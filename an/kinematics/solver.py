"""The solve: bodies joined at points, driven at a few, settled by gravity.

One frame at a time (:func:`solve`), or a run of frames with the caller's
targets and joined/unjoined joints per frame (:func:`solve_frames`). The
method and the measurements behind it are in the package docstring
(:mod:`an.kinematics`); in one line: extended position-based dynamics on 2D
rigid bodies [Müller et al. 2020], Gauss–Seidel over the joints, a fixed
number of substeps and iterations, hinge limits as angular projections, the
two-link closed form (or, for a longer slack chain, an arc) as the initial
guess.

**Two modes.** With ``dt=None`` (``pose``) the bodies are projected onto the
joints from where they stand, with no inertia and no gravity: the answer is
a function of the targets alone (plus the starting poses, which choose
between symmetric solutions). With a ``dt`` (``dynamic``) the bodies carry
velocity from frame to frame, gravity and forces act, a target is reached
over the frame's substeps (the driven body moves, it does not teleport), and
the result depends on every frame before: baked from the first frame at a
fixed substep, it is still a pure function of the inputs.

**Conflicts.** When the joints cannot all hold (a grip beyond the arm's
reach, an elbow asked past its range), Gauss–Seidel would spread the error
over every joint in the loop and tear the arm off its shoulder. The rows are
projected last-declared first, so the first-declared joint is the last
correction of every pass. A frame that leaves a rigid joint failing is
solved again with :data:`DFLT_CONFLICT_RETRY` times the iterations from a
start nudged by :data:`DFLT_NUDGE` (a straight chain pushed along its length
has no sideways correction to buckle with otherwise). If that at least
halves the failure (:data:`DFLT_CONFLICT_PROGRESS`) it was slow convergence:
the retry is repeated with ``retry`` times the passes while each round still
cuts what is left by more than :data:`DFLT_STALL_PROGRESS`, up to
:data:`DFLT_CONVERGE_CAP` times ``iterations`` (an#568). A round that stalls
is a conflict after all (a grip inside the arm's length but past its elbow's
range converges at first, then sits a pixel short), and what is left after the
cap is only reported. If not, it is a conflict, settled per
LOOP: the joints that share a cycle through the held bodies with a failing
one are tried last-declared first, and the first whose loss at least halves
the failure is given up for the frame (an#641: a rope held at both ends gives
up its end, never a link) (a joint on no cycle, such as
any joint of a rope hung from one hook, is never a candidate: a tree can
always be satisfied). The joints given up are in
:attr:`SolveResult.dropped`, and their gaps in ``unsatisfied``. So declare
the structure (the skeleton) before what it reaches for (a grip): an
unreachable grip is refused, and the arm reaches toward it from its
shoulder.

**Determinism.** Fixed order, fixed counts, no randomness, Python floats and
:mod:`math` only inside the loop (Gauss–Seidel is sequential, and scalar
numpy is both slower and free to take a different SIMD path per CPU), numpy
only at the boundary: on one platform the same inputs give the same bytes,
run after run and process after process. Across platforms they need not: a
libm may differ in the last ulp, and a dynamic run amplifies that (measured:
1e-13 on one frame's input is 0.014 units 96 frames later). So a cache key
built on a solve is built on its INPUTS (:func:`inputs_digest`, which holds
:data:`SOLVER_VERSION`), never on its output; :func:`quantize` and
:func:`digest` are for storing and comparing poses on one platform.

>>> arm = Body("arm", x=0.0, y=0.0, width=60.0, height=8.0, origin=(0.0, 0.5))
>>> r = solve([arm], [Pin(Point("arm", 0.0, 0.5), Point(WORLD, 0.0, 0.0))],
...           targets={"arm": {"rotation": 0.5}})
>>> round(r.pose("arm").rotation, 3), r.unsatisfied
(0.5, ())
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from typing import Any

import numpy as np

from an.kinematics.bodies import WORLD, Body, Point, inertia, local_offset, mass
from an.kinematics.chains import arc_chain, two_bone
from an.kinematics.joints import (
    Contact,
    Distance,
    Force,
    Hinge,
    Joint,
    Pin,
    Slide,
    Weld,
)

#: Gauss–Seidel passes over the joints per substep (dynamic) or per solve
#: (pose). Measured (package docstring): a two-link chain with a goal and a
#: hinge limit reaches its target to 1e-6 px within 6 passes from the
#: closed-form start.
DFLT_ITERATIONS: int = 8
#: Substeps per frame in dynamic mode: "smaller time steps are more effective
#: than more iterations" (Catto 2024), and four keeps a 24 fps frame under a
#: quarter of its period of free fall at 980 px/s².
DFLT_SUBSTEPS: int = 4
#: Fraction of velocity lost per substep in dynamic mode: the one style knob
#: a puppet has for how long it swings. 0.02 reads as a wooden marionette.
#: It is per substep, so changing ``substeps`` changes the swing too (both
#: are in every cache key built on a solve).
DFLT_DAMPING: float = 0.02
#: A joined joint whose points are further apart than this after the solve is
#: reported as unsatisfied (scene units; a quarter pixel is below what a
#: render shows).
DFLT_TOLERANCE: float = 0.25
#: A hinge or weld whose angle is outside its range by more than this is
#: reported (radians; 1e-3 rad is 0.06 degrees).
DFLT_ANGLE_TOLERANCE: float = 1e-3
#: A solve that leaves a joint failing is run again with this many times the
#: iterations before anything is given up: what more passes fix was slow
#: convergence (a hard swing), what they do not is a conflict.
DFLT_CONFLICT_RETRY: int = 4
#: A failing joint is in conflict when the retry left more than this fraction
#: of its failure (residual over tolerance, or range broken over angle
#: tolerance): a conflict is what more passes do not fix. Giving a joint up
#: settles a conflict when it leaves at most this fraction of the failure.
DFLT_CONFLICT_PROGRESS: float = 0.5
#: The most trial solves :func:`solve` spends looking for the joint to give
#: up in a conflict (each is a full solve of the frame).
DFLT_MAX_DROP_TRIALS: int = 12
#: Radians each free body is turned by on a retry, alternating in sign (see
#: ``_nudge``): far below what a frame shows, enough to buckle a straight
#: chain pushed along its length.
DFLT_NUDGE: float = 1e-3
#: Quanta a stored pose is rounded to by :func:`quantize`: finer than any
#: render shows.
DFLT_POSITION_QUANTUM: float = 1e-6
DFLT_ANGLE_QUANTUM: float = 1e-7
#: A contact or slide looks this far past a segment's ends (scene units)
#: before letting the point go: a foot half a unit past the edge still stands.
DFLT_SEGMENT_MARGIN: float = 0.5
#: Bumped whenever the solve can give a different answer for the same inputs
#: (a changed projection, order, or default): part of every cache key built
#: on this module.
#: 2: a slow retry keeps going while it converges (an#568); 3: a conflict gives up
#: the first candidate that halves the failure (an#641); 4: a slack chain of more
#: than two links held at both ends is seeded on an arc (an#646).
SOLVER_VERSION: str = "4"
#: The most passes a frame whose first retry made progress is given, as a
#: multiple of ``iterations``: its retry is repeated with ``retry`` times the
#: passes while each round still makes progress (an#568). On 300 random
#: out-and-back reaches of a two-link arm in dynamic mode, 126 frames were left
#: up to 6 px apart at the single retry (most of them a grip past the elbow's
#: range, a conflict that halved once and then stalled); none at a cap of 64.
#: A frame that converges at once pays nothing; a 50-link rope with its end out
#: of reach pays ~90 rather than ~40 ms a frame, with 7 rather than 22 frames
#: left failing.
DFLT_CONVERGE_CAP: int = 64
#: A later round STALLS when what is left is more than this fraction of the
#: round before (it cut less than 10%): a conflict, given up. Laxer than
#: :data:`DFLT_CONFLICT_PROGRESS`, which decides the first retry: requiring
#: every round to halve gave up a reachable grip that was still converging.
DFLT_STALL_PROGRESS: float = 0.9

#: The pose channels, in the order :attr:`SolveResult.poses` holds them.
POSE_CHANNELS: tuple[str, ...] = ("x", "y", "rotation", "scale")
#: ``{body name: {channel: value}}``; a channel given is held at its value
#: for the frame (a nail), the others move.
Targets = Mapping[str, Mapping[str, float]]
Gravity = tuple[float, float]

_DRIVABLE: frozenset[str] = frozenset({"x", "y", "rotation"})
_TWO_PI = 2.0 * math.pi


def _wrap(theta: float) -> float:
    """``theta`` wrapped into ``[-pi, pi)``."""
    return theta - _TWO_PI * math.floor((theta + math.pi) / _TWO_PI)


class KinematicsError(ValueError):
    """A solve that cannot be set up: an unknown body, gravity without time,
    a joint on the world alone, a body with no extent."""


# -----------------------------------------------------------------------------
# The result
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class SolveResult:
    """What one frame's solve found.

    ``bodies`` are the input bodies with their poses and velocities updated,
    ready to be the next frame's input; ``poses`` is the same as an array,
    one row per body in input order, columns :data:`POSE_CHANNELS`.
    ``residuals`` has one entry per joint in input order: how far apart a
    joined joint's points still are (0 for an unjoined joint, or one that
    holds; a compliant joint's stretch); ``unsatisfied`` lists the rigid
    joints' ``(joint index, residual)`` pairs above tolerance, and
    ``limit_violations`` the rigid hinges and welds outside their angle range
    as ``(joint index, radians)``. ``dropped`` lists the joints
    given up in a conflict (module docstring), in the order they were.
    """

    bodies: tuple[Body, ...]
    poses: np.ndarray
    residuals: tuple[float, ...]
    unsatisfied: tuple[tuple[int, float], ...]
    limit_violations: tuple[tuple[int, float], ...]
    dropped: tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        """Every joined joint holds and every range is kept.

        >>> solve([Body("b")], []).ok
        True
        """
        return not self.unsatisfied and not self.limit_violations

    def pose(self, name: str) -> Body:
        """The body called ``name`` as solved.

        >>> b = Body("b", x=1.0)
        >>> solve([b], []).pose("b").x
        1.0
        """
        for body in self.bodies:
            if body.name == name:
                return body
        raise KeyError(f"no body named {name!r}")


@dataclass(frozen=True)
class FramesResult:
    """A run of frames: ``poses`` is ``(frames, bodies, 4)``; ``unsatisfied``
    and ``limit_violations`` are per frame; ``snaps`` lists every joint that
    is enforced again after a frame it was not (the caller rejoined it, or a
    conflict had dropped it) as ``(frame, joint index, distance)``, the gap
    it closes in one frame (the caller decides whether to blend or to refuse
    it; in dynamic mode a large gap yanks the bodies it joins); ``final`` is the last frame's bodies, ready to continue the
    run; ``dropped`` the joints each frame gave up in a conflict."""

    bodies: tuple[str, ...]
    poses: np.ndarray
    unsatisfied: tuple[tuple[tuple[int, float], ...], ...]
    limit_violations: tuple[tuple[tuple[int, float], ...], ...]
    snaps: tuple[tuple[int, int, float], ...]
    final: tuple[Body, ...] = ()
    dropped: tuple[tuple[int, ...], ...] = ()


# -----------------------------------------------------------------------------
# State: Python floats inside the loop, numpy at the boundary
# -----------------------------------------------------------------------------


class _State:
    """Mutable solve state: index 0 is the world (fixed, at the origin).

    Each body is tracked at a *reference point*: its centre of mass (the
    centre of its extent), or, when its x and y are both held, its pose point
    (a pivot it turns about). ``x``, ``y`` are the reference's position,
    ``vx``, ``vy`` its velocity, ``inv_i`` the inverse inertia about it, and a
    point's local offset is measured from it. That is what makes a limb
    hinged at its pose point swing under gravity, and a push at its centre
    move it without turning it. The pose point is recovered at the boundary.
    """

    def __init__(self, bodies: Sequence[Body]) -> None:
        names = [b.name for b in bodies]
        if WORLD in names:
            raise KinematicsError(f"{WORLD!r} is the world's name; rename that body")
        if len(set(names)) != len(names):
            raise KinematicsError("body names must be unique")
        for b in bodies:
            if not b.fixed and not (
                b.width > 0 and b.height > 0 and b.scale > 0 and b.density > 0
            ):
                raise KinematicsError(
                    f"body {b.name!r}: a movable body needs a positive width, "
                    f"height, scale and density (it has no mass otherwise)"
                )
        self.names = names
        self.index = {name: i + 1 for i, name in enumerate(names)}
        self.bodies = list(bodies)
        #: The centre's offset from the pose point, in the body's frame.
        self.centre = [(0.0, 0.0)] + [
            local_offset(b, Point(b.name, 0.5, 0.5)) for b in bodies
        ]
        #: The reference point's offset from the pose point (the centre, or 0).
        self.ref = list(self.centre)
        self.th = [0.0] + [float(b.rotation) for b in bodies]
        self.x = [0.0] * (len(bodies) + 1)
        self.y = [0.0] * (len(bodies) + 1)
        for i, b in enumerate(bodies, start=1):
            self.set_pose(i, float(b.x), float(b.y), self.th[i])
        self.vx = [0.0] + [float(b.vx) for b in bodies]
        self.vy = [0.0] + [float(b.vy) for b in bodies]
        self.om = [0.0] + [float(b.omega) for b in bodies]
        self.m = [math.inf] + [mass(b) for b in bodies]
        self.inv_m = [0.0] + [0.0 if b.fixed else 1.0 / mass(b) for b in bodies]
        self.inv_i = [0.0] + [
            0.0 if b.fixed else 1.0 / _centre_inertia(b) for b in bodies
        ]
        #: ``body index -> [(channel, value at the frame's start, target)]``.
        self.held: dict[int, list[tuple[str, float, float]]] = {}

    def body_index(self, name: str) -> int:
        if name == WORLD:
            return 0
        try:
            return self.index[name]
        except KeyError:
            raise KinematicsError(
                f"unknown body {name!r}; known: {', '.join(self.names) or 'none'}"
            ) from None

    def offset(self, point: Point) -> tuple[int, float, float]:
        """``(body index, local x, local y)`` of a point, from the reference."""
        i = self.body_index(point.body)
        if i == 0:
            return 0, float(point.u), float(point.v)
        lx, ly = local_offset(self.bodies[i - 1], point)
        rx, ry = self.ref[i]
        return i, lx - rx, ly - ry

    def world(self, i: int, lx: float, ly: float) -> tuple[float, float]:
        if i == 0:
            return lx, ly
        c, s = math.cos(self.th[i]), math.sin(self.th[i])
        return self.x[i] + c * lx - s * ly, self.y[i] + s * lx + c * ly

    def pose_of(self, i: int) -> tuple[float, float, float]:
        """The pose point and rotation of body ``i``."""
        px, py = self.world(i, -self.ref[i][0], -self.ref[i][1])
        return px, py, self.th[i]

    def set_pose(self, i: int, x: float, y: float, rotation: float) -> None:
        self.th[i] = rotation
        c, s = math.cos(rotation), math.sin(rotation)
        rx, ry = self.ref[i]
        self.x[i] = x + c * rx - s * ry
        self.y[i] = y + s * rx + c * ry

    def _rebase(self, i: int, ref: tuple[float, float]) -> None:
        """Move body ``i``'s reference point, keeping its pose and motion."""
        px, py, th = self.pose_of(i)
        c, s = math.cos(th), math.sin(th)
        dx, dy = ref[0] - self.ref[i][0], ref[1] - self.ref[i][1]
        wx, wy = c * dx - s * dy, s * dx + c * dy  # old reference -> new, in the world
        self.vx[i] -= self.om[i] * wy
        self.vy[i] += self.om[i] * wx
        self.ref[i] = ref
        self.set_pose(i, px, py, th)

    def drive(self, targets: Targets | None) -> None:
        """Hold the targeted channels for the frame. A body held in both x
        and y turns about its pose point (the reference moves there) and no
        joint can push it; one held in rotation has no inertia to turn;
        :meth:`restore_held` puts the held channels back after every
        projection."""
        if not targets:
            return
        for name in sorted(targets):
            channels = targets[name]
            i = self.body_index(name)
            if i == 0:
                raise KinematicsError("the world cannot be driven")
            unknown = set(channels) - _DRIVABLE
            if unknown:
                raise KinematicsError(
                    f"body {name!r}: cannot drive {sorted(unknown)}; "
                    f"drivable channels are {sorted(_DRIVABLE)}"
                )
            if "x" in channels and "y" in channels and not self.bodies[i - 1].fixed:
                self._rebase(i, (0.0, 0.0))
                self.inv_i[i] = 1.0 / inertia(self.bodies[i - 1])
                self.inv_m[i] = 0.0
            if "rotation" in channels:
                self.inv_i[i] = 0.0
            pose = dict(zip(("x", "y", "rotation"), self.pose_of(i)))
            held = []
            for channel in sorted(channels):
                value = float(channels[channel])
                if not math.isfinite(value):
                    raise KinematicsError(
                        f"body {name!r}: target {channel}={value} is not finite"
                    )
                held.append((channel, pose[channel], value))
            self.held[i] = held

    def restore_held(self, along: float = 1.0) -> None:
        """Put every held channel at ``along`` of the way from its frame-start
        value to its target (1 is the target itself)."""
        for i, held in self.held.items():
            pose = dict(zip(("x", "y", "rotation"), self.pose_of(i)))
            for channel, start, target in held:
                pose[channel] = (
                    target if along >= 1.0 else start + (target - start) * along
                )
            self.set_pose(i, pose["x"], pose["y"], pose["rotation"])

    def centre_velocity(self, i: int) -> tuple[float, float]:
        """The velocity of body ``i``'s centre (what a :class:`Body` carries)."""
        c, s = math.cos(self.th[i]), math.sin(self.th[i])
        dx, dy = self.centre[i][0] - self.ref[i][0], self.centre[i][1] - self.ref[i][1]
        wx, wy = c * dx - s * dy, s * dx + c * dy
        return self.vx[i] - self.om[i] * wy, self.vy[i] + self.om[i] * wx

    def as_bodies(self) -> tuple[Body, ...]:
        out = []
        for i, b in enumerate(self.bodies, start=1):
            px, py, th = self.pose_of(i)
            vx, vy = self.centre_velocity(i)
            out.append(b.posed(x=px, y=py, rotation=th, vx=vx, vy=vy, omega=self.om[i]))
        return tuple(out)

    def as_array(self) -> np.ndarray:
        n = len(self.bodies)
        out = np.empty((n, len(POSE_CHANNELS)), dtype=np.float64)
        for k, b in enumerate(self.bodies):
            out[k, 0], out[k, 1], out[k, 2] = self.pose_of(k + 1)
            out[k, 3] = b.scale
        return out


