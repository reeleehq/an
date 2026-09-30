"""Words on screen (an#155, epic #9 Wave 8, first slice).

Layers, each checked where it can fail:

- the document: `TextDescriptor` refuses set-but-inert and machine-dependent input;
- the typesetting seam: tituli lays it out, every unit is a named node with a box
  on the pixel grid and SVG contours as its texture;
- fonts fail loudly: a missing file, a non-font, a relative path with nowhere to
  resolve, a glyph the face lacks — compile raises and validate says so;
- the overlay is camera-immune ON THE COMPILED DOCUMENT (screen positions through
  a push-in) and IN PIXELS (the browser lane);
- byte identity: a shot with no text serializes exactly as before;
- the stagger preset is ordinary actions that hold, reveal and round-trip.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.adapters.cutout.serialize import to_dict
from an.adapters.cutout.text import INLINE_SRC_PREFIX, TEXT_TEXTURE_OVERSAMPLE
from an.adapters.cutout.timeline import (
    evaluate_timeline,
    screen_position,
    timeline_from_scene,
)
from an.ir.compose import tween
from an.ir.schema import AssetRef, Camera, Meta, Resolution, SceneIR, Shot, StagePlacement
from an.ir.validate import validate_semantic
from an.text import (
    TextDescriptor,
    TextFontError,
    TextLayoutError,
    layout_text,
    resolve_text,
    stagger,
)

W, H = 1920, 1080


def _title(**kw) -> dict:
    return {"kind": "TextDescriptor", "name": "title", "layer": "overlay", **kw}


def _label(**kw) -> dict:
    return {"kind": "TextDescriptor", "name": "label", **kw}


def _entity(eid, ref, *, text=None, stage=None, **overrides) -> AssetRef:
    if text is not None:
        overrides["text"] = text
    return AssetRef(
        kind="prop", id=eid, store="props", ref=ref, overrides=overrides or None, stage=stage
    )


def _shot(entities, *, actions=(), camera=None, duration=2.0) -> Shot:
    return Shot(
        id="s",
        renderer="cutout",
        duration=duration,
        camera=camera,
        entities=list(entities),
        actions=list(actions),
    )


def _embedded_font_file(tmp_path: Path) -> Path:
    """A real font FILE with no system dependency: Pillow's embedded face, on disk."""
    from tituli import EMBEDDED, resolve_face
    from tituli.fonts import face_bytes

    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "Aileron.ttf"
    path.write_bytes(face_bytes(resolve_face(EMBEDDED, size=12)))
    return path


# --- the document ------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields, needle",
    [
        ({"anchor": "top"}, "only an overlay has"),
        ({"layer": "overlay", "anchor": "middle"}, "unknown anchor"),
        ({"tracking": 0.1}, "unit='glyph'"),
        ({"font": "Helvetica"}, "family name is refused"),
        ({"text": "   "}, "only whitespace"),
        ({"color": "red"}, "#rrggbb"),
        ({"colour": "#000000"}, "Extra inputs"),
    ],
)
def test_the_document_refuses_what_would_silently_do_nothing(fields, needle):
    with pytest.raises(ValueError, match=needle):
        TextDescriptor(**{"name": "t", "text": "hi", **fields})


def test_a_stored_style_takes_its_words_from_the_entity():
    desc = resolve_text(_label(size=0.04), {"text": "Paris"})
    assert (desc.text, desc.size, desc.layer) == ("Paris", 0.04, "world")


# --- layout -------------------------------------------------------------------------


def test_units_are_named_by_kind_and_count_only_what_is_drawn():
    words = layout_text(TextDescriptor(name="t", text="to be  or"), width=W, height=H)
    assert [(u.name, u.text) for u in words.units] == [
        ("word_0", "to"),
        ("word_1", "be"),
        ("word_2", "or"),
    ]
    glyphs = layout_text(
        TextDescriptor(name="t", text="a b", unit="glyph"), width=W, height=H
    )
    assert [(u.name, u.text) for u in glyphs.units] == [("glyph_0", "a"), ("glyph_1", "b")]
    lines = layout_text(
        TextDescriptor(name="t", text="one\ntwo", unit="line"), width=W, height=H
    )
    assert [u.name for u in lines.units] == ["line_0", "line_1"]


