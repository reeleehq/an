"""Motion presets by name from ``scene.md``, and the scene default easing (an#166).

What is pinned here, and why:

- a ``play`` whose name the descriptor does not declare — or any ``play`` on an
  entity with no descriptor — expands to EXACTLY the ``an.motion`` macro's
  tweens at the node's built rest pose, so ``rest=`` is never needed;
- a descriptor animation of the same name WINS;
- ``an validate`` and the compiler refuse the same plays in the same words
  (one resolver, ``an.characters.play.play_problems``);
- ``play`` with ``args`` and ``meta.default_easing`` survive the
  ``scene.md`` → json → ``scene.md`` round trip;
- a default easing reaches unnamed tweens only, with the precedence
  tween > ``meta.default_easing`` > ``"ease_in_out"``, and an unset one moves
  no byte of the compiled document.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.adapters.cutout.serialize import to_dict
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.ir.compose import delay, play, sequence, tween
from an.ir.schema import AssetRef, Meta, SceneIR, Shot, TweenAction
from an.ir.sync import ir_to_markdown, markdown_to_ir, scene_from_json_doc
from an.ir.validate import validate_semantic
from an.motion import PRESETS, as_leaves, hop, nod, rest_pose, shake
from an.stores.characters import CharactersStore

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "characters"


def _char(name: str) -> AssetRef:
    return AssetRef(kind="character", id=name, store="characters", ref=name)


def _shot(actions, *, names=("charlie",), duration=3.0) -> Shot:
    return Shot(
        id="s",
        duration=duration,
        entities=[_char(n) for n in names],
        actions=list(actions),
    )


def _compile(shot, mall=None, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the stand-in-rig warning
        return compile_shot(shot, mall, **kw)


def _poses(scene, times):
    tl = timeline_from_scene(scene)
    return [evaluate_timeline(tl, t) for t in times]


def _scene(shot, **meta) -> SceneIR:
    return SceneIR(meta=Meta(title="t", duration=shot.duration, **meta), timeline=[shot])


@pytest.fixture()
def gale_store(tmp_path):
    shutil.copytree(FIXTURES / "gale", tmp_path / "gale")
    return CharactersStore(tmp_path)


TIMES = [i / 60 for i in range(181)]


# ------------------------------------------------- a preset play IS the macro


@pytest.mark.parametrize(
    "name,target,args",
    [
        ("hop", "charlie", {"height": 30.0}),
        ("nod", "charlie", {}),
        ("point", "charlie/right_arm", {"hold": 0.2}),
        ("shake", "maya", {"cycles": 2}),  # an x move on a laid-out character
        ("waddle", "maya", {"steps": 2, "travel": 40.0}),
        ("pop_in", "charlie", {}),
        ("squash_stretch", "maya", {}),
    ],
)
def test_a_preset_play_draws_exactly_the_macro_at_the_built_rest(name, target, args):
    """The macro needs ``rest=rest_pose(...)`` for a laid-out ``x``; the play
    reads the same rest off the scene it is compiling, so the two agree
    frame for frame — here in a TWO-character shot, where ``maya`` stands
    at x = 110, not 0."""
    names = ("charlie", "maya")
    via_play = _shot([sequence(delay(0.5), play(target, name, args=args))], names=names)
    node = target if name != "nod" else f"{target}/head"
    macro = PRESETS[name](target, rest=rest_pose(_shot([], names=names), node), **args)
    via_macro = _shot(as_leaves(macro, start=0.5), names=names)
    got = _poses(_compile(via_play), TIMES)
    want = _poses(_compile(via_macro), TIMES)
    assert got and got == want


def test_shake_on_the_second_character_stays_centred_on_its_rest():
    scene = _compile(_shot([play("maya", "shake")], names=("charlie", "maya")))
    values = {
        k.value
        for a in scene.animations.values()
        for c in a.channels
        if (c.target, c.property) == ("maya", "x")
        for k in c.keyframes
    }
    assert values == {110.0, 118.0, 102.0}
    assert _poses(scene, [2.0])[0][("maya", "x")] == 110.0


def test_args_reach_the_preset():
    scene = _compile(_shot([play("charlie", "hop", args={"height": 30.0, "duration": 0.6})]))
    assert evaluate_timeline(timeline_from_scene(scene), 0.3)[("charlie", "y")] == pytest.approx(-30.0)


def test_duration_stretches_and_speed_divides_the_move():
    def apex_time(action):
        scene = _compile(_shot([action]))
        ys = [(t, p.get(("charlie", "y"), 0.0)) for t, p in zip(TIMES, _poses(scene, TIMES))]
        return min(ys, key=lambda ty: ty[1])[0]

    assert apex_time(play("charlie", "hop")) == pytest.approx(0.25)  # natural 0.5 s
    assert apex_time(play("charlie", "hop", duration=1.0)) == pytest.approx(0.5)
    assert apex_time(play("charlie", "hop", speed=2.0)) == pytest.approx(0.125, abs=1 / 60)


def test_a_preset_play_is_stepped_like_the_tweens_it_is():
    """A preset expands to tweens, and tweens are what ``step_hz`` resamples —
    unlike a descriptor ``play`` clip, which is exempt by construction."""
    smooth = _compile(_shot([play("charlie", "hop")]))
    stepped = _compile(_shot([play("charlie", "hop")]), step_hz=10.0)
    assert to_dict(smooth) != to_dict(stepped)


def test_a_preset_play_works_on_a_descriptor_rig_too(gale_store):
    """``hop`` is not one of gale's animations, so it falls back to the preset;
    ``nod`` moves the descriptor rig's ``head`` node."""
    shot = _shot([play("gale", "hop"), play("gale", "nod")], names=("gale",))
    scene = _compile(shot, {"characters": gale_store})
    targets = {c.target for a in scene.animations.values() for c in a.channels}
    assert {"gale", "gale/head"} <= targets


