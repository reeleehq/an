"""Motion presets (`an.motion`): authoring macros that expand to plain tweens.

What is pinned here, and why:

- every preset compiles on BOTH rigs (the procedural placeholder and a
  descriptor rig), and every channel it emits targets a node the built scene
  carries — the runtime throws on an unknown node, and no browser runs here,
  so the node-path check is the non-browser stand-in for that throw;
- evaluated through the Python spec evaluator, a preset reaches its apex and
  comes back to the node's REST, including a rest that is not the identity
  (a laid-out ``x``, a stage scale) when ``rest_pose`` supplies it;
- ``as_leaves`` survives the ``scene.md`` round trip, which composition trees
  do not.
"""

from __future__ import annotations

import shutil
import tempfile
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.ir.compose import duration_of, flatten, sequence
from an.ir.compose import delay, set_
from an.ir.schema import AssetRef, Meta, SceneIR, SetAction, Shot, StagePlacement, TweenAction
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.motion import (
    IDENTITY_POSE,
    PRESETS,
    as_leaves,
    hop,
    nod,
    point,
    pop_in,
    rest_pose,
    shake,
    slide_in,
    slide_out,
    speech_pulse,
    crawl,
    squash_stretch,
    turn,
    waddle,
    walk,
)
from an.stores.characters import CharactersStore

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "characters"


def _char(name: str, **kw) -> AssetRef:
    return AssetRef(kind="character", id=name, store="characters", ref=name, **kw)


def _shot(actions, *, entities=None, duration=4.0) -> Shot:
    return Shot(
        id="s",
        duration=duration,
        entities=entities or [_char("charlie")],
        actions=list(actions),
    )


