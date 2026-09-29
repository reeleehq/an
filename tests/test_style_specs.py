"""The `an-style` skill's style specs claim that every `live` key maps onto a
shipped feature. This checks each claim against the code, so a spec cannot
drift into asking for something `an` does not do.

`guidance` is free-form on purpose — it is what `an` does NOT do yet — so the
one thing checked about it is that nothing from it has leaked into `live`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from an.adapters.cutout.easing import EASING_FUNCS, apply_easing
from an.environments import EnvironmentDescriptor
from an.ir.camera import CAMERA_MOVES
from an.ir.schema import Meta
from an.motion import PRESETS
from an.styles import StylePack
from an.verify.style import StyleLintVerifier

SPEC_DIR = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "an-style" / "styles"
SPECS = sorted(SPEC_DIR.glob("*.yaml"))

#: Every key `live` may carry, and nothing else.
LIVE_KEYS = {
    "meta", "style_pack", "environment", "camera", "easing",
    "tween_duration_s", "shots", "characters", "motion_presets",
}
TOP_KEYS = {"style", "title", "cost_class", "cost_note", "live", "targets", "guidance"}
COST_CLASSES = {"low", "low_to_medium", "medium", "high", "very_high"}
GENERATORS = {"offline", "promote"}


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_the_six_researched_styles_have_specs():
    assert {p.stem for p in SPECS} >= {
        "south_park", "oversimplified", "kurzgesagt", "gilliam", "reiniger", "norstein"
    }


@pytest.fixture(params=SPECS, ids=lambda p: p.stem)
def spec(request):
    return _load(request.param) | {"_stem": request.param.stem}


def test_shape(spec):
    assert set(spec) - {"_stem"} <= TOP_KEYS
    assert spec["style"] == spec["_stem"]
    assert spec["cost_class"] in COST_CLASSES
    assert set(spec["live"]) <= LIVE_KEYS, set(spec["live"]) - LIVE_KEYS


def test_meta_is_a_valid_meta(spec):
    meta = spec["live"]["meta"]
    m = Meta(**meta)
    if m.step_hz is not None:
        assert m.step_hz <= m.fps
    if "style_pack" in meta:
        assert spec["live"]["style_pack"]["name"] == meta["style_pack"]


def test_style_pack_only_names_reachable_roles(spec):
    pack = spec["live"].get("style_pack")
    if pack is not None:
        StylePack(**pack)  # refuses an unreachable or unknown role


def test_environment_is_a_preset_or_a_valid_descriptor(spec):
    env = spec["live"].get("environment")
    if env is None:
        return
    assert set(env) in ({"preset"}, {"descriptor"})
    if "preset" in env:
        assert env["preset"] in {"park", "indoor", "night", "sunset", "default"}
    else:
        d = EnvironmentDescriptor(**env["descriptor"])
        names = [p.name for p in d.planes]
        assert d.characters_after is None or d.characters_after in names


def test_camera_moves_exist(spec):
    cam = spec["live"]["camera"]
    assert cam["default"] in CAMERA_MOVES
    assert cam["default"] in cam["allowed"]
    assert set(cam["allowed"]) <= set(CAMERA_MOVES)


def test_easings_exist(spec):
    for e in spec["live"]["easing"]:
        if isinstance(e, str):
            assert e in EASING_FUNCS
        else:
            apply_easing(e, 0.5)  # a 4-point cubic-Bezier the evaluator accepts


def test_ranges_and_characters(spec):
    live = spec["live"]
    lo, hi = live["tween_duration_s"]
    assert 0 < lo <= hi
    shots = live["shots"]
    assert shots["range_s"][0] <= shots["mean_s"] <= shots["range_s"][1]
    chars = live["characters"]
    assert chars["generate"] in GENERATORS
    assert set(chars) <= {"generate", "mouth_variants", "tint"}
    if "tint" in chars:
        assert chars["tint"].startswith("#") and len(chars["tint"]) == 7


def test_targets_are_measurable(spec):
    v = StyleLintVerifier(spec)  # refuses an unknown target or a bad range
    assert v.targets and v.style == spec["style"]


def test_motion_presets_exist(spec):
    assert set(spec["live"].get("motion_presets", [])) <= set(PRESETS)
