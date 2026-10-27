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
    want = -math.atan(20.0 / DFLT_WORLD_GRAVITY)  # radians: the runtime's unit  # leans forward: top toward the camera's left
    assert _rotation_at(shot, "right", 0.5) == pytest.approx(want, abs=0.02)
    assert _rotation_at(shot, "right", 1.8) == pytest.approx(0.0, abs=0.005)  # stopped: upright


def test_gain_scales_the_lean_and_no_sway_means_no_lean():
    half = lower_world(_braking(FrameSway(gain=0.5)), extents=EXTENTS).scene.timeline[0]
    full = math.atan(20.0 / DFLT_WORLD_GRAVITY)
    assert _rotation_at(half, "right", 0.5) == pytest.approx(-0.5 * full, abs=0.02)
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
    assert abs(_rotation_at(quick, "right", 1.3)) < 0.01
    assert abs(_rotation_at(slow, "right", 1.3)) > 0.2
    assert _rotation_at(slow, "right", 0.0) == pytest.approx(_rotation_at(quick, "right", 0.0))


def test_a_frame_without_sway_dumps_as_it_did():
    assert "sway" not in Frame().model_dump()
    assert Frame(sway=FrameSway(gain=2.0)).model_dump()["sway"]["gain"] == 2.0


def test_a_stop_with_no_easing_is_capped_not_a_flip():
    scene = _braking(FrameSway())
    scene.timeline[0].actions[-1] = tween("car", "at_z", to=10.0, duration=1.0, from_=0.0, easing="linear")
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    cap = math.radians(FrameSway().limit)
    for t in (0.0, 0.5, 0.99, 1.0, 1.04, 1.5):
        assert abs(_rotation_at(shot, "right", t)) <= cap + 1e-9


def test_a_member_that_reframes_out_stops_leaning_and_an_attached_one_is_told():
    from an.ir.reframe import reframe
    from an.ir.schema import Attachment

    scene = _braking(FrameSway())
    scene.timeline[0].actions.append(reframe("right", to="world", at=0.2))
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    assert abs(_rotation_at(shot, "right", 0.5)) < 0.01
    scene = _braking(FrameSway())
    scene.world.members.append(_lamp("hat", attached=Attachment(to="right")))
    notes = lower_world(scene, extents={**EXTENTS}).notes
    assert [n.entity for n in notes if n.kind == "sway_attached"] == ["hat"]


def test_gravity_is_the_frames_to_set():
    a = lower_world(_braking(FrameSway()), extents=EXTENTS).scene.timeline[0]
    b = lower_world(_braking(FrameSway(gravity=19.62)), extents=EXTENTS).scene.timeline[0]
    assert abs(_rotation_at(b, "right", 0.5)) < abs(_rotation_at(a, "right", 0.5))


# --- review fixes (an#504 PR) ---------------------------------------------------


def _lean_of_braking(*, gain=1.0, gravity=DFLT_WORLD_GRAVITY):
    return -gain * math.atan(20.0 / gravity)


def test_a_member_in_a_braking_sub_frame_of_a_swaying_car_leans():
    """The car is at rest and declares the sway; the cart in it brakes: the
    member in the cart leans with the cart's acceleration, by the car's sway."""
    scene = _braking(FrameSway())
    scene.world.frames["cart"] = Frame(parent="car")
    scene.world.members[1].frame = "cart"
    scene.timeline[0].actions[-1] = tween(
        "cart", "at_z", to=10.0, duration=1.0, from_=0.0, easing="ease_out"
    )
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    assert _rotation_at(shot, "right", 0.5) == pytest.approx(_lean_of_braking(), abs=0.02)


def test_the_lean_at_the_shots_first_instant_is_not_read_as_an_impulse():
    """The stencil stays inside the shot: braking that starts with the shot
    reads its real deceleration at t=0, not the cap of a jump from rest."""
    shot = lower_world(_braking(FrameSway()), extents=EXTENTS).scene.timeline[0]
    assert _rotation_at(shot, "right", 0.0) == pytest.approx(_lean_of_braking(), abs=0.02)


@pytest.mark.parametrize("duration", [0.01, 0.03])
def test_a_very_short_braking_shot_leans_the_right_way(duration):
    scene = _braking(FrameSway())
    scene.timeline[0].duration = duration
    scene.timeline[0].actions[-1] = tween(
        "car", "at_z", to=0.05, duration=duration, from_=0.0, easing="ease_out"
    )
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    lean = _rotation_at(shot, "right", duration / 2)
    assert lean is not None and lean < 0  # forward, as the long braking leans
    assert lean >= -math.radians(FrameSway().limit) - 1e-9


