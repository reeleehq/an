"""A halo under a text block: tituli's `Halo`, drawn as an SVG underlay (an#701).

`halo` on a `TextDescriptor` is tituli's own value type, so the two packages
share one vocabulary. Each unit's texture draws the glyphs' alpha dilated
(`feMorphology`, `spread` em), blurred (`feGaussianBlur`, `blur` em), boosted
by `gain` and laid in the halo's colour (or the opposite of the ink) at
`opacity`, under the outline and the fill. It is refused for an engine that
does not afford those SVG filters; a tituli run that arrives carrying a halo
(an#682's refusal) is now drawn; tituli plates are refused by name.
"""

from __future__ import annotations

import base64
import dataclasses
import warnings

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.adapters.cutout.serialize import to_dict
from an.ir.schema import AssetRef, Meta, SceneIR, Shot
from an.text import (
    HALO_FILTER_PRIMITIVES,
    TextDescriptor,
    TextHaloWarning,
    TextLayoutError,
    halo_paint,
    layout_text,
)

W, H = 320, 240

#: A halo spelled for parametrize without importing tituli at collection (it
#: pulls Pillow, an optional dependency, tests/test_browser_gate.py): built
#: inside the test by :func:`_halo`.
_TITULI_HALO = "tituli.Halo"


def Halo(**fields):
    """tituli's ``Halo``, imported when a test runs, not when it is collected."""
    from tituli import Halo as _Halo

    return _Halo(**fields)


def _halo(spec):
    """A parametrize spec as a value: ``(_TITULI_HALO, fields)`` is a ``Halo``."""
    if isinstance(spec, tuple) and spec[:1] == (_TITULI_HALO,):
        return Halo(**spec[1])
    return spec


# --- the document ------------------------------------------------------------


@pytest.mark.parametrize(
    "halo, expected",
    [
        (True, (_TITULI_HALO, {})),
        ({"blur": 0.2, "opacity": 1.0}, (_TITULI_HALO, {"blur": 0.2, "opacity": 1.0})),
        ((_TITULI_HALO, {"color": "#ffd400"}), (_TITULI_HALO, {"color": "#ffd400"})),
        ({"color": [255, 212, 0]}, (_TITULI_HALO, {"color": (255, 212, 0)})),
        (None, None),
        (False, None),
    ],
)
def test_halo_is_tituli_s_own_value(halo, expected):
    halo, expected = _halo(halo), _halo(expected)
    desc = TextDescriptor(name="t", text="hi", halo=halo)
    assert desc.halo == expected
    again = TextDescriptor.model_validate_json(desc.model_dump_json())
    assert again.halo == expected


@pytest.mark.parametrize(
    "halo, needle",
    [
        ({"glow": 1}, r"has no field\(s\) \['glow'\]"),
        ({"spread": -0.1}, "negative spread"),
        ({"opacity": 1.5}, r"outside \[0, 1\]"),
        ({"blur": "0.1"}, "takes a number"),
        ({"color": "not-a-colour"}, "not a colour tituli reads"),
        ("yes", "takes true, a mapping"),
    ],
)
def test_the_document_refuses_a_halo_tituli_would_not_draw(halo, needle):
    with pytest.raises(ValueError, match=needle):
        TextDescriptor(name="t", text="hi", halo=halo)


def test_a_tituli_from_before_halo_is_named(monkeypatch):
    """An older tituli has no ``Halo``: the bare ImportError becomes the
    typed refusal naming the version needed."""
    import sys
    import types

    monkeypatch.setitem(sys.modules, "tituli", types.ModuleType("tituli"))
    with pytest.raises(ValueError, match=r"needs tituli >= 0\.0\.13"):
        TextDescriptor(name="t", text="hi", halo=True)


def test_without_a_halo_nothing_changes():
    plain = TextDescriptor(name="t", text="hi")
    assert "halo" not in plain.model_dump()
    a = layout_text(plain, width=W, height=H)
    assert all(u.halo is None for u in a.units)


# --- tituli's semantics ------------------------------------------------------


