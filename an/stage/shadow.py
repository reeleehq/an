"""Contact shadows: an ellipse where a supported member meets its surface (an#519 rank 16, catalogue D2).

A member that says ``shadow: contact`` (its entity's ``overrides.shadow``, or
``metadata.shadow`` in its store document, next to ``shaded_side`` and
``contacts``; the entity's own wins) gets, for each of its supports (a
declared ``support`` joint, or the stance it is taken to have on the shot's
floor, :func:`an.stage.support.supports_at`), one flattened ellipse on the
surface spanning its contacts, painted just under it (and under what rides
just behind it; in a world that reorders it by depth, its shadow rides its
paint keys, :func:`shadow_paint_keys`). It is a compile-pass product (a
synthetic node ``<entity>__shadow``, like the stage's ``__band`` containers),
never authored:

- **where**: the foot of the normal from its held contacts (those within the
  support tolerance of the surface) onto the surface, the midpoint of the
  outermost two when there are several, and the ellipse spans them; with none
  held, under the lowest contact. Along the surface, never below or above it:
  a member that rises leaves its shadow on the floor.
- **tilt**: the surface's direction (a shadow on a tilted crate lies along it;
  the world's floor under a rolled camera, :data:`an.base.GROUND_OVERRIDE`).
- **the light**: offset along the surface away from the scene's light
  (``meta.light``, catalogue D1), by its lean along the surface
  (:func:`light_lean`); straight under the contact with no light.
- **presence**: full while the support is joined and its lowest contact within
  the support tolerance (or sunk: the ``support`` check reports that); fading
  and shrinking as the member rises beyond it, gone
  :data:`CONTACT_SHADOW_FADE` of its height above; gone while the support is
  unjoined, while the member is not seen, and times the member's own alpha.
- **size**: fractions of the member's height and width as the shot opens,
  scaled by its node's scale since (a member the world brings nearer grows,
  and so does its shadow).

Every size is a named fraction (:data:`CONTACT_SHADOW_WIDTH`, ...). A shot
where no member asks for a shadow is not touched (byte-identical), and a
shadow that does not move is a static node with no channel.

``shadow: cast`` (a skewed silhouette along the light) is not built: it is
refused by name (:class:`CastShadowNotBuiltError`).

>>> light_lean((-1.0, -1.0))  # from the upper left: cast to the right
0.7071067811865475
>>> light_lean((0.0, -1.0)), light_lean((1.0, 0.0), elevation=60.0)
(0.0, -0.5000000000000001)
"""

from __future__ import annotations

import math
import warnings
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from an.base import SHADOW_OVERRIDE
from an.stage.compile import CutoutCompileError, CutoutCompileWarning

__all__ = [
    "SHADOW_KEY",
    "CONTACT_SHADOW",
    "CAST_SHADOW",
    "NO_SHADOW",
    "SHADOW_INFIX",
    "CONTACT_SHADOW_WIDTH",
    "CONTACT_SHADOW_SPREAD",
    "CONTACT_SHADOW_MARGIN",
    "CONTACT_SHADOW_FLATTEN",
    "CONTACT_SHADOW_OPACITY",
    "CONTACT_SHADOW_OFFSET",
    "CONTACT_SHADOW_FADE",
    "CONTACT_SHADOW_SHRINK",
    "CONTACT_SHADOW_COLOR",
    "ShadowError",
    "CastShadowNotBuiltError",
    "ShadowPose",
    "shadow_of",
    "light_lean",
    "contact_shadow_pose",
    "shadow_node_name",
    "shadow_owner",
    "shadow_paint_keys",
    "contact_shadow_pass",
]

