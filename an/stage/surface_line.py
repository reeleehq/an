"""Surface lines: what a thing stands on, as a line on the stage (an#519).

A *support line* is a point on it and its unit direction, turned so that its
normal ``(-dy, dx)`` points DOWN the screen, into the support. The floor is a
level line (:func:`ground_line`); a body's top edge or a stage segment is the
line through its two ends (:func:`line_through`). Measured against one:

- :func:`lowest_on`: the lowest of some points (a part's corners or ink,
  under its world matrix) against the line, and how far above it that point
  is, along its normal; negative when sunk into it. :func:`above` is the
  distance alone.
- :func:`lift`: a world matrix moved along the line's normal by such a
  distance, which is how an item is laid exactly on what carries it.

A body's own surface (``<body>@surface``, an#536) is the segment
:func:`body_surface` reads off its rig (:data:`SURFACE_BONES`) or the top of
its ink. The hold layer (:mod:`an.stage.hold`) lays items on the floor and on
bodies' surfaces with these; they live here so that other measurements of
standing (the support and skate checks of an#519, :mod:`an.stage.support`)
use the same lines, the same segment, the same normal and the same sign.

>>> floor = ground_line(100.0)
>>> above((1, 0, 0, 1, 0, 0), [(0.0, 90.0)], floor)  # 10 px above the floor
10.0
>>> lift((1, 0, 0, 1, 0.0, 0.0), floor, 10.0)[4:]  # moved down onto it
(0.0, 10.0)
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from an.ir.schema import SURFACE_POINT
from an.stage.solve import Affine, _apply, _compose

__all__ = [
    "SURFACE_BONES",
    "Line",
    "Segment",
    "ground_line",
    "line_through",
    "lowest_on",
    "above",
    "lift",
    "body_surface",
]

#: The bones a body declares its supporting surface by (an#536), its two ends
#: in the art's terms (left, right): what ``<body>@surface`` lays an item on.
#: Undeclared, the surface is the top edge of the part's ink.
SURFACE_BONES: tuple[str, str] = ("surface_l", "surface_r")


#: A support line: a point on it and its unit direction, turned so that its
#: normal ``(-dy, dx)`` points DOWN the screen (into the support).
Line = tuple[tuple[float, float], tuple[float, float]]
#: A bounded surface: its two ends.
Segment = tuple[tuple[float, float], tuple[float, float]]


def ground_line(ground: float) -> Line:
    """The level floor at stage ``y`` ``ground``: its normal points down.

    >>> ground_line(5.0)
    ((0.0, 5.0), (1.0, 0.0))
    """
    return ((0.0, ground), (1.0, 0.0))


def line_through(a: tuple[float, float], b: tuple[float, float]) -> Line:
    """The support line through ``a`` and ``b``, whichever end is named first.

    >>> line_through((10.0, 5.0), (0.0, 5.0))
    ((10.0, 5.0), (1.0, 0.0))
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    d = (dx / n, dy / n)
    if d[0] < 0 or (d[0] == 0 and d[1] > 0):  # its normal (-dy, dx) points down
        d = (-d[0] + 0.0, -d[1] + 0.0)
    return a, d


def lowest_on(
    m: Affine, points: Sequence[tuple[float, float]], line: Line
) -> tuple[tuple[float, float], float]:
    """The lowest of ``points`` under ``m`` against ``line`` (the farthest
    along its normal, into it; the first of equals), and how far above the
    line it is (negative: sunk into it).

    >>> lowest_on((1, 0, 0, 1, 0, 0), [(0.0, 0.0), (2.0, 3.0)], ground_line(5.0))
    ((2.0, 3.0), 2.0)
    """
    (ax, ay), (dx, dy) = line
    nx, ny = -dy, dx
    lowest, depth = None, -math.inf
    for p in (_apply(m, c) for c in points):
        d = nx * (p[0] - ax) + ny * (p[1] - ay)
        if lowest is None or d > depth:
            lowest, depth = p, d
    if lowest is None:
        raise ValueError("no points to measure against a surface")
    return lowest, -depth


def above(m: Affine, corners: Sequence[tuple[float, float]], line: Line) -> float:
    """How far the lowest of ``corners`` under ``m`` is above ``line``, along
    its normal (negative: sunk into it). On the ground, ``ground - lowest``.

    >>> square = [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0), (2.0, 2.0)]
    >>> above((1, 0, 0, 1, 0, 0), square, ground_line(5.0))
    3.0
    """
    return lowest_on(m, corners, line)[1]


def lift(m: Affine, line: Line, distance: float) -> Affine:
    """``m`` moved ``distance`` along ``line``'s normal (down onto it when positive).

    >>> lift((1, 0, 0, 1, 2.0, 3.0), ground_line(10.0), 4.0)[4:]
    (2.0, 7.0)
    """
    dx, dy = line[1]
    return _compose((1.0, 0.0, 0.0, 1.0, -dy * distance + 0.0, dx * distance + 0.0), m)


def body_surface(
    doc: Any,
    nodes: Mapping[str, Any],
    mall: Mapping[str, Any] | None,
    *,
    rig: Any,
    entity: str,
    node: str,
    frame: str | None = None,
    to_frame: Affine | None = None,
) -> Segment | str:
    """``<body>@surface``'s segment (an#536): its two ends in node ``frame``'s
    own coordinates (default: ``node``'s), from the rig's :data:`SURFACE_BONES`
    when it declares them, else the top edge of ``node``'s ink, mapped by
    ``to_frame`` (``node``'s frame in ``frame``'s; none: they are one). Returns
    why, instead, when the rig names it wrongly.

    >>> from an.stage.serialize import NodeJSON, VisualJSON
    >>> art = {"crate": NodeJSON(name="crate", visual=VisualJSON(width=10, height=4))}
    >>> body_surface(None, art, None, rig=None, entity="crate", node="crate")
    ((-5.0, -2.0), (5.0, -2.0))
    """
    from an.stage.hold import _anchors_in, ink_box

    if rig is not None and SURFACE_POINT in rig.anchors:
        return (
            f"{entity!r} has a bone named {SURFACE_POINT!r}, a reserved point name "
            f"(`<body>@{SURFACE_POINT}` is the body's top, an#536): rename the bone, "
            f"and declare a surface by {list(SURFACE_BONES)}"
        )
    bones = (
        _anchors_in(doc, rig, entity, nodes, frame or node) if rig is not None else {}
    )
    declared = [b for b in SURFACE_BONES if b in bones]
    if len(declared) == len(SURFACE_BONES):
        return (bones[SURFACE_BONES[0]], bones[SURFACE_BONES[1]])
    if declared:
        return (
            f"{entity!r} declares {declared[0]!r} but not "
            f"{[b for b in SURFACE_BONES if b not in declared][0]!r}: a surface is "
            "two bones (its ends), or neither (the top of the part's ink)"
        )
    left, top, w, _h = ink_box(doc, nodes[node], mall)
    if to_frame is None:
        return ((left, top), (left + w, top))
    return (_apply(to_frame, (left, top)), _apply(to_frame, (left + w, top)))