def _centre_inertia(body: Body) -> float:
    """Rotational inertia about the centre of the body's extent."""
    w, h = body.width * body.scale, body.height * body.scale
    return mass(body) * (w * w + h * h) / 12.0


# -----------------------------------------------------------------------------
# Rows: a joint compiled to the projections it needs
# -----------------------------------------------------------------------------

#: One projection: ``(kind, joint index, payload)``. Kinds: ``pos`` (two
#: points at a distance: ``ia, lxa, lya, ib, lxb, lyb, length, mode,
#: compliance``), ``ang`` (a relative angle in a range: ``ia, ib, rest, lo,
#: hi, compliance``), ``seg`` (a point against a segment: ``ia, lx, ly, ib,
#: sx0, sy0, sx1, sy1, one_sided, compliance``). A pull is a ``pos`` row with
#: joint index ``-1``. Each row owns two multiplier slots (``2k``, ``2k + 1``:
#: a slide's second one holds it within the segment's ends).
_Row = tuple[str, int, tuple]


def _rows(
    state: _State,
    joints: Sequence[Joint],
    forces: Sequence[Force],
    *,
    skip: Sequence[int] = (),
) -> list[_Row]:
    rows: list[_Row] = []
    for j, joint in enumerate(joints):
        if joint.compliance < 0:
            raise KinematicsError(f"joint {j}: compliance must be non-negative")
        if not joint.joined or j in skip:
            continue
        if isinstance(joint, (Pin, Hinge, Weld)):
            ia, lxa, lya = state.offset(joint.a)
            ib, lxb, lyb = state.offset(joint.b)
            if ia == ib:
                raise KinematicsError(f"joint {j}: both points are on one body")
            rows.append(
                ("pos", j, (ia, lxa, lya, ib, lxb, lyb, 0.0, "equal", joint.compliance))
            )
            if isinstance(joint, Hinge) and joint.limits is not None:
                lo, hi = (float(v) for v in joint.limits)
                if lo > hi:
                    raise KinematicsError(
                        f"joint {j}: hinge limits {joint.limits} are reversed"
                    )
                if lo < -math.pi or hi > math.pi:
                    raise KinematicsError(
                        f"joint {j}: hinge limits {joint.limits} must lie within [-pi, pi] about the rest angle"
                    )
                rows.append(
                    ("ang", j, (ia, ib, float(joint.rest), lo, hi, joint.compliance))
                )
            elif isinstance(joint, Weld):
                rows.append(
                    ("ang", j, (ia, ib, float(joint.rest), 0.0, 0.0, joint.compliance))
                )
        elif isinstance(joint, Distance):
            ia, lxa, lya = state.offset(joint.a)
            ib, lxb, lyb = state.offset(joint.b)
            if ia == ib:
                raise KinematicsError(f"joint {j}: both points are on one body")
            if joint.mode not in ("equal", "at_most", "at_least"):
                raise KinematicsError(
                    f"joint {j}: unknown distance mode {joint.mode!r}"
                )
            if joint.length < 0:
                raise KinematicsError(
                    f"joint {j}: a distance's length must be non-negative"
                )
            rows.append(
                (
                    "pos",
                    j,
                    (
                        ia,
                        lxa,
                        lya,
                        ib,
                        lxb,
                        lyb,
                        float(joint.length),
                        joint.mode,
                        joint.compliance,
                    ),
                )
            )
        elif isinstance(joint, (Slide, Contact)):
            ia, lx, ly = state.offset(joint.point)
            ib, sx0, sy0 = state.offset(joint.start)
            ib2, sx1, sy1 = state.offset(joint.end)
            if ib != ib2:
                raise KinematicsError(
                    f"joint {j}: a segment's two points must be on one body"
                )
            if ia == ib:
                raise KinematicsError(
                    f"joint {j}: the point and the segment are on one body"
                )
            rows.append(
                (
                    "seg",
                    j,
                    (
                        ia,
                        lx,
                        ly,
                        ib,
                        sx0,
                        sy0,
                        sx1,
                        sy1,
                        isinstance(joint, Contact),
                        joint.compliance,
                    ),
                )
            )
        else:
            raise KinematicsError(f"joint {j}: unknown joint {type(joint).__name__}")
    for f in forces:
        if f.toward is None:
            continue
        if f.strength <= 0:
            raise KinematicsError("a pull's strength must be positive")
        ia, lxa, lya = state.offset(f.point)
        if isinstance(f.toward, Point):
            ib, lxb, lyb = state.offset(f.toward)
        else:
            ib, lxb, lyb = 0, float(f.toward[0]), float(f.toward[1])
        if ia == ib:
            raise KinematicsError("a pull's two points are on one body")
        rows.append(
            ("pos", -1, (ia, lxa, lya, ib, lxb, lyb, 0.0, "equal", 1.0 / f.strength))
        )
    return rows


