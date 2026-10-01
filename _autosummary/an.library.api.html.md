# an.library.api

The library’s verbs: `publish`, `find`, `vocabulary`, `show`, `promote`.

Plain functions over [`Library`](an.library.federation.html.md#an.library.federation.Library) objects (pillar 8:
the functions are the API; the `an library …` CLI and, later, MCP are thin
projections of them). Writes take the one owning library; reads take a library
or a search path ([`search_path()`](an.library.federation.html.md#an.library.federation.search_path)). Check-out lives
in [`an.library.checkout`](an.library.html.md#an.library.checkout).

The documents they write (ADR 0005 decision 4, design §4):

- a **record** per asset — identity and curation, mutable: `id`, `kind`,
  `title`, `family`, `head`, `status`, `facets` (`style`, `origin`),
  `tags`;
- a **version** per publish — immutable: the descriptor `doc` verbatim, its
  `files` as `dol.content.ContentRef` s, the asset-level `source`,
  `derived_from`, the derived `affordances` with the `analysers` that made
  them, the rolled-up `rights`, the `art` facet, and `manifest_sha256` —
  the **version identity**: the hash of `doc`, the files’ hashes, `source`
  and `derived_from`. It is not a content key (lineage changes it, and a
  checked-out copy can be edited after it is pinned); nothing should cache on it
  as one. Publishing what the head already is makes no new version.

**Rights are recomputed, not trusted.** The stored `rights` block is a cache of
[`effective_rights()`](#an.library.api.effective_rights), which rolls up — most restrictive wins — the asset-level
source, the descriptor’s own source, every part’s, and recursively every version
the asset derives from. `promote` and `find(rights=…)` recompute it.

### Module Attributes

| [`LIBRARY_ERRORS`](#an.library.api.LIBRARY_ERRORS)   | the CLI prints these as a sentence and exits non-zero.   |
|-------------------------------------------------------------------|----------------------------------------------------------|

### Functions

| [`effective_rights`](#an.library.api.effective_rights)(libraries, version, \*[, floor])   | The rights of a version, recomputed from its sources, its lineage and its bytes.      |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [`find`](#an.library.api.find)(libraries, \*[, kind, style, affords, ...])    | Assets matching every facet given (AND across facets, OR within one facet's values).  |
| [`promote`](#an.library.api.promote)(libraries, ref, \*[, to, as_id, ...])       | Copy one version into another library — by default the core `an` library.             |
| [`publish`](#an.library.api.publish)(library, asset_id, doc[, files, ...])       | Publish `doc` and its `files` as the next version of `asset_id` in `library`.         |
| [`publish_dir`](#an.library.api.publish_dir)(library, folder, asset_id, \*\*kwargs)  | Publish an asset folder as it sits in a project store (`assets/characters/alice/`).   |
| [`reindex`](#an.library.api.reindex)(library, \*[, search])                      | Rebuild `library`'s floor index from its versions.                                    |
| [`scan_index`](#an.library.api.scan_index)(library)                                 | Every asset's head version in `library`, read from the stores.                        |
| [`show`](#an.library.api.show)(libraries, ref)                                | The record, the resolved version, its recomputed rights and the list of versions.     |
| [`version_sources`](#an.library.api.version_sources)(libraries, version, \*[, ...])      | Every labelled source a version's rights depend on — its own, its lineage, its bytes. |
| [`vocabulary`](#an.library.api.vocabulary)(libraries, \*[, index])                  | Every facet with its values and counts, and the registered capabilities.              |

### Classes

| [`FindResult`](#an.library.api.FindResult)(hits, near, counts)                    | Hits, near misses (with `near=True`), and per-facet value counts over the hits.   |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`Hit`](#an.library.api.Hit)(library, asset_id, version, score[, ...])     | One asset that answers a query — or nearly does (`missing` non-empty).            |
| [`IndexEntry`](#an.library.api.IndexEntry)(library, asset_id, version, kind, ...) | One asset's head version, as the index sees it.                                   |
| [`PublishResult`](#an.library.api.PublishResult)(ref, manifest_sha256, created, ...) | What a publish did: the version it names, and whether it made one.                |

### Exceptions

| [`CheckoutError`](#an.library.api.CheckoutError)         | A version cannot be materialised into this project as asked.                     |
|------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`IntegrityError`](#an.library.api.IntegrityError)        | Stored bytes, paths or a stored manifest do not match what was recorded.         |
| [`LibraryError`](#an.library.api.LibraryError)          | A library operation refused, with a sentence saying why and what to do.          |
| [`LibraryIndexWarning`](#an.library.api.LibraryIndexWarning)   | A record or version could not be read; the index skipped it.                     |
| [`PlaceholderRigWarning`](#an.library.api.PlaceholderRigWarning) | A character published with no rig: the compiler would draw only its placeholder. |

### *exception* an.library.api.CheckoutError

Bases: [`LibraryError`](#an.library.api.LibraryError)

A version cannot be materialised into this project as asked.

### *class* an.library.api.FindResult(hits, near, counts)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Hits, near misses (with `near=True`), and per-facet value counts over the hits.

#### to_dict()

A JSON-ready view.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *class* an.library.api.Hit(library, asset_id, version, score, title=None, license_class='unknown', missing=<factory>, remedies=<factory>, federated=False)

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

### *class* an.library.api.IndexEntry(library, asset_id, version, kind, record, rights, affordances, art, document=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One asset’s head version, as the index sees it.

#### affordance_terms()

Every query term this entry satisfies: `cap` and each `cap:key`.

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### facet_values()

Every facet’s values for this entry (the AND/OR matcher’s input).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### *exception* an.library.api.IntegrityError

Bases: [`LibraryError`](#an.library.api.LibraryError)

Stored bytes, paths or a stored manifest do not match what was recorded.

### an.library.api.LIBRARY_ERRORS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[type](https://docs.python.org/3/builtins/functions.html#type)[[BaseException](https://docs.python.org/3/builtins/exceptions.html#BaseException)], ...]* *= (<class 'an.library.api.LibraryError'>, <class 'an.library.ids.AssetIdError'>, <class 'an.library.federation.AssetNotFoundError'>, <class 'an.library.stores.VersionExistsError'>, <class 'an.library.rights.RightsRefusal'>, <class 'an.library.kinds.UnknownKindError'>, <class 'an.library.registry.RegistryError'>)*

the CLI
prints these as a sentence and exits non-zero.

* **Type:**
  Every error a library verb raises for a caller’s mistake (not a bug)

### *exception* an.library.api.LibraryError

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

A library operation refused, with a sentence saying why and what to do.

### *exception* an.library.api.LibraryIndexWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A record or version could not be read; the index skipped it.

### *exception* an.library.api.PlaceholderRigWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A character published with no rig: the compiler would draw only its placeholder.

### *class* an.library.api.PublishResult(ref, manifest_sha256, created, rights, affordances)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a publish did: the version it names, and whether it made one.

### an.library.api.effective_rights(libraries, version, \*, floor=<object object>)

The rights of a version, recomputed from its sources, its lineage and its bytes.

* **Return type:**
  [`Rights`](an.library.rights.html.md#an.library.rights.Rights)

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> _ = publish(lib, "prop.vase", {"name": "vase"},
...             source={"provider": "film", "license": "all-rights-reserved"})
>>> effective_rights(lib, read_version(lib, "prop.vase", "v001")).license_class
'private'
```

### an.library.api.find(libraries, \*, kind=None, style=None, affords=None, rights='any', family=None, origin=None, status=None, tags=None, art=None, near=False, index=<function scan_index>)

Assets matching every facet given (AND across facets, OR within one facet’s values).

* **Return type:**
  [`FindResult`](#an.library.api.FindResult)

affords: capabilities the asset must ALL have — `limbs.legs`, or
: `swap.view:side` for a capability with a given key. Each capability is
  its own boolean facet, so a list of them is AND, as across facets. An
  unregistered name raises, naming the close ones

rights: `any` (default — study renders are legitimate), `publishable`
: (`free` + `attribution`), or licence classes. Rights are recomputed
  from each version’s sources and lineage, not read from its cache

near: also return assets that pass every other facet but miss some
: capabilities, each with what is missing and the remedy that would add it

index: the index to read (default: a scan of the stores)

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> _ = publish(lib, "prop.lamp", {"name": "lamp"}, style=["reiniger", "gilliam"])
>>> [h.ref for h in find(lib, kind="prop", style="gilliam")]
['prop.lamp@v001']
>>> len(find(lib, kind="prop", rights="publishable"))  # no source: unknown
0
```

### an.library.api.promote(libraries, ref, , to=None, as_id=None, allow_restricted=False)

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
  [`PublishResult`](#an.library.api.PublishResult)

### an.library.api.publish(library, asset_id, doc, files=None, \*, source=None, relicense=None, derived_from=(), title=None, family=None, style=None, origin=None, status=None, tags=None, replace_curation=False, note=None, expect_head=<object object>, search=None, carry_source=True)

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
  version and is `unknown` until a publish passes `source=` (or a
  relicence) again; with no source at all the version is `unknown` —
  recorded and visible, not refused

relicense: `{"by": who, "reason": why}` — the ONLY way to relax rights.
: Rights attach to the bytes and the lineage: a new version inherits the
  version it follows (`previous`), every version it derives from, and
  every version holding the same file bytes, and may only be more
  restrictive than they are — a cc0 in the descriptor or in `source=`
  never relabels private art. A relicence makes `source` (required) the
  whole statement, records who and why on the version (and in its
  manifest and reasons), and covers these bytes for later versions

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
  [`PublishResult`](#an.library.api.PublishResult)

### an.library.api.publish_dir(library, folder, asset_id, \*\*kwargs)

Publish an asset folder as it sits in a project store (`assets/characters/alice/`).

The descriptor is the kind’s descriptor file (`character.json`); every other
file under the folder is published as one of the asset’s files, so a
check-out reproduces the folder — except operating-system clutter
(`.DS_Store`, hidden files, `Thumbs.db`: `an.stores._common.is_os_junk()`). Keyword arguments go to [`publish()`](#an.library.api.publish).

* **Return type:**
  [`PublishResult`](#an.library.api.PublishResult)

### an.library.api.reindex(library, , search=None)

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

### an.library.api.scan_index(library)

Every asset’s head version in `library`, read from the stores.

Affordances snapshotted by an older analyser are recomputed, not trusted. A
record or version that cannot be read (a damaged file) is skipped with a
[`LibraryIndexWarning`](#an.library.api.LibraryIndexWarning) naming it, so one bad entry never blinds every
search.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`IndexEntry`](#an.library.api.IndexEntry)]

### an.library.api.show(libraries, ref)

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

### an.library.api.version_sources(libraries, version, \*, floor=<object object>, \_prefix='', \_seen=None)

Every labelled source a version’s rights depend on — its own, its lineage, its bytes.

- its own ([`an.library.rights.sources_in()`](an.library.rights.html.md#an.library.rights.sources_in): asset-level, descriptor, parts);
- the version it follows (`previous`) and each `derived_from` version,
  recursively, labelled `<ref> > <label>`;
- the **floor** of every file: what any OTHER asset in any library on this
  machine says about the same bytes ([`an.library.floor`](an.library.floor.html.md#module-an.library.floor)), labelled
  `<path>: same bytes as <asset>@<version>`. A blob is as restricted as the
  strictest statement made about it anywhere.

floor: a [`BlobFloor`](an.library.floor.html.md#an.library.floor.BlobFloor) to read (default: every
: library on the machine); `None` leaves the floor out — what the
  version itself says (its “asset label”), which is what the floor stores

A version carrying an explicit `relicense` (who, why) contributes its
asset-level source alone: that recorded statement replaces everything it
would otherwise inherit, and is the only way to relax rights. A parent no
library on the path holds falls back to the rights recorded at publish, or
`unknown` — never silence.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]]

### an.library.api.vocabulary(libraries, \*, index=<function scan_index>)

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