def test_the_halo_is_sized_in_em_and_coloured_as_tituli_does():
    """tituli rounds the dilation to whole pixels, keeps the blur exact and
    picks the opposite of the ink when the halo names no colour."""
    from tituli.color import ink_for, relative_luminance

    em = 48
    on_white = halo_paint(Halo(), em=em, ink="#ffffff")
    assert on_white.spread == round(Halo().spread * em) == 1
    assert on_white.blur == pytest.approx(Halo().blur * em)
    assert on_white.gain == Halo().gain and on_white.alpha == Halo().opacity
    r, g, b = ink_for(luminance=relative_luminance("#ffffff"))
    assert on_white.color == f"#{r:02x}{g:02x}{b:02x}"
    assert halo_paint(Halo(), em=em, ink="#1a1a1a").color == "#ffffff"
    assert halo_paint(Halo(color="#ffd400"), em=em, ink="#1a1a1a").color == "#ffd400"


def test_each_unit_box_grows_by_the_glow_s_reach():
    plain = layout_text(
        TextDescriptor(name="t", text="SAND DUNE", size=0.2), width=W, height=H
    )
    glowing = layout_text(
        TextDescriptor(name="t", text="SAND DUNE", size=0.2, halo=True),
        width=W,
        height=H,
    )
    for p, g in zip(plain.units, glowing.units):
        reach = g.halo.reach
        assert reach == g.halo.spread + 3 * 5  # ceil(3 x 4.8 px)
        assert g.box == (
            p.box[0] - reach,
            p.box[1] - reach,
            p.box[2] + reach,
            p.box[3] + reach,
        )
        assert (g.center, g.d) == (p.center, p.d)


def _shot(*entities, renderer="stage") -> Shot:
    return Shot(id="s", renderer=renderer, duration=1.0, entities=list(entities))


def _entity(eid="l", ref="l") -> AssetRef:
    return AssetRef(kind="prop", id=eid, store="props", ref=ref)


def _svg(doc, alias) -> str:
    src = to_dict(doc)["assets"]["textures"][alias]["src"]
    return base64.b64decode(src.split(",", 1)[1]).decode()


def _haloed_mall(**fields):
    doc = {"kind": "TextDescriptor", "name": "l", "text": "SAND DUNE", "size": 0.2,
           "color": "#ffffff", "halo": True, **fields}  # fmt: skip
    return {"props": {"l": doc}}


def test_the_glow_is_under_the_outline_under_the_fill_in_the_unit_s_own_texture():
    """One texture per word holding all three, so `word_1:alpha` hides its glow too."""
    mall = _haloed_mall(stroke_width=2.0, stroke_color="#1c1c1c")
    doc = compile_shot(_shot(_entity()), mall, width=W, height=H)
    (block,) = to_dict(doc)["scene"]["children"]
    assert [c["name"] for c in block["children"]] == ["word_0", "word_1"]
    for word in block["children"]:
        svg = _svg(doc, word["visual"]["asset_id"])
        glow = svg.index('filter="url(#halo)"')
        assert glow < svg.index('stroke="#1c1c1c"') < svg.index('fill="#ffffff"')
        for primitive in HALO_FILTER_PRIMITIVES:
            assert f"<{primitive}" in svg, primitive
        assert 'in="SourceAlpha"' in svg and 'operator="dilate" radius="1"' in svg
        assert 'stdDeviation="4.8"' in svg and 'slope="2"' in svg
        assert 'flood-color="#111111" flood-opacity="0.65"' in svg
        assert 'filterUnits="userSpaceOnUse"' in svg


def test_a_halo_moves_the_texture_and_so_the_contract():
    plain = compile_shot(_shot(_entity()), _haloed_mall(halo=None), width=W, height=H)
    glowing = compile_shot(_shot(_entity()), _haloed_mall(), width=W, height=H)
    assert set(to_dict(plain)["assets"]["textures"]).isdisjoint(
        to_dict(glowing)["assets"]["textures"]
    )


