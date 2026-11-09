"""The ``support`` and ``skate`` checks: a body declared to rest on a surface does, and its feet do not slide on it (an#519, catalogue A1 and B3).

Two constraints on the one interface (:class:`an.verify.constraints.Constraint`),
lint-only (no solver term in v1), over the compiled shot, measured by the pure
function :func:`an.stage.support.supports_at`. ``support`` (order 252):

- a declared ``support`` joint (``{type: support, a: paul, b: ground}``) whose
  contacts sink into its surface (**penetration**) or whose lowest contact is
  above it (**floating**) by more than :func:`an.stage.support.support_tolerance`
  of the entity's height, at any frame of the solve's grid at which it is
  joined, is an **error** span; a reference it cannot resolve is an error too
  (the solve never sees a support, so ``unknown_body`` cannot say it);
- an entity nothing declares, taken to stand on the shot's floor
  (``solve: {ground: y}``) as it opens, is held to it at its rest instants
  (between two keys where nothing of it moves), as a **warning**;
- ``b: ground`` on a shot with no floor is measured against where the entity
  stands as the shot opens, said once as ``info``.

Not judged: an unjoined span (``unjoin`` suspends the support: it is not a
flight), an entity's declared flight (``overrides.airborne``), an item the
hold layer moves when nothing declares a support on it (``floating_item``'s).

``skate`` (order 253, catalogue B3 i): a limb's contact (a foot: one the
kind's hook or ``metadata.contacts`` puts on a named part) **held** on its
surface at two adjacent frames (its support joined, within the support
tolerance) whose foot moved along the surface by more than
:func:`an.stage.support.skate_tolerance` of the entity's height per frame is
foot skate. The drift is measured in the surface's own frame, from a point
fixed in it (a body's first surface end; the stage's origin for the floor), so
a figure standing on a crate that is pushed does not skate. An error span for
a declared support; for an entity taken to stand on the floor, a warning, and
only under a style pack that declares ``gravity`` (a cartoon style that
glides is right by declaration). A body's own stance point (``origin``,
``ink``, ``box``, a prop's ``base`` on its root drawing) never skates: a
pushed crate or a gliding figure slides on it by right.

>>> SUPPORT.name, SUPPORT.order, SUPPORT.term is None
('support', 252.0, True)
>>> SKATE.name, SKATE.order, SKATE.term is None
('skate', 253.0, True)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from an.genres.registry import CORE_OWNER, check_names, register_check
from an.verify.constraints import (
    AIRBORNE_OVERRIDE,
    Constraint,
    _gravity_of,
    compiled_shot,
)

__all__ = [
    "SUPPORT",
    "SKATE",
    "SUPPORT_CONSTRAINTS",
    "SUPPORT_CHECK_ORDER",
    "SKATE_CHECK_ORDER",
    "SUPPORT_TOLERANCE",
    "SUPPORT_FLOOR_PX",
    "SKATE_TOLERANCE",
    "SKATE_FLOOR_PX",
    "support_findings",
    "skate_findings",
]

#: The tolerances, defined beside the measurement (:mod:`an.stage.support`)
#: and read from here lazily: a core check never loads the stage at import.
_STAGE_NAMES: frozenset[str] = frozenset(
    {"SUPPORT_TOLERANCE", "SUPPORT_FLOOR_PX", "SKATE_TOLERANCE", "SKATE_FLOOR_PX"}
)


def __getattr__(name: str) -> Any:
    if name in _STAGE_NAMES:
        import an.stage.support as measure

        return getattr(measure, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


#: Where the support check runs within a shot: after the joint checks (250),
#: which report broken declarations first, before the hold checks (255).
SUPPORT_CHECK_ORDER: float = 252.0
#: Where the skate check runs: just after the support check, whose broken
#: references it does not repeat.
SKATE_CHECK_ORDER: float = 253.0
#: Two instants closer than this are one.
_SAME_INSTANT_S: float = 1e-9


def _declares_support(shot: Any, stores: Any) -> bool:
    from an.stage.solve import declarations

    return bool(declarations(shot, stores or {}, verbs=False).supports)


def _has_floor(shot: Any) -> bool:
    return shot.solve is not None and shot.solve.ground is not None


def _flying(entity: Any, t: float, duration: float) -> bool:
    """Within the entity's declared flight (``overrides.airborne``)."""
    span = (getattr(entity, "overrides", None) or {}).get(AIRBORNE_OVERRIDE)
    if not isinstance(span, Mapping):
        return False
    start = float(span.get("from", 0.0))
    until = float(span.get("until", duration))
    return start - _SAME_INSTANT_S <= t <= until + _SAME_INSTANT_S


