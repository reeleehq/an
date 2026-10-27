"""One world, many shots: the scene world's geometry and its lowering (ADR 0009).

A scene may declare a **world** (`SceneIR.world`): members at world positions
with a size, named viewpoints, and a travel. A shot with a **viewpoint** is a
pinhole camera onto that world; this module turns the two into what the stage
already understands — a `stage` placement per entity, and plain `set`/`tween`
actions for the streams of a travelling view — so the compiler, the shot cache
and the renderers see nothing new. A shot without a viewpoint is untouched,
and a hand `stage.at` always wins.

The projection, with the stage's axes extended by depth (`x` right, `y` DOWN,
`z` away from the viewer): a point `p` seen from a camera at `c` with basis
`(forward, right, down)` and focal length `f` (pixels) lands at

    depth = (p − c) · forward
    sx    = f · ((p − c) · right) / depth
    sy    = f · ((p − c) · down)  / depth

and an entity of world size `S` whose art is `n` pixels tall at `stage.scale`
1 is drawn at `stage.scale = (S / n) · f / depth`. That is the multiplane
camera: near things are large and rush past, far things are small and barely
move, and a close-up is the same world seen from nearer.

>>> from an.ir.schema import World, WorldMember, Viewpoint
>>> world = World(members=[
...     WorldMember(kind="prop", id="near", store="props", ref="p", at=(1.0, 0.0, 2.0), height=1.0),
...     WorldMember(kind="prop", id="far", store="props", ref="p", at=(1.0, 0.0, 20.0), height=1.0),
... ])
>>> box = (-10.0, -20.0, 10.0, 0.0)             # 20 px tall art, feet at the origin
>>> eye = resolve_viewpoint(world, Viewpoint(at=(0.0, 0.0, 0.0), focal=1000.0),
...                         extents={"near": box, "far": box}, width=1280, height=720)
>>> placed = member_placements(world, eye, extents={"near": box, "far": box}, width=1280, height=720)
>>> placed["near"].at, round(placed["near"].scale, 2)
((500.0, 0.0), 25.0)
>>> placed["far"].at, round(placed["far"].scale, 2)
((50.0, 0.0), 2.5)
"""

from __future__ import annotations

import bisect
import json
import math
import random
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Mapping, Sequence

from an.base import (
    PAINT_KEYS_OVERRIDE,
    PLANE_FACTORS_OVERRIDE,
    STREAM_OVERRIDE,
    SWAY_OVERRIDE,
)
from an.ir.compose import (
    delay,
    flatten,
    iter_actions,
    map_leaves,
    parallel,
    sequence,
    set_,
    tween,
)
from an.ir.frames import (
    FRAME_PROPERTIES,
    FrameError,
    FrameTree,
    Pose,
    Track,
    TrackEvent,
)
from an.ir.frames import look_basis as _basis
from an.ir.schema import (
    DFLT_FOV_DEG,
    DFLT_TRAVEL_MAX_ACTIONS,
    DFLT_TRAVEL_NEAR,
    DFLT_TRAVEL_TOLERANCE_PX,
    SHOT_SIZES,
    AssetRef,
    FrameSway,
    SceneIR,
    Shot,
    StagePlacement,
    Stream,
    Travel,
    VEHICLE_FRAME,
    Viewpoint,
    WORLD_FRAME,
    World,
    WorldMember,
)
from an.timing.easing import apply_easing

__all__ = [
    "Box",
    "Extents",
    "HAND_PLACEMENT_TOLERANCE_PX",
    "HAND_SCALE_TOLERANCE",
    "PERSPECTIVE_TOLERANCE",
    "Lowered",
    "Placed",
    "Projection",
    "WorldError",
    "WorldNote",
    "fit_channel",
    "focal_length",
    "ground_scale",
    "frame_poses",
    "has_world",
    "lower_world",
    "member_of",
    "member_placements",
    "pose_look",
    "resolve_viewpoint",
    "stream_instances",
    "stream_slots",
    "viewpoint_of",
]

#: A member's native extent: ``(x0, y0, x1, y1)`` in its art's pixels at
#: ``stage.scale`` 1, relative to its placement point (a character's feet).
#: ``None`` means it could not be measured (nothing drawn, or a compile that
#: failed: the lowering's note says which).
Box = tuple[float, float, float, float]
#: ``{member or stream id: Box | None}``, measured by the stage
#: (:func:`an.stage.world.member_extents`); the IR layer only reads it.
Extents = Mapping[str, "Box | None"]
Point3 = tuple[float, float, float]

#: A hand ``stage.at`` this far from the world's placement is "the same"
#: (the cut-continuity tolerance, an#394); farther is a lint warning.
HAND_PLACEMENT_TOLERANCE_PX: float = 2.0
HAND_SCALE_TOLERANCE: float = 0.02
#: A depth this small is "at the camera": nothing projects through it.
_MIN_DEPTH: float = 1e-6
#: Adaptive fitting never splits a stream's segments finer than this many frames.
_MIN_SAMPLE_FRAMES: float = 1.0
#: The finest split the fitter reaches, as a safety net for a pathological `g`.
_MAX_SAMPLE_SPLITS: int = 14
#: Two consecutive keys of one channel closer than this are one value.
_FLAT_CHANNEL_EPS: float = 1e-6
#: The key the lowering records a member's attachment under in the entity's
#: ``overrides``, for a pass that places it from its host (ADR 0009).
ATTACHED_OVERRIDE: str = "attached"


class WorldError(ValueError):
    """A world or viewpoint that cannot be resolved (an unknown member, a
    subject whose extent is unknown, a viewpoint name the world does not
    have, a travel past its budget). The IR layer raises it; `an validate`
    reports it as an error and the lowering is then skipped for that scene."""


def has_world(scene: SceneIR) -> bool:
    """Whether lowering would change anything: a world, or a shot with a viewpoint.

    >>> has_world(SceneIR())
    False
    """
    return scene.world is not None or any(
        s.viewpoint is not None for s in scene.timeline
    )


def focal_length(viewpoint: Viewpoint, *, width: float) -> float:
    """The lens in pixels: ``focal`` as given, else from ``fov`` (horizontal,
    degrees; `DFLT_FOV_DEG` when unset) and the frame width. A wider frame at
    the same field of view is a longer focal, so a world framed once frames the
    same at any resolution.

    >>> round(focal_length(Viewpoint(fov=90.0), width=1280))
    640
    >>> focal_length(Viewpoint(focal=500.0), width=1280)
    500.0
    """
    if viewpoint.focal is not None:
        return float(viewpoint.focal)
    fov = float(viewpoint.fov if viewpoint.fov is not None else DFLT_FOV_DEG)
    return float(width) / (2.0 * math.tan(math.radians(fov) / 2.0))


# --- the camera ----------------------------------------------------------------


def _dot(a: Point3, b: Point3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Point3, b: Point3) -> Point3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _sub(a: Point3, b: Point3) -> Point3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Point3, b: Point3) -> Point3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Point3, k: float) -> Point3:
    return (a[0] * k, a[1] * k, a[2] * k)


def _unit(a: Point3) -> Point3:
    n = math.sqrt(_dot(a, a))
    if n == 0.0:
        raise WorldError("a direction must not be the zero vector")
    return _mul(a, 1.0 / n)


def _angles_toward(v: Point3) -> tuple[float, float]:
    """``(yaw, pitch)`` in degrees that look along ``v``."""
    yaw = math.degrees(math.atan2(v[0], v[2]))
    pitch = math.degrees(math.atan2(v[1], math.hypot(v[0], v[2])))
    return yaw, pitch


def _angles_for_vanish(
    vanish: tuple[float, float], focal: float
) -> tuple[float, float]:
    """``(yaw, pitch)`` that put the ``+z`` direction at screen ``vanish``.

    A road's vanishing point above the frame centre (negative ``y``) means the
    camera looks slightly DOWN; a vanishing point to the right means it is
    turned slightly LEFT. Exact, not small-angle: ``sx = −f·tan(yaw)/cos(pitch)``
    and ``sy = −f·tan(pitch)``.

    >>> yaw, pitch = _angles_for_vanish((0.0, -262.0), 1372.0)
    >>> round(yaw, 3) + 0.0, round(pitch, 2)
    (0.0, 10.81)
    """
    pitch = -math.atan2(vanish[1], focal)
    yaw = -math.atan2(vanish[0] * math.cos(pitch), focal)
    return math.degrees(yaw), math.degrees(pitch)


@dataclass(frozen=True)
class Projection:
    """A resolved viewpoint: where the camera is, which way it looks, its lens.

    >>> eye = Projection(at=(0.0, 0.0, 0.0), forward=(0.0, 0.0, 1.0), right=(1.0, 0.0, 0.0), down=(0.0, 1.0, 0.0), focal=1000.0)
    >>> eye.project((2.0, -1.0, 10.0))
    (200.0, -100.0, 10.0)
    >>> eye.project((0.0, 0.0, -1.0)) is None
    True
    >>> rolled = Projection((0.0, 0.0, 0.0), *_basis(0.0, 0.0, 90.0), focal=100.0)
    >>> [round(v, 6) + 0.0 for v in rolled.project((1.0, 0.0, 10.0))]   # a point on the right: now at the bottom
    [0.0, 10.0, 10.0]
    """

    at: Point3
    forward: Point3
    right: Point3
    down: Point3
    focal: float

    def view(self, p: Point3) -> tuple[float, float, float]:
        """``p`` in camera coordinates: ``(right, down, depth)``."""
        rel = _sub(p, self.at)
        return _dot(rel, self.right), _dot(rel, self.down), _dot(rel, self.forward)

    def project(self, p: Point3) -> tuple[float, float, float] | None:
        """``(sx, sy, depth)``: screen pixels from the frame centre, and the
        depth; ``None`` for a point at or behind the camera."""
        rx, ry, depth = self.view(p)
        if depth <= _MIN_DEPTH:
            return None
        return self.focal * rx / depth, self.focal * ry / depth, depth

    def moved(self, by: Point3) -> "Projection":
        """The same camera translated by ``by`` (the vehicle moved)."""
        return Projection(
            _add(self.at, by), self.forward, self.right, self.down, self.focal
        )

    def transformed(self, pose: Pose) -> "Projection":
        """The same camera carried by a frame whose pose is ``pose``: this
        projection is in the frame's units, the result is in its parent's
        (the world's, for a frame's world pose).

        >>> eye = Projection((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 100.0)
        >>> eye.transformed(Pose(at=(0.0, 0.0, 4.0))).at
        (0.0, 0.0, 4.0)
        >>> eye.transformed(Pose()) is eye
        True
        """
        if pose.is_identity:
            return self
        return Projection(
            pose.apply(self.at),
            pose.rotate(self.forward),
            pose.rotate(self.right),
            pose.rotate(self.down),
            self.focal,
        )


#: A hand placement whose scale differs from the ground plane's by more than
#: this fraction is out of perspective (catalogue A6).
PERSPECTIVE_TOLERANCE: float = 0.15


def ground_scale(
    projection: Projection, at: tuple[float, float], *, floor_y: float, unit: float
) -> float | None:
    """The ``stage.scale`` of a member standing on the horizontal plane ``y = floor_y`` whose feet are drawn at screen ``at`` (px from the frame centre), or ``None`` at or above the horizon or when the plane is not below the eye.

    The single-view relation (catalogue A6): the ray through the pixel meets the
    floor at depth ``t * f``, and a member of ``unit`` world units per native
    pixel is drawn at ``unit * f / depth`` = ``unit * ray_y / (floor_y - eye_y)``,
    so scale grows with the pixel's distance below the horizon.

    >>> eye = Projection((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 1000.0)
    >>> round(ground_scale(eye, (0.0, 100.0), floor_y=1.0, unit=0.01), 3)    # feet 100 px below the horizon
    1.0
    >>> round(ground_scale(eye, (0.0, 200.0), floor_y=1.0, unit=0.01), 3)    # nearer: twice the size
    2.0
    >>> ground_scale(eye, (0.0, -50.0), floor_y=1.0, unit=0.01) is None      # above the horizon
    True
    """
    below = floor_y - projection.at[1]
    ray_y = (
        projection.focal * projection.forward[1]
        + at[0] * projection.right[1]
        + at[1] * projection.down[1]
    )
    if below <= _MIN_DEPTH or ray_y <= _MIN_DEPTH:
        return None
    return unit * ray_y / below


def viewpoint_of(
    world: World | None, viewpoint: str | Viewpoint | None
) -> Viewpoint | None:
    """The shot's viewpoint as a model: a name is looked up in the world.

    >>> viewpoint_of(World(viewpoints={"a": Viewpoint(focal=1.0)}), "a").focal
    1.0
    >>> viewpoint_of(None, "a")
    Traceback (most recent call last):
    ...
    an.ir.world.WorldError: shot names viewpoint 'a' but the scene has no `world`
    """
    if viewpoint is None:
        return None
    if isinstance(viewpoint, Viewpoint):
        return viewpoint
    if world is None:
        raise WorldError(
            f"shot names viewpoint {viewpoint!r} but the scene has no `world`"
        )
    try:
        return world.viewpoints[viewpoint]
    except KeyError:
        raise WorldError(
            f"unknown viewpoint {viewpoint!r}; the world names "
            f"{sorted(world.viewpoints) or 'none'}"
        ) from None


def _member(world: World | None, member_id: str, *, where: str) -> WorldMember:
    for m in world.members if world is not None else ():
        if m.id == member_id:
            return m
    raise WorldError(f"{where} names {member_id!r}, which is not a member of the world")


def _unit_scale(
    member: WorldMember | Stream, box: Box | None, *, where: str
) -> float | None:
    """World units per native pixel: the member's size over its art's extent,
    or its `units_per_px` as given. ``None`` when the member is sized by its
    art and the art could not be measured (a lint, not a crash)."""
    if member.units_per_px is not None:
        return float(member.units_per_px)
    if box is None:
        return None
    w, h = box[2] - box[0], box[3] - box[1]
    if member.height is not None:
        if h <= 0:
            raise WorldError(f"{where}: its art has no height to size by")
        return float(member.height) / h
    if member.width is not None:
        if w <= 0:
            raise WorldError(f"{where}: its art has no width to size by")
        return float(member.width) / w
    return None


def _world_box(at: Point3, box: Box, m: float) -> tuple[float, float, float, float]:
    """The member's box in world ``(x0, y0, x1, y1)`` about its position (the
    art is a billboard facing the camera, so a box is a box)."""
    return (
        at[0] + m * box[0],
        at[1] + m * box[1],
        at[0] + m * box[2],
        at[1] + m * box[3],
    )


def resolve_viewpoint(
    world: World | None,
    viewpoint: str | Viewpoint,
    *,
    extents: Extents,
    width: float,
    height: float,
    member_at: Mapping[str, Point3] | None = None,
) -> Projection:
    """The camera a viewpoint is, as a :class:`Projection`, in its own frame's
    units. ``member_at`` overrides a subject's ``at`` with where it stands in
    the VIEWPOINT's frame (a subject in another frame, at the shot's start).

    A viewpoint with ``at`` is that camera. One with a ``subject`` is computed:
    on the look direction, at the distance that fills ``fill`` of the frame
    with the subject's band (`SHOT_SIZES`), shifted so the band's centre lands
    at ``subject_at``. With several subjects the band is their union, aimed at
    their mean depth, and the distance is what the NEAREST subject needs from
    its own depth, so every subject fits the frame's height and width.

    >>> from an.ir.schema import World, WorldMember
    >>> world = World(members=[WorldMember(kind="prop", id="p", store="props", ref="p", at=(3.0, 0.0, 10.0), height=2.0)])
    >>> eye = resolve_viewpoint(world, Viewpoint(subject="p", size="full", focal=900.0),
    ...                         extents={"p": (-10.0, -40.0, 10.0, 0.0)}, width=1600, height=900)
    >>> [round(v, 3) for v in eye.at]           # 2 units tall fills 0.9 × 900 px: 2.222 away, centred on the box
    [3.0, -1.0, 7.778]
    """
    vp = viewpoint_of(world, viewpoint)
    assert vp is not None
    focal = focal_length(vp, width=width)
    yaw, pitch, roll = (float(a) for a in vp.look)
    if vp.subject is None:
        at: Point3 = tuple(float(a) for a in (vp.at or (0.0, 0.0, 0.0)))  # type: ignore[assignment]
        if vp.look_at is not None:
            yaw, pitch = _angles_toward(_sub(tuple(map(float, vp.look_at)), at))  # type: ignore[arg-type]
        elif vp.vanish is not None:
            yaw, pitch = _angles_for_vanish(tuple(map(float, vp.vanish)), focal)  # type: ignore[arg-type]
        forward, right, down = _basis(yaw, pitch, roll)
        return Projection(at, forward, right, down, focal)

    subjects = [vp.subject] if isinstance(vp.subject, str) else list(vp.subject)
    forward, right, down = _basis(yaw, pitch, roll)
    top, bottom, fill = SHOT_SIZES[vp.size or "full"]
    boxes: list[tuple[float, float, float, float]] = []
    positions: list[Point3] = []
    for sid in subjects:
        member = _member(world, sid, where="viewpoint `subject`")
        if member.at is None:
            raise WorldError(
                f"viewpoint subject {sid!r}: it is attached to "
                f"{member.attached.to!r}; frame on the host instead"  # type: ignore[union-attr]
            )
        box = extents.get(sid)
        m = _unit_scale(member, box, where=f"viewpoint subject {sid!r}")
        if box is None or m is None:
            raise WorldError(
                f"viewpoint subject {sid!r}: its extent cannot be measured, so no "
                "shot size fits it; give the viewpoint `distance` and an `at`-less "
                "`look`, or size the member by `height`/`width` with measurable art"
            )
        position: Point3 = tuple(  # type: ignore[assignment]
            map(float, (member_at or {}).get(sid, member.at))
        )
        boxes.append(_world_box(position, box, m))
        positions.append(position)
    x0 = min(b[0] for b in boxes)
    x1 = max(b[2] for b in boxes)
    bands = [(b[1] + top * (b[3] - b[1]), b[1] + bottom * (b[3] - b[1])) for b in boxes]
    y0, y1 = min(b[0] for b in bands), max(b[1] for b in bands)
    n = float(len(positions))
    centre: Point3 = (
        (x0 + x1) / 2.0,
        (y0 + y1) / 2.0,
        sum(p[2] for p in positions) / n,
    )
    if vp.distance is not None:
        distance = float(vp.distance)
    else:
        # What each subject needs from ITS depth, the union's span on each axis.
        needed_h = focal * (y1 - y0) / (fill * float(height))
        needed_w = focal * (x1 - x0) / (fill * float(width))
        distance = _MIN_DEPTH
        for p in positions:
            ahead = _dot(_sub(p, centre), forward)  # how far beyond the aim point
            distance = max(distance, max(needed_h, needed_w) - ahead)
    sx, sy = (float(a) for a in vp.subject_at)
    at = _sub(
        _sub(
            _sub(centre, _mul(forward, distance)),
            _mul(right, sx * distance / focal),
        ),
        _mul(down, sy * distance / focal),
    )
    return Projection(at, forward, right, down, focal)


