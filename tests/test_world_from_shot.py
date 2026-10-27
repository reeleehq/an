"""`an world from-shot` (an#514): a world derived from a shot placed by hand.

The acceptance: run on a two-shot built from the corpus's lamp, the world it
writes lowers back to the master shot's hand placements within the hand
tolerance, and `an validate` reports nothing about it.
"""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import pytest

from an.ir.schema import AssetRef, Meta, Resolution, SceneIR, Shot, StagePlacement
from an.ir.sync import ir_to_markdown
from an.ir.validate import validate_semantic
from an.ir.world import HAND_PLACEMENT_TOLERANCE_PX, HAND_SCALE_TOLERANCE
from an.project import load
from an.stage.world import lower_scene, seed_world
from an.world_cli import from_shot

ROOT = Path(__file__).resolve().parents[1]
LAMP = ROOT / "misc" / "bench" / "corpus" / "prop_swap"
#: The master's hand placements: ``{id: (at, scale)}``.
HAND = {"near": ((-60.0, 80.0), 0.6), "far": ((70.0, 20.0), 0.3)}
PROSE = "The two lamps, placed by hand before the world existed."


def _lamp(eid: str, **kw) -> AssetRef:
    return AssetRef(kind="prop", id=eid, store="props", ref="lamp", **kw)


def _project(tmp_path: Path):
    root = Path(shutil.copytree(LAMP, tmp_path / "p"))
    scene = SceneIR(
        meta=Meta(fps=24, resolution=Resolution(width=320, height=240)),
        timeline=[
            Shot(
                id="master",
                duration=0.5,
                entities=[
                    _lamp(eid, stage=StagePlacement(at=at, scale=scale))
                    for eid, (at, scale) in HAND.items()
                ],
            ),
            # the next shot, placed by hand, continues the near lamp where it was
            Shot(
                id="close",
                duration=0.5,
                entities=[
                    _lamp(
                        "near",
                        stage=StagePlacement(at=HAND["near"][0], scale=HAND["near"][1]),
                    )
                ],
            ),
        ],
    )
    text = ir_to_markdown(scene).replace(
        "## Shot master", f"{PROSE}\n\n## Shot master", 1
    )
    (root / "scene.md").write_text(text, encoding="utf-8")
    shutil.rmtree(root / "ir", ignore_errors=True)
    return load(root)


def test_the_world_lowers_back_to_the_masters_hand_placements(tmp_path):
    project = _project(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from_shot(str(project.root), "master")
    project = load(project.root)
    assert project.scene.timeline[0].viewpoint == "master"
    world = project.scene.world
    assert {m.id for m in world.members} == set(HAND)
    # The world alone (the hand placements dropped) puts them back where they were.
    bare = project.scene.timeline[0].model_copy(
        update={"entities": [_lamp(eid) for eid in HAND]}
    )
    scene = project.scene.model_copy(update={"timeline": [bare]})
    lowered = lower_scene(scene, project.mall).scene.timeline[0]
    for e in lowered.entities:
        at, scale = HAND[e.id]
        assert abs(e.stage.at[0] - at[0]) <= HAND_PLACEMENT_TOLERANCE_PX
        assert abs(e.stage.at[1] - at[1]) <= HAND_PLACEMENT_TOLERANCE_PX
        assert abs(e.stage.scale - scale) <= HAND_SCALE_TOLERANCE
    assert [e.id for e in lowered.entities] == list(HAND), "the listed order is kept"


def test_validate_says_nothing_about_the_seeded_world(tmp_path):
    project = _project(tmp_path)
    from_shot(str(project.root), "master")
    project = load(project.root)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            project.scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )
    loud = [f for f in report.findings if f.severity in ("error", "warning")]
    assert not loud, [f.description for f in loud]


def test_the_scene_files_prose_is_kept_and_a_dry_run_writes_nothing(tmp_path):
    project = _project(tmp_path)
    before = (project.root / "scene.md").read_text(encoding="utf-8")
    out = from_shot(str(project.root), "master", dry_run=True)
    assert "dry run" in out and (project.root / "scene.md").read_text() == before
    from_shot(str(project.root), "master", depth=4.0, focal=400.0)
    text = (project.root / "scene.md").read_text(encoding="utf-8")
    assert PROSE in text and "world" in text
    near = next(m for m in load(project.root).scene.world.members if m.id == "near")
    assert near.at == pytest.approx((-60.0 * 4.0 / 400.0, 80.0 * 4.0 / 400.0, 4.0))


def test_what_cannot_be_inverted_is_refused_or_left_out(tmp_path):
    project = _project(tmp_path)
    empty = project.scene.timeline[1].model_copy(update={"entities": [_lamp("near")]})
    with pytest.raises(ValueError, match="places nothing by hand"):
        seed_world(
            project.scene.model_copy(
                update={"timeline": [project.scene.timeline[0], empty]}
            ),
            project.mall,
            "close",
        )
    with pytest.raises(ValueError, match="no shot 'nope'"):
        seed_world(project.scene, project.mall, "nope")
    scene, _seeded = seed_world(project.scene, project.mall, "master")
    with pytest.raises(ValueError, match="already has a `world`"):
        seed_world(scene, project.mall, "master")
    master = project.scene.timeline[0]

    def with_entities(*entities):
        shot = master.model_copy(update={"entities": list(entities)})
        return project.scene.model_copy(update={"timeline": [shot]})

    # Listed after the members, an unplaced lamp stays on top, placed by hand.
    _, seeded = seed_world(
        with_entities(*master.entities, _lamp("loose")), project.mall, "master"
    )
    assert "stage.at" in seeded.skipped["loose"]
    # Listed before them, it would move on top of them: refused, with the fix.
    with pytest.raises(ValueError, match="'loose' would be left out.*listed before"):
        seed_world(
            with_entities(_lamp("loose"), *master.entities), project.mall, "master"
        )
    # A voice is no member of a picture, and is not reported as left out.
    voice = AssetRef(kind="voice", id="v", store="voices", ref="v")
    _, seeded = seed_world(
        with_entities(voice, *master.entities), project.mall, "master"
    )
    assert "v" not in seeded.skipped


def test_an_asset_that_cannot_be_read_is_left_out_not_a_traceback(tmp_path):
    project = _project(tmp_path)
    broken = _lamp("broken", stage=StagePlacement(at=(0.0, 0.0)))
    broken = broken.model_copy(update={"ref": "no_such_prop"})
    shot = project.scene.timeline[0]
    shot = shot.model_copy(update={"entities": [*shot.entities, broken]})
    scene = project.scene.model_copy(update={"timeline": [shot]})
    _, seeded = seed_world(scene, project.mall, "master")
    assert set(m.id for m in seeded.members) == set(HAND)


def test_a_cut_from_a_framed_to_a_hand_placed_shot_is_still_checked_for_jumps(tmp_path):
    """Seeding frames the master; the next shot is placed by hand. A lamp that
    jumps across that cut is still a jump (an#514 review): only a cut between
    two viewpoints of one world is exempt."""
    project = _project(tmp_path)
    from_shot(str(project.root), "master")
    project = load(project.root)
    close = project.scene.timeline[1]
    jumped = close.model_copy(
        update={
            "entities": [
                _lamp("near", stage=StagePlacement(at=(100.0, -50.0), scale=0.6))
            ]
        }
    )
    scene = project.scene.model_copy(
        update={"timeline": [project.scene.timeline[0], jumped]}
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )
    assert any(
        "'near'" in f.description and "jump" in f.description for f in report.findings
    )
