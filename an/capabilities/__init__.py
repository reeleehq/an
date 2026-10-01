"""Capabilities: what an asset, an engine or the environment affords, and the one matcher.

ADR 0002 (capability-based applicability, with a universal default) and the core
study §2.13 (three subjects). This is the LOWER layer of the pair: it knows
capabilities, analysers, requirements and substitution records, and nothing
about vocabulary entries, methods or aspects — :mod:`an.semantic` imports it,
never the reverse, and neither imports :mod:`an.ir` at module level.

- A **capability** is a named, possibly parametrised fact (``limbs.legs``,
  ``face.mouth`` with chart ``rhubarb9``, ``env.latex``). Names use one dotted
  grammar, are registered with a description and a **remedy** (what would add
  it, and the command where one exists), and are **persisted identifiers**: the
  asset library's facets and the substitution records store them. A capability
  belongs to one **subject**: ``asset``, ``engine`` or ``environment``.
- An **analyser** derives a subject's capabilities — a **profile**,
  ``{capability: params}`` — from what is there (a descriptor and its art, a
  renderer's implemented members, the tools on ``PATH``), never from a list
  typed beside it (ADR 0002 decision 2). It is versioned: a stored snapshot
  made by an older analyser is recomputed (:func:`current_affordances`).
  Declared facts used *instead of* deriving are listed under the
  ``overrides`` param, so the derivation reports which overrides it used.
- A **requirement** is a predicate over a profile, spelled as a string. The
  whole grammar (consult on P7, §3): ``cap`` (afforded), ``cap:key`` (``key``
  among the capability's ``keys``), ``cap>=N`` (its ``count`` param — else its
  number of ``keys`` — is at least ``N``) and ``a|b`` (any of). No callables:
  a requirement must name its remedy, render into the generated docs and the
  MCP surface, and diff when a method's version bumps.
- :func:`missing` is THE matcher: the requirement terms a profile (or a
  :class:`Subjects` triple) does not meet, in the order asked. ``why_not``,
  ``applicable`` and ``resolve`` (in :mod:`an.semantic`) and the library's
  ``find(…, near=True)`` are all calls to it.
- A :class:`Substitution` records that a method other than the requested one
  was used (generalising the compiled document's ``asset_resolution``).
  ``policy`` choices are information; ``missing`` and ``noop`` are warnings
  that ``--strict-assets`` makes fatal (:data:`FATAL_REASONS`).

>>> profile = {"swap.view": {"keys": ["front", "side"]}, "limbs.legs": {}}
>>> matches(profile, "swap.view:side"), matches(profile, "swap.view:back"), matches(profile, "limbs.legs")
(True, False, True)
>>> missing(profile, ["limbs.legs", "face.mouth|face.jaw", "swap.view>=3"])
['face.mouth|face.jaw', 'swap.view>=3']
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Union

from an.genres.registry import CORE_OWNER

__all__ = [
    "ANALYSERS",
    "Analyser",
    "CAPABILITIES",
    "Capability",
    "CapabilityError",
    "FATAL_REASONS",
    "KEY_SEP",
    "KEYS_PARAM",
    "OVERRIDES_PARAM",
    "Profile",
    "Requirement",
    "SUBJECTS",
    "Subjects",
    "Substitution",
    "affordances",
    "analyse",
    "art_in_dir",
    "capability_names",
    "capability_of",
    "current_affordances",
    "matches",
    "missing",
    "parse_requirement",
    "register_analyser",
    "register_capability",
    "remedy_for",
    "subject_of",
]

# -----------------------------------------------------------------------------
# Vocabulary of the grammar
# -----------------------------------------------------------------------------

#: The three subjects a capability can belong to (core study §2.13).
SUBJECTS: tuple[str, ...] = ("asset", "engine", "environment")
Subject = Literal["asset", "engine", "environment"]
#: Separates a capability from one of its keys in a term (``swap.view:side``).
KEY_SEP: str = ":"
#: Separates the alternatives of a disjunction (``face.eyes|face.brows``).
ANY_SEP: str = "|"
#: Introduces a count threshold (``rig.slots>=2``).
AT_LEAST_SEP: str = ">="
#: The params entry listing the discrete values a capability affords.
KEYS_PARAM: str = "keys"
#: The params entry a count threshold reads first (else ``len(keys)``).
COUNT_PARAM: str = "count"
#: The params entry listing the declared facts the derivation used instead of deriving.
OVERRIDES_PARAM: str = "overrides"

#: A capability name: dotted lowercase segments (``limbs.legs``, ``env.key.anthropic``).
_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")

#: ``{capability: params}`` — what an analyser derives, and the matcher's only input.
Profile = Mapping[str, Mapping[str, Any]]


class CapabilityError(ValueError):
    """A capability, analyser or requirement is malformed, or collides with one registered."""


# -----------------------------------------------------------------------------
# Capabilities
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Capability:
    """A registered capability: its name, what it means, and how to add it.

    ``command`` is the CLI that adds it, when one exists (``an character
    add-views``); ``version`` bumps when the *meaning* of the name changes (a
    persisted name is never redefined in place).
    """

    name: str
    description: str
    remedy: str
    subject: str = "asset"
    command: str | None = None
    version: str = "1"

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise CapabilityError(
                f"capability {self.name!r}: a name is dotted lowercase segments "
                "(`limbs.legs`, `env.latex`)"
            )
        if self.subject not in SUBJECTS:
            raise CapabilityError(
                f"capability {self.name!r}: subject must be one of {SUBJECTS}, "
                f"got {self.subject!r}"
            )

    def to_json(self) -> dict[str, Any]:
        """The capability as the generated docs and the MCP surface list it."""
        out = {
            "name": self.name,
            "subject": self.subject,
            "version": self.version,
            "description": self.description,
            "remedy": self.remedy,
        }
        if self.command:
            out["command"] = self.command
        return out


#: Registered capabilities, by name.
CAPABILITIES: dict[str, Capability] = {}
#: Who registered each capability (the core, or a genre's name).
_CAPABILITY_OWNERS: dict[str, str] = {}


def register_capability(
    name: str | Capability,
    *,
    description: str = "",
    remedy: str = "",
    subject: str = "asset",
    command: str | None = None,
    version: str = "1",
    owner: str = CORE_OWNER,
) -> Capability:
    """Register a capability (or a :class:`Capability`). Returns it.

    Re-registering the same definition is a no-op; a different definition
    under a name another owner holds raises, because capability names are
    persisted and two meanings for one name would make a stored facet lie.

    >>> cap = register_capability("demo.thing", description="a thing", remedy="add one", owner="demo")
    >>> CAPABILITIES["demo.thing"] is cap
    True
    >>> _ = drop_owner("demo")
    """
    cap = (
        name
        if isinstance(name, Capability)
        else Capability(name, description, remedy, subject, command, version)
    )
    current = CAPABILITIES.get(cap.name)
    if current is not None and current != cap and _CAPABILITY_OWNERS[cap.name] != owner:
        raise CapabilityError(
            f"capability {cap.name!r} is already registered by "
            f"{_CAPABILITY_OWNERS[cap.name]!r} with another definition"
        )
    CAPABILITIES[cap.name] = cap
    _CAPABILITY_OWNERS[cap.name] = owner
    return cap


def capability_names(
    *, subject: str | None = None, owner: str | None = None
) -> tuple[str, ...]:
    """The registered capability names, sorted; filtered by ``subject``/``owner``."""
    return tuple(
        sorted(
            n
            for n, c in CAPABILITIES.items()
            if (subject is None or c.subject == subject)
            and (owner is None or _CAPABILITY_OWNERS.get(n) == owner)
        )
    )


def subject_of(term: str | "Requirement") -> str:
    """The subject whose profile a requirement term is matched against.

    An unregistered capability is matched against the asset (and reported
    missing there): :func:`an.semantic.check_registry` is what refuses it.

    >>> subject_of("env.latex") == subject_of("limbs.legs")
    False
    """
    req = parse_requirement(term) if isinstance(term, str) else term
    first = req.any_of[0] if req.any_of else req
    cap = CAPABILITIES.get(first.capability)
    if cap is not None:
        return cap.subject
    return _subject_by_prefix(first.capability)


def _subject_by_prefix(name: str) -> str:
    head = name.split(".", 1)[0]
    return {"engine": "engine", "env": "environment"}.get(head, "asset")


# -----------------------------------------------------------------------------
# Analysers
# -----------------------------------------------------------------------------

#: The art an asset analyser sees: ``{relative path: ContentRef JSON}``. ``in``
#: and iteration give the paths; the refs reach the bytes through the blob store.
Art = Mapping[str, Any]
#: ``(doc, art) -> {capability: params}``.
Derivation = Callable[[Any, Art], dict[str, dict[str, Any]]]


@dataclass(frozen=True)
class Analyser:
    """The derivation of one kind's profile, versioned.

    ``kind`` is an asset kind (``character``) or a subject that has one
    analyser (``engine``, ``environment``). Bump ``version`` whenever the
    output can change for the same input: snapshots made under the old one are
    then recomputed on read. The version is NOT a compile input (consult §5):
    the derived profile is, so touching an analyser without changing its output
    re-renders nothing.
    """

    kind: str
    version: str
    derive: Derivation = field(compare=False, repr=False)
    subject: str = "asset"
    #: The document's declared facts the derivation honours instead of deriving
    #: (``rest_view``, ``face_overlay``) or reads as a request (``gait``):
    #: reported by ``describe_asset`` (ADR 0002 decision 2).
    declares: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.subject not in SUBJECTS:
            raise CapabilityError(
                f"analyser {self.kind!r}: subject must be one of {SUBJECTS}"
            )


#: Registered analysers, by kind.
ANALYSERS: dict[str, Analyser] = {}
_ANALYSER_OWNERS: dict[str, str] = {}


def register_analyser(
    kind: str | Analyser,
    *,
    version: str = "",
    subject: str = "asset",
    owner: str = CORE_OWNER,
) -> Any:
    """Register an analyser. Two forms.

    ``register_analyser(Analyser(...), owner=...)`` registers the object and
    returns it (a genre's ``analysers`` field goes this way). With a ``kind``
    string it is a decorator: ``@register_analyser("character", version="0.1.0")``
    registers the decorated derivation.
    """
    if isinstance(kind, Analyser):
        _install_analyser(kind, owner=owner)
        return kind

    def deco(derive: Derivation) -> Derivation:
        _install_analyser(Analyser(kind, version, derive, subject=subject), owner=owner)
        return derive

    return deco


def _install_analyser(analyser: Analyser, *, owner: str) -> None:
    current = ANALYSERS.get(analyser.kind)
    if (
        current is not None
        and _ANALYSER_OWNERS[analyser.kind] != owner
        and (current.version, current.derive) != (analyser.version, analyser.derive)
    ):
        raise CapabilityError(
            f"an analyser for {analyser.kind!r} is already registered by "
            f"{_ANALYSER_OWNERS[analyser.kind]!r}"
        )
    ANALYSERS[analyser.kind] = analyser
    _ANALYSER_OWNERS[analyser.kind] = owner


def analyse(
    kind: str, doc: Any, art: Art | None = None
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """``(profile, analysers)`` of one subject: its capabilities and the analyser versions used.

    A kind with no registered analyser affords nothing *derived* and records no
    analyser — an honest empty answer, not a guess.

    >>> analyse("no-such-kind", {})
    ({}, {})
    """
    analyser = ANALYSERS.get(kind)
    if analyser is None:
        return {}, {}
    return analyser.derive(doc, dict(art or {})), {kind: analyser.version}


def affordances(
    asset: Any, art: Art | None = None, *, kind: str = "character"
) -> dict[str, dict[str, Any]]:
    """``affordances(asset)`` (ADR 0002 decision 2): what ``asset`` affords, derived.

    ``asset`` is the document (a mapping, or a pydantic model, dumped to JSON
    first); ``art`` the files present, ``{relative path: ref}``. The kind's
    registered analyser decides; with none, nothing is afforded.
    """
    if hasattr(asset, "model_dump"):
        asset = asset.model_dump(mode="json")
    return analyse(kind, asset, art)[0]


def art_in_dir(directory: Any, *, exclude: Iterable[str] = ()) -> dict[str, bool]:
    """The art an asset folder holds, as an analyser reads it: ``{relative path: True}``.

    ``exclude`` drops the document files themselves (``character.json``).

    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as d:
    ...     _ = (pathlib.Path(d) / "parts").mkdir(); _ = (pathlib.Path(d) / "parts" / "head.svg").write_text("<svg/>", encoding="utf-8")
    ...     sorted(art_in_dir(d))
    ['parts/head.svg']
    """
    from pathlib import Path

    root = Path(directory)
    skip = set(exclude)
    return {
        p.relative_to(root).as_posix(): True
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name not in skip
    }


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


# -----------------------------------------------------------------------------
# Requirements: the grammar
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Requirement:
    """One requirement term: a capability, optionally a key or a count, or a disjunction.

    >>> str(parse_requirement("swap.view:side")), str(parse_requirement("rig.slots>=2"))
    ('swap.view:side', 'rig.slots>=2')
    >>> [str(r) for r in parse_requirement("face.eyes|face.brows").any_of]
    ['face.eyes', 'face.brows']
    """

    capability: str = ""
    key: str | None = None
    at_least: int | None = None
    any_of: tuple["Requirement", ...] = ()

    def __str__(self) -> str:
        if self.any_of:
            return ANY_SEP.join(str(r) for r in self.any_of)
        if self.key is not None:
            return f"{self.capability}{KEY_SEP}{self.key}"
        if self.at_least is not None:
            return f"{self.capability}{AT_LEAST_SEP}{self.at_least}"
        return self.capability

    def capabilities(self) -> tuple[str, ...]:
        """Every capability name this term mentions."""
        if self.any_of:
            return tuple(c for r in self.any_of for c in r.capabilities())
        return (self.capability,)


def parse_requirement(spec: str | Requirement) -> Requirement:
    """A :class:`Requirement` from its spelling (``cap``, ``cap:key``, ``cap>=N``, ``a|b``).

    >>> parse_requirement("rig.slots>=2").at_least
    2
    >>> parse_requirement("limbs.legs(hips)")
    Traceback (most recent call last):
    ...
    an.capabilities.CapabilityError: requirement 'limbs.legs(hips)': ...
    """
    if isinstance(spec, Requirement):
        return spec
    text = str(spec).strip()
    if ANY_SEP in text:
        parts = tuple(_parse_atom(p.strip(), text) for p in text.split(ANY_SEP))
        return Requirement(any_of=parts)
    return _parse_atom(text, text)


def _parse_atom(atom: str, whole: str) -> Requirement:
    def bad() -> CapabilityError:
        return CapabilityError(
            f"requirement {whole!r}: the grammar is `cap`, `cap:key`, `cap>=N` "
            "or `a|b` over dotted capability names — a capability whose "
            "parameter you need to test is a key (`face.mouth:rhubarb9`) or "
            "two capabilities"
        )

    key = at_least = None
    name = atom
    if AT_LEAST_SEP in atom:
        name, _, n = atom.partition(AT_LEAST_SEP)
        if not n.isdigit():
            raise bad()
        at_least = int(n)
    elif KEY_SEP in atom:
        name, _, key = atom.partition(KEY_SEP)
        if not key:
            raise bad()
    if not _NAME.match(name):
        raise bad()
    return Requirement(name, key=key, at_least=at_least)


def capability_of(query: str) -> tuple[str, str | None]:
    """``(capability, key)`` of a query term (the library's ``find`` form).

    >>> capability_of("swap.view:side"), capability_of("limbs.legs")
    (('swap.view', 'side'), ('limbs.legs', None))
    """
    name, sep, key = query.partition(KEY_SEP)
    return name, (key if sep else None)


# -----------------------------------------------------------------------------
# Subjects and the matcher
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Subjects:
    """The three profiles a requirement can be matched against.

    A bare profile passed where ``Subjects`` is expected is the asset's.

    >>> Subjects.of({"limbs.legs": {}}).asset
    {'limbs.legs': {}}
    """

    asset: Profile = field(default_factory=dict)
    engine: Profile = field(default_factory=dict)
    environment: Profile = field(default_factory=dict)

    @classmethod
    def of(cls, x: "Subjects | Profile | None") -> "Subjects":
        if isinstance(x, Subjects):
            return x
        return cls(asset=dict(x or {}))

    def profile(self, subject: str) -> Profile:
        return {
            "asset": self.asset,
            "engine": self.engine,
            "environment": self.environment,
        }[subject]


ProfileLike = Union[Subjects, Mapping[str, Mapping[str, Any]], None]


def _meets(profile: Profile, req: Requirement) -> bool:
    if req.any_of:
        return any(_meets(profile, r) for r in req.any_of)
    if req.capability not in profile:
        return False
    params = profile[req.capability] or {}
    if req.key is not None:
        return req.key in params.get(KEYS_PARAM, ())
    if req.at_least is not None:
        count = params.get(COUNT_PARAM, len(params.get(KEYS_PARAM, ())))
        return count >= req.at_least
    return True


def matches(profile: ProfileLike, term: str | Requirement) -> bool:
    """Whether ``profile`` (or the subject of ``term`` in a :class:`Subjects`) meets ``term``."""
    req = parse_requirement(term)
    subjects = Subjects.of(profile)
    if req.any_of:
        return any(matches(subjects, r) for r in req.any_of)
    return _meets(subjects.profile(subject_of(req)), req)


def missing(profile: ProfileLike, requires: Iterable[str | Requirement]) -> list[str]:
    """The requirement terms ``profile`` does not meet, spelled, in the order asked.

    THE matcher (ADR 0002 decision 4): ``why_not``, ``applicable``,
    ``resolve`` and the library's ``find(…, near=True)`` all call it.

    >>> missing({}, ["env.ffmpeg"]), missing(Subjects(environment={"env.ffmpeg": {}}), ["env.ffmpeg"])
    (['env.ffmpeg'], [])
    """
    return [str(parse_requirement(t)) for t in requires if not matches(profile, t)]


def remedy_for(term: str | Requirement) -> str:
    """What would add the capability a requirement term asks for.

    >>> remedy_for("no.such.capability")
    'no registered capability no.such.capability; see vocabulary() for the known names'
    """
    req = parse_requirement(term)
    if req.any_of:
        return " — or — ".join(remedy_for(r) for r in req.any_of)
    cap = CAPABILITIES.get(req.capability)
    if cap is None:
        return (
            f"no registered capability {req.capability}; see vocabulary() for the "
            "known names"
        )
    if req.key is not None:
        return f"{cap.remedy} (needed key: {req.key})"
    if req.at_least is not None:
        return f"{cap.remedy} (needed: at least {req.at_least})"
    return cap.remedy


# -----------------------------------------------------------------------------
# Substitution records
# -----------------------------------------------------------------------------

#: Why a method other than the requested one was used.
#: ``policy``: a style's policy chose another applicable method (information);
#: ``missing``: the requested method does not apply, a fallback was used;
#: ``noop``: the aspect does not apply to the asset, nothing was done.
SubstitutionReason = Literal["policy", "missing", "noop"]
#: The reasons ``--strict-assets`` makes fatal (a test pins this set).
FATAL_REASONS: frozenset[str] = frozenset({"missing", "noop"})


@dataclass(frozen=True)
class Substitution:
    """One recorded substitution: the method asked for, the one used, and why.

    It generalises the compiled document's ``asset_resolution`` (ADR 0002
    decision 6): a requested method replaced by a default is said out loud,
    and fatal under ``--strict-assets`` unless it was a policy choice.

    >>> s = Substitution("locomotion", "bob", requested="loco.hem_sway", chosen="loco.rock",
    ...                  reason="missing", missing=("limbs.legs",))
    >>> s.fatal, s.sentence()
    (True, "bob: locomotion 'loco.hem_sway' does not apply (missing limbs.legs); used 'loco.rock'")
    """

    aspect: str
    entity: str
    requested: str | None
    chosen: str
    reason: str
    requested_version: str | None = None
    chosen_version: str = ""
    missing: tuple[str, ...] = ()
    remedies: Mapping[str, str] = field(default_factory=dict)

    @property
    def fatal(self) -> bool:
        return self.reason in FATAL_REASONS

    def sentence(self) -> str:
        """One human sentence saying what happened."""
        who = f"{self.entity}: " if self.entity else ""
        if self.reason == "noop":
            return (
                f"{who}{self.aspect} does not apply; nothing was done (recorded no-op)"
            )
        if self.reason == "policy":
            return f"{who}{self.aspect}: the policy chose {self.chosen!r}" + (
                f" over {self.requested!r}" if self.requested else ""
            )
        why = f" (missing {', '.join(self.missing)})" if self.missing else ""
        return (
            f"{who}{self.aspect} {self.requested!r} does not apply{why}; "
            f"used {self.chosen!r}"
        )

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "aspect": self.aspect,
            "entity": self.entity,
            "requested": self.requested,
            "chosen": self.chosen,
            "chosen_version": self.chosen_version,
            "reason": self.reason,
        }
        if self.requested_version is not None:
            out["requested_version"] = self.requested_version
        if self.missing:
            out["missing"] = list(self.missing)
            out["remedies"] = dict(self.remedies)
        return out


# -----------------------------------------------------------------------------
# Owners: a genre's registrations come out with it
# -----------------------------------------------------------------------------


def drop_owner(owner: str) -> None:
    """Remove every capability and analyser ``owner`` registered."""
    for table, owners in (
        (CAPABILITIES, _CAPABILITY_OWNERS),
        (ANALYSERS, _ANALYSER_OWNERS),
    ):
        for name in [k for k, o in owners.items() if o == owner]:
            table.pop(name, None)
            owners.pop(name, None)


def snapshot() -> tuple:
    """The state of the capability and analyser tables, for :func:`restore`."""
    return tuple(
        (dict(t), dict(o))
        for t, o in ((CAPABILITIES, _CAPABILITY_OWNERS), (ANALYSERS, _ANALYSER_OWNERS))
    )


def restore(state: tuple) -> None:
    for (table, owners), (saved, saved_owners) in zip(
        ((CAPABILITIES, _CAPABILITY_OWNERS), (ANALYSERS, _ANALYSER_OWNERS)), state
    ):
        table.clear()
        table.update(saved)
        owners.clear()
        owners.update(saved_owners)


def owner_of(name: str) -> str | None:
    """Who registered capability ``name``."""
    return _CAPABILITY_OWNERS.get(name)


#: ADR 0002 calls the matcher's three queries "the registry"'s; they live in
#: :mod:`an.semantic` because answering them needs the method table (P7 consult
#: §1), and are reachable here by name, imported on first use (this module stays
#: below :mod:`an.semantic` in the import graph).
_QUERIES: frozenset[str] = frozenset({"applicable", "why_not", "resolve"})


def __getattr__(name: str):
    if name in _QUERIES:
        from an import semantic

        return getattr(semantic, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# The core's own subjects: the engine and the environment analysers register on
# import, owned by the core (no genre needed to ask "is LaTeX here?").
from an.capabilities import subjects as _subjects  # noqa: E402,F401
