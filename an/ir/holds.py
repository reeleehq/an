"""Holding things: ``grasp``, ``place``, ``release``, ``handover`` and ``swap`` (an#502, catalogue A4).

A **hold** says what carries an item over a span of a shot: a hand (any point
of a body), a socket of another body (a figurine's hand), the ground, a point
of the stage, or nothing (it is in flight). These five action kinds change
holds, and each one moves the holder the way a hand would, so the change
reads as handled rather than teleported:

- ``grasp``: the holder's point (``by``) **reaches** the item's grip over
  ``reach`` seconds, takes it at the instant it arrives (the item keeps the
  pose it has at that instant: no slide, no jump), and **retracts** to where
  the shot would have it over ``retract`` seconds, carrying it. The item is
  taken from whatever held it: the ground, a socket, another hand (a
  hand-over between two hands is the receiver's ``grasp``).
- ``place``: the hand that holds the item brings it ``onto`` a target over
  ``reach`` seconds (its contact point onto the ground at floor height, its
  grip into a socket, aligned with the socket's frame), lets it go there, and
  retracts empty.
- ``release``: the hand lets go at ``at``; the item falls under gravity with
  the velocity it had and lands on the ground at its rest angle, or is tossed
  ``onto: ground@x`` on an arc of height ``arc``.
- ``handover``: ``place`` into another holder's point (``to``), or, with
  ``meet`` below 1, both hands reach toward each other and the receiver takes
  it where they meet.
- ``swap``: a hand takes the item a holder has (``take``) and the hand
  holding another item gives it in its place (``give``), a beat later.

A reach that cannot arrive is never cheated: the body it hangs from may bend
(``lean``, degrees; the chain's root turns about its own pivot, the way a
figure bends at the hip), and beyond that ``an validate`` says how far the
hand stays short and where to stand instead.

None of these makes a clip: the ``solve`` compile pass reads them
(:mod:`an.stage.hold`) and emits the holders' and the items' keys.

>>> from an.ir.compose import flatten, sequence, delay
>>> [(f.start, f.end, f.action.kind) for f in flatten(sequence(delay(1.0), grasp("paul/arm_r", "cup")))]
[(1.0, 1.75, 'grasp')]
>>> [(f.start, f.action.kind) for f in flatten(sequence(delay(2.0), release("cup", at=0.5)))]
[(2.5, 'release')]
>>> [(round(f.start, 2), f.action.kind) for f in flatten(swap("nap/hand", take="musket", give="sword", by="stu@hand_r"))]
[(0.0, 'grasp'), (0.25, 'place')]

These kinds are the core's (ADR 0001's test: a robot arm putting a box on a
shelf needs them without saying character), registered when :mod:`an.ir` loads.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from an.base import Seconds
from an.genres.registry import CORE_OWNER, ActionKind, action_kind, register_action_kind
from an.ir.schema import ExtensionAction

__all__ = [
    "GraspAction",
    "PlaceAction",
    "ReleaseAction",
    "HandoverAction",
    "SwapAction",
    "HOLD_ACTION_KINDS",
    "GESTURE_KINDS",
    "GROUND",
    "SURFACE",
    "DFLT_REACH",
    "DFLT_RETRACT",
    "DFLT_LEAN_DEG",
    "DFLT_TOSS_ARC",
    "DFLT_SWAP_LAG",
    "grasp",
    "place",
    "release",
    "handover",
    "swap",
]

#: How long a hand takes to reach what it takes or where it puts it (s): a
#: deliberate reach at arm's length, about two thirds of a second there and back.
DFLT_REACH: Seconds = 0.4
#: How long the hand takes to come back to where the shot has it (s).
DFLT_RETRACT: Seconds = 0.35
#: How far the body a hand hangs from may turn to reach (degrees): a figure
#: bent well over at the hip. ``0`` never bends.
DFLT_LEAN_DEG: float = 60.0
#: How high a toss rises above the higher of its two ends (scene px).
DFLT_TOSS_ARC: float = 40.0
#: In a ``swap``, how long after the taking hand starts the giving hand starts
#: (s): it arrives a beat after the socket is empty.
DFLT_SWAP_LAG: Seconds = 0.25
#: The name of the floor in a target (``ground``, ``ground@x``).
GROUND: str = "ground"
#: The point name of a body's supporting surface in a target (an#536):
#: ``crate@surface`` (below the hand), ``crate@surface@0.3`` (that fraction of
#: the way along it), as on the ground but on the body's top, following it.
SURFACE: str = "surface"

#: The kinds' names.
HOLD_ACTION_KINDS: tuple[str, ...] = ("grasp", "place", "release", "handover", "swap")
#: The kinds that move a hand (a reach and a retract), as flattened leaves.
GESTURE_KINDS: tuple[str, ...] = ("grasp", "place", "handover")

_Reach = Field(default=DFLT_REACH, gt=0, allow_inf_nan=False)
_Retract = Field(default=DFLT_RETRACT, gt=0, allow_inf_nan=False)
_Lean = Field(default=DFLT_LEAN_DEG, ge=0, le=180, allow_inf_nan=False)


class GraspAction(ExtensionAction):
    """``by`` (a body's point: a hand) reaches ``item``'s grip and takes it.

    ``item`` is an entity id, with ``@<point>`` the grip (a bone of its rig,
    or ``u,v`` a fraction of its drawing); unset: its ``grip`` bone, else its
    stage point. ``by`` with no ``@`` is the far end of the body (an arm's
    hand). The item is held from ``start + reach`` on, and over the retract it
    turns to how the hand holds things (``align``): drawn as it is, upright
    along the hand's part, the way a socket holds it; ``align: false`` keeps
    the angle it was taken at.

    >>> GraspAction(by="stu@hand_r", item="musket").reach == DFLT_REACH
    True
    """

    kind: Literal["grasp"] = "grasp"
    by: str
    item: str
    reach: Seconds = _Reach
    retract: Seconds = _Retract
    lean: float = _Lean
    align: bool = True


class PlaceAction(ExtensionAction):
    """The hand holding ``item`` puts it ``onto`` a target and lets it go.

    ``onto`` is ``ground`` (straight down, at floor height), ``ground@x`` (at
    stage ``x``), a body's point (a socket: the item's grip goes there, its
    frame aligned with the socket's), a body's surface (``crate@surface``, or
    ``crate@surface@f`` at that fraction along it: lying on its top as on the
    ground, held by that body from then on, an#536) or ``world@x,y`` (hung on
    a point).
    ``item@<point>`` names the item's point that touches the target (default:
    its grip on a socket, its lowest point on the ground). ``rotation``: the
    item's rotation where it rests (radians, the stage's; on a surface, relative
    to the surface, whose tilt is added; default: the angle it last rested at,
    else the nearest quarter turn; in a socket, the socket's own). In a socket
    it is the angle the item comes to rest at (a musket aimed at someone, a
    sabre raised), held relative to the socket
    from then on, so it turns with it.

    >>> PlaceAction(item="musket", onto="nap/arm_r/weapon").by is None
    True
    """

    kind: Literal["place"] = "place"
    item: str
    onto: str
    by: str | None = None
    rotation: float | None = Field(default=None, allow_inf_nan=False)
    reach: Seconds = _Reach
    retract: Seconds = _Retract
    lean: float = _Lean


class ReleaseAction(ExtensionAction):
    """The hand holding ``item`` lets it go at ``at``: it falls with the
    velocity it had onto the ground, or is tossed ``onto: ground@x`` on an
    arc ``arc`` px high, and lands at ``rotation`` (default: as in ``place``).

    >>> ReleaseAction(item="cup", at=1.0).onto is None
    True
    """

    kind: Literal["release"] = "release"
    item: str
    at: Seconds = 0.0
    onto: str | None = None
    arc: float = Field(default=DFLT_TOSS_ARC, ge=0, allow_inf_nan=False)
    rotation: float | None = Field(default=None, allow_inf_nan=False)


class HandoverAction(ExtensionAction):
    """The hand holding ``item`` gives it to ``to`` (a hand, or a socket).

    ``meet`` is where the two meet, as a fraction of the way from the giver's
    hand to the receiver's: ``1`` (the default) puts it into the receiver's
    point, which does not move (a figurine's hand, a waiting hand); below 1
    both hands reach and the receiver takes it where they meet (and turns it
    as a ``grasp`` does, ``align``).

    >>> HandoverAction(item="sword", to="nap/arm_r/weapon").meet
    1.0
    """

    kind: Literal["handover"] = "handover"
    item: str
    to: str
    by: str | None = None
    meet: float = Field(default=1.0, gt=0, le=1, allow_inf_nan=False)
    reach: Seconds = _Reach
    retract: Seconds = _Retract
    lean: float = _Lean
    align: bool = True


class SwapAction(ExtensionAction):
    """``by`` takes ``take`` from ``holder`` and the hand holding ``give``
    puts that there, ``lag`` seconds later: a ``grasp`` and a ``place``.
    ``rotation`` is the place's: the angle ``give`` comes to rest at in the
    holder (radians, the stage's; default: the holder's own).

    >>> SwapAction(holder="nap/hand", take="musket", give="sword", by="stu@hand_r").lag == DFLT_SWAP_LAG
    True
    """

    kind: Literal["swap"] = "swap"
    holder: str
    take: str
    give: str
    by: str
    lag: Seconds = Field(default=DFLT_SWAP_LAG, gt=0, allow_inf_nan=False)
    rotation: float | None = Field(default=None, allow_inf_nan=False)
    reach: Seconds = _Reach
    retract: Seconds = _Retract
    lean: float = _Lean
    align: bool = True


# -----------------------------------------------------------------------------
# Builders (the fluent spelling, beside `an.ir.compose`'s)
# -----------------------------------------------------------------------------


def grasp(
    by: str,
    item: str,
    *,
    reach: Seconds = DFLT_REACH,
    retract: Seconds = DFLT_RETRACT,
    lean: float = DFLT_LEAN_DEG,
    align: bool = True,
) -> GraspAction:
    """``by`` takes ``item``.

    >>> grasp("stu@hand_r", "musket@grip").item
    'musket@grip'
    """
    return GraspAction(
        by=by, item=item, reach=reach, retract=retract, lean=lean, align=align
    )


def place(
    item: str,
    onto: str,
    *,
    by: str | None = None,
    rotation: float | None = None,
    reach: Seconds = DFLT_REACH,
    retract: Seconds = DFLT_RETRACT,
    lean: float = DFLT_LEAN_DEG,
) -> PlaceAction:
    """The hand holding ``item`` puts it ``onto`` a target.

    >>> place("book", "ground@-860").onto
    'ground@-860'
    """
    return PlaceAction(
        item=item,
        onto=onto,
        by=by,
        rotation=rotation,
        reach=reach,
        retract=retract,
        lean=lean,
    )


def release(
    item: str,
    *,
    at: Seconds = 0.0,
    onto: str | None = None,
    arc: float = DFLT_TOSS_ARC,
    rotation: float | None = None,
) -> ReleaseAction:
    """Let ``item`` go at ``at`` (a drop, or a toss ``onto: ground@x``).

    >>> release("musket", onto="ground@-620", arc=60).arc
    60.0
    """
    return ReleaseAction(item=item, at=at, onto=onto, arc=arc, rotation=rotation)


def handover(
    item: str,
    to: str,
    *,
    by: str | None = None,
    meet: float = 1.0,
    reach: Seconds = DFLT_REACH,
    retract: Seconds = DFLT_RETRACT,
    lean: float = DFLT_LEAN_DEG,
    align: bool = True,
) -> HandoverAction:
    """Give ``item`` to ``to``.

    >>> handover("cup", "jo@hand_l", meet=0.5).meet
    0.5
    """
    return HandoverAction(
        item=item,
        to=to,
        by=by,
        meet=meet,
        reach=reach,
        retract=retract,
        lean=lean,
        align=align,
    )


def swap(
    holder: str,
    *,
    take: str,
    give: str,
    by: str,
    lag: Seconds = DFLT_SWAP_LAG,
    rotation: float | None = None,
    reach: Seconds = DFLT_REACH,
    retract: Seconds = DFLT_RETRACT,
    lean: float = DFLT_LEAN_DEG,
    align: bool = True,
) -> SwapAction:
    """``by`` takes ``take`` from ``holder``; ``give`` goes there in its place.

    >>> swap("nap/hand", take="musket", give="sword", by="stu@hand_r").give
    'sword'
    """
    return SwapAction(
        holder=holder,
        take=take,
        give=give,
        by=by,
        lag=lag,
        rotation=rotation,
        reach=reach,
        retract=retract,
        lean=lean,
        align=align,
    )


# -----------------------------------------------------------------------------
# Registration: durations, the swap's two leaves, scene.md forms, the lowering
# -----------------------------------------------------------------------------


def _gesture_length(action: Any, _extent: Any = None) -> Seconds:
    return float(action.reach) + float(action.retract)


def _flatten_release(action: Any, t: Seconds, ctx: Any) -> Seconds:
    """``release`` is an instant at ``t + at`` and advances nothing (``set``'s rule)."""
    ctx.emit(t + action.at, t + action.at, action)
    return t


def swap_leaves(action: SwapAction) -> tuple[GraspAction, PlaceAction]:
    """The ``grasp`` and the ``place`` a swap is, and the second one's delay.

    >>> take, give = swap_leaves(SwapAction(holder="nap/hand", take="m", give="s", by="stu@hand_r"))
    >>> (take.item, take.by, give.item, give.onto)
    ('m', 'stu@hand_r', 's', 'nap/hand')
    """
    common = dict(reach=action.reach, retract=action.retract, lean=action.lean)
    return (
        GraspAction(by=action.by, item=action.take, align=action.align, **common),
        PlaceAction(
            item=action.give, onto=action.holder, rotation=action.rotation, **common
        ),
    )


def _flatten_swap(action: Any, t: Seconds, ctx: Any) -> Seconds:
    take, give = swap_leaves(action)
    length = _gesture_length(action)
    ctx.emit(t, t + length, take)
    ctx.emit(t + action.lag, t + action.lag + length, give)
    return t + action.lag + length


def _read_md(model: type) -> Any:
    def read(item: dict[str, Any], *, index: int) -> Any:
        from an.ir.sync import SceneMarkdownError

        try:
            return model.model_validate(item)
        except ValueError as e:
            raise SceneMarkdownError(
                f"actions[{index}] ({item.get('kind')}): {e}"
            ) from e

    return read


#: Fields left out of a ``scene.md`` entry when they hold their default.
_DEFAULTS: dict[str, Any] = {
    "reach": DFLT_REACH,
    "retract": DFLT_RETRACT,
    "lean": DFLT_LEAN_DEG,
    "arc": DFLT_TOSS_ARC,
    "lag": DFLT_SWAP_LAG,
    "meet": 1.0,
    "at": 0.0,
    "align": True,
}


def _write_md(action: Any) -> dict[str, Any]:
    entry = action.model_dump(exclude_none=True)
    for key, default in _DEFAULTS.items():
        if key in entry and entry[key] == default:
            entry.pop(key)
    return entry


class _SolverOnly:
    """The stage lowering of a hold verb: it makes no clip, so the actions pass
    drops it (the ``solve`` pass reads the verbs from the shot itself)."""

    def __init__(self, kind: str) -> None:
        self.kind = kind

    def extent_resolver(self, vocab: Any, *, products: Any) -> None:
        return None

    def expand(self, flat_list: list, **kw: Any) -> list:
        return [f for f in flat_list if getattr(f.action, "kind", None) != self.kind]

    def view_of(self, entity_swaps: Any, vocab: Any, *, duration: float) -> None:
        return None


def _register_hold_kinds() -> None:
    for kind in (
        ActionKind(
            "grasp",
            GraspAction,
            duration=_gesture_length,
            read_md=_read_md(GraspAction),
            write_md=_write_md,
            lowering=_SolverOnly("grasp"),
            description="reach an item with a body's point (a hand) and take it, keeping its pose",
        ),
        ActionKind(
            "place",
            PlaceAction,
            duration=_gesture_length,
            read_md=_read_md(PlaceAction),
            write_md=_write_md,
            lowering=_SolverOnly("place"),
            description="bring a held item onto the ground, a socket or a point, and let it go there",
        ),
        ActionKind(
            "release",
            ReleaseAction,
            duration=lambda a, _extent: 0.0,
            flatten=_flatten_release,
            read_md=_read_md(ReleaseAction),
            write_md=_write_md,
            md_start=False,
            lowering=_SolverOnly("release"),
            description="let a held item go: it falls, or is tossed, onto the ground",
        ),
        ActionKind(
            "handover",
            HandoverAction,
            duration=_gesture_length,
            read_md=_read_md(HandoverAction),
            write_md=_write_md,
            lowering=_SolverOnly("handover"),
            description="give a held item to another holder (a hand, a socket)",
        ),
        ActionKind(
            "swap",
            SwapAction,
            duration=lambda a, _extent: float(a.lag) + _gesture_length(a),
            flatten=_flatten_swap,
            read_md=_read_md(SwapAction),
            write_md=_write_md,
            lowering=_SolverOnly("swap"),
            description="take the item a holder has and give it another in its place",
        ),
    ):
        if action_kind(kind.name) is None:
            register_action_kind(kind, owner=CORE_OWNER)


_register_hold_kinds()
