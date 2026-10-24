"""The joint checks: what ``an validate`` says about a shot's joints (ADR 0008, an#512).

Three constraints on the one interface (:class:`an.verify.constraints.Constraint`),
each a lint over the compiled shot whose ``term`` is the solver's residual
(:func:`an.stage.solve.joint_residuals`, the same measure the ``solve`` pass
drives to zero):

- ``unknown_body`` (error): a joint or a verb names a body, a point or a joint
  the shot does not have;
- ``unreachable_pin`` (error): a ``pin`` the joints cannot meet, with how far
  the chain reaches and where in reach to put the target;
- ``joint_violation`` (warning): a joined joint that does not hold in the
  compiled output (authored motion pulled it apart, or a hinge is bent past
  its range), with the time and the two bodies; a rejoin that closes more
  than :data:`REJOIN_TOLERANCE_PX` in one frame (below that it reads as a
  blend); and, as ``info``, the authored spans a solved channel replaces.

All three are silent for a shot that declares no joint and no verb, and they
run after the constraint catalogue's lints (order :data:`JOINT_CHECK_ORDER`).

>>> [c.name for c in JOINT_CONSTRAINTS]
['unknown_body', 'unreachable_pin', 'joint_violation']
"""

from __future__ import annotations

from typing import Any

from an.genres.registry import CORE_OWNER, check_names, register_check
from an.verify.constraints import Constraint

__all__ = [
    "JOINT_CONSTRAINTS",
    "UNKNOWN_BODY",
    "UNREACHABLE_PIN",
    "JOINT_VIOLATION",
    "JOINT_TOLERANCE_PX",
    "REJOIN_TOLERANCE_PX",
]

#: Where the joint checks run within a shot: after the catalogue's lints (200).
JOINT_CHECK_ORDER: float = 250.0
#: How far apart a joint's two points may be in the compiled output (px): the
#: solver's own tolerance (:data:`an.kinematics.solver.DFLT_TOLERANCE`).
JOINT_TOLERANCE_PX: float = 0.25
#: How far past its range a hinge may read (degrees): float noise, not a pose.
LIMIT_TOLERANCE_DEG: float = 0.1
#: A rejoin closing a gap wider than this in one frame is a visible snap (owner
#: decision 9 on an#497: a lint at 2 px, a blend below it).
REJOIN_TOLERANCE_PX: float = 2.0

#: The memo key of the shot compiled for the joint checks.
_COMPILED_KEY = "joints.compiled"


def _declares(ctx: Any) -> bool:
    from an.stage.solve import shot_declares_solve

    return shot_declares_solve(ctx.shot, ctx.stores or {})


def _compiled(ctx: Any) -> tuple[Any, Exception | None]:
    """``ctx.shot`` compiled as ``an render`` compiles it (its style pack
    included, whose gravity the solve reads), once per validation: ``(doc,
    None)``, or ``(None, the error)``."""

    def build():
        import warnings

        from an.stage.compile import compile_shot, style_pack_for
        from an.verify.constraints import STAGE_RENDERERS, _fps

        shot, scene = ctx.shot, ctx.scene
        if shot.renderer not in STAGE_RENDERERS:
            return None, None
        try:
            pack = style_pack_for(scene.meta, (ctx.stores or {}).get("styles") or {})
        except Exception:  # noqa: BLE001 - a broken pack is the style check's to report
            pack = None
        res = scene.meta.resolution
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                doc = compile_shot(
                    shot,
                    mall=ctx.stores,
                    fps=int(round(_fps(ctx))),
                    width=res.width,
                    height=res.height,
                    step_hz=shot.step_hz
                    if shot.step_hz is not None
                    else scene.meta.step_hz,
                    default_easing=scene.meta.default_easing,
                    style_pack=pack,
                )
        except Exception as e:  # noqa: BLE001 - reported by the check that owns it
            return None, e
        return doc, None

    return ctx.cached((_COMPILED_KEY, ctx.index), build)


def _report(doc: Any) -> dict[str, Any]:
    from an.stage.solve import SOLVE_EXTENSION

    return (doc.meta.extensions or {}).get(SOLVE_EXTENSION) or {}


# -----------------------------------------------------------------------------
# unknown_body
# -----------------------------------------------------------------------------


def check_unknown_body(ctx: Any) -> None:
    """Every body, point and joint a declaration names is in the shot."""
    if not _declares(ctx):
        return
    from an.stage.solve import UnknownBodyError

    _doc, error = _compiled(ctx)
    if isinstance(error, UnknownBodyError):
        for where, message in error.problems:
            ctx.report.add("error", f"{ctx.path}/{where}", message)


UNKNOWN_BODY = Constraint(
    "unknown_body",
    check_unknown_body,
    order=JOINT_CHECK_ORDER,
    description="a joint or a verb names a body, a point or a joint the shot has (ADR 0008)",
)


# -----------------------------------------------------------------------------
# unreachable_pin
# -----------------------------------------------------------------------------


