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


# -- an authored change (an#815): a sound on the frame a prop's state is set ------

#: The corpus shot sets the lamp's ``lamp`` swap channel to ``on`` at 0.25 s.
CHANGE = {"when": "lamp/body", "changes": "lamp", "to": "on"}


def test_a_cue_lands_on_the_set_that_changes_the_state(tmp_path):
    root = _project(tmp_path, shot_sounds=[{"sound": "scratch", "at": {**CHANGE, "offset": 0.05}}])
    prep = _prepared(root, tmp_path)
    assert prep.scene.timeline[0].sounds[0].at == pytest.approx(0.30)
    (finding,) = prep.sound_findings
    assert "lamp/body lamp to on" in finding.description
    # The scene keeps the anchor: retiming the set moves the sound with it.
    assert isinstance(load(root).scene.timeline[0].sounds[0].at, CueAnchor)
    scene_md = root / "scene.md"
    scene_md.write_text(
        scene_md.read_text(encoding="utf-8").replace("at: 0.25", "at: 0.4", 1),
        encoding="utf-8",
    )
    assert _prepared(root, tmp_path / "again").scene.timeline[0].sounds[0].at == pytest.approx(0.45)


def test_a_change_anchor_counts_sets_and_tweens_in_time_order(tmp_path):
    from an.ir.schema import Shot
    from an.sound_anchors import change_in_shot

    shot = Shot.model_validate(
        {
            "id": "s",
            "duration": 4.0,
            "actions": [
                {"kind": "set", "target": "book/body", "property": "state", "value": "page_r", "at": 3.0},
                {"kind": "sequence", "children": [
                    {"kind": "delay", "duration": 1.0},
                    {"kind": "set", "target": "book/body", "property": "state", "value": "page_l"},
                ]},
                {"kind": "tween", "target": "book", "property": "y", "to_value": 10.0, "start": 0.5},
            ],
        }
    )  # fmt: skip
    anchor = CueAnchor.model_validate
    assert change_in_shot(shot, anchor({"when": "book/body", "changes": "state"}), where="w") == 1.0
    assert change_in_shot(shot, anchor({"when": "book/body", "changes": "state", "nth": 2}), where="w") == 3.0
    assert change_in_shot(shot, anchor({"when": "book/body", "changes": "state", "to": "page_r"}), where="w") == 3.0
    with pytest.raises(SoundAnchorError, match=r"'page_l' at 1.00 s, 'page_r' at 3.00 s"):
        change_in_shot(shot, anchor({"when": "book/body", "changes": "state", "to": "cover"}), where="w")
    with pytest.raises(SoundAnchorError, match=r"nodes whose 'state' it changes: \['book/body'\]"):
        change_in_shot(shot, anchor({"when": "book", "changes": "state"}), where="w")


def test_a_change_anchor_is_one_form_and_round_trips():
    with pytest.raises(ValueError, match="not `event` and `changes`"):
        CueAnchor(when="lamp", event="land", changes="state")
    with pytest.raises(ValueError, match="has no `changes:`"):
        CueAnchor(when="lamp", event="land", to="on")
    a = CueAnchor(when="book/body", changes="state", to="page_l", nth=2)
    assert a.model_dump() == {"when": "book/body", "changes": "state", "to": "page_l", "nth": 2, "offset": 0.0, "shot": None}
    assert CueAnchor.model_validate(a.model_dump()) == a
    # an anchor without the new fields stores as it did before
    assert "changes" not in CueAnchor(when="m", event="land").model_dump()


def test_validate_names_a_cued_change_the_shot_does_not_have(tmp_path):
    from an.ir.validate import validate_semantic

    def cue_event(anchor):
        root = _project(tmp_path / str(len(list(tmp_path.iterdir()))), shot_sounds=[{"sound": "scratch", "at": anchor}])
        project = load(root)
        report = validate_semantic(
            project.scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
            only={"cue_event"},
        )
        return [(f.severity, f.description) for f in report.findings]

    ((severity, text),) = cue_event(CHANGE)
    assert severity == "info" and "0.25 s" in text
    ((severity, text),) = cue_event({**CHANGE, "to": "off"})
    assert severity == "error" and "'on' at 0.25 s" in text


def test_an_unquoted_on_in_scene_md_is_the_state_named_on(tmp_path):
    """Review of an#815: YAML reads ``to: on`` as ``True``; the set it means
    stores ``value: 'on'``. The two match (and a boolean never matches a 1)."""
    from an.sound_anchors import _same_value

    root = _project(tmp_path, shot_sounds=[{"sound": "scratch", "at": CHANGE}])
    scene_md = root / "scene.md"
    text = scene_md.read_text(encoding="utf-8")
    assert "to: 'on'" in text
    scene_md.write_text(text.replace("to: 'on'", "to: on"), encoding="utf-8")
    assert load(root).scene.timeline[0].sounds[0].at.to is True
    assert _prepared(root, tmp_path).scene.timeline[0].sounds[0].at == pytest.approx(0.25)
    assert not _same_value(1, True) and not _same_value("on", False)


def test_a_film_cue_timed_by_a_change_looks_in_the_shot_that_has_it(tmp_path):
    """A ``meta.sounds`` change anchor with no ``shot:`` is the first shot
    whose actions have the change, not merely the first that casts the node."""
    from an.ir.schema import SceneIR, SoundCue
    from an.sound_anchors import _shot_with

    root = _project(tmp_path)
    scene = load(root).scene
    shot = scene.timeline[0]
    bare = shot.model_copy(update={"id": "before", "actions": []})
    two = scene.model_copy(update={"timeline": [bare, shot]})
    anchor = SoundCue.model_validate({"sound": "scratch", "at": CHANGE}).at
    assert _shot_with(two, anchor, [], None) == 1
