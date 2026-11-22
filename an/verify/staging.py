"""Staging checks: a figure faces the way it goes, and is painted in front of what stands behind it.

Two constraints on the one interface (:class:`an.verify.constraints.Constraint`),
over the compiled shot:

- ``facing_travel`` (warning): an entity whose art says which way it faces
  (``metadata.faces`` in its store document, or the entity's own
  ``overrides.faces``) moves the other way: a character walking backwards
  because it was never turned (flip-to-turn) or was turned the wrong way.

How it reads a shot. The facing is where the art's declared side points on the
set (its own and every parent's mirror and rotation, before the camera, as the
``light`` check reads a shaded side), at every frame. The travel is the
entity's OWN move, its origin's ``x``/``y`` in its parent's frame carried onto
the set through that parent: a camera pan, a parallax wrapper or a vehicle the
entity rides is not the entity walking. A frame where the art is squashed (a
flip-to-turn passing through zero, its side probe under half its longest
length in the shot) faces nowhere and is not judged.

``faces`` is ``"left"`` or ``"right"`` (the way the unmirrored art faces), or,
for art whose facing depends on what it shows, a map from a swap set to its
keys' facings: ``{"face": {"dozy": "left", "rage": "left"}, "view": {"side":
"right"}}``. A key the map does not list (a front face) faces nowhere and is
not judged, and so is a set the shot never sets (the compiled document has no
channel for a rig's rest key). ``overrides: {faces: false}`` on the entity
turns the check off for it (a figure that backs away on purpose). The facing
is measured at the entity's root: a part mirrored on its own is not followed.

- ``depth_order`` (warning, an#820): a solid that walks past a floor prop
  standing farther back than its feet, and is painted under it, reads as
  walking behind it. In a shot with a floor, the foot line is the depth cue:
  lower on the set is nearer the camera.

How it reads a shot. A **floor prop** is an item whose holder at that instant
(the hold layer's report, ``meta.extensions.solve.holds``) is the floor or a
place on the set: ``ground``, ``ground@x``, ``world@x,y`` (an item put down,
let fall, or staged with ``overrides: {held_by: world@x,y}``), so a cup on a
table or a novel on a desk that nothing holds is not one; nor is one whose foot
rests on another solid's top (``world@`` on a counter top,
:func:`rests_on`). An item is held, and not judged, while its ``paint_after``
channel names a body's part (an#537). Floor props are chosen in ONE place,
:func:`held_on_floor`, handed to :func:`depth_inversions` as ``on_floor``. A
**walker** is any solid that is not an item of the hold layer (which carries
it, or lets it fall: a falling musket does not walk), such as a character or a
pushed crate, whose OWN travel on the set (as ``facing_travel`` reads it: its
origin's steps through its parent, so a camera pan or a ride is not a walk;
across the set or up and down it) is at least :data:`MIN_TRAVEL_SPEED_PX_S`;
once it is painted under a prop behind it, the stretch goes on while it stays
there, though it stops. The pairs are the ``solidity`` check's: the same
boxes, read the same way, on the same samples
(:data:`an.verify.constraints.SOLIDITY_SAMPLE_S`), covering more than
:data:`an.verify.constraints.SOLIDITY_TOLERANCE` of the smaller, two members
the world paints by depth skipped. A ``stage.after`` does not excuse a pair
here: a misplaced one is how the mistake is made.

The prop stands farther back when its foot (its box's bottom) is between the
walker's middle and :data:`DEPTH_MARGIN_SHARE` of the walker's height above
the walker's feet (its box's bottom). Both are read on the canvas, which a
camera pan and zoom move and scale alike, and the margin is a share of the
walker's height, so a wide and a close-up agree; a camera roll is not undone.
Equal foot lines (the margin) give no depth cue and are not judged: the
authoring answer there is to put the prop a little upstage. Limits: a pass
quicker than the sample step can fall between two samples, and a staged prop
nothing holds is not judged.

>>> [c.name for c in STAGING_CONSTRAINTS]
['facing_travel', 'depth_order']
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from an.genres.registry import CORE_OWNER, check_names, register_check
from an.verify.constraints import (
    ART_METADATA_KEY,
    SOLIDITY_TOLERANCE,
    Constraint,
    _covered_fraction,
    _fps,
    _is_solid,
    _sample_times,
    _side_on_set,
    compiled_shot,
    drawn_paths,
    paint_order,
    seen_boxes,
    solid_candidates,
)

__all__ = [
    "STAGING_CONSTRAINTS",
    "FACING_TRAVEL",
    "FACES_KEY",
    "FacingRun",
    "declared_faces",
    "art_facing_at",
    "backward_runs",
    "DEPTH_ORDER",
    "DEPTH_MARGIN_SHARE",
    "FLOOR_HOLDERS",
    "DepthInversion",
    "stands_behind",
    "rests_on",
    "floor_holder_at",
    "held_on_floor",
    "depth_inversions",
]

#: Where art says which way it faces (in its store document's ``metadata``, or
#: the entity's own ``overrides``).
FACES_KEY: str = "faces"
#: The facings art may declare.
FACINGS: frozenset[str] = frozenset({"left", "right"})
#: Slower than this on the set (px/s) is standing, not going anywhere.
MIN_TRAVEL_SPEED_PX_S: float = 20.0
#: A backward stretch shorter than this (s) is a stumble, not a walk.
MIN_BACKWARD_S: float = 0.2
#: A backward stretch that covers less than this (set px) is not reported.
MIN_BACKWARD_PX: float = 30.0
#: Frames of "not judged" (a mirror passing through zero) a backward stretch may
#: span and still be one stretch.
MAX_GAP_FRAMES: int = 3
#: A facing probe whose horizontal part is less than this share of its length
#: (art turned near vertical) says nothing about left or right.
MIN_HORIZONTAL_SHARE: float = 0.5
#: A facing probe shorter than this share of the longest it is in the shot is
#: art squashed mid-turn: it faces nowhere.
MIN_PROBE_SHARE: float = 0.5
#: How far above a walker's feet, as a share of its height, a floor prop's foot
#: must stand to read as farther back: closer foot lines are no depth cue.
DEPTH_MARGIN_SHARE: float = 0.05
#: The holders (the hold report's text, before any ``@``) that put an item on
#: the floor or at a place of the set, not in a hand or on a body.
FLOOR_HOLDERS: frozenset[str] = frozenset({"ground", "world"})


def declared_faces(entity: Any, stores: Any) -> Any:
    """``faces`` from the entity's ``overrides`` (winning) or its art's
    ``metadata``; ``None`` when neither says. The one reader of the
    declaration, for this check and for a genre that turns figures.

    >>> from types import SimpleNamespace as NS
    >>> stu = NS(overrides=None, store="characters", ref="stu")
    >>> declared_faces(stu, {"characters": {"stu": {"metadata": {"faces": "left"}}}})
    'left'
    >>> declared_faces(NS(overrides={"faces": False}, store="c", ref="s"), {}) is False
    True
    """
    overrides = entity.overrides or {}
    if FACES_KEY in overrides:
        return overrides[FACES_KEY]
    doc = ((stores or {}).get(entity.store) or {}).get(entity.ref)
    meta = doc.get(ART_METADATA_KEY) if isinstance(doc, Mapping) else None
    return meta.get(FACES_KEY) if isinstance(meta, Mapping) else None


def _normalised(faces: Any) -> tuple[Any, str | None]:
    """``(faces with every swap key as a string, what is wrong with it)``.

    >>> _normalised("left"), _normalised({"face": {1: "left"}})
    (('left', None), ({'face': {'1': 'left'}}, None))
    >>> _normalised("up")[1]
    "'up' is not a facing (left or right)"
    """
    if isinstance(faces, str):
        return (
            faces,
            None if faces in FACINGS else f"{faces!r} is not a facing (left or right)",
        )
    if isinstance(faces, Mapping):
        out: dict[str, dict[str, str]] = {}
        for set_name, keys in faces.items():
            if not isinstance(keys, Mapping):
                return (
                    None,
                    f"{set_name!r} maps to {keys!r}, not to {{key: left|right}}",
                )
            for key, way in keys.items():
                if way not in FACINGS:
                    return None, f"{set_name}.{key} is {way!r}, not left or right"
            out[str(set_name)] = {str(k): v for k, v in keys.items()}
        return out, None
    return None, f"{faces!r} is neither a facing nor a map of swap sets to facings"


def art_facing_at(faces: Any, pose: Mapping, entity_id: str) -> str | None:
    """The way the unmirrored art of ``entity_id`` faces under ``pose`` (a
    normalised declaration): the declaration itself when it is a facing; else
    the facing of the first swap set it lists whose key in force (a channel of
    that set's name on the entity or a part of it) it lists; ``None`` for a key
    it does not list, or no channel.

    >>> faces = {"face": {"dozy": "left"}}
    >>> art_facing_at("right", {}, "stu")
    'right'
    >>> art_facing_at(faces, {("stu/torso/face", "face"): "dozy"}, "stu")
    'left'
    >>> art_facing_at(faces, {("stu/torso/face", "face"): "smile"}, "stu") is None
    True
    """
    if isinstance(faces, str):
        return faces
    prefix = f"{entity_id}/"
    for set_name, keys in faces.items():
        for (target, prop), key in pose.items():
            if prop != set_name or not (
                target == entity_id or target.startswith(prefix)
            ):
                continue
            if str(key) in keys:
                return keys[str(key)]
    return None


@dataclass(frozen=True)
class FacingRun:
    """``entity`` moved ``moves`` (``left``/``right``) while facing the other
    way from ``start`` to ``end`` (s), over ``distance`` px of the set."""

    entity: str
    moves: str
    start: float
    end: float
    distance: float


def backward_runs(
    entity: str,
    times: list[float],
    xs: list[float],
    facings: list[str | None],
    *,
    min_speed: float = MIN_TRAVEL_SPEED_PX_S,
    min_duration: float = MIN_BACKWARD_S,
    min_distance: float = MIN_BACKWARD_PX,
    max_gap: int = MAX_GAP_FRAMES,
) -> list[FacingRun]:
    """The stretches where an entity whose own travel has brought it to set x
    ``xs[i]`` at ``times[i]``, facing ``facings[i]`` on the set (``None``: not
    judged), goes the other way. An interval is judged by the facing at its
    start, else at its end; up to ``max_gap`` unjudged intervals inside a
    stretch keep it one stretch.

    >>> ts = [i / 10 for i in range(11)]
    >>> xs = [100.0 * t for t in ts]
    >>> backward_runs("stu", ts, xs, ["left"] * 11)
    [FacingRun(entity='stu', moves='right', start=0.0, end=1.0, distance=100.0)]
    >>> backward_runs("stu", ts, xs, ["right"] * 11)
    []
    """
    runs: list[FacingRun] = []
    first = last = None  # the stretch's first and last backward interval
    moving: str | None = None
    gap = 0

    def close() -> None:
        if first is None:
            return
        t0, t1 = times[first], times[last + 1]
        dist = abs(xs[last + 1] - xs[first])
        if t1 - t0 >= min_duration - 1e-9 and dist >= min_distance:
            runs.append(FacingRun(entity, moving, round(t0, 6), round(t1, 6), dist))

    for i in range(len(times) - 1):
        dt = times[i + 1] - times[i]
        dx = xs[i + 1] - xs[i]
        way = None
        if dt > 0 and abs(dx) / dt >= min_speed:
            way = "right" if dx > 0 else "left"
        face = facings[i] if facings[i] is not None else facings[i + 1]
        if way is not None and face is not None and face != way:  # backward
            if first is not None and way != moving:
                close()
                first = None
            if first is None:
                first, moving = i, way
            last, gap = i, 0
        elif first is not None:
            judged = way is not None and face is not None  # going the way it faces
            gap += 1
            if judged or gap > max_gap:
                close()
                first = None
    close()
    return runs


def _probe(
    doc: Any, pose: Mapping, entity_id: str, way: str
) -> tuple[float, float] | None:
    """Where the side of art drawn facing ``way`` points on the set (a vector),
    ``None`` when squashed flat."""
    return _side_on_set(doc, pose, entity_id, side=way)


def _own_travel_xy(
    doc: Any, poses: list[Mapping], chain: list[tuple[Any, str]]
) -> list[tuple[float, float]]:
    """The set point the entity's OWN moves have taken it to, frame by frame:
    each step of its origin's ``x``/``y`` (in its parent's frame) carried onto
    the set through its parent's transform at the step's start. Two points
    mapped through one transform cancel its translation, so a camera pan, a
    parallax wrapper or a vehicle the entity rides adds nothing; the parent's
    mirror and rotation still turn the step."""
    from an.stage.timeline import screen_position

    node, path = chain[-1]
    parent = chain[-2][1] if len(chain) > 2 else None

    def local(pose: Mapping) -> tuple[float, float]:
        return (
            float(pose.get((path, "x"), node.transform.x)),
            float(pose.get((path, "y"), node.transform.y)),
        )

    out = [(0.0, 0.0)]
    for before, after in zip(poses, poses[1:]):
        (x0, y0), (x1, y1) = local(before), local(after)
        if parent is None:
            dx, dy = x1 - x0, y1 - y0
        else:
            a = screen_position(doc, parent, pose=before, point=(x0, y0), camera=False)
            b = screen_position(doc, parent, pose=before, point=(x1, y1), camera=False)
            dx, dy = b[0] - a[0], b[1] - a[1]
        out.append((out[-1][0] + dx, out[-1][1] + dy))
    return out


def _own_travel(
    doc: Any, poses: list[Mapping], chain: list[tuple[Any, str]]
) -> list[float]:
    """The set x of :func:`_own_travel_xy`: the way across the set an entity goes."""
    return [x for x, _ in _own_travel_xy(doc, poses, chain)]


def check_facing_travel(ctx: Any) -> None:
    """The core's ``facing_travel`` check: art that says which way it faces
    does not travel the other way across the set."""
    declared = []
    for e in ctx.shot.entities:
        faces = declared_faces(e, ctx.stores)
        if faces is None or faces is False:
            continue
        faces, problem = _normalised(faces)
        if problem is not None:
            ctx.report.add(
                "warning", f"{ctx.path}/entities", f"{e.id!r}: `faces`: {problem}."
            )
            continue
        declared.append((e, faces))
    if not declared:
        return
    doc = compiled_shot(ctx)
    if doc is None:
        return
    from an.stage.timeline import _node_chain, timeline_from_scene
    from an.timing.timeline import cut_timeline, evaluate_timeline

    chains = {}
    for e, _faces in declared:
        try:
            chains[e.id] = _node_chain(doc.scene, e.id)
        except Exception:  # noqa: BLE001 - not drawn on the stage
            continue
    if not chains:
        return
    above = {p for chain in chains.values() for _n, p in chain[1:]}
    sets = {s for _e, f in declared if isinstance(f, Mapping) for s in f}
    ids = tuple(chains)

    def wanted(target: str, prop: str) -> bool:
        return target in above or (
            prop in sets and any(target.startswith(f"{i}/") for i in ids)
        )

    timeline = cut_timeline(timeline_from_scene(doc), where=wanted)
    fps = _fps(ctx)
    duration = float(doc.timeline.duration)
    times = [f / fps for f in range(int(duration * fps + 1e-6) + 1)]
    poses = [evaluate_timeline(timeline, t) for t in times]
    for e, faces in declared:
        if e.id not in chains:
            continue
        xs = _own_travel(doc, poses, chains[e.id])
        probes = []
        for p in poses:
            way = art_facing_at(faces, p, e.id)
            probes.append(None if way is None else _probe(doc, p, e.id, way))
        longest = max((math.hypot(*v) for v in probes if v is not None), default=0.0)
        facings: list[str | None] = []
        for v in probes:
            n = math.hypot(*v) if v is not None else 0.0
            if (
                v is None
                or n < MIN_PROBE_SHARE * longest
                or abs(v[0]) < MIN_HORIZONTAL_SHARE * n
            ):
                facings.append(None)
            else:
                facings.append("right" if v[0] > 0 else "left")
        for run in backward_runs(e.id, times, xs, facings):
            other = "left" if run.moves == "right" else "right"
            ctx.report.add(
                "warning",
                f"{ctx.path}/actions",
                f"{e.id!r} moves {run.moves} while facing {other}, from {run.start:.2f} s "
                f"to {run.end:.2f} s ({run.distance:.0f} px): it walks backwards. Turn it "
                f"first (flip-to-turn: a `scale_x` of the other sign, or a `turn`), or move it "
                f"the way it faces; if it backs away on purpose, say so with "
                f"`overrides: {{{FACES_KEY}: false}}` on {e.id!r}.",
            )


FACING_TRAVEL = Constraint(
    "facing_travel",
    check_facing_travel,
    description="art that says which way it faces does not travel the other way (no walking backwards)",
)


# -----------------------------------------------------------------------------
# depth_order (an#820): a walker is painted in front of a floor prop behind it
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DepthInversion:
    """``walker`` was painted under ``prop`` from ``start`` to ``end`` (s, the
    sampled instants), though the prop's foot stood up to ``upstage`` px
    farther back (higher on the canvas) than the walker's feet."""

    walker: str
    prop: str
    start: float
    end: float
    upstage: float


