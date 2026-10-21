"""A voice written in words is cast by the writer, nobody else (an#486).

`an voices choose` records who chose a voice and when; a voice document that
has ``notes`` but no recorded choice is a render finding, refused under
``strict_assets`` before anything is synthesized; a ``provisional`` voice (a
timing draft's stand-in) is spoken and listed. Nothing here reaches an API.
"""

from __future__ import annotations

import json

import pytest

from an.audio.pipeline import (
    VoiceNotChosenError,
    VoiceNotChosenWarning,
    VoiceProvisionalWarning,
    produce_audio_for_scene,
)
from an.audio.voice_design import (
    VoiceDesignError,
    choose_project_voice,
    provisional_reason,
    record_choice,
    voice_casting,
    voice_casting_problem,
)
from an.ir.schema import Dialogue
from an.orchestrate import validate_project
from an.project import load
from an.render import _report_records, render_findings
from tests.test_shot_cache import (  # noqa: F401 — the fixture, by name
    _project,
    _set_shots,
    _shot,
    fake_render,
)
from tests.test_voice_design import NOTES, FakeDesigner
from tests.test_voice_provider import _render, _speaking, eleven  # noqa: F401 — the fixture, by name

WRITTEN = {"provider": "elevenlabs", "voice_id": "TX3", "notes": NOTES}
CHOSEN = {**WRITTEN, "chosen_by": "noel", "chosen_at": "2026-10-20T22:00:00+00:00"}
DRAFT = {**WRITTEN, "provisional": "round-2 timing draft"}


def _kinds(root):
    return sorted(r["kind"] for r in _report_records(root, "main"))


# -----------------------------------------------------------------------------
# The record
# -----------------------------------------------------------------------------


def test_choose_records_who_and_when(tmp_path):
    from an.project import init

    proj = tmp_path / "p"
    init(str(proj))
    (proj / "assets" / "voices").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "voices" / "jerry.json").write_text(
        json.dumps({**WRITTEN, "voice_id": "draft", "provisional": True}), encoding="utf-8"
    )
    from an.audio.voice_design import design_project_voices

    design_project_voices(proj, designer=FakeDesigner(n=2))
    doc = choose_project_voice(proj, "jerry", "b", designer=FakeDesigner(), by="noel")
    assert doc["voice_id"] == "voice-gen1" and doc["chosen_by"] == "noel"
    assert doc["chosen_at"].endswith("+00:00") and "T" in doc["chosen_at"]
    assert "provisional" not in doc  # the choice is what it stood in for
    on_disk = json.loads((proj / "assets" / "voices" / "jerry.json").read_text(encoding="utf-8"))
    assert on_disk == doc
    chosen = json.loads((proj / "artifacts" / "voice_options" / "jerry.json").read_text(encoding="utf-8"))["chosen"]
    assert chosen == {"option": "B", "voice_id": "voice-gen1", "chosen_by": "noel", "chosen_at": doc["chosen_at"]}


def test_choose_defaults_to_the_login_name(tmp_path, monkeypatch):
    monkeypatch.setattr("an.audio.voice_design.default_chooser", lambda: "thor")
    assert record_choice({}, "v")["chosen_by"] == "thor"
    assert record_choice({}, "v", by="  ")["chosen_by"] == "thor"


@pytest.mark.parametrize(
    "doc, problem",
    [
        ({"voice_id": "v"}, None),  # named by hand: not judged
        ({}, None),
        ({"notes": NOTES}, "no voice is chosen"),
        ({"notes": NOTES, "voice_id": "v"}, "no chosen_by"),
        ({"notes": NOTES, "voice_id": "v", "chosen_by": ""}, "no chosen_by"),
        (CHOSEN, None),
        (DRAFT, None),
        ({"notes": NOTES, "provisional": True}, "no voice is chosen"),  # provisional what?
    ],
)
def test_what_is_cast(doc, problem):
    found = voice_casting_problem(doc)
    assert (found is None) == (problem is None), found
    if problem:
        assert problem in found


def test_provisional_is_truthy_with_an_optional_reason():
    assert provisional_reason(DRAFT) == "round-2 timing draft"
    assert provisional_reason({"provisional": True}) == "provisional"
    assert provisional_reason({"provisional": ""}) is None
    assert provisional_reason({"provisional": False}) is None


def test_messages_are_one_per_voice_and_name_the_fix():
    uncast, provisional = voice_casting(["j", "j", "d", "h", "none"], {"j": WRITTEN, "d": DRAFT, "h": CHOSEN})
    assert len(uncast) == 1 and uncast[0].startswith("voice 'j'")
    assert "`an voices design`" in uncast[0] and "`an voices choose" in uncast[0]
    assert "`an voices cast" in uncast[0] and "provisional: true" in uncast[0]
    assert provisional == ["voice 'd' is provisional (round-2 timing draft): choose a voice before the cut"]