# --- placing members ---------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    """Where one member lands in a framed shot."""

    id: str
    #: Screen pixels from the frame centre; ``None`` when another pass places
    #: it (attached without an offset) or it cannot be placed (see ``note``).
    at: tuple[float, float] | None
    scale: float | None
    depth: float | None
    #: Its screen box, when its extent is known.
    box: tuple[float, float, float, float] | None
    in_frame: bool
    #: ``world`` (projected), ``attached`` (from the host's placement),
    #: ``host`` (goes with the host, placed by nothing here), ``environment``.
    via: str
    #: Why it is not placed by the world, when it is not.
    note: str = ""


def _in_frame(
    at: tuple[float, float] | None,
    box: tuple[float, float, float, float] | None,
    *,
    width: float,
    height: float,
) -> bool:
    hw, hh = width / 2.0, height / 2.0
    if box is not None:
        return box[2] >= -hw and box[0] <= hw and box[3] >= -hh and box[1] <= hh
    if at is None:
        return False
    return -hw <= at[0] <= hw and -hh <= at[1] <= hh


def _screen_box(
    at: tuple[float, float], scale: float, box: Box | None
) -> tuple[float, float, float, float] | None:
    if box is None:
        return None
    return (
        at[0] + scale * box[0],
        at[1] + scale * box[1],
        at[0] + scale * box[2],
        at[1] + scale * box[3],
    )


def member_placements(
    world: World,
    projection: Projection,
    *,
    extents: Extents,
    width: float,
    height: float,
    hide: Sequence[str] = (),
    hand: Mapping[str, tuple[tuple[float, float], float]] | None = None,
    extent_problems: Mapping[str, str] | None = None,
    member_at: Mapping[str, Point3] | None = None,
    fixed: Mapping[str, "Placed"] | None = None,
) -> dict[str, Placed]:
    """Every member's placement under ``projection``: ``{id: Placed}``.

    Positioned members are projected; attached ones follow their host (an
    offset in the host's native units, times the host's scale); an
    environment is present with no placement. A member behind the camera
    is placed nowhere and is not in frame. ``hand`` is ``{id: (at, scale)}``
    for members a shot placed by hand, positioned or attached: that placement
    stands in for the derived one (its depth stays the world's), so what is
    attached to it follows the hand, as the compiler's own passes do.
    ``extent_problems`` says why an extent could not be measured, for the note.
    ``member_at`` overrides a member's ``at`` with where it stands in the
    viewpoint's frame (a member in another frame, or moved by an action);
    ``fixed`` is a placement some other pass already settled (a member in
    motion), which attached members then follow.
    """
    out: dict[str, Placed] = {}
    member_at = dict(member_at or {})
    hidden = set(hide)
    hand = dict(hand or {})
    problems = dict(extent_problems or {})

    def unmeasured(member: WorldMember) -> str:
        why = problems.get(member.id)
        return (
            f"its art could not be measured ({why}); the shot leaves it out"
            if why
            else "its extent cannot be measured; give it `units_per_px`"
        )

    def place(member: WorldMember) -> Placed:
        if member.id in out:
            return out[member.id]
        if fixed and member.id in fixed:
            out[member.id] = fixed[member.id]
            return out[member.id]
        if member.kind == "environment":
            p = Placed(
                member.id,
                None,
                None,
                None,
                None,
                member.id not in hidden,
                "environment",
            )
        elif member.attached is not None:
            host = place(
                _member(world, member.attached.to, where=f"member {member.id!r}")
            )
            visible = host.in_frame and member.id not in hidden
            if member.id in hand:
                at, scale = hand[member.id]
                box = extents.get(member.id)
                p = Placed(
                    member.id,
                    at,
                    scale,
                    host.depth,
                    _screen_box(at, scale, box),
                    visible,
                    "attached",
                )
            elif member.attached.at is None or host.at is None or host.scale is None:
                p = Placed(member.id, None, None, host.depth, None, visible, "host")
            else:
                dx, dy = (float(a) for a in member.attached.at)
                at = (host.at[0] + host.scale * dx, host.at[1] + host.scale * dy)
                scale = host.scale * float(member.attached.scale)
                box = extents.get(member.id)
                p = Placed(
                    member.id,
                    at,
                    scale,
                    host.depth,
                    _screen_box(at, scale, box),
                    visible,
                    "attached",
                )
        else:
            assert member.at is not None
            box = extents.get(member.id)
            m = _unit_scale(member, box, where=f"member {member.id!r}")
            shot = projection.project(
                tuple(map(float, member_at.get(member.id, member.at)))  # type: ignore[arg-type]
            )
            if shot is None or m is None:
                note = "behind the camera" if shot is None else unmeasured(member)
                p = Placed(member.id, None, None, None, None, False, "world", note)
            else:
                sx, sy, depth = shot
                scale = m * projection.focal / depth
                if member.id in hand:
                    (sx, sy), scale = hand[member.id]
                sbox = _screen_box((sx, sy), scale, box)
                visible = member.id not in hidden and _in_frame(
                    (sx, sy), sbox, width=width, height=height
                )
                note = (
                    ""
                    if box is not None
                    else "framed by its point: its extent is unknown"
                )
                p = Placed(
                    member.id, (sx, sy), scale, depth, sbox, visible, "world", note
                )
        out[member.id] = p
        return p

    for member in world.members:
        place(member)
    return out


# --- streams ------------------------------------------------------------------


def _jitter(seed: int, k: int, salt: str, lo: float, hi: float) -> float:
    """A seeded value in ``[lo, hi]`` for instance ``k``: the same on every
    machine and in every shot, and independent of which instances a shot
    happens to need."""
    if lo == hi:
        return lo
    return random.Random(f"{seed}:{salt}:{k}").uniform(lo, hi)


def _range(v: float | tuple[float, float]) -> tuple[float, float]:
    return (
        (float(v), float(v))
        if isinstance(v, (int, float))
        else (float(v[0]), float(v[1]))
    )


def _pitch(stream: Stream) -> tuple[float, float]:
    """``(mean spacing, jitter)`` of a stream: consecutive spacings stay in
    ``every``'s range."""
    lo, hi = _range(stream.every)
    return (lo + hi) / 2.0, (hi - lo) / 4.0


def stream_instances(
    stream: Stream, travel: Travel, *, s_min: float, s_max: float
) -> list[tuple[int, Point3]]:
    """The instances of ``stream`` whose position along the travel lies in
    ``[s_min, s_max]``: ``[(k, world position)]``, ``k`` the instance index.

    Instance ``k`` stands at ``k × mean spacing`` plus a seeded jitter that
    keeps consecutive spacings inside the stream's range, ``lane`` to the right
    of the direction of travel, at height ``y``.

    >>> from an.ir.schema import Stream, Travel
    >>> t = Travel(speed=10.0)
    >>> s = Stream(id="pole", ref="pole", height=6.0, every=12.0, lane=2.0)
    >>> stream_instances(s, t, s_min=0.0, s_max=30.0)
    [(0, (2.0, 0.0, 0.0)), (1, (2.0, 0.0, 12.0)), (2, (2.0, 0.0, 24.0))]
    """
    direction = _unit(tuple(map(float, travel.direction)))  # type: ignore[arg-type]
    right_h = _unit((direction[2], 0.0, -direction[0]))
    pitch, spread = _pitch(stream)
    lane_lo, lane_hi = _range(stream.lane)
    k0 = math.floor((s_min - spread) / pitch)
    k1 = math.ceil((s_max + spread) / pitch)
    out: list[tuple[int, Point3]] = []
    for k in range(k0, k1 + 1):
        s = k * pitch + _jitter(stream.seed, k, "s", -spread, spread)
        if not (s_min <= s <= s_max):
            continue
        lane = _jitter(stream.seed, k, "lane", lane_lo, lane_hi)
        out.append((k, _stream_point(direction, right_h, s, lane, float(stream.y))))
    return out


def stream_slots(stream: Stream, travel: Travel) -> int:
    """How many entities a stream needs by its depth range: one per instance
    that can be between ``near`` and ``far`` at once, plus one. Instance ``k``
    is drawn by slot ``k mod slots``, so an entity is reused for the next
    instance once this one has passed the camera. A shot takes the larger of
    this and what its viewpoint shows (:func:`_span_slots`, an#516), so the
    count, and the slot an instance takes, can differ between two shots;
    nothing relies on it, since each shot compiles alone.

    >>> stream_slots(Stream(id="pole", ref="pole", height=6.0, every=12.0), Travel(speed=10.0, near=0.5, far=60.0))
    6
    """
    pitch, spread = _pitch(stream)
    return (
        int(
            math.ceil(
                (float(travel.far) - float(travel.near)) / max(pitch - 2 * spread, 1e-9)
            )
        )
        + 1
    )


#: Samples along the travel per minimum spacing of a stream, and lanes across
#: a stream whose ``lane`` is a range, when measuring how much of it one
#: viewpoint shows (:func:`_span_slots`).
_SPAN_STEPS_PER_SPACING: int = 8
_SPAN_LANES: int = 17
#: How many times the scan's reach doubles when the view still sees its ends.
_SPAN_WIDENINGS: int = 4


def _stream_point(
    direction: Point3, right_h: Point3, s: float, lane: float, y: float
) -> Point3:
    """A stream's point ``s`` along the travel, ``lane`` to its right, at height ``y``."""
    return _add(_add(_mul(direction, s), _mul(right_h, lane)), (0.0, y, 0.0))


def _span_slots(
    stream: Stream,
    travel: Travel,
    ctx: "_FrameCtx",
    frame: str,
    *,
    box: Box | None,
    m: float,
    width: float,
    height: float,
) -> int:
    """How many slots a stream needs under THIS viewpoint (an#516, B3): the
    stretch of the travel over which one instance is on screen (between
    ``near`` and ``far`` and in the frame), over every lane the stream uses,
    as the camera stands when the shot opens, over the stream's minimum
    spacing, plus one. A wide lens or a yawed side window shows more of a row
    than the depth range does; :func:`stream_slots` is the depth range's
    count, and a stream takes the larger, so a view the depth range already
    covers keeps its slots (and every lowering that worked lowers the same).

    At one instant the view of a point is affine in where it stands along the
    travel, so each lane costs two views and the scan is arithmetic."""
    direction = _unit(tuple(map(float, travel.direction)))  # type: ignore[arg-type]
    right_h = _unit((direction[2], 0.0, -direction[0]))
    pitch, spread = _pitch(stream)
    spacing = max(pitch - 2 * spread, 1e-9)
    step = spacing / _SPAN_STEPS_PER_SPACING
    focal, y = ctx.projection.focal, float(stream.y)
    lo, hi = _range(stream.lane)
    lanes = (
        [lo]
        if hi == lo
        else [lo + (hi - lo) * i / (_SPAN_LANES - 1) for i in range(_SPAN_LANES)]
    )
    eye = ctx.eye_at(0.0)
    s_cam = _dot(ctx.pose(frame, 0.0).unapply(eye.at), direction)
    # In view, a point is at most `far` deep inside the frame's diagonal; the
    # lane and height add their offsets; widened while the view sees the ends.
    reach = (
        float(travel.far) * math.hypot(1.0, math.hypot(width, height) / (2.0 * focal))
        + max(abs(lo), abs(hi))
        + abs(y)
    )
    lines = []
    for lane in lanes:

        def at(d: float, lane: float = lane) -> tuple[float, float, float]:
            p = _stream_point(direction, right_h, s_cam + d, lane, y)
            return ctx.view_fn(frame, lambda t, p=p: p)(0.0)

        v0, v1 = at(0.0), at(1.0)
        lines.append((v0, tuple(b - a for a, b in zip(v0, v1))))

    def seen_within(reach: float) -> list[float]:
        n = int(math.ceil(reach / step))
        seen = []
        for a, b in lines:
            for i in range(-n, n + 1):
                d = step * i
                rx, ry, depth = (a[k] + b[k] * d for k in range(3))
                if not (travel.near <= depth <= travel.far):
                    continue
                sx, sy, scale = (
                    focal * rx / depth,
                    focal * ry / depth,
                    m * focal / depth,
                )
                box_on = _screen_box((sx, sy), scale, box)
                if _in_frame((sx, sy), box_on, width=width, height=height):
                    seen.append(d)
        return seen

    seen = seen_within(reach)
    for _ in range(_SPAN_WIDENINGS):
        if not seen or max(abs(min(seen)), abs(max(seen))) < reach - step:
            break
        reach *= 2.0
        seen = seen_within(reach)
    if not seen:
        return 1
    span = max(seen) - min(seen) + 2 * step  # a step each side of the samples
    return int(math.ceil(span / spacing)) + 1


def fit_channel(
    g: Callable[[float], float],
    a: float,
    b: float,
    *,
    tolerance: float,
    min_step: float,
) -> list[tuple[float, float, float, float, Any]]:
    """One channel's motion ``g`` on ``[a, b]`` as tweens: ``[(t0, t1, v0, v1,
    easing)]``, each a cubic-Bézier easing whose end slopes match ``g``'s (a
    Hermite fit: control points ``(1/3, d0/3, 2/3, 1 − d1/3)``), split in two
    wherever the fit strays more than ``tolerance`` from ``g`` — dense where
    the motion bends (a stream instance near the camera), one segment where
    it is straight. A segment is never shorter than ``min_step``.

    >>> segs = fit_channel(lambda t: 100.0 / (10.0 - t), 0.0, 9.0, tolerance=1.0, min_step=0.05)
    >>> segs[0][:2], segs[-1][1], round(segs[-1][3], 1)
    ((0.0, 4.5), 9.0, 100.0)
    >>> len(segs) < 8
    True
    """
    out: list[tuple[float, float, float, float, Any]] = []

    def fit(t0: float, t1: float, v0: float, v1: float) -> tuple[Any, float]:
        h, dv = t1 - t0, v1 - v0
        if abs(dv) <= _FLAT_CHANNEL_EPS:
            # Flat at the ends is not flat between them (a bounce, an orbit):
            # the deviation from the end value is the error that splits it.
            return "linear", max(
                abs(g(t0 + u * h) - v0)
                for u in (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875)
            )
        eps = h * 1e-3
        d0 = (g(t0 + eps) - v0) / eps * h / dv
        d1 = (v1 - g(t1 - eps)) / eps * h / dv
        bez = (1.0 / 3.0, d0 / 3.0, 2.0 / 3.0, 1.0 - d1 / 3.0)
        err = max(
            abs(g(t0 + u * h) - (v0 + dv * apply_easing(bez, u)))
            for u in (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875)
        )
        return bez, err

    def rec(t0: float, t1: float, v0: float, v1: float, splits: int) -> None:
        easing, err = fit(t0, t1, v0, v1)
        if err <= tolerance or t1 - t0 <= 2 * min_step or splits >= _MAX_SAMPLE_SPLITS:
            out.append((t0, t1, v0, v1, easing))
            return
        tm = (t0 + t1) / 2.0
        vm = g(tm)
        rec(t0, tm, v0, vm, splits + 1)
        rec(tm, t1, vm, v1, splits + 1)

    rec(a, b, g(a), g(b), 0)
    return out


def _on_screen_window(
    g: Callable[[float], tuple[float, float, float]],
    a: float,
    b: float,
    box: Box | None,
    *,
    width: float,
    height: float,
    step: float,
) -> tuple[float, float] | None:
    """The stretch of ``[a, b]`` during which the instance is on screen,
    scanned at ``step`` and widened by one step on each side so it enters
    and leaves at its true speed. The tail after an instance has left the
    frame is where ``1/z`` is steepest, and nothing sees it. ``None`` when it
    is never on screen.
    """

    def on_screen(t: float) -> bool:
        sx, sy, scale = g(t)
        return _in_frame(
            (sx, sy), _screen_box((sx, sy), scale, box), width=width, height=height
        )

    n = max(1, int(math.ceil((b - a) / step)))
    times = [a + (b - a) * i / n for i in range(n + 1)]
    seen = [on_screen(t) for t in times]
    if not any(seen):
        return None
    first = max(0, seen.index(True) - 1)
    last = min(n, n - seen[::-1].index(True) + 1)
    return times[first], times[last]


@dataclass(frozen=True)
class _Pass:
    """One world instance passing through one slot: its channels' segments
    on ``[t_in, t_out]`` of the shot."""

    t_in: float
    t_out: float
    channels: dict[str, list[tuple[float, float, float, float, Any]]]
    first: tuple[float, float, float]


def _pass_actions(entity_id: str, passes: list[_Pass], *, duration: float) -> list[Any]:
    """The slot entity's motion: per pass, a `set` of each channel at its first
    segment and a tween per segment (a channel's flat stretches dropped); the
    entity hidden (`alpha`) before its first pass, between passes, and after
    a pass that ends before the shot does."""
    actions: list[Any] = []
    for i, p in enumerate(passes):
        for prop, segments in p.channels.items():
            if not segments:
                continue
            t0, _, v0, _, _ = segments[0]
            actions.append(set_(entity_id, prop, v0, at=t0))
            for ta, tb, va, vb, easing in segments:
                if abs(va - vb) <= _FLAT_CHANNEL_EPS:
                    continue
                tw = tween(
                    entity_id, prop, to=vb, duration=tb - ta, from_=va, easing=easing
                )
                actions.append(sequence(delay(ta), tw) if ta > 0 else tw)
        if i == 0 and p.t_in > 0:
            actions.append(set_(entity_id, "alpha", 0.0, at=0.0))
        if p.t_in > 0:
            actions.append(set_(entity_id, "alpha", 1.0, at=p.t_in))
        if p.t_out < duration:
            actions.append(set_(entity_id, "alpha", 0.0, at=p.t_out))
    return actions


