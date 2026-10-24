"""Frames of reference in the scene world (ADR 0009 amendment, P4a): the frame
tree, `in:` on members, viewpoints and streams, lowering by `world_pose`, and
the lints.

The byte-identity pin comes first: scenes written WITHOUT `frames`, `in` or
`at_*` actions (the world PR's vocabulary, the travel included) lower to
exactly the output recorded in ``fixtures/world_lowering_golden.json`` from the
code before frames existed.
"""

from __future__ import annotations

import json
from pathlib import Path

from an.ir.schema import (
    AssetRef,
    Attachment,
    Meta,
    Resolution,
    SceneIR,
    Shot,
    StagePlacement,
    Stream,
    Travel,
    Viewpoint,
    World,
    WorldMember,
)
from an.ir.world import lower_world

GOLDEN = Path(__file__).parent / "fixtures" / "world_lowering_golden.json"
BOX = (-5.0, -20.0, 5.0, 0.0)
W, H = 320, 240
EXTENTS = {k: BOX for k in ("left", "right", "hat", "pole", "car", "sign")}


def _lamp(id: str, **kw) -> WorldMember:
    return WorldMember(kind="prop", id=id, store="props", ref="lamp", **kw)


def _legacy_scenes() -> dict[str, SceneIR]:
    """Scenes in the world PR's vocabulary only (no frames, no `in`, no `at_*`)."""

    def base(**kw) -> SceneIR:
        world = World(
            members=[
                _lamp("left", at=(-0.5, 0.4, 2.0), height=0.8),
                _lamp("right", at=(0.5, 0.4, 2.0), height=0.8),
            ],
            viewpoints={
                "two": Viewpoint(at=(0.0, 0.0, 0.0), focal=300.0),
                "right_cu": Viewpoint(subject="right", size="close_up", focal=300.0),
                "road": Viewpoint(at=(0.0, -1.0, 0.0), focal=300.0),
                "side": Viewpoint(
                    at=(0.0, -1.0, 0.0), look=(90.0, 0.0, 0.0), focal=300.0
                ),
            },
        )
        return SceneIR(
            meta=Meta(fps=24, resolution=Resolution(width=W, height=H)),
            world=world,
            **kw,
        )

    still = base(
        timeline=[
            Shot(id="a", duration=1.0, viewpoint="two"),
            Shot(id="b", duration=1.0, viewpoint="right_cu"),
            Shot(
                id="c",
                duration=1.0,
                viewpoint="two",
                entities=[
                    AssetRef(
                        kind="prop",
                        id="left",
                        store="props",
                        ref="lamp",
                        stage=StagePlacement(at=(-40.0, 0.0), scale=2.0),
                    )
                ],
            ),
        ]
    )
    still.world.members.append(
        _lamp("hat", attached=Attachment(to="right", at=(0.0, -20.0), scale=0.5))
    )

    def travelling(view: str) -> SceneIR:
        s = base(
            timeline=[
                Shot(id="s1", duration=2.0, viewpoint=view),
                Shot(id="s2", duration=2.0, viewpoint=view),
            ]
        )
        s.world.travel = Travel(
            speed=4.0,
            far=30.0,
            streams=[Stream(id="pole", ref="lamp", height=1.5, every=3.0, lane=1.2)],
            plates={"far": ["set/sky"]},
        )
        return s

    return {
        "still": still,
        "travel": travelling("road"),
        "travel_side": travelling("side"),
    }


def _dump(scene: SceneIR) -> dict:
    lowered = lower_world(scene, extents=EXTENTS)
    return {
        "scene": json.loads(lowered.scene.model_dump_json()),
        "notes": [
            [n.shot, n.index, n.severity, n.kind, n.entity, n.message]
            for n in lowered.notes
        ],
    }


def test_scenes_without_frames_lower_exactly_as_before():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    got = {name: _dump(scene) for name, scene in _legacy_scenes().items()}
    assert got == golden


def _regenerate() -> None:
    """Rewrite the golden file. Run ONLY on a tree known to be pre-frames:
    ``python -c "import tests.test_world_frames as t; t._regenerate()"``."""
    GOLDEN.write_text(
        json.dumps({n: _dump(s) for n, s in _legacy_scenes().items()}, indent=1),
        encoding="utf-8",
    )


