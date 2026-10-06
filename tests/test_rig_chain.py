"""Nested chains, ``nesting: bones`` (an#340).

In the default ``flat`` nesting a slot nests only under its own bone's primary
slot, so limbs are siblings of the torso and a forearm cannot follow its upper
arm. ``nesting: bones`` nests a slot under the nearest ancestor bone's primary
slot, to any depth: forward kinematics.

The fixture is the core corpus's ``rig_chain`` scene: a desk-lamp arm,
base -> upper -> fore, with a shade NESTED on the forearm's bone.
"""

from __future__ import annotations

import copy
import json
import math
import shutil
from pathlib import Path

import pytest

from an.ir.schema import AssetRef, Meta, SceneIR, Shot, StagePlacement
from an.stage.compile import CutoutCompileError, compile_shot
from an.stage.rig import (
    RIG_HIERARCHY,
    rig_affordances,
    rig_problems,
    slot_node_paths,
    slot_parent_chain,
)
from an.stage.timeline import screen_position
from an.stage.tree import paths
from an.stores.props import PropsStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "misc" / "bench" / "corpus" / "rig_chain" / "assets" / "props"
K = 345.0 / 400.0  # SCENE_PX_PER_VIEW_BOX over the fixture's view_box height


def _doc() -> dict:
    return json.loads((FIXTURE / "arm_lamp" / "prop.json").read_text(encoding="utf-8"))


def _mall(tmp_path, doc: dict | None = None):
    shutil.copytree(FIXTURE, tmp_path / "props")
    if doc is not None:
        (tmp_path / "props" / "arm_lamp" / "prop.json").write_text(
            json.dumps(doc), encoding="utf-8"
        )
    return {"props": PropsStore(tmp_path / "props")}


def _shot() -> Shot:
    return Shot(
        id="s1",
        renderer="cutout",
        duration=0.5,
        entities=[
            AssetRef(
                kind="prop", id="lamp", store="props", ref="arm_lamp", stage=StagePlacement(at=(0.0, 0.0))
            )
        ],
    )


def test_bones_nesting_builds_the_chain_and_flat_keeps_the_siblings(tmp_path):
    scene = compile_shot(_shot(), mall=_mall(tmp_path))
    assert {"lamp/base/upper/fore/shade"} <= paths(scene.scene)
    flat = _doc()
    flat.pop("nesting")
    assert slot_node_paths(flat) == {"base": "base", "upper": "upper", "fore": "fore", "shade": "fore/shade"}
    assert slot_node_paths(_doc())["shade"] == "base/upper/fore/shade"


def _world(scene, path, point=(0.0, 0.0)):
    return screen_position(scene, path, point=point)


def test_a_chain_is_forward_kinematics(tmp_path):
    """Each part sits at its BONE in its parent's rotated frame: the forearm's
    root is the upper arm's tip, wherever the upper arm turns, and the shade
    is at the forearm's tip (its own attachment offset, nothing inherited)."""
    scene = compile_shot(_shot(), mall=_mall(tmp_path))
    upper_rot = math.radians(30)
    tip = _world(scene, "lamp/base/upper", point=(0.0, -150 * K))
    assert _world(scene, "lamp/base/upper/fore") == pytest.approx(tip)
    joint = _world(scene, "lamp/base/upper")
    assert tip[0] - joint[0] == pytest.approx(150 * K * math.sin(upper_rot))
    fore_tip = _world(scene, "lamp/base/upper/fore", point=(0.0, -120 * K))
    assert _world(scene, "lamp/base/upper/fore/shade") == pytest.approx(fore_tip)


def test_a_chain_does_not_inherit_its_parents_attachment_offset(tmp_path):
    doc = _doc()
    doc["skins"]["default"]["slots"]["upper"]["upper"]["x"] = 40.0  # the drawing, not the joint
    scene = compile_shot(_shot(), mall=_mall(tmp_path, doc))
    (lamp,) = [n for n in scene.scene.children if n.name == "lamp"]
    upper = lamp.children[0].children[0]
    fore = upper.children[0]
    assert upper.transform.x == pytest.approx(40 * K)
    assert fore.transform.x == pytest.approx(-40 * K), "the joint stays at the bone"


