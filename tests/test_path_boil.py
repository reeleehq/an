"""A boiling line (an#443): a hand-drawn wobble drawn again on twos.

The compiler puts every drawing on the wire (`PathJSON.variants`, the first
being the static wobble's bytes) and a stepped `boil` channel picks one every
``1 / boil_hz`` seconds; the runtime's path registers `boil` as a draw set, so
trim, dashes, taper and arrowheads are drawn on each drawing exactly as on the
static one. The pixels are the core corpus fixture `path_boil`'s goldens.
"""

from __future__ import annotations

import json

import pytest

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
    boiling = _path(_compiled({**ROUTE, "boil_hz": 12, "boil_variants": 3}))
    assert boiling["points"] == static["points"]
    assert "variants" not in static and "boil_hz" not in static
    assert len(boiling["variants"]) == 2
    for other in boiling["variants"]:
        assert len(other) == len(static["points"]) and other != static["points"]
        assert other[0] == static["points"][0] and other[-1] == static["points"][-1]
    assert boiling["variants"][0] != boiling["variants"][1]


def test_every_drawing_keeps_the_authored_points_at_the_same_indices():
    desc = PathDescriptor.model_validate({**ROUTE, "boil_hz": 12})
    _, anchors = drawn_polyline(desc, "route")
    for k in range(1, desc.boil_variants):
        assert drawn_polyline(desc, "route", variant=k)[1] == anchors


def test_the_boil_channel_steps_through_the_drawings_on_its_clock():
    compiled = _compiled({**ROUTE, "boil_hz": 12, "boil_variants": 3}, duration=0.3)
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
        ({"boil_hz": 12, "wobble": 0}, "a boil re-draws the wobble"),
        ({"boil_variants": 4}, "`boil_hz` is 0"),
        ({"boil_hz": 12, "boil_variants": 1}, "greater than or equal to 2"),
        ({"boil_hz": 12, "wobble_wavelength": 0.2}, "fewer `boil_variants`"),
    ],
)
def test_a_boil_that_would_draw_nothing_or_too_much_is_refused(fields, refusal):
    with pytest.raises(ValueError, match=refusal):
        PathDescriptor.model_validate({**ROUTE, **fields})