#: The declaration's key: the entity's ``overrides`` (a core override key,
#: :data:`an.base.SHADOW_OVERRIDE`) or its store document's ``metadata``.
SHADOW_KEY: str = SHADOW_OVERRIDE
#: A flattened ellipse per support, spanning its contacts (built).
CONTACT_SHADOW: str = "contact"
#: A skewed silhouette along the light (catalogue D2's second form; not built).
CAST_SHADOW: str = "cast"
#: No shadow: an entity's override that switches off its art's.
NO_SHADOW: str = "none"
SHADOW_KINDS: tuple[str, ...] = (CONTACT_SHADOW, CAST_SHADOW, NO_SHADOW)
#: Where ``shadow: cast`` is tracked.
CAST_SHADOW_FOLLOW_UP: str = "https://github.com/reeleehq/an/issues/519"
#: The synthetic node's name after the entity id (``__`` is reserved for the
#: stage's own nodes, so no authored id can take it); a member with several
#: supports gets ``<id>__shadow_<k>`` for the second on.
SHADOW_INFIX: str = "__shadow"
#: The clip id prefix of a moving shadow's channels.
SHADOW_CLIP_PREFIX: str = "__shadow__"

#: The ellipse's least width, as a fraction of the member's height ...
CONTACT_SHADOW_WIDTH: float = 0.4
#: ... or of its drawn width as the shot opens, whichever is wider: just wider
#: than what stands on it, so it shows on both sides of a box or a cup.
CONTACT_SHADOW_SPREAD: float = 1.1
#: What the ellipse adds to the span of its held contacts (both feet), as a
#: fraction of the member's height: it reaches past the outermost.
CONTACT_SHADOW_MARGIN: float = 0.15
#: The ellipse's height as a fraction of its least width: a floor seen at a glance.
CONTACT_SHADOW_FLATTEN: float = 0.2
#: Its alpha at full strength (a black ellipse: the floor shows through it).
CONTACT_SHADOW_OPACITY: float = 0.35
#: How far it is cast along the surface, away from the light, per unit of the
#: light's lean along it (:func:`light_lean`), as a fraction of the member's height.
CONTACT_SHADOW_OFFSET: float = 0.15
#: How far above the support tolerance (a fraction of the member's height) the
#: shadow has faded to nothing: a hop keeps a fading one, a float loses it.
CONTACT_SHADOW_FADE: float = 0.15
#: How much it shrinks by the time it has faded (a fraction of its size).
CONTACT_SHADOW_SHRINK: float = 0.5
#: Its colour.
CONTACT_SHADOW_COLOR: str = "#000000"
#: How closely a moving shadow's kept keys reproduce every frame's value
#: (:func:`an.stage.solve.compact_keys`): px for ``x``/``y``, radians, ratios.
SHADOW_KEY_TOLERANCES: dict[str, float] = {
    "x": 0.01,
    "y": 0.01,
    "rotation": 1e-4,
    "scale_x": 1e-4,
    "scale_y": 1e-4,
    "alpha": 1e-3,
}
#: The channels a shadow is keyed on, in the order they are emitted.
SHADOW_CHANNELS: tuple[str, ...] = tuple(SHADOW_KEY_TOLERANCES)
#: Values are rounded to this before keying, so a document is stable to the bit.
_QUANTUM: float = 1e-6
#: A lean below this is none (float noise of a light straight above).
_NO_LEAN: float = 1e-12


class ShadowError(CutoutCompileError):
    """A ``shadow`` declaration the stage cannot draw."""


class CastShadowNotBuiltError(ShadowError):
    """``shadow: cast`` (a skewed silhouette along the light, catalogue D2) is not built yet."""


def _field(doc: Any, name: str) -> Any:
    if isinstance(doc, Mapping):
        return doc.get(name)
    return getattr(doc, name, None)


