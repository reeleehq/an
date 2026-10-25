"""The hold layer: what carries each item, frame by frame, and the hands that move it (an#502, catalogue A4).

The verbs are :mod:`an.ir.holds` (``grasp``, ``place``, ``release``,
``handover``, ``swap``). This module runs them inside the ``solve`` compile
pass (:mod:`an.stage.solve`), because a hold needs the SOLVED hand at every
frame: the hand is a body of the shot's puppet, the item is not.

**The model.** Every item is, at each instant, in exactly one *holder's
frame*: a body's point (a hand, a figurine's socket), the ground, a point of
the stage, or none (in flight). A change of holder is a reframe that keeps the
item's world pose at that instant (``keep: world``, an#502): the item's local
transform in the new holder's frame is computed so the picture is continuous,
so there is never a slide or a jump. What makes the change look *handled* is
that the hand first goes where the item is:

- **Reach and retract.** A gesture drives its hand's point (an end effector:
  ``stu@hand_r``, ``stu/arm_r``) along a minimum-jerk path from where the shot
  would have it to the goal (the item's grip; for a ``place``, the point that
  puts the item's contact point on its target), and back, as a ``pull`` row of
  the solver whose goal moves frame by frame. The arm follows by the solver's
  joints. The item changes holder at the frame the hand arrives.
- **Lean.** When the goal is out of the arm's reach, the body the arm hangs
  from (the chain's root: a torso, a crane's base) turns about its own pivot
  by the least angle that brings the goal in reach (closed form, the two-link
  triangle), up to ``lean`` degrees, rising with the reach and falling with
  the retract, and every part riding on it turns with it (the head, the other
  arm). A reach that still cannot arrive is reported (``unreachable_hold``,
  with how far it stays short and which way to move the carrier).
- **Carry.** A held item's world transform is its holder's times a fixed local
  transform, so it turns, mirrors and squashes with the hand (a character
  turning round carries the musket round with it).
- **Place.** Over a ``place``'s reach the item keeps its point in the hand and
  turns from how it is carried to how it will rest (a wrist), so it arrives
  aligned with a socket's frame or lying on the ground at its rest angle, its
  lowest INK point at floor height (the texture's alpha, not its box, so a
  carved part with a transparent margin does not float).
- **Release.** A parabola under gravity (the shot's or the style pack's, else
  :data:`DFLT_FALL_GRAVITY`) from the velocity the hand gave it, turning to its
  rest angle on the way down, landing on the ground exactly; ``onto:
  ground@x`` solves the throw that lands there on an arc ``arc`` px high.

**Two passes.** The goals and the leans are planned from a solve without the
gestures (the shot as authored), the shot is solved with them, and the plan is
made again from that solve (an item carried after a grasp hangs where the
grasp really put it) before the final solve. :data:`HOLD_PLAN_PASSES` says how
many times.

The item's channels (``x``, ``y``, ``rotation``, ``scale_x``, ``scale_y`` of its
entity node) are emitted with the puppet's in the entity's ``__solve__`` clip;
``meta.extensions.solve.holds`` records each gesture (its contact instant,
where the hand arrived, how far it stayed short, its lean) and each item's
holders, what ``an validate``'s hold checks read (:mod:`an.verify.holds`).

>>> from an.ir.schema import Shot
>>> declares_holds(Shot(id="s"))
False
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from an.ir.holds import GESTURE_KINDS, GROUND, HOLD_ACTION_KINDS
from an.stage.compile import CutoutCompileError
from an.stage.solve import (
    REACH_SOURCE,
    WORLD_REF,
    Affine,
    JointRow,
    Located,
    Puppet,
    Run,
    _IDENTITY,
    _apply,
    _compose,
    _decompose,
    _invert,
    _local_box,
    _numbers,
    _pivot,
    _wrap,
)

__all__ = [
    "HOLD_VERSION",
    "HOLDS_REPORT",
    "ON_OVERRIDE",
    "GRASP_TOLERANCE_PX",
    "DFLT_FALL_GRAVITY",
    "HOLD_PLAN_PASSES",
    "HoldError",
    "HoldVerb",
    "HoldDeclarations",
    "declares_holds",
    "hold_declarations",
    "solve_holds",
    "ink_box",
    "ink_points",
]

#: The hold layer's version, in the shot-cache key (``solve_knobs``): bump it
#: when the same declarations can compile to other keys.
HOLD_VERSION: str = "1"
#: The key of the hold report inside ``meta.extensions.solve``.
HOLDS_REPORT: str = "holds"
#: ``AssetRef.overrides`` key: what holds an item when the shot opens
#: (``ground``, a body's point, ``world@x,y``).
ON_OVERRIDE: str = "held_by"
#: A reach that ends farther than this from its goal did not arrive (scene px).
GRASP_TOLERANCE_PX: float = 0.5
#: An item put down this close to the floor is on it (scene px); farther, it
#: falls the rest of the way.
SUPPORT_TOLERANCE_PX: float = 1.0
#: An item first taken this far above the ground or less is taken to lie on the
#: floor: the check asks for ``overrides: {held_by: ground}`` (scene px).
FLOAT_BAND_PX: float = 80.0
#: Gravity for a released item when neither the shot nor the style pack says
#: (scene px / s², down the screen).
DFLT_FALL_GRAVITY: float = 980.0
#: How many times the gestures are planned (each from the solve the previous
#: plan made).
HOLD_PLAN_PASSES: int = 2
#: Rounds of the fixed point between gestures that bend the same body at once.
LEAN_ROUNDS: int = 8
#: Samples of a lean's range searched when no angle brings the goal in reach.
LEAN_SAMPLES: int = 721
#: The alpha (0-255) above which a pixel is ink, not margin.
INK_ALPHA: int = 16
_EPS: float = 1e-9
#: The clip a hold's channels join (the solve's own, :data:`an.stage.solve.SOLVE_CLIP_PREFIX`).
ITEM_CHANNELS: tuple[str, ...] = ("x", "y", "rotation", "scale_x", "scale_y")


class HoldError(CutoutCompileError):
    """The holds of a shot do not make sense (a hand puts down what it does not
    hold, a socket gets a second item, one hand does two things at once).

    ``problems`` lists each one as ``(where, message)``, ``where`` relative to
    the shot: what ``an validate``'s ``hold_conflict`` check reports.
    """

    def __init__(self, message: str, problems: Sequence[tuple[str, str]]) -> None:
        super().__init__(message)
        self.problems = list(problems)


# -----------------------------------------------------------------------------
# What a shot declares
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class HoldVerb:
    """A flattened hold verb (a ``swap`` is its ``grasp`` and its ``place``)."""

    action: Any
    start: float
    end: float
    where: str


@dataclass
class HoldDeclarations:
    """The hold verbs of a shot and its ``held_by`` overrides, read without geometry.

    ``refs`` are the holder points to resolve as ``(ref, where, side)`` (side
    ``hand``: a moving point, ``socket``: one that holds still); ``items`` the
    entities held (``id -> where first named``); ``movers`` the entities that
    move a hand (they are solved; a holder that never moves is held fixed).
    """

    verbs: list[HoldVerb] = field(default_factory=list)
    initial: dict[str, tuple[str, str]] = field(default_factory=dict)
    refs: list[tuple[str, str, str]] = field(default_factory=list)
    items: dict[str, str] = field(default_factory=dict)
    movers: set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not self.verbs and not self.initial


def declares_holds(shot: Any) -> bool:
    """Whether ``shot`` has a hold verb or an item ``held_by`` something.

    >>> from an.ir.schema import Shot
    >>> cup = {"kind": "prop", "id": "cup", "store": "props", "ref": "cup", "overrides": {"held_by": "ground"}}
    >>> declares_holds(Shot(id="s", entities=[cup]))
    True
    """
    from an.ir.compose import iter_actions

    if any(e.overrides and ON_OVERRIDE in e.overrides for e in shot.entities):
        return True
    return any(
        getattr(node, "kind", None) in HOLD_ACTION_KINDS
        for action in shot.actions
        for node in iter_actions(action)
    )


def _is_place_target(ref: str) -> bool:
    """``ground``, ``ground@x`` and ``world@x,y`` are places, not holders."""
    head = ref.partition("@")[0]
    return head in (GROUND, WORLD_REF)


def _entity(ref: str) -> str:
    return ref.partition("@")[0].split("/", 1)[0]


def _item_id(ref: str) -> str:
    return ref.partition("@")[0]


def hold_declarations(shot: Any, *, play_extent: Any = None) -> HoldDeclarations:
    """The hold verbs of ``shot`` flattened to shot time, its ``held_by`` overrides,
    the holder points they name and who moves a hand."""
    from an.ir.compose import flatten

    out = HoldDeclarations()
    for i, entity in enumerate(shot.entities):
        on = (entity.overrides or {}).get(ON_OVERRIDE)
        if on is None:
            continue
        where = f"entities/{i}/overrides/{ON_OVERRIDE}"
        out.initial[entity.id] = (str(on), where)
        out.items.setdefault(entity.id, where)
        if not _is_place_target(str(on)):
            out.refs.append((str(on), where, "socket"))
    for k, action in enumerate(shot.actions):
        for flat in flatten(action, play_extent=play_extent):
            kind = getattr(flat.action, "kind", None)
            if kind not in HOLD_ACTION_KINDS:
                continue
            where = f"actions/{k}"
            out.verbs.append(HoldVerb(flat.action, flat.start, flat.end, where))
            a = flat.action
            out.items.setdefault(_item_id(a.item), where)
            if kind == "grasp":
                out.refs.append((a.by, where, "hand"))
            elif kind in ("place", "handover"):
                if a.by is not None:
                    out.refs.append((a.by, where, "hand"))
                target = a.onto if kind == "place" else a.to
                moving = kind == "handover" and a.meet < 1.0
                if not _is_place_target(target):
                    out.refs.append((target, where, "hand" if moving else "socket"))
    out.verbs.sort(key=lambda v: (v.start, v.end))
    # Who moves a hand: every explicit `by`, a receiver that reaches, and the
    # holder of an item a place, handover or release gives up without a `by`.
    holder: dict[str, str | None] = {
        item: (on if not _is_place_target(on) else None)
        for item, (on, _w) in out.initial.items()
    }
    for v in _by_instant(out.verbs):
        a, item = v.action, _item_id(v.action.item)
        if a.kind == "grasp":
            out.movers.add(_entity(a.by))
            holder[item] = a.by
            continue
        giver = a.by if getattr(a, "by", None) is not None else holder.get(item)
        if giver is not None:
            out.movers.add(_entity(giver))
        if a.kind == "release":
            holder[item] = None
        elif a.kind == "place":
            holder[item] = None if _is_place_target(a.onto) else a.onto
        else:  # handover
            if a.meet < 1.0:
                out.movers.add(_entity(a.to))
            holder[item] = a.to
    return out


def _by_instant(verbs: Sequence[HoldVerb]) -> list[HoldVerb]:
    """Verbs in the order their holds change: a gesture at its contact, a release at its instant."""

    def instant(v: HoldVerb) -> tuple[float, int, float]:
        a = v.action
        if a.kind == "release":
            # A hand that lets go at the instant another takes hold: the
            # release comes first, so the other hand catches it.
            return (v.start, 0, v.start)
        return (v.start + float(a.reach), 1, v.start)

    return sorted(verbs, key=instant)


# -----------------------------------------------------------------------------
# Geometry
# -----------------------------------------------------------------------------

#: A linear part as ``(theta, signed scale_x, scale_y)``: ``R(theta) diag(sx, sy)``.
Lin = tuple[float, float, float]


def _lin_of(m: Affine) -> Lin:
    theta, sx, sy, mirrored = _decompose(m)
    return (theta, -sx if mirrored else sx, sy)


def _lin_matrix(lin: Lin) -> Affine:
    theta, sx, sy = lin
    c, s = math.cos(theta), math.sin(theta)
    return (c * sx, s * sx, -s * sy, c * sy, 0.0, 0.0)


def _translate(x: float, y: float) -> Affine:
    return (1.0, 0.0, 0.0, 1.0, x, y)


def _placed(point: tuple[float, float], lin: Lin, local: tuple[float, float]) -> Affine:
    """The transform with linear part ``lin`` that puts ``local`` at ``point``."""
    return _compose(
        _translate(*point), _compose(_lin_matrix(lin), _translate(-local[0], -local[1]))
    )


def _blend_lin(a: Lin, b: Lin, f: float) -> Lin:
    return (
        a[0] + _wrap(b[0] - a[0]) * f,
        a[1] + (b[1] - a[1]) * f,
        a[2] + (b[2] - a[2]) * f,
    )


def _min_jerk(u: float) -> float:
    """The minimum-jerk profile (smootherstep): how far along a reach is at ``u``."""
    u = max(0.0, min(1.0, u))
    return u * u * u * (10.0 + u * (-15.0 + 6.0 * u))


def _lerp(
    a: tuple[float, float], b: tuple[float, float], f: float
) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def _rotate_about(
    p: tuple[float, float], centre: tuple[float, float], angle: float
) -> tuple[float, float]:
    c, s = math.cos(angle), math.sin(angle)
    dx, dy = p[0] - centre[0], p[1] - centre[1]
    return (centre[0] + c * dx - s * dy, centre[1] + s * dx + c * dy)


def _lowest(m: Affine, corners: Sequence[tuple[float, float]]) -> float:
    """The lowest (largest ``y``) of ``corners`` under ``m``."""
    return max(_apply(m, c)[1] for c in corners)


# -----------------------------------------------------------------------------
# Ink: where a part's art really is inside its box
# -----------------------------------------------------------------------------


#: The most hull points kept per part (a drawing's outline, thinned evenly).
INK_HULL_POINTS: int = 64


@lru_cache(maxsize=512)
def _ink_hull(
    path: str, mtime_ns: int, size: int
) -> tuple[tuple[tuple[float, float], ...], float, float] | None:
    """The convex hull of a raster's ink (alpha above :data:`INK_ALPHA`) as
    fractions of the image, and its size; ``None`` when it cannot be read.

    A hull, not a box: a musket drawn on the diagonal has a nearly square box,
    and turned to lie flat that box reaches far below the musket."""
    try:
        import numpy as np
        from PIL import Image

        with Image.open(path) as im:
            im = im.convert("RGBA")
            w, h = im.size
            alpha = np.asarray(im.getchannel("A")) > INK_ALPHA
    except Exception:  # noqa: BLE001 - unreadable art keeps its box
        return None
    rows = np.flatnonzero(alpha.any(axis=1))
    if not len(rows) or not w or not h:
        return None
    pts: list[tuple[float, float]] = []
    for y in rows:
        xs = np.flatnonzero(alpha[y])
        x0, x1 = float(xs[0]), float(xs[-1]) + 1.0
        pts.extend(
            [(x0, float(y)), (x1, float(y)), (x0, float(y) + 1.0), (x1, float(y) + 1.0)]
        )
    hull = _convex_hull(pts)
    if len(hull) > INK_HULL_POINTS:
        step = len(hull) / INK_HULL_POINTS
        hull = [hull[int(i * step)] for i in range(INK_HULL_POINTS)]
    return tuple((x / w, y / h) for x, y in hull), float(w), float(h)


def _convex_hull(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain.

    >>> _convex_hull([(0, 0), (2, 0), (1, 1), (2, 2), (0, 2)])
    [(0, 0), (2, 0), (2, 2), (0, 2)]
    """
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def ink_points(
    doc: Any, node: Any, mall: Mapping[str, Any] | None
) -> list[tuple[float, float]]:
    """A node's drawn ink as points in its own frame: the corners of the box
    its art is fitted into, or, for a raster the store can read, the convex
    hull of its painted pixels inside that box (so the lowest point of a part
    turned any way is the lowest painted pixel, not a corner of its margin).

    >>> from an.stage.serialize import NodeJSON, VisualJSON
    >>> ink_points(None, NodeJSON(name="n", visual=VisualJSON(width=10, height=20)), None)
    [(-5.0, -10.0), (5.0, -10.0), (-5.0, 10.0), (5.0, 10.0)]
    """
    box = _local_box(node)
    corners = _corners(box)
    v = node.visual
    if v is None or doc is None or mall is None or not (v.width and v.height):
        return corners
    alias = v.asset_id or v.texture_id
    textures = getattr(getattr(doc, "assets", None), "textures", None) or {}
    asset = textures.get(alias) if alias else None
    src = getattr(asset, "src", None) if asset is not None else None
    if not src or src.endswith(".svg") or ".svg?" in src:
        return corners
    try:
        from an.stage.render import texture_source

        path, _why = texture_source(src, mall)
    except Exception:  # noqa: BLE001
        return corners
    if path is None or not path.is_file():
        return corners
    stat = path.stat()
    ink = _ink_hull(str(path), stat.st_mtime_ns, stat.st_size)
    if ink is None:
        return corners
    hull, iw, ih = ink
    w, h = float(v.width), float(v.height)
    if v.fit == "contain":
        k = min(w / iw, h / ih)
        dw, dh = iw * k, ih * k
    else:
        dw, dh = w, h
    left, top = -float(v.anchor_x) * dw, -float(v.anchor_y) * dh
    return [(left + u * dw, top + q * dh) for u, q in hull]