def test_a_replacement_set_draws_a_halo_under_every_key():
    mall = {"props": {"l": {"kind": "TextDescriptor", "name": "l", "texts": {"a": "1", "b": "22"},
                            "unit": "block", "halo": {"color": "#ffd400"}}}}  # fmt: skip
    doc = compile_shot(_shot(_entity()), mall, width=W, height=H)
    textures = to_dict(doc)["assets"]["textures"]
    assert len(textures) == 2
    assert all('flood-color="#ffd400"' in _svg(doc, alias) for alias in textures)


# --- an#682 lifted, plates refused --------------------------------------------


def _patch_block(monkeypatch, change):
    import tituli

    real_block = tituli.block

    def patched(*args, **kwargs):
        return change(real_block(*args, **kwargs))

    monkeypatch.setattr(tituli, "block", patched)


def test_a_run_arriving_with_a_tituli_halo_is_drawn(monkeypatch):
    """an#682 refused a run carrying `halo`; `an` draws one now, so the run's
    own halo is what its unit glows with, even with none in the document.
    Real tituli runs, so a renamed field fails here."""
    gold = Halo(color="#ffd400")
    _patch_block(monkeypatch, lambda lay: lay.with_halo(gold))
    lay = layout_text(TextDescriptor(name="t", text="to be"), width=W, height=H)
    assert [u.halo.color for u in lay.units] == ["#ffd400", "#ffd400"]


def test_a_block_unit_whose_lines_carry_different_halos_is_refused(monkeypatch):
    """One unit is one texture with one glow: it cannot draw two."""

    def mixed(lay):
        runs = (dataclasses.replace(lay.runs[0], halo=Halo()), *lay.runs[1:])
        return dataclasses.replace(lay, runs=runs)

    _patch_block(monkeypatch, mixed)
    with pytest.raises(TextLayoutError, match="different halos"):
        layout_text(
            TextDescriptor(name="t", text="to\nbe", unit="block"), width=W, height=H
        )
    lines = layout_text(
        TextDescriptor(name="t", text="to\nbe", unit="line"), width=W, height=H
    )
    assert [u.halo is not None for u in lines.units] == [True, False]


def test_a_layout_carrying_tituli_plates_is_refused_by_name(monkeypatch):
    """The review of an#682: `_layout_string` ignored `Layout.plates`. `an`
    draws units only, so a scrim would be silently left off the film."""
    from tituli import Plate
    from tituli.geometry import Box

    _patch_block(
        monkeypatch,
        lambda lay: lay.with_plates(
            Plate(Box(0, 0, 10, 10), (0, 0, 0, 128), "gradient-bottom")
        ),
    )
    with pytest.raises(TextLayoutError, match=r"1 plate\(s\) \(gradient-bottom\)"):
        layout_text(TextDescriptor(name="t", text="to be"), width=W, height=H)


# --- the neighbouring unit -----------------------------------------------------


def test_a_halo_that_dims_the_neighbouring_unit_is_said():
    with pytest.warns(TextHaloWarning, match="drawn over an earlier one's glyphs"):
        layout_text(
            TextDescriptor(name="t", text="SAND", size=0.2, unit="glyph", halo=True),
            width=W,
            height=H,
        )
    with warnings.catch_warnings():
        warnings.simplefilter("error", TextHaloWarning)
        layout_text(
            TextDescriptor(name="t", text="SAND DUNE", size=0.2, halo=True),
            width=W,
            height=H,
        )
        layout_text(
            TextDescriptor(name="t", text="SAND", size=0.2, unit="block", halo=True),
            width=W,
            height=H,
        )


# --- the engine must afford the filters ----------------------------------------


def test_the_stage_affords_the_halo_s_filters():
    from an.capabilities import analyse
    from an.stage.render import CutoutRenderer

    profile, _ = analyse("engine", CutoutRenderer())
    assert set(HALO_FILTER_PRIMITIVES) <= set(profile["engine.svg_filter"]["keys"])


class _NoFilterRenderer:
    """A stage engine that rasterises SVG without filters: no `svg_filters`."""

    name = "cutout"
    supported_renderers = ("cutout", "stage")

    def render(self, shot, ctx):  # pragma: no cover - never called
        raise AssertionError


