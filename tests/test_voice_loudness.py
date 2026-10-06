"""One loudness for every voice (an#315): measured over each voice's lines,
one gain per voice, peaks held, timing untouched, derived audio content-keyed.

A four-voice scene reproduces the issue's measured spread (about -16, -35, -28
and -23 LUFS: 19 dB) with tones of those levels, spoken in short syllables.
"""

from __future__ import annotations

import io
import math
import warnings
import wave

import numpy as np
import pytest

from an.audio.loudness import (
    GAIN_STEP_DB,
    integrated_loudness,
    VoiceLoudnessWarning,
    leveled_audio,
    limit_peaks,
    loudness_report,
)
from an.audio.pipeline import produce_audio_for_scene
from an.audio.tts import AudioClip
from an.ir.schema import Dialogue, Meta, SceneIR, Shot, VoiceLoudness
from tests.test_shot_cache import fake_render  # noqa: F401 — the fixture, by name

RATE = 22050
#: The issue's measured levels, per voice (LUFS, as synthesized).
LEVELS = {"narrator": -16.4, "clone_a": -35.5, "clone_b": -28.4, "clone_c": -23.4}


def _speech(level_db: float, seconds: float, *, seed: int) -> bytes:
    """Syllables of a voiced tone at about ``level_db`` LUFS, with pauses; a
    loud plosive peak in each, so the limiter has work to do when raised."""
    rng = np.random.default_rng(seed)
    n = int(RATE * seconds)
    t = np.arange(n) / RATE
    syllables = (np.sin(2 * math.pi * 3.0 * t) > -0.2).astype(float)
    voice = np.sin(2 * math.pi * 180 * t) + 0.5 * np.sin(2 * math.pi * 360 * t)
    x = voice * syllables * (0.8 + 0.2 * rng.random(n))
    x /= np.sqrt(np.mean(x**2))
    x *= 10 ** ((level_db + 0.7) / 20)  # RMS dBFS -> roughly LUFS for this spectrum
    for start in range(int(0.1 * RATE), n, int(RATE / 3)):
        x[start] = 6 * x.std() * (1 if start % 2 else -1)  # plosives
    x = np.clip(x, -0.99, 0.99)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(np.rint(x * 32767).astype("<i2").tobytes())
    return buf.getvalue()


class _LevelTTS:
    """Each voice at its own level, as the providers deliver them."""

    name = "levels"
    repeatable = True
    billed = False

    def __init__(self):
        self.calls = 0

    def synthesize(self, text, voice_id="default", **kw):
        self.calls += 1
        seconds = 0.6 + 0.1 * (len(text) % 7)
        level = LEVELS.get(voice_id, -20.0) - (8.0 if "whisper" in text else 0.0)
        level += 1.0 if "a little louder" in text else 0.0
        data = _speech(level, seconds, seed=len(text))
        return AudioClip(bytes_=data, duration=seconds, voice_id=voice_id, transcript=text)

    def list_voices(self):
        return []


class _NoLipSync:
    name = "none"
    convention = "none"

    def align(self, audio, transcript):
        from an.audio.lipsync import NullLipSync

        return NullLipSync().align(audio, transcript)


def _scene(loudness=None, extra_line: str | None = None) -> SceneIR:
    shots = []
    for i, voice in enumerate(LEVELS):
        lines = [
            Dialogue(speaker=voice, text=f"line {k} of {voice}", voice_ref=voice)
            for k in range(3)
        ]
        if voice == "clone_b":  # a whisper first: the voice is measured whole
            lines[0] = Dialogue(speaker=voice, text="a whisper of clone_b", voice_ref=voice)
        if extra_line and voice == "clone_a":
            lines.append(Dialogue(speaker=voice, text=extra_line, voice_ref=voice))
        shots.append(Shot(id=f"s{i}", duration=8.0, dialogue=lines))
    return SceneIR(meta=Meta(title="t", voice_loudness=loudness), timeline=shots)