def test_max_width_wraps_through_tituli():
    one = layout_text(TextDescriptor(name="t", text="alpha beta gamma delta", unit="line"), width=W, height=H)
    wrapped = layout_text(
        TextDescriptor(name="t", text="alpha beta gamma delta", unit="line", max_width=0.15),
        width=W,
        height=H,
    )
    assert len(one.units) == 1 and len(wrapped.units) >= 2


def test_every_box_is_on_the_pixel_grid_and_the_block_is_centred():
    lay = layout_text(TextDescriptor(name="t", text="Hello big world"), width=W, height=H)
    assert all(isinstance(v, int) for u in lay.units for v in u.box)
    x0 = min(u.box[0] for u in lay.units)
    x1 = max(u.box[2] for u in lay.units)
    assert abs((x0 + x1) / 2 - W / 2) <= 2
    assert lay.origin == (W / 2, H / 2)


def test_an_anchor_places_the_block_inside_the_title_safe_area():
    from tituli import safe_area

    lay = layout_text(
        TextDescriptor(name="t", text="Top", layer="overlay", anchor="top"), width=W, height=H
    )
    safe = safe_area(W, H)
    top = min(u.box[1] for u in lay.units)
    assert safe.y0 - 2 <= top <= safe.y0 + 0.2 * H
    assert lay.origin[1] < H / 4


def test_the_default_face_is_the_embedded_one_by_its_bytes():
    lay = layout_text(TextDescriptor(name="t", text="x"), width=W, height=H)
    assert lay.font.embedded and lay.font.family == "Aileron"
    assert len(lay.font.sha256) == 64


# --- fonts fail loudly --------------------------------------------------------------


def test_a_missing_font_file_raises_at_layout_compile_and_validate(tmp_path):
    missing = str(tmp_path / "nope.ttf")
    with pytest.raises(TextFontError, match="not a file"):
        layout_text(TextDescriptor(name="t", text="x", font=missing), width=W, height=H)

    mall = {"props": {"lbl": _label(font=missing)}}
    shot = _shot([_entity("city", "lbl", text="Paris")])
    with pytest.raises(CutoutCompileError, match="not a file"):
        compile_shot(shot, mall)

    scene = SceneIR(meta=Meta(duration=2.0), timeline=[shot])
    report = validate_semantic(scene, available_props=mall["props"])
    assert not report.passed
    assert any("not a file" in f.description for f in report.findings)


def test_a_file_that_is_not_a_font_raises_rather_than_falling_back(tmp_path):
    bogus = tmp_path / "bogus.ttf"
    bogus.write_bytes(b"this is not a font")
    with pytest.raises(TextFontError, match="could not use it"):
        layout_text(TextDescriptor(name="t", text="x", font=str(bogus)), width=W, height=H)


def test_a_relative_font_needs_an_on_disk_store(tmp_path):
    _embedded_font_file(tmp_path / "props" / "lbl")
    desc = TextDescriptor(name="t", text="x", font="Aileron.ttf")
    with pytest.raises(TextFontError, match="relative path"):
        layout_text(desc, width=W, height=H)  # no base dir: never the CWD
    lay = layout_text(desc, width=W, height=H, base_dir=tmp_path / "props" / "lbl")
    assert not lay.font.embedded
    # the same bytes, so the same identity as the embedded face
    assert lay.font.sha256 == layout_text(
        TextDescriptor(name="t", text="x"), width=W, height=H
    ).font.sha256


def test_a_relative_font_resolves_beside_the_document_in_a_real_store(tmp_path):
    """Through the compiler: the props store's `_root` is where a relative
    `font` is looked for (the document's own directory)."""

    class _DiskStore(dict):
        _root = str(tmp_path / "props")

    _embedded_font_file(tmp_path / "props" / "lbl")
    store = _DiskStore(lbl=_label(font="Aileron.ttf"))
    doc = compile_shot(_shot([_entity("city", "lbl", text="Paris")]), {"props": store})
    assert "(embedded)" not in doc.meta.fonts["city"]


