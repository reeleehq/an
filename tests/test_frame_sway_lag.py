"""Lagged follow camera and the sway of an accelerating frame (an#504)."""

from __future__ import annotations

import math

import pytest

from an.ir.compose import flatten, parallel
from an.ir.frames import FrameTree, Track, TrackEvent, lag_filter
from an.ir.reframe import DFLT_WORLD_GRAVITY
from an.ir.schema import CameraFollow, Frame, FrameMoving, FrameSway, Shot, Viewpoint
from an.ir.compose import tween
from an.ir.world import lower_world
from an.timing.easing import apply_easing
from tests.test_world_frames import EXTENTS, _lamp, _scene


def test_lag_zero_is_the_follow_camera_it_was():
    assert CameraFollow(target="bob").model_dump() == {"target": "bob", "axes": "x"}
    assert CameraFollow(target="bob", lag=0.3).model_dump()["lag"] == 0.3
    xs = [0.0, 10.0, 20.0]
    assert lag_filter(xs, lag=0.0, dt=0.1) == xs


def test_a_step_is_followed_with_the_time_constant():
    dt, lag = 1 / 24, 0.3
    step = [0.0] + [100.0] * 48
    out = lag_filter(step, lag=lag, dt=dt)
    n = round(lag / dt)  # one time constant on
    assert out[n] == pytest.approx(100 * (1 - math.exp(-n * dt / lag)), rel=1e-6)
    assert out[n] == pytest.approx(63.2, abs=2.0)
    assert out[-1] > 99.0


def _braking(sway):
    scene = _scene(
        Shot(id="s", duration=2.0, viewpoint="side", actions=[]),
        frames={"car": Frame(sway=sway)},
    )
    scene.world.viewpoints["side"] = Viewpoint(at=(-8.0, -1.0, 5.0), look=(90.0, 0.0, 0.0), focal=300.0)
    scene.world.members[1].frame = "car"
    # brake from 20 m/s to 0 over the first second: 10 m, ease-out
    scene.timeline[0].actions.append(
        tween("car", "at_z", to=10.0, duration=1.0, from_=0.0, easing="ease_out")
    )
    return scene


def _rotation_at(shot, entity, t):
    """The rotation channel at ``t``: sets step, tweens ramp, and a value holds."""
    segs = []
    for f in flatten(parallel(*shot.actions)):
        a = f.action
        if getattr(a, "target", None) != entity or getattr(a, "property", "") != "rotation":
            continue
        if a.kind == "set":
            segs.append((f.start, f.start, a.value, a.value, None))
        elif a.kind == "tween":
            segs.append((f.start, f.end, a.from_value, a.to_value, a.easing))
    held = None
    for s, e, a, b, easing in sorted(segs, key=lambda x: (x[0], x[1])):
        if s > t:
            break
        held = b if t >= e else a + (b - a) * apply_easing(easing, (t - s) / (e - s))
    return held


def test_braking_with_sway_leans_the_members_by_atan_a_over_g():
    scene = _braking(FrameSway())
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    want = -math.degrees(math.atan(20.0 / DFLT_WORLD_GRAVITY))  # leans forward: top toward the camera's left
    assert _rotation_at(shot, "right", 0.5) == pytest.approx(want, abs=1.0)
    assert _rotation_at(shot, "right", 1.8) == pytest.approx(0.0, abs=0.2)  # stopped: upright


def test_gain_scales_the_lean_and_no_sway_means_no_lean():
    half = lower_world(_braking(FrameSway(gain=0.5)), extents=EXTENTS).scene.timeline[0]
    full = math.degrees(math.atan(20.0 / DFLT_WORLD_GRAVITY))
    assert _rotation_at(half, "right", 0.5) == pytest.approx(-0.5 * full, abs=1.0)
    off = lower_world(_braking(None), extents=EXTENTS).scene.timeline[0]
    assert _rotation_at(off, "right", 0.5) is None


def test_constant_speed_is_no_lean():
    scene = _scene(
        Shot(id="s", duration=2.0, viewpoint="side"),
        frames={"car": Frame(moving=FrameMoving(speed=20.0), sway=FrameSway())},
    )
    scene.world.viewpoints["side"] = Viewpoint(at=(-8.0, -1.0, 5.0), look=(90.0, 0.0, 0.0), focal=300.0)
    scene.world.members[1].frame = "car"
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    assert _rotation_at(shot, "right", 1.0) is None


def test_settle_lets_the_lean_die_away_instead_of_stopping_dead():
    quick = lower_world(_braking(FrameSway()), extents=EXTENTS).scene.timeline[0]
    slow = lower_world(_braking(FrameSway(settle=0.4)), extents=EXTENTS).scene.timeline[0]
    # braking ends at 1 s; the quick one is upright at once, the settled one rights itself over ~0.4 s
    assert abs(_rotation_at(quick, "right", 1.3)) < 0.5
    assert abs(_rotation_at(slow, "right", 1.3)) > 10.0
    assert _rotation_at(slow, "right", 0.0) == pytest.approx(_rotation_at(quick, "right", 0.0))


def test_a_frame_without_sway_dumps_as_it_did():
    assert "sway" not in Frame().model_dump()
    assert Frame(sway=FrameSway(gain=2.0)).model_dump()["sway"]["gain"] == 2.0
