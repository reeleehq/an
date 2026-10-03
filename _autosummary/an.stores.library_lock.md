# an.stores.library_lock

The project lockfile: which library version each checked-out asset came from.

`assets.lock.json` at the project root (design §7.2), one entry per checked-out
asset, keyed `<store>/<key>` (`characters/alice`) — the address the scene’s
`AssetRef` already uses:

```json
{"schema_version": "0.1.0",
 "assets": {"characters/alice": {"library": "cutan:character.alice-reiniger@v002",
                                 "manifest_sha256": "…", "checked_out": "…"}}}
```

**The lockfile is the single source of truth for a pin** (an#240). It is written
by the check-out that put the files there, beside the manifest it verified, so
it says what the project actually holds. A scene’s `AssetRef.library` is the
declared intent, an optional restatement of it for the reader; a later
“reference” resolution resolves through the lockfile entry `<store>/<ref>`
too, and treats `library:` as the intent it must match — never as a second
pin. `an validate` (and `an render`, fatally under `--strict-assets`)
reports every scene `library:` that disagrees with the lockfile, or names an
entry the lockfile does not pin (`an.library.checkout.check_pins()`). The
lockfile records no library root: it is committed, and a path would leak.

The pin records **provenance**: where each checked-out copy came from, so a
project can be rebuilt from the library. It is not a content key — the copy in
the project can be edited after it is pinned; `an.library.checkout.verify_checkout()`
says whether it still is its version (`an validate` reports the drift as
`info`: an edited check-out is a fork, not a mistake), and only then may
anything treat the pin as standing for the content.

A **kit** check-out ([`an.library.kits.checkout_kit()`](an.library.kits.md#an.library.kits.checkout_kit)) pins each member the
way any check-out does, and additionally records the kit in a top-level
`"kits"` section, keyed by the kit’s asset id:

```default
{"kits": {"kit.reiniger-base": {"library": "cutan:kit.reiniger-base@v002",
                                "manifest_sha256": "…", "checked_out": "…",
                                "members": ["styles/reiniger", "voices/narrator"]}}}
```

`members` are lockfile keys of `assets`. The section sits OUTSIDE `assets`
on purpose: everything that walks the pins (`verify_checkout`, `an validate`,
`check_pins`) iterates the mapping, which is `assets` only, so a kit entry
cannot be mistaken for an asset or collide with a `<store>/<key>` key. It is
additive (an older `an` reads the file and ignores the section, though its
next write drops it) and read through
[`ProjectLock.kits`](#an.stores.library_lock.ProjectLock.kits).

The lockfile is a `MutableMapping` like every other store (pillar 7),
registered in the project mall as `mall["library_lock"]`
([`an.stores.build_project_mall()`](an.stores.md#an.stores.build_project_mall)); `an.library.checkout.checkout()`
writes through the mall’s store unless one is injected (`lock=`). It lives
here, with the other project stores, so building a project mall never imports
the asset library; [`an.library.lock`](an.library.lock.md#module-an.library.lock) re-exports it.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     lock = ProjectLock(d)
...     lock["characters/alice"] = {"library": "character.alice@v001"}
...     list(ProjectLock(d).items())
[('characters/alice', {'library': 'character.alice@v001'})]
```

### Module Attributes

| [`LOCKFILE_NAME`](#an.stores.library_lock.LOCKFILE_NAME)           | The lockfile's name at the project root.                        |
|--------------------------------------------------------------------------|-----------------------------------------------------------------|
| [`LOCKFILE_SCHEMA_VERSION`](#an.stores.library_lock.LOCKFILE_SCHEMA_VERSION) | The lockfile document's schema version (its own document kind). |

### Functions

| [`lock_key`](#an.stores.library_lock.lock_key)(store, key)   | The lockfile key of one project store entry.   |
|-------------------------------------------------------------------------|------------------------------------------------|

### Classes

| [`ProjectLock`](#an.stores.library_lock.ProjectLock)(project_dir)   | `<store>/<key> -> pin` over a project's `assets.lock.json`.   |
|-----------------------------------------------------------------------------|---------------------------------------------------------------|

### an.stores.library_lock.LOCKFILE_NAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'assets.lock.json'*

The lockfile’s name at the project root.

### an.stores.library_lock.LOCKFILE_SCHEMA_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '0.1.0'*

The lockfile document’s schema version (its own document kind).

### *class* an.stores.library_lock.ProjectLock(project_dir)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`<store>/<key> -> pin` over a project’s `assets.lock.json`.

Every write rewrites the whole (small) file, sorted, so the lockfile diffs
cleanly under version control. The mapping is the `assets` section;
[`kits`](#an.stores.library_lock.ProjectLock.kits) is the `kits` section, and a write to either keeps the other.

#### *property* kits *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]]*

`kit asset id -> record` of the kits checked out into the project.

### an.stores.library_lock.lock_key(store, key)

The lockfile key of one project store entry.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> lock_key("characters", "alice")
'characters/alice'
```
