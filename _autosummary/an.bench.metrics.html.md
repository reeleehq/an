# an.bench.metrics

The metric panel: pure numpy, no I/O, no subprocess.

Every function here is `f(arrays, mask) -> float`. Loading is
[`an.bench.imageio`](an.bench.imageio.html.md#module-an.bench.imageio)’s job. The split is what lets the whole panel run in
the default CI leg — numpy is a hard dependency, ffmpeg and Playwright are not
— which is the only part of this wave that main CI can ever see.

**The set is the research’s corrected one, and it is not the epic’s draft.**
All twelve originally-proposed metrics were refuted. The corrections that are
easiest to undo by accident, each guarded by a test:

- `edge_transition_width`’s flatness tolerance must not be 0. With `> 0`,
  ±3-LSB dither sends the metric to 255.0.
- `off_palette_pixel_fraction` must not use `np.unique(..., axis=0)`:
  1.833 s/frame at 1080p against 0.019 s for the packed form, 94x, identical
  result.
- `encode_flicker_on_held_pixels` must **cast before subtracting**.
  `np.abs(a - b)` on uint8 is the identity on unsigned dtypes, so the literal
  proposed form measured the *sign* of the change. It stayed monotone, which is
  exactly why it would have shipped unnoticed. And it must report a **rate**,
  not a mean: the median held-pixel delta is 0 at every CRF.
- `encode_ringing_excess` is the difference of two overshoot means, so the
  source-hardness term cancels. Raw overshoot is a joint function of source
  hardness and encoder fidelity with one degree of freedom, which is why any
  move toward crisper outlines raised it under an unchanged encoder.
- `edge_masked_distinct_colours` must be handed a mask built from
  [`luma_u8()`](#an.bench.metrics.luma_u8), never from [`luma709()`](#an.bench.metrics.luma709) directly. `luma709` returns
  > **float in [0,1]** and [`an.bench.masks.edge_mask()`](an.bench.masks.html.md#an.bench.masks.edge_mask) thresholds at \*\*40 on
  > 0-255\*\*, so the float form makes every two-apart gradient <= 1.0 and the mask
  > comes back **entirely empty** — measured: 0 selected pixels against 4 for the
  > same hard step. The metric would then be `nan` on every scene, which reads
  > as “the check could not run” rather than as a bug (an#55).

One metric the epic named is deliberately absent: `mean_adjacent_frame_ssim`
moves the **wrong way** (0.958 at crf18 -> 0.977 at crf51, because a crushed
video is smoother). Its existing use as a frozen-render detector in
[`an.verify.media_quality`](an.verify.media_quality.html.md#module-an.verify.media_quality) is a different and legitimate job.

### Module Attributes

| [`EDGE_FLAT_TOL`](#an.bench.metrics.EDGE_FLAT_TOL)      | Two neighbours within this many code values count as "flat".                                                                                                     |
|---------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`EDGE_TRIM`](#an.bench.metrics.EDGE_TRIM)          | Trim fraction for `edge_transition_width`'s mean, so one pathological run cannot carry the number.                                                               |
| [`FLAT_DEV_TOL`](#an.bench.metrics.FLAT_DEV_TOL)       | A flat-field pixel more than this far off is "deviated".                                                                                                         |
| [`FLICKER_DELTA_TOL`](#an.bench.metrics.FLICKER_DELTA_TOL)  | A held pixel that moved by at least this much "flickered".                                                                                                       |
| [`SSIM_RADIUS`](#an.bench.metrics.SSIM_RADIUS)        | `ssim_map` window radius; 7x7, matched to feature size rather than the global-moment form.                                                                       |
| [`FLAT_DEV_TOL_SWEEP`](#an.bench.metrics.FLAT_DEV_TOL_SWEEP) | The neighbourhood of each threshold counter's OWN free parameters over which its verdict must agree before `an bench-compare` will call it a direction (an#140). |
| [`BLEND_TOLERANCE`](#an.bench.metrics.BLEND_TOLERANCE)    | How far off the line between two palette colours a pixel may sit and still be called a blend of them.                                                            |
| [`LUMA_709`](#an.bench.metrics.LUMA_709)           | BT.709 luma coefficients, recorded in the ledger so a future change to the reduction is visible rather than folded into the number.                              |

### Functions

| [`classify_off_palette`](#an.bench.metrics.classify_off_palette)(entries, palette)             | Say, for each off-palette colour, whether it is a blend of two declared ones.   |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`edge_masked_distinct_colours`](#an.bench.metrics.edge_masked_distinct_colours)(packed, edge)         | Mean distinct colours per frame, counted ONLY on the edge mask.                 |
| [`edge_transition_width`](#an.bench.metrics.edge_transition_width)(rgb, \*[, tol, trim])        | Average thickness, in pixels, of the fuzzy band between two flat areas.         |
| [`encode_flicker_on_held_pixels`](#an.bench.metrics.encode_flicker_on_held_pixels)(src_rgb, ...)        | Fraction of perfectly-held pixels that moved in the delivered video.            |
| [`encode_flicker_sweep`](#an.bench.metrics.encode_flicker_sweep)(src_rgb, dec_rgb, \*[, tols]) | `encode_flicker_on_held_pixels`' count at every `tol` of its sweep.             |
| [`encode_ringing_excess`](#an.bench.metrics.encode_ringing_excess)(dec_luma, ...)               | How much more the lossy encode overshoots than a lossless one does.             |
| [`flat_field_deviation`](#an.bench.metrics.flat_field_deviation)(src_rgb, dec_rgb, flat, \*)   | Fraction of flat-field pixels the encoder moved by more than `tol`.             |
| [`flat_field_deviation_sweep`](#an.bench.metrics.flat_field_deviation_sweep)(src_rgb, dec_rgb, ...)  | `flat_field_deviation`'s count at every `(dilate_k, tol)` of its sweep.         |
| [`frame_distinct_colours`](#an.bench.metrics.frame_distinct_colours)(packed)                     | Mean number of distinct colours per frame.                                      |
| [`golden_comparison`](#an.bench.metrics.golden_comparison)(today_rgb, golden_rgb)           | The full-frame identity gate plus its diagnostics.                              |
| [`luma709`](#an.bench.metrics.luma709)(rgb)                                       | `(H,W,3)` uint8 -> `(H,W)` float in [0,1].                                      |
| [`luma_u8`](#an.bench.metrics.luma_u8)(rgb)                                       | `(...,3)` uint8 -> `(...)` uint8 luma, on the 0-255 scale a plane uses.         |
| [`masked_mean_abs`](#an.bench.metrics.masked_mean_abs)(a, b, mask)                        | `|a - b|` averaged over `mask`, with the cast that makes it correct.            |
| [`off_palette_pixel_fraction`](#an.bench.metrics.off_palette_pixel_fraction)(packed, palette)        | Fraction of the frame whose colour is not one the compiler declared.            |
| [`off_palette_top_colours`](#an.bench.metrics.off_palette_top_colours)(packed, palette, \*)       | The most frequent off-palette colours, as `[{"hex", "count"}]`.                 |
| [`overshoot_mean`](#an.bench.metrics.overshoot_mean)(dec_luma, src_luma, ring)           | Mean positive excursion above the source, over the ring band.                   |
| [`pack_rgb`](#an.bench.metrics.pack_rgb)(rgb)                                      | `(N,H,W,3)` uint8 -> `(N,H,W)` uint32, one integer per colour.                  |
| [`ssim_map`](#an.bench.metrics.ssim_map)(a, b, \*[, r])                            | Windowed SSIM at stride 1, as a per-pixel map.                                  |
| [`sweep_cell_key`](#an.bench.metrics.sweep_cell_key)(\*\*params)                         | The label of one cell of a parameter sweep, stable across rows.                 |

### an.bench.metrics.BLEND_TOLERANCE *: int* *= 3*

How far off the line between two palette colours a pixel may sit and still
be called a blend of them. 8-bit channels, so a couple of code values covers
rounding in the compositor.

### an.bench.metrics.EDGE_FLAT_TOL *: int* *= 4*

Two neighbours within this many code values count as “flat”. NOT 0 — see
the module docstring.

### an.bench.metrics.EDGE_TRIM *: float* *= 0.1*

Trim fraction for `edge_transition_width`’s mean, so one pathological run
cannot carry the number.

### an.bench.metrics.FLAT_DEV_TOL *: int* *= 6*

A flat-field pixel more than this far off is “deviated”.

### an.bench.metrics.FLAT_DEV_TOL_SWEEP *: tuple[int, ...]* *= (4, 5, 6, 7, 8)*

The neighbourhood of each threshold counter’s OWN free parameters over which
its verdict must agree before `an bench-compare` will call it a direction
(an#140). `flat_field_deviation` is `(dev > tol).mean()` over a mask
eroded by `FLAT_DILATE_K`; both are free, and measured on one machine and
one x264 build its direction under a 4:2:0 -> 4:4:4 change reversed on three
of six scenes somewhere on this grid (`graded_field` +84.2% at tol 6,
-81.6% at tol 8). Every shipped value sits inside its own sweep, so a sweep
that disagrees is the row saying “somewhere near my own settings, my
direction reverses”. The grids are the ones the defect was measured on, not
tuned ones; the flicker grid is one-sided below because tol 0 counts every
pixel.

### an.bench.metrics.FLICKER_DELTA_TOL *: int* *= 2*

A held pixel that moved by at least this much “flickered”.

### an.bench.metrics.LUMA_709 *: tuple[float, float, float]* *= (0.2126, 0.7152, 0.0722)*

BT.709 luma coefficients, recorded in the ledger so a future change to the
reduction is visible rather than folded into the number.

### an.bench.metrics.SSIM_RADIUS *: int* *= 3*

`ssim_map` window radius; 7x7, matched to feature size rather than the
global-moment form.

### an.bench.metrics.classify_off_palette(entries, palette)

Say, for each off-palette colour, whether it is a blend of two declared ones.

This is the difference between a diagnostic and a list of hex codes. The
metric’s whole meaning is “not one of the colours the compiler declared”,
so a palette that under-collects turns it into a large, plausible number
with no error anywhere. Anti-aliasing legitimately produces colours \*on the
segment between\* two declared colours; a missed literal does not.

So each entry gains `blend_of` (the two palette colours it sits between,
or `None`). A row whose top off-palette colours are all blends is
reporting anti-aliasing correctly. One that is not is a derivation bug, and
now it says so in the ledger rather than waiting for someone to look.

* **Return type:**
  `list`[`dict`]

```pycon
>>> classify_off_palette([{"hex": "#808080"}], [0x000000, 0xffffff])[0]["blend_of"]
['#000000', '#ffffff']
>>> classify_off_palette([{"hex": "#ff00ff"}], [0x000000, 0xffffff])[0]["blend_of"]
```

### an.bench.metrics.edge_masked_distinct_colours(packed, edge)

Mean distinct colours per frame, counted ONLY on the edge mask.

The half of `frame_distinct_colours` that is about edges: an interior-only
change — a gradient laid into a flat field, a soft shadow — moves the
whole-frame count and cannot reach this one at all. The second doctest
below is that property, and it is the whole of what the mask buys.

\*\*It does NOT make the number blind to a whole-frame blur, and an#55’s
premise that it would is refuted.\*\* The mask is recomputed from the frame
being measured, and a blur WIDENS the edge band, so the mask grows to admit
the new gradation. Measured on the six committed goldens, 3x3 box blur,
ratio against k=1:

| scene             | whole-frame   | edge-masked   |
|-------------------|---------------|---------------|
| aa_probe          | 10.25x        | 9.50x         |
| graded_field      | 2.04x         | 2.35x         |
| multi_shot        | 7.92x         | 4.63x         |
| promote_demo      | 1.25x         | 0.83x         |
| saturated_outline | 1.49x         | 1.14x         |
| single_character  | 8.60x         | 5.70x         |

Damped on four of six, WORSE on `graded_field`, and nowhere near blind.
(an#55 quotes “1.8x-9.3x” for the whole-frame column; the real range on
these goldens is 1.25x-10.25x, wider at both ends.)

\*\*What separates a blur from a supersample is the WIDTH half of the pair,
not this one.\*\* The same blur puts `edge_transition_width` at 2.1x-3.4x
(`aa_probe` 2.655 -> 5.594 px), while an exact k=2 resolve moves it +2.6%
to +8.0% (research §4). So read this metric BESIDE
`edge_transition_width`: colours up with width flat is gradation added;
colours up with width doubled is a soft picture.

**Evidence for a human reader, never a gate.** an#41’s criterion counts
metrics independently and cannot express a conjunction, so neither half of
the pair may be declared as counting on the strength of the other.

`edge` must come from [`an.bench.masks.edge_mask()`](an.bench.masks.html.md#an.bench.masks.edge_mask) applied to
[`luma_u8()`](#an.bench.metrics.luma_u8) — **not** to [`luma709()`](#an.bench.metrics.luma709), which is float in [0,1]
against a threshold of 40 on 0-255 and yields an empty mask every time.

Returns `(mean, frames_measured)`. A frame whose mask is empty is
**skipped, not averaged in as zero** — a zero would drag the mean down and
read as exactly the regression this metric exists to notice. With no such
frame the answer is `nan`, which the caller records as `unavailable`;
[`an.bench.ledger.measured()`](an.bench.ledger.html.md#an.bench.ledger.measured) refuses it.

```pycon
>>> import numpy as np
>>> from an.bench.masks import edge_mask
>>> c = np.zeros((1, 4, 16, 3), np.uint8); c[0, :, 8:] = 255
>>> edge_masked_distinct_colours(pack_rgb(c), edge_mask(luma_u8(c)))
(2.0, 1)
```

A change entirely inside a flat field moves the whole-frame count and not
this one — this, and only this, is what the mask buys:

```pycon
>>> d = c.copy()
>>> for x in range(2, 6): d[0, :, x] = 8 * (x - 1)
...
>>> frame_distinct_colours(pack_rgb(d))
6.0
>>> edge_masked_distinct_colours(pack_rgb(d), edge_mask(luma_u8(d)))
(2.0, 1)
```

An empty mask is not a colour count of zero:

```pycon
>>> flat = np.full((1, 4, 8, 3), 128, np.uint8)
>>> edge_masked_distinct_colours(pack_rgb(flat), edge_mask(luma_u8(flat)))
(nan, 0)
```

* **Return type:**
  `tuple`[`float`, `int`]

### an.bench.metrics.edge_transition_width(rgb, , tol=4, trim=0.1)

Average thickness, in pixels, of the fuzzy band between two flat areas.

Under 1 is a jagged staircase; ~1 is clean AA; 3+ means the picture has
gone soft. **Two-sided**, which is the whole reason it replaced a palette
cardinality count: cardinality reads AA-off as 4, AA-on as 45 and a 3x3
blur as 416, so “the number went up” means “AA restored” and “the picture
went soft” indiscriminately.

Returns `(trimmed_mean, median)`.

* **Return type:**
  `tuple`[`float`, `float`]

```pycon
>>> import numpy as np
>>> a = np.zeros((1, 4, 8, 3), np.uint8); a[0, :, 4:] = 255
>>> round(edge_transition_width(a)[0], 3)   # one hard step = a 2px band
2.0
```

### an.bench.metrics.encode_flicker_on_held_pixels(src_rgb, dec_rgb, , tol=2)

Fraction of perfectly-held pixels that moved in the delivered video.

Held-pose “boiling” — the worst artefact for limited-motion animation.
Pooled over every frame pair rather than averaged per pair, so a pair with
three held pixels does not weigh as much as one with seventy thousand.

* **Return type:**
  `float`

```pycon
>>> import numpy as np
>>> s = np.zeros((2, 1, 4, 3), np.uint8)
>>> d = s.copy(); d[1, 0, 0] = 5
>>> encode_flicker_on_held_pixels(s, d)
0.25
```

### an.bench.metrics.encode_flicker_sweep(src_rgb, dec_rgb, , tols=(1, 2, 3, 4))

`encode_flicker_on_held_pixels`’ count at every `tol` of its sweep.

Same shape and same purpose as [`flat_field_deviation_sweep()`](#an.bench.metrics.flat_field_deviation_sweep): this is
the panel’s other hard-threshold counter, and measured under the same
4:2:0 -> 4:4:4 change its direction reverses between tol 2 and tol 3 on
`single_character` (+25% -> -15%), and under `high_crf` between tol 1
and tol 2 on `graded_field` (-9% -> +29%). Empty when nothing is held.

* **Return type:**
  `dict`[`str`, `list`[`int`]]

```pycon
>>> import numpy as np
>>> s = np.zeros((2, 1, 4, 3), np.uint8)
>>> d = s.copy(); d[1, 0, 0] = 2
>>> encode_flicker_sweep(s, d, tols=(2, 3))
{'tol=2': [1, 4], 'tol=3': [0, 4]}
```

### an.bench.metrics.encode_ringing_excess(dec_luma, lossless_luma, src_luma, ring)

How much more the lossy encode overshoots than a lossless one does.

Both legs share the source, so the source-spectrum term cancels: AA-off
raises both together (correctly reporting “the encoder did not get worse”),
a genuine crispness improvement also raises both (no false regression), and
a CRF change raises only the lossy leg.

**Provisional.** `edge_band_mae` is recorded beside it so research open
question 4 — “does plain edge-band MAE beat this?” — is answered by the
ledger rather than by nobody.

* **Return type:**
  `float`

```pycon
>>> import numpy as np
>>> s = np.zeros((1, 1, 2), np.uint8)
>>> encode_ringing_excess(np.array([[[9, 0]]], np.uint8),
...                       np.array([[[3, 0]]], np.uint8), s, np.ones((1, 1, 2), bool))
3.0
```

### an.bench.metrics.flat_field_deviation(src_rgb, dec_rgb, flat, , tol=6)

Fraction of flat-field pixels the encoder moved by more than `tol`.

The strongest metric in the set and the only one measured genuinely
orthogonal to the edge/AA axis: monotone over a 133x span on the CRF ladder
(0.0003 -> 0.0399, crf18 -> crf51) and flat under every AA variant.

Returns `(fraction_over_tol, p99_of_the_deviation)`.

* **Return type:**
  `tuple`[`float`, `float`]

```pycon
>>> import numpy as np
>>> s = np.zeros((1, 3, 3, 3), np.uint8)
>>> d = s.copy(); d[0, 1, 1] = 20
>>> flat_field_deviation(s, d, np.ones((1, 3, 3), bool))[0]
0.1111111111111111
```

### an.bench.metrics.flat_field_deviation_sweep(src_rgb, dec_rgb, , mask_rgb, tols=(4, 5, 6, 7, 8), ks=(1, 3, 5))

`flat_field_deviation`’s count at every `(dilate_k, tol)` of its sweep.

`{cell_key: [counted, of]}` — integers, so a comparison between two rows
is exact rather than a comparison of two rounded fractions. The positional
pair is `flat_field_deviation`’s own (reference, decoded); `mask_rgb`
— what the flat mask is derived from, the SOURCE frames in `run.py` — is
keyword-only so the two roles cannot be swapped positionally. A `k`
whose mask selects nothing is omitted, not recorded as `[0, 0]`.

It is not a new number for the panel. It is what lets `an bench-compare`
tell a verdict from a threshold accident (an#140): the shipped cell IS the
metric, and the others say whether anywhere else on the declared grid of
its own two parameters the direction reverses.

* **Return type:**
  `dict`[`str`, `list`[`int`]]

```pycon
>>> import numpy as np
>>> s = np.zeros((1, 9, 9, 3), np.uint8)
>>> d = s.copy(); d[0, 4, 4] = 7
>>> cells = flat_field_deviation_sweep(s, d, mask_rgb=s, tols=(6, 7), ks=(3,))
>>> cells
{'dilate_k=3,tol=6': [1, 81], 'dilate_k=3,tol=7': [0, 81]}
```

### an.bench.metrics.frame_distinct_colours(packed)

Mean number of distinct colours per frame.

A flatness / palette-discipline **guard**, with no predicted direction on
an AA change. Do not count it alongside `off_palette_pixel_fraction`; they
are the same family.

* **Return type:**
  `float`

```pycon
>>> import numpy as np
>>> frame_distinct_colours(np.array([[[1, 1, 2]], [[3, 4, 5]]], np.uint32))
2.5
```

### an.bench.metrics.golden_comparison(today_rgb, golden_rgb)

The full-frame identity gate plus its diagnostics.

Full-frame, not edge-masked: that is what makes the one sentence true, and
what catches the flat-interior regressions an edge mask is blind to — and
for this look the flat fields are most of the picture.

`changed_px` and `max_delta` belong in a failure message, not in the
metrics block; they are returned here so the caller can put them there.

* **Return type:**
  `dict`

```pycon
>>> import numpy as np
>>> a = np.zeros((4, 4, 3), np.uint8)
>>> golden_comparison(a, a)["identical"]
True
```

### an.bench.metrics.luma709(rgb)

`(H,W,3)` uint8 -> `(H,W)` float in [0,1]. PIL-free.

* **Return type:**
  `Any`

```pycon
>>> import numpy as np
>>> round(float(luma709(np.full((1, 1, 3), 255, np.uint8))[0, 0]), 6)
1.0
```

### an.bench.metrics.luma_u8(rgb)

`(...,3)` uint8 -> `(...)` uint8 luma, on the 0-255 scale a plane uses.

The one conversion between [`luma709()`](#an.bench.metrics.luma709), which returns \*\*float in
[0,1]\*\*, and [`an.bench.masks.edge_mask()`](an.bench.masks.html.md#an.bench.masks.edge_mask), whose threshold is \*\*40 on
0-255\*\*. Handing the float straight to the mask is not a wrong number, it is
an **empty mask**: every two-apart gradient is <= 1.0, so nothing is ever an
edge and the metric downstream reads `unavailable` on every scene. Written
once, named and tested here rather than open-coded at each call site,
because it cost a debugging round the first time (an#55).

**This is FULL-RANGE luma and the encode-side plane is not.**
[`an.bench.imageio.SOURCE_SCALE_FILTER`](an.bench.imageio.html.md#an.bench.imageio.SOURCE_SCALE_FILTER) pins `out_range=tv`, so
ffmpeg’s Y sits in [16,235] and its gradients are 219/255 of these. At one
threshold that makes the render-side mask the **wider** of the two —
measured: a 45-code-value step selects 4 pixels here and 0 there — which is
why the row records it under its own operator string rather than reusing
`an.bench.masks.EDGE_OPERATOR`.

* **Return type:**
  `Any`

```pycon
>>> import numpy as np
>>> a = np.zeros((1, 1, 2, 3), np.uint8); a[0, 0, 1] = 255
>>> luma_u8(a).tolist()
[[[0, 255]]]
```

### an.bench.metrics.masked_mean_abs(a, b, mask)

`|a - b|` averaged over `mask`, with the cast that makes it correct.

* **Return type:**
  `float`

```pycon
>>> import numpy as np
>>> x = np.array([[[10, 200]]], np.uint8); y = np.array([[[12, 190]]], np.uint8)
>>> masked_mean_abs(x, y, np.ones((1, 1, 2), bool))
6.0
```

### an.bench.metrics.off_palette_pixel_fraction(packed, palette)

Fraction of the frame whose colour is not one the compiler declared.

* **Return type:**
  `float`

```pycon
>>> import numpy as np
>>> p = np.array([[[0x000000, 0xffffff, 0x808080]]], np.uint32)
>>> round(off_palette_pixel_fraction(p, [0x000000, 0xffffff]), 4)
0.3333
```

### an.bench.metrics.off_palette_top_colours(packed, palette, , top=10)

The most frequent off-palette colours, as `[{"hex", "count"}]`.

Not decoration: this metric’s whole meaning is “not one of the colours the
compiler declared”, so a palette that under-collects turns it into a large
plausible number with no error anywhere. If the top entries are exact hex
literals from the staged art, the derivation missed them; if they are
blends sitting between two palette entries, that is anti-aliasing and the
number is right.

* **Return type:**
  `list`[`dict`]

```pycon
>>> import numpy as np
>>> p = np.array([[[1, 1, 2]]], np.uint32)
>>> off_palette_top_colours(p, [2], top=1)
[{'hex': '#000001', 'count': 2}]
```

### an.bench.metrics.overshoot_mean(dec_luma, src_luma, ring)

Mean positive excursion above the source, over the ring band.

* **Return type:**
  `float`

```pycon
>>> import numpy as np
>>> s = np.zeros((1, 1, 2), np.uint8); d = np.array([[[5, 0]]], np.uint8)
>>> overshoot_mean(d, s, np.ones((1, 1, 2), bool))
2.5
```

### an.bench.metrics.pack_rgb(rgb)

`(N,H,W,3)` uint8 -> `(N,H,W)` uint32, one integer per colour.

* **Return type:**
  `Any`

```pycon
>>> import numpy as np
>>> hex(int(pack_rgb(np.array([[[[0x12, 0x34, 0x56]]]], np.uint8))[0, 0, 0]))
'0x123456'
```

### an.bench.metrics.ssim_map(a, b, , r=3)

Windowed SSIM at stride 1, as a per-pixel map.

Added **beside** [`an.verify.media.ssim()`](an.verify.media.html.md#an.verify.media.ssim), never replacing it: that
function’s global-moment form is what
[`an.verify.media_quality`](an.verify.media_quality.html.md#module-an.verify.media_quality)’s frozen-render threshold was tuned
against, and `MediaQualityVerifier` sits in the default orchestrate chain.

Why it exists at all: the metrics survey concluded SSIM should be excluded
because whole-frame SSIM scores a total eye-blink at 0.9989. That
conclusion was **refuted** — only the *global-moment* reduction is blind.
With the window matched to feature size, min-over-windows scores the same
blink at 0.279 (1080p) and 0.063 (native).

Do not cross-check against ffmpeg’s `ssim` filter: it uses overlapped 8x8
block sums at 4-pixel stride, disagrees by up to 0.0201, and the
disagreement *grows* with degradation.

* **Return type:**
  `Any`

```pycon
>>> import numpy as np
>>> x = np.linspace(0, 1, 64).reshape(8, 8)
>>> round(float(ssim_map(x, x).min()), 6)
1.0
```

### an.bench.metrics.sweep_cell_key(\*\*params)

The label of one cell of a parameter sweep, stable across rows.

Keyword order is irrelevant — the key is sorted — so two rows written by
code that spells the call differently still match cell for cell.

* **Return type:**
  `str`

```pycon
>>> sweep_cell_key(tol=6, dilate_k=3)
'dilate_k=3,tol=6'
```
