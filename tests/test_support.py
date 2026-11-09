"""The ``support`` joint and check (an#519 PR 1b, catalogue A1): penetration and floating against a surface.

The fixture is ``tests/_hold_fixture.py`` (a figure standing on its ``origin``,
a stick drawn in a PNG, a stand and a crate declaring ``surface_l``/``surface_r``),
plus two props written here: a ``cup`` about 30 px tall naming its ``base`` in
``metadata.contacts``, and a ``block`` of SVG art with no ``origin``, whose
only contact is its box. Compiled only, never rendered.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from tests._hold_fixture import CRATE_SURFACE, K, make_project, scene

from an.ir import join, unjoin
from an.ir.schema import JointSpec, SceneIR, Shot
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.validate import validate_semantic
from an.project import load
from an.stage.compile import compile_shot
from an.stage.serialize import to_dict
from an.stage.solve import SOLVE_EXTENSION, declarations, shot_declares_solve
from an.stage.support import (
    SUPPORT_FLOOR_PX,
    contacts_of,
    support_tolerance,
    supports_at,
)

W, H = 640, 480
GROUND = 200.0
CHECKS = {"support", "unknown_body", "joint_violation", "floating_item"}
#: The cup's art, in view-box units: about 30 px tall at stage scale 1.
CUP_UNITS = 35


def _svg(w: int, h: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" '
        f'height="{h}"><rect width="{w}" height="{h}" fill="#888"/></svg>'
    )


def _prop(
    name: str, *, w: int, h: int, origin: bool, metadata=None, anchor=(0.5, 1.0)
) -> dict:
    desc = {
        "kind": "PropDescriptor",
        "schema_version": "0.2.0",
        "name": name,
        "view_box": [0, 0, 400, 400],
        "bones": [{"name": "root", "x": 200.0, "y": 400.0}],
        "slots": [
            {"name": "body", "bone": "root", "draw_order": 0, "attachment": "body"}
        ],
        "skins": {
            "default": {
                "name": "default",
                "slots": {
                    "body": {"body": {"path": "parts/body.svg", "anchor": list(anchor)}}
                },
            }
        },
    }
    if origin:
        desc["origin"] = [200.0, 400.0]
    if metadata is not None:
        desc["metadata"] = metadata
    return desc


EXTRA_PROPS = {
    "cup": (
        _prop(
            "cup",
            w=CUP_UNITS,
            h=CUP_UNITS,
            origin=False,
            metadata={"contacts": {"base": [0.5, 1.0]}},
        ),
        (CUP_UNITS, CUP_UNITS),
    ),
    "block": (_prop("block", w=80, h=80, origin=False), (80, 80)),
    # a leg hung from its bone, its `foot` the far end of its drawing
    "post": (
        _prop(
            "post",
            w=20,
            h=100,
            origin=False,
            metadata={"contacts": {"foot": {"slot": "body"}}},
            anchor=(0.5, 0.0),
        ),
        (20, 100),
    ),
}


def _project(tmp_path: Path, *, entities: str, shot: str, actions: str = "[]"):
    root = tmp_path / "p"
    make_project(root, scene(actions, entities=entities, shot=shot, duration=2.0))
    props = root / "assets" / "props"
    for name, (desc, (w, h)) in EXTRA_PROPS.items():
        (props / name / "parts").mkdir(parents=True, exist_ok=True)
        (props / name / "prop.json").write_text(json.dumps(desc), encoding="utf-8")
        (props / name / "parts" / "body.svg").write_text(_svg(w, h), encoding="utf-8")
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


def _lint(project, only=CHECKS):
    report = validate_semantic(
        project.scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only=set(only),
    )
    return [(f.severity, f.ir_path, f.description) for f in report.findings]


def _compile(project, shot=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(
            shot or project.scene.timeline[0], project.mall, fps=24, width=W, height=H
        )


# -- the declaration ---------------------------------------------------------------


def test_a_support_names_a_surface_and_an_end_only_with_a_stage_point():
    assert JointSpec(type="support", a="cup@base", b="ground").b == "ground"
    assert JointSpec(type="support", a="cup", b="crate/body@surface@0.3").id == "cup"
    assert JointSpec(
        type="support", a="cup", b="world@-50,0", end="world@50,0", name="shelf"
    ).id == ("shelf")
    with pytest.raises(ValueError, match="is not a surface"):
        JointSpec(type="support", a="cup", b="crate@grip")
    with pytest.raises(ValueError, match="`end`"):
        JointSpec(type="support", a="cup", b="ground", end="world@1,0")
    with pytest.raises(ValueError, match="`end`"):
        JointSpec(type="support", a="cup", b="world@0,0")
    with pytest.raises(ValueError, match="only a hinge"):
        JointSpec(type="support", a="cup", b="ground", limits=(0, 1))
    # a contact keeps its shipped rule: a segment, always with its end
    with pytest.raises(ValueError, match="slide and contact"):
        JointSpec(type="contact", a="ball", b="world@0,0")


def test_a_support_round_trips_through_scene_md():
    shot = Shot(
        id="s1",
        duration=2.0,
        entities=[
            {
                "kind": "prop",
                "id": "cup",
                "store": "props",
                "ref": "cup",
                "joints": [{"type": "support", "a": "@base", "b": "ground"}],
            }
        ],
        joints=[
            {"type": "support", "a": "stand", "b": "crate@surface", "name": "rest"}
        ],
        actions=[unjoin("rest", at=0.5), join("rest", at=1.0)],
    )
    scene_ir = SceneIR.model_validate(
        {"meta": {"title": "t", "duration": 2.0}, "timeline": [shot.model_dump()]}
    )
    back = markdown_to_ir(ir_to_markdown(scene_ir)).timeline[0]
    assert back.joints == shot.joints
    assert back.entities[0].joints == shot.entities[0].joints


def test_supports_are_kept_apart_from_the_solve():
    shot = Shot(
        id="s",
        duration=2.0,
        joints=[{"type": "support", "a": "stand", "b": "ground", "name": "rest"}],
        actions=[unjoin("rest", at=0.5), join("rest", at=1.0)],
    )
    decl = declarations(shot, {})
    assert [dj.spec.id for dj in decl.supports] == ["rest"]
    assert [v.action.kind for v in decl.support_verbs] == ["unjoin", "join"]
    assert not decl.joints and not decl.verbs and decl.empty
    assert not shot_declares_solve(shot)


def test_unnamed_entity_supports_are_told_apart(tmp_path):
    # both entities declare `{type: support, a: "@", b: ground}`: each is keyed
    # by its own path, so an `unjoin` of one suspends that one alone
    own = ", joints: [{type: support, a: '@', b: ground}]"
    entities = _entity("stand", "stand", 160, GROUND, own) + _entity(
        "cup", "cup", 0, GROUND, own
    )
    lift = """- {kind: tween, target: stand, property: y, from: 200, to: 160, duration: 0.5, start: 0.5}