@dataclass(frozen=True)
class _FrameCtx:
    """What a framed shot knows about its frames: the tree (with the shot's
    actions on frame channels), where the shot starts in the film, and the
    viewpoint resolved IN ITS OWN FRAME's units."""

    tree: FrameTree
    film_start: float
    duration: float
    vp_frame: str
    projection: Projection

    def pose(self, frame: str, t: float) -> Pose:
        return self.tree.world_pose(frame, t, film_start=self.film_start)

    def eye_at(self, t: float) -> Projection:
        """The camera at shot time ``t``, in world coordinates."""
        return self.projection.transformed(self.pose(self.vp_frame, t))

    def view_fn(
        self, frame: str, point_at: Callable[[float], Point3]
    ) -> Callable[[float], tuple[float, float, float]]:
        """``t -> (right, down, depth)`` of a point standing in ``frame``
        (``point_at(t)`` in that frame's units) as the camera sees it. In the
        camera's own frame the point is seen directly (a constant relative
        pose costs nothing); in any other the camera and the point are carried
        to the world."""
        if frame == self.vp_frame:
            return lambda t: self.projection.view(point_at(t))

        def view(t: float) -> tuple[float, float, float]:
            return self.eye_at(t).view(self.pose(frame, t).apply(point_at(t)))

        return view


def _fit_pass(
    g: Callable[[float], tuple[float, float, float]],
    t_in: float,
    t_out: float,
    *,
    box: Box | None,
    ref_height: float,
    tol: float,
    min_step: float,
    width: float,
    height: float,
    depth: Callable[[float], float] | None = None,
) -> _Pass | None:
    """The channels of one entity's passage: its on-screen window within
    ``[t_in, t_out]`` and the Bézier fits of ``g`` on it; ``None`` when it is
    never on screen.

    ``depth`` (the instance's depth at shot time ``t``) is given for a pass
    seen in closed form (the camera translating at a constant velocity, its
    orientation fixed): every channel of ``g`` is then a projection of linear
    motion, which ``projective(k)`` draws exactly between the window's two
    ends (an#629), so each channel is ONE tween, with no fitting."""
    window = _on_screen_window(
        g, t_in, t_out, box, width=width, height=height, step=min_step
    )
    if window is None:
        return None
    t_in, t_out = window
    if depth is not None:
        ratio = depth(t_out) / depth(t_in)
        ease = "linear" if ratio == 1.0 else f"projective({ratio:.17g})"
        a, b = g(t_in), g(t_out)
        exact = {
            prop: [(t_in, t_out, a[i], b[i], ease)]
            for i, prop in enumerate(("x", "y", "scale_x"))
        }
        exact["scale_y"] = exact["scale_x"]
        return _Pass(t_in, t_out, exact, a)
    channels = {
        "x": fit_channel(
            lambda t: g(t)[0], t_in, t_out, tolerance=tol, min_step=min_step
        ),
        "y": fit_channel(
            lambda t: g(t)[1], t_in, t_out, tolerance=tol, min_step=min_step
        ),
    }
    scale_tol = tol / ref_height if ref_height > 0 else tol
    channels["scale_x"] = fit_channel(
        lambda t: g(t)[2], t_in, t_out, tolerance=scale_tol, min_step=min_step
    )
    channels["scale_y"] = channels["scale_x"]
    return _Pass(t_in, t_out, channels, g(t_in))


def _depth_window(
    depth: Callable[[float], float],
    a: float,
    b: float,
    lo: float,
    hi: float,
    *,
    step: float,
) -> tuple[float, float] | None:
    """The stretch of ``[a, b]`` during which ``lo <= depth <= hi``, scanned at
    ``step`` and widened by a step each side; ``None`` if never."""
    n = max(1, int(math.ceil((b - a) / step)))
    times = [a + (b - a) * i / n for i in range(n + 1)]
    inside = [lo <= depth(t) <= hi for t in times]
    if not any(inside):
        return None
    first = max(0, inside.index(True) - 1)
    last = min(n, n - inside[::-1].index(True) + 1)
    return times[first], times[last]


def _grid(a: float, b: float, step: float) -> list[float]:
    """The times ``[a, b]`` is scanned at: evenly spaced, at most ``step`` apart."""
    n = max(1, int(math.ceil((b - a) / step)))
    return [a + (b - a) * i / n for i in range(n + 1)]


def _depth_runs(
    times: Sequence[float],
    depths: Sequence[float],
    lo: float,
) -> list[tuple[float, float]]:
    """The stretches of ``times`` during which ``depths >= lo`` (in front of
    the camera), widened by a sample each side; runs that touch after
    widening are one.

    >>> _depth_runs([0.0, 1.0, 2.0, 3.0, 4.0], [5.0, 0.0, 0.0, 0.0, 5.0], 1.0)
    [(0.0, 1.0), (3.0, 4.0)]
    """
    n = len(times) - 1
    inside = [d >= lo for d in depths]
    runs: list[list[int]] = []
    for i, ok in enumerate(inside):
        if not ok:
            continue
        if runs and runs[-1][1] == i - 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    widened: list[list[int]] = []
    for first, last in runs:
        first, last = max(0, first - 1), min(n, last + 1)
        if widened and first <= widened[-1][1]:
            widened[-1][1] = max(widened[-1][1], last)
        else:
            widened.append([first, last])
    return [(times[f], times[l]) for f, l in widened]


#: Sample points along a shot when asking how far the camera travels.
_CAMERA_SAMPLES: int = 33


#: A stream pass's paint depth: ``(start time, depth as the shot opens, its
#: motion)``, the motion being the depth's rate per second in a closed-form
#: pass, or in a scanned one its depths on the shot's scan grid (`_grid`;
#: an#648, an#658).
_PassDepth = tuple[float, float, "float | tuple[float, ...]"]


def _travel_entities(
    travel: Travel,
    ctx: _FrameCtx,
    *,
    extents: Extents,
    extent_problems: Mapping[str, str],
    fps: float,
    width: float,
    height: float,
    skip: Sequence[str] = (),
) -> tuple[list[tuple[AssetRef, list[_PassDepth]]], list[Any], list[tuple[str, str]]]:
    """The stream instances a framed shot shows, as ``(entity, [(time, depth,
    motion)] per pass)`` (each pass's start, 0 for the first; the depth of its
    instance as the shot opens, and its depth's rate of change in a closed-form
    pass, its depths on the shot's scan grid in a scanned one: what paints it,
    an#634, an#648, an#658) and their
    actions, plus the problems found (unsized streams) as ``(stream id,
    message)``. Entities are SLOTS (`stream_slots`),
    each drawing the instances that pass through it one after another, so
    the entity count is bounded by what the view shows and never by the
    shot's length; ``skip`` names slot entities the shot already has (a lowered
    scene lowered again adds nothing).

    A stream stands in its own frame (the world by default) and the camera in
    the viewpoint's. When the camera does nothing but translate at a constant
    velocity through a stream of the world (the straight road), or nothing
    moves, the window of each instance is solved in closed form; any other
    motion (a frame that turns, accelerates or is animated, a stream in a
    moving frame) is scanned a frame at a time."""
    projection, tree = ctx.projection, ctx.tree
    film_start, duration = ctx.film_start, ctx.duration
    direction = _unit(tuple(map(float, travel.direction)))  # type: ignore[arg-type]
    reach = float(travel.far)
    min_step = _MIN_SAMPLE_FRAMES / float(fps)
    grid = _grid(0.0, duration, min_step)  # the lowering's scan grid
    tol = float(travel.tolerance_px)
    entities: list[tuple[AssetRef, list[_PassDepth]]] = []
    actions: list[Any] = []
    problems: list[tuple[str, str]] = []
    skipped = set(skip)
    budget = int(travel.max_actions)
    spent = 0  # a lower bound of the actions fitted so far (an#516, S9)
    for stream in travel.streams:
        box = extents.get(stream.id)
        m = _unit_scale(stream, box, where=f"stream {stream.id!r}")
        if m is None:
            why = extent_problems.get(stream.id)
            problems.append(
                (
                    stream.id,
                    f"its art could not be measured ({why}); the stream is left out"
                    if why
                    else "its extent cannot be measured; give the stream `units_per_px`",
                )
            )
            continue
        frame = stream.frame or WORLD_FRAME
        # The camera's motion through the stream's frame: a closed form when
        # it is a straight constant velocity (or none), else scanned.
        closed: tuple[Point3, float] | None = None
        if frame == ctx.vp_frame:
            closed = (direction, 0.0)
        elif frame == WORLD_FRAME:
            closed = tree.constant_motion(ctx.vp_frame)
        if closed is not None:
            cam_dir, speed = closed
            k_forward = _dot(cam_dir, projection.forward)
            along = speed if cam_dir == direction else speed * _dot(cam_dir, direction)
            s_cam0 = _dot(projection.at, direction)
            s_lo = s_cam0 + along * film_start - reach
            s_hi = s_cam0 + along * (film_start + duration) + reach
        else:
            s_cam = []
            for i in range(_CAMERA_SAMPLES + 1):
                t = duration * i / _CAMERA_SAMPLES
                cam = ctx.pose(frame, t).unapply(ctx.eye_at(t).at)
                s_cam.append(_dot(cam, direction))
            s_lo, s_hi = min(s_cam) - reach, max(s_cam) + reach
        ref_height = (box[3] - box[1]) if box is not None else 1.0
        slots = max(
            stream_slots(stream, travel),
            _span_slots(
                stream, travel, ctx, frame, box=box, m=m, width=width, height=height
            ),
        )
        passes: dict[
            int, list[tuple[int, _Pass, tuple[float, float | tuple[float, ...]]]]
        ] = {}
        for k, p in stream_instances(stream, travel, s_min=s_lo, s_max=s_hi):
            view = ctx.view_fn(frame, lambda t, p=p: p)
            if closed is not None:
                at_start = projection.moved(_mul(cam_dir, speed * film_start))
                depth0 = _dot(_sub(p, at_start.at), projection.forward)
                slope = rate = -speed * k_forward
                if abs(slope) < _MIN_DEPTH:
                    if not (travel.near <= depth0 <= travel.far):
                        continue
                    t_in, t_out = 0.0, duration
                else:
                    ta, tb = (
                        (travel.near - depth0) / slope,
                        (travel.far - depth0) / slope,
                    )
                    t_in, t_out = max(0.0, min(ta, tb)), min(duration, max(ta, tb))
                    if t_out <= t_in:
                        continue
            else:
                scanned = _depth_window(
                    lambda t: view(t)[2],
                    0.0,
                    duration,
                    float(travel.near),
                    float(travel.far),
                    step=min_step,
                )
                if scanned is None:
                    continue
                t_in, t_out = scanned
                rate = tuple(view(t)[2] for t in grid)
                depth0 = rate[0]

            def g(t: float, view: Callable = view) -> tuple[float, float, float]:
                rx, ry, depth = view(t)
                depth = max(
                    depth, float(travel.near)
                )  # past the camera: hold at the near plane
                return (
                    projection.focal * rx / depth,
                    projection.focal * ry / depth,
                    m * projection.focal / depth,
                )

            fitted = _fit_pass(
                g,
                t_in,
                t_out,
                box=box,
                ref_height=ref_height,
                tol=tol,
                min_step=min_step,
                width=width,
                height=height,
                # closed form: the exact one-tween pass (an#629)
                depth=(lambda t, view=view: view(t)[2]) if closed is not None else None,
            )
            if fitted is None:
                continue  # never on screen during this shot
            passes.setdefault(k % slots, []).append((k, fitted, (depth0, rate)))
            spent += _pass_cost(fitted, duration=duration)
            if spent > budget:  # stop fitting: the rest can only add
                raise WorldError(
                    _over_budget(
                        f"at least {spent} actions, already", travel, duration=duration
                    )
                )
        for slot in sorted(passes):
            entity_id = f"{stream.id}_{slot}"
            if entity_id in skipped:
                continue
            ordered = sorted(passes[slot], key=lambda item: item[1].t_in)
            for (_, prev, _), (_, nxt, _) in zip(ordered, ordered[1:]):
                if nxt.t_in < prev.t_out:
                    # Two instances on screen at once in one slot: the slots are
                    # sized from what the view shows as the shot opens (an#516),
                    # and a camera that turns during the shot can show more.
                    # Loud, not a teleport.
                    raise WorldError(
                        f"stream {stream.id!r}: two instances are on screen at once "
                        f"in one slot ({entity_id}, {prev.t_out:.2f}s and {nxt.t_in:.2f}s) "
                        "under this viewpoint; the slots are sized by what the view shows "
                        "as the shot opens, and a camera that turns during it can show "
                        "more. Narrow `fov`, bring `far` in, or space the stream out (`every`)."
                    )
            first = ordered[0][1]
            entities.append(
                (
                    AssetRef(
                        kind=stream.kind,
                        id=entity_id,
                        store=stream.store,
                        ref=stream.ref,
                        overrides={STREAM_OVERRIDE: stream.id},
                        stage=StagePlacement(
                            at=(first.first[0], first.first[1]),
                            scale=first.first[2],
                            after=stream.after,
                        ),
                    ),
                    [
                        (p.t_in if i else 0.0, *depth)
                        for i, (_, p, depth) in enumerate(ordered)
                    ],
                )
            )
            actions.extend(
                _pass_actions(entity_id, [p for _, p, _ in ordered], duration=duration)
            )
    if len(actions) > budget:
        raise WorldError(
            _over_budget(
                f"{len(actions)} actions for {len(entities)} stream entities, which is",
                travel,
                duration=duration,
            )
        )
    return entities, actions, problems


#: Where a stream slot's paint key's tiebreak starts (``(1.0, -depth, tie)``):
#: past every listed entity's index and every added member's ``1000 + i``.
SLOT_TIEBREAK: float = 10_000.0


def _marked(entity: AssetRef, key: str, value: Any) -> AssetRef:
    """``entity`` with the core's ``key`` set in its overrides."""
    return entity.model_copy(
        update={"overrides": {**(entity.overrides or {}), key: value}}
    )


def _is_slot(entity: AssetRef) -> bool:
    return STREAM_OVERRIDE in (entity.overrides or {})


def _slot_paint_keys(
    slots: Sequence[tuple[AssetRef, Sequence[_PassDepth]]],
) -> dict[str, list[tuple[float, tuple[float, float, float]]]]:
    """Each stream slot's paint key from each pass on: ``(1.0, -depth,
    tiebreak)`` at its instance's depth as the shot opens (a key sorting
    farther first). Every instance of a closed-form stream moves alike, so
    that depth orders them for the whole pass (an#634).

    >>> e = AssetRef(kind="prop", id="p0", store="props", ref="p")
    >>> _slot_paint_keys([(e, [(0.0, 10.0, -4.0), (2.0, 30.0, -4.0)])])
    {'p0': [(0.0, (1.0, -10.0, 10000.0)), (2.0, (1.0, -30.0, 10000.0))]}
    """
    return {
        entity.id: [
            (start, (1.0, -depth0, SLOT_TIEBREAK + si)) for start, depth0, _ in passes
        ]
        for si, (entity, passes) in enumerate(slots)
    }


_PaintKey = tuple[float, float, float]
_PaintKeys = dict[str, list[tuple[float, _PaintKey]]]

#: How far (relative to its depth) a moving member's sampled depths may stray
#: from a straight line at the streams' rate and still move like them, and how
#: far two rates may differ and still be one (float noise only; an#658).
_ALIKE_TOLERANCE: float = 1e-9

#: Seconds: two times the paint keys change that are closer than this are one
#: (float noise, as a crossing computed at 0.9999999999999999 beside a pass
#: beginning at 1.0; an#658).
_BREAKPOINT_TOLERANCE: float = 1e-9


def _rest_paint_keys(
    rest: Mapping[str, _PaintKey],
    passes: Sequence[Sequence[_PassDepth]],
    *,
    duration: float,
) -> _PaintKeys:
    """The paint keys of the members at rest relative to the camera
    (``rest``: ``{id: (1.0, -depth, tiebreak)}``) when what moves alike (the
    closed-form ``passes``, one list per slot or moving member) passes them
    (an#648). The slots keep their depth as the shot opens; a member at depth
    ``d`` is then, in those terms, at ``d - rate * t``, so it is keyed again
    at each time a closed-form pass crosses its depth, for each stretch at its
    middle (never on a crossing). Anything moving like the streams (a member
    standing in the world) keeps its opening key and stays right. Only when
    every pass shares one nonzero rate; otherwise ``{}`` (the general form is
    :func:`_crossing_paint_keys`'s, an#658).

    >>> keys = _rest_paint_keys({"lamp": (1.0, -6.0, 3.0)}, [[(0.0, 10.0, -4.0)]], duration=2.0)
    >>> [(t, -k[1]) for t, k in keys["lamp"]]
    [(0.0, 8.0), (1.0, 12.0)]
    """
    rates = [rate for slot in passes for _, _, rate in slot if rate]
    if not rates or not rest:
        return {}
    rate = rates[0]
    if not all(
        math.isclose(r, rate, rel_tol=_ALIKE_TOLERANCE, abs_tol=_ALIKE_TOLERANCE)
        for r in rates
    ):
        return {}
    crossings: set[float] = set()
    for slot in passes:
        for i, (start, depth0, r) in enumerate(slot):
            end = slot[i + 1][0] if i + 1 < len(slot) else duration
            for _, minus_depth, _ in rest.values():
                t = (-minus_depth - depth0) / rate
                if r and start < t < end:
                    crossings.add(t)
    if not crossings:
        return {}
    times = sorted({0.0} | crossings)
    middles = [(a + b) / 2.0 for a, b in zip(times, [*times[1:], duration])]
    return {
        eid: [
            (t, (1.0, minus_depth + rate * mid, tie)) for t, mid in zip(times, middles)
        ]
        for eid, (_, minus_depth, tie) in rest.items()
    }


