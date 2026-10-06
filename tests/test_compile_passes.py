"""The stage compiler as ordered passes, and genres registering theirs (an#247).

`compile_shot` used to be one long function that threaded scene building, the
camera and parallax (the stage's) between the rig, the visemes, the face and the
swap poses (the cut-out genre's). Now the stage runs its own passes plus every
`CompilePass` a genre registers for the ``"stage"`` compiler, in order, and
builds each entity through the builder registered for its kind. The in-repo
cut-out genre registers its passes the way `cutan` will (P8): through
`an.genres`, never by editing the stage.
"""

from __future__ import annotations

import warnings

import pytest

from an.genres import CompilePass, EntityKind, Genre, available, register_genre, without_genres
from an.ir.compose import tween
from an.ir.schema import AssetRef, Shot
from an.stage.compile import compile_passes_for_stage, compile_shot
from an.stage.serialize import NodeJSON, TransformJSON, to_dict


def _quiet_compile(shot, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return to_dict(compile_shot(shot, mall={}, fps=10, width=64, height=48, **kw))


@pytest.mark.genre("cutout_animation")
def test_the_passes_run_in_the_order_the_document_was_always_built_in():
    assert [p.name for p in compile_passes_for_stage()] == [
        # cutan#32: a style's `policy:` block resolves right after the scene
        # an#342: `counters` lowers `value` after every pass that can add one
        "scene", "style_policy", "speech", "counters", "actions", "swap_pose", "view_spans",
        "visemes", "face", "camera", "parallax", "checks",
    ]


@pytest.mark.genre("cutout_animation")
def test_the_cutout_passes_are_the_genres_not_the_stages():
    from cutan.genre import CUTOUT, CUTOUT_COMPILE_PASSES

    assert CUTOUT.compile_passes == CUTOUT_COMPILE_PASSES
    assert "rig" in CUTOUT.provides()["compile passes"]
    with without_genres():
        assert [p.name for p in compile_passes_for_stage()] == [
            "scene", "counters", "actions", "camera", "parallax", "checks",
        ]


def test_a_shot_without_a_character_compiles_the_same_with_or_without_the_genre():
    shot = Shot(
        id="s", renderer="stage", duration=1.0,
        entities=[AssetRef(kind="environment", id="bg", store="environments", ref="park")],
        actions=[tween("root", "x", 10.0, 1.0, from_=0.0)],
    )
    with_genre = _quiet_compile(shot)
    with without_genres():
        without = _quiet_compile(shot)
    assert with_genre == without


def test_a_genre_adds_a_pass_and_an_entity_builder_without_editing_the_stage():
    """What `cutan` (P8) or a math-viz genre does: a new kind drawn by its own
    builder, and a pass of its own between the stage's."""
    seen = []

    def build_dial(entity, build):
        build.children.append(NodeJSON(name=entity.id, transform=TransformJSON(x=5.0)))

    def stamp(state):
        seen.append([p for p in state.animations])

    genre = Genre(
        "demo_dial_genre",
        entity_kinds=(EntityKind("dial", space="stage.node", store="props"),),
        compile_passes=(
            CompilePass("dial", build_dial, order=1, builds="dial"),
            CompilePass("stamp", stamp, order=650),
        ),
    )
    shot = Shot(
        id="s", renderer="stage", duration=1.0,
        entities=[AssetRef(kind="dial", id="dial", store="props", ref="d")],
        actions=[tween("dial", "rotation", 90.0, 1.0, from_=0.0)],
    )
    with without_genres():
        register_genre(genre)
        doc = _quiet_compile(shot)
        assert [p.name for p in compile_passes_for_stage()][-4:] == [
            "camera", "stamp", "parallax", "checks",
        ]
    assert [n["name"] for n in doc["scene"]["children"]] == ["dial"]
    assert seen and seen[0], "the pass ran after the actions, before the parallax"


@pytest.mark.genre("cutout_animation")
def test_a_genres_passes_are_inspectable_before_the_stage_loads():
    """`run` may be 'module:function', resolved only when the compiler runs."""
    pending = CompilePass("later", "cutan.compile.passes:_face_pass", order=500)
    assert pending.resolve().__name__ == "_face_pass"
    with pytest.raises(Exception, match="neither a callable"):
        CompilePass("bad", "not-a-reference").resolve()
    declared = available()
    assert "face" in declared["cutout_animation"].provides()["compile passes"]


# ------------------------------------------------ collisions and generic slots
# (review of an#270, S3 and S4: what P8's `cutan` will lean on)


def _env_shot():
    return Shot(
        id="s", renderer="stage", duration=1.0,
        entities=[AssetRef(kind="environment", id="bg", store="environments", ref="park")],
    )


def test_a_pass_named_like_the_stages_is_refused_unless_it_says_replace():
    from an.stage.compile import CompilePassCollision

    seen = []
    clash = Genre("demo_clash", compile_passes=(CompilePass("camera", lambda s: seen.append(1), order=600),))
    with without_genres():
        register_genre(clash)
        with pytest.raises(CompilePassCollision, match="demo_clash.*'camera'.*replace=True"):
            _quiet_compile(_env_shot())
    assert not seen, "a colliding pass never runs"


def test_an_explicit_replacement_runs_instead_and_is_recorded():
    seen = []
    takeover = Genre(
        "demo_takeover",
        compile_passes=(CompilePass("camera", lambda s: seen.append("mine"), order=600, replace=True),),
    )
    with without_genres():
        register_genre(takeover)
        doc = _quiet_compile(_env_shot())
        assert [p.name for p in compile_passes_for_stage()].count("camera") == 1
    assert seen == ["mine"]
    assert doc["meta"]["extensions"]["replaced_compile_passes"] == {"camera": "demo_takeover"}


def test_a_builder_for_a_kind_the_stage_builds_is_refused_unless_it_says_replace():
    from an.stage.compile import CompilePassCollision, scene_builders

    sneaky = Genre("demo_props", compile_passes=(CompilePass("my_prop", lambda e, b: None, order=1, builds="prop"),))
    with without_genres():
        register_genre(sneaky)
        with pytest.raises(CompilePassCollision, match="builder for 'prop'"):
            scene_builders()


def test_genre_passes_share_products_and_reach_the_document_through_generic_slots():
    def produce(state):
        state.products["demo.count"] = len(state.shot.entities)

    def publish(state):
        state.meta_extensions["demo"] = {"entities": state.products["demo.count"]}

    genre = Genre(
        "demo_slots",
        compile_passes=(CompilePass("produce", produce, order=250), CompilePass("publish", publish, order=650)),
    )
    with without_genres():
        register_genre(genre)
        doc = _quiet_compile(_env_shot())
    assert doc["meta"]["extensions"] == {"demo": {"entities": 1}}
    assert "extensions" not in _quiet_compile(_env_shot())["meta"], "omitted when empty"


def test_a_pass_for_another_compiler_never_runs_on_the_stage_and_ties_break_by_name():
    noop = lambda s: None  # noqa: E731
    genre = Genre(
        "demo_two_compilers",
        compile_passes=(
            CompilePass("elsewhere", noop, order=250, compiler="manim"),
            CompilePass("zz_tie", noop, order=650),
            CompilePass("aa_tie", noop, order=650),
        ),
    )
    with without_genres():
        register_genre(genre)
        names = [p.name for p in compile_passes_for_stage()]
    assert "elsewhere" not in names
    assert names.index("aa_tie") + 1 == names.index("zz_tie")
