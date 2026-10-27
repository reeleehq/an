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

import math
import random
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Mapping, Sequence

from an.base import PLANE_FACTORS_OVERRIDE
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
        p = _add(
            _add(_mul(direction, s), _mul(right_h, lane)), (0.0, float(stream.y), 0.0)
        )
        out.append((k, p))
    return out


def stream_slots(stream: Stream, travel: Travel) -> int:
    """How many entities a stream needs: one per instance that can be between
    ``near`` and ``far`` at once, plus one. Instance ``k`` is drawn by slot
    ``k mod slots``, so an entity is reused for the next instance once this
    one has passed the camera — and the SAME world instance lands in the same
    slot in every shot, which is what keeps a cut continuous.

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
) -> _Pass | None:
    """The channels of one entity's passage: its on-screen window within
    ``[t_in, t_out]`` and the Bézier fits of ``g`` on it; ``None`` when it is
    never on screen."""
    window = _on_screen_window(
        g, t_in, t_out, box, width=width, height=height, step=min_step
    )
    if window is None:
        return None
    t_in, t_out = window
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


def _depth_runs(
    depth: Callable[[float], float],
    a: float,
    b: float,
    lo: float,
    *,
    step: float,
) -> list[tuple[float, float]]:
    """The stretches of ``[a, b]`` during which ``depth >= lo`` (in front of
    the camera), scanned at ``step`` and widened by a step each side; runs that
    touch after widening are one."""
    n = max(1, int(math.ceil((b - a) / step)))
    times = [a + (b - a) * i / n for i in range(n + 1)]
    inside = [depth(t) >= lo for t in times]
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
) -> tuple[list[tuple[AssetRef, float]], list[Any], list[tuple[str, str]]]:
    """The stream instances a framed shot shows, as ``(entity, depth as the
    shot opens)`` and their actions, plus the problems found (unsized
    streams) as ``(stream id, message)``. Entities are SLOTS (`stream_slots`),
    each drawing the instances that pass through it one after another, so
    the entity count is bounded by the depth range and never by the shot's
    length; ``skip`` names slot entities the shot already has (a lowered
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
    tol = float(travel.tolerance_px)
    entities: list[tuple[AssetRef, float]] = []
    actions: list[Any] = []
    problems: list[tuple[str, str]] = []
    skipped = set(skip)
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
        slots = stream_slots(stream, travel)
        passes: dict[int, list[tuple[int, _Pass, float]]] = {}
        for k, p in stream_instances(stream, travel, s_min=s_lo, s_max=s_hi):
            view = ctx.view_fn(frame, lambda t, p=p: p)
            if closed is not None:
                at_start = projection.moved(_mul(cam_dir, speed * film_start))
                depth0 = _dot(_sub(p, at_start.at), projection.forward)
                slope = -speed * k_forward
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
                depth0 = view(0.0)[2]
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
            )
            if fitted is None:
                continue  # never on screen during this shot
            passes.setdefault(k % slots, []).append((k, fitted, depth0))
        for slot in sorted(passes):
            entity_id = f"{stream.id}_{slot}"
            if entity_id in skipped:
                continue
            ordered = sorted(passes[slot], key=lambda item: item[1].t_in)
            for (_, prev, _), (_, nxt, _) in zip(ordered, ordered[1:]):
                if nxt.t_in < prev.t_out:
                    # Two instances on screen at once in one slot: the slot count
                    # comes from the depth window, and a wide lens or a yawed
                    # view shows more of the row than that (review B3). Loud,
                    # not a teleport; the slot count from the on-screen span is
                    # the fix, filed.
                    raise WorldError(
                        f"stream {stream.id!r}: two instances are on screen at once "
                        f"in one slot ({entity_id}, {prev.t_out:.2f}s and {nxt.t_in:.2f}s) "
                        "under this viewpoint; the travelling view's slots are sized by "
                        "the depth range, which a wide lens or a yawed view exceeds. "
                        "Narrow `fov`, bring `far` in, or space the stream out (`every`)."
                    )
            first = ordered[0][1]
            entities.append(
                (
                    AssetRef(
                        kind=stream.kind,
                        id=entity_id,
                        store=stream.store,
                        ref=stream.ref,
                        stage=StagePlacement(
                            at=(first.first[0], first.first[1]),
                            scale=first.first[2],
                            after=stream.after,
                        ),
                    ),
                    ordered[0][2],
                )
            )
            actions.extend(
                _pass_actions(entity_id, [p for _, p, _ in ordered], duration=duration)
            )
    budget = int(travel.max_actions)
    if len(actions) > budget:
        raise WorldError(
            f"this shot's travel lowers to {len(actions)} actions for "
            f"{len(entities)} stream entities, past the travel's `max_actions` "
            f"({budget}). Space the streams further apart (`every`), bring `far` "
            f"in ({travel.far:g}), raise `tolerance_px` ({travel.tolerance_px:g}), "
            f"cut the shot ({duration:g} s), or raise `max_actions` knowingly."
        )
    return entities, actions, problems


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
) -> list[tuple[_Pass, float]]:
    """A positioned member in motion relative to the camera, as one passage per
    stretch of the shot it is in front of the camera and on screen (it can
    leave and come back), each with its depth as it enters. Empty when it
    never is."""
    view = ctx.view_fn(frame, course or (lambda t: _member_point(member, tracks, t)))
    focal = ctx.projection.focal

    def g(t: float) -> tuple[float, float, float]:
        rx, ry, depth = view(t)
        depth = max(depth, near)
        return focal * rx / depth, focal * ry / depth, m * focal / depth

    out: list[tuple[_Pass, float]] = []
    for t0, t1 in _depth_runs(
        lambda t: view(t)[2], 0.0, ctx.duration, near, step=min_step
    ):
        fitted = _fit_pass(
            g,
            t0,
            t1,
            box=box,
            ref_height=(box[3] - box[1]) if box is not None else 1.0,
            tol=tol,
            min_step=min_step,
            width=width,
            height=height,
        )
        if fitted is not None:
            out.append((fitted, view(fitted.t_in)[2]))
    return out


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


