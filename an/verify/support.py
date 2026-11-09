"""The ``support`` check: a body declared to rest on a surface does (an#519, catalogue A1).

One constraint on the one interface (:class:`an.verify.constraints.Constraint`),
lint-only (no solver term in v1), over the compiled shot, measured by the pure
function :func:`an.stage.support.supports_at`:

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

>>> SUPPORT.name, SUPPORT.order, SUPPORT.term is None
('support', 252.0, True)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from an.genres.registry import CORE_OWNER, check_names, register_check
from an.verify.constraints import AIRBORNE_OVERRIDE, Constraint, compiled_shot

__all__ = [
    "SUPPORT",
    "SUPPORT_CONSTRAINTS",
    "SUPPORT_CHECK_ORDER",
    "SUPPORT_TOLERANCE",
    "SUPPORT_FLOOR_PX",
    "FLOAT_BAND",
    "support_findings",
]

#: The tolerances, defined beside the measurement (:mod:`an.stage.support`)
#: and read from here lazily: a core check never loads the stage at import.
_STAGE_NAMES: frozenset[str] = frozenset(
    {"SUPPORT_TOLERANCE", "SUPPORT_FLOOR_PX", "FLOAT_BAND"}
)


def __getattr__(name: str) -> Any:
    if name in _STAGE_NAMES:
        import an.stage.support as measure

        return getattr(measure, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


#: Where the support check runs within a shot: after the joint checks (250),
#: which report broken declarations first, before the hold checks (255).
SUPPORT_CHECK_ORDER: float = 252.0
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
    states: list[Any], *, times: list[float], shot: Any
) -> list[tuple[str, str, str]]:
    """``(severity, where, message)`` for each span of frames a support does not
    hold in ``states`` (:func:`an.stage.support.supports_at`'s), the worst
    distance of the span named; ``times`` is the grid the states' frames index.

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
    from an.stage.support import support_tolerance

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
        tol = support_tolerance(judged[0].height)
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


SUPPORT = Constraint(
    "support",
    check_support,
    order=SUPPORT_CHECK_ORDER,
    term=None,
    description="a body declared to rest on a surface neither sinks into it nor floats above it (catalogue A1, an#519)",
)

#: The support checks, in the order they run.
SUPPORT_CONSTRAINTS: tuple[Constraint, ...] = (SUPPORT,)


def _register() -> None:
    for constraint in SUPPORT_CONSTRAINTS:
        if constraint.name not in check_names(owner=CORE_OWNER):
            register_check(constraint.semantic_check(), owner=CORE_OWNER)


_register()