- {kind: tween, target: stand, property: y, from: 160, to: 200, duration: 0.5, start: 1.0}"""
    verbs = "\n- {kind: unjoin, joint: stand, at: 0.5}\n- {kind: join, joint: stand, at: 1.5}"
    project = _project(tmp_path, entities=entities, shot=_shot(), actions=lift + verbs)
    shot = project.scene.timeline[0]
    decl = declarations(shot, project.mall)
    assert [dj.qualified_id for dj in decl.supports] == ["stand", "cup"]
    assert [v.action.joint for v in decl.support_verbs] == ["stand", "stand"]
    assert _lint(project) == []
    # held on the cup's own instead, the stand's lift is its error
    other = _project(
        tmp_path / "b",
        entities=entities,
        shot=_shot(),
        actions=lift + verbs.replace("joint: stand", "joint: cup"),
    )
    [(severity, where, message)] = _lint(other)
    assert (severity, where) == ("error", "timeline/0/entities/0/joints/0")
    assert "`stand` floats 40.0 px above" in message


def test_a_support_only_shot_compiles_byte_identically_and_runs_no_solve(tmp_path):
    entities = _entity("stand", "stand", 160, GROUND) + _entity(
        "fig", "figure", -100, GROUND
    )
    actions = (
        "- {kind: tween, target: stand, property: x, from: 160, to: 100, duration: 1.0}"
    )
    plain = _project(tmp_path / "a", entities=entities, shot=_shot(), actions=actions)
    declared = _project(
        tmp_path / "b",
        entities=entities,
        shot=_shot(
            "[{type: support, a: stand, b: ground, name: rest}, {type: support, a: fig, b: ground}]"
        ),
        actions=actions
        + "\n- {kind: unjoin, joint: rest, at: 0.5}\n- {kind: join, joint: rest, at: 1.5}",
    )
    a, b = _compile(plain), _compile(declared)
    assert SOLVE_EXTENSION not in (b.meta.extensions or {})
    assert to_dict(a) == to_dict(b)


# -- contacts ------------------------------------------------------------------------


def test_contacts_come_from_the_chain(tmp_path, monkeypatch):
    entities = (
        _entity("fig", "figure", -100, GROUND)
        + _entity("stick", "stick", 40, 150)
        + _entity("cup", "cup", 0, GROUND)
        + _entity("block", "block", 100, GROUND)
    )
    project = _project(tmp_path, entities=entities, shot=_shot())
    doc = _compile(project)
    shot = project.scene.timeline[0]
    by_id = {e.id: e for e in shot.entities}
    source = {
        eid: contacts_of(by_id[eid], project.mall, doc=doc).source for eid in by_id
    }
    # the figure stands on its origin; the stick's origin is its middle (where it
    # is held, an#601), so it is its read ink; the block's SVG gives only its box
    assert source == {
        "fig": "origin",
        "stick": "ink",
        "cup": "metadata",
        "block": "box",
    }
    assert contacts_of(by_id["cup"], project.mall).points == {"base": ("", (0.5, 1.0))}
    # a kind's hook comes first
    import an.genres.registry as registry

    hooked = NS(contacts=lambda desc: {"foot": ("body", None)}, landmarks=None)
    monkeypatch.setattr(registry, "entity_kind", lambda name: hooked)
    got = contacts_of(by_id["cup"], project.mall)
    assert (got.source, got.points) == ("hook", {"foot": ("body", None)})


def test_a_pin_and_a_support_name_one_point_for_a_contact(tmp_path):
    # `post@foot` names no point on its part: the far end of the leg. The solve
    # pins it and the support check measures it at the same place (not a hand's
    # point, 4% up the leg).
    target = (40.0, 150.0)
    project = _project(
        tmp_path,
        entities=_entity("post", "post", 0, 60),
        shot=_shot("[{type: support, a: post@foot, b: ground, name: rest}]"),
        actions=f"- {{kind: pin, point: post@foot, to: 'world@{target[0]:g},{target[1]:g}'}}",
    )
    shot = project.scene.timeline[0]
    states, problems = supports_at(_compile(project), shot, project.mall)
    measured = [s.contacts[0] for s in states if s.joint == "rest"]
    assert problems == [] and measured
    assert {c.name for c in measured} == {"foot"}
    for c in measured:
        assert c.at == pytest.approx(target, abs=0.3)


def test_the_solve_resolves_a_named_contact_like_a_landmark(tmp_path):
    def errors(point):
        project = _project(
            tmp_path / point,
            entities=_entity("cup", "cup", 0, 150),
            shot=_shot(f"[{{type: pin, a: cup@{point}, b: 'world@0,180'}}]"),
        )
        return [f[2] for f in _lint(project, {"unknown_body"}) if f[0] == "error"]

    assert errors("base") == []
    [message] = errors("rim")
    assert "named points: ['base']" in message


# -- the check -------------------------------------------------------------------------


@pytest.mark.parametrize("dy, kind", [(0.0, None), (5.0, "into"), (-5.0, "floats")])
def test_a_prop_on_the_ground_rests_sinks_or_floats(tmp_path, dy, kind):
    project = _project(
        tmp_path,
        entities=_entity("stand", "stand", 160, GROUND + dy),
        shot=_shot("[{type: support, a: stand, b: ground}]"),
    )
    findings = _lint(project)
    if kind is None:
        assert findings == []
        return
    [(severity, where, message)] = findings
    assert (severity, where) == ("error", "timeline/0/joints/0")
    assert kind in message and "5.0 px" in message
    assert "from 0.00 s to 2.00 s" in message


def test_an_entity_standing_on_the_floor_is_held_to_it_with_a_warning(tmp_path):
    # the stand opens on the floor (taken to stand on it), then a `set` lifts it
    # 5 px for good: judged at its rest instants, it is said once
    entities = (
        _entity("fig", "figure", -100, GROUND)
        + _entity("stand", "stand", 160, GROUND)
        + _entity(
            "far", "stand", 260, GROUND - 120
        )  # off the floor as it opens: flying
    )
    actions = "- {kind: set, target: stand, property: y, value: 195, at: 1.0}"
    findings = _lint(
        _project(tmp_path, entities=entities, shot=_shot(), actions=actions)
    )
    [(severity, where, message)] = findings
    assert (severity, where) == ("warning", "timeline/0/entities/1")
    assert message.startswith("`stand` stands on `ground` (y 200) as the shot opens")
    assert "5.0 px above" in message and "from 1.00 s to 2.00 s" in message


def test_a_figure_staged_on_a_crate_does_not_stand_on_the_floor(tmp_path):
    # its feet are on the crate's top, far above the floor as the shot opens:
    # nothing infers it stands on the floor, so nothing says it floats there
    surface_y = GROUND - CRATE_SURFACE * K
    entities = _entity("crate", "crate", 160, GROUND) + _entity(
        "fig", "figure", 160, surface_y
    )
    project = _project(tmp_path, entities=entities, shot=_shot())
    assert _lint(project) == []
    states, problems = supports_at(
        _compile(project), project.scene.timeline[0], project.mall
    )
    assert problems == [] and {s.entity for s in states} <= {"crate"}


def test_an_inferred_stance_is_not_judged_while_it_moves(tmp_path):
    # up 40 px and back: judged only as it opens and while it rests
    actions = """- {kind: tween, target: stand, property: y, from: 200, to: 160, duration: 0.5, start: 0.5}