def test_a_rest_rotation_composes_through_the_chain(tmp_path):
    scene = compile_shot(_shot(), mall=_mall(tmp_path))
    (lamp,) = [n for n in scene.scene.children if n.name == "lamp"]
    upper = lamp.children[0].children[0]
    fore = upper.children[0]
    shade = fore.children[0]
    assert upper.transform.rotation == pytest.approx(math.radians(30))
    assert fore.transform.rotation == pytest.approx(math.radians(-70))  # LOCAL to the upper arm
    assert shade.transform.rotation == 0.0  # on the forearm's bone: it turns WITH the forearm


def test_a_chain_drawn_around_its_parent_is_painted_from_a_global_order(tmp_path):
    from an.ir.validate import validate_semantic

    doc = _doc()
    for slot in doc["slots"]:
        if slot["name"] == "fore":
            # Under the upper arm (1) while the shade nested on it stays at 3:
            # the forearm's subtree would have to wrap around the upper arm,
            # which no sorting of one container can do (an#403).
            slot["draw_order"] = 0
    mall = _mall(tmp_path, doc)
    # Since an#430 the stage paints such a rig from a global part order
    # instead of refusing it (an engine without one still refuses it, by its
    # capability: tests/test_rig_interleave.py).
    scene = compile_shot(_shot(), mall=mall)
    (lamp,) = [n for n in scene.scene.children if n.name == "lamp"]
    assert lamp.paint_order[:3] == ["base", "base/upper/fore", "base/upper"]  # forearm under the upper arm
    report = validate_semantic(SceneIR(meta=Meta(), timeline=[_shot()]), available_props=mall["props"])
    assert report.passed


def test_a_bone_cycle_is_a_closed_linkage_and_is_refused(tmp_path):
    doc = _doc()
    for bone in doc["bones"]:
        if bone["name"] == "base":
            bone["parent"] = "fore"
    assert any("cycle" in p for p in rig_problems(doc))
    with pytest.raises(CutoutCompileError, match="cycle"):
        compile_shot(_shot(), mall=_mall(tmp_path, doc))


def test_skip_slots_drops_a_slot_and_what_hangs_from_it(tmp_path):
    from an.stage.props import PROP_DOCUMENT_KIND, PropDescriptor
    from an.stage.rig import build_rig_subtree

    entity = _shot().entities[0]
    node = build_rig_subtree(
        entity,
        _doc(),
        textures={},
        descriptor_model=PropDescriptor,
        document_kind=PROP_DOCUMENT_KIND,
        skip_slots={"fore"},
    )
    assert paths(node) == {"base", "base/upper"}  # the subtree root is not indexed


def test_flat_nesting_is_unchanged():
    """The default rule is the old one: a slot nests under its own bone's
    primary slot and nothing else, whatever the bone graph says."""
    flat = copy.deepcopy(_doc())
    flat.pop("nesting")
    assert slot_parent_chain(flat) == {"base": None, "upper": None, "fore": None, "shade": "fore"}


def test_the_prop_analyser_derives_rig_hierarchy():
    from an.capabilities import analyse, missing
    from an.stage.props import register_prop_analyser

    register_prop_analyser()  # what the library does when it loads the genres
    profile, analysers = analyse("prop", _doc(), {})
    assert profile[RIG_HIERARCHY] == {
        "keys": ["base", "fore", "shade", "upper"],
        "count": 3,  # three BONES; the shade on the forearm's bone adds no joint
        "chains": [["base", "upper", "fore", "shade"]],
    }
    assert "prop" in analysers
    assert not missing(profile, ["rig.hierarchy>=3", "rig.hierarchy:fore"])
    assert missing(profile, ["rig.hierarchy>=4"])
    flat = _doc()
    flat.pop("nesting")
    assert rig_affordances(flat) == {}


