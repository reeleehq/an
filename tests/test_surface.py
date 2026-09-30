"""Surface treatments as compile-time expansions (an#163 gap 5).

Checked where each can fail:

- byte identity: a pack that sets no treatment, and a scene with no pack,
  compile exactly as before (the corpus guard is
  `test_expression_compose.py::test_every_corpus_contract_hash_equals_the_committed_ledger_row`;
  here the same rule is checked on a scene that DOES have a pack);
- the document: which parts get an outline and a shadow, in what order, as
  what copies; the glow node; the grain tile and its PNG bytes;
- "follows its source with no extra channels": animations and the timeline
  are identical with and without every treatment;
- the pack: key-by-key per-entity override, and a dump that means the same
  thing when read back;
- pixels (browser lane): an outline band, a paper-gap shadow and the grain
  land exactly where and as the document says, and a tween on the part moves
  its outline with it.
"""

from __future__ import annotations

import io
import shutil
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import (
    _PLACEHOLDER_PARTS,
    CutoutCompileWarning,
    compile_shot,
)
from an.adapters.cutout.serialize import from_dict, to_dict
from an.adapters.cutout.surface import (
    GLOW_NODE,
    GRAIN_NODE,
    OUTLINE_RING,
    grain_greys,
    grain_indices,
    grain_png,
    ring_offsets,
)
from an.ir.schema import AssetRef, Shot, TweenAction
from an.styles import StylePack, SurfaceTreatment, surface_for

W, H = 640, 360
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "characters" / "gale"


def _shot(*entities, actions=(), duration=1.0) -> Shot:
    return Shot(
        id="s1",
        renderer="cutout",
        duration=duration,
        entities=list(entities)
        or [
            AssetRef(kind="environment", id="room", store="environments", ref="park"),
            AssetRef(kind="character", id="charlie", store="characters", ref="c"),
        ],
        actions=list(actions),
    )


def _char(eid: str, ref: str = "c") -> AssetRef:
    return AssetRef(kind="character", id=eid, store="characters", ref=ref)


def _compile(shot=None, pack=None, mall=None, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CutoutCompileWarning)
        return compile_shot(
            shot or _shot(), mall, fps=24, width=W, height=H, style_pack=pack, **kw
        )


def _node(doc, path: str):
    node = doc.scene
    for name in path.split("/"):
        node = next(c for c in node.children if c.name == name)
    return node


ALL = {"outline": {}, "shadow": {}, "glow": {}}


# --- byte identity -----------------------------------------------------------


@pytest.mark.parametrize(
    "pack",
    [
        StylePack(name="p"),
        StylePack(name="p", surface={}),
        StylePack(name="p", surface={"outline": None}),
        StylePack(name="p", surface=ALL, entity_surfaces={"charlie": SurfaceTreatment(
            outline=None, shadow=None, glow=None)}),
    ],
    ids=["no-treatments", "empty-surface", "outline-null", "all-switched-off"],
)
def test_a_pack_that_draws_no_treatment_compiles_exactly_as_no_pack(pack):
    plain = to_dict(_compile(pack=None))
    doc = to_dict(_compile(pack=pack))
    doc["meta"].pop("style_pack")
    assert doc == plain


def test_unset_wire_fields_are_omitted_and_set_ones_round_trip():
    plain = to_dict(_compile())

    def visuals(node):
        if node.get("visual"):
            yield node["visual"]
        for c in node.get("children", []):
            yield from visuals(c)

    assert all("underlays" not in v and "blend" not in v for v in visuals(plain["scene"]))
    doc = _compile(pack=StylePack(name="p", surface=ALL, grain={}))
    assert from_dict(to_dict(doc)) == doc


# --- which parts, which copies ------------------------------------------------


def test_procedural_parts_get_the_shadow_then_the_outline_as_grown_shapes():
    doc = _compile(pack=StylePack(name="p", surface={"outline": {"width": 2.5}, "shadow": {}}))
    torso = _node(doc, "charlie/torso").visual
    shadow, outline = torso.underlays  # back to front
    assert (shadow.color, shadow.alpha, shadow.offsets, shadow.grow) == (
        "#000000", 0.35, [(4.0, 4.0)], 2.5)
    assert (outline.color, outline.alpha, outline.offsets, outline.grow) == (
        "#1a1a1a", 1.0, [(0.0, 0.0)], 2.5)


def test_nested_parts_and_kinds_without_copies_are_left_alone_by_default():
    doc = _compile(pack=StylePack(name="p", surface={"outline": {}, "shadow": {}}))
    head = _node(doc, "charlie/head")
    assert head.visual.underlays
    assert all(c.visual.underlays is None for c in head.children)


def test_nested_true_reaches_face_features_but_never_an_eye_or_a_mouth():
    doc = _compile(pack=StylePack(name="p", surface={"outline": {"nested": True}}))
    head = _node(doc, "charlie/head")
    got = {c.name: c.visual.underlays is not None for c in head.children}
    assert got == {"hair": True, "left_brow": True, "right_brow": True,
                   "left_eye": False, "right_eye": False, "mouth": False}


