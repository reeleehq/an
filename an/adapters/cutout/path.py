"""Stroked-path geometry — the executable spec of ``runtime.js::pathGeometry``.

The runtime draws a path (an#160) from three things this module defines:

- **arc length** — cumulative straight-segment lengths over the polyline;
- **trim** — the visible span ``[min(ts, te), max(ts, te)]``, clamped to
  ``[0, 1]``, as fractions of that length;
- **dashes** — an optional on/off pattern laid along the WHOLE path from arc
  length 0 (shifted by an offset) and only then clipped to the trimmed span, so
  a draw-on reveals dashes in place rather than making them crawl (an#161);
- **the arrowhead** — a triangle whose tip is the trimmed end, oriented along
  the direction of the segment the tip lies on (the *incoming* segment when
  the tip sits exactly on a vertex).

``tests/test_path.py`` lifts the real ``runtime.js`` functions, runs them under
node on a shared battery, and compares — behaviourally, like the channel
evaluator's parity test. Both sides use the **same operation order** and no
trigonometry (a direction is a unit vector, never an angle), and every
operation is IEEE ``+ - * / sqrt``, which both languages round exactly — so
the parity is exact, not within a tolerance.

Cubic Béziers never reach the runtime: :func:`flatten_curve` turns them into a
polyline at compile time, so the wire carries one geometry kind.

>>> g = path_geometry([(0.0, 0.0), (100.0, 0.0)], 0.0, 0.5)
>>> g["stroke"]
[(0.0, 0.0), (50.0, 0.0)]
>>> g["head"] is None
True
>>> g = path_geometry([(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)], 0.0, 0.75,
...                   head_length=20.0, head_width=10.0)
>>> g["head"]  # tip at (100, 50), pointing DOWN (+y) along the second leg
[(100.0, 50.0), (95.0, 30.0), (105.0, 30.0)]
"""

from __future__ import annotations

import math
from typing import Sequence

Point = tuple[float, float]

__all__ = [
    "flatten_curve",
    "cumulative_lengths",
    "point_at",
    "trim_polyline",
    "dash_spans",
    "path_geometry",
    "HEAD_STROKE_INSET",
]

#: Where the stroke stops under an arrowhead, as a fraction of the head's
#: length back from the tip. Half-way keeps a butt or round cap inside the
#: head for the default proportions, so the stroke never pokes past the tip.
HEAD_STROKE_INSET: float = 0.5


def flatten_curve(
    points: Sequence[Sequence[float]], *, curve: str = "polyline", samples: int = 24
) -> list[Point]:
    """The polyline the runtime draws for ``points``.

    ``curve="cubic"`` reads ``points`` as chained cubic Béziers
    (``p0 c1 c2 p1 c1 c2 p2 ...``) and samples each uniformly in its parameter
    at ``samples`` steps; shared endpoints appear once.

    >>> flatten_curve([(0, 0), (10, 0)])
    [(0.0, 0.0), (10.0, 0.0)]
    >>> pts = flatten_curve([(0, 0), (0, 10), (10, 10), (10, 0)], curve="cubic", samples=2)
    >>> pts
    [(0.0, 0.0), (5.0, 7.5), (10.0, 0.0)]
    """
    pts = [(float(p[0]), float(p[1])) for p in points]
    if curve == "polyline":
        return pts
    if curve != "cubic":
        raise ValueError(f"unknown curve {curve!r}; known: 'polyline', 'cubic'")
    if (len(pts) - 1) % 3 or len(pts) < 4:
        raise ValueError(f"a cubic path takes 3n + 1 points; got {len(pts)}")
    out = [pts[0]]
    for k in range(0, len(pts) - 1, 3):
        p0, c1, c2, p1 = pts[k], pts[k + 1], pts[k + 2], pts[k + 3]
        for i in range(1, samples + 1):
            t = i / samples
            u = 1.0 - t
            b0, b1, b2, b3 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
            out.append(
                (
                    b0 * p0[0] + b1 * c1[0] + b2 * c2[0] + b3 * p1[0],
                    b0 * p0[1] + b1 * c1[1] + b2 * c2[1] + b3 * p1[1],
                )
            )
    return out


def cumulative_lengths(points: Sequence[Point]) -> list[float]:
    """Arc length at each vertex. Mirror of ``runtime.js::pathLengths``.

    >>> cumulative_lengths([(0, 0), (3, 4), (3, 10)])
    [0.0, 5.0, 11.0]
    """
    cum = [0.0]
    for i in range(1, len(points)):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        cum.append(cum[i - 1] + math.sqrt(dx * dx + dy * dy))
    return cum


def _segment_at(cum: Sequence[float], s: float) -> int:
    """The index ``i`` of the segment ``[i, i+1]`` holding arc length ``s``.

    The first non-degenerate segment whose END reaches ``s`` — so a point
    exactly on a vertex belongs to the segment arriving there, which is what
    makes an arrowhead at a corner point along the leg it came in on.
    Mirror of ``runtime.js::pathSegmentAt``.
    """
    last = 0
    for i in range(len(cum) - 1):
        if cum[i + 1] > cum[i]:
            last = i
            if s <= cum[i + 1]:
                return i
    return last


