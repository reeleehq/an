"""The delivered film's video stream plays at ``meta.fps`` (an#195).

An end-user run delivered ``output/main.mp4`` reporting ``r_frame_rate=120/1``
for a 24 fps scene. The shots were not whole frames long (2.6 s at 24 fps is
62.4 frames): each shot's picture had 62 frames but its audio ran the full
2.6 s, so the concat — which advances by CONTAINER length — left sub-frame
holes between shots. The per-shot audio is now cut to the picture, and these
tests ffprobe the delivered file on both paths: the concat, and the assembler
(a sound cue plus a dissolve). The style lint, which read that 120 and measured
"2.042 s at 120 fps, 0 cuts", now reads the rate the frames arrive at.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import an.render as render_mod
from an.assemble import film_timeline
from an.frame_clock import frame_count
from an.ir.schema import Dialogue, Meta, Resolution, SceneIR, Shot, SoundCue, Transition

from tests.test_assemble import _project, _render

FPS = 24
#: 62.4, 48 and 76.8 frames: two of three are off the frame grid.
DURATIONS = {"red": 2.6, "blue": 2.0, "green": 3.2}
#: One AAC frame at the film's sample rate: the encoder's priming delay.
AAC_PRIMING_S = 1024 / 44100


def _meta(duration, **kw):
    return Meta(fps=FPS, duration=duration, resolution=Resolution(width=64, height=48), **kw)


def _probe(mp4: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=r_frame_rate,avg_frame_rate,nb_read_frames,duration",
         "-of", "default=noprint_wrappers=1", str(mp4)],
        capture_output=True, text=True, check=True,
    ).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def _assert_plays_at(mp4: Path, n_frames: int, *, fps: int = FPS) -> None:
    p = _probe(mp4)
    container = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(mp4)],
        capture_output=True, text=True, check=True,
    ).stdout
    # The container is the picture's length, up to the AAC encoder's priming
    # (one 1024-sample frame the concat carries, measured in an#163's review) —
    # never the ~a-frame-per-shot excess the holes added.
    assert 0 <= float(container) - n_frames / fps <= AAC_PRIMING_S + 1e-3, container
    assert p["r_frame_rate"] == f"{fps}/1", p
    assert p["avg_frame_rate"] == f"{fps}/1", p
    assert int(p["nb_read_frames"]) == n_frames, p
    assert float(p["duration"]) == pytest.approx(n_frames / fps, abs=1e-3), p


def _shots(**extra):
    return [Shot(id=sid, duration=d, **extra.get(sid, {})) for sid, d in DURATIONS.items()]


@pytest.mark.ffmpeg
def test_the_concat_of_off_grid_shots_plays_at_the_scene_rate(tmp_path, monkeypatch):
    scene = SceneIR(meta=_meta(sum(DURATIONS.values())), timeline=_shots())
    project = _project(tmp_path, scene)
    monkeypatch.setattr(render_mod, "assemble_film", lambda *a, **k: pytest.fail("assembled"))
    out = _render(project, monkeypatch, auto_audio=False)
    _assert_plays_at(out, sum(frame_count(d, FPS) for d in DURATIONS.values()))


@pytest.mark.ffmpeg
def test_a_sound_and_a_dissolve_play_at_the_scene_rate(tmp_path, monkeypatch):
    from an.sounds import SYNTH_SOURCE, add_sound, synth_hit, synth_tone

    shots = _shots(
        blue={"transition": Transition(kind="dissolve", duration=0.5),
              "sounds": [SoundCue(sound="hit", at=0.3)]},
    )
    scene = SceneIR(
        meta=_meta(7.3, sounds=[SoundCue(sound="bed", loop=True)]), timeline=shots
    )
    project = _project(tmp_path, scene)
    add_sound(project.mall["sounds"], "bed", synth_tone(220.0, 1.0, amplitude=0.2), source=SYNTH_SOURCE)
    add_sound(project.mall["sounds"], "hit", synth_hit(0.1, seed=1), source=SYNTH_SOURCE)
    out = _render(project, monkeypatch, auto_audio=False)
    _assert_plays_at(out, film_timeline(shots, fps=FPS).total_frames)


@pytest.mark.ffmpeg
def test_the_style_lint_reads_the_rate_the_frames_arrive_at(tmp_path):
    """A file WITH the holes (the old per-shot audio length, rebuilt on
    purpose) must still read as ~24 fps, not the 120 its r_frame_rate says."""
    from PIL import Image

    from an.adapters.cutout.render import (
        DEFAULT_FRAME_PNG_PATTERN,
        _ffmpeg_add_audio,
        _ffmpeg_mux,
    )
    from an.verify.style import _probe_fps

    shots = []
    for sid, d in DURATIONS.items():
        frames = tmp_path / sid
        frames.mkdir()
        for i in range(frame_count(d, FPS)):
            Image.new("RGB", (32, 32), (0, 0, 0)).save(frames / (DEFAULT_FRAME_PNG_PATTERN % i))
        silent, shot = tmp_path / f"{sid}_silent.mp4", tmp_path / f"{sid}.mp4"
        _ffmpeg_mux(frames, FPS, silent)
        _ffmpeg_add_audio(silent, [], shot, d)  # the bug: audio longer than picture
        shots.append(shot)
    holed = tmp_path / "holed.mp4"
    render_mod._ffmpeg_concat(shots, holed)
    # ffmpeg 8 reads this file as 120/1; whatever this build reads, the lint
    # must report the rate the frames arrive at.
    assert _probe_fps(holed) == pytest.approx(FPS, rel=0.01)


@pytest.mark.browser
@pytest.mark.ffmpeg
@pytest.mark.parametrize("assembled", [False, True], ids=["concat", "sound+dissolve"])
def test_a_real_render_delivers_the_scene_rate(tmp_path, assembled):
    """The real cutout renderer, end to end: off-grid shots with dialogue on the
    concat path; the same with a sound bed and a dissolve on the assembler."""
    from an.orchestrate import render_project
    from an.sounds import SYNTH_SOURCE, add_sound, synth_tone

    durations = {"a": 0.3, "b": 0.25, "c": 0.35}  # 7.2, 6 and 8.4 frames
    shots = [
        Shot(id=sid, duration=d, dialogue=[Dialogue(speaker="x", text="Hi.")] if sid == "a" else [])
        for sid, d in durations.items()
    ]
    meta = _meta(sum(durations.values()))
    if assembled:
        shots[1] = shots[1].model_copy(update={"transition": Transition(kind="dissolve", duration=0.1)})
        meta = meta.model_copy(update={"sounds": [SoundCue(sound="bed", loop=True)]})
    project = _project(tmp_path, SceneIR(meta=meta, timeline=shots))
    if assembled:
        add_sound(project.mall["sounds"], "bed", synth_tone(220.0, 0.5, amplitude=0.2), source=SYNTH_SOURCE)
    out = render_project(project.root)
    expected = (
        film_timeline(shots, fps=FPS).total_frames
        if assembled
        else sum(frame_count(d, FPS) for d in durations.values())
    )
    _assert_plays_at(out, expected)
