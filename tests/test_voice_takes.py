"""Best-of-N takes and the tempo effect (an#265).

The rules under test:

- one take (the default) and no ``tempo`` keep every audio key a project had;
- every take has its own content key, and the line keeps the CHOSEN take's own
  key — so a different take is a different ``audio_ref``, and its visemes and
  word timings are aligned on it;
- the takes record is the resolution (ADR 0003): a render restores the
  recorded take and never re-bills it, a hand edit of ``chosen`` wins, a lost
  take is an error before any request, a newer scorer keeps the recorded take
  and says so, and ``rescore`` / ``reroll`` are the only ways to replace one;
- the cost is announced before the first request, and a cached take is free;
- a ``tempo`` changes the line's duration, and lip-sync (hence word timings and
  captions) reads the re-timed audio — checked with ffmpeg AND with a fake
  effect chain, so the default CI leg (no ffmpeg) guards it too.

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

import an.audio.pipeline as pipeline
from an.audio.effects import VoiceEffectError, atempo_stages, filter_chain, normalize_effects
from an.audio.elevenlabs_tts import ElevenLabsTTS
from an.audio.lipsync import Viseme, VisemeTrack
from an.audio.offline_tts import OfflineTTS
from an.audio.pipeline import (
    TakeDigestWarning,
    audio_key,
    produce_audio_for_scene,
    retake_lines,
    takes_cost_message,
    viseme_key,
)
from an.audio.takes import (
    ProsodyTakeScorer,
    TakeLostError,
    TakeScore,
    TakesRecordError,
    TakesSpec,
    VoiceTakesError,
    choose_take,
    decode_for_scoring,
    style_voice_role,
    takes_choice_part,
    takes_spec,
    voice_takes,
)
from an.audio.tts import AudioClip
from an.ir.schema import Dialogue, Meta, SceneIR, Shot
from an.util import _stable_hash
from an.verify.prosody import ProsodyStats, target_distance

RATE = 16000
TEXT = "one two three four five six"  # six syllables


def _tone(seconds: float, *, hz: float = 150.0, rate: int = RATE) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    pcm = (0.3 * 32767 * np.sin(2 * math.pi * hz * t)).astype("<i2").tobytes()
    return _wav(pcm, rate)


def _wav(pcm: bytes, rate: int) -> bytes:
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


def _fake_effects(audio: bytes, effects) -> bytes:
    """A deterministic stand-in for the ffmpeg chain: ``tempo`` resamples the
    WAV to ``1/tempo`` of its length (enough to test what follows the effect)."""
    tempo = effects.get("tempo", 1.0)
    with wave.open(io.BytesIO(audio)) as w:
        rate = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)
    n = int(round(x.size / tempo))
    y = np.interp(np.arange(n) * tempo, np.arange(x.size), x).astype("<i2")
    return _wav(y.tobytes(), rate)


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


SCORED: list[float] = []  # every duration the fake scorer scored


class _DurationScorer:
    """Prefers the take whose length is closest to ``target_s`` (no ffmpeg, no estimator)."""

    name = "duration"
    version = "test"

    def __init__(self, target_s: float):
        self.config = {"target_s": target_s}
        self.target_s = target_s

    def score(self, audio, text):
        d = _duration(audio)
        SCORED.append(round(d, 3))
        return TakeScore((round(abs(d - self.target_s), 6),), {"duration_s": round(d, 3)})


def _duration_scorer(spec: TakesSpec):
    return _DurationScorer(spec.targets["articulation_rate_sps"][0])


class _Words:
    """Spreads the transcript's words evenly over the audio it is handed."""

    name = "words"
    convention = "rhubarb"
    emits_word_timings = True

    def __init__(self):
        self.heard: list[bytes] = []

    def align(self, audio, transcript):
        self.heard.append(audio.bytes_)
        words = transcript.split()
        step = audio.duration / len(words)
        timed = [(w, i * step, (i + 1) * step) for i, w in enumerate(words)]
        return VisemeTrack(visemes=[Viseme(0.0, "X")], duration=audio.duration, words=timed)


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
    kw.setdefault("lipsync", _Words())
    kw.setdefault("take_scorer", _duration_scorer)
    kw.setdefault("announce", None)
    return produce_audio_for_scene(scene, mall, tts=tts, **kw)


