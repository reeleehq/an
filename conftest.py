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


import pytest


@pytest.fixture(autouse=True)
def _isolated_library_registry(tmp_path_factory, monkeypatch):
    """Point the machine's registry of library roots into a fresh temp folder.

    The registry (:mod:`an.library.registry`, an#249) lives at a path that
    deliberately ignores every environment variable, so the ``AN_HOME`` /
    ``XDG_DATA_HOME`` redirection the library tests use cannot move it. Every
    test and doctest that publishes would otherwise append its temp root to the
    developer's real registry — and one test's private bytes would sit in the
    next test's rights floor. Fresh per test, for both reasons.
    """
    from an.library import registry

    path = tmp_path_factory.mktemp("library-registry") / registry.REGISTRY_FILENAME
    monkeypatch.setattr(registry, "machine_registry_path", lambda: path)
