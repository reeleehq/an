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

from an.base import PAINT_AFTER_PROPERTY
from an.ir.schema import JointSpec, Shot, gravity_vector
from an.stage.compile import CutoutCompileError

__all__ = [
    "SOLVE_ORDER",
    "SOLVE_CLIP_PREFIX",
    "SOLVE_EXTENSION",
    "solve_report",
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
#: A drawing this small on both sides (scene px) is a speck, not an extent: the
#: one-pixel "empty" key of a swap set (the transparent-part workaround).
SPECK_EXTENT: float = 2.0
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
#: The ``source`` of a joint row the hold layer adds: a hand's reach (a pull
#: along a moving goal, :mod:`an.stage.hold`).
REACH_SOURCE: str = "reach"
#: How close a solved value must be to what the document already shows for the
#: channel to be left unemitted: a few quanta (the round trip through stage
#: space costs float noise, never a visible move).
SAME_VALUE: dict[str, float] = {"x": 1e-5, "y": 1e-5, "rotation": 1e-6}
#: The same, for a held item's scale (a factor).
SAME_SCALE: float = 1e-6


class UnknownBodyError(CutoutCompileError):
    """A declaration names a body, a point or a joint the shot does not have.

    ``problems`` lists each one as ``(where, message)``, ``where`` relative to
    the shot (``joints/0``, ``actions/2``): what ``an validate``'s
    ``unknown_body`` check reports.
    """

    def __init__(self, message: str, problems: Sequence[tuple[str, str]]) -> None:
        super().__init__(message)
        self.problems = list(problems)


def solve_report(doc: Any) -> dict[str, Any]:
    """The solve's report recorded on a compiled document
    (``meta.extensions.solve``), ``{}`` when the pass recorded nothing: what
    ``an validate``'s joint and hold checks read (the ``holds`` entry is the
    hold layer's).

    >>> from types import SimpleNamespace as NS
    >>> solve_report(NS(meta=NS(extensions={SOLVE_EXTENSION: {"mode": "solve"}})))
    {'mode': 'solve'}
    >>> solve_report(NS(meta=NS(extensions=None)))
    {}
    """
    return (doc.meta.extensions or {}).get(SOLVE_EXTENSION) or {}


def _unknown_body_error(
    problems: Sequence[tuple[str, str]], *, shot_id: str
) -> UnknownBodyError:
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
    """Every joint and verb a shot declares, in solver order (structure first),
    and what it holds (:class:`an.stage.hold.HoldDeclarations`)."""

    joints: list[DeclaredJoint] = field(default_factory=list)
    verbs: list[Verb] = field(default_factory=list)
    #: ``(where, message)`` for a declaration that does not read (a descriptor's).
    problems: list[tuple[str, str]] = field(default_factory=list)
    #: The hold verbs and ``held_by`` overrides (:mod:`an.stage.hold`), or ``None``.
    holds: Any = None

    @property
    def empty(self) -> bool:
        return (
            not self.joints
            and not self.verbs
            and not self.problems
            and (self.holds is None or self.holds.empty)
        )


def shot_declares_solve(shot: Shot, mall: Mapping[str, Any] | None = None) -> bool:
    """Whether ``shot`` declares anything the solve acts on (the pass's gate).

    >>> shot_declares_solve(Shot(id="s"))
    False
    """
    return not declarations(
        shot, mall or {}, verbs=_has_verb(shot) or _declares_holds(shot)
    ).empty


def _declares_holds(shot: Shot) -> bool:
    from an.stage.hold import declares_holds

    return declares_holds(shot)


def solve_knobs(shot: Shot) -> dict[str, Any]:
    """The solve's render knobs for the shot-cache key: the solver's version, the
    shot's mode and effort as declared, and a digest of its declarations.

    >>> sorted(solve_knobs(Shot(id="s")))
    ['declared', 'hold_version', 'iterations', 'mode', 'solver_version', 'substeps']
    """
    import hashlib
    import json

    from an.kinematics import DFLT_ITERATIONS, DFLT_SUBSTEPS, SOLVER_VERSION
    from an.stage.hold import HOLD_VERSION

    own = shot.solve
    declared = {
        "joints": [j.model_dump(mode="json") for j in shot.joints],
        "entities": [
            [e.id, [j.model_dump(mode="json") for j in e.joints], e.overrides]
            for e in shot.entities
        ],
        "solve": own.model_dump(mode="json") if own is not None else None,
    }
    return {
        "solver_version": SOLVER_VERSION,
        "hold_version": HOLD_VERSION,
        "mode": (own.mode if own is not None else None) or "auto",
        "iterations": (
            own.iterations if own is not None and own.iterations else DFLT_ITERATIONS
        ),
        "substeps": (
            own.substeps if own is not None and own.substeps else DFLT_SUBSTEPS
        ),
        "declared": hashlib.sha256(
            json.dumps(declared, sort_keys=True, default=str).encode()
        ).hexdigest(),
    }


def _has_verb(shot: Shot) -> bool:
    from an.ir.compose import iter_actions
    from an.ir.joints import JOINT_ACTION_KINDS

    return any(
        getattr(node, "kind", None) in JOINT_ACTION_KINDS
        for action in shot.actions
        for node in iter_actions(action)
    )


def _is_rig_kind(entity: Any) -> bool:
    """Whether ``entity``'s store holds a rig descriptor (a prop, a genre's
    character): the only entries the solve reads, and the compile reads anyway,
    so a shot that declares nothing records no new asset read."""
    from an.genres.registry import entity_kind

    if entity.kind == "prop":
        return True
    kind = entity_kind(entity.kind)
    return kind is not None and kind.descriptor_kind is not None


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
        desc = _descriptor(entity, mall) if _is_rig_kind(entity) else None
        for k, raw in enumerate(
            _field(desc, "joints") or [] if desc is not None else []
        ):
            where = f"{entity.id} descriptor joints/{k}"
            try:
                spec = (
                    raw if isinstance(raw, JointSpec) else JointSpec.model_validate(raw)
                )
            except ValueError as e:
                out.problems.append(
                    (where, f"{entity.ref!r} declares a joint that does not read: {e}")
                )
                continue
            out.joints.append(_declared(spec, entity.id, where=where))
        for k, spec in enumerate(entity.joints):
            out.joints.append(
                _declared(spec, entity.id, where=f"entities/{i}/joints/{k}")
            )
    for k, spec in enumerate(shot.joints):
        out.joints.append(
            DeclaredJoint(
                spec=spec, a=spec.a, b=spec.b, end=spec.end, where=f"joints/{k}"
            )
        )
    if verbs:
        from an.ir.compose import flatten
        from an.ir.joints import JOINT_ACTION_KINDS

        for k, action in enumerate(shot.actions):
            for flat in flatten(action, play_extent=play_extent):
                if getattr(flat.action, "kind", None) in JOINT_ACTION_KINDS:
                    out.verbs.append(
                        Verb(flat.action, flat.start, flat.end, where=f"actions/{k}")
                    )
    if verbs or any(e.overrides and "held_by" in e.overrides for e in shot.entities):
        from an.stage.hold import hold_declarations

        holds = hold_declarations(shot, play_extent=play_extent)
        out.holds = None if holds.empty else holds
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
    return (
        a,
        b,
        cc,
        d,
        t.x - (a * t.pivot_x + cc * t.pivot_y),
        t.y - (b * t.pivot_x + d * t.pivot_y),
    )


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

    def fraction(
        self, local: tuple[float, float], mirrored: bool | None = None
    ) -> tuple[float, float]:
        """A local point as a fraction of this body's extent (the solver's Point),
        as drawn at rest, or ``mirrored`` (its x read the other way)."""
        left, top, w, h = self.box
        u, v = (local[0] - left) / w, (local[1] - top) / h
        mirrored = self.mirrored if mirrored is None else mirrored
        return (1.0 - u if mirrored else u), v

    def matrix(
        self, x: float, y: float, theta: float, geometry: "Geometry | None" = None
    ) -> Affine:
        """This body's node transform in stage space for a solved pose, at its
        rest scale or a frame's (``geometry``)."""
        sx, sy, mirrored = (
            (self.sx, self.sy, self.mirrored) if geometry is None else geometry[:3]
        )
        c, s = math.cos(theta), math.sin(theta)
        ex = -sx if mirrored else sx
        m = (c * ex, s * ex, -s * sy, c * sy, 0.0, 0.0)
        px, py = _apply(m, self.pivot)
        return (*m[:4], x - px, y - py)


#: A body's scale and mirroring at one frame: ``(sx, sy, mirrored, flip_x)``
#: (``flip_x``: the node's own ``scale_x`` is negative).
Geometry = tuple[float, float, bool, bool]


def _geometry_at(m: Affine, local_scale_x: float) -> Geometry:
    _theta, sx, sy, mirrored = _decompose(m)
    return (sx, sy, mirrored, local_scale_x < 0)


def _flip_point(p: Any, flips: Mapping[str, bool]) -> Any:
    from dataclasses import replace

    return replace(p, u=1.0 - p.u) if flips.get(p.body) else p


def _frame_joint(joint: Any, flips: Mapping[str, bool]) -> Any:
    """``joint`` for a frame in which the bodies in ``flips`` are drawn mirrored
    against their rest: their points read the other way, and an angle measured
    from a mirrored body turns the other way."""
    from dataclasses import replace

    from an.kinematics import Contact, Hinge, Slide, Weld

    if not any(flips.values()):
        return joint
    if isinstance(joint, (Slide, Contact)):
        return replace(
            joint,
            point=_flip_point(joint.point, flips),
            start=_flip_point(joint.start, flips),
            end=_flip_point(joint.end, flips),
        )
    out = replace(joint, a=_flip_point(joint.a, flips), b=_flip_point(joint.b, flips))
    if isinstance(out, (Hinge, Weld)) and out.rest is not None:
        anchor = joint.a.body if joint.a.body in flips else joint.b.body
        if flips.get(anchor):
            out = replace(out, rest=-out.rest)
            if isinstance(out, Hinge) and out.limits is not None:
                out = replace(out, limits=(-out.limits[1], -out.limits[0]))
    return out


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
    #: A goal that moves frame by frame (a hand's reach): its stage point at
    #: each of the solve's frames, ``None`` outside the span.
    track: tuple[tuple[float, float] | None, ...] | None = None
    #: Bodies whose authored channels this row replaces over its span (the
    #: chain a reaching hand hangs from).
    overrides: tuple[str, ...] = ()


@dataclass
class Puppet:
    """A shot's bodies (structure first) and joints, ready to solve."""

    bodies: dict[str, BodyInfo]
    rows: list[JointRow]
    held: set[str]  # bodies held where the author put them (roots, fixed entities)
    events: dict[str, list[tuple[float, bool]]]  # joint id -> [(time, joined)]
    rest: dict[str, Affine]  # body -> its rest (declared) stage transform
    #: The holder points the hold verbs name: ``(ref, side) -> Located``.
    located: dict[tuple[str, str], Any] = field(default_factory=dict)
    #: The built tree's nodes by path.
    nodes: dict[str, Any] = field(default_factory=dict)
    #: Per-frame rotation targets the hold layer gives bodies (a lean, and what
    #: rides on it): ``body -> [rotation or None, per frame]``.
    lean: dict[str, list[float | None]] = field(default_factory=dict)


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
    """The extent a node's body has: its drawing, or a :data:`DFLT_BODY_EXTENT`
    square about its pivot when it draws nothing, or a speck.

    A drawing under :data:`SPECK_EXTENT` on both sides (a one-pixel "empty" key
    of a swap set, the transparent-part workaround) is not an extent: as a body
    it would be a speck with its pivot many widths away, whose rotation the
    solver cannot hold, and the part would drift off its joint. A small drawing
    (a bead, a button) keeps its own box.

    >>> from an.stage.serialize import NodeJSON, VisualJSON
    >>> _local_box(NodeJSON(name="speck", visual=VisualJSON(width=1, height=1, anchor_y=68)))
    (-5.0, -5.0, 10.0, 10.0)
    """
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
        if w >= SPECK_EXTENT or h >= SPECK_EXTENT:
            return (-float(v.anchor_x) * w, -float(v.anchor_y) * h, w, h)
    e = DFLT_BODY_EXTENT
    return (t.pivot_x - e / 2.0, t.pivot_y - e / 2.0, e, e)


def _world_matrices(
    doc: Any, paths: Sequence[str], pose: Any, nodes: Mapping[str, Any]
) -> dict[str, Affine]:
    """``{path: stage transform}`` for ``paths`` and every ancestor, under ``pose``."""
    from an.stage.timeline import _pose_for, transform_of

    height = doc.meta.height
    out: dict[str, Affine] = {"": _IDENTITY}

    def world(path: str) -> Affine:
        if path in out:
            return out[path]
        parent = _parent_path(path, nodes)
        local = _affine_of(
            transform_of(nodes[path], _pose_for(pose, path), frame_height=height)
        )
        out[path] = _compose(world(parent), local)
        return out[path]

    for p in paths:
        world(p)
    return out


def _rig_of(
    entity: Any, mall: Mapping[str, Any], nodes: Mapping[str, Any], vocab: Any = None
) -> Any:
    """The entity's :class:`~an.stage.rig.RigStructure`, or ``None`` for a non-rig."""
    from an.ir.migrate import KINDS, migrate
    from an.stage.rig import rig_structure, slot_node_paths, _RigView

    desc = (
        (getattr(vocab, "descriptors", None) or {}).get(entity.id)
        if vocab is not None
        else None
    )
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
    built = {
        slot
        for slot, rel in slot_node_paths(view).items()
        if f"{entity.id}/{rel}" in nodes
    }
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
    problems: list[tuple[str, str]] = list(decl.problems)
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
    holds = decl.holds
    solved_by_joints = set(named)
    if holds is not None:
        for ref, _where, _side in holds.refs:
            note(ref)
        for ref, where, _side in holds.refs:
            holder = ref.partition("@")[0].split("/", 1)[0]
            if holder in holds.items:
                problems.append(
                    (
                        where,
                        f"{ref!r}: {holder!r} is itself held (grasp/place/release or "
                        "`held_by`), and an item that holds another is not built: hold "
                        "the outer one, or make the inner one part of its drawing",
                    )
                )
        for item, where in sorted(holds.items.items()):
            if item in solved_by_joints:
                problems.append(
                    (
                        where,
                        f"{item!r} is held (grasp/place/release) and also named by a joint or a "
                        "pin/pull: an item is moved by what holds it, never by both",
                    )
                )
        named = [eid for eid in named if eid not in holds.items]

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
        # A holder that never moves a hand (a figurine's socket, a shelf) and
        # no joint names is held where it is put: nothing of it is solved.
        fixed = bool(overrides.get(FIXED_OVERRIDE)) or (
            holds is not None
            and eid not in solved_by_joints
            and eid not in holds.movers
        )
        if rig is None or not rig.bodies:
            path = eid
            bodies[path] = BodyInfo(
                path, eid, "", None, _local_box(nodes[path]), _pivot(nodes[path]), True
            )
            if fixed or free is not True:
                held.add(path)
            continue
        for slot, rel in rig.bodies.items():
            path = f"{eid}/{rel}"
            parent = _parent_path(path, nodes)
            is_root = slot in rig.roots
            bodies[path] = BodyInfo(
                path,
                eid,
                parent,
                None,
                _local_box(nodes[path]),
                _pivot(nodes[path]),
                is_root,
            )
            freed = free is True or (isinstance(free, (list, tuple)) and slot in free)
            if fixed or (is_root and not freed):
                held.add(path)
        for joint in rig.joints:
            structural.append((joint, eid))
    for b in bodies.values():
        if b.parent in bodies:
            b.parent_body = b.parent

    def depth(path: str) -> int:
        d, cursor = 0, bodies[path].parent_body
        while cursor is not None and d <= len(bodies):
            d, cursor = d + 1, bodies[cursor].parent_body
        return d

    # Parents before children whatever the draw order (a back arm drawn behind its
    # torso): a child's channels are read off its parent's solved pose.
    index = {p: i for i, p in enumerate(bodies)}
    bodies = {p: bodies[p] for p in sorted(bodies, key=lambda p: (depth(p), index[p]))}

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
            _node_rest(
                f"{eid}/{rig.bodies.get(anchor.on) or _slot_path(eid, anchor.on, nodes)}"
            )
            if anchor.on is not None
            else _node_rest(eid)
        )
        return _apply(frame, anchor.offset)

    landmark_cache: dict[str, Mapping[str, Any]] = {}

    def landmarks_of(eid: str) -> Mapping[str, Any]:
        """The named points a genre declares for ``eid``'s rig beyond its bones
        (:attr:`an.genres.EntityKind.landmarks`: a character's hands)."""
        if eid not in landmark_cache:
            from an.genres.registry import entity_kind

            kind = entity_kind(entities[eid].kind)
            hook = getattr(kind, "landmarks", None) if kind is not None else None
            found: Mapping[str, Any] = {}
            if hook is not None and rigs.get(eid) is not None:
                desc = (
                    (getattr(vocab, "descriptors", None) or {}).get(eid)
                    if vocab is not None
                    else None
                ) or _descriptor(entities[eid], mall)
                try:
                    found = dict(hook(desc) or {}) if desc is not None else {}
                except Exception:  # noqa: BLE001 - a genre that cannot say names nothing
                    found = {}
            landmark_cache[eid] = found
        return landmark_cache[eid]

    def locate(ref: Any, *, where: str, side: str) -> Any:
        """A reference as ``Located(body, local, frame, node)`` (a point of a
        body, in its node's own coordinates, and the frame of the node named),
        a world ``Point``, or ``None`` after noting the problem.

        ``side`` says what a reference with no ``@`` means: ``"a"`` (and
        ``"socket"``) the node's pivot, ``"b"`` the centre of its drawing,
        ``"hand"`` the far end of the body from its pivot (its end effector).
        """
        if (
            isinstance(ref, (list, tuple))
            and len(ref) == 2
            and all(isinstance(v, (int, float)) for v in ref)
        ):
            return Point(WORLD, float(ref[0]), float(ref[1]))
        if not isinstance(ref, str):
            problems.append(
                (
                    where,
                    f"{ref!r} is not a body reference (`body[@point]`, `world@x,y`, or [x, y])",
                )
            )
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
        landmark = (
            landmarks_of(eid).get(at)
            if at
            and _numbers(at) is None
            and not (rigs.get(eid) is not None and at in rigs[eid].anchors)
            else None
        )
        if landmark is not None:
            slot, fraction = landmark
            rig = rigs.get(eid)
            if rig is None or slot not in rig.bodies:
                problems.append(
                    (
                        where,
                        f"{ref!r}: {at!r} names part {slot!r}, which {eid!r} does not draw",
                    )
                )
                return None
            node_path = f"{eid}/{rig.bodies[slot]}"
            at = "" if fraction is None else f"{fraction[0]},{fraction[1]}"
            side = "hand" if fraction is None else side
        else:
            node_path = (
                _slot_path(eid, head.split("/", 1)[1], nodes, rigs.get(eid))
                if "/" in head
                else head
            )
            # A bone named on an entity with several root parts (`ned@hand_r`)
            # is a point of the part that bone carries: it needs no `ned/<part>`
            # (with one root, the reference is that root's, as it always was).
            carrier = (
                _bone_carrier(rigs[eid], at)
                if "/" not in head
                and rigs.get(eid) is not None
                and len(rigs[eid].roots) > 1
                else None
            )
            if carrier is not None:
                node_path = f"{eid}/{rigs[eid].bodies[carrier]}"
        if node_path not in nodes:
            near = sorted(p for p in nodes if p.split("/", 1)[0] == eid)
            problems.append(
                (where, f"{ref!r}: no node {node_path!r}; {eid!r} has {near}")
            )
            return None
        if node_path == eid and rigs.get(eid) is not None and rigs[eid].bodies:
            roots = rigs[eid].roots
            if len(roots) != 1:
                problems.append(
                    (
                        where,
                        f"{ref!r}: {eid!r} has {len(roots)} root parts {list(roots)}; name the part (`{eid}/<part>`)",
                    )
                )
                return None
            node_path = f"{eid}/{rigs[eid].bodies[roots[0]]}"
        found = body_and_local(node_path)
        if found is None:
            problems.append(
                (where, f"{ref!r}: {node_path!r} is on no body of the shot")
            )
            return None
        body, inner = found
        node = nodes[node_path]
        if not at:
            if side == "hand" and node_path == body:
                local_on_node = end_effector(_local_box(node), _pivot(node))
            elif side in ("a", "socket", "hand"):
                local_on_node = _pivot(node)
            else:
                local_on_node = _centre(_local_box(node))
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
                    named_points = sorted(landmarks_of(eid))
                    also = f", named points: {named_points}" if named_points else ""
                    problems.append(
                        (
                            where,
                            f"{ref!r}: {at!r} is not a bone of {eid!r} (bones: {known}{also}) nor a fraction `u,v`",
                        )
                    )
                    return None
                local = _apply(_invert(rest[body]), world)
        return Located(body, local, inner, node_path)

    def resolve(ref: Any, *, where: str, side: str) -> Any:
        """A reference as a solver Point (and its body), or ``None`` after noting the problem."""
        found = locate(ref, where=where, side=side)
        if found is None or not isinstance(found, Located):
            return found
        u, v = bodies[found.body].fraction(found.local)
        return Point(found.body, u, v)

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
        limits = (
            joint.limits if dj is None or dj.spec.limits is None else dj.spec.limits
        )
        give = 0.0 if dj is None else dj.spec.give
        if kind == "weld":
            row = Weld(a, b, rest=relative, compliance=give)
        else:
            row = Hinge(
                a,
                b,
                limits=_limits(limits, mirrored=_flips(rest[parent])),
                rest=relative,
                compliance=give,
            )
        rows.append(
            JointRow(
                row,
                f"{parent} — {child}",
                "rig",
                dj.spec.id if dj and dj.spec.name else child,
                dj.where if dj else f"{eid} rig bone {joint.bone!r}",
                child=child,
                parent=parent,
            )
        )
    for child, dj in overrides_by_child.items():
        problems.append(
            (
                dj.where,
                f"{dj.a!r}: a {dj.spec.type} with no `b` is a rig part's own joint, and {child!r} hangs from no parent part",
            )
        )

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
            row = Hinge(
                pb,
                pa,
                limits=_limits(spec.limits, mirrored=False),
                rest=_relative_points(rest, pb, pa, bodies),
                compliance=spec.give,
            )
        elif spec.type == "weld":
            row = Weld(
                pb,
                pa,
                rest=_relative_points(rest, pb, pa, bodies),
                compliance=spec.give,
            )
        elif spec.type in ("distance", "string", "rod"):
            length = (
                spec.length
                if spec.length is not None
                else _distance(rest, bodies, pa, pb)
            )
            row = Distance(
                pa,
                pb,
                length=float(length),
                mode=spec.distance_mode,
                compliance=spec.give,
            )
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
            events.setdefault(action.joint, []).append(
                (verb.start, action.kind == "join")
            )
            continue
        open_ended = (action.duration if action.kind == "pin" else action.over) is None
        span = (verb.start, duration if open_ended else verb.end)
        pa = resolve(action.point, where=verb.where, side="a")
        path = None
        to = action.to
        if (
            action.kind == "pull"
            and isinstance(to, list)
            and to
            and isinstance(to[0], (list, tuple))
        ):
            path = tuple((float(p[0]), float(p[1])) for p in to)
            pb = Point(WORLD, *path[0])
        else:
            pb = resolve(to, where=verb.where, side="b")
        if pa is None or pb is None:
            continue
        if action.kind == "pin":
            row = Pin(pa, pb)
        else:
            row = Distance(
                pa, pb, length=0.0, mode="at_most", compliance=float(action.give)
            )
        rows.append(
            JointRow(
                row,
                f"{action.point} — {_ref_text(to)}",
                action.kind,
                f"{action.kind}:{verb.where}",
                verb.where,
                span=span,
                path=path,
                frees=(pa.body,),
                verb=action.kind,
            )
        )
    ids = {row.id for row in rows}
    for jid in events:
        if jid not in ids:
            problems.append(
                (
                    "actions",
                    f"join/unjoin names {jid!r}, which is no joint of this shot (joints: {sorted(ids)})",
                )
            )
    for jid in events:
        events[jid].sort(key=lambda e: e[0])
    # 4. What holds things: every holder point a hold verb names.
    located: dict[tuple[str, str], Located] = {}
    if holds is not None:
        for ref, where, side in holds.refs:
            if ref.partition("@")[0].split("/", 1)[0] in holds.items:
                continue  # an item holding another: said above
            found = locate(ref, where=where, side=side)
            if isinstance(found, Located):
                located[(ref, side)] = found
            elif found is not None:
                problems.append(
                    (
                        where,
                        f"{ref!r}: a stage point holds nothing; name a body's point "
                        "(`nap/arm_r@hand`), or `ground`",
                    )
                )
    if problems:
        raise _unknown_body_error(problems, shot_id=shot.id)
    return Puppet(
        bodies=bodies,
        rows=rows,
        held=held,
        events=events,
        rest={p: rest[p] for p in bodies},
        located=located,
        nodes=nodes,
    )


