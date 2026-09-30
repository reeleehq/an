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
from an.audio.effects import normalize_effects
from an.environments import EnvironmentDescriptor
from an.ir.camera import CAMERA_MOVES
from an.ir.schema import Meta, SoundCue, Transition
from an.motion import PRESETS
from an.styles import StylePack, SurfaceTreatment
from an.verify.style import StyleLintVerifier

SPEC_DIR = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "an-style" / "styles"
SPECS = sorted(SPEC_DIR.glob("*.yaml"))

#: Every key `live` may carry, and nothing else.
LIVE_KEYS = {
    "meta", "style_pack", "environment", "camera", "easing",
    "tween_duration_s", "shots", "characters", "motion_presets",
    "transitions", "sound", "voice", "entity_surface",
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
        StylePack(**pack)  # refuses an unreachable or unknown role, or a bad treatment


def test_surface_treatments_are_live_where_they_ship():
    """an#163: the outline, the paper-gap shadow and the grain are compiled
    now, so South Park carries them under `live` (and no longer under
    `guidance`), and Kurzgesagt's glow is a per-entity template."""
    sp = _load(SPEC_DIR / "south_park.yaml")
    pack = StylePack(**sp["live"]["style_pack"])
    assert pack.surface.outline and pack.surface.shadow and pack.grain
    assert not {"outline", "paper_gap_shadow", "paper_grain"} & set(sp["guidance"])
    kz = _load(SPEC_DIR / "kurzgesagt.yaml")
    assert "glow" not in kz["guidance"]


def test_an_entity_surface_template_is_a_valid_treatment(spec):
    template = spec["live"].get("entity_surface")
    if template is not None:
        assert not SurfaceTreatment(**template).is_empty()


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


def test_the_default_easing_is_live_and_is_the_style_s_house_curve(spec):
    """``meta.default_easing`` (an#166) is a real `Meta` key the compiler reads,
    so every spec sets it — to the FIRST of ``live.easing``, the style's house
    curve; the rest of that list are the curves a move may name instead."""
    meta = Meta(**spec["live"]["meta"])
    assert meta.default_easing is not None
    assert meta.default_easing == spec["live"]["easing"][0]
    apply_easing(meta.default_easing, 0.5)


def test_ranges_and_characters(spec):
    live = spec["live"]
    lo, hi = live["tween_duration_s"]
    assert 0 < lo <= hi
    shots = live["shots"]
    assert shots["range_s"][0] <= shots["mean_s"] <= shots["range_s"][1]
    chars = live["characters"]
    assert chars["generate"] in GENERATORS
    assert set(chars) <= {"generate", "mouth_variants", "tint"} | set(FACTORY_KNOBS)
    if "tint" in chars:
        assert chars["tint"].startswith("#") and len(chars["tint"]) == 7


#: `live.characters` keys that are `new_character` keyword arguments, with how a
#: spec may spell each: `hat` lists the choices a cast picks from, and `palette`
#: is `per_character` (the style's identity is each figure's own costume) or a
#: role -> colour map.
FACTORY_KNOBS = ("build", "head_scale", "hat", "sash", "palette")


def test_character_knobs_are_live_factory_settings(spec, tmp_path):
    """Every factory knob a spec names is a real `new_character` argument with a
    value the factory accepts — checked by BUILDING one character per hat."""
    import inspect

    from an.characters import new_character
    from an.characters.factory import BUILDS, HATS

    chars = spec["live"]["characters"]
    knobs = {k: chars[k] for k in FACTORY_KNOBS if k in chars}
    if not knobs:
        return
    params = inspect.signature(new_character).parameters
    assert set(knobs) <= set(params), set(knobs) - set(params)
    if "build" in knobs:
        assert knobs["build"] in BUILDS
    hats = knobs.pop("hat", ["none"])
    assert isinstance(hats, list) and set(hats) <= set(HATS)
    palette = knobs.pop("palette", None)
    assert palette == "per_character" or isinstance(palette, (dict, type(None)))
    if isinstance(palette, dict):
        knobs["palette"] = palette
    if chars["generate"] != "offline":
        return
    for i, hat in enumerate(hats):
        new_character(tmp_path, name=f"c{i}", use_dicebear=False, hat=hat, **knobs)


def test_targets_are_measurable(spec):
    v = StyleLintVerifier(spec)  # refuses an unknown target or a bad range
    assert v.targets and v.style == spec["style"]


def test_motion_presets_exist(spec):
    assert set(spec["live"].get("motion_presets", [])) <= set(PRESETS)


def test_transitions_are_valid_transitions(spec):
    """`live.transitions` maps a name to a `Transition`; `default` is required."""
    transitions = spec["live"].get("transitions")
    if transitions is None:
        return
    assert "default" in transitions
    for name, t in transitions.items():
        Transition(**t)  # refuses an unknown kind or a bad colour


def test_sound_bed_is_a_valid_cue(spec):
    """`live.sound.bed` is a `SoundCue` minus the asset key the user supplies."""
    sound = spec["live"].get("sound")
    if sound is None:
        return
    assert set(sound) <= {"bed"}
    cue = SoundCue(sound="bed", **sound["bed"])
    assert cue.loop  # a bed runs under the whole film


def test_voice_effects_are_valid_voice_effects(spec):
    """`live.voice.effects` is the `effects` of a voice document in the voices
    store (an#163): `normalize_effects` refuses an unknown effect or range."""
    voice = spec["live"].get("voice")
    if voice is None:
        return
    assert set(voice) == {"effects"}
    assert normalize_effects(voice["effects"])  # non-empty: a spec that says nothing omits the key


def test_south_park_raises_its_voices():
    fx = _load(SPEC_DIR / "south_park.yaml")["live"]["voice"]["effects"]
    assert 0 < fx["pitch_semitones"] <= 12


# -----------------------------------------------------------------------------
# The lint's advice agrees with the spec (e2e finding 5)
# -----------------------------------------------------------------------------

#: Advice that would break a spec that SETS step_hz.
_UNSTEP_ADVICE = ("drop `step_hz`", "step_hz: null", "raise `step_hz`", "lower `step_hz`",
                  "higher `step_hz`", "set `step_hz` to")
#: Advice that would break a spec that leaves step_hz UNSET.
_STEP_ADVICE = ("set `step_hz`", "raise `step_hz`", "lower `step_hz`", "higher `step_hz`",
                "`step_hz` to fps")


def test_the_lint_never_advises_against_the_spec(spec):
    """South Park (step_hz 12) was told "drop `step_hz`" for a high held-frame
    share, and OverSimplified (no step_hz) "set `step_hz`" for a low one — both
    break the style they were measuring. Every fix, both directions, every metric."""
    from an.verify.style import METRICS, _fix_for

    live = spec["live"]
    stepped = live["meta"].get("step_hz") is not None
    banned = _UNSTEP_ADVICE if stepped else _STEP_ADVICE
    for name in METRICS:
        for low in (True, False):
            fix = _fix_for(name, low, live)
            hits = [b for b in banned if b in fix]
            assert not hits, (spec["style"], name, "low" if low else "high", fix)
            assert "{" not in fix, fix  # every placeholder filled


# -----------------------------------------------------------------------------
# Guidance must not call a shipped feature missing (e2e finding 1)
# -----------------------------------------------------------------------------

#: A phrase that says a feature is absent, and the shipped thing that makes it
#: false. The e2e agent, following an-style literally, would have told its user
#: the date card and the map arrow were unsupported — while the `an` skill
#: documented text props, path props and plane environments.
STALE_ABSENCE_CLAIMS = {
    r"\bno text (node|layer|primitive|prop)": "text props ship (an#155, an.text.TextDescriptor)",
    r"has no text\b": "text props ship (an#155)",
    r"\bno map layer": "plane environments (an#110) + path props (an#160) build a map",
    r"\bno (path|stroke|line|arrow) (node|primitive|prop|layer)": "path props ship (an#160, an.paths.PathDescriptor)",
    r"\bno (plane|parallax|multiplane) (layer|support)": "plane environments ship (an#110)",
    r"\bno (sound|audio) (layer|support|track)": "shot and meta `sounds` ship (an#176)",
    r"\bno transitions?\b": "shot transitions ship (an#176)",
}

SKILL_MD = SPEC_DIR.parent / "SKILL.md"


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def test_guidance_does_not_call_a_shipped_feature_missing(spec):
    import re

    found = [
        (text, why)
        for text in _strings(spec.get("guidance", {}))
        for pat, why in STALE_ABSENCE_CLAIMS.items()
        if re.search(pat, text.lower())
    ]
    assert not found, found


def test_the_an_style_skill_does_not_call_a_shipped_feature_missing():
    import re

    text = SKILL_MD.read_text(encoding="utf-8").lower()
    found = [why for pat, why in STALE_ABSENCE_CLAIMS.items() if re.search(pat, text)]
    assert not found, found


def test_the_an_style_skill_points_at_its_specs_relative_to_itself():
    """A downstream agent has the skill directory, not the `an` repo: a spec
    path written as `.claude/skills/an-style/styles/...` does not exist there."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert ".claude/skills/an-style/styles" not in text