def ink_box(
    doc: Any, node: Any, mall: Mapping[str, Any] | None
) -> tuple[float, float, float, float]:
    """The box round a node's ink (:func:`ink_points`), in its own frame.

    >>> from an.stage.serialize import NodeJSON, VisualJSON
    >>> ink_box(None, NodeJSON(name="n", visual=VisualJSON(width=10, height=20)), None)
    (-5.0, -10.0, 10.0, 20.0)
    """
    pts = ink_points(doc, node, mall)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _corners(box: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    left, top, w, h = box
    return [(left, top), (left + w, top), (left, top + h), (left + w, top + h)]


# -----------------------------------------------------------------------------
# Items and holders
# -----------------------------------------------------------------------------


@dataclass
class ItemInfo:
    """An item: its entity node, its ink corners and its points, in its own frame."""

    id: str
    parent: str
    pivot: tuple[float, float]
    corners: list[tuple[float, float]]
    box: tuple[float, float, float, float]
    centre: tuple[float, float]
    grip: tuple[float, float]
    anchors: dict[str, tuple[float, float]]
    scale: tuple[float, float]  # |scale| as staged: what it keeps in a socket


@dataclass(frozen=True)
class Holder:
    """What holds an item: a body's point, the ground, a stage point, or nothing."""

    kind: str  # "body" | "ground" | "world" | "authored" | "air"
    ref: str = ""
    body: str | None = None
    local: tuple[float, float] | None = None
    frame: Affine | None = None
    entity: str | None = None
    x: float | None = None  # ground@x, world@x,y
    y: float | None = None
    #: ``hand`` (a part the solve moves: one item at a time, one gesture at a
    #: time, whatever point of it is named) or ``socket`` (a point of a part
    #: held still: each point holds its own item).
    role: str = "socket"

    def key(self) -> tuple:
        """Who this holder is: a hand is its part, a socket its point."""
        if self.kind == "body":
            if self.role == "hand":
                return ("body", self.body)
            return ("body", self.body, round(self.local[0], 6), round(self.local[1], 6))
        return (self.kind,)

    def text(self) -> str:
        return self.ref or self.kind


@dataclass
class Gesture:
    """One hand's reach and retract for one change of hold."""

    index: int
    kind: str  # "grasp" | "place" | "give" | "take"
    item: str
    hand: Holder
    start: float
    contact: float
    end: float
    lean: float  # radians, the most the chain's root may turn
    where: str
    ref: str  # how the scene names the hand
    target: Holder | None = None  # place/give: where the item goes
    rotation: float | None = None
    point: tuple[float, float] | None = (
        None  # the item's point: its grip, or its contact point
    )
    meet: float = 1.0
    partner: int | None = None
    #: A taking hand turns the item, over its retract, to how it holds things.
    align: bool = False
    #: Gestures that bend the same body the other way while this one runs.
    against: tuple[int, ...] = ()
    # frame indices (contact snapped to the grid)
    k0: int = 0
    kc: int = 0
    k1: int = 0
    # planned
    chain: tuple[str, ...] = ()
    recruit: str | None = None
    delta: float = 0.0
    goal: tuple[float, float] | None = None
    # measured on the final solve
    gap: float = 0.0
    arrived: tuple[float, float] | None = None
    reach_gap: float = 0.0


#: The order in which an item's holds change, ever increasing: what breaks a
#: tie between two changes at one frame (a release, then the catch).
_EVENT_SEQ = itertools.count()


@dataclass
class Event:
    """A change of what holds an item, at frame ``k``; ``seq`` is the order the
    schedule decided it in (a tie at one frame keeps that order)."""

    k: int
    kind: str  # "take" | "settle" | "carry" | "put" | "drop"
    gesture: Gesture | None = None
    release: Any = None
    where: str = ""
    seq: int = field(default_factory=lambda: next(_EVENT_SEQ))


@dataclass
class _Ctx:
    doc: Any
    shot: Any
    mall: Mapping[str, Any]
    puppet: Puppet
    times: list[float]
    items: dict[str, ItemInfo]
    gestures: list[Gesture]
    events: dict[str, list[Event]]
    initial: dict[str, Holder]
    gravity: tuple[float, float] | None
    ground: float | None
    problems: list[tuple[str, str]]
    warnings: list[dict[str, Any]]


def _frame_at(times: Sequence[float], t: float) -> int:
    """The first frame at or after ``t``."""
    for k, tk in enumerate(times):
        if tk >= t - 1e-7:
            return k
    return len(times) - 1


def _nearest_frame(times: Sequence[float], t: float) -> int:
    return min(range(len(times)), key=lambda k: (abs(times[k] - t), k))


def _item_info(
    doc: Any,
    shot: Any,
    mall: Mapping[str, Any],
    nodes: Mapping[str, Any],
    item: str,
    vocab: Any,
) -> ItemInfo | None:
    from an.stage.solve import _parent_path, _rig_of, _world_matrices

    if item not in nodes:
        return None
    paths = [p for p in nodes if p == item or p.startswith(item + "/")]
    rest = _world_matrices(doc, paths, None, nodes)
    inv = _invert(rest[item])
    corners: list[tuple[float, float]] = []
    for p in paths:
        node = nodes[p]
        if node.visual is None or not (node.visual.width and node.visual.height):
            continue
        local = _compose(inv, rest[p])
        corners.extend(_apply(local, c) for c in ink_points(doc, node, mall))
    if not corners:
        corners = _corners(_local_box(nodes[item]))
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    box = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    centre = (box[0] + box[2] / 2.0, box[1] + box[3] / 2.0)
    anchors: dict[str, tuple[float, float]] = {}
    entity = next((e for e in shot.entities if e.id == item), None)
    rig = _rig_of(entity, mall, nodes, vocab) if entity is not None else None
    if rig is not None:
        for bone, anchor in rig.anchors.items():
            if anchor.on is None:
                anchors[bone] = anchor.offset
            else:
                slot_path = f"{item}/{rig.bodies.get(anchor.on, anchor.on)}"
                if slot_path in rest:
                    anchors[bone] = _apply(
                        _compose(inv, rest[slot_path]), anchor.offset
                    )
    pivot = _pivot(nodes[item])
    grip = anchors.get("grip", pivot)
    _theta, sx, sy, _m = _decompose(rest[item])
    return ItemInfo(
        id=item,
        parent=_parent_path(item, nodes),
        pivot=pivot,
        corners=corners,
        box=box,
        centre=centre,
        grip=grip,
        anchors=anchors,
        scale=(sx, sy),
    )


def _item_point(
    info: ItemInfo,
    ref: str,
    *,
    where: str,
    problems: list,
    default: tuple[float, float] | None = None,
) -> tuple[float, float] | None:
    """``item@<bone>`` or ``item@u,v`` (a fraction of its ink box) in the item's
    frame; no ``@``: ``default`` (its grip)."""
    _head, _, at = ref.partition("@")
    if not at:
        return info.grip if default is None else default
    xy = _numbers(at)
    if xy is not None:
        left, top, w, h = info.box
        return (left + xy[0] * w, top + xy[1] * h)
    if at in info.anchors:
        return info.anchors[at]
    problems.append(
        (
            where,
            f"{ref!r}: {at!r} is not a bone of {info.id!r} (bones: {sorted(info.anchors)}) nor a fraction `u,v`",
        )
    )
    return None


def _holder(ctx_puppet: Puppet, ref: str, side: str) -> Holder | None:
    found = ctx_puppet.located.get((ref, side))
    if not isinstance(found, Located):
        return None
    return Holder(
        "body",
        ref=ref,
        body=found.body,
        local=found.local,
        frame=found.frame,
        entity=_entity(ref),
        # A part the solve may move (an arm) is a hand; one held where it is
        # put (a root, a figurine that never gestures) is a socket.
        role="socket" if found.body in ctx_puppet.held else "hand",
    )


def _place_holder(ref: str, *, where: str, problems: list) -> Holder | None:
    head, _, at = ref.partition("@")
    if head == GROUND:
        if not at:
            return Holder("ground", ref=ref)
        try:
            return Holder("ground", ref=ref, x=float(at))
        except ValueError:
            problems.append(
                (where, f"{ref!r}: a place on the ground is `ground` or `ground@x`")
            )
            return None
    xy = _numbers(at)
    if xy is None:
        problems.append((where, f"{ref!r}: a stage point is `world@x,y`"))
        return None
    return Holder("world", ref=ref, x=xy[0], y=xy[1])


# -----------------------------------------------------------------------------
# The schedule: gestures and events, checked
# -----------------------------------------------------------------------------


def _schedule(
    doc: Any,
    shot: Any,
    mall: Mapping[str, Any],
    puppet: Puppet,
    decl: HoldDeclarations,
    times: list[float],
    *,
    vocab: Any,
) -> _Ctx:
    nodes = puppet.nodes
    problems: list[tuple[str, str]] = []
    entities = {e.id for e in shot.entities}
    items: dict[str, ItemInfo] = {}
    for item, where in decl.items.items():
        if item not in entities:
            problems.append((where, f"{item!r} is not an entity of this shot"))
            continue
        info = _item_info(doc, shot, mall, nodes, item, vocab)
        if info is None:
            problems.append((where, f"{item!r} draws nothing this shot builds"))
            continue
        items[item] = info
    initial: dict[str, Holder] = {}
    for item, (on, where) in decl.initial.items():
        if item not in items:
            continue
        if _is_place_target(on):
            h = _place_holder(on, where=where, problems=problems)
        else:
            h = _holder(puppet, on, "socket")
        if h is not None:
            initial[item] = h
    gestures: list[Gesture] = []
    events: dict[str, list[Event]] = {item: [] for item in items}
    holder: dict[str, Holder] = {
        item: initial.get(item, Holder("authored")) for item in items
    }
    occupied: dict[tuple, str] = {
        h.key(): item for item, h in holder.items() if h.kind == "body"
    }

    def frames(start: float, contact: float, end: float) -> tuple[int, int, int]:
        k0 = _frame_at(times, start)
        kc = max(k0, _nearest_frame(times, contact))
        k1 = max(kc, _frame_at(times, end))
        return k0, kc, k1

    def new_gesture(
        kind: str, item: str, hand: Holder, v: HoldVerb, ref: str, **kw: Any
    ) -> Gesture:
        a = v.action
        start, contact = v.start, v.start + float(a.reach)
        end = contact + float(a.retract)
        if contact > times[-1] + 1e-6:
            problems.append(
                (
                    v.where,
                    f"the {a.kind} of {item!r} by {ref!r} starts at {start:.2f} s and would reach "
                    f"its goal at {contact:.2f} s, after the shot ends ({times[-1]:.2f} s): start "
                    f"it by {times[-1] - float(a.reach):.2f} s, or shorten its `reach`",
                )
            )
        k0, kc, k1 = frames(start, contact, end)
        g = Gesture(
            len(gestures),
            kind,
            item,
            hand,
            start,
            times[kc],
            end,
            math.radians(float(a.lean)),
            v.where,
            ref,
            k0=k0,
            kc=kc,
            k1=k1,
            **kw,
        )
        gestures.append(g)
        return g

    for v in _by_instant(decl.verbs):
        a = v.action
        item = _item_id(a.item)
        if item not in items:
            continue
        info = items[item]
        current = holder[item]
        if a.kind == "grasp":
            hand = _holder(puppet, a.by, "hand")
            point = _item_point(info, a.item, where=v.where, problems=problems)
            if hand is None or point is None:
                continue
            if current.kind == "body" and current.key() == hand.key():
                problems.append(
                    (
                        v.where,
                        f"{a.by!r} already holds {item!r} when it reaches for it at {v.start:.2f} s",
                    )
                )
                continue
            busy = occupied.get(hand.key())
            if busy is not None and busy != item:
                problems.append(
                    (
                        v.where,
                        f"{a.by!r} still holds {busy!r} at {v.start + float(a.reach):.2f} s: put it down, hand it over or release it before it takes {item!r}",
                    )
                )
                continue
            g = new_gesture(
                "grasp", item, hand, v, a.by, point=point, align=bool(a.align)
            )
            events[item].append(Event(g.kc, "take", g, where=v.where))
            if g.align and g.k1 > g.kc:
                events[item].append(Event(g.k1, "settle", g, where=v.where))
            if current.kind == "body":
                occupied.pop(current.key(), None)
            occupied[hand.key()] = item
            holder[item] = hand
            continue
        # place, handover, release: the item leaves the hand that holds it
        if current.kind != "body":
            what = {
                "ground": "on the ground",
                "world": f"at {current.ref}",
                "authored": "where it is staged",
                "air": "in the air",
            }[current.kind]
            problems.append(
                (
                    v.where,
                    f"{a.kind} {item!r} at {v.start:.2f} s: nothing holds it (it is {what}); `grasp` it first",
                )
            )
            continue
        if getattr(a, "by", None) is not None:
            given = _holder(puppet, a.by, "hand")
            if given is None:
                continue
            if given.key() != current.key():
                problems.append(
                    (
                        v.where,
                        f"{a.kind} {item!r} by {a.by!r} at {v.start:.2f} s: {current.text()!r} holds it, not {a.by!r}",
                    )
                )
                continue
        if a.kind == "release":
            events[item].append(
                Event(_frame_at(times, v.start), "drop", release=a, where=v.where)
            )
            occupied.pop(current.key(), None)
            holder[item] = Holder("air")
            continue
        target_ref = a.onto if a.kind == "place" else a.to
        meet = getattr(a, "meet", 1.0)
        if _is_place_target(target_ref):
            target = _place_holder(target_ref, where=v.where, problems=problems)
        else:
            target = _holder(puppet, target_ref, "hand" if meet < 1.0 else "socket")
        if target is None:
            continue
        contact = v.start + float(a.reach)
        if target.kind == "body":
            busy = occupied.get(target.key())
            if busy is not None:
                problems.append(
                    (
                        v.where,
                        f"{target_ref!r} holds {busy!r} at {contact:.2f} s, when {item!r} arrives: take {busy!r} first (a `swap` does both)",
                    )
                )
                continue
            if target.key() == current.key():
                problems.append(
                    (
                        v.where,
                        f"{a.kind} {item!r} into {target_ref!r}, which already holds it",
                    )
                )
                continue
        point_default = info.grip if target.kind in ("body", "world") else None
        point = _item_point(
            info,
            a.item,
            where=v.where,
            problems=problems,
            default=point_default or info.centre,
        )
        if point is None:
            continue
        if a.kind == "handover" and meet < 1.0:
            give = new_gesture(
                "give",
                item,
                current,
                v,
                current.text(),
                target=target,
                meet=meet,
                point=point,
            )
            take = new_gesture(
                "take",
                item,
                target,
                v,
                target_ref,
                point=point,
                meet=meet,
                align=bool(a.align),
            )
            give.partner, take.partner = take.index, give.index
            events[item].append(Event(take.kc, "take", take, where=v.where))
            if take.align and take.k1 > take.kc:
                events[item].append(Event(take.k1, "settle", take, where=v.where))
        else:
            g = new_gesture(
                "place",
                item,
                current,
                v,
                current.text(),
                target=target,
                rotation=getattr(a, "rotation", None),
                point=point if (target.kind != "ground" or "@" in a.item) else None,
            )
            events[item].append(Event(g.k0, "carry", g, where=v.where))
            events[item].append(Event(g.kc, "put", g, where=v.where))
        occupied.pop(current.key(), None)
        if target.kind == "body":
            occupied[target.key()] = item
        holder[item] = (
            target
            if target.kind == "body"
            else Holder(target.kind, ref=target.ref, x=target.x, y=target.y)
        )
    # One hand, one gesture at a time.
    by_hand: dict[tuple, list[Gesture]] = {}
    for g in gestures:
        by_hand.setdefault(g.hand.key(), []).append(g)
    for hand_gestures in by_hand.values():
        hand_gestures.sort(key=lambda g: g.start)
        for g1, g2 in zip(hand_gestures, hand_gestures[1:]):
            if g2.start < g1.end - 1e-6:
                problems.append(
                    (
                        g2.where,
                        f"{g2.ref!r} starts its {g2.kind} of {g2.item!r} at {g2.start:.2f} s, before its {g1.kind} of {g1.item!r} is over ({g1.end:.2f} s): start it later, or shorten the first one's `retract`",
                    )
                )
    for item in events:
        events[item].sort(key=lambda e: (e.k, e.seq))
    return _Ctx(
        doc,
        shot,
        mall,
        puppet,
        times,
        items,
        gestures,
        events,
        initial,
        None,
        None,
        problems,
        [],
    )


# -----------------------------------------------------------------------------
# Bodies at a frame
# -----------------------------------------------------------------------------


def _body_world(puppet: Puppet, run: Run, k: int, body: str) -> Affine:
    info = puppet.bodies[body]
    x, y, theta = run.poses[k][body]
    return info.matrix(x, y, theta, run.geometry[k][body])


def _authored_world(puppet: Puppet, run: Run, k: int, body: str) -> Affine:
    """A body as the run had it (``run.poses``) — same as :func:`_body_world`."""
    return _body_world(puppet, run, k, body)


def _point_world(
    puppet: Puppet, run: Run, k: int, holder: Holder
) -> tuple[float, float]:
    return _apply(_body_world(puppet, run, k, holder.body), holder.local)


def _ground_at(ctx: _Ctx, run: Run, k: int, entity: str | None) -> float | None:
    """The floor line: the shot's ``ground``, else the bottom of ``entity``'s
    root parts (the floor it stands on) at frame ``k``."""
    if ctx.ground is not None:
        return ctx.ground
    if entity is None:
        return None
    puppet = ctx.puppet
    roots = [
        p
        for p, b in puppet.bodies.items()
        if b.entity == entity and b.parent_body is None
    ]
    if not roots:
        return None
    lowest = None
    for p in roots:
        m = _body_world(puppet, run, k, p)
        y = _lowest(m, ink_points(ctx.doc, puppet.nodes[p], ctx.mall))
        lowest = y if lowest is None else max(lowest, y)
    return lowest


def _first_carrier(ctx: _Ctx, item: str) -> str | None:
    for g in sorted(ctx.gestures, key=lambda g: g.start):
        if g.item == item:
            return g.hand.entity
    return None


# -----------------------------------------------------------------------------
# The item walk: each item's world transform at every frame
# -----------------------------------------------------------------------------


@dataclass
class _State:
    kind: str  # "authored" | "rest" | "body" | "settling" | "placing" | "flight"
    m: Affine | None = None  # rest
    body: str | None = None
    local: Affine | None = None  # body / placing: the item in the holder's frame
    gesture: Gesture | None = None
    attach: tuple[float, float] | None = None  # placing: the item's point at the hand
    hand: tuple[float, float] | None = None  # placing: the hand point (body-local)
    # flight
    k0: int = 0
    t0: float = 0.0
    duration: float = 0.0
    c0: tuple[float, float] = (0.0, 0.0)
    v0: tuple[float, float] = (0.0, 0.0)
    lin0: Lin = (0.0, 1.0, 1.0)
    lin1: Lin = (0.0, 1.0, 1.0)
    landing: Affine | None = None


@dataclass
class Walk:
    """Each item's world transform per frame, the pose it had just before each
    gesture took it, and where each place's item was carried from."""

    poses: dict[str, list[Affine]]
    before: dict[int, Affine]  # gesture index -> item pose just before its take/put
    attach: dict[
        int, tuple[float, float]
    ]  # place gesture -> the item's point at the hand
    carried: dict[
        int, Lin
    ]  # place gesture -> the item's linear part when the place starts
    rests: dict[
        str, list[tuple[int, Lin]]
    ]  # item -> (frame, how it lay) each time it came to rest on the ground
    #: place gesture onto the ground or a stage point -> ``(lin, whole pose,
    #: stage point)`` decided when the place starts (a socket's follows it).
    targets: dict[int, tuple[Lin, Affine | None, tuple[float, float] | None]] = field(
        default_factory=dict
    )


def _rest_lin(
    ctx: _Ctx,
    item: str,
    current: Lin,
    rotation: float | None,
    rests: list[tuple[int, Lin]],
) -> Lin:
    """How an item lies when it comes to rest on the ground: at ``rotation`` if
    given, else as it last lay, else its nearest quarter turn."""
    sx0, sy0 = ctx.items[item].scale
    sign = -1.0 if current[1] < 0 else 1.0
    if rotation is not None:
        last_sign = (-1.0 if rests[-1][1][1] < 0 else 1.0) if rests else sign
        return (float(rotation), last_sign * sx0, sy0)
    if rests:
        return rests[-1][1]
    quarter = round(current[0] / (math.pi / 2.0)) * (math.pi / 2.0)
    return (quarter, sign * sx0, sy0)


def _socket_lin(ctx: _Ctx, run: Run, k: int, holder: Holder, item: str) -> Lin:
    """An item aligned with a socket: the socket node's orientation and mirror,
    the item's own size."""
    frame = _compose(
        _body_world(ctx.puppet, run, k, holder.body), holder.frame or _IDENTITY
    )
    theta, _sx, _sy, mirrored = _decompose(frame)
    sx0, sy0 = ctx.items[item].scale
    return (theta, -sx0 if mirrored else sx0, sy0)


def _on_ground(
    ctx: _Ctx,
    lin: Lin,
    item: str,
    x: float,
    ground: float,
    *,
    about: tuple[float, float] | None = None,
) -> Affine:
    """The item lying with linear part ``lin``, its point ``about`` (default:
    its centre) at stage ``x``, its lowest ink point on ``ground``."""
    info = ctx.items[item]
    about = info.centre if about is None else about
    m = _placed((x, 0.0), lin, about)
    return _compose(_translate(0.0, ground - _lowest(m, info.corners)), m)


def _place_target(
    ctx: _Ctx, run: Run, g: Gesture, k: int, carried: Lin, rests: list[tuple[int, Lin]]
) -> tuple[Lin, Affine | None, tuple[float, float] | None]:
    """Where a place puts its item, as seen at frame ``k``: the item's linear
    part there, and either its whole pose (the ground, a stage point) or the
    stage point its contact point goes to (a socket)."""
    item, target = g.item, g.target
    if target.kind == "body":
        point = _point_world(ctx.puppet, run, k, target)
        return _socket_lin(ctx, run, k, target, item), None, point
    if target.kind == "world":
        lin = (
            carried
            if g.rotation is None
            else (float(g.rotation), carried[1], carried[2])
        )
        return lin, None, (target.x, target.y)
    lin = _rest_lin(ctx, item, carried, g.rotation, rests)
    ground = _ground_at(ctx, run, g.k0, g.hand.entity)
    if ground is None:
        return lin, None, None
    info = ctx.items[item]
    about = g.point if g.point is not None else info.centre
    hand0 = _point_world(ctx.puppet, run, g.k0, g.hand)
    x = target.x if target.x is not None else hand0[0]
    return lin, _on_ground(ctx, lin, item, x, ground, about=about), None


def walk_items(
    ctx: _Ctx, run: Run, *, ideal: bool, ideal_take: bool | None = None
) -> Walk:
    """Every item's world transform at every frame of ``run``.

    ``ideal`` (planning): a place puts its item exactly where it is going, and
    a hand that takes an item takes it by its grip (``ideal_take``, default
    ``ideal``: false plans a later place from where a grasp REALLY put the item
    in the hand), whatever the hand reached; else (the picture) every change of
    holder keeps the item where it is."""
    ideal_take = ideal if ideal_take is None else ideal_take
    out = Walk({}, {}, {}, {}, {})
    puppet, times = ctx.puppet, ctx.times
    for item, info in ctx.items.items():
        events = list(ctx.events.get(item, ()))
        rests: list[tuple[int, Lin]] = []
        poses: list[Affine] = []
        first = ctx.initial.get(item)
        state = _State("authored")
        if first is not None:
            m_doc = run.evaluated[0][item]
            if first.kind == "ground":
                ground = (
                    ctx.ground
                    if ctx.ground is not None
                    else _ground_at(ctx, run, 0, _first_carrier(ctx, item))
                )
                if ground is not None:
                    lin = _lin_of(m_doc)
                    x = (
                        first.x
                        if first.x is not None
                        else _apply(m_doc, info.centre)[0]
                    )
                    m = _on_ground(ctx, lin, item, x, ground)
                    state = _State("rest", m=m)
                    rests.append((0, lin))
            elif first.kind == "world":
                state = _State(
                    "rest", m=_placed((first.x, first.y), _lin_of(m_doc), info.grip)
                )
            elif first.kind == "body":
                lin = _socket_lin(ctx, run, 0, first, item)
                m = _placed(_point_world(puppet, run, 0, first), lin, info.grip)
                state = _State(
                    "body",
                    body=first.body,
                    local=_compose(_invert(_body_world(puppet, run, 0, first.body)), m),
                )
        for k in range(len(times)):
            current = _pose(ctx, run, k, item, state, poses)
            while events and events[0].k <= k:
                ev = events.pop(0)
                state, current = _transition(
                    ctx,
                    run,
                    k,
                    item,
                    state,
                    current,
                    ev,
                    poses,
                    rests,
                    out,
                    ideal=ideal,
                    ideal_take=ideal_take,
                )
            poses.append(current)
        out.poses[item] = poses
        out.rests[item] = rests
    return out


def _pose(
    ctx: _Ctx, run: Run, k: int, item: str, state: _State, poses: list[Affine]
) -> Affine:
    puppet = ctx.puppet
    if state.kind == "authored":
        return run.evaluated[k][item]
    if state.kind == "rest":
        return state.m
    if state.kind == "body":
        return _compose(_body_world(puppet, run, k, state.body), state.local)
    if state.kind == "settling":
        g = state.gesture
        hand_world = _body_world(puppet, run, k, state.body)
        carried = _lin_of(_compose(hand_world, state.local))
        span = max(_EPS, ctx.times[g.k1] - ctx.times[g.kc])
        f = _min_jerk((ctx.times[k] - ctx.times[g.kc]) / span)
        target = _socket_lin(ctx, run, k, g.hand, item)
        return _placed(
            _apply(hand_world, state.hand), _blend_lin(carried, target, f), state.attach
        )
    if state.kind == "placing":
        g = state.gesture
        carried = _lin_of(
            _compose(_body_world(puppet, run, k, state.body), state.local)
        )
        target_lin = (
            _place_target(ctx, run, g, min(k, g.kc), carried, [])[0]
            if g.target.kind == "body"
            else state.lin1
        )
        span = max(_EPS, ctx.times[g.kc] - ctx.times[g.k0])
        f = _min_jerk((ctx.times[k] - ctx.times[g.k0]) / span)
        hand = _apply(_body_world(puppet, run, k, state.body), state.hand)
        return _placed(hand, _blend_lin(carried, target_lin, f), state.attach)
    # flight
    tau = ctx.times[k] - state.t0
    if tau >= state.duration - 1e-9 and state.landing is not None:
        return state.landing
    gx, gy = ctx.gravity or (0.0, 0.0)
    c = (
        state.c0[0] + state.v0[0] * tau + 0.5 * gx * tau * tau,
        state.c0[1] + state.v0[1] * tau + 0.5 * gy * tau * tau,
    )
    f = _min_jerk(tau / state.duration) if state.duration > 0 else 1.0
    return _placed(c, _blend_lin(state.lin0, state.lin1, f), ctx.items[item].centre)


def _transition(
    ctx: _Ctx,
    run: Run,
    k: int,
    item: str,
    state: _State,
    current: Affine,
    ev: Event,
    poses: list[Affine],
    rests: list[tuple[int, Lin]],
    out: Walk,
    *,
    ideal: bool,
    ideal_take: bool,
) -> tuple[_State, Affine]:
    puppet = ctx.puppet
    info = ctx.items[item]
    g = ev.gesture
    if state.kind == "settling" and not (ev.kind == "settle" and g is state.gesture):
        # Something else happens before the hand has finished turning it: it is
        # held as it is now.
        state = _State(
            "body",
            body=state.body,
            local=_compose(_invert(_body_world(puppet, run, k, state.body)), current),
        )
    if ev.kind == "settle":
        if state.kind != "settling":
            return state, current
        return _State(
            "body",
            body=state.body,
            local=_compose(_invert(_body_world(puppet, run, k, state.body)), current),
        ), current
    if ev.kind == "take":
        out.before[g.index] = current
        hand_world = _point_world(puppet, run, k, g.hand)
        m = current
        if ideal_take and g.point is not None:
            at = _apply(current, g.point)
            m = _compose(
                _translate(hand_world[0] - at[0], hand_world[1] - at[1]), current
            )
        local = _compose(_invert(_body_world(puppet, run, k, g.hand.body)), m)
        if g.align and g.k1 > g.kc:
            attach = _apply(_invert(local), g.hand.local)
            return _State(
                "settling",
                body=g.hand.body,
                local=local,
                gesture=g,
                attach=attach,
                hand=g.hand.local,
            ), m
        return _State("body", body=g.hand.body, local=local), m
    if ev.kind == "carry":
        if state.kind != "body":
            return state, current
        hand_local = g.hand.local
        attach = _apply(_invert(state.local), hand_local)
        carried = _lin_of(current)
        out.attach[g.index] = attach
        out.carried[g.index] = carried
        decided = _place_target(ctx, run, g, g.kc, carried, rests)
        if g.target.kind != "body":
            out.targets[g.index] = decided
        new = _State(
            "placing",
            body=state.body,
            local=state.local,
            gesture=g,
            attach=attach,
            hand=hand_local,
            lin1=decided[0],
        )
        return new, current
    if ev.kind == "put":
        out.before[g.index] = current
        if state.kind not in ("placing", "body"):
            return state, current
        carried = out.carried.get(g.index, _lin_of(current))
        lin, whole, point = (
            out.targets[g.index]
            if g.index in out.targets
            else _place_target(ctx, run, g, k, carried, rests)
        )
        if g.target.kind == "body":
            m = current
            if ideal and point is not None:
                m = _placed(point, lin, g.point if g.point is not None else info.grip)
            new = _State(
                "body",
                body=g.target.body,
                local=_compose(_invert(_body_world(puppet, run, k, g.target.body)), m),
            )
            return new, m
        if g.target.kind == "world":
            m = (
                _placed(point, lin, g.point if g.point is not None else info.grip)
                if ideal
                else current
            )
            return _State("rest", m=m), m
        # the ground
        ground = _ground_at(ctx, run, g.k0, g.hand.entity)
        if ground is None:
            return _State("rest", m=current), current
        if ideal and whole is not None:
            rests.append((k, lin))
            return _State("rest", m=whole), whole
        above = ground - _lowest(current, info.corners)
        if abs(above) <= SUPPORT_TOLERANCE_PX:
            m = _compose(_translate(0.0, above), current)
            rests.append((k, _lin_of(m)))
            return _State("rest", m=m), m
        # Let go short of the floor: it falls the rest of the way.
        return _fall(
            ctx,
            run,
            k,
            item,
            current,
            poses,
            rests,
            rotation=g.rotation,
            toss=None,
            arc=0.0,
            entity=g.hand.entity,
            inherit=False,
        )
    # drop
    a = ev.release
    holder_entity = (
        puppet.bodies[state.body].entity if state.body in puppet.bodies else None
    )
    toss = None
    if a.onto is not None:
        target = _place_holder(a.onto, where=ev.where, problems=[])
        toss = target.x if target is not None and target.kind == "ground" else None
    return _fall(
        ctx,
        run,
        k,
        item,
        current,
        poses,
        rests,
        rotation=a.rotation,
        toss=toss,
        arc=float(a.arc),
        entity=holder_entity,
        inherit=toss is None,
    )


def _fall(
    ctx: _Ctx,
    run: Run,
    k: int,
    item: str,
    current: Affine,
    poses: list[Affine],
    rests: list[tuple[int, Lin]],
    *,
    rotation: float | None,
    toss: float | None,
    arc: float,
    entity: str | None,
    inherit: bool,
) -> tuple[_State, Affine]:
    """The item leaves every holder at frame ``k``: a parabola onto the ground."""
    info = ctx.items[item]
    t0 = ctx.times[k]
    c0 = _apply(current, info.centre)
    lin0 = _lin_of(current)
    v0 = (0.0, 0.0)
    if inherit and poses:
        dt = t0 - ctx.times[k - 1] if k > 0 else 0.0
        if dt > 0:
            prev = _apply(poses[-1], info.centre)
            v0 = ((c0[0] - prev[0]) / dt, (c0[1] - prev[1]) / dt)
    gx, gy = ctx.gravity or (0.0, 0.0)
    ground = _ground_at(ctx, run, k, entity)
    lin1 = _rest_lin(ctx, item, lin0, rotation, rests)
    if ground is None or gy <= 0:
        ctx.warnings.append(
            {
                "item": item,
                "at": round(t0, 3),
                "message": f"{item!r} is let go at {t0:.2f} s with no ground below it or no gravity: it stays in the air",
            }
        )
        return _State("rest", m=current), current
    landing0 = _on_ground(ctx, lin1, item, 0.0, ground)
    y_land = _apply(landing0, info.centre)[1]
    if toss is not None:
        apex = min(c0[1], y_land) - max(0.0, arc)
        up = math.sqrt(max(0.0, 2.0 * gy * (c0[1] - apex)))
        down = math.sqrt(max(0.0, 2.0 * (y_land - apex) / gy))
        duration = up / gy + down
        vx = (
            (toss - c0[0] - 0.5 * gx * duration * duration) / duration
            if duration > 0
            else 0.0
        )
        v0 = (vx, -up)
    else:
        # Solve 1/2 gy T^2 + vy T - (y_land - c0y) = 0 for T > 0.
        dy = y_land - c0[1]
        disc = v0[1] * v0[1] + 2.0 * gy * dy
        duration = (-v0[1] + math.sqrt(disc)) / gy if disc >= 0 else 0.0
    duration = max(0.0, duration)
    x_land = c0[0] + v0[0] * duration + 0.5 * gx * duration * duration
    landing = _compose(_translate(x_land, 0.0), landing0)
    state = _State(
        "flight",
        k0=k,
        t0=t0,
        duration=duration,
        c0=c0,
        v0=v0,
        lin0=lin0,
        lin1=lin1,
        landing=landing,
    )
    land_k = _frame_at(ctx.times, t0 + duration)
    rests.append((land_k, lin1))
    return state, (current if duration > 0 else landing)


# -----------------------------------------------------------------------------
# Planning the gestures: goals, leans, the hand's path
# -----------------------------------------------------------------------------


def _rig_parents(puppet: Puppet) -> dict[str, str]:
    """``child -> parent`` along the rigs' own joints (a flat rig's arm hangs
    from its torso by a joint, not by the node tree)."""
    return {
        r.child: r.parent
        for r in puppet.rows
        if r.source == "rig" and r.child is not None and r.parent is not None
    }


def _chain(puppet: Puppet, body: str) -> tuple[tuple[str, ...], str | None]:
    """The bodies from ``body`` up to (not including) the root it hangs from,
    and that root (``None`` when ``body`` hangs from nothing)."""
    parents = _rig_parents(puppet)
    chain, cursor, seen = [], body, set()
    while cursor in parents and cursor not in seen:
        seen.add(cursor)
        chain.append(cursor)
        cursor = parents[cursor]
    return tuple(chain), (cursor if chain else None)


def _hinge_world(
    puppet: Puppet, run: Run, k: int, child: str
) -> tuple[float, float] | None:
    """Where ``child`` hangs from its parent (the rig joint's point) at frame ``k``."""
    row = next((r for r in puppet.rows if r.source == "rig" and r.child == child), None)
    if row is None:
        return None
    p = row.joint.b
    info = puppet.bodies[child]
    left, top, w, h = info.box
    u = 1.0 - p.u if info.mirrored else p.u
    return _apply(_body_world(puppet, run, k, child), (left + u * w, top + p.v * h))


def _descendants(puppet: Puppet, root: str) -> list[str]:
    """Every body that hangs, through the rigs' joints, from ``root``."""
    parents = _rig_parents(puppet)
    out = []
    for path in puppet.bodies:
        cursor, seen = parents.get(path), set()
        while cursor is not None and cursor not in seen:
            if cursor == root:
                out.append(path)
                break
            seen.add(cursor)
            cursor = parents.get(cursor)
    return out


def _envelope(g: Gesture, times: Sequence[float], k: int) -> float:
    """How much of a gesture's lean is in force at frame ``k``: up over the reach, down over the retract."""
    t, t0, tc, t1 = times[k], times[g.k0], times[g.kc], g.end
    if k < g.k0 or t > t1 + 1e-9:
        return 0.0
    if k <= g.kc:
        return _min_jerk((t - t0) / (tc - t0)) if tc > t0 else 1.0
    return 1.0 - _min_jerk((t - tc) / (t1 - tc)) if t1 > tc else 0.0


def _reach_range(
    puppet: Puppet, run: Run, k: int, g: Gesture
) -> tuple[tuple[float, float] | None, float, float]:
    """The point the chain hangs from on its root, and how near and how far the
    chain puts the hand from it: ``(shoulder, nearest, farthest)``."""
    links = []
    hand = _point_world(puppet, run, k, g.hand)
    joints = [_hinge_world(puppet, run, k, b) for b in g.chain]
    if not joints or any(j is None for j in joints):
        return None, 0.0, 0.0
    points = [hand, *joints]  # hand, then each hinge up the chain
    for a, b in zip(points, points[1:]):
        links.append(math.hypot(a[0] - b[0], a[1] - b[1]))
    far = sum(links)
    near = max(0.0, 2.0 * max(links) - far) if len(links) > 1 else far
    return joints[-1], near, far


def _solve_lean(
    pivot: tuple[float, float],
    shoulder: tuple[float, float],
    goal: tuple[float, float],
    near: float,
    far: float,
    cap: float,
) -> tuple[float, float]:
    """The least turn of the root about ``pivot`` that puts ``goal`` between
    ``near`` and ``far`` of the turned ``shoulder``, within ``cap``: ``(angle,
    how far it stays out of reach)``.

    >>> a, gap = _solve_lean((0.0, 0.0), (0.0, -100.0), (60.0, 0.0), 80.0, 80.0, math.radians(90))
    >>> round(math.degrees(a), 1), round(gap, 6)
    (36.9, 0.0)
    """

    def distance(angle: float) -> float:
        s = _rotate_about(shoulder, pivot, angle)
        return math.hypot(goal[0] - s[0], goal[1] - s[1])

    def outside(angle: float) -> float:
        d = distance(angle)
        return max(0.0, near - d, d - far)

    if outside(0.0) <= 1e-9:
        return 0.0, 0.0
    gp = (goal[0] - pivot[0], goal[1] - pivot[1])
    up = (shoulder[0] - pivot[0], shoulder[1] - pivot[1])
    dg, r = math.hypot(*gp), math.hypot(*up)
    candidates = []
    if dg > 0 and r > 0:
        psi = math.atan2(gp[1], gp[0]) - math.atan2(up[1], up[0])
        for length in (far, near):
            c = (dg * dg + r * r - length * length) / (2.0 * dg * r)
            if -1.0 <= c <= 1.0:
                for sign in (1.0, -1.0):
                    angle = _wrap(psi - sign * math.acos(c))
                    if abs(angle) <= cap + 1e-12 and outside(angle) <= 1e-6:
                        candidates.append(angle)
    if candidates:
        return min(candidates, key=lambda a: (abs(a), a)), 0.0
    best = min(
        (cap * (2.0 * i / (LEAN_SAMPLES - 1) - 1.0) for i in range(LEAN_SAMPLES)),
        key=lambda a: (round(outside(a), 9), abs(a)),
    )
    return best, outside(best)


def _plan(ctx: _Ctx, base: Run, run: Run) -> None:
    """Give every gesture its chain, its lean and its hand's path (a reach row
    on the puppet), and every leaning body its rotation targets.

    ``base`` is the shot solved without any gesture (where a hand is when it is
    not reaching); ``run`` the latest solve (where the items are)."""
    puppet, times = ctx.puppet, ctx.times
    # The first plan (from the shot without gestures) takes every item by its
    # grip; a later one plans each place from where its grasp really put the item.
    walk = walk_items(ctx, run, ideal=True, ideal_take=run is base)
    goals: dict[int, list[tuple[float, float] | None]] = {}
    for g in ctx.gestures:
        g.chain, g.recruit = _chain(puppet, g.hand.body)
    # The goal of each gesture at every frame of its reach.
    for g in ctx.gestures:
        track: list[tuple[float, float] | None] = [None] * len(times)
        for k in range(g.k0, g.kc + 1):
            track[k] = _goal(ctx, base, run, walk, g, k)
        goals[g.index] = track
        g.goal = track[g.kc]
    # Leans: a fixed point among the gestures that turn the same root.
    by_root: dict[str, list[Gesture]] = {}
    for g in ctx.gestures:
        g.delta = 0.0
        if g.recruit is not None and g.goal is not None and g.lean > 0:
            by_root.setdefault(g.recruit, []).append(g)
    for root, group in by_root.items():
        for _round in range(LEAN_ROUNDS):
            moved = 0.0
            for g in group:
                others = sum(
                    _envelope(o, times, g.kc) * o.delta for o in group if o is not g
                )
                pivot = _apply(
                    _body_world(puppet, base, g.kc, root), puppet.bodies[root].pivot
                )
                shoulder, near, far = _reach_range(puppet, base, g.kc, g)
                if shoulder is None:
                    continue
                shoulder = _rotate_about(shoulder, pivot, others)
                delta, _gap = _solve_lean(
                    pivot, shoulder, g.goal, near, far, max(0.0, g.lean - abs(others))
                )
                moved = max(moved, abs(delta - g.delta))
                g.delta = delta
            if moved < 1e-10:
                break
        for g in group:
            g.against = tuple(
                o.index
                for o in group
                if o is not g
                and o.delta * g.delta < 0
                and o.start < g.end
                and g.start < o.end
            )

    def lean_at(root: str, k: int, skip: Gesture | None = None) -> float:
        return sum(
            _envelope(o, times, k) * o.delta
            for o in by_root.get(root, ())
            if o is not skip
        )

    riders_of = {root: set(_descendants(puppet, root)) for root in by_root}

    def turned(
        point: tuple[float, float], body: str, k: int, skip: Gesture | None
    ) -> tuple[float, float]:
        """``point`` (on ``body``, as the shot without gestures has it) where the
        leans in force at frame ``k`` carry it (all of them, or all but ``skip``'s)."""
        for root, riders in riders_of.items():
            if body in riders or body == root:
                pivot = _apply(
                    _body_world(puppet, base, k, root), puppet.bodies[root].pivot
                )
                point = _rotate_about(point, pivot, lean_at(root, k, skip=skip))
        return point

    # The hand's path: from where it would be (riding any other lean) to the goal
    # and back, kept where the chain can reach (on the circle a one-link arm
    # sweeps, inside the ring a bending one does), so the reach is never refused.
    puppet.rows = [r for r in puppet.rows if r.source != REACH_SOURCE]
    from an.kinematics import WORLD, Distance, Point

    for g in ctx.gestures:
        goal_c = goals[g.index][g.kc]
        if goal_c is None:
            continue
        track: list[tuple[float, float] | None] = [None] * len(times)
        t0, tc = times[g.k0], times[g.kc]
        turn: dict[
            str, float
        ] = {}  # the way round each phase goes, kept for its frames
        for k in range(g.k0, len(times)):
            t = times[k]
            if t > g.end + 1e-9:
                break
            rest = turned(_point_world(puppet, base, k, g.hand), g.hand.body, k, g)
            if k <= g.kc:
                phase, a, b = "reach", rest, goals[g.index][k] or goal_c
                f = _min_jerk((t - t0) / (tc - t0)) if tc > t0 else 1.0
            else:
                phase, a, b = "retract", goal_c, rest
                f = _min_jerk((t - tc) / (g.end - tc)) if g.end > tc else 1.0
            shoulder, near, far = _reach_range(puppet, base, k, g)
            if shoulder is None or not g.chain:
                track[k] = _lerp(a, b, f)
                continue
            centre = turned(shoulder, _root_of(g), k, None)
            track[k] = _swing(a, b, f, centre, near, far, turn, phase)
        info = puppet.bodies[g.hand.body]
        u, v = info.fraction(g.hand.local)
        puppet.rows.append(
            JointRow(
                Distance(
                    Point(g.hand.body, u, v),
                    Point(WORLD, 0.0, 0.0),
                    length=0.0,
                    mode="at_most",
                ),
                f"{g.ref} — {g.item}",
                REACH_SOURCE,
                f"{g.kind}:{g.where}:{g.index}",
                g.where,
                span=(t0, g.end),
                track=tuple(track),
                overrides=g.chain,
            )
        )
    # What leans: each root, and every part riding on it, while a lean is in force.
    puppet.lean = {}
    for root, group in by_root.items():
        if not any(g.delta for g in group):
            continue
        for body in [root, *sorted(riders_of[root])]:
            values: list[float | None] = [None] * len(times)
            for k in range(len(times)):
                if not any(g.k0 <= k and times[k] <= g.end + 1e-9 for g in group):
                    continue
                if any(
                    body in g.chain
                    for g in ctx.gestures
                    if g.k0 <= k and times[k] <= g.end + 1e-9
                ):
                    continue  # a reaching chain is moved by its reach
                theta = _decompose(_body_world(puppet, base, k, body))[0]
                values[k] = theta + lean_at(root, k)
            if any(v is not None for v in values):
                puppet.lean[body] = values


def _swing(
    a: tuple[float, float],
    b: tuple[float, float],
    f: float,
    centre: tuple[float, float],
    near: float,
    far: float,
    turn: dict[str, float],
    phase: str,
) -> tuple[float, float]:
    """The point ``f`` of the way from ``a`` to ``b`` as a hand swings about
    ``centre`` (its shoulder): angle and distance blended apart, the distance
    kept between ``near`` and ``far``. A straight line through the shoulder
    would make the arm flip across it; an arc never does. ``turn`` keeps the
    way round a phase first chose, so a goal straight across does not make it
    swap sides from one frame to the next.

    >>> p = _swing((0.0, 100.0), (100.0, 0.0), 0.5, (0.0, 0.0), 100.0, 100.0, {}, "reach")
    >>> [round(v, 3) for v in p]
    [70.711, 70.711]
    """
    ra = math.hypot(a[0] - centre[0], a[1] - centre[1])
    rb = math.hypot(b[0] - centre[0], b[1] - centre[1])
    if ra == 0 or rb == 0:
        return _lerp(a, b, f)
    angle_a = math.atan2(a[1] - centre[1], a[0] - centre[0])
    angle_b = math.atan2(b[1] - centre[1], b[0] - centre[0])
    raw = angle_b - angle_a
    first = turn.setdefault(phase, _wrap(raw))
    delta = first + _wrap(raw - first)
    angle = angle_a + delta * f
    r = min(max(ra + (rb - ra) * f, near), far)
    return (
        centre[0] + r * math.cos(angle) + 0.0,
        centre[1] + r * math.sin(angle) + 0.0,
    )


def _root_of(g: Gesture) -> str:
    """The body a gesture's shoulder is on: the root its chain hangs from."""
    return g.recruit if g.recruit is not None else g.hand.body


def _goal(
    ctx: _Ctx, base: Run, run: Run, walk: Walk, g: Gesture, k: int
) -> tuple[float, float] | None:
    """Where a gesture's hand must be at frame ``k`` for it to take or put its item there."""
    item = g.item
    info = ctx.items[item]
    if g.kind in ("grasp", "take"):
        if g.kind == "take" and g.partner is not None:
            return _meet(ctx, base, g, k)
        pose = (
            walk.poses[item][k]
            if k < g.kc
            else walk.before.get(g.index, walk.poses[item][k])
        )
        return _apply(pose, g.point if g.point is not None else info.grip)
    if g.kind == "give":
        return _meet(ctx, base, g, k)
    attach = walk.attach.get(g.index)
    carried = walk.carried.get(g.index)
    if attach is None or carried is None:
        return None
    lin, whole, point = (
        walk.targets[g.index]
        if g.index in walk.targets
        else _place_target(ctx, run, g, k, carried, [])
    )
    if whole is not None:
        return _apply(whole, attach)
    if point is None:
        return None
    contact = g.point if g.point is not None else info.grip
    m = _placed(point, lin, contact)
    return _apply(m, attach)


def _meet(ctx: _Ctx, base: Run, g: Gesture, k: int) -> tuple[float, float]:
    """Where a giving hand and a taking hand meet (``meet`` of the way from the giver's)."""
    pair = ctx.gestures[g.partner]
    give, take = (g, pair) if g.kind == "give" else (pair, g)
    a = _point_world(ctx.puppet, base, give.k0, give.hand)
    b = _point_world(ctx.puppet, base, take.k0, take.hand)
    return _lerp(a, b, give.meet)


# -----------------------------------------------------------------------------
# The pass: plan, solve, walk, measure
# -----------------------------------------------------------------------------


def _gravity(shot: Any, style_pack: Any) -> tuple[float, float] | None:
    from an.ir.schema import gravity_vector
    from an.stage.solve import _field

    own = shot.solve
    if own is not None and own.gravity is not None:
        return own.gravity_vector()
    pack = _field(style_pack, "gravity") if style_pack is not None else None
    if pack is not None:
        return gravity_vector(pack)
    return (0.0, DFLT_FALL_GRAVITY)


def solve_holds(
    state: Any, doc: Any, puppet: Puppet, decl: Any, settings: Any, times: list[float]
) -> tuple[Run, dict[tuple[str, str], tuple[list[float], list[float]]], dict[str, Any]]:
    """Plan and solve a shot's holds: the final run, the items' channels
    ``{(path, prop): (values, as the document shows them)}``, and the report."""
    from an.stage.solve import run_solve

    shot = state.shot
    holds = decl.holds
    extra = sorted(item for item in holds.items if item in puppet.nodes)
    base = run_solve(doc, puppet, times, settings, extra_paths=extra)
    ctx = _schedule(
        doc, shot, state.mall, puppet, holds, list(times), vocab=state.vocab
    )
    if ctx.problems:
        lines = "\n".join(f"  - {where}: {msg}" for where, msg in ctx.problems)
        raise HoldError(
            f"shot {shot.id!r}: its holds do not add up:\n{lines}", ctx.problems
        )
    ctx.gravity = _gravity(shot, state.style_pack)
    ctx.ground = shot.solve.ground if shot.solve is not None else None
    run = base
    if ctx.gestures:
        for _pass in range(HOLD_PLAN_PASSES):
            _plan(ctx, base, run)
            run = run_solve(doc, puppet, times, settings, extra_paths=extra)
    ctx.warnings.clear()  # the plans' walks said it too; the picture's walk says it once
    walk = walk_items(ctx, run, ideal=False)
    _measure(ctx, run, walk)
    channels = _item_channels(ctx, run, walk)
    return run, channels, _report(ctx, run, walk)


def _measure(ctx: _Ctx, run: Run, walk: Walk) -> None:
    """How far each hand stayed from its goal when its hold changed."""
    puppet = ctx.puppet
    for g in ctx.gestures:
        hand = _point_world(puppet, run, g.kc, g.hand)
        g.arrived = hand
        info = ctx.items[g.item]
        if g.kind in ("grasp", "take"):
            if g.kind == "take" and g.partner is not None:
                other = ctx.gestures[g.partner]
                there = _point_world(puppet, run, g.kc, other.hand)
            else:
                before = walk.before.get(g.index)
                there = (
                    _apply(before, g.point if g.point is not None else info.grip)
                    if before is not None
                    else hand
                )
        elif g.kind == "give":
            there = g.goal or hand
        else:
            # The item reached its target: its contact point on the socket, its lowest point on the ground.
            pose = walk.poses[g.item][g.kc]
            if g.target.kind == "body":
                there_item = _apply(pose, g.point if g.point is not None else info.grip)
                socket = _point_world(puppet, run, g.kc, g.target)
                g.gap = math.hypot(there_item[0] - socket[0], there_item[1] - socket[1])
                continue
            there = g.goal or hand
            if g.target.kind == "ground":
                before = walk.before.get(g.index)
                ground = _ground_at(ctx, run, g.k0, g.hand.entity)
                if before is not None and ground is not None:
                    off = abs(ground - _lowest(before, info.corners))
                    g.gap = max(off, math.hypot(hand[0] - there[0], hand[1] - there[1]))
                    continue
        g.gap = math.hypot(hand[0] - there[0], hand[1] - there[1])


def _item_channels(
    ctx: _Ctx, run: Run, walk: Walk
) -> dict[tuple[str, str], tuple[list[float], list[float]]]:
    out: dict[tuple[str, str], tuple[list[float], list[float]]] = {}
    for item, poses in walk.poses.items():
        info = ctx.items[item]
        values: dict[str, list[float]] = {p: [] for p in ITEM_CHANNELS}
        shown: dict[str, list[float]] = {p: [] for p in ITEM_CHANNELS}
        previous = None
        for k, m in enumerate(poses):
            parent = run.evaluated[k].get(info.parent, _IDENTITY)
            local = _compose(_invert(parent), m)
            theta, sx, sy, mirrored = _decompose(local)
            x, y = _apply(local, info.pivot)
            doc_x, doc_y, doc_rot, doc_sx, doc_sy = run.extra[k][item]
            ref = previous if previous is not None else doc_rot
            theta = ref + _wrap(theta - ref)
            previous = theta
            for prop, v, w in (
                ("x", x, doc_x),
                ("y", y, doc_y),
                ("rotation", theta, doc_rot),
                ("scale_x", -sx if mirrored else sx, doc_sx),
                ("scale_y", sy, doc_sy),
            ):
                values[prop].append(v)
                shown[prop].append(w)
        for prop in ITEM_CHANNELS:
            out[(item, prop)] = (values[prop], shown[prop])
    return out


def _report(ctx: _Ctx, run: Run, walk: Walk) -> dict[str, Any]:
    def r2(v: float) -> float:
        return round(float(v), 2) + 0.0

    gestures = []
    for g in ctx.gestures:
        entry: dict[str, Any] = {
            "kind": g.kind,
            "where": g.where,
            "item": g.item,
            "by": g.ref,
            "start": r2(g.start),
            "contact": r2(g.contact),
            "end": r2(g.end),
            "gap": r2(g.gap),
            "lean": r2(math.degrees(g.delta)),
            "lean_cap": r2(math.degrees(g.lean)),
            "carrier": g.hand.entity,
        }
        if g.target is not None:
            entry["onto"] = g.target.text()
        if g.against:
            entry["against"] = [
                {
                    "kind": ctx.gestures[o].kind,
                    "item": ctx.gestures[o].item,
                    "by": ctx.gestures[o].ref,
                    "start": r2(ctx.gestures[o].start),
                }
                for o in g.against
            ]
        if g.goal is not None and g.arrived is not None:
            entry["goal"] = [r2(g.goal[0]), r2(g.goal[1])]
            entry["hand"] = [r2(g.arrived[0]), r2(g.arrived[1])]
        gestures.append(entry)
    holders: dict[str, list[list[Any]]] = {}
    for item in ctx.items:
        first = ctx.initial.get(item)
        timeline = [[0.0, first.text() if first is not None else "staged"]]
        for ev in ctx.events.get(item, ()):
            t = r2(ctx.times[ev.k])
            if ev.kind == "take":
                timeline.append([t, ev.gesture.ref])
            elif ev.kind == "put":
                timeline.append([t, ev.gesture.target.text()])
            elif ev.kind == "drop":
                timeline.append([t, "air"])
        holders[item] = timeline
    floating = []
    for g in ctx.gestures:
        if g.kind != "grasp" or ctx.initial.get(g.item) is not None:
            continue
        if any(o.item == g.item and o.start < g.start for o in ctx.gestures):
            continue
        ground = _ground_at(ctx, run, g.k0, g.hand.entity)
        if ground is None:
            continue
        before = walk.before.get(g.index)
        if before is None:
            continue
        above = ground - _lowest(before, ctx.items[g.item].corners)
        if (
            SUPPORT_TOLERANCE_PX < above <= FLOAT_BAND_PX
            or above < -SUPPORT_TOLERANCE_PX
        ):
            floating.append(
                {
                    "item": g.item,
                    "where": g.where,
                    "above": r2(above),
                    "at": r2(g.contact),
                    "ground": r2(ground),
                }
            )
    return {
        "version": HOLD_VERSION,
        "gravity": [r2(v) for v in ctx.gravity] if ctx.gravity else None,
        "ground": r2(ctx.ground) if ctx.ground is not None else None,
        "gestures": gestures,
        "holders": holders,
        "floating": floating,
        "warnings": ctx.warnings,
    }
