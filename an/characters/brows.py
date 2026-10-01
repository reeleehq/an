"""Brow acting: where the brows can go, what may not draw there, and the ``face.brows`` capability.

An expression acts largely with the brows (raised in surprise, knitted in
anger, tilted in sorrow). A drawing that sits where the brows go — a hat brim
pulled down over the forehead — leaves them nothing to read against, and the
expression falls to the lids, the gaze and the mouth (an#252). So:

- **The brows' acting range** (:func:`brow_range`) is measured, not assumed:
  the factory's brow drawing, posed by every shipped expression preset through
  the default expression binding (its travel and its signs), on every view
  that shows a brow, at the character's head scale — in the offline head's
  drawing units, so it can be compared with what the head draws.
- **A hat is seated above that range** (:func:`seat_above_brows`): lifted, and
  if its crown would leave the drawing, flattened toward its crown, by one
  transform shared by every view so the hat does not change shape as the
  character turns. When even the flattest seat still overlaps — a small head
  under a tall hat — the overlap is not hidden: the factory records it in the
  descriptor's ``occluded`` (a declared fact, written by whoever KNOWS the
  geometry, like ``colour_roles``).
- **``face.brows``** is the capability the character analyser
  (:mod:`an.library.character`) derives with :func:`brow_affordance`: two brow
  slots with art on an overlay face, and nothing recorded over them. The cut-out genre's ``expression`` aspect
  requires it for its full-face method (:mod:`an.characters.methods`).

Hair is not measured here: the brows' outer ends meet the hairline by design
(the default hair has always run under them), so a hair style is held to the
default hairline instead (tests), never to the brows' range.

Units: the offline head is drawn in an :data:`HEAD_ART_SIZE` square; the rig
draws it :data:`~an.characters.schema.REFERENCE_HEAD_HEIGHT` × ``head_scale``
view-box units tall, hung from the neck at
:data:`~an.characters.schema.HEAD_ANCHOR`. The face offsets scale with the head
(``_scale_face``), so a brow's rest place in head units does not depend on the
head scale; its expression travel does (``BROW_HEIGHT_TRAVEL`` is a view-box
length), which is why a small head's brows reach higher up its forehead.

A surprised brow reaches about three head units above its rest, less on a
bigger head; a band drawn across the forehead is lifted clear of it:

>>> round(BROW_REST_TOP, 1)
22.8
>>> [round(min(brow_range(head_scale=s)["front"].values()), 1) for s in (1.0, 1.7)]
[19.5, 20.3]
>>> seat_above_brows({"front": '<rect x="20" y="20" width="40" height="4"/>'}, head_scale=1.0)
Seat(transform='translate(0 -5.47)', covers=False)
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from an.characters.schema import FACE_OFFSETS, HEAD_ANCHOR, REFERENCE_HEAD_HEIGHT

__all__ = [
    "BROW_CANVAS",
    "BROW_STROKE",
    "BROWS_FEATURE",
    "HAT_BROW_CLEARANCE",
    "HAT_CROWN_MIN_Y",
    "HAT_MIN_FLATTEN",
    "HEAD_ART_SIZE",
    "OCCLUDABLE_FEATURES",
    "Seat",
    "brow_affordance",
    "brow_path_d",
    "brow_range",
    "ink_columns",
    "seat_above_brows",
]

# -----------------------------------------------------------------------------
# The drawings
# -----------------------------------------------------------------------------

#: The offline head's drawing is this many units square (its ``viewBox``).
HEAD_ART_SIZE: float = 80.0
#: The factory's brow drawing: its canvas (view-box units at head scale 1),
#: the stroke, and how far each end tilts from the level.
BROW_CANVAS: tuple[int, int] = (80, 24)
BROW_STROKE: float = 6.0
BROW_TILT: float = 4.0

#: The face features a drawing can be recorded as covering (``occluded`` keys).
BROWS_FEATURE: str = "brows"
OCCLUDABLE_FEATURES: tuple[str, ...] = (BROWS_FEATURE,)

#: Head units left between a hat's lowest ink and the brows' highest reach —
#: about the outline's width, so a raised brow never touches the brim's line.
HAT_BROW_CLEARANCE: float = 1.0
#: How high a lifted hat's crown may go (head units from the drawing's top
#: edge): above it the crown would be clipped by the head's canvas.
HAT_CROWN_MIN_Y: float = 0.5
#: The flattest a hat is drawn (its height kept, as a fraction) to seat it
#: above the brows; past it the hat keeps this shape and the overlap is recorded.
HAT_MIN_FLATTEN: float = 0.6

#: Samples per drawn segment, per head unit of its length (at least 8).
_SAMPLES_PER_UNIT: float = 2.0
_MIN_SAMPLES: int = 8
#: The four-arc circle approximation's handle length (a unit circle).
_KAPPA: float = 0.5522847498


def brow_path_d(side: str) -> str:
    """The path of the factory's brow on ``side`` (``l`` or ``r``) in its canvas.

    >>> brow_path_d("l")
    'M 8 16 Q 40 4 72 8'
    """
    tilt = BROW_TILT if side == "l" else -BROW_TILT
    w, h = BROW_CANVAS
    mid = h / 2
    return f"M 8 {mid + tilt:g} Q {w / 2:g} 4 {w - 8:g} {mid - tilt:g}"


#: Head units per view-box unit at head scale 1 (the head art is
#: REFERENCE_HEAD_HEIGHT tall).
_UNIT: float = REFERENCE_HEAD_HEIGHT / HEAD_ART_SIZE
#: Where the neck (the head bone) sits in the head's drawing.
_NECK: tuple[float, float] = (HEAD_ANCHOR[0] * HEAD_ART_SIZE, HEAD_ANCHOR[1] * HEAD_ART_SIZE)


def _brow_centre(slot: str) -> tuple[float, float]:
    x, y = FACE_OFFSETS[slot]
    return _NECK[0] + x / _UNIT, _NECK[1] + y / _UNIT


#: The brow's rest place, in head units (the default face layout).
BROW_REST_Y: float = _brow_centre("left_brow")[1]


# -----------------------------------------------------------------------------
# Ink: sampled boundaries, reduced to per-column extents
# -----------------------------------------------------------------------------

#: A sample of ink: a disc ``(x, y, r)`` — a point of an outline, padded by
#: half its stroke.
Disc = tuple[float, float, float]
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_CMD = re.compile(r"[MLQCZmlqcz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _bezier(pts: list[tuple[float, float]], n: int) -> list[tuple[float, float]]:
    out = []
    for i in range(n + 1):
        t = i / n
        p = list(pts)
        while len(p) > 1:
            p = [
                (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                for a, b in zip(p, p[1:])
            ]
        out.append(p[0])
    return out


def _count(pts: list[tuple[float, float]]) -> int:
    length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    return max(_MIN_SAMPLES, int(length * _SAMPLES_PER_UNIT))


def _path_points(d: str) -> list[tuple[float, float]]:
    """Points along an SVG path of absolute ``M L Q C Z`` commands (what the
    factory draws); any other command is refused, never guessed."""
    tokens = _CMD.findall(d)
    if re.sub(r"[\s,]", "", d) != "".join(tokens):
        raise ValueError(f"path {d!r}: only absolute M, L, Q, C and Z are measured")
    out: list[tuple[float, float]] = []
    cur = start = (0.0, 0.0)
    i, cmd = 0, ""
    arity = {"M": 2, "L": 2, "Q": 4, "C": 6}
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                out += _bezier([cur, start], _count([cur, start]))
                cur = start
                continue
        if cmd not in arity:
            raise ValueError(f"path {d!r}: only absolute M, L, Q, C and Z are measured")
        nums = [float(t) for t in tokens[i : i + arity[cmd]]]
        i += arity[cmd]
        pts = [(nums[k], nums[k + 1]) for k in range(0, len(nums), 2)]
        if cmd == "M":
            cur = start = pts[0]
            out.append(cur)
            cmd = "L"  # implicit lineto after a moveto
            continue
        ctrl = [cur, *pts]
        out += _bezier(ctrl, _count(ctrl))
        cur = pts[-1]
    return out


def _ellipse_points(cx: float, cy: float, rx: float, ry: float) -> list[tuple[float, float]]:
    n = max(_MIN_SAMPLES * 4, int(2 * math.pi * max(rx, ry) * _SAMPLES_PER_UNIT))
    return [
        (cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def _rect_points(x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
    out: list[tuple[float, float]] = []
    for a, b in zip(corners, corners[1:]):
        out += _bezier([a, b], _count([a, b]))
    return out


def _f(el: ET.Element, name: str, default: float = 0.0) -> float:
    return float(el.get(name, default))


def ink_discs(fragment: str) -> list[Disc]:
    """The ink of an SVG fragment (paths, ellipses, circles, rects) as boundary discs.

    A filled shape's lowest and highest ink lie on its outline, so the outline
    is all a column extent needs; a stroke pads it by half its width.

    >>> [d[2] for d in ink_discs('<rect x="0" y="0" width="2" height="2" stroke="#000" stroke-width="2"/>')][:1]
    [1.0]
    """
    root = ET.fromstring(f'<g xmlns="http://www.w3.org/2000/svg">{fragment}</g>')
    out: list[Disc] = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "path":
            pts = _path_points(el.get("d", ""))
        elif tag == "ellipse":
            pts = _ellipse_points(_f(el, "cx"), _f(el, "cy"), _f(el, "rx"), _f(el, "ry"))
        elif tag == "circle":
            r = _f(el, "r")
            pts = _ellipse_points(_f(el, "cx"), _f(el, "cy"), r, r)
        elif tag == "rect":
            pts = _rect_points(_f(el, "x"), _f(el, "y"), _f(el, "width"), _f(el, "height"))
        else:
            continue
        stroked = el.get("stroke") not in (None, "none")
        pad = _f(el, "stroke-width", 1.0) / 2 if stroked else 0.0
        out += [(x, y, pad) for x, y in pts]
    return out


def ink_columns(discs: Iterable[Disc]) -> dict[int, tuple[float, float]]:
    """``{column: (top, bottom)}`` of ink, per head-unit column (``round(x)``).

    >>> ink_columns([(10.2, 5.0, 0.0), (10.4, 7.0, 0.0)])
    {10: (5.0, 7.0)}
    """
    cols: dict[int, tuple[float, float]] = {}
    for x, y, r in discs:
        for c in {round(x), *range(math.ceil(x - r), math.floor(x + r) + 1)}:
            dy = math.sqrt(max(r * r - (c - x) ** 2, 0.0))
            top, bottom = cols.get(c, (math.inf, -math.inf))
            cols[c] = (min(top, y - dy), max(bottom, y + dy))
    return cols


# -----------------------------------------------------------------------------
# The brows' acting range
# -----------------------------------------------------------------------------

#: The views that show a brow (the back view hides the face).
_VIEWS_WITH_BROWS: tuple[str, ...] = ("front", "three_quarter", "side")


def _brow_ink(side: str) -> list[Disc]:
    """The factory brow's ink about its own centre, in view-box units at head scale 1."""
    w, h = BROW_CANVAS
    return [
        (x - w / 2, y - h / 2, BROW_STROKE / 2)
        for x, y in _path_points(brow_path_d(side))
    ]


