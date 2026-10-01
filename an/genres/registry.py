"""The core's open registries: action kinds, entity kinds, semantic checks, md sugar, compile passes.

ADR 0001 decision 2 ("the IR is open at the type level; genres register, never
edit") and decision 4 (the first batch of registries). Each registry is a plain
name-keyed table with an **owner** per entry, so the core can tell its own
entries from a genre's (the timing contract does the same, review-237 S3), and a
test can take every genre out and put it back (:func:`snapshot` /
:func:`restore`).

This module imports nothing from ``an.ir``: the schema consults it while it
validates (a document's ``kind: play`` is looked up here), so it must sit below
the schema in the import graph. That is also why an entry holds its model class
and hooks as plain values: the registry never needs to know what they are.

>>> isinstance(action_kind("tween"), ActionKind)  # core kinds register on import of the IR
True
>>> "play" in action_kind_names(owner=CORE_OWNER)  # a genre's kind is never the core's
False
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

#: The owner of every entry the core registers itself. A genre registers under
#: its own name (:attr:`an.genres.Genre.name`).
CORE_OWNER: str = "an"


class RegistryError(ValueError):
    """A registration is malformed or collides with one already made."""


class UnregisteredKindError(RegistryError):
    """A document names a kind no loaded genre registered.

    The message names the installed genres that *could* provide it (read from
    their declarations, which are inspectable without loading them), so the fix
    is one line: ``an.genres.load()``, or installing the package named.
    """

    def __init__(
        self,
        what: str,
        name: str,
        *,
        known: Iterable[str] = (),
        providers: Iterable[str] = (),
        where: str = "",
    ) -> None:
        self.what = what
        self.name = name
        self.known = tuple(sorted(known))
        self.providers = tuple(providers)
        prefix = f"{where}: " if where else ""
        if self.providers:
            hint = (
                f"it is provided by the genre(s) {list(self.providers)}, which "
                "are installed but not loaded — call `an.genres.load()` (the CLI "
                "and `an.load(project)` do) before reading the document"
            )
        else:
            hint = (
                "no installed genre provides it — install the genre package that "
                "defines it (it registers through the `an.genres` entry point)"
            )
        super().__init__(
            f"{prefix}{what} {name!r} is not registered; {hint}. "
            f"Registered: {list(self.known)}."
        )


# -----------------------------------------------------------------------------
# Entries
# -----------------------------------------------------------------------------

#: ``(action, extent) -> seconds``: the natural length of a leaf. ``extent`` is
#: the caller's per-call resolver for a leaf that has no explicit duration (the
#: compiler and ``an validate`` pass one bound to the entity's descriptor), or
#: ``None``.
DurationHook = Callable[[Any, Any], float]


@dataclass(frozen=True)
class ActionKind:
    """One kind of action: its model, how it occupies time, how ``scene.md`` spells it.

    - ``model`` validates a document's action of this kind. A genre's model
      subclasses :class:`an.ir.schema.ExtensionAction`; the core's are the
      static members of the schema's union.
    - ``duration`` is a LEAF's natural length; a leaf flattens to one
      ``FlatAction`` on ``[t, t + duration]`` and advances a ``sequence`` by it.
    - ``flatten`` replaces that default for kinds that place themselves
      differently (``set`` does not advance the cursor) or that hold children
      (``sequence``): ``flatten(action, t, ctx) -> new cursor``, where ``ctx``
      is :class:`an.ir.compose.FlattenContext`.
    - ``children`` lists a composite's child actions, so generic walkers
      (validation) reach every leaf without knowing the kind.
    - ``read_md`` / ``write_md`` are the ``scene.md`` ``yaml actions`` hooks:
      ``read_md(item, index=i) -> action`` (``start:`` already removed when
      ``md_start``) and ``write_md(action) -> dict`` (without ``start``).
      A kind with no ``read_md`` has no ``scene.md`` form.
    """

    name: str
    model: type
    duration: DurationHook | None = None
    flatten: Callable[..., float] | None = None
    children: Callable[[Any], Iterable[Any]] | None = None
    read_md: Callable[..., Any] | None = None
    write_md: Callable[[Any], dict | None] | None = None
    #: Does ``start:`` in ``scene.md`` wrap this kind in ``sequence(delay(start), …)``?
    md_start: bool = True
    description: str = ""
    #: The kind's vocabulary version (ADR 0003): bump when what an action of
    #: this kind compiles to changes for the same fields, so the shots that use
    #: it re-render visibly (:mod:`an.semantic` folds it into the shot digest).
    version: str = "1"


@dataclass(frozen=True)
class EntityKind:
    """One kind of entity (``AssetRef.kind``): what its nodes' properties are.

    ``space`` names the registered :class:`an.timing.spaces.PropertySpace` its
    nodes' properties live in (``None``: the entity has no animatable nodes, as
    a voice); ``store`` is the project-mall store its ``ref`` keys into.
    """

    name: str
    space: str | None = None
    store: str | None = None
    description: str = ""
    #: The kind's vocabulary version (ADR 0003), as :attr:`ActionKind.version`.
    version: str = "1"


#: When a check runs: once before the shots, once per shot, once after them.
CheckStage = Literal["scene", "shot", "finish"]
CHECK_STAGES: tuple[str, ...] = ("scene", "shot", "finish")


@dataclass(frozen=True)
class SemanticCheck:
    """One semantic-validation check: ``run(ctx)`` adds findings to ``ctx.report``.

    ``ctx`` is :class:`an.ir.validate.ValidationContext`; a ``shot`` check is
    called once per shot with ``ctx.shot`` set. Within a stage, checks run by
    ``order`` (then registration order), so a genre's check lands exactly where
    it belongs in the report.
    """

    name: str
    run: Callable[[Any], None]
    stage: CheckStage = "shot"
    order: float = 0.0
    description: str = ""

    def __post_init__(self) -> None:
        if self.stage not in CHECK_STAGES:
            raise RegistryError(
                f"check {self.name!r}: stage must be one of {CHECK_STAGES}, "
                f"got {self.stage!r}"
            )


#: The bracket pairs a GENRE may claim on a ``scene.md`` dialogue line. The
#: line grammar has three: ``(…)`` (timing) and ``{…}`` (delivery direction)
#: are the core's own and never registered; ``[…]`` is the one left for sugar.
DIALOGUE_BRACKETS: dict[str, str] = {"[": "]"}


@dataclass(frozen=True)
class DialogueSugar:
    """``scene.md`` sugar on a dialogue line: one bracket pair, one ``Dialogue`` field.

    ``parse(content) -> value`` turns what is between the brackets into the
    field's value (raise ``ValueError(why)`` to refuse it); ``format(line) ->
    str | None`` is the inverse (the content, without brackets, or ``None`` when
    the line carries none). The cut-out genre's ``[emotion]`` is one.
    """

    name: str
    opener: str
    field: str
    parse: Callable[[str], Any]
    format: Callable[[Any], str | None]
    description: str = ""

    def __post_init__(self) -> None:
        if self.opener not in DIALOGUE_BRACKETS:
            raise RegistryError(
                f"dialogue sugar {self.name!r}: opener must be one of "
                f"{sorted(DIALOGUE_BRACKETS)}, got {self.opener!r}"
            )

    @property
    def closer(self) -> str:
        return DIALOGUE_BRACKETS[self.opener]


# -----------------------------------------------------------------------------
# The tables
# -----------------------------------------------------------------------------


@dataclass
class _Table:
    """A name-keyed registry with an owner per entry."""

    what: str
    entries: dict[str, Any] = field(default_factory=dict)
    owners: dict[str, str] = field(default_factory=dict)

    def register(self, name: str, entry: Any, *, owner: str, replace: bool) -> Any:
        if not name:
            raise RegistryError(f"a {self.what} needs a non-empty name")
        if name in self.entries and not replace:
            raise RegistryError(
                f"{self.what} {name!r} is already registered by "
                f"{self.owners[name]!r}; pass replace=True to replace it"
            )
        self.entries[name] = entry
        self.owners[name] = owner
        return entry

    def names(self, *, owner: str | None = None) -> tuple[str, ...]:
        return tuple(
            k for k in self.entries if owner is None or self.owners[k] == owner
        )

    def drop_owner(self, owner: str) -> None:
        for name in [k for k, o in self.owners.items() if o == owner]:
            del self.entries[name]
            del self.owners[name]


_ACTION_KINDS = _Table("action kind")
_ENTITY_KINDS = _Table("entity kind")
_CHECKS = _Table("semantic check")
_DIALOGUE_SUGAR = _Table("dialogue sugar")
_COMPILE_PASSES = _Table("compile pass")
_TABLES: tuple[_Table, ...] = (
    _ACTION_KINDS,
    _ENTITY_KINDS,
    _CHECKS,
    _DIALOGUE_SUGAR,
    _COMPILE_PASSES,
)


def register_action_kind(
    kind: ActionKind, *, owner: str = CORE_OWNER, replace: bool = False
) -> ActionKind:
    """Register an action kind. Its model's ``kind`` must default to its name.

    >>> from pydantic import BaseModel
    >>> class Bad(BaseModel):
    ...     kind: str = "other"
    >>> register_action_kind(ActionKind("wave", Bad), owner="demo")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    an.genres.registry.RegistryError: action kind 'wave': ...
    """
    declared = getattr(kind.model, "model_fields", {}).get("kind")
    if declared is None or declared.default != kind.name:
        raise RegistryError(
            f"action kind {kind.name!r}: its model {kind.model.__name__} must "
            f"declare `kind` defaulting to {kind.name!r} (a Literal), so a "
            "document that names it validates to it"
        )
    return _ACTION_KINDS.register(kind.name, kind, owner=owner, replace=replace)


def action_kind(name: str) -> ActionKind | None:
    """The registered kind called ``name``, or ``None``."""
    return _ACTION_KINDS.entries.get(name)


def action_kind_names(*, owner: str | None = None) -> tuple[str, ...]:
    """Registered action-kind names in registration order; ``owner``'s only when given."""
    return _ACTION_KINDS.names(owner=owner)


