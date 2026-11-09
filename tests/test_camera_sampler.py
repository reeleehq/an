"""One sampler for a camera the runtime cannot evaluate itself (an#626).

A follow (an#445) and a dolly (an#478) are compiled to keys the compiler lays
on a grid; the runtime interpolates between them. These tests read the
compiled document through the runtime's executable spec (`evaluate_timeline`
+ `screen_position`, no browser) at the instants a render samples: a shutter's
sub-frame ones, and the instants between a stepped shot's steps.
"""

from __future__ import annotations

import math

import pytest

from an.frame_clock import (
    CameraGrid,
    FrameClock,
    FrameClockError,
    camera_grid,
    frame_times,
    grid_times,
)
from an.ir.schema import (
    AssetRef,
    Camera,
    CameraFollow,
    CameraKey,
    Meta,
    SceneIR,
    Shot,
    StagePlacement,
    TweenAction,
)
from an.stage.compile import compile_args, compile_shot

FPS, W, H, DURATION = 12, 640, 360, 2.0
#: A 180-degree shutter, four instants a frame: what `RenderContext.frame_samples` carries.
SHUTTER = FrameClock(fps=FPS, exposure=0.5, samples=4).sample_times(DURATION)


# --- the sampler itself -----------------------------------------------------------


def test_the_default_grid_is_every_frame_linearly():
    grid = camera_grid(DURATION, fps=FPS)
    assert list(grid.times) == frame_times(DURATION, fps=FPS) == list(grid.base)
    assert grid.easing == "linear" and not grid.stepped


def test_every_shutter_instant_is_a_key_and_the_frames_stay():
    grid = camera_grid(DURATION, fps=FPS, frame_samples=SHUTTER)
    assert set(frame_times(DURATION, fps=FPS)) <= set(grid.times)
    assert {t for frame in SHUTTER for t in frame} <= set(grid.times)
    assert list(grid.times) == sorted(set(grid.times))
    assert grid.base == tuple(frame_times(DURATION, fps=FPS))


def test_the_sampler_alone_clips_merges_and_refuses_bad_samples():
    """A direct unit test of `camera_grid`: no render reaches the clipping
    (`check_frame_samples` refuses an instant outside the shot before a
    compile), so it only guards the sampler's own contract."""
    grid = camera_grid(
        1.0, fps=4, frame_samples=[[-0.5, 0.0, 0.25 + 1e-12], [0.5], [0.75], [2.0]]
    )
    assert grid.times == (0.0, 0.25, 0.5, 0.75, 1.0)  # clipped onto 0 and 1, merged
    with pytest.raises(FrameClockError, match="non-finite"):
        camera_grid(1.0, fps=4, frame_samples=[[math.nan], [0.25], [0.5], [0.75]])


def test_another_shots_frame_samples_are_refused(tmp_path):
    """Samples for a shot of another length would key the camera at the
    wrong instants: refused, by the sampler and so by every compile."""
    with pytest.raises(FrameClockError, match="24 frame"):
        camera_grid(1.0, fps=FPS, frame_samples=SHUTTER)
    with pytest.raises(FrameClockError, match="another shot's samples"):
        compile_shot(
            _follow(),
            mall=_dot_mall(tmp_path),
            fps=FPS,
            width=W,
            height=H,
            frame_samples=SHUTTER[:-1],
        )


def test_a_stepped_grid_is_every_frame_and_every_step_step_eased():
    grid = camera_grid(1.0, fps=12, step_hz=5)
    steps = grid_times(1.0, fps=12, step_hz=5)
    assert set(frame_times(1.0, fps=12)) <= set(grid.times)
    assert all(any(abs(s - t) < 1e-9 for t in grid.times) for s in steps)
    assert grid.easing == "step" and grid.base == grid.times
    assert isinstance(grid, CameraGrid)


def test_the_solve_and_the_ir_share_the_grid_rule():
    from an.ir.camera import frame_times as ir_frame_times
    from an.stage.compile import step_times as compile_step_times
    from an.stage.solve import frame_times as solve_frame_times

    assert ir_frame_times(duration=0.5, fps=4) == frame_times(0.5, fps=4)
    assert solve_frame_times(0.25, fps=20, step_hz=10) == grid_times(
        0.25, fps=20, step_hz=10
    )
    assert solve_frame_times(0.1, fps=20, step_hz=None) == frame_times(0.1, fps=20)
    from an.frame_clock import step_times

    assert compile_step_times is step_times


# --- a follow ---------------------------------------------------------------------


