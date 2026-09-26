# an.bench.png

A filter-0 PNG writer and a full-filter reader — numpy and stdlib only.

The golden corpus is committed as PNGs, and the gate compares \*\*decoded
pixels\*\*. Both halves of that sentence need this module.

**Why write our own encoder rather than copy Chromium’s bytes.** A committed
golden written by copying the screenshot file is a function of Chromium’s
libpng settings as well as of the picture. Re-encoding every row with filter
type 0 makes the committed file a function of the **pixel data alone**, so a
future Chromium bump that changes its filter heuristic produces no diff at all
when the picture has not moved. Measured on the five real frames in this repo,
filter-0 re-encoding is also *smaller* every time — between -5.2% and -22.3%
(research §3 recorded -0.30%, from a single frame; the range is wider both ways
than one sample suggested).

**Why the reader must handle all five filter types.** The bless path reads
Chromium’s own screenshots, and Chromium emits Sub / Up / Paeth. Only the files
this module writes are filter-0.

\*\*Why the filters are unfiltered over a `bytearray` rather than a numpy
array.\*\* Sub, Average and Paeth are sequential along the row — byte *x* depends
on byte *x - bpp* of the same row — so they cannot be vectorised, and the inner
loop is scalar either way. Scalar indexing into a `bytearray` is measurably
cheaper than into a numpy array: 32 ms against 111 ms for a 320x240 Chromium
frame, and 444 ms against 2,430 ms for a mixed-filter 1920x1080 one. A filter-0
file skips the loop entirely (a whole-row slice), which is why reading a golden
costs ~0.1 ms at 320x240 and ~1.8 ms at 1080p.

