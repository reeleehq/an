"""`an validate` agrees with compile on swaps set on a WHOLE character (an#201).

An entity-level swap (``{kind: set, target: ned, property: view, value: side}``,
an#197) is fanned out by the compiler to every slot the set projects onto. Two
places validate judged it by the per-node rule instead, and passed a shot that
compile refuses:

1. a ``tween`` of the swap on the character root — compile does not fan a tween
   out, and raises naming the nodes that carry the set;
2. a key whose art is missing on ONE of those slots — validate asked whether
   ANY slot had it, while compile under ``--strict-assets`` needs every one.

Each test checks both verdicts, so the two cannot drift apart again.
"""

from __future__ import annotations

import shutil
import tempfile
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.characters import new_character
from an.ir.schema import AssetRef, Meta, SceneIR, SetAction, Shot, TweenAction
from an.ir.validate import validate_semantic
from an.project import init, load


@pytest.fixture(scope="module")
def project():
    with tempfile.TemporaryDirectory() as d:
        root = init(Path(d) / "p")
        new_character(root / "assets" / "characters", name="ned", seed="ned", use_dicebear=False)
        yield root


def _shot(*actions) -> Shot:
    return Shot(
        id="s",
        renderer="cutout",
        duration=1.0,
        entities=[AssetRef(kind="character", id="ned", store="characters", ref="ned")],
        actions=list(actions),
    )


def _errors(root, shot) -> list[str]:
    scene = SceneIR(meta=Meta(title="t", duration=shot.duration), timeline=[shot])
    report = validate_semantic(scene, available_characters=load(root).mall["characters"])
    return [f.description for f in report.findings if f.severity == "error"]


def _compile(root, shot, *, strict=True):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(shot, mall=load(root).mall, fps=24, strict_assets=strict)


def test_a_tween_of_a_swap_on_the_character_root_is_refused_by_both(project):
    shot = _shot(TweenAction(target="ned", property="view", to_value="side", duration=0.2))
    with pytest.raises(CutoutCompileError, match="resolves on"):
        _compile(project, shot)
    (msg,) = _errors(project, shot)
    assert "`tween` of 'view' on the whole character 'ned'" in msg
    assert "ned/head" in msg and "ned/torso" in msg


def test_a_set_on_the_root_still_validates_and_compiles(project):
    shot = _shot(SetAction(target="ned", property="view", value="side", at=0.0))
    assert _errors(project, shot) == []
    _compile(project, shot)


def test_art_missing_on_one_slot_of_a_whole_character_swap_is_an_error(project, tmp_path):
    root = init(tmp_path / "q")
    shutil.copytree(
        project / "assets" / "characters" / "ned", root / "assets" / "characters" / "ned"
    )
    (root / "assets" / "characters" / "ned" / "parts" / "head_side.svg").unlink()
    shot = _shot(SetAction(target="ned", property="view", value="side", at=0.0))
    with pytest.raises(CutoutCompileError):
        _compile(root, shot, strict=True)
    (msg,) = _errors(root, shot)
    assert "head_side.svg" in msg and "'side'" in msg
    # The torso still has its side art, so a key that no slot misses is fine.
    assert _errors(root, _shot(SetAction(target="ned", property="view", value="back", at=0.0))) == []


def test_a_slot_with_none_of_the_set_s_art_is_not_a_target(tmp_path):
    """Review of an#201: compile fans a root `set` out only to slots where some
    art of the set resolved; a slot whose only attachment for the set is missing
    receives nothing, so validate must not count it as missing art."""
    import json

    root = init(tmp_path / "q")
    chars = root / "assets" / "characters"
    new_character(chars, name="ned", seed="ned", use_dicebear=False)
    doc_path = chars / "ned" / "character.json"
    doc = json.loads(doc_path.read_text("utf-8"))
    slots = doc["skins"]["default"]["slots"]
    slots["head"]["pa"] = dict(next(iter(slots["head"].values())))
    slots["torso"]["pa"] = {**next(iter(slots["torso"].values())), "path": "parts/nonexistent.svg"}
    doc["asset_sets"]["pose"] = {"a": "pa"}
    doc_path.write_text(json.dumps(doc), "utf-8")
    shot = _shot(SetAction(target="ned", property="pose", value="a", at=0.0))
    _compile(root, shot, strict=True)
    assert _errors(root, shot) == []
