"""Dialogue timing inside a shot: a pause before a line, or a start pinned in shot time (an#187).

Before this, a shot's lines played back to back from its start and `scene.md`
could not say otherwise, so an author wanting "hi — a beat — bye" split every
beat into its own shot (end-user runs measured 17–19 cuts/min against style
targets of 8–14). `Dialogue.pause` / `Dialogue.at` are what the author wrote;
`Dialogue.start` is what the audio pipeline derives from them on every pass.
Every consumer reads `start`, so each one is tested here against a shifted line:
the audio mux (`mix_plan`), the visemes (`compile_shot`), captions, ducking, and
`an validate`'s overrun warning.
"""

from __future__ import annotations

import json
import warnings

import pytest

from an.audio.offline_tts import OfflineTTS, estimate_speech_duration
from an.audio.pipeline import audio_key, produce_audio_for_scene
from an.ir.schema import AssetRef, Dialogue, SceneIR, Shot
from an.ir.sync import SceneMarkdownError, ir_to_markdown, markdown_to_ir
from an.ir.validate import validate_semantic

_MD = """# T

```yaml meta
title: T
duration: 6
```

## Shot s1 (cutout)

```yaml shot
duration: 6
```

```dialogue
{lines}
```
"""


def _md(*lines: str) -> str:
    return _MD.format(lines="\n".join(lines))


def _lines(*lines: str) -> list[Dialogue]:
    return markdown_to_ir(_md(*lines)).timeline[0].dialogue


def _scene(*lines: Dialogue, duration: float = 6.0) -> SceneIR:
    entities = [
        AssetRef(kind="character", id=s, store="characters", ref=f"{s}-v1")
        for s in dict.fromkeys(line.speaker for line in lines)
    ]
    return SceneIR(
        timeline=[
            Shot(id="s1", duration=duration, entities=entities, dialogue=list(lines))
        ]
    )


