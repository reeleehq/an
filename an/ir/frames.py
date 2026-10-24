"""Frames of reference: a tree of named poses over film time (ADR 0009 amendment, an#501).

A **frame** is a rigid pose (a position and an orientation) as a function of
film time, relative to a parent frame; ``world`` is the root. Every element of
the scene's world (a member, a viewpoint, a stream, a plane) is in exactly one
frame, with a local pose in that frame's units. Its world pose is the
composition of the poses up the chain, and what a viewpoint sees is the
pinhole projection of world poses into the viewpoint's own frame (the
projection itself is :class:`an.ir.world.Projection`). The multiplane camera,
the moving panorama, the process shot and the camera rig are all the same
tree with a different shape: what stands still in one frame is scenery in
another, and the eye is attached to whichever frame the shot is in.

Orientation uses the viewpoint's convention: ``look: [yaw, pitch, roll]``
degrees, the frame's local axes being ``(right, down, forward)`` — so a frame
with ``look`` zero is the world's axes (``x`` right, ``y`` DOWN, ``z`` away
from the viewer).

A **far** frame follows its parent's rotation and none of its translation: what
is at infinity turns with the camera and never moves with it.

This module is pure geometry on tuples; it imports the schema's :class:`Frame`
and the easing function, nothing else. It is an extraction candidate: previz
(an#257) is the TypeScript twin of the same vocabulary.

>>> from an.ir.schema import Frame, FrameMoving
>>> tree = FrameTree({
...     "car": Frame(moving=FrameMoving(speed=20.0)),
...     "seat": Frame(parent="car", at=(0.45, 0.65, 1.6)),
...     "horizon": Frame(parent="car", coupling="far"),
... })
>>> tree.world_pose("seat", 2.0).at          # 2 s on: the seat is 40 m down the road
(0.45, 0.65, 41.6)
>>> tree.world_pose("horizon", 2.0).at       # at infinity: never translates
(0.0, 0.0, 0.0)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from an.ir.schema import WORLD_FRAME, Frame
from an.timing.easing import apply_easing

__all__ = [
    "FRAME_PROPERTIES",
    "Axes",
    "FrameError",
    "FrameTree",
    "Pose",
    "Track",
    "TrackEvent",
    "Vec3",
    "look_basis",
]

Vec3 = tuple[float, float, float]
#: ``(right, down, forward)``: a frame's local axes in its parent's coordinates.
Axes = tuple[Vec3, Vec3, Vec3]

#: The channels of a frame an ordinary ``set``/``tween`` may target
#: (``<frame>:at_x``): its position in its parent's units, its orientation in
#: degrees.
FRAME_PROPERTIES: tuple[str, ...] = ("at_x", "at_y", "at_z", "yaw", "pitch", "roll")

_ZERO: Vec3 = (0.0, 0.0, 0.0)
#: Two poses closer than this (units, and unit-vector components) are one pose.
_SAME_POSE_EPS: float = 1e-9
#: Sample points per shot when asking whether a pose changes within it.
_STATIC_SAMPLES: int = 33


class FrameError(ValueError):
    """A frame tree that cannot be built or evaluated (an unknown frame)."""


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a: Vec3, k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _unit(a: Vec3) -> Vec3:
    n = math.sqrt(_dot(a, a))
    if n == 0.0:
        raise FrameError("a direction must not be the zero vector")
    return _mul(a, 1.0 / n)


def look_basis(yaw: float, pitch: float, roll: float) -> Axes:
    """``(forward, right, down)`` for a look of ``yaw`` (turn right), ``pitch``
    (look down) and ``roll`` (the PICTURE turns clockwise: what was on the
    right moves to the bottom), in degrees.

    >>> [tuple(round(v, 6) + 0.0 for v in axis) for axis in look_basis(0.0, 0.0, 0.0)]
    [(0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    >>> [round(v, 6) + 0.0 for v in look_basis(90.0, 0.0, 0.0)[0]]
    [1.0, 0.0, 0.0]
    """
    t, p, r_ = (math.radians(a) for a in (yaw, pitch, roll))
    forward: Vec3 = (
        math.sin(t) * math.cos(p),
        math.sin(p),
        math.cos(t) * math.cos(p),
    )
    right: Vec3 = (math.cos(t), 0.0, -math.sin(t))
    down = _cross(forward, right)
    if r_:
        c, s = math.cos(r_), math.sin(r_)
        right, down = (
            _add(_mul(right, c), _mul(down, -s)),
            _add(_mul(right, s), _mul(down, c)),
        )
    return forward, right, down


@dataclass(frozen=True)
class Pose:
    """A rigid pose: where a frame's origin is (``at``) and how its axes lie
    (``axes``, ``None`` for the parent's), both in the parent's coordinates.

    >>> Pose(at=(1.0, 0.0, 0.0)).apply((0.0, 0.0, 5.0))
    (1.0, 0.0, 5.0)
    >>> turned = Pose(axes=_axes(90.0, 0.0, 0.0))     # turned right by 90 degrees
    >>> [round(v, 6) + 0.0 for v in turned.apply((0.0, 0.0, 1.0))]
    [1.0, 0.0, 0.0]
    >>> [round(v, 6) + 0.0 for v in turned.unapply(turned.apply((2.0, 3.0, 4.0)))]
    [2.0, 3.0, 4.0]
    """

    at: Vec3 = _ZERO
    axes: Axes | None = None

    @property
    def is_identity(self) -> bool:
        return self.axes is None and self.at == _ZERO

    def rotate(self, v: Vec3) -> Vec3:
        """A direction in this frame's axes, in the parent's."""
        if self.axes is None:
            return v
        right, down, forward = self.axes
        return _add(_add(_mul(right, v[0]), _mul(down, v[1])), _mul(forward, v[2]))

    def apply(self, p: Vec3) -> Vec3:
        """A point in this frame's units, in the parent's."""
        if self.axes is None:
            return p if self.at == _ZERO else _add(p, self.at)
        return _add(self.rotate(p), self.at)

    def unapply(self, p: Vec3) -> Vec3:
        """The inverse of :meth:`apply`."""
        q = p if self.at == _ZERO else _sub(p, self.at)
        if self.axes is None:
            return q
        right, down, forward = self.axes
        return (_dot(q, right), _dot(q, down), _dot(q, forward))

    def compose(self, child: "Pose") -> "Pose":
        """``self ∘ child``: the child's pose seen from this pose's parent.

        >>> Pose(at=(10.0, 0.0, 0.0)).compose(Pose(at=(1.0, 0.0, 0.0))).at
        (11.0, 0.0, 0.0)
        """
        if child.axes is None:
            axes = self.axes
        elif self.axes is None:
            axes = child.axes
        else:
            axes = tuple(self.rotate(a) for a in child.axes)  # type: ignore[assignment]
        return Pose(self.apply(child.at), axes)

    def inverse(self) -> "Pose":
        """The pose that undoes this one."""
        if self.axes is None:
            return Pose(_mul(self.at, -1.0) if self.at != _ZERO else _ZERO)
        right, down, forward = self.axes
        inv: Axes = (
            (right[0], down[0], forward[0]),
            (right[1], down[1], forward[1]),
            (right[2], down[2], forward[2]),
        )
        return Pose(self.unapply(_ZERO), inv)

    def same_as(self, other: "Pose") -> bool:
        """Equal within :data:`_SAME_POSE_EPS` (position and axes)."""
        if any(abs(a - b) > _SAME_POSE_EPS for a, b in zip(self.at, other.at)):
            return False
        a, b = self.axes or _IDENTITY_AXES, other.axes or _IDENTITY_AXES
        return all(
            abs(x - y) <= _SAME_POSE_EPS
            for u, v in zip(a, b)
            for x, y in zip(u, v)
        )


_IDENTITY_AXES: Axes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _axes(yaw: float, pitch: float, roll: float) -> Axes | None:
    """The ``(right, down, forward)`` axes of a look, ``None`` for the identity
    (so a frame that does not turn costs, and changes, nothing)."""
    if not (yaw or pitch or roll):
        return None
    forward, right, down = look_basis(yaw, pitch, roll)
    return right, down, forward


# --- a channel animated by ordinary actions ----------------------------------------


@dataclass(frozen=True)
class TrackEvent:
    """One ``set`` (``start == end``) or ``tween`` of a channel, in shot time."""

    start: float
    end: float
    to: float
    from_: float | None = None
    easing: Any = None


@dataclass(frozen=True)
class Track:
    """The ``set``/``tween`` actions on one channel of a frame, as a function
    of shot time: it holds the base value until the first event, a set steps,
    a tween ramps from its ``from_`` (the value the channel has when it starts,
    if unset) and holds its end.

    >>> track = Track([TrackEvent(1.0, 3.0, to=10.0, easing=None)])
    >>> track.value(0.0, 4.0), track.value(2.0, 4.0), track.value(5.0, 4.0)
    (4.0, 7.0, 10.0)
    """

    events: Sequence[TrackEvent]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "events", tuple(sorted(self.events, key=lambda e: (e.start, e.end)))
        )

    def value(self, t: float, base: float) -> float:
        state = base
        for ev in self.events:
            if ev.start > t:
                break
            if ev.end <= ev.start or t >= ev.end:
                state = ev.to
                continue
            a = state if ev.from_ is None else ev.from_
            u = (t - ev.start) / (ev.end - ev.start)
            return a + (ev.to - a) * apply_easing(ev.easing, u)
        return state

    @property
    def breaks(self) -> tuple[float, ...]:
        """Where the channel's behaviour changes: every event's start and end."""
        return tuple(sorted({x for e in self.events for x in (e.start, e.end)}))


# --- the tree ---------------------------------------------------------------------


class FrameTree:
    """The frames of a scene and the world pose of anything in one of them.

    ``tracks`` are the shot's ``set``/``tween`` actions on frame channels
    (``{frame: {channel: Track}}``, shot time): a track REPLACES the channel's
    declared value for that shot, the way a pose value replaces a property.
    ``moving`` adds ``direction × speed × film time`` to the position on top.
    Poses are evaluated at a shot time ``t`` with ``film_start`` the shot's
    start in the film, so a moving frame keeps its phase across a cut.

    >>> from an.ir.schema import Frame, FrameMoving
    >>> tree = FrameTree({"car": Frame(moving=FrameMoving(speed=10.0))})
    >>> tree.world_pose("car", 1.0, film_start=4.0).at
    (0.0, 0.0, 50.0)
    >>> tree.relative_pose("world", "car", 1.0).at        # the world seen from the car: it comes at us
    (0.0, 0.0, -10.0)
    >>> FrameTree({"a": Frame(parent="b"), "b": Frame(parent="a")})
    Traceback (most recent call last):
    ...
    an.ir.frames.FrameError: frames form a cycle through 'a'
    """

    def __init__(
        self,
        frames: Mapping[str, Frame],
        *,
        tracks: Mapping[str, Mapping[str, Track]] | None = None,
    ):
        self.frames: dict[str, Frame] = dict(frames)
        self.tracks = {k: dict(v) for k, v in (tracks or {}).items()}
        for name, frame in self.frames.items():
            if frame.parent != WORLD_FRAME and frame.parent not in self.frames:
                raise FrameError(
                    f"frame {name!r} has parent {frame.parent!r}, which is not a frame"
                )
        for name in self.frames:
            seen, cur = set(), name
            while cur != WORLD_FRAME:
                if cur in seen:
                    raise FrameError(f"frames form a cycle through {cur!r}")
                seen.add(cur)
                cur = self.frames[cur].parent

    def __contains__(self, name: str) -> bool:
        return name == WORLD_FRAME or name in self.frames

    def _frame(self, name: str) -> Frame:
        try:
            return self.frames[name]
        except KeyError:
            raise FrameError(
                f"unknown frame {name!r}; the frames are "
                f"{sorted({WORLD_FRAME, *self.frames})}"
            ) from None

    def chain(self, name: str) -> list[str]:
        """The frames from ``name`` up to (not including) the world, root first."""
        out: list[str] = []
        cur = name
        while cur != WORLD_FRAME:
            self._frame(cur)
            out.append(cur)
            cur = self.frames[cur].parent
        return list(reversed(out))

    def _channel(self, name: str, prop: str, base: float, t: float) -> float:
        track = self.tracks.get(name, {}).get(prop)
        return base if track is None else track.value(t, base)

    def local_pose(self, name: str, t: float, *, film_start: float = 0.0) -> Pose:
        """``name``'s pose in its parent's units at shot time ``t``."""
        f = self._frame(name)
        ch = self._channel
        at: Vec3 = (
            ch(name, "at_x", f.at[0], t),
            ch(name, "at_y", f.at[1], t),
            ch(name, "at_z", f.at[2], t),
        )
        if f.moving is not None:
            by = _mul(_unit(tuple(map(float, f.moving.direction))), float(f.moving.speed) * (film_start + t))  # type: ignore[arg-type]
            at = _add(at, by)
        return Pose(
            at,
            _axes(
                ch(name, "yaw", f.look[0], t),
                ch(name, "pitch", f.look[1], t),
                ch(name, "roll", f.look[2], t),
            ),
        )

    def world_pose(self, name: str, t: float, *, film_start: float = 0.0) -> Pose:
        """``name``'s pose in the world at shot time ``t``: the poses up the
        chain composed; a ``far`` edge keeps its parent's rotation and none of
        its translation."""
        pose = Pose()
        for n in self.chain(name):
            local = self.local_pose(n, t, film_start=film_start)
            if self.frames[n].coupling == "far":
                inherited = Pose(_ZERO, pose.axes)
                pose = Pose(local.at, inherited.compose(Pose(_ZERO, local.axes)).axes)
            else:
                pose = pose.compose(local)
        return pose

    def relative_pose(
        self, name: str, to: str, t: float, *, film_start: float = 0.0
    ) -> Pose:
        """``name``'s pose expressed in ``to``'s coordinates: what takes a point
        in ``name`` to the same point in ``to``."""
        if name == to:
            return Pose()
        return (
            self.world_pose(to, t, film_start=film_start)
            .inverse()
            .compose(self.world_pose(name, t, film_start=film_start))
        )

    def is_still(self, name: str) -> bool:
        """Whether ``name`` and every frame above it are fixed for any shot:
        nothing moves them and no action animates them."""
        return all(
            self.frames[n].moving is None and not self.tracks.get(n)
            for n in self.chain(name)
        )

    def is_static(
        self,
        name: str,
        to: str,
        duration: float,
        *,
        film_start: float = 0.0,
        samples: int = _STATIC_SAMPLES,
    ) -> bool:
        """Whether ``name`` stands still in ``to`` through a shot of ``duration``
        seconds: the same frame, two frames that move together, or two still
        ones. Sampled (and at every action's start and end), exactly equal
        within :data:`_SAME_POSE_EPS`.

        >>> from an.ir.schema import Frame, FrameMoving
        >>> tree = FrameTree({"car": Frame(moving=FrameMoving(speed=5.0)), "seat": Frame(parent="car", at=(1.0, 0.0, 0.0))})
        >>> tree.is_static("seat", "car", 2.0), tree.is_static("world", "car", 2.0)
        (True, False)
        """
        if name == to:
            return True
        if self.is_still(name) and self.is_still(to):
            return True
        times = {duration * i / samples for i in range(samples + 1)}
        for n in (*self.chain(name), *self.chain(to)):
            for track in self.tracks.get(n, {}).values():
                times.update(b for b in track.breaks if 0.0 <= b <= duration)
        first = self.relative_pose(name, to, 0.0, film_start=film_start)
        return all(
            first.same_as(self.relative_pose(name, to, t, film_start=film_start))
            for t in sorted(times)
        )

    def constant_motion(self, name: str) -> tuple[Vec3, float] | None:
        """``(unit direction, speed)`` when ``name`` is a frame of the world
        that does nothing but translate at a constant velocity from the origin
        (a ``vehicle``), else ``None``: the case a straight travel's streams are
        solved for in closed form."""
        f = self.frames.get(name)
        if (
            f is None
            or f.parent != WORLD_FRAME
            or f.moving is None
            or f.coupling != "rigid"
            or tuple(f.at) != _ZERO
            or any(f.look)
            or self.tracks.get(name)
        ):
            return None
        return _unit(tuple(map(float, f.moving.direction))), float(f.moving.speed)  # type: ignore[arg-type]
