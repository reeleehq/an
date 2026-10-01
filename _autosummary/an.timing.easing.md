# an.timing.easing

The easing registry: every named timing curve, each with the solver that computes it.

An **easing** (CSS: *timing function*; Manim: *rate function*) maps a segment’s
normalised time `u` in `[0, 1]` to its progress. One registry holds every
curve a timeline may name, and each entry carries its own **solver**, because two
solvers of “the same” curve do not agree to the contract tolerance (core study
§2.3): `an`’s cubic Bézier runs 8 Newton steps and stops, the CSS one runs Newton
and then bisects.

Four vocabularies live here, and none is silently aliased to another:

- **legacy** — `an`’s own names, with the polynomial curves `an` has always drawn
  (`ease`, `ease_in`, `ease_out`, `ease_in_out`, `step`). `ease` and
  `ease_in_out` are the quadratic ease-in-out, **not** CSS `ease`; the CSS
  `ease` curve is spelled `cubic-bezier(0.25, 0.1, 0.25, 1)`.
- **css** — CSS Easing Level 1/2 hyphenated names with the exact CSS curves
  (`ease-in`, `ease-out`, `ease-in-out`, `step-start`, `step-end`),
  plus the parametrised `cubic-bezier(x1, y1, x2, y2)` and
  `steps(n[, position])`.
- **manim** — Manim Community Edition’s rate functions under their own names
  (`smooth`, `there_and_back`, `rush_into`, …), so a curve means the same
  thing whether the stage engine or Manim draws it.
- **common** — `linear`, which every vocabulary agrees on.

A bare 4-sequence `[cx1, cy1, cx2, cy2]` (what `an` scenes have always written)
is a cubic Bézier solved by the **legacy** solver, so no existing scene moves.

```pycon
>>> apply_easing("linear", 0.5)
0.5
>>> apply_easing("ease_in_out", 0.25)  # an's quadratic, not CSS
0.125
>>> round(apply_easing("ease-in-out", 0.25), 6)  # the CSS curve
0.129162
>>> round(apply_easing("cubic-bezier(0.42, 0, 0.58, 1)", 0.25), 6)
0.129162
>>> apply_easing("steps(4)", 0.3)
0.25
>>> round(apply_easing("smooth", 0.25), 6)  # Manim's default rate function
0.070104
>>> round(apply_easing([0.42, 0.0, 0.58, 1.0], 0.25), 6)  # legacy solver
0.129162
```

### Module Attributes

