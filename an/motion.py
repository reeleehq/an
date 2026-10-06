"""Motion presets: a named vocabulary of moves, as authoring macros.

``pop_in``, ``hop``, ``shake``, ``slide_in``, ``slide_out``,
``squash_stretch`` and ``crawl`` each EXPAND to ordinary ``tween`` (and
``set``) actions on transform properties, composed with
:func:`~an.ir.compose.sequence` and :func:`~an.ir.compose.parallel`. Called from
Python, nothing downstream learns a preset exists: the flat timeline, ``an
validate``, the verifiers and the renderer see the same tweens an author could
have written by hand. No runtime change, and no compiled document that does not
use a preset moves by a byte.

These are the core's presets: each moves the node it is given (an entity
container, a text block, a plane) and needs no rig. The moves that name a
rig's parts or swap its views — ``nod``, ``point``, ``turn``, ``walk``,
``waddle``, ``speech_pulse`` — are the cut-out genre's, in ``cutan.motion``
(an#322); their old names here are live aliases while anything still imports
them. This module also holds what every preset is built from: the rest pose
(:func:`rest_pose`, :func:`stage_poses`), the landing ``set``, and
:func:`as_leaves`.

>>> from an.ir.compose import flatten, sequence
>>> leaves = _tweens(sequence(pop_in("charlie"), hop("charlie"), shake("charlie")))
>>> [(f.action.target, f.action.property) for f in leaves][:3]
[('charlie', 'scale_x'), ('charlie', 'scale_y'), ('charlie', 'y')]
>>> round(leaves[-1].end, 3)
1.35

**Targets.** A preset targets the node it is given — usually the entity
container (``"charlie"``), the node a descriptor's ``bone:root`` track animates
too. A target the built scene does not carry makes the render raise (the
runtime refuses an unknown node, naming the known ones); :func:`rest_pose`
raises for it up front, before any browser starts.

**Landing.** Every preset ends each property it moves with a ``set`` at the
value it ends on, so the move lands exactly whatever the frame rate or
``step_hz`` (a tween ending between two frames otherwise leaves the property
where the last sampled frame had it). The ``set`` holds until the next tween
on that property.

**Rest.** A tween's value is ABSOLUTE, and every preset writes its ``from``
explicitly so presets chain without a jump. Each preset therefore needs the
target node's rest value for the properties it moves; ``rest=None`` means the
identity pose (``x = y = rotation = 0``, ``scale = 1``), which is right for
every rotation, and for ``y``/``scale`` of any entity without a ``stage``
placement — but an entity's ``x`` is laid out across the shot (``-110`` and
``110`` for two characters), so a move on ``x`` (``shake``, ``slide_in``,
``slide_out``) in a shot with more than one character
wants ``rest=rest_pose(shot, "charlie")``, which reads the value off the
compiler's own scene builder rather than restating its layout.

**scene.md: play a preset by name** (an#166; ``play`` is the cut-out genre's
action kind, and ``cutan.motion.PRESETS`` lists these presets with its own). ``{kind: play, target:
charlie, animation: hop, args: {height: 30}, start: 1.0}`` expands to exactly
this module's tweens at compile, with ``rest`` the pose the node HAS at the
play's start — the built scene's (stage placement, layout) overridden by the
sets and tweens before it (an#212) — so no ``rest=``, and a preset after a move
starts where the move left it (an entrance in :data:`HOME_PRESETS` lands on the
built pose instead); ``args`` are the preset's keyword arguments. A character
descriptor animation of the same name WINS; ``an validate`` and the compiler
decide both through :func:`cutan.characters.play.play_problems`. ``duration``
stretches the move and ``speed`` divides it; ``loop`` is refused. In a
``sequence`` a ``play`` without a ``duration`` occupies the preset's own
length divided by ``speed``, so two in a row run one after the other.
:func:`as_leaves` remains for a preset composed in Python and written into
``scene.md`` as plain, hand-editable tweens (a composition tree round-trips
too since an#241, but verbatim, as its JSON form).
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping
from functools import lru_cache
from typing import Any

from an._shims import moved_names
from an.base import EasingSpec, PathStr, Seconds
from an.ir.compose import FlatAction, delay, flatten, parallel, sequence, set_, tween
from an.ir.schema import Action, SetAction, Shot, TweenAction

# -----------------------------------------------------------------------------
# Easings and defaults
# -----------------------------------------------------------------------------

#: A cubic-Bézier that overshoots its target by about 10% and settles back
#: (CSS "easeOutBack"). The compiler and both evaluators take any 4-point
#: Bézier on a numeric channel, and nothing clamps ``y`` to ``[0, 1]``.
OVERSHOOT: tuple[float, float, float, float] = (0.34, 1.56, 0.64, 1.0)

#: Rising/leaving half of a move (decelerate into the apex).
DFLT_OUT_EASING: EasingSpec = "ease_out"
#: Falling/returning half of a move (accelerate out of the apex).
DFLT_IN_EASING: EasingSpec = "ease_in"
#: Back-and-forth oscillations.
DFLT_OSCILLATION_EASING: EasingSpec = "ease_in_out"

DFLT_POP_IN_DURATION: Seconds = 0.45
DFLT_HOP_HEIGHT: float = 40.0  # scene px; screen y grows DOWN, so up is minus
DFLT_HOP_DURATION: Seconds = 0.5
DFLT_SHAKE_AMPLITUDE: float = 8.0  # scene px
DFLT_SHAKE_DURATION: Seconds = 0.4
DFLT_SHAKE_CYCLES: int = 3
DFLT_SLIDE_DISTANCE: float = 600.0  # scene px
DFLT_SLIDE_DURATION: Seconds = 0.35
DFLT_SQUASH_AMOUNT: float = 0.2  # fraction of the rest scale
DFLT_SQUASH_DURATION: Seconds = 0.36
#: The crawl (an#314): how far up its tilted plane the content travels (scene
#: px along the plane), in how long, at what tilt (radians; ~55°, the top
#: receding) and eye distance (frame heights), with the far fade's start and
#: end (scene px up the plane from the hinge; sized for a 1080-row frame).
DFLT_CRAWL_DISTANCE: float = 2400.0
DFLT_CRAWL_DURATION: Seconds = 30.0
DFLT_CRAWL_TILT: float = 0.96
DFLT_CRAWL_PERSPECTIVE: float = 1.0
DFLT_CRAWL_FADE: tuple[float, float] | None = (700.0, 1500.0)
DFLT_CRAWL_EASING: EasingSpec = "linear"
#: The properties a preset may read a rest value for.
POSE_PROPERTIES: tuple[str, ...] = ("x", "y", "rotation", "scale_x", "scale_y", "alpha")


def _identity_pose() -> dict[str, float]:
    """A node's rest pose with nothing placed: the transform schema's defaults.

    Derived from ``TransformJSON`` — the compiler's own SSOT for rest values —
    rather than restated.
    """
    from an.stage.serialize import TransformJSON

    fields = TransformJSON.model_fields
    return {p: float(fields[p].default) for p in POSE_PROPERTIES}


@lru_cache(maxsize=None)
def _identity() -> dict[str, float]:
    """:func:`_identity_pose`, once. Lazy: ``import an.motion`` must not load the stage."""
    return _identity_pose()


#: The rig presets and their defaults moved to the cut-out genre (an#322): they
#: name a rig's parts or swap its views. Live aliases, removed under the
#: genre-move shim rule (no importer under the projects folder, and 14 days).
_MOVED_TO_CUTAN: tuple[str, ...] = (
    "nod",
    "point",
    "turn",
    "face_toward",
    "walk",
    "waddle",
    "speech_pulse",
    "GAITS",
    "WALK_LANDING_S",
    "WALK_LEG_NAMES",
    "WALK_ARM_NAMES",
    "WALK_SWING_VIEWS",
    "DFLT_NOD_PART",
    "DFLT_NOD_ANGLE",
    "DFLT_NOD_DURATION",
    "DFLT_NOD_COUNT",
    "DFLT_POINT_ANGLE",
    "DFLT_POINT_RAISE",
    "DFLT_POINT_HOLD",
    "DFLT_WADDLE_STEPS",
    "DFLT_WADDLE_STEP_DURATION",
    "DFLT_WADDLE_ANGLE",
    "DFLT_WADDLE_LIFT",
    "DFLT_TURN_DURATION",
    "DFLT_TURN_SET",
    "DFLT_TURN_TO",
    "DFLT_WALK_STEP_S",
    "DFLT_WALK_STEPS",
    "DFLT_WALK_STEP_LENGTH",
    "DFLT_WALK_STRIDE",
    "DFLT_WALK_LIFT",
    "DFLT_WALK_BOB",
    "DFLT_WALK_ARM_SWING",
    "DFLT_WALK_ROCK",
    "DFLT_WALK_HEM_TILT",
    "DFLT_PULSE_PART",
    "DFLT_PULSE_STRENGTH",
    "DFLT_PULSE_ATTACK_S",
    "DFLT_PULSE_RELEASE_S",
)
_moved = moved_names(__name__, {n: f"cutan.motion:{n}" for n in _MOVED_TO_CUTAN})


def __getattr__(name: str):
    """``IDENTITY_POSE`` (``x = y = rotation = 0``, ``scale_x = scale_y = alpha = 1``), on
    first use; a rig preset's old name, from ``cutan.motion`` (an#322)."""
    if name == "IDENTITY_POSE":
        return dict(_identity())
    return _moved(name)


