"""an#245: the default EVALUATOR resolves each target's property space per entity kind.

`an validate` and the compiler already ask `an.genres.entity_space_resolver`
which space a target's properties live in. The evaluator's default did not: it
evaluated every target in `stage.node`, because a compiled document did not say
what its entities are. Now the compiled document records, per entity, the space
its kind declares where that is not the default (`meta.entity_spaces`, omitted
when empty, so no shipped document and no contract hash moves), and
`timeline_from_compiled` carries it into the `Timeline`, so every caller of the
default -- the stage's screen space, the impact ground truth, the bench -- agrees
with validate and compile.
"""

from __future__ import annotations

import pytest

from an.genres import EntityKind, Genre, register_genre, without_genres
from an.ir.schema import AssetRef, Shot
from an.timing.kinds import NumberKind
from an.timing.spaces import FieldDecl, PropertySpace
from an.timing.timeline import evaluate_timeline, timeline_from_compiled

#: A genre whose `dial` entity zooms in LOG space (1 -> 4 is 2 at the midpoint).
DIAL_SPACE = PropertySpace("demo.dial", (FieldDecl("zoom", NumberKind(space="log")),))
DIAL_GENRE = Genre(
    "demo_dial_genre",
    spaces=(DIAL_SPACE,),
    entity_kinds=(EntityKind("dial", space="demo.dial", store="props"),),
)


def _doc(**meta):
    return {
        "meta": meta,
        "timeline": {"duration": 1.0, "tracks": [{"clips": [{"animation_id": "z", "start_time": 0.0}]}]},
        "animations": {
            "z": {
                "duration": 1.0,
                "channels": [
                    {"target": "dial", "property": "zoom",
                     "keyframes": [{"time": 0.0, "value": 1.0}, {"time": 1.0, "value": 4.0}]},
                    {"target": "root", "property": "x",
                     "keyframes": [{"time": 0.0, "value": 1.0}, {"time": 1.0, "value": 4.0}]},
                ],
            }
        },
    }


@pytest.fixture
def dial_genre():
    with without_genres():
        register_genre(DIAL_GENRE)
        yield


def test_the_default_evaluator_uses_the_space_the_document_declares(dial_genre):
    pose = evaluate_timeline(timeline_from_compiled(_doc(entity_spaces={"dial": "demo.dial"})), 0.5)
    assert pose[("dial", "zoom")] == pytest.approx(2.0), "the dial's declared log space"
    assert pose[("root", "x")] == pytest.approx(2.5), "an undeclared target: the default"


def test_a_document_that_declares_nothing_evaluates_as_before(dial_genre):
    """In `stage.node`, `zoom` is undeclared, so discrete: it holds 1 until the key."""
    pose = evaluate_timeline(timeline_from_compiled(_doc()), 0.5)
    assert pose[("dial", "zoom")] == 1.0


def test_an_explicit_space_still_wins_over_the_documents(dial_genre):
    tl = timeline_from_compiled(_doc(entity_spaces={"dial": "demo.dial"}))
    assert evaluate_timeline(tl, 0.5, space="stage.node")[("dial", "zoom")] == 1.0


def test_the_compiler_records_the_spaces_and_only_the_non_default_ones(dial_genre):
    from an.stage.compile import compile_shot
    from an.stage.serialize import to_dict

    shot = Shot(
        id="s",
        renderer="stage",
        duration=1.0,
        entities=[AssetRef(kind="dial", id="dial", store="props", ref="d")],
    )
    doc = to_dict(compile_shot(shot, mall={}, fps=10, width=64, height=48))
    assert doc["meta"]["entity_spaces"] == {"dial": "demo.dial"}
    # ...and the evaluator reads it back from the document the stage ships.
    assert timeline_from_compiled(doc).space("dial/needle").name == "demo.dial"


def test_no_shipped_entity_kind_moves_a_compiled_document():
    """`meta.entity_spaces` is omitted when every entity is in the default
    space -- true of every kind `an` ships, so no contract hash moves."""
    from an.stage.compile import compile_shot
    from an.stage.serialize import to_dict

    import warnings

    shot = Shot(id="s", renderer="cutout", duration=1.0,
                entities=[AssetRef(kind="environment", id="bg", store="environments", ref="park")])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the preset backdrop stands in, and says so
        doc = to_dict(compile_shot(shot, mall={}, fps=10, width=64, height=48))
    assert "entity_spaces" not in doc["meta"]