- {kind: tween, target: stand, property: y, from: 160, to: 200, duration: 0.5, start: 1.0}"""
    project = _project(
        tmp_path,
        entities=_entity("stand", "stand", 160, GROUND),
        shot=_shot(),
        actions=actions,
    )
    assert _lint(project) == []


def test_a_small_prop_is_held_to_the_pixel_floor(tmp_path):
    assert support_tolerance(30.0) == SUPPORT_FLOOR_PX
    for dy, expected in ((-1.5, []), (-3.0, ["error"])):
        project = _project(
            tmp_path / str(dy),
            entities=_entity("cup", "cup", 0, GROUND + dy),
            shot=_shot("[{type: support, a: cup@base, b: ground}]"),
        )
        found = _lint(project)
        assert [f[0] for f in found] == expected, found
    assert "tolerance is 2.0 px" in found[0][2]
    shot = project.scene.timeline[0]
    states, problems = supports_at(_compile(project), shot, project.mall)
    assert problems == []
    assert states[0].height == pytest.approx(CUP_UNITS * K, abs=0.01)
    assert states[0].contacts[0].name == "base"


def test_unjoin_suspends_a_support_and_is_not_an_error(tmp_path):
    lift = """- {kind: tween, target: stand, property: y, from: 200, to: 160, duration: 0.5, start: 0.5}
