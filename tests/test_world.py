"""The scene world (ADR 0009): one world, shots as viewpoints onto it, the
lowering to `stage` placements and stream tweens, and the continuity lints.

The fixture is the `prop_swap` corpus project (a lamp prop), which keeps every
check in the core and browser-free: a member's extent is the compiled
specimen's box, and a lowered shot compiles like any other.
"""

from __future__ import annotations

import json
import re
import shutil
import warnings
from pathlib import Path

import pytest

from an.ir.compose import flatten, parallel
from an.ir.schema import (
    SHOT_SIZES,
    AssetRef,
    Attachment,
    Meta,
    Resolution,
    SceneIR,
    Shot,
    World,
    WorldMember,
    StagePlacement,
    Stream,
    Travel,
    Viewpoint,
)
from an.ir.world import (
    Projection,
    WorldError,
    fit_channel,
    has_world,
    lower_world,
    member_placements,
    resolve_viewpoint,
    stream_instances,
)
from an.ir.sync import ir_to_markdown, markdown_to_ir, merge_markdown
from an.ir.validate import validate_semantic
from an.project import load

ROOT = Path(__file__).resolve().parents[1]
LAMP = ROOT / "misc" / "bench" / "corpus" / "prop_swap"
PLANES = ROOT / "misc" / "bench" / "corpus" / "front_plane"

#: A 20 px tall, 10 px wide art with its placement point at its feet.
BOX = (-5.0, -20.0, 5.0, 0.0)
W, H = 320.0, 240.0


def _lamp(id: str, **world) -> WorldMember:
    return WorldMember(kind="prop", id=id, store="props", ref="lamp", **world)


def _project(tmp_path: Path, corpus: Path = LAMP):
    return load(Path(shutil.copytree(corpus, tmp_path / corpus.name)))


def _validate(project, scene):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return validate_semantic(
            scene,
            available_props=project.mall["props"],
            available_environments=project.mall["environments"],
        )


def _two_lamps_scene(**timeline_kwargs) -> SceneIR:
    """Two lamps side by side two units away, and a viewpoint at the origin."""
    world = World(
        members=[
            _lamp("left", at=(-0.5, 0.4, 2.0), height=0.8),
            _lamp("right", at=(0.5, 0.4, 2.0), height=0.8),
        ],
        viewpoints={
            "two": Viewpoint(at=(0.0, 0.0, 0.0), focal=300.0),
            "right_cu": Viewpoint(subject="right", size="close_up", focal=300.0),
        },
    )
    return SceneIR(
        meta=Meta(fps=24, resolution=Resolution(width=int(W), height=int(H))),
        world=world,
        **timeline_kwargs,
    )


EXTENTS = {"left": BOX, "right": BOX, "hat": BOX, "pole": BOX}


# --- the schema and scene.md --------------------------------------------------


def test_a_scene_without_a_space_dumps_as_before():
    assert "world" not in json.loads(SceneIR().model_dump_json())
    assert "viewpoint" not in json.loads(Shot(id="s").model_dump_json())
    assert not has_world(SceneIR(timeline=[Shot(id="s")]))


def test_scene_md_round_trips_the_space_and_the_viewpoints():
    scene = _two_lamps_scene(
        timeline=[
            Shot(
                id="a",
                duration=1.0,
                viewpoint="two",
                entities=[AssetRef(kind="prop", id="left", store="props", ref="lamp")],
            ),
            Shot(
                id="b",
                duration=1.0,
                viewpoint=Viewpoint(
                    subject=["left", "right"], size="wide", subject_at=(10.0, -5.0)
                ),
            ),
            Shot(id="c", duration=0.5),
        ]
    )
    scene.world.travel = Travel(
        speed=4.0,
        far=30.0,
        streams=[Stream(id="pole", ref="lamp", height=1.5, every=(3.0, 5.0), lane=1.2)],
        plates={"far": ["set/sky"]},
    )
    scene.meta.duration = 2.5  # what the reader fills in from the shots
    md = ir_to_markdown(scene)
    assert "```yaml world" in md and "viewpoint: two" in md
    back = markdown_to_ir(md)
    assert back.world == scene.world
    assert [s.viewpoint for s in back.timeline] == [s.viewpoint for s in scene.timeline]
    assert ir_to_markdown(back) == md


def test_subject_survives_yaml_because_on_would_not():
    """`on:` is a YAML boolean (`on: paul` reads as `True: paul`); the field is `subject`."""
    md = ir_to_markdown(_two_lamps_scene(timeline=[Shot(id="a", viewpoint="right_cu")]))
    assert "subject: right" in md
    assert markdown_to_ir(md).world.viewpoints["right_cu"].subject == "right"


def test_merge_markdown_inserts_the_space_block_after_meta_and_keeps_prose():
    before = _two_lamps_scene(timeline=[Shot(id="a", duration=1.0)])
    before.world = None
    existing = ir_to_markdown(before).replace(
        "## Shot a", "Some prose the author wrote.\n\n## Shot a"
    )
    after = _two_lamps_scene(timeline=[Shot(id="a", duration=1.0)])
    merged = merge_markdown(existing, after)
    assert "Some prose the author wrote." in merged
    assert (
        merged.index("```yaml meta")
        < merged.index("```yaml world")
        < merged.index("## Shot a")
    )
    assert markdown_to_ir(merged).world == after.world


@pytest.mark.parametrize(
    "bad, says",
    [
        (dict(stage=StagePlacement(at=(1.0, 2.0))), "carries `stage`"),
        (dict(), "exactly one of `at:"),
        (dict(at=(0.0, 0.0, 1.0)), "exactly one of `height`"),
        (dict(at=(0.0, 0.0, 1.0), height=1.0, width=1.0), "exactly one of `height`"),
        (dict(attached=Attachment(to="x"), height=1.0), "relative to the host"),
    ],
)
def test_a_member_has_one_way_to_be_placed(bad, says):
    with pytest.raises(ValueError, match=re.escape(says)):
        WorldMember(kind="prop", id="x", store="props", ref="lamp", **bad)


@pytest.mark.parametrize(
    "bad, says",
    [
        (dict(fov=50.0, focal=300.0), "not both"),
        (dict(size="close_up"), "needs `subject"),
        (dict(subject="a", at=(0.0, 0.0, 0.0)), "computes its own position"),
        (dict(subject="a", size="huge"), "unknown shot size"),
        (dict(look_at=(0.0, 0.0, 1.0), look=(10.0, 0.0, 0.0)), "only carry a roll"),
    ],
)
def test_a_viewpoint_has_one_front_door(bad, says):
    with pytest.raises(ValueError, match=says):
        Viewpoint(**bad)


