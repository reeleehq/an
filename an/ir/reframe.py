"""Changing frame: the ``reframe`` action (an#502, ADR 0008 decision 5).

A member of the world is in one frame of reference at a time
(:mod:`an.ir.frames`). ``reframe`` moves it to another at an instant:

- ``keep: world`` (the default) recomputes its local position in the new frame
  so the picture is continuous (Unity's ``worldPositionStays``, Unreal's
  ``KeepWorld``, Godot's ``keep_global_transform``); ``keep: local`` keeps the
  numbers and lets the picture jump (``KeepRelative``);
- ``snap`` moves it to a named **socket** of the new frame (``Frame.sockets``:
  where a prop is picked up) instead;
- ``inherit: velocity`` (the default) gives the member, in the new frame, the
  velocity the old frame carried it with, added to its own (the Galilean sum;
  Godot's ``platform_on_leave`` ``ADD_VELOCITY``); ``inherit: none`` stops that
  part in the world. It, and ``velocity``, only apply with ``motion:
  ballistic`` (otherwise the member follows the new frame, and asking for
  them is refused);
- ``motion: ballistic`` makes the member a projectile in the world from then
  on, ``p + v·dt + ½·g·dt²`` (closed form, no dependency, sampled by
  :func:`an.ir.world.fit_channel`). This is the gravity seam: the puppet
  solver's gravity is the later implementation at the same place. Without it
  the member follows its own ``<member>:at_*`` actions that start at or after
  ``at``, in the new frame's units.

``at`` is shot time (like every frame action); ``velocity`` is the member's own
extra velocity in the OLD frame's axes, per second (a throw: sideways 3, up 2).

None of it makes a clip: the world lowering (:mod:`an.ir.world`) reads it and
samples the member's course; the actions pass drops it. A scene with no
``reframe`` lowers byte for byte as before.

>>> from an.ir.compose import flatten, sequence, delay
>>> [(f.start, f.end, f.action.kind) for f in flatten(sequence(delay(1.0), reframe("bottle", to="world", at=0.5)))]
[(1.5, 1.5, 'reframe')]
>>> reframe("bottle", to="world", velocity=(3.0, -2.0, 0.0), motion="ballistic").motion
'ballistic'

The kind is the core's (ADR 0001's test: a ball leaving a conveyor needs it
without saying character), registered when :mod:`an.ir` loads.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from an.base import Seconds
from an.genres.registry import CORE_OWNER, ActionKind, action_kind, register_action_kind
from an.ir.schema import DFLT_WORLD_GRAVITY, ExtensionAction, Point3

__all__ = [
    "ReframeAction",
    "reframe",
    "DFLT_WORLD_GRAVITY",
]


class ReframeAction(ExtensionAction):
    """Member ``target`` leaves its frame for ``to`` at ``at`` (shot seconds).

    >>> ReframeAction(target="bottle", to="world").keep
    'world'
    """

    kind: Literal["reframe"] = "reframe"
    target: str
    to: str
    at: Seconds = 0.0
    keep: Literal["world", "local"] = "world"
    snap: str | None = None
    #: Unset reads as ``velocity``; a lint asks for it to be said when the old
    #: frame moves.
    inherit: Literal["velocity", "none"] | None = None
    motion: Literal["ballistic"] | None = None
    velocity: Point3 = (0.0, 0.0, 0.0)
    gravity: float = Field(default=DFLT_WORLD_GRAVITY, allow_inf_nan=False)

    @model_validator(mode="after")
    def _flight_fields_need_a_flight(self) -> "ReframeAction":
        import math

        if not all(math.isfinite(v) for v in (self.at, *self.velocity)):
            raise ValueError("a reframe's `at` and `velocity` must be finite numbers.")
        if self.motion is None and (self.inherit is not None or any(self.velocity)):
            raise ValueError(
                "`inherit` and `velocity` say how a member flies after leaving its "
                "frame; give `motion: ballistic`, or drop them (a member that does not "
                "fly follows the new frame)."
            )
        return self


def reframe(
    target: str,
    *,
    to: str,
    at: Seconds = 0.0,
    keep: Literal["world", "local"] = "world",
    snap: str | None = None,
    inherit: Literal["velocity", "none"] | None = None,
    motion: Literal["ballistic"] | None = None,
    velocity: Point3 = (0.0, 0.0, 0.0),
    gravity: float = DFLT_WORLD_GRAVITY,
) -> ReframeAction:
    """``target`` changes to frame ``to`` at ``at`` seconds into the action.

    >>> reframe("cup", to="hand", snap="palm").snap
    'palm'
    """
    return ReframeAction(
        target=target,
        to=to,
        at=at,
        keep=keep,
        snap=snap,
        inherit=inherit,
        motion=motion,
        velocity=velocity,
        gravity=gravity,
    )


# -----------------------------------------------------------------------------
# Registration: an instant, its scene.md form, the lowering that drops it
# -----------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    "at": 0.0,
    "keep": "world",
    "velocity": (0.0, 0.0, 0.0),
    "gravity": DFLT_WORLD_GRAVITY,
}


def _flatten_instant(action: Any, t: Seconds, ctx: Any) -> Seconds:
    """An instant at ``t + at`` that advances nothing (``set``'s rule)."""
    ctx.emit(t + action.at, t + action.at, action)
    return t


def _read_md(item: dict[str, Any], *, index: int) -> Any:
    from an.ir.sync import SceneMarkdownError

    try:
        return ReframeAction.model_validate(item)
    except ValueError as e:
        raise SceneMarkdownError(f"actions[{index}] ({item.get('kind')}): {e}") from e


def _write_md(action: Any) -> dict[str, Any]:
    entry = action.model_dump(exclude_none=True)
    for key, default in _DEFAULTS.items():
        if key in entry and (
            tuple(entry[key]) == default
            if isinstance(default, tuple)
            else entry[key] == default
        ):
            entry.pop(key)
    return entry


class _WorldOnly:
    """The stage lowering of a ``reframe``: it makes no clip (the world lowering
    turned it into the member's sampled course), so the actions pass drops it."""

    kind = "reframe"

    def extent_resolver(self, vocab: Any, *, products: Any) -> None:
        return None

    def expand(self, flat_list: list, **kw: Any) -> list:
        return [f for f in flat_list if getattr(f.action, "kind", None) != self.kind]

    def view_of(self, entity_swaps: Any, vocab: Any, *, duration: float) -> None:
        return None


def _register_reframe_kind() -> None:
    kind = ActionKind(
        "reframe",
        ReframeAction,
        duration=lambda a, _extent: 0.0,
        flatten=_flatten_instant,
        read_md=_read_md,
        write_md=_write_md,
        md_start=False,
        lowering=_WorldOnly(),
        description="move a world member to another frame of reference at an instant, "
        "keeping its place in the world; optionally flying free under gravity",
    )
    if action_kind(kind.name) is None:
        register_action_kind(kind, owner=CORE_OWNER)


_register_reframe_kind()