def stands_behind(
    walker_box: tuple[float, ...],
    prop_box: tuple[float, ...],
    *,
    margin_share: float = DEPTH_MARGIN_SHARE,
    tolerance: float = SOLIDITY_TOLERANCE,
) -> float | None:
    """How many px the prop's foot stands above the walker's feet when it reads
    as farther back and the two overlap: its foot (``prop_box``'s bottom, boxes
    are ``(x0, y0, x1, y1)``, y down) between the walker's middle and
    ``margin_share`` of the walker's height above its feet, and the boxes
    covering more than ``tolerance`` of the smaller; else ``None``.

    >>> stu = (0, 0, 40, 200)  # a 200 px walker, feet at y 200
    >>> stands_behind(stu, (10, 160, 60, 180))  # a book whose foot is 20 px upstage
    20
    >>> stands_behind(stu, (10, 185, 60, 195)) is None  # 5 px: equal foot lines
    True
    >>> stands_behind(stu, (10, 40, 60, 90)) is None  # above his middle: not on his floor
    True
    >>> stands_behind(stu, (100, 160, 160, 180)) is None  # not where he is
    True
    """
    feet, middle = walker_box[3], (walker_box[1] + walker_box[3]) / 2
    height = walker_box[3] - walker_box[1]
    foot = prop_box[3]
    if not middle <= foot <= feet - margin_share * height:
        return None
    if _covered_fraction(walker_box, prop_box) <= tolerance:
        return None
    return feet - foot