The round trip is exact, and it is verified in both directions against an
independent decoder: `ffmpeg -pix_fmt rgb24` agrees with [`decode_png()`](#an.bench.png.decode_png)
on every rendered frame in the repo, and reads back what [`encode_png()`](#an.bench.png.encode_png)
writes.

### Module Attributes

| [`PNG_SIGNATURE`](#an.bench.png.PNG_SIGNATURE)       | PNG's fixed 8-byte signature.                                                                                                   |
|----------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_ZLIB_LEVEL`](#an.bench.png.DFLT_ZLIB_LEVEL)     | zlib level for the IDAT stream.                                                                                                 |
| [`RGB_CHANNELS`](#an.bench.png.RGB_CHANNELS)        | What [`encode_png()`](#an.bench.png.encode_png) writes, and the only channel count the golden gate compares. |
| [`SUPPORTED_BIT_DEPTH`](#an.bench.png.SUPPORTED_BIT_DEPTH) | Bit depth.                                                                                                                      |
| [`PNG_HEADER_BYTES`](#an.bench.png.PNG_HEADER_BYTES)    | the 8-byte signature, a 4-byte chunk length, the 4-byte `IHDR` tag, and two big-endian uint32s.                                 |

### Functions

| [`decode_png`](#an.bench.png.decode_png)(data)                  | Decode an 8-bit truecolour PNG to `(H, W, C)` uint8, `C` in `{3, 4}`.         |
|------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`encode_png`](#an.bench.png.encode_png)(rgb, \*[, level])      | Encode `(H, W, 3)` uint8 as an 8-bit truecolour PNG, every row filter 0.      |
| [`png_dimensions`](#an.bench.png.png_dimensions)(data)              | `(width, height)` from a PNG's IHDR, without decoding a single pixel.         |
| [`read_png`](#an.bench.png.read_png)(path)                    | `(H, W, 3)` uint8 for a PNG on disk, alpha dropped only if opaque.            |
| [`read_png_dimensions`](#an.bench.png.read_png_dimensions)(path)         | `(width, height)` for a PNG on disk, reading only its header.                 |
| [`to_rgb`](#an.bench.png.to_rgb)(arr)                       | Drop a **fully opaque** alpha channel, refusing to drop a meaningful one.     |
| [`write_png`](#an.bench.png.write_png)(path, rgb, \*[, level]) | Write `rgb` as a filter-0 PNG and **verify the round trip** before returning. |

### Exceptions

| [`PngFormatError`](#an.bench.png.PngFormatError)   | A PNG this module deliberately does not decode, or a malformed one.   |
|-------------------------------------------------------------------|-----------------------------------------------------------------------|

### an.bench.png.DFLT_ZLIB_LEVEL *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 9*

zlib level for the IDAT stream. 9 because a golden is written rarely and
read often, and because the committed bytes are reviewed in a diff.

### an.bench.png.PNG_HEADER_BYTES *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 24*

the 8-byte signature, a
4-byte chunk length, the 4-byte `IHDR` tag, and two big-endian uint32s. PNG
requires IHDR to be the FIRST chunk, so this prefix is always enough.

* **Type:**
  Bytes needed to read an image’s declared size

### an.bench.png.PNG_SIGNATURE *: [bytes](https://docs.python.org/3/builtins/stdtypes.html#bytes)* *= b'\\x89PNG\\r\\n\\x1a\\n'*

PNG’s fixed 8-byte signature.

### *exception* an.bench.png.PngFormatError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A PNG this module deliberately does not decode, or a malformed one.

Typed and specific on purpose: the alternative to refusing is returning a
plausible array, and a golden gate that compares a plausible array is worse
than one that does not run.

### an.bench.png.RGB_CHANNELS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 3*

What [`encode_png()`](#an.bench.png.encode_png) writes, and the only channel count the golden gate
compares. Alpha is dropped at the boundary (see [`to_rgb()`](#an.bench.png.to_rgb)), never here.

### an.bench.png.SUPPORTED_BIT_DEPTH *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 8*

Bit depth. 16-bit PNGs are refused rather than truncated — a silently
halved code value is exactly the class of bug this corpus exists to catch.

### an.bench.png.decode_png(data)

Decode an 8-bit truecolour PNG to `(H, W, C)` uint8, `C` in `{3, 4}`.

Refuses — rather than approximates — 16-bit, palette, greyscale and
interlaced images, naming what it found.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> a = np.array([[[1, 2, 3], [4, 5, 6]]], np.uint8)
>>> np.array_equal(decode_png(encode_png(a)), a)
True
```

### an.bench.png.encode_png(rgb, , level=9)

Encode `(H, W, 3)` uint8 as an 8-bit truecolour PNG, every row filter 0.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

```pycon
>>> import numpy as np
>>> data = encode_png(np.zeros((2, 3, 3), np.uint8))
>>> data[:8] == PNG_SIGNATURE
True
>>> decode_png(data).shape
(2, 3, 3)
```

### an.bench.png.png_dimensions(data)

`(width, height)` from a PNG’s IHDR, without decoding a single pixel.

Width first, matching the PNG header itself — and deliberately the opposite
order from [`read_png()`](#an.bench.png.read_png), which returns `(H, W, C)` like every other
array here. Getting it backwards produces a square-looking check that
passes on square frames only, so the order is asserted in the tests.

Cheap on purpose. The bench reads this for **every** frame on disk rather
than sampling one, because the failure it exists to catch — a render whose
frame size changed partway through — is exactly the one sampling misses.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]

```pycon
>>> import numpy as np
>>> png_dimensions(encode_png(np.zeros((240, 320, 3), np.uint8)))
(320, 240)
```

### an.bench.png.read_png(path)

`(H, W, 3)` uint8 for a PNG on disk, alpha dropped only if opaque.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.bench.png.read_png_dimensions(path)

`(width, height)` for a PNG on disk, reading only its header.

A 1080p frame is megabytes and its declared size is in the first 24 of
them. Reading only those is what makes checking every frame of every shot
free rather than a second full decode of the corpus.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]

### an.bench.png.to_rgb(arr)

Drop a **fully opaque** alpha channel, refusing to drop a meaningful one.

The golden gate compares RGB ([`an.bench.metrics.golden_comparison()`](an.bench.metrics.html.md#an.bench.metrics.golden_comparison)
takes three channels). Dropping alpha unconditionally would make a
transparency regression invisible to the one gate that exists to see
changes, so a non-opaque alpha is an error rather than a silent narrowing.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> to_rgb(np.full((1, 1, 4), 255, np.uint8)).shape
(1, 1, 3)
```

### an.bench.png.write_png(path, rgb, , level=9)

Write `rgb` as a filter-0 PNG and **verify the round trip** before returning.

The verification is not defensive noise: it is the only thing standing
between a bug in this module’s own encoder and a committed golden that
silently disagrees with the frame it was blessed from. Research §3 asks for
exactly this — “assert the round trip at bless time against the in-memory
screenshot pixels, so a bug in `an`’s own encoder cannot hide”.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)
