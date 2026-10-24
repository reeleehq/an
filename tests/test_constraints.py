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
ONLY = {
    "continuity",
    "solidity",
    "draw_order",
    "jump_cut",
    "object_permanence",
    "held_item",
    "rigidity",
}


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


def test_the_same_two_painted_in_the_other_order_is_one_warning_naming_both_shots(
    tmp_path,
):
    (msg,) = _msgs(_two_shot_order(tmp_path))
    assert "'lamp'" in msg and "'twin'" in msg and "'one'" in msg and "'two'" in msg


def test_a_changed_after_makes_the_flip_deliberate(tmp_path):
    assert _msgs(_two_shot_order(tmp_path, swapped_after="twin")) == []


# -- jump cut, the 30-degree rule (catalogue C4) ------------------------------


def _jump_cut_report(tmp_path: Path, first: dict, second: dict):
    from an.ir.schema import Meta, Resolution, SceneIR, Viewpoint, World, WorldMember

    project = load(Path(shutil.copytree(LAMP, tmp_path / "p")))
    world = World(
        members=[
            WorldMember(
                kind="prop",
                id="lamp",
                store="props",
                ref="lamp",
                at=(0.0, 0.4, 4.0),
                height=0.8,
            )
        ],
        viewpoints={
            "a": Viewpoint(subject="lamp", focal=300.0, **first),
            "b": Viewpoint(subject="lamp", focal=300.0, **second),
        },
    )
    shots = [
        Shot(id=n, renderer="cutout", duration=1.0, viewpoint=n) for n in ("a", "b")
    ]
    scene = SceneIR(
        meta=Meta(fps=24, resolution=Resolution(width=320, height=240)),
        world=world,
        timeline=shots,
    )
    return validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only={"jump_cut"},
    )


def test_the_same_framing_twice_is_a_jump_cut(tmp_path):
    (msg,) = _msgs(_jump_cut_report(tmp_path, {"size": "medium"}, {"size": "medium"}))
    assert "'a'" in msg and "'b'" in msg and "jump cut" in msg


def test_a_change_of_shot_size_is_not_a_jump_cut(tmp_path):
    assert (
        _msgs(_jump_cut_report(tmp_path, {"size": "medium"}, {"size": "close_up"}))
        == []
    )


def test_a_turn_of_thirty_degrees_is_not_a_jump_cut(tmp_path):
    assert (
        _msgs(
            _jump_cut_report(
                tmp_path,
                {"size": "medium"},
                {"size": "medium", "look": (45.0, 0.0, 0.0)},
            )
        )
        == []
    )


# -- object permanence (catalogue C1) -----------------------------------------


def _permanence(tmp_path: Path, present, *, jump_at=None, opens_with=None):
    """The lamp shot repeated; ``present[i]`` says whether shot ``i`` shows it."""
    project = load(Path(shutil.copytree(LAMP, tmp_path / "p")))
    first = project.scene.timeline[0]
    shots = []
    for i, shown in enumerate(present):
        data = {**first.model_dump(), "id": f"s{i}", "actions": []}
        data["entities"] = first.model_dump()["entities"] if shown else []
        if i == jump_at:
            data["transition"] = {"kind": "cut", "time_jump": True}
        if i == opens_with:
            data["actions"] = [_tween(start=0.0)]
        shots.append(Shot.model_validate(data))
    scene = project.scene.model_copy(update={"timeline": shots})
    return validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only={"object_permanence"},
    )


def test_object_permanence_is_registered_at_finish():
    assert "object_permanence" in check_names(owner=CORE_OWNER)


def test_an_entity_that_vanishes_and_returns_is_one_warning(tmp_path):
    (msg,) = _msgs(_permanence(tmp_path, [True, False, True]))
    assert "'s0'" in msg and "'s2'" in msg and "time_jump" in msg


def test_a_time_jump_explains_the_return(tmp_path):
    assert _msgs(_permanence(tmp_path, [True, False, True], jump_at=2)) == []


def test_an_entrance_explains_the_return(tmp_path):
    assert _msgs(_permanence(tmp_path, [True, False, True], opens_with=2)) == []


def test_an_entity_in_every_shot_is_fine(tmp_path):
    assert _msgs(_permanence(tmp_path, [True, True, True])) == []


def test_an_entity_drawn_twice_in_a_shot_is_an_error(tmp_path):
    project = load(Path(shutil.copytree(LAMP, tmp_path / "p")))
    first = project.scene.timeline[0].model_dump()
    first["entities"] = first["entities"] * 2
    scene = project.scene.model_copy(update={"timeline": [Shot.model_validate(first)]})
    report = validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only={"object_permanence"},
    )
    (f,) = report.findings
    assert f.severity == "error" and "2 times" in f.description


