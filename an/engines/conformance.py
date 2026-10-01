"""Conformance of a TIME-driven engine against the timing kernel's golden vectors.

A time-driven engine evaluates the compiled channels itself (core study §2.7):
``runtime.js`` does, in a browser. Its pictures are only comparable with any
other engine's if the STATE it evaluated at ``t`` is the kernel's, so a
time-driven session exposes ``state(t)`` -- the read-back -- and this module
holds it to ``an/data/timing/timing_vectors.json``, the contract ``an.timing``
and ``previz`` both assert (ADR 0001 decision 10): numbers within the file's
tolerance, everything else exact, every sample of every case of the session's
property space.

The engine supplies how to load a vector's document; the check is the core's.

>>> cases = vector_cases(space="stage.node")
>>> len(cases) >= 10 and all(c["space"] == "stage.node" for c in cases)
True
>>> readback_mismatches(lambda t: {}, {"name": "n", "samples": [{"t": 0.0, "state": {}}]})
[]
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

__all__ = [
    "VECTORS_RESOURCE",
    "as_contract_state",
    "conformance_report",
    "readback_mismatches",
    "vector_cases",
]

#: Where the vectors ship: ``(package, path inside it)`` for :mod:`importlib.resources`.
VECTORS_RESOURCE: tuple[str, str] = ("an.data", "timing/timing_vectors.json")


def vector_cases(*, space: str | None = None) -> list[dict[str, Any]]:
    """The golden cases, optionally only those of one property space."""
    from importlib.resources import files

    package, name = VECTORS_RESOURCE
    doc = json.loads(files(package).joinpath(name).read_text(encoding="utf-8"))
    return [c for c in doc["cases"] if space is None or c.get("space") == space]


def as_contract_state(state: Mapping[Any, Any]) -> dict[str, Any]:
    """A state in the vectors' spelling: ``"target:property"`` keys.

    Accepts the kernel's pose keys (``(target, property)`` tuples) and the
    runtime's (``"target::property"``).

    >>> as_contract_state({("a", "x"): 1.0, "b::y": 2})
    {'a:x': 1.0, 'b:y': 2}
    """
    out = {}
    for key, value in state.items():
        if isinstance(key, tuple):
            key = f"{key[0]}:{key[1]}"
        else:
            key = str(key).replace("::", ":", 1)
        out[key] = value
    return out


def readback_mismatches(
    state_at: Callable[[float], Mapping[Any, Any]],
    case: Mapping[str, Any],
) -> list[tuple[str, float, Any, Any]]:
    """``(case, t, expected, got)`` for every sample whose read-back differs.

    ``state_at`` is a loaded session's ``state`` (or anything with its shape).
    Compared with the contract's own rule (:func:`an.timing.contract.values_close`).
    """
    from an.timing.contract import values_close

    out = []
    for sample in case["samples"]:
        got = as_contract_state(state_at(sample["t"]))
        if not values_close(sample["state"], got):
            out.append((case["name"], sample["t"], sample["state"], got))
    return out


def conformance_report(
    open_case: Callable[[Mapping[str, Any]], Any],
    cases: Iterable[Mapping[str, Any]],
) -> list[tuple[str, float, Any, Any]]:
    """Every mismatch over ``cases``; ``open_case(case)`` is a context manager
    yielding a session loaded with the case's document."""
    mismatches = []
    for case in cases:
        with open_case(case) as session:
            mismatches += readback_mismatches(session.state, case)
    return mismatches
