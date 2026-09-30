"""Resolve a ``play`` against a character descriptor — the renderer-free half (an#7).

A :class:`~an.ir.schema.PlayAction` names a descriptor animation. Its tracks
speak the DESCRIPTOR's vocabulary — bones, slots, attachment names, view-box
units, degrees — while the renderer's channels speak the SCENE's: node paths,
swap-set keys, scene pixels, radians. This module does everything on the
descriptor side of that line and knows no renderer, so that ``an validate``
and the cutout compiler share ONE verdict on whether a play can resolve. The
compiler used to decide alone, and validate passed plays that compile then
refused — four measured cases: an unknown bone property, a bone with no slot
of its own, a frame naming art that is not on disk, and a slot suppressed by
``face_overlay=false`` (an#7 review).

Every rule mirrors a rig-builder fact, and the builder imports the shared
helpers rather than restating them, so the two cannot drift:

- A bone track animates the node of the bone's **primary slot** — the slot
  named like the bone (:func:`primary_slot_per_bone`); ``bone:root.*``
  animates the entity container. A bone with no primary slot is a resolution
  error that *says so*: the old message ("no node of that name was built")
  named the symptom and left the rule for the author to guess.
- A slot track resolves to exactly **one** swap set: the set whose keys name
  every frame's attachment. Resolving frame-by-frame used to split a track
  across two channels; the runtime applies a pose's properties in name order,
  so ``blink`` never closed once a second set that sorted before ``eyelid``
  also named ``open``. Two candidates is an error naming both.
- Art is consulted when the caller can consult it (``art_exists``): a frame
  whose attachment is declared but not on disk is reported as exactly that,
  not as "no set resolves it".

>>> from an.characters.schema import CharacterDescriptor
>>> desc = CharacterDescriptor(name="maya")
>>> resolved = resolve_play(desc, "blink")
>>> [(t.slot, t.set_name) for t in resolved.tracks]
[('left_eye', 'eyelid'), ('right_eye', 'eyelid')]

**Motion presets (an#166).** A name the descriptor does not declare — or any
name on an entity with no descriptor (a procedural rig, a prop) — falls back
to :data:`an.motion.PRESETS`. The DESCRIPTOR WINS a name both know: a rig that
ships its own ``hop`` means that one. :func:`play_source` makes that call and
:func:`play_problems` gives the whole verdict, for ``an validate`` and the
compiler alike. A preset resolves to tweens, not a clip:
:func:`expand_preset_play` builds them at the moved node's REST pose, which
the caller reads off the built scene, so an author never passes ``rest``.

>>> play_problems(desc, "walk")  # doctest: +NORMALIZE_WHITESPACE
["no animation 'walk': the descriptor declares ['blink', 'idle_breath'] and no
  motion preset has that name (presets: ['hop', 'nod', 'point', 'pop_in',
  'shake', 'slide_in', 'slide_out', 'squash_stretch', 'turn', 'waddle'])"]
>>> play_source(desc, "hop"), play_source(None, "hop"), play_source(desc, "blink")
('preset', 'preset', 'descriptor')
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from an.characters.idle import evaluate_track
from an.characters.schema import (
    AnimationTrack,
    Attachment,
    CharacterDescriptor,
    IdleAnimation,
    Skin,
    Slot,
)

#: Descriptor bone-track properties → ``(runtime property, unit factor)``.
#: The descriptor speaks degrees for rotation; the runtime is radians.
BONE_TRACK_PROPERTIES: dict[str, tuple[str, float]] = {
    "x": ("x", 1.0),
    "y": ("y", 1.0),
    "rotation_deg": ("rotation", math.pi / 180.0),
    "scale_x": ("scale_x", 1.0),
    "scale_y": ("scale_y", 1.0),
}

#: Bone-track properties whose values are view-box LENGTHS, so a renderer
#: scales them by the rig's view-box → scene-pixel factor. Scales and angles
#: are dimensionless.
RIG_SCALED_PROPERTIES: frozenset[str] = frozenset({"x", "y"})

#: The bone that stands for the whole rig: a track on it animates the entity's
#: container node rather than any slot.
ROOT_BONE = "root"

#: The bone whose primary slot's nested slots are the FACE — what
#: ``face_overlay=false`` suppresses.
HEAD_BONE = "head"


class PlayResolutionError(ValueError):
    """A ``play`` that cannot resolve; ``problems`` lists every reason found."""

    def __init__(self, animation: str, problems: list[str]) -> None:
        self.animation = animation
        self.problems = list(problems)
        super().__init__(f"play of {animation!r}: " + "; ".join(self.problems))


@dataclass(frozen=True)
class BoneTrack:
    """A resolved ``bone:<name>.<prop>`` track.

    ``slot`` is the primary slot whose node carries the bone, or ``None`` for
    the entity container (``bone:root``). ``property`` is the RUNTIME name;
    values are ``rest + deviation * unit`` (times the rig's pixel factor when
    ``rig_scaled``).
    """

    track: AnimationTrack
    slot: str | None
    property: str
    unit: float
    rig_scaled: bool


@dataclass(frozen=True)
class SlotTrack:
    """A resolved ``slot:<name>.attachment`` track: one set, frames as KEYS."""

    track: AnimationTrack
    slot: str
    set_name: str
    frames: tuple[tuple[float, str], ...]


ResolvedTrack = Union[BoneTrack, SlotTrack]


@dataclass(frozen=True)
class ResolvedPlay:
    animation: IdleAnimation
    tracks: tuple[ResolvedTrack, ...]


# ----------------------------------------------------------------- rig facts


def primary_slot_per_bone(desc: CharacterDescriptor) -> dict[str, str]:
    """``{bone name: the slot that IS that bone}``, when one exists.

    Used for node nesting, which is deliberately **not** the bone hierarchy.
    The rigs here are flat by design — arms are siblings of the torso, not
    children (CLAUDE.md pillar 4) — so bone parentage decides *position* only.
    A slot nests under the primary slot of its bone when it is not that slot
    itself, which is what puts eyes and mouth under ``head`` and leaves every
    limb a direct child of the entity.

    >>> primary_slot_per_bone(CharacterDescriptor(name="m"))["head"]
    'head'
    """
    return {s.bone: s.name for s in desc.slots if s.name == s.bone}


def slot_parent(desc: CharacterDescriptor, slot: Slot) -> str | None:
    """The slot ``slot`` nests under, or ``None`` when it is a direct child."""
    parent = primary_slot_per_bone(desc).get(slot.bone)
    return parent if parent is not None and parent != slot.name else None


def slot_node_path(desc: CharacterDescriptor, slot_name: str) -> str:
    """The node path of a slot RELATIVE to its entity (``head/left_eye``,
    ``torso``) — the rig builder's nesting rule, stated once.

    >>> slot_node_path(CharacterDescriptor(name="m"), "left_eye")
    'head/left_eye'
    >>> slot_node_path(CharacterDescriptor(name="m"), "torso")
    'torso'
    """
    slot = _slot_named(desc, slot_name)
    if slot is None:
        raise KeyError(slot_name)
    parent = slot_parent(desc, slot)
    return f"{parent}/{slot_name}" if parent else slot_name


def suppressed_slots(desc: CharacterDescriptor) -> frozenset[str]:
    """Slots the rig builder never builds: with the face baked into the head
    art (``face_overlay=false``), every slot nested under the HEAD BONE's
    primary slot — keyed on the bone, not on a slot named "head".

    >>> sorted(suppressed_slots(CharacterDescriptor(name="m", face_overlay=False)))
    ['left_brow', 'left_eye', 'mouth', 'right_brow', 'right_eye']
    >>> suppressed_slots(CharacterDescriptor(name="m"))
    frozenset()
    """
    if desc.face_overlay:
        return frozenset()
    head_slot = primary_slot_per_bone(desc).get(HEAD_BONE)
    if head_slot is None:
        return frozenset()
    return frozenset(s.name for s in desc.slots if slot_parent(desc, s) == head_slot)


def active_skin(desc: CharacterDescriptor) -> Skin:
    """The skin the rig draws: ``default``, else the first declared, else empty."""
    return desc.skins.get("default") or next(iter(desc.skins.values()), Skin())


def drawn_attachment(
    desc: CharacterDescriptor, skin: Skin, slot: Slot
) -> tuple[str, Attachment] | None:
    """The ``(name, attachment)`` a slot draws by default, or ``None``."""
    available = skin.slots.get(slot.name) or {}
    if not available:
        return None
    name = slot.attachment if slot.attachment in available else next(iter(available))
    return name, available[name]


def art_exists_for(characters_store: Mapping, ref: str) -> Callable[[str], bool] | None:
    """``rel_path -> is the art on disk``, for a character in a filesystem
    store; ``None`` when the store has no root to look under (a dict, a
    fake) — a store that can answer nothing must assume presence, not absence,
    exactly as the rig builder's part probe does.
    """
    root = getattr(characters_store, "_root", None)
    if root is None:
        return None
    base = Path(root) / ref

    def exists(rel_path: str) -> bool:
        return (base / rel_path).is_file()

    return exists


# ----------------------------------------------------------------- resolution


#: Where a ``play`` resolves: the entity descriptor's own ``animations``…
DESCRIPTOR_SOURCE = "descriptor"
#: …or, for a name it does not declare, :data:`an.motion.PRESETS` (an#166).
PRESET_SOURCE = "preset"

#: Preset parameters an author may NOT pass through ``args``: the target is
#: the play's own, and the rest pose is read off the built scene.
RESERVED_PRESET_ARGS: frozenset[str] = frozenset({"target", "rest"})


def _presets() -> dict[str, Callable]:
    # Lazy: `an.motion` imports the IR, and the IR's validator imports this.
    from an.motion import PRESETS

    return PRESETS


def play_source(desc: CharacterDescriptor | None, animation: str) -> str:
    """Which library a ``play`` of ``animation`` resolves in —
    :data:`DESCRIPTOR_SOURCE` when ``desc`` declares it (the descriptor WINS a
    name a preset also has), else :data:`PRESET_SOURCE` when a motion preset
    has it. ``desc=None`` is an entity with no descriptor: presets only.

    Raises :class:`PlayResolutionError` naming BOTH vocabularies when neither
    has the name.
    """
    if desc is not None and animation in desc.animations:
        return DESCRIPTOR_SOURCE
    presets = _presets()
    if animation in presets:
        return PRESET_SOURCE
    if desc is None:
        problem = (
            f"no animation {animation!r}: the entity has no descriptor, so only "
            f"motion presets resolve, and none has that name "
            f"(presets: {sorted(presets)})"
        )
    else:
        problem = (
            f"no animation {animation!r}: the descriptor declares "
            f"{sorted(desc.animations)} and no motion preset has that name "
            f"(presets: {sorted(presets)})"
        )
    raise PlayResolutionError(animation, [problem])


def play_problems(
    desc: CharacterDescriptor | None,
    animation: str,
    *,
    art_exists: Callable[[str], bool] | None = None,
    args: Mapping[str, object] | None = None,
    duration: float | None = None,
    speed: float = 1.0,
    loop: bool | None = None,
) -> list[str]:
    """Every reason ``play(<entity>, animation, ...)`` cannot resolve — empty
    when it can. THE verdict ``an validate`` reports and the compiler raises
    on, for both sources (an#7, an#166).

    >>> play_problems(None, "hop", args={"heigth": 3})  # doctest: +ELLIPSIS
    ["motion preset 'hop' has no parameter 'heigth' (it takes: [...])"]
    >>> play_problems(None, "hop", loop=True)  # doctest: +ELLIPSIS
    ["motion preset 'hop' is a one-shot: `loop: true` ...
    """
    try:
        source = play_source(desc, animation)
    except PlayResolutionError as e:
        return list(e.problems)
    if source == PRESET_SOURCE:
        problems = preset_problems(
            animation, args=args, duration=duration, speed=speed, loop=loop
        )
        return problems or preset_swap_problems(
            desc, animation, args=args, art_exists=art_exists
        )
    problems: list[str] = []
    if args:
        problems.append(
            f"`args` {dict(args)!r} are motion-preset parameters, and "
            f"{animation!r} is the descriptor's own animation, which takes none "
            "(a descriptor animation wins over a preset of the same name)"
        )
    try:
        resolve_play(desc, animation, art_exists=art_exists)
    except PlayResolutionError as e:
        problems.extend(e.problems)
    return problems


def preset_problems(
    animation: str,
    *,
    args: Mapping[str, object] | None = None,
    duration: float | None = None,
    speed: float = 1.0,
    loop: bool | None = None,
) -> list[str]:
    """Why a ``play`` of the motion preset ``animation`` cannot expand.

    The parameters are checked by NAME against the preset's signature, then by
    building it (at the identity pose), so a value the preset itself refuses —
    ``cycles: 0``, a string height — is reported in the preset's own words.
    """
    import inspect

    preset = _presets()[animation]
    problems: list[str] = []
    args = dict(args or {})
    params = inspect.signature(preset).parameters
    accepted = sorted(
        n
        for n, p in params.items()
        if n not in RESERVED_PRESET_ARGS and p.kind is inspect.Parameter.KEYWORD_ONLY
    )
    for name in sorted(args):
        if name in RESERVED_PRESET_ARGS:
            problems.append(
                f"motion preset {animation!r}: {name!r} is not an argument — "
                + (
                    "the rest pose is read off the built scene"
                    if name == "rest"
                    else "the target is the play's own `target`"
                )
            )
        elif name not in accepted:
            problems.append(
                f"motion preset {animation!r} has no parameter {name!r} "
                f"(it takes: {accepted})"
            )
    if loop:
        problems.append(
            f"motion preset {animation!r} is a one-shot: `loop: true` is for "
            "descriptor animations — place the play again, or pass the "
            "preset's own count (`cycles`, `count`, `steps`) in `args`"
        )
    if duration is not None and speed != 1.0:
        problems.append(
            f"motion preset {animation!r}: give `duration` (stretch the move "
            "to that length) or `speed` (divide its length), not both"
        )
    if duration is not None and not duration > 0:
        problems.append(f"motion preset {animation!r}: duration must be > 0")
    if not speed > 0:
        problems.append(f"motion preset {animation!r}: speed must be > 0")
    if not problems:
        try:
            tree = preset("_", **args)
        except (TypeError, ValueError) as e:
            problems.append(f"motion preset {animation!r} refuses {args!r}: {e}")
        else:
            problems.extend(_easing_problems(animation, tree))
    return problems


def preset_swap_problems(
    desc: CharacterDescriptor | None,
    animation: str,
    *,
    args: Mapping[str, object] | None = None,
    art_exists: Callable[[str], bool] | None = None,
) -> list[str]:
    """Why the swap ``set`` s a motion preset emits cannot land on ``desc`` —
    ``turn`` swaps the character's ``view`` set (an#197), which a character
    made before views, a DiceBear head or a procedural rig does not declare.
    Checked here so ``an validate`` says it before the render does — including
    a key whose art is missing on a slot it swaps (``art_exists``, when the
    caller can tell), which the compiler drops and ``strict_assets`` refuses.

    >>> preset_swap_problems(None, "turn")  # doctest: +ELLIPSIS
    ["motion preset 'turn' swaps 'view' to 'back', but the entity has no descriptor..."]
    >>> preset_swap_problems(None, "hop")
    []
    """
    from an.base import TRANSFORM_PROPERTIES
    from an.ir.compose import flatten
    from an.ir.schema import SetAction

    tree = _presets()[animation]("_", **dict(args or {}))
    problems: list[str] = []
    for f in flatten(tree):
        leaf = f.action
        if not isinstance(leaf, SetAction) or leaf.property in TRANSFORM_PROPERTIES:
            continue
        what = f"motion preset {animation!r} swaps {leaf.property!r} to {leaf.value!r}"
        hint = (
            " — `an character new --offline` draws the views, and `an character "
            "add-views` adds them to a factory character made before them"
            if leaf.property == "view"
            else ""
        )
        if desc is None:
            problems.append(
                f"{what}, but the entity has no descriptor, so it declares no "
                f"swap sets{hint}"
            )
        elif leaf.property not in desc.asset_sets:
            problems.append(
                f"{what}, but the descriptor declares no {leaf.property!r} set "
                f"(it has: {sorted(desc.asset_sets)}){hint}"
            )
        elif leaf.value not in desc.asset_sets[leaf.property]:
            problems.append(
                f"{what}, which is not a key of its {leaf.property!r} set "
                f"(keys: {sorted(desc.asset_sets[leaf.property])})"
            )
        elif art_exists is not None:
            missing = swap_art_missing(desc, leaf.property, leaf.value, art_exists)
            if missing:
                problems.append(f"{what}, but its art is not on disk: {missing}")
    return problems


def swap_slots(
    desc: CharacterDescriptor,
    set_name: str,
    *,
    art_exists: Callable[[str], bool] | None = None,
) -> list[str]:
    """The slots a WHOLE-CHARACTER swap of ``set_name`` lands on (an#197): every
    built slot whose skin carries an attachment some key of the set names, and
    — when ``art_exists`` can tell — at least one of them resolves. That is the
    compiler's ``swap_capable_paths``: a slot with none of the set's art never
    receives the set, so the fan-out skips it.

    >>> from an.characters.schema import Skin
    >>> d = CharacterDescriptor(
    ...     name="m", asset_sets={"view": {"front": "a", "side": "b"}},
    ...     skins={"default": Skin(slots={"head": {"a": {"path": "h.svg"}},
    ...                                   "torso": {"b": {"path": "t.svg"}}})})
    >>> swap_slots(d, "view")
    ['head', 'torso']
    """
    names = set((desc.asset_sets.get(set_name) or {}).values())
    unbuilt = suppressed_slots(desc)
    return sorted(
        slot
        for slot, atts in active_skin(desc).slots.items()
        if slot not in unbuilt
        and any(
            art_exists is None or art_exists(atts[n].path) for n in names & set(atts)
        )
    )


def swap_art_missing(
    desc: CharacterDescriptor,
    set_name: str,
    key: str,
    art_exists: Callable[[str], bool],
) -> list[str]:
    """The art ``key`` of ``set_name`` is missing, on ANY slot it lands on.

    A whole-character swap lands on every slot the set projects onto
    (:func:`swap_slots`), and the compiler drops a slot whose art for the key
    did not resolve — so ``--strict-assets`` refuses the shot when one slot
    lacks it, even though another slot has it. A slot with none of the set's
    art, or one the rig never builds, receives no swap and is skipped, as the
    compiler skips it. "Some slot has the art" is the
    wrong question for an entity-level swap; this is the right one, shared by
    ``an validate`` and :func:`preset_swap_problems` (an#201).

    >>> from an.characters.schema import Skin
    >>> d = CharacterDescriptor(
    ...     name="m", asset_sets={"view": {"front": "f", "side": "s"}},
    ...     skins={"default": Skin(slots={
    ...         "head": {"f": {"path": "hf.svg"}, "s": {"path": "hs.svg"}},
    ...         "torso": {"s": {"path": "ts.svg"}}})})
    >>> swap_art_missing(d, "view", "side", lambda p: p != "hs.svg")
    ['hs.svg']
    >>> swap_art_missing(d, "view", "side", lambda p: p != "ts.svg")  # torso has no view art at all
    []
    """
    name = (desc.asset_sets.get(set_name) or {}).get(key)
    if name is None:
        return []
    slots = active_skin(desc).slots
    return sorted(
        slots[slot][name].path
        for slot in swap_slots(desc, set_name, art_exists=art_exists)
        if name in slots[slot] and not art_exists(slots[slot][name].path)
    )


def _easing_problems(animation: str, tree) -> list[str]:
    """An ``easing`` passed through ``args`` reaches the compiled keyframes
    verbatim, and the runtime throws on an unknown one mid-render — so check
    every tween's easing the way the evaluators will read it."""
    from an.adapters.cutout.easing import apply_easing
    from an.ir.compose import flatten
    from an.ir.schema import TweenAction

    for f in flatten(tree):
        if isinstance(f.action, TweenAction):
            try:
                apply_easing(f.action.easing, 0.5)
            except (ValueError, TypeError) as e:
                return [f"motion preset {animation!r}: easing {f.action.easing!r}: {e}"]
    return []


def preset_play_span(action) -> float:
    """How long a preset ``play`` runs, in seconds: its ``duration`` when set,
    else the preset's natural length divided by ``speed``. What a
    ``sequence`` advances by is :func:`play_extent`, which is this for a preset
    source.

    >>> from an.ir.schema import PlayAction
    >>> preset_play_span(PlayAction(target="a", animation="hop"))
    0.5
    >>> preset_play_span(PlayAction(target="a", animation="hop", speed=2.0))
    0.25
    """
    from an.ir.compose import duration_of

    if action.duration is not None:
        return float(action.duration)
    tree = _presets()[action.animation](action.target, **dict(action.args or {}))
    return duration_of(tree) / float(action.speed)


def play_extent(desc: CharacterDescriptor | None, action) -> float:
    """How long a ``play`` occupies inside a ``sequence``, in seconds — THE
    resolver ``flatten`` is given by the compiler and ``an validate`` (with the
    entity's ``desc``) and by default (``desc=None``: presets only).

    An explicit ``duration`` is its own extent. Otherwise the play's NATURAL
    length over ``speed``: a motion preset's (:func:`preset_play_span`), or a
    descriptor animation's ``duration``. A **looping** play (``loop`` true, or
    the animation's own) runs to the shot end and occupies ZERO: it has no
    natural length, and a sibling after it must not wait for the shot end. A
    play that cannot resolve occupies zero too — the same
    :func:`play_problems` verdict reports it, and this must never raise inside
    ``flatten``.

    >>> from an.ir.schema import PlayAction
    >>> play_extent(None, PlayAction(target="a", animation="hop", speed=2.0))
    0.25
    >>> play_extent(None, PlayAction(target="a", animation="hop", duration=3.0))
    3.0
    >>> play_extent(None, PlayAction(target="a", animation="nope"))
    0.0
    """
    if action.duration is not None:
        return float(action.duration)
    try:
        source = play_source(desc, action.animation)
    except PlayResolutionError:
        return 0.0
    if source == PRESET_SOURCE:
        try:
            return preset_play_span(action)
        except (TypeError, ValueError):
            return 0.0
    anim = desc.animations[action.animation]
    loop = action.loop if action.loop is not None else bool(anim.loop)
    if loop:
        return 0.0
    return float(anim.duration) / float(action.speed)


def play_extent_for(
    descriptor_of: Callable[[str], CharacterDescriptor | None],
) -> Callable[[object], float]:
    """A ``PlayAction -> seconds`` resolver (:func:`play_extent`) that reads
    each play's descriptor from ``descriptor_of(entity_id)``, the entity being
    the first segment of the play's target."""

    def extent(action) -> float:
        entity_id = (getattr(action, "target", "") or "").split("/", 1)[0]
        return play_extent(descriptor_of(entity_id), action)

    return extent


def preset_moved_node(action_target: str, animation: str, args=None) -> str:
    """The ONE node path a preset play moves — ``<target>/head`` for a ``nod``,
    the target itself for the rest. Read off the expansion rather than
    restated per preset, so a preset added later needs no entry here.

    >>> preset_moved_node("charlie", "nod"), preset_moved_node("charlie", "hop")
    ('charlie/head', 'charlie')
    """
    from an.ir.compose import flatten

    tree = _presets()[animation](action_target, **dict(args or {}))
    moved = sorted({f.action.target for f in flatten(tree)})
    if len(moved) != 1:  # every shipped preset moves one node; a new one must too
        raise PlayResolutionError(
            animation,
            [
                f"motion preset {animation!r} moves {moved}; a play needs exactly one node"
            ],
        )
    return moved[0]


def expand_preset_play(
    action,
    *,
    start: float,
    rest_of: Callable[[str], Mapping[str, float] | None],
) -> list:
    """A preset ``play`` as the flat tweens and settling ``set``s it stands
    for, at absolute times from ``start`` (an#166).

    ``rest_of(node_path)`` returns that node's built rest pose (``x``, ``y``,
    ``rotation``, ``scale_x``, ``scale_y``, ``alpha``), or ``None`` when the
    built scene carries no such node — then this raises naming it, which is
    what the runtime would otherwise do mid-render. ``duration`` stretches the
    move to that length; ``speed`` divides it. Assumes
    :func:`preset_problems` came back empty.

    >>> from an.ir.schema import PlayAction
    >>> flats = expand_preset_play(
    ...     PlayAction(target="a", animation="hop", args={"height": 10}),
    ...     start=1.0, rest_of=lambda p: {"y": 5.0})
    >>> [(round(f.start, 3), type(f.action).__name__, f.action.property) for f in flats]
    [(1.0, 'TweenAction', 'y'), (1.25, 'TweenAction', 'y'), (1.5, 'SetAction', 'y')]
    >>> flats[0].action.to_value
    -5.0
    """
    from an.ir.compose import FlatAction, duration_of, flatten
    from an.ir.schema import TweenAction

    preset = _presets()[action.animation]
    args = dict(action.args or {})
    node = preset_moved_node(action.target, action.animation, args)
    rest = rest_of(node)
    if rest is None:
        raise PlayResolutionError(
            action.animation,
            [
                f"motion preset {action.animation!r} on {action.target!r} moves "
                f"node {node!r}, which the built scene does not carry"
            ],
        )
    tree = preset(action.target, rest=rest, **args)
    natural = duration_of(tree)
    if action.duration is not None and natural > 0:
        scale = float(action.duration) / natural
    else:
        scale = 1.0 / float(action.speed)
    flats = flatten(tree, start=start)  # the macro's own time arithmetic, exactly
    if scale == 1.0:
        return flats
    out = []
    for f in flats:
        leaf = f.action
        if isinstance(leaf, TweenAction):
            leaf = leaf.model_copy(update={"duration": leaf.duration * scale})
        t0 = start + (f.start - start) * scale
        out.append(
            FlatAction(start=t0, end=t0 + (f.end - f.start) * scale, action=leaf)
        )
    return out


# --------------------------------------------------------- facing (an#203)

#: The preset whose START depends on what came before it on the timeline: a
#: turn opens from the side the character faces NOW, which only the timeline
#: knows.
TURN_PRESET = "turn"
#: Slack for "at or before" on the timeline: a turn chained straight after
#: another starts at the instant the first one settles.
_FACING_SLACK: float = 1e-9


@dataclass(frozen=True)
class Facing:
    """What an entity shows at one instant, read off a flat timeline.

    ``view`` is the key of its view set last set on the ENTITY (``None``: not
    set in this shot, so the rig's default — ``front`` on a factory
    character); ``direction`` is ``"right"``/``"left"`` from the sign of the
    last ``scale_x`` it was given (``None``: nothing set it, so its rest).
    """

    view: str | None = None
    direction: str | None = None


@dataclass(frozen=True)
class TurnInference:
    """One ``play`` of :data:`TURN_PRESET` and the state it starts from.

    ``index`` is the play's position in the flat list it was read from;
    ``declared`` is the ``from_direction`` the author passed (``None``: left
    to the timeline).
    """

    index: int
    start: float
    entity: str
    before: Facing
    declared: str | None = None

    @property
    def contradicted(self) -> bool:
        """The author's ``from_direction`` disagrees with the timeline — the
        turn would jump to the other side before it squashes."""
        return (
            self.declared is not None
            and self.before.direction is not None
            and self.declared != self.before.direction
        )


@dataclass(frozen=True)
class TurnResolution:
    """:func:`resolve_turns`' result: ``flats`` is the input with each turn's
    inferred ``from_direction`` filled in; ``turns`` says what each turn
    started from; ``events`` is the timeline with every preset play expanded,
    which :func:`facing_at` reads."""

    flats: list
    turns: list[TurnInference]
    events: list


def facing_at(events, entity: str, t: float, *, view_set: str = "view") -> Facing:
    """What ``entity`` shows at time ``t``: the latest ``view_set`` swap set
    on the entity and the sign of the latest ``scale_x`` it was given, at or
    before ``t`` (a tween counts from its END, when its value has landed; at
    one instant the one LATER in ``events`` wins — so pass them in authoring
    order, as :func:`resolve_turns` does).

    >>> from an.ir.compose import flatten, sequence
    >>> from an.motion import turn
    >>> flats = flatten(sequence(turn("ned", to="side", direction="left")))
    >>> facing_at(flats, "ned", 0.0), facing_at(flats, "ned", 1.0)
    (Facing(view=None, direction=None), Facing(view='side', direction='left'))
    """
    from an.ir.schema import SetAction, TweenAction

    view: str | None = None
    sx: float | None = None
    stamped = []
    for order, f in enumerate(events):
        a = f.action
        if getattr(a, "target", None) != entity:
            continue
        if isinstance(a, TweenAction) and a.property == "scale_x":
            stamped.append((f.start + float(a.duration), order, "scale_x", a.to_value))
        elif isinstance(a, SetAction) and a.property in ("scale_x", view_set):
            stamped.append((f.start, order, a.property, a.value))
    for time, _, prop, value in sorted(stamped, key=lambda e: (e[0], e[1])):
        if time > t + _FACING_SLACK:
            break
        if prop != "scale_x":
            view = value
            continue
        try:
            sx = float(value)
        except (TypeError, ValueError):
            continue  # a value the compiler refuses; validate reports it elsewhere
    direction = None if not sx else ("left" if sx < 0 else "right")
    return Facing(view=view, direction=direction)


def resolve_turns(
    flat_list,
    *,
    descriptor_of: Callable[[str], CharacterDescriptor | None],
    rest_of: Callable[[str], Mapping[str, float] | None],
) -> TurnResolution:
    """Fill in each turn's ``from_direction`` from the timeline before it
    (an#203): a ``play`` of ``turn`` on an entity that does not pass one
    opens from the side the latest earlier ``scale_x`` left the entity facing
    — so ``side`` (``direction: left``) then ``back`` is two plays, with no
    ``from_direction`` by hand. Turns are resolved in time order, each seeing
    the ones before it expanded. THE resolver the compiler expands with and
    ``an validate`` checks with.

    An explicit ``from_direction`` is kept — ``turns`` records it with the
    inferred state so ``an validate`` can say when the two disagree. A play
    that cannot resolve is left for :func:`play_problems` to report.

    >>> from an.ir.compose import flatten, sequence
    >>> from an.ir.schema import PlayAction
    >>> flats = flatten(sequence(
    ...     PlayAction(target="ned", animation="turn", args={"to": "side", "direction": "left"}),
    ...     PlayAction(target="ned", animation="turn", args={"to": "back"})))
    >>> res = resolve_turns(flats, descriptor_of=lambda e: None,
    ...                     rest_of=lambda p: {"scale_x": 1.0})
    >>> res.flats[1].action.args["from_direction"], res.turns[1].before
    ('left', Facing(view='side', direction='left'))
    """
    from an.ir.compose import FlatAction
    from an.ir.schema import PlayAction

    out = list(flat_list)
    # (authoring position, sub-step) -> flat: an expanded play's leaves sit
    # where the play was authored, so a tie at one instant goes to whatever
    # was authored later, as the compiler orders it.
    ordered = [
        ((i, 0), f)
        for i, f in enumerate(flat_list)
        if not isinstance(f.action, PlayAction)
    ]

    def events() -> list:
        return [f for _, f in sorted(ordered, key=lambda e: e[0])]

    plays = sorted(
        ((i, f) for i, f in enumerate(flat_list) if isinstance(f.action, PlayAction)),
        key=lambda p: (p[1].start, p[0]),
    )
    turns: list[TurnInference] = []
    for i, f in plays:
        action = f.action
        entity = (action.target or "").split("/", 1)[0]
        try:
            if play_source(descriptor_of(entity), action.animation) != PRESET_SOURCE:
                continue
        except PlayResolutionError:
            continue
        args = dict(action.args or {})
        if action.animation == TURN_PRESET and action.target == entity:
            from an.motion import DFLT_TURN_SET

            before = facing_at(
                events(),
                entity,
                f.start,
                view_set=str(args.get("view_set", DFLT_TURN_SET)),
            )
            declared = args.get("from_direction")
            turns.append(TurnInference(i, f.start, entity, before, declared))
            if declared is None and before.direction is not None:
                args["from_direction"] = before.direction
                action = action.model_copy(update={"args": args})
                out[i] = FlatAction(start=f.start, end=f.end, action=action)
        try:
            leaves = expand_preset_play(action, start=f.start, rest_of=rest_of)
        except (PlayResolutionError, TypeError, ValueError):
            continue  # play_problems says why; the facing just learns nothing
        ordered.extend(((i, n + 1), leaf) for n, leaf in enumerate(leaves))
    return TurnResolution(flats=out, turns=turns, events=events())


def resolve_play(
    desc: CharacterDescriptor,
    animation: str,
    *,
    art_exists: Callable[[str], bool] | None = None,
) -> ResolvedPlay:
    """Resolve ``animation`` of ``desc`` into renderer-ready tracks, or raise
    :class:`PlayResolutionError` listing every problem found.

    ``art_exists(rel_path)`` answers whether a skin attachment's art is on
    disk; pass ``None`` when the caller cannot know, and every declared
    attachment is assumed present (the rig builder's own rule for a store
    without a filesystem root).
    """
    anim = desc.animations.get(animation)
    if anim is None:
        raise PlayResolutionError(
            animation,
            [
                f"the descriptor declares no animation {animation!r} "
                f"(it has: {sorted(desc.animations)})"
            ],
        )
    ctx = _RigFacts.of(desc, art_exists)
    problems: list[str] = []
    tracks: list[ResolvedTrack] = []
    for track in anim.tracks:
        kind, _, rest = track.target.partition(":")
        name, _, prop = rest.partition(".")
        if kind == "bone":
            out = _resolve_bone_track(track, name, prop, ctx, problems)
        elif kind == "slot" and prop == "attachment":
            out = _resolve_slot_track(track, name, ctx, problems)
        else:
            problems.append(
                f"track {track.target!r} has an unsupported target "
                "(bone:<name>.<prop> or slot:<name>.attachment)"
            )
            out = None
        if out is not None:
            tracks.append(out)
    if problems:
        raise PlayResolutionError(animation, problems)
    return ResolvedPlay(animation=anim, tracks=tuple(tracks))


@dataclass(frozen=True)
class _RigFacts:
    """What the rig builder would build from ``desc`` — derived once per resolve."""

    desc: CharacterDescriptor
    skin: Skin
    primary: dict[str, str]
    suppressed: frozenset[str]
    art_exists: Callable[[str], bool] | None

    @classmethod
    def of(
        cls, desc: CharacterDescriptor, art_exists: Callable[[str], bool] | None
    ) -> "_RigFacts":
        return cls(
            desc=desc,
            skin=active_skin(desc),
            primary=primary_slot_per_bone(desc),
            suppressed=suppressed_slots(desc),
            art_exists=art_exists,
        )

    def has_art(self, attachment: Attachment) -> bool:
        return self.art_exists is None or self.art_exists(attachment.path)

    def unbuilt_reason(self, slot_name: str) -> str | None:
        """Why the rig builder would NOT build ``slot_name``'s node, or None."""
        slot = _slot_named(self.desc, slot_name)
        if slot is None:
            return (
                f"the descriptor declares no slot {slot_name!r} "
                f"(slots: {sorted(s.name for s in self.desc.slots)})"
            )
        if slot_name in self.suppressed:
            return (
                f"slot {slot_name!r} is suppressed: face_overlay=false bakes "
                "the face into the head art, so its node is never built"
            )
        drawn = drawn_attachment(self.desc, self.skin, slot)
        if drawn is None:
            return (
                f"slot {slot_name!r} has no attachment in the skin, so it draws nothing"
            )
        drawn_name, attachment = drawn
        if not self.has_art(attachment):
            return (
                f"slot {slot_name!r} draws nothing: its attachment "
                f"{drawn_name!r} art {attachment.path!r} is not on disk"
            )
        parent = slot_parent(self.desc, slot)
        if parent is not None:
            why = self.unbuilt_reason(parent)
            if why is not None:
                return f"slot {slot_name!r} nests under an unbuilt slot: {why}"
        return None


def _slot_named(desc: CharacterDescriptor, name: str) -> Slot | None:
    return next((s for s in desc.slots if s.name == name), None)


def _resolve_bone_track(
    track: AnimationTrack,
    bone: str,
    prop: str,
    ctx: _RigFacts,
    problems: list[str],
) -> BoneTrack | None:
    ok = True
    if prop not in BONE_TRACK_PROPERTIES:
        problems.append(
            f"track {track.target!r}: bone property {prop!r} is not animatable "
            f"(known: {sorted(BONE_TRACK_PROPERTIES)})"
        )
        ok = False
    slot = ctx.primary.get(bone)
    if slot is not None:
        why = ctx.unbuilt_reason(slot)
        if why is not None:
            problems.append(
                f"track {track.target!r}: bone {bone!r} animates its primary "
                f"slot {slot!r}, which is not built — {why}"
            )
            ok = False
    elif bone == ROOT_BONE:
        slot = None
    else:
        declared = {b.name for b in ctx.desc.bones}
        if bone in declared:
            owned = sorted(s.name for s in ctx.desc.slots if s.bone == bone)
            problems.append(
                f"track {track.target!r}: bone {bone!r} has no primary slot "
                f"(a slot named {bone!r}) whose node could carry it; its slots "
                f"are {owned} — a bone track moves the node of its same-named "
                "slot, or the entity container for 'root'"
            )
        else:
            problems.append(
                f"track {track.target!r}: the descriptor declares no bone "
                f"{bone!r} (bones: {sorted(declared)})"
            )
        ok = False
    if track.type in ("step", "linear"):
        for ft, fv in track.frames:
            if isinstance(fv, bool) or not isinstance(fv, (int, float)):
                problems.append(
                    f"track {track.target!r}: frame at t={ft} has value {fv!r}; "
                    "a bone track's values must be numbers"
                )
                ok = False
                break
    if not ok:
        return None
    runtime_prop, unit = BONE_TRACK_PROPERTIES[prop]
    return BoneTrack(
        track=track,
        slot=slot,
        property=runtime_prop,
        unit=unit,
        rig_scaled=prop in RIG_SCALED_PROPERTIES,
    )


def _resolve_slot_track(
    track: AnimationTrack, slot_name: str, ctx: _RigFacts, problems: list[str]
) -> SlotTrack | None:
    if track.type not in ("step", "linear"):
        problems.append(
            f"track {track.target!r}: an attachment track must be step or "
            f"linear frames naming attachments, not {track.type!r}"
        )
        return None
    why = ctx.unbuilt_reason(slot_name)
    if why is not None:
        problems.append(f"track {track.target!r}: {why}")
        return None
    inventory = ctx.skin.slots.get(slot_name) or {}
    wanted: list[str] = []
    for ft, attachment in track.frames:
        if not isinstance(attachment, str):
            problems.append(
                f"track {track.target!r}: frame at t={ft} has value "
                f"{attachment!r}; an attachment track's values name attachments"
            )
            return None
        if attachment not in wanted:
            wanted.append(attachment)
    if not wanted:
        problems.append(f"track {track.target!r} has no frames")
        return None
    # Sets that name EVERY wanted attachment — the projection the rig builder
    # stamps on this slot's node covers the whole track, or the track does
    # not resolve to that set at all.
    sets_naming = {
        name: sorted(k for k, att in key_map.items() if att in wanted)
        for name, key_map in ctx.desc.asset_sets.items()
    }
    covering = sorted(
        name
        for name, key_map in ctx.desc.asset_sets.items()
        if all(att in key_map.values() for att in wanted)
    )
    for attachment in wanted:
        if attachment not in inventory:
            problems.append(
                f"track {track.target!r}: names attachment {attachment!r}, which "
                f"the skin's slot {slot_name!r} does not carry "
                f"(it has: {sorted(inventory)})"
            )
            return None
        if not ctx.has_art(inventory[attachment]):
            named_by = sorted(n for n, keys in sets_naming.items() if keys)
            problems.append(
                f"track {track.target!r}: attachment {attachment!r} of slot "
                f"{slot_name!r} is declared (by set(s) {named_by}) but its art "
                f"{inventory[attachment].path!r} is not on disk"
            )
            return None
    on_slot = sorted(
        name
        for name, key_map in ctx.desc.asset_sets.items()
        if any(att in inventory for att in key_map.values())
    )
    if not covering:
        problems.append(
            f"track {track.target!r}: no declared asset set maps a key to "
            f"every attachment it names ({wanted}); sets projecting onto "
            f"{slot_name!r}: {on_slot}"
        )
        return None
    if len(covering) > 1:
        problems.append(
            f"track {track.target!r}: attachments {wanted} are named by more "
            f"than one asset set ({covering}); a track resolves to exactly one "
            "set — give each set its own attachment names, or split the track"
        )
        return None
    (set_name,) = covering
    key_map = ctx.desc.asset_sets[set_name]
    key_of = {att: min(k for k, a in key_map.items() if a == att) for att in wanted}
    frames = tuple((float(ft), key_of[att]) for ft, att in track.frames)
    return SlotTrack(track=track, slot=slot_name, set_name=set_name, frames=frames)


def sine_sample_times(duration: float, fps: int) -> list[float]:
    """Frame-rate sample times for a sine track, ALWAYS ending at ``duration``.

    ``ceil`` rather than ``round``: with ``round``, a 0.18 s track at 24 fps
    got samples up to 0.1667 s and then held that value to the clip end, so
    the cycle-closing sample (equal to the first) was never emitted and the
    clip wrapped with a jump (an#7 review).

    >>> sine_sample_times(0.19, 24)[-2:]
    [0.16666666666666666, 0.19]
    >>> len(sine_sample_times(6.0, 24))
    145
    """
    duration = max(0.0, float(duration))
    n = max(1, math.ceil(duration * fps - 1e-9))
    return [min(duration, i / fps) for i in range(n + 1)]


def sampled_deviations(
    track: AnimationTrack, duration: float, fps: int
) -> list[tuple[float, float]]:
    """``(time, deviation)`` pairs for a sine bone track at the frame rate —
    :func:`an.characters.idle.evaluate_track`'s formula, sampled, so the
    descriptor's own evaluator stays the one definition of a sine track."""
    return [
        (t, float(evaluate_track(track, t, duration)))
        for t in sine_sample_times(duration, fps)
    ]


__all__ = [
    "BONE_TRACK_PROPERTIES",
    "BoneTrack",
    "DESCRIPTOR_SOURCE",
    "Facing",
    "HEAD_BONE",
    "PRESET_SOURCE",
    "PlayResolutionError",
    "RESERVED_PRESET_ARGS",
    "RIG_SCALED_PROPERTIES",
    "ROOT_BONE",
    "ResolvedPlay",
    "SlotTrack",
    "TURN_PRESET",
    "TurnInference",
    "TurnResolution",
    "active_skin",
    "art_exists_for",
    "drawn_attachment",
    "expand_preset_play",
    "facing_at",
    "play_problems",
    "play_source",
    "preset_moved_node",
    "preset_play_span",
    "preset_problems",
    "primary_slot_per_bone",
    "resolve_play",
    "resolve_turns",
    "sampled_deviations",
    "sine_sample_times",
    "slot_node_path",
    "slot_parent",
    "suppressed_slots",
]
