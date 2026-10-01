"""The cut-out genre's methods and aspects, and their compile-time resolution (ADR 0002).

The first two aspects of ADR 0002's first slice, as registry data:

=============  ==============================================  =====================  ==========
aspect         method (spelled)                                requires               chain
=============  ==============================================  =====================  ==========
locomotion     ``loco.legged_cycle`` (``legs``)                ``limbs.legs``         1st
locomotion     ``loco.hem_sway`` (``hem``)                     ``limbs.legs``         by request
locomotion     ``loco.rock`` (``rock``)                        nothing                last link
speech         ``speech.mouth_chart`` (``mouth_chart``)        ``face.mouth``         1st
speech         ``speech.pose_only`` (``pulse``)                nothing                last link
=============  ==============================================  =====================  ==========

**Locomotion is today's walk/gait chain, moved, not changed** (ADR 0002
decision 8: the gate is byte-identical output). A walk's ``gait`` arg is the
author's request, the descriptor's ``gait`` a declared override (reported as
such); with neither, the chain picks ``legs`` when the character affords a leg
pair and ``rock`` when it does not — exactly what :func:`an.motion.walk` did on
its own. What is new is that the choice is the registry's, made once, and a
requested gait the rig cannot honour (``hem`` on a legless blob) is a
**recorded substitution**: a warning, fatal under ``--strict-assets``.

**Speech gains a requirement-free last link.** A character whose face is baked
into its art (``face_overlay: false``) used to speak with a frozen mouth; it now
pulses its head on each syllable (:func:`an.motion.speech_pulse`, parametrised:
``strength``, ``part``, ``attack``, ``release``; ``strength: 0`` is a mime).

The asset profile the compiler resolves against is the character analyser's
(``an.capabilities.affordances``), fed what the compiler actually has: the
descriptor and the art its store holds, or — for a rig drawn from ``parts`` or
the placeholder — the parts the builder built. Characters only: other entity
kinds have no analyser yet, and keep the preset's own rig lookup.

Importing this module registers nothing: :data:`an.genres.cutout.CUTOUT` lists
:data:`CUTOUT_METHODS` and :data:`CUTOUT_ASPECTS`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from an.semantic.entries import Aspect, Method
from an.semantic.seeds import schema_of_callable

__all__ = [
    "CUTOUT_ASPECTS",
    "CUTOUT_METHODS",
    "LOCOMOTION",
    "SPEECH",
    "compile_profile",
    "resolve_walk_gait",
    "speech_default_actions",
    "substitution_record",
    "syllable_beats",
]

#: The aspect names (persisted in substitution records).
LOCOMOTION: str = "locomotion"
SPEECH: str = "speech"

#: The entity kind whose assets have an analyser, and so resolve on the registry.
CHARACTER_KIND: str = "character"

#: Walk parameters each locomotion method reads (its params; the rest are the
#: walk's own — where to, how many steps).
_LEGGED_PARAMS: tuple[str, ...] = ("stride", "lift", "arm_swing", "bob")
_HEM_PARAMS: tuple[str, ...] = ("hem_tilt", "rock", "bob", "stride", "arm_swing")
_ROCK_PARAMS: tuple[str, ...] = ("rock", "bob", "arm_swing")
#: Rhubarb's closed shapes: a syllable starts where the mouth opens out of one.
CLOSED_VISEMES: frozenset[str] = frozenset({"A", "X"})
#: Pulses closer than this are one syllable.
DFLT_MIN_BEAT_GAP_S: float = 0.18


def _walk_params(names: Iterable[str]) -> dict[str, Any]:
    from an.motion import walk

    full = schema_of_callable(walk, skip=("target", "rest", "parts"))["properties"]
    return {"type": "object", "properties": {n: full[n] for n in names if n in full}}


def _walk_expand(gait: str) -> Callable[[Mapping[str, Any], Any], Any]:
    def expand(params: Mapping[str, Any], context: Any):
        from an.motion import walk

        ctx = dict(context or {})
        return walk(ctx.pop("target"), gait=gait, **ctx, **dict(params))

    return expand


def _pulse_expand(params: Mapping[str, Any], context: Any):
    from an.motion import speech_pulse

    ctx = dict(context or {})
    return speech_pulse(ctx.pop("target"), **ctx, **dict(params))


def _pulse_params() -> dict[str, Any]:
    from an.motion import speech_pulse

    return schema_of_callable(speech_pulse, skip=("target", "rest", "beats"))


_LEGS_REMEDY = (
    "split the legs into two slots named leg_l/leg_r, each with its art, "
    "pivoted at the hip (an-art-package skill; `an character new` builds them)"
)

LOCO_LEGGED = Method(
    "loco.legged_cycle",
    aspect=LOCOMOTION,
    name="legs",
    title="legged walk cycle",
    description=(
        "a legged walk cycle: in profile the legs swing about the hip in "
        "opposition, facing the camera the stepping leg lifts; the arms swing "
        "against the legs"
    ),
    params=_walk_params(_LEGGED_PARAMS),
    requires=("limbs.legs",),
    remedies={"limbs.legs": _LEGS_REMEDY},
    examples=({"kind": "play", "target": "ned", "animation": "walk", "args": {"gait": "legs"}},),
    expand=_walk_expand("legs"),
)
LOCO_HEM = Method(
    "loco.hem_sway",
    aspect=LOCOMOTION,
    name="hem",
    title="hem sway",
    description=(
        "a robe figure's walk: the leg slots are the two halves of the hem, which "
        "tilt in turn about the hip while the body sways and bobs"
    ),
    params=_walk_params(_HEM_PARAMS),
    requires=("limbs.legs",),
    remedies={
        "limbs.legs": (
            "carve the robe's hem into two halves on slots leg_l/leg_r, pivoted at "
            "the hip, and declare `gait: hem` in character.json"
        )
    },
    examples=({"kind": "play", "target": "ned", "animation": "walk", "args": {"gait": "hem"}},),
    expand=_walk_expand("hem"),
)
LOCO_ROCK = Method(
    "loco.rock",
    aspect=LOCOMOTION,
    name="rock",
    title="rock and bob",
    description=(
        "no leg moves: the body rocks side to side and bobs once per step while "
        "it travels (a blob, a sack, anything drawable)"
    ),
    params=_walk_params(_ROCK_PARAMS),
    examples=({"kind": "play", "target": "ned", "animation": "walk", "args": {"gait": "rock"}},),
    expand=_walk_expand("rock"),
)
SPEECH_CHART = Method(
    "speech.mouth_chart",
    aspect=SPEECH,
    name="mouth_chart",
    title="mouth chart lip-sync",
    description=(
        "lip-sync on the character's mouth chart: the line's visemes swap the "
        "mouth drawings (the nine Rhubarb shapes, or the character's own set)"
    ),
    requires=("face.mouth",),
    remedies={
        "face.mouth": (
            "give the character an overlay mouth: a `mouth` slot with the viseme "
            "set's drawings (`an character mouths <dir>`) and face_overlay: true"
        )
    },
)
SPEECH_PULSE = Method(
    "speech.pose_only",
    aspect=SPEECH,
    name="pulse",
    title="speech pulse",
    description=(
        "no lip-sync: the head (or the body) pulses on each syllable, so a "
        "baked face or a mime still reads as speaking"
    ),
    params=_pulse_params(),
    examples=("a character with face_overlay: false speaks",),
    expand=_pulse_expand,
)

#: The genre's methods, as vocabulary entries (kind ``method``).
CUTOUT_METHODS: tuple[Method, ...] = (
    LOCO_LEGGED,
    LOCO_HEM,
    LOCO_ROCK,
    SPEECH_CHART,
    SPEECH_PULSE,
)
#: The genre's aspects: each chain ends in a method that requires nothing.
CUTOUT_ASPECTS: tuple[Aspect, ...] = (
    Aspect(
        LOCOMOTION,
        chain=(LOCO_LEGGED.id, LOCO_ROCK.id),
        description="how a character travels when it walks.",
    ),
    Aspect(
        SPEECH,
        chain=(SPEECH_CHART.id, SPEECH_PULSE.id),
        description="how a character shows that it is speaking.",
    ),
)


# -----------------------------------------------------------------------------
# Compile-time resolution
# -----------------------------------------------------------------------------


def compile_profile(
    descriptor: Any | None,
    *,
    built_parts: Iterable[str] = (),
    art_exists: Callable[[str], bool] | None = None,
) -> dict[str, dict[str, Any]]:
    """The character's profile, from what the compiler has: the analyser, fed honestly.

    ``descriptor`` is the migrated ``CharacterDescriptor`` (or ``None`` for a
    rig drawn from ``parts`` / the placeholder); ``art_exists(rel_path)`` the
    store's probe (``None``: the store cannot say, so every declared drawing
    counts — the rig builder's own rule); ``built_parts`` the part names the
    builder built under the entity (for a non-descriptor rig, they ARE its
    parts document).
    """
    from an.capabilities import affordances

    if descriptor is None:
        parts = sorted({p.split("/", 1)[0] for p in built_parts})
        return affordances({"parts": parts}, {}, kind=CHARACTER_KIND)
    art = {
        att.path: True
        for skin in descriptor.skins.values()
        for attachments in skin.slots.values()
        for att in attachments.values()
        if art_exists is None or art_exists(att.path)
    }
    return affordances(descriptor, art, kind=CHARACTER_KIND)


def resolve_walk_gait(
    entity: str,
    *,
    args: Mapping[str, Any],
    descriptor: Any | None,
    profile: Mapping[str, Mapping[str, Any]],
    policy: Any = None,
):
    """``(gait, resolution)`` of a walk on ``entity``: the locomotion method's spelling.

    The request is the walk's ``gait`` arg, else the descriptor's declared
    ``gait`` (an override of the derivation, and reported as one). An explicit
    ``legs`` arg names the limbs itself: a non-empty pair affords legs whatever
    the derivation says, ``()`` affords none.

    >>> gait, r = resolve_walk_gait("blob", args={"gait": "hem"}, descriptor=None, profile={})
    >>> gait, r.substitution.reason, r.substitution.missing
    ('rock', 'missing', ('limbs.legs',))
    """
    from an.semantic import resolve

    profile = dict(profile)
    legs = args.get("legs")
    if legs is not None:
        if legs:
            profile["limbs.legs"] = {"slots": list(legs), "overrides": ["legs arg"]}
        else:
            profile.pop("limbs.legs", None)
    requested = args.get("gait") or getattr(descriptor, "gait", None)
    r = resolve(LOCOMOTION, profile, requested=requested, policy=policy, entity=entity)
    return r.method.term, r


def substitution_record(sub, *, entity_ref: str | None = None) -> dict[str, Any]:
    """A :class:`~an.capabilities.Substitution` as an ``asset_resolution`` entry.

    The compiled document's record generalised (ADR 0002 decision 6):
    ``kind: method``, ``store`` the aspect, ``ref`` what was asked for,
    ``resolved`` what was used, ``fallback`` whether ``--strict-assets`` makes
    it fatal.
    """
    return {
        "id": sub.entity,
        "kind": "method",
        "store": sub.aspect,
        "ref": sub.requested or "",
        "resolved": sub.chosen,
        "fallback": sub.fatal,
        "detail": sub.sentence(),
    }


def syllable_beats(line, *, min_gap_s: float = DFLT_MIN_BEAT_GAP_S) -> list[float]:
    """Syllable onsets of a dialogue line, in seconds from its start.

    From the line's viseme track (a syllable starts where the mouth opens out
    of a closed shape), else its word timings (one beat per word), else one
    beat at its start. Beats closer than ``min_gap_s`` merge.
    """
    times: list[float] = []
    track = getattr(line, "viseme_track", None)
    if track is not None and track.keyframes:
        closed = True
        for kf in sorted(track.keyframes, key=lambda k: float(k.time)):
            shape = str(kf.viseme).upper()
            if shape in CLOSED_VISEMES:
                closed = True
            elif closed:
                times.append(float(kf.time))
                closed = False
    elif getattr(line, "word_timings", None):
        times = [float(w.start) for w in line.word_timings]
    else:
        times = [0.0]
    end = float(line.duration) if line.duration is not None else float("inf")
    out: list[float] = []
    for t in sorted(times):
        if t < 0 or t >= end:
            continue
        if out and t - out[-1] < min_gap_s:
            continue
        out.append(round(t, 6))
    return out or [0.0]


def speech_default_actions(
    shot,
    *,
    is_character: Callable[[str], bool],
    profile_of: Callable[[str], Mapping[str, Mapping[str, Any]]],
    has_part: Callable[[str], bool],
    record: Callable[[Any], None] | None = None,
    policy: Any = None,
) -> list:
    """The actions the speech aspect adds to ``shot``: one pulse per line it resolves to.

    For each timed dialogue line whose speaker is a character in the shot, the
    speech aspect is resolved on the speaker's profile; where it is
    ``speech.pose_only``, a ``play`` of ``speech_pulse`` is placed at the line's
    start on the syllables. ``speech.mouth_chart`` adds nothing here (the
    viseme pass draws it). Substitutions go to ``record``.
    """
    from an.ir.compose import delay, play, sequence
    from an.semantic import resolve

    out = []
    for line in shot.dialogue or ():
        speaker = line.speaker
        if line.start is None or line.duration is None or not is_character(speaker):
            continue
        r = resolve(SPEECH, profile_of(speaker), policy=policy, entity=speaker)
        if r.substitution is not None and record is not None:
            record(r.substitution)
        if r.method.id != SPEECH_PULSE.id:
            continue
        args = {k: v for k, v in r.args.items() if k != "part"}
        part = r.args.get("part", "head")
        args["part"] = part if part and has_part(f"{speaker}/{part}") else ""
        args["beats"] = syllable_beats(line)
        pulse = play(speaker, "speech_pulse", args=args)
        out.append(sequence(delay(float(line.start)), pulse) if line.start else pulse)
    return out
