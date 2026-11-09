"""Contact shadows (an#519 rank 16, catalogue D2): an ellipse at each contact, offset from the light.

A member that says ``shadow: contact`` gets a synthetic ``<id>__shadow`` node
from the ``contact_shadows`` compile pass (:mod:`an.stage.shadow`), on its
surface at its contact, cast away from the scene's ``meta.light``, following
it every frame and gone while it is not supported. The fixture is
``tests/test_support.py``'s: the ``cup`` (about 30 px tall, its ``base`` named
in ``metadata.contacts``) on the floor at y 200. Compiled only; the pixels are
the core corpus's ``contact_shadow`` scene and the browser test at the end.
"""

from __future__ import annotations

import json
import warnings

import pytest

from tests.test_support import GROUND, H, W, _entity, _project, _prop, _shot, _svg

from an.ir.schema import SceneLight
from an.stage.compile import CutoutCompileWarning, compile_shot
from an.stage.serialize import to_dict
from an.stage.shadow import (
    CONTACT_SHADOW_OFFSET,
    CONTACT_SHADOW_OPACITY,
    CastShadowNotBuiltError,
    ShadowError,
    light_lean,
)
from an.stage.timeline import timeline_from_scene
from an.timing.timeline import evaluate_timeline

UPPER_LEFT = SceneLight(key="upper_left")
SHADOW = ", overrides: {shadow: contact}"
ON_FLOOR = "[{type: support, a: cup, b: ground, name: rest}]"