@dataclass(frozen=True)
class Located:
    """A point of a body: ``local`` in the body node's own coordinates;
    ``frame`` the named node's rest transform in the body's frame (its
    orientation, for a socket); ``node`` the node the reference named."""

    body: str
    local: tuple[float, float]
    frame: Affine
    node: str


#: How far inside its far end a body's end effector sits, as a fraction of its
#: length: the palm of a hand drawn at the end of an arm, not the fingertips.
DFLT_EFFECTOR_INSET: float = 0.04


def end_effector(
    box: tuple[float, float, float, float],
    pivot: tuple[float, float],
    *,
    inset: float = DFLT_EFFECTOR_INSET,
) -> tuple[float, float]:
    """The point of a body farthest from its pivot along its long axis, a
    little inside its end: where an arm hung from its shoulder has its hand.

    >>> end_effector((-8.0, 0.0, 16.0, 100.0), (0.0, 0.0))   # an arm hanging down
    (0.0, 96.0)
    >>> end_effector((-100.0, -5.0, 100.0, 10.0), (0.0, 0.0))  # a crane's jib, pointing left
    (-96.0, 0.0)
    """
    left, top, w, h = box
    if h >= w:
        ends = ((left + w / 2.0, top), (left + w / 2.0, top + h))
        length = h
    else:
        ends = ((left, top + h / 2.0), (left + w, top + h / 2.0))
        length = w
    far = max(ends, key=lambda e: (math.hypot(e[0] - pivot[0], e[1] - pivot[1]), e))
    near = ends[0] if far is ends[1] else ends[1]
    f = inset * length / max(1e-9, math.hypot(far[0] - near[0], far[1] - near[1]))
    return (
        far[0] + (near[0] - far[0]) * f + 0.0,
        far[1] + (near[1] - far[1]) * f + 0.0,
    )