def _mall(**voices):
    return {
        "audio": {},
        "visemes": {},
        "voices": {v: {"provider": "levels", **voices.get(v, {})} for v in LEVELS},
    }


def _run(scene, mall, tts=None):
    return produce_audio_for_scene(scene, mall, tts=tts or _LevelTTS(), lipsync=_NoLipSync())


def _levels(scene, mall) -> dict[str, float]:
    return {v.voice: v.lufs for v in loudness_report(scene, mall)}


# -----------------------------------------------------------------------------
# No ffmpeg: the limiter
# -----------------------------------------------------------------------------


def test_the_limiter_holds_the_ceiling_and_moves_nothing_in_time():
    rng = np.random.default_rng(1)
    x = np.clip(rng.normal(0, 0.05, (4000, 2)), -0.4, 0.4)
    x[1000] = [3.0, -2.5]  # one peak far over
    out = limit_peaks(x, ceiling=0.5, window=40)
    assert np.abs(out).max() <= 0.5 + 1e-12
    assert out.shape == x.shape
    assert np.abs(out[1000]).max() == pytest.approx(0.5)  # the peak is still where it was
    far = np.ones(len(x), bool)
    far[900:1100] = False
    assert np.array_equal(out[far], x[far])  # away from the peak, untouched
    assert np.all(np.abs(out[960:1040]) <= np.abs(x[960:1040]))  # eased, never raised


# -----------------------------------------------------------------------------
# ffmpeg: measuring and leveling
# -----------------------------------------------------------------------------


@pytest.mark.ffmpeg
def test_the_issues_19_db_spread_is_brought_within_a_db_and_a_half():
    raw_mall = _mall()
    raw = _levels(_run(_scene(), raw_mall), raw_mall)
    assert max(raw.values()) - min(raw.values()) > 15  # the problem, reproduced
    mall = _mall()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        scene = _run(_scene(VoiceLoudness(target_lufs=-16)), mall)
    leveled = _levels(scene, mall)
    assert max(leveled.values()) - min(leveled.values()) <= 1.5, leveled
    assert all(abs(v + 16) <= 1.0 for v in leveled.values()), leveled  # the limiter's toll made up
    assert not [w for w in caught if "reaches" in str(w.message)]


@pytest.mark.ffmpeg
def test_leveling_changes_no_timing_and_holds_the_peaks():
    mall = _mall()
    scene = _run(_scene(VoiceLoudness(target_lufs=-16, peak_db=-1.5)), mall)
    raw_mall = _mall()
    raw = _run(_scene(), raw_mall)
    for shot, raw_shot in zip(scene.timeline, raw.timeline):
        for line, raw_line in zip(shot.dialogue, raw_shot.dialogue):
            assert line.audio_ref != raw_line.audio_ref
            assert (line.start, line.duration) == (raw_line.start, raw_line.duration)
            with wave.open(io.BytesIO(mall["audio"][line.audio_ref])) as a, wave.open(
                io.BytesIO(raw_mall["audio"][raw_line.audio_ref])
            ) as b:
                assert a.getnframes() == b.getnframes()
                s = np.frombuffer(a.readframes(a.getnframes()), "<i2") / 32768
            assert np.abs(s).max() <= 10 ** (-1.5 / 20)  # held after 16-bit rounding too


@pytest.mark.ffmpeg
def test_a_second_run_reuses_every_leveled_line():
    mall, tts = _mall(), _LevelTTS()
    first = _run(_scene(-16), mall, tts)
    refs = [line.audio_ref for shot in first.timeline for line in shot.dialogue]
    stored = set(mall["audio"])
    again = _run(_scene(-16), mall, tts)
    assert [line.audio_ref for shot in again.timeline for line in shot.dialogue] == refs
    assert set(mall["audio"]) == stored and tts.calls == 12  # nothing synthesised again