class _CountingTTS(OfflineTTS):
    """The offline voice, counting how often it is actually asked to speak."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def synthesize(self, text, voice_id="default"):
        self.calls += 1
        return super().synthesize(text, voice_id)


def _mall() -> dict:
    return {"audio": {}, "visemes": {}}


# -----------------------------------------------------------------------------
# scene.md grammar: parser and writer
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spelling, expected",
    [
        ("y (pause 1.5): Bye.", {"pause": 1.5}),
        ("y (pause 1.5s): Bye.", {"pause": 1.5}),
        ("y (PAUSE .5): Bye.", {"pause": 0.5}),
        ("y (at 3): Bye.", {"at": 3.0}),
        ("y (at 3.25s): Bye.", {"at": 3.25}),
        ("y [sad] (pause 1.5): Bye.", {"pause": 1.5, "emotion": "sad"}),
        ("y (pause 1.5) [sad]: Bye.", {"pause": 1.5, "emotion": "sad"}),
        ("y [sad]: Bye.", {"emotion": "sad"}),
        ("y: Bye.", {}),
    ],
)
def test_the_md_grammar_reads_a_pause_or_an_at(spelling, expected):
    (line,) = _lines(spelling)
    assert line.speaker == "y" and line.text == "Bye."
    got = {k: getattr(line, k) for k in ("pause", "at", "emotion")}
    assert got == {"pause": None, "at": None, "emotion": None, **expected}


@pytest.mark.parametrize(
    "bad, says",
    [
        ("maya (warm): hi", "not a timing"),  # the an#96 typo stays refused
        ("maya (pause): hi", "not a timing"),
        ("maya (pause -1): hi", "not a timing"),
        ("maya (pause 1) (at 2): hi", "two timings"),
        ("maya (pause 1) (pause 2): hi", "two timings"),
        ("maya [sad] [happy]: hi", "two emotions"),
        ("maya [very sad]: hi", "not an emotion"),
    ],
)
def test_a_malformed_timing_is_refused_naming_the_line(bad, says):
    with pytest.raises(SceneMarkdownError) as e:
        _lines("x: fine", bad)
    assert bad in str(e.value) and says in str(e.value)
    assert "(pause 1.5)" in str(e.value)  # the error teaches the grammar


def test_the_schema_refuses_both_a_pause_and_an_at():
    with pytest.raises(ValueError, match="both `pause` and `at`"):
        Dialogue(speaker="a", text="b", pause=1.0, at=2.0)
    with pytest.raises(ValueError):
        Dialogue(speaker="a", text="b", pause=-0.5)


def test_md_to_ir_to_md_round_trips_the_timing():
    md = _md(
        "x: Hi, Y.",
        "y [sad] (pause 1.5): Bye.",
        "x (at 4.25): Wait.",
        "y (pause 0.1): No.",
    )
    scene = markdown_to_ir(md)
    again = markdown_to_ir(ir_to_markdown(scene))
    assert again.model_dump() == scene.model_dump()
    written = ir_to_markdown(scene)
    assert "y [sad] (pause 1.5): Bye." in written
    assert "x (at 4.25): Wait." in written
    # And through JSON, which is what `an sync` writes.
    doc = json.loads(scene.model_dump_json())
    assert SceneIR.model_validate(doc).model_dump() == scene.model_dump()


def test_an_unset_timing_leaves_no_key_in_the_json():
    """Every committed `ir/scene.json` predates the fields: a defaulted null
    on every line would rewrite all of them on the next `an sync`."""
    line = json.loads(Dialogue(speaker="a", text="b").model_dump_json())
    assert "pause" not in line and "at" not in line
    set_ = json.loads(Dialogue(speaker="a", text="b", pause=0.0).model_dump_json())
    assert set_["pause"] == 0.0 and "at" not in set_


# -----------------------------------------------------------------------------
# The audio pipeline derives `start`
# -----------------------------------------------------------------------------


def test_a_pause_shifts_its_line_and_every_line_after_it():
    scene = _scene(
        Dialogue(speaker="x", text="Hi, Y."),
        Dialogue(speaker="y", text="Bye.", pause=1.5),
        Dialogue(speaker="x", text="Oh."),
    )
    produce_audio_for_scene(scene)
    a, b, c = scene.timeline[0].dialogue
    assert a.start == 0.0
    assert b.start == pytest.approx(a.duration + 1.5)
    assert c.start == pytest.approx(b.start + b.duration)


def test_an_at_pins_its_line_and_the_next_follows_it():
    scene = _scene(
        Dialogue(speaker="x", text="Hi."),
        Dialogue(speaker="y", text="Bye.", at=4.0),
        Dialogue(speaker="x", text="Oh.", pause=0.25),
    )
    produce_audio_for_scene(scene)
    _, b, c = scene.timeline[0].dialogue
    assert b.start == 4.0
    assert c.start == pytest.approx(4.0 + b.duration + 0.25)


def test_editing_a_pause_re_times_the_shot_without_re_synthesizing():
    """The acceptance line of an#187: the edit moves `start` on the NEXT pass,
    for the edited line and every line after it, and the voice is never
    asked again — the stamped line is `already_done`, and `start` is derived
    on every pass rather than trusted from the stamp."""
    tts, mall = _CountingTTS(), _mall()
    scene = _scene(
        Dialogue(speaker="x", text="Hi, Y."),
        Dialogue(speaker="y", text="Bye.", pause=1.5),
        Dialogue(speaker="x", text="Oh."),
    )
    produce_audio_for_scene(scene, mall, tts=tts)
    assert tts.calls == 3
    before = [line.start for line in scene.timeline[0].dialogue]
    refs = [line.audio_ref for line in scene.timeline[0].dialogue]

    scene.timeline[0].dialogue[1].pause = 0.5  # what an `an iterate` patch does
    produce_audio_for_scene(scene, mall, tts=tts)
    after = [line.start for line in scene.timeline[0].dialogue]
    assert tts.calls == 3  # nothing re-synthesized
    assert [line.audio_ref for line in scene.timeline[0].dialogue] == refs
    assert after[0] == before[0]
    assert after[1] == pytest.approx(before[1] - 1.0)
    assert after[2] == pytest.approx(before[2] - 1.0)


def test_an_md_edit_of_a_pause_costs_no_synthesis_either():
    """An `scene.md` edit re-parses the scene (no stamps survive); the
    content-keyed audio store makes the re-stamp free."""
    tts, mall = _CountingTTS(), _mall()
    first = markdown_to_ir(_md("x: Hi, Y.", "y (pause 1.5): Bye."))
    produce_audio_for_scene(first, mall, tts=tts)
    edited = markdown_to_ir(_md("x: Hi, Y.", "y (pause 0.5): Bye."))
    produce_audio_for_scene(edited, mall, tts=tts)
    assert tts.calls == 2
    a, b = edited.timeline[0].dialogue
    assert b.start == pytest.approx(a.duration + 0.5)


def test_the_timing_is_not_in_any_cache_key():
    """A pause moves a line, it does not change what the line sounds like:
    the audio and viseme keys of a paused line are the unpaused line's."""
    plain = _scene(Dialogue(speaker="x", text="Hi."), Dialogue(speaker="y", text="Bye."))
    paused = _scene(
        Dialogue(speaker="x", text="Hi.", at=0.5),
        Dialogue(speaker="y", text="Bye.", pause=1.5),
    )
    produce_audio_for_scene(plain)
    produce_audio_for_scene(paused)
    for p, q in zip(plain.timeline[0].dialogue, paused.timeline[0].dialogue):
        assert (p.audio_ref, p.viseme_ref) == (q.audio_ref, q.viseme_ref)
        assert p.audio_ref == audio_key(p.text, "default", "offline")


