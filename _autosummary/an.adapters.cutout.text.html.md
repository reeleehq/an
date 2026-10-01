# an.adapters.cutout.text

A text block, compiled: one node per unit, each an SVG sprite (an#155).

[`an.text.layout_text()`](an.text.html.md#an.text.layout_text) asks tituli where every unit goes and what its
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
  `scale_x`/`scale_y` pop or a `rotation` pivots about the unit’s middle.

**Crispness.** The SVG declares `TEXT_TEXTURE_OVERSAMPLE` x its box as its
intrinsic size, and the sprite is fitted back into the box (`fit="contain"`),
so a texel is half a scene pixel: an overlay at 1:1 samples it as a clean 2:1
box filter, and a world label survives a push-in. Every box is snapped outward
to whole pixels, so at zoom 1 a sprite’s corners sit on the pixel grid.

### Module Attributes

| [`TEXT_TEXTURE_OVERSAMPLE`](#an.adapters.cutout.text.TEXT_TEXTURE_OVERSAMPLE)   | Texels per scene pixel in a unit's texture.                                |
|----------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`TEXT_TEXTURE_PREFIX`](#an.adapters.cutout.text.TEXT_TEXTURE_PREFIX)       | What a text texture's alias starts with — `text.<entity>.<unit>.<digest>`. |
| [`TEXT_ALIAS_DIGEST_LEN`](#an.adapters.cutout.text.TEXT_ALIAS_DIGEST_LEN)     | Hex digits of the texture's sha256 kept in its alias.                      |
| [`INLINE_SRC_PREFIX`](#an.adapters.cutout.text.INLINE_SRC_PREFIX)         | The `src` scheme of a texture that carries its bytes inline.               |

### Functions

| [`build_text_subtree`](#an.adapters.cutout.text.build_text_subtree)(entity, document, \*, ...)   | The block's node and its unit children, plus what it resolved to.                               |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| [`svg_data_uri`](#an.adapters.cutout.text.svg_data_uri)(svg)                               | `data:image/svg+xml;base64,…` — the form the vendored engine's SVG loader recognises by prefix. |
| [`text_document`](#an.adapters.cutout.text.text_document)(entity, props_store)              | The stored document behind a prop entity if it is a text block, else None.                      |
| [`unit_svg`](#an.adapters.cutout.text.unit_svg)(d, box, \*, color)                     | One unit's texture: its contours in a viewBox equal to its frame-pixel box.                     |

### an.adapters.cutout.text.INLINE_SRC_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'data:'*

The `src` scheme of a texture that carries its bytes inline. The staging
step skips it (there is nothing to copy) instead of warning that the prefix
names no store.

### an.adapters.cutout.text.TEXT_ALIAS_DIGEST_LEN *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 12*

Hex digits of the texture’s sha256 kept in its alias.

### an.adapters.cutout.text.TEXT_TEXTURE_OVERSAMPLE *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

Texels per scene pixel in a unit’s texture. See the module docstring.

### an.adapters.cutout.text.TEXT_TEXTURE_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'text.'*

What a text texture’s alias starts with — `text.<entity>.<unit>.<digest>`.

### an.adapters.cutout.text.build_text_subtree(entity, document, , width, height, base_dir, textures, resolutions)

The block’s node and its unit children, plus what it resolved to.

Raises `ValueError` subclasses (`TextFontError`, `TextLayoutError`,
pydantic’s `ValidationError`) — the compiler wraps them.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`NodeJSON`](an.adapters.cutout.serialize.html.md#an.adapters.cutout.serialize.NodeJSON), [`TextDescriptor`](an.text.html.md#an.text.TextDescriptor), [`TextLayout`](an.text.html.md#an.text.TextLayout)]

### an.adapters.cutout.text.svg_data_uri(svg)

`data:image/svg+xml;base64,…` — the form the vendored engine’s SVG
loader recognises by prefix.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.adapters.cutout.text.text_document(entity, props_store)

The stored document behind a prop entity if it is a text block, else None.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.adapters.cutout.text.unit_svg(d, box, , color)

One unit’s texture: its contours in a viewBox equal to its frame-pixel box.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> unit_svg("M0 0L2 0L2 2Z", (0, 0, 4, 4), color="#123456")[:60]
'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"'
```
