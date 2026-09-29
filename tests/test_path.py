"""Stroked paths with trim and an auto-oriented arrowhead (an#160, epic #9 Wave 9).

Four layers, each checked where it can fail:

- the geometry spec (`an.adapters.cutout.path`) against the runtime's own
  functions, executed under node — exact parity, not a tolerance;
- the compiler: what a path document becomes, the strict override merge,
  `trim_*` refused on anything that is not a path, validate agreeing;
- byte-identity: a visual without a path serializes exactly as before;
- pixels, in the browser lane: an arrow drawing itself, its head at the moving
  tip and pointing along the leg it is on.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.adapters.cutout.path import (
    HEAD_STROKE_INSET,
    cumulative_lengths,
    flatten_curve,
    path_geometry,
)
from an.adapters.cutout.serialize import VisualJSON, to_dict
from an.ir.schema import (
    AssetRef,
    Meta,
    SceneIR,
    SequenceAction,
    DelayAction,
    SetAction,
    Shot,
    StagePlacement,
    TweenAction,
)
from an.ir.validate import validate_semantic
from an.paths import PathDescriptor
from tests._node import node_json, requires_node

RUNTIME_JS = (
    Path(__file__).resolve().parents[1] / "an" / "data" / "cutout_runtime" / "runtime.js"
)

L_POINTS = [(-120.0, -60.0), (0.0, -60.0), (0.0, 60.0)]


def _doc(**kw) -> dict:
    return {"kind": "PathDescriptor", "name": "route", "points": L_POINTS, **kw}


def _shot(*, actions=(), overrides=None, stage=None, extra=()) -> Shot:
    return Shot(
        id="s",
        renderer="cutout",
        duration=1.0,
        entities=[
            AssetRef(
                kind="prop",
                id="route",
                store="props",
                ref="route",
                overrides=overrides,
                stage=stage,
            ),
            *extra,
        ],
        actions=list(actions),
    )


def _draw_on(duration: float = 1.0):
    return TweenAction(
        target="route",
        property="trim_end",
        from_value=0.0,
        to_value=1.0,
        duration=duration,
        easing="linear",
    )


# --- the geometry spec --------------------------------------------------------


def test_the_head_points_along_the_leg_the_tip_is_on():
    """Before the corner the head points +x; after it, +y — the auto-orientation."""
    pts = L_POINTS
    before = path_geometry(pts, 0.0, 0.25, head_length=20.0, head_width=10.0)["head"]
    after = path_geometry(pts, 0.0, 0.75, head_length=20.0, head_width=10.0)["head"]
    (tx, ty), (ax, ay), (bx, by) = before
    assert (tx, ty) == (-60.0, -60.0)
    assert ax == bx == tx - 20.0 and {ay, by} == {ty - 5.0, ty + 5.0}
    (tx, ty), (ax, ay), (bx, by) = after
    assert (tx, ty) == (0.0, 0.0)
    assert ay == by == ty - 20.0 and {ax, bx} == {tx - 5.0, tx + 5.0}


def test_a_tip_exactly_on_a_corner_points_along_the_incoming_leg():
    head = path_geometry(L_POINTS, 0.0, 0.5, head_length=20.0, head_width=10.0)["head"]
    assert head[0] == (0.0, -60.0)
    assert head[1][0] == head[2][0] == -20.0  # base vertical: pointing +x


def test_trim_is_by_arc_length_and_order_independent():
    g = path_geometry(L_POINTS, 0.75, 0.25)
    assert g["stroke"] == [(-60.0, -60.0), (0.0, -60.0), (0.0, 0.0)]
    assert path_geometry(L_POINTS, 1.5, -2.0)["stroke"] == L_POINTS  # clamped


def test_an_empty_span_draws_nothing_not_even_a_head():
    assert path_geometry(L_POINTS, 0.0, 0.0, head_length=20.0, head_width=10.0) == {
        "stroke": [],
        "head": None,
    }


def test_the_head_grows_in_while_the_visible_length_is_shorter_than_it():
    g = path_geometry(L_POINTS, 0.0, 10.0 / 240.0, head_length=20.0, head_width=10.0)
    (tx, _), (bx, _), _ = g["head"]
    assert math.isclose(tx - bx, 10.0)  # half-size head for half the length
    assert g["stroke"][-1][0] == pytest.approx(tx - 10.0 * HEAD_STROKE_INSET)


def test_a_cubic_is_flattened_to_its_own_endpoints():
    pts = flatten_curve(
        [(0, 0), (0, 100), (100, 100), (100, 0)], curve="cubic", samples=16
    )
    assert len(pts) == 17 and pts[0] == (0.0, 0.0) and pts[-1] == (100.0, 0.0)
    # A chain of two shares the joint once.
    two = flatten_curve(
        [(0, 0), (0, 1), (1, 1), (1, 0), (1, -1), (2, -1), (2, 0)],
        curve="cubic",
        samples=4,
    )
    assert len(two) == 9


def _battery() -> list[dict]:
    rng_pts = [
        [(-120.0, -60.0), (0.0, -60.0), (0.0, 60.0)],
        # degenerate (repeated) vertices, a U-turn, irrational lengths
        [(0.0, 0.0), (0.0, 0.0), (3.0, 4.0), (3.0, 4.0), (-7.3, 11.1), (5.5, -2.25)],
        flatten_curve(
            [(-200, 40), (-120, -160), (80, 180), (210, -30)], curve="cubic", samples=24
        ),
        [(0.1, 0.2), (0.30000000000000004, 0.7)],
    ]
    trims = [
        (0.0, 1.0), (0.0, 0.5), (0.25, 0.75), (0.75, 0.25), (0.0, 0.0),
        (0.3, 0.3), (-1.0, 2.0), (0.0, 1e-9), (0.1, 0.9999999999999999),
        (1.0 / 3.0, 2.0 / 3.0),
    ]
    heads = [(0.0, 0.0), (20.0, 10.0), (1e6, 3.0)]
    return [
        {"pts": [list(p) for p in pts], "ts": ts, "te": te, "hl": hl, "hw": hw}
        for pts in rng_pts
        for ts, te in trims
        for hl, hw in heads
    ]


def _extract_js_block(src: str, start_marker: str) -> str:
    start = src.index(start_marker)
    i = src.index("{", start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start : j + 1]
    raise AssertionError(f"unbalanced braces after {start_marker!r}")


_GEOMETRY_FUNCS = (
    "function pathLengths",
    "function pathSegmentAt",
    "function pathPointAt",
    "function pathTrim",
    "function clamp01",
    "function pathGeometry",
)


def _runtime_pieces(*markers: str) -> str:
    src = RUNTIME_JS.read_text(encoding="utf-8")
    inset = src[src.index("const PATH_HEAD_STROKE_INSET") :]
    inset = inset[: inset.index(";") + 1]
    return "\n".join([inset, *(_extract_js_block(src, m) for m in markers)])


@requires_node
def test_the_runtime_geometry_equals_the_python_spec_exactly(tmp_path):
    """Behavioural parity over a battery, not a textual diff: the runtime's own
    `pathGeometry` is lifted out of `runtime.js` and executed under node.
    EXACT equality — both sides use only IEEE + - * / sqrt, in one order.

    The battery goes through a FILE, not the `-e` script: inlined, the command
    line exceeds Windows' 32 767-character limit (WinError 206)."""
    cases = _battery()
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(json.dumps(cases), encoding="utf-8")
    script = "\n".join(
        [
            _runtime_pieces(*_GEOMETRY_FUNCS),
            "const cases = JSON.parse(require('fs').readFileSync("
            "process.argv[1], 'utf8'));",
            "console.log(JSON.stringify(cases.map(c => "
            "pathGeometry(c.pts, c.ts, c.te, c.hl, c.hw))));",
        ]
    )
    js = node_json(script, str(cases_file))
    for case, got in zip(cases, js):
        want = path_geometry(
            [tuple(p) for p in case["pts"]],
            case["ts"],
            case["te"],
            head_length=case["hl"],
            head_width=case["hw"],
        )
        want_json = json.loads(json.dumps(want))
        assert got == want_json, case