def test_a_member_that_reframes_into_a_swaying_frame_starts_leaning():
    from an.ir.reframe import reframe

    scene = _braking(FrameSway())
    scene.world.members[1].frame = None
    scene.timeline[0].actions.append(reframe("right", to="car", at=0.5))
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    assert abs(_rotation_at(shot, "right", 0.25)) < 0.01
    assert _rotation_at(shot, "right", 0.75) == pytest.approx(_lean_of_braking(), abs=0.02)


def test_a_member_that_goes_out_and_back_resumes_leaning():
    from an.ir.reframe import reframe

    scene = _braking(FrameSway())
    scene.timeline[0].actions += [
        reframe("right", to="world", at=0.2),
        reframe("right", to="car", at=0.5),
    ]
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    assert _rotation_at(shot, "right", 0.1) == pytest.approx(_lean_of_braking(), abs=0.02)
    assert abs(_rotation_at(shot, "right", 0.35)) < 0.01
    assert _rotation_at(shot, "right", 0.75) == pytest.approx(_lean_of_braking(), abs=0.02)


def test_members_riding_together_cost_one_lean(monkeypatch):
    import an.ir.world as world

    calls = {"lean": 0, "fit": 0}
    lean, fit = world._sway_lean, world._fit_lean

    def counted_lean(*a, **k):
        calls["lean"] += 1
        return lean(*a, **k)

    def counted_fit(*a, **k):
        calls["fit"] += 1
        return fit(*a, **k)

    monkeypatch.setattr(world, "_sway_lean", counted_lean)
    monkeypatch.setattr(world, "_fit_lean", counted_fit)
    scene = _braking(FrameSway())
    scene.world.members[0].frame = "car"  # both lamps ride the car
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    assert _rotation_at(shot, "left", 0.5) == _rotation_at(shot, "right", 0.5)
    assert calls == {"lean": 1, "fit": 1}


def test_sway_attached_is_said_only_of_a_member_in_the_shot():
    from an.ir.schema import Attachment

    scene = _braking(FrameSway())
    scene.world.members.append(_lamp("hat", attached=Attachment(to="right")))
    scene.world.viewpoints["side"].hide = ["hat"]
    notes = lower_world(scene, extents=EXTENTS).notes
    assert not [n for n in notes if n.kind == "sway_attached"]


def test_the_lean_is_gain_times_atan_of_a_over_gravity():
    sway = FrameSway(gain=0.5, gravity=2 * DFLT_WORLD_GRAVITY)
    shot = lower_world(_braking(sway), extents=EXTENTS).scene.timeline[0]
    want = _lean_of_braking(gain=sway.gain, gravity=sway.gravity)
    for t in (0.25, 0.5, 0.75):
        assert _rotation_at(shot, "right", t) == pytest.approx(want, abs=0.005)


def test_animating_the_rotation_of_a_swaying_member_warns():
    scene = _braking(FrameSway())
    scene.timeline[0].actions.append(tween("right", "rotation", to=0.3, duration=1.0))
    notes = lower_world(scene, extents=EXTENTS).notes
    assert [n.entity for n in notes if n.kind == "sway_rotation"] == ["right"]


@pytest.mark.parametrize("how", ["held_by", "place", "grasp_point", "swap_give"])
def test_a_swaying_item_the_holds_solver_rotates_warns(how):
    """an#590: the holds solver sets the rotation of an item it holds, grasps
    (at a point of it too) or places, replacing the lean: said as for an
    explicit rotation."""
    from an.ir.holds import GraspAction, PlaceAction, SwapAction

    scene = _braking(FrameSway())
    shot = scene.timeline[0]
    if how == "held_by":
        from an.ir.schema import AssetRef

        shot.entities.append(
            AssetRef(kind="prop", id="right", store="props", ref="lamp",
                     overrides={"held_by": "ground"})
        )
    elif how == "place":
        shot.actions.append(PlaceAction(item="right", onto="ground", by="left@hand_r", at=0.2))
    elif how == "grasp_point":
        shot.actions.append(GraspAction(item="right@handle", by="left@hand_r", at=0.2))
    else:
        shot.actions.append(
            SwapAction(holder="left@hand_l", take="hat", give="right", by="left@hand_r", at=0.2)
        )
    notes = lower_world(scene, extents=EXTENTS).notes
    said = [n for n in notes if n.kind == "sway_rotation"]
    assert [n.entity for n in said] == ["right"] and "holds solver" in said[0].message


