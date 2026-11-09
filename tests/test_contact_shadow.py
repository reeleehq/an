"""Contact shadows (an#519 rank 16, catalogue D2): one ellipse per support, spanning its contacts, offset from the light.

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


def _paint_order(doc, t):
    """The scene root's children in the order they are painted at ``t``."""
    from an.base import Z_INDEX_PROPERTY

    pose = evaluate_timeline(timeline_from_scene(doc), t)
    z = {
        n.name: (pose.get((n.name, Z_INDEX_PROPERTY), n.z_index), i)
        for i, n in enumerate(doc.scene.children)
    }
    return sorted(z, key=z.get)


@pytest.mark.parametrize("shadowed", [("a",), ("b",), ("a", "b")])
def test_a_shadow_rides_its_member_when_the_world_reorders_it_by_depth(
    tmp_path, shadowed
):
    """an#634 review: ``a`` walks away from the camera (depth 3 to 8) past
    ``b`` (depth 5). The world keys both by depth; each shadow rides its
    member's keys just behind it, so the pair is still reordered (both get
    ``z_index`` keys: an unkeyed shadow between them used to end the run) and
    every shadow is painted right under its member at every frame."""
    from tests.test_world_ground import G, _member, _world

    from an.base import Z_INDEX_PROPERTY
    from an.stage.world import lower_scene

    def listed(eid):
        extra = SHADOW if eid in shadowed else ""
        return f"- {{kind: prop, id: {eid}, store: props, ref: walker{extra}}}\n"

    supports = ", ".join(f"{{type: support, a: {e}, b: ground}}" for e in shadowed)
    project, scene = _world(
        tmp_path,
        [_member("a", "walker", (-0.3, G, 3.0)), _member("b", "walker", (0.3, G, 5.0))],
        joints=f"[{supports}]",
        entities=listed("a") + listed("b"),
        actions="- {kind: tween, target: a, property: at_z, from: 3.0, to: 8.0, duration: 2.0, easing: linear}",
    )
    shot = lower_scene(scene, project.mall).scene.timeline[0]
    doc = _compile(project, shot=shot)
    keyed = {
        c.target
        for clip in doc.animations.values()
        for c in clip.channels
        if c.property == Z_INDEX_PROPERTY
    }
    assert {"a", "b"} <= keyed
    orders = set()
    for frame in range(48):
        order = _paint_order(doc, frame / 24 + 0.01)
        for eid in shadowed:
            assert order.index(f"{eid}__shadow") == order.index(eid) - 1, (frame, order)
        orders.add(order.index("a") < order.index("b"))
    assert orders == {True, False}  # they did swap


def test_the_world_paint_keys_of_a_shadow_ride_behind_its_member():
    from an.base import paint_key_rank
    from an.stage.shadow import shadow_paint_keys

    keys = {"cup": [(0.0, [1.0, -5.0, 0.0])], "rider": [(0.0, [1.0, -5.0, 0.0, -1, 0])]}
    names = ["cup__shadow", "cup__shadow_1", "rider", "cup"]
    mine = shadow_paint_keys(names, keys)
    ranks = [paint_key_rank(({**keys, **mine})[n][0][1]) for n in names]
    assert ranks == sorted(ranks)  # both shadows, then the rider, then the cup


def test_a_tilted_surface_tilts_its_shadow(tmp_path):
    """A cup on ``crate@surface``, the crate turned: the shadow turns with the
    surface (its ``rotation`` the crate's, sign included) and lies on the
    surface's line, computed here from the crate's own geometry."""
    import math

    from tests._hold_fixture import CRATE_SURFACE, K

    top = GROUND - CRATE_SURFACE * K
    for turn in (0.2, -0.2):
        project = _project(
            tmp_path / str(turn),
            entities=_entity("crate", "crate", 160, GROUND)
            + _entity("cup", "cup", 160, top, SHADOW),
            shot=_shot("[{type: support, a: cup, b: crate@surface}]"),
            actions=f"- {{kind: set, target: crate, property: rotation, value: {turn}, at: 0}}",
        )
        node = _node(_compile(project), "cup__shadow")
        assert node.transform.rotation == pytest.approx(turn, abs=1e-6)
        c, s = math.cos(turn), math.sin(turn)
        (ax, ay), (bx, by) = [
            (160 + c * dx - s * dy, GROUND + s * dx + c * dy)
            for dx, dy in ((-50 * K, -CRATE_SURFACE * K), (50 * K, -CRATE_SURFACE * K))
        ]
        x, y = node.transform.x, node.transform.y
        off_line = ((x - ax) * (by - ay) - (y - ay) * (bx - ax)) / math.hypot(
            bx - ax, by - ay
        )
        assert off_line == pytest.approx(0.0, abs=1e-4), turn
        assert ax < x < bx


