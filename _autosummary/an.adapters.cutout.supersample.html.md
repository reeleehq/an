# an.adapters.cutout.supersample

Moved to [`an.media.supersample`](an.media.supersample.html.md#module-an.media.supersample) (an#247); this path re-exports it.

The spatial resolve is engine-independent, so it lives in the core’s media
package. Every name below is the same object as in its new home.

### Functions

| [`block_mean_resolve`](#an.adapters.cutout.supersample.block_mean_resolve)(frame, factor)   | `(H*k, W*k, C)` uint8 -> `(H, W, C)` uint8, by an exact `k x k` mean.   |
|--------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`check_factor`](#an.adapters.cutout.supersample.check_factor)(factor)                | Validate a supersample factor, or refuse with the reason.               |
| [`resolve_png_bytes`](#an.adapters.cutout.supersample.resolve_png_bytes)(data, \*, factor) | Decode a screenshot, block-mean it down by `factor`, re-encode.         |

### Exceptions

| [`SupersampleError`](#an.adapters.cutout.supersample.SupersampleError)   | A supersample factor or frame that cannot be resolved exactly.   |
|---------------------------------------------------------------------|------------------------------------------------------------------|

### *exception* an.adapters.cutout.supersample.SupersampleError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A supersample factor or frame that cannot be resolved exactly.

### an.adapters.cutout.supersample.block_mean_resolve(frame, factor)

`(H*k, W*k, C)` uint8 -> `(H, W, C)` uint8, by an exact `k x k` mean.

Two-step, summing rows and then columns in `uint16`, rather than the
obvious `reshape(...).astype(float64).mean(axis=(1, 3))`. The two agree
**bit for bit** — asserted exhaustively over every possible 2x2 block, and
on real frames — and the two-step form is 2.3x faster at 1080p (111.7 ms
against 262.0 ms), because the cost here is the strided reduce and the
64-bit temporary, not the arithmetic.

Rounding is spelled out rather than inherited: `np.rint` is banker’s
rounding, so a block averaging exactly `.5` goes to the EVEN neighbour.
Getting that wrong changes one code value on every half-block, which is
invisible in a picture and moves every golden.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> f = np.array([[0, 0, 1, 2], [0, 4, 1, 2]], np.uint8)[..., None].repeat(3, -1)
>>> block_mean_resolve(f, 2)[0, :, 0].tolist()
[1, 2]
>>> block_mean_resolve(f, 1) is f
True
```

### an.adapters.cutout.supersample.check_factor(factor)

Validate a supersample factor, or refuse with the reason.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> check_factor(1), check_factor(2)
(1, 2)
>>> check_factor(0)
Traceback (most recent call last):
  ...
an.media.supersample.SupersampleError: supersample must be >= 1, got 0
```

### an.adapters.cutout.supersample.resolve_png_bytes(data, , factor)

Decode a screenshot, block-mean it down by `factor`, re-encode.

Returns `data` unchanged at `factor == 1`, so the un-supersampled path
keeps Chromium’s own bytes and pays nothing at all — which is what makes
this knob free when it is off.

**The early return sits above the imports deliberately.** “Off is free”
should mean free of the *dependency* too: the default path must not need
Pillow merely to decide it has nothing to do. (Found in CI, when Pillow came
only with the `cutout` extra and the default lane did not install it.)

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)
