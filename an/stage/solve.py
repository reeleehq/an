"""The ``solve`` compile pass: joints kept at every frame (ADR 0008 decision 6, an#512).

After every pass that moves a body (the actions, a genre's poses and faces;
order 525, between ``face`` at 500 and ``camera_follow`` at 550), the
document so far is evaluated at every frame of the shot's grid, the joints a
scene declares are solved under the authored motion by :mod:`an.kinematics`,
and one key per frame is emitted for every channel the solve moved. A scene
that declares no joint and no verb compiles byte for byte as before: the pass
returns before it reads anything.

**Bodies** are read from the built tree and the rigs (:func:`an.stage.rig.rig_structure`):
every part of an entity a declaration names is a body posed in stage space
(the root's own coordinates: scene px from the stage centre), with the extent
of its drawing; its bones' joints are hinges; a bone with no part is a named
point (``paul/fore_r@hand_r``). A node that is not a body (a face part) is a
point on the body it rides.

**Drivers.** What the author wrote is met exactly where the joints allow:

- a rig's ROOT parts (a torso, a prop's body: nothing hangs them from a
  parent) stay where they are staged and animated, unless the entity says
  ``overrides: {free: true}`` (or names the parts: ``free: [torso]``), or a
  ``pin``/``pull`` moves them (a pinned cup goes to the hand);
- a part hung from a parent (an arm) is free, except in the channels authored
  on it; in ``nesting: bones`` an authored rotation is its joint held at that
  angle (a weld), since the angle is relative to a parent that may itself move;
- ``overrides: {fixed: true}`` holds every part of an entity where the author put it.

**What it emits.** One clip per entity, ``__solve__<entity>``, placed last in
that entity's track (later wins, so a solved channel replaces an authored one
on the same span: that is what a join means), with one quantised key per
frame on ``x``, ``y`` and ``rotation`` of a part whose parent is not a body
(a root, a part of a flat rig) and ``rotation`` alone of a part nested in a
chain (its position follows from its parent's). A channel the solve never
moves from what the document already shows is not emitted. Under ``step_hz``
the solve runs on the shot's step grid and the keys are stepped (its own
emission site, as the camera's). ``meta.extensions.solve`` records the mode,
the solver version and effort, a digest of the solve's inputs, the joints in
solver order, and what could not be held (the joints given up, the rejoins
that snapped, the authored spans the solve overrode): what ``an validate``'s
joint checks read (:mod:`an.verify.joints`).

>>> from an.ir.schema import Shot
>>> declarations(Shot(id="s"), {}).empty
True
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from an.ir.schema import JointSpec, Shot, gravity_vector
from an.stage.compile import CutoutCompileError

__all__ = [
    "SOLVE_ORDER",
    "SOLVE_CLIP_PREFIX",
    "SOLVE_EXTENSION",
    "UnknownBodyError",
    "Declarations",
    "declarations",
    "Puppet",
    "build_puppet",
    "solve_pass",
    "joint_residuals",
    "shot_declares_solve",
    "solve_knobs",
]

#: Where the pass runs: after ``face`` (500), before ``camera_follow`` (550).
SOLVE_ORDER: int = 525
#: The name of the clip of each entity's solved channels (``__solve__paul``).
SOLVE_CLIP_PREFIX: str = "__solve__"
#: The ``meta.extensions`` key of the solve's report.
SOLVE_EXTENSION: str = "solve"
#: The side of the square a body that draws nothing is given (scene px): a
#: body needs an extent for its mass and for points given as fractions.
DFLT_BODY_EXTENT: float = 10.0
#: ``AssetRef.overrides`` keys: free a rig's roots, or hold every part.
FREE_OVERRIDE: str = "free"
FIXED_OVERRIDE: str = "fixed"
#: The quanta a solved key is stored at (the solver's own, :func:`an.kinematics.quantize`).
POSITION_QUANTUM: float = 1e-6
ANGLE_QUANTUM: float = 1e-7
#: The spelling of a stage point: ``world@x,y``.
WORLD_REF: str = "world"
#: The pose channels a solve drives and emits.
SOLVED_CHANNELS: tuple[str, ...] = ("x", "y", "rotation")
#: How close a solved value must be to what the document already shows for the
#: channel to be left unemitted: a few quanta (the round trip through stage
#: space costs float noise, never a visible move).
SAME_VALUE: dict[str, float] = {"x": 1e-5, "y": 1e-5, "rotation": 1e-6}


class UnknownBodyError(CutoutCompileError):
    """A declaration names a body, a point or a joint the shot does not have.

    ``problems`` lists each one as ``(where, message)``, ``where`` relative to
    the shot (``joints/0``, ``actions/2``): what ``an validate``'s
    ``unknown_body`` check reports.
    """

    def __init__(self, message: str, problems: Sequence[tuple[str, str]]) -> None:
        super().__init__(message)
        self.problems = list(problems)


def _unknown_body_error(problems: Sequence[tuple[str, str]], *, shot_id: str) -> UnknownBodyError:
    lines = "\n".join(f"  - {where}: {msg}" for where, msg in problems)
    return UnknownBodyError(
        f"shot {shot_id!r}: its joints name what it does not have:\n{lines}", problems
    )


# -----------------------------------------------------------------------------
# What a shot declares
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DeclaredJoint:
    """A :class:`JointSpec` with its body references made shot paths, and where it came from."""

    spec: JointSpec
    a: str
    b: str | None
    end: str | None
    where: str


@dataclass(frozen=True)
class Verb:
    """A ``pin`` or ``pull`` over ``[start, end]``, or a ``join``/``unjoin`` at ``start``."""

    action: Any
    start: float
    end: float
    where: str


@dataclass
class Declarations:
    """Every joint and verb a shot declares, in solver order (structure first)."""

    joints: list[DeclaredJoint] = field(default_factory=list)
    verbs: list[Verb] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.joints and not self.verbs


def shot_declares_solve(shot: Shot, mall: Mapping[str, Any] | None = None) -> bool:
    """Whether ``shot`` declares anything the solve acts on (the pass's gate).

    >>> shot_declares_solve(Shot(id="s"))
    False
    """
    return not declarations(shot, mall or {}, verbs=_has_verb(shot)).empty


def solve_knobs(shot: Shot) -> dict[str, Any]:
    """The solve's render knobs for the shot-cache key: the solver's version, the
    shot's mode and effort as declared, and a digest of its declarations.

    >>> sorted(solve_knobs(Shot(id="s")))
    ['declared', 'iterations', 'mode', 'solver_version', 'substeps']
    """
    import hashlib
    import json

    from an.kinematics import DFLT_ITERATIONS, DFLT_SUBSTEPS, SOLVER_VERSION

    own = shot.solve
    declared = {
        "joints": [j.model_dump(mode="json") for j in shot.joints],
        "entities": [[e.id, [j.model_dump(mode="json") for j in e.joints], e.overrides] for e in shot.entities],
        "solve": own.model_dump(mode="json") if own is not None else None,
    }
    return {
        "solver_version": SOLVER_VERSION,
        "mode": (own.mode if own is not None else None) or "auto",
        "iterations": (own.iterations if own is not None and own.iterations else DFLT_ITERATIONS),
        "substeps": (own.substeps if own is not None and own.substeps else DFLT_SUBSTEPS),
        "declared": hashlib.sha256(json.dumps(declared, sort_keys=True, default=str).encode()).hexdigest(),
    }


def _has_verb(shot: Shot) -> bool:
    from an.ir.compose import iter_actions
    from an.ir.joints import JOINT_ACTION_KINDS

    return any(
        getattr(node, "kind", None) in JOINT_ACTION_KINDS
        for action in shot.actions
        for node in iter_actions(action)
    )


def _entity_ref(entity_id: str, ref: str) -> str:
    """An entity-relative body reference as a shot path (``fore@hand`` -> ``paul/fore@hand``)."""
    if ref.startswith("@"):
        return entity_id + ref
    return f"{entity_id}/{ref}"


def _descriptor(entity: Any, mall: Mapping[str, Any]) -> Any:
    """The entity's stored descriptor, or ``None``."""
    store = (mall or {}).get(entity.store) if entity.store else None
    if store is None:
        return None
    try:
        return store[entity.ref] if entity.ref in store else None
    except Exception:  # noqa: BLE001 - a store that cannot say has nothing to declare
        return None


def _field(doc: Any, name: str, default: Any = None) -> Any:
    if isinstance(doc, Mapping):
        return doc.get(name, default)
    return getattr(doc, name, default)


def declarations(
    shot: Shot, mall: Mapping[str, Any], *, verbs: bool = True, play_extent: Any = None
) -> Declarations:
    """The joints ``shot`` declares (its entities' descriptors', its entities',
    its own, in that order) and its verbs, flattened to shot time."""
    out = Declarations()
    for i, entity in enumerate(shot.entities):
        desc = _descriptor(entity, mall)
        for k, raw in enumerate(_field(desc, "joints") or [] if desc is not None else []):
            spec = raw if isinstance(raw, JointSpec) else JointSpec.model_validate(raw)
            out.joints.append(_declared(spec, entity.id, where=f"{entity.id} descriptor joints/{k}"))
        for k, spec in enumerate(entity.joints):
            out.joints.append(_declared(spec, entity.id, where=f"entities/{i}/joints/{k}"))
    for k, spec in enumerate(shot.joints):
        out.joints.append(
            DeclaredJoint(spec=spec, a=spec.a, b=spec.b, end=spec.end, where=f"joints/{k}")
        )
    if verbs:
        from an.ir.compose import flatten
        from an.ir.joints import JOINT_ACTION_KINDS

        for k, action in enumerate(shot.actions):
            for flat in flatten(action, play_extent=play_extent):
                if getattr(flat.action, "kind", None) in JOINT_ACTION_KINDS:
                    out.verbs.append(Verb(flat.action, flat.start, flat.end, where=f"actions/{k}"))
    return out


def _declared(spec: JointSpec, entity_id: str, *, where: str) -> DeclaredJoint:
    return DeclaredJoint(
        spec=spec,
        a=_entity_ref(entity_id, spec.a),
        b=spec.b,
        end=spec.end,
        where=where,
    )


# -----------------------------------------------------------------------------
# Geometry: 2D affine transforms in stage space
# -----------------------------------------------------------------------------

#: ``(a, b, c, d, tx, ty)``: ``p -> (a px + c py + tx, b px + d py + ty)``.
Affine = tuple[float, float, float, float, float, float]
_IDENTITY: Affine = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _affine_of(t: Any) -> Affine:
    """A :class:`~an.stage.timeline.Transform2D` (no tilt) as an affine map."""
    c, s = math.cos(t.rotation), math.sin(t.rotation)
    a, b = c * t.scale_x, s * t.scale_x
    cc, d = -s * t.scale_y, c * t.scale_y
    return (a, b, cc, d, t.x - (a * t.pivot_x + cc * t.pivot_y), t.y - (b * t.pivot_x + d * t.pivot_y))


def _compose(p: Affine, q: Affine) -> Affine:
    a1, b1, c1, d1, x1, y1 = p
    a2, b2, c2, d2, x2, y2 = q
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * x2 + c1 * y2 + x1,
        b1 * x2 + d1 * y2 + y1,
    )


