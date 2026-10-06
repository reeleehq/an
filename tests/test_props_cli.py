"""``an props validate`` takes a key or a path (an#459, end-user test 3 finding 8)."""

from __future__ import annotations

from pathlib import Path

from an.props_cli import validate

PROPS = Path(__file__).resolve().parents[1] / "misc/bench/corpus/rig_chain/assets/props"


def test_a_key_a_folder_and_a_prop_json_reach_the_same_prop(monkeypatch):
    by_key = validate("arm_lamp", out_dir=str(PROPS))
    assert by_key.startswith("arm_lamp: ")
    assert validate(str(PROPS / "arm_lamp")) == by_key
    assert validate(str(PROPS / "arm_lamp" / "prop.json")) == by_key
    monkeypatch.chdir(PROPS.parent.parent)  # the project root: assets/props/<key>
    assert validate("assets/props/arm_lamp") == by_key == validate("arm_lamp")


def test_a_name_that_is_neither_says_what_it_takes(tmp_path):
    out = validate("assets/props/nope", out_dir=str(tmp_path))
    assert out.startswith("assets/props/nope: FAILED")
    assert "pass a prop's KEY" in out and str(tmp_path) in out