def _brow_gains() -> dict[str, dict[str, tuple[str, float]]]:
    """``{slot: {property: (axis, gain)}}`` from the default expression binding."""
    from an.characters.schema import CharacterDescriptor
    from an.expression.binding import ChannelBinding, default_binding

    out: dict[str, dict[str, tuple[str, float]]] = {}
    for b in default_binding(CharacterDescriptor(name="_brow_range")):
        if isinstance(b, ChannelBinding) and b.slot in ("left_brow", "right_brow"):
            out.setdefault(b.slot, {})[b.property] = (b.axis, b.gain)
    return out


def brow_range(
    *,
    head_scale: float = 1.0,
    views: Iterable[str] = _VIEWS_WITH_BROWS,
    presets: Iterable[str] | None = None,
) -> dict[str, dict[int, float]]:
    """``{view: {column: top}}``: the highest the brows' ink reaches, per head-unit column.

    Every shipped expression preset (or ``presets``), at full intensity, posed
    through the default binding on each brow the view shows (its turnaround
    pose: shifted, narrowed, or hidden) — the region a cover must stay above
    for the presets to read.
    """
    from an.characters.factory import view_poses
    from an.expression.presets import PRESETS

    s = float(head_scale)
    gains = _brow_gains()
    names = list(PRESETS) if presets is None else list(presets)
    poses = view_poses(head_scale=s)
    out: dict[str, dict[int, float]] = {}
    for view in views:
        discs: list[Disc] = []
        for slot, side in (("left_brow", "l"), ("right_brow", "r")):
            pose = poses.get(view, {}).get(slot)
            if pose is not None and pose.alpha == 0.0:
                continue
            shift = (pose.x if pose is not None else 0.0) / (_UNIT * s)
            squash = pose.scale_x if pose is not None else 1.0
            cx, cy = _brow_centre(slot)
            ink = _brow_ink(side)
            for name in names:
                axes = PRESETS[name].axes
                ax, gy = gains[slot]["y"]
                ar, gr = gains[slot]["rotation"]
                dy = float(axes.get(ax, 0.0)) * gy / (_UNIT * s)
                th = float(axes.get(ar, 0.0)) * gr
                c, sn = math.cos(th), math.sin(th)
                for x, y, r in ink:
                    x *= squash  # the pose's scale is local: before the rotation
                    rx, ry = x * c - y * sn, x * sn + y * c  # clockwise, y down
                    discs.append(
                        (cx + shift + rx / _UNIT, cy + dy + ry / _UNIT, r / _UNIT)
                    )
        out[view] = {c: top for c, (top, _) in ink_columns(discs).items()}
    return out