def _bone_carrier(rig: Any, bone: str) -> str | None:
    """The slot whose part a bone is a point of: the part drawn on that bone
    (the one named like it, else the first in draw order, as the rig's own joints pick it), or ``None`` for a bone no
    part sits on (a landmark such as a prop's ``grip``) or a name that is no bone.

    >>> from types import SimpleNamespace as NS
    >>> rig = NS(anchors={"hand_r": 1, "grip": 1}, body_bone={"hand_r": "hand_r", "fist": "hand_r", "torso": "torso"})
    >>> _bone_carrier(rig, "hand_r"), _bone_carrier(rig, "grip"), _bone_carrier(rig, "nope")
    ('hand_r', None, None)
    """
    if not bone or bone not in rig.anchors:
        return None
    slots = [slot for slot, b in rig.body_bone.items() if b == bone]  # draw order
    if not slots:
        return None
    return bone if bone in slots else slots[0]


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


def _relative(
    rest: Mapping[str, Affine], parent: str, child: str, bodies: Mapping[str, BodyInfo]
) -> float:
    return _wrap(_decompose(rest[child])[0] - _decompose(rest[parent])[0])


def _relative_points(
    rest: Mapping[str, Affine], a: Any, b: Any, bodies: Mapping[str, BodyInfo]
) -> float:
    ta = _decompose(rest[a.body])[0] if a.body in rest else 0.0
    tb = _decompose(rest[b.body])[0] if b.body in rest else 0.0
    return _wrap(tb - ta)