def _apply(m: Affine, p: tuple[float, float]) -> tuple[float, float]:
    return (m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5])


def _invert(m: Affine) -> Affine:
    a, b, c, d, x, y = m
    det = a * d - b * c
    if det == 0:
        raise ValueError("a body with zero scale cannot be solved")
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(ia * x + ic * y), -(ib * x + id_ * y))


def _decompose(m: Affine) -> tuple[float, float, float, bool]:
    """``(theta, sx, sy, mirrored)`` with ``M = R(theta) diag(±sx, sy)`` (a
    mirror is put on x), skew ignored."""
    a, b, c, d = m[:4]
    det = a * d - b * c
    sx = math.hypot(a, b)
    if det < 0:
        return math.atan2(-b, -a), sx, -det / sx, True
    return math.atan2(b, a), sx, (det / sx if sx else 0.0), False


def _wrap(theta: float) -> float:
    return theta - 2.0 * math.pi * math.floor((theta + math.pi) / (2.0 * math.pi))


# -----------------------------------------------------------------------------
# The puppet: bodies and joints of one shot
# -----------------------------------------------------------------------------


@dataclass
class BodyInfo:
    """One body: a node of the built tree, its drawn extent and where it hangs."""

    path: str
    entity: str
    parent: str  # the node's parent path ("" is the root)
    parent_body: str | None  # the parent, when it is a body itself
    box: tuple[float, float, float, float]  # local (left, top, width, height)
    pivot: tuple[float, float]
    root: bool  # nothing hangs it from a parent body
    #: Filled from the rest pose: world scale and mirror (fixed for the shot).
    sx: float = 1.0
    sy: float = 1.0
    mirrored: bool = False
    #: The node's own ``scale_x`` is negative (it is drawn mirrored in its parent).
    flip_x: bool = False

    def width(self) -> float:
        return self.box[2] * self.sx

    def height(self) -> float:
        return self.box[3] * self.sy

    def fraction(self, local: tuple[float, float]) -> tuple[float, float]:
        """A local point as a fraction of this body's extent (the solver's Point)."""
        left, top, w, h = self.box
        u, v = (local[0] - left) / w, (local[1] - top) / h
        return (1.0 - u if self.mirrored else u), v

    def matrix(self, x: float, y: float, theta: float) -> Affine:
        """This body's node transform in stage space for a solved pose."""
        c, s = math.cos(theta), math.sin(theta)
        ex = -self.sx if self.mirrored else self.sx
        m = (c * ex, s * ex, -s * self.sy, c * self.sy, 0.0, 0.0)
        px, py = _apply(m, self.pivot)
        return (*m[:4], x - px, y - py)