def test_cast_records_a_hand_picked_voice_without_a_design_round(tmp_path):
    from an.audio.voice_design import cast_project_voice
    from an.project import init

    proj = tmp_path / "p"
    init(str(proj))
    (proj / "assets" / "voices").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "voices" / "paul.json").write_text(
        json.dumps({"provider": "mac_say", "notes": NOTES, "voice_id": "Ralph", "provisional": True}), encoding="utf-8"
    )
    doc = cast_project_voice(proj, "paul", by="noel", at="2026-10-20T22:00:00+00:00")
    assert doc["voice_id"] == "Ralph" and doc["provider"] == "mac_say"  # the document's own, kept
    assert doc["chosen_by"] == "noel" and "provisional" not in doc
    assert voice_casting_problem(json.loads((proj / "assets" / "voices" / "paul.json").read_text(encoding="utf-8"))) is None
    doc = cast_project_voice(proj, "paul", "TX3", by="noel", provider="elevenlabs")
    assert (doc["voice_id"], doc["provider"]) == ("TX3", "elevenlabs")
    with pytest.raises(VoiceDesignError, match="no voice document 'ghost'"):
        cast_project_voice(proj, "ghost", "x", by="noel")
    (proj / "assets" / "voices" / "bare.json").write_text(json.dumps({"notes": NOTES}), encoding="utf-8")
    with pytest.raises(VoiceDesignError, match="names no voice_id"):
        cast_project_voice(proj, "bare", by="noel")


def test_the_cli_prints_a_refusal_as_a_sentence():
    from an.__main__ import _REFUSALS

    assert issubclass(VoiceNotChosenError, _REFUSALS)


# -----------------------------------------------------------------------------
# The render
# -----------------------------------------------------------------------------


def test_an_unchosen_voice_is_refused_under_strict_before_synthesis(tmp_path, fake_render, eleven):
    root = _speaking(tmp_path, WRITTEN)
    with pytest.raises(VoiceNotChosenError, match="no chosen_by"):
        _render(root, strict_assets=True)
    assert list(load(root).mall["audio"]) == []
    assert eleven.requests == []


def test_an_unchosen_voice_is_a_finding_without_strict(tmp_path, fake_render, eleven):
    root = _speaking(tmp_path, WRITTEN)
    _render(root)
    assert _kinds(root) == ["VoiceNotChosenWarning"]
    (f,) = render_findings(root)
    assert f.severity == "warning" and "voice 'bob' has a voice_id nobody" in f.description
    assert len(eleven.requests) == 1  # spoken anyway, and said


def test_a_chosen_voice_is_not_a_finding(tmp_path, fake_render, eleven):
    root = _speaking(tmp_path, CHOSEN)
    _render(root, strict_assets=True)
    assert render_findings(root) == []


def test_a_provisional_voice_is_spoken_and_listed(tmp_path, fake_render, eleven):
    root = _speaking(tmp_path, DRAFT)
    _render(root, strict_assets=True)  # allowed, even strict
    assert _kinds(root) == ["VoiceProvisionalWarning"]
    (f,) = render_findings(root)
    assert "voice 'bob' is provisional (round-2 timing draft)" in f.description
    assert len(eleven.requests) == 1


def test_a_hand_named_voice_is_unchanged(tmp_path, fake_render, eleven):
    root = _speaking(tmp_path, {"provider": "elevenlabs", "voice_id": "TX3"})
    _render(root, strict_assets=True)
    assert render_findings(root) == []


@pytest.mark.genre("cutout_animation")
def test_the_pipeline_warns_a_python_caller_too():
    from an.ir.schema import SceneIR, Shot
    from tests.test_voice_provider import _offline_lipsync

    scene = SceneIR(timeline=[Shot(id="s", dialogue=[Dialogue(speaker="x", text="hi", voice_ref="bob")])])
    mall = {"voices": {"bob": {"notes": NOTES, "voice_id": "v"}}, "audio": {}, "visemes": {}}
    with pytest.warns(VoiceNotChosenWarning, match="no chosen_by"):
        produce_audio_for_scene(scene, mall, tts="offline", lipsync=_offline_lipsync(), announce=None)
    mall["voices"]["bob"] = {"notes": NOTES, "voice_id": "v", "provisional": True}
    with pytest.warns(VoiceProvisionalWarning, match="provisional"):
        produce_audio_for_scene(scene, mall, tts="offline", lipsync=_offline_lipsync(), announce=None)


# -----------------------------------------------------------------------------
# `an validate` agrees
# -----------------------------------------------------------------------------


def test_validate_notes_it_as_info_strict_or_not_because_casting_comes_after_the_check(tmp_path):
    """A production pack is checked with --strict-assets while its voices are
    still words: that must pass, and check CLEAN (the pack checker's example
    pack allows no warning). The refusal is the render's."""
    root = _speaking(tmp_path, WRITTEN)
    for strict in (False, True):
        report = validate_project(root, strict_assets=strict)
        (f,) = [f for f in report.findings if f.ir_path == "voices"]
        assert f.severity == "info" and "nobody is recorded as choosing" in f.description
        assert "`an render --strict-assets` refuses it until it is cast" in f.description
        assert report.passed


def test_validate_lists_a_provisional_voice_as_info(tmp_path):
    root = _speaking(tmp_path, DRAFT)
    report = validate_project(root, strict_assets=True)
    (f,) = [f for f in report.findings if f.ir_path == "voices"]
    assert f.severity == "info" and "provisional" in f.description
