"""``topple``: a rigid body falling over about its foot, knocking the next (:mod:`an.stage.topple`).

The scene this was built for (the user, 2026-11-10): "he trips over one of the
camera's legs, which then falls on Napoleon, who tips over, his sword ending up
gouging the right eye of Hannibal". Here: stands from the hold fixture (a box
80 x 150 units with a socket above it, holding the stick sideways).
"""

from __future__ import annotations

import math
import warnings

import pytest

from tests._hold_fixture import K, make_project, scene

from an.stage.compile import compile_shot
from an.stage.timeline import evaluate_timeline, screen_position, timeline_from_scene
from an.stage.topple import ToppleError

W, H = 640, 480
FLOOR = 200.0
#: The stand's box, in its node's frame (80 x 150 units, anchored at its foot).
BOX = [(sx * 40.0 * K, -sy * 150.0 * K) for sx in (-1, 1) for sy in (0, 1)]


def _entities(*, b_at=60.0, stick=True):
    lines = [
        "- {kind: prop, id: a, store: props, ref: stand, stage: {at: [-100, 200]}}",
        f"- {{kind: prop, id: b, store: props, ref: stand, stage: {{at: [{b_at}, 200]}}}}",
    ]
    if stick:
        lines.append(
            "- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [-100, 0], scale: 0.5, after: a}, overrides: {held_by: a@hand}}"
        )
    return "\n".join(lines) + "\n"


def _compile(tmp_path, actions, **kw):
    project = make_project(
        tmp_path / "p", scene(actions, entities=_entities(**kw), shot="duration: 4.0\nsolve: {ground: 200}")
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(project.scene.timeline[0], project.mall, fps=24, width=W, height=H)


def _stage(doc, path, t, point=(0.0, 0.0)):
    pose = evaluate_timeline(timeline_from_scene(doc), t)
    x, y = screen_position(doc, path, pose=pose, point=point)
    return (x - W / 2.0, y - H / 2.0)


def _events(doc):
    return [(e["event"], e["item"]) for e in doc.meta.extensions["topple"]["events"]]


def test_a_pushed_stand_falls_onto_its_side_and_carries_what_it_holds(tmp_path):
    doc = _compile(tmp_path, "- {kind: topple, body: a, toward: right, push: 3.0, start: 0.5}")
    assert _events(doc)[0] == ("topple", "a") and ("land", "a") in _events(doc)
    rot = evaluate_timeline(timeline_from_scene(doc), 3.9)[("a", "rotation")]
    assert rot == pytest.approx(math.pi / 2, abs=0.03)  # on its right side
    lowest = max(_stage(doc, "a", 3.9, point=c)[1] for c in BOX)
    assert lowest == pytest.approx(FLOOR, abs=1.5)
    # Before it starts it has not moved; the stick in its socket turns with it.
    assert _stage(doc, "a", 0.4) == pytest.approx((-100.0, 200.0), abs=1e-3)
    def heading(t):
        (x0, y0), (x1, y1) = _stage(doc, "stick", t), _stage(doc, "stick", t, point=(0.0, 10.0))
        return math.atan2(y1 - y0, x1 - x0)

    assert math.remainder(heading(3.9) - heading(0.4), 2 * math.pi) == pytest.approx(rot, abs=0.03)


def test_a_push_too_weak_to_tip_it_is_refused_with_the_push_it_needs(tmp_path):
    with pytest.raises(ToppleError, match=r"rocks back.*`push:` at least"):
        _compile(tmp_path, "- {kind: topple, body: a, toward: right, push: 0.2, start: 0.5}")


def test_one_body_knocks_the_next_over_when_it_reaches_it(tmp_path):
    doc = _compile(
        tmp_path,
        "- {kind: topple, id: first, body: a, toward: right, push: 3.0, start: 0.5}\n"
        "- {kind: topple, body: b, toward: right, after: first, knock: 1.5}",
    )
    events = doc.meta.extensions["topple"]["events"]
    hit = next(e for e in events if e["event"] == "hit")
    start_b = next(e for e in events if e["event"] == "topple" and e["item"] == "b")
    assert hit["on"] == "b" and start_b["at"] == pytest.approx(hit["at"])
    assert evaluate_timeline(timeline_from_scene(doc), 3.9)[("b", "rotation")] > 1.0


def test_a_knocked_body_out_of_reach_says_how_close_it_came(tmp_path):
    with pytest.raises(ToppleError, match="never touches"):
        _compile(
            tmp_path,
            "- {kind: topple, id: first, body: a, toward: right, push: 3.0, start: 0.5}\n"
            "- {kind: topple, body: b, toward: right, after: first}",
            b_at=400.0,
        )


def test_a_point_stops_on_its_target_or_the_body_is_told_where_to_stand(tmp_path):
    # The top right corner of a's box sweeps a circle about its right foot (x -100 + 40K, y 200).
    foot = (-100.0 + 40.0 * K, FLOOR)
    corner = (-100.0 + 40.0 * K, FLOOR - 150.0 * K)
    radius = math.hypot(corner[0] - foot[0], corner[1] - foot[1])
    angle = math.radians(50.0)
    target = (foot[0] + radius * math.sin(angle), foot[1] - radius * math.cos(angle))
    doc = _compile(
        tmp_path,
        "- {kind: topple, body: a, toward: right, push: 3.0, start: 0.5, "
        f"point: 'a@1.0,0.0', until: 'world@{target[0]:.3f},{target[1]:.3f}'}}",
        stick=False,
    )
    assert ("pin", "a") in _events(doc)
    tip = _stage(doc, "a", 3.9, point=BOX[3])
    assert tip == pytest.approx(target, abs=1.0)
    with pytest.raises(ToppleError, match=r"Move 'a' about \d+ px"):
        _compile(
            tmp_path / "off",
            "- {kind: topple, body: a, toward: right, push: 3.0, start: 0.5, "
            f"point: 'a@1.0,0.0', until: 'world@{target[0] + 30:.3f},{target[1]:.3f}'}}",
            stick=False,
        )