def test_the_space_refuses_duplicates_and_dangling_attachments():
    with pytest.raises(ValueError, match="duplicate ids"):
        World(
            members=[
                _lamp("a", at=(0, 0, 1), height=1),
                _lamp("a", at=(0, 0, 2), height=1),
            ]
        )
    with pytest.raises(ValueError, match="not a member"):
        World(members=[_lamp("a", attached=Attachment(to="ghost"))])
    with pytest.raises(ValueError, match="cycle"):
        World(
            members=[
                _lamp("a", attached=Attachment(to="b")),
                _lamp("b", attached=Attachment(to="a")),
            ]
        )


# --- the geometry --------------------------------------------------------------


def test_size_on_screen_falls_with_depth():
    scene = _two_lamps_scene()
    scene.world.members.append(_lamp("far", at=(0.5, 0.4, 8.0), height=0.8))
    eye = resolve_viewpoint(
        scene.world, "two", extents={**EXTENTS, "far": BOX}, width=W, height=H
    )
    placed = member_placements(
        scene.world, eye, extents={**EXTENTS, "far": BOX}, width=W, height=H
    )
    assert placed["right"].scale == pytest.approx(4 * placed["far"].scale)
    assert placed["right"].at[0] == pytest.approx(4 * placed["far"].at[0])
    # 0.8 units over a 20 px art is 0.04 units per pixel; at depth 2 with focal 300 that is ×6.
    assert placed["right"].scale == pytest.approx(0.04 * 300 / 2)


def test_the_vanishing_point_lands_where_it_says():
    eye = resolve_viewpoint(
        None,
        Viewpoint(at=(0.0, 0.0, 0.0), vanish=(30.0, -80.0), focal=300.0),
        extents={},
        width=W,
        height=H,
    )
    sx, sy, _ = eye.project((0.0, 0.0, 1000.0))
    assert (sx, sy) == pytest.approx((30.0, -80.0), abs=0.05)


def test_a_yawed_viewpoint_is_a_side_window():
    eye = resolve_viewpoint(
        None,
        Viewpoint(at=(0.0, 0.0, 0.0), look=(90.0, 0.0, 0.0), focal=300.0),
        extents={},
        width=W,
        height=H,
    )
    ahead = eye.project(
        (10.0, 0.0, 0.0)
    )  # to the right of the origin: straight ahead now
    assert ahead[:2] == pytest.approx((0.0, 0.0), abs=1e-9) and ahead[
        2
    ] == pytest.approx(10.0)
    assert (
        eye.project((10.0, 0.0, 5.0))[0] < 0
    )  # the road ahead (+z) is on the left of a right-facing window


def test_a_close_up_is_the_same_world_seen_from_nearer():
    """Distances and sizes scale together: the close-up keeps the two-shot's layout."""
    scene = _two_lamps_scene()
    two = member_placements(
        scene.world,
        resolve_viewpoint(scene.world, "two", extents=EXTENTS, width=W, height=H),
        extents=EXTENTS,
        width=W,
        height=H,
    )
    cu = member_placements(
        scene.world,
        resolve_viewpoint(scene.world, "right_cu", extents=EXTENTS, width=W, height=H),
        extents=EXTENTS,
        width=W,
        height=H,
    )
    k = cu["right"].scale / two["right"].scale
    assert k > 1
    assert cu["left"].at[0] - cu["right"].at[0] == pytest.approx(
        k * (two["left"].at[0] - two["right"].at[0])
    )
    # the close-up's band (the top 35 % of the lamp) fills 90 % of the frame, on
    # whichever axis binds first (this lamp is wide for a 4:3 frame: its width)
    top, bottom, fill = SHOT_SIZES["close_up"]
    band_px, width_px = (
        cu["right"].scale * (bottom - top) * 20.0,
        cu["right"].scale * 10.0,
    )
    assert max(band_px / (fill * H), width_px / (fill * W)) == pytest.approx(1.0)
    # and its centre sits at the frame centre
    band_centre_y = cu["right"].at[1] + cu["right"].scale * (
        -20.0 + (top + bottom) / 2 * 20.0
    )
    assert band_centre_y == pytest.approx(0.0)


def test_a_two_shot_fits_both_subjects_in_the_frame():
    scene = _two_lamps_scene()
    vp = Viewpoint(subject=["left", "right"], size="full", focal=300.0)
    placed = member_placements(
        scene.world,
        resolve_viewpoint(scene.world, vp, extents=EXTENTS, width=W, height=H),
        extents=EXTENTS,
        width=W,
        height=H,
    )
    for pid in ("left", "right"):
        x0, y0, x1, y1 = placed[pid].box
        assert -W / 2 <= x0 and x1 <= W / 2 and -H / 2 <= y0 and y1 <= H / 2


# --- the lowering --------------------------------------------------------------


def test_shots_without_a_viewpoint_are_untouched():
    scene = _two_lamps_scene(
        timeline=[
            Shot(
                id="plain",
                entities=[
                    AssetRef(
                        kind="prop",
                        id="lamp",
                        store="props",
                        ref="lamp",
                        stage=StagePlacement(at=(0.0, 90.0)),
                    )
                ],
            )
        ]
    )
    lowered = lower_world(scene, extents=EXTENTS)
    assert lowered.scene.timeline[0] is scene.timeline[0]
    assert lowered.notes == []


def test_the_world_adds_what_the_frame_shows_and_fills_what_is_listed():
    scene = _two_lamps_scene(
        timeline=[
            Shot(
                id="two",
                duration=1.0,
                viewpoint="two",
                entities=[AssetRef(kind="prop", id="left", store="props", ref="lamp")],
            )
        ]
    )
    lowered = lower_world(scene, extents=EXTENTS)
    shot = lowered.scene.timeline[0]
    assert [e.id for e in shot.entities] == ["left", "right"]
    assert shot.entities[0].stage.at == pytest.approx((-75.0, 60.0)) and shot.entities[
        0
    ].stage.scale == pytest.approx(6.0)
    assert shot.entities[1].stage.at == pytest.approx((75.0, 60.0))
    assert [(n.kind, n.entity, n.severity) for n in lowered.notes] == [
        ("added", "right", "info")
    ]


def test_hide_and_the_frame_leave_members_out():
    scene = _two_lamps_scene(
        timeline=[
            Shot(
                id="a",
                viewpoint=Viewpoint(at=(0.0, 0.0, 0.0), focal=300.0, hide=["left"]),
            )
        ]
    )
    scene.world.members.append(_lamp("behind", at=(0.0, 0.0, -1.0), height=0.8))
    scene.world.members.append(_lamp("offside", at=(40.0, 0.0, 2.0), height=0.8))
    lowered = lower_world(scene, extents={**EXTENTS, "behind": BOX, "offside": BOX})
    assert [e.id for e in lowered.scene.timeline[0].entities] == ["right"]