@dataclass
class JointRow:
    """One solver joint and what it is for the report: ``label`` names its two
    bodies, ``source`` is ``rig`` (a bone), ``joint`` (declared) or a verb."""

    joint: Any
    label: str
    source: str
    id: str
    where: str
    #: ``(start, end)`` when only a span joins it (a verb); ``None``: always, unless unjoined.
    span: tuple[float, float] | None = None
    #: The structural joint of this child body (to weld it at an authored angle).
    child: str | None = None
    parent: str | None = None
    #: A pull's path of stage points, walked over ``span``.
    path: tuple[tuple[float, float], ...] | None = None
    #: Bodies a verb frees over its span.
    frees: tuple[str, ...] = ()
    #: The stage point a pin holds to (for a refused pin's message), when fixed.
    verb: str | None = None


@dataclass
class Puppet:
    """A shot's bodies (structure first) and joints, ready to solve."""

    bodies: dict[str, BodyInfo]
    rows: list[JointRow]
    held: set[str]  # bodies held where the author put them (roots, fixed entities)
    events: dict[str, list[tuple[float, bool]]]  # joint id -> [(time, joined)]
    rest: dict[str, Affine]  # body -> its rest (declared) stage transform


def _node_index(doc: Any) -> dict[str, Any]:
    from an.stage.tree import walk_children

    return {path: node for path, node in walk_children(doc.scene)}


def _parent_path(path: str, nodes: Mapping[str, Any]) -> str:
    """The indexed path of ``path``'s parent node ("" for a top-level node)."""
    head = path.rsplit("/", 1)[0] if "/" in path else ""
    while head and head not in nodes:
        head = head.rsplit("/", 1)[0] if "/" in head else ""
    return head


def _local_box(node: Any) -> tuple[float, float, float, float]:
    v = node.visual
    t = node.transform
    if v is not None and v.path is not None and v.path.points:
        xs = [p[0] for p in v.path.points]
        ys = [p[1] for p in v.path.points]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if w > 0 and h > 0:
            return (min(xs), min(ys), w, h)
    if v is not None and v.width and v.height:
        w, h = float(v.width), float(v.height)
        return (-float(v.anchor_x) * w, -float(v.anchor_y) * h, w, h)
    e = DFLT_BODY_EXTENT
    return (t.pivot_x - e / 2.0, t.pivot_y - e / 2.0, e, e)


def _world_matrices(doc: Any, paths: Sequence[str], pose: Any, nodes: Mapping[str, Any]) -> dict[str, Affine]:
    """``{path: stage transform}`` for ``paths`` and every ancestor, under ``pose``."""
    from an.stage.timeline import _pose_for, transform_of

    height = doc.meta.height
    out: dict[str, Affine] = {"": _IDENTITY}

    def world(path: str) -> Affine:
        if path in out:
            return out[path]
        parent = _parent_path(path, nodes)
        local = _affine_of(transform_of(nodes[path], _pose_for(pose, path), frame_height=height))
        out[path] = _compose(world(parent), local)
        return out[path]

    for p in paths:
        world(p)
    return out


def _rig_of(entity: Any, mall: Mapping[str, Any], nodes: Mapping[str, Any], vocab: Any = None) -> Any:
    """The entity's :class:`~an.stage.rig.RigStructure`, or ``None`` for a non-rig."""
    from an.ir.migrate import KINDS, migrate
    from an.stage.rig import rig_structure, slot_node_paths, _RigView

    desc = (getattr(vocab, "descriptors", None) or {}).get(entity.id) if vocab is not None else None
    if desc is None:
        desc = _descriptor(entity, mall)
    if desc is None or not _field(desc, "slots"):
        return None
    raw = desc.model_dump() if hasattr(desc, "model_dump") else dict(desc)
    kind = raw.get("kind")
    if kind in KINDS:
        try:
            raw = migrate(dict(raw), kind=kind)
        except Exception:  # noqa: BLE001 - the builder reports a broken descriptor
            pass
    view = _RigView.model_validate(raw)
    built = {slot for slot, rel in slot_node_paths(view).items() if f"{entity.id}/{rel}" in nodes}
    return rig_structure(view, built=built)


