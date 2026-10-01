"""The ``an iterate`` system prompt, generated from the vocabulary registry.

ADR 0003 decision 6: the prompt is one of the three surfaces generated from the
registry, never written by hand. :func:`vocabulary_prompt` renders the IR's
fields and every registered name — action and entity kinds, motion and
expression presets, camera moves, easings, methods by aspect — each with its
one-sentence description and its params. The *protocol* around it (the patch
operations, the path syntax, the editing rules) is ``an iterate``'s own and is
passed in as ``preamble`` and ``postamble``.

>>> text = vocabulary_prompt()
>>> "push_in" in text and "tween" in text and "linear" in text
True
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from an.semantic.entries import Entry, Method
from an.semantic.registry import aspects, entries, methods_of

__all__ = ["iterate_prompt", "vocabulary_prompt"]

#: The order the vocabulary kinds are listed in, with the heading each gets.
KIND_HEADINGS: tuple[tuple[str, str], ...] = (
    ("action", "Action kinds (an action's `kind`)"),
    ("entity", "Entity kinds (an entity's `kind`)"),
    ("motion_preset", "Motion presets (`play` by name; `args` are the parameters shown)"),
    ("expression_preset", "Expression presets (an `expression`'s `preset`, a dialogue line's `emotion`)"),
    ("camera_move", "Camera moves (`camera: {move: …}`)"),
    ("easing", "Easings (a tween's `easing`)"),
)

#: Params that are noise in a prompt line (and never an author's to set).
_HIDDEN_PARAMS: frozenset[str] = frozenset()


def _params_line(e: Entry, *, limit: int = 12) -> str:
    props: dict[str, Any] = dict((e.params or {}).get("properties") or {})
    shown = []
    for name, spec in props.items():
        if name in _HIDDEN_PARAMS:
            continue
        if isinstance(spec, dict) and "default" in spec:
            shown.append(f"{name}={spec['default']!r}")
        else:
            shown.append(name)
    if not shown:
        return ""
    more = f", … ({len(shown) - limit} more)" if len(shown) > limit else ""
    return "(" + ", ".join(shown[:limit]) + more + ")"


def _entry_line(e: Entry, *, params: bool) -> str:
    line = f"    - {e.term}"
    if params:
        line += _params_line(e)
    if e.description:
        line += f": {e.description}"
    if e.version != "1":
        line += f" [v{e.version}]"
    return line


def _section(kind: str, heading: str) -> list[str]:
    found = entries(kind=kind)
    if kind == "easing":  # only what a tween may name today (seeds.ir_easing_names)
        from an.semantic.seeds import ir_easing_names

        found = tuple(e for e in found if e.term in ir_easing_names())
    if not found:
        return []
    params = kind == "motion_preset"
    return [f"  {heading}:"] + [_entry_line(e, params=params) for e in found]


def _methods_section() -> list[str]:
    out: list[str] = []
    for a in aspects():
        methods = [m for m in methods_of(a.name) if isinstance(m, Method)]
        if not methods:
            continue
        out.append(
            f"    - {a.name}: {a.description} Default chain: "
            + " → ".join(a.chain)
            + "."
        )
        for m in methods:
            needs = ", ".join(str(r) for r in m.requires) or "nothing"
            spelled = f" (spelled {m.term!r})" if m.term != m.id else ""
            out.append(f"        · {m.id}{spelled} — requires {needs}: {m.description}")
    if not out:
        return []
    return [
        "  Methods, by aspect (ADR 0002). A method that does not apply falls back "
        "down its aspect's chain, recorded; never request one the asset lacks the "
        "structure for without saying so:"
    ] + out


def vocabulary_prompt(*, kinds: Iterable[tuple[str, str]] = KIND_HEADINGS) -> str:
    """The IR fields and every registered name, as prompt text."""
    lines = ["The IR shape (relevant fields):"]
    for f in entries(kind="field"):
        lines.append(f"  - {f.usage or f.description}")
    lines += [
        "",
        "Vocabulary — every name below is registered and versioned; a name "
        "outside these lists fails validation, so never invent one:",
    ]
    for kind, heading in kinds:
        lines += _section(kind, heading)
    lines += _methods_section()
    return "\n".join(lines)


def iterate_prompt(*, preamble: str, postamble: str) -> str:
    """``preamble`` + the generated vocabulary + ``postamble`` (the ``an iterate`` protocol)."""
    return "\n\n".join(p.strip("\n") for p in (preamble, vocabulary_prompt(), postamble))
