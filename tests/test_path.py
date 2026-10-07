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
    dash_spans,
    flatten_curve,
    path_geometry,
)
from an.adapters.cutout.serialize import VisualJSON, to_dict
from an.ir.schema import (
    AssetRef,
    Meta,
    Resolution,
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
    Path(__file__).resolve().parents[1] / "an" / "stage" / "runtime" / "runtime.js"
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
        (0.5, 1.0),  # the first path's trim starts ON its corner (a tail's leaving leg)
    ]
    heads = [(0.0, 0.0), (20.0, 10.0), (1e6, 3.0)]
    # the tail head (an#161): none, a normal one, and one far longer than the path
    tails = [(0.0, 0.0), (14.0, 9.0), (1e6, 3.0)]
    # (dash, gap, offset): solid, plain, an irrational period with a negative
    # offset, a dash far longer than the path, and a hairline dash
    # width profiles (an#161): none, a taper to nothing, an irregular brush
    profiles = [None, [[0.0, 1.0], [1.0, 0.0]], [[0.0, 0.2], [0.37, 1.5], [1.0, 0.1]]]
    dashes = [
        (0.0, 0.0, 0.0),
        (10.0, 15.0, 0.0),
        (7.3, 2.9000000000000004, -13.7),
        (1e6, 1.0, 5.0),
        (0.5, 0.5, 1e5),
    ]
    return [
        {
            "pts": [list(p) for p in pts],
            "ts": ts,
            "te": te,
            "hl": hl,
            "hw": hw,
            "dash": d,
            "gap": g,
            "off": o,
            "thl": thl,
            "thw": thw,
            "w": 7.3,
            "prof": prof,
        }
        for pts in rng_pts
        for ts, te in trims
        for hl, hw in heads
        for d, g, o in dashes
        for thl, thw in tails
        for prof in profiles
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
    "function pathSegmentFrom",
    "function pathHead",
    "function pathPointAt",
    "function pathTrim",
    "function pathDashSpans",
    "function clamp01",
    "function pathProfileWidth",
    "function pathOutline",
    "function pathGeometry",
)


def _runtime_pieces(*markers: str) -> str:
    src = RUNTIME_JS.read_text(encoding="utf-8")
    consts = []
    for name in ("const PATH_HEAD_STROKE_INSET", "const PATH_OUTLINE_MITER_LIMIT"):
        c = src[src.index(name) :]
        consts.append(c[: c.index(";") + 1])
    return "\n".join([*consts, *(_extract_js_block(src, m) for m in markers)])


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
            "pathGeometry(c.pts, c.ts, c.te, c.hl, c.hw, c.dash, c.gap, c.off, c.thl, c.thw, c.w, c.prof))));",
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
            dash=case["dash"],
            gap=case["gap"],
            dash_offset=case["off"],
            tail_head_length=case["thl"],
            tail_head_width=case["thw"],
            width=case["w"],
            width_profile=case["prof"],
        )
        want_json = json.loads(json.dumps(want))
        assert got == want_json, case


# --- dashes (an#161) ------------------------------------------------------------


def test_dashes_are_laid_from_the_path_start_and_clipped_to_the_trim():
    assert dash_spans(0.0, 100.0, 10.0, 15.0, 0.0) == [
        (0.0, 10.0), (25.0, 35.0), (50.0, 60.0), (75.0, 85.0),
    ]
    # a trim that starts mid-dash clips that dash; it does not restart the pattern
    assert dash_spans(30.0, 60.0, 10.0, 15.0, 0.0) == [(30.0, 35.0), (50.0, 60.0)]


def test_dashes_do_not_crawl_as_trim_end_grows():
    """The acceptance line of the issue: revealing a dashed path must not move a
    dash. Every dash of a shorter trim is a dash of a longer one, unchanged —
    except the last, which is the one the tip is cutting into."""
    pts = flatten_curve(
        [(-200, 40), (-120, -160), (80, 180), (210, -30)], curve="cubic", samples=24
    )
    kw = dict(dash=12.0, gap=9.0, dash_offset=3.5)
    previous = []
    for i in range(1, 101):
        now = path_geometry(pts, 0.0, i / 100, **kw)["dashes"]
        assert now[: len(previous) - 1] == previous[:-1]
        assert not previous or now[len(previous) - 1][0] == previous[-1][0]
        previous = now
    assert len(previous) > 20


