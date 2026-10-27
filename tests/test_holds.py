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
            swap(
                "nap/hand", take="sword", give="musket", by="stu@hand_l", rotation=-0.4
            ),
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


def test_a_place_into_a_socket_at_a_rotation_rests_aimed_and_turns_with_the_socket(
    tmp_path,
):
    """``rotation`` on a place into a socket: the item comes to rest at that
    stage angle (a musket aimed at someone), its grip on the socket, and is held
    relative to the socket from then on."""
    doc = _compile(
        _project(
            tmp_path,
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}\n"
            "- {kind: place, item: stick, onto: stand@hand, start: 1.6, rotation: 0.6}\n"
            "- {kind: tween, target: stand, property: rotation, from: 0.0, to: 0.3, duration: 0.5, start: 3.0}",
        )
    )
    g = _gesture(doc, "place")
    assert g["gap"] <= GRASP_TOLERANCE_PX
    for t in _times(g["contact"], 2.9):
        socket = _stage(doc, "stand", t, point=(0.0, -250.0 * K))
        assert math.dist(_grip(doc, t), socket) < GRASP_TOLERANCE_PX
        assert _pose(doc, t)[("stick", "rotation")] == pytest.approx(0.6, abs=1e-6)
    later = _pose(doc, 3.8)
    assert later[("stick", "rotation")] == pytest.approx(0.9, abs=1e-5)
    socket = _stage(doc, "stand", 3.8, point=(0.0, -250.0 * K))
    assert math.dist(_grip(doc, 3.8), socket) < GRASP_TOLERANCE_PX


def test_an_item_held_from_the_start_can_open_aimed(tmp_path):
    """``held_rotation`` beside ``held_by: <socket>``: a shot that continues another
    opens on the item already aimed (the stage angle a place's ``rotation`` would
    have left it at), grip on the socket, and it turns with the socket after."""
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [40, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 0], scale: 0.5, after: fig}, overrides: {held_by: stand@hand, held_rotation: 0.6}}
"""
    actions = "- {kind: tween, target: stand, property: rotation, from: 0.0, to: 0.3, duration: 0.5, start: 1.0}"
    doc = _compile(make_project(tmp_path / "p", scene(actions, entities=entities)))
    for t in (0.0, 0.5):
        assert _pose(doc, t)[("stick", "rotation")] == pytest.approx(0.6, abs=1e-6)
        socket = _stage(doc, "stand", t, point=(0.0, -250.0 * K))
        assert math.dist(_grip(doc, t), socket) < GRASP_TOLERANCE_PX
    assert _pose(doc, 1.8)[("stick", "rotation")] == pytest.approx(0.9, abs=1e-5)
    socket = _stage(doc, "stand", 1.8, point=(0.0, -250.0 * K))
    assert math.dist(_grip(doc, 1.8), socket) < GRASP_TOLERANCE_PX


def test_held_rotation_on_an_item_on_the_ground_is_refused(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 150], scale: 0.5, after: fig}, overrides: {held_by: ground, held_rotation: 0.6}}
"""
    actions = "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}"
    with pytest.raises(Exception, match="held_rotation aims an item"):
        _compile(make_project(tmp_path / "p", scene(actions, entities=entities)))


