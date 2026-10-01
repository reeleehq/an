"""A re-synthesized line never keeps the mouth of other audio (an#289).

An audio key names a REQUEST, and an expressive provider (``eleven_v3``)
answers one request differently each time. So when a line's audio blob is
deleted and synthesized again, the viseme track, word timings and captions
cached under the same key were aligned on DIFFERENT audio. The rules under
test:

- the viseme sidecar records the sha256 of the audio it was aligned on;
- a cached track is re-aligned when that digest is not the audio's, and — for a
  sidecar written before the digest existed — when the audio was produced in
  this call;
- a cached sidecar is still reused when the audio was read back (every
  existing project keeps its tracks), and no key moves;
- a deleted raw take whose processed audio survives is never re-billed.

No test reaches a provider: the TTS is a fake that returns tones of a new
length on every call.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import wave

import numpy as np
import pytest

import an.audio.pipeline as pipeline
from an.audio.lipsync import Viseme, VisemeTrack
from an.audio.pipeline import audio_key, produce_audio_for_scene, viseme_key
from an.audio.tts import AudioClip
from an.ir.schema import Dialogue, Meta, SceneIR, Shot

RATE = 16000
TEXT = "one two three"


def _tone(seconds: float, rate: int = RATE) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    pcm = (0.3 * 32767 * np.sin(2 * math.pi * 150 * t)).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _fake_effects(audio: bytes, effects) -> bytes:
    """``tempo`` resamples the WAV (a deterministic stand-in for ffmpeg)."""
    tempo = effects.get("tempo", 1.0)
    with wave.open(io.BytesIO(audio)) as w:
        rate = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)
    n = int(round(x.size / tempo))
    y = np.interp(np.arange(n) * tempo, np.arange(x.size), x).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(y.tobytes())
    return buf.getvalue()


class _UnrepeatableTTS:
    """The same request answered with a new length every time (as eleven_v3 does)."""

    name = "unrepeatable"

    def __init__(self, durations=(1.0, 1.6, 0.7)):
        self.durations = list(durations)
        self.calls = 0

    def synthesize(self, text, voice_id="default", **kw):
        seconds = self.durations[self.calls % len(self.durations)]
        self.calls += 1
        return AudioClip(bytes_=_tone(seconds), duration=seconds, voice_id=voice_id, transcript=text)

    def list_voices(self):
        return []


class _Words:
    """Spreads the words evenly over the audio it is handed; counts its calls."""

    name = "words"
    convention = "rhubarb"
    emits_word_timings = True

    def __init__(self):
        self.calls = 0

    def align(self, audio, transcript):
        self.calls += 1
        words = transcript.split()
        step = audio.duration / len(words)
        timed = [(w, i * step, (i + 1) * step) for i, w in enumerate(words)]
        return VisemeTrack(visemes=[Viseme(0.0, "X")], duration=audio.duration, words=timed)


def _scene():
    return SceneIR(
        meta=Meta(title="t", duration=4.0),
        timeline=[Shot(id="s", renderer="cutout", duration=4.0,
                       dialogue=[Dialogue(speaker="a", text=TEXT, voice_ref="v")])],
    )


def _mall(voice=None):
    return {"audio": {}, "visemes": {}, "takes": {}, "voices": {"v": dict(voice or {})}}


def _line(scene):
    return scene.timeline[0].dialogue[0]


def _run(scene, mall, tts, words):
    return produce_audio_for_scene(scene, mall, tts=tts, lipsync=words, announce=None)


def _sidecar(mall, line):
    return json.loads(mall["visemes"][line.viseme_ref])


def test_a_resynthesized_line_is_realigned_on_its_new_audio():
    tts, words, mall = _UnrepeatableTTS(), _Words(), _mall()
    scene = _run(_scene(), mall, tts, words)
    first = _line(scene).model_copy(deep=True)
    assert first.word_timings[-1].end == pytest.approx(1.0)

    del mall["audio"][first.audio_ref]  # the blob is gone; the sidecar is not
    line = _line(_run(scene, mall, tts, words))
    assert (tts.calls, words.calls) == (2, 2)
    assert line.audio_ref == first.audio_ref and line.viseme_ref == first.viseme_ref  # no key moves
    assert line.duration == pytest.approx(1.6)
    assert line.word_timings[-1].end == pytest.approx(1.6)  # the mouth and captions follow
    assert _sidecar(mall, line)["duration"] == pytest.approx(1.6)
    assert _sidecar(mall, line)["audio_sha256"] == hashlib.sha256(
        mall["audio"][line.audio_ref]
    ).hexdigest()


def test_a_legacy_sidecar_is_realigned_only_when_the_audio_is_new():
    tts, words, mall = _UnrepeatableTTS(), _Words(), _mall()
    line = _line(_run(_scene(), mall, tts, words))
    legacy = _sidecar(mall, line)
    del legacy["audio_sha256"]  # written before an#289
    mall["visemes"][line.viseme_ref] = json.dumps(legacy).encode()

    _run(_scene(), mall, tts, words)  # the audio read back: the legacy track is kept
    assert (tts.calls, words.calls) == (1, 1)

    del mall["audio"][line.audio_ref]  # re-synthesized: the legacy track cannot vouch for it
    again = _line(_run(_scene(), mall, tts, words))
    assert (tts.calls, words.calls) == (2, 2)
    assert again.word_timings[-1].end == pytest.approx(1.6)


def test_audio_replaced_under_its_key_is_realigned():
    tts, words, mall = _UnrepeatableTTS(), _Words(), _mall()
    line = _line(_run(_scene(), mall, tts, words))
    mall["audio"][line.audio_ref] = _tone(2.2)  # swapped in place (a sync, a hand copy)
    clip, track = pipeline.produce_audio_for_dialogue(
        Dialogue(speaker="a", text=TEXT, voice_ref="v"), mall, tts=tts, lipsync=words
    )
    assert tts.calls == 1 and words.calls == 2
    assert track.words[-1][2] == pytest.approx(2.2)


def test_a_surviving_processed_audio_never_rebills_its_deleted_raw_take(monkeypatch):
    monkeypatch.setattr(pipeline, "apply_voice_effects", _fake_effects)
    tts, words, mall = _UnrepeatableTTS(), _Words(), _mall({"effects": {"tempo": 2.0}})
    line = _line(_run(_scene(), mall, tts, words))
    assert line.duration == pytest.approx(0.5, abs=0.01)
    del mall["audio"][audio_key(TEXT, "v", "unrepeatable")]  # the raw take only
    again = _line(_run(_scene(), mall, tts, words))
    assert (tts.calls, words.calls) == (1, 1)
    assert again.audio_ref == line.audio_ref


def test_a_resynthesized_line_with_effects_is_realigned(monkeypatch):
    monkeypatch.setattr(pipeline, "apply_voice_effects", _fake_effects)
    tts, words, mall = _UnrepeatableTTS(), _Words(), _mall({"effects": {"tempo": 2.0}})
    scene = _run(_scene(), mall, tts, words)
    ref = _line(scene).audio_ref
    mall["audio"].clear()
    line = _line(_run(scene, mall, tts, words))
    assert line.audio_ref == ref and tts.calls == 2
    assert line.duration == pytest.approx(0.8, abs=0.01)
    assert line.word_timings[-1].end == pytest.approx(line.duration)


def test_a_rechosen_take_after_a_deleted_record_is_realigned():
    """A best-of-N line whose record AND audio are gone chooses again; a take
    re-synthesized under its old key is re-aligned, not given the old mouth."""

    class Scorer:
        name, version, config = "shortest", "1", {}

        def score(self, audio, text):
            from an.audio.takes import TakeScore

            with wave.open(io.BytesIO(audio)) as w:
                return TakeScore((w.getnframes() / w.getframerate(),))

    voice = {"takes": {"n": 2, "targets": {"f0_sd_st": [2, 4]}}}
    tts, words, mall = _UnrepeatableTTS((1.0, 1.6, 0.7, 1.9)), _Words(), _mall(voice)

    def run():
        return produce_audio_for_scene(
            _scene(), mall, tts=tts, lipsync=words, announce=None,
            take_scorer=lambda spec: Scorer(),
        )

    first = _line(run())
    assert first.duration == pytest.approx(1.0)  # 1.0 beats 1.6
    mall["audio"].clear()
    mall["takes"].clear()
    line = _line(run())  # takes 0.7 and 1.9: take 0 again, with new bytes
    assert line.audio_ref == first.audio_ref
    assert line.duration == pytest.approx(0.7)
    assert line.word_timings[-1].end == pytest.approx(0.7)


def test_no_key_moves_and_the_sidecar_names_its_audio():
    tts, words, mall = _UnrepeatableTTS(), _Words(), _mall()
    line = _line(_run(_scene(), mall, tts, words))
    assert line.audio_ref == audio_key(TEXT, "v", "unrepeatable")
    assert line.viseme_ref == viseme_key(line.audio_ref, "words", TEXT)
    assert "audio_sha256" in _sidecar(mall, line)


# --- through `an render`'s entry point (an#289 review): the fast path verifies too


class _RecordingRenderer:
    """Records the shots it is handed (their dialogue stamps are what the
    compiler would draw the mouth from); writes a placeholder mp4."""

    name = "recording"
    supported_renderers = ("cutout",)

    def __init__(self):
        self.shots = []

    def can_render(self, shot):
        return True

    def render(self, shot, ctx):
        from pathlib import Path

        from an.adapters._base import RenderResult

        self.shots.append(shot.model_copy(deep=True))
        out = Path(ctx.work_dir) / f"{shot.id}.mp4"
        out.write_bytes(b"not really an mp4")
        return RenderResult(mp4_path=out, duration=shot.duration)


def _duration_of(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.getnframes() / w.getframerate()


def _srt_last_end(text):
    """The end of the last SubRip cue, in seconds."""
    stamp = [ln for ln in text.splitlines() if "-->" in ln][-1].split("-->")[1].strip()
    h, m, rest = stamp.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


@pytest.fixture
def render_project_with(tmp_path, monkeypatch):
    """``an render``'s entry point (:func:`an.render.render_project`) over a real
    project directory, with a recording renderer and no ffmpeg concat."""
    import shutil

    import an.render as render_mod
    from an import init
    from an.ir.schema import Captions

    root = init(tmp_path / "demo")
    renderer = _RecordingRenderer()
    monkeypatch.setattr(render_mod._DEFAULT_REGISTRY, "find_for", lambda shot: renderer)
    monkeypatch.setattr(
        render_mod, "_ffmpeg_concat", lambda inputs, out: shutil.copy(list(inputs)[0], out)
    )

    def setup(voice):
        from an.project import load

        project = load(root)
        project.mall["voices"]["v"] = voice
        scene = _scene()
        scene.meta.fps = 10
        scene.meta.captions = Captions(burn=False)
        project.mall["scenes"]["main"] = scene

    def render(tts, words):
        from an.project import load

        out = render_mod.render_project(root, tts=tts, lipsync=words, incremental=False)
        project = load(root)
        line = renderer.shots[-1].dialogue[0]
        heard = _duration_of(project.mall["audio"][line.audio_ref])
        return project, line, heard, _srt_last_end(out.with_suffix(".srt").read_text("utf-8"))

    return setup, render


def test_render_realigns_a_blob_replaced_under_its_key(render_project_with):
    """Review S2: the scene is stamped and every file is present, but the audio
    under the key is not the audio the mouth was aligned on."""
    setup, render = render_project_with
    setup({})
    tts, words = _UnrepeatableTTS(), _Words()
    project, line, heard, _ = render(tts, words)
    assert heard == pytest.approx(1.0)
    project.mall["audio"][line.audio_ref] = _tone(2.2)  # a sync clobber, a hand copy

    _, line, heard, srt_end = render(tts, words)
    assert heard == pytest.approx(2.2) and tts.calls == 1
    assert line.duration == pytest.approx(2.2)
    assert line.word_timings[-1].end == pytest.approx(2.2)  # the mouth the compiler draws
    assert srt_end == pytest.approx(2.2, abs=0.1)  # and the captions


def test_render_restamps_from_a_restored_backup(render_project_with):
    """Review S3a: audio and visemes restored from an older backup agree with
    each other, but scene.json was stamped from a newer take."""
    setup, render = render_project_with
    setup({})
    tts, words = _UnrepeatableTTS(), _Words()
    project, line, _, _ = render(tts, words)  # take A, 1.0 s
    backup = {k: dict(project.mall[k].items()) for k in ("audio", "visemes")}
    del project.mall["audio"][line.audio_ref]
    project, line, heard, _ = render(tts, words)  # take B, 1.6 s, stamped
    assert heard == pytest.approx(1.6)
    for store, items in backup.items():
        for key, value in items.items():
            project.mall[store][key] = value

    _, line, heard, srt_end = render(tts, words)
    assert heard == pytest.approx(1.0) and tts.calls == 2
    assert line.duration == pytest.approx(1.0)
    assert line.word_timings[-1].end == pytest.approx(1.0)
    assert srt_end == pytest.approx(1.0, abs=0.1)


def test_render_realigns_a_replaced_kept_take_with_tempo(render_project_with, monkeypatch):
    """Review T2: a best-of-N line with a tempo; its kept (heard) audio is
    replaced under its key. Warned about, and the mouth follows the bytes."""
    from an.audio import takes as takes_mod
    from an.audio.takes import TakeScore

    class Shortest:
        name, version, config = "shortest", "1", {}

        def score(self, audio, text):
            return TakeScore((_duration_of(audio),))

    monkeypatch.setitem(takes_mod.SCORERS, "shortest", lambda spec: Shortest())
    monkeypatch.setattr(pipeline, "apply_voice_effects", _fake_effects)
    setup, render = render_project_with
    setup({"effects": {"tempo": 2.0}, "takes": {"n": 2, "scorer": "shortest"}})
    tts, words = _UnrepeatableTTS((1.0, 1.6)), _Words()
    project, line, heard, _ = render(tts, words)
    assert heard == pytest.approx(0.5, abs=0.01)
    project.mall["audio"][line.audio_ref] = _tone(1.3)

    with pytest.warns(pipeline.TakeDigestWarning):
        _, line, heard, srt_end = render(tts, words)
    assert heard == pytest.approx(1.3) and tts.calls == 2
    assert line.duration == pytest.approx(1.3)
    assert line.word_timings[-1].end == pytest.approx(1.3)
    assert srt_end == pytest.approx(1.3, abs=0.1)


def test_an_untouched_project_rerenders_without_realigning(render_project_with):
    setup, render = render_project_with
    setup({})
    tts, words = _UnrepeatableTTS(), _Words()
    project, line, _, _ = render(tts, words)
    stamped = project.mall["scenes"]["main"].model_dump_json()
    render(tts, words)
    from an.project import load

    assert (tts.calls, words.calls) == (1, 1)
    assert load(project.root).mall["scenes"]["main"].model_dump_json() == stamped


# --- the fresh-audio flag on a takes line with a sidecar written before an#289


def _legacy(mall, ref):
    """Strip the digest from a sidecar, as one written before an#289."""
    payload = json.loads(mall["visemes"][ref])
    payload.pop("audio_sha256", None)
    mall["visemes"][ref] = json.dumps(payload).encode()