def build_puppet(
    doc: Any,
    shot: Shot,
    mall: Mapping[str, Any],
    decl: Declarations,
    *,
    vocab: Any = None,
) -> Puppet:
    """The bodies and joints of ``shot`` as built in ``doc``; raises
    :class:`UnknownBodyError` naming every reference it cannot resolve."""
    from an.kinematics import WORLD, Distance, Hinge, Pin, Point, Slide, Contact, Weld

    nodes = _node_index(doc)
    entities = {e.id: e for e in shot.entities}
    problems: list[tuple[str, str]] = []
    rigs: dict[str, Any] = {}

    def entity_of(path: str) -> str:
        return path.split("/", 1)[0]

    # Which entities take part: every one a declaration names.
    named: list[str] = []

    def note(ref: Any) -> None:
        if isinstance(ref, str):
            head = ref.split("@", 1)[0]
            if head and head != WORLD_REF:
                eid = entity_of(head)
                if eid not in named:
                    named.append(eid)

    for dj in decl.joints:
        for ref in (dj.a, dj.b, dj.end):
            note(ref)
    for verb in decl.verbs:
        note(getattr(verb.action, "point", None))
        note(getattr(verb.action, "to", None))

    bodies: dict[str, BodyInfo] = {}
    held: set[str] = set()
    structural: list[tuple[Any, str]] = []  # (RigJoint, entity id)
    for eid in named:
        entity = entities.get(eid)
        if entity is None or eid not in nodes:
            continue  # reported when the reference is resolved
        rig = _rig_of(entity, mall, nodes, vocab)
        rigs[eid] = rig
        overrides = entity.overrides or {}
        free = overrides.get(FREE_OVERRIDE)
        fixed = bool(overrides.get(FIXED_OVERRIDE))
        if rig is None or not rig.bodies:
            path = eid
            bodies[path] = BodyInfo(path, eid, "", None, _local_box(nodes[path]), _pivot(nodes[path]), True)
            if fixed or free is not True:
                held.add(path)
            continue
        for slot, rel in rig.bodies.items():
            path = f"{eid}/{rel}"
            parent = _parent_path(path, nodes)
            is_root = slot in rig.roots
            bodies[path] = BodyInfo(
                path, eid, parent, None, _local_box(nodes[path]), _pivot(nodes[path]), is_root
            )
            freed = free is True or (isinstance(free, (list, tuple)) and slot in free)
            if fixed or (is_root and not freed):
                held.add(path)
        for joint in rig.joints:
            structural.append((joint, eid))
    for b in bodies.values():
        if b.parent in bodies:
            b.parent_body = b.parent

    rest = _world_matrices(doc, list(bodies), None, nodes)
    for b in bodies.values():
        _theta, b.sx, b.sy, b.mirrored = _decompose(rest[b.path])
        b.flip_x = nodes[b.path].transform.scale_x < 0
        if not (b.sx > 0 and b.sy > 0):
            problems.append((b.path, "has zero scale at rest and cannot be solved"))

    def body_and_local(node_path: str) -> tuple[str, Affine] | None:
        """The body ``node_path`` is (or rides on), and the node's transform in that body's frame."""
        cursor = node_path
        while cursor:
            if cursor in bodies:
                inner = _compose(_invert(rest[cursor]), _node_rest(node_path))
                return cursor, inner
            cursor = _parent_path(cursor, nodes)
        return None

    rest_cache: dict[str, Affine] = {}

    def _node_rest(path: str) -> Affine:
        if path not in rest_cache:
            rest_cache[path] = _world_matrices(doc, [path], None, nodes)[path]
        return rest_cache[path]

    def anchor_world(eid: str, bone: str) -> tuple[float, float] | None:
        rig = rigs.get(eid)
        if rig is None or bone not in rig.anchors:
            return None
        anchor = rig.anchors[bone]
        frame = (
            _node_rest(f"{eid}/{rig.bodies.get(anchor.on) or _slot_path(eid, anchor.on, nodes)}")
            if anchor.on is not None
            else _node_rest(eid)
        )
        return _apply(frame, anchor.offset)

    def resolve(ref: Any, *, where: str, side: str) -> Any:
        """A reference as a solver Point (and its body), or ``None`` after noting the problem."""
        if isinstance(ref, (list, tuple)) and len(ref) == 2 and all(isinstance(v, (int, float)) for v in ref):
            return Point(WORLD, float(ref[0]), float(ref[1]))
        if not isinstance(ref, str):
            problems.append((where, f"{ref!r} is not a body reference (`body[@point]`, `world@x,y`, or [x, y])"))
            return None
        head, _, at = ref.partition("@")
        if head == WORLD_REF:
            xy = _numbers(at)
            if xy is None:
                problems.append((where, f"{ref!r}: a stage point is `world@x,y`"))
                return None
            return Point(WORLD, *xy)
        eid = entity_of(head)
        if eid not in entities:
            problems.append((where, f"{ref!r}: {eid!r} is not an entity of this shot"))
            return None
        node_path = _slot_path(eid, head.split("/", 1)[1], nodes, rigs.get(eid)) if "/" in head else head
        if node_path not in nodes:
            near = sorted(p for p in nodes if p.split("/", 1)[0] == eid)
            problems.append((where, f"{ref!r}: no node {node_path!r}; {eid!r} has {near}"))
            return None
        if node_path == eid and rigs.get(eid) is not None and rigs[eid].bodies:
            roots = rigs[eid].roots
            if len(roots) != 1:
                problems.append(
                    (where, f"{ref!r}: {eid!r} has {len(roots)} root parts {list(roots)}; name the part (`{eid}/<part>`)")
                )
                return None
            node_path = f"{eid}/{rigs[eid].bodies[roots[0]]}"
        found = body_and_local(node_path)
        if found is None:
            problems.append((where, f"{ref!r}: {node_path!r} is on no body of the shot"))
            return None
        body, inner = found
        info = bodies[body]
        node = nodes[node_path]
        if not at:
            local_on_node = _pivot(node) if side == "a" else _centre(_local_box(node))
            local = _apply(inner, local_on_node)
        else:
            xy = _numbers(at)
            if xy is not None:
                left, top, w, h = _local_box(node)
                local = _apply(inner, (left + xy[0] * w, top + xy[1] * h))
            else:
                world = anchor_world(eid, at)
                if world is None:
                    rig = rigs.get(eid)
                    known = sorted(rig.anchors) if rig is not None else []
                    problems.append((where, f"{ref!r}: {at!r} is not a bone of {eid!r} (bones: {known}) nor a fraction `u,v`"))
                    return None
                local = _apply(_invert(rest[body]), world)
        u, v = info.fraction(local)
        return Point(body, u, v)

    rows: list[JointRow] = []
    # 1. The rigs' own joints, parents first: the structure before what it reaches for.
    overrides_by_child: dict[str, DeclaredJoint] = {}
    for dj in decl.joints:
        if dj.b is None:
            p = resolve(dj.a, where=dj.where, side="a")
            if p is not None:
                overrides_by_child[p.body] = dj
    for joint, eid in structural:
        rig = rigs[eid]
        child = f"{eid}/{rig.bodies[joint.child]}"
        parent = f"{eid}/{rig.bodies[joint.parent]}"
        world = anchor_world(eid, joint.bone)
        if world is None:
            continue
        pc = bodies[child].fraction(_apply(_invert(rest[child]), world))
        pp = bodies[parent].fraction(_apply(_invert(rest[parent]), world))
        a, b = Point(parent, *pp), Point(child, *pc)
        relative = _relative(rest, parent, child, bodies)
        dj = overrides_by_child.pop(child, None)
        kind = joint.kind if dj is None else dj.spec.type
        limits = joint.limits if dj is None or dj.spec.limits is None else dj.spec.limits
        give = 0.0 if dj is None else dj.spec.give
        if kind == "weld":
            row = Weld(a, b, rest=relative, compliance=give)
        else:
            row = Hinge(a, b, limits=_limits(limits, mirrored=_flips(rest[parent])), rest=relative, compliance=give)
        rows.append(
            JointRow(
                row, f"{parent} — {child}", "rig", dj.spec.id if dj and dj.spec.name else child,
                dj.where if dj else f"{eid} rig bone {joint.bone!r}", child=child, parent=parent,
            )
        )
    for child, dj in overrides_by_child.items():
        problems.append((dj.where, f"{dj.a!r}: a {dj.spec.type} with no `b` is a rig part's own joint, and {child!r} hangs from no parent part"))

    # 2. Declared joints.
    for dj in decl.joints:
        if dj.b is None:
            continue
        pa = resolve(dj.a, where=dj.where, side="a")
        pb = resolve(dj.b, where=dj.where, side="b")
        pe = resolve(dj.end, where=dj.where, side="b") if dj.end is not None else None
        if pa is None or pb is None or (dj.end is not None and pe is None):
            continue
        spec = dj.spec
        label = f"{dj.a} — {dj.b}"
        if spec.type == "pin":
            row = Pin(pa, pb, compliance=spec.give)
        elif spec.type == "hinge":
            row = Hinge(pb, pa, limits=_limits(spec.limits, mirrored=False), rest=_relative_points(rest, pb, pa, bodies), compliance=spec.give)
        elif spec.type == "weld":
            row = Weld(pb, pa, rest=_relative_points(rest, pb, pa, bodies), compliance=spec.give)
        elif spec.type in ("distance", "string", "rod"):
            length = spec.length if spec.length is not None else _distance(rest, bodies, pa, pb)
            row = Distance(pa, pb, length=float(length), mode=spec.distance_mode, compliance=spec.give)
        elif spec.type == "slide":
            row = Slide(pa, pb, pe, compliance=spec.give)
        else:
            row = Contact(pa, pb, pe, compliance=spec.give)
        rows.append(JointRow(row, label, "joint", spec.id, dj.where))

    # 3. The verbs over their spans; join/unjoin events by joint id.
    events: dict[str, list[tuple[float, bool]]] = {}
    duration = float(shot.duration)
    for verb in decl.verbs:
        action = verb.action
        if action.kind in ("join", "unjoin"):
            events.setdefault(action.joint, []).append((verb.start, action.kind == "join"))
            continue
        open_ended = (action.duration if action.kind == "pin" else action.over) is None
        span = (verb.start, duration if open_ended else verb.end)
        pa = resolve(action.point, where=verb.where, side="a")
        path = None
        to = action.to
        if action.kind == "pull" and isinstance(to, list) and to and isinstance(to[0], (list, tuple)):
            path = tuple((float(p[0]), float(p[1])) for p in to)
            pb = Point(WORLD, *path[0])
        else:
            pb = resolve(to, where=verb.where, side="b")
        if pa is None or pb is None:
            continue
        if action.kind == "pin":
            row = Pin(pa, pb)
        else:
            row = Distance(pa, pb, length=0.0, mode="at_most", compliance=float(action.give))
        rows.append(
            JointRow(
                row, f"{action.point} — {_ref_text(to)}", action.kind, f"{action.kind}:{verb.where}",
                verb.where, span=span, path=path, frees=(pa.body,), verb=action.kind,
            )
        )
    ids = {row.id for row in rows}
    for jid in events:
        if jid not in ids:
            problems.append(("actions", f"join/unjoin names {jid!r}, which is no joint of this shot (joints: {sorted(ids)})"))
    for jid in events:
        events[jid].sort(key=lambda e: e[0])
    if problems:
        raise _unknown_body_error(problems, shot_id=shot.id)
    return Puppet(bodies=bodies, rows=rows, held=held, events=events, rest={p: rest[p] for p in bodies})


