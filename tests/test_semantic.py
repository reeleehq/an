"""The vocabulary registry and the matcher (ADRs 0002, 0003; an#248).

One registry, every entry versioned; methods and aspects whose chains end in a
method that requires nothing; ``resolve`` with requests, policies and
recorded substitutions; the three generated surfaces (the ``an iterate``
prompt, the skill section, the shot's vocabulary digest); and a genre from
another distribution extending all of it without a core edit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from an.capabilities import Capability, Subjects
from an.genres import Genre, GenreError, register_genre, without_genres
from an.semantic import (
    NOOP,
    Aspect,
    Entry,
    Method,
    Policy,
    VocabularyError,
    applicable,
    aspects,
    check_registry,
    entries,
    entry,
    lookup,
    methods_of,
    resolve,
    vocabulary,
    why_not,
)

ROOT = Path(__file__).resolve().parents[1]
LEGS = {"limbs.legs": {"slots": ["leg_l", "leg_r"]}}


# --------------------------------------------------------------------------- the registry


def test_every_registered_aspects_chain_ends_in_a_requirement_free_method_or_the_no_op():
    """ADR 0002 decision 5, as a test over whatever is registered."""
    assert aspects(), "the cut-out genre registers its aspects (conftest loads it)"
    for a in aspects():
        last = a.chain[-1]
        m = NOOP if last == NOOP.id else entry(last)
        assert isinstance(m, Method) and not m.requires, (a.name, last)
    assert check_registry() == []


def test_every_entry_is_versioned_and_ids_are_unique():
    found = entries()
    ids = [e.id for e in found]
    assert len(ids) == len(set(ids))
    assert all(e.version for e in found)
    json.dumps(vocabulary())  # the MCP surface returns it as is


def test_todays_named_vocabularies_are_all_entries():
    """ADR 0003 first slice: motion presets, expression presets, camera moves,
    easings, action kinds, entity kinds — each from the table that defines it."""
    from an.expression.presets import PRESETS as EXPRESSIONS
    from an.genres import action_kind_names, entity_kind_names
    from an.ir.camera import CAMERA_MOVES
    from an.motion import PRESET_VERSIONS, PRESETS
    from an.semantic.seeds import CAMERA_MOVE_VERSIONS
    from an.timing.easing import easing_entries

    def names(kind):
        return {e.term for e in entries(kind=kind)}

    assert names("motion_preset") == set(PRESETS) == set(PRESET_VERSIONS)
    assert names("expression_preset") == set(EXPRESSIONS)
    assert names("camera_move") == set(CAMERA_MOVES) == set(CAMERA_MOVE_VERSIONS)
    assert names("easing") == {e.name for e in easing_entries()}
    assert names("action") == set(action_kind_names())
    assert names("entity") == set(entity_kind_names())


def test_a_motion_presets_entry_describes_its_parameters_with_defaults():
    walk = lookup("motion_preset", "walk")
    props = walk.params["properties"]
    assert props["step_s"] == {"type": "number", "default": 0.4}
    assert not {"target", "rest", "parts"} & set(props)
    assert walk.aspects == ("locomotion",)


def test_a_genres_entries_come_and_go_with_it():
    with without_genres():
        assert lookup("motion_preset", "walk") is None
        assert lookup("action", "play") is None
        assert lookup("action", "tween") is not None  # the core's stay
        assert not aspects()
    assert lookup("motion_preset", "walk") is not None


# --------------------------------------------------------------------------- the matcher


def test_the_locomotion_chain_is_todays_walk_gait_chain():
    """legs when the character affords a leg pair, rock when it does not."""
    assert resolve("locomotion", LEGS).method.id == "loco.legged_cycle"
    assert resolve("locomotion", {}).method.id == "loco.rock"
    assert [m.id for m in applicable("locomotion", {})] == ["loco.rock"]


def test_a_request_by_its_spelling_applies_or_falls_back_with_a_recorded_substitution():
    r = resolve("locomotion", LEGS, requested="hem", entity="robe")
    assert (r.method.id, r.source, r.substitution) == ("loco.hem_sway", "request", None)
    r = resolve("locomotion", {}, requested="hem", entity="blob")
    s = r.substitution
    assert (r.method.id, s.reason, s.requested, s.missing, s.fatal) == (
        "loco.rock",
        "missing",
        "loco.hem_sway",
        ("limbs.legs",),
        True,
    )
    assert "hem" in s.remedies["limbs.legs"]


def test_why_not_gives_the_methods_own_remedy_before_the_capabilitys():
    (gap,) = why_not("loco.legged_cycle", {})
    assert gap.term == "limbs.legs" and "hip" in gap.remedy
    assert why_not("loco.legged_cycle", LEGS) == ()


def test_a_policy_choice_over_an_applicable_chain_is_information_not_a_warning():
    """South Park: the show rocks even when its characters have legs."""
    r = resolve("locomotion", LEGS, policy={"locomotion": ["loco.rock"]})
    assert r.method.id == "loco.rock" and r.source == "policy"
    assert r.substitution.reason == "policy" and not r.substitution.fatal


def test_a_policy_choice_that_does_not_apply_is_a_recorded_substitution():
    r = resolve("locomotion", {}, policy={"locomotion": ["hem", "loco.rock"]})
    assert r.method.id == "loco.rock"
    assert r.substitution.reason == "missing" and r.substitution.requested == "loco.hem_sway"


def test_the_authors_request_outranks_the_policy_and_policies_layer_shot_first():
    r = resolve("locomotion", LEGS, requested="legs", policy={"locomotion": ["loco.rock"]})
    assert r.method.id == "loco.legged_cycle" and r.substitution is None
    layered = Policy.layered({"locomotion": ["hem"]}, {"locomotion": ["rock"], "speech": ["pulse"]})
    assert [c.method for c in layered.choices("locomotion")] == ["hem"]
    assert [c.method for c in layered.choices("speech")] == ["pulse"]


def test_policy_args_reach_the_resolution():
    r = resolve("speech", {}, policy={"speech": [{"method": "pulse", "args": {"strength": 0}}]})
    assert r.method.id == "speech.pose_only" and r.args["strength"] == 0


def test_a_version_pin_that_no_longer_holds_is_an_error_not_a_silent_change():
    with pytest.raises(VocabularyError, match="pinned"):
        resolve("locomotion", LEGS, requested={"method": "loco.legged_cycle", "version": "0"})


def test_an_aspect_that_does_not_apply_to_the_kind_is_a_recorded_no_op():
    """`applies_to` alone decides it: the first link requires nothing, so only
    the kind check can turn it into the no-op (review-256 M15)."""
    a = Aspect("demo_expression", chain=("demo.posture", NOOP.id), applies_to={"character"})
    m = Method("demo.posture", aspect="demo_expression")
    genre = Genre("demo_noop", vocabulary=(m,), aspects=(a,))
    with without_genres():
        register_genre(genre)
        r = resolve("demo_expression", {}, entity="lamp", entity_kind="prop")
        assert r.method is NOOP and r.substitution.reason == "noop" and r.substitution.fatal
        r = resolve("demo_expression", {}, entity="ned", entity_kind="character")
        assert r.method.id == "demo.posture" and r.substitution is None


# --------------------------------------------------------------------------- genres extend it


def test_an_unsound_genre_is_refused_whole_and_leaves_no_trace():
    bad = Genre(
        "demo_bad",
        vocabulary=(Method("demo.legs_only", aspect="demo_walk", requires=("limbs.legs",)),),
        aspects=(Aspect("demo_walk", chain=("demo.legs_only",)),),
    )
    with pytest.raises(GenreError, match="must require\\s+nothing"):
        register_genre(bad)
    assert lookup("method", "demo.legs_only") is None
    with pytest.raises(KeyError):
        resolve("demo_walk", {})


def test_a_requirement_must_name_a_registered_capability():
    bad = Genre(
        "demo_typo",
        vocabulary=(Method("demo.fly", aspect="locomotion", requires=("limbs.wigns",)),),
    )
    with pytest.raises(GenreError, match="limbs.wigns"):
        register_genre(bad)


def test_a_genre_from_another_distribution_adds_methods_capabilities_and_a_policy():
    """P8/P10's question: can `cutan` (another distribution) add a locomotion
    method with its capability and a style policy choosing it — without an
    edit to `an.capabilities` or `an.semantic`? Yes: one Genre object."""
    glide = Method(
        "loco.demo_glide",
        aspect="locomotion",
        name="demo_glide",
        description="carried, no leg action",
        params={"type": "object", "properties": {"bob": {"type": "number", "default": 2.0}}},
    )
    skate = Method(
        "loco.demo_skate", aspect="locomotion", name="demo_skate", requires=("demo.skates",)
    )
    genre = Genre(
        "demo_cutan",
        package="demo-dist",
        capabilities=(Capability("demo.skates", "skates on the feet", "draw skates"),),
        vocabulary=(glide, skate),
    )
    register_genre(genre)
    try:
        assert {"loco.demo_glide"} <= {m.id for m in applicable("locomotion", {})}
        r = resolve("locomotion", LEGS, policy={"locomotion": ["demo_skate", "demo_glide"]})
        assert r.method.id == "loco.demo_glide" and r.args == {"bob": 2.0}
        assert r.substitution.reason == "missing" and r.substitution.missing == ("demo.skates",)
        assert [w.remedy for w in why_not("loco.demo_skate", {})] == ["draw skates"]
    finally:
        from an.genres import _uninstall

        _uninstall("demo_cutan")
    assert lookup("method", "loco.demo_glide") is None


def test_a_second_genre_cannot_register_a_second_chain_for_an_aspect():
    """It adds methods and a policy; the chain is the owning genre's."""
    with pytest.raises(GenreError):
        register_genre(Genre("demo_chain", aspects=(Aspect("locomotion", chain=("loco.rock",)),)))
    assert entry("loco.legged_cycle")
    assert methods_of("locomotion")[0].id == "loco.legged_cycle"


