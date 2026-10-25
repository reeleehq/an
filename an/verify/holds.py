"""The hold checks: what ``an validate`` says about a shot's holds (an#502, catalogue A1 and A4).

Three constraints on the one interface (:class:`an.verify.constraints.Constraint`),
over the compiled shot (the hold layer, :mod:`an.stage.hold`, records what it
did in ``meta.extensions.solve.holds``):

- ``hold_conflict`` (error): the holds do not add up: a hand puts down what
  it does not hold, a socket gets a second item, one hand does two things at
  once, a verb names an item that is not in the shot;
- ``unreachable_hold`` (error): a hand does not arrive where it takes or puts
  its item (even bending as far as its ``lean`` allows), with how far it
  stays short and which way to move the carrier;
- ``floating_item`` (warning): an item that a hand takes from the floor
  hovers above it (or sinks into it) before it is taken, and a released item
  with no ground below it or no gravity, that stays in the air.

All three are silent for a shot that holds nothing.

>>> [c.name for c in HOLD_CONSTRAINTS]
['hold_conflict', 'unreachable_hold', 'floating_item']
"""

from __future__ import annotations

import math
from typing import Any

from an.genres.registry import CORE_OWNER, check_names, register_check
from an.verify.constraints import Constraint

__all__ = ["HOLD_CONSTRAINTS", "HOLD_CONFLICT", "UNREACHABLE_HOLD", "FLOATING_ITEM"]

#: Where the hold checks run within a shot: with the joint checks (250).
HOLD_CHECK_ORDER: float = 255.0


def _declares(ctx: Any) -> bool:
    from an.stage.hold import declares_holds

    return declares_holds(ctx.shot)


def _holds(ctx: Any) -> tuple[dict[str, Any] | None, Exception | None]:
    from an.verify.joints import _compiled, _report

    doc, error = _compiled(ctx)
    if doc is None:
        return None, error
    return _report(doc).get("holds"), None


def check_hold_conflict(ctx: Any) -> None:
    """The holds of the shot add up (what holds each item, and when, is one story)."""
    if not _declares(ctx):
        return
    from an.stage.hold import HoldError

    _report, error = _holds(ctx)
    if isinstance(error, HoldError):
        for where, message in error.problems:
            ctx.report.add("error", f"{ctx.path}/{where}", message)


HOLD_CONFLICT = Constraint(
    "hold_conflict",
    check_hold_conflict,
    order=HOLD_CHECK_ORDER,
    description="what holds each item, and when, adds up (grasp, place, release, handover, swap)",
)


def _move_hint(gesture: dict[str, Any]) -> str:
    goal, hand = gesture.get("goal"), gesture.get("hand")
    carrier = gesture.get("carrier") or "the carrier"
    if not goal or not hand:
        return f"move {carrier} closer"
    dx, dy = goal[0] - hand[0], goal[1] - hand[1]
    if abs(dx) >= abs(dy):
        side = "right" if dx > 0 else "left"
        return f"move {carrier} about {abs(dx):.0f} px to the {side} (its `stage.at` x, or a longer walk), so the goal is at arm's length"
    if dy > 0:
        return (
            f"the goal is {dy:.0f} px lower than the hand gets: put {gesture.get('item')!r} higher "
            f"(on something), or let {carrier} bend further (`lean`, now {gesture.get('lean_cap', 0):g}°)"
        )
    return f"the goal is {-dy:.0f} px higher than the hand gets: put it lower, or move {carrier} closer"


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def check_unreachable_hold(ctx: Any) -> None:
    """Every hand arrives where it takes or puts its item."""
    if not _declares(ctx):
        return
    from an.stage.hold import GRASP_TOLERANCE_PX

    report, _error = _holds(ctx)
    if not report:
        return
    for g in report.get("gestures") or ():
        gap = float(g.get("gap") or 0.0)
        if gap <= GRASP_TOLERANCE_PX or not math.isfinite(gap):
            continue
        what = {
            "grasp": f"reach {g['item']!r}",
            "take": f"take {g['item']!r}",
            "give": f"give {g['item']!r}",
            "place": f"put {g['item']!r} on {g.get('onto')!r}",
        }.get(g["kind"], g["kind"])
        lean = f", bent {g['lean']:g}°" if g.get("lean") else ""
        ctx.report.add(
            "error",
            f"{ctx.path}/{g['where']}",
            f"{g['by']!r} cannot {what} at {g['contact']:.2f} s: it stays {gap:.1f} px short{lean}, "
            f"so the item changes hands that far from the hand. {_capital(_move_hint(g))}.",
        )


UNREACHABLE_HOLD = Constraint(
    "unreachable_hold",
    check_unreachable_hold,
    order=HOLD_CHECK_ORDER,
    description="a hand arrives where it takes or puts its item (an#502)",
)


def check_floating_item(ctx: Any) -> None:
    """An item taken from the floor lies on it; a released item comes down."""
    if not _declares(ctx):
        return
    report, _error = _holds(ctx)
    if not report:
        return
    for f in report.get("floating") or ():
        how = (
            f"{f['above']:.0f} px above the ground (y {f['ground']:g})"
            if f["above"] > 0
            else f"{-f['above']:.0f} px into the ground (y {f['ground']:g})"
        )
        ctx.report.add(
            "warning",
            f"{ctx.path}/{f['where']}",
            f"{f['item']!r} is {how} when it is taken at {f['at']:.2f} s. If it lies on the "
            f"floor, say so: `overrides: {{held_by: ground}}` on {f['item']!r} puts its lowest "
            "point on the ground.",
        )
    for w in report.get("warnings") or ():
        ctx.report.add("warning", f"{ctx.path}/actions", w["message"] + ".")


FLOATING_ITEM = Constraint(
    "floating_item",
    check_floating_item,
    order=HOLD_CHECK_ORDER,
    description="an item taken from the floor lies on it, and a released item comes down (catalogue A1)",
)

#: The hold checks, in the order they run.
HOLD_CONSTRAINTS: tuple[Constraint, ...] = (
    HOLD_CONFLICT,
    UNREACHABLE_HOLD,
    FLOATING_ITEM,
)


def _register() -> None:
    for constraint in HOLD_CONSTRAINTS:
        if constraint.name not in check_names(owner=CORE_OWNER):
            register_check(constraint.semantic_check(), owner=CORE_OWNER)


_register()
