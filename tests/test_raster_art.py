"""Raster art, private-study licences, empty props, framing, per-key geometry (an#211).

End-user agents built a two-character scene out of art carved from real
footage, and every item here is something that got in their way:

1. an image plate that is a PNG crashed the compiler, which parsed it as SVG —
   and an image plane ignored its declared `size`;
2. a character part could not be raster at all, so carved art was traced to
   SVG and lost its shading;
3. `an credits` called `all-rights-reserved` and `pd` "licence unknown", and an
   environment could credit only one source;
4. a prop with no skin drew nothing, with `strict_assets` silent;
5. a close-up showed the edge of the plate and nothing said so;
6. a swap carried only the texture, so an open mouth drawn on a bigger canvas
   than the closed one was squashed into the closed one's box.

Every fixture is synthetic, drawn here with Pillow. The pixel tests are
`browser`-marked: they run on a developer machine or a PR labelled
`run-browser-tests`.
"""

from __future__ import annotations

import json
import struct
import warnings
import zlib
from pathlib import Path

import pytest

from an.adapters.cutout.compile import (
    CutoutCompileError,
    CutoutCompileWarning,
    compile_shot,
)
from an.environments import EnvironmentDescriptor, Plane, PlaneArt
from an.ir.schema import AssetRef, Camera, CameraKey, SetAction, Shot
from an.props import PropDescriptor
from cutan.characters.schema import Attachment, Skin

pytestmark = pytest.mark.genre("cutout_animation")


W, H = 320, 180

# --- fixtures ---------------------------------------------------------------


