"""A bone's rest pose poses its part (an#339).

Before it, a bone's ``rotation_deg`` and ``scale_*`` reached no node
(``TransformJSON(x, y)`` only), so a tripod's legs or a hanging sword were
drawn pre-rotated in pixels. Now the built node carries them, every rest
reader composes on the built transform, and the schema bump's migration
protects a legacy rig that carried a pose it never showed.

The fixture is the core corpus's ``rig_rest`` scene: a tripod whose three legs
are one drawing on bones at 22 / 0 / -22 degrees.
"""

from __future__ import annotations

import copy
import json
import math
import shutil
import warnings
from pathlib import Path

import pytest

from an.ir.migrate import migrate
from an.ir.schema import AssetRef, Shot, StagePlacement, TweenAction
from an.stage.compile import compile_shot
from an.stage.props import PROP_DOCUMENT_KIND, PROP_SCHEMA_VERSION, PropDescriptor
from an.stage.rig import REST_POSE_SINCE, RestPoseWarning, rig_rest_problems
from an.stores.props import PropsStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "misc" / "bench" / "corpus" / "rig_rest" / "assets" / "props"


def _doc() -> dict:
    return json.loads((FIXTURE / "tripod" / "prop.json").read_text(encoding="utf-8"))


def _mall(tmp_path, doc: dict | None = None):
    shutil.copytree(FIXTURE, tmp_path / "props")
    if doc is not None:
        (tmp_path / "props" / "tripod" / "prop.json").write_text(json.dumps(doc), encoding="utf-8")
    return {"props": PropsStore(tmp_path / "props")}


def _shot(*, actions=()) -> Shot:
    return Shot(
        id="s1",
        renderer="cutout",
        duration=0.5,
        entities=[
            AssetRef(
                kind="prop", id="t", store="props", ref="tripod", stage=StagePlacement(at=(0.0, 100.0))
            )
        ],
        actions=list(actions),
    )


def _legs(scene) -> dict[str, float]:
    (entity,) = [n for n in scene.scene.children if n.name == "t"]
    return {c.name: c.transform.rotation for c in entity.children}


def test_a_bones_rest_rotation_reaches_its_node(tmp_path):
    legs = _legs(compile_shot(_shot(), mall=_mall(tmp_path)))
    assert legs["leg_l"] == pytest.approx(math.radians(22))
    assert legs["leg_r"] == pytest.approx(math.radians(-22))
    assert legs["leg_c"] == 0.0 and legs["body"] == 0.0


def test_a_bones_rest_scale_reaches_its_node_and_minus_zero_is_normalised(tmp_path):
    doc = _doc()
    for bone in doc["bones"]:
        if bone["name"] == "leg_c":
            bone["scale_y"] = 1.5
            bone["rotation_deg"] = -0.0
    scene = compile_shot(_shot(), mall=_mall(tmp_path, doc))
    (entity,) = [n for n in scene.scene.children if n.name == "t"]
    leg_c = next(c for c in entity.children if c.name == "leg_c")
    assert leg_c.transform.scale_y == 1.5
    assert math.copysign(1.0, leg_c.transform.rotation) == 1.0  # +0.0, never -0.0


@pytest.mark.genre("cutout_animation")
def test_a_from_less_tween_starts_from_the_rest_pose(tmp_path):
    """With the cut-out genre registered: the timeline-aware from-less
    resolution lives in its lowering today, so the core alone starts from
    identity (an#365, which moves it into the core)."""
    shot = _shot(actions=[TweenAction(target="t/leg_r", property="rotation", to_value=0.0, duration=0.5)])
    scene = compile_shot(shot, mall=_mall(tmp_path))
    (clip,) = scene.animations.values()
    first = clip.channels[0].keyframes[0].value
    assert first == pytest.approx(math.radians(-22))