#: How high the brow's ink reaches at rest, in head units.
BROW_REST_TOP: float = BROW_REST_Y + min(y - r for _, y, r in _brow_ink("l")) / _UNIT


# -----------------------------------------------------------------------------
# Seating a hat above the brows
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Seat:
    """Where a hat is drawn: ``transform`` (``None``: where it was drawn) and
    whether it still covers the brows' range there (``covers``)."""

    transform: str | None = None
    covers: bool = False


def _overlap(
    fragments: Mapping[str, list[Disc]],
    reach: Mapping[str, Mapping[int, float]],
    *,
    top: float,
    to_top: float,
    k: float,
    margin: float,
) -> float:
    """How far (head units) the hat's lowest ink dips below the brows' reach
    minus ``margin``, with the hat mapped ``y -> to_top + (y - top) * k``."""
    worst = -math.inf
    for view, discs in fragments.items():
        cols = ink_columns((x, to_top + (y - top) * k, r * k) for x, y, r in discs)
        for c, (_, bottom) in cols.items():
            if c in reach.get(view, {}):
                worst = max(worst, bottom + margin - reach[view][c])
    return worst


def seat_above_brows(
    fragments: Mapping[str, str],
    *,
    head_scale: float = 1.0,
    clearance: float = HAT_BROW_CLEARANCE,
    crown_min_y: float = HAT_CROWN_MIN_Y,
    min_flatten: float = HAT_MIN_FLATTEN,
) -> Seat:
    """Seat a hat, drawn as ``{view: svg fragment}`` in head units, above the brows' range.

    No transform when it already clears them by ``clearance``. Else it is
    lifted — as far as its crown may go (``crown_min_y``) — and, if that is
    not enough, flattened toward its crown, never below ``min_flatten`` of its
    height; one transform for every view. ``covers`` says the seat found still
    overlaps the range (it never claims a clearance it did not measure).
    """
    discs = {v: ink_discs(f) for v, f in fragments.items() if f}
    if not any(discs.values()):
        return Seat()
    reach = brow_range(head_scale=head_scale, views=[v for v in discs])
    top = min(y - r for ds in discs.values() for _, y, r in ds)

    def overlap(to_top: float, k: float, margin: float = clearance) -> float:
        return _overlap(discs, reach, top=top, to_top=to_top, k=k, margin=margin)

    need = overlap(top, 1.0)
    if need <= 0:
        return Seat()
    lift = min(need, max(top - crown_min_y, 0.0))
    lift = math.ceil(lift * 100) / 100
    if overlap(top - lift, 1.0) <= 0:
        return Seat(f"translate(0 {-lift:g})")
    to_top = top - lift
    lo, hi = min_flatten, 1.0
    if overlap(to_top, lo) > 0:
        k = lo
    else:
        for _ in range(30):  # bisect the gentlest flattening that clears
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if overlap(to_top, mid) <= 0 else (lo, mid)
        k = math.floor(lo * 1000) / 1000
    transform = (
        f"translate(0 {to_top:.3f}) scale(1 {k:g}) translate(0 {-top:.3f})"
    )
    return Seat(transform, covers=overlap(to_top, k, margin=0.0) > 0)