def _png(path: Path, size, rgba=(200, 30, 30, 255), *, mode="RGBA") -> Path:
    """A solid image; ``rgba`` may be a callable (x, y) -> colour."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    if callable(rgba):
        im = Image.new(mode, size)
        im.putdata([rgba(x, y) for y in range(size[1]) for x in range(size[0])])
    else:
        im = Image.new(mode, size, rgba if mode == "RGBA" else rgba[:3])
    im.save(path)
    return path


def _shot(*entities, camera=None, actions=(), duration=1.0) -> Shot:
    return Shot(
        id="s1",
        renderer="cutout",
        duration=duration,
        camera=camera,
        entities=list(entities),
        actions=list(actions),
    )


def _env_ref(ref="street") -> AssetRef:
    return AssetRef(kind="environment", id="street", store="environments", ref=ref)


def _prop_ref(ref="thing", pid=None) -> AssetRef:
    return AssetRef(kind="prop", id=pid or ref, store="props", ref=ref)


def _compile(shot, mall, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CutoutCompileWarning)
        return compile_shot(shot, mall=mall, fps=4, width=W, height=H, **kw)


def _env_store(tmp_path, planes, **kw):
    from an.stores.environments import EnvironmentsStore

    store = EnvironmentsStore(tmp_path / "envs")
    store["street"] = json.loads(
        EnvironmentDescriptor(name="street", planes=planes, **kw).model_dump_json()
    )
    return store


#: A prop whose view_box is 345 tall: `k` = SCENE_PX_PER_VIEW_BOX / 345 = 1,
#: so a part's pixel size IS its scene size and the pixel maths stays legible.
VIEW_BOX = (0, 0, 345, 345)


def _prop_store(tmp_path, *, parts: dict, slot_default: str, asset_sets=None,
                key="thing", **extra):
    """A props store holding one raster prop: ``parts`` = {name: (size, rgba)}."""
    from an.stores.props import PropsStore

    store = PropsStore(tmp_path / "props")
    for name, (size, rgba) in parts.items():
        _png(tmp_path / "props" / key / "parts" / f"{name}.png", size, rgba)
    doc = PropDescriptor(
        name=key,
        view_box=VIEW_BOX,
        skins={"default": Skin(slots={"body": {
            name: Attachment(path=f"parts/{name}.png") for name in parts
        }})},
        asset_sets=asset_sets or {},
        **extra,
    )
    data = json.loads(doc.model_dump_json())
    for slot in data["slots"]:
        slot["attachment"] = slot_default
    store[key] = data
    return store


def _node(scene, *path):
    node = scene.scene
    for name in path:
        node = next(c for c in node.children if c.name == name)
    return node


# --- 1. the header probe -----------------------------------------------------


def test_image_size_reads_png_jpeg_and_webp_headers(tmp_path):
    from an.raster import image_size

    _png(tmp_path / "a.png", (37, 21))
    from PIL import Image

    Image.new("RGB", (40, 30), (1, 2, 3)).save(tmp_path / "b.jpg", quality=90)
    Image.new("RGBA", (13, 9), (1, 2, 3, 4)).save(tmp_path / "c.webp", lossless=True)
    Image.new("RGB", (15, 11), (1, 2, 3)).save(tmp_path / "d.webp", quality=80)
    assert image_size(tmp_path / "a.png") == (37.0, 21.0)
    assert image_size(tmp_path / "b.jpg") == (40.0, 30.0)
    assert image_size(tmp_path / "c.webp") == (13.0, 9.0)
    assert image_size(tmp_path / "d.webp") == (15.0, 11.0)


def test_a_file_that_is_not_an_image_is_a_value_error_naming_the_formats(tmp_path):
    from an.raster import RasterFormatError, art_size

    (tmp_path / "x.png").write_text("<svg/>", encoding="utf-8")
    with pytest.raises(RasterFormatError, match="PNG, JPEG or WebP"):
        art_size(tmp_path / "x.png")
    assert issubclass(RasterFormatError, ValueError)  # the probe's contract


def test_alpha_is_read_from_the_header(tmp_path):
    from an.raster import has_alpha

    assert has_alpha(_png(tmp_path / "a.png", (4, 4))) is True
    assert has_alpha(_png(tmp_path / "b.png", (4, 4), mode="RGB")) is False


def test_the_content_digest_follows_the_bytes(tmp_path):
    from an.raster import content_digest

    p = _png(tmp_path / "a.png", (4, 4), (1, 2, 3, 255))
    before = content_digest(p)
    import os
    import time

    _png(p, (4, 4), (9, 9, 9, 255))
    os.utime(p, ns=(time.time_ns(), time.time_ns() + 10_000_000))
    assert content_digest(p) != before


# --- 1. image plates ---------------------------------------------------------


def test_a_png_plate_compiles_where_it_used_to_raise_a_parse_error(tmp_path):
    """The reported crash: `ParseError: not well-formed (invalid token)`."""
    from an.raster import short_digest

    png = _png(tmp_path / "envs" / "street" / "plate.png", (64, 36))
    store = _env_store(tmp_path, [
        Plane(name="plate", art=PlaneArt(kind="image", src="plate.png"), depth=0.0)
    ])
    scene = _compile(_shot(_env_ref()), {"environments": store}, strict_assets=True)
    (alias, asset), = scene.assets.textures.items()
    # addressed by its bytes: a re-carved plate is a different texture under a
    # different alias AND URL (PixiJS caches a load by URL, the browser too)
    sha = short_digest(png)
    assert alias == f"street.plate.{sha}"
    assert asset.src == f"environments/street/plate.png?v={sha}"
    visual = _node(scene, "street", "plate").visual
    assert (visual.width, visual.height) == (64.0, 36.0)  # from the PNG header


def test_a_declared_plane_size_wins_over_the_art_s_own_extent(tmp_path):
    """It was the other way round: `size` was read only for unmeasurable art,
    so resizing a plate meant rewriting its file."""
    (tmp_path / "envs" / "street").mkdir(parents=True)
    (tmp_path / "envs" / "street" / "sign.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 40" width="10" '
        'height="40"><rect width="10" height="40"/></svg>', encoding="utf-8")
    _png(tmp_path / "envs" / "street" / "plate.png", (64, 36))
    store = _env_store(tmp_path, [
        Plane(name="plate", art=PlaneArt(kind="image", src="plate.png"),
              size=(W, H), fit="stretch"),
        Plane(name="sign", art=PlaneArt(kind="image", src="sign.svg"),
              size=(30.0, 120.0)),
    ])
    scene = _compile(_shot(_env_ref()), {"environments": store}, strict_assets=True)
    plate = _node(scene, "street", "plate").visual
    sign = _node(scene, "street", "sign").visual
    assert (plate.width, plate.height) == (float(W), float(H))
    assert (sign.width, sign.height) == (30.0, 120.0)


# --- 2. raster parts ---------------------------------------------------------


def test_a_raster_part_is_sized_from_its_pixels_and_addressed_by_its_bytes(tmp_path):
    from an.raster import short_digest

    store = _prop_store(tmp_path, parts={"lamp": ((50, 80), (10, 200, 10, 255))},
                        slot_default="lamp")
    scene = _compile(_shot(_prop_ref()), {"props": store}, strict_assets=True)
    visual = _node(scene, "thing", "body").visual
    assert visual.kind == "svg_sprite" and visual.fit == "contain"
    assert (visual.width, visual.height) == (50.0, 80.0)  # k == 1
    digest = short_digest(tmp_path / "props" / "thing" / "parts" / "lamp.png")
    assert visual.asset_id == f"thing.body.lamp.{digest}"
    assert scene.assets.textures[visual.asset_id].src == (
        f"props/thing/parts/lamp.png?v={digest}")


def test_a_character_can_be_built_entirely_from_raster_parts(tmp_path):
    """Required parts, mouth shapes and the eyelid swap, all PNG: the rig
    compiles with every slot drawn and `an character validate` is satisfied."""
    from cutan.characters.schema import CharacterDescriptor
    from cutan.characters.validate import validate_character
    from an.stores.characters import CharactersStore

    doc = json.loads(CharacterDescriptor(name="rae").model_dump_json())
    char_dir = tmp_path / "chars" / "rae"
    for attachments in doc["skins"]["default"]["slots"].values():
        for att in attachments.values():
            att["path"] = att["path"].replace(".svg", ".png")
            _png(char_dir / att["path"], (40, 40), (90, 60, 30, 255))
    doc["source"] = {"provider": "me", "license": "cc0-1.0"}
    store = CharactersStore(tmp_path / "chars")
    store["rae"] = doc
    report = validate_character(char_dir)
    assert report.passed, [f.description for f in report.findings if f.severity == "error"]
    scene = _compile(
        _shot(AssetRef(kind="character", id="rae", store="characters", ref="rae")),
        {"characters": store},
        strict_assets=True,
    )
    srcs = {a.src for a in scene.assets.textures.values()}
    assert srcs and all(".png?v=" in s for s in srcs)
    # the eyelid set still projects onto both eye slots
    eyes = [n for n in _node(scene, "rae", "head").children if n.name.endswith("_eye")]
    assert eyes and all("eyelid" in (n.visual.asset_sets or {}) for n in eyes)


def test_surface_treatments_reach_a_raster_part(tmp_path):
    """The outline and the shadow are copies of the part's own visual, so a
    PNG gets them exactly as an SVG does."""
    from an.styles import StylePack

    store = _prop_store(tmp_path, parts={"lamp": ((50, 80), (10, 200, 10, 255))},
                        slot_default="lamp")
    pack = StylePack(name="p", surface={"outline": {"width": 3, "color": "#ff00ff"},
                                        "shadow": {"dx": 4, "dy": 4}})
    scene = _compile(_shot(_prop_ref()), {"props": store}, style_pack=pack)
    underlays = _node(scene, "thing", "body").visual.underlays
    assert underlays and len(underlays) == 2


def test_a_pack_warns_once_that_it_cannot_recolour_raster_parts(tmp_path):
    from an.styles import StylePack

    store = _prop_store(tmp_path, parts={"lamp": ((50, 80), (10, 200, 10, 255))},
                        slot_default="lamp")
    pack = StylePack(name="warm", roles={"skin": "#aa7755"})
    with pytest.warns(CutoutCompileWarning, match=r"raster .* cannot recolour"):
        compile_shot(_shot(_prop_ref()), mall={"props": store}, fps=4, width=W,
                     height=H, style_pack=pack)


def test_a_colour_role_on_a_raster_part_is_skipped_not_read_as_text(tmp_path):
    """`_recoloured_texture_srcs` read every tagged part as UTF-8 SVG text; a
    PNG there raised `UnicodeDecodeError` in the compiler."""
    from cutan.characters.schema import CharacterDescriptor
    from an.stores.characters import CharactersStore
    from an.styles import StylePack

    doc = json.loads(CharacterDescriptor(name="rae").model_dump_json())
    char_dir = tmp_path / "chars" / "rae"
    for attachments in doc["skins"]["default"]["slots"].values():
        for att in attachments.values():
            att["path"] = att["path"].replace(".svg", ".png")
            _png(char_dir / att["path"], (40, 40))
    doc["colour_roles"] = {"parts/torso.png": {"#c81e1e": "clothing"}}
    store = CharactersStore(tmp_path / "chars")
    store["rae"] = doc
    pack = StylePack(name="warm", roles={"clothing": "#112233"})
    scene = _compile(
        _shot(AssetRef(kind="character", id="rae", store="characters", ref="rae")),
        {"characters": store},
        style_pack=pack,
    )
    assert not any(a.src.startswith("data:") for a in scene.assets.textures.values())


# --- 2. the art-package contract ---------------------------------------------


def _package(tmp_path, *, head=None):
    """A complete PNG art package; ``head`` overrides the head part's writer."""
    from cutan.characters.schema import CharacterDescriptor

    doc = json.loads(CharacterDescriptor(name="rae").model_dump_json())
    char_dir = tmp_path / "rae"
    for attachments in doc["skins"]["default"]["slots"].values():
        for att in attachments.values():
            att["path"] = att["path"].replace(".svg", ".png")
            _png(char_dir / att["path"], (40, 40))
    doc["source"] = {"provider": "me", "license": "cc0-1.0"}
    if head is not None:
        head(char_dir / "parts" / "head.png")
    (char_dir / "character.json").write_text(json.dumps(doc), encoding="utf-8")
    return char_dir


