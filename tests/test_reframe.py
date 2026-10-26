"""`reframe` and ballistic motion (an#502, ADR 0008 decision 5): a member
changes frame at an instant, keeping its place in the world, inheriting the old
frame's velocity, and flying free under gravity; plus the two lints."""

from __future__ import annotations

import json

import pytest

from an.ir.compose import sequence, delay, tween
from an.ir.frames import FrameTree
from an.ir.reframe import DFLT_WORLD_GRAVITY, reframe
from an.ir.schema import (
    AssetRef,
    Frame,
    FrameMoving,
    StagePlacement,
    Shot,
    Viewpoint,
    WorldMember,
)
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.world import WorldError, _Course, lower_world, resolve_viewpoint
from tests.test_world_frames import (
    BOX,
    EXTENTS,
    GOLDEN,
    H,
    W,
    _channel,
    _legacy_scenes,
    _dump,
    _lamp,
    _lowered,
    _scene,
    mall,  # noqa: F401  (fixture)
    _screen_at,
)

EXT = {**EXTENTS, "bottle": BOX}
CAR_SPEED = 20.0
SEAT = (0.6, -0.3, 0.5)
THROW = (3.0, -2.0, 0.0)  # sideways 3 m/s, up 2 m/s (y is down)
OUT_AT = 2.0


def _car_scene(*actions, shot_len=3.0, **reframe_kw):
    """A bottle in a car doing 20 m/s, thrown out at t = 2 s; the camera rides
    three metres behind the car's origin."""
    scene = _scene(
        Shot(id="s", duration=shot_len, viewpoint="behind", actions=list(actions)),
        frames={"car": Frame(moving=FrameMoving(speed=CAR_SPEED))},
    )
    scene.world.members = [_lamp("bottle", at=SEAT, height=0.3, frame="car")]
    scene.world.viewpoints["behind"] = Viewpoint(
        at=(0.0, -1.0, -3.0), frame="car", focal=300.0
    )
    return scene


def _throw(**kw):
    return reframe(
        "bottle", to="world", at=OUT_AT, motion="ballistic", velocity=THROW, **kw
    )


def _bottle_course(**kw):
    tree = FrameTree({"car": Frame(moving=FrameMoving(speed=CAR_SPEED))})
    member = WorldMember(
        kind="prop", id="bottle", store="props", ref="b", at=SEAT, height=0.3, frame="car"
    )
    return tree, _Course(member, "car", tree, [(OUT_AT, _throw(**kw))], {}, film_start=0.0)


def _relative_to_car(tree, course, t):
    return tree.world_pose("car", t).unapply(course.world_at(t))


def test_the_bottle_is_still_abreast_of_the_car_half_a_second_later():
    tree, course = _bottle_course()
    rel = _relative_to_car(tree, course, OUT_AT + 0.5)
    assert rel[2] == pytest.approx(0.5)  # abreast
    assert rel[0] == pytest.approx(0.6 + 3.0 * 0.5)
    g = DFLT_WORLD_GRAVITY
    assert rel[1] == pytest.approx(-0.3 - 2.0 * 0.5 + 0.5 * g * 0.25)  # y is down: dropping
    assert course.world_at(OUT_AT)[2] == pytest.approx(40.5)


def test_without_inheriting_it_is_left_behind_in_the_world():
    tree, course = _bottle_course(inherit="none")
    assert _relative_to_car(tree, course, OUT_AT + 0.5)[2] == pytest.approx(-9.5)


def test_keep_world_does_not_jump_and_keep_local_does():
    tree = FrameTree({"car": Frame(moving=FrameMoving(speed=CAR_SPEED))})
    member = WorldMember(
        kind="prop", id="bottle", store="props", ref="b", at=SEAT, height=0.3, frame="car"
    )

    def jump(keep):
        c = _Course(member, "car", tree, [(OUT_AT, reframe("bottle", to="world", at=0, keep=keep))], {}, film_start=0.0)
        ch = c.changes[0]
        return sum((a - b) ** 2 for a, b in zip(ch.before, ch.after)) ** 0.5

    assert jump("world") == pytest.approx(0.0, abs=1e-9)
    assert jump("local") == pytest.approx(40.0)  # the car had gone 40 m


def test_snap_puts_the_member_at_a_socket_of_the_new_frame():
    tree = FrameTree({"hand": Frame(at=(5.0, 0.0, 5.0), sockets={"palm": (0.0, -0.1, 0.0)})})
    member = WorldMember(kind="prop", id="cup", store="props", ref="c", at=(0, 0, 1), height=0.1)
    c = _Course(member, "world", tree, [(1.0, reframe("cup", to="hand", snap="palm"))], {}, film_start=0.0)
    assert c.world_at(0.5) == pytest.approx((0, 0, 1))
    assert c.world_at(1.5) == pytest.approx((5.0, -0.1, 5.0))
    with pytest.raises(WorldError, match="no socket 'nope'"):
        _Course(member, "world", tree, [(1.0, reframe("cup", to="hand", snap="nope"))], {}, film_start=0.0)


