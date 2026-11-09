"""The ``skate`` check (an#519 PR 2, catalogue B3 i): a held foot does not slide along its surface.

The fixture is ``tests/_hold_fixture.py`` plus, written here, a ``walker``: the
fixture's figure with its legs hinged to its torso (not roots of its rig) and
naming their far ends as contacts (``metadata.contacts: {foot_l: {slot:
leg_l}, foot_r: {slot: leg_r}}``), so its feet are a limb's contacts that can
skate, where the figure's own ``origin`` cannot; and the ``cup`` of ``tests/test_support.py``, whose ``base`` is on its
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
    SKATE_DRIFT_FLOOR_PX,
    SKATE_DRIFT_TOLERANCE,
    SKATE_FLOOR_PX,
    SKATE_TOLERANCE,
    skate_drift_tolerance,
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
        (walker / "parts" / f"{part}.svg").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
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


def _lint(
    project,
    *,
    gravity: bool | None = None,
    only=("skate",),
    fps: float | None = None,
    step_hz: float | None = None,
    scene_ir=None,
):
    """The skate findings; ``gravity``: under a style pack declaring it (True)
    or not (False), or with no pack (None); ``fps``/``step_hz`` replace the
    scene's; ``scene_ir`` replaces the project's scene."""
    scene_ir, styles = scene_ir or project.scene, None
    timing = {k: v for k, v in (("fps", fps), ("step_hz", step_hz)) if v is not None}
    if timing:
        meta = scene_ir.meta.model_copy(update=timing)
        scene_ir = scene_ir.model_copy(update={"meta": meta})
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


def _tween(target: str, prop: str, *, a: float, b: float, start: float, secs: float):
    """A linear tween of ``target:prop`` from ``a`` to ``b`` over ``secs`` s from ``start``."""
    return (
        f"- {{kind: tween, target: {target}, property: {prop}, from: {a:g}, to: {b:g}, "
        f"duration: {secs:.6f}, start: {start:.6f}, easing: linear}}"
    )


def _walker_sliding(tmp_path: Path, *, by: float, secs: float, start: float = 0.0):
    return _project(
        tmp_path,
        entities=_entity("wal", "walker", -100, GROUND),
        shot=_shot(LEFT),
        actions=_tween("wal", "x", a=-100, b=-100 + by, start=start, secs=secs),
    )


def test_skate_is_a_lint_after_the_support_check():
    assert SKATE in SUPPORT_CONSTRAINTS
    assert (SKATE.order, SKATE.term) == (253.0, None)
    # a speed (a fraction of the height per second) and a drift, each floored
    assert skate_tolerance(200.0) == pytest.approx(SKATE_TOLERANCE * 200.0)
    assert skate_tolerance(20.0) == SKATE_FLOOR_PX
    assert skate_drift_tolerance(200.0) == pytest.approx(SKATE_DRIFT_TOLERANCE * 200.0)
    assert skate_drift_tolerance(20.0) == SKATE_DRIFT_FLOOR_PX


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
        "`wal`'s `foot_l` slides 10.0 px per frame (240 px/s) along `ground`"
    )
    assert "from 1.00 s to 1.04 s" in message
    assert "`unjoin` the support `left`" in message
    # the support itself holds: the foot never leaves the floor
    assert _lint(project, only=("support",)) == []
    # measured where the support check measures: the slide in the floor's frame
    states, problems = supports_at(
        _compile(project), project.scene.timeline[0], project.mall
    )
    assert problems == []
    slid = [c.slid for s in states for c in s.contacts if c.slid]
    assert max(slid) == pytest.approx(10.0, abs=0.05)
    assert all(c.limb for s in states for c in s.contacts)


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


def test_a_slow_short_drift_is_within_the_tolerance(tmp_path):
    # 6 px over a second on a figure about 290 px tall: under the speed
    # tolerance (about 35 px/s) and under the drift (about 8.7 px)
    project = _walker_sliding(tmp_path, by=6.0, secs=1.0)
    assert _lint(project) == []


def test_one_slide_speed_gets_one_verdict_at_any_frame_rate(tmp_path):
    # 60 px/s: 2.5 px a frame at 24 fps, 1 px a frame at 60 (both over ~35 px/s)
    fast = _walker_sliding(tmp_path / "fast", by=60.0, secs=1.0, start=0.5)
    at_24, at_60 = _lint(fast, fps=24), _lint(fast, fps=60)
    assert [f[0] for f in at_24] == [f[0] for f in at_60] == ["error"]
    assert "slides 2.5 px per frame (60 px/s)" in at_24[0][2]
    assert "slides 1.0 px per frame (60 px/s)" in at_60[0][2]
    # 20 px/s for a quarter second (5 px): clean at both
    slow = _walker_sliding(tmp_path / "slow", by=5.0, secs=0.25, start=0.5)
    assert _lint(slow, fps=24) == _lint(slow, fps=60) == []


def test_a_slow_long_slide_is_caught_by_its_drift(tmp_path):
    # 62 px over 1.95 s: about 32 px/s, under the speed tolerance at every
    # frame, but the planted foot ends 62 px from where it was put down
    project = _walker_sliding(tmp_path, by=62.0, secs=1.95)
    [(severity, where, message)] = _lint(project)
    assert (severity, where) == ("error", "timeline/0/joints/0")
    assert message.startswith("`wal`'s `foot_l` drifts 6")
    assert "a planted foot may drift" in message


def test_a_step_grid_is_reported_per_step(tmp_path):
    # on twos (12 steps a second at 24 fps), 60 px/s is a 5 px pop per step
    project = _walker_sliding(tmp_path, by=60.0, secs=1.0, start=0.5)
    [(severity, _where, message)] = _lint(project, step_hz=12)
    assert severity == "error"
    assert "slides 5.0 px per step (60 px/s)" in message


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
    assert "slides 2.5 px per frame (60 px/s) along `crate@surface`" in message


def test_a_crate_mirrored_under_a_still_foot_does_not_skate(tmp_path):
    # the walker's left foot over the crate's middle; the crate flips (scale_x
    # 1 to -1 in a frame): its ends swap on the stage, but in its own frame
    # the foot has not moved (it measured 86 px a frame from the swapped end)
    surface_y = GROUND - CRATE_SURFACE * K
    foot_over_middle = 160 + 20.0 * K  # foot_l hangs 20 units left of the root
    entities = _entity("crate", "crate", 160, GROUND) + _entity(
        "wal", "walker", foot_over_middle, surface_y
    )
    joints = "[{type: support, a: wal@foot_l, b: crate@surface, name: left}]"
    flip = _tween("crate", "scale_x", a=1, b=-1, start=1.0, secs=FRAME)
    project = _project(tmp_path, entities=entities, shot=_shot(joints), actions=flip)
    assert _lint(project, only=("support", "skate")) == []
    states, _ = supports_at(
        _compile(project), project.scene.timeline[0], project.mall, rest_only=False
    )
    slid = [c.slid for s in states for c in s.contacts if c.slid is not None]
    assert len(slid) > 24 and max(map(abs, slid)) < 0.05


def test_a_pushed_bodys_own_points_do_not_skate(tmp_path):
    # a point on the root part (a prop's base, a bone of it, its fraction, the
    # whole body) is its own stance point: a pushed cup or crate slides on it
    cases = [("cup", "cup@base"), ("cup", "cup"), ("crate", "crate@root")]
    cases += [
        ("crate", "crate"),
        ("crate", "crate@surface_l"),
        ("crate", "crate@0.5,1"),
    ]
    for ref, a in cases:
        project = _project(
            tmp_path / a.replace("@", "_").replace(",", "_"),
            entities=_entity(ref, ref, 0, GROUND),
            shot=_shot(f"[{{type: support, a: '{a}', b: ground}}]"),
            actions=_slide(ref, start=0.5, by=40.0, frames=4, origin=0),
        )
        assert _lint(project) == [], a


def test_a_figure_gliding_on_its_origin_does_not_skate(tmp_path):
    for a in ("fig", "fig@origin"):
        project = _project(
            tmp_path / a.replace("@", "_"),
            entities=_entity("fig", "figure", -100, GROUND),
            shot=_shot(f"[{{type: support, a: {a}, b: ground}}]"),
            actions=_slide("fig", start=0.5, by=40.0, frames=4, origin=-100),
        )
        assert _lint(project) == [], a


def test_a_foot_lifting_off_does_not_skate(tmp_path):
    # in one frame the walker moves 8 px forward and rises 5 px (within the
    # support tolerance, about 5.8 px), then leaves the floor: a lift-off,
    # not a slide (it measured 8 px a frame before the normal motion counted)
    up = "\n".join(
        (
            _tween("wal", "x", a=-100, b=-84, start=1.0, secs=2 * FRAME),
            _tween("wal", "y", a=GROUND, b=GROUND - 5, start=1.0, secs=FRAME),
            _tween(
                "wal", "y", a=GROUND - 5, b=GROUND - 40, start=1.0 + FRAME, secs=FRAME
            ),
        )
    )
    declared = _project(
        tmp_path / "a",
        entities=_entity("wal", "walker", -100, GROUND),
        shot=_shot(LEFT),
        actions=up,
    )
    assert _lint(declared) == []
    inferred = _project(
        tmp_path / "b",
        entities=_entity("wal", "walker", -100, GROUND),
        shot=_shot(),
        actions=up,
    )
    assert _lint(inferred, gravity=True) == []


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


def _framed(project, *, camera_frame: str):
    """The project's scene framed by a world: the walker a member standing in
    the world frame, the viewpoint in ``camera_frame`` (``dolly`` moves
    sideways, so the walker crosses the stage)."""
    from an.ir.schema import Frame, FrameMoving, Viewpoint, World, WorldMember

    world = World(
        frames={
            "dolly": Frame(moving=FrameMoving(direction=(1.0, 0.0, 0.0), speed=0.5))
        },
        members=[
            WorldMember(
                kind="prop",
                id="wal",
                store="props",
                ref="walker",
                at=(0.0, 0.0, 5.0),
                height=1.8,
            )
        ],
        viewpoints={
            "v": Viewpoint(at=(0.0, -1.0, 0.0), focal=300.0, frame=camera_frame)
        },
    )
    shot = project.scene.timeline[0].model_copy(update={"viewpoint": "v"})
    return project.scene.model_copy(update={"world": world, "timeline": [shot]})


def test_ground_under_a_moving_world_frame_is_not_judged(tmp_path, monkeypatch):
    import an.ir.world as world_module
    from an.ir.world import frame_moving_members

    # the world places the walker (its feet on the stage's y 60) and moves it
    project = _project(
        tmp_path,
        entities="- {kind: prop, id: wal, store: props, ref: walker}\n",
        shot=_shot(LEFT, ground=60),
    )
    tracking = _framed(project, camera_frame="dolly")
    assert frame_moving_members(tracking, 0) == {"wal"}
    assert frame_moving_members(_framed(project, camera_frame="world"), 0) == set()
    # the camera rides the dolly: the walker standing still in the world slides
    # across the stage's floor, which is not its floor: said once, not judged
    [(severity, where, message)] = _lint(project, scene_ir=tracking)
    assert (severity, where) == ("info", "timeline/0/joints/0")
    assert "an#519 PR 4" in message
    # the gate is what stands between it and a skate error
    monkeypatch.setattr(world_module, "frame_moving_members", lambda *a, **k: set())
    assert [f[0] for f in _lint(project, scene_ir=tracking)] == ["error"]
