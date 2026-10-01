# an.text

Words on screen: title cards, labels, and text you can animate word by word.

Epic #9 Wave 8, first slice; the design question was an#155. A text block is a
**prop** whose document `kind` is `TextDescriptor` — the shape stroked paths
took ([`an.paths`](an.paths.md#module-an.paths)) — so a scene names it with an ordinary
`AssetRef(kind="prop", ...)`, its `overrides` supply the per-shot string,
and nothing in the scene IR changed (no field, no migration).

```pycon
>>> title = TextDescriptor(name="title", text="Words on screen", layer="overlay")
>>> title.kind, title.unit, title.layer
('TextDescriptor', 'word', 'overlay')
```

**Typesetting is not done here.** The sibling package `tituli` owns it —
shaping, real glyph metrics, wrapping, alignment, the title-safe area — and
emits a `Layout` of placed `Run``s, one per unit. :func:`layout_text` asks it
for that layout and for each run's glyph contours (``tituli.run_outline`), and
the compiler turns each unit into one node whose visual is an SVG sprite
converted at compile time. The runtime never learns what text is, so fonts
never reach the frame path and the determinism perimeter is unchanged.

**Units are addressable, so text animates with ordinary tweens.** A block of
`unit="word"` builds `<id>/word_0`, `<id>/word_1`, …; `"glyph"` and
`"line"` likewise. `index` counts DRAWN units in reading order (spaces are
not units). [`stagger()`](#an.text.stagger) is a Python-side generator of ordinary actions for
a staggered reveal — a preset, not a new IR node:

```pycon
>>> from an.ir.compose import flatten
>>> reveal = stagger("title", 3, "alpha", to=1.0, from_=0.0, duration=0.3, step=0.1)
>>> [(f.action.target, round(f.start, 3)) for a in reveal for f in flatten(a)
...  if f.action.kind == "tween"]
[('title/word_0', 0.0), ('title/word_1', 0.1), ('title/word_2', 0.2)]
```

**Two layers.** `layer="world"` is in the scene and moves with the camera, like
any prop. `layer="overlay"` is drawn in a second top-level container the
camera never touches — a title card stays exactly where it is through a
push-in while an in-world label grows with the scene.

**Fonts fail loudly and never depend on the machine.** `font=None` is the
face Pillow embeds (Aileron, CC0 — “No Rights Reserved”), requested through
`tituli.EMBEDDED` so the installed fonts are never consulted: the same bytes
on every machine with the same Pillow, and no typeface is vendored in this
package. `font` otherwise names a font FILE (`.ttf`/`.otf`/`.ttc`),
absolute or relative to the text document’s directory in the props store;
a path that is not a file, or a file the typesetter could not use, RAISES
([`TextFontError`](#an.text.TextFontError)). A family NAME is refused on purpose: resolving one
would make the picture depend on what a machine has installed. A character
the face has no glyph for raises too — `an` is English-first and refuses
loudly rather than drawing a box. The face’s identity (sha256 of its bytes) is
recorded in the compiled document.

### Module Attributes

| [`TEXT_DOCUMENT_KIND`](#an.text.TEXT_DOCUMENT_KIND)   | Its own versioned document kind, registered from the module that owns the schema (the rule `PathDescriptor` and `PropDescriptor` follow).   |
|-----------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_TEXT_SIZE`](#an.text.DFLT_TEXT_SIZE)       | 0.06 is 65 px at 1080p, and the same block reads the same at 720p and at 4K.                                                                |
| [`DFLT_TEXT_COLOUR`](#an.text.DFLT_TEXT_COLOUR)     | Ink when the document names none — a near-black that reads on the default white background.                                                 |
| [`RESERVED_TEXT_IDS`](#an.text.RESERVED_TEXT_IDS)    | the runtime indexes the scene's container as `root` (the camera's target), and the overlay container is named `overlay`.                    |

### Functions

| [`resolve_text`](#an.text.resolve_text)(document[, overrides])              | The text block an entity draws: its stored document with `overrides` on top.                                                                                                                                                                                                              |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`font_base_dir`](#an.text.font_base_dir)(props_store, ref)                  | What a relative `font` path resolves against: the text document's own directory in an on-disk props store — `None` for an in-memory one, where a relative path then RAISES rather than resolving against the working directory (which would make the picture depend on where you ran it). |
| [`text_entity_problem`](#an.text.text_entity_problem)(entity, desc)                | What is wrong with WHERE this entity puts its block, or `None`.                                                                                                                                                                                                                           |
| [`layout_text`](#an.text.layout_text)(desc, \*, width, height[, base_dir]) | Set `desc` on a `width` x `height` frame and take each unit's contours.                                                                                                                                                                                                                   |
| [`unit_names`](#an.text.unit_names)(desc, \*, width, height[, base_dir])  | The node names a block builds — what `<id>/<name>` targets may address.                                                                                                                                                                                                                   |
| [`stagger`](#an.text.stagger)(entity_id, count, property, \*, to, ...) | Tween `property` from `from_` to `to` on units `0..count-1` of a text block, each `step` seconds after the last — a word-by-word (or letter-by-letter) reveal.                                                                                                                            |

### Classes

| [`TextDescriptor`](#an.text.TextDescriptor)(\*\*data)                      | The on-disk text schema, saved as a prop's `prop.json`.                   |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`TextUnit`](#an.text.TextUnit)(name, text, box, d)                  | One addressable unit: its node name, its string, its box and its ink.     |
| [`TextLayout`](#an.text.TextLayout)(units, origin, font)               | A placed block: its units, its reference point, and the face that set it. |
| [`FontIdentity`](#an.text.FontIdentity)(family, style, sha256, embedded) | Which face drew a block — by its bytes, not its name.                     |

### Exceptions

| [`TextFontError`](#an.text.TextFontError)   | A text block's font cannot be used: not a file, not a font, or not the face the typesetter actually used.   |
|------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| [`TextLayoutError`](#an.text.TextLayoutError) | The text cannot be set as asked (a glyph the face lacks, nothing to draw).                                  |

### an.text.DFLT_TEXT_COLOUR *: str* *= '#1a1a1a'*

Ink when the document names none — a near-black that reads on the default
white background.

### an.text.DFLT_TEXT_SIZE *: float* *= 0.06*

0.06 is
65 px at 1080p, and the same block reads the same at 720p and at 4K.

* **Type:**
  Type size as a FRACTION OF FRAME HEIGHT (tituli’s convention)

### *class* an.text.FontIdentity(family, style, sha256, embedded, layout_engine='basic')

Bases: `object`

Which face drew a block — by its bytes, not its name.

#### label()

`"Aileron Regular (embedded) sha256:6985… layout:basic"` — what the
compiled document records.

* **Return type:**
  `str`

#### layout_engine *: str* *= 'basic'*

Pillow’s layout engine for this face (`basic` or `raqm`). Recorded
because it moves glyph ADVANCES: RAQM (HarfBuzz) applies kerning and
ligatures and is used for a font file whenever libraqm can be loaded,
so the same bytes can set differently on two machines. The embedded
face is always `basic`.

### an.text.RESERVED_TEXT_IDS *: frozenset[str]* *= frozenset({'overlay', 'root'})*

the runtime indexes the scene’s
container as `root` (the camera’s target), and the overlay container is
named `overlay`. An overlay block called `root` would overwrite the
camera’s node in the runtime’s index and take the push-in with it.

* **Type:**
  Entity ids a text block may not take

### an.text.TEXT_DOCUMENT_KIND *: [DocumentKind](an.ir.md#an.ir.DocumentKind)* *= DocumentKind(name='TextDescriptor', version_field='schema_version', current_version='0.1.0')*

Its own versioned document kind, registered from the module that owns the
schema (the rule `PathDescriptor` and `PropDescriptor` follow).

### *class* an.text.TextDescriptor(\*\*data)

Bases: `BaseModel`

The on-disk text schema, saved as a prop’s `prop.json`.

`extra="forbid"` (the `PathDescriptor` precedent): a text block is a
precise instruction, and a misspelt `colour` that silently did nothing is
the defect class this package refuses. Set-but-inert combinations raise too:

```pycon
>>> TextDescriptor(name="t", text="hi", anchor="top")
Traceback (most recent call last):
...
pydantic_core._pydantic_core.ValidationError: 1 validation error for TextDescriptor
  Value error, `anchor` places a block in the title-safe area of the FRAME, which only an overlay has; a world-layer block is placed with the entity's `stage.at` [type=value_error, input_value=..., input_type=dict]
...
```

#### anchor *: str | None*

one of tituli’s nine anchors (`"top"`, `"bottom-left"`,
`"center"`, …) inside the title-safe area. `None` centres the block
on the node origin (the frame centre, or `stage.at`).

* **Type:**
  Overlay only

#### color *: str*

`#rrggbb`.

#### font *: str | None*

`None` = the embedded face; else a font FILE path (see the module doc).

#### max_width *: float | None*

Wrap width as a fraction of frame WIDTH; `None` = break only at newlines.

#### model_config *: ClassVar[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### size *: float*

Fraction of frame height.

#### text *: str*

The words. Explicit newlines break lines; `max_width` wraps.

#### tracking *: float*

tituli sets a
tracked string one run per glyph, so a word unit would not exist.

* **Type:**
  Extra advance per glyph, in em. Only with `unit="glyph"`

#### unit *: Literal['word', 'glyph', 'line']*

a word, a glyph, or a whole line.

* **Type:**
  What one addressable node is

### *exception* an.text.TextFontError

Bases: `ValueError`

A text block’s font cannot be used: not a file, not a font, or not the
face the typesetter actually used. Raised instead of falling back, because
a fallback face is a different picture wearing the right one’s clothes.

### *class* an.text.TextLayout(units, origin, font)

Bases: `object`

A placed block: its units, its reference point, and the face that set it.

`origin` is the block’s reference point in frame pixels — the frame
centre, or its title-safe anchor position — which is where the block’s own
node sits; each unit’s node is placed relative to it.

### *exception* an.text.TextLayoutError

Bases: `ValueError`

The text cannot be set as asked (a glyph the face lacks, nothing to draw).

### *class* an.text.TextUnit(name, text, box, d)

Bases: `object`

One addressable unit: its node name, its string, its box and its ink.

`box` is `(x0, y0, x1, y1)` in frame pixels, snapped OUTWARD to whole
pixels and containing both the layout box and the ink, so the sprite’s
corners sit on the pixel grid and nothing is clipped. `d` is the unit’s
glyph contours as SVG path data in frame pixels.

#### *property* center *: tuple[float, float]*

The box centre in frame pixels — where the unit’s node sits.

#### *property* size *: tuple[int, int]*

`(width, height)` of `box`.

### an.text.font_base_dir(props_store, ref)

What a relative `font` path resolves against: the text document’s own
directory in an on-disk props store — `None` for an in-memory one, where a
relative path then RAISES rather than resolving against the working
directory (which would make the picture depend on where you ran it).

* **Return type:**
  `Path` | `None`

### an.text.layout_text(desc, , width, height, base_dir=None)

Set `desc` on a `width` x `height` frame and take each unit’s contours.

`base_dir` is what a relative `font` path resolves against — the text
document’s own directory in the props store.

* **Return type:**
  [`TextLayout`](#an.text.TextLayout)

```pycon
>>> lay = layout_text(TextDescriptor(name="t", text="Hello big world"), width=1920, height=1080)
>>> [u.name for u in lay.units]
['word_0', 'word_1', 'word_2']
>>> lay.origin
(960.0, 540.0)
>>> lay.font.family, lay.font.embedded
('Aileron', True)
```

### an.text.resolve_text(document, overrides=None)

The text block an entity draws: its stored document with `overrides` on top.

Validated strictly AFTER the merge, so a stored document may be a reusable
style with no `text` of its own, and each entity supplies the words:

* **Return type:**
  [`TextDescriptor`](#an.text.TextDescriptor)

```pycon
>>> style = {"kind": "TextDescriptor", "name": "label", "size": 0.04}
>>> resolve_text(style, {"text": "Paris"}).text
'Paris'
```

### an.text.stagger(entity_id, count, property, , to, from_, duration, step, start=0.0, unit='word', easing='ease_out')

Tween `property` from `from_` to `to` on units `0..count-1` of a
text block, each `step` seconds after the last — a word-by-word (or
letter-by-letter) reveal. Unit `i` starts at `start + i*step`.

A unit whose tween starts later also gets a `set` to `from_` at 0, which
HOLDS until its tween begins (the compiler’s set-hold rule) — without it the
word would show its built value until its turn and then snap to `from_`.
That is also why `from_` is required.

Returns a LIST of top-level actions — `set`, a bare `tween`, or the
`sequence(delay(start), tween)` wrapper the `scene.md` parser itself
produces for a `start:` key — so `shot.actions.extend(stagger(...))`
round-trips through `scene.md`. (A `parallel` would not: the markdown
writer only knows leaf shapes and that one wrapper.)

* **Return type:**
  `list`

```pycon
>>> [a.kind for a in stagger("t", 2, "alpha", to=1, from_=0, duration=0.2, step=0.1)]
['tween', 'set', 'sequence']
```

### an.text.text_entity_problem(entity, desc)

What is wrong with WHERE this entity puts its block, or `None`.

The one statement of the placement rules, called by the compiler (which
raises) and by `an validate` (which reports) so the two agree:

- a reserved id ([`RESERVED_TEXT_IDS`](#an.text.RESERVED_TEXT_IDS)) — `root` would hijack the
  camera’s node in the runtime’s index;
- `anchor` and `stage.at` together — two answers to one question.

* **Return type:**
  `str` | `None`

### an.text.unit_names(desc, , width, height, base_dir=None)

The node names a block builds — what `<id>/<name>` targets may address.

* **Return type:**
  `list`[`str`]
