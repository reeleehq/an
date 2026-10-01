"""The cut-out methods at compile time (ADR 0002 first slice, an#248).

**Locomotion moved, not changed.** The gate is byte-identical output (ADR 0002
decision 8): every walk below compiles to the same document whether the gait
comes from the capability registry or from the pre-an#248 rule (the author's
``gait`` arg, else the descriptor's, else the walk's own leg lookup) — the
oracle is that rule, patched in for the comparison. A requested gait the rig
cannot honour now also leaves a recorded substitution, which is the only
difference allowed, and `--strict-assets` makes it fatal.

**Speech gains its requirement-free default.** A baked face speaks with a head
pulse on its syllables; a character with a mouth chart compiles exactly as
before. Compile only: no browser.
"""

from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout import compile as cc
from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.characters.methods import syllable_beats
from an.ir.schema import (
    AssetRef,
    Dialogue,
    PlayAction,
    Shot,
    VisemeKeyframe,
    VisemeTrack,
    WordTimingIR,
)
from an.stores.characters import CharactersStore

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "characters"
LEGGED_PARTS = ["head", "torso", "left_arm", "right_arm", "left_leg", "right_leg"]
LEGLESS_PARTS = ["head", "torso", "left_arm", "right_arm"]


@pytest.fixture()
def store(tmp_path):
    shutil.copytree(FIXTURES / "gale", tmp_path / "gale")
    for name, gait in (("gale_hem", "hem"), ("gale_rock", "rock"), ("gale_legs", "legs")):
        shutil.copytree(FIXTURES / "gale", tmp_path / name)
        path = tmp_path / name / "character.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["gait"] = gait
        path.write_text(json.dumps(doc), encoding="utf-8")
    s = CharactersStore(tmp_path)
    s["legged"] = {"name": "legged", "parts": LEGGED_PARTS}
    s["legless"] = {"name": "legless", "parts": LEGLESS_PARTS}
    s["legless_hem"] = {"name": "legless_hem", "parts": LEGLESS_PARTS}
    return s


def _old_gait(entity, args, desc, vocab, resolutions):
    """The pre-an#248 rule: the author's gait, else the descriptor's; else unset."""
    return args.get("gait") or getattr(desc, "gait", None)


def _doc(scene, *, drop_methods: bool = True) -> dict:
    d = scene.model_dump(mode="json")
    if drop_methods:
        d["asset_resolution"] = [r for r in d["asset_resolution"] if r["kind"] != "method"]
    return d


def _walk_shot(ref: str, *, view: str | None = None, **args) -> Shot:
    if view is not None:
        args["view"] = view
    actions = [PlayAction(target="w", animation="walk", args={"distance": 160, **args})]
    return Shot(
        id="walk",
        duration=3.0,
        entities=[AssetRef(kind="character", id="w", store="characters", ref=ref)],
        actions=actions,
    )


WALKS = [
    ("placeholder", {}),
    ("legged", {}),
    ("legless", {}),
    ("legged", {"gait": "rock"}),
    ("legged", {"gait": "hem"}),
    ("legless", {"gait": "hem"}),
    ("legless", {"gait": "legs"}),
    ("gale", {}),
    ("gale", {"gait": "hem"}),
    ("gale", {"legs": []}),
    ("gale", {"legs": ["arm_l", "arm_r"], "arms": []}),
    ("gale_hem", {}),
    ("gale_rock", {}),
    ("gale_legs", {"gait": "rock"}),
]


@pytest.mark.parametrize("ref,args", WALKS, ids=[f"{r}-{a}" for r, a in WALKS])
def test_a_walk_compiles_byte_identically_to_the_rule_it_replaced(ref, args, store, monkeypatch):
    mall = {"characters": store}
    shots = [_walk_shot(ref, **args)]
    if ref.startswith("gale"):
        shots.append(_walk_shot(ref, view="side", **args))
    for shot in shots:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            new = _doc(compile_shot(shot, mall))
            with monkeypatch.context() as m:
                m.setattr(cc, "_locomotion_gait", _old_gait)
                old = _doc(compile_shot(shot, mall))
        assert new == old


def test_a_requested_gait_the_rig_cannot_honour_is_recorded_and_fatal_under_strict(store):
    mall = {"characters": store}
    shot = _walk_shot("legless", gait="hem")
    with pytest.warns(Warning, match="loco.hem_sway"):
        scene = compile_shot(shot, mall)
    (record,) = [r for r in scene.asset_resolution if r.kind == "method"]
    assert (record.store, record.ref, record.resolved, record.fallback) == (
        "locomotion",
        "loco.hem_sway",
        "loco.rock",
        True,
    )
    assert "limbs.legs" in record.detail
    with pytest.raises(CutoutCompileError, match="loco.hem_sway"):
        compile_shot(shot, mall, strict_assets=True)