def _line(scene):
    return scene.timeline[0].dialogue[0]


def _record(mall) -> tuple[str, dict]:
    (key,) = mall["takes"]
    return key, json.loads(mall["takes"][key])


def _edit_record(mall, **changes):
    key, record = _record(mall)
    record.update(changes)
    mall["takes"][key] = json.dumps(record).encode()


@pytest.fixture(autouse=True)
def _reset_scored():
    SCORED.clear()


# --- the declaration ---------------------------------------------------------


def test_one_take_and_no_declaration_keep_every_key():
    legacy = _stable_hash({"text": "hi", "voice": "nar", "tts": "tones"})
    assert audio_key("hi", "nar", "tones", takes=None, take=0, roll=0) == legacy
    for decl in (None, 1, {"n": 1}, {"n": 1, "targets": {"f0_sd_st": [2, 4]}}):
        assert takes_spec(decl) is None
    mall = _mall({"takes": 1})
    assert _line(_run(_scene(text="hi"), mall, _TakesTTS())).audio_ref == legacy
    assert mall["takes"] == {}


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


def test_a_bad_declaration_fails_before_any_request_and_in_validate():
    tts = _TakesTTS()
    with pytest.raises(VoiceTakesError):
        _run(_scene(), _mall({"takes": {"n": 3}}), tts)
    assert tts.calls == []

    from an.ir.validate import validate_semantic

    report = validate_semantic(_scene(), available_voices={"nar": {"takes": {"n": 3}}})
    assert any("needs `targets`" in f.description for f in report.findings if f.severity == "error")


def test_cues_opt_lines_in_and_override_the_voice():
    decl = {"n": 1, "targets": {"f0_sd_st": [3, 5]},
            "cues": {"deadpan": {"n": 4, "targets": {"f0_sd_st": [2, 3]}}, "excited": 2}}
    assert takes_spec(decl, direction=None) is None
    dead = takes_spec(decl, direction=["sighs", "deadpan"])
    assert (dead.n, dict(dead.targets)) == (4, {"f0_sd_st": [2.0, 3.0]})
    excited = takes_spec(decl, direction=["excited"])
    assert (excited.n, dict(excited.targets)) == (2, {"f0_sd_st": [3.0, 5.0]})


def test_takes_are_scoped_to_the_provider_and_skip_repeatable_ones():
    mall = _mall({"provider": "elevenlabs", "takes": _takes()})
    assert voice_takes(mall, "nar", tts_name="offline") is None
    assert voice_takes(mall, "nar", tts_name="elevenlabs").n == 3
    assert voice_takes(mall, "absent", tts_name="elevenlabs") is None
    # no `provider` declared, spoken by a provider that repeats itself: one take
    said: list[str] = []
    mall = _mall({"takes": _takes()})
    _run(_scene(), mall, OfflineTTS(), announce=said.append)
    assert said == [] and mall["takes"] == {}


def test_the_choice_key_covers_n_the_scorer_and_its_configuration_not_its_version():
    def key(n, scorer):
        return audio_key("hi", "nar", "tones", takes=takes_choice_part(scorer, n))

    targets = {"f0_sd_st": [2.0, 4.0]}
    scorer = ProsodyTakeScorer(targets)
    bumped = ProsodyTakeScorer(targets)
    bumped.version = "99"
    keys = {
        key(3, scorer),
        key(4, scorer),
        key(3, ProsodyTakeScorer({"f0_sd_st": [2.0, 5.0]})),
        key(3, ProsodyTakeScorer(targets, reference_hz=120)),
        audio_key("hi", "nar", "tones"),
    }
    assert len(keys) == 5
    assert key(3, bumped) == key(3, scorer)


def test_the_scorer_version_follows_the_estimator(monkeypatch):
    import an.verify.prosody as prosody

    before = ProsodyTakeScorer({"f0_sd_st": [2, 4]}).version
    monkeypatch.setattr(prosody, "ESTIMATOR_VERSION", "2")
    assert ProsodyTakeScorer({"f0_sd_st": [2, 4]}).version != before


def test_choose_take_is_the_lowest_score_ties_to_the_first():
    s = [TakeScore((1.0, 0.0)), TakeScore((0.0, 0.5)), TakeScore((0.0, 0.5))]
    assert choose_take(s) == 1
    with pytest.raises(VoiceTakesError):
        choose_take([])


