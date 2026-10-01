"""The shapes of the vocabulary: entries, methods, aspects, policies.

ADR 0003 decision 5 and the core study §2.11: a **vocabulary entry** is shaped
to be isomorphic to a ``previz`` formula — ``id``, ``version``, ``kind``,
``title``, ``description`` (one sentence, for a person or an agent choosing),
``params`` (a JSON Schema object with defaults), ``examples``, ``requires``
(ADR 0002 requirement terms), the spectrum ``levels`` it accepts, and
``expand(params, context) → actions``. Plain, JSON-describable data, so a
TypeScript package can export its formulas into the registry and an MCP client
sees one list.

A **method** (ADR 0002) is an entry of kind ``method`` with an ``aspect`` and
per-requirement ``remedies`` — not a separate record an entry points to (P7
consult §1: one id namespace, one version, one description). An **aspect**
names a default ``chain`` of methods whose last link requires nothing (or is
:data:`NOOP`). A **policy** is how a style reorders the choice ("this show hops
even when its characters have legs"); a :class:`Choice` in it is exactly a
``previz`` ``FormulaCall`` plus ADR 0003's version pin.

This module imports nothing from ``an.ir`` (the schema consults the vocabulary
while it validates), only the requirement grammar from :mod:`an.capabilities`.

>>> walk = Entry("motion.walk", "motion_preset", name="walk", description="walk")
>>> walk.term, walk.version, sorted(walk.levels)
('walk', '1', ['a', 'b-name'])
>>> Entry("x", "motion_preset", levels={"b-guess"})
Traceback (most recent call last):
...
an.semantic.entries.VocabularyError: entry 'x': levels must be among ('a', 'b-name', 'b-llm', 'c'), got ['b-guess']
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from an.capabilities import Requirement, parse_requirement

__all__ = [
    "ANY_ASPECT",
    "Aspect",
    "Choice",
    "DFLT_LEVELS",
    "Entry",
    "LEVELS",
    "Method",
    "NOOP",
    "NOOP_ID",
    "Policy",
    "VocabularyError",
]

#: The four levels of the structured ↔ semantic spectrum (ADR 0003 decision 1).
LEVELS: tuple[str, ...] = ("a", "b-name", "b-llm", "c")
#: What an entry accepts unless it says otherwise: its typed params, and its name.
DFLT_LEVELS: frozenset[str] = frozenset({"a", "b-name"})
#: The aspect a method claims when it serves every aspect (:data:`NOOP`).
ANY_ASPECT: str = "*"
#: The id of the core's recorded no-op.
NOOP_ID: str = "noop"


class VocabularyError(ValueError):
    """A vocabulary entry, aspect or policy is malformed or collides with a registered one."""


#: ``expand(params, context) -> actions``: what an entry means, as typed actions.
Expand = Callable[[Mapping[str, Any], Any], Any]


@dataclass(frozen=True)
class Entry:
    """One vocabulary entry: a named, versioned, described, parametrised recipe.

    - ``id`` is the persisted identifier (dotted: ``motion.walk``,
      ``loco.legged_cycle``); ``name`` is how a document spells it (``walk``;
      defaults to ``id``), looked up per ``kind``.
    - ``version`` changes whenever the meaning changes for the same params; the
      versions of the entries a shot uses fold into its compile key.
    - ``params`` is a JSON Schema object; ``properties.*.default`` are the
      defaults (``{}`` when the entry takes none).
    - ``aspects`` names the aspects that using this entry resolves (a ``walk``
      resolves ``locomotion``), so the digest of a shot can include the methods
      it may resolve to.
    - ``usage`` is the longer note the generated surfaces print under the
      one-sentence ``description`` (how a document spells it, what bites).
    """

    id: str
    kind: str
    version: str = "1"
    name: str = ""
    title: str = ""
    description: str = ""
    usage: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    examples: tuple = ()
    requires: tuple = ()
    levels: frozenset = DFLT_LEVELS
    aspects: tuple[str, ...] = ()
    expand: Expand | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id or not self.kind:
            raise VocabularyError(f"an entry needs an id and a kind, got {self.id!r}/{self.kind!r}")
        object.__setattr__(self, "version", str(self.version))
        if not self.version:
            raise VocabularyError(f"entry {self.id!r}: every entry carries a version")
        levels = frozenset(self.levels)
        bad = sorted(levels - set(LEVELS))
        if bad or not levels:
            raise VocabularyError(
                f"entry {self.id!r}: levels must be among {LEVELS}, got {bad or sorted(levels)}"
            )
        object.__setattr__(self, "levels", levels)
        object.__setattr__(
            self, "requires", tuple(parse_requirement(r) for r in self.requires)
        )
        object.__setattr__(self, "examples", tuple(self.examples))
        object.__setattr__(self, "aspects", tuple(self.aspects))

    @property
    def term(self) -> str:
        """How a document spells this entry."""
        return self.name or self.id

    def defaults(self) -> dict[str, Any]:
        """The params' defaults (``properties.*.default``)."""
        return {
            k: v["default"]
            for k, v in (self.params.get("properties") or {}).items()
            if isinstance(v, Mapping) and "default" in v
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any], *, expand: Expand | None = None) -> "Entry":
        """An entry from its JSON form (what :meth:`to_json` writes, or another
        package exports — previz's formulas): the explicit loader, a ``method``
        kind giving a :class:`Method`.

        >>> e = Entry("camera.demo", "camera_move", name="demo", description="d")
        >>> Entry.from_json(e.to_json()) == e
        True
        """
        d = dict(data)
        kind = d.get("kind")
        fields = {k: v for k, v in d.items() if k in cls.__dataclass_fields__ or k in Method.__dataclass_fields__}
        if "levels" in fields:
            fields["levels"] = frozenset(fields["levels"])
        for key in ("examples", "requires", "aspects"):
            if key in fields:
                fields[key] = tuple(fields[key])
        target = Method if kind == "method" else cls
        if target is not Method:
            for key in ("aspect", "remedies"):
                fields.pop(key, None)
        return target(**fields, expand=expand)

    def to_json(self) -> dict[str, Any]:
        """The entry as data (no ``expand``): what the MCP surface and the docs list."""
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "name": self.term,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "levels": sorted(self.levels, key=LEVELS.index),
        }
        if self.usage:
            out["usage"] = self.usage
        if self.params:
            out["params"] = dict(self.params)
        if self.examples:
            out["examples"] = list(self.examples)
        if self.requires:
            out["requires"] = [str(r) for r in self.requires]
        if self.aspects:
            out["aspects"] = list(self.aspects)
        return out