def test_a_swap_gives_at_the_rotation_it_is_given(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [40, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 0], scale: 0.5, after: fig}, overrides: {held_by: stand@hand}}
- {kind: prop, id: rod, store: props, ref: stick, stage: {at: [-200, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
    actions = """- {kind: grasp, by: fig/arm_l, item: rod, start: 0.2}
- {kind: swap, holder: stand@hand, take: stick, give: rod, by: fig/arm_r, start: 1.2, rotation: -0.5}"""
    doc = _compile(make_project(tmp_path / "p", scene(actions, entities=entities)))
    give = _gesture(doc, "place")
    assert give["gap"] <= GRASP_TOLERANCE_PX
    assert _pose(doc, give["contact"] + 0.5)[("rod", "rotation")] == pytest.approx(
        -0.5, abs=1e-6
    )


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


# -- draw order follows the holder (an#537) -------------------------------------------

#: What each holder in the report paints the stick just after: the part that
#: holds it, or its staged place.
_HOSTS = {"fig/arm_r": "fig/arm_r", "stand@hand": "stand/body", "ground": "", "air": ""}


def _paint_channels(doc):
    return [
        ch
        for clip in doc.animations.values()
        for ch in clip.channels
        if ch.property == "paint_after"
    ]


def test_a_held_item_draws_just_above_the_part_that_holds_it(tmp_path):
    """The acceptance of an#537: at every frame, the stick is painted just after
    the part that holds it (the hand, then the stand's socket part, then the
    hand again) and back at its staged place once it is let go, switching at
    the frame its holder changes; its transform is not what moves its paint."""
    doc = _compile(
        _project(
            tmp_path,
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}\n"
            "- {kind: place, item: stick, onto: stand@hand, start: 1.6}\n"
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 2.4}\n"
            "- {kind: release, item: stick, at: 3.4}",
        )
    )
    timeline = _holds(doc)["holders"]["stick"]
    assert [h for _t, h in timeline] == [
        "ground",
        "fig/arm_r",
        "stand@hand",
        "fig/arm_r",
        "air",
    ]
    (channel,) = _paint_channels(doc)
    assert channel.target == "stick"
    for t in _times(0.0, 4.0):
        holder = [h for at, h in timeline if round(t, 2) >= at][-1]
        assert _pose(doc, t)[("stick", "paint_after")] == _HOSTS[holder], t


def test_an_item_held_from_the_start_draws_with_its_holder_from_the_start(tmp_path):
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [40, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 0], scale: 0.5, after: fig}, overrides: {held_by: stand@hand}}
"""
    actions = "- {kind: tween, target: stand, property: rotation, from: 0.0, to: 0.3, duration: 0.5, start: 1.0}"
    doc = _compile(make_project(tmp_path / "p", scene(actions, entities=entities)))
    assert all(
        _pose(doc, t)[("stick", "paint_after")] == "stand/body"
        for t in _times(0.0, 4.0)
    )


def test_an_item_no_body_holds_keeps_its_staged_place_and_emits_nothing(tmp_path):
    """Byte identity for every shot whose items no body ever holds: no channel."""
    actions = "- {kind: tween, target: stand, property: rotation, from: 0.0, to: 0.3, duration: 0.5, start: 1.0}"
    doc = _compile(_project(tmp_path, actions))
    assert _holds(doc)["holders"]["stick"] == [[0.0, "ground"]]
    assert _paint_channels(doc) == []


# -- putting down on a body's surface (an#536) ----------------------------------------

#: The figure, the crate (its declared surface 40 units above its base) at x 20,
#: the stand (no declared surface: its ink's top) at x 160, the stick on the floor.
_SURFACE_ENTITIES = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: crate, store: props, ref: crate, stage: {at: [20, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [160, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [-160, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
_TAKE = "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.3}\n"


def _surface_project(tmp_path, actions, entities=_SURFACE_ENTITIES):
    return make_project(tmp_path / "p", scene(actions, entities=entities))


def _crate_top(doc, t):
    """The crate's declared surface at ``t``: its two ends on the stage."""
    from tests._hold_fixture import CRATE_SURFACE

    return (
        _stage(doc, "crate", t, point=(-50.0 * K, -CRATE_SURFACE * K)),
        _stage(doc, "crate", t, point=(50.0 * K, -CRATE_SURFACE * K)),
    )


def test_a_place_onto_a_surface_lays_the_item_on_it_and_it_follows_the_body(tmp_path):
    """The acceptance of an#536: ``place onto: crate@surface`` puts the stick's
    lowest painted point on the crate's declared surface (two bones, below the
    top of its ink), below the hand, at its rest angle; from then on the crate
    holds it: it moves with the crate and draws just above it."""
    actions = (
        _TAKE + "- {kind: place, item: stick, onto: crate@surface, start: 1.4}\n"
        "- {kind: tween, target: crate, property: x, from: 20, to: 120, duration: 0.5, start: 3.0}"
    )
    doc = _compile(_surface_project(tmp_path, actions))
    g = _gesture(doc, "place")
    assert g["gap"] <= GRASP_TOLERANCE_PX and g["onto"] == "crate@surface"
    assert [h for _t, h in _holds(doc)["holders"]["stick"]] == [
        "ground",
        "fig/arm_r",
        "crate@surface",
    ]
    for t in _times(g["contact"], 4.0):
        (lx, ly), (rx, _ry) = _crate_top(doc, t)
        bottom = _stage(doc, "stick", t, point=INK_BOTTOM)
        assert bottom[1] == pytest.approx(ly, abs=1e-3), (
            t
        )  # on the surface, not its box
        assert lx - 1e-3 <= bottom[0] <= rx + 1e-3, t
        assert _pose(doc, t)[("stick", "rotation")] == pytest.approx(0.0, abs=1e-6)
        assert _pose(doc, t)[("stick", "paint_after")] == "crate/body", t
    # It rides on the crate: the crate's move is the stick's.
    before, after = _stage(doc, "stick", 2.9), _stage(doc, "stick", 3.9)
    assert after[0] - before[0] == pytest.approx(100.0, abs=1e-3)
    assert after[1] == pytest.approx(before[1], abs=1e-3)


