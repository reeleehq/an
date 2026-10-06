"""Describe an asset: what it affords, and per aspect what applies and what is missing.

ADR 0002's first slice ends with ``an character capabilities <name>``: the
affordances (with the declared overrides the derivation used), and per aspect
the method the default chain picks, the methods that apply, and the
``why_not`` of the rest with their remedies. :func:`describe_asset` is that
answer as data (the MCP surface's describe-an-asset query returns it);
:func:`format_description` is its terminal form. Core code: it names no rig.
Given a ``policy`` (a style's, an#348), each aspect also says what it
resolves to under it (``under_policy``), by the same precedence the compiler
uses (:func:`an.semantic.resolve`).

>>> from an.semantic.entries import Aspect, Method
>>> from an.semantic.registry import register_aspect, register_entry, drop_owner
>>> _ = register_entry(Method("demo.fly", aspect="demo_travel", requires=("limbs.wings",)), owner="demo")
>>> _ = register_entry(Method("demo.float", aspect="demo_travel"), owner="demo")
>>> _ = register_aspect(Aspect("demo_travel", chain=("demo.fly", "demo.float")), owner="demo")
>>> d = describe_profile({}, aspects=("demo_travel",))
>>> d["aspects"]["demo_travel"]["default"], list(d["aspects"]["demo_travel"]["not_applicable"])
('demo.float', ['demo.fly'])
>>> d = describe_profile({}, aspects=("demo_travel",), policy={"demo_travel": ["demo.fly", "demo.float"]})
>>> u = d["aspects"]["demo_travel"]["under_policy"]
>>> u["method"], u["source"], u["skipped"]
('demo.float', 'policy', [{'method': 'demo.fly', 'missing': ['limbs.wings']}])
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
    declared: Mapping[str, Any] | None = None,
    policy: Any = None,
) -> dict[str, Any]:
    """Per aspect: the method it resolves to, the applicable ones, and why not the rest.

    ``declared`` is the asset document's declared facts: an aspect's
    declaration is read from the field it names (``Aspect.declared_by``: a
    character's ``gait``), so the answer is the method the compiler will use.
    ``policy`` (a style's, anything :meth:`an.semantic.Policy.of` reads) adds
    ``under_policy`` per aspect: the method, where the choice came from, what
    that method requires (a genre may say when it holds), and any
    substitution or skipped policy entries.
    """
    from an.semantic.registry import aspect as _aspect

    subjects = Subjects.of(profile)
    declared = dict(declared or {})
    out: dict[str, Any] = {}
    for name in aspects if aspects is not None else aspect_names():
        asp = _aspect(name)
        request = declared.get(asp.declared_by) if asp.declared_by else None
        r = resolve(name, subjects, declared=request, entity_kind=kind)
        fits = [m.id for m in applicable(name, subjects)]
        out[name] = {
            "default": r.method.id,
            **({"declared": request} if request is not None else {}),
            **(
                {"substitution": r.substitution.to_json()}
                if r.substitution is not None
                else {}
            ),
            "applicable": fits,
            "not_applicable": {
                m.id: [w.to_json() for w in why_not(m, subjects)]
                for m in methods_of(name)
                if m is not NOOP and m.id not in fits
            },
        }
        if policy is not None:
            out[name]["under_policy"] = _under_policy(
                resolve(
                    name, subjects, declared=request, policy=policy, entity_kind=kind
                )
            )
    return {
        "affordances": {k: dict(v or {}) for k, v in subjects.asset.items()},
        "aspects": out,
    }


def _under_policy(r: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "method": r.method.id,
        "source": r.source,
        "requires": [str(t) for t in r.method.requires],
    }
    if r.substitution is not None:
        out["substitution"] = r.substitution.to_json()
    if r.skipped:
        out["skipped"] = r.to_json()["skipped"]
    return out


def describe_asset(
    doc: Any,
    art: Mapping[str, Any] | None = None,
    *,
    kind: str = "character",
    aspects: Iterable[str] | None = None,
    policy: Any = None,
) -> dict[str, Any]:
    """:func:`describe_profile` of an asset's derived profile, with the analyser and
    overrides; ``policy`` as :func:`describe_profile`'s."""
    profile = affordances(doc, art, kind=kind)
    analyser = ANALYSERS.get(kind)
    raw = doc.model_dump(mode="json") if hasattr(doc, "model_dump") else dict(doc)
    declared = {
        f: raw[f]
        for f in (analyser.declares if analyser else ())
        if raw.get(f) is not None
    }
    out = {
        "kind": kind,
        "analyser": {kind: analyser.version} if analyser else {},
        "declared": declared,
        **describe_profile(
            profile, kind=kind, aspects=aspects, declared=declared, policy=policy
        ),
    }
    # declared overrides the derivation used: those on an afforded capability's
    # params, and those that removed one (the analyser says, an#381)
    removed = (
        analyser.overrides(raw, dict(art or {}))
        if analyser is not None and analyser.overrides is not None
        else ()
    )
    out["overrides"] = sorted(
        {
            o
            for params in profile.values()
            for o in (params or {}).get(OVERRIDES_PARAM, ())
        }
        | set(removed)
    )
    return out


def _params_text(params: Mapping[str, Any]) -> str:
    shown = {k: v for k, v in params.items() if k != OVERRIDES_PARAM}
    return ", ".join(f"{k}={v}" for k, v in shown.items())


def format_description(
    d: Mapping[str, Any], *, name: str = "", policy_label: str = "the policy"
) -> str:
    """The terminal form of :func:`describe_asset`; ``policy_label`` names the
    policy an ``under_policy`` answer was resolved under (a style's name)."""
    who = f"{name}: " if name else ""
    lines = [f"{who}affords (derived from the descriptor and the art present)"]
    if not d["affordances"]:
        lines.append("  (nothing derived)")
    for cap, params in sorted(d["affordances"].items()):
        text = _params_text(params)
        lines.append(f"  {cap}" + (f"  [{text}]" if text else ""))
    if d.get("overrides"):
        lines.append(f"  declared overrides used: {', '.join(d['overrides'])}")
    if d.get("declared"):
        lines.append(
            "  declared: "
            + ", ".join(f"{k}={v}" for k, v in sorted(d["declared"].items()))
        )
    for aspect, info in d["aspects"].items():
        lines.append("")
        head = f"{aspect}: default {info['default']}"
        if "declared" in info:
            head += f" (declared: {info['declared']})"
        lines.append(head)
        if "substitution" in info:
            lines.append(
                f"  recorded: {info['substitution']['reason']} — {info['substitution']['requested']} → {info['substitution']['chosen']}"
            )
        if "under_policy" in info:
            under = info["under_policy"]
            needs = (
                f"; needs {', '.join(under['requires'])}" if under["requires"] else ""
            )
            lines.append(
                f"  under {policy_label}: {under['method']} ({under['source']}{needs})"
            )
            for skip in under.get("skipped", ()):
                lines.append(
                    f"    skipped {skip['method']}: missing {', '.join(skip['missing'])}"
                )
        if info["applicable"]:
            lines.append(f"  applies: {', '.join(info['applicable'])}")
        for method, gaps in info["not_applicable"].items():
            lines.append(
                f"  not {method}: missing {', '.join(g['term'] for g in gaps)}"
            )
            for g in gaps:
                lines.append(f"    to add {g['term']}: {g['remedy']}")
    return "\n".join(lines)
