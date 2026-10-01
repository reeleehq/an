"""Composition combinators for authoring action trees, plus a flattener.

The composition tree is the *authoring* form. The flat list of `FlatAction`s
with absolute start times is the *canonical* form that gets verified, cached,
and rendered. Both forms round-trip through the schema; the flat form is
what tooling reasons about.

>>> from an.ir.compose import sequence, parallel, tween, delay, flatten
>>> action = sequence(
...     tween("charlie/torso", "rotation", to=10.0, duration=1.0),
...     delay(0.5),
...     tween("charlie/torso", "rotation", to=0.0, duration=1.0),
... )
>>> flat = flatten(action)
>>> [round(f.start, 3) for f in flat]
[0.0, 1.5]
>>> [round(f.end, 3) for f in flat]
[1.0, 2.5]
>>> action2 = parallel(
...     tween("a", "x", to=1.0, duration=2.0),
...     tween("b", "y", to=1.0, duration=3.0),
... )
>>> flat2 = flatten(action2)
>>> [(round(f.start, 2), round(f.end, 2)) for f in flat2]
[(0.0, 2.0), (0.0, 3.0)]
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from an.base import EasingSpec, PathStr, Seconds
from an.genres.registry import (
    CORE_OWNER,
    ActionKind,
    action_kind,
    register_action_kind,
)
from an.ir.schema import (
    DFLT_EXPRESSION_BLEND_S,
    Action,
    DelayAction,
    ExpressionAction,
    ExtensionAction,
    LoopAction,
    ParallelAction,
    PlayAction,
    SequenceAction,
    SetAction,
    TweenAction,
    unregistered_action_kind,
)


# -----------------------------------------------------------------------------
# Atoms — small fluent constructors that produce schema instances directly.
# -----------------------------------------------------------------------------


def set_(target: PathStr, property: str, value: Any, *, at: Seconds = 0.0) -> SetAction:
    """Discrete property set at time ``at`` (relative to its enclosing scope)."""
    return SetAction(target=target, property=property, value=value, at=at)


class _Inherit:
    """The type of :data:`INHERIT`."""

    def __repr__(self) -> str:
        return "INHERIT"


#: ``tween(..., easing=INHERIT)`` — the default — leaves the easing UNSET, so
#: the scene's ``meta.default_easing`` applies, else ``"ease_in_out"`` (an#166).
#: A sentinel rather than ``None`` because ``None`` already means linear.
INHERIT = _Inherit()


def tween(
    target: PathStr,
    property: str,
    to: Any,
    duration: Seconds,
    *,
    from_: Any | None = None,
    easing: EasingSpec | None | _Inherit = INHERIT,
) -> TweenAction:
    """Animate a property from ``from_`` (or its current value) to ``to``.

    ``easing`` left out inherits the scene's ``meta.default_easing`` (else
    ``"ease_in_out"``); naming one — ``"ease_in_out"`` included — pins it.

    >>> "easing" in tween("a", "x", to=1.0, duration=1.0).model_fields_set
    False
    >>> tween("a", "x", to=1.0, duration=1.0, easing="linear").easing
    'linear'
    """
    kwargs: dict[str, Any] = {} if easing is INHERIT else {"easing": easing}
    return TweenAction(
        target=target,
        property=property,
        to_value=to,
        from_value=from_,
        duration=duration,
        **kwargs,
    )


def play(
    target: PathStr,
    animation: str,
    *,
    duration: Seconds | None = None,
    speed: float = 1.0,
    loop: bool | None = None,
    args: dict[str, Any] | None = None,
) -> PlayAction:
    """Play a named animation of the target entity's descriptor (an#7).

    ``duration=None`` fills the animation's natural length — or the shot's
    remainder for a looping one. In a ``sequence`` a play with no ``duration``
    occupies its **natural** length (a motion preset's own length divided by
    ``speed``; a non-looping descriptor animation's likewise), so the sibling
    after it starts when it ends; a looping one runs to the shot end and
    occupies **zero**:

    >>> [f.start for f in flatten(sequence(play("a", "idle_breath"), delay(1.0), play("a", "blink")))]
    [0.0, 1.0]
    >>> [f.start for f in flatten(sequence(play("a", "idle_breath", duration=2.0), play("a", "blink")))]
    [0.0, 2.0]
    >>> [f.start for f in flatten(sequence(play("a", "hop"), play("a", "nod")))]
    [0.0, 0.5]
    >>> [f.start for f in flatten(sequence(play("a", "hop", speed=2.0), play("a", "nod")))]
    [0.0, 0.25]

    (Bare ``flatten`` knows only the presets, by name; ``an validate`` and the
    compiler pass the entity's descriptor too — :func:`an.characters.play.play_extent`
    — so a descriptor animation that shares a preset's name is measured as the
    descriptor's.)

    A name the descriptor does not declare falls back to a motion preset of
    :data:`an.motion.PRESETS`, with ``args`` as its parameters (an#166):

    >>> play("charlie", "hop", args={"height": 30}).args
    {'height': 30}
    """
    return PlayAction(
        target=target,
        animation=animation,
        duration=duration,
        speed=speed,
        loop=loop,
        args=args,
    )


def expression(
    target: PathStr,
    preset: str | None = None,
    *,
    axes: dict[str, float] | None = None,
    intensity: float = 1.0,
    duration: Seconds | None = None,
    blend: Seconds = DFLT_EXPRESSION_BLEND_S,
) -> ExpressionAction:
    """Hold a facial expression on an entity (an#98).

    ``duration=None`` runs to the shot end and counts as **zero** in a
    ``sequence``, as a looping ``play`` does:

    >>> [f.start for f in flatten(sequence(expression("a", "happy"), delay(1.0), expression("a", "sad")))]
    [0.0, 1.0]
    >>> flatten(expression("a", "angry", duration=2.0))[0].end
    2.0
    """
    return ExpressionAction(
        target=target,
        preset=preset,
        axes=dict(axes or {}),
        intensity=intensity,
        duration=duration,
        blend=blend,
    )


# -----------------------------------------------------------------------------
# Combinators — build composition trees.
# -----------------------------------------------------------------------------


def sequence(*actions: Action) -> SequenceAction:
    """Run children one after the other. Total duration = sum of child durations."""
    return SequenceAction(children=list(actions))


def parallel(*actions: Action) -> ParallelAction:
    """Run all children at once. Total duration = max of child durations."""
    return ParallelAction(children=list(actions))


def delay(duration: Seconds) -> DelayAction:
    """An empty span that consumes time. Useful inside `sequence`."""
    return DelayAction(duration=duration)


def loop(action: Action, count: int) -> LoopAction:
    """Repeat ``action`` ``count`` times."""
    if count < 1:
        raise ValueError(f"loop count must be >= 1, got {count}")
    return LoopAction(child=action, count=count)


def stagger(lag: Seconds, *actions: Action) -> ParallelAction:
    """Start each action ``lag`` seconds after the previous one STARTS.

    The **stagger** (Manim's ``LaggedStart``, ``previz``'s compose, a crowd
    entering one by one): the children run in parallel, the ``i``-th delayed
    by ``i * lag``. It is authoring sugar, not a new kind — it builds the
    ``parallel`` of ``sequence(delay(i * lag), action)`` it means, so the
    scene document, ``scene.md`` and every renderer see only core kinds.
    Total duration: the latest child's end. ``scene.md`` holds it verbatim (a
    ``kind: parallel`` entry), so it round-trips. (``an.stage.text.reveal_units`` —
    ``an.stage.text.stagger`` before an#241 — is the text-block preset: a LIST of
    per-unit actions with holds, not a combinator.)

    >>> flat = flatten(stagger(0.25, tween("a", "x", to=1.0, duration=1.0),
    ...                              tween("b", "x", to=1.0, duration=1.0),
    ...                              tween("c", "x", to=1.0, duration=1.0)))
    >>> [(f.action.target, f.start, f.end) for f in flat]
    [('a', 0.0, 1.0), ('b', 0.25, 1.25), ('c', 0.5, 1.5)]
    >>> duration_of(stagger(0.5, delay(1.0), delay(1.0)))
    1.5
    >>> stagger(0.1).children
    []
    >>> stagger(-1.0, delay(1.0))
    Traceback (most recent call last):
    ...
    ValueError: stagger lag must be >= 0, got -1.0
    """
    if not lag >= 0:  # `not >=` also refuses NaN
        raise ValueError(f"stagger lag must be >= 0, got {lag}")
    return parallel(
        *(
            sequence(delay(i * lag), action) if i else action
            for i, action in enumerate(actions)
        )
    )


# -----------------------------------------------------------------------------
# Duration and flattening — dispatched through the action-kind registry.
# -----------------------------------------------------------------------------


#: ``PlayAction -> seconds`` a play WITHOUT an explicit ``duration`` occupies in
#: a ``sequence``. The default is :func:`default_play_extent`; the compiler and
#: ``an validate`` pass one bound to the entity's descriptor. Generically, it is
#: the caller's **extent resolver**: it is handed to every leaf kind's
#: ``duration`` hook (:class:`an.genres.ActionKind`), and the kinds that have an
#: open-ended length (the cut-out genre's ``play``) consult it.
PlayExtent = Callable[[PlayAction], Seconds]


def default_play_extent(action: PlayAction) -> Seconds:
    """A duration-less play's extent when no descriptor is known: a motion
    preset's natural length over ``speed``, else ``0.0``.

    The one resolver is :func:`an.characters.play.play_extent`; this is it with
    ``desc=None``.

    >>> default_play_extent(PlayAction(target="a", animation="hop"))
    0.5
    >>> default_play_extent(PlayAction(target="a", animation="not_a_preset"))
    0.0
    """
    from an.characters.play import play_extent  # lazy: play imports the IR

    return play_extent(None, action)


def kind_of(action: Any) -> ActionKind:
    """The registered :class:`~an.genres.ActionKind` that governs ``action``.

    Raises :class:`~an.genres.UnregisteredKindError`, naming the genre that
    provides it, for a kind nobody registered.

    >>> kind_of(delay(1.0)).name
    'delay'
    """
    name = getattr(action, "kind", None)
    registered = action_kind(name) if isinstance(name, str) else None
    if registered is None:
        if isinstance(name, str):
            raise unregistered_action_kind(name)
        raise TypeError(f"Unknown action type: {type(action).__name__}")
    return registered


def resolve_action(action: Any) -> Any:
    """``action`` as its registered model (an :class:`ExtensionAction` left open
    by a document read before its genre loaded is validated now).

    >>> resolve_action(delay(0.5)).duration
    0.5
    """
    if type(action) is ExtensionAction:
        return action.resolved()
    return action


def iter_actions(action: Any):
    """``action`` and every action under it, depth first (composites through
    their kind's ``children`` hook). Unregistered kinds are yielded, not raised:
    a validator walks with this to REPORT them.

    >>> [a.kind for a in iter_actions(sequence(delay(1.0), loop(delay(0.5), 2)))]
    ['sequence', 'delay', 'loop', 'delay']
    """
    yield action
    registered = action_kind(getattr(action, "kind", None) or "")
    if registered is not None and registered.children is not None:
        for child in registered.children(action):
            yield from iter_actions(child)


def duration_of(action: Action, *, play_extent: PlayExtent | None = None) -> Seconds:
    """Compute the total duration of an action tree without evaluating it.

    ``play_extent`` resolves a duration-less ``play`` (see :data:`PlayExtent`).

    >>> duration_of(tween("a", "x", to=1.0, duration=2.0))
    2.0
    >>> duration_of(sequence(delay(0.5), tween("a", "x", to=1.0, duration=1.5)))
    2.0
    >>> duration_of(parallel(delay(0.5), delay(2.5)))
    2.5
    >>> duration_of(loop(delay(0.25), 4))
    1.0
    >>> duration_of(set_("a", "x", 1.0))
    0.0
    """
    action = resolve_action(action)
    registered = kind_of(action)
    if registered.duration is None:
        raise TypeError(f"action kind {registered.name!r} declares no duration")
    return registered.duration(action, play_extent)


@dataclass(frozen=True, slots=True)
class FlatAction:
    """A leaf action with its absolute start and end times.

    The flat-form list is the canonical representation passed to renderers
    and verifiers. Composition nodes (sequence/parallel/delay/loop) do not
    appear in the flat form — they're collapsed into time offsets.
    """

    start: Seconds
    end: Seconds
    action: Action  # always a leaf: SetAction | TweenAction | a genre's leaf (PlayAction, …)


@dataclass(slots=True)
class FlattenContext:
    """What a kind's ``flatten`` hook gets: where to put leaves, how to recurse.

    ``extent`` is the caller's extent resolver (:data:`PlayExtent`), passed on
    to every leaf's ``duration`` hook.
    """

    out: list[FlatAction]
    extent: PlayExtent | None = None

    def emit(self, start: Seconds, end: Seconds, action: Any) -> None:
        self.out.append(FlatAction(start=start, end=end, action=action))

    def flatten(self, action: Any, t: Seconds) -> Seconds:
        """Flatten ``action`` starting at ``t``; return the new cursor."""
        return _flatten_into(action, t, self)


def flatten(
    action: Action,
    *,
    start: Seconds = 0.0,
    play_extent: PlayExtent | None = None,
) -> list[FlatAction]:
    """Walk a composition tree, emitting leaf actions with absolute times.

    A ``play`` without ``duration`` advances a ``sequence`` by ``play_extent``
    (default :func:`default_play_extent`): its natural length, or zero for a
    looping animation, which runs to the shot end.

    Delays are absorbed into the timeline (they don't appear in the output).
    Loops are unrolled by simple repetition — appropriate at v0.1; the cutout
    runtime can re-roll for efficiency later.

    Every node is dispatched through its registered kind
    (:class:`~an.genres.ActionKind`), so a genre's kind flattens without an
    edit here; a node whose kind nobody registered raises, naming the genre
    that provides it, and an :class:`ExtensionAction` read before its genre
    loaded is validated by the registered model on the way through.
    """
    ctx = FlattenContext(out=[], extent=play_extent)
    _flatten_into(action, start, ctx)
    return ctx.out


def _flatten_into(action: Action, t: Seconds, ctx: FlattenContext) -> Seconds:
    """Append leaf actions to ``ctx.out`` and return the new cursor time."""
    action = resolve_action(action)
    registered = kind_of(action)
    if registered.flatten is not None:
        return registered.flatten(action, t, ctx)
    if registered.duration is None:
        raise TypeError(f"action kind {registered.name!r} declares no duration")
    d = registered.duration(action, ctx.extent)
    ctx.emit(t, t + d, action)
    return t + d


# -----------------------------------------------------------------------------
# The core kinds' hooks (the md hooks of `set`/`tween` live in `an.ir.sync`).
# -----------------------------------------------------------------------------


def _flatten_set(action: SetAction, t: Seconds, ctx: FlattenContext) -> Seconds:
    # `at` is relative to enclosing scope; absolute start is t + at.
    abs_t = t + action.at
    ctx.emit(abs_t, abs_t, action)
    return t  # set actions do not advance the cursor


def _flatten_delay(action: DelayAction, t: Seconds, ctx: FlattenContext) -> Seconds:
    return t + action.duration


def _flatten_sequence(
    action: SequenceAction, t: Seconds, ctx: FlattenContext
) -> Seconds:
    cursor = t
    for child in action.children:
        cursor = ctx.flatten(child, cursor)
    return cursor


def _flatten_parallel(
    action: ParallelAction, t: Seconds, ctx: FlattenContext
) -> Seconds:
    max_end = t
    for child in action.children:
        child_end = ctx.flatten(child, t)
        if child_end > max_end:
            max_end = child_end
    return max_end


def _flatten_loop(action: LoopAction, t: Seconds, ctx: FlattenContext) -> Seconds:
    cursor = t
    for _ in range(action.count):
        cursor = ctx.flatten(action.child, cursor)
    return cursor


def _register_core_kinds() -> None:
    """The core's six kinds, owned by the core (``an.genres.registry.CORE_OWNER``).

    Their ``scene.md`` hooks are attached by :mod:`an.ir.sync`, which owns the
    markdown form; the md-less composites have none.
    """
    for kind in (
        ActionKind(
            "set",
            SetAction,
            duration=lambda a, _extent: 0.0,
            flatten=_flatten_set,
            md_start=False,
            description="set a property to a value at an instant",
        ),
        ActionKind(
            "tween",
            TweenAction,
            duration=lambda a, _extent: a.duration,
            description="interpolate a property to a value over a duration",
        ),
        ActionKind(
            "sequence",
            SequenceAction,
            duration=lambda a, extent: sum(
                (duration_of(c, play_extent=extent) for c in a.children), 0.0
            ),
            flatten=_flatten_sequence,
            children=lambda a: a.children,
            description="run children one after the other",
        ),
        ActionKind(
            "parallel",
            ParallelAction,
            duration=lambda a, extent: max(
                (duration_of(c, play_extent=extent) for c in a.children),
                default=0.0,
            ),
            flatten=_flatten_parallel,
            children=lambda a: a.children,
            description="run children at once",
        ),
        ActionKind(
            "delay",
            DelayAction,
            duration=lambda a, _extent: a.duration,
            flatten=_flatten_delay,
            description="an empty span that consumes time",
        ),
        ActionKind(
            "loop",
            LoopAction,
            duration=lambda a, extent: (
                duration_of(a.child, play_extent=extent) * a.count
            ),
            flatten=_flatten_loop,
            children=lambda a: (a.child,),
            description="repeat a child count times",
        ),
    ):
        if action_kind(kind.name) is None:
            register_action_kind(kind, owner=CORE_OWNER)


_register_core_kinds()
