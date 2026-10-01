"""The authored flat timeline: ``(start, end, address, change)`` rows.

The upper of the kernel's two canonical levels (core study §2.4). Every authoring
front-end — `an`'s combinators, a keyframe sequence, Manim-style beats, recipes —
lowers to this list with absolute seconds, and a compiler lowers it to the
compiled form (:mod:`an.timing.timeline`). It is what ``timeline.schema.json``
describes and what a package that copies `an`'s track format (``shaping``)
validates against.

A **change** is ``set`` (a value from ``start`` on) or ``tween`` (from an
optional ``from`` — absent means "from whatever the property has at ``start``" —
to ``to``, through an ``easing``). Genre actions (a ``play``, an ``expression``)
are not changes: a genre lowers them before this level.

>>> from types import SimpleNamespace as NS
>>> rows = [NS(start=0.0, end=1.0, action=NS(kind="tween", target="charlie/left_arm",
...     property="rotation", to_value=0.5, from_value=None, easing="ease_in_out"))]
>>> flat_timeline_doc(rows)["actions"]
[{'start': 0.0, 'end': 1.0, 'address': 'charlie/left_arm:rotation', 'change': {'kind': 'tween', 'to': 0.5, 'easing': 'ease_in_out'}}]
"""

from __future__ import annotations

from typing import Any, Iterable

from an.timing.address import Address

#: The document's self-description (``{kind, version}`` envelope, core study §2.1).
FLAT_TIMELINE_FORMAT: str = "an.timeline"
FLAT_TIMELINE_VERSION: int = 1
CHANGE_KINDS: tuple[str, ...] = ("set", "tween")


class UnsupportedChangeError(ValueError):
    """A flat action is not a ``set`` or a ``tween`` (a genre action not yet lowered)."""


def _jsonable(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


def change_of(action: Any, *, default_easing: Any = None) -> dict[str, Any]:
    """The ``change`` of one leaf action (any object with the IR's attribute names).

    A tween's easing is written RESOLVED and always (``null`` is linear): the
    tween's own, else ``default_easing`` (the scene's ``meta.default_easing``),
    else the IR default — the precedence ``TweenAction.resolved_easing`` states,
    so the flat document says what compiles (an#166).
    """
    kind = getattr(action, "kind", None)
    if kind == "set":
        return {"kind": "set", "value": _jsonable(action.value)}
    if kind == "tween":
        out: dict[str, Any] = {"kind": "tween"}
        if getattr(action, "from_value", None) is not None:
            out["from"] = _jsonable(action.from_value)
        out["to"] = _jsonable(action.to_value)
        resolve = getattr(action, "resolved_easing", None)
        easing = resolve(default_easing) if resolve else getattr(action, "easing", None)
        out["easing"] = _jsonable(easing)
        return out
    raise UnsupportedChangeError(
        f"a flat timeline holds set and tween changes only; {kind!r} must be lowered first"
    )


def flat_timeline_doc(
    flat_actions: Iterable[Any],
    *,
    duration: float | None = None,
    default_easing: Any = None,
    skip_other: bool = False,
) -> dict[str, Any]:
    """A ``timeline.schema.json`` document from flat actions.

    Each item has ``start``, ``end`` and a leaf ``action`` with ``kind``,
    ``target``, ``property`` and the change's values — the shape of
    ``an.ir.compose.flatten``'s output, read by attribute so this module does not
    import the IR. ``default_easing`` is the scene's ``meta.default_easing``.
    ``skip_other`` drops non-change actions instead of raising.
    """
    rows = []
    for item in flat_actions:
        action = item.action
        try:
            change = change_of(action, default_easing=default_easing)
        except UnsupportedChangeError:
            if skip_other:
                continue
            raise
        rows.append(
            {
                "start": item.start,
                "end": item.end,
                "address": str(Address.of(action.target, action.property)),
                "change": change,
            }
        )
    doc: dict[str, Any] = {
        "format": FLAT_TIMELINE_FORMAT,
        "version": FLAT_TIMELINE_VERSION,
    }
    if duration is not None:
        doc["duration"] = duration
    doc["actions"] = rows
    return doc
