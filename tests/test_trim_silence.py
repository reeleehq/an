"""`effects: {trim_silence: ...}` — a line starts on its word (an#254).

eleven_v3 returned 1.6 s for "Hi!": 0.4 s of breath before the word and 0.65 s
of room tone after it, which pushed the next line past its shot. The trim is a
voice effect, so it inherits every rule the others obey: it runs after
synthesis and before alignment (the mouth, word timings and captions follow the
trimmed audio), the raw synthesis stays cached under its own key (turning it on
or off never re-bills the provider), and a voice that declares nothing keeps
every key it had. What was cut is recorded inside the WAV it wrote.

The pure tests need no ffmpeg: a 16-bit PCM WAV is trimmed in Python.
"""

from __future__ import annotations

import io
import math
import shutil
import subprocess
import wave

import numpy as np
import pytest

from an.audio import effects as effects_mod
from an.audio.effects import (
    DFLT_TRIM_KEEP_LEAD_S,
    DFLT_TRIM_KEEP_TAIL_S,
    TRIM_VERSION,
    VoiceEffectError,
    apply_voice_effects,
    normalize_effects,
    trim_record,
    trim_silence,
)
from an.audio.lipsync import Viseme, VisemeTrack
from an.audio.pipeline import audio_key, produce_audio_for_scene
from an.audio.tts import AudioClip
from an.ir.schema import Dialogue, Meta, SceneIR, Shot
from an.ir.validate import validate_semantic
from an.util import _stable_hash

RATE = 16000


def _padded_tone(
    lead_s=0.4, speech_s=0.5, tail_s=0.65, *, breath_db=None, channels=1, rate=RATE
) -> bytes:
    """Silence, a tone, silence — optionally a quiet 'breath' in the lead."""
    n_lead, n_speech, n_tail = (int(round(x * rate)) for x in (lead_s, speech_s, tail_s))
    t = np.arange(n_speech) / rate
    speech = 12000 * np.sin(2 * math.pi * 220 * t)
    lead = np.zeros(n_lead)
    if breath_db is not None:
        lead[:] = 12000 * 10 ** (breath_db / 20) * np.sin(2 * math.pi * 1500 * np.arange(n_lead) / rate)
    mono = np.concatenate([lead, speech, np.zeros(n_tail)]).astype("<i2")
    frames = np.repeat(mono[:, None], channels, axis=1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames.tobytes())
    return buf.getvalue()