def _surface_text(ref: str, state: Any) -> str:
    if ref == "ground":
        return f"`ground` (y {state.surface[0][1]:g})"
    return f"`{ref}`"


def support_findings(
    states: list[Any],
    *,
    times: list[float],
    shot: Any,
    tolerance: float | None = None,
    floor: float | None = None,
) -> list[tuple[str, str, str]]:
    """``(severity, where, message)`` for each span of frames a support does not
    hold in ``states`` (:func:`an.stage.support.supports_at`'s), the worst
    distance of the span named; ``times`` is the grid the states' frames index.
    A contact is off its surface beyond
    :func:`an.stage.support.support_tolerance`: ``tolerance`` of the entity's
    height (default :data:`SUPPORT_TOLERANCE`), ``floor`` px at least (default
    :data:`SUPPORT_FLOOR_PX`).

    >>> from an.stage.support import ContactState, SupportState
    >>> from types import SimpleNamespace as NS
    >>> def at(k, gap):
    ...     return SupportState("cup", "cup", "joints/0", k, k / 10, ((0.0, 0.0), (1.0, 0.0)),
    ...         "ground", (ContactState("base", "cup", (0.0, -gap), gap),), True, 30.0, "metadata")
    >>> [m[:2] for m in support_findings([at(0, 0.0), at(1, 5.0), at(2, 6.0)],
    ...     times=[0.0, 0.1, 0.2], shot=NS(entities=[], duration=1.0))]
    [('error', 'joints/0')]
    """
    from an.stage.solve import _spans
    from an.stage.support import (
        SUPPORT_FLOOR_PX,
        SUPPORT_TOLERANCE,
        support_tolerance,
    )

    tolerance = SUPPORT_TOLERANCE if tolerance is None else tolerance
    floor = SUPPORT_FLOOR_PX if floor is None else floor

    entities = {e.id: e for e in shot.entities}
    groups: dict[tuple[str, str | None, str], list[Any]] = {}
    for s in states:
        groups.setdefault((s.where, s.joint, s.entity), []).append(s)
    out: list[tuple[str, str, str]] = []
    for (where, joint, eid), series in groups.items():
        judged = [
            s
            for s in series
            if s.joined
            and s.lowest is not None
            and not _flying(entities.get(eid), s.t, float(shot.duration))
        ]
        if not judged:
            continue
        tol = support_tolerance(judged[0].height, tolerance=tolerance, floor=floor)
        by_frame = {s.frame: s for s in judged}
        for kind, broken in (
            ("penetration", [s.frame for s in judged if s.lowest < -tol]),
            ("floating", [s.frame for s in judged if s.lowest > tol]),
        ):
            for a, b in _spans(times, broken):
                span = [by_frame[k] for k in broken if a <= times[k] <= b]
                worst = (min if kind == "penetration" else max)(
                    span, key=lambda s: s.lowest
                )
                out.append(
                    (
                        "error" if joint is not None else "warning",
                        where,
                        _message(kind, worst, a=a, b=b, tol=tol),
                    )
                )
    return out


def _message(kind: str, s: Any, *, a: float, b: float, tol: float) -> str:
    when = (
        f"from {a:.2f} s to {b:.2f} s" if b - a > _SAME_INSTANT_S else f"at {a:.2f} s"
    )
    surface = _surface_text(s.surface_ref, s)
    gap = abs(s.lowest)
    within = f"(the tolerance is {tol:.1f} px)"
    if s.inferred:
        lead = f"`{s.entity}` stands on {surface} as the shot opens, but "
        if kind == "penetration":
            return (
                f"{lead}it is {gap:.1f} px into it {when} {within}. Raise it, or "
                f"declare where it stands (`{{type: support, a: {s.entity}, b: ground}}`)."
            )
        return (
            f"{lead}it is {gap:.1f} px above it {when} {within}, with nothing under it. "
            "Put it back down, or declare its flight "
            "(`overrides: {airborne: {from: …, until: …}}`)."
        )
    box = (
        f" Measured on `{s.entity}`'s box, not its ink: declare "
        "`metadata: {contacts: {base: [u, v]}}` on its descriptor."
        if s.source == "box"
        else ""
    )
    if kind == "penetration":
        contact = s.deepest.name if s.deepest is not None else "contact"
        return (
            f"`{s.entity}`'s `{contact}` is {gap:.1f} px into {surface} {when} {within}. "
            f"Raise `{s.entity}` (its `stage.at` y or the tween on `{s.entity}:y`), or "
            f"lower the floor (`solve: {{ground: …}}`).{box}"
        )
    return (
        f"`{s.entity}` floats {gap:.1f} px above {surface} {when} {within}: nothing it "
        f"stands on reaches it. Put it down (`overrides: {{held_by: {s.surface_ref}}}` "
        f"lays it there), or `unjoin` the support `{s.joint}` while it is off it.{box}"
    )


