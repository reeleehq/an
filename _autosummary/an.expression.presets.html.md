# an.expression.presets

Expression presets: our art direction on the axes (an#98).

Every name the compiler’s retired brow-tilt table accepted is a preset here
(`amused` included — live content authors it), plus the two the research
added (`afraid`, `disgusted`). The FACS action-unit numbers in each `anchor` are cross-reference
comments, not sources: no emotion table was transcribed (research
`misc/docs/wave6_research.md` §3, §8). Gaze is absent from every preset so
the two sources stay independent — “thinking looks up and away” is a gaze
action, not a preset value.

A preset’s `mouth_form` names the `viseme@<form>` set its mouth prefers;
a character that declares none falls back to `viseme` with a warning
([`an.expression.binding.resolve_mouth_set()`](an.expression.binding.html.md#an.expression.binding.resolve_mouth_set)).

```pycon
>>> preset_axes("happy")["brow_height_l"]
0.2
>>> preset_axes("happy", intensity=0.5)["brow_height_l"]
0.1
>>> preset_axes("happy", axes={"brow_height_l": -1.0})["brow_height_l"]
-1.0
>>> preset_axes(None) == {}
True
>>> PRESETS["skeptical"].mouth_form is None
True
```

### Functions

| [`known_presets`](#an.expression.presets.known_presets)()                            | The preset names, in declaration order.                                                                                          |
|---------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| [`mouth_form_of`](#an.expression.presets.mouth_form_of)(preset)                      | The `viseme@<form>` a preset prefers, or `None` for the neutral set.                                                             |
| [`preset_axes`](#an.expression.presets.preset_axes)(preset, \*[, axes, intensity]) | The numeric axis offsets an expression asks for: the preset's, with `axes` layered over them, scaled by `intensity` and clamped. |

### Classes

| [`Preset`](#an.expression.presets.Preset)(name[, axes, mouth_form, anchor])   | A named expression: axis offsets, the mouth form it prefers, its anchor.   |
|---------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|

### *class* an.expression.presets.Preset(name, axes=<factory>, mouth_form=None, anchor='')

Bases: `object`

A named expression: axis offsets, the mouth form it prefers, its anchor.

#### anchor *: str* *= ''*

FACS AU cross-reference (a comment, never a source).

#### mouth_form *: str | None* *= None*

The `viseme@<form>` set this preset’s mouth prefers; `None` = `viseme`.

### an.expression.presets.known_presets()

The preset names, in declaration order.

* **Return type:**
  `tuple`[`str`, `...`]

```pycon
>>> known_presets()[:3]
('neutral', 'happy', 'sad')
```

### an.expression.presets.mouth_form_of(preset)

The `viseme@<form>` a preset prefers, or `None` for the neutral set.

* **Return type:**
  `str` | `None`

```pycon
>>> mouth_form_of("amused"), mouth_form_of("thinking"), mouth_form_of(None)
('happy', None, None)
```

### an.expression.presets.preset_axes(preset, , axes=None, intensity=1.0)

The numeric axis offsets an expression asks for: the preset’s, with
`axes` layered over them, scaled by `intensity` and clamped. Only
non-zero offsets are returned, so a neutral expression is `{}`.

An unknown preset or axis is a `ValueError` — validate reports it as an
error, the compiler refuses it.

* **Return type:**
  `dict`[`str`, `float`]
