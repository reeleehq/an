"""Hats above the brows, ``face.brows``, and hair (an#252).

The end-user test found that at the OverSimplified head scale a cap or bowler
brim sat where the brows go, so surprised / annoyed / happy did not read, and
that two figures could only differ by costume. Rules this file holds:

1. **A factory hat is worn above the brows' acting range** — measured on the
   written art, in every view that shows a brow, at the head scales a style
   uses; one seat for every view.
2. **When it cannot be, it is recorded, never hidden**: the descriptor says
   what covers the brows (``occluded``), the character does not afford
   ``face.brows``, the expression aspect falls to ``expr.without_brows``, and
   ``an validate`` / ``an character capabilities`` say so with the remedy.
3. **Hair has a style and a length**, drawn in the ``hair`` role in every view,
   never lower over the brows than the default hairline; the defaults draw the
   original head (the golden digests in test_character_variety hold that).
4. A character made before hats were seated keeps its hat where its front has
   it when its views are redrawn.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from an.characters import new_character
from an.characters.brows import (
    BROWS_FEATURE,
    brow_range,
    ink_columns,
    ink_discs,
)
from an.characters.factory import (
    DFLT_HAIR_LENGTH,
    DFLT_HAIR_STYLE,
    HAIR_LENGTHS,
    HAIR_STYLES,
    HATS,
    _hair_layers,
    _hat_seat,
    _head_part_text,
    _resolve_looks,
    add_views,
)
from an.characters.schema import REFERENCE_HEAD_HEIGHT, CharacterDescriptor

#: The head scales the shipped styles use (South Park 1.3, OverSimplified 1.7)
#: and the range's ends.
SCALES = (0.5, 1.0, 1.3, 1.7, 2.5)
REAL_HATS = [h for h in HATS if h != "none"]
#: Views that show a brow, and the file each is drawn in.
VIEW_FILES = {"front": "head.svg", "three_quarter": "head_three_quarter.svg", "side": "head_side.svg"}
_TRANSFORM = re.compile(
    r'<g transform="(?:translate\(0 (?P<a>[-\d.]+)\) scale\(1 (?P<k>[\d.]+)\) '
    r'translate\(0 (?P<b>[-\d.]+)\)|translate\(0 (?P<lift>[-\d.]+)\))">(?P<hat>.*?)</g>'
)


def _make(tmp_path: Path, name: str = "c", **knobs) -> Path:
    return new_character(tmp_path, name=name, use_dicebear=False, **knobs).parent


def _worn_hat_columns(svg: str) -> dict[int, tuple[float, float]]:
    """The hat's ink per column as WORN: the written transform applied."""
    m = _TRANSFORM.search(svg)
    assert m, "a seated hat is drawn inside its seat's transform"
    if m["lift"] is not None:
        a, k, b = float(m["lift"]), 1.0, 0.0
    else:
        a, k, b = float(m["a"]), float(m["k"]), float(m["b"])
    discs = [(x, a + (y + b) * k, r * k) for x, y, r in ink_discs(m["hat"])]
    return ink_columns(discs)


# ------------------------------------------------------------------ 1. the seat


@pytest.mark.parametrize("hat", REAL_HATS)
@pytest.mark.parametrize("scale", SCALES)
def test_a_hat_is_worn_above_the_brows_in_every_view(tmp_path, hat, scale):
    char = _make(tmp_path, hat=hat, head_scale=scale)
    reach = brow_range(head_scale=scale)
    for view, filename in VIEW_FILES.items():
        svg = (char / "parts" / filename).read_text(encoding="utf-8")
        cols = _worn_hat_columns(svg)
        dips = {c: bottom - reach[view][c] for c, (_, bottom) in cols.items() if c in reach[view]}
        assert dips and max(dips.values()) <= 0, (view, max(dips.values()))
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    assert "occluded" not in doc


def test_one_seat_for_every_view_so_the_hat_keeps_its_shape_as_it_turns(tmp_path):
    char = _make(tmp_path, hat="cap", head_scale=1.7)
    seats = {
        _TRANSFORM.search((char / "parts" / f).read_text(encoding="utf-8")).group(0).split(">")[0]
        for f in (*VIEW_FILES.values(), "head_back.svg")
    }
    assert len(seats) == 1


