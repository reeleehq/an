# an.characters.mouth_set

Generate the 9-shape default mouth set as parametric SVGs.

Produces drop-in art for `mouth_a` … `mouth_h` plus `mouth_x`, with
shape parameters cribbed from Daniel Wolf’s Rhubarb README (see research
§2.2). Every shape is rendered into the same per-mouth canvas
(`DEFAULT_MOUTH_VIEWBOX`, default 256×128) with a centered anchor, so
swapping attachments at runtime needs no per-shape offset.

The set is deliberately stylized — flat colors, bold strokes — so it reads
at the small sizes a typical cutout puppet uses (~30-40 px tall on a
1080p frame). It’s not meant to compete with hand-drawn art; it’s the
“always works” fallback.

```pycon
>>> svgs = generate_default_mouths()
>>> sorted(svgs.keys())
['mouth_a', 'mouth_b', 'mouth_c', 'mouth_d', 'mouth_e', 'mouth_f', 'mouth_g', 'mouth_h', 'mouth_x']
>>> len(svgs['mouth_a']) > 100
True
```

### Module Attributes

| [`DEFAULT_MOUTH_VIEWBOX`](#an.characters.mouth_set.DEFAULT_MOUTH_VIEWBOX)   | Mouth canvas viewBox (width, height) — small per-shape and centered so the anchor is always (0.5, 0.5).   |
|--------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| [`DEFAULT_MOUTH_VARIANTS`](#an.characters.mouth_set.DEFAULT_MOUTH_VARIANTS)  | a `viseme@<form>` set per entry, its shapes drawn with this corner upturn added (an#98).                  |

### Functions

| [`generate_default_mouths`](#an.characters.mouth_set.generate_default_mouths)(\*[, canvas, ...])       | Return `{"mouth_<letter>[_<form>]": <svg-string>, ...}` for every shape.                                                                                                            |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`mouth_attachment_name`](#an.characters.mouth_set.mouth_attachment_name)(shape[, form])             | The attachment (and file stem) of one mouth drawing.                                                                                                                                |
| [`write_default_mouths`](#an.characters.mouth_set.write_default_mouths)(out_dir, \*[, canvas, ...]) | Write the default mouth SVGs into `out_dir` (created if missing), plus one `mouth_<shape>_<form>.svg` per shape for every `variants` entry (`{form: smile offset}`; `None` = none). |

### an.characters.mouth_set.DEFAULT_MOUTH_VARIANTS *: dict[str, float]* *= {'happy': 0.35, 'sad': -0.35}*

a
`viseme@<form>` set per entry, its shapes drawn with this corner upturn
added (an#98). Every preset that prefers a form the character lacks falls
back to `viseme` with a warning, so the default covers the two forms the
most-authored presets (`happy`/`amused`, `sad`) ask for.

* **Type:**
  The mouth-form variants a synthesized character gets by default

### an.characters.mouth_set.DEFAULT_MOUTH_VIEWBOX *: tuple[int, int]* *= (256, 128)*

Mouth canvas viewBox (width, height) — small per-shape and centered so the
anchor is always (0.5, 0.5).

### an.characters.mouth_set.generate_default_mouths(, canvas=(256, 128), palette=None, shapes=('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'x'), smile=0.0, form=None)

Return `{"mouth_<letter>[_<form>]": <svg-string>, ...}` for every shape.

* **Return type:**
  `dict`[`str`, `str`]

```pycon
>>> svgs = generate_default_mouths()
>>> 'mouth_x' in svgs and 'viewBox' in svgs['mouth_x']
True
>>> sorted(generate_default_mouths(shapes=["a"], smile=0.35, form="happy"))
['mouth_a_happy']
```

### an.characters.mouth_set.mouth_attachment_name(shape, form=None)

The attachment (and file stem) of one mouth drawing.

* **Return type:**
  `str`

```pycon
>>> mouth_attachment_name("a"), mouth_attachment_name("a", "happy")
('mouth_a', 'mouth_a_happy')
```

### an.characters.mouth_set.write_default_mouths(out_dir, , canvas=(256, 128), palette=None, shapes=('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'x'), variants=None)

Write the default mouth SVGs into `out_dir` (created if missing),
plus one `mouth_<shape>_<form>.svg` per shape for every `variants`
entry (`{form: smile offset}`; `None` = none).

Returns the list of paths written: the neutral set in shape order, then
each variant’s.

* **Return type:**
  `list`[`Path`]
