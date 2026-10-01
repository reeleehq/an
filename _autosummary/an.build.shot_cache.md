# an.build.shot_cache

The content-keyed shot cache: ADR 0004’s first slice, behind the `incremental=` seam.

`render_project` asks an *incremental engine*, per shot, for a plan: the
shot’s key, and — when an entry with that key exists — the rendered shot to
reuse. It renders only the misses, and hands each fresh render back to be
recorded. The engine is a seam (`incremental=` on `an.render.render`), and
[`ShotCache`](#an.build.shot_cache.ShotCache) is its built-in default; an `nw`-backed engine is the
planned alternative (ADR 0004 decision 5).

\*\*Data model: `lacing`’s\*\* (decision 4). An entry is a `ShotArtifact` —
a `lacing.Artifact` (`asset_id` = sha256 of the mp4, W3C-PROV provenance
whose `was_derived_from` lists the key’s input digests) plus the named parts
of its key and the timings that produced it. Entries live in a
`lacing.ArtifactStore`: a catalog (`key -> record`) and a content-addressed
blob store, both injected `dol` mappings. In a project the store is
`mall["shot_cache"]` (`artifacts/shot_cache/{catalog,blobs}/`).

A film ASSEMBLED from frames (transitions, a sound layer) needs each shot’s
PNGs too; those are cached only with `ShotCache(cache_frames=True)`, so by
default such a film re-renders its shots.

**Invalidation is by digest, never by deletion** (decision 6): a changed input
is a different key, and the old entry simply stops being asked for. The
pre-cache `artifacts/shots/<shot.id>.mp4` archive is not read. Collecting
unreachable blobs is a separate, explicit command (not in this slice).

```pycon
>>> from an.build.shot_cache import BuildReport, ShotOutcome
>>> r = BuildReport([ShotOutcome("a", "cutout", "reused", key="k" * 64),
...                  ShotOutcome("b", "cutout", "rendered", key="j" * 64, reason="new or changed")])
>>> r.summary()
'2 shot(s): 1 rendered (b), 1 reused (a); not reused: new or changed (b)'
```

### Module Attributes

| [`SHOT_CACHE_STORE`](#an.build.shot_cache.SHOT_CACHE_STORE)   | The mall key of the shot cache.   |
|---------------------------------------------------------------------|-----------------------------------|

### Functions

| [`default_environment_digest`](#an.build.shot_cache.default_environment_digest)(renderer_name)   | The digest of `renderer_name`'s registered environment probe, once per process.   |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`in_memory_shot_cache_store`](#an.build.shot_cache.in_memory_shot_cache_store)()                | A shot cache held in dicts — for tests, and for a mall with no disk.              |
| [`resolve_incremental`](#an.build.shot_cache.resolve_incremental)(incremental)            | `incremental=` → an engine, or `None` for "render every shot cold".               |
| [`shot_artifact_type`](#an.build.shot_cache.shot_artifact_type)()                        | The record type (`lacing.Artifact` subclass), built on first use.                 |
| [`shot_cache_store`](#an.build.shot_cache.shot_cache_store)(root)                      | A filesystem shot cache under `root`: `catalog/` + `blobs/` (lacing's layout).    |

### Classes

| [`BuildReport`](#an.build.shot_cache.BuildReport)([outcomes])                         | Every shot's outcome, in timeline order.                                      |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`IncrementalEngine`](#an.build.shot_cache.IncrementalEngine)(\*args, \*\*kwargs)           | The `incremental=` seam of `an.render.render` (ADR 0004 decision 5).          |
| [`ShotCache`](#an.build.shot_cache.ShotCache)([store, environment, ...])            | The built-in engine: look a shot's key up in an ArtifactStore; record misses. |
| [`ShotOutcome`](#an.build.shot_cache.ShotOutcome)(shot_id, renderer, status[, ...])   | What happened to one shot in one render, with its wall times (seconds).       |
| [`ShotPlan`](#an.build.shot_cache.ShotPlan)(shot_id, renderer, key[, inputs, ...]) | The engine's answer for one shot: its key, and what to reuse if anything.     |

### Exceptions

| [`ShotCacheWarning`](#an.build.shot_cache.ShotCacheWarning)   | The shot cache could not do something it should have; the render still stands.   |
|---------------------------------------------------------------------|----------------------------------------------------------------------------------|

### *class* an.build.shot_cache.BuildReport(outcomes=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Every shot’s outcome, in timeline order.

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

### *class* an.build.shot_cache.IncrementalEngine(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

The `incremental=` seam of `an.render.render` (ADR 0004 decision 5).

`begin` once per render with the project mall (and its root, for the
root files every shot depends on); `plan` once per shot,
BEFORE any shot renders (in the calling thread); `record` once per shot
that was rendered (possibly from a worker thread); `finish` returns the
report.

### an.build.shot_cache.SHOT_CACHE_STORE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'shot_cache'*

The mall key of the shot cache.

### *class* an.build.shot_cache.ShotCache(store=None, \*, environment=<function default_environment_digest>, dependencies=<function project_assets_digest>, cache_frames=False)

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
`cache_frames` also stores each shot’s PNG sequence, which an ASSEMBLED
film (transitions, a sound layer) needs to reuse a shot; off by default,
because a 1080p shot’s frames are hundreds of MB and nothing collects
unreachable entries yet — so an assembled film re-renders its shots.

After a render, `report` holds what happened to each shot.

### *exception* an.build.shot_cache.ShotCacheWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

The shot cache could not do something it should have; the render still stands.

### *class* an.build.shot_cache.ShotOutcome(shot_id, renderer, status, key=None, reason='', key_s=None, compile_s=None, render_s=None, cached_render_s=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What happened to one shot in one render, with its wall times (seconds).

`key_s` is the whole key computation, of which `compile_s` is the
compile; `render_s` is this render’s wall time (`None` when reused) and
`cached_render_s` the wall time of the render being reused.

### *class* an.build.shot_cache.ShotPlan(shot_id, renderer, key, inputs=<factory>, cached=None, reason='', key_s=None, compile_s=None, cached_render_s=None, needs_frames=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The engine’s answer for one shot: its key, and what to reuse if anything.

### an.build.shot_cache.default_environment_digest(renderer_name)

The digest of `renderer_name`’s registered environment probe, once per process.

Memoised per renderer NAME (each backend has its own machine: Chromium and
ffmpeg for cut-out, a Manim install for Manim), and once per process,
because the cut-out probe launches a browser and encodes a frame. So a
long-lived host does not see a `playwright install` or a `brew upgrade`
made after its first render: restart it, or pass `force_render`. A
renderer with no probe has the empty environment.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.build.shot_cache.in_memory_shot_cache_store()

A shot cache held in dicts — for tests, and for a mall with no disk.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.build.shot_cache.resolve_incremental(incremental)

`incremental=` → an engine, or `None` for “render every shot cold”.

`True` is a fresh [`ShotCache`](#an.build.shot_cache.ShotCache) over the mall’s store; `False` or
`None` is off; anything else must be an [`IncrementalEngine`](#an.build.shot_cache.IncrementalEngine).

* **Return type:**
  [`IncrementalEngine`](#an.build.shot_cache.IncrementalEngine) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> resolve_incremental(False) is None
True
>>> isinstance(resolve_incremental(True), ShotCache)
True
```

### an.build.shot_cache.shot_artifact_type()

The record type (`lacing.Artifact` subclass), built on first use.

### an.build.shot_cache.shot_cache_store(root)

A filesystem shot cache under `root`: `catalog/` + `blobs/` (lacing’s layout).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)