def _compile(shot, mall=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the stand-in-rig warning
        return compile_shot(shot, mall)


def _node_paths(scene) -> set[str]:
    out: set[str] = set()

    def walk(node, prefix):
        path = f"{prefix}/{node.name}" if prefix else node.name
        if prefix or node.name != "root":
            out.add(path)
        for child in node.children:
            walk(child, path if (prefix or node.name != "root") else "")

    walk(scene.scene, "")
    return out


def _pose_at(scene, t):
    return evaluate_timeline(timeline_from_scene(scene), t)


@pytest.fixture()
def gale_store(tmp_path):
    shutil.copytree(FIXTURES / "gale", tmp_path / "gale")
    return CharactersStore(tmp_path)


# One call per preset, per rig: whole-body moves on the entity, part moves on
# the part each rig actually builds.
PROCEDURAL_CALLS = {
    "pop_in": lambda: pop_in("charlie"),
    "hop": lambda: hop("charlie"),
    "shake": lambda: shake("charlie"),
    "nod": lambda: nod("charlie"),
    "point": lambda: point("charlie/right_arm"),
    "slide_in": lambda: slide_in("charlie"),
    "slide_out": lambda: slide_out("charlie"),
    "squash_stretch": lambda: squash_stretch("charlie"),
    "waddle": lambda: waddle("charlie", travel=80.0),
    # The placeholder builds no legs (an#214): the legless walk, arms named.
    "walk": lambda: walk("charlie", legs=(), arms=("left_arm", "right_arm")),
    # The speech aspect's requirement-free last link (an#248): the head pulses.
    "speech_pulse": lambda: speech_pulse("charlie", beats=(0.0, 0.3)),
    # an#314: a plane move works on any entity, a rig's included.
    "crawl": lambda: crawl("charlie", distance=300.0, duration=2.0),
}
#: Presets that swap a SET, which only a descriptor declares (an#197): `turn`
#: swaps the view. The procedural rig refuses them loudly (below); on `gale`,
#: `turn` swaps the fixture's own `body_facing` set — the whole-character swap
#: is set-agnostic, and a view set is only the factory's convention.
DESCRIPTOR_ONLY: frozenset[str] = frozenset({"turn"})
DESCRIPTOR_CALLS = {
    **{k: (lambda f=f: f("gale")) for k, f in PRESETS.items() if k not in ("point", "turn")},
    "point": lambda: point("gale/arm_r", angle=1.3),
    "turn": lambda: turn("gale", to="left", view_set="body_facing"),
}
PROCEDURAL_PRESETS = sorted(set(PRESETS) - DESCRIPTOR_ONLY)


def test_every_preset_is_covered_on_both_rigs():
    assert set(PROCEDURAL_CALLS) | DESCRIPTOR_ONLY == set(PRESETS) == set(DESCRIPTOR_CALLS)


@pytest.mark.genre("cutout_animation")
def test_a_swapping_preset_on_the_procedural_rig_is_refused_by_name():
    from an.adapters.cutout.compile import CutoutCompileError
    from cutan.characters.registration import PlayAction

    with pytest.raises(CutoutCompileError, match="'view'"):
        _compile(_shot([PlayAction(target="charlie", animation="turn")]))


@pytest.mark.genre("cutout_animation")
@pytest.mark.parametrize("name", PROCEDURAL_PRESETS)
def test_preset_targets_nodes_the_procedural_rig_builds(name):
    action = PROCEDURAL_CALLS[name]()
    scene = _compile(_shot([action]))
    paths = _node_paths(scene)
    targets = {c.target for a in scene.animations.values() for c in a.channels}
    assert targets and targets <= paths, targets - paths


@pytest.mark.genre("cutout_animation")
@pytest.mark.parametrize("name", sorted(PRESETS))
def test_preset_targets_nodes_a_descriptor_rig_builds(name, gale_store):
    action = DESCRIPTOR_CALLS[name]()
    scene = _compile(
        _shot([action], entities=[_char("gale")]), {"characters": gale_store}
    )
    paths = _node_paths(scene)
    targets = {c.target for a in scene.animations.values() for c in a.channels}
    assert targets and targets <= paths, targets - paths


@pytest.mark.genre("cutout_animation")
def test_the_rigs_name_their_arms_differently():
    """Why `point` takes the arm node: the procedural rig has no `arm_r`, and
    the compiler refuses it as an unknown node, naming the one it has (an#193;
    before, the runtime threw from inside the browser)."""
    with pytest.raises(CutoutCompileError, match=r"'charlie/arm_r' is not a node"):
        _compile(_shot([point("charlie/arm_r")]))
    scene = _compile(_shot([point("charlie/right_arm")]))
    assert "charlie/arm_r" not in _node_paths(scene)
    assert "charlie/right_arm" in _node_paths(scene)


@pytest.mark.genre("cutout_animation")
@pytest.mark.parametrize("name", sorted(set(PROCEDURAL_PRESETS) - {"slide_out", "crawl"}))
def test_preset_ends_at_rest(name):
    """Every preset but the exit and the crawl (which leaves its plane tilted
    and its content up the plane, an#314) leaves each property it touched at
    REST."""
    action = PROCEDURAL_CALLS[name]()
    if name == "waddle":  # travel moves x on purpose
        action = waddle("charlie")
    scene = _compile(_shot([action]))
    end = duration_of(action)
    pose = _pose_at(scene, end)
    assert pose, "the preset animated nothing"
    for (target, prop), value in pose.items():
        assert value == pytest.approx(IDENTITY_POSE[prop], abs=1e-9), (target, prop)


def _landed(scene, *, fps, duration):
    """What the runtime SHOWS after the last frame: poses sampled at ``i / fps``
    and HELD (the runtime keeps the last pose it applied), not the pose at the
    exact clip end, which no frame need land on."""
    tl = timeline_from_scene(scene)
    state: dict = {}
    for i in range(int(duration * fps) + 1):
        state.update(evaluate_timeline(tl, i / fps))
    return state


@pytest.mark.genre("cutout_animation")
@pytest.mark.parametrize("fps,step_hz", [(30, None), (24, None), (30, 10.0), (30, 15.0)])
@pytest.mark.parametrize("name", PROCEDURAL_PRESETS)
def test_preset_lands_on_its_end_value_at_frame_times(name, fps, step_hz):
    """The review's catch: a 0.36 s squash at 30 fps used to be left at
    scale 0.96/1.04, and a shake under step_hz 10 stranded 8 px off rest,
    because the last frame inside the move was not its end. The settling
    `set` each preset ends with is what lands it."""
    action = PROCEDURAL_CALLS[name]()
    ends = {}
    for f in flatten(action):
        if isinstance(f.action, TweenAction):
            key = (f.action.target, f.action.property)
            if key not in ends or f.end >= ends[key][0]:
                ends[key] = (f.end, f.action.to_value)
    shot = _shot([action], duration=duration_of(action) + 0.5)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scene = compile_shot(shot, fps=fps, step_hz=step_hz)
    shown = _landed(scene, fps=fps, duration=shot.duration)
    for key, (_, value) in ends.items():
        assert shown[key] == pytest.approx(value, abs=1e-9), key


@pytest.mark.genre("cutout_animation")
@pytest.mark.parametrize("fps,step_hz", [(30, None), (24, None), (30, 10.0)])
def test_turn_lands_mirrored_on_the_swapped_key(fps, step_hz, gale_store):
    """`turn` on a descriptor rig: `scale_x` lands on minus the rest for a left
    facing, and the torso shows the swapped key, at frame times (an#197)."""
    action = turn("gale", to="left", direction="left", view_set="body_facing")
    shot = _shot([action], entities=[_char("gale")], duration=duration_of(action) + 0.5)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scene = compile_shot(shot, {"characters": gale_store}, fps=fps, step_hz=step_hz)
    shown = _landed(scene, fps=fps, duration=shot.duration)
    assert shown[("gale", "scale_x")] == pytest.approx(-1.0, abs=1e-9)
    assert shown[("gale/torso", "body_facing")] == "left"


@pytest.mark.genre("cutout_animation")
def test_hop_reaches_its_apex_mid_move():
    scene = _compile(_shot([hop("charlie", height=30.0, duration=0.6)]))
    assert _pose_at(scene, 0.3)[("charlie", "y")] == pytest.approx(-30.0)


@pytest.mark.genre("cutout_animation")
def test_pop_in_overshoots_and_settles():
    scene = _compile(_shot([pop_in("charlie", duration=1.0)]))
    peak = max(_pose_at(scene, i / 100)[("charlie", "scale_x")] for i in range(101))
    assert peak > 1.05
    assert _pose_at(scene, 1.0)[("charlie", "scale_x")] == pytest.approx(1.0)


@pytest.mark.genre("cutout_animation")
def test_rest_pose_reads_the_compilers_layout_and_placement():
    two = [_char("a"), _char("b", stage=StagePlacement(at=(300.0, 40.0), scale=2.0))]
    shot = _shot([], entities=two)
    assert rest_pose(shot, "a")["x"] == -110.0
    placed = rest_pose(shot, "b")
    assert (placed["x"], placed["y"], placed["scale_x"]) == (300.0, 40.0, 2.0)
    with pytest.raises(KeyError, match="right_arm"):
        rest_pose(shot, "a/arm_r")


@pytest.mark.genre("cutout_animation")
def test_a_move_on_x_stays_centred_on_the_laid_out_rest():
    """The trap `rest` exists for: with two characters `a` rests at x=-110,
    and a shake around the identity would teleport it to the centre."""
    entities = [_char("a"), _char("b")]
    base = _shot([], entities=entities)
    action = shake("a", amplitude=5.0, rest=rest_pose(base, "a"))
    scene = _compile(_shot([action], entities=entities))
    xs = [kf.value for a in scene.animations.values() for c in a.channels
          if c.property == "x" for kf in c.keyframes]
    assert min(xs) == pytest.approx(-115.0) and max(xs) == pytest.approx(-105.0)
    assert _pose_at(scene, duration_of(action))[("a", "x")] == pytest.approx(-110.0)


@pytest.mark.genre("cutout_animation")
def test_scale_presets_respect_a_stage_scale():
    entities = [_char("c", stage=StagePlacement(scale=2.0))]
    rest = rest_pose(_shot([], entities=entities), "c")
    scene = _compile(_shot([pop_in("c", rest=rest)], entities=entities))
    assert _pose_at(scene, 0.45)[("c", "scale_y")] == pytest.approx(2.0)


def test_presets_chain_without_a_jump():
    """Each segment names its `from`, equal to the previous segment's `to`."""
    leaves = flatten(sequence(hop("c"), squash_stretch("c"), waddle("c", steps=2)))
    last: dict[tuple[str, str], float] = {}
    tweens = [f for f in leaves if isinstance(f.action, TweenAction)]
    for f in sorted(tweens, key=lambda f: f.start):
        key = (f.action.target, f.action.property)
        if key in last:
            assert f.action.from_value == pytest.approx(last[key]), key
        last[key] = f.action.to_value


@pytest.mark.parametrize("bad", [lambda: shake("c", cycles=0), lambda: nod("c", count=0),
                                 lambda: waddle("c", steps=0), lambda: slide_in("c", from_side="up"),
                                 lambda: shake("c", duration=-1.0), lambda: hop("c", duration=0.0),
                                 lambda: waddle("c", step_duration=0.0), lambda: point("c/a", hold=-1.0)])
def test_nonsense_parameters_raise(bad):
    with pytest.raises(ValueError):
        bad()


@pytest.mark.genre("cutout_animation")
def test_as_leaves_survives_the_scene_md_round_trip():
    action = sequence(pop_in("charlie"), hop("charlie"), shake("charlie"))
    shot = _shot(as_leaves(action, start=0.5))
    scene = SceneIR(meta=Meta(title="t"), timeline=[shot])
    back = markdown_to_ir(ir_to_markdown(scene)).timeline[0]
    a = _compile(shot).model_dump(mode="json")
    b = _compile(back).model_dump(mode="json")
    assert a["animations"] == b["animations"]
    assert a["timeline"] == b["timeline"]


def test_as_leaves_keeps_a_set_at_its_absolute_time():
    leaves = as_leaves(sequence(delay(1.0), set_("charlie", "alpha", 0.5, at=0.25)), start=0.5)
    (leaf,) = leaves
    assert isinstance(leaf, SetAction) and leaf.at == pytest.approx(1.75)
    scene = SceneIR(meta=Meta(title="t"), timeline=[_shot(leaves)])
    (back,) = markdown_to_ir(ir_to_markdown(scene)).timeline[0].actions
    assert back.at == pytest.approx(1.75)


def test_a_composition_tree_survives_scene_md_verbatim():
    """It used not to (the writer dropped composites, and `as_leaves` was the
    workaround). Since an#241's review round the writer keeps an action it has
    no short form for VERBATIM, so a preset's tree round-trips as is;
    `as_leaves` still gives the short, hand-editable form."""
    scene = SceneIR(meta=Meta(title="t"), timeline=[_shot([hop("charlie")])])
    back = markdown_to_ir(ir_to_markdown(scene)).timeline[0]
    assert back.actions == scene.timeline[0].actions


@pytest.mark.genre("cutout_animation")
@pytest.mark.browser
@pytest.mark.ffmpeg
def test_presets_render_smoke():
    """A second of presets through the real runtime: every target resolves
    (the runtime throws on an unknown node) and an mp4 comes out."""
    from an import build_project_mall
    from an.adapters._base import RenderContext
    from an.adapters.cutout import CutoutRenderer

    shot = _shot([sequence(pop_in("charlie", duration=0.3), hop("charlie", duration=0.3),
                           nod("charlie", duration=0.2), point("charlie/right_arm", hold=0.1))],
                 duration=1.2)
    with tempfile.TemporaryDirectory() as d:
        mall = build_project_mall(d, ensure=True)
        ctx = RenderContext(mall=mall, work_dir=Path(d) / "work", fps=10, resolution=(320, 240))
        ctx.work_dir.mkdir(parents=True, exist_ok=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = CutoutRenderer().render(shot, ctx)
        assert result.mp4_path.exists() and result.mp4_path.stat().st_size > 0