@dataclass(frozen=True)
class _DepthPiece:
    """One stretch ``[lo, hi]`` of an entity's depth over a shot, linear
    between its knots ``(times, depths)`` (an#658): a closed-form pass is one
    line, a scanned one or a member in motion its samples on the scan grid.

    >>> _DepthPiece(0.0, 2.0, (0.0, 2.0), (10.0, 6.0)).at(0.5)
    9.0
    """

    lo: float
    hi: float
    times: tuple[float, ...]
    depths: tuple[float, ...]

    def at(self, t: float) -> float:
        """The depth at ``t``, linear between knots, held past the ends."""
        times, depths = self.times, self.depths
        i = bisect.bisect_right(times, t)
        if i <= 0:
            return depths[0]
        if i >= len(times):
            return depths[-1]
        t0, t1 = times[i - 1], times[i]
        u = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
        return depths[i - 1] + (depths[i] - depths[i - 1]) * u


def _piece(
    lo: float,
    hi: float,
    motion: float | Sequence[float],
    *,
    depth0: float,
    grid: Sequence[float],
) -> _DepthPiece:
    """The depth over ``[lo, hi]`` of a closed-form motion (``depth0 + motion
    * t``) or of depths sampled on ``grid``, as one :class:`_DepthPiece`.

    >>> _piece(1.0, 2.0, -4.0, depth0=10.0, grid=()).depths
    (6.0, 2.0)
    >>> _piece(0.5, 1.5, (9.0, 8.0, 6.0), depth0=9.0, grid=(0.0, 1.0, 2.0)).depths
    (8.5, 8.0, 7.0)
    """
    if isinstance(motion, (int, float)):
        ends = (depth0 + motion * lo, depth0 + motion * hi)
        return _DepthPiece(lo, hi, (lo, hi), ends)
    whole = _DepthPiece(grid[0], grid[-1], tuple(grid), tuple(motion))
    inside = [t for t in grid if lo < t < hi]
    times = (lo, *inside, hi)
    return _DepthPiece(lo, hi, times, tuple(whole.at(t) for t in times))


def _slot_pieces(
    passes: Sequence[_PassDepth], *, duration: float, grid: Sequence[float]
) -> list[_DepthPiece]:
    """A slot's depth over the shot, one piece per pass from its start to the
    next one's (the slot draws that instance until then)."""
    ends = [start for start, _, _ in passes[1:]] + [duration]
    return [
        _piece(start, end, motion, depth0=depth0, grid=grid)
        for (start, depth0, motion), end in zip(passes, ends)
    ]


def _piece_crossings(a: _DepthPiece, b: _DepthPiece, *, near: float) -> list[float]:
    """The times ``a`` and ``b`` swap depth where both are defined, exact
    between knots, each being linear there: where one crosses the other, comes
    level with it, or leaves a tie with it (a tie that then splits is keyed
    from the split, not by the tiebreak). A crossing behind the camera counts
    too (two receding entities emerge in front in the swapped order); only
    when both stay nearer than ``near`` over the whole span they share, so
    neither is ever seen, are there none.

    >>> line = _DepthPiece(0.0, 4.0, (0.0, 4.0), (10.0, 2.0))
    >>> _piece_crossings(line, _DepthPiece(0.0, 4.0, (0.0, 4.0), (5.0, 5.0)), near=0.5)
    [2.5]
    """
    lo, hi = max(a.lo, b.lo), min(a.hi, b.hi)
    if hi <= lo:
        return []
    if min(a.depths) > max(b.depths) or min(b.depths) > max(a.depths):
        return []
    times = sorted({lo, hi, *(t for t in (*a.times, *b.times) if lo < t < hi)})
    pairs = [(a.at(t), b.at(t)) for t in times]
    if all(da < near and db < near for da, db in pairs):
        return []
    diffs = [da - db for da, db in pairs]
    out: list[float] = []
    for (t0, d0), (t1, d1) in zip(zip(times, diffs), zip(times[1:], diffs[1:])):
        if d0 * d1 < 0.0:
            out.append(t0 + (t1 - t0) * d0 / (d0 - d1))
        elif d1 == 0.0 and d0 != 0.0 and t1 < hi:  # comes level
            out.append(t1)
        elif d0 == 0.0 and d1 != 0.0 and t0 > lo:  # a tie splits
            out.append(t0)
    return out


def _depth_paint_keys(
    curves: Mapping[str, tuple[Sequence[_DepthPiece], float]],
    *,
    duration: float,
    near: float,
) -> _PaintKeys:
    """Every entity of ``curves`` (``{id: (its depth's pieces, tiebreak)}``,
    the pieces tiling the shot) keyed, in each stretch between two
    consecutive times any two of them swap depth or a piece begins, at its
    depth at the stretch's middle (an#658): within a stretch no two swap, so
    keys read at one instant order them for all of it. Times closer than
    :data:`_BREAKPOINT_TOLERANCE` are one. A key repeats only when it changes
    (a member at rest has one).

    >>> rest = [_DepthPiece(0.0, 4.0, (0.0, 4.0), (5.0, 5.0))]
    >>> pole = [_DepthPiece(0.0, 4.0, (0.0, 4.0), (10.0, 2.0))]
    >>> keys = _depth_paint_keys({"lamp": (rest, 0.0), "pole": (pole, 1.0)}, duration=4.0, near=0.5)
    >>> [(t, -k[1]) for t, k in keys["pole"]], [(t, -k[1]) for t, k in keys["lamp"]]
    ([(0.0, 7.5), (2.5, 3.5)], [(0.0, 5.0)])
    """
    ids = sorted(curves)
    times = {0.0}
    for i, a in enumerate(ids):
        times.update(p.lo for p in curves[a][0] if 0.0 < p.lo < duration)
        for b in ids[i + 1 :]:
            for pa in curves[a][0]:
                for pb in curves[b][0]:
                    times.update(_piece_crossings(pa, pb, near=near))
    starts = [0.0]
    for t in sorted(times):
        apart = t - starts[-1] > _BREAKPOINT_TOLERANCE
        if apart and t < duration - _BREAKPOINT_TOLERANCE:
            starts.append(t)
    middles = [(t0 + t1) / 2.0 for t0, t1 in zip(starts, [*starts[1:], duration])]
    out: _PaintKeys = {}
    for eid in ids:
        pieces, tie = curves[eid]
        los = [p.lo for p in pieces]
        keys: list[tuple[float, _PaintKey]] = []
        for t, mid in zip(starts, middles):
            piece = pieces[max(0, bisect.bisect_right(los, mid) - 1)]
            key = (1.0, -piece.at(mid), tie)
            if not keys or keys[-1][1] != key:
                keys.append((t, key))
        out[eid] = keys
    return out


def _alike_rate(depths: Sequence[float], *, grid: Sequence[float]) -> float | None:
    """The rate of ``depths`` (sampled on ``grid``) when they lie on one line,
    else ``None`` (an#658).

    >>> _alike_rate([8.0, 6.0, 4.0], grid=[0.0, 0.5, 1.0]), _alike_rate([8.0, 7.0, 4.0], grid=[0.0, 0.5, 1.0])
    (-4.0, None)
    """
    if len(grid) < 2:
        return 0.0
    rate = (depths[-1] - depths[0]) / (grid[-1] - grid[0])
    scale = _ALIKE_TOLERANCE * (1.0 + max(abs(d) for d in depths))
    if all(abs(d - depths[0] - rate * t) <= scale for d, t in zip(depths, grid)):
        return rate
    return None


def _crossing_paint_keys(
    rest: Mapping[str, _PaintKey],
    slots: Sequence[tuple[AssetRef, Sequence[_PassDepth]]],
    movers: Mapping[str, tuple[Sequence[float], _PaintKey]],
    *,
    duration: float,
    grid: Sequence[float],
    near: float,
) -> _PaintKeys:
    """The paint keys of the depth-ordered entities where their order changes
    within the shot (an#648, an#658), on top of :func:`_slot_paint_keys`: the
    members at rest relative to the camera (``rest``: ``{id: key}``), the
    stream ``slots`` and the members in motion (``movers``: ``{id: (depths on
    grid, key)}``).

    When everything that moves moves alike (closed-form passes and movers on
    one line at one rate), the slots and movers keep their opening keys and
    only the members at rest are keyed again, at the crossings
    (:func:`_rest_paint_keys`). A mover's opening key is its depth at 0, as a
    slot's is, even when it enters view later (its key as placed is its depth
    as it enters view, which the others' keys are not in terms of). Otherwise (streams at different rates, a rate
    0 among them, a scanned pass, a member walking or turning with the camera)
    every one of them is keyed at its depth in each stretch between swaps
    (:func:`_depth_paint_keys`)."""
    motions = [m for _, passes in slots for _, _, m in passes]
    mover_rates = {mid: _alike_rate(d, grid=grid) for mid, (d, _) in movers.items()}
    rates = [*motions, *mover_rates.values()]
    closed = [r for r in rates if isinstance(r, (int, float))]
    if len(closed) == len(rates) and all(
        math.isclose(r, closed[0], rel_tol=_ALIKE_TOLERANCE, abs_tol=_ALIKE_TOLERANCE)
        for r in closed
    ):
        opening: _PaintKeys = {
            mid: [(0.0, (1.0, -d[0], k[2]))] for mid, (d, k) in movers.items()
        }
        return {
            **opening,
            **_rest_paint_keys(
                rest,
                [passes for _, passes in slots]
                + [[(0.0, movers[mid][0][0], r)] for mid, r in mover_rates.items()],
                duration=duration,
            ),
        }
    whole = (0.0, duration)
    curves: dict[str, tuple[Sequence[_DepthPiece], float]] = {
        eid: ([_DepthPiece(*whole, whole, (-k[1], -k[1]))], k[2])
        for eid, k in rest.items()
    }
    curves.update(
        (mid, ([_DepthPiece(*whole, tuple(grid), tuple(d))], k[2]))
        for mid, (d, k) in movers.items()
    )
    curves.update(
        (e.id, (_slot_pieces(passes, duration=duration, grid=grid), SLOT_TIEBREAK + si))
        for si, (e, passes) in enumerate(slots)
    )
    return _depth_paint_keys(curves, duration=duration, near=near)


def _with_paint_keys(
    ordered: list[tuple[tuple[float, float, float], AssetRef, int | None]],
    pass_keys: Mapping[str, Sequence[tuple[float, tuple[float, float, float]]]],
    *,
    entity_ids: Collection[str],
    members: Collection[str],
) -> list[tuple[tuple[float, float, float], AssetRef, int | None]]:
    """``ordered`` with each entity's paint key from each time on recorded
    under :data:`an.base.PAINT_KEYS_OVERRIDE` (``[[time, key]]``, the first at
    0; a key sorts farther first) when a stream slot is reused (an#634): the
    compiler orders each run of keyed siblings by them, frame by frame. An
    entity the author placed after another entity (``stage.after`` naming one
    of ``entity_ids``) rides that entity's keys, just behind it, so it stays
    painted right after it as it moves (an#648), when it is a world member
    (``members``: the only entities a shot reorders); otherwise it carries
    none, and keeps its built place. Its keys are its host's with a suffix,
    so the compiler can tell whether its host is built beside it."""
    if not any(len(ks) > 1 for ks in pass_keys.values()):
        return ordered
    after = {
        e.id: e.stage.after if e.stage is not None else None for _, e, _ in ordered
    }
    hosts = {eid: a for eid, a in after.items() if a in entity_ids}

    keys = {
        e.id: [[t, list(k)] for t, k in pass_keys.get(e.id) or [(0.0, key)]]
        for key, e, _ in ordered
        if e.id not in hosts
    }
    riding = True
    while riding:  # a chain of `after`s rides from its first keyed entity
        riding = False
        for n, (eid, host) in enumerate(sorted(hosts.items())):
            if host in keys and eid in members:
                keys[eid] = [[t, [*k, 1, n]] for t, k in keys[host]]
                del hosts[eid]
                riding = True
    return [
        (
            key,
            e.model_copy(
                update={
                    "overrides": {
                        **(e.overrides or {}),
                        PAINT_KEYS_OVERRIDE: keys[e.id],
                    }
                }
            )
            if e.id in keys
            else e,
            j,
        )
        for key, e, j in ordered
    ]


def _pass_cost(p: _Pass, *, duration: float) -> int:
    """The actions one pass adds to its slot, not counting the hide before a
    slot's first pass (one per slot): a lower bound, so a running total of
    them refuses only what the full count would."""
    return len(_pass_actions("_", [p], duration=duration)) - (1 if p.t_in > 0 else 0)


def _over_budget(spent: str, travel: Travel, *, duration: float) -> str:
    """The refusal of a travel past its ``max_actions``, with its levers."""
    return (
        f"this shot's travel lowers to {spent} past the travel's `max_actions` "
        f"({int(travel.max_actions)}). Space the streams further apart (`every`), "
        f"bring `far` in ({travel.far:g}), raise `tolerance_px` "
        f"({travel.tolerance_px:g}), cut the shot ({duration:g} s), or raise "
        "`max_actions` knowingly."
    )


# --- frames: actions on frame channels, members in motion ------------------------

_AT_CHANNELS: dict[str, int] = {"at_x": 0, "at_y": 1, "at_z": 2}


@dataclass(frozen=True)
class _Split:
    """A shot's actions with the ones that move frames and members through the
    world taken out: those are lowered to screen channels, not played."""

    actions: list[Any]
    frame_tracks: dict[str, dict[str, Track]]
    member_tracks: dict[str, dict[str, Track]]
    #: ``{member: [(shot time, ReframeAction), ...]}``, in time order.
    reframes: dict[str, list[tuple[float, Any]]] = field(default_factory=dict)


def _split_frame_actions(
    shot: Shot,
    *,
    default_easing: Any,
    frames: Collection[str],
    members: Collection[str],
) -> _Split:
    """Take ``<frame>:at_x|at_y|at_z|yaw|pitch|roll`` and ``<member>:at_x|at_y|at_z``
    out of the shot's actions, as tracks in shot time. A shot with none keeps
    its actions as they are; one with some has them replaced by delays of
    their own length, so everything else keeps its time (the leaves' own times
    are read with the default extent of a duration-less ``play``)."""

    def kind_of_target(a: Any) -> str | None:
        if getattr(a, "kind", None) == "reframe":
            return "reframe"
        if getattr(a, "kind", None) not in ("set", "tween"):
            return None
        if a.target in frames and a.property in FRAME_PROPERTIES:
            return "frame"
        if a.target in members and a.property in _AT_CHANNELS:
            return "member"
        return None

    if not any(kind_of_target(a) for top in shot.actions for a in iter_actions(top)):
        return _Split(list(shot.actions), {}, {})
    events: dict[tuple[str, str, str], list[TrackEvent]] = {}
    reframes: dict[str, list[tuple[float, Any]]] = {}
    for f in flatten(parallel(*shot.actions)):
        a = f.action
        which = kind_of_target(a)
        if which is None:
            continue
        if which == "reframe":
            if a.target not in members:
                raise WorldError(
                    f"shot {shot.id!r}: reframe of {a.target!r}, which is not a positioned "
                    f"member of the world; the members are {sorted(members)}."
                )
            reframes.setdefault(a.target, []).append((f.start, a))
            continue
        where = f"shot {shot.id!r}: {a.target}:{a.property}"
        try:
            if a.kind == "set":
                ev = TrackEvent(f.start, f.start, to=float(a.value))
            else:
                ev = TrackEvent(
                    f.start,
                    f.end,
                    to=float(a.to_value),
                    from_=None if a.from_value is None else float(a.from_value),
                    easing=a.resolved_easing(default_easing),
                )
        except (TypeError, ValueError):
            raise WorldError(
                f"{where} needs numbers, not {a.value if a.kind == 'set' else a.to_value!r}"
            ) from None
        events.setdefault((which, a.target, a.property), []).append(ev)

    def lowered_away(a: Any) -> Any:
        """A lowered leaf stands in as a delay of its own length, so what
        follows it in a sequence keeps its time and the tree its shape."""
        if kind_of_target(a) is None:
            return a
        return delay(0.0 if a.kind in ("set", "reframe") else a.duration)

    kept = [map_leaves(top, lowered_away) for top in shot.actions]
    tracks: dict[str, dict[str, dict[str, Track]]] = {"frame": {}, "member": {}}
    for (which, target, prop), evs in events.items():
        tracks[which].setdefault(target, {})[prop] = Track(evs)
    return _Split(
        kept,
        tracks["frame"],
        tracks["member"],
        {k: sorted(v, key=lambda x: x[0]) for k, v in reframes.items()},
    )


def _member_point(
    member: WorldMember, tracks: Mapping[str, Track] | None, t: float
) -> Point3:
    """Where a positioned member stands at shot time ``t`` in its own frame's
    units: its ``at``, with each channel an action animates replaced."""
    p = list(member.at)  # type: ignore[arg-type]
    for prop, i in _AT_CHANNELS.items():
        track = (tracks or {}).get(prop)
        if track is not None:
            p[i] = track.value(t, float(p[i]))
    return (float(p[0]), float(p[1]), float(p[2]))


def _tracks_vary(tracks: Mapping[str, Track] | None, duration: float) -> bool:
    """Whether any of the tracks gives different values within the shot."""
    for track in (tracks or {}).values():
        times = {0.0, duration, *(b for b in track.breaks if 0.0 <= b <= duration)}
        for base in (0.0, 1.0):
            if len({round(track.value(t, base), 9) for t in times}) > 1:
                return True
    return False


#: Step of the central differences a velocity is read with (s).
_VELOCITY_DT: float = 1e-3
#: A frame carrying a member faster than this (world units per second) is
#: moving, for the lint that asks a ``reframe`` out of it to say what it inherits.
_MOVING_EPS: float = 1e-6


