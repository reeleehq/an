"""Joints: declared relations between two bodies, or a body and the world.

Every joint names its points as :class:`~an.kinematics.bodies.Point`\\ s and
carries ``joined`` (the caller's time dimension: an unjoined joint is kept in
the list, so its index is stable, and simply not enforced) and ``compliance``
(0 is rigid; a positive value is a softness in units of distance per unit of
force, which XPBD keeps independent of the iteration count).

- :class:`Pin`: two points coincide; the bodies turn freely about them.
- :class:`Hinge`: a pin plus a range for the relative angle, about the
  relative angle the bodies have on the solve's input (or the first frame
  of a run), or an explicit ``rest``.
- :class:`Weld`: a pin plus a fixed relative angle.
- :class:`Distance`: the two points keep a length: ``equal`` (a rod),
  ``at_most`` (a rope or string: slack is free), ``at_least`` (a spacer).
- :class:`Slide`: a point stays on a segment of another body (a groove).
- :class:`Contact`: a point stays on the free side of a segment, or on it
  (a foot on the ground, a lamp on a table); one-sided, and only over the
  segment's own extent, so a body slides off an edge.

A segment's free side: with the segment running from ``start`` to ``end``,
the free side is the one a y-down screen shows ABOVE a left-to-right
segment (normal ``(ty, -tx)``).

>>> Distance(Point("a", 0.5, 0.5), Point("b", 0.5, 0.5), length=10.0).mode
'equal'
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from an.kinematics.bodies import Point

#: The ways a :class:`Distance` joint may hold its length.
DistanceMode = Literal["equal", "at_most", "at_least"]


@dataclass(frozen=True)
class Pin:
    """Two points coincide; free rotation about them.

    >>> Pin(Point("arm", 0.0, 0.5), Point("torso", 1.0, 0.2)).joined
    True
    """

    a: Point
    b: Point
    compliance: float = 0.0
    joined: bool = True


@dataclass(frozen=True)
class Hinge:
    """A pin with a range for the angle of ``b``'s body relative to ``a``'s.

    ``limits`` is ``(lo, hi)`` in radians about ``rest``, within
    ``[-pi, pi]``; ``rest`` is the relative angle (``b.rotation -
    a.rotation``) the range is measured from, taken from the bodies' poses at
    the start of the solve when ``None``. With no ``limits`` it is a pin.

    >>> Hinge(Point("fore", 0.0, 0.5), Point("upper", 1.0, 0.5), limits=(-2.6, 0.0)).limits
    (-2.6, 0.0)
    """

    a: Point
    b: Point
    limits: tuple[float, float] | None = None
    rest: float | None = None
    compliance: float = 0.0
    joined: bool = True


@dataclass(frozen=True)
class Weld:
    """A pin plus a fixed relative angle (``rest``, or the starting one).

    >>> Weld(Point("hat", 0.5, 1.0), Point("head", 0.5, 0.0)).rest is None
    True
    """

    a: Point
    b: Point
    rest: float | None = None
    compliance: float = 0.0
    joined: bool = True


@dataclass(frozen=True)
class Distance:
    """The two points keep ``length`` apart: exactly, at most, or at least.

    >>> Distance(Point("hand", 0.5, 0.5), Point("world", 0.0, -200.0), length=150.0, mode="at_most").mode
    'at_most'
    """

    a: Point
    b: Point
    length: float
    mode: DistanceMode = "equal"
    compliance: float = 0.0
    joined: bool = True


@dataclass(frozen=True)
class Slide:
    """``point`` stays on the segment ``start``–``end`` (both on one other
    body, or the world), within its ends.

    >>> Slide(Point("bead", 0.5, 0.5), Point("world", 0.0, 0.0), Point("world", 100.0, 0.0)).joined
    True
    """

    point: Point
    start: Point
    end: Point
    compliance: float = 0.0
    joined: bool = True


@dataclass(frozen=True)
class Contact:
    """``point`` stays on the free side of the segment ``start``–``end``, or
    on it; nothing holds it there (it may lift off), and nothing holds it
    beyond the segment's ends (it may fall off an edge).

    >>> Contact(Point("lamp", 0.5, 1.0), Point("table", 0.0, 0.0), Point("table", 1.0, 0.0)).joined
    True
    """

    point: Point
    start: Point
    end: Point
    compliance: float = 0.0
    joined: bool = True


#: Every joint kind, in the order the module documents them.
Joint = Pin | Hinge | Weld | Distance | Slide | Contact


@dataclass(frozen=True)
class Force:
    """A driver that is not a target: a constant ``vector`` (force per unit
    mass, applied at ``point``, so an off-centre push also turns the body), or
    a pull of ``point`` ``toward`` a position with ``strength`` (a compliant
    zero-length rope: ``compliance = 1 / strength``), or both.

    >>> Force(Point("kite", 0.5, 0.0), vector=(30.0, 0.0)).toward is None
    True
    """

    point: Point
    vector: tuple[float, float] | None = None
    toward: tuple[float, float] | Point | None = None
    strength: float = 1.0
