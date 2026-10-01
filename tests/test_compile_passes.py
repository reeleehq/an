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


def test_the_passes_run_in_the_order_the_document_was_always_built_in():
    assert [p.name for p in compile_passes_for_stage()] == [
        "scene", "actions", "swap_pose", "view_spans", "visemes", "face",
        "camera", "parallax", "checks",
    ]


def test_the_cutout_passes_are_the_genres_not_the_stages():
    from an.genres.cutout import CUTOUT, CUTOUT_COMPILE_PASSES

    assert CUTOUT.compile_passes == CUTOUT_COMPILE_PASSES
    assert "rig" in CUTOUT.provides()["compile passes"]
    with without_genres():
        assert [p.name for p in compile_passes_for_stage()] == [
            "scene", "actions", "camera", "parallax", "checks",
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


def test_a_genres_passes_are_inspectable_before_the_stage_loads():
    """`run` may be 'module:function', resolved only when the compiler runs."""
    pending = CompilePass("later", "an.stage.compile:_face_pass", order=500)
    assert pending.resolve().__name__ == "_face_pass"
    with pytest.raises(Exception, match="neither a callable"):
        CompilePass("bad", "not-a-reference").resolve()
    declared = available()
    assert "face" in declared["cutout_animation"].provides()["compile passes"]