def _point_at(
    rest: Mapping[str, Affine], bodies: Mapping[str, BodyInfo], p: Any
) -> tuple[float, float]:
    if p.body not in bodies:
        return (p.u, p.v)
    info = bodies[p.body]
    left, top, w, h = info.box
    u = 1.0 - p.u if info.mirrored else p.u
    return _apply(rest[p.body], (left + u * w, top + p.v * h))


def _distance(
    rest: Mapping[str, Affine], bodies: Mapping[str, BodyInfo], a: Any, b: Any
) -> float:
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
    # A declared string hangs things (follow-through); a `pull` is a goal, met in either mode.
    strings = any(
        isinstance(r.joint, Distance)
        and r.joint.mode == "at_most"
        and r.source == "joint"
        for r in puppet.rows
    )
    mode = (own.mode if own is not None else None) or (
        "dynamic" if gravity or strings else "pose"
    )
    damping = (
        own.damping if own is not None and own.damping is not None else pack_damping
    )
    return Settings(
        mode=mode,
        gravity=gravity if mode == "dynamic" else None,
        damping=float(damping) if damping is not None else DFLT_DAMPING,
        iterations=(
            own.iterations if own is not None and own.iterations else DFLT_ITERATIONS
        ),
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
    #: per frame: body -> its scale and mirroring as the document shows it
    geometry: list[dict[str, Geometry]] = field(default_factory=list)
    #: per frame: a non-body path (``extra_paths``) -> its node's channels
    #: ``(x, y, rotation, scale_x, scale_y)`` as the document shows them
    extra: list[dict[str, tuple[float, ...]]] = field(default_factory=list)
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


def run_solve(
    doc: Any,
    puppet: Puppet,
    times: Sequence[float],
    settings: Settings,
    *,
    extra_paths: Sequence[str] = (),
) -> Run:
    """Solve ``puppet`` at each of ``times`` under the authored motion in ``doc``.

    ``extra_paths`` are nodes that are not bodies whose authored transforms the
    run records too (``evaluated``, ``extra``): the items the hold layer moves."""
    from dataclasses import replace

    from an.kinematics import Body, Point, Weld, WORLD, inputs_digest, solve
    from an.stage.timeline import (
        _pose_for,
        evaluate_timeline,
        timeline_from_scene,
        transform_of,
    )

    nodes = _node_index(doc)
    timeline = timeline_from_scene(doc)
    order = list(puppet.bodies)
    dt = (
        None
        if settings.mode == "pose"
        else (times[1] - times[0] if len(times) > 1 else None)
    )
    run = Run(list(times), [], [], [], [], [], [], [], [])
    parent_of = {
        row.child: row.parent
        for row in puppet.rows
        if row.source == "rig" and row.child is not None and row.parent is not None
    }
    ever_driven = _bodies_ever_driven(puppet, parent_of)
    current: list[Any] | None = None
    joined_before: list[bool] | None = None
    frames_inputs: list[Any] = []
    for k, t in enumerate(times):
        pose = evaluate_timeline(timeline, t)
        world = _world_matrices(doc, [*order, *extra_paths], pose, nodes)
        run.evaluated.append(world)
        if extra_paths:
            extra = {}
            for path in extra_paths:
                tr = transform_of(
                    nodes[path], _pose_for(pose, path), frame_height=doc.meta.height
                )
                extra[path] = (tr.x, tr.y, tr.rotation, tr.scale_x, tr.scale_y)
            run.extra.append(extra)
        local_now, geometry = {}, {}
        for path in order:
            tr = transform_of(
                nodes[path], _pose_for(pose, path), frame_height=doc.meta.height
            )
            local_now[path] = (tr.x, tr.y, tr.rotation)
            geometry[path] = _geometry_at(world[path], tr.scale_x)
        run.local.append(local_now)
        run.geometry.append(geometry)
        flips = {p: geometry[p][2] != puppet.bodies[p].mirrored for p in order}
        authored_props = {
            (path, prop) for (path, prop) in pose if prop in SOLVED_CHANNELS
        }
        freed = {
            body
            for row in puppet.rows
            if row.frees
            and row.span is not None
            and row.span[0] - 1e-9 <= t <= row.span[1] + 1e-9
            for body in row.frees
        }
        # A reaching hand's chain: the reach, not the authored channels, moves it.
        overridden = {
            body
            for row in puppet.rows
            if row.overrides
            and row.span is not None
            and row.span[0] - 1e-9 <= t <= row.span[1] + 1e-9
            for body in row.overrides
        }
        targets: dict[str, dict[str, float]] = {}
        held: dict[str, set[str]] = {}
        welded: dict[str, float] = {}
        driven = (
            _driven_bodies(puppet, t, parent_of, always=ever_driven)
            if settings.mode == "pose"
            else None
        )
        for path in order:
            info = puppet.bodies[path]
            x, y = _apply(world[path], info.pivot)
            theta = _decompose(world[path])[0]
            if path in overridden:
                channels = set()
            elif path in puppet.held and path not in freed:
                channels = set(SOLVED_CHANNELS)
            else:
                channels = {prop for (p, prop) in authored_props if p == path}
                if driven is not None and path not in driven and path not in freed:
                    # A passenger (no joint, verb or reach acts on it): in pose
                    # mode it keeps the angle the document gives it, so a body
                    # carried along by its parent does not swing about its joint.
                    channels |= {"rotation"}
                if info.parent_body is not None:
                    if "rotation" in channels:
                        welded[path] = _wrap(
                            theta - _decompose(world[info.parent_body])[0]
                        )
                    channels = set()
                elif channels & {"x", "y"}:
                    channels |= {"x", "y"}
            lean = puppet.lean.get(path)
            if lean is not None and lean[k] is not None:
                # The hold layer turns it (a body bending to reach, or riding one).
                welded.pop(path, None)
                channels = channels | {"rotation"}
                theta = lean[k]
            held[path] = channels
            if channels:
                targets[path] = {
                    c: v
                    for c, v in (("x", x), ("y", y), ("rotation", theta))
                    if c in channels
                }
        joints = []
        joined_now = []
        for row in puppet.rows:
            j = _frame_joint(row.joint, flips)
            on = _joined_at(puppet, row, t)
            if row.track is not None:
                goal = row.track[k] if k < len(row.track) else None
                if goal is not None:
                    j = replace(j, b=Point(WORLD, *goal))
            elif row.path is not None and row.span is not None:
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
                current.append(
                    Body(path, x=x, y=y, rotation=_decompose(world[path])[0])
                )
        else:
            # A held body's channels are where the author put them NOW: start it there,
            # so a dynamic solve does not drag it from its last pose over the substeps.
            current = [
                b.posed(
                    **{
                        ("rotation" if c == "rotation" else c): v
                        for c, v in targets.get(b.name, {}).items()
                    }
                )
                if settings.mode == "pose"
                else b
                for b in current
            ]
        # This frame's extent and mirroring (an authored scale or flip), read
        # from the document: the points are fractions of it.
        current = [
            replace(
                b,
                width=puppet.bodies[b.name].box[2] * geometry[b.name][0],
                height=puppet.bodies[b.name].box[3] * geometry[b.name][1],
                origin=puppet.bodies[b.name].fraction(
                    puppet.bodies[b.name].pivot, geometry[b.name][2]
                ),
            )
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
            targets=targets or None,
            gravity=settings.gravity,
            dt=dt,
            iterations=settings.iterations,
            substeps=settings.substeps,
            damping=settings.damping,
        )
        directed = [
            j
            for j, row in enumerate(puppet.rows)
            if row.verb is not None and joints[j].joined and joints[j].b.body != WORLD
        ]
        if directed:
            # A verb holds ITS point where the other body is: that body is solved
            # without it first, and the verb then pins to where it went (a cup goes
            # to the hand; the hand is not pulled toward the cup).
            first = solve(
                current,
                [
                    replace(jt, joined=False) if j in directed else jt
                    for j, jt in enumerate(joints)
                ],
                **options,
            )
            for j in directed:
                b = joints[j].b
                joints[j] = replace(
                    joints[j], b=Point(WORLD, *_body_point(first.pose(b.body), b))
                )
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
        mode=settings.mode,
        iterations=settings.iterations,
        substeps=settings.substeps,
        damping=settings.damping,
        joints_at=[f[0] for f in frames_inputs],
        times=list(times),
    )
    return run


