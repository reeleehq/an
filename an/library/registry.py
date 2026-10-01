"""The machine's memory of its libraries: every root ever written, and every statement ever made (an#249).

The rights floor (:mod:`an.library.floor`) must read every statement any
library on this machine makes about a blob, not only those it can discover
from today's environment. Discovery finds the package roots under the CURRENT
data folder (which follows ``XDG_DATA_HOME``) and the CURRENTLY set
``<PKG>_HOME`` roots. A library written at an explicit ``root=`` / ``--root``,
or under an environment that has since changed, is invisible to discovery, and
its private bytes would then publish as ``free`` anywhere else.

So this module keeps two records, side by side, at a location that depends on
**nothing in the environment**: the account's home folder as the operating
system records it (the password database on POSIX, never ``$HOME``), under the
core package's default data folder — ``~/.local/share/an/registry/`` on Linux
and macOS, whatever ``XDG_DATA_HOME``, ``AN_HOME`` or ``<PKG>_HOME`` say. (On
Windows the account's home is ``Path.home()``, which follows ``USERPROFILE``:
there the location is as stable as that variable.)

- **The registry of roots** (``library_roots.jsonl``): the first write to any
  on-disk library records its root, and the floor reads each registered root's
  own index. JSON Lines, **append-only**: an append of one short line is
  atomic, so racing publishers cannot lose each other's registration, and a
  line torn by a crash is skipped (the next append starts on a fresh line).
  A root that no longer exists is skipped — which is why the second record
  exists.
- **The memory of statements** (``statements/<aa>/<sha256>/…json``): every
  statement a version makes about a blob, written at publish beside the
  library's own index. The floor reads it in addition to the libraries, so a
  library that is moved, renamed, unmounted or deleted can never relax a
  statement it once made: **a missing root relaxes nothing**. One small file
  per (blob, library root, asset), replaced only by a later version of the same
  asset at the same root — so a relicence there still speaks, as in the
  library's own index. A file that cannot be parsed counts as ``unknown``.

Deleting the registry folder wholesale deletes that memory with it — nothing
left on disk tells a deleted registry from a first use — so whenever the
registry is created from nothing, the first write warns
(:class:`RegistryWarning`). Prune it; never delete it.

Both are read **fail-closed**: a registry or memory that exists but cannot be
read raises :class:`RegistryError` — a floor that silently read less would let
private bytes out. Libraries with injected stores (no root on disk: an S3 or
in-memory mall) are in neither record; their statements reach the floor only
while they are on the search path.

Neither record is a search path: a registered library's assets are never
found, resolved or checked out through them — reads still go through the
explicit search path (:func:`an.library.federation.search_path`).

Tests and doctests are redirected by the repository's root ``conftest.py``,
which points :func:`_account_home` into a temporary folder. A test that runs
``an`` in a SUBPROCESS cannot be redirected that way and must not publish.

>>> import tempfile, pathlib
>>> with tempfile.TemporaryDirectory() as d:
...     reg = pathlib.Path(d) / "roots.jsonl"
...     first = register_root("cutan", pathlib.Path(d) / "study", registry=reg)
...     again = register_root("cutan", pathlib.Path(d) / "study", registry=reg)
...     (first, again), [(p, r.name) for p, r in registered_roots(registry=reg)]
((True, False), [('cutan', 'study')])
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from an.library.root import CORE_PACKAGE, POSIX_DATA_DEFAULT, WINDOWS_DATA_DEFAULT

__all__ = [
    "REGISTRY_DIRNAME",
    "REGISTRY_FILENAME",
    "STATEMENTS_DIRNAME",
    "RegistryError",
    "machine_registry_dir",
    "machine_registry_path",
    "register_root",
    "registered_roots",
    "remember_statements",
    "remembered_statements",
    "remembered_statements_by_root",
]

#: The sub-folder of the core package's default data root holding the registry
#: (a root holds one sub-folder per kind of data, never files at the top).
REGISTRY_DIRNAME: str = "registry"
#: The registry file: JSON Lines, one ``{"package", "root", "registered"}`` per line.
REGISTRY_FILENAME: str = "library_roots.jsonl"
#: The folder of remembered statements, beside the registry file.
STATEMENTS_DIRNAME: str = "statements"
#: Leading hex digits of a blob's hash used as its fan-out folder.
_FANOUT: int = 2
#: Hex digits of the (root, asset) hash naming one remembered statement.
_STATEMENT_ID_LEN: int = 24


class RegistryError(OSError):
    """The machine's registry or statement memory cannot be read or written; nothing proceeds."""


class RegistryWarning(UserWarning):
    """The registry was absent and is being created from nothing (first use, or deleted)."""


def _account_home() -> Path:
    """The account's home folder as the OS records it — not ``$HOME``, which a shell can change."""
    if sys.platform.startswith("win"):
        return Path.home()
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (
        ImportError,
        KeyError,
        AttributeError,
    ):  # pragma: no cover — no passwd entry
        return Path.home()


def machine_registry_dir() -> Path:
    """The folder holding the registry and the statement memory (independent of the environment).

    >>> machine_registry_dir().name
    'registry'
    """
    defaults = (
        WINDOWS_DATA_DEFAULT if sys.platform.startswith("win") else POSIX_DATA_DEFAULT
    )
    return _account_home().joinpath(*defaults) / CORE_PACKAGE / REGISTRY_DIRNAME


def machine_registry_path() -> Path:
    """Where this machine's registry of library roots lives.

    >>> machine_registry_path().name
    'library_roots.jsonl'
    """
    return machine_registry_dir() / REGISTRY_FILENAME


