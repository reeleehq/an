"""Voice leveling without the shared loudness component (an#563).

``an.audio.loudness`` measures and limits through ``mixing.loudness`` (the
``loudness`` extra). Absent, leveling raises a typed, install-hinting error and
the render's spread warning is skipped, as it is without ffmpeg.
"""

from __future__ import annotations

import sys

import pytest

from an.audio import loudness


@pytest.fixture
def no_mixing(monkeypatch):
    monkeypatch.setitem(sys.modules, "mixing.loudness", None)  # import raises
    if "mixing" in sys.modules:  # and the package no longer hands out the module
        monkeypatch.delattr(sys.modules["mixing"], "loudness", raising=False)


def test_leveling_without_the_component_names_the_extra(no_mixing):
    assert not loudness.component_available()
    with pytest.raises(loudness.LoudnessComponentMissing, match=r"an\[loudness\]"):
        loudness.limit_peaks([[2.0]], ceiling=1.0)
    assert issubclass(loudness.LoudnessComponentMissing, loudness.VoiceLoudnessError)
    assert issubclass(loudness.LoudnessComponentMissing, ImportError)


def test_the_spread_report_is_skipped_without_the_component(no_mixing, monkeypatch):
    from an.audio import pipeline
    from an.ir.schema import Dialogue, Meta, SceneIR, Shot

    monkeypatch.setattr(pipeline.shutil, "which", lambda name: "/bin/ffmpeg")
    scene = SceneIR(
        meta=Meta(title="t"),
        timeline=[
            Shot(id="s", duration=1.0, dialogue=[Dialogue(speaker="a", text="x")])
        ],
    )
    pipeline._voice_loudness(scene, {"audio": {}}, report=True)  # no error, no warning
