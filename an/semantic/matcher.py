"""The three queries and the policy (ADR 0002 decision 4): ``applicable``, ``why_not``, ``resolve``.

All three are calls to the one matcher, :func:`an.capabilities.missing`, over
the methods the vocabulary registry holds for an aspect.

- :func:`applicable` lists the methods of an aspect that apply to the subjects
  (the default chain's order first).
- :func:`why_not` lists what a method is missing, each term with its remedy —
  the method's own, else the capability's.
- :func:`resolve` picks one: the author's request if it applies; else the first
  applicable choice of the policy (shot before style, :meth:`Policy.layered`);
  else the aspect's default chain. Every departure from what was asked is a
  :class:`~an.capabilities.Substitution` on the result: ``missing`` when what
  was asked does not apply, ``policy`` when a policy chose against the chain
  (information, never fatal), ``noop`` when the aspect does not apply at all.

>>> from an.semantic.entries import Aspect, Method
>>> from an.semantic.registry import register_aspect, register_entry, drop_owner
>>> _ = register_entry(Method("demo.legs", aspect="demo_move", requires=("limbs.legs",)), owner="demo")
>>> _ = register_entry(Method("demo.slide", aspect="demo_move"), owner="demo")
>>> _ = register_aspect(Aspect("demo_move", chain=("demo.legs", "demo.slide")), owner="demo")
>>> [m.id for m in applicable("demo_move", {})]
['demo.slide']
>>> [w.term for w in why_not("demo.legs", {})]
['limbs.legs']
>>> r = resolve("demo_move", {}, requested="demo.legs", entity="blob")
>>> r.method.id, r.substitution.reason
('demo.slide', 'missing')
>>> drop_owner("demo")
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from an.capabilities import (
    ProfileLike,
    Subjects,
    Substitution,
    missing,
    remedy_for,
)
from an.semantic.entries import (
    ANY_ASPECT,
    NOOP,
    Choice,
    Method,
    Policy,
    VocabularyError,
)
from an.semantic.registry import aspect as _aspect
from an.semantic.registry import entry as _entry
from an.semantic.registry import lookup, methods_of

__all__ = [
    "Missing",
    "Resolution",
    "applicable",
    "resolve",
    "why_not",
]


@dataclass(frozen=True)
class Missing:
    """One unmet requirement term and what would meet it."""

    term: str
    remedy: str

    def to_json(self) -> dict[str, str]:
        return {"term": self.term, "remedy": self.remedy}


@dataclass(frozen=True)
class Resolution:
    """What :func:`resolve` chose: the method, its args, where the choice came from.

    ``source`` is ``request``, ``policy``, ``chain`` or ``noop``;
    ``substitution`` is the record when the choice departs from what was asked
    (``None`` when it did not); ``considered`` is the trail of methods tried
    before it, each with what it was missing.
    """

    aspect: str
    method: Method
    args: Mapping[str, Any] = field(default_factory=dict)
    source: str = "chain"
    substitution: Substitution | None = None
    considered: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "aspect": self.aspect,
            "method": self.method.id,
            "version": self.method.version,
            "args": dict(self.args),
            "source": self.source,
        }
        if self.substitution is not None:
            out["substitution"] = self.substitution.to_json()
        if self.considered:
            out["considered"] = [
                {"method": m, "missing": list(t)} for m, t in self.considered
            ]
        return out


def _method(x: Method | Choice | str, aspect_name: str | None = None) -> Method:
    """The method ``x`` names — by spelling within ``aspect_name``, else by id.

    With ``aspect_name``, a method of ANOTHER aspect is refused: a typo in a
    style's ``policy:`` block must not realise one aspect with another's method.
    """
    if isinstance(x, Method):
        found = x
    else:
        mid = x.method if isinstance(x, Choice) else str(x)
        found = lookup("method", mid, aspect=aspect_name) if aspect_name else None
        if found is None:
            try:
                found = _entry(mid)
            except KeyError:
                found = None
        if not isinstance(found, Method):
            known = [m.id for m in methods_of(aspect_name)] if aspect_name else []
            raise VocabularyError(
                f"{mid!r} is not a registered method"
                + (f" of {aspect_name!r}; its methods: {known}" if aspect_name else "")
            )
    if aspect_name is not None and found.aspect not in (aspect_name, ANY_ASPECT):
        raise VocabularyError(
            f"{found.id!r} is a method of {found.aspect!r}, not of {aspect_name!r}; "
            f"{aspect_name!r}'s methods: {[m.id for m in methods_of(aspect_name)]}"
        )
    return found


def why_not(
    method: Method | Choice | str, subjects: ProfileLike
) -> tuple[Missing, ...]:
    """What ``method`` is missing on ``subjects``, each with its remedy (empty: it applies)."""
    m = _method(method)
    return tuple(
        Missing(term, m.remedies.get(term) or remedy_for(term))
        for term in missing(subjects, m.requires)
    )


def applicable(aspect_name: str, subjects: ProfileLike) -> tuple[Method, ...]:
    """The methods of ``aspect_name`` that apply to ``subjects``, the default chain's order first."""
    _aspect(aspect_name)  # an unknown aspect is an error, not an empty answer
    return tuple(
        m for m in methods_of(aspect_name) if m is not NOOP and not why_not(m, subjects)
    )