- {kind: tween, target: stand, property: y, from: 160, to: 200, duration: 0.5, start: 1.0}"""
    verbs = (
        "\n- {kind: unjoin, joint: rest, at: 0.5}\n- {kind: join, joint: rest, at: 1.5}"
    )
    joints = "[{type: support, a: stand, b: ground, name: rest}]"
    entities = _entity("stand", "stand", 160, GROUND)
    suspended = _project(
        tmp_path / "a", entities=entities, shot=_shot(joints), actions=lift + verbs
    )
    assert _lint(suspended) == []
    held = _project(tmp_path / "b", entities=entities, shot=_shot(joints), actions=lift)
    [(severity, _where, message)] = _lint(held)
    assert severity == "error" and "floats 40.0 px above" in message
    # the span starts where the (eased) gap passes the tolerance, after 0.5 s
    start = float(message.split(" from ")[1].split(" s")[0])
    assert 0.5 < start < 1.0


def test_a_flight_is_not_judged(tmp_path):
    project = _project(
        tmp_path,
        entities=_entity(
            "stand",
            "stand",
            160,
            GROUND - 30,
            ", overrides: {airborne: {from: 0.0, until: 2.0}}",
        ),
        shot=_shot("[{type: support, a: stand, b: ground}]"),
    )
    assert _lint(project) == []


def test_a_support_naming_what_the_shot_lacks_is_the_support_checks_error(tmp_path):
    project = _project(
        tmp_path,
        entities=_entity("stand", "stand", 160, GROUND)
        + _entity("cup", "cup", 0, GROUND),
        shot=_shot(
            "[{type: support, a: stand, b: nobody@surface}, {type: support, a: ghost, b: ground},"
            " {type: support, a: cup@rim, b: ground}]"
        ),
    )
    findings = _lint(project)
    assert all(f[0] == "error" for f in findings)
    assert [f[1] for f in findings] == [
        "timeline/0/joints/0",
        "timeline/0/joints/1",
        "timeline/0/joints/2",
    ]
    assert "'nobody' is not an entity of this shot" in findings[0][2]
    assert "'ghost' is not an entity of this shot" in findings[1][2]
    assert "metadata: {contacts: {rim: [u, v]}}" in findings[2][2]


def test_an_svg_prop_is_measured_on_its_box_and_never_inferred(tmp_path):
    entities = _entity("block", "block", 100, GROUND - 6)
    assert _lint(_project(tmp_path / "a", entities=entities, shot=_shot())) == []
    declared = _project(
        tmp_path / "b",
        entities=entities,
        shot=_shot("[{type: support, a: block, b: ground}]"),
    )
    [(severity, _where, message)] = _lint(declared)
    assert severity == "error" and "6.0 px above" in message
    assert "box, not its ink" in message


def test_a_prop_on_a_body_surface(tmp_path):
    surface_y = GROUND - CRATE_SURFACE * K
    entities = _entity("crate", "crate", 160, GROUND)
    for dy, expected in ((0.0, []), (-10.0, ["error"])):
        project = _project(
            tmp_path / str(dy),
            entities=entities + _entity("stand", "stand", 160, surface_y + dy),
            shot=_shot("[{type: support, a: stand, b: crate@surface}]"),
        )
        found = _lint(project)
        assert [f[0] for f in found] == expected, found
    assert "above `crate@surface`" in found[0][2]
    # past the surface's ends nothing is measured
    off = _project(
        tmp_path / "off",
        entities=entities + _entity("stand", "stand", -200, surface_y - 50),
        shot=_shot("[{type: support, a: stand, b: crate@surface}]"),
    )
    assert _lint(off) == []


def test_an_item_the_hold_layer_lays_on_a_surface_is_on_it(tmp_path):
    entities = _entity("crate", "crate", 160, GROUND) + _entity(
        "stick", "stick", 160, 100, ", overrides: {held_by: crate@surface}"
    )
    project = _project(
        tmp_path,
        entities=entities,
        shot=_shot("[{type: support, a: stick, b: crate@surface}]"),
    )
    assert [f for f in _lint(project) if f[0] != "info"] == []


def test_a_hold_item_is_not_inferred_to_stand(tmp_path):
    # the stick lies on the floor by `held_by`: floating_item's, never doubled
    entities = _entity(
        "stick", "stick", 40, 150, ", overrides: {held_by: ground}"
    ) + _entity("fig", "figure", -100, GROUND)
    assert _lint(_project(tmp_path, entities=entities, shot=_shot())) == []


def test_no_floor_is_said_once(tmp_path):
    project = _project(
        tmp_path,
        entities=_entity("stand", "stand", 160, GROUND)
        + _entity("fig", "figure", -100, GROUND),
        shot=_shot(
            "[{type: support, a: stand, b: ground}, {type: support, a: fig, b: ground}]",
            ground=None,
        ),
    )
    [(severity, where, message)] = _lint(project)
    assert (severity, where) == ("info", "timeline/0/solve")
    assert message.startswith("no floor declared") and "`fig`, `stand`" in message