def rests_on(prop_box: tuple[float, ...], other_box: tuple[float, ...]) -> bool:
    """Whether a prop's foot (the middle of its box's bottom) rests on another
    solid: it lies inside ``other_box``, in its upper half (on its top, not at
    its foot in front of it). A cup on a counter top, a book on a shelf: the
    place it rests at is not the floor.

    >>> counter = (0, 100, 200, 200)
    >>> rests_on((80, 70, 120, 102), counter)  # a cup standing on its top
    True
    >>> rests_on((80, 170, 120, 198), counter)  # a box at its foot, in front
    False
    >>> rests_on((300, 70, 340, 102), counter)  # beside it
    False
    """
    x = (prop_box[0] + prop_box[2]) / 2
    foot = prop_box[3]
    top, bottom = other_box[1], other_box[3]
    return other_box[0] <= x <= other_box[2] and top <= foot <= (top + bottom) / 2


def floor_holder_at(timeline: list[list[Any]], t: float) -> bool:
    """Whether the hold report's holder timeline of an item (``[[t, holder],
    ...]``) has it on the floor or at a place of the set at ``t``
    (:data:`FLOOR_HOLDERS`).

    >>> tl = [[0.0, "world@-840,460"], [1.0, "stu/hand_r"], [3.0, "ground"]]
    >>> [floor_holder_at(tl, t) for t in (0.5, 2.0, 3.5)]
    [True, False, True]
    """
    holder = None
    for start, text in timeline:
        if float(start) <= t + 1e-9:
            holder = str(text)
    return holder is not None and holder.partition("@")[0] in FLOOR_HOLDERS