class _Shortest:
    name, version, config = "shortest", "1", {}

    def score(self, audio, text):
        from an.audio.takes import TakeScore

        return TakeScore((_duration_of(audio),))


def _takes_run(mall, tts, words):
    return produce_audio_for_scene(
        _scene(), mall, tts=tts, lipsync=words, announce=None,
        take_scorer=lambda spec: _Shortest(),
    )


def test_a_rechosen_take_realigns_a_legacy_sidecar():
    voice = {"takes": {"n": 2, "targets": {"f0_sd_st": [2, 4]}}}
    tts, words, mall = _UnrepeatableTTS((1.0, 1.6, 0.7, 1.9)), _Words(), _mall(voice)
    first = _line(_takes_run(mall, tts, words))
    _legacy(mall, first.viseme_ref)
    mall["audio"].clear()
    mall["takes"].clear()
    line = _line(_takes_run(mall, tts, words))  # take 0 again: new 0.7 s bytes
    assert line.viseme_ref == first.viseme_ref and words.calls == 2
    assert line.word_timings[-1].end == pytest.approx(0.7)


def test_a_restored_take_realigns_a_legacy_sidecar(monkeypatch):
    monkeypatch.setattr(pipeline, "apply_voice_effects", _fake_effects)
    voice = {"effects": {"tempo": 2.0}, "takes": {"n": 2, "targets": {"f0_sd_st": [2, 4]}}}
    tts, words, mall = _UnrepeatableTTS((1.0, 1.6)), _Words(), _mall(voice)
    first = _line(_takes_run(mall, tts, words))
    _legacy(mall, first.viseme_ref)
    del mall["audio"][first.audio_ref]  # the heard audio; its raw take survives
    line = _line(_takes_run(mall, tts, words))
    assert tts.calls == 2 and words.calls == 2  # restored, not re-billed; re-aligned
    assert line.word_timings[-1].end == pytest.approx(line.duration)


