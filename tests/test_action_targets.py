"""Animation targets resolve against the node tree the compiler BUILDS (an#193).

End-user agents wrote ``ned/left_brow`` and ``wellington/mouth`` — the face
lives under ``<entity>/head/`` — and ``an validate`` passed both; the render
then died inside Chromium. Now validate reports the unknown target with the
real path suggested, and the compiler refuses it as a typed Python error before
any browser starts. Both read the one stage builder (`an.motion.stage_poses`),
so neither restates the rig.
"""

from __future__ import annotations

import pytest

from an.adapters.cutout.compile import (
    CutoutCompileError,
    compile_shot,
    node_path_suggestions,
)
from an.characters import new_character
from an.ir.compose import delay, sequence
from an.ir.schema import AssetRef, SceneIR, SetAction, Shot, TweenAction
from an.ir.validate import validate_semantic
from an.project import init
from an.stores import build_project_mall


@pytest.fixture
def mall(tmp_path):
    root = init(tmp_path / "p")
    mall = build_project_mall(root)
    for name in ("ned", "wellington"):
        new_character(root / "assets" / "characters", name=name, use_dicebear=False)
    return mall


def _shot(*actions, who=("ned",)):
    return Shot(
        id="s",
        duration=1.0,
        entities=[
            AssetRef(kind="character", id=w, store="characters", ref=w) for w in who
        ],
        actions=list(actions),
    )


def _errors(shot, mall, **stores):
    stores = stores or {"available_characters": mall["characters"]}
    report = validate_semantic(SceneIR(timeline=[shot]), **stores)
    return [f for f in report.findings if f.severity == "error"]


def test_validate_names_the_real_path_of_a_face_part(mall):
    """The South Park run: a `set` on `ned/left_brow`, inside a `start:` wrapper."""
    hide = SetAction(target="ned/left_brow", property="alpha", value=0.0)
    [err] = _errors(_shot(sequence(delay(0.5), hide)), mall)
    assert err.ir_path == "timeline/0/actions/0"
    assert "'ned/left_brow' is not a node" in err.description
    assert "did you mean 'ned/head/left_brow'" in err.description


def test_validate_catches_the_mouth_one_level_too_high(mall):
    """The OverSimplified run: `wellington/mouth` is `wellington/head/mouth`."""
    tw = TweenAction(target="wellington/mouth", property="alpha", to_value=0.0, duration=0.2)
    [err] = _errors(_shot(tw, who=("ned", "wellington")), mall)
    assert "did you mean 'wellington/head/mouth'" in err.description


def test_validate_passes_every_built_path_and_the_entity(mall):
    ok = [
        SetAction(target="ned/head/left_brow", property="alpha", value=0.0),
        TweenAction(target="ned/arm_r", property="rotation", to_value=-1.0, duration=0.3),
        TweenAction(target="ned", property="x", to_value=40.0, duration=0.3),
    ]
    assert _errors(_shot(*ok), mall) == []


def test_validate_names_an_unknown_entity(mall):
    [err] = _errors(_shot(TweenAction(target="nobody/head", property="x", to_value=1.0, duration=0.1)), mall)
    assert "no entity 'nobody'" in err.description


def test_without_the_characters_store_the_check_does_not_guess(mall):
    """The placeholder rig would stand in and its paths are not the
    descriptor's, so a store that was not supplied skips the check."""
    hide = SetAction(target="ned/left_brow", property="alpha", value=0.0)
    assert _errors(_shot(hide), mall, available_props={}) == []


def test_the_compiler_refuses_an_unknown_target_as_a_typed_error(mall):
    """Before this, the first anyone heard was a JS `applyPose` stack trace."""
    tw = TweenAction(target="ned/mouth", property="rotation", to_value=0.3, duration=0.5)
    with pytest.raises(CutoutCompileError, match=r"did you mean 'ned/head/mouth'"):
        compile_shot(_shot(tw), mall)


def test_the_compiler_accepts_what_it_built(mall):
    tw = TweenAction(target="ned/head/mouth", property="rotation", to_value=0.3, duration=0.5)
    doc = compile_shot(_shot(tw), mall)
    targets = {c.target for clip in doc.animations.values() for c in clip.channels}
    assert "ned/head/mouth" in targets


def test_suggestions_prefer_the_same_part_by_name():
    built = ["a", "a/head", "a/head/mouth", "a/torso", "b/head/mouth"]
    assert node_path_suggestions("a/mouth", built) == ["a/head/mouth"]
    assert node_path_suggestions("a/torsoo", built) == ["a/torso"]


def test_a_plane_target_is_not_judged_without_the_environments_store(mall):
    """The default backdrop would stand in for the plane environment, whose
    plane nodes it does not have."""
    shot = Shot(
        id="s",
        duration=1.0,
        entities=[AssetRef(kind="environment", id="map", store="environments", ref="map")],
        actions=[SetAction(target="map/west", property="tint", value="#3a5fa0")],
    )
    assert _errors(shot, mall) == []


def test_the_camera_node_is_a_legitimate_target(mall):
    """`root` is the runtime's camera node; the compiler accepts it, so must validate."""
    zoom = SetAction(target="root", property="scale_x", value=1.2)
    assert _errors(_shot(zoom), mall) == []
    compile_shot(_shot(zoom), mall)
