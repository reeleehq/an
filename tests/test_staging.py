"""The staging check (:mod:`an.verify.staging`): ``facing_travel``, no walking backwards (an#818)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from an.genres.registry import CORE_OWNER, check_names
from an.ir.schema import Shot
from an.ir.validate import validate_semantic
from an.project import load
from an.verify.staging import art_facing_at, backward_runs

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "misc" / "bench" / "corpus"
LAMP = CORPUS / "prop_swap"  # one prop, `lamp`, with a swap set `lamp` (off/on)
AFTER_PLANE = (
    CORPUS / "after_plane"
)  # a `disc` after a 0.25-depth sky, under a 60 px pan


def _warnings(
    fixture: Path,
    tmp_path: Path,
    entity: str,
    *,
    faces=None,
    override=None,
    actions=None,
    duration=None,
    camera=None,
):
    """The ``facing_travel`` warnings of ``fixture``'s first shot, ``entity``'s
    art declaring ``faces`` (``metadata.faces``) and the entity ``override``
    (its own ``faces``); ``actions``/``duration``/``camera`` replace the shot's."""
    root = Path(shutil.copytree(fixture, tmp_path / "p"))
    if faces is not None:
        for doc_path in (root / "assets" / "props").glob("*/prop.json"):
            doc = json.loads(doc_path.read_text(encoding="utf-8"))
            doc.setdefault("metadata", {})["faces"] = faces
            doc_path.write_text(json.dumps(doc), encoding="utf-8")
    project = load(root)
    data = project.scene.timeline[0].model_dump()
    if actions is not None:
        data["actions"] = list(actions)
    if duration is not None:
        data["duration"] = duration
    if camera is not None:
        data["camera"] = camera
    if override is not None:
        for e in data["entities"]:
            if e["id"] == entity:
                e["overrides"] = {**(e.get("overrides") or {}), "faces": override}
    scene = project.scene.model_copy(update={"timeline": [Shot.model_validate(data)]})
    report = validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only={"facing_travel"},
    )
    return [f.description for f in report.findings]


def _walk(tmp_path, **kw):
    kw.setdefault("duration", 1.0)
    return _warnings(LAMP, tmp_path, "lamp", **kw)


def _slide(to, *, duration=0.6):
    """Slide the lamp to x ``to`` from the shot's start (linear)."""
    return {
        "kind": "tween",
        "target": "lamp",
        "property": "x",
        "to_value": to,
        "duration": duration,
        "easing": "linear",
    }


def _set(prop, value, at=0.0, target="lamp"):
    return {"kind": "set", "target": target, "property": prop, "value": value, "at": at}


def test_facing_travel_is_registered_under_the_core_owner():
    assert "facing_travel" in check_names(owner=CORE_OWNER)


def test_art_facing_left_that_moves_right_walks_backwards_and_says_when(tmp_path):
    """Round 7 of a cut-out film: Stu's dozy face looks left, and he crossed
    the room left to right unmirrored: a human saw him walk backwards."""
    (msg,) = _walk(tmp_path, faces="left", actions=[_slide(100.0)])
    assert "'lamp' moves right while facing left" in msg
    assert "from 0.00 s to 0.62 s" in msg  # 24 fps: it arrives on frame 15
    assert "(100 px)" in msg


def test_turned_the_way_it_goes_says_nothing(tmp_path):
    """Mirrored (flip-to-turn), the same art faces right on the set."""
    mirror = _set("scale_x", -0.55)
    assert _walk(tmp_path / "a", faces="left", actions=[mirror, _slide(100.0)]) == []
    assert _walk(tmp_path / "b", faces="right", actions=[_slide(100.0)]) == []
    assert _walk(tmp_path / "c", faces="left", actions=[_slide(-100.0)]) == []


def test_undeclared_or_opted_out_art_is_not_judged(tmp_path):
    assert _walk(tmp_path / "a", actions=[_slide(100.0)]) == []
    assert (
        _walk(tmp_path / "b", faces="left", override=False, actions=[_slide(100.0)])
        == []
    )


