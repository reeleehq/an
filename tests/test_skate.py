"""The ``skate`` check (an#519 PR 2, catalogue B3 i): a held foot does not slide along its surface.

The fixture is ``tests/_hold_fixture.py`` plus, written here, a ``walker``: the
fixture's figure whose legs name their far ends as contacts
(``metadata.contacts: {foot_l: {slot: leg_l}, foot_r: {slot: leg_r}}``), so its
feet are a limb's contacts that can skate, where the figure's own ``origin``
cannot; and the ``cup`` of ``tests/test_support.py``, whose ``base`` is on its
root drawing (a pushed prop slides on it by right). Skate is measured in the
surface's frame: a walker standing on a crate that moves with it does not
skate. Compiled only, never rendered.
"""

from __future__ import annotations

import copy
import json
import warnings
from pathlib import Path

import pytest

from tests._hold_fixture import CRATE_SURFACE, FIGURE, K, make_project, scene
from tests.test_support import CUP_UNITS, _prop, _svg

from an.ir.validate import validate_semantic
from an.project import load
from an.stage.compile import compile_shot
from an.stage.support import (
    SKATE_FLOOR_PX,
    SKATE_TOLERANCE,
    skate_tolerance,
    supports_at,
)
from an.verify.support import SKATE, SUPPORT_CONSTRAINTS

W, H = 640, 480
GROUND = 200.0
#: One frame at the fixture's 24 fps.
FRAME = 1 / 24

WALKER = copy.deepcopy(FIGURE) | {
    "name": "walker",
    "metadata": {
        "contacts": {"foot_l": {"slot": "leg_l"}, "foot_r": {"slot": "leg_r"}}
    },
}
CUP = _prop(
    "cup",
    w=CUP_UNITS,
    h=CUP_UNITS,
    origin=False,
    metadata={"contacts": {"base": [0.5, 1.0]}},
)


def _project(tmp_path: Path, *, entities: str, shot: str, actions: str = "[]"):
    root = tmp_path / "p"
    make_project(root, scene(actions, entities=entities, shot=shot, duration=2.0))
    props = root / "assets" / "props"
    walker = props / "walker"
    (walker / "parts").mkdir(parents=True, exist_ok=True)
    (walker / "prop.json").write_text(json.dumps(WALKER), encoding="utf-8")
    for part in ("leg", "torso", "head", "arm"):
        src = props / "figure" / "parts" / f"{part}.svg"
        (walker / "parts" / f"{part}.svg").write_text(src.read_text(), encoding="utf-8")
    cup = props / "cup"
    (cup / "parts").mkdir(parents=True, exist_ok=True)
    (cup / "prop.json").write_text(json.dumps(CUP), encoding="utf-8")
    (cup / "parts" / "body.svg").write_text(
        _svg(CUP_UNITS, CUP_UNITS), encoding="utf-8"
    )
    return load(root)


def _entity(eid: str, ref: str, x: float, y: float, extra: str = "") -> str:
    return f"- {{kind: prop, id: {eid}, store: props, ref: {ref}, stage: {{at: [{x}, {y}]}}{extra}}}\n"


def _shot(joints: str = "", *, ground: float | None = GROUND) -> str:
    out = "duration: 2.0"
    if ground is not None:
        out += f"\nsolve: {{ground: {ground:g}}}"
    if joints:
        out += f"\njoints: {joints}"
    return out


def _slide(target: str, *, start: float, by: float, frames: float, origin: float):
    """A linear ``x`` tween of ``target`` from ``origin`` by ``by`` px over ``frames`` frames."""
    return (
        f"- {{kind: tween, target: {target}, property: x, from: {origin:g}, "
        f"to: {origin + by:g}, duration: {frames * FRAME:.6f}, start: {start:g}, easing: linear}}"
    )


def _lint(project, *, gravity: bool | None = None, only=("skate",)):
    """The skate findings; ``gravity``: under a style pack declaring it (True)
    or not (False), or with no pack (None)."""
    scene_ir, styles = project.scene, None
    if gravity is not None:
        meta = scene_ir.meta.model_copy(update={"style_pack": "house"})
        scene_ir = scene_ir.model_copy(update={"meta": meta})
        pack = {"name": "house"} | ({"gravity": {}} if gravity else {})
        styles = {"house": pack}
    report = validate_semantic(
        scene_ir,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        available_styles=styles,
        only=set(only),
    )
    return [(f.severity, f.ir_path, f.description) for f in report.findings]


def _compile(project):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(
            project.scene.timeline[0], project.mall, fps=24, width=W, height=H
        )


LEFT = "[{type: support, a: wal@foot_l, b: ground, name: left}]"


def test_skate_is_a_lint_after_the_support_check():
    assert SKATE in SUPPORT_CONSTRAINTS
    assert (SKATE.order, SKATE.term) == (253.0, None)
    assert skate_tolerance(200.0) == pytest.approx(SKATE_TOLERANCE * 200.0)
    assert skate_tolerance(20.0) == SKATE_FLOOR_PX


