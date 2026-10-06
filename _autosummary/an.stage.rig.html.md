# an.stage.rig

The rig model the stage draws: bones, slots, skins and attachments.

A *rig* is the stage’s own idea (a skeleton of bones, draw-ordered slots bound to
them, and skins mapping slots to drawable attachments); props use it as well as
characters. It lives in `an.stage` so the stage compiler can build a rig
without importing any genre; a genre’s descriptor (`cutan`’s
`CharacterDescriptor`) is composed from these types.

Two layers live here:

- **the model**: [`Bone`](#an.stage.rig.Bone), [`Slot`](#an.stage.rig.Slot), [`Attachment`](#an.stage.rig.Attachment),
  [`Skin`](#an.stage.rig.Skin), and [`RigDocument`](#an.stage.rig.RigDocument), the base of every document that IS a
  > rig (`PropDescriptor`, `CharacterDescriptor`), which carries the fields
  > about the rig as a whole (its declared [`RigDocument.origin`](#an.stage.rig.RigDocument.origin));
- **the builder**: [`build_rig_subtree()`](#an.stage.rig.build_rig_subtree), the ONE function that turns a rig
  document into a scene subtree for props and characters alike (an#108), with
  the helpers a genre needs to call it ([`part_probe()`](#an.stage.rig.part_probe),
  [`raster_digest()`](#an.stage.rig.raster_digest), [`art_src()`](#an.stage.rig.art_src), [`bone_positions()`](#an.stage.rig.bone_positions),
  [`rig_origin()`](#an.stage.rig.rig_origin)). Public since an#338: before it, `cutan` reached the
  > builder through private names of the stage compiler, which a second genre
  > could not have done. The compiler re-exports the old private spellings.

### Module Attributes

| [`DEFAULT_VIEW_BOX`](#an.stage.rig.DEFAULT_VIEW_BOX)             | 1024x1024 with feet near y≈980.                                                                                                                                                                                                                                                                                 |
|-------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`RIG_DOCUMENT_OPTIONAL_FIELDS`](#an.stage.rig.RIG_DOCUMENT_OPTIONAL_FIELDS) | The fields [`RigDocument`](#an.stage.rig.RigDocument) adds, each written out of the stored document when unset ([`omit_unset_rig_fields()`](#an.stage.rig.omit_unset_rig_fields)), so every descriptor that never set one reads back, and hashes, as it did before the field existed. |
| [`REST_POSE_SINCE`](#an.stage.rig.REST_POSE_SINCE)              | `{rig document kind: the version from which its bones' rest pose is applied}`, filled by [`register_rest_pose_migration()`](#an.stage.rig.register_rest_pose_migration) (an#339).                                                                                                                              |
| [`NESTINGS`](#an.stage.rig.NESTINGS)                     | The nesting modes ([`RigDocument.nesting`](#an.stage.rig.RigDocument.nesting)); unset means the first.                                                                                                                                                                                                |
| [`RIG_HIERARCHY`](#an.stage.rig.RIG_HIERARCHY)                | The capability a nested chain affords (ADR 0002 decision 1's name, registered by the core in [`an.capabilities.subjects`](an.capabilities.subjects.html.md#module-an.capabilities.subjects)).                                                                                                        |
| [`SCENE_PX_PER_VIEW_BOX`](#an.stage.rig.SCENE_PX_PER_VIEW_BOX)        | Scene-graph pixels spanned by a descriptor's full `view_box` height.                                                                                                                                                                                                                                            |
| [`CONTAIN_FIT`](#an.stage.rig.CONTAIN_FIT)                  | The fit policy every compiled sprite carries.                                                                                                                                                                                                                                                                   |
| [`CHARACTER_ART_PREFIX`](#an.stage.rig.CHARACTER_ART_PREFIX)         | The `assets.textures` `src` prefix a rig's art is addressed under, which is also the mall store that resolves it (`render.ASSET_SRC_PREFIX_TO_STORE`).                                                                                                                                                          |
| [`PROP_ART_PREFIX`](#an.stage.rig.PROP_ART_PREFIX)              | The same, for props.                                                                                                                                                                                                                                                                                            |

### Functions

| [`art_src`](#an.stage.rig.art_src)(ref, rel_path, \*[, art_prefix])           | Path used inside the runtime dir, relative to `index.html`.                                                                                                                                                                              |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`attachment_box`](#an.stage.rig.attachment_box)(width, height, art)                 | The box a part draws in, in view_box units: the declared size wins, the art's aspect is kept (an#220).                                                                                                                                   |
| [`bone_extent_centre`](#an.stage.rig.bone_extent_centre)(bones)                          | The DEFAULT point in view_box space that the entity's placement refers to, when the rig declares no [`RigDocument.origin`](#an.stage.rig.RigDocument.origin) ([`rig_origin()`](#an.stage.rig.rig_origin)). |
| [`bone_positions`](#an.stage.rig.bone_positions)(desc)                               | Absolute `(x, y)` per bone, in view_box units.                                                                                                                                                                                           |
| [`bones_carry_a_rest_pose`](#an.stage.rig.bones_carry_a_rest_pose)(doc)                       | Whether any bone of a (raw or model) rig document has a non-zero `rotation_deg` or a non-unit `scale_x`/`scale_y`.                                                                                                                       |
| [`build_rig_subtree`](#an.stage.rig.build_rig_subtree)(entity, desc_data, \*, textures) | Build the scene subtree for a rig (a prop or a character), **from its descriptor**.                                                                                                                                                      |
| [`chain_draw_order_problems`](#an.stage.rig.chain_draw_order_problems)(desc)                    | Where a nested chain asks the STAGE for a draw order it cannot give (an#340, an#403).                                                                                                                                                    |
| [`chain_paint_order`](#an.stage.rig.chain_paint_order)(desc, \*[, built])               | How each container of a nested chain must order what it holds (an#403).                                                                                                                                                                  |
| [`chain_pose_problems`](#an.stage.rig.chain_pose_problems)(desc)                          | A rest pose the stage cannot apply in a nested chain (an#340).                                                                                                                                                                           |
| [`declared_origin`](#an.stage.rig.declared_origin)(desc)                              | The rig's DECLARED origin as two floats, or `None` when it declares none.                                                                                                                                                                |
| [`drawn_attachment`](#an.stage.rig.drawn_attachment)(desc, skin, slot)                 | The `(name, attachment)` a slot draws by default, or `None`.                                                                                                                                                                             |
| [`legacy_rest_pose_unknown`](#an.stage.rig.legacy_rest_pose_unknown)(raw, kind, \*, since)     | The builder guard (an#339): whether `raw` may be a pre-rest-pose document that its migration could not see.                                                                                                                              |
| [`natural_paint_order`](#an.stage.rig.natural_paint_order)(order, keys)                   | What each container holds in the builder's own order: the slot's visual first, then its children by their own `(draw_order, name)`.                                                                                                      |
| [`nesting_of`](#an.stage.rig.nesting_of)(desc)                                   | `"flat"` or `"bones"` (an#340); unset is flat.                                                                                                                                                                                           |
| [`omit_unset_rig_fields`](#an.stage.rig.omit_unset_rig_fields)(data)                        | Drop every unset [`RigDocument`](#an.stage.rig.RigDocument) field from a dumped document, in place.                                                                                                                    |
| [`part_probe`](#an.stage.rig.part_probe)(characters_store, \*[, art_prefix])     | A probe answering `(art exists, the size it rasterises at)` for a part.                                                                                                                                                                  |
| [`primary_slot_per_bone`](#an.stage.rig.primary_slot_per_bone)(desc)                        | `{bone name: the slot that IS that bone}`, when one exists.                                                                                                                                                                              |
| [`protect_legacy_rest_pose`](#an.stage.rig.protect_legacy_rest_pose)(doc)                      | The migration step every rig kind runs onto the version that applies the rest pose (an#339).                                                                                                                                             |
| [`raster_digest`](#an.stage.rig.raster_digest)(store, \*[, art_prefix])             | `digest(src)`: a short content digest for RASTER art, else `None`.                                                                                                                                                                       |
| [`register_rest_pose_migration`](#an.stage.rig.register_rest_pose_migration)(kind, ...)            | Register the protective rest-pose step for one rig kind (an#339).                                                                                                                                                                        |
| [`rest_pose_protection`](#an.stage.rig.rest_pose_protection)(raw, migrated, \*[, kind])    | What to say when the MIGRATION, on this read, kept a rig's pose unapplied (an#407).                                                                                                                                                      |
| [`rest_transform`](#an.stage.rig.rest_transform)(bone)                               | The node transform fields a bone's rest pose sets (an#339): its `rotation_deg` in radians and its scales, `-0.0` normalised to `0.0`.                                                                                                    |
| [`rig_affordances`](#an.stage.rig.rig_affordances)(desc)                              | What a rig's structure affords, derived from the rig model (an#340).                                                                                                                                                                     |
| [`rig_origin`](#an.stage.rig.rig_origin)(desc)                                   | The point of the rig, in view_box units, that lands at the entity's placement.                                                                                                                                                           |
| [`rig_origin_problems`](#an.stage.rig.rig_origin_problems)(desc)                          | What is wrong with a rig's declared origin, as warnings (an#338).                                                                                                                                                                        |
| [`rig_problems`](#an.stage.rig.rig_problems)(desc)                                 | What is structurally wrong with a rig's bones and slots (an#340).                                                                                                                                                                        |
| [`rig_rest_problems`](#an.stage.rig.rig_rest_problems)(desc)                            | Warnings about a rig's rest pose (an#339), on a model or a raw document.                                                                                                                                                                 |
| [`slot_node_paths`](#an.stage.rig.slot_node_paths)(desc)                              | `{slot: its node path relative to the entity}` (`torso/arm/hand`), by [`slot_parent_chain()`](#an.stage.rig.slot_parent_chain); a slot caught in a cycle maps to its own name.                                               |
| [`slot_parent_chain`](#an.stage.rig.slot_parent_chain)(desc)                            | `{slot: the slot it nests under, or None}`: THE nesting rule (an#340).                                                                                                                                                                   |

### Classes

| [`Attachment`](#an.stage.rig.Attachment)(\*\*data)   | A drawable: an SVG path + anchor point (in 0..1 per-axis units).                   |
|-------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`Bone`](#an.stage.rig.Bone)(\*\*data)         | A skeleton joint with a local transform relative to its parent.                    |
| [`RigDocument`](#an.stage.rig.RigDocument)(\*\*data)  | The base of every document that IS a rig: `PropDescriptor`, `CharacterDescriptor`. |
| [`RigModel`](#an.stage.rig.RigModel)(\*\*data)     | Common config: forward-compatible reads, strict writes.                            |
| [`Skin`](#an.stage.rig.Skin)(\*\*data)         | A named outfit/variant: maps slot → {attachment_name → Attachment}.                |
| [`Slot`](#an.stage.rig.Slot)(\*\*data)         | A draw-order slot bound to a bone, displaying one attachment at a time.            |

### Exceptions

| [`RestPoseWarning`](#an.stage.rig.RestPoseWarning)   | A rig's bone rest pose was NOT applied, because the document may predate it.   |
|--------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`RigError`](#an.stage.rig.RigError)          | A rig cannot be built as declared (a cycle, or a chain the stage cannot draw). |

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

#### source *: [AssetSource](an.ir.assets.html.md#an.ir.assets.AssetSource) | [None](https://docs.python.org/3/builtins/constants.html#None)*

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

### an.stage.rig.CHARACTER_ART_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'characters/'*

The `assets.textures` `src` prefix a rig’s art is addressed under, which is
also the mall store that resolves it (`render.ASSET_SRC_PREFIX_TO_STORE`).
A parameter rather than a literal because the rig builder is the same code
for a character and for a prop, and the store is the ONLY thing that differs
about where their art lives. Two hardcoded copies of `"characters/"` — the
`src` builder and the probe’s own — reached three call sites, and that is
what made “a prop is a rig too” read as a rewrite instead of an argument
(an#108).

### an.stage.rig.CONTAIN_FIT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'contain'*

The fit policy every compiled sprite carries. Named rather than inlined so
the one place that decides “the art keeps its shape” is greppable.

### an.stage.rig.DEFAULT_VIEW_BOX *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)]* *= (0, 0, 1024, 1024)*

1024x1024 with feet near y≈980. All parts
inherit this viewBox at export so PixiJS can use the SVG’s intrinsic
viewBox without a calibration step.

* **Type:**
  Canonical character viewBox

### an.stage.rig.NESTINGS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('flat', 'bones')*

The nesting modes ([`RigDocument.nesting`](#an.stage.rig.RigDocument.nesting)); unset means the first.

### an.stage.rig.PROP_ART_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'props/'*

The same, for props. Both are keys of `render.ASSET_SRC_PREFIX_TO_STORE`,
which is what decides where the staging step copies the art from.

### an.stage.rig.REST_POSE_SINCE *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'PropDescriptor': '0.2.0'}*

`{rig document kind: the version from which its bones' rest pose is applied}`,
filled by [`register_rest_pose_migration()`](#an.stage.rig.register_rest_pose_migration) (an#339). The builder guard
reads it to recognise a document older than that version.

### an.stage.rig.RIG_DOCUMENT_OPTIONAL_FIELDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('origin', 'rest_rotation', 'nesting')*

The fields [`RigDocument`](#an.stage.rig.RigDocument) adds, each written out of the stored
document when unset ([`omit_unset_rig_fields()`](#an.stage.rig.omit_unset_rig_fields)), so every descriptor
that never set one reads back, and hashes, as it did before the field existed.

### an.stage.rig.RIG_HIERARCHY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'rig.hierarchy'*

The capability a nested chain affords (ADR 0002 decision 1’s name, registered
by the core in [`an.capabilities.subjects`](an.capabilities.subjects.html.md#module-an.capabilities.subjects)).

### *exception* an.stage.rig.RestPoseWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A rig’s bone rest pose was NOT applied, because the document may predate it.

### *class* an.stage.rig.RigDocument(\*\*data)

Bases: [`RigModel`](#an.stage.rig.RigModel)

The base of every document that IS a rig: `PropDescriptor`, `CharacterDescriptor`.

Holds what is true of the rig as a whole, not of one bone or slot (which is
why it is not [`RigModel`](#an.stage.rig.RigModel), the base of [`Bone`](#an.stage.rig.Bone) and the others
as well). Every field here is omitted from the stored document when unset.

```pycon
>>> RigDocument(origin=(512, 1010)).origin
(512.0, 1010.0)
>>> RigDocument().model_dump()
{}
>>> RigDocument(origin=(float("inf"), 0))
Traceback (most recent call last):
...
pydantic_core._pydantic_core.ValidationError: 1 validation error for RigDocument
...
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### nesting *: [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)['flat', 'bones'] | [None](https://docs.python.org/3/builtins/constants.html#None)*

a slot nests under its
OWN bone’s primary slot only, so limbs are siblings of the torso (the
rigs’ long-standing shape). `"bones"`: a slot nests under the primary
slot of the nearest ancestor bone that has one, to any depth, so a
forearm turns with its upper arm and a sword with its hand (forward
kinematics). [`slot_parent_chain()`](#an.stage.rig.slot_parent_chain) is the rule.

* **Type:**
  How slots nest (an#340). Unset or `"flat"`

#### origin *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[float](https://docs.python.org/3/builtins/functions.html#float), FieldInfo(annotation=NoneType, required=True, metadata=[\_PydanticGeneralMetadata(allow_inf_nan=False)])], [Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[float](https://docs.python.org/3/builtins/functions.html#float), FieldInfo(annotation=NoneType, required=True, metadata=[\_PydanticGeneralMetadata(allow_inf_nan=False)])]] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The point of the art that the entity’s placement (`stage.at`) refers
to, in view_box units (an#338). Unset, the rig is placed by the centre
of its bones’ extent ([`bone_extent_centre()`](#an.stage.rig.bone_extent_centre)), which is what every
rig did before the field existed; a prop declares its foot (a tripod’s,
a figurine’s stand) so it stands where it is put whatever its extent.

#### rest_rotation *: [bool](https://docs.python.org/3/builtins/functions.html#bool) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Whether the bones’ `rotation_deg`/`scale_x`/`scale_y` pose the
built parts (an#339). Unset (or `True`) they do: the rest pose is the
bones’. `False` is written ONLY by the migration onto a document from
before that rule whose bones carry a rotation or scale, because such a
rig was drawn with the pose already in its pixels (the fields were
ignored) and applying them now would pose it twice
([`protect_legacy_rest_pose()`](#an.stage.rig.protect_legacy_rest_pose)).

### *exception* an.stage.rig.RigError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A rig cannot be built as declared (a cycle, or a chain the stage cannot draw).

### *class* an.stage.rig.RigModel(\*\*data)

Bases: `BaseModel`

Common config: forward-compatible reads, strict writes.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.stage.rig.SCENE_PX_PER_VIEW_BOX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 345.0*

Scene-graph pixels spanned by a descriptor’s full `view_box` height.

The single number that maps descriptor space to scene space. One uniform
factor `k = SCENE_PX_PER_VIEW_BOX / view_box_height` scales bone positions
and part extents alike — uniform by construction, so the compiler cannot
violate the invariant that aspect ratio is intrinsic to the art (an#74).

345 is a calibration, not a preference. It is what reproduces the framing the
seven deleted `_SVG_*_SIZE` constants hand-tuned: at k = 345/1024 = 0.3369,
`saturated-rig`’s own art gives torso 107.8x129.4 against the old 110x130,
legs 37.7x118.6 against 38x120. The constants were an approximation of
exactly this product, which is the evidence that the rig should have been
driving it all along.

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

### an.stage.rig.art_src(ref, rel_path, , art_prefix='characters/')

Path used inside the runtime dir, relative to `index.html`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> art_src("maya", "parts/head.svg")
'characters/maya/parts/head.svg'
>>> art_src("lamp", "parts/body.svg", art_prefix="props/")
'props/lamp/parts/body.svg'
```

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

### an.stage.rig.bone_extent_centre(bones)

The DEFAULT point in view_box space that the entity’s placement refers
to, when the rig declares no [`RigDocument.origin`](#an.stage.rig.RigDocument.origin) ([`rig_origin()`](#an.stage.rig.rig_origin)).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> bone_extent_centre({"root": (512.0, 980.0), "head": (512.0, 420.0)})
(512.0, 700.0)
```

The centre of the rig’s bone extent, **not** the root bone. The scene root
positions a character on x only and leaves y at 0, so this point is what
lands at the frame’s vertical centre — and a rig whose root is its ground
contact (the default puts it at the feet, y=980) would therefore hang its
whole body above the placement point, head off-frame.

Centring on the extent makes framing independent of where an author chose
to put the root, which is a rigging decision and should not be a framing
one. On the default rig it lands at y=700, within 20 units of the torso
bone — i.e. it reproduces the convention the deleted `torso_y = 0.0`
literal encoded, without hardcoding a bone name.

### an.stage.rig.bone_positions(desc)

Absolute `(x, y)` per bone, in view_box units.

Bone transforms are parent-relative, so a bone’s position is the sum along
its parent chain. A cycle or a dangling parent stops the walk rather than
looping — a malformed rig is #78’s business, not this function’s.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.stage.rig.bones_carry_a_rest_pose(doc)

Whether any bone of a (raw or model) rig document has a non-zero
`rotation_deg` or a non-unit `scale_x`/`scale_y`.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> bones_carry_a_rest_pose({"bones": [{"name": "a"}, {"name": "b", "rotation_deg": 22}]})
True
>>> bones_carry_a_rest_pose({"bones": [{"name": "a", "scale_x": 1.0}]})
False
```

### an.stage.rig.build_rig_subtree(entity, desc_data, , textures, probe=None, resolutions=None, art_prefix='characters/', descriptor_model, document_kind, texture_srcs=None, digest=None, skip_slots=None)

Build the scene subtree for a rig (a prop or a character), **from its descriptor**.

Slots nest by [`slot_parent_chain()`](#an.stage.rig.slot_parent_chain) (`nesting: flat` or `bones`,
an#340). In `bones` mode a nested part is placed relative to its parent
BONE, without inheriting the parent’s attachment offset, and its bone’s
rest pose composes through the chain.

`skip_slots` are slots the GENRE says not to build (the cut-out genre’s
baked face: `cutan.characters.play.suppressed_slots`); a skipped slot’s
nested parts are not built either. `None` is the legacy rule for a genre
that predates the argument (`an.genres.API_LEVEL` < 5): with
`face_overlay` false, the slots nested under the `head` bone’s primary
slot. It is the one place the core still names a bone, and it goes when no
genre needs it.

A part may be SVG or raster (PNG/JPEG/WebP, an#211): the probe measures
either, and `digest(src)` — a content digest for raster art, `None`
for SVG — is appended to a raster texture’s alias so the texture is
addressed by its bytes.

**Every swap key keeps its own geometry** (an#211). A swap re-textures the
sprite, and the box, anchor and offset were the DEFAULT attachment’s, so a
key drawn on a different canvas was fitted into the wrong box — a closed
mouth on a thin canvas squashed every open mouth to a fraction of a pixel.
A key whose box, anchor or offset differs from the drawn attachment’s is
listed in `VisualJSON.asset_geometry` and the runtime applies it with the
texture; a rig whose keys share a canvas emits nothing new.

`texture_srcs` maps a part path to the `src` its texture loads from
instead of the stored file — a style pack’s recoloured art
(`_recoloured_texture_srcs()`). Such a texture’s alias carries a digest
of its content, so a different recolour is a different texture (the
runtime’s loader ignores a re-added alias on hot reload, an#155). The part
is still probed and sized from the stored file, whose geometry is the same.

Every part’s position comes from a bone, every part’s extent from its own
art, and both are scaled by one uniform factor. Nothing here is a module
constant: the seven `_SVG_*_SIZE` values and the four y-offset literals
this replaced are gone, and gutting `bones`/`slots`/`skins`/`view_box`
now changes the output — which it provably did not before (an#73).

A slot whose art is not on disk is recorded in `resolutions` as a fallback,
which makes it audible by default and fatal under `strict_assets` — the
same treatment a missing *character* already got (an#33), now reaching
inside the descriptor to the individual part (an#76). It is recorded rather
than raised here because the decision belongs to one place, and that place
is `_raise_or_warn_on_asset_fallbacks()`.

`probe(src) -> (exists, size)` answers whether a part’s art is on disk and
what size it rasterises at. Existence decides whether a texture is declared
at all. The sprite’s box is the attachment’s declared `width`/`height`
when it has them — **a declared size wins**, with the art’s aspect kept
(`an.characters.schema.attachment_box()`, an#220) — else the art’s own
extent (a raster’s pixel count); failing both, the runtime’s `contain`
fit draws the art at its natural shape — never stretched to a fabricated box.

* **Return type:**
  [`NodeJSON`](an.stage.serialize.html.md#an.stage.serialize.NodeJSON)

### an.stage.rig.chain_draw_order_problems(desc)

Where a nested chain asks the STAGE for a draw order it cannot give (an#340, an#403).

The stage sorts the items of each container ([`chain_paint_order()`](#an.stage.rig.chain_paint_order)), so
a part nested under one drawn LATER is fine (a far arm behind its torso).
What it cannot do is interleave two containers: a slot’s subtree is always
painted together, so an unrelated part ordered between a chain’s members
(a leg between the arms and the head) cannot be honoured. Refused by the
stage compiler; the asset validators only warn. Nothing in `flat`
nesting.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from types import SimpleNamespace as NS
>>> rig = NS(nesting="bones",
...          bones=[NS(name="arm", parent=None), NS(name="hand", parent="arm"), NS(name="cord", parent=None)],
...          slots=[NS(name="arm", bone="arm", draw_order=1), NS(name="cord", bone="cord", draw_order=2),
...                 NS(name="hand", bone="hand", draw_order=3)])
>>> chain_draw_order_problems(rig)[0].startswith("the stage paints each chain's parts together")
True
```

### an.stage.rig.chain_paint_order(desc, , built=None)

How each container of a nested chain must order what it holds (an#403).

The stage draws a container’s items in order: its slot’s own visual and its
child slots’ containers (`None` is the entity’s container, which holds the
root slots and no visual of its own). Sorting those siblings (PixiJS’s
`sortableChildren` on a `zIndex`) gives any order in which every slot’s
SUBTREE is painted contiguously, a far arm behind the torso it nests under
included. Each item spans the draw orders of its subtree; the items are
sorted, stably, by that `(lowest, highest)` span, starting from the
builder’s own order ([`natural_paint_order()`](#an.stage.rig.natural_paint_order)), so equal draw orders keep
their tree order and a chain already painted in declared order is not
reordered. `built` limits it to the slots the builder drew.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> from types import SimpleNamespace as NS
>>> rig = NS(nesting="bones",
...          bones=[NS(name="torso", parent=None), NS(name="arm", parent="torso")],
...          slots=[NS(name="torso", bone="torso", draw_order=2), NS(name="arm", bone="arm", draw_order=1)])
>>> chain_paint_order(rig)
{None: ['torso'], 'torso': ['arm', 'torso']}
```

### an.stage.rig.chain_pose_problems(desc)

A rest pose the stage cannot apply in a nested chain (an#340).

A node exists only for a bone that carries a slot. A bone with NO slot
between a part and the part it nests under has no node to rotate or
scale, so its `rotation_deg`/`scale_*` would be lost (its `x`/`y`
are kept: positions sum along the chain). Refused at compile, like the
draw order; give the bone a slot or move its pose to the bone below it.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from types import SimpleNamespace as NS
>>> rig = NS(nesting="bones", slots=[NS(name="arm", bone="arm"), NS(name="hand", bone="hand")],
...          bones=[NS(name="arm", parent=None), NS(name="elbow", parent="arm", rotation_deg=-70),
...                 NS(name="hand", parent="elbow")])
>>> chain_pose_problems(rig)[0].startswith("bone 'elbow' carries no slot")
True
```

### an.stage.rig.declared_origin(desc)

The rig’s DECLARED origin as two floats, or `None` when it declares none.

`desc` is a model or a raw document (a mapping, as `an validate` reads
it); a descriptor model that predates [`RigDocument`](#an.stage.rig.RigDocument), where
`origin` is an `extra` key (a list), is read the same way.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> from types import SimpleNamespace as NS
>>> declared_origin(NS(origin=[512, 1010])), declared_origin(NS())
((512.0, 1010.0), None)
>>> declared_origin({"origin": [0, 5]})
(0.0, 5.0)
```

### an.stage.rig.drawn_attachment(desc, skin, slot)

The `(name, attachment)` a slot draws by default, or `None`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Attachment`](#an.stage.rig.Attachment)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.stage.rig.legacy_rest_pose_unknown(raw, kind, , since)

The builder guard (an#339): whether `raw` may be a pre-rest-pose
document that its migration could not see.

`DocumentKind.version_of` reads a document with no version field as
CURRENT, so the protective migration never runs on it. A document like
that whose bones carry a pose, and which says nothing about
`rest_rotation`, is built flat (as it would have been) and warned
about. A version older than `since` is caught too, should a read skip
the migration.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> k = DocumentKind("Demo", "schema_version", "0.2.0")
>>> legacy_rest_pose_unknown({"bones": [{"name": "a", "rotation_deg": 9}]}, k, since="0.2.0")
True
>>> legacy_rest_pose_unknown({"schema_version": "0.2.0", "bones": [{"name": "a", "rotation_deg": 9}]}, k, since="0.2.0")
False
```

### an.stage.rig.natural_paint_order(order, keys)

What each container holds in the builder’s own order: the slot’s visual
first, then its children by their own `(draw_order, name)`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.stage.rig.nesting_of(desc)

`"flat"` or `"bones"` (an#340); unset is flat.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> nesting_of({"nesting": "bones"}), nesting_of({})
('bones', 'flat')
```

### an.stage.rig.omit_unset_rig_fields(data)

Drop every unset [`RigDocument`](#an.stage.rig.RigDocument) field from a dumped document, in place.

A subclass that declares its own `model_serializer` REPLACES the base’s
(pydantic keeps one per model), so it must call this on its output, or an
unset `origin` reaches every stored descriptor as `null`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> omit_unset_rig_fields({"name": "lamp", "origin": None})
{'name': 'lamp'}
>>> omit_unset_rig_fields({"origin": [512.0, 1010.0]})
{'origin': [512.0, 1010.0]}
```

### an.stage.rig.part_probe(characters_store, , art_prefix='characters/')

A probe answering `(art exists, the size it rasterises at)` for a part.

**Two questions, deliberately not one.** Whether the art is *there* decides
whether the compiler declares a texture for it; whether it can be *measured*
decides only whether the sprite’s box comes from the art or from the
runtime’s fit. Collapsing them is a real bug and it was here: a degenerate
`<svg/>` is unmeasurable but present, and treating that as absent made the
part vanish from the scene silently — trading an#79’s hang for exactly the
invisible-art failure #76 exists to stop.

Returns `None` when the store has no filesystem root — **not** a probe
that answers “absent” — because a store that can answer nothing must drop
no parts rather than all of them.

Size is read from the SVG root’s `width`/`height`, falling back to the
viewBox extent as a browser does — or, for PNG/JPEG/WebP art, from the
image header (an#211): a header parse, not a render, either way. Before
an#211 a PNG was parsed AS SVG here and the compile died on an XML error.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`bool`](https://docs.python.org/3/builtins/functions.html#bool), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)]]]

### an.stage.rig.primary_slot_per_bone(desc)

`{bone name: the slot that IS that bone}`, when one exists.

The anchor of node nesting ([`slot_parent_chain()`](#an.stage.rig.slot_parent_chain)). In the default
`flat` nesting the rigs are flat — arms are siblings of the torso, not
children (CLAUDE.md pillar 4) — so bone parentage decides *position* only:
a slot nests under the primary slot of its own bone when it is not that
slot itself, which puts eyes and mouth under `head` and leaves every limb
a direct child of the entity. `nesting: bones` (an#340) follows the bone
hierarchy to the nearest ancestor’s primary slot instead.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from types import SimpleNamespace as NS
>>> primary_slot_per_bone(NS(slots=[NS(name="head", bone="head"), NS(name="mouth", bone="head")]))["head"]
'head'
```

### an.stage.rig.protect_legacy_rest_pose(doc)

The migration step every rig kind runs onto the version that applies the rest pose (an#339).

Before it, a bone’s `rotation_deg` and scale reached no node, so a rig
whose bones carry one was drawn with that pose in its pixels. Such a
document gets `rest_rotation: false` and keeps its picture; a document
whose bones carry none gets nothing (and every document on the
maintainer’s machine was of that kind when this shipped). Returns `doc`,
edited in place; the caller sets the version.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> protect_legacy_rest_pose({"bones": [{"name": "leg", "rotation_deg": -22}]})["rest_rotation"]
False
>>> "rest_rotation" in protect_legacy_rest_pose({"bones": [{"name": "root"}]})
False
>>> protect_legacy_rest_pose({"bones": [{"name": "leg", "rotation_deg": 5}], "rest_rotation": True})["rest_rotation"]
True
```

### an.stage.rig.raster_digest(store, , art_prefix='characters/')

`digest(src)`: a short content digest for RASTER art, else `None`.

A raster texture is addressed by its bytes (an#211): the digest goes into
the texture’s alias, so a re-carved part is a different texture — the
runtime’s loader ignores a re-added alias on hot reload (an#155) — and a
different compiled contract, whose hash then covers the pixels drawn. SVG
art keeps its plain alias, which is what keeps every existing document
byte-identical.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### an.stage.rig.register_rest_pose_migration(kind, from_version, to_version)

Register the protective rest-pose step for one rig kind (an#339).

One call from the module that owns the kind’s schema (`an.stage.props`
for `PropDescriptor`, `cutan` for `CharacterDescriptor`): it registers
[`protect_legacy_rest_pose()`](#an.stage.rig.protect_legacy_rest_pose) as that kind’s `from -> to` migration and
records `to` as the version the builder applies the rest pose from.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> register_rest_pose_migration("DemoRig", "1.0", "2.0")
>>> REST_POSE_SINCE["DemoRig"]
'2.0'
>>> from an.ir.migrate import MIGRATIONS
>>> MIGRATIONS[("DemoRig", "1.0", "2.0")]({"version": "1.0", "bones": []})
{'version': '1.0', 'bones': []}
```

### an.stage.rig.rest_pose_protection(raw, migrated, , kind='rig document')

What to say when the MIGRATION, on this read, kept a rig’s pose unapplied (an#407).

The protective step writes `rest_rotation: false` onto a document from
before the rest pose whose bones carry one, guessing the pose is already in
its pixels. An author who added a rotation to such a file is the other
case, and nothing else would tell them why the part did not move. A flag
the AUTHOR wrote (present in the stored document) is a choice, and silent.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> old = {"schema_version": "0.1.0", "bones": [{"name": "leg", "rotation_deg": 20}]}
>>> rest_pose_protection(old, {**old, "rest_rotation": False}).startswith("its bones carry")
True
>>> rest_pose_protection({**old, "rest_rotation": False}, {**old, "rest_rotation": False}) is None
True
```

### an.stage.rig.rest_transform(bone)

The node transform fields a bone’s rest pose sets (an#339): its
`rotation_deg` in radians and its scales, `-0.0` normalised to `0.0`.

Every rest reader composes on the built transform (`play` deviations,
swap poses, the face solver, presets, a from-less tween, the runtime’s
load), so this is the whole change. An authored `rotation` tween stays
ABSOLUTE: `to: 0` straightens a part whose rest is splayed.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> rest_transform(Bone(name="leg", rotation_deg=-22))["rotation"]
-0.3839724354387525
>>> rest_transform(Bone(name="leg", rotation_deg=-0.0))
{'rotation': 0.0, 'scale_x': 1.0, 'scale_y': 1.0}
```

### an.stage.rig.rig_affordances(desc)

What a rig’s structure affords, derived from the rig model (an#340).

`rig.hierarchy` when the rig nests in `bones` mode and some chain links
two different bones: `keys` are every slot in such a chain (so
`rig.hierarchy:forearm_l` asks for a forearm in a chain), `count` the
deepest chain’s number of BONES (`rig.hierarchy>=3` is “a shoulder, an
elbow and a hand”), `chains` every root-to-leaf chain of slots. Parts on
one bone (a head with its face) add no depth, and a flat rig affords
nothing here: that nesting is a drawing convention, not a joint. The core registers it as the `prop`
analyser; a genre’s analyser composes it for its own kinds.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

```pycon
>>> from types import SimpleNamespace as NS
>>> rig = NS(nesting="bones", bones=[NS(name="arm", parent=None), NS(name="hand", parent="arm")],
...          slots=[NS(name="arm", bone="arm"), NS(name="hand", bone="hand"), NS(name="sword", bone="hand")])
>>> rig_affordances(rig)
{'rig.hierarchy': {'keys': ['arm', 'hand', 'sword'], 'count': 2, 'chains': [['arm', 'hand', 'sword']]}}
```

### an.stage.rig.rig_origin(desc)

The point of the rig, in view_box units, that lands at the entity’s placement.

The ONE rule (an#338): the declared [`RigDocument.origin`](#an.stage.rig.RigDocument.origin) when the rig
has one, else the centre of its bones’ extent ([`bone_extent_centre()`](#an.stage.rig.bone_extent_centre)).
[`build_rig_subtree()`](#an.stage.rig.build_rig_subtree) places every part relative to it, and a genre that
reports where a rig’s art reaches from its stage point (`cutan`’s
`stage_extent`) reads it too, so the two agree by construction.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> from types import SimpleNamespace as NS
>>> bones = [NS(name="root", parent=None, x=512, y=980), NS(name="top", parent="root", x=0, y=-560)]
>>> rig_origin(NS(bones=bones))
(512.0, 700.0)
>>> rig_origin(NS(bones=bones, origin=(512, 980)))
(512.0, 980.0)
```

### an.stage.rig.rig_origin_problems(desc)

What is wrong with a rig’s declared origin, as warnings (an#338).

Nothing when the rig declares none. A non-finite origin (possible only on a
document read without [`RigDocument`](#an.stage.rig.RigDocument), which refuses one) places the
whole rig nowhere; one outside the `view_box` is legal (a hanging sign’s
hook can sit above its art) but is far more often a unit slip (scene pixels
written where view_box units belong), so it is said, not refused.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from types import SimpleNamespace as NS
>>> rig_origin_problems(NS(origin=(512, 1010), view_box=(0, 0, 1024, 1024)))
[]
>>> rig_origin_problems(NS(origin=(512, 2000), view_box=(0, 0, 1024, 1024)))[0].startswith("origin (512.0, 2000.0) lies outside")
True
>>> rig_origin_problems(NS(origin=(float("nan"), 0), view_box=(0, 0, 1024, 1024)))[0][:30]
'origin (nan, 0.0) is not finit'
```

### an.stage.rig.rig_problems(desc)

What is structurally wrong with a rig’s bones and slots (an#340).

A bone whose `parent` names no bone; a cycle in the bone graph (the one
form a closed linkage can take in a model where each bone names one
parent: forward kinematics only, so it is refused); a slot whose `bone`
names no bone (it used to land at the origin, silently). Shared by the
asset validators (`an character validate`, `an.stage.props.validate_prop()`).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from types import SimpleNamespace as NS
>>> rig_problems(NS(bones=[NS(name="a", parent="b"), NS(name="b", parent="a")],
...                 slots=[NS(name="s", bone="nope")]))
['bones form a cycle (a closed linkage): a -> b -> a; a rig is a tree (forward kinematics only)', "slot 's' is bound to bone 'nope', which the rig does not declare"]
```

### an.stage.rig.rig_rest_problems(desc)

Warnings about a rig’s rest pose (an#339), on a model or a raw document.

A part turns about its NODE’s origin, which is the bone plus the drawn
attachment’s `x`/`y` offset. A bone with a rest rotation whose part is
offset therefore turns that part about a point that is not the joint, the
usual way a splayed leg ends up detached from its hip. The way to turn a
part about its joint is `x: 0, y: 0` on the attachment and the art’s
`anchor` at the joint. Nothing is said about a rig that keeps its legacy
pose (`rest_rotation: false`), since its bones pose nothing.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> doc = {"bones": [{"name": "leg", "rotation_deg": 20}],
...        "slots": [{"name": "leg", "bone": "leg"}],
...        "skins": {"default": {"slots": {"leg": {"leg": {"path": "p.svg", "y": 40}}}}}}
>>> rig_rest_problems(doc)[0].startswith("bone 'leg' rests at 20")
True
>>> doc["skins"]["default"]["slots"]["leg"]["leg"]["y"] = 0
>>> rig_rest_problems(doc)
[]
```

### an.stage.rig.slot_node_paths(desc)

`{slot: its node path relative to the entity}` (`torso/arm/hand`), by
[`slot_parent_chain()`](#an.stage.rig.slot_parent_chain); a slot caught in a cycle maps to its own name.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from types import SimpleNamespace as NS
>>> rig = NS(nesting="bones", bones=[NS(name="a", parent=None), NS(name="b", parent="a")],
...          slots=[NS(name="a", bone="a"), NS(name="b", bone="b")])
>>> slot_node_paths(rig)
{'a': 'a', 'b': 'a/b'}
```

### an.stage.rig.slot_parent_chain(desc)

`{slot: the slot it nests under, or None}`: THE nesting rule (an#340).

The builder and a genre’s part paths (`cutan`’s `play.slot_parent`,
`slot_node_path`) all read it, so a `play` or a preset addresses the
node the builder made.

- `flat` (unset): a slot nests under its own bone’s primary slot (the
  slot named like the bone) when it is not that slot; everything else is a
  child of the entity. Arms are siblings of the torso.
- `bones`: the same, and a slot that IS its bone’s primary (or whose bone
  has none) nests under the primary slot of the nearest ANCESTOR bone that
  has one, to any depth. A bone cycle stops the walk; `rig_problems`
  names it and the builder refuses it.

```pycon
>>> from types import SimpleNamespace as NS
>>> rig = NS(bones=[NS(name="arm", parent="torso"), NS(name="hand", parent="arm"),
...                 NS(name="torso", parent=None)],
...          slots=[NS(name="torso", bone="torso"), NS(name="arm", bone="arm"),
...                 NS(name="hand", bone="hand"), NS(name="sword", bone="hand")])
>>> slot_parent_chain(rig)
{'torso': None, 'arm': None, 'hand': None, 'sword': 'hand'}
>>> rig.nesting = "bones"
>>> slot_parent_chain(rig)
{'torso': None, 'arm': 'torso', 'hand': 'arm', 'sword': 'hand'}
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]
