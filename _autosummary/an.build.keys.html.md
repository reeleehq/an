# an.build.keys

Cache keys for build stages: canonical digests, the project fallback, keyers.

ADR 0004 decision 2: *every key covers everything that changes the output*, and
`shot.id` is never one of them (pillar 11). A shot key is composed from NAMED
parts, each a sha256 hex digest, so a re-render can say which input moved:

The core names no renderer: a backend joins by [`register_shot_keyer()`](#an.build.keys.register_shot_keyer). A
renderer with no keyer is never cached, which is the safe default — an opaque
shot is re-rendered, never reused on a guess.

```pycon
>>> canonical_digest({"b": 1, "a": [1, 2]}) == canonical_digest({"a": [1, 2], "b": 1})
True
>>> len(compose_shot_key({"renderer": canonical_digest("cutout")}))
64
```

### Module Attributes

| [`SHOT_KEY_IMPL_VERSION`](#an.build.keys.SHOT_KEY_IMPL_VERSION)       | The key's own version — the `impl_version` salt of `nw.Transform` and of `burns.RESOLVER_IMPL_VERSION` ("a lock, not a receipt").                                   |
|------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`PROJECT_ASSET_STORES`](#an.build.keys.PROJECT_ASSET_STORES)        | the art the compiler reads (characters, environments, props, styles) and the two the audio path reads (voices, sounds).                                             |
| [`PROJECT_ROOT_FILES`](#an.build.keys.PROJECT_ROOT_FILES)          | Files at the project ROOT that every shot depends on, whether or not a mall store exposes them.                                                                     |
| [`IGNORED_ASSET_NAME_PREFIXES`](#an.build.keys.IGNORED_ASSET_NAME_PREFIXES) | an OS's folder metadata must not re-render a film.                                                                                                                  |
| [`ABSENT`](#an.build.keys.ABSENT)                      | a missing texture, an audio ref the store does not hold.                                                                                                            |
| [`ShotKeyer`](#an.build.keys.ShotKeyer)                   | `keyer(shot, ctx) -> ShotKeyInputs`.                                                                                                                                |
| [`EnvironmentProbe`](#an.build.keys.EnvironmentProbe)            | the renderer's environment record.                                                                                                                                  |
| [`ShotKeyPart`](#an.build.keys.ShotKeyPart)                 | one more named digest for a renderer's key — the additive seam for an input read OUTSIDE the compiled document (a genre's side file, a vocabulary entry's version). |

### Functions

| [`bytes_digest`](#an.build.keys.bytes_digest)(data)                                 | The hex sha256 of `data`.                                                                                                                                                  |
|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`callable_identity`](#an.build.keys.callable_identity)(obj)                             | `module.qualname` of a function or class (of an instance: of its type).                                                                                                    |
| [`canonical_digest`](#an.build.keys.canonical_digest)(obj)                              | The hex sha256 of [`canonical_json()`](#an.build.keys.canonical_json) of `obj`.                                                                              |
| [`canonical_json`](#an.build.keys.canonical_json)(obj)                                | `obj` as sorted, whitespace-free JSON — the one spelling every digest hashes.                                                                                              |
| [`compose_shot_key`](#an.build.keys.compose_shot_key)(parts)                            | The shot key: one digest over the named parts and the key's own version.                                                                                                   |
| [`every_asset_digest`](#an.build.keys.every_asset_digest)(mall, \*[, project_root])       | Every asset in the project (decision 3's fallback), without the root files — those are [`project_dependencies()`](#an.build.keys.project_dependencies)'.           |
| [`file_digest`](#an.build.keys.file_digest)(path)                                  | The hex sha256 of a file's bytes, read NOW.                                                                                                                                |
| [`project_assets_digest`](#an.build.keys.project_assets_digest)(mall, \*[, stores, ...])     | One digest over every asset store of the project (ADR 0004 decision 3).                                                                                                    |
| [`project_dependencies`](#an.build.keys.project_dependencies)(mall, \*[, project_root])     | What every shot depends on project-wide: the project-root files ([`PROJECT_ROOT_FILES`](#an.build.keys.PROJECT_ROOT_FILES), the library lockfile), read by path. |
| [`project_root_files_digest`](#an.build.keys.project_root_files_digest)(project_root, \*[, ...]) | `{name: sha256 or ABSENT}` for the project-root files every shot depends on.                                                                                               |
| [`register_shot_key_part`](#an.build.keys.register_shot_key_part)(renderer_name, ...)         | Add one named input to every key of `renderer_name`'s shots — additively.                                                                                                  |
| [`register_shot_keyer`](#an.build.keys.register_shot_keyer)(renderer_name, keyer, \*)      | Declare how shots of `renderer_name` are keyed, and how its machine is probed.                                                                                             |
| [`registered_shot_keyers`](#an.build.keys.registered_shot_keyers)()                           | The renderer names that have a keyer.                                                                                                                                      |
| [`shot_keyer_for`](#an.build.keys.shot_keyer_for)(renderer)                           | The keyer that describes `renderer` (an instance, or a name), or `None`.                                                                                                   |
| [`store_digest`](#an.build.keys.store_digest)(store)                                | A digest of one store's whole content.                                                                                                                                     |

### Classes

| [`ShotKeyInputs`](#an.build.keys.ShotKeyInputs)(parts[, compile_s, details])   | What a renderer's keyer returns for one shot.   |
|-----------------------------------------------------------------------------------------------|-------------------------------------------------|

### Exceptions

| [`ShotKeyerRegistrationError`](#an.build.keys.ShotKeyerRegistrationError)   | A shot keyer or key part was registered twice, or collides with another.   |
|-------------------------------------------------------------------------------|----------------------------------------------------------------------------|

### an.build.keys.ABSENT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'absent'*

a missing texture, an
audio ref the store does not hold. Still deterministic, and different from
any present value, so a part that later appears re-renders.

* **Type:**
  A part’s value when the thing it digests is absent

### an.build.keys.EnvironmentProbe

the renderer’s environment record. Called once per
process per renderer (see `ShotCache`), because a browser probe costs a
launch.

* **Type:**
  `probe() -> Mapping`

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[], [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.build.keys.IGNORED_ASSET_NAME_PREFIXES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('.',)*

an OS’s folder
metadata must not re-render a film.

* **Type:**
  File names under an asset root that are never assets

### an.build.keys.PROJECT_ASSET_STORES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('characters', 'environments', 'props', 'styles', 'voices', 'sounds')*

the art the compiler reads (characters,
environments, props, styles) and the two the audio path reads (voices,
sounds). What a recording view records ([`an.build.reads`](an.build.reads.html.md#module-an.build.reads)), and what
“every asset in the project” means for decision 3’s fallback. The scene
document is deliberately NOT here — each shot’s own slice reaches its key
through its compiled document, which is what lets an edit to one shot
re-render only that shot.

* **Type:**
  The mall’s ASSET stores

### an.build.keys.PROJECT_ROOT_FILES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('assets.lock.json',)*

Files at the project ROOT that every shot depends on, whether or not a mall
store exposes them. `assets.lock.json` is the asset library’s lockfile of
pinned library versions (ADR 0005, P5): a re-pin changes what is checked out,
so it must move every key — and it must do so before (and independently of)
its registration in the mall (an#240). Read by path, through
[`project_root_files_digest()`](#an.build.keys.project_root_files_digest); an absent file is recorded as absent.

### an.build.keys.SHOT_KEY_IMPL_VERSION *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

The key’s own version — the `impl_version` salt of `nw.Transform` and of
`burns.RESOLVER_IMPL_VERSION` (“a lock, not a receipt”). Bump it when the
COMPOSITION of a key changes (a part added, renamed or re-spelled). It is
NOT how a renderer’s code changes reach the key — a hand-bumped constant is
one someone forgets — that is each keyer’s `code` part, a digest of the
render path’s source. Bumping it orphans every entry; nothing is deleted
(decision 6).

### *class* an.build.keys.ShotKeyInputs(parts, compile_s=None, details=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a renderer’s keyer returns for one shot.

`parts` are named sha256 hex digests (the key’s content half); the engine
adds `renderer`, `project` and `environment`. `compile_s` is the
wall time of the compile the keyer ran to get its digest, or `None` for a
renderer that has no compile stage.

#### details *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

Diagnostics a keyer wants on the record beside the digests — never part
of the key (the digests are).

### an.build.keys.ShotKeyPart

one more named digest for a renderer’s key —
the additive seam for an input read OUTSIDE the compiled document (a genre’s
side file, a vocabulary entry’s version). See [`register_shot_key_part()`](#an.build.keys.register_shot_key_part).

* **Type:**
  `part(shot, ctx) -> str`

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.build.keys.ShotKeyer

`keyer(shot, ctx) -> ShotKeyInputs`. Raises what the render itself would
raise for the same inputs (a compile error, an invalid knob), so a bad shot
fails before any browser launches.

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)], [`ShotKeyInputs`](#an.build.keys.ShotKeyInputs)]

### *exception* an.build.keys.ShotKeyerRegistrationError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A shot keyer or key part was registered twice, or collides with another.

### an.build.keys.bytes_digest(data)

The hex sha256 of `data`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> bytes_digest(b"")[:8]
'e3b0c442'
```

### an.build.keys.callable_identity(obj)

`module.qualname` of a function or class (of an instance: of its type).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> callable_identity(callable_identity)
'an.build.keys.callable_identity'
```

### an.build.keys.canonical_digest(obj)

The hex sha256 of [`canonical_json()`](#an.build.keys.canonical_json) of `obj`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.build.keys.canonical_json(obj)

`obj` as sorted, whitespace-free JSON — the one spelling every digest hashes.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> canonical_json({"b": (1, 2), "a": None})
'{"a":null,"b":[1,2]}'
```

### an.build.keys.compose_shot_key(parts)

The shot key: one digest over the named parts and the key’s own version.

The parts are a MAPPING so the record can keep them by name, and a
re-render can be explained (”`textures` moved”) rather than merely
observed.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.build.keys.every_asset_digest(mall, , project_root=None)

Every asset in the project (decision 3’s fallback), without the root
files — those are [`project_dependencies()`](#an.build.keys.project_dependencies)’. The `assets` part of a
shot whose keyer cannot vouch for its reads.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> every_asset_digest({"props": {"a": 1}}) != every_asset_digest({"props": {"a": 2}})
True
```

### an.build.keys.file_digest(path)

The hex sha256 of a file’s bytes, read NOW.

Deliberately unmemoised. A (path, mtime, size) memo — `an.stage.raster`’s, which
is fine for a texture alias inside one compile — let a same-size edit whose
mtime was restored (`cp -p`, `rsync -t`, `tar x`, a sync client) be
served stale from cache in a long-running process (an#243 review, S2). A
cache KEY is only as good as its weakest input, so every byte is read on
every render; on the golden corpus the whole project digest is under 10 ms.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.build.keys.project_assets_digest(mall, , stores=('characters', 'environments', 'props', 'styles', 'voices', 'sounds'), project_root=None, root_files=('assets.lock.json',))

One digest over every asset store of the project (ADR 0004 decision 3).

The first slice’s dependency edge for every shot: safe — no asset can change
without every shot’s key moving — at the price of the per-character saving,
which read recording buys back. A store the mall does not have is recorded
as absent rather than skipped, so adding one later moves the digest.

With `project_root`, the files in `root_files` (the library lockfile)
are hashed by PATH as well — so a re-pin moves every key whether or not
the mall has a store for the file yet.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> a = project_assets_digest({"characters": {"c": {"v": 1}}}, stores=["characters"])
>>> b = project_assets_digest({"characters": {"c": {"v": 2}}}, stores=["characters"])
>>> a == b
False
```

### an.build.keys.project_dependencies(mall, , project_root=None)

What every shot depends on project-wide: the project-root files
([`PROJECT_ROOT_FILES`](#an.build.keys.PROJECT_ROOT_FILES), the library lockfile), read by path. A re-pin
changes what is checked out, so it moves every key, conservatively.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> project_dependencies({}) == project_dependencies({"props": {"a": 1}})
True
```

### an.build.keys.project_root_files_digest(project_root, , files=('assets.lock.json',))

`{name: sha256 or ABSENT}` for the project-root files every shot depends on.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     project_root_files_digest(d, files=["assets.lock.json"])
{'assets.lock.json': 'absent'}
```

### an.build.keys.register_shot_key_part(renderer_name, part_name, part)

Add one named input to every key of `renderer_name`’s shots — additively.

For an input the render reads OUTSIDE its compiled document (whatever
changes the document is already covered by the `compiled` part, with
early cutoff for free): a genre package’s side file, a vocabulary entry’s
version (P7). Refuses a duplicate `part_name`; a name that collides with
one of the keyer’s own parts is refused when the key is computed.

A renderer registered LAZILY (the stage, an#247) brings its keyer when the
renderer registry first loads, so this loads it first – a genre adding a
key part at install (`cutan`, P8) needs no prior lookup.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.build.keys.register_shot_keyer(renderer_name, keyer, , environment=None, renderer_type=None, records_reads=False, replace=False)

Declare how shots of `renderer_name` are keyed, and how its machine is probed.

The registration seam for every backend (cut-out here; Manim’s opaque
shots, keyed on source hash + Manim version + quality, are the next).
`renderer_type` binds the keyer to one renderer class: a renderer whose
type is not exactly it is never cached. `records_reads=True` claims
that every asset the shot depends on is read through `ctx.mall` (or is
already digested by one of the keyer’s parts): the engine then keys the
shot on the entries it read rather than on the whole project. A second registration for a name
is refused unless `replace=True` — a silent replacement would drop the
first keyer’s parts from every key without anyone saying so.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.build.keys.registered_shot_keyers()

The renderer names that have a keyer.

A keyer registers beside its renderer, and a backend behind the import
firewall registers when the renderer registry first loads it (an#247), so
this loads the registry first.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> "cutout" in registered_shot_keyers()
True
```

### an.build.keys.shot_keyer_for(renderer)

The keyer that describes `renderer` (an instance, or a name), or `None`.

`None` means the shot is never cached: no keyer for the name, or a
renderer whose class is not the one the keyer was registered for.

* **Return type:**
  `_KeyerEntry` | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.build.keys.store_digest(store)

A digest of one store’s whole content.

A filesystem store (one exposing `_root`) is digested from its FILES,
sidecars included — a character’s `meta.json` is not its art; the SVG
parts beside it are. That reads behind the mapping, which is ADR 0004’s gap
3 (“art bypasses the mall”), and it is exactly why this is the fallback:
once art is read through the stores (the asset library, ADR 0005), a
read-recording view replaces it with the keys a shot actually read. Any
other mapping is digested from its items.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> store_digest({"a": {"x": 1}}) == store_digest({"a": {"x": 1}})
True
>>> store_digest({"a": {"x": 1}}) == store_digest({"a": {"x": 2}})
False
```
