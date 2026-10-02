"""Voice effects (an#163): a `pitch_semitones` declared on the voice document.

The rules under test: the effect is applied after synthesis and before
alignment; the audio cache keys on it and on nothing else new; a voice that
declares none keeps every key it had; the shift preserves duration so word
timings still land; and a bad declaration is refused, never ignored.
"""

from __future__ import annotations

import array
import io
import math
import wave

import pytest

from an.audio.effects import (
    VoiceEffectError,
    apply_voice_effects,
    filter_chain,
    normalize_effects,
    voice_effects,
)
from cutan.audio.injectable_lipsync import StaticWordTimings, WordTimingsLipSync
from an.audio.lipsync import Viseme, VisemeTrack
from an.audio.pipeline import audio_key, produce_audio_for_scene, viseme_key
from an.audio.tts import AudioClip
from an.ir.schema import Dialogue, Meta, SceneIR, Shot
from an.ir.validate import validate_semantic
from an.util import _stable_hash

pytestmark = pytest.mark.genre("cutout_animation")


RATE = 22050
TONE_HZ = 440.0
DURATION_S = 1.5


def _sine_wav(hz=TONE_HZ, seconds=DURATION_S, rate=RATE) -> bytes:
    n = int(rate * seconds)
    frames = b"".join(
        int(12000 * math.sin(2 * math.pi * hz * i / rate)).to_bytes(2, "little", signed=True)
        for i in range(n)
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def _measure(wav_bytes: bytes) -> tuple[float, float]:
    """(fundamental Hz by upward zero crossings over the middle, duration s)."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, n = w.getframerate(), w.getnframes()
        samples = array.array("h", w.readframes(n))
    mid = samples[n // 4 : 3 * n // 4]
    ups = sum(1 for a, b in zip(mid, mid[1:]) if a < 0 <= b)
    return ups / (len(mid) / rate), n / rate


class _SineTTS:
    name = "sine"

    def __init__(self):
        self.calls = 0

    def synthesize(self, text, voice_id="default", **kw):
        self.calls += 1
        return AudioClip(bytes_=_sine_wav(), duration=DURATION_S, voice_id=voice_id, transcript=text)

    def list_voices(self):
        return []


class _RecordingLipSync:
    """Aligns nothing; records the audio it was handed."""

    name = "recording"
    convention = "rhubarb"

    def __init__(self):
        self.heard: list[bytes] = []

    def align(self, audio, transcript):
        self.heard.append(audio.bytes_)
        return VisemeTrack(visemes=[Viseme(0.0, "X")], duration=audio.duration)


def _scene(voice="kid", text="Hold the shape"):
    return SceneIR(
        meta=Meta(title="t", duration=3.0),
        timeline=[
            Shot(id="s", renderer="cutout", duration=3.0,
                 dialogue=[Dialogue(speaker="a", text=text, voice_ref=voice)])
        ],
    )


def _mall(effects=None):
    voice = {"provider": "sine"} | ({"effects": effects} if effects is not None else {})
    return {"audio": {}, "visemes": {}, "voices": {"kid": voice}}


# --- pure: no ffmpeg ---------------------------------------------------------


def test_no_effect_means_no_key_change():
    """The whole no-regression promise: the key of a line whose voice declares
    nothing is the key it had before effects existed."""
    legacy = _stable_hash({"text": "hi", "voice": "kid", "tts": "sine"})
    assert audio_key("hi", "kid", "sine") == legacy
    assert audio_key("hi", "kid", "sine", {}) == legacy
    assert audio_key("hi", "kid", "sine", normalize_effects({"pitch_semitones": 0})) == legacy
    assert audio_key("hi", "kid", "sine", {"pitch_semitones": 4.0}) != legacy
    assert audio_key("hi", "kid", "sine", {"pitch_semitones": 4.0}) != audio_key(
        "hi", "kid", "sine", {"pitch_semitones": 5.0}
    )
    legacy_v = _stable_hash({"audio_key": legacy, "lipsync": "offline", "transcript": "hi"})
    assert viseme_key(legacy, "offline", "hi") == legacy_v


def test_the_pipeline_stamps_the_legacy_ref_when_no_effect_is_declared():
    scene = produce_audio_for_scene(_scene(), _mall(), tts=_SineTTS(), lipsync=_RecordingLipSync())
    line = scene.timeline[0].dialogue[0]
    assert line.audio_ref == _stable_hash({"text": "Hold the shape", "voice": "kid", "tts": "sine"})


@pytest.mark.parametrize(
    "bad, match",
    [
        ({"reverb": 1}, "unknown voice effect"),
        ({"pitch_semitones": "high"}, "must be a number"),
        ({"pitch_semitones": True}, "must be a number"),
        ({"pitch_semitones": 13}, "outside"),
        ({"pitch_semitones": -12.5}, "outside"),
        (["pitch_semitones"], "mapping"),
    ],
)
def test_a_bad_declaration_is_refused(bad, match):
    with pytest.raises(VoiceEffectError, match=match):
        normalize_effects(bad)


def test_voice_effects_lookup_tolerates_absent_stores_and_voices():
    assert voice_effects(None, "kid") == {}
    assert voice_effects({}, "kid") == {}
    assert voice_effects({"voices": {}}, "kid") == {}
    assert voice_effects({"voices": {"kid": {"provider": "x"}}}, "kid") == {}
    assert voice_effects(_mall({"pitch_semitones": 4}), "kid") == {"pitch_semitones": 4.0}


def test_the_chain_is_stock_ffmpeg_and_duration_neutral():
    chain = filter_chain({"pitch_semitones": 4.0})
    assert "rubberband" not in chain
    assert chain.split(",")[1].startswith("asetrate=") and "atempo=" in chain
    ratio = 2 ** (4 / 12)
    assert float(chain.rsplit("atempo=", 1)[1]) == pytest.approx(1 / ratio, rel=1e-8)
    assert filter_chain({}) == ""


def test_validate_flags_an_invalid_effect_on_a_used_voice():
    good = validate_semantic(_scene(), available_voices=_mall({"pitch_semitones": 4})["voices"])
    assert not [f for f in good.findings if "kid" in f.description]
    bad = validate_semantic(_scene(), available_voices=_mall({"pitch_semitones": 40})["voices"])
    assert any(f.severity == "error" and "outside" in f.description for f in bad.findings)


# --- ffmpeg ------------------------------------------------------------------


@pytest.mark.ffmpeg
def test_a_raised_voice_is_higher_and_the_same_length():
    wav = _sine_wav()
    for semitones in (12.0, 4.0, -5.0):
        out = apply_voice_effects(wav, {"pitch_semitones": semitones})
        hz, dur = _measure(out)
        assert hz == pytest.approx(TONE_HZ * 2 ** (semitones / 12), rel=0.03)
        assert dur == pytest.approx(DURATION_S, abs=0.05)


@pytest.mark.ffmpeg
def test_the_shifted_bytes_are_deterministic():
    wav = _sine_wav()
    a = apply_voice_effects(wav, {"pitch_semitones": 4.0})
    assert a == apply_voice_effects(wav, {"pitch_semitones": 4.0})
    assert a != wav


@pytest.mark.ffmpeg
def test_no_effects_returns_the_audio_untouched():
    wav = _sine_wav()
    assert apply_voice_effects(wav, {}) is wav


@pytest.mark.ffmpeg
def test_the_pipeline_aligns_the_audio_that_is_heard_and_keeps_word_timings():
    """Lip-sync reads the shifted bytes; the duration (hence the timings) is
    preserved to well under a frame at 24 fps."""
    words = [("Hold", 0.05, 0.30), ("the", 0.32, 0.45), ("shape", 0.50, 0.90)]
    ls = WordTimingsLipSync(StaticWordTimings(words))
    raw_scene = produce_audio_for_scene(_scene(), _mall(), tts=_SineTTS(), lipsync=ls)
    mall = _mall({"pitch_semitones": 4})
    fx_scene = produce_audio_for_scene(_scene(), mall, tts=_SineTTS(), lipsync=ls)
    raw, fx = raw_scene.timeline[0].dialogue[0], fx_scene.timeline[0].dialogue[0]

    assert fx.audio_ref != raw.audio_ref and fx.viseme_ref != raw.viseme_ref
    assert fx.duration == pytest.approx(raw.duration, abs=0.5 / 24)
    assert [(w.text, w.start, w.end) for w in fx.word_timings] == [
        (w.text, w.start, w.end) for w in raw.word_timings
    ]
    hz, _ = _measure(mall["audio"][fx.audio_ref])
    assert hz == pytest.approx(TONE_HZ * 2 ** (4 / 12), rel=0.03)

    rec = _RecordingLipSync()
    mall2 = _mall({"pitch_semitones": 4})
    produce_audio_for_scene(_scene(), mall2, tts=_SineTTS(), lipsync=rec)
    assert rec.heard == [mall2["audio"][fx.audio_ref]]  # aligned the SHIFTED bytes


@pytest.mark.ffmpeg
def test_changing_the_effect_resynthesizes_only_the_effect_not_the_tts():
    tts, rec = _SineTTS(), _RecordingLipSync()
    mall = _mall({"pitch_semitones": 4})
    scene = produce_audio_for_scene(_scene(), mall, tts=tts, lipsync=rec)
    ref4 = scene.timeline[0].dialogue[0].audio_ref
    assert (tts.calls, len(rec.heard)) == (1, 1)

    # Unchanged: fully idempotent.
    produce_audio_for_scene(scene, mall, tts=tts, lipsync=rec)
    assert (tts.calls, len(rec.heard)) == (1, 1)

    # A new pitch: the raw synthesis is reused, the effect and alignment redone.
    mall["voices"]["kid"]["effects"] = {"pitch_semitones": 6}
    scene = produce_audio_for_scene(scene, mall, tts=tts, lipsync=rec)
    ref6 = scene.timeline[0].dialogue[0].audio_ref
    assert ref6 != ref4
    assert (tts.calls, len(rec.heard)) == (1, 2)

    # Removing the effect returns to the legacy key, still without a TTS call.
    del mall["voices"]["kid"]["effects"]
    scene = produce_audio_for_scene(scene, mall, tts=tts, lipsync=rec)
    assert scene.timeline[0].dialogue[0].audio_ref == audio_key("Hold the shape", "kid", "sine")
    assert tts.calls == 1


@pytest.mark.ffmpeg
def test_an_mp3_or_other_container_is_accepted_as_input():
    import subprocess

    mp3 = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "mp3", "pipe:1"],
        input=_sine_wav(), capture_output=True, check=True,
    ).stdout
    out = apply_voice_effects(mp3, {"pitch_semitones": 4.0})
    assert out[:4] == b"RIFF"
    assert _measure(out)[1] == pytest.approx(DURATION_S, abs=0.15)  # mp3 padding
