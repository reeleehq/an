"""Staging checks: a figure faces the way it goes.

One constraint on the one interface (:class:`an.verify.constraints.Constraint`),
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

>>> [c.name for c in STAGING_CONSTRAINTS]
['facing_travel']
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from an.genres.registry import CORE_OWNER, check_names, register_check
from an.verify.constraints import (
    ART_METADATA_KEY,
    Constraint,
    _fps,
    _side_on_set,
    compiled_shot,
)

__all__ = [
    "STAGING_CONSTRAINTS",
    "FACING_TRAVEL",
    "FACES_KEY",
    "FacingRun",
    "declared_faces",
    "art_facing_at",
    "backward_runs",
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


def _own_travel(
    doc: Any, poses: list[Mapping], chain: list[tuple[Any, str]]
) -> list[float]:
    """The set x the entity's OWN moves have taken it to, frame by frame: each
    step of its origin's ``x``/``y`` (in its parent's frame) carried onto the
    set through its parent's transform at the step's start. Two points mapped
    through one transform cancel its translation, so a camera pan, a parallax
    wrapper or a vehicle the entity rides adds nothing; the parent's mirror and
    rotation still turn the step."""
    from an.stage.timeline import screen_position

    node, path = chain[-1]
    parent = chain[-2][1] if len(chain) > 2 else None

    def local(pose: Mapping) -> tuple[float, float]:
        return (
            float(pose.get((path, "x"), node.transform.x)),
            float(pose.get((path, "y"), node.transform.y)),
        )

    xs = [0.0]
    for before, after in zip(poses, poses[1:]):
        (x0, y0), (x1, y1) = local(before), local(after)
        if parent is None:
            step = x1 - x0
        else:
            a = screen_position(doc, parent, pose=before, point=(x0, y0), camera=False)
            b = screen_position(doc, parent, pose=before, point=(x1, y1), camera=False)
            step = b[0] - a[0]
        xs.append(xs[-1] + step)
    return xs


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


#: The staging checks, in the order they run.
STAGING_CONSTRAINTS: tuple[Constraint, ...] = (FACING_TRAVEL,)


def _register() -> None:
    for constraint in STAGING_CONSTRAINTS:
        if constraint.name not in check_names(owner=CORE_OWNER):
            register_check(constraint.semantic_check(), owner=CORE_OWNER)


_register()
