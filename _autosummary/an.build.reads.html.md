# an.build.reads

What a shot read: a read-recording view of the mall, and the digests of what it saw.

ADR 0004 decision 3: *a shot’s inputs are recorded, not assumed.* The mall a
keyer compiles against is wrapped in a [`RecordingMall`](#an.build.reads.RecordingMall), which notes
every asset entry the compile asks for — `props["logo"]`, a `get`, an
`in` test — and every store it LISTS (iterating a store, or taking its
length, depends on all of it). Those reads become the shot’s dependency edges:
[`read_digests()`](#an.build.reads.read_digests) digests exactly them, and an edit to an asset no shot
read moves no key. Before an#316 every shot depended on every asset in its
project ([`an.build.keys.project_assets_digest()`](an.build.keys.html.md#an.build.keys.project_assets_digest), the first slice’s
fallback), so a one-prop edit re-rendered the whole film.

Only the asset stores ([`PROJECT_ASSET_STORES`](an.build.keys.html.md#an.build.keys.PROJECT_ASSET_STORES)) are
recorded. Everything else a render reads already has a part of its own: the
scene reaches the key through each shot’s compiled document, the dialogue
audio through `audio`, art staged by path through `textures`.

An entry’s digest covers what the mapping returns AND, for a filesystem store,
the files of the entry beside it (a prop’s `prop.json`, its `parts/` SVGs,
a relative font) — so a sidecar edited behind the mapping still moves it.

```pycon
>>> mall = RecordingMall({"props": {"logo": {"text": "A"}, "intro": {}}})
>>> mall["props"]["logo"]["text"]
'A'
>>> sorted(mall.reads)
[('props', 'logo')]
>>> sorted(read_digests({"props": {"logo": {"text": "A"}}}, mall.reads))
['props/logo']
```

### Module Attributes

| [`WHOLE_STORE`](#an.build.reads.WHOLE_STORE)   | The key a read of a WHOLE store is recorded under (iteration, `len`): the shot depends on every entry, present and future.   |
|----------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`entry_digest`](#an.build.reads.entry_digest)(store, key)   | One entry's digest: what the mapping returns, plus its files on disk.          |
|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`entry_files`](#an.build.reads.entry_files)(store, key)    | The files of entry `key` in a filesystem store (one exposing `_root`).         |
| [`read_digests`](#an.build.reads.read_digests)(mall, reads)  | `{"store/key": digest}` for every recorded read — the shot's dependency edges. |

### Classes

| [`RecordingMall`](#an.build.reads.RecordingMall)(mall, \*[, recorded])   | A view of `mall` that records which asset entries are read through it.                                               |
|----------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| [`RecordingStore`](#an.build.reads.RecordingStore)(store, name, reads)    | One store of a [`RecordingMall`](#an.build.reads.RecordingMall): reads are noted, writes pass through. |

### *class* an.build.reads.RecordingMall(mall, , recorded=('characters', 'environments', 'props', 'styles', 'voices', 'sounds'))

Bases: [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)

A view of `mall` that records which asset entries are read through it.

Stores named in `recorded` come back wrapped in a [`RecordingStore`](#an.build.reads.RecordingStore)
(one per store, so identity is stable across lookups); every other store
comes back as it is. `reads` is the set of `(store, key)` read so
far, `key` being [`WHOLE_STORE`](#an.build.reads.WHOLE_STORE) for a store that was listed.

### *class* an.build.reads.RecordingStore(store, name, reads)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

One store of a [`RecordingMall`](#an.build.reads.RecordingMall): reads are noted, writes pass through.

Attribute access (`_root`, a store’s own helpers) reaches the wrapped
store unchanged — the compiler reads art by path through `_root`, and
those bytes are keyed by the `textures` part, not here. `bool()` is
NOT a read: `mall.get(name) or {}` asks whether the store has anything,
and recording it would make every shot depend on the whole store. So a
read of an EMPTY store (which that idiom replaces with `{}`) goes
unrecorded — safe, because what the shot draws from an entry that appears
later reaches its compiled document.

### an.build.reads.WHOLE_STORE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '\*'*

The key a read of a WHOLE store is recorded under (iteration, `len`):
the shot depends on every entry, present and future.

### an.build.reads.entry_digest(store, key)

One entry’s digest: what the mapping returns, plus its files on disk.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> entry_digest({"a": 1}, "a") == entry_digest({"a": 1}, "a")
True
>>> entry_digest({"a": 1}, "a") == entry_digest({"a": 2}, "a")
False
>>> entry_digest({}, "a") == entry_digest({}, "a")  # absent is a value too
True
```

### an.build.reads.entry_files(store, key)

The files of entry `key` in a filesystem store (one exposing `_root`).

Both store layouts are covered: a sidecar store’s folder `<root>/<key>/`
(everything under it) and a file store’s `<root>/<key>.<ext>` (one
suffix: `logo.json` is entry `logo`’s; `logo.v2/` and
`logo.v2.json` are entry `logo.v2`’s). Operating-system clutter is
never an asset (`an.stores._common.is_os_junk()`).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### an.build.reads.read_digests(mall, reads)

`{"store/key": digest}` for every recorded read — the shot’s dependency edges.

A read of a store the mall does not have is recorded as `ABSENT`, so
the day the store appears the key moves.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> read_digests({}, [("props", "logo")])
{'props/logo': 'absent'}
```