def test_moving_trim_start_does_not_move_a_dash_either():
    full = path_geometry(L_POINTS, 0.0, 1.0, dash=10.0, gap=10.0)["dashes"]
    cut = path_geometry(L_POINTS, 0.3, 1.0, dash=10.0, gap=10.0)["dashes"]
    assert cut[-len(full) + 6 :] == full[6:]  # the untouched tail is identical


def test_the_offset_slides_the_pattern_forward_along_the_path():
    a = dash_spans(0.0, 60.0, 10.0, 10.0, 0.0)
    b = dash_spans(0.0, 60.0, 10.0, 10.0, 5.0)
    assert a[1] == (20.0, 30.0) and b[1] == (25.0, 35.0)
    # one full period is the identity (marching ants loop seamlessly)
    assert dash_spans(0.0, 60.0, 10.0, 10.0, 20.0) == a


def test_a_dashed_stroke_ends_short_of_an_arrowhead_like_a_solid_one():
    g = path_geometry(L_POINTS, 0.0, 1.0, head_length=20.0, head_width=10.0, dash=10.0, gap=5.0)
    assert g["stroke"] == [] and g["head"] is not None
    last = g["dashes"][-1][-1]
    assert last[1] <= 60.0 - 20.0 * HEAD_STROKE_INSET + 1e-9  # stops inside the head


def test_a_solid_path_has_no_dashes_key():
    assert "dashes" not in path_geometry(L_POINTS, 0.0, 1.0)


def test_the_python_lengths_are_exact_square_roots():
    assert cumulative_lengths([(0, 0), (3, 4), (3, 10)]) == [0.0, 5.0, 11.0]


# --- the runtime applies trim to the path, and only to a path -----------------


_FAKE_GRAPHICS = """
function FakeGraphics() {
  this.calls = [];
  const self = this;
  ['clear','lineStyle','moveTo','lineTo','beginFill','endFill','drawPolygon','closePath']
    .forEach(m => { self[m] = function() { self.calls.push([m].concat([].slice.call(arguments))); }; });
}
function parseColor(s) { return parseInt(s.slice(1), 16); }
"""