def test_a_glyph_the_face_lacks_raises_naming_it():
    with pytest.raises(TextLayoutError, match=r"U\+00E9"):
        layout_text(TextDescriptor(name="t", text="café"), width=W, height=H)
    mall = {"props": {"lbl": _label()}}
    with pytest.raises(CutoutCompileError, match=r"U\+00E9"):
        compile_shot(_shot([_entity("city", "lbl", text="café")]), mall)


# --- the compiled document ------------------------------------------------------------


def _title_and_label_shot(*, actions=(), camera="push_in"):
    mall = {
        "props": {
            "title_style": _title(size=0.08, anchor="top", color="#c0392b"),
            "label": _label(size=0.05, color="#1f4e9a"),
        }
    }
    shot = _shot(
        [
            _entity("title", "title_style", text="Words on screen"),
            _entity("city", "label", text="Paris", stage=StagePlacement(at=(200.0, 100.0))),
        ],
        actions=actions,
        camera=Camera(move=camera) if camera else None,
    )
    return shot, mall


def test_overlay_blocks_go_to_the_overlay_and_world_blocks_to_the_scene():
    shot, mall = _title_and_label_shot()
    doc = compile_shot(shot, mall, width=W, height=H)
    assert [c.name for c in doc.overlay.children] == ["title"]
    assert "title" not in [c.name for c in doc.scene.children]
    assert "city" in [c.name for c in doc.scene.children]
    word = doc.overlay.children[0].children[0]
    assert word.name == "word_0" and word.visual.kind == "svg_sprite"
    assert word.visual.fit == "contain"
    src = doc.assets.textures[word.visual.asset_id].src
    assert src.startswith(INLINE_SRC_PREFIX + "image/svg+xml;base64,")
    assert set(doc.meta.fonts) == {"title", "city"}
    assert [r.resolved for r in doc.asset_resolution] == ["text", "text"]


def test_the_texture_is_oversampled_and_fits_back_into_its_box():
    import base64

    shot, mall = _title_and_label_shot()
    doc = compile_shot(shot, mall, width=W, height=H)
    word = doc.scene.children[0].children[0]
    svg = base64.b64decode(
        doc.assets.textures[word.visual.asset_id].src.split(",", 1)[1]
    ).decode()
    k = TEXT_TEXTURE_OVERSAMPLE
    assert f'width="{int(word.visual.width) * k}"' in svg
    assert f'height="{int(word.visual.height) * k}"' in svg
    assert 'fill="#1f4e9a"' in svg


def _screen_box(doc, path, pose):
    """The unit's sprite box on the canvas (anchored at 0.5 on its node)."""
    unit = _find(doc, path)
    hw, hh = unit.visual.width / 2, unit.visual.height / 2
    corners = [
        screen_position(doc, path, pose=pose, point=(dx, dy))
        for dx in (-hw, hw)
        for dy in (-hh, hh)
    ]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _find(doc, path):
    top, rest = path.split("/", 1)
    roots = list(doc.scene.children) + (list(doc.overlay.children) if doc.overlay else [])
    node = next(c for c in roots if c.name == top)
    for part in rest.split("/"):
        node = next(c for c in node.children if c.name == part)
    return node


def test_the_overlay_holds_still_through_a_push_in_while_a_world_label_moves():
    """The done-when, on the compiled document: screen boxes at the first and
    last instant of a push-in."""
    shot, mall = _title_and_label_shot()
    doc = compile_shot(shot, mall, width=W, height=H)
    tl = timeline_from_scene(doc)
    first, last = evaluate_timeline(tl, 0.0), evaluate_timeline(tl, shot.duration)
    assert first != last, "the push-in must actually move the camera"
    for unit in ("title/word_0", "title/word_2"):
        assert _screen_box(doc, unit, first) == _screen_box(doc, unit, last)
    a, b = _screen_box(doc, "city/word_0", first), _screen_box(doc, "city/word_0", last)
    assert a != b
    assert (b[2] - b[0]) > (a[2] - a[0]) * 1.1, "a world label grows with the zoom"