# -----------------------------------------------------------------------------
# The capability
# -----------------------------------------------------------------------------

def brow_affordance(desc: Any, drawn: Mapping[str, Any]) -> dict[str, Any] | None:
    """``face.brows``'s params for a descriptor whose drawn slots are ``drawn``, or ``None``.

    Afforded when the face is an overlay (``face_overlay``), both slots the
    expression binding moves have art, and the descriptor records nothing
    over the brows (``occluded``). The brow slots' names are the binding's,
    so the capability and the solver cannot disagree about which slots act.

    >>> from an.characters.schema import CharacterDescriptor
    >>> d = CharacterDescriptor(name="c")
    >>> brow_affordance(d, {"left_brow": {"brow_l"}, "right_brow": {"brow_r"}})
    {'slots': ['left_brow', 'right_brow']}
    >>> d.occluded = {"brows": "a helmet"}
    >>> brow_affordance(d, {"left_brow": {"brow_l"}, "right_brow": {"brow_r"}}) is None
    True
    """
    from an.expression.binding import LEFT_BROW_SLOT, RIGHT_BROW_SLOT

    slots = [LEFT_BROW_SLOT, RIGHT_BROW_SLOT]
    if not getattr(desc, "face_overlay", True) or not all(s in drawn for s in slots):
        return None
    if BROWS_FEATURE in (getattr(desc, "occluded", None) or {}):
        return None
    return {"slots": slots}