def _apply_property_source() -> str:
    src = RUNTIME_JS.read_text(encoding="utf-8")
    return "\n".join(
        [
            _runtime_pieces(*_GEOMETRY_FUNCS, "function drawPath", "function applyTrim"),
            # an#314: a node's own drawing lives in `contentOf(node)`.
            _extract_js_block(src, "function contentOf"),
            _extract_js_block(src, "function planeOf"),
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


@pytest.mark.genre("cutout_animation")
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


def test_a_dashed_path_reaches_the_wire_with_gap_defaulting_to_dash():
    p = _compile(_shot(), {"dash": 12.0}).scene.children[0].visual.path
    assert (p.dash, p.gap, p.dash_offset) == (12.0, 12.0, 0.0)
    p = _compile(_shot(), {"dash": 12.0, "gap": 4.0, "dash_offset": 3.0})
    p = p.scene.children[0].visual.path
    assert (p.dash, p.gap, p.dash_offset) == (12.0, 4.0, 3.0)
    assert _compile(_shot()).scene.children[0].visual.path.dash == 0.0


def _march(**kw):
    return TweenAction(
        target="route", property="dash_offset", from_value=0.0, to_value=20.0,
        duration=1.0, easing="linear", **kw,
    )


def test_marching_ants_is_an_ordinary_numeric_tween_on_dash_offset():
    scene = _compile(_shot(actions=[_march()]), {"dash": 10.0})
    (clip,) = scene.animations.values()
    (ch,) = clip.channels
    assert (ch.target, ch.property) == ("route", "dash_offset")
    assert [k.value for k in ch.keyframes] == [0.0, 20.0]


def test_a_dash_offset_tween_starts_at_the_documents_offset():
    tween = TweenAction(target="route", property="dash_offset", to_value=20.0)
    scene = _compile(_shot(actions=[tween]), {"dash": 10.0, "dash_offset": 7.0})
    (clip,) = scene.animations.values()
    assert [k.value for k in clip.channels[0].keyframes] == [7.0, 20.0]


def test_dash_offset_on_a_solid_path_raises_and_validate_agrees():
    shot = _shot(actions=[_march()])
    with pytest.raises(CutoutCompileError, match="no dash pattern"):
        _compile(shot)
    assert not _validate(shot).passed
    assert _validate(shot, {"dash": 10.0}).passed


@pytest.mark.genre("cutout_animation")
def test_dash_offset_on_a_character_is_refused_too():
    shot = _shot(
        actions=[SetAction(target="charlie", property="dash_offset", value=1.0)],
        extra=[AssetRef(kind="character", id="charlie", store="characters", ref="c")],
    )
    with pytest.raises(CutoutCompileError, match="not a path node"):
        _compile(shot)
    assert not _validate(shot).passed


def test_a_swap_set_may_not_be_named_dash_offset():
    from an.base import swap_set_name_problem

    assert swap_set_name_problem("dash_offset") is not None


def test_the_descriptor_refuses_inert_or_sub_pixel_dashes():
    import pydantic

    with pytest.raises(pydantic.ValidationError, match="`dash` is not"):
        PathDescriptor(name="x", points=L_POINTS, gap=4.0)
    with pytest.raises(pydantic.ValidationError, match="`dash` is not"):
        PathDescriptor(name="x", points=L_POINTS, dash_offset=4.0)
    with pytest.raises(pydantic.ValidationError, match="below"):
        PathDescriptor(name="x", points=L_POINTS, dash=0.2, gap=0.2)
    with pytest.raises(pydantic.ValidationError):
        PathDescriptor(name="x", points=L_POINTS, dash=-3.0)


@requires_node
def test_the_runtime_applies_dash_offset_and_throws_on_an_undashed_path():
    script = "\n".join(
        [
            _FAKE_GRAPHICS,
            _apply_property_source(),
            "const out = {};",
            "const g = new FakeGraphics();",
            "g._anPath = {spec: {points: [[0,0],[100,0]], stroke_width: 4, color: '#ff0000',"
            " head_length: 0, head_width: 0, dash: 10, gap: 10},"
            " trim_start: 0, trim_end: 1, dash_offset: 0};",
            "applyProperty({name: 'route', children: [g]}, 'dash_offset', 5);",
            "out.moves = g.calls.filter(c => c[0] === 'moveTo').map(c => c[1]);",
            "const solid = new FakeGraphics();",
            "solid._anPath = {spec: {points: [[0,0],[100,0]], stroke_width: 4,"
            " color: '#ff0000'}, trim_start: 0, trim_end: 1, dash_offset: 0};",
            "try { applyProperty({name: 'route', children: [solid]}, 'dash_offset', 5);"
            " out.err = 'no throw'; } catch (e) { out.err = String(e.message); }",
            "console.log(JSON.stringify(out));",
        ]
    )
    out = node_json(script)
    assert out["moves"] == [5, 25, 45, 65, 85]  # a dash every 20 px, shifted by 5
    assert "no dash pattern" in out["err"]


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


# --- tail and double-headed arrows, arc-length sampling (an#161) -------------------


def test_a_tail_head_points_back_along_the_leg_the_path_leaves_on():
    g = path_geometry(L_POINTS, 0.0, 1.0, tail_head_length=20.0, tail_head_width=10.0)
    tip, b1, b2 = g["tail"]
    assert tip == pytest.approx((-120.0, -60.0))  # at the trimmed start
    assert b1[0] == pytest.approx(-100.0) and b2[0] == pytest.approx(-100.0)  # base 20 px in, along +x
    assert {round(b1[1], 6), round(b2[1], 6)} == {-55.0, -65.0}
    assert g["stroke"][0][0] == pytest.approx(-120.0 + 20.0 * HEAD_STROKE_INSET)
    assert g["head"] is None  # no end head asked for


def test_a_tail_tip_on_a_corner_points_back_along_the_outgoing_leg():
    g = path_geometry(L_POINTS, 0.5, 1.0, tail_head_length=20.0, tail_head_width=10.0)
    tip, b1, _ = g["tail"]
    assert tip == pytest.approx((0.0, -60.0))
    assert b1[1] == pytest.approx(-40.0)  # base down the second leg (+y), not back along the first


def test_both_heads_shrink_together_while_the_visible_length_is_short():
    full = path_geometry(L_POINTS, 0.0, 1.0, head_length=20.0, head_width=10.0,
                         tail_head_length=20.0, tail_head_width=10.0)
    short = path_geometry(L_POINTS, 0.0, 20.0 / 240.0, head_length=20.0, head_width=10.0,
                          tail_head_length=20.0, tail_head_width=10.0)
    def length(tri):
        (tx, ty), (bx, by), (cx, cy) = tri
        return math.hypot(tx - (bx + cx) / 2, ty - (by + cy) / 2)
    assert length(full["head"]) == pytest.approx(20.0) and length(full["tail"]) == pytest.approx(20.0)
    assert length(short["head"]) == pytest.approx(10.0) and length(short["tail"]) == pytest.approx(10.0)


def test_one_head_scales_and_draws_exactly_as_before():
    """No tail asked for: no `tail` key, and the end head is what it was (the parity battery pins it)."""
    g = path_geometry(L_POINTS, 0.0, 0.05, head_length=20.0, head_width=10.0)
    assert "tail" not in g


def test_a_double_headed_arrow_reaches_the_wire_and_a_single_one_has_no_tail_field():
    def wire(**doc):
        scene = compile_shot(_shot(), {"props": {"route": _doc(**doc)}})
        return scene.scene.children[0].visual.path.model_dump(mode="json")

    wire_both = wire(arrowhead=True, tail_arrowhead=True)
    wire_one = wire(arrowhead=True)
    assert wire_both["tail_head_length"] == wire_both["head_length"] > 0
    assert "tail_head_length" not in wire_one and "tail_head_width" not in wire_one  # no hash moves


def test_head_sizes_with_only_a_tail_are_not_inert():
    PathDescriptor(name="x", points=L_POINTS, tail_arrowhead=True, head_length=10.0)
    with pytest.raises(ValueError, match="arrowhead is false"):
        PathDescriptor(name="x", points=L_POINTS, head_length=10.0)


def test_arclength_sampling_spaces_a_cubic_evenly():
    cubic = [(0, 0), (0, 300), (30, 0), (300, 0)]  # slow at the start, fast at the end
    def spread(pts):
        steps = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
        return max(steps) / min(steps)
    by_param = flatten_curve(cubic, curve="cubic", samples=24)
    by_length = flatten_curve(cubic, curve="cubic", samples=24, sampling="arclength")
    assert by_length[0] == by_param[0] and by_length[-1] == by_param[-1]  # same endpoints
    assert spread(by_param) > 3 and spread(by_length) < 1.1
    with pytest.raises(ValueError, match="sampling"):
        PathDescriptor(name="x", points=L_POINTS, sampling="arclength")  # a polyline: inert


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_a_double_headed_arrow_draws_both_heads(tmp_path):
    """The L arrow drawn whole, a head at each end: at its start (pixel 40, 60)
    the tail spreads across the leg pointing -x, at its end (160, 180) the head
    points +y. Same canvas as the draw-on test above."""
    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer

    head_len, head_w = 21.0, 18.0
    mall = {"props": {"route": _doc(color="#ff0000", width=6.0, arrowhead=True,
                                    tail_arrowhead=True, head_length=head_len,
                                    head_width=head_w)}}
    result = CutoutRenderer().render(
        _shot(),
        RenderContext(mall=mall, work_dir=tmp_path, fps=12, resolution=(320, 240),
                      strict_assets=True),
    )
    m = _ink_mask(result.frame_manifest[0])
    cx, cy = 160, 120
    assert abs(min(x for x, _ in m) - (cx - 120)) <= 2  # the tail's tip
    near_tail_base = [y for x, y in m if x == cx - 120 + int(head_len) - 3]
    assert max(near_tail_base) - min(near_tail_base) >= head_w * 0.7, near_tail_base
    assert abs(max(y for _, y in m) - (cy + 60)) <= 2  # the end head's tip


# --- the hand-drawn wobble (an#161) ------------------------------------------------


def _distance_to_polyline(p, poly):
    best = math.inf
    for (ax, ay), (bx, by) in zip(poly, poly[1:]):
        dx, dy = bx - ax, by - ay
        u = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.dist(p, (ax + u * dx, ay + u * dy)))
    return best


def test_a_wobble_wanders_within_its_amplitude_and_keeps_the_ends():
    """Every point stays within `wobble` px of the ruled line, the ends and
    the corner are kept as samples, and the line does wander."""
    scene = _compile(_shot(), {"wobble": 3.0, "wobble_wavelength": 40.0})
    pts = scene.scene.children[0].visual.path.points
    assert pts[0] == L_POINTS[0] and pts[-1] == L_POINTS[-1]
    assert len(pts) > len(L_POINTS)
    off = [_distance_to_polyline(p, L_POINTS) for p in pts]
    assert max(off) <= 3.0 + 1e-9 and max(off) > 1.0


def test_a_wobble_is_seeded_by_the_entity_and_its_seed():
    """Two arrows sharing one document wobble differently; the same arrow
    wobbles the same way every compile."""
    from an.stage.path_wobble import wobble_polyline

    def wobbled(seed):
        return wobble_polyline(L_POINTS, amplitude=3.0, wavelength=40.0, seed=seed)

    first = _compile(_shot(), {"wobble": 3.0, "wobble_wavelength": 40.0})
    again = _compile(_shot(), {"wobble": 3.0, "wobble_wavelength": 40.0})
    assert first.scene.children[0].visual.path.points == again.scene.children[0].visual.path.points
    assert first.scene.children[0].visual.path.points == wobbled("route:0")
    assert wobbled("route:0") != wobbled("other:0") != wobbled("route:1")


def test_the_wobble_is_the_same_bytes_on_every_machine():
    """No trigonometry: value noise from sha256 knots, joined by a cubic, so
    the floats are pinned (CI runs on another OS than the goldens' machine)."""
    import hashlib

    from an.stage.path_wobble import wobble_polyline

    pts = wobble_polyline(L_POINTS, amplitude=3.0, wavelength=40.0, seed="route:0")
    digest = hashlib.sha256(repr(pts).encode()).hexdigest()[:16]
    assert digest == WOBBLE_DIGEST, digest


WOBBLE_DIGEST = "341ba348bb4d9ffa"


def test_the_descriptor_refuses_an_inert_or_runaway_wobble():
    with pytest.raises(ValueError, match="wobble` is 0"):
        PathDescriptor(name="r", points=L_POINTS, wobble_seed=2)
    with pytest.raises(ValueError, match="lengthen `wobble_wavelength`"):
        PathDescriptor(name="r", points=[(0, 0), (100_000, 0)], wobble=2.0, wobble_wavelength=1.0)
    assert PathDescriptor(name="r", points=L_POINTS, wobble=2.0).wobble_wavelength_px == 80.0


# --- closed and filled shapes (an#161) ----------------------------------------------

SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]


