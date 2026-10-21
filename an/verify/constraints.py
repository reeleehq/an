"""Constraints: declarative statements a lint checks and a solver may enforce (an#497).

A constraint says something about the world the shots show that must stay true:
a node does not jump within a shot, two solids do not pass through each other, a
prop meets the body it is drawn on. It is declared once and has up to two faces
(the constraints catalogue, ``misc/docs/constraints_catalogue.md``):

- a **check**: a lint, run by ``an validate`` through the semantic-check registry
  (:class:`an.genres.SemanticCheck`). It reads a
  :class:`an.ir.validate.ValidationContext` and adds findings to ``ctx.report``;
- a **term**, optional: the residual the kinematic layer's solver drives to zero,
  for a constraint that is enforced as well as checked. ``None`` means lint-only,
  and that is the legitimate default rather than a stub: draw order is derived
  from depth and continuity comes from solving each frame from the previous one,
  so neither has a residual.

Every constraint ships as a lint before it is a term, and a term never replaces
the lint: what the solver produces is checked again by the same ``check``.

The one example a genre or a later batch copies (P2's ``joint_violation``):

>>> def joint_check(ctx):
...     "Every joint of ctx.shot holds at every sampled instant, else ctx.report.add(...)."
>>> def joint_term(state):
...     "The solver's residual for one joint: zero when its two bodies meet there."
...     return 0.0
>>> JOINT = Constraint("joint_violation", joint_check, term=joint_term,
...                    description="a joint's two bodies meet at the joint")
>>> check = JOINT.semantic_check()
>>> check.name, check.stage, check.order == DFLT_ORDER, JOINT.term is joint_term
('joint_violation', 'shot', True, True)

A genre registers it like any check (``Genre(checks=(JOINT.semantic_check(),))``);
the core's own are :data:`CONSTRAINTS`, registered when this module is imported
(``an.ir`` imports it, so ``validate_semantic`` always has them, the way the core's
other checks are registered when ``an.ir.validate`` is).

The core's constraints:

- ``continuity`` (an#508, catalogue B1): a node does not jump within a shot
  unless a ``set`` says so, and a value is not held for less than a frame.
  :func:`discontinuities` is the pure function under it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping

from an.genres.registry import (
    CORE_OWNER,
    CheckStage,
    SemanticCheck,
    check_names,
    register_check,
)

__all__ = [
    "Constraint",
    "CONSTRAINTS",
    "CONTINUITY",
    "Discontinuity",
    "ShortHold",
    "compiled_shot",
    "continuity_findings",
    "discontinuities",
    "short_holds",
]

#: Where a constraint's check runs within its stage when it says nothing: after
#: the core's own per-shot checks (targets 90, entity refs 100, dialogue 120 and
#: 130), which report the broken shots these would otherwise trip over.
DFLT_ORDER: float = 200.0


@dataclass(frozen=True)
class Constraint:
    """One constraint: a declarative statement with a ``check`` and, optionally, a ``term``.

    ``check(ctx)`` is SemanticCheck-shaped (it adds findings to ``ctx.report``);
    ``stage``, ``order`` and ``description`` are the registry's. ``term`` is the
    solver residual hook the kinematic layer's ``solve`` pass consumes: a callable
    returning the residual(s), zero when the constraint holds, in the units of the
    constrained quantity. ``None`` is lint-only.

    >>> c = Constraint("holds", lambda ctx: None, stage="finish", order=5.0)
    >>> c.semantic_check().stage, c.term
    ('finish', None)
    """

    name: str
    check: Callable[[Any], None]
    stage: CheckStage = "shot"
    order: float = DFLT_ORDER
    description: str = ""
    term: Callable[..., Any] | None = None

    def semantic_check(self) -> SemanticCheck:
        """The registry's view of this constraint: its ``check``, to register."""
        return SemanticCheck(
            self.name,
            self.check,
            stage=self.stage,
            order=self.order,
            description=self.description,
        )


