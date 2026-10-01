# an.library.character

The character analyser: legs, arms, views and mouth chart, derived from the rig.

The first analyser (ADR 0005 first slice, item 2), shared with ADR 0002’s first
slice: P7’s capability registry adopts [`character_affordances()`](#an.library.character.character_affordances) as
`affordances(asset)` for characters instead of deriving a second time.

**What it reads is what the compiler reads**, or the facets would lie (ADR 0005,
Risks): the limb pairs `walk` resolves (`an.motion.WALK_LEG_NAMES`,
`an.motion.WALK_ARM_NAMES`), the `view` and `viseme` swap sets
(`asset_sets`), the declared facts `rest_view` and
`face_overlay`. And **art must be present**: a slot or swap key counts only
when an attachment it names has its file among the asset’s files — a descriptor
promising a side view whose drawing is missing does not afford one.

It is genre code (cut-out characters). It lives here until the genre package
exists (plan P8), registered under the `character` kind, and imports the
cut-out modules lazily so `import an.library` stays free of them.

| capability   | afforded when                                                                                       | `keys`                                 |
|--------------|-----------------------------------------------------------------------------------------------------|----------------------------------------|
| `limbs.legs` | a leg pair `walk` resolves, both with art                                                           | —                                      |
| `limbs.arms` | an arm pair `walk` resolves, both with art                                                          | —                                      |
| `swap.view`  | always: the rest view, plus every `view` key with<br/>art (`swappable`: whether it can turn at all) | the views it can show                  |
| `face.mouth` | an overlay face (`face_overlay`) whose `viseme`<br/>set has drawings                                | the chart (`rhubarb9`<br/>or `custom`) |

### Module Attributes

| [`CHARACTER_ANALYSER_VERSION`](#an.library.character.CHARACTER_ANALYSER_VERSION)   | Bump when the derivation can answer differently for the same input.        |
|-------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`MOUTH_CHART_RHUBARB`](#an.library.character.MOUTH_CHART_RHUBARB)          | The chart name of the nine Rhubarb mouth shapes (A–H, X) — `an`'s default. |

### Functions

| [`character_affordances`](#an.library.character.character_affordances)(doc, art)   | The capabilities a character descriptor and its art afford.                      |
|------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`renders_as_placeholder`](#an.library.character.renders_as_placeholder)(doc)       | Whether the compiler would draw this character only as its placeholder stand-in. |

### an.library.character.CHARACTER_ANALYSER_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '0.1.0'*

Bump when the derivation can answer differently for the same input.

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