def test_a_replaced_kept_take_is_caught_by_its_record_even_with_a_legacy_sidecar():
    """The takes record names the kept audio's digest, so a take replaced under
    its key is caught even when its sidecar (written before an#289) cannot."""
    voice = {"takes": {"n": 2, "targets": {"f0_sd_st": [2, 4]}}}
    tts, words, mall = _UnrepeatableTTS((1.0, 1.6)), _Words(), _mall(voice)
    scene = _takes_run(mall, tts, words)
    first = _line(scene)
    _legacy(mall, first.viseme_ref)
    mall["audio"][first.audio_ref] = _tone(1.3)
    with pytest.warns(pipeline.TakeDigestWarning):
        line = _line(
            produce_audio_for_scene(
                scene, mall, tts=tts, lipsync=words, announce=None,
                take_scorer=lambda spec: _Shortest(),
            )
        )
    assert tts.calls == 2 and words.calls == 2
    assert line.duration == pytest.approx(1.3)
    assert line.word_timings[-1].end == pytest.approx(1.3)


# --- a project rendered before an#289: legacy sidecars, through `an render`


@pytest.fixture
def pre_289_project(render_project_with):
    """A project rendered before an#289: its viseme sidecars name no audio
    (exactly what the pipeline wrote then: the payload without
    ``audio_sha256``). Returns ``(render, tts, words, project, line)``."""
    from an.project import load

    setup, render = render_project_with
    setup({})
    tts, words = _UnrepeatableTTS(), _Words()
    project, line, _, _ = render(tts, words)
    visemes = project.mall["visemes"]
    for key in list(visemes):
        payload = json.loads(visemes[key])
        payload.pop("audio_sha256")
        visemes[key] = json.dumps(payload).encode()
    return render, tts, words, load(project.root), line