# -----------------------------------------------------------------------------
# The compiled shot, once per validation
# -----------------------------------------------------------------------------

#: The memo key under which the compiled document of shot ``i`` is kept.
COMPILED_KEY: str = "constraints.compiled"
#: Renderers whose shots the stage compiles (the others are opaque here).
STAGE_RENDERERS: frozenset[str] = frozenset({"stage", "cutout"})


def compiled_shot(ctx: Any) -> Any | None:
    """``ctx.shot`` compiled as ``an render`` compiles it, once per validation.

    The stores validate was given stand in for the mall; the scene's frame rate
    (the render's when ``an validate --fps`` says), resolution, step grid and
    default easing are the ones the render uses, so what is linted is the
    document that is drawn. ``None`` for a shot the stage does not render or
    that does not compile: the checks that own those problems report them, and
    a constraint says nothing about a shot it could not see.
    """

    def build():
        import warnings

        shot, scene = ctx.shot, ctx.scene
        if shot.renderer not in STAGE_RENDERERS:
            return None
        from an.stage.compile import compile_shot

        res = scene.meta.resolution
        step_hz = shot.step_hz if shot.step_hz is not None else scene.meta.step_hz
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # the render's warnings, not validate's
                return compile_shot(
                    shot,
                    mall=ctx.stores,
                    fps=int(round(_fps(ctx))),
                    width=res.width,
                    height=res.height,
                    step_hz=step_hz,
                    default_easing=scene.meta.default_easing,
                )
        except Exception:  # noqa: BLE001 - a shot that cannot compile is reported elsewhere
            return None

    return ctx.cached((COMPILED_KEY, ctx.index), build)


def _fps(ctx: Any) -> float:
    """The frame rate the film is assembled at: ``an validate --fps``, else the scene's."""
    from an.ir.validate import _RENDER_FPS

    return float(ctx.memo.get(_RENDER_FPS) or ctx.scene.meta.fps)


# -----------------------------------------------------------------------------
# continuity (an#508): a node does not jump within a shot unless a set says so
# -----------------------------------------------------------------------------

#: How far a numeric value may differ on the two sides of an instant and still be
#: continuous: float noise and the compiler's rounding, never a visible move.
#: Keyed by property; :data:`DFLT_CONTINUITY_TOLERANCE` for the rest.
CONTINUITY_TOLERANCE: dict[str, float] = {
    "x": 0.5, "y": 0.5, "pivot_x": 0.5, "pivot_y": 0.5,
}  # fmt: skip
DFLT_CONTINUITY_TOLERANCE: float = 1e-3
#: The easing that holds a value until the next keyframe: a ``set``'s, and a
#: stepped tween's. A jump it lands is the author's.
STEP_EASING: str = "step"
#: How far either side of an instant the pose is read (seconds).
SIDE_S: float = 1e-6
#: Instants closer than this are one instant (seconds).
SAME_INSTANT_S: float = 1e-9


@dataclass(frozen=True)
class Discontinuity:
    """A numeric channel of ``target`` that jumps at ``at`` (seconds into the shot)."""

    target: str
    property: str
    at: float
    before: float
    after: float
    #: ``start``: an action begins there from a value the node is not at;
    #: ``end``: the action governing the value ends there and another one, running
    #: underneath, takes over; ``loop``: a looping clip restarts there.
    cause: str
    #: A ``set`` (a step-held value equal to what shows) explains it: the author's.
    deliberate: bool


@dataclass(frozen=True)
class ShortHold:
    """A step-held value of ``target``'s ``property`` shown for less than a frame."""

    target: str
    property: str
    at: float
    value: float
    held_s: float


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric_channels(clip: Any) -> list[Any]:
    """The channels of ``clip`` whose every keyframe is a number (a transform, a
    tint component), not a swap key or text."""
    return [
        ch for ch in clip.channels if all(_is_number(k.value) for k in ch.keyframes)
    ]