def _driven_bodies(
    puppet: Puppet, t: float, parent_of: Mapping[str, str], *, always: set[str]
) -> set[str]:
    """The bodies something other than their own rig acts on at ``t``, and
    every body they hang from; the rest are passengers.

    A joint or a ``pin``/``pull`` makes its bodies driven for the WHOLE shot
    (``always``, from :func:`_bodies_ever_driven`): after a pin's span the part
    stays where the pin left it, as it always did, instead of snapping back to
    its document angle. A hand's reach (the hold layer's row) drives only over
    its span: it starts from, and retracts to, where the part is as a passenger,
    so the hand-off is continuous."""
    out: set[str] = set(always)
    for row in puppet.rows:
        if row.source != REACH_SOURCE or not _joined_at(puppet, row, t):
            continue
        _add_row_bodies(row, parent_of, out)
    return out


def _bodies_ever_driven(puppet: Puppet, parent_of: Mapping[str, str]) -> set[str]:
    """Every body a joint or a verb (not a rig's own joint, not a reach) names
    at any time, and every body they hang from."""
    out: set[str] = set()
    for row in puppet.rows:
        if row.source in ("rig", REACH_SOURCE):
            continue
        _add_row_bodies(row, parent_of, out)
    return out


def _add_row_bodies(row: JointRow, parent_of: Mapping[str, str], out: set[str]) -> None:
    from an.kinematics import WORLD

    j = row.joint
    for p in (getattr(j, n, None) for n in ("a", "b", "point", "start", "end")):
        body = getattr(p, "body", None)
        while body is not None and body != WORLD and body not in out:
            out.add(body)
            body = parent_of.get(body)
    for body in row.frees:
        cursor = body
        while cursor is not None and cursor not in out:
            out.add(cursor)
            cursor = parent_of.get(cursor)