@pytest.mark.parametrize("hat", REAL_HATS)
def test_the_seat_never_lifts_a_crown_out_of_the_head_drawing(tmp_path, hat):
    """Lifted no higher than the canvas allows (a crown the drawing already
    clipped stays where it was): the rest is flattening, never clipping."""
    from an.characters.factory import _hat_fragment

    drawn = min(t for t, _ in ink_columns(ink_discs(_hat_fragment(hat, "front", accessory="#000000"))).values())
    for scale in SCALES:
        char = _make(tmp_path / f"{scale}", hat=hat, head_scale=scale)
        worn = _worn_hat_columns((char / "parts" / "head.svg").read_text(encoding="utf-8"))
        assert min(t for t, _ in worn.values()) >= min(drawn, 0.0) - 1e-6


# ------------------------------------------------------- 2. recorded, not hidden


def test_a_hat_that_cannot_clear_a_tiny_heads_brows_is_recorded(tmp_path):
    from an.capabilities import art_in_dir
    from an.characters.cli import capabilities, new as cli_new
    from an.genres import load
    from an.semantic.describe import describe_asset

    load()
    out = cli_new("tiny", out_dir=str(tmp_path), offline=True, hat="cap", head_scale=0.3)
    assert "covers the brows" in out
    doc = json.loads((tmp_path / "tiny" / "character.json").read_text(encoding="utf-8"))
    assert doc["occluded"] == {BROWS_FEATURE: "the cap hat at head_scale 0.3"}
    described = describe_asset(doc, art_in_dir(tmp_path / "tiny", exclude=("character.json",)))
    assert "face.brows" not in described["affordances"]
    expression = described["aspects"]["expression"]
    assert expression["default"] == "expr.without_brows"
    assert expression["substitution"]["missing"] == ["face.brows"]
    text = capabilities("tiny", out_dir=str(tmp_path))
    assert "occluded=" in text and "to add face.brows:" in text


def test_a_character_with_clear_brows_affords_them_and_acts_with_the_full_face(tmp_path):
    from an.capabilities import art_in_dir
    from an.genres import load
    from an.semantic.describe import describe_asset

    load()
    char = _make(tmp_path, hat="bowler", head_scale=1.7, build="stick")
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    d = describe_asset(doc, art_in_dir(char, exclude=("character.json",)))
    assert d["affordances"]["face.brows"] == {"slots": ["left_brow", "right_brow"]}
    assert d["aspects"]["expression"]["default"] == "expr.full_face"
    assert "substitution" not in d["aspects"]["expression"]


def test_brows_without_art_do_not_count(tmp_path):
    from an.library.character import character_affordances

    char = _make(tmp_path)
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    art = {p.relative_to(char).as_posix(): True for p in char.rglob("*.svg")}
    assert "face.brows" in character_affordances(doc, art)
    art.pop("parts/brow_l.svg")
    assert "face.brows" not in character_affordances(doc, art)
    doc["face_overlay"] = False
    assert "face.brows" not in character_affordances(doc, dict(art, **{"parts/brow_l.svg": True}))


def _scene_with(entity_ref: str, *actions, dialogue=()):
    from an.ir.schema import AssetRef, Meta, SceneIR, Shot

    shot = Shot(
        id="s",
        renderer="cutout",
        duration=2.0,
        entities=[AssetRef(kind="character", id="c", store="characters", ref=entity_ref)],
        actions=list(actions),
        dialogue=list(dialogue),
    )
    return SceneIR(meta=Meta(title="t", duration=2.0), timeline=[shot])


def _brow_warnings(scene, store):
    from an.ir.validate import validate_semantic

    report = validate_semantic(scene, available_characters=store)
    return [f for f in report.findings if "brows cannot be seen acting" in f.description]


def test_validate_warns_when_an_expression_moves_brows_that_cannot_act(tmp_path):
    from an.ir.compose import expression
    from an.ir.schema import Dialogue
    from an.stores.characters import CharactersStore

    _make(tmp_path, name="tiny", hat="beanie", head_scale=0.25)
    _make(tmp_path, name="big", hat="beanie", head_scale=1.7)
    store = CharactersStore(tmp_path)

    (hit,) = _brow_warnings(_scene_with("tiny", expression("c", "surprised")), store)
    assert hit.severity == "warning" and "the beanie hat" in hit.description
    assert "expr.without_brows" in hit.description and "--head-scale" in hit.description
    # The dialogue sugar is the same expression.
    line = Dialogue(speaker="c", text="Oh!", emotion="surprised", start=0.2, duration=0.5)
    assert _brow_warnings(_scene_with("tiny", dialogue=[line]), store)
    # Nothing to lose: a neutral face, or brows that can act.
    assert not _brow_warnings(_scene_with("tiny", expression("c", "neutral")), store)
    assert not _brow_warnings(_scene_with("big", expression("c", "surprised")), store)


