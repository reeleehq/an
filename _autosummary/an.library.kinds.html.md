# an.library.kinds

Asset kinds: the `kind` facet’s vocabulary, and where each kind lives in a project.

An asset id’s prefix is its kind (`character.alice`). A kind says two things the
library needs for check-out and for publishing from a folder: which project
store holds it (`characters`) and what its descriptor file is called inside a
folder (`character.json`). Kinds with no project store yet (`motion`,
`reference`, `plane`) can be published and found, not checked out. The
`kit` kind is one of them for `checkout()`: a kit is a
document naming other assets, and [`checkout_kit()`](an.library.kits.html.md#an.library.kits.checkout_kit) checks
out the assets it names.

Genre packages register their kinds on import (ADR 0005 decision 12); the
built-ins below are the kinds `an`’s project mall already stores, plus the ones
the design names.

```pycon
>>> asset_kind_info("character").store
'characters'
>>> asset_kind_info("motion").store is None
True
```

### Module Attributes

| [`KIT_KIND`](#an.library.kinds.KIT_KIND)    | a versioned set of assets a production checks out together.   |
|--------------------------------------------------------------|---------------------------------------------------------------|
| [`ASSET_KINDS`](#an.library.kinds.ASSET_KINDS) | Registered asset kinds, by name.                              |

### Functions

| [`asset_kind_info`](#an.library.kinds.asset_kind_info)(name)                       | The registered kind `name`, or [`UnknownKindError`](#an.library.kinds.UnknownKindError) naming the known ones.   |
|----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| [`register_asset_kind`](#an.library.kinds.register_asset_kind)(name, \*[, store, ...]) | Register (or re-register) an asset kind.                                                                                  |

### Classes

| [`AssetKind`](#an.library.kinds.AssetKind)(name, store, descriptor[, ...])   | One asset kind: its project store and its descriptor file name in a folder.   |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|

### Exceptions

| [`UnknownKindError`](#an.library.kinds.UnknownKindError)   | An asset id whose kind prefix nobody registered.   |
|---------------------------------------------------------------------|----------------------------------------------------|

### an.library.kinds.ASSET_KINDS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [AssetKind](#an.library.kinds.AssetKind)]* *= {'character': AssetKind(name='character', store='characters', descriptor='character.json', credits_store='characters'), 'environment': AssetKind(name='environment', store='environments', descriptor='meta.json', credits_store='environments'), 'kit': AssetKind(name='kit', store=None, descriptor=None, credits_store=None), 'motion': AssetKind(name='motion', store=None, descriptor=None, credits_store=None), 'plane': AssetKind(name='plane', store=None, descriptor=None, credits_store=None), 'prop': AssetKind(name='prop', store='props', descriptor='prop.json', credits_store='props'), 'reference': AssetKind(name='reference', store=None, descriptor=None, credits_store=None), 'sound': AssetKind(name='sound', store='sounds', descriptor='sound.json', credits_store='sounds'), 'style': AssetKind(name='style', store='styles', descriptor=None, credits_store=None), 'voice': AssetKind(name='voice', store='voices', descriptor=None, credits_store=None)}*

Registered asset kinds, by name.

### *class* an.library.kinds.AssetKind(name, store, descriptor, credits_store=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One asset kind: its project store and its descriptor file name in a folder.

`descriptor` is `None` for kinds whose project store keeps one JSON
document per key with no folder (voices, styles): such an asset has no files.

#### credits_store *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The `an credits` store name its sources are read under (rights roll-up);
`None` reads the top-level `source` only.

### an.library.kinds.KIT_KIND *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'kit'*

a versioned set of assets a production checks out together.

* **Type:**
  The kind of a kit

### *exception* an.library.kinds.UnknownKindError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

An asset id whose kind prefix nobody registered.

### an.library.kinds.asset_kind_info(name)

The registered kind `name`, or [`UnknownKindError`](#an.library.kinds.UnknownKindError) naming the known ones.

* **Return type:**
  [`AssetKind`](#an.library.kinds.AssetKind)

### an.library.kinds.register_asset_kind(name, , store=None, descriptor=None, credits_store=None)

Register (or re-register) an asset kind. Returns it.

* **Return type:**
  [`AssetKind`](#an.library.kinds.AssetKind)
