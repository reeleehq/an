"""The capability registry (ADR 0002, an#248): grammar, subjects, analysers, substitutions.

The lower layer of P7: what an asset, an engine or the environment affords, the
one matcher, and the substitution record. The cut-out genre's methods and
their compile-time resolution are in ``tests/test_methods_compile.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import an.capabilities as caps
from an.capabilities import (
    FATAL_REASONS,
    CapabilityError,
    Subjects,
    Substitution,
    matches,
    missing,
    parse_requirement,
    register_capability,
    remedy_for,
)
from an.capabilities.subjects import engine_affordances, environment_affordances

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- grammar


@pytest.mark.parametrize(
    "spec", ["limbs.legs", "swap.view:side", "rig.slots>=2", "face.eyes|face.brows"]
)
def test_a_requirement_spells_back_as_written(spec):
    assert str(parse_requirement(spec)) == spec


@pytest.mark.parametrize(
    "spec", ["legs", "face.mouth(chart=rhubarb9)", "rig.slots>=two", "swap.view:", "Limbs.Legs"]
)
def test_anything_outside_the_four_forms_is_refused(spec):
    """No call syntax, no callables: a requirement must name its remedy and diff."""
    with pytest.raises(CapabilityError):
        parse_requirement(spec)


def test_count_reads_the_count_param_else_the_number_of_keys():
    profile = {"rig.slots": {"count": 3}, "swap.view": {"keys": ["front", "side"]}}
    assert matches(profile, "rig.slots>=3") and not matches(profile, "rig.slots>=4")
    assert matches(profile, "swap.view>=2") and not matches(profile, "swap.view>=3")


def test_missing_keeps_the_order_asked_and_spells_each_term():
    assert missing({"limbs.legs": {}}, ["face.mouth", "limbs.legs", "swap.view:back"]) == [
        "face.mouth",
        "swap.view:back",
    ]


def test_a_disjunction_is_met_by_either_side_and_its_remedy_names_both():
    assert matches({"face.brows": {}}, "face.eyes|face.brows")
    assert " — or — " in remedy_for("limbs.legs|limbs.arms")


# --------------------------------------------------------------------------- subjects


def test_each_term_is_matched_against_its_own_subjects_profile():
    """`env.latex` is the environment's, `engine.render` the engine's, `limbs.legs` the asset's."""
    subjects = Subjects(
        asset={"limbs.legs": {}},
        engine={"engine.render": {"keys": ["cutout"]}},
        environment={"env.latex": {}},
    )
    assert missing(subjects, ["limbs.legs", "engine.render:cutout", "env.latex"]) == []
    # The same facts in the WRONG subject do not count.
    wrong = Subjects(asset={"env.latex": {}, "engine.render": {"keys": ["cutout"]}})
    assert missing(wrong, ["env.latex", "engine.render:cutout"]) == [
        "env.latex",
        "engine.render:cutout",
    ]


def test_an_api_keys_value_appears_nowhere_in_the_profile(monkeypatch):
    """M24: presence only — the value never reaches a profile, a facet or a record."""
    secret = "sk-ant-THIS-MUST-NOT-LEAK-0123456789"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    profile = environment_affordances()
    assert "env.key.anthropic" in profile
    assert secret not in repr(profile)


def test_the_environment_analyser_reads_presence_never_values():
    profile = environment_affordances(
        probe={
            "which": {"ffmpeg", "pdflatex"},
            "env": {"ANTHROPIC_API_KEY"},
            "modules": {"playwright"},
            "browsers": True,
        }
    )
    assert profile["env.latex"] == {"keys": ["pdflatex"]}
    assert {"env.ffmpeg", "env.key.anthropic", "env.browser"} <= set(profile)
    assert "env.key.elevenlabs" not in profile
    assert "env.browser" not in environment_affordances(
        probe={"which": set(), "env": set(), "modules": {"playwright"}, "browsers": False}
    )


def test_the_real_environment_probe_spawns_no_process():
    """Cheap probes only: the analyser's module never names `subprocess`, and the
    real probe runs (PATH lookups, variable presence, an import spec)."""
    import an.capabilities.subjects as subjects

    assert "import subprocess" not in Path(subjects.__file__).read_text(encoding="utf-8")
    assert isinstance(environment_affordances(), dict)


def test_the_engine_analyser_derives_from_the_registered_renderers_members():
    import an.adapters  # noqa: F401 — registers the renderers

    # The stage renderer claims its own name and the persisted `cutout` (an#247).
    assert engine_affordances("cutout")["engine.render"] == {"keys": ["cutout", "stage"]}
    assert engine_affordances("manim")["engine.render"] == {"keys": ["manim"]}


# --------------------------------------------------------------------------- registry


def test_the_library_reads_the_same_tables_not_a_copy():
    """Consult trap 1: one derivation. P5's tables moved here and are re-exported."""
    from an.library import affordances as lib

    assert lib.ANALYSERS is caps.ANALYSERS
    assert lib.CAPABILITIES is caps.CAPABILITIES
    assert lib.missing is caps.missing


@pytest.mark.genre("cutout_animation")
def test_the_character_analyser_is_the_cut_out_genres_and_leaves_with_it():
    from an.genres import without_genres
    from cutan.library import CHARACTER_ANALYSER

    assert caps.ANALYSERS["character"] is CHARACTER_ANALYSER
    assert caps.owner_of("limbs.legs") == "cutout_animation"
    with without_genres():
        assert "character" not in caps.ANALYSERS
        assert "limbs.legs" not in caps.CAPABILITIES
        assert "env.ffmpeg" in caps.CAPABILITIES  # the core's own stay
    assert caps.ANALYSERS["character"] is CHARACTER_ANALYSER


@pytest.mark.genre("cutout_animation")
def test_another_owner_cannot_redefine_a_persisted_capability_name():
    with pytest.raises(CapabilityError, match="already registered"):
        register_capability("limbs.legs", description="other", remedy="other", owner="intruder")


def test_importing_the_library_registers_no_analyser():
    """The analyser registers with the genre, never as an import side effect."""
    code = (
        "import an.library, an.capabilities as c; "
        "print(sorted(c.ANALYSERS))"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env, cwd=ROOT
    )
    assert out.stdout.strip() == "['engine', 'environment']"


@pytest.mark.genre("cutout_animation")
def test_the_library_loads_the_genres_before_it_analyses(tmp_path):
    """Consult trap 1's consequence: a library used from a plain script (no
    `an.genres.load()`) still derives a character's facets."""
    code = (
        "import json, sys, pathlib\n"
        "from an.library import open_library, publish\n"
        "from cutan.characters.schema import CharacterDescriptor\n"
        "lib = open_library('an', records={}, versions={}, blobs={})\n"
        "doc = CharacterDescriptor(name='blob').model_dump(mode='json')\n"
        "publish(lib, 'character.blob', doc, source={'provider': 'an-tests', 'license': 'cc0-1.0'})\n"
        "print(sorted(lib.versions['character.blob@v001']['affordances']))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "['swap.view']"


# --------------------------------------------------------------------------- substitutions


def test_which_substitutions_strict_assets_makes_fatal():
    """A policy choice is information; a requested method that does not apply,
    and a recorded no-op, are warnings `--strict-assets` makes fatal."""
    assert FATAL_REASONS == {"missing", "noop"}
    policy = Substitution("locomotion", "ned", "loco.legged_cycle", "loco.rock", "policy")
    assert not policy.fatal and "policy chose" in policy.sentence()
    gone = Substitution("speech", "prop", None, "noop", "noop")
    assert gone.fatal and "no-op" in gone.sentence()
