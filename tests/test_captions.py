"""Captions from word timings (an#175): the one page list, the burned-in picture
it compiles to, the SubRip sidecar it writes, and the promise that the two
cannot disagree — across a dissolve, which shortens the film.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import compile_shot
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.assemble import film_timeline
from an.captions import (
    CAPTION_PROP_REF,
    CaptionError,
    CaptionTimingWarning,
    Cue,
    caption_cues,
    caption_pages,
    captioned_shot,
    dump_srt,
    paginate,
    seconds_to_srt_time,
    srt_for_scene,
    wrap_words,
)
from an.ir.schema import (
    Captions,
    Dialogue,
    Meta,
    Narration,
    SceneIR,
    Shot,
    Transition,
    WordTimingIR,
)

FPS = 10
W, H = 640, 360


def _line(text, *, start=0.5, step=0.3, duration=None, timed=True, speaker="a"):
    words = text.split()
    timings = (
        [WordTimingIR(text=w, start=k * step, end=k * step + step * 0.8) for k, w in enumerate(words)]
        if timed
        else None
    )
    return Dialogue(
        speaker=speaker,
        text=text,
        start=start,
        duration=duration if duration is not None else len(words) * step,
        word_timings=timings,
    )


def _scene(*shots, **captions) -> SceneIR:
    return SceneIR(meta=Meta(fps=FPS, captions=Captions(**captions)), timeline=list(shots))


# --- the page list -------------------------------------------------------------------------


def test_pages_follow_the_word_timings_to_the_frame():
    scene = _scene(Shot(id="s", duration=4.0, dialogue=[_line("One two three. Four five")]))
    pages = caption_pages(scene, fps=FPS)
    # line at 0.5 s, words every 0.3 s: 0.5, 0.8, 1.1 | 1.4, 1.7; line ends 0.5 + 1.5
    assert [(p.start, p.end, p.text) for p in pages] == [
        (5, 14, "One two three."),
        (14, 20, "Four five"),
    ]
    assert pages[0].word_frames == (5, 8, 11)


def test_line_breaks_are_made_once_and_carried_by_the_page():
    assert wrap_words(["aaaa", "bb", "cccccc"], 7) == [["aaaa", "bb"], ["cccccc"]]
    assert wrap_words(["waytoolongword"], 5) == [["waytoolongword"]]  # never split
    assert paginate("a b c d e f".split(), max_chars=3, max_lines=2) == [range(0, 4), range(4, 6)]
    scene = _scene(
        Shot(id="s", duration=5.0, dialogue=[_line("alpha beta gamma delta")]),
        max_chars=11,
        max_lines=2,
    )
    (page,) = caption_pages(scene, fps=FPS)
    assert page.lines == (("alpha", "beta"), ("gamma", "delta"))
    assert page.text == "alpha beta\ngamma delta"


def test_a_line_without_timings_is_spread_evenly_and_says_so():
    scene = _scene(Shot(id="s", duration=4.0, dialogue=[_line("a b c d", timed=False, duration=2.0)]))
    with pytest.warns(CaptionTimingWarning, match="no word timings"):
        (page,) = caption_pages(scene, fps=FPS)
    assert page.word_frames == (5, 10, 15, 20)
    strict = scene.model_copy(update={"meta": Meta(fps=FPS, captions=Captions(strict=True))})
    with pytest.raises(CaptionError, match="no word timings"):
        caption_pages(strict, fps=FPS)


def test_a_line_the_audio_pipeline_has_not_placed_is_skipped_loudly():
    unplaced = Dialogue(speaker="a", text="not voiced yet")
    scene = _scene(Shot(id="s", duration=2.0, dialogue=[unplaced]))
    with pytest.warns(CaptionTimingWarning, match="no start/duration"):
        assert caption_pages(scene, fps=FPS) == []
    with pytest.raises(CaptionError):
        caption_pages(scene, fps=FPS, captions=Captions(strict=True))


def test_when_the_provider_timed_different_words_the_timed_words_are_shown():
    line = _line("gonna go").model_copy(
        update={"word_timings": [WordTimingIR(text=w, start=k * 0.2, end=k * 0.2 + 0.1)
                                 for k, w in enumerate(["going", "to", "go"])]}
    )
    scene = _scene(Shot(id="s", duration=3.0, dialogue=[line]))
    with pytest.warns(CaptionTimingWarning, match="timed 3"):
        (page,) = caption_pages(scene, fps=FPS)
    assert page.words == ("going", "to", "go")


def test_narration_is_captioned_too():
    narr = Narration(text="Once upon", start=0.0, duration=1.0,
                     word_timings=[WordTimingIR(text="Once", start=0, end=0.4),
                               WordTimingIR(text="upon", start=0.5, end=0.9)])
    scene = _scene(Shot(id="s", duration=2.0, narration=[narr]))
    (page,) = caption_pages(scene, fps=FPS)
    assert (page.text, page.speaker) == ("Once upon", None)


def test_overlapping_lines_never_share_the_slot():
    a = _line("first line here", start=0.0, step=0.5)  # 0.0 .. 1.5
    b = _line("second", start=1.0, speaker="b")
    scene = _scene(Shot(id="s", duration=3.0, dialogue=[a, b]))
    first, second = caption_pages(scene, fps=FPS)
    assert first.end == second.start == 10
    assert max(first.word_frames) < first.end


def test_pages_are_clipped_to_their_shot():
    scene = _scene(Shot(id="s", duration=1.0, dialogue=[_line("a b c d e", start=0.5)]))
    pages = caption_pages(scene, fps=FPS)
    assert pages and all(p.end <= 10 for p in pages)


# --- the sidecar, in film time -------------------------------------------------------------


def test_a_dissolve_moves_every_later_cue_earlier_by_its_overlap():
    def shot(sid, **kw):
        return Shot(id=sid, duration=2.0, dialogue=[_line("hi there", start=0.2)], **kw)

    cut = _scene(shot("a"), shot("b"))
    dissolve = _scene(shot("a"), shot("b", transition=Transition(kind="dissolve", duration=0.5)))
    fade = _scene(shot("a"), shot("b", transition=Transition(kind="fade", duration=0.5)))
    starts = {
        name: [c.start for c in caption_cues(caption_pages(s, fps=FPS), film_timeline(s.timeline, fps=FPS))]
        for name, s in (("cut", cut), ("dissolve", dissolve), ("fade", fade))
    }
    assert starts["cut"] == [0.2, 2.2]
    assert starts["dissolve"] == [0.2, 1.7]
    assert starts["fade"] == starts["cut"]  # a fade holds the film's length


def test_the_sidecar_is_subrip_of_the_same_pages():
    scene = _scene(Shot(id="s", duration=3.0, dialogue=[_line("Hello there. Friend")]))
    assert srt_for_scene(scene, fps=FPS) == (
        "1\n00:00:00,500 --> 00:00:01,100\nHello there.\n\n"
        "2\n00:00:01,100 --> 00:00:01,400\nFriend\n"
    )


def _shown_frames(scene, shot_index, *, fps=FPS):
    """Per caption entity of one shot, the SHOT-local frames the compiled
    document shows it on — read off the executable spec of the runtime."""
    pages = caption_pages(scene, fps=fps)
    shot = scene.timeline[shot_index]
    captioned, mall = captioned_shot(
        shot, pages, scene.meta.captions, fps=fps, mall={}, shot_index=shot_index
    )
    doc = compile_shot(captioned, mall, fps=fps, width=W, height=H)
    tl = timeline_from_scene(doc)
    ids = [e.id for e in captioned.entities if e.id.startswith("caption_")]
    from an.frame_clock import frame_count

    shown = {eid: [] for eid in ids}
    for f in range(frame_count(shot.duration, fps)):
        pose = evaluate_timeline(tl, f / fps)
        for eid in ids:
            if pose.get((eid, "alpha"), 1.0) == 1.0:
                shown[eid].append(f)
    return [shown[eid] for eid in ids]


def test_the_picture_and_the_sidecar_cannot_disagree_across_a_dissolve():
    """The acceptance line: for every cue, the film frames the compiled
    documents show its page on are EXACTLY [start*fps, end*fps)."""

    def shot(sid, text, **kw):
        return Shot(id=sid, duration=2.0, dialogue=[_line(text, start=0.1)], **kw)

    scene = _scene(
        shot("a", "One two. Three four"),
        shot("b", "Five six seven", transition=Transition(kind="dissolve", duration=0.4)),
        shot("c", "Eight", transition=Transition(kind="fade", duration=0.4)),
    )
    timeline = film_timeline(scene.timeline, fps=FPS)
    cues = caption_cues(caption_pages(scene, fps=FPS), timeline)
    shown_film = []
    for i in range(len(scene.timeline)):
        for frames in _shown_frames(scene, i):
            shown_film.append([timeline.starts[i] + f for f in frames])
    assert len(shown_film) == len(cues) == 4
    for frames, cue in zip(shown_film, cues):
        assert frames == list(range(round(cue.start * FPS), round(cue.end * FPS))), cue
    # and the dissolve really did move shot b's cue: it starts 4 frames early
    assert cues[2].start == pytest.approx((20 - 4 + 1) / FPS)


def test_highlight_lights_each_word_from_its_first_frame_to_the_next():
    scene = _scene(Shot(id="s", duration=2.0, dialogue=[_line("a b c")]), highlight="#ff0000",
                   color="#0000ff")
    (page,) = caption_pages(scene, fps=FPS)
    captioned, mall = captioned_shot(scene.timeline[0], [page], scene.meta.captions, fps=FPS, mall={})
    doc = compile_shot(captioned, mall, fps=FPS, width=W, height=H)
    tl = timeline_from_scene(doc)
    lit = []
    for f in range(page.start, page.end):
        pose = evaluate_timeline(tl, f / FPS)
        lit.append([j for j in range(3) if pose[(f"caption_0/word_{j}", "tint_r")] == 1.0])
    assert lit == [[0]] * 3 + [[1]] * 3 + [[2]] * 3
    # the glyphs are white so the tint IS the colour
    assert {c.visual.color for c in doc.overlay.children[0].children} == {"#ffffff"}


def test_without_highlight_a_page_is_drawn_by_line_and_never_tinted():
    scene = _scene(Shot(id="s", duration=3.0, dialogue=[_line("alpha beta gamma delta")]), max_chars=11)
    captioned, mall = captioned_shot(
        scene.timeline[0], caption_pages(scene, fps=FPS), scene.meta.captions, fps=FPS, mall={}
    )
    doc = compile_shot(captioned, mall, fps=FPS, width=W, height=H)
    (block,) = doc.overlay.children
    assert [c.name for c in block.children] == ["line_0", "line_1"]
    assert not any("tint" in str(a) for a in captioned.actions)


def test_a_caption_block_is_placed_in_the_title_safe_area_at_the_bottom():
    from tituli import safe_area

    scene = _scene(Shot(id="s", duration=2.0, dialogue=[_line("bottom text")]))
    captioned, mall = captioned_shot(
        scene.timeline[0], caption_pages(scene, fps=FPS), scene.meta.captions, fps=FPS, mall={}
    )
    doc = compile_shot(captioned, mall, fps=FPS, width=W, height=H)
    (block,) = doc.overlay.children
    y = block.transform.y + H / 2  # the block node sits at its origin
    area = safe_area(W, H)
    assert H * 0.75 < y < area.y1


def test_a_taken_caption_id_is_refused():
    from an.ir.schema import AssetRef

    shot = Shot(
        id="s",
        duration=2.0,
        dialogue=[_line("hi")],
        entities=[AssetRef(kind="prop", id="caption_0", store="props", ref="x")],
    )
    scene = _scene(shot)
    with pytest.raises(CaptionError, match="caption_0"):
        captioned_shot(shot, caption_pages(scene, fps=FPS), scene.meta.captions, fps=FPS, mall={})


def test_a_caption_the_face_cannot_draw_is_refused_before_any_render():
    scene = _scene(Shot(id="s1", duration=2.0, dialogue=[_line("wait \u2014 what")]))
    pages = caption_pages(scene, fps=FPS)
    with pytest.raises(CaptionError, match="shot 's1'.*U\\+2014"):
        captioned_shot(scene.timeline[0], pages, scene.meta.captions, fps=FPS, mall={},
                       resolution=(W, H))


def test_the_caption_style_overlays_the_props_store_without_hiding_it(tmp_path):
    from an.stores.props import PropsStore

    props = PropsStore(tmp_path)
    scene = _scene(Shot(id="s", duration=2.0, dialogue=[_line("hi")]))
    _, mall = captioned_shot(
        scene.timeline[0], caption_pages(scene, fps=FPS), scene.meta.captions,
        fps=FPS, mall={"props": props},
    )
    assert mall["props"][CAPTION_PROP_REF]["kind"] == "TextDescriptor"
    assert mall["props"]._root == props._root  # an author's relative font still resolves
    assert CAPTION_PROP_REF not in props  # nothing written to the project


# --- review findings (an#175): each one a regression test --------------------------------


def _lit_words(scene, page, *, n_words):
    captioned, mall = captioned_shot(scene.timeline[0], [page], scene.meta.captions, fps=FPS, mall={})
    tl = timeline_from_scene(compile_shot(captioned, mall, fps=FPS, width=W, height=H))
    return [
        [j for j in range(n_words)
         if evaluate_timeline(tl, f / FPS)[(f"caption_0/word_{j}", "tint_r")] == 1.0]
        for f in range(page.start, page.end)
    ]


def test_the_first_word_of_a_page_on_frame_zero_is_lit():
    scene = _scene(Shot(id="s", duration=2.0, dialogue=[_line("a b", start=0.0)]),
                   highlight="#ff0000", color="#0000ff")
    (page,) = caption_pages(scene, fps=FPS)
    assert page.start == 0
    assert _lit_words(scene, page, n_words=2)[:3] == [[0], [0], [0]]


def test_times_between_frames_round_up_to_the_first_frame_that_shows_them():
    scene = _scene(Shot(id="s", duration=3.0, dialogue=[_line("a b", start=0.53, step=0.31)]))
    (page,) = caption_pages(scene, fps=FPS)
    assert (page.start, page.word_frames) == (6, (6, 9))  # 0.53 -> 0.6, 0.84 -> 0.9
    assert srt_for_scene(scene, fps=FPS).split("\n")[1].startswith("00:00:00,600")


def test_every_caption_set_lands_between_frames():
    scene = _scene(Shot(id="s", duration=3.0, dialogue=[_line("a b c. d e", start=0.53)]),
                   highlight="#ff0000")
    captioned, _ = captioned_shot(scene.timeline[0], caption_pages(scene, fps=FPS),
                                  scene.meta.captions, fps=FPS, mall={})
    ats = [a.at * FPS for a in captioned.actions]
    assert ats and all(at == 0 or abs(at - round(at)) == pytest.approx(0.5) for at in ats)


def test_a_page_is_seen_for_at_least_one_frame():
    line = Dialogue(speaker="a", text="blip", start=0.5, duration=0.0,
                    word_timings=[WordTimingIR(text="blip", start=0.0, end=0.0)])
    (page,) = caption_pages(_scene(Shot(id="s", duration=2.0, dialogue=[line])), fps=FPS)
    assert page.end == page.start + 1


def test_a_word_sharing_its_frame_with_the_next_is_never_lit_alone():
    line = Dialogue(speaker="a", text="a b c", start=0.0, duration=1.5, word_timings=[
        WordTimingIR(text=w, start=t, end=t + 0.01) for w, t in (("a", 0.02), ("b", 0.05), ("c", 0.5))])
    scene = _scene(Shot(id="s", duration=2.0, dialogue=[line]), highlight="#ff0000")
    (page,) = caption_pages(scene, fps=FPS)
    lit = _lit_words(scene, page, n_words=3)
    assert lit[0] == [1] and not any(0 in frame for frame in lit)


def test_an_abbreviation_does_not_make_a_page_nobody_sees():
    line = Dialogue(speaker="a", text="Mr. Smith is here", start=1.005, duration=1.0,
                    word_timings=[WordTimingIR(text=w, start=t, end=t + 0.01) for w, t in
                                  (("Mr.", 0.0), ("Smith", 0.015), ("is", 0.3), ("here", 0.5))])
    (page,) = caption_pages(_scene(Shot(id="s", duration=3.0, dialogue=[line])), fps=30)
    assert page.text == "Mr. Smith is here"


def test_two_lines_starting_on_one_frame_warn_instead_of_aborting():
    a, b = _line("first", start=0.5), _line("second", start=0.5, speaker="b")
    with pytest.warns(UserWarning, match="same frame"):
        (page,) = caption_pages(_scene(Shot(id="s", duration=2.0, dialogue=[a, b])), fps=FPS)
    assert page.text == "second"


def test_a_timed_token_with_a_space_is_one_word_per_unit():
    line = Dialogue(speaker="a", text="New York is big", start=0.0, duration=1.5, word_timings=[
        WordTimingIR(text="New York", start=0.0, end=0.4),
        WordTimingIR(text="is", start=0.5, end=0.6), WordTimingIR(text="big", start=1.0, end=1.2)])
    scene = _scene(Shot(id="s", duration=2.0, dialogue=[line]), highlight="#ff0000")
    with pytest.warns(CaptionTimingWarning):
        (page,) = caption_pages(scene, fps=FPS)
    assert page.words == ("New", "York", "is", "big") and page.word_frames == (0, 2, 5, 10)
    captioned, mall = captioned_shot(scene.timeline[0], [page], scene.meta.captions, fps=FPS,
                                     mall={}, resolution=(W, H))
    doc = compile_shot(captioned, mall, fps=FPS, width=W, height=H)
    assert len(doc.overlay.children[0].children) == 4


def test_unsorted_timings_are_sorted_and_said():
    line = Dialogue(speaker="a", text="a b c", start=0.0, duration=2.0, word_timings=[
        WordTimingIR(text=w, start=t, end=t + 0.1) for w, t in (("a", 0.0), ("c", 1.0), ("b", 0.5))])
    with pytest.warns(CaptionTimingWarning, match="not in time order"):
        (page,) = caption_pages(_scene(Shot(id="s", duration=3.0, dialogue=[line])), fps=FPS)
    assert page.words == ("a", "b", "c") and page.word_frames == (0, 5, 10)


def test_a_line_spoken_after_its_shot_ends_is_said():
    scene = _scene(Shot(id="s", duration=1.0, dialogue=[_line("late", start=1.5)]))
    with pytest.warns(UserWarning, match="after the shot ends"):
        assert caption_pages(scene, fps=FPS) == []


def test_a_caption_wider_than_the_title_safe_area_is_refused():
    scene = _scene(Shot(id="s", duration=3.0, dialogue=[_line("word " * 8)]))
    with pytest.raises(CaptionError, match="title-safe"):
        captioned_shot(scene.timeline[0], caption_pages(scene, fps=FPS), scene.meta.captions,
                       fps=FPS, mall={}, resolution=(360, 640))


# --- the IR: opt-in, omit-when-unset, round trip -------------------------------------------


def test_unset_captions_leave_no_trace():
    assert "captions" not in Meta().model_dump()
    assert "captions" not in SceneIR().model_dump_json()


def test_captions_round_trip_through_scene_md():
    from an.ir.sync import ir_to_markdown, markdown_to_ir

    for captions in (Captions(), Captions(highlight="#ffcc00", max_chars=30, burn=False)):
        scene = SceneIR(meta=Meta(title="t", captions=captions), timeline=[Shot(id="s")])
        assert markdown_to_ir(ir_to_markdown(scene)).meta.captions == captions


def test_a_bad_colour_is_refused():
    with pytest.raises(ValueError, match="#rrggbb"):
        Captions(highlight="yellow")


# --- the render path: one page list, two outputs --------------------------------------------


class _RecordingRenderer:
    name = "recording"
    supported_renderers = ("cutout",)

    def __init__(self):
        self.calls = []

    def can_render(self, shot):
        return True

    def render(self, shot, ctx):
        from an.adapters._base import RenderResult

        self.calls.append((shot, ctx))
        out = Path(ctx.work_dir) / f"{shot.id}.mp4"
        out.write_bytes(b"not really an mp4")
        return RenderResult(mp4_path=out, duration=shot.duration)


def _no_ffmpeg(monkeypatch):
    """These tests are about which files the render writes, not the encode: the
    concat is stubbed (the default CI lane has no ffmpeg)."""
    import shutil

    import an.render as render_mod

    monkeypatch.setattr(
        render_mod, "_ffmpeg_concat", lambda inputs, out: shutil.copy(list(inputs)[0], out)
    )


def _render(tmp_path, monkeypatch, scene):
    from an import init
    from an.project import load
    import an.render as render_mod

    root = init(tmp_path / "demo")
    project = load(root)
    project.mall["scenes"]["main"] = scene
    project = load(root)
    renderer = _RecordingRenderer()
    _no_ffmpeg(monkeypatch)
    monkeypatch.setattr(render_mod._DEFAULT_REGISTRY, "find_for", lambda shot: renderer)
    out = render_mod.render(project, auto_audio=False)
    return project, renderer, out


def test_render_burns_the_pages_and_writes_the_sidecar_beside_the_mp4(tmp_path, monkeypatch):
    scene = _scene(Shot(id="s", duration=2.0, dialogue=[_line("Hello there")]))
    project, renderer, out = _render(tmp_path, monkeypatch, scene)
    ((shot, ctx),) = renderer.calls
    assert [e.id for e in shot.entities] == ["caption_0"]
    assert ctx.mall["props"][CAPTION_PROP_REF]["kind"] == "TextDescriptor"
    srt = out.with_suffix(".srt")
    assert srt.read_text("utf-8") == srt_for_scene(scene, fps=FPS)
    assert project.mall["captions"]["main"] == srt.read_bytes()
    # the captions were materialised for the render, never written to the scene
    assert project.mall["scenes"]["main"].timeline[0].entities == []


def test_no_captions_means_no_sidecar_and_an_untouched_shot(tmp_path, monkeypatch):
    scene = SceneIR(meta=Meta(fps=FPS), timeline=[Shot(id="s", dialogue=[_line("hi")])])
    project, renderer, out = _render(tmp_path, monkeypatch, scene)
    ((shot, ctx),) = renderer.calls
    assert shot.entities == [] and ctx.mall is project.mall
    assert not out.with_suffix(".srt").exists()
    assert list(project.mall["captions"]) == []


def test_sidecar_only_captions_leave_the_picture_alone(tmp_path, monkeypatch):
    scene = _scene(Shot(id="s", duration=2.0, dialogue=[_line("hi")]), burn=False)
    _, renderer, out = _render(tmp_path, monkeypatch, scene)
    ((shot, _),) = renderer.calls
    assert shot.entities == []
    assert out.with_suffix(".srt").read_text("utf-8").startswith("1\n")


def test_a_stale_sidecar_is_removed_when_this_render_writes_none(tmp_path, monkeypatch):
    scene = _scene(Shot(id="s", duration=2.0, dialogue=[_line("hi")]))
    project, _, out = _render(tmp_path, monkeypatch, scene)
    assert out.with_suffix(".srt").exists()
    import an.render as render_mod

    off = _scene(Shot(id="s", duration=2.0, dialogue=[_line("hi")]), sidecar=False)
    project.mall["scenes"]["main"] = off
    from an.project import load

    render_mod.render(load(project.root), auto_audio=False)
    assert not out.with_suffix(".srt").exists()


def test_an_authors_own_srt_is_left_alone_when_the_scene_has_no_captions(tmp_path, monkeypatch):
    scene = SceneIR(meta=Meta(fps=FPS), timeline=[Shot(id="s", dialogue=[_line("hi")])])
    from an import init
    from an.project import load
    import an.render as render_mod

    root = init(tmp_path / "demo")
    (root / "output" / "main.srt").write_text("mine", encoding="utf-8")
    project = load(root)
    project.mall["scenes"]["main"] = scene
    _no_ffmpeg(monkeypatch)
    monkeypatch.setattr(render_mod._DEFAULT_REGISTRY, "find_for", lambda shot: _RecordingRenderer())
    with pytest.warns(UserWarning, match="NOT written by this render"):
        render_mod.render(load(root), auto_audio=False)
    assert (root / "output" / "main.srt").read_text("utf-8") == "mine"


def test_a_shot_off_the_frame_grid_does_not_send_a_captioned_film_to_the_assembler(
    tmp_path, monkeypatch
):
    """an#200: a captioned film whose shots are not whole frames long used to be
    ASSEMBLED, because the concat advanced by container length and drifted off
    the sidecar's frame grid. Each shot's audio is cut to its picture since
    an#195, so the concat is on the grid (measured in
    `tests/test_delivered_frame_rate.py`) and the ordinary path delivers it —
    with no warning, even from a renderer that keeps no frames."""
    import warnings

    import an.render as render_mod

    monkeypatch.setattr(render_mod, "assemble_film", lambda *a, **k: pytest.fail("assembled"))
    scene = _scene(Shot(id="a", duration=1.04, dialogue=[_line("hi")]), Shot(id="b", duration=1.0))
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        project, _, _ = _render(tmp_path, monkeypatch, scene)
    assert (project.root / "output" / "main.srt").exists()


# --- the SubRip mirror and the import boundary (Decision 2 of epic #9) ----------------------

#: What `mixing.srt.dump_srt` wrote for these cues (mixing 0.0.55): the pin that
#: holds where `mixing` is not installed, which is CI.
_GOLDEN_SRT = (
    "1\n00:00:00,000 --> 00:00:01,500\nfirst\n\n"
    "2\n00:59:59,999 --> 01:00:00,000\ntwo\nlines\n\n"
    "3\n00:00:02,346 --> 00:00:03,000\nrounded\n"
)
_GOLDEN_CUES = [
    Cue(1, 0.0, 1.5, "first"),
    Cue(5, 3599.999, 3600.0005, "two\nlines"),
    Cue(9, 2.3456, 3.0, "rounded"),
]


def test_the_subrip_mirror_matches_its_pinned_output():
    assert dump_srt(_GOLDEN_CUES) == _GOLDEN_SRT


def test_the_subrip_mirror_matches_mixing_field_for_field_and_byte_for_byte():
    srt = pytest.importorskip("mixing.srt", reason="mixing is not installed; the literal pin holds")
    import dataclasses

    assert [(f.name, f.type) for f in dataclasses.fields(srt.Cue)] == [
        (f.name, f.type) for f in dataclasses.fields(Cue)
    ]
    mixing_cues = [srt.Cue(c.index, c.start, c.end, c.text) for c in _GOLDEN_CUES]
    assert srt.dump_srt(mixing_cues) == dump_srt(_GOLDEN_CUES) == _GOLDEN_SRT
    for t in (0.0, 0.0004, 0.0005, 59.9995, 3599.9996, 1e5 / 3, -1.0):
        assert srt.seconds_to_srt_time(t) == seconds_to_srt_time(t), t


def test_an_never_imports_mixing():
    """The boundary: `an` MIRRORS `mixing.srt` rather than depending on it,
    because installing `mixing` would pull a GPL-built ffmpeg binary (via
    moviepy -> imageio-ffmpeg) past a licence perimeter that reads declared
    metadata only. See `an/captions.py`'s docstring before changing this."""
    root = Path(__file__).resolve().parents[1] / "an"
    offenders = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] == "mixing"]
    assert offenders == []


