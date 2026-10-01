# an.expression.provider

The expression provider: authored leaves + dialogue sugar → per-axis curves (an#98).

The face solver in the cutout compiler sums contributors per `(node,
property)` at compile time. It gets those contributors from an
[`ExpressionProvider`](#an.expression.provider.ExpressionProvider) — the seam an audio- or vision-driven source
plugs into later. The default provider composes, for one entity of one shot:

- every `expression` leaf action (flattened out of the shot’s composition
  tree with its absolute times);
- the **dialogue sugar**: a line’s `[emotion]` becomes an expression over
  the line, **in memory only** — never written into `shot.actions` or the
  scenes store, or the md writer would emit the emotion twice.

Each span ramps its intensity in and out over `blend` seconds (0 = cut);
two overlapping spans cross-fade because the sum is additive. Curves are
sampled per frame, so the solver and this module agree on time by
construction.

```pycon
>>> from an.ir.schema import AssetRef, Dialogue, Shot
>>> from an.ir.compose import expression
>>> shot = Shot(id="s", renderer="cutout", duration=1.0,
...             entities=[AssetRef(kind="character", id="c", store="characters", ref="c")],
...             actions=[expression("c", "angry", blend=0.0)])
>>> [s.preset for s in expression_spans(shot, "c")]
['angry']
>>> curves = {c.axis: c for c in DefaultExpressionProvider().curves(shot, "c", fps=4)}
>>> curves["brow_angle_l"].samples
(-0.8, -0.8, -0.8, -0.8, -0.8)
```

### Module Attributes

| [`DIALOGUE_EMOTION_BLEND_S`](#an.expression.provider.DIALOGUE_EMOTION_BLEND_S)   | The `[emotion]` sugar ramps in and out over this; it is a comment on the line, not a cut.   |
|-----------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|

### Functions

| [`expression_spans`](#an.expression.provider.expression_spans)(shot, entity_id)   | Every expression contributor on `entity_id`: authored leaves, then dialogue sugar.   |
|--------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`flatten_expressions`](#an.expression.provider.flatten_expressions)(shot)           | The shot's `expression` leaves with absolute times (other leaves dropped).           |

### Classes

| [`AxisCurve`](#an.expression.provider.AxisCurve)(axis, samples)                        | One axis sampled at the frame times `0, 1/fps, …, n/fps` (offline, deterministic).   |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`DefaultExpressionProvider`](#an.expression.provider.DefaultExpressionProvider)()                     | Sum of the shot's expression spans on the entity, ramped, per frame.                 |
| [`ExpressionProvider`](#an.expression.provider.ExpressionProvider)(\*args, \*\*kwargs)          | The seam: whatever produces per-axis curves for one entity of one shot.              |
| [`ExpressionSpan`](#an.expression.provider.ExpressionSpan)(start, end, preset[, axes, ...]) | One expression contributor on one entity, in absolute shot time.                     |

### *class* an.expression.provider.AxisCurve(axis, samples)

Bases: `object`

One axis sampled at the frame times `0, 1/fps, …, n/fps` (offline, deterministic).

### an.expression.provider.DIALOGUE_EMOTION_BLEND_S *: float* *= 0.15*

The `[emotion]` sugar ramps in and out over this; it is a comment on the
line, not a cut.

### *class* an.expression.provider.DefaultExpressionProvider

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

### *class* an.expression.provider.ExpressionProvider(\*args, \*\*kwargs)

Bases: `Protocol`

The seam: whatever produces per-axis curves for one entity of one shot.

### *class* an.expression.provider.ExpressionSpan(start, end, preset, axes=<factory>, intensity=1.0, blend=0.0, source='action')

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

### an.expression.provider.expression_spans(shot, entity_id)

Every expression contributor on `entity_id`: authored leaves, then
dialogue sugar. `duration=None` runs to the shot end (the looping-play
rule); a span never extends past the shot.

* **Return type:**
  `list`[[`ExpressionSpan`](#an.expression.provider.ExpressionSpan)]

### an.expression.provider.flatten_expressions(shot)

The shot’s `expression` leaves with absolute times (other leaves dropped).
