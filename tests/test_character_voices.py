"""A voice per character (an#194): the speaker's descriptor binds its voice.

The rules under test: a line's own ``voice_ref`` wins, then the speaking
entity's ``overrides.voice_ref``, then its descriptor's ``voice_ref``, then
``default``; a voice document's ``voice_id`` is what the TTS provider is
handed; and a project that declares none of it keeps every cache key it had.
"""

from __future__ import annotations

import pytest

from an.audio.pipeline import audio_key, produce_audio_for_scene, viseme_key
from an.audio.tts import AudioClip
from an.characters import new_character
from an.ir.schema import AssetRef, Dialogue, Meta, SceneIR, Shot
from an.ir.validate import validate_semantic
from an.project import init
from an.stores import build_project_mall
from an.util import _stable_hash

from tests.test_voice_effects import _RecordingLipSync, _sine_wav, DURATION_S


class _VoiceRecordingTTS:
    """A sine for every line; records the voice id the provider was handed."""

    name = "sine"

    def __init__(self):
        self.voices: list[str] = []

    def synthesize(self, text, voice_id="default", **kw):
        self.voices.append(voice_id)
        return AudioClip(bytes_=_sine_wav(), duration=DURATION_S, voice_id=voice_id, transcript=text)

    def list_voices(self):
        return []


def _mall(tmp_path, *, bind: bool):
    root = init(tmp_path / "p")
    mall = build_project_mall(root)
    ch = root / "assets" / "characters"
    new_character(ch, name="carl", use_dicebear=False, voice_ref="carl_voice" if bind else None)
    new_character(ch, name="ned", use_dicebear=False, voice_ref="ned_voice" if bind else None)
    return mall


def _scene(*lines, overrides=None):
    return SceneIR(
        meta=Meta(title="t", duration=4.0),
        timeline=[
            Shot(
                id="s",
                duration=4.0,
                entities=[
                    AssetRef(kind="character", id="carl", store="characters", ref="carl"),
                    AssetRef(
                        kind="character", id="ned", store="characters", ref="ned",
                        overrides=overrides,
                    ),
                ],
                dialogue=list(lines),
            )
        ],
    )


def test_nothing_declared_keeps_every_cache_key(tmp_path):
    """The no-regression promise: with no binding and no voice document, every
    line is keyed exactly as before an#194 — voice "default", no new field."""
    mall = _mall(tmp_path, bind=False)
    tts, lip = _VoiceRecordingTTS(), _RecordingLipSync()
    scene = _scene(Dialogue(speaker="carl", text="Hi!"), Dialogue(speaker="ned", text="Bye."))
    produce_audio_for_scene(scene, mall, tts=tts, lipsync=lip)
    for line in scene.timeline[0].dialogue:
        legacy = _stable_hash({"text": line.text, "voice": "default", "tts": "sine"})
        assert line.audio_ref == legacy
        assert line.viseme_ref == _stable_hash(
            {"audio_key": legacy, "lipsync": "recording", "transcript": line.text}
        )
    assert tts.voices == ["default", "default"]
    assert audio_key("x", "v", "t", provider_voice=None) == audio_key("x", "v", "t")


@pytest.mark.ffmpeg
def test_two_characters_speak_two_voices_at_two_pitches(tmp_path):
    """The skill's example: each descriptor binds a voice document, which names
    the provider voice and carries a pitch."""
    mall = _mall(tmp_path, bind=True)
    mall["voices"]["carl_voice"] = {"voice_id": "Junior", "effects": {"pitch_semitones": 5}}
    mall["voices"]["ned_voice"] = {"voice_id": "Ralph", "effects": {"pitch_semitones": 2}}
    tts, lip = _VoiceRecordingTTS(), _RecordingLipSync()
    scene = _scene(Dialogue(speaker="carl", text="Hi!"), Dialogue(speaker="ned", text="Bye."))
    produce_audio_for_scene(scene, mall, tts=tts, lipsync=lip)
    carl, ned = scene.timeline[0].dialogue
    assert tts.voices == ["Junior", "Ralph"]
    assert carl.audio_ref == audio_key(
        "Hi!", "carl_voice", "sine", {"pitch_semitones": 5.0}, provider_voice="Junior"
    )
    assert ned.audio_ref == audio_key(
        "Bye.", "ned_voice", "sine", {"pitch_semitones": 2.0}, provider_voice="Ralph"
    )
    # Pitched differently: the two lines' audio differs though the TTS is one sine.
    assert mall["audio"][carl.audio_ref] != mall["audio"][ned.audio_ref]
    assert carl.viseme_ref == viseme_key(carl.audio_ref, "recording", "Hi!")


def test_precedence_line_then_overrides_then_descriptor(tmp_path):
    mall = _mall(tmp_path, bind=True)
    tts, lip = _VoiceRecordingTTS(), _RecordingLipSync()
    scene = _scene(
        Dialogue(speaker="carl", text="Mine.", voice_ref="own"),
        Dialogue(speaker="carl", text="Bound."),
        Dialogue(speaker="ned", text="Shot-local."),
        Dialogue(speaker="narrator", text="Off screen."),
        overrides={"voice_ref": "ned_whisper"},
    )
    produce_audio_for_scene(scene, mall, tts=tts, lipsync=lip)
    # No document for any of them, so each store key is handed over as is.
    assert tts.voices == ["own", "carl_voice", "ned_whisper", "default"]
    # The binding is resolved, never stamped: scene.md has no per-line syntax
    # to carry it, so a stamped voice_ref would be lost on the next edit.
    assert [d.voice_ref for d in scene.timeline[0].dialogue] == ["own", None, None, None]


def test_a_rerun_is_idempotent_with_a_binding(tmp_path):
    mall = _mall(tmp_path, bind=True)
    tts, lip = _VoiceRecordingTTS(), _RecordingLipSync()
    scene = _scene(Dialogue(speaker="carl", text="Hi!"))
    produce_audio_for_scene(scene, mall, tts=tts, lipsync=lip)
    produce_audio_for_scene(scene, mall, tts=tts, lipsync=lip)
    assert tts.voices == ["carl_voice"]


def test_validate_warns_about_a_bound_voice_missing_from_the_store(tmp_path):
    mall = _mall(tmp_path, bind=True)
    mall["voices"]["ned_voice"] = {"effects": {"pitch_semitones": 40}}
    scene = _scene(Dialogue(speaker="carl", text="Hi!"), Dialogue(speaker="ned", text="Bye."))
    report = validate_semantic(
        scene,
        available_voices=mall["voices"],
        available_characters=mall["characters"],
    )
    by_path = {f.ir_path: f for f in report.findings}
    carl = by_path["timeline/0/dialogue/0/voice_ref"]
    assert carl.severity == "warning" and "character 'carl' is bound to" in carl.description
    # A bound voice's effects are checked like a line's own.
    assert by_path["timeline/0/dialogue/1/voice_ref"].severity == "error"