def resolve(
    aspect_name: str,
    subjects: ProfileLike,
    requested: Method | Choice | str | Mapping[str, Any] | None = None,
    *,
    policy: Policy | Mapping[str, Any] | None = None,
    entity: str = "",
    entity_kind: str | None = None,
) -> Resolution:
    """Choose the method that realises ``aspect_name`` on ``subjects``.

    ``requested`` is the author's explicit choice (a method id, its spelling
    in the aspect — ``"hem"`` for locomotion —, or ``{method, args, version}``);
    ``policy`` the layered shot/style policy; ``entity_kind`` the asset's kind,
    checked against the aspect's ``applies_to``. Never raises for a method that
    does not apply: it falls back and records why.
    """
    asp = _aspect(aspect_name)
    subjects = Subjects.of(subjects)
    if entity_kind is not None and asp.applies_to and entity_kind not in asp.applies_to:
        return Resolution(
            aspect_name,
            NOOP,
            source="noop",
            substitution=Substitution(
                aspect_name, entity, None, NOOP.id, "noop", chosen_version=NOOP.version
            ),
        )
    asked = _as_choice(requested, aspect_name)
    policy_choices = Policy.of(policy).choices(aspect_name)
    considered: list[tuple[str, tuple[str, ...]]] = []

    def trial(choice: Choice) -> Method | None:
        m = _method(choice, aspect_name)
        gaps = tuple(missing(subjects, m.requires))
        if gaps:
            considered.append((m.id, gaps))
            return None
        return m

    chain_choice = _first_of_chain(asp.chain, subjects)

    def done(m: Method, choice: Choice | None, source: str) -> Resolution:
        args = {**m.defaults(), **dict(choice.args if choice else {})}
        effective = asked or (policy_choices[0] if policy_choices else None)
        sub = None
        if m is NOOP:
            sub = Substitution(
                aspect_name,
                entity,
                effective.method if effective else None,
                NOOP.id,
                "noop",
                chosen_version=NOOP.version,
            )
        elif effective is not None and _method(effective, aspect_name).id != m.id:
            wanted = _method(effective, aspect_name)
            gaps = next((g for mid, g in considered if mid == wanted.id), ())
            sub = Substitution(
                aspect_name,
                entity,
                wanted.id,
                m.id,
                "missing",
                requested_version=wanted.version,
                chosen_version=m.version,
                missing=gaps,
                remedies={t: wanted.remedies.get(t) or remedy_for(t) for t in gaps},
            )
        elif effective is None and asp.records_fallback and m.id != asp.chain[0]:
            head = _method(asp.chain[0], aspect_name)
            gaps = next((g for mid, g in considered if mid == head.id), ())
            sub = Substitution(
                aspect_name,
                entity,
                head.id,
                m.id,
                "missing",
                requested_version=head.version,
                chosen_version=m.version,
                missing=gaps,
                remedies={t: head.remedies.get(t) or remedy_for(t) for t in gaps},
            )
        elif (
            source == "policy" and chain_choice is not None and chain_choice.id != m.id
        ):
            sub = Substitution(
                aspect_name,
                entity,
                chain_choice.id,
                m.id,
                "policy",
                requested_version=chain_choice.version,
                chosen_version=m.version,
            )
        return Resolution(aspect_name, m, args, source, sub, tuple(considered))

    if asked is not None:
        m = trial(asked)
        if m is not None:
            return done(m, asked, "request")
    for choice in policy_choices:
        m = trial(choice)
        if m is not None:
            return done(m, choice, "policy")
    for mid in asp.chain:
        m = NOOP if mid == NOOP.id else trial(Choice(mid))
        if m is not None:
            return done(m, None, "noop" if m is NOOP else "chain")
    raise VocabularyError(
        f"aspect {aspect_name!r}: no link of its chain {list(asp.chain)} applies — "
        "its last link must require nothing (check_registry refuses such a chain)"
    )


def _first_of_chain(chain: tuple[str, ...], subjects: Subjects) -> Method | None:
    for mid in chain:
        if mid == NOOP.id:
            return NOOP
        m = _method(mid)
        if not missing(subjects, m.requires):
            return m
    return None


def _as_choice(x: Any, aspect_name: str) -> Choice | None:
    if x is None or x == "":
        return None
    if isinstance(x, Method):
        return Choice(x.id)
    c = Choice.of(x)
    if c.version is not None:
        m = _method(c, aspect_name)
        if m.version != str(c.version):
            raise VocabularyError(
                f"{m.id!r} is pinned to version {c.version!r}, but the registry has "
                f"{m.version!r} — freeze its expansion, or update the pin"
            )
    return c