@dataclass(frozen=True)
class Lowered:
    """The scene as the compiler will see it, the notes to report, and for
    each framed shot where its lowered entities came from (``origins``: per
    lowered entity index, the author's entity index, or ``None`` for one the
    world added), so a finding on a lowered shot can name the author's line."""

    scene: SceneIR
    notes: list[WorldNote] = field(default_factory=list)
    origins: dict[int, list[int | None]] = field(default_factory=dict)

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
    if world.travel is not None and any(
        _is_slot_id(eid, world.travel) for eid in listed
    ):
        # The shot already holds a stream's slot entities: it IS a lowered shot
        # (a validate of what the render draws), and a second pass would only
        # re-sort what the first laid out. Nothing to add.
        return shot, notes, list(range(len(shot.entities)))

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
    for mid in sorted(moving):
        member, box = positioned[mid], extents.get(mid)
        m = _unit_scale(member, box, where=f"member {mid!r}")
        if m is None:
            continue  # unmeasured: the static path says so
        found = _member_passes(
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
        )
        if found:
            passes[mid] = found
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
    # of exactly 1.0 is the field's default, and the default means "the world's".
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
                envs.append((_entity_of(member), None))
            continue
        if not p.in_frame:
            if p.note and member.id not in vp.hide:
                note("warning", "unplaced", member.id, p.note)
            continue
        if p.at is not None and p.scale is not None:
            stage = StagePlacement(at=p.at, scale=p.scale, after=member.after)
        else:
            stage = StagePlacement(after=member.after) if member.after else None
        entity = _entity_of(member, stage=stage)
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
            f"shot {shot.id!r}: the members in motion lower to {n_motion} actions"
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
        # opens; `after` slots a stream behind a plate, which is where a
        # travelling view's streams belong.
        for si, (entity, depth0) in enumerate(extra):
            ordered.append(((1.0, -depth0, 10_000.0 + si), entity, None))
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
    ordered.sort(key=lambda item: item[0])
    envs = [
        (_with_plane_factors(e, members.get(e.id), placed, vp, note), j)
        for e, j in envs
    ]
    entities = [e for e, _ in envs] + [e for _, e, _ in ordered]
    origins = [j for _, j in envs] + [j for _, _, j in ordered]
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


def _with_plane_factors(
    entity: AssetRef,
    member: WorldMember | None,
    placed: Mapping[str, Placed],
    viewpoint: Viewpoint,
    note: Callable[[str, str, str, str], None],
) -> AssetRef:
    """``entity`` (an environment) carrying the factors its member's ``depths``
    derive (:data:`PLANE_FACTORS_OVERRIDE`); unchanged without ``depths``. A
    plane's depth is its distance from the camera along the look direction, and
    its factor ``z_ref / z`` is relative to :func:`reference_depth`, so it is the
    shot's own: the same plane scrolls differently from a wider or a closer
    viewpoint, as parallax does."""
    if member is None or not member.depths:
        return entity
    z_ref = reference_depth(placed, viewpoint)
    if z_ref is None:
        note(
            "warning",
            "plane_depths",
            entity.id,
            "its planes have world depths but the shot shows no member to measure "
            "them against: the planes keep their own parallax factors.",
        )
        return entity
    factors = {name: parallax_factor(z, z_ref) for name, z in member.depths.items()}
    overrides = {**(entity.overrides or {}), PLANE_FACTORS_OVERRIDE: factors}
    return entity.model_copy(update={"overrides": overrides})


def _is_slot_id(entity_id: str, travel: Travel) -> bool:
    """Whether ``entity_id`` is a stream slot's (``<stream id>_<k>``)."""
    return any(
        re.fullmatch(rf"{re.escape(stream.id)}_\d+", entity_id) is not None
        for stream in travel.streams
    )


def _entity_of(member: WorldMember, *, stage: StagePlacement | None = None) -> AssetRef:
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
    shot sum by default).

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
        )
        shots.append(lowered)
        notes.extend(shot_notes)
        origins[i] = shot_origins
    return Lowered(scene.model_copy(update={"timeline": shots}), notes, origins)
