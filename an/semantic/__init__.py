"""The semantic layer: one versioned vocabulary registry, methods, aspects and the matcher.

ADR 0003 (the structured ↔ semantic spectrum) and ADR 0002 (capability-based
applicability). Defined once, in the core, for every genre (design principle 3):

- **the vocabulary** — every name a document may spell, as an :class:`Entry`
  (id, version, kind, title, description, params as JSON Schema with
  defaults, examples, requires, accepted levels, expand): action and entity
  kinds, easings, camera moves and IR fields from the core
  (:mod:`an.semantic.seeds`); motion and expression presets, methods and
  aspects from the genres (:class:`an.genres.Genre`'s ``vocabulary`` and
  ``aspects``);
- **methods and aspects** — a :class:`Method` is an entry of kind ``method``
  realising an :class:`Aspect`, whose default chain ends in a method that
  requires nothing or in the recorded :data:`NOOP`;
- **the queries** — :func:`applicable`, :func:`why_not` and :func:`resolve`
  (with a :class:`Policy`), all calls to the one matcher
  :func:`an.capabilities.missing`;
- **the generated surfaces** — the ``an iterate`` prompt
  (:mod:`an.semantic.prompt`), the skill's vocabulary section
  (:mod:`an.semantic.docs`), the MCP surface (:mod:`an.mcp`), and the shot's
  vocabulary digest for the compile key (:mod:`an.semantic.digest`).

Nothing here imports ``an.ir`` at module level, and nothing below the IR ever
calls an LLM.

>>> from an.semantic import entry, vocabulary
>>> entry("action.tween").kind
'action'
>>> any(e["id"] == "easing.ease_in_out" for e in vocabulary())
True
"""

from __future__ import annotations

from typing import Any

from an.capabilities import CAPABILITIES
from an.semantic.entries import (
    ANY_ASPECT,
    LEVELS,
    NOOP,
    NOOP_ID,
    Aspect,
    Choice,
    Entry,
    Method,
    Policy,
    VocabularyError,
)
from an.semantic.matcher import Missing, Resolution, applicable, resolve, why_not
from an.semantic.registry import (
    UnknownEntryError,
    aspect,
    aspect_names,
    aspects,
    entries,
    entry,
    lookup,
    methods_of,
    owner_of,
    register_aspect,
    register_entry,
)
from an.semantic import seeds as _seeds  # noqa: F401 — the core's vocabulary

__all__ = [
    "ANY_ASPECT",
    "Aspect",
    "Choice",
    "Entry",
    "LEVELS",
    "Method",
    "Missing",
    "NOOP",
    "NOOP_ID",
    "Policy",
    "Resolution",
    "UnknownEntryError",
    "VocabularyError",
    "applicable",
    "aspect",
    "aspect_names",
    "aspects",
    "check_registry",
    "entries",
    "entry",
    "lookup",
    "methods_of",
    "owner_of",
    "register_aspect",
    "register_entry",
    "resolve",
    "vocabulary",
    "why_not",
]


def vocabulary(*, kind: str | None = None, owner: str | None = None) -> list[dict[str, Any]]:
    """Every entry as data (what the MCP surface returns), filtered by ``kind``/``owner``."""
    return [e.to_json() for e in entries(kind=kind, owner=owner)]


def check_registry(*, owner: str | None = None, capabilities: bool = True) -> list[str]:
    """The problems with the registered aspects and methods (empty: sound).

    ADR 0002 decision 5 as a check: every aspect's chain names methods of that
    aspect, and its last link requires nothing or is the recorded :data:`NOOP`;
    one spelling is one entry; and (``capabilities``) every requirement names a
    registered capability. ``owner`` limits it to one genre's aspects and
    entries. :func:`an.genres.register_genre` runs the chain checks per genre;
    :func:`an.genres.load` runs the capability check once every genre is in, so
    a genre needing another's capability does not depend on load order.
    """
    from an.semantic.registry import duplicates

    problems: list[str] = [] if owner is not None else duplicates()
    for a in aspects():
        if owner is not None and owner_of_aspect(a.name) != owner:
            continue
        for mid in a.chain:
            if mid == NOOP_ID:
                continue
            try:
                m = entry(mid)
            except UnknownEntryError:
                problems.append(f"aspect {a.name!r}: chain names {mid!r}, which is not registered")
                continue
            if not isinstance(m, Method) or m.aspect not in (a.name, ANY_ASPECT):
                problems.append(f"aspect {a.name!r}: {mid!r} is not a method of it")
        last = a.chain[-1]
        if last != NOOP_ID:
            try:
                m = entry(last)
            except UnknownEntryError:
                continue
            if getattr(m, "requires", ()):
                problems.append(
                    f"aspect {a.name!r}: its chain ends in {last!r}, which requires "
                    f"{[str(r) for r in m.requires]} — the last link must require "
                    "nothing, or be the recorded no-op"
                )
    for e in entries(owner=owner) if capabilities else ():
        for req in e.requires:
            for cap in req.capabilities():
                if cap not in CAPABILITIES:
                    problems.append(
                        f"{e.kind} {e.id!r} requires {str(req)!r}, but {cap!r} is not "
                        "a registered capability"
                    )
    return problems


def owner_of_aspect(name: str) -> str | None:
    from an.semantic.registry import _T

    return _T.aspect_owners.get(name)
