# an.library.ids

Asset ids, version labels and library references — the library’s persisted names.

Three grammars, each a persisted identifier (ADR 0005 decisions 3 and 4, plan §1
decision 7), so each is checked here once and never re-parsed by hand elsewhere:

- an **asset id** is `<kind>.<slug>` — flat, readable, filename-safe
  (`character.alice-reiniger`). The kind prefix keeps two kinds from colliding
  on one slug and makes `find(kind=…)` cheap;
- a **version label** is `v001`, `v002`, … — the studio convention, for
  people. The version’s `manifest_sha256` is its identity for machines;
- a **library reference** is `[<namespace>:]<asset_id>[@<version>]`, where
  `<version>` is a label, `latest` (floating; resolved once at check-out and
  pinned) or `sha256:<prefix>` (exact content). The namespace names the library
  an id resolves in when several are federated (`cutan:character.alice@v003`).

Because these strings become file names (`records/<asset_id>.json`,
`versions/<asset_id>/<vNNN>.json`), the grammars are also the path-traversal
guard: nothing that parses here can contain `/`, `..` or a drive letter.

```pycon
>>> ref = parse_ref("cutan:character.alice-reiniger@v003")
>>> (ref.namespace, ref.asset_id, ref.version, ref.kind)
('cutan', 'character.alice-reiniger', 'v003', 'character')
>>> str(ref)
'cutan:character.alice-reiniger@v003'
>>> version_label(12)
'v012'
```

### Module Attributes

| [`LATEST`](#an.library.ids.LATEST)        | the record's head, resolved once and then pinned.                           |
|----------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`SHA256_PREFIX`](#an.library.ids.SHA256_PREFIX) | The prefix of a content-addressed version selector (`sha256:<hex prefix>`). |

### Functions

| [`asset_kind`](#an.library.ids.asset_kind)(asset_id)                        | The kind an asset id declares by its prefix.                                                                          |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| [`check_asset_id`](#an.library.ids.check_asset_id)(asset_id)                    | Return `asset_id` if it is `<kind>.<slug>`, else raise [`AssetIdError`](#an.library.ids.AssetIdError). |
| [`check_namespace`](#an.library.ids.check_namespace)(name)                       | Return `name` if it can name a library (a package name), else raise.                                                  |
| [`check_version_label`](#an.library.ids.check_version_label)(label)                  | Return `label` if it is `vNNN`, else raise [`AssetIdError`](#an.library.ids.AssetIdError).             |
| [`parse_ref`](#an.library.ids.parse_ref)(text, \*[, require_version, ...]) | Parse a library reference.                                                                                            |
| [`version_label`](#an.library.ids.version_label)(number)                       | The label of the `number`-th version (1-based).                                                                       |
| [`version_number`](#an.library.ids.version_number)(label)                       | The number of a version label.                                                                                        |

### Classes

| [`LibraryRef`](#an.library.ids.LibraryRef)(asset_id[, version, namespace])   | A parsed `[<namespace>:]<asset_id>[@<version>]`.   |
|-----------------------------------------------------------------------------------------------|----------------------------------------------------|

### Exceptions

| [`AssetIdError`](#an.library.ids.AssetIdError)   | An asset id, version label or library reference that does not parse.   |
|-----------------------------------------------------------------|------------------------------------------------------------------------|

### *exception* an.library.ids.AssetIdError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

An asset id, version label or library reference that does not parse.

### an.library.ids.LATEST *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'latest'*

the record’s head, resolved once and then pinned.

* **Type:**
  The floating version

### *class* an.library.ids.LibraryRef(asset_id, version=None, namespace=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A parsed `[<namespace>:]<asset_id>[@<version>]`.

`version` is `None` when the reference gave none (read as `latest` by
readers; refused where a pin is required, e.g. `AssetRef.library`).

#### *property* is_pinned *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether this names one immutable version (a label or a content hash).

#### *property* kind *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The asset kind, from the id’s prefix.

#### with_namespace(namespace)

The same asset and version, qualified by another library name.

* **Return type:**
  [`LibraryRef`](#an.library.ids.LibraryRef)

#### with_version(version)

The same asset, another version.

* **Return type:**
  [`LibraryRef`](#an.library.ids.LibraryRef)

### an.library.ids.SHA256_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'sha256:'*

The prefix of a content-addressed version selector (`sha256:<hex prefix>`).

### an.library.ids.asset_kind(asset_id)

The kind an asset id declares by its prefix.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> asset_kind("environment.palace-hall")
'environment'
```

### an.library.ids.check_asset_id(asset_id)

Return `asset_id` if it is `<kind>.<slug>`, else raise [`AssetIdError`](#an.library.ids.AssetIdError).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> check_asset_id("prop.teacup-victorian")
'prop.teacup-victorian'
>>> check_asset_id("Alice")
Traceback (most recent call last):
AssetIdError: ...
```

### an.library.ids.check_namespace(name)

Return `name` if it can name a library (a package name), else raise.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.library.ids.check_version_label(label)

Return `label` if it is `vNNN`, else raise [`AssetIdError`](#an.library.ids.AssetIdError).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.library.ids.parse_ref(text, , require_version=False, require_pin=False)

Parse a library reference.

`require_version=True` refuses a reference with no `@<version>`;
`require_pin=True` also refuses `@latest` — the grammar of
`AssetRef.library`, where a floating reference would make a render depend
on whatever the library’s head is that day.

* **Return type:**
  [`LibraryRef`](#an.library.ids.LibraryRef)

```pycon
>>> parse_ref("character.alice")
LibraryRef(asset_id='character.alice', version=None, namespace=None)
>>> parse_ref("character.alice@sha256:0a1b2c3d").version
'sha256:0a1b2c3d'
>>> parse_ref("character.alice", require_version=True)
Traceback (most recent call last):
AssetIdError: ...
```

### an.library.ids.version_label(number)

The label of the `number`-th version (1-based).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> version_label(1), version_label(1000)
('v001', 'v1000')
```

### an.library.ids.version_number(label)

The number of a version label.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> version_number("v012")
12
```
