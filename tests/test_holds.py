"""Holding things (an#502, catalogue A1 and A4): grasp, place, release, handover, swap.

The fixture is ``tests/_hold_fixture.py``: a figure that bends at the hip (a
torso with one-link arms, legs as root parts, its stage point at its feet), a
stick drawn with transparent margins and a ``grip`` bone, and a stand with a
``hand`` socket. Compiled only, never rendered: the assertions read the
compiled document's channels (``evaluate_timeline``) and the hold report.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import pytest

from tests._hold_fixture import K, make_project, scene

from an.ir import grasp, handover, place, release, swap
from an.ir.holds import DFLT_REACH, DFLT_RETRACT
from an.ir.schema import SceneIR, Shot
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.validate import validate_semantic
from an.stage.compile import compile_shot
from an.stage.hold import GRASP_TOLERANCE_PX, HoldError
from an.stage.timeline import evaluate_timeline, screen_position, timeline_from_scene

#: The canvas the fixture compiles to: stage (0, 0) is the canvas centre.
W, H = 640, 480
GROUND = 200.0
HOLD_CHECKS = {"hold_conflict", "unreachable_hold", "floating_item", "unknown_body"}


def _compile(project, shot=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(
            shot or project.scene.timeline[0], project.mall, fps=24, width=W, height=H
        )


def _project(tmp_path: Path, actions: str, **kw):
    return make_project(tmp_path / "p", scene(actions, **kw))


def _stage(doc, path, t, point=(0.0, 0.0)):
    pose = evaluate_timeline(timeline_from_scene(doc), t)
    x, y = screen_position(doc, path, pose=pose, point=point)
    return (x - W / 2.0, y - H / 2.0)


def _pose(doc, t):
    return evaluate_timeline(timeline_from_scene(doc), t)


def _times(start, end, fps=24):
    return [k / fps for k in range(int(math.ceil(start * fps)), int(end * fps) + 1)]


def _holds(doc):
    return doc.meta.extensions["solve"]["holds"]


def _gesture(doc, kind, index=0):
    return [g for g in _holds(doc)["gestures"] if g["kind"] == kind][index]


#: The stick's grip, in its node's frame (60 view-box units below its centre).
GRIP = (0.0, 60.0 * K)
#: The bottom of the stick's ink, in its node's frame (its 260-unit canvas has
#: 30 transparent units under the bar).
INK_BOTTOM = (0.0, 100.0 * K)
#: The figure's right hand: the end of its arm (16 x 200 units, hung from its top).
HAND_END = (0.0, 200.0 * K * (1.0 - 0.04))


def _hand(doc, t):
    return _stage(doc, "fig/arm_r", t, point=HAND_END)


def _grip(doc, t):
    return _stage(doc, "stick", t, point=GRIP)


def _lint(project, shot=None, only=HOLD_CHECKS):
    scene_ir = (
        project.scene
        if shot is None
        else project.scene.model_copy(update={"timeline": [shot]})
    )
    report = validate_semantic(
        scene_ir,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only=set(only),
    )
    return [(f.severity, f.description) for f in report.findings]


# -- the IR -----------------------------------------------------------------------


def test_the_hold_verbs_round_trip_through_scene_md():
    shot = Shot(
        id="s1",
        duration=6.0,
        solve={"ground": 200},
        entities=[
            {
                "kind": "prop",
                "id": "cup",
                "store": "props",
                "ref": "cup",
                "overrides": {"held_by": "ground"},
            }
        ],
        actions=[
            grasp("paul/arm_r", "cup@grip", reach=0.5),
            place("cup", "ground@-40", rotation=0.3),
            release("cup", at=3.0, onto="ground@100", arc=50),
            handover("cup", "jo@hand_l", meet=0.5),
            swap("nap/hand", take="musket", give="sword", by="stu@hand_r", lag=0.3),
        ],
    )
    back = markdown_to_ir(ir_to_markdown(SceneIR(timeline=[shot])))
    assert back.timeline[0].model_dump(mode="json") == shot.model_dump(mode="json")
    md = ir_to_markdown(SceneIR(timeline=[Shot(id="s", actions=[grasp("a/arm", "b")])]))
    assert (
        f"reach: {DFLT_REACH}" not in md and "retract" not in md
    )  # defaults stay unwritten


def test_a_hold_verb_refuses_a_retract_of_zero():
    with pytest.raises(ValueError):
        grasp("a/arm", "b", retract=0.0)


# -- picking up --------------------------------------------------------------------


def test_an_item_on_the_ground_lies_on_its_ink_not_its_box(tmp_path):
    """``held_by: ground`` puts the lowest painted pixel on the floor line: the
    stick's PNG has 30 transparent px under its ink, which must not float."""
    doc = _compile(
        _project(tmp_path, "- {kind: grasp, by: fig/arm_r, item: stick, start: 2.0}")
    )
    ink_bottom = _stage(doc, "stick", 0.0, point=INK_BOTTOM)
    box_bottom = _stage(doc, "stick", 0.0, point=(0.0, 130 * K))
    assert ink_bottom[1] == pytest.approx(GROUND, abs=1e-3)
    assert box_bottom[1] > GROUND + 10  # the margin is below the floor line, unseen


