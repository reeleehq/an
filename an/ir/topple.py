"""``topple``: a rigid body falls over about the point it stands on, under gravity (catalogue A1, B4).

A camera on a tripod knocked over, a figurine tipping onto its face, a chain
of them: the body turns, as one piece, about its foot on the side it falls
toward (the corner of its ink that touches the floor), from a ``push`` (an
angular velocity, rad/s), accelerating as a rigid pendulum does, until
another of its points reaches the floor (it lies there after a small bounce)
or a named point of it reaches a target (``point`` onto ``until``: the sabre's
tip into an eye; it stays there). What it holds (a sabre in a figurine's hand)
falls with it.

A topple can be **knocked** by another: ``after: cam_falls`` starts it at the
instant the body of the topple named ``cam_falls`` first touches it, with a
push from that body's speed there. The ``topple`` compile pass
(:mod:`an.stage.topple`) runs after the ``solve`` pass (it moves what the hold
layer has placed) and writes the bodies' keys; nothing here makes a clip.

>>> from an.ir.compose import flatten, sequence, delay
>>> [(f.start, f.action.kind) for f in flatten(sequence(delay(1.0), topple("cam", toward="right")))]
[(1.0, 'topple')]
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from an.genres.registry import CORE_OWNER, ActionKind, action_kind, register_action_kind
from an.ir.schema import ExtensionAction

__all__ = ["DFLT_PUSH", "DFLT_KNOCK", "ToppleAction", "topple"]

#: The angular velocity a topple starts with when nothing knocks it (rad/s):
#: a nudge, enough to start a balanced body falling.
DFLT_PUSH: float = 0.6
#: The share of the knocking body's speed at the contact a knocked body starts
#: turning with (its tip speed over its height).
DFLT_KNOCK: float = 0.6


class ToppleAction(ExtensionAction):
    """``body`` falls over ``toward`` a side, about its foot on that side.

    >>> ToppleAction(body="nap", after="cam_falls", point="sabre@0.97,0.03", until="han@0.62,0.2").toward
    'right'
    """

    kind: Literal["topple"] = "topple"
    body: str
    #: Its name, for another topple's ``after``.
    id: str | None = None
    toward: Literal["left", "right"] = "right"
    #: Rad/s it starts with (ignored when it is knocked: ``after``).
    push: float = Field(default=DFLT_PUSH, ge=0, allow_inf_nan=False)
    #: The topple whose body knocks this one over (it starts when they touch).
    after: str | None = None
    #: A point of the body, or of an item it holds (``path@u,v``: fractions of
    #: that node's drawing), that stops the fall where it reaches ``until``.
    point: str | None = None
    #: Where ``point`` stops (``path@u,v`` of another body, or ``world@x,y``);
    #: unset: the body falls until another of its points reaches the floor.
    until: str | None = None
    #: The coefficient of restitution when it hits the floor (0: dead).
    bounce: float | None = Field(default=None, ge=0, le=0.95, allow_inf_nan=False)
    #: The share of the knocker's speed it starts with (``after`` only).
    knock: float = Field(default=DFLT_KNOCK, gt=0, le=2.0, allow_inf_nan=False)


def topple(body: str, **kw: Any) -> ToppleAction:
    """``body`` falls over (see :class:`ToppleAction` for the fields).

    >>> topple("cam", toward="right", push=1.0).push
    1.0
    """
    return ToppleAction(body=body, **kw)


def _read_md(item: dict[str, Any], *, index: int) -> Any:
    from an.ir.sync import SceneMarkdownError

    try:
        return ToppleAction.model_validate(item)
    except ValueError as e:
        raise SceneMarkdownError(f"actions[{index}] (topple): {e}") from e


def _write_md(action: Any) -> dict[str, Any]:
    entry = action.model_dump(exclude_none=True)
    for key, default in (
        ("toward", "right"),
        ("push", DFLT_PUSH),
        ("knock", DFLT_KNOCK),
    ):
        if entry.get(key) == default:
            entry.pop(key)
    return entry


class _PassOnly:
    """The stage lowering of ``topple``: no clip; the ``topple`` pass reads it."""

    kind = "topple"

    def extent_resolver(self, vocab: Any, *, products: Any) -> None:
        return None

    def expand(self, flat_list: list, **kw: Any) -> list:
        return [f for f in flat_list if getattr(f.action, "kind", None) != self.kind]

    def view_of(self, entity_swaps: Any, vocab: Any, *, duration: float) -> None:
        return None


def _register() -> None:
    if action_kind("topple") is not None:
        return
    register_action_kind(
        ActionKind(
            "topple",
            ToppleAction,
            duration=lambda a, _extent: 0.0,
            read_md=_read_md,
            write_md=_write_md,
            lowering=_PassOnly(),
            description="a rigid body falls over about its foot under gravity, onto the floor or until a point of it reaches a target; one can knock another",
        ),
        owner=CORE_OWNER,
    )


_register()
