"""The ``Constraint`` interface and the core's ``continuity`` lint (an#508, an#497):
registration, the interface example, the within-shot jump and short-hold cases,
a loop seam, and the core corpus staying clean."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from an.bench.core_corpus import CORE_FIXTURES, stage_copy
from an.genres.registry import CORE_OWNER, check_names
from an.ir.schema import Shot
from an.ir.validate import validate_semantic
from an.project import load
from an.verify import constraints
from an.verify.constraints import Constraint, discontinuities

ROOT = Path(__file__).resolve().parents[1]
LAMP = ROOT / "misc" / "bench" / "corpus" / "prop_swap"
ONLY = {"continuity", "solidity", "draw_order"}


def _lint(tmp_path: Path, actions, *, duration=2.0, extra=None):
    root = Path(shutil.copytree(LAMP, tmp_path / "p"))
    project = load(root)
    first = project.scene.timeline[0]
    shot = Shot.model_validate(
        {
            **first.model_dump(),
            "duration": duration,
            "actions": list(actions),
            **(extra or {}),
        }
    )
    scene = project.scene.model_copy(update={"timeline": [shot]})
    return validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only=ONLY,
    )


def _msgs(report) -> list[str]:
    return [f.description for f in report.findings]


def _tween(**kw):
    return {"kind": "tween", "target": "lamp", "property": "x", "to_value": 50.0, **kw}


def test_continuity_is_registered_under_the_core_owner():
    assert "continuity" in check_names(owner=CORE_OWNER)


def _later(action, delay=0.5):
    """``action`` starting ``delay`` s into the shot (top-level actions all start at 0)."""
    return {
        "kind": "sequence",
        "children": [{"kind": "delay", "duration": delay}, action],
    }


def test_the_interface_example_builds_a_check():
    c = Constraint("demo", lambda ctx: None, term=lambda state: 0.0, description="demo")
    check = c.semantic_check()
    assert (check.name, check.stage) == ("demo", "shot")
    assert c.term is not None
    assert Constraint("lint_only", lambda ctx: None).term is None


def test_a_plain_tween_is_continuous(tmp_path):
    assert _msgs(_lint(tmp_path, [_tween(duration=1.0)])) == []


def test_a_from_the_node_is_not_at_is_one_warning(tmp_path):
    msgs = _msgs(_lint(tmp_path, [_later(_tween(from_value=500.0, duration=1.0))]))
    assert len(msgs) == 1 and "jumps" in msgs[0]


def test_a_set_at_that_instant_makes_it_deliberate(tmp_path):
    set_x = {
        "kind": "set",
        "target": "lamp",
        "property": "x",
        "value": 500.0,
        "at": 0.5,
    }
    assert (
        _msgs(_lint(tmp_path, [set_x, _later(_tween(from_value=500.0, duration=1.0))]))
        == []
    )


def test_a_tween_ending_over_a_longer_one_shows_it_through(tmp_path):
    actions = [
        _tween(duration=1.5, to_value=50.0),
        _later(_tween(duration=0.5, to_value=-80.0)),
    ]
    msgs = _msgs(_lint(tmp_path, actions))
    assert len(msgs) == 1 and "shows through" in msgs[0]


def test_two_sets_ten_milliseconds_apart_are_a_short_hold(tmp_path):
    sets = [
        {"kind": "set", "target": "lamp", "property": "x", "value": v, "at": at}
        for v, at in ((10.0, 0.5), (20.0, 0.51))
    ]
    msgs = _msgs(_lint(tmp_path, sets))
    assert len(msgs) == 1 and "frame" in msgs[0]


def test_stepped_tweens_say_nothing(tmp_path):
    assert _msgs(_lint(tmp_path, [_tween(duration=1.0)], extra={"step_hz": 8.0})) == []


def test_a_loop_seam_is_a_discontinuity_unless_the_pose_closes():
    from an.timing.channel import Channel, Keyframe
    from an.timing.clip import Clip, LoopMode
    from an.timing.timeline import PlacedClip, Timeline, Track

    def run(end: float):
        keys = [Keyframe(0.0, 0.0, "linear"), Keyframe(1.0, end)]
        clip = Clip("wave", 1.0, [Channel("a", "x", keys)], loop_mode=LoopMode.LOOP)
        tl = Timeline(
            3.0, [Track("a", [PlacedClip(clip, start_time=0.0, duration=3.0)])]
        )
        return [
            d
            for d in discontinuities(tl, rest={("a", "x"): 0.0}, duration=3.0)
            if not d.deliberate
        ]

    assert run(0.0) == []
    assert run(40.0)


def test_a_shot_that_fails_to_compile_adds_nothing(tmp_path):
    report = _lint(tmp_path, [_tween(target="nobody")])
    assert [m for m in _msgs(report) if "jump" in m or "frame" in m] == []


@pytest.mark.parametrize("name", sorted(CORE_FIXTURES))
def test_the_core_corpus_reports_no_continuity_finding(name, tmp_path):
    project = load(
        stage_copy(ROOT / CORE_FIXTURES[name].path, tmp_path / name), check_kinds=False
    )
    report = validate_semantic(
        project.scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only=ONLY,
    )
    assert _msgs(report) == []


# -- solidity (an#509) ------------------------------------------------------


def _two_lamps(tmp_path: Path, *, second: dict | None = None, at=(0.0, 90.0)):
    root = Path(shutil.copytree(LAMP, tmp_path / "p"))
    project = load(root)
    first = project.scene.timeline[0]
    lamp = first.entities[0].model_dump()
    twin = {
        **lamp,
        "id": "twin",
        "stage": {"at": list(at), "scale": 0.55},
        **(second or {}),
    }
    shot = Shot.model_validate({**first.model_dump(), "entities": [lamp, twin]})
    scene = project.scene.model_copy(update={"timeline": [shot]})
    return validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only={"solidity"},
    )


def test_solidity_is_registered_under_the_core_owner():
    assert "solidity" in check_names(owner=CORE_OWNER)


def test_two_overlapping_props_are_one_warning_naming_both(tmp_path):
    (msg,) = _msgs(_two_lamps(tmp_path))
    assert "'lamp'" in msg and "'twin'" in msg and "stage.after" in msg


def test_props_far_apart_say_nothing(tmp_path):
    assert _msgs(_two_lamps(tmp_path, at=(900.0, 90.0))) == []


def test_an_after_on_either_makes_the_overlap_occlusion(tmp_path):
    stage = {"at": [0.0, 90.0], "scale": 0.55, "after": "lamp"}
    assert _msgs(_two_lamps(tmp_path, second={"stage": stage})) == []


def test_a_solid_false_override_opts_out(tmp_path):
    assert _msgs(_two_lamps(tmp_path, second={"overrides": {"solid": False}})) == []


# -- draw order (an#510) ----------------------------------------------------


def _two_shot_order(tmp_path: Path, *, swapped_after: str | None = None):
    root = Path(shutil.copytree(LAMP, tmp_path / "p"))
    project = load(root)
    first = project.scene.timeline[0].model_dump()
    lamp = first["entities"][0]
    twin = {**lamp, "id": "twin", "stage": {"at": [300.0, 90.0], "scale": 0.55}}
    if swapped_after:
        lamp = {**lamp, "stage": {**(lamp.get("stage") or {}), "after": swapped_after}}
    one = Shot.model_validate({**first, "id": "one", "entities": [lamp, twin]})
    two = Shot.model_validate({**first, "id": "two", "entities": [twin, lamp]})
    scene = project.scene.model_copy(update={"timeline": [one, two]})
    return validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only={"draw_order"},
    )


def test_draw_order_is_registered_at_finish():
    assert "draw_order" in check_names(owner=CORE_OWNER)


def test_the_same_two_painted_in_the_other_order_is_one_warning_naming_both_shots(tmp_path):
    (msg,) = _msgs(_two_shot_order(tmp_path))
    assert "'lamp'" in msg and "'twin'" in msg and "'one'" in msg and "'two'" in msg


def test_a_changed_after_makes_the_flip_deliberate(tmp_path):
    assert _msgs(_two_shot_order(tmp_path, swapped_after="twin")) == []
