"""Expressive ElevenLabs voices (an#209): model, voice_settings, seed, and a
line's ``[emotion]`` / ``{direction}`` as v3 audio tags.

Nothing here reaches the API: ``ElevenLabsTTS`` takes a ``client_factory`` and
every test hands it a fake that records the request. The rules under test:

- a voice declaring nothing new keeps its exact pre-an#209 cache key;
- model, settings, seed and tags each move the key, and reach the request;
- tags are sent only to a model that reads them, prefixed to the text, and
  never reach ``Dialogue.text``, the clip's transcript or the aligner;
- a voice written for another provider is not handed to this one;
- ``scene.md``'s ``{direction}`` round-trips, and JSON omits it when unset.
"""

from __future__ import annotations

import warnings

import pytest

from an.audio.cli import browse_voices, format_voices
from an.audio.elevenlabs_tts import ElevenLabsTTS, ElevenLabsVoiceError
from an.audio.offline_tts import OfflineTTS
from an.audio.pipeline import audio_key, produce_audio_for_scene, synthesis_options
from an.ir.schema import AssetRef, Dialogue, Meta, SceneIR, Shot
from an.ir.sync import SceneMarkdownError, _extract_dialogue_block, _format_dialogue_line
from an.ir.validate import validate_semantic
from an.util import _stable_hash

from tests.test_voice_effects import _RecordingLipSync, _sine_wav


class _FakeClient:
    """Stands in for ``elevenlabs.client.ElevenLabs``; records every request."""

    def __init__(self, pages=None):
        self.requests: list[dict] = []
        self._pages = pages or []
        outer = self

        class _TTS:
            def convert(self, **request):
                outer.requests.append(request)
                return iter([_sine_wav()])

        class _Voices:
            def search(self, **kw):
                outer.searches.append(kw)
                return outer._pages[len(outer.searches) - 1]

        self.text_to_speech = _TTS()
        self.voices = _Voices()
        self.searches: list[dict] = []


def _tts(client=None):
    client = client or _FakeClient()
    return ElevenLabsTTS(api_key="fake", client_factory=lambda _key: client), client


def _mall(voices):
    return {
        "audio": {},
        "visemes": {},
        "characters": {"bob": {"voice_ref": "bob"}},
        "voices": voices,
    }


def _scene(*lines):
    return SceneIR(
        meta=Meta(title="t", duration=4.0),
        timeline=[
            Shot(
                id="s",
                renderer="cutout",
                duration=4.0,
                entities=[AssetRef(kind="character", id="bob", store="characters", ref="bob")],
                dialogue=list(lines),
            )
        ],
    )


V3 = {"provider": "elevenlabs", "voice_id": "abc", "model_id": "eleven_v3"}


# --- the cache key -------------------------------------------------------------


def test_a_voice_declaring_nothing_new_keeps_its_key():
    """The exact pre-an#209 payload, for ElevenLabs and for offline."""
    for tts, voices in (
        (_tts()[0], {"bob": {"provider": "elevenlabs", "voice_id": "abc"}}),
        (OfflineTTS(), {"bob": {"voice_id": "abc"}}),
    ):
        scene = _scene(Dialogue(speaker="bob", text="Hi!", emotion="happy"))
        produce_audio_for_scene(scene, _mall(voices), tts=tts, lipsync=_RecordingLipSync())
        want = _stable_hash(
            {"text": "Hi!", "voice": "bob", "tts": tts.name, "provider_voice": "abc"}
        )
        assert scene.timeline[0].dialogue[0].audio_ref == want


def test_model_settings_seed_and_tags_each_move_the_key_and_reach_the_request():
    tts, client = _tts()
    line = Dialogue(speaker="bob", text="Hi!", emotion="happy", direction=["excited"])
    base = {"provider": "elevenlabs", "voice_id": "abc"}
    keys = set()
    for doc in (
        base,
        {**base, "model_id": "eleven_multilingual_v2"},
        {**base, "voice_settings": {"stability": 0.3}},
        {**base, "seed": 7},
        {**base, "model_id": "eleven_v3"},  # now the tags ride along
    ):
        mall = _mall({"bob": doc})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # the dropped direction on non-v3
            options = synthesis_options(tts, line, mall, "bob")
        keys.add(audio_key("Hi!", "bob", tts.name, provider_voice="abc", options=options))
    assert len(keys) == 5

    scene = _scene(line)
    mall = _mall({"bob": {**V3, "voice_settings": {"stability": 0.5, "speed": 1.1}, "seed": 3}})
    produce_audio_for_scene(scene, mall, tts=tts, lipsync=_RecordingLipSync())
    (request,) = client.requests
    assert request["model_id"] == "eleven_v3"
    assert request["voice_id"] == "abc"
    assert request["seed"] == 3
    settings = request["voice_settings"]
    assert (getattr(settings, "stability", None) or settings["stability"]) == 0.5
    assert request["text"] == "[happy] [excited] Hi!"


def test_tags_never_reach_the_text_the_transcript_or_the_aligner():
    tts, client = _tts()

    class _Aligner(_RecordingLipSync):
        def __init__(self):
            super().__init__()
            self.transcripts: list[str] = []

        def align(self, audio, transcript):
            self.transcripts.append(transcript)
            assert audio.transcript == "Fine."
            return super().align(audio, transcript)

    aligner = _Aligner()
    scene = _scene(Dialogue(speaker="bob", text="Fine.", direction=["sighs", "annoyed"]))
    produce_audio_for_scene(scene, _mall({"bob": V3}), tts=tts, lipsync=aligner)
    assert client.requests[0]["text"] == "[sighs] [annoyed] Fine."
    assert aligner.transcripts == ["Fine."]
    assert scene.timeline[0].dialogue[0].text == "Fine."