def test_a_walk_the_rig_honours_records_nothing(store):
    scene = compile_shot(_walk_shot("legged", gait="hem"), {"characters": store})
    assert not [r for r in scene.asset_resolution if r.kind == "method"]


# --------------------------------------------------------------------------- speech


def _speaking(ref: str) -> Shot:
    line = Dialogue(
        speaker="g",
        text="hello there",
        start=0.5,
        duration=1.0,
        viseme_track=VisemeTrack(
            keyframes=[
                VisemeKeyframe(time=t, viseme=v)
                for t, v in [(0.0, "X"), (0.1, "C"), (0.2, "A"), (0.35, "E"), (0.5, "B"), (0.6, "X"), (0.7, "D"), (0.9, "X")]
            ]
        ),
    )
    return Shot(
        id="talk",
        duration=2.0,
        entities=[AssetRef(kind="character", id="g", store="characters", ref=ref)],
        dialogue=[line],
    )


def _baked(store, tmp_path) -> None:
    path = Path(store.sidecar_path("gale", "character.json"))
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["face_overlay"] = False
    (tmp_path / "baked").mkdir()
    shutil.copytree(path.parent, tmp_path / "baked", dirs_exist_ok=True)
    (tmp_path / "baked" / "character.json").write_text(json.dumps(doc), encoding="utf-8")


def test_a_baked_face_speaks_with_a_head_pulse_on_its_syllables(store, tmp_path):
    from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene

    _baked(store, tmp_path)
    scene = compile_shot(_speaking("baked"), {"characters": CharactersStore(tmp_path)})
    timeline = timeline_from_scene(scene)

    def head(t: float) -> float:
        return evaluate_timeline(timeline, t).get(("g/head", "scale_y"), 1.0)

    # The mouth opens at 0.1, 0.35 and 0.7 s into the line, which starts at 0.5 s:
    # each onset peaks one attack (0.06 s) later, and the head is at rest between.
    for onset in (0.6, 0.85, 1.2):
        assert head(onset) == pytest.approx(1.0)
        assert head(onset + 0.06) == pytest.approx(1.06)
    assert head(0.3) == pytest.approx(1.0) and head(1.9) == pytest.approx(1.0)
    assert not any(k.startswith("__viseme__") for k in scene.animations)


def test_a_character_with_a_mouth_chart_compiles_as_before(store, monkeypatch):
    mall = {"characters": store}
    new = _doc(compile_shot(_speaking("gale"), mall), drop_methods=False)
    monkeypatch.setattr(cc, "_speech_default_actions", lambda *a, **k: [])
    assert new == _doc(compile_shot(_speaking("gale"), mall), drop_methods=False)


def test_syllable_beats_come_from_the_visemes_else_the_words_else_the_start():
    line = _speaking("gale").dialogue[0]
    assert syllable_beats(line) == [0.1, 0.35, 0.7]
    words = Dialogue(
        speaker="g",
        text="a b",
        start=0.0,
        duration=1.0,
        word_timings=[WordTimingIR(text="a", start=0.0, end=0.2), WordTimingIR(text="b", start=0.1, end=0.5)],
    )
    assert syllable_beats(words) == [0.0]  # 0.1 is inside the minimum gap
    assert syllable_beats(Dialogue(speaker="g", text="x", start=0.0, duration=1.0)) == [0.0]


# --------------------------------------------------------------------------- the CLI


def test_an_character_capabilities_says_what_applies_and_what_is_missing(tmp_path):
    from an.characters.cli import capabilities

    out = capabilities("gale", out_dir=str(FIXTURES))
    assert "limbs.legs" in out and "locomotion: default loco.legged_cycle" in out
    assert "speech: default speech.mouth_chart" in out

    # A legless, baked-face copy: the defaults fall to the requirement-free
    # links, and the rest say what to add.
    shutil.copytree(FIXTURES / "gale", tmp_path / "blob")
    doc = json.loads((tmp_path / "blob" / "character.json").read_text(encoding="utf-8"))
    doc["face_overlay"] = False
    for skin in doc["skins"].values():
        for slot in ("leg_l", "leg_r"):
            skin["slots"].pop(slot, None)
    (tmp_path / "blob" / "character.json").write_text(json.dumps(doc), encoding="utf-8")
    out = capabilities("blob", out_dir=str(tmp_path))
    assert "locomotion: default loco.rock" in out
    assert "speech: default speech.pose_only" in out
    assert "not loco.legged_cycle: missing limbs.legs" in out
    assert "to add face.mouth:" in out
    assert '"default": "loco.rock"' in capabilities("blob", out_dir=str(tmp_path), as_json=True)
