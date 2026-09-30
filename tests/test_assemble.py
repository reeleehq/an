"""Shot transitions and the sound layer (an#163, `an.assemble`).

Three layers of test:

- **pure** — the timeline arithmetic, the refusals, the mix argv, the ducking
  spec, the IR round trip and the validate verdicts. No ffmpeg, no browser.
- **default byte-identity** — a scene without transitions or sounds never
  reaches the assembler, and the concat argv it does reach is pinned.
- **ffmpeg** — real per-shot encodes from a stand-in renderer that paints solid
  colours (no browser), assembled for real and decoded: frame counts, blend
  values, film length, and dialogue landing on its own shot's frames.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

import an.render as render_mod
from an.adapters._base import RenderResult
from an.assemble import (
    AssemblyError,
    MixPlan,
    Placement,
    blend,
    duck_gain,
    film_timeline,
    merge_spans,
    mix_command,
    needs_assembly,
    transition_problems,
)
from an.ir.schema import Dialogue, Meta, Resolution, SceneIR, Shot, SoundCue, Transition
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.validate import validate_semantic

REPO = Path(__file__).resolve().parents[1]


def _shots(*specs):
    """``("a", 1.0)`` or ``("b", 1.0, Transition(...))`` → Shots."""
    out = []
    for spec in specs:
        sid, dur, *rest = spec
        out.append(Shot(id=sid, duration=dur, transition=rest[0] if rest else None))
    return out


# --- the timeline -------------------------------------------------------------


def test_cuts_lay_shots_end_to_end():
    tl = film_timeline(_shots(("a", 1.0), ("b", 0.5)), fps=10)
    assert tl.starts == (0, 10) and tl.total_frames == 15
    assert not tl.has_transitions


def test_a_dissolve_overlaps_and_shortens_the_film():
    t = Transition(kind="dissolve", duration=0.4)
    tl = film_timeline(_shots(("a", 1.0), ("b", 1.0, t), ("c", 1.0, t)), fps=10)
    assert tl.starts == (0, 6, 12)
    assert tl.total_frames == 30 - 8
    assert tl.duration == pytest.approx(2.2)


def test_a_fade_holds_the_film_length_and_splits_across_the_cut():
    t = Transition(kind="fade", duration=0.5, color="#ffffff")
    tl = film_timeline(_shots(("a", 1.0), ("b", 1.0, t)), fps=10)
    assert tl.total_frames == 20 and tl.starts == (0, 10)
    assert (tl.fade_out[0], tl.fade_in[1]) == (2, 3)  # 5 frames: 2 out, 3 in
    assert tl.fade_out_color[0] == tl.fade_in_color[1] == "#ffffff"


def test_a_fade_on_the_first_shot_is_a_fade_up_over_the_whole_duration():
    tl = film_timeline(_shots(("a", 1.0, Transition(kind="fade", duration=0.4))), fps=10)
    assert tl.fade_in == (4,) and tl.fade_out == (0,)


def test_an_explicit_cut_is_a_cut():
    tl = film_timeline(_shots(("a", 1.0), ("b", 1.0, Transition(kind="cut", duration=9))), fps=10)
    assert tl.total_frames == 20 and not tl.has_transitions


def test_refusals_are_one_list_for_validate_and_the_assembler():
    first = _shots(("a", 1.0, Transition(kind="dissolve")))
    assert "first shot" in transition_problems(first, 30)[0][1]
    with pytest.raises(AssemblyError, match="first shot"):
        film_timeline(first, fps=30)
    # b is 5 frames: a 0.4 s dissolve in AND a 0.4 s dissolve out need 8.
    d = Transition(kind="dissolve", duration=0.4)
    short = _shots(("a", 1.0), ("b", 0.5, d), ("c", 1.0, d))
    [(i, msg)] = transition_problems(short, 10)
    assert i == 1 and "4 at its head and 4 at its tail" in msg


# --- the picture: exact blends -------------------------------------------------


def test_blend_is_exact_and_rounds_half_to_even():
    a = np.array([[[0, 1, 2]]], np.uint8)
    b = np.array([[[255, 2, 3]]], np.uint8)
    # 0*1+255*1 = 255 / 2 = 127.5 -> 128 ; 1.5 -> 2 ; 2.5 -> 2
    assert blend(a, b, 1, 2)[0, 0].tolist() == [128, 2, 2]
    assert blend(a, b, 2, 5)[0, 0].tolist() == [102, 1, 2]  # 102.0, 1.4, 2.4


# --- the sound: plan, argv, ducking --------------------------------------------


def test_duck_gain_ramps_before_and_after_and_merges_close_lines():
    spans = [(1.0, 2.0), (2.2, 3.0)]  # 0.2 s apart: closer than attack+release
    g = lambda t: duck_gain(t, spans, duck_db=-20, attack=0.1, release=0.3)  # noqa: E731
    assert g(0.0) == 1.0 and g(0.95) == pytest.approx(0.55)
    assert g(2.1) == pytest.approx(0.1)  # held down between the two lines
    assert g(3.15) == pytest.approx(0.55) and g(3.5) == 1.0
    assert merge_spans(spans, attack=0.1, release=0.3) == [(1.0, 3.0)]


def test_mix_command_copies_the_picture_and_places_in_samples(tmp_path):
    plan = MixPlan(
        duration=2.0,
        placements=[
            Placement(path=tmp_path / "d.wav", at=0.5),
            Placement(path=tmp_path / "b.wav", at=0.0, play=2.0, loop=True,
                      gain_db=-6.0, fade_in=0.5, fade_out=0.5, duck=(-12.0, 0.1, 0.3)),
        ],
        dialogue_spans=[(0.5, 1.0)],
    )
    cmd = mix_command(plan, tmp_path / "v.mp4", tmp_path / "o.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "adelay=22050S:all=1" in graph  # 0.5 s at 44.1 kHz, in samples
    i = cmd.index(str(tmp_path / "b.wav"))
    assert cmd[i - 3 : i - 1] == ["-stream_loop", "-1"]
    assert "afade=t=out:st=1.500000:d=0.500000" in graph
    assert "volume=-6.0dB" in graph and "volume=eval=frame" in graph
    assert graph.endswith("amix=inputs=3:dropout_transition=0:normalize=0[aout]")
    assert cmd[-3:-1] == ["-movflags", "+faststart"]


# --- the IR: omit-when-unset, round trip, validate -----------------------------


def test_unset_fields_leave_no_trace_in_the_document():
    doc = SceneIR(timeline=[Shot(id="a")]).model_dump()
    assert "transition" not in doc["timeline"][0]
    assert "sounds" not in doc["timeline"][0]
    assert "sounds" not in doc["meta"]


def _full_scene() -> SceneIR:
    return SceneIR(
        meta=Meta(
            title="t", duration=3.0,
            sounds=[SoundCue(sound="bed", loop=True, duck_db=-12.0, fade_in=0.5)],
        ),
        timeline=[
            Shot(id="a", duration=1.5, sounds=[SoundCue(sound="hit", at=0.25)]),
            Shot(id="b", duration=1.5,
                 transition=Transition(kind="fade", duration=0.4, color="#102030")),
        ],
    )


def test_scene_md_round_trips_transitions_and_sounds():
    scene = _full_scene()
    back = markdown_to_ir(ir_to_markdown(scene))
    assert back.meta.sounds == scene.meta.sounds
    assert back.timeline[0].sounds == scene.timeline[0].sounds
    assert back.timeline[1].transition == scene.timeline[1].transition
    assert back.timeline[0].transition is None


def test_every_committed_scene_takes_the_old_concat_path():
    """The default is byte-identical because nothing committed opts in."""
    import json

    from an.ir.sync import scene_from_json_doc

    mds = sorted(REPO.glob("examples/*/scene.md")) + sorted(
        REPO.glob("misc/bench/corpus/*/scene.md")
    )
    jsons = sorted(REPO.glob("examples/*/ir/scene.json")) + sorted(
        REPO.glob("misc/bench/corpus/*/ir/scene.json")
    )
    assert mds and jsons
    for md in mds:
        assert not needs_assembly(markdown_to_ir(md.read_text(encoding="utf-8"))), md
    for js in jsons:
        doc = json.loads(js.read_text(encoding="utf-8"))
        assert not needs_assembly(scene_from_json_doc(doc)), js
        # ...and re-serializing it adds no trace of the new fields.
        text = scene_from_json_doc(doc).model_dump_json()
        assert '"transition"' not in text and '"sounds"' not in text, js


def test_validate_reports_what_the_assembler_would_refuse(tmp_path):
    from an.sounds import add_sound, synth_hit
    from an.stores.sounds import SoundsStore

    scene = SceneIR(
        meta=Meta(sounds=[SoundCue(sound="nope")]),
        timeline=[
            Shot(id="a", duration=1.0, transition=Transition(kind="dissolve"),
                 sounds=[SoundCue(sound="hit", at=2.0)]),
        ],
    )
    store = SoundsStore(tmp_path)
    add_sound(store, "hit", synth_hit(), source={"provider": "someone"})
    report = validate_semantic(scene, available_sounds=store)
    by_path = {f.ir_path: (f.severity, f.description) for f in report.findings}
    assert by_path["timeline/0/transition"][0] == "error"
    assert by_path["meta/sounds/0/sound"][0] == "error"
    assert by_path["timeline/0/sounds/0/at"][0] == "warning"
    assert "UNVERIFIED" in by_path["timeline/0/sounds/0/sound"][1]


def test_validate_warns_about_a_line_inside_a_dissolve():
    scene = SceneIR(
        timeline=[
            Shot(id="a", duration=2.0,
                 dialogue=[Dialogue(speaker="x", text="hi", start=1.8, duration=0.3)]),
            Shot(id="b", duration=2.0, transition=Transition(kind="dissolve", duration=0.5)),
        ],
    )
    report = validate_semantic(scene)
    assert any(
        f.ir_path == "timeline/0/dialogue/0" and f.severity == "warning"
        for f in report.findings
    )


# --- default byte-identity: the concat path is untouched ------------------------


def test_the_concat_argv_is_pinned(tmp_path, monkeypatch):
    """The cut-only path's ffmpeg call, verbatim. A scene without transitions
    or sounds reaches exactly this, as before an#163."""
    from tests._fake_subprocess import patch_subprocess_run, touch_output

    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        touch_output(cmd[-1], root=tmp_path, argv=cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    patch_subprocess_run(monkeypatch, render_mod, fake_run)
    monkeypatch.setattr(render_mod.shutil, "which", lambda _: "/bin/ffmpeg")
    a, b, out = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "out.mp4"
    render_mod._ffmpeg_concat([a, b], out)
    list_path = out.with_suffix(".concat.txt")
    assert seen == [[
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(list_path), "-c", "copy", "-movflags", "+faststart", str(out),
    ]]


# --- ffmpeg: a stand-in renderer, assembled for real ---------------------------

#: Solid colours per shot id: saturated, so a blend is easy to read back.
_COLOURS = {"red": (255, 0, 0), "blue": (0, 0, 255), "green": (0, 255, 0)}
_FPS = 10
_SIZE = (64, 48)


class _SolidRenderer:
    """Paints each shot one colour and runs the REAL per-shot mux and audio mux."""

    name = "solid"
    supported_renderers = ("cutout",)

    def can_render(self, shot):
        return True

    def render(self, shot, ctx):
        from PIL import Image

        from an.adapters.cutout.render import (
            DEFAULT_FRAME_PNG_PATTERN,
            _ffmpeg_add_audio,
            _ffmpeg_mux,
            _stage_audio_inputs,
        )
        from an.frame_clock import frame_count

        work = Path(ctx.work_dir) / f"solid_{shot.id}"
        frames = work / "frames"
        frames.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", ctx.resolution, _COLOURS[shot.id])
        for i in range(frame_count(shot.duration, ctx.fps)):
            image.save(frames / (DEFAULT_FRAME_PNG_PATTERN % i), format="PNG")
        silent, out = work / "silent.mp4", work / f"{shot.id}.mp4"
        _ffmpeg_mux(frames, ctx.fps, silent)
        _ffmpeg_add_audio(silent, _stage_audio_inputs(shot, ctx, work), out, shot.duration)
        return RenderResult(
            mp4_path=out, duration=shot.duration,
            frame_manifest=sorted(frames.glob("*.png")),
        )


def _project(tmp_path, scene):
    from an import init
    from an.project import load

    root = init(tmp_path / "demo")
    project = load(root)
    project.scene = scene
    project.mall["scenes"]["main"] = scene
    return load(root)


def _render(project, monkeypatch, **kw):
    renderer = _SolidRenderer()
    monkeypatch.setattr(render_mod._DEFAULT_REGISTRY, "find_for", lambda shot: renderer)
    return render_mod.render(project, **kw)


def _meta(duration):
    return Meta(fps=_FPS, duration=duration, resolution=Resolution(width=_SIZE[0], height=_SIZE[1]))


def _decode_rgb(mp4: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp4), "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, _SIZE[1], _SIZE[0], 3)


def _decode_audio(mp4: Path, sr: int = 44100) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp4), "-f", "f32le", "-ac", "1",
         "-ar", str(sr), "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.float32)