def _findings(char_dir, severity):
    from cutan.characters.validate import validate_character

    return [f for f in validate_character(char_dir).findings if f.severity == severity]


def test_validate_blocks_a_fully_transparent_raster_part(tmp_path):
    char_dir = _package(tmp_path, head=lambda p: _png(p, (40, 40), (0, 0, 0, 0)))
    assert any("head.png" in f.ir_path and "transparent" in f.description
               for f in _findings(char_dir, "error"))


def test_validate_blocks_an_unreadable_raster_part(tmp_path):
    char_dir = _package(tmp_path, head=lambda p: p.write_bytes(b"not an image"))
    assert any("head.png" in f.ir_path for f in _findings(char_dir, "error"))


def test_validate_advises_a_raster_part_with_no_alpha(tmp_path):
    char_dir = _package(tmp_path, head=lambda p: _png(p, (40, 40), mode="RGB"))
    assert any("head.png" in f.ir_path and "alpha" in f.description
               for f in _findings(char_dir, "warning"))
    assert not any("head.png" in f.ir_path for f in _findings(char_dir, "error"))


def test_validate_advises_a_colour_role_on_a_raster_part(tmp_path):
    char_dir = _package(tmp_path)
    doc = json.loads((char_dir / "character.json").read_text(encoding="utf-8"))
    doc["colour_roles"] = {"parts/head.png": {"#c81e1e": "skin"}}
    (char_dir / "character.json").write_text(json.dumps(doc), encoding="utf-8")
    assert any("raster" in f.description for f in _findings(char_dir, "warning"))


