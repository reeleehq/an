"""A shot that opens from another shot's end state (an#542): `continue:`."""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import pytest

from an.continuity import ContinuityError, EntityEnd, _carried, continue_shots
from an.ir.schema import (
    AssetRef,
    Meta,
    SceneIR,
    SetAction,
    Shot,
    StagePlacement,
    TweenAction,
)
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.validate import validate_semantic
from an.project import load

ROOT = Path(__file__).resolve().parents[1]
LAMP = ROOT / "misc" / "bench" / "corpus" / "prop_swap"
FPS = 24


def _lamp(at=(0.0, 90.0)) -> AssetRef:
    return AssetRef(
        kind="prop", id="lamp", store="props", ref="lamp",
        stage=StagePlacement(at=at, scale=0.55),
    )  # fmt: skip


def _studio(*, continue_from=None, actions=()) -> Shot:
    return Shot(
        id="next", duration=0.5, entities=[_lamp()], actions=list(actions),
        continue_from=continue_from,
    )  # fmt: skip


def _bedtime() -> Shot:
    """The lamp walks to x 120, turns on, and fades to half."""
    return Shot(
        id="bed", duration=0.5, entities=[_lamp()],
        actions=[
            TweenAction(target="lamp", property="x", to_value=120.0, duration=0.5),
            TweenAction(target="lamp", property="alpha", to_value=0.5, duration=0.5),
            SetAction(target="lamp/body", property="lamp", value="on", at=0.25),
        ],
    )  # fmt: skip


def _scene(*shots: Shot) -> SceneIR:
    scene = SceneIR(meta=Meta(fps=FPS), timeline=list(shots))
    scene.meta.resolution.width, scene.meta.resolution.height = 320, 240
    return scene


def _mall(tmp_path):
    return load(Path(shutil.copytree(LAMP, tmp_path / "p"))).mall


def _opening(shot: Shot, mall) -> dict:
    """The continuing shot's lamp at its first frame, as the runtime draws it."""
    from an.continuity import end_states
    from an.stage.compile import compile_shot

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = compile_shot(shot, mall=mall, fps=FPS, width=320, height=240)
    return end_states(doc, ["lamp"], at=0.0)["lamp"].channels


def test_a_continued_shot_opens_as_the_other_one_ends(tmp_path):
    mall = _mall(tmp_path)
    scene = continue_shots(
        _scene(_bedtime(), _studio(continue_from="bed")), mall, fps=FPS
    )
    opening = _opening(scene.timeline[1], mall)
    assert opening[("lamp", "x")] == pytest.approx(120.0)
    assert opening[("lamp", "alpha")] == pytest.approx(0.5)
    assert opening[("lamp/body", "lamp")] == "on"
    assert scene.timeline[0] == _bedtime(), "the source is untouched"


def test_the_shots_own_opening_wins(tmp_path):
    mall = _mall(tmp_path)
    own = SetAction(target="lamp", property="x", value=-40.0, at=0.0)
    scene = continue_shots(
        _scene(_bedtime(), _studio(continue_from="bed", actions=[own])), mall, fps=FPS
    )
    opening = _opening(scene.timeline[1], mall)
    assert opening[("lamp", "x")] == pytest.approx(-40.0)
    assert opening[("lamp", "alpha")] == pytest.approx(0.5)


def test_a_shot_can_continue_a_later_one_and_a_cycle_is_refused(tmp_path):
    mall = _mall(tmp_path)
    scene = continue_shots(
        _scene(_studio(continue_from="bed"), _bedtime()), mall, fps=FPS
    )
    assert _opening(scene.timeline[0], mall)[("lamp", "x")] == pytest.approx(120.0)
    a = _bedtime().model_copy(update={"continue_from": "next"})
    with pytest.raises(ContinuityError, match="cycle"):
        continue_shots(_scene(a, _studio(continue_from="bed")), mall, fps=FPS)
    with pytest.raises(ContinuityError, match="names no shot"):
        continue_shots(_scene(_studio(continue_from="nope")), mall, fps=FPS)


