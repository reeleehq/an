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

An ASSEMBLED film (transitions, a sound layer) is a stream-copy concat of
segments (`an.assemble`, an#260): a shot no transition touches needs only its
mp4, and a shot one touches also needs its *parts* — its body, encoded once,
and the PNGs inside its transition window — a second entry,
`<key>.parts.<code>.h<head>.t<tail>`, of a few MB. So such a film reuses its
shots by default. (The older whole-frames entry, `<key>.frames`, is read only
by a caller that asks for it with `needs_frames=True`; the render loop no
longer does.)

Each cached render also records a *root* (`root.<digest>`): which entries a
render of output `<name>` under one set of render knobs on one machine used.
Roots are what `an.build.gc` keeps alive, beside what the current scene reaches.

**Invalidation is by digest, never by deletion** (decision 6): a changed input
is a different key, and the old entry simply stops being asked for. The
pre-cache `artifacts/shots/<shot.id>.mp4` archive is not read. Collecting
unreachable entries is a separate, explicit command: `an cache gc`
([`an.build.gc`](an.build.gc.md#module-an.build.gc)).

```pycon
>>> from an.build.shot_cache import BuildReport, ShotOutcome
>>> r = BuildReport([ShotOutcome("a", "cutout", "reused", key="k" * 64),
...                  ShotOutcome("b", "cutout", "rendered", key="j" * 64, reason="new or changed")])
>>> r.summary()
'2 shot(s): 1 rendered (b), 1 reused (a); not reused: new or changed (b)'
```

### Module Attributes

| [`SHOT_CACHE_STORE`](#an.build.shot_cache.SHOT_CACHE_STORE)   | The mall key of the shot cache.                                                                                          |
|---------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| [`PARTS_INFIX`](#an.build.shot_cache.PARTS_INFIX)        | what an assembled film takes from a shot its transitions touch — its body, encoded once, and the PNGs inside its window. |
| [`ROOT_PREFIX`](#an.build.shot_cache.ROOT_PREFIX)        | what one render used (see [`ShotCache.record_root()`](#an.build.shot_cache.ShotCache.record_root)).                     |

### Functions

| [`default_environment_digest`](#an.build.shot_cache.default_environment_digest)(renderer_name)        | The digest of `renderer_name`'s registered environment probe, once per process.                                                                  |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| [`explain_change`](#an.build.shot_cache.explain_change)(before, before_reads, after, ...) | Why a shot keyed `after` is not the entry keyed `before`, in words.                                                                              |
| [`human_bytes`](#an.build.shot_cache.human_bytes)(n)                                   | `n` bytes for a person: 1024-based, one decimal.                                                                                                 |
| [`in_memory_shot_cache_store`](#an.build.shot_cache.in_memory_shot_cache_store)()                     | A shot cache held in dicts — for tests, and for a mall with no disk.                                                                             |
| [`machine_id`](#an.build.shot_cache.machine_id)()                                     | A short digest naming this machine (its host name and hardware address), so each machine's renders of a synced project keep a root of their own. |
| [`project_id`](#an.build.shot_cache.project_id)(project_root)                         | A short digest naming a project by its resolved directory, so two projects sharing one cache store keep a root each (`""` for none).             |
| [`parts_entry_id`](#an.build.shot_cache.parts_entry_id)(key, window)                      | The catalog id of the parts entry of shot `key` for `window`.                                                                                    |
| [`resolve_incremental`](#an.build.shot_cache.resolve_incremental)(incremental)                 | `incremental=` → an engine, or `None` for "render every shot cold".                                                                              |
| [`shot_artifact_type`](#an.build.shot_cache.shot_artifact_type)()                             | The record type (`lacing.Artifact` subclass), built on first use.                                                                                |
| [`shot_cache_store`](#an.build.shot_cache.shot_cache_store)(root)                           | A filesystem shot cache under `root`: `catalog/` + `blobs/` (lacing's layout).                                                                   |
| [`store_usage`](#an.build.shot_cache.store_usage)(store)                               | `(bytes, entries)` of a shot cache store: every blob byte on disk (or, off disk, every distinct blob its records name) and its catalog entries.  |

### Classes

| [`BuildReport`](#an.build.shot_cache.BuildReport)([outcomes, store_bytes, ...])       | Every shot's outcome, in timeline order.                                      |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`IncrementalEngine`](#an.build.shot_cache.IncrementalEngine)(\*args, \*\*kwargs)           | The `incremental=` seam of `an.render.render` (ADR 0004 decision 5).          |
| [`ShotCache`](#an.build.shot_cache.ShotCache)([store, environment, ...])            | The built-in engine: look a shot's key up in an ArtifactStore; record misses. |
| [`ShotOutcome`](#an.build.shot_cache.ShotOutcome)(shot_id, renderer, status[, ...])   | What happened to one shot in one render, with its wall times (seconds).       |
| [`ShotPlan`](#an.build.shot_cache.ShotPlan)(shot_id, renderer, key[, inputs, ...]) | The engine's answer for one shot: its key, and what to reuse if anything.     |

### Exceptions

| [`ShotCacheWarning`](#an.build.shot_cache.ShotCacheWarning)   | The shot cache could not do something it should have; the render still stands.   |
|---------------------------------------------------------------------|----------------------------------------------------------------------------------|

### *class* an.build.shot_cache.BuildReport(outcomes=<factory>, store_bytes=None, store_entries=None)

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

### *class* an.build.shot_cache.IncrementalEngine(\*args, \*\*kwargs)

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

### an.build.shot_cache.PARTS_INFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '.parts.'*

what an assembled
film takes from a shot its transitions touch — its body, encoded once, and
the PNGs inside its window. See [`parts_entry_id()`](#an.build.shot_cache.parts_entry_id).

* **Type:**
  The catalog id infix of a shot’s PARTS entry (an#260)

### an.build.shot_cache.ROOT_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'root.'*

what one render used (see [`ShotCache.record_root()`](#an.build.shot_cache.ShotCache.record_root)).

* **Type:**
  The catalog id prefix of a ROOT

### an.build.shot_cache.SHOT_CACHE_STORE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'shot_cache'*

The mall key of the shot cache.

### *class* an.build.shot_cache.ShotCache(store=None, \*, environment=<function default_environment_digest>, dependencies=<function project_dependencies>, fallback=<function every_asset_digest>, record_reads=True, cache_frames=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The built-in engine: look a shot’s key up in an ArtifactStore; record misses.

`store` is the injected `lacing.ArtifactStore`; `None` means the
mall’s `shot_cache` (resolved in `begin()`), and a mall without one
renders every shot. `environment(renderer_name) -> digest` is the
environment seam — injectable so a test (or a remote-render backend) can
state its machine rather than probe this one. Three dependency seams (see
`Dependencies`):

- `record_reads` (on by default) keys a shot whose keyer is registered
  with `records_reads=True` on the asset entries its compile read
  ([`an.build.reads`](an.build.reads.md#module-an.build.reads), an#316: the `assets` part), so an edit to an
  asset re-renders only the shots that read it;
- `fallback` is the `assets` part of every OTHER shot — a keyer that
  cannot vouch for its reads, or every shot under `record_reads=False`:
  by default every asset in the project (decision 3’s first slice);
- `dependencies` is what EVERY shot depends on (the `project` part): by
  default the library lockfile. `None` drops it, and `fallback=None`
  keys an unrecorded shot on its own parts alone — use either knowingly.

An engine built with other seams writes keys `an cache gc` (which
recomputes the current scene’s keys with the defaults) does not reach:
collect such a cache with the same engine.
`cache_frames` also stores each shot’s whole PNG sequence when a caller
plans with `needs_frames=True`. The render loop no longer does (an#260):
an assembled film takes a shot’s mp4 and, at a transition, its *parts*
(`window=`), which are cached by default at a few MB. Kept for callers of
the engine that need every frame; `an cache gc` collects old frames.

After a render, `report` holds what happened to each shot.

#### entry_ids(shot, renderer, ctx, , window=None)

The catalog ids a [`plan()`](#an.build.shot_cache.ShotCache.plan) of this shot would read — computed by
the same code, looking nothing up and rendering nothing. What
`an.build.gc` keeps for the current scene. Call `begin()` first.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### plan(shot, renderer, ctx, , needs_frames=False, window=None, force=False)

`window` is what an assembled film needs from this shot
(`an.assemble.ShotWindow`; `None` for a plain concat): a shot whose
window is not whole is reused only when its parts entry is there too.

* **Return type:**
  [`ShotPlan`](#an.build.shot_cache.ShotPlan)

#### record_parts(plan, parts)

Store a freshly rendered shot’s `an.assemble.ShotParts` under
`plan.parts_id`: its body mp4 and its window’s PNGs, one stored zip.
A failed write never fails the render (the next render renders it).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### record_root(output_name, , profile, output)

Record what this render used, as a ROOT for `an.build.gc`; return its id.

A root is keyed by the project ([`project_id()`](#an.build.shot_cache.project_id)), the output name,
the render `profile` (the knobs as passed — `None` meaning “the
scene’s own”) and this machine ([`machine_id()`](#an.build.shot_cache.machine_id)), so the next render
of the same output with the same knobs on the same machine replaces it
— a browser upgrade included — while a render on another machine of a
synced project, or of another project sharing the store, keeps its own. Its record is a `lacing.Artifact` of the delivered film,
derived from the shot keys. Also measures the store, for the summary.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *exception* an.build.shot_cache.ShotCacheWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

The shot cache could not do something it should have; the render still stands.

### *class* an.build.shot_cache.ShotOutcome(shot_id, renderer, status, key=None, reason='', key_s=None, compile_s=None, render_s=None, cached_render_s=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What happened to one shot in one render, with its wall times (seconds).

`key_s` is the whole key computation, of which `compile_s` is the
compile; `render_s` is this render’s wall time (`None` when reused) and
`cached_render_s` the wall time of the render being reused.

### *class* an.build.shot_cache.ShotPlan(shot_id, renderer, key, inputs=<factory>, reads=<factory>, code=<factory>, cached=None, reason='', key_s=None, compile_s=None, cached_render_s=None, needs_frames=False, window=None, parts_id=None, parts=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The engine’s answer for one shot: its key, and what to reuse if anything.

#### code *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

The render path’s modules, digested (`{module: digest}`, an#395).

#### parts *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= None*

The reused parts (`an.assemble.ShotParts`), materialised for this plan.

#### parts_id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The catalog id of this shot’s parts entry, when its window is not whole.

#### reads *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

The asset entries the shot read, digested (`{"store/key": digest}`).

#### window *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= None*

What an assembled film needs from this shot (`an.assemble.ShotWindow`);
`None` for a film that is a plain concat of shot mp4s.

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

### an.build.shot_cache.explain_change(before, before_reads, after, after_reads, , before_code=None, after_code=None)

Why a shot keyed `after` is not the entry keyed `before`, in words.

The assets it read that moved come first, by name (`asset changed:
props/logo`), then every other key part that moved, appeared or went, by
`PART_LABELS` (an optional part — `fonts`, `runtime_extensions` —
comes and goes with what the shot draws). The parts that follow from an
asset (`FOLLOWS_ASSETS`) are left out when one is named. Both keys
are of one composition: a different `key_version` is
`KEY_FORMAT_CHANGED`, decided before this is called.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> explain_change({"compiled": "a", "assets": "x"}, {"props/logo": "1"},
...                {"compiled": "b", "assets": "y"}, {"props/logo": "2"})
'asset changed: props/logo'
>>> explain_change({"knobs": "a", "compiled": "c"}, {}, {"knobs": "b", "compiled": "c"}, {})
'render settings changed'
>>> explain_change({"compiled": "a"}, {}, {"compiled": "a", "fonts": "f"}, {})
'the system fonts changed'
>>> explain_change({"assets": "a"}, {}, {"assets": "b"}, {})  # an unrecorded shot
'a project asset changed'
>>> explain_change({"code": "a"}, {}, {"code": "b"}, {},
...                before_code={"an.motion": "1"}, after_code={"an.motion": "2"})
"an's render code (an.motion) changed"
```

### an.build.shot_cache.human_bytes(n)

`n` bytes for a person: 1024-based, one decimal.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> human_bytes(0), human_bytes(1536), human_bytes(5 * 1024**3)
('0 B', '1.5 KB', '5.0 GB')
```

### an.build.shot_cache.in_memory_shot_cache_store()

A shot cache held in dicts — for tests, and for a mall with no disk.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.build.shot_cache.machine_id()

A short digest naming this machine (its host name and hardware
address), so each machine’s renders of a synced project keep a root of
their own. A digest, never the names themselves.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> len(machine_id())
16
```

### an.build.shot_cache.parts_entry_id(key, window)

The catalog id of the parts entry of shot `key` for `window`.

The id names the window (the same shot cut for another neighbour is a
different entry) and the digest of the code that cuts and encodes the parts
(`parts_code_digest()`): a parts entry is produced by `an.assemble`, not
by the renderer, so the renderer’s own `code` key part does not cover it.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> from an.assemble import ShotWindow
>>> parts_entry_id("k" * 64, ShotWindow(frames=30, head=0, tail=4)).endswith(".h0.t4")
True
```

### an.build.shot_cache.project_id(project_root)

A short digest naming a project by its resolved directory, so two
projects sharing one cache store keep a root each (`""` for none).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> project_id(None)
''
>>> len(project_id("."))
16
```

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

### an.build.shot_cache.store_usage(store)

`(bytes, entries)` of a shot cache store: every blob byte on disk (or,
off disk, every distinct blob its records name) and its catalog entries.

On a filesystem store this is a directory listing, not a read of every
record, so the render summary can afford it on every render.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]