# --------------------------------------------------------------------------- generated surfaces


HAND_WRITTEN = ROOT / "tests" / "fixtures" / "iterate_prompt_handwritten.txt"


def _idents(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z_#][A-Za-z0-9_]*", text))


def test_the_generated_iterate_prompt_covers_the_hand_written_one():
    """Semantic coverage, not bytes (ADR 0003 first slice, item 2), checked before
    the hand-written prompt was deleted: every field named in braces, every
    underscored identifier and every quoted value of the old prompt is in the
    generated one, and so is each of its warnings and rules."""
    from an.iterate import system_prompt

    old, new = HAND_WRITTEN.read_text(encoding="utf-8"), system_prompt()
    taught = _idents(new)
    braces = {w for m in re.findall(r"\{([^{}]*)\}", old) for w in _idents(m)}
    underscored = {w for w in _idents(old) if "_" in w}
    quoted = set(re.findall(r'"([^"\n]+)"', old))
    assert braces - taught == set()
    assert underscored - taught == set()
    assert {q for q in quoted if q not in new} == set()
    flat = " ".join(new.split())
    for phrase in (
        "NOT IMPLEMENTED",
        "never patch them",
        "Never invent a sound key",
        "it has no placeholder rig",
        "face_overlay: false cannot take one",
        "Make the SMALLEST set of patches",
        "Preserve shot ids",
        "affected_shots",
    ):
        assert phrase in flat, phrase


def test_the_generated_prompt_teaches_what_the_hand_written_one_had_dropped():
    from an.iterate import system_prompt

    text = system_prompt()
    for name in ("walk", "turn", "speech_pulse", "loco.legged_cycle", "speech.pose_only"):
        assert name in text, name


def test_the_prompt_lists_only_easings_a_tween_may_name():
    from an.iterate import system_prompt
    from an.semantic.seeds import ir_easing_names

    text = system_prompt()
    after = text.split("Easings (a tween's `easing`):\n", 1)[1]
    section = after.split("\n  M", 1)[0]  # up to the next heading (Methods)
    listed = set(re.findall(r"^    - ([a-z_-]+):", section, re.M))
    assert ir_easing_names() == listed
    assert "smooth" not in listed  # a kernel easing the stage does not draw yet


def test_the_skill_vocabulary_section_is_generated_and_current():
    from an.semantic.docs import current_section, skill_vocabulary_section

    skill = (ROOT / ".claude" / "skills" / "an" / "SKILL.md").read_text(encoding="utf-8")
    assert current_section(skill) == skill_vocabulary_section(), (
        "run: python -m an.semantic.docs --write .claude/skills/an/SKILL.md"
    )


# --------------------------------------------------------------------------- the shot digest


def _shot(**kw):
    from an.ir.schema import AssetRef, Shot

    return Shot(
        id="s",
        entities=[AssetRef(kind="character", id="ned", store="characters", ref="ned")],
        **kw,
    )


def test_the_digest_names_every_entry_a_shot_uses_with_its_version():
    from an.ir.compose import tween
    from an.ir.schema import Camera, PlayAction
    from an.semantic.digest import vocabulary_versions

    from an.ir.compose import loop, parallel, sequence

    shot = _shot(
        camera=Camera(move="push_in"),
        actions=[
            # Nested composites: the digest reaches every leaf (review-256 M14).
            sequence(
                parallel(
                    loop(PlayAction(target="ned", animation="walk", args={"distance": 80}), count=2),
                ),
                tween("ned", "x", to=1.0, duration=1.0, easing="ease_in"),
            ),
        ],
    )
    v = vocabulary_versions(shot)
    for eid in (
        "camera.push_in",
        "motion.walk",
        "action.play",
        "action.tween",
        "easing.ease_in",
        "entity.character",
        "loco.legged_cycle",  # a walk may resolve to any locomotion method
        "loco.rock",
    ):
        assert eid in v, eid


def test_bumping_one_entrys_version_moves_only_the_shots_that_use_it():
    from an.ir.schema import PlayAction
    from an.semantic import register_entry
    from an.semantic.digest import vocabulary_digest

    hopper = _shot(actions=[PlayAction(target="ned", animation="hop")])
    nodder = _shot(actions=[PlayAction(target="ned", animation="nod")])
    before = vocabulary_digest(hopper), vocabulary_digest(nodder)
    hop = lookup("motion_preset", "hop")
    owner = "cutout_animation"
    from dataclasses import replace

    register_entry(replace(hop, version="2"), owner=owner, replace=True)
    try:
        assert vocabulary_digest(hopper) != before[0]
        assert vocabulary_digest(nodder) == before[1]
    finally:
        register_entry(hop, owner=owner, replace=True)
    assert vocabulary_digest(hopper) == before[0]


def test_the_vocabulary_is_a_part_of_the_cut_out_shot_key_and_registering_it_is_idempotent():
    """review-256 S6: called again, or for a renderer with no keyer, it never raises."""
    import an.adapters  # noqa: F401 — registers the cut-out keyer, and the part
    from an.build.keys import shot_keyer_for
    from an.semantic.digest import VOCABULARY_KEY_PART, register_vocabulary_key_part

    assert VOCABULARY_KEY_PART in shot_keyer_for("cutout").parts
    assert register_vocabulary_key_part("cutout") is True
    assert register_vocabulary_key_part("cutout") is True
    assert register_vocabulary_key_part("no-such-renderer") is False


def test_bumping_an_entrys_version_rerenders_the_shots_that_use_it(tmp_path):
    """ADR 0003 decision 2 through P6's seam: the shot key moves with the version."""
    from dataclasses import replace

    from an.ir.schema import PlayAction
    from an.semantic import register_entry
    from tests.test_shot_cache import _ctx, _key

    def shot(animation):
        from an.ir.schema import AssetRef, Shot

        return Shot(
            id="s",
            renderer="cutout",
            duration=1.0,
            entities=[AssetRef(kind="character", id="ned", store="characters", ref="ned")],
            actions=[PlayAction(target="ned", animation=animation)],
        )

    ctx = _ctx(tmp_path)
    hopper, nodder = shot("hop"), shot("nod")
    before = _key(hopper, ctx), _key(nodder, ctx)
    hop = lookup("motion_preset", "hop")
    register_entry(replace(hop, version="2"), owner="cutout_animation", replace=True)
    try:
        assert _key(hopper, ctx) != before[0]  # a miss: the shot re-renders
        assert _key(nodder, ctx) == before[1]  # the other shot is reused
    finally:
        register_entry(hop, owner="cutout_animation", replace=True)
    assert _key(hopper, ctx) == before[0]


def test_entry_validation_refuses_an_unversioned_or_unlevelled_entry():
    with pytest.raises(VocabularyError):
        Entry("x.y", "motion_preset", version="")
    with pytest.raises(VocabularyError):
        Entry("x.y", "motion_preset", levels=())


def test_a_policy_document_round_trips():
    doc = {"locomotion": ["loco.rock", {"method": "speech.pose_only", "args": {"strength": 0}}]}
    assert Policy.of(doc).to_json() == doc
    assert Subjects.of(None).asset == {}


# --------------------------------------------------------------------------- view spaces (an#257)


def test_a_camera_move_is_a_path_through_a_view_space_an_engine_must_lower():
    """Defined once over the framing2d space; the stage engine lowers it, a
    renderer that does not lower framing2d says what is missing."""
    import an.adapters  # noqa: F401 — registers the renderers
    from an.capabilities import missing
    from an.capabilities.subjects import engine_affordances

    push = lookup("camera_move", "push_in")
    assert [str(r) for r in push.requires] == ["space.framing2d"]
    assert push.params["properties"]["path"]["default"] == [
        {"at": 0.0, "zoom": 1.0},
        {"at": 1.0, "zoom": 1.25},
    ]
    assert lookup("view_space", "framing2d").params["properties"]["zoom"]["scale"] == "log"
    assert missing(Subjects(engine=engine_affordances("cutout")), push.requires) == []
    assert missing(Subjects(engine=engine_affordances("manim")), push.requires) == [
        "space.framing2d"
    ]


def test_another_package_declares_a_view_space_and_moves_through_it():
    """previz's orbit camera, or any n-dim space, joins the same camera-move table."""
    from an.semantic.views import ViewField, view_space

    dome = view_space(
        "dome", (ViewField("tilt", "rad", "angle"),), description="a planetarium dome"
    )
    sweep = Entry(
        "camera.dome_sweep",
        "camera_move",
        name="dome_sweep",
        description="sweep the dome",
        requires=(dome.requirement,),
        params={"type": "object", "properties": {"path": {"default": [{"at": 0.0, "tilt": 0.0}, {"at": 1.0, "tilt": 1.0}]}}},
    )
    genre = Genre("demo_dome", capabilities=(dome.capability,), vocabulary=(dome.entry, sweep))
    register_genre(genre)
    try:
        assert lookup("camera_move", "dome_sweep").requires[0].capability == "space.dome"
        assert lookup("view_space", "dome") is dome.entry
    finally:
        from an.genres import _uninstall

        _uninstall("demo_dome")
    assert lookup("camera_move", "dome_sweep") is None


# --------------------------------------------------------------------------- review-256 invariants


def test_resolve_refuses_a_method_of_another_aspect():
    """S3: a typo in a style's policy must not realise one aspect with another's method."""
    with pytest.raises(VocabularyError, match="method of 'speech'"):
        resolve("locomotion", {}, requested="speech.pose_only")
    with pytest.raises(VocabularyError, match="method of 'speech'"):
        resolve("locomotion", {}, policy={"locomotion": ["speech.pose_only"]})


def test_one_name_is_one_entry_and_a_replacement_is_explicit_and_recorded():
    """S5: `push_in` means one thing; burns cannot redefine it by accident."""
    from dataclasses import replace

    from an.semantic import register_entry
    from an.semantic.registry import drop_owner, duplicates, replacements

    push = lookup("camera_move", "push_in")
    with pytest.raises(VocabularyError, match="already"):
        register_entry(replace(push, version="9"), owner="burns")
    with pytest.raises(VocabularyError, match="one name means one thing"):
        register_entry(Entry("burns.push_in", "camera_move", name="push_in"), owner="burns")
    with pytest.raises(VocabularyError, match="one name means one thing"):
        register_entry(Entry("demo.walk", "motion_preset", name="walk"), owner="demo")
    assert duplicates() == [] and check_registry() == []
    register_entry(replace(push, version="9"), owner="burns", replace=True)
    try:
        assert lookup("camera_move", "push_in").version == "9"
        assert replacements()["camera.push_in"] == ("an", "burns", "1")
    finally:
        drop_owner("burns")
    assert lookup("camera_move", "push_in") == push and "camera.push_in" not in replacements()


def test_every_entry_survives_its_json_form():
    """The explicit loader another package (previz) exports entries through."""
    for e in entries():
        if e is NOOP:
            continue
        assert Entry.from_json(e.to_json()) == e, e.id


EXTENSION = Genre(
    "demo_extension",
    vocabulary=(Method("loco.demo_stomp", aspect="locomotion", name="stomp", requires=("limbs.legs",)),),
)


def test_a_genre_needing_another_genres_capability_loads_in_any_order():
    """S7: the capability check runs once every genre is in."""
    from importlib.metadata import EntryPoint

    from an.genres import load

    eps = [
        EntryPoint("demo_extension", "tests.test_semantic:EXTENSION", "an.genres"),
        EntryPoint("cutout_animation", "an.genres.cutout:CUTOUT", "an.genres"),
    ]
    with without_genres():
        assert load(entry_points=eps, builtin=False) == ("demo_extension", "cutout_animation")
        assert lookup("method", "stomp", aspect="locomotion") is not None
    with without_genres():
        with pytest.raises(GenreError, match="limbs.legs"):
            load(entry_points=eps[:1], builtin=False)