def test_a_sibling_scene_file_is_read_from_the_project(tmp_path):
    mall = _mall(tmp_path)
    project = tmp_path / "p"
    (project / "scene.bedtime.md").write_text(
        ir_to_markdown(_scene(_bedtime())), encoding="utf-8"
    )
    scene = continue_shots(
        _scene(_studio(continue_from="scene.bedtime.md#bed")), mall, fps=FPS
    )
    assert _opening(scene.timeline[0], mall)[("lamp", "x")] == pytest.approx(120.0)
    with pytest.raises(ContinuityError, match="names no shot of 'scene.bedtime.md'"):
        continue_shots(
            _scene(_studio(continue_from="scene.bedtime.md#gone")), mall, fps=FPS
        )


def test_validate_reports_a_continuation_that_cannot_resolve_at_its_shot(
    tmp_path,
):
    mall = _mall(tmp_path)

    def findings(scene):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return validate_semantic(scene, available_props=mall["props"]).findings

    bad = findings(_scene(_studio(continue_from="nope")))
    assert any(
        f.severity == "error"
        and "names no shot" in f.description
        and f.ir_path == "timeline/0/continue_from"
        for f in bad
    )
    world = _scene(_bedtime(), _studio(continue_from="nope"))
    assert any("names no shot" in f.description for f in findings(world))


def test_continue_round_trips_through_scene_md_and_omits_when_unset():
    scene = _scene(_bedtime(), _studio(continue_from="scene.bedtime.md#bed"))
    back = markdown_to_ir(ir_to_markdown(scene))
    assert back.timeline[1].continue_from == "scene.bedtime.md#bed"
    assert "continue_from" not in _bedtime().model_dump()


def _shot_of(*ids) -> Shot:
    return Shot(
        id="s", duration=1.0,
        entities=[AssetRef(kind="prop", id=i, store="props", ref=i) for i in ids],
    )  # fmt: skip


def _end(eid, holder, **channels):
    base = {"x": 5.0, "y": 7.0, "rotation": 0.7, "scale_x": 1.0, "scale_y": 1.0}
    return EntityEnd(
        {(eid, k): v for k, v in {**base, **channels}.items()}, holder=holder
    )


def test_a_held_item_carries_its_holder_by_kind():
    """A hand in this shot keeps holding it, aimed (no place carried); a hand
    this shot lacks leaves it where it was; a place or the floor holds it
    without an aim (the floor keeps its x)."""
    ends = {
        "musket": _end("musket", "napoleon@hand_r"),
        "pistol": _end("pistol", "hannibal@hand_l"),
        "book": _end("book", "world@10,20"),
        "sabre": _end("sabre", "ground"),
    }
    out = _carried(
        _shot_of("napoleon", "musket", "pistol", "book", "sabre"), ends, fps=FPS
    )
    by_id = {e.id: e.overrides for e in out.entities}
    assert by_id["musket"] == {"held_by": "napoleon@hand_r", "held_rotation": 0.7}
    assert by_id["pistol"] is None, "its holder is not in this shot"
    assert by_id["book"] == {"held_by": "world@10,20"}
    assert by_id["sabre"] == {"held_by": "ground"}
    carried = {(a.target, a.property) for a in out.actions}
    assert ("musket", "x") not in carried and ("pistol", "x") in carried
    assert ("book", "x") not in carried and ("book", "rotation") in carried
    assert ("sabre", "x") in carried and ("sabre", "y") not in carried


def test_a_tween_from_where_it_is_glides_from_the_carried_value(tmp_path):
    mall = _mall(tmp_path)
    glide = TweenAction(target="lamp", property="x", to_value=0.0, duration=0.5)
    scene = continue_shots(
        _scene(_bedtime(), _studio(continue_from="bed", actions=[glide])), mall, fps=FPS
    )
    assert _opening(scene.timeline[1], mall)[("lamp", "x")] == pytest.approx(120.0)


