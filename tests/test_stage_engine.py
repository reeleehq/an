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


# --------------------------------- a genre's runtime visuals (P8's mouth and eye)

def _demo_genre():
    from an.genres import Genre, RuntimeScript

    return Genre(
        "demo_runtime_visual",
        runtime_scripts=(RuntimeScript("demo_disc", "tests:fixtures/runtime_visual_demo.js"),),
    )


def test_a_genres_runtime_script_is_staged_and_keyed():
    from an.genres import register_genre, without_genres
    from an.stage.render import runtime_extensions

    assert runtime_extensions() == "", "nothing registered: the shipped file stays"
    with without_genres():
        register_genre(_demo_genre())
        code = runtime_extensions()
    assert "anRegisterVisual('demo_disc'" in code


@pytest.mark.browser
def test_a_genre_draws_its_own_visual_kind_on_the_stage(tmp_path):
    """The hook `cutan` takes the mouth and eye through: a kind the stage does
    not know, drawn by the genre's script, with no edit to runtime.js."""
    import base64
    import io

    from PIL import Image

    from an.genres import register_genre, without_genres
    from an.stage.render import StageEngine

    doc = {
        "scene": {"name": "root", "children": [
            {"name": "disc", "transform": {"x": 0.0, "y": 0.0},
             "visual": {"kind": "demo_disc", "width": 400, "height": 400}},
        ]},
        "timeline": {"duration": 1.0, "tracks": []},
        "animations": {},
    }
    with without_genres():
        register_genre(_demo_genre())
        with StageEngine().open_document(doc, workspace=tmp_path) as session:
            png = session.frame(0.0)
    with Image.open(io.BytesIO(png)) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        assert rgb.getpixel((w // 2, h // 2)) == (255, 0, 0)