def test_a_grasp_reaches_the_grip_bending_and_takes_it_where_it_lies(tmp_path):
    doc = _compile(
        _project(tmp_path, "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}")
    )
    g = _gesture(doc, "grasp")
    contact = g["contact"]
    # The hand arrives exactly at the grip, and the figure bent to get there.
    assert math.dist(_hand(doc, contact), _grip(doc, contact)) < GRASP_TOLERANCE_PX
    assert g["gap"] <= GRASP_TOLERANCE_PX and g["lean"] > 10
    # The stick does not move before the hand gets there ...
    lying = _stage(doc, "stick", 0.0)
    assert all(
        math.dist(_stage(doc, "stick", t), lying) < 1e-6 for t in _times(0.0, contact)
    )
    # ... and from then on it is in the hand, the grip on the hand, frame after frame.
    for t in _times(contact, 4.0):
        assert math.dist(_hand(doc, t), _grip(doc, t)) < GRASP_TOLERANCE_PX, t
    # The bend comes back: the torso is upright once the retract is over.
    pose = _pose(doc, g["end"] + 0.05)
    assert abs(pose.get(("fig/torso", "rotation"), 0.0)) < 1e-6


def test_the_item_never_jumps(tmp_path):
    """Frame to frame, the stick's grip moves no more than the hand does (a
    reframe that keeps the world pose)."""
    doc = _compile(
        _project(
            tmp_path,
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}\n- {kind: place, item: stick, onto: stand@hand, start: 1.6}",
        )
    )
    frames = _times(0.0, 4.0)
    for a, b in zip(frames, frames[1:]):
        step = math.dist(_grip(doc, a), _grip(doc, b))
        hand = math.dist(_hand(doc, a), _hand(doc, b))
        assert step <= hand + 1e-3, (a, step, hand)


def test_what_rides_on_a_bending_body_bends_with_it(tmp_path):
    """The head and the other arm keep their angle to the torso while it bends
    (they ride on it), and the legs stay planted."""
    doc = _compile(
        _project(tmp_path, "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}")
    )
    contact = _gesture(doc, "grasp")["contact"]
    pose = _pose(doc, contact)
    torso = pose[("fig/torso", "rotation")]
    assert torso > 0.1
    assert pose[("fig/head", "rotation")] == pytest.approx(torso, abs=1e-5)
    assert pose[("fig/arm_l", "rotation")] == pytest.approx(torso, abs=1e-5)
    assert ("fig/leg_l", "rotation") not in pose or abs(
        pose[("fig/leg_l", "rotation")]
    ) < 1e-9


# -- putting down, handing over, swapping --------------------------------------------


def test_a_place_puts_the_grip_in_the_socket_aligned_with_it(tmp_path):
    doc = _compile(
        _project(
            tmp_path,
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}\n- {kind: place, item: stick, onto: stand@hand, start: 1.6}",
        )
    )
    g = _gesture(doc, "place")
    assert g["gap"] <= GRASP_TOLERANCE_PX
    socket = _stage(doc, "stand", 0.0, point=(0.0, -250.0 * K))
    for t in _times(g["contact"], 4.0):
        assert math.dist(_grip(doc, t), socket) < GRASP_TOLERANCE_PX
        assert _pose(doc, t)[("stick", "rotation")] == pytest.approx(
            0.0, abs=1e-6
        )  # the socket's frame
    assert _holds(doc)["holders"]["stick"] == [
        [0.0, "ground"],
        [_gesture(doc, "grasp")["contact"], "fig/arm_r"],
        [g["contact"], "stand@hand"],
    ]