def shadow_of(entity: Any, desc: Any = None) -> str | None:
    """The shadow ``entity`` asks for: its ``overrides.shadow``, else its store
    document's (``desc``) ``metadata.shadow``; ``None`` for none (``none``,
    ``false`` or unset). ``cast`` and an unknown value are refused by name.

    >>> from types import SimpleNamespace as NS
    >>> shadow_of(NS(id="cup", overrides={"shadow": "contact"}))
    'contact'
    >>> shadow_of(NS(id="cup", overrides={"shadow": "none"}), {"metadata": {"shadow": "contact"}}) is None
    True
    >>> shadow_of(NS(id="cup", overrides=None), {"metadata": {"shadow": "contact"}})
    'contact'
    >>> shadow_of(NS(id="cup", overrides={"shadow": "cast"}))
    Traceback (most recent call last):
    ...
    an.stage.shadow.CastShadowNotBuiltError: ...
    """
    overrides = getattr(entity, "overrides", None) or {}
    if SHADOW_KEY in overrides:
        value = overrides[SHADOW_KEY]
    else:
        meta = _field(desc, "metadata") if desc is not None else None
        value = meta.get(SHADOW_KEY) if isinstance(meta, Mapping) else None
    if value is None or value is False or value == NO_SHADOW:
        return None
    if value == CAST_SHADOW:
        raise CastShadowNotBuiltError(
            f"{getattr(entity, 'id', entity)!r} asks for `shadow: cast` (a skewed "
            "silhouette along the light, catalogue D2), which is not built yet: "
            f"only `shadow: {CONTACT_SHADOW}` is (one ellipse per support, spanning "
            f"its contacts, offset from the light). Say `shadow: {CONTACT_SHADOW}`, or follow the cast "
            f"shadow's follow-up at {CAST_SHADOW_FOLLOW_UP}."
        )
    if value != CONTACT_SHADOW:
        raise ShadowError(
            f"{getattr(entity, 'id', entity)!r} asks for `shadow: {value!r}`; a "
            f"shadow is one of {list(SHADOW_KINDS)} (`{CAST_SHADOW}` is not built yet)"
        )
    return CONTACT_SHADOW


def light_lean(
    light: Sequence[float] | None,
    *,
    elevation: float | None = None,
    along: Sequence[float] = (1.0, 0.0),
) -> float:
    """How far a shadow falls along a surface of unit direction ``along``,
    away from a light that comes FROM ``light`` on screen (x right, y down;
    :attr:`an.ir.schema.SceneLight.vector`), per unit of the offset: the
    component of the direction away from the light along the surface, or,
    when the light's ``elevation`` (degrees above the ground) is said, its
    cosine on that side. ``0`` with no light or one straight above.

    >>> light_lean((1.0, -1.0))  # from the upper right: cast to the left
    -0.7071067811865475
    >>> light_lean((-1.0, -1.0), elevation=90.0) < 1e-12, light_lean(None)
    (True, 0.0)
    >>> round(light_lean((-1.0, 0.0), along=(0.0, -1.0)), 12)  # a wall's surface
    0.0
    """
    if light is None:
        return 0.0
    lx, ly = float(light[0]), float(light[1])
    norm = math.hypot(lx, ly)
    if norm == 0:
        return 0.0
    lean = -(lx * along[0] + ly * along[1]) / norm
    if abs(lean) <= _NO_LEAN:
        return 0.0
    if elevation is not None:
        return math.copysign(math.cos(math.radians(float(elevation))), lean)
    return lean + 0.0


@dataclass(frozen=True)
class ShadowPose:
    """A contact shadow at one instant, on the stage: its centre, its tilt
    (radians), its width (px, before ``shrink``), its alpha, and how much it
    has shrunk as its member rose (1: not at all)."""

    x: float
    y: float
    rotation: float
    width: float
    alpha: float
    shrink: float = 1.0


