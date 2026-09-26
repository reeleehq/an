# an.bench.masks

Every mask the panel is computed over, and the recorded operator for each.

Three of them serve the encode-side metrics, plus the ring. `EDGE_OPERATOR`
has a second spelling, `RENDER_EDGE_OPERATOR`: the same operator applied on
the **render** side, where the luma comes from the source RGB rather than from
ffmpeg. It is a second string rather than a reuse because it measures a
different plane — which is also what keeps family A’s mask off the encoder’s
toolchain, on the branch where ffmpeg is absent.

Each mask is derived **only from the reference (pre-encode) frames**, never
from the decoded ones. That is not a stylistic choice: a mask derived from the
decoded stream moves with the mutation, which is the defect that made
`edge_ssim` invisible on the AA arm (Δ = +0.0004, ~11x the machine band,
because the reference moved with the mutation).

Every operator here is exported as a **string** as well as a function, because
the ledger has to record what it measured — a threshold nobody can read back is
a threshold that quietly changes.

### Module Attributes

| [`EDGE_MASK_THRESHOLD`](#an.bench.masks.EDGE_MASK_THRESHOLD)   | Two-pixel-apart luma gradient above this counts as an edge.                                                    |
|------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| [`FLAT_DILATE_K`](#an.bench.masks.FLAT_DILATE_K)         | Structuring element for the flat-field erosion.                                                                |
| [`RENDER_EDGE_OPERATOR`](#an.bench.masks.RENDER_EDGE_OPERATOR)  | The SAME operator on the render side, and deliberately a second string rather than a reuse of `EDGE_OPERATOR`. |

### Functions

| [`dilate`](#an.bench.masks.dilate)(mask[, k])                | Binary dilation by a `k x k` square, numpy-only.                        |
|-----------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`edge_mask`](#an.bench.masks.edge_mask)(luma, \*[, threshold]) | Pixels straddling a hard luma step, from the reference plane only.      |
| [`flat_mask`](#an.bench.masks.flat_mask)(rgb, \*[, k])          | The interior of large flat colour fields, from the source frames.       |
| [`held_mask`](#an.bench.masks.held_mask)(rgb)                   | `(N-1, H, W)`: pixels the animator held perfectly still between frames. |
| [`ring_mask`](#an.bench.masks.ring_mask)(edge)                  | The band immediately *around* an edge, excluding the edge itself.       |

### an.bench.masks.EDGE_MASK_THRESHOLD *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 40*

Two-pixel-apart luma gradient above this counts as an edge. Recorded in the
ledger with the operator string, because the research is explicit that the
prototype’s absolute numbers are ordinal evidence only and no threshold may
be written from them.

### an.bench.masks.FLAT_DILATE_K *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 3*

Structuring element for the flat-field erosion.

### an.bench.masks.RENDER_EDGE_OPERATOR *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'max(|Y[:,2:]-Y[:,:-2]|, |Y[2:,:]-Y[:-2,:]|) > 40, on FULL-RANGE BT.709 luma from the SOURCE RGB (an.bench.metrics.luma_u8)'*

The SAME operator on the render side, and deliberately a second string
rather than a reuse of `EDGE_OPERATOR`. `an.bench.imageio`’s
`SOURCE_SCALE_FILTER` pins `out_range=tv`, so ffmpeg’s Y lives in [16,235]
and its two-apart gradients are 219/255 of the full-range ones this operator
sees. At one threshold that makes this the wider mask ON A HARD SYNTHETIC
STEP — measured, a 45-code-value step selects 4 pixels here and 0 on the
limited-range plane — but NOT uniformly on real frames, where the two run
within a percent either way and the render-side one is the narrower on
`graded_field` and `single_character`. Which is the point: the two are
different measurements, and a reader can only know which one a row carries
if the row says which plane it measured.

### an.bench.masks.dilate(mask, k=3)

Binary dilation by a `k x k` square, numpy-only.

Implemented as shifted ORs rather than a convolution: `k` is 2 or 3 here,
so nine shifts beat pulling in scipy, and the package’s dependency
perimeter is four names wide on purpose.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> m = np.zeros((1, 5, 5), bool); m[0, 2, 2] = True
>>> int(dilate(m, 3)[0].sum())
9
```

### an.bench.masks.edge_mask(luma, , threshold=40)

Pixels straddling a hard luma step, from the reference plane only.

`luma` is `(N, H, W)` uint8. The border ring is excluded because a
two-apart difference is undefined there; excluding it is what keeps the
operator string honest.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> y = np.zeros((1, 5, 6), np.uint8); y[0, :, 3:] = 255
>>> int(edge_mask(y).sum())
6
```

### an.bench.masks.flat_mask(rgb, , k=3)

The interior of large flat colour fields, from the source frames.

~90% of a flat-cutout frame, and the part no edge metric touches. Banding
and blocking live here, and without this mask they are invisible.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> a = np.zeros((1, 9, 9, 3), np.uint8); a[0, :, 5:] = 255
>>> bool(flat_mask(a)[0, 0, 0]) and not bool(flat_mask(a)[0, 0, 5])
True
```

### an.bench.masks.held_mask(rgb)

`(N-1, H, W)`: pixels the animator held perfectly still between frames.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> a = np.zeros((2, 3, 3, 3), np.uint8); a[1, 0, 0] = 5
>>> int(held_mask(a).sum())
8
```

### an.bench.masks.ring_mask(edge)

The band immediately *around* an edge, excluding the edge itself.

Where ringing and mosquito noise land. Excluding the edge is what makes it
a different measurement from `coded_luma_edge_error` rather than a second
name for it.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> e = np.zeros((1, 5, 5), bool); e[0, 2, 2] = True
>>> int(ring_mask(e).sum())
8
```
