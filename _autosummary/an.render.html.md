# an.render

Project-level rendering: per-shot mp4 → final composited mp4 via ffmpeg concat.

The orchestrator picks a renderer per shot from the registry (matched on
`shot.renderer`) and renders each shot in isolation, then concatenates the
per-shot outputs into one final mp4 written to `project.mall["output"]`.

Phase 2D ships the cutout path; later phases register Manim / Remotion / etc.
adapters and the same flow handles them.

### Module Attributes

| [`RENDER_RUNS_DIR`](#an.render.RENDER_RUNS_DIR)        | one directory per CACHED render run.                                                                                                                                                                                       |
|-------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`RUN_LIVE_MARKER`](#an.render.RUN_LIVE_MARKER)        | the pid of the process rendering it (written at start).                                                                                                                                                                    |
| [`RUN_DONE_MARKER`](#an.render.RUN_DONE_MARKER)        | written when the run delivered its film.                                                                                                                                                                                   |
| [`TMP_TOKEN`](#an.render.TMP_TOKEN)              | What a temp-folder path becomes in a portable text ([`portable_text()`](#an.render.portable_text)).                                                                                                     |
| [`POSIX_TEMP_DIRS`](#an.render.POSIX_TEMP_DIRS)        | The temp folders every POSIX machine has, besides the one Python reports.                                                                                                                                                  |
| [`FINDING_GROUPS`](#an.render.FINDING_GROUPS)         | How `an render`'s summary heads each `kind` of finding, in this order; a kind not listed (another warning category) is headed by its own name, after.                                                                      |
| [`SUMMARY_MAX_PER_GROUP`](#an.render.SUMMARY_MAX_PER_GROUP)  | At most this many findings of one kind are listed in the summary.                                                                                                                                                          |
| [`UNKNOWN_LIVENESS_MAX_S`](#an.render.UNKNOWN_LIVENESS_MAX_S) | Where a run's process cannot be asked whether it lives (Windows), a run unfinished after this long is taken for one that crashed: otherwise it would shield every cache entry written since, from `an cache gc`, for ever. |

### Functions

| [`cache_entries`](#an.render.cache_entries)(project, engine, \*\*knobs)    | The shot-cache entry ids of [`cache_reach()`](#an.render.cache_reach) (what `an.build.gc` keeps of the shot cache, an#274).                                                                                                                                                                                                                                                                                                            |
|-----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`cache_reach`](#an.render.cache_reach)(project, engine, \*[, fps, ...]) | What a render of `project`'s CURRENT scene under these knobs would read — the shot-cache entry ids, and the record-store entries of the renderers' derived stores (a Manim shot's measurement record, which names its picture and contact sheet: [`an.build.derived`](an.build.derived.html.md#module-an.build.derived), an#299) — computed by the render's own setup and the engine's own key code, rendering and synthesising nothing. |
| [`format_render_findings`](#an.render.format_render_findings)(project[, ...])       | `an render`'s summary of what the render found: one heading per kind ([`FINDING_GROUPS`](#an.render.FINDING_GROUPS)) with its count, then each finding's IR path and message — the message carries its fix — at most `max_per_group` per kind.                                                                                                                                                                                            |
| [`live_runs`](#an.render.live_runs)(project_root)                      | Every cached render of this project still in progress, with the time it started (its live marker's mtime): what `an cache gc` must not race.                                                                                                                                                                                                                                                                                                                |
| [`portable_text`](#an.render.portable_text)(text, \*[, root, home, tmp])   | `text` with this machine's absolute paths taken out: a path under the project `root` becomes project-relative, the root itself `.`, a temp folder `<tmp>` and the home directory `~` — so a render report (which a project may commit or share, and an agent may pass on) names no user, host folder or temp dir.                                                                                                                                           |
| [`render`](#an.render.render)(project, \*[, output_name, fps, ...]) | Lower-level: render a loaded `Project` to mp4.                                                                                                                                                                                                                                                                                                                                                                                                              |
| [`render_findings`](#an.render.render_findings)(project[, output_name])      | The `Finding` s the last render of `output_name` reported (an#254), from `render_reports/<output_name>.json`; `[]` before any render.                                                                                                                                                                                                                                                                                                                       |
| [`render_project`](#an.render.render_project)(project_dir, \*[, ...])       | Render every shot in `project_dir`'s scene and concatenate to one mp4.                                                                                                                                                                                                                                                                                                                                                                                      |

### Classes

| [`CacheReach`](#an.render.CacheReach)([ids, derived])   | [`cache_reach()`](#an.render.cache_reach)'s answer: shot-cache ids, and derived-store entries by store name.   |
|-------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|

### Exceptions

| [`RenderError`](#an.render.RenderError)   | Raised on render-pipeline failures with actionable detail.   |
|----------------------------------------------------------------|--------------------------------------------------------------|

### *class* an.render.CacheReach(ids=<factory>, derived=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

[`cache_reach()`](#an.render.cache_reach)’s answer: shot-cache ids, and derived-store entries
by store name.

### an.render.FINDING_GROUPS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'CaptionTimingWarning': 'captions without word timings', 'CutoutAssetWarning': 'art that could not be staged', 'CutoutCompileWarning': 'stand-ins, substitutions and compile notes', 'ShotCacheWarning': 'the shot cache', 'TakeDigestWarning': 'takes whose audio is not the recorded one', 'VoiceLoudnessWarning': 'voices at very different loudness', 'VoiceStandInWarning': 'voices spoken by another provider than they declare', 'dialogue_fits': 'dialogue that does not fit its shot', 'dialogue_in_dissolve': 'dialogue heard during a dissolve', 'library_pins': 'library pins that disagree with assets.lock.json', 'measurement': 'shots whose renderer measured their length'}*

How `an render`’s summary heads each `kind` of finding, in this order; a
kind not listed (another warning category) is headed by its own name, after.

### an.render.POSIX_TEMP_DIRS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('/tmp', '/private/tmp', '/var/tmp')*

The temp folders every POSIX machine has, besides the one Python reports.

### an.render.RENDER_RUNS_DIR *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'runs'*

one directory per CACHED render run.

* **Type:**
  Under `.an/render_work/`

### an.render.RUN_DONE_MARKER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '.done'*

written when the run delivered its film.

* **Type:**
  In a run directory

### an.render.RUN_LIVE_MARKER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '.live'*

the pid of the process rendering it (written at start).

* **Type:**
  In a run directory

### *exception* an.render.RenderError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised on render-pipeline failures with actionable detail.

### an.render.SUMMARY_MAX_PER_GROUP *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 5*

At most this many findings of one kind are listed in the summary.

### an.render.TMP_TOKEN *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '<tmp>'*

What a temp-folder path becomes in a portable text ([`portable_text()`](#an.render.portable_text)).

### an.render.UNKNOWN_LIVENESS_MAX_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 86400.0*

Where a run’s process cannot be asked whether it lives (Windows), a run
unfinished after this long is taken for one that crashed: otherwise it would
shield every cache entry written since, from `an cache gc`, for ever.

### an.render.cache_entries(project, engine, \*\*knobs)

The shot-cache entry ids of [`cache_reach()`](#an.render.cache_reach) (what `an.build.gc`
keeps of the shot cache, an#274).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.render.cache_reach(project, engine, , fps=None, resolution=None, strict_assets=False, supersample=1, pix_fmt=None, capture=None, step_hz=None, tts=None, lipsync='offline', language='en')

What a render of `project`’s CURRENT scene under these knobs would
read — the shot-cache entry ids, and the record-store entries of the
renderers’ derived stores (a Manim shot’s measurement record, which names
its picture and contact sheet: [`an.build.derived`](an.build.derived.html.md#module-an.build.derived), an#299) — computed
by the render’s own setup and the engine’s own key code, rendering and
synthesising nothing.

What `an.build.gc` keeps (an#274). The dialogue is stamped the way the
render’s audio pipeline stamps it, from the content-keyed audio and viseme
stores only (`an.audio.pipeline.stamp_from_stores`): a `scene.md` edit
drops every stamp on re-sync, and the next render re-stamps the same audio
from the stores, so those are the keys it will use. A line the stores
cannot answer whose provider is free and repeatable (offline speech) is
re-made IN MEMORY, writing nothing (an#311): a later render re-makes the
same bytes. Any other (new text in a billed voice, a non-repeatable
provider) raises `an.audio.pipeline.AudioNotCachedError`: its shot’s next
key is unknowable without a paid or random synthesis, and a collector must
not guess.

* **Return type:**
  [`CacheReach`](#an.render.CacheReach)

### an.render.format_render_findings(project, output_name='main', , max_per_group=5)

`an render`’s summary of what the render found: one heading per kind
([`FINDING_GROUPS`](#an.render.FINDING_GROUPS)) with its count, then each finding’s IR path and
message — the message carries its fix — at most `max_per_group` per kind.
`info` findings are counted in the report, not listed. `[]` when the
render found nothing to warn about.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> recs = {"findings": [{"severity": "warning", "ir_path": "timeline/0/dialogue/1",
...     "description": "line 1 (bob) ends at 3.64s as synthesized, past the shot's "
...     "3.6s end. Lengthen the shot", "suggested_fix": None, "location": None,
...     "kind": "dialogue_fits"}]}
>>> import json
>>> print("\n".join(format_render_findings(
...     {"render_reports": {"main": json.dumps(recs)}})))
findings: 1 warning (all in artifacts/render_reports/main.json)
  dialogue that does not fit its shot (1):
    timeline/0/dialogue/1: line 1 (bob) ends at 3.64s as synthesized, past the shot's 3.6s end. Lengthen the shot
```

### an.render.live_runs(project_root)

Every cached render of this project still in progress, with the time it
started (its live marker’s mtime): what `an cache gc` must not race.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.render.portable_text(text, , root=None, home=None, tmp=None)

`text` with this machine’s absolute paths taken out: a path under the
project `root` becomes project-relative, the root itself `.`, a temp
folder `<tmp>` and the home directory `~` — so a render report (which a
project may commit or share, and an agent may pass on) names no user, host
folder or temp dir. Only WHOLE path components are replaced, at both ends
(an#309): a sibling that shares a prefix (`/u/me/proj2` beside
`/u/me/p`) or a path that merely ends like one (`/mnt/data/p` against
`/data/p`) is left as it is. A Windows path matches with either
separator and in any case.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> portable_text("missing at /u/me/p/assets/a.png; see /u/me/x.log",
...               root="/u/me/p", home="/u/me", tmp="/t")
'missing at assets/a.png; see ~/x.log'
>>> portable_text("rendered in /u/me/p", root="/u/me/p", home="/u/me", tmp="/t")
'rendered in .'
>>> portable_text("/u/me/proj2/a.png, /u/me2/x, /t/f.png, /mnt/u/me/p/b",
...               root="/u/me/p", home="/u/me", tmp="/t")
'~/proj2/a.png, /u/me2/x, <tmp>/f.png, /mnt/u/me/p/b'
>>> portable_text("c:/users/me/p/a.png", root=r"C:\Users\me\p", home=r"C:\Users\me", tmp="/t")
'a.png'
```

### an.render.render(project, , output_name='main', fps=None, resolution=None, auto_audio=True, tts=None, lipsync='offline', parallel=None, strict_assets=False, supersample=1, pix_fmt=None, capture=None, step_hz=None, language='en', incremental=False, force_render=False, echo_warnings=True)

Lower-level: render a loaded `Project` to mp4.

`incremental` is the build-cache seam (ADR 0004 decision 5): `True` is
the built-in [`ShotCache`](an.build.html.md#an.build.ShotCache) over `mall["shot_cache"]`, an
[`IncrementalEngine`](an.build.html.md#an.build.IncrementalEngine) is used as given, and `False` — the
default HERE, unlike [`render_project()`](#an.render.render_project) — renders every shot cold, as
this function always has. Cold is this layer’s default because its other
callers are measurements (the bench, the golden corpus, the demo builds),
whose wall times and lever rebinds a reused shot would silently void.
`force_render=True` with an engine renders every shot and re-records it.

`supersample` renders at N times the declared resolution and resolves back
with an exact N x N block mean, in the frame stage, before anything else
reads the frames. **Opt-in, and 1 costs nothing**: at 1 Chromium writes
straight to disk and no pixel is decoded.

**Measured on the shipped path, not on the render alone** — the distinction
matters, because the two differ by 1.6x. `single_character` forced to
1920x1080, 60 frames, this machine:

|   factor |   ms/frame | vs k=1    |
|----------|------------|-----------|
|        1 |      125.5 | 1.00x     |
|        2 |      508.6 | **4.05x** |

`misc/docs/wave3_research.md` §3b reports 2.54x for k=2; that is the
**render only**, measured with a patched runtime and no Python-side resolve,
and quoting it here would understate what a caller pays by 1.6x. The
difference is the decode + block mean + re-encode per frame.

**What it buys, and where it does not.** Research §3a renders each corpus
scene at rising k and lets `edge_transition_width` converge: k=2 travels 57%
to 112% of the way to that ceiling, and k=3 reaches it on every scene that
has one, at twice k=2’s cost. `promote_demo` — the descriptor path — is the
scene it helps most (-34.8% edge width, because the SVG sprite rasterises AT
2x instead of being stretched up from a 1x texture). `aa_probe` has no
ceiling at all: its diagonals land the block-mean grid differently at every
k, so it oscillates +/-5-8% with no settling.

**The corpus cannot inform the factor and must not be used to.** At 320x240
the same ladder reads 1.0x / 1.08x, because fixed costs dominate.

When `auto_audio` is True (the default) and any shot has dialogue,
the audio pipeline is run first so visemes + audio are available to
the renderer. Re-synthesis is triggered on provider changes (the
pipeline’s idempotency check compares against the current providers’
expected content hashes).

`strict_assets=True` refuses to draw a stand-in for a declared asset the
stores do not supply — the placeholder rig for a missing character
descriptor, the default backdrop for an unknown environment ref. Use it for
anything that measures pixels: a stand-in renders happily and is a
different picture (an#33).

**What the render learns, it reports** (an#254). Render is when a line’s
real length becomes known, so after synthesis the checks `an validate`
could only estimate run again on the timing the film will mux — the SAME
functions ([`an.ir.validate.post_synthesis_findings()`](an.ir.validate.html.md#an.ir.validate.post_synthesis_findings)): a line past its
shot’s end, a speaker overlapping themself, a line heard during a dissolve.
With them go the clock-owning renderers’ findings (an#279), the scene’s
library pins that disagree with `assets.lock.json`, and every warning
raised while the film was made — a stand-in or a recorded substitution, a
take whose audio is not the one recorded, a caption without word timings —
each addressed to its shot when its message names one. All of it is written
to `render_reports/<output_name>.json` (`kind` says which check),
readable as `Finding` s with [`render_findings()`](#an.render.render_findings);
[`format_render_findings()`](#an.render.format_render_findings) is `an render`’s grouped summary of it.
The warnings are still warned, after the render (`echo_warnings=False`:
only reported — what `an render` passes, since it prints the summary; a
render that fails echoes them anyway). What `strict_assets` refuses is
refused where it is found, before a frame is drawn; nothing here is fatal.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.render.render_findings(project, output_name='main')

The `Finding` s the last render of `output_name` reported (an#254),
from `render_reports/<output_name>.json`; `[]` before any render.

`project` is a project directory, a loaded `Project` or its mall.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### an.render.render_project(project_dir, , output_name='main', fps=None, resolution=None, tts=None, lipsync='offline', parallel=None, strict_assets=False, supersample=1, pix_fmt=None, capture=None, step_hz=None, language='en', incremental=True, force_render=False, echo_warnings=True)

Render every shot in `project_dir`’s scene and concatenate to one mp4.

**Incremental by default** (ADR 0004): a shot whose key — a digest of
everything its render reads, never its id — already has an entry in the
project’s shot cache is not rendered again; its cached mp4 is reused. So
editing one shot re-renders that shot, and an unchanged project re-renders
nothing. `force_render=True` renders every shot anyway (and refreshes
their entries); `incremental=False` neither reads nor writes the cache.
Pass your own engine (e.g. `ShotCache()`) to read what happened to each
shot afterwards from its `report` — the same summary is logged on the
`an.build` logger. See [`render()`](#an.render.render).

`tts` and `lipsync` may be provider name strings (`"offline"`,
`"elevenlabs"`, `"rhubarb"`) or provider instances. **\`\`tts\`\` defaults
to each voice’s own provider** (an#305): a line whose voice document
declares `provider: elevenlabs` is spoken by ElevenLabs — its cost
announced before the first request, a cached line never billed — and a
voice that declares none by the offline provider, so a project that
declares no provider needs no API key and renders exactly as before. A
`tts` given overrides every voice; a line spoken by another provider than
its voice declares (`--tts offline` for an ElevenLabs voice: silence) is a
finding, and refused under `strict_assets`. `lipsync` defaults to
offline. Switching providers triggers a re-synthesis on dialogue lines whose
stamped audio_ref / viseme_ref no longer match the current configuration.

`parallel` controls per-shot concurrency:

- `None` or `1` (default): render shots serially.
- `"auto"`: `min(n_shots, cpu_count(), DEFAULT_PARALLEL_CAP)`.
- integer ≥ 2: cap the thread pool at that size.

Each shot’s renderer runs in its own thread (the cutout backend
spawns a Chromium + http.server per shot, so threads release the
GIL during the slow parts).

`supersample` renders at N times the declared resolution and resolves back
with an exact block mean. **Opt-in, and 1 is free** — at 1 nothing is
decoded and Chromium’s own bytes reach disk. See [`render()`](#an.render.render).

`capture` picks how frames leave the browser: `"canvas"` (the default,
via `None`, since an#192) — an in-page read of the canvas, batched,
writing frames whose decoded pixels equal the screenshot path’s and
measured ~7.8x faster in the frame stage on the golden corpus, ~2.3x at
1080p (see `an.stage.canvas_capture`) — or `"screenshot"`, a
Playwright element screenshot per instant.

`step_hz` overrides the scene’s `meta.step_hz` for this render (a shot’s
own `step_hz` still wins): authored tweens are resampled onto a pose grid
of that many updates per second — 15 at 30 fps is “on twos”. `None` uses
the scene’s declaration, which is itself `None` (smooth) by default.

`language` (BCP-47) reaches lip-sync providers that select behaviour by
it when `lipsync` is a provider *name* — Rhubarb’s recognizer (an#96). A
provider *instance* carries its own.

A scene whose `library:` pins disagree with the project’s
`assets.lock.json` renders with a `LibraryPinWarning` per pin, and is
refused under `strict_assets` (`an.library.checkout.check_pins_before_render()`).

**What the render learned is reported** (an#254): see [`render()`](#an.render.render) — every
finding is in `render_reports/<output_name>.json`, read back as
`Finding` s by [`render_findings()`](#an.render.render_findings), and summarised by `an render`.

Returns the absolute path of the final output file (under `output/`).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