# ------------------------------------------------------- the descriptor wins


def _add_hop_animation(store):
    d = dict(store["gale"])
    d.setdefault("animations", {})["hop"] = {
        "name": "hop",
        "duration": 0.4,
        "loop": False,
        "tracks": [
            {"target": "bone:root.y", "type": "linear", "frames": [[0.0, 0.0], [0.4, -5.0]]}
        ],
    }
    store["gale"] = d


def test_a_descriptor_animation_of_the_same_name_wins(gale_store):
    _add_hop_animation(gale_store)
    scene = _compile(_shot([play("gale", "hop")], names=("gale",)), {"characters": gale_store})
    assert [a for a in scene.animations if a.startswith("__play__")], "no descriptor clip"
    assert not [a for a in scene.animations if a.startswith("__tween__")], "the preset ran"
    report = validate_semantic(
        _scene(_shot([play("gale", "hop")], names=("gale",))), available_characters=gale_store
    )
    assert report.passed, report.findings


def test_args_on_a_descriptor_animation_are_refused_by_both(gale_store):
    _add_hop_animation(gale_store)
    shot = _shot([play("gale", "hop", args={"height": 3})], names=("gale",))
    report = validate_semantic(_scene(shot), available_characters=gale_store)
    assert any("descriptor's own animation" in f.description for f in report.findings)
    with pytest.raises(CutoutCompileError, match="descriptor's own animation"):
        _compile(shot, {"characters": gale_store})


# ------------------------------------------- one verdict, validate = compile


_REFUSALS = {
    "unknown name": (play("charlie", "moonwalk"), ["moonwalk", "no descriptor", "hop", "waddle"]),
    "unknown arg": (play("charlie", "hop", args={"heigth": 3}), ["heigth", "height"]),
    "rest is not an arg": (play("charlie", "hop", args={"rest": {"y": 0}}), ["rest", "built scene"]),
    "a value the preset refuses": (play("charlie", "shake", args={"cycles": 0}), ["cycles", "at least one"]),
    "loop": (play("charlie", "hop", loop=True), ["one-shot", "loop"]),
    "duration and speed": (play("charlie", "hop", duration=1.0, speed=2.0), ["not both"]),
    "a node the rig lacks": (play("charlie/arm_r", "point"), ["charlie/arm_r", "charlie/right_arm"]),
}


@pytest.mark.parametrize("case", sorted(_REFUSALS))
def test_validate_and_compile_refuse_the_same_preset_plays_with_the_same_words(case):
    action, words = _REFUSALS[case]
    shot = _shot([action])
    report = validate_semantic(_scene(shot), available_characters={})
    errors = [f.description for f in report.findings if f.severity == "error"]
    assert errors, case
    for word in words:
        assert any(word in e for e in errors), (case, word, errors)
    with pytest.raises(CutoutCompileError) as e:
        _compile(shot)
    for word in words:
        assert word in str(e.value), (case, word, str(e.value))


