"""Draw order that follows the holder, in the runtime (an#537).

The hold layer keys a held item's ``paint_after`` channel on the part that holds
it (``tests/test_holds.py`` checks those keys). Here the runtime's half runs
under node on the vendored PixiJS bundle: ``PaintProxy``, ``makeHeldPaints`` and
``applyPaintAfter`` are lifted from ``runtime.js`` verbatim, a small tree is
built, and every leaf records when it is rendered, so the assertion is the
paint order PixiJS itself walks (no WebGL: nothing is drawn, the order is).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tests._node import NODE_BUNDLE_TIMEOUT_S, requires_node, run_node

from an.base import ORDER_PROPERTIES, PAINT_AFTER_PROPERTY, swap_set_name_problem
from an.timing.timeline import write_group

RUNTIME_DIR = Path(__file__).resolve().parents[1] / "an" / "stage" / "runtime"
RUNTIME_JS = RUNTIME_DIR / "runtime.js"
BUNDLE = RUNTIME_DIR / "vendor" / "pixi.min.js"


def _lift(src: str, start: str, end: str) -> str:
    """``src`` from the line holding ``start`` to the end of the block ending
    the line holding ``end``'s function."""
    i = src.index(start)
    j = src.index(end, i)
    return src[i : src.index("\n    }", j) + len("\n    }")]


def _paint_order(case: str, hide: str = "none") -> list[str]:
    """The leaves PixiJS renders, in order, for one of the scripted cases.
    ``hide`` hides the figure (the holder) before each frame: ``alpha0`` or
    ``invisible``; ``root_alpha0`` hides their common ancestor (an#562)."""
    if not BUNDLE.is_file():
        pytest.skip(f"vendored pixi not present at {BUNDLE}")
    src = RUNTIME_JS.read_text(encoding="utf-8")
    lifted = "\n".join(
        [
            _lift(src, "class PaintProxy extends", "function applyPaintAfter("),
            src[src.index("const PAINT_AFTER =") : src.index("const SHARED_WRITES")],
        ]
    )
    script = f"""
    global.self = global; global.window = global;
    global.document = {{ createElement: () => ({{ getContext: () => null, style: {{}} }}),
                        addEventListener: () => {{}} }};
    (0, eval)(require('fs').readFileSync({json.dumps(str(BUNDLE))}, 'utf8'));
    let nodeIndex = {{}};
    const log = [];
    class Leaf extends PIXI.Container {{
        render(r) {{
            if (!this.visible || this.worldAlpha <= 0 || !this.renderable) return;
            log.push(this.name);
        }}
    }}
    {lifted}
    function node(path, parent) {{
        const c = new PIXI.Container();
        c.name = path;
        nodeIndex[path] = c;
        const leaf = new Leaf();
        leaf.name = path;
        c.addChild(leaf);
        c._anDraws = [leaf];
        if (parent) parent.addChild(c);
        return c;
    }}
    const top = new PIXI.Container();
    const root = new PIXI.Container();
    top.addChild(root);
    const fig = new PIXI.Container();
    fig.name = 'fig'; nodeIndex['fig'] = fig; root.addChild(fig);
    node('fig/arm_far', fig); node('fig/torso', fig); node('fig/arm_near', fig);
    node('stand', root);
    const stick = node('stick', root);
    const host = {json.dumps(case)};
    const hide = {json.dumps(hide)};
    if (hide === 'alpha0') fig.alpha = 0;
    if (hide === 'invisible') fig.visible = false;
    if (hide === 'root_alpha0') root.alpha = 0;
    if (host === 'sorted') {{
        // The figure's container sorts its parts (an#403): the torso first.
        nodeIndex['fig/arm_far'].zIndex = 2;
        nodeIndex['fig/torso'].zIndex = 1;
        nodeIndex['fig/arm_near'].zIndex = 3;
        fig.sortableChildren = true;
    }}
    if (host === 'global') {{
        // The figure's parts painted from a global paint list (an#430).
        applyGlobalPaint(fig, 'fig', ['torso', 'arm_far', 'arm_near']);
    }}
    const scene = {{animations: {{
        __solve__stick: {{channels: [{{target: 'stick', property: 'paint_after', keyframes: [
            {{time: 0, value: ''}}, {{time: 1, value: 'fig/arm_far'}}, {{time: 2, value: 'stand'}}]}}]}}
    }}}};
    makeHeldPaints(scene);
    const out = {{}};
    for (const value of ['', 'fig/arm_far', 'stand']) {{
        applyPaintAfter(stick, value);
        log.length = 0;
        root.updateTransform();
        root.render({{}});
        out[value] = log.slice();
    }}
    let refused = null;
    try {{ applyPaintAfter(stick, 'fig/torso'); }} catch (e) {{ refused = String(e.message); }}
    out.refused = refused;
    console.log(JSON.stringify(out));
    """
    proc = run_node(script, timeout=NODE_BUNDLE_TIMEOUT_S)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@requires_node
@pytest.mark.parametrize(
    "case, held_by_far_arm",
    [
        ("plain", ["fig/arm_far", "stick", "fig/torso", "fig/arm_near", "stand"]),
        ("sorted", ["fig/torso", "fig/arm_far", "stick", "fig/arm_near", "stand"]),
        ("global", ["fig/torso", "fig/arm_far", "stick", "fig/arm_near", "stand"]),
    ],
)
def test_a_held_item_is_painted_just_after_its_holder_and_back_in_place_when_let_go(
    case, held_by_far_arm
):
    """Held by the far arm, the stick paints right after it (under the torso and
    the near arm, whichever way the figure orders its parts); in the stand,
    right after the stand; let go, at its own place. Each frame it paints once."""
    out = _paint_order(case)
    staged = {
        "plain": ["fig/arm_far", "fig/torso", "fig/arm_near", "stand", "stick"],
        "sorted": ["fig/torso", "fig/arm_far", "fig/arm_near", "stand", "stick"],
        "global": ["fig/torso", "fig/arm_far", "fig/arm_near", "stand", "stick"],
    }[case]
    assert out[""] == staged
    assert out["fig/arm_far"] == held_by_far_arm
    assert out["stand"] == [p for p in staged if p != "stick"] + ["stick"]
    assert "no loaded channel prepared" in out["refused"]


