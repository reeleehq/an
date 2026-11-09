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

from an.base import GROUND_OVERRIDE, STREAM_OVERRIDE
from an.ir.schema import (
    DFLT_TRAVEL_TOLERANCE_PX,
    AssetRef,
    Frame,
    FrameMoving,
    Shot,
    StagePlacement,
    Viewpoint,
    World,
    WorldMember,
)
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.world import lower_world, world_ground_at
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
    solve: float | None = None,
    look: tuple[float, float, float] = (0.0, 0.0, 0.0),
    entities: str = "- {kind: prop, id: wal, store: props, ref: walker}\n",
):
    """The skate fixture's project, its one shot framed by a world of
    ``members`` on ``ground``, the viewpoint in ``camera`` (``world``, or
    ``dolly``/``car``: frames moving along ``x`` at ``speed``) looking
    ``look``; ``solve``: the shot's own ``solve.ground``."""
    project = _project(
        tmp_path,
        entities=entities,
        shot=_shot(joints, ground=solve),
        actions=actions,
    )
    moving = Frame(moving=FrameMoving(direction=(1.0, 0.0, 0.0), speed=speed))
    world = World(
        ground=ground,
        frames={"dolly": moving, "car": moving},
        members=list(members),
        viewpoints={"v": Viewpoint(at=EYE, focal=FOCAL, frame=camera, look=look)},
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
    # 1 unit below the eye, keyed to the travel's tolerance as the member is
    assert ys == pytest.approx(
        [FOCAL / z for z in (6.0, 4.5, 3.0)], abs=DFLT_TRAVEL_TOLERANCE_PX
    )
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
        viewpoint="v",
        entities=[
            AssetRef(
                kind="prop",
                id="wal",
                store="props",
                ref="walker",
                overrides={GROUND_OVERRIDE: floor},
            ),
            AssetRef(kind="prop", id="box", store="props", ref="crate"),
        ],
    )
    ctx = NS(shot=shot, times=[0.0, 0.5, 1.0])
    assert [_world_floor_y(ctx, "wal", k) for k in range(3)] == [60.0, 80.0, 100.0]
    assert _world_floor_y(ctx, "box", 0) is None
    # read only on a shot lowered from a world (one with a viewpoint)
    unframed = NS(shot=NS(viewpoint=None, entities=shot.entities), times=ctx.times)
    assert _world_floor_y(unframed, "wal", 0) is None


def test_a_place_on_the_ground_lands_on_the_world_floor_under_the_carrier(tmp_path):
    # the hold fixture's figure grasps the stick and puts it down on `ground`;
    # the world's floor is 0.1 units under the figure's feet, so the stick
    # lands there, not where the figure stands
    import warnings

    from tests._hold_fixture import make_project, scene as hold_scene
    from tests.test_holds import INK_BOTTOM, _stage

    from an.ir import grasp, place
    from an.ir.compose import delay, sequence
    from an.ir.schema import Meta, Resolution, SceneIR
    from an.stage.compile import compile_shot

    project = make_project(tmp_path / "p", hold_scene(""))
    feet = 0.4
    members = [
        WorldMember(
            kind="prop", id="fig", store="props", ref="figure", at=(0.0, feet, 2.0),
            height=0.8,
        ),
        WorldMember(
            kind="prop", id="stick", store="props", ref="stick",
            at=(0.15, feet, 2.0), height=0.3,
        ),
    ]  # fmt: skip

    def landed(ground):
        world = World(
            ground=ground,
            members=members,
            viewpoints={"v": Viewpoint(at=(0.0, 0.0, 0.0), focal=300.0)},
        )
        shot = Shot(
            id="s",
            duration=2.0,
            viewpoint="v",
            actions=[
                grasp("fig/arm_r", "stick", reach=0.2, retract=0.1),
                sequence(delay(0.8), place("stick", "ground", reach=0.2)),
            ],
        )
        scene = SceneIR(
            meta=Meta(fps=24, resolution=Resolution(width=640, height=480)),
            world=world,
            timeline=[shot],
        )
        low = lower_scene(scene, project.mall).scene.timeline[0]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            doc = compile_shot(low, project.mall, fps=24, width=640, height=480)
        fig = next(e for e in low.entities if e.id == "fig")
        return _stage(doc, "stick", 1.9, point=INK_BOTTOM)[1], fig

    y, fig = landed(feet + 0.1)
    floor = _floor(fig).at[1]
    assert floor == pytest.approx(fig.stage.at[1] + 0.1 * 300.0 / 2.0)
    assert y == pytest.approx(floor, abs=1.0)
    # without the world's floor it lands where the figure stands
    y, fig = landed(None)
    assert y == pytest.approx(fig.stage.at[1], abs=1.0)


# --- which floor, and what reads it --------------------------------------------


