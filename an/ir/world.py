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
from typing import Any, Callable, Mapping, Sequence

from an.ir.compose import delay, sequence, set_, tween
from an.ir.schema import (
    DFLT_FOV_DEG,
    SHOT_SIZES,
    AssetRef,
    SceneIR,
    Shot,
    StagePlacement,
    Stream,
    Travel,
    Viewpoint,
    World,
    WorldMember,
)
from an.timing.easing import apply_easing

__all__ = [
    "Box",
    "Extents",
    "HAND_PLACEMENT_TOLERANCE_PX",
    "HAND_SCALE_TOLERANCE",
    "Lowered",
    "Placed",
    "Projection",
    "WorldError",
    "WorldNote",
    "fit_channel",
    "focal_length",
    "has_world",
    "lower_world",
    "member_placements",
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


def _basis(yaw: float, pitch: float, roll: float) -> tuple[Point3, Point3, Point3]:
    """``(forward, right, down)`` for a look of ``yaw`` (turn right), ``pitch``
    (look down) and ``roll`` (the PICTURE turns clockwise: what was on the
    right moves to the bottom), in degrees.

    >>> [tuple(round(v, 6) + 0.0 for v in axis) for axis in _basis(0.0, 0.0, 0.0)]
    [(0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    >>> [round(v, 6) + 0.0 for v in _basis(90.0, 0.0, 0.0)[0]]
    [1.0, 0.0, 0.0]
    >>> eye = Projection((0.0, 0.0, 0.0), *_basis(0.0, 0.0, 90.0), focal=100.0)
    >>> [round(v, 6) + 0.0 for v in eye.project((1.0, 0.0, 10.0))]   # a point on the right: now at the bottom
    [0.0, 10.0, 10.0]
    """
    t, p, r_ = (math.radians(a) for a in (yaw, pitch, roll))
    forward: Point3 = (
        math.sin(t) * math.cos(p),
        math.sin(p),
        math.cos(t) * math.cos(p),
    )
    right: Point3 = (math.cos(t), 0.0, -math.sin(t))
    down = _cross(forward, right)
    if r_:
        c, s = math.cos(r_), math.sin(r_)
        right, down = (
            _add(_mul(right, c), _mul(down, -s)),
            _add(_mul(right, s), _mul(down, c)),
        )
    return forward, right, down


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
) -> Projection:
    """The camera a viewpoint is, as a :class:`Projection`.

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
        position: Point3 = tuple(map(float, member.at))  # type: ignore[assignment]
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
    """
    out: dict[str, Placed] = {}
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
            shot = projection.project(tuple(map(float, member.at)))  # type: ignore[arg-type]
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
            return "linear", 0.0
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


def _travel_entities(
    travel: Travel,
    projection: Projection,
    *,
    extents: Extents,
    extent_problems: Mapping[str, str],
    film_start: float,
    duration: float,
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
    scene lowered again adds nothing)."""
    direction = _unit(tuple(map(float, travel.direction)))  # type: ignore[arg-type]
    speed = float(travel.speed)
    k_forward = _dot(direction, projection.forward)
    s_cam0 = _dot(projection.at, direction)
    reach = float(travel.far)
    s_lo = s_cam0 + speed * film_start - reach
    s_hi = s_cam0 + speed * (film_start + duration) + reach
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
        ref_height = (box[3] - box[1]) if box is not None else 1.0
        slots = stream_slots(stream, travel)
        passes: dict[int, list[tuple[int, _Pass, float]]] = {}
        for k, p in stream_instances(stream, travel, s_min=s_lo, s_max=s_hi):
            at_start = projection.moved(_mul(direction, speed * film_start))
            depth0 = _dot(_sub(p, at_start.at), projection.forward)
            slope = -speed * k_forward
            if abs(slope) < _MIN_DEPTH:
                if not (travel.near <= depth0 <= travel.far):
                    continue
                t_in, t_out = 0.0, duration
            else:
                ta, tb = (travel.near - depth0) / slope, (travel.far - depth0) / slope
                t_in, t_out = max(0.0, min(ta, tb)), min(duration, max(ta, tb))
                if t_out <= t_in:
                    continue

            def g(t: float, p: Point3 = p) -> tuple[float, float, float]:
                eye = projection.moved(_mul(direction, speed * (film_start + t)))
                rx, ry, depth = eye.view(p)
                depth = max(
                    depth, float(travel.near)
                )  # past the camera: hold at the near plane
                return (
                    projection.focal * rx / depth,
                    projection.focal * ry / depth,
                    m * projection.focal / depth,
                )

            window = _on_screen_window(
                g, t_in, t_out, box, width=width, height=height, step=min_step
            )
            if window is None:
                continue  # never on screen during this shot
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
            passes.setdefault(k % slots, []).append(
                (k, _Pass(t_in, t_out, channels, g(t_in)), depth0)
            )
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
    projection = resolve_viewpoint(
        world, vp, extents=extents, width=width, height=height
    )
    members = {m.id: m for m in world.members}
    listed = {e.id: j for j, e in enumerate(shot.entities)}
    if world.travel is not None and any(
        _is_slot_id(eid, world.travel) for eid in listed
    ):
        # The shot already holds a stream's slot entities: it IS a lowered shot
        # (a validate of what the render draws), and a second pass would only
        # re-sort what the first laid out. Nothing to add.
        return shot, notes, list(range(len(shot.entities)))
    common = dict(
        extents=extents,
        width=width,
        height=height,
        hide=vp.hide,
        extent_problems=extent_problems,
    )
    projected = member_placements(world, projection, **common)
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
    placed = (
        member_placements(world, projection, hand=hand, **common) if hand else projected
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
            if w.at is not None and w.scale is not None:
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

    actions = list(shot.actions)
    if world.travel is not None:
        extra, extra_actions, problems = _travel_entities(
            world.travel,
            projection,
            extents=extents,
            extent_problems=extent_problems,
            film_start=film_start,
            duration=float(shot.duration),
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
        for stream_id, problem in problems:
            note("warning", "stream", stream_id, problem)
    ordered.sort(key=lambda item: item[0])
    entities = [e for e, _ in envs] + [e for _, e, _ in ordered]
    origins = [j for _, j in envs] + [j for _, _, j in ordered]
    return (
        shot.model_copy(update={"entities": entities, "actions": actions}),
        notes,
        origins,
    )


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