def _instants(timeline: Any, duration: float) -> list[float]:
    """Where a numeric value can jump: a clip's start, its end, and each restart
    of a looping clip. Never a keyframe inside a clip: between two keyframes the
    curve reaches the next value, and a step-eased keyframe lands a jump the
    author wrote (a ``set``, a stepped tween). Never ``0``: the shot's first
    frame has no previous one (``cut_continuity`` owns the cut)."""
    from an.timing.clip import LoopMode

    out: set[float] = set()

    def add(t: float) -> None:
        if SAME_INSTANT_S < t <= duration + SAME_INSTANT_S:
            out.add(round(min(t, duration), 9))

    for track in timeline.tracks:
        for placed in track.clips:
            if not _numeric_channels(placed.clip):
                continue
            add(placed.start_time)
            add(placed.end_time)
            if placed.clip.loop_mode is LoopMode.LOOP:
                period = placed.clip.duration / placed.speed
                k = 1
                while placed.start_time + k * period < placed.end_time - SAME_INSTANT_S:
                    add(placed.start_time + k * period)
                    k += 1
    return sorted(out)


def _active(timeline: Any, key: tuple[str, str], t: float) -> Iterator[tuple[Any, Any]]:
    """``(placed clip, channel)`` of every clip writing ``key`` at ``t``, in the
    order the evaluator reads them (later wins)."""
    for track in timeline.tracks:
        for placed in track.clips:
            if placed.start_time <= t <= placed.end_time:
                for ch in placed.clip.channels:
                    if (ch.target, ch.property) == key:
                        yield placed, ch


def _local_time(placed: Any, t: float) -> float:
    from an.timing.clip import _wrap_time

    return _wrap_time(
        (t - placed.start_time) * placed.speed,
        placed.clip.duration,
        placed.clip.loop_mode,
    )


def _in_force_easing(channel: Any, local: float) -> Any:
    """The easing of the segment ``local`` lies in: the last keyframe's at or
    before it (``None`` before the first)."""
    easing = None
    for kf in channel.keyframes:
        if kf.time <= local + SAME_INSTANT_S:
            easing = kf.easing
        else:
            break
    return easing


def _value_of(placed: Any, key: tuple[str, str], t: float) -> float | None:
    from an.timing.clip import evaluate

    return evaluate(placed.clip, _local_time(placed, t)).get(key)


def _tolerance(prop: str) -> float:
    return CONTINUITY_TOLERANCE.get(prop, DFLT_CONTINUITY_TOLERANCE)


def _deliberate(timeline: Any, key: tuple[str, str], t: float, shown: float) -> bool:
    """A ``set`` explains what shows at ``t``: some clip writing ``key`` at ``t``
    holds a step-eased value there, and that value is the one shown. A hold
    running underneath a tween that jumps to something else explains nothing."""
    for placed, ch in _active(timeline, key, t):
        if _in_force_easing(ch, _local_time(placed, t)) != STEP_EASING:
            continue
        value = _value_of(placed, key, t)
        if value is not None and abs(value - shown) <= _tolerance(key[1]):
            return True
    return False


def _cause(timeline: Any, key: tuple[str, str], t: float, after_side: float) -> str:
    """Why the value changes across ``t``, read off the clips active after it."""
    from an.timing.clip import LoopMode

    governing = None
    for placed, _ch in _active(timeline, key, after_side):
        governing = placed
    if governing is None:
        return "end"
    if abs(governing.start_time - t) <= SIDE_S:
        return "start"
    if governing.clip.loop_mode is LoopMode.LOOP and abs(
        _local_time(governing, after_side)
    ) <= SIDE_S * governing.speed + SAME_INSTANT_S:
        return "loop"
    return "end"