def test_the_shots_solve_ground_wins_over_the_worlds(tmp_path):
    from an.stage.compile import compile_shot
    from an.stage.solve import node_index
    from an.stage.support import _Reader, supports_at

    members = [_member("wal", "walker", (0.3, G, 5.0))]
    project, scene = _world(tmp_path, members, joints=SUPPORT, solve=40.0)
    # its feet are on the world's floor (y 60), 20 px under the shot's
    [(severity, _where, message)] = _checks(project, scene, only=("support",))
    assert severity == "error" and "into `ground` (y 40)" in message
    assert "world's floor" not in message

    def reader_and_states(scene):
        shot = _lowered(project, scene).scene.timeline[0]
        doc = compile_shot(shot, project.mall, fps=24, width=640, height=480)
        reader = _Reader(doc, shot, project.mall, node_index(doc))
        return reader, supports_at(doc, shot, project.mall)[0]

    reader, states = reader_and_states(scene)
    assert not reader.on_world_floor("wal")
    assert states and not any(s.world_floor for s in states)
    _, scene = _world(tmp_path / "b", members, joints=SUPPORT)
    reader, states = reader_and_states(scene)
    assert reader.on_world_floor("wal")
    assert states and all(s.world_floor for s in states)


def test_environments_and_stream_slots_get_no_floor():
    from tests.test_world import EXTENTS, _travel_scene

    scene = _travel_scene(Shot(id="s1", duration=3.0, viewpoint="road"))
    scene.world.ground = 0.4
    scene.world.members.append(
        WorldMember(kind="environment", id="set", store="environments", ref="default")
    )
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    marked = {e.id for e in shot.entities if GROUND_OVERRIDE in (e.overrides or {})}
    slots = {e.id for e in shot.entities if STREAM_OVERRIDE in (e.overrides or {})}
    assert slots and "set" in {e.id for e in shot.entities}
    assert marked == {"left", "right"}


def test_lateral_is_the_walk_along_the_floor_in_the_members_frame(tmp_path):
    # a walk of 1 unit along x in the world, and the same walk in a car moving
    # 0.5 units/s: the lateral is the walk, not what the car adds
    walk = _tween("wal", "at_x", a=0, b=1, start=0, secs=2)
    for frame in (None, "car"):
        members = [_member("wal", "walker", (0.0, G, 5.0), frame)]
        project, scene = _world(tmp_path / str(frame), members, actions=walk)
        lowered = _entity(_lowered(project, scene), "wal")
        assert [_floor(lowered, t).lateral for t in (0.0, 1.0, 2.0)] == pytest.approx(
            [0.0, 0.5, 1.0], abs=1e-6
        )
    # a still member under a camera on a dolly: it does not move along the floor
    project, scene = _world(
        tmp_path / "d", [_member("wal", "walker", (0.0, G, 5.0))], camera="dolly"
    )
    floor = (_entity(_lowered(project, scene), "wal").overrides or {})[GROUND_OVERRIDE]
    assert {k[6] for k in floor["keys"]} == {0.0}
    assert floor["keys"][-1][1] == pytest.approx(-0.5 * 2.0 * FOCAL / 5.0)


# --- unseen, rolled, by hand ------------------------------------------------------


def test_an_unseen_member_is_not_measured(tmp_path):
    # still in a car moving 3 units/s: it leaves the frame, and is hidden
    # (alpha 0) while the floor's keys go on; nothing is measured then
    project, scene = _world(
        tmp_path,
        [_member("wal", "walker", (0.0, G, 5.0), "car")],
        joints=SUPPORT,
        speed=3.0,
    )
    assert _checks(project, scene) == []
    # walked toward the camera and past it: hidden from where it passes the
    # near plane, and keyed while it is seen
    walk = _tween("wal", "at_z", a=2, b=-2, start=0, secs=2)
    members = [_member("wal", "walker", (0.0, G, 2.0))]
    project, scene = _world(tmp_path / "b", members, joints=SUPPORT, actions=walk)
    keys = (_entity(_lowered(project, scene), "wal").overrides or {})[GROUND_OVERRIDE]
    assert keys["keys"][-1][0] < 1.0  # behind the camera from 0.75 s on
    assert _checks(project, scene) == []


def test_under_a_rolled_camera_the_floor_is_level_under_an_upright_member(tmp_path):
    # members do not roll with the camera: an upright figure stands on a
    # level line, not on the tilted horizon (its downhill foot would sink)
    members = [_member("wal", "walker", (0.3, G, 5.0))]
    project, scene = _world(tmp_path, members, joints=SUPPORT, look=(0.0, 0.0, 30.0))
    lowered = _entity(_lowered(project, scene), "wal")
    assert _floor(lowered).along == (1.0, 0.0)
    assert _floor(lowered).at == pytest.approx(lowered.stage.at)
    assert _checks(project, scene) == []