def _push(
    st: _State,
    ia: int,
    rax: float,
    ray: float,
    ib: int,
    rbx: float,
    rby: float,
    nx: float,
    ny: float,
    c: float,
    alpha_t: float,
    lam: list[float],
    k: int,
) -> None:
    """Apply one XPBD correction: the point on ``ia`` moves along ``-n`` and
    the point on ``ib`` along ``+n`` until ``c`` (the constraint value whose
    gradient is ``+n`` at ``a``) is zero, in the measure of their generalized
    inverse masses ``1/m + (r × n)² / I``."""
    cra = rax * ny - ray * nx
    crb = rbx * ny - rby * nx
    wa = st.inv_m[ia] + st.inv_i[ia] * cra * cra
    wb = st.inv_m[ib] + st.inv_i[ib] * crb * crb
    denom = wa + wb + alpha_t
    if denom == 0.0:
        return
    dlam = (-c - alpha_t * lam[k]) / denom
    lam[k] += dlam
    if wa:
        st.x[ia] += st.inv_m[ia] * dlam * nx
        st.y[ia] += st.inv_m[ia] * dlam * ny
        st.th[ia] += st.inv_i[ia] * dlam * cra
    if wb:
        st.x[ib] -= st.inv_m[ib] * dlam * nx
        st.y[ib] -= st.inv_m[ib] * dlam * ny
        st.th[ib] -= st.inv_i[ib] * dlam * crb


