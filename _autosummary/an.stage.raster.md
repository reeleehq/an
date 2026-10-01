# an.stage.raster

Raster art: what a PNG, JPEG or WebP is, read from its header (an#211).

Every piece of art the cutout renderer drew was SVG, and the size probe said
so: `an.characters.svg_utils.raster_size` parses its input as XML, so a PNG
plate died in the compiler with `ParseError: not well-formed (invalid token):
line 1, column 0` — the error a user sees for “I gave it a picture”. Art carved
out of footage, a scanned drawing, a photographed paper cut-out: those are
raster, and tracing them to SVG throws away the shading that made them worth
carving.

PixiJS loads PNG, JPEG and WebP natively (its `loadTextures` parser, chosen by
the file’s extension), so the renderer needed nothing new. What the COMPILER
needed was three answers it previously got only from an SVG:

- **how big is it** — [`image_size()`](#an.stage.raster.image_size), read from the header (no decode, no
  dependency: the four formats state their pixel size in the first few dozen
  bytes, and a header parse is the same cost as the SVG probe it sits beside);
- **what size does this art draw at, whatever it is** — [`art_size()`](#an.stage.raster.art_size), the
  one probe the compiler, the fidelity check and `an validate` call;
- **what exactly is it** — [`content_digest()`](#an.stage.raster.content_digest), because a raster texture is
  addressed by its bytes: a re-carved part is a different texture (the runtime’s
  loader ignores a re-added alias on hot reload, an#155) and a different
  compiled contract, so the contract hash covers the pixels it will draw.

**Known limit: EXIF orientation.** The header size is the stored size. A
JPEG whose EXIF says “rotate 90°” (a phone photo) is decoded upright by
Chromium, so its box would be transposed — export such art rotated.

**Why a raster part is never recoloured.** A StylePack recolours SVG art by
rewriting the literal colours its descriptor tags (`colour_roles`). A raster
has no literals — its colours are pixels, and inferring a role from a pixel is
exactly what caused an#99’s wrong-tone lid — so it renders as drawn, and the
compiler says so once.

```pycon
>>> is_raster("parts/head.png"), is_raster("parts/head.svg")
(True, False)
```

### Module Attributes

| [`RASTER_SUFFIXES`](#an.stage.raster.RASTER_SUFFIXES)   | The raster formats a plate or a part may be, by file suffix.   |
|--------------------------------------------------------------------|----------------------------------------------------------------|

### Functions

| [`art_size`](#an.stage.raster.art_size)(source)           | The size a piece of art rasterises at, whatever format it is.        |
|-----------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`content_digest`](#an.stage.raster.content_digest)(path)       | The hex sha256 of a file's bytes, cached by (path, mtime, size).     |
| [`has_alpha`](#an.stage.raster.has_alpha)(source)          | Whether the image can be transparent anywhere; `None` if unknown.    |
| [`image_size`](#an.stage.raster.image_size)(source)         | `(width, height)` in pixels of a PNG, JPEG or WebP, from its header. |
| [`is_raster`](#an.stage.raster.is_raster)(src)             | Whether `src` names raster art, by its suffix (case-insensitive).    |
| [`strip_version`](#an.stage.raster.strip_version)(src)         | The file path a (possibly versioned) texture `src` names.            |
| [`versioned_src`](#an.stage.raster.versioned_src)(src, digest) | `src` with its content digest as a query string.                     |

### Exceptions

| [`RasterFormatError`](#an.stage.raster.RasterFormatError)   | A file named as raster art whose header this module cannot read.   |
|----------------------------------------------------------------------|--------------------------------------------------------------------|

### an.stage.raster.RASTER_SUFFIXES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('.png', '.jpg', '.jpeg', '.webp')*

The raster formats a plate or a part may be, by file suffix. PixiJS 7’s
`loadTextures` picks its parser by extension and accepts exactly these
(plus AVIF, left out because Chromium’s AVIF decode is the one of the four
whose output is not specified bit-exactly and the render is a contract).

### *exception* an.stage.raster.RasterFormatError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A file named as raster art whose header this module cannot read.

A `ValueError`, so the compiler’s size probe treats it exactly like a
malformed SVG: the art is declared (and fails loudly at load) rather than
silently dropped.

### an.stage.raster.art_size(source)

The size a piece of art rasterises at, whatever format it is.

SVG: its declared `width`/`height` (else its viewBox), as the browser
does — [`an.characters.svg_utils.raster_size()`](an.characters.svg_utils.md#an.characters.svg_utils.raster_size). Raster: its pixel size.
The ONE probe the compiler, the fidelity check and `an validate` share, so
none of them can size a PNG as if it were XML again.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.stage.raster.content_digest(path)

The hex sha256 of a file’s bytes, cached by (path, mtime, size).

The ENCODED bytes, not the pixels: re-saving the same image with another
encoder changes the digest (and so the alias and the contract hash) —
which is the conservative direction for a contract.

Cached because a rig registers every attachment of every slot and a scene
compiles each shot separately; keyed on the stat so an edited file is
re-read, which is what makes the digest safe to put in a texture alias.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.stage.raster.has_alpha(source)

Whether the image can be transparent anywhere; `None` if unknown.

A PNG says so in its header (colour type 4 or 6) or with a `tRNS` chunk;
a JPEG never can; a WebP says so in its `VP8X` flags or by being lossless
with an alpha bit. A cut-out part without alpha is a rectangle — the whole
canvas draws, background and all — which is what `an character validate`
uses this for.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.stage.raster.image_size(source)

`(width, height)` in pixels of a PNG, JPEG or WebP, from its header.

`source` is a path or the file’s bytes.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> import struct, zlib
>>> ihdr = struct.pack(">IIBBBBB", 3, 2, 8, 6, 0, 0, 0)
>>> png = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
...        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)))
>>> image_size(png)
(3.0, 2.0)
```

### an.stage.raster.is_raster(src)

Whether `src` names raster art, by its suffix (case-insensitive).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> is_raster("plates/Street.JPG")
True
>>> is_raster("data:image/svg+xml;base64,AAAA")
False
```

### an.stage.raster.strip_version(src)

The file path a (possibly versioned) texture `src` names.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> strip_version("props/lamp/parts/on.png?v=abc123")
'props/lamp/parts/on.png'
```

### an.stage.raster.versioned_src(src, digest)

`src` with its content digest as a query string.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> versioned_src("props/lamp/parts/on.png", "abc123")
'props/lamp/parts/on.png?v=abc123'
```