def held_on_floor(holders: Mapping[str, list[list[Any]]]) -> Any:
    """``on_floor(entity_id, t)`` for :func:`depth_inversions`, from the hold
    report's ``holders``: an item whose holder at ``t`` puts it on the floor or
    at a place of the set (:func:`floor_holder_at`). The one place floor props
    are chosen: a later reading (a staged prop nothing holds) extends this."""

    def on_floor(eid: str, t: float) -> bool:
        return eid in holders and floor_holder_at(holders[eid], t)

    on_floor.candidates = frozenset(  # type: ignore[attr-defined]
        eid
        for eid, tl in holders.items()
        if any(str(h).partition("@")[0] in FLOOR_HOLDERS for _t, h in tl)
    )
    return on_floor


def _travel_speeds(
    doc: Any, poses: list[Mapping], chain: list[tuple[Any, str]], times: list[float]
) -> list[float]:
    """Per sampled instant, the larger of the own-travel speeds (set px/s, in
    any direction: across the set or up and down it) of the intervals either
    side of it (:func:`_own_travel_xy`)."""
    pts = _own_travel_xy(doc, poses, chain)
    steps = [
        math.dist(pts[i + 1], pts[i]) / (times[i + 1] - times[i])
        if times[i + 1] > times[i]
        else 0.0
        for i in range(len(times) - 1)
    ]
    return [
        max(steps[i - 1] if i > 0 else 0.0, steps[i] if i < len(steps) else 0.0)
        for i in range(len(times))
    ]


