"""One world, many shots: the scene space's geometry and its lowering (ADR 0007).

A scene may declare a **space** (`SceneIR.space`): members at world positions
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

>>> from an.ir.schema import Space, SpaceMember, Viewpoint
>>> space = Space(members=[
...     SpaceMember(kind="prop", id="near", store="props", ref="p", at=(1.0, 0.0, 2.0), height=1.0),
...     SpaceMember(kind="prop", id="far", store="props", ref="p", at=(1.0, 0.0, 20.0), height=1.0),
... ])
>>> box = (-10.0, -20.0, 10.0, 0.0)             # 20 px tall art, feet at the origin
>>> eye = resolve_viewpoint(space, Viewpoint(at=(0.0, 0.0, 0.0), focal=1000.0),
...                         extents={"near": box, "far": box}, width=1280, height=720)
>>> placed = member_placements(space, eye, extents={"near": box, "far": box}, width=1280, height=720)
>>> placed["near"].at, round(placed["near"].scale, 2)
((500.0, 0.0), 25.0)
>>> placed["far"].at, round(placed["far"].scale, 2)
((50.0, 0.0), 2.5)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from an.ir.compose import delay, sequence, set_, tween
from an.timing.easing import apply_easing
from an.ir.schema import (
    DFLT_FOV_DEG,
    SHOT_SIZES,
    AssetRef,
    SceneIR,
    Shot,
    Space,
    SpaceMember,
    StagePlacement,
    Stream,
    Travel,
    Viewpoint,
)

__all__ = [
    "Box",
    "Extents",
    "HAND_PLACEMENT_TOLERANCE_PX",
    "HAND_SCALE_TOLERANCE",
    "Lowered",
    "Placed",
    "Projection",
    "SpaceError",
    "SpaceNote",
    "focal_length",
    "has_space",
    "lower_space",
    "member_placements",
    "resolve_viewpoint",
    "fit_channel",
    "stream_instances",
    "viewpoint_of",
]

#: A member's native extent: ``(x0, y0, x1, y1)`` in its art's pixels at
#: ``stage.scale`` 1, relative to its placement point (a character's feet).
#: ``None`` means it could not be measured (nothing drawn).
Box = tuple[float, float, float, float]
#: ``{member or stream id: Box | None}``, measured by the stage
#: (:func:`an.stage.space.member_extents`); the IR layer only reads it.
Extents = Mapping[str, "Box | None"]
Point3 = tuple[float, float, float]

#: A hand ``stage.at`` this far from the world's placement is "the same"
#: (the cut-continuity tolerance, an#394); farther is a lint warning.
HAND_PLACEMENT_TOLERANCE_PX: float = 2.0
HAND_SCALE_TOLERANCE: float = 0.02
#: A depth this small is "at the camera": nothing projects through it.
_MIN_DEPTH: float = 1e-6
#: Adaptive sampling never splits a stream's keys finer than this many frames.
_MIN_SAMPLE_FRAMES: float = 1.0
#: The finest grid the sampler reaches, as a safety net for a pathological `g`.
_MAX_SAMPLE_SPLITS: int = 14
#: Two consecutive keys of one channel closer than this are one value.
_FLAT_CHANNEL_EPS: float = 1e-6


class SpaceError(ValueError):
    """A space or viewpoint that cannot be resolved (an unknown member, a
    subject whose extent is unknown, a viewpoint name the space does not
    have). The IR layer raises it; `an validate` reports it as an error and
    the lowering is then skipped for that scene."""


def has_space(scene: SceneIR) -> bool:
    """Whether lowering would change anything: a space, or a shot with a viewpoint.

    >>> has_space(SceneIR())
    False
    """
    return scene.space is not None or any(
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
        raise SpaceError("a direction must not be the zero vector")
    return _mul(a, 1.0 / n)


def _basis(yaw: float, pitch: float, roll: float) -> tuple[Point3, Point3, Point3]:
    """``(forward, right, down)`` for a look of ``yaw`` (turn right), ``pitch``
    (look down) and ``roll`` (the picture turns clockwise), in degrees.

    >>> [tuple(round(v, 6) + 0.0 for v in axis) for axis in _basis(0.0, 0.0, 0.0)]
    [(0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    >>> [round(v, 6) + 0.0 for v in _basis(90.0, 0.0, 0.0)[0]]
    [1.0, 0.0, 0.0]
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
            _add(_mul(right, c), _mul(down, s)),
            _add(_mul(right, -s), _mul(down, c)),
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
    >>> round(yaw, 3), round(pitch, 2)
    (-0.0, 10.81)
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
    space: Space | None, viewpoint: str | Viewpoint | None
) -> Viewpoint | None:
    """The shot's viewpoint as a model: a name is looked up in the space.

    >>> viewpoint_of(Space(viewpoints={"a": Viewpoint(focal=1.0)}), "a").focal
    1.0
    >>> viewpoint_of(None, "a")
    Traceback (most recent call last):
    ...
    an.ir.space.SpaceError: shot names viewpoint 'a' but the scene has no `space`
    """
    if viewpoint is None:
        return None
    if isinstance(viewpoint, Viewpoint):
        return viewpoint
    if space is None:
        raise SpaceError(
            f"shot names viewpoint {viewpoint!r} but the scene has no `space`"
        )
    try:
        return space.viewpoints[viewpoint]
    except KeyError:
        raise SpaceError(
            f"unknown viewpoint {viewpoint!r}; the space names "
            f"{sorted(space.viewpoints) or 'none'}"
        ) from None


def _member(space: Space | None, member_id: str, *, where: str) -> SpaceMember:
    for m in space.members if space is not None else ():
        if m.id == member_id:
            return m
    raise SpaceError(f"{where} names {member_id!r}, which is not a member of the space")


def _unit_scale(
    member: SpaceMember | Stream, box: Box | None, *, where: str
) -> float | None:
    """World units per native pixel: the member's size over its art's extent,
    or its `scale` as given. ``None`` when the member is sized by its art and
    the art could not be measured (a lint, not a crash)."""
    if member.scale is not None:
        return float(member.scale)
    if box is None:
        return None
    w, h = box[2] - box[0], box[3] - box[1]
    if member.height is not None:
        if h <= 0:
            raise SpaceError(f"{where}: its art has no height to size by")
        return float(member.height) / h
    if member.width is not None:
        if w <= 0:
            raise SpaceError(f"{where}: its art has no width to size by")
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
    space: Space | None,
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
    at ``subject_at``. The band of several subjects is their union, at their
    mean depth, and it must fit the frame's width as well as its height.

    >>> from an.ir.schema import Space, SpaceMember
    >>> space = Space(members=[SpaceMember(kind="prop", id="p", store="props", ref="p", at=(3.0, 0.0, 10.0), height=2.0)])
    >>> eye = resolve_viewpoint(space, Viewpoint(subject="p", size="full", focal=900.0),
    ...                         extents={"p": (-10.0, -40.0, 10.0, 0.0)}, width=1600, height=900)
    >>> [round(v, 3) for v in eye.at]           # 2 units tall fills 0.9 × 900 px: 2.222 away, centred on the box
    [3.0, -1.0, 7.778]
    """
    vp = viewpoint_of(space, viewpoint)
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
    boxes: list[tuple[float, float, float, float]] = []
    depths: list[float] = []
    for sid in subjects:
        member = _member(space, sid, where="viewpoint `subject`")
        if member.at is None:
            raise SpaceError(
                f"viewpoint subject {sid!r}: it is attached to {member.attached.to!r}; "  # type: ignore[union-attr]
                "frame on the host instead"
            )
        box = extents.get(sid)
        m = _unit_scale(member, box, where=f"viewpoint subject {sid!r}")
        if box is None or m is None:
            raise SpaceError(
                f"viewpoint subject {sid!r}: its extent cannot be measured, so no shot "
                "size fits it; give the viewpoint `distance` and `at`-less `look`, "
                "or size the member by `height`/`width` with measurable art"
            )
        boxes.append(_world_box(tuple(map(float, member.at)), box, m))  # type: ignore[arg-type]
        depths.append(float(member.at[2]))
    top, bottom, fill = SHOT_SIZES[vp.size or "full"]
    x0 = min(b[0] for b in boxes)
    x1 = max(b[2] for b in boxes)
    bands = [(b[1] + top * (b[3] - b[1]), b[1] + bottom * (b[3] - b[1])) for b in boxes]
    y0, y1 = min(b[0] for b in bands), max(b[1] for b in bands)
    centre: Point3 = ((x0 + x1) / 2.0, (y0 + y1) / 2.0, sum(depths) / len(depths))
    if vp.distance is not None:
        distance = float(vp.distance)
    else:
        distance = max(
            focal * (y1 - y0) / (fill * float(height)),
            focal * (x1 - x0) / (fill * float(width)),
            _MIN_DEPTH,
        )
    forward, right, down = _basis(yaw, pitch, roll)
    sx, sy = (float(a) for a in vp.subject_at)
    at = _sub(
        _sub(_sub(centre, _mul(forward, distance)), _mul(right, sx * distance / focal)),
        _mul(down, sy * distance / focal),
    )
    return Projection(at, forward, right, down, focal)


# --- placing members ---------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    """Where one member lands in a framed shot."""

    id: str
    #: Screen pixels from the frame centre; ``None`` when another pass places
    #: it (attached without an offset).
    at: tuple[float, float] | None
    scale: float | None
    depth: float | None
    #: Its screen box, when its extent is known.
    box: tuple[float, float, float, float] | None
    in_frame: bool
    #: ``world`` (projected), ``attached`` (from the host's placement),
    #: ``host`` (goes with the host, placed by nothing here), ``environment``.
    via: str
    #: Why it is not placed by the world, when it is not (an unmeasured art).
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


def member_placements(
    space: Space,
    projection: Projection,
    *,
    extents: Extents,
    width: float,
    height: float,
    hide: Sequence[str] = (),
    hand: Mapping[str, tuple[tuple[float, float], float]] | None = None,
) -> dict[str, Placed]:
    """Every member's placement under ``projection``: ``{id: Placed}``.

    Positioned members are projected; attached ones follow their host (an
    offset in the host's native units, times the host's scale); an
    environment is present with no placement. A member behind the camera
    is placed nowhere and is not in frame. ``hand`` is ``{id: (at, scale)}``
    for members a shot placed by hand: that placement stands in for the
    projected one (its depth stays the world's), so what is attached to it
    follows the hand, as the compiler's own passes do.
    """
    out: dict[str, Placed] = {}
    hidden = set(hide)
    hand = dict(hand or {})

    def place(member: SpaceMember) -> Placed:
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
                _member(space, member.attached.to, where=f"member {member.id!r}")
            )
            visible = host.in_frame and member.id not in hidden
            if member.attached.at is None or host.at is None or host.scale is None:
                p = Placed(member.id, None, None, host.depth, None, visible, "host")
            else:
                dx, dy = (float(a) for a in member.attached.at)
                at = (host.at[0] + host.scale * dx, host.at[1] + host.scale * dy)
                scale = host.scale * float(member.attached.scale)
                box = extents.get(member.id)
                sbox = (
                    (
                        at[0] + scale * box[0],
                        at[1] + scale * box[1],
                        at[0] + scale * box[2],
                        at[1] + scale * box[3],
                    )
                    if box is not None
                    else None
                )
                p = Placed(member.id, at, scale, host.depth, sbox, visible, "attached")
        else:
            assert member.at is not None
            box = extents.get(member.id)
            m = _unit_scale(member, box, where=f"member {member.id!r}")
            shot = projection.project(tuple(map(float, member.at)))  # type: ignore[arg-type]
            if shot is None or m is None:
                note = (
                    "behind the camera"
                    if shot is None
                    else "its extent cannot be measured; give it `scale`"
                )
                p = Placed(member.id, None, None, None, None, False, "world", note)
            else:
                sx, sy, depth = shot
                scale = m * projection.focal / depth
                if member.id in hand:
                    (sx, sy), scale = hand[member.id]
                sbox = (
                    (
                        sx + scale * box[0],
                        sy + scale * box[1],
                        sx + scale * box[2],
                        sy + scale * box[3],
                    )
                    if box is not None
                    else None
                )
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

    for member in space.members:
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
    lo, hi = _range(stream.every)
    pitch = (lo + hi) / 2.0
    spread = (hi - lo) / 4.0
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
        if box is None:
            return _in_frame((sx, sy), None, width=width, height=height)
        sbox = (
            sx + scale * box[0],
            sy + scale * box[1],
            sx + scale * box[2],
            sy + scale * box[3],
        )
        return _in_frame((sx, sy), sbox, width=width, height=height)

    n = max(1, int(math.ceil((b - a) / step)))
    times = [a + (b - a) * i / n for i in range(n + 1)]
    seen = [on_screen(t) for t in times]
    if not any(seen):
        return None
    first = max(0, seen.index(True) - 1)
    last = min(n, n - seen[::-1].index(True) + 1)
    return times[first], times[last]


def _stream_actions(
    entity_id: str,
    channels: Mapping[str, list[tuple[float, float, float, float, Any]]],
    *,
    show_at: float | None,
    hide_at: float | None,
) -> list[Any]:
    """The instance's motion: a `set` of each channel at its first segment
    and a tween per segment (a channel's flat stretches dropped), plus the
    alpha that hides it before it is in range and after it has passed the
    camera."""
    actions: list[Any] = []
    for prop, segments in channels.items():
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
    if show_at is not None and show_at > 0:
        actions.append(set_(entity_id, "alpha", 0.0, at=0.0))
        actions.append(set_(entity_id, "alpha", 1.0, at=show_at))
    if hide_at is not None:
        actions.append(set_(entity_id, "alpha", 0.0, at=hide_at))
    return actions


def _travel_entities(
    travel: Travel,
    projection: Projection,
    *,
    extents: Extents,
    film_start: float,
    duration: float,
    fps: float,
    width: float,
    height: float,
) -> tuple[list[tuple[AssetRef, float]], list[Any], list[tuple[str, str]]]:
    """The stream instances a framed shot shows, as ``(entity, depth as the
    shot opens)`` and their actions, plus the problems found (unsized
    streams) as ``(stream id, message)``."""
    direction = _unit(tuple(map(float, travel.direction)))  # type: ignore[arg-type]
    speed = float(travel.speed)
    k_forward = _dot(direction, projection.forward)
    s_cam0 = _dot(projection.at, direction)
    reach = float(travel.far)
    s_lo = s_cam0 + speed * film_start - reach
    s_hi = s_cam0 + speed * (film_start + duration) + reach
    min_step = _MIN_SAMPLE_FRAMES / float(fps)
    entities: list[tuple[AssetRef, float]] = []
    actions: list[Any] = []
    problems: list[tuple[str, str]] = []
    for stream in travel.streams:
        box = extents.get(stream.id)
        m = _unit_scale(stream, box, where=f"stream {stream.id!r}")
        if m is None:
            problems.append(
                (stream.id, "its extent cannot be measured; give the stream `scale`")
            )
            continue
        ref_height = (box[3] - box[1]) if box is not None else 1.0
        for k, p in stream_instances(stream, travel, s_min=s_lo, s_max=s_hi):
            depth0 = _dot(
                _sub(p, projection.moved(_mul(direction, speed * film_start)).at),
                projection.forward,
            )
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
            tol = float(travel.tolerance_px)
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
            first = g(t_in)
            entity_id = f"{stream.id}_{k}"
            entities.append(
                (
                    AssetRef(
                        kind=stream.kind,
                        id=entity_id,
                        store=stream.store,
                        ref=stream.ref,
                        stage=StagePlacement(
                            at=(first[0], first[1]), scale=first[2], after=stream.after
                        ),
                    ),
                    depth0,
                )
            )
            actions.extend(
                _stream_actions(
                    entity_id,
                    channels,
                    show_at=t_in if t_in > 0 else None,
                    hide_at=t_out if t_out < duration else None,
                )
            )
    return entities, actions, problems


# --- lowering ------------------------------------------------------------------


@dataclass(frozen=True)
class SpaceNote:
    """One thing the lowering did or could not do for one shot, for
    `an validate` (its severity) and `an space show`."""

    shot: str
    index: int
    severity: str
    kind: str
    entity: str
    message: str


@dataclass(frozen=True)
class Lowered:
    """The scene as the compiler will see it, and the notes to report."""

    scene: SceneIR
    notes: list[SpaceNote] = field(default_factory=list)

    def notes_for(self, index: int) -> list[SpaceNote]:
        return [n for n in self.notes if n.index == index]


def _film_starts(scene: SceneIR) -> list[float]:
    """Where each shot starts in the film, ignoring dissolves: the fallback
    when the caller has not laid the film out."""
    starts, t = [], 0.0
    for shot in scene.timeline:
        starts.append(t)
        t += float(shot.duration)
    return starts


def _lower_shot(
    scene: SceneIR,
    index: int,
    *,
    extents: Extents,
    film_start: float,
    width: float,
    height: float,
    fps: float,
) -> tuple[Shot, list[SpaceNote]]:
    shot = scene.timeline[index]
    space = scene.space
    notes: list[SpaceNote] = []

    def note(severity: str, kind: str, entity: str, message: str) -> None:
        notes.append(SpaceNote(shot.id, index, severity, kind, entity, message))

    vp = viewpoint_of(space, shot.viewpoint)
    assert vp is not None
    if space is None:
        raise SpaceError(
            f"shot {shot.id!r} has a viewpoint but the scene has no `space`"
        )
    for hid in vp.hide:
        _member(space, hid, where=f"shot {shot.id!r} viewpoint `hide`")
    projection = resolve_viewpoint(
        space, vp, extents=extents, width=width, height=height
    )
    members = {m.id: m for m in space.members}
    listed = {e.id: j for j, e in enumerate(shot.entities)}
    hand = {
        e.id: ((float(e.stage.at[0]), float(e.stage.at[1])), float(e.stage.scale))
        for e in shot.entities
        if e.id in members and e.stage is not None and e.stage.at is not None
    }
    world = member_placements(
        space, projection, extents=extents, width=width, height=height, hide=vp.hide
    )
    placed = (
        member_placements(
            space,
            projection,
            extents=extents,
            width=width,
            height=height,
            hide=vp.hide,
            hand=hand,
        )
        if hand
        else world
    )

    # The shot's own entities, filled in from the world where they let it.
    ordered: list[tuple[tuple[float, float, float], AssetRef]] = []
    envs: list[AssetRef] = [e for e in shot.entities if e.kind == "environment"]
    for j, entity in enumerate(shot.entities):
        if entity.kind == "environment":
            continue
        p = placed.get(entity.id)
        if p is None or entity.id not in members:
            ordered.append(
                ((2.0, float(j), 0.0), entity)
            )  # not a member: on top, as listed
            continue
        depth = p.depth if p.depth is not None else 0.0
        stage = entity.stage
        if stage is not None and stage.at is not None:
            w = world[entity.id]
            if w.at is not None and w.scale is not None:
                off = math.hypot(stage.at[0] - w.at[0], stage.at[1] - w.at[1])
                if (
                    off > HAND_PLACEMENT_TOLERANCE_PX
                    or abs(stage.scale - w.scale) > HAND_SCALE_TOLERANCE
                ):
                    note(
                        "warning",
                        "hand",
                        entity.id,
                        f"placed by hand at {_fmt(stage.at)} scale {stage.scale:g}; the world "
                        f"puts it at {_fmt(w.at)} scale {w.scale:.3g}. The hand placement wins; "
                        "drop `stage.at` to follow the world, or move the member.",
                    )
            ordered.append(((1.0, -depth, float(j)), entity))
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
            ordered.append(((1.0, -depth, float(j)), entity))

    # Members the frame shows that the shot did not list.
    for mi, member in enumerate(space.members):
        if member.id in listed:
            continue
        p = placed[member.id]
        if member.kind == "environment":
            if p.in_frame:
                envs.append(
                    AssetRef(
                        kind=member.kind,
                        id=member.id,
                        store=member.store,
                        ref=member.ref,
                        overrides=member.overrides,
                        library=member.library,
                    )
                )
            continue
        if not p.in_frame:
            if p.note and member.id not in vp.hide:
                note("warning", "unplaced", member.id, p.note)
            continue
        if p.at is not None and p.scale is not None:
            stage = StagePlacement(at=p.at, scale=p.scale, after=member.after)
        else:
            stage = StagePlacement(after=member.after) if member.after else None
        entity = AssetRef(
            kind=member.kind,
            id=member.id,
            store=member.store,
            ref=member.ref,
            overrides=member.overrides,
            library=member.library,
            stage=stage,
        )
        depth = p.depth if p.depth is not None else 0.0
        ordered.append(((1.0, -depth, 1000.0 + mi), entity))
        where = (
            f"at {_fmt(p.at)} scale {p.scale:.3g}"
            if p.at is not None
            else f"with {members[p.id].attached.to!r}"
        )  # type: ignore[union-attr]
        note("info", "added", member.id, f"the world adds it {where}")

    actions = list(shot.actions)
    if space.travel is not None:
        extra, extra_actions, problems = _travel_entities(
            space.travel,
            projection,
            extents=extents,
            film_start=film_start,
            duration=float(shot.duration),
            fps=fps,
            width=width,
            height=height,
        )
        # An instance is sorted by its depth as the shot opens; one that passes
        # the cast mid-shot keeps that order (`after` slots a stream behind a
        # plate, which is where a travelling view's streams belong).
        for si, (entity, depth0) in enumerate(extra):
            ordered.append(((1.0, -depth0, 10_000.0 + si), entity))
        actions.extend(extra_actions)
        for stream_id, problem in problems:
            note("warning", "stream", stream_id, problem)
    ordered.sort(key=lambda item: item[0])
    entities = envs + [e for _, e in ordered]
    return shot.model_copy(update={"entities": entities, "actions": actions}), notes


def _fmt(at: tuple[float, float] | None) -> str:
    if at is None:
        return "(nowhere)"
    return f"({at[0]:.4g}, {at[1]:.4g})"


def lower_space(
    scene: SceneIR,
    *,
    extents: Extents,
    film_starts: Sequence[float] | None = None,
    fps: float | None = None,
) -> Lowered:
    """The scene with every framed shot's placements derived from the space.

    A shot without a viewpoint is returned as it is. For a framed shot: its
    listed entities keep their order of appearance among themselves but are
    drawn in depth order (far first) with the members the frame shows and the
    shot did not list; environments come first; listed entities that are not
    members go on top. A listed member's hand ``stage.at`` wins (a note says
    when it disagrees with the world); one without is filled in. Under a
    travel, the streams' instances are appended with their motion.

    ``extents`` is what the stage measured (:func:`an.stage.space.member_extents`);
    ``film_starts`` is where each shot starts in the film, so stream phase is
    continuous across cuts (the shot sum by default).

    Raises :class:`SpaceError` for a viewpoint the space cannot resolve.

    >>> lower_space(SceneIR(), extents={}).scene.timeline
    []
    """
    if not has_space(scene):
        return Lowered(scene, [])
    starts = list(film_starts) if film_starts is not None else _film_starts(scene)
    width = float(scene.meta.resolution.width)
    height = float(scene.meta.resolution.height)
    rate = float(fps if fps is not None else scene.meta.fps)
    shots: list[Shot] = []
    notes: list[SpaceNote] = []
    for i, shot in enumerate(scene.timeline):
        if shot.viewpoint is None:
            shots.append(shot)
            continue
        lowered, shot_notes = _lower_shot(
            scene,
            i,
            extents=extents,
            film_start=starts[i],
            width=width,
            height=height,
            fps=rate,
        )
        shots.append(lowered)
        notes.extend(shot_notes)
    return Lowered(scene.model_copy(update={"timeline": shots}), notes)