def test_a_swaying_member_nothing_rotates_is_not_warned():
    """The warning is about a second writer of `rotation`: none, no warning."""
    notes = lower_world(_braking(FrameSway()), extents=EXTENTS).notes
    assert not [n for n in notes if n.kind == "sway_rotation"]


def test_a_sway_dumps_only_what_differs_from_its_defaults_and_round_trips():
    assert FrameSway().model_dump() == {}
    assert FrameSway(gain=2.0, limit=30.0).model_dump() == {"gain": 2.0, "limit": 30.0}
    frame = Frame(sway=FrameSway(settle=0.2))
    assert Frame.model_validate(frame.model_dump()) == frame
    assert Frame.model_validate(Frame(sway=FrameSway()).model_dump()).sway == FrameSway()


def test_lag_filter_refuses_a_step_that_is_not_positive():
    with pytest.raises(ValueError, match="dt"):
        lag_filter([0.0, 1.0], lag=0.3, dt=0.0)


def test_a_set_that_jumps_the_frame_is_a_cut_not_an_impulse():
    """an#580: a position step read as an acceleration twitched the riders to the cap."""
    from an.ir.compose import delay, sequence, set_

    scene = _braking(FrameSway())
    scene.timeline[0].actions[-1] = sequence(delay(1.0), set_("car", "at_z", 5.0))
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    for t in (0.9, 0.97, 1.0, 1.02, 1.1):
        assert abs(_rotation_at(shot, "right", t) or 0.0) < 0.01, t


def test_the_stencil_slides_off_a_jump_and_is_zero_where_it_cannot():
    tree = FrameTree(
        {"car": Frame()},
        tracks={"car": {"at_z": Track([TrackEvent(1.0, 1.0, to=5.0)])}},
    )
    assert tree.jump_times("car") == [1.0]
    for t in (0.99, 1.0, 1.01):
        assert tree.acceleration("car", t, dt=0.04) == (0.0, 0.0, 0.0)
    # No room on either side inside the window: zero, not the step's impulse.
    assert tree.acceleration("car", 1.0, dt=0.5, within=(0.9, 1.1)) == (0.0, 0.0, 0.0)


def test_leaving_a_swaying_frame_settles_as_the_frame_did():
    from an.ir.reframe import reframe

    scene = _braking(FrameSway(settle=0.4))
    scene.timeline[0].actions.append(reframe("right", to="world", at=0.5))
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    before = _rotation_at(shot, "right", 0.5)
    assert abs(before) > 0.1
    assert abs(_rotation_at(shot, "right", 0.55)) > 0.5 * abs(before)  # not upright at once
    assert abs(_rotation_at(shot, "right", 1.5)) < 0.1 * abs(before)  # but gone in time


def test_the_max_actions_refusal_names_the_sway_leans_it_counted():
    from an.ir.schema import Travel
    from an.ir.world import WorldError

    scene = _braking(FrameSway())
    scene.world.travel = Travel(speed=1.0, max_actions=1)
    with pytest.raises(WorldError, match="sway leans"):
        lower_world(scene, extents=EXTENTS)


def test_a_tween_from_an_explicit_value_is_a_step_too():
    tree = FrameTree(
        {"car": Frame()},
        tracks={"car": {"at_z": Track([TrackEvent(1.0, 3.0, to=10.0, from_=5.0)])}},
    )
    assert tree.jump_times("car") == [1.0]
    assert tree.acceleration("car", 1.0, dt=0.04) == pytest.approx((0.0, 0.0, 0.0), abs=1.0)


def test_a_jump_in_the_first_instants_still_leaves_the_far_side_to_read():
    """The stencil slides to the other side when one side leaves the shot."""
    tree = FrameTree(
        {"car": Frame()},
        tracks={"car": {"at_z": Track([TrackEvent(0.05, 0.15, to=1.0, from_=0.0)])}},
    )
    # from_=0.0 makes 0.05 a step; the ramp after it is real motion on the right side
    a = tree.acceleration("car", 0.0, dt=1 / 24, within=(0.0, 1.0))
    assert a == tree.acceleration("car", 0.05 + 1 / 24, dt=1 / 24, within=(0.0, 1.0))