def test_an_embedded_image_in_an_svg_part_is_still_refused(tmp_path):
    """The route is a raster PART, not a raster inside an SVG: an `<image>`
    depends on the rasteriser and hides the pixels from every check here."""
    char_dir = _package(tmp_path)
    (char_dir / "parts" / "extra.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4" width="4" '
        'height="4"><image href="x.png" width="4" height="4"/><rect width="1" '
        'height="1"/></svg>', encoding="utf-8")
    assert any("<image>" in f.description and "parts/extra" in f.ir_path
               for f in _findings(char_dir, "error"))


def test_the_contract_documents_raster_parts():
    from cutan.characters.validate import render_contract

    text = render_contract()
    assert "## Raster parts" in text and ".png" in text


# --- 3. licences ---------------------------------------------------------------


@pytest.mark.parametrize(
    "code,cls",
    [
        ("pd", "free"), ("public domain", "free"), ("cc-pdm-1.0", "free"),
        ("cc0-1.0", "free"), ("all-rights-reserved", "private"),
        ("All rights reserved - private study only; never commit or publish", "private"),
        ("private-study", "private"), ("cc-by-4.0", "attribution"),
        ("(c) Some Studio. All rights reserved.", "private"),
        ("pdm-1.0", "free"), ("PD-US", "free"), ("mitigated", "unknown"),
        (None, "unknown"), ("bespoke", "unknown"),
    ],
)
def test_licence_classes(code, cls):
    from an.ir.assets import AssetSource, license_class

    assert license_class(AssetSource(provider="p", license=code)) == cls


def _credit_mall(tmp_path):
    from an.stores.environments import EnvironmentsStore
    from an.stores.props import PropsStore

    envs = EnvironmentsStore(tmp_path / "envs")
    envs["field"] = json.loads(EnvironmentDescriptor(
        name="field",
        planes=[
            Plane(name="plate", art=PlaneArt(kind="image", src="field.png")),
            Plane(name="basket", art=PlaneArt(kind="image", src="basket.png"),
                  source={"provider": "openclipart", "license": "cc0-1.0"}),
        ],
        source={"provider": "youtube", "id": "abc", "license": "all-rights-reserved",
                "url": "https://example.org/v/abc"},
    ).model_dump_json())
    envs["unused"] = {"name": "unused", "source": {"provider": "x",
                                                  "license": "all-rights-reserved"}}
    props = PropsStore(tmp_path / "props")
    props["sign"] = json.loads(PropDescriptor(
        name="sign", source={"provider": "wikimedia", "license": "pd"}
    ).model_dump_json())
    return {"environments": envs, "props": props}


def test_credits_say_private_study_loudly_and_credit_each_plane(tmp_path):
    from an.credits import collect_credits

    report = collect_credits(_credit_mall(tmp_path))
    assets = {e.asset: e.license_class for e in report.entries}
    assert assets["environments/field"] == "private"
    assert assets["environments/field/planes/basket"] == "free"
    assert assets["props/sign"] == "free"  # `pd` is no longer "unknown"
    assert not report.unverified and not report.publishable
    text = report.format()
    assert text.splitlines()[2].startswith("NOT PUBLISHABLE")
    assert "UNVERIFIED" not in text
    assert report.to_dict()["publishable"] is False


def test_a_render_owes_only_what_it_used(tmp_path):
    """A private-study plate sitting unused in the store must not make an
    unrelated render "not publishable"."""
    from an.credits import credits_for_scene, warn_if_private_study
    from an.ir.schema import Meta, SceneIR

    mall = _credit_mall(tmp_path)
    scene = SceneIR(meta=Meta(title="t", duration=1.0), timeline=[
        _shot(_prop_ref("sign"))
    ])
    report = credits_for_scene(mall, scene)
    assert [e.asset for e in report.entries] == ["props/sign"]
    assert warn_if_private_study(report) is False
    scene.timeline[0].entities.append(
        AssetRef(kind="environment", id="bg", store="environments", ref="field"))
    report = credits_for_scene(mall, scene)
    assert {e.asset for e in report.entries} == {
        "props/sign", "environments/field", "environments/field/planes/basket"}
    from an.credits import PrivateStudyWarning

    with pytest.warns(PrivateStudyWarning, match="NOT PUBLISHABLE"):
        assert warn_if_private_study(report, output="main.mp4")