def test_validate_prop_blocks_a_structural_problem_and_advises_on_order(tmp_path):
    from an.stage.prop_validate import validate_prop

    folder = tmp_path / "props" / "arm_lamp"
    shutil.copytree(FIXTURE / "arm_lamp", folder)
    assert validate_prop(folder).passed
    doc = _doc()
    doc["slots"].append({"name": "ghost", "bone": "nope", "draw_order": 9, "attachment": "x"})
    for slot in doc["slots"]:
        if slot["name"] == "fore":
            slot["draw_order"] = 0
    (folder / "prop.json").write_text(json.dumps(doc), encoding="utf-8")
    report = validate_prop(folder)
    assert not report.passed
    severities = {f.description.split(": ", 1)[1][:20]: f.severity for f in report.findings if "#rig" in f.ir_path}
    assert "error" in severities.values() and "warning" in severities.values()


def test_an_props_cli_is_wired():
    from an.tools import _dispatch_namespaces

    names = [f.__name__ for f in _dispatch_namespaces["props"]]
    assert names == ["validate", "contract"]


def test_a_chain_straddling_an_unrelated_part_is_painted_from_a_global_order(tmp_path):
    """Depth-first painting would move a whole chain past a part ordered
    between its members (the review's leg-over-the-face case); since an#430
    the rig is painted from one global part order instead."""
    from an.stage.rig import chain_draw_order_problems

    doc = _doc()
    doc["bones"].append({"name": "cord", "x": 100, "y": 376})
    doc["slots"].append({"name": "cord", "bone": "cord", "draw_order": 2, "attachment": "cord"})
    doc["skins"]["default"]["slots"]["cord"] = {"cord": {"path": "parts/base.svg"}}
    for slot in doc["slots"]:  # upper 1, cord 2, fore 3: the chain straddles the cord
        slot["draw_order"] = {"base": 0, "upper": 1, "fore": 3, "shade": 4}.get(slot["name"], slot["draw_order"])
    assert chain_draw_order_problems(doc)
    # Painted from a global part order since an#430, not refused.
    scene = compile_shot(_shot(), mall=_mall(tmp_path / "a", doc))
    (lamp,) = [n for n in scene.scene.children if n.name == "lamp"]
    assert lamp.paint_order == ["base", "base/upper", "cord", "base/upper/fore", "base/upper/fore/shade"]
    doc["slots"][-1]["draw_order"] = 5  # after the chain: the tree's own order
    assert not chain_draw_order_problems(doc)
    scene = compile_shot(_shot(), mall=_mall(tmp_path / "b", doc))
    (lamp,) = [n for n in scene.scene.children if n.name == "lamp"]
    assert lamp.paint_order is None


def test_a_posed_bone_with_no_slot_in_a_chain_is_refused(tmp_path):
    """Its node does not exist, so its rotation would be dropped silently."""
    doc = _doc()
    for bone in doc["bones"]:
        if bone["name"] == "fore":
            bone["parent"] = "elbow"
    doc["bones"].append({"name": "elbow", "parent": "upper", "y": -150, "rotation_deg": -70})
    with pytest.raises(CutoutCompileError, match="carries no slot"):
        compile_shot(_shot(), mall=_mall(tmp_path, doc))


def test_a_part_whose_parent_was_not_built_is_reported(tmp_path):
    mall = _mall(tmp_path)
    (tmp_path / "props" / "arm_lamp" / "parts" / "upper.svg").unlink()
    scene = compile_shot(_shot(), mall=mall)
    orphaned = {r.id for r in scene.asset_resolution if r.resolved == "orphaned"}
    assert orphaned == {"lamp/fore", "lamp/shade"}
    assert all(r.fallback for r in scene.asset_resolution if r.resolved == "orphaned")


def test_the_legacy_face_rule_keeps_a_part_on_a_child_bone_of_the_head():
    """A genre that passes no `skip_slots` gets the old rule: the slots ON the
    head bone, in either nesting, never a hat on a bone hung from the head."""
    from types import SimpleNamespace as NS

    from an.stage.rig import _legacy_baked_face_slots, slot_parent_chain

    for nesting in ("flat", "bones"):
        desc = NS(
            face_overlay=False,
            nesting=nesting,
            bones=[NS(name="head", parent=None), NS(name="hat", parent="head")],
            slots=[NS(name="head", bone="head"), NS(name="mouth", bone="head"), NS(name="hat", bone="hat")],
        )
        assert _legacy_baked_face_slots(desc, slot_parent_chain(desc)) == {"mouth"}


