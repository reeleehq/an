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

``skate`` (order 253, catalogue B3 i): a limb's contact (one whose node is not
the entity's own nor one of its root parts: a foot on a leg hinged to the
body) **held** on its surface (its support joined, within the support
tolerance) is foot skate when, between two instants of the grid at which it
is held, its foot slides along the surface faster than
:func:`an.stage.support.skate_tolerance` (a fraction of the entity's height
per SECOND, so one slide gets one verdict at 24 or 60 fps), or when, over one
stance, it drifts from where it was planted by more than
:func:`an.stage.support.skate_drift_tolerance` (a slow skate adds up). A step
on a ``step_hz`` grid is reported per step, not per frame. A step whose foot
moves along the surface's normal by more than
:data:`an.stage.support.SKATE_LIFT` of its slide is a lift-off or a landing,
not measured. The slide is measured in the surface's own frame (a body's
surface: in the body's own units from its first end, so a figure standing on
a pushed or mirrored crate does not skate; the floor: from the stage's
origin). An error for a declared support; for an entity taken to stand on
the floor, a warning, and only under a style pack that declares ``gravity``
(a cartoon style that glides is right by declaration). A body's own stance
point (``origin``, the ink of its roots, a prop's ``base``, a bone on a root
part) never skates: a pushed crate or a gliding figure slides on it by right.
In a shot a world frames, a member whose frame moves relative to the
viewpoint's is not judged on ``ground`` (the stage floor does not stay under
it; ``World.ground``, an#519 PR 4, measures it): said once as ``info``.

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
    compiled_shot,
    gravity_of,
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
    "SKATE_DRIFT_TOLERANCE",
    "SKATE_DRIFT_FLOOR_PX",
    "support_findings",
    "skate_findings",
]

#: The tolerances, defined beside the measurement (:mod:`an.stage.support`)
#: and read from here lazily: a core check never loads the stage at import.
_STAGE_NAMES: frozenset[str] = frozenset(
    {
        "SUPPORT_TOLERANCE",
        "SUPPORT_FLOOR_PX",
        "SKATE_TOLERANCE",
        "SKATE_FLOOR_PX",
        "SKATE_DRIFT_TOLERANCE",
        "SKATE_DRIFT_FLOOR_PX",
    }
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
    step_hz: float | None = None,
    tolerance: float | None = None,
    floor: float | None = None,
    drift: float | None = None,
    drift_floor: float | None = None,
) -> list[tuple[str, str, str]]:
    """``(severity, where, message)`` for each span over which a limb's contact
    held on its surface slides along it faster than
    :func:`an.stage.support.skate_tolerance` (``tolerance`` of the entity's
    height per second, default :data:`SKATE_TOLERANCE`; ``floor`` px/s at
    least, default :data:`SKATE_FLOOR_PX`), the fastest step of the span named;
    and for each stance (a run of held steps) with no such span over which it
    drifts from where it was planted by more than
    :func:`an.stage.support.skate_drift_tolerance` (``drift`` of the height,
    default :data:`SKATE_DRIFT_TOLERANCE`; ``drift_floor`` px at least, default
    :data:`SKATE_DRIFT_FLOOR_PX`). ``times`` is the grid the states' frames
    index; ``step_hz`` says it is a step grid, so a step is reported as one
    (a pop on twos is not half of it per frame).

    >>> from an.stage.support import ContactState, SupportState
    >>> from types import SimpleNamespace as NS
    >>> def at(k, slid):
    ...     foot = ContactState("foot_l", "fig/leg_l", (0.0, 0.0), 0.0, limb=True, slid=slid)
    ...     return SupportState("fig", "left", "joints/0", k, k / 10, ((0.0, 0.0), (1.0, 0.0)),
    ...         "ground", (foot,), True, 200.0, "metadata")
    >>> [m[:2] for m in skate_findings([at(0, None), at(1, 3.0), at(2, 0.0)],
    ...     times=[0.0, 0.1, 0.2], shot=NS(entities=[], duration=1.0))]
    [('error', 'joints/0')]
    >>> [(sev, m.split(" along ")[0]) for sev, _w, m in skate_findings(
    ...     [at(k, 0.5 if k else None) for k in range(20)],
    ...     times=[k / 10 for k in range(20)], shot=NS(entities=[], duration=2.0))]
    [('error', "`fig`'s `foot_l` drifts 9.5 px")]
    """
    from an.stage.support import (
        SKATE_DRIFT_FLOOR_PX,
        SKATE_DRIFT_TOLERANCE,
        SKATE_FLOOR_PX,
        SKATE_TOLERANCE,
        skate_drift_tolerance,
        skate_tolerance,
    )

    tolerance = SKATE_TOLERANCE if tolerance is None else tolerance
    floor = SKATE_FLOOR_PX if floor is None else floor
    drift = SKATE_DRIFT_TOLERANCE if drift is None else drift
    drift_floor = SKATE_DRIFT_FLOOR_PX if drift_floor is None else drift_floor
    entities = {e.id: e for e in shot.entities}
    duration = float(shot.duration)
    groups: dict[tuple[str, str | None, str, str, str], list[tuple[Any, Any]]] = {}
    for s in states:
        for c in s.contacts:
            if c.limb and c.slid is not None:
                key = (s.where, s.joint, s.entity, c.name, c.part)
                groups.setdefault(key, []).append((s, c))
    out: list[tuple[str, str, str]] = []
    for (where, joint, eid, _name, _part), series in groups.items():
        height = series[0][0].height
        speed_tol = skate_tolerance(height, tolerance=tolerance, floor=floor)
        drift_tol = skate_drift_tolerance(height, tolerance=drift, floor=drift_floor)
        flying = entities.get(eid)
        steps = {
            s.frame: (s, c)
            for s, c in series
            if not _flying(flying, s.t, duration)
            and not _flying(flying, times[s.frame - 1], duration)
        }
        severity = "error" if joint is not None else "warning"
        speed = {
            k: abs(c.slid) / (times[k] - times[k - 1]) for k, (_s, c) in steps.items()
        }
        for first, last in _frame_runs(steps):  # one stance: held from first - 1
            stance = range(first, last + 1)
            fast = {k: steps[k] for k in stance if speed[k] > speed_tol}
            for a, b in _frame_runs(fast):
                worst = max(range(a, b + 1), key=speed.__getitem__)
                s, c = steps[worst]
                out.append(
                    (
                        severity,
                        where,
                        _skate_message(
                            s,
                            c,
                            what=_slides(abs(c.slid), speed[worst], step_hz),
                            a=times[a - 1],
                            b=times[b],
                            within=f"the tolerance is {speed_tol:.0f} px/s",
                        ),
                    )
                )
            if fast:
                continue
            total, farthest, at_k = 0.0, 0.0, first
            for k in stance:
                total += steps[k][1].slid
                if abs(total) > farthest:
                    farthest, at_k = abs(total), k
            if farthest > drift_tol:
                s, c = steps[at_k]
                out.append(
                    (
                        severity,
                        where,
                        _skate_message(
                            s,
                            c,
                            what=f"drifts {farthest:.1f} px",
                            a=times[first - 1],
                            b=times[at_k],
                            within=(
                                f"each step is under {speed_tol:.0f} px/s, but a "
                                f"planted foot may drift {drift_tol:.1f} px in all"
                            ),
                        ),
                    )
                )
    return out


