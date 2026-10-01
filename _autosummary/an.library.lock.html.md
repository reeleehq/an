# an.library.lock

The project lockfile: which library version each checked-out asset came from.

`assets.lock.json` at the project root (design §7.2), one entry per checked-out
asset, keyed `<store>/<key>` (`characters/alice`) — the address the scene’s
`AssetRef` already uses:

```json
{"schema_version": "0.1.0",
 "assets": {"characters/alice": {"library": "cutan:character.alice-reiniger@v002",
                                 "manifest_sha256": "…", "checked_out": "…"}}}
```

The pin records **provenance**: where each checked-out copy came from, so a
project can be rebuilt from the library. It is not a content key — the copy in
the project can be edited after it is pinned; `an.library.checkout.verify_checkout()`
says whether it still is its version, and only then may anything (ADR 0004’s
shot cache) treat the pin as standing for the content.

The lockfile is a `MutableMapping` like every other store (pillar 7);
`an.library.checkout.checkout()` takes one by injection (`lock=`) and
defaults to [`ProjectLock`](#an.library.lock.ProjectLock) over the project folder. Registering it in the
project mall (`mall["library_lock"]`) is an#240.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     lock = ProjectLock(d)
...     lock["characters/alice"] = {"library": "character.alice@v001"}
...     list(ProjectLock(d).items())
[('characters/alice', {'library': 'character.alice@v001'})]
```

### Module Attributes

| [`LOCKFILE_NAME`](#an.library.lock.LOCKFILE_NAME)           | The lockfile's name at the project root.                        |
|--------------------------------------------------------------------------|-----------------------------------------------------------------|
| [`LOCKFILE_SCHEMA_VERSION`](#an.library.lock.LOCKFILE_SCHEMA_VERSION) | The lockfile document's schema version (its own document kind). |

### Functions

| [`lock_key`](#an.library.lock.lock_key)(store, key)   | The lockfile key of one project store entry.   |
|-------------------------------------------------------------------------|------------------------------------------------|

### Classes

| [`ProjectLock`](#an.library.lock.ProjectLock)(project_dir)   | `<store>/<key> -> pin` over a project's `assets.lock.json`.   |
|-----------------------------------------------------------------------------|---------------------------------------------------------------|

### an.library.lock.LOCKFILE_NAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'assets.lock.json'*

The lockfile’s name at the project root.

### an.library.lock.LOCKFILE_SCHEMA_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '0.1.0'*

The lockfile document’s schema version (its own document kind).

### *class* an.library.lock.ProjectLock(project_dir)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`<store>/<key> -> pin` over a project’s `assets.lock.json`.

Every write rewrites the whole (small) file, sorted, so the lockfile diffs
cleanly under version control.

### an.library.lock.lock_key(store, key)

The lockfile key of one project store entry.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> lock_key("characters", "alice")
'characters/alice'
```