def test_occluded_is_a_declared_fact_omitted_when_empty_and_checked():
    import pydantic

    c = CharacterDescriptor(name="c")
    assert "occluded" not in json.loads(c.model_dump_json())
    c = CharacterDescriptor(name="c", occluded={"brows": "a helmet"})
    assert json.loads(c.model_dump_json())["occluded"] == {"brows": "a helmet"}
    with pytest.raises(pydantic.ValidationError, match="features a drawing can cover"):
        CharacterDescriptor(name="c", occluded={"nose": "a mask"})


# ----------------------------------------------------------------------- 3. hair


@pytest.mark.parametrize("style", HAIR_STYLES)
@pytest.mark.parametrize("length", HAIR_LENGTHS)
def test_every_hair_builds_in_every_view_in_the_hair_role(tmp_path, style, length):
    if style == "bald" and length != DFLT_HAIR_LENGTH:
        with pytest.raises(ValueError, match="bald"):
            _make(tmp_path, hair_style=style, hair_length=length)
        return
    hair = "#5a3a8a"
    char = _make(tmp_path, hair_style=style, hair_length=length, palette={"hair": hair})
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    for f in ("head.svg", "head_back.svg", "head_side.svg", "head_three_quarter.svg"):
        svg = (char / "parts" / f).read_text(encoding="utf-8")
        assert (hair in svg) == (style != "bald"), f
        assert doc["colour_roles"][f"parts/{f}"][hair] == "hair"
    meta = doc["metadata"]
    assert meta.get("hair_style", DFLT_HAIR_STYLE) == style
    assert meta.get("hair_length", DFLT_HAIR_LENGTH) == length


def test_the_defaults_draw_no_hair_layer_and_record_no_knob(tmp_path):
    for view in ("front", "back", "side", "three_quarter"):
        assert _hair_layers(view, hair="#000000", hair_style="peak", hair_length="short") == ("", "")
    meta = json.loads((_make(tmp_path) / "character.json").read_text(encoding="utf-8"))["metadata"]
    assert not {"hair_style", "hair_length"} & set(meta)


@pytest.mark.parametrize("style", [s for s in HAIR_STYLES if s != "bald"])
@pytest.mark.parametrize("length", HAIR_LENGTHS)
def test_hair_never_draws_lower_over_the_brows_than_the_default_hairline(style, length):
    """What a style or a length adds is either BEHIND the skull (hidden where
    the face is) or, drawn over it, outside the columns the brows act in."""
    reach = brow_range(head_scale=1.0)
    for view in ("front", "three_quarter", "side"):
        _, over = _hair_layers(view, hair="#000000", hair_style=style, hair_length=length)
        if over:
            assert not set(ink_columns(ink_discs(over))) & set(reach[view]), view


def test_the_skin_stays_the_first_circle_so_the_lid_takes_its_tone(tmp_path):
    """`add_gaze` reads the lid's tone off the head's first circle: hair volume
    is drawn as paths, never circles, so it cannot be mistaken for the skin."""
    char = _make(tmp_path, hair_style="curly", hair_length="long", palette={"skin": "#c08a5a"})
    head = (char / "parts" / "head.svg").read_text(encoding="utf-8")
    assert re.search(r'<(?:circle|ellipse)[^>]*fill="(#[0-9a-f]{6})"', head).group(1) == "#c08a5a"


def test_hair_and_hats_are_offline_only():
    with pytest.raises(ValueError, match="offline head"):
        new_character("unused", name="d", use_dicebear=True, hair_length="long")


# --------------------------------------------------------------- 4. old characters


def test_views_of_a_character_made_before_the_seat_keep_its_hat_where_it_was(tmp_path):
    char = _make(tmp_path, hat="cap", head_scale=1.7, views=False)
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    meta = doc["metadata"]
    # Its front as the factory drew it before hats were seated.
    legacy = _resolve_looks(meta["seed"], {}, hat="cap", hat_seat=None)
    (char / "parts" / "head.svg").write_text(
        _head_part_text(legacy.head_svg, height=REFERENCE_HEAD_HEIGHT * 1.7), encoding="utf-8"
    )
    add_views(char)
    side = (char / "parts" / "head_side.svg").read_text(encoding="utf-8")
    assert "transform" not in side and "M 12 22 C 12 3 68 3 68 22 Z" in side