def _validate_errors(shot, mall):
    report = validate_semantic(
        SceneIR(meta=Meta(duration=2.0), timeline=[shot]), available_props=mall["props"]
    )
    return [f.description for f in report.findings if f.severity == "error"]


def test_an_overlay_sharing_a_path_with_the_scene_is_refused():
    """One runtime index serves both layers, so a clash would shadow a node."""
    mall = {"props": {"t": _title()}}
    shot = _shot(
        [
            AssetRef(kind="character", id="x", store="characters", ref="x"),
            _entity("x", "t", text="A"),
        ]
    )
    with pytest.raises(CutoutCompileError, match="overlay and scene both build"):
        compile_shot(shot, mall)
    assert any("shares its id" in e for e in _validate_errors(shot, mall))


@pytest.mark.parametrize("eid", ["root", "overlay"])
def test_a_text_block_may_not_take_a_runtime_container_name(eid):
    """An overlay block called `root` would overwrite the camera's node in the
    runtime's index and zoom with the push-in (review finding)."""
    mall = {"props": {"t": _title()}}
    shot = _shot([_entity(eid, "t", text="A")], camera=Camera(move="push_in"))
    with pytest.raises(CutoutCompileError, match="reserved"):
        compile_shot(shot, mall)
    assert any("reserved" in e for e in _validate_errors(shot, mall))


def test_two_text_blocks_with_one_id_are_refused():
    mall = {"props": {"t": _title()}}
    shot = _shot([_entity("t", "t", text="Hello"), _entity("t", "t", text="World")])
    with pytest.raises(CutoutCompileError, match="share the id"):
        compile_shot(shot, mall)
    assert any("share the id" in e for e in _validate_errors(shot, mall))


def test_anchor_and_stage_at_are_two_answers_at_compile_and_validate():
    mall = {"props": {"t": _title(anchor="top")}}
    shot = _shot([_entity("t", "t", text="A", stage=StagePlacement(at=(0.0, 10.0)))])
    with pytest.raises(CutoutCompileError, match="both"):
        compile_shot(shot, mall)
    assert any("both" in e for e in _validate_errors(shot, mall))


def test_texture_aliases_follow_the_glyphs_not_the_name():
    """Content-addressed, so a hot reload with new words cannot reuse the old
    texture under the same alias."""
    mall = {"props": {"t": _title()}}
    a = compile_shot(_shot([_entity("t", "t", text="Hello")]), mall)
    b = compile_shot(_shot([_entity("t", "t", text="World")]), mall)
    ids = lambda d: d.overlay.children[0].children[0].visual.asset_id  # noqa: E731
    assert ids(a) != ids(b) and ids(a).startswith("text.t.word_0.")


def test_crlf_and_tabs_are_normalised_before_typesetting():
    lay = layout_text(TextDescriptor(name="t", text="one\r\ntwo\tthree", unit="line"), width=W, height=H)
    assert [u.text for u in lay.units] == ["one", "two three"]


def test_rest_pose_reads_overlay_units():
    from an.motion import rest_pose

    mall = {"props": {"t": _title()}}
    pose = rest_pose(_shot([_entity("t", "t", text="Hi there")]), "t/word_1", mall=mall)
    assert pose["x"] > 0


def test_a_target_the_block_does_not_build_raises_naming_its_units():
    mall = {"props": {"t": _title(unit="glyph")}}
    shot = _shot(
        [_entity("t", "t", text="Hi")],
        actions=[tween("t/word_0", "alpha", 0.0, 0.5)],
    )
    with pytest.raises(CutoutCompileError, match=r"glyph_0"):
        compile_shot(shot, mall)
    report = validate_semantic(
        SceneIR(meta=Meta(duration=2.0), timeline=[shot]), available_props=mall["props"]
    )
    assert any("is not a unit of text block" in f.description for f in report.findings)


def test_validate_passes_a_scene_that_compiles():
    shot, mall = _title_and_label_shot(
        actions=stagger("title", 3, "alpha", to=1.0, from_=0.0, duration=0.3, step=0.2)
    )
    compile_shot(shot, mall)
    scene = SceneIR(
        meta=Meta(duration=2.0, resolution=Resolution(width=W, height=H)), timeline=[shot]
    )
    report = validate_semantic(scene, available_props=mall["props"])
    assert report.passed, [f.description for f in report.findings]