Rest = Mapping[str, float]


def _rest(rest: Rest | None, prop: str) -> float:
    return float((rest or {}).get(prop, _identity()[prop]))


def _tweens(action: Action) -> list[FlatAction]:
    """The flattened TWEENS of ``action`` (the settling ``set``s left out)."""
    return [f for f in flatten(action) if isinstance(f.action, TweenAction)]


def _positive(**durations: float) -> None:
    for name, value in durations.items():
        if not value > 0:
            raise ValueError(f"{name} must be positive, got {value!r}")


def _settled(target: PathStr, prop: str, value: float, *moves: Action) -> Action:
    """``moves`` then a ``set`` pinning ``prop`` at ``value`` where they end.

    A frame shows the pose at ``i / fps`` and the runtime HOLDS the last pose it
    applied, so a tween ending between two frames leaves its property wherever
    the last sampled frame had it — off rest by a fraction of the final
    segment, and under ``step_hz`` by the whole of it, since a stepped segment
    shorter than one grid step holds its ``from`` value to its last instant. A
    ``set`` holds from the first frame at or after its time until the next
    tween on the same property, so it lands the move exactly.
    """
    return sequence(*moves, set_(target, prop, value))


def _through(
    target: PathStr,
    prop: str,
    values: list[float],
    *,
    durations: list[Seconds],
    easings: list[EasingSpec],
) -> Action:
    """Tweens from ``values[i]`` to ``values[i+1]``, one after the other.

    Every segment names its ``from``, so the chain never depends on what the
    runtime was holding when it started.
    """
    return _settled(
        target,
        prop,
        values[-1],
        *(
            tween(target, prop, to=b, duration=d, from_=a, easing=e)
            for a, b, d, e in zip(values, values[1:], durations, easings)
        ),
    )


