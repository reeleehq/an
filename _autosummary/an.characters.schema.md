# an.characters.schema

Character descriptor schema (Spine-shaped, Pydantic v2).

A character on disk lives at:

```default
characters/<name>/
    <name>.svg              # optional canonical layered SVG
    character.json          # CharacterDescriptor as JSON
    parts/
        head.svg
        torso.svg
        arm_l.svg, arm_r.svg
        leg_l.svg, leg_r.svg
        eye_l_open.svg, eye_l_closed.svg, eye_r_open.svg, eye_r_closed.svg
        brow_l.svg, brow_r.svg
        mouth/mouth_a.svg … mouth_h.svg, mouth_x.svg
```

The descriptor borrows Spine’s separation of concerns:

- **bones** — where things attach. Local transforms relative to a parent.
- **slots** — what is drawn at each bone (one attachment active at a time).
- **skins** — for each slot, the named attachments and their SVG paths.
- **asset_sets** — `{channel: {key: attachment_name}}`. What a swap key
  *selects*, layered over `skins`, which says what art *exists*. The
  `viseme` channel is Rhubarb’s shape letter → an attachment on the `mouth`
  slot. (Replaced `viseme_map` in schema 0.2.0.)
- **animations** — built-in idle loops (breath, blink) keyed by name.

A slot’s name **is** its scene-graph node name, which is why the face slots read
`left_eye` rather than `eye_l`; attachment names are a separate, per-slot
namespace — file-derived for single-attachment slots, and shared key-like names
(`open`/`closed` on both eye slots, 0.3.0) where one swap set must drive
several slots.

```pycon
>>> char = CharacterDescriptor(name="maya")
>>> char.asset_sets["viseme"]["A"]
'mouth_a'
>>> char.asset_sets["viseme"]["X"]
'mouth_x'
>>> char.view_box
(0, 0, 1024, 1024)
>>> sorted(char.skins["default"].slots.keys())[:3]
['arm_l', 'arm_r', 'head']
```

### Module Attributes