def _seconds(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.getnframes() / w.getframerate()


# -----------------------------------------------------------------------------
# The declaration and the key
# -----------------------------------------------------------------------------


def test_true_resolves_every_default_into_the_key():
    assert normalize_effects({"trim_silence": True}) == {
        "trim_silence": {
            "keep_lead_s": DFLT_TRIM_KEEP_LEAD_S,
            "keep_tail_s": DFLT_TRIM_KEEP_TAIL_S,
            "threshold_db": -20.0,
            "version": TRIM_VERSION,
        }
    }
    custom = normalize_effects({"trim_silence": {"threshold_db": -45}})["trim_silence"]
    assert custom["threshold_db"] == -45.0 and custom["keep_lead_s"] == DFLT_TRIM_KEEP_LEAD_S


def test_a_voice_without_the_trim_keeps_every_key_it_had():
    legacy = _stable_hash({"text": "hi", "voice": "kid", "tts": "sine"})
    for off in ({}, {"trim_silence": False}, {"trim_silence": None}):
        assert audio_key("hi", "kid", "sine", normalize_effects(off)) == legacy
    trimmed = audio_key("hi", "kid", "sine", normalize_effects({"trim_silence": True}))
    assert trimmed != legacy
    assert trimmed != audio_key(
        "hi", "kid", "sine", normalize_effects({"trim_silence": {"keep_tail_s": 0.3}})
    )


@pytest.mark.parametrize(
    "bad, match",
    [
        ({"trim_silence": "yes"}, "true, false or a mapping"),
        ({"trim_silence": {"threshold": -20}}, "unknown trim_silence parameter"),
        ({"trim_silence": {"threshold_db": 5}}, "outside"),
        ({"trim_silence": {"keep_lead_s": -0.1}}, "outside"),
        ({"trim_silence": {"keep_tail_s": True}}, "must be a number"),
    ],
)
def test_a_bad_trim_is_refused_and_validate_says_so(bad, match):
    with pytest.raises(VoiceEffectError, match=match):
        normalize_effects(bad)
    scene = SceneIR(
        meta=Meta(title="t", duration=3.0),
        timeline=[Shot(id="s", duration=3.0, dialogue=[Dialogue(speaker="a", text="hi", voice_ref="kid")])],
    )
    report = validate_semantic(scene, available_voices={"kid": {"effects": bad}})
    assert any(f.severity == "error" and "trim_silence" in f.description for f in report.findings)


# -----------------------------------------------------------------------------
# The trim itself (pure, no ffmpeg)
# -----------------------------------------------------------------------------


def test_the_trim_keeps_the_word_and_a_little_of_each_side():
    cut = trim_silence(_padded_tone(), keep_lead_s=0.1, keep_tail_s=0.2)
    assert cut.lead_s == pytest.approx(0.3, abs=0.021)
    assert cut.tail_s == pytest.approx(0.45, abs=0.021)
    assert _seconds(cut.audio) == pytest.approx(0.1 + 0.5 + 0.2, abs=0.021)
    assert trim_record(cut.audio) == cut.record()
    assert cut.source_s == pytest.approx(1.55)


def test_a_breath_goes_at_the_default_and_stays_at_a_lower_threshold():
    """The measured eleven_v3 breath sat 25 dB under the word: -20 cuts it, -45 keeps it."""
    wav = _padded_tone(breath_db=-25)
    assert trim_silence(wav).lead_s == pytest.approx(0.4 - DFLT_TRIM_KEEP_LEAD_S, abs=0.021)
    assert trim_silence(wav, threshold_db=-45).lead_s == 0.0


def test_silence_is_left_whole_and_the_bytes_are_deterministic():
    silent = _padded_tone(speech_s=0.0)
    cut = trim_silence(silent)
    assert (cut.lead_s, cut.tail_s) == (0.0, 0.0)
    assert _seconds(cut.audio) == pytest.approx(_seconds(silent))
    wav = _padded_tone(channels=2)
    assert trim_silence(wav).audio == trim_silence(wav).audio
    with wave.open(io.BytesIO(trim_silence(wav).audio)) as w:
        assert (w.getnchannels(), w.getframerate()) == (2, RATE)


def test_the_record_is_where_readers_never_look():
    """After the samples, so the stdlib (and a naive 44-byte reader) reads the
    same audio; and audio the trim did not write has no record."""
    cut = trim_silence(_padded_tone())
    with wave.open(io.BytesIO(cut.audio)) as w:
        frames = w.readframes(w.getnframes())
    assert cut.audio[44 : 44 + len(frames)] == frames
    assert trim_record(_padded_tone()) is None and trim_record(b"not a wav") is None


def test_a_trim_alone_on_a_wav_needs_no_ffmpeg(monkeypatch):
    monkeypatch.setattr(effects_mod.shutil, "which", lambda name: None)
    out = apply_voice_effects(_padded_tone(), normalize_effects({"trim_silence": True}))
    assert _seconds(out) < 1.0 and trim_record(out) is not None


# -----------------------------------------------------------------------------
# Through the pipeline: the mouth, the duration and the timing follow
# -----------------------------------------------------------------------------


class _PaddedTTS:
    """A voice that pads every line: 0.4 s before the word, 0.65 s after it."""

    name = "padded"

    def __init__(self):
        self.calls = 0

    def synthesize(self, text, voice_id="default", **kw):
        self.calls += 1
        data = _padded_tone()
        return AudioClip(bytes_=data, duration=_seconds(data), voice_id=voice_id, transcript=text)

    def list_voices(self):
        return []


class _RecordingLipSync:
    name = "recording"
    convention = "rhubarb"

    def __init__(self):
        self.heard: list[bytes] = []

    def align(self, audio, transcript):
        self.heard.append(audio.bytes_)
        return VisemeTrack(visemes=[Viseme(0.0, "X")], duration=audio.duration)


def _scene():
    return SceneIR(
        meta=Meta(title="t", duration=4.0),
        timeline=[
            Shot(
                id="s",
                duration=4.0,
                dialogue=[
                    Dialogue(speaker="bob", text="Hi!", voice_ref="bob"),
                    Dialogue(speaker="bob", text="Bye.", voice_ref="bob"),
                ],
            )
        ],
    )


def _mall(effects=None):
    voice = {} if effects is None else {"effects": effects}
    return {"audio": {}, "visemes": {}, "voices": {"bob": voice}}


def test_a_trimming_voice_starts_on_its_word_and_the_mouth_follows():
    tts, ls = _PaddedTTS(), _RecordingLipSync()
    plain = produce_audio_for_scene(_scene(), _mall(), tts=tts, lipsync=_RecordingLipSync(), announce=None)
    mall = _mall({"trim_silence": True})
    trimmed = produce_audio_for_scene(_scene(), mall, tts=tts, lipsync=ls, announce=None)
    a, b = trimmed.timeline[0].dialogue
    p = plain.timeline[0].dialogue[0]
    assert p.duration == pytest.approx(1.55, abs=0.01)
    assert a.duration == pytest.approx(0.1 + 0.5 + 0.2, abs=0.021)
    # The next line moves up with it.
    assert b.start == pytest.approx(a.duration)
    # Lip sync was handed the trimmed audio — the bytes the line keeps.
    assert ls.heard[0] == mall["audio"][a.audio_ref]
    assert trim_record(mall["audio"][a.audio_ref])["lead_s"] == pytest.approx(0.3, abs=0.021)


def test_turning_the_trim_on_or_off_never_re_bills_the_provider():
    tts, ls = _PaddedTTS(), _RecordingLipSync()
    mall = _mall()
    scene = produce_audio_for_scene(_scene(), mall, tts=tts, lipsync=ls, announce=None)
    legacy_ref = scene.timeline[0].dialogue[0].audio_ref
    assert tts.calls == 2

    mall["voices"]["bob"]["effects"] = {"trim_silence": True}
    scene = produce_audio_for_scene(scene, mall, tts=tts, lipsync=ls, announce=None)
    assert scene.timeline[0].dialogue[0].audio_ref != legacy_ref
    assert tts.calls == 2  # the raw synthesis is reused; only the trim ran

    mall["voices"]["bob"]["effects"] = {}
    scene = produce_audio_for_scene(scene, mall, tts=tts, lipsync=ls, announce=None)
    assert scene.timeline[0].dialogue[0].audio_ref == legacy_ref
    assert tts.calls == 2


def test_an_overrun_names_the_trim_only_where_the_voice_does_not_trim():
    from an.audio.pipeline import dialogue_overruns

    def overrun(effects):
        mall = _mall(effects)
        scene = _scene()
        scene.timeline[0].duration = 1.0
        produce_audio_for_scene(scene, mall, tts=_PaddedTTS(), lipsync=_RecordingLipSync(), announce=None, overruns=False)
        return dialogue_overruns(scene, mall=mall)

    untrimmed = overrun(None)
    assert untrimmed and all("trim_silence" in m for m in untrimmed)
    trimmed = overrun({"trim_silence": True})
    assert trimmed and not any("trim_silence" in m for m in trimmed)


# -----------------------------------------------------------------------------
# A real voice's container: MP3 is decoded by ffmpeg, then trimmed
# -----------------------------------------------------------------------------


@pytest.mark.ffmpeg
def test_an_mp3_line_is_decoded_then_trimmed():
    mp3 = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "mp3", "pipe:1"],
        input=_padded_tone(),
        capture_output=True,
        check=True,
    ).stdout
    out = apply_voice_effects(mp3, normalize_effects({"trim_silence": True}))
    assert out[:4] == b"RIFF"
    assert _seconds(out) == pytest.approx(0.8, abs=0.06)
    assert trim_record(out)["source_s"] > 1.5


@pytest.mark.ffmpeg
def test_a_trim_after_a_tempo_keeps_its_padding_in_heard_seconds():
    out = apply_voice_effects(_padded_tone(), normalize_effects({"tempo": 2.0, "trim_silence": True}))
    # 0.5 s of tone at double speed is 0.25 s; the padding is NOT halved.
    assert _seconds(out) == pytest.approx(0.1 + 0.25 + 0.2, abs=0.03)
    assert shutil.which("ffmpeg")
