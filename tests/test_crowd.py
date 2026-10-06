"""Crowds (an#437): many placed copies of one asset, and an action fanned out across them."""

from __future__ import annotations

import pytest

from an.ir.compose import flatten, parallel, sequence, stagger, tween
from an.ir.crowd import CROWD_LAYOUTS, crowd, fan_out
from an.ir.schema import Meta, SceneIR, Shot
from an.ir.validate import validate_semantic

AREA = (-400.0, -50.0, 400.0, 250.0)


@pytest.mark.parametrize("layout", CROWD_LAYOUTS)
@pytest.mark.parametrize("count", [1, 7, 24])
def test_every_member_stands_inside_the_area_back_row_first(layout, count):
    members = crowd(
        "army", ref="soldier", count=count, layout=layout, area=AREA, jitter=0.5
    )
    assert [m.id for m in members] == [f"army_{k}" for k in range(count)]
    assert {(m.kind, m.store, m.ref) for m in members} == {("prop", "props", "soldier")}
    x0, y0, x1, y1 = AREA
    for m in members:
        x, y = m.stage.at
        assert x0 <= x <= x1 and y0 <= y <= y1, (layout, m.stage.at)
    ys = [m.stage.at[1] for m in members]
    if layout == "scatter":
        assert ys == sorted(ys)  # nearer (larger y) members draw over farther ones
    elif layout == "grid" and count > 1:  # rows back first; jitter stays inside a cell
        assert max(ys[:2]) <= min(ys[-2:])


def test_a_crowd_is_deterministic_per_seed():
    a = crowd(
        "s", ref="blob", count=10, layout="scatter", area=AREA, scale_jitter=0.2, seed=1
    )
    b = crowd(
        "s", ref="blob", count=10, layout="scatter", area=AREA, scale_jitter=0.2, seed=1
    )
    c = crowd(
        "s", ref="blob", count=10, layout="scatter", area=AREA, scale_jitter=0.2, seed=2
    )
    assert a == b and a != c
    assert all(0.8 <= m.stage.scale <= 1.2 for m in a)
    assert len({m.stage.scale for m in a}) > 1


def test_a_plain_grid_is_even():
    members = crowd("g", ref="dot", count=4, layout="grid", area=(0, 0, 200, 200))
    assert [m.stage.at for m in members] == [
        (50.0, 50.0),
        (150.0, 50.0),
        (50.0, 150.0),
        (150.0, 150.0),
    ]
    assert {m.stage.scale for m in members} == {1.0}


@pytest.mark.parametrize(
    "kwargs,needle",
    [
        ({"count": 0}, "at least one member"),
        ({"count": 3, "area": (0, 0, 0, 10)}, "x1 > x0"),
        ({"count": 3, "layout": "spiral"}, "unknown crowd layout"),
        ({"count": 3, "jitter": 1.0}, "jitter is a fraction"),
        ({"count": 3, "kind": "nonesuch"}, "no registered store"),
    ],
)
def test_a_crowd_that_cannot_be_placed_is_refused(kwargs, needle):
    with pytest.raises(ValueError, match=needle):
        crowd("x", ref="dot", **kwargs)


def test_fan_out_retargets_every_target_on_the_crowd_and_nothing_else():
    members = crowd("army", ref="soldier", count=3)
    action = sequence(
        tween("army", "y", to=-30.0, duration=0.2),
        parallel(
            tween("army/arm_l", "rotation", to=1.0, duration=0.3),
            tween("flag", "x", to=5.0, duration=0.3),
        ),
    )
    copies = fan_out(action, members)
    assert len(copies) == 3
    flat = [[f.action.target for f in flatten(c)] for c in copies]
    assert flat[1] == ["army_1", "army_1/arm_l", "flag"]
    assert flatten(action)[0].action.target == "army"  # the original is untouched
    # a crowd whose name itself has an underscore: say it
    named = fan_out(
        tween("red_team", "x", to=1.0, duration=0.1),
        ["red_team_0"],
        crowd_id="red_team",
    )
    assert named[0].target == "red_team_0"


def test_stagger_over_fan_out_is_a_ripple_through_the_ranks():
    members = crowd("army", ref="soldier", count=4)
    hop = tween("army", "y", to=-30.0, duration=0.2)
    flat = flatten(stagger(0.1, *fan_out(hop, members)))
    assert [(f.action.target, round(f.start, 3)) for f in flat] == [
        ("army_0", 0.0),
        ("army_1", 0.1),
        ("army_2", 0.2),
        ("army_3", 0.3),
    ]


def test_a_crowd_scene_validates_and_compiles(tmp_path):
    from an.adapters.cutout.compile import compile_shot
    from an.paths import PathDescriptor
    from an.stores import build_project_mall

    mall = build_project_mall(tmp_path, ensure=True)
    mall["props"]["soldier"] = PathDescriptor(
        name="soldier", points=[(0, 0), (0, -40)]
    ).model_dump(mode="json")
    members = crowd(
        "army", ref="soldier", count=12, area=(-300, 0, 300, 200), jitter=0.3, seed=4
    )
    shot = Shot(
        id="march",
        renderer="cutout",
        duration=2.0,
        entities=members,
        actions=[
            stagger(0.05, *fan_out(tween("army", "y", to=-20.0, duration=0.3), members))
        ],
    )
    report = validate_semantic(
        SceneIR(meta=Meta(title="t", duration=2.0), timeline=[shot]),
        available_props=mall["props"],
    )
    assert report.passed, [
        f.description for f in report.findings if f.severity == "error"
    ]
    scene = compile_shot(
        shot, mall=mall, fps=12, width=640, height=360, strict_assets=True
    )
    targets = {ch.target for a in scene.animations.values() for ch in a.channels}
    assert {f"army_{k}" for k in range(12)} <= targets
