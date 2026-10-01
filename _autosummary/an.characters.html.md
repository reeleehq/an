# an.characters

Character art system: Spine-shaped descriptor + SVG sidecars.

Public API:

- [`CharacterDescriptor`](#an.characters.CharacterDescriptor) — the on-disk schema for a character (bones,
  slots, skins, viseme map, idle animations).
- [`new_character()`](#an.characters.new_character) — generate a fresh character (DiceBear or built-in).
- [`generate_default_mouths()`](#an.characters.generate_default_mouths) — produce the 9-shape default mouth set.
- [`render_silhouette()`](#an.characters.render_silhouette), [`compare_silhouettes()`](#an.characters.compare_silhouettes) — silhouette test.
- [`breath_animation()`](#an.characters.breath_animation), [`blink_animation()`](#an.characters.blink_animation) — idle animation factories.
- [`validate_character()`](#an.characters.validate_character) — completeness check against the schema.
- [`promote()`](#an.characters.promote) — lift an inline character into the reusable mall.

Conventions (locked in):

- Slot/skin/animation separation modeled on Spine’s JSON format.
- SVG layout: a `<g id="skeleton">` of named `<circle>` pivots and a
  sibling `<g id="illustration">` containing named part groups (Pose
  Animator convention).
- 9 mouth shapes, named `mouth_a` through `mouth_h` plus `mouth_x`
  (the rest position), matching Rhubarb’s A–H + X visemes.
- Time in seconds (float); `bone:<name>.<prop>` and
  `slot:<name>.attachment` are the two animation target syntaxes.

```pycon
>>> from an.characters import MOUTH_SHAPES
>>> MOUTH_SHAPES
('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'x')
```

### Functions

| [`normalize_svg`](#an.characters.normalize_svg)(source, \*[, fallback_viewbox])     | Promote Inkscape labels to ids and ensure a viewBox is set.                                                                                                                         |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`extract_part`](#an.characters.extract_part)(source, part_id, \*[, ...])          | Emit a standalone SVG tree containing only the group with the given id.                                                                                                             |
| [`extract_pivots`](#an.characters.extract_pivots)(source, \*[, skeleton_id])         | Return `{name: (cx, cy)}` for every named `<circle>` under skeleton.                                                                                                                |
| [`write_svg`](#an.characters.write_svg)(tree_or_element[, path])                | Serialize an `ElementTree` or `Element` to bytes (and optionally disk).                                                                                                             |
| [`promote_inkscape_labels_to_ids`](#an.characters.promote_inkscape_labels_to_ids)(tree)              | Copy `inkscape:label` to `id` on each group missing an id.                                                                                                                          |
| [`generate_default_mouths`](#an.characters.generate_default_mouths)(\*[, canvas, ...])        | Return `{"mouth_<letter>[_<form>]": <svg-string>, ...}` for every shape.                                                                                                            |
| [`write_default_mouths`](#an.characters.write_default_mouths)(out_dir, \*[, canvas, ...])  | Write the default mouth SVGs into `out_dir` (created if missing), plus one `mouth_<shape>_<form>.svg` per shape for every `variants` entry (`{form: smile offset}`; `None` = none). |
| [`breath_animation`](#an.characters.breath_animation)(\*[, period_s, ...])             | Sine-wave breath on torso Y + head rotation; optional weight shift.                                                                                                                 |
| [`blink_animation`](#an.characters.blink_animation)(\*[, closure_s, duration_s, ...]) | Step-animation that snaps both eye slots closed → open.                                                                                                                             |
| [`render_silhouette`](#an.characters.render_silhouette)(svg_source, out_png, \*[, ...]) | Render an SVG to a binary silhouette PNG (black on white).                                                                                                                          |
| [`compare_silhouettes`](#an.characters.compare_silhouettes)(a, b, \*[, size])             | Return IoU between two silhouette PNGs (0..1; lower = more distinct).                                                                                                               |
| [`fetch_dicebear`](#an.characters.fetch_dicebear)(seed, \*[, style, ...])            | Fetch an avatar SVG from DiceBear's HTTP API.                                                                                                                                       |
| [`new_character`](#an.characters.new_character)(out_dir, \*, name[, seed, ...])     | Build a complete character on disk.                                                                                                                                                 |
| [`validate_character`](#an.characters.validate_character)(char_dir, \*[, name])          | Check an art package against the contract, offline.                                                                                                                                 |
| [`promote`](#an.characters.promote)(project_dir, entity, as_, \*[, ...])      | Promote `entity` from `project_dir`'s inline assets into the mall.                                                                                                                  |
| [`record_character`](#an.characters.record_character)(char_dir, \*[, name, ...])       | Render preview.html for the character at `char_dir` and record it.                                                                                                                  |
| [`record_preview_to_mp4`](#an.characters.record_preview_to_mp4)(preview_html, out_mp4, \*)  | Record `preview_html` to `out_mp4` for `duration_s` seconds.                                                                                                                        |

### Classes

| [`CharacterDescriptor`](#an.characters.CharacterDescriptor)(\*\*data)   | The on-disk character schema.                                           |
|----------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`Bone`](#an.characters.Bone)(\*\*data)                  | A skeleton joint with a local transform relative to its parent.         |
| [`Slot`](#an.characters.Slot)(\*\*data)                  | A draw-order slot bound to a bone, displaying one attachment at a time. |
| [`Attachment`](#an.characters.Attachment)(\*\*data)            | A drawable: an SVG path + anchor point (in 0..1 per-axis units).        |
| [`Skin`](#an.characters.Skin)(\*\*data)                  | A named outfit/variant: maps slot → {attachment_name → Attachment}.     |
| [`IdleAnimation`](#an.characters.IdleAnimation)(\*\*data)         | A named idle loop (e.g., breath, blink).                                |
| [`AnimationTrack`](#an.characters.AnimationTrack)(\*\*data)        | A single channel inside an idle animation.                              |

### *class* an.characters.AnimationTrack(\*\*data)

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

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.characters.Attachment(\*\*data)

Bases: `_CharModel`

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
`attachment_box()`.

#### x *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Offset from the slot’s bone, in view_box units.

**This is where a part’s position lives**, and it is the reference data
model’s answer, not an invention: DragonBones puts it in
`display.transform`, Spine in the region attachment’s `{x, y}`, and
in both the *slot* carries no transform at all. It is what lets five face
parts share one `head` bone and still land in different places — before
this field they all stacked on the bone, because the descriptor had no
way to say otherwise and the compiler used hardcoded literals instead.

### *class* an.characters.Bone(\*\*data)

Bases: `_CharModel`

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

### *class* an.characters.CharacterDescriptor(\*\*data)

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

#### asset_sets *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

`{channel: {key: attachment_name}}` — what a swap key SELECTS, layered
over `skins`, which is the SSOT for what art EXISTS. The indirection is
deliberate: a channel key is not an attachment name. Today’s viseme map
happens to be one-to-one (9 keys, 9 attachments), but real mouth charts
are many-to-one — ~10 drawings carrying ~40 phonemes — and collapsing the
two namespaces makes the first shared drawing a schema change instead of
a data change. Replaces `viseme_map` (schema 0.2.0).

#### colour_roles *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

Which colour literal in which part plays which `StylePack` role —
`{part path: {"#rrggbb": role}}`, e.g.
`{"parts/torso.svg": {"#a83249": "clothing"}}`. Written by the factory,
which KNOWS what it drew as skin or clothing; read by the compiler, which
rewrites the tagged literals under a pack (palette swapping — see
[`an.characters.colour_roles`](an.characters.colour_roles.html.md#module-an.characters.colour_roles)). Empty = untagged art (hand-drawn,
DiceBear): a pack cannot reach it and the compiler says so, because the
alternative is inferring a role from a pixel (an#99’s wrong-tone lid).
Additive: no schema bump, and a descriptor without it reads back as
untagged. Keys are normalised to lowercase `#rrggbb`; a role must be
one a pack can set ([`an.styles.REACHABLE_ROLES`](an.styles.html.md#an.styles.REACHABLE_ROLES)).

#### expression_binding *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]] | [None](https://docs.python.org/3/builtins/constants.html#None)*

How expression axes reach this rig (an#98), as a list of binding dicts —
`{"axis", "slot", "property", "gain"[, "rig_scaled"]}` for a transform
channel, `{"axis", "slot", "set_family"}` for a swap set. `None` means
the default binding derived from the slots the rig has
([`an.expression.binding.default_binding()`](an.expression.binding.html.md#an.expression.binding.default_binding)). Additive: no schema bump,
and a pre-Wave-6 descriptor reads back unchanged.

#### face_overlay *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

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

#### gait *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

This character’s default walk `gait` (one of `GAITS`, an#220);
an author’s `gait` arg overrides it. `None` = `legs` when the rig
builds a leg pair, else `rock`. A robe figure whose leg slots are hem
halves declares `"hem"` once, here, rather than on every walk.
Omitted from the stored document when unset.

#### gaze_travel *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

How far a pupil may travel from its rest, in view-box units per axis
(an#99): the sclera’s clearance minus the pupil’s radius, written by
`an character add-gaze` from the parts it synthesized. `None` = the
rig has no pupil layer (gaze is a no-op on it) or uses the default
travel. The travel maps the gaze axes’ unit circle onto the sclera’s
inner ellipse; the compiler clamps the summed (x, y) to 0.95 of that
circle, which keeps the whole pupil disc inside the white at every
angle (a per-axis box pokes out at the diagonal) — no runtime mask.

#### metadata *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

Free-form metadata (dicebear style/seed, etc.). Schema-evolution
friendly: anything an external tool wants to record can land here.

This comment used to say “art license, etc.” — an invitation nothing ever
took up. Rights live in `source` now, typed, so they can be found.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### model_post_init(\_CharacterDescriptor_\_context)

Override this method to perform additional initialization after `__init__` and `model_construct`.
This is useful if you want to do some validation that requires the entire model to be initialized.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### rest_view *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The view the DEFAULT art is drawn in (an#220) — a declared fact about
the art, like `face_overlay`. `None` means `DFLT_VIEW`
(front). A character carved from a profile (a silhouette film, a side-
on figure) says `"side"`, and everything that asks which view is in
force before any turn — `walk` swinging its legs rather than lifting
them — reads it instead of the author passing `view: side` by hand.
Omitted from the stored document when unset.

#### source *: [AssetSource](an.ir.assets.html.md#an.ir.assets.AssetSource) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where this character’s art came from, and what its licence obliges.

`None` means “we made this” — not “unknown”. Anything acquired should
carry one, because a licence defect is the only failure that reaches
BACKWARDS through completed work: a video shipped with an unattributed
CC BY asset cannot be un-shipped.

Field names match `illustration.ImageResult` exactly, so an adapter is a
dict copy rather than a rename table — and a rename table is where a field
quietly stops being carried. Pinned by test.

#### source_svg *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Optional source SVG (relative path) that the parts/ folder was
extracted from. Useful for re-slicing.

#### speech *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

a
method’s spelling (`mouth_chart`, `pulse`), its id
(`speech.pose_only`) or a choice with args and an optional version pin
(`{method: pulse, args: {strength: 0}}` — a mime). `None` = the
default chain: lip-sync when the character has a mouth chart, else a
head pulse, recorded. Declaring it is also how a baked-face character
renders under `--strict-assets`: a declared pulse is the request, not a
fallback. Resolved (and refused when unknown) by the capability
registry. Omitted from the stored document when unset.

* **Type:**
  How this character shows it is speaking (the speech aspect, an#248)

#### swap_poses *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [SlotPose](an.characters.schema.html.md#an.characters.schema.SlotPose)]]]*

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

#### voice_ref *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Voice-store id or path used by the audio pipeline. Optional; the scene
can override per shot.

### *class* an.characters.IdleAnimation(\*\*data)

Bases: `_CharModel`

A named idle loop (e.g., breath, blink).

```pycon
>>> a = IdleAnimation(name="idle_breath", duration=4.0)
>>> a.loop
True
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.characters.Skin(\*\*data)

Bases: `_CharModel`

A named outfit/variant: maps slot → {attachment_name → Attachment}.

```pycon
>>> skin = Skin(name="default", slots={"mouth": {"mouth_a": Attachment(path="parts/mouth/mouth_a.svg")}})
>>> skin.slots["mouth"]["mouth_a"].path
'parts/mouth/mouth_a.svg'
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.characters.Slot(\*\*data)

Bases: `_CharModel`

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

### an.characters.blink_animation(, closure_s=0.13, duration_s=0.18, eye_l_slot='left_eye', eye_r_slot='right_eye', open_attachment_l='open', closed_attachment_l='closed', open_attachment_r='open', closed_attachment_r='closed', name='blink')

Step-animation that snaps both eye slots closed → open.

The closure is centred: open → closed at `(duration - closure) / 2` →
open again `closure` later. With the defaults (0.13s closure in an
0.18s envelope) that is closed at 0.025s, open at 0.155s. (An earlier
docstring claimed 0.05/0.13 — numbers from an older closure value; and
the slot/attachment defaults were the stale pre-0.2.0 spellings
`eye_l`/`eye_l_open`, unnoticed for as long as nothing consumed
`descriptor.animations` — both fixed in an#87.)

* **Return type:**
  [`IdleAnimation`](an.characters.schema.html.md#an.characters.schema.IdleAnimation)

### an.characters.breath_animation(, period_s=4.0, amplitude_px=2.0, head_tilt_deg=0.5, include_weight_shift=True, weight_shift_amplitude_px=1.5, weight_shift_period_s=6.0, name='idle_breath')

Sine-wave breath on torso Y + head rotation; optional weight shift.

The head tilt is phase-offset by 0.25 cycles to follow the chest with a
natural lag. The optional weight shift is on a slower 6-second period to
avoid a metronomic feel when both run at the same time.

The animation’s `duration` is the LCM-ish combined period: the longest
sub-track period, so the overall loop closes cleanly.

* **Return type:**
  [`IdleAnimation`](an.characters.schema.html.md#an.characters.schema.IdleAnimation)

### an.characters.compare_silhouettes(a, b, , size=(256, 256))

Return IoU between two silhouette PNGs (0..1; lower = more distinct).

Both images are resized to `size`, converted to grayscale, thresholded
at the midpoint, and the intersection-over-union of the foreground (dark)
pixels is computed.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> # Two identical silhouettes → IoU = 1.0; two empty → 0.0 (no overlap).
>>> # Tested via test suite, not doctest, since it requires Playwright.
```

### an.characters.extract_part(source, part_id, , crop_viewbox=True, padding=8.0)

Emit a standalone SVG tree containing only the group with the given id.

Any top-level `<defs>` from the source is copied so the part can
resolve gradient / pattern / filter references like
`fill="url(#some_gradient)"`. The matched group is appended unchanged.

When `crop_viewbox` is True (the default), the new SVG’s viewBox is
cropped to the bounding box of the part’s primitive content (rect /
circle / ellipse / path) plus `padding` units on each side. This
keeps a part’s texture proportional to its content instead of to the whole
character canvas. Falls back to the source viewBox when no bbox can be
derived.

The emitted `width`/`height` always match the emitted viewBox, so the
part rasterises at its own extent and is never letterboxed inside a canvas
it does not fill. The crop rect’s \*\*parent-space origin survives as the
viewBox’s first two numbers\*\*, so where the part sat relative to its
siblings is not lost and needs no separate record.

If no match is found, raises [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError).

* **Return type:**
  [`ElementTree`](https://docs.python.org/3/library/xml.etree.elementtree.html#xml.etree.ElementTree.ElementTree)

### an.characters.extract_pivots(source, , skeleton_id='skeleton')

Return `{name: (cx, cy)}` for every named `<circle>` under skeleton.

Pivots use the Pose Animator convention: a `<g id="skeleton">` group
sibling of the illustration, containing one `<circle>` per named joint.
The circle’s `cx`/`cy` is the pivot in the same coordinate system as
the art (the SVG’s viewBox).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.characters.fetch_dicebear(seed, , style='lorelei', api_version='9.x', timeout_s=10.0, extra_params=None)

Fetch an avatar SVG from DiceBear’s HTTP API.

Returns the SVG string. Raises [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError) if the API call
fails (network error, HTTP error, non-SVG response).

The URL pattern is:

```default
https://api.dicebear.com/<api_version>/<style>/svg?seed=<seed>
```

Pass `extra_params` to forward style-specific options (e.g.
`backgroundColor=transparent`).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.generate_default_mouths(, canvas=(256, 128), palette=None, shapes=('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'x'), smile=0.0, form=None)

Return `{"mouth_<letter>[_<form>]": <svg-string>, ...}` for every shape.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> svgs = generate_default_mouths()
>>> 'mouth_x' in svgs and 'viewBox' in svgs['mouth_x']
True
>>> sorted(generate_default_mouths(shapes=["a"], smile=0.35, form="happy"))
['mouth_a_happy']
```

### an.characters.new_character(out_dir, , name, seed=None, style='lorelei', voice_ref=None, use_dicebear=True, acknowledge_attribution=False, overwrite=False, mouth_variants=None, gaze=True, palette=None, build='regular', head_scale=1.0, hat='none', sash=False, views=True)

Build a complete character on disk.

**Variety knobs** (every default reproduces the pre-knob character byte for
byte, which a golden test holds):

- `palette` — `{role: "#rrggbb"}` over `PALETTE_ROLES` (`skin`,
  `hair`, `clothing`, `leg`, `accessory`) — the SAME role names a
  [`StylePack`](an.styles.html.md#an.styles.StylePack) uses. Unset roles keep the seed’s colours.
  > `skin` also paints the hands and the gaze lid; `hair` the brows and
  > the collar. On a DiceBear head only the body follows (its face is baked).
- `build` — a key of `BUILDS`: `regular`, `squat` (round body,
  short legs), `tall`, `stick` (small blocky body, stick limbs).
- `head_scale` — the head and its whole face (eyes, brows, mouths, their
  offsets, the pupil travel) scaled together, so a big head keeps its face.
- `hat` — a key of `HATS` (offline head only), in `accessory`.
- `sash` — a diagonal band across the torso, in `accessory`.
- `views` (an#197) — draw the turnaround: `back`, `side` (a profile
  facing the viewer’s right) and `three_quarter` beside the front, as a
  `view` swap set with a pose per view (`add_views()`), so
  [`an.motion.turn()`](an.motion.html.md#an.motion.turn) can turn the character around. Offline head only
  > (a DiceBear face is baked into its art); ignored for a DiceBear head.

  Additive: a shot that never sets a view renders exactly as without it.

Every colour the factory draws in a role is recorded in the descriptor’s
`colour_roles` so a style pack can recolour it later (palette swapping,
[`an.characters.colour_roles`](an.characters.colour_roles.html.md#module-an.characters.colour_roles)).

`gaze` (an#99) adds the eye stack — sclera and pupil slots under each
lid, a filled closed lid, the `gaze_travel` clamp — through
`add_gaze()`, so `gaze_x`/`gaze_y` and the ambient saccades reach the
pupils. Off, the eye is the single pre-stack drawing.

`mouth_variants` (an#98) — `{form: smile offset}` — writes one more
9-shape mouth set per form (`mouth_<shape>_<form>.svg`) and declares it
as the `viseme@<form>` swap set, with its attachments in the default
skin’s `mouth` slot, so an expression preset preferring that form
selects it. `None` means [`DEFAULT_MOUTH_VARIANTS`](an.characters.mouth_set.html.md#an.characters.mouth_set.DEFAULT_MOUTH_VARIANTS)
(happy, sad); `{}` means the neutral set only.

Steps:

1. Fetch a DiceBear avatar (skip if `use_dicebear=False` — useful for
   offline tests).
2. Wrap it into the canonical `an` cutout SVG (skeleton + illustration
   groups), saved as `<name>.svg`.
3. Slice each part into `parts/<part>.svg`.
4. Write the 9-shape default mouth set into `parts/mouth/`.
5. Synthesize a few derived parts (open/closed eyes, brows) so the
   character is complete out of the box.
6. Emit a `character.json` descriptor.

Returns the path to the created `character.json`.

Raises [`FileExistsError`](https://docs.python.org/3/builtins/exceptions.html#FileExistsError) if `out_dir/name` already exists and
`overwrite=False`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.characters.normalize_svg(source, , fallback_viewbox='0 0 1024 1024')

Promote Inkscape labels to ids and ensure a viewBox is set.

Returns the parsed `ElementTree`. Idempotent: running it twice is a
no-op on the second pass.

* **Return type:**
  [`ElementTree`](https://docs.python.org/3/library/xml.etree.elementtree.html#xml.etree.ElementTree.ElementTree)

### an.characters.promote(project_dir, entity, as_, , source_svg=None, voice_ref=None, use_dicebear=True, overwrite=False)

Promote `entity` from `project_dir`’s inline assets into the mall.

* **Parameters:**
  * **project_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Path to an `an` project (must contain `assets/characters/`).
  * **entity** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Inline entity id used inside the scene (the directory under
    `assets/characters/<entity>`, or the SVG file at
    `assets/characters/<entity>.svg`).
  * **as_** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The mall character id to register the result as. Becomes the
    directory name under `assets/characters/` and the descriptor’s
    `name` field.
  * **source_svg** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Optional explicit path to a source SVG. If omitted, the function
    looks for `assets/characters/<entity>.svg` or
    `assets/characters/<entity>/<entity>.svg`.
  * **voice_ref** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Voice reference to embed in the descriptor.
  * **use_dicebear** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Forwarded to [`new_character()`](an.characters.factory.html.md#an.characters.factory.new_character) on the
    no-source fallback path. Pass `False` to keep the call offline —
    without it that fallback always reaches the DiceBear API, and
    `new_character` swallows the failure and generates geometry instead,
    so an offline test looks like it passed rather than like it was skipped.
  * **overwrite** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If False and the target already exists, raises `FileExistsError`.
  * **character.json.** (*Returns the path to the new*)
* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.characters.promote_inkscape_labels_to_ids(tree)

Copy `inkscape:label` to `id` on each group missing an id.

Returns the number of groups updated.

Inkscape stores the user-visible name in the `inkscape:label` attribute
and does NOT promote it to `id` on save. This is a long-standing UX
issue (Inkscape bug #243383); the workaround is to promote at parse time.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.characters.record_character(char_dir, , name=None, out_mp4=None, duration_s=8.0, size=(640, 480))

Render preview.html for the character at `char_dir` and record it.

The preview HTML is generated/refreshed via the same writer used by
`an character preview`, so this command is self-contained.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.characters.record_preview_to_mp4(preview_html, out_mp4, , duration_s=8.0, size=(640, 480), fps=30, crf=23)

Record `preview_html` to `out_mp4` for `duration_s` seconds.

Returns the output mp4 path.

Pipeline:

> 1. Playwright launches headless Chromium with video recording on.
> 2. Navigates to `preview_html` ([file://](file://) URL).
> 3. Waits `duration_s` real-time so the browser captures frames.
> 4. Closes the context to flush the webm.
> 5. ffmpeg re-encodes the webm to H.264 mp4 (better compatibility,
>    smaller files, plays in `quicktime` / GitHub previews).

Both Playwright (project dep) and ffmpeg (system dep, already
required by the renderer) must be installed.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.characters.render_silhouette(svg_source, out_png, , size=(256, 256), background='#ffffff')

Render an SVG to a binary silhouette PNG (black on white).

Uses Playwright/Chromium to rasterize, then PIL to threshold by alpha
or luminance. Returns the output path.

The output is RGB; the silhouette is filled with black (#000) and the
background with the given color.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.characters.validate_character(char_dir, , name=None)

Check an art package against the contract, offline.

Reports a [`Finding`](an.verify.html.md#an.verify.Finding) per problem: a missing or
unparseable descriptor, absent required parts or mouth shapes, a part that
draws nothing, a prohibited construct, a letterboxed part, a joint name
colliding with a part id, and an unpopulated `AssetSource`.

* **Return type:**
  [`VerificationReport`](an.verify.html.md#an.verify.VerificationReport)

```pycon
>>> import tempfile, pathlib
>>> with tempfile.TemporaryDirectory() as d:
...     report = validate_character(d, name="nobody")
>>> report.passed
False
>>> any("character.json" in f.description for f in report.findings)
True
```

### an.characters.write_default_mouths(out_dir, , canvas=(256, 128), palette=None, shapes=('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'x'), variants=None)

Write the default mouth SVGs into `out_dir` (created if missing),
plus one `mouth_<shape>_<form>.svg` per shape for every `variants`
entry (`{form: smile offset}`; `None` = none).

Returns the list of paths written: the neutral set in shape order, then
each variant’s.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### an.characters.write_svg(tree_or_element, path=None)

Serialize an `ElementTree` or `Element` to bytes (and optionally disk).

Always emits `<?xml version="1.0" encoding="UTF-8"?>` and the SVG
namespace as the default, so the output is a valid standalone SVG.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### Modules

| [`cli`](an.characters.cli.html.md#module-an.characters.cli)                   | User-facing character CLI subcommands.                                                      |
|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`colour_roles`](an.characters.colour_roles.html.md#module-an.characters.colour_roles) | Colour roles: which colour literal in which part is skin, clothing, hair…                   |
| [`dicebear`](an.characters.dicebear.html.md#module-an.characters.dicebear)         | DiceBear HTTP API client + best-effort post-processing.                                     |
| [`factory`](an.characters.factory.html.md#module-an.characters.factory)           | High-level entry points: build and inspect a character.                                     |
| [`idle`](an.characters.idle.html.md#module-an.characters.idle)                 | Idle animation factories: breath, blink, weight-shift.                                      |
| [`licenses`](an.characters.licenses.html.md#module-an.characters.licenses)         | DiceBear per-style licences, as data.                                                       |
| [`methods`](an.characters.methods.html.md#module-an.characters.methods)           | The cut-out genre's methods and aspects, and their compile-time resolution (ADR 0002).      |
| [`mouth_set`](an.characters.mouth_set.html.md#module-an.characters.mouth_set)       | Generate the 9-shape default mouth set as parametric SVGs.                                  |
| [`play`](an.characters.play.html.md#module-an.characters.play)                 | Resolve a `play` against a character descriptor — the renderer-free half (an#7).            |
| [`record`](an.characters.record.html.md#module-an.characters.record)             | Record a character's preview HTML to an mp4.                                                |
| [`registration`](an.characters.registration.html.md#module-an.characters.registration) | The character side of the cut-out genre, as declarations: `play` and `character`.           |
| [`schema`](an.characters.schema.html.md#module-an.characters.schema)             | Character descriptor schema (Spine-shaped, Pydantic v2).                                    |
| [`silhouette`](an.characters.silhouette.html.md#module-an.characters.silhouette)     | Silhouette rendering and comparison for the silhouette test.                                |
| [`svg_utils`](an.characters.svg_utils.html.md#module-an.characters.svg_utils)       | SVG manipulation: namespace-aware DOM helpers using stdlib `xml.etree`.                     |
| [`validate`](an.characters.validate.html.md#module-an.characters.validate)         | Whether an art package is one the compiler can actually render.                             |
| [`vocabulary`](an.characters.vocabulary.html.md#module-an.characters.vocabulary)     | The cut-out genre's vocabulary entries: motion presets, expression presets, IR-field notes. |
