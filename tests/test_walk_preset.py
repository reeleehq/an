"""The ``walk`` motion preset (an#214), played by name, on compiled documents.

Every end-user agent that built "Bob walks in from the left" (2026-09-30)
hand-wrote a walk cycle: alternating leg rotations, a counter-swinging arm, a
body bob and a linear ``x``. ``walk`` is that cycle as one ``play``:

- the body travels from where it IS at the play's start (an#212) to ``to_x``
  (or by ``distance``) and bobs once per step;
- in a side view the legs SWING about the hip, in opposition, around the
  profile's own splay (an#203) — and the view's pose takes them back after;
- in a front view the stepping leg rises and sets down, the two alternating;
- a figure with no legs rocks and bobs instead;
- its length is ``steps × step_s``, known before it is placed (``play_extent``),
  and ``step_hz`` steps it like any tween.
"""

from __future__ import annotations

import subprocess
import tempfile
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import compile_shot
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.characters import new_character
from an.ir.compose import delay, play, sequence, set_
from an.ir.schema import AssetRef, SceneIR, Shot
from an.ir.validate import validate_semantic
from an.motion import DFLT_WALK_STRIDE, walk
from an.project import init, load


@pytest.fixture(scope="module")
def project():
    with tempfile.TemporaryDirectory() as d:
        root = init(Path(d) / "p")
        new_character(root / "assets" / "characters", name="ned", seed="ned", use_dicebear=False)
        yield root


def _shot(actions, *, entity="ned", ref=None, duration=6.0) -> Shot:
    return Shot(
        id="s",
        renderer="cutout",
        duration=duration,
        entities=[AssetRef(kind="character", id=entity, store="characters", ref=ref or entity)],
        actions=list(actions),
    )


