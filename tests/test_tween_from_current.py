"""A tween with no ``from`` starts from the value its property HAS at that
moment (an#212) — on the compiled document, where the runtime reads it.

Before an#212 it started from the property's identity (``0`` for ``x``/``y``/
``rotation``, ``1`` for scales and ``alpha``), whatever the entity's stage
placement or the motion before it: the first step of a hand-built walk bob
jumped ~120 px, and ``examples/walk_demo``'s torso rock snapped back to ``0``
every half second. The start is now read off the flat timeline the way the
runtime evaluates it (``_value_at``): the built transform (the ``stage``
placement), overridden by the ``set``s and tweens before it on the same
(target, property) — an active tween governs, otherwise the latest write holds.
Motion presets played by name read the same pose at their start.
"""

from __future__ import annotations

import warnings

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.ir.compose import delay, play, sequence, set_
from an.ir.compose import tween as _tween
from an.ir.schema import AssetRef, Shot, StagePlacement
from an.motion import rest_pose


def tween(target, prop, *, to, duration, start=0.0, **kw):
    """``an.ir.compose.tween`` placed at ``start`` (the parser's own wrapper)."""
    leaf = _tween(target, prop, to, duration, **kw)
    return sequence(delay(start), leaf) if start else leaf


def _char(name: str, **stage) -> AssetRef:
    return AssetRef(
        kind="character",
        id=name,
        store="characters",
        ref=name,
        **({"stage": StagePlacement(**stage)} if stage else {}),
    )


def _shot(actions, *, entities=None, duration=4.0) -> Shot:
    return Shot(
        id="s",
        duration=duration,
        entities=entities or [_char("c")],
        actions=list(actions),
    )


def _compile(shot, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the stand-in-rig warning
        return compile_shot(shot, None, **kw)


def _starts(scene, target, prop):
    """Every compiled tween channel on (target, prop): (first value, last value)."""
    return [
        (ch.keyframes[0].value, ch.keyframes[-1].value)
        for aid, a in scene.animations.items()
        if aid.startswith("__tween__")
        for ch in a.channels
        if (ch.target, ch.property) == (target, prop)
    ]


def _at(scene, t, target, prop):
    return evaluate_timeline(timeline_from_scene(scene), t).get((target, prop))


def test_a_from_less_tween_starts_at_the_stage_placement():
    """The evidence: an entity staged at y=120, bobbed with ``to`` only."""
    shot = _shot(
        [tween("c", "y", to=110.0, duration=0.2)],
        entities=[_char("c", at=(-300.0, 120.0))],
    )
    y0 = rest_pose(shot, "c")["y"]
    assert y0 != 0.0  # the placement is not the identity, or this proves nothing
    scene = _compile(shot)
    assert _starts(scene, "c", "y") == [(y0, 110.0)]
    # …so the frame the tween starts on shows the entity where it stood.
    assert _at(scene, 0.0, "c", "y") == pytest.approx(y0)


def test_the_laid_out_x_of_a_second_character():
    """No ``stage`` at all: the compiler's own layout (``-110``/``110``)."""
    shot = _shot(
        [tween("b", "x", to=300.0, duration=1.0)],
        entities=[_char("a"), _char("b")],
    )
    assert _starts(_compile(shot), "b", "x") == [(110.0, 300.0)]


def test_a_set_at_the_same_instant_is_where_the_tween_starts():
    """"Put him off-screen, then walk him in": set then tween at t=0."""
    shot = _shot([set_("c", "x", -800.0), tween("c", "x", to=0.0, duration=2.0)])
    assert _starts(_compile(shot), "c", "x") == [(-800.0, 0.0)]


def test_a_chain_of_from_less_tweens_is_continuous():
    """``examples/walk_demo``'s rock: each tween continues from the last."""
    shot = _shot(
        [
            tween("c/torso", "rotation", to=0.05, duration=0.5, from_=-0.05),
            tween("c/torso", "rotation", to=-0.05, duration=0.5, start=0.5),
            tween("c/torso", "rotation", to=0.05, duration=0.5, start=1.0),
        ]
    )
    assert _starts(_compile(shot), "c/torso", "rotation") == [
        (-0.05, 0.05),
        (0.05, -0.05),
        (-0.05, 0.05),
    ]


def test_a_tween_starting_inside_another_starts_from_its_current_value():
    shot = _shot(
        [
            tween("c", "x", to=100.0, duration=2.0, from_=0.0, easing="linear"),
            tween("c", "x", to=0.0, duration=1.0, start=1.0),
        ]
    )
    scene = _compile(shot)
    assert _starts(scene, "c", "x")[1] == (pytest.approx(50.0), 0.0)
    # No jump at the handoff: the later tween governs from where the first was.
    assert _at(scene, 1.0, "c", "x") == pytest.approx(50.0)


def test_a_set_after_an_ended_tween_wins():
    shot = _shot(
        [
            tween("c", "x", to=100.0, duration=1.0, from_=0.0),
            set_("c", "x", 40.0, at=1.5),
            tween("c", "x", to=0.0, duration=1.0, start=2.0),
        ]
    )
    assert _starts(_compile(shot), "c", "x")[1] == (40.0, 0.0)


def test_the_start_is_the_stepped_value_under_step_hz():
    """Under ``step_hz`` the runtime shows the STEPPED curve, so a tween that
    starts mid-way through another starts from the value on screen."""
    first = tween("c", "x", to=100.0, duration=1.0, from_=0.0, easing="linear")
    shot = _shot([first, tween("c", "x", to=0.0, duration=1.0, start=0.55)])
    smooth = _starts(_compile(shot), "c", "x")[1][0]
    stepped_scene = _compile(shot, step_hz=10)
    stepped = _starts(stepped_scene, "c", "x")[1][0]
    assert smooth == pytest.approx(55.0)
    assert stepped == pytest.approx(50.0)  # held since the 0.5 s grid point
    assert stepped == pytest.approx(_at(stepped_scene, 0.549, "c", "x"))


def test_a_from_less_tint_tween_starts_from_the_tint_in_force():
    shot = _shot(
        [set_("c", "tint", "#ff0000"), tween("c", "tint", to="#ffffff", duration=1.0, start=1.0)]
    )
    scene = _compile(shot)
    assert _starts(scene, "c", "tint_g") == [(0.0, 1.0)]
    assert _starts(scene, "c", "tint_r") == [(1.0, 1.0)]


def test_a_preset_played_after_a_move_starts_where_the_move_left_it():
    """``hop`` after a ``set`` of ``y``: it hops from there and lands there."""
    shot = _shot([set_("c", "y", 40.0), sequence(delay(1.0), play("c", "hop"))])
    scene = _compile(shot)
    assert _starts(scene, "c", "y") == [(40.0, 0.0), (0.0, 40.0)]
    assert _at(scene, 2.0, "c", "y") == pytest.approx(40.0)


def test_an_explicit_from_is_kept():
    shot = _shot([set_("c", "x", -800.0), tween("c", "x", to=0.0, duration=1.0, from_=5.0)])
    assert _starts(_compile(shot), "c", "x") == [(5.0, 0.0)]


def test_a_from_less_tween_on_a_swap_set_still_raises():
    """No numeric start exists for a key, so nothing is invented (unchanged)."""
    with pytest.raises(CutoutCompileError, match="no from_value"):
        _compile(_shot([tween("c/head/mouth", "viseme", to="A", duration=0.2)]))
