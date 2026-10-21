"""Planes of movement: a tree of frames of reference, membership over time, and its lowering.

Reference implementation for ``planes_of_movement.md`` beside it, and the
starter for an#501 (frames) and an#502 (reframe). Pure Python, no
dependencies, doctested: ``python -m doctest planes_of_movement_frames.py``.

The model in one paragraph. A **frame** is a named rigid pose (position and
yaw) as a function of film time, relative to a parent frame; ``world`` is the
root. Every **member** (a character, a prop, a plane, a viewpoint) belongs to
exactly one frame at a time, with a local pose in that frame's units. A
member's world pose is the composition up the chain; a viewpoint's picture is
the pinhole projection of world poses into the viewpoint's own frame (ADR
0007's formula). A **far** frame is coupled to its parent by rotation only
(what is at infinity turns with the camera but never translates). A
**reframe** moves a member to another frame at an instant, keeping its world
pose (and, optionally, inheriting the old frame's velocity: the Galilean
composition). Everything the renderer sees is still a 2D placement per
frame; the frames only decide which placements are consistent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Literal

Vec3 = tuple[float, float, float]
Coupling = Literal["rigid", "far"]

#: Gravity along the stage's +y (down), in world units per second squared.
DFLT_GRAVITY: float = 9.81
#: Finite-difference step for a frame's velocity (seconds).
_DT: float = 1e-3


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a: Vec3, k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def _rot_y(p: Vec3, yaw_deg: float) -> Vec3:
    """Turn ``p`` right by ``yaw_deg`` about the vertical (the stage's y)."""
    t = math.radians(yaw_deg)
    c, s = math.cos(t), math.sin(t)
    return (c * p[0] + s * p[2], p[1], -s * p[0] + c * p[2])


@dataclass(frozen=True)
class Pose:
    """A rigid pose: where a frame's origin is and which way it faces (yaw,
    degrees, turning right), in its parent's units.

    >>> tuple(round(v, 6) + 0.0 for v in Pose((1.0, 0.0, 0.0), yaw=90.0).apply((0.0, 0.0, 1.0)))
    (2.0, 0.0, 0.0)
    """

    at: Vec3 = (0.0, 0.0, 0.0)
    yaw: float = 0.0

    def apply(self, p: Vec3) -> Vec3:
        """A point in this frame's units, in the parent's."""
        x, y, z = _rot_y(p, self.yaw)
        return (x + self.at[0], y + self.at[1], z + self.at[2])

    def unapply(self, p: Vec3) -> Vec3:
        """The inverse of :meth:`apply`."""
        return _rot_y(_sub(p, self.at), -self.yaw)

    def compose(self, child: "Pose") -> "Pose":
        """``self ∘ child``: the child's pose seen from this frame's parent.

        >>> Pose((10.0, 0.0, 0.0)).compose(Pose((1.0, 0.0, 0.0), yaw=30.0))
        Pose(at=(11.0, 0.0, 0.0), yaw=30.0)
        """
        return Pose(self.apply(child.at), self.yaw + child.yaw)

    def relative_to(self, other: "Pose") -> "Pose":
        """This pose expressed in ``other``'s frame (both given in one parent)."""
        return Pose(other.unapply(self.at), self.yaw - other.yaw)


@dataclass(frozen=True)
class Frame:
    """A frame of reference: a pose over film time, relative to ``parent``.

    ``coupling="far"`` is the frame at infinity: it inherits its parent's
    rotation and ignores its translation (a sky, a mountain range, a sun).
    """

    name: str
    parent: str | None = "world"
    pose: Callable[[float], Pose] = lambda t: Pose()
    coupling: Coupling = "rigid"


def moving(at0: Vec3, *, velocity: Vec3, yaw: float = 0.0) -> Callable[[float], Pose]:
    """A frame translating at a constant velocity (a car on a straight road).

    >>> moving((0.0, 0.0, 0.0), velocity=(0.0, 0.0, 20.0))(1.5).at
    (0.0, 0.0, 30.0)
    """
    return lambda t: Pose(_add(at0, _mul(velocity, t)), yaw)


def still(at: Vec3 = (0.0, 0.0, 0.0), *, yaw: float = 0.0) -> Callable[[float], Pose]:
    return lambda t: Pose(at, yaw)


class FrameTree:
    """The frames of a scene, and the world pose of anything in one of them.

    >>> tree = FrameTree([
    ...     Frame("car", pose=moving((0.0, 0.0, 0.0), velocity=(0.0, 0.0, 20.0))),
    ...     Frame("seat", parent="car", pose=still((0.45, 0.65, 1.6))),
    ...     Frame("horizon", parent="car", coupling="far"),
    ... ])
    >>> tree.world_pose("seat", 2.0).at
    (0.45, 0.65, 41.6)
    >>> tree.world_pose("horizon", 2.0).at          # at infinity: never translates
    (0.0, 0.0, 0.0)
    """

    def __init__(self, frames: list[Frame]):
        self.frames: dict[str, Frame] = {"world": Frame("world", parent=None)}
        for f in frames:
            if f.name in self.frames:
                raise ValueError(f"duplicate frame {f.name!r}")
            self.frames[f.name] = f
        for f in frames:
            if f.parent not in self.frames:
                raise ValueError(f"frame {f.name!r}: unknown parent {f.parent!r}")
        self._check_tree()

    def _check_tree(self) -> None:
        for name in self.frames:
            seen, cur = set(), name
            while cur is not None:
                if cur in seen:
                    raise ValueError(f"frames form a cycle through {cur!r}")
                seen.add(cur)
                cur = self.frames[cur].parent

    def chain(self, name: str) -> list[Frame]:
        """Root first."""
        out, cur = [], name
        while cur is not None:
            f = self.frames[cur]
            out.append(f)
            cur = f.parent
        return list(reversed(out))

    def world_pose(self, name: str, t: float) -> Pose:
        pose = Pose()
        for f in self.chain(name):
            if f.parent is None:
                continue
            local = f.pose(t)
            if f.coupling == "far":
                # Rotation couples, translation does not: the far frame sits
                # at the parent's ORIGIN of rotation but at the world's origin.
                pose = Pose(local.at, pose.yaw + local.yaw)
            else:
                pose = pose.compose(local)
        return pose

    def to_world(self, name: str, p: Vec3, t: float) -> Vec3:
        return self.world_pose(name, t).apply(p)

    def from_world(self, name: str, p: Vec3, t: float) -> Vec3:
        return self.world_pose(name, t).unapply(p)

    def velocity(self, name: str, t: float) -> Vec3:
        """The world velocity of ``name``'s origin (finite difference)."""
        a, b = self.world_pose(name, t - _DT).at, self.world_pose(name, t + _DT).at
        return tuple(round((bi - ai) / (2 * _DT), 9) for ai, bi in zip(a, b))  # type: ignore[return-value]

    def reframe(
        self,
        p_local: Vec3,
        *,
        frm: str,
        to: str,
        t: float,
        keep: Literal["world", "local"] = "world",
    ) -> Vec3:
        """A point's local coordinates in ``to`` after leaving ``frm`` at ``t``.

        ``keep="world"`` is Unity's ``worldPositionStays``, Unreal's
        ``KeepWorld``, Godot's ``keep_global_transform``: the picture does not
        jump. ``keep="local"`` is ``KeepRelative``: the numbers stay, the
        picture jumps to the new frame.

        >>> tree = FrameTree([Frame("car", pose=moving((0.0, 0.0, 0.0), velocity=(0.0, 0.0, 20.0)))])
        >>> tree.reframe((0.6, -0.3, 0.5), frm="car", to="world", t=2.0)
        (0.6, -0.3, 40.5)
        >>> tree.reframe((0.6, -0.3, 0.5), frm="car", to="world", t=2.0, keep="local")
        (0.6, -0.3, 0.5)
        """
        if keep == "local":
            return p_local
        return self.from_world(to, self.to_world(frm, p_local, t), t)


# --- projection (ADR 0007's pinhole, yaw only) ---------------------------------


def project(
    p_world: Vec3, *, viewpoint: Pose, focal: float
) -> tuple[float, float, float] | None:
    """Screen ``(sx, sy, 1/depth)`` of a world point seen from a viewpoint pose
    (its frame's world pose), or ``None`` behind the camera.

    >>> project((10.0, 0.0, 100.0), viewpoint=Pose(), focal=1000.0)
    (100.0, 0.0, 0.01)
    """
    x, y, z = viewpoint.unapply(p_world)
    if z <= 1e-9:
        return None
    return (focal * x / z, focal * y / z, 1.0 / z)


def parallax_factor(plane_depth: float, reference_depth: float) -> float:
    """The parallax factor an engine stores (Godot's ``scroll_scale``, an's
    ``Plane.depth``) is the LOWERED form of a plane at a world depth: a
    camera translating ``d`` shifts a plane at depth ``z`` by ``f·d/z`` on
    screen, so relative to the reference (character) plane the factor is
    ``z_ref / z_plane``. Infinity lowers to 0, the character plane to 1, a
    nearer plane to more than 1.

    >>> parallax_factor(20.0, 2.0), parallax_factor(math.inf, 2.0), parallax_factor(1.0, 2.0)
    (0.1, 0.0, 2.0)
    """
    if math.isinf(plane_depth):
        return 0.0
    return reference_depth / plane_depth


# --- the worked instance: the car, and a bottle out of the window --------------


def bottle_out_of_the_window(
    *,
    car_speed: float = 20.0,
    throw: Vec3 = (3.0, -2.0, 0.0),
    at: float = 2.0,
    gravity: float = DFLT_GRAVITY,
    inherit_velocity: bool = True,
) -> Callable[[float], Vec3]:
    """World trajectory of a bottle thrown sideways out of a moving car.

    The bottle is a member of ``car`` until ``at``; then it is reframed to
    ``world`` keeping its world position and, if ``inherit_velocity``, adding
    the car's velocity to its own (Galilean composition: u' = u + v). After
    that it is a projectile in the world frame. Seen from the car it stays
    abreast and drops (no drag), which is what a camera on the car shows and
    what nobody had to animate.

    >>> path = bottle_out_of_the_window()
    >>> [round(v, 2) for v in path(2.0)]               # the release point, in the world
    [0.6, -0.3, 40.5]
    >>> [round(v, 2) for v in path(2.5)]               # half a second later (y is DOWN: thrown up 2 m/s, falling back)
    [2.1, -0.07, 50.5]
    >>> tree = FrameTree([Frame("car", pose=moving((0.0, 0.0, 0.0), velocity=(0.0, 0.0, 20.0)))])
    >>> [round(v, 2) for v in tree.from_world("car", path(2.5), 2.5)]   # seen from the car: abreast, dropping
    [2.1, -0.07, 0.5]
    >>> dead = bottle_out_of_the_window(inherit_velocity=False)
    >>> [round(v, 2) for v in tree.from_world("car", dead(2.5), 2.5)]   # the mistake: it 'stops' in the world
    [2.1, -0.07, -9.5]
    """
    tree = FrameTree(
        [Frame("car", pose=moving((0.0, 0.0, 0.0), velocity=(0.0, 0.0, car_speed)))]
    )
    seat: Vec3 = (0.6, -0.3, 0.5)
    p0 = tree.reframe(seat, frm="car", to="world", t=at)
    v0 = _add(throw, tree.velocity("car", at)) if inherit_velocity else throw

    def path(t: float) -> Vec3:
        if t < at:
            return tree.to_world("car", seat, t)
        dt = t - at
        return (
            p0[0] + v0[0] * dt,
            p0[1] + v0[1] * dt + 0.5 * gravity * dt * dt,
            p0[2] + v0[2] * dt,
        )

    return path


def pole_seen_from_the_car(
    *, pole_z: float = 100.0, lane: float = 3.0, car_speed: float = 20.0, focal: float = 1000.0
) -> list[tuple[float, float]]:
    """A roadside pole (a WORLD member) through the windscreen of a car (the
    viewpoint is a CAR member): screen x per half second. Near things rush,
    far things crawl: the multiplane law, from the frames alone.

    >>> pole_seen_from_the_car()
    [(0.0, 30.0), (0.5, 33.3), (1.0, 37.5), (1.5, 42.9), (2.0, 50.0), (2.5, 60.0), (3.0, 75.0), (3.5, 100.0), (4.0, 150.0), (4.5, 300.0)]
    """
    tree = FrameTree(
        [Frame("car", pose=moving((0.0, 0.0, 0.0), velocity=(0.0, 0.0, car_speed)))]
    )
    out = []
    t = 0.0
    while t < pole_z / car_speed:
        s = project((lane, 0.0, pole_z), viewpoint=tree.world_pose("car", t), focal=focal)
        if s is None:
            break
        out.append((t, round(s[0], 1)))
        t += 0.5
    return out


if __name__ == "__main__":
    import doctest

    print(doctest.testmod())