| [`CHARACTER_DOCUMENT_KIND`](#an.characters.schema.CHARACTER_DOCUMENT_KIND)   | The descriptor is a schema-versioned document in its own right, with its own version field.                                                                                                                                                                  |
|----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`MOUTH_SHAPES`](#an.characters.schema.MOUTH_SHAPES)              | Rhubarb mouth shapes.                                                                                                                                                                                                                                        |
| [`DEFAULT_VISEME_MAP`](#an.characters.schema.DEFAULT_VISEME_MAP)        | Default Rhubarb-letter → mouth-attachment-name mapping.                                                                                                                                                                                                      |
| [`VISEME_CHANNEL`](#an.characters.schema.VISEME_CHANNEL)            | The swap channel lip-sync drives.                                                                                                                                                                                                                            |
| [`EYELID_CHANNEL`](#an.characters.schema.EYELID_CHANNEL)            | The swap channel blinks drive.                                                                                                                                                                                                                               |
| [`DEFAULT_EYELID_MAP`](#an.characters.schema.DEFAULT_EYELID_MAP)        | Default eyelid-state → attachment-name mapping, shared by both eye slots.                                                                                                                                                                                    |
| [`VIEW_CHANNEL`](#an.characters.schema.VIEW_CHANNEL)              | one KEY per drawn view, projected onto the slots whose art changes with the view (the factory draws the head and the torso), each slot carrying attachments NAMED after the keys.                                                                            |
| [`VIEWS`](#an.characters.schema.VIEWS)                     | The views the factory draws, in turnaround order.                                                                                                                                                                                                            |
| [`DFLT_VIEW`](#an.characters.schema.DFLT_VIEW)                 | its default attachments ARE this view.                                                                                                                                                                                                                       |
| [`VIEW_VARIANT_SEP`](#an.characters.schema.VIEW_VARIANT_SEP)          | What joins a swap set's name to the view a variant of it serves: `eyelid@side` is the `eyelid` set drawn for the `side` view (an#220), the same separator the expression variants (`viseme@happy`, an#98) use.                                               |
| [`GAITS`](#an.characters.schema.GAITS)                     | `legs` swing about the hip in a profile and step up and down facing the camera; `hem` — the leg slots are the two halves of a robe's hem — tilts them in turn under a swaying, bobbing body; `rock` moves no leg at all (a blob, a sack) and rocks the body. |
| [`REQUIRED_PARTS`](#an.characters.schema.REQUIRED_PARTS)            | Required body parts.                                                                                                                                                                                                                                         |
| [`DEFAULT_VIEW_BOX`](#an.characters.schema.DEFAULT_VIEW_BOX)          | 1024x1024 with feet near y≈980.                                                                                                                                                                                                                              |
| [`SLOT_POSE_OFFSETS`](#an.characters.schema.SLOT_POSE_OFFSETS)         | The transform properties a [`SlotPose`](#an.characters.schema.SlotPose) sets, and whether each is an OFFSET added to the rest (in view_box units, so scaled by the rig), an ANGLE added to it (radians, never scaled) or a FACTOR on it.        |
| [`LEG_LENGTH`](#an.characters.schema.LEG_LENGTH)                | Hip to ground in the default rig, in view_box units.                                                                                                                                                                                                         |
| [`HEAD_ANCHOR`](#an.characters.schema.HEAD_ANCHOR)               | the head hangs above the neck, its lower ~fifth overlapping the collar.                                                                                                                                                                                      |
| [`REFERENCE_HEAD_HEIGHT`](#an.characters.schema.REFERENCE_HEAD_HEIGHT)     | The head height the default face layout is drawn for, in view_box units — the pre-Wave-4 compiler's 96 px head at k = 345/1024.                                                                                                                              |
| [`FACE_OFFSETS`](#an.characters.schema.FACE_OFFSETS)              | Where each face part sits relative to the `head` bone, in view_box units.                                                                                                                                                                                    |

### Functions

| [`attachment_box`](#an.characters.schema.attachment_box)(width, height, art)      | The box a part draws in, in view_box units: the declared size wins, the art's aspect is kept (an#220).                                                                                                                     |
|------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`bones_from_pivots`](#an.characters.schema.bones_from_pivots)(pivots, \*[, bones])  | Re-place a bone rig onto an illustrator's own joint coordinates.                                                                                                                                                           |
| [`default_asset_sets`](#an.characters.schema.default_asset_sets)()                    | `{channel: {key: attachment_name}}` for a freshly-built character.                                                                                                                                                         |
| [`view_variant_set`](#an.characters.schema.view_variant_set)(set_name, view)        | The name of `set_name`'s variant for `view` (an#220).                                                                                                                                                                      |
| [`view_variant_sets`](#an.characters.schema.view_variant_sets)(desc, \*[, view_set]) | `{base set: {view: variant set name}}` — every per-view face set the descriptor declares (an#220): a set named `<base>@<view>` where `<base>` is a declared set and `<view>` a key of its `view` set (or its `rest_view`). |

### Classes

| [`AnimationTrack`](#an.characters.schema.AnimationTrack)(\*\*data)      | A single channel inside an idle animation.                              |
|--------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`Attachment`](#an.characters.schema.Attachment)(\*\*data)          | A drawable: an SVG path + anchor point (in 0..1 per-axis units).        |
| [`Bone`](#an.characters.schema.Bone)(\*\*data)                | A skeleton joint with a local transform relative to its parent.         |
| [`CharacterDescriptor`](#an.characters.schema.CharacterDescriptor)(\*\*data) | The on-disk character schema.                                           |
| [`IdleAnimation`](#an.characters.schema.IdleAnimation)(\*\*data)       | A named idle loop (e.g., breath, blink).                                |
| [`Skin`](#an.characters.schema.Skin)(\*\*data)                | A named outfit/variant: maps slot → {attachment_name → Attachment}.     |
| [`Slot`](#an.characters.schema.Slot)(\*\*data)                | A draw-order slot bound to a bone, displaying one attachment at a time. |
| [`SlotPose`](#an.characters.schema.SlotPose)(\*\*data)            | How one slot is posed while a swap key is shown (`swap_poses`, an#197). |

### *class* an.characters.schema.AnimationTrack(\*\*data)

Bases: `_CharModel`

A single channel inside an idle animation.

The `target` is a path-string per the architecture pillar:

- `bone:<name>.<prop>` for bone transforms (`x`, `y`, `rotation_deg`,
  `scale_x`, `scale_y`).
- `slot:<name>.attachment` for swap animations (eyes blinking, mouth visemes).

For `type="sine"`: `amplitude` is the peak deviation; `phase` is in
cycles (0..1). For `type="step"` / `type="linear"`: `frames` is a
list of `[time_s, value]` pairs evaluated in order.

```pycon
>>> t = AnimationTrack(target="bone:torso.y", type="sine", amplitude=2.0)
>>> t.amplitude
2.0
```

#### model_config *: ClassVar[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.characters.schema.Attachment(\*\*data)

Bases: `_CharModel`

A drawable: an SVG path + anchor point (in 0..1 per-axis units).

```pycon
>>> a = Attachment(path="parts/head.svg", anchor=(0.5, 0.78))
>>> a.anchor
(0.5, 0.78)
```

#### anchor *: tuple[float, float]*

Anchor in 0..1 per-axis units (Pixi’s Sprite.anchor convention).

#### model_config *: ClassVar[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### source *: [AssetSource](an.ir.assets.md#an.ir.assets.AssetSource) | None*

Where THIS part’s art came from, when it is not the descriptor’s
`source` — a character composed from several clips, or a carved head
on a CC0 body, credits each (an#220). `None` = the descriptor’s
`source` covers it. `an credits` lists every one; an all-rights-
reserved part makes the render NOT PUBLISHABLE like any other.
Omitted from the stored document when unset.

#### width *: float | None*

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
[`attachment_box()`](#an.characters.schema.attachment_box).

#### x *: float*

Offset from the slot’s bone, in view_box units.

**This is where a part’s position lives**, and it is the reference data
model’s answer, not an invention: DragonBones puts it in
`display.transform`, Spine in the region attachment’s `{x, y}`, and
in both the *slot* carries no transform at all. It is what lets five face
parts share one `head` bone and still land in different places — before
this field they all stacked on the bone, because the descriptor had no
way to say otherwise and the compiler used hardcoded literals instead.

### *class* an.characters.schema.Bone(\*\*data)

Bases: `_CharModel`

A skeleton joint with a local transform relative to its parent.

```pycon
>>> b = Bone(name="head", parent="torso", x=0, y=-260, pivot="neck")
>>> b.parent
'torso'
```

#### model_config *: ClassVar[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### pivot *: str | None*

Optional pivot name — must match a circle in the SVG `skeleton` group.

### an.characters.schema.CHARACTER_DOCUMENT_KIND *: [DocumentKind](an.ir.md#an.ir.DocumentKind)* *= DocumentKind(name='CharacterDescriptor', version_field='schema_version', current_version='0.3.0')*

The descriptor is a schema-versioned document in its own right, with its own
version field. Registered here rather than in [`an.ir.migrate`](an.ir.md#an.ir.migrate) because
this module already imports from [`an.ir.assets`](an.ir.assets.md#module-an.ir.assets) — registering from the
other direction would close an import cycle, and because the package that
owns a schema is the one that knows its version field.

### *class* an.characters.schema.CharacterDescriptor(\*\*data)

Bases: `_CharModel`

The on-disk character schema. Saved as `character.json`.

The descriptor is the SSOT for a character’s identity, body part inventory,
pivot geometry, viseme map, and built-in idle behaviors. Binary art lives
as SVG sidecars referenced by `Attachment.path` (relative to the
descriptor file).

```pycon
>>> c = CharacterDescriptor(name="maya")
>>> c.schema_version == CHARACTER_SCHEMA_VERSION
True
>>> # all 9 mouths are wired into the default skin
>>> sorted(c.skins["default"].slots["mouth"].keys()) == [
...     'mouth_a', 'mouth_b', 'mouth_c', 'mouth_d',
...     'mouth_e', 'mouth_f', 'mouth_g', 'mouth_h', 'mouth_x',
... ]
True
>>> # round-trip
>>> raw = c.model_dump_json()
>>> back = CharacterDescriptor.model_validate_json(raw)
>>> back.name == c.name
True
```

#### asset_sets *: dict[str, dict[str, str]]*

`{channel: {key: attachment_name}}` — what a swap key SELECTS, layered
over `skins`, which is the SSOT for what art EXISTS. The indirection is
deliberate: a channel key is not an attachment name. Today’s viseme map
happens to be one-to-one (9 keys, 9 attachments), but real mouth charts
are many-to-one — ~10 drawings carrying ~40 phonemes — and collapsing the
two namespaces makes the first shared drawing a schema change instead of
a data change. Replaces `viseme_map` (schema 0.2.0).

#### colour_roles *: dict[str, dict[str, str]]*

Which colour literal in which part plays which `StylePack` role —
`{part path: {"#rrggbb": role}}`, e.g.
`{"parts/torso.svg": {"#a83249": "clothing"}}`. Written by the factory,
which KNOWS what it drew as skin or clothing; read by the compiler, which
rewrites the tagged literals under a pack (palette swapping — see
[`an.characters.colour_roles`](an.characters.colour_roles.md#module-an.characters.colour_roles)). Empty = untagged art (hand-drawn,
DiceBear): a pack cannot reach it and the compiler says so, because the
alternative is inferring a role from a pixel (an#99’s wrong-tone lid).
Additive: no schema bump, and a descriptor without it reads back as
untagged. Keys are normalised to lowercase `#rrggbb`; a role must be
one a pack can set ([`an.styles.REACHABLE_ROLES`](an.styles.md#an.styles.REACHABLE_ROLES)).

#### expression_binding *: list[dict[str, Any]] | None*

How expression axes reach this rig (an#98), as a list of binding dicts —
`{"axis", "slot", "property", "gain"[, "rig_scaled"]}` for a transform
channel, `{"axis", "slot", "set_family"}` for a swap set. `None` means
the default binding derived from the slots the rig has
([`an.expression.binding.default_binding()`](an.expression.binding.md#an.expression.binding.default_binding)). Additive: no schema bump,
and a pre-Wave-6 descriptor reads back unchanged.

#### face_overlay *: bool*

Whether this character’s face is drawn as separate overlay parts
(eyes, brows, mouth as their own slots — the default) or baked into the
head art (DiceBear / external avatars). `False` suppresses the face
overlay slots at rig build AND the viseme/emotion channels at dialogue
compile — a baked face has no overlay mouth to drive.

This is a **declared fact**, replacing the old vendor-name check on
`metadata.art_provenance` (an#87): provenance says where art came
from; this says what the art IS. The 0.2.0 → 0.3.0 migration derives it
from the provenance string once, and `art_provenance` reverts to pure
provenance/licensing metadata.

#### gait *: str | None*

This character’s default walk `gait` (one of [`GAITS`](#an.characters.schema.GAITS), an#220);
an author’s `gait` arg overrides it. `None` = `legs` when the rig
builds a leg pair, else `rock`. A robe figure whose leg slots are hem
halves declares `"hem"` once, here, rather than on every walk.
Omitted from the stored document when unset.

#### gaze_travel *: dict[str, float] | None*

How far a pupil may travel from its rest, in view-box units per axis
(an#99): the sclera’s clearance minus the pupil’s radius, written by
`an character add-gaze` from the parts it synthesized. `None` = the
rig has no pupil layer (gaze is a no-op on it) or uses the default
travel. The travel maps the gaze axes’ unit circle onto the sclera’s
inner ellipse; the compiler clamps the summed (x, y) to 0.95 of that
circle, which keeps the whole pupil disc inside the white at every
angle (a per-axis box pokes out at the diagonal) — no runtime mask.

#### metadata *: dict[str, Any]*

Free-form metadata (dicebear style/seed, etc.). Schema-evolution
friendly: anything an external tool wants to record can land here.

This comment used to say “art license, etc.” — an invitation nothing ever
took up. Rights live in `source` now, typed, so they can be found.

#### model_config *: ClassVar[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### model_post_init(\_CharacterDescriptor_\_context)

Override this method to perform additional initialization after `__init__` and `model_construct`.
This is useful if you want to do some validation that requires the entire model to be initialized.

* **Return type:**
  `None`

#### rest_view *: str | None*

The view the DEFAULT art is drawn in (an#220) — a declared fact about
the art, like `face_overlay`. `None` means [`DFLT_VIEW`](#an.characters.schema.DFLT_VIEW)
(front). A character carved from a profile (a silhouette film, a side-
on figure) says `"side"`, and everything that asks which view is in
force before any turn — `walk` swinging its legs rather than lifting
them — reads it instead of the author passing `view: side` by hand.
Omitted from the stored document when unset.

#### source *: [AssetSource](an.ir.assets.md#an.ir.assets.AssetSource) | None*

Where this character’s art came from, and what its licence obliges.

`None` means “we made this” — not “unknown”. Anything acquired should
carry one, because a licence defect is the only failure that reaches
BACKWARDS through completed work: a video shipped with an unattributed
CC BY asset cannot be un-shipped.

Field names match `illustration.ImageResult` exactly, so an adapter is a
dict copy rather than a rename table — and a rename table is where a field
quietly stops being carried. Pinned by test.

#### source_svg *: str | None*

Optional source SVG (relative path) that the parts/ folder was
extracted from. Useful for re-slicing.

#### swap_poses *: dict[str, dict[str, dict[str, [SlotPose](#an.characters.schema.SlotPose)]]]*

{slot:
SlotPose}}}\`\` (an#197). A `set` of a swap set on the ENTITY itself
(`{kind: set, target: maya, property: view, value: side}`) fans the
key out to every slot the set projects onto AND poses the slots listed
under that key; a slot listed under another key of the set returns to
rest. That is how one key turns a whole character: the head and torso
swap art, the far eye and arm hide, the mouth slides to the profile
edge — while blinks, gaze and lip-sync keep running on what is visible
(the face solver folds a pose into its own channels). Additive: no
schema bump, and a descriptor without it reads back unposed.

* **Type:**
  How slots are POSED while a swap key shows — 

  ```
  ``
  ```

  {set
* **Type:**
  {key

#### voice_ref *: str | None*

Voice-store id or path used by the audio pipeline. Optional; the scene
can override per shot.

### an.characters.schema.DEFAULT_EYELID_MAP *: dict[str, str]* *= {'CLOSED': 'closed', 'OPEN': 'open'}*

Default eyelid-state → attachment-name mapping, shared by both eye slots.

### an.characters.schema.DEFAULT_VIEW_BOX *: tuple[int, int, int, int]* *= (0, 0, 1024, 1024)*

1024x1024 with feet near y≈980. All parts
inherit this viewBox at export so PixiJS can use the SVG’s intrinsic
viewBox without a calibration step.

* **Type:**
  Canonical character viewBox

### an.characters.schema.DEFAULT_VISEME_MAP *: dict[str, str]* *= {'A': 'mouth_a', 'B': 'mouth_b', 'C': 'mouth_c', 'D': 'mouth_d', 'E': 'mouth_e', 'F': 'mouth_f', 'G': 'mouth_g', 'H': 'mouth_h', 'X': 'mouth_x'}*

Default Rhubarb-letter → mouth-attachment-name mapping. Uppercase keys
because Rhubarb emits A-X; lowercase attachment names by convention.

### an.characters.schema.DFLT_VIEW *: str* *= 'front'*

its default attachments ARE this view.
A descriptor whose art is drawn in another view says so in `rest_view`.

* **Type:**
  The view a character shows at rest

### an.characters.schema.EYELID_CHANNEL *: str* *= 'eyelid'*

The swap channel blinks drive. One set serves BOTH eye slots because the
eye slots share per-slot attachment names (`open` / `closed`) — the 0.3.0
migration renamed them from the file-derived `eye_l_open` spelling for
exactly this: a set’s keys are looked up per slot, so slots that a single
channel must drive together need attachment names in common.

### an.characters.schema.FACE_OFFSETS *: dict[str, tuple[float, float]]* *= {'left_brow': (-41.6, -133.2), 'left_eye': (-41.6, -97.6), 'mouth': (0.0, -38.2), 'right_brow': (41.6, -133.2), 'right_eye': (41.6, -97.6)}*

Where each face part sits relative to the `head` bone, in view_box units.

All five share one bone, so without a per-attachment offset they stack on it.
These are the compiler’s four deleted hardcoded pairs converted at
k = 345/1024 — i.e. the same picture, now expressed where an illustrator can
change it. Those pairs were relative to the head’s CENTRE (the old compiler
anchored the head at 0.5); the bone is the NECK, and the head hangs above it
at [`HEAD_ANCHOR`](#an.characters.schema.HEAD_ANCHOR), so each pair is lifted by the centre’s height above
the neck. Unlifted, the mouth sat below the neck — on the torso (an#168).

### an.characters.schema.GAITS *: tuple[str, ...]* *= ('legs', 'hem', 'rock')*

`legs`
swing about the hip in a profile and step up and down facing the camera;
`hem` — the leg slots are the two halves of a robe’s hem — tilts them in
turn under a swaying, bobbing body; `rock` moves no leg at all (a blob, a
sack) and rocks the body.

* **Type:**
  How a character walks (`an.motion.walk`’s `gait`, an#220)

### an.characters.schema.HEAD_ANCHOR *: tuple[float, float]* *= (0.5, 0.78)*

the head hangs above the neck, its lower
~fifth overlapping the collar.

* **Type:**
  The head’s anchor on the neck bone

### *class* an.characters.schema.IdleAnimation(\*\*data)

Bases: `_CharModel`

A named idle loop (e.g., breath, blink).

```pycon
>>> a = IdleAnimation(name="idle_breath", duration=4.0)
>>> a.loop
True
```

#### model_config *: ClassVar[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.characters.schema.LEG_LENGTH *: float* *= 300.0*

Hip to ground in the default rig, in view_box units. The torso bone (the
hip) and both leg bones sit this far above the root (the ground contact), so
a leg drawn this long reaches the ground. The factory draws its legs to it.

### an.characters.schema.MOUTH_SHAPES *: tuple[str, ...]* *= ('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'x')*

Rhubarb mouth shapes. A-F are mandatory in Rhubarb’s basic set; G/H/X
are emitted when `--extendedShapes GHX` is on (Rhubarb’s default).
We always ship all 9 so the renderer never has to fall back.

### an.characters.schema.REFERENCE_HEAD_HEIGHT *: float* *= 285.0*

The head height the default face layout is drawn for, in view_box units —
the pre-Wave-4 compiler’s 96 px head at k = 345/1024. The factory writes its
head art at this height, so [`FACE_OFFSETS`](#an.characters.schema.FACE_OFFSETS) lands on the face.

### an.characters.schema.REQUIRED_PARTS *: tuple[str, ...]* *= ('head', 'torso', 'arm_l', 'arm_r', 'leg_l', 'leg_r', 'eye_l_open', 'eye_l_closed', 'eye_r_open', 'eye_r_closed', 'brow_l', 'brow_r')*

Required body parts. A character missing any of these can’t be rendered
as a full puppet; `validate_character` flags the gap.

### an.characters.schema.SLOT_POSE_OFFSETS *: tuple[str, ...]* *= ('x', 'y')*

The transform properties a [`SlotPose`](#an.characters.schema.SlotPose) sets, and whether each is an
OFFSET added to the rest (in view_box units, so scaled by the rig), an
ANGLE added to it (radians, never scaled) or a FACTOR on it.

### *class* an.characters.schema.Skin(\*\*data)

Bases: `_CharModel`

A named outfit/variant: maps slot → {attachment_name → Attachment}.

```pycon
>>> skin = Skin(name="default", slots={"mouth": {"mouth_a": Attachment(path="parts/mouth/mouth_a.svg")}})
>>> skin.slots["mouth"]["mouth_a"].path
'parts/mouth/mouth_a.svg'
```

#### model_config *: ClassVar[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.characters.schema.Slot(\*\*data)

Bases: `_CharModel`

A draw-order slot bound to a bone, displaying one attachment at a time.

```pycon
>>> s = Slot(name="mouth", bone="head", draw_order=7, attachment="mouth_x")
>>> s.attachment
'mouth_x'
```

#### attachment *: str | None*

Default attachment name; the active attachment can change at runtime
via animation tracks targeting `slot:<name>.attachment`.

#### model_config *: ClassVar[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.characters.schema.SlotPose(\*\*data)

Bases: `_CharModel`

How one slot is posed while a swap key is shown (`swap_poses`, an#197).

Relative to the slot’s REST, so one pose serves every placement: `x`/`y`
are added (view_box units, like an attachment offset), `rotation` is
added too (radians, about the slot’s own pivot — how a profile splays its
legs so both show), `scale_x`, `scale_y` and `alpha` multiply.
`alpha: 0` is how a view HIDES a slot — the back view hides the face —
which is a property of the view, never an author’s alpha hack on node
paths guessed by trial.

```pycon
>>> SlotPose(alpha=0).alpha, SlotPose().x, SlotPose().rotation
(0.0, 0.0, 0.0)
```

#### model_config *: ClassVar[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.characters.schema.VIEWS *: tuple[str, ...]* *= ('front', 'three_quarter', 'side', 'back')*

The views the factory draws, in turnaround order. `side` is a profile
facing the viewer’s RIGHT at a positive `scale_x`; a negative `scale_x`
(`an.motion.turn(direction="left")`) mirrors it to face left.

### an.characters.schema.VIEW_CHANNEL *: str* *= 'view'*

one KEY per drawn view, projected
onto the slots whose art changes with the view (the factory draws the head
and the torso), each slot carrying attachments NAMED after the keys. A
conventional name, like `viseme` — nothing in the compiler or the runtime
reads it; `an.motion.turn` is the one writer that defaults to it.

* **Type:**
  The swap set a turnaround rides (an#197)

### an.characters.schema.VIEW_VARIANT_SEP *: str* *= '@'*

What joins a swap set’s name to the view a variant of it serves:
`eyelid@side` is the `eyelid` set drawn for the `side` view (an#220),
the same separator the expression variants (`viseme@happy`, an#98) use.

### an.characters.schema.VISEME_CHANNEL *: str* *= 'viseme'*

The swap channel lip-sync drives. `viseme` is a conventional set name, not
a special case in control flow (an#87): the compiler projects EVERY
`asset_sets` channel onto the slots whose attachments its keys name, and
the runtime applies any projected channel the same way.

### an.characters.schema.attachment_box(width, height, art)

The box a part draws in, in view_box units: the declared size wins, the
art’s aspect is kept (an#220).

* **Return type:**
  `tuple`[`float`, `float`] | `None`

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

### an.characters.schema.bones_from_pivots(pivots, , bones=None)

Re-place a bone rig onto an illustrator’s own joint coordinates.

Each [`Bone`](#an.characters.schema.Bone) already declares the joint it stands for
(`head` -> `neck`, `arm_l` -> `shoulder_l`, …), and
[`extract_pivots()`](an.characters.svg_utils.md#an.characters.svg_utils.extract_pivots) already returns those joints
as `{name: (cx, cy)}`. Nothing connected the two: `promote` computed the
pivots and stored **only their names**, so the coordinates an artist drew
were discarded and every character got the generic rig (an#75).

Bones a drawing has no joint for keep their default placement, so a partial
skeleton improves a rig rather than breaking it.

Positions are stored parent-relative, so an absolute joint is converted
against its parent’s resolved absolute position — and parents are resolved
first, which is why this walks in declaration order rather than by index.

* **Return type:**
  list[Bone]

```pycon
>>> bones = bones_from_pivots({"neck": (500.0, 300.0), "root": (500.0, 900.0)})
>>> head = next(b for b in bones if b.name == "head")
>>> root = next(b for b in bones if b.name == "root")
>>> root.x, root.y
(500.0, 900.0)
>>> torso = next(b for b in bones if b.name == "torso")
>>> round(head.y + torso.y + root.y)          # absolute, back to the neck
300
```

### an.characters.schema.default_asset_sets()

`{channel: {key: attachment_name}}` for a freshly-built character.

* **Return type:**
  `dict`[`str`, `dict`[`str`, `str`]]

### an.characters.schema.view_variant_set(set_name, view)

The name of `set_name`’s variant for `view` (an#220).

* **Return type:**
  `str`

```pycon
>>> view_variant_set("eyelid", "side")
'eyelid@side'
```

### an.characters.schema.view_variant_sets(desc, , view_set='view')

`{base set: {view: variant set name}}` — every per-view face set the
descriptor declares (an#220): a set named `<base>@<view>` where `<base>`
is a declared set and `<view>` a key of its `view` set (or its
`rest_view`). `viseme@happy` is NOT one — `happy` is not a view —
so the expression variants (an#98) and the view variants never collide.

* **Return type:**
  `dict`[`str`, `dict`[`str`, `str`]]

```pycon
>>> d = CharacterDescriptor(name="v")
>>> d.asset_sets["view"] = {"front": "front", "side": "side"}
>>> d.asset_sets["eyelid@side"] = {"OPEN": "open_side", "CLOSED": "closed_side"}
>>> d.asset_sets["viseme@happy"] = {"X": "mouth_x_happy"}
>>> view_variant_sets(d)
{'eyelid': {'side': 'eyelid@side'}}
```
