"""A dialogue line's voice in ``scene.md``: ``narrator (voice carl_recorded): text`` (an#492).

``Dialogue.voice_ref`` lived in ``ir/scene.json`` only, so an edit of ``scene.md``
regenerated the JSON from the Markdown and dropped a narrator's recorded voice.
It is now a modifier of the line, in the parentheses that hold the timing.
"""

from __future__ import annotations

import pytest

from an.ir.schema import Dialogue
from an.ir.sync import (
    SceneMarkdownError,
    _format_dialogue_line,
    _parse_dialogue_line,
    ir_to_markdown,
    markdown_to_ir,
)


def test_a_line_names_its_voice():
    line = _parse_dialogue_line("narrator (voice carl_recorded): Once upon a time.", where="")
    assert (line.speaker, line.voice_ref, line.text) == (
        "narrator",
        "carl_recorded",
        "Once upon a time.",
    )


@pytest.mark.parametrize(
    "text",
    [
        "narrator (voice carl_recorded): Once.",
        "narrator {sighs} (pause 1.5) (voice carl-2.take1): Once.",
        "narrator (at 3) (voice v): Once.",
    ],
)
def test_the_voice_round_trips_with_the_other_modifiers(text):
    line = _parse_dialogue_line(text, where="")
    again = _parse_dialogue_line(_format_dialogue_line(line), where="")
    assert again == line and again.voice_ref


def test_a_line_without_a_voice_is_written_as_before():
    line = Dialogue(speaker="ned", text="Fine.", pause=1.0)
    assert _format_dialogue_line(line) == "ned (pause 1): Fine."


def test_an_edit_of_scene_md_keeps_the_voice(tmp_path):
    """The failure of an#492: markdown -> IR -> markdown -> IR dropped voice_ref."""
    md = (
        "# T\n\n```yaml meta\ntitle: T\nduration: 2\n```\n\n## Shot s1 (cutout)\n\n"
        "```yaml shot\nduration: 2\n```\n\n```dialogue\n"
        "narrator (voice carl_recorded): Once upon a time.\n```\n"
    )
    scene = markdown_to_ir(md)
    assert scene.timeline[0].dialogue[0].voice_ref == "carl_recorded"
    scene2 = markdown_to_ir(ir_to_markdown(scene))
    assert scene2.timeline[0].dialogue[0].voice_ref == "carl_recorded"


@pytest.mark.parametrize(
    "text, message",
    [
        ("a (voice x) (voice y): hi", "two voices"),
        ("a (voice): hi", "not a timing or a voice"),
        ("a (voice has space): hi", "not a timing or a voice"),
    ],
)
def test_a_malformed_voice_is_refused_with_the_grammar(text, message):
    with pytest.raises(SceneMarkdownError, match=message) as info:
        _parse_dialogue_line(text, where="")
    assert "(voice <key>)" in str(info.value)


def test_a_voice_bound_through_the_store_is_written_into_scene_md(tmp_path):
    """`an voices import` sets the line's voice_ref and saves: scene.md must carry it."""
    from an import init, load
    from an.stores import build_project_mall

    root = init(tmp_path / "p")
    md = root / "scene.md"
    md.write_text(
        "# T\n\n```yaml meta\ntitle: T\nduration: 2\n```\n\n## Shot s1 (cutout)\n\n"
        "```yaml shot\nduration: 2\n```\n\n```dialogue\nnarrator: Once upon a time.\n```\n",
        encoding="utf-8",
    )
    project = load(root)
    project.scene.timeline[0].dialogue[0].voice_ref = "carl_recorded"
    build_project_mall(root)["scenes"]["main"] = project.scene
    assert "narrator (voice carl_recorded): Once upon a time." in md.read_text(encoding="utf-8")
    again = load(root)  # a reload re-reads the pair: still bound
    assert again.scene.timeline[0].dialogue[0].voice_ref == "carl_recorded"