def _stream_duration(mp4: Path, kind: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", kind, "-show_entries",
         "stream=duration", "-of", "csv=p=0", str(mp4)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


def _video_bitstream(mp4: Path) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp4), "-map", "0:v", "-c", "copy",
         "-f", "h264", "-"],
        capture_output=True, check=True,
    ).stdout


@pytest.mark.ffmpeg
def test_unset_fields_route_through_the_unchanged_concat(tmp_path, monkeypatch):
    scene = SceneIR(meta=_meta(2.0), timeline=[Shot(id="red", duration=1.0), Shot(id="blue", duration=1.0)])
    project = _project(tmp_path, scene)
    calls = []
    real = render_mod._ffmpeg_concat
    monkeypatch.setattr(render_mod, "_ffmpeg_concat", lambda i, o: (calls.append((list(i), o)), real(i, o)))
    monkeypatch.setattr(render_mod, "assemble_film", lambda *a, **k: pytest.fail("assembled"))
    out = _render(project, monkeypatch)
    [(inputs, target)] = calls
    assert target == out and [p.name for p in inputs] == ["red.mp4", "blue.mp4"]
    # The delivered bytes ARE the concat's: re-running it reproduces them.
    again = tmp_path / "again.mp4"
    real(inputs, again)
    assert again.read_bytes() == out.read_bytes()