def test_a_closed_path_returns_to_its_first_point_on_the_wire():
    p = _compile(_shot(), {"points": SQUARE, "closed": True, "fill": "#3498db", "fill_alpha": 0.5})
    path = p.scene.children[0].visual.path
    assert path.points == [*SQUARE, SQUARE[0]]
    assert (path.closed, path.fill, path.fill_alpha) == (True, "#3498db", 0.5)


def test_an_open_unfilled_path_carries_no_new_wire_fields():
    """Byte identity: every pre-existing path document serializes as before."""
    d = json.dumps(to_dict(_compile(_shot(), {"arrowhead": True})))
    assert '"closed"' not in d and '"fill' not in d


def test_the_descriptor_refuses_a_fill_it_cannot_draw():
    with pytest.raises(ValueError, match="closed: true"):
        PathDescriptor(name="r", points=SQUARE, fill="#000000")
    with pytest.raises(ValueError, match="fill_alpha is set"):
        PathDescriptor(name="r", points=SQUARE, closed=True, fill_alpha=0.5)
    with pytest.raises(ValueError, match="three distinct points"):
        PathDescriptor(name="r", points=[(0, 0), (10, 0)], closed=True, fill="#000000")
    with pytest.raises(ValueError, match="draw nothing"):
        PathDescriptor(name="r", points=SQUARE, width=0)
    with pytest.raises(ValueError, match="arrowhead"):
        PathDescriptor(name="r", points=SQUARE, width=0, closed=True, fill="#000000", arrowhead=True)
    assert PathDescriptor(name="r", points=SQUARE, width=0, closed=True, fill="#000000").width == 0