def _body_point(body: Any, point: Any) -> tuple[float, float]:
    from an.kinematics import point_world

    return point_world(body, point)


def _start_body(puppet: Puppet, path: str) -> Any:
    from an.kinematics import Body

    info = puppet.bodies[path]
    return Body(
        path, width=info.width(), height=info.height(), origin=info.fraction(info.pivot)
    )


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
    if (
        not shot.joints
        and not _has_verb(shot)
        and not any(e.joints for e in shot.entities)
        and not _declares_holds(shot)
    ):
        if not any(
            _field(_descriptor(e, state.mall), "joints")
            for e in shot.entities
            if e.store and _is_rig_kind(e)
        ):
            return
    from an.stage.compile import _assemble_document, _lowerings

    extent = next(
        (
            r
            for r in (
                low.extent_resolver(state.vocab, products=state.products)
                for low in _lowerings()
            )
            if r
        ),
        None,
    )
    decl = declarations(shot, state.mall, play_extent=extent)
    if decl.empty:
        return
    doc = _assemble_document(state, background="#000000")
    puppet = build_puppet(doc, shot, state.mall, decl, vocab=state.vocab)
    if not puppet.bodies and decl.holds is None:
        return
    settings = resolve_settings(shot, state.style_pack, puppet)
    times = frame_times(shot.duration, fps=state.fps, step_hz=state.step_hz)
    held_channels: dict[tuple[str, str], tuple[list[float], list[float]]] = {}
    paint_hosts: dict[str, list[tuple[float, str]]] = {}
    holds_report = None
    if decl.holds is not None:
        from an.stage.hold import HOLDS_REPORT, solve_holds

        run, held_channels, paint_hosts, holds_report = solve_holds(
            state, doc, puppet, decl, settings, times
        )
    else:
        run = run_solve(doc, puppet, times, settings)
    overridden = _emit(
        state,
        doc,
        puppet,
        run,
        stepped=state.step_hz is not None,
        extra=held_channels,
        paint=paint_hosts,
    )
    report = _report(puppet, run, settings, overridden)
    if holds_report is not None:
        report[HOLDS_REPORT] = holds_report
    state.meta_extensions[SOLVE_EXTENSION] = report