def test_an_unmeasurable_metric_never_wins():
    nan = float("nan")
    on = ProsodyStats(1.0, 1.0, 1.0, 3, 0, *[3.0] * 13)
    broken = ProsodyStats(1.0, 1.0, 1.0, 3, 0, *[nan] * 13)
    targets = {"f0_sd_st": [2, 4]}
    assert target_distance(broken, targets)[0] > target_distance(on, targets)[0]
    assert target_distance(broken, targets) == (1.0, 1.0)


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


# --- choosing and recording --------------------------------------------------


def test_the_best_take_is_kept_under_its_own_key_and_recorded():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3, target_s=1.0)})
    line = _line(_run(_scene(), mall, tts))
    assert len(tts.calls) == 3
    assert line.duration == pytest.approx(1.0)
    # the line keeps take 1's OWN key: a different take is a different audio_ref
    assert line.audio_ref == audio_key(TEXT, "nar", "tones", take=1)
    assert line.viseme_ref == viseme_key(line.audio_ref, "words", TEXT)
    kept = mall["audio"][line.audio_ref]
    assert _duration(kept) == pytest.approx(1.0)

    key, record = _record(mall)
    assert key != line.audio_ref  # the record is keyed by the choice, not the audio
    assert record["chosen"] == 1 and record["audio_key"] == line.audio_ref
    assert record["scorer"] == {"name": "duration", "version": "test", "config": {"target_s": 1.0}}
    assert [t["duration_s"] for t in record["takes"]] == [2.0, 1.0, 0.6]
    import hashlib

    assert record["digest"] == hashlib.sha256(kept).hexdigest()
    assert record["takes"][0]["audio_key"] == audio_key(TEXT, "nar", "tones")  # take 0 = the plain key
    assert all(t["audio_key"] in mall["audio"] for t in record["takes"])


def test_a_rerender_reads_the_record_and_neither_bills_nor_rescores():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    ref = _line(_run(_scene(), mall, tts)).audio_ref
    SCORED.clear()
    again = _line(_run(_scene(), mall, tts))  # a fresh, unstamped scene, as after editing scene.md
    assert (again.audio_ref, len(tts.calls), SCORED) == (ref, 3, [])


def test_a_lost_take_is_an_error_before_any_request():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    ref = _line(_run(_scene(), mall, tts)).audio_ref
    del mall["audio"][ref]  # no effects: the kept audio IS the raw take
    with pytest.raises(TakeLostError, match="an voices reroll"):
        _run(_scene(), mall, tts)
    assert len(tts.calls) == 3


def test_a_lost_kept_audio_is_restored_from_its_raw_take(monkeypatch):
    monkeypatch.setattr(pipeline, "apply_voice_effects", _fake_effects)
    tts = _TakesTTS((2.0, 1.0, 0.6))
    mall = _mall({"effects": {"tempo": 2.0}, "takes": _takes(3, target_s=1.0)})
    line = _line(_run(_scene(), mall, tts))
    assert json.loads(next(iter(mall["takes"].values())))["chosen"] == 0  # 2.0 s heard at 1.0 s
    kept = mall["audio"].pop(line.audio_ref)
    del mall["audio"][audio_key(TEXT, "nar", "tones", take=2)]  # a LOSING take gone too
    SCORED.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        again = _line(_run(_scene(), mall, tts))
    assert again.audio_ref == line.audio_ref and mall["audio"][line.audio_ref] == kept
    assert (len(tts.calls), SCORED) == (3, [])  # restored, not re-rolled nor re-scored


def test_a_hand_edit_of_the_record_wins_and_is_logged():
    class Log(dict):
        def append(self, **entry):
            self[str(len(self))] = entry

    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    mall["decisions"] = Log()
    scene = _run(_scene(), mall, tts)
    _edit_record(mall, chosen=2)
    line = _line(_run(scene, mall, tts))
    assert line.audio_ref == audio_key(TEXT, "nar", "tones", take=2)
    assert line.duration == pytest.approx(0.6)
    assert line.word_timings[-1].end == pytest.approx(0.6)  # re-aligned on the hand-picked take
    _, record = _record(mall)
    assert record["chosen"] == 2 and record["superseded_by"] == "hand"
    assert record["history"][-1]["chosen"] == 1
    assert mall["decisions"]["0"]["kind"] == "takes_hand_edit"
    _run(_scene(), mall, tts)  # and it stays
    assert _record(mall)[1]["chosen"] == 2 and len(tts.calls) == 3


