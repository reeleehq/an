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
- for a relicensed version, its relicence;
- for a version carrying per-file statements (`file_sources`, an#345), or
  one whose lineage does: the strictest of its per-file statement (else its
  label computed without per-file statements), the same file’s per-part
  source, the same bytes at its other paths, and what its lineage says about
  these bytes — so a later statement never relaxes an earlier one
  (`an.library.api._PerFileRule`).

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

| [`library_origin`](#an.library.floor.library_origin)(library)                           | Which library a statement came from: its resolved root, or this in-memory library.          |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`machine_libraries`](#an.library.floor.machine_libraries)([libraries, environ, platform]) | `libraries` (first, as given) plus every other library root on this machine.                |
| [`record_statement`](#an.library.floor.record_statement)(store, digest, asset_key, ...)   | Record what `asset_key` says about `digest`: its latest holding version wins.               |
| [`register_library`](#an.library.floor.register_library)(library)                         | Record an on-disk library's root in the machine registry, before its first write.           |
| [`remember`](#an.library.floor.remember)(library, statements)                     | Remember an on-disk library's statements in the machine memory (none for an in-memory one). |

### Classes

| [`BlobFloor`](#an.library.floor.BlobFloor)([libraries, discover])   | The strictest statements about a blob, over every library on the machine, memoised.   |
|-------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|

### *class* an.library.floor.BlobFloor(libraries=None, , discover=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The strictest statements about a blob, over every library on the machine, memoised.

Build one per operation (a publish, a search, a check-out): it opens the
machine’s libraries once and reads each digest once.

#### each(digest)

Every `(origin, asset_key, statement)` about `digest`, unmerged.

`origin` is the library that made it ([`library_origin()`](#an.library.floor.library_origin)), so a
caller can tell a version it read itself from a same-named library’s.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]]

#### statements(digest, , exclude=())

`{asset_key: statement}` about `digest` from every library.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

exclude: `(origin, manifest)` of versions whose statements to leave
: out — the versions a rights walk reads in full itself
  ([`an.library.api.version_sources()`](an.library.api.html.md#an.library.api.version_sources)), each in the library it
  was read from ([`library_origin()`](#an.library.floor.library_origin)). A same-named library’s
  version with the same manifest is another version (its lineage
  resolves in ITS library), so it is never left out; and the
  exclusion runs before statements under one asset key are merged,
  so it can hide nothing else.

#### strictest(digests)

The strictest class any statement makes about any of `digests` (`free` if none).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.library.floor.library_origin(library)

Which library a statement came from: its resolved root, or this in-memory library.

Two libraries can share a name (the default `cutan` and one at a custom
root), and so an asset key, a version label and even a manifest: only the
root tells their statements apart.

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

A registry that does not exist yet means either this machine’s first
library write, or a registry that was deleted (or libraries that predate
it). The libraries on disk tell the two apart (an#307):

- no library discoverable now holds an asset: a **new** registry, created;
- libraries already hold assets: a **lost** one. It is rebuilt from what
  is discoverable now — those libraries are registered, and the statements
  their own floor indexes hold are remembered again — so their rights bind
  exactly as before. What cannot be recovered is a library kept at a
  custom root that is not discoverable now: it binds again once it is
  written to or reindexed.

Either way a `an.library.registry.RegistryWarning` says which
(R2b-N2: a registry deleted wholesale must never pass silently). Never
delete the registry folder wholesale; prune it.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.library.floor.remember(library, statements)

Remember an on-disk library’s statements in the machine memory (none for an in-memory one).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
