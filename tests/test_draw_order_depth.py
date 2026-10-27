"""Draw order against world depth inside a shot (an#510, part (i)): a member that
passes another in depth is painted on the wrong side of it, and the lowering says so.

The cross-shot half (a pair whose painted order flips between shots) is
``tests/test_constraints*.py``'s ``draw_order``.
"""

from __future__ import annotations

import time

from an.ir.compose import parallel, tween
from an.ir.schema import (
    AssetRef,
    Attachment,
    Meta,
    Resolution,
    SceneIR,
    Shot,
    StagePlacement,
    Viewpoint,
    World,
)
from an.ir.world import depth_order_problems, lower_world
from tests.test_world_frames import BOX, EXTENTS, _lamp, _scene


def _notes(scene):
    return [
        n for n in lower_world(scene, extents=EXTENTS).notes if n.kind == "draw_order"
    ]


#: Where `right` stands so that it overlaps `left` on screen (the two lamps
#: of `_scene` stand apart, at -75 and +75 px).
OVERLAPPING = (-0.4, 0.4, 2.0)


def _passing(to_z: float, *, right_at=OVERLAPPING, **shot_kw):
    """`left` and `right` both stand 2 deep, overlapping on screen (unless
    ``right_at`` moves `right`); `left` walks to depth `to_z`."""
    scene = _scene(
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
    if right_at is not None:
        scene.world.members[1] = scene.world.members[1].model_copy(
            update={"at": right_at}
        )
    return scene


def test_a_member_that_passes_a_nearer_one_is_reported_once():
    (note,) = _notes(_passing(0.8))
    assert (note.severity, note.entity, note.shot) == ("warning", "left", "s")
    assert note.message.startswith("painted behind 'right' but nearer the camera")
    assert "stage.after" in note.message


def test_members_that_pass_in_depth_apart_on_screen_are_not_reported():
    assert _notes(_passing(0.8, right_at=None)) == []


def test_a_member_entering_later_behind_is_judged_where_it_first_shows():
    """`left` starts off screen and nearer than `right`, and comes on screen
    farther: it is sorted by its depth where it shows, and that is right."""
    shot = Shot(
        id="s",
        duration=2.0,
        viewpoint="road",
        actions=[
            parallel(
                tween(
                    "left", "at_x", to=-0.5, duration=2.0, from_=-5.0, easing="linear"
                ),
                tween("left", "at_z", to=3.0, duration=2.0, from_=1.0, easing="linear"),
            )
        ],
    )
    scene = _scene(shot)
    scene.world.members[1] = scene.world.members[1].model_copy(
        update={"at": OVERLAPPING}
    )
    assert _notes(scene) == []


def test_a_host_and_its_attached_member_are_not_a_pair():
    scene = _passing(0.8, right_at=(5.0, 0.4, 2.0))  # `right` out of the way
    scene.world.members.append(_lamp("hat", attached=Attachment(to="left")))
    assert _notes(scene) == []


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
    found = [f for f in report.findings if "painted behind" in f.description]
    assert len(found) == 1 and found[0].severity == "warning"
    assert "timeline/0" in found[0].ir_path


def test_the_worlds_of_the_lowering_golden_report_no_draw_order_finding():
    from tests.test_world_frames import _legacy_scenes

    for name, scene in _legacy_scenes().items():
        assert _notes(scene) == [], name


def test_the_check_is_data_sampled_once_per_member_and_cheap():
    """30 members in motion for 10 s at 24 fps: each member's depth is sampled
    once by the lowering, and the check compares the series (an#510)."""
    n, duration = 30, 10.0
    members = [
        _lamp(f"m{i}", at=(-1.5 + 0.1 * i, 0.4, 3.0 + 0.5 * i), height=0.8)
        for i in range(n)
    ]
    actions = [
        tween(f"m{i}", "at_z", to=2.0 + 0.5 * i, duration=duration,
              from_=3.0 + 0.5 * i, easing="linear")
        for i in range(n)
    ]  # fmt: skip
    scene = SceneIR(
        meta=Meta(fps=24, resolution=Resolution(width=320, height=240)),
        world=World(
            members=members,
            viewpoints={"road": Viewpoint(at=(0.0, -1.0, 0.0), focal=300.0)},
        ),
        timeline=[Shot(id="s", duration=duration, viewpoint="road", actions=actions)],
    )
    lower_world(scene, extents={f"m{i}": BOX for i in range(n)})

    times = [duration * k / 240 for k in range(241)]
    painted = [
        AssetRef(kind="prop", id=f"m{i}", store="props", ref="lamp") for i in range(n)
    ]
    depths = {f"m{i}": [10.0 - i * 0.01 - t * 0.1 for t in times] for i in range(n)}
    windows = {k: [(0.0, duration)] for k in depths}
    start = time.perf_counter()
    depth_order_problems(painted, times, depths, windows)
    assert time.perf_counter() - start < 2.0  # generous: ~10 ms on a laptop
