"""Rigid falls in the stage plane: a let-go item's flight, landing, tip and bounce; a body toppling about a contact.

Two motions, both of a rigid drawing under gravity (stage px, ``y`` down, an
angle turning ``+x`` toward ``+y``, clockwise on screen), shared by the hold
layer's ``release`` (:mod:`an.stage.hold`) and the ``topple`` pass
(:mod:`an.stage.topple`):

- **A drop** (:func:`drop_track`): the item's centre flies a parabola from
  where it was let go, spinning at a CONSTANT rate (a body in the air has no
  torque on it), until its lowest point touches the floor slightly short of
  its rest angle; it then **tips** about that point onto its resting side
  (rotation about a fixed contact under gravity, the impact's angular momentum
  carried over), **bounces** a little (``bounce``, a coefficient of
  restitution) and comes to rest. A flat landing bounces straight up instead.
  Nothing eases into its rest pose: the old release's smooth-step rotation was
  what made a dropped musket read as floating.
- **A pivot fall** (:func:`pivot_fall`): a body turning about a fixed contact
  point under gravity from an angular velocity, until a ``stop`` function of
  its turn says it hit something (the floor, another body, a target).

Pure functions over points; no stage types. The item is a cloud of points
(its ink) about its centre of mass, at a reference pose; a pose is
``(cx, cy, turn)`` with ``turn`` the rotation from that reference.

>>> rod = [(-50.0, 0.0), (50.0, 0.0)]
>>> round(inertia(rod), 1)    # a uniform rod of length 100: L**2 / 12
833.3
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

__all__ = [
    "DFLT_BOUNCE",
    "DropTrack",
    "PivotFall",
    "stable_angles",
    "drop_track",
    "inertia",
    "pivot_fall",
]

Point = tuple[float, float]

#: Coefficient of restitution of a let-go item on the floor: the share of its
#: speed it keeps when it bounces (a clatter, not a rubber ball).
DFLT_BOUNCE: float = 0.15
#: The most a drop lands short of its rest angle and then tips onto its side
#: (radians): one end touches first, then it slaps down.
TIP_MAX: float = math.radians(20.0)
#: A rest angle nearer than this to the angle it falls at lands flat (radians).
FLAT_TOLERANCE: float = math.radians(2.0)
#: A side it must tip at least this far to fall off is one it can lie on (radians).
LIE_MIN: float = math.radians(15.0)
#: Bounces stop below these: a hop under ``MIN_HOP_PX`` px, a rock under ``MIN_ROCK``.
MIN_HOP_PX: float = 1.0
MIN_ROCK: float = math.radians(1.0)
#: At most this many bounces before it rests.
MAX_BOUNCES: int = 3
#: Integration step of a pivot fall (s): far under a frame.
SUBSTEP_S: float = 1.0 / 960.0
#: A pivot fall that has not stopped by then is cut (s).
PIVOT_CAP_S: float = 4.0


def _rot(p: Point, a: float) -> Point:
    c, s = math.cos(a), math.sin(a)
    return (c * p[0] - s * p[1], s * p[0] + c * p[1])


def inertia(points: Sequence[Point]) -> float:
    """Moment of inertia per unit mass about the centre (px²), from ink points
    on the drawing's outline: a third of their mean squared distance (a uniform
    rod's ``L²/12``, a square's ``a²/6``).

    >>> round(inertia([(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]), 3)  # a 2x2 square
    0.667
    """
    if not points:
        return 1.0
    return max(1e-6, sum(x * x + y * y for x, y in points) / len(points) / 3.0)


def _hull(points: Sequence[Point]) -> list[Point]:
    """The convex hull of ``points``, counter-clockwise in ``y``-up terms (monotone chain)."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def stable_angles(points: Sequence[Point]) -> list[float]:
    """The angles a rigid drawing can lie at on a floor: each side of its ink's
    convex hull turned to be the bottom, where its centre (the origin of
    ``points``) stands over that side with at least :data:`LIE_MIN` to tip
    before it falls off. Radians in ``(-pi, pi]``.

    >>> sorted(round(a, 3) for a in stable_angles([(-50.0, -2.0), (50.0, -2.0), (50.0, 2.0), (-50.0, 2.0)]))
    [0.0, 3.142]
    """
    hull = _hull(points)
    out: list[float] = []
    for a, b in zip(hull, hull[1:] + hull[:1]):
        ex, ey = b[0] - a[0], b[1] - a[1]
        length2 = ex * ex + ey * ey
        if length2 <= 1e-9:
            continue
        u = (-a[0] * ex - a[1] * ey) / length2  # the centre's foot on the side
        if not 0.0 < u < 1.0:
            continue
        # Stable enough to lie on: it must tip this far before it falls off the side
        # (a rod stood on its end is not lying).
        height = abs(a[0] * ey - a[1] * ex) / math.sqrt(length2)
        if math.atan2(min(u, 1.0 - u) * math.sqrt(length2), height) < LIE_MIN:
            continue
        # The side's outward normal (the hull's interior is to its left): turned to point down (+y).
        nx, ny = ey, -ex
        if nx * (-a[0]) + ny * (-a[1]) > 0:  # pointing at the centre: flip it
            nx, ny = -nx, -ny
        angle = math.remainder(math.pi / 2 - math.atan2(ny, nx), 2 * math.pi)
        if all(
            abs(math.remainder(angle - o, 2 * math.pi)) > FLAT_TOLERANCE for o in out
        ):
            out.append(angle)
    return out


@dataclass
class PivotFall:
    """A body turning about a fixed ``pivot``: ``turn(t)`` and ``centre(t)``
    for ``t`` from 0 to ``duration``; ``omega_end`` is its angular velocity when
    it stopped, ``stopped`` whether ``stop`` said so (else the cap or the end)."""

    pivot: Point
    centre0: Point
    times: list[float]
    turns: list[float]
    duration: float
    omega_end: float
    stopped: bool

    def turn(self, t: float) -> float:
        """The turn ``t`` s into the fall (linear between steps)."""
        if t <= 0.0:
            return self.turns[0]
        if t >= self.duration:
            return self.turns[-1]
        i = min(len(self.times) - 2, int(t / SUBSTEP_S))
        t0, t1 = self.times[i], self.times[i + 1]
        u = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
        return self.turns[i] + (self.turns[i + 1] - self.turns[i]) * u

    def centre(self, t: float) -> Point:
        """Where the centre is ``t`` s into the fall."""
        d = _rot(
            (self.centre0[0] - self.pivot[0], self.centre0[1] - self.pivot[1]),
            self.turn(t),
        )
        return (self.pivot[0] + d[0], self.pivot[1] + d[1])


def pivot_fall(
    centre: Point,
    pivot: Point,
    *,
    gravity: float,
    omega: float = 0.0,
    inertia_cm: float = 1.0,
    stop: Callable[[float], float] | None = None,
    cap: float = PIVOT_CAP_S,
) -> PivotFall:
    """A body whose centre is at ``centre`` turning about ``pivot`` under
    ``gravity`` (px/s², down), from angular velocity ``omega`` (rad/s,
    clockwise positive), until ``stop(turn)`` changes sign from positive (the
    gap to whatever it hits; the crossing is found to a fraction of a step) or
    ``cap`` seconds pass.

    The equation is the rigid pendulum's, inverted: ``I_p θ'' = g r_x`` with
    ``r`` from the pivot to the centre and ``I_p = I_cm + |r|²``.

    >>> f = pivot_fall((0.0, -100.0), (0.0, 0.0), gravity=980.0, omega=0.5,
    ...                inertia_cm=833.3, stop=lambda a: math.pi / 2 - a)
    >>> f.stopped, round(f.turn(f.duration), 3), 0.8 < f.duration < 1.2
    (True, 1.571, True)
    """
    r0 = (centre[0] - pivot[0], centre[1] - pivot[1])
    ip = inertia_cm + r0[0] ** 2 + r0[1] ** 2
    times, turns = [0.0], [0.0]
    a, w, t = 0.0, float(omega), 0.0
    gap = stop(a) if stop is not None else 1.0
    stopped = gap <= 0.0 and stop is not None
    while not stopped and t < cap:
        rx = _rot(r0, a)[0]
        w += gravity * rx / ip * SUBSTEP_S
        a_next = a + w * SUBSTEP_S
        g_next = stop(a_next) if stop is not None else 1.0
        if g_next <= 0.0:
            u = gap / (gap - g_next) if gap != g_next else 1.0
            a = a + (a_next - a) * u
            t += SUBSTEP_S * u
            stopped = True
        else:
            a, gap, t = a_next, g_next, t + SUBSTEP_S
        times.append(t)
        turns.append(a)
    return PivotFall(
        pivot=pivot,
        centre0=centre,
        times=times,
        turns=turns,
        duration=t,
        omega_end=w,
        stopped=stopped,
    )


@dataclass
class DropTrack:
    """A let-go item's motion from the instant it is let go (``t = 0``):
    :meth:`pose` gives ``(cx, cy, angle, scale_x, scale_y)`` at any ``t``.

    ``touch`` is when it first touches the floor, ``rest`` when it stops
    moving, ``bounces`` when each bounce lands (all seconds from the let-go);
    ``floor`` the line it comes to rest on.
    """

    touch: float
    rest: float
    bounces: list[float]
    #: The angle it comes to rest at.
    angle: float
    #: The floor line it lies on: ``ground``, or the line its lowest point was
    #: already on (below ``ground``) when it was let go touching the floor.
    floor: float
    _phases: list[
        tuple[float, float, Callable[[float], tuple[float, float, float]]]
    ] = field(repr=False)
    _scale: tuple[tuple[float, float], tuple[float, float]] = field(repr=False)

    def pose(self, t: float) -> tuple[float, float, float, float, float]:
        """``(cx, cy, angle, scale_x, scale_y)`` ``t`` s after the let-go."""
        (sx0, sy0), (sx1, sy1) = self._scale
        f = 1.0 if self.touch <= 0 else max(0.0, min(1.0, t / self.touch))
        sx, sy = sx0 + (sx1 - sx0) * f, sy0 + (sy1 - sy0) * f
        for start, end, at in self._phases:
            if t <= end + 1e-12:
                return (*at(max(0.0, t - start)), sx, sy)
        return (*self._phases[-1][2](self._phases[-1][1] - self._phases[-1][0]), sx, sy)


def _lowest(
    points: Sequence[Point], centre: Point, angle: float
) -> tuple[float, Point]:
    """The lowest (largest ``y``) of ``points`` (about the centre, at angle 0)
    turned by ``angle`` about ``centre``: ``(y, the point)``."""
    best = None
    for p in points:
        q = _rot(p, angle)
        w = (centre[0] + q[0], centre[1] + q[1])
        if best is None or w[1] > best[1]:
            best = w
    return best[1], best


def _drop_once(
    points: Sequence[Point],
    *,
    centre: Point,
    velocity: Point,
    angle: float,
    rest_angle: float | None,
    ground: float,
    gravity: float,
    scale: tuple[tuple[float, float], tuple[float, float]] = ((1.0, 1.0), (1.0, 1.0)),
    toss_x: float | None = None,
    arc: float = 0.0,
    bounce: float = DFLT_BOUNCE,
    inertia_cm: float | None = None,
) -> DropTrack:
    """The motion of a rigid item let go at ``centre`` with ``velocity``, at
    ``angle``, that comes to rest at ``rest_angle`` on the floor ``ground``
    (``None``: the side of it nearest to how it falls, :func:`stable_angles`:
    a let-go item lands the way it falls, it does not twirl to a set angle).

    points: the item's ink about its centre of mass, at angle 0 (already
        scaled as it lands)
    toss_x: thrown to land with its centre near this ``x`` (its horizontal
        speed is solved), rising ``arc`` px above where it was let go first
        (``arc`` 0: it is let fall, never thrown up)
    bounce: the coefficient of restitution (0: it lands dead)

    A drop never rises unless it is tossed: an upward ``velocity`` (the hand
    lifting as it lets go) is not carried over.

    >>> rod = [(-50.0, 0.0), (50.0, 0.0), (-50.0, 4.0), (50.0, 4.0)]
    >>> tr = drop_track(rod, centre=(0.0, 0.0), velocity=(0.0, 0.0), angle=0.6,
    ...                 rest_angle=0.0, ground=200.0, gravity=980.0)
    >>> 0.5 < tr.touch < tr.rest < 1.5, abs(round(tr.pose(tr.rest)[2], 3))
    (True, 0.0)
    >>> ys = [tr.pose(t)[1] for t in (0.0, 0.05, 0.1)]
    >>> ys == sorted(ys)   # it falls from the first frame: no rise, no hang
    True
    """
    g = float(gravity)
    if rest_angle is None:
        sides = stable_angles(points) or [angle]
        rest_angle = min(
            sides, key=lambda a: abs(math.remainder(a - angle, 2 * math.pi))
        )
    target = angle + math.remainder(rest_angle - angle, 2 * math.pi)
    delta = target - angle
    flat = abs(delta) <= FLAT_TOLERANCE
    tip = 0.0 if flat else math.copysign(min(abs(delta), TIP_MAX), delta)
    touch_angle = target - tip
    low, _p = _lowest(points, (0.0, 0.0), touch_angle)
    y_touch = ground - low  # the centre's height when the lowest point touches
    cx0, cy0 = centre
    vx, vy = velocity
    floor = ground
    tossed = arc > 0
    low_now, _p = _lowest(points, (0.0, 0.0), angle)
    if not tossed and cy0 + low_now >= ground - 1e-6:
        # Let go already touching the floor (or into it: in a 2.5D set, in
        # front of the floor line): it falls over that end, where it is.
        floor = cy0 + low_now
        touch_angle, tip, y_touch, toss_x = angle, (0.0 if flat else delta), cy0, None
        vx, vy = 0.0, 0.0
    elif not tossed and y_touch < cy0:
        # It would not clear the floor turned to where it lands: it falls
        # unturned, touches, and falls over the end that touched.
        touch_angle, tip = angle, (0.0 if flat else delta)
        y_touch = ground - low_now
    if tossed:
        apex = min(cy0, y_touch) - max(0.0, arc)
        up = math.sqrt(max(0.0, 2.0 * g * (cy0 - apex)))
        down = math.sqrt(max(0.0, 2.0 * (y_touch - apex) / g))
        air = up / g + down
        vy = -up
        if toss_x is not None:
            vx = (toss_x - cx0) / air if air > 0 else 0.0
    elif y_touch < cy0:
        # Let go already into the floor: the floor lifts it clear, no higher
        # (the hold layer warns: let go of it higher).
        vy = -math.sqrt(2.0 * g * (cy0 - y_touch))
        air = -vy / g
    else:
        vy = max(0.0, vy)
        dy = y_touch - cy0
        disc = vy * vy + 2.0 * g * dy
        air = (-vy + math.sqrt(disc)) / g if disc >= 0 and dy > 0 else 0.0
    if not tossed and toss_x is not None and air > 0:
        vx = (toss_x - cx0) / air  # let fall, nudged sideways to land at toss_x
    air = max(0.0, air)
    spin = (touch_angle - angle) / air if air > 0 else 0.0
    phases: list[
        tuple[float, float, Callable[[float], tuple[float, float, float]]]
    ] = []

    def flight(t: float) -> tuple[float, float, float]:
        return (cx0 + vx * t, cy0 + vy * t + 0.5 * g * t * t, angle + spin * t)

    phases.append((0.0, air, flight))
    c_touch = (cx0 + vx * air, cy0 + vy * air + 0.5 * g * air * air)
    v_touch = (vx, vy + g * air)
    i_cm = inertia(points) if inertia_cm is None else inertia_cm
    t = air
    bounces: list[float] = []
    if tip == 0.0:
        # Flat: hops straight up, each one ``bounce`` times as fast.
        v = v_touch[1] * bounce
        cx, cy = c_touch
        for _ in range(MAX_BOUNCES):
            if v * v / (2.0 * g) < MIN_HOP_PX:
                break
            hop = 2.0 * v / g

            def hopping(u: float, v=v, cx=cx, cy=cy) -> tuple[float, float, float]:
                return (cx, cy - v * u + 0.5 * g * u * u, target)

            phases.append((t, t + hop, hopping))
            t += hop
            bounces.append(t)
            v *= bounce
        phases.append((t, t, lambda u, cx=cx, cy=cy: (cx, cy, target)))
        return DropTrack(
            touch=air,
            rest=t,
            bounces=bounces,
            floor=floor,
            angle=target,
            _phases=phases,
            _scale=scale,
        )
    # One end touches first: it tips about it onto its side, then rocks.
    _y, pivot = _lowest(points, c_touch, touch_angle)
    r = (c_touch[0] - pivot[0], c_touch[1] - pivot[1])
    ip = i_cm + r[0] ** 2 + r[1] ** 2
    omega = (i_cm * spin + (r[0] * v_touch[1] - r[1] * v_touch[0])) / ip
    sign = 1.0 if tip > 0 else -1.0
    fall = pivot_fall(
        c_touch,
        pivot,
        gravity=g,
        omega=omega,
        inertia_cm=i_cm,
        stop=lambda a: sign * (tip - a),
    )
    if (
        not fall.stopped
    ):  # pushed the other way harder than gravity brings it back: no tip
        final = (c_touch[0], c_touch[1], target)
        phases.append((t, t, lambda u: final))
        return DropTrack(
            touch=air,
            rest=t,
            bounces=bounces,
            floor=floor,
            angle=target,
            _phases=phases,
            _scale=scale,
        )

    def tipping(u: float, fall=fall) -> tuple[float, float, float]:
        c = fall.centre(u)
        return (c[0], c[1], touch_angle + fall.turn(u))

    phases.append((t, t + fall.duration, tipping))
    t += fall.duration
    centre_now = fall.centre(fall.duration)
    omega = -bounce * fall.omega_end
    for _ in range(MAX_BOUNCES):
        # The far end bounces up about the same contact and falls back flat.
        rock = pivot_fall(
            centre_now,
            pivot,
            gravity=g,
            omega=omega,
            inertia_cm=i_cm,
            stop=lambda a: 1e-9 - sign * a,
        )
        if not rock.stopped or max(abs(a) for a in rock.turns) < MIN_ROCK:
            break

        def rocking(u: float, rock=rock) -> tuple[float, float, float]:
            c = rock.centre(u)
            return (c[0], c[1], target + rock.turn(u))

        phases.append((t, t + rock.duration, rocking))
        t += rock.duration
        bounces.append(t)
        omega = -bounce * rock.omega_end
    final = (centre_now[0], centre_now[1], target)
    phases.append((t, t, lambda u: final))
    return DropTrack(
        touch=air,
        rest=t,
        bounces=bounces,
        floor=floor,
        angle=target,
        _phases=phases,
        _scale=scale,
    )


#: Rounds of aiming a toss so it comes to rest (after its tip) centred on its ``x``.
TOSS_AIM_ROUNDS: int = 4


def drop_track(points: Sequence[Point], **kw) -> DropTrack:
    """The motion of a rigid item let go (:func:`_drop_once` has the
    parameters); a toss ``toss_x`` is aimed so that the item comes to REST,
    after the tip onto its side, centred on that ``x``.

    >>> rod = [(-50.0, 0.0), (50.0, 0.0), (-50.0, 4.0), (50.0, 4.0)]
    >>> tr = drop_track(rod, centre=(0.0, 0.0), velocity=(0.0, 0.0), angle=0.6,
    ...                 rest_angle=0.0, ground=200.0, gravity=980.0, toss_x=120.0, arc=30.0)
    >>> round(tr.pose(tr.rest)[0], 3)
    120.0
    """
    target = kw.get("toss_x")
    track = _drop_once(points, **kw)
    if target is None:
        return track
    aim = target
    for _ in range(TOSS_AIM_ROUNDS):
        miss = track.pose(track.rest)[0] - target
        if abs(miss) < 1e-5:
            break
        aim -= miss
        track = _drop_once(points, **{**kw, "toss_x": aim})
    return track