def test_a_slot_nested_under_its_bones_primary_slot_is_not_posed_twice(tmp_path):
    """A non-primary slot on a posed bone is a PixiJS child of the primary
    slot's node, so it turns WITH it; giving it the bone's rotation as well
    would turn it twice."""
    doc = _doc()
    doc["slots"].append({"name": "badge", "bone": "leg_l", "draw_order": 4, "attachment": "leg"})
    doc["skins"]["default"]["slots"]["badge"] = {"leg": {"path": "parts/leg.svg"}}
    scene = compile_shot(_shot(), mall=_mall(tmp_path, doc))
    (entity,) = [n for n in scene.scene.children if n.name == "t"]
    leg_l = next(c for c in entity.children if c.name == "leg_l")
    (badge,) = leg_l.children
    assert leg_l.transform.rotation == pytest.approx(math.radians(22))
    assert badge.transform.rotation == 0.0


def test_the_migration_protects_only_a_legacy_rig_that_carried_a_pose(tmp_path):
    legacy = _doc()
    legacy["schema_version"] = "0.1.0"
    migrated = migrate(copy.deepcopy(legacy), kind=PROP_DOCUMENT_KIND.name)
    assert migrated["schema_version"] == PROP_SCHEMA_VERSION == REST_POSE_SINCE["PropDescriptor"]
    assert migrated["rest_rotation"] is False
    # ...and it keeps its pixels: built flat, as it always was, and silently
    # (the migration decided; the guard is for documents it cannot see).
    with warnings.catch_warnings():
        warnings.simplefilter("error", RestPoseWarning)
        legs = _legs(compile_shot(_shot(), mall=_mall(tmp_path, legacy)))
    assert set(legs.values()) == {0.0}
    # A legacy rig with no pose gets nothing but the version.
    plain = {"kind": "PropDescriptor", "schema_version": "0.1.0", "name": "lamp"}
    assert migrate(dict(plain), kind=PROP_DOCUMENT_KIND.name) == {**plain, "schema_version": "0.2.0"}


def test_a_posed_rig_with_no_version_is_built_flat_and_warned(tmp_path):
    """`version_of` reads a missing version as CURRENT, so the migration never
    sees such a document: the builder guard duplicates its condition."""
    doc = _doc()
    del doc["schema_version"]
    with pytest.warns(RestPoseWarning, match="schema_version"):
        legs = _legs(compile_shot(_shot(), mall=_mall(tmp_path, doc)))
    assert set(legs.values()) == {0.0}
    doc["rest_rotation"] = False  # the author's way to keep it, silently
    with warnings.catch_warnings():
        warnings.simplefilter("error", RestPoseWarning)
        compile_shot(_shot(), mall=_mall(tmp_path / "again", doc))


def test_rest_rotation_is_omitted_when_unset_and_round_trips_when_set():
    assert "rest_rotation" not in PropDescriptor(name="x").model_dump()
    kept = PropDescriptor(name="x", rest_rotation=False)
    assert PropDescriptor.model_validate_json(kept.model_dump_json()).rest_rotation is False


def test_drift_does_not_read_a_schema_bump_as_an_edit():
    """The factory and the CLI re-save a descriptor at this build's version;
    `drift` migrates both sides, so an untouched copy is not "edited"."""
    from an.library.checkout import drift

    pinned = {"kind": "PropDescriptor", "schema_version": "0.1.0", "name": "lamp"}
    resaved = {**pinned, "schema_version": PROP_SCHEMA_VERSION}
    assert drift({"lamp": resaved}, "lamp", {"doc": pinned, "files": {}}) == []
    edited = {**resaved, "display_name": "Lamp!"}
    assert drift({"lamp": edited}, "lamp", {"doc": pinned, "files": {}}) == ["descriptor edited"]


def test_validate_warns_on_a_rest_rotated_bone_with_an_offset_part(tmp_path):
    from an.ir.schema import Meta, SceneIR
    from an.ir.validate import validate_semantic

    doc = _doc()
    doc["skins"]["default"]["slots"]["leg_l"]["leg"]["y"] = 30.0
    mall = _mall(tmp_path, doc)
    report = validate_semantic(SceneIR(meta=Meta(), timeline=[_shot()]), available_props=mall["props"])
    found = [f for f in report.findings if "rests at 22" in f.description]
    assert found and found[0].severity == "warning" and report.passed
    assert rig_rest_problems(doc) and not rig_rest_problems(_doc())