def _project(
    st: _State, rows: list[_Row], lam: list[float], h: float, *, apply: bool
) -> list[float]:
    """One pass over the rows, last first: the first-declared joint is
    projected last, so it holds and a conflict shows on the later ones (the
    ones :func:`solve` gives up). Returns each row's constraint value in row
    order (0 where inactive); with ``apply`` False it only measures."""
    out = [0.0] * len(rows)
    inv_h2 = 1.0 / (h * h)
    for k in range(len(rows) - 1, -1, -1):
        kind, _j, p = rows[k]
        if kind == "pos":
            ia, lxa, lya, ib, lxb, lyb, length, mode, compliance = p
            ax, ay = st.world(ia, lxa, lya)
            bx, by = st.world(ib, lxb, lyb)
            dx, dy = ax - bx, ay - by
            dist = math.hypot(dx, dy)
            if (mode == "at_most" and dist <= length) or (
                mode == "at_least" and dist >= length
            ):
                continue
            if dist == 0.0:
                if length == 0.0:
                    continue
                nx, ny = (
                    0.0,
                    1.0,
                )  # a spacer between coincident points: push apart along y
            else:
                nx, ny = dx / dist, dy / dist
            c = dist - length
            out[k] = c
            if apply:
                _push(
                    st,
                    ia,
                    ax - st.x[ia],
                    ay - st.y[ia],
                    ib,
                    bx - st.x[ib],
                    by - st.y[ib],
                    nx,
                    ny,
                    c,
                    compliance * inv_h2,
                    lam,
                    2 * k,
                )
        elif kind == "ang":
            ia, ib, rest, lo, hi, compliance = p
            c = _range_violation(_wrap(st.th[ib] - st.th[ia] - rest), lo, hi)
            out[k] = c
            if c and apply:
                wa, wb = st.inv_i[ia], st.inv_i[ib]
                alpha_t = compliance * inv_h2
                denom = wa + wb + alpha_t
                if denom:
                    dlam = (-c - alpha_t * lam[2 * k]) / denom
                    lam[2 * k] += dlam
                    st.th[ia] -= wa * dlam
                    st.th[ib] += wb * dlam
        else:  # seg
            ia, lx, ly, ib, sx0, sy0, sx1, sy1, one_sided, compliance = p
            px, py = st.world(ia, lx, ly)
            x0, y0 = st.world(ib, sx0, sy0)
            x1, y1 = st.world(ib, sx1, sy1)
            tx, ty = x1 - x0, y1 - y0
            seg = math.hypot(tx, ty)
            if seg == 0.0:
                continue
            tx, ty = tx / seg, ty / seg
            nx, ny = ty, -tx
            along = (px - x0) * tx + (py - y0) * ty
            if one_sided and (
                along < -DFLT_SEGMENT_MARGIN or along > seg + DFLT_SEGMENT_MARGIN
            ):
                continue
            c = (px - x0) * nx + (py - y0) * ny
            if one_sided and c >= 0.0:
                continue
            # A slide is also held within the segment's ends.
            ct = (
                0.0
                if one_sided
                else along
                if along < 0.0
                else along - seg
                if along > seg
                else 0.0
            )
            out[k] = math.hypot(c, ct)
            if apply:
                u = min(max(along, 0.0), seg)
                qx, qy = x0 + u * tx, y0 + u * ty
                alpha_t = compliance * inv_h2
                _push(
                    st,
                    ia,
                    px - st.x[ia],
                    py - st.y[ia],
                    ib,
                    qx - st.x[ib],
                    qy - st.y[ib],
                    nx,
                    ny,
                    c,
                    alpha_t,
                    lam,
                    2 * k,
                )
                if ct:
                    px, py = st.world(ia, lx, ly)
                    _push(
                        st,
                        ia,
                        px - st.x[ia],
                        py - st.y[ia],
                        ib,
                        qx - st.x[ib],
                        qy - st.y[ib],
                        tx,
                        ty,
                        ct,
                        alpha_t,
                        lam,
                        2 * k + 1,
                    )
    return out


# -----------------------------------------------------------------------------
# The two-link initial guess
# -----------------------------------------------------------------------------


def _range_violation(rel: float, lo: float, hi: float) -> float:
    """How far the wrapped relative angle ``rel`` is outside ``[lo, hi]``:
    0 inside, positive past ``hi``, negative short of ``lo``, toward whichever
    bound is nearer AROUND THE CIRCLE (an elbow folded past its range at
    166 degrees is 0.3 past ``hi``, not 6 short of ``lo``)."""
    if lo <= rel <= hi:
        return 0.0
    past_hi = (rel - hi) % _TWO_PI
    short_of_lo = (lo - rel) % _TWO_PI
    return past_hi if past_hi <= short_of_lo else -short_of_lo


#: A chain between two held ends: ``(root, root point, links, tip, tip
#: point, joint ids)``; each link is ``(body, entry point, exit point, exit
#: joint)`` in body-local coordinates; ``joint ids`` are the root pin's then
#: each link's exit joint (the last is the grip).
_Chain = tuple[int, tuple[float, float], list, int, tuple[float, float], list[int]]


def _chains(st: _State, rows: list[_Row]) -> list[_Chain]:
    """Every unbranched run of pinned bodies (two pins each, none held) from
    one held body to another (or back to the same one through two or more
    links): the chains the closed form seeds and the reach check reads."""
    pins = [
        (j, p)
        for kind, j, p in rows
        if kind == "pos" and p[6] == 0.0 and p[7] == "equal" and j >= 0
    ]
    by_body: dict[int, list[tuple[int, tuple]]] = {}
    for j, p in pins:
        by_body.setdefault(p[0], []).append((j, p))
        by_body.setdefault(p[3], []).append((j, p))

    def anchored(i: int) -> bool:
        return st.inv_m[i] == 0.0

    def ends(p: tuple, i: int) -> tuple[float, float, int, float, float]:
        """(local x, local y) of the pin on body i, and the other body with its local point."""
        if p[0] == i:
            return p[1], p[2], p[3], p[4], p[5]
        return p[4], p[5], p[0], p[1], p[2]

    def walk(a: int, jr: int, root_pin: tuple) -> _Chain | None:
        lx, ly, root, rlx, rly = ends(root_pin, a)
        links, cur, entry, seen, pin_in = [], a, (lx, ly), {a}, root_pin
        while True:
            if anchored(cur) or len(by_body.get(cur, ())) != 2:
                return None
            j_out, pin_out = next((j, p) for j, p in by_body[cur] if p is not pin_in)
            ox, oy, nxt, nlx, nly = ends(pin_out, cur)
            links.append((cur, entry, (ox, oy), j_out))
            if anchored(nxt):
                if nxt == root and len(links) < 2:
                    return None
                return (
                    root,
                    (rlx, rly),
                    links,
                    nxt,
                    (nlx, nly),
                    [jr] + [link[3] for link in links],
                )
            if nxt in seen:
                return None
            seen.add(nxt)
            cur, entry, pin_in = nxt, (nlx, nly), pin_out

    out: list[_Chain] = []
    taken: set[int] = set()
    for a in range(1, len(st.names) + 1):
        if anchored(a) or a in taken or len(by_body.get(a, ())) != 2:
            continue
        for jr, root_pin in by_body[a]:
            other = next(p for _, p in by_body[a] if p is not root_pin)
            if not anchored(ends(root_pin, a)[2]) or anchored(ends(other, a)[2]):
                continue
            chain = walk(a, jr, root_pin)
            if chain is not None and not taken.intersection(
                link[0] for link in chain[2]
            ):
                taken.update(link[0] for link in chain[2])
                out.append(chain)
                break
    return out


def _out_of_reach(st: _State, rows: list[_Row], tolerance: float) -> list[int]:
    """The grips no pose can meet: for every chain between two RIGID ends
    (the world, a fixed body, or one held in x, y and rotation, at its
    target), the chain's last-declared joint when the distance between its
    ends is outside the chain's reach by more than ``tolerance``. Such a
    conflict is known from the geometry, before any pass."""

    def rigid(i: int) -> bool:
        return st.inv_m[i] == 0.0 and st.inv_i[i] == 0.0

    out = []
    for root, (rlx, rly), links, tip, (tlx, tly), joint_ids in _chains(st, rows):
        if not (rigid(root) and rigid(tip)):
            continue
        lengths = [math.hypot(x1 - x0, y1 - y0) for _b, (x0, y0), (x1, y1), _j in links]
        far = sum(lengths)
        near = max(0.0, 2.0 * max(lengths) - far)
        d = math.dist(st.world(root, rlx, rly), st.world(tip, tlx, tly))
        if d > far + tolerance or d < near - tolerance:
            out.append(max(joint_ids))
    return out