def test_render_project_ends_with_the_private_study_warning(tmp_path, monkeypatch):
    """The warning is the LAST thing `render` does, after the file exists."""
    import an.render as render_mod

    src = Path(render_mod.__file__).read_text(encoding="utf-8")
    # `render` makes the film (`_render_film` writes the file), then reports
    # what it found (an#254), and only then checks the credits.
    body = src[src.index("def render("):src.index("def _render_film(")]
    assert body.index("_render_film(") < body.index("_write_render_report(")
    tail = body[body.rindex("_write_render_report("):]
    assert "credits_for_scene(project.mall, report_scene)" in tail
    assert "warn_if_private_study(report, output=output_path)" in tail
    assert tail.rstrip().endswith("return output_path")
    # …and a credits failure only warns: a finished render never fails on it
    assert "except Exception" in tail and "CreditsWarning" in tail


def test_staging_copies_the_file_a_versioned_src_names(tmp_path):
    """The digest rides in the URL's query; the staged file is the path."""
    from an.adapters.cutout.render import _stage_scene_assets

    store = _prop_store(tmp_path, parts={"lamp": ((50, 80), (10, 200, 10, 255))},
                        slot_default="lamp")
    scene = _compile(_shot(_prop_ref()), {"props": store}, strict_assets=True)
    out = tmp_path / "runtime"
    _stage_scene_assets(scene, {"props": store}, out)
    assert (out / "props" / "thing" / "parts" / "lamp.png").is_file()


def test_a_malformed_source_is_unverified_not_a_crash(tmp_path):
    """A render ends with a credits check; an unrelated store entry whose
    `source` is a bare string must not raise from it."""
    from an.credits import CreditsWarning, collect_credits, credits_for_scene
    from an.ir.schema import Meta, SceneIR

    mall = _credit_mall(tmp_path)
    mall["props"]["junk"] = {"name": "junk", "source": "found on the web"}
    with pytest.warns(CreditsWarning, match="junk"):
        report = collect_credits(mall)
    assert "props/junk" in [e.asset for e in report.unverified]
    scene = SceneIR(meta=Meta(title="t", duration=1.0), timeline=[_shot(_prop_ref("sign"))])
    with warnings.catch_warnings():
        warnings.simplefilter("error", CreditsWarning)  # the unused entry is never read
        assert [e.asset for e in credits_for_scene(mall, scene).entries] == ["props/sign"]


def test_a_plane_without_a_source_stores_no_source_key():
    doc = json.loads(EnvironmentDescriptor(name="e", planes=[Plane(name="a")]).model_dump_json())
    assert "source" not in doc["planes"][0]


# --- 4. empty props, and draw order -------------------------------------------


def test_a_prop_with_no_skin_is_a_fallback_loud_by_default_fatal_when_strict(tmp_path):
    from an.stores.props import PropsStore

    store = PropsStore(tmp_path / "props")
    store["thing"] = json.loads(PropDescriptor(name="thing").model_dump_json())
    with pytest.warns(CutoutCompileWarning, match="draws NOTHING"):
        compile_shot(_shot(_prop_ref()), mall={"props": store}, fps=4, width=W, height=H)
    with pytest.raises(CutoutCompileError, match="draws NOTHING"):
        compile_shot(_shot(_prop_ref()), mall={"props": store}, fps=4, width=W,
                     height=H, strict_assets=True)


def test_a_prop_listed_before_a_character_draws_behind_it(tmp_path):
    """Props and characters share one loop in ENTITY order, so the author puts
    a prop behind a character by listing it first — nothing new to learn."""
    store = _prop_store(tmp_path, parts={"lamp": ((50, 80), (10, 200, 10, 255))},
                        slot_default="lamp")
    char = AssetRef(kind="character", id="bob", store="characters", ref="bob")
    mall = {"props": store, "characters": {"bob": {"name": "bob",
                                                   "parts": ["head", "torso"]}}}
    behind = _compile(_shot(_prop_ref(), char), mall)
    front = _compile(_shot(char, _prop_ref()), mall)
    assert [c.name for c in behind.scene.children] == ["thing", "bob"]
    assert [c.name for c in front.scene.children] == ["bob", "thing"]


# --- 5. framing ------------------------------------------------------------------


def _framing(tmp_path, planes, *, camera=None, env_kw=None):
    from an.ir.schema import Meta, Resolution, SceneIR
    from an.ir.validate import validate_semantic

    store = _env_store(tmp_path, planes, **(env_kw or {}))
    scene = SceneIR(
        meta=Meta(title="t", duration=2.0, resolution=Resolution(width=W, height=H)),
        timeline=[_shot(_env_ref(), camera=camera, duration=2.0)],
    )
    report = validate_semantic(scene, available_environments=store)
    return [f for f in report.findings if "edge of the plate" in f.description]