def _dot_mall(tmp_path):
    from an.paths import PathDescriptor
    from an.stores import build_project_mall

    mall = build_project_mall(tmp_path, ensure=True)
    mall["props"]["dot"] = PathDescriptor(
        name="dot", points=[(0, 0), (0, -40)]
    ).model_dump(mode="json")
    return mall


def _follow(*, lag=0.0, overlay=None):
    return Shot(
        id="f",
        renderer="cutout",
        duration=DURATION,
        camera=Camera(
            follow=CameraFollow(target="dot", axes="xy", lag=lag), keys=overlay
        ),
        entities=[
            AssetRef(
                kind="prop",
                id="dot",
                store="props",
                ref="dot",
                stage=StagePlacement(at=(-100.0, 50.0)),
            )
        ],
        actions=[
            TweenAction(
                target="dot",
                property="x",
                to_value=200.0,
                duration=DURATION,
                easing="ease_in_out",
            ),
            TweenAction(
                target="dot",
                property="y",
                to_value=-40.0,
                duration=DURATION,
                easing="linear",
            ),
        ],
    )


def _screen(doc, path, times, **point):
    from an.stage.timeline import (
        evaluate_timeline,
        screen_position,
        timeline_from_scene,
    )

    tl = timeline_from_scene(doc)
    return [
        screen_position(doc, path, pose=evaluate_timeline(tl, t), **point)
        for t in times
    ]


def _drift(doc, times):
    """How far the followed dot strays from where it stood at the start."""
    track = _screen(doc, "dot", [0.0, *times])
    return max(abs(p[a] - track[0][a]) for p in track for a in (0, 1))


def _camera_keys(doc):
    return {
        ch.property: [(k.time, k.value, k.easing) for k in ch.keyframes]
        for aid, anim in doc.animations.items()
        if aid.startswith("__camera__")
        for ch in anim.channels
    }


@pytest.mark.parametrize(
    "overlay",
    [
        None,
        [CameraKey(at=0.0), CameraKey(at=DURATION, dolly=0.3, easing="ease_in_out")],
    ],
)
def test_a_follow_is_exact_at_a_shutters_sub_frame_samples(tmp_path, overlay):
    """The acceptance: compiled with the render's frame samples, the follow
    holds its target at every sub-frame instant; keyed a frame each, it did not."""
    mall, kw = _dot_mall(tmp_path), dict(fps=FPS, width=W, height=H, strict_assets=True)
    instants = [t for frame in SHUTTER for t in frame]
    plain = compile_shot(_follow(overlay=overlay), mall=mall, **kw)
    sampled = compile_shot(
        _follow(overlay=overlay), mall=mall, frame_samples=SHUTTER, **kw
    )
    assert _drift(plain, instants) > 0.05  # was off between frames
    assert _drift(sampled, instants) < 1e-6
    # and nothing moved at a whole frame
    frames = set(frame_times(DURATION, fps=FPS))
    for prop, keys in _camera_keys(plain).items():
        on_frames = [k for k in _camera_keys(sampled)[prop] if k[0] in frames]
        assert on_frames == keys, prop


def test_a_lagging_follow_keeps_its_frames_and_samples_its_own_trajectory(tmp_path):
    from an.ir.frames import lag_filter, lag_resample

    mall, kw = _dot_mall(tmp_path), dict(fps=FPS, width=W, height=H, strict_assets=True)
    plain = _camera_keys(compile_shot(_follow(lag=0.4), mall=mall, **kw))
    sampled = _camera_keys(
        compile_shot(_follow(lag=0.4), mall=mall, frame_samples=SHUTTER, **kw)
    )
    frames = frame_times(DURATION, fps=FPS)
    assert [k for k in sampled["pivot_x"] if k[0] in set(frames)] == plain["pivot_x"]
    # between frames: the filter's own trajectory, from the unlagged target
    ideal = _camera_keys(
        compile_shot(_follow(), mall=mall, frame_samples=SHUTTER, **kw)
    )["pivot_x"]
    ideal_at = dict((t, v) for t, v, _ in ideal)
    values = [ideal_at[t] for t in frames]
    lagged = lag_filter(values, lag=0.4, dt=1.0 / FPS)
    times = [t for t, *_ in sampled["pivot_x"]]
    want = lag_resample(frames, values, lagged, times, lag=0.4)
    assert [v for _, v, _ in sampled["pivot_x"]] == pytest.approx(want, abs=1e-9)