# --- the schema ------------------------------------------------------------------------

import math

import pytest

from an.ir.frames import FrameError, FrameTree, Pose, Track, TrackEvent
from an.ir.schema import Frame, FrameMoving
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.world import (
    WorldError,
    resolve_viewpoint,
    stream_instances,
)

SPEED = 4.0


def _scene(*shots: Shot, **world_kw) -> SceneIR:
    """Two lamps side by side two units away, a road, and a viewpoint at the
    origin of whichever frame the test puts it in."""
    world = World(
        members=[
            _lamp("left", at=(-0.5, 0.4, 2.0), height=0.8),
            _lamp("right", at=(0.5, 0.4, 2.0), height=0.8),
        ],
        viewpoints={"road": Viewpoint(at=(0.0, -1.0, 0.0), focal=300.0)},
        **world_kw,
    )
    return SceneIR(
        meta=Meta(fps=24, resolution=Resolution(width=W, height=H)),
        world=world,
        timeline=list(shots),
    )


def _channel(shot: Shot, entity: str, prop: str):
    """``(start, end, from, to)`` of every tween of one channel, in time order."""
    from an.ir.compose import flatten, parallel

    out = []
    for f in flatten(parallel(*shot.actions)):
        a = f.action
        if (
            getattr(a, "kind", "") == "tween"
            and a.target == entity
            and a.property == prop
        ):
            out.append((f.start, f.end, a.from_value, a.to_value))
    return sorted(out)


def _screen_at(shot: Shot, entity: str, t: float, tmp_mall) -> tuple[float, float]:
    """Where the compiled, evaluated shot puts ``entity`` at ``t`` (centre-relative px)."""
    import warnings

    from an.stage.compile import compile_shot
    from an.stage.timeline import screen_position, timeline_from_scene
    from an.timing import evaluate_timeline

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = compile_shot(shot, mall=tmp_mall, width=W, height=H, fps=24)
    pose = evaluate_timeline(timeline_from_scene(doc), t)
    sx, sy = screen_position(doc, entity, pose=pose)
    return sx - W / 2, sy - H / 2


def test_in_is_the_documents_key_and_round_trips_through_scene_md():
    scene = _scene(
        Shot(id="a", duration=1.0, viewpoint="road"),
        frames={
            "vehicle": Frame(moving=FrameMoving(speed=SPEED)),
            "far": Frame(parent="vehicle", coupling="far"),
        },
    )
    scene.world.members[0].frame = "vehicle"
    scene.world.viewpoints["road"].frame = "vehicle"
    scene.world.members.append(
        WorldMember(
            kind="environment",
            id="set",
            store="environments",
            ref="stage",
            frame="vehicle",
            planes={"sky": "far"},
        )
    )
    dumped = json.loads(scene.world.model_dump_json())
    assert (
        dumped["members"][0]["in"] == "vehicle" and "frame" not in dumped["members"][0]
    )
    assert dumped["viewpoints"]["road"]["in"] == "vehicle"
    assert dumped["frames"]["far"] == {"parent": "vehicle", "coupling": "far"}
    assert World.model_validate(dumped) == scene.world
    back = markdown_to_ir(ir_to_markdown(scene))
    assert back.world == scene.world


def test_a_world_without_frames_stores_no_frame_key():
    scene = _scene(Shot(id="a", duration=1.0, viewpoint="road"))
    text = scene.world.model_dump_json()
    assert '"in"' not in text and "frame" not in text and "planes" not in text


@pytest.mark.parametrize(
    "bad, says",
    [
        (dict(frames={"a": Frame(parent="b"), "b": Frame(parent="a")}), "cycle"),
        (dict(frames={"a": Frame(parent="nowhere")}), "not a frame"),
        (dict(frames={"world": Frame()}), "implicit root"),
        (
            dict(
                frames={"vehicle": Frame()},
                travel=Travel(speed=1.0),
            ),
            "already is the `vehicle` frame",
        ),
    ],
)
def test_a_frame_tree_that_is_not_a_tree_is_refused_with_the_fix(bad, says):
    with pytest.raises(ValueError, match=says):
        World(**bad)