def _pivot(node: Any) -> tuple[float, float]:
    return (float(node.transform.pivot_x), float(node.transform.pivot_y))


def _centre(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return (box[0] + box[2] / 2.0, box[1] + box[3] / 2.0)


def _numbers(text: str) -> tuple[float, float] | None:
    parts = text.split(",")
    if len(parts) != 2:
        return None
    try:
        return (float(parts[0]), float(parts[1]))
    except ValueError:
        return None


def _ref_text(ref: Any) -> str:
    if isinstance(ref, str):
        return ref
    if ref and isinstance(ref[0], (list, tuple)):
        return f"a path of {len(ref)} points"
    return f"({ref[0]:g}, {ref[1]:g})"


def _slot_path(eid: str, rel: str, nodes: Mapping[str, Any], rig: Any = None) -> str:
    """``eid/rel`` as a node path; a rig's slot name stands for its node path."""
    full = f"{eid}/{rel}"
    if full in nodes or rig is None:
        return full
    if rel in rig.bodies:
        return f"{eid}/{rig.bodies[rel]}"
    head, _, rest_ = rel.partition("/")
    if head in rig.bodies:
        return f"{eid}/{rig.bodies[head]}" + (f"/{rest_}" if rest_ else "")
    return full


def _flips(m: Affine) -> bool:
    return (m[0] * m[3] - m[1] * m[2]) < 0


def _limits(limits: Any, *, mirrored: bool) -> tuple[float, float] | None:
    """Degrees about the rest pose as the solver's radians; a mirrored frame turns the other way."""
    if limits is None:
        return None
    lo, hi = math.radians(float(limits[0])), math.radians(float(limits[1]))
    return (-hi, -lo) if mirrored else (lo, hi)


def _relative(rest: Mapping[str, Affine], parent: str, child: str, bodies: Mapping[str, BodyInfo]) -> float:
    return _wrap(_decompose(rest[child])[0] - _decompose(rest[parent])[0])


def _relative_points(rest: Mapping[str, Affine], a: Any, b: Any, bodies: Mapping[str, BodyInfo]) -> float:
    ta = _decompose(rest[a.body])[0] if a.body in rest else 0.0
    tb = _decompose(rest[b.body])[0] if b.body in rest else 0.0
    return _wrap(tb - ta)


def _point_at(rest: Mapping[str, Affine], bodies: Mapping[str, BodyInfo], p: Any) -> tuple[float, float]:
    if p.body not in bodies:
        return (p.u, p.v)
    info = bodies[p.body]
    left, top, w, h = info.box
    u = 1.0 - p.u if info.mirrored else p.u
    return _apply(rest[p.body], (left + u * w, top + p.v * h))


def _distance(rest: Mapping[str, Affine], bodies: Mapping[str, BodyInfo], a: Any, b: Any) -> float:
    (ax, ay), (bx, by) = _point_at(rest, bodies, a), _point_at(rest, bodies, b)
    return math.hypot(ax - bx, ay - by)


# -----------------------------------------------------------------------------
# Running the solve
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """What the solve runs with, resolved from the shot, the style pack and the declarations."""

    mode: str
    gravity: tuple[float, float] | None
    damping: float
    iterations: int
    substeps: int


def resolve_settings(shot: Shot, style_pack: Any, puppet: Puppet) -> Settings:
    """Shot over style pack over the solver's defaults; ``dynamic`` when gravity
    or a string acts and the shot does not say ``pose``."""
    from an.kinematics import DFLT_ITERATIONS, DFLT_SUBSTEPS, Distance
    from an.kinematics.solver import DFLT_DAMPING

    own = shot.solve
    pack_gravity = _field(style_pack, "gravity") if style_pack is not None else None
    pack_damping = _field(style_pack, "damping") if style_pack is not None else None
    if own is not None and own.gravity is not None:
        gravity = own.gravity_vector()
    else:
        gravity = gravity_vector(pack_gravity)
    strings = any(isinstance(r.joint, Distance) and r.joint.mode == "at_most" for r in puppet.rows)
    mode = (own.mode if own is not None else None) or ("dynamic" if gravity or strings else "pose")
    damping = own.damping if own is not None and own.damping is not None else pack_damping
    return Settings(
        mode=mode,
        gravity=gravity if mode == "dynamic" else None,
        damping=float(damping) if damping is not None else DFLT_DAMPING,
        iterations=(own.iterations if own is not None and own.iterations else DFLT_ITERATIONS),
        substeps=(own.substeps if own is not None and own.substeps else DFLT_SUBSTEPS),
    )


def frame_times(duration: float, *, fps: float, step_hz: float | None) -> list[float]:
    """The instants the solve runs at: every frame (``k/fps``, the end
    included), or the shot's step grid under ``step_hz``.

    >>> frame_times(0.1, fps=20, step_hz=None)
    [0.0, 0.05, 0.1]
    >>> frame_times(0.25, fps=20, step_hz=10)
    [0.0, 0.1, 0.2, 0.25]
    """
    duration = max(0.001, float(duration))
    if step_hz:
        from an.stage.compile import step_times

        return step_times(0.0, duration, step_hz)
    frames = max(1, round(duration * fps))
    return [min(duration, k / fps) for k in range(frames + 1)]


@dataclass
class Run:
    """What a solve over the grid produced: ``poses[k][body] = (x, y, theta)``."""

    times: list[float]
    poses: list[dict[str, tuple[float, float, float]]]
    held: list[dict[str, set[str]]]  # per frame: body -> held channels
    evaluated: list[dict[str, Affine]]  # per frame: authored stage transforms
    dropped: list[tuple[int, ...]]
    unsatisfied: list[tuple[tuple[int, float], ...]]
    limits: list[tuple[tuple[int, float], ...]]
    snaps: list[tuple[int, int, float]]
    joined: list[list[bool]]
    #: per frame: body -> its node's channels ``(x, y, rotation)`` as the document shows them
    local: list[dict[str, tuple[float, float, float]]] = field(default_factory=list)
    digest: str = ""


def _joined_at(puppet: Puppet, row: JointRow, t: float) -> bool:
    if row.span is not None and not (row.span[0] - 1e-9 <= t <= row.span[1] + 1e-9):
        return False
    state = True
    for at, joined in puppet.events.get(row.id, ()):
        if at <= t + 1e-9:
            state = joined
    return state


def _along(path: Sequence[tuple[float, float]], f: float) -> tuple[float, float]:
    """The point a fraction ``f`` of the way along a polyline, by arc length."""
    if len(path) == 1:
        return path[0]
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])]
    total = sum(lengths)
    if total == 0:
        return path[0]
    goal = max(0.0, min(1.0, f)) * total
    for (a, b), seg in zip(zip(path, path[1:]), lengths):
        if goal <= seg or seg == lengths[-1] and (a, b) == (path[-2], path[-1]):
            r = goal / seg if seg else 0.0
            return (a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r)
        goal -= seg
    return path[-1]