def _alternating(n: int, first: EasingSpec, second: EasingSpec) -> list[EasingSpec]:
    return [first if i % 2 == 0 else second for i in range(n)]


# -----------------------------------------------------------------------------
# Presets
# -----------------------------------------------------------------------------


def pop_in(
    target: PathStr,
    *,
    duration: Seconds = DFLT_POP_IN_DURATION,
    easing: EasingSpec = OVERSHOOT,
    rest: Rest | None = None,
) -> Action:
    """Grow from nothing to full size, overshooting and settling (an entrance).

    Scales the target from 0 to its rest scale. Before the preset starts the
    target shows at its rest pose: to keep it hidden until it pops, start the
    preset at the target's first frame (or hold ``scale_x``/``scale_y`` at 0
    with a ``set`` before it).

    >>> [(f.action.property, f.action.from_value, f.action.to_value)
    ...  for f in _tweens(pop_in("charlie"))]
    [('scale_x', 0.0, 1.0), ('scale_y', 0.0, 1.0)]
    """
    _positive(duration=duration)
    return parallel(
        *(
            _settled(
                target,
                p,
                _rest(rest, p),
                tween(
                    target,
                    p,
                    to=_rest(rest, p),
                    duration=duration,
                    from_=0.0,
                    easing=easing,
                ),
            )
            for p in ("scale_x", "scale_y")
        )
    )


def hop(
    target: PathStr,
    *,
    height: float = DFLT_HOP_HEIGHT,
    duration: Seconds = DFLT_HOP_DURATION,
    rest: Rest | None = None,
) -> Action:
    """Jump up by ``height`` scene pixels and land back where it started.

    >>> [(f.action.from_value, f.action.to_value) for f in _tweens(hop("charlie", height=30))]
    [(0.0, -30.0), (-30.0, 0.0)]
    """
    _positive(duration=duration)
    y0 = _rest(rest, "y")
    half = duration / 2
    return _through(
        target,
        "y",
        [y0, y0 - height, y0],
        durations=[half, half],
        easings=[DFLT_OUT_EASING, DFLT_IN_EASING],
    )


