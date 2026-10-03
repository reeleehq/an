# an.library.lock

The project lockfile, as the asset library sees it (re-exported from [`an.stores.library_lock`](an.stores.library_lock.md#module-an.stores.library_lock)).

The lockfile is a project store — `mall["library_lock"]`, registered by
[`an.stores.build_project_mall()`](an.stores.md#an.stores.build_project_mall) (an#240) — so its class lives with the other
project stores and building a project never imports the library. This module
keeps the import path the library and its callers already use.

```pycon
>>> LOCKFILE_NAME, lock_key("characters", "alice")
('assets.lock.json', 'characters/alice')
```

### Functions

| [`lock_key`](#an.library.lock.lock_key)(store, key)   | The lockfile key of one project store entry.   |
|-------------------------------------------------------------------------|------------------------------------------------|

### Classes

| [`ProjectLock`](#an.library.lock.ProjectLock)(project_dir)   | `<store>/<key> -> pin` over a project's `assets.lock.json`.   |
|-----------------------------------------------------------------------------|---------------------------------------------------------------|

### *class* an.library.lock.ProjectLock(project_dir)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`<store>/<key> -> pin` over a project’s `assets.lock.json`.

Every write rewrites the whole (small) file, sorted, so the lockfile diffs
cleanly under version control. The mapping is the `assets` section;
[`kits`](#an.library.lock.ProjectLock.kits) is the `kits` section, and a write to either keeps the other.

#### *property* kits *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]]*

`kit asset id -> record` of the kits checked out into the project.

### an.library.lock.lock_key(store, key)

The lockfile key of one project store entry.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> lock_key("characters", "alice")
'characters/alice'
```