def test_a_member_whose_hand_placement_wins_has_no_world_floor(tmp_path):
    # placed by hand 30 px above the world's placement: the world's floor is
    # under the world's point, so it gets none, and `ground` is its own floor
    members = [_member("wal", "walker", (0.0, G, 5.0))]
    project, scene = _world(tmp_path, members, joints=SUPPORT)
    at = _entity(_lowered(project, scene), "wal").stage.at
    hand = f"- {{kind: prop, id: wal, store: props, ref: walker, stage: {{at: [{at[0]}, {at[1] - 30}]}}}}\n"
    project, scene = _world(tmp_path / "b", members, joints=SUPPORT, entities=hand)
    lowered = _lowered(project, scene)
    assert GROUND_OVERRIDE not in (_entity(lowered, "wal").overrides or {})
    assert "hand" in [n.kind for n in lowered.notes if n.entity == "wal"]
    assert not [f for f in _checks(project, scene) if f[0] != "info"]
    # one the world moves (in a moving car): the hand placement stays put on
    # screen, so a floor keyed under the world's point would skate under it
    members = [_member("wal", "walker", (0.0, G, 5.0), "car")]
    project, scene = _world(tmp_path / "c", members, joints=SUPPORT, entities=hand)
    lowered = _lowered(project, scene)
    assert GROUND_OVERRIDE not in (_entity(lowered, "wal").overrides or {})
    assert "hand_moving" in [n.kind for n in lowered.notes]
    assert not [f for f in _checks(project, scene) if f[0] != "info"]


# --- the mark is the lowering's own ------------------------------------------------


def test_a_hand_written_mark_is_replaced_or_dropped_on_a_framed_shot(tmp_path):
    members = [_member("wal", "walker", (0.0, G, 5.0))]
    written = "- {kind: prop, id: wal, store: props, ref: walker, overrides: {ground: {at: [0, 10], along: [1, 0]}}}\n"
    for ground, said in ((G, "replaced"), (None, "dropped")):
        project, scene = _world(
            tmp_path / said, members, joints=SUPPORT, ground=ground, entities=written
        )
        lowered = _lowered(project, scene)
        mark = _floor(_entity(lowered, "wal"))
        [note] = [n for n in lowered.notes if n.kind == "ground"]
        assert note.severity == "warning" and said in note.message
        if ground is None:
            assert mark is None
        else:
            assert mark.at[1] == pytest.approx(60.0)
    # a lowered shot lowered again keeps its marks, and says nothing: one
    # still, and one the camera's dolly passes (keyed)
    project, scene = _world(tmp_path / "again", members, camera="dolly")
    once = _lowered(project, scene)
    assert "keys" in (_entity(once, "wal").overrides or {})[GROUND_OVERRIDE]
    twice = lower_scene(once.scene, project.mall)
    assert _entity(twice, "wal").overrides == _entity(once, "wal").overrides
    assert not [n for n in twice.notes if n.kind == "ground"]
    project, scene = _world(tmp_path / "still", members)
    once = _lowered(project, scene)
    twice = lower_scene(once.scene, project.mall)
    assert _entity(twice, "wal").overrides == _entity(once, "wal").overrides
    assert not [n for n in twice.notes if n.kind == "ground"]


def test_a_mark_on_a_shot_no_world_lowered_is_refused(tmp_path):
    from an.stage.compile import CutoutCompileError, compile_shot

    project = _project(
        tmp_path,
        entities="- {kind: prop, id: wal, store: props, ref: walker, stage: {at: [0, 100]}, overrides: {ground: {at: [0, 100], along: [1, 0]}}}\n",
        shot=_shot(SUPPORT, ground=None),
    )
    with pytest.raises(CutoutCompileError, match="overrides.ground"):
        compile_shot(project.scene.timeline[0], project.mall)


def test_a_long_travel_in_depth_keys_the_floor_to_the_travels_tolerance(tmp_path):
    # 60 s of a camera closing on a still member, 30 to 6 units away: keyed
    # within the travel's tolerance, not per frame
    members = [_member("wal", "walker", (0.3, G, 30.0))]
    project, scene = _world(tmp_path, members, camera="dolly", speed=0.4)
    world = scene.world.model_copy(
        update={
            "frames": {
                "dolly": Frame(moving=FrameMoving(direction=(0.0, 0.0, 1.0), speed=0.4))
            }
        }
    )
    shot = scene.timeline[0].model_copy(update={"duration": 60.0})
    scene = scene.model_copy(update={"world": world, "timeline": [shot]})
    floor = (_entity(_lowered(project, scene), "wal").overrides or {})[GROUND_OVERRIDE]
    keys = floor["keys"]
    assert len(keys) <= 20, len(keys)
    for t in (7.3, 31.1, 52.9):  # between keys, within the tolerance of the floor
        depth = 30.0 - 0.4 * t
        assert world_ground_at(floor, t).at[1] == pytest.approx(
            FOCAL / depth, abs=DFLT_TRAVEL_TOLERANCE_PX
        )
