# an.library.character

The character analyser: legs, arms, views and mouth chart, derived from the rig.

The first analyser (ADR 0005 first slice, item 2), shared with ADR 0002’s first
slice: P7’s capability registry adopts [`character_affordances()`](#an.library.character.character_affordances) as
`affordances(asset)` for characters instead of deriving a second time.

**What it reads is what the compiler reads**, or the facets would lie (ADR 0005,
Risks): the limb pairs `walk` resolves (`an.motion.WALK_LEG_NAMES`,
`an.motion.WALK_ARM_NAMES`), the `view` and `viseme` swap sets
(`asset_sets`), the declared facts `rest_view`,
`face_overlay` and `occluded`. And **art must be present**: a slot or swap key counts only
when an attachment it names has its file among the asset’s files — a descriptor
promising a side view whose drawing is missing does not afford one.

It is genre code (cut-out characters). It lives here until the genre package
exists (plan P8) and imports the cut-out modules lazily so `import an.library`
stays free of them. **Importing it registers nothing** (P7): the cut-out genre
declares [`CHARACTER_CAPABILITIES`](#an.library.character.CHARACTER_CAPABILITIES) and [`CHARACTER_ANALYSER`](#an.library.character.CHARACTER_ANALYSER) in its
`capabilities` and `analysers` fields (`an.genres.cutout.CUTOUT`), so
they register with the genre, owned by it, and come out with it.

| capability   | afforded when                                                                                           | `keys`                                 |
|--------------|---------------------------------------------------------------------------------------------------------|----------------------------------------|
| `limbs.legs` | a leg pair `walk` resolves, both with art                                                               | —                                      |
| `limbs.arms` | an arm pair `walk` resolves, both with art                                                              | —                                      |
| `swap.view`  | always: the rest view, plus every `view` key with<br/>art (`swappable`: whether it can turn at all)     | the views it can show                  |
| `face.mouth` | an overlay face (`face_overlay`) whose `viseme`<br/>set has drawings                                    | the chart (`rhubarb9`<br/>or `custom`) |
| `face.brows` | an overlay face whose two brow slots have art, with<br/>nothing recorded over them (`occluded`, an#252) | —                                      |

### Module Attributes

| [`CHARACTER_ANALYSER_VERSION`](#an.library.character.CHARACTER_ANALYSER_VERSION)   | Bump when the derivation can answer differently for the same input.              |
|-------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`MOUTH_CHART_RHUBARB`](#an.library.character.MOUTH_CHART_RHUBARB)          | The chart name of the nine Rhubarb mouth shapes (A–H, X) — `an`'s default.       |
| [`CHARACTER_CAPABILITIES`](#an.library.character.CHARACTER_CAPABILITIES)       | The capabilities the character analyser derives (declared by the cut-out genre). |
| [`CHARACTER_ANALYSER`](#an.library.character.CHARACTER_ANALYSER)           | The character analyser (declared by the cut-out genre, registered with it).      |

### Functions

| [`character_affordances`](#an.library.character.character_affordances)(doc, art)   | The capabilities a character descriptor and its art afford.                      |
|------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`renders_as_placeholder`](#an.library.character.renders_as_placeholder)(doc)       | Whether the compiler would draw this character only as its placeholder stand-in. |

### an.library.character.CHARACTER_ANALYSER *: [Analyser](an.capabilities.md#an.capabilities.Analyser)* *= Analyser(kind='character', version='0.2.0', subject='asset', declares=('rest_view', 'face_overlay', 'gait', 'speech', 'occluded'))*

The character analyser (declared by the cut-out genre, registered with it).

### an.library.character.CHARACTER_ANALYSER_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '0.2.0'*

Bump when the derivation can answer differently for the same input.
0.2.0: `face.brows` (an#252).

### an.library.character.CHARACTER_CAPABILITIES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Capability](an.capabilities.md#an.capabilities.Capability), ...]* *= (Capability(name='limbs.legs', description='a pair of leg slots with art that a legged walk swings', remedy='add two leg slots named leg_l/leg_r (or left_leg/right_leg) with their art, pivoted at the hip; \`an character new\` builds them (an-art-package skill)', subject='asset', command=None, version='1'), Capability(name='limbs.arms', description='a pair of arm slots with art that a walk swings and gestures move', remedy='add two arm slots named arm_l/arm_r (or left_arm/right_arm) with their art, pivoted at the shoulder (an-art-package skill)', subject='asset', command=None, version='1'), Capability(name='swap.view', description='the turnaround views the character can show (keys); swappable=true when a \`view\` swap set lets it turn', remedy='add turnaround art and list it in the \`view\` swap set: \`an character add-views <dir>\` for an offline character, else draw the views', subject='asset', command='an character add-views', version='1'), Capability(name='face.mouth', description='an overlay mouth with a viseme chart that lip-sync drives (keys: the chart)', remedy="give the character an overlay mouth: a \`mouth\` slot with the viseme set's drawings (\`an character mouths <dir>\` writes the default nine) and face_overlay: true — a face baked into the head art cannot lip-sync", subject='asset', command='an character mouths', version='1'), Capability(name='face.brows', description='two brows on an overlay face that an expression raises, lowers and angles, with nothing recorded over their acting range (slots: the brow slots)', remedy="give the overlay face two brow slots (left_brow/right_brow) with their art, and keep hats off the brows' acting range: a factory hat that cannot sit above them is recorded in character.json's \`occluded\` — \`an character new\` with a larger --head-scale, another --hat or --hat none; for drawn art, redraw the cover above the brows and remove its \`occluded\` entry", subject='asset', command=None, version='1'))*

The capabilities the character analyser derives (declared by the cut-out genre).

### an.library.character.MOUTH_CHART_RHUBARB *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'rhubarb9'*

The chart name of the nine Rhubarb mouth shapes (A–H, X) — `an`’s default.

### an.library.character.character_affordances(doc, art)

The capabilities a character descriptor and its art afford.

doc: the character descriptor document (any schema version; migrated first)
art: the files present, `{relative path: ContentRef JSON}` (`parts/head.svg`, …)

Gait is deliberately not here: which walk methods apply is the capability
matcher’s answer (`applicable("locomotion", asset)`, ADR 0002), derived from
`limbs.legs`, not a second fact about the asset.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

```pycon
>>> from an.characters.schema import CharacterDescriptor
>>> doc = CharacterDescriptor(name="blob").model_dump(mode="json")
>>> sorted(character_affordances(doc, art={}))   # a descriptor with no art
['swap.view']
```

### an.library.character.renders_as_placeholder(doc)

Whether the compiler would draw this character only as its placeholder stand-in.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> renders_as_placeholder({"name": "alice"}), renders_as_placeholder({"parts": ["head"]})
(True, False)
```
