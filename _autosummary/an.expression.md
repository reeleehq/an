# an.expression

Facial expression for the cutout face (an#98, epic #9 Wave 6).

The vocabulary ([`axes`](an.expression.axes.md#module-an.expression.axes)), our presets
([`presets`](an.expression.presets.md#module-an.expression.presets)), how they reach a character’s slots and which
mouth set a line uses ([`binding`](an.expression.binding.md#module-an.expression.binding)), the provider seam that
turns authored leaves and dialogue sugar into per-frame curves
([`provider`](an.expression.provider.md#module-an.expression.provider)), and the 52-coefficient import/export
mapping ([`blendshapes`](an.expression.blendshapes.md#module-an.expression.blendshapes)). Renderer-free throughout: the
cutout compiler’s face solver consumes these; `an validate` and
`an character validate` share the same resolution.

### Functions

| [`binding_for`](#an.expression.binding_for)(desc)                              | The descriptor's declared `expression_binding` (additive field), else the default.                                               |
|-------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| [`clamp_axes`](#an.expression.clamp_axes)(values)                             | Clamp every numeric axis to its range; an unknown axis is an error.                                                              |
| [`declared_mouth_variants`](#an.expression.declared_mouth_variants)(desc)                  | `{form: set name}` for every `viseme@<form>` set the descriptor declares.                                                        |
| [`default_binding`](#an.expression.default_binding)(desc)                          | The binding the default rig implies, from the slots it actually has.                                                             |
| [`expression_problems`](#an.expression.expression_problems)(desc, \*, preset[, axes])  | Every reason an expression cannot resolve on `desc` — empty means it can.                                                        |
| [`expression_spans`](#an.expression.expression_spans)(shot, entity_id)              | Every expression contributor on `entity_id`: authored leaves, then dialogue sugar.                                               |
| [`from_blendshapes`](#an.expression.from_blendshapes)(coefficients)                 | Fold unipolar coefficients onto the axes (summed, then clamped).                                                                 |
| [`known_presets`](#an.expression.known_presets)()                                | The preset names, in declaration order.                                                                                          |
| [`lid_key`](#an.expression.lid_key)(value, \*, available)                  | The eyelid key a lid state selects, degraded to the art the rig declares.                                                        |
| [`mouth_form_of`](#an.expression.mouth_form_of)(preset)                          | The `viseme@<form>` a preset prefers, or `None` for the neutral set.                                                             |
| [`preset_axes`](#an.expression.preset_axes)(preset, \*[, axes, intensity])     | The numeric axis offsets an expression asks for: the preset's, with `axes` layered over them, scaled by `intensity` and clamped. |
| [`resolve_mouth_set`](#an.expression.resolve_mouth_set)(desc, preset, \*, keys_used) | Which mouth set a line under `preset` uses — the one chain, shared.                                                              |
| [`variant_set_name`](#an.expression.variant_set_name)(form)                         | The swap-set name for a mouth form (`@` is a legal set-name character).                                                          |

### Classes

| [`Axis`](#an.expression.Axis)(name, lo, hi[, rest])                        | One numeric axis: its range and its rest (neutral) value.                          |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`AxisCurve`](#an.expression.AxisCurve)(axis, samples)                          | One axis sampled at the frame times `0, 1/fps, …, n/fps` (offline, deterministic). |
| [`ChannelBinding`](#an.expression.ChannelBinding)(axis, slot, property, gain[, ...]) | A numeric axis driving one transform property of one slot's node.                  |
| [`DefaultExpressionProvider`](#an.expression.DefaultExpressionProvider)()                       | Sum of the shot's expression spans on the entity, ramped, per frame.               |
| [`ExpressionProvider`](#an.expression.ExpressionProvider)(\*args, \*\*kwargs)            | The seam: whatever produces per-axis curves for one entity of one shot.            |
| [`ExpressionSpan`](#an.expression.ExpressionSpan)(start, end, preset[, axes, ...])   | One expression contributor on one entity, in absolute shot time.                   |
| [`Preset`](#an.expression.Preset)(name[, axes, mouth_form, anchor])          | A named expression: axis offsets, the mouth form it prefers, its anchor.           |
| [`SetBinding`](#an.expression.SetBinding)(axis, slot[, set_family])              | A lid axis driving one slot's swap set through the ladder.                         |

### Exceptions

| [`ExpressionResolutionError`](#an.expression.ExpressionResolutionError)(who, problems)   | An expression that cannot resolve on a character; `problems` says why.   |
|---------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|

### *class* an.expression.Axis(name, lo, hi, rest=0.0)

Bases: `object`

One numeric axis: its range and its rest (neutral) value.

### *class* an.expression.AxisCurve(axis, samples)

Bases: `object`

One axis sampled at the frame times `0, 1/fps, …, n/fps` (offline, deterministic).

### *class* an.expression.ChannelBinding(axis, slot, property, gain, rig_scaled=False)

Bases: `object`

A numeric axis driving one transform property of one slot’s node.

#### rig_scaled *: bool* *= False*

Whether the gain is a view-box length (scaled by the rig factor).

### *class* an.expression.DefaultExpressionProvider

Bases: `object`

Sum of the shot’s expression spans on the entity, ramped, per frame.

#### mouth_preset_at(shot, entity_id, t)

The preset whose mouth form is in force at `t`: the heaviest span
at `t` that prefers a form, or `None` (the neutral set).

Whole-line by construction when called at a line’s start — the solver
asks once per line, never per frame, so at most one mouth swap
property is live per instant.

* **Return type:**
  `str` | `None`

### *class* an.expression.ExpressionProvider(\*args, \*\*kwargs)

Bases: `Protocol`

The seam: whatever produces per-axis curves for one entity of one shot.

### *exception* an.expression.ExpressionResolutionError(who, problems)

Bases: `ValueError`

An expression that cannot resolve on a character; `problems` says why.

### *class* an.expression.ExpressionSpan(start, end, preset, axes=<factory>, intensity=1.0, blend=0.0, source='action')

Bases: `object`

One expression contributor on one entity, in absolute shot time.

#### offsets()

The unscaled axis offsets this span asks for.

* **Return type:**
  `dict`[`str`, `float`]

#### source *: str* *= 'action'*

`"action"` for an authored leaf, `"dialogue"` for the `[emotion]` sugar.

#### weight_at(t)

The ramped intensity at `t`: 0 outside, ramping over `blend` at each end.

* **Return type:**
  `float`

### *class* an.expression.Preset(name, axes=<factory>, mouth_form=None, anchor='')

Bases: `object`

A named expression: axis offsets, the mouth form it prefers, its anchor.

#### anchor *: str* *= ''*

FACS AU cross-reference (a comment, never a source).

#### mouth_form *: str | None* *= None*

The `viseme@<form>` set this preset’s mouth prefers; `None` = `viseme`.

### *class* an.expression.SetBinding(axis, slot, set_family='eyelid')

Bases: `object`

A lid axis driving one slot’s swap set through the ladder.

### an.expression.binding_for(desc)

The descriptor’s declared `expression_binding` (additive field), else the default.

A declared binding is a list of dicts in the two dataclasses’ shapes
(`{"axis", "slot", "property", "gain"[, "rig_scaled"]}` or
`{"axis", "slot", "set_family"}`). An unknown axis in it is an error.

* **Return type:**
  `list`[`Union`[[`ChannelBinding`](an.expression.binding.md#an.expression.binding.ChannelBinding), [`SetBinding`](an.expression.binding.md#an.expression.binding.SetBinding)]]

### an.expression.clamp_axes(values)

Clamp every numeric axis to its range; an unknown axis is an error.

* **Return type:**
  `dict`[`str`, `float`]

```pycon
>>> clamp_axes({"brow_height_l": 2.0, "lid_open_r": -3.0})
{'brow_height_l': 1.0, 'lid_open_r': -1.0}
>>> clamp_axes({"eyebrow": 1.0})
Traceback (most recent call last):
...
ValueError: unknown expression axis 'eyebrow' (known: brow_angle_l, ...)
```

### an.expression.declared_mouth_variants(desc)

`{form: set name}` for every `viseme@<form>` set the descriptor declares.

* **Return type:**
  `dict`[`str`, `str`]

```pycon
>>> declared_mouth_variants(CharacterDescriptor(name="m"))
{}
```

### an.expression.default_binding(desc)

The binding the default rig implies, from the slots it actually has.

The brow angle’s screen sign: PixiJS rotation is clockwise-positive with y
down, so on the LEFT brow (screen-left) a clockwise turn drops the inner
end while on the RIGHT brow it lifts it — the axis says “+ = inner end
up”, hence `-travel` on the left and `+travel` on the right.

* **Return type:**
  `list`[`Union`[[`ChannelBinding`](an.expression.binding.md#an.expression.binding.ChannelBinding), [`SetBinding`](an.expression.binding.md#an.expression.binding.SetBinding)]]

### an.expression.expression_problems(desc, , preset, axes=(), who)

Every reason an expression cannot resolve on `desc` — empty means it can.

Shared by `an validate` (each becomes an error Finding) and the compiler
(which raises [`ExpressionResolutionError`](#an.expression.ExpressionResolutionError) with the same list).

* **Return type:**
  `list`[`str`]

```pycon
>>> expression_problems(CharacterDescriptor(name="m"), preset="joyful", who="m")
["unknown expression preset 'joyful' (known: neutral, happy, sad, angry, surprised, afraid, disgusted, thinking, skeptical, amused)"]
>>> expression_problems(CharacterDescriptor(name="m", face_overlay=False), preset="happy", who="m")[0].startswith("'m' has its face baked")
True
```

### an.expression.expression_spans(shot, entity_id)

Every expression contributor on `entity_id`: authored leaves, then
dialogue sugar. `duration=None` runs to the shot end (the looping-play
rule); a span never extends past the shot.

* **Return type:**
  `list`[[`ExpressionSpan`](an.expression.provider.md#an.expression.provider.ExpressionSpan)]

### an.expression.from_blendshapes(coefficients)

Fold unipolar coefficients onto the axes (summed, then clamped).

Unknown names raise — a misspelt coefficient must not vanish quietly.

* **Return type:**
  `dict`[`str`, `float`]

### an.expression.known_presets()

The preset names, in declaration order.

* **Return type:**
  `tuple`[`str`, `...`]

```pycon
>>> known_presets()[:3]
('neutral', 'happy', 'sad')
```

### an.expression.lid_key(value, , available)

The eyelid key a lid state selects, degraded to the art the rig declares.

`wide` above +0.25, `open`, `half` below −0.35, `closed` below −0.85;
a rig without `half` stays open until the lower threshold and one without
`wide` stays open above the upper one — never a blend of two drawings.

* **Return type:**
  `str`

### an.expression.mouth_form_of(preset)

The `viseme@<form>` a preset prefers, or `None` for the neutral set.

* **Return type:**
  `str` | `None`

```pycon
>>> mouth_form_of("amused"), mouth_form_of("thinking"), mouth_form_of(None)
('happy', None, None)
```

### an.expression.preset_axes(preset, , axes=None, intensity=1.0)

The numeric axis offsets an expression asks for: the preset’s, with
`axes` layered over them, scaled by `intensity` and clamped. Only
non-zero offsets are returned, so a neutral expression is `{}`.

An unknown preset or axis is a `ValueError` — validate reports it as an
error, the compiler refuses it.

* **Return type:**
  `dict`[`str`, `float`]

### an.expression.resolve_mouth_set(desc, preset, , keys_used, who=None)

Which mouth set a line under `preset` uses — the one chain, shared.

`viseme@<form>` if the preset prefers a form the descriptor declares and
that set covers `keys_used`; else `viseme` with a warning naming what
was missing; else [`ExpressionResolutionError`](#an.expression.ExpressionResolutionError). A descriptor with no
`viseme` set and no covering variant cannot speak at all — that is the
error, not a fallback.

* **Return type:**
  `str`

### an.expression.variant_set_name(form)

The swap-set name for a mouth form (`@` is a legal set-name character).

* **Return type:**
  `str`

```pycon
>>> variant_set_name("happy")
'viseme@happy'
```

### Modules

| [`axes`](an.expression.axes.md#module-an.expression.axes)               | The facial expression axes: what a cutout face can be asked to do (an#98).           |
|-----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`binding`](an.expression.binding.md#module-an.expression.binding)         | How the axes reach a character: the binding and the mouth-set resolver (an#98).      |
| [`blendshapes`](an.expression.blendshapes.md#module-an.expression.blendshapes) | The 52-coefficient blendshape vocabulary, as an import/export mapping (an#98).       |
| [`presets`](an.expression.presets.md#module-an.expression.presets)         | Expression presets: our art direction on the axes (an#98).                           |
| [`provider`](an.expression.provider.md#module-an.expression.provider)       | The expression provider: authored leaves + dialogue sugar → per-axis curves (an#98). |