@pytest.mark.ffmpeg
def test_a_new_line_that_barely_moves_its_voice_relevels_nothing_else():
    mall = _mall()
    before = _run(_scene(-16), mall)
    after = _run(_scene(-16, extra_line="one more, a little louder, of clone_a"), mall)
    old = {line.text: line.audio_ref for s in before.timeline for line in s.dialogue}
    for shot in after.timeline:
        for line in shot.dialogue[:3]:
            assert line.audio_ref == old[line.text], line.text


@pytest.mark.ffmpeg
def test_a_voice_offset_and_a_silent_voice():
    mall = _mall(narrator={"loudness_offset_db": 3.0})
    scene = _run(_scene(-20), mall)
    levels = _levels(scene, mall)
    assert levels["narrator"] - levels["clone_b"] == pytest.approx(3.0, abs=1.0)
    silence = io.BytesIO()
    with wave.open(silence, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"\0\0" * RATE)

    class _Silent(_LevelTTS):
        def synthesize(self, text, voice_id="default", **kw):
            return AudioClip(bytes_=silence.getvalue(), duration=1.0, voice_id=voice_id, transcript=text)

    quiet_mall, plain_mall = _mall(), _mall()
    quiet = _run(_scene(-16), quiet_mall, _Silent())
    plain = _run(_scene(), plain_mall, _Silent())
    assert [d.audio_ref for s in quiet.timeline for d in s.dialogue] == [
        d.audio_ref for s in plain.timeline for d in s.dialogue
    ]  # silence is left as it is: not even re-stamped


@pytest.mark.ffmpeg
def test_without_a_target_a_wide_spread_is_warned_naming_each_voice():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _run(_scene(), _mall())
    (w,) = [w for w in caught if issubclass(w.category, VoiceLoudnessWarning)]
    text = str(w.message)
    assert "clone_a" in text and "narrator" in text and "voice_loudness" in text


@pytest.mark.ffmpeg
def test_leveled_audio_keeps_its_length_exactly():
    data = _speech(-35, 1.3, seed=3)
    out = leveled_audio(data, gain_db=19.0, peak_db=-1.5)
    with wave.open(io.BytesIO(data)) as a, wave.open(io.BytesIO(out)) as b:
        assert a.getnframes() == b.getnframes() and a.getframerate() == b.getframerate()


def test_the_gain_step_is_coarse_enough_to_absorb_a_line():
    assert 0.05 <= GAIN_STEP_DB <= 0.5


@pytest.mark.ffmpeg
def test_a_voices_own_dynamics_between_lines_are_kept():
    """One gain per voice: a whisper stays a whisper next to its voice's other
    lines. (Brought DOWN, so no peak is limited and the gain is all there is.)"""
    from an.audio.loudness import _decode

    mall = _mall()
    scene = _run(_scene(-36), mall)
    (shot,) = [s for s in scene.timeline if s.dialogue[0].speaker == "clone_b"]
    whisper, normal = (integrated_loudness(_decode(mall["audio"][d.audio_ref])) for d in shot.dialogue[:2])
    assert normal - whisper == pytest.approx(8.0, abs=1.0)


#: sha256 of ``leveled_audio`` on a fixed fixture, by LEVEL_VERSION. NEVER edit a
#: row: a red here means leveled bytes changed (limiter, window, encoding) —
#: bump LEVEL_VERSION, which moves every leveled key, and ADD a row.
LEVEL_GOLDEN: dict[int, str] = {1: "53a9646282646360d14aa6f3bf861ca587217532ea9a542986c56727aaec13b0"}


def test_leveled_bytes_change_only_with_the_level_version():
    import hashlib

    from an.audio import loudness

    out = loudness.leveled_audio(_speech(-30, 0.8, seed=5), gain_db=17.5, peak_db=-1.5)
    digest = hashlib.sha256(out).hexdigest()
    assert digest == LEVEL_GOLDEN.get(loudness.LEVEL_VERSION, digest), (
        "leveled bytes changed: bump LEVEL_VERSION and ADD a row (never edit one)"
    )
    assert loudness.LEVEL_VERSION in LEVEL_GOLDEN