def test_own_motion_after_the_reframe_is_in_the_new_frames_units():
    tree = FrameTree({"belt": Frame(moving=FrameMoving(speed=1.0, direction=(1.0, 0.0, 0.0)))})
    member = WorldMember(kind="prop", id="box", store="props", ref="b", at=(0, 0, 3), height=0.1)
    from an.ir.world import _split_frame_actions

    shot = Shot(id="s", duration=4.0, actions=[sequence(delay(1.0), reframe("box", to="belt"), tween("box", "at_z", to=5.0, duration=2.0, from_=3.0, easing="linear"))])
    split = _split_frame_actions(shot, default_easing=None, frames=tree.frames, members=["box"])
    c = _Course(member, "world", tree, split.reframes["box"], split.member_tracks.get("box", {}), film_start=0.0)
    # on the belt (which drifts +x at 1 m/s) from t = 1, walking from z 3 to 5
    assert c.world_at(1.0) == pytest.approx((0, 0, 3))
    assert c.world_at(2.0) == pytest.approx((1.0, 0, 4.0))  # drifted 2 m, held its place from 1
    assert c.world_at(4.0) == pytest.approx((3.0, 0, 5.0))


def test_a_thrown_bottle_lowers_to_the_pinhole_view_of_its_path(mall):  # noqa: F811
    scene = _car_scene(_throw())
    shot = lower_world(scene, extents=EXT).scene.timeline[0]
    assert all(getattr(a, "kind", "") != "reframe" for a in shot.actions)
    tree, course = _bottle_course()
    eye = resolve_viewpoint(scene.world, "behind", extents=EXT, width=W, height=H)
    seen = 0
    for t in (0.5, 1.0, 1.5, 2.0, 2.25, 2.5):
        x, y, z = _relative_to_car(tree, course, t)
        sx, sy = eye.project((x, y, z))[:2]
        if abs(sx) > W / 2 or abs(sy) > H / 2:
            continue
        assert _screen_at(shot, "bottle", t, mall) == pytest.approx((sx, sy), abs=2.5)
        seen += 1
    assert seen >= 4


def test_reframe_out_of_a_moving_frame_without_inherit_is_an_info_lint():
    notes = lower_world(_car_scene(_throw()), extents=EXT).notes
    infos = [n for n in notes if n.kind == "reframe_inherit"]
    assert len(infos) == 1 and infos[0].severity == "info"
    assert "inherit: velocity" in infos[0].message
    said = lower_world(_car_scene(_throw(inherit="velocity")), extents=EXT).notes
    assert not [n for n in said if n.kind == "reframe_inherit"]


def test_keep_local_that_jumps_the_picture_is_a_warning_with_the_pixels():
    scene = _car_scene(
        reframe("bottle", to="world", at=2.0, keep="local", inherit="velocity")
    )
    notes = lower_world(scene, extents=EXT).notes
    warned = [n for n in notes if n.kind == "reframe_jump"]
    assert len(warned) == 1 and warned[0].severity == "warning"
    assert " px" in warned[0].message and "keep: world" in warned[0].message
    held = _car_scene(reframe("bottle", to="world", at=2.0, inherit="velocity"))
    assert not [n for n in lower_world(held, extents=EXT).notes if n.kind == "reframe_jump"]


def test_a_reframe_of_something_that_is_not_a_member_or_to_a_non_frame_is_refused():
    with pytest.raises(WorldError, match="not a positioned member"):
        lower_world(_car_scene(reframe("nobody", to="world")), extents=EXT)
    with pytest.raises(WorldError, match="`to: boat` is not a frame"):
        lower_world(_car_scene(reframe("bottle", to="boat")), extents=EXT)


def test_the_action_round_trips_through_scene_md_without_its_defaults():
    scene = _car_scene(_throw(inherit="none"))
    md = ir_to_markdown(scene)
    assert "keep:" not in md and "gravity" not in md and "inherit: none" in md
    back = markdown_to_ir(md)
    a = back.timeline[0].actions[0]
    assert (a.kind, a.motion, a.inherit, tuple(a.velocity)) == ("reframe", "ballistic", "none", THROW)


def test_a_scene_with_no_reframe_lowers_byte_identically():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert {n: _dump(s) for n, s in _legacy_scenes().items()} == golden
