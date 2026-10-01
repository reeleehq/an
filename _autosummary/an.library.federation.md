# an.library.federation

Libraries federated by a search path: one read view, writes to the owner (plan §1 decision 7).

Each package has its own library root (`an` → `~/.local/share/an`, a genre
such as `cutan` → `~/.local/share/cutan`). A process reads them as one
ordered **search path** — its own library first, then the core `an` library,
then any others the user lists (ADR 0005 decision 1, Harmony’s scope chain
reduced to one mechanism). An id resolves in the first library that has it;
a namespaced id (`cutan:character.alice@v003`) resolves only in the named one.
Writes always go to one owning [`Library`](#an.library.federation.Library), never to the path.

The search path is the seam where a team share, a shipped seed library or a
remote bucket plugs in later: each is just another [`Library`](#an.library.federation.Library) whose mall
was built over different stores.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     path = search_path("cutan", roots={"cutan": f"{d}/cutan", "an": f"{d}/an"})
...     [lib.name for lib in path]
['cutan', 'an']
```

### Module Attributes

| [`Libraries`](#an.library.federation.Libraries)   | one library, or a search path of them.   |
|--------------------------------------------------------------|------------------------------------------|

### Functions

| [`as_libraries`](#an.library.federation.as_libraries)(libraries)              | Normalise one library or a search path to a list.                                                                                             |
|---------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| [`open_library`](#an.library.federation.open_library)([package, root])        | The library of `package`, at `root` (resolved as in [`an.library.root`](an.library.root.md#module-an.library.root)). |
| [`resolve`](#an.library.federation.resolve)(libraries, ref)              | `(library, pinned_ref, version_doc)` for a reference, along the search path.                                                                  |
| [`search_path`](#an.library.federation.search_path)([package, extra, roots]) | The ordered libraries `package` reads: its own, then the core `an`, then `extra`.                                                             |

### Classes

| [`Library`](#an.library.federation.Library)(name, mall[, root])   | One library: its name (the namespace of its ids), its mall, and its root if on disk.   |
|--------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|

### Exceptions

| [`AssetNotFoundError`](#an.library.federation.AssetNotFoundError)   | No library on the search path holds the asset or version asked for.   |
|-----------------------------------------------------------------------|-----------------------------------------------------------------------|

### *exception* an.library.federation.AssetNotFoundError

Bases: [`LookupError`](https://docs.python.org/3/builtins/exceptions.html#LookupError)

No library on the search path holds the asset or version asked for.

### an.library.federation.Libraries

one library, or a search path of them.

* **Type:**
  What the read functions accept

alias of [`Library`](#an.library.federation.Library) | [`Sequence`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)[[`Library`](#an.library.federation.Library)]

### *class* an.library.federation.Library(name, mall, root=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One library: its name (the namespace of its ids), its mall, and its root if on disk.

#### *property* blob_rights *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)*

`sha256 -> {asset: statement}`, derived ([`an.library.floor`](an.library.floor.md#module-an.library.floor)).

#### *property* blobs *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)*

`sha256 -> bytes` (content-addressed).

#### *property* records *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)*

`asset_id -> record` (mutable curation).

#### *property* versions *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)*

`<asset_id>@<vNNN> -> version` (write-once).

### an.library.federation.as_libraries(libraries)

Normalise one library or a search path to a list.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Library`](#an.library.federation.Library)]

### an.library.federation.open_library(package='an', root=None, \*\*overrides)

The library of `package`, at `root` (resolved as in [`an.library.root`](an.library.root.md#module-an.library.root)).

* **Return type:**
  [`Library`](#an.library.federation.Library)

overrides: stores to inject (`records`, `versions`, `blobs`), as in
: [`an.library.stores.build_library_mall()`](an.library.stores.md#an.library.stores.build_library_mall)

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> (lib.name, lib.root)
('an', None)
```

### an.library.federation.resolve(libraries, ref)

`(library, pinned_ref, version_doc)` for a reference, along the search path.

A namespaced reference reads only its library; a bare one reads the first
library holding the asset. `latest` resolves to that library’s head and
`sha256:<prefix>` to the one version whose manifest hash starts with it.
The returned reference is pinned (`vNNN`) and namespaced with the library
it resolved in.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Library`](#an.library.federation.Library), [`LibraryRef`](an.library.ids.md#an.library.ids.LibraryRef), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.library.federation.search_path(package='an', , extra=(), roots=None)

The ordered libraries `package` reads: its own, then the core `an`, then `extra`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Library`](#an.library.federation.Library)]

extra: further libraries, by package name (resolved like any root) or as
: [`Library`](#an.library.federation.Library) objects (a team share, a seed library)

roots: an explicit root per package name (tests, a non-default layout);
: unnamed packages resolve as usual (`<PKG>_HOME`, then the data folder)

A name appears once, at its first position.