def _seed_chains(st: _State, rows: list[_Row], tolerance: float) -> None:
    """Pose every chain whose both ends are held (anchored to the world, a
    fixed body or one held in x and y) by the two-link closed form (a chain of
    more than two links it cannot fold, or folds only past a hinge range, is
    also laid on an arc, :func:`_arc_seed`, and the seed that breaks less is
    kept, an#646): the
    first link is the first bone, the rest of the chain (a forearm and a
    hand) is held rigid at its current angles, clamped into their ranges,
    and is the second. Of the two bend sides it takes the one the hinge
    ranges allow, and between two allowed sides the one it currently has,
    so a run of frames never flips an elbow. A chain already on its target
    within its ranges is left as it is."""
    angles = {j: p for kind, j, p in rows if kind == "ang"}

    def violation(joint_ids: Sequence[int]) -> float:
        total = 0.0
        for j in joint_ids:
            if j in angles:
                ia, ib, rest, lo, hi, _c = angles[j]
                total += abs(
                    _range_violation(_wrap(st.th[ib] - st.th[ia] - rest), lo, hi)
                )
        return total

    def tail_angles(links: list) -> list[float]:
        """Each tail joint's turn (next body's rotation minus the previous
        one's), from the current poses, a hinge's clamped into its range."""
        turns = []
        for (prev, _e, _o, j), (nxt, *_rest) in zip(links[1:], links[2:]):
            turn = st.th[nxt] - st.th[prev]
            if j in angles:
                ia, ib, rest, lo, hi, _c = angles[j]
                rel = _wrap(st.th[ib] - st.th[ia] - rest)
                turn -= _range_violation(rel, lo, hi) * (1.0 if ib == nxt else -1.0)
            turns.append(turn)
        return turns

    def pose_tail(
        links: list, turns: list[float], x0: float, y0: float, theta: float
    ) -> tuple[float, float]:
        """Pose ``links[1:]`` rigidly from ``(x0, y0)``: the first of them at
        ``theta``, each next one turned by its entry in ``turns``. Returns the
        tail's tip."""
        i, (ex, ey), _o, _ = links[1]
        st.th[i] = theta
        _pose_link_at(st, i, ex, ey, x0, y0)
        for (prev, _e, (px_, py_), _j), (nxt, (nx_, ny_), _o2, _j2), turn in zip(
            links[1:], links[2:], turns
        ):
            st.th[nxt] = st.th[prev] + turn
            wx, wy = st.world(prev, px_, py_)
            _pose_link_at(st, nxt, nx_, ny_, wx, wy)
        last, _e, (tx_, ty_), _ = links[-1]
        return st.world(last, tx_, ty_)

    for root, (rlx, rly), links, tip, (tlx, tly), joint_ids in _chains(st, rows):
        if len(links) < 2:
            continue
        bodies = [link[0] for link in links]
        rx, ry = st.world(root, rlx, rly)
        gx, gy = st.world(tip, tlx, tly)
        first, entry1, exit1, _ = links[0]
        saved = [(st.x[i], st.y[i], st.th[i]) for i in bodies]
        # The tail's geometry at its current (clamped) angles.
        ex, ey = st.world(first, *exit1)
        turns = tail_angles(links)
        hx, hy = pose_tail(links, turns, ex, ey, st.th[links[1][0]])
        sx, sy = st.world(first, *entry1)
        if (
            math.hypot(hx - gx, hy - gy) <= tolerance
            and math.hypot(sx - rx, sy - ry) <= tolerance
            and violation(joint_ids) == 0.0
        ):
            for i, (x, y, th) in zip(
                bodies, saved
            ):  # already there: leave the warm start alone
                st.x[i], st.y[i], st.th[i] = x, y, th
            continue
        tail_offset = math.atan2(hy - ey, hx - ex) - st.th[links[1][0]]
        l1 = math.hypot(exit1[0] - entry1[0], exit1[1] - entry1[1])
        l2 = math.hypot(hx - ex, hy - ey)
        if l1 == 0.0 or l2 == 0.0:
            for i, (x, y, th) in zip(bodies, saved):
                st.x[i], st.y[i], st.th[i] = x, y, th
            continue
        # two_bone's bend +1 puts the middle joint clockwise of root→tip
        # in this cross-product's sense, hence the minus.
        cross = (ex - rx) * (gy - ry) - (ey - ry) * (gx - rx)
        current = -1 if cross > 0 else 1

        def pose(t1: float, t2: float) -> None:
            _pose_link(st, first, *entry1, *exit1, rx, ry, t1)
            elbow = st.world(first, *exit1)
            pose_tail(links, turns, *elbow, t2 - tail_offset)

        best: tuple[float, int] | None = None
        for bend in (current, -current):
            sol = two_bone((rx, ry), (gx, gy), (l1, l2), bend=bend)
            if sol is None:
                break
            pose(*sol)
            v = violation(joint_ids)
            if best is None or v < best[0]:
                best = (v, bend)
            if v == 0.0:
                break
        # A chain of more than two links the two-link form cannot fold, or
        # folds only by breaking a hinge range (its tail rigid at its current
        # angles): laid on an arc too, and the seed that breaks less is kept
        # (an#646).
        arc = None
        if len(links) > 2 and (best is None or best[0] > 0.0):
            laid = _arc_seed(
                st,
                links,
                (rx, ry),
                (gx, gy),
                bend=current,
                violation=lambda: violation(joint_ids),
            )
            arc = violation(joint_ids) if laid else None
        if best is not None and (arc is None or best[0] <= arc):
            pose(*two_bone((rx, ry), (gx, gy), (l1, l2), bend=best[1]))
        elif arc is None and (gx, gy) != (rx, ry):
            # Out of reach: point the chain at the target (straight when
            # it is too far, folded when too near); the projection then
            # reports the grip, and a conflict gives it up.
            phi = math.atan2(gy - ry, gx - rx)
            too_far = math.hypot(gx - rx, gy - ry) > l1 + l2
            pose(
                phi if too_far or l1 >= l2 else phi + math.pi,
                phi if too_far or l1 < l2 else phi + math.pi,
            )
        elif arc is None:  # on the root: no direction to take, nothing is guessed
            for i, (x, y, th) in zip(bodies, saved):
                st.x[i], st.y[i], st.th[i] = x, y, th
        # else: the arc is laid


def _arc_seed(
    st: _State,
    links: list,
    root: tuple[float, float],
    target: tuple[float, float],
    *,
    bend: int,
    violation: Callable[[], float],
) -> bool:
    """Lay a chain of more than two links held at both ends nearer than its
    length on a circular arc (:func:`an.kinematics.chains.arc_chain`): the
    rigid tail the two-link form uses is too long to fold, and a straight
    chain pushed along its length has no sideways correction to buckle with
    (an#646). Each link goes from its entry point to its exit point along
    the arc. Of the two sides, the one ``bend`` names unless only the other
    keeps the hinge ranges; a straight chain has no side of its own (its
    cross product is 0), so it sags to ``+1``, down on a y-down screen.
    Returns whether it laid the chain (else the chain is left as it was)."""
    lengths = [math.hypot(ex - nx, ey - ny) for _i, (nx, ny), (ex, ey), _j in links]

    def lay(angles: list[float]) -> None:
        x, y = root
        for (i, entry, exit_, _j), theta, length in zip(links, angles, lengths):
            _pose_link(st, i, *entry, *exit_, x, y, theta)
            x, y = x + length * math.cos(theta), y + length * math.sin(theta)

    best: tuple[float, list[float]] | None = None
    for side in (bend, -bend):
        angles = arc_chain(root, target, lengths, bend=side)
        if angles is None:
            return False
        lay(angles)
        v = violation()
        if v == 0.0:
            return True
        if best is None or v < best[0]:
            best = (v, angles)
    lay(best[1])
    return True


def _pose_link_at(
    st: _State, i: int, lx: float, ly: float, x0: float, y0: float
) -> None:
    """Translate body ``i`` (keeping its rotation) so its local point sits at ``(x0, y0)``."""
    c, s = math.cos(st.th[i]), math.sin(st.th[i])
    st.x[i] = x0 - (c * lx - s * ly)
    st.y[i] = y0 - (s * lx + c * ly)


def _pose_link(
    st: _State,
    i: int,
    lx0: float,
    ly0: float,
    lx1: float,
    ly1: float,
    x0: float,
    y0: float,
    theta: float,
) -> None:
    """Pose body ``i`` so its local point ``(lx0, ly0)`` sits at ``(x0, y0)``
    and the local direction to ``(lx1, ly1)`` points along ``theta``. The new
    rotation is the nearest turn to the old one, so an unwrapped rotation
    stays unwrapped."""
    th = theta - math.atan2(ly1 - ly0, lx1 - lx0)
    st.th[i] = st.th[i] + _wrap(th - st.th[i])
    c, s = math.cos(st.th[i]), math.sin(st.th[i])
    st.x[i] = x0 - (c * lx0 - s * ly0)
    st.y[i] = y0 - (s * lx0 + c * ly0)


# -----------------------------------------------------------------------------
# solve
# -----------------------------------------------------------------------------


