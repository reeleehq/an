"""The cut-out genre's vocabulary entries: motion presets, expression presets, IR-field notes.

ADR 0003's first slice, the genre's share (the core's is
:mod:`an.semantic.seeds`). Each entry is built FROM the table that already
defines the thing — :data:`an.motion.PRESETS` (with
:data:`an.motion.PRESET_VERSIONS`), :data:`an.expression.presets.PRESETS`, the
expression axes — never restated, so a preset added there is an entry here
with nothing else to edit. The genre declares them through
:data:`an.genres.cutout.CUTOUT`'s ``vocabulary`` field; importing this module
registers nothing.

>>> walk = next(e for e in MOTION_PRESET_ENTRIES if e.term == "walk")
>>> walk.id, walk.aspects, "gait" in walk.params["properties"]
('motion.walk', ('locomotion',), True)
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping
from typing import Any

from an.semantic.entries import Entry
from an.semantic.seeds import schema_of_callable

__all__ = [
    "CUTOUT_FIELDS",
    "CUTOUT_VOCABULARY",
    "EXPRESSION_PRESET_ENTRIES",
    "EXPRESSION_PRESET_VERSIONS",
    "MOTION_PRESET_ENTRIES",
    "PRESET_ASPECTS",
]

#: Parameters of a motion preset that are the compiler's, never an author's.
_COMPILER_PARAMS: tuple[str, ...] = ("target", "rest", "parts")

#: Which aspect a preset resolves when played (ADR 0002): a ``walk`` picks a
#: locomotion method; ``speech_pulse`` IS the speech aspect's last link.
PRESET_ASPECTS: dict[str, tuple[str, ...]] = {
    "walk": ("locomotion",),
    "speech_pulse": ("speech",),
}

#: Each expression preset's vocabulary version (ADR 0003). Bump one in the same
#: change that moves its axes or its mouth form.
EXPRESSION_PRESET_VERSIONS: dict[str, str] = {}


def _first_sentence(doc: str | None) -> str:
    text = " ".join((inspect.cleandoc(doc or "")).split("\n\n")[0].split())
    text = text.replace("``", "`")  # reST literals read as markdown ones
    text = re.sub(r"\s*\(an#\d+\)", "", text)  # issue references are noise to a reader
    head, dot, _ = text.partition(". ")
    return (head + "." if dot else text).rstrip()


def _motion_preset_entries() -> tuple[Entry, ...]:
    from an.motion import PRESET_VERSIONS, PRESETS

    def expand_with(fn):
        def expand(params: Mapping[str, Any], context: Any):
            ctx = dict(context or {})
            return fn(ctx.pop("target"), **ctx, **dict(params))

        return expand

    return tuple(
        Entry(
            f"motion.{name}",
            "motion_preset",
            version=PRESET_VERSIONS.get(name, "1"),
            name=name,
            title=name.replace("_", " "),
            description=_first_sentence(fn.__doc__),
            params=schema_of_callable(fn, skip=_COMPILER_PARAMS),
            examples=({"kind": "play", "target": "ned", "animation": name},),
            aspects=PRESET_ASPECTS.get(name, ()),
            expand=expand_with(fn),
        )
        for name, fn in PRESETS.items()
    )


def _expression_preset_entries() -> tuple[Entry, ...]:
    from an.expression.presets import PRESETS

    def describe(p) -> str:
        if not p.axes:
            return "the rest face: every axis at its neutral value"
        moves = ", ".join(f"{k} {v:+g}" for k, v in sorted(p.axes.items()))
        form = f"; mouth form {p.mouth_form!r}" if p.mouth_form else ""
        return f"expression-sheet preset: {moves}{form}"

    return tuple(
        Entry(
            f"expression.{name}",
            "expression_preset",
            version=EXPRESSION_PRESET_VERSIONS.get(name, "1"),
            name=name,
            description=describe(p),
            usage=f"FACS cross-reference {p.anchor}" if p.anchor else "",
            examples=(
                {"kind": "expression", "target": "ned", "preset": name},
                f"[{name}] on a scene.md dialogue line",
            ),
        )
        for name, p in PRESETS.items()
    )


def _cutout_fields() -> tuple[Entry, ...]:
    from an.expression.axes import AXES

    axes = ", ".join(
        f"{n} [{a.lo:g}, {a.hi:g}]" for n, a in AXES.items()
    )
    return (
        Entry(
            "field.shot.actions.swap_set",
            "field",
            name="shot.actions.swap_set",
            description="a set action that swaps a drawing (replacement animation)",
            usage=(
                "A set/tween property may also be the name of a swap set the target "
                "character's descriptor declares in asset_sets (e.g. 'viseme', "
                "'eyelid', 'hands'), used with a 'set' action whose 'value' is one "
                "of that set's declared KEYS (replacement animation). The compiler "
                "refuses any other name with the declared sets listed. Never invent "
                "a set or a key."
            ),
        ),
        Entry(
            "field.shot.actions.play",
            "field",
            name="shot.actions.play",
            description="play a named animation of the target character, or a motion preset",
            usage=(
                "A 'play' action ({kind: play, target: <entity>, animation: <name>, "
                "[duration], [speed], [loop], [args]}) plays one of the target "
                "character's descriptor animations ('idle_breath', 'blink', or any it "
                "declares) or, for a name the descriptor does not declare, a motion "
                "preset (listed below) with 'args' as its parameters (e.g. "
                "{'height': 30}); a name in neither fails validation — never invent "
                "one. 'point' targets the arm node. A 'walk' picks its gait from the "
                "character's structure (its locomotion method, below) unless 'gait' "
                "is given."
            ),
            levels=frozenset({"a", "b-name"}),
            aspects=("locomotion",),
        ),
        Entry(
            "field.shot.actions.expression",
            "field",
            name="shot.actions.expression",
            description="hold a facial expression on a character",
            usage=(
                "An 'expression' action ({kind: expression, target: <entity>, "
                "preset: <name>, [axes: {axis: value}], [intensity], [duration], "
                "[blend]}) holds a facial expression on a character: brows, eyelids, "
                "and the mouth's set for any dialogue under it. 'preset' is an "
                "expression preset (listed below) — an unknown preset fails "
                f"validation. Axes are offsets within their ranges: {axes}. "
                "'duration' omitted = to the shot end. A character whose descriptor "
                "says face_overlay: false cannot take one."
            ),
            levels=frozenset({"a", "b-name"}),
        ),
        Entry(
            "field.shot.dialogue.emotion",
            "field",
            name="shot.dialogue.emotion",
            description="the mood a line is said in",
            usage=(
                "A dialogue line's 'emotion' is an expression preset name ([happy] "
                "on a scene.md line): it sets the face for the line and the voice's "
                "mood. When a line's wording changes, update its emotion if the mood "
                "changed too."
            ),
            levels=frozenset({"a", "b-name"}),
            aspects=("speech",),  # a spoken line resolves the speech aspect
        ),
    )


MOTION_PRESET_ENTRIES: tuple[Entry, ...] = _motion_preset_entries()
EXPRESSION_PRESET_ENTRIES: tuple[Entry, ...] = _expression_preset_entries()
CUTOUT_FIELDS: tuple[Entry, ...] = _cutout_fields()
#: Everything this genre contributes to the vocabulary except its methods
#: (:mod:`an.characters.methods`).
CUTOUT_VOCABULARY: tuple[Entry, ...] = (
    *CUTOUT_FIELDS,
    *MOTION_PRESET_ENTRIES,
    *EXPRESSION_PRESET_ENTRIES,
)