def shake(
    target: PathStr,
    *,
    amplitude: float = DFLT_SHAKE_AMPLITUDE,
    duration: Seconds = DFLT_SHAKE_DURATION,
    cycles: int = DFLT_SHAKE_CYCLES,
    rest: Rest | None = None,
) -> Action:
    """Tremble side to side ``cycles`` times and come back to rest (on ``x``).

    >>> [f.action.to_value for f in _tweens(shake("charlie", amplitude=5, cycles=2))]
    [5.0, -5.0, 5.0, -5.0, 0.0]
    >>> [f.action.to_value for f in _tweens(shake("charlie", cycles=1, rest={"x": -110}))]
    [-102.0, -118.0, -110.0]
    """
    if cycles < 1:
        raise ValueError(f"shake needs at least one cycle, got {cycles}")
    _positive(duration=duration)
    x0 = _rest(rest, "x")
    values = [x0] + [x0 + amplitude, x0 - amplitude] * cycles + [x0]
    n = len(values) - 1
    return _through(
        target,
        "x",
        values,
        durations=[duration / n] * n,
        easings=[DFLT_OSCILLATION_EASING] * n,
    )


_SIDES: dict[str, float] = {"left": -1.0, "right": 1.0}


def _side_sign(side: str) -> float:
    if side not in _SIDES:
        raise ValueError(f"side must be one of {sorted(_SIDES)}, got {side!r}")
    return _SIDES[side]


def slide_in(
    target: PathStr,
    *,
    from_side: str = "left",
    distance: float = DFLT_SLIDE_DISTANCE,
    duration: Seconds = DFLT_SLIDE_DURATION,
    easing: EasingSpec = OVERSHOOT,
    rest: Rest | None = None,
) -> Action:
    """Whip in from ``distance`` pixels off to one side, overshoot, and settle.

    >>> [(f.action.from_value, f.action.to_value) for f in _tweens(slide_in("charlie", distance=400))]
    [(-400.0, 0.0)]
    """
    _positive(duration=duration)
    x0 = _rest(rest, "x")
    return _settled(
        target,
        "x",
        x0,
        tween(
            target,
            "x",
            to=x0,
            duration=duration,
            from_=x0 + _side_sign(from_side) * distance,
            easing=easing,
        ),
    )


def slide_out(
    target: PathStr,
    *,
    to_side: str = "right",
    distance: float = DFLT_SLIDE_DISTANCE,
    duration: Seconds = DFLT_SLIDE_DURATION,
    easing: EasingSpec = DFLT_IN_EASING,
    rest: Rest | None = None,
) -> Action:
    """Exit ``distance`` pixels off to one side, accelerating (an exit).

    >>> [(f.action.from_value, f.action.to_value) for f in _tweens(slide_out("charlie", to_side="left"))]
    [(0.0, -600.0)]
    """
    _positive(duration=duration)
    x0 = _rest(rest, "x")
    end = x0 + _side_sign(to_side) * distance
    return _settled(
        target,
        "x",
        end,
        tween(target, "x", to=end, duration=duration, from_=x0, easing=easing),
    )


def squash_stretch(
    target: PathStr,
    *,
    amount: float = DFLT_SQUASH_AMOUNT,
    duration: Seconds = DFLT_SQUASH_DURATION,
    rest: Rest | None = None,
) -> Action:
    """Squash (wide and short), stretch (narrow and tall), then settle.

    Scales about the target's own origin (for the procedural rig, the torso's
    centre). Volume is roughly kept: one axis grows by what the other loses.

    >>> [[round(f.action.to_value, 2) for f in _tweens(squash_stretch("c"))
    ...   if f.action.property == p] for p in ("scale_x", "scale_y")]
    [[1.2, 0.9, 1.0], [0.8, 1.1, 1.0]]
    """
    _positive(duration=duration)
    sx0, sy0 = _rest(rest, "scale_x"), _rest(rest, "scale_y")
    third = duration / 3
    easings = [DFLT_OUT_EASING, DFLT_OSCILLATION_EASING, DFLT_IN_EASING]

    def chain(prop: str, s0: float, sign: float) -> Action:
        values = [s0, s0 * (1 + sign * amount), s0 * (1 - sign * amount / 2), s0]
        return _through(target, prop, values, durations=[third] * 3, easings=easings)

    return parallel(chain("scale_x", sx0, 1.0), chain("scale_y", sy0, -1.0))