def action_kind_owner(name: str) -> str | None:
    return _ACTION_KINDS.owners.get(name)


def register_entity_kind(
    kind: EntityKind, *, owner: str = CORE_OWNER, replace: bool = False
) -> EntityKind:
    """Register an entity kind (a value ``AssetRef.kind`` may take)."""
    return _ENTITY_KINDS.register(kind.name, kind, owner=owner, replace=replace)


def entity_kind(name: str) -> EntityKind | None:
    return _ENTITY_KINDS.entries.get(name)


def entity_kind_names(*, owner: str | None = None) -> tuple[str, ...]:
    return _ENTITY_KINDS.names(owner=owner)


def register_check(
    check: SemanticCheck, *, owner: str = CORE_OWNER, replace: bool = False
) -> SemanticCheck:
    """Register a semantic-validation check (run by ``an.ir.validate.validate_semantic``)."""
    return _CHECKS.register(check.name, check, owner=owner, replace=replace)


def checks(stage: str) -> tuple[SemanticCheck, ...]:
    """The registered checks of ``stage``, in run order (``order``, then registration)."""
    found = [
        (c.order, i, c)
        for i, c in enumerate(_CHECKS.entries.values())
        if c.stage == stage
    ]
    return tuple(c for _o, _i, c in sorted(found, key=lambda x: (x[0], x[1])))


