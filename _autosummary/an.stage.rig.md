# an.stage.rig

The rig model the stage draws: bones, slots, skins and attachments.

A *rig* is the stage’s own idea (a skeleton of bones, draw-ordered slots bound to
them, and skins mapping slots to drawable attachments); props use it as well as
characters. It lives in `an.stage` so the stage compiler can build a rig
without importing any genre; a genre’s descriptor (`cutan`’s
`CharacterDescriptor`) is composed from these types.

### Module Attributes

| [`DEFAULT_VIEW_BOX`](#an.stage.rig.DEFAULT_VIEW_BOX)   | 1024x1024 with feet near y≈980.   |
|---------------------------------------------------------------------|-----------------------------------|

### Functions

| [`attachment_box`](#an.stage.rig.attachment_box)(width, height, art)   | The box a part draws in, in view_box units: the declared size wins, the art's aspect is kept (an#220).   |
|---------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| [`drawn_attachment`](#an.stage.rig.drawn_attachment)(desc, skin, slot)   | The `(name, attachment)` a slot draws by default, or `None`.                                             |
| [`primary_slot_per_bone`](#an.stage.rig.primary_slot_per_bone)(desc)          | `{bone name: the slot that IS that bone}`, when one exists.                                              |

### Classes

| [`Attachment`](#an.stage.rig.Attachment)(\*\*data)   | A drawable: an SVG path + anchor point (in 0..1 per-axis units).        |
|-------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`Bone`](#an.stage.rig.Bone)(\*\*data)         | A skeleton joint with a local transform relative to its parent.         |
| [`RigModel`](#an.stage.rig.RigModel)(\*\*data)     | Common config: forward-compatible reads, strict writes.                 |
| [`Skin`](#an.stage.rig.Skin)(\*\*data)         | A named outfit/variant: maps slot → {attachment_name → Attachment}.     |
| [`Slot`](#an.stage.rig.Slot)(\*\*data)         | A draw-order slot bound to a bone, displaying one attachment at a time. |

### *class* an.stage.rig.Attachment(\*\*data)

Bases: [`RigModel`](#an.stage.rig.RigModel)

A drawable: an SVG path + anchor point (in 0..1 per-axis units).

```pycon
>>> a = Attachment(path="parts/head.svg", anchor=(0.5, 0.78))
>>> a.anchor
(0.5, 0.78)
```

#### anchor *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]*

Anchor in 0..1 per-axis units (Pixi’s Sprite.anchor convention).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### source *: [AssetSource](an.ir.assets.md#an.ir.assets.AssetSource) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where THIS part’s art came from, when it is not the descriptor’s
`source` — a character composed from several clips, or a carved head
on a CC0 body, credits each (an#220). `None` = the descriptor’s
`source` covers it. `an credits` lists every one; an all-rights-
reserved part makes the render NOT PUBLISHABLE like any other.
Omitted from the stored document when unset.

#### width *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The size the part draws at, in **view_box units** — the rig’s units,
the ones `x`/`y` and the bones use (an#220). \*\*A declared size
wins\*\* over the art’s own extent, as `Plane.size` does for plates.
Unset, the art’s own extent is the size: an SVG’s `width`/`height`
(else its viewBox), a raster’s PIXEL count — so a PNG carved at one
pixel per unit needs nothing, and one carved at any other scale
declares its size here instead of being resampled. The aspect is the
art’s, always (an#74): with ONE of the two declared the other follows
the art’s aspect; with both, the art is contained in the box
(uniformly scaled to fit, never stretched) and `an character
validate` says when the two aspects disagree. See
[`attachment_box()`](#an.stage.rig.attachment_box).

#### x *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Offset from the slot’s bone, in view_box units.

**This is where a part’s position lives**, and it is the reference data
model’s answer, not an invention: DragonBones puts it in
`display.transform`, Spine in the region attachment’s `{x, y}`, and
in both the *slot* carries no transform at all. It is what lets five face
parts share one `head` bone and still land in different places — before
this field they all stacked on the bone, because the descriptor had no
way to say otherwise and the compiler used hardcoded literals instead.

### *class* an.stage.rig.Bone(\*\*data)

Bases: [`RigModel`](#an.stage.rig.RigModel)

A skeleton joint with a local transform relative to its parent.

```pycon
>>> b = Bone(name="head", parent="torso", x=0, y=-260, pivot="neck")
>>> b.parent
'torso'
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### pivot *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Optional pivot name — must match a circle in the SVG `skeleton` group.

### an.stage.rig.DEFAULT_VIEW_BOX *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)]* *= (0, 0, 1024, 1024)*

1024x1024 with feet near y≈980. All parts
inherit this viewBox at export so PixiJS can use the SVG’s intrinsic
viewBox without a calibration step.

* **Type:**
  Canonical character viewBox

### *class* an.stage.rig.RigModel(\*\*data)

Bases: `BaseModel`

Common config: forward-compatible reads, strict writes.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.stage.rig.Skin(\*\*data)

Bases: [`RigModel`](#an.stage.rig.RigModel)

A named outfit/variant: maps slot → {attachment_name → Attachment}.

```pycon
>>> skin = Skin(name="default", slots={"mouth": {"mouth_a": Attachment(path="parts/mouth/mouth_a.svg")}})
>>> skin.slots["mouth"]["mouth_a"].path
'parts/mouth/mouth_a.svg'
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.stage.rig.Slot(\*\*data)

Bases: [`RigModel`](#an.stage.rig.RigModel)

A draw-order slot bound to a bone, displaying one attachment at a time.

```pycon
>>> s = Slot(name="mouth", bone="head", draw_order=7, attachment="mouth_x")
>>> s.attachment
'mouth_x'
```

#### attachment *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Default attachment name; the active attachment can change at runtime
via animation tracks targeting `slot:<name>.attachment`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.stage.rig.attachment_box(width, height, art)

The box a part draws in, in view_box units: the declared size wins, the
art’s aspect is kept (an#220).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> attachment_box(None, None, (40, 20))       # the art's own extent
(40.0, 20.0)
>>> attachment_box(120, None, (40, 20))        # width declared: height follows
(120.0, 60.0)
>>> attachment_box(None, 30, (40, 20))
(60.0, 30.0)
>>> attachment_box(120, 120, (40, 20))         # both: contained, never stretched
(120.0, 60.0)
>>> attachment_box(120, 90, None)              # unmeasurable art: the box as declared
(120.0, 90.0)
>>> attachment_box(120, None, None) is None    # nothing to take the aspect from
True
```

### an.stage.rig.drawn_attachment(desc, skin, slot)

The `(name, attachment)` a slot draws by default, or `None`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Attachment`](#an.stage.rig.Attachment)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.stage.rig.primary_slot_per_bone(desc)

`{bone name: the slot that IS that bone}`, when one exists.

Used for node nesting, which is deliberately **not** the bone hierarchy.
The rigs here are flat by design — arms are siblings of the torso, not
children (CLAUDE.md pillar 4) — so bone parentage decides *position* only.
A slot nests under the primary slot of its bone when it is not that slot
itself, which is what puts eyes and mouth under `head` and leaves every
limb a direct child of the entity.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from types import SimpleNamespace as NS
>>> primary_slot_per_bone(NS(slots=[NS(name="head", bone="head"), NS(name="mouth", bone="head")]))["head"]
'head'
```
