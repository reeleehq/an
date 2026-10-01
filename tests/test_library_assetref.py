"""``AssetRef.library``: additive, optional, omit-when-unset — no stored scene changes.

The field pins the library version an entity was checked out from (ADR 0005
decision 8). It ships without a schema-version bump, which is only honest if
every document written before it serialises exactly as before; these tests
hold that over every scene committed in the repository (the bench corpus and
the examples), in both serialisations a scene has: ``ir/scene.json`` and
``scene.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from an.ir.schema import AssetRef, SceneIR
from an.ir.sync import ir_to_markdown, markdown_to_ir, scene_from_json_doc

ROOT = Path(__file__).resolve().parents[1]
SCENE_MDS = sorted(
    [*ROOT.glob("examples/**/scene.md"), *ROOT.glob("misc/bench/corpus/*/scene.md")]
)
SCENE_JSONS = sorted(
    [
        *ROOT.glob("examples/**/ir/scene.json"),
        *ROOT.glob("misc/bench/corpus/*/ir/scene.json"),
    ]
)


def _ids(paths):
    return [p.relative_to(ROOT).as_posix() for p in paths]


def test_the_corpus_is_found():
    """Guard the guard: an empty glob would make every parametrised case vanish."""
    assert len(SCENE_MDS) >= 10 and len(SCENE_JSONS) >= 1


def _entities(scene: SceneIR) -> list[AssetRef]:
    return [*scene.assets, *(e for shot in scene.timeline for e in shot.entities)]


def _assert_no_trace(scene: SceneIR) -> None:
    dumped = json.loads(scene.model_dump_json())
    refs = [
        *dumped.get("assets", []),
        *(e for s in dumped.get("timeline", []) for e in s.get("entities", [])),
    ]
    assert refs or not _entities(scene)
    assert all("library" not in ref for ref in refs)
    assert "library:" not in ir_to_markdown(scene)


@pytest.mark.parametrize("path", SCENE_MDS, ids=_ids(SCENE_MDS))
def test_every_committed_scene_md_serialises_without_the_field(path):
    _assert_no_trace(markdown_to_ir(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", SCENE_JSONS, ids=_ids(SCENE_JSONS))
def test_every_committed_scene_json_serialises_without_the_field(path):
    _assert_no_trace(scene_from_json_doc(json.loads(path.read_text(encoding="utf-8"))))


@pytest.mark.parametrize("path", SCENE_MDS, ids=_ids(SCENE_MDS))
def test_an_unset_field_and_an_absent_field_dump_byte_identically(path):
    """``library=None`` set explicitly leaves the same bytes as never mentioning it."""
    scene = markdown_to_ir(path.read_text(encoding="utf-8"))
    explicit = scene.model_copy(deep=True)
    for ref in _entities(explicit):
        ref.library = None
    assert explicit.model_dump_json() == scene.model_dump_json()
    assert ir_to_markdown(explicit) == ir_to_markdown(scene)


def test_a_pinned_reference_round_trips_through_json_and_markdown():
    ref = AssetRef(
        kind="character",
        id="alice",
        store="characters",
        ref="alice",
        library="cutan:character.alice-reiniger@v003",
    )
    assert ref.model_dump()["library"] == "cutan:character.alice-reiniger@v003"
    assert AssetRef.model_validate_json(ref.model_dump_json()) == ref
    assert (
        "library"
        not in AssetRef(
            kind="character", id="a", store="characters", ref="a"
        ).model_dump()
    )


@pytest.mark.parametrize(
    "value",
    [
        "character.alice",  # unpinned: a render would follow the head
        "Alice@v001",
        "character.alice@1",
        "../character.alice@v001",
        "character.alice@v001\n",  # a trailing newline must not pass the grammar
    ],
)
def test_the_reference_must_parse_and_be_pinned(value):
    with pytest.raises(ValueError):
        AssetRef(kind="character", id="a", store="characters", ref="a", library=value)


def test_a_content_hash_pins_but_latest_floats_and_is_refused():
    """A scene that said ``@latest`` would render whatever the head is that day."""
    value = "character.alice@sha256:0a1b2c3d4e"
    ref = AssetRef(kind="character", id="a", store="characters", ref="a", library=value)
    assert ref.library == value
    with pytest.raises(ValueError, match="floats"):
        AssetRef(
            kind="character",
            id="a",
            store="characters",
            ref="a",
            library="character.alice@latest",
        )


def test_stage_is_still_omitted_when_unset():
    """The two omissions share one serialiser; neither may undo the other."""
    from an.ir.schema import StagePlacement

    ref = AssetRef(
        kind="character",
        id="a",
        store="characters",
        ref="a",
        library="character.a@v001",
    )
    assert "stage" not in ref.model_dump()
    placed = AssetRef(
        kind="character",
        id="a",
        store="characters",
        ref="a",
        stage=StagePlacement(x=10),
    )
    assert "stage" in placed.model_dump() and "library" not in placed.model_dump()