@pytest.mark.ffmpeg
def test_a_dissolve_blends_exactly_and_shortens_the_film(tmp_path, monkeypatch):
    t = Transition(kind="dissolve", duration=0.4)
    scene = SceneIR(meta=_meta(2.0), timeline=[
        Shot(id="red", duration=1.0), Shot(id="blue", duration=1.0, transition=t)])
    out = _render(_project(tmp_path, scene), monkeypatch)

    # The composed PNGs are exact: frame 7 is overlap frame j=1 of k=4, so
    # blue carries 2/5 — (255*3 + 0*2)/5 = 153, (0*3 + 255*2)/5 = 102.
    from PIL import Image

    film_frames = sorted((tmp_path / "demo/.an/render_work/film/frames").glob("*.png"))
    assert len(film_frames) == 16
    with Image.open(film_frames[7]) as im:
        assert im.convert("RGB").getpixel((5, 5)) == (153, 0, 102)
    with Image.open(film_frames[5]) as im:  # untouched: red's own bytes, copied
        assert im.convert("RGB").getpixel((5, 5)) == (255, 0, 0)

    video = _decode_rgb(out)
    assert len(video) == 16
    mid = video[7].reshape(-1, 3).mean(axis=0)
    assert np.allclose(mid, (153, 0, 102), atol=8), mid
    assert _stream_duration(out, "v") == pytest.approx(1.6, abs=0.01)
    assert _stream_duration(out, "a") == pytest.approx(1.6, abs=0.03)