@dataclass(frozen=True)
class _Leg:
    """One stretch of a member's course: from ``start`` (shot time) on, either
    standing in ``frame`` at ``base`` (its own ``tracks`` replacing channels),
    or, with ``flight``, a projectile in the world from ``(p0, v0, g)``."""

    start: float
    frame: str
    base: Point3
    tracks: Mapping[str, Track]
    flight: tuple[Point3, Point3, float] | None = None


@dataclass(frozen=True)
class _Change:
    """What one ``reframe`` did, for the lints: the world point just before
    and just after it, and the velocity the old frame carried the member with."""

    at: float
    action: Any
    old_frame: str
    before: Point3
    after: Point3
    carried: Point3


class _Course:
    """A member that changes frame: its world position as a function of shot
    time, built leg by leg from its ``reframe`` actions (an#502).

    >>> from an.ir.schema import Frame, FrameMoving, WorldMember
    >>> from an.ir.reframe import reframe
    >>> tree = FrameTree({"car": Frame(moving=FrameMoving(speed=20.0))})
    >>> bottle = WorldMember(kind="prop", id="bottle", store="props", ref="b", at=(0.6, -0.3, 0.5), height=0.3, frame="car")
    >>> acts = [(2.0, reframe("bottle", to="world", motion="ballistic", velocity=(3.0, -2.0, 0.0)))]
    >>> course = _Course(bottle, "car", tree, acts, {}, film_start=0.0)
    >>> [round(v, 2) for v in course.world_at(2.5)]
    [2.1, -0.07, 50.5]
    >>> [round(v, 2) for v in tree.world_pose("car", 2.5).at]       # abreast: 0.5 m ahead of the car
    [0.0, 0.0, 50.0]
    """

    def __init__(
        self,
        member: WorldMember,
        frame: str,
        tree: FrameTree,
        reframes: Sequence[tuple[float, Any]],
        tracks: Mapping[str, Track],
        *,
        film_start: float,
    ):
        self.tree, self.film_start = tree, film_start
        self.changes: list[_Change] = []
        cuts = [t for t, _ in reframes]
        parts = [
            self._slice(tracks, lo, hi)
            for lo, hi in zip([-math.inf, *cuts], [*cuts, math.inf])
        ]
        base = (float(member.at[0]), float(member.at[1]), float(member.at[2]))  # type: ignore[index]
        self.legs: list[_Leg] = [_Leg(-math.inf, frame, base, parts[0])]
        for (t, a), leg_tracks in zip(reframes, parts[1:]):
            self._reframe(t, a, leg_tracks)

    @staticmethod
    def _slice(tracks: Mapping[str, Track], lo: float, hi: float) -> dict[str, Track]:
        """The events of each track that start in ``[lo, hi)``."""
        out = {}
        for prop, track in tracks.items():
            evs = [e for e in track.events if lo <= e.start < hi]
            if evs:
                out[prop] = Track(evs)
        return out

    def _leg_at(self, t: float, legs: Sequence[_Leg] | None = None) -> _Leg:
        legs = legs or self.legs
        return [leg for leg in legs if leg.start <= t][-1]

    def _world(self, leg: _Leg, t: float) -> Point3:
        if leg.flight is not None:
            p0, v0, g = leg.flight
            dt = t - leg.start
            return (
                p0[0] + v0[0] * dt,
                p0[1] + v0[1] * dt + 0.5 * g * dt * dt,
                p0[2] + v0[2] * dt,
            )
        p = list(leg.base)
        for prop, i in _AT_CHANNELS.items():
            track = leg.tracks.get(prop)
            if track is not None:
                p[i] = track.value(t, p[i])
        return self.tree.world_pose(leg.frame, t, film_start=self.film_start).apply(
            (p[0], p[1], p[2])
        )

    def world_at(self, t: float) -> Point3:
        """The member's world position at shot time ``t``."""
        return self._world(self._leg_at(t), t)

    def _velocity(self, f: Callable[[float], Point3], t: float) -> Point3:
        h = _VELOCITY_DT
        a, b = f(t - h), f(t + h)
        return tuple((bi - ai) / (2 * h) for ai, bi in zip(a, b))  # type: ignore[return-value]

    def _reframe(self, t: float, a: Any, tracks: Mapping[str, Track]) -> None:
        old = self.legs[-1]
        tree = self.tree
        where = f"reframe of {a.target!r} at {t:g}"
        if a.to not in tree:
            raise WorldError(
                f"{where}: `to: {a.to}` is not a frame; the frames are "
                f"{sorted({WORLD_FRAME, *tree.frames})}."
            )
        if t < 0:
            raise WorldError(f"{where}: `at` is before the shot opens.")
        before = self._world(old, t)
        pose_old = tree.world_pose(old.frame, t, film_start=self.film_start)
        pose_new = tree.world_pose(a.to, t, film_start=self.film_start)
        local_old = pose_old.unapply(before)
        if a.snap is not None:
            sockets = tree.frames[a.to].sockets if a.to in tree.frames else {}
            if a.snap not in sockets:
                raise WorldError(
                    f"{where}: frame {a.to!r} has no socket {a.snap!r}; its sockets are "
                    f"{sorted(sockets)}."
                )
            base = tuple(float(v) for v in sockets[a.snap])
        elif a.keep == "local":
            base = local_old  # the numbers stay; the picture may jump
        else:
            base = pose_new.unapply(before)  # the picture stays; the numbers change
        base = (float(base[0]), float(base[1]), float(base[2]))
        after_leg = _Leg(t, a.to, base, tracks)
        # The velocity the old frame carried the member with (a point fixed in
        # it), and what the member does of its own on top of that.
        carried = self._velocity(
            lambda u: tree.world_pose(old.frame, u, film_start=self.film_start).apply(
                local_old
            ),
            t,
        )
        total = self._velocity(lambda u: self._world(old, u), t)
        own = tuple(x - c for x, c in zip(total, carried))
        thrown = pose_old.rotate(tuple(float(v) for v in a.velocity))  # type: ignore[arg-type]
        if a.motion == "ballistic":
            keep_frame = 0.0 if a.inherit == "none" else 1.0
            v0 = tuple(
                o + th + keep_frame * c for o, th, c in zip(own, thrown, carried)
            )
            after_leg = _Leg(
                t,
                WORLD_FRAME,
                base,
                tracks,
                flight=(pose_new.apply(base), v0, float(a.gravity)),  # type: ignore[arg-type]
            )
        self.legs.append(after_leg)
        self.changes.append(
            _Change(t, a, old.frame, before, self._world(after_leg, t), carried)  # type: ignore[arg-type]
        )


def _reframe_notes(
    change: _Change,
    member: str,
    ctx: _FrameCtx,
    *,
    near: float,
    note: Callable[[str, str, str, str], None],
) -> None:
    """The lints of one ``reframe`` (an#502): a ``keep: local`` that makes the
    picture jump (``reframe_jump``, warning, with the jump in pixels, over the
    cut-continuity tolerance, or in size), and a ballistic reframe out of a
    moving frame that does not say what the member inherits (``reframe_inherit``, info)."""
    a = change.action
    eye = ctx.eye_at(change.at)
    focal = ctx.projection.focal
    seen = [eye.view(p) for p in (change.before, change.after)]
    if a.snap is None and any(v[2] > near for v in seen):
        # One end behind the camera is read at the near plane: a jump out of
        # (or into) the picture is still a jump.
        (x0, y0, d0), (x1, y1, d1) = ((x, y, max(d, near)) for x, y, d in seen)
        jump = math.hypot(
            focal * x1 / d1 - focal * x0 / d0, focal * y1 / d1 - focal * y0 / d0
        )
        resized = abs(d0 / d1 - 1.0)  # the scale ratio: a depth-only jump
        if jump > HAND_PLACEMENT_TOLERANCE_PX or resized > HAND_SCALE_TOLERANCE:
            note(
                "warning",
                "reframe_jump",
                member,
                f"reframe to {a.to!r} at {change.at:g} s with `keep: {a.keep}` jumps the "
                f"picture by {jump:.0f} px (size x{d0 / d1:.2g}). Say `keep: world` to hold its place, or "
                "`snap` to put it at a socket on purpose.",
            )
    if (
        a.motion == "ballistic"
        and a.inherit is None
        and math.hypot(*change.carried) > _MOVING_EPS
    ):
        note(
            "info",
            "reframe_inherit",
            member,
            f"reframe out of {change.old_frame!r}, which carries it at "
            f"{math.hypot(*change.carried):.3g} units/s: say `inherit: velocity` "
            "(it keeps going) or `inherit: none` (it stops in the world).",
        )


#: Rotation (radians) a sway channel's fit may stray from the lean (about
#: 0.05 degrees); a lean below it all shot long is none.
SWAY_TOLERANCE_RAD: float = 0.0009


def _sway_lean(
    accel: Callable[[float], Point3],
    right: Sequence[Point3],
    times: Sequence[float],
    *,
    sway: FrameSway,
) -> list[float]:
    """The lean (radians, the runtime's; clockwise is positive) of what rides
    a frame accelerating by ``accel(t)``, at each of ``times``, unsettled:
    ``-gain × atan(a / gravity)`` capped at ``limit`` degrees, ``a`` being the
    acceleration along the camera's right axis ``right[i]`` (an#504). So a
    frame braking toward the picture's left (acceleration right) tips what
    rides in it to the left; constant speed is no lean.

    >>> from an.ir.schema import FrameSway
    >>> lean = _sway_lean(lambda t: (9.81, 0.0, 0.0), [(1.0, 0.0, 0.0)], [0.0], sway=FrameSway(gain=0.5))
    >>> round(lean[0], 4) == round(-0.5 * math.atan(1.0), 4)
    True
    """
    limit = math.radians(float(sway.limit))
    out = []
    for t, r in zip(times, right):
        a = sum(x * y for x, y in zip(accel(t), r))
        lean = -float(sway.gain) * math.atan2(a, float(sway.gravity))
        out.append(max(-limit, min(limit, lean)))
    return out


def _fit_lean(
    lean: Sequence[float], *, duration: float, tol: float, min_step: float
) -> tuple[float, list[tuple[float, float, float, float, Any]]] | None:
    """A lean sampled at ``len(lean)`` even steps over ``[0, duration]``,
    fitted by :func:`fit_channel`: ``(value at 0, [(ta, tb, va, vb, easing)])``
    with the flat segments dropped, or ``None`` when it stays under ``tol``
    all shot long."""
    if max(abs(v) for v in lean) <= tol:
        return None
    n = len(lean) - 1

    def g(t: float) -> float:
        x = min(max(t / duration * n, 0.0), float(n))
        i = min(int(x), n - 1)
        return lean[i] + (lean[i + 1] - lean[i]) * (x - i)

    segments = [
        seg
        for seg in fit_channel(g, 0.0, duration, tolerance=tol, min_step=min_step)
        if abs(seg[2] - seg[3]) > _FLAT_CHANNEL_EPS
    ]
    return g(0.0), segments


def _lean_actions(
    entity_id: str,
    fitted: tuple[float, list[tuple[float, float, float, float, Any]]],
) -> list[Any]:
    """The ``rotation`` channel of ``entity_id`` from :func:`_fit_lean`. It SETS
    the rotation: the core's entities rest at 0, so a genre rig with a rest
    rotation on the entity root has to add its own (an#580)."""
    v0, segments = fitted
    out: list[Any] = [set_(entity_id, "rotation", v0, at=0.0)]
    for ta, tb, va, vb, easing in segments:
        tw = tween(
            entity_id, "rotation", to=vb, duration=tb - ta, from_=va, easing=easing
        )
        out.append(sequence(delay(ta), tw) if ta > 0 else tw)
    return out


def _sway_members(
    mids: Sequence[str],
    ctx: _FrameCtx,
    *,
    legs: Mapping[str, Sequence[tuple[float, str, bool]]],
    frame_of: Mapping[str, str],
    fps: float,
    min_step: float,
    tol: float = SWAY_TOLERANCE_RAD,
) -> dict[str, list[Any]]:
    """``{member: its rotation actions}`` for the members of ``mids`` that lean
    with an accelerating frame (an#504), the others left out.

    A member's course is a list of legs ``(start, frame, flying)`` (one leg
    from ``-inf`` in ``frame_of[mid]`` when it never reframes): on each leg it
    leans with the acceleration of the frame it stands in (whose world
    acceleration includes its parents'), by the ``sway`` of the nearest frame
    up that frame's chain that declares one; in a frame with none, or in
    flight, it does not lean. So a member that reframes into a swaying frame
    starts leaning, and one that goes out and back resumes. The lean settles
    by that sway's ``settle`` (a first-order lag starting on the lean the shot
    opens with: the frame was already moving); out of a swaying frame it
    returns upright with the settle of the last one it was in. The unsettled lean is computed once per frame and the
    fit once per distinct course, so members riding together cost one."""
    duration, tree = ctx.duration, ctx.tree
    if duration <= 0:
        return {}
    n = max(1, int(math.ceil(duration * fps)))
    dt = duration / n
    times = [duration * i / n for i in range(n + 1)]
    rights: list[Point3] = []
    raw: dict[str, list[float] | None] = {}
    fits: dict[tuple, Any] = {}

    def raw_of(frame: str) -> list[float] | None:
        if frame not in raw:
            governing = tree.sway_frame(frame)
            if governing is None:
                raw[frame] = None
            else:
                if not rights:
                    rights.extend(ctx.eye_at(t).right for t in times)
                raw[frame] = _sway_lean(
                    lambda t: tree.acceleration(
                        frame,
                        t,
                        film_start=ctx.film_start,
                        dt=1.0 / fps,
                        within=(0.0, duration),
                    ),
                    rights,
                    times,
                    sway=tree.frames[governing].sway,
                )
        return raw[frame]

    def lean_of(course: tuple[tuple[float, str, bool], ...]) -> Any:
        target, settle = [0.0] * len(times), [0.0] * len(times)
        last_settle = 0.0  # leaving a swaying frame settles as the last one did
        for i, t in enumerate(times):
            _, frame, flying = [leg for leg in course if leg[0] <= t][-1]
            series = None if flying else raw_of(frame)
            if series is not None:
                target[i] = series[i]
                last_settle = float(tree.frames[tree.sway_frame(frame)].sway.settle)
            settle[i] = last_settle
        lean = [target[0]]
        for v, lag in zip(target[1:], settle[1:]):
            k = 1.0 - math.exp(-dt / lag) if lag > 0 else 1.0
            lean.append(lean[-1] + k * (v - lean[-1]))
        return _fit_lean(lean, duration=duration, tol=tol, min_step=min_step)

    out: dict[str, list[Any]] = {}
    for mid in mids:
        course = tuple(legs.get(mid) or [(-math.inf, frame_of[mid], False)])
        if not any(tree.sway_frame(frame) for _, frame, _ in course):
            continue
        if course not in fits:
            fits[course] = lean_of(course)
        if fits[course] is not None:
            out[mid] = _lean_actions(mid, fits[course])
    return out


@dataclass(frozen=True)
class _Sighting:
    """A member in motion as the camera sees it over a shot: its passages, and
    its depth and screen box at each time of the shot's scan grid (the box is
    ``None`` when its extent is unknown), for the draw-order check."""

    passes: list[tuple[_Pass, float]]
    depths: list[float]
    boxes: list[Box | None]


def _member_passes(
    member: WorldMember,
    ctx: _FrameCtx,
    frame: str,
    tracks: Mapping[str, Track] | None,
    *,
    course: Callable[[float], Point3] | None = None,
    box: Box | None,
    m: float,
    near: float,
    tol: float,
    min_step: float,
    width: float,
    height: float,
    times: Sequence[float],
) -> _Sighting:
    """A positioned member in motion relative to the camera (:func:`_sight` of
    where it stands, ``course`` or its own point and tracks)."""
    view = ctx.view_fn(frame, course or (lambda t: _member_point(member, tracks, t)))
    return _sight(
        view,
        focal=ctx.projection.focal,
        box=box,
        m=m,
        near=near,
        tol=tol,
        min_step=min_step,
        width=width,
        height=height,
        times=times,
    )


def _sight(
    view: Callable[[float], tuple[float, float, float]],
    *,
    focal: float,
    box: Box | None,
    m: float,
    near: float,
    tol: float,
    min_step: float,
    width: float,
    height: float,
    times: Sequence[float],
    ref_height: float | None = None,
) -> _Sighting:
    """Something in motion relative to the camera, ``view`` being ``t -> (right,
    down, depth)`` of its point: one passage per stretch of the shot it is in
    front of the camera and on screen (it can leave and come back), each with
    its depth as it enters; no passage when it never is. Its screen scale is
    ``m · focal / depth``. ``times`` is the shot's scan grid (``_grid``),
    sampled once for the depth runs and the sighting's series."""

    def g(t: float) -> tuple[float, float, float]:
        return to_screen(view(t))

    def to_screen(seen: Point3) -> tuple[float, float, float]:
        rx, ry, depth = seen
        depth = max(depth, near)
        return focal * rx / depth, focal * ry / depth, m * focal / depth

    samples = [view(t) for t in times]
    depths = [s[2] for s in samples]
    boxes = [
        _screen_box((sx, sy), scale, box)
        for sx, sy, scale in (to_screen(s) for s in samples)
    ]
    out: list[tuple[_Pass, float]] = []
    for t0, t1 in _depth_runs(times, depths, near):
        fitted = _fit_pass(
            g,
            t0,
            t1,
            box=box,
            ref_height=(
                ref_height
                if ref_height is not None
                else ((box[3] - box[1]) if box is not None else 1.0)
            ),
            tol=tol,
            min_step=min_step,
            width=width,
            height=height,
        )
        if fitted is not None:
            out.append((fitted, view(fitted.t_in)[2]))
    return _Sighting(out, depths, boxes)


# --- lowering ------------------------------------------------------------------


