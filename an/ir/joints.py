"""The constraint layer's verbs: ``pin``, ``pull``, ``join`` and ``unjoin`` (ADR 0008, an#512).

A joint (:class:`an.ir.schema.JointSpec`) says how two bodies stay together;
these four action kinds say what happens to them over time, and they are the
puppeteer's whole repertoire:

- ``pin`` (a rod, a nail): a point of a body is held exactly at a point (of
  another body, or of the stage) for a span, or refused when it is out of
  reach (``an validate`` reports ``unreachable_pin``);
- ``pull`` (a string): a point is drawn as close as the joints allow toward a
  point, or along a path over the span, with a ``give``;
- ``join`` / ``unjoin``: a declared joint's state from an instant on (a
  hand lets go of a cup; it is caught again).

None of them makes a clip. The ``solve`` compile pass (:mod:`an.stage.solve`)
reads them beside the joints and emits the keys of the bodies they move; the
actions pass drops them (their :class:`_SolverOnly` lowering).

>>> from an.ir.compose import flatten, sequence, delay
>>> [(f.start, f.end, f.action.kind) for f in flatten(sequence(delay(1.0), pin("paul/fore_r@hand", "wheel@grip", duration=2.0)))]
[(1.0, 3.0, 'pin')]
>>> [(f.start, f.action.kind) for f in flatten(sequence(delay(1.0), unjoin("grip", at=0.5)))]
[(1.5, 'unjoin')]

These kinds are the core's (ADR 0001's test: a data-visualisation genre pins a
label to a bar without saying character), registered when :mod:`an.ir` loads.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from an.base import Seconds
from an.genres.registry import CORE_OWNER, ActionKind, action_kind, register_action_kind
from an.ir.schema import ExtensionAction, Point2

__all__ = [
    "PinAction",
    "PullAction",
    "JoinAction",
    "UnjoinAction",
    "JOINT_ACTION_KINDS",
    "DFLT_PULL_GIVE",
    "pin",
    "pull",
    "join",
    "unjoin",
]

#: How soft a ``pull`` is when it says nothing: a compliance small enough that
#: a reachable point is met within a fraction of a pixel, and non-zero so an
#: unreachable one is approached (the rigid joints win) rather than refused.
DFLT_PULL_GIVE: float = 1e-6

#: The verbs' kind names.
JOINT_ACTION_KINDS: tuple[str, ...] = ("pin", "pull", "join", "unjoin")

#: Where a verb's point goes: a body point (``wheel@grip``), or a stage point.
Target = str | Point2


class PinAction(ExtensionAction):
    """``point`` (``body[@point]``) held exactly at ``to`` for ``duration``
    seconds (``None``: to the shot's end). It frees the body ``point`` is on
    for the span: a pinned cup goes to the hand, wherever it was staged.

    >>> PinAction(point="cup", to="paul/fore_r@hand").to
    'paul/fore_r@hand'
    """

    kind: Literal["pin"] = "pin"
    point: str
    to: Target
    duration: Seconds | None = Field(default=None, ge=0)


class PullAction(ExtensionAction):
    """``point`` drawn toward ``to`` (a point, or a path of stage points walked
    at an even speed over the span) for ``over`` seconds (``None``: to the
    shot's end), as close as the joints allow; ``give`` is the string's
    softness (compliance, px per unit of pull).

    >>> PullAction(point="puppet/hand_l", to=[[0, -200], [100, -200]], over=2.0).over
    2.0
    """

    kind: Literal["pull"] = "pull"
    point: str
    to: Target | list[Point2]
    over: Seconds | None = Field(default=None, ge=0)
    give: float = Field(default=DFLT_PULL_GIVE, gt=0, allow_inf_nan=False)


class JoinAction(ExtensionAction):
    """The declared joint named ``joint`` is enforced from ``at`` on.

    >>> JoinAction(joint="grip", at=1.0).at
    1.0
    """

    kind: Literal["join"] = "join"
    joint: str
    at: Seconds = 0.0


class UnjoinAction(ExtensionAction):
    """The declared joint named ``joint`` lets go from ``at`` on.

    >>> UnjoinAction(joint="grip").kind
    'unjoin'
    """

    kind: Literal["unjoin"] = "unjoin"
    joint: str
    at: Seconds = 0.0


# -----------------------------------------------------------------------------
# Builders (the fluent spelling, beside `an.ir.compose`'s)
# -----------------------------------------------------------------------------


def pin(point: str, to: Target, *, duration: Seconds | None = None) -> PinAction:
    """``point`` held at ``to``. ``to`` is ``body[@point]`` or ``(x, y)``.

    >>> pin("cup", (10.0, -40.0)).to
    (10.0, -40.0)
    """
    return PinAction(point=point, to=to, duration=duration)


def pull(
    point: str, to: Any, *, over: Seconds | None = None, give: float = DFLT_PULL_GIVE
) -> PullAction:
    """``point`` drawn toward ``to`` (a point, a body point, or a path).

    >>> pull("kite", "world@0,-300", over=1.0).give == DFLT_PULL_GIVE
    True
    """
    return PullAction(point=point, to=to, over=over, give=give)


def join(joint: str, *, at: Seconds = 0.0) -> JoinAction:
    """Rejoin the joint named ``joint`` at ``at``.

    >>> join("grip", at=2.0).at
    2.0
    """
    return JoinAction(joint=joint, at=at)


def unjoin(joint: str, *, at: Seconds = 0.0) -> UnjoinAction:
    """Let go of the joint named ``joint`` at ``at``.

    >>> unjoin("grip").joint
    'grip'
    """
    return UnjoinAction(joint=joint, at=at)


# -----------------------------------------------------------------------------
# Registration: durations, scene.md forms, and the lowering that drops them
# -----------------------------------------------------------------------------


class _SolverOnly:
    """The stage lowering of a verb: it makes no clip, so the actions pass drops
    it (the ``solve`` pass reads the verbs from the shot itself)."""

    def __init__(self, kind: str) -> None:
        self.kind = kind

    def extent_resolver(self, vocab: Any, *, products: Any) -> None:
        return None

    def expand(self, flat_list: list, **kw: Any) -> list:
        return [f for f in flat_list if getattr(f.action, "kind", None) != self.kind]

    def view_of(self, entity_swaps: Any, vocab: Any, *, duration: float) -> None:
        return None


def _flatten_instant(action: Any, t: Seconds, ctx: Any) -> Seconds:
    """``join``/``unjoin`` are instants at ``t + at`` and advance nothing (``set``'s rule)."""
    ctx.emit(t + action.at, t + action.at, action)
    return t


def _read_md(model: type) -> Any:
    def read(item: dict[str, Any], *, index: int) -> Any:
        from an.ir.sync import SceneMarkdownError

        try:
            return model.model_validate(item)
        except ValueError as e:
            raise SceneMarkdownError(f"actions[{index}] ({item.get('kind')}): {e}") from e

    return read


def _write_md(action: Any) -> dict[str, Any]:
    entry = action.model_dump(exclude_none=True)
    if "at" in entry and not entry["at"]:
        entry.pop("at")
    if isinstance(action, PullAction) and action.give == DFLT_PULL_GIVE:
        entry.pop("give", None)
    return entry


def _register_joint_kinds() -> None:
    for kind in (
        ActionKind(
            "pin",
            PinAction,
            duration=lambda a, _extent: a.duration or 0.0,
            read_md=_read_md(PinAction),
            write_md=_write_md,
            lowering=_SolverOnly("pin"),
            description="hold a body's point exactly at a point for a span (a rod, a nail)",
        ),
        ActionKind(
            "pull",
            PullAction,
            duration=lambda a, _extent: a.over or 0.0,
            read_md=_read_md(PullAction),
            write_md=_write_md,
            lowering=_SolverOnly("pull"),
            description="draw a body's point toward a point or along a path (a string)",
        ),
        ActionKind(
            "join",
            JoinAction,
            duration=lambda a, _extent: 0.0,
            flatten=_flatten_instant,
            read_md=_read_md(JoinAction),
            write_md=_write_md,
            md_start=False,
            lowering=_SolverOnly("join"),
            description="enforce a declared joint from an instant on",
        ),
        ActionKind(
            "unjoin",
            UnjoinAction,
            duration=lambda a, _extent: 0.0,
            flatten=_flatten_instant,
            read_md=_read_md(UnjoinAction),
            write_md=_write_md,
            md_start=False,
            lowering=_SolverOnly("unjoin"),
            description="let a declared joint go from an instant on",
        ),
    ):
        if action_kind(kind.name) is None:
            register_action_kind(kind, owner=CORE_OWNER)


_register_joint_kinds()
