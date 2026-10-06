"""Genres: what a kind of animation adds to the core, declared as one object.

ADR 0001 decisions 2-4 and the core study §2.15. A **genre** (cut-out
animation, data visualisation, mathematical explainers, …) extends the core by
*registration*, never by editing a core ``if kind == …`` chain. It is one plain,
declarative :class:`Genre` object — the shape ``shaping`` uses ("a new genre is
one file") — listing what it registers:

- **action kinds** (:class:`ActionKind`): a model, how it occupies time, how
  ``scene.md`` spells it;
- **entity kinds** (:class:`EntityKind`), each naming the property space its
  nodes live in, plus any new **property spaces** and **field kinds** for the
  timing kernel (:mod:`an.timing`);
- **semantic checks** (:class:`SemanticCheck`) that ``an validate`` runs;
- **md sugar** (:class:`DialogueSugar`) on ``scene.md`` dialogue lines;
- **capabilities** and **analysers** (:mod:`an.capabilities`, ADR 0002): the
  capability names its methods require and the derivation of what its assets
  afford;
- **vocabulary** entries — presets, methods, IR-field notes — and **aspects**
  with their default chains (:mod:`an.semantic`, ADR 0003).

Because the object is plain data, a genre is **inspectable before it is
loaded**: :func:`available` reads every installed genre's declaration without
registering anything, which is how an unregistered kind's error can name the
package that provides it.

**Discovery is explicit, never at import time** (decision 3). Importing ``an``
registers no genre. :func:`load` reads the ``an.genres`` entry point group and
registers each genre it finds; ``an.load(project)``, the ``an`` CLI and (later)
the MCP entry call it, and anyone can. A package declares its genre as::

    [project.entry-points."an.genres"]
    cutout_animation = "cutan.genre:CUTOUT"

:func:`register_genre` installs a genre object directly (a test, a notebook, a
genre defined in the same process).

>>> from an.genres import Genre, register_genre, installed, without_genres
>>> with without_genres():
...     installed()
()
>>> demo = Genre("demo_genre", title="Demo")
>>> with without_genres():
...     _ = register_genre(demo)
...     installed()
('demo_genre',)
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib import import_module
from importlib.metadata import EntryPoint, entry_points as _entry_points

from an.genres.registry import (
    CORE_OWNER,
    ActionKind,
    CompilePass,
    RuntimeScript,
    ServiceMissingError,
    SwapDeclaration,
    DialogueSugar,
    EntityKind,
    RegistryError,
    SemanticCheck,
    UnregisteredKindError,
    action_kind,
    action_kind_names,
    entity_kind,
    entity_kind_names,
    register_action_kind,
    register_check,
    register_compile_pass,
    register_runtime_script,
    hook_modules,
    register_service,
    require_service,
    service,
    services,
    register_dialogue_sugar,
    register_entity_kind,
    restore,
    snapshot,
    unregister_owner,
)

#: The entry-point group a genre package declares its :class:`Genre` under.
ENTRY_POINT_GROUP: str = "an.genres"


class GenreError(RegistryError):
    """A genre declaration is malformed, or its entry point does not resolve."""


#: The level of the genre-facing API this ``an`` provides: every hook, registry
#: field and moved path a genre package may rely on. Bumped by each change a
#: genre needs (the P8 seam PRs and each move to ``cutan``, an#225), never
#: decremented. A genre states the lowest level it needs with
#: :func:`require_api_level`, which is how "the genre declares the lowest ``an``
#: it supports" (ADR 0001 decision 8) is said without a version pin: ``an``'s
#: version is assigned by CI at merge, so no PR can name the release it ships in.
#:
#: A genre package must also run against an ``an`` older than this constant:
#: it reads ``getattr(an.genres, "API_LEVEL", 0)`` before calling
#: :func:`require_api_level`, and raises its own typed error when it is missing.
#:
#: Levels (one line each; ``tests/test_genre_gate.py`` holds the list complete):
#:
#: 1 = moved-module shims (``an._shims.moved_to_package``) and this check (an#296, P8 B0a).
#: 2 = the cut-out genre's move (an#225): ``Genre.services``, ``ActionKind.lowering``,
#:     ``EntityKind.swap_declaration``, ``an.stage.rig``.
#: 3 = the public rig builder (an#338): ``an.stage.rig.build_rig_subtree``, ``rig_origin``,
#:     ``RigDocument`` (``origin``), ``omit_unset_rig_fields``, ``an.stage.compile.note_raster_rig``.
#: 4 = the bones' rest pose (an#339): ``an.stage.rig.register_rest_pose_migration``,
#:     ``rig_rest_problems``, ``RigDocument.rest_rotation``.
#: 5 = nested chains (an#340): ``build_rig_subtree(skip_slots=)``, ``slot_parent_chain``,
#:     ``slot_node_paths``, ``rig_problems``, ``rig_affordances``, ``RigError``, ``rig.hierarchy``.
API_LEVEL: int = 5


class GenreAPILevelError(GenreError, ImportError):
    """A genre package needs a newer ``an`` than the one installed."""


def require_api_level(level: int, *, package: str) -> None:
    """Refuse, with an upgrade hint, when this ``an`` is older than ``package`` needs.

    A genre package calls it at import (``require_api_level(3, package="cutan")``).

    >>> require_api_level(1, package="demo")
    >>> try:
    ...     require_api_level(API_LEVEL + 1, package="demo")
    ... except GenreAPILevelError as e:
    ...     print(str(e).startswith(f"demo needs an.genres API level {API_LEVEL + 1}"))
    True
    """
    if API_LEVEL < level:
        raise GenreAPILevelError(
            f"{package} needs an.genres API level {level} or higher; this an "
            f"provides {API_LEVEL}. Upgrade an (pip install -U an), or install "
            f"the {package} release that matches it."
        )


@dataclass(frozen=True)
class Genre:
    """A genre: one plain, declarative object listing what it registers.

    ``name`` is the genre's persisted slug (``cutout_animation``); it is also
    the owner of every entry it registers. ``package`` names the distribution
    that ships it, for error messages. Every collection defaults to empty, so a
    later phase adds a field (compile passes, vocabulary, capabilities) without
    touching any genre that does not use it.

    ``spaces`` are :class:`an.timing.spaces.PropertySpace` objects and
    ``field_kinds`` are ``(name, factory)`` pairs for
    :func:`an.timing.kinds.register_kind`. ``capabilities`` are
    :class:`an.capabilities.Capability` objects, ``analysers``
    :class:`an.capabilities.Analyser` objects, ``vocabulary``
    :class:`an.semantic.Entry` objects (methods included) and ``aspects``
    :class:`an.semantic.Aspect` objects; registering the genre checks the whole
    (:func:`an.semantic.check_registry`): every aspect's chain ends in a method
    that requires nothing, and every requirement names a registered capability.

    ``library`` names the package whose data root holds the genre's asset
    library and its projects (``~/.local/share/<library>``, ADR 0005, plan §1
    decision 7); empty means the core's (``an``). It is not ``package``: the
    distribution that ships a genre and the root its data lives under can
    differ (the cut-out genre ships inside ``an`` today, while its library is
    already ``cutan``'s). The core never names a genre's library itself —
    a project made in a genre asks the genre (:func:`genre_library`).
    """

    name: str
    title: str = ""
    description: str = ""
    package: str = ""
    library: str = ""
    action_kinds: tuple[ActionKind, ...] = ()
    entity_kinds: tuple[EntityKind, ...] = ()
    spaces: tuple = ()
    field_kinds: tuple = ()
    checks: tuple[SemanticCheck, ...] = ()
    dialogue_sugar: tuple[DialogueSugar, ...] = ()
    capabilities: tuple = ()
    analysers: tuple = ()
    vocabulary: tuple = ()
    aspects: tuple = ()
    #: Steps the genre adds to an engine's compiler, and builders for its
    #: entity kinds (:class:`CompilePass`; an#247).
    compile_passes: tuple[CompilePass, ...] = ()
    #: Code the genre adds to an engine's runtime: its visual kinds
    #: (:class:`RuntimeScript`; an#247).
    runtime_scripts: tuple[RuntimeScript, ...] = ()
    #: ``{name: object or "module:attr"}`` the genre offers the core by name
    #: (:func:`register_service`; an#225): the CLI namespaces it adds
    #: (``cli.<namespace>``), its lip-sync providers (``lipsync.<name>``), and the
    #: other places the core asks "is there a genre that does this?".
    services: dict[str, object] = field(default_factory=dict)

    def provides(self) -> dict[str, tuple[str, ...]]:
        """What this genre registers, by registry, as names — without registering it.

        >>> Genre("g", action_kinds=()).provides()["action kinds"]
        ()
        """
        return {
            "action kinds": tuple(k.name for k in self.action_kinds),
            "entity kinds": tuple(k.name for k in self.entity_kinds),
            "spaces": tuple(s.name for s in self.spaces),
            "field kinds": tuple(name for name, _ in self.field_kinds),
            "checks": tuple(c.name for c in self.checks),
            "dialogue sugar": tuple(s.name for s in self.dialogue_sugar),
            "capabilities": tuple(c.name for c in self.capabilities),
            "analysers": tuple(a.kind for a in self.analysers),
            "vocabulary": tuple(e.id for e in self.vocabulary),
            "aspects": tuple(a.name for a in self.aspects),
            "compile passes": tuple(p.name for p in self.compile_passes),
            "runtime scripts": tuple(s.name for s in self.runtime_scripts),
            "services": tuple(self.services),
        }


#: Genres registered in this process, by name.
_INSTALLED: dict[str, Genre] = {}


def register_genre(
    genre: Genre, *, replace: bool = False, check_capabilities: bool = True
) -> Genre:
    """Register everything ``genre`` declares, owned by ``genre.name``.

    Idempotent for the same object: registering a genre that is already
    installed is a no-op, so :func:`load` can be called from every entry point.
    A different object under an installed name raises unless ``replace``.
    All or nothing: a registration that fails part-way leaves no trace.
    ``check_capabilities=False`` defers the "every requirement names a
    registered capability" check to the caller (:func:`load` runs it once all
    genres are in, so a genre extending another loads in any order).
    """
    if not isinstance(genre, Genre):
        raise GenreError(f"not a Genre: {genre!r}")
    if not genre.name or genre.name == CORE_OWNER:
        raise GenreError(f"a genre needs a name other than {CORE_OWNER!r}")
    current = _INSTALLED.get(genre.name)
    if current is genre:
        return genre
    if current is not None and not replace:
        raise GenreError(
            f"a different genre named {genre.name!r} is already registered; "
            "pass replace=True to replace it"
        )
    state, timing_state, sem_state = (
        snapshot(),
        _timing_snapshot(),
        _semantic_snapshot(),
    )
    try:
        if current is not None:
            _uninstall(genre.name)
        _install(genre, check_capabilities=check_capabilities)
    except Exception:
        restore(state)
        _timing_restore(timing_state)
        _semantic_restore(sem_state)
        raise
    _INSTALLED[genre.name] = genre
    return genre


def _install(genre: Genre, *, check_capabilities: bool = True) -> None:
    from an.timing.kinds import register_kind
    from an.timing.spaces import register_space

    owner = genre.name
    for name, factory in genre.field_kinds:
        register_kind(name, factory, owner=owner)
    for space in genre.spaces:
        register_space(space, owner=owner)
    for kind in genre.entity_kinds:
        register_entity_kind(kind, owner=owner)
    for kind in genre.action_kinds:
        register_action_kind(kind, owner=owner)
    for check in genre.checks:
        register_check(check, owner=owner)
    for sugar in genre.dialogue_sugar:
        register_dialogue_sugar(sugar, owner=owner)
    for compile_pass in genre.compile_passes:
        register_compile_pass(compile_pass, owner=owner)
    for script in genre.runtime_scripts:
        register_runtime_script(script, owner=owner)
    for name, target in genre.services.items():
        register_service(name, target, owner=owner)
    if genre.capabilities or genre.analysers or genre.vocabulary or genre.aspects:
        _install_semantics(genre, check_capabilities=check_capabilities)


def _install_semantics(genre: Genre, *, check_capabilities: bool = True) -> None:
    """Capabilities, analysers, vocabulary and aspects (ADRs 0002, 0003), then the check."""
    from an import capabilities as caps
    from an import semantic as sem

    owner = genre.name
    try:
        for cap in genre.capabilities:
            caps.register_capability(cap, owner=owner)
        for analyser in genre.analysers:
            caps.register_analyser(analyser, owner=owner)
        for entry in genre.vocabulary:
            sem.register_entry(entry, owner=owner)
        for aspect in genre.aspects:
            sem.register_aspect(aspect, owner=owner)
    except (caps.CapabilityError, sem.VocabularyError) as e:
        raise GenreError(f"genre {genre.name!r}: {e}") from e
    problems = sem.check_registry(owner=owner, capabilities=check_capabilities)
    if problems:
        raise GenreError(
            f"genre {genre.name!r} registers an unsound vocabulary:\n  - "
            + "\n  - ".join(problems)
        )


def _uninstall(name: str) -> None:
    unregister_owner(name)
    _timing_drop_owner(name)
    _semantic_drop_owner(name)
    _INSTALLED.pop(name, None)


# The capability and vocabulary registries (P7) sit beside the core's tables:
# a genre's entries there come out with it, exactly like its kinds. Imported
# lazily: `an.semantic` is below `an.ir` but above this registry module.


def _semantic_snapshot() -> tuple:
    from an import capabilities as caps
    from an.semantic import registry as sem

    return caps.snapshot(), sem.snapshot()


def _semantic_restore(state: tuple) -> None:
    from an import capabilities as caps
    from an.semantic import registry as sem

    caps.restore(state[0])
    sem.restore(state[1])


def _semantic_drop_owner(owner: str) -> None:
    from an import capabilities as caps
    from an.semantic import registry as sem

    caps.drop_owner(owner)
    sem.drop_owner(owner)


# The timing kernel's registries are P1's; a genre's spaces and field kinds go
# there with the genre as owner (so the contract files never list them).


def _timing_tables() -> list[tuple[dict, dict]]:
    from an.timing import kinds, spaces

    return [(kinds._REGISTRY, kinds._OWNERS), (spaces._REGISTRY, spaces._OWNERS)]


def _timing_snapshot() -> list[tuple[dict, dict]]:
    return [(dict(r), dict(o)) for r, o in _timing_tables()]


def _timing_restore(state: list[tuple[dict, dict]]) -> None:
    for (registry, owners), (saved_r, saved_o) in zip(_timing_tables(), state):
        registry.clear()
        registry.update(saved_r)
        owners.clear()
        owners.update(saved_o)
    for space in _space_caches():
        space._resolved.clear()


def _timing_drop_owner(owner: str) -> None:
    for registry, owners in _timing_tables():
        for name in [k for k, o in owners.items() if o == owner]:
            registry.pop(name, None)
            owners.pop(name, None)


def _space_caches():
    from an.timing import spaces

    return list(spaces._REGISTRY.values())


def installed() -> tuple[str, ...]:
    """The names of the genres registered in this process, in registration order."""
    return tuple(_INSTALLED)


def installed_genre(name: str) -> Genre | None:
    return _INSTALLED.get(name)


# -----------------------------------------------------------------------------
# Discovery
# -----------------------------------------------------------------------------


#: Genres the ``an`` distribution itself ships, as entry-point values. They are
#: found by :func:`load` WITHOUT relying on installed metadata: an editable
#: install made before the ``an.genres`` group existed never refreshes its
#: ``dist-info``, and a missing entry point must never silently drop a genre
#: that ships in the same distribution as the core (review-244 S1). Still
#: explicit discovery (only :func:`load` reads it, never an import). Every genre is
#: external now: the cut-out genre moved to ``cutan`` (an#225) and comes through
#: the ``an.genres`` entry point alone.
IN_DISTRIBUTION_GENRES: tuple[tuple[str, str], ...] = ()


def genre_library(name: str | None, *, default: str = "an") -> str:
    """The package whose data root holds genre ``name``'s library and projects.

    ``default`` (the core package) for no genre, an unknown one, or a genre
    that declares none. Reads the genres installed in this process (call
    :func:`load` first, as every entry point does).

    >>> genre_library(None)
    'an'
    """
    genre = installed_genre(name) if name else None
    return (genre.library if genre is not None else "") or default


def genre_entry_points(*, group: str = ENTRY_POINT_GROUP) -> tuple[EntryPoint, ...]:
    """The installed ``an.genres`` entry points (nothing is imported)."""
    return tuple(_entry_points(group=group))


def discovered_entry_points(
    *, entry_points: Iterable[EntryPoint] | None = None, builtin: bool = True
) -> tuple[EntryPoint, ...]:
    """The in-distribution genres (``builtin``; none since the cut-out genre moved to
    ``cutan``, an#225) merged with ``entry_points`` (default: the installed ones),
    de-duplicated by name — the in-distribution declaration first.

    >>> [ep.name for ep in discovered_entry_points(entry_points=())]
    []
    """
    eps = genre_entry_points() if entry_points is None else tuple(entry_points)
    builtins = (
        tuple(EntryPoint(n, v, ENTRY_POINT_GROUP) for n, v in IN_DISTRIBUTION_GENRES)
        if builtin
        else ()
    )
    out: dict[str, EntryPoint] = {}
    for ep in (*builtins, *eps):
        out.setdefault(ep.name, ep)
    return tuple(out.values())


#: Resolved declarations, by entry point: reading a genre imports its module
#: once per process (review-244 N6).
_RESOLVED: dict[tuple[str, str], Genre] = {}


def _resolve(ep: EntryPoint) -> Genre:
    key = (ep.name, ep.value)
    if key in _RESOLVED:
        return _RESOLVED[key]
    try:
        genre = ep.load()
    except Exception as e:  # noqa: BLE001 — re-raised, named
        raise GenreError(
            f"the `{ENTRY_POINT_GROUP}` entry point {ep.name!r} = {ep.value!r} "
            f"does not import: {type(e).__name__}: {e}"
        ) from e
    if not isinstance(genre, Genre):
        raise GenreError(
            f"the `{ENTRY_POINT_GROUP}` entry point {ep.name!r} = {ep.value!r} "
            f"names a {type(genre).__name__}, not an an.genres.Genre"
        )
    _RESOLVED[key] = genre
    return genre


def available(
    *, entry_points: Iterable[EntryPoint] | None = None, builtin: bool = True
) -> dict[str, Genre]:
    """Every discoverable genre's declaration, by name — read, never registered.

    The in-distribution genres plus the entry points (:func:`discovered_entry_points`).
    A genre whose entry point does not import is left out (its error is what
    :func:`load` raises).
    """
    out: dict[str, Genre] = {}
    for ep in discovered_entry_points(entry_points=entry_points, builtin=builtin):
        try:
            genre = _resolve(ep)
        except GenreError:
            continue
        out.setdefault(genre.name, genre)
    return out


def load(
    *, entry_points: Iterable[EntryPoint] | None = None, builtin: bool = True
) -> tuple[str, ...]:
    """Register every discoverable genre. Idempotent.

    Discoverable: the genres the ``an`` distribution ships
    (:data:`IN_DISTRIBUTION_GENRES`, unless ``builtin=False``) and the
    ``an.genres`` entry points (``entry_points`` replaces the installed ones —
    tests, a host that curates). Returns the names of the genres registered
    after the call. Never called at import time: the CLI, ``an.load(project)``
    and the MCP entry call it, so a document naming a genre's kind validates to
    that kind's model.
    """
    seen: set[str] = set()
    for ep in discovered_entry_points(entry_points=entry_points, builtin=builtin):
        genre = _resolve(ep)
        if genre.name in seen:
            continue  # the same genre under two entry-point names
        seen.add(genre.name)
        register_genre(genre, check_capabilities=False)
    _check_capabilities_of(seen)
    return installed()


def _check_capabilities_of(names: Iterable[str]) -> None:
    """Every requirement of these genres names a capability registered by SOME
    genre — checked once all are in, so load order never matters (review-256 S7)."""
    from an import semantic as sem

    problems = [p for name in names for p in sem.check_registry(owner=name)]
    if problems:
        raise GenreError(
            "the loaded genres register an unsound vocabulary:\n  - "
            + "\n  - ".join(problems)
        )


def genres_declaring(test) -> tuple[str, ...]:
    """The installed genres (loaded or not) whose declaration passes ``test``.

    Each is named as ``genre (package)``. Reading declarations imports the
    genre modules but registers nothing.
    """
    candidates = {**available(), **_INSTALLED}
    return tuple(
        f"{g.name} ({g.package})" if g.package else g.name
        for g in candidates.values()
        if test(g)
    )


def providers_of(kind: str, *, registry: str = "action kinds") -> tuple[str, ...]:
    """The installed genres (loaded or not) that declare ``kind`` in ``registry``
    (a key of :meth:`Genre.provides`). Used by the unregistered-kind errors."""
    return genres_declaring(lambda g: kind in g.provides().get(registry, ()))


# -----------------------------------------------------------------------------
# Which property space a target lives in
# -----------------------------------------------------------------------------


def entity_space_resolver(entities: Iterable, *, default: str | None = None):
    """``target -> PropertySpace``: the space its ENTITY's kind declares.

    The ONE policy for "what are this target's properties" (review-244 S7):
    ``an validate``'s generic target check and the compiler's keyframe check
    both use it. A target's entity is its first path segment; a target with no
    entity (the stage camera's ``root``), or an entity whose kind is
    unregistered or declares no space, gets ``default`` — the timing default
    :data:`an.timing.spaces.DFLT_TIMELINE_SPACE` when ``None``.

    The default EVALUATOR agrees since an#245: the stage's compiled document
    records each entity whose kind declares another space
    (``meta.entity_spaces``), and ``timeline_from_compiled`` resolves by it.

    >>> from an.ir.schema import AssetRef
    >>> space_of = entity_space_resolver([AssetRef(kind="prop", id="lamp", store="props", ref="l")])
    >>> space_of("lamp/shade").name, space_of("root").name
    ('stage.node', 'stage.node')
    """
    from an.timing import spaces

    fallback = spaces.get_space(default or spaces.DFLT_TIMELINE_SPACE or "stage.node")
    by_entity = {}
    for entity in entities:
        kind = entity_kind(entity.kind)
        if kind is not None and kind.space is not None:
            by_entity[entity.id] = spaces.get_space(kind.space)

    def space_of(target: str):
        return by_entity.get(target.split("/", 1)[0], fallback)

    return space_of


# -----------------------------------------------------------------------------
# Isolation (tests, multi-tenant hosts)
# -----------------------------------------------------------------------------


@contextmanager
def without_genres() -> Iterator[None]:
    """Run a block with no genre registered (the core alone), then restore.

    >>> with without_genres():
    ...     action_kind("play") is None
    True
    """
    state = (snapshot(), _timing_snapshot(), dict(_INSTALLED), _semantic_snapshot())
    try:
        for name in list(_INSTALLED):
            _uninstall(name)
        for owner in {o for o in _all_owners() if o != CORE_OWNER}:
            unregister_owner(owner)
        yield
    finally:
        restore(state[0])
        _timing_restore(state[1])
        _INSTALLED.clear()
        _INSTALLED.update(state[2])
        _semantic_restore(state[3])


def _all_owners() -> set[str]:
    from an.genres.registry import owners

    return set(owners())


__all__ = [
    "API_LEVEL",
    "ENTRY_POINT_GROUP",
    "GenreAPILevelError",
    "require_api_level",
    "ActionKind",
    "CompilePass",
    "RuntimeScript",
    "ServiceMissingError",
    "SwapDeclaration",
    "hook_modules",
    "register_service",
    "require_service",
    "service",
    "services",
    "DialogueSugar",
    "EntityKind",
    "Genre",
    "GenreError",
    "RegistryError",
    "SemanticCheck",
    "UnregisteredKindError",
    "action_kind",
    "action_kind_names",
    "available",
    "entity_kind",
    "entity_kind_names",
    "entity_space_resolver",
    "IN_DISTRIBUTION_GENRES",
    "discovered_entry_points",
    "genre_entry_points",
    "genres_declaring",
    "installed",
    "genre_library",
    "installed_genre",
    "load",
    "providers_of",
    "register_genre",
    "without_genres",
]