def check_unreachable_pin(ctx: Any) -> None:
    """A ``pin`` the joints can meet: else where the chain reaches, and where to put it."""
    if not _declares(ctx):
        return
    doc, _error = _compiled(ctx)
    if doc is None:
        return
    report = _report(doc)
    joints = report.get("joints") or []
    for entry in report.get("dropped") or []:
        row = joints[entry["joint"]] if entry["joint"] < len(joints) else {}
        if row.get("source") != "pin":
            continue
        reach = entry.get("reach")
        if reach and reach.get("within"):
            how = (
                f"it is within reach ({reach['distance']:.0f} px from {reach['from']!r}, the "
                f"chain reaches {reach['reach']:.0f} px), but the joints or an authored "
                "channel hold the chain away from it. Let the solve move the parts in "
                "between (drop the channel that fights it), or widen a hinge's `limits`."
            )
        elif reach:
            how = (
                f"it is {reach['distance']:.0f} px from {reach['from']!r}, and the chain "
                f"reaches {reach['reach']:.0f} px. Move the target within reach (on the "
                f"line toward it: ({reach['place'][0]:g}, {reach['place'][1]:g}) in "
                "stage px), or pin it from a body that is closer."
            )
        else:
            how = "nothing holds the chain it is on, or the joints conflict with it."
        ctx.report.add(
            "error",
            f"{ctx.path}/{row.get('where', 'actions')}",
            f"pin {row.get('bodies')} cannot be held from {entry['from']:.2f} s to "
            f"{entry['until']:.2f} s (it stays {entry['gap']:.1f} px short): {how}",
        )


def joint_term(doc: Any, shot: Any, mall: Any) -> Any:
    """The joint constraints' term: every joint's residual at every frame of a
    compiled shot (px), the quantity the ``solve`` pass drives to zero
    (:func:`an.stage.solve.joint_residuals`)."""
    from an.stage.solve import joint_residuals

    return joint_residuals(doc, shot, mall)


UNREACHABLE_PIN = Constraint(
    "unreachable_pin",
    check_unreachable_pin,
    order=JOINT_CHECK_ORDER,
    term=joint_term,
    description="a pin is within reach of the joints that hold the body it moves (ADR 0008)",
)


# -----------------------------------------------------------------------------
# joint_violation
# -----------------------------------------------------------------------------


def check_joint_violation(ctx: Any) -> None:
    """Every joined joint holds at every frame of the compiled shot."""
    if not _declares(ctx):
        return
    doc, _error = _compiled(ctx)
    if doc is None:
        return
    import math

    from an.stage.solve import _spans, joint_residuals

    report = _report(doc)
    joints = report.get("joints") or []
    try:
        puppet, times, gaps, excess = joint_residuals(doc, ctx.shot, ctx.stores or {})
    except Exception:  # noqa: BLE001 - unknown_body reports a broken declaration
        return
    # A refused pin is unreachable_pin's to report, with its reach.
    refused = [
        (e["joint"], e["from"], e["until"])
        for e in report.get("dropped") or []
        if e["joint"] < len(joints) and joints[e["joint"]].get("source") == "pin"
    ]
    refused_frames = {
        (j, k)
        for j, a, b in refused
        for k, t in enumerate(times)
        if a - 0.005 <= t <= b + 0.005
    }
    for j, row in enumerate(puppet.rows):
        broken = [
            k
            for k in range(len(times))
            if gaps[k][j] > JOINT_TOLERANCE_PX and (j, k) not in refused_frames
        ]
        for a, b in _spans(times, broken):
            worst = max(gaps[k][j] for k in broken if a <= times[k] <= b)
            ctx.report.add(
                "warning",
                f"{ctx.path}/{row.where}",
                f"joint {row.id!r} ({row.label}) does not hold from {a:.2f} s to {b:.2f} s: "
                f"up to {worst:.1f} px apart. Authored motion pulls it apart: let the solve "
                "move one of the two bodies (drop the channel that fights it), or `unjoin` "
                "it for the span.",
            )
        bent = [
            k
            for k in range(len(times))
            if math.degrees(excess[k][j]) > LIMIT_TOLERANCE_DEG
        ]
        for a, b in _spans(times, bent):
            worst = max(math.degrees(excess[k][j]) for k in bent if a <= times[k] <= b)
            ctx.report.add(
                "warning",
                f"{ctx.path}/{row.where}",
                f"joint {row.id!r} ({row.label}) is bent {worst:.1f}° past its range from "
                f"{a:.2f} s to {b:.2f} s. An authored rotation forces it: widen the "
                "`limits`, or let the solve turn it.",
            )
    for snap in report.get("snaps") or []:
        if snap["gap"] > REJOIN_TOLERANCE_PX:
            row = joints[snap["joint"]] if snap["joint"] < len(joints) else {}
            ctx.report.add(
                "warning",
                f"{ctx.path}/{row.get('where', 'actions')}",
                f"joint {row.get('id')!r} ({row.get('bodies')}) is rejoined at {snap['at']:.2f} s "
                f"{snap['gap']:.1f} px apart: it snaps shut in one frame. Bring the two "
                f"bodies within {REJOIN_TOLERANCE_PX:g} px before the `join`.",
            )
    for span in report.get("overridden") or []:
        ctx.report.add(
            "info",
            f"{ctx.path}/actions",
            f"the solve replaces the authored {span['target']}:{span['property']} from "
            f"{span['from']:.2f} s to {span['until']:.2f} s (a joint moves it there).",
        )


JOINT_VIOLATION = Constraint(
    "joint_violation",
    check_joint_violation,
    order=JOINT_CHECK_ORDER,
    term=joint_term,
    description="a joined joint holds at every frame of the compiled shot (ADR 0008)",
)


#: The joint checks, in the order they run.
JOINT_CONSTRAINTS: tuple[Constraint, ...] = (
    UNKNOWN_BODY,
    UNREACHABLE_PIN,
    JOINT_VIOLATION,
)


def _register() -> None:
    for constraint in JOINT_CONSTRAINTS:
        if constraint.name not in check_names(owner=CORE_OWNER):
            register_check(constraint.semantic_check(), owner=CORE_OWNER)


_register()