@dataclass(frozen=True)
class WorldNote:
    """One thing the lowering did or could not do for one shot, for
    `an validate` (its severity) and `an world show`."""

    shot: str
    index: int
    severity: str
    kind: str
    entity: str
    message: str

    @property
    def ir_path(self) -> str:
        """Where a finding on it points: the shot's entities."""
        return f"timeline/{self.index}/entities"

    @property
    def description(self) -> str:
        """The note as a finding says it (validate and the render alike)."""
        return f"{self.entity!r}: {self.message}"


@dataclass(frozen=True)
class Lowered:
    """The scene as the compiler will see it, the notes to report, and for
    each framed shot where its lowered entities came from (``origins``: per
    lowered entity index, the author's entity index, or ``None`` for one the
    world added), so a finding on a lowered shot can name the author's line."""

    scene: SceneIR
    notes: list[WorldNote] = field(default_factory=list)
    origins: dict[int, list[int | None]] = field(default_factory=dict)
    #: Per continued shot (an#542), how many actions its ``continue:`` put
    #: before the author's, so a finding's ``actions/<k>`` can name the
    #: author's line.
    carried: dict[int, int] = field(default_factory=dict)

    def notes_for(self, index: int) -> list[WorldNote]:
        return [n for n in self.notes if n.index == index]


def _film_starts(scene: SceneIR) -> list[float]:
    """Where each shot starts in the film, ignoring dissolves: the fallback
    when the caller has not laid the film out."""
    starts, t = [], 0.0
    for shot in scene.timeline:
        starts.append(t)
        t += float(shot.duration)
    return starts


def _fmt(at: tuple[float, float] | None) -> str:
    if at is None:
        return "(nowhere)"
    return f"({at[0]:.4g}, {at[1]:.4g})"


def _perspective_note(
    note: Callable[[str, str, str, str], None],
    projection: Projection,
    member: WorldMember,
    at: tuple[float, float],
    scale: float,
    *,
    box: Box | None,
    at3: Point3 | None,
) -> None:
    """A warning when a hand-placed member's ``scale`` is not the one the ground plane gives at its screen row (catalogue A6).

    The member is taken to stand on the horizontal plane through its world
    position. A hand ``at`` keeps the world's scale, so walking a member to a
    nearer row by hand leaves it the size of its old row.
    """
    pos = at3 if at3 is not None else member.at
    unit = _unit_scale(member, box, where=f"member {member.id!r}")
    if pos is None or unit is None:
        return
    want = ground_scale(projection, at, floor_y=pos[1], unit=unit)
    if want is None or abs(scale - want) <= PERSPECTIVE_TOLERANCE * want:
        return
    note(
        "warning",
        "perspective",
        member.id,
        f"placed by hand at {_fmt(at)} scale {scale:.3g}, but standing on the "
        f"ground plane there it would be drawn at scale {want:.3g} (size follows "
        "the row's distance below the horizon). Set `stage.scale` to that, or "
        "drop `stage.at` to let the world place it.",
    )


def _lower_shot(
    scene: SceneIR,
    index: int,
    *,
    extents: Extents,
    extent_problems: Mapping[str, str],
    film_start: float,
    width: float,
    height: float,
    fps: float,
    plane_geometry: Mapping[str, Mapping[str, tuple[tuple[float, float], Box | None]]],
    plane_anchors: dict[tuple[str, str], _PlaneAnchor],
) -> tuple[Shot, list[WorldNote], list[int | None]]:
    shot = scene.timeline[index]
    world = scene.world
    notes: list[WorldNote] = []

    def note(severity: str, kind: str, entity: str, message: str) -> None:
        notes.append(WorldNote(shot.id, index, severity, kind, entity, message))

    vp = viewpoint_of(world, shot.viewpoint)
    assert vp is not None
    if world is None:
        raise WorldError(
            f"shot {shot.id!r} has a viewpoint but the scene has no `world`"
        )
    for hid in vp.hide:
        _member(world, hid, where=f"shot {shot.id!r} viewpoint `hide`")
    listed = {e.id: j for j, e in enumerate(shot.entities)}
    if any(STREAM_OVERRIDE in (e.overrides or {}) for e in shot.entities):
        # The shot holds slot entities the lowering made: it IS a lowered shot
        # (a validate of what the render draws), and a second pass would only
        # re-sort what the first laid out. Nothing to add.
        note("info", "lowered", "slots", "already lowered: its stream slots are kept")
        return shot, notes, list(range(len(shot.entities)))
    if world.travel is not None:
        named = sorted(eid for eid in listed if _is_slot_id(eid, world.travel))
        if named:
            raise WorldError(
                f"shot {shot.id!r} lists {named}, named like a stream's slots: "
                "`<stream id>_<n>` is the travelling view's own namespace for the "
                "slot entities it makes, whether or not slot n exists in a shot; "
                "rename them (an#516)."
            )

    # Frames: the tree with this shot's actions on frame channels, and where
    # each member and the camera stand in it.
    duration = float(shot.duration)
    frames = world.all_frames()
    members = {m.id: m for m in world.members}
    positioned = {m.id: m for m in world.members if m.at is not None}
    split = _split_frame_actions(
        shot,
        default_easing=scene.meta.default_easing,
        frames=frames,
        members=positioned,
    )
    try:
        tree = FrameTree(frames, tracks=split.frame_tracks)
    except FrameError as e:
        raise WorldError(f"shot {shot.id!r}: {e}") from None
    vp_frame = vp.frame or world.default_frame()
    if vp_frame not in tree:
        raise WorldError(
            f"shot {shot.id!r}: the viewpoint is `in: {vp_frame}`, which is not a "
            f"frame; the frames are {sorted({WORLD_FRAME, *frames})}."
        )
    frame_of = {m.id: m.frame or world.default_frame() for m in positioned.values()}
    member_at: dict[str, Point3] = {}
    moving: set[str] = set()
    courses = {
        mid: _Course(
            positioned[mid],
            frame_of[mid],
            tree,
            acts,
            split.member_tracks.get(mid, {}),
            film_start=film_start,
        )
        for mid, acts in split.reframes.items()
    }
    for mid, member in positioned.items():
        tracks = split.member_tracks.get(mid)
        fx = frame_of[mid]
        if mid in courses:
            w0 = courses[mid].world_at(0.0)
            member_at[mid] = tree.relative_pose(
                WORLD_FRAME, vp_frame, 0.0, film_start=film_start
            ).apply(w0)
            moving.add(mid)
            continue
        if fx == vp_frame and not tracks:
            continue
        p0 = _member_point(member, tracks, 0.0)
        if fx != vp_frame:
            p0 = tree.relative_pose(fx, vp_frame, 0.0, film_start=film_start).apply(p0)
            if not tree.is_static(fx, vp_frame, duration, film_start=film_start):
                moving.add(mid)
        if _tracks_vary(tracks, duration):
            moving.add(mid)
        member_at[mid] = p0
    projection = resolve_viewpoint(
        world, vp, extents=extents, width=width, height=height, member_at=member_at
    )
    ctx = _FrameCtx(tree, film_start, duration, vp_frame, projection)
    common = dict(
        extents=extents,
        width=width,
        height=height,
        hide=vp.hide,
        extent_problems=extent_problems,
        member_at=member_at,
    )
    projected = member_placements(world, projection, **common)

    # Members in motion relative to the camera: sampled channels, not a placement.
    near = float(world.travel.near) if world.travel is not None else DFLT_TRAVEL_NEAR
    tol = (
        float(world.travel.tolerance_px)
        if world.travel is not None
        else DFLT_TRAVEL_TOLERANCE_PX
    )
    budget = (
        int(world.travel.max_actions)
        if world.travel is not None
        else DFLT_TRAVEL_MAX_ACTIONS
    )
    min_step = _MIN_SAMPLE_FRAMES / float(fps)
    passes: dict[str, list[tuple[_Pass, float]]] = {}
    grid = _grid(0.0, duration, min_step)
    sightings: dict[str, _Sighting] = {}  # for the draw-order check
    for mid in sorted(moving):
        member, box = positioned[mid], extents.get(mid)
        m = _unit_scale(member, box, where=f"member {mid!r}")
        if m is None:
            continue  # unmeasured: the static path says so
        sighting = _member_passes(
            member,
            ctx,
            WORLD_FRAME if mid in courses else frame_of[mid],
            split.member_tracks.get(mid),
            course=courses[mid].world_at if mid in courses else None,
            box=box,
            m=m,
            near=near,
            tol=tol,
            min_step=min_step,
            width=width,
            height=height,
            times=grid,
        )
        if sighting.passes:
            passes[mid] = sighting.passes
            sightings[mid] = sighting
    for mid, course in courses.items():
        for change in course.changes:
            _reframe_notes(change, mid, ctx, near=near, note=note)

    # A lowered scene lowered again: the shot lists the member where its pass
    # begins, so its motion is already there.
    already = {
        e.id
        for e in shot.entities
        if e.id in passes
        and e.stage is not None
        and e.stage.at is not None
        and math.hypot(
            e.stage.at[0] - passes[e.id][0][0].first[0],
            e.stage.at[1] - passes[e.id][0][0].first[1],
        )
        <= HAND_PLACEMENT_TOLERANCE_PX
        and any(
            getattr(a, "target", None) == e.id and a.property in ("x", "y")
            for top in shot.actions
            for a in iter_actions(top)
            if getattr(a, "kind", None) == "tween"
        )
    }

    # A hand `at` keeps the world's scale unless the author set one: a `scale`
    # of exactly 1.0 is the field's default, and the default means "the world's"
    # (decided in an#516, not `model_fields_set`: scene.md and scene.json write
    # `scale` whether it was set or not, so after one save every hand `at` would
    # read as set and lose the world's scale). Native size by hand on a world
    # member is a `set` of `scale_x`/`scale_y` 1 at 0, which wins over placement.
    hand: dict[str, tuple[tuple[float, float], float]] = {}
    for e in shot.entities:
        if e.id in members and e.stage is not None and e.stage.at is not None:
            w = projected[e.id]
            scale = float(e.stage.scale)
            if scale == 1.0 and w.scale is not None:
                scale = w.scale
            hand[e.id] = ((float(e.stage.at[0]), float(e.stage.at[1])), scale)
    fixed = {
        mid: Placed(
            mid,
            (runs[0][0].first[0], runs[0][0].first[1]),
            runs[0][0].first[2],
            runs[0][1],
            _screen_box(
                (runs[0][0].first[0], runs[0][0].first[1]),
                runs[0][0].first[2],
                extents.get(mid),
            ),
            mid not in vp.hide,
            "world",
        )
        for mid, runs in passes.items()
        if mid not in hand
    }
    placed = (
        member_placements(world, projection, hand=hand, fixed=fixed, **common)
        if hand or fixed
        else projected
    )

    ordered: list[tuple[tuple[float, float, float], AssetRef, int | None]] = []
    envs: list[tuple[AssetRef, int | None]] = [
        (e, j) for j, e in enumerate(shot.entities) if e.kind == "environment"
    ]
    for j, entity in enumerate(shot.entities):
        if entity.kind == "environment":
            continue
        p = placed.get(entity.id)
        if p is None or entity.id not in members:
            ordered.append(
                ((2.0, float(j), 0.0), entity, j)
            )  # not a member: on top, as listed
            continue
        if entity.id in vp.hide:
            note(
                "info",
                "listed",
                entity.id,
                "hidden by the viewpoint but listed by the shot: the listing wins",
            )
        depth = p.depth if p.depth is not None else 0.0
        stage = entity.stage
        if stage is not None and stage.at is not None:
            w = projected[entity.id]
            if entity.id in moving and entity.id not in already:
                note(
                    "warning",
                    "hand_moving",
                    entity.id,
                    f"placed by hand at {_fmt(stage.at)}, but the world moves it "
                    f"(it is in frame {frame_of[entity.id]!r} and the viewpoint in "
                    f"{vp_frame!r}, or an `at_*` action moves it): the hand placement "
                    "stays put on screen. Drop `stage.at` to let the world move it, or "
                    "put the member in the viewpoint's frame (`in:`).",
                )
            elif w.at is not None and w.scale is not None and entity.id not in already:
                off = math.hypot(stage.at[0] - w.at[0], stage.at[1] - w.at[1])
                _, eff_scale = hand[entity.id]
                if (
                    off > HAND_PLACEMENT_TOLERANCE_PX
                    or abs(eff_scale - w.scale) > HAND_SCALE_TOLERANCE
                ):
                    note(
                        "warning",
                        "hand",
                        entity.id,
                        f"placed by hand at {_fmt(stage.at)} scale {eff_scale:.3g}; the world "
                        f"puts it at {_fmt(w.at)} scale {w.scale:.3g}. The hand placement wins; "
                        "drop `stage.at` to follow the world, or move the member.",
                    )
            _, eff_scale = hand[entity.id]
            if entity.id not in moving and not members[entity.id].attached:
                _perspective_note(
                    note, projection, members[entity.id], stage.at, eff_scale,
                    box=extents.get(entity.id), at3=member_at.get(entity.id),
                )  # fmt: skip
            if eff_scale != float(stage.scale):
                entity = entity.model_copy(
                    update={"stage": stage.model_copy(update={"scale": eff_scale})}
                )
            ordered.append(((1.0, -depth, float(j)), entity, j))
            continue
        if p.via in ("world", "attached") and p.at is not None and p.scale is not None:
            if stage is not None and stage.scale != 1.0:
                note(
                    "info",
                    "scale",
                    entity.id,
                    f"`stage.scale` {stage.scale:g} is replaced by the world's {p.scale:.3g}",
                )
            new_stage = StagePlacement(
                at=p.at,
                scale=p.scale,
                after=stage.after if stage is not None else members[entity.id].after,
            )
            ordered.append(
                (
                    (1.0, -depth, float(j)),
                    entity.model_copy(update={"stage": new_stage}),
                    j,
                )
            )
            if not p.in_frame and entity.id not in vp.hide:
                note(
                    "info",
                    "out_of_frame",
                    entity.id,
                    f"listed in the shot but the frame does not show it ({p.note or 'off screen'})",
                )
        else:
            if p.note:
                note("warning", "unplaced", entity.id, p.note)
            ordered.append(((1.0, -depth, float(j)), entity, j))

    # Members the frame shows that the shot did not list.
    for mi, member in enumerate(world.members):
        if member.id in listed:
            continue
        p = placed[member.id]
        if member.kind == "environment":
            if p.in_frame:
                envs.append((entity_of(member), None))
            continue
        if not p.in_frame:
            if p.note and member.id not in vp.hide:
                note("warning", "unplaced", member.id, p.note)
            continue
        if p.at is not None and p.scale is not None:
            stage = StagePlacement(at=p.at, scale=p.scale, after=member.after)
        else:
            stage = StagePlacement(after=member.after) if member.after else None
        entity = entity_of(member, stage=stage)
        depth = p.depth if p.depth is not None else 0.0
        ordered.append(((1.0, -depth, 1000.0 + mi), entity, None))
        where = (
            f"at {_fmt(p.at)} scale {p.scale:.3g}"
            if p.at is not None
            else f"with {member.attached.to!r}"
        )  # type: ignore[union-attr]
        note("info", "added", member.id, f"the world adds it {where}")

    actions = list(split.actions)
    emitted = {e.id for _, e, _ in ordered} | {e.id for e, _ in envs}
    for mid in passes:
        if mid in fixed and mid not in already and mid in emitted:
            actions.extend(
                _pass_actions(mid, [p for p, _ in passes[mid]], duration=duration)
            )
    lowered_envs = []
    for e, j in envs:
        e, plane_actions = _with_plane_depths(
            e,
            members.get(e.id),
            world=world,
            ctx=ctx,
            placed=placed,
            viewpoint=vp,
            geometry=plane_geometry.get(e.id, {}),
            anchors=plane_anchors,
            existing=[*shot.actions, *actions],
            sight=dict(
                focal=projection.focal,
                near=near,
                tol=tol,
                min_step=min_step,
                width=width,
                height=height,
                times=grid,
            ),
            note=note,
        )
        lowered_envs.append((e, j))
        actions.extend(plane_actions)
    envs = lowered_envs
    swayed = _sway_members(
        sorted(
            mid
            for mid in emitted & frame_of.keys()
            if members[mid].kind != "environment" and mid not in vp.hide
        ),
        ctx,
        legs={
            mid: [(leg.start, leg.frame, leg.flight is not None) for leg in c.legs]
            for mid, c in courses.items()
        },
        frame_of=frame_of,
        fps=fps,
        min_step=min_step,
    )
    rotated = {
        getattr(a, "target", None)
        for top in shot.actions
        for a in iter_actions(top)
        if getattr(a, "property", None) == "rotation"
    }
    from an.stage.hold import hold_declarations

    # The items the holds solver sets the rotation of (an#590): its own list.
    holds = hold_declarations(shot) if swayed else None
    # Held as the shot opens (`held_by`): the solver rests it at an angle read
    # off the first frame, which a lean would tip for good (an#651), so it does
    # not lean. One a verb takes later leans until then; the solver's angle
    # replaces the lean while it holds it (an#590).
    resting = set(holds.initial) if holds else set()
    handled = set(holds.items) - resting if holds else set()
    for mid in sorted(resting & swayed.keys()):
        del swayed[mid]
        note(
            "warning",
            "sway_rotation",
            mid,
            "its frame sways, and the holds solver holds it as the shot opens "
            "(`held_by`): it does not lean; it rests and is carried at the angles "
            "the solver gives it (an#651). To see it lean, let a swaying holder "
            "carry it, or drop `held_by`.",
        )
    for mid, lean in swayed.items():
        actions.extend(lean)
        if mid in rotated:
            note(
                "warning",
                "sway_rotation",
                mid,
                "its frame sways (it leans with the frame's acceleration) and the "
                "shot also animates its `rotation`: the two fight. Drop one.",
            )
        elif mid in handled:
            note(
                "warning",
                "sway_rotation",
                mid,
                "its frame sways (it leans with the frame's acceleration), and the "
                "holds solver also sets its `rotation` (it is grasped, placed or "
                "released): it leans until a hand takes it; from then on the "
                "solver's angle replaces the lean (an#590).",
            )
    for member in world.members:
        if (
            member.id in emitted
            and member.attached is not None
            and member.attached.to in swayed
        ):
            note(
                "info",
                "sway_attached",
                member.id,
                f"attached to {member.attached.to!r}, which leans with its frame's "
                "acceleration: the attachment does not lean with it. Put the member "
                "in the frame (`in:`) to sway it too.",
            )
    n_motion = len(actions) - len(split.actions)
    if n_motion > budget:
        n_sway = sum(len(lean) for lean in swayed.values())
        sway_note = (
            f" ({n_sway} of them are sway leans, which `tolerance_px` does not "
            "change: put `sway` on fewer frames)"
            if n_sway
            else ""
        )
        raise WorldError(
            f"shot {shot.id!r}: the members and planes in motion lower to {n_motion} actions"
            f"{sway_note}, past the `max_actions` ({budget}). Raise `tolerance_px` "
            "on the travel, cut the shot, or keep fewer members moving relative "
            "to the camera."
        )
    for member in world.members:
        host = member.attached.to if member.attached is not None else None
        if host in passes and member.attached.at is not None:  # type: ignore[union-attr]
            note(
                "warning",
                "attached_moving",
                member.id,
                f"attached to {host!r}, which is in motion relative to the viewpoint: "
                "its offset is applied at the host's placement as the shot opens, and "
                "the attachment does not follow the host's motion across the frame.",
            )
    pass_keys: dict[str, list[tuple[float, tuple[float, float, float]]]] = {}
    extra: list = []
    if world.travel is not None:
        extra, extra_actions, problems = _travel_entities(
            world.travel,
            ctx,
            extents=extents,
            extent_problems=extent_problems,
            fps=fps,
            width=width,
            height=height,
            skip=list(listed),
        )
        # A slot is sorted by the depth of its first instance as the shot
        # opens, and each later pass by its own instance's (an#634); `after`
        # slots a stream behind a plate, which is where a travelling view's
        # streams belong.
        for si, (entity, keys) in enumerate(extra):
            ordered.append(((1.0, -keys[0][1], SLOT_TIEBREAK + si), entity, None))
        pass_keys.update(_slot_paint_keys(extra))
        actions.extend(extra_actions)
        if n_motion and n_motion + len(extra_actions) > budget:
            raise WorldError(
                f"shot {shot.id!r}: the members in motion ({n_motion} actions) and the "
                f"travel's streams ({len(extra_actions)}) together pass `max_actions` "
                f"({budget}). Raise `tolerance_px`, cut the shot, or raise `max_actions` "
                "knowingly."
            )
        for stream_id, problem in problems:
            note("warning", "stream", stream_id, problem)
    # Crossings are keyed in any world, a travel's or not: a member that walks
    # behind one standing is painted behind it while it is behind (an#679).
    pass_keys.update(
        _crossing_paint_keys(
            {
                e.id: key
                for key, e, _ in ordered
                if e.id in placed
                and e.id not in moving
                and not _is_slot(e)
                and placed[e.id].depth is not None
                and key[0] == 1.0
            },
            extra,
            {
                e.id: (sightings[e.id].depths, key)
                for key, e, _ in ordered
                if e.id in sightings and key[0] == 1.0
            },
            duration=duration,
            grid=grid,
            near=near,
        )
    )
    # Built in the order of the first keys, which the compiler's runs read as
    # the opening order (an#658: two that swap as the shot opens).
    ordered = [
        (pass_keys[e.id][0][1] if e.id in pass_keys else key, e, j)
        for key, e, j in ordered
    ]
    ordered.sort(key=lambda item: item[0])
    # Its rotation channel is the lean only where the shot animates no rotation
    # of its own (sway_rotation warns where it does).
    leaning = swayed.keys() - rotated
    ordered = [  # what the world leans, said for the hold layer (an#659)
        (key, _marked(e, SWAY_OVERRIDE, True) if e.id in leaning else e, j)
        for key, e, j in ordered
    ]
    ordered = _with_paint_keys(
        ordered,
        pass_keys,
        entity_ids={e.id for _, e, _ in ordered} | {e.id for e, _ in envs},
        members=members.keys(),
    )
    if sightings:
        _depth_order_notes(
            [e for _, e, _ in ordered],
            sightings,
            placed,
            times=grid,
            duration=duration,
            attached=[(mm.id, mm.attached.to) for mm in world.members if mm.attached]
            + [
                (e.id, e.overrides[ATTACHED_OVERRIDE]["to"])
                for _, e, _ in ordered
                if e.overrides and ATTACHED_OVERRIDE in e.overrides
            ],
            note=note,
        )
    entities = [e for e, _ in envs] + [e for _, e, _ in ordered]
    origins = [j for _, j in envs] + [j for _, _, j in ordered]
    from an.stage.world import UNDRAWN_KINDS

    cast = [
        mid
        for mid, m in positioned.items()
        if m.kind != "environment" and m.kind not in UNDRAWN_KINDS
    ]
    if cast and all(extents.get(mid) is None for mid in cast):
        note(
            "info",
            "unplaced",
            "members",
            "no member of the world could be measured, so this shot draws none of "
            "them (each is noted: a store not supplied, or a ref it cannot find; an#516)",
        )
    return (
        shot.model_copy(update={"entities": entities, "actions": actions}),
        notes,
        origins,
    )


