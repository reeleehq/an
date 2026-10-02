"""A child python process the tests spawn must not reach the real data folder (an#302).

The root ``conftest.py`` redirects the machine registry in the pytest process by
monkeypatching, which a child interpreter does not inherit. These tests hold the
mechanism that does carry it (``tests/_child_guard/sitecustomize.py``, put on
every child's ``PYTHONPATH`` by a ``subprocess.Popen`` wrapper): a child sees
the redirected home however its ``env=`` was built, and the guard costs the
import-firewall tests nothing because ``an`` is not imported until asked for.

Nothing here writes to a registry: each child only REPORTS where it would write.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from an.library import registry

ROOT = Path(__file__).resolve().parents[1]

_PROBE = (
    "import sys; pre = 'an' in sys.modules\n"
    "from an.library import registry\n"
    "print(registry.machine_registry_dir()); print(pre)"
)


def _minimal_env() -> dict:
    """Just the tree under test; Windows cannot start Python without ``SYSTEMROOT``."""
    keep = {k: v for k, v in os.environ.items() if k.upper() == "SYSTEMROOT"}
    return {**keep, "PYTHONPATH": str(ROOT)}


def _probe(**kwargs) -> tuple[Path, bool]:
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
        **kwargs,
    )
    where, pre = out.stdout.split("\n")[:2]
    return Path(where), pre == "True"


def _real_data_dir() -> Path:
    """The real account's ``<data>/an``, as captured BEFORE the session redirect."""
    import conftest

    return conftest._REAL_DATA_SNAPSHOT["dirs"][0]


def _real_home() -> Path:
    import conftest

    return conftest._REAL_DATA_SNAPSHOT["home"]


def _expected() -> Path:
    return registry.machine_registry_dir()


@pytest.mark.parametrize(
    "env",
    [
        pytest.param(None, id="inherited"),
        pytest.param(_minimal_env(), id="pythonpath-replaced"),
        pytest.param(
            {**_minimal_env(), "PATH": os.environ.get("PATH", "")}, id="minimal"
        ),
    ],
)
def test_a_child_sees_the_redirected_registry(env):
    kwargs = {} if env is None else {"env": env}
    if env is None:
        # `an` must resolve to THIS tree even when the editable install points
        # at another checkout; keep the parent's environment otherwise.
        kwargs["env"] = {**os.environ, "PYTHONPATH": str(ROOT)}
    where, imported_before_asked = _probe(**kwargs)
    assert where == _expected()
    assert not imported_before_asked, "the child guard must not import `an` eagerly"


def test_the_redirect_is_not_the_real_data_folder():
    assert not str(_expected()).startswith(str(_real_data_dir()))


def test_a_child_follows_the_per_test_home(tmp_path, monkeypatch):
    import conftest

    other = tmp_path / "other-home"
    monkeypatch.setitem(conftest._CHILD_STATE, "home", other)
    where, _ = _probe(env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert other in where.parents


def test_a_child_that_bypasses_the_redirect_is_logged(tmp_path):
    """The tripwire: a child whose registry resolves to the real folder logs itself."""
    log = tmp_path / "attempts.log"
    code = (
        "from an.library import registry\n"
        "import pathlib\n"
        "registry._account_home = lambda: pathlib.Path(%r)\n"
        "registry.machine_registry_dir()\n"
    ) % str(_real_home())
    # The child's own override replaces the redirect AFTER the guard patched
    # `_account_home`, so `machine_registry_dir` (the guard's wrapper) now
    # resolves into the real folder: exactly the escape the log exists for.
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT),
            "AN_TEST_REAL_HOME_LOG": str(log),
        },
    )
    assert log.exists() and "registry" in log.read_text(encoding="utf-8")


