"""Affordances for the library: the capability registry, re-exported from :mod:`an.capabilities`.

P5 seeded ADR 0002's ``affordances(asset)`` here; P7 moved the tables and the
matcher to the core registry, :mod:`an.capabilities`, and this module now
re-exports the SAME objects (``ANALYSERS is an.capabilities.ANALYSERS``), so the
library's facets and ``find(…, near=True)`` and the compiler's method choice
are one derivation and one matcher, never two.

The character analyser is the cut-out genre's: it registers through
:data:`an.genres.cutout.CUTOUT` (its ``capabilities`` and ``analysers``
fields) when the genres load, which the library's entry points do
(:func:`an.library.api.publish`, :func:`an.library.api.find`).

>>> import an.capabilities
>>> ANALYSERS is an.capabilities.ANALYSERS and CAPABILITIES is an.capabilities.CAPABILITIES
True
>>> afford = {"swap.view": {"keys": ["front", "side"]}, "limbs.legs": {}}
>>> matches(afford, "swap.view:side"), matches(afford, "swap.view:back"), matches(afford, "limbs.legs")
(True, False, True)
"""

from __future__ import annotations

from an.capabilities import (
    ANALYSERS,
    CAPABILITIES,
    KEY_SEP,
    KEYS_PARAM,
    Analyser,
    Capability,
    analyse,
    capability_of,
    current_affordances,
    matches,
    missing,
    register_analyser,
    register_capability,
    remedy_for,
)

__all__ = [
    "Analyser",
    "Capability",
    "CAPABILITIES",
    "ANALYSERS",
    "KEY_SEP",
    "KEYS_PARAM",
    "analyse",
    "capability_of",
    "current_affordances",
    "matches",
    "missing",
    "register_analyser",
    "register_capability",
    "remedy_for",
]
