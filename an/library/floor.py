"""The rights floor of a blob: the strictest statement any library on this machine makes about its bytes.

ADR 0005 decision 10's "most restrictive", read as the maintainer decided it
(an#236): rights attach to the bytes. A file is as restricted as the strictest
statement ANY library known on this machine makes about its SHA-256 — whichever
library one reads through — and only an explicit, recorded relicence relaxes it.

**What a statement is.** Each version that holds a blob says one thing about it:

- the version's own per-part ``source`` for that exact file, if the source pins
  the same digest (``AssetSource.sha256``) — a per-part claim about OTHER bytes
  (a stale factory stamp on a re-carved part) itemises nothing;
- otherwise the asset's own label: its asset-level and descriptor sources and
  its lineage — what the asset says about every file it does not itemise;
- for a relicensed version, its relicence.

**Where the statements live.** Each library keeps a derived store,
``blob_rights``: ``sha256 -> {"<library>:<asset_id>": statement}``, one entry
per asset (its latest version holding the blob), maintained by ``publish`` and
rebuilt by :func:`an.library.api.reindex`. Reading a floor is one key lookup per
library, so the cross-library check costs nothing like a scan.

**Which libraries.** Those on the search path, plus every other library on
this machine the floor can find:

- each package root under the current platform data folder
  (``~/.local/share/an``, ``~/.local/share/cutan``, …);
- each currently set ``<PKG>_HOME`` root;
- every root in the machine's **registry of library roots**
  (:mod:`an.library.registry`, an#249) — written on the first write to any
  library, at a path that depends on nothing in the environment. A library at a
  custom ``--root``, or under a ``<PKG>_HOME`` / ``XDG_DATA_HOME`` that has since
  changed, is therefore still read. A registered root that no longer exists (or
  holds no library) is skipped;
- the machine's **memory of statements** (same place): every statement any
  on-disk library made at publish, so a library moved, renamed or deleted
  since relaxes nothing — the floor keeps its last-known statements.

A library written by an older ``an`` at a custom root, before the registry
existed, is registered by its next write or by :func:`an.library.api.reindex`.
"""

from __future__ import annotations

import os
import sys
import warnings
from collections.abc import Collection, Iterable, Mapping, MutableMapping
from pathlib import Path
from typing import Any

from an.library.federation import Libraries, Library, as_libraries, open_library
from an.library.ids import AssetIdError, check_namespace
from an.library.registry import (
    RegistryWarning,
    machine_registry_path,
    register_root,
    registered_roots,
    remember_statements,
    remembered_statements_by_root,
)
from an.library.root import HOME_ENV_SUFFIX, LIBRARY_DIRNAME, _platform_data_dir
from an.library.rights import LICENSE_CLASS_ORDER

__all__ = [
    "BlobFloor",
    "library_origin",
    "machine_libraries",
    "record_statement",
    "register_library",
    "remember",
]

#: The sub-folders that mark a directory as a library's (any one suffices).
_LIBRARY_MARKERS: tuple[str, ...] = ("versions", "records", "blob_rights")


def _is_library_root(root: Path) -> bool:
    lib = root / LIBRARY_DIRNAME
    return any((lib / m).is_dir() for m in _LIBRARY_MARKERS)


def _discovered_roots(
    environ: Mapping[str, str], platform: str
) -> list[tuple[str, Path]]:
    """``(package, root)`` for every library root discoverable now, then every registered one."""
    found: list[tuple[str, Path]] = []
    data = _platform_data_dir(environ, platform)
    if data.is_dir():
        for child in sorted(data.iterdir()):
            if child.is_dir() and _is_library_root(child):
                found.append((child.name, child))
    for var, value in sorted(environ.items()):
        if var.endswith(HOME_ENV_SUFFIX) and value:
            root = Path(value).expanduser()
            if _is_library_root(root):
                found.append((var[: -len(HOME_ENV_SUFFIX)].lower(), root))
    for package, root in registered_roots():
        if _is_library_root(root):
            found.append((package, root))
    return found


def register_library(library: Library) -> None:
    """Record an on-disk library's root in the machine registry, before its first write.

    An in-memory library (no root) has nothing to register. Raises
    :class:`an.library.registry.RegistryError` when the registry cannot be
    read or written: the write is refused rather than made invisible to the floor.

    A registry that does not exist yet means either this machine's first
    library write, or a registry that was deleted — and nothing on disk tells
    the two apart: a deleted registry takes its memory of statements with it.
    So whenever the registry is created from nothing (an#263, R2b-N2), every
    library discoverable now is registered with this one, and a
    :class:`an.library.registry.RegistryWarning` says that a library kept at a
    custom root binds the rights checks again only once it is written to or
    reindexed. Never delete the registry folder wholesale; prune it.
    """
    if library.root is None:
        return
    if not machine_registry_path().exists():
        discovered = [
            (package, root)
            for package, root in _discovered_roots(os.environ, sys.platform)
            if root.resolve() != library.root.resolve()
        ]
        for package, root in discovered:
            register_root(package, root)
        found = (
            f"registered the {len(discovered)} other library root(s) discoverable now"
            if discovered
            else "no other library is discoverable now"
        )
        warnings.warn(
            f"the registry of library roots ({machine_registry_path()}) did not "
            f"exist, so it was created from nothing ({found}). On a machine's first "
            "library write that is expected. If it was deleted, every statement it "
            "remembered is gone: a library kept at a custom root binds the rights "
            "checks again only once it is written to or reindexed "
            "(an.library.api.reindex). Prune the registry; never delete it.",
            RegistryWarning,
            stacklevel=3,
        )
    register_root(library.name, library.root)