def solve(
    bodies: Sequence[Body],
    joints: Sequence[Joint],
    *,
    targets: Targets | None = None,
    forces: Sequence[Force] = (),
    gravity: Gravity | None = None,
    dt: float | None = None,
    iterations: int = DFLT_ITERATIONS,
    substeps: int = DFLT_SUBSTEPS,
    damping: float = DFLT_DAMPING,
    tolerance: float = DFLT_TOLERANCE,
    angle_tolerance: float = DFLT_ANGLE_TOLERANCE,
    seed_chains: bool = True,
    retry: int = DFLT_CONFLICT_RETRY,
    drop_conflicts: bool = True,
    seed: int = 0,
    converge_cap: int = DFLT_CONVERGE_CAP,
) -> SolveResult:
    """One frame: the poses of all ``bodies`` that satisfy the joined
    ``joints`` with the ``targets`` held, forces and ``gravity`` acting.

    ``dt=None`` is pose mode: no inertia, no gravity, no pushes (a gravity or
    a ``Force.vector`` is refused there: they need time; a ``Force.toward``
    pull works in both modes). With a ``dt`` the bodies step through
    ``substeps`` of ``dt / substeps``, carrying their velocities in and out,
    and a target is reached over those substeps. ``targets`` hold channels
    exactly (a body held in x and y is immovable to the joints for the frame,
    one held in rotation unturnable); a target beyond a chain's reach shows
    up in ``unsatisfied`` rather than stretching anything. Hinge and weld
    rests left ``None`` are the relative angles the bodies have on input.
    A frame that leaves a joint failing is solved again with ``retry`` times
    the ``iterations`` (1: never), again while each round still cuts what is
    left, up to ``converge_cap`` times the ``iterations``; ``drop_conflicts``
    then gives up the joints in conflict (a first retry that did not halve the
    failure, or a later one that stalled), last declared first (module docstring);
    ``False`` keeps them all and reports what fails. ``seed`` is reserved for stochastic drivers and does nothing in this
    version: the solve has no randomness.

    A shoulder driven to a point, an upper arm pinned to it, a forearm
    hinged to that, the hand pinned to a handle (the two-link case): the hand
    lands on the handle and the elbow bends the way its range allows.

    >>> torso = Body("torso", width=40.0, height=80.0)
    >>> upper = Body("upper", x=20.0, y=-30.0, width=50.0, height=10.0, origin=(0.0, 0.5))
    >>> fore = Body("fore", x=70.0, y=-30.0, width=40.0, height=8.0, origin=(0.0, 0.5))
    >>> handle = Body("handle", x=80.0, y=10.0, width=4.0, height=4.0, fixed=True)
    >>> joints = [Pin(Point("upper", 0.0, 0.5), Point("torso", 1.0, 0.125)),
    ...           Hinge(Point("fore", 0.0, 0.5), Point("upper", 1.0, 0.5), limits=(-2.6, 0.0)),
    ...           Pin(Point("fore", 1.0, 0.5), Point("handle", 0.5, 0.5))]
    >>> r = solve([torso, upper, fore, handle], joints, targets={"torso": {"x": 0.0, "y": 0.0}})
    >>> r.ok, tuple(round(v, 3) for v in r.residuals)
    (True, (0.0, 0.0, 0.0))

    Out of reach, the grip is reported, and the arm stays on its shoulder:

    >>> far = handle.posed(x=300.0)
    >>> r = solve([torso, upper, fore, far], joints, targets={"torso": {"x": 0.0, "y": 0.0}})
    >>> [j for j, _ in r.unsatisfied], r.dropped, [round(v, 6) for v in r.residuals[:2]]
    ([2], (2,), [0.0, 0.0])
    """
    if gravity is not None and dt is None:
        raise KinematicsError(
            "gravity needs time: pass dt (dynamic mode) or drop gravity"
        )
    if dt is None and any(f.vector is not None for f in forces):
        raise KinematicsError(
            "a force vector needs time: pass dt (dynamic mode), or use a pull (toward=)"
        )
    if dt is not None and not dt > 0:
        raise KinematicsError(f"dt must be positive, got {dt}")
    if iterations < 1 or substeps < 1 or retry < 1:
        raise KinematicsError("iterations, substeps and retry must be at least 1")
    _require_finite(bodies, joints, forces, gravity=gravity, dt=dt)
    joints = resolve_rests(bodies, joints)
    unreachable: list[int] = []
    if (
        drop_conflicts
    ):  # what the geometry already rules out is given up before any pass
        st0 = _State(bodies)
        st0.drive(targets)
        st0.restore_held()
        unreachable = _out_of_reach(st0, _rows(st0, joints, ()), tolerance)
    starts: dict[bool, tuple[list[float], list[float], list[float]]] = {}

    def attempt(passes: int, skip: Sequence[int], *, nudge: bool) -> _Attempt:
        st = _State(bodies)
        st.drive(targets)
        rows = _rows(st, joints, forces, skip=skip)
        lam = [0.0] * (2 * len(rows))
        if dt is None:
            st.restore_held()
            if (
                nudge not in starts
            ):  # every attempt starts where the seed put the chains
                if seed_chains:
                    _seed_chains(st, rows, tolerance)
                if nudge:
                    _nudge(st)
                starts[nudge] = (list(st.x), list(st.y), list(st.th))
            st.x, st.y, st.th = (list(v) for v in starts[nudge])
            for _ in range(passes):
                _project(st, rows, lam, 1.0, apply=True)
                st.restore_held()
            for i in range(1, len(st.x)):
                st.vx[i] = st.vy[i] = st.om[i] = 0.0
        else:
            if nudge:
                _nudge(st)
            _step(
                st,
                rows,
                lam,
                forces,
                gravity,
                float(dt),
                substeps=substeps,
                iterations=passes,
                damping=damping,
            )
        residuals, unsatisfied, limits = _measure(
            st,
            _rows(st, joints, ()),
            len(joints),
            tolerance=tolerance,
            angle_tolerance=angle_tolerance,
        )
        failure = 0.0
        for j, r in unsatisfied:
            if j not in skip:
                failure += r / tolerance if math.isfinite(r) else math.inf
        for j, c in limits:
            if j not in skip:
                failure += abs(c) / angle_tolerance
        return _Attempt(st, rows, residuals, unsatisfied, limits, tuple(skip), failure)

    result = attempt(iterations, unreachable, nudge=False)
    if result.failure and retry > 1:
        # Slow to converge, a singular start (a straight chain pushed along
        # its length), or a conflict? More passes from a nudged start first.
        passes = iterations * retry
        retried = attempt(passes, unreachable, nudge=True)
        slow = retried.failure <= DFLT_CONFLICT_PROGRESS * result.failure
        result = retried if retried.failure <= result.failure else result
        # Slow: keep going while each round still makes progress, up to the cap.
        # One that stalls short of holding is a conflict too (an#568: a grip
        # within the arm's length but past its elbow's range halved once, then
        # sat at 1.2 px for any number of passes).
        while slow and result.failure and passes * retry <= iterations * converge_cap:
            passes *= retry
            more = attempt(passes, unreachable, nudge=True)
            slow = more.failure <= DFLT_STALL_PROGRESS * result.failure
            result = more if more.failure <= result.failure else result
        if drop_conflicts and result.failure and not slow:
            result = _give_up_conflicts(result, attempt, passes=iterations * retry)
    if not all(math.isfinite(v) for v in result.st.as_array().flat):
        raise KinematicsError(
            "the solve produced a non-finite pose; check the inputs' scale"
        )
    return SolveResult(
        bodies=result.st.as_bodies(),
        poses=result.st.as_array(),
        residuals=result.residuals,
        unsatisfied=result.unsatisfied,
        limit_violations=result.limits,
        dropped=result.dropped,
    )


@dataclass(frozen=True)
class _Attempt:
    """One solve of a frame with some joints given up; ``failure`` is the sum
    of the failing joints' residuals over their tolerances."""

    st: _State
    rows: list[_Row]
    residuals: tuple[float, ...]
    unsatisfied: tuple[tuple[int, float], ...]
    limits: tuple[tuple[int, float], ...]
    dropped: tuple[int, ...]
    failure: float


def _give_up_conflicts(
    result: _Attempt, attempt: Callable[..., _Attempt], *, passes: int
) -> _Attempt:
    """Give up joints until the frame holds. The candidates are the joints
    that share a loop (a cycle through the held bodies) with a failing one,
    tried last-declared first; the first whose loss at least halves the
    failure (:data:`DFLT_CONFLICT_PROGRESS`) is given up, so the grip goes
    before the structure it reaches with. "Lets everything else hold" was the
    rule before an#641, and it is too strict: a rope held at both ends is one
    loop, and once its end is given up, the falling rope is a little short of
    converged on links that are on no cycle any more, so no candidate let
    everything hold and the most-reducing one, an interior link, was given up
    and the rope came apart. If no candidate halves the failure, nothing more
    is given up. At most :data:`DFLT_MAX_DROP_TRIALS` trial solves in all."""
    trials = 0
    while result.failure and trials < DFLT_MAX_DROP_TRIALS:
        failing = {j for j, _ in result.unsatisfied} | {j for j, _ in result.limits}
        failing.difference_update(result.dropped)
        candidates = sorted(_loop_mates(result.st, result.rows, failing), reverse=True)
        enough = DFLT_CONFLICT_PROGRESS * result.failure
        settled: _Attempt | None = None
        for j in candidates:
            if trials >= DFLT_MAX_DROP_TRIALS:
                break
            trials += 1
            trial = attempt(passes, (*result.dropped, j), nudge=False)
            if trial.failure <= enough:
                settled = trial
                break
        if settled is None:
            break
        result = settled
    return result