@dataclass(frozen=True)
class Method(Entry):
    """A way of realising an aspect (ADR 0002): an entry of kind ``method``.

    ``remedies`` overrides a capability's own remedy per requirement term (a
    method can say "split the legs into two slots with hip pivots" where the
    capability only says "add legs").

    >>> m = Method("loco.rock", aspect="locomotion", name="rock")
    >>> m.kind, m.aspect, m.requirement_free
    ('method', 'locomotion', True)
    """

    kind: str = "method"
    aspect: str = ""
    remedies: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.kind != "method":
            raise VocabularyError(f"method {self.id!r}: kind is always 'method'")
        if not self.aspect:
            raise VocabularyError(f"method {self.id!r} names no aspect")

    @property
    def requirement_free(self) -> bool:
        """Whether the method applies to anything (a legal last link of a chain)."""
        return not self.requires

    def to_json(self) -> dict[str, Any]:
        out = super().to_json()
        out["aspect"] = self.aspect
        if self.remedies:
            out["remedies"] = dict(self.remedies)
        return out


#: The core's recorded no-op: requires nothing, expands to nothing, serves every
#: aspect. The only legal chain end for an aspect that does not apply to an
#: asset kind (an expression on a prop) — chosen, it is always recorded.
NOOP = Method(
    NOOP_ID,
    aspect=ANY_ASPECT,
    title="no-op",
    description=(
        "do nothing, and record it: the last link of a chain whose aspect does "
        "not apply to the asset"
    ),
    levels=frozenset({"a"}),
    expand=lambda params, context: (),
)


