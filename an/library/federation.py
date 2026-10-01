"""Libraries federated by a search path: one read view, writes to the owner (plan §1 decision 7).

Each package has its own library root (``an`` → ``~/.local/share/an``, a genre
such as ``cutan`` → ``~/.local/share/cutan``). A process reads them as one
ordered **search path** — its own library first, then the core ``an`` library,
then any others the user lists (ADR 0005 decision 1, Harmony's scope chain
reduced to one mechanism). An id resolves in the first library that has it;
a namespaced id (``cutan:character.alice@v003``) resolves only in the named one.
Writes always go to one owning :class:`Library`, never to the path.

The search path is the seam where a team share, a shipped seed library or a
remote bucket plugs in later: each is just another :class:`Library` whose mall
was built over different stores.

>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     path = search_path("cutan", roots={"cutan": f"{d}/cutan", "an": f"{d}/an"})
...     [lib.name for lib in path]
['cutan', 'an']
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from an.library.ids import (
    LATEST,
    SHA256_PREFIX,
    LibraryRef,
    check_namespace,
    parse_ref,
    version_number,
)
from an.library.root import (
    CORE_PACKAGE,
    LibraryLocationWarning,
    git_worktree_of,
    library_root,
)
from an.library.stores import build_library_mall, split_version_key, version_key

__all__ = [
    "AssetNotFoundError",
    "Libraries",
    "Library",
    "as_libraries",
    "open_library",
    "resolve",
    "search_path",
]


class AssetNotFoundError(LookupError):
    """No library on the search path holds the asset or version asked for."""


@dataclass(frozen=True)
class Library:
    """One library: its name (the namespace of its ids), its mall, and its root if on disk."""

    name: str
    mall: Mapping[str, MutableMapping] = field(repr=False)
    root: Path | None = None

    @property
    def records(self) -> MutableMapping:
        """``asset_id -> record`` (mutable curation)."""
        return self.mall["records"]

    @property
    def versions(self) -> MutableMapping:
        """``<asset_id>@<vNNN> -> version`` (write-once)."""
        return self.mall["versions"]

    @property
    def blobs(self) -> MutableMapping:
        """``sha256 -> bytes`` (content-addressed)."""
        return self.mall["blobs"]

    @property
    def blob_rights(self) -> MutableMapping:
        """``sha256 -> {asset: statement}``, derived (:mod:`an.library.floor`)."""
        return self.mall.setdefault("blob_rights", {})


#: What the read functions accept: one library, or a search path of them.
Libraries = Union[Library, Sequence[Library]]


def open_library(
    package: str = CORE_PACKAGE,
    root: str | os.PathLike | None = None,
    **overrides: MutableMapping,
) -> Library:
    """The library of ``package``, at ``root`` (resolved as in :mod:`an.library.root`).

    overrides: stores to inject (``records``, ``versions``, ``blobs``), as in
        :func:`an.library.stores.build_library_mall`

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> (lib.name, lib.root)
    ('an', None)
    """
    check_namespace(package)
    on_disk = not {"records", "versions", "blobs"} <= set(overrides)
    resolved = library_root(root, package=package) if on_disk else None
    repo = git_worktree_of(resolved) if resolved is not None else None
    if repo is not None:
        warnings.warn(
            f"the {package!r} library root {resolved} is inside the git work tree "
            f"{repo}; a library may hold private-study material and must never be "
            "committed (ADR 0005 decision 2). Move it, or set "
            f"{package.upper()}_HOME outside any repository.",
            LibraryLocationWarning,
            stacklevel=2,
        )
    return Library(
        package, build_library_mall(resolved, package=package, **overrides), resolved
    )


def search_path(
    package: str = CORE_PACKAGE,
    *,
    extra: Iterable[str | Library] = (),
    roots: Mapping[str, str | os.PathLike] | None = None,
) -> list[Library]:
    """The ordered libraries ``package`` reads: its own, then the core ``an``, then ``extra``.

    extra: further libraries, by package name (resolved like any root) or as
        :class:`Library` objects (a team share, a seed library)
    roots: an explicit root per package name (tests, a non-default layout);
        unnamed packages resolve as usual (``<PKG>_HOME``, then the data folder)

    A name appears once, at its first position.
    """
    roots = dict(roots or {})
    out: list[Library] = []
    for item in (package, CORE_PACKAGE, *extra):
        lib = item if isinstance(item, Library) else open_library(item, roots.get(item))
        if all(lib.name != seen.name for seen in out):
            out.append(lib)
    return out


def as_libraries(libraries: Libraries) -> list[Library]:
    """Normalise one library or a search path to a list."""
    if isinstance(libraries, Library):
        return [libraries]
    out = list(libraries)
    if not out or not all(isinstance(lib, Library) for lib in out):
        raise TypeError("expected a Library or a non-empty sequence of Library objects")
    return out


def is_federated(libraries: Libraries) -> bool:
    """Whether reads span more than one library (so ids are reported namespaced)."""
    return len(as_libraries(libraries)) > 1


def versions_of(library: Library, asset_id: str) -> list[str]:
    """The version labels of ``asset_id`` in ``library``, oldest first."""
    labels = []
    for key in library.versions:
        aid, label = split_version_key(key)
        if aid == asset_id:
            labels.append(label)
    return sorted(labels, key=version_number)


def _pick_version(library: Library, ref: LibraryRef) -> str:
    asset_id, selector = ref.asset_id, ref.version or LATEST
    if selector == LATEST:
        record = library.records.get(asset_id) if asset_id in library.records else None
        head = (record or {}).get("head")
        if not head:
            raise AssetNotFoundError(
                f"{library.name}:{asset_id} has no published version"
            )
        return head
    if selector.startswith(SHA256_PREFIX):
        prefix = selector[len(SHA256_PREFIX) :]
        hits = [
            label
            for label in versions_of(library, asset_id)
            if library.versions[version_key(asset_id, label)]
            .get("manifest_sha256", "")
            .startswith(prefix)
        ]
        if len(hits) != 1:
            raise AssetNotFoundError(
                f"{library.name}:{asset_id}@{selector} matches {len(hits)} versions "
                f"({hits}); give more of the hash"
            )
        return hits[0]
    if version_key(asset_id, selector) not in library.versions:
        raise AssetNotFoundError(
            f"{library.name}:{asset_id} has no version {selector}; "
            f"published: {versions_of(library, asset_id)}"
        )
    return selector


def resolve(
    libraries: Libraries, ref: str | LibraryRef
) -> tuple[Library, LibraryRef, dict[str, Any]]:
    """``(library, pinned_ref, version_doc)`` for a reference, along the search path.

    A namespaced reference reads only its library; a bare one reads the first
    library holding the asset. ``latest`` resolves to that library's head and
    ``sha256:<prefix>`` to the one version whose manifest hash starts with it.
    The returned reference is pinned (``vNNN``) and namespaced with the library
    it resolved in.
    """
    ref = parse_ref(ref) if isinstance(ref, str) else ref
    libs = as_libraries(libraries)
    if ref.namespace is not None:
        libs = [lib for lib in libs if lib.name == ref.namespace]
        if not libs:
            raise AssetNotFoundError(
                f"no library named {ref.namespace!r} on the search path "
                f"({[lib.name for lib in as_libraries(libraries)]})"
            )
    holders = [lib for lib in libs if ref.asset_id in lib.records]
    if not holders:
        raise AssetNotFoundError(
            f"{ref} is in none of the libraries {[lib.name for lib in libs]}"
        )
    library = holders[0]
    label = _pick_version(library, ref)
    pinned = LibraryRef(ref.asset_id, label, library.name)
    return library, pinned, library.versions[version_key(ref.asset_id, label)]