def discontinuities(
    timeline: Any, *, rest: Mapping[tuple[str, str], float], duration: float
) -> list[Discontinuity]:
    """Every instant in ``(0, duration]`` where a numeric value of ``timeline``
    jumps: the pose read just before the instant and just after it differ
    beyond :data:`CONTINUITY_TOLERANCE`. ``rest`` is each ``(target, property)``'s
    value while nothing writes it (the node's own transform); a key absent from
    both the pose and ``rest`` is not judged.

    A tween with a ``from`` the node is not at jumps where it starts; two tweens
    on one property jump where the later one starts and again where it ends and
    the earlier one shows through; a loop whose last pose is not its first jumps
    at each restart. A ``set`` is a jump the author wrote: it is reported with
    ``deliberate=True``, for the caller to leave alone.

    >>> from an.timing.channel import Channel, Keyframe
    >>> from an.timing.clip import Clip
    >>> from an.timing.timeline import PlacedClip, Timeline, Track
    >>> rise = Clip("rise", 1.0, [Channel("a", "y", [Keyframe(0.0, 3.0, "linear"), Keyframe(1.0, 10.0)])])
    >>> tl = Timeline(2.0, [Track("a", [PlacedClip(rise, start_time=0.5)])])
    >>> (d,) = discontinuities(tl, rest={("a", "y"): 0.0}, duration=2.0)
    >>> d.at, d.before, d.after, d.cause, d.deliberate
    (0.5, 0.0, 3.0, 'start', False)
    >>> hold = Clip("hold", 1.5, [Channel("a", "y", [Keyframe(0.0, 3.0, "step")])])
    >>> tl = Timeline(2.0, [Track("a", [PlacedClip(hold, start_time=0.5), PlacedClip(rise, start_time=0.5)])])
    >>> discontinuities(tl, rest={("a", "y"): 0.0}, duration=2.0)[0].deliberate
    True
    """
    from an.timing.timeline import evaluate_timeline

    out: list[Discontinuity] = []
    for t in _instants(timeline, duration):
        before_side = max(0.0, t - SIDE_S)
        after_side = min(duration, t + SIDE_S)
        poses = [evaluate_timeline(timeline, s) for s in (before_side, t, after_side)]
        keys = {k for pose in poses for k in pose} | {
            k for k in rest if any(k in pose for pose in poses)
        }
        for key in sorted(keys):
            values = [pose.get(key, rest.get(key)) for pose in poses]
            if not all(_is_number(v) for v in values):
                continue
            tol = _tolerance(key[1])
            for lo, hi, side in ((0, 1, t), (1, 2, after_side)):
                a, b = values[lo], values[hi]
                if abs(b - a) <= tol:
                    continue
                out.append(
                    Discontinuity(
                        key[0],
                        key[1],
                        t,
                        float(a),
                        float(b),
                        _cause(timeline, key, t, side),
                        _deliberate(timeline, key, side, float(b)),
                    )
                )
                break  # one jump per key per instant
    return out


def short_holds(timeline: Any, *, fps: float) -> list[ShortHold]:
    """Step-held values shown for less than a frame: two ``set``s of one property
    closer than ``1/fps``, so the first may never land on a frame.

    >>> from an.timing.channel import Channel, Keyframe
    >>> from an.timing.clip import Clip
    >>> from an.timing.timeline import PlacedClip, Timeline, Track
    >>> sets = Clip("sets", 1.0, [Channel("a", "x", [Keyframe(0.0, 5.0, "step"), Keyframe(0.01, 0.0, "step")])])
    >>> tl = Timeline(2.0, [Track("a", [PlacedClip(sets, start_time=0.5)])])
    >>> [(h.at, h.value, round(h.held_s, 3)) for h in short_holds(tl, fps=24)]
    [(0.5, 5.0, 0.01)]
    """
    frame = 1.0 / float(fps)
    out: list[ShortHold] = []
    for track in timeline.tracks:
        for placed in track.clips:
            for ch in _numeric_channels(placed.clip):
                kfs = ch.keyframes
                for k in range(len(kfs) - 1):
                    held = (kfs[k + 1].time - kfs[k].time) / placed.speed
                    if (
                        kfs[k].easing == STEP_EASING
                        and held < frame - SAME_INSTANT_S
                        and abs(kfs[k + 1].value - kfs[k].value) > _tolerance(ch.property)
                    ):
                        out.append(
                            ShortHold(
                                ch.target,
                                ch.property,
                                placed.start_time + kfs[k].time / placed.speed,
                                float(kfs[k].value),
                                held,
                            )
                        )
    return out