def test_a_place_on_the_ground_lays_it_down_at_floor_height(tmp_path):
    doc = _compile(
        _project(
            tmp_path,
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}\n- {kind: place, item: stick, onto: ground@-60, start: 1.6}",
        )
    )
    g = _gesture(doc, "place")
    assert g["gap"] <= GRASP_TOLERANCE_PX
    for t in _times(g["contact"], 4.0):
        x, y = _stage(doc, "stick", t)
        assert x == pytest.approx(-60.0, abs=1e-3)
        # it lies as it lay before it was taken (rotation 0, upright as drawn)
        assert _stage(doc, "stick", t, point=INK_BOTTOM)[1] == pytest.approx(
            GROUND, abs=1.0
        )


def test_a_release_tossed_onto_the_ground_lands_there_on_an_arc(tmp_path):
    actions = "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}\n- {kind: release, item: stick, at: 1.6, onto: ground@150, arc: 60}"
    doc = _compile(_project(tmp_path, actions))
    ys = [(_stage(doc, "stick", t)[1], t) for t in _times(1.6, 4.0)]
    start_y = ys[0][0]
    apex = min(y for y, _ in ys)
    assert apex < start_y - 30  # it rises before it falls
    x, _y = _stage(doc, "stick", 4.0)
    assert x == pytest.approx(150.0, abs=1e-3)
    assert _stage(doc, "stick", 4.0, point=INK_BOTTOM)[1] == pytest.approx(
        GROUND, abs=1.0
    )


def test_a_dropped_item_falls_straight_and_lands_on_the_floor(tmp_path):
    actions = "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}\n- {kind: release, item: stick, at: 2.0}"
    doc = _compile(_project(tmp_path, actions))
    x0 = _stage(doc, "stick", 2.0)[0]
    assert _stage(doc, "stick", 4.0)[0] == pytest.approx(x0, abs=0.5)
    assert _stage(doc, "stick", 4.0, point=INK_BOTTOM)[1] == pytest.approx(
        GROUND, abs=1.0
    )
    ys = [_stage(doc, "stick", t)[1] for t in _times(2.0, 2.4)]
    assert all(b >= a - 1e-6 for a, b in zip(ys, ys[1:]))  # it only goes down


def test_a_held_item_turns_round_with_its_carrier(tmp_path):
    """A carrier that mirrors (scale_x through 0) mirrors what it holds."""
    actions = """- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}
- {kind: tween, target: fig, property: scale_x, from: 1.0, to: -1.0, duration: 0.4, start: 2.0}"""
    doc = _compile(_project(tmp_path, actions))
    before, after = _pose(doc, 1.9), _pose(doc, 3.0)
    assert before[("stick", "scale_x")] > 0 > after[("stick", "scale_x")]
    assert math.dist(_hand(doc, 3.0), _grip(doc, 3.0)) < GRASP_TOLERANCE_PX