def check_names(*, owner: str | None = None) -> tuple[str, ...]:
    return _CHECKS.names(owner=owner)


def register_dialogue_sugar(
    sugar: DialogueSugar, *, owner: str = CORE_OWNER, replace: bool = False
) -> DialogueSugar:
    """Register ``scene.md`` dialogue sugar. One sugar per bracket pair."""
    for name, other in _DIALOGUE_SUGAR.entries.items():
        if other.opener == sugar.opener and name != sugar.name and not replace:
            raise RegistryError(
                f"dialogue sugar {sugar.name!r}: the {sugar.opener}…{sugar.closer} "
                f"brackets are already {name!r}'s"
            )
    return _DIALOGUE_SUGAR.register(sugar.name, sugar, owner=owner, replace=replace)


def dialogue_sugar(opener: str) -> DialogueSugar | None:
    """The sugar registered for the bracket ``opener``, or ``None``."""
    return next(
        (s for s in _DIALOGUE_SUGAR.entries.values() if s.opener == opener), None
    )


def dialogue_sugars() -> tuple[DialogueSugar, ...]:
    return tuple(_DIALOGUE_SUGAR.entries.values())


# -----------------------------------------------------------------------------
# Compile passes (ADR 0001 decision 4; an#247)
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class CompilePass:
    """One step a genre adds to an engine's COMPILER (shot -> compiled document).

    A compiler (``compiler``: today ``"stage"``, :mod:`an.stage.compile`) runs
    its own passes plus every registered one, in ``order``. A pass with
    ``builds`` set is an ENTITY BUILDER instead: the compiler's scene pass calls
    it for each entity of that kind (the cut-out genre's ``rig`` builds a
    ``character``); builders with a lower ``order`` build all their entities
    first (the stage's backdrop before the cast), equal orders in entity order.

    ``run`` is the callable, or ``"module:function"``, resolved on first use --
    so a genre is inspectable (:func:`an.genres.available`) without importing
    the engine its passes target. What ``run`` receives is the compiler's
    business (the stage hands a pass its ``CompileState``, a builder the entity
    and the scene being built); the core never calls it.
    """

    name: str
    run: Callable[..., Any] | str
    order: float = 0.0
    compiler: str = "stage"
    builds: str | None = None
    description: str = ""

    def resolve(self) -> Callable[..., Any]:
        """The callable ``run`` names.

        >>> CompilePass("p", "math:sqrt").resolve()(4.0)
        2.0
        """
        if callable(self.run):
            return self.run
        module, _, attr = self.run.partition(":")
        if not module or not attr:
            raise RegistryError(
                f"compile pass {self.name!r}: run={self.run!r} is neither a callable "
                "nor 'module:function'"
            )
        from importlib import import_module

        return getattr(import_module(module), attr)