def test_a_support_with_two_contacts_casts_one_ellipse_spanning_them(tmp_path):
    from an.project import load
    from an.stage.shadow import CONTACT_SHADOW_MARGIN
    from an.stage.support import supports_at

    desc = _prop(
        "bench",
        w=80,
        h=20,
        origin=False,
        metadata={"contacts": {"left": [0.0, 1.0], "right": [1.0, 1.0]}},
    )
    project = _project(
        tmp_path,
        entities=_entity("bench", "bench", 30, GROUND, SHADOW),
        shot=_shot("[{type: support, a: bench, b: ground}]"),
    )
    bench = project.root / "assets" / "props" / "bench"
    (bench / "parts").mkdir(parents=True)
    (bench / "prop.json").write_text(json.dumps(desc), encoding="utf-8")
    (bench / "parts" / "body.svg").write_text(_svg(80, 20), encoding="utf-8")
    project = load(project.root)
    doc = _compile(project)
    assert [n for n in _names(doc) if "__shadow" in n] == ["bench__shadow"]
    (state,) = supports_at(doc, project.scene.timeline[0], project.mall, times=[0.0])[0]
    left, right = sorted(c.at[0] for c in state.contacts)
    assert right - left > 50  # two contacts, far apart
    node = _node(doc, "bench__shadow")
    assert node.transform.x == pytest.approx((left + right) / 2, abs=1e-5)
    assert (
        node.visual.width >= right - left + CONTACT_SHADOW_MARGIN * state.height - 1e-6
    )


# --- overrides and clip ids -----------------------------------------------------------


def test_a_path_entity_may_ask_for_a_shadow(tmp_path):
    """``shadow`` is a core override key (:data:`an.base.CORE_OVERRIDE_KEYS`): a
    stroked path's resolver does not refuse it as a field of its document, and
    the path standing on the floor gets its shadow."""
    from an.paths import PathDescriptor

    project = _project(
        tmp_path,
        entities=_entity("rope", "rope", 0, GROUND, SHADOW),
        shot=_shot("[{type: support, a: rope, b: ground}]"),
    )
    project.mall["props"]["rope"] = PathDescriptor(
        name="rope", points=[(-40, 0), (0, -30), (40, 0)]
    ).model_dump(mode="json")
    doc = _compile(project)
    assert {"rope", "rope__shadow"} <= set(_names(doc))


def test_a_taken_clip_id_gets_a_fresh_one():
    from types import SimpleNamespace as NS

    from an.stage.shadow import SHADOW_CLIP_PREFIX, _add_shadow_clip, _Shadow

    moving = _Shadow("cup", "cup__shadow", {"x": [0.0, 5.0], **{
        p: [1.0, 1.0] for p in ("y", "rotation", "scale_x", "scale_y", "alpha")
    }}, 10.0, 2.0)  # fmt: skip
    taken = f"{SHADOW_CLIP_PREFIX}cup__shadow"
    state = NS(
        animations={taken: object()},
        tracks=[],
        shot=NS(id="s", duration=1.0),
        step_hz=None,
    )
    _add_shadow_clip(state, moving, times=[0.0, 1.0])
    assert f"{taken}~2" in state.animations
    assert state.tracks[0].clips[0].animation_id == f"{taken}~2"


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
    # its centre where the compiled document puts it (cast right by its lean)
    x = _at(_compile(project, light=UPPER_LEFT), 0.0)[0]
    centre = (min(cols) + max(cols) + 1) / 2  # pixel k covers [k, k + 1)
    assert centre == pytest.approx(cx + x, abs=1.5), (centre, cx + x)
    assert not any(shadow(px[x, floor - 20]) for x in range(cx - 10, cx + 11)), (
        "the shadow is painted over the cup"
    )
    assert hermetic_browser["blocked"] == [], hermetic_browser["blocked"]