def test_an_unknown_frame_is_refused_wherever_it_is_named():
    members = [_lamp("a", at=(0.0, 0.0, 1.0), height=1.0, frame="boat")]
    with pytest.raises(ValueError, match="'a'.*`in: boat`.*not a frame"):
        World(members=members)
    with pytest.raises(ValueError, match="viewpoint 'v'.*boat"):
        World(viewpoints={"v": Viewpoint(at=(0.0, 0.0, 0.0), frame="boat")})
    with pytest.raises(ValueError, match="stream 's'.*boat"):
        World(
            travel=Travel(
                streams=[
                    Stream(id="s", ref="lamp", height=1.0, every=3.0, frame="boat")
                ]
            )
        )


def test_an_attached_member_is_in_its_hosts_frame_and_planes_are_an_environments():
    with pytest.raises(ValueError, match="in its host's frame"):
        World(
            members=[
                _lamp("h", at=(0.0, 0.0, 1.0), height=1.0),
                _lamp("a", attached=Attachment(to="h"), frame="world"),
            ]
        )
    with pytest.raises(ValueError, match="only an environment"):
        _lamp("p", at=(0.0, 0.0, 1.0), height=1.0, planes={"sky": "world"})


# --- the frame tree --------------------------------------------------------------------


def test_a_far_frame_turns_with_its_parent_and_never_translates():
    tree = FrameTree(
        {
            "car": Frame(
                moving=FrameMoving(direction=(1.0, 0.0, 0.0), speed=10.0),
                look=(90.0, 0.0, 0.0),
            ),
            "sky": Frame(parent="car", coupling="far"),
            "dash": Frame(parent="car"),
        }
    )
    sky, dash = tree.world_pose("sky", 3.0), tree.world_pose("dash", 3.0)
    assert sky.at == (0.0, 0.0, 0.0)
    assert dash.at == pytest.approx((30.0, 0.0, 0.0))  # the car faces +x and drove 30 m
    assert sky.same_as(Pose(sky.at, dash.axes))  # both turned 90 degrees
    assert [round(v, 6) + 0.0 for v in sky.apply((0.0, 0.0, 1.0))] == [1.0, 0.0, 0.0]


def test_a_pose_and_its_inverse_cancel_for_any_look():
    p = Pose(
        (1.0, -2.0, 3.0),
        FrameTree({"f": Frame(look=(30.0, 20.0, 10.0))}).world_pose("f", 0).axes,
    )
    q = (4.0, 5.0, 6.0)
    assert p.inverse().apply(p.apply(q)) == pytest.approx(q)
    assert p.unapply(p.apply(q)) == pytest.approx(q)


def test_a_moving_frame_keeps_its_phase_across_a_cut():
    tree = FrameTree({"car": Frame(moving=FrameMoving(speed=5.0))})
    end_of_first = tree.world_pose("car", 2.0, film_start=0.0).at
    start_of_second = tree.world_pose("car", 0.0, film_start=2.0).at
    assert end_of_first == start_of_second == (0.0, 0.0, 10.0)


def test_a_track_replaces_the_declared_channel_for_the_shot():
    track = Track([TrackEvent(0.0, 2.0, to=10.0, easing="linear")])
    tree = FrameTree(
        {"dolly": Frame(at=(0.0, 0.0, 5.0))}, tracks={"dolly": {"at_z": track}}
    )
    assert tree.world_pose("dolly", 1.0).at[2] == pytest.approx(
        7.5
    )  # from the declared 5 to 10
    assert tree.world_pose("dolly", 9.0).at[2] == 10.0  # and it holds


# --- lowering ----------------------------------------------------------------------------

import shutil

from an.ir.compose import sequence, set_, tween
from an.project import load

ROOT = Path(__file__).resolve().parents[1]
LAMP = ROOT / "misc" / "bench" / "corpus" / "prop_swap"


@pytest.fixture
def mall(tmp_path):
    return load(Path(shutil.copytree(LAMP, tmp_path / "p"))).mall


def _lowered(scene: SceneIR, index: int = 0):
    return lower_world(scene, extents=EXTENTS).scene.timeline[index]


