"""Describe an asset: what it affords, and per aspect what applies and what is missing.

ADR 0002's first slice ends with ``an character capabilities <name>``: the
affordances (with the declared overrides the derivation used), and per aspect
the method the default chain picks, the methods that apply, and the
``why_not`` of the rest with their remedies. :func:`describe_asset` is that
answer as data (the MCP surface's describe-an-asset query returns it);
:func:`format_description` is its terminal form. Core code: it names no rig.

>>> from an.semantic.entries import Aspect, Method
>>> from an.semantic.registry import register_aspect, register_entry, drop_owner
>>> _ = register_entry(Method("demo.fly", aspect="demo_travel", requires=("limbs.wings",)), owner="demo")
>>> _ = register_entry(Method("demo.float", aspect="demo_travel"), owner="demo")
>>> _ = register_aspect(Aspect("demo_travel", chain=("demo.fly", "demo.float")), owner="demo")
>>> d = describe_profile({}, aspects=("demo_travel",))
>>> d["aspects"]["demo_travel"]["default"], list(d["aspects"]["demo_travel"]["not_applicable"])
('demo.float', ['demo.fly'])
>>> drop_owner("demo")
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from an.capabilities import ANALYSERS, OVERRIDES_PARAM, Subjects, affordances
from an.semantic.entries import NOOP
from an.semantic.matcher import applicable, resolve, why_not
from an.semantic.registry import aspect_names, methods_of

__all__ = ["describe_asset", "describe_profile", "format_description"]


def describe_profile(
    profile: Mapping[str, Mapping[str, Any]] | Subjects,
    *,
    kind: str | None = None,
    aspects: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Per aspect: the default method, the applicable ones, and why not the rest."""
    subjects = Subjects.of(profile)
    out: dict[str, Any] = {}
    for name in aspects if aspects is not None else aspect_names():
        r = resolve(name, subjects, entity_kind=kind)
        fits = [m.id for m in applicable(name, subjects)]
        out[name] = {
            "default": r.method.id,
            "applicable": fits,
            "not_applicable": {
                m.id: [w.to_json() for w in why_not(m, subjects)]
                for m in methods_of(name)
                if m is not NOOP and m.id not in fits
            },
        }
    return {
        "affordances": {k: dict(v or {}) for k, v in subjects.asset.items()},
        "aspects": out,
    }


def describe_asset(
    doc: Any,
    art: Mapping[str, Any] | None = None,
    *,
    kind: str = "character",
    aspects: Iterable[str] | None = None,
) -> dict[str, Any]:
    """:func:`describe_profile` of an asset's derived profile, with the analyser and overrides."""
    profile = affordances(doc, art, kind=kind)
    analyser = ANALYSERS.get(kind)
    out = {
        "kind": kind,
        "analyser": {kind: analyser.version} if analyser else {},
        **describe_profile(profile, kind=kind, aspects=aspects),
    }
    out["overrides"] = sorted(
        {o for params in profile.values() for o in (params or {}).get(OVERRIDES_PARAM, ())}
    )
    return out


def _params_text(params: Mapping[str, Any]) -> str:
    shown = {k: v for k, v in params.items() if k != OVERRIDES_PARAM}
    return ", ".join(f"{k}={v}" for k, v in shown.items())


def format_description(d: Mapping[str, Any], *, name: str = "") -> str:
    """The terminal form of :func:`describe_asset`."""
    who = f"{name}: " if name else ""
    lines = [f"{who}affords (derived from the descriptor and the art present)"]
    if not d["affordances"]:
        lines.append("  (nothing derived)")
    for cap, params in sorted(d["affordances"].items()):
        text = _params_text(params)
        lines.append(f"  {cap}" + (f"  [{text}]" if text else ""))
    if d.get("overrides"):
        lines.append(f"  declared overrides used: {', '.join(d['overrides'])}")
    for aspect, info in d["aspects"].items():
        lines.append("")
        lines.append(f"{aspect}: default {info['default']}")
        if info["applicable"]:
            lines.append(f"  applies: {', '.join(info['applicable'])}")
        for method, gaps in info["not_applicable"].items():
            lines.append(f"  not {method}: missing {', '.join(g['term'] for g in gaps)}")
            for g in gaps:
                lines.append(f"    to add {g['term']}: {g['remedy']}")
    return "\n".join(lines)
