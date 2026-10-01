"""The lazy renderer registry (an#247): found in a fresh process, safe across threads, loud on failure.

The stage is behind the core's import firewall, so the registry names it by
module and imports it on the first lookup. Three ways that can go wrong, each
pinned here (review of an#270, S1 and S7):

- the lookup ``an render`` makes first (``find_for``) must load it -- checked in
  a FRESH process, because the test process has always imported the stage by
  then and a missing load would pass every other test;
- concurrent first lookups must all find it (they used to see a half-filled
  registry: 7 of 8 threads got ``None``);
- a backend that fails to import must be reported to the lookup that needed it
  and retried later, never silently forgotten.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from an.adapters._base import RendererLoadError, RendererLoadWarning, RendererRegistry
from an.ir.schema import Shot

ROOT = Path(__file__).resolve().parents[1]


def _fresh(code: str) -> dict:
    """Run ``code`` in a new interpreter importing THIS tree; return its JSON."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, env=env, check=False
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_lookup_an_render_makes_finds_the_stage_in_a_fresh_process():
    report = _fresh(
        """
import json, sys
import an
from an.adapters._base import _DEFAULT_REGISTRY, get_renderer
from an.ir.schema import Shot
before = "an.stage.render" in sys.modules
found = _DEFAULT_REGISTRY.find_for(Shot(id="s", renderer="cutout"))
stage = get_renderer("stage")
print(json.dumps({"before": before, "found": type(found).__module__ + "." + type(found).__name__,
                  "stage_is_it": stage is found, "root": an.__file__}))
"""
    )
    assert report["root"] == str(ROOT / "an" / "__init__.py")
    assert report["before"] is False, "importing the core must not load the stage"
    assert report["found"] == "an.stage.render.CutoutRenderer"
    assert report["stage_is_it"], "`stage` is the name the stage renderer claims"


def test_concurrent_first_lookups_all_find_the_stage():
    report = _fresh(
        """
import json, threading
import an
from an.adapters._base import _DEFAULT_REGISTRY
from an.ir.schema import Shot
n = 8
barrier, found = threading.Barrier(n), []
def look():
    barrier.wait()
    found.append(_DEFAULT_REGISTRY.find_for(Shot(id="s", renderer="cutout")) is not None)
threads = [threading.Thread(target=look) for _ in range(n)]
[t.start() for t in threads]; [t.join() for t in threads]
print(json.dumps({"found": found}))
"""
    )
    assert report["found"] == [True] * 8


class _Card:
    name = "card"
    supported_renderers = ("card",)

    def can_render(self, shot):
        return shot.renderer in self.supported_renderers

    def render(self, shot, ctx):  # pragma: no cover - never called
        raise AssertionError


def test_a_backend_that_fails_to_import_is_reported_and_retried():
    registry = RendererRegistry()
    registry.register_lazy("broken", "an_no_such_backend_for_this_test")
    registry.register(_Card())

    with pytest.raises(RendererLoadError, match="an_no_such_backend_for_this_test"):
        registry.get("broken")
    # Not forgotten: the next lookup tries again, and says so again.
    with pytest.raises(RendererLoadError):
        registry.get("broken")
    # A lookup it was not needed for is answered.
    assert registry.find_for(Shot(id="s", renderer="card")) is not None
    with pytest.warns(RendererLoadWarning, match="an_no_such_backend_for_this_test"):
        assert list(registry.names()) == ["card"]
    # A shot no renderer can draw, with a backend down: the error, not None.
    with pytest.raises(RendererLoadError):
        registry.find_for(Shot(id="s", renderer="mystery"))


def test_a_failed_backend_does_not_block_the_ones_after_it():
    registry = RendererRegistry()
    registry.register_lazy("broken", "an_no_such_backend_for_this_test")
    registry.register_lazy("cutout", "an.stage.render")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RendererLoadWarning)
        # The stage module registers into the DEFAULT registry; what matters
        # here is that this registry imported it despite the broken one first.
        registry.names()
    assert "an.stage.render" in registry._imported
    assert not registry._loaded, "the broken one is still pending, to be retried"


def test_a_genre_can_add_a_shot_key_part_before_any_lookup():
    """`cutan` (P8) adds key parts at install; the stage's keyer must be there
    even if nothing looked the registry up yet (review of an#270, S2)."""
    report = _fresh(
        """
import json, sys
import an
from an.build.keys import register_shot_key_part, shot_keyer_for
before = "an.stage.render" in sys.modules
register_shot_key_part("cutout", "genre_side_file", lambda shot, ctx: "x")
print(json.dumps({"before": before, "parts": sorted(shot_keyer_for("cutout").parts)}))
"""
    )
    assert report["before"] is False
    assert "genre_side_file" in report["parts"]
