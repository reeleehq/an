"""Closed-form pieces for chains: the two-link reach and its reachable range.

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