def contact_shadow_pose(
    state: Any,
    *,
    height: float,
    light: Sequence[float] | None = None,
    elevation: float | None = None,
    tolerance: float | None = None,
    least: float | None = None,
    width: float = CONTACT_SHADOW_WIDTH,
    margin: float = CONTACT_SHADOW_MARGIN,
    offset: float = CONTACT_SHADOW_OFFSET,
    fade: float = CONTACT_SHADOW_FADE,
    shrink: float = CONTACT_SHADOW_SHRINK,
    opacity: float = CONTACT_SHADOW_OPACITY,
) -> ShadowPose | None:
    """The contact shadow of one :class:`an.stage.support.SupportState`, its
    member ``height`` px tall now; ``None`` when it measured no contact (off a
    bounded surface's ends). ``tolerance`` defaults to the support's
    (:func:`an.stage.support.support_tolerance` of ``height``), ``least`` (the
    narrowest the ellipse is, px) to ``width`` of ``height``.

    >>> from an.stage.support import ContactState, SupportState
    >>> floor = ((0.0, 100.0), (1.0, 0.0))
    >>> def at(*feet, joined=True):
    ...     cs = tuple(ContactState(f"c{i}", "cup", p, 100.0 - p[1]) for i, p in enumerate(feet))
    ...     return SupportState("cup", None, "", 0, 0.0, floor, "ground", cs, joined, 50.0, "metadata")
    >>> p = contact_shadow_pose(at((10.0, 100.0)), height=50.0)
    >>> (p.x, p.y, p.width, p.alpha, p.shrink)
    (10.0, 100.0, 20.0, 0.35, 1.0)
    >>> contact_shadow_pose(at((10.0, 100.0)), height=50.0, light=(-1.0, 0.0)).x  # cast right
    17.5
    >>> contact_shadow_pose(at((0.0, 100.0), (40.0, 100.0)), height=50.0).width  # both feet
    47.5
    >>> contact_shadow_pose(at((10.0, 100.0), joined=False), height=50.0).alpha
    0.0
    >>> contact_shadow_pose(at((10.0, 90.0)), height=50.0).alpha  # risen 10 px: faded
    0.0
    """
    from an.stage.support import support_tolerance

    if not state.contacts:
        return None
    tol = support_tolerance(height) if tolerance is None else tolerance
    (ax, ay), (ux, uy) = state.surface
    held = [c for c in state.contacts if abs(c.above) <= tol]
    use = held or [min(state.contacts, key=lambda c: c.above)]
    feet = [(c.at[0] - ax) * ux + (c.at[1] - ay) * uy for c in use]
    lo, hi = min(feet), max(feet)
    lean = light_lean(light, elevation=elevation, along=(ux, uy))
    mid = (lo + hi) / 2.0 + lean * offset * height
    rise = max(0.0, min(c.above for c in state.contacts) - tol)
    gone = fade * height
    k = 1.0 if gone <= 0 and rise > 0 else (min(1.0, rise / gone) if gone > 0 else 0.0)
    return ShadowPose(
        x=ax + mid * ux + 0.0,
        y=ay + mid * uy + 0.0,
        rotation=math.atan2(uy, ux) + 0.0,
        width=max(
            (hi - lo) + margin * height, width * height if least is None else least
        ),
        alpha=(opacity * (1.0 - k) + 0.0) if state.joined else 0.0,
        shrink=1.0 - shrink * k,
    )


def shadow_node_name(entity: str, k: int = 0) -> str:
    """The synthetic node of ``entity``'s ``k``-th support's shadow.

    >>> shadow_node_name("cup"), shadow_node_name("cup", 1)
    ('cup__shadow', 'cup__shadow_1')
    """
    return f"{entity}{SHADOW_INFIX}" + (f"_{k}" if k else "")


# -----------------------------------------------------------------------------
# The compile pass
# -----------------------------------------------------------------------------


def _asked(state: Any) -> dict[str, str]:
    """``{entity id: shadow}`` for every entity of the shot that asks for one."""
    from an.stage.support import _descriptor_of

    vocab_descs = getattr(state.vocab, "descriptors", None) or {}
    out: dict[str, str] = {}
    for e in state.shot.entities:
        desc = None
        if SHADOW_KEY not in (e.overrides or {}):
            desc = vocab_descs.get(e.id) or _descriptor_of(e, state.mall)
        kind = shadow_of(e, desc)
        if kind is not None:
            out[e.id] = kind
    return out


def _least(height: float, breadth: float) -> float:
    """The narrowest a member's shadow is (px): :data:`CONTACT_SHADOW_WIDTH` of
    its ``height`` or :data:`CONTACT_SHADOW_SPREAD` of its ``breadth``.

    >>> _least(100.0, 20.0), _least(30.0, 30.0)
    (40.0, 33.0)
    """
    return max(CONTACT_SHADOW_WIDTH * height, CONTACT_SHADOW_SPREAD * breadth)


