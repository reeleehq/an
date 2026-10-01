# an.stage.easing

The stage engine’s easing vocabulary — a view of [`an.timing.easing`](an.timing.easing.md#module-an.timing.easing).

The curves, their solvers and the full registry live in the timing kernel
([`an.timing.easing`](an.timing.easing.md#module-an.timing.easing)). This module keeps the path every stage caller already
imports, and it states what the STAGE implements: `runtime.js` evaluates the
legacy names in [`an.base.EASING_PRESETS`](an.base.md#an.base.EASING_PRESETS) and a cubic-Bézier control
4-tuple, nothing else, so [`apply_easing()`](#an.stage.easing.apply_easing) here refuses any other name. That
refusal is what `an validate` and the compiler use to say “the evaluators know
this easing” — a curve the kernel knows but the stage runtime does not would
otherwise surface as a throw in the browser.

```pycon
>>> apply_easing("linear", 0.5)
0.5
>>> round(apply_easing("ease_in_out", 0.5), 6)
0.5
>>> round(apply_easing([0.0, 0.0, 1.0, 1.0], 0.5), 6)
0.5
>>> apply_easing("ease-in", 0.5)
Traceback (most recent call last):
 ...
an.timing.easing.UnknownEasingError: unknown easing preset 'ease-in'; known: ['ease', 'ease_in', 'ease_in_out', 'ease_out', 'linear', 'step']
```

### Module Attributes

| [`EASING_FUNCS`](#an.stage.easing.EASING_FUNCS)   | The easings the stage runtime implements (`runtime.js` `EASINGS`), each the kernel registry's own curve.   |
|-----------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|

### Functions

| [`apply_easing`](#an.stage.easing.apply_easing)(spec, t)               | Apply an easing the STAGE implements to `t` in `[0, 1]`.           |
|--------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| [`cubic_bezier`](#an.stage.easing.cubic_bezier)(cx1, cy1, cx2, cy2, t) | an's cubic-Bézier easing at `t` — the `an-bezier-newton-8` solver. |

### an.stage.easing.EASING_FUNCS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[[[float](https://docs.python.org/3/builtins/functions.html#float)], [float](https://docs.python.org/3/builtins/functions.html#float)]]* *= {'ease': <function \_ease>, 'ease_in': <function \_ease_in>, 'ease_in_out': <function \_ease_in_out>, 'ease_out': <function \_ease_out>, 'linear': <function \_linear>, 'step': <function \_step>}*

The easings the stage runtime implements (`runtime.js` `EASINGS`), each
the kernel registry’s own curve.

### an.stage.easing.apply_easing(spec, t)

Apply an easing the STAGE implements to `t` in `[0, 1]`.

- `None` → linear (passthrough)
- a string preset name (must be a key of `EASING_FUNCS`)
- a 4-element sequence of cubic-Bézier control points (the legacy solver)

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

### an.stage.easing.cubic_bezier(cx1, cy1, cx2, cy2, t)

an’s cubic-Bézier easing at `t` — the `an-bezier-newton-8` solver.

The curve is defined by P0=(0,0), P1=(cx1,cy1), P2=(cx2,cy2), P3=(1,1).
Given a desired x=t we solve for the matching curve parameter u, then
return the y coordinate, by exactly 8 clamped Newton steps.

Structurally IDENTICAL to runtime.js::cubicBezier on purpose: always 8
iterations, break only on a degenerate derivative, clamp each step. This
function is the spec of that port, and the two are compared bit-for-bit by
the parity battery — an earlier version had an extra 

```
|u_new - u|
```

 < 1e-9
early-convergence break the JS side lacked, which left the two a ULP apart;
a numeric channel lerping large magnitudes amplifies a ULP of easing by
(b - a) (found by the an#86 adversarial review; the loops now match).

It does NOT agree with the CSS solver (`css_cubic_bezier()`) to 1e-9
for every control point, which is why it stays a named legacy solver until
the pixel goldens are re-blessed under the stricter one.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> round(legacy_cubic_bezier(0.0, 0.0, 1.0, 1.0, 0.5), 6)  # linear
0.5
>>> legacy_cubic_bezier(0.42, 0.0, 0.58, 1.0, 0.0), legacy_cubic_bezier(0.42, 0.0, 0.58, 1.0, 1.0)
(0.0, 1.0)
```