def run_solve(doc: Any, puppet: Puppet, times: Sequence[float], settings: Settings) -> Run:
    """Solve ``puppet`` at each of ``times`` under the authored motion in ``doc``."""
    from dataclasses import replace

    from an.kinematics import Body, Point, Weld, WORLD, inputs_digest, solve
    from an.stage.timeline import _pose_for, evaluate_timeline, timeline_from_scene, transform_of

    nodes = _node_index(doc)
    timeline = timeline_from_scene(doc)
    order = list(puppet.bodies)
    dt = None if settings.mode == "pose" else (times[1] - times[0] if len(times) > 1 else None)
    run = Run(list(times), [], [], [], [], [], [], [], [])
    current: list[Any] | None = None
    joined_before: list[bool] | None = None
    frames_inputs: list[Any] = []
    for k, t in enumerate(times):
        pose = evaluate_timeline(timeline, t)
        world = _world_matrices(doc, order, pose, nodes)
        run.evaluated.append(world)
        local_now = {}
        for path in order:
            tr = transform_of(nodes[path], _pose_for(pose, path), frame_height=doc.meta.height)
            local_now[path] = (tr.x, tr.y, tr.rotation)
        run.local.append(local_now)
        authored_props = {(path, prop) for (path, prop) in pose if prop in SOLVED_CHANNELS}
        freed = {
            body
            for row in puppet.rows
            if row.frees and row.span is not None and row.span[0] - 1e-9 <= t <= row.span[1] + 1e-9
            for body in row.frees
        }
        targets: dict[str, dict[str, float]] = {}
        held: dict[str, set[str]] = {}
        welded: dict[str, float] = {}
        for path in order:
            info = puppet.bodies[path]
            x, y = _apply(world[path], info.pivot)
            theta = _decompose(world[path])[0]
            if path in puppet.held and path not in freed:
                channels = set(SOLVED_CHANNELS)
            else:
                channels = {prop for (p, prop) in authored_props if p == path}
                if info.parent_body is not None:
                    if "rotation" in channels:
                        welded[path] = _wrap(theta - _decompose(world[info.parent_body])[0])
                    channels = set()
                elif channels & {"x", "y"}:
                    channels |= {"x", "y"}
            held[path] = channels
            if channels:
                targets[path] = {c: v for c, v in (("x", x), ("y", y), ("rotation", theta)) if c in channels}
        joints = []
        joined_now = []
        for row in puppet.rows:
            j = row.joint
            on = _joined_at(puppet, row, t)
            if row.path is not None and row.span is not None:
                s0, s1 = row.span
                f = (t - s0) / (s1 - s0) if s1 > s0 else 1.0
                j = replace(j, b=Point(WORLD, *_along(row.path, f)))
            if row.child in welded:
                j = Weld(j.a, j.b, rest=welded[row.child], compliance=j.compliance)
            joints.append(replace(j, joined=on))
            joined_now.append(on)
        if current is None:
            current = []
            for path in order:
                info = puppet.bodies[path]
                x, y = _apply(world[path], info.pivot)
                left, top, w, h = info.box
                ox, oy = info.fraction(info.pivot)
                current.append(
                    Body(path, x=x, y=y, rotation=_decompose(world[path])[0], width=info.width(),
                         height=info.height(), origin=(ox, oy))
                )
        else:
            # A held body's channels are where the author put them NOW: start it there,
            # so a dynamic solve does not drag it from its last pose over the substeps.
            current = [
                b.posed(**{("rotation" if c == "rotation" else c): v for c, v in targets.get(b.name, {}).items()})
                if settings.mode == "pose" else b
                for b in current
            ]
        if joined_before is not None:
            # A joint the AUTHOR joins again (a `join`, a verb's span opening),
            # not one a conflict gave up for a frame: that one is refused, and
            # unreachable_pin or joint_violation says so.
            for j, (was, now) in enumerate(zip(joined_before, joined_now)):
                if now and not was:
                    run.snaps.append((k, j, _gap(current, joints[j])))
        options = dict(
            targets=targets or None, gravity=settings.gravity, dt=dt,
            iterations=settings.iterations, substeps=settings.substeps, damping=settings.damping,
        )
        directed = [
            j for j, row in enumerate(puppet.rows)
            if row.verb is not None and joints[j].joined and joints[j].b.body != WORLD
        ]
        if directed:
            # A verb holds ITS point where the other body is: that body is solved
            # without it first, and the verb then pins to where it went (a cup goes
            # to the hand; the hand is not pulled toward the cup).
            first = solve(current, [replace(jt, joined=False) if j in directed else jt
                                    for j, jt in enumerate(joints)], **options)
            for j in directed:
                b = joints[j].b
                joints[j] = replace(joints[j], b=Point(WORLD, *_body_point(first.pose(b.body), b)))
        r = solve(current, joints, **options)
        frames_inputs.append([joints, targets])
        current = list(r.bodies)
        joined_before = joined_now
        run.poses.append({b.name: (b.x, b.y, b.rotation) for b in r.bodies})
        run.held.append(held)
        run.dropped.append(r.dropped)
        run.unsatisfied.append(r.unsatisfied)
        run.limits.append(r.limit_violations)
        run.joined.append(joined_now)
    run.digest = inputs_digest(
        [_start_body(puppet, p) for p in order],
        [row.joint for row in puppet.rows],
        targets=[f[1] or None for f in frames_inputs],
        gravity=settings.gravity,
        mode=settings.mode, iterations=settings.iterations, substeps=settings.substeps,
        damping=settings.damping, joints_at=[f[0] for f in frames_inputs], times=list(times),
    )
    return run


def _body_point(body: Any, point: Any) -> tuple[float, float]:
    from an.kinematics import point_world

    return point_world(body, point)


def _start_body(puppet: Puppet, path: str) -> Any:
    from an.kinematics import Body

    info = puppet.bodies[path]
    return Body(path, width=info.width(), height=info.height(), origin=info.fraction(info.pivot))


def _gap(bodies: Sequence[Any], joint: Any) -> float:
    from an.kinematics.solver import _gap as gap

    return gap(bodies, joint)


# -----------------------------------------------------------------------------
# Emission
# -----------------------------------------------------------------------------