def test_an_unpaused_scene_is_stamped_exactly_as_before():
    """The derivation must reproduce the old back-to-back cursor bit for bit —
    `start = cursor + 0.0` — or every committed stamp would move."""
    scene = _scene(*(Dialogue(speaker="x", text=t) for t in ("One.", "Two two.", "3")))
    produce_audio_for_scene(scene)
    cursor = 0.0
    for line in scene.timeline[0].dialogue:
        assert line.start == cursor
        cursor = line.start + line.duration
    produce_audio_for_scene(scene)  # a second pass changes nothing
    again = [line.start for line in scene.timeline[0].dialogue]
    cursor = 0.0
    for start, line in zip(again, scene.timeline[0].dialogue):
        assert start == cursor
        cursor = start + line.duration


def test_an_authored_start_from_before_at_existed_is_kept_as_at():
    """A `start` on a line never synthesized was authored (the Python API has
    always accepted one). It becomes the line's `at` on first synthesis, so it
    survives every later pass — where the old code honoured it once and reset
    it to the running cursor on the next re-synthesis."""
    scene = _scene(Dialogue(speaker="x", text="late line", start=5.0), duration=10.0)
    produce_audio_for_scene(scene)
    (line,) = scene.timeline[0].dialogue
    assert (line.start, line.at) == (5.0, 5.0)
    produce_audio_for_scene(scene)
    assert line.start == 5.0
    assert "(at 5)" in ir_to_markdown(scene)


# -----------------------------------------------------------------------------
# Every consumer of `start` follows the shifted line
# -----------------------------------------------------------------------------


def _hi_pause_bye() -> SceneIR:
    scene = _scene(
        Dialogue(speaker="x", text="Hi, Y."),
        Dialogue(speaker="y", text="Bye.", pause=1.5),
    )
    return scene


def test_the_mux_and_the_ducking_follow_the_shifted_line(tmp_path):
    from an.assemble import duck_gain, film_timeline, mix_plan

    mall = _mall()
    scene = produce_audio_for_scene(_hi_pause_bye(), mall)
    a, b = scene.timeline[0].dialogue
    plan = mix_plan(scene, film_timeline(scene.timeline, fps=24), mall, tmp_path)
    assert [p.at for p in plan.placements] == pytest.approx([0.0, b.start])
    assert plan.dialogue_spans == pytest.approx(
        [(0.0, a.duration), (b.start, b.start + b.duration)]
    )
    # Ducked under each line, and back up in the pause between them.
    spans = plan.dialogue_spans
    gap = (a.duration + b.start) / 2
    assert duck_gain(gap, spans, duck_db=-12, attack=0.1, release=0.1) == pytest.approx(1.0)
    assert duck_gain(b.start + 0.1, spans, duck_db=-12, attack=0.1, release=0.1) < 1.0


