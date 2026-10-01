# an.adapters.cutout.easing

Easing functions for keyframe interpolation.

Two forms are supported (matching `an.base.EasingSpec`):

- A **named preset** string from `an.base.EASING_PRESETS`.
- A **cubic-Bézier control 4-tuple** `[cx1, cy1, cx2, cy2]` over the unit square.

`apply_easing(spec, t)` is the dispatcher; named presets are resolved via
`EASING_FUNCS`. Step easing returns 0 until t==1.

```pycon
>>> apply_easing("linear", 0.5)
0.5
>>> round(apply_easing("ease_in_out", 0.5), 6)
0.5
>>> round(apply_easing([0.0, 0.0, 1.0, 1.0], 0.5), 6)
0.5
```

### Functions

| [`apply_easing`](#an.adapters.cutout.easing.apply_easing)(spec, t)               | Apply an easing spec to a normalized parameter `t` ∈ [0, 1].       |
|--------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| [`cubic_bezier`](#an.adapters.cutout.easing.cubic_bezier)(cx1, cy1, cx2, cy2, t) | Evaluate a 1D cubic-Bézier easing curve at parameter `t` ∈ [0, 1]. |

### an.adapters.cutout.easing.apply_easing(spec, t)

Apply an easing spec to a normalized parameter `t` ∈ [0, 1].

Accepts:

- `None` → linear (passthrough)
- a string preset name (must be a key of `EASING_FUNCS`)
- a 4-element sequence of cubic-Bézier control points

Raises `ValueError` for unknown preset names or malformed sequences.

```pycon
>>> apply_easing(None, 0.25)
0.25
>>> apply_easing("step", 0.99)
0.0
>>> apply_easing("step", 1.0)
1.0
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.adapters.cutout.easing.cubic_bezier(cx1, cy1, cx2, cy2, t)

Evaluate a 1D cubic-Bézier easing curve at parameter `t` ∈ [0, 1].

The curve is defined by P0=(0,0), P1=(cx1,cy1), P2=(cx2,cy2), P3=(1,1).
Given a desired x=t we solve for the matching curve parameter u, then
return the y coordinate. Newton’s-method approximation; 8 iterations is
visually indistinguishable from analytic.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> round(cubic_bezier(0.0, 0.0, 1.0, 1.0, 0.5), 6)  # linear
0.5
>>> round(cubic_bezier(0.42, 0.0, 0.58, 1.0, 0.0), 6)  # endpoints exact
0.0
>>> round(cubic_bezier(0.42, 0.0, 0.58, 1.0, 1.0), 6)
1.0
```