def test_an_svg_part_gets_a_ring_of_texture_copies(tmp_path):
    from an.stores.characters import CharactersStore

    shutil.copytree(FIXTURE, tmp_path / "gale")
    mall = {"characters": CharactersStore(tmp_path)}
    doc = _compile(_shot(_char("gale", "gale")),
                   StylePack(name="p", surface={"outline": {"width": 2}, "shadow": {}}), mall)
    parts = _node(doc, "gale").children
    assert parts and all(p.visual.kind == "svg_sprite" for p in parts)
    for p in parts:
        shadow, outline = p.visual.underlays
        assert outline.offsets == ring_offsets(2.0) and len(outline.offsets) == OUTLINE_RING
        assert outline.grow == 0.0
        # the shadow is ONE copy (translucent copies would compound), grown to
        # the outlined silhouette so it shows past the outline
        assert shadow.offsets == [(4.0, 4.0)] and shadow.grow == 2.0
    # face features are nested under the head and untouched by default
    for p in parts:
        assert all(c.visual.underlays is None for c in p.children)


def test_ring_offsets_are_exact_unit_directions():
    offs = ring_offsets(3.0)
    assert all(abs((x * x + y * y) ** 0.5 - 3.0) < 1e-5 for x, y in offs)
    assert offs[0] == (3.0, 0.0) and offs[2] == (0.0, 3.0) and offs[4] == (-3.0, 0.0)


# --- no extra channels --------------------------------------------------------


def test_every_treatment_follows_its_part_with_no_channel_of_its_own():
    """The copies live in the part's own container and the glow in the
    entity's, so the animation half of the document must not move at all."""
    actions = [
        TweenAction(kind="tween", target="charlie/right_arm", property="rotation",
                    start=0.0, duration=1.0, from_value=0.0, to_value=1.0),
        TweenAction(kind="tween", target="charlie", property="x",
                    start=0.0, duration=1.0, from_value=0.0, to_value=80.0),
    ]
    plain = to_dict(_compile(_shot(actions=actions)))
    treated = to_dict(_compile(_shot(actions=actions),
                               StylePack(name="p", surface=ALL, grain={})))
    assert treated["animations"] == plain["animations"]
    assert treated["timeline"] == plain["timeline"]


# --- glow ---------------------------------------------------------------------


def test_the_glow_is_the_entitys_first_child_an_additive_gradient_on_its_box():
    doc = _compile(pack=StylePack(name="p", surface={"glow": {"radius": 20}}))
    ent = _node(doc, "charlie")
    glow = ent.children[0]
    assert glow.name == GLOW_NODE and glow.visual.blend == "add"
    assert glow.visual.underlays is None  # never outlined itself
    src = doc.assets.textures[glow.visual.asset_id].src
    assert src.startswith("data:image/svg+xml;base64,")
    # procedural rig box: x -65..65 (arms), y -84 (hair top) .. 40 (torso bottom)
    assert (glow.transform.x, glow.transform.y) == (0.0, -22.0)
    assert (glow.visual.width, glow.visual.height) == (130.0 + 40, 124.0 + 40)


# --- per-entity override --------------------------------------------------------


def test_a_per_entity_override_is_key_by_key():
    pack = StylePack(
        name="p",
        surface={"outline": {}, "shadow": {}},
        entity_surfaces={"bob": {"outline": None}, "sun": {"glow": {}}},
    )
    doc = _compile(_shot(_char("maya"), _char("bob"), _char("sun")), pack)
    maya, bob, sun = (_node(doc, n) for n in ("maya", "bob", "sun"))
    assert len(_node(doc, "maya/torso").visual.underlays) == 2
    assert [u.alpha for u in _node(doc, "bob/torso").visual.underlays] == [0.35]  # shadow only
    assert sun.children[0].name == GLOW_NODE
    assert GLOW_NODE not in {c.name for c in maya.children + bob.children}


def test_a_dumped_pack_reads_back_meaning_the_same_thing():
    pack = StylePack(name="p", surface={"outline": {}, "shadow": {"dx": 2}},
                     entity_surfaces={"sun": {"glow": {}}, "bob": {"outline": None}},
                     grain={"seed": 7})
    again = StylePack.model_validate_json(pack.model_dump_json())
    for eid in ("sun", "bob", "maya"):
        assert surface_for(again, eid) == surface_for(pack, eid)
    assert again.grain == pack.grain


def test_a_treatment_refuses_a_key_it_does_not_have_or_a_bad_colour():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        StylePack(name="p", surface={"outline": {"widht": 2}})
    with pytest.raises(pydantic.ValidationError):
        StylePack(name="p", surface={"shadow": {"color": "black"}})