@pytest.mark.ffmpeg
def test_a_fade_reaches_the_colour_on_exactly_one_frame(tmp_path, monkeypatch):
    t = Transition(kind="fade", duration=0.4, color="#000000")
    scene = SceneIR(meta=_meta(2.0), timeline=[
        Shot(id="red", duration=1.0), Shot(id="blue", duration=1.0, transition=t)])
    out = _render(_project(tmp_path, scene), monkeypatch)
    from PIL import Image

    frames = sorted((tmp_path / "demo/.an/render_work/film/frames").glob("*.png"))
    px = []
    for f in frames:
        with Image.open(f) as im:
            px.append(im.convert("RGB").getpixel((5, 5)))
    # red's tail: 1/3, 2/3 of the way to black; blue's head: black, then half.
    assert px[7:12] == [(255, 0, 0), (170, 0, 0), (85, 0, 0), (0, 0, 0), (0, 0, 128)]
    assert len(_decode_rgb(out)) == 20  # a fade holds the film's length


@pytest.mark.ffmpeg
def test_dialogue_stays_on_its_own_shots_frames_across_a_dissolve(tmp_path, monkeypatch):
    """The offline TTS stamps the line; its cached WAV is swapped for a tone of
    the same length (the cache is content-keyed, so the render reads it back),
    and the tone's onset is found in the assembled film's audio."""
    from an.audio.pipeline import produce_audio_for_scene
    from an.sounds import synth_tone, wav_info

    t = Transition(kind="dissolve", duration=0.4)
    line = Dialogue(speaker="x", text="hello there", start=0.3)
    scene = SceneIR(meta=_meta(2.5), timeline=[
        Shot(id="red", duration=1.0),
        Shot(id="blue", duration=1.5, transition=t, dialogue=[line])])
    project = _project(tmp_path, scene)
    produce_audio_for_scene(project.scene, project.mall)
    project.mall["scenes"]["main"] = project.scene
    stamped = project.scene.timeline[1].dialogue[0]
    sr, _, n = wav_info(project.mall["audio"][stamped.audio_ref])
    project.mall["audio"][stamped.audio_ref] = synth_tone(
        440.0, n / sr, sample_rate=sr, attack=0.0, release=0.0)

    out = _render(project, monkeypatch)
    audio = _decode_audio(out)
    onset = np.argmax(np.abs(audio) > 0.05) / 44100
    # blue starts at film frame 10 - 4 = 6 → 0.6 s; the line at 0.6 + start.
    assert onset == pytest.approx(0.6 + stamped.start, abs=0.005)