@pytest.mark.parametrize("step_hz", [4.0, 5.0])
def test_a_stepped_follow_holds_between_steps(tmp_path, step_hz):
    """On a stepped shot the target holds between steps, and so does the
    camera: it is step-eased, so a step is a cut, not a one-frame ramp."""
    mall, kw = _dot_mall(tmp_path), dict(fps=FPS, width=W, height=H, strict_assets=True)
    doc = compile_shot(_follow(), mall=mall, step_hz=step_hz, **kw)
    fine = [i / 240 for i in range(int(DURATION * 240) + 1)]
    assert _drift(doc, fine) < 1e-6
    keys = _camera_keys(doc)["pivot_x"]
    assert {e for *_, e in keys[:-1]} == {"step"}
    # keyed at every frame and every step instant
    times = [t for t, *_ in keys]
    assert set(frame_times(DURATION, fps=FPS)) <= set(times)
    # lagging, with a shutter too: still step-eased, and at every frame and
    # step instant exactly the lagging follow compiled without the shutter,
    # which is the lag filter run over the unlagged stepped follow there
    from an.ir.frames import lag_filter

    lagged = _camera_keys(
        compile_shot(
            _follow(lag=0.3), mall=mall, step_hz=step_hz, frame_samples=SHUTTER, **kw
        )
    )["pivot_x"]
    assert {e for *_, e in lagged[:-1]} == {"step"}
    plain = _camera_keys(
        compile_shot(_follow(lag=0.3), mall=mall, step_hz=step_hz, **kw)
    )
    base = list(camera_grid(DURATION, fps=FPS, step_hz=step_hz).base)
    assert [t for t, *_ in plain["pivot_x"]] == base
    assert [k for k in lagged if k[0] in set(base)] == plain["pivot_x"]
    unlagged = dict((t, v) for t, v, _ in keys)
    on_frames = base == frame_times(DURATION, fps=FPS)
    dt = 1.0 / FPS if on_frames else [b - a for a, b in zip(base, base[1:])]
    want = lag_filter([unlagged[t] for t in base], lag=0.3, dt=dt)
    assert [v for _, v, _ in plain["pivot_x"]] == pytest.approx(want, abs=1e-9)


# --- a dolly ----------------------------------------------------------------------

DEPTHS = {"far": 0.25, "near": 2.0}
OFFSET = 40.0


def _plane_mall(tmp_path, depths=DEPTHS, *, size=(40.0, 40.0), offset=(OFFSET, 0.0)):
    from an.environments import EnvironmentDescriptor, Plane, PlaneArt
    from an.stores import build_project_mall

    mall = build_project_mall(tmp_path, ensure=True)
    mall["environments"]["depths"] = EnvironmentDescriptor(
        name="depths",
        planes=[
            Plane(
                name=n,
                art=PlaneArt(kind="fill", color="#336699"),
                depth=d,
                size=size,
                offset=offset,
            )
            for n, d in depths.items()
        ],
    ).model_dump(mode="json")
    return mall


def _dolly_shot(camera):
    return Shot(
        id="d", renderer="cutout", duration=DURATION, camera=camera,
        entities=[AssetRef(kind="environment", id="depths", store="environments", ref="depths")],
    )  # fmt: skip


#: A deep dolly (the near plane grows 5x) that rolls: its growth is far from
#: linear in its travel, so a key a frame interpolates pixels off between them.
ROLLING_DOLLY = Camera(
    keys=[
        CameraKey(at=0.0),
        CameraKey(at=DURATION, dolly=0.4, rotation=1.0, easing="ease_in"),
    ]
)


def test_a_rolling_dolly_is_exact_at_a_shutters_sub_frame_samples(tmp_path):
    """The reference is the same camera at a frame rate whose whole frames ARE
    the sample instants: exact by construction. Keyed at 12 fps the samples
    sat between two frames' keys, pixels off; keyed at them, they are not."""
    mall = _plane_mall(tmp_path)
    per_frame = 10
    fine_fps = FPS * per_frame
    samples = [
        [(per_frame * i + j) / fine_fps for j in range(per_frame)]
        for i in range(int(DURATION * FPS))
    ]
    instants = [t for frame in samples for t in frame]
    reference = compile_shot(
        _dolly_shot(ROLLING_DOLLY), mall=mall, fps=fine_fps, width=W, height=H
    )
    plain = compile_shot(
        _dolly_shot(ROLLING_DOLLY), mall=mall, fps=FPS, width=W, height=H
    )
    sampled = compile_shot(
        _dolly_shot(ROLLING_DOLLY),
        mall=mall,
        fps=FPS,
        width=W,
        height=H,
        frame_samples=samples,
    )

    def error(doc):
        return max(
            math.dist(a, b)
            for plane in DEPTHS
            for u in (-W / 2, 0.0, W / 2)
            for a, b in zip(
                _screen(doc, f"depths/{plane}", instants, point=(u, 0.0)),
                _screen(reference, f"depths/{plane}", instants, point=(u, 0.0)),
            )
        )

    assert error(plain) > 1.0  # px
    assert error(sampled) < 1e-6


