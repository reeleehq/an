"""Supports: what a body rests on, and how far it is from resting there (an#519, catalogue A1).

A ``support`` joint (:class:`an.ir.schema.JointSpec`, ``type: support``) says a
body's contact points rest on a surface: ``ground`` (the shot's floor line),
``<body>@surface[@f]`` (a body's supporting segment, the hold layer's grammar)
or a ``world@x,y`` segment with ``end``. This module is the pure measurement
under the ``support`` check (:mod:`an.verify.support`):

- :func:`contacts_of`: the named points of an entity that touch what it stands
  on, by one fallback chain: the entity kind's hook
  (:attr:`an.genres.EntityKind.contacts`: a character's feet), else the
  descriptor's ``metadata.contacts`` (``{name: [u, v]}``, fractions of the root
  part's drawing), else the rig's declared ``origin`` when a part rests on it
  (an#601's rule: where the rig stands, not where it is held), else the lowest
  point of its root parts' ink: ``ink`` when a raster's alpha hull was read,
  ``box`` when only the corners of its box were (SVG art), which is measured
  for a declared support but never makes an entity be taken to stand.
- :func:`supports_at`: every declared support of a compiled shot, and every
  entity taken to stand on its floor, as :class:`SupportState` records per
  instant: each contact's signed distance to the surface along its normal
  (:func:`an.stage.surface_line.lowest_on`'s sign: positive above, negative
  sunk), whether it is a **limb**'s (on a part that is not one of the body's
  roots), where its foot on the surface lies along it (``along``, in the
  surface's own frame) and how far that foot **slid** along it since the grid
  instant before while the contact was held there (the ``skate`` check's
  measure, an#519 PR 2), with the references that do not resolve returned as
  ``(where, message)``.

A named point (``cup@base``, ``paul@foot_l``) is resolved by the solve's own
resolver (:func:`an.stage.solve.locate_point`), so a ``pin`` and a ``support``
naming one contact name one point (:func:`an.stage.solve.contact_point`); a
``<body>@surface`` is the hold layer's segment
(:func:`an.stage.surface_line.body_surface`).

Tolerances are fractions of the entity's height with a pixel floor
(:func:`support_tolerance`): a wide and a close-up agree, and a small prop is
not held to a gap below what a frame shows.

>>> support_tolerance(200.0), support_tolerance(30.0)
(4.0, 2.0)
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from an.ir.schema import GROUND_SURFACE, SURFACE_POINT, Shot
from an.stage.surface_line import (
    Line,
    body_surface,
    ground_line,
    line_through,
    lowest_on,
)

__all__ = [
    "CONTACT_SOURCES",
    "CONTACTS_KEY",
    "SUPPORT_TOLERANCE",
    "SUPPORT_FLOOR_PX",
    "SKATE_TOLERANCE",
    "SKATE_FLOOR_PX",
    "SKATE_DRIFT_TOLERANCE",
    "SKATE_DRIFT_FLOOR_PX",
    "SKATE_LIFT",
    "Contacts",
    "ContactState",
    "SupportState",
    "support_tolerance",
    "skate_tolerance",
    "skate_drift_tolerance",
    "contacts_of",
    "contacts_on_parts",
    "supports_at",
]

#: Where an entity's contacts come from, in the order the chain tries them.
CONTACT_SOURCES: tuple[str, ...] = ("hook", "metadata", "origin", "ink", "box")
#: The descriptor's ``metadata`` key that names a prop's contacts.
CONTACTS_KEY: str = "contacts"
#: The descriptor field holding art facts (``metadata.shaded_side``, ``.contacts``).
METADATA_KEY: str = "metadata"
#: How far a contact may be off its surface, either way, as a fraction of the
#: entity's height (4 px on a 200 px figure).
SUPPORT_TOLERANCE: float = 0.02
#: The least tolerance, in px: the solver's own rejoin blend
#: (:data:`an.kinematics.solver.DFLT_REJOIN_BLEND_PX`), below which it calls two
#: points joined; a small prop is not held tighter than a joint.
SUPPORT_FLOOR_PX: float = 2.0
#: How fast a held contact's foot may move along its surface, in the surface's
#: own frame, as a fraction of the entity's height PER SECOND (24 px/s on a
#: 200 px figure: 1 px a frame at 24 fps, 0.4 px at 60). A speed, so one slide
#: gets one verdict at any frame rate or step rate.
SKATE_TOLERANCE: float = 0.12
#: The least skate speed tolerance, in px per second (half a pixel a frame at
#: 24 fps: a fraction of a small body's height is less).
SKATE_FLOOR_PX: float = 12.0
#: How far a held contact's foot may drift along its surface over one stance
#: (from where it was planted, while it stays held), as a fraction of the
#: entity's height (6 px on a 200 px figure): a slow skate under the speed
#: tolerance still adds up to a foot that is not where it was put down.
SKATE_DRIFT_TOLERANCE: float = 0.03
#: The least drift tolerance, in px: the support's own floor
#: (:data:`SUPPORT_FLOOR_PX`), below which two points are one.
SKATE_DRIFT_FLOOR_PX: float = 2.0
#: A step between two instants whose foot moves along the surface's normal by
#: more than this fraction of how far it moves along the surface is a lift-off
#: or a landing (a foot leaving the floor while still within the support
#: tolerance of it), not a slide: it is not measured for skate.
SKATE_LIFT: float = 0.25
#: A normal motion (px) below this is none (float noise of the matrices).
_SAME_PX: float = 1e-6
#: How close (px, at rest in the entity's own frame) a part's painted bottom
#: must come to the rig's ``origin`` for the origin to be where it stands
#: (:data:`an.stage.hold.SUPPORT_TOLERANCE_PX`'s rule, an#601).
ORIGIN_TOUCH_PX: float = 1.0
#: Two instants closer than this are one.
SAME_INSTANT_S: float = 1e-9


def support_tolerance(
    height: float,
    *,
    tolerance: float = SUPPORT_TOLERANCE,
    floor: float = SUPPORT_FLOOR_PX,
) -> float:
    """How far a contact of an entity ``height`` px tall may be off its surface:
    ``tolerance`` of its height, never under ``floor`` px.

    >>> support_tolerance(500.0), support_tolerance(500.0, tolerance=0.05, floor=30.0)
    (10.0, 30.0)
    """
    return max(tolerance * float(height), floor)


def skate_tolerance(
    height: float,
    *,
    tolerance: float = SKATE_TOLERANCE,
    floor: float = SKATE_FLOOR_PX,
) -> float:
    """How fast (px per second) a held contact of an entity ``height`` px tall
    may slide along its surface: ``tolerance`` of its height per second, never
    under ``floor``.

    >>> skate_tolerance(200.0), skate_tolerance(40.0)
    (24.0, 12.0)
    """
    return max(tolerance * float(height), floor)


def skate_drift_tolerance(
    height: float,
    *,
    tolerance: float = SKATE_DRIFT_TOLERANCE,
    floor: float = SKATE_DRIFT_FLOOR_PX,
) -> float:
    """How far (px) a held contact of an entity ``height`` px tall may drift
    along its surface over one stance: ``tolerance`` of its height, never under
    ``floor``.

    >>> skate_drift_tolerance(200.0), skate_drift_tolerance(40.0)
    (6.0, 2.0)
    """
    return max(tolerance * float(height), floor)


# -----------------------------------------------------------------------------
# Contacts: which points of a body touch what it stands on
# -----------------------------------------------------------------------------

#: ``(slot, point)``: ``point`` a fraction ``(u, v)`` of the slot's drawing, or
#: ``None`` for its far end from its pivot. Slot ``""`` is the entity's own
#: frame (``origin``) or its root parts (``ink``, ``box``, ``metadata``).
ContactPoint = tuple[str, tuple[float, float] | None]


@dataclass(frozen=True)
class Contacts:
    """An entity's contacts and where the chain found them.

    >>> Contacts("origin", {"origin": ("", None)}).names
    ('origin',)
    """

    source: str
    points: dict[str, ContactPoint]
    #: Why a kind's hook gave nothing it could use (it raised), else ``""``.
    note: str = ""

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.points)


def _field(doc: Any, name: str) -> Any:
    if isinstance(doc, Mapping):
        return doc.get(name)
    return getattr(doc, name, None)


def _metadata_contacts(desc: Any) -> dict[str, ContactPoint]:
    """``metadata.contacts``: ``{name: [u, v]}`` (the root part's drawing) or
    ``{name: {slot: s, at: [u, v]}}`` (a part's; no ``at``: its far end).

    >>> _metadata_contacts({"metadata": {"contacts": {"base": [0.5, 1.0]}}})
    {'base': ('', (0.5, 1.0))}
    >>> _metadata_contacts({"metadata": {"contacts": {"foot_l": {"slot": "leg_l"}}}})
    {'foot_l': ('leg_l', None)}
    >>> _metadata_contacts({"metadata": {"contacts": {"bad": "x"}}})
    {}
    """
    meta = _field(desc, METADATA_KEY)
    raw = meta.get(CONTACTS_KEY) if isinstance(meta, Mapping) else None
    out: dict[str, ContactPoint] = {}
    for name, spec in (raw or {}).items() if isinstance(raw, Mapping) else ():
        slot, at = "", spec
        if isinstance(spec, Mapping):
            slot, at = str(spec.get("slot") or ""), spec.get("at")
        if at is None and slot:
            out[str(name)] = (slot, None)
            continue
        try:
            u, v = (float(c) for c in at)
        except (TypeError, ValueError):
            continue
        if math.isfinite(u) and math.isfinite(v):
            out[str(name)] = (slot, (u, v))
    return out


def _hook_contacts(entity: Any, desc: Any) -> tuple[dict[str, ContactPoint], str]:
    """The entity kind's ``contacts`` answer, and why it gave none when it raised."""
    from an.genres.registry import entity_kind

    kind = entity_kind(getattr(entity, "kind", "") or "")
    hook = getattr(kind, "contacts", None) if kind is not None else None
    if hook is None or desc is None:
        return {}, ""
    try:
        found = dict(hook(desc) or {})
    except Exception as e:  # noqa: BLE001 - a genre that cannot say names nothing
        return {}, f"{entity.kind!r}'s contacts hook failed: {e}"
    return {str(k): (str(v[0]), v[1]) for k, v in found.items()}, ""


def contacts_on_parts(entity: Any, desc: Any, *, rig: Any) -> dict[str, ContactPoint]:
    """The contacts the chain names on a part of ``entity``'s rig (the hook's,
    else ``metadata.contacts``, a root-part fraction put on the first root):
    what the point resolver (:func:`an.stage.solve.locate_point`) names after
    a rig's landmarks, so a joint, a verb or a support may name ``paul@foot_l``
    as it names ``paul@hand_l``.

    >>> from types import SimpleNamespace as NS
    >>> contacts_on_parts(NS(kind="prop"), {"metadata": {"contacts": {"base": [0.5, 1]}}}, rig=NS(roots=("body",)))
    {'base': ('body', (0.5, 1.0))}
    """
    found, _note = _hook_contacts(entity, desc)
    if not found:
        found = _metadata_contacts(desc)
    roots = tuple(getattr(rig, "roots", ()) or ())
    out: dict[str, ContactPoint] = {}
    for name, (slot, point) in found.items():
        if not slot:
            if not roots:
                continue
            slot = roots[0]
        out[name] = (slot, point)
    return out


def contacts_of(
    entity: Any,
    mall: Mapping[str, Any] | None,
    *,
    rig: Any = None,
    descriptor: Any = None,
    doc: Any = None,
) -> Contacts:
    """``entity``'s contacts, by the chain: the kind's hook, ``metadata.contacts``,
    the rig's ``origin`` (when a root part's painted bottom rests on it, read
    in ``doc``), else the lowest ink of its root parts: ``ink`` when ``doc``
    shows a raster whose alpha hull was read, else ``box``.

    >>> from types import SimpleNamespace as NS
    >>> contacts_of(NS(kind="prop", store=None, ref="x"), {}, descriptor={"origin": [0, 0]})
    Contacts(source='origin', points={'origin': ('', None)}, note='')
    >>> contacts_of(NS(kind="prop", store=None, ref="x"), {}).source
    'box'
    """
    from an.stage.rig import declared_origin

    desc = descriptor if descriptor is not None else _descriptor_of(entity, mall)
    found, note = _hook_contacts(entity, desc)
    if found:
        return Contacts("hook", found, note)
    meta = _metadata_contacts(desc)
    if meta:
        return Contacts("metadata", meta, note)
    if (
        desc is not None
        and declared_origin(desc) is not None
        and (doc is None or _origin_touched(doc, entity, rig, mall))
    ):
        return Contacts("origin", {"origin": ("", None)}, note)
    source = "ink" if doc is not None and _ink_read(doc, entity, rig, mall) else "box"
    return Contacts(source, {source: ("", None)}, note)


def _descriptor_of(entity: Any, mall: Mapping[str, Any] | None) -> Any:
    from an.stage.solve import _descriptor, _is_rig_kind

    if entity is None or not getattr(entity, "store", None):
        return None
    return _descriptor(entity, mall or {}) if _is_rig_kind(entity) else None


def _root_paths(eid: str, rig: Any, nodes: Mapping[str, Any]) -> list[str]:
    """The node paths of ``eid``'s root parts (the entity node for a non-rig,
    or its drawn descendants when it draws nothing itself)."""
    if rig is not None and getattr(rig, "bodies", None):
        out = [f"{eid}/{rig.bodies[s]}" for s in rig.roots if s in rig.bodies]
        out = [p for p in out if p in nodes]
        if out:
            return out
    if eid in nodes and nodes[eid].visual is not None:
        return [eid]
    return [p for p, n in nodes.items() if p.startswith(eid + "/") and n.visual]


def _carrying_root_paths(eid: str, rig: Any) -> frozenset[str]:
    """The node paths of ``eid``'s root parts that some joint hangs a part from.

    >>> from types import SimpleNamespace as NS
    >>> rig = NS(bodies={"torso": "torso", "leg_l": "leg_l", "arm": "arm"},
    ...          roots=("torso", "leg_l"), joints=(NS(child="arm", parent="torso"),))
    >>> sorted(_carrying_root_paths("bob", rig))
    ['bob/torso']
    """
    if rig is None or not getattr(rig, "bodies", None):
        return frozenset()
    parents = {j.parent for j in rig.joints}
    return frozenset(
        f"{eid}/{rig.bodies[s]}" for s in rig.roots if s in parents and s in rig.bodies
    )


def _origin_touched(doc: Any, entity: Any, rig: Any, mall: Any) -> bool:
    """Whether a root part's painted bottom rests on the entity's origin, at rest
    (an#601: a stick's middle or a wheel's hub is where it is held)."""
    from an.stage.hold import ink_points
    from an.stage.solve import _apply, _compose, _invert, node_index, world_matrices

    nodes = node_index(doc)
    eid = entity.id
    if eid not in nodes:
        return False
    roots = _root_paths(eid, rig, nodes)
    rest = world_matrices(doc, [eid, *roots], None, nodes)
    to_entity = _invert(rest[eid])
    for p in roots:
        m = _compose(to_entity, rest[p])
        lowest = max(_apply(m, c)[1] for c in ink_points(doc, nodes[p], mall))
        if abs(lowest) <= ORIGIN_TOUCH_PX:
            return True
    return False


def _ink_read(doc: Any, entity: Any, rig: Any, mall: Any) -> bool:
    """Whether every root part's ink is a read alpha hull, not its box's corners."""
    from an.stage.hold import _corners, ink_points
    from an.stage.solve import local_box, node_index

    nodes = node_index(doc)
    roots = _root_paths(entity.id, rig, nodes) if entity.id in nodes else []
    return bool(roots) and all(
        set(ink_points(doc, nodes[p], mall)) != set(_corners(local_box(nodes[p])))
        for p in roots
    )


# -----------------------------------------------------------------------------
# The states
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ContactState:
    """One contact at one instant."""

    name: str
    #: The node path that carries it.
    part: str
    #: Its stage point (the lowest of its points, for ``ink`` or ``box``).
    at: tuple[float, float]
    #: Its signed distance to the surface along the normal (+ above, - sunk).
    above: float
    #: Whether it is a limb's: its node is not the entity's own nor one of its
    #: root parts (a leg hinged to the body, a hoof), so it moves relative to
    #: the body and can skate. A body's own stance point (its ``origin``, the
    #: ink of its roots, a prop's ``base``, a bone on a root part) cannot: a
    #: body that glides or is pushed slides on it by right.
    limb: bool = False
    #: Its foot parameter along the surface, in the surface's own frame: where
    #: the foot of its normal falls along the surface from a point fixed in it,
    #: in the surface's units (a body's surface: its own units from the
    #: segment's first end, so it neither moves nor flips with the body; the
    #: floor and a stage segment: stage px from the floor's ``(0, y)`` or the
    #: segment's ``a``).
    along: float = 0.0
    #: How far (stage px, signed along the surface) its foot moved along the
    #: surface, in the surface's own frame, since the grid's previous instant
    #: (so a body carried by what it stands on does not move); ``None`` unless
    #: it was held at both (its support joined, within the support tolerance of
    #: the surface) and the step was not a lift-off or a landing
    #: (:data:`SKATE_LIFT`).
    slid: float | None = None


@dataclass(frozen=True)
class SupportState:
    """One support (declared, or a stance taken as the shot opens) at one instant.

    >>> s = SupportState("cup", None, "entities", 0, 0.0, ((0.0, 0.0), (1.0, 0.0)), "ground",
    ...     (ContactState("base", "cup", (0.0, -3.0), 3.0),), True, 30.0, "metadata")
    >>> s.lowest, s.inferred
    (3.0, True)
    """

    entity: str
    #: The support's id; ``None`` when inferred.
    joint: str | None
    #: Where it is declared (``joints/0``, ``entities/1/joints/0``, ...).
    where: str
    #: The instant's index on the shot's frame grid, and its time.
    frame: int
    t: float
    surface: Line
    surface_ref: str
    #: The contacts measured (one past a bounded surface's ends is not).
    contacts: tuple[ContactState, ...]
    joined: bool
    #: The entity's height as the shot opens (px): what its tolerance is a fraction of.
    height: float
    #: Where its contacts came from (:data:`CONTACT_SOURCES`; a point named by
    #: bone, landmark or fraction is ``point``).
    source: str
    #: The contact named in the reference, or ``""`` for all of them.
    named: str = ""
    #: Whether the surface is the world's floor (``World.ground``) as the
    #: camera projects it under the entity, measured along from a point held
    #: in the frame the entity stands in (an#519 PR 4), not a stage floor.
    world_floor: bool = False

    @property
    def inferred(self) -> bool:
        return self.joint is None

    @property
    def lowest(self) -> float | None:
        """The least distance of a contact above the surface; ``None``, none measured."""
        return min((c.above for c in self.contacts), default=None)

    @property
    def deepest(self) -> ContactState | None:
        return min(self.contacts, key=lambda c: c.above, default=None)


@dataclass(frozen=True)
class _Contact:
    """A resolved contact: a node and its points in that node's own frame."""

    name: str
    node: str
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class _SurfaceAt:
    """A support's surface at one instant: its stage line, a bounded surface's
    ends (``None`` for the floor), and its own frame: ``along(p)`` is a stage
    point's foot parameter in the surface's units, ``scale`` the stage px per
    unit along it."""

    line: Line
    ends: tuple[tuple[float, float], tuple[float, float]] | None
    along: Any
    scale: float = 1.0


@dataclass
class _Support:
    """A support resolved against the compiled document."""

    entity: str
    joint: str | None
    where: str
    surface_ref: str
    contacts: list[_Contact]
    source: str
    named: str = ""
    #: The surface at an instant (:class:`_SurfaceAt`), from world matrices
    #: and the time: ``surface(world, t)``.
    surface: Any = None
    surface_paths: tuple[str, ...] = ()
    events: list[tuple[float, bool]] = field(default_factory=list)
    instants: frozenset[int] | None = None  # None: every frame
    #: The entity's own node and its root parts': a contact on one is the
    #: body's stance point, not a limb's (:attr:`ContactState.limb`).
    body: frozenset[str] = frozenset()
    #: Measured against the world's floor (:attr:`SupportState.world_floor`).
    world_floor: bool = False


def supports_at(
    doc: Any,
    shot: Shot,
    mall: Mapping[str, Any] | None,
    *,
    times: Sequence[float] | None = None,
    inferred: bool = True,
    rest_only: bool = True,
    tolerance: float = SUPPORT_TOLERANCE,
    floor: float = SUPPORT_FLOOR_PX,
    lift: float = SKATE_LIFT,
) -> tuple[list[SupportState], list[tuple[str, str]]]:
    """Every declared support of ``shot`` in its compiled document ``doc`` at
    every instant of ``times`` (default: the solve's frame grid,
    :func:`an.stage.solve.frame_times`), joined or not; and, with
    ``inferred``, every entity taken to stand on the shot's floor
    (``solve: {ground: y}``) as it opens: its lowest contact within
    :func:`support_tolerance` (``tolerance`` of its height, ``floor`` px at
    least) of the floor then, measured at that instant and its rest instants
    (``rest_only``, the ``support`` check's rule) or at every instant (the
    ``skate`` check's, which judges a stance while it moves).

    A contact is held at an instant its support is joined and it is within
    that tolerance of the surface; its ``slid`` is how far (stage px) its foot
    parameter along the surface (``along``, in the surface's own frame) changed
    since the grid's previous instant, when it was held at both and its motion
    along the surface's normal was at most ``lift`` of that (more is a foot
    leaving or meeting the surface). An entity is not measured at an instant
    it is not seen (its alpha at most :data:`an.base.UNSEEN_ALPHA`: a member
    the world hides outside its on-screen window, a fade's end), the rule the
    ``solidity`` check applies, so a slide is never measured across one.
    Returns the states and ``(where, message)`` for each reference that does
    not resolve (no state is made for it)."""
    from an.base import UNSEEN_ALPHA
    from an.stage.solve import (
        node_index,
        world_matrices,
        declarations,
        frame_times,
    )
    from an.stage.timeline import timeline_from_scene
    from an.timing.timeline import evaluate_timeline

    mall = mall or {}
    nodes = node_index(doc)
    if times is None:
        times = frame_times(shot.duration, fps=doc.meta.fps, step_hz=doc.meta.step_hz)
    times = list(times)
    reader = _Reader(doc, shot, mall, nodes)
    decl = declarations(shot, mall)
    problems: list[tuple[str, str]] = []
    supports: list[_Support] = []
    events: dict[str, list[tuple[float, bool]]] = {}
    for verb in decl.support_verbs:
        events.setdefault(verb.action.joint, []).append(
            (verb.start, verb.action.kind == "join")
        )
    for dj in decl.supports:
        found = reader.declared(dj, problems)
        if found is not None:
            found.events = sorted(events.get(dj.qualified_id, ()), key=lambda e: e[0])
            supports.append(found)
    if inferred:
        declared_entities = {s.entity for s in supports} | {
            dj.a.partition("@")[0].split("/", 1)[0] for dj in decl.supports
        }
        supports.extend(
            reader.stances(
                times,
                skip=declared_entities,
                tolerance=tolerance,
                floor=floor,
                rest_only=rest_only,
            )
        )
    if not supports:
        return [], problems

    timeline = timeline_from_scene(doc)
    paths = sorted(
        {p for s in supports for p in (*(c.node for c in s.contacts), *s.surface_paths)}
    )
    out: list[SupportState] = []
    last: dict[int, SupportState] = {}
    for k, t in enumerate(times):
        due = [
            (i, s)
            for i, s in enumerate(supports)
            if s.instants is None or k in s.instants
        ]
        if not due:
            continue
        pose = evaluate_timeline(timeline, t)
        seen = {
            eid: _seen(doc, pose, eid, unseen=UNSEEN_ALPHA)
            for eid in {s.entity for _, s in due}
        }
        due = [(i, s) for i, s in due if seen[s.entity]]
        if not due:
            continue
        world = world_matrices(doc, paths, pose, nodes)
        for i, s in due:
            height = reader.height(s.entity)
            prev = last.get(i)
            state = _state(
                s,
                k,
                t,
                world,
                height,
                tol=support_tolerance(height, tolerance=tolerance, floor=floor),
                prev=prev if prev is not None and prev.frame == k - 1 else None,
                lift=lift,
            )
            last[i] = state
            out.append(state)
    return out, problems


def _seen(doc: Any, pose: Any, eid: str, *, unseen: float) -> bool:
    """Whether ``eid`` is seen under ``pose`` (its alpha over ``unseen``); an
    entity the document does not draw by that id counts as seen."""
    from an.stage.timeline import entity_alpha

    try:
        return entity_alpha(doc, pose, eid) > unseen
    except KeyError:
        return True


def _joined(events: Sequence[tuple[float, bool]], t: float) -> bool:
    """A support's state at ``t``: joined until an ``unjoin``, as a joint's is.

    >>> _joined([(1.0, False), (2.0, True)], 1.5), _joined([(1.0, False)], 0.5)
    (False, True)
    """
    state = True
    for at, joined in events:
        if at <= t + SAME_INSTANT_S:
            state = joined
    return state


def _state(
    s: _Support,
    k: int,
    t: float,
    world: Mapping[str, Any],
    height: float,
    *,
    tol: float,
    prev: SupportState | None,
    lift: float = SKATE_LIFT,
) -> SupportState:
    """``s`` at frame ``k`` (time ``t``) under ``world``'s matrices; ``prev`` its
    state at frame ``k - 1``, when it was measured then, for the slide."""
    at = s.surface(world, t)
    joined = _joined(s.events, t)
    before = (
        {(c.name, c.part): c for c in prev.contacts if abs(c.above) <= tol}
        if prev is not None and prev.joined
        else {}
    )
    contacts = []
    for c in s.contacts:
        low, gap = lowest_on(world[c.node], c.points, at.line)
        if at.ends is not None and not _on_segment(low, *at.ends):
            continue  # off a bounded surface's ends: nothing to stand on
        along = at.along(low)
        was = before.get((c.name, c.node))
        slid = None
        if joined and abs(gap) <= tol and was is not None and math.isfinite(along):
            step = (along - was.along) * at.scale
            rose = abs(gap - was.above)
            if rose <= max(lift * abs(step), _SAME_PX):  # else lifting or landing
                slid = step + 0.0
        contacts.append(
            ContactState(
                c.name,
                c.node,
                (low[0] + 0.0, low[1] + 0.0),
                gap + 0.0,
                limb=c.node not in s.body,
                along=along,
                slid=slid,
            )
        )
    return SupportState(
        entity=s.entity,
        joint=s.joint,
        where=s.where,
        frame=k,
        t=t,
        surface=at.line,
        surface_ref=s.surface_ref,
        contacts=tuple(contacts),
        joined=joined,
        height=height,
        source=s.source,
        named=s.named,
        world_floor=s.world_floor,
    )


def _along(
    p: tuple[float, float], ref: tuple[float, float], axis: tuple[float, float]
) -> float:
    """The foot parameter of ``p`` along the unit ``axis``: how far along it the
    foot of ``p``'s normal lies from ``ref``.

    >>> _along((7.0, -3.0), (2.0, 0.0), (1.0, 0.0))
    5.0
    """
    return (p[0] - ref[0]) * axis[0] + (p[1] - ref[1]) * axis[1] + 0.0


def _stage_surface(line: Line, ends: Any = None) -> _SurfaceAt:
    """A surface fixed on the stage (the floor, a ``world@`` segment): its frame
    is the stage's, from the floor's point or the segment's first end.

    >>> _stage_surface(((0.0, 200.0), (1.0, 0.0))).along((30.0, 195.0))
    30.0
    """
    ref = ends[0] if ends is not None else line[0]
    return _SurfaceAt(line, ends, lambda p: _along(p, ref, line[1]))


def _body_surface_at(
    m: Any, seg: tuple[tuple[float, float], tuple[float, float]]
) -> _SurfaceAt:
    """A body's surface segment ``seg`` (in its node's frame) under its world
    matrix ``m``: the stage line through its ends, and its own frame, a stage
    point taken back into the node's frame (``m`` inverted) and projected on
    ``seg[1] - seg[0]`` from ``seg[0]``, so the parameter neither moves nor
    flips with the body (a mirrored crate keeps its ends where they are).

    >>> s = _body_surface_at((-1.0, 0.0, 0.0, 1.0, 100.0, 0.0), ((0.0, 0.0), (10.0, 0.0)))
    >>> s.ends, s.along((97.0, -2.0)), s.scale
    (((100.0, 0.0), (90.0, 0.0)), 3.0, 1.0)
    """
    from an.stage.solve import _apply, _invert

    a, b = _apply(m, seg[0]), _apply(m, seg[1])
    dx, dy = seg[1][0] - seg[0][0], seg[1][1] - seg[0][1]
    length = math.hypot(dx, dy)
    try:
        inv = _invert(m)
    except ValueError:  # a body drawn at zero scale has no frame to measure in
        inv = None
    if inv is None or length == 0:
        return _SurfaceAt(line_through(a, b), (a, b), lambda _p: math.nan)
    axis = (dx / length, dy / length)
    return _SurfaceAt(
        line_through(a, b),
        (a, b),
        lambda p: _along(_apply(inv, p), seg[0], axis),
        math.hypot(b[0] - a[0], b[1] - a[1]) / length,
    )


def _on_segment(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> bool:
    """Whether the foot of ``p`` on the line ``a``-``b`` falls between its ends.

    >>> _on_segment((5.0, -3.0), (0.0, 0.0), (10.0, 0.0)), _on_segment((11.0, 0.0), (0.0, 0.0), (10.0, 0.0))
    (True, False)
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return False
    s = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
    return 0.0 <= s <= 1.0


# -----------------------------------------------------------------------------
# Reading references against the compiled document
# -----------------------------------------------------------------------------


class _Reader:
    """Resolves bodies, points, contacts and surfaces of one compiled shot."""

    def __init__(self, doc: Any, shot: Shot, mall: Mapping[str, Any], nodes: Any):
        self.doc, self.shot, self.mall, self.nodes = doc, shot, mall, nodes
        self.entities = {e.id: e for e in shot.entities}
        self._rigs: dict[str, Any] = {}
        self._heights: dict[str, float] = {}
        self._contacts: dict[str, Contacts] = {}
        self._open_world: dict[str, Any] | None = None
        self._open_pose: Any = None
        self._rest: dict[str, Any] = {}
        self._contacts_on_parts: dict[str, Mapping[str, Any]] = {}

    @property
    def scope(self) -> Any:
        """The solve's point resolver's view of this shot (:class:`an.stage.solve.PointScope`)."""
        from an.stage.solve import PointScope

        return PointScope(
            nodes=self.nodes,
            entities=self.entities,
            rig=self.rig,
            landmarks=self._landmarks,
            contacts=self.contacts_on_parts,
            rest=self.rest,
        )

    def rest(self, path: str) -> Any:
        """A node's rest (declared) stage transform."""
        from an.stage.solve import world_matrices

        if path not in self._rest:
            self._rest[path] = world_matrices(self.doc, [path], None, self.nodes)[path]
        return self._rest[path]

    def contacts_on_parts(self, eid: str) -> Mapping[str, Any]:
        """``eid``'s hook's or ``metadata`` contacts, each on a part (:func:`contacts_on_parts`)."""
        if eid not in self._contacts_on_parts:
            rig = self.rig(eid)
            desc = _descriptor_of(self.entities[eid], self.mall)
            self._contacts_on_parts[eid] = (
                contacts_on_parts(self.entities[eid], desc, rig=rig)
                if rig is not None and desc is not None
                else {}
            )
        return self._contacts_on_parts[eid]

    # -- per entity --------------------------------------------------------

    def rig(self, eid: str) -> Any:
        from an.stage.solve import _rig_of

        if eid not in self._rigs:
            entity = self.entities[eid]
            try:
                self._rigs[eid] = (
                    _rig_of(entity, self.mall, self.nodes)
                    if _descriptor_of(entity, self.mall) is not None
                    else None
                )
            except Exception:  # noqa: BLE001 - a rig that does not read is measured as drawn
                self._rigs[eid] = None
        return self._rigs[eid]

    def contacts(self, eid: str) -> Contacts:
        if eid not in self._contacts:
            self._contacts[eid] = contacts_of(
                self.entities[eid], self.mall, rig=self.rig(eid), doc=self.doc
            )
        return self._contacts[eid]

    def opening(self, paths: Sequence[str]) -> Mapping[str, Any]:
        """World matrices as the shot opens."""
        from an.stage.solve import world_matrices
        from an.stage.timeline import timeline_from_scene
        from an.timing.timeline import evaluate_timeline

        if self._open_world is None:
            self._open_pose = evaluate_timeline(timeline_from_scene(self.doc), 0.0)
            self._open_world = {}
        missing = [p for p in paths if p not in self._open_world]
        if missing:
            self._open_world.update(
                world_matrices(self.doc, missing, self._open_pose, self.nodes)
            )
        return self._open_world

    def height(self, eid: str) -> float:
        """The entity's drawn height as the shot opens (px, stage)."""
        from an.stage.solve import _apply, local_box

        if eid not in self._heights:
            drawn = [
                p
                for p, n in self.nodes.items()
                if (p == eid or p.startswith(eid + "/")) and n.visual is not None
            ]
            world = self.opening(drawn)
            ys = []
            for p in drawn:
                left, top, w, h = local_box(self.nodes[p])
                for c in (
                    (left, top),
                    (left + w, top),
                    (left, top + h),
                    (left + w, top + h),
                ):
                    ys.append(_apply(world[p], c)[1])
            self._heights[eid] = (max(ys) - min(ys)) if ys else 0.0
        return self._heights[eid]

    def body(self, eid: str) -> frozenset[str]:
        """``eid``'s own node and the root parts that carry it: where a contact
        is the body's stance point, not a limb's. A root something hangs from
        (a torso) carries the rig; a root nothing hangs from beside it (a
        factory character's legs, hung from a slotless ``root`` bone) is a limb.
        A rig where no root carries anything (a crate, a cup) is all body."""
        rig = self.rig(eid)
        roots = _root_paths(eid, rig, self.nodes)
        carrying = _carrying_root_paths(eid, rig)
        body = [p for p in roots if p in carrying] or roots
        return frozenset({eid, *body})

    # -- contacts as nodes and points ---------------------------------------

    def _resolve_point(
        self, eid: str, slot: str, point: Any, *, name: str, source: str = "point"
    ) -> list[_Contact] | str:
        """A ``(slot, point)`` of the chain as contacts, or why it cannot be."""
        from an.stage.hold import ink_points
        from an.stage.solve import contact_point

        rig = self.rig(eid)
        if source == "origin":  # where the rig stands: the entity's own (0, 0)
            return [_Contact(name, eid, ((0.0, 0.0),))]
        if source in ("ink", "box"):  # the lowest of the root parts' ink
            roots = _root_paths(eid, rig, self.nodes)
            if not roots:
                return f"{eid!r} draws nothing to stand on"
            return [
                _Contact(name, p, tuple(ink_points(self.doc, self.nodes[p], self.mall)))
                for p in roots
            ]
        if slot:
            if rig is None or slot not in rig.bodies:
                return f"{name!r} names part {slot!r}, which {eid!r} does not draw"
            node_path = f"{eid}/{rig.bodies[slot]}"
        else:
            roots = _root_paths(eid, rig, self.nodes)
            if not roots:
                return f"{eid!r} draws nothing to stand on"
            node_path = roots[0]
        if node_path not in self.nodes:
            return f"{name!r} names part {slot!r}, which {eid!r} does not draw"
        return [
            _Contact(name, node_path, (contact_point(self.nodes[node_path], point),))
        ]

    def contacts_named(
        self, ref: str, *, where: str, problems: list
    ) -> tuple[list[_Contact], str, str] | None:
        """``a`` of a support as contacts, their source, and the name it gave:
        no ``@``, every contact of the body (or of the part named); ``@point``,
        the point the solve's resolver names (:func:`an.stage.solve.locate_point`),
        else one of the chain's own (``origin``, ``ink``, ``box``)."""
        from an.stage.hold import _corners, ink_points
        from an.stage.solve import (
            WORLD_REF,
            local_box,
            _slot_path,
            locate_point,
            named_point,
        )

        head, _, at = ref.partition("@")
        eid = head.split("/", 1)[0]
        if not head or head == WORLD_REF:
            problems.append(
                (where, f"{ref!r}: a support's `a` is a body, not a stage point")
            )
            return None
        if eid not in self.entities:
            problems.append((where, f"{ref!r}: {eid!r} is not an entity of this shot"))
            return None
        if eid not in self.nodes:
            problems.append((where, f"{ref!r}: {eid!r} is not drawn on the stage"))
            return None
        rig = self.rig(eid)
        part = None
        if "/" in head:
            part = _slot_path(eid, head.split("/", 1)[1], self.nodes, rig)
            if part not in self.nodes:
                near = sorted(p for p in self.nodes if p.split("/", 1)[0] == eid)
                problems.append(
                    (where, f"{ref!r}: no node {part!r}; {eid!r} has {near}")
                )
                return None
        chain = self.contacts(eid)
        if not at:
            if part is None:
                return self._chain(eid, chain, where=where, ref=ref, problems=problems)
            carried = [
                c
                for c in (
                    self._chain(eid, chain, where=where, ref=ref, problems=[])
                    or ([], "", "")
                )[0]
                if c.node == part
            ]
            if carried:
                return carried, chain.source, ""
            pts = ink_points(self.doc, self.nodes[part], self.mall)
            source = (
                "box"
                if set(pts) == set(_corners(local_box(self.nodes[part])))
                else "ink"
            )
            return [_Contact(source, part, tuple(pts))], source, ""

        if self._names_nothing(eid, at):
            if at in chain.points:  # the chain's own: `origin`, `ink`, `box`
                got = self._resolve_point(
                    eid, *chain.points[at], name=at, source=chain.source
                )
                if isinstance(got, str):
                    problems.append((where, f"{ref!r}: {got}"))
                    return None
                return got, chain.source, at
            bones = sorted(rig.anchors) if rig is not None else []
            problems.append(
                (
                    where,
                    f"{ref!r}: {at!r} is no bone of {eid!r} (bones: {bones}), no named point "
                    f"(landmarks: {sorted(self._landmarks(eid))}) and no contact (its contacts, "
                    f"from its {chain.source}: {list(chain.names)}) nor a fraction `u,v`. "
                    f"Declare `metadata: {{contacts: {{{at}: [u, v]}}}}` on its descriptor, or "
                    "name no point to use all of its contacts",
                )
            )
            return None
        found = locate_point(ref, self.scope, side="a")
        if isinstance(found, str):
            problems.append((where, found))
            return None
        named = named_point(self.scope, eid, at)
        source = (
            chain.source if named is not None and named[0] == "contact" else "point"
        )
        return [_Contact(at, found.node, (found.on_node(self.rest),))], source, at

    def _names_nothing(self, eid: str, at: str) -> bool:
        """Whether ``eid@at`` is no fraction, bone, landmark or contact on a part."""
        from an.stage.solve import _numbers, named_point

        rig = self.rig(eid)
        return (
            _numbers(at) is None
            and not (rig is not None and at in rig.anchors)
            and named_point(self.scope, eid, at) is None
        )

    def _chain(
        self, eid: str, chain: Contacts, *, where: str, ref: str, problems: list
    ) -> tuple[list[_Contact], str, str] | None:
        out: list[_Contact] = []
        for name, (slot, point) in chain.points.items():
            got = self._resolve_point(eid, slot, point, name=name, source=chain.source)
            if isinstance(got, str):
                problems.append((where, f"{ref!r}: {got}"))
                return None
            out.extend(got)
        return out, chain.source, ""

    def _landmarks(self, eid: str) -> Mapping[str, Any]:
        from an.genres.registry import entity_kind

        entity = self.entities[eid]
        kind = entity_kind(entity.kind)
        hook = getattr(kind, "landmarks", None) if kind is not None else None
        desc = _descriptor_of(entity, self.mall)
        if hook is None or desc is None:
            return {}
        try:
            return dict(hook(desc) or {})
        except Exception:  # noqa: BLE001 - a genre that cannot say names nothing
            return {}

    # -- surfaces ------------------------------------------------------------

    def surface(
        self,
        ref: str,
        end: str | None,
        *,
        entity: str,
        contacts: list[_Contact],
        where: str,
        problems: list,
    ) -> tuple[Any, tuple[str, ...]] | None:
        """``b`` as ``((world, t) -> its surface then, the node paths it reads)``."""
        from an.stage.solve import WORLD_REF, _numbers, _slot_path

        if ref == GROUND_SURFACE:
            return self.ground(entity, contacts)
        head, _, at = ref.partition("@")
        if head == WORLD_REF:
            a, b = _numbers(at), _numbers((end or "").partition("@")[2])
            if a is None or b is None:
                problems.append(
                    (
                        where,
                        f"{ref!r} to {end!r}: a stage segment is `world@x,y` to `world@x2,y2`",
                    )
                )
                return None
            segment_at = _stage_surface(line_through(a, b), (a, b))
            return (lambda _world, _t: segment_at), ()
        eid = head.split("/", 1)[0]
        if eid not in self.entities:
            problems.append((where, f"{ref!r}: {eid!r} is not an entity of this shot"))
            return None
        if eid not in self.nodes:
            problems.append((where, f"{ref!r}: {eid!r} is not drawn on the stage"))
            return None
        rig = self.rig(eid)
        if "/" in head:
            node_path = _slot_path(eid, head.split("/", 1)[1], self.nodes, rig)
            if node_path not in self.nodes:
                problems.append((where, f"{ref!r}: no node {node_path!r}"))
                return None
        else:
            roots = _root_paths(eid, rig, self.nodes)
            if len(roots) != 1:
                problems.append(
                    (
                        where,
                        f"{ref!r}: {eid!r} has {len(roots)} root parts; name the part (`{eid}/<part>@{SURFACE_POINT}`)",
                    )
                )
                return None
            node_path = roots[0]
        seg = body_surface(
            self.doc, self.nodes, self.mall, rig=rig, entity=eid, node=node_path
        )
        if isinstance(seg, str):
            problems.append((where, f"{ref!r}: {seg}"))
            return None

        def at_instant(world: Mapping[str, Any], _t: float) -> _SurfaceAt:
            return _body_surface_at(world[node_path], seg)

        return at_instant, (node_path,)

    def ground(self, eid: str, contacts: list[_Contact]) -> tuple[Any, tuple[str, ...]]:
        """``ground`` for ``eid``, as :meth:`surface` gives a surface: the
        shot's floor line (``solve: {ground: y}``); else the world's floor under
        the entity (:meth:`world_floor`); else where its contacts are as the
        shot opens (its own floor)."""
        from an.stage.solve import _apply

        solve = self.shot.solve
        if solve is not None and solve.ground is not None:
            floor_at = _stage_surface(ground_line(float(solve.ground)))
            return (lambda _world, _t: floor_at), ()
        found = self.world_floor(eid)
        if found is not None:
            return found
        world = self.opening([c.node for c in contacts])
        y = max(_apply(world[c.node], p)[1] for c in contacts for p in c.points)
        floor_at = _stage_surface(ground_line(y))
        return (lambda _world, _t: floor_at), ()

    def world_floor(self, eid: str) -> tuple[Any, tuple[str, ...]] | None:
        """The world's floor under ``eid`` (``overrides.ground``, which the
        world's lowering writes when it declares ``ground``,
        :func:`an.ir.world.world_ground_at`), as :meth:`surface` gives a
        surface: at each instant, the line through its floor point along its
        direction, carried from the entity's parent to the stage; a point's
        position along it is in world units in the frame the entity stands in
        (:meth:`an.ir.world.GroundAt.position`), its scale the stage px per
        unit there, so a foot carried by the frame, or by a walk straight in
        depth, does not slide. ``None`` when it has none (the mark is read only
        on a shot lowered from a world, :func:`an.ir.world.world_ground_mark`)."""
        from an.ir.world import world_ground_at, world_ground_mark
        from an.stage.solve import _apply, _parent_path

        spec = world_ground_mark(self.shot, self.entities.get(eid))
        if spec is None or world_ground_at(spec, 0.0) is None:
            return None
        parent = _parent_path(eid, self.nodes)

        def at_instant(world: Mapping[str, Any], t: float) -> _SurfaceAt:
            g = world_ground_at(spec, t)
            m = world[parent]
            a = _apply(m, g.at)
            b = _apply(m, (g.at[0] + g.along[0], g.at[1] + g.along[1]))
            line = line_through(a, b)
            per_unit = g.scale * math.hypot(b[0] - a[0], b[1] - a[1])
            sign = 1.0 if _along(b, a, line[1]) >= 0 else -1.0

            def position(p: tuple[float, float]) -> float:
                return g.lateral + sign * _along(p, a, line[1]) / per_unit

            return _SurfaceAt(line, None, position, per_unit)

        return at_instant, ((parent,) if parent else ())

    # -- what the shot declares, and what stands -----------------------------

    def declared(self, dj: Any, problems: list) -> _Support | None:
        resolved = self.contacts_named(dj.a, where=dj.where, problems=problems)
        if resolved is None:
            return None
        contacts, source, named = resolved
        eid = dj.a.partition("@")[0].split("/", 1)[0]
        found = self.surface(
            dj.b,
            dj.end,
            entity=eid,
            contacts=contacts,
            where=dj.where,
            problems=problems,
        )
        if found is None:
            return None
        at_instant, paths = found
        return _Support(
            entity=eid,
            joint=dj.qualified_id,
            where=dj.where,
            surface_ref=dj.b if dj.end is None else f"{dj.b} to {dj.end}",
            contacts=contacts,
            source=source,
            named=named,
            surface=at_instant,
            surface_paths=paths,
            body=self.body(eid),
            world_floor=dj.b == GROUND_SURFACE
            and dj.end is None
            and self.on_world_floor(eid),
        )

    def on_world_floor(self, eid: str) -> bool:
        """Whether ``ground`` for ``eid`` is the world's floor under it: the
        shot declares no ``solve.ground`` and the world's lowering gave it one."""
        solve = self.shot.solve
        if solve is not None and solve.ground is not None:
            return False
        return self.world_floor(eid) is not None

    def stances(
        self,
        times: Sequence[float],
        *,
        skip: set[str],
        tolerance: float = SUPPORT_TOLERANCE,
        floor: float = SUPPORT_FLOOR_PX,
        rest_only: bool = True,
    ) -> list[_Support]:
        """The entities taken to stand on the shot's floor as it opens (§2.4 of
        the spec): a rig kind, not held by the hold layer, whose contacts are
        not a box's corners, its lowest contact within :func:`support_tolerance`
        of the floor at the opening instant (one staged on a crate stands on
        the crate, not the floor); each measured as it opens and at its rest
        instants (``rest_only``), else at every instant. The floor is the
        shot's (``solve: {ground: y}``, :meth:`_level_stance`), else the
        world's under the entity (``World.ground``, :meth:`_world_floor_stance`);
        an entity with neither has none and is not taken to stand."""
        from an.stage.hold import hold_declarations
        from an.stage.solve import _is_rig_kind

        solve = self.shot.solve
        level = (
            float(solve.ground)
            if solve is not None and solve.ground is not None
            else None
        )
        if level is None and not any(
            self.world_floor(e.id) is not None for e in self.shot.entities
        ):
            return []
        try:
            items = set(hold_declarations(self.shot).items)
        except Exception:  # noqa: BLE001 - the hold checks report broken holds
            items = set()
        out = []
        for e in self.shot.entities:
            if e.id in skip or e.id in items or e.id not in self.nodes:
                continue
            if not _is_rig_kind(e) or _descriptor_of(e, self.mall) is None:
                continue
            chain = self.contacts(e.id)
            if chain.source == "box":
                continue  # a box's bottom edge is a margin, not a foot
            resolved = self._chain(e.id, chain, where="entities", ref=e.id, problems=[])
            if resolved is None or not resolved[0]:
                continue
            contacts = resolved[0]
            tol = support_tolerance(self.height(e.id), tolerance=tolerance, floor=floor)
            found = (
                self._level_stance(contacts, level, tol=tol)
                if level is not None
                else self._world_floor_stance(e.id, contacts, tol=tol)
            )
            if found is None:
                continue
            surface, paths = found
            out.append(
                _Support(
                    entity=e.id,
                    joint=None,
                    where=f"entities/{self.shot.entities.index(e)}",
                    surface_ref=GROUND_SURFACE,
                    contacts=contacts,
                    source=chain.source,
                    surface=surface,
                    surface_paths=paths,
                    instants=(
                        frozenset(self.rest_frames(e.id, times)) if rest_only else None
                    ),
                    body=self.body(e.id),
                    world_floor=level is None,
                )
            )
        return out

    def _level_stance(
        self, contacts: list[_Contact], y: float, *, tol: float
    ) -> tuple[Any, tuple[str, ...]] | None:
        """The shot's floor line at stage ``y`` as a surface, when the lowest of
        ``contacts`` is within ``tol`` of it as the shot opens; else ``None``."""
        from an.stage.solve import _apply

        world = self.opening([c.node for c in contacts])
        lowest = max(_apply(world[c.node], p)[1] for c in contacts for p in c.points)
        if abs(y - lowest) > tol:
            return None
        floor_at = _stage_surface(ground_line(y))
        return (lambda _world, _t: floor_at), ()

    def _world_floor_stance(
        self, eid: str, contacts: list[_Contact], *, tol: float
    ) -> tuple[Any, tuple[str, ...]] | None:
        """The world's floor under ``eid`` (:meth:`world_floor`), when it has
        one and the lowest of ``contacts`` is within ``tol`` of it as the shot
        opens; else ``None``."""
        found = self.world_floor(eid)
        if found is None:
            return None
        surface, paths = found
        world = self.opening([*(c.node for c in contacts), *paths])
        line = surface(world, 0.0).line
        gap = min(lowest_on(world[c.node], c.points, line)[1] for c in contacts)
        return found if abs(gap) <= tol else None

    def rest_frames(self, eid: str, times: Sequence[float]) -> list[int]:
        """The grid frames at which ``eid`` is judged by an inferred stance: the
        opening one, and every frame between two consecutive keys of its
        chain's channels (:func:`an.timing.timeline.key_times`) over which
        none of them changes."""
        from an.stage.timeline import _node_chain, timeline_from_scene
        from an.timing.timeline import cut_timeline, evaluate_timeline, key_times

        try:
            above = {p for _n, p in _node_chain(self.doc.scene, eid)[1:]}
        except Exception:  # noqa: BLE001 - not drawn on the stage
            return [0]
        paths = above | {p for p in self.nodes if p.startswith(eid + "/")}

        def selected(target: str, _prop: str) -> bool:
            return target in paths

        timeline = cut_timeline(timeline_from_scene(self.doc), where=selected)
        duration = float(self.shot.duration)
        keys = sorted(
            {0.0, duration, *(k for k in key_times(timeline) if 0.0 <= k <= duration)}
        )
        still = []
        for a, b in zip(keys, keys[1:]):
            at_a = evaluate_timeline(timeline, a)
            if all(
                evaluate_timeline(timeline, a + (b - a) * i / 3.0) == at_a
                for i in (1, 2)
            ):
                still.append((a, b))
        return [
            k
            for k, t in enumerate(times)
            if k == 0
            or any(a - SAME_INSTANT_S <= t <= b + SAME_INSTANT_S for a, b in still)
        ]