def _opening_widths(
    doc: Any, nodes: Mapping[str, Any], entities: Sequence[str], timeline: Any
) -> dict[str, float]:
    """Each entity's drawn width as the shot opens (px, stage): the span in
    ``x`` of its drawn nodes' boxes, as the support's height is in ``y``."""
    from an.stage.solve import _apply, local_box, world_matrices
    from an.timing.timeline import evaluate_timeline

    pose = evaluate_timeline(timeline, 0.0)
    out: dict[str, float] = {}
    for eid in entities:
        drawn = [
            p
            for p, n in nodes.items()
            if (p == eid or p.startswith(eid + "/")) and n.visual is not None
        ]
        world = world_matrices(doc, drawn, pose, nodes)
        xs = [
            _apply(world[p], (left + dx, top + dy))[0]
            for p in drawn
            for left, top, w, h in (local_box(nodes[p]),)
            for dx, dy in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h))
        ]
        out[eid] = (max(xs) - min(xs)) if xs else 0.0
    return out


def _scale(m: Sequence[float]) -> float:
    """A world matrix's uniform scale (the root of its determinant's size)."""
    return math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))


def _filled(values: list[Any], fallback: Any) -> list[Any]:
    """``values`` with each ``None`` replaced by the nearest value before it,
    else after it (a hidden shadow holds where it was, so it never sweeps).

    >>> _filled([None, 1, None, 2, None], 0)
    [1, 1, 1, 2, 2]
    """
    first = next((v for v in values if v is not None), fallback)
    out, last = [], first
    for v in values:
        last = v if v is not None else last
        out.append(last)
    return out


@dataclass(frozen=True)
class _Shadow:
    """One shadow node the pass places: its ``name``, its channels' value at
    every frame of the grid (``values``), and its ellipse's ``width`` and
    ``height`` (px) at full size."""

    member: str
    name: str
    values: dict[str, list[float]]
    width: float
    height: float


def contact_shadow_pass(state: Any) -> None:
    """The ``contact_shadows`` compile pass (catalogue D2): a shadow node under
    each supported member that asks for one, one per support (spanning its
    contacts), keyed every frame of the shot's grid where it moves. A no-op
    (byte-identical) when no member asks."""
    asked = _asked(state)
    if not asked:
        return
    from an.stage.compile import _assemble_document, _rebuild_vocabulary
    from an.stage.solve import frame_times

    doc = _assemble_document(state, background="#000000")
    times = frame_times(state.shot.duration, fps=state.fps, step_hz=state.step_hz)
    series = _support_series(state, asked, doc=doc, times=times)
    if not series:
        return
    shadows = _shadow_values(
        series, getattr(state, "light", None), doc=doc, times=times
    )
    if not shadows:
        return
    _place(state, shadows, times=times)
    _rebuild_vocabulary(state)


def _support_series(
    state: Any, asked: Mapping[str, str], *, doc: Any, times: Sequence[float]
) -> dict[tuple[str, str], dict[int, Any]]:
    """``{(entity, support): {frame: SupportState}}`` for every member in
    ``asked``, over the grid ``times``; a member nothing supports is said, by
    name, to draw none."""
    from an.stage.support import supports_at

    shot = state.shot
    states, _problems = supports_at(doc, shot, state.mall, times=times, rest_only=False)
    series: dict[tuple[str, str], dict[int, Any]] = {}
    for s in states:
        if s.entity in asked:
            series.setdefault((s.entity, s.where), {})[s.frame] = s
    supported = {e for e, _ in series}
    for eid in asked:
        if eid not in supported:
            warnings.warn(
                f"shot {shot.id!r}: {eid!r} asks for a contact shadow (`shadow: "
                f"{CONTACT_SHADOW}`) but nothing supports it, so none is drawn: "
                "declare a `support` joint, or a floor it stands on (`solve: "
                "{ground: y}`, a world's `ground`).",
                CutoutCompileWarning,
                stacklevel=3,
            )
    return series


