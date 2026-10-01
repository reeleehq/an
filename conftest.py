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
    _install_real_home_guard()
    _redirect_account_home_for_the_session()


#: What the session guard found: stack traces of writes that reached the real
#: account's data folder (review-269 B3).
_REAL_HOME_WRITES: list[str] = []
_REAL_DATA_SNAPSHOT: dict = {}


def _real_data_dirs():
    from an.library import registry
    from an.library.root import POSIX_DATA_DEFAULT

    data = registry._account_home().joinpath(*POSIX_DATA_DEFAULT)
    return [data / "an", data / "cutan"]


def _snapshot(dirs) -> dict:
    out = {}
    for d in dirs:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            try:
                st = p.lstat()
            except OSError:
                continue
            out[str(p)] = (st.st_mtime_ns, st.st_size)
    return out


def _install_real_home_guard() -> None:
    """Fail the run if this process writes into the real account's data folder.

    Two layers, installed before any fixture runs:

    - a tripwire, in this process: every library-store write and every
      machine-registry path that lands under the real data folder is recorded
      with its stack, and fails the session (``pytest_sessionfinish``);
    - a snapshot of ``<data>/an`` and ``<data>/cutan`` before and after the
      session. On CI (``CI`` set) any difference fails the run. On a developer
      machine other sessions (an end-to-end render, an agent publishing) write
      there concurrently, so a difference is reported, and fails only with
      ``AN_TEST_HOME_GUARD=strict``.
    """
    import traceback

    from an.library import registry, stores

    data_dirs = _real_data_dirs()
    real_data = str(data_dirs[0].parent)
    _REAL_DATA_SNAPSHOT["dirs"] = data_dirs
    _REAL_DATA_SNAPSHOT["before"] = _snapshot(data_dirs)

    def note(path) -> None:
        if str(path).startswith(real_data):
            _REAL_HOME_WRITES.append(
                f"{path}\n" + "".join(traceback.format_stack(limit=30))
            )

    temp, delete = stores.LocalFiles._temp, stores.LocalFiles.__delitem__

    def guarded_temp(self, path, data):
        note(path)
        return temp(self, path, data)

    def guarded_delete(self, key):
        note(self._path(key))
        return delete(self, key)

    stores.LocalFiles._temp = guarded_temp
    stores.LocalFiles.__delitem__ = guarded_delete
    registry_dir = registry.machine_registry_dir

    def guarded_registry_dir():
        out = registry_dir()
        note(out)
        return out

    registry.machine_registry_dir = guarded_registry_dir


def pytest_collection_modifyitems(config, items):  # noqa: D103 — a pytest hook
    # Every test gets a fresh registry, so every publish is a "first use": the
    # RegistryWarning would fire once per publishing test and bury real
    # warnings (review-269 N2). `pytest.warns` still sees it.
    mark = pytest.mark.filterwarnings("ignore::an.library.registry.RegistryWarning")
    for item in items:
        item.add_marker(mark)


def pytest_sessionfinish(session, exitstatus):  # noqa: D103 — a pytest hook
    import os

    reporter = session.config.pluginmanager.get_plugin("terminalreporter")

    def say(text: str) -> None:
        if reporter is not None:
            reporter.write_line(text)

    if _REAL_HOME_WRITES:
        say(
            f"REAL-HOME GUARD: {len(_REAL_HOME_WRITES)} write(s) or registry access(es) "
            "reached the real data folder from this test process; first one:\n"
            + _REAL_HOME_WRITES[0]
        )
        session.exitstatus = 1
    if "before" in _REAL_DATA_SNAPSHOT:
        after = _snapshot(_REAL_DATA_SNAPSHOT["dirs"])
        before = _REAL_DATA_SNAPSHOT["before"]
        changed = sorted(
            k for k in set(before) | set(after) if before.get(k) != after.get(k)
        )
        if changed:
            strict = (
                os.environ.get("CI") or os.environ.get("AN_TEST_HOME_GUARD") == "strict"
            )
            say(
                f"REAL-HOME GUARD: {len(changed)} path(s) under the real data folder "
                "changed during the session"
                + (
                    ""
                    if strict
                    else " (another process? set AN_TEST_HOME_GUARD=strict to fail on it)"
                )
                + ":\n  "
                + "\n  ".join(changed[:20])
            )
            if strict:
                session.exitstatus = 1


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