def _resolve(registry: str | os.PathLike | None) -> Path:
    return Path(registry) if registry is not None else machine_registry_path()


def _unreadable(what: Path, e: BaseException) -> RegistryError:
    return RegistryError(
        f"{what} cannot be read ({e}); the rights floor cannot know every library "
        "on this machine, so nothing proceeds. Make it readable and retry."
    )


def registered_roots(
    *, registry: str | os.PathLike | None = None
) -> Iterator[tuple[str, Path]]:
    """``(package, root)`` for every root ever registered, oldest first, each once.

    A line that does not parse (a torn append) is skipped; existence is the
    caller's to check. A registry that exists but cannot be read raises
    :class:`RegistryError`.
    """
    path = _resolve(registry)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return
    except OSError as e:
        raise _unreadable(path, e) from e
    seen: set[str] = set()
    for line in raw.decode("utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
            package, root = str(entry["package"]), str(entry["root"])
        except (ValueError, KeyError, TypeError):
            continue
        if root in seen:
            continue
        seen.add(root)
        yield package, Path(root)


def register_root(
    package: str,
    root: str | os.PathLike,
    *,
    registry: str | os.PathLike | None = None,
) -> bool:
    """Record ``root`` (``package``'s library root) in the registry; ``True`` if it was new.

    Idempotent. Raises :class:`RegistryError` when the registry cannot be read
    or written: a library the floor cannot find later must not be written to.
    """
    resolved = str(Path(root).expanduser().resolve())
    path = _resolve(registry)
    try:
        known = any(str(r) == resolved for _, r in registered_roots(registry=path))
    except RegistryError as e:
        raise RegistryError(f"{e} (nothing was written)") from e
    if known:
        return False
    line = json.dumps(
        {
            "package": package,
            "root": resolved,
            "registered": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        sort_keys=True,
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # A line torn by a crash must not swallow this one: start fresh.
        lead = ""
        if path.exists() and path.stat().st_size:
            with path.open("rb") as f:
                f.seek(-1, os.SEEK_END)
                lead = "" if f.read(1) == b"\n" else "\n"
        # O_APPEND: one short write is atomic, so concurrent registrations
        # interleave whole lines and none is lost.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (lead + line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError as e:
        raise RegistryError(
            f"cannot record the library root {resolved} in the registry {path} "
            f"({e}); the rights checks of every other library would not see it, so "
            "nothing was written. Make that folder writable and retry."
        ) from e
    return True


# --------------------------------------------------------------------------- statements


def _statements_dir(digest: str) -> Path:
    return machine_registry_dir() / STATEMENTS_DIRNAME / digest[:_FANOUT] / digest


def _statement_id(root: str, asset_key: str) -> str:
    return hashlib.sha256(f"{root}\0{asset_key}".encode("utf-8")).hexdigest()[
        :_STATEMENT_ID_LEN
    ]


def remember_statements(
    root: str | os.PathLike,
    statements: Iterable[tuple[str, str, Mapping[str, Any]]],
) -> None:
    """Remember ``(digest, asset_key, statement)`` made by the library at ``root``.

    One file per (digest, root, asset), replaced only by a statement of a later
    (or the same) version of that asset — the same rule as a library's own
    index. Raises :class:`RegistryError` when it cannot be written.
    """
    root_s = str(Path(root).expanduser().resolve())
    for digest, asset_key, statement in statements:
        folder = _statements_dir(digest)
        target = folder / f"{_statement_id(root_s, asset_key)}.json"
        try:
            if target.exists():
                held = json.loads(target.read_text(encoding="utf-8"))
                if held.get("number", 0) > statement.get("number", 0):
                    continue
            folder.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    {**dict(statement), "asset": asset_key, "root": root_s},
                    f,
                    sort_keys=True,
                )
            os.replace(tmp, target)
        except (OSError, ValueError) as e:
            raise RegistryError(
                f"cannot remember what {asset_key} says about {digest[:12]}… in "
                f"{folder} ({e}); nothing more was written. Make it writable and retry."
            ) from e


def remembered_statements(digest: str) -> list[tuple[str, dict[str, Any]]]:
    """``(asset_key, statement)`` for every statement this machine ever recorded about ``digest``.

    A remembered file that cannot be parsed counts as an ``unknown``
    statement (it said something; what is no longer known). A memory that
    exists but cannot be listed raises :class:`RegistryError`.
    """
    return [(key, held) for _, key, held in remembered_statements_by_root(digest)]


def remembered_statements_by_root(
    digest: str,
) -> list[tuple[str | None, str, dict[str, Any]]]:
    """``(root, asset_key, statement)``: :func:`remembered_statements` with the
    resolved root of the library that made each (``None`` when unreadable)."""
    folder = _statements_dir(digest)
    try:
        names = sorted(p for p in folder.iterdir() if p.suffix == ".json")
    except FileNotFoundError:
        return []
    except OSError as e:
        raise _unreadable(folder, e) from e
    out: list[tuple[str | None, str, dict[str, Any]]] = []
    for path in names:
        try:
            held = json.loads(path.read_text(encoding="utf-8"))
            asset_key = str(held.pop("asset"))
            root = held.pop("root", None)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            root, asset_key, held = (
                None,
                f"unreadable statement {path.stem}",
                {
                    "class": "unknown",
                    "label": "a remembered statement that can no longer be read",
                    "number": 0,
                },
            )
        out.append((str(root) if root else None, asset_key, held))
    return out