def test_an_undeclared_surface_is_the_top_of_the_ink_and_takes_a_fraction(tmp_path):
    """``stand@surface@0.5``: the stand declares no surface bones, so its
    surface is the top of its painted box; the item goes halfway along it."""
    actions = (
        _TAKE
        + "- {kind: place, item: stick, onto: stand@surface@0.5, start: 1.4, reach: 0.8}"
    )
    doc = _compile(_surface_project(tmp_path, actions))
    g = _gesture(doc, "place")
    assert g["gap"] <= GRASP_TOLERANCE_PX
    top = 200.0 - 150.0 * K  # the stand's body is 150 units tall, standing on y 200
    for t in _times(g["contact"], 4.0):
        x, y = _stage(doc, "stick", t, point=INK_BOTTOM)
        assert (x, y) == (pytest.approx(160.0, abs=1e-3), pytest.approx(top, abs=1e-3))


def test_a_tilted_surface_lays_the_item_along_it(tmp_path):
    """The crate tilted by 0.2 rad before the place: the stick lies at 0.2,
    its lowest point on the middle of the tilted surface."""
    actions = (
        "- {kind: tween, target: crate, property: rotation, from: 0.0, to: 0.2, duration: 0.2, start: 0.0}\n"
        + _TAKE
        + "- {kind: place, item: stick, onto: crate@surface@0.5, start: 1.4}"
    )
    doc = _compile(_surface_project(tmp_path, actions))
    g = _gesture(doc, "place")
    assert g["gap"] <= GRASP_TOLERANCE_PX
    t = g["contact"] + 0.5
    (lx, ly), (rx, ry) = _crate_top(doc, t)
    mid = ((lx + rx) / 2.0, (ly + ry) / 2.0)
    assert _pose(doc, t)[("stick", "rotation")] == pytest.approx(0.2, abs=1e-6)
    assert math.dist(_stage(doc, "stick", t, point=INK_BOTTOM), mid) < 1e-3


def test_an_item_can_start_on_a_surface_and_is_taken_from_it(tmp_path):
    entities = _SURFACE_ENTITIES.replace(
        "overrides: {held_by: ground}", "overrides: {held_by: crate@surface@0.25}"
    )
    doc = _compile(_surface_project(tmp_path, _TAKE, entities))
    (lx, ly), (rx, _ry) = _crate_top(doc, 0.0)
    x, y = _stage(doc, "stick", 0.0, point=INK_BOTTOM)
    assert (x, y) == (
        pytest.approx(lx + 0.25 * (rx - lx), abs=1e-3),
        pytest.approx(ly, abs=1e-3),
    )
    assert _pose(doc, 0.0)[("stick", "paint_after")] == "crate/body"
    g = _gesture(doc, "grasp")
    assert g["gap"] <= GRASP_TOLERANCE_PX
    assert _holds(doc)["holders"]["stick"] == [
        [0.0, "crate@surface@0.25"],
        [g["contact"], "fig/arm_r"],
    ]


