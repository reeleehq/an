"""A boiling line (an#443): a hand-drawn wobble drawn again on twos.

The compiler puts every drawing on the wire (`PathJSON.drawings`, the first
being the static wobble's bytes) and a stepped `boil` channel picks one every
``1 / boil_hz`` seconds; the runtime's path registers `boil` as a draw set, so
trim, dashes, taper and arrowheads are drawn on each drawing exactly as on the
static one. The pixels are the core corpus fixture `path_boil`'s goldens.
"""

from __future__ import annotations

import json

import pytest

from tests._node import node_json, requires_node

from an.ir.schema import AssetRef, Shot
from an.stage.compile import BOIL_SET, boil_keys, compile_shot
from an.stage.paths import PathDescriptor, drawn_polyline

ROUTE = {
    "kind": "PathDescriptor",
    "name": "route",
    "points": [[-110, 50], [-20, 50], [20, -40], [110, -40]],
    "width": 6,
    "wobble": 4,
    "arrowhead": True,
}


def _compiled(doc: dict, *, duration: float = 0.5) -> dict:
    shot = Shot(
        id="s",
        duration=duration,
        entities=[AssetRef(kind="prop", id="route", store="props", ref="route")],
    )
    compiled = compile_shot(
        shot, {"props": {"route": doc}}, fps=24, width=320, height=240
    )
    return json.loads(compiled.model_dump_json())


def _path(compiled: dict) -> dict:
    (route,) = [c for c in compiled["scene"]["children"] if c["name"] == "route"]
    return route["visual"]["path"]


def test_the_first_drawing_is_the_static_wobbles_bytes_and_the_others_differ():
    static = _path(_compiled(ROUTE))
    boiling = _path(_compiled({**ROUTE, "boil_hz": 12, "boil_drawings": 3}))
    assert boiling["points"] == static["points"]
    assert "drawings" not in static and "boil_hz" not in boiling
    assert len(boiling["drawings"]) == 2
    for other in boiling["drawings"]:
        assert len(other) == len(static["points"]) and other != static["points"]
        assert other[0] == static["points"][0] and other[-1] == static["points"][-1]
    assert boiling["drawings"][0] != boiling["drawings"][1]


def test_every_drawing_keeps_the_authored_points_at_the_same_indices():
    desc = PathDescriptor.model_validate({**ROUTE, "boil_hz": 12})
    _, anchors = drawn_polyline(desc, "route")
    for k in range(1, desc.boil_drawings):
        assert drawn_polyline(desc, "route", variant=k)[1] == anchors


def test_the_boil_channel_steps_through_the_drawings_on_its_clock():
    compiled = _compiled({**ROUTE, "boil_hz": 12, "boil_drawings": 3}, duration=0.3)
    (anim,) = [
        a for a in compiled["animations"].values() if a["name"].startswith("__boil__")
    ]
    (channel,) = anim["channels"]
    assert (channel["target"], channel["property"]) == ("route", BOIL_SET)
    keys = [(k["time"], k["value"], k["easing"]) for k in channel["keyframes"]]
    assert keys == [(t, v, "step") for t, v in boil_keys(12, 3, 0.3)]
    assert [v for _, v, _ in keys] == ["0", "1", "2", "0"]
    assert keys[1][0] == pytest.approx(1 / 12)


def test_a_boil_compiles_to_the_same_bytes_every_time():
    doc = {**ROUTE, "boil_hz": 12}
    assert _compiled(doc) == _compiled(doc)


@pytest.mark.parametrize(
    "fields, refusal",
    [
        ({"boil_hz": 12, "wobble": None}, "a boil re-draws the wobble"),
        ({"boil_drawings": 4}, "`boil_hz` is not"),
        ({"boil_hz": 12, "boil_drawings": 1}, "greater than or equal to 2"),
        ({"boil_hz": 12, "wobble_wavelength": 0.2}, "fewer `boil_drawings`"),
    ],
)
def test_a_boil_that_would_draw_nothing_or_too_much_is_refused(fields, refusal):
    doc = {k: v for k, v in {**ROUTE, **fields}.items() if v is not None}
    with pytest.raises(ValueError, match=refusal):
        PathDescriptor.model_validate(doc)


def test_an_explicit_zero_switches_a_boil_off_for_one_shot():
    """A document that boils, and a shot that wants it still (or ruled)."""
    from an.stage.paths import resolve_path

    doc = {**ROUTE, "boil_hz": 12, "boil_drawings": 2}
    assert not resolve_path(doc, {"boil_hz": 0}).boils
    assert not resolve_path(doc, {"wobble": 0}).boils
    still = _path(_compiled({**doc, "boil_hz": 0}))
    assert "drawings" not in still