def test_a_hand_placement_wins_and_is_noted():
    by_hand = AssetRef(
        kind="prop",
        id="right",
        store="props",
        ref="lamp",
        stage=StagePlacement(at=(40.0, 0.0), scale=9.0),
    )
    scene = _two_lamps_scene(
        timeline=[Shot(id="two", viewpoint="two", entities=[by_hand])]
    )
    lowered = lower_world(scene, extents=EXTENTS)
    right = next(e for e in lowered.scene.timeline[0].entities if e.id == "right")
    assert right.stage.at == (40.0, 0.0) and right.stage.scale == 9.0
    (hand,) = [n for n in lowered.notes if n.kind == "hand"]
    assert (
        hand.severity == "warning"
        and "(75, 60)" in hand.message
        and "hand placement wins" in hand.message
    )
    # the same placement as the world's says nothing
    agreed = by_hand.model_copy(
        update={"stage": StagePlacement(at=(75.0, 60.0), scale=6.0)}
    )
    scene = _two_lamps_scene(
        timeline=[Shot(id="two", viewpoint="two", entities=[agreed])]
    )
    assert [n.kind for n in lower_world(scene, extents=EXTENTS).notes] == ["added"]


def test_attached_members_follow_the_host():
    scene = _two_lamps_scene(timeline=[Shot(id="two", viewpoint="two")])
    scene.world.members += [
        _lamp("hat", attached=Attachment(to="right", at=(0.0, -20.0), scale=0.5)),
        _lamp("hands", attached=Attachment(to="right")),  # placed by another pass
    ]
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    by_id = {e.id: e for e in shot.entities}
    assert by_id["hat"].stage.at == pytest.approx((75.0, 60.0 - 6.0 * 20.0)) and by_id[
        "hat"
    ].stage.scale == pytest.approx(3.0)
    assert by_id["hands"].stage is None
    # under a hand placement of the host, the attachment follows the hand (as the compiler's passes do)
    by_hand = AssetRef(
        kind="prop",
        id="right",
        store="props",
        ref="lamp",
        stage=StagePlacement(at=(40.0, 0.0), scale=2.0),
    )
    scene.timeline[0] = Shot(id="two", viewpoint="two", entities=[by_hand])
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    hat = next(e for e in shot.entities if e.id == "hat")
    assert hat.stage.at == pytest.approx(
        (40.0, -40.0)
    ) and hat.stage.scale == pytest.approx(1.0)


def test_draw_order_is_depth_with_environments_first_and_the_rest_on_top():
    scene = _two_lamps_scene(
        timeline=[
            Shot(
                id="two",
                viewpoint="two",
                entities=[
                    AssetRef(
                        kind="prop",
                        id="card",
                        store="props",
                        ref="lamp",
                        stage=StagePlacement(at=(0.0, 0.0)),
                    ),
                    AssetRef(
                        kind="environment",
                        id="set",
                        store="environments",
                        ref="default",
                    ),
                ],
            )
        ]
    )
    scene.world.members.insert(0, _lamp("near", at=(0.0, 0.4, 1.0), height=0.8))
    scene.world.members.append(_lamp("far", at=(0.0, 0.4, 9.0), height=0.8))
    shot = lower_world(
        scene, extents={**EXTENTS, "near": BOX, "far": BOX}
    ).scene.timeline[0]
    assert [e.id for e in shot.entities] == [
        "set",
        "far",
        "left",
        "right",
        "near",
        "card",
    ]


def test_an_unknown_viewpoint_or_subject_raises_a_space_error():
    scene = _two_lamps_scene(timeline=[Shot(id="a", viewpoint="nowhere")])
    with pytest.raises(WorldError, match="unknown viewpoint 'nowhere'"):
        lower_world(scene, extents=EXTENTS)
    with pytest.raises(WorldError, match="not a member"):
        resolve_viewpoint(
            scene.world, Viewpoint(subject="nobody"), extents=EXTENTS, width=W, height=H
        )
    with pytest.raises(WorldError, match="cannot be measured"):
        resolve_viewpoint(
            scene.world, "right_cu", extents={"right": None}, width=W, height=H
        )


# --- the travelling view ---------------------------------------------------------


def _travel_scene(*shots: Shot, yaw: float = 0.0) -> SceneIR:
    scene = _two_lamps_scene(timeline=list(shots))
    scene.world.viewpoints["road"] = Viewpoint(
        at=(0.0, -1.0, 0.0), look=(yaw, 0.0, 0.0), focal=300.0
    )
    scene.world.travel = Travel(
        speed=4.0,
        far=30.0,
        near=0.5,
        streams=[Stream(id="pole", ref="lamp", height=1.5, every=3.0, lane=1.2, y=0.0)],
    )
    return scene


def _channel(
    shot: Shot, entity: str, prop: str
) -> list[tuple[float, float, float | None, float]]:
    """``(start, end, from, to)`` of every tween of one channel, in time order."""
    out = []
    for f in flatten(parallel(*shot.actions)):
        a = f.action
        if (
            getattr(a, "kind", "") == "tween"
            and a.target == entity
            and a.property == prop
        ):
            out.append((f.start, f.start + a.duration, a.from_value, a.to_value))
    return sorted(out)


def test_stream_instances_are_positioned_once_in_the_world():
    stream = Stream(
        id="pole", ref="lamp", height=1.5, every=(2.0, 4.0), lane=(1.0, 2.0), seed=3
    )
    a = stream_instances(stream, Travel(speed=1.0), s_min=0.0, s_max=40.0)
    b = stream_instances(stream, Travel(speed=1.0), s_min=10.0, s_max=25.0)
    assert (
        dict(b).items() <= dict(a).items()
    )  # a narrower window is a subset, instance for instance
    spacings = [q[1][2] - p[1][2] for p, q in zip(a, a[1:])]
    assert all(2.0 - 1e-9 <= d <= 4.0 + 1e-9 for d in spacings)
    assert all(1.0 <= p[1][0] <= 2.0 for p in a)


def test_streams_keep_phase_across_the_cut():
    scene = _travel_scene(
        Shot(id="s1", duration=2.0, viewpoint="road"),
        Shot(id="s2", duration=2.0, viewpoint="road"),
    )
    lowered = lower_world(scene, extents=EXTENTS)
    s1, s2 = lowered.scene.timeline
    common = sorted(
        {e.id for e in s1.entities} & {e.id for e in s2.entities} - {"left", "right"}
    )
    assert common, "an instance on screen at the cut is in both shots"
    for eid in common:
        ends = _channel(s1, eid, "x")
        starts = _channel(s2, eid, "x")
        if (
            ends
            and starts
            and ends[-1][1] == pytest.approx(2.0)
            and starts[0][0] == 0.0
        ):
            assert starts[0][2] == pytest.approx(ends[-1][3], abs=1e-6)