def _local_channels(
    puppet: Puppet, run: Run, k: int, path: str, solved_world: dict[str, Affine]
) -> tuple[float, float, float]:
    """Body ``path``'s node channels ``(x, y, rotation)`` at frame ``k``, from its
    solved pose and its parent's (solved, when the parent is a body)."""
    info = puppet.bodies[path]
    x, y, theta = run.poses[k][path]
    geometry = run.geometry[k][path]
    m = info.matrix(x, y, theta, geometry)
    solved_world[path] = m
    parent = solved_world.get(info.parent) if info.parent_body else None
    if parent is None:
        parent = run.evaluated[k].get(info.parent, _IDENTITY)
    inv = _invert(parent)
    lx, ly = _apply(inv, (x, y))
    local = _compose(inv, m)
    # The node's own transform is R(rotation) diag(scale_x, scale_y): its first
    # column is scale_x (cos, sin), so a negative scale_x turns the reading round.
    sign = -1.0 if geometry[3] else 1.0
    return lx, ly, math.atan2(local[1] * sign, local[0] * sign)


def _emit(
    state: Any,
    doc: Any,
    puppet: Puppet,
    run: Run,
    *,
    stepped: bool,
    extra: Mapping[tuple[str, str], tuple[Sequence[float], Sequence[float]]]
    | None = None,
    paint: Mapping[str, Sequence[tuple[float, str]]] | None = None,
) -> list[dict[str, Any]]:
    """Emit the solved channels (and ``extra``: ``{(path, prop): (values, as
    the document shows them)}``, the held items'; and ``paint``: ``{path:
    [(time, host)]}``, each held item's ``paint_after`` keys, an#537) as each
    entity's ``__solve__`` clip; return the authored spans they replace."""
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
            channels = (
                ("rotation",) if puppet.bodies[path].parent_body else SOLVED_CHANNELS
            )
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
                    KeyframeJSON(time=_q(t, 1e-9), value=v, easing=easing)
                    for t, v in zip(run.times, qs)
                ],
            )
        )
        emitted.add((path, prop))
    for (path, prop), (vs, shown) in sorted((extra or {}).items()):
        quantum = ANGLE_QUANTUM if prop == "rotation" else POSITION_QUANTUM
        qs = [_q(v, quantum) for v in vs]
        same = SAME_VALUE.get(prop, SAME_SCALE)
        if all(abs(v - w) <= same for v, w in zip(qs, shown)):
            continue
        root = path.split("/", 1)[0]
        clips.setdefault(root, []).append(
            ChannelJSON(
                target=path,
                property=prop,
                keyframes=[
                    KeyframeJSON(time=_q(t, 1e-9), value=v, easing=easing)
                    for t, v in zip(run.times, qs)
                ],
            )
        )
        emitted.add((path, prop))
    for path, keys in sorted((paint or {}).items()):
        clips.setdefault(path.split("/", 1)[0], []).append(
            ChannelJSON(
                target=path,
                property=PAINT_AFTER_PROPERTY,
                keyframes=[
                    KeyframeJSON(time=_q(t, 1e-9), value=host, easing="step")
                    for t, host in keys
                ],
            )
        )
    overridden = _overridden(state, emitted, run)
    for root, channels in clips.items():
        name = f"{SOLVE_CLIP_PREFIX}{root}"
        state.animations[name] = AnimationClipJSON(
            name=name, duration=max(0.001, duration), channels=channels
        )
        placed = PlacedClipJSON(
            animation_id=name, start_time=0.0, duration=max(0.001, duration)
        )
        track = next((tr for tr in state.tracks if tr.target_root == root), None)
        if track is None:
            state.tracks.append(TrackJSON(target_root=root, clips=[placed]))
        else:
            track.clips.append(placed)
    return overridden


def _overridden(
    state: Any, emitted: set[tuple[str, str]], run: Run
) -> list[dict[str, Any]]:
    """The authored spans a solved channel replaces: ``[{target, property, from,
    until}]`` (an authored span the solve held at every frame is kept, not replaced)."""
    out = []
    for track in state.tracks:
        for placed in track.clips:
            clip = state.animations.get(placed.animation_id)
            if clip is None or placed.animation_id.startswith(SOLVE_CLIP_PREFIX):
                continue
            for ch in clip.channels:
                if (ch.target, ch.property) in emitted:
                    span = (
                        placed.duration
                        if placed.duration is not None
                        else clip.duration
                    )
                    inside = [
                        k
                        for k, t in enumerate(run.times)
                        if placed.start_time - 1e-9
                        <= t
                        <= placed.start_time + span + 1e-9
                    ]
                    if all(
                        ch.property in run.held[k].get(ch.target, ()) for k in inside
                    ):
                        continue
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