def _member_frames(
    doc: Any,
    nodes: Mapping[str, Any],
    entities: Sequence[str],
    timeline: Any,
    times: Sequence[float],
) -> dict[str, list[tuple[float, float]]]:
    """``{entity: [(alpha, growth)]}`` at each of ``times``: its alpha, and its
    node's scale relative to the shot's opening (a member the world brings
    nearer grows, and so does its shadow)."""
    from an.stage.solve import world_matrices
    from an.stage.timeline import entity_alpha
    from an.timing.timeline import evaluate_timeline

    opening: dict[str, float] = {}
    out: dict[str, list[tuple[float, float]]] = {e: [] for e in entities}
    for t in times:
        pose = evaluate_timeline(timeline, t)
        world = world_matrices(doc, entities, pose, nodes)
        for eid in entities:
            try:
                alpha = entity_alpha(doc, pose, eid)
            except KeyError:
                alpha = 1.0
            scale = _scale(world[eid])
            first = opening.setdefault(eid, scale)
            out[eid].append((alpha, scale / first if first > 0 else 1.0))
    return out


def _shadow_values(
    series: Mapping[tuple[str, str], Mapping[int, Any]],
    light: Any,
    *,
    doc: Any,
    times: Sequence[float],
) -> dict[str, list[_Shadow]]:
    """``{entity: [shadow]}``: each support's shadow (``series``, from
    :func:`_support_series`) under ``light`` (a :class:`an.ir.schema.SceneLight`,
    or ``None``), its channels' values at every frame of ``times``; a shadow
    never seen at any frame is left out."""
    from an.stage.solve import node_index
    from an.stage.timeline import timeline_from_scene

    nodes = node_index(doc)
    timeline = timeline_from_scene(doc)
    vector = light.vector if light is not None else None
    elevation = getattr(light, "elevation", None)
    entities = sorted({e for e, _ in series})
    breadth = _opening_widths(doc, nodes, entities, timeline)
    frames = _member_frames(doc, nodes, entities, timeline, times)
    out: dict[str, list[_Shadow]] = {}
    for (eid, _where), by_frame in series.items():
        poses = _series_poses(
            by_frame,
            frames[eid],
            breadth=breadth[eid],
            light=vector,
            elevation=elevation,
        )
        if not any(p is not None and p.alpha > 0 for p in poses):
            continue
        first = next(iter(by_frame.values()))
        mine = out.setdefault(eid, [])
        mine.append(
            _shadow_track(
                eid,
                shadow_node_name(eid, len(mine)),
                poses,
                thick=CONTACT_SHADOW_FLATTEN * _least(first.height, breadth[eid]),
            )
        )
    return out


def _series_poses(
    by_frame: Mapping[int, Any],
    frames: Sequence[tuple[float, float]],
    *,
    breadth: float,
    light: Sequence[float] | None,
    elevation: float | None,
) -> list[ShadowPose | None]:
    """One support's shadow at each frame (``None`` where it measured nothing
    or its member is not seen), times the member's own alpha."""
    from an.base import UNSEEN_ALPHA

    poses: list[ShadowPose | None] = []
    for i, (alpha, grown) in enumerate(frames):
        s = by_frame.get(i)
        if s is None or alpha <= UNSEEN_ALPHA:
            poses.append(None)
            continue
        p = contact_shadow_pose(
            s,
            height=s.height * grown,
            least=_least(s.height, breadth) * grown,
            light=light,
            elevation=elevation,
        )
        if p is not None:
            p = replace(p, alpha=p.alpha * min(1.0, alpha))
        poses.append(p)
    return poses


