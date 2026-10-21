"""Prototype of a 2D puppet solver, for measurements that back the research report.

Pure Python, no dependencies. Three solvers that the report compares:

- :func:`two_bone_ik`: the analytic two-bone solve (law of cosines), exact.
- :func:`fabrik`: FABRIK on a chain of fixed-length links (Aristidou & Lasenby 2011).
- :class:`Puppet`: a position-based solver (Jakobsen 2001 / PBD) over particles
  (joint points) joined by sticks (rigid parts), with pins (rods: hard position
  targets), strings (unilateral max-length constraints), hinge angle limits, and
  gravity. Two modes: :meth:`Puppet.settle` (quasi-static: a pure function of the
  targets at one instant) and :meth:`Puppet.step` (dynamic: Verlet, history-dependent).

Everything is deterministic by construction: fixed constraint order, fixed
iteration counts, fixed substeps, IEEE doubles.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

Vec = tuple[float, float]


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1])


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1])


def mul(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k)


def length(a: Vec) -> float:
    return math.hypot(a[0], a[1])


def angle_of(a: Vec) -> float:
    return math.atan2(a[1], a[0])


def polar(theta: float, r: float) -> Vec:
    return (r * math.cos(theta), r * math.sin(theta))


def wrap_angle(theta: float) -> float:
    """``theta`` wrapped into ``(-pi, pi]``."""
    return math.atan2(math.sin(theta), math.cos(theta))


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


# -----------------------------------------------------------------------------
# Analytic two-bone IK
# -----------------------------------------------------------------------------


def two_bone_ik(
    root: Vec, l1: float, l2: float, target: Vec, *, bend: int = 1
) -> tuple[float, float] | None:
    """Absolute angles ``(theta1, theta2)`` of two links of lengths ``l1``, ``l2``
    hinged at ``root`` so the tip meets ``target``; ``None`` when unreachable.

    ``bend`` is +1 for an elbow that deviates counter-clockwise from the
    root-target line (screen coordinates: y down), -1 for the other side.

    >>> t1, t2 = two_bone_ik((0.0, 0.0), 3.0, 4.0, (5.0, 0.0))
    >>> tip = add(polar(t1, 3.0), polar(t2, 4.0))
    >>> round(tip[0], 9), round(tip[1], 9)
    (5.0, 0.0)
    >>> two_bone_ik((0.0, 0.0), 3.0, 4.0, (8.0, 0.0)) is None
    True
    """
    d = sub(target, root)
    dist = length(d)
    if dist > l1 + l2 or dist < abs(l1 - l2) or dist == 0.0:
        return None
    cos_a = (l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist)
    a = math.acos(_clamp(cos_a, -1.0, 1.0))
    cos_b = (l1 * l1 + l2 * l2 - dist * dist) / (2.0 * l1 * l2)
    b = math.acos(_clamp(cos_b, -1.0, 1.0))
    theta1 = angle_of(d) + bend * a
    theta2 = theta1 - bend * (math.pi - b)
    return theta1, theta2


# -----------------------------------------------------------------------------
# FABRIK
# -----------------------------------------------------------------------------


def fabrik(
    joints: Sequence[Vec],
    target: Vec,
    *,
    tolerance: float = 1e-3,
    max_iterations: int = 100,
) -> tuple[list[Vec], int, float]:
    """FABRIK: move the chain ``joints`` (root first) so its tip reaches ``target``.

    Returns ``(new joints, iterations used, final tip error)``. The root stays
    put. An unreachable target straightens the chain toward it (one pass).

    >>> pts, n, err = fabrik([(0, 0), (1, 0), (2, 0), (3, 0)], (0, 2.5))
    >>> err < 1e-3, n < 100
    (True, True)
    """
    pts = [tuple(map(float, p)) for p in joints]
    lengths = [length(sub(pts[i + 1], pts[i])) for i in range(len(pts) - 1)]
    root = pts[0]
    total = sum(lengths)
    if length(sub(target, root)) > total:
        # Unreachable: point every link at the target.
        for i in range(len(pts) - 1):
            r = lengths[i]
            d = sub(target, pts[i])
            pts[i + 1] = add(pts[i], mul(d, r / length(d)))
        return pts, 1, length(sub(pts[-1], target))
    err = length(sub(pts[-1], target))
    n = 0
    while err > tolerance and n < max_iterations:
        n += 1
        # Backward reach: tip to target, walk to root.
        pts[-1] = target
        for i in range(len(pts) - 2, -1, -1):
            r = lengths[i]
            d = sub(pts[i], pts[i + 1])
            pts[i] = add(pts[i + 1], mul(d, r / length(d)))
        # Forward reach: root back home, walk to tip.
        pts[0] = root
        for i in range(len(pts) - 1):
            r = lengths[i]
            d = sub(pts[i + 1], pts[i])
            pts[i + 1] = add(pts[i], mul(d, r / length(d)))
        err = length(sub(pts[-1], target))
    return pts, n, err


# -----------------------------------------------------------------------------
# Position-based puppet: particles, sticks, pins, strings, hinge limits, gravity
# -----------------------------------------------------------------------------

Target = Callable[[float], Vec]


@dataclass
class Stick:
    """A rigid part: the distance between joint particles ``i`` and ``j`` is fixed."""

    i: int
    j: int
    length: float


@dataclass
class String:
    """A marionette string: particle ``i`` may not be further than ``max_length``
    from ``anchor(t)``; closer is slack (unilateral)."""

    i: int
    anchor: Target
    max_length: float


@dataclass
class Pin:
    """A rod: particle ``i`` sits exactly at ``target(t)`` (infinite mass)."""

    i: int
    target: Target


@dataclass
class HingeLimit:
    """The signed angle at joint ``b`` from link ``(b -> a)`` to link ``(b -> c)``
    stays within ``[lo, hi]`` radians."""

    a: int
    b: int
    c: int
    lo: float
    hi: float


@dataclass
class Puppet:
    """Particles are joint points; parts are sticks between them.

    >>> p = Puppet(positions=[(0, 0), (0, 10)], sticks=[Stick(0, 1, 10.0)],
    ...            pins=[Pin(0, lambda t: (0.0, 0.0))])
    >>> n = p.settle(0.0)
    >>> round(p.positions[1][1], 3), abs(p.positions[1][0]) < 1e-6
    (10.0, True)
    """

    positions: list[Vec]
    sticks: list[Stick] = field(default_factory=list)
    strings: list[String] = field(default_factory=list)
    pins: list[Pin] = field(default_factory=list)
    limits: list[HingeLimit] = field(default_factory=list)
    gravity: Vec = (0.0, 980.0)  # px/s^2, screen y down
    damping: float = 0.02  # Verlet velocity damping per substep
    previous: list[Vec] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.positions = [tuple(map(float, p)) for p in self.positions]
        if not self.previous:
            self.previous = list(self.positions)
        self._pinned = {pin.i for pin in self.pins}

    # -- constraint projection (Gauss-Seidel, fixed order) --------------------

    def _project(self, t: float) -> float:
        """One pass over every constraint; returns the largest correction."""
        pos = self.positions
        worst = 0.0
        for pin in self.pins:
            pos[pin.i] = pin.target(t)
        for s in self.sticks:
            a, b = pos[s.i], pos[s.j]
            d = sub(b, a)
            dist = length(d)
            if dist == 0.0:
                continue
            diff = (dist - s.length) / dist
            wa = 0.0 if s.i in self._pinned else 1.0
            wb = 0.0 if s.j in self._pinned else 1.0
            if wa + wb == 0.0:
                continue
            ca, cb = wa / (wa + wb), wb / (wa + wb)
            pos[s.i] = add(a, mul(d, diff * ca))
            pos[s.j] = sub(b, mul(d, diff * cb))
            worst = max(worst, abs(dist - s.length))
        for st in self.strings:
            if st.i in self._pinned:
                continue
            anchor = st.anchor(t)
            d = sub(pos[st.i], anchor)
            dist = length(d)
            if dist > st.max_length:
                pos[st.i] = add(anchor, mul(d, st.max_length / dist))
                worst = max(worst, dist - st.max_length)
        for lim in self.limits:
            a, b, c = pos[lim.a], pos[lim.b], pos[lim.c]
            theta = wrap_angle(angle_of(sub(c, b)) - angle_of(sub(a, b)))
            delta = 0.0
            if theta < lim.lo:
                delta = lim.lo - theta
            elif theta > lim.hi:
                delta = lim.hi - theta
            if delta:
                # Rotate the free end(s) about the joint; a pinned end does not move.
                wa = 0.0 if lim.a in self._pinned else 1.0
                wc = 0.0 if lim.c in self._pinned else 1.0
                if wa + wc == 0.0:
                    continue
                share_c = wc / (wa + wc)
                share_a = wa / (wa + wc)
                pos[lim.c] = add(b, _rotate(sub(c, b), delta * share_c))
                pos[lim.a] = add(b, _rotate(sub(a, b), -delta * share_a))
                worst = max(worst, abs(delta))
        return worst

    # -- quasi-static: a pure function of the targets at time t ---------------

    def settle(
        self, t: float, *, max_rounds: int = 2000, eps: float = 1e-3,
        dt: float = 1.0 / 60.0, damping: float = 0.15, iterations: int = 8,
    ) -> int:
        """The pose at time ``t`` once everything has come to rest: heavily
        damped Verlet steps with the pins and strings HELD at ``t`` until no
        particle moves more than ``eps`` per step. Velocity-free at the end, so
        the same inputs always give the same pose (a pure function of ``t``).
        Returns the steps used (``max_rounds`` when it did not come to rest)."""
        n = 0
        saved = self.damping
        self.damping = damping
        self.previous = list(self.positions)
        try:
            while n < max_rounds:
                n += 1
                before = list(self.positions)
                self.step(t, dt, substeps=1, iterations=iterations, hold_time=True)
                moved = max(length(sub(p, q)) for p, q in zip(self.positions, before))
                if moved < eps:
                    break
        finally:
            self.damping = saved
        self.previous = list(self.positions)
        return n

    # -- dynamic: Verlet with history ------------------------------------------

    def step(
        self, t: float, dt: float, *, substeps: int = 4, iterations: int = 8,
        hold_time: bool = False,
    ) -> float:
        """Advance from ``t`` by ``dt``; returns the worst constraint error after
        the last projection."""
        h = dt / substeps
        worst = 0.0
        for k in range(substeps):
            tk = t if hold_time else t + (k + 1) * h
            for i in range(len(self.positions)):
                if i in self._pinned:
                    continue
                p, q = self.positions[i], self.previous[i]
                v = mul(sub(p, q), 1.0 - self.damping)
                self.previous[i] = p
                self.positions[i] = add(add(p, v), mul(self.gravity, h * h))
            for _ in range(iterations):
                worst = self._project(tk)
        return worst

    def digest(self, *, quantum: float = 1e-6) -> str:
        """A hash of the pose, quantized to ``quantum`` (what a baked document
        would store)."""
        import hashlib

        q = [(round(x / quantum), round(y / quantum)) for x, y in self.positions]
        return hashlib.sha256(repr(q).encode()).hexdigest()[:16]


def hinge_limit_about_rest(
    pos: dict[str, Vec], idx: dict[str, int], a: str, b: str, c: str,
    *, close: float, open: float = 0.0,
) -> HingeLimit:
    """A :class:`HingeLimit` at joint ``b`` allowing the joint to CLOSE (the
    interior angle to shrink) by ``close`` radians and to OPEN by ``open``
    radians from its rest angle, whichever way round the rest pose bends."""
    rest = wrap_angle(angle_of(sub(pos[c], pos[b])) - angle_of(sub(pos[a], pos[b])))
    # The interior angle shrinks when |theta| shrinks; the sign of rest says which side.
    sign = 1.0 if rest >= 0 else -1.0
    lo, hi = sorted((rest - sign * close, rest + sign * open))
    return HingeLimit(idx[a], idx[b], idx[c], lo, hi)


def _rotate(v: Vec, theta: float) -> Vec:
    c, s = math.cos(theta), math.sin(theta)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def marionette(*, scale: float = 1.0) -> tuple[Puppet, dict[str, int]]:
    """An eleven-joint marionette (pelvis, neck, head, elbows, hands, knees, feet)
    on five strings from a control bar: head, both hands, both knees."""
    names = [
        "pelvis", "neck", "head", "elbow_l", "hand_l", "elbow_r", "hand_r",
        "knee_l", "foot_l", "knee_r", "foot_r",
    ]
    idx = {n: i for i, n in enumerate(names)}
    s = scale
    pos = {
        "pelvis": (0, 0), "neck": (0, -60 * s), "head": (0, -100 * s),
        "elbow_l": (-30 * s, -30 * s), "hand_l": (-30 * s, 0),
        "elbow_r": (30 * s, -30 * s), "hand_r": (30 * s, 0),
        "knee_l": (-12 * s, 50 * s), "foot_l": (-12 * s, 100 * s),
        "knee_r": (12 * s, 50 * s), "foot_r": (12 * s, 100 * s),
    }
    positions = [pos[n] for n in names]

    def stick(a: str, b: str) -> Stick:
        return Stick(idx[a], idx[b], length(sub(pos[b], pos[a])))

    sticks = [
        stick("pelvis", "neck"), stick("neck", "head"),
        stick("neck", "elbow_l"), stick("elbow_l", "hand_l"),
        stick("neck", "elbow_r"), stick("elbow_r", "hand_r"),
        stick("pelvis", "knee_l"), stick("knee_l", "foot_l"),
        stick("pelvis", "knee_r"), stick("knee_r", "foot_r"),
    ]
    # Control bar: bobs 10 px at 1 Hz and sways 20 px at 0.5 Hz.
    def bar(dx: float, dy: float) -> Target:
        return lambda t: (dx + 20 * s * math.sin(2 * math.pi * 0.5 * t),
                          dy + 10 * s * math.sin(2 * math.pi * 1.0 * t))

    strings = [
        String(idx["head"], bar(0, -200 * s), 100 * s),
        String(idx["hand_l"], bar(-40 * s, -200 * s), 200 * s),
        String(idx["hand_r"], bar(40 * s, -200 * s), 200 * s),
        String(idx["knee_l"], bar(-20 * s, -200 * s), 250 * s),
        String(idx["knee_r"], bar(20 * s, -200 * s), 250 * s),
    ]
    deg = math.pi / 180
    # Elbows and knees: a range about the REST angle (closing by up to 150
    # degrees, opening by 0), so the sign convention comes from the pose, not
    # from the author (the first draft hand-typed the knees' signs and got
    # them inverted; measured as 88 px of permanent constraint conflict).
    limits = [
        hinge_limit_about_rest(pos, idx, "neck", "elbow_l", "hand_l", close=150 * deg),
        hinge_limit_about_rest(pos, idx, "neck", "elbow_r", "hand_r", close=150 * deg),
        hinge_limit_about_rest(pos, idx, "pelvis", "knee_l", "foot_l", close=150 * deg),
        hinge_limit_about_rest(pos, idx, "pelvis", "knee_r", "foot_r", close=150 * deg),
    ]
    return Puppet(positions=positions, sticks=sticks, strings=strings, limits=limits), idx