def test_an_authored_dolly_stays_on_ones_under_a_stepped_shot(tmp_path):
    """The compiler keeps every authored camera off the step grid (a stepped
    pan slides a stepped character in screen space): a dolly too."""
    mall = _plane_mall(tmp_path)
    shot = _dolly_shot(Camera(move="dolly_in"))
    plain = compile_shot(shot, mall=mall, fps=FPS, width=W, height=H)
    stepped = compile_shot(shot, mall=mall, fps=FPS, width=W, height=H, step_hz=4.0)
    assert _camera_keys(plain) == _camera_keys(stepped)
    assert {e for *_, e in _camera_keys(plain)["scale_x"]} == {"linear"}


# --- the seam ---------------------------------------------------------------------


def test_the_render_compiles_and_keys_with_its_frame_samples(tmp_path):
    """One seam (an#713): the stage engine and the shot cache both build
    `compile_shot`'s keywords from the `RenderContext`, frame samples included."""
    from an.adapters._base import RenderContext
    from an.stage.render import context_compile_args

    ctx = RenderContext(mall={}, work_dir=tmp_path, fps=FPS, frame_samples=SHUTTER)
    assert context_compile_args(Shot(id="s"), ctx)["frame_samples"] == SHUTTER
    assert (
        compile_args(Shot(id="s"), mall={}, fps=FPS, width=W, height=H)["frame_samples"]
        is None
    )


# --- validate ---------------------------------------------------------------------


def test_validate_samples_a_rolling_camera_between_its_keys(tmp_path):
    """A plate a hair bigger than the frame covers it unrolled and covers it
    rolled a quarter turn at 1.8x; half way through the roll (45 degrees at
    about 1.4x) the frame's corners pass the plate. Checked at its keys, the
    roll passed; sampled every frame, it warns."""
    from an.ir.validate import validate_semantic

    mall = _plane_mall(
        tmp_path, {"backdrop": 1.0}, size=(W + 2.0, H + 2.0), offset=(0.0, 0.0)
    )

    def uncovered(camera):
        scene = SceneIR(meta=Meta(), timeline=[_dolly_shot(camera)])
        scene.meta.resolution.width, scene.meta.resolution.height = W, H
        report = validate_semantic(scene, available_environments=mall["environments"])
        return [f for f in report.findings if "uncovered" in f.description]

    still = [CameraKey(at=0.0), CameraKey(at=DURATION, zoom=1.8)]
    assert uncovered(Camera(keys=still)) == []
    rolled = [CameraKey(at=0.0), CameraKey(at=DURATION, zoom=1.8, rotation=math.pi / 2)]
    found = uncovered(Camera(keys=rolled))
    assert found, "a rolling camera was checked at its keys only"
    import re

    # a sampled instant, named as one (not "the camera key"), with its roll
    m = re.search(
        r"the camera at ([0-9.e-]+)s \(frame (\d+): .* roll ([0-9.e-]+) rad\)",
        found[0].description,
    )
    assert m, found[0].description
    at, frame, roll = float(m.group(1)), int(m.group(2)), float(m.group(3))
    assert 0.0 < at < DURATION  # a frame between the keys
    assert frame == round(at * Meta().fps) and 0.0 < roll < math.pi / 2


def test_a_shutter_at_a_fractional_rate_is_counted_at_that_rate(tmp_path):
    """Re-review of an#626: the compiled grid rounds 29.97 fps to 30, but a
    29.97 camera's frame clock describes 29.97's frames; ``compile_args``
    passes the exact rate, so the follow compiles instead of refusing them."""
    from an.frame_clock import FrameClock

    duration = 20.0
    shot = _follow().model_copy(update={"duration": duration})
    samples = FrameClock(fps=29.97, exposure=0.5, samples=2).sample_times(duration)
    args = compile_args(shot, mall=_dot_mall(tmp_path), fps=29.97, width=320, height=240, frame_samples=samples)
    assert args["fps"] == 30 and args["sample_fps"] == pytest.approx(29.97)
    doc = compile_shot(shot, **args)
    assert doc is not None
    with pytest.raises(FrameClockError, match="another shot's samples"):
        compile_shot(shot, **{**args, "sample_fps": None})  # counted at 30: refused