def check_support(ctx: Any) -> None:
    """Every declared support holds at every joined frame of the compiled shot,
    and every entity taken to stand on the shot's floor stays on it at rest."""
    shot = ctx.shot
    stores = ctx.stores or {}
    declared = _declares_support(shot, stores)
    if not declared and not _has_floor(shot):
        return
    doc = compiled_shot(ctx)
    if doc is None:
        return  # not_compiled says so
    from an.stage.solve import frame_times
    from an.stage.support import supports_at
    from an.verify.vision import FAILURE_SEVERITY

    times = frame_times(shot.duration, fps=doc.meta.fps, step_hz=doc.meta.step_hz)
    try:
        states, problems = supports_at(doc, shot, stores, times=times)
    except Exception as e:  # noqa: BLE001 - said, never passed over as success
        ctx.report.add(
            FAILURE_SEVERITY,
            f"{ctx.path}/joints",
            f"the support check could not measure this shot ({type(e).__name__}: {e}); "
            "its supports were NOT checked.",
        )
        return
    for where, message in problems:
        ctx.report.add("error", f"{ctx.path}/{where}", message)
    if not _has_floor(shot):
        on_ground = sorted(
            {s.entity for s in states if not s.inferred and s.surface_ref == "ground"}
        )
        if on_ground:
            ctx.report.add(
                "info",
                f"{ctx.path}/solve",
                "no floor declared; `ground` is measured against where "
                + ", ".join(f"`{e}`" for e in on_ground)
                + " stands as the shot opens (say `solve: {ground: y}` for a floor).",
            )
    for severity, where, message in support_findings(states, times=times, shot=shot):
        ctx.report.add(severity, f"{ctx.path}/{where}", message)


def skate_findings(
    states: list[Any],
    *,
    times: list[float],
    shot: Any,
    tolerance: float | None = None,
    floor: float | None = None,
) -> list[tuple[str, str, str]]:
    """``(severity, where, message)`` for each span of frames over which a limb's
    contact held on its surface slides along it faster than
    :func:`an.stage.support.skate_tolerance` (``tolerance`` of the entity's
    height per frame, default :data:`SKATE_TOLERANCE`; ``floor`` px per frame
    at least, default :data:`SKATE_FLOOR_PX`), the fastest frame of the span
    named; ``times`` is the grid the states' frames index. A span runs from
    the frame before its first sliding frame to its last.

    >>> from an.stage.support import ContactState, SupportState
    >>> from types import SimpleNamespace as NS
    >>> def at(k, speed):
    ...     foot = ContactState("foot_l", "fig/leg_l", (0.0, 0.0), 0.0, limb=True,
    ...         held=True, tangent_speed=speed)
    ...     return SupportState("fig", "left", "joints/0", k, k / 10, ((0.0, 0.0), (1.0, 0.0)),
    ...         "ground", (foot,), True, 200.0, "metadata")
    >>> [m[:2] for m in skate_findings([at(0, None), at(1, 3.0), at(2, 0.0)],
    ...     times=[0.0, 0.1, 0.2], shot=NS(entities=[], duration=1.0))]
    [('error', 'joints/0')]
    """
    from an.stage.support import SKATE_FLOOR_PX, SKATE_TOLERANCE, skate_tolerance

    tolerance = SKATE_TOLERANCE if tolerance is None else tolerance
    floor = SKATE_FLOOR_PX if floor is None else floor
    entities = {e.id: e for e in shot.entities}
    duration = float(shot.duration)
    groups: dict[tuple[str, str | None, str, str, str], list[tuple[Any, Any]]] = {}
    for s in states:
        for c in s.contacts:
            if c.limb and c.tangent_speed is not None:
                key = (s.where, s.joint, s.entity, c.name, c.part)
                groups.setdefault(key, []).append((s, c))
    out: list[tuple[str, str, str]] = []
    for (where, joint, eid, name, _part), series in groups.items():
        tol = skate_tolerance(series[0][0].height, tolerance=tolerance, floor=floor)
        flying = entities.get(eid)
        sliding = {
            s.frame: (s, c)
            for s, c in series
            if c.tangent_speed > tol
            and not _flying(flying, s.t, duration)
            and not _flying(flying, times[s.frame - 1], duration)
        }
        for first, last in _frame_runs(sliding):
            worst_s, worst_c = max(
                (sliding[k] for k in range(first, last + 1)),
                key=lambda sc: sc[1].tangent_speed,
            )
            out.append(
                (
                    "error" if joint is not None else "warning",
                    where,
                    _skate_message(
                        worst_s,
                        worst_c,
                        a=times[first - 1],
                        b=times[last],
                        tol=tol,
                    ),
                )
            )
    return out


