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


# -----------------------------------------------------------------------------
# depth_order (an#820): a walker painted under a floor prop that stands behind it
# -----------------------------------------------------------------------------


def _depth(
    tmp_path,
    *,
    crate_y=180,
    after=True,
    held_by="world@40,{y}",
    walk=True,
    crate_first=False,
    shot="duration: 4.0\nsolve: {ground: 200}",
    extra="",
):
    """``depth_order`` warnings for the hold fixture's figure walking from x -200
    to 250 past a crate standing at ``[40, crate_y]`` (its foot; the figure's
    feet are on y 200), the crate held by ``held_by`` (``None``: staged with no
    holder) and painted after the figure when ``after``."""
    from tests._hold_fixture import make_project, scene

    held = f', overrides: {{held_by: "{held_by.format(y=crate_y)}"}}' if held_by else ""
    crate = (
        f"- {{kind: prop, id: crate, store: props, ref: crate, "
        f"stage: {{at: [40, {crate_y}]{', after: fig' if after else ''}}}{held}}}\n"
    )
    fig = "- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-200, 200]}}\n"
    move = (
        "- {kind: tween, target: fig, property: x, to: 250, duration: 3.0, easing: linear}"
        if walk
        else "- {kind: set, target: fig, property: x, value: 40, at: 0}"
    )
    entities = (crate + fig if crate_first else fig + crate) + extra
    project = make_project(
        tmp_path / "p", scene(move, entities=entities, shot=shot)
    )
    report = validate_semantic(
        project.scene, available_props=project.mall["props"], only={"depth_order"}
    )
    return [f.description for f in report.findings]


def test_depth_order_is_registered_under_the_core_owner():
    assert "depth_order" in check_names(owner=CORE_OWNER)


def test_a_walker_painted_under_a_floor_prop_upstage_of_its_feet_walks_behind_it(
    tmp_path,
):
    """Round 7 of a cut-out film: a `stage.after` meant for something else put
    Stu before the book in the paint order, and the book lies 43 px upstage of
    his feet (`world@-840,460`): he walked behind it."""
    (msg,) = _depth(tmp_path)
    assert "'fig' is painted under 'crate' from 1.25 s to 2.00 s" in msg
    assert "its foot 20 px above the feet of 'fig'" in msg
    assert "`stage.after: crate`" in msg


def test_painted_in_order_or_on_one_foot_line_says_nothing(tmp_path):
    """The walker painted over it is right; equal foot lines give no depth cue."""
    assert _depth(tmp_path / "a", after=False, crate_first=True) == []
    assert _depth(tmp_path / "b", crate_y=200) == []


def test_only_a_walker_is_judged(tmp_path):
    """Standing over a prop with no travel of its own is not walking past it."""
    assert _depth(tmp_path, walk=False) == []


def test_an_item_of_the_hold_layer_does_not_walk(tmp_path):
    """A musket let go in a cut-out film's studio fell past a sabre lying
    upstage of it: the hold layer moves an item (carried, or falling), so it is
    never a walker. The same compiled shot, the figure named an item or not."""
    from an.stage.compile import compile_as_rendered
    from an.verify.staging import depth_inversions, held_on_floor
    from tests._hold_fixture import make_project, scene

    entities = (
        "- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-200, 200]}}\n"
        "- {kind: prop, id: crate, store: props, ref: crate, stage: {at: [40, 180], after: fig}}\n"
    )
    move = "- {kind: tween, target: fig, property: x, to: 250, duration: 3.0, easing: linear}"
    project = make_project(tmp_path / "p", scene(move, entities=entities))
    shot = project.scene.timeline[0]
    doc, error = compile_as_rendered(shot, project.scene, project.mall, fps=24)
    assert error is None
    on_floor = held_on_floor({"crate": [[0.0, "world@40,180"]]})

    def judged(carried):
        return depth_inversions(
            doc, list(shot.entities), on_floor, duration=shot.duration, carried=carried
        )

    (inv,) = judged(frozenset({"crate"}))
    assert (inv.walker, inv.prop) == ("fig", "crate")
    assert judged(frozenset({"crate", "fig"})) == []


def test_only_a_prop_that_rests_on_the_floor_is_judged(tmp_path):
    """A staged item nothing says rests on the floor (a laptop on a desk, a cup
    carried without a hold) is not judged, nor is a shot with no floor."""
    assert _depth(tmp_path / "a", held_by=None) == []
    assert _depth(tmp_path / "b", shot="duration: 4.0") == []


def test_the_pairs_are_judged_whatever_the_stage_after(tmp_path):
    """Listed after the figure with no `stage.after`, the crate is painted over
    it all the same: the check reads the paint order, not the declaration."""
    (msg,) = _depth(tmp_path, after=False)
    assert "'fig' is painted under 'crate'" in msg


def test_a_prop_on_a_counter_top_is_not_on_the_floor(tmp_path):
    """an#844 review: `world@x,y` is any place of the set. A crate put on top of
    a stand (a counter) that stands on the figure's own floor line is above it,
    not behind it on the floor: the figure walking past is not judged against
    it."""
    stand = "- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [40, 200]}}\n"
    assert _depth(tmp_path / "a", crate_y=72, extra=stand) == []
    (msg,) = _depth(tmp_path / "b", crate_y=72)  # no stand under it: a far floor prop
    assert "'fig' is painted under 'crate'" in msg
