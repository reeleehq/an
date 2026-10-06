"""A hand-drawn wobble for stroked paths, applied at compile time (an#161).

A ruled line reads as a diagram; a line that wanders a little reads as drawn
by hand. The wobble displaces the FLATTENED polyline sideways (along its
normal) by a smooth seeded noise, before it reaches the wire, so the runtime
and its parity spec (:mod:`an.stage.path_geometry`) never learn about it:
trim, dashes and arrowheads work on the wobbly polyline exactly as on any
other.

- **Deterministic everywhere.** The noise is value noise over knots one
  wavelength apart, each knot's value read from ``sha256(seed:k)``, joined by
  a cubic smoothstep: only ``+ - * /``, ``floor`` and ``sqrt``, no
  trigonometry, so the compiled points are the same bytes on every machine.
- **Seeded by the entity** (``"<entity id>:<wobble_seed>"``), like a
  character's blink phase: two arrows sharing one document wobble
  differently, and the same arrow wobbles the same way every render.
- **The ends stay put.** The amplitude ramps up over the first and down over
  the last wavelength, so a route still starts and ends where it was drawn
  to, and an arrowhead's tip lands on its target.
- **Static.** One displacement per path. A *boil* (a wobble that changes on
  twos) is several displaced polylines on a step channel; not built.

>>> pts = wobble_polyline([(0.0, 0.0), (200.0, 0.0)], amplitude=4.0, wavelength=50.0, seed="route:0")
>>> pts[0], pts[-1]  # the ends are where they were
((0.0, 0.0), (200.0, 0.0))
>>> 0.0 < max(abs(y) for _, y in pts) <= 4.0
True
>>> pts == wobble_polyline([(0.0, 0.0), (200.0, 0.0)], amplitude=4.0, wavelength=50.0, seed="route:0")
True
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from typing import Sequence

from an.stage.path_geometry import _segment_at, cumulative_lengths, point_at

Point = tuple[float, float]

__all__ = [
    "wobble_polyline",
    "wobble_with_vertices",
    "wobble_point_count",
    "WOBBLE_SAMPLES_PER_WAVELENGTH",
    "MAX_WOBBLE_POINTS",
]

#: Samples per wavelength of the noise: enough that the wobble reads as a
#: curve, not a zig-zag, at any amplitude a stroke should take.
WOBBLE_SAMPLES_PER_WAVELENGTH: int = 8

#: The most points a wobbled path may carry. Every point is redrawn each
#: frame a trim or dash moves; past this the wavelength is too short for the
#: path's length (a hair-fine wobble over a long route).
MAX_WOBBLE_POINTS: int = 20_000

_HASH_SPAN: float = float(2**64)


def wobble_point_count(length: float, wavelength: float) -> int:
    """How many samples a wobble of ``wavelength`` puts along ``length`` px."""
    step = wavelength / WOBBLE_SAMPLES_PER_WAVELENGTH
    return max(1, math.ceil(length / step))


@lru_cache(maxsize=4096)
def _knot(seed: str, k: int) -> float:
    """The noise value at knot ``k``, in ``[-1, 1)``."""
    digest = hashlib.sha256(f"{seed}:{k}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / _HASH_SPAN * 2.0 - 1.0


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _noise(seed: str, x: float) -> float:
    """Smooth value noise in ``[-1, 1]``: knots at the integers."""
    k = math.floor(x)
    t = _smoothstep(x - k)
    a, b = _knot(seed, k), _knot(seed, k + 1)
    return a + (b - a) * t


def _unit_normal(points: Sequence[Point], i: int) -> Point:
    dx = points[i + 1][0] - points[i][0]
    dy = points[i + 1][1] - points[i][1]
    seg = math.sqrt(dx * dx + dy * dy)
    return (-dy / seg, dx / seg)


def wobble_polyline(
    points: Sequence[Point],
    *,
    amplitude: float,
    wavelength: float,
    seed: str,
) -> list[Point]:
    """``points`` resampled and wobbled; see :func:`wobble_with_vertices`."""
    return wobble_with_vertices(
        points, amplitude=amplitude, wavelength=wavelength, seed=seed
    )[0]


def wobble_with_vertices(
    points: Sequence[Point],
    *,
    amplitude: float,
    wavelength: float,
    seed: str,
) -> tuple[list[Point], list[int]]:
    """``points`` resampled every ``wavelength / 8`` px and each sample moved
    up to ``amplitude`` px along the path's normal by seeded smooth noise.

    The original vertices are kept as samples (a corner stays a corner) and
    move along the bisector of their two legs. Raises ``ValueError`` when the
    result would carry more than :data:`MAX_WOBBLE_POINTS` points.

    Also returns, for each input point, its index in the output (where a
    vertex landed), so a caller can find the authored points on the wobbled
    line (:func:`an.stage.paths.drawn_polyline`).
    """
    cum = cumulative_lengths(points)
    length = cum[-1]
    n = wobble_point_count(length, wavelength)
    if n + len(points) > MAX_WOBBLE_POINTS:
        raise ValueError(
            f"a wobble of wavelength {wavelength:g} px over a {length:.0f} px path "
            f"is {n} points, more than {MAX_WOBBLE_POINTS} redrawn every frame: "
            "lengthen `wobble_wavelength`"
        )
    vertices = {cum[i]: i for i in range(1, len(points) - 1)}
    stations = sorted({*(length * k / n for k in range(n + 1)), *vertices})
    out: list[Point] = []
    where = {s: k for k, s in enumerate(stations)}
    landed = [0, *(where[cum[i]] for i in range(1, len(points) - 1)), len(stations) - 1]
    for s in stations:
        x, y = point_at(points, cum, s)
        edge = min(s, length - s) / wavelength
        envelope = _smoothstep(min(1.0, max(0.0, edge)))
        shift = amplitude * envelope * _noise(seed, s / wavelength)
        nx, ny = _station_normal(points, cum, s, vertices.get(s))
        out.append((x + nx * shift, y + ny * shift))
    return out, landed


def _station_normal(
    points: Sequence[Point], cum: Sequence[float], s: float, vertex: int | None
) -> Point:
    """The normal at arc length ``s``: its segment's, or at an interior vertex
    the bisector of the two legs that meet there (the incoming leg's normal
    when they fold back on each other)."""
    i = _segment_at(cum, s)
    nx, ny = _unit_normal(points, i)
    if vertex is None or vertex >= len(points) - 1:
        return nx, ny
    j = vertex
    while j < len(points) - 1 and not cum[j + 1] > cum[j]:
        j += 1
    if j >= len(points) - 1:
        return nx, ny
    mx, my = _unit_normal(points, j)
    bx, by = nx + mx, ny + my
    norm = math.sqrt(bx * bx + by * by)
    if not norm > 0:
        return nx, ny
    return bx / norm, by / norm
