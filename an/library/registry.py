"""The machine's registry of library roots: every library ever written on this machine (an#249).

The rights floor (:mod:`an.library.floor`) must read every library that might
make a statement about a blob — not only the ones it can discover from today's
environment. Discovery finds the package roots under the CURRENT data folder
(which follows ``XDG_DATA_HOME``) and the CURRENTLY set ``<PKG>_HOME`` roots. A
library written at an explicit ``root=`` / ``--root``, or under an environment
that has since changed, is invisible to it — and its private bytes would then
publish as ``free`` anywhere else.

So the first write to any on-disk library records its root here, and the floor
reads this registry beside its discovery. The registry's own location depends
on **nothing in the environment**: it is derived from the account's home folder
as the operating system records it (the password database on POSIX, not
``$HOME``), under the core package's default data folder —
``~/.local/share/an/registry/library_roots.jsonl`` on Linux and macOS,
``%USERPROFILE%\\AppData\\Local\\an\\registry\\…`` on Windows — whatever
``XDG_DATA_HOME``, ``AN_HOME`` or ``<PKG>_HOME`` say at the time.

The file is JSON Lines, one root per line, **append-only**: an append of one
short line is atomic, so racing publishers cannot lose each other's
registration, and a torn last line is skipped on read. A root that no longer
exists (deleted, an unmounted drive) is skipped; the registry is never pruned
automatically, so a root that comes back is read again.

The registry feeds the rights floor ONLY. It is not a search path: a registered
library's assets are never found, resolved or checked out through it — reads
still go through the explicit search path (:func:`an.library.federation.search_path`).

>>> import tempfile, pathlib
>>> with tempfile.TemporaryDirectory() as d:
...     reg = pathlib.Path(d) / "roots.jsonl"
...     first = register_root("cutan", pathlib.Path(d) / "study", registry=reg)
...     again = register_root("cutan", pathlib.Path(d) / "study", registry=reg)
...     (first, again), [(p, r.name) for p, r in registered_roots(registry=reg)]
((True, False), [('cutan', 'study')])
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from an.library.root import CORE_PACKAGE, POSIX_DATA_DEFAULT, WINDOWS_DATA_DEFAULT

__all__ = [
    "REGISTRY_DIRNAME",
    "REGISTRY_FILENAME",
    "RegistryError",
    "machine_registry_path",
    "register_root",
    "registered_roots",
]

#: The sub-folder of the core package's default data root holding the registry
#: (a root holds one sub-folder per kind of data, never files at the top).
REGISTRY_DIRNAME: str = "registry"
#: The registry file: JSON Lines, one ``{"package", "root", "registered"}`` per line.
REGISTRY_FILENAME: str = "library_roots.jsonl"


class RegistryError(OSError):
    """The registry of library roots cannot be written, so a library write is refused."""


def _account_home() -> Path:
    """The account's home folder as the OS records it — not ``$HOME``, which a shell can change."""
    if sys.platform.startswith("win"):
        return Path.home()
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, AttributeError):  # pragma: no cover — no passwd entry
        return Path.home()


def machine_registry_path() -> Path:
    """Where this machine's registry of library roots lives (independent of the environment).

    >>> machine_registry_path().name
    'library_roots.jsonl'
    """
    defaults = (
        WINDOWS_DATA_DEFAULT if sys.platform.startswith("win") else POSIX_DATA_DEFAULT
    )
    return (
        _account_home().joinpath(*defaults)
        / CORE_PACKAGE
        / REGISTRY_DIRNAME
        / REGISTRY_FILENAME
    )


def _resolve(registry: str | os.PathLike | None) -> Path:
    return Path(registry) if registry is not None else machine_registry_path()


def registered_roots(
    *, registry: str | os.PathLike | None = None
) -> Iterator[tuple[str, Path]]:
    """``(package, root)`` for every root ever registered, oldest first, each once.

    A line that does not parse (a torn append) is skipped; existence is the
    caller's to check. A registry that exists but cannot be read raises
    :class:`RegistryError`: a floor that silently read fewer libraries would
    let private bytes out.
    """
    path = _resolve(registry)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    except OSError as e:
        raise RegistryError(
            f"the registry of library roots {path} cannot be read ({e}); the rights "
            "floor cannot know every library on this machine, so nothing proceeds. "
            "Make it readable and retry."
        ) from e
    seen: set[str] = set()
    for line in lines:
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

    Idempotent. Raises :class:`RegistryError` when the registry cannot be
    written: a library the floor cannot find later must not be written to.
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
        # O_APPEND: one short write is atomic, so concurrent registrations
        # interleave whole lines and none is lost.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError as e:
        raise RegistryError(
            f"cannot record the library root {resolved} in the registry {path} "
            f"({e}); the rights checks of every other library would not see it, so "
            "nothing was written. Make that folder writable and retry."
        ) from e
    return True