@pytest.mark.ffmpeg
def test_a_ducked_bed_and_a_hit_leave_the_picture_untouched(tmp_path, monkeypatch):
    from an.sounds import SYNTH_SOURCE, add_sound, synth_hit, synth_tone

    plain = SceneIR(meta=_meta(2.0), timeline=[Shot(id="red", duration=2.0)])
    silent_film = _render(_project(tmp_path / "plain", plain), monkeypatch)

    line = Dialogue(speaker="x", text="hi", start=1.0, duration=0.5, audio_ref="line")
    scene = SceneIR(
        meta=_meta(2.0).model_copy(update={"sounds": [
            SoundCue(sound="bed", loop=True, duck_db=-20.0, duck_attack=0.1, duck_release=0.1)]}),
        timeline=[Shot(id="red", duration=2.0, dialogue=[line],
                       sounds=[SoundCue(sound="hit", at=0.4, gain_db=-6.0)])],
    )
    project = _project(tmp_path / "sound", scene)
    add_sound(project.mall["sounds"], "bed", synth_tone(200.0, 0.5, amplitude=0.25, attack=0, release=0), source=SYNTH_SOURCE)
    add_sound(project.mall["sounds"], "hit", synth_hit(0.1, seed=3), source=SYNTH_SOURCE)
    project.mall["audio"]["line"] = synth_tone(1000.0, 0.5, amplitude=1e-4)
    out = _render(project, monkeypatch, auto_audio=False)

    # The mix copies the picture: the video bitstream is the concat's own.
    assert _video_bitstream(out) == _video_bitstream(silent_film)
    audio = _decode_audio(out)

    def level(t0, t1):
        seg = audio[int(t0 * 44100): int(t1 * 44100)]
        return float(np.sqrt(2 * (seg.astype(np.float64) ** 2).mean()))

    assert level(0.1, 0.35) == pytest.approx(0.25, rel=0.03)  # the bed, full
    assert level(1.15, 1.45) == pytest.approx(0.025, rel=0.1)  # ducked 20 dB
    assert level(1.75, 1.95) == pytest.approx(0.25, rel=0.03)  # back up
    assert level(0.4, 0.45) > 0.3  # the hit lands on its frame


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_a_real_cutout_render_dissolves(tmp_path):
    """The real renderer's frame manifest feeds the composer: the film has the
    overlapped frame count, and both streams run the shortened length."""
    from an.orchestrate import render_project

    scene = SceneIR(meta=_meta(1.0), timeline=[
        Shot(id="s1", duration=0.5),
        Shot(id="s2", duration=0.5, transition=Transition(kind="dissolve", duration=0.2))])
    project = _project(tmp_path, scene)
    out = render_project(project.root)
    assert len(_decode_rgb(out)) == 5 + 5 - 2
    assert _stream_duration(out, "v") == pytest.approx(0.8, abs=0.01)
    assert _stream_duration(out, "a") == pytest.approx(0.8, abs=0.03)
