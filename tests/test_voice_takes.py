"""Best-of-N takes and the tempo effect (an#265).

The rules under test:

- one take (the default) and no ``tempo`` keep every audio key a project had;
- the kept take is chosen by its score on the audio the viewer HEARS (effects
  applied), ties go to the lower take, and the choice is recorded;
- a re-render never re-rolls: the kept take is read back, and with the takes
  cached the same take is chosen again even if the kept audio was deleted;
- take 0 is the single-take request, so turning takes on pays only for the rest;
- the cost is announced before the first request, and a cached take is free;
- a ``tempo`` changes the line's duration, and lip-sync (hence word timings and
  captions) reads the re-timed audio.

No test reaches a provider: the TTS is a fake that returns tones.
"""

from __future__ import annotations

import io
import json
import math
import warnings
import wave

import numpy as np
import pytest

from an.audio.effects import VoiceEffectError, atempo_stages, filter_chain, normalize_effects
from an.audio.elevenlabs_tts import ElevenLabsTTS
from an.audio.lipsync import Viseme, VisemeTrack
from an.audio.pipeline import (
    TakeLostWarning,
    audio_key,
    produce_audio_for_scene,
    takes_cost_message,
)
from an.audio.takes import (
    ProsodyTakeScorer,
    TakeScore,
    TakesSpec,
    VoiceTakesError,
    choose_take,
    decode_for_scoring,
    style_voice_role,
    takes_key_part,
    takes_spec,
    voice_takes,
)
from an.audio.tts import AudioClip
from an.ir.schema import Dialogue, Meta, SceneIR, Shot
from an.util import _stable_hash

RATE = 16000
TEXT = "one two three four five six"  # six syllables