def _legacy_count(project):
    return sum("audio_sha256" not in json.loads(v) for v in project.mall["visemes"].values())


def test_an_untouched_pre_289_project_backfills_its_digests_and_realigns_nothing(pre_289_project):
    from an.project import load

    render, tts, words, project, _ = pre_289_project
    stamped = project.mall["scenes"]["main"].model_dump_json()
    assert _legacy_count(project) == 1
    render(tts, words)
    project = load(project.root)
    assert (tts.calls, words.calls) == (1, 1)
    assert project.mall["scenes"]["main"].model_dump_json() == stamped
    assert _legacy_count(project) == 0  # covered by the digest check from now on


def test_a_pre_289_project_with_a_replaced_blob_is_realigned(pre_289_project):
    """Review LEG-S2: a legacy sidecar, the blob replaced under its key."""
    render, tts, words, project, line = pre_289_project
    project.mall["audio"][line.audio_ref] = _tone(2.2)
    _, line, heard, srt_end = render(tts, words)
    assert heard == pytest.approx(2.2) and tts.calls == 1 and words.calls == 2
    assert line.duration == pytest.approx(2.2)
    assert line.word_timings[-1].end == pytest.approx(2.2)
    assert srt_end == pytest.approx(2.2, abs=0.1)


def test_a_pre_289_project_with_its_audio_restored_from_a_backup_is_realigned(pre_289_project):
    """Review LEG-S3c: the audio store restored from an older take (another length)."""
    render, tts, words, project, line = pre_289_project
    project.mall["audio"][line.audio_ref] = _tone(0.7)
    _, line, heard, _ = render(tts, words)
    assert heard == pytest.approx(0.7) and tts.calls == 1
    assert line.word_timings[-1].end == pytest.approx(0.7)