def _frame_runs(frames: Mapping[int, Any]) -> list[tuple[int, int]]:
    """Runs of consecutive frame indices, as ``(first, last)``.

    >>> _frame_runs({3: 0, 4: 0, 7: 0})
    [(3, 4), (7, 7)]
    """
    out: list[tuple[int, int]] = []
    for k in sorted(frames):
        if out and k == out[-1][1] + 1:
            out[-1] = (out[-1][0], k)
        else:
            out.append((k, k))
    return out


def _skate_message(s: Any, c: Any, *, a: float, b: float, tol: float) -> str:
    surface = _surface_text(s.surface_ref, s)
    head = (
        f"`{s.entity}`'s `{c.name}` slides {c.tangent_speed:.1f} px per frame along "
        f"{surface} from {a:.2f} s to {b:.2f} s while it stands on it (foot skate; "
        f"the tolerance is {tol:.1f} px per frame, measured in the surface's own frame)."
    )
    if s.inferred:
        return (
            f"{head} `{s.entity}` stands on it as the shot opens, and the style's "
            f"gravity holds a foot that is down where it is. Plant it (keep "
            f"`{s.entity}:x` still while the foot is down), or lift the foot off "
            "the floor while it moves."
        )
    return (
        f"{head} Plant it (`unjoin` the support `{s.joint}` while the foot swings, "
        f"or keep `{s.entity}:x` still while it is down)."
    )


def check_skate(ctx: Any) -> None:
    """No limb's contact held on its surface slides along it: every declared
    support (an error), and, under a style pack that declares ``gravity``,
    every entity taken to stand on the shot's floor (a warning)."""
    shot = ctx.shot
    stores = ctx.stores or {}
    declared = _declares_support(shot, stores)
    gravity = _gravity_of(ctx) if _has_floor(shot) else None
    if not declared and gravity is None:
        return
    doc = compiled_shot(ctx)
    if doc is None:
        return  # not_compiled says so
    from an.stage.solve import frame_times
    from an.stage.support import supports_at
    from an.verify.vision import FAILURE_SEVERITY

    times = frame_times(shot.duration, fps=doc.meta.fps, step_hz=doc.meta.step_hz)
    try:
        # unresolved references are the support check's errors, not repeated here
        states, _problems = supports_at(
            doc,
            shot,
            stores,
            times=times,
            inferred=gravity is not None,
            rest_only=False,
        )
    except Exception as e:  # noqa: BLE001 - said, never passed over as success
        ctx.report.add(
            FAILURE_SEVERITY,
            f"{ctx.path}/joints",
            f"the skate check could not measure this shot ({type(e).__name__}: {e}); "
            "its supports' feet were NOT checked for skate.",
        )
        return
    for severity, where, message in skate_findings(states, times=times, shot=shot):
        ctx.report.add(severity, f"{ctx.path}/{where}", message)


SUPPORT = Constraint(
    "support",
    check_support,
    order=SUPPORT_CHECK_ORDER,
    term=None,
    description="a body declared to rest on a surface neither sinks into it nor floats above it (catalogue A1, an#519)",
)

SKATE = Constraint(
    "skate",
    check_skate,
    order=SKATE_CHECK_ORDER,
    term=None,
    description="a foot held on its surface does not slide along it, measured in the surface's own frame (catalogue B3, an#519)",
)

#: The support checks, in the order they run.
SUPPORT_CONSTRAINTS: tuple[Constraint, ...] = (SUPPORT, SKATE)


def _register() -> None:
    for constraint in SUPPORT_CONSTRAINTS:
        if constraint.name not in check_names(owner=CORE_OWNER):
            register_check(constraint.semantic_check(), owner=CORE_OWNER)


_register()
