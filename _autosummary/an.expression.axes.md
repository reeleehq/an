# an.expression.axes

The facial expression axes: what a cutout face can be asked to do (an#98).

Ten axes ship in Wave 6 of epic #9 — eight numeric, one selection
(`mouth_form`, which picks a `viseme@<preset>` set and is not a number),
one scalar (`intensity`). Every numeric value is an \*\*offset over the built
rest\*\* of the node it drives; rest is neutral. The ranges and the eyelid
ladder below are the only numbers in the vocabulary (research
`misc/docs/wave6_research.md` §4, §6).

Deferred, named so nobody re-invents them: `brow_squeeze`, `squint`,
`head_yaw` / `head_pitch` (Wave 7), `mouth_open` (the viseme set already
opens monotonically `X → A → B → C → D`).

```pycon
>>> AXES["brow_height_l"].clamp(3.0)
1.0
>>> lid_key(-0.9, available={"OPEN", "CLOSED"})
'CLOSED'
>>> lid_key(-0.5, available={"OPEN", "CLOSED"})          # no `half` art: stays open
'OPEN'
>>> lid_key(-0.5, available={"OPEN", "CLOSED", "HALF"})
'HALF'
```

### Module Attributes

| [`AXES`](#an.expression.axes.AXES)            |                                                                                    |
|------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`MOUTH_FORM_AXIS`](#an.expression.axes.MOUTH_FORM_AXIS) | which `viseme@<form>` set the mouth's key indexes.                                 |
| [`INTENSITY_AXIS`](#an.expression.axes.INTENSITY_AXIS)  | The scalar on every offset (MPEG-4 "excitation"); the blend ramp is a curve on it. |
| [`LID_WIDE_ABOVE`](#an.expression.axes.LID_WIDE_ABOVE)  | The eyelid ladder — one rule, stated once (research §6).                           |
| [`LID_KEY_WIDE`](#an.expression.axes.LID_KEY_WIDE)    | Eyelid set keys the ladder can name, by openness.                                  |

### Functions

| [`clamp_axes`](#an.expression.axes.clamp_axes)(values)            | Clamp every numeric axis to its range; an unknown axis is an error.       |
|--------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`lid_key`](#an.expression.axes.lid_key)(value, \*, available) | The eyelid key a lid state selects, degraded to the art the rig declares. |

### Classes

| [`Axis`](#an.expression.axes.Axis)(name, lo, hi[, rest])   | One numeric axis: its range and its rest (neutral) value.   |
|-------------------------------------------------------------------------------|-------------------------------------------------------------|

### an.expression.axes.AXES *: dict[str, [Axis](#an.expression.axes.Axis)]* *= {'brow_angle_l': Axis(name='brow_angle_l', lo=-1.0, hi=1.0, rest=0.0), 'brow_angle_r': Axis(name='brow_angle_r', lo=-1.0, hi=1.0, rest=0.0), 'brow_height_l': Axis(name='brow_height_l', lo=-1.0, hi=1.0, rest=0.0), 'brow_height_r': Axis(name='brow_height_r', lo=-1.0, hi=1.0, rest=0.0), 'gaze_x': Axis(name='gaze_x', lo=-1.0, hi=1.0, rest=0.0), 'gaze_y': Axis(name='gaze_y', lo=-1.0, hi=1.0, rest=0.0), 'lid_open_l': Axis(name='lid_open_l', lo=-1.0, hi=0.5, rest=0.0), 'lid_open_r': Axis(name='lid_open_r', lo=-1.0, hi=0.5, rest=0.0)}*

+ raises the brow, scaled by the rig’s eye height.

Brow angle, per side: + inner end up (worry), − inner end down (furrow);
the binding’s per-side gain carries the screen sign.
Lid openness, per side: − closes (`half`, then `closed`), + widens (`wide`).
Gaze: pupil travel inside the eye, clamped by the rig’s declared travel.

* **Type:**
  Brow height, per side

### *class* an.expression.axes.Axis(name, lo, hi, rest=0.0)

Bases: `object`

One numeric axis: its range and its rest (neutral) value.

### an.expression.axes.INTENSITY_AXIS *: str* *= 'intensity'*

The scalar on every offset (MPEG-4 “excitation”); the blend ramp is a curve on it.

### an.expression.axes.LID_KEY_WIDE *: str* *= 'WIDE'*

Eyelid set keys the ladder can name, by openness.

### an.expression.axes.LID_WIDE_ABOVE *: float* *= 0.25*

The eyelid ladder — one rule, stated once (research §6). A lid state
`min(lid_expr, lid_blink)` reads off these thresholds; a rig without the
intermediate art degrades to the key it has.

### an.expression.axes.MOUTH_FORM_AXIS *: str* *= 'mouth_form'*

which `viseme@<form>` set the mouth’s key indexes.

* **Type:**
  The selection axis

### an.expression.axes.clamp_axes(values)

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

### an.expression.axes.lid_key(value, , available)

The eyelid key a lid state selects, degraded to the art the rig declares.

`wide` above +0.25, `open`, `half` below −0.35, `closed` below −0.85;
a rig without `half` stays open until the lower threshold and one without
`wide` stays open above the upper one — never a blend of two drawings.

* **Return type:**
  `str`
