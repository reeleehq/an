# an.adapters.cutout.supersample

Render bigger, then resolve back exactly — the supersample knob’s two halves.

**\`autoDensity: false\` is the whole plumbing finding, and it is load-bearing.**
`resolution: k` alone reproduces the failure it exists to avoid: with
`autoDensity: true` PixiJS sets the canvas CSS size to the *logical* size, so
Chromium composites the k-times backbuffer down before the screenshot — a blind
browser downscale, no filter choice, no record that it happened. Measured on a
declared 320x240 scene: neither key -> 320x240 PNGs; `resolution: 2,
autoDensity: false` -> 640x480; `resolution: 2, autoDensity: true` -> 320x240.
It is the option whose name most suggests it is the right one.

\*\*The resolve is an exact k x k block mean, and calling it a filter would be
wrong\*\* — at an integer ratio it *is* the supersample resolve. Measured against
the alternatives on all six corpus scenes: PIL’s `BOX` agrees with it to four
decimals, and lanczos triples the edge band on the most idiom-like scene
(+208.8% on `saturated_outline`), because its negative lobes ring on hard-edged
flat fills. An ffmpeg-side `-vf scale` is refused for a second, independent
reason: it would move `x264_argv`, refusing every encode-side metric, and retire
the cross-arch verdict’s load-bearing “ffmpeg never touches a frame” clause.

\*\*Why PIL here and not `an.bench.png`.\*\* The bench’s codec exists so a committed
golden is a function of the *pixel data alone* rather than of Chromium’s libpng
settings — a goal about files that get committed and diffed, which render-path
frames are not. And it is the wrong tool for this job by an order of magnitude:
Chromium’s screenshots are Paeth-filtered on ~87% of rows (measured: 209 of 240),
which takes its scalar unfilter path at **416 ns/px against PIL’s 31 ns/px**.
Extrapolated to a 3840x2160 supersampled frame that is \*\*3.46 s of decoding per
frame\*\* versus 256 ms — more than the render itself costs. `pillow` is declared
by the `cutout` extra, which this module cannot run without anyway.

### Module Attributes

| [`NO_SUPERSAMPLE`](#an.adapters.cutout.supersample.NO_SUPERSAMPLE)   | The factor at which every code path here is a no-op rather than merely cheap.   |
|-------------------------------------------------------------------|---------------------------------------------------------------------------------|

### Functions

| [`block_mean_resolve`](#an.adapters.cutout.supersample.block_mean_resolve)(frame, factor)   | `(H*k, W*k, C)` uint8 -> `(H, W, C)` uint8, by an exact `k x k` mean.   |
|--------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`check_factor`](#an.adapters.cutout.supersample.check_factor)(factor)                | Validate a supersample factor, or refuse with the reason.               |
| [`resolve_png_bytes`](#an.adapters.cutout.supersample.resolve_png_bytes)(data, \*, factor) | Decode a screenshot, block-mean it down by `factor`, re-encode.         |

### Exceptions

| [`SupersampleError`](#an.adapters.cutout.supersample.SupersampleError)   | A supersample factor or frame that cannot be resolved exactly.   |
|---------------------------------------------------------------------|------------------------------------------------------------------|

### an.adapters.cutout.supersample.NO_SUPERSAMPLE *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

The factor at which every code path here is a no-op rather than merely cheap.
Aliased from [`an.base.DEFAULT_SUPERSAMPLE`](an.base.html.md#an.base.DEFAULT_SUPERSAMPLE) rather than restated: the
default and the off-switch are the same fact, and two copies of a fact drift.

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
an.adapters.cutout.supersample.SupersampleError: supersample must be >= 1, got 0
```

### an.adapters.cutout.supersample.resolve_png_bytes(data, , factor)

Decode a screenshot, block-mean it down by `factor`, re-encode.

Returns `data` unchanged at `factor == 1`, so the un-supersampled path
keeps Chromium’s own bytes and pays nothing at all — which is what makes
this knob free when it is off.

**The early return sits above the imports deliberately.** “Off is free”
should mean free of the *dependency* too: Pillow is declared by the `cutout`
extra, so the default path must not need it merely to decide it has nothing
to do. Without this, importing it here would make the knob’s own tests
unrunnable in the default CI lane, which installs `dev,test` and not
`cutout` — and CI is where that was found.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)
