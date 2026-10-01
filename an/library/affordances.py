"""Affordances: what an asset can do, derived from its descriptor and the art present.

This is the seed of ADR 0002's ``affordances(asset) → set[Capability]``, built
so its registry (P7) adopts it rather than writing a second derivation:

- an **analyser** is registered per asset kind (:func:`register_analyser`) with a
  version. It reads the descriptor document and the art present — a mapping of
  each file's relative path to its ``ContentRef`` (so a later analyser can read
  bytes through the blob store; today's tests membership only) —
  never a hand-typed list beside them (ADR 0002 decision 2) — and returns
  ``{capability: params}``. A capability that is absent is not afforded;
- a **capability** is a dotted, registered name (:func:`register_capability`)
  with a description and a **remedy** (what would add it, and the command when
  one exists), because ``find(…, near=True)`` must say how to close a near miss;
- **params** are the capability's parameters. The one convention every query
  relies on: ``keys`` lists the discrete values it affords, so ``swap.view:side``
  asks for ``swap.view`` with ``side`` among its keys. ``overrides`` lists the
  declared descriptor fields (``rest_view``, …) the
  derivation used instead of deriving — ADR 0002's "the derivation reports which
  overrides it used".

The library snapshots an analyser's output on each version with the analyser's
version (``analysers: {kind: version}``); a reader whose analyser is newer
recomputes rather than trusting the snapshot (:func:`current_affordances`).

Capability names are persisted identifiers: once a version stores one, it is
renamed only through this registry, never in place.

>>> afford = {"swap.view": {"keys": ["front", "side"]}, "limbs.legs": {}}
>>> matches(afford, "swap.view:side"), matches(afford, "swap.view:back"), matches(afford, "limbs.legs")
(True, False, True)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "Analyser",
    "Capability",
    "CAPABILITIES",
    "ANALYSERS",
    "KEY_SEP",
    "analyse",
    "capability_of",
    "current_affordances",
    "matches",
    "missing",
    "register_analyser",
    "register_capability",
    "remedy_for",
]

#: Separates a capability from one of its keys in a query (``swap.view:side``).
KEY_SEP: str = ":"
#: The params entry listing the discrete values a capability affords.
KEYS_PARAM: str = "keys"

#: The art an analyser sees: ``{relative path: ContentRef JSON}``. ``in`` and
#: iteration give the paths; the refs reach the bytes through the blob store.
Art = Mapping[str, Any]
#: ``(doc, art) -> {capability: params}``.
Derivation = Callable[[Mapping[str, Any], Art], dict[str, dict[str, Any]]]


@dataclass(frozen=True)
class Capability:
    """A registered capability name, what it means, and how to add it."""

    name: str
    description: str
    remedy: str


@dataclass(frozen=True)
class Analyser:
    """The derivation of one asset kind's affordances, versioned."""

    kind: str
    version: str
    derive: Derivation


#: Registered capabilities, by name. Genre packages add theirs on import.
CAPABILITIES: dict[str, Capability] = {}
#: Registered analysers, by asset kind.
ANALYSERS: dict[str, Analyser] = {}


def register_capability(name: str, *, description: str, remedy: str) -> Capability:
    """Register (or re-register) a capability. Returns it."""
    cap = Capability(name, description, remedy)
    CAPABILITIES[name] = cap
    return cap


def register_analyser(kind: str, *, version: str) -> Callable[[Derivation], Derivation]:
    """Decorator: register ``derive`` as the analyser of ``kind`` at ``version``.

    Bump ``version`` whenever the derivation's output can change for the same
    input: versions published under the old one are then recomputed on read.
    """

    def deco(derive: Derivation) -> Derivation:
        ANALYSERS[kind] = Analyser(kind, version, derive)
        return derive

    return deco


def analyse(
    kind: str, doc: Mapping[str, Any], art: Art
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """``(affordances, analysers)`` of one asset: its capabilities and the analyser versions used.

    A kind with no registered analyser affords nothing *derived* and records no
    analyser — an honest empty answer, not a guess.
    """
    analyser = ANALYSERS.get(kind)
    if analyser is None:
        return {}, {}
    return analyser.derive(doc, dict(art)), {kind: analyser.version}


def current_affordances(
    kind: str,
    doc: Mapping[str, Any],
    art: Art,
    *,
    stored: Mapping[str, Any] | None,
    stored_analysers: Mapping[str, str] | None,
) -> dict[str, dict[str, Any]]:
    """The stored snapshot when its analyser version is current, else a fresh derivation.

    Affordances are derived data, so recomputing them is always safe; trusting a
    snapshot made by an older analyser is what would make a facet lie.
    """
    analyser = ANALYSERS.get(kind)
    if analyser is None:
        return dict(stored or {})
    if stored is not None and (stored_analysers or {}).get(kind) == analyser.version:
        return dict(stored)
    return analyser.derive(doc, dict(art))


def capability_of(query: str) -> tuple[str, str | None]:
    """``(capability, key)`` of a query term.

    >>> capability_of("swap.view:side"), capability_of("limbs.legs")
    (('swap.view', 'side'), ('limbs.legs', None))
    """
    name, sep, key = query.partition(KEY_SEP)
    return name, (key if sep else None)


def matches(affordances: Mapping[str, Mapping[str, Any]], query: str) -> bool:
    """Whether ``affordances`` satisfy one query term (``cap`` or ``cap:key``)."""
    name, key = capability_of(query)
    if name not in affordances:
        return False
    if key is None:
        return True
    return key in (affordances[name] or {}).get(KEYS_PARAM, ())


def missing(
    affordances: Mapping[str, Mapping[str, Any]], queries: Iterable[str]
) -> list[str]:
    """The query terms ``affordances`` do not satisfy, in the order asked."""
    return [q for q in queries if not matches(affordances, q)]


def remedy_for(query: str) -> str:
    """What would add the capability a query term asks for.

    >>> remedy_for("no.such.capability")
    'no registered capability no.such.capability; see vocabulary() for the known names'
    """
    name, key = capability_of(query)
    cap = CAPABILITIES.get(name)
    if cap is None:
        return f"no registered capability {name}; see vocabulary() for the known names"
    return cap.remedy if key is None else f"{cap.remedy} (needed key: {key})"
