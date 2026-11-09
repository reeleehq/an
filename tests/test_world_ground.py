"""``World.ground``: the scene-space floor the supports and skate measure against (an#519 PR 4).

A world that declares ``ground`` (the world ``y`` of a horizontal floor plane)
lowers it under each positioned member as the camera projects it at the
member's depth (``overrides.ground``, :data:`an.base.GROUND_OVERRIDE`): the
floor line, keyed when the camera sees the member move, and where the floor
point lies along the floor in the frame the member stands in, so ``skate``
measures a foot on the floor in the floor's own frame. Members are the
``walker`` of ``tests/test_skate.py`` (feet that are a limb's contacts) and
the fixture's ``crate``, sized by ``units_per_px`` so their world geometry is
exact. Compiled only, never rendered.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from tests._hold_fixture import CRATE_SURFACE, K
from tests.test_skate import _lint, _project, _shot, _tween

from an.base import GROUND_OVERRIDE
from an.ir.schema import (
    AssetRef,
    Frame,
    FrameMoving,
    Shot,
    Viewpoint,
    World,
    WorldMember,
)
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.world import world_ground_at
from an.stage.world import lower_scene, world_report

#: The floor plane's world ``y`` (down positive): a camera 1 unit above it.
G = 1.75
#: World units per native px of the members' art.
UPP = 0.01
#: The viewpoint: 1 unit above the floor, looking along ``z``, focal 300 px, so
#: a member 5 units away stands on the stage's ``y`` 60.
EYE = (0.0, G - 1.0, 0.0)
FOCAL = 300.0
#: One frame at the fixture's 24 fps.
FRAME = 1 / 24


def _member(mid: str, ref: str, at, frame: str | None = None) -> WorldMember:
    return WorldMember(
        kind="prop",
        id=mid,
        store="props",
        ref=ref,
        at=at,
        units_per_px=UPP,
        frame=frame,
    )


def _world(
    tmp_path: Path,
    members,
    *,
    joints: str = "",
    actions: str = "[]",
    ground: float | None = G,
    camera: str = "world",
    speed: float = 0.5,
):
    """The skate fixture's project, its one shot framed by a world of
    ``members`` on ``ground``, the viewpoint in ``camera`` (``world``, or
    ``dolly``/``car``: frames moving along ``x`` at ``speed``)."""
    project = _project(
        tmp_path,
        entities="- {kind: prop, id: wal, store: props, ref: walker}\n",
        shot=_shot(joints, ground=None),
        actions=actions,
    )
    moving = Frame(moving=FrameMoving(direction=(1.0, 0.0, 0.0), speed=speed))
    world = World(
        ground=ground,
        frames={"dolly": moving, "car": moving},
        members=list(members),
        viewpoints={"v": Viewpoint(at=EYE, focal=FOCAL, frame=camera)},
    )
    shot = project.scene.timeline[0].model_copy(update={"viewpoint": "v"})
    return project, project.scene.model_copy(
        update={"world": world, "timeline": [shot]}
    )


def _lowered(project, scene):
    return lower_scene(scene, project.mall)


def _entity(lowered, eid: str):
    return next(e for e in lowered.scene.timeline[0].entities if e.id == eid)


def _floor(entity, t: float = 0.0):
    return world_ground_at((entity.overrides or {}).get(GROUND_OVERRIDE), t)


def _checks(project, scene, *, gravity=None, only=("support", "skate")):
    return _lint(project, scene_ir=scene, gravity=gravity, only=only)


# --- the field ----------------------------------------------------------------


def test_world_ground_round_trips_and_is_omitted_when_unset():
    scene = markdown_to_ir(ir_to_markdown(_scene_with(ground=G)))
    assert scene.world.ground == G
    assert ir_to_markdown(scene) == ir_to_markdown(_scene_with(ground=G))
    assert "ground" not in _scene_with(ground=None).world.model_dump(mode="json")
    assert "ground:" not in ir_to_markdown(_scene_with(ground=None))


def _scene_with(*, ground):
    from an.ir.schema import SceneIR

    world = World(
        ground=ground,
        members=[_member("wal", "walker", (0.0, G, 5.0))],
        viewpoints={"v": Viewpoint(at=EYE, focal=FOCAL)},
    )
    return SceneIR(world=world, timeline=[Shot(id="a", duration=1.0, viewpoint="v")])


# --- the lowering ---------------------------------------------------------------


def test_members_on_the_floor_have_it_under_their_feet(tmp_path):
    # two members on the floor at different depths: each one's floor is the
    # floor plane projected at its depth, where its placement point (its feet) is
    project, scene = _world(
        tmp_path,
        [
            _member("wal", "walker", (-0.5, G, 5.0)),
            _member("box", "crate", (1.0, G, 8.0)),
        ],
    )
    lowered = _lowered(project, scene)
    for eid in ("wal", "box"):
        e = _entity(lowered, eid)
        floor = _floor(e)
        assert floor.at == pytest.approx(e.stage.at)
        assert floor.along == (1.0, 0.0)  # a camera that does not roll: level
    assert _floor(_entity(lowered, "wal")).at[1] == pytest.approx(60.0)
    assert _floor(_entity(lowered, "box")).scale == pytest.approx(FOCAL / 8.0)
    [row] = world_report(lowered)
    floors = {e["id"]: e.get("floor") for e in row["entities"]}
    assert floors["wal"] == pytest.approx(60.0) and floors["box"] == pytest.approx(37.5)


def test_a_world_without_ground_lowers_as_before(tmp_path):
    # the floor is the only thing `ground` adds to a lowering
    members = [
        _member("wal", "walker", (-0.5, G, 5.0)),
        _member("box", "crate", (1.0, G, 8.0)),
    ]
    actions = _tween("wal", "at_z", a=5, b=3, start=0, secs=2)
    project, plain = _world(tmp_path, members, actions=actions, ground=None)
    _, grounded = _world(tmp_path / "g", members, actions=actions)
    without = _lowered(project, plain).scene.timeline[0]
    assert all(GROUND_OVERRIDE not in (e.overrides or {}) for e in without.entities)
    floored = _lowered(project, grounded).scene.timeline[0]

    def dropped(shot):
        doc = shot.model_dump(mode="json")
        for e in doc["entities"]:
            if e.get("overrides"):
                e["overrides"].pop(GROUND_OVERRIDE, None)
                e["overrides"] = e["overrides"] or None
        return json.dumps(doc, sort_keys=True)

    assert dropped(floored) == json.dumps(
        without.model_dump(mode="json"), sort_keys=True
    )
    assert [world_report(_lowered(project, plain))[0]["entities"][0].get("floor")] == [
        None
    ]


# --- support ------------------------------------------------------------------


SUPPORT = "[{type: support, a: wal, b: ground}]"


def test_a_member_standing_on_the_world_floor_passes_support(tmp_path):
    project, scene = _world(
        tmp_path, [_member("wal", "walker", (0.3, G, 5.0))], joints=SUPPORT
    )
    assert _checks(project, scene) == []
    # nothing declared: it is taken to stand on the world's floor, and does
    project, scene = _world(tmp_path / "b", [_member("wal", "walker", (0.3, G, 5.0))])
    assert _checks(project, scene, gravity=True) == []


def test_a_member_above_the_world_floor_floats(tmp_path):
    # 0.2 units above the floor, 5 away: 12 px on the stage
    above = [_member("wal", "walker", (0.0, G - 0.2, 5.0))]
    project, scene = _world(tmp_path, above, joints=SUPPORT)
    [(severity, where, message)] = _checks(project, scene)
    assert (severity, where) == ("error", "timeline/0/joints/0")
    assert (
        "`wal` floats 12.0 px above `ground` (the world's floor under it, y 60.0)"
        in message
    )
    assert "its world `at` y onto `world.ground`" in message
    # nothing declared: beyond the support tolerance it is not taken to stand
    project, scene = _world(tmp_path / "b", above)
    assert _checks(project, scene, gravity=True) == []


def test_a_member_lifted_off_the_world_floor_at_rest_warns(tmp_path):
    # it stands on the floor as the shot opens, then rises and rests above it
    lift = _tween("wal", "at_y", a=G, b=G - 0.3, start=0.5, secs=0.5)
    project, scene = _world(
        tmp_path, [_member("wal", "walker", (0.0, G, 5.0))], actions=lift
    )
    [(severity, _where, message)] = _checks(project, scene, only=("support",))
    assert severity == "warning"
    assert message.startswith("`wal` stands on `ground` (the world's floor under it")


def test_a_member_walking_in_depth_neither_sinks_nor_skates(tmp_path):
    # walked straight toward the camera: its feet go down the stage, and so
    # does its floor; along the floor, in the world, it has not moved sideways
    walk = _tween("wal", "at_z", a=6, b=3, start=0, secs=2)
    members = [_member("wal", "walker", (0.3, G, 6.0))]
    project, scene = _world(tmp_path, members, joints=SUPPORT, actions=walk)
    lowered = _entity(_lowered(project, scene), "wal")
    ys = [_floor(lowered, t).at[1] for t in (0.0, 1.0, 2.0)]
    assert ys == pytest.approx(
        [FOCAL / z for z in (6.0, 4.5, 3.0)]
    )  # 1 unit below the eye
    assert _checks(project, scene) == []
    # without the world's floor, `ground` is where it stood as the shot opened
    project, scene = _world(
        tmp_path / "b", members, joints=SUPPORT, actions=walk, ground=None
    )
    assert any("px into `ground`" in m for _s, _w, m in _checks(project, scene))


# --- skate, in the floor's own frame ---------------------------------------------


def test_a_passenger_does_not_skate_on_what_carries_it(tmp_path):
    # a crate in a car passing the camera, and the walker on the crate's
    # surface: both cross the stage at 30 px/s, neither slides on what it is on
    top = G - CRATE_SURFACE * K * UPP
    riders = [
        _member("crate", "crate", (0.0, G, 5.0), "car"),
        _member("wal", "walker", (0.0, top, 5.0), "car"),
    ]
    on_crate = "[{type: support, a: wal, b: crate@surface}]"
    project, scene = _world(tmp_path, riders, joints=on_crate)
    lowered = _lowered(project, scene)
    assert _entity(lowered, "wal").stage.at[1] < _floor(_entity(lowered, "wal")).at[1]
    assert _checks(project, scene) == []
    # standing on the world's floor in the car: keyed, and measured in the car
    project, scene = _world(
        tmp_path / "b", [_member("wal", "walker", (0.0, G, 5.0), "car")], joints=SUPPORT
    )
    floor = (_entity(_lowered(project, scene), "wal").overrides or {})[GROUND_OVERRIDE]
    assert [k[1] for k in floor["keys"]] == pytest.approx([0.0, 60.0])
    assert {k[6] for k in floor["keys"]} == {0.0}
    assert _checks(project, scene) == []


def test_a_glide_the_camera_follows_skates_on_the_world_floor(tmp_path):
    # the walker glides 1 unit/s along x and the camera rides a dolly at the
    # same speed: it stands still on the stage, and its feet slide on the floor
    glide = _tween("wal", "at_x", a=0, b=2, start=0, secs=2)
    members = [_member("wal", "walker", (0.0, G, 5.0))]
    project, scene = _world(
        tmp_path, members, joints=SUPPORT, actions=glide, camera="dolly", speed=1.0
    )
    lowered = _entity(_lowered(project, scene), "wal")
    assert _floor(lowered, 2.0).at == pytest.approx(_floor(lowered, 0.0).at)
    findings = _checks(project, scene)
    assert findings and {f[0] for f in findings} == {"error"}
    assert all("(60 px/s) along `ground`" in m for _s, _w, m in findings)
    # without `ground` the stage floor does not follow it: not judged, said once
    project, scene = _world(
        tmp_path / "b",
        members,
        joints=SUPPORT,
        actions=glide,
        camera="dolly",
        speed=1.0,
        ground=None,
    )
    assert [f[0] for f in _checks(project, scene, only=("skate",))] == ["info"]


# --- the hold layer --------------------------------------------------------------


def test_the_hold_layers_floor_is_the_world_floor_under_the_carrier():
    from an.stage.hold import _world_floor_y

    floor = {
        "keys": [
            [0.0, 0.0, 60.0, 1.0, 0.0, 60.0, 0.0],
            [1.0, 0.0, 100.0, 1.0, 0.0, 30.0, 0.0],
        ]
    }
    shot = NS(
        entities=[
            AssetRef(
                kind="prop",
                id="wal",
                store="props",
                ref="walker",
                overrides={GROUND_OVERRIDE: floor},
            ),
            AssetRef(kind="prop", id="box", store="props", ref="crate"),
        ]
    )
    ctx = NS(shot=shot, times=[0.0, 0.5, 1.0])
    assert [_world_floor_y(ctx, "wal", k) for k in range(3)] == [60.0, 80.0, 100.0]
    assert _world_floor_y(ctx, "box", 0) is None
