"""The stage as the first engine (an#247): what it is, and that its read-back is the kernel's.

The stage engine is TIME-driven: ``runtime.js`` evaluates the compiled channels
itself. So its session exposes ``state(t)``, the pose the runtime computed, and
:mod:`an.engines.conformance` holds that to the timing kernel's golden vectors
(``an/data/timing/timing_vectors.json``) -- the contract ``an.timing`` and
``previz`` assert. This is the check of the engine FROM ITS OWN SIDE, in the
browser that draws the frames; the node-run parity tests
(``tests/test_timing_contract.py``) check the same functions extracted from the
file.
"""

from __future__ import annotations

import pytest

from an.engines import DRIVE_TIME, TIER_SEEKABLE, describe
from an.engines.conformance import readback_mismatches, vector_cases


def test_the_stage_sessions_are_time_driven_with_a_readback():
    from an.stage.render import _CanvasStageSession, _ScreenshotStageSession

    canvas = describe(_CanvasStageSession)
    assert (canvas.tier, canvas.drive) == (TIER_SEEKABLE, DRIVE_TIME)
    assert {"readback", "batch", "resolve", "provenance"} <= canvas.features
    screenshot = describe(_ScreenshotStageSession)
    assert {"readback", "batch"} <= screenshot.features
    assert "resolve" not in screenshot.features, "a lone screenshot reaches disk untouched"


def test_the_stage_renderer_claims_both_names_and_registers_lazily():
    import sys

    from an.adapters import get_renderer, list_renderers
    from an.ir.schema import Shot

    assert "cutout" in list_renderers()
    renderer = get_renderer("cutout")
    assert renderer.can_render(Shot(id="a", renderer="stage"))
    assert renderer.can_render(Shot(id="b", renderer="cutout"))
    assert type(renderer).__module__ == "an.stage.render"
    assert "an.stage.render" in sys.modules


def test_the_stage_has_vectors_to_conform_to():
    assert len(vector_cases(space="stage.node")) >= 10


@pytest.mark.browser
def test_the_stage_engines_readback_reproduces_every_stage_vector(tmp_path):
    """Every sample of every ``stage.node`` case, read back from the page."""
    from an.stage.render import StageEngine

    engine = StageEngine()
    mismatches = []
    for i, case in enumerate(vector_cases(space="stage.node")):
        document = dict(case["document"])
        document.setdefault("meta", {})
        document["meta"] = {**document["meta"], "duration": document["timeline"]["duration"]}
        with engine.open_document(document, workspace=tmp_path / f"case_{i}") as session:
            mismatches += readback_mismatches(session.state, case)
    assert not mismatches, mismatches[:5]


@pytest.mark.browser
def test_a_wrong_readback_is_reported_not_absorbed(tmp_path):
    """The check can fail: a session that reads back a shifted time does."""
    from an.stage.render import StageEngine

    case = next(c for c in vector_cases(space="stage.node") if len(c["samples"]) > 2)
    with StageEngine().open_document(dict(case["document"]), workspace=tmp_path) as session:
        late = lambda t: session.state(t + 0.05)  # noqa: E731
        assert readback_mismatches(late, case)