def _plate(size, **kw):
    return Plane(name="plate", art=PlaneArt(kind="image", src="plate.png"),
                 size=size, fit="stretch", **kw)


def test_a_plate_that_fills_the_frame_is_fine_until_the_camera_pulls_out(tmp_path):
    _png(tmp_path / "envs" / "street" / "plate.png", (64, 36))
    exact = [_plate((W, H))]
    assert not _framing(tmp_path, exact)
    assert not _framing(tmp_path, exact, camera=Camera(move="push_in"))
    found = _framing(tmp_path, exact, camera=Camera(move="pull_out"))
    assert len(found) == 1 and "zoom 0.8" in found[0].description


def test_a_close_up_off_centre_shows_the_edge_it_approaches(tmp_path):
    """The reported shape: zoomed in, but moved down past the plate's bottom."""
    _png(tmp_path / "envs" / "street" / "plate.png", (64, 36))
    keys = [CameraKey(at=0.0), CameraKey(at=2.0, y=60.0, zoom=1.5)]
    found = _framing(tmp_path, [_plate((W, H))], camera=Camera(keys=keys))
    assert found and "bottom" in found[0].description


def test_parallax_is_part_of_the_coverage(tmp_path):
    """A pan over a frame-sized plate shows its edge at depth 1 (it moves with
    the world) and does not at depth 0 (it is pinned in frame)."""
    _png(tmp_path / "envs" / "street" / "plate.png", (64, 36))
    pan = Camera(move="pan_right")
    assert _framing(tmp_path, [_plate((W, H), depth=1.0)], camera=pan)
    assert not _framing(tmp_path, [_plate((W, H), depth=0.0)], camera=pan)


def test_the_union_of_planes_counts_and_a_fill_covers(tmp_path):
    _png(tmp_path / "envs" / "street" / "plate.png", (64, 36))
    halves = [
        _plate((W / 2, H), offset=(-W / 4, 0.0)),
        Plane(name="right", art=PlaneArt(kind="image", src="plate.png"),
              size=(W / 2, H), fit="stretch", offset=(W / 4, 0.0)),
    ]
    assert not _framing(tmp_path, halves)
    assert _framing(tmp_path, halves[:1])
    sky = [Plane(name="sky", art=PlaneArt(kind="fill", color="#88aaff"))]
    assert not _framing(tmp_path, sky + halves[:1], camera=Camera(move="pull_out"))


def test_a_fill_plane_is_placed_centred_as_the_compiler_draws_it(tmp_path):
    """The compiler emits a fill as a centred rect whatever its `anchor`, so
    the framing geometry must too — or it vouches for a frame half empty."""
    fill = Plane(name="band", art=PlaneArt(kind="fill", color="#88aaff"),
                 size=(W, H), offset=(0.0, -H / 2), anchor=(0.5, 0.0))
    found = _framing(tmp_path, [fill])
    assert found and "bottom" in found[0].description


def test_a_truncated_header_is_a_raster_format_error(tmp_path):
    from an.raster import RasterFormatError, has_alpha, image_size

    (tmp_path / "t.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8X\x00")
    with pytest.raises(RasterFormatError):
        image_size(tmp_path / "t.webp")
    assert has_alpha(tmp_path / "t.webp") is None


def test_framing_is_silent_when_it_cannot_know(tmp_path):
    """An unmeasurable plate is an unknown, not a hole."""
    missing = [Plane(name="plate", art=PlaneArt(kind="image", src="nope.png"))]
    assert not _framing(tmp_path, missing, camera=Camera(move="pull_out"))


# --- 6. per-key swap geometry -----------------------------------------------------


MOUTH_PARTS = {
    "closed": ((120, 8), (200, 30, 30, 255)),
    "open": ((120, 60), (30, 30, 200, 255)),
}


def test_a_key_on_a_bigger_canvas_carries_its_own_box(tmp_path):
    store = _prop_store(tmp_path, parts=MOUTH_PARTS, slot_default="closed",
                        asset_sets={"mouth": {"X": "closed", "A": "open"}})
    scene = _compile(_shot(_prop_ref()), {"props": store}, strict_assets=True)
    visual = _node(scene, "thing", "body").visual
    assert (visual.width, visual.height) == (120.0, 8.0)
    (alias, geometry), = visual.asset_geometry.items()
    assert alias.startswith("thing.body.open.")
    assert geometry == {"width": 120.0, "height": 60.0, "anchor_x": 0.5,
                        "anchor_y": 0.5, "x": 0.0, "y": 0.0}


