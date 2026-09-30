"""Style lint (`an.verify.style`): the measurement on synthetic frames, the target
check, the verifier's severities, and one ffmpeg round trip.

The estimators were checked against the research's own script on its six study
clips (identical to three decimals on every cadence and cut statistic); those
clips are copyrighted and not in the repo, so what is pinned here is behaviour on
frame sequences whose answer is known by construction.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from an.adapters._base import RenderResult
from an.ir.schema import SceneIR, Shot
from an.verify import StyleLintVerifier, Verifier
from an.verify.style import (
    METRICS,
    check_targets,
    measure_style,
    style_lint,
)
from an.verify.vision import FAILURE_SEVERITY

H, W = 18, 32


def _solid(rgb, n=1):
    return np.broadcast_to(np.array(rgb, np.uint8), (n, H, W, 3)).copy()


def _moving(n, *, every=1, hold_after=None, base=(90, 90, 90)):
    """``n`` frames where a white bar advances every ``every`` frames."""
    frames = _solid(base, n)
    pos = 0
    for i in range(n):
        if i and i % every == 0 and (hold_after is None or i < hold_after):
            pos += 1
        frames[i, :, pos % W] = 255
    return frames


def test_on_ones_on_twos_and_holds_are_told_apart():
    ones = measure_style(_moving(48, every=1), fps=24.0, shot_durations=[2.0])
    twos = measure_style(_moving(48, every=2), fps=24.0, shot_durations=[2.0])
    assert ones.one_frame_interval_share == 1.0
    assert ones.identical_frame_share == 0.0
    assert twos.two_frame_interval_share == 1.0
    assert twos.identical_frame_share == pytest.approx(0.5, abs=0.02)
    assert twos.pose_changes_per_s == pytest.approx(12.0, abs=0.6)


def test_a_uniformly_moving_clip_is_not_measured_as_a_still():
    """Without the noise-floor cap, a clip whose every step differs by the same
    amount has its motion taken for compression noise and reads 100% held."""
    m = measure_style(_moving(30, every=1), fps=30.0, shot_durations=[1.0])
    assert m.identical_frame_share == 0.0


def test_the_longest_hold_is_counted_in_frames():
    m = measure_style(_moving(40, every=1, hold_after=10), fps=20.0, shot_durations=[2.0])
    assert m.max_hold_frames == 31  # frames 9..39 show one picture


def test_cuts_from_the_shot_list_are_exact():
    frames = _moving(96)
    m = measure_style(frames, fps=24.0, shot_durations=[1.0, 1.0, 2.0])
    assert (m.cuts, m.cut_source) == (2, "shots")
    assert m.cuts_per_min == 30.0
    assert m.mean_shot_s == pytest.approx(4 / 3, abs=1e-3)


def test_the_pixel_cut_detector_finds_a_hard_colour_change():
    frames = np.concatenate(
        [_solid((200, 30, 30), 24), _solid((20, 20, 120), 24), _solid((240, 240, 60), 24)]
    )
    m = measure_style(frames, fps=24.0)
    assert (m.cuts, m.cut_source) == (2, "pixels")
    assert m.mean_shot_s == 1.0
    # The step INTO a cut is an edit, not a pose change: no cadence recorded.
    assert m.one_frame_interval_share == 0.0


def test_palette_statistics():
    red = measure_style(_solid((255, 0, 0), 4), fps=4.0)
    grey = measure_style(_solid((40, 40, 40), 4), fps=4.0)
    assert red.mean_saturation == 1.0 and red.dark_pixel_share == 0.0
    assert grey.mean_saturation == 0.0 and grey.dark_pixel_share == 1.0
    assert red.top16_colour_coverage == 1.0


@pytest.mark.parametrize(
    "bad",
    [np.zeros((1, H, W, 3), np.uint8), np.zeros((4, H, W), np.uint8), np.zeros((4, H, W, 3))],
)
def test_measure_refuses_what_it_cannot_measure(bad):
    with pytest.raises(ValueError):
        measure_style(bad, fps=24.0)


def test_every_metric_has_a_fix_in_both_directions():
    from an.verify.style import _FIXES, StyleMetrics

    fields = set(StyleMetrics.__dataclass_fields__)
    assert set(METRICS) <= fields
    assert set(_FIXES) == set(METRICS)


def test_a_miss_names_the_direction_and_a_fix():
    m = measure_style(_moving(48, every=1), fps=24.0, shot_durations=[2.0])
    (f,) = check_targets(m, {"identical_frame_share": [0.55, 0.70]})
    assert f.severity == "warning" and "below" in f.description
    assert "step_hz" in f.suggested_fix


@pytest.mark.parametrize(
    "targets",
    [{"camera_shake": [0, 1]}, {"cuts_per_min": 12}, {"cuts_per_min": [14, 10]},
     {"cuts_per_min": "10-14"}],
)
def test_a_malformed_target_is_refused_at_construction(targets):
    with pytest.raises(ValueError):
        StyleLintVerifier(targets)


def test_the_verifier_is_a_verifier_and_skips_before_a_render():
    v = StyleLintVerifier({"cuts_per_min": [10, 14]})
    assert isinstance(v, Verifier)
    rep = v.verify(SceneIR(timeline=[Shot(id="s1", duration=1.0)]), None)
    assert rep.passed
    assert [f.severity for f in rep.findings] == ["info"]


def test_a_lint_that_could_not_run_does_not_read_as_clean(tmp_path):
    """The an#39 rule: a configured-and-broken verifier reports above `info`."""
    missing = tmp_path / "nope.mp4"
    rep = StyleLintVerifier({"cuts_per_min": [10, 14]}).verify(
        SceneIR(timeline=[Shot(id="s1", duration=1.0)]),
        RenderResult(mp4_path=missing, duration=1.0),
    )
    assert any(f.severity == FAILURE_SEVERITY for f in rep.findings)
    assert all(f.severity != "info" for f in rep.findings)