def _shadow_track(
    member: str, name: str, poses: Sequence[ShadowPose | None], *, thick: float
) -> _Shadow:
    """The shadow node ``name`` of ``member`` from its ``poses``: an ellipse as
    wide as its widest pose, each frame's width and shrink a scale of it; a
    frame with no pose holds the nearest one's place, at alpha 0."""
    base = max(p.width for p in poses if p is not None)
    shown = [
        None
        if p is None
        else {
            "x": p.x,
            "y": p.y,
            "rotation": p.rotation,
            "scale_x": p.width / base * p.shrink,
            "scale_y": p.shrink,
            "alpha": p.alpha,
        }
        for p in poses
    ]
    held = _filled(shown, None)
    values = {prop: [_q(h[prop]) for h in held] for prop in SHADOW_CHANNELS}
    values["alpha"] = [0.0 if s is None else _q(s["alpha"]) for s in shown]
    return _Shadow(member, name, values, base, thick)


def _q(value: float) -> float:
    return round(value / _QUANTUM) * _QUANTUM + 0.0


# -----------------------------------------------------------------------------
# Placing the nodes, and their paint keys
# -----------------------------------------------------------------------------


def shadow_owner(name: str) -> tuple[str, int] | None:
    """``(entity, k)`` of the shadow node ``name`` (:func:`shadow_node_name`),
    ``None`` for any other node.

    >>> shadow_owner("cup__shadow"), shadow_owner("cup__shadow_2"), shadow_owner("cup")
    (('cup', 0), ('cup', 2), None)
    >>> shadow_owner("cup__shadow_x"), shadow_owner("__shadow")
    (None, None)
    """
    head, sep, tail = name.rpartition(SHADOW_INFIX)
    if not sep or not head:
        return None
    if not tail:
        return head, 0
    k = tail[1:]
    return (head, int(k)) if tail[0] == "_" and k.isdigit() and int(k) > 0 else None


def shadow_paint_keys(
    names: Sequence[str], keys: Mapping[str, Sequence[tuple[float, Any]]]
) -> dict[str, list[tuple[float, list]]]:
    """The paint keys (:data:`an.base.PAINT_KEYS_OVERRIDE`) of the shadow nodes
    among ``names``, the children of one container, whose member has keys in
    ``keys``: each rides its member just behind it at every time
    (:func:`an.base.rider_key`, :data:`an.base.RIDER_BEHIND`), behind the
    member's other riders on that side too (their ``n`` is never negative), as
    :func:`_place` builds it, so a world that reorders its member by depth
    moves its shadow with it (an#634).

    >>> keys = {"a": [(0.0, [1, 5, 0]), (1.0, [1, 3, 0])], "b": [(0.0, [1, 4, 0])]}
    >>> shadow_paint_keys(["a__shadow", "a", "b__shadow_1", "b"], keys)["a__shadow"]
    [(0.0, [1, 5, 0, -1, -1]), (1.0, [1, 3, 0, -1, -1])]
    >>> shadow_paint_keys(["c__shadow", "c"], keys)
    {}
    """
    from an.base import RIDER_BEHIND, rider_key

    owned = {
        name: owner
        for name in names
        if (owner := shadow_owner(name)) is not None and owner[0] in keys
    }
    count = Counter(eid for eid, _ in owned.values())
    return {
        name: [
            (t, rider_key(key, side=RIDER_BEHIND, n=k - count[eid]))
            for t, key in keys[eid]
        ]
        for name, (eid, k) in owned.items()
    }


def _behind_riders(entities: Sequence[Any]) -> dict[str, set[str]]:
    """``{host: {rider}}``: the entities drawn just behind their host, by the
    world's mark (:data:`an.base.BESIDE_HOST_OVERRIDE`) or their paint keys."""
    from an.base import (
        BESIDE_HOST_OVERRIDE,
        PAINT_KEYS_OVERRIDE,
        RIDER_BEHIND,
        RIDER_SUFFIX_LEN,
        paint_key_items,
        rider_host_key,
    )

    out: dict[str, set[str]] = {}
    opening = {
        e.id: paint_key_items(e.overrides[PAINT_KEYS_OVERRIDE][0][1])
        for e in entities
        if PAINT_KEYS_OVERRIDE in (e.overrides or {})
    }
    by_key = {key: eid for eid, key in opening.items()}
    for e in entities:
        mark = (e.overrides or {}).get(BESIDE_HOST_OVERRIDE)
        if isinstance(mark, Mapping) and mark.get("side") == RIDER_BEHIND:
            out.setdefault(mark.get("host"), set()).add(e.id)
        key = opening.get(e.id)
        host = by_key.get(rider_host_key(key)) if key is not None else None
        if host is not None and key[-RIDER_SUFFIX_LEN] == RIDER_BEHIND:
            out.setdefault(host, set()).add(e.id)
    return out


