"""Timeline: tracks of placed clips with absolute times — the compiled evaluation form.

A `Timeline` is a flat description of *what plays when*: tracks of
:class:`PlacedClip`, each a :class:`~an.timing.clip.Clip` at an absolute start,
with a duration override, a speed and recorded blend ramps. It is the level the
stage runtime evaluates (``runtime.js::evaluateTimeline`` is a port of
:func:`evaluate_timeline`) and the level the contract's golden vectors exercise
(``compiled.schema.json``). Authoring composition trees (``an.ir.compose``) are
flattened into it by a compiler.

``blend_in`` and ``blend_out`` ramps are recorded but **not applied** to pose
values: the timeline produces the raw pose.

>>> from an.timing.channel import Channel, Keyframe
>>> from an.timing.clip import Clip
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> clip = Clip("walk", duration=1.0, channels=[ch])
>>> tl = Timeline(duration=2.0, tracks=[Track("a", clips=[PlacedClip(clip, start_time=0.5)])])
>>> evaluate_timeline(tl, 1.0)[("a", "x")]
5.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from an.timing.channel import Channel, Keyframe
from an.timing.clip import Clip, KindOf, LoopMode, Pose
from an.timing.clip import evaluate as _evaluate_clip
from an.timing.spaces import STAGE_NODE, SWAP_WRITE_GROUP, SpaceLike, space_resolver

__all__ = [
    "PlacedClip",
    "Track",
    "Timeline",
    "SWAP_WRITE_GROUP",
    "write_group",
    "evaluate_timeline",
    "clip_from_json",
    "timeline_from_compiled",
]


@dataclass(slots=True)
class PlacedClip:
    """A clip placed at an absolute time on a track."""

    clip: Clip
    start_time: float = 0.0
    duration: float | None = None  # override; None = clip's natural duration
    speed: float = 1.0
    blend_in: float = 0.0
    blend_out: float = 0.0

    def __post_init__(self) -> None:
        if self.speed <= 0:
            raise ValueError(f"PlacedClip speed must be > 0; got {self.speed}")
        if self.blend_in < 0 or self.blend_out < 0:
            raise ValueError("blend_in/out must be non-negative")

    @property
    def effective_duration(self) -> float:
        """Duration this clip occupies on the timeline (after speed scaling)."""
        natural = self.duration if self.duration is not None else self.clip.duration
        return natural / self.speed

    @property
    def end_time(self) -> float:
        return self.start_time + self.effective_duration


@dataclass(slots=True)
class Track:
    """A sequence of placed clips that share a common purpose / target prefix.

    ``target_root`` is informational metadata for downstream tools (the JS
    runtime can use it to scope rendering); evaluation does not filter by it.
    """

    target_root: str = ""
    clips: list[PlacedClip] = field(default_factory=list)


@dataclass(slots=True)
class Timeline:
    """A duration + ordered list of tracks. The canonical playback structure."""

    duration: float
    tracks: list[Track] = field(default_factory=list)


def write_group(prop: str) -> str:
    """What ``prop`` writes on a STAGE node (the ``stage.node`` space's groups).

    Two keys in one group set the same thing, so only the more recently written
    can be showing: every swap set on a node swaps the one visual it carries
    (``viseme`` and ``viseme@happy`` both set the mouth's texture, an#88), and
    ``rotation_rad`` is ``rotation``. Every other runtime property
    (:data:`an.base.TRANSFORM_PROPERTIES`, the runtime's own switch) writes only
    itself.

    >>> write_group("x"), write_group("rotation_rad"), write_group("viseme@happy")
    ('x', 'rotation', '<swap>')
    """
    return STAGE_NODE.write_group(prop)


def _stage_group(_target: str, prop: str) -> str:
    return STAGE_NODE.write_group(prop)


def evaluate_timeline(
    timeline: Timeline, t: float, *, space: SpaceLike | None = None
) -> Pose:
    """Evaluate ``timeline`` at time ``t``, merging poses across tracks/clips.

    The result is a PURE function of ``t`` (an#185): what a node shows at ``t``
    never depends on which instants were evaluated before it. Per
    ``(target, property)``:

    - **Active** — some clip writing it is playing at ``t`` (inclusive end:
      a clip at ``[s, e]`` is active at ``t == e`` too, so the final frame of
      "play this from 0 to 1 s" is visible at 1.0). Later wins: track order,
      then clip order within a track. Written at ``t``.
    - **Held** — no clip writing it is playing, but one has ended: the value
      the clip reached AT ITS END holds. The latest end wins; a tie goes to
      the later clip, the same "later wins" as above. Written at that end.
    - **At rest** — nothing writing it has started yet. The key is ABSENT from
      the pose, and its value is the node's own (the entity's rest state;
      ``runtime.js`` restores what it built).

    Keys that write the same thing on one node (a write group: the swap sets of
    one visual, ``rotation``/``rotation_rad``) keep only the most recently
    WRITTEN — an ended ``viseme@happy`` span does not outlive the ``viseme``
    track that took the mouth back.

    ``space`` says what each property is (:mod:`an.timing.spaces`): one space, a
    registered space's name, or a ``target -> space`` resolver. Its field kinds
    interpolate and its write groups resolve. ``None`` is the stage runtime's
    rule, which ``runtime.js`` implements: interpolation by value type, the
    ``stage.node`` write groups.

    Forward-order rendering used to show the value at the clip's last SAMPLED
    frame instead (the runtime kept whatever it last applied). The two agree
    whenever a clip ends on the frame grid — true of every golden-corpus clip
    — and differ when it ends between frames: a 0.37 s tween to 10 at 24 fps
    used to stop at 9.80 and now lands on 10, as authored. That landing is
    deliberate (it is the bug the motion presets' settling ``set`` patched one
    preset at a time), and it is what makes the pose independent of the grid.
    Also deliberate: a clip shorter than a frame that no frame lands in now
    leaves its end value, and a held descendant tint stays on top of an
    ancestor's later tint (the more specific target wins, as it always did
    while both played).

    ``runtime.js::evaluateTimeline`` is a port of this function and
    ``tests/test_pure_pose.py`` holds the two to it.

    >>> from an.timing.channel import Channel, Keyframe
    >>> from an.timing.clip import Clip
    >>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
    >>> tl = Timeline(2.0, [Track("a", [PlacedClip(Clip("m", 1.0, [ch]), 0.5)])])
    >>> evaluate_timeline(tl, 0.0)  # not started: at rest, so absent
    {}
    >>> evaluate_timeline(tl, 1.0)[("a", "x")]  # active
    5.0
    >>> evaluate_timeline(tl, 1.75)[("a", "x")]  # ended: its end value holds
    10.0
    """
    kind_of: KindOf | None
    if space is None:
        kind_of, group_of = None, _stage_group
    else:
        resolve = space_resolver(space)

        def kind_of(target: str, prop: str):
            return resolve(target).kind_of(prop)

        def group_of(target: str, prop: str) -> str:
            return resolve(target).write_group(prop)

    written: dict[tuple[str, str], tuple[float, Any]] = {}  # key -> (when, value)
    held: dict[tuple[str, str], tuple[float, Any]] = {}
    for track in timeline.tracks:
        for placed in track.clips:
            end = placed.end_time
            if placed.start_time <= t <= end:
                local_t = (t - placed.start_time) * placed.speed
                for key, value in _evaluate_clip(
                    placed.clip, local_t, kind_of=kind_of
                ).items():
                    written[key] = (t, value)
            elif t > end:
                end_pose = _evaluate_clip(
                    placed.clip,
                    (end - placed.start_time) * placed.speed,
                    kind_of=kind_of,
                )
                for key, value in end_pose.items():
                    if key not in held or end >= held[key][0]:
                        held[key] = (end, value)
    for key, entry in held.items():
        written.setdefault(key, entry)
    latest: dict[tuple[str, str], float] = {}
    for (target, prop), (when, _) in written.items():
        group = (target, group_of(target, prop))
        latest[group] = max(latest.get(group, when), when)
    return {
        key: value
        for key, (when, value) in written.items()
        if when >= latest[(key[0], group_of(*key))]
    }


# --- reading the compiled document ---------------------------------------------


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """``obj[name]`` for a mapping (a JSON document), else ``obj.name`` (a model)."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def clip_from_json(anim: Any, *, name: str | None = None) -> Clip:
    """One compiled animation (``compiled.schema.json``'s ``animation``) as a :class:`Clip`.

    Accepts the JSON mapping or any object with the same attributes (the stage's
    ``AnimationClipJSON``). Two fields are carried rather than defaulted, and
    both have cost a bug: ``loop_mode`` (without it every loop evaluated as
    ``once`` — an#7) and a list-valued ``easing``, which is a cubic-bezier
    control quadruple and must stay a tuple for ``Keyframe``. The stage compiler
    reads a from-less tween's start through this too (an#212), so it evaluates
    exactly what the runtime will.
    """
    return Clip(
        _get(anim, "name") if name is None else name,
        duration=_get(anim, "duration"),
        loop_mode=LoopMode(_get(anim, "loop_mode", LoopMode.ONCE.value)),
        channels=[
            Channel(
                _get(ch, "target"),
                _get(ch, "property"),
                [
                    Keyframe(
                        _get(k, "time"),
                        _get(k, "value"),
                        tuple(e) if isinstance(e := _get(k, "easing"), list) else e,
                    )
                    for k in _get(ch, "keyframes", ())
                ],
            )
            for ch in _get(anim, "channels", ())
        ],
    )


def timeline_from_compiled(doc: Any) -> Timeline:
    """The compiled document's ``timeline``/``animations`` as an evaluable `Timeline`.

    ``doc`` is the JSON mapping of ``compiled.schema.json`` or any object with
    the same attributes (the stage's ``CutoutSceneJSON``). This is the Python
    side of the parity contract: ``evaluate_timeline`` over what it returns is
    the executable spec ``runtime.js`` is tested against.

    ``target_root`` and the blend ramps are carried although nothing reads them
    yet: a reader that quietly drops a field it was handed is a lossy "rebuilds
    the evaluable form".

    >>> doc = {"timeline": {"duration": 1.0, "tracks": [{"clips": [
    ...     {"animation_id": "m", "start_time": 0.0}]}]},
    ...     "animations": {"m": {"duration": 1.0, "channels": [{"target": "a",
    ...     "property": "x", "keyframes": [{"time": 0.0, "value": 0.0},
    ...     {"time": 1.0, "value": 4.0}]}]}}}
    >>> evaluate_timeline(timeline_from_compiled(doc), 0.25)
    {('a', 'x'): 1.0}
    """
    animations = _get(doc, "animations", {}) or {}
    clips = {aid: clip_from_json(a, name=aid) for aid, a in animations.items()}
    tl = _get(doc, "timeline")
    return Timeline(
        duration=_get(tl, "duration"),
        tracks=[
            Track(
                _get(t, "target_root", ""),
                [
                    PlacedClip(
                        clips[_get(p, "animation_id")],
                        _get(p, "start_time", 0.0),
                        _get(p, "duration"),
                        _get(p, "speed", 1.0),
                        _get(p, "blend_in", 0.0),
                        _get(p, "blend_out", 0.0),
                    )
                    for p in _get(t, "clips", ())
                ],
            )
            for t in _get(tl, "tracks", ())
        ],
    )