def _tone(seconds: float, *, hz: float = 150.0, rate: int = RATE) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    pcm = (0.3 * 32767 * np.sin(2 * math.pi * hz * t)).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _duration(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.getnframes() / w.getframerate()


class _TakesTTS:
    """Each call returns the next duration in ``durations`` (cycling), as a tone."""

    name = "tones"

    def __init__(self, durations=(2.0, 1.0, 0.6), *, events=None):
        self.durations = list(durations)
        self.calls: list[dict] = []
        self.events = events if events is not None else []

    def synthesize(self, text, voice_id="default", **kw):
        seconds = self.durations[len(self.calls) % len(self.durations)]
        self.calls.append(kw)
        self.events.append("synthesize")
        return AudioClip(bytes_=_tone(seconds), duration=seconds, voice_id=voice_id, transcript=text)

    def list_voices(self):
        return []


class _DurationScorer:
    """Prefers the take whose length is closest to ``target_s`` (no ffmpeg, no estimator)."""

    name = "duration"
    version = "test"

    def __init__(self, target_s: float):
        self.config = {"target_s": target_s}
        self.target_s = target_s

    def score(self, audio, text):
        d = _duration(audio)
        return TakeScore((round(abs(d - self.target_s), 6),), {"duration_s": round(d, 3)})


def _duration_scorer(spec: TakesSpec):
    return _DurationScorer(spec.targets["articulation_rate_sps"][0])


class _Recording:
    name = "recording"
    convention = "rhubarb"

    def __init__(self):
        self.heard: list[bytes] = []

    def align(self, audio, transcript):
        self.heard.append(audio.bytes_)
        return VisemeTrack(visemes=[Viseme(0.0, "X")], duration=audio.duration)


def _scene(*, text=TEXT, direction=None):
    return SceneIR(
        meta=Meta(title="t", duration=4.0),
        timeline=[
            Shot(id="s", renderer="cutout", duration=4.0,
                 dialogue=[Dialogue(speaker="a", text=text, voice_ref="nar", direction=direction)])
        ],
    )


def _mall(voice: dict | None = None):
    return {"audio": {}, "visemes": {}, "takes": {}, "voices": {"nar": dict(voice or {})}}


#: With the duration scorer, the "target" rides in articulation_rate_sps[0] (seconds).
def _takes(n=3, target_s=1.0, **extra):
    return {"n": n, "targets": {"articulation_rate_sps": [target_s, target_s + 1]}, **extra}


def _run(scene, mall, tts, **kw):
    kw.setdefault("lipsync", _Recording())
    kw.setdefault("take_scorer", _duration_scorer)
    kw.setdefault("announce", None)
    return produce_audio_for_scene(scene, mall, tts=tts, **kw)


# --- the declaration ---------------------------------------------------------


def test_one_take_and_no_declaration_keep_every_key():
    legacy = _stable_hash({"text": "hi", "voice": "nar", "tts": "tones"})
    assert audio_key("hi", "nar", "tones", takes=None, take=0) == legacy
    for decl in (None, 1, {"n": 1}, {"n": 1, "targets": {"f0_sd_st": [2, 4]}}):
        assert takes_spec(decl) is None
    scene = _run(_scene(text="hi"), _mall({"takes": 1}), _TakesTTS())
    assert scene.timeline[0].dialogue[0].audio_ref == legacy


@pytest.mark.parametrize(
    "decl, message",
    [
        ({"n": 0}, "integer from 1 to"),
        ({"n": 99}, "integer from 1 to"),
        ({"n": 3}, "needs `targets`"),
        ({"n": 2, "targets": "narrator"}, "style_voice_role"),
        ({"n": 2, "targets": {"swagger": [0, 1]}}, "unknown prosody target"),
        ({"n": 2, "tagets": {}}, "unknown takes key"),
        (True, "number of takes or a mapping"),
    ],
)
def test_a_bad_declaration_is_refused(decl, message):
    with pytest.raises(VoiceTakesError, match=message):
        takes_spec(decl)


def test_a_bad_declaration_fails_before_any_request():
    tts = _TakesTTS()
    with pytest.raises(VoiceTakesError):
        _run(_scene(), _mall({"takes": {"n": 3}}), tts)
    assert tts.calls == []


def test_cues_opt_lines_in_and_override_the_voice():
    decl = {"n": 1, "targets": {"f0_sd_st": [3, 5]},
            "cues": {"deadpan": {"n": 4, "targets": {"f0_sd_st": [2, 3]}}, "excited": 2}}
    assert takes_spec(decl, direction=None) is None
    dead = takes_spec(decl, direction=["sighs", "deadpan"])
    assert (dead.n, dict(dead.targets)) == (4, {"f0_sd_st": [2.0, 3.0]})
    excited = takes_spec(decl, direction=["excited"])
    assert (excited.n, dict(excited.targets)) == (2, {"f0_sd_st": [3.0, 5.0]})


def test_takes_are_scoped_to_the_voice_provider():
    mall = _mall({"provider": "elevenlabs", "takes": _takes()})
    assert voice_takes(mall, "nar", tts_name="offline") is None
    assert voice_takes(mall, "nar", tts_name="elevenlabs").n == 3
    assert voice_takes(mall, "absent", tts_name="elevenlabs") is None


def test_the_key_covers_n_the_scorer_and_its_configuration():
    def key(spec, scorer):
        return audio_key("hi", "nar", "tones", takes=takes_key_part(scorer, spec.n))

    base = TakesSpec(n=3, targets={"f0_sd_st": [2.0, 4.0]})
    scorer = ProsodyTakeScorer(base.targets)
    keys = {
        key(base, scorer),
        key(TakesSpec(n=4, targets=base.targets), scorer),
        key(base, ProsodyTakeScorer({"f0_sd_st": [2.0, 5.0]})),
        key(base, ProsodyTakeScorer(base.targets, reference_hz=120)),
        audio_key("hi", "nar", "tones"),
    }
    assert len(keys) == 5
    assert "estimator" in scorer.version


def test_choose_take_is_the_lowest_score_ties_to_the_first():
    s = [TakeScore((1.0, 0.0)), TakeScore((0.0, 0.5)), TakeScore((0.0, 0.5))]
    assert choose_take(s) == 1
    with pytest.raises(VoiceTakesError):
        choose_take([])


def test_style_voice_role_resolves_target_names_into_values():
    spec = {
        "live": {"voice": {"roles": {"narrator": {"model_id": "eleven_v3", "effects": {"tempo": 1.1},
                                                   "takes": {"n": 3, "targets": "narrator"}}}}},
        "prosody_targets": {"narrator": {"f0_sd_st": [3.9, 5.2]}},
    }
    role = style_voice_role(spec, "narrator")
    assert role["takes"]["targets"] == {"f0_sd_st": [3.9, 5.2]}
    assert role["effects"] == {"tempo": 1.1}
    assert spec["live"]["voice"]["roles"]["narrator"]["takes"]["targets"] == "narrator"  # a copy
    with pytest.raises(VoiceTakesError, match="no voice role"):
        style_voice_role(spec, "villain")
    spec["live"]["voice"]["roles"]["narrator"]["takes"]["targets"] = "missing"
    with pytest.raises(VoiceTakesError, match="do not have"):
        style_voice_role(spec, "narrator")


# --- choosing, recording, reusing -------------------------------------------


def test_the_best_take_is_kept_and_the_choice_recorded():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3, target_s=1.0)})
    line = _run(_scene(), mall, tts).timeline[0].dialogue[0]
    assert len(tts.calls) == 3
    assert line.duration == pytest.approx(1.0)
    kept = mall["audio"][line.audio_ref]
    assert _duration(kept) == pytest.approx(1.0)

    record = json.loads(mall["takes"][line.audio_ref])
    assert record["chosen"] == 1
    assert record["scorer"] == {"n": 3, "scorer": "duration", "version": "test",
                                "config": {"target_s": 1.0}}
    assert [t["take"] for t in record["takes"]] == [0, 1, 2]
    assert [t["duration_s"] for t in record["takes"]] == [2.0, 1.0, 0.6]
    import hashlib

    assert record["digest"] == hashlib.sha256(kept).hexdigest()
    # every take's raw audio stays cached under its own key; take 0 under the plain key
    assert record["takes"][0]["audio_key"] == audio_key(TEXT, "nar", "tones")
    assert all(t["audio_key"] in mall["audio"] for t in record["takes"])


