# an.library.registry

The machine’s memory of its libraries: every root ever written, and every statement ever made (an#249).

The rights floor ([`an.library.floor`](an.library.floor.md#module-an.library.floor)) must read every statement any
library on this machine makes about a blob, not only those it can discover
from today’s environment. Discovery finds the package roots under the CURRENT
data folder (which follows `XDG_DATA_HOME`) and the CURRENTLY set
`<PKG>_HOME` roots. A library written at an explicit `root=` / `--root`,
or under an environment that has since changed, is invisible to discovery, and
its private bytes would then publish as `free` anywhere else.

So this module keeps two records, side by side, at a location that depends on
**nothing in the environment**: the account’s home folder as the operating
system records it (the password database on POSIX, never `$HOME`), under the
core package’s default data folder — `~/.local/share/an/registry/` on Linux
and macOS, whatever `XDG_DATA_HOME`, `AN_HOME` or `<PKG>_HOME` say. (On
Windows the account’s home is `Path.home()`, which follows `USERPROFILE`:
there the location is as stable as that variable.)

- **The registry of roots** (`library_roots.jsonl`): the first write to any
  on-disk library records its root, and the floor reads each registered root’s
  own index. JSON Lines, **append-only**: an append of one short line is
  atomic, so racing publishers cannot lose each other’s registration, and a
  line torn by a crash is skipped (the next append starts on a fresh line).
  A root that no longer exists is skipped — which is why the second record
  exists.
- **The memory of statements** (`statements/<aa>/<sha256>/…json`): every
  statement a version makes about a blob, written at publish beside the
  library’s own index. The floor reads it in addition to the libraries, so a
  library that is moved, renamed, unmounted or deleted can never relax a
  statement it once made: **a missing root relaxes nothing**. One small file
  per (blob, library root, asset), replaced only by a later version of the same
  asset at the same root — so a relicence there still speaks, as in the
  library’s own index. A file that cannot be parsed counts as `unknown`.

Both are read **fail-closed**: a registry or memory that exists but cannot be
read raises [`RegistryError`](#an.library.registry.RegistryError) — a floor that silently read less would let
private bytes out. Libraries with injected stores (no root on disk: an S3 or
in-memory mall) are in neither record; their statements reach the floor only
while they are on the search path.

Neither record is a search path: a registered library’s assets are never
found, resolved or checked out through them — reads still go through the
explicit search path ([`an.library.federation.search_path()`](an.library.federation.md#an.library.federation.search_path)).

Tests and doctests are redirected by the repository’s root `conftest.py`,
which points `_account_home()` into a temporary folder. A test that runs
`an` in a SUBPROCESS cannot be redirected that way and must not publish.

```pycon
>>> import tempfile, pathlib
>>> with tempfile.TemporaryDirectory() as d:
...     reg = pathlib.Path(d) / "roots.jsonl"
...     first = register_root("cutan", pathlib.Path(d) / "study", registry=reg)
...     again = register_root("cutan", pathlib.Path(d) / "study", registry=reg)
...     (first, again), [(p, r.name) for p, r in registered_roots(registry=reg)]
((True, False), [('cutan', 'study')])
```

### Module Attributes

| [`REGISTRY_DIRNAME`](#an.library.registry.REGISTRY_DIRNAME)   | The sub-folder of the core package's default data root holding the registry (a root holds one sub-folder per kind of data, never files at the top).   |
|---------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`REGISTRY_FILENAME`](#an.library.registry.REGISTRY_FILENAME)  | JSON Lines, one `{"package", "root", "registered"}` per line.                                                                                         |
| [`STATEMENTS_DIRNAME`](#an.library.registry.STATEMENTS_DIRNAME) | The folder of remembered statements, beside the registry file.                                                                                        |

### Functions

| [`machine_registry_dir`](#an.library.registry.machine_registry_dir)()                       | The folder holding the registry and the statement memory (independent of the environment).   |
|-----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| [`machine_registry_path`](#an.library.registry.machine_registry_path)()                      | Where this machine's registry of library roots lives.                                        |
| [`register_root`](#an.library.registry.register_root)(package, root, \*[, registry]) | Record `root` (`package`'s library root) in the registry; `True` if it was new.              |
| [`registered_roots`](#an.library.registry.registered_roots)(\*[, registry])             | `(package, root)` for every root ever registered, oldest first, each once.                   |
| [`remember_statements`](#an.library.registry.remember_statements)(root, statements)        | Remember `(digest, asset_key, statement)` made by the library at `root`.                     |
| [`remembered_statements`](#an.library.registry.remembered_statements)(digest)                | `(asset_key, statement)` for every statement this machine ever recorded about `digest`.      |

### Exceptions

| [`RegistryError`](#an.library.registry.RegistryError)   | The machine's registry or statement memory cannot be read or written; nothing proceeds.   |
|------------------------------------------------------------------|-------------------------------------------------------------------------------------------|

### an.library.registry.REGISTRY_DIRNAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'registry'*

The sub-folder of the core package’s default data root holding the registry
(a root holds one sub-folder per kind of data, never files at the top).

### an.library.registry.REGISTRY_FILENAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'library_roots.jsonl'*

JSON Lines, one `{"package", "root", "registered"}` per line.

* **Type:**
  The registry file

### *exception* an.library.registry.RegistryError

Bases: [`OSError`](https://docs.python.org/3/builtins/exceptions.html#OSError)

The machine’s registry or statement memory cannot be read or written; nothing proceeds.

### an.library.registry.STATEMENTS_DIRNAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'statements'*

The folder of remembered statements, beside the registry file.

### an.library.registry.machine_registry_dir()

The folder holding the registry and the statement memory (independent of the environment).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> machine_registry_dir().name
'registry'
```

### an.library.registry.machine_registry_path()

Where this machine’s registry of library roots lives.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> machine_registry_path().name
'library_roots.jsonl'
```

### an.library.registry.register_root(package, root, , registry=None)

Record `root` (`package`’s library root) in the registry; `True` if it was new.

Idempotent. Raises [`RegistryError`](#an.library.registry.RegistryError) when the registry cannot be read
or written: a library the floor cannot find later must not be written to.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.library.registry.registered_roots(, registry=None)

`(package, root)` for every root ever registered, oldest first, each once.

A line that does not parse (a torn append) is skipped; existence is the
caller’s to check. A registry that exists but cannot be read raises
[`RegistryError`](#an.library.registry.RegistryError).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]]

### an.library.registry.remember_statements(root, statements)

Remember `(digest, asset_key, statement)` made by the library at `root`.

One file per (digest, root, asset), replaced only by a statement of a later
(or the same) version of that asset — the same rule as a library’s own
index. Raises [`RegistryError`](#an.library.registry.RegistryError) when it cannot be written.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.library.registry.remembered_statements(digest)

`(asset_key, statement)` for every statement this machine ever recorded about `digest`.

A remembered file that cannot be parsed counts as an `unknown`
statement (it said something; what is no longer known). A memory that
exists but cannot be listed raises [`RegistryError`](#an.library.registry.RegistryError).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]]