def _car(*shots: Shot, frames_form: bool) -> SceneIR:
    """The world PR's travel, in its sugar form and in the general form."""
    scene = _scene(*shots)
    streams = [Stream(id="pole", ref="lamp", height=1.5, every=3.0, lane=1.2)]
    if not frames_form:
        scene.world.travel = Travel(speed=SPEED, far=30.0, streams=streams)
        return scene
    scene.world.frames = {"vehicle": Frame(moving=FrameMoving(speed=SPEED))}
    scene.world.travel = Travel(far=30.0, streams=streams)
    for m in scene.world.members:
        m.frame = "vehicle"
    for v in scene.world.viewpoints.values():
        v.frame = "vehicle"
    return scene


def test_the_car_in_the_general_form_lowers_to_the_same_keys_as_the_travel():
    shots = [
        Shot(id="s1", duration=2.0, viewpoint="road"),
        Shot(id="s2", duration=2.0, viewpoint="road"),
    ]
    sugar = lower_world(_car(*shots, frames_form=False), extents=EXTENTS).scene
    general = lower_world(_car(*shots, frames_form=True), extents=EXTENTS).scene
    assert sugar.timeline == general.timeline
    assert any(e.id.startswith("pole_") for e in general.timeline[0].entities)


def test_a_roadside_viewpoint_sees_the_car_pass_with_no_hand_placement(mall):
    scene = _scene(
        Shot(id="side", duration=2.0, viewpoint="roadside"),
        frames={"vehicle": Frame(moving=FrameMoving(speed=SPEED))},
    )
    for m in scene.world.members:
        m.frame = "vehicle"
    scene.world.viewpoints["roadside"] = Viewpoint(
        at=(20.0, -1.0, 0.0), look=(-90.0, 0.0, 0.0), focal=300.0, frame="world"
    )
    lowered = lower_world(scene, extents=EXTENTS)
    shot = lowered.scene.timeline[0]
    assert {e.id for e in shot.entities} == {"left", "right"}
    assert all(e.stage is not None for e in shot.entities)
    assert _channel(shot, "right", "x"), "the car moves across the picture"
    assert [n.kind for n in lowered.notes] == ["added", "added"]
    eye = resolve_viewpoint(scene.world, "roadside", extents=EXTENTS, width=W, height=H)
    checked = 0
    for i in range(0, 9):
        t = i / 4
        exact = eye.project((0.5, 0.4, 2.0 + SPEED * t))
        sx, sy = _screen_at(shot, "right", t, mall)
        assert (sx, sy) == pytest.approx(exact[:2], abs=1.5)
        checked += 1
    assert checked == 9


def test_a_member_fixed_in_the_world_streams_past_a_travelling_view(mall):
    scene = _car(Shot(id="s1", duration=2.0, viewpoint="road"), frames_form=False)
    scene.world.members.append(
        _lamp("sign", at=(2.0, 0.0, 12.0), height=1.0, frame="world")
    )
    shot = _lowered(scene)
    assert _channel(shot, "sign", "x"), "the sign comes toward the camera"
    assert _channel(shot, "left", "x") == [], "the cast rides with the camera"
    eye = resolve_viewpoint(scene.world, "road", extents=EXTENTS, width=W, height=H)
    for i in range(0, 8):
        t = i / 4
        exact = eye.moved((0.0, 0.0, SPEED * t)).project((2.0, 0.0, 12.0))
        if exact is None or abs(exact[0]) > W / 2 or abs(exact[1]) > H / 2:
            continue
        got = _screen_at(shot, "sign", t, mall)
        assert got == pytest.approx(exact[:2], abs=1.5)


def test_a_viewpoint_in_a_chain_of_frames_is_a_camera_rig(mall):
    """world ⊃ dolly ⊃ arm ⊃ camera: moving the dolly moves the picture."""
    scene = _scene(
        Shot(
            id="s",
            duration=2.0,
            viewpoint="rig",
            actions=[
                tween("dolly", "at_z", to=3.0, duration=2.0, from_=0.0, easing="linear")
            ],
        ),
        frames={"dolly": Frame(), "arm": Frame(parent="dolly", at=(0.0, -1.0, 0.0))},
    )
    scene.world.viewpoints["rig"] = Viewpoint(
        at=(0.0, 0.0, 0.0), focal=300.0, frame="arm"
    )
    for m in scene.world.members:
        m.at = (m.at[0], m.at[1], 6.0)
    lowered = lower_world(scene, extents=EXTENTS)
    shot = lowered.scene.timeline[0]
    assert all(getattr(a, "target", "") != "dolly" for a in shot.actions), (
        "lowered, not played"
    )
    assert _channel(shot, "right", "x")
    for i in range(0, 9):
        t = i / 4
        # the camera sits 1 above the world's origin and has moved 1.5·t along z
        depth = 6.0 - 1.5 * t
        want = (300.0 * 0.5 / depth, 300.0 * (0.4 + 1.0) / depth)
        assert _screen_at(shot, "right", t, mall) == pytest.approx(want, abs=1.5)