def test_an_item_hovering_over_a_named_surface_is_called_floating(tmp_path):
    """``floating_item`` measures a staged item against the surfaces the holds
    name as well as the ground, and names the one to rest it on."""
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: crate, store: props, ref: crate, stage: {at: [20, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [20, 110], scale: 0.5, after: fig}}
"""
    actions = _TAKE + "- {kind: place, item: stick, onto: crate@surface, start: 1.4}"
    warnings_ = [
        m
        for s, m in _lint(_surface_project(tmp_path, actions, entities))
        if s == "warning"
    ]
    assert any(
        "above 'crate@surface'" in m and "held_by: crate@surface" in m
        for m in warnings_
    ), warnings_


@pytest.mark.parametrize(
    "actions, expected",
    [
        (
            _TAKE + "- {kind: place, item: stick, onto: crate@surface@2, start: 1.4}",
            "f from 0",
        ),
        (
            _TAKE + "- {kind: handover, item: stick, to: crate@surface, start: 1.4}",
            "by `place`",
        ),
        (
            _TAKE + "- {kind: release, item: stick, at: 1.4, onto: crate@surface}",
            "a release falls to the floor",
        ),
        (
            _TAKE + "- {kind: place, item: stick, onto: 'crate@surface@', start: 1.4}",
            "f from 0",
        ),
    ],
)
def test_a_surface_target_that_does_not_make_sense_is_refused(
    tmp_path, actions, expected
):
    with pytest.raises(HoldError, match=expected):
        _compile(_surface_project(tmp_path, actions))


def test_a_bone_named_surface_is_refused_as_a_reserved_name(tmp_path, monkeypatch):
    import tests._hold_fixture as fixture

    crate = dict(fixture.CRATE)
    crate["bones"] = [
        *crate["bones"],
        {"name": "surface", "parent": "root", "x": 0.0, "y": -50.0},
    ]
    monkeypatch.setattr(fixture, "CRATE", crate)
    actions = _TAKE + "- {kind: place, item: stick, onto: crate@surface, start: 1.4}"
    with pytest.raises(HoldError, match="reserved point name"):
        _compile(_surface_project(tmp_path, actions))


# -- the review of #564's follow-ups (an#565) --------------------------------------------

#: Half the width of the stick's ink (its bar is 20 of its 60 canvas units), in its node's frame.
INK_HALF_WIDTH = 10.0 * K


def test_put_below_the_hand_the_items_ink_does_not_hang_over_an_end(tmp_path):
    """The hand starts left of the crate, so "below the hand" is the crate's
    left end; the stick is moved in until its ink is all on the surface."""
    actions = _TAKE + "- {kind: place, item: stick, onto: crate@surface, start: 1.4}"
    doc = _compile(_surface_project(tmp_path, actions))
    g = _gesture(doc, "place")
    assert _hand(doc, 1.4)[0] < _crate_top(doc, 1.4)[0][0], (
        "the hand starts past the end"
    )
    t = g["contact"] + 0.3
    (lx, _ly), (rx, _ry) = _crate_top(doc, t)
    left = _stage(doc, "stick", t, point=(-INK_HALF_WIDTH, INK_BOTTOM[1]))
    right = _stage(doc, "stick", t, point=(INK_HALF_WIDTH, INK_BOTTOM[1]))
    assert lx - 1e-3 <= left[0] and right[0] <= rx + 1e-3
    assert left[0] == pytest.approx(lx, abs=1e-3), "moved in no further than needed"


def test_a_moving_surface_is_read_as_it_is_at_contact(tmp_path):
    """The crate slides right while the hand reaches: the stick goes below
    where the hand started, on the crate as it is when the stick touches it
    (not at the fraction the hand was over when it started)."""
    entities = _SURFACE_ENTITIES.replace(
        "stage: {at: [20, 200]}", "stage: {at: [-65, 200]}"
    )
    actions = (
        _TAKE
        + "- {kind: tween, target: crate, property: x, from: -65, to: -45, duration: 0.2, start: 1.4}\n"
        + "- {kind: place, item: stick, onto: crate@surface, start: 1.4}"
    )
    doc = _compile(_surface_project(tmp_path, actions, entities))
    g = _gesture(doc, "place")
    hand0 = _hand(doc, 1.4)
    (lx, _), (rx, _) = _crate_top(doc, g["contact"])
    assert lx + INK_HALF_WIDTH < hand0[0] < rx - INK_HALF_WIDTH
    x, _y = _stage(doc, "stick", g["contact"] + 0.3, point=INK_BOTTOM)
    assert x == pytest.approx(hand0[0], abs=1e-3)


def test_an_item_sunk_into_every_support_names_each_of_them(tmp_path):
    """The crate stands lower than the figure's floor and the stick is sunk
    below both: the warning names the least sunk, and the other it measured
    (it may not be the one the item was meant to rest on)."""
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: crate, store: props, ref: crate, stage: {at: [20, 300]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [20, 280], scale: 0.5, after: fig}}
"""
    actions = _TAKE.replace("start: 0.3", "start: 0.3, reach: 0.6") + (
        "- {kind: place, item: stick, onto: crate@surface, start: 1.4}"
    )
    found = [
        m
        for s, m in _lint(_surface_project(tmp_path, actions, entities))
        if "'stick' is" in m
    ]
    assert found and all(
        "px into 'crate@surface' (also" in m and "px into the ground)" in m
        for m in found
    ), found


