"""The one vocabulary registry (ADR 0003 decision 6): entries and aspects, by owner.

Two kinds of source feed it:

- **registered entries** (:func:`register_entry`, :func:`register_aspect`):
  methods, motion and expression presets, camera moves, IR fields — each with
  an owner (the core, or a genre, through :class:`an.genres.Genre`'s
  ``vocabulary`` and ``aspects`` fields, so a genre's entries come out with it);
- **views** (:func:`register_view`): entries derived on every read from a
  registry that already exists — the action and entity kinds of
  :mod:`an.genres.registry`, the easings of :mod:`an.timing.easing` — so a kind
  or an easing is defined once, where it lives, and never copied here (design
  principle 3).

Like :mod:`an.genres.registry` this module imports nothing from ``an.ir``: a
view imports its source lazily, when it is read.

>>> from an.semantic.entries import Entry
>>> e = register_entry(Entry("demo.wiggle", "motion_preset", name="wiggle"), owner="demo")
>>> lookup("motion_preset", "wiggle") is e, entry("demo.wiggle") is e
(True, True)
>>> drop_owner("demo"); lookup("motion_preset", "wiggle") is None
True
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from an.genres.registry import CORE_OWNER
from an.semantic.entries import (
    ANY_ASPECT,
    NOOP,
    Aspect,
    Entry,
    Method,
    VocabularyError,
)

__all__ = [
    "UnknownEntryError",
    "duplicates",
    "aspect",
    "aspect_names",
    "aspects",
    "drop_owner",
    "entries",
    "entry",
    "lookup",
    "methods_of",
    "owner_of",
    "register_aspect",
    "register_entry",
    "register_view",
    "replacements",
    "restore",
    "snapshot",
]


class UnknownEntryError(VocabularyError, KeyError):
    """A name or id is not in the vocabulary; the message lists what is."""

    def __str__(self) -> str:  # KeyError would repr-quote the message
        return str(self.args[0]) if self.args else ""


#: ``() -> Iterable[(entry, owner)]``: a read-time view over another registry.
View = Callable[[], Iterable[tuple[Entry, str]]]


@dataclass
class _Tables:
    entries: dict[str, Entry]
    entry_owners: dict[str, str]
    aspects: dict[str, Aspect]
    aspect_owners: dict[str, str]
    views: dict[str, View]
    #: id -> (previous owner, new owner, previous version): every deliberate
    #: replacement (``replace=True``), so a shared definition is never silent.
    replaced: dict[str, tuple[str, str, str]]
    #: new id -> (the registered entry it retired, its owner): put back when the
    #: replacing owner leaves.
    shadowed: dict[str, tuple[Entry, str]]


_T = _Tables({}, {}, {}, {}, {}, {}, {})


def _held(entry_id: str) -> tuple[Entry, str] | None:
    """The entry (registered or viewed) under ``entry_id``, with its owner."""
    for e, o in _all():
        if e.id == entry_id:
            return e, o
    return None


def _spelled(kind: str, term: str, *, aspect: str | None) -> tuple[Entry, str] | None:
    for e, o in _all():
        if e.kind == kind and e.term == term and getattr(e, "aspect", None) == aspect:
            return e, o
    return None


def register_entry(
    e: Entry, *, owner: str = CORE_OWNER, replace: bool = False
) -> Entry:
    """Register a vocabulary entry under ``owner``: ONE entry per id, and per spelling.

    A name means one thing everywhere (``push_in`` is one entry, an#257): a
    second entry under a taken id — registered or provided by a view — or under
    a taken ``(kind, name)`` (within an aspect, for methods) raises, unless
    ``replace=True`` is passed explicitly, and then the replacement is recorded
    (:func:`replacements`). Re-registering the same entry is a no-op.

    >>> from an.semantic.entries import Entry
    >>> register_entry(Entry("demo.push_in", "camera_move", name="push_in"), owner="demo")
    Traceback (most recent call last):
    ...
    an.semantic.entries.VocabularyError: camera_move 'push_in' is already defined by 'camera.push_in' (owner 'an'); ...
    """
    if not isinstance(e, Entry):
        raise VocabularyError(f"not an Entry: {e!r}")
    held = _held(e.id)
    if held is not None and held[0] == e:
        _T.entries[e.id] = e
        _T.entry_owners.setdefault(e.id, owner)
        return e
    clash = held or _spelled(e.kind, e.term, aspect=getattr(e, "aspect", None))
    if clash is not None and clash[0].id != e.id and held is None and not replace:
        other, other_owner = clash
        raise VocabularyError(
            f"{e.kind} {e.term!r} is already defined by {other.id!r} (owner "
            f"{other_owner!r}); one name means one thing — register under that id "
            "with replace=True to redefine it, or choose another name"
        )
    if held is not None and not replace:
        raise VocabularyError(
            f"vocabulary entry {e.id!r} is already registered by {held[1]!r}; "
            "pass replace=True to replace it (the replacement is recorded)"
        )
    if clash is not None and replace:
        old, old_owner = clash
        if old.id in _T.entries:  # a registered one is retired, and kept to put back
            _T.shadowed[e.id] = (_T.entries.pop(old.id), _T.entry_owners.pop(old.id))
        _T.replaced[e.id] = (old_owner, owner, old.version)
    _T.entries[e.id] = e
    _T.entry_owners[e.id] = owner
    return e


def replacements() -> dict[str, tuple[str, str, str]]:
    """Every deliberate replacement: ``{id: (previous owner, new owner, previous version)}``."""
    return dict(_T.replaced)


def register_aspect(
    a: Aspect, *, owner: str = CORE_OWNER, replace: bool = False
) -> Aspect:
    """Register an aspect and its default chain. Checked as a whole by
    :func:`an.semantic.check_registry` (a chain may name methods registered
    after it, within the same genre)."""
    if not isinstance(a, Aspect):
        raise VocabularyError(f"not an Aspect: {a!r}")
    current = _T.aspects.get(a.name)
    if current is not None and current != a and not replace:
        raise VocabularyError(
            f"aspect {a.name!r} is already registered by {_T.aspect_owners[a.name]!r}; "
            "a second genre extends it with methods and a policy, not a second chain"
        )
    _T.aspects[a.name] = a
    _T.aspect_owners[a.name] = owner
    return a


def register_view(name: str, view: View) -> None:
    """Register a read-time view (core only: the kinds and easing registries)."""
    _T.views[name] = view


def _all() -> Iterator[tuple[Entry, str]]:
    """Every entry with its owner; a registered entry shadows a viewed one of
    the same id or spelling (only ever through an explicit, recorded replace)."""
    yield NOOP, CORE_OWNER
    taken: set = set()
    for eid, e in _T.entries.items():
        taken.add(eid)
        taken.add((e.kind, e.term, getattr(e, "aspect", None)))
        yield e, _T.entry_owners[eid]
    for view in _T.views.values():
        for e, o in view():
            if e.id in taken or (e.kind, e.term, getattr(e, "aspect", None)) in taken:
                continue
            yield e, o


def duplicates() -> list[str]:
    """Spellings defined twice (a view and a registered entry disagreeing on an id
    count once: the registered one shadows). Empty when one name is one thing."""
    seen: dict = {}
    out: list[str] = []
    for e, _ in _all():
        key = (e.kind, e.term, getattr(e, "aspect", None))
        if key in seen and seen[key] != e.id:
            out.append(f"{e.kind} {e.term!r} is defined by both {seen[key]!r} and {e.id!r}")
        seen.setdefault(key, e.id)
    return out


def entries(
    *, kind: str | None = None, owner: str | None = None
) -> tuple[Entry, ...]:
    """Every entry (registered and viewed), filtered by ``kind``/``owner``, in a stable order."""
    seen: dict[str, Entry] = {}
    for e, o in _all():
        if (kind is None or e.kind == kind) and (owner is None or o == owner):
            seen.setdefault(e.id, e)
    return tuple(seen.values())


def owner_of(entry_id: str) -> str | None:
    for e, o in _all():
        if e.id == entry_id:
            return o
    return None


def entry(entry_id: str) -> Entry:
    """The entry with this id; :class:`UnknownEntryError` naming the known ids otherwise."""
    for e, _ in _all():
        if e.id == entry_id:
            return e
    raise UnknownEntryError(
        f"no vocabulary entry {entry_id!r}; known: {sorted(e.id for e in entries())}"
    )


def lookup(kind: str, name: str, *, aspect: str | None = None) -> Entry | None:
    """The entry of ``kind`` a document spells ``name`` (for methods, within ``aspect``)."""
    for e, _ in _all():
        if e.kind != kind or e.term != name:
            continue
        if aspect is not None and getattr(e, "aspect", None) not in (aspect, ANY_ASPECT):
            continue
        return e
    return None


def aspect(name: str) -> Aspect:
    """The registered aspect ``name``; :class:`UnknownEntryError` otherwise."""
    try:
        return _T.aspects[name]
    except KeyError:
        raise UnknownEntryError(
            f"no aspect {name!r} is registered; known: {sorted(_T.aspects)} "
            "(a genre registers its aspects: call `an.genres.load()`)"
        ) from None


def aspects() -> tuple[Aspect, ...]:
    return tuple(_T.aspects.values())


def aspect_names(*, owner: str | None = None) -> tuple[str, ...]:
    return tuple(
        n for n in _T.aspects if owner is None or _T.aspect_owners[n] == owner
    )


def methods_of(aspect_name: str) -> tuple[Method, ...]:
    """Every registered method of an aspect: its chain first, in order, then the rest."""
    a = _T.aspects.get(aspect_name)
    pool = [
        e
        for e in entries(kind="method")
        if isinstance(e, Method) and e.aspect == aspect_name
    ]
    by_id = {m.id: m for m in pool}
    chain = [
        by_id.get(mid) or (NOOP if mid == NOOP.id else None)
        for mid in (a.chain if a else ())
    ]
    ordered = [m for m in chain if m is not None]
    ordered += [m for m in pool if m not in ordered]
    return tuple(ordered)


def drop_owner(owner: str) -> None:
    """Remove every entry and aspect ``owner`` registered."""
    if owner == CORE_OWNER:
        raise VocabularyError("the core's own vocabulary cannot be unregistered")
    for table, owners in (
        (_T.entries, _T.entry_owners),
        (_T.aspects, _T.aspect_owners),
    ):
        for name in [k for k, o in owners.items() if o == owner]:
            table.pop(name, None)
            owners.pop(name, None)
            if table is _T.entries:
                _T.replaced.pop(name, None)
                back = _T.shadowed.pop(name, None)
                if back is not None and back[1] != owner:
                    _T.entries[back[0].id] = back[0]
                    _T.entry_owners[back[0].id] = back[1]


def snapshot() -> tuple:
    """The state of the registered tables (views are code, not state)."""
    return tuple(
        dict(t)
        for t in (_T.entries, _T.entry_owners, _T.aspects, _T.aspect_owners, _T.replaced, _T.shadowed)
    )


def restore(state: tuple) -> None:
    for table, saved in zip(
        (_T.entries, _T.entry_owners, _T.aspects, _T.aspect_owners, _T.replaced, _T.shadowed), state
    ):
        table.clear()
        table.update(saved)