def test_the_python_lengths_are_exact_square_roots():
    assert cumulative_lengths([(0, 0), (3, 4), (3, 10)]) == [0.0, 5.0, 11.0]


# --- the runtime applies trim to the path, and only to a path -----------------


_FAKE_GRAPHICS = """
function FakeGraphics() {
  this.calls = [];
  const self = this;
  ['clear','lineStyle','moveTo','lineTo','beginFill','endFill','drawPolygon']
    .forEach(m => { self[m] = function() { self.calls.push([m].concat([].slice.call(arguments))); }; });
}
function parseColor(s) { return parseInt(s.slice(1), 16); }
"""


def _apply_property_source() -> str:
    src = RUNTIME_JS.read_text(encoding="utf-8")
    return "\n".join(
        [
            _runtime_pieces(*_GEOMETRY_FUNCS, "function drawPath", "function applyTrim"),
            _extract_js_block(src, "function applyTintDeep"),
            _extract_js_block(src, "function applyProperty"),
        ]
    )


@requires_node
def test_the_runtime_applies_trim_to_the_path_visual():
    """The counterpart of `test_loud_discards`' PATH_ONLY exemption: each trim
    property lands on the path visual's state and triggers a redraw."""
    script = "\n".join(
        [
            _FAKE_GRAPHICS,
            _apply_property_source(),
            "const spec = {points: [[0,0],[100,0]], stroke_width: 4, color: '#ff0000',"
            " head_length: 0, head_width: 0};",
            "const out = {};",
            "for (const p of ['trim_start', 'trim_end']) {",
            "  const g = new FakeGraphics();",
            "  g._anPath = {spec: spec, trim_start: 0, trim_end: 1};",
            "  const node = {name: 'route', children: [g]};",
            "  applyProperty(node, p, 0.25);",
            "  out[p] = {state: g._anPath[p], calls: g.calls};",
            "}",
            "console.log(JSON.stringify(out));",
        ]
    )
    out = node_json(script)
    assert out["trim_start"]["state"] == 0.25 and out["trim_end"]["state"] == 0.25
    moves = [c for c in out["trim_end"]["calls"] if c[0] in ("moveTo", "lineTo")]
    assert moves == [["moveTo", 0, 0], ["lineTo", 25, 0]]
    moves = [c for c in out["trim_start"]["calls"] if c[0] in ("moveTo", "lineTo")]
    assert moves == [["moveTo", 25, 0], ["lineTo", 100, 0]]


