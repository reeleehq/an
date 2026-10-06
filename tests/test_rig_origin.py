"""A rig's declared origin: the point of its art that lands at ``stage.at`` (an#338).

Before it, a rig was placed by the centre of its bones' extent, so a prop
whose foot should stand on a floor line needed padding bones to move that
centre (the art lab's ``pad_origin``). ``RigDocument.origin`` declares the
point instead; :func:`an.stage.rig.rig_origin` is the one rule the builder
and a genre's extent report read.

The fixture is the core corpus's ``rig_origin`` scene: two copies of one
three-bone signpost, ``footed`` declaring its origin at the foot of its base
and ``centred`` declaring none.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from an.ir.schema import AssetRef, Shot, StagePlacement
from an.stage.compile import compile_shot
from an.stage.props import PropDescriptor
from an.stage.rig import (
    RigDocument,
    bone_extent_centre,
    bone_positions,
    build_rig_subtree,
    rig_origin,
    rig_origin_problems,
)
from an.stores.props import PropsStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "misc" / "bench" / "corpus" / "rig_origin" / "assets" / "props"


@pytest.fixture()
def mall(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "props")
    return {"props": PropsStore(tmp_path / "props")}


def _shot(ref: str, *, at=(0.0, 50.0)) -> Shot:
    return Shot(
        id="s1",
        renderer="cutout",
        duration=1.0,
        entities=[
            AssetRef(kind="prop", id="p", store="props", ref=ref, stage=StagePlacement(at=at))
        ],
    )


def _parts(scene) -> dict[str, tuple[float, float]]:
    (entity,) = [n for n in scene.scene.children if n.name == "p"]
    return {c.name: (c.transform.x, c.transform.y) for c in entity.children}


def test_the_declared_origin_is_the_point_that_lands_at_stage_at(mall):
    """`footed`'s origin is the bottom of its base: the base (anchored at its
    bottom edge, offset 10 below the root bone) sits exactly at the entity's
    node, which `stage.at` puts on the placement line."""
    footed = _parts(compile_shot(_shot("footed"), mall=mall))
    assert footed["base"] == (0.0, 0.0)
    # The undeclared copy: the same rig, placed by the middle of its bones.
    centred = _parts(compile_shot(_shot("centred"), mall=mall))
    assert centred["base"][1] > 0, "unset, the rig hangs below its placement point"
    # Same rig, so the parts differ by ONE translation: the two origins' gap.
    desc = PropDescriptor.model_validate(json.loads((FIXTURE / "centred" / "prop.json").read_text(encoding="utf-8")))
    k = 345.0 / desc.view_box[3]
    dy = (400.0 - rig_origin(desc)[1]) * k
    for name, (x, y) in footed.items():
        assert centred[name] == pytest.approx((x, y + dy))


def test_rig_origin_is_the_declared_point_else_the_bone_extent_centre():
    desc = PropDescriptor.model_validate(json.loads((FIXTURE / "centred" / "prop.json").read_text(encoding="utf-8")))
    assert rig_origin(desc) == bone_extent_centre(bone_positions(desc))
    assert rig_origin(desc.model_copy(update={"origin": (1.0, 2.0)})) == (1.0, 2.0)


def test_an_unset_origin_is_not_written_so_stored_descriptors_read_back_unchanged():
    """Every committed prop document re-dumps without an `origin` key: adding
    the field moved no stored descriptor and no library manifest."""
    docs = [p for p in ROOT.glob("misc/bench/corpus/*/assets/props/*/prop.json")]
    docs += list(ROOT.glob("tests/fixtures/**/prop.json"))
    assert docs
    for path in docs:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("kind") != "PropDescriptor":
            continue
        dumped = PropDescriptor.model_validate(raw).model_dump(mode="json")
        assert ("origin" in dumped) == ("origin" in raw), path
    assert "origin" not in RigDocument().model_dump()


def test_a_subclass_with_its_own_serializer_must_call_the_omit_helper():
    """pydantic keeps ONE model_serializer per model: a subclass that declares
    its own replaces the base's, so an unset origin would reach every stored
    document as null unless it calls `omit_unset_rig_fields` (as
    `cutan`'s CharacterDescriptor does)."""
    from pydantic import model_serializer

    from an.stage.rig import omit_unset_rig_fields

    class Forgets(RigDocument):
        @model_serializer(mode="wrap")
        def _own(self, handler):
            return handler(self)

    class Remembers(RigDocument):
        @model_serializer(mode="wrap")
        def _own(self, handler):
            return omit_unset_rig_fields(handler(self))

    assert Forgets().model_dump()["origin"] is None  # leaked into every dump
    assert Remembers().model_dump() == {}


def test_validate_warns_on_an_origin_outside_the_view_box(mall, tmp_path):
    from an.ir.schema import Meta, SceneIR
    from an.ir.validate import validate_semantic

    path = tmp_path / "props" / "footed" / "prop.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["origin"] = [100.0, 4000.0]
    path.write_text(json.dumps(doc), encoding="utf-8")
    report = validate_semantic(
        SceneIR(meta=Meta(), timeline=[_shot("footed")]),
        available_props=mall["props"],
    )
    warnings = [f for f in report.findings if "origin" in f.description]
    assert warnings and all(f.severity == "warning" for f in warnings), report.findings
    assert report.passed
    assert rig_origin_problems(doc) == rig_origin_problems(PropDescriptor.model_validate(doc))


def test_a_non_finite_origin_is_refused_by_the_model():
    with pytest.raises(ValueError):
        PropDescriptor(name="x", origin=(float("nan"), 0.0))
    assert rig_origin_problems({"origin": [float("inf"), 0.0]})


def test_the_compilers_old_private_names_are_the_public_builder():
    """cutan reached the builder through private names of the stage compiler;
    they stay importable, and they ARE the public API (an#338)."""
    from an.stage import compile as c
    from an.stage import rig

    assert c._build_svg_character_subtree is rig.build_rig_subtree is build_rig_subtree
    assert c._bone_positions is rig.bone_positions
    assert c._rig_origin is rig.bone_extent_centre
    assert c._part_probe is rig.part_probe
    assert c._raster_digest is rig.raster_digest
    assert c._svg_asset_src is rig.art_src
    assert c._note_raster_rig is c.note_raster_rig


def test_a_default_prop_takes_its_origin_in_the_arts_own_coordinates(tmp_path):
    """an#408: a one-part prop on the default bone, its art drawn on the full
    view_box, with its foot at (512, 1000): `origin=(512, 1000)` puts that
    foot at `stage.at`. (Before, the root bone sat at (0, 0), so the origin was
    measured from the art's centre and the foot landed ~172 px off.)"""
    from an.stage.rig import Attachment, Skin

    folder = tmp_path / "props" / "tree"
    (folder / "parts").mkdir(parents=True)
    (folder / "parts" / "tree.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" '
        'height="1024"><rect x="500" y="200" width="24" height="800" fill="#000"/></svg>',
        encoding="utf-8",
    )
    tree = PropDescriptor(
        name="tree",
        origin=(512, 1000),
        skins={"default": Skin(slots={"body": {"body": Attachment(path="parts/tree.svg")}})},
    )
    (folder / "prop.json").write_text(tree.model_dump_json(), encoding="utf-8")
    scene = compile_shot(_shot("tree", at=(0.0, 0.0)), mall={"props": PropsStore(tmp_path / "props")})
    (entity,) = [n for n in scene.scene.children if n.name == "p"]
    (body,) = entity.children
    k = 345.0 / 1024
    art_top = body.transform.y - body.visual.height * body.visual.anchor_y
    assert art_top + 1000 * k == pytest.approx(0.0)  # the foot, at stage.at
    assert body.transform.x == pytest.approx(0.0)