def test_an_unknown_name_lists_both_vocabularies(gale_store):
    shot = _shot([play("gale", "moonwalk")], names=("gale",))
    report = validate_semantic(_scene(shot), available_characters=gale_store)
    (error,) = [f.description for f in report.findings if f.severity == "error"]
    for word in ("blink", "idle_breath", "hop", "squash_stretch"):
        assert word in error, (word, error)


def test_a_valid_preset_play_passes_validate():
    shot = _shot([play("charlie", "nod", args={"count": 1})])
    report = validate_semantic(_scene(shot), available_characters={})
    assert report.passed, report.findings


# --------------------------------------------------------------- round trips


MD = """# T

```yaml meta
title: T
duration: 3
default_easing: linear
```

## Shot s (cutout)

```yaml shot
duration: 3
```

```yaml entities
- {kind: character, id: charlie, store: characters, ref: charlie}
```

```yaml actions
- {kind: play, target: charlie, animation: hop, args: {height: 30}, start: 0.5}
- {kind: tween, target: charlie, property: x, to: 50, duration: 1}
- {kind: tween, target: charlie, property: y, to: 5, duration: 1, easing: ease_in_out}
```
"""


def test_scene_md_to_json_to_scene_md_keeps_the_play_args_and_the_easings():
    scene = markdown_to_ir(MD)
    back = scene_from_json_doc(json.loads(scene.model_dump_json()))
    assert back == scene
    again = markdown_to_ir(ir_to_markdown(back))
    assert again == scene
    assert again.meta.default_easing == "linear"
    p, unset, pinned = [
        a.children[1] if a.kind == "sequence" else a for a in again.timeline[0].actions
    ]
    assert p.args == {"height": 30} and p.animation == "hop"
    assert "easing" not in unset.model_fields_set
    assert pinned.easing == "ease_in_out" and "easing" in pinned.model_fields_set


def test_a_bezier_default_easing_round_trips():
    scene = _scene(_shot([]), default_easing=(0.34, 1.56, 0.64, 1.0))
    again = markdown_to_ir(ir_to_markdown(scene))
    assert list(again.meta.default_easing) == [0.34, 1.56, 0.64, 1.0]


# --------------------------------------------------------- default easing


def _tween_easing(scene):
    (clip,) = [a for aid, a in scene.animations.items() if aid.startswith("__tween__")]
    return clip.channels[0].keyframes[0].easing


def test_precedence_tween_over_scene_over_builtin():
    unset = tween("charlie", "x", to=10.0, duration=1.0)
    pinned = tween("charlie", "x", to=10.0, duration=1.0, easing="ease_in_out")
    assert _tween_easing(_compile(_shot([unset]), default_easing="linear")) == "linear"
    assert _tween_easing(_compile(_shot([pinned]), default_easing="linear")) == "ease_in_out"
    assert _tween_easing(_compile(_shot([unset]))) == "ease_in_out"


def test_an_unset_default_moves_no_byte():
    """Absent ``default_easing`` must compile exactly what an explicit
    ``ease_in_out`` compiled before the field existed — and serialize away.
    (The committed corpus and example scenes' contract hashes were compared
    before/after at landing: identical.)"""
    unset = _compile(_shot([tween("charlie", "x", to=10.0, duration=1.0)]))
    pinned = _compile(
        _shot([tween("charlie", "x", to=10.0, duration=1.0, easing="ease_in_out")])
    )
    assert to_dict(unset) == to_dict(pinned)
    assert "default_easing" not in Meta().model_dump()
    assert "easing" not in tween("a", "x", to=1.0, duration=1.0).model_dump()
    assert TweenAction.model_validate({"target": "a", "property": "x", "to_value": 1}).easing == "ease_in_out"


def test_presets_keep_their_own_easings_under_a_default():
    a = _compile(_shot([play("charlie", "hop")]))
    b = _compile(_shot([play("charlie", "hop")]), default_easing="linear")
    assert to_dict(a) == to_dict(b)


def test_a_bad_default_easing_is_refused_by_both():
    report = validate_semantic(_scene(_shot([]), default_easing="bouncy"))
    assert any(f.ir_path == "meta/default_easing" for f in report.findings)
    with pytest.raises(CutoutCompileError, match="default_easing"):
        _compile(_shot([]), default_easing="bouncy")


