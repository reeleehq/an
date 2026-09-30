"""Motion presets: a named vocabulary of cut-out moves, as authoring macros.

``pop_in``, ``hop``, ``shake``, ``nod``, ``point``, ``slide_in``, ``slide_out``,
``squash_stretch``, ``waddle`` and ``turn`` each EXPAND to ordinary ``tween``
actions on transform properties (``turn`` adds one swap ``set``), composed with :func:`~an.ir.compose.sequence` and
:func:`~an.ir.compose.parallel`. Called from Python, nothing downstream
learns a preset exists: the flat timeline, ``an validate``, the verifiers and
the renderer see the same tweens an author could have written by hand. Played
by NAME from ``scene.md`` (an#166, below), the compiler expands the ``play``
into those same tweens before anything else looks; ``PlayAction.args`` is the
one IR field that added. No runtime change either way, and no compiled
document that does not use a preset moves by a byte.

>>> from an.ir.compose import flatten, sequence
>>> leaves = _tweens(sequence(pop_in("charlie"), hop("charlie"), nod("charlie")))
>>> [(f.action.target, f.action.property) for f in leaves][:3]
[('charlie', 'scale_x'), ('charlie', 'scale_y'), ('charlie', 'y')]
>>> round(leaves[-1].end, 3)
1.45

**Targets.** Whole-body moves target the entity container (``"charlie"``) —
the node a descriptor's ``bone:root`` track animates too. Part moves name the
part: ``nod`` rotates ``<entity>/head`` (the head is a direct child of the
entity on both the procedural and the descriptor rig), and ``point`` takes
the ARM node itself, because the two rigs name it differently — the
procedural rig's ``right_arm`` stands on the viewer's right, a descriptor
rig's ``arm_r`` on the viewer's left. The rigs are flat (arms are siblings of
the torso), and a target the built scene does not carry makes the render
raise (the runtime refuses an unknown node, naming the known ones);
:func:`rest_pose` raises for it up front, before any browser starts.

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
``slide_out``, ``waddle(travel=...)``) in a shot with more than one character
wants ``rest=rest_pose(shot, "charlie")``, which reads the value off the
compiler's own scene builder rather than restating its layout.

**scene.md: play a preset by name** (an#166). ``{kind: play, target:
charlie, animation: hop, args: {height: 30}, start: 1.0}`` expands to exactly
this module's tweens at compile, with ``rest`` the pose the node HAS at the
play's start — the built scene's (stage placement, layout) overridden by the
sets and tweens before it (an#212) — so no ``rest=``, and a preset after a move
starts where the move left it; ``args`` are the preset's keyword arguments. A character
descriptor animation of the same name WINS; ``an validate`` and the compiler
decide both through :func:`an.characters.play.play_problems`. ``duration``
stretches the move and ``speed`` divides it; ``loop`` is refused. In a
``sequence`` a ``play`` without a ``duration`` occupies the preset's own
length divided by ``speed``, so two in a row run one after the other.
:func:`as_leaves` remains for a preset composed in Python and written into
``scene.md`` as plain tweens (a composition tree does not round-trip).
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping
from typing import Any

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
DFLT_NOD_PART: str = "head"
DFLT_NOD_ANGLE: float = 0.18  # radians
DFLT_NOD_DURATION: Seconds = 0.5
DFLT_NOD_COUNT: int = 2
#: Negative is counter-clockwise on screen: an arm hanging from a shoulder
#: swings its hand to the VIEWER'S RIGHT — outward for the procedural rig's
#: ``right_arm``. A descriptor rig's ``arm_r`` hangs on the viewer's left, so
#: point it outward with a positive angle.
DFLT_POINT_ANGLE: float = -1.3  # radians
DFLT_POINT_RAISE: Seconds = 0.25
DFLT_POINT_HOLD: Seconds = 0.6
DFLT_SLIDE_DISTANCE: float = 600.0  # scene px
DFLT_SLIDE_DURATION: Seconds = 0.35
DFLT_SQUASH_AMOUNT: float = 0.2  # fraction of the rest scale
DFLT_SQUASH_DURATION: Seconds = 0.36
DFLT_WADDLE_STEPS: int = 4
DFLT_WADDLE_STEP_DURATION: Seconds = 0.3
DFLT_WADDLE_ANGLE: float = 0.1  # radians
DFLT_WADDLE_LIFT: float = 6.0  # scene px
DFLT_TURN_DURATION: Seconds = 0.3
#: The swap set a turn swaps: the factory's turnaround (an#197).
DFLT_TURN_SET: str = "view"
DFLT_TURN_TO: str = "back"

#: The properties a preset may read a rest value for.
POSE_PROPERTIES: tuple[str, ...] = ("x", "y", "rotation", "scale_x", "scale_y", "alpha")


def _identity_pose() -> dict[str, float]:
    """A node's rest pose with nothing placed: the transform schema's defaults.

    Derived from ``TransformJSON`` — the compiler's own SSOT for rest values —
    rather than restated.
    """
    from an.adapters.cutout.serialize import TransformJSON

    fields = TransformJSON.model_fields
    return {p: float(fields[p].default) for p in POSE_PROPERTIES}


#: ``x = y = rotation = 0``, ``scale_x = scale_y = alpha = 1``.
IDENTITY_POSE: dict[str, float] = _identity_pose()

Rest = Mapping[str, float]


def _rest(rest: Rest | None, prop: str) -> float:
    return float((rest or {}).get(prop, IDENTITY_POSE[prop]))


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


def nod(
    target: PathStr,
    *,
    part: str = DFLT_NOD_PART,
    angle: float = DFLT_NOD_ANGLE,
    duration: Seconds = DFLT_NOD_DURATION,
    count: int = DFLT_NOD_COUNT,
    rest: Rest | None = None,
) -> Action:
    """Dip the head ``count`` times (a rotation of ``<target>/<part>``).

    In a front-facing 2D cut-out a nod reads as a small head rotation about
    its pivot; ``rest`` is the HEAD's rest, not the entity's.

    >>> [(f.action.target, round(f.action.to_value, 2)) for f in _tweens(nod("charlie", count=1))]
    [('charlie/head', 0.18), ('charlie/head', 0.0)]
    """
    if count < 1:
        raise ValueError(f"nod needs a count of at least 1, got {count}")
    _positive(duration=duration)
    path = f"{target}/{part}" if part else target
    r0 = _rest(rest, "rotation")
    values = [r0] + [r0 + angle, r0] * count
    n = len(values) - 1
    return _through(
        path,
        "rotation",
        values,
        durations=[duration / n] * n,
        easings=_alternating(n, DFLT_OUT_EASING, DFLT_IN_EASING),
    )


def point(
    target: PathStr,
    *,
    angle: float = DFLT_POINT_ANGLE,
    raise_duration: Seconds = DFLT_POINT_RAISE,
    hold: Seconds = DFLT_POINT_HOLD,
    easing: EasingSpec = OVERSHOOT,
    rest: Rest | None = None,
) -> Action:
    """Swing an arm out to point, hold it, and lower it again.

    ``target`` is the ARM node — ``"charlie/right_arm"`` on the procedural
    rig, ``"maya/arm_r"`` on a descriptor rig (and there, since that arm hangs
    on the viewer's left, pass a positive ``angle`` to point outward).

    >>> [(f.start, f.action.to_value) for f in _tweens(point("charlie/right_arm", hold=0.5))]
    [(0.0, -1.3), (0.75, 0.0)]
    """
    _positive(raise_duration=raise_duration)
    if hold < 0:
        raise ValueError(f"hold must not be negative, got {hold!r}")
    r0 = _rest(rest, "rotation")
    return _settled(
        target,
        "rotation",
        r0,
        tween(
            target,
            "rotation",
            to=r0 + angle,
            duration=raise_duration,
            from_=r0,
            easing=easing,
        ),
        delay(hold),
        tween(
            target,
            "rotation",
            to=r0,
            duration=raise_duration,
            from_=r0 + angle,
            easing=DFLT_OSCILLATION_EASING,
        ),
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


def waddle(
    target: PathStr,
    *,
    steps: int = DFLT_WADDLE_STEPS,
    step_duration: Seconds = DFLT_WADDLE_STEP_DURATION,
    angle: float = DFLT_WADDLE_ANGLE,
    lift: float = DFLT_WADDLE_LIFT,
    travel: float = 0.0,
    rest: Rest | None = None,
) -> Action:
    """A walk cycle for a rig with no legs to animate: rock and bob per step.

    Each step rocks the body to alternate sides by ``angle`` and bobs it up by
    ``lift``; ``angle=0`` is a plain bob. ``travel`` (scene px, signed)
    carries the body sideways over the whole walk — the one ``x`` move here,
    so it is the one that needs ``rest`` in a multi-character shot.

    >>> w = _tweens(waddle("charlie", steps=2, travel=100))
    >>> sorted({f.action.property for f in w})
    ['rotation', 'x', 'y']
    >>> max(f.end for f in w)
    0.6
    """
    if steps < 1:
        raise ValueError(f"waddle needs at least one step, got {steps}")
    _positive(step_duration=step_duration)
    r0, y0 = _rest(rest, "rotation"), _rest(rest, "y")
    half = step_duration / 2
    rock = [r0]
    bob = [y0]
    for i in range(steps):
        rock += [r0 + (angle if i % 2 == 0 else -angle), r0]
        bob += [y0 - lift, y0]
    n = 2 * steps
    easings = _alternating(n, DFLT_OUT_EASING, DFLT_IN_EASING)
    moves = [
        _through(target, "rotation", rock, durations=[half] * n, easings=easings),
        _through(target, "y", bob, durations=[half] * n, easings=easings),
    ]
    if travel:
        x0 = _rest(rest, "x")
        moves.append(
            _settled(
                target,
                "x",
                x0 + travel,
                tween(
                    target,
                    "x",
                    to=x0 + travel,
                    duration=steps * step_duration,
                    from_=x0,
                    easing="linear",
                ),
            )
        )
    return parallel(*moves)


_FACINGS: tuple[str, ...] = ("right", "left")


def _facing_sign(name: str, value: str) -> float:
    if value not in _FACINGS:
        raise ValueError(f"{name} must be one of {list(_FACINGS)}, got {value!r}")
    return -1.0 if value == "left" else 1.0


def turn(
    target: PathStr,
    *,
    to: str = DFLT_TURN_TO,
    direction: str = "right",
    from_direction: str | None = None,
    duration: Seconds = DFLT_TURN_DURATION,
    view_set: str = DFLT_TURN_SET,
    rest: Rest | None = None,
) -> Action:
    """Turn a character to the view ``to`` — the classic cut-out turn (an#197).

    ``scale_x`` squashes to 0 (the character edge-on), the view swaps at that
    midpoint, and ``scale_x`` opens again to the rest scale — mirrored when
    ``direction="left"``: a ``side`` view is drawn facing the viewer's right,
    so ``direction`` is which way the character FACES after the turn.
    ``from_direction`` is which way it faced before — by default the sign of
    the rest ``scale_x`` (a character staged mirrored faces left). Called from
    Python the preset cannot see an EARLIER turn, so turning back from a
    left-facing profile is ``turn(to="front", from_direction="left")``; PLAYED
    by name (``{kind: play, animation: turn}``) the compiler fills it in from
    the timeline before it (:func:`an.characters.play.resolve_turns`, an#203).

    ``to`` is a key of the character's ``view`` set — ``front``, ``back``,
    ``side`` or ``three_quarter`` on a factory character
    (``an character new --offline``); the swap is a ``set`` on the ENTITY,
    which the compiler fans out to the head and torso and which poses the face
    (the back hides it, the profile keeps one eye). ``rest`` is the entity's:
    its ``scale_x`` magnitude is where the turn opens to.

    >>> def lands(a):  # a tween's end value, a set's value
    ...     return a.to_value if a.kind == "tween" else a.value
    >>> [(round(f.start, 2), f.action.property, lands(f.action))
    ...  for f in flatten(turn("ned", to="side", direction="left"))]
    [(0.0, 'scale_x', 0.0), (0.15, 'view', 'side'), (0.15, 'scale_x', -1.0), (0.3, 'scale_x', -1.0)]
    """
    _positive(duration=duration)
    if not isinstance(to, str) or not to:
        raise ValueError(
            f"to must name a view (a key of the {view_set!r} set), got {to!r}"
        )
    rest_sx = _rest(rest, "scale_x")
    s0 = abs(rest_sx)
    if from_direction is None:
        from_direction = "left" if rest_sx < 0 else "right"
    before = _facing_sign("from_direction", from_direction) * s0
    after = _facing_sign("direction", direction) * s0
    half = duration / 2
    return sequence(
        tween(
            target,
            "scale_x",
            to=0.0,
            duration=half,
            from_=before,
            easing=DFLT_IN_EASING,
        ),
        parallel(
            set_(target, view_set, to),
            _settled(
                target,
                "scale_x",
                after,
                tween(
                    target,
                    "scale_x",
                    to=after,
                    duration=half,
                    from_=0.0,
                    easing=DFLT_OUT_EASING,
                ),
            ),
        ),
    )


def face_toward(
    shot: Shot,
    who: str,
    other: str,
    *,
    view: str = "side",
    from_direction: str | None = None,
    duration: Seconds = DFLT_TURN_DURATION,
    mall: Mapping[str, Mapping] | None = None,
) -> Action:
    """:func:`turn` ``who`` to ``view``, facing ``other`` — the direction read
    off the stage, so a profile looks at the other character wherever the
    layout put them.

    >>> from an.ir.schema import AssetRef
    >>> two = Shot(id="s", entities=[
    ...     AssetRef(kind="character", id=n, store="characters", ref=n) for n in ("a", "b")])
    >>> [f.action.to_value for f in _tweens(face_toward(two, "b", "a"))]
    [0.0, -1.0]
    """
    poses = stage_poses(shot, mall=mall)
    for name in (who, other):
        if name not in poses:
            raise KeyError(f"no entity {name!r} in the shot; built: {sorted(poses)}")
    direction = "right" if poses[other]["x"] >= poses[who]["x"] else "left"
    return turn(
        who,
        to=view,
        direction=direction,
        from_direction=from_direction,
        duration=duration,
        rest=poses[who],
    )


#: Every preset by name — the one list the skill, the demo and the ``play``
#: fallback (:func:`an.characters.play.play_source`, an#166) read.
PRESETS: dict[str, Callable[..., Action]] = {
    f.__name__: f
    for f in (
        pop_in,
        hop,
        shake,
        nod,
        point,
        slide_in,
        slide_out,
        squash_stretch,
        waddle,
        turn,
    )
}


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

    >>> from an.ir.schema import AssetRef
    >>> two = Shot(id="s", entities=[
    ...     AssetRef(kind="character", id=n, store="characters", ref=n) for n in ("a", "b")])
    >>> rest_pose(two, "a")["x"], rest_pose(two, "b")["x"]
    (-110.0, 110.0)
    >>> rest_pose(two, "a/head")["y"]
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

    >>> from an.ir.schema import AssetRef
    >>> one = Shot(id="s", entities=[AssetRef(kind="character", id="c", store="characters", ref="c")])
    >>> poses = stage_poses(one)
    >>> "c/right_arm" in poses, poses["c/head"]["y"]
    (True, -55.0)
    """
    from an.adapters.cutout.compile import compile_shot

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
    found: dict[str, dict[str, float]] = {}

    def walk(node: Any, prefix: str) -> None:
        path = f"{prefix}/{node.name}" if prefix else node.name
        if prefix or node.name != "root":
            found[path] = {
                p: float(getattr(node.transform, p)) for p in POSE_PROPERTIES
            }
            child_prefix = path
        else:
            child_prefix = ""  # the synthetic root is not addressable
        for child in node.children:
            walk(child, child_prefix)

    walk(doc.scene, "")
    if doc.overlay is not None:  # an#155: overlay text is addressable too
        for child in doc.overlay.children:
            walk(child, "")
    return found


def as_leaves(action: Action, *, start: Seconds = 0.0) -> list[Action]:
    """``action`` as top-level leaves that ``scene.md`` can round-trip.

    The markdown writer keeps a leaf and the ``sequence(delay(start), leaf)``
    wrapper the parser produces for a ``start:`` key, and drops composition
    trees from ``scene.md``. This flattens a preset (or any tree) into exactly
    those, with the same absolute times.

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
    "IDENTITY_POSE",
    "face_toward",
    "OVERSHOOT",
    "PRESETS",
    "as_leaves",
    "hop",
    "nod",
    "point",
    "pop_in",
    "rest_pose",
    "shake",
    "stage_poses",
    "slide_in",
    "slide_out",
    "squash_stretch",
    "turn",
    "waddle",
]