def test_building_captions_loads_no_media_stack():
    code = (
        "import sys, an.captions, an.render\n"
        "from an.ir.schema import *\n"
        "line = Dialogue(speaker='a', text='hi', start=0.0, duration=1.0,"
        " word_timings=[WordTimingIR(text='hi', start=0.0, end=0.5)])\n"
        "scene = SceneIR(meta=Meta(captions=Captions()), timeline=[Shot(id='s', dialogue=[line])])\n"
        "an.captions.srt_for_scene(scene, fps=10)\n"
        "print(sorted(m for m in ('mixing', 'moviepy', 'cv2', 'pydub', 'scipy') if m in sys.modules))\n"
    )
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=root,
        env={**__import__("os").environ, "PYTHONPATH": str(root)}, check=True,
    ).stdout
    assert out.strip() == "[]"


# --- pixels ---------------------------------------------------------------------------------


def _ink_box(png, rgb, *, tol=40):
    from PIL import Image

    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()
    hits = [
        (x, y) for y in range(h) for x in range(w)
        if all(abs(px[x, y][i] - rgb[i]) <= tol for i in range(3))
    ]
    if not hits:
        return None
    xs, ys = [p[0] for p in hits], [p[1] for p in hits]
    return min(xs), min(ys), max(xs), max(ys)


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_the_caption_pages_through_the_line_and_lights_the_spoken_word(
    hermetic_browser, tmp_path
):
    """Rendered: nothing before the line starts; then the page at the bottom of
    the frame, blue, with the spoken word red — and the red moving right as the
    words are spoken; nothing once the line has ended."""
    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer

    blue, red = (0x1F, 0x4E, 0x9A), (0xC0, 0x39, 0x2B)
    line = _line("Words on screen", start=0.3, step=0.2, duration=0.6)  # 0.3 .. 0.9
    scene = _scene(
        Shot(id="s", duration=1.2, dialogue=[line]), color="#1f4e9a", highlight="#c0392b",
        size=0.08,
    )
    captioned, mall = captioned_shot(
        scene.timeline[0], caption_pages(scene, fps=FPS), scene.meta.captions, fps=FPS, mall={}
    )
    result = CutoutRenderer().render(
        captioned,
        RenderContext(mall=mall, work_dir=tmp_path, fps=FPS, resolution=(W, H), strict_assets=True),
    )
    frames = result.frame_manifest
    assert _ink_box(frames[2], blue) is None and _ink_box(frames[2], red) is None
    lit = [_ink_box(frames[f], red) for f in (3, 5, 7)]  # words 0, 1, 2
    assert all(lit), lit
    assert lit[0][2] < lit[1][0] and lit[1][2] < lit[2][0]  # left to right
    assert _ink_box(frames[5], blue) is not None  # the unspoken words
    assert lit[0][1] > H * 0.7  # at the bottom
    assert _ink_box(frames[10], blue) is None and _ink_box(frames[10], red) is None
    assert hermetic_browser["blocked"] == [], hermetic_browser["blocked"]