| [`Curve`](#an.timing.easing.Curve)                      | normalised time `u` -> progress.                                                                                                                            |
|-----------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`CORE_OWNER`](#an.timing.easing.CORE_OWNER)                 | Who registered a core entry.                                                                                                                                |
| [`EASING_FAMILIES`](#an.timing.easing.EASING_FAMILIES)            | a genre adds its own (a Penner family, say) with [`register_family()`](#an.timing.easing.register_family).                                        |
| [`SOLVERS`](#an.timing.easing.SOLVERS)                    | The core solvers, by name.                                                                                                                                  |
| [`LEGACY_BEZIER_NEWTON_STEPS`](#an.timing.easing.LEGACY_BEZIER_NEWTON_STEPS) | Newton steps of the legacy Bézier solver, and its degenerate-slope guard.                                                                                   |
| [`CSS_BEZIERS`](#an.timing.easing.CSS_BEZIERS)                | The CSS named curves, as cubic-bezier control points (CSS Easing Level 1).                                                                                  |
| [`CSS_NEWTON_STEPS`](#an.timing.easing.CSS_NEWTON_STEPS)           | The CSS solver's constants (see `SOLVERS["css-bezier-newton-bisection"]`).                                                                                  |
| [`STEP_POSITIONS`](#an.timing.easing.STEP_POSITIONS)             | The positions `steps()` accepts; `start`/`end` are the CSS aliases of `jump-start`/`jump-end`.                                                              |
| [`MANIM_INFLECTION`](#an.timing.easing.MANIM_INFLECTION)           | Manim's default sigmoid steepness for `smooth` and its relatives.                                                                                           |
| [`VALUE_TYPED_EASINGS`](#an.timing.easing.VALUE_TYPED_EASINGS)        | exactly `runtime.js`'s `EASINGS` table (the stage engine draws these and no others), so the Python spec of that rule refuses what the browser would refuse. |

### Functions

| [`apply_easing`](#an.timing.easing.apply_easing)(spec, t, \*[, names])              | Apply an easing spec to a normalised parameter `t` in `[0, 1]`.              |
|--------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`css_cubic_bezier`](#an.timing.easing.css_cubic_bezier)(x1, y1, x2, y2)                | The CSS `cubic-bezier(x1, y1, x2, y2)` curve, solved to well below 1e-9.     |
| [`css_steps`](#an.timing.easing.css_steps)(n[, position])                        | CSS `steps(n, position)`, following the CSS Easing Level 1 algorithm.        |
| [`easing_entries`](#an.timing.easing.easing_entries)(\*[, owner])                     | Every registered entry in registration order; only `owner`'s when given.     |
| [`easing_entry`](#an.timing.easing.easing_entry)(name)                              | The registered entry called `name`.                                          |
| [`legacy_cubic_bezier`](#an.timing.easing.legacy_cubic_bezier)(cx1, cy1, cx2, cy2, t)      | an's cubic-Bézier easing at `t` — the `an-bezier-newton-8` solver.           |
| [`register_easing`](#an.timing.easing.register_easing)(entry, \*[, replace, owner])    | Add `entry` to the registry (a genre's own curves register here).            |
| [`register_family`](#an.timing.easing.register_family)(name, \*[, owner])              | Open a new easing family (refused if it exists).                             |
| [`register_solver`](#an.timing.easing.register_solver)(name, description, \*[, owner]) | Name a new solver, with the description another language implements it from. |
| [`resolve_easing`](#an.timing.easing.resolve_easing)(spec)                            | The curve an easing spec names.                                              |
| [`solvers`](#an.timing.easing.solvers)(\*[, owner])                            | The registered solvers; only `owner`'s when given.                           |

### Classes

| [`EasingEntry`](#an.timing.easing.EasingEntry)(name, curve, family, solver, ...)   | One named easing: its curve, where it comes from, and how it is solved.   |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|

### Exceptions

| [`UnknownEasingError`](#an.timing.easing.UnknownEasingError)   | An easing spec names no registered curve and parses as no parametrised one.   |
|-----------------------------------------------------------------------|-------------------------------------------------------------------------------|

### an.timing.easing.CORE_OWNER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an'*

Who registered a core entry. Registries record an owner for every entry, and
the contract files ([`an.timing.contract`](an.timing.contract.md#module-an.timing.contract)) list only this owner’s, so a
genre’s registrations never leak into `an`’s core contract.

### an.timing.easing.CSS_BEZIERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]]* *= {'ease': (0.25, 0.1, 0.25, 1.0), 'ease-in': (0.42, 0.0, 1.0, 1.0), 'ease-in-out': (0.42, 0.0, 0.58, 1.0), 'ease-out': (0.0, 0.0, 0.58, 1.0)}*

The CSS named curves, as cubic-bezier control points (CSS Easing Level 1).

### an.timing.easing.CSS_NEWTON_STEPS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 8*

The CSS solver’s constants (see `SOLVERS["css-bezier-newton-bisection"]`).

### an.timing.easing.Curve

normalised time `u` -> progress.

* **Type:**
  A curve

alias of `Callable`[[[`float`](https://docs.python.org/3/builtins/functions.html#float)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.timing.easing.EASING_FAMILIES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('common', 'legacy', 'css', 'manim')*

a genre adds its own
(a Penner family, say) with [`register_family()`](#an.timing.easing.register_family).

* **Type:**
  The core families (see the module docstring). Open

### *class* an.timing.easing.EasingEntry(name, curve, family, solver, description, version=1, params=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One named easing: its curve, where it comes from, and how it is solved.

`version` follows ADR 0003: an entry whose meaning changes gets a new
version, so a shot that names it re-renders visibly instead of silently.

#### to_json()

The entry as the contract file lists it (without samples).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.timing.easing.LEGACY_BEZIER_NEWTON_STEPS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 8*

Newton steps of the legacy Bézier solver, and its degenerate-slope guard.

### an.timing.easing.MANIM_INFLECTION *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 10.0*

Manim’s default sigmoid steepness for `smooth` and its relatives.

### an.timing.easing.SOLVERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'an-bezier-newton-8': "an's cubic Bézier: x(s) = t solved by exactly 8 Newton steps from s = t, each clamped to [0, 1], stopping only on a derivative below 1e-12; no bisection. Bit-identical to runtime.js cubicBezier", 'closed-form': 'evaluated directly from its formula', 'css-bezier-newton-bisection': 'the CSS cubic Bézier: up to 8 Newton steps from s = t (stop when |x(s) - t| < 1e-12, give up on a slope below 1e-6), then up to 60 bisection steps on [0, 1] to the same 1e-12', 'css-steps': 'the CSS Easing Level 1 step algorithm'}*

The core solvers, by name. An entry names the one that computes it, so a
curve’s numbers are reproducible in another language from its entry alone.
Open: a genre adds one (a spring integrator) with [`register_solver()`](#an.timing.easing.register_solver).

### an.timing.easing.STEP_POSITIONS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('jump-start', 'jump-end', 'jump-none', 'jump-both', 'start', 'end')*

The positions `steps()` accepts; `start`/`end` are the CSS aliases of
`jump-start`/`jump-end`.

### *exception* an.timing.easing.UnknownEasingError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

An easing spec names no registered curve and parses as no parametrised one.

### an.timing.easing.VALUE_TYPED_EASINGS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'ease', 'ease_in', 'ease_in_out', 'ease_out', 'linear', 'step'})*

exactly `runtime.js`’s
`EASINGS` table (the stage engine draws these and no others), so the Python
spec of that rule refuses what the browser would refuse.

* **Type:**
  The easings the value-typed rule accepts

### an.timing.easing.apply_easing(spec, t, , names=None)

Apply an easing spec to a normalised parameter `t` in `[0, 1]`.

`names` restricts the string specs accepted to that collection — what an
engine that implements only part of the registry passes (the stage runtime
implements the legacy names; see `an.adapters.cutout.easing`). Sequences
always take the legacy Bézier solver.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> apply_easing(None, 0.25)
0.25
>>> apply_easing("step", 0.99), apply_easing("step", 1.0)
(0.0, 1.0)
>>> apply_easing("smooth", 0.5, names={"linear"})
Traceback (most recent call last):
 ...
an.timing.easing.UnknownEasingError: unknown easing preset 'smooth'; known: ['linear']
```

### an.timing.easing.css_cubic_bezier(x1, y1, x2, y2)

The CSS `cubic-bezier(x1, y1, x2, y2)` curve, solved to well below 1e-9.

`x1` and `x2` must lie in `[0, 1]` (so the curve is a function of
time); `y` may overshoot.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`float`](https://docs.python.org/3/builtins/functions.html#float)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> css = css_cubic_bezier(0.42, 0.0, 0.58, 1.0)
>>> css(0.0), css(1.0), round(css(0.5), 12)
(0, 1, 0.5)
>>> css_cubic_bezier(1.5, 0, 0, 1)
Traceback (most recent call last):
 ...
ValueError: cubic-bezier x values must lie in [0, 1], got x1=1.5, x2=0
```

### an.timing.easing.css_steps(n, position='jump-end')

CSS `steps(n, position)`, following the CSS Easing Level 1 algorithm.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`float`](https://docs.python.org/3/builtins/functions.html#float)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> f = css_steps(4)
>>> [f(u) for u in (0.0, 0.24, 0.25, 0.99, 1.0)]
[0.0, 0.0, 0.25, 0.75, 1.0]
>>> css_steps(3, "jump-none")(0.5)
0.5
```

### an.timing.easing.easing_entries(, owner=None)

Every registered entry in registration order; only `owner`’s when given.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`EasingEntry`](#an.timing.easing.EasingEntry), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.timing.easing.easing_entry(name)

The registered entry called `name`.

* **Return type:**
  [`EasingEntry`](#an.timing.easing.EasingEntry)

```pycon
>>> easing_entry("ease").family
'legacy'
```

### an.timing.easing.legacy_cubic_bezier(cx1, cy1, cx2, cy2, t)

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

It does NOT agree with the CSS solver ([`css_cubic_bezier()`](#an.timing.easing.css_cubic_bezier)) to 1e-9
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

### an.timing.easing.register_easing(entry, , replace=False, owner=None)

Add `entry` to the registry (a genre’s own curves register here).

Re-registering a name is refused unless `replace=True`, and a replacement
must carry a HIGHER version: a name’s meaning changing under a scene that
uses it is exactly what entry versions exist to make visible, so it must be
deliberate and visible. `owner` names who registered it (core entries:
[`CORE_OWNER`](#an.timing.easing.CORE_OWNER)); only core entries reach the contract files.

* **Return type:**
  [`EasingEntry`](#an.timing.easing.EasingEntry)

### an.timing.easing.register_family(name, , owner=None)

Open a new easing family (refused if it exists).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.timing.easing.register_solver(name, description, , owner=None)

Name a new solver, with the description another language implements it from.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.timing.easing.resolve_easing(spec)

The curve an easing spec names.

- `None` -> linear;
- a registered name, `cubic-bezier(x1, y1, x2, y2)` or `steps(n[, position])`;
- a 4-sequence `[cx1, cy1, cx2, cy2]` -> the legacy Bézier solver.

Raises [`UnknownEasingError`](#an.timing.easing.UnknownEasingError) (a `ValueError`) for an unknown name or
a malformed sequence, `TypeError` for any other type.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`float`](https://docs.python.org/3/builtins/functions.html#float)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.timing.easing.solvers(, owner=None)

The registered solvers; only `owner`’s when given.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
