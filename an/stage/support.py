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
  (:func:`an.stage.surface_line.above`'s sign: positive above, negative sunk),
  with the references that do not resolve returned as ``(where, message)``.

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
from an.stage.surface_line import Line, ground_line, line_through

__all__ = [
    "CONTACT_SOURCES",
    "CONTACTS_KEY",
    "SUPPORT_TOLERANCE",
    "SUPPORT_FLOOR_PX",
    "FLOAT_BAND",
    "Contacts",
    "ContactState",
    "SupportState",
    "support_tolerance",
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
#: How far from its floor, as a fraction of its height, an entity nothing
#: declares may be and still be taken to stand on it as the shot opens.
FLOAT_BAND: float = 0.4
#: How close (px, at rest in the entity's own frame) a part's painted bottom
#: must come to the rig's ``origin`` for the origin to be where it stands
#: (:data:`an.stage.hold.SUPPORT_TOLERANCE_PX`'s rule, an#601).
ORIGIN_TOUCH_PX: float = 1.0
#: Two instants closer than this are one.
SAME_INSTANT_S: float = 1e-9


def support_tolerance(height: float) -> float:
    """How far a contact of an entity ``height`` px tall may be off its surface.

    >>> support_tolerance(500.0)
    10.0
    """
    return max(SUPPORT_TOLERANCE * float(height), SUPPORT_FLOOR_PX)


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
    what the solve's point resolver adds to a rig's landmarks, so a joint or a
    verb may name ``paul@foot_l`` as it names ``paul@hand_l``.

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


def _origin_touched(doc: Any, entity: Any, rig: Any, mall: Any) -> bool:
    """Whether a root part's painted bottom rests on the entity's origin, at rest
    (an#601: a stick's middle or a wheel's hub is where it is held)."""
    from an.stage.hold import ink_points
    from an.stage.solve import _apply, _compose, _invert, _node_index, _world_matrices

    nodes = _node_index(doc)
    eid = entity.id
    if eid not in nodes:
        return False
    roots = _root_paths(eid, rig, nodes)
    rest = _world_matrices(doc, [eid, *roots], None, nodes)
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
    from an.stage.solve import _local_box, _node_index

    nodes = _node_index(doc)
    roots = _root_paths(entity.id, rig, nodes) if entity.id in nodes else []
    return bool(roots) and all(
        set(ink_points(doc, nodes[p], mall)) != set(_corners(_local_box(nodes[p])))
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
    #: ``(the line, the segment's ends or None)`` at an instant, from world matrices.
    surface: Any = None
    surface_paths: tuple[str, ...] = ()
    events: list[tuple[float, bool]] = field(default_factory=list)
    instants: frozenset[int] | None = None  # None: every frame


def supports_at(
    doc: Any,
    shot: Shot,
    mall: Mapping[str, Any] | None,
    *,
    times: Sequence[float] | None = None,
    inferred: bool = True,
) -> tuple[list[SupportState], list[tuple[str, str]]]:
    """Every declared support of ``shot`` in its compiled document ``doc`` at
    every instant of ``times`` (default: the solve's frame grid,
    :func:`an.stage.solve.frame_times`), joined or not; and, with
    ``inferred``, every entity taken to stand on the shot's floor
    (``solve: {ground: y}``) as it opens, at that instant and its rest
    instants. Returns the states and ``(where, message)`` for each reference
    that does not resolve (no state is made for it)."""
    from an.stage.solve import (
        _node_index,
        _world_matrices,
        declarations,
        frame_times,
    )
    from an.stage.timeline import timeline_from_scene
    from an.timing.timeline import evaluate_timeline

    mall = mall or {}
    nodes = _node_index(doc)
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
            found.events = sorted(events.get(dj.spec.id, ()), key=lambda e: e[0])
            supports.append(found)
    if inferred:
        declared_entities = {s.entity for s in supports} | {
            dj.a.partition("@")[0].split("/", 1)[0] for dj in decl.supports
        }
        supports.extend(reader.stances(times, skip=declared_entities))
    if not supports:
        return [], problems

    timeline = timeline_from_scene(doc)
    paths = sorted(
        {p for s in supports for p in (*(c.node for c in s.contacts), *s.surface_paths)}
    )
    out: list[SupportState] = []
    for k, t in enumerate(times):
        due = [s for s in supports if s.instants is None or k in s.instants]
        if not due:
            continue
        pose = evaluate_timeline(timeline, t)
        world = _world_matrices(doc, paths, pose, nodes)
        for s in due:
            out.append(_state(s, k, t, world, reader.height(s.entity)))
    return out, problems


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
    s: _Support, k: int, t: float, world: Mapping[str, Any], height: float
) -> SupportState:
    from an.stage.solve import _apply

    line, ends = s.surface(world)
    (ax, ay), (dx, dy) = line
    nx, ny = -dy, dx
    contacts = []
    for c in s.contacts:
        pts = [_apply(world[c.node], p) for p in c.points]
        low = max(pts, key=lambda p: nx * (p[0] - ax) + ny * (p[1] - ay))
        if ends is not None and not _on_segment(low, *ends):
            continue  # off a bounded surface's ends: nothing to stand on
        depth = nx * (low[0] - ax) + ny * (low[1] - ay)
        contacts.append(
            ContactState(c.name, c.node, (low[0] + 0.0, low[1] + 0.0), -depth + 0.0)
        )
    return SupportState(
        entity=s.entity,
        joint=s.joint,
        where=s.where,
        frame=k,
        t=t,
        surface=line,
        surface_ref=s.surface_ref,
        contacts=tuple(contacts),
        joined=_joined(s.events, t),
        height=height,
        source=s.source,
        named=s.named,
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
        from an.stage.solve import _world_matrices
        from an.stage.timeline import timeline_from_scene
        from an.timing.timeline import evaluate_timeline

        if self._open_world is None:
            self._open_pose = evaluate_timeline(timeline_from_scene(self.doc), 0.0)
            self._open_world = {}
        missing = [p for p in paths if p not in self._open_world]
        if missing:
            self._open_world.update(
                _world_matrices(self.doc, missing, self._open_pose, self.nodes)
            )
        return self._open_world

    def height(self, eid: str) -> float:
        """The entity's drawn height as the shot opens (px, stage)."""
        from an.stage.solve import _apply, _local_box

        if eid not in self._heights:
            drawn = [
                p
                for p, n in self.nodes.items()
                if (p == eid or p.startswith(eid + "/")) and n.visual is not None
            ]
            world = self.opening(drawn)
            ys = []
            for p in drawn:
                left, top, w, h = _local_box(self.nodes[p])
                for c in (
                    (left, top),
                    (left + w, top),
                    (left, top + h),
                    (left + w, top + h),
                ):
                    ys.append(_apply(world[p], c)[1])
            self._heights[eid] = (max(ys) - min(ys)) if ys else 0.0
        return self._heights[eid]

    # -- contacts as nodes and points ---------------------------------------

    def _resolve_point(
        self, eid: str, slot: str, point: Any, *, name: str, source: str = "point"
    ) -> list[_Contact] | str:
        """A ``(slot, point)`` of the chain as contacts, or why it cannot be."""
        from an.stage.hold import ink_points
        from an.stage.solve import _local_box, _pivot, end_effector

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
        node = self.nodes[node_path]
        box = _local_box(node)
        if point is None:  # the drawn extent's far end from the pivot: no inset
            local = end_effector(box, _pivot(node), inset=0.0)
        else:
            local = (box[0] + point[0] * box[2], box[1] + point[1] * box[3])
        return [_Contact(name, node_path, (local,))]

    def contacts_named(
        self, ref: str, *, where: str, problems: list
    ) -> tuple[list[_Contact], str, str] | None:
        """``a`` of a support as contacts, their source, and the name it gave."""
        from an.stage.hold import _anchors_in, _corners, ink_points
        from an.stage.solve import (
            WORLD_REF,
            _bone_carrier,
            _local_box,
            _numbers,
            _slot_path,
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
                if set(pts) == set(_corners(_local_box(self.nodes[part])))
                else "ink"
            )
            return [_Contact(source, part, tuple(pts))], source, ""

        def node_for(bone: str | None = None) -> str | None:
            if part is not None:
                return part
            if rig is not None and bone is not None and len(rig.roots) > 1:
                carrier = _bone_carrier(rig, bone)
                if carrier is not None:
                    return f"{eid}/{rig.bodies[carrier]}"
            roots = _root_paths(eid, rig, self.nodes)
            if len(roots) != 1:
                problems.append(
                    (
                        where,
                        f"{ref!r}: {eid!r} has {len(roots)} root parts; name the part (`{eid}/<part>@{at}`)",
                    )
                )
                return None
            return roots[0]

        xy = _numbers(at)
        if xy is not None:
            node_path = node_for()
            if node_path is None:
                return None
            left, top, w, h = _local_box(self.nodes[node_path])
            local = (left + xy[0] * w, top + xy[1] * h)
            return [_Contact(at, node_path, (local,))], "point", at
        if rig is not None and at in rig.anchors:
            node_path = node_for(at)
            if node_path is None:
                return None
            bones = _anchors_in(self.doc, rig, eid, self.nodes, node_path)
            return [_Contact(at, node_path, (bones[at],))], "point", at
        landmark = self._landmarks(eid).get(at)
        if landmark is not None:
            got = self._resolve_point(eid, landmark[0], landmark[1], name=at)
            if isinstance(got, str):
                problems.append((where, f"{ref!r}: {got}"))
                return None
            return got, "point", at
        if at in chain.points:
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
        """``b`` as ``(world -> (line, ends or None), the node paths it reads)``."""
        from an.stage.hold import SURFACE_BONES, _anchors_in, ink_box
        from an.stage.solve import WORLD_REF, _apply, _numbers, _slot_path

        if ref == GROUND_SURFACE:
            line = ground_line(self.floor(entity, contacts))
            return (lambda _world: (line, None)), ()
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
            line = line_through(a, b)
            return (lambda _world: (line, (a, b))), ()
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
        bones = (
            _anchors_in(self.doc, rig, eid, self.nodes, node_path)
            if rig is not None
            else {}
        )
        declared = [b for b in SURFACE_BONES if b in bones]
        if len(declared) == len(SURFACE_BONES):
            seg = (bones[SURFACE_BONES[0]], bones[SURFACE_BONES[1]])
        elif declared:
            problems.append(
                (
                    where,
                    f"{ref!r}: {eid!r} declares {declared[0]!r} but not the other of {list(SURFACE_BONES)}: a surface is two bones, or neither (the top of its ink)",
                )
            )
            return None
        else:
            left, top, w, _h = ink_box(self.doc, self.nodes[node_path], self.mall)
            seg = ((left, top), (left + w, top))

        def at_instant(world: Mapping[str, Any]) -> tuple[Line, Any]:
            m = world[node_path]
            a, b = _apply(m, seg[0]), _apply(m, seg[1])
            return line_through(a, b), (a, b)

        return at_instant, (node_path,)

    def floor(self, eid: str, contacts: list[_Contact]) -> float:
        """The shot's floor line (``solve: {ground: y}``), else where the entity's
        contacts are as the shot opens (its own floor)."""
        from an.stage.solve import _apply

        solve = self.shot.solve
        if solve is not None and solve.ground is not None:
            return float(solve.ground)
        world = self.opening([c.node for c in contacts])
        return max(_apply(world[c.node], p)[1] for c in contacts for p in c.points)

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
            joint=dj.spec.id,
            where=dj.where,
            surface_ref=dj.b if dj.end is None else f"{dj.b} to {dj.end}",
            contacts=contacts,
            source=source,
            named=named,
            surface=at_instant,
            surface_paths=paths,
        )

    def stances(self, times: Sequence[float], *, skip: set[str]) -> list[_Support]:
        """The entities taken to stand on the shot's floor as it opens (§2.4 of
        the spec): a rig kind, not held by the hold layer, whose contacts are
        not a box's corners, within :data:`FLOAT_BAND` of its height of the
        floor; each judged as it opens and at its rest instants."""
        from an.stage.hold import hold_declarations
        from an.stage.solve import _apply, _is_rig_kind

        solve = self.shot.solve
        if solve is None or solve.ground is None:
            return []
        try:
            items = set(hold_declarations(self.shot).items)
        except Exception:  # noqa: BLE001 - the hold checks report broken holds
            items = set()
        floor = ground_line(float(solve.ground))
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
            world = self.opening([c.node for c in contacts])
            lowest = max(
                _apply(world[c.node], p)[1] for c in contacts for p in c.points
            )
            if abs(float(solve.ground) - lowest) > FLOAT_BAND * self.height(e.id):
                continue
            out.append(
                _Support(
                    entity=e.id,
                    joint=None,
                    where=f"entities/{self.shot.entities.index(e)}",
                    surface_ref=GROUND_SURFACE,
                    contacts=contacts,
                    source=chain.source,
                    surface=lambda _world, floor=floor: (floor, None),
                    instants=frozenset(self.rest_frames(e.id, times)),
                )
            )
        return out

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
