# an.media.grid

Tile images into one contact sheet: [`tile()`](#an.media.grid.tile) (an#347).

A small pure function over PNG bytes — decoded and encoded by
[`an.bench.png`](an.bench.png.md#module-an.bench.png) (numpy and the standard library), each image fitted into a
square cell without distortion, an optional caption under each. `an probe`
tiles several instants of a shot with it and `an library sheet` one specimen
per asset.

Candidate fleet component: one production wrote three ad hoc copies of this
before it existed (design of an#331, §5.3).

```pycon
>>> from an.bench.png import decode_png, encode_png
>>> import numpy as np
>>> red = encode_png(np.full((4, 8, 3), (255, 0, 0), np.uint8))
>>> sheet = decode_png(tile([red, red, red], cell=16, columns=2))
>>> sheet.shape
(44, 44, 3)
```

### Functions

| [`tile`](#an.media.grid.tile)(images, \*[, cell, columns, labels, ...])   | One PNG holding every image of `images` (PNG bytes), each in a `cell` square.      |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`trim`](#an.media.grid.trim)(image, \*[, tolerance, margin])             | `image` (PNG bytes) cropped to what differs from its corner colour, plus a margin. |

### an.media.grid.tile(images, , cell=256, columns=None, labels=None, gap=4, background=(255, 255, 255))

One PNG holding every image of `images` (PNG bytes), each in a `cell` square.

columns: cells per row (default: the smallest square grid that holds them)
labels: one caption per image, drawn under its cell

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.media.grid.trim(image, , tolerance=8, margin=0.06)

`image` (PNG bytes) cropped to what differs from its corner colour, plus a margin.

An image that is all background is returned unchanged.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

```pycon
>>> import numpy as np
>>> a = np.full((20, 20, 3), 255, np.uint8); a[5:9, 10:12] = 0
>>> decode_png(trim(encode_png(a), margin=0)).shape
(4, 2, 3)
```