def _q(value: float, quantum: float) -> float:
    return round(value / quantum) * quantum + 0.0


def solve_pass(state: Any) -> None:
    """The ``solve`` compile pass (order :data:`SOLVE_ORDER`). A no-op for a shot
    that declares no joint and no verb."""
    shot = state.shot
    if not shot.joints and not _has_verb(shot) and not any(e.joints for e in shot.entities):
        if not any(
            _field(_descriptor(e, state.mall), "joints") for e in shot.entities if e.store
        ):
            return
    from an.stage.compile import _assemble_document, _lowerings

    extent = next(
        (r for r in (low.extent_resolver(state.vocab, products=state.products) for low in _lowerings()) if r),
        None,
    )
    decl = declarations(shot, state.mall, play_extent=extent)
    if decl.empty:
        return
    doc = _assemble_document(state, background="#000000")
    puppet = build_puppet(doc, shot, state.mall, decl, vocab=state.vocab)
    if not puppet.bodies:
        return
    settings = resolve_settings(shot, state.style_pack, puppet)
    times = frame_times(shot.duration, fps=state.fps, step_hz=state.step_hz)
    run = run_solve(doc, puppet, times, settings)
    overridden = _emit(state, doc, puppet, run, stepped=state.step_hz is not None)
    state.meta_extensions[SOLVE_EXTENSION] = _report(puppet, run, settings, overridden)


def _local_channels(
    puppet: Puppet, run: Run, k: int, path: str, solved_world: dict[str, Affine]
) -> tuple[float, float, float]:
    """Body ``path``'s node channels ``(x, y, rotation)`` at frame ``k``, from its
    solved pose and its parent's (solved, when the parent is a body)."""
    info = puppet.bodies[path]
    x, y, theta = run.poses[k][path]
    m = info.matrix(x, y, theta)
    solved_world[path] = m
    parent = solved_world.get(info.parent) if info.parent_body else None
    if parent is None:
        parent = run.evaluated[k].get(info.parent, _IDENTITY)
    inv = _invert(parent)
    lx, ly = _apply(inv, (x, y))
    local = _compose(inv, m)
    # The node's own transform is R(rotation) diag(scale_x, scale_y): its first
    # column is scale_x (cos, sin), so a negative scale_x turns the reading round.
    sign = -1.0 if info.flip_x else 1.0
    return lx, ly, math.atan2(local[1] * sign, local[0] * sign)


def _emit(state: Any, doc: Any, puppet: Puppet, run: Run, *, stepped: bool) -> list[dict[str, Any]]:
    from an.stage.serialize import (
        AnimationClipJSON,
        ChannelJSON,
        KeyframeJSON,
        PlacedClipJSON,
        TrackJSON,
    )
    order = list(puppet.bodies)
    values: dict[tuple[str, str], list[float]] = {}
    for k in range(len(run.times)):
        solved_world: dict[str, Affine] = {}
        for path in order:  # structure order: a parent before its children
            lx, ly, rot = _local_channels(puppet, run, k, path, solved_world)
            previous = values.get((path, "rotation"))
            ref = previous[-1] if previous else run.local[k][path][2]
            rot = ref + _wrap(rot - ref)
            channels = ("rotation",) if puppet.bodies[path].parent_body else SOLVED_CHANNELS
            for prop, v in (("x", lx), ("y", ly), ("rotation", rot)):
                if prop in channels:
                    values.setdefault((path, prop), []).append(v)
    duration = float(state.shot.duration)
    easing = "step" if stepped else "linear"
    clips: dict[str, list[Any]] = {}
    emitted: set[tuple[str, str]] = set()
    index = {prop: i for i, prop in enumerate(SOLVED_CHANNELS)}
    for (path, prop), vs in values.items():
        quantum = ANGLE_QUANTUM if prop == "rotation" else POSITION_QUANTUM
        qs = [_q(v, quantum) for v in vs]
        shown = [run.local[k][path][index[prop]] for k in range(len(run.times))]
        if all(abs(v - w) <= SAME_VALUE[prop] for v, w in zip(qs, shown)):
            continue  # the solve leaves it where the document already has it
        root = path.split("/", 1)[0]
        clips.setdefault(root, []).append(
            ChannelJSON(
                target=path,
                property=prop,
                keyframes=[
                    KeyframeJSON(time=_q(t, 1e-9), value=v, easing=easing) for t, v in zip(run.times, qs)
                ],
            )
        )
        emitted.add((path, prop))
    overridden = _overridden(state, emitted)
    for root, channels in clips.items():
        name = f"{SOLVE_CLIP_PREFIX}{root}"
        state.animations[name] = AnimationClipJSON(name=name, duration=max(0.001, duration), channels=channels)
        placed = PlacedClipJSON(animation_id=name, start_time=0.0, duration=max(0.001, duration))
        track = next((tr for tr in state.tracks if tr.target_root == root), None)
        if track is None:
            state.tracks.append(TrackJSON(target_root=root, clips=[placed]))
        else:
            track.clips.append(placed)
    return overridden


def _overridden(state: Any, emitted: set[tuple[str, str]]) -> list[dict[str, Any]]:
    """The authored spans a solved channel replaces: ``[{target, property, from, until}]``."""
    out = []
    for track in state.tracks:
        for placed in track.clips:
            clip = state.animations.get(placed.animation_id)
            if clip is None or placed.animation_id.startswith(SOLVE_CLIP_PREFIX):
                continue
            for ch in clip.channels:
                if (ch.target, ch.property) in emitted:
                    span = placed.duration if placed.duration is not None else clip.duration
                    out.append(
                        {
                            "target": ch.target,
                            "property": ch.property,
                            "from": round(placed.start_time, 6),
                            "until": round(placed.start_time + span, 6),
                        }
                    )
    return sorted(out, key=lambda d: (d["target"], d["property"], d["from"]))


def _spans(times: Sequence[float], frames: Sequence[int]) -> list[tuple[float, float]]:
    """Consecutive frame indices as ``(from, until)`` time spans."""
    out: list[tuple[float, float]] = []
    run_start = prev = None
    for k in sorted(frames):
        if prev is not None and k == prev + 1:
            prev = k
            continue
        if run_start is not None:
            out.append((times[run_start], times[prev]))
        run_start = prev = k
    if run_start is not None:
        out.append((times[run_start], times[prev]))
    return out


