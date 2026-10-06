"""Outlined text: `stroke_width` / `stroke_color` on a text block (an#313).

OverSimplified's labels are white words edged in black. The outline is drawn in
each unit's OWN texture, under the fill, so a per-word `alpha` reveal shows
outline and fill together; each unit's box grows by the outline so it is never
clipped; a block without one is byte-identical; an outline wide enough to cover
the neighbouring unit is said out loud.
"""

from __future__ import annotations

import base64
import warnings

import pytest

from an.adapters.cutout.compile import compile_shot
from an.adapters.cutout.serialize import to_dict
from an.ir.schema import AssetRef, Shot
from an.text import TextDescriptor, TextOutlineWarning, layout_text

W, H = 320, 240


@pytest.mark.parametrize(
    "fields, needle",
    [
        ({"stroke_color": "#000000"}, "`stroke_width` is 0"),
        ({"stroke_width": -1.0}, "greater than or equal"),
        ({"stroke_width": 2.0, "stroke_color": "black"}, "#rrggbb"),
    ],
)
def test_the_document_refuses_an_outline_it_could_not_draw(fields, needle):
    with pytest.raises(ValueError, match=needle):
        TextDescriptor(name="t", text="hi", **fields)


def test_without_an_outline_nothing_changes():
    plain = TextDescriptor(name="t", text="hi")
    assert "stroke_width" not in plain.model_dump()
    a = layout_text(plain, width=W, height=H)
    b = layout_text(TextDescriptor(name="t", text="hi", stroke_width=0.0), width=W, height=H)
    assert a.units == b.units


def test_each_unit_box_grows_by_the_outline():
    plain = layout_text(TextDescriptor(name="t", text="ROME FALLS", size=0.2), width=W, height=H)
    outlined = layout_text(
        TextDescriptor(name="t", text="ROME FALLS", size=0.2, stroke_width=3.5), width=W, height=H
    )
    for p, o in zip(plain.units, outlined.units):
        assert (o.box[0], o.box[1]) == (p.box[0] - 4, p.box[1] - 4)
        assert (o.box[2], o.box[3]) == (p.box[2] + 4, p.box[3] + 4)


def _svg(doc, alias) -> str:
    src = to_dict(doc)["assets"]["textures"][alias]["src"]
    return base64.b64decode(src.split(",", 1)[1]).decode()


def test_the_outline_is_under_the_fill_in_the_word_s_own_texture():
    """One texture per word holding both: so `word_1:alpha` hides the outline too."""
    mall = {
        "props": {
            "l": {"kind": "TextDescriptor", "name": "l", "text": "ROME FALLS", "size": 0.2,
                  "color": "#ffffff", "stroke_width": 4.0, "stroke_color": "#1c1c1c"}
        }
    }  # fmt: skip
    shot = Shot(id="s", renderer="stage", duration=1.0,
                entities=[AssetRef(kind="prop", id="l", store="props", ref="l")])  # fmt: skip
    doc = compile_shot(shot, mall, width=W, height=H)
    (block,) = to_dict(doc)["scene"]["children"]
    assert [c["name"] for c in block["children"]] == ["word_0", "word_1"]
    for word in block["children"]:
        svg = _svg(doc, word["visual"]["asset_id"])
        stroke, fill = svg.index('stroke="#1c1c1c"'), svg.index('fill="#ffffff"')
        assert stroke < fill, "the outline is drawn first, under the fill"
        assert 'stroke-width="8"' in svg and 'stroke-linejoin="round"' in svg


def test_an_outline_that_covers_the_neighbouring_word_is_said():
    with pytest.warns(TextOutlineWarning, match="covers part of the one before it"):
        layout_text(TextDescriptor(name="t", text="ROME FALLS", size=0.2, stroke_width=8.0), width=W, height=H)
    with warnings.catch_warnings():
        warnings.simplefilter("error", TextOutlineWarning)
        layout_text(TextDescriptor(name="t", text="ROME FALLS", size=0.2, stroke_width=4.0), width=W, height=H)
        layout_text(
            TextDescriptor(name="t", text="ROME FALLS", size=0.2, stroke_width=8.0, unit="line"),
            width=W,
            height=H,
        )
