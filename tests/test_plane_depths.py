"""A plane at a world depth (an#503, slice 1): the parallax factor is derived.

An environment member's ``depths`` (``{plane: z}``, world units) give each named
plane the factor ``z_ref / z`` (``z_ref``: the depth of what the shot shows), which
the compiler reads where it reads the descriptor's own ``depth``: a plane at a depth
compiles byte for byte as one with that factor written by hand.

Slice 2 (an#598): a depth is the plane's ``z`` in its own frame, and a plane in a
frame that moves relative to the viewpoint's is keyed instead (its screen position
and apparent size, sampled from the exact projection and fitted to the travel's
pixel tolerance); the P4a lint (neither far nor at a depth) stops firing for it.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from an.base import PLANE_FACTORS_OVERRIDE
from an.ir.schema import (
    AssetRef,
    Camera,
    CameraKey,
    Shot,
    WorldMember,
)
from an.ir.validate import validate_semantic
from an.ir.world import lower_world, parallax_factor
from an.stage.compile import CutoutCompileError, compile_shot
from an.stage.world import lower_scene
from tests.test_world_frames import EXTENTS, _env_project, _scene

#: The lamps stand 2 deep, so a plane 20 deep derives 2 / 20.
Z, FACTOR = 20.0, 0.1


def _shot() -> Shot:
    return Shot(
        id="s",
        duration=1.0,
        viewpoint="road",
        renderer="stage",
        entities=[
            AssetRef(kind="environment", id="set", store="environments", ref="stage")
        ],
        camera=Camera(keys=[CameraKey(at=0.0, x=0.0), CameraKey(at=1.0, x=-120.0)]),
    )


def _scene_with(depths=None):
    scene = _scene(_shot())
    scene.world.members.append(
        WorldMember(
            kind="environment",
            id="set",
            store="environments",
            ref="stage",
            depths=depths,
        )
    )
    return scene


def _compiled(project, scene) -> str:
    lowered = lower_scene(scene, project.mall)
    shot = lowered.scene.timeline[0]
    doc = compile_shot(shot, project.mall, fps=24, width=320, height=240)
    return doc.model_dump_json()


def _set_plane_depth(project, plane: str, depth: float) -> None:
    doc = dict(project.mall["environments"]["stage"])
    for p in doc["planes"]:
        if p["name"] == plane:
            p["depth"] = depth
    project.mall["environments"]["stage"] = doc


def test_a_plane_at_a_depth_compiles_as_the_hand_written_factor(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        derived = _compiled(_env_project(tmp_path / "a"), _scene_with({"sky": Z}))
        by_hand_project = _env_project(tmp_path / "b")
        _set_plane_depth(by_hand_project, "sky", FACTOR)
        by_hand = _compiled(by_hand_project, _scene_with())
    assert "__parallax__s_set_sky_x" in derived  # the plane really scrolls
    assert derived == by_hand


def test_a_plane_at_the_reference_depth_emits_nothing(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        compiled = _compiled(_env_project(tmp_path), _scene_with({"sky": 2.0}))
    assert "__parallax__s_set_sky" not in compiled


def test_the_lowering_hands_the_factors_to_the_compiler_through_overrides():
    lowered = lower_world(_scene_with({"sky": Z, "hill": 4.0}), extents=EXTENTS)
    (env,) = [e for e in lowered.scene.timeline[0].entities if e.kind == "environment"]
    assert env.overrides[PLANE_FACTORS_OVERRIDE] == {"sky": FACTOR, "hill": 0.5}
    assert parallax_factor(20.0, 2.0) == FACTOR


def test_a_scene_without_depths_lowers_as_it_did():
    lowered = lower_world(_scene_with(), extents=EXTENTS)
    (env,) = [e for e in lowered.scene.timeline[0].entities if e.kind == "environment"]
    assert not env.overrides


def test_a_world_depth_and_a_parallax_of_its_own_are_two_spellings(tmp_path):
    project = _env_project(tmp_path)
    _set_plane_depth(project, "sky", 0.3)
    scene = _scene_with({"sky": Z})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )
        errors = [f.description for f in report.findings if f.severity == "error"]
        assert any("two spellings of one fact" in d for d in errors)
        with pytest.raises(CutoutCompileError, match="two spellings"):
            _compiled(project, scene)


def test_a_depth_for_a_plane_the_environment_lacks_is_an_error(tmp_path):
    project = _env_project(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            _scene_with({"moon": Z}),
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )
    assert any(
        f.severity == "error" and "has no such plane" in f.description
        for f in report.findings
    )


def test_depths_are_for_environments_and_must_be_positive_and_finite():
    kw = {"id": "x", "store": "props", "ref": "lamp"}
    with pytest.raises(ValueError, match="only an environment has `depths`"):
        WorldMember(kind="prop", at=(0, 0, 1), height=1.0, depths={"a": 1.0}, **kw)
    for bad in (0.0, -1.0, float("inf")):
        with pytest.raises(ValueError, match="positive, finite"):
            WorldMember(
                kind="environment",
                id="e",
                store="environments",
                ref="r",
                depths={"a": bad},
            )


def test_depths_round_trip_and_are_omitted_when_unset():
    member = WorldMember(
        kind="environment", id="e", store="environments", ref="r", depths={"sky": 20.0}
    )
    assert json.loads(member.model_dump_json())["depths"] == {"sky": 20.0}
    plain = WorldMember(kind="environment", id="e", store="environments", ref="r")
    assert "depths" not in json.loads(plain.model_dump_json())


def test_a_shot_that_shows_nothing_to_measure_against_keeps_the_planes_factors():
    scene = _scene_with({"sky": Z})
    scene.world.viewpoints["road"].hide = ["left", "right"]
    lowered = lower_world(scene, extents=EXTENTS)
    (env,) = [e for e in lowered.scene.timeline[0].entities if e.kind == "environment"]
    assert not env.overrides
    assert [n.kind for n in lowered.notes if n.kind == "plane_depths"] == [
        "plane_depths"
    ]


def test_a_plane_in_a_far_frame_cannot_also_have_a_depth(tmp_path):
    from an.ir.schema import Frame

    project = _env_project(tmp_path)
    scene = _scene_with({"sky": Z})
    scene.world.frames = {"far": Frame(coupling="far")}
    scene.world.members[-1].planes = {"sky": "far"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )
    assert any(
        f.severity == "error" and "coupled by rotation only" in f.description
        for f in report.findings
    )


def test_validate_reads_the_derived_factors_not_the_raw_descriptor(tmp_path):
    """The parallax check must see what the compiler sees: planes at different depths scroll differently."""
    project = _env_project(tmp_path)
    scene = _scene_with({"sky": Z, "hill": 4.0})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )
    assert not [
        f for f in report.findings if "all moving at the same rate" in f.description
    ]


def test_the_reference_depth_is_the_subjects_when_the_viewpoint_names_one():
    from an.ir.schema import Viewpoint
    from an.ir.world import Placed, reference_depth

    shown = {
        "a": Placed("a", (0, 0), 1.0, 2.0, None, True, "world"),
        "b": Placed("b", (0, 0), 1.0, 6.0, None, True, "world"),
        "hat": Placed("hat", (0, 0), 1.0, 6.0, None, True, "attached"),
    }
    assert (
        reference_depth(shown, Viewpoint()) == 4.0
    )  # an attached member is not counted twice
    assert reference_depth(shown, Viewpoint(subject="b")) == 6.0
    assert reference_depth({}, Viewpoint()) is None


@pytest.mark.parametrize("bad", [-1.0, float("inf")])
def test_factors_a_hand_wrote_into_overrides_must_be_finite_and_not_negative(
    tmp_path, bad
):
    project = _env_project(tmp_path)
    shot = _shot()
    shot.entities[0] = shot.entities[0].model_copy(
        update={"overrides": {PLANE_FACTORS_OVERRIDE: {"sky": bad}}}
    )
    with pytest.raises(CutoutCompileError, match="finite and >= 0"):
        compile_shot(shot, project.mall, fps=24, width=320, height=240)


# --- slice 2 (an#598): a plane at a depth in a frame that moves -------------------------

from an.ir.schema import DFLT_TRAVEL_TOLERANCE_PX, Frame, FrameMoving  # noqa: E402
from tests.test_world_frames import _plate_findings, _plates_scene  # noqa: E402

#: The camera (viewpoint ``road``) and its lens, as ``tests.test_world_frames`` has it.
EYE, FOCAL, SPEED = (0.0, -1.0, 0.0), 300.0, 4.0
#: The hill plane's origin on screen (the ``front_plane`` corpus environment).
HILL_OFFSET = (0.0, 80.0)


def _moving_scene(direction=(0.0, 0.0, 1.0), *, actions=(), duration=1.0, shots=1):
    """The camera rides a vehicle moving along ``direction``; the hill stands
    still in the world, ``Z`` deep."""
    shot = _shot().model_copy(
        update={"camera": None, "actions": list(actions), "duration": duration}
    )
    scene = _scene_with({"hill": Z})
    scene.timeline = [shot.model_copy(update={"id": f"s{i}"}) for i in range(shots)]
    scene.world.frames = {
        "vehicle": Frame(moving=FrameMoving(direction=direction, speed=SPEED))
    }
    scene.world.viewpoints["road"].frame = "vehicle"
    env = scene.world.members[-1]
    env.frame, env.planes = "vehicle", {"hill": "world"}
    return scene


def _hill_on_screen(project, scene, t, point=(0.0, 0.0), *, shot_index=0):
    from an.stage.timeline import screen_position, timeline_from_scene
    from an.timing import evaluate_timeline

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        shot = lower_scene(scene, project.mall).scene.timeline[shot_index]
        doc = compile_shot(shot, project.mall, fps=24, width=320, height=240)
    pose = evaluate_timeline(timeline_from_scene(doc), t)
    sx, sy = screen_position(doc, "set/hill", pose=pose, point=point)
    return sx - 160.0, sy - 120.0


def _exact(direction, t, point=(0.0, 0.0)):
    """The pinhole projection of a point of the hill plate (``point``: px in the
    plate, as it shows when the shot opens) seen from the moving camera at ``t``.
    Written out, not computed by the code under test: the ray from the camera at
    ``EYE`` through the hill's origin on screen (``HILL_OFFSET``) meets ``z = Z``
    at ``(0, -1 + 80 / 300 * 20, 20)``, ``Z`` in front of it."""
    anchor = (0.0, -1.0 + HILL_OFFSET[1] / FOCAL * Z, Z)
    p = (anchor[0] + point[0] * Z / FOCAL, anchor[1] + point[1] * Z / FOCAL, Z)
    cam = tuple(e + d * SPEED * t for e, d in zip(EYE, direction))
    rx, ry, depth = (a - c for a, c in zip(p, cam))
    return FOCAL * rx / depth, FOCAL * ry / depth


@pytest.mark.parametrize(
    "direction", [(0.0, 0.0, 1.0), (1.0, 0.0, 0.0)], ids=["toward", "across"]
)
def test_a_plane_at_a_depth_in_the_world_streams_past_a_moving_camera(
    tmp_path, direction
):
    project = _env_project(tmp_path)
    scene = _moving_scene(direction)
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        # its origin, within the travel's tolerance; a point off it, within that
        # plus the scale's (the tolerance over the frame's larger side, per px)
        for point in ((0.0, 0.0), (120.0, 30.0)):
            tol = DFLT_TRAVEL_TOLERANCE_PX * (1.0 + max(map(abs, point)) / 320.0)
            got = _hill_on_screen(project, scene, t, point)
            want = _exact(direction, t, point)
            assert max(abs(g - w) for g, w in zip(got, want)) <= tol + 1e-6, (
                t,
                point,
                got,
                want,
            )
    start, end = _exact(direction, 0.0), _exact(direction, 1.0)
    assert max(abs(end[0] - start[0]), abs(end[1] - start[1])) >= 10, "it really moves"


def test_a_plane_in_a_frame_still_relative_to_the_camera_is_not_keyed():
    scene = _moving_scene()
    scene.world.members[-1].planes = {"hill": "vehicle"}
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    assert not [a for a in shot.actions if getattr(a, "target", "") == "set/hill"]
    (env,) = [e for e in shot.entities if e.kind == "environment"]
    assert env.overrides[PLANE_FACTORS_OVERRIDE] == {"hill": 2.0 / Z}


def test_the_lint_for_a_plane_in_a_moving_frame_stops_firing_once_it_has_a_depth(
    tmp_path,
):
    project = _env_project(tmp_path)
    moves = "moves relative to the viewpoint's frame"
    bare = _plates_scene(
        project, frame="vehicle", planes={"sky": "far", "hill": "world"}
    )
    assert any("'set/hill'" in d and moves in d for d in _plate_findings(project, bare))
    deep = _plates_scene(
        project,
        frame="vehicle",
        planes={"sky": "far", "hill": "world"},
        depths={"hill": Z},
    )
    found = _plate_findings(project, deep)
    assert not any("'set/hill'" in d and moves in d for d in found)
    assert not any("not derived" in d for d in found)


def test_a_depth_is_the_planes_z_in_its_frame_not_its_distance_from_the_camera():
    scene = _scene_with({"sky": Z})
    scene.world.viewpoints["road"].at = (0.0, -1.0, -2.0)  # two units further back
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    (env,) = [e for e in shot.entities if e.kind == "environment"]
    # the lamps (z = 2) and the sky (z = 20) are both two units further away
    assert env.overrides[PLANE_FACTORS_OVERRIDE] == {"sky": pytest.approx(4.0 / 22.0)}


def test_the_shots_own_actions_on_a_plane_win_over_its_depth():
    from an.ir.compose import tween

    scene = _moving_scene(actions=[tween("set/hill", "x", to=10.0, duration=1.0)])
    lowered = lower_world(scene, extents=EXTENTS)
    shot = lowered.scene.timeline[0]
    assert len([a for a in shot.actions if getattr(a, "target", "") == "set/hill"]) == 1
    assert any(
        n.kind == "plane_depths" and "actions win" in n.message for n in lowered.notes
    )


def test_a_plane_behind_the_camera_keeps_its_own_parallax():
    scene = _scene_with({"sky": Z})
    scene.world.viewpoints["road"].at = (0.0, -1.0, Z + 1.0)
    lowered = lower_world(scene, extents=EXTENTS)
    (env,) = [e for e in lowered.scene.timeline[0].entities if e.kind == "environment"]
    assert PLANE_FACTORS_OVERRIDE not in (env.overrides or {})
    assert any("not in front of the camera" in n.message for n in lowered.notes)


def _hill_keys(shot):
    """The flat actions on the hill plane: ``(start, action)``, in time order."""
    from an.ir.compose import flatten, parallel

    return sorted(
        (
            (f.start, f.action)
            for f in flatten(parallel(*shot.actions))
            if getattr(f.action, "target", "") == "set/hill"
        ),
        key=lambda item: item[0],
    )


def test_a_cut_continues_the_same_plate(tmp_path):
    project = _env_project(tmp_path)
    scene = _moving_scene(shots=2)
    end_of_first = _hill_on_screen(project, scene, 1.0, (120.0, 30.0))
    start_of_second = _hill_on_screen(project, scene, 0.0, (120.0, 30.0), shot_index=1)
    want = _exact((0.0, 0.0, 1.0), 1.0, (120.0, 30.0))
    for got in (end_of_first, start_of_second):
        assert (
            max(abs(g - w) for g, w in zip(got, want)) <= 1.5 * DFLT_TRAVEL_TOLERANCE_PX
        )


def test_a_plate_the_camera_drives_through_is_hidden_once_it_is_behind(tmp_path):
    scene = _moving_scene(duration=8.0)  # the camera reaches the hill at t = 5
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    alphas = [(t, a) for t, a in _hill_keys(shot) if a.property == "alpha"]
    assert alphas and alphas[-1][1].value == 0.0 and alphas[-1][0] <= 5.0


def test_a_side_window_sees_a_plane_at_a_depth_along_its_look(tmp_path):
    # the camera looks along +x out of a vehicle driving along +z: the hill,
    # Z along the look, streams across the window
    scene = _moving_scene()
    scene.world.viewpoints["road"].look = (90.0, 0.0, 0.0)
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    xs = [a for _, a in _hill_keys(shot) if a.property == "x"]
    assert len(xs) > 1, "the plane is keyed"
    assert not [
        n
        for n in lower_world(scene, extents=EXTENTS).notes
        if "not in front" in n.message
    ]


def test_a_fade_on_the_plane_does_not_stop_its_keys():
    from an.ir.compose import tween

    scene = _moving_scene(actions=[tween("set/hill", "alpha", to=0.5, duration=1.0)])
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    assert {a.property for _, a in _hill_keys(shot)} >= {"x", "y", "scale_x", "alpha"}


@pytest.mark.parametrize("via_json", [False, True], ids=["in memory", "via json"])
def test_lowering_a_lowered_scene_adds_no_plane_keys_and_no_note(via_json):
    from an.ir.schema import SceneIR

    lowered = lower_world(_moving_scene(), extents=EXTENTS)
    scene = lowered.scene
    if via_json:
        scene = SceneIR.model_validate_json(scene.model_dump_json())
    again = lower_world(scene, extents=EXTENTS)
    assert len(_hill_keys(again.scene.timeline[0])) == len(
        _hill_keys(lowered.scene.timeline[0])
    )
    assert not [n for n in again.notes if n.kind == "plane_depths"]


def test_a_plate_keyed_in_one_shot_is_held_where_it_is_in_a_still_one(tmp_path):
    from an.ir.compose import set_, tween

    project = _env_project(tmp_path)
    scene = _moving_scene(shots=2)
    scene.world.frames["vehicle"] = Frame()  # moved by the shots, not a velocity
    first, second = scene.timeline
    first.actions = [tween("vehicle", "at_z", to=SPEED, duration=1.0, from_=0.0)]
    second.actions = [set_("vehicle", "at_z", SPEED, at=0.0)]
    end_of_first = _hill_on_screen(project, scene, 1.0, (120.0, 30.0))
    in_second = _hill_on_screen(project, scene, 0.5, (120.0, 30.0), shot_index=1)
    want = _exact((0.0, 0.0, 1.0), 1.0, (120.0, 30.0))
    for got in (end_of_first, in_second):
        assert (
            max(abs(g - w) for g, w in zip(got, want)) <= 1.5 * DFLT_TRAVEL_TOLERANCE_PX
        )


def test_a_fade_on_a_plate_that_must_be_hidden_keeps_it_moving():
    from an.ir.compose import tween

    scene = _moving_scene(
        duration=8.0,
        actions=[tween("set/hill", "alpha", to=1.0, duration=1.0, from_=0.0)],
    )
    lowered = lower_world(scene, extents=EXTENTS)
    props = [a.property for _, a in _hill_keys(lowered.scene.timeline[0])]
    assert "x" in props and props.count("alpha") == 1, "the author's fade, and the keys"
    assert any("not hidden" in n.message for n in lowered.notes)


def test_a_depth_on_a_plane_the_travel_lists_far_is_an_error(tmp_path):
    from an.ir.schema import Travel

    project = _env_project(tmp_path)
    scene = _scene_with({"sky": Z})
    scene.world.travel = Travel(plates={"far": ["set/sky"]})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )
    assert any(
        f.severity == "error" and "lists it `far`" in f.description
        for f in report.findings
    )
    (env,) = [
        e
        for e in lower_world(scene, extents=EXTENTS).scene.timeline[0].entities
        if e.kind == "environment"
    ]
    assert PLANE_FACTORS_OVERRIDE not in (env.overrides or {})


# --- an#599: a plate turns with a frame that rolls ---------------------------------------


def _screen(project, scene, path, t, point=(0.0, 0.0)):
    from an.stage.timeline import screen_position, timeline_from_scene
    from an.timing import evaluate_timeline

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        shot = lower_scene(scene, project.mall).scene.timeline[0]
        doc = compile_shot(shot, project.mall, fps=24, width=320, height=240)
    pose = evaluate_timeline(timeline_from_scene(doc), t)
    return screen_position(doc, path, pose=pose, point=point)


def test_a_rolled_plate_turns_with_the_roll_clockwise_on_screen(tmp_path):
    """The camera's vehicle rolls 20 degrees, linearly, over the shot: at t =
    0.25 the plate's right edge has turned 5 degrees, clockwise on screen (y
    down: a positive angle), as a roll turns the picture (an#599)."""
    import math

    from an.ir.compose import tween

    project = _env_project(tmp_path)
    scene = _moving_scene(
        actions=[
            tween("vehicle", "roll", to=20.0, duration=1.0, from_=0.0, easing="linear")
        ]
    )
    a = _screen(project, scene, "set/hill", 0.25)
    b = _screen(project, scene, "set/hill", 0.25, (100.0, 0.0))
    assert math.atan2(b[1] - a[1], b[0] - a[0]) == pytest.approx(
        math.radians(5.0), abs=0.005
    )


def test_a_yaw_turns_no_plate_and_a_long_roll_keeps_turning():
    import math

    from an.ir.compose import tween

    yawed = lower_world(
        _moving_scene(
            actions=[tween("vehicle", "yaw", to=30.0, duration=1.0, from_=0.0)]
        ),
        extents=EXTENTS,
    ).scene.timeline[0]
    assert not [a for _, a in _hill_keys(yawed) if a.property == "rotation"]
    rolled = lower_world(
        _moving_scene(
            actions=[tween("vehicle", "roll", to=300.0, duration=1.0, from_=0.0)]
        ),
        extents=EXTENTS,
    ).scene.timeline[0]
    ends = [
        getattr(a, "to_value", None)
        if getattr(a, "to_value", None) is not None
        else a.value
        for _, a in _hill_keys(rolled)
        if a.property == "rotation"
    ]
    assert abs(ends[-1]) == pytest.approx(math.radians(300.0), abs=0.02)


def test_a_hand_rotation_on_a_plate_keeps_its_depth_keys():
    from an.ir.compose import tween

    scene = _moving_scene(
        actions=[
            tween("vehicle", "roll", to=20.0, duration=1.0, from_=0.0),
            tween("set/hill", "rotation", to=0.5, duration=1.0, from_=0.0),
        ]
    )
    lowered = lower_world(scene, extents=EXTENTS)
    props = [a.property for _, a in _hill_keys(lowered.scene.timeline[0])]
    assert "x" in props and props.count("rotation") == 1, "the author's, and the keys"
    assert any("does not turn with its frame" in n.message for n in lowered.notes)


def test_a_plate_rotates_as_the_camera_rolls_and_a_pan_adds_no_rotation():
    """The vehicle carrying the camera rolls 20 degrees over the shot: the plate
    in the world turns by the roll on screen (the other way), exactly at the
    shot's end. Without a roll, no rotation key."""
    import math

    from an.ir.compose import tween

    still = lower_world(_moving_scene(), extents=EXTENTS).scene.timeline[0]
    assert not [a for _, a in _hill_keys(still) if a.property == "rotation"]
    scene = _moving_scene(
        actions=[tween("vehicle", "roll", to=20.0, duration=1.0, from_=0.0)]
    )
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    turns = [(t, a) for t, a in _hill_keys(shot) if a.property == "rotation"]
    assert turns, "the plate is keyed with a rotation"
    last = turns[-1][1]
    final = getattr(last, "to_value", None)
    final = last.value if final is None else final
    assert abs(abs(final) - math.radians(20.0)) <= 0.01