def _compile(project, shot, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(shot, load(project).mall if project else None, **kw)


def _poses(doc, *times):
    tl = timeline_from_scene(doc)
    return [evaluate_timeline(tl, t) for t in times]


def test_a_side_view_walk_travels_bobs_and_swings_the_legs_about_the_splay(project):
    """The evidence scene's entry, as one line: off-screen left, then walk."""
    doc = _compile(
        project,
        _shot(
            [
                set_("ned", "view", "side"),
                set_("ned", "x", -600.0),
                play("ned", "walk", args={"to_x": 100.0, "steps": 4, "step_s": 0.4}),
            ]
        ),
    )
    start, mid, contact, end, after = _poses(doc, 0.0, 0.2, 0.4, 1.6, 3.0)
    splay = start[("ned/leg_l", "rotation")]
    assert splay > 0 and start[("ned/leg_r", "rotation")] == pytest.approx(-splay)
    assert start[("ned", "x")] == pytest.approx(-600.0)  # starts where the set put it
    assert end[("ned", "x")] == pytest.approx(100.0) == after[("ned", "x")]
    assert mid[("ned", "y")] < start[("ned", "y")]  # up between contacts
    # At a contact the legs are at their extremes, in opposition, about the splay.
    assert contact[("ned/leg_l", "rotation")] == pytest.approx(splay + DFLT_WALK_STRIDE)
    assert contact[("ned/leg_r", "rotation")] == pytest.approx(-splay - DFLT_WALK_STRIDE)
    # After the walk the view's pose holds the legs — no snap back to the front rest.
    assert after[("ned/leg_l", "rotation")] == pytest.approx(splay)


def test_a_turn_to_the_front_after_a_profile_walk_straightens_the_legs(project):
    """The limbs land without a settling ``set``, whose hold would outrank the
    view's pose channel and keep the profile's splay in the front view."""
    doc = _compile(
        project,
        _shot(
            [
                set_("ned", "view", "side"),
                play("ned", "walk", args={"steps": 2}),
                sequence(delay(1.5), play("ned", "turn", args={"to": "front"})),
            ]
        ),
    )
    (after,) = _poses(doc, 2.5)
    assert after[("ned/leg_l", "rotation")] == pytest.approx(0.0)
    assert after[("ned/leg_r", "rotation")] == pytest.approx(0.0)


def test_a_front_view_walk_lifts_the_legs_in_turn(project):
    doc = _compile(project, _shot([play("ned", "walk", args={"distance": 160, "steps": 2})]))
    rest, first, second = _poses(doc, 0.0, 0.2, 0.6)
    ly = rest[("ned/leg_l", "y")] if ("ned/leg_l", "y") in rest else None
    assert ly is not None
    assert first[("ned/leg_l", "y")] < ly and first[("ned/leg_r", "y")] == pytest.approx(ly)
    assert second[("ned/leg_r", "y")] < ly and second[("ned/leg_l", "y")] == pytest.approx(ly)
    assert ("ned/leg_l", "rotation") not in first


def test_the_view_is_read_off_the_timeline_and_can_be_overridden(project):
    """A turn to the side before the walk makes it a swing; ``view: front``
    overrides."""
    turned = _compile(project, _shot([set_("ned", "view", "side"), play("ned", "walk", args={"steps": 2})]))
    forced = _compile(
        project,
        _shot([set_("ned", "view", "side"), play("ned", "walk", args={"steps": 2, "view": "front"})]),
    )

    def moved(doc):
        return {
            ch.property
            for a in doc.animations.values()
            for ch in a.channels
            if ch.target == "ned/leg_l" and a.name.startswith("__tween__")
        }

    assert moved(turned) == {"rotation"} and moved(forced) == {"y"}


def test_a_legless_figure_rocks_and_bobs():
    """The procedural placeholder builds no legs: the walk degrades to the
    body's rock and bob, and the arms still swing."""
    doc = _compile(None, _shot([play("c", "walk", args={"distance": -160, "steps": 2})], entity="c", ref="nope"))
    targets = {ch.target for a in doc.animations.values() for ch in a.channels}
    assert not any("leg" in t for t in targets)
    (pose,) = _poses(doc, 0.2)
    assert pose[("c", "rotation")] != 0.0 and pose[("c/left_arm", "rotation")] != 0.0


def test_its_natural_length_is_known_before_it_is_placed(project):
    """``steps × step_s`` whatever the start: a ``sequence`` waits for it."""
    doc = _compile(
        project,
        _shot([sequence(play("ned", "walk", args={"steps": 3, "step_s": 0.5}), play("ned", "hop"))]),
    )
    hop_starts = [
        p.start_time
        for t in doc.timeline.tracks
        for p in t.clips
        if any(ch.property == "y" and ch.target == "ned" for ch in doc.animations[p.animation_id].channels)
        and p.start_time >= 1.4
    ]
    assert min(hop_starts) == pytest.approx(1.5)
    from an.ir.compose import duration_of
    from an.motion import DFLT_WALK_STEP_LENGTH, DFLT_WALK_STEP_S

    # `distance` counts the steps; an absolute `to_x` cannot, so its length is fixed.
    assert duration_of(walk("x", distance=3 * DFLT_WALK_STEP_LENGTH)) == pytest.approx(3 * DFLT_WALK_STEP_S)
    assert duration_of(walk("x", to_x=10.0)) == duration_of(walk("x", to_x=900.0, rest={"x": -900.0}))


def test_step_hz_steps_the_walk(project):
    doc = _compile(project, _shot([play("ned", "walk", args={"steps": 2})]), step_hz=12)
    legs = [
        ch
        for a in doc.animations.values()
        for ch in a.channels
        if ch.target == "ned/leg_l" and a.name.startswith("__tween__")
    ]
    assert legs and all(k.easing == "step" for ch in legs for k in ch.keyframes[:-1])


def test_validate_names_a_limb_the_rig_does_not_build(project):
    shot = _shot([play("ned", "walk", args={"legs": ["leg_l", "tail"]})])
    scene = SceneIR(meta={"title": "w", "duration": 6.0}, timeline=[shot])
    report = validate_semantic(scene, available_characters=load(project).mall["characters"])
    assert any("ned/tail" in f.description for f in report.findings), [f.description for f in report.findings]
    ok = validate_semantic(
        SceneIR(meta={"title": "w", "duration": 6.0}, timeline=[_shot([play("ned", "walk")])]),
        available_characters=load(project).mall["characters"],
    )
    assert not [f for f in ok.findings if f.severity == "error"]


# ------------------------------------------------------------------ pixels


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_a_walk_renders_moving_legs_and_travel(tmp_path):
    """Rendered: the legs at a contact are a different picture from the legs
    at rest, and the figure ends ``distance`` further right."""
    import numpy as np
    from PIL import Image

    from an.ir.schema import Meta, Resolution
    from an.orchestrate import render_project

    root = init(tmp_path / "p")
    new_character(root / "assets" / "characters", name="g", seed="g", use_dicebear=False)
    proj = load(root)
    fps, step_s = 10, 0.4
    proj.scene = SceneIR(
        meta=Meta(title="walk", duration=1.7, fps=fps, resolution=Resolution(width=240, height=240)),
        timeline=[
            Shot(
                id="s1",
                renderer="cutout",
                duration=1.7,
                entities=[AssetRef(kind="character", id="g", store="characters", ref="g", stage={"at": [-40, 20], "scale": 0.6})],
                actions=[
                    set_("g", "view", "side"),
                    sequence(delay(0.1), play("g", "walk", args={"distance": 80, "steps": 3, "step_s": step_s})),
                ],
            )
        ],
    )
    proj.mall["scenes"]["main"] = proj.scene
    mp4 = render_project(root, output_name="out")

    def frame(n):
        png = tmp_path / f"f{n}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf", f"select=eq(n\\,{n})", "-vframes", "1", str(png)],
            check=True,
            capture_output=True,
        )
        return np.asarray(Image.open(png).convert("RGB")).astype(int)

    first, contact, last = frame(0), frame(5), frame(16)  # t = 0, 0.5 (a contact), 1.6

    def centre_x(img):
        ink = (img.min(axis=2) < 200).nonzero()
        return ink[1].mean()

    legs = slice(150, 240)  # the lower part of the frame, where the legs are
    changed = int((abs(first[legs] - contact[legs]).max(axis=2) > 32).sum())
    assert changed > 150, changed
    assert 60 < centre_x(last) - centre_x(first) < 100