def test_paint_after_is_its_own_write_group_and_not_a_swap_set():
    """A swap on the item's node must not make the pose drop its paint key, nor
    the reverse: two different write groups. And no swap set may take the name."""
    assert write_group(PAINT_AFTER_PROPERTY) == PAINT_AFTER_PROPERTY
    assert write_group("viseme") != write_group(PAINT_AFTER_PROPERTY)
    assert swap_set_name_problem(PAINT_AFTER_PROPERTY) is not None


def test_the_runtime_lists_the_same_order_properties():
    """`runtime.js`'s ``ORDER_PROPERTIES`` mirrors :data:`an.base.ORDER_PROPERTIES`."""
    import re

    src = RUNTIME_JS.read_text(encoding="utf-8")
    block = src[src.index("const PAINT_AFTER =") : src.index("const SHARED_WRITES")]
    (listed,) = re.findall(r"const PAINT_AFTER = '([a-z_]+)'", block)
    assert {listed} == set(ORDER_PROPERTIES)
    assert "new Set([PAINT_AFTER])" in block
    # applyProperty and captureRest spell the one member literally (tests lift
    # them out on their own): the same name.
    for fn in ("function applyProperty(", "function captureRest("):
        body = src[src.index(fn) : src.index("switch (prop)", src.index(fn))]
        assert f"prop === '{listed}'" in body, fn


# -- in pixels ---------------------------------------------------------------------


@pytest.mark.browser
@pytest.mark.parametrize("holder_alpha", [None, 0.0])
def test_in_pixels_a_held_item_draws_over_the_arm_that_holds_it(tmp_path, holder_alpha):
    """The stick is staged BEFORE the figure (under every part of it). Taken in
    the right hand, its grip is drawn over the hand that holds it: the pixel at
    the grip is the stick's brown, not the arm's blue (which it was before
    an#537, the item's entity order standing for the whole shot). With the
    figure faded to alpha 0 the stick still draws (an#562): brown, and not the
    background."""
    import warnings

    from PIL import Image

    from tests._hold_fixture import K, make_project, scene

    from an.adapters._base import RenderContext
    from an.stage.compile import compile_shot
    from an.stage.render import CutoutRenderer
    from an.stage.timeline import (
        evaluate_timeline,
        screen_position,
        timeline_from_scene,
    )

    width, height, fps = 640, 480, 4
    entities = """- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 150], scale: 0.5}, overrides: {held_by: ground}}
- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [160, 200]}}
"""
    project = make_project(
        tmp_path / "p",
        scene(
            "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}"
            + (
                ""
                if holder_alpha is None
                else f"\n- {{kind: set, target: fig, property: alpha, value: {holder_alpha}, at: 0.0}}"
            ),
            entities=entities,
        ),
    )
    shot = project.scene.timeline[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = CutoutRenderer().render(
            shot,
            RenderContext(
                mall=project.mall,
                work_dir=tmp_path / "w",
                fps=fps,
                resolution=(width, height),
            ),
        )
        doc = compile_shot(shot, project.mall, fps=fps, width=width, height=height)
    frames = result.frame_manifest
    t = (len(frames) - 1) / fps
    pose = evaluate_timeline(timeline_from_scene(doc), t)
    assert pose[("stick", "paint_after")] == "fig/arm_r"
    x, y = screen_position(doc, "stick", pose=pose, point=(0.0, 60.0 * K))
    with Image.open(frames[-1]) as im:
        r, g, b = im.convert("RGB").getpixel((round(x), round(y)))
    brown, blue = (120, 80, 40), (0x2F, 0x6F, 0x9F)
    assert math.dist((r, g, b), brown) < math.dist((r, g, b), blue), (r, g, b)
    if holder_alpha == 0.0:  # nothing of the figure shows, so the stick is not the arm's colour by luck
        assert math.dist((r, g, b), brown) < 60, (r, g, b)


@requires_node
@pytest.mark.parametrize("case", ["plain", "sorted", "global"])
@pytest.mark.parametrize("hide", ["alpha0", "invisible"])
def test_a_held_item_still_shows_when_its_holder_is_hidden(case, hide):
    """an#562: the holder faded to alpha 0 (or hidden) takes its parts with it, and
    the item, its own entity, still paints: from the holder's skipped place."""
    out = _paint_order(case, hide)
    assert out["fig/arm_far"] == ["stick", "stand"][:1] + ["stand"]
    assert out[""] == ["stand", "stick"]  # at its own place, as ever
    assert out["stand"] == ["stand", "stick"]


@requires_node
def test_a_hidden_ancestor_shared_with_the_item_still_hides_it():
    """The item follows ITS tree: hide what holds them both and neither paints."""
    out = _paint_order("plain", "root_alpha0")
    assert out["fig/arm_far"] == [] and out[""] == []


@requires_node
@pytest.mark.parametrize("case", ["plain", "sorted", "global"])
def test_nothing_hidden_nothing_changes(case):
    """The guard is invisible until an ancestor is skipped: the same order as before."""
    out = _paint_order(case)
    assert out["fig/arm_far"].count("stick") == 1