def test_a_trim_on_a_fill_with_no_border_is_refused_and_validate_agrees():
    region = {"points": SQUARE, "closed": True, "fill": "#3498db", "width": 0}
    with pytest.raises(CutoutCompileError, match="no stroke"):
        _compile(_shot(actions=[_draw_on()]), region)
    scene = SceneIR(
        meta=Meta(duration=1.0, resolution=Resolution(width=320, height=240)),
        timeline=[_shot(actions=[_draw_on()])],
    )
    report = validate_semantic(scene, available_props={"route": _doc(**region)})
    assert any("no stroke" in f.description for f in report.findings if f.severity == "error")


def _draw(spec: dict, **state) -> list:
    script = "\n".join(
        [
            _FAKE_GRAPHICS,
            _apply_property_source(),
            f"const g = new FakeGraphics(); g._anPath = Object.assign({{spec: {json.dumps(spec)},"
            " trim_start: 0, trim_end: 1, dash_offset: 0}, " + json.dumps(state) + ");",
            "drawPath(g); console.log(JSON.stringify(g.calls));",
        ]
    )
    return node_json(script)


@requires_node
def test_the_runtime_fills_under_the_stroke_and_joins_a_whole_closed_path():
    closed = [list(p) for p in [*SQUARE, SQUARE[0]]]
    spec = {"points": closed, "stroke_width": 4, "color": "#ff0000", "closed": True,
            "fill": "#0000ff", "fill_alpha": 0.25}
    calls = _draw(spec)
    names = [c[0] for c in calls]
    assert names.index("beginFill") < names.index("moveTo")  # the fill is under the stroke
    assert ["beginFill", 0x0000FF, 0.25] in calls and "closePath" in names
    lines = [c for c in calls if c[0] == "lineTo"]
    assert len(lines) == 3  # the closing leg is closePath, not a lineTo onto the start
    # trimmed, it is an open stroke again; the fill stays whole
    calls = _draw(spec, trim_end=0.5)
    assert "closePath" not in [c[0] for c in calls]
    (poly,) = [c for c in calls if c[0] == "drawPolygon"]
    assert len(poly[1]) == 2 * len(closed)


