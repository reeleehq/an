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

__all__ = ["drawing", "write_bytes", "write_derived_text", "write_text"]

_LOG: ContextVar[dict[str, str] | None] = ContextVar("an_factory_drawn", default=None)


@contextmanager
def drawing() -> Iterator[dict[str, str]]:
    """Log ``{resolved path: sha256}`` of every file written through this module, in this context.

    Re-entrant: inside an open drawing (``add_gaze`` called by
    ``new_character``) the same log is shared, so the outer call sees every
    byte the inner one wrote.
    """
    held = _LOG.get()
    if held is not None:
        yield held
        return
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


def write_derived_text(
    path: str | os.PathLike, source: bytes, text: str, *, encoding: str = "utf-8"
) -> None:
    """Write ``text``, derived from ``source`` — the bytes just read back from ``path``.

    Logged only if ``source`` is exactly what this drawing itself wrote there:
    a file swapped in between the factory's write and its re-read (a rescale)
    is rewritten, but not as the factory's drawing (review-288 round 2).

    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as d, drawing() as log:
    ...     p = pathlib.Path(d) / "a.svg"
    ...     write_text(p, "<svg/>")
    ...     p.write_bytes(b"<svg>swapped</svg>")  # not the factory's write
    ...     write_derived_text(p, p.read_bytes(), "<svg>scaled</svg>")
    ...     str(p.resolve()) in log
    18
    False
    """
    path = Path(path)
    log = _LOG.get()
    key = str(path.resolve())
    if log is None or log.get(key) == hashlib.sha256(source).hexdigest():
        write_text(path, text, encoding=encoding)
        return
    path.write_bytes(text.replace("\n", os.linesep).encode(encoding))
    log.pop(key, None)