def test_a_pre_289_backup_of_audio_and_visemes_restamps_a_newer_scene(pre_289_project):
    """Review LEG-S3a: audio and its legacy sidecar agree (an older take), but
    scene.json was stamped from a newer one: the IR follows the store."""
    render, tts, words, project, line = pre_289_project
    old = {k: dict(project.mall[k].items()) for k in ("audio", "visemes")}
    del project.mall["audio"][line.audio_ref]
    project, line, heard, _ = render(tts, words)  # a newer take, 1.6 s
    assert heard == pytest.approx(1.6)
    for store, items in old.items():
        for key, value in items.items():
            project.mall[store][key] = value
    _, line, heard, _ = render(tts, words)
    assert heard == pytest.approx(1.0) and tts.calls == 2
    assert line.duration == pytest.approx(1.0)
    assert line.word_timings[-1].end == pytest.approx(1.0)


def test_an_unreadable_sidecar_is_never_trusted(render_project_with):
    """Review F7: a corrupt sidecar on the fast path is re-aligned, not trusted."""
    setup, render = render_project_with
    setup({})
    tts, words = _UnrepeatableTTS(), _Words()
    project, line, _, _ = render(tts, words)
    project.mall["visemes"][line.viseme_ref] = b"{not json"
    _, line, _, _ = render(tts, words)
    assert words.calls == 2 and tts.calls == 1
    assert json.loads(project.mall["visemes"][line.viseme_ref])["audio_sha256"]
