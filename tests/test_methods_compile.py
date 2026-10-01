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


def _old_args(entity, args, desc, vocab, resolutions):
    """The pre-an#248 rule: the author's gait, else the descriptor's; else unset."""
    gait = args.get("gait") or getattr(desc, "gait", None)
    return {**args, "gait": gait} if gait else dict(args)


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
                m.setattr(cc, "_locomotion_args", _old_args)
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
    from an.characters.methods import SpeechPlan

    monkeypatch.setattr(cc, "_speech_plan", lambda *a, **k: SpeechPlan())
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


# --------------------------------------------------------------------------- review-256


def _variant(tmp_path, name: str, **changes) -> CharactersStore:
    """A copy of `gale` under ``name`` with descriptor fields changed."""
    shutil.copytree(FIXTURES / "gale", tmp_path / name)
    path = tmp_path / name / "character.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc.update(changes)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return CharactersStore(tmp_path)


def _head(scene, entity: str = "g", part: str = "head"):
    from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene

    timeline = timeline_from_scene(scene)
    path = f"{entity}/{part}" if part else entity
    return lambda t: evaluate_timeline(timeline, t).get((path, "scale_y"), 1.0)


def _methods(scene):
    return [r for r in scene.asset_resolution if r.kind == "method"]


def test_falling_to_the_pulse_is_recorded_and_fatal_under_strict(tmp_path):
    """S1: a baked face that never asked for the pulse: recorded, strict refuses it."""
    store = _variant(tmp_path, "baked", face_overlay=False)
    with pytest.warns(Warning, match="speech.pose_only"):
        scene = compile_shot(_speaking("baked"), {"characters": store})
    (record,) = _methods(scene)
    assert (record.store, record.ref, record.resolved, record.fallback) == (
        "speech", "speech.mouth_chart", "speech.pose_only", True,
    )
    with pytest.raises(CutoutCompileError, match="speech"):
        compile_shot(_speaking("baked"), {"characters": store}, strict_assets=True)


def test_a_declared_pulse_is_the_request_and_renders_under_strict(tmp_path):
    store = _variant(tmp_path, "baked", face_overlay=False, speech="pulse")
    scene = compile_shot(_speaking("baked"), {"characters": store}, strict_assets=True)
    assert _methods(scene) == []
    assert _head(scene)(0.66) == pytest.approx(1.06)


def test_strength_zero_is_a_mime_no_pulse_and_no_lip_sync(tmp_path):
    store = _variant(tmp_path, "mime", speech={"method": "pulse", "args": {"strength": 0}})
    scene = compile_shot(_speaking("mime"), {"characters": store}, strict_assets=True)
    head = _head(scene)
    assert all(head(t) == pytest.approx(1.0) for t in (0.6, 0.66, 0.91, 1.26))
    assert not any(k.startswith("__viseme__") for k in scene.animations)


def test_a_character_with_a_chart_that_declares_the_pulse_stops_lip_syncing(tmp_path):
    """S2: one resolution decides both halves — no visemes AND a pulse."""
    store = _variant(tmp_path, "pulser", speech="pulse")
    scene = compile_shot(_speaking("pulser"), {"characters": store})
    assert not any(k.startswith("__viseme__") for k in scene.animations)
    assert _head(scene)(0.66) == pytest.approx(1.06)


