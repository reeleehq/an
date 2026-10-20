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
        return [SimpleNamespace(generated_voice_id=f"gen{i}", audio=b"ID3" + bytes([i]), duration_s=2.0) for i in range(self.n)]

    def design_voice(self, description, *, preview, name):
        gid = getattr(preview, "generated_voice_id", preview)
        self.calls.append(("save", gid, name))
        return SimpleNamespace(segment=f"voice-{gid}")


def test_persist_saves_every_option():
    d, samples = FakeDesigner(), {}
    m = design_voice_options({"j": {"notes": NOTES, "sample_text": "x" * 120}}, samples=samples, designer=d)
    assert [o["voice_id"] for o in m["j"]["options"]] == ["voice-gen0", "voice-gen1", "voice-gen2"]
    assert d.calls[0] == ("previews", NOTES, "x" * 120, "eleven_ttv_v3")
    assert samples["j_C"] == b"ID3\x02"


def test_not_persisted_option_is_saved_when_chosen():
    d = FakeDesigner()
    m = design_voice_options({"j": {"notes": NOTES}}, samples={}, designer=d, persist=False)
    assert all(o["voice_id"] is None for o in m["j"]["options"])
    assert not [c for c in d.calls if c[0] == "save"]
    assert choose_voice_option(m["j"], "b", ref="j", designer=d) == "voice-gen1"
    with pytest.raises(VoiceDesignError, match="no option 'Z'"):
        choose_voice_option(m["j"], "Z", designer=d)


def test_named_voice_without_notes_is_refused_before_any_call():
    d = FakeDesigner()
    with pytest.raises(VoiceDesignError, match="no 'notes'"):
        design_voice_options({"j": {"provider": "elevenlabs"}}, samples={}, refs=["j"], designer=d)
    with pytest.raises(VoiceDesignError, match="characters"):
        design_voice_options({"j": {"notes": "short"}}, samples={}, refs=["j"], designer=d)
    assert d.calls == []


def test_project_round_trip(tmp_path):
    from an.project import init

    proj = tmp_path / "p"
    init(str(proj))
    (proj / "assets" / "voices").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "voices" / "jerry.json").write_text(json.dumps({"provider": "elevenlabs", "model_id": "eleven_v3", "notes": NOTES}), encoding="utf-8")
    d = FakeDesigner(n=2)
    manifest = design_project_voices(proj, designer=d)
    assert (proj / "artifacts" / "voice_samples" / "jerry_A.mp3").read_bytes() == b"ID3\x00"
    assert json.loads((proj / "artifacts" / "voice_options" / "jerry.json").read_text(encoding="utf-8"))["options"][1]["sample_path"] == "artifacts/voice_samples/jerry_B.mp3"
    assert manifest["jerry"]["name_prefix"] == "p"
    doc = choose_project_voice(proj, "jerry", "B", designer=d)
    assert doc == {"provider": "elevenlabs", "model_id": "eleven_v3", "notes": NOTES, "voice_id": "voice-gen1"}
    assert json.loads((proj / "assets" / "voices" / "jerry.json").read_text(encoding="utf-8"))["voice_id"] == "voice-gen1"
    assert json.loads((proj / "artifacts" / "voice_options" / "jerry.json").read_text(encoding="utf-8"))["chosen"] == {"option": "B", "voice_id": "voice-gen1"}


def test_elevenlabs_designer_calls_the_sdk_shape():
    import base64

    from an.audio.voice_design import ElevenLabsVoiceDesigner

    calls = []

    class TTV:
        def design(self, **kw):
            calls.append(("design", kw))
            return SimpleNamespace(previews=[SimpleNamespace(generated_voice_id="g", audio_base_64=base64.b64encode(b"ID3").decode(), duration_secs=1.5)])

        def create(self, **kw):
            calls.append(("create", kw))
            return SimpleNamespace(voice_id="v1")

    d = ElevenLabsVoiceDesigner(api_key="k", client_factory=lambda key: SimpleNamespace(text_to_voice=TTV()))
    [p] = d.design_voice_previews(NOTES, text=None)
    assert (p.generated_voice_id, p.audio, p.duration_s) == ("g", b"ID3", 1.5)
    assert calls[0] == ("design", {"voice_description": NOTES, "model_id": "eleven_ttv_v3", "auto_generate_text": True, "request_options": {"timeout_in_seconds": 120}})
    assert d.design_voice(NOTES, preview=p, name="n").segment == "v1"
    assert calls[1][1]["generated_voice_id"] == "g"
