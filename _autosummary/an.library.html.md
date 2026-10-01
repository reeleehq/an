# an.library

The asset library: reusable assets that outlive their videos (ADR 0005).

A **library** holds characters, props, environments, sounds, styles, voices and
motion clips across videos and styles; a **project** is one video that checks
assets out of it. Each package has its own library root (`an` →
`~/.local/share/an`, a genre such as `cutan` → `~/.local/share/cutan`),
read together as an ordered search path.

```pycon
>>> import tempfile
>>> from an.characters.schema import CharacterDescriptor
>>> with tempfile.TemporaryDirectory() as d:
...     lib = open_library("an", root=d)
...     doc = CharacterDescriptor(name="blob")
...     r = publish(lib, "character.blob", doc, style="reiniger")
...     [h.ref for h in find(lib, kind="character", affords="swap.view:front")]
['character.blob@v001']
```

What lives where:

- [`an.library.root`](an.library.root.html.md#module-an.library.root) — the root of each package’s data (vendored XDG logic);
- [`an.library.ids`](an.library.ids.html.md#module-an.library.ids) — asset ids, version labels, library references;
- [`an.library.stores`](an.library.stores.html.md#module-an.library.stores) — the mall: `records`, write-once `versions`,
  content-addressed `blobs`, all injected `MutableMapping` s;
- [`an.library.federation`](an.library.federation.html.md#module-an.library.federation) — [`Library`](#an.library.Library) and the search path;
- [`an.library.affordances`](an.library.affordances.html.md#module-an.library.affordances) — capabilities and per-kind analysers (the seed
  of ADR 0002’s registry); [`an.library.character`](an.library.character.html.md#module-an.library.character) — the character analyser;
- [`an.library.rights`](an.library.rights.html.md#module-an.library.rights) — the most-restrictive roll-up over `AssetSource`;
  [`an.library.floor`](an.library.floor.html.md#module-an.library.floor) — the strictest statement any library on the machine
  > makes about a blob; [`an.library.registry`](an.library.registry.html.md#module-an.library.registry) — the machine’s registry of
  > library roots the floor reads, independent of the environment;
- [`an.library.api`](an.library.api.html.md#module-an.library.api) — `publish`, `find`, `vocabulary`, `show`,
  `promote`; [`an.library.checkout`](#an.library.checkout) — `checkout`, `verify_checkout`,
  `check_pins`, `drift_findings` (both run by `an validate`);
  [`an.library.lock`](an.library.lock.html.md#module-an.library.lock) — the project lockfile (a project store,
  > `mall["library_lock"]`);
- [`an.library.cli`](an.library.cli.html.md#module-an.library.cli) — `an library …`, a projection of the same functions.

### Functions

| [`analyse`](#an.library.analyse)(kind, doc[, art])                          | `(profile, analysers)` of one subject: its capabilities and the analyser versions used.                                                       |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| [`build_library_mall`](#an.library.build_library_mall)([root, package])                | The library mall of `package`: `records`, `versions` (write-once), `blobs` (CAS).                                                             |
| [`check_pins`](#an.library.check_pins)(scene, lock)                            | Findings where a scene's `AssetRef.library` and the project lockfile disagree.                                                                |
| [`checkout`](#an.library.checkout)(libraries, project_dir, ref, \*[, ...])   | Materialise a library version into a project, carry its rights, pin it.                                                                       |
| [`drift_findings`](#an.library.drift_findings)([project_dir, mall, lock, ...])     | One `info` Finding per checked-out entry that is no longer — or cannot be shown to be — its pinned version.                                   |
| [`effective_rights`](#an.library.effective_rights)(libraries, version, \*[, ...])    | The rights of a version, recomputed from its sources, its lineage and its bytes.                                                              |
| [`find`](#an.library.find)(libraries, \*[, kind, style, affords, ...])   | Assets matching every facet given (AND across facets, OR within one facet's values).                                                          |
| [`library_root`](#an.library.library_root)([root, package, environ, platform])   | The data root of `package` — its library and its projects live under it.                                                                      |
| [`open_library`](#an.library.open_library)([package, root])                      | The library of `package`, at `root` (resolved as in [`an.library.root`](an.library.root.html.md#module-an.library.root)). |
| [`parse_ref`](#an.library.parse_ref)(text, \*[, require_version, ...])        | Parse a library reference.                                                                                                                    |
| [`project_dir`](#an.library.project_dir)(project_id[, root, package, environ])  | The default directory of the agent-made project `project_id` (design §7.5).                                                                   |
| [`projects_root`](#an.library.projects_root)([root, package, environ])            | Where agent-made projects go by default: `<root>/projects/`.                                                                                  |
| [`promote`](#an.library.promote)(libraries, ref, \*[, to, as_id, ...])      | Copy one version into another library — by default the core `an` library.                                                                     |
| [`publish`](#an.library.publish)(library, asset_id, doc[, files, ...])      | Publish `doc` and its `files` as the next version of `asset_id` in `library`.                                                                 |
| [`publish_dir`](#an.library.publish_dir)(library, folder, asset_id, \*\*kwargs) | Publish an asset folder as it sits in a project store (`assets/characters/alice/`).                                                           |
| [`reindex`](#an.library.reindex)(library, \*[, search])                     | Rebuild `library`'s floor index from its versions.                                                                                            |
| [`register_analyser`](#an.library.register_analyser)(kind, \*[, version, ...])        | Register an analyser.                                                                                                                         |
| [`register_asset_kind`](#an.library.register_asset_kind)(name, \*[, store, ...])        | Register (or re-register) an asset kind.                                                                                                      |
| [`register_capability`](#an.library.register_capability)(name, \*[, description, ...])  | Register a capability (or a [`Capability`](#an.library.Capability)).                                                     |
| [`register_root`](#an.library.register_root)(package, root, \*[, registry])       | Record `root` (`package`'s library root) in the registry; `True` if it was new.                                                               |
| [`registered_roots`](#an.library.registered_roots)(\*[, registry])                   | `(package, root)` for every root ever registered, oldest first, each once.                                                                    |
| [`resolve`](#an.library.resolve)(libraries, ref)                            | `(library, pinned_ref, version_doc)` for a reference, along the search path.                                                                  |
| [`roll_up`](#an.library.roll_up)(sources, \*[, inherited])                  | Roll labelled sources (and parents' rights) up to one [`Rights`](#an.library.Rights).                                |
| [`scan_index`](#an.library.scan_index)(library)                                | Every asset's head version in `library`, read from the stores.                                                                                |
| [`search_path`](#an.library.search_path)([package, extra, roots])               | The ordered libraries `package` reads: its own, then the core `an`, then `extra`.                                                             |
| [`show`](#an.library.show)(libraries, ref)                               | The record, the resolved version, its recomputed rights and the list of versions.                                                             |
| [`verify_checkout`](#an.library.verify_checkout)(libraries, project_dir, \*[, ...]) | `{<store>/<key>: differences}` for every pinned entry; empty lists are intact copies.                                                         |
| [`vocabulary`](#an.library.vocabulary)(libraries, \*[, index])                 | Every facet with its values and counts, and the registered capabilities.                                                                      |

### Classes

| [`Capability`](#an.library.Capability)(name, description, remedy[, ...])      | A registered capability: its name, what it means, and how to add it.                 |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`CheckoutResult`](#an.library.CheckoutResult)(ref, store, key, ...)              | Where a checked-out version landed in the project, and its pin.                      |
| [`FindResult`](#an.library.FindResult)(hits, near, counts)                    | Hits, near misses (with `near=True`), and per-facet value counts over the hits.      |
| [`Hit`](#an.library.Hit)(library, asset_id, version, score[, ...])     | One asset that answers a query — or nearly does (`missing` non-empty).               |
| [`Library`](#an.library.Library)(name, mall[, root])                       | One library: its name (the namespace of its ids), its mall, and its root if on disk. |
| [`LibraryRef`](#an.library.LibraryRef)(asset_id[, version, namespace])        | A parsed `[<namespace>:]<asset_id>[@<version>]`.                                     |
| [`ProjectLock`](#an.library.ProjectLock)(project_dir)                          | `<store>/<key> -> pin` over a project's `assets.lock.json`.                          |
| [`PublishResult`](#an.library.PublishResult)(ref, manifest_sha256, created, ...) | What a publish did: the version it names, and whether it made one.                   |
| [`Rights`](#an.library.Rights)(license_class[, reasons])                  | The rolled-up rights of one version, as stored on it.                                |

### Exceptions

| [`AssetIdError`](#an.library.AssetIdError)       | An asset id, version label or library reference that does not parse.                    |
|---------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`AssetNotFoundError`](#an.library.AssetNotFoundError) | No library on the search path holds the asset or version asked for.                     |
| [`CheckoutError`](#an.library.CheckoutError)      | A version cannot be materialised into this project as asked.                            |
| [`IntegrityError`](#an.library.IntegrityError)     | Stored bytes, paths or a stored manifest do not match what was recorded.                |
| [`LibraryError`](#an.library.LibraryError)       | A library operation refused, with a sentence saying why and what to do.                 |
| [`RegistryError`](#an.library.RegistryError)      | The machine's registry or statement memory cannot be read or written; nothing proceeds. |
| [`RightsRefusal`](#an.library.RightsRefusal)      | A private or unknown version would leave the user's library without an override.        |
| [`VersionExistsError`](#an.library.VersionExistsError) | A write-once key was written twice, or deleted.                                         |

### *exception* an.library.AssetIdError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

An asset id, version label or library reference that does not parse.

### *exception* an.library.AssetNotFoundError

Bases: [`LookupError`](https://docs.python.org/3/builtins/exceptions.html#LookupError)

No library on the search path holds the asset or version asked for.

### *class* an.library.Capability(name, description, remedy, subject='asset', command=None, version='1')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A registered capability: its name, what it means, and how to add it.

`command` is the CLI that adds it, when one exists (`an character
add-views`); `version` bumps when the *meaning* of the name changes (a
persisted name is never redefined in place).

#### to_json()

The capability as the generated docs and the MCP surface list it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *exception* an.library.CheckoutError

Bases: [`LibraryError`](an.library.api.html.md#an.library.api.LibraryError)

A version cannot be materialised into this project as asked.

### *class* an.library.CheckoutResult(ref, store, key, manifest_sha256, files, changed, rights)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Where a checked-out version landed in the project, and its pin.

#### asset_ref(entity_id=None)

An [`AssetRef`](an.ir.schema.html.md#an.ir.schema.AssetRef) casting this asset, pinned by `library`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### *class* an.library.FindResult(hits, near, counts)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Hits, near misses (with `near=True`), and per-facet value counts over the hits.

#### to_dict()

A JSON-ready view.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *class* an.library.Hit(library, asset_id, version, score, title=None, license_class='unknown', missing=<factory>, remedies=<factory>, federated=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One asset that answers a query — or nearly does (`missing` non-empty).

#### *property* ref *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

namespaced when the search spanned several libraries.

* **Type:**
  The reference to pin

#### to_dict()

A JSON-ready view (CLI `--json`, MCP).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *exception* an.library.IntegrityError

Bases: [`LibraryError`](an.library.api.html.md#an.library.api.LibraryError)

Stored bytes, paths or a stored manifest do not match what was recorded.

### *class* an.library.Library(name, mall, root=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One library: its name (the namespace of its ids), its mall, and its root if on disk.

#### *property* blob_rights *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)*

`sha256 -> {asset: statement}`, derived ([`an.library.floor`](an.library.floor.html.md#module-an.library.floor)).

#### *property* blobs *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)*

`sha256 -> bytes` (content-addressed).

#### *property* records *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)*

`asset_id -> record` (mutable curation).

#### *property* versions *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)*

`<asset_id>@<vNNN> -> version` (write-once).

### *exception* an.library.LibraryError

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

A library operation refused, with a sentence saying why and what to do.

### *class* an.library.LibraryRef(asset_id, version=None, namespace=None)

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
  [`LibraryRef`](an.library.ids.html.md#an.library.ids.LibraryRef)

#### with_version(version)

The same asset, another version.

* **Return type:**
  [`LibraryRef`](an.library.ids.html.md#an.library.ids.LibraryRef)

### *class* an.library.ProjectLock(project_dir)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`<store>/<key> -> pin` over a project’s `assets.lock.json`.

Every write rewrites the whole (small) file, sorted, so the lockfile diffs
cleanly under version control.

### *class* an.library.PublishResult(ref, manifest_sha256, created, rights, affordances)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a publish did: the version it names, and whether it made one.

### *exception* an.library.RegistryError

Bases: [`OSError`](https://docs.python.org/3/builtins/exceptions.html#OSError)

The machine’s registry or statement memory cannot be read or written; nothing proceeds.

### *class* an.library.Rights(license_class, reasons=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The rolled-up rights of one version, as stored on it.

#### *classmethod* from_dict(d)

Read a version’s `rights` block back.

* **Return type:**
  [`Rights`](an.library.rights.html.md#an.library.rights.Rights)

#### *property* publishable *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether a video containing this asset may ship.

#### to_dict()

The `rights` block of a version document.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *exception* an.library.RightsRefusal

Bases: [`PermissionError`](https://docs.python.org/3/builtins/exceptions.html#PermissionError)

A private or unknown version would leave the user’s library without an override.

### *exception* an.library.VersionExistsError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

A write-once key was written twice, or deleted. Versions are immutable.

### an.library.analyse(kind, doc, art=None)

`(profile, analysers)` of one subject: its capabilities and the analyser versions used.

A kind with no registered analyser affords nothing *derived* and records no
analyser — an honest empty answer, not a guess.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> analyse("no-such-kind", {})
({}, {})
```

### an.library.build_library_mall(root=None, , package='an', \*\*overrides)

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

### an.library.check_pins(scene, lock)

Findings where a scene’s `AssetRef.library` and the project lockfile disagree.

The lockfile is the source of truth (it is what the check-out wrote, beside
the files); the scene’s `library:` restates it. Two records of one pin can
drift — a re-check-out updates the lockfile, not the scene — so `an
validate` runs this on every project (an#240). Each disagreement, and each
`library:` the lockfile does not pin, is a `warning`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.library.checkout(libraries, project_dir, ref, , key=None, mall=None, lock=None, overwrite=False)

Materialise a library version into a project, carry its rights, pin it.

* **Return type:**
  [`CheckoutResult`](#an.library.CheckoutResult)

project_dir: the project to check out into
ref: `[<library>:]<asset_id>[@<version>]`; `latest` (or no version) is

> resolved now and pinned

key: the key in the project store (default: the asset id’s slug)
mall: the project mall (default: `build_project_mall(project_dir)`)
lock: the lockfile mapping (default: the mall’s `library_lock` store,

> `<project_dir>/assets.lock.json`)

overwrite: replace an existing entry that is not exactly this version — a
: local fork (any edited file or descriptor) or another asset; without it
  that is refused

An entry that already IS this version byte for byte — the folder a
`publish` just sent to the library, still unedited — is recognised and
linked (origin block, carried source, pin) without `overwrite`: publishing
a project’s asset and checking it back out is the natural first round trip.

Every stored path, blob and the manifest are verified before anything is
written, and every file is written inside the entry’s folder or not at all.
Editing the checked-out copy forks it; `publish` of the edited folder
sends it back as a new version derived from this one.

### an.library.drift_findings(project_dir=None, , mall=None, lock=None, libraries=None)

One `info` Finding per checked-out entry that is no longer — or cannot be shown to be — its pinned version.

An edited check-out is a fork, not a mistake — hence `info`: it says the
pin now records where the copy CAME FROM, not what it IS, so nothing may
treat the pin as standing for the content (an#240), and publishing the
folder would make a new version. A pin this machine cannot check (its
library is at a custom root, or elsewhere) is its own `info`, with no
advice to check anything out again — that could swap the asset for a
same-named other one.

project_dir: the project (not needed when both `mall` and `lock` are given)

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.library.effective_rights(libraries, version, \*, floor=<object object>, owner=None)

The rights of a version, recomputed from its sources, its lineage and its bytes.

owner: the library holding `version` (see `version_sources()`)

* **Return type:**
  [`Rights`](an.library.rights.html.md#an.library.rights.Rights)

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> _ = publish(lib, "prop.vase", {"name": "vase"},
...             source={"provider": "film", "license": "all-rights-reserved"})
>>> effective_rights(lib, read_version(lib, "prop.vase", "v001"), owner=lib).license_class
'private'
```

### an.library.find(libraries, \*, kind=None, style=None, affords=None, rights='any', family=None, origin=None, status=None, tags=None, art=None, near=False, index=<function scan_index>)

Assets matching every facet given (AND across facets, OR within one facet’s values).

* **Return type:**
  [`FindResult`](an.library.api.html.md#an.library.api.FindResult)

affords: capabilities the asset must ALL have — `limbs.legs`, or
: `swap.view:side` for a capability with a given key. Each capability is
  its own boolean facet, so a list of them is AND, as across facets. An
  unregistered name raises, naming the close ones

rights: `any` (default — study renders are legitimate), `publishable`
: (`free` + `attribution`), or licence classes. Rights are recomputed
  from each version’s sources and lineage, not read from its cache

near: also return assets that pass every other facet but miss some
: capabilities, or are curated for another style than asked, each with
  what is missing and the remedy that would add it (a style mismatch is
  listed as `style:<wanted>`, remedied by restyling: an#271)

index: the index to read (default: a scan of the stores)

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> _ = publish(lib, "prop.lamp", {"name": "lamp"}, style=["reiniger", "gilliam"])
>>> [h.ref for h in find(lib, kind="prop", style="gilliam")]
['prop.lamp@v001']
>>> len(find(lib, kind="prop", rights="publishable"))  # no source: unknown
0
```

### an.library.library_root(root=None, , package='an', environ=None, platform=None)

The data root of `package` — its library and its projects live under it.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

root: an explicit root; wins over everything
package: the package whose root this is (`an` for the core library, a

> genre’s own name for its library)

environ: the environment to read (default `os.environ`; injectable for tests)
platform: `sys.platform` value to resolve for (default: this one)

```pycon
>>> library_root("~/x", package="an").name
'x'
```

### an.library.open_library(package='an', root=None, \*\*overrides)

The library of `package`, at `root` (resolved as in [`an.library.root`](an.library.root.html.md#module-an.library.root)).

* **Return type:**
  [`Library`](an.library.federation.html.md#an.library.federation.Library)

overrides: stores to inject (`records`, `versions`, `blobs`), as in
: [`an.library.stores.build_library_mall()`](an.library.stores.html.md#an.library.stores.build_library_mall)

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> (lib.name, lib.root)
('an', None)
```

### an.library.parse_ref(text, , require_version=False, require_pin=False)

Parse a library reference.

`require_version=True` refuses a reference with no `@<version>`;
`require_pin=True` also refuses `@latest` — the grammar of
`AssetRef.library`, where a floating reference would make a render depend
on whatever the library’s head is that day.

* **Return type:**
  [`LibraryRef`](an.library.ids.html.md#an.library.ids.LibraryRef)

```pycon
>>> parse_ref("character.alice")
LibraryRef(asset_id='character.alice', version=None, namespace=None)
>>> parse_ref("character.alice@sha256:0a1b2c3d").version
'sha256:0a1b2c3d'
>>> parse_ref("character.alice", require_version=True)
Traceback (most recent call last):
AssetIdError: ...
```

### an.library.project_dir(project_id, root=None, , package='an', environ=None)

The default directory of the agent-made project `project_id` (design §7.5).

`an init <dir>` with an explicit directory keeps working anywhere; this is
the default for projects an agent makes (`an init --id <id>`), so they
never land in a session’s working folder or a repository. `package` is
the library package of the genre the video is made in
([`an.genres.genre_library()`](an.genres.html.md#an.genres.genre_library); the core’s, `an`, by default — the core
names no genre).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> project_dir("alice-and-bob", "/lib").as_posix()
'/lib/projects/alice-and-bob'
>>> project_dir("../escape", "/lib")
Traceback (most recent call last):
ValueError: ...
```

### an.library.projects_root(root=None, , package='an', environ=None)

Where agent-made projects go by default: `<root>/projects/`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> projects_root("/lib", package="cutan").as_posix()
'/lib/projects'
```

### an.library.promote(libraries, ref, , to=None, as_id=None, allow_restricted=False)

Copy one version into another library — by default the core `an` library.

An asset made in a genre’s library and reused across genres is promoted to the
core (plan §1 decision 7). The copy is a new version in the target, derived
from the source version, with the record’s curation carried over.

- A `private` or `unknown` version is refused unless
  `allow_restricted=True`: private-study material never leaves its library
  by default (ADR 0005 decision 10). The rights checked are recomputed from
  the version’s sources and lineage, and the stricter of those and the
  stored ones wins.
- If the target already has an asset with this id that does not derive from
  the one promoted (another character that happens to share the id), it is
  refused: promoting would make it a new version of an unrelated asset.
  `as_id` promotes under another id.

* **Return type:**
  [`PublishResult`](an.library.api.html.md#an.library.api.PublishResult)

### an.library.publish(library, asset_id, doc, files=None, \*, source=None, relicense=None, relabel=None, derived_from=(), title=None, family=None, style=None, origin=None, status=None, tags=None, replace_curation=False, note=None, expect_head=<object object>, search=None, carry_source=True)

Publish `doc` and its `files` as the next version of `asset_id` in `library`.

library: the owning library (writes never go to a search path)
asset_id: `<kind>.<slug>`; the kind must be registered
doc: the descriptor — the existing document `an` already versions

> (`CharacterDescriptor`, …), as a model or its JSON dict, stored verbatim

files: the asset’s files, by the relative paths the descriptor uses
: (`parts/head.svg`) — stored once each in the content-addressed blobs

source: provenance declared for the asset as a whole. It contributes BESIDE
: the descriptor’s own `source` (the most restrictive wins), never
  instead of it. With no `source`, and a descriptor declaring nothing
  or exactly what the head’s declared, the source of the previous version
  carries forward (`carry_source`) — for the bytes it was declared on
  only: a file changed or added since is recorded as `unlabelled` on the
  version and is `unknown`. Later versions inherit that gap through
  `previous` even when they pass `source=`; `relabel` (or a
  relicence) answers it. With no source at all the version is `unknown`
  — recorded and visible, not refused

relicense: `{"by": who, "reason": why}` — the ONLY way to relax rights.
: Rights attach to the bytes and the lineage: a new version inherits the
  version it follows (`previous`), every version it derives from, and
  every version holding the same file bytes, and may only be more
  restrictive than they are — a cc0 in the descriptor or in `source=`
  never relabels private art. A relicence makes `source` (required) the
  whole statement, records who and why on the version (and in its
  manifest and reasons), and covers these bytes for later versions

relabel: `{"by": who, "reason": why}` beside an explicit `source=`
: (required) — a first statement about bytes NOBODY labelled (an#263):
  the gaps of this asset’s own version chain (files an earlier version
  recorded `unlabelled`, an earlier version with no source at all) are
  answered with `source`. It relaxes no statement anyone made: a private
  (or any) licence, a per-part source, a version this one derives from,
  and every other asset’s statement about the same bytes still bind.
  Recorded on the version, in its manifest and in its reasons

derived_from: library references this version derives from (an earlier version,
: the original of a recolour); each must resolve, and its rights are inherited.
  A descriptor checked out of a library derives from its origin by default

title, family, style, origin, status, tags: curation, stored on the record;
: given again with unchanged content they update the record and make no
  version. `style` and `tags` add to what is there, or replace it with
  `replace_curation=True`

note: what changed, stored on the version
expect_head: guard against publishing into an asset you did not mean:

> `None` — the id must be new; `"vNNN"` — the head must be that version

search: further libraries where `derived_from` references resolve (the
: owning library is always searched first)

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> doc = {"name": "lamp", "source": {"provider": "me", "license": "cc0-1.0"}}
>>> r = publish(lib, "prop.lamp", doc, {"parts/lamp.svg": b"<svg/>"}, style="reiniger")
>>> str(r.ref), r.created, r.rights.license_class
('an:prop.lamp@v001', True, 'free')
>>> publish(lib, "prop.lamp", doc, {"parts/lamp.svg": b"<svg/>"}).created
False
```

* **Return type:**
  [`PublishResult`](an.library.api.html.md#an.library.api.PublishResult)

### an.library.publish_dir(library, folder, asset_id, \*\*kwargs)

Publish an asset folder as it sits in a project store (`assets/characters/alice/`).

The descriptor is the kind’s descriptor file (`character.json`); every other
file under the folder is published as one of the asset’s files, so a
check-out reproduces the folder — except operating-system clutter
(`.DS_Store`, hidden files, `Thumbs.db`: `an.stores._common.is_os_junk()`)
that the descriptor does not name — a part it names is published whatever
its file is called (review-288 S2). Keyword arguments go to [`publish()`](#an.library.publish).

* **Return type:**
  [`PublishResult`](an.library.api.html.md#an.library.api.PublishResult)

### an.library.register_analyser(kind, , version='', subject='asset', owner='an')

Register an analyser. Two forms.

`register_analyser(Analyser(...), owner=...)` registers the object and
returns it (a genre’s `analysers` field goes this way). With a `kind`
string it is a decorator: `@register_analyser("character", version="0.1.0")`
registers the decorated derivation.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.library.register_asset_kind(name, , store=None, descriptor=None, credits_store=None)

Register (or re-register) an asset kind. Returns it.

* **Return type:**
  [`AssetKind`](an.library.kinds.html.md#an.library.kinds.AssetKind)

### an.library.register_capability(name, , description='', remedy='', subject='asset', command=None, version='1', owner='an')

Register a capability (or a [`Capability`](#an.library.Capability)). Returns it.

Re-registering the same definition is a no-op; a different definition
under a name another owner holds raises, because capability names are
persisted and two meanings for one name would make a stored facet lie.

* **Return type:**
  [`Capability`](an.capabilities.html.md#an.capabilities.Capability)

```pycon
>>> cap = register_capability("demo.thing", description="a thing", remedy="add one", owner="demo")
>>> CAPABILITIES["demo.thing"] is cap
True
>>> _ = drop_owner("demo")
```

### an.library.register_root(package, root, , registry=None)

Record `root` (`package`’s library root) in the registry; `True` if it was new.

Idempotent. Raises [`RegistryError`](#an.library.RegistryError) when the registry cannot be read
or written: a library the floor cannot find later must not be written to.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.library.registered_roots(, registry=None)

`(package, root)` for every root ever registered, oldest first, each once.

A line that does not parse (a torn append) is skipped; existence is the
caller’s to check. A registry that exists but cannot be read raises
[`RegistryError`](#an.library.RegistryError).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]]

### an.library.reindex(library, , search=None)

Rebuild `library`’s floor index from its versions. Returns the number of blobs indexed.

The index is derived data: rebuilding it is always safe, and the way to
repair a library whose index was lost or written by an older `an`. It also
(re-)registers the library’s root in the machine registry
([`an.library.registry`](an.library.registry.html.md#module-an.library.registry)), so a library made at a custom root before the
registry existed becomes visible to every other library’s rights floor.

The new index is computed in full first, then written over the old one
entry by entry, and only then are stale entries removed: a crash midway
leaves old and new statements side by side, never an empty floor (an#249
R4-N4).

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.library.resolve(libraries, ref)

`(library, pinned_ref, version_doc)` for a reference, along the search path.

A namespaced reference reads only its library; a bare one reads the first
library holding the asset. `latest` resolves to that library’s head and
`sha256:<prefix>` to the one version whose manifest hash starts with it.
The returned reference is pinned (`vNNN`) and namespaced with the library
it resolved in.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Library`](an.library.federation.html.md#an.library.federation.Library), [`LibraryRef`](an.library.ids.html.md#an.library.ids.LibraryRef), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.library.roll_up(sources, , inherited=())

Roll labelled sources (and parents’ rights) up to one [`Rights`](#an.library.Rights).

A `None` source is `unknown`. The reasons name every contributor of the
winning class, so a reader sees *why* a version is restricted.

* **Return type:**
  [`Rights`](an.library.rights.html.md#an.library.rights.Rights)

```pycon
>>> roll_up([("asset", None)]).to_dict()
{'license_class': 'unknown', 'publishable': False, 'reasons': ['asset: no source recorded (unknown)']}
```

### an.library.scan_index(library)

Every asset’s head version in `library`, read from the stores.

Affordances snapshotted by an older analyser are recomputed, not trusted. A
record or version that cannot be read (a damaged file) is skipped with a
`LibraryIndexWarning` naming it, so one bad entry never blinds every
search.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`IndexEntry`](an.library.api.html.md#an.library.api.IndexEntry)]

### an.library.search_path(package='an', , extra=(), roots=None)

The ordered libraries `package` reads: its own, then the core `an`, then `extra`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Library`](an.library.federation.html.md#an.library.federation.Library)]

extra: further libraries, by package name (resolved like any root) or as
: [`Library`](#an.library.Library) objects (a team share, a seed library)

roots: an explicit root per package name (tests, a non-default layout);
: unnamed packages resolve as usual (`<PKG>_HOME`, then the data folder)

A name appears once, at its first position.

### an.library.show(libraries, ref)

The record, the resolved version, its recomputed rights and the list of versions.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> _ = publish(lib, "prop.lamp", {"name": "lamp"}, title="A lamp")
>>> s = show(lib, "prop.lamp")
>>> s["ref"], s["record"]["title"], s["versions"]
('an:prop.lamp@v001', 'A lamp', ['v001'])
```

### an.library.verify_checkout(libraries, project_dir, , mall=None, lock=None)

`{<store>/<key>: differences}` for every pinned entry; empty lists are intact copies.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

libraries: where the pinned versions resolve (`None`: the library each
: pin names, at its default root — `pinned_libraries()`)

What makes a pin usable as more than provenance: an entry with no
differences is byte-for-byte the version its pin names. An entry whose
pinned version cannot be found, or is found with another manifest (a
same-named asset in another library), reads `["cannot verify: …"]` —
never as an edit.

### an.library.vocabulary(libraries, \*, index=<function scan_index>)

Every facet with its values and counts, and the registered capabilities.

What an agent reads to turn words into a typed query (spectrum (b)): “a
Reiniger character who can walk in profile” → `style=reiniger`,
`affords=["limbs.legs", "swap.view:side"]`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> v = vocabulary(lib)
>>> sorted(v)
['capabilities', 'facets', 'kinds', 'rights', 'statuses']
>>> "limbs.legs" in v["capabilities"]
True
```

### Modules

| [`affordances`](an.library.affordances.html.md#module-an.library.affordances)   | Affordances for the library: the capability registry, re-exported from [`an.capabilities`](an.capabilities.html.md#module-an.capabilities).              |
|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`api`](an.library.api.html.md#module-an.library.api)                   | The library's verbs: `publish`, `find`, `vocabulary`, `show`, `promote`.                                                                                                     |
| [`character`](an.library.character.html.md#module-an.library.character)       | The character analyser: legs, arms, views and mouth chart, derived from the rig.                                                                                             |
| [`cli`](an.library.cli.html.md#module-an.library.cli)                   | `an library …` — the asset library from the shell, over the same functions as Python.                                                                                        |
| [`federation`](an.library.federation.html.md#module-an.library.federation)     | Libraries federated by a search path: one read view, writes to the owner (plan §1 decision 7).                                                                               |
| [`floor`](an.library.floor.html.md#module-an.library.floor)               | The rights floor of a blob: the strictest statement any library on this machine makes about its bytes.                                                                       |
| [`ids`](an.library.ids.html.md#module-an.library.ids)                   | Asset ids, version labels and library references — the library's persisted names.                                                                                            |
| [`kinds`](an.library.kinds.html.md#module-an.library.kinds)               | Asset kinds: the `kind` facet's vocabulary, and where each kind lives in a project.                                                                                          |
| [`lock`](an.library.lock.html.md#module-an.library.lock)                 | The project lockfile, as the asset library sees it (re-exported from [`an.stores.library_lock`](an.stores.library_lock.html.md#module-an.stores.library_lock)). |
| [`registry`](an.library.registry.html.md#module-an.library.registry)         | The machine's memory of its libraries: every root ever written, and every statement ever made (an#249).                                                                      |
| [`rights`](an.library.rights.html.md#module-an.library.rights)             | Rights on every version: the most restrictive licence class wins (ADR 0005 decision 10, design §9).                                                                          |
| [`root`](an.library.root.html.md#module-an.library.root)                 | Where a package's library lives on disk: one root per package (ADR 0005 §2, plan §1 decisions 7–8).                                                                          |
| [`stores`](an.library.stores.html.md#module-an.library.stores)             | The library mall: `records`, `versions` and `blobs`, each an injected `MutableMapping`.                                                                                      |