def test_a_rerender_never_rerolls():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    ref = _run(_scene(), mall, tts).timeline[0].dialogue[0].audio_ref
    # a fresh, unstamped scene (as after editing scene.md) reads the kept take back
    again = _run(_scene(), mall, tts).timeline[0].dialogue[0]
    assert (again.audio_ref, len(tts.calls)) == (ref, 3)
    # the kept audio deleted, the takes cached: re-chosen from the cache, identically
    del mall["audio"][ref]
    with warnings.catch_warnings():
        warnings.simplefilter("error", TakeLostWarning)
        again = _run(_scene(), mall, tts).timeline[0].dialogue[0]
    assert again.audio_ref == ref and len(tts.calls) == 3
    assert _duration(mall["audio"][ref]) == pytest.approx(1.0)


def test_a_lost_take_is_rechosen_loudly():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    ref = _run(_scene(), mall, tts).timeline[0].dialogue[0].audio_ref
    first = json.loads(mall["takes"][ref])
    mall["audio"].clear()  # every take gone: the next takes differ
    tts.durations = [1.1, 3.0, 2.5]
    with pytest.warns(TakeLostWarning, match="no longer in the audio store"):
        _run(_scene(), mall, tts)
    record = json.loads(mall["takes"][ref])
    assert record["supersedes"] == first["digest"] and record["chosen"] == 0


def test_turning_takes_on_reuses_the_single_take_as_take_zero():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall()
    _run(_scene(), mall, tts)
    assert len(tts.calls) == 1
    mall["voices"]["nar"]["takes"] = _takes(3, target_s=2.0)
    line = _run(_scene(), mall, tts).timeline[0].dialogue[0]
    assert len(tts.calls) == 3  # two new takes, not three
    assert json.loads(mall["takes"][line.audio_ref])["chosen"] == 0


def test_changing_the_targets_chooses_again_from_the_cached_takes():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3, target_s=1.0)})
    a = _run(_scene(), mall, tts).timeline[0].dialogue[0].audio_ref
    mall["voices"]["nar"]["takes"] = _takes(3, target_s=0.5)
    b = _run(_scene(), mall, tts).timeline[0].dialogue[0]
    assert b.audio_ref != a and len(tts.calls) == 3
    assert json.loads(mall["takes"][b.audio_ref])["chosen"] == 2


def test_a_per_cue_takes_line_rerolls_and_its_neighbours_do_not():
    decl = {"cues": {"deadpan": _takes(3)}}
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": decl})
    scene = _scene(direction=["deadpan"])
    scene.timeline[0].dialogue.append(Dialogue(speaker="a", text="plain line", voice_ref="nar"))
    _run(scene, mall, tts)
    assert len(tts.calls) == 4
    assert len(mall["takes"]) == 1


def test_elevenlabs_takes_offset_a_declared_seed():
    class Client:
        def __init__(self):
            self.requests = []
            self.text_to_speech = self

        def convert(self, **request):
            self.requests.append(request)
            yield _tone(1.0 + 0.1 * len(self.requests))

    client = Client()
    tts = ElevenLabsTTS(api_key="unused", client_factory=lambda _key: client)
    mall = _mall({"provider": "elevenlabs", "seed": 11, "takes": _takes(3)})
    _run(_scene(), mall, tts)
    assert [r["seed"] for r in client.requests] == [11, 12, 13]


# --- the cost, before spending -----------------------------------------------


def test_the_cost_is_announced_before_the_first_request():
    events: list[str] = []
    tts = _TakesTTS(events=events)
    tts.billed_characters = lambda text, **_: len(text) + 10
    mall = _mall({"takes": _takes(3)})
    _run(_scene(), mall, tts, announce=lambda m: events.append(m))
    assert events[0].startswith("best-of-N takes: 3 tones request(s)")
    assert f"{3 * (len(TEXT) + 10):,} billed characters" in events[0]
    assert events[1:] == ["synthesize"] * 3