def test_a_foot_that_slides_while_joined_is_an_error(tmp_path):
    # 10 px in one frame, its foot on the floor throughout
    project = _project(
        tmp_path,
        entities=_entity("wal", "walker", -100, GROUND),
        shot=_shot(LEFT),
        actions=_slide("wal", start=1.0, by=10.0, frames=1, origin=-100),
    )
    [(severity, where, message)] = _lint(project)
    assert (severity, where) == ("error", "timeline/0/joints/0")
    assert message.startswith(
        "`wal`'s `foot_l` slides 10.0 px per frame along `ground`"
    )
    assert "from 1.00 s to 1.04 s" in message
    assert "`unjoin` the support `left`" in message
    # the support itself holds: the foot never leaves the floor
    assert _lint(project, only=("support",)) == []
    # measured where the support check measures: held, the drift in the floor's frame
    states, problems = supports_at(
        _compile(project), project.scene.timeline[0], project.mall
    )
    assert problems == []
    speeds = [c.tangent_speed for s in states for c in s.contacts if c.tangent_speed]
    assert max(speeds) == pytest.approx(10.0, abs=0.05)
    assert all(c.held and c.limb for s in states for c in s.contacts)


def test_the_same_slide_while_unjoined_is_not(tmp_path):
    verbs = (
        "\n- {kind: unjoin, joint: left, at: 0.9}\n- {kind: join, joint: left, at: 1.2}"
    )
    project = _project(
        tmp_path,
        entities=_entity("wal", "walker", -100, GROUND),
        shot=_shot(LEFT),
        actions=_slide("wal", start=1.0, by=10.0, frames=1, origin=-100) + verbs,
    )
    assert _lint(project) == []


def test_a_slow_drift_is_within_the_tolerance(tmp_path):
    # 0.5 px per frame on a figure about 290 px tall (tolerance about 1.5 px)
    project = _project(
        tmp_path,
        entities=_entity("wal", "walker", -100, GROUND),
        shot=_shot(LEFT),
        actions=_slide("wal", start=0.0, by=12.0, frames=24, origin=-100),
    )
    assert _lint(project) == []


def test_standing_on_a_crate_that_moves_with_it_is_not_skate(tmp_path):
    # the crate and the walker on it are carried 30 px in 12 frames together:
    # 2.5 px per frame on the stage, nothing in the crate's frame
    surface_y = GROUND - CRATE_SURFACE * K
    entities = _entity("crate", "crate", 160, GROUND) + _entity(
        "wal", "walker", 160, surface_y
    )
    joints = "[{type: support, a: wal@foot_l, b: crate@surface, name: left}]"
    carried = _slide("crate", start=0.5, by=30.0, frames=12, origin=160)
    project = _project(
        tmp_path / "a",
        entities=entities,
        shot=_shot(joints),
        actions=carried
        + "\n"
        + _slide("wal", start=0.5, by=30.0, frames=12, origin=160),
    )
    assert _lint(project, only=("support", "skate")) == []
    # the crate pushed out from under a walker that stays put: its foot slides on it
    pushed = _project(
        tmp_path / "b", entities=entities, shot=_shot(joints), actions=carried
    )
    [(severity, _where, message)] = _lint(pushed)
    assert severity == "error"
    assert "slides 2.5 px per frame along `crate@surface`" in message


def test_a_pushed_props_base_does_not_skate(tmp_path):
    # a prop's base is its own stance point: a pushed cup slides on it by right
    for a in ("cup@base", "cup"):
        project = _project(
            tmp_path / a.replace("@", "_"),
            entities=_entity("cup", "cup", 0, GROUND),
            shot=_shot(f"[{{type: support, a: {a}, b: ground}}]"),
            actions=_slide("cup", start=0.5, by=40.0, frames=4, origin=0),
        )
        assert _lint(project) == []


def test_a_figure_gliding_on_its_origin_does_not_skate(tmp_path):
    project = _project(
        tmp_path,
        entities=_entity("fig", "figure", -100, GROUND),
        shot=_shot("[{type: support, a: fig, b: ground}]"),
        actions=_slide("fig", start=0.5, by=40.0, frames=4, origin=-100),
    )
    assert _lint(project) == []


def test_inferred_skate_warns_only_under_a_pack_with_gravity(tmp_path):
    # nothing declares a support: the walker is taken to stand on the floor
    project = _project(
        tmp_path,
        entities=_entity("wal", "walker", -100, GROUND),
        shot=_shot(),
        actions=_slide("wal", start=0.5, by=40.0, frames=4, origin=-100),
    )
    found = _lint(project, gravity=True)
    assert {f[0] for f in found} == {"warning"}
    assert {f[1] for f in found} == {"timeline/0/entities/0"}
    assert {m.split("`")[3] for _s, _w, m in found} == {"foot_l", "foot_r"}
    assert "stands on it as the shot opens" in found[0][2]
    assert _lint(project, gravity=False) == []
    assert _lint(project) == []


def test_a_slide_within_a_flight_is_not_judged(tmp_path):
    project = _project(
        tmp_path,
        entities=_entity(
            "wal",
            "walker",
            -100,
            GROUND,
            ", overrides: {airborne: {from: 0.9, until: 1.2}}",
        ),
        shot=_shot(LEFT),
        actions=_slide("wal", start=1.0, by=10.0, frames=1, origin=-100),
    )
    assert _lint(project) == []


def test_the_core_corpus_has_no_skate(tmp_path):
    # no core scene declares a support or a pack with gravity: the check is
    # silent, and it compiles nothing of its own (lint-only, `term=None`)
    from an.bench.core_corpus import CORE_FIXTURES, stage_copy

    repo = Path(__file__).resolve().parents[1]
    for name, fixture in sorted(CORE_FIXTURES.items()):
        work = stage_copy(repo / fixture.path, tmp_path / name)
        if fixture.prepare is not None:
            fixture.prepare(work)
        project = load(work)
        report = validate_semantic(
            project.scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
            available_styles=project.mall["styles"],
            only={"skate"},
        )
        assert report.findings == [], (name, report.findings)
