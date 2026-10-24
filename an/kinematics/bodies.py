"""Bodies and the points on them: the things a joint joins and a driver moves.

A :class:`Body` is a rigid rectangle of ``width`` by ``height`` (its *extent*)
posed in one frame by ``(x, y, rotation, scale)``: the pose point is the
body's ``origin``, a fraction of the extent (``(0.5, 0.5)`` is the centre,
``(0.5, 0.0)`` the middle of the top edge: where a hanging part is hinged). A
:class:`Point` on a body is likewise a fraction ``(u, v)`` of the extent, so a
caller that knows its landmarks (a bone, a grip, a corner) resolves them to
fractions once and the solver never learns their names. The world is the body
named :data:`WORLD`: a point on it is an absolute position.

Nothing here imports the scene IR or the stage: a body is four numbers and an
extent, which is what lets this package be described without naming an
animation (``# extraction candidate``: it becomes its own package when a
second consumer exists).

>>> arm = Body("arm", x=10.0, y=20.0, width=60.0, height=10.0, origin=(0.0, 0.5))
>>> point_world(arm, Point("arm", 1.0, 0.5))   # the far end of an unrotated arm
(70.0, 20.0)
>>> point_world(arm, Point(WORLD, 3.0, 4.0))   # a world point is itself
(3.0, 4.0)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

#: The name of the world body: a :class:`Point` on it is an absolute position,
#: and it has infinite mass (a joint to it is a joint to the ground).
WORLD: str = "world"

#: Density of a body whose caller gave none: mass = density × area. Only the
#: RATIO of masses matters to a solve (a heavy prop drags a light arm), so one
#: unit per square unit of extent is the natural default.
DFLT_DENSITY: float = 1.0

#: Where a body's pose point sits by default: the centre of its extent.
DFLT_ORIGIN: tuple[float, float] = (0.5, 0.5)


@dataclass(frozen=True)
class Point:
    """A point on a body, as a fraction of the body's extent.

    On :data:`WORLD` the fraction is an absolute position instead.

    >>> Point("hand", 0.5, 1.0).body
    'hand'
    """

    body: str
    u: float
    v: float


@dataclass(frozen=True)
class Body:
    """A rigid rectangle posed in one frame.

    ``fixed`` bodies have infinite mass: joints move everything else around
    them. ``vx``, ``vy`` (the velocity of the extent's centre) and ``omega``
    are what a dynamic solve carries from one frame to the next (zero at
    rest). ``density`` sets the mass per unit area, spread evenly over the
    extent, so a limb whose pose point is at its end still swings about it.

    >>> b = Body("box", width=4.0, height=2.0)
    >>> round(mass(b), 3), round(inertia(b), 3)
    (8.0, 13.333)
    """

    name: str
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    scale: float = 1.0
    width: float = 1.0
    height: float = 1.0
    origin: tuple[float, float] = DFLT_ORIGIN
    fixed: bool = False
    density: float = DFLT_DENSITY
    vx: float = 0.0
    vy: float = 0.0
    omega: float = 0.0

    def posed(
        self,
        *,
        x: float | None = None,
        y: float | None = None,
        rotation: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
        omega: float | None = None,
    ) -> Body:
        """This body with the given pose channels (and velocities) replaced.

        >>> Body("b").posed(x=3.0).x
        3.0
        """
        updates = {
            k: v
            for k, v in dict(
                x=x, y=y, rotation=rotation, vx=vx, vy=vy, omega=omega
            ).items()
            if v is not None
        }
        return replace(self, **updates)


def mass(body: Body) -> float:
    """The body's mass: density × scaled area; ``inf`` for a fixed body.

    >>> mass(Body("b", width=3.0, height=2.0, scale=2.0))
    24.0
    >>> mass(Body("b", fixed=True))
    inf
    """
    if body.fixed:
        return math.inf
    return body.density * body.width * body.height * body.scale * body.scale


def inertia(body: Body) -> float:
    """Rotational inertia about the body's pose point (parallel-axis from the
    extent's centre); ``inf`` for a fixed body.

    >>> round(inertia(Body("b", width=4.0, height=2.0, origin=(0.0, 0.5))), 3)
    45.333
    """
    m = mass(body)
    if math.isinf(m):
        return math.inf
    w, h = body.width * body.scale, body.height * body.scale
    cx = (0.5 - body.origin[0]) * w
    cy = (0.5 - body.origin[1]) * h
    return m * (w * w + h * h) / 12.0 + m * (cx * cx + cy * cy)


def local_offset(body: Body, point: Point) -> tuple[float, float]:
    """The point's offset from the body's pose point, in the body's own
    (unrotated) frame, scaled.

    >>> local_offset(Body("b", width=10.0, height=4.0), Point("b", 1.0, 0.0))
    (5.0, -2.0)
    """
    return (
        (point.u - body.origin[0]) * body.width * body.scale,
        (point.v - body.origin[1]) * body.height * body.scale,
    )


def point_world(body: Body, point: Point) -> tuple[float, float]:
    """The point's position in the body's frame of reference (the world, for
    a body posed in it); a :data:`WORLD` point is returned as is.

    >>> b = Body("b", x=1.0, y=1.0, rotation=math.pi / 2, width=2.0, height=2.0)
    >>> tuple(round(c, 9) for c in point_world(b, Point("b", 1.0, 0.5)))
    (1.0, 2.0)
    """
    if point.body == WORLD:
        return (float(point.u), float(point.v))
    lx, ly = local_offset(body, point)
    c, s = math.cos(body.rotation), math.sin(body.rotation)
    return (body.x + c * lx - s * ly, body.y + s * lx + c * ly)