def test_an_authored_speech_pulse_takes_over_from_the_automatic_one(tmp_path):
    store = _variant(tmp_path, "baked", face_overlay=False)
    shot = _speaking("baked").model_copy(
        update={"actions": [PlayAction(target="g", animation="speech_pulse", args={"beats": [0.5], "strength": 0.2})]}
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scene = compile_shot(shot, {"characters": store})
    head = _head(scene)
    assert head(0.56) == pytest.approx(1.2)
    assert all(head(t) == pytest.approx(1.0) for t in (0.66, 0.91, 1.26))


def test_the_pulse_rides_an_authored_head_scale_tween(tmp_path):
    """S1: an authored tween of the same property is composed with, not overwritten."""
    from an.ir.compose import tween

    store = _variant(tmp_path, "baked", face_overlay=False, speech="pulse")
    shot = _speaking("baked").model_copy(
        update={"actions": [tween("g/head", "scale_y", to=1.3, duration=2.0, easing="linear")]}
    )
    head = _head(compile_shot(shot, {"characters": store}))
    for t in (0.3, 0.8, 1.1, 1.5, 1.9):  # between pulses: the authored tween, untouched
        assert head(t) == pytest.approx(1.0 + 0.15 * t)
    assert head(0.66) == pytest.approx((1.0 + 0.15 * 0.6) * 1.06)  # a pulse on top


def test_the_compile_profile_honours_the_art_on_disk(tmp_path):
    """M11: a declared mouth whose drawings are gone is not a mouth chart."""
    store = _variant(tmp_path, "mouthless")
    for svg in (tmp_path / "mouthless" / "parts" / "mouth").glob("*.svg"):
        svg.unlink()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scene = compile_shot(_speaking("mouthless"), {"characters": store})
    assert [r.resolved for r in _methods(scene)] == ["speech.pose_only"]
    assert _head(scene)(0.66) == pytest.approx(1.06)


def test_a_headless_rig_pulses_its_body(store):
    """M10: no head node, so the pulse falls to the entity itself."""
    store["headless"] = {"name": "headless", "parts": ["torso", "left_arm", "right_arm"]}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scene = compile_shot(_speaking("headless"), {"characters": store})
    assert _head(scene, part="")(0.66) == pytest.approx(1.06)


def test_an_explicit_empty_legs_arg_is_honoured_and_recorded(store):
    """M12: `legs: []` affords no legs, so a requested hem falls to a rock, recorded."""
    with pytest.warns(Warning, match="loco.hem_sway"):
        scene = compile_shot(_walk_shot("gale", gait="hem", legs=[]), {"characters": store})
    (record,) = _methods(scene)
    assert (record.ref, record.resolved) == ("loco.hem_sway", "loco.rock")


@pytest.mark.parametrize(
    "spelled,expected",
    [
        ("loco.rock", {"gait": "rock"}),
        ({"method": "loco.legged_cycle", "version": "1"}, {"gait": "legs"}),
        ({"method": "legs", "args": {"stride": 0.5}}, {"gait": "legs", "stride": 0.5}),
    ],
)
def test_gait_takes_a_method_id_or_a_pinned_choice(spelled, expected, store):
    """S4: the level-(a) form, and the IR path for a version pin (ADR 0003 decision 2)."""
    from an.characters.play import preset_problems

    assert preset_problems("walk", args={"distance": 160, "gait": spelled}) == []
    mall = {"characters": store}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        got = _doc(compile_shot(_walk_shot("gale", gait=spelled), mall))
        want = _doc(compile_shot(_walk_shot("gale", **expected), mall))
    assert got == want


def test_a_stale_pin_or_another_aspects_method_is_refused_by_name(store):
    from an.characters.play import preset_problems

    (stale,) = preset_problems("walk", args={"gait": {"method": "loco.rock", "version": "0"}})
    assert "pinned" in stale
    (foreign,) = preset_problems("walk", args={"gait": "speech.pose_only"})
    assert "method of 'speech'" in foreign


def test_capabilities_reports_the_declared_gait_and_face(tmp_path):
    """S8: the CLI answers what the compiler will do, and says what was declared."""
    from an.characters.cli import capabilities

    _variant(tmp_path, "robe", gait="hem", face_overlay=False)
    out = capabilities("robe", out_dir=str(tmp_path))
    assert "locomotion: default loco.hem_sway (declared: hem)" in out
    assert "face_overlay=False" in out
    assert "speech: default speech.pose_only" in out and "recorded: missing" in out