def crawl(
    target: PathStr,
    *,
    distance: float = DFLT_CRAWL_DISTANCE,
    duration: Seconds = DFLT_CRAWL_DURATION,
    start: float | None = None,
    tilt: float = DFLT_CRAWL_TILT,
    perspective: float = DFLT_CRAWL_PERSPECTIVE,
    fade: tuple[float, float] | None = DFLT_CRAWL_FADE,
    y: float | None = None,
    easing: EasingSpec = DFLT_CRAWL_EASING,
    rest: Rest | None = None,
) -> Action:
    """An opening crawl: lay ``target`` on a plane tilted away, and slide it up and away.

    Sets the plane (``rotation_x`` = ``tilt``, ``perspective``, the far
    ``fade``, and the hinge's ``y`` when given) at the start, then ONE tween:
    ``pivot_y`` from ``start`` (default: where the pivot rests) to ``start +
    distance``. On a tilted node the pivot is the point of the plane on the
    hinge (an#314), so the content travels ``distance`` scene px along the
    plane; the slowing and shrinking as it recedes are the projection's, not
    the tween's. A block centred on its origin starts with its middle on the
    hinge: a negative ``start`` (half the block's height and more) has it
    enter from below. ``fade=None`` draws the plane to the horizon.

    >>> leaves = flatten(crawl("crawl", distance=1000, duration=20, start=-300, fade=None))
    >>> sorted((f.action.property, getattr(f.action, "value", None)) for f in leaves
    ...        if isinstance(f.action, SetAction) and f.start == 0)
    [('perspective', 1.0), ('rotation_x', 0.96)]
    >>> [(f.action.from_value, f.action.to_value, f.end) for f in _tweens(crawl("crawl",
    ...     distance=1000, duration=20, start=-300))]
    [(-300.0, 700.0, 20.0)]
    """
    _positive(duration=duration)
    p0 = float(start) if start is not None else float((rest or {}).get("pivot_y", 0.0))
    plane = [
        set_(target, "rotation_x", float(tilt)),
        set_(target, "perspective", float(perspective)),
    ]
    if fade is not None:
        fade_start, fade_end = (float(v) for v in fade)
        if not 0.0 <= fade_start < fade_end:
            raise ValueError(
                f"fade must be (start, end) with 0 <= start < end, got {fade!r}"
            )
        plane += [
            set_(target, "plane_fade_start", fade_start),
            set_(target, "plane_fade_end", fade_end),
        ]
    if y is not None:
        plane.append(set_(target, "y", float(y)))
    end = p0 + float(distance)
    return parallel(
        *plane,
        _settled(
            target,
            "pivot_y",
            end,
            tween(
                target, "pivot_y", to=end, duration=duration, from_=p0, easing=easing
            ),
        ),
    )


#: The core's presets by name: the moves that need no rig. A genre's presets
#: (the cut-out ones: ``cutan.motion.PRESETS``, an#322) are listed beside these
#: by the genre, which owns the ``play`` that names them.
PRESETS: dict[str, Callable[..., Action]] = {
    f.__name__: f
    for f in (
        pop_in,
        hop,
        shake,
        slide_in,
        slide_out,
        squash_stretch,
        crawl,
    )
}

#: Each preset's vocabulary version (ADR 0003 decision 2): bump a preset's
#: version in the SAME change that makes it expand differently for the same
#: args, so every shot that plays it re-renders visibly instead of silently
#: (:mod:`an.semantic` folds it into the shot's vocabulary digest). Versioning
#: starts here (an#248).
PRESET_VERSIONS: dict[str, str] = {name: "1" for name in PRESETS}


#: Presets whose ``rest`` is the node's HOME — where an entrance LANDS — rather
#: than where the node is when the move starts. Played by name these read the
#: BUILT pose (``slide_out`` then ``slide_in`` comes back home; ``pop_in`` after a
#: ``set`` of the scales to 0 grows to full size); every other preset moves
#: relative to where the node IS at its start (an#212).
HOME_PRESETS: frozenset[str] = frozenset({"pop_in", "slide_in"})


# -----------------------------------------------------------------------------
# Rest from the built scene, and scene.md-friendly leaves
# -----------------------------------------------------------------------------


