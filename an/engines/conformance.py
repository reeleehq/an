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
    "case_document",
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


def case_document(case: Mapping[str, Any]) -> dict[str, Any]:
    """The case's document, carrying its property space the way a compiled
    document does (an#287): ``meta.entity_spaces`` names the space for every
    entity the case animates and ``meta.spaces`` defines it, so an engine that
    reads only the DOCUMENT (``runtime.js`` has no registry) evaluates the case
    in the case's space. A case in the default space is returned as it is.

    >>> case = {"space": {"name": "inline", "fields": []}, "document": {
    ...     "timeline": {"duration": 1.0, "tracks": []}, "animations": {"m": {
    ...     "duration": 1.0, "channels": [{"target": "view/a", "property": "x",
    ...     "keyframes": [{"time": 0.0, "value": 0}]}]}}}}
    >>> meta = case_document(case)["meta"]
    >>> meta["entity_spaces"], meta["spaces"]["inline"]["fields"]
    ({'view': 'inline'}, [])
    >>> "meta" in case_document({"space": "stage.node", "document": case["document"]})
    False
    """
    import copy

    from an.timing import spaces

    doc = copy.deepcopy(dict(case["document"]))
    space = case.get("space")
    if space is None or space == spaces.DFLT_TIMELINE_SPACE:
        return doc
    definition = (
        spaces.get_space(space).to_json() if isinstance(space, str) else dict(space)
    )
    name = definition.get("name", "inline")
    entities = sorted(
        {
            ch["target"].split("/", 1)[0]
            for anim in doc.get("animations", {}).values()
            for ch in anim.get("channels", ())
        }
    )
    doc["meta"] = {
        **dict(doc.get("meta", {})),
        "entity_spaces": dict.fromkeys(entities, name),
        "spaces": {name: definition},
    }
    return doc


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
