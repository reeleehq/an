"""The public dialogue layout (an#767): where each line of a shot plays, as ``an validate`` lays it out."""

from __future__ import annotations

import pytest

from an.ir import Dialogue, Shot, dialogue_layout


def _shot(*lines):
    return Shot(id="s", duration=20.0, dialogue=list(lines))


def test_a_line_without_audio_plays_for_the_offline_estimate_over_its_tempo():
    from an.audio.offline_tts import estimate_speech_duration

    text = "a line nobody has synthesized yet"
    (plain,) = dialogue_layout(_shot(Dialogue(speaker="a", text=text)))
    (fast,) = dialogue_layout(_shot(Dialogue(speaker="a", text=text)), tempo_of=lambda _l: 2.0)
    assert plain.estimated and plain.end == pytest.approx(estimate_speech_duration(text))
    assert fast.end == pytest.approx(plain.end / 2.0)


def test_lines_play_back_to_back_after_their_pause_or_at_their_at():
    lines = [
        Dialogue(speaker="a", text="one", duration=1.0),
        Dialogue(speaker="b", text="two", duration=1.0, pause=0.5),
        Dialogue(speaker="a", text="three", duration=1.0, at=6.0),
    ]
    rows = [(p.k, p.line.text, p.start, p.end) for p in dialogue_layout(_shot(*lines))]
    assert rows == [(0, "one", 0.0, 1.0), (1, "two", 1.5, 2.5), (2, "three", 6.0, 7.0)]


def test_the_private_name_a_genre_imported_is_the_public_layout():
    """cutan's eyeline check imported ``an.ir.validate._dialogue_layout``; it
    keeps working, and unpacks the rows as five-tuples, until it moves."""
    from an.ir.validate import _dialogue_layout

    assert _dialogue_layout is dialogue_layout
    ((k, line, start, end, estimated),) = _dialogue_layout(
        _shot(Dialogue(speaker="a", text="hi", duration=1.0))
    )
    assert (k, line.text, start, end, estimated) == (0, "hi", 0.0, 1.0, False)
