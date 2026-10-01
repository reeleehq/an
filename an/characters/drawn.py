"""What the character factory wrote, as it wrote it: the in-memory log behind its record of drawn bytes.

The machine's record of bytes the factory drew (an#269,
``an.library.registry.record_generated``) verifies the factory's stamps in the
asset library. It must hold the digests of bytes the factory itself produced,
never of whatever sits on disk when it finishes: a file swapped in while
``new_character`` runs is not the factory's drawing. So every file the factory
writes goes through :func:`write_text` / :func:`write_bytes`, which write it AND,
while a :func:`drawing` is open in this context, log the SHA-256 of the exact
bytes written — computed in memory at write time.

>>> import tempfile, pathlib
>>> with tempfile.TemporaryDirectory() as d, drawing() as log:
...     p = pathlib.Path(d) / "a.svg"
...     write_text(p, "<svg/>")
...     log[str(p.resolve())] == hashlib.sha256(b"<svg/>").hexdigest()
True
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

__all__ = ["drawing", "write_bytes", "write_text"]

_LOG: ContextVar[dict[str, str] | None] = ContextVar("an_factory_drawn", default=None)


@contextmanager
def drawing() -> Iterator[dict[str, str]]:
    """Log ``{resolved path: sha256}`` of every file written through this module, in this context."""
    log: dict[str, str] = {}
    token = _LOG.set(log)
    try:
        yield log
    finally:
        _LOG.reset(token)


def write_bytes(path: str | os.PathLike, data: bytes) -> None:
    """Write ``data`` to ``path``, logging its digest if a :func:`drawing` is open."""
    path = Path(path)
    path.write_bytes(data)
    log = _LOG.get()
    if log is not None:
        log[str(path.resolve())] = hashlib.sha256(data).hexdigest()


def write_text(path: str | os.PathLike, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` as ``Path.write_text`` does (newlines as the platform writes them), logged."""
    write_bytes(path, text.replace("\n", os.linesep).encode(encoding))