@dataclass(frozen=True)
class Aspect:
    """Something every asset of a kind gets (locomotion, speech, blink, …).

    ``chain`` is the default order of method ids, first applicable wins; its
    last link requires nothing, or is :data:`NOOP`. ``applies_to`` is the
    entity kinds it makes sense for (empty: all); for any other kind the
    aspect resolves to the recorded no-op.
    """

    name: str
    chain: tuple[str, ...]
    applies_to: frozenset = frozenset()
    description: str = ""
    #: The asset-document field an asset declares its request in (a
    #: character's ``gait``, ``speech``): a declared method choice, reported as
    #: such by ``describe_asset`` and honoured by the compiler.
    declared_by: str = ""
    #: Record falling down the chain even when nothing was requested (reason
    #: ``missing``, so ``--strict-assets`` sees it). For an aspect whose
    #: fallback is a behaviour the asset never had before — speech's pulse on a
    #: baked face — rather than today's long-standing default (a legless walk).
    records_fallback: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.chain:
            raise VocabularyError(f"aspect {self.name!r} needs a name and a non-empty chain")
        object.__setattr__(self, "chain", tuple(self.chain))
        object.__setattr__(self, "applies_to", frozenset(self.applies_to))

    def to_json(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "chain": list(self.chain),
            "applies_to": sorted(self.applies_to),
            "description": self.description,
        }
        if self.declared_by:
            out["declared_by"] = self.declared_by
        if self.records_fallback:
            out["records_fallback"] = True
        return out


@dataclass(frozen=True)
class Choice:
    """One method choice in a policy or a request: ``previz``'s ``FormulaCall`` plus a pin.

    >>> Choice.of({"method": "speech.mouth_flap", "args": {"shapes": 3}}).args
    {'shapes': 3}
    >>> Choice.of("loco.rock").method
    'loco.rock'
    """

    method: str
    args: Mapping[str, Any] = field(default_factory=dict)
    version: str | None = None

    @classmethod
    def of(cls, x: "Choice | str | Mapping[str, Any]") -> "Choice":
        if isinstance(x, Choice):
            return x
        if isinstance(x, str):
            return cls(x)
        if isinstance(x, Mapping) and "method" in x:
            unknown = set(x) - {"method", "args", "version"}
            if unknown:
                raise VocabularyError(
                    f"a method choice takes method/args/version, got {sorted(unknown)}"
                )
            return cls(str(x["method"]), dict(x.get("args") or {}), x.get("version"))
        raise VocabularyError(
            f"a method choice is a method id or {{method, args, version}}, got {x!r}"
        )

    def to_json(self) -> dict[str, Any] | str:
        if not self.args and self.version is None:
            return self.method
        out: dict[str, Any] = {"method": self.method}
        if self.args:
            out["args"] = dict(self.args)
        if self.version is not None:
            out["version"] = self.version
        return out


@dataclass(frozen=True)
class Policy:
    """Per-aspect method orders set by a style (study_the_masters §4).

    The parsed form of a style document's ``policy:`` block; precedence when
    resolving is the author's request, then the shot, then the style, then the
    aspect's chain (:meth:`layered`).

    >>> p = Policy.of({"locomotion": ["loco.bob", {"method": "loco.glide", "args": {"bob": 0}}]})
    >>> [c.method for c in p.choices("locomotion")], p.choices("speech")
    (['loco.bob', 'loco.glide'], ())
    """

    order: Mapping[str, tuple[Choice, ...]] = field(default_factory=dict)

    @classmethod
    def of(cls, x: "Policy | Mapping[str, Any] | None") -> "Policy":
        if isinstance(x, Policy):
            return x
        out: dict[str, tuple[Choice, ...]] = {}
        for aspect, choices in (x or {}).items():
            items = [choices] if isinstance(choices, (str, Mapping)) else list(choices)
            out[str(aspect)] = tuple(Choice.of(c) for c in items)
        return cls(out)

    def choices(self, aspect: str) -> tuple[Choice, ...]:
        return tuple(self.order.get(aspect, ()))

    @staticmethod
    def layered(*policies: "Policy | Mapping[str, Any] | None") -> "Policy":
        """Policies in precedence order (shot before style): the first that names an aspect wins it."""
        out: dict[str, tuple[Choice, ...]] = {}
        for p in policies:
            for aspect, choices in Policy.of(p).order.items():
                out.setdefault(aspect, choices)
        return Policy(out)

    def to_json(self) -> dict[str, list]:
        return {a: [c.to_json() for c in cs] for a, cs in self.order.items()}


def requirement_terms(requires: Iterable[Requirement]) -> tuple[str, ...]:
    """The spelled terms of a requirement tuple."""
    return tuple(str(r) for r in requires)
