# an.library.api

The library’s verbs: `publish`, `find`, `vocabulary`, `show`, `promote`, `retire`.

Plain functions over [`Library`](an.library.federation.md#an.library.federation.Library) objects (pillar 8:
the functions are the API; the `an library …` CLI and, later, MCP are thin
projections of them). Writes take the one owning library; reads take a library
or a search path ([`search_path()`](an.library.federation.md#an.library.federation.search_path)). Check-out lives
in [`an.library.checkout`](an.library.md#an.library.checkout).

The documents they write (ADR 0005 decision 4, design §4):

- a **record** per asset — identity and curation, mutable: `id`, `kind`,
  `title`, `family`, `head`, `status` (`retired` hides it from
  `find`: [`retire()`](#an.library.api.retire)), its append-only `status_history`, `facets`
  (`style`, `origin`), `tags`;
- a **label** per relabel of a version’s unchanged content (an#307) —
  append-only, keyed by the hash of what it says: the source, who and why,
  and the rights it gave the version; a version’s rights read its labels;
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

| [`effective_rights`](#an.library.api.effective_rights)(libraries, version, \*[, ...])    | The rights of a version, recomputed from its sources, its lineage and its bytes.      |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [`find`](#an.library.api.find)(libraries, \*[, kind, style, affords, ...])   | Assets matching every facet given (AND across facets, OR within one facet's values).  |
| [`promote`](#an.library.api.promote)(libraries, ref, \*[, to, as_id, ...])      | Copy one version into another library — by default the core `an` library.             |
| [`publish`](#an.library.api.publish)(library, asset_id, doc[, files, ...])      | Publish `doc` and its `files` as the next version of `asset_id` in `library`.         |
| [`publish_dir`](#an.library.api.publish_dir)(library, folder, asset_id, \*\*kwargs) | Publish an asset folder as it sits in a project store (`assets/characters/alice/`).   |
| [`reindex`](#an.library.api.reindex)(library, \*[, search])                     | Rebuild `library`'s floor index from its versions.                                    |
| [`retire`](#an.library.api.retire)(library, asset_id, \*, by, reason)          | Retire an asset id: recorded, hidden from `find` by default, never deleted.           |
| [`scan_index`](#an.library.api.scan_index)(library)                                | Every asset's head version in `library`, read from the stores.                        |
| [`set_status`](#an.library.api.set_status)(library, asset_id, status, \*, by, ...) | Set an asset's curation status, recording who and why; return the record.             |
| [`show`](#an.library.api.show)(libraries, ref)                               | The record, the resolved version, its recomputed rights and the list of versions.     |
| [`unknown_advice`](#an.library.api.unknown_advice)(libraries, version, \*[, ...])      | What would answer each `unknown` contributor of a version — one sentence per kind.    |
| [`version_labels`](#an.library.api.version_labels)(library, version)                   | The labels recorded on a stored version since it was published, oldest first.         |
| [`version_sources`](#an.library.api.version_sources)(libraries, version, \*[, ...])     | Every labelled source a version's rights depend on — its own, its lineage, its bytes. |
| [`vocabulary`](#an.library.api.vocabulary)(libraries, \*[, index])                 | Every facet with its values and counts, and the registered capabilities.              |

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

### *class* an.library.api.PublishResult(ref, manifest_sha256, created, rights, affordances, advice=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a publish did: the version it names, and whether it made one.

#### advice *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

what would answer each kind of gap, one
sentence each ([`unknown_advice()`](#an.library.api.unknown_advice)).

* **Type:**
  For an `unknown` result

### an.library.api.effective_rights(libraries, version, \*, floor=<object object>, owner=None)

The rights of a version, recomputed from its sources, its lineage and its bytes.

owner: the library holding `version` (see [`version_sources()`](#an.library.api.version_sources))

* **Return type:**
  [`Rights`](an.library.rights.md#an.library.rights.Rights)

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> _ = publish(lib, "prop.vase", {"name": "vase"},
...             source={"provider": "film", "license": "all-rights-reserved"})
>>> effective_rights(lib, read_version(lib, "prop.vase", "v001"), owner=lib).license_class
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

status: curation statuses; an asset whose status is hidden
: (`HIDDEN_STATUSES`: `retired`) is offered only when its status
  is asked for by name

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

### an.library.api.publish(library, asset_id, doc, files=None, \*, source=None, relicense=None, relabel=None, derived_from=(), title=None, family=None, style=None, origin=None, status=None, tags=None, replace_curation=False, note=None, expect_head=<object object>, search=None, carry_source=True, license_parts=None, file_sources=None)

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
  recorded `unlabelled`, files no person’s source spoke for, an earlier
  version with no source at all) are answered with `source`, and so is
  another asset’s silence about a file the chain held once and this
  version no longer holds (an#307). It relaxes no statement anyone made:
  a private (or any) licence, a per-part source, a version this one
  derives from, and every other asset’s statement about bytes this
  version holds still bind. On content that changed, recorded on the new
  version, in its manifest and in its reasons; on UNCHANGED content,
  recorded on the head in the append-only `labels` store
  ([`version_labels()`](#an.library.api.version_labels)) and no version is minted (an#307)

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

license_parts: `{glob: source}` — a per-file statement for every stored
: path a glob matches (`match_license_parts()`: `*` stays in one
  folder, `**` crosses folders, case-exact; a glob matching nothing,
  two globs disagreeing on a path, or a near miss refuse), each pinned
  to the file’s digest (an#345). Needs an asset-level `source` (given
  or carried): the files no glob names are stated with the version’s
  label computed WITHOUT these statements. A per-file statement never
  relaxes what the bytes already carry — the per-part source of the same
  file, the same bytes at another path, and every earlier statement of
  this asset’s chain or of a version it derives from about them: a
  looser one is refused unless `relicense` records who and why (the
  relicence then lists the digests it covers, and a per-file statement
  stricter than it keeps binding). At a later publish a statement is
  carried for its file while the bytes are unchanged; a file changed
  since is recorded `unlabelled`

file_sources: `{path: source}` — the same, by exact stored path (what a
: stored version holds; [`promote()`](#an.library.api.promote) passes it)

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
(`.DS_Store`, hidden files, `Thumbs.db`: `an.stores._common.is_os_junk()`)
that the descriptor does not name — a part it names is published whatever
its file is called (review-288 S2). Keyword arguments go to [`publish()`](#an.library.api.publish).

* **Return type:**
  [`PublishResult`](#an.library.api.PublishResult)

### an.library.api.reindex(library, , search=None)

Rebuild `library`’s floor index from its versions. Returns the number of blobs indexed.

Lineage resolves through `search` and then every library on this machine
([`an.library.floor.machine_libraries()`](an.library.floor.md#an.library.floor.machine_libraries)), so a promoted copy’s parent
in a genre’s library is read without being named (an#361).

The index is derived data: rebuilding it is always safe, and the way to
repair a library whose index was lost or written by an older `an`. It also
(re-)registers the library’s root in the machine registry
([`an.library.registry`](an.library.registry.md#module-an.library.registry)), so a library made at a custom root before the
registry existed becomes visible to every other library’s rights floor.

The new index is computed in full first, then written over the old one
entry by entry, and only then are stale entries removed: a crash midway
leaves old and new statements side by side, never an empty floor (an#249
R4-N4).

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.library.api.retire(library, asset_id, , by, reason)

Retire an asset id: recorded, hidden from `find` by default, never deleted.

Its versions stay readable — a project pinned to one still checks it out
and validates — and its rights statements still bind the floor (retiring
is curation, not a relabel). `find(status="retired")` lists it; a publish
into it is refused unless it passes `status=` to revive it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> _ = publish(lib, "prop.dead", {"name": "dead"})
>>> _ = retire(lib, "prop.dead", by="me", reason="superseded")
>>> len(find(lib)), [h.asset_id for h in find(lib, status="retired")]
(0, ['prop.dead'])
```

### an.library.api.scan_index(library)

Every asset’s head version in `library`, read from the stores.

Affordances snapshotted by an older analyser are recomputed, not trusted. A
record or version that cannot be read (a damaged file) is skipped with a
[`LibraryIndexWarning`](#an.library.api.LibraryIndexWarning) naming it, so one bad entry never blinds every
search.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`IndexEntry`](#an.library.api.IndexEntry)]

### an.library.api.set_status(library, asset_id, status, , by, reason)

Set an asset’s curation status, recording who and why; return the record.

The record’s `status_history` is appended to, never rewritten, and no
version is touched: a project pinned to one keeps reading it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> _ = publish(lib, "prop.lamp", {"name": "lamp"})
>>> set_status(lib, "prop.lamp", "approved", by="me", reason="looks right")["status"]
'approved'
```

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

### an.library.api.unknown_advice(libraries, version, \*, owner=None, floor=<object object>)

What would answer each `unknown` contributor of a version — one sentence per kind.

The advice a refusal prints, so it names what works for THESE gaps
(an#307): a gap of the asset’s own chain takes a relabel; a gap of a
version it derives from is labelled there; another asset’s silence about
bytes this version still holds is answered by labelling THAT asset (a
relabel here cannot speak for another asset), or by dropping the file; and
anything stated (a licence nobody recognises, an unverified stamp, a
parent not on the path) relaxes only by a relicence.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> r = publish(lib, "prop.vase", {"name": "vase"})
>>> r.rights.license_class, "--relabel-by" in r.advice[0]
('unknown', True)
```

### an.library.api.version_labels(library, version)

The labels recorded on a stored version since it was published, oldest first.

A relabel of a version’s UNCHANGED content is recorded on that version, in
the library’s append-only `labels` store, instead of minting a new
version (an#307). A label counts only for the very version it was made on:
its `manifest` must be this version’s (a same-named library’s other
`x@v001` never inherits it). An unreadable label is skipped with a
[`LibraryIndexWarning`](#an.library.api.LibraryIndexWarning); skipping one can only leave the version
stricter.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.library.api.version_sources(libraries, version, \*, floor=<object object>, owner=None, per_file=True)

Every labelled source a version’s rights depend on — its own, its lineage, its bytes.

- its own ([`an.library.rights.sources_in()`](an.library.rights.md#an.library.rights.sources_in): asset-level, descriptor, parts);
- the version it follows (`previous`) and each `derived_from` version,
  recursively, labelled `<ref> > <label>`. A version records the
  manifest of each parent it resolved at publish (`LINEAGE_FIELD`);
  a parent that no longer resolves to that manifest is “not on the search
  path”, and the rights the child recorded stand in for it;
- the **floor** of every file of every version walked: what any library on
  this machine says about the same bytes ([`an.library.floor`](an.library.floor.md#module-an.library.floor)),
  labelled `<path>: same bytes as <asset>@<version>`. A blob is as
  restricted as the strictest statement made about it anywhere.

One exception to reading the floor, so a `relabel` can answer an earlier
version’s gap: the `unknown` statements of a version this walk read in
full AND could verify (each lineage link resolved to its pinned manifest,
or a `previous` link inside the same library root) are not read twice. A
`private` or `attribution` statement is always read, and so is anything
said by a version the walk could not verify (review-269 B1).

floor: a [`BlobFloor`](an.library.floor.md#an.library.floor.BlobFloor) to read (default: every
: library on the machine); `None` leaves the floor out — what the
  version itself says (its “asset label”), which is what the floor stores

owner: the library holding `version` (default: unknown — its own
: statements are then read from the floor too, which repeats a reason and
  relaxes nothing)

per_file: count each walked version’s per-file statements
: (`FILE_SOURCES_FIELD`, labelled `file:<path>`; an#345) — they
  count toward a version’s rights, never toward the label that speaks
  for the files nothing itemises (`False`: `_own_label_class()`)

A version carrying an explicit `relicense` (who, why) contributes its
asset-level source alone: that recorded statement replaces everything it
would otherwise inherit, and is the only way to relax rights. A version
carrying a `relabel` (who, why, beside an explicit source) answers the
GAPS of its own `previous` chain with that source — a file recorded
`unlabelled`, a version that recorded no source at all — and nothing else
(`RELABEL_FIELD`). A parent no library on the path holds falls back to
the rights recorded at publish, or `unknown` — never silence.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`AssetSource`](an.ir.assets.md#an.ir.assets.AssetSource) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]]

### an.library.api.vocabulary(libraries, \*, index=<function scan_index>)

Every facet with its values and counts, and the registered capabilities.

What an agent reads to turn words into a typed query (spectrum (b)): “a
Reiniger character who can walk in profile” → `style=reiniger`,
`affords=["limbs.legs", "swap.view:side"]`. The counts are over what
`find` offers by default — the same recomputed rights, and no asset of a
hidden status (`retired`), whose numbers are under `hidden`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> v = vocabulary(lib)
>>> sorted(v)
['capabilities', 'facets', 'hidden', 'kinds', 'rights', 'statuses']
>>> isinstance(v["capabilities"], (dict, list, tuple))
True
```
