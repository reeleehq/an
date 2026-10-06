# an.stage.props

Props: a rig whose art is not a person.

A lamp, a sword, a sign. Structurally a prop is what a character already is —
bones, slots, skins, attachments, swap sets — and the cutout compiler builds
both with the **same** rig builder, which is why an#108 made the art store an
argument rather than writing a second one.

What differs is the *descriptor*, and the difference is entirely in the
defaults:

| `CharacterDescriptor`        | `PropDescriptor`   |
|------------------------------|--------------------|
| seven-bone humanoid          | one `root` bone    |
| face, eyes, brows, mouth     | one `body` slot    |
| `idle_breath` + `blink`      | no animations      |
| viseme + eyelid `asset_sets` | none               |
| `face_overlay` matters       | no face at all     |

\*\*Why not `CharacterDescriptor` with `kind: "prop"`.\*\* Three measured reasons,
each of which turns a one-field change into a silent wrong render:

1. `CharacterDescriptor.model_post_init` re-seeds the humanoid skeleton, the
   face slots, the default skin **and** `idle_breath`/`blink` from an empty
   list — so `CharacterDescriptor(name="sword")` is a seven-bone person with a
   blinking face, not an empty rig.
2. The compiler’s placeholder fallback draws a **person** where a lamp should
   be (the an#33 failure mode), so a prop whose art fails to resolve renders
   as a humanoid rather than as nothing.
3. `an character validate` scores a correct prop at **22** blocking findings —
   `REQUIRED_PARTS` (12) plus `MOUTH_SHAPES` (9), none of which a lamp has,
   plus “has no character.json”, which is the tool saying out loud that it was
   handed the wrong kind of document. (Measured on
   `tests/fixtures/props/lamp/`; an earlier draft of this docstring said 21,
   having added the two lists without running the tool.)

\*\*Why not a new minimal document with `states`.\*\* That is `asset_sets`
renamed: it would need a rename table at the compiler boundary and would cap a
prop at one moving piece. A prop reuses the swap-channel machinery instead, so
a two-state lamp is `asset_sets={"lamp": {"off": ..., "on": ...}}` and
`set lamp on` in the scene — the same words a character’s viseme swap uses.

### Module Attributes

| [`PROP_DOCUMENT_KIND`](#an.stage.props.PROP_DOCUMENT_KIND)   | Its own versioned document, registered from the module that owns the schema — the same rule `CharacterDescriptor` follows, and the reason the migration registry is keyed per KIND: two documents at `0.1.0` that migrate differently is exactly the collision an#77 fixed.   |
|-----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`default_prop_bones`](#an.stage.props.default_prop_bones)()   | One bone at the origin.   |
|-------------------------------------------------------------------------|---------------------------|
| [`default_prop_slots`](#an.stage.props.default_prop_slots)()   | One slot on that bone.    |

### Classes

| [`PropDescriptor`](#an.stage.props.PropDescriptor)(\*\*data)   | The on-disk prop schema.   |
|-----------------------------------------------------------------------------|----------------------------|

### an.stage.props.PROP_DOCUMENT_KIND *: [DocumentKind](an.ir.md#an.ir.DocumentKind)* *= DocumentKind(name='PropDescriptor', version_field='schema_version', current_version='0.1.0')*

Its own versioned document, registered from the module that owns the schema
— the same rule `CharacterDescriptor` follows, and the reason the migration
registry is keyed per KIND: two documents at `0.1.0` that migrate
differently is exactly the collision an#77 fixed.

### *class* an.stage.props.PropDescriptor(\*\*data)

Bases: [`RigDocument`](an.stage.rig.md#an.stage.rig.RigDocument)

The on-disk prop schema. Saved as `prop.json`.

```pycon
>>> p = PropDescriptor(name="lamp")
>>> p.kind
'PropDescriptor'
>>> [b.name for b in p.bones], [s.name for s in p.slots]
(['root'], ['body'])
```

A prop is **not** seeded with a face, a skeleton or an idle animation —
the three things `CharacterDescriptor` fills in from an empty list:

```pycon
>>> p.animations, p.asset_sets, p.skins
({}, {}, {})
```

Two states are the swap-channel machinery a character’s viseme already
uses, not a second vocabulary:

```pycon
>>> lamp = PropDescriptor(
...     name="lamp",
...     skins={"default": Skin(slots={"body": {
...         "off": Attachment(path="parts/off.svg"),
...         "on": Attachment(path="parts/on.svg"),
...     }})},
...     asset_sets={"lamp": {"off": "off", "on": "on"}},
... )
>>> sorted(lamp.asset_sets["lamp"])
['off', 'on']
>>> back = PropDescriptor.model_validate_json(lamp.model_dump_json())
>>> back.skins["default"].slots["body"]["on"].path
'parts/on.svg'
```

A prop stands where it is put by its declared `origin` (an#338), in
view_box units; unset, by the centre of its bones’ extent, and the stored
document does not mention it:

```pycon
>>> PropDescriptor(name="tripod", origin=(512, 1010)).origin
(512.0, 1010.0)
>>> "origin" in PropDescriptor(name="lamp").model_dump()
False
```

#### animations *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

Present so `play` and the rig builder read the same attribute on either
descriptor. Empty by default — a prop has no `idle_breath` and no
`blink`, and seeding one would animate a lamp.

#### asset_sets *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

`{channel: {key: attachment_name}}` — the same indirection a character
uses for visemes. Empty by default: a prop with no moving parts declares
none, and declaring a channel a rig cannot serve is what makes a swap
silently keep the previous texture.

#### face_overlay *: [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)[True]*

Always true, and not a knob. `face_overlay=False` means “the face is
baked into the head art”, which makes the builder suppress every slot
nested under the head bone’s primary slot. A prop has no head bone, so
the flag can only do harm; it exists because the shared builder reads it.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### model_post_init(\_PropDescriptor_\_context)

Override this method to perform additional initialization after `__init__` and `model_construct`.
This is useful if you want to do some validation that requires the entire model to be initialized.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### source *: [AssetSource](an.ir.assets.md#an.ir.assets.AssetSource) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where this art came from and what its licence obliges. `None` means
“we made this” — not “unknown”. Same field as `CharacterDescriptor`,
because `an credits` should not need to know which store it came from.

#### source_svg *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Optional source SVG the `parts/` folder was sliced from.

### an.stage.props.default_prop_bones()

One bone at the origin.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Bone`](an.stage.rig.md#an.stage.rig.Bone)]

```pycon
>>> [b.name for b in default_prop_bones()]
['root']
```

### an.stage.props.default_prop_slots()

One slot on that bone.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Slot`](an.stage.rig.md#an.stage.rig.Slot)]

```pycon
>>> [(s.name, s.bone, s.draw_order) for s in default_prop_slots()]
[('body', 'root', 0)]
```