def _compile(project, *, light=None, shot=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(
            shot or project.scene.timeline[0],
            project.mall,
            fps=24,
            width=W,
            height=H,
            light=light,
        )


def _cup(tmp_path, *, extra=SHADOW, joints=ON_FLOOR, actions="[]", ground=GROUND):
    return _project(
        tmp_path,
        entities=_entity("cup", "cup", 0, GROUND, extra),
        shot=_shot(joints, ground=ground),
        actions=actions,
    )


def _names(doc):
    return [n.name for n in doc.scene.children]


def _node(doc, name):
    return next(n for n in doc.scene.children if n.name == name)


def _at(doc, t, name="cup__shadow"):
    """``(x, y, alpha)`` of ``name`` at ``t``: its channels, else its rest."""
    pose = evaluate_timeline(timeline_from_scene(doc), t)
    rest = _node(doc, name).transform
    return tuple(
        pose.get((name, prop), getattr(rest, prop)) for prop in ("x", "y", "alpha")
    )


# --- where it is ------------------------------------------------------------------


def test_a_supported_prop_gets_one_shadow_at_its_contact_cast_away_from_the_light(
    tmp_path,
):
    project = _cup(tmp_path)
    doc = _compile(project, light=UPPER_LEFT)
    names = _names(doc)
    assert [n for n in names if "__shadow" in n] == ["cup__shadow"]
    # painted just under its member
    assert names.index("cup__shadow") == names.index("cup") - 1
    node = _node(doc, "cup__shadow")
    assert node.visual.kind == "ellipse" and node.visual.width > node.visual.height
    x, y, alpha = _at(doc, 0.0)
    assert y == pytest.approx(GROUND)
    assert alpha == pytest.approx(CONTACT_SHADOW_OPACITY)
    # from the upper left: cast to the right of the contact (x 0), by its lean
    from an.stage.support import supports_at

    states, _ = supports_at(doc, project.scene.timeline[0], project.mall, times=[0.0])
    height = next(s.height for s in states if s.entity == "cup")
    lean = light_lean(UPPER_LEFT.vector)
    assert x == pytest.approx(lean * CONTACT_SHADOW_OFFSET * height, abs=1e-5)
    assert x > 0
    # with no light it is straight under the contact; from the right, to the left
    assert _at(_compile(project), 0.0)[0] == pytest.approx(0.0, abs=1e-6)
    assert _at(_compile(project, light=SceneLight(key="right")), 0.0)[0] < 0


def test_a_static_shadow_is_a_node_with_no_channel(tmp_path):
    doc = _compile(_cup(tmp_path), light=UPPER_LEFT)
    targets = {c.target for a in doc.animations.values() for c in a.channels}
    assert "cup__shadow" not in targets


def test_it_follows_a_tween_of_its_member(tmp_path):
    slide = "- {kind: tween, target: cup, property: x, from: 0, to: 120, duration: 1.0, easing: ease_in_out}"
    project = _cup(tmp_path, actions=slide)
    doc = _compile(project, light=UPPER_LEFT)
    offset = _at(doc, 0.0)[0]
    pose_at = lambda t: evaluate_timeline(timeline_from_scene(doc), t)  # noqa: E731
    for frame in (0, 5, 12, 18, 24, 36):
        t = frame / 24
        cup_x = pose_at(t).get(("cup", "x"), 0.0)
        x, y, alpha = _at(doc, t)
        assert x == pytest.approx(cup_x + offset, abs=0.02), frame
        assert y == pytest.approx(GROUND) and alpha == pytest.approx(
            CONTACT_SHADOW_OPACITY
        )


def test_it_is_gone_while_the_support_is_unjoined(tmp_path):
    verbs = (
        "- {kind: unjoin, joint: rest, at: 0.5}\n- {kind: join, joint: rest, at: 1.5}"
    )
    doc = _compile(_cup(tmp_path, actions=verbs))
    assert _at(doc, 0.25)[2] == pytest.approx(CONTACT_SHADOW_OPACITY)
    assert _at(doc, 1.0)[2] == 0.0
    assert _at(doc, 1.75)[2] == pytest.approx(CONTACT_SHADOW_OPACITY)


def test_it_fades_as_its_member_rises_and_is_gone_beyond_tolerance(tmp_path):
    # the cup (about 30 px) lifted 40 px off the floor, and set down again
    lift = (
        "- {kind: tween, target: cup, property: y, from: 200, to: 160, duration: 0.5, start: 0.25, easing: linear}\n"
        "- {kind: tween, target: cup, property: y, from: 160, to: 200, duration: 0.5, start: 1.25, easing: linear}"
    )
    doc = _compile(_cup(tmp_path, actions=lift))
    assert _at(doc, 0.0)[2] == pytest.approx(CONTACT_SHADOW_OPACITY)
    x, y, alpha = _at(doc, 1.0)
    assert alpha == 0.0
    assert y == pytest.approx(GROUND)  # it stays on the floor, under the cup
    # partway up: fading, not yet gone
    rising = [_at(doc, f / 24)[2] for f in range(6, 13)]
    assert any(0 < a < CONTACT_SHADOW_OPACITY for a in rising)
    assert _at(doc, 1.9)[2] == pytest.approx(CONTACT_SHADOW_OPACITY)


def test_an_inferred_stance_on_the_floor_casts_one_too(tmp_path):
    # no support declared: the cup is taken to stand on `solve: {ground}`
    doc = _compile(_cup(tmp_path, joints=""), light=UPPER_LEFT)
    assert "cup__shadow" in _names(doc)
    assert _at(doc, 0.0)[1] == pytest.approx(GROUND)


def test_the_art_may_ask_for_it_and_the_entity_may_refuse(tmp_path):
    from an.project import load

    desc = _prop(
        "mug",
        w=35,
        h=35,
        origin=False,
        metadata={"contacts": {"base": [0.5, 1.0]}, "shadow": "contact"},
    )
    for extra, expected in (("", True), (", overrides: {shadow: none}", False)):
        project = _project(
            tmp_path / str(expected),
            entities=_entity("mug", "mug", 80, GROUND, extra),
            shot=_shot(),
        )
        mug = project.root / "assets" / "props" / "mug"
        (mug / "parts").mkdir(parents=True)
        (mug / "prop.json").write_text(json.dumps(desc), encoding="utf-8")
        (mug / "parts" / "body.svg").write_text(_svg(35, 35), encoding="utf-8")
        doc = _compile(load(project.root))
        assert ("mug__shadow" in _names(doc)) is expected


def test_a_member_nothing_supports_draws_none_and_says_so(tmp_path):
    project = _cup(tmp_path, joints="", ground=None)
    with pytest.warns(CutoutCompileWarning, match="nothing supports it"):
        doc = compile_shot(
            project.scene.timeline[0], project.mall, fps=24, width=W, height=H
        )
    assert "cup__shadow" not in _names(doc)


# --- byte identity and refusals ------------------------------------------------------


def test_no_shadow_compiles_byte_identically_with_or_without_a_light(tmp_path):
    plain = _cup(tmp_path / "a", extra="")
    none = _cup(tmp_path / "b", extra=", overrides: {shadow: none}")
    base = to_dict(_compile(plain))
    assert to_dict(_compile(plain, light=UPPER_LEFT)) == base
    assert to_dict(_compile(none, light=UPPER_LEFT)) == base


def test_a_cast_shadow_is_refused_by_name(tmp_path):
    project = _cup(tmp_path, extra=", overrides: {shadow: cast}")
    with pytest.raises(CastShadowNotBuiltError, match=r"`shadow: cast`.*not built"):
        _compile(project)
    project = _cup(tmp_path / "b", extra=", overrides: {shadow: drop}")
    with pytest.raises(ShadowError, match="a shadow is one of"):
        _compile(project)


def test_the_render_hands_the_scene_light_to_the_compiler(tmp_path):
    from pathlib import Path

    from an.adapters._base import RenderContext
    from an.ir.schema import Meta, Shot
    from an.stage.compile import rendered_compile_args
    from an.stage.render import context_compile_args

    ctx = RenderContext(mall={}, work_dir=Path("."), light=UPPER_LEFT)
    assert context_compile_args(Shot(id="s"), ctx)["light"] == UPPER_LEFT
    meta = Meta(light=UPPER_LEFT)
    assert rendered_compile_args(Shot(id="s"), meta, {})["light"] == UPPER_LEFT


# --- the world's floor -------------------------------------------------------------


def test_on_a_world_floor_the_shadow_lies_on_the_projected_floor(tmp_path):
    from tests.test_world_ground import (
        G,
        _entity as _lowered_entity,
        _floor,
        _member,
        _world,
    )

    from an.stage.world import lower_scene

    listed = "- {kind: prop, id: wal, store: props, ref: walker, overrides: {shadow: contact}}\n"
    project, scene = _world(
        tmp_path,
        [_member("wal", "walker", (0.3, G, 5.0))],
        joints="[{type: support, a: wal, b: ground}]",
        entities=listed,
    )
    lowered = lower_scene(scene, project.mall)
    shot = lowered.scene.timeline[0]
    floor = _floor(_lowered_entity(lowered, "wal"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = compile_shot(shot, project.mall, fps=24, width=W, height=H)
    x, y, alpha = _at(doc, 0.0, "wal__shadow")
    assert y == pytest.approx(floor.at[1], abs=1e-4)  # the floor at the walker's depth
    assert alpha == pytest.approx(CONTACT_SHADOW_OPACITY)
    # both feet on the floor: the ellipse is centred between them, under the walker
    assert x == pytest.approx(floor.at[0], abs=2.0)


# --- in pixels ----------------------------------------------------------------------


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_the_shadow_lies_under_the_cup_cast_away_from_the_light(
    hermetic_browser, tmp_path
):
    """On a rendered frame: a grey ellipse on the floor under the cup (the
    floor is y 200, the canvas centre's 240 below it), reaching farther to the
    right of the cup's centre than to its left (the light is upper left), and
    lighter than the cup's own grey (a translucent black over white)."""
    from PIL import Image

    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer

    project = _cup(tmp_path / "p")
    shot = project.scene.timeline[0].model_copy(update={"duration": 0.25})
    result = CutoutRenderer().render(
        shot,
        RenderContext(
            mall=project.mall,
            work_dir=tmp_path / "w",
            fps=4,
            resolution=(W, H),
            strict_assets=True,
            light=UPPER_LEFT,
        ),
    )
    im = Image.open(result.frame_manifest[0]).convert("RGB")
    px = im.load()
    cx, floor = W // 2, H // 2 + int(GROUND)

    def shadow(p):  # 35% black over white: about 166; the cup is #888 (136)
        return all(150 <= c <= 185 for c in p) and max(p) - min(p) <= 6

    below = range(floor + 1, floor + 6)
    cols = [x for x in range(cx - 40, cx + 41) if any(shadow(px[x, y]) for y in below)]
    assert cols, "no shadow under the cup"
    left, right = cx - min(cols), max(cols) - cx
    assert right > left + 2, (
        f"not cast away from the light (left {left}, right {right})"
    )
    assert not any(shadow(px[x, floor - 20]) for x in range(cx - 10, cx + 11)), (
        "the shadow is painted over the cup"
    )
    assert hermetic_browser["blocked"] == [], hermetic_browser["blocked"]