def test_a_newer_scorer_keeps_the_recorded_take_and_says_so():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    ref = _line(_run(_scene(), mall, tts)).audio_ref

    def newer(spec):
        scorer = _DurationScorer(0.6)  # would choose take 2
        scorer.config = {"target_s": spec.targets["articulation_rate_sps"][0]}
        scorer.version = "test2"
        return scorer

    said: list[str] = []
    SCORED.clear()
    line = _line(_run(_scene(), mall, tts, take_scorer=newer, announce=said.append))
    assert line.audio_ref == ref and SCORED == [] and len(tts.calls) == 3
    assert len(said) == 1 and "older scorer" in said[0] and "an voices rescore" in said[0]


def test_rescore_rechooses_from_cached_takes_and_the_mouth_follows():
    """H1: a different take is a different key, so its visemes and words follow it."""
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    scene = _run(_scene(), mall, tts)
    first = _line(scene).model_copy(deep=True)
    assert first.word_timings[-1].end == pytest.approx(1.0)

    def newer(spec):
        scorer = _DurationScorer(0.6)
        scorer.config = {"target_s": spec.targets["articulation_rate_sps"][0]}
        scorer.version = "test2"
        return scorer

    msgs = retake_lines(scene, mall, "three four", tts=tts, rescore=True, take_scorer=newer)
    assert "released" in msgs[0]
    line = _line(_run(scene, mall, tts, take_scorer=newer))
    assert len(tts.calls) == 3  # chosen from the cached takes
    assert line.audio_ref != first.audio_ref and line.viseme_ref != first.viseme_ref
    assert line.duration == pytest.approx(0.6)
    assert line.word_timings[-1].end == pytest.approx(0.6)
    _, record = _record(mall)
    assert record["chosen"] == 2 and record["history"][-1]["reason"] == "rescore"


def test_reroll_synthesizes_a_new_roll_under_new_keys():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    scene = _run(_scene(), mall, tts)
    first = _line(scene).audio_ref
    tts.durations = [1.9, 3.0, 2.5]
    assert "roll 1" in retake_lines(scene, mall, TEXT, tts=tts, take_scorer=_duration_scorer)[0]
    said: list[str] = []
    line = _line(_run(scene, mall, tts, announce=said.append))
    assert len(tts.calls) == 6 and "3 tones request(s)" in said[0]
    assert line.audio_ref == audio_key(TEXT, "nar", "tones", take=0, roll=1) != first
    assert line.word_timings[-1].end == pytest.approx(1.9)
    _, record = _record(mall)
    assert record["roll"] == 1 and record["history"][-1]["reason"] == "reroll"
    assert first in mall["audio"]  # the replaced take is kept, never overwritten


def test_retake_says_what_it_did_not_do():
    tts, mall = _TakesTTS(), _mall()
    scene = _scene()
    def retake(match):
        return retake_lines(scene, mall, match, tts=tts, take_scorer=_duration_scorer)[0]

    assert "declares no takes" in retake("one")
    assert "no dialogue line contains" in retake("zebra")
    mall["voices"]["nar"]["takes"] = _takes(3)
    assert "no take recorded yet" in retake("one")


def test_a_corrupt_record_is_a_typed_error_before_any_request():
    tts, mall = _TakesTTS(), _mall({"takes": _takes(3)})
    _run(_scene(), mall, tts)
    key, _ = _record(mall)
    for bad in (b"{not json", b"[1, 2]", json.dumps({"chosen": 7, "takes": []}).encode()):
        mall["takes"][key] = bad
        with pytest.raises(TakesRecordError, match="delete it to choose again"):
            _run(_scene(), mall, tts)
    assert len(tts.calls) == 3


def test_replaced_kept_audio_is_reported():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    scene = _run(_scene(), mall, tts)
    mall["audio"][_line(scene).audio_ref] = _tone(1.0, hz=300)
    with pytest.warns(TakeDigestWarning, match="not the audio its takes record names"):
        _run(_scene(), mall, tts)


