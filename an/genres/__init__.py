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
- **md sugar** (:class:`DialogueSugar`) on ``scene.md`` dialogue lines.

Because the object is plain data, a genre is **inspectable before it is
loaded**: :func:`available` reads every installed genre's declaration without
registering anything, which is how an unregistered kind's error can name the
package that provides it.

**Discovery is explicit, never at import time** (decision 3). Importing ``an``
registers no genre. :func:`load` reads the ``an.genres`` entry point group and
registers each genre it finds; ``an.load(project)``, the ``an`` CLI and (later)
the MCP entry call it, and anyone can. A package declares its genre as::

    [project.entry-points."an.genres"]
    cutout_animation = "an.genres.cutout:CUTOUT"

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
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import EntryPoint, entry_points as _entry_points

from an.genres.registry import (
    CORE_OWNER,
    ActionKind,
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
    :func:`an.timing.kinds.register_kind`.
    """

    name: str
    title: str = ""
    description: str = ""
    package: str = ""
    action_kinds: tuple[ActionKind, ...] = ()
    entity_kinds: tuple[EntityKind, ...] = ()
    spaces: tuple = ()
    field_kinds: tuple = ()
    checks: tuple[SemanticCheck, ...] = ()
    dialogue_sugar: tuple[DialogueSugar, ...] = ()

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
        }


#: Genres registered in this process, by name.
_INSTALLED: dict[str, Genre] = {}


def register_genre(genre: Genre, *, replace: bool = False) -> Genre:
    """Register everything ``genre`` declares, owned by ``genre.name``.

    Idempotent for the same object: registering a genre that is already
    installed is a no-op, so :func:`load` can be called from every entry point.
    A different object under an installed name raises unless ``replace``.
    All or nothing: a registration that fails part-way leaves no trace.
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
    state, timing_state = snapshot(), _timing_snapshot()
    try:
        if current is not None:
            _uninstall(genre.name)
        _install(genre)
    except Exception:
        restore(state)
        _timing_restore(timing_state)
        raise
    _INSTALLED[genre.name] = genre
    return genre


def _install(genre: Genre) -> None:
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


def _uninstall(name: str) -> None:
    unregister_owner(name)
    _timing_drop_owner(name)
    _INSTALLED.pop(name, None)


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


def genre_entry_points(*, group: str = ENTRY_POINT_GROUP) -> tuple[EntryPoint, ...]:
    """The installed ``an.genres`` entry points (nothing is imported)."""
    return tuple(_entry_points(group=group))


def _resolve(ep: EntryPoint) -> Genre:
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
    return genre


def available(*, entry_points: Iterable[EntryPoint] | None = None) -> dict[str, Genre]:
    """Every installed genre's declaration, by name — read, never registered.

    A genre whose entry point does not import is left out (its error is what
    :func:`load` raises).
    """
    eps = genre_entry_points() if entry_points is None else tuple(entry_points)
    out: dict[str, Genre] = {}
    for ep in eps:
        try:
            genre = _resolve(ep)
        except GenreError:
            continue
        out[genre.name] = genre
    return out


def load(*, entry_points: Iterable[EntryPoint] | None = None) -> tuple[str, ...]:
    """Register every installed genre (the ``an.genres`` entry points). Idempotent.

    Returns the names of the genres registered after the call. Never called at
    import time: the CLI, ``an.load(project)`` and the MCP entry call it, so a
    document naming a genre's kind validates to that kind's model.
    ``entry_points`` replaces the installed ones (tests, a host that curates).
    """
    eps = genre_entry_points() if entry_points is None else tuple(entry_points)
    for ep in eps:
        register_genre(_resolve(ep))
    return installed()


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
# Isolation (tests, multi-tenant hosts)
# -----------------------------------------------------------------------------


@contextmanager
def without_genres() -> Iterator[None]:
    """Run a block with no genre registered (the core alone), then restore.

    >>> with without_genres():
    ...     action_kind("play") is None
    True
    """
    state = (snapshot(), _timing_snapshot(), dict(_INSTALLED))
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


def _all_owners() -> set[str]:
    from an.genres.registry import owners

    return set(owners())


__all__ = [
    "ENTRY_POINT_GROUP",
    "ActionKind",
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
    "genre_entry_points",
    "genres_declaring",
    "installed",
    "installed_genre",
    "load",
    "providers_of",
    "register_genre",
    "without_genres",
]