def test_keys_that_share_a_canvas_emit_no_geometry_at_all(tmp_path):
    """Byte-identity for every rig drawn the conventional way."""
    from an.adapters.cutout.serialize import to_dict

    parts = {"closed": ((120, 60), (200, 30, 30, 255)),
             "open": ((120, 60), (30, 30, 200, 255))}
    store = _prop_store(tmp_path, parts=parts, slot_default="closed",
                        asset_sets={"mouth": {"X": "closed", "A": "open"}})
    scene = _compile(_shot(_prop_ref()), {"props": store}, strict_assets=True)
    assert "asset_geometry" not in json.dumps(to_dict(scene))


def test_the_runtime_applies_a_key_s_geometry_and_restores_the_built_one():
    """Executed against the real extracted functions under node."""
    import re
    import shutil

    from tests._node import run_node
    from an.adapters.cutout.runtime_files import runtime_dir

    if shutil.which("node") is None:
        pytest.skip("node not installed")
    src = (runtime_dir() / "runtime.js").read_text(encoding="utf-8")

    def extract(name):
        m = re.search(rf"function {name}\([^)]*\)\s*\{{.*?\n    \}}", src, re.S)
        assert m, name
        return m.group(0)

    script = "\n".join([
        "const PIXI = { Assets: { get: (id) => ({ id, orig: { width: id === 'o' ? 120 : 120,"
        " height: id === 'o' ? 60 : 8 } }) } };",
        extract("refitToBox"), extract("unknownSwapKey"), extract("applyKeyGeometry"),
        extract("applySwap"),
        "const s = { anchor: { set(x, y) { this.x = x; this.y = y; } }, scale: { set(x, y)"
        " { this.x = x; this.y = y; } }, x: 0, y: 0 };",
        "s.texture = PIXI.Assets.get('c'); s._anFitBox = [120, 8];",
        "s._anAssetSets = { mouth: { X: 'c', A: 'o' } };",
        "s._anAssetGeometry = { o: { width: 120, height: 60, anchor_x: 0.5, anchor_y: 1,"
        " x: 3, y: -4 } };",
        "s._anBuiltGeometry = { width: 120, height: 8, anchor_x: 0.5, anchor_y: 0.5, x: 0,"
        " y: 0, fit: 'contain' };",
        "const node = { name: 'thing/body' };",
        "applySwap(s, node, 'mouth', 'A');",
        "const open = { box: s._anFitBox, scale: s.scale.y, anchor: s.anchor.y, x: s.x, y: s.y };",
        "applySwap(s, node, 'mouth', 'X');",
        "const closed = { box: s._anFitBox, scale: s.scale.y, anchor: s.anchor.y, x: s.x, y: s.y };",
        "console.log(JSON.stringify({ open, closed }));",
    ])
    proc = run_node(script)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout.strip())
    # open: its own 120x60 box, so scale 1 — not squashed to 8/60
    assert got["open"] == {"box": [120, 60], "scale": 1, "anchor": 1, "x": 3, "y": -4}
    assert got["closed"] == {"box": [120, 8], "scale": 1, "anchor": 0.5, "x": 0, "y": 0}


# --- pixels -------------------------------------------------------------------------


def _render(shot, mall, tmp_path, **kw):
    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer

    return CutoutRenderer().render(
        shot,
        RenderContext(mall=mall, work_dir=tmp_path / "out", fps=4, resolution=(W, H),
                      strict_assets=True, **kw),
    )


def _pixel(frame, x, y):
    from PIL import Image

    return Image.open(frame).convert("RGB").getpixel((x, y))