def test_render_project_hands_the_scene_default_to_the_renderer():
    """Hop one: ``meta.default_easing`` → ``RenderContext.default_easing``."""
    import an.adapters.cutout.render as render_mod
    from an.project import init, load
    from an.render import render as render_project

    with tempfile.TemporaryDirectory() as tmp:
        root = init(Path(tmp) / "p")
        md = (root / "scene.md").read_text(encoding="utf-8").replace(
            "default_renderer: cutout", "default_renderer: cutout\ndefault_easing: linear"
        )
        md += "\n## Shot s1 (cutout)\n\n```yaml shot\nduration: 1.0\n```\n"
        (root / "scene.md").write_text(md, encoding="utf-8")
        (root / "ir" / "scene.json").unlink(missing_ok=True)
        seen: list[object] = []
        original = render_mod.CutoutRenderer.render

        def spy(self, shot, ctx):
            seen.append(ctx.default_easing)
            raise RuntimeError("stop before the browser")

        render_mod.CutoutRenderer.render = spy
        try:
            with pytest.raises(RuntimeError, match="stop before the browser"):
                render_project(load(root), auto_audio=False)
        finally:
            render_mod.CutoutRenderer.render = original
    assert seen == ["linear"], seen


def test_the_renderer_hands_the_default_to_the_compiler(monkeypatch):
    """Hop two: ``RenderContext.default_easing`` → ``compile_shot``."""
    import an.adapters.cutout.render as render_mod
    from tests._render_seam import stop_at_compile_shot

    seam = stop_at_compile_shot(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        ctx = render_mod.RenderContext(mall={}, work_dir=Path(tmp), default_easing="linear")
        with pytest.raises(seam.Stop):
            render_mod.CutoutRenderer().render(_shot([]), ctx)
    assert seam.reached and seam.kwargs.get("default_easing") == "linear", seam.kwargs


def test_the_preview_path_carries_it_too():
    import inspect

    import an.preview as preview_mod

    assert "default_easing=scene.meta.default_easing" in inspect.getsource(preview_mod)


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_a_preset_play_renders_smoke():
    """A second of preset plays through the real runtime: every node resolves
    (the runtime throws on an unknown one) and an mp4 comes out."""
    from an import build_project_mall
    from an.adapters._base import RenderContext
    from an.adapters.cutout import CutoutRenderer

    shot = _shot(
        [
            play("charlie", "hop", duration=0.4),
            sequence(delay(0.4), play("charlie", "nod", duration=0.3)),
            sequence(delay(0.7), play("charlie/right_arm", "point", args={"hold": 0.1})),
        ],
        duration=1.2,
    )
    with tempfile.TemporaryDirectory() as d:
        mall = build_project_mall(d, ensure=True)
        ctx = RenderContext(
            mall=mall, work_dir=Path(d) / "work", fps=10, resolution=(320, 240),
            default_easing="linear",
        )
        ctx.work_dir.mkdir(parents=True, exist_ok=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = CutoutRenderer().render(shot, ctx)
        assert result.mp4_path.exists() and result.mp4_path.stat().st_size > 0


# ------------------------------------------------------- review follow-ups


def test_a_bad_easing_in_args_is_refused_by_both():
    shot = _shot([play("charlie", "pop_in", args={"easing": "bogus"})])
    report = validate_semantic(_scene(shot), available_characters={})
    assert any("bogus" in f.description for f in report.findings if f.severity == "error")
    with pytest.raises(CutoutCompileError, match="bogus"):
        _compile(shot)


def test_validate_warns_when_a_preset_play_runs_past_the_shot_end():
    shot = _shot([sequence(delay(0.9), play("charlie", "hop"))], duration=1.0)
    report = validate_semantic(_scene(shot), available_characters={})
    assert any(
        f.severity == "warning" and "past the shot's end" in f.description
        for f in report.findings
    )


def test_validate_says_when_it_could_not_check_the_node(monkeypatch):
    import an.motion

    def broken(*a, **k):
        raise RuntimeError("stage exploded")

    monkeypatch.setattr(an.motion, "stage_poses", broken)
    report = validate_semantic(_scene(_shot([play("charlie", "hop")])), available_characters={})
    assert any("NOT" in f.description and "stage exploded" in f.description for f in report.findings)


def test_validate_warns_when_the_scene_default_meets_explicit_ease_in_out():
    shot = _shot([tween("charlie", "x", to=1.0, duration=1.0, easing="ease_in_out")])
    report = validate_semantic(_scene(shot, default_easing="linear"))
    assert any(f.ir_path == "meta/default_easing" and f.severity == "warning" for f in report.findings)
    quiet = validate_semantic(_scene(_shot([tween("charlie", "x", to=1.0, duration=1.0)]), default_easing="linear"))
    assert not any(f.ir_path == "meta/default_easing" for f in quiet.findings)