@requires_node
def test_the_runtime_throws_on_trim_of_a_node_that_draws_no_path():
    script = "\n".join(
        [
            _FAKE_GRAPHICS,
            _apply_property_source(),
            "try { applyProperty({name: 'charlie', children: []}, 'trim_end', 0.5);"
            " console.log(JSON.stringify('no throw')); }",
            "catch (e) { console.log(JSON.stringify(String(e.message))); }",
        ]
    )
    msg = node_json(script)
    assert "only a stroked path has a trim" in msg


# --- the compiler ---------------------------------------------------------------


def _compile(shot, docs=None, **kw):
    mall = {"props": {"route": _doc(**(docs or {}))}}
    return compile_shot(shot, mall=mall, fps=12, width=320, height=240, **kw)


def test_a_path_compiles_to_one_node_with_a_path_visual():
    scene = _compile(_shot(stage=StagePlacement(at=(10.0, 20.0))), {"arrowhead": True})
    (node,) = scene.scene.children
    assert node.name == "route" and node.visual.kind == "path"
    assert (node.transform.x, node.transform.y) == (10.0, 20.0)
    p = node.visual.path
    assert p.points == L_POINTS
    assert (p.head_length, p.head_width) == (28.0, 24.0)
    (res,) = scene.asset_resolution
    assert (res.kind, res.resolved, res.fallback) == ("prop", "path", False)


def test_no_arrowhead_means_a_zero_head_on_the_wire():
    p = _compile(_shot()).scene.children[0].visual.path
    assert p.head_length == 0.0 and p.head_width == 0.0


def test_a_draw_on_is_an_ordinary_numeric_tween():
    scene = _compile(_shot(actions=[_draw_on()]))
    (clip,) = scene.animations.values()
    (ch,) = clip.channels
    assert (ch.target, ch.property) == ("route", "trim_end")
    assert [k.value for k in ch.keyframes] == [0.0, 1.0]


