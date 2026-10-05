"""The paid providers' API keys never reach a test or doctest that is not
``live_api`` (an#311).

Checked in a child pytest whose environment HAS every key, so the guard is
proven on every machine — not only on one where a developer happened to export one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from an.live_api import paid_provider_key_vars

_PROBE = '''
"""A doctest sees no key either.

>>> import os
>>> [v for v in {vars!r} if os.environ.get(v)]
[]
"""
import os
import pytest

from an.audio.elevenlabs_tts import ElevenLabsTTS, ElevenLabsUnavailableError


def test_ordinary():
    assert not any(os.environ.get(v) for v in {vars!r})
    with pytest.raises(ElevenLabsUnavailableError):
        ElevenLabsTTS().check_available()


@pytest.mark.live_api
def test_live_keeps_it():
    assert all(os.environ.get(v) == "sk-planted" for v in {vars!r})
'''


def test_a_planted_key_is_invisible_to_ordinary_tests_and_doctests_and_kept_for_live_ones(
    tmp_path,
):
    keys = paid_provider_key_vars()
    probe = tmp_path / "test_probe.py"
    probe.write_text(_PROBE.format(vars=keys), encoding="utf-8")
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, **{v: "sk-planted" for v in keys}, "PYTHONPATH": str(root)}
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "conftest", "-p", "no:cacheprovider",
         "--rootdir", str(tmp_path), "-o", "addopts=", "-m", "", "--doctest-modules",
         str(probe)],
        capture_output=True, text=True, env=env, cwd=root,
    )  # fmt: skip
    assert "3 passed" in out.stdout, out.stdout[-2000:] + out.stderr[-2000:]