def _loop_mates(st: _State, rows: list[_Row], failing: set[int]) -> set[int]:
    """The joints that lie on a common cycle with a failing joint: the
    biconnected blocks of the joint graph that hold one, where every
    anchored body (the world, a fixed body, one with any held channel) is
    one node. A joint on no cycle (a tree hung from one anchor) can always
    be satisfied, so it is never a conflict, and is in no block of more than
    itself."""
    anchors = {0} | {
        i for i in range(1, len(st.x)) if st.bodies[i - 1].fixed or i in st.held
    }

    def node(i: int) -> int:
        return 0 if i in anchors else i

    edges: dict[int, tuple[int, int]] = {}
    for kind, j, p in rows:
        if j >= 0 and j not in edges:
            edges[j] = (node(p[0]), node(p[1] if kind == "ang" else p[3]))
    adjacency: dict[int, list[tuple[int, int]]] = {}
    blocks: list[list[int]] = []
    for j, (a, b) in edges.items():
        if a == b:
            blocks.append([j])  # a joint between two anchors is a loop by itself
            continue
        adjacency.setdefault(a, []).append((b, j))
        adjacency.setdefault(b, []).append((a, j))
    # Tarjan's biconnected components, iteratively, on a multigraph.
    disc: dict[int, int] = {}
    low: dict[int, int] = {}
    edge_stack: list[int] = []
    clock = 0
    for root in sorted(adjacency):
        if root in disc:
            continue
        disc[root] = low[root] = clock
        clock += 1
        stack = [(root, -1, iter(adjacency[root]))]
        while stack:
            v, parent_edge, neighbours = stack[-1]
            descended = False
            for w, e in neighbours:
                if e == parent_edge:
                    continue
                if w not in disc:
                    edge_stack.append(e)
                    disc[w] = low[w] = clock
                    clock += 1
                    stack.append((w, e, iter(adjacency[w])))
                    descended = True
                    break
                if disc[w] < disc[v]:
                    edge_stack.append(e)
                    low[v] = min(low[v], disc[w])
            if descended:
                continue
            stack.pop()
            if stack:
                u = stack[-1][0]
                low[u] = min(low[u], low[v])
                if low[v] >= disc[u]:
                    block = []
                    while True:
                        e = edge_stack.pop()
                        block.append(e)
                        if e == parent_edge:
                            break
                    blocks.append(block)
    mates: set[int] = set()
    for block in blocks:
        cyclic = len(block) > 1 or edges[block[0]][0] == edges[block[0]][1]
        if cyclic and failing.intersection(block):
            mates.update(block)
    return mates


def _nudge(st: _State) -> None:
    """Turn every body free to turn by :data:`DFLT_NUDGE`, alternating in
    sign: a straight chain pushed along its length has no sideways
    correction to buckle with, and this gives it one, the same every time."""
    for i in range(1, len(st.x)):
        if st.inv_i[i]:
            st.th[i] += DFLT_NUDGE if i % 2 else -DFLT_NUDGE


def _require_finite(
    bodies: Sequence[Body],
    joints: Sequence[Joint],
    forces: Sequence[Force],
    *,
    gravity: Gravity | None,
    dt: float | None,
) -> None:
    """Refuse a NaN or an infinity anywhere in the inputs: it would spread
    through every body the solve touches and still measure as satisfied."""

    def numbers(value: Any) -> list[float]:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return [float(value)]
        if isinstance(value, Point):
            return [float(value.u), float(value.v)]
        if isinstance(value, (tuple, list)):
            return [x for v in value for x in numbers(v)]
        return []

    def check(what: str, values: Any) -> None:
        if not all(math.isfinite(v) for v in numbers(values)):
            raise KinematicsError(f"{what} has a value that is not finite: {values!r}")

    for b in bodies:
        check(
            f"body {b.name!r}",
            [
                b.x,
                b.y,
                b.rotation,
                b.scale,
                b.width,
                b.height,
                b.origin,
                b.density,
                b.vx,
                b.vy,
                b.omega,
            ],
        )
    for j, joint in enumerate(joints):
        check(f"joint {j}", [getattr(joint, f.name) for f in fields(joint)])
    for f in forces:
        check("a force", [f.point, f.vector, f.toward, f.strength])
    check("gravity", gravity)
    check("dt", dt)


def _measure(
    st: _State,
    rows: list[_Row],
    n_joints: int,
    *,
    tolerance: float,
    angle_tolerance: float,
) -> tuple[
    tuple[float, ...], tuple[tuple[int, float], ...], tuple[tuple[int, float], ...]
]:
    """Residuals per joint, the rigid joints above ``tolerance``, and the
    rigid angle ranges broken by more than ``angle_tolerance``. A compliant
    joint's stretch is what it was asked for: it is in the residuals, never
    a failure."""
    values = _project(st, rows, [0.0] * (2 * len(rows)), 1.0, apply=False)
    residuals = [0.0] * n_joints
    rigid = [True] * n_joints
    limits: list[tuple[int, float]] = []
    for (kind, j, p), c in zip(rows, values):
        soft = p[-1] > 0.0
        if kind == "ang":
            if abs(c) > angle_tolerance and not soft:
                limits.append((j, c))
        else:
            residuals[j] = max(residuals[j], abs(c))
            rigid[j] = rigid[j] and not soft
    unsatisfied = tuple(
        (j, r)
        for j, r in enumerate(residuals)
        if rigid[j] and (r > tolerance or not math.isfinite(r))
    )
    return tuple(residuals), unsatisfied, tuple(limits)


def _step(
    st: _State,
    rows: list[_Row],
    lam: list[float],
    forces: Sequence[Force],
    gravity: Gravity | None,
    dt: float,
    *,
    substeps: int,
    iterations: int,
    damping: float,
) -> None:
    """Dynamic mode: ``substeps`` of predict (gravity, pushes, velocities),
    project, and derive the velocities from the move (XPBD's order)."""
    h = dt / substeps
    gx, gy = (float(g) for g in gravity) if gravity is not None else (0.0, 0.0)
    n = len(st.x)
    # Gravity acts at each body's centre (a body turning about a held pivot
    # feels its torque); a push at its point. Both are per unit mass.
    pushes = []
    if gx or gy:
        for i in range(1, n):
            cx, cy = st.centre[i][0] - st.ref[i][0], st.centre[i][1] - st.ref[i][1]
            pushes.append((i, cx, cy, gx, gy))
    for f in forces:
        if f.vector is not None:
            i, lx, ly = st.offset(f.point)
            if i:
                pushes.append((i, lx, ly, float(f.vector[0]), float(f.vector[1])))
    start_x, start_y, start_th = list(st.x), list(st.y), list(st.th)
    keep = 1.0 - damping
    for s in range(1, substeps + 1):
        px, py, pth = list(st.x), list(st.y), list(st.th)
        for i, lx, ly, fx, fy in pushes:
            if st.inv_m[i]:
                st.vx[i] += fx * h
                st.vy[i] += fy * h
            if st.inv_i[i] and (lx or ly):
                c, s_ = math.cos(st.th[i]), math.sin(st.th[i])
                rx, ry = c * lx - s_ * ly, s_ * lx + c * ly
                st.om[i] += (rx * fy - ry * fx) * st.m[i] * st.inv_i[i] * h
        for i in range(1, n):
            if st.inv_m[i]:
                st.x[i] += st.vx[i] * h
                st.y[i] += st.vy[i] * h
            if st.inv_i[i]:
                st.th[i] += st.om[i] * h
        along = s / substeps
        st.restore_held(along)
        for k in range(len(lam)):
            lam[k] = 0.0
        for _ in range(iterations):
            _project(st, rows, lam, h, apply=True)
            st.restore_held(along)
        for i in range(1, n):
            if st.inv_m[i]:
                st.vx[i] = (st.x[i] - px[i]) / h * keep
                st.vy[i] = (st.y[i] - py[i]) / h * keep
            if st.inv_i[i]:
                st.om[i] = (st.th[i] - pth[i]) / h * keep
    # A held body's velocity is the motion its target gave it this frame, so
    # a body let go keeps the throw.
    for i in range(1, n):
        if not st.inv_m[i]:
            st.vx[i] = (st.x[i] - start_x[i]) / dt
            st.vy[i] = (st.y[i] - start_y[i]) / dt
        if not st.inv_i[i]:
            st.om[i] = (st.th[i] - start_th[i]) / dt


# -----------------------------------------------------------------------------
# frames
# -----------------------------------------------------------------------------