def test_cached_takes_are_free_and_a_plain_scene_says_nothing():
    said: list[str] = []
    tts = _TakesTTS()
    _run(_scene(), _mall(), tts, announce=said.append)
    assert said == []  # no takes declared: today's output, unchanged
    mall = _mall({"takes": _takes(3)})
    mall["audio"][audio_key(TEXT, "nar", "tones")] = _tone(1.0)  # take 0 already synthesized
    _run(_scene(), mall, tts, announce=said.append)
    assert "2 tones request(s)" in said[0] and "1 take(s) already cached" in said[0]
    _run(_scene(), mall, tts, announce=said.append)
    assert len(said) == 1  # the kept take is cached: nothing to bill, nothing said


def test_takes_cost_message_is_empty_without_takes():
    assert takes_cost_message([], _TakesTTS(), {}) == ""


# --- the prosody scorer ------------------------------------------------------


def test_scoring_decodes_a_wav_without_ffmpeg(monkeypatch):
    import an.audio.takes as takes

    monkeypatch.setattr(takes.shutil, "which", lambda _name: None)
    x = decode_for_scoring(_tone(0.5, rate=22050))
    assert x.size == pytest.approx(8000, abs=2)
    with pytest.raises(VoiceTakesError, match="ffmpeg"):
        decode_for_scoring(b"ID3 not a wav")


def test_the_prosody_scorer_prefers_the_take_on_target():
    scorer = ProsodyTakeScorer({"articulation_rate_sps": [5.0, 7.0]})
    scores = [scorer.score(_tone(s), TEXT) for s in (2.0, 1.0, 0.6)]  # 3, 6, 10 syll/s
    assert choose_take(scores) == 1
    assert scores[1].detail["misses"] == [] and scores[0].detail["misses"] == ["articulation_rate_sps"]
    assert scores[1].detail["measured"]["articulation_rate_sps"] == pytest.approx(6.0, rel=0.05)


# --- tempo --------------------------------------------------------------------


def test_tempo_is_validated_and_omitted_at_one():
    assert normalize_effects({"tempo": 1.0}) == {}
    assert normalize_effects({"tempo": 0.8}) == {"tempo": 0.8}
    for bad in (0.3, 2.5, "fast", True):
        with pytest.raises(VoiceEffectError):
            normalize_effects({"tempo": bad})


def test_the_pitch_only_chain_is_unchanged_and_tempo_multiplies_into_it():
    ratio = 2 ** (4 / 12)
    assert filter_chain({"pitch_semitones": 4.0}) == (
        f"aresample=44100,asetrate={44100 * ratio:.6f},aresample=44100,atempo={1 / ratio:.9f}"
    )
    both = filter_chain({"pitch_semitones": 4.0, "tempo": 1.5})
    assert both.endswith(f"atempo={1.5 / ratio:.9f}")
    assert filter_chain({"pitch_semitones": 12.0, "tempo": 0.5}).count("atempo=") == 2
    assert all(0.5 <= f <= 2.0 for f in atempo_stages(0.25)) and math.prod(atempo_stages(0.25)) == pytest.approx(0.25)


@pytest.mark.ffmpeg
def test_tempo_retimes_the_line_and_lipsync_hears_the_retimed_audio():
    rec = _Recording()
    mall = _mall({"effects": {"tempo": 2.0}})
    line = _run(_scene(), mall, _TakesTTS((2.0,)), lipsync=rec).timeline[0].dialogue[0]
    assert line.duration == pytest.approx(1.0, abs=0.02)
    assert rec.heard == [mall["audio"][line.audio_ref]]
    assert _duration(rec.heard[0]) == pytest.approx(1.0, abs=0.02)
    assert line.audio_ref == audio_key(TEXT, "nar", "tones", {"tempo": 2.0})
    assert audio_key(TEXT, "nar", "tones") in mall["audio"]  # the raw take, cached apart


@pytest.mark.ffmpeg
def test_takes_are_scored_on_the_audio_heard():
    """At tempo 2 the raw 2.0 s take is heard at 1.0 s — the one on target."""
    mall = _mall({"effects": {"tempo": 2.0}, "takes": _takes(2, target_s=1.0)})
    line = _run(_scene(), mall, _TakesTTS((2.0, 1.0))).timeline[0].dialogue[0]
    assert json.loads(mall["takes"][line.audio_ref])["chosen"] == 0
    assert line.duration == pytest.approx(1.0, abs=0.02)
