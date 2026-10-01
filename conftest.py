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

from pathlib import Path


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
    import sys

    from an.library.root import POSIX_DATA_DEFAULT, WINDOWS_DATA_DEFAULT

    defaults = (
        WINDOWS_DATA_DEFAULT if sys.platform.startswith("win") else POSIX_DATA_DEFAULT
    )
    data = registry._account_home().joinpath(*defaults)
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
    real_prefixes = tuple(str(d) for d in data_dirs)  # not their parent: on Windows
    # the temp dir (home of the redirect) sits inside `AppData/Local`.
    _REAL_DATA_SNAPSHOT["dirs"] = data_dirs
    _REAL_DATA_SNAPSHOT["home"] = registry._account_home()
    _REAL_DATA_SNAPSHOT["before"] = _snapshot(data_dirs)

    def note(path) -> None:
        if str(path).startswith(real_prefixes):
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

    child_log = _CHILD_STATE.get("path")
    if child_log is not None and child_log.exists() and child_log.stat().st_size:
        say(
            "REAL-HOME GUARD: a CHILD python process reached the real data folder "
            "despite the redirect (an#302):\n"
            + child_log.read_text(encoding="utf-8")[:4000]
        )
        session.exitstatus = 1
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
    from an.library import registry

    home = Path(tempfile.mkdtemp(prefix="an-session-account-home-"))
    registry._account_home = lambda: home
    _redirect_children_too(home)


#: Environment variable naming the redirected account home for child pythons.
CHILD_HOME_ENV: str = "AN_TEST_ACCOUNT_HOME"
#: Environment variable naming the file a child appends to if it reaches the real data folder.
CHILD_LOG_ENV: str = "AN_TEST_REAL_HOME_LOG"
#: The folder whose ``sitecustomize`` applies the redirect inside a child (an#302).
CHILD_GUARD_DIR = Path(__file__).parent / "tests" / "_child_guard"


def _redirect_children_too(home) -> None:
    """Make every child python process the tests spawn honour the same redirect.

    The monkeypatch above lives in THIS interpreter; a child (a CLI test, a
    ``[sys.executable, "-c", ...]`` probe) is a new one and, left alone, would
    write the developer's real registry (an#302). The library reads no
    environment variable for that location, so the redirect rides on
    ``tests/_child_guard/sitecustomize.py`` instead, put on each child's
    ``PYTHONPATH`` by wrapping ``subprocess.Popen`` — whatever ``env=`` the
    test built, including one that replaces ``PYTHONPATH`` wholesale.
    A child that reaches the real folder regardless logs itself to
    ``CHILD_LOG_ENV``, and :func:`pytest_sessionfinish` fails the run on it.
    """
    import os
    import subprocess

    log = home / "child-real-home-writes.log"
    os.environ[CHILD_HOME_ENV] = str(home)
    os.environ[CHILD_LOG_ENV] = str(log)
    _CHILD_STATE["path"] = log
    _CHILD_STATE["home"] = home
    init = subprocess.Popen.__init__

    def popen_init(self, *args, **kwargs):
        env = dict(os.environ if kwargs.get("env") is None else kwargs["env"])
        # The CURRENT home: the per-test fixture swaps it, like the in-process one.
        env[CHILD_HOME_ENV] = str(_CHILD_STATE["home"])
        env.setdefault(CHILD_LOG_ENV, str(log))
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(
            [str(CHILD_GUARD_DIR)] + ([existing] if existing else [])
        )
        kwargs["env"] = env
        return init(self, *args, **kwargs)

    subprocess.Popen.__init__ = popen_init


#: Where the child-process tripwire writes (set by :func:`_redirect_children_too`).
_CHILD_STATE: dict = {}


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
    # Children get the same fresh registry (an#302), restored afterwards.
    monkeypatch.setitem(_CHILD_STATE, "home", home)