def _report(
    puppet: Puppet, run: Run, settings: Settings, overridden: list[dict[str, Any]]
) -> dict[str, Any]:
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
        if puppet.rows[j].source == REACH_SOURCE:
            continue  # a reach is a goal on its way: the hold report says where it arrived
        for a, b in _spans(run.times, refused[j]):
            worst = max(
                (gaps.get((j, k), 0.0) for k, t in enumerate(run.times) if a <= t <= b),
                default=0.0,
            )
            entry = {"joint": j, "from": r2(a), "until": r2(b), "gap": r2(worst)}
            if puppet.rows[j].source == "pin":
                reach = _reach(puppet, run, j, run.times.index(a))
                if reach is not None:
                    entry["reach"] = {
                        k: (r2(v) if isinstance(v, float) else v)
                        for k, v in reach.items()
                    }
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
            {
                "id": row.id,
                "type": type(row.joint).__name__.lower(),
                "bodies": row.label,
                "source": row.source,
                "where": row.where,
                "span": [round(row.span[0], 9), round(row.span[1], 9)]
                if row.span is not None
                else None,
            }
            for row in puppet.rows
        ],
        "events": {
            jid: [[round(t, 9), on] for t, on in evs]
            for jid, evs in sorted(puppet.events.items())
        },
        "dropped": dropped,
        "snaps": [
            {"joint": j, "at": r2(run.times[k]), "gap": r2(g)}
            for k, j, g in run.snaps
            if puppet.rows[j].source != REACH_SOURCE  # a reach starts where the hand is
        ],
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
        joint_on_body = (
            link.joint.b
        )  # the hinge's child-side point (the rig's rows are (parent, child))
        reach += _distance(puppet.rest, puppet.bodies, at, joint_on_body)
        body, at = link.parent, link.joint.a
    if body not in puppet.held:
        return None

    def world(p: Any) -> tuple[float, float]:
        if p.body not in puppet.bodies:
            return (p.u, p.v)
        info = puppet.bodies[p.body]
        x, y, theta = run.poses[k][p.body]
        sx, sy, mirrored, _flip = run.geometry[k][p.body]
        b = Body(
            p.body,
            x=x,
            y=y,
            rotation=theta,
            width=info.box[2] * sx,
            height=info.box[3] * sy,
            origin=info.fraction(info.pivot, mirrored),
        )
        return point_world(b, _flip_point(p, {p.body: mirrored != info.mirrored}))

    ax, ay = world(at)
    tx, ty = world(target)
    dist = math.hypot(tx - ax, ty - ay)
    f = min(1.0, reach / dist) if dist else 0.0
    return {
        "from": body,
        "within": reach >= dist,
        "reach": reach,
        "distance": dist,
        "place": [
            round(ax + (tx - ax) * f, 1) + 0.0,
            round(ay + (ty - ay) * f, 1) + 0.0,
        ],
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

    from an.stage.timeline import _pose_for, transform_of

    decl = declarations(shot, mall)
    puppet = build_puppet(doc, shot, mall, decl)
    # The verbs' spans and the join/unjoin instants as the COMPILE placed them
    # (it knew every leaf's natural length; this reading does not).
    report = solve_report(doc)
    recorded = report.get("joints") or []
    if len(recorded) >= len(puppet.rows):  # the reaches the hold layer added come last
        for row, rec in zip(puppet.rows, recorded):
            if rec.get("span") is not None:
                row.span = (float(rec["span"][0]), float(rec["span"][1]))
    if isinstance(report.get("events"), Mapping):
        puppet.events = {
            jid: [(float(t), bool(on)) for t, on in evs]
            for jid, evs in report["events"].items()
        }
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
        flips: dict[str, bool] = {}
        for path, info in puppet.bodies.items():
            x, y = _apply(world[path], info.pivot)
            tr = transform_of(
                nodes[path], _pose_for(pose, path), frame_height=doc.meta.height
            )
            sx, sy, mirrored, _flip = _geometry_at(world[path], tr.scale_x)
            flips[path] = mirrored != info.mirrored
            bodies[path] = Body(
                path,
                x=x,
                y=y,
                rotation=_decompose(world[path])[0],
                width=info.box[2] * sx,
                height=info.box[3] * sy,
                origin=info.fraction(info.pivot, mirrored),
            )
        row_gaps, row_excess = [], []
        for row in puppet.rows:
            if row.source == "pull" or not _joined_at(puppet, row, t):
                # A pull is a goal, not a joint: it gets as close as the joints allow.
                row_gaps.append(0.0)
                row_excess.append(0.0)
                continue
            j = _frame_joint(row.joint, flips)
            if row.path is not None and row.span is not None:
                from an.kinematics import Point, WORLD

                s0, s1 = row.span
                j = type(j)(
                    j.a,
                    Point(
                        WORLD,
                        *_along(row.path, (t - s0) / (s1 - s0) if s1 > s0 else 1.0),
                    ),
                    length=j.length,
                    mode=j.mode,
                    compliance=j.compliance,
                )

            def at(p, bodies=bodies):
                return (
                    point_world(bodies[p.body], p) if p.body in bodies else (p.u, p.v)
                )

            if isinstance(j, (Slide, Contact)):
                gap = _segment_gap(
                    at(j.point),
                    at(j.start),
                    at(j.end),
                    one_sided=isinstance(j, Contact),
                )
            else:
                (ax, ay), (bx, by) = at(j.a), at(j.b)
                gap = math.hypot(ax - bx, ay - by)
                if isinstance(j, Distance):
                    gap = {
                        "equal": abs(gap - j.length),
                        "at_most": max(0.0, gap - j.length),
                        "at_least": max(0.0, j.length - gap),
                    }[j.mode]
            over = 0.0
            if isinstance(j, Hinge) and j.limits is not None:
                rel = _wrap(
                    bodies[j.b.body].rotation
                    - (bodies[j.a.body].rotation if j.a.body in bodies else 0.0)
                    - (j.rest or 0.0)
                )
                lo, hi = j.limits
                over = max(0.0, lo - rel, rel - hi)
            elif isinstance(j, Weld) and j.rest is not None and row.source != "rig":
                rel = _wrap(
                    bodies[j.b.body].rotation
                    - (bodies[j.a.body].rotation if j.a.body in bodies else 0.0)
                    - j.rest
                )
                over = abs(rel)
            row_gaps.append(gap)
            row_excess.append(over)
        gaps.append(row_gaps)
        excess.append(row_excess)
    return puppet, list(times), gaps, excess


def _segment_gap(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    one_sided: bool,
) -> float:
    tx, ty = b[0] - a[0], b[1] - a[1]
    length = math.hypot(tx, ty)
    if length == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    s = ((p[0] - a[0]) * tx + (p[1] - a[1]) * ty) / (length * length)
    if one_sided:
        if not 0.0 <= s <= 1.0:
            return 0.0  # off the segment's ends: nothing to stand on, nothing broken
        depth = (
            (p[0] - a[0]) * ty - (p[1] - a[1]) * tx
        ) / length  # >0 on the free side
        return max(0.0, -depth)
    s = max(0.0, min(1.0, s))
    return math.hypot(p[0] - (a[0] + s * tx), p[1] - (a[1] + s * ty))