# ------------------------------------------------------- free draw order (an#403)


def _nodes(node, out=None):
    out = {} if out is None else out
    out[node.name] = node
    for child in node.children:
        _nodes(child, out)
    return out


def test_a_chain_behind_the_part_it_hangs_from_is_drawn_in_its_order(tmp_path):
    """The usual cut-out layout: the far arm BEHIND the torso it nests under.
    R3 refused it; the base's container now sorts its own drawing after the
    arm, and nothing else is touched."""
    from an.stage.rig import chain_draw_order_problems

    doc = _doc()
    for slot in doc["slots"]:
        slot["draw_order"] = {"upper": 1, "fore": 2, "shade": 3, "base": 4}[slot["name"]]
    assert chain_draw_order_problems(doc) == []
    scene = compile_shot(_shot(), mall=_mall(tmp_path, doc))
    nodes = _nodes(scene.scene)
    assert nodes["base"].visual.z_index == 2 and nodes["upper"].z_index == 1
    stamped = {n for n, node in nodes.items() if node.z_index is not None or (node.visual and node.visual.z_index is not None)}
    assert stamped == {"base", "upper"}, stamped


def test_equal_draw_orders_are_free_so_a_chain_can_swap_past_its_twin(tmp_path):
    """The `gale` layout: both arms at 2, a hand at 3 under the LEFT arm. In
    tree order the hand would paint before the right arm; equal orders state
    no order between the arms, so the right one is sorted first (it was
    refused while ties were broken by name)."""
    from types import SimpleNamespace as NS

    from an.stage.rig import _painted, chain_draw_order_problems, chain_paint_order

    rig = NS(
        nesting="bones",
        bones=[NS(name="torso", parent=None), NS(name="arm_l", parent="torso"),
               NS(name="arm_r", parent="torso"), NS(name="hand_l", parent="arm_l")],
        slots=[NS(name="torso", bone="torso", draw_order=1), NS(name="arm_l", bone="arm_l", draw_order=2),
               NS(name="arm_r", bone="arm_r", draw_order=2), NS(name="left_hand", bone="hand_l", draw_order=3)],
    )
    assert chain_draw_order_problems(rig) == []
    assert _painted(chain_paint_order(rig)) == ["torso", "arm_r", "arm_l", "left_hand"]


def test_a_chain_already_in_tree_order_carries_no_index(tmp_path):
    """Byte identity: the committed fixture paints depth first in its declared
    order, so nothing is stamped and the document is what it was."""
    from an.stage.serialize import to_dict

    doc = json.dumps(to_dict(compile_shot(_shot(), mall=_mall(tmp_path))))
    assert "z_index" not in doc


def test_the_runtime_sorts_only_a_container_with_an_index():
    """`applyPaintOrder`, lifted verbatim from runtime.js: an indexed child gets
    its index, an unindexed one its predecessor's (so the stable sort keeps it
    right after it), and a container with no index is never made sortable."""
    from tests._node import run_node

    src = (ROOT / "an" / "stage" / "runtime" / "runtime.js").read_text(encoding="utf-8")
    start = src.index("function applyPaintOrder(")
    body = src[start : src.index("\n    }", start) + len("\n    }")]
    script = body + """
    const mk = (z) => (z === undefined ? {} : {_anZ: z});
    const a = {children: [mk(), mk(2), mk(), mk(1)]};
    applyPaintOrder(a);
    const b = {children: [mk(), mk()]};
    applyPaintOrder(b);
    console.log(JSON.stringify([a.sortableChildren, a.children.map(c => c.zIndex),
                                b.sortableChildren === undefined]));
    """
    proc = run_node(script)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == [True, [0, 2, 2, 1], True]