def _rest_values(doc: Any) -> dict[tuple[str, str], float]:
    """Every node's transform as ``{(path, property): value}``: what a property
    shows while no clip writes it."""
    from an.stage.tree import walk_document

    out: dict[tuple[str, str], float] = {}
    # The layer roots themselves (the camera moves `root`), then every indexed node.
    roots = [
        (layer.name, layer)
        for layer in (getattr(doc, "scene", None), getattr(doc, "overlay", None))
        if layer is not None
    ]
    for path, node in [*roots, *walk_document(doc)]:
        transform = getattr(node, "transform", None)
        if transform is None:
            continue
        for prop, value in transform.model_dump().items():
            if _is_number(value):
                out[(path, prop)] = float(value)
    return out


def _frame(t: float, fps: float) -> int:
    return int(math.floor(t * fps + SAME_INSTANT_S))


def continuity_findings(
    doc: Any, *, duration: float, fps: float, path: str = ""
) -> list[tuple[str, str, str]]:
    """``[(severity, ir path, message)]`` for a compiled shot's jumps and short holds."""
    from an.stage.timeline import timeline_from_scene

    timeline = timeline_from_scene(doc)
    where = f"{path}/actions" if path else "actions"
    out: list[tuple[str, str, str]] = []
    for d in discontinuities(timeline, rest=_rest_values(doc), duration=duration):
        if d.deliberate:
            continue
        head = (
            f"{d.target!r} {d.property} jumps at {d.at:.3f} s (frame {_frame(d.at, fps)}) "
            f"from {d.before:g} to {d.after:g}: "
        )
        if d.cause == "start":
            why = (
                "the action starting there begins from a value the node is not at. "
                "A tween with no `from` starts where the node is; to jump on purpose, "
                f"`set` {d.property} on {d.target!r} to {d.after:g} at {d.at:g}."
            )
        elif d.cause == "loop":
            why = (
                "a loop restarts there and its first pose is not its last. Make the "
                "loop end where it starts, or cut it with a `set`."
            )
        else:
            why = (
                f"the action governing {d.property} ends there and another one running "
                "underneath shows through. End the other action first, or give it the "
                "value this one ends with."
            )
        out.append(("warning", where, head + why))
    for h in short_holds(timeline, fps=fps):
        out.append(
            (
                "warning",
                where,
                f"{h.target!r} {h.property} holds {h.value:g} for only {h.held_s * 1000:.0f} ms "
                f"from {h.at:.3f} s, less than a frame at {fps:g} fps: it may never show. "
                "Hold it for a frame, or drop one of the two changes.",
            )
        )
    return out


def check_continuity(ctx: Any) -> None:
    """The core's ``continuity`` check (an#508) over the compiled shot."""
    doc = compiled_shot(ctx)
    if doc is None:
        return
    for severity, where, message in continuity_findings(
        doc, duration=float(ctx.shot.duration), fps=_fps(ctx), path=ctx.path
    ):
        ctx.report.add(severity, where, message)


CONTINUITY = Constraint(
    "continuity",
    check_continuity,
    description="a node does not jump within a shot unless a set says so (an#508)",
)

#: The core's constraints, in the order their checks run within a stage.
CONSTRAINTS: tuple[Constraint, ...] = (CONTINUITY,)


def _register(constraints: tuple[Constraint, ...] = CONSTRAINTS) -> None:
    """Register the core's constraint checks once (the core's other checks are
    registered the same way when ``an.ir.validate`` loads)."""
    for constraint in constraints:
        if constraint.name not in check_names(owner=CORE_OWNER):
            register_check(constraint.semantic_check(), owner=CORE_OWNER)


_register()
