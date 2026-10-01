# an.library.floor

The rights floor of a blob: the strictest statement any library on this machine makes about its bytes.

ADR 0005 decision 10’s “most restrictive”, read as the maintainer decided it
(an#236): rights attach to the bytes. A file is as restricted as the strictest
statement ANY library known on this machine makes about its SHA-256 — whichever
library one reads through — and only an explicit, recorded relicence relaxes it.

**What a statement is.** Each version that holds a blob says one thing about it:

- the version’s own per-part `source` for that exact file, if the source pins
  the same digest (`AssetSource.sha256`) — a per-part claim about OTHER bytes
  (a stale factory stamp on a re-carved part) itemises nothing;
- otherwise the asset’s own label: its asset-level and descriptor sources and
  its lineage — what the asset says about every file it does not itemise;
- for a relicensed version, its relicence.

**Where the statements live.** Each library keeps a derived store,
`blob_rights`: `sha256 -> {"<library>:<asset_id>": statement}`, one entry
per asset (its latest version holding the blob), maintained by `publish` and
rebuilt by [`an.library.api.reindex()`](an.library.api.html.md#an.library.api.reindex). Reading a floor is one key lookup per
library, so the cross-library check costs nothing like a scan.

**Which libraries.** Those on the search path, plus every other library on
this machine the floor can find:

- each package root under the current platform data folder
  (`~/.local/share/an`, `~/.local/share/cutan`, …);
- each currently set `<PKG>_HOME` root;
- every root in the machine’s **registry of library roots**
  ([`an.library.registry`](an.library.registry.html.md#module-an.library.registry), an#249) — written on the first write to any
  library, at a path that depends on nothing in the environment. A library at a
  custom `--root`, or under a `<PKG>_HOME` / `XDG_DATA_HOME` that has since
  changed, is therefore still read. A registered root that no longer exists (or
  holds no library) is skipped;
- the machine’s **memory of statements** (same place): every statement any
  on-disk library made at publish, so a library moved, renamed or deleted
  since relaxes nothing — the floor keeps its last-known statements.

A library written by an older `an` at a custom root, before the registry
existed, is registered by its next write or by [`an.library.api.reindex()`](an.library.api.html.md#an.library.api.reindex).

### Functions

| [`machine_libraries`](#an.library.floor.machine_libraries)([libraries, environ, platform])   | `libraries` (first, as given) plus every other library root on this machine.                |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`record_statement`](#an.library.floor.record_statement)(store, digest, asset_key, ...)     | Record what `asset_key` says about `digest`: its latest holding version wins.               |
| [`register_library`](#an.library.floor.register_library)(library)                           | Record an on-disk library's root in the machine registry, before its first write.           |
| [`remember`](#an.library.floor.remember)(library, statements)                       | Remember an on-disk library's statements in the machine memory (none for an in-memory one). |

### Classes

| [`BlobFloor`](#an.library.floor.BlobFloor)([libraries, discover])   | The strictest statements about a blob, over every library on the machine, memoised.   |
|-------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|

### *class* an.library.floor.BlobFloor(libraries=None, , discover=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The strictest statements about a blob, over every library on the machine, memoised.

Build one per operation (a publish, a search, a check-out): it opens the
machine’s libraries once and reads each digest once.

#### statements(digest)

`{asset_key: statement}` about `digest` from every library.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

#### strictest(digests)

The strictest class any statement makes about any of `digests` (`free` if none).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.library.floor.machine_libraries(libraries=None, , environ=None, platform=None)

`libraries` (first, as given) plus every other library root on this machine.

Roots already on the path are not opened twice; a folder whose name is not a
valid library name is skipped.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Library`](an.library.federation.html.md#an.library.federation.Library)]

### an.library.floor.record_statement(store, digest, asset_key, statement)

Record what `asset_key` says about `digest`: its latest holding version wins.

A later version of an asset may only be as strict or stricter than an
earlier one (it inherits it), unless it is relicensed — so the latest
version’s statement is the asset’s statement.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.library.floor.register_library(library)

Record an on-disk library’s root in the machine registry, before its first write.

An in-memory library (no root) has nothing to register. Raises
[`an.library.registry.RegistryError`](an.library.registry.html.md#an.library.registry.RegistryError) when the registry cannot be
read or written: the write is refused rather than made invisible to the floor.

A registry that does not exist yet while libraries already sit on disk
means either the first use since the registry exists, or a registry that
was lost: every library discoverable now is registered with this one, and a
`an.library.registry.RegistryWarning` says that libraries kept at
custom roots are known again only once written to or reindexed.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.library.floor.remember(library, statements)

Remember an on-disk library’s statements in the machine memory (none for an in-memory one).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