def test_the_per_shot_mux_places_the_shifted_line(tmp_path):
    from types import SimpleNamespace

    from an.adapters.cutout.render import _stage_audio_inputs

    mall = _mall()
    scene = produce_audio_for_scene(_hi_pause_bye(), mall)
    _, b = scene.timeline[0].dialogue
    placed = _stage_audio_inputs(scene.timeline[0], SimpleNamespace(mall=mall), tmp_path)
    assert [at for _path, at in placed] == pytest.approx([0.0, b.start])


def test_the_visemes_follow_the_shifted_line():
    from an.adapters.cutout.compile import compile_shot

    scene = produce_audio_for_scene(_hi_pause_bye())
    _, b = scene.timeline[0].dialogue
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the placeholder rig stands in, and says so
        doc = compile_shot(scene.timeline[0])
    y_track = next(t for t in doc.timeline.tracks if t.target_root == "y")
    (clip,) = [c for c in y_track.clips if c.animation_id.startswith("__viseme__")]
    assert clip.start_time == pytest.approx(b.start)
    assert clip.duration == pytest.approx(b.duration)


def test_the_captions_follow_the_shifted_line():
    from an.assemble import film_timeline
    from an.captions import caption_cues, caption_pages

    scene = produce_audio_for_scene(_hi_pause_bye())
    _, b = scene.timeline[0].dialogue
    fps = 24
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # offline lip-sync keeps no word timings
        pages = caption_pages(scene, fps=fps)
    cues = caption_cues(pages, film_timeline(scene.timeline, fps=fps))
    bye = next(c for c in cues if "Bye" in c.text)
    assert bye.start == pytest.approx(b.start, abs=1 / fps)
    hi = next(c for c in cues if "Hi" in c.text)
    assert hi.end <= b.start + 1 / fps  # the pause is caption-free


def _overruns(scene):
    return [f for f in validate_semantic(scene).findings if "past the shot" in f.description]


def test_the_overrun_warning_counts_the_pause_before_and_after_synthesis():
    need = estimate_speech_duration("Hi, Y.") + estimate_speech_duration("Bye.")
    fits = _hi_pause_bye()
    fits.timeline[0].duration = need + 1.6
    assert _overruns(fits) == []
    tight = _hi_pause_bye()
    tight.timeline[0].duration = need + 1.0  # enough without the pause, not with it
    (before,) = _overruns(tight)
    assert before.ir_path == "timeline/0/dialogue/1" and "offline voice" in before.description
    produce_audio_for_scene(tight)
    (after,) = _overruns(tight)
    assert "as synthesized" in after.description


def test_the_overrun_warning_judges_an_edited_pause_not_the_stale_stamp():
    scene = produce_audio_for_scene(_hi_pause_bye())
    a, b = scene.timeline[0].dialogue
    scene.timeline[0].duration = b.start + b.duration + 0.05
    assert _overruns(scene) == []
    b.pause = 3.0  # edited after synthesis; the stamped start is now stale
    (f,) = _overruns(scene)
    assert f.ir_path == "timeline/0/dialogue/1"


def test_one_speaker_cannot_say_two_lines_at_once():
    overlap = _scene(
        Dialogue(speaker="x", text="A long opening line here."),
        Dialogue(speaker="x", text="Again.", at=0.2),
    )
    (f,) = [
        f for f in validate_semantic(overlap).findings if "one mouth" in f.description
    ]
    assert f.severity == "warning" and f.ir_path == "timeline/0/dialogue/1"
    crosstalk = _scene(
        Dialogue(speaker="x", text="A long opening line here."),
        Dialogue(speaker="y", text="Again.", at=0.2),
    )
    assert not [
        f for f in validate_semantic(crosstalk).findings if "one mouth" in f.description
    ]


def test_an_iterate_patch_of_a_pause_validates_and_re_times():
    from an.iterate import Patch, _apply_one

    scene = produce_audio_for_scene(_hi_pause_bye())
    doc = json.loads(scene.model_dump_json())
    _apply_one(doc, Patch(op="set", path="timeline/0/dialogue/1/pause", value=0.25))
    patched = SceneIR.model_validate(doc)
    produce_audio_for_scene(patched)
    a, b = patched.timeline[0].dialogue
    assert b.start == pytest.approx(a.duration + 0.25)
