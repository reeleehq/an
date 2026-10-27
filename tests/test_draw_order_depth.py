"""Draw order against world depth inside a shot (an#510, part (i)): a member that
passes another in depth is painted on the wrong side of it, and the lowering says so.

The cross-shot half (a pair whose painted order flips between shots) is
``tests/test_constraints*.py``'s ``draw_order``.
"""

from __future__ import annotations

from an.ir.compose import tween
from an.ir.schema import AssetRef, Shot, StagePlacement
from an.ir.world import lower_world
from tests.test_world_frames import EXTENTS, _scene


def _notes(scene):
    return [
        n for n in lower_world(scene, extents=EXTENTS).notes if n.kind == "draw_order"
    ]


def _passing(to_z: float, **shot_kw):
    """`left` and `right` both stand 2 deep; `left` walks to depth `to_z`."""
    return _scene(
        Shot(
            id="s",
            duration=2.0,
            viewpoint="road",
            actions=[
                tween("left", "at_z", to=to_z, duration=2.0, from_=2.0, easing="linear")
            ],
            **shot_kw,
        )
    )


def test_a_member_that_passes_a_nearer_one_is_reported_once():
    (note,) = _notes(_passing(0.8))
    assert (note.severity, note.entity, note.shot) == ("warning", "left", "s")
    assert "'left' is painted behind 'right' but is nearer the camera" in note.message
    assert "stage.after" in note.message


def test_a_member_walking_away_stays_behind_and_is_not_reported():
    assert _notes(_passing(4.0)) == []


def test_members_at_rest_are_ordered_by_construction_and_not_reported():
    scene = _scene(Shot(id="s", duration=1.0, viewpoint="road"))
    assert _notes(scene) == []


def test_an_after_on_either_member_is_the_authors_word():
    scene = _passing(
        0.8,
        entities=[
            AssetRef(
                kind="prop",
                id="left",
                store="props",
                ref="lamp",
                stage=StagePlacement(after="right"),
            )
        ],
    )
    assert _notes(scene) == []


def test_an_validate_reports_it_with_the_shot(tmp_path):
    import warnings

    from an.ir.validate import validate_semantic
    from tests.test_world_frames import _env_project

    project = _env_project(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            _passing(0.8),
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )
    found = [f for f in report.findings if "is painted behind" in f.description]
    assert len(found) == 1 and found[0].severity == "warning"
    assert "timeline/0" in found[0].ir_path


def test_the_worlds_of_the_lowering_golden_report_no_draw_order_finding():
    from tests.test_world_frames import _legacy_scenes

    for name, scene in _legacy_scenes().items():
        assert _notes(scene) == [], name