def test_a_spec_file_is_read_for_its_targets(tmp_path):
    spec = tmp_path / "s.yaml"
    spec.write_text(
        "style: demo\nlive: {}\ntargets:\n  cuts_per_min: [10, 14]\n", encoding="utf-8"
    )
    v = StyleLintVerifier(spec)
    assert (v.style, v.targets) == ("demo", {"cuts_per_min": [10, 14]})


def _encode(frames: np.ndarray, fps: int, out: Path) -> Path:
    n, h, w, _ = frames.shape
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv444p", "-crf", "12", str(out)],
        input=frames.tobytes(),
        check=True,
    )
    return out


@pytest.mark.ffmpeg
def test_round_trip_through_an_encoded_mp4(tmp_path):
    """Encode a known on-twos clip, decode it through the lint, get twos back."""
    frames = np.repeat(_moving(48, every=2), 1, axis=0)
    frames = np.stack([np.kron(f, np.ones((10, 10, 1), np.uint8)) for f in frames])
    mp4 = _encode(frames, 24, tmp_path / "twos.mp4")
    result = style_lint(
        mp4,
        {"style": "t", "targets": {"identical_frame_share": [0.4, 0.6],
                                    "two_frame_interval_share": [0.9, 1.0]}},
        shot_durations=[2.0],
    )
    assert result.metrics is not None
    assert result.metrics.fps == 24.0 and result.metrics.frames == 48
    assert result.report.passed
    assert [f.severity for f in result.report.findings] == ["info"]


# -----------------------------------------------------------------------------
# Per-shot breakdown, the authored shot list, and the CLI (e2e findings 4 and 5)
# -----------------------------------------------------------------------------


def test_per_shot_cadence_finds_the_static_shot():
    """The OverSimplified e2e run: a static date card held the whole clip's
    identical-frame share up, and only a hand-written per-shot script showed it."""
    from an.verify.style import measure_shots

    card = _solid((4, 4, 4), 24)
    busy = _moving(24, every=1)
    rows = measure_shots(
        np.concatenate([card, busy]),
        fps=24.0,
        shot_durations=[1.0, 1.0],
        shot_ids=["date_card", "map"],
    )
    assert [r.shot for r in rows] == ["date_card", "map"]
    assert rows[0].identical_frame_share == 1.0
    assert rows[1].identical_frame_share == 0.0
    assert [r.start_s for r in rows] == [0.0, 1.0]


def test_film_shots_take_a_dissolve_out_of_the_shot_it_overlaps():
    from an.ir.schema import Meta, Transition
    from an.verify.style import film_shots

    scene = SceneIR(
        meta=Meta(fps=24),
        timeline=[
            Shot(id="a", duration=2.0),
            Shot(id="b", duration=2.0, transition=Transition(kind="dissolve", duration=0.5)),
            Shot(id="c", duration=1.0, transition=Transition(kind="fade", duration=0.5)),
        ],
    )
    assert film_shots(scene) == [("a", 1.5), ("b", 2.0), ("c", 1.0)]


def test_a_render_finds_its_own_project(tmp_path):
    from an.verify.style import project_of_render

    (tmp_path / "ir").mkdir()
    (tmp_path / "ir" / "scene.json").write_text("{}", encoding="utf-8")
    (tmp_path / "output").mkdir()
    assert project_of_render(tmp_path / "output" / "main.mp4") == tmp_path.resolve()
    assert project_of_render(tmp_path / "elsewhere.mp4") is None


@pytest.mark.ffmpeg
def test_the_scene_gives_exact_cuts_where_pixels_find_none(tmp_path):
    """Two shots on one backdrop: pixels see no cut, the scene knows there is one."""
    frames = _moving(48, every=2)
    frames = np.stack([np.kron(f, np.ones((10, 10, 1), np.uint8)) for f in frames])
    mp4 = _encode(frames, 24, tmp_path / "two_shots.mp4")
    spec = {"style": "t", "targets": {"cuts_per_min": [20, 40]}}

    by_pixels = style_lint(mp4, spec)
    assert by_pixels.metrics.cut_source == "pixels" and by_pixels.metrics.cuts == 0
    assert any("detected from pixels" in f.description for f in by_pixels.report.findings)

    scene = SceneIR(timeline=[Shot(id="s1", duration=1.0), Shot(id="s2", duration=1.0)])
    scene.meta.fps = 24
    exact = style_lint(mp4, spec, scene=scene)
    assert exact.metrics.cut_source == "shots" and exact.metrics.cuts == 1
    assert [r.shot for r in exact.per_shot] == ["s1", "s2"]
    assert exact.report.passed


def test_running_the_module_does_not_warn_about_sys_modules():
    """``python -m an.verify.style`` printed a RuntimeWarning, because the
    package imported the module it was about to run as ``__main__``."""
    import os
    import sys

    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root)}  # this checkout, not an installed copy
    proc = subprocess.run(
        [sys.executable, "-W", "error::RuntimeWarning", "-m", "an.verify.style", "--help"],
        capture_output=True,
        text=True,
        cwd=root,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "RuntimeWarning" not in proc.stderr
    assert "--project" in proc.stdout


def test_the_verifier_is_still_importable_from_the_package():
    import an.verify

    assert an.verify.StyleLintVerifier is StyleLintVerifier