def _near(got, want, tol=6):
    return all(abs(g - w) <= tol for g, w in zip(got, want))


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_a_png_plate_and_a_png_part_render_where_the_document_says(tmp_path):
    """A 64x36 two-colour PNG plate stretched to the frame by its declared
    size, and a PNG prop with a transparent surround and an outline: the
    plate's halves, the prop's opaque core, the plate through its transparent
    margin, and the outline band are each where they should be."""
    from an.styles import StylePack

    left, right = (220, 120, 40), (40, 120, 220)
    _png(tmp_path / "envs" / "street" / "plate.png", (64, 36),
         lambda x, y: (*(left if x < 32 else right), 255))
    envs = _env_store(tmp_path, [_plate((W, H), depth=0.0)])
    core = (30, 200, 60)
    props = _prop_store(
        tmp_path,
        parts={"lamp": ((60, 60),
                        lambda x, y: (*core, 255) if 15 <= x < 45 and 15 <= y < 45
                        else (0, 0, 0, 0))},
        slot_default="lamp",
    )
    pack = StylePack(name="p", surface={"outline": {"width": 3, "color": "#ff00ff"}})
    result = _render(_shot(_env_ref(), _prop_ref("thing")),
                     {"environments": envs, "props": props}, tmp_path, style_pack=pack)
    frame = result.frame_manifest[0]
    cx, cy = W // 2, H // 2
    assert _near(_pixel(frame, 10, 10), left), "left half of the plate"
    assert _near(_pixel(frame, W - 10, 10), right), "right half of the plate"
    assert _near(_pixel(frame, cx, cy), core), "the prop's opaque core"
    # the prop's transparent margin shows the plate (x = cx - 20 is inside the
    # 60 px part but outside its 30 px core and outside the 3 px outline)
    assert _near(_pixel(frame, cx - 25, cy), left), "the plate through the PNG's alpha"
    # 1 px outside the core's left edge: the outline copy, whose tint is a
    # MULTIPLY over the part's own pixels — magenta keeps red and blue and
    # zeroes green, exactly as on SVG art — not the plate
    band = _pixel(frame, cx - 16, cy)
    assert _near(band, (core[0], 0, core[2])), ("outline band", band)


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_a_swapped_key_is_drawn_exactly_as_if_it_were_the_default(tmp_path):
    """The Reiniger failure: a closed mouth on a 120x8 canvas and an open one
    on 120x60. Swapped to open, the picture must equal the rig DRAWN open —
    before an#211 the open mouth was fitted into the closed one's box, 8 px
    tall."""
    import numpy as np
    from PIL import Image

    frames = {}
    for variant in ("drawn", "swapped"):
        root = tmp_path / variant
        store = _prop_store(root, parts=MOUTH_PARTS,
                            slot_default="open" if variant == "drawn" else "closed",
                            asset_sets={"mouth": {"X": "closed", "A": "open"}})
        actions = (
            [SetAction(kind="set", target="thing", property="mouth", value="A", at=0.0)]
            if variant == "swapped" else []
        )
        # the swap targets the slot the set projects onto
        actions = [a.model_copy(update={"target": "thing/body"}) for a in actions]
        result = _render(_shot(_prop_ref(), actions=actions), {"props": store}, root)
        frames[variant] = np.asarray(
            Image.open(result.frame_manifest[-1]).convert("RGB"))
    assert np.array_equal(frames["drawn"], frames["swapped"])
    blue = (frames["swapped"][..., 2] > 150) & (frames["swapped"][..., 0] < 80)
    rows = np.nonzero(blue.any(axis=1))[0]
    assert rows.size and rows[-1] - rows[0] + 1 >= 55, "the open mouth is its own height"


# --- an#218: EXIF orientation ------------------------------------------------


def _jpeg(path: Path, size, rgb, *, orientation=None) -> Path:
    """A JPEG with an EXIF orientation tag; ``rgb`` may be a callable (x, y) -> colour."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size)
    im.putdata([rgb(x, y) for y in range(size[1]) for x in range(size[0])])
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    im.save(path, "JPEG", quality=95, exif=exif.tobytes())
    return path


@pytest.mark.parametrize(
    "orientation, size", [(None, (60, 30)), (1, (60, 30)), (3, (60, 30)), (6, (30, 60)), (8, (30, 60))]
)
def test_a_jpeg_box_is_its_displayed_size(tmp_path, orientation, size):
    from an.stage.raster import image_size

    path = _jpeg(tmp_path / "p.jpg", (60, 30), lambda x, y: (200, 30, 30), orientation=orientation)
    assert image_size(path) == tuple(float(v) for v in size)


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_an_exif_rotated_jpeg_part_is_drawn_upright_in_its_box(tmp_path):
    """Stored 120x60 (left half green, right half blue) with orientation 6
    (rotate 90 degrees clockwise to display): drawn 60 wide and 120 tall,
    green on top — the box the compiler declares is the one Chromium draws."""
    import numpy as np
    from PIL import Image

    from an.stores.props import PropsStore

    green, blue = (30, 200, 60), (40, 60, 220)
    _jpeg(tmp_path / "props" / "thing" / "parts" / "photo.jpg", (120, 60),
          lambda x, y: green if x < 60 else blue, orientation=6)
    store = PropsStore(tmp_path / "props")
    data = json.loads(PropDescriptor(
        name="thing", view_box=VIEW_BOX,
        skins={"default": Skin(slots={"body": {"photo": Attachment(path="parts/photo.jpg")}})},
    ).model_dump_json())
    data["slots"][0]["attachment"] = "photo"
    store["thing"] = data
    frame = _render(_shot(_prop_ref("thing")), {"props": store}, tmp_path).frame_manifest[0]
    rgb = np.asarray(Image.open(frame).convert("RGB")).astype(int)
    drawn = (np.abs(rgb - rgb[0, 0]).sum(axis=-1) > 60)
    rows, cols = np.flatnonzero(drawn.any(axis=1)), np.flatnonzero(drawn.any(axis=0))
    height, width = rows[-1] - rows[0] + 1, cols[-1] - cols[0] + 1
    assert height == pytest.approx(120, abs=4) and width == pytest.approx(60, abs=4)
    top = rgb[rows[0] + 10, (cols[0] + cols[-1]) // 2]
    bottom = rgb[rows[-1] - 10, (cols[0] + cols[-1]) // 2]
    assert _near(tuple(top), green, tol=40) and _near(tuple(bottom), blue, tol=40)
