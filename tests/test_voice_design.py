"""Voice design from a voice document's notes, and the writer's choice (an voices design/choose)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from an.audio.voice_design import (
    VoiceDesignError,
    choose_project_voice,
    choose_voice_option,
    design_project_voices,
    design_voice_options,
)

NOTES = "A man in his early 50s, rural Yorkshire accent, warm and unhurried."


class FakeDesigner:
    """voxy's two designer methods, recording the calls; nothing is billed."""

    def __init__(self, n=3):
        self.n, self.calls = n, []

    def design_voice_previews(self, description, *, text=None, model_id=None):
        self.calls.append(("previews", description, text, model_id))
        return [
            SimpleNamespace(
                generated_voice_id=f"gen{i}", audio=b"ID3" + bytes([i]), duration_s=2.0
            )
            for i in range(self.n)
        ]

    def design_voice(self, description, *, preview, name):
        gid = getattr(preview, "generated_voice_id", preview)
        self.calls.append(("save", gid, name))
        return SimpleNamespace(segment=f"voice-{gid}")


def test_persist_saves_every_option():
    d, samples = FakeDesigner(), {}
    m = design_voice_options(
        {"j": {"notes": NOTES, "sample_text": "x" * 120}}, samples=samples, designer=d
    )
    assert [o["voice_id"] for o in m["j"]["options"]] == [
        "voice-gen0",
        "voice-gen1",
        "voice-gen2",
    ]
    assert d.calls[0] == ("previews", NOTES, "x" * 120, "eleven_ttv_v3")
    assert samples["j_C"] == b"ID3\x02"


def test_not_persisted_option_is_saved_when_chosen():
    d = FakeDesigner()
    m = design_voice_options(
        {"j": {"notes": NOTES}}, samples={}, designer=d, persist=False
    )
    assert all(o["voice_id"] is None for o in m["j"]["options"])
    assert not [c for c in d.calls if c[0] == "save"]
    assert choose_voice_option(m["j"], "b", ref="j", designer=d) == "voice-gen1"
    with pytest.raises(VoiceDesignError, match="no option 'Z'"):
        choose_voice_option(m["j"], "Z", designer=d)


def test_named_voice_without_notes_is_refused_before_any_call():
    d = FakeDesigner()
    with pytest.raises(VoiceDesignError, match="no 'notes'"):
        design_voice_options(
            {"j": {"provider": "elevenlabs"}}, samples={}, refs=["j"], designer=d
        )
    with pytest.raises(VoiceDesignError, match="characters"):
        design_voice_options(
            {"j": {"notes": "short"}}, samples={}, refs=["j"], designer=d
        )
    assert d.calls == []


def test_project_round_trip(tmp_path):
    from an.project import init

    proj = tmp_path / "p"
    init(str(proj))
    (proj / "assets" / "voices").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "voices" / "jerry.json").write_text(
        json.dumps({"provider": "elevenlabs", "model_id": "eleven_v3", "notes": NOTES}),
        encoding="utf-8",
    )
    d = FakeDesigner(n=2)
    manifest = design_project_voices(proj, designer=d)
    assert (
        proj / "artifacts" / "voice_samples" / "jerry_A.mp3"
    ).read_bytes() == b"ID3\x00"
    assert (
        json.loads(
            (proj / "artifacts" / "voice_options" / "jerry.json").read_text(
                encoding="utf-8"
            )
        )["options"][1]["sample_path"]
        == "artifacts/voice_samples/jerry_B.mp3"
    )
    assert manifest["jerry"]["name_prefix"] == "p"
    doc = choose_project_voice(
        proj, "jerry", "B", designer=d, by="noel", at="2026-10-20T22:00:00+00:00"
    )
    assert doc == {
        "provider": "elevenlabs",
        "model_id": "eleven_v3",
        "notes": NOTES,
        "voice_id": "voice-gen1",
        "chosen_by": "noel",
        "chosen_at": "2026-10-20T22:00:00+00:00",
    }
    assert (
        json.loads(
            (proj / "assets" / "voices" / "jerry.json").read_text(encoding="utf-8")
        )["voice_id"]
        == "voice-gen1"
    )
    assert json.loads(
        (proj / "artifacts" / "voice_options" / "jerry.json").read_text(
            encoding="utf-8"
        )
    )["chosen"] == {
        "option": "B",
        "voice_id": "voice-gen1",
        "chosen_by": "noel",
        "chosen_at": "2026-10-20T22:00:00+00:00",
    }