@requires_node
def test_the_runtime_draws_no_stroke_for_a_fill_with_no_border():
    spec = {"points": [list(p) for p in [*SQUARE, SQUARE[0]]], "stroke_width": 0,
            "color": "#ff0000", "closed": True, "fill": "#0000ff"}
    names = [c[0] for c in _draw(spec)]
    assert "drawPolygon" in names and "moveTo" not in names


# --- variable width / taper (an#161) ------------------------------------------------

TAPER = [(0.0, 1.0), (1.0, 0.0)]


def test_a_taper_is_anchored_to_the_path_so_a_draw_on_does_not_crawl():
    """The width at a point of the path is the same whatever the trim: the
    outline's start (left, right) is identical at trim_end 0.5 and 1.0."""
    pts = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]
    half = path_geometry(pts, 0.0, 0.5, width=10.0, width_profile=TAPER)["outlines"][0]
    whole = path_geometry(pts, 0.0, 1.0, width=10.0, width_profile=TAPER)["outlines"][0]
    assert half[0] == whole[0] == (0.0, 5.0)
    assert half[-1] == whole[-1] == (0.0, -5.0)
    # at the half-way tip (the corner) the stroke is half as wide
    assert half == [(0.0, 5.0), (100.0, 2.5), (100.0, -2.5), (0.0, -5.0)]
    assert whole[len(whole) // 2 - 1] == (100.0, 100.0)  # factor 0 at the end


def test_a_taper_reaches_the_wire_and_an_even_stroke_carries_no_profile():
    p = _compile(_shot(), {"width_profile": [[0, 1], [1, 0.2]]}).scene.children[0].visual.path
    assert p.width_profile == [(0.0, 1.0), (1.0, 0.2)]
    assert '"width_profile"' not in json.dumps(to_dict(_compile(_shot())))


def test_the_descriptor_refuses_a_profile_it_cannot_draw():
    for bad, msg in [
        ([[0, 1]], "t=0 to t=1"),
        ([[0.1, 1], [1, 0]], "t=0 to t=1"),
        ([[0, 1], [0.5, 1], [0.5, 0], [1, 0]], "increase strictly"),
        ([[0, 0], [1, 0]], "not all zero"),
        ([[0, -1], [1, 1]], "non-negative"),
    ]:
        with pytest.raises(ValueError, match=msg):
            PathDescriptor(name="r", points=L_POINTS, width_profile=bad)
    with pytest.raises(ValueError, match="cap/join"):
        PathDescriptor(name="r", points=L_POINTS, width_profile=TAPER, cap="butt")


@requires_node
def test_the_runtime_fills_a_tapered_stroke_instead_of_stroking_it():
    spec = {"points": [[0, 0], [100, 0]], "stroke_width": 8, "color": "#ff0000",
            "width_profile": [[0, 1], [1, 0]]}
    calls = _draw(spec)
    names = [c[0] for c in calls]
    assert "moveTo" not in names and "lineTo" not in names
    (poly,) = [c for c in calls if c[0] == "drawPolygon"]
    assert poly[1] == [0, 4, 100, 0, 100, 0, 0, -4]


# --- arrivals: a draw-on timed per point (an#161) -----------------------------------


def _tip_at(scene_doc, entity, t):
    from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene

    return evaluate_timeline(timeline_from_scene(scene_doc), t)[(entity, "trim_end")]


@pytest.mark.parametrize("extra", [{}, {"wobble": 3.0, "wobble_wavelength": 30.0}, {"closed": True}])
def test_the_tip_reaches_each_authored_point_on_its_beat(extra):
    """`draw_on_through` times each leg; at each arrival the trim is exactly
    the arc fraction of that point on the polyline the compiler drew (wobble
    and the closing leg included)."""
    from an.stage.path_geometry import cumulative_lengths
    from an.stage.paths import draw_on_through, drawn_polyline, resolve_path

    doc = _doc(trim_end=0.0, **extra)
    desc = resolve_path(doc)
    pts, anchors = drawn_polyline(desc, "route")
    arrivals = [0.25, 0.4, 0.9][: len(anchors) - 1]
    shot = _shot(actions=draw_on_through("route", doc, arrivals))
    scene = compile_shot(shot, mall={"props": {"route": doc}}, fps=12, width=320, height=240)
    drawn = scene.scene.children[0].visual.path.points
    assert drawn == pts  # the helper measured what the compiler drew
    cum = cumulative_lengths(pts)
    for t, i in zip(arrivals, anchors[1:]):
        assert _tip_at(scene, "route", t) == pytest.approx(cum[i] / cum[-1], abs=1e-12)
    assert _tip_at(scene, "route", 0.0) == 0.0


def test_draw_on_through_refuses_a_wrong_count_or_order():
    from an.stage.paths import draw_on_through

    with pytest.raises(ValueError, match="takes 2 arrival times"):
        draw_on_through("route", _doc(), [1.0])
    with pytest.raises(ValueError, match="must increase"):
        draw_on_through("route", _doc(), [1.0, 0.5])


def test_an_unknown_field_names_the_closest_ones_and_lists_them_all():
    """an#457: an end user guessed `arrowhead_start` for a double-headed arrow."""
    with pytest.raises(ValueError) as err:
        PathDescriptor(name="r", points=L_POINTS, arrowhead_start=True)
    msg = str(err.value)
    assert "'arrowhead_start' (did you mean" in msg and "'tail_arrowhead'" in msg
    assert "The fields are: arrowhead, cap, closed" in msg
