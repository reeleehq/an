"""The impact harness: performance, stroke, ground truth, and the rendered pixels.

The contract under test is the one a downstream estimator relies on: three
times kept apart (intended grid time, executed impact time in continuous
seconds, what the frames show), and a sidecar that cannot drift from its video.
Everything but the last section runs in the default lane — the truth and the
keypoints come from the compiled document, not from a browser.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import replace

import numpy as np
import pytest

from an.impacts import (
    ImpactClipSpec,
    TempoMap,
    TruthMismatch,
    build_stroke,
    gaussian_humanizer,
    impact_set_specs,
    perform,
    plan_impact_clip,
    write_impact_clip,
    write_impact_set,
)
from an.impacts.performance import MAX_OFFSET_FRACTION, PerformanceError
from an.impacts.stroke import StrokeError

# --- tempo and performance ------------------------------------------------------


def test_the_tempo_map_integrates_a_ramp_exactly():
    m = TempoMap(((0.0, 80.0), (8.0, 140.0), (12.0, 140.0)))
    for beat in (0.5, 3.0, 8.0, 10.0, 15.0):
        xs = np.linspace(0.0, beat, 200001)
        numeric = np.trapezoid(60.0 / np.array([m.bpm_at(x) for x in xs]), xs)
        assert m.time_of(beat) == pytest.approx(numeric, abs=1e-8), beat


def test_without_humanisation_executed_equals_intended():
    events = perform([(0, 90), (8, 120)], beats=8, subdivision=2, pattern=(1, 0, 0.5))
    assert all(e.t_impact == e.t_grid and e.offset == 0.0 for e in events)
    # A rest is absent, not a zero-height hit.
    assert [e.beat for e in events][:4] == [0.0, 1.0, 1.5, 2.5]


def test_humanisation_is_seeded_and_never_reorders_impacts():
    kwargs = dict(beats=64, subdivision=4, humanizer=gaussian_humanizer(0.5))  # absurd sd
    events = perform(120, seed=4, **kwargs)
    assert events == perform(120, seed=4, **kwargs)
    assert events != perform(120, seed=5, **kwargs)
    times = [e.t_impact for e in events]
    assert all(b > a for a, b in zip(times, times[1:]))
    gap = 60.0 / 120 / 4
    assert max(abs(e.offset) for e in events) <= MAX_OFFSET_FRACTION * gap + 1e-12


def test_the_humanizer_s_rho_shapes_the_wander_not_its_size():
    rng = np.random.default_rng(1)
    offs = np.array(gaussian_humanizer(0.01, rho=0.8)([0.0] * 50000, rng))
    assert offs.std() == pytest.approx(0.01, rel=0.05)
    assert np.corrcoef(offs[:-1], offs[1:])[0, 1] == pytest.approx(0.8, abs=0.02)


@pytest.mark.parametrize(
    "kwargs",
    [{"beats": 0}, {"pattern": (0, 0)}, {"pattern": (1.5,)}, {"lead_in": -1}],
)
def test_an_unplayable_performance_is_refused(kwargs):
    with pytest.raises(PerformanceError):
        perform(100, **kwargs)


# --- the stroke -----------------------------------------------------------------


def _dense(stroke, hz=20000):
    ts = np.linspace(0.0, stroke.duration, int(stroke.duration * hz) + 1)
    return ts, np.array([stroke.h(t) for t in ts])


@pytest.mark.parametrize("kind", ["surface", "air"])
def test_the_stroke_reaches_contact_exactly_at_each_executed_impact(kind):
    events = perform(
        [(0, 70), (12, 150)], beats=12, subdivision=2, pattern=(1, 0.5, 0, 0.8),
        humanizer=gaussian_humanizer(0.02, rho=0.4), seed=2,
    )
    stroke = build_stroke(events, kind=kind, duration=events[-1].t_impact + 0.5)
    assert [stroke.h(e.t_impact) for e in events] == [0.0] * len(events)
    ts, hs = _dense(stroke)
    assert hs.min() >= 0.0 and hs.max() <= 1.0 + 1e-12
    # The object comes near contact ONLY around impacts, and around every one.
    near = ts[hs < 0.01]
    impacts = np.array([e.t_impact for e in events])
    distance = np.abs(near[:, None] - impacts[None, :])
    # An air stroke's turning point is FLAT (it dwells near h=0 for ~20 ms);
    # a surface contact is a sharp V. 30 ms bounds both.
    assert distance.min(axis=1).max() < 0.03
    assert (distance.min(axis=0) < 1e-3).all()


def test_a_surface_impact_reverses_velocity_and_an_air_impact_turns():
    events = perform(100, beats=6)
    surface = build_stroke(events, kind="surface", duration=4.5)
    air = build_stroke(events, kind="air", duration=4.5)
    for k_s, k_a, e in zip(surface.kinematics, air.kinematics, events):
        T = e.t_impact
        assert surface.velocity(T - 1e-9) == pytest.approx(-k_s.peak_speed, rel=1e-6)
        assert surface.velocity(T) == pytest.approx(k_s.peak_speed, rel=1e-6)  # the bounce
        assert air.velocity(T - 1e-9) == pytest.approx(0.0, abs=1e-5)
        assert air.velocity(T) == 0.0
        assert k_a.t_peak_speed == pytest.approx(T - k_a.brake)
        assert -air.velocity(k_a.t_peak_speed) == pytest.approx(k_a.peak_speed, rel=1e-9)


def test_air_velocity_is_continuous_everywhere():
    events = perform(140, beats=8, pattern=(1, 0.4))
    stroke = build_stroke(events, kind="air", duration=events[-1].t_impact + 0.5)
    ts = np.linspace(0.0, stroke.duration, 200001)
    vs = np.array([stroke.velocity(t) for t in ts])
    dt = ts[1] - ts[0]
    # Largest acceleration the stroke uses is the brake's, 2 * d / b^2 in
    # stroke heights / s^2; a velocity JUMP would exceed it per sample by far.
    worst = max(2 * k.apex / k.fall / k.brake for k in stroke.kinematics)
    assert np.abs(np.diff(vs)).max() <= worst * dt * 1.01


def test_a_stroke_refuses_impacts_it_cannot_place():
    events = perform(100, beats=2)
    with pytest.raises(StrokeError):
        build_stroke(events, kind="sideways", duration=3.0)  # type: ignore[arg-type]
    with pytest.raises(StrokeError):
        build_stroke(events, duration=events[-1].t_impact)  # no room after the last


# --- the plan, the compiled scene, the ground truth ---------------------------------


def _jittery(**kw) -> ImpactClipSpec:
    return ImpactClipSpec(**{"beats": 6, "jitter_sd": 0.013, "jitter_rho": 0.3, "seed": 11, **kw})


@pytest.mark.parametrize("obj", ["stick", "ball"])
@pytest.mark.parametrize("kind", ["surface", "air"])
def test_every_impact_is_a_keyframe_at_its_exact_float(obj, kind, tmp_path):
    """The executed time is where the rendered motion actually turns — bit-exact,
    not a frame, not a rounding of the sum of the segments before it."""
    from an.adapters.cutout.compile import compile_shot
    from an.impacts.clip import _install_props
    from an.stores import build_project_mall

    plan = plan_impact_clip(_jittery(object=obj, kind=kind))
    mall = build_project_mall(tmp_path, ensure=True)
    _install_props(plan, mall)
    scene = compile_shot(plan.shot, mall=mall, fps=30, width=640, height=360, strict_assets=True)
    starts = {
        placed.start_time
        for track in scene.timeline.tracks
        for placed in track.clips
    }
    for e in plan.events:
        assert e.t_impact in starts
        assert e.t_impact * 30 != round(e.t_impact * 30)  # genuinely sub-frame


def test_the_sidecar_keeps_the_three_times_apart(tmp_path):
    spec = _jittery(kind="air", fps=24, exposure=0.5, timestamp_jitter_sd=0.004)
    clip = write_impact_clip(spec, tmp_path, render=False)
    truth = json.loads((clip / "truth.json").read_text(encoding="utf-8"))
    assert truth["schema"] == "an.impacts/truth"
    assert not (clip / "clip.mp4").exists() and "video" not in truth["clip"]["files"]
    frames = truth["frames"]
    assert len(frames) == truth["clip"]["frame_count"] == round(truth["clip"]["duration"] * 24)
    offsets = [e["t_impact"] - e["t_grid"] for e in truth["events"]]
    assert any(abs(o) > 1e-3 for o in offsets) and offsets == pytest.approx(
        [e["offset"] for e in truth["events"]]
    )
    for e in truth["events"]:
        ev, T = e["frames"], e["t_impact"]
        if ev["before"] is not None:
            assert frames[ev["before"]]["t_close"] <= T
        if ev["after"] is not None:
            assert frames[ev["after"]]["t_open"] >= T
        if ev["during"] is not None:
            f = frames[ev["during"]]
            assert f["t_open"] < T < f["t_close"]
        assert e["t_peak_speed"] == pytest.approx(T - e["brake"])
    # With capture jitter, the actual instants are off the nominal grid.
    assert any(f["t_open"] != f["t_nominal"] for f in frames)
    assert all(len(f["samples"]) == 8 for f in frames)


@pytest.mark.parametrize("fps", [24, 29.97, 44, 60])
def test_any_camera_rate_gets_one_frame_record_per_rendered_frame(fps, tmp_path):
    spec = _jittery(fps=fps)
    truth = json.loads((write_impact_clip(spec, tmp_path, render=False) / "truth.json").read_text(encoding="utf-8"))
    n = max(1, int(round(truth["clip"]["duration"] * fps)))  # CutoutRenderer's count
    assert truth["clip"]["frame_count"] == len(truth["frames"]) == n
    assert [f["t_nominal"] for f in truth["frames"]] == [i / fps for i in range(n)]


def test_the_keypoint_stream_is_thoremin_s_recorder_shape_and_nothing_more(tmp_path):
    clip = write_impact_clip(_jittery(object="ball"), tmp_path, render=False)
    lines = [json.loads(line) for line in (clip / "keypoints.ndjson").read_text(encoding="utf-8").splitlines()]
    truth = json.loads((clip / "truth.json").read_text(encoding="utf-8"))
    assert len(lines) == len(truth["frames"])
    for i, line in enumerate(lines):
        assert set(line) == {"tick", "t", "value"}  # no ground truth leaks in
        assert line["tick"] == i
        assert set(line["value"]) == {"width", "height", "keypoints"}
        points = line["value"]["keypoints"]
        assert [(k["object"], k["name"]) for k in points] == [("ball", "center"), ("ball", "bottom")]
        for k in points:
            x, y = truth["frames"][i]["keypoints"]["ball"][k["name"]]
            assert (k["x"], k["y"]) == pytest.approx((x, y), abs=1e-4)
    assert [ln["t"] for ln in lines] == pytest.approx([f["t_reported"] for f in truth["frames"]])


def test_the_trajectory_is_dense_and_touches_contact_at_each_impact(tmp_path):
    spec = _jittery(object="ball", trajectory_hz=2000.0)
    clip = write_impact_clip(spec, tmp_path, render=False)
    rows = list(csv.reader((clip / "trajectory.csv").open(encoding="utf-8")))
    assert rows[0] == ["t", "h", "ball.center_x", "ball.center_y", "ball.bottom_x", "ball.bottom_y"]
    body = np.array(rows[1:], dtype=float)
    assert np.diff(body[:, 0]).max() == pytest.approx(1 / 2000.0, abs=1e-9)
    truth = json.loads((clip / "truth.json").read_text(encoding="utf-8"))
    floor_y = max(e["impact_xy"][1] for e in truth["events"])
    assert body[:, 5].max() <= floor_y + 1e-9  # the bottom never passes the floor
    assert body[:, 5].max() == pytest.approx(floor_y, abs=0.1)
    assert {round(e["impact_xy"][1], 9) for e in truth["events"]} == {round(floor_y, 9)}


def test_a_clip_regenerates_from_its_own_sidecar(tmp_path):
    spec = _jittery(tempo=((0, 90), (6, 110)), pattern=(1, 0.5))
    first = write_impact_clip(spec, tmp_path / "a", render=False)
    again = ImpactClipSpec.from_dict(json.loads((first / "truth.json").read_text(encoding="utf-8"))["spec"])
    assert again == spec
    second = write_impact_clip(again, tmp_path / "b", render=False)
    for name in ("truth.json", "keypoints.ndjson", "trajectory.csv", "scene.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_camera_variants_share_one_performance():
    specs = impact_set_specs(base=_jittery(), fps=(24, 60), exposures=(0.0, 0.5))
    events = {tuple((e.t_grid, e.t_impact) for e in plan_impact_clip(s).events) for s in specs}
    assert len(events) == 1, "a camera setting changed the performance"
    assert len({s.clip_id for s in specs}) == len(specs)


def test_the_truth_refuses_a_document_that_disagrees_with_the_stroke(monkeypatch, tmp_path):
    from an.impacts import truth as truth_mod

    real = truth_mod._Projector.analytic

    def drifted(self, t):
        return {k: (x + 0.01, y) for k, (x, y) in real(self, t).items()}

    monkeypatch.setattr(truth_mod._Projector, "analytic", drifted)
    with pytest.raises(TruthMismatch, match="compiled"):
        write_impact_clip(_jittery(), tmp_path, render=False)


def test_the_truth_refuses_a_document_that_misses_contact(monkeypatch, tmp_path):
    from an.impacts import clip as clip_mod

    real_plan = clip_mod.plan_impact_clip

    def late(spec):
        plan = real_plan(spec)
        # Shift the ground truth, not the motion: every impact now claims a time
        # 2 ms after the one the document animates.
        shifted = tuple(replace(e, t_impact=e.t_impact + 0.002) for e in plan.events)
        return replace(plan, events=shifted)

    monkeypatch.setattr(clip_mod, "plan_impact_clip", late)
    with pytest.raises(TruthMismatch, match="contact value"):
        clip_mod.write_impact_clip(_jittery(), tmp_path, render=False)


def test_a_blurred_frame_shows_the_average_of_its_samples_not_mid_exposure(tmp_path):
    """The review's blocker: at a surface contact the path is a V, so a frame
    whose exposure spans it SHOWS the object above contact — the average of the
    sampled positions — while the mid-exposure position is at contact."""
    spec = ImpactClipSpec(object="ball", beats=4, tempo=120, jitter_sd=0.0, exposure=0.5, fps=30,
                          lead_in=0.5 + 0.25 / 30)  # every impact mid-exposure
    truth = json.loads((write_impact_clip(spec, tmp_path, render=False) / "truth.json")
                       .read_text(encoding="utf-8"))
    plan = plan_impact_clip(spec)
    ball = plan.obj
    for f in truth["frames"]:
        ys = [ball.pose(plan.stroke.h(t))[("ball", "y")] + 180.0 for t in f["samples"]]
        assert f["keypoints"]["ball"]["center"][1] == pytest.approx(sum(ys) / len(ys), abs=1e-6)
    gaps = [
        abs(truth["frames"][e["frames"]["during"]]["keypoints"]["ball"]["center"][1]
            - truth["frames"][e["frames"]["during"]]["keypoints_mid"]["ball"]["center"][1])
        for e in truth["events"]
    ]
    assert min(gaps) > 2.0, gaps  # the two genuinely differ at contact


def test_the_frame_evidence_is_right_by_brute_force(tmp_path):
    spec = _jittery(fps=24, exposure=0.5, timestamp_jitter_sd=0.002, beats=10)
    truth = json.loads((write_impact_clip(spec, tmp_path, render=False) / "truth.json")
                       .read_text(encoding="utf-8"))
    stroke = plan_impact_clip(spec).stroke
    frames = truth["frames"]
    shown = [sum(stroke.h(t) for t in f["samples"]) / len(f["samples"]) for f in frames]
    times = [e["t_impact"] for e in truth["events"]]
    for k, e in enumerate(truth["events"]):
        ev, T = e["frames"], e["t_impact"]
        before = [f["index"] for f in frames if f["t_close"] <= T]
        after = [f["index"] for f in frames if f["t_open"] >= T]
        during = [f["index"] for f in frames if f["t_open"] < T < f["t_close"]]
        assert ev["before"] == (before[-1] if before else None)
        assert ev["after"] == (after[0] if after else None)
        assert ev["during"] == (during[0] if during else None)
        assert ev["nearest"] == min(frames, key=lambda f: abs(f["t_mid"] - T))["index"]
        lo = (times[k - 1] + T) / 2 if k else 0.0
        hi = (T + times[k + 1]) / 2 if k + 1 < len(times) else truth["clip"]["duration"]
        window = [f["index"] for f in frames if lo <= f["t_mid"] <= hi]
        assert shown[ev["lowest"]] == min(shown[i] for i in window)
        assert ev["lowest_error"] == pytest.approx(frames[ev["lowest"]]["t_reported"] - T)


def test_equal_specs_name_one_directory():
    assert ImpactClipSpec(fps=30, tempo=100).clip_id == ImpactClipSpec(fps=30.0, tempo=100.0).clip_id
    with pytest.raises(ValueError):
        ImpactClipSpec(tail=0)
    with pytest.raises(ValueError, match="unknown"):
        ImpactClipSpec.from_dict({**ImpactClipSpec().to_dict(), "wobble": 1})


def test_the_stick_s_rounded_end_meets_the_surface_top_at_contact():
    from an.impacts.objects import stick

    s = stick()
    L, r = s.params["length"], s.params["thickness"] / 2
    (ch,) = s.channels
    a = ch.contact_value
    # The cap's centre is r short of the axis end; its lowest point is r below it.
    lowest_y = s.at[1] + (L - r) * math.sin(a) + r
    assert lowest_y == pytest.approx(s.surface_at[1])
    assert s.at[0] + (L - r) * math.cos(a) == pytest.approx(s.surface_at[0])


def test_a_truth_only_rewrite_removes_a_stale_video(tmp_path):
    spec = _jittery()
    (tmp_path / spec.clip_id).mkdir()
    (tmp_path / spec.clip_id / "clip.mp4").write_bytes(b"old")
    clip = write_impact_clip(spec, tmp_path, render=False)
    assert not (clip / "clip.mp4").exists()


def test_a_two_channel_object_with_a_child_node_keypoint_stays_exact(monkeypatch, tmp_path):
    """The seam a forearm-plus-stick limb uses: several channels, each affine in
    the same h, and a keypoint on a node below the entity. The truth's own
    cross-check (compiled vs analytic, at every sample) is the assertion that
    matters — it raises if the multi-channel tweens drift from the stroke."""
    from an.impacts.objects import IMPACT_OBJECTS, StrokeChannel, ball

    def diagonal_ball():
        b = ball()
        return replace(
            b,
            channels=(*b.channels, StrokeChannel("ball", "x", 0.0, 60.0)),
            keypoint_nodes={"center": "ball/body"},
        )

    monkeypatch.setitem(IMPACT_OBJECTS, "diagonal", diagonal_ball)
    spec = _jittery(object="diagonal", exposure=0.5)
    truth = json.loads((write_impact_clip(spec, tmp_path, render=False) / "truth.json")
                       .read_text(encoding="utf-8"))
    (obj,) = truth["objects"]
    assert [(c["target"], c["property"]) for c in obj["stroke"]["channels"]] == [
        ("ball", "y"), ("ball", "x")
    ]
    xs = [f["keypoints"]["ball"]["center"][0] for f in truth["frames"]]
    assert max(xs) - min(xs) > 50  # the second channel really moves it
    for e in truth["events"]:
        assert e["impact_xy"][0] == pytest.approx(320.0)  # x is at contact too


def test_noisy_report_timestamps_never_run_backwards():
    from an.frame_clock import FrameClock, FrameClockError

    clock = FrameClock(fps=30, report_noise_sd=0.004, seed=9)
    reported = [f.t_reported for f in clock.frames(30.0)]
    assert all(b > a for a, b in zip(reported, reported[1:]))
    with pytest.raises(FrameClockError, match="keep increasing"):
        FrameClock(fps=30, report_noise_sd=0.02)


def test_a_spec_refuses_what_it_would_otherwise_bend():
    with pytest.raises(ValueError, match="whole number"):
        ImpactClipSpec(beats=2.7)
    with pytest.raises(ValueError, match="frame period"):
        ImpactClipSpec(tail=1e-12)
    assert ImpactClipSpec(beats=4.0).beats == 4


def test_a_set_writes_an_index(tmp_path):
    specs = impact_set_specs(base=replace(_jittery(), beats=2), objects=("ball",), fps=(30,), exposures=(0.0,))
    seen = []
    root = write_impact_set(tmp_path, specs, render=False, progress=lambda i, n, d: seen.append((i, n)))
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert [c["clip"] for c in index["clips"]] == [s.clip_id for s in specs]
    assert seen == [(1, 2), (2, 2)]
    assert all((root / c["clip"] / "truth.json").exists() for c in index["clips"])


def test_the_cli_namespace_is_wired():
    from an.tools import _dispatch_namespaces

    names = {f.__name__ for f in _dispatch_namespaces["impacts"]}
    assert names == {"clip", "clip_set"}


def test_the_cli_writes_a_truth_only_clip(tmp_path):
    from an.impacts.cli import clip

    msg = clip(str(tmp_path), object="ball", kind="air", tempo="0:90,4:120", beats=4,
               pattern="1,0.5", jitter_sd=0.01, render=False)
    (made,) = tmp_path.iterdir()
    assert str(made) in msg
    spec = json.loads((made / "truth.json").read_text(encoding="utf-8"))["spec"]
    assert spec["tempo"] == [[0.0, 90.0], [4.0, 120.0]] and spec["pattern"] == [1.0, 0.5]


# --- the pixels (browser lane) ----------------------------------------------------


def _decode(mp4, width, height):
    import subprocess

    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp4), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width, 3).astype(float)


def _dark_centroid(frame, surface_top):
    """Darkness-weighted centroid above the surface — no threshold, so a smear's
    faint edges count in proportion, which is what makes a blurred frame's
    centroid the average of its sampled positions."""
    lum = frame.mean(axis=2)
    w = np.clip(255.0 - lum, 0, None)
    if surface_top is not None:
        w[int(math.floor(surface_top)):] = 0.0  # the slab; the object never enters it
    ys, xs = np.indices(lum.shape)
    return (w * xs).sum() / w.sum() + 0.5, (w * ys).sum() / w.sum() + 0.5, w


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_the_rendered_pixels_are_where_the_truth_says(tmp_path):
    """MUTATION: drop `frame_samples=` from `_render`'s RenderContext, flip the
    stick's anchor, or report the blurred keypoint at mid-exposure — the
    centroids leave the keypoints by pixels, not tenths.

    Surface impacts through an open shutter are in the set on purpose: that is
    where the frame shows the average of a V-shaped path, not its midpoint.
    Also the averaging path's only behavioural test: an open shutter must SMEAR.
    """
    base = ImpactClipSpec(beats=3, tempo=120, jitter_sd=0.01, seed=5)
    smear = {}
    for spec in (
        base,
        replace(base, exposure=0.5),
        replace(base, object="ball", exposure=0.5, timestamp_jitter_sd=0.003, fps=29.97),
        replace(base, object="ball"),
        replace(base, object="ball", kind="air", exposure=0.5),
    ):
        clip = write_impact_clip(spec, tmp_path)
        truth = json.loads((clip / "truth.json").read_text(encoding="utf-8"))
        (obj,) = truth["objects"]
        top = obj["surface_xy"][1] if spec.kind == "surface" else None
        frames = _decode(clip / "clip.mp4", spec.width, spec.height)
        assert len(frames) == truth["clip"]["frame_count"]
        lines = [json.loads(ln) for ln in (clip / "keypoints.ndjson").read_text(encoding="utf-8").splitlines()]
        errors, partial = [], []
        for frame, line in zip(frames, lines):
            p = {k["name"]: (k["x"], k["y"]) for k in line["value"]["keypoints"]}
            want = p["center"] if "center" in p else tuple(
                (a + b) / 2 for a, b in zip(p["pivot"], p["tip"])
            )
            cx, cy, w = _dark_centroid(frame, top)
            errors.append(math.hypot(cx - want[0], cy - want[1]))
            partial.append(int(((w > 20) & (w < 200)).sum()))
        assert max(errors) < 1.0, (spec.clip_id, max(errors))
        smear[(spec.object, spec.kind, spec.exposure)] = max(partial)
    assert smear[("ball", "surface", 0.5)] > 2 * smear[("ball", "surface", 0.0)], smear