def resolve_rests(bodies: Sequence[Body], joints: Sequence[Joint]) -> list[Joint]:
    """``joints`` with every ``rest=None`` hinge and weld given the relative
    angle the bodies have now, so a run of frames measures its limits from
    one pose rather than from each frame's.

    >>> a = Body("a", rotation=0.1); b = Body("b", rotation=0.4)
    >>> [round(j.rest, 3) for j in resolve_rests([a, b], [Hinge(Point("a", 0.5, 0.5), Point("b", 0.5, 0.5), limits=(-1.0, 1.0))])]
    [0.3]
    """
    st = _State(bodies)
    out: list[Joint] = []
    for joint in joints:
        if isinstance(joint, (Hinge, Weld)) and joint.rest is None:
            ia, ib = st.body_index(joint.a.body), st.body_index(joint.b.body)
            joint = replace(joint, rest=_wrap(st.th[ib] - st.th[ia]))
        out.append(joint)
    return out


def solve_frames(
    bodies: Sequence[Body],
    joints: Sequence[Joint],
    *,
    frames: int,
    dt: float | None,
    targets_at: Callable[[int], Targets | None]
    | Sequence[Targets | None]
    | None = None,
    joints_at: Callable[[int], Sequence[Joint]] | None = None,
    forces: Sequence[Force] = (),
    gravity: Gravity | None = None,
    **options: Any,
) -> FramesResult:
    """``frames`` solves in a row, each starting from the last: the caller's
    time dimension. ``targets_at(k)`` (or ``targets_at[k]``) gives frame
    ``k``'s targets; ``joints_at(k)`` its joints (the same list with
    ``joined`` flags flipped is how a joint is unjoined and rejoined). Hinge
    and weld rests are fixed from the starting poses. ``options`` go to
    :func:`solve`.

    A part unjoined falls, and is caught where it is when rejoined:

    >>> peg = Body("peg", width=2.0, height=2.0, fixed=True)
    >>> part = Body("part", y=10.0, width=4.0, height=20.0, origin=(0.5, 0.0))
    >>> joined = [Pin(Point("part", 0.5, 0.0), Point("peg", 0.5, 0.5))]
    >>> loose = [Pin(Point("part", 0.5, 0.0), Point("peg", 0.5, 0.5), joined=False)]
    >>> r = solve_frames([peg, part], joined, frames=12, dt=1 / 24, gravity=(0.0, 980.0),
    ...                  joints_at=lambda k: loose if 2 <= k < 8 else joined)
    >>> bool(r.poses[1, 1, 1] < r.poses[7, 1, 1]), r.snaps[0][:2], r.snaps[0][2] > 2.0
    (True, (8, 0), True)
    >>> r.unsatisfied[-1]
    ()
    """
    if frames < 0:
        raise KinematicsError("frames must be non-negative")
    if targets_at is not None and not callable(targets_at) and len(targets_at) < frames:
        raise KinematicsError(
            f"targets_at has {len(targets_at)} entries for {frames} frames"
        )
    current = tuple(bodies)
    base = resolve_rests(current, joints)
    enforced_before = [j.joined for j in base]
    poses, unsat, lims, snaps, drops = [], [], [], [], []
    for k in range(frames):
        frame_joints = base
        if joints_at is not None:
            frame_joints = list(joints_at(k))
            if len(frame_joints) != len(base):
                raise KinematicsError(
                    f"frame {k}: joints_at must return one entry per joint, in order"
                )
            frame_joints = [_with_rest(fj, bj) for fj, bj in zip(frame_joints, base)]
        reengaged = [
            (j, _gap(current, joint))
            for j, joint in enumerate(frame_joints)
            if joint.joined and not enforced_before[j]
        ]
        if targets_at is None:
            targets = None
        elif callable(targets_at):
            targets = targets_at(k)
        else:
            targets = targets_at[k]
        r = solve(
            current,
            frame_joints,
            targets=targets,
            forces=forces,
            gravity=gravity,
            dt=dt,
            **options,
        )
        snaps += [(k, j, gap) for j, gap in reengaged if j not in r.dropped]
        enforced_before = [
            joint.joined and j not in r.dropped for j, joint in enumerate(frame_joints)
        ]
        current = r.bodies
        poses.append(r.poses)
        unsat.append(r.unsatisfied)
        lims.append(r.limit_violations)
        drops.append(r.dropped)
    stacked = (
        np.stack(poses) if poses else np.empty((0, len(current), len(POSE_CHANNELS)))
    )
    return FramesResult(
        bodies=tuple(b.name for b in current),
        poses=stacked,
        unsatisfied=tuple(unsat),
        limit_violations=tuple(lims),
        snaps=tuple(snaps),
        final=current,
        dropped=tuple(drops),
    )


def _with_rest(frame_joint: Joint, base_joint: Joint) -> Joint:
    if isinstance(frame_joint, (Hinge, Weld)) and frame_joint.rest is None:
        return replace(frame_joint, rest=getattr(base_joint, "rest", None))
    return frame_joint


def _gap(bodies: Sequence[Body], joint: Joint) -> float:
    """How far apart a joint's two points are now (0 for a segment joint)."""
    if not isinstance(joint, (Pin, Hinge, Weld, Distance)):
        return 0.0
    st = _State(bodies)
    ia, lxa, lya = st.offset(joint.a)
    ib, lxb, lyb = st.offset(joint.b)
    ax, ay = st.world(ia, lxa, lya)
    bx, by = st.world(ib, lxb, lyb)
    gap = math.hypot(ax - bx, ay - by)
    if isinstance(joint, Distance):
        if joint.mode == "at_least":
            return max(0.0, joint.length - gap)
        if joint.mode == "at_most":
            return max(0.0, gap - joint.length)
        return abs(gap - joint.length)
    return gap


# -----------------------------------------------------------------------------
# What a document stores
# -----------------------------------------------------------------------------


def quantize(
    poses: np.ndarray,
    *,
    position_quantum: float = DFLT_POSITION_QUANTUM,
    angle_quantum: float = DFLT_ANGLE_QUANTUM,
) -> np.ndarray:
    """``poses`` (any shape whose last axis is :data:`POSE_CHANNELS`) rounded
    to the quanta a document stores: positions and scale to
    ``position_quantum``, rotation to ``angle_quantum``.

    >>> q = quantize(np.array([[1.00000049, 2.0, 0.123456789, 1.0]]))
    >>> float(q[0, 0]), bool(abs(q[0, 2] - 0.1234568) < 1e-15)
    (1.0, True)
    """
    out = np.asarray(poses, dtype=np.float64).copy()
    out[..., 0] = np.round(out[..., 0] / position_quantum) * position_quantum
    out[..., 1] = np.round(out[..., 1] / position_quantum) * position_quantum
    out[..., 2] = np.round(out[..., 2] / angle_quantum) * angle_quantum
    out[..., 3] = np.round(out[..., 3] / position_quantum) * position_quantum
    return out


def digest(poses: np.ndarray, **quanta: float) -> str:
    """A hex digest of the quantized poses' bytes, with the solver version:
    for comparing solved poses on one platform (a golden test). A cache key
    is built on the inputs instead (:func:`inputs_digest`).

    >>> digest(np.zeros((2, 4))) == digest(np.zeros((2, 4)) + 1e-9)
    True
    """
    q = np.ascontiguousarray(quantize(poses, **quanta))
    h = hashlib.sha256()
    h.update(SOLVER_VERSION.encode())
    h.update(str(q.shape).encode())
    h.update(q.tobytes())
    return h.hexdigest()


def inputs_digest(
    bodies: Sequence[Body],
    joints: Sequence[Joint],
    *,
    targets: Targets | Sequence[Targets | None] | None = None,
    forces: Sequence[Force] = (),
    gravity: Gravity | None = None,
    **options: Any,
) -> str:
    """A hex digest of everything a solve reads, with :data:`SOLVER_VERSION`:
    the cache key for a solve (or a run of them: pass the per-frame targets
    as a list, and ``frames``, ``dt`` and the rest as ``options``). Floats
    are hashed exactly (``float.hex``); mappings by sorted key.

    >>> a = inputs_digest([Body("b", x=1.0)], [], dt=1 / 24)
    >>> a == inputs_digest([Body("b", x=1.0)], [], dt=1 / 24), a == inputs_digest([Body("b", x=1.0 + 1e-15)], [], dt=1 / 24)
    (True, False)
    """

    def canon(value: Any) -> Any:
        if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
            return value
        if isinstance(value, float):
            return value.hex()
        if isinstance(value, (Body, Point, Force, *_JOINT_TYPES)):
            return [
                type(value).__name__,
                {f.name: canon(getattr(value, f.name)) for f in fields(value)},
            ]
        if isinstance(value, Mapping):
            return {str(k): canon(value[k]) for k in sorted(value)}
        if isinstance(value, (list, tuple)):
            return [canon(v) for v in value]
        raise KinematicsError(f"cannot key a {type(value).__name__}: pass plain values")

    document = canon(
        dict(
            version=SOLVER_VERSION,
            bodies=list(bodies),
            joints=list(joints),
            targets=targets,
            forces=list(forces),
            gravity=gravity,
            options=options,
        )
    )
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


_JOINT_TYPES = (Pin, Hinge, Weld, Distance, Slide, Contact)
