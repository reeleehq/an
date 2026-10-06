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
  ``scale_x``/``scale_y`` pop or a ``rotation`` pivots about the unit's middle;
- a block with a replacement set (``texts``, an#341) is one ``block_0`` node
  whose visual carries a ``text`` swap set, one texture per string and a box
  per string on the ``align`` edge — replacement animation, which the runtime
  already draws (``applySwap``).

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
from an.stage.text import (
    TEXT_SET,
    TextDescriptor,
    TextLayout,
    TextUnit,
    layout_text,
    layout_text_set,
    resolve_text,
    text_set_keys,
)

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


def text_swap_declaration(entity: Any, mall: Any) -> Any:
    """The core ``prop`` kind's swap declaration (an#341): a text block with
    ``texts`` declares its ``text`` set, ``{key: key}``; any other prop
    declares nothing (its built nodes' sets are its declaration).

    Through :attr:`an.genres.EntityKind.swap_declaration`, so the compiler's
    swap vocabulary, its swap checks and ``an validate`` learn the set the way
    they learn a rig's. ``descriptor`` stays ``None``: the text block has no
    lowering, and a descriptor is what a genre's passes read as a rig. A
    document that does not resolve declares nothing here; the builder raises
    on it, naming why.
    """
    from an.genres import SwapDeclaration

    props = mall.get("props") if hasattr(mall, "get") else None
    document = text_document(entity, props) if props is not None else None
    if document is None:
        return None
    try:
        desc = resolve_text(document, entity.overrides)
    except ValueError:
        return None
    if desc.texts is None:
        return None
    return SwapDeclaration(sets={TEXT_SET: text_set_keys(desc)})


def _unit_texture(
    entity_id: str, unit: TextUnit, desc: TextDescriptor, textures: dict[str, AssetJSON]
) -> str:
    """Register one unit's texture and return its alias.

    CONTENT-addressed: the alias changes whenever the glyphs do. A name-only
    alias (`text.title.word_0`) survives an edit of the words, and the
    runtime's loader ignores a re-added alias on hot reload, so `an preview`
    would keep showing the old word — and two blocks sharing an id would
    silently share one texture. Two keys of one set with one string share one
    texture.
    """
    src = svg_data_uri(unit_svg(unit.d, unit.box, color=desc.color))
    digest = hashlib.sha256(src.encode("ascii")).hexdigest()[:TEXT_ALIAS_DIGEST_LEN]
    alias = f"{TEXT_TEXTURE_PREFIX}{entity_id}.{unit.name}.{digest}"
    textures[alias] = AssetJSON(src=src)
    return alias


def _align_offset(desc: TextDescriptor, rest: TextLayout, other: TextLayout) -> float:
    """How far ``other`` moves horizontally so its ``align`` edge sits on the
    rest string's: a right-aligned counter grows leftwards, a left-aligned one
    rightwards, a centred one both ways (an#341). Layout boxes, not ink, so
    "1" and "11" share their right edge where their advances end."""
    (r0, _, r1, _), (o0, _, o1, _) = rest.bounds, other.bounds
    if desc.align == "right":
        return r1 - o1
    if desc.align == "left":
        return r0 - o0
    return (r0 + r1) / 2.0 - (o0 + o1) / 2.0


def _text_set_visual(
    entity_id: str,
    desc: TextDescriptor,
    rest: TextLayout,
    layouts: dict[str, TextLayout],
    textures: dict[str, AssetJSON],
) -> VisualJSON:
    """``block_0``'s visual for a replacement set: the rest key's sprite, the
    ``text`` set naming every key's texture, and a box per key whose geometry
    differs from the rest's, placed on the ``align`` edge."""
    (rest_unit,) = rest.units
    rest_alias = _unit_texture(entity_id, rest_unit, desc, textures)
    rest_cx, rest_cy = rest_unit.center
    built = {
        "width": float(rest_unit.size[0]),
        "height": float(rest_unit.size[1]),
        "anchor_x": 0.5,
        "anchor_y": 0.5,
        "x": 0.0,
        "y": 0.0,
    }
    (_, ry0, _, ry1) = rest.bounds
    key_map: dict[str, str] = {}
    geometry: dict[str, dict[str, float]] = {}
    for key, lay in layouts.items():
        (unit,) = lay.units
        alias = _unit_texture(entity_id, unit, desc, textures)
        key_map[key] = alias
        if alias == rest_alias:
            continue
        (_, oy0, _, oy1) = lay.bounds
        cx, cy = unit.center
        w, h = unit.size
        box = {
            "width": float(w),
            "height": float(h),
            "anchor_x": 0.5,
            "anchor_y": 0.5,
            "x": cx + _align_offset(desc, rest, lay) - rest_cx,
            # Vertically every key is centred where the rest string is, by
            # layout box, so one-line keys share a baseline.
            "y": cy + ((ry0 + ry1) - (oy0 + oy1)) / 2.0 - rest_cy,
        }
        if box != built:  # only keys drawn differently are listed (an#211)
            geometry[alias] = box
    w, h = rest_unit.size
    return VisualJSON(
        kind="svg_sprite",
        fit="contain",
        asset_id=rest_alias,
        asset_sets={TEXT_SET: key_map},
        asset_geometry=geometry or None,
        width=float(w),
        height=float(h),
        color=desc.color,
    )


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
    if desc.texts is not None:
        # A replacement set (an#341): one `block_0` node drawing the rest
        # string, swapping to any other key's drawing — a `discrete` string
        # the runtime's `applySwap` already handles.
        layouts = layout_text_set(desc, width=width, height=height, base_dir=base_dir)
        (unit,) = lay.units
        cx, cy = unit.center
        children.append(
            NodeJSON(
                name=unit.name,
                transform=TransformJSON(x=cx - ox, y=cy - oy),
                visual=_text_set_visual(entity.id, desc, lay, layouts, textures),
            )
        )
    for unit in lay.units if desc.texts is None else ():
        alias = _unit_texture(entity.id, unit, desc, textures)
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
