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
    _redirect_account_home_for_the_session()


def _redirect_account_home_for_the_session() -> None:
    """Point the machine registry into a temp folder for the WHOLE session.

    The per-test fixture below gives each test a fresh registry, but a
    module- or session-scoped fixture runs before it: one that draws a
    character (the factory records what it draws, an#269) or publishes would
    otherwise write the developer's real ``~/.local/share/an/registry``. This
    session-wide redirect is what those fixtures see; each test still gets
    its own fresh one.
    """
    import tempfile
    from pathlib import Path

    from an.library import registry

    home = Path(tempfile.mkdtemp(prefix="an-session-account-home-"))
    registry._account_home = lambda: home


import pytest


@pytest.fixture(autouse=True)
def _isolated_library_registry(tmp_path_factory, monkeypatch):
    """Point the machine's library registry and statement memory into a fresh temp folder.

    The registry (:mod:`an.library.registry`, an#249) lives under the account's
    home as the OS records it, deliberately ignoring every environment variable,
    so the ``AN_HOME`` / ``XDG_DATA_HOME`` redirection the library tests use
    cannot move it. Every test and doctest that publishes would otherwise
    append to the developer's real registry — and one test's private bytes
    would sit in the next test's rights floor. Fresh per test, for both
    reasons. The account home is what is replaced, so the real path logic
    (``machine_registry_path``) still runs, and a test can hold it to its
    independence from the environment.
    """
    from an.library import registry

    home = tmp_path_factory.mktemp("account-home")
    monkeypatch.setattr(registry, "_account_home", lambda: home)