def test_elevenlabs_designer_calls_the_sdk_shape():
    import base64

    from an.audio.voice_design import ElevenLabsVoiceDesigner

    calls = []

    class TTV:
        def design(self, **kw):
            calls.append(("design", kw))
            return SimpleNamespace(
                previews=[
                    SimpleNamespace(
                        generated_voice_id="g",
                        audio_base_64=base64.b64encode(b"ID3").decode(),
                        duration_secs=1.5,
                    )
                ]
            )

        def create(self, **kw):
            calls.append(("create", kw))
            return SimpleNamespace(voice_id="v1")

    d = ElevenLabsVoiceDesigner(
        api_key="k", client_factory=lambda key: SimpleNamespace(text_to_voice=TTV())
    )
    [p] = d.design_voice_previews(NOTES, text=None)
    assert (p.generated_voice_id, p.audio, p.duration_s) == ("g", b"ID3", 1.5)
    assert calls[0] == (
        "design",
        {
            "voice_description": NOTES,
            "model_id": "eleven_ttv_v3",
            "auto_generate_text": True,
            "request_options": {"timeout_in_seconds": 120},
        },
    )
    assert d.design_voice(NOTES, preview=p, name="n").segment == "v1"
    assert calls[1][1]["generated_voice_id"] == "g"


def _voice_project(tmp_path, doc):
    from an.project import init

    proj = tmp_path / "p"
    init(str(proj))
    (proj / "assets" / "voices").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "voices" / "jerry.json").write_text(
        json.dumps(doc), encoding="utf-8"
    )
    return proj


def _manifest(proj):
    return json.loads(
        (proj / "artifacts" / "voice_options" / "jerry.json").read_text(
            encoding="utf-8"
        )
    )


def test_choosing_again_retires_the_replaced_designed_voice(tmp_path):
    """an#549: the choose step a connector shares (`choose_in_entry`). Choosing
    another option retires the voice it replaces (named in `retired`, never
    deleted; its option no longer names it), choosing it back saves it anew
    from its preview, and the same choice again keeps its first `chosen_at`.
    The voice document keeps its notes and loses `provisional`."""
    proj = _voice_project(tmp_path, {"notes": NOTES, "provisional": True})
    d = FakeDesigner(n=2)
    design_project_voices(proj, designer=d, persist=False)
    choose_project_voice(proj, "jerry", "A", designer=d, by="noel", at="t1")
    doc = choose_project_voice(proj, "jerry", "B", designer=d, by="noel", at="t2")
    assert doc["notes"] == NOTES and "provisional" not in doc
    m = _manifest(proj)
    assert m["retired"] == [
        {"voice_id": "voice-gen0", "option": "A", "name_prefix": "p"}
    ]
    assert [o["voice_id"] for o in m["options"]] == [None, "voice-gen1"]
    assert (
        choose_project_voice(proj, "jerry", "B", designer=d, by="noel")["chosen_at"]
        == "t2"
    )
    saves = len([c for c in d.calls if c[0] == "save"])
    choose_project_voice(proj, "jerry", "A", designer=d, by="noel")
    assert len([c for c in d.calls if c[0] == "save"]) == saves + 1, (
        "saved anew, not taken back"
    )


def test_with_every_option_persisted_only_the_replaced_voice_is_retired(tmp_path):
    proj = _voice_project(tmp_path, {"notes": NOTES})
    d = FakeDesigner(n=3)
    design_project_voices(proj, designer=d)  # persist=True: every option is a voice
    choose_project_voice(proj, "jerry", "A", designer=d, by="noel")
    choose_project_voice(proj, "jerry", "B", designer=d, by="noel")
    m = _manifest(proj)
    assert [o["voice_id"] for o in m["options"]] == [None, "voice-gen1", "voice-gen2"]
    assert [r["voice_id"] for r in m["retired"]] == ["voice-gen0"]


def test_a_voice_this_manifest_did_not_save_is_never_retired():
    """A library option's voice is another account's, and a voice cast by hand
    the writer's: replacing either retires nothing and clears nothing."""
    from an.audio.voice_design import choose_in_entry

    entry = {
        "options": [
            {"option": "A", "generated_voice_id": "gA", "voice_id": "vA"},
            {"option": "L1", "kind": "library", "voice_id": "pub1"},
        ]
    }
    choose_in_entry(entry, "L1", by="noel")
    choice = choose_in_entry(entry, "A", by="noel")
    assert choice.replaced is None and "retired" not in entry
    assert entry["options"][1]["voice_id"] == "pub1"
    entry["chosen"] = {
        "option": None,
        "voice_id": "my-clone",
        "chosen_by": "noel",
        "chosen_at": "t",
    }
    assert (
        choose_in_entry(entry, "A", by="noel").replaced is None
        and "retired" not in entry
    )


def test_a_damaged_retired_ledger_is_refused_before_anything_is_chosen():
    from an.audio.voice_design import VoiceDesignError, choose_in_entry

    entry = {
        "options": [
            {"option": "A", "voice_id": "vA"},
            {"option": "B", "voice_id": "vB"},
        ],
        "chosen": {"option": "A", "voice_id": "vA"},
        "retired": {},
    }
    with pytest.raises(VoiceDesignError, match="damaged"):
        choose_in_entry(entry, "B", by="noel")