def test_a_walk_in_a_moving_platforms_units(mall):
    scene = _scene(
        Shot(
            id="s",
            duration=2.0,
            viewpoint="road",
            actions=[
                tween("right", "at_x", to=1.0, duration=2.0, from_=0.5, easing="linear")
            ],
        ),
        frames={
            "platform": Frame(moving=FrameMoving(direction=(1.0, 0.0, 0.0), speed=0.25))
        },
    )
    scene.world.members[1].frame = "platform"
    shot = _lowered(scene)
    assert all(getattr(a, "property", "") != "at_x" for a in shot.actions)
    eye = resolve_viewpoint(scene.world, "road", extents=EXTENTS, width=W, height=H)
    seen = 0
    for i in range(0, 9):
        t = i / 4
        x = 0.25 * t + (
            0.5 + 0.25 * t
        )  # the platform's drift plus the walk, in its units
        exact = eye.project((x, 0.4, 2.0))
        if abs(exact[0]) > W / 2:
            continue  # left the frame: hidden
        assert _screen_at(shot, "right", t, mall) == pytest.approx(exact[:2], abs=1.5)
        seen += 1
    assert seen >= 4


def test_a_member_walking_in_the_cameras_own_frame_needs_no_frame_motion(mall):
    scene = _scene(
        Shot(
            id="s",
            duration=1.0,
            viewpoint="road",
            actions=[
                tween("left", "at_x", to=0.5, duration=1.0, from_=-0.5, easing="linear")
            ],
        )
    )
    shot = _lowered(scene)
    eye = resolve_viewpoint(scene.world, "road", extents=EXTENTS, width=W, height=H)
    for t in (0.0, 0.5, 1.0):
        x = -0.5 + t
        assert _screen_at(shot, "left", t, mall) == pytest.approx(
            eye.project((x, 0.4, 2.0))[:2], abs=1.5
        )


def test_a_member_that_passes_the_camera_is_hidden_once_it_is_behind_it():
    scene = _scene(
        Shot(id="s", duration=2.0, viewpoint="road"),
        frames={
            "vehicle": Frame(
                moving=FrameMoving(direction=(0.0, 0.0, -1.0), speed=SPEED)
            )
        },
    )
    scene.world.members[
        0
    ].frame = "vehicle"  # starts 2 ahead and drives back through the lens
    shot = _lowered(scene)
    from an.ir.compose import flatten, parallel

    alphas = [
        (f.start, f.action.value)
        for f in flatten(parallel(*shot.actions))
        if getattr(f.action, "kind", "") == "set"
        and f.action.target == "left"
        and f.action.property == "alpha"
    ]
    assert alphas and alphas[-1][1] == 0.0, "it is hidden once it is past the camera"


def test_lowering_a_scene_with_members_in_motion_is_idempotent():
    scene = _scene(
        Shot(id="s", duration=2.0, viewpoint="road"),
        frames={
            "vehicle": Frame(moving=FrameMoving(direction=(1.0, 0.0, 0.0), speed=0.5))
        },
    )
    scene.world.members[1].frame = "vehicle"
    once = lower_world(scene, extents=EXTENTS).scene
    twice = lower_world(once, extents=EXTENTS).scene
    assert twice.timeline == once.timeline


