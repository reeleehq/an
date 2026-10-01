"""The character side of the cut-out genre, as declarations: ``play`` and ``character``.

What the cut-out genre (:mod:`an.genres.cutout`) registers from here (ADR 0001
§First slice):

- the **``play`` action kind** — :class:`an.ir.schema.PlayAction`, how long a
  duration-less play occupies a ``sequence`` (its natural length, through the
  caller's extent resolver), and its ``scene.md`` spelling;
- the **``character`` entity kind** — a rigged character, whose nodes are
  nodes of the 2D stage engine (the ``stage.node`` property space).

Plain declarations: importing this module registers nothing.

>>> PLAY.name, CHARACTER.space
('play', 'stage.node')
"""

from __future__ import annotations

from typing import Any

from an.genres.registry import ActionKind, EntityKind
from an.ir.schema import PlayAction


def play_duration(action: PlayAction, extent: Any) -> float:
    """The span a ``play`` occupies: its ``duration``, else its natural extent.

    ``extent`` is the caller's resolver (the compiler and ``an validate`` pass
    one bound to the entity's descriptor); without one, a motion preset's own
    length (:func:`an.ir.compose.default_play_extent`).

    >>> play_duration(PlayAction(target="a", animation="hop", duration=2.0), None)
    2.0
    >>> play_duration(PlayAction(target="a", animation="hop"), None)
    0.5
    """
    if action.duration is not None:
        return action.duration
    if extent is None:
        from an.ir.compose import default_play_extent  # lazy: compose imports this

        extent = default_play_extent
    return extent(action)


def _play_args(raw: Any, *, index: int) -> dict[str, Any] | None:
    """A ``play``'s ``args:`` — a mapping of motion-preset parameters, or absent."""
    from an.ir.sync import SceneMarkdownError

    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SceneMarkdownError(
            f"actions[{index}].args must be a mapping of motion-preset "
            f"parameters (e.g. `args: {{height: 30}}`); got {raw!r}"
        )
    return {str(k): v for k, v in raw.items()}


def read_play_md(item: dict[str, Any], *, index: int) -> PlayAction:
    """``{kind: play, target, animation, [duration], [speed], [loop], [args]}``.

    Resolved at compile against the target entity's descriptor ``animations``
    (an#7), falling back to the motion presets of ``an.motion.PRESETS`` for a
    name the descriptor does not declare, with ``args`` as the preset's
    parameters (an#166). ``loop`` omitted means the animation's own. This
    reader accepted the shape from the start, then #24 made it refuse (nothing
    resolved a play) while the writer kept emitting it — three days of a
    project's own scene.md failing to parse.
    """
    from an.ir.compose import play

    return play(
        item["target"],
        item["animation"],
        duration=(
            float(item["duration"]) if item.get("duration") is not None else None
        ),
        speed=float(item.get("speed", 1.0)),
        loop=(bool(item["loop"]) if item.get("loop") is not None else None),
        args=_play_args(item.get("args"), index=index),
    )


def write_play_md(leaf: PlayAction) -> dict[str, Any]:
    """The ``scene.md`` entry for ``leaf`` (``read_play_md``'s inverse)."""
    entry: dict[str, Any] = {
        "kind": "play",
        "target": leaf.target,
        "animation": leaf.animation,
    }
    if leaf.duration is not None:
        entry["duration"] = leaf.duration
    if leaf.speed != 1.0:
        entry["speed"] = leaf.speed
    if leaf.loop is not None:
        entry["loop"] = bool(leaf.loop)
    if leaf.args is not None:
        entry["args"] = dict(leaf.args)
    return entry


PLAY = ActionKind(
    "play",
    PlayAction,
    duration=play_duration,
    read_md=read_play_md,
    write_md=write_play_md,
    description=(
        "play a named animation (an action / animation clip) of the target "
        "entity's descriptor, falling back to a motion preset"
    ),
)

CHARACTER = EntityKind(
    "character",
    space="stage.node",
    store="characters",
    description=(
        "a rigged cut-out character: a skeleton of bones with slots, drawn by "
        "the stage engine; its nodes are stage nodes"
    ),
)
