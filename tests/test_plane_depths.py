"""A plane at a world depth (an#503, slice 1): the parallax factor is derived.

An environment member's ``depths`` (``{plane: z}``, world units) give each named
plane the factor ``z_ref / z`` (``z_ref``: the depth of what the shot shows), which
the compiler reads where it reads the descriptor's own ``depth``: a plane at a depth
compiles byte for byte as one with that factor written by hand. Not here yet: a plane
in a frame that moves relative to the viewpoint's, whose motion keys the same depth
would derive.
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
