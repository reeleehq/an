# an.build.gc

Garbage collection of the shot cache: `an cache gc` and `an cache info` (an#274).

ADR 0004 decision 6: invalidation is by digest, never by deletion, so every
edit leaves the old entries behind — an end user’s `artifacts/shot_cache`
reached 4.9 GB after nine renders of a 16 s film. Collecting them is a
separate, explicit command, and this module is it.

**What is kept (reachable).** An entry is reachable when either

- a render of the project’s CURRENT scene would read it — under any knob set
  a recorded render ever used, or under a plain `an render`’s — computed
  by the render loop’s own setup and the engine’s own key code, with the
  dialogue stamped from the audio stores as the render stamps it
  ([`an.render.cache_entries()`](an.render.md#an.render.cache_entries)); or
- the latest render of an output, under one knob set, on one machine, used it
  — its *root* ([`an.build.ShotCache.record_root()`](an.build.md#an.build.ShotCache.record_root)). This keeps what a
  render on ANOTHER machine of a synced project used, which this machine
  cannot recompute (its environment digest differs).

A cache no render of the project has recorded a root in (one written before
an#274) is refused unless `force`: the current scene’s keys alone are then
the only evidence, and a render’s knobs or providers that differ from the
defaults would leave its entries looking unreachable.

**A knob set under which the current scene has a line with no audio** (an#306)
— a line edited since the last render under it, or the plain render’s
hypothetical knobs for a project only ever spoken by ElevenLabs — has no keys
to compute until that line is synthesised, so nothing in the cache can be its
entry for that shot. It is skipped rather than refused, and what each root
recorded under it is kept whatever `--max-age` says, so its unchanged shots
stay. Only when the current scene can be keyed under NO knob set (every one
lacks some line’s audio: the scene has lines nothing has synthesised) is the
collection refused — render first. Each knob set is replayed with its OWN
providers (a root’s recorded `tts`), never with a command line’s defaults.

Everything else is unreachable: the entries of shots as they were before an
edit, parts cut for an old neighbour, whole-frame entries (`<key>.frames`)
that no render reads since an#260, and unreadable records.

**What is never deleted.** A reachable entry, whatever the caps say (a cap
trims unreachable history only; `--max-age` lets an old root stop naming its
entries, never stops its knob set being recomputed). A root. An entry
written after the collection began, or after the start of any render of the
project still in progress (`.an/render_work/runs/<run>/.live`), minus
[`CLOCK_SLACK_S`](#an.build.gc.CLOCK_SLACK_S): a render’s entries are protected from the moment its
run starts until its root records them. A blob still named by a kept record.

**What a concurrent render can see**, at worst: an entry it looked up being
collected between reading its record and its blob — a miss, so that shot
renders again. Never a wrong picture: every blob is checked against its id
(its sha256) when read, and a reused shot’s bytes are copied into the render’s
own run directory at lookup, before anything can remove them.

**Deletion is permanent.** `dol.Files` would move each file to the OS trash,
which frees nothing (and on macOS asks Finder once per file), so on a
filesystem store the catalog record and the blob are unlinked directly, in the
layout `lacing.ArtifactStore.from_directory` documents.

```pycon
>>> parse_size("2G"), parse_size("500MB"), parse_age("36h"), parse_age("7d")
(2147483648, 524288000, 129600.0, 604800.0)
```

### Module Attributes

| [`CLOCK_SLACK_S`](#an.build.gc.CLOCK_SLACK_S)         | a file system's timestamp granularity, and the gap between a record's provenance time and the moment it lands.                                                                                      |
|------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DEFAULT_PROFILE`](#an.build.gc.DEFAULT_PROFILE)       | The render knobs of a plain `an render` (and of `render_project`'s defaults), as `ShotCache.record_root()` records them: `tts` is each voice's own provider (an#305).                               |
| [`HYPOTHETICAL_PROFILES`](#an.build.gc.HYPOTHETICAL_PROFILES) | today's ([`DEFAULT_PROFILE`](#an.build.gc.DEFAULT_PROFILE)) and the one before an#305, which spoke every line offline — what a cache written before roots existed was rendered with. |

### Functions

| [`cache_info`](#an.build.gc.cache_info)(project_dir, \*[, reachability, ...])   | What `project_dir`'s shot cache holds; never fails on reachability (it says why it is unknown instead).   |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| [`collect_garbage`](#an.build.gc.collect_garbage)(project_dir, \*[, dry_run, ...])   | Delete the shot-cache entries of `project_dir` that nothing reaches.                                      |
| [`inventory`](#an.build.gc.inventory)(store)                                   | Every catalog record of `store`, read once.                                                               |
| [`parse_age`](#an.build.gc.parse_age)(text)                                    | `"7d"`, `"36h"`, `"90m"`, `"2w"`, `"30s"` → seconds.                                                      |
| [`parse_size`](#an.build.gc.parse_size)(text)                                   | `"2G"`, `"500MB"`, `"1.5GB"`, `"1048576"` → bytes (1024-based).                                           |
| [`reachable_entries`](#an.build.gc.reachable_entries)(project, store, \*[, ...])       | What the project's current scene and its recorded roots reach.                                            |

### Classes

| [`CacheEntry`](#an.build.gc.CacheEntry)(id, role[, asset_id, bytes_size, ...])   | One catalog record: its id, what it holds, its blob, and when it was written.            |
|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| [`CacheInfo`](#an.build.gc.CacheInfo)(path[, total_bytes, by_role, ...])        | The shot cache's size, what it holds, and how much of it is reachable.                   |
| [`GcReport`](#an.build.gc.GcReport)(dry_run[, deleted, deleted_blobs, ...])    | What a collection deleted (or, with `dry_run`, would delete), and why the rest was kept. |
| [`Reachability`](#an.build.gc.Reachability)([from_scene, from_roots, ...])         | What the current scene and the recorded roots keep, and why.                             |

### Exceptions

| [`CacheGcError`](#an.build.gc.CacheGcError)   | The collection cannot be done safely; nothing was deleted.   |
|-----------------------------------------------------------------|--------------------------------------------------------------|

### an.build.gc.CLOCK_SLACK_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 2.0*

a file
system’s timestamp granularity, and the gap between a record’s provenance
time and the moment it lands.

* **Type:**
  Seconds before a protection horizon still treated as “after” it

### *class* an.build.gc.CacheEntry(id, role, asset_id=None, bytes_size=0, written_at=None, record=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One catalog record: its id, what it holds, its blob, and when it was written.

### *exception* an.build.gc.CacheGcError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The collection cannot be done safely; nothing was deleted.

### *class* an.build.gc.CacheInfo(path, total_bytes=0, by_role=<factory>, reachable=None, unreachable=None, orphan_blobs=(0, 0), roots=<factory>, reachability_error='', skipped=<factory>, derived=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The shot cache’s size, what it holds, and how much of it is reachable.

#### derived *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), DerivedUsage]*

The renderers’ derived stores (an#299), by store name.

### an.build.gc.DEFAULT_PROFILE *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]* *= {'capture': None, 'fps': None, 'language': 'en', 'lipsync': 'offline', 'pix_fmt': None, 'resolution': None, 'step_hz': None, 'strict_assets': False, 'supersample': 1, 'tts': 'voice'}*

The render knobs of a plain `an render` (and of `render_project`’s
defaults), as `ShotCache.record_root()` records them: `tts` is each
voice’s own provider (an#305). Always among the profiles the current scene
is keyed under, so a cache written before roots existed keeps what a plain
render of the current scene reads.

### *class* an.build.gc.GcReport(dry_run, deleted=<factory>, deleted_blobs=<factory>, kept_reachable=0, kept_protected=<factory>, kept_retained=0, failed=<factory>, bytes_before=0, reach=None, deleted_derived=<factory>, derived_freed=0, kept_derived=0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a collection deleted (or, with `dry_run`, would delete), and why
the rest was kept.

#### deleted_derived *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

what was (or would be) deleted,
by store, and the bytes that frees.

* **Type:**
  The renderers’ derived stores (an#299)

### an.build.gc.HYPOTHETICAL_PROFILES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)], ...]* *= ({'capture': None, 'fps': None, 'language': 'en', 'lipsync': 'offline', 'pix_fmt': None, 'resolution': None, 'step_hz': None, 'strict_assets': False, 'supersample': 1, 'tts': 'voice'}, {'capture': None, 'fps': None, 'language': 'en', 'lipsync': 'offline', 'pix_fmt': None, 'resolution': None, 'step_hz': None, 'strict_assets': False, 'supersample': 1, 'tts': 'offline'})*

today’s
([`DEFAULT_PROFILE`](#an.build.gc.DEFAULT_PROFILE)) and the one before an#305, which spoke every line
offline — what a cache written before roots existed was rendered with.

* **Type:**
  The knob sets a plain render used or uses, recorded by a root or not

### *class* an.build.gc.Reachability(from_scene=<factory>, from_roots=<factory>, profiles=<factory>, roots=<factory>, skipped=<factory>, derived=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What the current scene and the recorded roots keep, and why.

`profiles` are the knob sets the current scene was keyed under;
`skipped` the ones it could not be (`(profile, why)`: a line’s audio
is not cached under it — an#306), whose roots keep what they recorded.

#### derived *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [set](https://docs.python.org/3/builtins/stdtypes.html#set)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

The renderers’ derived-store entries the current scene reads, by store
(a Manim picture, its measurement and contact sheet; an#299).

### an.build.gc.cache_info(project_dir, , reachability=True, engine=None, now=None)

What `project_dir`’s shot cache holds; never fails on reachability
(it says why it is unknown instead).

* **Return type:**
  [`CacheInfo`](#an.build.gc.CacheInfo)

### an.build.gc.collect_garbage(project_dir, , dry_run=False, max_size=None, max_age=None, engine=None, now=None, force=False)

Delete the shot-cache entries of `project_dir` that nothing reaches.

With no cap, every unreachable entry goes. With caps, unreachable history
is kept within them, newest first, and both bind: `max_age` (seconds)
keeps only unreachable entries written more recently than that (and lets a
recorded render older than that stop protecting its entries); `max_size`
(bytes) keeps only those that fit in a cache of that size. Neither ever
removes a reachable entry, so the cache can stay above `max_size`.
`dry_run` reports and deletes nothing. `force` collects a cache no
render of this project has recorded a root in (see [`reachable_entries()`](#an.build.gc.reachable_entries)).

See the module docstring for the reachability and concurrency argument.

* **Return type:**
  [`GcReport`](#an.build.gc.GcReport)

### an.build.gc.inventory(store)

Every catalog record of `store`, read once. An unreadable record is
listed with role `"unreadable"` and, on disk, its file’s mtime.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`CacheEntry`](#an.build.gc.CacheEntry)]

### an.build.gc.parse_age(text)

`"7d"`, `"36h"`, `"90m"`, `"2w"`, `"30s"` → seconds.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> parse_age("90m")
5400.0
```

### an.build.gc.parse_size(text)

`"2G"`, `"500MB"`, `"1.5GB"`, `"1048576"` → bytes (1024-based).

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> parse_size("1.5k")
1536
```

### an.build.gc.reachable_entries(project, store, , entries=None, engine=None, root_max_age=None, now=None, force=False)

What the project’s current scene and its recorded roots reach.

The current scene is keyed under the knobs of EVERY recorded root (of any
project, any age: a knob set is a few values, and dropping one would orphan
that render’s entries of the unchanged scene), each with its own recorded
providers, and under [`HYPOTHETICAL_PROFILES`](#an.build.gc.HYPOTHETICAL_PROFILES) (a plain render’s). A
root younger than `root_max_age` seconds (all, when `None`) also keeps
the entries it names; roots themselves are always kept.

A knob set under which some line’s audio is not cached cannot be keyed
without a synthesis (an#306): it is skipped, listed in `skipped`, and
every root recorded under it keeps its entries whatever `root_max_age`.

`engine` computes the keys (its environment seam included); `None` is
a default [`ShotCache`](an.build.md#an.build.ShotCache) over `store`, which probes this
machine like a render does. Raises [`CacheGcError`](#an.build.gc.CacheGcError) when the current
scene’s keys cannot be computed for any other reason, or under no knob set
at all (guessing is never safe), and when no render of THIS project has
recorded a root yet — a cache written before roots existed (an#274) —
unless `force`.

* **Return type:**
  [`Reachability`](#an.build.gc.Reachability)
