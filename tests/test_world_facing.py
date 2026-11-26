"""A world member's facing and the view hook (an#734, reeleehq/cutan#173)."""

from __future__ import annotations

import pytest

from an.genres.registry import EntityKind, register_entity_kind, unregister_owner
from an.ir.compose import tween
from an.ir.schema import Frame, Shot, Viewpoint, WorldMember
from an.ir.world import lower_world
from an.stage.world import member_views
from tests.test_world_frames import EXTENTS, _scene


def _lowered(scene, **kw):
    seen: dict[str, float] = {}

    def view_for(member, yaw):
        seen[member.id] = yaw
        return [tween(member.id, "rotation", to=yaw, duration=0.0, from_=yaw)]

    out = lower_world(scene, extents=EXTENTS, view_for=view_for, **kw)
    return out.scene.timeline[0], seen


def _facing(**by_id):
    scene = _scene(Shot(id="s", duration=1.0, viewpoint="road", actions=[]))
    for m in scene.world.members:
        m.at = (0.0, 0.4, 2.0)  # on the camera's axis, so the angle is the facing
        m.facing = by_id.get(m.id)
    return scene


def test_facing_the_camera_is_zero_and_away_is_behind():
    _, seen = _lowered(_facing(left=180.0, right=0.0))
    assert seen["left"] == pytest.approx(0.0, abs=1e-9)
    assert abs(seen["right"]) == pytest.approx(180.0)


def test_a_quarter_turn_is_signed_by_the_screen_side_it_faces():
    _, seen = _lowered(_facing(left=90.0, right=-90.0))
    assert seen["left"] == pytest.approx(90.0)  # +x: faces screen-right
    assert seen["right"] == pytest.approx(-90.0)


def test_no_facing_is_a_billboard_and_asks_nothing():
    shot, seen = _lowered(_facing())
    assert seen == {}
    assert shot.actions == []


def test_the_views_come_ahead_of_the_shots_own_actions():
    scene = _facing(left=180.0)
    own = tween("left", "rotation", to=1.0, duration=1.0, from_=0.0)
    scene.timeline[0].actions.append(own)
    shot, _ = _lowered(scene)
    assert shot.actions[-1] is own
    assert len(shot.actions) == 2


def test_a_member_in_a_turned_frame_is_turned_with_it():
    scene = _scene(
        Shot(id="s", duration=1.0, viewpoint="road", actions=[]),
        frames={"turn": Frame(at=(0.0, 0.0, 4.0), look=(180.0, 0.0, 0.0))},
    )
    left = scene.world.members[0]
    left.frame, left.at, left.facing = "turn", (0.0, 0.4, 2.0), 0.0
    _, seen = _lowered(scene)
    # The member stands at (0, .4, 2) of the world and looks along +z in its
    # frame, which is turned half a turn: in the world it looks at the camera.
    assert seen["left"] == pytest.approx(0.0, abs=1e-9)


def test_a_failing_hook_is_a_note_not_a_crash():
    def boom(member, yaw):
        raise RuntimeError("nope")

    out = lower_world(_facing(left=180.0), extents=EXTENTS, view_for=boom)
    assert any(n.kind == "view" and n.entity == "left" for n in out.notes)


def test_the_kinds_hook_is_reached_through_member_views():
    calls = []

    def hook(entity, mall, yaw):
        calls.append((entity.id, mall, yaw))
        return [tween(entity.id, "rotation", to=0.0, duration=0.0, from_=0.0)]

    register_entity_kind(
        EntityKind(name="facing_probe", view_for=hook),
        owner="test_facing",
        replace=True,
    )
    try:
        member = WorldMember(
            kind="facing_probe",
            id="p",
            store="s",
            ref="p",
            at=(0, 0, 1),
            height=1,
            facing=180,
        )
        assert member_views({"k": {}})(member, 12.0) is not None
        assert calls == [("p", {"k": {}}, 12.0)]
    finally:
        unregister_owner("test_facing")


def test_the_facing_round_trips_and_defaults_to_none():
    m = WorldMember(kind="prop", id="p", store="s", ref="p", at=(0, 0, 1), height=1)
    assert m.facing is None
    assert "facing" not in m.model_dump()  # a billboard lowers byte-identically
    assert WorldMember.model_validate(m.model_dump()).facing is None
    assert WorldMember.model_validate({**m.model_dump(), "facing": 45}).facing == 45


def test_a_reframed_member_keeps_the_facing_of_the_frame_it_starts_in():
    from an.ir.compose import sequence, delay
    from an.ir.reframe import reframe

    scene = _scene(
        Shot(id="s", duration=1.0, viewpoint="road", actions=[]),
        frames={"turn": Frame(at=(0.0, 0.0, 4.0), look=(180.0, 0.0, 0.0))},
    )
    left = scene.world.members[0]
    left.frame, left.at, left.facing = "turn", (0.0, 0.4, 2.0), 0.0
    scene.timeline[0].actions.append(sequence(delay(0.5), reframe("left", to="world")))
    _, seen = _lowered(scene)
    assert seen["left"] == pytest.approx(0.0, abs=1e-9)


def test_lowering_twice_gives_each_view_once():
    scene = _facing(left=180.0)
    once, _ = _lowered(scene)
    scene.timeline[0] = once
    twice, _ = _lowered(scene)
    assert len(twice.actions) == len(once.actions) == 1


def test_a_hook_that_gives_junk_is_a_note():
    for junk in ("front", [("set", 1)]):
        out = lower_world(
            _facing(left=180.0), extents=EXTENTS, view_for=lambda m, y, j=junk: j
        )
        shot = out.scene.timeline[0]
        assert shot.actions == []
        assert any(n.kind == "view" for n in out.notes)


def test_a_camera_straight_above_gives_no_view():
    scene = _facing(left=180.0)
    scene.world.viewpoints["road"] = Viewpoint(at=(0.0, -1.0, 2.0), focal=300.0)
    out, seen = _lowered(scene)
    assert seen == {}