def point_at(points: Sequence[Point], cum: Sequence[float], s: float) -> Point:
    """The point at arc length ``s``. Mirror of ``runtime.js::pathPointAt``."""
    i = _segment_at(cum, s)
    span = cum[i + 1] - cum[i]
    if not span > 0:
        return (points[i][0], points[i][1])
    u = (s - cum[i]) / span
    ax, ay = points[i]
    bx, by = points[i + 1]
    return (ax + (bx - ax) * u, ay + (by - ay) * u)


def trim_polyline(
    points: Sequence[Point], cum: Sequence[float], a: float, b: float
) -> list[Point]:
    """The sub-polyline between arc lengths ``a < b``: the two cut points and
    every vertex strictly between them. Mirror of ``runtime.js::pathTrim``."""
    out = [point_at(points, cum, a)]
    for i in range(1, len(points) - 1):
        if a < cum[i] < b:
            out.append((points[i][0], points[i][1]))
    out.append(point_at(points, cum, b))
    return out


def dash_spans(
    a: float, b: float, dash: float, gap: float, offset: float
) -> list[tuple[float, float]]:
    """The arc-length spans ``[lo, hi]`` inside ``[a, b]`` that a dash covers.

    The pattern is anchored at arc length ``0`` — dash ``k`` covers
    ``[offset + k*period, offset + k*period + dash]`` — and is clipped to the
    window afterwards, so moving ``a`` or ``b`` never moves a dash. Only IEEE
    ``+ - * /`` and ``floor``, in the order ``runtime.js::pathDashSpans`` uses.

    >>> dash_spans(0.0, 100.0, 10.0, 15.0, 0.0)
    [(0.0, 10.0), (25.0, 35.0), (50.0, 60.0), (75.0, 85.0)]
    >>> dash_spans(30.0, 60.0, 10.0, 15.0, 0.0)  # clipped, not re-anchored
    [(30.0, 35.0), (50.0, 60.0)]
    >>> dash_spans(0.0, 30.0, 10.0, 10.0, 5.0)  # offset slides the pattern forward
    [(5.0, 15.0), (25.0, 30.0)]
    """
    period = dash + gap
    k = math.floor((a - offset - dash) / period)
    out: list[tuple[float, float]] = []
    while True:
        start = offset + k * period
        if not start < b:
            break
        lo = a if a > start else start
        end = start + dash
        hi = b if b < end else end
        if hi > lo:
            out.append((lo, hi))
        k += 1
    return out


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def path_geometry(
    points: Sequence[Point],
    trim_start: float,
    trim_end: float,
    *,
    head_length: float = 0.0,
    head_width: float = 0.0,
    dash: float = 0.0,
    gap: float = 0.0,
    dash_offset: float = 0.0,
) -> dict:
    """What the runtime draws: ``{"stroke": [points], "head": [3 points] | None}``.

    ``dash > 0`` makes the stroke a dash pattern: ``stroke`` is then ``[]`` and
    a ``"dashes"`` key (absent otherwise) holds one polyline per visible dash.

    ``head_length > 0`` turns the arrowhead on. While the visible length is
    shorter than the head, the head is scaled by ``visible / head_length`` so
    a draw-on grows it in rather than popping a full-size triangle at frame
    one. The stroke stops :data:`HEAD_STROKE_INSET` of the head's length back
    from the tip, inside the head. Mirror of ``runtime.js::pathGeometry``.

    >>> path_geometry([(0.0, 0.0), (10.0, 0.0)], 0.3, 0.3)
    {'stroke': [], 'head': None}
    """
    pts = [(float(p[0]), float(p[1])) for p in points]
    cum = cumulative_lengths(pts)
    total = cum[-1]
    lo = _clamp01(min(trim_start, trim_end))
    hi = _clamp01(max(trim_start, trim_end))
    a = lo * total
    b = hi * total
    if not b > a:
        return {"stroke": [], "head": None}
    head = None
    stroke_end = b
    if head_length > 0:
        visible = b - a
        k = visible / head_length if visible < head_length else 1.0
        hl = head_length * k
        hw = head_width * k
        i = _segment_at(cum, b)
        dx = pts[i + 1][0] - pts[i][0]
        dy = pts[i + 1][1] - pts[i][1]
        seg = math.sqrt(dx * dx + dy * dy)
        ux = dx / seg
        uy = dy / seg
        tx, ty = point_at(pts, cum, b)
        bx = tx - ux * hl
        by = ty - uy * hl
        nx = -uy * (hw / 2)
        ny = ux * (hw / 2)
        head = [(tx, ty), (bx + nx, by + ny), (bx - nx, by - ny)]
        stroke_end = b - hl * HEAD_STROKE_INSET
    if dash > 0:
        spans = dash_spans(a, stroke_end, dash, gap, dash_offset) if stroke_end > a else []
        dashes = [trim_polyline(pts, cum, lo_s, hi_s) for lo_s, hi_s in spans]
        return {"stroke": [], "head": head, "dashes": dashes}
    stroke = trim_polyline(pts, cum, a, stroke_end) if stroke_end > a else []
    return {"stroke": stroke, "head": head}
