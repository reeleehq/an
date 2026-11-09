"""Surface lines: what a thing stands on, as a line on the stage (an#519).

A *support line* is a point on it and its unit direction, turned so that its
normal ``(-dy, dx)`` points DOWN the screen, into the support. The floor is a
level line (:func:`ground_line`); a body's top edge or a stage segment is the
line through its two ends (:func:`line_through`). Measured against one:

- :func:`above`: how far the lowest of some points (a part's corners or ink,
  under its world matrix) is above the line, along its normal; negative when
  sunk into it.
- :func:`lift`: a world matrix moved along the line's normal by such a
  distance, which is how an item is laid exactly on what carries it.

The hold layer (:mod:`an.stage.hold`) lays items on the floor and on bodies'
surfaces with these; they live here so that other measurements of standing
(the support and skate checks of an#519) use the same lines, the same normal
and the same sign.

>>> floor = ground_line(100.0)
>>> above((1, 0, 0, 1, 0, 0), [(0.0, 90.0)], floor)  # 10 px above the floor
10.0
>>> lift((1, 0, 0, 1, 0.0, 0.0), floor, 10.0)[4:]  # moved down onto it
(0.0, 10.0)
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from an.stage.solve import Affine, _apply, _compose

__all__ = ["Line", "ground_line", "line_through", "above", "lift"]


#: A support line: a point on it and its unit direction, turned so that its
#: normal ``(-dy, dx)`` points DOWN the screen (into the support).
Line = tuple[tuple[float, float], tuple[float, float]]


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


def above(m: Affine, corners: Sequence[tuple[float, float]], line: Line) -> float:
    """How far the lowest of ``corners`` under ``m`` is above ``line``, along
    its normal (negative: sunk into it). On the ground, ``ground - lowest``.

    >>> square = [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0), (2.0, 2.0)]
    >>> above((1, 0, 0, 1, 0, 0), square, ground_line(5.0))
    3.0
    """
    (ax, ay), (dx, dy) = line
    nx, ny = -dy, dx
    return -max(
        nx * (p[0] - ax) + ny * (p[1] - ay) for p in (_apply(m, c) for c in corners)
    )


def lift(m: Affine, line: Line, distance: float) -> Affine:
    """``m`` moved ``distance`` along ``line``'s normal (down onto it when positive).

    >>> lift((1, 0, 0, 1, 2.0, 3.0), ground_line(10.0), 4.0)[4:]
    (2.0, 7.0)
    """
    dx, dy = line[1]
    return _compose((1.0, 0.0, 0.0, 1.0, -dy * distance + 0.0, dx * distance + 0.0), m)