def test_a_swap_takes_one_item_and_gives_another(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [40, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 0], scale: 0.5, after: fig}, overrides: {held_by: stand@hand}}
- {kind: prop, id: rod, store: props, ref: stick, stage: {at: [-200, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
    actions = """- {kind: grasp, by: fig/arm_l, item: rod, start: 0.2}
- {kind: swap, holder: stand@hand, take: stick, give: rod, by: fig/arm_r, start: 1.2}"""
    doc = _compile(make_project(tmp_path / "p", scene(actions, entities=entities)))
    holders = _holds(doc)["holders"]
    assert (
        holders["stick"][-1][1] == "fig/arm_r" and holders["rod"][-1][1] == "stand@hand"
    )
    assert all(g["gap"] <= GRASP_TOLERANCE_PX for g in _holds(doc)["gestures"])


def test_a_handover_between_two_hands_meets_in_the_middle(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-160, 200]}}
- {kind: prop, id: jo, store: props, ref: figure, stage: {at: [100, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [-140, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
    actions = """- {kind: set, target: jo, property: scale_x, value: -1.0, at: 0.0}
- {kind: grasp, by: fig/arm_r, item: stick, start: 0.2}
- {kind: handover, item: stick, to: jo/arm_r, meet: 0.5, start: 1.5}"""
    doc = _compile(make_project(tmp_path / "p", scene(actions, entities=entities)))
    take = _gesture(doc, "take")
    assert take["gap"] <= GRASP_TOLERANCE_PX
    assert _holds(doc)["holders"]["stick"][-1][1] == "jo/arm_r"
    # jo faces the other way: the stick, aligned to jo's hand, is drawn mirrored
    assert _pose(doc, 3.5)[("stick", "scale_x")] < 0


# -- what an validate says ------------------------------------------------------------


def test_a_reach_that_cannot_arrive_is_an_error_saying_which_way_to_move(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-260, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [160, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [200, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
    project = make_project(
        tmp_path / "p",
        scene(
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}", entities=entities
        ),
    )
    findings = _lint(project)
    errors = [m for s, m in findings if s == "error"]
    assert (
        len(errors) == 1
        and "stays" in errors[0]
        and "px short" in errors[0]
        and "to the right" in errors[0]
    )
    doc = _compile(project)
    # Never cheated: the stick stays where the hand is when it is taken, no slide to the hand.
    contact = (
        round(_gesture(doc, "grasp")["contact"] * 24) / 24
    )  # the frame it is taken at
    assert math.dist(_stage(doc, "stick", contact), _stage(doc, "stick", 0.0)) < 1e-6


@pytest.mark.parametrize(
    "actions, expected",
    [
        (
            "- {kind: place, item: stick, onto: stand@hand, start: 0.5}",
            "nothing holds it",
        ),
        (
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.2}\n- {kind: grasp, by: fig/arm_r, item: stick, start: 1.5}",
            "already holds",
        ),
        (
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.2}\n- {kind: place, item: stick, onto: ground, start: 0.6}",
            "before its grasp",
        ),
        ("- {kind: grasp, by: fig/arm_r, item: ghost, start: 0.2}", "not an entity"),
    ],
    ids=["not-held", "twice", "overlap", "unknown-item"],
)
def test_holds_that_do_not_add_up_are_refused_by_name(tmp_path, actions, expected):
    project = _project(tmp_path, actions)
    with pytest.raises(HoldError):
        _compile(project)
    messages = [m for s, m in _lint(project) if s == "error"]
    assert messages and any(expected in m for m in messages), messages


def test_a_socket_that_holds_something_must_be_emptied_first(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [40, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 0], scale: 0.5, after: fig}, overrides: {held_by: stand@hand}}
- {kind: prop, id: rod, store: props, ref: stick, stage: {at: [-200, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
    actions = """- {kind: grasp, by: fig/arm_l, item: rod, start: 0.2}
- {kind: place, item: rod, onto: stand@hand, start: 1.2}"""
    project = make_project(tmp_path / "p", scene(actions, entities=entities))
    messages = [m for s, m in _lint(project) if s == "error"]
    assert any("holds 'stick'" in m and "swap" in m for m in messages), messages


def test_an_item_taken_from_above_the_floor_is_called_floating(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [20, 140], scale: 0.5, after: fig}}
"""
    project = make_project(
        tmp_path / "p",
        scene(
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}", entities=entities
        ),
    )
    warnings_ = [m for s, m in _lint(project) if s == "warning"]
    assert any("above the ground" in m and "held_by: ground" in m for m in warnings_), (
        warnings_
    )


def test_the_hold_checks_are_core_checks():
    from an.genres.registry import CORE_OWNER, check_names

    assert {"hold_conflict", "unreachable_hold", "floating_item"} <= set(
        check_names(owner=CORE_OWNER)
    )


def test_the_solve_with_holds_is_deterministic(tmp_path):
    from an.stage.serialize import to_dict

    project = _project(
        tmp_path,
        "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}\n- {kind: place, item: stick, onto: stand@hand, start: 1.6}",
    )
    assert to_dict(_compile(project)) == to_dict(_compile(project))


def test_defaults_are_the_documented_ones():
    g = grasp("a/arm", "b")
    assert (g.reach, g.retract) == (DFLT_REACH, DFLT_RETRACT)


def test_a_genre_names_a_rigs_points_for_the_hold_verbs(tmp_path, monkeypatch):
    """``EntityKind.landmarks``: ``fig@hand_r`` resolves to the far end of the
    part the kind names, so a scene says ``hand_r`` without knowing the rig."""
    from dataclasses import replace

    from an.genres import registry

    prop = registry.entity_kind("prop")
    state = registry.snapshot()
    try:
        registry.register_entity_kind(
            replace(prop, landmarks=lambda desc: {"hand_r": ("arm_r", None)}),
            owner=registry._ENTITY_KINDS.owners["prop"],
            replace=True,
        )
        named = _compile(
            _project(
                tmp_path, "- {kind: grasp, by: fig@hand_r, item: stick, start: 0.5}"
            )
        )
    finally:
        registry.restore(state)
    path = _compile(
        _project(
            tmp_path / "b", "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}"
        )
    )
    contact = _gesture(named, "grasp")["contact"]
    assert _gesture(named, "grasp")["gap"] <= GRASP_TOLERANCE_PX
    assert math.dist(_hand(named, contact), _hand(path, contact)) < 1e-6


def test_a_taken_item_turns_to_how_the_hand_holds_things(tmp_path):
    """``align`` (the default): over the retract the stick turns to the hand's
    frame, as a socket holds it; ``align: false`` keeps the angle it was taken at."""
    actions = "- {{kind: grasp, by: fig/arm_r, item: stick, start: 0.5{}}}\n- {{kind: tween, target: fig/arm_r, property: rotation, from: 0.0, to: 0.4, duration: 0.5, start: 2.0}}"
    aligned = _compile(_project(tmp_path / "a", actions.format("")))
    kept = _compile(_project(tmp_path / "k", actions.format(", align: false")))
    g = _gesture(aligned, "grasp")
    contact = round(g["contact"] * 24) / 24
    for t in (g["end"] + 0.05, 2.25, 3.0):
        pose = _pose(aligned, t)
        assert pose[("stick", "rotation")] == pytest.approx(
            pose[("fig/arm_r", "rotation")], abs=1e-5
        ), t
        assert math.dist(_hand(aligned, t), _grip(aligned, t)) < GRASP_TOLERANCE_PX
    at_contact, later = _pose(kept, contact), _pose(kept, 3.0)
    turned = later[("fig/arm_r", "rotation")] - at_contact[("fig/arm_r", "rotation")]
    assert later[("stick", "rotation")] - at_contact[
        ("stick", "rotation")
    ] == pytest.approx(turned, abs=1e-5)


def test_a_passenger_part_does_not_swing_when_its_body_moves(tmp_path):
    """In pose mode a part nothing acts on (the head, the idle arm) keeps the
    angle the document gives it while the figure travels: it does not swing
    about its joint as the joint drags it along."""
    actions = """- {kind: tween, target: fig, property: x, from: -100, to: -300, duration: 0.6, start: 0.0}
- {kind: grasp, by: fig/arm_r, item: stick, start: 2.0}"""
    doc = _compile(_project(tmp_path, actions))
    for t in _times(0.0, 1.9):
        pose = _pose(doc, t)
        for part in ("fig/head", "fig/arm_l", "fig/arm_r"):
            assert abs(pose.get((part, "rotation"), 0.0)) < 1e-6, (t, part)


def test_a_part_that_draws_a_speck_stays_on_its_joint(tmp_path):
    """A one-pixel drawing (the "empty" key of a swap set) is no extent: as a
    body it was a speck far from its pivot, which the solver could not turn,
    and the part drifted off its joint while the figure moved."""
    import json

    from an.project import load

    project = _project(
        tmp_path,
        "- {kind: tween, target: fig, property: x, from: -100, to: -300, duration: 0.6}\n- {kind: grasp, by: fig/arm_r, item: stick, start: 2.0}",
        shot="duration: 4.0\nsolve: {ground: 200, mode: dynamic}",  # parts swing: only the joint keeps them on
    )
    root = Path(project.root) if hasattr(project, "root") else tmp_path / "p"
    desc_path = root / "assets" / "props" / "figure" / "prop.json"
    desc = json.loads(desc_path.read_text(encoding="utf-8"))
    desc["bones"].append({"name": "badge", "parent": "head", "x": 0.0, "y": 0.0})
    desc["slots"].append(
        {"name": "badge", "bone": "badge", "draw_order": 5, "attachment": "badge"}
    )
    desc["skins"]["default"]["slots"]["badge"] = {
        "badge": {
            "path": "parts/badge.svg",
            "anchor": [0.5, 68.0],
            "width": 1,
            "height": 1,
        }
    }
    desc_path.write_text(json.dumps(desc), encoding="utf-8")
    (desc_path.parent / "parts" / "badge.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1" width="1" height="1"><rect width="1" height="1" fill="#000" fill-opacity="0.01"/></svg>',
        encoding="utf-8",
    )
    doc = _compile(load(root))
    for t in _times(0.0, 1.9):
        assert (
            math.dist(_stage(doc, "fig/badge", t), _stage(doc, "fig/head", t)) < 0.25
        ), t


# -- regressions found in review ------------------------------------------------------


def test_a_hand_catches_what_another_lets_go_of_at_that_instant(tmp_path):
    """A release and a grasp of the same item at one instant: the release
    comes first and the other hand catches it (it used to fall to the floor
    while the catching hand arrived empty)."""
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: jo, store: props, ref: figure, stage: {at: [60, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 150], scale: 0.5, after: jo}, overrides: {held_by: ground}}
"""
    actions = """- {kind: grasp, by: fig/arm_r, item: stick, start: 0.2}
- {kind: release, item: stick, at: 2.0}
- {kind: grasp, by: jo/arm_l, item: stick, start: 1.6}"""
    doc = _compile(make_project(tmp_path / "p", scene(actions, entities=entities)))
    holders = _holds(doc)["holders"]["stick"]
    assert [h for _t, h in holders] == ["ground", "fig/arm_r", "air", "jo/arm_l"]


def test_a_gesture_that_would_reach_after_the_shot_ends_is_refused(tmp_path):
    project = _project(
        tmp_path, "- {kind: grasp, by: fig/arm_r, item: stick, start: 3.9}"
    )
    with pytest.raises(HoldError):
        _compile(project)
    assert any("after the shot ends" in m for s, m in _lint(project) if s == "error")


def test_one_arm_holds_one_item_whatever_point_of_it_is_named(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
- {kind: prop, id: rod, store: props, ref: stick, stage: {at: [-20, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
    actions = """- {kind: grasp, by: fig/arm_r, item: stick, start: 0.2}
- {kind: grasp, by: 'fig/arm_r@0.5,0.9', item: rod, start: 1.5}"""
    project = make_project(tmp_path / "p", scene(actions, entities=entities))
    messages = [m for s, m in _lint(project) if s == "error"]
    assert any("still holds 'stick'" in m for m in messages), messages


def test_a_reach_that_starts_while_the_body_moves_is_not_called_a_rejoin(tmp_path):
    actions = """- {kind: tween, target: fig, property: x, from: -100, to: -60, duration: 1.0, start: 0.0}
- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}"""
    project = _project(tmp_path, actions)
    report = _compile(project).meta.extensions["solve"]
    assert not [
        s for s in report["snaps"] if "grasp" in report["joints"][s["joint"]]["id"]
    ]
    assert not any(
        "rejoined" in m for _s, m in _lint(project, only={"joint_violation"})
    )


def test_an_item_that_holds_another_is_refused_by_name(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [40, 200]}, overrides: {held_by: ground}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 0], scale: 0.5}, overrides: {held_by: stand@hand}}
"""
    project = make_project(
        tmp_path / "p",
        scene(
            "- {kind: grasp, by: fig/arm_r, item: stand, start: 0.2}", entities=entities
        ),
    )
    messages = [m for s, m in _lint(project) if s == "error"]
    assert any("is itself held" in m for m in messages), messages