def test_turning_takes_on_reuses_the_single_take_as_take_zero():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall()
    _run(_scene(), mall, tts)
    assert len(tts.calls) == 1
    mall["voices"]["nar"]["takes"] = _takes(3, target_s=2.0)
    line = _line(_run(_scene(), mall, tts))
    assert len(tts.calls) == 3  # two new takes, not three
    assert line.audio_ref == audio_key(TEXT, "nar", "tones")  # take 0 kept: the plain key


def test_changing_the_targets_chooses_again_from_the_cached_takes():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3, target_s=1.0)})
    a = _line(_run(_scene(), mall, tts)).audio_ref
    mall["voices"]["nar"]["takes"] = _takes(3, target_s=0.5)
    b = _line(_run(_scene(), mall, tts))
    assert b.audio_ref != a and len(tts.calls) == 3
    assert b.audio_ref == audio_key(TEXT, "nar", "tones", take=2)


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
    assert "not billed per character" in said[0]  # this provider has no billing hook
    _run(_scene(), mall, tts, announce=said.append)
    assert len(said) == 1  # recorded: nothing to bill, nothing said


def test_takes_cost_message_is_empty_without_takes():
    assert takes_cost_message([], _TakesTTS(), {}) == ""


# --- the prosody scorer ------------------------------------------------------


def test_scoring_without_ffmpeg_fails_before_any_request(monkeypatch):
    import an.audio.takes as takes

    monkeypatch.setattr(takes.shutil, "which", lambda _name: None)
    with pytest.raises(VoiceTakesError, match="ffmpeg"):
        decode_for_scoring(_tone(0.5))
    tts = _TakesTTS()
    voice = {"takes": {"n": 2, "targets": {"f0_sd_st": [2, 4]}}}
    with pytest.raises(VoiceTakesError, match="nothing was billed"):
        _run(_scene(), _mall(voice), tts, take_scorer=pipeline.make_take_scorer)
    assert tts.calls == []


@pytest.mark.ffmpeg
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
    assert filter_chain({"tempo": 1.25}) == "aresample=44100,atempo=1.250000000"
    assert all(0.5 <= f <= 2.0 for f in atempo_stages(0.25)) and math.prod(atempo_stages(0.25)) == pytest.approx(0.25)


def test_tempo_retimes_the_line_without_ffmpeg(monkeypatch):
    """The default CI leg has no ffmpeg: a fake chain checks what FOLLOWS the
    effect — the key, the duration, what lip-sync hears, the viseme key."""
    monkeypatch.setattr(pipeline, "apply_voice_effects", _fake_effects)
    words = _Words()
    mall = _mall({"effects": {"tempo": 2.0}})
    line = _line(_run(_scene(), mall, _TakesTTS((2.0,)), lipsync=words))
    assert line.audio_ref == audio_key(TEXT, "nar", "tones", {"tempo": 2.0})
    assert line.audio_ref != audio_key(TEXT, "nar", "tones")
    assert line.duration == pytest.approx(1.0, abs=0.01)
    assert words.heard == [mall["audio"][line.audio_ref]]
    assert line.viseme_ref == viseme_key(line.audio_ref, "words", TEXT)
    assert line.word_timings[-1].end == pytest.approx(1.0, abs=0.01)
    assert _duration(mall["audio"][audio_key(TEXT, "nar", "tones")]) == pytest.approx(2.0)


def test_takes_are_scored_on_the_audio_heard_without_ffmpeg(monkeypatch):
    monkeypatch.setattr(pipeline, "apply_voice_effects", _fake_effects)
    mall = _mall({"effects": {"tempo": 2.0}, "takes": _takes(2, target_s=1.0)})
    line = _line(_run(_scene(), mall, _TakesTTS((2.0, 1.0))))
    assert SCORED == [1.0, 0.5]  # the heard lengths, not the raw 2.0 and 1.0
    assert _record(mall)[1]["chosen"] == 0
    assert line.audio_ref == audio_key(TEXT, "nar", "tones", {"tempo": 2.0})
    assert line.duration == pytest.approx(1.0, abs=0.01)