def test_an_item_staged_on_a_surface_past_its_end_is_moved_onto_it(tmp_path):
    entities = _SURFACE_ENTITIES.replace(
        "stage: {at: [-160, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}",
        "stage: {at: [70, 150], scale: 0.5, after: fig}, overrides: {held_by: crate@surface}",
    )
    doc = _compile(_surface_project(tmp_path, _TAKE, entities))
    (_lx, _), (rx, _) = _crate_top(doc, 0.0)
    right = _stage(doc, "stick", 0.0, point=(INK_HALF_WIDTH, INK_BOTTOM[1]))
    assert right[0] == pytest.approx(rx, abs=1e-3)


def test_with_no_ground_given_the_floor_is_where_the_feet_are_not_the_reaching_arm(
    tmp_path,
):
    """No `solve.ground`: the floor is the bottom of the carrier's root parts,
    read from the solve without the gestures, so the reach that bends the
    figure does not drop it. The stick laid flat on it lies on y 200, where
    the figure stands."""
    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [-160, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
    actions = _TAKE + (
        "- {kind: place, item: stick, onto: ground@-40, rotation: 1.5708, start: 1.4}"
    )
    doc = _compile(
        make_project(
            tmp_path / "p", scene(actions, entities=entities, shot="duration: 4.0")
        )
    )
    g = _gesture(doc, "place")
    assert g["gap"] <= GRASP_TOLERANCE_PX
    t = g["contact"] + 0.5
    lowest = max(
        _stage(doc, "stick", t, point=(x * K, y * K))[1]
        for x in (-10.0, 10.0)
        for y in (-100.0, 100.0)
    )
    assert lowest == pytest.approx(GROUND, abs=1e-3)


def test_the_floor_is_where_the_figure_stands_not_its_lowest_part(tmp_path):
    """an#601: no `solve.ground`, and the figure's left arm hangs below its
    feet. The figure is placed by its declared `origin` (its feet), so the
    floor is that line, and the stick laid flat lands on y 200, not on the
    hanging hand."""
    import json as _json

    from tests._hold_fixture import _svg

    entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [-160, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
    actions = _TAKE + (
        "- {kind: place, item: stick, onto: ground@-40, rotation: 1.5708, start: 1.4}"
    )
    root = tmp_path / "p"
    make_project(root, scene(actions, entities=entities, shot="duration: 4.0"))
    figure = root / "assets" / "props" / "figure"
    doc = _json.loads((figure / "prop.json").read_text(encoding="utf-8"))
    doc["skins"]["default"]["slots"]["arm_l"]["arm"]["path"] = "parts/long_arm.svg"
    (figure / "prop.json").write_text(_json.dumps(doc), encoding="utf-8")
    # hung 140 units above the feet, 300 long: its hand 160 units below them
    (figure / "parts" / "long_arm.svg").write_text(
        _svg(16, 300, "#2f6f9f"), encoding="utf-8"
    )
    from an.project import load

    doc = _compile(load(root))
    hand_l = _stage(doc, "fig/arm_l", 0.0, point=(0.0, 300.0 * K * (1.0 - 0.04)))
    assert hand_l[1] > GROUND + 10, "the left hand hangs below the feet"
    g = _gesture(doc, "place")
    t = g["contact"] + 0.5
    lowest = max(
        _stage(doc, "stick", t, point=(x * K, y * K))[1]
        for x in (-10.0, 10.0)
        for y in (-100.0, 100.0)
    )
    assert lowest == pytest.approx(GROUND, abs=1e-3)


def test_a_rig_placed_by_its_middle_is_not_standing_on_it(tmp_path):
    """an#601 review: an `origin` above a bone is where a rig is placed, not
    what it stands on. A stand placed by its middle lets go of the stick with
    no `solve.ground`: the stick falls to the stand's base, not its middle."""
    import json as _json

    from an.project import load

    entities = """- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [160, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [160, 100], scale: 0.5, after: stand}, overrides: {held_by: stand@hand}}
"""
    actions = "- {kind: release, item: stick, at: 1.0}"
    root = tmp_path / "p"
    make_project(root, scene(actions, entities=entities, shot="duration: 3.0"))
    stand = root / "assets" / "props" / "stand"
    doc = _json.loads((stand / "prop.json").read_text(encoding="utf-8"))
    doc["origin"] = [200.0, 325.0]  # 75 units above its foot
    (stand / "prop.json").write_text(_json.dumps(doc), encoding="utf-8")
    doc = _compile(load(root))
    base = 200.0 + 75.0 * K
    lowest = _stage(doc, "stick", 2.9, point=INK_BOTTOM)[1]
    assert lowest == pytest.approx(base, abs=1.0), lowest