def test_other_actions_keep_their_times_when_frame_actions_are_lowered():
    scene = _scene(
        Shot(
            id="s",
            duration=3.0,
            viewpoint="road",
            actions=[
                sequence(
                    tween("left", "alpha", to=0.5, duration=1.0),
                    tween("dolly", "at_z", to=1.0, duration=1.0),
                    tween("left", "alpha", to=1.0, duration=1.0),
                ),
                set_("right", "alpha", 0.25, at=2.0),
            ],
        ),
        frames={"dolly": Frame()},
    )
    scene.world.viewpoints["road"].frame = "dolly"
    shot = _lowered(scene)
    from an.ir.compose import flatten, parallel

    times = sorted(
        (f.action.target, f.action.property, f.start)
        for f in flatten(parallel(*shot.actions))
        if f.action.target in ("left", "right")
    )
    assert ("left", "alpha", 0.0) in times and ("left", "alpha", 2.0) in times
    assert ("right", "alpha", 2.0) in times


def test_an_inline_viewpoint_in_an_unknown_frame_is_a_world_error():
    scene = _scene(
        Shot(
            id="s", duration=1.0, viewpoint=Viewpoint(at=(0.0, 0.0, 0.0), frame="boat")
        )
    )
    with pytest.raises(WorldError, match="`in: boat`.*not a frame"):
        lower_world(scene, extents=EXTENTS)


def test_a_hand_placement_in_a_frame_that_moves_is_a_warning_naming_the_fix():
    scene = _scene(
        Shot(
            id="s",
            duration=2.0,
            viewpoint="road",
            entities=[
                AssetRef(
                    kind="prop",
                    id="right",
                    store="props",
                    ref="lamp",
                    stage=StagePlacement(at=(10.0, 0.0), scale=2.0),
                )
            ],
        ),
        frames={
            "vehicle": Frame(moving=FrameMoving(direction=(1.0, 0.0, 0.0), speed=1.0))
        },
    )
    scene.world.members[1].frame = "vehicle"
    lowered = lower_world(scene, extents=EXTENTS)
    warned = [n for n in lowered.notes if n.kind == "hand_moving"]
    assert (
        len(warned) == 1
        and warned[0].severity == "warning"
        and warned[0].entity == "right"
    )
    assert "Drop `stage.at`" in warned[0].message
    assert _channel(lowered.scene.timeline[0], "right", "x") == [], "the hand wins"


# --- validate ----------------------------------------------------------------------------

import warnings

from an.ir.validate import validate_semantic

PLANES = ROOT / "misc" / "bench" / "corpus" / "front_plane"


def _env_project(tmp_path):
    root = Path(shutil.copytree(LAMP, tmp_path / "p"))
    shutil.copytree(
        PLANES / "assets" / "environments" / "stage",
        root / "assets" / "environments" / "stage",
    )
    return load(root)


def _plate_findings(project, scene) -> list[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )
    return [f.description for f in report.findings if "plane 'set/" in f.description]


def _plates_scene(project, **env_kw) -> SceneIR:
    scene = _scene(
        Shot(
            id="s1",
            duration=0.5,
            viewpoint="road",
            entities=[
                AssetRef(
                    kind="environment", id="set", store="environments", ref="stage"
                )
            ],
        ),
        frames={
            "vehicle": Frame(moving=FrameMoving(speed=SPEED)),
            "far": Frame(parent="vehicle", coupling="far"),
        },
    )
    scene.meta = project.scene.meta
    scene.world.viewpoints["road"].frame = "vehicle"
    scene.world.members.append(
        WorldMember(
            kind="environment", id="set", store="environments", ref="stage", **env_kw
        )
    )
    return scene


def test_planes_under_a_moving_view_must_say_which_frame_they_are_in(tmp_path):
    project = _env_project(tmp_path)
    found = _plate_findings(project, _plates_scene(project))
    assert any("'set/sky'" in d and "nothing says what it holds" in d for d in found)
    assert any("`planes:" in d for d in found), "the message names the fix"
    none_needed = _plate_findings(
        project, _plates_scene(project, frame="vehicle", planes={"sky": "far"})
    )
    assert not any("nothing says" in d for d in none_needed)


def test_a_plane_in_a_far_frame_is_pinned_and_one_in_another_moving_frame_is_a_warning(
    tmp_path,
):
    project = _env_project(tmp_path)
    scene = _plates_scene(
        project, frame="vehicle", planes={"sky": "far", "hill": "world"}
    )
    found = _plate_findings(project, scene)
    assert any("'set/sky'" in d and "coupled by rotation only" in d for d in found), (
        "sky is in the far frame but its parallax factor is 1"
    )
    assert any(
        "'set/hill'" in d and "moves relative to the viewpoint's frame 'vehicle'" in d
        for d in found
    )
    assert not any("'set/rail'" in d for d in found), "rail rides with the camera"