def test_a_model_without_tags_gets_none_and_the_direction_warns():
    tts, client = _tts()
    line = Dialogue(speaker="bob", text="Hi!", emotion="happy", direction=["excited"])
    with pytest.warns(UserWarning, match="does not read audio tags"):
        opts = tts.synthesis_options({"voice_id": "abc"}, emotion="happy", direction=["excited"])
    assert "audio_tags" not in opts
    # An [emotion] alone on a non-tag model stays a face-only cue: no warning.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert tts.synthesis_options({}, emotion="happy") == {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        produce_audio_for_scene(_scene(line), _mall({"bob": {"voice_id": "abc"}}), tts=tts,
                                lipsync=_RecordingLipSync())
    assert client.requests[0]["text"] == "Hi!"


def test_neutral_is_not_a_tag_and_prefixes_match_variants():
    tts, _ = _tts()
    assert tts.synthesis_options({"model_id": "eleven_v3"}, emotion="neutral") == {"model_id": "eleven_v3"}
    assert tts.synthesis_options({"model_id": "eleven_v4_turbo"}, emotion="sad")["audio_tags"] == ["sad"]


@pytest.mark.parametrize(
    "doc, match",
    [
        ({"voice_settings": {"stabilty": 0.5}}, "unknown voice_settings"),
        ({"voice_settings": {"stability": 2}}, "outside"),
        ({"voice_settings": {"use_speaker_boost": 1}}, "true or false"),
        ({"seed": -1}, "seed"),
        ({"model_id": 3}, "model_id"),
    ],
)
def test_malformed_settings_raise(doc, match):
    with pytest.raises(ElevenLabsVoiceError, match=match):
        _tts()[0].synthesis_options(doc)


# --- provider scoping ----------------------------------------------------------


def test_a_voice_for_another_provider_is_handed_default():
    """An ElevenLabs-voiced project previews offline without a foreign voice id."""

    class _Recording(OfflineTTS):
        def __init__(self):
            super().__init__()
            self.voices = []

        def synthesize(self, text, voice_id="default", **kw):
            self.voices.append((voice_id, kw))
            return super().synthesize(text, voice_id, **kw)

    tts = _Recording()
    scene = _scene(Dialogue(speaker="bob", text="Hi!", direction=["excited"]))
    produce_audio_for_scene(scene, _mall({"bob": V3}), tts=tts, lipsync=_RecordingLipSync())
    assert tts.voices == [("default", {})]


# --- scene.md and JSON ---------------------------------------------------------


def test_direction_round_trips_through_scene_md():
    block = "```dialogue\nbob [happy] {excited}: Hi!\nned {sighs, annoyed} (pause 1): Fine.\n```"
    lines = _extract_dialogue_block(block)
    assert [line.direction for line in lines] == [["excited"], ["sighs", "annoyed"]]
    assert lines[0].emotion == "happy" and lines[1].pause == 1.0
    again = _extract_dialogue_block(
        "```dialogue\n" + "\n".join(_format_dialogue_line(x) for x in lines) + "\n```"
    )
    assert again == lines


@pytest.mark.parametrize("bad", ["a {}: x", "a {x} {y}: z", "a {[x]}: z", "a {x,}: z"])
def test_a_malformed_direction_is_a_parse_error(bad):
    with pytest.raises(SceneMarkdownError):
        _extract_dialogue_block(f"```dialogue\n{bad}\n```")


def test_json_omits_direction_when_unset():
    assert "direction" not in Dialogue(speaker="a", text="b").model_dump(mode="json")
    assert Dialogue(speaker="a", text="b", direction=["whispers"]).model_dump(mode="json")[
        "direction"
    ] == ["whispers"]


# --- validate ------------------------------------------------------------------


def test_validate_flags_bad_settings_and_a_dropped_direction():
    line = Dialogue(speaker="bob", text="Hi!", voice_ref="bob", direction=["excited"])
    ok = validate_semantic(_scene(line), available_voices={"bob": V3})
    assert not [f for f in ok.findings if "bob" in f.description or "direction" in f.ir_path]
    bad = validate_semantic(
        _scene(line),
        available_voices={"bob": {**V3, "voice_settings": {"speed": 3}}},
    )
    assert any(f.severity == "error" and "outside" in f.description for f in bad.findings)
    dropped = validate_semantic(
        _scene(line), available_voices={"bob": {"provider": "elevenlabs", "voice_id": "abc"}}
    )
    assert any(
        f.severity == "warning" and f.ir_path.endswith("/direction") for f in dropped.findings
    )


# --- browsing ------------------------------------------------------------------


class _Voice:
    def __init__(self, voice_id, name, **labels):
        self.voice_id, self.name, self.labels = voice_id, name, labels
        self.category, self.description = "premade", None


class _Page:
    def __init__(self, voices, token=None):
        self.voices, self.next_page_token, self.has_more = voices, token, token is not None


def test_list_voices_pages_and_formats():
    client = _FakeClient(
        pages=[_Page([_Voice("a1", "Ada", accent="british")], token="t"), _Page([_Voice("b2", "Bob")])]
    )
    tts, _ = _tts(client)
    voices = browse_voices("elevenlabs", search="x", make=lambda _name: tts)
    assert [v.voice_id for v in voices] == ["a1", "b2"]
    assert client.searches[0]["search"] == "x" and client.searches[1]["next_page_token"] == "t"
    assert format_voices(voices).splitlines() == ["a1  Ada  (accent=british)", "b2  Bob"]


def test_the_cli_mounts_voices_list():
    from typer.testing import CliRunner

    from an.__main__ import build_app

    result = CliRunner().invoke(build_app(), ["voices", "list", "--help"])
    assert result.exit_code == 0 and "--provider" in result.output