def rest_pose(
    shot: Shot, target: PathStr, *, mall: Mapping[str, Mapping] | None = None
) -> dict[str, float]:
    """The rest values of ``target``'s node as the compiler builds ``shot``.

    Compiles the shot's STAGE — its entities, without actions, dialogue or
    camera — through the cutout compiler's own scene builder, so the layout
    (``-110``/``110`` for two characters), a ``stage`` placement and a stage
    scale are read, never restated. Pass the same ``mall`` you render with:
    a descriptor rig is built from its character store.

    (These examples build character entities, the cut-out genre's; they are not run here.)
    >>> from an.ir.schema import AssetRef  # doctest: +SKIP
    >>> two = Shot(id="s", entities=[  # doctest: +SKIP
    ...     AssetRef(kind="character", id=n, store="characters", ref=n) for n in ("a", "b")])
    >>> rest_pose(two, "a")["x"], rest_pose(two, "b")["x"]  # doctest: +SKIP
    (-110.0, 110.0)
    >>> rest_pose(two, "a/head")["y"]  # doctest: +SKIP
    -55.0
    """
    poses = stage_poses(shot, mall=mall)
    if target not in poses:
        raise KeyError(f"no node {target!r} in the built scene; built: {sorted(poses)}")
    return poses[target]


def stage_poses(
    shot: Shot,
    *,
    mall: Mapping[str, Mapping] | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, dict[str, float]]:
    """``{node path: rest pose}`` for every node the compiler builds for
    ``shot``'s stage — what :func:`rest_pose` reads one entry of, and what
    ``an validate`` checks a preset ``play``'s node and every ``set``/``tween``
    target against (an#166, an#193). ``width``/``height`` (default: the
    compiler's) matter to text, whose line breaks depend on the frame.

    (These examples build character entities, the cut-out genre's; they are not run here.)
    >>> from an.ir.schema import AssetRef  # doctest: +SKIP
    >>> one = Shot(id="s", entities=[AssetRef(kind="character", id="c", store="characters", ref="c")])  # doctest: +SKIP
    >>> poses = stage_poses(one)  # doctest: +SKIP
    >>> "c/right_arm" in poses, poses["c/head"]["y"]  # doctest: +SKIP
    (True, -55.0)
    """
    from an.stage.compile import compile_shot

    stage = shot.model_copy(
        update={"actions": [], "dialogue": [], "narration": [], "camera": None}
    )
    with warnings.catch_warnings():
        # The stand-in-rig warning is the real render's to give, not this read's.
        warnings.simplefilter("ignore")
        size = {
            k: v for k, v in (("width", width), ("height", height)) if v is not None
        }
        doc = compile_shot(stage, mall, **size)
    from an.stage.tree import walk_document

    # Every indexed node, the overlay's too (an#155), by the runtime's rule
    # (an.stage.tree, `scope` included: an#343).
    return {
        path: {p: float(getattr(node.transform, p)) for p in POSE_PROPERTIES}
        for path, node in walk_document(doc)
    }


def as_leaves(action: Action, *, start: Seconds = 0.0) -> list[Action]:
    """``action`` as top-level leaves that ``scene.md`` can round-trip.

    The markdown writer spells a leaf and the ``sequence(delay(start), leaf)``
    wrapper the parser produces for a ``start:`` key in their short form, and
    writes any other composition tree verbatim (its JSON form, an#241). This
    flattens a preset (or any tree) into the short form, with the same
    absolute times, which is what a person editing ``scene.md`` wants.

    A ``set`` keeps its absolute time in ``at`` instead of a wrapper.

    >>> leaves = as_leaves(hop("charlie"), start=1.0)
    >>> [type(a).__name__ for a in leaves]
    ['SequenceAction', 'SequenceAction', 'SetAction']
    >>> [round(f.start, 3) for a in leaves for f in flatten(a)]  # each from 0
    [1.0, 1.25, 1.5]
    """
    out: list[Action] = []
    for f in flatten(action, start=start):
        leaf = f.action
        if isinstance(leaf, SetAction):
            out.append(leaf.model_copy(update={"at": f.start}))
        elif f.start > 0:
            out.append(sequence(delay(f.start), leaf))
        else:
            out.append(leaf)
    return out


__all__ = [
    "HOME_PRESETS",
    "IDENTITY_POSE",
    "OVERSHOOT",
    "PRESETS",
    "PRESET_VERSIONS",
    "as_leaves",
    "crawl",
    "hop",
    "pop_in",
    "rest_pose",
    "shake",
    "stage_poses",
    "slide_in",
    "slide_out",
    "squash_stretch",
]
