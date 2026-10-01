# an.expression.binding

How the axes reach a character: the binding and the mouth-set resolver (an#98).

Renderer-free, like [`an.characters.play`](an.characters.play.html.md#module-an.characters.play) — `an validate`,
`an character validate` and the cutout face solver all call the same
functions here, so the three cannot disagree about whether an expression can
resolve on a character.

- A **channel binding** maps a numeric axis onto `(slot, property, gain)`:
  the solver emits `rest + Σ axis·gain` on that slot’s node. The brow angle’s
  per-side sign lives in the gain — the two sides rotate in opposite screen
  directions for one axis sign.
- A **set binding** maps a lid axis onto a slot’s swap set (`eyelid`); the
  solver reads a key off the ladder in [`an.expression.axes`](an.expression.axes.html.md#module-an.expression.axes).
- `resolve_mouth_set` is the ONE chain for “which mouth set does this line
  use”: `viseme@<form>` if declared **and** it covers the keys the line
  uses, else `viseme` with a warning naming the missing keys, else an
  [`ExpressionResolutionError`](#an.expression.binding.ExpressionResolutionError) (a speaking overlay face with no neutral
  > mouth set).

```pycon
>>> from an.characters.schema import CharacterDescriptor
>>> desc = CharacterDescriptor(name="m")
>>> sorted({b.axis for b in default_binding(desc)})
['brow_angle_l', 'brow_angle_r', 'brow_height_l', 'brow_height_r', 'lid_open_l', 'lid_open_r']
>>> resolve_mouth_set(desc, None, keys_used=["A", "X"])
'viseme'
>>> import warnings
>>> with warnings.catch_warnings(record=True) as w:
...     warnings.simplefilter("always")
...     resolve_mouth_set(desc, "happy", keys_used=["A", "X"])
'viseme'
>>> "viseme@happy" in str(w[0].message)
True
```

### Module Attributes

| [`BROW_HEIGHT_TRAVEL`](#an.expression.binding.BROW_HEIGHT_TRAVEL)   | Brow travel per unit of `brow_height_*`, in the rig's view-box units (scaled to scene pixels by the entity's rig factor).                             |
|-----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`BROW_ANGLE_TRAVEL`](#an.expression.binding.BROW_ANGLE_TRAVEL)    | Brow rotation per unit of `brow_angle_*`, radians.                                                                                                    |
| [`GAZE_TRAVEL`](#an.expression.binding.GAZE_TRAVEL)          | Pupil travel per unit of `gaze_*`, in view-box units — the default when a descriptor declares no travel of its own (`add_gaze` writes `gaze_travel`). |
| [`LID_SQUASH_GAIN`](#an.expression.binding.LID_SQUASH_GAIN)      | On a rig whose eye squashes instead of swapping art, a lid offset scales the eye by this much per unit.                                               |

### Functions

| [`binding_for`](#an.expression.binding.binding_for)(desc)                              | The descriptor's declared `expression_binding` (additive field), else the default.                                               |
|-------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| [`declared_mouth_variants`](#an.expression.binding.declared_mouth_variants)(desc)                  | `{form: set name}` for every `viseme@<form>` set the descriptor declares.                                                        |
| [`default_binding`](#an.expression.binding.default_binding)(desc)                          | The binding the default rig implies, from the slots it actually has.                                                             |
| [`expression_problems`](#an.expression.binding.expression_problems)(desc, \*, preset[, axes])  | Every reason an expression cannot resolve on `desc` — empty means it can.                                                        |
| [`preset_axes`](#an.expression.binding.preset_axes)(preset, \*[, axes, intensity])     | The numeric axis offsets an expression asks for: the preset's, with `axes` layered over them, scaled by `intensity` and clamped. |
| [`resolve_mouth_set`](#an.expression.binding.resolve_mouth_set)(desc, preset, \*, keys_used) | Which mouth set a line under `preset` uses — the one chain, shared.                                                              |
| [`touches_gaze`](#an.expression.binding.touches_gaze)(axes)                             | Whether any of `axes` is a gaze axis (a no-op on a rig without pupils).                                                          |
| [`variant_set_name`](#an.expression.binding.variant_set_name)(form)                         | The swap-set name for a mouth form (`@` is a legal set-name character).                                                          |

### Classes

| [`ChannelBinding`](#an.expression.binding.ChannelBinding)(axis, slot, property, gain[, ...])   | A numeric axis driving one transform property of one slot's node.   |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`SetBinding`](#an.expression.binding.SetBinding)(axis, slot[, set_family])                | A lid axis driving one slot's swap set through the ladder.          |

### Exceptions

| [`ExpressionResolutionError`](#an.expression.binding.ExpressionResolutionError)(who, problems)   | An expression that cannot resolve on a character; `problems` says why.   |
|---------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|

### an.expression.binding.BROW_ANGLE_TRAVEL *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.35*

Brow rotation per unit of `brow_angle_*`, radians. Art direction.

### an.expression.binding.BROW_HEIGHT_TRAVEL *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 10.0*

Brow travel per unit of `brow_height_*`, in the rig’s view-box units
(scaled to scene pixels by the entity’s rig factor). Art direction; about
the synthesized eye’s half-height.

### *class* an.expression.binding.ChannelBinding(axis, slot, property, gain, rig_scaled=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A numeric axis driving one transform property of one slot’s node.

#### rig_scaled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

Whether the gain is a view-box length (scaled by the rig factor).

### *exception* an.expression.binding.ExpressionResolutionError(who, problems)

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

An expression that cannot resolve on a character; `problems` says why.

### an.expression.binding.GAZE_TRAVEL *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 6.0*

Pupil travel per unit of `gaze_*`, in view-box units — the default when a
descriptor declares no travel of its own (`add_gaze` writes `gaze_travel`).

### an.expression.binding.LID_SQUASH_GAIN *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

On a rig whose eye squashes instead of swapping art, a lid offset scales
the eye by this much per unit.

### *class* an.expression.binding.SetBinding(axis, slot, set_family='eyelid')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A lid axis driving one slot’s swap set through the ladder.

### an.expression.binding.binding_for(desc)

The descriptor’s declared `expression_binding` (additive field), else the default.

A declared binding is a list of dicts in the two dataclasses’ shapes
(`{"axis", "slot", "property", "gain"[, "rig_scaled"]}` or
`{"axis", "slot", "set_family"}`). An unknown axis in it is an error.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[`Union`[[`ChannelBinding`](#an.expression.binding.ChannelBinding), [`SetBinding`](#an.expression.binding.SetBinding)]]

### an.expression.binding.declared_mouth_variants(desc)

`{form: set name}` for every `viseme@<form>` set the descriptor declares.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> declared_mouth_variants(CharacterDescriptor(name="m"))
{}
```

### an.expression.binding.default_binding(desc)

The binding the default rig implies, from the slots it actually has.

The brow angle’s screen sign: PixiJS rotation is clockwise-positive with y
down, so on the LEFT brow (screen-left) a clockwise turn drops the inner
end while on the RIGHT brow it lifts it — the axis says “+ = inner end
up”, hence `-travel` on the left and `+travel` on the right.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[`Union`[[`ChannelBinding`](#an.expression.binding.ChannelBinding), [`SetBinding`](#an.expression.binding.SetBinding)]]

### an.expression.binding.expression_problems(desc, , preset, axes=(), who)

Every reason an expression cannot resolve on `desc` — empty means it can.

Shared by `an validate` (each becomes an error Finding) and the compiler
(which raises [`ExpressionResolutionError`](#an.expression.binding.ExpressionResolutionError) with the same list).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> expression_problems(CharacterDescriptor(name="m"), preset="joyful", who="m")
["unknown expression preset 'joyful' (known: neutral, happy, sad, angry, surprised, afraid, disgusted, thinking, skeptical, amused)"]
>>> expression_problems(CharacterDescriptor(name="m", face_overlay=False), preset="happy", who="m")[0].startswith("'m' has its face baked")
True
```

### an.expression.binding.preset_axes(preset, , axes=None, intensity=1.0)

The numeric axis offsets an expression asks for: the preset’s, with
`axes` layered over them, scaled by `intensity` and clamped. Only
non-zero offsets are returned, so a neutral expression is `{}`.

An unknown preset or axis is a `ValueError` — validate reports it as an
error, the compiler refuses it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.expression.binding.resolve_mouth_set(desc, preset, , keys_used, who=None)

Which mouth set a line under `preset` uses — the one chain, shared.

`viseme@<form>` if the preset prefers a form the descriptor declares and
that set covers `keys_used`; else `viseme` with a warning naming what
was missing; else [`ExpressionResolutionError`](#an.expression.binding.ExpressionResolutionError). A descriptor with no
`viseme` set and no covering variant cannot speak at all — that is the
error, not a fallback.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.expression.binding.touches_gaze(axes)

Whether any of `axes` is a gaze axis (a no-op on a rig without pupils).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> touches_gaze(["gaze_x"]), touches_gaze(["brow_angle_l"])
(True, False)
```

### an.expression.binding.variant_set_name(form)

The swap-set name for a mouth form (`@` is a legal set-name character).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> variant_set_name("happy")
'viseme@happy'
```
