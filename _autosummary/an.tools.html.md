# an.tools

User-facing utility functions, plus the SSOT list for CLI dispatch.

Each function here is meant to be callable from Python *and* from the shell
via `an <funcname>`. Keep their signatures dispatch-friendly: positional args
become required arguments, defaults become optional flags, and the docstring
becomes the command’s help. `an/__main__.py` projects this list onto typer
without touching these functions, so they stay plain Python.

### Functions

| [`bench`](#an.tools.bench)([scenes, out, keep_render, quiet, ...])    | Render the fixed bench corpus and write a metrics ledger.                            |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`bench_compare`](#an.tools.bench_compare)([before, after, mutation, ...])    | Compare two ledger rows — and refuse when they are not comparable.                   |
| [`bench_mutants`](#an.tools.bench_mutants)([names, quiet])                    | Break each guard on purpose and check the test that names it goes red.               |
| [`check`](#an.tools.check)()                                          | Print a status report of all backend system + Python deps.                           |
| [`credits`](#an.tools.credits)(project_dir[, json_out])                 | Show what third-party work is in `project_dir` and what it obliges.                  |
| [`init`](#an.tools.init)(project_dir[, name, force, id, genre, ...]) | Create a fresh an project at `project_dir` — or, with --id, at the default location. |
| [`iterate`](#an.tools.iterate)(project_dir, instruction[, ...])         | Apply a free-text instruction to the scene.                                          |
| [`preview`](#an.tools.preview)(project_dir[, shot, no_browser])         | Live-preview the project's scene in a browser; reloads on edit.                      |
| [`render`](#an.tools.render)(project_dir[, output_name, tts, ...])     | Render the project at `project_dir` to a single mp4.                                 |
| [`sync`](#an.tools.sync)(project_dir[, accept_measured])             | Reconcile scene.md and ir/scene.json inside `project_dir`.                           |
| [`validate`](#an.tools.validate)(project_dir)                            | Validate the scene at `project_dir`.                                                 |

### an.tools.bench(scenes='', out='', keep_render='', quiet=False, bless='', compare='', mutation='')

Render the fixed bench corpus and write a metrics ledger.

The instrument, not the verdict: it records numbers whose predicted
direction under each deliberate degradation is declared in advance, so a
future regression is caught by something other than someone noticing.

scenes: comma-separated corpus scene names (default: all of them)
out: ledger path (default: misc/bench/ledger/<date>-<sha>[-dirty].json)
keep_render: keep the throwaway render tree here instead of deleting it
quiet: print only the ledger path
bless: (re)write the golden frames, recording THIS STRING as the reason
compare: after the run, compare it against this baseline ledger row
mutation: pull one declared lever for this run, and ask –compare the

> per-mutation question instead of “is the second row worse”

Rendering knobs are deliberately NOT flags: a bench whose render knobs vary
per invocation produces incomparable rows, so they are a module constant
recorded verbatim into the ledger. `--mutation` is not one of them, and is
the exception that states the rule: a lever is the **independent variable**,
it is named in the report, it is exempted by declaration in
`MUTATION_TOUCHES` rather than by widening anything, and the row it
produces is never filed under a commit’s name. Without it the `--compare`
artifact is always the `mutation=None` path, which asks “is this worse” of
a run that was broken on purpose — the wrong question, answered
confidently.

`--bless` takes the reason as its value rather than pairing with a
separate `--reason`, so a bless with no recorded reason cannot be typed.
A re-bless with no recorded reason is the same failure as a silently
widened threshold, and it is the failure this wave exists to prevent — so
look at the PNG diff (GitHub renders 2-up, swipe and onion-skin) before
writing one.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.bench_compare(before='', after='', mutation='', strict=False, raw=False)

Compare two ledger rows — and refuse when they are not comparable.

before: baseline ledger row (default: the second-newest committed row)
after: the row to judge (default: the newest committed row)
mutation: evaluate the per-mutation predictions instead of asking whether

> the second row is worse. One of the mutations the rows declare.

strict: exit nonzero when the answer is bad — a regression without a
: mutation, or a direction that reverses on its own metric’s threshold
  grid (an#140: some cell of it got worse), an unmet criterion with one,
  a comparison that answered nothing, or a row that could not be read at
  all. For CI.

raw: print the report as JSON instead of the human digest

Refusing is the feature. Two rows measured on different scenes, at
different resolutions, or on different x264 builds are not “one better and
one worse” — every number in them is uninterpretable relative to the other,
and a number reported across incomparable rows is worse than none.

`-dirty` rows are excluded from the defaults: a row measured against
uncommitted edits describes no commit. Name one explicitly to compare it.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.bench_mutants(names='', quiet=False)

Break each guard on purpose and check the test that names it goes red.

names: comma-separated mutant names (default: every declared one)
quiet: print only the tally

“N mutants, all caught” is unfalsifiable after the fact when the mutations
lived in a scratch script. These are declared data, so the proof is
re-runnable — which matters because Wave 1 shipped three guards that stayed
green while the bug they guarded was present.

The WHOLE guard file runs for each mutant, never a `-k` filter: a filter that
happens to exclude the catching test reports “not caught” and sends you to
write a test that already exists. Takes about forty seconds.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.check()

Print a status report of all backend system + Python deps.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.credits(project_dir, json_out=None)

Show what third-party work is in `project_dir` and what it obliges.

project_dir: the an project
json_out: also write the machine-readable record to this path

A licence recorded and never displayed is not compliance, so this is the
consumer that makes the provenance field worth having.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.init(project_dir, name=None, force=False, id=False, genre='', package='', root='')

Create a fresh an project at `project_dir` — or, with –id, at the default location.

project_dir: where to create the project (created if missing); with –id, the project’s id instead (an init <id> –id; –id is a switch and takes no value)
name: project display name (defaults to the directory name)
force: overwrite an existing scene.md
id: a switch: read the positional as a project id, and create the project under its genre’s projects folder (an init alice-and-bob –id –genre cutout_animation -> ~/.local/share/cutan/projects/alice-and-bob)
genre: with –id, the genre the video is made in (e.g. cutout_animation); the genre names the package whose root holds the project
package: with –id, that package directly, overriding –genre (default: the genre’s, else an)
root: with –id, that package’s root (default: its data folder, or <PKG>_HOME)

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.iterate(project_dir, instruction, apply_changes=True, model='claude-opus-4-7')

Apply a free-text instruction to the scene. Needs ANTHROPIC_API_KEY.

project_dir: path to an an project
instruction: what to change in plain English (e.g. “make Maya’s laugh longer and warmer”)
apply_changes: persist the new scene to disk (default True); the next render

> re-renders exactly the shots whose content changed

model: Anthropic model id (default claude-opus-4-7)

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.preview(project_dir, shot='', no_browser=False)

Live-preview the project’s scene in a browser; reloads on edit.

Spins up a local HTTP server pointed at the runtime canvas. The
browser polls `scene.json` for changes and re-loads when you save
`scene.md`. Lossy: visuals only, no audio. Blocks until Ctrl-C.

project_dir: path to an an project (must contain scene.md / ir/scene.json)
shot: shot id to preview (default: first shot in the timeline)
no_browser: don’t auto-open the default browser

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.render(project_dir, output_name='main', tts='offline', lipsync='offline', parallel='', strict_assets=False, supersample=1, pix_fmt='', step_hz=0.0, language='en', capture='', force_render=False, no_cache=False, cache_frames=False)

Render the project at `project_dir` to a single mp4.

Incremental: a shot whose inputs (its compiled document, its art’s bytes,
its audio, the runtime, the render settings, this machine’s browser and
ffmpeg) are unchanged since a previous render is reused from the shot cache
rather than rendered again, and the summary line says which were which.

project_dir: path to an an project (must contain scene.md / ir/scene.json)
output_name: filename stem under output/ (default: “main”)
tts: TTS provider — “offline” (silent) or “elevenlabs” (needs ELEVEN_API_KEY)
lipsync: lip-sync provider — “offline” (deterministic), “rhubarb”

> (needs the rhubarb binary), or “whisper” (needs faster-whisper)

parallel: per-shot concurrency. “” or “1” = serial (default); “auto” =
: min(shots, cpu, 4); a number ≥ 2 caps the thread pool.

strict_assets: fail instead of drawing a stand-in (the placeholder rig, the
: default backdrop) for an asset the project’s stores don’t supply

supersample: render at N times the resolution and resolve back with an exact
: N x N block mean. Opt-in; 1 (the default) costs nothing at all. Measured
  on the shipped path at 1920x1080: 125.5 ms/frame at 1, 508.6 at 2 —
  4.05x, which is NOT the 2.54x the research reports for the render alone

pix_fmt: the delivered encode’s pixel format — “yuv420p” (default) or
: “yuv444p”. The ONE first-order quality lever in the encoder: 4:4:4 cuts
  the edge-band error 11.35 -> 3.79, where a mathematically lossless 4:2:0
  only reaches 10.15. It is opt-in for a PRODUCT reason and not an encoder
  one: High 4:4:4 Predictive is refused by many hardware decoders,
  browsers and platforms, so a 4:4:4 file is one some viewers cannot play

step_hz: stepped timing for authored tweens — pose updates per second, on a
: shot-wide grid (15 at 30 fps is “on twos”, 10 “on threes”). 0 (the
  default) uses the scene’s own `meta.step_hz`, which is unset (smooth)
  unless the author declared one. The camera, blinks, `play` clips and
  swap channels are never stepped by this

language: the dialogue’s language (BCP-47) for providers that select
: behaviour by it — Rhubarb’s recognizer today: English (the default)
  uses `pocketSphinx` with the transcript, anything else `phonetic`
  without one (an#96)

capture: how frames leave the browser — “canvas” (the default), an in-page
: read of the canvas in batches, ~7.8x faster frame stage on the corpus,
  ~2.3x at 1080p; or “screenshot”, a Playwright element screenshot per
  instant. Both write frames with the same decoded pixels

force_render: render every shot even when the shot cache holds it (and
: refresh its entry)

no_cache: neither read nor write the shot cache — every shot is rendered
: cold, as before the cache existed

cache_frames: no longer needed, and no effect on `an render` (an#260): a
: film with transitions or a sound layer now reuses its shots by default,
  caching only the frames at each transition. Kept so scripts that pass
  it still run

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.sync(project_dir, accept_measured=False)

Reconcile scene.md and ir/scene.json inside `project_dir`.

`--accept-measured` also writes the durations a clock-owning renderer
(Manim) MEASURED into the scene — each such shot’s `duration:` line,
patched in place, so the prose around it is kept. Without it, a measured
duration lives only in the derived `measurements` store and the scene
says what its author wrote.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.tools.validate(project_dir)

Validate the scene at `project_dir`. Prints findings, exit 0 on pass.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
