"""The demo helper seats a synthesized character inside the demo frame (an#170).

At the demos' 480x270 a default-placed synthesized character had its hair
cropped by the top edge: the compiler places a character by the centre of its
BONE extent, which is not the centre of what is drawn. The demo helper
(`misc/demos/build_demos.py`) now places by the drawn bounds. Asserted on the
COMPILED document — no browser — by compiling the exact `stage` the helper
emits and walking the sprites.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

from an.adapters.cutout.compile import compile_shot
from an.adapters.cutout.serialize import to_dict
from an.characters import new_character
from an.ir.schema import AssetRef, Shot, StagePlacement
from an.project import init, load

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def demos():
    spec = importlib.util.spec_from_file_location(
        "_build_demos_under_test", ROOT / "misc" / "demos" / "build_demos.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _drawn_y_range(stage: StagePlacement | None) -> tuple[float, float]:
    """(top, bottom) of the character's sprites in frame pixels from the centre."""
    with tempfile.TemporaryDirectory() as d:
        root = init(Path(d) / "p")
        new_character(root / "assets" / "characters", name="c", use_dicebear=False)
        shot = Shot(
            id="s",
            renderer="cutout",
            duration=1.0,
            entities=[
                AssetRef(
                    kind="character", id="c", store="characters", ref="c", stage=stage
                )
            ],
        )
        doc = to_dict(compile_shot(shot, mall=load(root).mall, fps=24, strict_assets=True))
    (char,) = doc["scene"]["children"]
    tops, bottoms = [], []

    def walk(node, oy=0.0):
        t, v = node["transform"], node["visual"]
        y = oy + t["y"]
        top = y - v["anchor_y"] * v["height"]
        tops.append(top)
        bottoms.append(top + v["height"])
        for kid in node.get("children") or []:
            walk(kid, y)

    for part in char["children"]:
        walk(part)
    k, y0 = char["transform"]["scale_y"], char["transform"]["y"]
    return y0 + k * min(tops), y0 + k * max(bottoms)


def test_the_default_placement_is_the_problem_being_fixed(demos):
    """Guard the premise: unplaced, the drawn art overflows the demo frame."""
    top, bottom = _drawn_y_range(None)
    half = demos.DEMO_RESOLUTION[1] / 2
    assert top < -half or bottom > half - demos.FRAME_MARGIN * 2 * half


def test_full_body_framing_leaves_the_margin_at_both_ends(demos):
    y, scale = demos.frame_full_body()
    top, bottom = _drawn_y_range(StagePlacement(at=(0.0, y), scale=scale))
    half = demos.DEMO_RESOLUTION[1] / 2
    margin = demos.FRAME_MARGIN * demos.DEMO_RESOLUTION[1]
    assert top == pytest.approx(-half + margin, abs=1.0)
    assert bottom == pytest.approx(half - margin, abs=1.0)


@pytest.mark.parametrize("scale", (1.4, 2.0))
def test_seat_head_puts_the_head_a_margin_below_the_top_edge(demos, scale):
    top, _ = _drawn_y_range(StagePlacement(at=(0.0, demos.seat_head(scale)), scale=scale))
    half = demos.DEMO_RESOLUTION[1] / 2
    margin = demos.FRAME_MARGIN * demos.DEMO_RESOLUTION[1]
    assert top == pytest.approx(-half + margin, abs=1.0)


def test_the_entities_block_places_every_character_at_its_layout_x(demos):
    import yaml

    block = demos._entities("a", "b", "c").strip("`\n").removeprefix("yaml entities\n")
    rows = yaml.safe_load(block)
    xs = [r["stage"]["at"][0] for r in rows]
    assert xs == sorted(xs) and len(set(xs)) == 3
    assert {r["stage"]["scale"] for r in rows} == {rows[0]["stage"]["scale"]}


def test_unframed_entities_carry_no_stage(demos):
    assert "stage" not in demos._entities("a", framed=False)
