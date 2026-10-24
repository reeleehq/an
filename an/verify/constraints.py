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
- ``solidity`` (an#509, catalogue A2): two solids (characters and props) whose
  boxes overlap, with no ``stage.after`` between them, are drawn through each
  other. :func:`solid_overlaps` is the pure function under it.
- ``draw_order`` (an#510, catalogue A3): two entities painted one way in one
  shot and the other way in a later one, with no change of ``stage.after``
  between them. :func:`order_flips` is the pure function under it. (The
  within-shot half, painted order against world depth, is not built.)
- ``jump_cut`` (catalogue C4, the 30-degree rule): two consecutive shots of one
  subject from nearly the same angle and size. :func:`jump_cut_between` is the
  pure function under it.
- ``object_permanence`` (catalogue C1): an entity shown, then absent for whole
  shots, then shown again with no ``time_jump`` between and no entrance; and one
  entity drawn twice in a shot. :func:`vanishings` is the pure function under it.
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
    "SOLIDITY",
    "DRAW_ORDER",
    "JUMP_CUT",
    "OBJECT_PERMANENCE",
    "Vanishing",
    "vanishings",
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
    if (
        governing.clip.loop_mode is LoopMode.LOOP
        and abs(_local_time(governing, after_side))
        <= SIDE_S * governing.speed + SAME_INSTANT_S
    ):
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
                        and abs(kfs[k + 1].value - kfs[k].value)
                        > _tolerance(ch.property)
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

# -----------------------------------------------------------------------------
# solidity (an#509): two solids are not drawn through each other
# -----------------------------------------------------------------------------

#: Entity kinds that are not solids: a backdrop and a voice occupy no place a
#: body could be pushed out of.
NON_SOLID_KINDS: frozenset[str] = frozenset({"environment", "voice"})
#: Prop descriptor kinds that are drawings laid over the scene (a route on a map,
#: a title), not things a body could stand in: never solids.
DRAWING_DESCRIPTOR_KINDS: frozenset[str] = frozenset(
    {"PathDescriptor", "TextDescriptor"}
)
#: The ``AssetRef.overrides`` key that opts one entity out (a glow, a balloon).
SOLID_OVERRIDE: str = "solid"
#: How much of the smaller box the other may cover before it is penetration: a
#: fraction of the smaller box's area. Boxes are upper bounds on what is painted
#: (a character's box takes in a swung arm), so a touch is not a finding.
SOLIDITY_TOLERANCE: float = 0.25
#: Seconds between the instants a shot is sampled at (the last frame is always one).
SOLIDITY_SAMPLE_S: float = 0.25


@dataclass(frozen=True)
class Overlap:
    """Two solids ``a`` and ``b`` whose boxes cover ``fraction`` of the smaller one at ``at``."""

    a: str
    b: str
    at: float
    fraction: float


def _union_box(
    boxes: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _covered_fraction(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """The share of the smaller box's area the other covers (0 when they miss).

    >>> _covered_fraction((0, 0, 10, 10), (5, 0, 15, 10))
    0.5
    >>> _covered_fraction((0, 0, 10, 10), (20, 0, 30, 10))
    0.0
    >>> _covered_fraction((0, 0, 10, 10), (2, 2, 4, 4))
    1.0
    """
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return w * h / smaller if smaller > 0 else 0.0


def _is_solid(entity: Any) -> bool:
    overrides = entity.overrides or {}
    return (
        entity.kind not in NON_SOLID_KINDS
        and overrides.get(SOLID_OVERRIDE) is not False
    )


def _is_ordered(a: Any, b: Any) -> bool:
    """Either one is drawn after something (``stage.after``): an overlap is occlusion."""
    return any(e.stage is not None and e.stage.after is not None for e in (a, b))


def _sample_times(duration: float) -> list[float]:
    n = int(duration / SOLIDITY_SAMPLE_S)
    times = [i * SOLIDITY_SAMPLE_S for i in range(n + 1)]
    if duration - times[-1] > SAME_INSTANT_S:
        times.append(duration)
    return times


def solid_overlaps(
    doc: Any,
    entities: list[Any],
    *,
    duration: float,
    tolerance: float = SOLIDITY_TOLERANCE,
) -> list[Overlap]:
    """Per unordered pair of solids among ``entities`` (AssetRefs), the first
    sampled instant their boxes overlap by more than ``tolerance``, with the
    worst overlap seen up to the end of the shot as ``fraction``.

    An entity's box is the union of its visuals' boxes (:func:`an.stage.timeline.node_box`,
    through the pose and the camera at that instant).
    """
    from an.stage.timeline import node_box, timeline_from_scene
    from an.stage.tree import walk_document
    from an.timing.timeline import evaluate_timeline

    solids = [e for e in entities if _is_solid(e)]
    if len(solids) < 2:
        return []
    drawn = {
        e.id: [
            path
            for path, node in walk_document(doc)
            if node.visual is not None and (path == e.id or path.startswith(f"{e.id}/"))
        ]
        for e in solids
    }
    timeline = timeline_from_scene(doc)
    first: dict[tuple[str, str], Overlap] = {}
    worst: dict[tuple[str, str], float] = {}
    for t in _sample_times(duration):
        pose = evaluate_timeline(timeline, t)
        boxes = {}
        for e in solids:
            found = [
                b for p in drawn[e.id] if (b := node_box(doc, p, pose=pose)) is not None
            ]
            if found:
                boxes[e.id] = _union_box(found)
        for i, a in enumerate(solids):
            for b in solids[i + 1 :]:
                if a.id not in boxes or b.id not in boxes or _is_ordered(a, b):
                    continue
                frac = _covered_fraction(boxes[a.id], boxes[b.id])
                key = (a.id, b.id)
                if frac > tolerance:
                    worst[key] = max(worst.get(key, 0.0), frac)
                    first.setdefault(key, Overlap(a.id, b.id, t, frac))
    return [Overlap(o.a, o.b, o.at, worst[(o.a, o.b)]) for o in first.values()]


def check_solidity(ctx: Any) -> None:
    """The core's ``solidity`` check (an#509) over the compiled shot."""
    doc = compiled_shot(ctx)
    if doc is None:
        return
    props = (ctx.stores or {}).get("props")

    def is_drawing(entity: Any) -> bool:
        if entity.kind != "prop" or props is None:
            return False
        try:
            return (props[entity.ref] or {}).get("kind") in DRAWING_DESCRIPTOR_KINDS
        except Exception:  # noqa: BLE001 - a prop the store cannot read is reported elsewhere
            return False

    entities = [e for e in ctx.shot.entities if not is_drawing(e)]
    for o in solid_overlaps(doc, entities, duration=float(ctx.shot.duration)):
        ctx.report.add(
            "warning",
            f"{ctx.path}/entities",
            f"{o.a!r} and {o.b!r} overlap from {o.at:.2f} s, covering up to "
            f"{o.fraction:.0%} of the smaller: two solids drawn through each other. "
            f"Keep them apart, say which is in front with `stage.after`, or mark one "
            f"`overrides: {{{SOLID_OVERRIDE}: false}}` if it is not a solid.",
        )


SOLIDITY = Constraint(
    "solidity",
    check_solidity,
    description="two solids are not drawn through each other unless one is placed after (an#509)",
)


# -----------------------------------------------------------------------------
# draw order (an#510): the same two things are painted in the same order
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderFlip:
    """``front`` was painted over ``back`` in shot ``before`` and under it in shot ``after``."""

    back: str
    front: str
    before: int
    after: int


def painted_order(doc: Any, ids: Any) -> list[str]:
    """The entities among ``ids`` in the order the compiled scene paints them (back to front).

    >>> from an.stage.serialize import CutoutSceneJSON, NodeJSON, TimelineJSON
    >>> doc = CutoutSceneJSON(
    ...     scene=NodeJSON(name="root", children=[NodeJSON(name="b"), NodeJSON(name="a", z_index=-1.0)]),
    ...     timeline=TimelineJSON(duration=1.0),
    ... )
    >>> painted_order(doc, {"a", "b"})
    ['a', 'b']
    """
    kids = [(i, n) for i, n in enumerate(doc.scene.children) if n.name in ids]
    kids.sort(key=lambda p: (p[1].z_index if p[1].z_index is not None else p[0], p[0]))
    return [n.name for _, n in kids]


def order_flips(
    orders: list[list[str]], afters: list[Mapping[str, str | None]]
) -> list[OrderFlip]:
    """Pairs whose painted order differs from the last shot that had both.

    ``orders[i]`` is shot ``i``'s painted order, back to front; ``afters[i]`` maps
    its entities to their ``stage.after``. A flip is not reported when either
    entity's ``after`` changed between the two shots: the author said so.

    >>> order_flips([["a", "b"], ["b", "a"]], [{}, {}])
    [OrderFlip(back='a', front='b', before=0, after=1)]
    >>> order_flips([["a", "b"], ["b", "a"]], [{}, {"a": "b"}])
    []
    """
    out: list[OrderFlip] = []
    seen: dict[frozenset[str], tuple[int, str]] = {}  # pair -> (shot, the back one)
    for i, order in enumerate(orders):
        for pos, front in enumerate(order):
            for back in order[:pos]:
                pair = frozenset((back, front))
                if pair in seen:
                    j, was_back = seen[pair]
                    changed = any(afters[j].get(e) != afters[i].get(e) for e in pair)
                    if was_back != back and not changed:
                        out.append(OrderFlip(was_back, back, j, i))
                seen[pair] = (i, back)
    return out


def check_draw_order(ctx: Any) -> None:
    """The core's ``draw_order`` check (an#510): painted order across the shots."""
    orders: list[list[str]] = []
    afters: list[dict[str, str | None]] = []
    world_ids = {m.id for m in ctx.scene.world.members} if ctx.scene.world else set()
    shots = ctx.shots
    for i, shot in enumerate(shots):
        ctx.shot, ctx.index = shot, i
        doc = compiled_shot(ctx)
        ctx.shot = ctx.index = None
        # a world derives its members' order from depth (ADR 0009), so it may flip
        ids = {e.id for e in shot.entities if e.kind not in NON_SOLID_KINDS} - world_ids
        orders.append(painted_order(doc, ids) if doc is not None else [])
        afters.append({e.id: e.stage.after if e.stage else None for e in shot.entities})
    for f in order_flips(orders, afters):
        ctx.report.add(
            "warning",
            f"timeline/{f.after}/entities",
            f"{f.front!r} is painted over {f.back!r} in shot {shots[f.before].id!r} "
            f"(timeline/{f.before}) and under it in shot {shots[f.after].id!r}: the order "
            f"flips with nothing saying so. Say which is in front with `stage.after` in the "
            f"shot that changes, or keep one order.",
        )


DRAW_ORDER = Constraint(
    "draw_order",
    check_draw_order,
    stage="finish",
    description="two entities are painted in the same order in every shot unless `after` changes (an#510)",
)


# -----------------------------------------------------------------------------
# jump_cut (catalogue C4): the 30-degree rule over viewpoints
# -----------------------------------------------------------------------------

#: Two views of one subject that differ by less than this in look direction are
#: close enough to be a jump cut when the size does not change either (degrees).
JUMP_CUT_ANGLE_DEG: float = 30.0
#: ... and by less than this ratio in the subject's apparent size (larger / smaller):
#: about one shot-size step (a close-up fills 1.57 times a medium).
JUMP_CUT_SIZE_RATIO: float = 1.3


def _centroid(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    n = len(points)
    return tuple(sum(p[i] for p in points) / n for i in range(3))  # type: ignore[return-value]


def jump_cut_between(
    a: Any, b: Any, subject: list[tuple[float, float, float]]
) -> tuple[float, float] | None:
    """``(angle in degrees, size ratio)`` between two :class:`an.ir.world.Projection`
    views of ``subject`` (world points), when it is a jump cut: both under the
    limits. ``None`` otherwise, and when the subject is not in front of both.

    >>> from an.ir.world import Projection
    >>> def eye(x, z=0.0):
    ...     return Projection(at=(x, 0.0, z), forward=(0.0, 0.0, 1.0), right=(1.0, 0.0, 0.0), down=(0.0, 1.0, 0.0), focal=1000.0)
    >>> jump_cut_between(eye(0.0), eye(0.0, z=1.0), [(0.0, 0.0, 10.0)])
    (0.0, 1.1111111111111112)
    >>> jump_cut_between(eye(0.0), eye(0.0, z=6.0), [(0.0, 0.0, 10.0)]) is None   # 2.5x closer
    True
    """
    import math

    c = _centroid(subject)
    va, vb = a.view(c), b.view(c)
    if va[2] <= 0 or vb[2] <= 0:
        return None
    dot = sum(x * y for x, y in zip(a.forward, b.forward))
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    sa, sb = a.focal / va[2], b.focal / vb[2]
    ratio = max(sa, sb) / min(sa, sb)
    return (
        (angle, ratio)
        if angle < JUMP_CUT_ANGLE_DEG and ratio < JUMP_CUT_SIZE_RATIO
        else None
    )


def check_jump_cut(ctx: Any) -> None:
    """The core's ``jump_cut`` check: consecutive shots framing the same subject."""
    world = ctx.scene.world
    if world is None:
        return
    from an.ir.world import resolve_viewpoint, viewpoint_of
    from an.stage.world import member_extents

    res = ctx.scene.meta.resolution
    width, height = int(res.width), int(res.height)
    extents = ctx.cached(
        "constraints.extents",
        lambda: member_extents(
            world, ctx.stores, width=width, height=height, problems={}
        ),
    )
    at = {m.id: m.at for m in world.members if m.at is not None}
    views: list[tuple[frozenset[str], Any] | None] = []
    for shot in ctx.scene.timeline:
        try:
            vp = viewpoint_of(world, shot.viewpoint)
            if vp is None or vp.subject is None:
                views.append(None)
                continue
            subject = frozenset(
                [vp.subject] if isinstance(vp.subject, str) else vp.subject
            )
            if not subject <= at.keys():
                views.append(None)
                continue
            views.append(
                (
                    subject,
                    resolve_viewpoint(
                        world, vp, extents=extents, width=width, height=height
                    ),
                )
            )
        except Exception:  # noqa: BLE001 - an unresolvable viewpoint is reported by the world check
            views.append(None)
    for i in range(1, len(views)):
        before, after = views[i - 1], views[i]
        if before is None or after is None or before[0] != after[0]:
            continue
        hit = jump_cut_between(before[1], after[1], [at[m] for m in sorted(after[0])])
        if hit is None:
            continue
        angle, ratio = hit
        prev, shot = ctx.scene.timeline[i - 1], ctx.scene.timeline[i]
        ctx.report.add(
            "warning",
            f"timeline/{i}/viewpoint",
            f"shots {prev.id!r} and {shot.id!r} frame {', '.join(sorted(after[0]))} from nearly the "
            f"same view ({angle:.0f}° apart, size x{ratio:.2f}): a jump cut. Move the camera "
            f"at least {JUMP_CUT_ANGLE_DEG:.0f}° or change the size by x{JUMP_CUT_SIZE_RATIO:g} or more.",
        )


JUMP_CUT = Constraint(
    "jump_cut",
    check_jump_cut,
    stage="finish",
    description="consecutive shots of one subject differ by 30 degrees or a shot size",
)


# -----------------------------------------------------------------------------
# object_permanence (catalogue C1): presence across shots, uniqueness in a shot
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Vanishing:
    """``entity`` is in shot ``before`` and again in shot ``after`` (timeline
    indices) but in none of the shots between."""

    entity: str
    before: int
    after: int


def vanishings(
    presence: list[frozenset[str]],
    time_jumps: list[bool],
    entrances: list[frozenset[str]] | None = None,
) -> list[Vanishing]:
    """The entities that vanish and return with nothing to explain it.

    ``presence[i]`` is the ids drawn in shot ``i``; ``time_jumps[i]`` says the
    transition into shot ``i`` passes time; ``entrances[i]`` is the ids shot ``i``
    opens by acting on. A return after absent shots is explained by a time jump
    into any shot from the first absent one to the returning one, or by an entrance.

    >>> shots = [frozenset({"a"}), frozenset(), frozenset({"a"})]
    >>> vanishings(shots, [False] * 3)
    [Vanishing(entity='a', before=0, after=2)]
    >>> vanishings(shots, [False, False, True])
    []
    >>> vanishings(shots, [False] * 3, [frozenset(), frozenset(), frozenset({"a"})])
    []
    >>> vanishings([frozenset({"a"}), frozenset({"a"})], [False] * 2)
    []
    """
    entrances = entrances or [frozenset()] * len(presence)
    out: list[Vanishing] = []
    last: dict[str, int] = {}
    for i, here in enumerate(presence):
        for entity in sorted(here):
            j = last.get(entity)
            if (
                j is not None
                and j < i - 1
                and not any(time_jumps[j + 1 : i + 1])
                and entity not in entrances[i]
            ):
                out.append(Vanishing(entity, j, i))
            last[entity] = i
    return out


def check_object_permanence(ctx: Any) -> None:
    """The core's ``object_permanence`` check: presence across shots, uniqueness in one."""
    from an.ir.validate import _opened

    shots = ctx.shots
    fps = ctx.scene.meta.fps
    presence: list[frozenset[str]] = []
    entrances: list[frozenset[str]] = []
    for i, shot in enumerate(shots):
        ids = [e.id for e in shot.entities if e.kind not in NON_SOLID_KINDS]
        for entity_id in sorted({x for x in ids if ids.count(x) > 1}):
            ctx.report.add(
                "error",
                f"timeline/{i}/entities",
                f"{entity_id!r} is drawn {ids.count(entity_id)} times in shot {shot.id!r}: "
                "one entity is one thing on screen. Give the second its own id.",
            )
        presence.append(frozenset(ids))
        entrances.append(frozenset(x for x in ids if _opened(shot, x, fps=fps)))
    jumps = [bool(s.transition and s.transition.time_jump) for s in shots]
    for v in vanishings(presence, jumps, entrances):
        ctx.report.add(
            "warning",
            f"timeline/{v.after}/entities",
            f"{v.entity!r} is in shot {shots[v.before].id!r}, absent from the shots "
            f"between and back in shot {shots[v.after].id!r} with no exit or entrance: "
            "it vanishes and reappears. Show it, open the shot with an action on it "
            "(an entrance), or set `transition.time_jump` on the cut that skips time.",
        )


OBJECT_PERMANENCE = Constraint(
    "object_permanence",
    check_object_permanence,
    stage="finish",
    description="an entity does not vanish and return across shots, nor appear twice in one (catalogue C1)",
)


#: The core's constraints, in the order their checks run within a stage.
CONSTRAINTS: tuple[Constraint, ...] = (
    CONTINUITY,
    SOLIDITY,
    DRAW_ORDER,
    JUMP_CUT,
    OBJECT_PERMANENCE,
)


def _register(constraints: tuple[Constraint, ...] = CONSTRAINTS) -> None:
    """Register the core's constraint checks once (the core's other checks are
    registered the same way when ``an.ir.validate`` loads)."""
    for constraint in constraints:
        if constraint.name not in check_names(owner=CORE_OWNER):
            register_check(constraint.semantic_check(), owner=CORE_OWNER)


_register()
