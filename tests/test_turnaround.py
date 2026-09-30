"""Turnaround views and the `turn` preset (an#197).

Three end-user agents asked for "Y turns around and says bye" in three styles
and all three faked it: the factory drew front views only, a `scale_x` flip of
a symmetric front is invisible, so they squashed the character paper-thin and
set `alpha: 0` on nine face node paths guessed by trial. What this file holds:

1. **The factory draws views** — `front`, `three_quarter`, `side`, `back` as a
   `view` swap set on the head and torso, on the SAME canvas as the front (the
   swap carries texture only), every colour role-tagged like the front's.
2. **Views are additive** — the art a character had is byte-identical, and a
   shot that never sets a view compiles exactly as without the poses.
3. **A whole-character swap poses the rig** (`swap_poses`): the back hides the
   face, the profile keeps one eye, the mouth still lip-syncs, a posed pupil
   still follows the gaze — asserted on the COMPILED document, evaluated.
4. **`turn`** squashes `scale_x` through 0 and swaps at the midpoint, mirrored
   for `direction: left`, playable by name from `scene.md`.
5. Pixels: front, back and side render visibly different (browser lane).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import (
    SCENE_PX_PER_VIEW_BOX,
    CutoutCompileError,
    compile_shot,
)
from an.adapters.cutout.serialize import to_dict
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.characters import new_character
from an.characters.factory import (
    FACE_SLOTS,
    SIDE_EYE_SHIFT,
    SIDE_MOUTH_SHIFT,
    THREE_QUARTER_FACE_SHIFT,
    add_views,
)
from an.characters.play import play_problems
from an.characters.schema import VIEW_CHANNEL, VIEWS, CharacterDescriptor
from an.characters.svg_utils import raster_size
from an.characters.validate import validate_character
from an.ir.compose import delay, flatten, sequence, set_
from an.ir.schema import (
    AssetRef,
    Dialogue,
    PlayAction,
    SetAction,
    Shot,
    VisemeKeyframe,
    VisemeTrack,
)
from an.motion import PRESETS, face_toward, turn
from an.project import init, load

K = SCENE_PX_PER_VIEW_BOX / 1024.0
FPS = 24


def _desc(path: Path) -> CharacterDescriptor:
    return CharacterDescriptor.model_validate_json(path.read_text("utf-8"))


@pytest.fixture(scope="module")
def project():
    with tempfile.TemporaryDirectory() as d:
        root = init(Path(d) / "p")
        chars = root / "assets" / "characters"
        new_character(chars, name="ned", seed="ned", use_dicebear=False, hat="cap", sash=True)
        new_character(chars, name="carl", seed="carl", use_dicebear=False)
        yield root


def _shot(actions=(), *, dialogue=(), entities=("ned",), duration=2.0) -> Shot:
    return Shot(
        id="s",
        renderer="cutout",
        duration=duration,
        entities=[
            AssetRef(kind="character", id=e, store="characters", ref=e) for e in entities
        ],
        actions=list(actions),
        dialogue=list(dialogue),
    )


def _compile(project, shot):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(shot, mall=load(project).mall, fps=FPS, strict_assets=True)


def _pose_at(doc, t):
    return evaluate_timeline(timeline_from_scene(doc), t)


def _rest(doc, path):
    node = None
    for part in path.split("/"):
        kids = doc.scene.children if node is None else node.children
        node = next(n for n in kids if n.name == part)
    return node.transform


def _value(doc, pose, path, prop):
    return pose.get((path, prop), getattr(_rest(doc, path), prop))


# --- 1. the factory draws views ------------------------------------------------


def test_an_offline_character_declares_the_four_views(project):
    desc = _desc(project / "assets" / "characters" / "ned" / "character.json")
    assert desc.asset_sets[VIEW_CHANNEL] == {v: v for v in VIEWS}
    skin = desc.skins["default"]
    for slot in ("head", "torso"):
        assert set(VIEWS) <= set(skin.slots[slot])
        # `front` IS the default art: resting and being set to front look the same.
        assert skin.slots[slot]["front"].path == skin.slots[slot][slot].path
    assert set(desc.swap_poses[VIEW_CHANNEL]) == set(VIEWS)
    assert desc.swap_poses[VIEW_CHANNEL]["front"] == {}


def test_view_art_shares_the_front_canvas_and_its_colour_roles(project):
    """A swap carries texture only and is fitted into the front's box (an#87),
    so a view drawn on another canvas would land somewhere else; and a view
    whose colours were untagged would stay put under a StylePack (an#191)."""
    c = project / "assets" / "characters" / "ned"
    desc = _desc(c / "character.json")
    for slot in ("head", "torso"):
        front = desc.skins["default"].slots[slot]["front"]
        for view in VIEWS:
            att = desc.skins["default"].slots[slot][view]
            assert raster_size(c / att.path) == raster_size(c / front.path), (slot, view)
            assert (att.anchor, att.x, att.y) == (front.anchor, front.x, front.y)
            assert set(desc.colour_roles[att.path].values()) == set(
                desc.colour_roles[front.path].values()
            ), (slot, view)


def test_the_character_validates_clean(project):
    report = validate_character(project / "assets" / "characters" / "ned")
    assert not [f for f in report.findings if f.severity == "error"], report.findings


def test_views_are_additive_to_the_character_that_existed(tmp_path):
    """Every file and descriptor entry of a `views=False` character is in the
    default one unchanged — views only ADD (the variety goldens hold views off)."""
    plain = new_character(tmp_path / "a", name="c", use_dicebear=False, views=False).parent
    views = new_character(tmp_path / "b", name="c", use_dicebear=False).parent
    for f in plain.rglob("*.svg"):
        assert (views / f.relative_to(plain)).read_bytes() == f.read_bytes(), f
    a = json.loads((plain / "character.json").read_text("utf-8"))
    b = json.loads((views / "character.json").read_text("utf-8"))
    assert VIEW_CHANNEL not in a["asset_sets"] and not a["swap_poses"]
    for key in ("bones", "slots", "animations", "gaze_travel", "face_overlay"):
        assert a[key] == b[key], key
    for slot, atts in a["skins"]["default"]["slots"].items():
        for name, att in atts.items():
            assert b["skins"]["default"]["slots"][slot][name] == att
    for part, roles in a["colour_roles"].items():
        assert b["colour_roles"][part] == roles
    assert {k: v for k, v in b["asset_sets"].items() if k != VIEW_CHANNEL} == a["asset_sets"]
    assert {k: v for k, v in b["metadata"].items() if k != "views"} == a["metadata"]


def test_add_views_is_idempotent_and_brings_an_old_character_level(tmp_path):
    old = new_character(tmp_path, name="c", use_dicebear=False, views=False, build="squat", head_scale=1.3, hat="beanie").parent
    add_views(old)
    first = {p: p.read_bytes() for p in sorted(old.rglob("*")) if p.is_file()}
    add_views(old)
    assert first == {p: p.read_bytes() for p in sorted(old.rglob("*")) if p.is_file()}
    fresh = new_character(tmp_path / "f", name="c", use_dicebear=False, build="squat", head_scale=1.3, hat="beanie").parent
    for p, data in first.items():
        assert (fresh / p.relative_to(old)).read_bytes() == data, p


def test_add_views_refuses_art_it_did_not_draw(tmp_path):
    c = new_character(tmp_path, name="c", use_dicebear=False, views=False).parent
    head = c / "parts" / "head.svg"
    head.write_text(head.read_text("utf-8").replace("<circle", '<circle data-edited="1"', 1), "utf-8")
    with pytest.raises(ValueError, match="not the factory's drawing"):
        add_views(c)
    d = json.loads((c / "character.json").read_text("utf-8"))
    d["metadata"]["art_provenance"] = "dicebear"
    (c / "character.json").write_text(json.dumps(d), "utf-8")
    with pytest.raises(ValueError, match="cannot be synthesized"):
        add_views(c)


def test_validate_names_a_pose_on_a_slot_the_rig_does_not_have(tmp_path):
    c = new_character(tmp_path, name="c", use_dicebear=False).parent
    d = json.loads((c / "character.json").read_text("utf-8"))
    d["swap_poses"]["view"]["back"]["tail"] = {"alpha": 0.0}
    d["swap_poses"]["nope"] = {"x": {}}
    (c / "character.json").write_text(json.dumps(d), "utf-8")
    errors = [f.description for f in validate_character(c).findings if f.severity == "error"]
    assert any("'tail'" in e for e in errors), errors
    assert any("'nope'" in e for e in errors), errors


# --- 2. additive at compile ----------------------------------------------------


def test_a_shot_that_sets_no_view_compiles_as_without_the_poses(project, tmp_path):
    """The poses are read only when a whole-character swap lands, so a scene
    that never turns anyone is the document it always was."""
    shot = _shot([set_("ned", "y", 20.0)])
    with_poses = to_dict(_compile(project, shot))
    root = init(tmp_path / "q")
    chars = root / "assets" / "characters"
    new_character(chars, name="ned", seed="ned", use_dicebear=False, hat="cap", sash=True)
    d = json.loads((chars / "ned" / "character.json").read_text("utf-8"))
    d["swap_poses"] = {}
    (chars / "ned" / "character.json").write_text(json.dumps(d), "utf-8")
    without = to_dict(_compile(root, shot))
    with_poses.pop("assets"), without.pop("assets")  # temp-dir texture paths
    assert with_poses == without


# --- 3. the pose of each view ----------------------------------------------------


@pytest.mark.parametrize("view", VIEWS)
def test_each_view_swaps_the_head_and_torso_and_poses_the_rig(project, view):
    doc = _compile(project, _shot([SetAction(target="ned", property="view", value=view, at=0.5)]))
    before, after = _pose_at(doc, 0.25), _pose_at(doc, 1.0)
    for slot in ("head", "torso"):
        assert after[(f"ned/{slot}", VIEW_CHANNEL)] == view
        assert (f"ned/{slot}", VIEW_CHANNEL) not in before
    face = [f"ned/head/{s}" for s in FACE_SLOTS]
    alpha = {p: _value(doc, after, p, "alpha") for p in face}
    assert all(_value(doc, before, p, "alpha") == 1.0 for p in face)  # rest until the swap
    if view == "back":
        assert set(alpha.values()) == {0.0}, alpha
    elif view == "side":
        assert {p for p, a in alpha.items() if a == 0.0} == {
            f"ned/head/{s}" for s in ("left_eye", "left_sclera", "left_pupil", "left_brow")
        }
        assert _value(doc, after, "ned/arm_l", "alpha") == 0.0
        rest = _rest(doc, "ned/head/right_eye").x
        assert _value(doc, after, "ned/head/right_eye", "x") == pytest.approx(rest + SIDE_EYE_SHIFT * K)
        mouth_rest = _rest(doc, "ned/head/mouth")
        assert _value(doc, after, "ned/head/mouth", "x") == pytest.approx(mouth_rest.x + SIDE_MOUTH_SHIFT * K)
        assert _value(doc, after, "ned/head/mouth", "scale_x") < mouth_rest.scale_x
    else:
        assert set(alpha.values()) == {1.0}, alpha
    if view == "three_quarter":
        for s in ("left_eye", "right_eye", "left_brow"):
            path = f"ned/head/{s}"
            assert _value(doc, after, path, "x") == pytest.approx(
                _rest(doc, path).x + THREE_QUARTER_FACE_SHIFT * K
            ), path
    if view == "front":
        # Every pose curve returns to rest: nothing moved.
        for (path, prop), v in after.items():
            if prop in ("alpha", "scale_x") and "pupil" not in path and path != "ned":
                assert v == pytest.approx(getattr(_rest(doc, path), prop)), (path, prop)


def test_same_instant_swaps_resolve_to_the_later_one(project):
    doc = _compile(project, _shot([
        SetAction(target="ned", property="view", value="side", at=0.5),
        SetAction(target="ned", property="view", value="back", at=0.5),
    ]))
    pose = _pose_at(doc, 1.0)
    assert pose[("ned/head", VIEW_CHANNEL)] == "back"
    assert _value(doc, pose, "ned/head/right_eye", "alpha") == 0.0  # back's pose
    assert _value(doc, pose, "ned/arm_l", "alpha") == 1.0  # not side's


def test_a_view_off_the_frame_grid_lands_on_the_next_frame(project):
    at = 0.5 + 0.4 / FPS
    doc = _compile(project, _shot([SetAction(target="ned", property="view", value="back", at=at)]))
    assert _value(doc, _pose_at(doc, 12 / FPS), "ned/head/mouth", "alpha") == 1.0
    assert _value(doc, _pose_at(doc, 13 / FPS), "ned/head/mouth", "alpha") == 0.0


def test_a_baked_face_rig_is_still_posed(project, tmp_path):
    """A rig with its face in the head art never reaches the face solver; its
    view still hides the far arm (review of an#197)."""
    root = init(tmp_path / "q")
    chars = root / "assets" / "characters"
    new_character(chars, name="ned", seed="ned", use_dicebear=False, hat="cap", sash=True)
    d = json.loads((chars / "ned" / "character.json").read_text("utf-8"))
    d["face_overlay"] = False
    (chars / "ned" / "character.json").write_text(json.dumps(d), "utf-8")
    doc = _compile(root, _shot([SetAction(target="ned", property="view", value="side", at=0.0)]))
    pose = _pose_at(doc, 0.5)
    assert pose[("ned/head", VIEW_CHANNEL)] == "side"
    assert pose[("ned/arm_l", "alpha")] == 0.0
    assert pose[("ned/arm_r", "x")] == pytest.approx(_rest(doc, "ned/arm_r").x - 90.0 * K)


def test_back_to_front_restores_the_rest_pose(project):
    doc = _compile(project, _shot([
        SetAction(target="ned", property="view", value="side", at=0.2),
        SetAction(target="ned", property="view", value="front", at=1.0),
    ]))
    pose = _pose_at(doc, 1.5)
    for s in (*FACE_SLOTS, "arm_l", "arm_r", "leg_l", "leg_r"):
        path = f"ned/head/{s}" if s in FACE_SLOTS else f"ned/{s}"
        rest = _rest(doc, path)
        # A pupil's x/y is its rest plus the ambient saccade, inside the travel.
        slack = 9.0 * K + 1e-6 if s.endswith("pupil") else 1e-6
        for prop in ("x", "y", "alpha", "scale_x"):
            assert abs(_value(doc, pose, path, prop) - getattr(rest, prop)) <= slack, (path, prop)


def test_a_posed_pupil_keeps_its_gaze(project):
    """The pupil's x is ONE channel: the gaze solver's, summed onto the pose —
    not a pose channel that freezes the gaze, nor two that fight."""
    doc = _compile(project, _shot([SetAction(target="ned", property="view", value="side", at=0.0)], duration=4.0))
    path = "ned/head/right_pupil"
    channels = [c for a in doc.animations.values() for c in a.channels if (c.target, c.property) == (path, "x")]
    assert len(channels) == 1
    xs = {round(kf.value, 3) for kf in channels[0].keyframes}
    assert len(xs) > 1, "the saccades still move the pupil"
    rest = _rest(doc, path).x + SIDE_EYE_SHIFT * K
    travel = 9.0 * K  # `gaze_travel_for()["x"]` at k
    assert all(abs(x - rest) <= travel + 1e-6 for x in xs)


def test_the_mouth_lip_syncs_in_profile_and_hides_with_the_back(project):
    line = Dialogue(
        speaker="ned", text="hi", start=0.0, duration=1.0,
        viseme_track=VisemeTrack(keyframes=[
            VisemeKeyframe(time=0.0, viseme="X"),
            VisemeKeyframe(time=0.3, viseme="A"),
            VisemeKeyframe(time=0.7, viseme="C"),
        ]),
    )
    for view, shown in (("side", 1.0), ("back", 0.0)):
        doc = _compile(project, _shot([SetAction(target="ned", property="view", value=view, at=0.0)], dialogue=[line]))
        pose = _pose_at(doc, 0.5)
        assert pose[("ned/head/mouth", "viseme")] == "A"
        assert _value(doc, pose, "ned/head/mouth", "alpha") == shown


def test_a_tint_on_the_character_is_not_taken_for_a_swap(project):
    """Reiniger's silhouette is a black `tint` on each character root beside a
    `view: side` — a transform-ish property on the entity must never be fanned
    out as a whole-character swap (found rendering the Reiniger spec)."""
    doc = _compile(project, _shot([
        SetAction(target="ned", property="tint", value="#000000", at=0.0),
        SetAction(target="ned", property="alpha", value=0.5, at=0.0),
        SetAction(target="ned", property="view", value="side", at=0.0),
    ]))
    pose = _pose_at(doc, 0.5)
    assert pose[("ned", "tint_r")] == 0.0 and pose[("ned", "alpha")] == 0.5
    assert pose[("ned/head", VIEW_CHANNEL)] == "side"


def test_a_view_swap_on_a_character_without_views_is_refused(project, tmp_path):
    root = init(tmp_path / "q")
    new_character(root / "assets" / "characters", name="old", use_dicebear=False, views=False)
    with pytest.raises(CutoutCompileError, match="add-views"):
        _compile(root, _shot([SetAction(target="old", property="view", value="back", at=0.0)], entities=("old",)))
    with pytest.raises(CutoutCompileError, match="'upside_down'"):
        _compile(project, _shot([SetAction(target="ned", property="view", value="upside_down", at=0.0)]))


# --- 4. the turn preset --------------------------------------------------------


def test_turn_is_a_preset_played_by_name(project):
    assert PRESETS["turn"] is turn
    desc = CharacterDescriptor(name="plain")  # no views
    assert any("add-views" in p for p in play_problems(desc, "turn", args={"to": "back"}))
    with_views = CharacterDescriptor.model_validate_json(
        (project / "assets" / "characters" / "ned" / "character.json").read_text("utf-8")
    )
    assert play_problems(with_views, "turn", args={"to": "side"}) == []
    (bad,) = play_problems(with_views, "turn", args={"to": "side", "direction": "up"})
    assert "direction" in bad


@pytest.mark.parametrize(("direction", "sign"), [("right", 1.0), ("left", -1.0)])
def test_turn_crosses_zero_and_swaps_at_the_midpoint(project, direction, sign):
    start, dur = 0.5, 0.5
    doc = _compile(project, _shot([
        sequence(delay(start), PlayAction(
            target="ned", animation="turn", args={"to": "side", "direction": direction, "duration": dur}
        ))
    ]))
    mid = start + dur / 2
    s0 = _rest(doc, "ned").scale_x
    frame = 1.0 / FPS
    early, late = _pose_at(doc, mid - frame), _pose_at(doc, mid + frame)
    assert _pose_at(doc, mid)[("ned", "scale_x")] == pytest.approx(0.0, abs=1e-9)
    assert 0 < early[("ned", "scale_x")] < s0
    assert (late[("ned", "scale_x")] > 0) == (sign > 0)
    assert ("ned/head", VIEW_CHANNEL) not in early  # still the front
    assert late[("ned/head", VIEW_CHANNEL)] == "side"
    assert _value(doc, early, "ned/head/left_eye", "alpha") == 1.0
    assert _value(doc, late, "ned/head/left_eye", "alpha") == 0.0
    assert _pose_at(doc, 1.5)[("ned", "scale_x")] == pytest.approx(sign * s0)


def test_validate_says_a_turn_s_art_is_missing(project, tmp_path):
    """`an validate` and compile agree when a view's art is gone (review)."""
    import shutil

    from an.characters.play import art_exists_for

    root = init(tmp_path / "q")
    shutil.copytree(project / "assets" / "characters" / "ned", root / "assets" / "characters" / "ned")
    (root / "assets" / "characters" / "ned" / "parts" / "head_side.svg").unlink()
    mall = load(root).mall
    desc = CharacterDescriptor.model_validate(mall["characters"]["ned"])
    (problem,) = play_problems(
        desc, "turn", args={"to": "side"}, art_exists=art_exists_for(mall["characters"], "ned")
    )
    assert "head_side.svg" in problem


def test_turn_infers_the_starting_side_from_a_mirrored_rest():
    first = flatten(turn("ned", to="back", rest={"scale_x": -2.0}))[0].action
    assert first.from_value == -2.0


def test_turn_back_from_a_left_profile_starts_mirrored():
    flats = flatten(turn("ned", to="front", from_direction="left", rest={"scale_x": 1.4}))
    first = flats[0].action
    assert (first.from_value, first.to_value) == (-1.4, 0.0)
    assert flats[-1].action.value == 1.4


def test_face_toward_reads_the_direction_off_the_stage(project):
    shot = _shot(entities=("ned", "carl"))
    mall = load(project).mall
    leaves = [f.action for f in flatten(face_toward(shot, "ned", "carl", mall=mall))]
    assert leaves[-1].value > 0  # carl stands to ned's right: face right
    leaves = [f.action for f in flatten(face_toward(shot, "carl", "ned", mall=mall))]
    assert leaves[-1].value < 0


def test_a_turn_in_scene_md_round_trips(project):
    from an.ir.sync import ir_to_markdown, markdown_to_ir

    proj = load(project)
    proj.scene.timeline = [_shot([sequence(delay(1.0), PlayAction(target="ned", animation="turn", args={"to": "back"}))])]
    md = ir_to_markdown(proj.scene)
    assert "animation: turn" in md
    back = markdown_to_ir(md)
    assert back.timeline[0].actions == proj.scene.timeline[0].actions
    assert ir_to_markdown(markdown_to_ir(ir_to_markdown(back))) == ir_to_markdown(back)


def test_swap_poses_round_trip_through_json(project):
    desc = _desc(project / "assets" / "characters" / "ned" / "character.json")
    again = CharacterDescriptor.model_validate_json(desc.model_dump_json())
    assert again.swap_poses == desc.swap_poses


# --- 5. pixels -----------------------------------------------------------------


def _frame_of(view: str, work: Path):
    import numpy as np
    from PIL import Image

    from an.ir.schema import Meta, Resolution, SceneIR
    from an.orchestrate import render_project

    root = init(work / view)
    new_character(root / "assets" / "characters", name="g", seed="g", use_dicebear=False, hat="cap")
    proj = load(root)
    proj.scene = SceneIR(
        meta=Meta(title=view, duration=0.25, fps=12, resolution=Resolution(width=240, height=240)),
        timeline=[Shot(
            id="s1", renderer="cutout", duration=0.25,
            entities=[AssetRef(kind="character", id="g", store="characters", ref="g", stage={"at": [0, 20], "scale": 0.8})],
            actions=[SetAction(target="g", property="view", value=view, at=0.0)],
        )],
    )
    proj.mall["scenes"]["main"] = proj.scene
    mp4 = render_project(root, output_name="out")
    png = work / f"{view}.png"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf", "select=eq(n\\,0)", "-vframes", "1", str(png)],
        check=True, capture_output=True,
    )
    return np.asarray(Image.open(png).convert("RGB")).astype(int)


#: A drawn change, above the lossy mp4's per-channel noise.
STRONG_CHANGE: int = 32
#: The fewest changed pixels that count as a different picture of a 240x240
#: frame — a face hidden or a profile drawn is thousands.
MIN_CHANGED: int = 400


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_front_back_and_side_render_visibly_different(tmp_path):
    frames = {v: _frame_of(v, tmp_path) for v in ("front", "back", "side")}
    for a, b in (("front", "back"), ("front", "side"), ("side", "back")):
        changed = int((abs(frames[a] - frames[b]).max(axis=2) > STRONG_CHANGE).sum())
        assert changed > MIN_CHANGED, (a, b, changed)