@pytest.fixture()
def no_filters(monkeypatch):
    import an.adapters._base as base

    real = base.get_renderer
    monkeypatch.setattr(
        base,
        "get_renderer",
        lambda name: _NoFilterRenderer() if name in ("cutout", "stage") else real(name),
    )


def test_an_engine_without_svg_filters_refuses_a_halo_by_name(no_filters):
    with pytest.raises(CutoutCompileError, match=r"engine\.svg_filter:feGaussianBlur"):
        compile_shot(_shot(_entity()), _haloed_mall(), width=W, height=H)
    compile_shot(
        _shot(_entity()), _haloed_mall(halo=None), width=W, height=H
    )  # no halo, no need


def test_validate_agrees_with_compile(monkeypatch):
    from an.ir.validate import validate_semantic

    mall = _haloed_mall()
    scene = SceneIR(meta=Meta(), timeline=[_shot(_entity())])
    ok = validate_semantic(scene, available_props=mall["props"])
    assert not [f for f in ok.findings if "svg_filter" in f.description]
    import an.adapters._base as base

    real = base.get_renderer
    monkeypatch.setattr(
        base,
        "get_renderer",
        lambda n: _NoFilterRenderer() if n in ("cutout", "stage") else real(n),
    )
    bad = validate_semantic(scene, available_props=mall["props"])
    assert any(
        "engine.svg_filter:" in f.description and f.severity == "error"
        for f in bad.findings
    )


# --- in pixels ------------------------------------------------------------------


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_a_halo_glows_under_its_glyphs(hermetic_browser, tmp_path):
    """The acceptance of an#701, on a frame: on the default white background,
    white words are invisible without a halo and ringed in dark with one, and
    a dark word with a gold halo sits in gold."""
    from PIL import Image

    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer

    def block(name, anchor, **kw):
        return {"kind": "TextDescriptor", "name": name, "text": "SAND", "size": 0.15,
                "layer": "overlay", "anchor": anchor, **kw}  # fmt: skip

    mall = {
        "props": {
            "glow": block("glow", "top", color="#ffffff", halo=True),
            "gold": block("gold", "center", color="#1a1a1a",
                          halo={"color": "#ffd400", "spread": 0.08, "blur": 0.15, "gain": 3, "opacity": 0.8}),
            "bare": block("bare", "bottom", color="#ffffff"),
        }
    }  # fmt: skip
    shot = Shot(
        id="s",
        renderer="stage",
        duration=0.25,
        entities=[_entity(e, e) for e in ("glow", "gold", "bare")],
    )
    result = CutoutRenderer().render(
        shot,
        RenderContext(
            mall=mall, work_dir=tmp_path, fps=4, resolution=(W, H), strict_assets=True
        ),
    )
    im = Image.open(result.frame_manifest[0]).convert("RGB")
    px = im.load()

    def count(rows, test):
        return sum(1 for y in rows for x in range(W) if test(px[x, y]))

    top, middle, bottom = range(0, 85), range(85, 160), range(170, H)
    dark = count(top, lambda p: max(p) < 200)
    gold = count(middle, lambda p: p[0] > 200 and p[1] > 150 and p[2] < 120)
    marked = count(bottom, lambda p: min(p) < 250)
    assert dark > 300, f"no dark glow under the white words ({dark} px)"
    # ... and the white glyphs drawn over it: white inside the glow's box
    ring = [(x, y) for y in top for x in range(W) if max(px[x, y]) < 200]
    x0, x1 = min(x for x, _ in ring), max(x for x, _ in ring)
    y0, y1 = min(y for _, y in ring), max(y for _, y in ring)
    inside = count(range(y0, y1), lambda p: min(p) >= 250) - (W - (x1 - x0)) * (y1 - y0)
    assert inside > 100, f"the glyphs are not drawn over their glow ({inside} px)"
    assert gold > 300, f"no gold glow under the dark word ({gold} px)"
    assert marked == 0, (
        f"white words with no halo must leave the white frame white ({marked} px)"
    )
    assert hermetic_browser["blocked"] == [], hermetic_browser["blocked"]