def _report(puppet: Puppet, run: Run, settings: Settings, overridden: list[dict[str, Any]]) -> dict[str, Any]:
    """``meta.extensions.solve``: what the solve ran with and what it could not hold."""
    from an.kinematics import SOLVER_VERSION

    def r2(v: float) -> float:
        return round(float(v), 2) + 0.0

    refused: dict[int, list[int]] = {}
    for k, dropped in enumerate(run.dropped):
        for j in dropped:
            refused.setdefault(j, []).append(k)
    gaps: dict[tuple[int, int], float] = {}
    for k, unsat in enumerate(run.unsatisfied):
        for j, gap in unsat:
            gaps[(j, k)] = gap if math.isfinite(gap) else 1e9
    dropped = []
    for j in sorted(refused):
        for a, b in _spans(run.times, refused[j]):
            worst = max(
                (gaps.get((j, k), 0.0) for k, t in enumerate(run.times) if a <= t <= b), default=0.0
            )
            entry = {"joint": j, "from": r2(a), "until": r2(b), "gap": r2(worst)}
            if puppet.rows[j].source == "pin":
                reach = _reach(puppet, run, j, run.times.index(a))
                if reach is not None:
                    entry["reach"] = {k: (r2(v) if isinstance(v, float) else v) for k, v in reach.items()}
            dropped.append(entry)
    return {
        "solver_version": SOLVER_VERSION,
        "mode": settings.mode,
        "iterations": settings.iterations,
        "substeps": settings.substeps,
        "gravity": [r2(v) for v in settings.gravity] if settings.gravity else None,
        "damping": settings.damping,
        "frames": len(run.times),
        "inputs": run.digest,
        "joints": [
            {"id": row.id, "type": type(row.joint).__name__.lower(), "bodies": row.label, "source": row.source, "where": row.where}
            for row in puppet.rows
        ],
        "dropped": dropped,
        "snaps": [{"joint": j, "at": r2(run.times[k]), "gap": r2(g)} for k, j, g in run.snaps],
        "overridden": overridden,
    }


def _reach(puppet: Puppet, run: Run, j: int, k: int) -> dict[str, Any] | None:
    """For a pin refused at frame ``k``: how far its chain reaches from the
    nearest body that holds it (the sum of its links), how far the target is,
    and the nearest place in reach on the line toward it."""
    from an.kinematics import point_world, Body

    row = puppet.rows[j]
    point, target = row.joint.a, row.joint.b
    by_child = {r.child: r for r in puppet.rows if r.source == "rig" and r.child}
    reach, body, at = 0.0, point.body, point
    seen = set()
    while body not in puppet.held and body in by_child and body not in seen:
        seen.add(body)
        link = by_child[body]
        joint_on_body = link.joint.b  # the hinge's child-side point (the rig's rows are (parent, child))
        reach += _distance(puppet.rest, puppet.bodies, at, joint_on_body)
        body, at = link.parent, link.joint.a
    if body not in puppet.held:
        return None

    def world(p: Any) -> tuple[float, float]:
        if p.body not in puppet.bodies:
            return (p.u, p.v)
        info = puppet.bodies[p.body]
        x, y, theta = run.poses[k][p.body]
        b = Body(p.body, x=x, y=y, rotation=theta, width=info.width(), height=info.height(),
                 origin=info.fraction(info.pivot))
        return point_world(b, p)

    ax, ay = world(at)
    tx, ty = world(target)
    dist = math.hypot(tx - ax, ty - ay)
    f = reach / dist if dist else 0.0
    return {
        "from": body,
        "reach": reach,
        "distance": dist,
        "place": [round(ax + (tx - ax) * f, 1) + 0.0, round(ay + (ty - ay) * f, 1) + 0.0],
    }


# -----------------------------------------------------------------------------
# Measuring a compiled document (the joint checks)
# -----------------------------------------------------------------------------


def joint_residuals(
    doc: Any,
    shot: Shot,
    mall: Mapping[str, Any],
    *,
    times: Sequence[float] | None = None,
) -> tuple[Puppet, list[float], list[list[float]], list[list[float]]]:
    """How far each joined joint of ``shot`` is from holding in ``doc``, at
    every frame: ``(puppet, times, gaps[k][j], range_excess[k][j])`` (px; and
    radians past a hinge's range, 0 inside it). An unjoined joint reads 0."""
    from an.kinematics import Body, Hinge, Weld, point_world, Distance, Slide, Contact
    from an.stage.timeline import evaluate_timeline, timeline_from_scene

    decl = declarations(shot, mall)
    puppet = build_puppet(doc, shot, mall, decl)
    nodes = _node_index(doc)
    timeline = timeline_from_scene(doc)
    if times is None:
        times = frame_times(shot.duration, fps=doc.meta.fps, step_hz=doc.meta.step_hz)
    gaps: list[list[float]] = []
    excess: list[list[float]] = []
    for t in times:
        pose = evaluate_timeline(timeline, t)
        world = _world_matrices(doc, list(puppet.bodies), pose, nodes)
        bodies: dict[str, Any] = {}
        for path, info in puppet.bodies.items():
            x, y = _apply(world[path], info.pivot)
            bodies[path] = Body(path, x=x, y=y, rotation=_decompose(world[path])[0], width=info.width(),
                                height=info.height(), origin=info.fraction(info.pivot))
        row_gaps, row_excess = [], []
        for row in puppet.rows:
            if not _joined_at(puppet, row, t):
                row_gaps.append(0.0)
                row_excess.append(0.0)
                continue
            j = row.joint
            if row.path is not None and row.span is not None:
                from an.kinematics import Point, WORLD

                s0, s1 = row.span
                j = type(j)(j.a, Point(WORLD, *_along(row.path, (t - s0) / (s1 - s0) if s1 > s0 else 1.0)),
                            length=j.length, mode=j.mode, compliance=j.compliance)

            def at(p, bodies=bodies):
                return point_world(bodies[p.body], p) if p.body in bodies else (p.u, p.v)

            if isinstance(j, (Slide, Contact)):
                gap = _segment_gap(at(j.point), at(j.start), at(j.end), one_sided=isinstance(j, Contact))
            else:
                (ax, ay), (bx, by) = at(j.a), at(j.b)
                gap = math.hypot(ax - bx, ay - by)
                if isinstance(j, Distance):
                    gap = {"equal": abs(gap - j.length), "at_most": max(0.0, gap - j.length),
                           "at_least": max(0.0, j.length - gap)}[j.mode]
            over = 0.0
            if isinstance(j, Hinge) and j.limits is not None:
                rel = _wrap(bodies[j.b.body].rotation - (bodies[j.a.body].rotation if j.a.body in bodies else 0.0) - (j.rest or 0.0))
                lo, hi = j.limits
                over = max(0.0, lo - rel, rel - hi)
            elif isinstance(j, Weld) and j.rest is not None and row.source != "rig":
                rel = _wrap(bodies[j.b.body].rotation - (bodies[j.a.body].rotation if j.a.body in bodies else 0.0) - j.rest)
                over = abs(rel)
            row_gaps.append(gap)
            row_excess.append(over)
        gaps.append(row_gaps)
        excess.append(row_excess)
    return puppet, list(times), gaps, excess


def _segment_gap(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float], *, one_sided: bool) -> float:
    tx, ty = b[0] - a[0], b[1] - a[1]
    length = math.hypot(tx, ty)
    if length == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    s = ((p[0] - a[0]) * tx + (p[1] - a[1]) * ty) / (length * length)
    if one_sided:
        if not 0.0 <= s <= 1.0:
            return 0.0  # off the segment's ends: nothing to stand on, nothing broken
        depth = ((p[0] - a[0]) * ty - (p[1] - a[1]) * tx) / length  # >0 on the free side
        return max(0.0, -depth)
    s = max(0.0, min(1.0, s))
    return math.hypot(p[0] - (a[0] + s * tx), p[1] - (a[1] + s * ty))
