"""Mirror states (an#819): art drawn mirrored shows its declared mirror drawing.

The fixture is the core corpus's ``prop_swap`` lamp (one swap set ``lamp`` with
keys ``off`` and ``on`` on its ``lamp/body`` slot), its art given a
``metadata`` block here; ``on`` stands in for ``off``'s mirror drawing.
Compiled only, never rendered.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from an.ir.validate import validate_semantic
from an.project import load
from an.stage.compile import compile_shot
from an.stage.mirror_states import MirrorStatesError, mirror_states_of
from an.stage.serialize import to_dict

ROOT = Path(__file__).resolve().parents[1]
LAMP = ROOT / "misc" / "bench" / "corpus" / "prop_swap"
AUTHORED_SET = """- kind: set
  target: lamp/body
  property: lamp
  value: 'on'
  at: 0.25"""
FLIP = """- kind: tween
  target: lamp
  property: scale_x
  from: 0.55
  to: -0.55
  duration: 0.2
  start: 0.1"""


def _lamp(tmp_path: Path, *, metadata=None, actions: str = FLIP):
    root = Path(shutil.copytree(LAMP, tmp_path / "p"))
    art = root / "assets" / "props" / "lamp" / "prop.json"
    doc = json.loads(art.read_text())
    if metadata is not None:
        doc["metadata"] = metadata
    art.write_text(json.dumps(doc))
    scene = root / "scene.md"
    scene.write_text(scene.read_text().replace(AUTHORED_SET, actions))
    return load(root)


def _compile(project):
    shot = project.scene.timeline[0]
    return compile_shot(shot, mall=project.mall, fps=24, width=320, height=240)


def _mirror_channel(doc):
    found = [
        (c.target, c.property, [(round(k.time, 4), k.value) for k in c.keyframes])
        for name, clip in doc.animations.items()
        if name.startswith("__mirror__")
        for c in clip.channels
    ]
    return found


def test_a_drawing_mirrored_by_hand_shows_its_mirror_state(tmp_path):
    """The lamp flips through zero at 0.2 s: from the first frame it is drawn
    mirrored (0.208 s at 24 fps), it shows `off`'s mirror drawing."""
    doc = _compile(_lamp(tmp_path, metadata={"mirror_states": {"off": "on"}}))
    assert _mirror_channel(doc) == [("lamp/body", "lamp", [(0.0, "off"), (0.2083, "on")])]
    assert doc.timeline.tracks[-1].target_root == "__mirror__"


def test_an_authored_swap_is_kept_and_mirrored_too(tmp_path):
    """The channel is computed from the timeline as authored: the lamp is set
    `on` at 0.25 s while mirrored, so it shows `on`'s mirror state from then."""
    actions = FLIP + "\n" + AUTHORED_SET
    doc = _compile(_lamp(tmp_path, metadata={"mirror_states": {"off": "on", "on": "off"}}, actions=actions))
    assert _mirror_channel(doc) == [
        ("lamp/body", "lamp", [(0.0, "off"), (0.2083, "on"), (0.25, "off")])
    ]


def test_art_never_mirrored_compiles_byte_for_byte_as_before(tmp_path):
    plain = to_dict(_compile(_lamp(tmp_path / "a", actions=AUTHORED_SET)))
    declared = to_dict(
        _compile(_lamp(tmp_path / "b", metadata={"mirror_states": {"off": "on"}}, actions=AUTHORED_SET))
    )
    assert declared == plain


def test_a_mirror_state_outside_the_set_is_refused(tmp_path):
    with pytest.raises(MirrorStatesError, match="'gone'"):
        _compile(_lamp(tmp_path, metadata={"mirror_states": {"off": "gone"}}))


def test_a_malformed_declaration_is_refused():
    with pytest.raises(MirrorStatesError, match="maps a swap-set key"):
        mirror_states_of({"metadata": {"mirror_states": ["off", "on"]}})


def _lettering(project):
    report = validate_semantic(
        project.scene, available_props=project.mall["props"], only={"lettering"}
    )
    return [f for f in report.findings]


def test_lettering_drawn_mirrored_without_a_mirror_state_is_a_warning(tmp_path):
    (f,) = _lettering(_lamp(tmp_path, metadata={"lettering": True}))
    assert f.severity == "warning"
    assert "'lamp' has lettering and is drawn mirrored from 0.21 s" in f.description
    assert "drawing 'off'" in f.description


def test_lettering_with_its_mirror_state_or_never_mirrored_is_fine(tmp_path):
    declared = {"lettering": True, "mirror_states": {"off": "on"}}
    assert _lettering(_lamp(tmp_path / "a", metadata=declared)) == []
    assert _lettering(_lamp(tmp_path / "b", metadata={"lettering": True}, actions=AUTHORED_SET)) == []


def test_an_item_carried_by_a_carrier_that_turns_round_shows_its_mirror_state(tmp_path):
    """The case of the issue: the hold layer mirrors what a hand holds with its
    carrier (the item's own channels are not negative before the turn, its
    world is after), so the stick shows its mirror drawing from the turn on."""
    import warnings

    from tests._hold_fixture import make_project, scene

    actions = """- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}
- {kind: tween, target: fig, property: scale_x, from: 1.0, to: -1.0, duration: 0.4, start: 2.0}"""
    root = tmp_path / "p"
    make_project(root, scene(actions))
    art = root / "assets" / "props" / "stick" / "prop.json"
    doc = json.loads(art.read_text())
    drawings = doc["skins"]["default"]["slots"]["body"]
    drawings["flipped"] = dict(drawings["body"])
    doc["asset_sets"] = {"label": {"plain": "body", "flipped": "flipped"}}
    doc["metadata"] = {"mirror_states": {"plain": "flipped"}, "lettering": True}
    art.write_text(json.dumps(doc))
    project = load(root)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        compiled = compile_shot(project.scene.timeline[0], project.mall, fps=24, width=640, height=480)
    [(target, prop, keys)] = _mirror_channel(compiled)
    assert (target, prop) == ("stick/body", "label")
    assert keys[0] == (0.0, "plain") and keys[1][1] == "flipped" and len(keys) == 2
    assert 2.2 < keys[1][0] <= 2.25, keys  # the first frame after the turn passes 0
    report = validate_semantic(
        project.scene, available_props=project.mall["props"], only={"lettering"}
    )
    assert report.findings == []