def parallax_factor(z: float, z_ref: float) -> float:
    """The parallax factor of a plane ``z`` deep when what the shot shows is
    ``z_ref`` deep: a camera translating by ``d`` shifts the plane by ``f * d / z``
    and the character plane by ``f * d / z_ref``, so relative to it the plane
    moves by ``z_ref / z`` (a plane at the reference depth is 1, which emits
    nothing; a far one tends to 0).

    >>> parallax_factor(20.0, 2.0), parallax_factor(2.0, 2.0), parallax_factor(1.0, 2.0)
    (0.1, 1.0, 2.0)
    """
    return z_ref / z


def reference_depth(placed: Mapping[str, Placed], viewpoint: Viewpoint) -> float | None:
    """The depth of the character plane in a shot: the viewpoint's subject(s),
    when it names any that the shot shows, else everything the shot shows from
    the world (an attached member rides its host and is not counted again).
    ``None`` when nothing is shown. Depths are the camera's, as the shot opens.

    >>> from an.ir.schema import Viewpoint
    >>> shown = {"a": Placed("a", (0, 0), 1.0, 2.0, None, True, "world"),
    ...          "b": Placed("b", (0, 0), 1.0, 6.0, None, True, "world")}
    >>> reference_depth(shown, Viewpoint()), reference_depth(shown, Viewpoint(subject="b"))
    (4.0, 6.0)
    """
    subjects = (
        [viewpoint.subject]
        if isinstance(viewpoint.subject, str)
        else list(viewpoint.subject or [])
    )

    def depths(ids) -> list[float]:
        return [
            p.depth
            for mid, p in placed.items()
            if mid in ids and p.depth is not None and p.in_frame and p.via == "world"
        ]

    shown = depths(set(subjects)) or depths(set(placed))
    return sum(shown) / len(shown) if shown else None


def plane_frame(world: World, member: WorldMember, plane: str) -> str:
    """The frame plane ``plane`` of environment ``member`` stands in: its own
    ``planes`` entry, else the member's ``in``, else the frame a member that
    names none is in (:meth:`World.default_frame`).

    >>> from an.ir.schema import World, WorldMember
    >>> m = WorldMember(kind="environment", id="set", store="environments", ref="e",
    ...                 frame="car", planes={"sky": "far"})
    >>> plane_frame(World(), m, "sky"), plane_frame(World(), m, "hill")
    ('far', 'car')
    """
    return (member.planes or {}).get(plane) or member.frame or world.default_frame()


def plane_anchor(
    eye: Projection, offset: tuple[float, float], z: float, *, near: float = 0.0
) -> Point3 | None:
    """Where a plane at depth ``z`` of its frame stands: the point where the ray
    from ``eye`` (the camera, in that frame's units) through the plane's origin
    on screen (``offset``, pixels from the frame centre) meets the plane
    ``z`` along the camera's look direction from the frame's origin. The plane
    is a plate facing the camera through that point, ``z - eye.at · forward``
    in front of it; ``None`` when that is less than ``near`` (behind it).

    >>> eye = Projection((0.0, 0.0, -5.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 100.0)
    >>> plane_anchor(eye, (0.0, 50.0), 15.0)   # 20 in front of a camera standing at z = -5
    (0.0, 10.0, 15.0)
    >>> plane_anchor(eye, (0.0, 0.0), -10.0) is None
    True
    >>> side = Projection((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0), 100.0)
    >>> plane_anchor(side, (0.0, 0.0), 20.0)   # a camera looking along +x
    (20.0, 0.0, 0.0)
    """
    ox, oy = offset
    ray = _add(
        eye.forward,
        _add(_mul(eye.right, ox / eye.focal), _mul(eye.down, oy / eye.focal)),
    )
    reach = z - _dot(eye.at, eye.forward)
    if reach <= max(near, _MIN_DEPTH):
        return None
    return _add(eye.at, _mul(ray, reach))


@dataclass(frozen=True)
class _PlaneAnchor:
    """A plane at a depth keyed by the world: the point of its frame it stands
    at, and the depth at which it shows as its environment draws it (scale 1,
    at its ``offset``), both taken the first time a shot keys it, so it is the
    same plate across cuts."""

    at: Point3
    rest: float
    #: The plate's down direction in its frame (the camera's down as it was
    #: anchored): where the camera sees it point is the plate's rotation (an#599).
    down: Point3 = (0.0, 1.0, 0.0)


def _with_plane_depths(
    entity: AssetRef,
    member: WorldMember | None,
    *,
    world: World,
    ctx: _FrameCtx,
    placed: Mapping[str, Placed],
    viewpoint: Viewpoint,
    geometry: Mapping[str, tuple[tuple[float, float], Box | None]],
    anchors: dict[tuple[str, str], _PlaneAnchor],
    existing: Sequence[Any],
    sight: Mapping[str, Any],
    note: Callable[[str, str, str, str], None],
) -> tuple[AssetRef, list[Any]]:
    """``entity`` (an environment) and the actions its member's ``depths``
    derive (an#503); unchanged and none without ``depths``.

    A plane's depth is its ``z`` in its frame (:func:`plane_frame`), measured
    along the camera's look direction from the frame's origin. A plane in a
    frame still relative to the camera's gets the parallax factor ``z_ref /
    depth`` (:data:`PLANE_FACTORS_OVERRIDE`, :func:`reference_depth`), the
    shot's own: the same plane scrolls differently from a wider or a closer
    viewpoint, as parallax does. A plane in a frame that moves relative to the
    camera's is keyed instead (:func:`_plane_keys`). ``geometry`` is each
    plane's ``(offset, box)`` (:func:`an.stage.world.plane_geometry`);
    ``anchors`` the planes already keyed in earlier shots (updated);
    ``existing`` the shot's actions; ``sight`` the knobs of :func:`_sight`.
    A plane in a ``far`` frame or a travel's ``far`` plates is skipped: the
    validator refuses a depth there."""
    if member is None or not member.depths:
        return entity, []
    tree, vp_frame = ctx.tree, ctx.vp_frame
    travel_far = set(world.travel.plates.get("far", ())) if world.travel else set()
    z_ref = reference_depth(placed, viewpoint)
    factors: dict[str, float] = {}
    actions: list[Any] = []
    unmeasured = False
    for name, z in sorted(member.depths.items()):
        frame = plane_frame(world, member, name)
        if (
            frame not in tree
            or f"{member.id}/{name}" in travel_far
            or any(tree.frames[n].coupling == "far" for n in tree.chain(frame))
        ):
            continue
        offset, box = geometry.get(name, ((0.0, 0.0), None))
        if (member.id, name) not in anchors and tree.is_static(
            frame, vp_frame, ctx.duration, film_start=ctx.film_start
        ):
            to_frame = tree.relative_pose(
                vp_frame, frame, 0.0, film_start=ctx.film_start
            )
            eye = ctx.projection.transformed(to_frame)
            at = plane_anchor(eye, offset, z, near=sight["near"])
            if at is None:
                _behind(note, entity.id, name, z, frame)
            elif z_ref is None:
                unmeasured = True
            else:
                factors[name] = parallax_factor(eye.view(at)[2], z_ref)
            continue
        keyed = _plane_keys(
            f"{entity.id}/{name}",
            (member.id, name),
            ctx,
            frame=frame,
            z=z,
            offset=offset,
            box=box,
            anchors=anchors,
            existing=existing,
            sight=sight,
            note=note,
        )
        actions.extend(keyed)
    if unmeasured:
        note(
            "warning",
            "plane_depths",
            entity.id,
            "its planes have world depths but the shot shows no member to measure "
            "them against: the planes keep their own parallax factors.",
        )
    if not factors:
        return entity, actions
    overrides = {**(entity.overrides or {}), PLANE_FACTORS_OVERRIDE: factors}
    return entity.model_copy(update={"overrides": overrides}), actions


def _plate_turn(
    ctx: _FrameCtx,
    frame: str,
    anchor: _PlaneAnchor,
    *,
    tol: float,
    sight: Mapping[str, Any],
) -> Callable[[float], float] | None:
    """``t -> the plate's rotation`` (radians) over the shot, when its frame rolls
    relative to the camera past ``tol`` at some time of it, else ``None``
    (an#599). The angle is where the camera sees the plate's ``down`` point:
    exact for a roll, nothing for a yaw or a pitch (a billboard's verticals stay
    vertical), unwrapped across ±π so a long roll keeps turning."""
    origin = ctx.view_fn(frame, lambda t: anchor.at)
    below = ctx.view_fn(frame, lambda t: _add(anchor.at, anchor.down))

    def raw(t: float) -> float:
        (ax, ay, _), (bx, by, _) = origin(t), below(t)
        return math.atan2(-(bx - ax), by - ay)

    times = _grid(0.0, ctx.duration, sight["min_step"])
    unwrapped = [raw(times[0])]
    for t in times[1:]:
        unwrapped.append(_nearest_turn(raw(t), unwrapped[-1]))
    if max(abs(a) for a in unwrapped) <= tol:
        return None

    def turn(t: float) -> float:
        k = bisect.bisect_left(times, t)
        near = unwrapped[min(k, len(times) - 1)]
        return _nearest_turn(raw(t), near)

    return turn


def _nearest_turn(angle: float, near: float) -> float:
    """``angle`` plus the whole turns that bring it nearest ``near``.

    >>> round(_nearest_turn(-3.1, 3.1), 4)
    3.1832
    """
    return angle + 2.0 * math.pi * round((near - angle) / (2.0 * math.pi))


def _with_rotation(
    passage: _Pass,
    turn: Callable[[float], float] | None,
    *,
    tol: float,
    min_step: float,
) -> _Pass:
    """``passage`` with the plate's ``rotation`` fitted from ``turn`` (every
    passage of a plate that turns at all, so none holds a stale angle), or
    unchanged when it never turns."""
    if turn is None:
        return passage
    rotation = fit_channel(
        turn, passage.t_in, passage.t_out, tolerance=tol, min_step=min_step
    )
    return _Pass(
        passage.t_in,
        passage.t_out,
        {**passage.channels, "rotation": rotation},
        passage.first,
    )


def _behind(
    note: Callable,
    entity: str,
    name: str,
    z: float,
    frame: str,
    *,
    then: str = "it keeps its own parallax",
) -> None:
    note(
        "warning",
        "plane_depths",
        entity,
        f"plane {name!r} is at depth {z:g} in frame {frame!r}, which is not in front "
        f"of the camera as the shot opens: {then}.",
    )


def _plane_keys(
    target: str,
    key: tuple[str, str],
    ctx: _FrameCtx,
    *,
    frame: str,
    z: float,
    offset: tuple[float, float],
    box: Box | None,
    anchors: dict[tuple[str, str], _PlaneAnchor],
    existing: Sequence[Any],
    sight: Mapping[str, Any],
    note: Callable[[str, str, str, str], None],
) -> list[Any]:
    """The keys of a plane standing still in a frame that moves relative to the
    camera (an#503): a plate in ``world`` under a moving ``vehicle`` streams past
    at its depth, as a member does (:func:`_sight`: its screen position and
    apparent size, fitted to the travel's tolerance, hidden while it is behind
    the camera or off screen). It is anchored (:class:`_PlaneAnchor`) the first
    time a shot keys it, so a cut continues the same plate. It rides the 2D
    camera as the character plane does, as every member in motion does. The
    shot's own actions on a channel it would key win (a warning); keys the shot
    already holds (a lowered scene lowered again) are not added twice."""
    entity = target.split("/", 1)[0]
    hide = [set_(target, "alpha", 0.0, at=0.0)]
    anchor = anchors.get(key)
    if anchor is None:
        to_frame = ctx.tree.relative_pose(
            ctx.vp_frame, frame, 0.0, film_start=ctx.film_start
        )
        eye = ctx.projection.transformed(to_frame)
        at = plane_anchor(eye, offset, z, near=sight["near"])
        if at is None:
            _behind(note, entity, key[1], z, frame, then="it is hidden")
            return hide
        anchor = anchors[key] = _PlaneAnchor(at, eye.view(at)[2], eye.down)
    view = ctx.view_fn(frame, lambda t: anchor.at)
    focal = sight["focal"]
    span = max(sight["width"], sight["height"])
    # The scale is judged at the plate's visible extent: no more than the frame
    # (a canvas-sized fill would otherwise demand sub-pixel scale keys, an#599).
    ref_height = min(box[3] - box[1], sight["height"]) if box is not None else span
    angle_tol = sight["tol"] / (span / 2)
    turn = _plate_turn(ctx, frame, anchor, tol=angle_tol, sight=sight)
    passes = [
        _with_rotation(p, turn, tol=angle_tol, min_step=sight["min_step"])
        for p, _ in _sight(
            view, box=box, m=anchor.rest / focal, ref_height=ref_height, **sight
        ).passes
    ]
    keys = _pass_actions(target, passes, duration=ctx.duration) if passes else hide
    there = [a.model_dump(mode="json") for a in existing]
    if all(k.model_dump(mode="json") in there for k in keys):
        return []  # already there: a lowered scene lowered again
    hand = {
        a.property
        for top in existing
        for a in iter_actions(top)
        if getattr(a, "target", None) == target
    } & set().union(*map(_properties, keys))
    if hand and hand <= {"alpha", "rotation"}:
        note(
            "warning",
            "plane_depths",
            entity,
            f"plane {key[1]!r} is at a depth and the shot's own actions drive its "
            f"{sorted(hand)}: they win"
            + (
                ", so it is not hidden while the camera does not see it"
                if "alpha" in hand
                else ""
            )
            + (", so it does not turn with its frame" if "rotation" in hand else "")
            + ".",
        )
        return [k for k in keys if not (_properties(k) & hand)]
    if hand:
        note(
            "warning",
            "plane_depths",
            entity,
            f"plane {key[1]!r} is at a depth in frame {frame!r}, which moves relative "
            f"to the viewpoint's, but the shot's own actions drive its {sorted(hand)}: "
            "the actions win and the plane is not keyed by its depth.",
        )
        return []
    if not passes:
        note(
            "info",
            "plane_depths",
            entity,
            f"plane {key[1]!r} is at a depth in frame {frame!r} and the shot never "
            "shows it: it is hidden.",
        )
    return keys