# --- byte identity --------------------------------------------------------------------


def test_a_shot_with_no_text_serializes_exactly_as_before():
    doc = to_dict(compile_shot(_shot([]), {}))
    assert "overlay" not in doc
    assert "fonts" not in doc["meta"]


# --- the stagger preset ---------------------------------------------------------------


def test_stagger_holds_each_word_hidden_until_its_turn_then_reveals_it():
    reveal = stagger("title", 3, "alpha", to=1.0, from_=0.0, duration=0.3, step=0.4)
    shot, mall = _title_and_label_shot(actions=reveal, camera=None)
    tl = timeline_from_scene(compile_shot(shot, mall))
    at = lambda t, i: evaluate_timeline(tl, t).get((f"title/word_{i}", "alpha"))  # noqa: E731
    assert at(0.0, 0) == 0.0 and at(0.0, 2) == 0.0  # held, not the built 1.0
    assert at(0.5, 0) is None or at(0.5, 0) == 1.0  # word 0 is done
    assert at(0.5, 2) == 0.0  # word 2 still waits (its tween starts at 0.8)
    assert at(1.1, 2) == pytest.approx(1.0)


def test_stagger_round_trips_through_scene_md():
    from an.ir.sync import ir_to_markdown, markdown_to_ir

    reveal = stagger("title", 2, "scale_x", to=1.0, from_=0.0, duration=0.3, step=0.2)
    shot, _ = _title_and_label_shot(actions=reveal)
    scene = SceneIR(meta=Meta(title="t", duration=2.0), timeline=[shot])
    again = markdown_to_ir(ir_to_markdown(scene))
    assert [a.model_dump() for a in again.timeline[0].actions] == [
        a.model_dump() for a in shot.actions
    ]
    assert again.timeline[0].entities == shot.entities


def test_inline_textures_are_not_staged_and_not_warned_about(tmp_path):
    from an.adapters.cutout.render import _stage_scene_assets

    shot, mall = _title_and_label_shot()
    doc = compile_shot(shot, mall)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _stage_scene_assets(doc, mall, tmp_path)
    assert not any(tmp_path.iterdir())


# --- pixels -----------------------------------------------------------------------------


def _colour_box(png, rgb, *, tol=40):
    from PIL import Image

    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()
    hits = [
        (x, y)
        for y in range(h)
        for x in range(w)
        if all(abs(px[x, y][i] - rgb[i]) <= tol for i in range(3))
    ]
    assert hits, f"no {rgb} pixels in {png}"
    xs, ys = [p[0] for p in hits], [p[1] for p in hits]
    return min(xs), min(ys), max(xs), max(ys)


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_a_title_card_holds_still_through_a_push_in(hermetic_browser, tmp_path):
    """The Wave 8 done-when, on frames: a push-in over an overlay title (red)
    and an in-world label (blue). The title's ink box is identical on the first
    and last frame; the label's grows by the zoom. Rendered under
    ``hermetic_browser``, so the inline glyph textures are proven to need no
    request at all."""
    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer

    shot, mall = _title_and_label_shot()
    shot = shot.model_copy(update={"duration": 1.0})
    result = CutoutRenderer().render(
        shot,
        RenderContext(
            mall=mall, work_dir=tmp_path, fps=6, resolution=(640, 360), strict_assets=True
        ),
    )
    frames = result.frame_manifest
    red, blue = (0xC0, 0x39, 0x2B), (0x1F, 0x4E, 0x9A)
    t0, t1 = _colour_box(frames[0], red), _colour_box(frames[-1], red)
    assert t0 == t1, (t0, t1)
    l0, l1 = _colour_box(frames[0], blue), _colour_box(frames[-1], blue)
    assert (l1[2] - l1[0]) > (l0[2] - l0[0]) * 1.1, (l0, l1)
    # the title sits in the top of the title-safe area, the label right of centre
    assert t0[1] < 360 * 0.25 and l0[0] > 320
    assert hermetic_browser["blocked"] == [], hermetic_browser["blocked"]