def test_a_boil_faster_than_the_frame_rate_is_refused_and_a_slow_one_warned():
    from an.stage.compile import CutoutCompileError

    with pytest.raises(CutoutCompileError, match="faster than the shot's 24 fps"):
        _compiled({**ROUTE, "boil_hz": 200})
    with pytest.warns(UserWarning, match="never steps"):
        _compiled({**ROUTE, "boil_hz": 1}, duration=0.5)


def test_a_boiling_path_draws_on_with_its_own_trim_channel():
    """A trim tween and the boil each keep their own channel on the path."""
    from an.ir.compose import tween

    shot = Shot(
        id="s",
        duration=0.5,
        entities=[AssetRef(kind="prop", id="route", store="props", ref="route")],
        actions=[tween("route", "trim_end", to=1.0, duration=0.5, from_=0.0)],
    )
    doc = {**ROUTE, "boil_hz": 12}
    compiled = json.loads(
        compile_shot(
            shot, {"props": {"route": doc}}, fps=24, width=320, height=240
        ).model_dump_json()
    )
    props = {
        (ch["target"], ch["property"])
        for a in compiled["animations"].values()
        for ch in a["channels"]
    }
    assert {("route", "trim_end"), ("route", BOIL_SET)} <= props


@requires_node
def test_the_runtime_swaps_the_drawing_and_refuses_a_key_it_does_not_have():
    """`makePath` registers `boil` as a draw set: key `k` redraws drawing `k`
    through the same `drawPath` (trim and all), `"0"` is `points`, its rest;
    an unknown key throws naming the keys it has."""
    from tests.test_path import (
        RUNTIME_JS,
        _FAKE_GRAPHICS,
        _apply_property_source,
        _extract_js_block,
    )

    compiled = _compiled({**ROUTE, "boil_hz": 12, "boil_drawings": 3})
    spec = _path(compiled)
    src = RUNTIME_JS.read_text(encoding="utf-8")
    script = "\n".join(
        [
            _FAKE_GRAPHICS,
            _apply_property_source(),
            _extract_js_block(src, "function makePath"),
            _extract_js_block(src, "function unknownSwapKey"),
            _extract_js_block(src, "function applySwap"),
            "const PIXI = {Graphics: FakeGraphics};",
            f"const g = makePath({{path: {json.dumps(spec)}}});",
            # the stroke's first lineTo is the drawing's second point: the
            # ends stay put, the points between them are what a boil moves
            "const firstMove = () => g.calls.find(c => c[0] === 'lineTo').slice(1);",
            "const out = {rest: g._anDrawSets.boil.rest, keys: g._anDrawSets.boil.keys};",
            "out.drawn = [firstMove()];",
            "for (const k of ['1', '2', '0']) { g.calls = []; applySwap(g, {name: 'route'}, 'boil', k);"
            " out.drawn.push(firstMove()); }",
            "try { applySwap(g, {name: 'route'}, 'boil', '7'); } catch (e) { out.error = e.message; }",
            "console.log(JSON.stringify(out));",
        ]
    )
    out = node_json(script)
    assert out["rest"] == "0" and out["keys"] == ["0", "1", "2"]
    drawings = [spec["points"], *spec["drawings"]]
    seconds = [list(d[1]) for d in (drawings[0], drawings[1], drawings[2], drawings[0])]
    assert out["drawn"] == seconds
    assert len({tuple(p) for p in seconds[:3]}) == 3, "three different drawings"
    assert 'unknown key "7"' in out["error"] and '["0","1","2"]' in out["error"]


@requires_node
def test_seeking_back_restores_the_first_drawing():
    """The runtime captures each channel's rest before it plays and restores it
    on a seek backwards: for `boil`, through the draw set's rest, drawing 0."""
    from tests.test_path import (
        RUNTIME_JS,
        _FAKE_GRAPHICS,
        _apply_property_source,
        _extract_js_block,
    )

    spec = _path(_compiled({**ROUTE, "boil_hz": 12, "boil_drawings": 3}))
    src = RUNTIME_JS.read_text(encoding="utf-8")
    script = "\n".join(
        [
            _FAKE_GRAPHICS,
            _apply_property_source(),
            _extract_js_block(src, "function makePath"),
            _extract_js_block(src, "function unknownSwapKey"),
            _extract_js_block(src, "function applySwap"),
            _extract_js_block(src, "function captureRest"),
            "const PIXI = {Graphics: FakeGraphics};",
            f"const g = makePath({{path: {json.dumps(spec)}}});",
            "const node = {name: 'route', children: [g]};",
            "const restore = captureRest(node, 'boil');",
            "applySwap(g, node, 'boil', '2');",
            "const swapped = g._anPath.points === g._anPath.spec.drawings[1];",
            "restore();",
            "console.log(JSON.stringify({swapped,"
            " restored: g._anPath.points === g._anPath.spec.points}));",
        ]
    )
    assert node_json(script) == {"swapped": True, "restored": True}
