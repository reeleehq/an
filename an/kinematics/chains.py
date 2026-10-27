"""Closed-form pieces for chains: the two-link reach and its reachable range,
and the arc a longer chain held at both ends sags on (:func:`arc_chain`).

A two-link chain (an upper arm and a forearm, a thigh and a shin) with its
root held and its tip asked for is the common case of every puppet, and it
has an exact answer by the law of cosines. The solver uses it as the initial
guess for such chains before projecting (so the common case converges in a
round and the bend side is an explicit choice, never an interpolation), and
callers use it directly to ask whether a grip is in reach at all.

>>> t1, t2 = two_bone((0.0, 0.0), (5.0, 0.0), (3.0, 4.0))
>>> tip = (3.0 * math.cos(t1) + 4.0 * math.cos(t2), 3.0 * math.sin(t1) + 4.0 * math.sin(t2))
>>> tuple(round(c, 9) for c in tip)
(5.0, 0.0)
>>> two_bone((0.0, 0.0), (8.0, 0.0), (3.0, 4.0)) is None
True
"""

from __future__ import annotations

import math
from collections.abc import Sequence

#: Below this distance a target coincides with the root and the chain's
#: direction is undefined: reported as unreachable rather than guessed.
_COINCIDENT: float = 1e-12


def reach(l1: float, l2: float) -> tuple[float, float]:
    """The ``(nearest, farthest)`` distance from the root a two-link chain of
    lengths ``l1`` and ``l2`` can put its tip.

    >>> reach(3.0, 4.0)
    (1.0, 7.0)
    """
    return (abs(l1 - l2), l1 + l2)


def two_bone(
    root: tuple[float, float],
    target: tuple[float, float],
    lengths: tuple[float, float],
    *,
    bend: int = 1,
) -> tuple[float, float] | None:
    """Absolute angles ``(theta1, theta2)`` of two links of ``lengths``
    ``(l1, l2)`` hinged at ``root`` so that the tip meets ``target``; ``None``
    when the target is out of :func:`reach`.

    ``bend`` is ``+1`` for a middle joint that deviates counter-clockwise from
    the root-to-target line (which, on a y-down screen, reads as clockwise),
    ``-1`` for the other side. Each side is a different pose of the same chain;
    which one is right is the author's (or a hinge range's) choice.

    >>> t1, t2 = two_bone((0.0, 0.0), (1.0, 1.0), (1.0, 1.0), bend=1)
    >>> round(math.degrees(t1)), round(math.degrees(t2))
    (90, 0)
    >>> t1, t2 = two_bone((0.0, 0.0), (1.0, 1.0), (1.0, 1.0), bend=-1)
    >>> round(math.degrees(t1)), round(math.degrees(t2))
    (0, 90)
    """
    l1, l2 = lengths
    dx, dy = target[0] - root[0], target[1] - root[1]
    dist = math.hypot(dx, dy)
    lo, hi = reach(l1, l2)
    if dist < _COINCIDENT or dist > hi or dist < lo:
        return None
    cos_a = (l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist)
    a = math.acos(max(-1.0, min(1.0, cos_a)))
    cos_b = (l1 * l1 + l2 * l2 - dist * dist) / (2.0 * l1 * l2)
    b = math.acos(max(-1.0, min(1.0, cos_b)))
    theta1 = math.atan2(dy, dx) + bend * a
    theta2 = theta1 - bend * (math.pi - b)
    return theta1, theta2


#: Bisection steps for :func:`arc_chain`'s radius: far past float precision.
_ARC_STEPS: int = 80


def arc_chain(
    root: tuple[float, float],
    target: tuple[float, float],
    lengths: Sequence[float],
    *,
    bend: int = 1,
) -> list[float] | None:
    """Absolute angles of links of ``lengths``, end to end from ``root``, laid
    on one circular arc whose ends are ``root`` and ``target``: the slack pose
    of a chain held at both ends nearer than its length (an#646), which no
    two-link form gives a long chain. ``None`` when the chain cannot sag
    (``target`` at or past its length, or on the root) or no arc fits.

    ``bend`` is the side, as for :func:`two_bone`: ``+1`` sags
    counter-clockwise of the root-to-target line.

    >>> angles = arc_chain((0.0, 0.0), (35.0, 0.0), [1.0] * 50)
    >>> tip = (sum(math.cos(a) for a in angles), sum(math.sin(a) for a in angles))
    >>> tuple(round(c, 9) for c in tip)
    (35.0, 0.0)
    >>> arc_chain((0.0, 0.0), (60.0, 0.0), [1.0] * 50) is None
    True
    """
    d = math.hypot(target[0] - root[0], target[1] - root[1])
    total = float(sum(lengths))
    if d < _COINCIDENT or d >= total or not lengths:
        return None

    def turned(radius: float) -> float:  # the arc's central angle
        return sum(2.0 * math.asin(min(1.0, l / (2.0 * radius))) for l in lengths)

    def chord(radius: float) -> float:
        phi = turned(radius)
        return 2.0 * radius * math.sin(phi / 2.0) if phi <= 2.0 * math.pi else -1.0

    lo, hi = max(lengths) / 2.0, total  # chord(lo) <= d < chord(hi)
    while chord(hi) <= d:
        hi *= 2.0
    if chord(lo) > d:
        return None
    for _ in range(_ARC_STEPS):
        mid = (lo + hi) / 2.0
        lo, hi = (mid, hi) if chord(mid) <= d else (lo, mid)
    radius = hi
    deltas = [2.0 * math.asin(min(1.0, l / (2.0 * radius))) for l in lengths]
    phi = sum(deltas)
    start = math.atan2(target[1] - root[1], target[0] - root[0])
    out, swept = [], 0.0
    for delta in deltas:
        out.append(start + bend * (phi / 2.0 - swept - delta / 2.0))
        swept += delta
    return out
