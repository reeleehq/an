"""an#275 (finding 14): gradient planes, and a StylePack that sets them through roles.

A plane offered only `fill` and `image`, so a backlit-glass look needed
hand-drawn gradient SVG plates. A `gradient` plane is a linear or radial blend
of colour stops (`an.paint.Gradient`, CSS's vocabulary), compiled into an inline
SVG texture (`an.stage.gradients`) -- document content, like the glow, so
`runtime.js` does not change and no scene that does not use one moves a byte.
"""

from __future__ import annotations

import base64
import io
import warnings

import pytest
from pydantic import ValidationError

from an.ir.schema import AssetRef, Shot
from an.paint import Gradient
from an.stage.environments import EnvironmentDescriptor, Plane, PlaneArt, plane_rect
from an.stage.gradients import gradient_svg
from an.styles import StylePack

W, H = 320, 180


def _env(*planes: dict) -> dict:
    return {"glass": {"kind": "EnvironmentDescriptor", "name": "glass", "planes": list(planes)}}


def _compile(env: dict, *, pack: StylePack | None = None, size=(W, H)) -> dict:
    from an.stage.compile import compile_shot
    from an.stage.serialize import to_dict

    shot = Shot(
        id="s",
        renderer="stage",
        duration=1.0,
        entities=[AssetRef(kind="environment", id="bg", store="environments", ref="glass")],
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return to_dict(
            compile_shot(
                shot,
                mall={"environments": env},
                fps=10,
                width=size[0],
                height=size[1],
                style_pack=pack,
            )
        )


def _planes(doc: dict) -> dict[str, dict]:
    return {c["name"]: c for c in doc["scene"]["children"][0]["children"]}


def _svg(doc: dict, node: dict) -> str:
    src = doc["assets"]["textures"][node["visual"]["asset_id"]]["src"]
    prefix = "data:image/svg+xml;base64,"
    assert src.startswith(prefix)
    return base64.b64decode(src[len(prefix) :]).decode("utf-8")


SKY = {"name": "sky", "art": {"kind": "gradient", "gradient": {"stops": ["#000000", "#ffffff"]}}}
TABLE = {"name": "table", "art": {"kind": "fill", "color": "#202020", "role": "glass"},
         "size": [W, 40], "offset": [0, 70]}


# ------------------------------------------------------------------ the schema


def test_a_gradient_needs_two_stops_in_order():
    with pytest.raises(ValidationError, match="at least 2 stops"):
        Gradient(stops=["#fff"])
    with pytest.raises(ValidationError, match="must not decrease"):
        Gradient(stops=[{"offset": 0.6, "color": "#fff"}, {"offset": 0.2, "color": "#000"}])
    with pytest.raises(ValidationError):
        Gradient(stops=["#fff", "white"])  # hex only, as everywhere in a pack


def test_a_field_that_does_nothing_is_refused():
    with pytest.raises(ValidationError, match="do nothing on a linear"):
        Gradient(stops=["#fff", "#000"], radius=0.3)
    with pytest.raises(ValidationError, match="do nothing on a radial"):
        Gradient(type="radial", stops=["#fff", "#000"], angle=45)


def test_a_gradient_dump_reads_back():
    for g in (
        Gradient(stops=["#fff", "#000"], angle=45),
        Gradient(type="radial", stops=["#fff", "#0000"], center=(0.3, 0.6), radius=0.8),
    ):
        assert Gradient(**g.model_dump()) == g


def test_plane_art_kinds_and_their_paint_agree():
    with pytest.raises(ValidationError, match="needs `gradient"):
        PlaneArt(kind="gradient")
    with pytest.raises(ValidationError, match="does nothing on a `fill`"):
        PlaneArt(kind="fill", gradient={"stops": ["#fff", "#000"]})
    with pytest.raises(ValidationError, match="does nothing on an `image`"):
        PlaneArt(kind="image", src="a.svg", role="glass")


def test_a_stored_plane_without_paint_dumps_as_it_did():
    env = EnvironmentDescriptor(name="e", planes=[Plane(name="p")])
    art = env.model_dump()["planes"][0]["art"]
    assert set(art) == {"kind", "color", "src"}


def test_a_style_pack_typo_of_gradients_is_refused():
    with pytest.raises(ValidationError, match="did you mean 'gradients'"):
        StylePack(name="x", gradient={"glass": {"stops": ["#fff", "#000"]}})


# ----------------------------------------------------------------- the geometry


def test_linear_follows_the_css_angle_over_the_frame():
    g = Gradient(stops=["#000", "#fff"], angle=90)  # to the right
    svg = gradient_svg(g, box=(400.0, 400.0), frame=(200.0, 100.0))
    assert 'x1="100" y1="200" x2="300" y2="200"' in svg  # the frame's width, centred
    g = Gradient(stops=["#000", "#fff"], angle=45)  # CSS: corners on the end stops
    svg = gradient_svg(g, box=(100.0, 100.0), frame=(100.0, 100.0))
    assert 'x1="0" y1="100" x2="100" y2="0"' in svg


def test_the_raster_is_capped_and_stretched_not_the_box():
    svg = gradient_svg(Gradient(stops=["#000", "#fff"]), box=(4000.0, 2000.0),
                       frame=(1920.0, 1080.0), raster_max=512)
    assert 'width="512" height="256"' in svg and 'viewBox="0 0 4000 2000"' in svg


def test_an_unsized_gradient_covers_like_a_fill_and_a_sized_one_honours_its_anchor():
    unsized = Plane(name="p", art=PlaneArt(kind="gradient", gradient={"stops": ["#000", "#fff"]}),
                    anchor=(0.0, 0.0))
    assert plane_rect(unsized, None) == (-2000.0, -2000.0, 2000.0, 2000.0)
    sized = unsized.model_copy(update={"size": (100.0, 50.0)})
    assert plane_rect(sized, None) == (0.0, 0.0, 100.0, 50.0)


# ------------------------------------------------------------------ the compiler


def test_a_gradient_plane_compiles_to_an_inline_svg_sprite():
    doc = _compile(_env(SKY))
    sky = _planes(doc)["sky"]
    assert sky["visual"]["kind"] == "svg_sprite" and sky["visual"]["fit"] == "stretch"
    assert (sky["visual"]["width"], sky["visual"]["height"]) == (4000.0, 4000.0)
    svg = _svg(doc, sky)
    # shaped over the CANVAS, centred in the covering box
    assert f'y1="{2000 - H // 2}"' in svg and f'y2="{2000 + H // 2}"' in svg
    assert _compile(_env(SKY)) == doc, "deterministic: the same document twice"


def test_the_texture_alias_is_content_addressed():
    a = _planes(_compile(_env(SKY)))["sky"]["visual"]["asset_id"]
    other = {**SKY, "art": {"kind": "gradient", "gradient": {"stops": ["#000000", "#fefefe"]}}}
    b = _planes(_compile(_env(other)))["sky"]["visual"]["asset_id"]
    assert a != b and a.startswith("glass.sky.")


def test_a_fill_plane_is_untouched_without_a_pack_or_its_role():
    plain = _compile(_env(TABLE))
    assert _planes(plain)["table"]["visual"]["kind"] == "rect"
    other_role = StylePack(name="p", gradients={"sky": {"stops": ["#fff", "#000"]}})
    assert _compile(_env(TABLE), pack=other_role)["scene"] == plain["scene"]


def test_a_pack_gradient_role_repaints_a_fill_plane_and_a_gradient_plane():
    pack = StylePack(name="dusk", gradients={
        "glass": {"angle": 90, "stops": ["#3a2414", "#b8783c"]},
    })
    sky = {**SKY, "art": {**SKY["art"], "role": "glass"}}
    planes = _planes(doc := _compile(_env(sky, TABLE), pack=pack))
    for name in ("sky", "table"):
        assert planes[name]["visual"]["kind"] == "svg_sprite", name
        assert 'stop-color="#b8783c"' in _svg(doc, planes[name]), name
    # the fill keeps its own geometry: its box, centred
    assert (planes["table"]["visual"]["width"], planes["table"]["visual"]["height"]) == (W, 40)


def test_a_scene_without_gradients_compiles_exactly_as_before():
    """The fill/image paths are the pre-an#275 code: a fill plane and a pack
    with no gradients give the document the stage always gave."""
    doc = _compile(_env(TABLE), pack=StylePack(name="p", roles={"sky": "#123456"}))
    table = _planes(doc)["table"]
    assert table["visual"] == {"kind": "rect", "fit": "stretch", "texture_id": None,
                               "asset_id": None, "asset_sets": None, "width": float(W),
                               "height": 40.0, "anchor_x": 0.5, "anchor_y": 0.5,
                               "color": "#202020"}


# --------------------------------------------------------------------- pixels


def _frame(doc: dict, tmp_path):
    from PIL import Image

    from an.stage.render import StageEngine

    with StageEngine().open_document(doc, workspace=tmp_path, size=(W, H)) as session:
        png = session.frame(0.0)
    return Image.open(io.BytesIO(png)).convert("RGB")


def _close(a, b, tol=12):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


@pytest.mark.browser
def test_a_linear_gradient_runs_top_to_bottom_over_the_frame(tmp_path):
    img = _frame(_compile(_env(SKY)), tmp_path)
    top, mid, bottom = (img.getpixel((W // 2, y)) for y in (1, H // 2, H - 2))
    assert _close(top, (0, 0, 0)) and _close(bottom, (255, 255, 255)), (top, bottom)
    assert _close(mid, (128, 128, 128), tol=16), mid
    left, right = img.getpixel((2, H // 2)), img.getpixel((W - 3, H // 2))
    assert _close(left, right, tol=2), "a vertical gradient is level across"


@pytest.mark.browser
def test_a_radial_gradient_is_brightest_at_its_centre(tmp_path):
    glow = {"name": "glow", "art": {"kind": "gradient", "gradient": {
        "type": "radial", "stops": ["#ffffff", "#000000"]}}, "size": [W, H]}
    img = _frame(_compile(_env(glow)), tmp_path)
    centre = img.getpixel((W // 2, H // 2))
    edge = img.getpixel((W // 2, 1))
    corner = img.getpixel((1, 1))
    assert _close(centre, (255, 255, 255)) and _close(edge, (0, 0, 0), tol=16)
    assert _close(corner, (0, 0, 0)), "past the radius the end colour holds"
