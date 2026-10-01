"""Redirect the machine registry in a test's CHILD python processes (an#302).

The repository's root ``conftest.py`` redirects :func:`an.library.registry._account_home`
into a temp folder for the pytest process, but that is a monkeypatch: a child
python (a CLI test, a ``subprocess.run([sys.executable, ...])`` probe) is a new
interpreter and would write the developer's REAL ``~/.local/share/an/registry``.
The library deliberately reads no environment variable for that location, so
the redirect cannot travel through one. This module travels instead: the
conftest puts this folder on every child's ``PYTHONPATH`` (see
``_inject_child_guard`` there), Python imports ``sitecustomize`` at startup,
and it patches the registry module the moment — and only if — the child
imports it. ``an`` itself is never imported here, so the import-firewall tests,
which hold what ``import an`` pulls in, see no difference.

Inert unless ``AN_TEST_ACCOUNT_HOME`` is set. If a child reaches the real data
folder anyway (the redirect bypassed), the attempt is appended, with its stack,
to the file named by ``AN_TEST_REAL_HOME_LOG`` and the parent session fails.
"""

import os
import sys

HOME_ENV = "AN_TEST_ACCOUNT_HOME"
LOG_ENV = "AN_TEST_REAL_HOME_LOG"
TARGET = "an.library.registry"


def _patch(module, home, log):
    from pathlib import Path

    real_home = module._account_home()
    defaults = (
        module.WINDOWS_DATA_DEFAULT
        if sys.platform.startswith("win")
        else module.POSIX_DATA_DEFAULT
    )
    real_data = real_home.joinpath(*defaults)
    redirected = Path(home)
    module._account_home = lambda: redirected
    registry_dir = module.machine_registry_dir

    def tripwire():
        out = registry_dir()
        if log and str(out).startswith(str(real_data)):
            import traceback

            with open(log, "a", encoding="utf-8") as f:
                f.write(f"{out}\n" + "".join(traceback.format_stack(limit=30)) + "\n")
        return out

    module.machine_registry_dir = tripwire


class _PatchOnImport:
    """A meta-path finder that wraps the target's loader, then gets out of the way."""

    def __init__(self, home, log):
        self.home, self.log, self._busy = home, log, False

    def find_spec(self, name, path=None, target=None):
        if name != TARGET or self._busy:
            return None
        self._busy = True
        try:
            for finder in sys.meta_path:
                if finder is self or not hasattr(finder, "find_spec"):
                    continue
                spec = finder.find_spec(name, path, target)
                if spec is not None and spec.loader is not None:
                    break
            else:
                return None
        finally:
            self._busy = False
        loader, home, log = spec.loader, self.home, self.log
        exec_module = loader.exec_module

        def exec_and_patch(module):
            exec_module(module)
            _patch(module, home, log)

        loader.exec_module = exec_and_patch
        return spec


if os.environ.get(HOME_ENV):
    sys.meta_path.insert(
        0, _PatchOnImport(os.environ[HOME_ENV], os.environ.get(LOG_ENV))
    )
