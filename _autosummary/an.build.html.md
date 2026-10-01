# an.build

Incremental re-processing: content-addressed build stages (ADR 0004).

A draft must stay adjustable without re-processing everything: an edit
re-renders only what depends on it. The first slice is the **shot cache** —
`an render` skips any shot whose key (everything its render reads, digested;
never `shot.id`) already has an entry, and reuses that entry’s mp4.

- [`an.build.keys`](an.build.keys.html.md#module-an.build.keys) — canonical digests, the project-wide fallback
  dependency, and the registry through which a renderer says what its shot
  render reads ([`register_shot_keyer()`](#an.build.register_shot_keyer)).
- [`an.build.shot_cache`](an.build.shot_cache.html.md#module-an.build.shot_cache) — the `incremental=` seam
  ([`IncrementalEngine`](#an.build.IncrementalEngine)), its built-in engine [`ShotCache`](#an.build.ShotCache), and
  the entries, shaped as `lacing` artifacts in a `lacing.ArtifactStore`.
- [`an.build.gc`](an.build.gc.html.md#module-an.build.gc) — garbage collection: what the current scene and the
  recorded renders reach, and deleting the rest (`an cache gc`,
  `an cache info`; [`an.build.cli`](an.build.cli.html.md#module-an.build.cli)).

The core names no renderer; the cut-out keyer lives with the cut-out backend
(`an.stage.cache_key`) and registers on its import.

```pycon
>>> from an.build import ShotCache, resolve_incremental
>>> isinstance(resolve_incremental(True), ShotCache)
True
```

### Functions

| [`cache_info`](#an.build.cache_info)(project_dir, \*[, reachability, ...])   | What `project_dir`'s shot cache holds; never fails on reachability (it says why it is unknown instead).   |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| [`canonical_digest`](#an.build.canonical_digest)(obj)                              | The hex sha256 of `canonical_json()` of `obj`.                                                            |
| [`collect_garbage`](#an.build.collect_garbage)(project_dir, \*[, dry_run, ...])   | Delete the shot-cache entries of `project_dir` that nothing reaches.                                      |
| [`compose_shot_key`](#an.build.compose_shot_key)(parts)                            | The shot key: one digest over the named parts and the key's own version.                                  |
| [`default_environment_digest`](#an.build.default_environment_digest)(renderer_name)          | The digest of `renderer_name`'s registered environment probe, once per process.                           |
| [`in_memory_shot_cache_store`](#an.build.in_memory_shot_cache_store)()                       | A shot cache held in dicts — for tests, and for a mall with no disk.                                      |
| [`project_assets_digest`](#an.build.project_assets_digest)(mall, \*[, stores, ...])     | One digest over every asset store of the project (ADR 0004 decision 3).                                   |
| [`register_shot_keyer`](#an.build.register_shot_keyer)(renderer_name, keyer, \*)      | Declare how shots of `renderer_name` are keyed, and how its machine is probed.                            |
| [`registered_shot_keyers`](#an.build.registered_shot_keyers)()                           | The renderer names that have a keyer.                                                                     |
| [`resolve_incremental`](#an.build.resolve_incremental)(incremental)                   | `incremental=` → an engine, or `None` for "render every shot cold".                                       |
| [`shot_artifact_type`](#an.build.shot_artifact_type)()                               | The record type (`lacing.Artifact` subclass), built on first use.                                         |
| [`shot_cache_store`](#an.build.shot_cache_store)(root)                             | A filesystem shot cache under `root`: `catalog/` + `blobs/` (lacing's layout).                            |
| [`shot_keyer_for`](#an.build.shot_keyer_for)(renderer)                           | The keyer that describes `renderer` (an instance, or a name), or `None`.                                  |

### Classes

| [`BuildReport`](#an.build.BuildReport)([outcomes, store_bytes, ...])       | Every shot's outcome, in timeline order.                                      |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`IncrementalEngine`](#an.build.IncrementalEngine)(\*args, \*\*kwargs)           | The `incremental=` seam of `an.render.render` (ADR 0004 decision 5).          |
| [`ShotCache`](#an.build.ShotCache)([store, environment, ...])            | The built-in engine: look a shot's key up in an ArtifactStore; record misses. |
| [`ShotKeyInputs`](#an.build.ShotKeyInputs)(parts[, compile_s, details])      | What a renderer's keyer returns for one shot.                                 |
| [`ShotOutcome`](#an.build.ShotOutcome)(shot_id, renderer, status[, ...])   | What happened to one shot in one render, with its wall times (seconds).       |
| [`ShotPlan`](#an.build.ShotPlan)(shot_id, renderer, key[, inputs, ...]) | The engine's answer for one shot: its key, and what to reuse if anything.     |

### Exceptions

| [`CacheGcError`](#an.build.CacheGcError)     | The collection cannot be done safely; nothing was deleted.                     |
|-------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`ShotCacheWarning`](#an.build.ShotCacheWarning) | The shot cache could not do something it should have; the render still stands. |

### *class* an.build.BuildReport(outcomes=<factory>, store_bytes=None, store_entries=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Every shot’s outcome, in timeline order.

#### store_bytes *: [int](https://docs.python.org/3/builtins/functions.html#int) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The shot cache’s size after the render, when the engine measured it.

#### store_line()

How big the shot cache is after the render, or `""` if unmeasured.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> BuildReport(store_bytes=3 * 1024**2, store_entries=4).store_line()
'3.0 MB in 4 entries'
```

#### summary()

One line: what was rendered, what reused, and WHY each rendered shot
was not reused — a cache that silently re-renders everything reads as
a broken cache (an#243 review, R2-1).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> BuildReport([ShotOutcome("a", "cutout", "uncached", reason=FRAMES_NOT_CACHED)]).summary()
'1 shot(s): 1 rendered (a), 0 reused (-); not reused: frames not cached: film has transitions/sound; pass --cache-frames (a)'
```

#### timing_table()

A Markdown table of the per-shot wall times.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### *exception* an.build.CacheGcError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The collection cannot be done safely; nothing was deleted.

### *class* an.build.IncrementalEngine(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

The `incremental=` seam of `an.render.render` (ADR 0004 decision 5).

`begin` once per render with the project mall (and its root, for the
root files every shot depends on); `plan` once per shot,
BEFORE any shot renders (in the calling thread); `record` once per shot
that was rendered (possibly from a worker thread); `finish` returns the
report.

Two hooks are OPTIONAL (the render loop calls them when an engine has
them): `record_parts(plan, parts)` once per rendered shot whose film
window is not whole (an#260), and `record_root(output_name, profile=...,
output=...)` once the film is delivered (what the garbage collector keeps).

### *class* an.build.ShotCache(store=None, \*, environment=<function default_environment_digest>, dependencies=<function project_assets_digest>, cache_frames=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The built-in engine: look a shot’s key up in an ArtifactStore; record misses.

`store` is the injected `lacing.ArtifactStore`; `None` means the
mall’s `shot_cache` (resolved in `begin()`), and a mall without one
renders every shot. `environment(renderer_name) -> digest` is the
environment seam — injectable so a test (or a remote-render backend) can
state its machine rather than probe this one. `dependencies` is the
project-wide dependency strategy (see `Dependencies`); `None` keys
a shot on its own parts alone (its document and the bytes of the textures
it stages) — and then drops the lockfile too, so use it knowingly.
`cache_frames` also stores each shot’s whole PNG sequence when a caller
plans with `needs_frames=True`. The render loop no longer does (an#260):
an assembled film takes a shot’s mp4 and, at a transition, its *parts*
(`window=`), which are cached by default at a few MB. Kept for callers of
the engine that need every frame; `an cache gc` collects old frames.

After a render, `report` holds what happened to each shot.

#### entry_ids(shot, renderer, ctx, , window=None)

The catalog ids a [`plan()`](#an.build.ShotCache.plan) of this shot would read — computed by
the same code, looking nothing up and rendering nothing. What
`an.build.gc` keeps for the current scene. Call `begin()` first.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### plan(shot, renderer, ctx, , needs_frames=False, window=None, force=False)

`window` is what an assembled film needs from this shot
(`an.assemble.ShotWindow`; `None` for a plain concat): a shot whose
window is not whole is reused only when its parts entry is there too.

* **Return type:**
  [`ShotPlan`](an.build.shot_cache.html.md#an.build.shot_cache.ShotPlan)

#### record_parts(plan, parts)

Store a freshly rendered shot’s `an.assemble.ShotParts` under
`plan.parts_id`: its body mp4 and its window’s PNGs, one stored zip.
A failed write never fails the render (the next render renders it).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### record_root(output_name, , profile, output)

Record what this render used, as a ROOT for `an.build.gc`; return its id.

A root is keyed by the project (`project_id()`), the output name,
the render `profile` (the knobs as passed — `None` meaning “the
scene’s own”) and this machine (`machine_id()`), so the next render
of the same output with the same knobs on the same machine replaces it
— a browser upgrade included — while a render on another machine of a
synced project, or of another project sharing the store, keeps its own. Its record is a `lacing.Artifact` of the delivered film,
derived from the shot keys. Also measures the store, for the summary.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *exception* an.build.ShotCacheWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

The shot cache could not do something it should have; the render still stands.

### *class* an.build.ShotKeyInputs(parts, compile_s=None, details=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a renderer’s keyer returns for one shot.

`parts` are named sha256 hex digests (the key’s content half); the engine
adds `renderer`, `project` and `environment`. `compile_s` is the
wall time of the compile the keyer ran to get its digest, or `None` for a
renderer that has no compile stage.

#### details *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

Diagnostics a keyer wants on the record beside the digests — never part
of the key (the digests are).

### *class* an.build.ShotOutcome(shot_id, renderer, status, key=None, reason='', key_s=None, compile_s=None, render_s=None, cached_render_s=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What happened to one shot in one render, with its wall times (seconds).

`key_s` is the whole key computation, of which `compile_s` is the
compile; `render_s` is this render’s wall time (`None` when reused) and
`cached_render_s` the wall time of the render being reused.

### *class* an.build.ShotPlan(shot_id, renderer, key, inputs=<factory>, cached=None, reason='', key_s=None, compile_s=None, cached_render_s=None, needs_frames=False, window=None, parts_id=None, parts=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The engine’s answer for one shot: its key, and what to reuse if anything.

#### parts *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= None*

The reused parts (`an.assemble.ShotParts`), materialised for this plan.

#### parts_id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The catalog id of this shot’s parts entry, when its window is not whole.

#### window *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= None*

What an assembled film needs from this shot (`an.assemble.ShotWindow`);
`None` for a film that is a plain concat of shot mp4s.

### an.build.cache_info(project_dir, , reachability=True, engine=None, now=None)

What `project_dir`’s shot cache holds; never fails on reachability
(it says why it is unknown instead).

* **Return type:**
  [`CacheInfo`](an.build.gc.html.md#an.build.gc.CacheInfo)

### an.build.canonical_digest(obj)

The hex sha256 of `canonical_json()` of `obj`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.build.collect_garbage(project_dir, , dry_run=False, max_size=None, max_age=None, engine=None, now=None, force=False)

Delete the shot-cache entries of `project_dir` that nothing reaches.

With no cap, every unreachable entry goes. With caps, unreachable history
is kept within them, newest first, and both bind: `max_age` (seconds)
keeps only unreachable entries written more recently than that (and lets a
recorded render older than that stop protecting its entries); `max_size`
(bytes) keeps only those that fit in a cache of that size. Neither ever
removes a reachable entry, so the cache can stay above `max_size`.
`dry_run` reports and deletes nothing. `force` collects a cache no
render of this project has recorded a root in (see `reachable_entries()`).

See the module docstring for the reachability and concurrency argument.

* **Return type:**
  [`GcReport`](an.build.gc.html.md#an.build.gc.GcReport)

### an.build.compose_shot_key(parts)

The shot key: one digest over the named parts and the key’s own version.

The parts are a MAPPING so the record can keep them by name, and a
re-render can be explained (”`textures` moved”) rather than merely
observed.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.build.default_environment_digest(renderer_name)

The digest of `renderer_name`’s registered environment probe, once per process.

Memoised per renderer NAME (each backend has its own machine: Chromium and
ffmpeg for cut-out, a Manim install for Manim), and once per process,
because the cut-out probe launches a browser and encodes a frame. So a
long-lived host does not see a `playwright install` or a `brew upgrade`
made after its first render: restart it, or pass `force_render`. A
renderer with no probe has the empty environment.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.build.in_memory_shot_cache_store()

A shot cache held in dicts — for tests, and for a mall with no disk.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.build.project_assets_digest(mall, , stores=('characters', 'environments', 'props', 'styles', 'voices', 'sounds'), project_root=None, root_files=('assets.lock.json',))

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

### an.build.register_shot_keyer(renderer_name, keyer, , environment=None, renderer_type=None, replace=False)

Declare how shots of `renderer_name` are keyed, and how its machine is probed.

The registration seam for every backend (cut-out here; Manim’s opaque
shots, keyed on source hash + Manim version + quality, are the next).
`renderer_type` binds the keyer to one renderer class: a renderer whose
type is not exactly it is never cached. A second registration for a name
is refused unless `replace=True` — a silent replacement would drop the
first keyer’s parts from every key without anyone saying so.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.build.registered_shot_keyers()

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

### an.build.resolve_incremental(incremental)

`incremental=` → an engine, or `None` for “render every shot cold”.

`True` is a fresh [`ShotCache`](#an.build.ShotCache) over the mall’s store; `False` or
`None` is off; anything else must be an [`IncrementalEngine`](#an.build.IncrementalEngine).

* **Return type:**
  [`IncrementalEngine`](an.build.shot_cache.html.md#an.build.shot_cache.IncrementalEngine) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> resolve_incremental(False) is None
True
>>> isinstance(resolve_incremental(True), ShotCache)
True
```

### an.build.shot_artifact_type()

The record type (`lacing.Artifact` subclass), built on first use.

### an.build.shot_cache_store(root)

A filesystem shot cache under `root`: `catalog/` + `blobs/` (lacing’s layout).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.build.shot_keyer_for(renderer)

The keyer that describes `renderer` (an instance, or a name), or `None`.

`None` means the shot is never cached: no keyer for the name, or a
renderer whose class is not the one the keyer was registered for.

* **Return type:**
  `_KeyerEntry` | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### Modules

| [`cli`](an.build.cli.html.md#module-an.build.cli)               | `an cache …` — the shot cache from the shell (an#274).                                |
|----------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [`gc`](an.build.gc.html.md#module-an.build.gc)                 | Garbage collection of the shot cache: `an cache gc` and `an cache info` (an#274).     |
| [`keys`](an.build.keys.html.md#module-an.build.keys)             | Cache keys for build stages: canonical digests, the project fallback, keyers.         |
| [`shot_cache`](an.build.shot_cache.html.md#module-an.build.shot_cache) | The content-keyed shot cache: ADR 0004's first slice, behind the `incremental=` seam. |
