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
  holds no library) is skipped.

A library written by an older ``an`` at a custom root, before the registry
existed, is registered by its next write or by :func:`an.library.api.reindex`.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path
from typing import Any

from an.library.federation import Libraries, Library, as_libraries, open_library
from an.library.ids import AssetIdError, check_namespace
from an.library.registry import register_root, registered_roots
from an.library.root import HOME_ENV_SUFFIX, LIBRARY_DIRNAME, _platform_data_dir
from an.library.rights import LICENSE_CLASS_ORDER

__all__ = ["BlobFloor", "machine_libraries", "record_statement", "register_library"]

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
    written: the write is refused rather than made invisible to the floor.
    """
    if library.root is not None:
        register_root(library.name, library.root)


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
        self.libraries = (
            machine_libraries(libraries)
            if discover
            else (as_libraries(libraries) if libraries else [])
        )
        self._memo: dict[str, dict[str, dict[str, Any]]] = {}

    def statements(self, digest: str) -> dict[str, dict[str, Any]]:
        """``{asset_key: statement}`` about ``digest`` from every library."""
        if digest not in self._memo:
            merged: dict[str, dict[str, Any]] = {}
            for library in self.libraries:
                store = library.blob_rights
                try:
                    entries = store[digest] if digest in store else {}
                except Exception:  # noqa: BLE001 — a damaged index entry is rebuilt by reindex
                    entries = {}
                for key, statement in entries.items():
                    held = merged.get(key)
                    if held is None or _outranks(statement, held):
                        merged[key] = dict(statement)
            self._memo[digest] = merged
        return self._memo[digest]

    def strictest(self, digests: Iterable[str]) -> str:
        """The strictest class any statement makes about any of ``digests`` (``free`` if none)."""
        cls = "free"
        for d in digests:
            for statement in self.statements(d).values():
                cls = _stricter_class(cls, statement.get("class", "unknown"))
        return cls