def test_two_files_sharing_a_shot_id_are_not_a_cycle(tmp_path):
    """A: s1 -> intro, intro -> scene.b.md#y; B: y -> intro (B's own)."""
    mall = _mall(tmp_path)
    b = _scene(
        _bedtime().model_copy(update={"id": "intro"}),
        _studio(continue_from="intro").model_copy(update={"id": "y"}),
    )
    (tmp_path / "p" / "scene.b.md").write_text(ir_to_markdown(b), encoding="utf-8")
    a = _scene(
        _studio(continue_from="intro").model_copy(update={"id": "s1"}),
        _studio(continue_from="scene.b.md#y").model_copy(update={"id": "intro"}),
    )
    scene = continue_shots(a, mall, fps=FPS)
    assert _opening(scene.timeline[0], mall)[("lamp", "x")] == pytest.approx(120.0)


def test_validate_reads_a_sibling_file_and_names_the_authors_actions(tmp_path):
    mall = _mall(tmp_path)
    (tmp_path / "p" / "scene.bedtime.md").write_text(
        ir_to_markdown(_scene(_bedtime())), encoding="utf-8"
    )
    typo = SetAction(target="lamp", property="nope_prop", value=1.0, at=0.2)
    scene = _scene(_studio(continue_from="scene.bedtime.md#bed", actions=[typo]))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = validate_semantic(
            scene, available_props=mall["props"], available_scenes=mall["scenes"]
        )
    assert not [f for f in report.findings if "continue" in f.ir_path], report.findings
    on_actions = [f.ir_path for f in report.findings if "/actions/" in f.ir_path]
    assert on_actions and all(p.startswith("timeline/0/actions/0") for p in on_actions)


def test_a_cut_between_two_framings_leaves_placement_to_the_world(tmp_path):
    """Wide shot, then a close-up that continues it: the world places the
    lamp in the close-up; continuity carries no screen placement for it."""
    from an.ir.schema import Viewpoint, World, WorldMember
    from an.stage.world import lower_scene

    mall = _mall(tmp_path)
    world = World(
        members=[WorldMember(kind="prop", id="lamp", store="props", ref="lamp",
                             at=(0.0, 0.4, 2.0), height=0.8)],
        viewpoints={
            "wide": Viewpoint(at=(0.0, 0.0, 0.0), focal=300.0),
            "cu": Viewpoint(subject="lamp", size="close_up", focal=300.0),
        },
    )  # fmt: skip
    scene = _scene(
        Shot(id="w", duration=0.5, viewpoint="wide"),
        Shot(id="c", duration=0.5, viewpoint="cu", continue_from="w"),
    ).model_copy(update={"world": world})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lowered = lower_scene(scene, mall, fps=FPS)
    carried = {(a.target, a.property) for a in lowered.scene.timeline[1].actions}
    assert ("lamp", "x") not in carried and ("lamp", "alpha") in carried


def test_a_surface_whose_body_is_absent_leaves_the_item_where_it_was():
    out = _carried(_shot_of("book"), {"book": _end("book", "crate@surface")}, fps=FPS)
    assert out.entities[0].overrides is None
    assert ("book", "x") in {(a.target, a.property) for a in out.actions}
    held = _carried(
        _shot_of("crate", "book"), {"book": _end("book", "crate@surface")}, fps=FPS
    )
    assert held.entities[1].overrides == {"held_by": "crate@surface"}


def test_each_source_is_compiled_once(tmp_path):
    from an.stage.compile import compile_shot

    mall, calls = _mall(tmp_path), []

    def counting(shot, **kw):
        calls.append(shot.id)
        return compile_shot(shot, **kw)

    two = _studio(continue_from="bed").model_copy(update={"id": "again"})
    continue_shots(
        _scene(_bedtime(), _studio(continue_from="bed"), two),
        mall,
        fps=FPS,
        compile_shot=counting,
    )
    assert calls == ["bed"]


def test_the_render_validate_reads_a_sibling_file(tmp_path):
    """`an render`'s post-synthesis checks see the project's scenes store, so
    a sibling-file continue is not reported as unresolvable."""
    from an.render import _post_synthesis

    _mall(tmp_path)
    project = load(tmp_path / "p")
    (tmp_path / "p" / "scene.bedtime.md").write_text(
        ir_to_markdown(_scene(_bedtime())), encoding="utf-8"
    )
    scene = _scene(_studio(continue_from="scene.bedtime.md#bed"))
    found = _post_synthesis(project, scene, fps=FPS)
    assert not [f for _, f in found if "continue" in f.description], found