def _properties(action: Any) -> set[str]:
    """The properties ``action`` and the actions under it drive."""
    return {a.property for a in iter_actions(action) if hasattr(a, "property")}


def _depth_order_notes(
    painted: Sequence[AssetRef],
    sightings: Mapping[str, _Sighting],
    placed: Mapping[str, Placed],
    *,
    times: Sequence[float],
    duration: float,
    attached: Collection[tuple[str, str]],
    note: Callable[[str, str, str, str], None],
) -> None:
    """The ``draw_order`` notes of one framed shot: the members in motion as
    their sightings saw them, the ones at rest where ``placed`` puts them, on
    screen the whole shot when in frame."""
    depths: dict[str, float | Sequence[float]] = {}
    windows: dict[str, list[tuple[float, float]]] = {}
    boxes: dict[str, Any] = {}
    # An attached member rides its host (the attachment pass places it, and its
    # `placed` depth and box are the host's as the shot opens): not examined.
    riders = {member for member, _ in attached}
    for mid, s in sightings.items():
        if mid in riders:
            continue
        depths[mid], boxes[mid] = s.depths, s.boxes
        windows[mid] = [(p.t_in, p.t_out) for p, _ in s.passes]
    for mid, p in placed.items():
        if mid in depths or mid in riders or p.depth is None or not p.in_frame:
            continue
        depths[mid], windows[mid] = p.depth, [(0.0, duration)]
        boxes[mid] = p.box if p.box is not None or p.at is None else (*p.at, *p.at)
    found = depth_order_problems(
        painted, times, depths, windows, boxes, attached=attached
    )
    for entity_id, message in found[:MAX_DEPTH_ORDER_NOTES]:
        note("warning", "draw_order", entity_id, message)
    if len(found) > MAX_DEPTH_ORDER_NOTES:
        entity_id = found[MAX_DEPTH_ORDER_NOTES][0]
        note(
            "warning",
            "draw_order",
            entity_id,
            f"{len(found) - MAX_DEPTH_ORDER_NOTES} more pairs are painted on the "
            "wrong side of each other in this shot (the first "
            f"{MAX_DEPTH_ORDER_NOTES} are listed): a crowd passing through itself "
            "wants a cut, or `stage.after` where the order matters.",
        )


#: Pairs listed per shot; the rest are counted in one closing note.
MAX_DEPTH_ORDER_NOTES: int = 10

#: A member must be this much nearer (world units) than one painted over it
#: before it counts as nearer: depth ties and rounding are not an order.
DEPTH_ORDER_TOLERANCE: float = 1e-6

#: Slack (seconds) on a window's ends when asking whether a scan time is in it.
_WINDOW_EPS: float = 1e-9


def depth_order_problems(
    painted: Sequence[AssetRef],
    times: Sequence[float],
    depths: Mapping[str, float | Sequence[float]],
    windows: Mapping[str, Sequence[tuple[float, float]]],
    boxes: Mapping[str, Any] | None = None,
    *,
    attached: Collection[tuple[str, str]] = (),
    tolerance: float = DEPTH_ORDER_TOLERANCE,
) -> list[tuple[str, str]]:
    """``(entity, message)`` for each pair of members painted one way
    (``painted``, back to front) that the camera sees the other way round at
    some time of the shot, one of them in motion (an#510, catalogue A3). The
    lowering orders a member by its depth where it first shows, so one that
    passes another in depth is painted on the wrong side of it from then on.

    The data is sampled once per member at ``times`` (the shot's scan grid):
    ``depths`` maps a member at rest to its depth and one in motion to its
    depth at each time; ``windows`` maps each to the ``(t_in, t_out)``
    stretches it is on screen and in front of the camera; ``boxes`` maps each
    to its screen box ``(x0, y0, x1, y1)`` (one box at rest, one per time in
    motion; ``None``, or a member missing, is a box not known, which overlaps
    everything). A pair counts only at a time both are on screen and their
    boxes overlap: two members apart on screen can pass in depth unseen. A
    member not in ``depths`` (a stream slot, a non-member) is not checked,
    nor a pair where either has a ``stage.after`` (the author's statement of
    order), nor a pair ``attached`` links (``(member, host)``, either way
    round): the attachment pass places them. A pair whose entities both carry
    paint keys (:data:`an.base.PAINT_KEYS_OVERRIDE`) is painted, at each time,
    in the order of their keys in force then (an#681), not in ``painted``'s.
    Each pair is reported once, at the first such time.

    >>> from an.ir.schema import AssetRef
    >>> a, b = (AssetRef(kind="prop", id=i, store="props", ref=i) for i in "ab")
    >>> times = [0.0, 0.5, 1.0, 1.5, 2.0]
    >>> walk = [10.0, 8.0, 6.0, 4.0, 2.0]  # `a` walks towards the camera
    >>> whole = {"a": [(0.0, 2.0)], "b": [(0.0, 2.0)]}
    >>> [(e, m.split(",")[0]) for e, m in depth_order_problems(
    ...     [a, b], times, {"a": walk, "b": 5.0}, whole)]
    [('a', "painted behind 'b' but nearer the camera from 1.50 s")]

    Not while `a` is off screen, nor when the two never overlap on screen,
    nor when one is attached to the other:

    >>> depth_order_problems([a, b], times, {"a": walk, "b": 5.0},
    ...     {"a": [(0.0, 1.0)], "b": [(0.0, 2.0)]})
    []
    >>> depth_order_problems([a, b], times, {"a": walk, "b": 5.0}, whole,
    ...     {"a": [(-50.0, 0.0, -40.0, 10.0)] * 5, "b": (40.0, 0.0, 50.0, 10.0)})
    []
    >>> depth_order_problems([a, b], times, {"a": walk, "b": 5.0}, whole,
    ...     attached=[("b", "a")])
    []
    """
    boxes = boxes or {}
    linked = {frozenset(pair) for pair in attached}
    n = len(times)

    def series(mid: str) -> tuple[list[float], list[Any], list[bool]]:
        d, box = depths[mid], boxes.get(mid)
        if isinstance(d, (int, float)):
            ds, bs = [float(d)] * n, [box] * n
        else:
            ds, bs = list(d), list(box) if box is not None else [None] * n
        spans = windows.get(mid, ())
        on = [
            any(t0 - _WINDOW_EPS <= t <= t1 + _WINDOW_EPS for t0, t1 in spans)
            for t in times
        ]
        return ds, bs, on

    def overlap(p: Any, q: Any) -> bool:
        if p is None or q is None:
            return True
        return p[0] <= q[2] and q[0] <= p[2] and p[1] <= q[3] and q[1] <= p[3]

    def key_at(keys: Sequence[Any], t: float) -> list[Any]:
        """The paint key in force at ``t`` (keys sort farther first)."""
        return [list(k) for s, k in keys if s <= t + _WINDOW_EPS][-1]

    members = [e for e in painted if e.id in depths]
    sampled = {e.id: series(e.id) for e in members}
    paint_keys = {
        e.id: (e.overrides or {})[PAINT_KEYS_OVERRIDE]
        for e in members
        if PAINT_KEYS_OVERRIDE in (e.overrides or {})
    }
    moving = {e.id for e in members if not isinstance(depths[e.id], (int, float))}
    out: list[tuple[str, str]] = []
    for i, behind in enumerate(members):
        if behind.stage and behind.stage.after:
            continue
        db, bb, onb = sampled[behind.id]
        for front in members[i + 1 :]:
            if behind.id not in moving and front.id not in moving:
                continue  # both at rest: ordered by their depth, by construction
            if (front.stage and front.stage.after) or frozenset(
                (behind.id, front.id)
            ) in linked:
                continue
            df, bf, onf = sampled[front.id]
            kb, kf = paint_keys.get(behind.id), paint_keys.get(front.id)

            def swapped(k: int) -> bool:  # the keys paint `front` first at k
                return (
                    kb is not None
                    and kf is not None
                    and key_at(kf, times[k]) < key_at(kb, times[k])
                )

            def wrong(k: int) -> bool:
                if swapped(k):
                    return df[k] < db[k] - tolerance
                return db[k] < df[k] - tolerance

            k = next(
                (
                    k
                    for k in range(n)
                    if onb[k] and onf[k] and wrong(k) and overlap(bb[k], bf[k])
                ),
                None,
            )
            if k is not None:
                if swapped(k):
                    behind_id, front_id, d_near, d_far = front.id, behind.id, df[k], db[k]
                else:
                    behind_id, front_id, d_near, d_far = behind.id, front.id, db[k], df[k]
                out.append(
                    (
                        behind_id,
                        f"painted behind {front_id!r} but nearer the camera from "
                        f"{times[k]:.2f} s, where they overlap on screen (depth "
                        f"{d_near:.3g} against {d_far:.3g}): the world orders each "
                        "member by its depth where it first shows, so it stays on "
                        "the wrong side. Cut the shot where they pass, or say which "
                        "is in front with `stage.after`.",
                    )
                )
    return out


def viewpoint_key(shot: Any) -> Any:
    """What identifies a shot's viewpoint for "the same framing": its name, or
    its inline viewpoint's dump; ``None`` for a hand-placed shot. Two shots
    with one key cut within a framing; two keys are a cut between framings
    (``cut_continuity``, and a ``continue:`` across them, an#542)."""
    vp = getattr(shot, "viewpoint", None)
    if vp is None or isinstance(vp, str):
        return vp
    return json.dumps(vp.model_dump(), sort_keys=True, default=str)


def _is_slot_id(entity_id: str, travel: Travel) -> bool:
    """Whether ``entity_id`` is a stream slot's (``<stream id>_<k>``)."""
    return any(
        re.fullmatch(rf"{re.escape(stream.id)}_\d+", entity_id) is not None
        for stream in travel.streams
    )


def entity_of(member: WorldMember, *, stage: StagePlacement | None = None) -> AssetRef:
    """The shot entity a world member becomes. An attached member carries its
    attachment under ``overrides[ATTACHED_OVERRIDE]`` (``{to, at?, scale}``),
    so a pass that places it from its host can find the host in the shot."""
    overrides = dict(member.overrides or {})
    if member.attached is not None:
        overrides[ATTACHED_OVERRIDE] = member.attached.model_dump()
    return AssetRef(
        kind=member.kind,
        id=member.id,
        store=member.store,
        ref=member.ref,
        overrides=overrides or None,
        library=member.library,
        stage=stage,
    )


def member_of(entity: AssetRef, **placement: Any) -> WorldMember:
    """The world member a shot entity becomes (the inverse of
    :func:`entity_of`): its fields as they are, its ``stage`` dropped (a
    member is placed by each shot's viewpoint) and its ``after`` kept, with
    ``placement`` (``at``, ``height``, ...) where the world stands it. Its
    ``joints`` stay with the shot: they tie it to other entities of THAT shot,
    and :func:`entity_of` gives a member none.

    >>> e = AssetRef(kind="prop", id="lamp", store="props", ref="lamp",
    ...              stage=StagePlacement(at=(1.0, 2.0), after="set/sky"))
    >>> m = member_of(e, at=(0.0, 0.0, 5.0), height=1.0)
    >>> m.at, m.after, m.stage
    ((0.0, 0.0, 5.0), 'set/sky', None)
    """
    fields = entity.model_dump(exclude={"stage", "joints"}, exclude_none=True)
    if entity.stage is not None and entity.stage.after is not None:
        fields["after"] = entity.stage.after
    return WorldMember(**{**fields, **placement})


def pose_look(pose: Pose) -> tuple[float, float]:
    """The ``(yaw, pitch)`` in degrees a pose faces.

    >>> pose_look(Pose())
    (0.0, 0.0)
    """
    return _angles_toward(pose.rotate((0.0, 0.0, 1.0)))


def frame_poses(
    scene: SceneIR, *, film_starts: Sequence[float] | None = None
) -> list[dict[str, Any]]:
    """Per framed shot, where each frame stands in the world as the shot opens
    and as it closes (after the shot's own ``<frame>:at_*`` actions): what
    `an world show --frames` prints.

    >>> from an.ir.schema import Frame, FrameMoving, Viewpoint, World
    >>> scene = SceneIR(world=World(frames={"car": Frame(moving=FrameMoving(speed=10.0))},
    ...                             viewpoints={"v": Viewpoint(at=(0.0, 0.0, 0.0), frame="car")}),
    ...                 timeline=[Shot(id="s", duration=2.0, viewpoint="v")])
    >>> row = frame_poses(scene)[0]
    >>> row["viewpoint_frame"], row["frames"][0]["name"], row["frames"][0]["end"]["at"]
    ('car', 'car', (0.0, 0.0, 20.0))
    """
    world = scene.world
    if world is None:
        return []
    starts = list(film_starts) if film_starts is not None else _film_starts(scene)
    frames = world.all_frames()
    rows: list[dict[str, Any]] = []
    for i, shot in enumerate(scene.timeline):
        if shot.viewpoint is None:
            continue
        vp = viewpoint_of(world, shot.viewpoint)
        assert vp is not None
        split = _split_frame_actions(
            shot,
            default_easing=scene.meta.default_easing,
            frames=frames,
            members={m.id for m in world.members if m.at is not None},
        )
        try:
            tree = FrameTree(frames, tracks=split.frame_tracks)
        except FrameError as e:
            raise WorldError(f"shot {shot.id!r}: {e}") from None

        def at(name: str, t: float) -> dict[str, Any]:
            pose = tree.world_pose(name, t, film_start=starts[i])
            yaw, pitch = pose_look(pose)
            return {
                "at": tuple(round(v, 6) + 0.0 for v in pose.at),
                "yaw": round(yaw, 6) + 0.0,
                "pitch": round(pitch, 6) + 0.0,
            }

        rows.append(
            {
                "shot": shot.id,
                "viewpoint_frame": vp.frame or world.default_frame(),
                "frames": [
                    {
                        "name": name,
                        "parent": frames[name].parent,
                        "coupling": frames[name].coupling,
                        "start": at(name, 0.0),
                        "end": at(name, float(shot.duration)),
                    }
                    for name in frames
                ],
            }
        )
    return rows


def lower_world(
    scene: SceneIR,
    *,
    extents: Extents,
    film_starts: Sequence[float] | None = None,
    fps: float | None = None,
    extent_problems: Mapping[str, str] | None = None,
    plane_geometry: Mapping[str, Mapping[str, tuple[tuple[float, float], Box | None]]]
    | None = None,
) -> Lowered:
    """The scene with every framed shot's placements derived from the world.

    A shot without a viewpoint is returned as it is. For a framed shot: its
    listed entities keep their order of appearance among themselves but are
    drawn in depth order (far first) with the members the frame shows and the
    shot did not list; environments come first; listed entities that are not
    members go on top. A listed member's hand ``stage.at`` wins (a note says
    when it disagrees with the world; its ``scale`` is the world's unless set);
    one without is filled in. A member the viewpoint hides is left out unless
    the shot lists it: the listing wins, and a note says so. Under a travel,
    the streams' slot entities are added with their motion; a scene already
    lowered gains nothing from a second pass.

    ``extents`` is what the stage measured (:func:`an.stage.world.member_extents`),
    ``extent_problems`` why some could not be; ``film_starts`` is where each
    shot starts in the film, so stream phase is continuous across cuts (the
    shot sum by default); ``plane_geometry`` is ``{environment member id: {plane:
    (offset, box)}}``, each plane's origin on screen (``Plane.offset``) and its
    drawn box around it (``None``: unknown), read by the stage
    (:func:`an.stage.world.plane_geometry`): where a plane at a world depth is
    anchored and when it is on screen (an#503; the origin and no box for one
    it does not name).

    Raises :class:`WorldError` for a viewpoint the world cannot resolve.

    >>> lower_world(SceneIR(), extents={}).scene.timeline
    []
    """
    if not has_world(scene):
        return Lowered(scene, [])
    starts = list(film_starts) if film_starts is not None else _film_starts(scene)
    if len(starts) < len(scene.timeline):
        raise WorldError(
            f"film_starts has {len(starts)} entries for {len(scene.timeline)} shots"
        )
    width = float(scene.meta.resolution.width)
    height = float(scene.meta.resolution.height)
    rate = float(fps if fps is not None else scene.meta.fps)
    shots: list[Shot] = []
    notes: list[WorldNote] = []
    origins: dict[int, list[int | None]] = {}
    plane_anchors: dict[tuple[str, str], _PlaneAnchor] = {}  # across the cuts
    for i, shot in enumerate(scene.timeline):
        if shot.viewpoint is None:
            shots.append(shot)
            continue
        lowered, shot_notes, shot_origins = _lower_shot(
            scene,
            i,
            extents=extents,
            extent_problems=extent_problems or {},
            film_start=starts[i],
            width=width,
            height=height,
            fps=rate,
            plane_geometry=plane_geometry or {},
            plane_anchors=plane_anchors,
        )
        shots.append(lowered)
        notes.extend(shot_notes)
        origins[i] = shot_origins
    return Lowered(scene.model_copy(update={"timeline": shots}), notes, origins)