@pytest.mark.ffmpeg
def test_tempo_retimes_the_line_and_lipsync_hears_the_retimed_audio():
    words = _Words()
    mall = _mall({"effects": {"tempo": 2.0}})
    line = _line(_run(_scene(), mall, _TakesTTS((2.0,)), lipsync=words))
    assert line.duration == pytest.approx(1.0, abs=0.02)
    assert words.heard == [mall["audio"][line.audio_ref]]
    assert _duration(words.heard[0]) == pytest.approx(1.0, abs=0.02)
    assert line.word_timings[-1].end == pytest.approx(1.0, abs=0.02)
    assert line.audio_ref == audio_key(TEXT, "nar", "tones", {"tempo": 2.0})
    assert audio_key(TEXT, "nar", "tones") in mall["audio"]  # the raw take, cached apart


@pytest.mark.ffmpeg
def test_takes_are_scored_on_the_audio_heard():
    """At tempo 2 the raw 2.0 s take is heard at 1.0 s — the one on target."""
    mall = _mall({"effects": {"tempo": 2.0}, "takes": _takes(2, target_s=1.0)})
    line = _line(_run(_scene(), mall, _TakesTTS((2.0, 1.0))))
    assert _record(mall)[1]["chosen"] == 0
    assert line.duration == pytest.approx(1.0, abs=0.02)


# --- round 2: a rescore never re-synthesizes under old keys; tempo in the estimate


def test_rescore_after_a_lost_take_is_refused_and_reroll_keeps_the_mouth_in_step():
    tts, mall = _TakesTTS((2.0, 1.0, 0.6)), _mall({"takes": _takes(3)})
    scene = _run(_scene(), mall, tts)
    mall["audio"].clear()
    with pytest.raises(TakeLostError, match="an voices reroll"):
        _run(scene, mall, tts)
    msg = retake_lines(scene, mall, TEXT, tts=tts, rescore=True, take_scorer=_duration_scorer)[0]
    assert "not rescored" in msg and "an voices reroll" in msg
    key, original = _record(mall)
    assert original["chosen"] == 1  # untouched

    # a pending rescore written by hand cannot sneak a re-synthesis in either
    _edit_record(mall, chosen=None, pending="rescore", takes=[])
    with pytest.raises(TakeLostError, match="needs every take"):
        _run(scene, mall, tts)
    assert len(tts.calls) == 3

    # reroll: new keys, so the same index winning with a NEW length re-aligns
    mall["takes"][key] = json.dumps(original).encode()
    tts.durations = [2.0, 1.4, 0.6]
    retake_lines(scene, mall, TEXT, tts=tts, take_scorer=_duration_scorer)
    line = _line(_run(scene, mall, tts))
    assert _record(mall)[1]["chosen"] == 1
    assert line.duration == pytest.approx(1.4)
    assert line.word_timings[-1].end == pytest.approx(line.duration)


def test_validate_divides_the_estimate_by_the_voice_tempo():
    from an.audio.offline_tts import estimate_speech_duration
    from an.ir.validate import validate_semantic

    raw = estimate_speech_duration(TEXT)
    scene = _scene()
    scene.timeline[0].duration = round(raw + 0.2, 2)  # fits at the offline rate

    def overruns(voices):
        report = validate_semantic(scene, available_voices=voices)
        return [f.description for f in report.findings if "cut off" in f.description]

    assert overruns({"nar": {}}) == []
    found = overruns({"nar": {"effects": {"tempo": 0.7}}})
    assert len(found) == 1 and "tempo 0.7" in found[0]
    assert f"{raw / 0.7:.2f}s" in found[0]


def test_the_render_surfaces_an_overrun_after_synthesis(monkeypatch):
    monkeypatch.setattr(pipeline, "apply_voice_effects", _fake_effects)
    scene = _scene()
    scene.timeline[0].duration = 2.5
    said: list[str] = []
    _run(scene, _mall({"effects": {"tempo": 0.5}}), _TakesTTS((2.0,)), announce=said.append)
    assert len(said) == 1 and "ends at 4.00s" in said[0] and "cut off" in said[0]
    with pytest.warns(pipeline.DialogueOverrunWarning):
        _run(_scene(), _mall({"effects": {"tempo": 0.5}}), _TakesTTS((9.0,)))