def test_overrides_are_merged_over_the_stored_document():
    scene = _compile(_shot(overrides={"points": [[0, 0], [0, 50]], "width": 3.0}))
    p = scene.scene.children[0].visual.path
    assert p.points == [(0.0, 0.0), (0.0, 50.0)] and p.stroke_width == 3.0


def test_an_unknown_override_key_raises_rather_than_vanishing():
    with pytest.raises(CutoutCompileError, match="trim_ends"):
        _compile(_shot(overrides={"trim_ends": 0.0}))


def test_a_cubic_path_reaches_the_wire_flattened():
    pts = [(-100, 0), (-50, -80), (50, 80), (100, 0)]
    scene = _compile(_shot(), {"points": pts, "curve": "cubic", "samples_per_segment": 8})
    assert len(scene.scene.children[0].visual.path.points) == 9


def test_trim_on_a_character_raises_at_compile():
    shot = _shot(
        actions=[
            TweenAction(
                target="charlie", property="trim_end", from_value=0.0, to_value=1.0
            )
        ],
        extra=[AssetRef(kind="character", id="charlie", store="characters", ref="c")],
    )
    with pytest.raises(CutoutCompileError, match="not a path node"):
        _compile(shot)


def test_a_swap_set_may_not_be_named_trim_end():
    from an.base import swap_set_name_problem

    assert swap_set_name_problem("trim_end") is not None


def _validate(shot, docs=None):
    scene = SceneIR(meta=Meta(title="t", duration=1.0), timeline=[shot])
    return validate_semantic(
        scene,
        available_props={"route": _doc(**(docs or {}))},
        available_characters={},
    )


def _compiles(shot) -> bool:
    try:
        _compile(shot, strict_assets=False)
        return True
    except CutoutCompileError:
        return False


@pytest.mark.parametrize(
    "name,make",
    [
        ("plain", lambda: _shot()),
        ("draw-on", lambda: _shot(actions=[_draw_on()])),
        ("bad override", lambda: _shot(overrides={"colour": "#000000"})),
        ("bad cubic arity", lambda: _shot(overrides={"curve": "cubic"})),
        (
            "trim on a sub-path",
            lambda: _shot(
                actions=[SetAction(target="route/x", property="trim_end", value=0.5)]
            ),
        ),
        (
            "viseme on a path",
            lambda: _shot(
                actions=[SetAction(target="route", property="viseme", value="A")]
            ),
        ),
        (
            "trim on a character",
            lambda: _shot(
                actions=[SetAction(target="charlie", property="trim_end", value=0.5)],
                extra=[
                    AssetRef(kind="character", id="charlie", store="characters", ref="c")
                ],
            ),
        ),
    ],
)
def test_validate_and_compile_reach_the_same_verdict(name, make):
    shot = make()
    assert _validate(shot).passed is _compiles(shot), name


def test_trim_on_a_character_is_refused_even_without_the_props_store():
    """Review M1: before an#160 a trim on a character was refused as a
    non-transform property; joining the numeric vocabulary must not turn that
    into a pass for callers who supply only the characters store."""
    shot = _shot(
        actions=[SetAction(target="charlie", property="trim_end", value=0.5)],
        extra=[AssetRef(kind="character", id="charlie", store="characters", ref="c")],
    )
    scene = SceneIR(meta=Meta(title="t", duration=1.0), timeline=[shot])
    assert not validate_semantic(scene, available_characters={}).passed
    assert not validate_semantic(scene).passed


def test_a_trim_tween_with_no_from_starts_at_the_document_s_value():
    """Review M2: `trim_end: 0` + "tween trim_end to 1" is a draw-on. Starting
    it at the global rest (1.0) drew the whole path from frame 0, silently."""
    tween = TweenAction(target="route", property="trim_end", to_value=1.0)
    scene = _compile(_shot(actions=[tween]), {"trim_end": 0.0})
    (clip,) = scene.animations.values()
    assert [k.value for k in clip.channels[0].keyframes] == [0.0, 1.0]


# --- byte-identity ------------------------------------------------------------


def test_a_visual_without_a_path_serializes_as_before():
    """Omit-when-unset, written in the same commit as the field (the an#112
    rule). The corpus-wide guard is
    `test_expression_compose.py::test_every_corpus_contract_hash_equals_the_committed_ledger_row`,
    which this change leaves green."""
    assert "path" not in VisualJSON(kind="rect").model_dump(mode="json")
    scene = _compile(_shot())
    assert "path" in to_dict(scene)["scene"]["children"][0]["visual"]


