"""The placeholder rig's limbs pivot at their joint, not their centre (an#173).

A rotation of `charlie/right_arm` used to spin the rect about its middle: the
hand swung up while the top of the arm swung down into the torso, so `point`
and every other arm rotation disagreed with a descriptor rig's bone. The rig
builder now places each limb NODE at its joint and hangs the rect from it.

Asserted on the COMPILED document through the spec's own `screen_position`,
so no browser is needed:

- the joint (the rect's top-centre) does not move when the limb rotates;
- at rest the rect still covers the pixels it always did (the layout is
  unchanged; only the pivot moved);
- the `point` preset, played on the arm, keeps the shoulder put at its apex.

MUTATION: set `_LIMB_PIVOT_Y` back to `_DFLT_PIVOT_Y` in `compile.py` — the
joint assertions go red (the arm's top edge sweeps by tens of pixels).
"""

from __future__ import annotations

import math
import warnings

import pytest

from an.adapters.cutout.compile import (
    _PLACEHOLDER_PART_GEOMETRY,
    compile_shot,
)
from an.adapters.cutout.timeline import (
    evaluate_timeline,
    screen_position,
    timeline_from_scene,
)
from an.ir.schema import AssetRef, Shot
from an.motion import DFLT_POINT_ANGLE, point

LIMBS = ("left_arm", "right_arm", "left_leg", "right_leg")
ANGLES = (0.4, -1.3, 1.9)
#: Sub-pixel: the composition is exact float arithmetic, so this is generous.
TOL = 1e-6


def _scene(actions=()):
    shot = Shot(
        id="s",
        duration=4.0,
        entities=[AssetRef(kind="character", id="c", store="characters", ref="c-v1")],
        actions=list(actions),
    )
    mall = {"characters": {"c-v1": {"parts": ["head", "torso", *LIMBS]}}}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(shot, mall)


def _node(scene, name):
    return next(c for c in scene.scene.children[0].children if c.name == name)


def _close(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1]) < TOL


@pytest.mark.parametrize("limb", LIMBS)
def test_the_joint_stays_put_under_rotation(limb):
    scene = _scene()
    path = f"c/{limb}"
    # The pivot IS the rect's top edge (the shoulder / hip): anchor_y == 0.
    assert _node(scene, limb).visual.anchor_y == 0.0
    joint_local = (0.0, 0.0)
    rest = screen_position(scene, path, point=joint_local)
    for angle in ANGLES:
        pose = {(path, "rotation"): angle}
        assert _close(screen_position(scene, path, pose=pose, point=joint_local), rest), (
            f"{limb} joint moved under rotation {angle}"
        )


@pytest.mark.parametrize("limb", LIMBS)
def test_the_far_end_does_swing(limb):
    """The guard is not vacuous: the free end of the limb moves a lot."""
    scene = _scene()
    path = f"c/{limb}"
    h = _node(scene, limb).visual.height
    tip = (0.0, h)
    at_rest = screen_position(scene, path, point=tip)
    turned = screen_position(scene, path, pose={(path, "rotation"): 1.0}, point=tip)
    assert math.hypot(turned[0] - at_rest[0], turned[1] - at_rest[1]) > h / 2


@pytest.mark.parametrize("limb", LIMBS)
def test_at_rest_the_rect_covers_the_layout_pixels(limb):
    """Moving the pivot must not move the picture: the rect's centre is the
    layout's (x, y), within the torso-relative frame the rig is built in."""
    scene = _scene()
    geom = _PLACEHOLDER_PART_GEOMETRY[limb]
    node = _node(scene, limb)
    centre_local = (0.0, node.visual.height * (0.5 - node.visual.anchor_y))
    centre = screen_position(scene, f"c/{limb}", point=centre_local)
    origin = screen_position(scene, "c")
    expected = (origin[0] + geom["x"], origin[1] + geom["y"])
    assert _close(centre, expected)


def test_point_preset_keeps_the_shoulder_at_the_shoulder():
    scene = _scene([point("c/right_arm")])
    tl = timeline_from_scene(scene)
    path = "c/right_arm"
    node = _node(scene, "right_arm")
    joint = (0.0, -node.visual.height * node.visual.anchor_y)
    rest = screen_position(scene, path, point=joint)
    # sample across the whole gesture, including the apex
    apex_seen = False
    for i in range(0, 41):
        pose = evaluate_timeline(tl, i * 0.05)
        assert _close(screen_position(scene, path, pose=pose, point=joint), rest)
        if abs(pose.get((path, "rotation"), 0.0) - DFLT_POINT_ANGLE) < 1e-3:
            apex_seen = True
    assert apex_seen, "the sampling never reached the preset's apex"
