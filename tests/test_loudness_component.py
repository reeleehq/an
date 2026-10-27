"""A ``mixing`` too old for the parts ``an`` uses (an#563, an#621).

``mixing`` is a core dependency (an#611), so the one way ``mixing.loudness`` or
``mixing.filtergraph`` can be missing is an older ``mixing``. Both say so the
same way, through :func:`an.audio.shared_mixing.mixing_too_old`: upgrade it.
"""

from __future__ import annotations

import sys

import pytest

from an.audio import effects, loudness


def _too_old(monkeypatch, part: str) -> None:
    """The installed ``mixing`` without ``mixing.<part>``."""
    monkeypatch.setitem(sys.modules, f"mixing.{part}", None)  # import raises
    if "mixing" in sys.modules:  # and the package no longer hands out the module
        monkeypatch.delattr(sys.modules["mixing"], part, raising=False)


def test_leveling_on_a_mixing_too_old_says_upgrade_it(monkeypatch):
    _too_old(monkeypatch, "loudness")
    with pytest.raises(
        loudness.VoiceLoudnessError,
        match=r"leveling voices needs mixing\.loudness, which the installed mixing is too old",
    ):
        loudness.limit_peaks([[2.0]], ceiling=1.0)


def test_a_voice_effect_on_a_mixing_too_old_says_upgrade_it(monkeypatch):
    _too_old(monkeypatch, "filtergraph")
    with pytest.raises(
        effects.VoiceEffectError,
        match=r"voice-effect chain needs mixing\.filtergraph, which the installed mixing is too old",
    ):
        effects.filter_chain({"pitch_semitones": 4.0})
    assert effects.filter_chain({}) == ""  # no chain asked for: mixing not needed


def test_the_render_spread_report_on_a_mixing_too_old_is_loud(monkeypatch):
    """Not skipped as when mixing was optional: the render says what to upgrade."""
    from an.audio import pipeline
    from an.ir.schema import Dialogue, Meta, SceneIR, Shot

    _too_old(monkeypatch, "loudness")
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: "/bin/ffmpeg")
    monkeypatch.setattr(
        loudness, "voiced_lines", lambda scene, mall: {"a": [], "b": []}
    )
    scene = SceneIR(
        meta=Meta(title="t"),
        timeline=[
            Shot(id="s", duration=1.0, dialogue=[Dialogue(speaker="a", text="x")])
        ],
    )
    with pytest.raises(loudness.VoiceLoudnessError, match="pip install -U mixing"):
        pipeline._voice_loudness(scene, {"audio": {}}, report=True)


def test_a_mixing_that_is_absent_or_broken_is_not_called_too_old(monkeypatch):
    """Only a missing PART of mixing is an old mixing; mixing itself absent (an
    install with --no-deps), or a module it imports failing, says what failed."""
    from an.audio.shared_mixing import mixing_too_old

    for failure in (
        ModuleNotFoundError("No module named 'mixing'", name="mixing"),
        ModuleNotFoundError("No module named 'dol'", name="dol"),
    ):
        with pytest.raises(RuntimeError) as caught:
            with mixing_too_old(needed_for="testing", error=RuntimeError):
                raise failure
        assert "too old" not in str(caught.value)
        assert "failed to import" in str(caught.value)
        assert ("pip install mixing" in str(caught.value)) == (failure.name == "mixing")
    with pytest.raises(RuntimeError, match=r"needs mixing\.part, which the installed"):
        with mixing_too_old(needed_for="testing", error=RuntimeError):
            raise ImportError(
                "cannot import name 'part' from 'mixing' (x.py)", name="mixing"
            )


@pytest.mark.parametrize(
    "entry",
    [
        "an.audio.voice_design:design_project_voices",
        "an.audio.voice_design:audition_project_voices",
    ],
)
def test_an_old_mixing_is_said_once_before_anything_is_billed(monkeypatch, tmp_path, entry):
    """an#644: the entry points that may bill warn first, once per process,
    when the installed mixing lacks a part an uses: before the scene is even
    read (a stub that fails on reading it still sees the warning)."""
    import importlib
    import warnings

    from an.audio import shared_mixing

    module, name = entry.split(":")
    call = getattr(importlib.import_module(module), name)
    _too_old(monkeypatch, "filtergraph")

    def refuse(*a, **k):
        raise LookupError("the scene was read")

    for where in ("an.ir.sync", module):
        mod = importlib.import_module(where)
        if hasattr(mod, "resolve_scene_file"):
            monkeypatch.setattr(mod, "resolve_scene_file", refuse)
    shared_mixing.warn_if_mixing_too_old.cache_clear()
    try:
        with pytest.warns(shared_mixing.MixingTooOldWarning, match="too old to have"):
            with pytest.raises(Exception):  # no project here: it fails after the warning
                call(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", shared_mixing.MixingTooOldWarning)
            shared_mixing.warn_if_mixing_too_old()  # said once
    finally:
        shared_mixing.warn_if_mixing_too_old.cache_clear()


def test_the_check_asks_the_code_not_a_version_number(monkeypatch):
    """An editable mixing's metadata keeps the version it was installed at;
    what counts is whether the parts import."""
    import importlib.metadata

    from an.audio.shared_mixing import mixing_problem

    monkeypatch.setattr(importlib.metadata, "version", lambda dist: "0.0.1")
    assert mixing_problem() is None
    _too_old(monkeypatch, "loudness")
    assert "mixing.loudness" in mixing_problem()


def test_a_render_says_an_old_mixing_before_it_makes_anything(monkeypatch, tmp_path):
    """an#644: the render checks inside the warnings its report holds, before
    the film (and its voices) is made."""
    from an import render as render_mod
    from an.audio import shared_mixing
    from an.ir.schema import Shot
    from an.project import init, load

    root = init(tmp_path / "p")
    project = load(root)
    scene = project.scene
    scene.timeline = [Shot(id="s", duration=1.0)]
    project.mall["scenes"]["main"] = scene
    _too_old(monkeypatch, "filtergraph")

    def nothing_made(*a, **k):
        raise LookupError("the film was not made")

    monkeypatch.setattr(render_mod, "_render_film", nothing_made)
    shared_mixing.warn_if_mixing_too_old.cache_clear()
    try:
        with pytest.warns(shared_mixing.MixingTooOldWarning, match="too old to have"):
            with pytest.raises(LookupError):
                render_mod.render_project(root)
    finally:
        shared_mixing.warn_if_mixing_too_old.cache_clear()


def test_a_reroll_says_an_old_mixing_first(monkeypatch):
    """an#644: `an voices reroll` (retake_lines) is billed too."""
    from an.audio import shared_mixing
    from an.audio.pipeline import retake_lines
    from an.ir.schema import Meta, SceneIR

    _too_old(monkeypatch, "filtergraph")
    shared_mixing.warn_if_mixing_too_old.cache_clear()
    try:
        with pytest.warns(shared_mixing.MixingTooOldWarning, match="too old to have"):
            assert retake_lines(SceneIR(meta=Meta(title="t")), {}, "x", tts=object()) == []
    finally:
        shared_mixing.warn_if_mixing_too_old.cache_clear()