def depth_inversions(
    doc: Any,
    entities: list[Any],
    on_floor: Any,
    *,
    duration: float,
    carried: frozenset[str] = frozenset(),
    candidates: frozenset[str] | None = None,
    depth_sorted: frozenset[str] = frozenset(),
    min_speed: float = MIN_TRAVEL_SPEED_PX_S,
    margin_share: float = DEPTH_MARGIN_SHARE,
    tolerance: float = SOLIDITY_TOLERANCE,
) -> list[DepthInversion]:
    """Every walker among ``entities`` painted under a floor prop that stands
    behind it (:func:`stands_behind`), one record per pair and stretch of
    sampled instants. ``on_floor(entity_id, t)`` says which props are on the
    floor at ``t`` (:func:`held_on_floor`), ``candidates`` the ids it can say
    so of (default: every entity); ``carried`` the ids that never walk (the
    hold layer's items: carried, or falling). A prop resting on another solid
    lower than it (:func:`rests_on`: a counter top) is not on the floor. A
    walker starts a stretch while it moves at least ``min_speed``, and the
    stretch goes on while it stays painted under the prop behind it, though it
    stops there; a gap of more than one sample ends it."""
    from an.base import PAINT_AFTER_PROPERTY
    from an.stage.timeline import _node_chain, timeline_from_scene
    from an.stage.tree import paint_places
    from an.timing.timeline import evaluate_timeline

    places = paint_places(doc.scene)
    solids = [e for e in entities if _is_solid(e) and e.id in places]
    props = [e for e in solids if candidates is None or e.id in candidates]
    walkers = [e for e in solids if e.id not in carried]
    if not props or not walkers:
        return []
    chains = {}
    for e in walkers:
        try:
            chains[e.id] = _node_chain(doc.scene, e.id)
        except Exception:  # noqa: BLE001 - not drawn on the stage
            continue
    times = _sample_times(duration)
    timeline = timeline_from_scene(doc)
    poses = [evaluate_timeline(timeline, t) for t in times]
    speeds = {
        eid: _travel_speeds(doc, poses, chain, times) for eid, chain in chains.items()
    }
    drawn = drawn_paths(doc, [e.id for e in solids])
    painted_at = paint_order(doc)
    runs: dict[tuple[str, str], list[list[Any]]] = {}  # pair -> [[k0, k1, upstage]]

    for k, (t, pose) in enumerate(zip(times, poses)):
        floor_props = [
            e.id
            for e in props
            if on_floor(e.id, t) and not pose.get((e.id, PAINT_AFTER_PROPERTY))
        ]  # a paint_after naming a body's part: held
        if not floor_props:
            continue

        def ongoing(w: str, p: str) -> bool:
            last = runs.get((w, p))
            return bool(last) and last[-1][1] == k - 1

        movers = [
            w
            for w in chains
            if speeds[w][k] >= min_speed or any(ongoing(w, p) for p in floor_props)
        ]
        if not movers:
            continue
        others = {e.id for e in solids}
        boxes = seen_boxes(doc, {i: drawn[i] for i in others}, pose)
        for prop in floor_props:
            if prop not in boxes:
                continue
            for walker in movers:
                if walker == prop or walker not in boxes:
                    continue
                if walker in depth_sorted and prop in depth_sorted:
                    continue  # the world paints them by depth
                if speeds[walker][k] < min_speed and not ongoing(walker, prop):
                    continue
                if painted_at(prop, pose) <= painted_at(walker, pose):
                    continue  # the walker is painted over it: right
                up = stands_behind(
                    boxes[walker],
                    boxes[prop],
                    margin_share=margin_share,
                    tolerance=tolerance,
                )
                if up is None:
                    continue
                if any(
                    rests_on(boxes[prop], boxes[o])
                    for o in boxes
                    if o not in (prop, walker)
                ):
                    continue  # on a counter top, not the floor
                pair = runs.setdefault((walker, prop), [])
                if (
                    pair and pair[-1][1] >= k - 2
                ):  # one missed sample keeps it one stretch
                    pair[-1][1], pair[-1][2] = k, max(pair[-1][2], up)
                else:
                    pair.append([k, k, up])
    return [
        DepthInversion(w, p, round(times[a], 6), round(times[b], 6), up)
        for (w, p), stretches in runs.items()
        for a, b, up in stretches
    ]


