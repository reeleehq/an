"""The constraint layer in the IR and the compiler (ADR 0008, an#512): joints, the
verbs, bodies from any rig, the ``solve`` pass, and the joint checks.

The fixture is ``misc/bench/corpus/joint_pin``: a torso with a two-link arm
(an elbow hinged within [-10, 150] degrees, a ``hand`` bone as its landmark) and a
wheel with a ``grip`` bone, the hand pinned to the grip while the torso sways.
Compiled only, never rendered.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import pytest

from an.bench.core_corpus import CORE_FIXTURES, stage_copy
from an.genres.registry import CORE_OWNER, check_names
from an.ir import join, pin, pull, unjoin
from an.ir.schema import JointSpec, SceneIR, Shot, SolveSettings, gravity_vector
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.validate import validate_semantic
from an.project import load
from an.stage import compile as stage_compile
from an.stage.compile import CutoutCompileError, compile_shot
from an.stage.rig import rig_structure
from an.stage.serialize import to_dict
from an.stage.solve import SOLVE_CLIP_PREFIX, UnknownBodyError, shot_declares_solve
from an.stage.timeline import evaluate_timeline, screen_position, timeline_from_scene
from an.stage.tree import walk_children

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "misc" / "bench" / "corpus" / "joint_pin"
#: The arm's view_box -> scene px factor (345 / 400) and the hand's offset on the forearm.
K = 345.0 / 400.0
HAND = (70.0 * K, 0.0)
JOINT_CHECKS = {"unknown_body", "unreachable_pin", "joint_violation"}


def _project(
    tmp_path: Path,
    *,
    nesting: str | None = None,
    draw_order=None,
    prop=None,
    joints=None,
):
    root = stage_copy(FIXTURE, tmp_path / "p")
    desc_path = root / "assets" / "props" / (prop or "arm") / "prop.json"
    desc = json.loads(desc_path.read_text(encoding="utf-8"))
    if nesting is not None:
        desc["nesting"] = nesting
    for slot in desc["slots"]:
        slot["draw_order"] = (draw_order or {}).get(slot["name"], slot["draw_order"])
    if joints is not None:
        desc["joints"] = joints
    desc_path.write_text(json.dumps(desc), encoding="utf-8")
    return load(root)


def _shot(project, **update) -> Shot:
    data = project.scene.timeline[0].model_dump()
    data.update(update)
    return Shot.model_validate(data)


def _compile(project, shot=None, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(
            shot or project.scene.timeline[0],
            project.mall,
            fps=24,
            width=320,
            height=240,
            **kw,
        )


def _paths(doc) -> set[str]:
    return {p for p, _ in walk_children(doc.scene)}


def _fore(doc) -> str:
    return next(p for p in _paths(doc) if p.endswith("/fore"))


def _hand_and_grip(doc, t):
    pose = evaluate_timeline(timeline_from_scene(doc), t)
    hand = screen_position(doc, _fore(doc), pose=pose, point=HAND)
    return hand, screen_position(doc, "wheel/body", pose=pose)


def _times(duration, fps=24):
    return [min(duration, k / fps) for k in range(round(duration * fps) + 1)]


def _lint(project, shot, *, only=JOINT_CHECKS):
    scene = project.scene.model_copy(update={"timeline": [shot]})
    report = validate_semantic(
        scene,
        available_props=project.mall["props"],
        available_environments=project.mall["environments"],
        only=set(only),
    )
    return [(f.severity, f.description) for f in report.findings]


# -- the IR -------------------------------------------------------------------


def test_joint_specs_are_checked_where_they_are_written():
    assert (
        JointSpec(
            type="string", a="p@0.5,0", b="world@0,-200", length=150
        ).distance_mode
        == "at_most"
    )
    with pytest.raises(ValueError, match="needs `b`"):
        JointSpec(type="pin", a="p")
    with pytest.raises(ValueError, match="only a hinge"):
        JointSpec(type="pin", a="p", b="q", limits=(0, 10))
    with pytest.raises(ValueError, match="`end`"):
        JointSpec(type="contact", a="lamp@0.5,1", b="table@0,0")
    with pytest.raises(ValueError, match="gravity"):
        SolveSettings(gravity="sideways")
    assert gravity_vector("down 500") == (0.0, 500.0) and gravity_vector("none") is None


def test_nothing_new_is_written_for_a_shot_that_declares_nothing():
    shot = Shot(id="s")
    assert "joints" not in shot.model_dump() and "solve" not in shot.model_dump()
    assert "joints" not in shot.entities and not shot_declares_solve(shot)


def test_joints_and_verbs_round_trip_through_scene_md():
    shot = Shot(
        id="s1",
        duration=2.0,
        entities=[
            {
                "kind": "prop",
                "id": "p",
                "store": "props",
                "ref": "arm",
                "joints": [{"type": "hinge", "a": "fore", "limits": [-10, 150]}],
                "overrides": {"free": True},
            }
        ],
        joints=[
            {
                "type": "string",
                "a": "p/fore@hand",
                "b": "world@0,-200",
                "length": 150,
                "give": 0.001,
                "name": "s",
            }
        ],
        solve={"gravity": "down 500", "mode": "dynamic"},
        actions=[
            pin("p/fore@hand", "wheel@grip", duration=1.0),
            pull("p", [[0, 0], [10, 10]], over=1.0),
            unjoin("s", at=1.2),
            join("s", at=1.8),
        ],
    )
    scene = SceneIR(timeline=[shot])
    back = markdown_to_ir(ir_to_markdown(scene))
    assert back.timeline[0].model_dump(mode="json") == shot.model_dump(mode="json")
    assert SceneIR.model_validate_json(scene.model_dump_json()).timeline[0] == shot


# -- bodies and joints from any rig ------------------------------------------------


@pytest.mark.parametrize("nesting", ["flat", "bones"])
def test_a_rig_reads_as_bodies_hinged_at_its_bones(nesting):
    desc = json.loads(
        (FIXTURE / "assets" / "props" / "arm" / "prop.json").read_text(encoding="utf-8")
    )
    desc["nesting"] = nesting
    s = rig_structure(desc)
    assert set(s.bodies) == {"torso", "upper", "fore"} and s.roots == ("torso",)
    assert [(j.child, j.parent, j.limits) for j in s.joints] == [
        ("upper", "torso", None),
        ("fore", "upper", (-10.0, 150.0)),
    ]
    assert "hand" in s.anchors  # a bone with no part is a named point


# -- the solve pass -----------------------------------------------------------------


@pytest.mark.parametrize("nesting", ["flat", "bones"])
def test_the_hand_stays_on_the_grip_while_the_torso_sways(tmp_path, nesting):
    """The acceptance case: a two-link arm with a limited elbow, its hand pinned to
    a prop's grip, the torso tweened; the arm's channels keep the hand there."""
    project = _project(tmp_path, nesting=nesting)
    doc = _compile(project)
    solved = doc.animations[f"{SOLVE_CLIP_PREFIX}puppet"]
    emitted = {(c.target.rsplit("/", 1)[-1], c.property) for c in solved.channels}
    if nesting == "flat":
        assert emitted == {
            (part, p) for part in ("upper", "fore") for p in ("x", "y", "rotation")
        }
    else:  # a chain moves by its rotations alone
        assert emitted == {("upper", "rotation"), ("fore", "rotation")}
    for t in _times(0.5):
        hand, grip = _hand_and_grip(doc, t)
        assert math.dist(hand, grip) < 1e-3, (t, hand, grip)
    timeline = timeline_from_scene(doc)
    upper = next(p for p in _paths(doc) if p.endswith("/upper"))
    for t in _times(0.5):
        pose = evaluate_timeline(timeline, t)
        bend = math.degrees(
            pose[(_fore(doc), "rotation")]
            - (pose[(upper, "rotation")] if nesting == "flat" else 0.0)
        )
        assert -10.0 - 1e-6 <= bend <= 150.0 + 1e-6
    report = doc.meta.extensions["solve"]
    assert report["mode"] == "pose" and not report["dropped"]
    assert _lint(project, project.scene.timeline[0]) == []


def test_a_string_under_gravity_settles_in_dynamic_mode(tmp_path):
    project = _project(tmp_path)
    shot = _shot(
        project,
        duration=3.0,
        actions=[],
        joints=[
            {
                "type": "string",
                "a": "puppet/fore@hand",
                "b": "world@0,-40",
                "length": 60,
            }
        ],
        solve={"gravity": "down", "damping": 0.1},
    )
    doc = _compile(project, shot)
    assert doc.meta.extensions["solve"]["mode"] == "dynamic"
    hands = [_hand_and_grip(doc, t)[0] for t in _times(3.0)]
    anchor = (160.0, 80.0)  # world@0,-40 on a 320x240 canvas
    assert all(
        math.dist(h, anchor) <= 60.0 + 0.25 for h in hands
    )  # the string never stretches
    assert math.dist(hands[0], anchor) < 50.0 and math.dist(
        hands[-1], anchor
    ) == pytest.approx(60.0, abs=0.25)
    assert (
        max(math.dist(a, b) for a, b in zip(hands[-24:], hands[-23:])) < 0.05
    )  # settled


def test_a_pin_out_of_reach_is_refused_with_where_to_put_it(tmp_path):
    project = _project(tmp_path)
    data = project.scene.timeline[0].model_dump()
    data["entities"][1]["stage"]["at"] = [200.0, 10.0]
    shot = Shot.model_validate(data)
    findings = _lint(project, shot)
    assert [s for s, _ in findings] == ["error"]
    ((_, message),) = findings
    assert (
        "cannot be held" in message
        and "reaches 129 px" in message
        and "275 px" in message
    )
    hand, grip = _hand_and_grip(_compile(project, shot), 0.25)
    assert math.dist(hand, grip) > 100  # the arm reaches toward it, from its shoulder


def test_a_join_broken_by_authored_motion_is_a_joint_violation(tmp_path):
    project = _project(tmp_path)
    shot = _shot(
        project,
        joints=[
            {"type": "pin", "a": "puppet/fore@hand", "b": "wheel@grip", "name": "grip"}
        ],
        actions=[
            {
                "kind": "tween",
                "target": "puppet/upper",
                "property": "rotation",
                "from_value": 0.0,
                "to_value": 0.6,
                "duration": 0.5,
            },
            {
                "kind": "tween",
                "target": "puppet/fore",
                "property": "rotation",
                "from_value": 0.8,
                "to_value": 1.2,
                "duration": 0.5,
            },
        ],
    )
    findings = _lint(project, shot)
    assert len(findings) == 1 and findings[0][0] == "warning"
    assert (
        "joint 'grip'" in findings[0][1]
        and "does not hold from 0.00 s" in findings[0][1]
    )


def test_unknown_bodies_points_and_joints_are_named(tmp_path):
    project = _project(tmp_path)
    shot = _shot(
        project,
        joints=[{"type": "pin", "a": "puppet/foot", "b": "wheel@nothing"}],
        actions=[unjoin("nope")],
    )
    with pytest.raises(CutoutCompileError) as caught:
        _compile(project, shot)
    assert isinstance(caught.value, UnknownBodyError)
    messages = [m for _, m in _lint(project, shot)]
    assert any("no node 'puppet/foot'" in m for m in messages)
    assert any("'nothing' is not a bone of 'wheel'" in m for m in messages)
    assert any("'nope', which is no joint" in m for m in messages)


def test_a_pinned_prop_goes_to_the_hand_and_the_hand_stays_put(tmp_path):
    """The moved side of a verb is its point: the wheel is freed for the span and
    goes to the hand; the arm is not pulled toward it."""
    project = _project(tmp_path)
    still = _shot(project, actions=[])
    shot = _shot(project, actions=[pin("wheel", "puppet/fore@hand")])
    doc, ref = _compile(project, shot), _compile(project, still)
    for t in _times(0.5):
        hand, grip = _hand_and_grip(doc, t)
        assert math.dist(hand, grip) < 1e-3
        assert math.dist(hand, _hand_and_grip(ref, t)[0]) < 1e-3


def test_a_bone_named_on_an_entity_with_several_roots_is_a_point_of_its_part(tmp_path):
    """`puppet@fore` needs no `puppet/fore` when the rig has more than one root
    part (cutan#104: a character's `ned@hand_r`); with one root it still means
    that root, as it always did."""
    project = _project(tmp_path)
    desc_path = tmp_path / "p" / "joint_pin" / "assets" / "props" / "arm" / "prop.json"
    desc = json.loads(desc_path.read_text(encoding="utf-8"))
    desc["bones"].append({"name": "base", "x": 40.0, "y": 380.0})
    desc["slots"].append(
        {"name": "base", "bone": "base", "draw_order": 0, "attachment": "base"}
    )
    desc["skins"]["default"]["slots"]["base"] = {
        "base": {"path": "parts/torso.svg", "anchor": [0.5, 1.0]}
    }
    desc_path.write_text(json.dumps(desc), encoding="utf-8")
    project = load(tmp_path / "p" / "joint_pin")
    # no part sits on `hand`: still no body to choose
    with pytest.raises(UnknownBodyError, match="root parts"):
        _compile(project, _shot(project, actions=[pin("puppet@hand", "wheel@grip")]))
    named = _compile(project, _shot(project, actions=[pin("puppet@fore", "wheel@grip")]))
    on_part = _compile(
        project, _shot(project, actions=[pin("puppet/fore@fore", "wheel@grip")])
    )
    assert {k: v.model_dump() for k, v in named.animations.items()} == {
        k: v.model_dump() for k, v in on_part.animations.items()
    }
    report = named.meta.extensions["solve"]
    assert report["dropped"] == on_part.meta.extensions["solve"]["dropped"]
    assert report["joints"][-1]["bodies"] == "puppet@fore — wheel@grip"  # as written


def test_a_rejoin_across_a_gap_is_a_snap(tmp_path):
    project = _project(tmp_path)
    shot = _shot(
        project,
        duration=1.0,
        joints=[
            {"type": "pin", "a": "puppet/fore@hand", "b": "wheel@grip", "name": "grip"}
        ],
        solve={"gravity": "down"},
        actions=[unjoin("grip", at=0.1), join("grip", at=0.6)],
    )
    doc = _compile(project, shot)
    hand, grip = _hand_and_grip(doc, 0.5)
    assert math.dist(hand, grip) > 2.0  # it fell while let go
    assert math.dist(*_hand_and_grip(doc, 0.8)) < 0.25  # and was caught again
    (finding,) = _lint(project, shot)
    assert finding[0] == "warning" and "rejoined at 0.62 s" in finding[1]


def test_the_solve_honours_the_step_grid(tmp_path):
    project = _project(tmp_path)
    doc = _compile(project, step_hz=12.0)
    keys = doc.animations[f"{SOLVE_CLIP_PREFIX}puppet"].channels[0].keyframes
    assert [round(k.time, 6) for k in keys] == [round(i / 12, 6) for i in range(7)]
    assert {k.easing for k in keys} == {"step"}


def test_the_solve_is_deterministic(tmp_path):
    project = _project(tmp_path)
    assert to_dict(_compile(project)) == to_dict(_compile(project))


def test_the_joint_checks_are_core_checks():
    assert JOINT_CHECKS <= set(check_names(owner=CORE_OWNER))


# -- nothing declared, nothing changed ------------------------------------------------


@pytest.mark.parametrize("name", sorted(CORE_FIXTURES))
def test_the_core_corpus_compiles_byte_identically_without_the_pass(
    tmp_path, name, monkeypatch
):
    project = load(stage_copy(ROOT / CORE_FIXTURES[name].path, tmp_path / name))
    res = project.scene.meta.resolution

    def compiled():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return [
                to_dict(
                    compile_shot(
                        shot,
                        project.mall,
                        fps=project.scene.meta.fps,
                        width=res.width,
                        height=res.height,
                    )
                )
                for shot in project.scene.timeline
                if shot.renderer in ("stage", "cutout")
            ]

    with_pass = compiled()
    monkeypatch.setattr(
        stage_compile,
        "STAGE_COMPILE_PASSES",
        tuple(p for p in stage_compile.STAGE_COMPILE_PASSES if p.name != "solve"),
    )
    assert compiled() == with_pass


# -- regressions found in review ------------------------------------------------------


def test_a_chain_drawn_child_first_still_follows_its_parent(tmp_path):
    """A back arm drawn behind its torso: bodies are solved and read parents first."""
    project = _project(
        tmp_path, nesting="bones", draw_order={"torso": 2, "upper": 1, "fore": 0}
    )
    doc = _compile(project)
    assert max(math.dist(*_hand_and_grip(doc, t)) for t in _times(0.5)) < 1e-3


@pytest.mark.parametrize(
    "extra, wheel_at",
    [
        (
            [{"kind": "set", "target": "puppet", "property": "scale_x", "value": -1.0}],
            [-210.0, 10.0],
        ),
        (
            [
                {
                    "kind": "tween",
                    "target": "puppet",
                    "property": p,
                    "from_value": 1.0,
                    "to_value": 1.3,
                    "duration": 0.5,
                }
                for p in ("scale_x", "scale_y")
            ],
            [10.0, 10.0],
        ),
    ],
    ids=["mirrored", "scaled"],
)
def test_an_authored_mirror_or_scale_is_solved_at_the_frames_geometry(
    tmp_path, extra, wheel_at
):
    project = _project(tmp_path)
    data = project.scene.timeline[0].model_dump()
    data["entities"][1]["stage"]["at"] = wheel_at
    data["actions"] = data["actions"] + extra
    shot = Shot.model_validate(data)
    doc = _compile(project, shot)
    assert not doc.meta.extensions["solve"]["dropped"]
    assert max(math.dist(*_hand_and_grip(doc, t)) for t in _times(0.5)) < 1e-3
    assert _lint(project, shot) == []


def test_a_pull_reaches_what_it_can_and_is_never_a_violation(tmp_path):
    project = _project(tmp_path)
    reachable = _shot(project, actions=[pull("puppet/fore@hand", "wheel@grip")])
    doc = _compile(project, reachable)
    assert (
        doc.meta.extensions["solve"]["mode"] == "pose"
    )  # a pull is a goal, not a string
    assert max(math.dist(*_hand_and_grip(doc, t)) for t in _times(0.5)) < 1e-3
    far = _shot(project, actions=[pull("puppet/fore@hand", "world@300,-300")])
    assert _lint(project, reachable) == [] and _lint(project, far) == []


def test_a_pin_held_off_by_an_authored_channel_is_not_called_out_of_reach(tmp_path):
    project = _project(tmp_path)
    fight = {
        "kind": "sequence",
        "children": [
            {"kind": "delay", "duration": 0.2},
            {
                "kind": "tween",
                "target": "puppet/fore",
                "property": "rotation",
                "from_value": 0.5,
                "to_value": 1.0,
                "duration": 0.2,
            },
        ],
    }
    shot = _shot(
        project,
        actions=list(project.scene.timeline[0].model_dump()["actions"]) + [fight],
    )
    findings = _lint(project, shot)
    errors = [m for sev, m in findings if sev == "error"]
    assert len(errors) == 1 and "within reach" in errors[0]
    assert not [
        m for sev, m in findings if sev == "info"
    ]  # the held tween is not "replaced"


def test_a_descriptor_joint_that_does_not_read_is_named_not_raised(tmp_path):
    project = _project(tmp_path, prop="wheel", joints=[{"type": "pin", "a": "@0.5,0"}])
    with pytest.raises(UnknownBodyError):
        _compile(project)
    findings = _lint(project, project.scene.timeline[0])
    assert [s for s, _ in findings] == ["error"] and "does not read" in findings[0][1]


def test_a_shot_that_declares_nothing_reads_no_other_store_entry():
    """The pass's gate reads only rig descriptors (which the compile reads anyway)."""
    from an.stage.solve import declarations

    class Untouchable(dict):
        def __contains__(self, key):
            raise AssertionError("read a voice entry")

    shot = Shot(
        id="s",
        entities=[{"kind": "voice", "id": "n", "store": "voices", "ref": "narrator"}],
    )
    assert declarations(shot, {"voices": Untouchable()}).empty


@pytest.mark.parametrize("ends", ["pin span", "unjoin"])
def test_a_part_a_joint_let_go_of_stays_where_it_was_left(tmp_path, ends):
    """Pose mode keeps a part nothing acts on at its document angle (a
    passenger), but a part a joint or a verb drives is never one: when the pin's
    span ends (or the joint is unjoined) the arm stays where it was, it does not
    snap back to the angle the document gives it (a 101 px jump in one frame
    before this was caught in review, an#502)."""
    project = _project(tmp_path)
    sway = {
        "kind": "tween",
        "target": "puppet/torso",
        "property": "rotation",
        "from_value": 0.0,
        "to_value": 0.6,
        "duration": 1.0,
        "easing": "linear",
    }
    if ends == "pin span":
        shot = _shot(
            project,
            duration=1.0,
            actions=[sway, pin("puppet/fore@hand", "wheel@grip", duration=0.4)],
        )
    else:
        shot = _shot(
            project,
            duration=1.0,
            joints=[
                {
                    "type": "pin",
                    "a": "puppet/fore@hand",
                    "b": "wheel@grip",
                    "name": "grip",
                }
            ],
            solve={"mode": "pose"},
            actions=[sway, unjoin("grip", at=0.4)],
        )
    doc = _compile(project, shot)
    hands = [_hand_and_grip(doc, t)[0] for t in _times(1.0)]
    assert max(math.dist(a, b) for a, b in zip(hands, hands[1:])) < 5.0
