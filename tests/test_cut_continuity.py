"""Placement continuity across a cut (an#394): an entity in two consecutive stage
shots that jumps (x, y, size) without the next shot saying so is a warning."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from an.ir.schema import AssetRef, Shot
from an.ir.validate import validate_semantic
from an.project import load

ROOT = Path(__file__).resolve().parents[1]
LAMP = ROOT / "misc" / "bench" / "corpus" / "prop_swap"


def _two_shots(tmp_path: Path, *, second_at=(0.0, 90.0), second_scale=0.55, actions=()):
    root = Path(shutil.copytree(LAMP, tmp_path / "p"))
    project = load(root)
    first = project.scene.timeline[0]
    lamp = first.entities[0].model_dump()
    second = Shot.model_validate(
        {
            "id": "second",
            "renderer": first.renderer,
            "duration": 0.5,
            "entities": [{**lamp, "stage": {"at": list(second_at), "scale": second_scale}}],
            "actions": list(actions),
        }
    )
    scene = project.scene.model_copy(update={"timeline": [first, second]})
    return validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
    )


def _jumps(report) -> list[str]:
    return [f.description for f in report.findings if "jumps across the cut" in f.description]


def test_the_same_placement_across_the_cut_says_nothing(tmp_path):
    assert _jumps(_two_shots(tmp_path)) == []


def test_a_jump_names_both_values(tmp_path):
    (msg,) = _jumps(_two_shots(tmp_path, second_at=(20.0, 90.0)))
    assert "'lamp'" in msg and "x 0 → 20" in msg and "'prop_swap'" not in msg


def test_a_size_jump_is_a_jump_too(tmp_path):
    (msg,) = _jumps(_two_shots(tmp_path, second_scale=0.8))
    assert "scale_x" in msg and "scale_y" in msg


def test_an_opening_set_makes_it_deliberate(tmp_path):
    set_x = {"kind": "set", "target": "lamp", "property": "x", "value": 20.0, "at": 0.0}
    assert _jumps(_two_shots(tmp_path, second_at=(20.0, 90.0), actions=[set_x])) == []
