"""The timing kernel: what is on screen at time ``t``, as a pure function.

The heart of the core (core study §3, layer K; ADR 0001 decisions 10-11). Every
genre that can answer "what is the value of this property at time t" does it the
same way: **addressed** properties (:mod:`~an.timing.address`), each of a
declared **field kind** (:mod:`~an.timing.kinds`) chosen by its entity kind's
**property space** (:mod:`~an.timing.spaces`), keyed over time with **easing**
(:mod:`~an.timing.easing`), flattened to absolute times
(:mod:`~an.timing.flat`), compiled to tracks of placed clips of channels
(:mod:`~an.timing.channel`, :mod:`~an.timing.clip`, :mod:`~an.timing.timeline`)
and evaluated by ``evaluate_timeline(timeline, t)`` — sparse: a property nothing
has started writing is absent, and the entity's rest state supplies it.

The kernel is a **cross-language contract** before it is code: five JSON files
in ``an/data/timing/`` generated from these registries (:mod:`~an.timing.contract`),
which a second implementation (TypeScript) asserts. ``runtime.js`` — the stage
engine's evaluator — is a bit-exact port of this package's value-typed rule, and
its parity tests hold it there.

The frame clock is `an`'s: frame ``k`` at ``k / fps``, ``frame_count = max(1,
round(duration * fps))`` (:mod:`an.frame_clock`).

>>> from an.timing import Channel, Keyframe, evaluate_channel, get_space
>>> ch = Channel("charlie", "x", [Keyframe(0.0, 0.0, "ease_in_out"), Keyframe(1.0, 10.0)])
>>> evaluate_channel(ch, 0.25, kind=get_space("stage.node").kind_of("x"))
1.25
"""

from an.timing.address import Address, AddressError, format_address, parse_address
from an.timing.channel import Channel, Keyframe, check_channel
from an.timing.channel import evaluate as evaluate_channel
from an.timing.clip import Clip, LoopMode, Pose, merge_poses, wrap_time
from an.timing.clip import evaluate as evaluate_clip
from an.timing.easing import (
    EasingEntry,
    UnknownEasingError,
    apply_easing,
    easing_entries,
    easing_entry,
    register_easing,
    resolve_easing,
)
from an.timing.kinds import (
    AngleKind,
    ColorKind,
    DiscreteKind,
    FieldKind,
    FieldKindError,
    NumberKind,
    OrbitKind,
    QuaternionKind,
    Segment,
    VectorKind,
    kind_from_spec,
    kind_names,
    register_kind,
)
from an.timing.spaces import (
    STAGE_CAMERA,
    STAGE_NODE,
    FieldDecl,
    PropertySpace,
    SpaceError,
    get_space,
    register_space,
    space_from_json,
    space_names,
)
from an.timing.timeline import (
    PlacedClip,
    Timeline,
    Track,
    clip_from_json,
    evaluate_timeline,
    timeline_from_compiled,
)

__all__ = [
    "Address",
    "AddressError",
    "format_address",
    "parse_address",
    "Channel",
    "Keyframe",
    "check_channel",
    "evaluate_channel",
    "Clip",
    "LoopMode",
    "Pose",
    "merge_poses",
    "wrap_time",
    "evaluate_clip",
    "EasingEntry",
    "UnknownEasingError",
    "apply_easing",
    "easing_entries",
    "easing_entry",
    "register_easing",
    "resolve_easing",
    "AngleKind",
    "ColorKind",
    "DiscreteKind",
    "FieldKind",
    "FieldKindError",
    "NumberKind",
    "OrbitKind",
    "QuaternionKind",
    "Segment",
    "VectorKind",
    "kind_from_spec",
    "kind_names",
    "register_kind",
    "STAGE_CAMERA",
    "STAGE_NODE",
    "FieldDecl",
    "PropertySpace",
    "SpaceError",
    "get_space",
    "register_space",
    "space_from_json",
    "space_names",
    "PlacedClip",
    "Timeline",
    "Track",
    "clip_from_json",
    "evaluate_timeline",
    "timeline_from_compiled",
]