def library_origin(library: Library) -> str:
    """Which library a statement came from: its resolved root, or this in-memory library.

    Two libraries can share a name (the default ``cutan`` and one at a custom
    root), and so an asset key, a version label and even a manifest: only the
    root tells their statements apart.
    """
    if library.root is not None:
        return str(Path(library.root).expanduser().resolve())
    return f"<in-memory library {id(library)}>"


def remember(library: Library, statements) -> None:
    """Remember an on-disk library's statements in the machine memory (none for an in-memory one)."""
    if library.root is not None:
        remember_statements(library.root, statements)


def machine_libraries(
    libraries: Libraries | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> list[Library]:
    """``libraries`` (first, as given) plus every other library root on this machine.

    Roots already on the path are not opened twice; a folder whose name is not a
    valid library name is skipped.
    """
    out = list(as_libraries(libraries)) if libraries else []
    seen = {lib.root.resolve() for lib in out if lib.root is not None}
    env = os.environ if environ is None else environ
    for package, root in _discovered_roots(env, platform or sys.platform):
        if root.resolve() in seen:
            continue
        try:
            check_namespace(package)
        except AssetIdError:
            continue
        seen.add(root.resolve())
        out.append(open_library(package, root))
    return out


def _stricter_class(a: str, b: str) -> str:
    order = LICENSE_CLASS_ORDER.index
    return a if order(a) < order(b) else b


def _outranks(statement: Mapping[str, Any], held: Mapping[str, Any]) -> bool:
    """Whether ``statement`` replaces ``held`` for the same ``<library>:<asset>`` key.

    Two libraries can share a name (the default ``cutan`` and a ``cutan`` at a
    registered custom root), so one key can come from both: the stricter
    statement wins, and only on a tie the later version.
    """
    order = LICENSE_CLASS_ORDER.index
    new = order(statement.get("class", "unknown"))
    old = order(held.get("class", "unknown"))
    if new != old:
        return new < old
    return statement.get("number", 0) >= held.get("number", 0)


def record_statement(
    store: MutableMapping, digest: str, asset_key: str, statement: Mapping[str, Any]
) -> None:
    """Record what ``asset_key`` says about ``digest``: its latest holding version wins.

    A later version of an asset may only be as strict or stricter than an
    earlier one (it inherits it), unless it is relicensed — so the latest
    version's statement is the asset's statement.
    """
    entries = dict(store[digest]) if digest in store else {}
    previous = entries.get(asset_key)
    if previous is None or statement["number"] >= previous.get("number", 0):
        entries[asset_key] = dict(statement)
        store[digest] = entries


class BlobFloor:
    """The strictest statements about a blob, over every library on the machine, memoised.

    Build one per operation (a publish, a search, a check-out): it opens the
    machine's libraries once and reads each digest once.
    """

    def __init__(
        self, libraries: Libraries | None = None, *, discover: bool = True
    ) -> None:
        """libraries: the search path; discover: also read every other library
        on the machine and the machine's memory of statements (default)."""
        self.libraries = (
            machine_libraries(libraries)
            if discover
            else (as_libraries(libraries) if libraries else [])
        )
        self.remembered = discover
        self._memo: dict[str, list[tuple[str | None, str, dict[str, Any]]]] = {}

    def _all(self, digest: str) -> list[tuple[str | None, str, dict[str, Any]]]:
        """Every ``(origin, asset_key, statement)`` about ``digest``, unmerged, read once."""
        if digest not in self._memo:
            found: list[tuple[str | None, str, dict[str, Any]]] = []
            for library in self.libraries:
                store = library.blob_rights
                try:
                    entries = store[digest] if digest in store else {}
                except Exception:  # noqa: BLE001 — a damaged index entry is rebuilt by reindex
                    entries = {}
                origin = library_origin(library)
                found += [(origin, key, dict(s)) for key, s in entries.items()]
            # What any library on this machine ever said, even one since moved,
            # renamed or deleted: a missing root relaxes nothing.
            found += remembered_statements_by_root(digest) if self.remembered else []
            self._memo[digest] = found
        return self._memo[digest]

    def statements(
        self, digest: str, *, exclude: Collection[tuple[str, str]] = ()
    ) -> dict[str, dict[str, Any]]:
        """``{asset_key: statement}`` about ``digest`` from every library.

        exclude: ``(origin, manifest)`` of versions whose statements to leave
            out — the versions a rights walk reads in full itself
            (:func:`an.library.api.version_sources`), each in the library it
            was read from (:func:`library_origin`). A same-named library's
            version with the same manifest is another version (its lineage
            resolves in ITS library), so it is never left out; and the
            exclusion runs before statements under one asset key are merged,
            so it can hide nothing else.
        """
        merged: dict[str, dict[str, Any]] = {}
        for origin, key, statement in self._all(digest):
            if exclude and (origin, statement.get("manifest")) in exclude:
                continue
            held = merged.get(key)
            if held is None or _outranks(statement, held):
                merged[key] = dict(statement)
        return merged

    def strictest(self, digests: Iterable[str]) -> str:
        """The strictest class any statement makes about any of ``digests`` (``free`` if none)."""
        cls = "free"
        for d in digests:
            for statement in self.statements(d).values():
                cls = _stricter_class(cls, statement.get("class", "unknown"))
        return cls