def _slides(px: float, speed: float, step_hz: float | None) -> str:
    """The slide of one step, per frame or per step of a ``step_hz`` grid.

    >>> _slides(5.0, 60.0, 12.0), _slides(2.5, 60.0, None)
    ('slides 5.0 px per step (60 px/s)', 'slides 2.5 px per frame (60 px/s)')
    """
    unit = "step" if step_hz else "frame"
    return f"slides {px:.1f} px per {unit} ({speed:.0f} px/s)"


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


def _skate_message(
    s: Any, c: Any, *, what: str, a: float, b: float, within: str
) -> str:
    surface = _surface_text(s.surface_ref, s)
    head = (
        f"`{s.entity}`'s `{c.name}` {what} along {surface} from {a:.2f} s to "
        f"{b:.2f} s while it stands on it (foot skate; {within}, measured in the "
        "surface's own frame)."
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


def _moving_frames(ctx: Any) -> frozenset[str]:
    """The members a world carries in a frame that moves relative to the shot's
    viewpoint (:func:`an.ir.world.frame_moving_members`); none for a shot no
    world frames, or one whose world does not lower (the world check says so)."""
    from an.ir.world import frame_moving_members

    if (
        ctx.index is None
        or getattr(ctx.scene.timeline[ctx.index], "viewpoint", None) is None
    ):
        return frozenset()
    try:
        return frame_moving_members(ctx.scene, ctx.index)
    except Exception:  # noqa: BLE001 - a world that does not lower is the world check's error
        return frozenset()


def check_skate(ctx: Any) -> None:
    """No limb's contact held on its surface slides along it: every declared
    support (an error), and, under a style pack that declares ``gravity``,
    every entity taken to stand on the shot's floor (a warning)."""
    shot = ctx.shot
    stores = ctx.stores or {}
    declared = _declares_support(shot, stores)
    gravity = gravity_of(ctx) if _has_floor(shot) else None
    if not declared and gravity is None:
        return
    doc = compiled_shot(ctx)
    if doc is None:
        return  # not_compiled says so
    from an.ir.schema import GROUND_SURFACE
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
    moving = _moving_frames(ctx)
    gated = {
        (s.where, s.entity)
        for s in states
        if s.surface_ref == GROUND_SURFACE
        and s.entity in moving
        and any(c.limb for c in s.contacts)
    }
    for where, eid in sorted(gated):
        ctx.report.add(
            "info",
            f"{ctx.path}/{where}",
            f"`{eid}`'s feet are not checked for skate on `ground`: the world carries "
            "it in a frame that moves relative to the viewpoint, so the stage's floor "
            "does not stay under it (`World.ground`, an#519 PR 4, will measure it "
            "in its own frame).",
        )
    states = [s for s in states if (s.where, s.entity) not in gated]
    for severity, where, message in skate_findings(
        states, times=times, shot=shot, step_hz=doc.meta.step_hz
    ):
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
