# an.stage.text_layout

A text block, compiled: one node per unit, each an SVG sprite (an#155).

[`an.stage.text.layout_text()`](an.stage.text.html.md#an.stage.text.layout_text) asks tituli where every unit goes and what its
glyphs look like; this module turns that into the wire. The block is one
node (the entity), each unit a child named `word_<i>` / `glyph_<i>` /
`line_<i>` whose visual is an `svg_sprite` — the kind the runtime already
draws — backed by a texture whose `src` is a `data:` URI holding that
unit’s contours. So:

- the runtime gains no visual kind and never rasterises a font (option 2 of
  an#155); text reaches the frame path as SVG art, exactly as rig parts do;
- the compiled document is self-contained — no staging, no file to lose — and
  the scene contract hash covers the glyphs themselves, so a different face
  moves it;
- each unit node sits at its box centre with the sprite anchored at 0.5, so a
  `scale_x`/`scale_y` pop or a `rotation` pivots about the unit’s middle;
- a block with a replacement set (`texts`, an#341) is one `block_0` node
  whose visual carries a `text` swap set, one texture per string and a box
  per string on the `align` edge — replacement animation, which the runtime
  already draws (`applySwap`).

**Crispness.** The SVG declares `TEXT_TEXTURE_OVERSAMPLE` x its box as its
intrinsic size, and the sprite is fitted back into the box (`fit="contain"`),
so a texel is half a scene pixel: an overlay at 1:1 samples it as a clean 2:1
box filter, and a world label survives a push-in. Every box is snapped outward
to whole pixels, so at zoom 1 a sprite’s corners sit on the pixel grid.

### Module Attributes

| [`TEXT_TEXTURE_OVERSAMPLE`](#an.stage.text_layout.TEXT_TEXTURE_OVERSAMPLE)   | Texels per scene pixel in a unit's texture.                                |
|----------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`TEXT_TEXTURE_PREFIX`](#an.stage.text_layout.TEXT_TEXTURE_PREFIX)       | What a text texture's alias starts with — `text.<entity>.<unit>.<digest>`. |
| [`TEXT_ALIAS_DIGEST_LEN`](#an.stage.text_layout.TEXT_ALIAS_DIGEST_LEN)     | Hex digits of the texture's sha256 kept in its alias.                      |
| [`INLINE_SRC_PREFIX`](#an.stage.text_layout.INLINE_SRC_PREFIX)         | The `src` scheme of a texture that carries its bytes inline.               |

### Functions

| [`build_text_subtree`](#an.stage.text_layout.build_text_subtree)(entity, document, \*, ...)    | The block's node and its unit children, plus what it resolved to.                                                                                                                               |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`svg_data_uri`](#an.stage.text_layout.svg_data_uri)(svg)                                | `data:image/svg+xml;base64,…` — the form the vendored engine's SVG loader recognises by prefix.                                                                                                 |
| [`text_document`](#an.stage.text_layout.text_document)(entity, props_store)               | The stored document behind a prop entity if it is a text block, else None.                                                                                                                      |
| [`text_swap_declaration`](#an.stage.text_layout.text_swap_declaration)(entity, mall)              | The core `prop` kind's swap declaration (an#341): a text block with `texts` declares its `text` set, `{key: key}`; any other prop declares nothing (its built nodes' sets are its declaration). |
| [`unit_svg`](#an.stage.text_layout.unit_svg)(d, box, \*, color[, stroke_width, ...]) | One unit's texture: its contours in a viewBox equal to its frame-pixel box.                                                                                                                     |

### an.stage.text_layout.INLINE_SRC_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'data:'*

The `src` scheme of a texture that carries its bytes inline. The staging
step skips it (there is nothing to copy) instead of warning that the prefix
names no store.

### an.stage.text_layout.TEXT_ALIAS_DIGEST_LEN *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 12*

Hex digits of the texture’s sha256 kept in its alias.

### an.stage.text_layout.TEXT_TEXTURE_OVERSAMPLE *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

Texels per scene pixel in a unit’s texture. See the module docstring.

### an.stage.text_layout.TEXT_TEXTURE_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'text.'*

What a text texture’s alias starts with — `text.<entity>.<unit>.<digest>`.

### an.stage.text_layout.build_text_subtree(entity, document, , width, height, base_dir, textures, resolutions)

The block’s node and its unit children, plus what it resolved to.

Raises `ValueError` subclasses (`TextFontError`, `TextLayoutError`,
pydantic’s `ValidationError`) — the compiler wraps them.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`NodeJSON`](an.stage.serialize.html.md#an.stage.serialize.NodeJSON), [`TextDescriptor`](an.stage.text.html.md#an.stage.text.TextDescriptor), [`TextLayout`](an.stage.text.html.md#an.stage.text.TextLayout)]

### an.stage.text_layout.svg_data_uri(svg)

`data:image/svg+xml;base64,…` — the form the vendored engine’s SVG
loader recognises by prefix.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.stage.text_layout.text_document(entity, props_store)

The stored document behind a prop entity if it is a text block, else None.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.stage.text_layout.text_swap_declaration(entity, mall)

The core `prop` kind’s swap declaration (an#341): a text block with
`texts` declares its `text` set, `{key: key}`; any other prop
declares nothing (its built nodes’ sets are its declaration).

Through [`an.genres.EntityKind.swap_declaration`](an.genres.html.md#an.genres.EntityKind.swap_declaration), so the compiler’s
swap vocabulary, its swap checks and `an validate` learn the set the way
they learn a rig’s. `descriptor` stays `None`: the text block has no
lowering, and a descriptor is what a genre’s passes read as a rig. A
document that does not resolve declares nothing here; the builder raises
on it, naming why.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.stage.text_layout.unit_svg(d, box, , color, stroke_width=0.0, stroke_color=None)

One unit’s texture: its contours in a viewBox equal to its frame-pixel box.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> unit_svg("M0 0L2 0L2 2Z", (0, 0, 4, 4), color="#123456")[:60]
'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"'
```

With an outline (an#313) the same contours are drawn first as a stroke
TWICE `stroke_width` wide, round-joined, so `stroke_width` shows outside
the glyph once the fill covers the inner half: two paths rather than
`paint-order`, so no rasteriser’s support for that attribute is assumed.

```pycon
>>> 'stroke-width="6"' in unit_svg("M0 0Z", (0, 0, 4, 4), color="#fff", stroke_width=3, stroke_color="#000")
True
```
