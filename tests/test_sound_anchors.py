"""Sound cues timed by the picture (an#317): ``at: {when, reaches}`` and ``until:``.

The corpus lamp is tweened down the frame; a cue anchored to "the lamp reaches
row 220" must resolve to the instant the stage draws it there — computed from
the very document the stage renders, never written back into the scene.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from an.ir.schema import CueAnchor, SoundCue
from an.project import load
from an.sound_anchors import SoundAnchorError
from an.sounds import SYNTH_SOURCE, add_sound, synth_hit

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "misc" / "bench" / "corpus"
#: The lamp's root moves from y=-100 to y=300 over the 0.5 s shot (linear): it
#: crosses frame row 120 + 100 = 220 at 0.25 s (the frame is 240 rows).
TWEEN = {
    "kind": "tween", "target": "lamp", "property": "y",
    "from_value": -100.0, "to_value": 300.0, "duration": 0.5, "easing": "linear",
}  # fmt: skip


def _project(tmp_path: Path, *, shot_sounds=(), meta_sounds=()) -> Path:
    from an.ir.schema import Shot

    root = Path(shutil.copytree(CORPUS / "prop_swap", tmp_path / "p"))
    project = load(root)
    add_sound(project.mall["sounds"], "scratch", synth_hit(seed=1), source=SYNTH_SOURCE)
    add_sound(project.mall["sounds"], "theme", synth_hit(seed=2), source=SYNTH_SOURCE)
    scene = project.scene
    shot = scene.timeline[0]
    shot = Shot.model_validate(
        {
            **shot.model_dump(),
            "actions": [*shot.model_dump()["actions"], TWEEN],
            "sounds": list(shot_sounds),
        }
    )
    project.mall["scenes"]["main"] = scene.model_copy(
        update={
            "timeline": [shot],
            "meta": scene.meta.model_copy(
                update={"sounds": [SoundCue.model_validate(c) for c in meta_sounds]}
            ),
        }
    )
    return root


def _prepared(root: Path, tmp_path: Path):
    from an.render import _prepare_shots

    return _prepare_shots(
        load(root), tmp_path / "work", fps=None, resolution=None, strict_assets=False,
        supersample=1, pix_fmt=None, capture=None, step_hz=None,
    )  # fmt: skip


ANCHOR = {"when": "lamp", "reaches": {"y": 220}}


def test_a_cue_lands_when_the_node_reaches_the_row(tmp_path):
    root = _project(tmp_path, shot_sounds=[{"sound": "scratch", "at": ANCHOR}])
    prep = _prepared(root, tmp_path)
    at = prep.scene.timeline[0].sounds[0].at
    assert at == pytest.approx(0.25, abs=1 / 24)
    (finding,) = prep.sound_findings
    assert finding.severity == "info" and "lamp reached y=220" in finding.description
    # The scene on disk keeps the anchor, never the second.
    assert isinstance(load(root).scene.timeline[0].sounds[0].at, CueAnchor)
    assert "reaches" in (root / "scene.md").read_text(encoding="utf-8")


def test_an_offset_a_film_time_cue_and_until(tmp_path):
    root = _project(
        tmp_path,
        meta_sounds=[
            {"sound": "theme", "at": 0.0, "until": {"cue": "scratch", "offset": 0.05}},
            {"sound": "scratch", "at": {**ANCHOR, "offset": 0.1}},
        ],
    )
    prep = _prepared(root, tmp_path)
    theme, scratch = prep.scene.meta.sounds
    assert scratch.at == pytest.approx(0.35, abs=1 / 24)
    assert theme.duration == pytest.approx(scratch.at + 0.05)


def test_an_anchor_that_cannot_resolve_refuses_before_any_browser(tmp_path):
    never = _project(tmp_path / "a", shot_sounds=[{"sound": "scratch", "at": {"when": "lamp", "reaches": {"y": 9000}}}])
    with pytest.raises(SoundAnchorError, match="never reaches y=9000"):
        _prepared(never, tmp_path / "a")
    nobody = _project(tmp_path / "b", shot_sounds=[{"sound": "scratch", "at": {"when": "ghost", "reaches": {"y": 220}}}])
    with pytest.raises(SoundAnchorError, match="no node 'ghost'"):
        _prepared(nobody, tmp_path / "b")
    with pytest.raises(ValueError, match="one frame axis"):
        CueAnchor(when="lamp", reaches={"y": 1, "x": 2})


def test_validate_accepts_an_anchored_cue(tmp_path):
    from an.ir.validate import validate_semantic

    root = _project(tmp_path, shot_sounds=[{"sound": "scratch", "at": ANCHOR}])
    report = validate_semantic(load(root).scene)
    assert not [f for f in report.findings if "sounds" in f.ir_path and f.severity == "error"]