def test_a_surface_only_pack_does_not_warn_about_colour_it_never_asked_for(tmp_path):
    from an.stores.characters import CharactersStore

    shutil.copytree(FIXTURE, tmp_path / "gale")
    with warnings.catch_warnings():
        warnings.simplefilter("error", CutoutCompileWarning)
        compile_shot(_shot(_char("gale", "gale")), {"characters": CharactersStore(tmp_path)},
                     fps=24, style_pack=StylePack(name="p", surface={"outline": {}}))


# --- grain ----------------------------------------------------------------------


def test_the_grain_tiles_the_frame_first_on_the_overlay():
    doc = _compile(pack=StylePack(name="p", grain={"tile": 256}))
    grain = doc.overlay.children[0]
    assert grain.name == GRAIN_NODE
    assert len(grain.children) == 3 * 2  # ceil(640/256) x ceil(360/256)
    xs = sorted({t.transform.x for t in grain.children})
    ys = sorted({t.transform.y for t in grain.children})
    assert xs == [-320.0, -64.0, 192.0] and ys == [-180.0, 76.0]
    assert {t.visual.blend for t in grain.children} == {"multiply"}
    assert len({t.visual.asset_id for t in grain.children}) == 1


def test_the_grain_png_is_the_seeded_palette_exactly():
    from PIL import Image

    png = grain_png(seed=3, amount=0.1, tile=32)
    im = Image.open(io.BytesIO(png))
    assert im.mode == "P" and im.size == (32, 32)
    greys = grain_greys(0.1)
    expected = [greys[i] for i in grain_indices(3, 32)]
    assert list(im.convert("L").getdata()) == expected
    assert min(greys) == round(255 * 0.9) and max(greys) == 255


def test_the_grain_bytes_do_not_depend_on_the_zlib_build():
    """STORED deflate blocks: BTYPE 00 after the zlib header, so the bytes are
    the seed's and nobody's compressor's."""
    png = grain_png(seed=0, amount=0.06, tile=64)
    idat = png.index(b"IDAT") + 4
    assert png[idat : idat + 2] == b"\x78\x01"
    assert (png[idat + 2] >> 1) & 0b11 == 0
    assert grain_png(seed=0, amount=0.06, tile=64) == png != grain_png(seed=1, amount=0.06, tile=64)


# --- pixels ---------------------------------------------------------------------


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_outline_shadow_and_grain_land_where_the_document_says(tmp_path):
    """On white, with a magenta outline: the band beside the right arm is
    magenta, the zone past it is the half-alpha shadow, the corner is plain
    paper — each multiplied by the grain texel at that exact pixel. Then a
    tween on the ARM (and on nothing else) has moved the band with it."""
    from PIL import Image

    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer

    width, dx, tile = 4.0, 8.0, 64
    pack = StylePack(
        name="p",
        surface={"outline": {"width": width, "color": "#ff00ff"},
                 "shadow": {"dx": dx, "dy": dx, "alpha": 0.5}},
        grain={"amount": 0.2, "seed": 11, "tile": tile},
    )
    shot = _shot(
        _char("charlie"),
        actions=[TweenAction(kind="tween", target="charlie/right_arm", property="x",
                             start=0.0, duration=0.5, from_value=50.0, to_value=90.0)],
    )
    # The procedural rig DECLARED, so it is a choice rather than an#33's stand-in.
    mall = {"characters": {"c": {"name": "c", "parts": list(_PLACEHOLDER_PARTS)}}}
    result = CutoutRenderer().render(
        shot,
        RenderContext(mall=mall, work_dir=tmp_path, fps=4, resolution=(W, H),
                      style_pack=pack, strict_assets=True),
    )
    greys = grain_greys(0.2)
    idx = grain_indices(11, tile)

    def paper(x, y):
        return greys[idx[(y % tile) * tile + (x % tile)]] / 255

    def check(frame, x, y, rgb, what):
        got = Image.open(frame).convert("RGB").getpixel((x, y))
        want = tuple(round(c * paper(x, y)) for c in rgb)
        assert all(abs(g - w) <= 2 for g, w in zip(got, want)), (what, x, y, got, want)

    first, last = result.frame_manifest[0], result.frame_manifest[-1]
    cx, cy = W // 2, H // 2
    edge = cx + 50 + 15  # the right arm's right edge: x 50, width 30
    y = cy - 10  # the arm's middle: y -10, height 70
    check(first, edge + 2, y, (255, 0, 255), "outline band")
    check(first, edge + int(width) + 4, y, (128, 128, 128), "shadow past the outline")
    check(first, 5, 5, (255, 255, 255), "plain paper under the grain")
    # t = 0.75 s: the arm has moved +40 px; its outline band went with it
    check(last, edge + 40 + 2, y, (255, 0, 255), "outline band after the tween")
    check(last, edge + 2, y, (255, 255, 255), "the band's old place is paper again")
