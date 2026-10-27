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
    with pytest.raises(ContinuityError, match="names no other shot"):
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
    with pytest.raises(ContinuityError, match="has no shot 'gone'"):
        continue_shots(
            _scene(_studio(continue_from="scene.bedtime.md#gone")), mall, fps=FPS
        )


def test_validate_reports_a_continuation_that_cannot_resolve_and_no_jump_after_one(
    tmp_path,
):
    mall = _mall(tmp_path)

    def findings(scene):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return validate_semantic(scene, available_props=mall["props"]).findings

    bad = findings(_scene(_studio(continue_from="nope")))
    assert any(
        f.severity == "error" and "names no other shot" in f.description for f in bad
    )
    jumped = findings(_scene(_bedtime(), _studio()))
    assert any("jumps across the cut" in f.description for f in jumped)
    carried = findings(_scene(_bedtime(), _studio(continue_from="bed")))
    assert not any("jumps across the cut" in f.description for f in carried)


def test_continue_round_trips_through_scene_md_and_omits_when_unset():
    scene = _scene(_bedtime(), _studio(continue_from="scene.bedtime.md#bed"))
    back = markdown_to_ir(ir_to_markdown(scene))
    assert back.timeline[1].continue_from == "scene.bedtime.md#bed"
    assert "continue_from" not in _bedtime().model_dump()


def test_a_held_item_carries_its_holder_and_aim_not_its_place():
    """A hand holds it as the source ends: the next shot opens with the same
    hand holding it at the same angle (`held_by`, `held_rotation`)."""
    ends = {
        "musket": EntityEnd(
            {
                ("musket", "x"): 5.0,
                ("musket", "rotation"): 0.7,
                ("musket", "alpha"): 1.0,
            },
            holder="napoleon@hand_r",
        ),
        "sabre": EntityEnd(
            {("sabre", "x"): -30.0, ("sabre", "rotation"): 0.0}, holder="ground"
        ),
    }
    shot = Shot(
        id="s", duration=1.0,
        entities=[AssetRef(kind="prop", id=i, store="props", ref=i) for i in ("musket", "sabre")],
    )  # fmt: skip
    out = _carried(shot, ends, fps=FPS)
    musket, sabre = out.entities
    assert musket.overrides == {"held_by": "napoleon@hand_r", "held_rotation": 0.7}
    assert sabre.overrides == {"held_by": "ground"}
    carried = {(a.target, a.property) for a in out.actions}
    assert ("musket", "x") not in carried and ("musket", "alpha") in carried
    assert ("sabre", "x") in carried