def test_a_short_shuffle_backwards_is_not_a_walk(tmp_path):
    assert _walk(tmp_path, faces="left", actions=[_slide(10.0, duration=0.1)]) == []


def test_a_bad_declaration_says_what_a_facing_is(tmp_path):
    (msg,) = _walk(tmp_path, faces="up", actions=[_slide(100.0)])
    assert "'up' is not a facing" in msg


def test_a_facing_by_swap_key_follows_the_key_set_in_the_shot(tmp_path):
    """The lamp faces left only once its `lamp` set is `on` (0.25 s): the
    backward stretch starts there, read off the compiled document."""
    actions = [
        _set("lamp", "on", at=0.25, target="lamp/body"),
        _slide(100.0, duration=1.0),
    ]
    (msg,) = _walk(tmp_path, faces={"lamp": {"on": "left"}}, actions=actions)
    start = float(msg.split(" from ")[1].split(" s")[0])
    assert (
        0.2 <= start <= 0.25 and "to 1.00 s" in msg
    )  # a set switches on its frame (24 fps)


def test_swap_keys_are_matched_as_strings():
    faces = {"face": {"dozy": "left"}, "view": {"side": "right"}}
    assert art_facing_at(faces, {("stu/torso/face", "face"): "dozy"}, "stu") == "left"
    assert art_facing_at(faces, {("stu/torso/head", "view"): "side"}, "stu") == "right"
    assert art_facing_at(faces, {("stu/torso/face", "face"): "smile"}, "stu") is None
    assert art_facing_at(faces, {("ned/torso/face", "face"): "dozy"}, "stu") is None
    assert art_facing_at({"n": {"1": "left"}}, {("stu", "n"): 1}, "stu") == "left"


def test_a_camera_pan_or_a_parallax_wrapper_is_not_the_entity_walking(tmp_path):
    """an#818 review: a still disc after a 0.25-depth sky rides a wrapper the
    camera drives; under a 400 px pan it travels on the set but does not walk."""
    pan = {
        "keys": [
            {
                "at": 0.0,
                "x": 0.0,
                "y": 0.0,
                "zoom": 1.0,
                "rotation": 0.0,
                "easing": "linear",
            },
            {"at": 2.0, "x": 400.0, "y": 0.0, "zoom": 1.0, "rotation": 0.0},
        ]
    }
    assert (
        _warnings(AFTER_PLANE, tmp_path, "disc", faces="left", camera=pan, duration=2.0)
        == []
    )


def test_a_squash_turn_mid_walk_is_not_walking_backwards(tmp_path):
    """an#818 review: art facing right walks left and turns (scale_x 0.55 to
    -0.55 over 0.5 s, from the start): while it is squashed it faces nowhere."""
    turn = {
        "kind": "tween",
        "target": "lamp",
        "property": "scale_x",
        "to_value": -0.55,
        "duration": 0.5,
        "easing": "linear",
    }
    actions = [_set("scale_x", 0.55), turn, _slide(-150.0, duration=1.0)]
    assert _walk(tmp_path, faces="right", actions=actions) == []


def test_unjudged_frames_inside_a_backward_walk_keep_it_one_walk_up_to_the_gap():
    ts = [i / 10 for i in range(21)]
    xs = [100.0 * t for t in ts]
    three = ["left"] * 21
    three[8:11] = [None, None, None]  # three intervals unjudged: still one stretch
    (run,) = backward_runs("stu", ts, xs, three, max_gap=3)
    assert (run.start, run.end) == (0.0, 2.0)
    five = ["left"] * 21
    five[8:13] = [None] * 5  # five: two stretches
    runs = backward_runs("stu", ts, xs, five, max_gap=3)
    assert [(r.start, r.end) for r in runs] == [(0.0, 0.8), (1.2, 2.0)]
