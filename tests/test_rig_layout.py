"""The default rig's parts land where a body has them — asserted on the COMPILED
document, so no browser is needed (an#168).

A character synthesized offline (`new_character(use_dicebear=False)`, what every
demo uses) drew its mouth on the torso and its legs detached a whole leg length
below the body. Three independent defects composed into that picture: the leg
bones sat at the feet while the leg art hangs from its top edge, the face
offsets were measured from the head's centre while the head bone is the neck,
and the factory wrote its head a quarter of the size the face layout is drawn
for. Each assertion below fails on exactly one of them.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from an.adapters.cutout.compile import (
    SCENE_PX_PER_VIEW_BOX,
    _bone_positions,
    _rig_origin,
    compile_shot,
)
from an.adapters.cutout.serialize import to_dict
from an.characters import new_character
from an.characters.schema import CharacterDescriptor
from an.ir.schema import AssetRef, Shot
from an.project import init, load

FACE_PARTS = ("left_eye", "right_eye", "left_brow", "right_brow", "mouth")
#: Scene pixels. Loose enough for float rounding, far tighter than any defect
#: (the detached legs were ~98 px off, the mouth ~13 px below the neck).
TOL_PX = 0.5


@pytest.fixture(scope="module")
def compiled():
    with tempfile.TemporaryDirectory() as d:
        root = init(Path(d) / "p")
        desc_path = new_character(
            root / "assets" / "characters", name="c", seed="c", use_dicebear=False
        )
        desc = CharacterDescriptor.model_validate_json(desc_path.read_text("utf-8"))
        shot = Shot(
            id="s",
            renderer="cutout",
            duration=1.0,
            entities=[AssetRef(kind="character", id="c", store="characters", ref="c")],
        )
        doc = to_dict(compile_shot(shot, mall=load(root).mall, fps=24, strict_assets=True))
    (char,) = doc["scene"]["children"]
    boxes = {}

    def walk(node, ox=0.0, oy=0.0):
        t, v = node["transform"], node["visual"]
        x, y = ox + t["x"], oy + t["y"]
        top = y - v["anchor_y"] * v["height"]
        left = x - v["anchor_x"] * v["width"]
        boxes[node["name"]] = (left, top, left + v["width"], top + v["height"])
        for kid in node.get("children") or []:
            walk(kid, x, y)

    for part in char["children"]:
        walk(part)
    bones = _bone_positions(desc)
    k = SCENE_PX_PER_VIEW_BOX / desc.view_box[3]
    ground = (bones["root"][1] - _rig_origin(bones)[1]) * k
    return boxes, ground


def _centre(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


@pytest.mark.parametrize("part", FACE_PARTS)
def test_face_parts_sit_on_the_face_above_the_neck(compiled, part):
    boxes, _ = compiled
    cx, cy = _centre(boxes[part])
    left, top, right, bottom = boxes["head"]
    assert left < cx < right and top < cy < bottom, f"{part} is off the head"
    assert cy < boxes["torso"][1], f"{part} is drawn on the torso, below the neck"


@pytest.mark.parametrize("leg", ("leg_l", "leg_r"))
def test_legs_hang_from_the_hip_to_the_ground(compiled, leg):
    boxes, ground = compiled
    torso_bottom = boxes["torso"][3]
    assert abs(boxes[leg][1] - torso_bottom) <= TOL_PX, "leg detached from the torso"
    assert abs(boxes[leg][3] - ground) <= TOL_PX, "leg does not reach the ground"
