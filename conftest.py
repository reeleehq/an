"""Repository-wide pytest setup: load the genres, as the real entry points do.

Genres are discovered explicitly (ADR 0001 decision 3): importing ``an``
registers none, and ``an.load(project)`` / the CLI call
:func:`an.genres.load`. Most tests and doctests build scenes with the cut-out
genre's kinds (``play``, ``expression``, ``character``, ``[emotion]``)
without going through either, so the session calls the same
:func:`an.genres.load` once, here — the in-distribution genres are found
whatever the installed metadata says. Tests of the unloaded core use
:func:`an.genres.without_genres`; the entry points themselves are held by
subprocess tests that run with no pre-registration
(``tests/test_open_document_model.py``).

At the repository root so it reaches both ``tests/`` and the doctests under
``an/`` (CI's ``--doctest-modules``).
"""

from __future__ import annotations


def pytest_configure(config):  # noqa: D103 — a pytest hook
    from an.genres import load

    load()
