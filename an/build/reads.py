"""What a shot read: a read-recording view of the mall, and the digests of what it saw.

ADR 0004 decision 3: *a shot's inputs are recorded, not assumed.* The mall a
keyer compiles against is wrapped in a :class:`RecordingMall`, which notes
every asset entry the compile asks for — ``props["logo"]``, a ``get``, an
``in`` test — and every store it LISTS (iterating a store, or taking its
length, depends on all of it). Those reads become the shot's dependency edges:
:func:`read_digests` digests exactly them, and an edit to an asset no shot
read moves no key. Before an#316 every shot depended on every asset in its
project (:func:`an.build.keys.project_assets_digest`, the first slice's
fallback), so a one-prop edit re-rendered the whole film.

Only the asset stores (:data:`~an.build.keys.PROJECT_ASSET_STORES`) are
recorded. Everything else a render reads already has a part of its own: the
scene reaches the key through each shot's compiled document, the dialogue
audio through ``audio``, art staged by path through ``textures``.

An entry's digest covers what the mapping returns AND, for a filesystem store,
the files of the entry beside it (a prop's ``prop.json``, its ``parts/`` SVGs,
a relative font) — so a sidecar edited behind the mapping still moves it.

>>> mall = RecordingMall({"props": {"logo": {"text": "A"}, "intro": {}}})
>>> mall["props"]["logo"]["text"]
'A'
>>> sorted(mall.reads)
[('props', 'logo')]
>>> sorted(read_digests({"props": {"logo": {"text": "A"}}}, mall.reads))
['props/logo']
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from pathlib import Path
from typing import Any

from an.build.keys import (
    ABSENT,
    PROJECT_ASSET_STORES,
    canonical_digest,
    file_digest,
    store_digest,
)

#: The key a read of a WHOLE store is recorded under (iteration, ``len``):
#: the shot depends on every entry, present and future.
WHOLE_STORE: str = "*"

#: ``(store name, entry key or WHOLE_STORE)``.
Read = tuple[str, str]


class RecordingStore(MutableMapping):
    """One store of a :class:`RecordingMall`: reads are noted, writes pass through.

    Attribute access (``_root``, a store's own helpers) reaches the wrapped
    store unchanged — the compiler reads art by path through ``_root``, and
    those bytes are keyed by the ``textures`` part, not here. ``bool()`` is
    NOT a read: ``mall.get(name) or {}`` asks whether the store has anything,
    and recording it would make every shot depend on the whole store. So a
    read of an EMPTY store (which that idiom replaces with ``{}``) goes
    unrecorded — safe, because what the shot draws from an entry that appears
    later reaches its compiled document.
    """

    def __init__(self, store: Any, name: str, reads: set[Read]) -> None:
        self._an_store = store
        self._an_name = name
        self._an_reads = reads

    def _note(self, key: Any) -> None:
        self._an_reads.add((self._an_name, str(key)))

    def __getitem__(self, key: Any) -> Any:
        self._note(key)
        return self._an_store[key]

    def __contains__(self, key: Any) -> bool:
        self._note(key)
        return key in self._an_store

    def __iter__(self) -> Iterator:
        self._note(WHOLE_STORE)
        return iter(self._an_store)

    def __len__(self) -> int:
        self._note(WHOLE_STORE)
        return len(self._an_store)

    def __bool__(self) -> bool:
        return bool(self._an_store)

    def __setitem__(self, key: Any, value: Any) -> None:
        self._an_store[key] = value

    def __delitem__(self, key: Any) -> None:
        del self._an_store[key]

    def __getattr__(self, attr: str) -> Any:
        # Only called for attributes NOT found on this wrapper.
        if attr.startswith("_an_"):  # half-built (copy, pickle): no recursion
            raise AttributeError(attr)
        return getattr(self._an_store, attr)

    def __repr__(self) -> str:
        return f"RecordingStore({self._an_name!r}, {self._an_store!r})"


class RecordingMall(Mapping):
    """A view of ``mall`` that records which asset entries are read through it.

    Stores named in ``recorded`` come back wrapped in a :class:`RecordingStore`
    (one per store, so identity is stable across lookups); every other store
    comes back as it is. :attr:`reads` is the set of ``(store, key)`` read so
    far, ``key`` being :data:`WHOLE_STORE` for a store that was listed.
    """

    def __init__(
        self,
        mall: Mapping[str, Any] | None,
        *,
        recorded: Iterable[str] = PROJECT_ASSET_STORES,
    ) -> None:
        self._mall = mall if mall is not None else {}
        self._recorded = frozenset(recorded)
        self.reads: set[Read] = set()
        self._views: dict[str, RecordingStore] = {}

    def _view(self, name: str, store: Any) -> Any:
        if name not in self._recorded or store is None:
            return store
        view = self._views.get(name)
        if view is None or view._an_store is not store:
            view = self._views[name] = RecordingStore(store, name, self.reads)
        return view

    def __getitem__(self, name: str) -> Any:
        return self._view(name, self._mall[name])

    def __iter__(self) -> Iterator[str]:
        return iter(self._mall)

    def __len__(self) -> int:
        return len(self._mall)

    def __getattr__(self, attr: str) -> Any:
        if attr in {"_mall", "_recorded", "_views", "reads"}:
            raise AttributeError(attr)
        return getattr(self._mall, attr)


def entry_files(store: Any, key: str) -> list[Path]:
    """The files of entry ``key`` in a filesystem store (one exposing ``_root``).

    Both store layouts are covered: a sidecar store's folder ``<root>/<key>/``
    (everything under it) and a file store's ``<root>/<key>.<ext>`` (one
    suffix: ``logo.json`` is entry ``logo``'s; ``logo.v2/`` and
    ``logo.v2.json`` are entry ``logo.v2``'s). Operating-system clutter is
    never an asset (:func:`an.stores._common.is_os_junk`).
    """
    from an.stores._common import is_os_junk

    root = getattr(store, "_root", None)
    if root is None or not Path(root).is_dir():
        return []
    root = Path(root)
    found: list[Path] = []
    for path in sorted(root.glob(f"{_glob_escape(key)}*")):
        if path.name != key and not (path.is_file() and path.stem == key):
            continue
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for f in candidates:
            if f.is_file() and not is_os_junk(f.relative_to(root).as_posix()):
                found.append(f)
    return found


def _glob_escape(text: str) -> str:
    return "".join(f"[{c}]" if c in "*?[]" else c for c in text)


def entry_digest(store: Any, key: str) -> str:
    """One entry's digest: what the mapping returns, plus its files on disk.

    >>> entry_digest({"a": 1}, "a") == entry_digest({"a": 1}, "a")
    True
    >>> entry_digest({"a": 1}, "a") == entry_digest({"a": 2}, "a")
    False
    >>> entry_digest({}, "a") == entry_digest({}, "a")  # absent is a value too
    True
    """
    if key == WHOLE_STORE:
        return store_digest(store)
    try:
        value: Any = canonical_digest(store[key])
    except KeyError:
        value = ABSENT
    except Exception as e:  # noqa: BLE001 — an unreadable entry is a fact, not a crash
        value = {"unreadable": f"{type(e).__name__}: {e}"}
    root = getattr(store, "_root", None)
    files = [
        [f.relative_to(Path(root)).as_posix(), file_digest(f)]
        for f in entry_files(store, key)
    ]
    return canonical_digest([value, files])


def read_digests(mall: Mapping[str, Any], reads: Iterable[Read]) -> dict[str, str]:
    """``{"store/key": digest}`` for every recorded read — the shot's dependency edges.

    A read of a store the mall does not have is recorded as :data:`ABSENT`, so
    the day the store appears the key moves.

    >>> read_digests({}, [("props", "logo")])
    {'props/logo': 'absent'}
    """
    out: dict[str, str] = {}
    for store_name, key in sorted(set(reads)):
        store = mall.get(store_name) if mall is not None else None
        out[f"{store_name}/{key}"] = (
            ABSENT if store is None else entry_digest(store, key)
        )
    return out


__all__ = [
    "WHOLE_STORE",
    "RecordingMall",
    "RecordingStore",
    "entry_digest",
    "entry_files",
    "read_digests",
]