def check_depth_order(ctx: Any) -> None:
    """The core's ``depth_order`` check (an#820): a walker is not painted under
    a floor prop that stands farther back than its feet."""
    from an.verify.support import _has_floor

    if not _has_floor(ctx.shot):
        return  # no floor, no foot line to read depth from
    doc = compiled_shot(ctx)
    if doc is None:
        return
    from an.stage.solve import solve_report

    holders = (solve_report(doc).get("holds") or {}).get("holders") or {}
    on_floor = held_on_floor(holders)
    if not on_floor.candidates:
        return
    entities, depth_sorted = solid_candidates(ctx)
    for inv in depth_inversions(
        doc,
        entities,
        on_floor,
        duration=float(ctx.shot.duration),
        carried=frozenset(holders),
        candidates=on_floor.candidates,
        depth_sorted=depth_sorted,
    ):
        ctx.report.add(
            "warning",
            f"{ctx.path}/entities",
            f"{inv.walker!r} is painted under {inv.prop!r} from {inv.start:.2f} s to "
            f"{inv.end:.2f} s as it goes past, though {inv.prop!r} stands farther back "
            f"(its foot {inv.upstage:.0f} px above the feet of {inv.walker!r}): it reads as "
            f"walking behind it. Paint {inv.walker!r} after it (`stage.after: {inv.prop}`, "
            f"or check a `stage.after` that puts {inv.walker!r} earlier), or move "
            f"{inv.prop!r} downstage of its path.",
        )


DEPTH_ORDER = Constraint(
    "depth_order",
    check_depth_order,
    description="a walker is not painted under a floor prop that stands farther back (an#820)",
)


#: The staging checks, in the order they run.
STAGING_CONSTRAINTS: tuple[Constraint, ...] = (FACING_TRAVEL, DEPTH_ORDER)


def _register() -> None:
    for constraint in STAGING_CONSTRAINTS:
        if constraint.name not in check_names(owner=CORE_OWNER):
            register_check(constraint.semantic_check(), owner=CORE_OWNER)


_register()
