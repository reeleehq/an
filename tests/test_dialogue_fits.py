"""`an validate` warns when a shot is too short for its dialogue.

The shot's audio is trimmed to the shot, so a line running past the shot end
loses its tail with no error anywhere. An e2e run shrank an 8.2 s shot holding
7.1 s of speech to 3.0 s and `an validate` said nothing about it.
"""

from __future__ import annotations

from an.audio.offline_tts import OfflineTTS, estimate_speech_duration
from an.ir.schema import Dialogue, SceneIR, Shot
from an.ir.validate import validate_semantic

LINE = "Dude, the school replaced the cafeteria with a vending machine."


def _overruns(scene):
    return [
        f for f in validate_semantic(scene).findings
        if "past the shot" in f.description
    ]


def test_the_estimate_is_what_the_offline_voice_produces():
    assert OfflineTTS().synthesize(LINE).duration == round(
        estimate_speech_duration(LINE) * 22050
    ) / 22050


def test_before_synthesis_the_estimate_catches_an_overrun():
    need = estimate_speech_duration(LINE)
    short = SceneIR(timeline=[Shot(id="s", duration=need / 2,
                                   dialogue=[Dialogue(speaker="stan", text=LINE)])])
    (f,) = _overruns(short)
    assert f.severity == "warning" and f.ir_path == "timeline/0/dialogue/0"
    assert "offline voice" in f.description and "cut off" in f.description

    fits = SceneIR(timeline=[Shot(id="s", duration=need + 0.1,
                                  dialogue=[Dialogue(speaker="stan", text=LINE)])])
    assert _overruns(fits) == []


def test_lines_are_laid_back_to_back_like_the_pipeline_lays_them():
    one = estimate_speech_duration(LINE)
    shot = Shot(
        id="s",
        duration=1.5 * one,  # holds the first line, not the second
        dialogue=[Dialogue(speaker="stan", text=LINE), Dialogue(speaker="kyle", text=LINE)],
    )
    (f,) = _overruns(SceneIR(timeline=[shot]))
    assert f.ir_path == "timeline/0/dialogue/1"


def test_after_synthesis_the_real_timing_is_used():
    """A stamped line (start, duration) is judged exactly, whatever its text."""
    stamped = Dialogue(speaker="stan", text="Hi.", start=2.0, duration=2.5)
    (f,) = _overruns(SceneIR(timeline=[Shot(id="s", duration=4.0, dialogue=[stamped])]))
    assert "as synthesized" in f.description and "4.50s" in f.description
    assert _overruns(SceneIR(timeline=[Shot(id="s", duration=4.5, dialogue=[stamped])])) == []
