"""The `an` skill's planes-of-movement reference is checked, not only read (an#505).

Every fenced YAML example in ``.claude/skills/an/references/planes-of-movement.md``
validates against the scene schema, and with nothing the schema does not know:
the IR takes unknown keys (``extra="allow"``, for schema evolution), so a typo
in an example would otherwise pass as data and teach an agent a field that does
nothing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel

from an.ir.schema import Shot, World

REFERENCE = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "an"
    / "references"
    / "planes-of-movement.md"
)
#: How each example's top-level key is read: the world, or a shot's actions.
READERS = {
    "world": World.model_validate,
    "actions": lambda actions: Shot.model_validate(
        {"id": "example", "duration": 10.0, "actions": actions}
    ),
}


def _examples() -> list[dict]:
    text = REFERENCE.read_text(encoding="utf-8")
    return [
        yaml.safe_load(m.group(1))
        for m in re.finditer(r"```ya?ml[^\n]*\n(.*?)```", text, re.S)
    ]


def _unknown_keys(value: Any, where: str = "") -> list[str]:
    """Every key a model kept as an extra, anywhere inside ``value``."""
    if isinstance(value, BaseModel):
        out = [f"{where}/{k}" for k in (value.model_extra or {})]
        for name in type(value).model_fields:
            out += _unknown_keys(getattr(value, name), f"{where}/{name}")
        return out
    if isinstance(value, dict):
        return [u for k, v in value.items() for u in _unknown_keys(v, f"{where}/{k}")]
    if isinstance(value, (list, tuple)):
        return [u for i, v in enumerate(value) for u in _unknown_keys(v, f"{where}/{i}")]
    return []


def test_the_reference_has_its_examples():
    assert [next(iter(e)) for e in _examples()] == ["world", "actions"]


@pytest.mark.parametrize("example", _examples(), ids=lambda e: next(iter(e)))
def test_each_example_validates_with_no_unknown_key(example):
    ((key, value),) = example.items()
    model = READERS[key](value)
    assert _unknown_keys(model) == []


def test_an_unknown_key_in_an_example_would_be_caught():
    world = dict(_examples()[0]["world"])
    world["frames"] = {**world["frames"], "vehicle": {"movin": {"speed": 1}}}
    assert _unknown_keys(World.model_validate(world)) == ["/frames/vehicle/movin"]
