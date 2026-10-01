"""A text block, compiled: one node per unit, each an SVG sprite (an#155).

:func:`an.stage.text.layout_text` asks tituli where every unit goes and what its
glyphs look like; this module turns that into the wire. The block is one
node (the entity), each unit a child named ``word_<i>`` / ``glyph_<i>`` /
``line_<i>`` whose visual is an ``svg_sprite`` — the kind the runtime already
draws — backed by a texture whose ``src`` is a ``data:`` URI holding that
unit's contours. So:

- the runtime gains no visual kind and never rasterises a font (option 2 of
  an#155); text reaches the frame path as SVG art, exactly as rig parts do;
- the compiled document is self-contained — no staging, no file to lose — and
  the scene contract hash covers the glyphs themselves, so a different face
  moves it;
- each unit node sits at its box centre with the sprite anchored at 0.5, so a
  ``scale_x``/``scale_y`` pop or a ``rotation`` pivots about the unit's middle.

**Crispness.** The SVG declares ``TEXT_TEXTURE_OVERSAMPLE`` x its box as its
intrinsic size, and the sprite is fitted back into the box (``fit="contain"``),
so a texel is half a scene pixel: an overlay at 1:1 samples it as a clean 2:1
box filter, and a world label survives a push-in. Every box is snapped outward
to whole pixels, so at zoom 1 a sprite's corners sit on the pixel grid.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any, Mapping

from an.stage.serialize import (
    AssetJSON,
    AssetResolutionJSON,
    NodeJSON,
    TransformJSON,
    VisualJSON,
)
from an.stage.text import TextDescriptor, TextLayout, layout_text, resolve_text

#: Texels per scene pixel in a unit's texture. See the module docstring.
TEXT_TEXTURE_OVERSAMPLE: int = 2

#: What a text texture's alias starts with — `text.<entity>.<unit>.<digest>`.
TEXT_TEXTURE_PREFIX: str = "text."

#: Hex digits of the texture's sha256 kept in its alias.
TEXT_ALIAS_DIGEST_LEN: int = 12

#: The ``src`` scheme of a texture that carries its bytes inline. The staging
#: step skips it (there is nothing to copy) instead of warning that the prefix
#: names no store.
INLINE_SRC_PREFIX: str = "data:"

_SVG_NS = "http://www.w3.org/2000/svg"


def unit_svg(d: str, box: tuple[int, int, int, int], *, color: str) -> str:
    """One unit's texture: its contours in a viewBox equal to its frame-pixel box.

    >>> unit_svg("M0 0L2 0L2 2Z", (0, 0, 4, 4), color="#123456")[:60]
    '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"'
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    k = TEXT_TEXTURE_OVERSAMPLE
    return (
        f'<svg xmlns="{_SVG_NS}" width="{w * k}" height="{h * k}" '
        f'viewBox="{x0} {y0} {w} {h}"><path fill="{color}" d="{d}"/></svg>'
    )


def svg_data_uri(svg: str) -> str:
    """``data:image/svg+xml;base64,…`` — the form the vendored engine's SVG
    loader recognises by prefix."""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode(
        "ascii"
    )


def text_document(entity: Any, props_store: Mapping) -> Mapping[str, Any] | None:
    """The stored document behind a prop entity if it is a text block, else None."""
    try:
        doc = props_store[entity.ref]
    except (KeyError, TypeError):
        return None
    if isinstance(doc, dict) and doc.get("kind") == "TextDescriptor":
        return doc
    return None


def build_text_subtree(
    entity: Any,
    document: Mapping[str, Any],
    *,
    width: int,
    height: int,
    base_dir: Path | None,
    textures: dict[str, AssetJSON],
    resolutions: list[AssetResolutionJSON],
) -> tuple[NodeJSON, TextDescriptor, TextLayout]:
    """The block's node and its unit children, plus what it resolved to.

    Raises ``ValueError`` subclasses (`TextFontError`, `TextLayoutError`,
    pydantic's `ValidationError`) — the compiler wraps them.
    """
    desc = resolve_text(document, entity.overrides)
    lay = layout_text(desc, width=width, height=height, base_dir=base_dir)
    ox, oy = lay.origin
    children: list[NodeJSON] = []
    for unit in lay.units:
        src = svg_data_uri(unit_svg(unit.d, unit.box, color=desc.color))
        # CONTENT-addressed: the alias changes whenever the glyphs do. A
        # name-only alias (`text.title.word_0`) survives an edit of the words,
        # and the runtime's loader ignores a re-added alias on hot reload, so
        # `an preview` would keep showing the old word — and two blocks
        # sharing an id would silently share one texture.
        digest = hashlib.sha256(src.encode("ascii")).hexdigest()[:TEXT_ALIAS_DIGEST_LEN]
        alias = f"{TEXT_TEXTURE_PREFIX}{entity.id}.{unit.name}.{digest}"
        textures[alias] = AssetJSON(src=src)
        cx, cy = unit.center
        w, h = unit.size
        children.append(
            NodeJSON(
                name=unit.name,
                transform=TransformJSON(x=cx - ox, y=cy - oy),
                visual=VisualJSON(
                    kind="svg_sprite",
                    fit="contain",
                    asset_id=alias,
                    width=float(w),
                    height=float(h),
                    color=desc.color,
                ),
            )
        )
    resolutions.append(
        AssetResolutionJSON(
            id=entity.id,
            kind="prop",
            store=entity.store,
            ref=entity.ref,
            resolved="text",
        )
    )
    node = NodeJSON(
        name=entity.id,
        transform=TransformJSON(x=ox - width / 2.0, y=oy - height / 2.0),
        children=children,
    )
    return node, desc, lay