def test_the_descriptor_refuses_what_it_cannot_draw():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        PathDescriptor(name="x", points=[(0.0, 0.0)])
    with pytest.raises(pydantic.ValidationError):
        PathDescriptor(name="x", points=[(0.0, 0.0), (float("nan"), 1.0)])
    with pytest.raises(pydantic.ValidationError):
        PathDescriptor(name="x", points=L_POINTS, trim_end=1.5)
    with pytest.raises(pydantic.ValidationError):
        PathDescriptor(name="x", points=L_POINTS, color="red")
    # Review L3: set-but-inert fields are refused like unknown ones.
    with pytest.raises(pydantic.ValidationError, match="arrowhead is false"):
        PathDescriptor(name="x", points=L_POINTS, head_length=10.0)
    with pytest.raises(pydantic.ValidationError, match="only applies"):
        PathDescriptor(name="x", points=L_POINTS, samples_per_segment=8)
    with pytest.raises(pydantic.ValidationError, match="zero"):
        PathDescriptor(name="x", points=[(1.0, 1.0), (1.0, 1.0)])


# --- pixels -------------------------------------------------------------------

#: The stroke is pure red on white; a pixel is "ink" well inside that colour,
#: so antialiased edges count only where they are mostly red.
_INK = lambda r, g, b: r > 170 and g < 110 and b < 110  # noqa: E731


def _ink_mask(png: Path):
    from PIL import Image

    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()
    return {(x, y) for y in range(h) for x in range(w) if _INK(*px[x, y])}


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_an_arrow_draws_itself_with_its_head_on_the_moving_tip(tmp_path):
    """The Wave 9 done-when for this slice, asserted on frames.

    An L-shaped arrow (right 120 px, then down 120 px) draws on linearly over
    one second at 12 fps on a 320x240 canvas, so the stage origin is pixel
    (160, 120). At t = 3/12 the tip is 60 px along the first leg, pointing
    right; at t = 9/12 it is 60 px down the second leg, pointing down.
    """
    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer

    width, head_len, head_w = 6.0, 21.0, 18.0
    mall = {
        "props": {
            "route": _doc(
                color="#ff0000",
                width=width,
                arrowhead=True,
                head_length=head_len,
                head_width=head_w,
                trim_end=0.0,
            )
        }
    }
    shot = _shot(actions=[_draw_on(1.0)])
    result = CutoutRenderer().render(
        shot,
        RenderContext(
            mall=mall,
            work_dir=tmp_path,
            fps=12,
            resolution=(320, 240),
            strict_assets=True,
        ),
    )
    frames = result.frame_manifest
    assert len(frames) == 12
    masks = [_ink_mask(f) for f in frames]

    assert not masks[0], "trim_end starts at 0: nothing may be drawn at t=0"
    counts = [len(m) for m in masks]
    assert all(b >= a for a, b in zip(counts[1:], counts[2:])), counts

    cx, cy = 160, 120
    # t = 3/12: tip at scene (-60, -60) → pixel (100, 60), head pointing +x.
    m = masks[3]
    xs = [x for x, _ in m]
    assert abs(max(xs) - (cx - 60)) <= 2, max(xs)
    near_base = [y for x, y in m if x == cx - 60 - int(head_len) + 3]
    assert max(near_base) - min(near_base) >= head_w * 0.7, near_base
    assert not any(y > cy - 60 + head_w for _, y in m)  # nothing on the second leg

    # t = 9/12: tip at scene (0, 0) → pixel (160, 120), head pointing +y.
    m = masks[9]
    ys = [y for _, y in m]
    assert abs(max(ys) - cy) <= 2, max(ys)
    near_base = [x for x, y in m if y == cy - int(head_len) + 3]
    assert max(near_base) - min(near_base) >= head_w * 0.7, near_base
    # A head pointing +x would reach 21 px right of the leg; this one is
    # symmetric about it and stays within its half-width.
    assert max(x for x, _ in m) <= cx + head_w / 2 + 2
    # The first leg is fully drawn by now.
    assert min(x for x, _ in m) <= cx - 118