def register_compile_pass(
    compile_pass: CompilePass, *, owner: str = CORE_OWNER, replace: bool = False
) -> CompilePass:
    """Register a compile pass (or an entity builder) under its name."""
    return _COMPILE_PASSES.register(
        compile_pass.name, compile_pass, owner=owner, replace=replace
    )


def compile_passes(compiler: str) -> tuple[CompilePass, ...]:
    """The registered passes of ``compiler`` (builders excluded), in run order."""
    found = [
        p for p in _COMPILE_PASSES.entries.values()
        if p.compiler == compiler and p.builds is None
    ]
    return tuple(sorted(found, key=lambda p: (p.order, p.name)))


def entity_builders(compiler: str) -> dict[str, CompilePass]:
    """``{entity kind: builder}`` registered for ``compiler``."""
    return {
        p.builds: p
        for p in _COMPILE_PASSES.entries.values()
        if p.compiler == compiler and p.builds is not None
    }


def compile_pass_names(*, owner: str | None = None) -> tuple[str, ...]:
    return _COMPILE_PASSES.names(owner=owner)


# -----------------------------------------------------------------------------
# Taking genres out and putting them back
# -----------------------------------------------------------------------------


def unregister_owner(owner: str) -> None:
    """Remove every entry ``owner`` registered, from every table."""
    if owner == CORE_OWNER:
        raise RegistryError("the core's own entries cannot be unregistered")
    for table in _TABLES:
        table.drop_owner(owner)


def owners() -> tuple[str, ...]:
    """Every owner with at least one entry, the core first."""
    seen = dict.fromkeys(o for t in _TABLES for o in t.owners.values())
    return tuple(sorted(seen, key=lambda o: (o != CORE_OWNER, o)))


def snapshot() -> tuple:
    """The state of every table, for :func:`restore`."""
    return tuple((dict(t.entries), dict(t.owners)) for t in _TABLES)


def restore(state: tuple) -> None:
    for table, (entries, owners_) in zip(_TABLES, state):
        table.entries.clear()
        table.entries.update(entries)
        table.owners.clear()
        table.owners.update(owners_)
