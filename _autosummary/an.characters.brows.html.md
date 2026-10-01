# an.characters.brows

Brow acting: where the brows can go, what may not draw there, and the `face.brows` capability.

An expression acts largely with the brows (raised in surprise, knitted in
anger, tilted in sorrow). A drawing that sits where the brows go — a hat brim
pulled down over the forehead — leaves them nothing to read against, and the
expression falls to the lids, the gaze and the mouth (an#252). So:

- **The brows’ acting range** ([`brow_range()`](#an.characters.brows.brow_range)) is measured, not assumed:
  the factory’s brow drawing, posed by every shipped expression preset through
  the default expression binding (its travel and its signs), on every view
  that shows a brow, at the character’s head scale — in the offline head’s
  drawing units, so it can be compared with what the head draws.
- **A hat is seated above that range** ([`seat_above_brows()`](#an.characters.brows.seat_above_brows)): lifted, and
  if its crown would leave the drawing, flattened toward its crown, by one
  transform shared by every view so the hat does not change shape as the
  character turns. When even the flattest seat still overlaps — a small head
  under a tall hat — the overlap is not hidden: the factory records it in the
  descriptor’s `occluded` (a declared fact, written by whoever KNOWS the
  geometry, like `colour_roles`).
- **\`\`face.brows\`\`** is the capability the character analyser
  ([`an.library.character`](an.library.character.html.md#module-an.library.character)) derives with [`brow_affordance()`](#an.characters.brows.brow_affordance): two brow
  slots with art on an overlay face, and nothing recorded over them. The cut-out genre’s `expression` aspect
  requires it for its full-face method ([`an.characters.methods`](an.characters.methods.html.md#module-an.characters.methods)).

Hair is not measured here: the brows’ outer ends meet the hairline by design
(the default hair has always run under them), so a hair style is held to the
default hairline instead (tests), never to the brows’ range.

Units: the offline head is drawn in an [`HEAD_ART_SIZE`](#an.characters.brows.HEAD_ART_SIZE) square; the rig
draws it [`REFERENCE_HEAD_HEIGHT`](an.characters.schema.html.md#an.characters.schema.REFERENCE_HEAD_HEIGHT) × `head_scale`
view-box units tall, hung from the neck at
[`HEAD_ANCHOR`](an.characters.schema.html.md#an.characters.schema.HEAD_ANCHOR). The face offsets scale with the head
(`_scale_face`), so a brow’s rest place in head units does not depend on the
head scale; its expression travel does (`BROW_HEIGHT_TRAVEL` is a view-box
length), which is why a small head’s brows reach higher up its forehead.

A surprised brow reaches about three head units above its rest, less on a
bigger head; a band drawn across the forehead is lifted clear of it:

```pycon
>>> round(BROW_REST_TOP, 1)
22.8
>>> [round(min(brow_range(head_scale=s)["front"].values()), 1) for s in (1.0, 1.7)]
[19.5, 20.3]
>>> seat_above_brows({"front": '<rect x="20" y="20" width="40" height="4"/>'}, head_scale=1.0)
Seat(transform='translate(0 -5.47)', covers=False)
```

### Module Attributes

| [`HEAD_ART_SIZE`](#an.characters.brows.HEAD_ART_SIZE)      | The offline head's drawing is this many units square (its `viewBox`).                                                                                  |
|---------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`BROW_CANVAS`](#an.characters.brows.BROW_CANVAS)        | its canvas (view-box units at head scale 1), the stroke, and how far each end tilts from the level.                                                    |
| [`BROWS_FEATURE`](#an.characters.brows.BROWS_FEATURE)      | The face features a drawing can be recorded as covering (`occluded` keys).                                                                             |
| [`HAT_BROW_CLEARANCE`](#an.characters.brows.HAT_BROW_CLEARANCE) | Head units left between a hat's lowest ink and the brows' highest reach — about the outline's width, so a raised brow never touches the brim's line.   |
| [`HAT_CROWN_MIN_Y`](#an.characters.brows.HAT_CROWN_MIN_Y)    | How high a lifted hat's crown may go (head units from the drawing's top edge): above it the crown would be clipped by the head's canvas.               |
| [`HAT_MIN_FLATTEN`](#an.characters.brows.HAT_MIN_FLATTEN)    | The flattest a hat is drawn (its height kept, as a fraction) to seat it above the brows; past it the hat keeps this shape and the overlap is recorded. |

### Functions

| [`brow_affordance`](#an.characters.brows.brow_affordance)(desc, drawn)                       | `face.brows`'s params for a descriptor whose drawn slots are `drawn`, or `None`.   |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`brow_slots`](#an.characters.brows.brow_slots)(desc)                                   | The slots the character's own expression binding moves on a brow axis.             |
| [`brow_path_d`](#an.characters.brows.brow_path_d)(side)                                  | The path of the factory's brow on `side` (`l` or `r`) in its canvas.               |
| [`brow_range`](#an.characters.brows.brow_range)(\*[, head_scale, views, presets])       | `{view: {column: top}}`: the highest the brows' ink reaches, per head-unit column. |
| [`ink_columns`](#an.characters.brows.ink_columns)(discs)                                 | `{column: (top, bottom)}` of ink, per head-unit column (`round(x)`).               |
| [`seat_above_brows`](#an.characters.brows.seat_above_brows)(fragments, \*[, head_scale, ...]) | Seat a hat, drawn as `{view: svg fragment}` in head units, above the brows' range. |

### Classes

| [`Seat`](#an.characters.brows.Seat)([transform, covers])   | Where a hat is drawn: `transform` (`None`: where it was drawn) and whether it still covers the brows' range there (`covers`).   |
|------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|

### an.characters.brows.BROWS_FEATURE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'brows'*

The face features a drawing can be recorded as covering (`occluded` keys).

### an.characters.brows.BROW_CANVAS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)]* *= (80, 24)*

its canvas (view-box units at head scale 1),
the stroke, and how far each end tilts from the level.

* **Type:**
  The factory’s brow drawing

### an.characters.brows.HAT_BROW_CLEARANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1.0*

Head units left between a hat’s lowest ink and the brows’ highest reach —
about the outline’s width, so a raised brow never touches the brim’s line.

### an.characters.brows.HAT_CROWN_MIN_Y *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

How high a lifted hat’s crown may go (head units from the drawing’s top
edge): above it the crown would be clipped by the head’s canvas.

### an.characters.brows.HAT_MIN_FLATTEN *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.6*

The flattest a hat is drawn (its height kept, as a fraction) to seat it
above the brows; past it the hat keeps this shape and the overlap is recorded.

### an.characters.brows.HEAD_ART_SIZE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 80.0*

The offline head’s drawing is this many units square (its `viewBox`).

### *class* an.characters.brows.Seat(transform=None, covers=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Where a hat is drawn: `transform` (`None`: where it was drawn) and
whether it still covers the brows’ range there (`covers`).

### an.characters.brows.brow_affordance(desc, drawn)

`face.brows`’s params for a descriptor whose drawn slots are `drawn`, or `None`.

Afforded when the face is an overlay (`face_overlay`), the binding moves
a brow ([`brow_slots()`](#an.characters.brows.brow_slots)) and every slot it moves on a brow axis has
art, and the descriptor records nothing over the brows (`occluded`).
The slots are the solver’s own binding’s, so the capability and the solver
cannot disagree about which slots act.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> from an.characters.schema import CharacterDescriptor
>>> d = CharacterDescriptor(name="c")
>>> brow_affordance(d, {"left_brow": {"brow_l"}, "right_brow": {"brow_r"}})
{'slots': ['left_brow', 'right_brow']}
>>> d.occluded = {"brows": "a helmet"}
>>> brow_affordance(d, {"left_brow": {"brow_l"}, "right_brow": {"brow_r"}}) is None
True
```

### an.characters.brows.brow_path_d(side)

The path of the factory’s brow on `side` (`l` or `r`) in its canvas.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> brow_path_d("l")
'M 8 16 Q 40 4 72 8'
```

### an.characters.brows.brow_range(, head_scale=1.0, views=('front', 'three_quarter', 'side'), presets=None)

`{view: {column: top}}`: the highest the brows’ ink reaches, per head-unit column.

Every shipped expression preset (or `presets`), at full intensity, posed
through the default binding on each brow the view shows (its turnaround
pose: shifted, narrowed, or hidden) — the region a cover must stay above
for the presets to read.
The range is bounded by the PRESETS, not by the axes’ full box: an
`axes:` override at the corner (height 1, a full tilt) or two summed
spans can reach past it (review-278 L1).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.characters.brows.brow_slots(desc)

The slots the character’s own expression binding moves on a brow axis.

The binding the solver uses ([`binding_for()`](an.expression.binding.html.md#an.expression.binding.binding_for):
the declared `expression_binding`, else the default one), so a rig whose
brows live on slots of its own naming is read as having brows, and one
whose declared binding moves no brow is read as having none. A binding
that does not resolve moves nothing (`an validate` reports it).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from an.characters.schema import CharacterDescriptor
>>> brow_slots(CharacterDescriptor(name="c"))
['left_brow', 'right_brow']
```

### an.characters.brows.ink_columns(discs)

`{column: (top, bottom)}` of ink, per head-unit column (`round(x)`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

```pycon
>>> ink_columns([(10.2, 5.0, 0.0), (10.4, 7.0, 0.0)])
{10: (5.0, 7.0)}
```

### an.characters.brows.seat_above_brows(fragments, , head_scale=1.0, clearance=1.0, crown_min_y=0.5, min_flatten=0.6)

Seat a hat, drawn as `{view: svg fragment}` in head units, above the brows’ range.

No transform when it already clears them by `clearance`. Else it is
lifted — as far as its crown may go (`crown_min_y`) — and, if that is
not enough, flattened toward its crown, never below `min_flatten` of its
height; one transform for every view. `covers` says the seat found still
overlaps the range (it never claims a clearance it did not measure).

* **Return type:**
  [`Seat`](#an.characters.brows.Seat)
