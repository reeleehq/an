# an.bench.stage

Measuring a pan: does the stage move as planes, or as one rigid image?

**The trap the epic’s own sentence sets.** “The planes moved at different
rates” is satisfied by a scene with *no parallax whatsoever*, because a
centre-anchored zoom already produces unequal per-plane displacements. The
honest null hypothesis is **“the camera moved the whole stage as one rigid
image”**, and a zoom has to be excluded rather than assumed away.

**The quantity.** Probe each plane at scene-space `x = 0` — the canvas
centre column. There the zoom term vanishes *exactly*:

> Δ_i = s₁ · p_i · D₁          ratio_ij = Δ_i / Δ_j = p_i / p_j   (any zoom)

Under a rigid pan every ratio is exactly 1, so the measurement can tell a
parallaxing stage from a zooming one. Two additions the epic does not require:

- assert `Δy ≈ 0`, so a pan is distinguishable from a zoom — but only for a
  ZOOM-FREE pan: §4 endorses zoom composing through the pivot, and a pan+zoom
  shot measures a non-zero Δy by design;
- assert the ORDERING `p_far < p_mid < p_near`, because wrong-order parallax
  is a real bug that a bare inequality passes. It is a \*\*bonus, not a second
  gate\*\*: the zoom false positive satisfies the ordering too. Only the x = 0
  probe excludes a zoom.

Two measurements, deliberately different instruments:

**(a) JSON** — free, on every PR, from the compiled document through
[`an.adapters.cutout.timeline.screen_position()`](an.adapters.cutout.timeline.md#an.adapters.cutout.timeline.screen_position). Composed screen space,
not local channel values: a rigid pan on `root` leaves every plane’s local
`Δx` at zero.

**(b) Pixels** — on a labelled PR, per-plane centroids over exact-colour
masks. The `x = 0` cancellation does **not** reach (b): a centroid sits at
the plane’s own offset, not at `x = 0`, so the fixture holds zoom constant.
And each mask’s pixel COUNT is asserted unchanged between frames, because a
plane panning partly off-canvas biases its centroid — measured, that read a
`depth = 2` plane as 1.975.

### Functions

| [`measure_pan_json`](#an.bench.stage.measure_pan_json)(scene, plane_paths, times, \*)   | Measurement (a): composed screen displacement, probed at `x = 0`.    |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`plane_centroids`](#an.bench.stage.plane_centroids)(frame, colours)                   | `{plane: (cx, cy, pixel count)}` for exact-colour masks.             |
| [`measure_pan_pixels`](#an.bench.stage.measure_pan_pixels)(frames, colours, \*[, depths]) | Measurement (b): per-plane centroid displacement between two frames. |
| [`min_ratio_gap`](#an.bench.stage.min_ratio_gap)(ratios)                             | The smallest gap between any two planes' ratios.                     |

### Classes

| [`PlaneTrack`](#an.bench.stage.PlaneTrack)(name, dx, dy[, depth])   | One plane's displacement between the two probed times.   |
|--------------------------------------------------------------------------------------|----------------------------------------------------------|
| [`PanMeasurement`](#an.bench.stage.PanMeasurement)(tracks, reference)   | What a pan did, plane by plane.                          |

### Exceptions

| [`RotatingCamera`](#an.bench.stage.RotatingCamera)   | The camera rolls, so a per-axis ratio is not a depth ratio.   |
|-------------------------------------------------------------------|---------------------------------------------------------------|

### *class* an.bench.stage.PanMeasurement(tracks, reference)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a pan did, plane by plane.

#### *property* is_rigid *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

True when every plane moved by the same amount — the null
hypothesis, and what a stage with no parallax looks like.

Computed from the DISPLACEMENTS, not from the ratios, because a stage
that did not move at all has no ratios (the reference is zero, so every
ratio is NaN) and is nonetheless as rigid as a stage can be. Reading it
off the ratios made a pure zoom — which cancels to zero displacement at
the probe column, exactly as intended — report as parallaxing.

```pycon
>>> PanMeasurement((PlaneTrack("a", 10.0, 0.0), PlaneTrack("b", 10.0, 0.0)), "b").is_rigid
True
>>> PanMeasurement((PlaneTrack("a", 0.0, 0.0), PlaneTrack("b", 0.0, 0.0)), "b").is_rigid
True
>>> PanMeasurement((PlaneTrack("a", 5.0, 0.0), PlaneTrack("b", 10.0, 0.0)), "b").is_rigid
False
```

#### *property* ratios *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float)]*

`{plane: Δ_i / Δ_ref}`. A rigid stage gives 1.0 for every plane.

```pycon
>>> m = PanMeasurement((PlaneTrack("a", 10.0, 0.0), PlaneTrack("b", 40.0, 0.0)), "b")
>>> m.ratios
{'a': 0.25, 'b': 1.0}
```

#### reference *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

always the largest mover, so
the JSON and pixel halves agree and the number does not depend on what
a descriptor declares (`_reference()`).

* **Type:**
  The plane every ratio is taken against

### *class* an.bench.stage.PlaneTrack(name, dx, dy, depth=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One plane’s displacement between the two probed times.

#### depth *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The declared parallax factor, when the caller knows it.

### *exception* an.bench.stage.RotatingCamera

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The camera rolls, so a per-axis ratio is not a depth ratio.

Under a rotation the composed x-displacement is `−fx·A + fy·B` with
plane-independent `A`/`B`, so the axes mix and `Δ_i/Δ_j` stops being
`f_i/f_j`. Measured with `rotation = 0.6` and per-axis factors: one plane
reported a NEGATIVE ratio and the resulting gap was *larger* than the
honest one, so the tripwire passed on a number that meant nothing
(an#111 review, M2).

Refused rather than reported. The measurement’s whole job is to exclude a
camera move that mimics depth; silently reporting one is the failure it
exists to prevent, pointed the other way.

### an.bench.stage.measure_pan_json(scene, plane_paths, times, , depths=None)

Measurement (a): composed screen displacement, probed at `x = 0`.

`plane_paths` are full node paths (`"depths/far"`); the returned
tracks are keyed by the LAST segment, which is the plane’s own name.

* **Return type:**
  [`PanMeasurement`](#an.bench.stage.PanMeasurement)

### an.bench.stage.measure_pan_pixels(frames, colours, , depths=None)

Measurement (b): per-plane centroid displacement between two frames.

* **Return type:**
  [`PanMeasurement`](#an.bench.stage.PanMeasurement)

### an.bench.stage.min_ratio_gap(ratios)

The smallest gap between any two planes’ ratios.

This is the number the ledger row reports and the tripwire guards. Zero
means two planes moved together, which on a stage that declares distinct
depths means the parallax flattened.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> min_ratio_gap({"far": 0.25, "mid": 1.0, "near": 2.0})
0.75
>>> min_ratio_gap({"far": 1.0, "mid": 1.0})
0.0
```

### an.bench.stage.plane_centroids(frame, colours)

`{plane: (cx, cy, pixel count)}` for exact-colour masks.

`an/bench/masks.py` is deliberately not reused: it has no colour
selection. The primitive is `metrics.pack_rgb` plus equality — one integer
per colour, compared exactly, so a plane’s mask cannot pick up an
anti-aliased edge pixel from its neighbour.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`int`](https://docs.python.org/3/builtins/functions.html#int)]]