# -- held item, the weld (catalogue A4) ---------------------------------------


def _held(tmp_path: Path, weld: dict, *, carrier_moves=True, item_moves=True):
    """``twin`` (the item) and ``lamp`` (the carrier), each tweened across 1 s."""
    project = load(Path(shutil.copytree(LAMP, tmp_path / "p")))
    first = project.scene.timeline[0].model_dump()
    lamp = first["entities"][0]
    twin = {**lamp, "id": "twin", "stage": {"at": [300.0, 90.0], "scale": 0.55}}
    actions = []
    for target, moves, start in (
        ("lamp", carrier_moves, 0.0),
        ("twin", item_moves, 300.0),
    ):
        if moves:  # both travel 100 px, so the offset between them is kept
            actions.append(
                {
                    **_tween(duration=1.0, from_value=start, to_value=start + 100.0),
                    "target": target,
                }
            )
    shot = Shot.model_validate(
        {
            **first,
            "duration": 1.0,
            "entities": [lamp, twin],
            "actions": actions,
            "welds": [weld],
        }
    )
    scene = project.scene.model_copy(update={"timeline": [shot]})
    return validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only={"held_item"},
    )


def test_held_item_is_registered_under_the_core_owner():
    assert "held_item" in check_names(owner=CORE_OWNER)


def test_an_item_that_stays_when_its_carrier_moves_is_one_warning(tmp_path):
    (msg,) = _msgs(_held(tmp_path, {"item": "twin", "by": "lamp"}, item_moves=False))
    assert "'twin'" in msg and "'lamp'" in msg and "not held" in msg


def test_an_item_that_moves_with_its_carrier_is_held(tmp_path):
    report = _held(tmp_path, {"item": "twin", "by": "lamp"})
    assert _msgs(report) == []


def test_releasing_before_the_carrier_moves_ends_the_check(tmp_path):
    weld = {"item": "twin", "by": "lamp", "until": 0.01}
    assert _msgs(_held(tmp_path, weld, item_moves=False)) == []


def test_a_weld_to_an_entity_not_in_the_shot_is_an_error(tmp_path):
    (f,) = _held(tmp_path, {"item": "cup", "by": "lamp"}).findings
    assert f.severity == "error" and "'cup'" in f.description


def test_weld_drifts_is_pure():
    from an.verify.constraints import weld_drifts

    assert weld_drifts([(0.0, (0, 0), (5, 0)), (1.0, (9, 0), (14, 0))]) == []


# -- rigidity and volume (catalogue A5) ---------------------------------------


def _lamp_with(tmp_path: Path, overrides: dict):
    first = load(Path(shutil.copytree(LAMP, tmp_path / "q"))).scene.timeline[0]
    (lamp,) = first.model_dump()["entities"][:1]
    return [{**lamp, "overrides": {**(lamp.get("overrides") or {}), **overrides}}]


def _scaled(tmp_path: Path, overrides: dict, **scales):
    """The lamp tweened in ``scale_x`` / ``scale_y`` to the given values over 1 s."""
    actions = [
        _tween(property=p, to_value=v, from_value=1.0, duration=1.0)
        for p, v in scales.items()
    ]
    return _lint(
        tmp_path,
        actions,
        duration=1.0,
        extra={"entities": _lamp_with(tmp_path, overrides)},
    )


def test_rigidity_is_registered_under_the_core_owner():
    assert "rigidity" in check_names(owner=CORE_OWNER)


def test_a_rigid_entity_stretched_one_way_is_one_warning(tmp_path):
    report = _scaled(tmp_path, {"rigid": True}, scale_x=1.5)
    (msg,) = [m for m in _msgs(report) if "proportions" in m]
    assert "'lamp'" in msg and "rigid" in msg


def test_a_rigid_entity_scaled_together_is_fine(tmp_path):
    report = _scaled(tmp_path, {"rigid": True}, scale_x=1.5, scale_y=1.5)
    assert [m for m in _msgs(report) if "proportions" in m] == []


def test_squash_with_the_area_kept_passes_the_volume_check(tmp_path):
    report = _scaled(tmp_path, {"preserve_volume": True}, scale_x=1.25, scale_y=0.8)
    assert [m for m in _msgs(report) if "volume" in m] == []


def test_a_stretch_that_grows_the_area_breaks_the_volume_check(tmp_path):
    report = _scaled(tmp_path, {"preserve_volume": True}, scale_x=1.5)
    assert [m for m in _msgs(report) if "volume" in m]


def test_nothing_declared_nothing_said(tmp_path):
    report = _scaled(tmp_path, {}, scale_x=1.5)
    assert [m for m in _msgs(report) if "proportions" in m] == []