def _place(
    state: Any,
    shadows: Mapping[str, Sequence[_Shadow]],
    *,
    times: Sequence[float],
) -> None:
    """Insert each member's shadow nodes in the container that holds it, just
    behind it and behind what rides just behind it (painted under them, over
    what is behind them), with their opening values as their rest transform,
    and key each channel that moves."""
    from an.stage import tree as stage_tree

    riders = _behind_riders(state.shot.entities)
    for container in stage_tree.entity_containers(state.scene_root):
        kids = list(container.children or [])
        out: list[Any] = []
        for kid in kids:
            mine = shadows.get(kid.name, ())
            if mine:
                at = len(out)
                behind = riders.get(kid.name, set())
                while at and out[at - 1].name in behind:
                    at -= 1
                out[at:at] = [_shadow_node(s) for s in mine]
                for s in mine:
                    _add_shadow_clip(state, s, times=times)
            out.append(kid)
        if len(out) != len(kids):
            container.children = out


def _shadow_node(shadow: _Shadow) -> Any:
    """The ellipse node of ``shadow``, at its opening values."""
    from an.stage.serialize import NodeJSON, TransformJSON, VisualJSON

    return NodeJSON(
        name=shadow.name,
        transform=TransformJSON(**{p: vs[0] for p, vs in shadow.values.items()}),
        visual=VisualJSON(
            kind="ellipse",
            width=_q(shadow.width),
            height=_q(shadow.height),
            color=CONTACT_SHADOW_COLOR,
        ),
    )


def _shadow_channels(
    shadow: _Shadow, *, times: Sequence[float], stepped: bool
) -> list[Any]:
    """A channel for each of ``shadow``'s properties that moves, its keys the
    fewest that reproduce every frame (:func:`an.stage.solve.compact_keys`)."""
    from an.stage.serialize import ChannelJSON, KeyframeJSON
    from an.stage.solve import compact_keys

    easing = "step" if stepped else "linear"
    channels = []
    for prop in SHADOW_CHANNELS:
        vs = shadow.values[prop]
        tolerance = SHADOW_KEY_TOLERANCES[prop]
        if max(vs) - min(vs) <= tolerance:
            continue
        kept = compact_keys(times, vs, tolerance=tolerance, stepped=stepped)
        channels.append(
            ChannelJSON(
                target=shadow.name,
                property=prop,
                keyframes=[
                    KeyframeJSON(
                        time=round(times[i], 9) + 0.0, value=vs[i], easing=easing
                    )
                    for i in kept
                ],
            )
        )
    return channels


def _add_shadow_clip(state: Any, shadow: _Shadow, *, times: Sequence[float]) -> None:
    """``shadow``'s moving channels as a clip of their own on the shot's
    timeline (none for a shadow that does not move)."""
    from an.stage.compile import _fresh_clip_id
    from an.stage.serialize import AnimationClipJSON, PlacedClipJSON, TrackJSON

    channels = _shadow_channels(shadow, times=times, stepped=state.step_hz is not None)
    if not channels:
        return
    duration = max(0.001, float(state.shot.duration))
    clip = _fresh_clip_id(f"{SHADOW_CLIP_PREFIX}{shadow.name}", state.animations)
    state.animations[clip] = AnimationClipJSON(
        name=clip, duration=duration, channels=channels
    )
    state.tracks.append(
        TrackJSON(
            target_root=shadow.name,
            clips=[
                PlacedClipJSON(animation_id=clip, start_time=0.0, duration=duration)
            ],
        )
    )