@pytest.mark.ffmpeg
def test_a_take_resynthesised_under_the_same_request_is_leveled_again():
    """an#315 review: the leveled key names the source BYTES, so a lost raw
    take made again (other audio, same request) never reuses stale leveling."""

    class _Varying(_LevelTTS):
        def synthesize(self, text, voice_id="default", **kw):
            clip = super().synthesize(text + "!" * self.calls, voice_id, **kw)
            clip.transcript = text
            return clip

    mall, tts = _mall(), _Varying()
    first = _run(_scene(-16), mall, tts)
    old = {d.text: d.audio_ref for s in first.timeline for d in s.dialogue}
    from an.audio.pipeline import audio_key

    raw = audio_key("line 1 of narrator", "narrator", "levels")
    assert raw in mall["audio"]
    del mall["audio"][raw]  # the raw take is lost; the request is the same
    again = _run(_scene(-16), mall, tts)
    (line,) = [d for s in again.timeline for d in s.dialogue if d.text == "line 1 of narrator"]
    assert line.audio_ref != old["line 1 of narrator"]


# -----------------------------------------------------------------------------
# The adversarial review's cases (an#315)
# -----------------------------------------------------------------------------


def _wav(x, rate=RATE) -> bytes:
    x = np.atleast_2d(np.asarray(x, float).T).T
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.rint(np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


class _Fixed(_LevelTTS):
    """Each voice speaks the bytes given for it."""

    def __init__(self, by_voice):
        super().__init__()
        self.by_voice = by_voice

    def synthesize(self, text, voice_id="default", **kw):
        self.calls += 1
        data = self.by_voice[voice_id]
        with wave.open(io.BytesIO(data)) as w:
            seconds = w.getnframes() / w.getframerate()
        return AudioClip(bytes_=data, duration=seconds, voice_id=voice_id, transcript=text)


def _two_voices(narrator: bytes, other: bytes, target=-20):
    by = {"narrator": narrator, "clone_a": other, "clone_b": narrator, "clone_c": narrator}
    mall = _mall()
    scene = _run(_scene(target), mall, _Fixed(by))
    return scene, mall


@pytest.mark.ffmpeg
def test_a_voice_of_only_short_lines_is_leveled_not_taken_for_silence():
    short = _speech(-35, 0.12, seed=1)  # three of these are under one 400 ms gating block
    scene, mall = _two_voices(_speech(-20, 1.5, seed=2), short)
    levels = _levels(scene, mall)
    assert levels["clone_a"] == pytest.approx(-20, abs=1.5)


@pytest.mark.ffmpeg
def test_room_tone_is_not_raised_past_the_gain_cap():
    from an.audio.loudness import MAX_GAIN_DB

    rng = np.random.default_rng(0)
    tone = _wav(rng.normal(0, 10 ** (-60 / 20), RATE * 2))  # ~ -62 LUFS of noise
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        scene, mall = _two_voices(_speech(-20, 1.5, seed=2), tone)
    gains = {d.leveled["gain_db"] for s in scene.timeline for d in s.dialogue if d.speaker == "clone_a"}
    assert gains == {MAX_GAIN_DB}
    assert any("capped" in str(w.message) for w in caught)


def test_a_bad_offset_is_refused_with_its_bounds():
    from an.audio.loudness import VoiceLoudnessError, _offset

    for bad in ("loud", float("nan"), 200, True):
        with pytest.raises(VoiceLoudnessError, match="loudness_offset_db"):
            _offset({"voices": {"v": {"loudness_offset_db": bad}}}, "v")


@pytest.mark.ffmpeg
def test_a_warm_run_decodes_and_measures_nothing(monkeypatch):
    import an.audio.loudness as loudness
    import an.audio.pipeline as pipeline

    mall, tts = _mall(), _LevelTTS()
    scene = _run(_scene(-16), mall, tts)
    calls = {"measure": 0, "produce": 0}
    real_measure, real_produce = loudness.integrated_loudness, pipeline._produce_line
    monkeypatch.setattr(loudness, "integrated_loudness", lambda p: calls.__setitem__("measure", calls["measure"] + 1) or real_measure(p))
    monkeypatch.setattr(pipeline, "_produce_line", lambda *a, **k: calls.__setitem__("produce", calls["produce"] + 1) or real_produce(*a, **k))
    _run(scene, mall, tts)  # the same, stamped scene: nothing changed
    assert calls == {"measure": 0, "produce": 0}


@pytest.mark.ffmpeg
def test_uncorrelated_stereo_is_measured_as_stereo():
    rng = np.random.default_rng(3)
    mono = _speech(-30, 1.5, seed=4)
    with wave.open(io.BytesIO(mono)) as w:
        m = np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32768
    stereo = _wav(np.stack([m, rng.permutation(m)], axis=1))  # same level, uncorrelated
    scene, mall = _two_voices(mono, stereo)
    from an.audio.loudness import _decode

    heard = {
        d.speaker: integrated_loudness(_decode(mall["audio"][d.audio_ref]))  # as ffmpeg hears the file
        for s in scene.timeline for d in s.dialogue[:1] if d.speaker in ("narrator", "clone_a")
    }  # fmt: skip
    assert heard["clone_a"] == pytest.approx(heard["narrator"], abs=1.0)


@pytest.mark.ffmpeg
def test_turning_leveling_off_restores_the_lines_as_made():
    mall, tts = _mall(), _LevelTTS()
    raw = _run(_scene(), _mall(), _LevelTTS())
    leveled = _run(_scene(-16), mall, tts)
    leveled.meta.voice_loudness = None
    off = _run(leveled, mall, tts)
    assert [d.audio_ref for s in off.timeline for d in s.dialogue] == [
        d.audio_ref for s in raw.timeline for d in s.dialogue
    ]
    assert all(d.leveled is None for s in off.timeline for d in s.dialogue)


@pytest.mark.ffmpeg
def test_the_spread_is_said_once_not_on_every_warm_render():
    mall, tts = _mall(), _LevelTTS()
    scene = _run(_scene(), mall, tts)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _run(scene, mall, tts)
    assert not [w for w in caught if issubclass(w.category, VoiceLoudnessWarning)]


@pytest.mark.ffmpeg
def test_gc_after_a_target_edit_keys_the_new_leveling_in_memory(tmp_path, monkeypatch, fake_render):
    """an#315 review: after `target_lufs` changes and before any render, the
    collector re-levels in memory (an#311's overlay): it neither refuses nor
    writes to the audio store."""
    import an.audio.providers as providers
    from an.project import load
    from tests.test_shot_cache_gc import _gc, _project, _render, _shot, _voiced

    monkeypatch.setitem(providers.TTS_FACTORIES, "levels", lambda: _LevelTTS())
    root = _project(tmp_path, _shot("a", 10.0))
    _voiced(root, "hello there", "and again", voice={"provider": "levels"})

    def target(lufs):
        scenes = load(root).mall["scenes"]
        scene = scenes["main"]
        scene.meta.voice_loudness = VoiceLoudness(target_lufs=lufs)
        scenes["main"] = scene

    target(-16)
    _render(root, fake_render)
    audio = set(load(root).mall["audio"])
    target(-24)
    report = _gc(root)
    assert not [p for p, _ in report.reach.skipped if p["tts"] == "voice"]  # keyed, not skipped
    assert set(load(root).mall["audio"]) == audio  # the new leveling stayed in memory