# --- an world show --frames ----------------------------------------------------------------


def test_an_world_show_frames_prints_each_frame_as_the_shot_opens_and_closes(
    tmp_path, capsys
):
    from an.world_cli import show

    project = load(Path(shutil.copytree(LAMP, tmp_path / "p")))
    scene = _scene(
        Shot(id="a", duration=2.0, viewpoint="road"),
        Shot(id="b", duration=1.0, viewpoint="road"),
        Shot(id="plain", duration=1.0),
        frames={
            "vehicle": Frame(moving=FrameMoving(speed=SPEED)),
            "far": Frame(parent="vehicle", coupling="far"),
        },
    )
    scene.meta = project.scene.meta
    scene.world.viewpoints["road"].frame = "vehicle"
    (project.root / "scene.md").write_text(ir_to_markdown(scene), encoding="utf-8")
    shutil.rmtree(project.root / "ir")
    text = show(str(project.root), frames=True)
    assert "## a  viewpoint in: vehicle" in text and "## plain" not in text
    a = text.split("## b")[0]
    assert "vehicle" in a and "at (0, 0, 0)  ->  at (0, 0, 8)" in a
    b = text.split("## b")[1]
    assert "at (0, 0, 8)  ->  at (0, 0, 12)" in b, "film time carries across the cut"
    assert "[far]" in a
    rows = json.loads(show(str(project.root), frames=True, json=True))
    assert [r["shot"] for r in rows] == ["a", "b"]


# --- what the adversarial review found (PR 532) -----------------------------------------


def test_motion_that_ends_where_it_began_is_still_motion():
    scene = _scene(
        Shot(
            id="s",
            duration=2.0,
            viewpoint="road",
            actions=[
                sequence(
                    tween("right", "at_x", to=1.0, duration=1.0, from_=0.5, easing="linear"),
                    tween("right", "at_x", to=0.5, duration=1.0, easing="linear"),
                )
            ],
        )
    )
    xs = _channel(_lowered(scene), "right", "x")
    assert xs and max(t[3] for t in xs) == pytest.approx(150.0, abs=2.0), "out to 150 px and back"


def test_a_member_that_goes_behind_the_camera_and_returns_is_hidden_meanwhile():
    from an.ir.compose import flatten, parallel

    scene = _scene(
        Shot(
            id="s",
            duration=4.0,
            viewpoint="road",
            actions=[
                sequence(
                    tween("right", "at_z", to=-3.0, duration=2.0, from_=6.0, easing="linear"),
                    tween("right", "at_z", to=6.0, duration=2.0, easing="linear"),
                )
            ],
        )
    )
    shot = _lowered(scene)
    alphas = sorted(
        (f.start, f.action.value)
        for f in flatten(parallel(*shot.actions))
        if getattr(f.action, "kind", "") == "set"
        and f.action.target == "right"
        and f.action.property == "alpha"
    )
    assert 0.0 in [v for _, v in alphas] and 1.0 in [v for _, v in alphas]
    hidden = [t for t, v in alphas if v == 0.0]
    shown = [t for t, v in alphas if v == 1.0]
    assert hidden and shown and max(shown) > min(hidden), "gone, then back"


def test_a_hidden_member_that_moves_leaves_no_actions_on_an_absent_entity():
    scene = _scene(
        Shot(
            id="s",
            duration=2.0,
            viewpoint=Viewpoint(at=(0.0, 0.0, 0.0), focal=300.0, hide=["right"]),
            actions=[tween("right", "at_x", to=1.0, duration=1.0, from_=0.5)],
        )
    )
    shot = _lowered(scene)
    assert [e.id for e in shot.entities] == ["left"]
    assert all(getattr(a, "target", "left") != "right" for a in shot.actions)


def test_a_frame_and_a_member_may_not_share_a_name():
    with pytest.raises(ValueError, match="both a frame and a member"):
        _scene(frames={"left": Frame()})