def test_a_side_window_scrolls_in_one_linear_stretch():
    scene = _travel_scene(Shot(id="s1", duration=2.0, viewpoint="road"), yaw=90.0)
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    poles = [e.id for e in shot.entities if e.id.startswith("pole_")]
    assert poles
    for eid in poles:
        xs = _channel(shot, eid, "x")
        assert len(xs) == 1, "constant depth: one tween, no bend"
        assert _channel(shot, eid, "scale_x") == []  # size does not change


def test_the_fit_tracks_the_projection_within_tolerance():
    segs = fit_channel(
        lambda t: 300.0 / (10.0 - 4.0 * t), 0.0, 2.0, tolerance=0.5, min_step=1 / 24
    )
    assert 2 <= len(segs) <= 10
    from an.timing.easing import apply_easing

    for t0, t1, v0, v1, easing in segs:
        for u in (0.1, 0.3, 0.5, 0.7, 0.9):
            t = t0 + u * (t1 - t0)
            assert v0 + (v1 - v0) * apply_easing(easing, u) == pytest.approx(
                300.0 / (10.0 - 4.0 * t), abs=0.5
            )


def test_a_lowered_travelling_shot_compiles_and_moves_as_the_world_says(tmp_path):
    from an.ir.world import _mul, _unit
    from an.stage.compile import compile_shot
    from an.stage.timeline import screen_position, timeline_from_scene
    from an.timing import evaluate_timeline

    project = _project(tmp_path)
    scene = _travel_scene(Shot(id="s1", duration=2.0, viewpoint="road"))
    lowered = lower_world(scene, extents=EXTENTS)
    shot = lowered.scene.timeline[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = compile_shot(shot, mall=project.mall, width=int(W), height=int(H), fps=24)
    timeline = timeline_from_scene(doc)
    eye = resolve_viewpoint(scene.world, "road", extents=EXTENTS, width=W, height=H)
    instances = dict(
        stream_instances(
            scene.world.travel.streams[0], scene.world.travel, s_min=-100.0, s_max=100.0
        )
    )
    checked = 0
    for entity in shot.entities:
        if not entity.id.startswith("pole_"):
            continue
        world = instances[int(entity.id.split("_")[1])]
        for i in range(0, 25):
            t = i / 12
            pose = evaluate_timeline(timeline, t)
            if pose.get((entity.id, "alpha"), 1.0) == 0.0:
                continue
            exact = eye.moved(_mul(_unit((0.0, 0.0, 1.0)), 4.0 * t)).project(world)
            if exact is None or abs(exact[0]) > W / 2 or abs(exact[1]) > H / 2:
                continue
            sx, sy = screen_position(doc, entity.id, pose=pose)
            # exact (an#629): one projective tween per channel
            assert (sx - W / 2, sy - H / 2) == pytest.approx(exact[:2], abs=1e-6)
            checked += 1
    assert checked > 20


# --- validate ---------------------------------------------------------------------


def test_validate_reports_the_lowering_and_resolves_actions_on_added_members(tmp_path):
    project = _project(tmp_path)
    scene = _two_lamps_scene(
        timeline=[
            Shot(
                id="two",
                duration=1.0,
                viewpoint="two",
                actions=[
                    {
                        "kind": "set",
                        "target": "right",
                        "property": "alpha",
                        "value": 0.5,
                        "at": 0.2,
                    }
                ],
            )
        ]
    )
    report = _validate(project, scene)
    descriptions = [f.description for f in report.findings]
    assert any("the world adds it" in d and "'left'" in d for d in descriptions)
    assert not any(
        "unknown" in d.lower() and "target" in d.lower() for d in descriptions
    )
    assert not any(f.severity == "error" for f in report.findings), descriptions


def test_validate_names_an_unknown_viewpoint_and_subject(tmp_path):
    project = _project(tmp_path)
    scene = _two_lamps_scene(timeline=[Shot(id="a", viewpoint="nowhere")])
    scene.world.viewpoints["bad"] = Viewpoint(subject="nobody", hide=["ghost"])
    report = _validate(project, scene)
    errors = [
        (f.ir_path, f.description) for f in report.findings if f.severity == "error"
    ]
    assert any(path == "world" and "nowhere" in d for path, d in errors)
    assert any(path == "world/viewpoints/bad" and "nobody" in d for path, d in errors)
    assert any(path == "world/viewpoints/bad" and "ghost" in d for path, d in errors)


def test_cut_continuity_is_silent_across_two_viewpoints_and_loud_within_one(tmp_path):
    project = _project(tmp_path)
    scene = _two_lamps_scene(
        timeline=[
            Shot(id="two", duration=0.5, viewpoint="two"),
            Shot(id="cu", duration=0.5, viewpoint="right_cu"),
        ]
    )
    jumps = [
        f
        for f in _validate(project, scene).findings
        if "jumps across the cut" in f.description
    ]
    assert jumps == []
    by_hand = AssetRef(
        kind="prop",
        id="right",
        store="props",
        ref="lamp",
        stage=StagePlacement(at=(40.0, 0.0), scale=9.0),
    )
    scene = _two_lamps_scene(
        timeline=[
            Shot(id="two", duration=0.5, viewpoint="two"),
            Shot(id="again", duration=0.5, viewpoint="two", entities=[by_hand]),
        ]
    )
    jumps = [
        f
        for f in _validate(project, scene).findings
        if "jumps across the cut" in f.description
    ]
    assert jumps and "'right'" in jumps[0].description


def test_crossing_the_line_is_a_warning(tmp_path):
    project = _project(tmp_path)

    def shot(id, a_x, b_x):
        return Shot(
            id=id,
            duration=0.5,
            entities=[
                AssetRef(
                    kind="prop",
                    id="a",
                    store="props",
                    ref="lamp",
                    stage=StagePlacement(at=(a_x, 0.0), scale=0.3),
                ),
                AssetRef(
                    kind="prop",
                    id="b",
                    store="props",
                    ref="lamp",
                    stage=StagePlacement(at=(b_x, 0.0), scale=0.3),
                ),
            ],
        )

    scene = project.scene.model_copy(
        update={"timeline": [shot("s1", -50.0, 50.0), shot("s2", 60.0, -60.0)]}
    )
    flips = [
        f for f in _validate(project, scene).findings if "swap sides" in f.description
    ]
    assert (
        len(flips) == 1
        and "180°" in flips[0].description
        and "'a'" in flips[0].description
    )
    scene = project.scene.model_copy(
        update={"timeline": [shot("s1", -50.0, 50.0), shot("s2", -90.0, 10.0)]}
    )
    assert [
        f for f in _validate(project, scene).findings if "swap sides" in f.description
    ] == []


def test_plates_under_a_travel_must_be_declared(tmp_path):
    root = Path(shutil.copytree(LAMP, tmp_path / "p"))
    shutil.copytree(
        PLANES / "assets" / "environments" / "stage",
        root / "assets" / "environments" / "stage",
    )
    project = load(root)
    env = AssetRef(kind="environment", id="set", store="environments", ref="stage")
    scene = _travel_scene(Shot(id="s1", duration=0.5, viewpoint="road", entities=[env]))
    scene.meta = project.scene.meta
    report = _validate(project, scene)
    undeclared = [
        f.description
        for f in report.findings
        if "does not say what it holds" in f.description
    ]
    assert any("'set/sky'" in d for d in undeclared) and any(
        "'set/hill'" in d for d in undeclared
    )
    scene.world.travel.plates = {
        "far": ["set/sky"],
        "vehicle": ["set/hill", "set/rail"],
    }
    report = _validate(project, scene)
    assert [
        f for f in report.findings if "does not say what it holds" in f.description
    ] == []
    pinned = [
        f.description
        for f in report.findings
        if "a far plate is pinned" in f.description
    ]
    assert any("'set/sky'" in d for d in pinned), (
        "sky is declared far but its parallax factor is 1"
    )


# --- the entry points and the CLI ----------------------------------------------------


def test_every_entry_point_lowers_the_scene_before_compiling():
    """`an render` (and `an probe`, which prepares shots through it), `an preview`
    and the orchestrator compile the LOWERED scene, and nothing writes it back."""
    for module, fn in (
        ("an/render.py", "_prepare_shots"),
        ("an/stage/preview.py", "preview_project"),
        ("an/orchestrate.py", "_strict_asset_findings"),
    ):
        src = (ROOT / module).read_text(encoding="utf-8")
        body = src[src.index(f"def {fn}(") :]
        assert "lower_scene(" in body, f"{module}::{fn} must compile the lowered scene"
    assert "lower_scene" not in (ROOT / "an" / "ir" / "sync.py").read_text(
        encoding="utf-8"
    )


def test_an_space_show_prints_the_lowered_shots(tmp_path, capsys):
    from an.world_cli import show

    project = _project(tmp_path)
    scene = _two_lamps_scene(
        timeline=[
            Shot(id="two", duration=1.0, viewpoint="two"),
            Shot(id="plain", duration=0.5),
        ]
    )
    scene.meta = project.scene.meta
    (project.root / "scene.md").write_text(ir_to_markdown(scene), encoding="utf-8")
    shutil.rmtree(project.root / "ir")
    text = show(str(project.root))
    assert "## two" in text and "## plain" not in text
    assert "the world adds it" in text and "left" in text and "right" in text
    as_json = json.loads(show(str(project.root), json=True))
    assert [row["shot"] for row in as_json] == ["two"]


# --- what the adversarial review found (ADR 0009 review, 2026-10-21) ----------------


def test_a_member_whose_art_cannot_compile_is_a_finding_not_a_traceback(tmp_path):
    """B1: a missing ref, an unregistered kind or no stores at all: validate reports."""
    project = _project(tmp_path)
    scene = _two_lamps_scene(timeline=[Shot(id="two", duration=0.5, viewpoint="two")])
    scene.world.members.append(
        _lamp("ghost", at=(0.0, 0.4, 2.0), height=0.8).model_copy(
            update={"ref": "no_such_prop"}
        )
    )
    report = _validate(project, scene)
    said = [
        f for f in report.findings
        if "'ghost'" in f.description or "no_such_prop" in f.description
    ]  # fmt: skip
    # an#516: said once, as the member's error (not again per shot)
    assert [(f.severity, f.ir_path) for f in said] == [("error", "world/members/2")]
    assert not any("Traceback" in f.description for f in said)
    # no stores at all: the lowering cannot measure, and still does not raise
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bare = validate_semantic(scene)
    assert any("'left'" in f.description for f in bare.findings)
    # an unknown kind is the world check's finding, and the lowering survives it
    scene.world.members.append(
        WorldMember(
            kind="alien",
            id="zed",
            store="props",
            ref="lamp",
            at=(0.0, 0.0, 2.0),
            height=1.0,
        )
    )
    report = _validate(project, scene)
    assert any(
        f.ir_path.startswith("world/members/") and "alien" in f.description
        for f in report.findings
    )
    from an.world_cli import show

    (project.root / "scene.md").write_text(ir_to_markdown(scene), encoding="utf-8")
    shutil.rmtree(project.root / "ir")
    assert "## two" in show(str(project.root))


def test_a_travel_reuses_entities_and_refuses_past_its_budget():
    """B2: entities are slots bounded by the depth range, not by the shot's length; a
    lowering past `max_actions` is refused with the knobs named."""
    from an.ir.world import stream_slots

    scene = _travel_scene(Shot(id="long", duration=40.0, viewpoint="road"))
    stream, travel = scene.world.travel.streams[0], scene.world.travel
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    poles = [e for e in shot.entities if e.id.startswith("pole_")]
    assert 0 < len(poles) <= stream_slots(stream, travel) == 11
    passes = sum(
        1
        for f in flatten(parallel(*shot.actions))
        if getattr(f.action, "property", "") == "alpha" and f.action.value == 1.0
    )
    assert passes > len(poles), "a slot draws several instances one after another"
    scene.world.travel = travel.model_copy(update={"max_actions": 50})
    with pytest.raises(WorldError, match="max_actions"):
        lower_world(scene, extents=EXTENTS)


def test_lowering_is_idempotent():
    """S1: a lowered scene lowered again gains no entity and no action."""
    scene = _travel_scene(Shot(id="s1", duration=2.0, viewpoint="road"))
    once = lower_world(scene, extents=EXTENTS).scene
    twice = lower_world(once, extents=EXTENTS).scene
    assert [e.id for e in twice.timeline[0].entities] == [
        e.id for e in once.timeline[0].entities
    ]
    assert len(twice.timeline[0].actions) == len(once.timeline[0].actions)


def test_the_listing_wins_over_hide_and_says_so():
    """S2: a member the viewpoint hides but the shot lists stays, with a note."""
    scene = _two_lamps_scene(
        timeline=[
            Shot(
                id="a",
                viewpoint=Viewpoint(at=(0.0, 0.0, 0.0), focal=300.0, hide=["left"]),
                entities=[AssetRef(kind="prop", id="left", store="props", ref="lamp")],
            )
        ]
    )
    lowered = lower_world(scene, extents=EXTENTS)
    assert [e.id for e in lowered.scene.timeline[0].entities] == ["left", "right"]
    assert any(
        n.kind == "listed" and n.entity == "left" and "listing wins" in n.message
        for n in lowered.notes
    )


def test_a_hand_at_keeps_the_worlds_scale_unless_a_scale_is_set():
    """S3: `stage: {at: [...]}` nudges a member; its size stays the world's (the
    default scale 1.0 means the world's), and what is attached to it follows."""
    scene = _two_lamps_scene(
        timeline=[
            Shot(
                id="two",
                viewpoint="two",
                entities=[
                    AssetRef(
                        kind="prop",
                        id="right",
                        store="props",
                        ref="lamp",
                        stage=StagePlacement(at=(76.0, 60.0)),
                    )
                ],
            )
        ]
    )
    scene.world.members.append(
        _lamp("hat", attached=Attachment(to="right", at=(0.0, -20.0), scale=0.5))
    )
    lowered = lower_world(scene, extents=EXTENTS)
    by_id = {e.id: e for e in lowered.scene.timeline[0].entities}
    assert by_id["right"].stage.at == (76.0, 60.0) and by_id[
        "right"
    ].stage.scale == pytest.approx(6.0)
    assert by_id["hat"].stage.at == pytest.approx((76.0, 60.0 - 6.0 * 20.0)) and by_id[
        "hat"
    ].stage.scale == pytest.approx(3.0)
    # a nudge of a pixel is within tolerance: no hand note
    assert not any(n.kind == "hand" for n in lowered.notes)


def test_a_composition_over_two_depths_frames_both():
    """S4: the camera stands back far enough for the NEAREST subject."""
    scene = _two_lamps_scene()
    scene.world.members.append(_lamp("close", at=(0.0, 0.4, 0.5), height=0.8))
    vp = Viewpoint(subject=["close", "right"], size="full", focal=300.0)
    eye = resolve_viewpoint(
        scene.world, vp, extents={**EXTENTS, "close": BOX}, width=W, height=H
    )
    placed = member_placements(
        scene.world, eye, extents={**EXTENTS, "close": BOX}, width=W, height=H
    )
    assert placed["close"].in_frame and placed["right"].in_frame
    assert placed["close"].depth > 0 and placed["right"].depth > placed["close"].depth


def test_an_added_attached_member_carries_its_attachment():
    """S5: a pass that places a body prop from its host finds the host on the entity."""
    from an.ir.world import ATTACHED_OVERRIDE

    scene = _two_lamps_scene(timeline=[Shot(id="two", viewpoint="two")])
    scene.world.members.append(_lamp("hands", attached=Attachment(to="right")))
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    hands = next(e for e in shot.entities if e.id == "hands")
    assert hands.stage is None and hands.overrides[ATTACHED_OVERRIDE] == {"to": "right"}


def test_findings_on_a_framed_shot_name_the_authors_entities(tmp_path):
    """S8: a finding's `entities/<j>` is the author's index, or `~<id>` for one the
    world added, never the lowered list's index."""
    project = _project(tmp_path)
    # `right` is listed first by the author but drawn after `left`... both at one depth,
    # so the lowered order is the listed order; an added member comes with `~`.
    scene = _two_lamps_scene(
        timeline=[
            Shot(
                id="two",
                duration=0.5,
                viewpoint="two",
                entities=[
                    AssetRef(
                        kind="prop",
                        id="right",
                        store="props",
                        ref="lamp",
                        stage=StagePlacement(after="nobody"),
                    )
                ],
            )
        ]
    )
    report = _validate(project, scene)
    after = [f for f in report.findings if "nobody" in f.description]
    assert after and after[0].ir_path.startswith("timeline/0/entities/0")
    scene.world.members.append(
        _lamp("ghost", at=(0.0, 0.4, 2.0), height=0.8).model_copy(
            update={"ref": "no_such_prop", "units_per_px": 0.04, "height": None}
        )
    )
    report = _validate(project, scene)
    ghost = [
        f for f in report.findings if f.ir_path.startswith("timeline/0/entities/~ghost")
    ]
    assert ghost, [f.ir_path + " " + f.description[:60] for f in report.findings]


def test_short_film_starts_are_refused():
    scene = _two_lamps_scene(
        timeline=[Shot(id="a", viewpoint="two"), Shot(id="b", viewpoint="two")]
    )
    with pytest.raises(WorldError, match="film_starts"):
        lower_world(scene, extents=EXTENTS, film_starts=[0.0])


def test_a_world_block_inside_a_shot_is_refused():
    from an.ir.sync import SceneMarkdownError

    md = ir_to_markdown(_two_lamps_scene(timeline=[Shot(id="a", duration=1.0)]))
    head, _, tail = md.partition("## Shot a")
    moved = (
        head.replace("```yaml world", "```yaml notworld")
        + "## Shot a"
        + tail
        + "\n```yaml world\nmembers: []\n```\n"
    )
    with pytest.raises(SceneMarkdownError, match="before the first shot"):
        markdown_to_ir(moved)


def test_a_wide_lens_side_window_gets_the_slots_its_view_needs():
    """Review B3 (an#516): a wide lens on a side window shows more of the row
    than the depth range; the slots are sized from the on-screen span, so it
    lowers (the lowering still asserts no slot holds two passes at once)."""
    from an.ir.world import stream_slots

    scene = _travel_scene(Shot(id="s1", duration=6.0, viewpoint="road"), yaw=90.0)
    scene.world.viewpoints["road"] = Viewpoint(
        at=(0.0, -1.0, 0.0), look=(90.0, 0.0, 0.0), fov=120.0
    )
    scene.world.travel = scene.world.travel.model_copy(
        update={
            "far": 30.0,
            "streams": [
                Stream(id="pole", ref="lamp", height=6.0, every=2.0, lane=20.0, y=0.0)
            ],
        }
    )
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    slots = {e.id for e in shot.entities if e.id.startswith("pole_")}
    depth_count = stream_slots(scene.world.travel.streams[0], scene.world.travel)
    assert len(slots) > depth_count, (len(slots), depth_count)


# --- ground-plane perspective on hand placements (catalogue A6) ----------------


def _handed(at, scale=1.0):
    return AssetRef(
        kind="prop",
        id="right",
        store="props",
        ref="lamp",
        stage=StagePlacement(at=at, scale=scale),
    )


def _perspective(scene):
    return [
        n for n in lower_world(scene, extents=EXTENTS).notes if n.kind == "perspective"
    ]


def test_a_world_placement_is_in_perspective():
    scene = _two_lamps_scene(
        timeline=[
            Shot(id="two", viewpoint="two", entities=[_handed((75.0, 60.0), 6.0)])
        ]
    )
    assert _perspective(scene) == []


def test_walking_a_member_nearer_by_hand_without_resizing_it_is_a_warning():
    scene = _two_lamps_scene(
        timeline=[
            Shot(id="two", viewpoint="two", entities=[_handed((75.0, 120.0), 6.0)])
        ]
    )
    (note,) = _perspective(scene)
    assert note.severity == "warning" and note.entity == "right"
    assert "scale 12" in note.message  # twice as far below the horizon: twice the size


def test_a_hand_scale_that_follows_the_row_is_clean():
    scene = _two_lamps_scene(
        timeline=[
            Shot(id="two", viewpoint="two", entities=[_handed((75.0, 120.0), 12.0)])
        ]
    )
    assert _perspective(scene) == []


# --- an#516: the review's second pass, slice A ---------------------------------


def test_a_lowered_shot_is_known_by_its_marker_not_by_its_names():
    """Slot entities carry `overrides.stream`; a lowered scene lowered again is
    recognised by it (with an info note), and an AUTHORED entity merely named
    like a slot is refused instead of silently un-lowering the shot."""
    from an.ir.world import STREAM_OVERRIDE

    scene = _travel_scene(Shot(id="s1", duration=2.0, viewpoint="road"))
    once = lower_world(scene, extents=EXTENTS)
    slots = [e for e in once.scene.timeline[0].entities if e.id.startswith("pole_")]
    assert slots and all(e.overrides[STREAM_OVERRIDE] == "pole" for e in slots)
    twice = lower_world(once.scene, extents=EXTENTS)
    assert any(n.kind == "lowered" and n.severity == "info" for n in twice.notes)
    impostor = AssetRef(kind="prop", id="pole_0", store="props", ref="lamp")
    named = _travel_scene(
        Shot(id="s1", duration=2.0, viewpoint="road", entities=[impostor])
    )
    with pytest.raises(WorldError, match="named like a stream's slots"):
        lower_world(named, extents=EXTENTS)


def test_cut_continuity_and_screen_direction_skip_an_entity_unseen_on_a_side(tmp_path):
    """A hidden entity (alpha 0) at a cut does not jump: S11."""
    from an.ir.schema import SetAction

    project = _project(tmp_path)
    by_hand = AssetRef(
        kind="prop", id="right", store="props", ref="lamp",
        stage=StagePlacement(at=(40.0, 0.0), scale=9.0),
    )  # fmt: skip

    def jumps(*end_actions):
        scene = _two_lamps_scene(
            timeline=[
                Shot(
                    id="two", duration=0.5, viewpoint="two", actions=list(end_actions)
                ),
                Shot(id="again", duration=0.5, viewpoint="two", entities=[by_hand]),
            ]
        )
        return [
            f
            for f in _validate(project, scene).findings
            if "jumps across the cut" in f.description and "'right'" in f.description
        ]

    assert jumps(), "seen on both sides: the jump is reported"
    hidden = SetAction(target="right", property="alpha", value=0.0, at=0.0)
    assert jumps(hidden) == []


def test_a_world_member_whose_ref_is_missing_is_an_error(tmp_path):
    """S12: the lowering cannot draw it, so validate says so as an error, as it
    does for a listed entity."""
    project = _project(tmp_path)
    scene = _two_lamps_scene(timeline=[Shot(id="two", duration=0.5, viewpoint="two")])
    scene.world.members.append(
        WorldMember(
            kind="prop",
            id="ghost",
            store="props",
            ref="nope",
            at=(0.0, 0.0, 2.0),
            height=0.5,
        )
    )
    errors = [
        f for f in _validate(project, scene).findings
        if f.severity == "error" and "'nope'" in f.description
    ]  # fmt: skip
    assert errors and errors[0].ir_path == "world/members/2"


def test_a_shot_whose_members_cannot_be_measured_says_so():
    """Without the stores no member has an extent: one info line for the shot."""
    scene = _two_lamps_scene(timeline=[Shot(id="two", duration=0.5, viewpoint="two")])
    notes = lower_world(scene, extents={}).notes
    assert any(n.kind == "unplaced" and n.severity == "info" for n in notes)
    assert not any(
        n.kind == "unplaced" and n.severity == "info"
        for n in lower_world(scene, extents=EXTENTS).notes
    )


def test_the_render_says_what_the_lowering_could_not_draw(tmp_path):
    """S12: a member the lowering cannot place is a warning at render, not a
    silent drop (`_prepare_shots` routes the lowering's notes)."""
    import dataclasses

    from an.measurements import ShotFindingWarning
    from an.render import _prepare_shots

    project = _project(tmp_path)
    scene = _two_lamps_scene(timeline=[Shot(id="two", duration=0.5, viewpoint="two")])
    scene.world.members.append(
        WorldMember(
            kind="prop",
            id="ghost",
            store="props",
            ref="nope",
            at=(0.0, 0.0, 2.0),
            height=0.5,
        )
    )
    with pytest.warns(ShotFindingWarning, match="'ghost'"):
        _prepare_shots(
            dataclasses.replace(project, scene=scene), tmp_path / "work", fps=None,
            resolution=None, strict_assets=False, supersample=1, pix_fmt=None,
            capture=None, step_hz=None,
        )  # fmt: skip


def test_a_stream_of_stroked_paths_compiles_with_its_slot_marker(tmp_path):
    """A road marking is a `PathDescriptor` prop: the slot marker is the core's
    key, not a path field, so the path resolves (an#516 review blocker)."""
    from an.paths import PathDescriptor

    project = _project(tmp_path)
    project.mall["props"]["dash"] = PathDescriptor(
        name="dash", points=[(0, 0), (0, -40)]
    ).model_dump(mode="json")
    scene = _travel_scene(Shot(id="s1", duration=2.0, viewpoint="road"))
    scene.world.travel = scene.world.travel.model_copy(
        update={
            "streams": [
                Stream(id="dash", ref="dash", height=1.5, every=3.0, lane=1.2, y=0.0)
            ]
        }
    )
    report = _validate(project, scene)
    bad = [
        f
        for f in report.findings
        if "PathDescriptor" in f.description or "did NOT run" in f.description
    ]
    assert bad == [], bad


def test_the_core_override_keys_are_the_owners_constants():
    from an.base import CORE_OVERRIDE_KEYS, PLANE_FACTORS_OVERRIDE
    from an.ir.world import ATTACHED_OVERRIDE, STREAM_OVERRIDE
    from an.stage.hold import AIM_OVERRIDE, ON_OVERRIDE

    owners = {
        ATTACHED_OVERRIDE,
        STREAM_OVERRIDE,
        ON_OVERRIDE,
        AIM_OVERRIDE,
        PLANE_FACTORS_OVERRIDE,
    }
    assert owners == set(CORE_OVERRIDE_KEYS)


def test_a_member_ref_of_the_wrong_kind_is_an_error_once(tmp_path):
    """The listed entity's rule, for a member: a ref in the store that is not a
    prop is an error at the member, and the lowering's per-shot note on it is
    not repeated."""
    project = _project(tmp_path)
    project.mall["props"]["junk"] = {"kind": "CharacterDescriptor", "name": "junk"}
    scene = _two_lamps_scene(
        timeline=[
            Shot(id="a", duration=0.5, viewpoint="two"),
            Shot(id="b", duration=0.5, viewpoint="two"),
        ]
    )
    scene.world.members.append(
        WorldMember(
            kind="prop",
            id="ghost",
            store="props",
            ref="junk",
            at=(0.0, 0.0, 2.0),
            height=0.5,
        )
    )
    on_ghost = [
        f for f in _validate(project, scene).findings
        if "ghost" in f.description or "'junk'" in f.description
    ]  # fmt: skip
    assert [f.severity for f in on_ghost] == ["error"], on_ghost
    assert on_ghost[0].ir_path == "world/members/2"


def test_screen_direction_skips_an_entity_unseen_on_a_side(tmp_path):
    """Two lamps swap sides across a cut; hidden on one side, they do not."""
    from an.ir.schema import SetAction

    project = _project(tmp_path)
    placed = {
        "left": AssetRef(
            kind="prop",
            id="left",
            store="props",
            ref="lamp",
            stage=StagePlacement(at=(60.0, 0.0)),
        ),
        "right": AssetRef(
            kind="prop",
            id="right",
            store="props",
            ref="lamp",
            stage=StagePlacement(at=(-60.0, 0.0)),
        ),
    }

    def swaps(*end_actions):
        scene = _two_lamps_scene(
            timeline=[
                Shot(
                    id="two", duration=0.5, viewpoint="two", actions=list(end_actions)
                ),
                Shot(
                    id="again",
                    duration=0.5,
                    viewpoint="two",
                    entities=list(placed.values()),
                ),
            ]
        )
        return [
            f
            for f in _validate(project, scene).findings
            if "swap sides" in f.description
        ]

    assert swaps(), "seen on both sides: the swap is reported"
    assert swaps(SetAction(target="left", property="alpha", value=0.0, at=0.0)) == []


def test_a_travel_past_its_budget_stops_fitting_early(monkeypatch):
    """S9: the budget is counted as passes are fitted, so a refused road stops
    fitting once it is past, instead of fitting every pass first."""
    import an.ir.world as world_mod

    calls = []
    real = world_mod._fit_pass

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(world_mod, "_fit_pass", counting)
    scene = _travel_scene(Shot(id="s1", duration=6.0, viewpoint="road"))
    lower_world(scene, extents=EXTENTS)
    every = len(calls)
    calls.clear()
    scene.world.travel = scene.world.travel.model_copy(update={"max_actions": 20})
    with pytest.raises(WorldError, match="at least .* actions, already past"):
        lower_world(scene, extents=EXTENTS)
    assert 0 < len(calls) < every / 2, (len(calls), every)


def test_a_lane_range_is_measured_across_it_not_at_its_ends():
    """B3 review: a field of trees over lanes 2..60 under a wide side window.
    Neither end sees much (60 is past `far`), the lanes between see most."""
    scene = _travel_scene(Shot(id="s1", duration=6.0, viewpoint="road"), yaw=90.0)
    scene.world.viewpoints["road"] = Viewpoint(
        at=(0.0, -1.0, 0.0), look=(90.0, 0.0, 0.0), fov=120.0
    )
    scene.world.travel = scene.world.travel.model_copy(
        update={
            "far": 30.0,
            "streams": [
                Stream(
                    id="pole",
                    ref="lamp",
                    height=6.0,
                    every=3.0,
                    lane=(2.0, 60.0),
                    y=0.0,
                )
            ],
        }
    )
    lower_world(scene, extents=EXTENTS)  # no "two instances in one slot"


def test_a_travel_is_not_reported_as_solids_through_each_other(tmp_path):
    """an#632: three shots down a road of poles. A slot hidden between passes
    overlaps nothing, a nearer pole over a farther one is occlusion, and the
    draw-order check leaves slots to the world. What is left is the paint
    inversion of a reused slot (an#634), said as such."""
    project = _project(tmp_path)
    scene = _travel_scene(
        *[Shot(id=f"s{i}", duration=3.0, viewpoint="road") for i in range(3)]
    )
    found = _validate(project, scene).findings
    assert not [f for f in found if "drawn through each other" in f.description]
    assert not [f for f in found if "the order flips" in f.description]
    inversions = [f for f in found if "though it is the farther" in f.description]
    assert inversions and all("an#634" in f.description for f in inversions)


# --- an#629: a closed-form pass is one exact tween per channel -----------------


def test_a_closed_form_pass_is_one_perspective_tween_per_channel_and_exact():
    """A point at lateral X, height Y, depth z0 - v·t: its projection is drawn
    by `projective(z_out / z_in)` between the window's ends, exactly."""
    from an.ir.world import _fit_pass
    from an.timing.easing import apply_easing

    focal, X, Y, z0, v = 300.0, 1.7, 0.6, 30.0, 6.0

    def depth(t):
        return z0 - v * t

    def g(t):
        return focal * X / depth(t), focal * Y / depth(t), 0.5 * focal / depth(t)

    p = _fit_pass(
        g, 0.0, 4.0, box=BOX, ref_height=20.0, tol=0.5, min_step=0.05,
        width=W, height=H, depth=depth,
    )  # fmt: skip
    for prop, i in (("x", 0), ("y", 1), ("scale_x", 2)):
        ((ta, tb, va, vb, ease),) = p.channels[prop]
        assert ease.startswith("projective(")
        for k in range(1, 20):
            t = ta + (tb - ta) * k / 20
            drawn = va + (vb - va) * apply_easing(ease, (t - ta) / (tb - ta))
            assert drawn == pytest.approx(g(t)[i], rel=1e-9, abs=1e-9)


def test_a_minute_of_road_costs_a_third_of_what_fitting_did():
    """S9's case: a 60 s road with a pole every 2 units. Fitted, it lowered to
    3695 actions; one tween per channel per pass, 1312. A budget of 2000
    refused it, and now holds it."""
    scene = _travel_scene(Shot(id="s1", duration=60.0, viewpoint="road"))
    scene.world.travel = scene.world.travel.model_copy(
        update={
            "streams": [
                Stream(id="pole", ref="lamp", height=1.5, every=2.0, lane=1.2, y=0.0)
            ],
            "max_actions": 2000,
        }
    )
    shot = lower_world(scene, extents=EXTENTS).scene.timeline[0]
    assert 0 < len(shot.actions) <= 2000
