# an.library.stores

The library mall: `records`, `versions` and `blobs`, each an injected `MutableMapping`.

ADR 0005 decision 11 and design §10. Three entities, three stores:

| store    | key                         | on disk (default backend)                       |
|----------|-----------------------------|-------------------------------------------------|
| records  | `<asset_id>`                | `library/records/<asset_id>.json`               |
| versions | `<asset_id>@<vNNN>`         | `library/versions/<asset_id>/<vNNN>.json`       |
| blobs    | `<sha256>`                  | `library/blobs/<aa>/<sha256>`                   |
| labels   | `<asset_id>@<vNNN>/<hex16>` | `library/labels/<asset_id>/<vNNN>/<hex16>.json` |

`labels` is write-once too: the append-only statements made about an existing
version after it was published (a relabel of its unchanged content, an#307),
each its own document, never rewritten or deleted.

- **\`\`dol\`\` stores**, unlike the project mall’s hand-written folder classes: a
  byte store ([`LocalFiles`](#an.library.stores.LocalFiles)) seen through `dol.wrap_kvs()` with a JSON
  codec and a key transform. Each store is replaced by injection
  (`build_library_mall(blobs=my_s3_store)`), and business logic sees only the
  mapping interface — the move to S3 is an injection, not a rewrite.
  [`LocalFiles`](#an.library.stores.LocalFiles) rather than `dol.Files` because the library needs three
  > things `dol.Files` does not give: writes that cannot tear (temp file +
  > `os.replace`), an exclusive create for write-once versions, and containment
  > (`dol.Files` writes a `../x` key outside its root).
- **\`\`versions\`\` is write-once** ([`WriteOnce`](#an.library.stores.WriteOnce)): a version is immutable, so
  overwriting or deleting one raises [`VersionExistsError`](#an.library.stores.VersionExistsError) — projects pin
  versions, and a pin that could change under them is no pin. On the folder
  backend the create is exclusive, so racing publishers cannot both win.
- **\`\`blobs\`\` is content-addressed and undeletable** ([`ImmutableBlobs`](#an.library.stores.ImmutableBlobs),
  a `dol.content.ContentAddressedStore`): every file of every version once,
  keyed by its SHA-256; a key can never point at changed bytes, and a blob a
  version pins cannot be deleted from under it.
- **Keys are validated twice** before they become paths: by the id grammars
  ([`an.library.ids`](an.library.ids.html.md#module-an.library.ids)), and by [`LocalFiles`](#an.library.stores.LocalFiles)’ containment check.
- **Nothing is created until the first write.**

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     lib = build_library_mall(d)
...     sorted(lib)
['blob_rights', 'blobs', 'labels', 'records', 'versions']
>>> mem = build_library_mall(records={}, versions={}, blobs={})  # all in memory
>>> ref = mem["blobs"].add(b"<svg/>")
>>> mem["blobs"][ref.item_id]
b'<svg/>'
```

### Module Attributes

| [`LIBRARY_STORES`](#an.library.stores.LIBRARY_STORES)   | The three stores every library mall holds.   |
|-------------------------------------------------------------------|----------------------------------------------|

### Functions

| [`build_library_mall`](#an.library.stores.build_library_mall)([root, package])    | The library mall of `package`: `records`, `versions` (write-once), `blobs` (CAS).   |
|-----------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| [`canonical_json`](#an.library.stores.canonical_json)(obj, \*[, indent])      | JSON with sorted keys and no locale or platform dependence.                         |
| [`label_key`](#an.library.stores.label_key)(asset_id, version, label_id) | The `labels` key of one statement about a version.                                  |
| [`split_label_key`](#an.library.stores.split_label_key)(key)                   | `(asset_id, version, label_id)` of a `labels` key, validated.                       |
| [`version_key`](#an.library.stores.version_key)(asset_id, version)         | The `versions` key of one version.                                                  |
| [`split_version_key`](#an.library.stores.split_version_key)(key)                 | `(asset_id, version)` of a `versions` key, validated.                               |

### Classes

| [`ImmutableBlobs`](#an.library.stores.ImmutableBlobs)([store, hasher, length, field])   | The content-addressed blob store, with deletion refused.                        |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`LocalFiles`](#an.library.stores.LocalFiles)(root)                                 | `relative/posix/path -> bytes` under one folder, with atomic, contained writes. |
| [`WriteOnce`](#an.library.stores.WriteOnce)(store)                                 | A mapping whose keys, once written, can be neither overwritten nor deleted.     |

### Exceptions

| [`VersionExistsError`](#an.library.stores.VersionExistsError)   | A write-once key was written twice, or deleted.   |
|-----------------------------------------------------------------------|---------------------------------------------------|

### *class* an.library.stores.ImmutableBlobs(store=None, \*, hasher=<built-in function openssl_sha256>, length=None, field='content')

Bases: `ContentAddressedStore`

The content-addressed blob store, with deletion refused.

Versions are write-once and pin their files by hash, so deleting a blob
would leave a published version pointing at nothing. Reclaiming unreferenced
blobs is a maintenance job (a garbage collector that counts references), not
a mapping operation.

```pycon
>>> blobs = ImmutableBlobs({})
>>> ref = blobs.add(b"x")
>>> del blobs[ref.item_id]
Traceback (most recent call last):
VersionExistsError: ...
```

### an.library.stores.LIBRARY_STORES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('records', 'versions', 'blobs')*

The three stores every library mall holds.

### *class* an.library.stores.LocalFiles(root)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`relative/posix/path -> bytes` under one folder, with atomic, contained writes.

The default backend of every library store:

- **contained**: a key that would resolve outside the folder (`..`, an
  absolute path, a drive) raises `KeyError` and never touches the disk;
- **atomic**: a write goes to a temp file in the target folder and is moved
  into place with `os.replace`, so a crash never leaves a torn document;
- **create-only** ([`create_only()`](#an.library.stores.LocalFiles.create_only)): a hard link of the fully written temp
  file, which fails if the target exists — the primitive [`WriteOnce`](#an.library.stores.WriteOnce)
  uses so two publishers cannot both create one version;
- **lazy**: nothing is created until the first write, so opening (or
  mistyping) a library never creates folders.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     f = LocalFiles(d + "/lib")
...     f["a/b.json"] = b"{}"
...     sorted(f), f["a/b.json"]
(['a/b.json'], b'{}')
```

#### create_only(key, data)

Write `key` only if it does not exist — atomically, in one step.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *exception* an.library.stores.VersionExistsError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

A write-once key was written twice, or deleted. Versions are immutable.

### *class* an.library.stores.WriteOnce(store)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

A mapping whose keys, once written, can be neither overwritten nor deleted.

Wraps any injected `MutableMapping`. Rewriting a key with the *same* value
is refused too: immutability is about the key, and a silent no-op would hide
a caller that believes it is replacing something.

**Atomicity.** When the wrapped store offers `create_only(key, value)` — an
exclusive create that raises [`VersionExistsError`](#an.library.stores.VersionExistsError) if the key exists —
every write goes through it, so two publishers racing for one key cannot both
win. The default folder backend has one (a hard link of a fully written temp
file); an S3 backend would map it to a conditional put (`If-None-Match: *`).
A store without it gets a check-then-set, which is correct for one writer.

```pycon
>>> versions = WriteOnce({})
>>> versions["character.a@v001"] = {"x": 1}
>>> versions["character.a@v001"] = {"x": 2}
Traceback (most recent call last):
VersionExistsError: ...
```

### an.library.stores.build_library_mall(root=None, , package='an', \*\*overrides)

The library mall of `package`: `records`, `versions` (write-once), `blobs` (CAS).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)]

root: the package’s data root (default: resolved by
: [`an.library.root.library_root()`](an.library.root.html.md#an.library.root.library_root) — `root` → `<PKG>_HOME` → the
  platform data folder); the stores live under `<root>/library/`

package: whose library this is (`an`, or a genre such as `cutan`)
overrides: a store per name to inject instead of the folder default — a

> `dict` for tests, an S3 or database mapping later. An injected
> `versions` is still made write-once and an injected `blobs` still
> content-addressed and undeletable, so injection cannot drop an invariant.

Nothing is created until the first write: opening a library (or mistyping
one on a search path) leaves the disk as it was.

### an.library.stores.canonical_json(obj, , indent=None)

JSON with sorted keys and no locale or platform dependence.

With `indent=None` it is the compact form hashed for a manifest; with an
indent it is the on-disk form (same content, readable).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> canonical_json({"b": 1, "a": [1, 2]})
'{"a":[1,2],"b":1}'
```

### an.library.stores.label_key(asset_id, version, label_id)

The `labels` key of one statement about a version.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> label_key("character.alice", "v002", "0123456789abcdef")
'character.alice@v002/0123456789abcdef'
```

### an.library.stores.split_label_key(key)

`(asset_id, version, label_id)` of a `labels` key, validated.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> split_label_key("character.alice@v002/0123456789abcdef")
('character.alice', 'v002', '0123456789abcdef')
```

### an.library.stores.split_version_key(key)

`(asset_id, version)` of a `versions` key, validated.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> split_version_key("character.alice@v002")
('character.alice', 'v002')
```

### an.library.stores.version_key(asset_id, version)

The `versions` key of one version.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> version_key("character.alice", "v002")
'character.alice@v002'
```
