# an.bench.capture

Render one corpus fixture into a throwaway copy, and hand back its artifacts.

Two things this module exists to get right, both of which produce plausible
numbers when got wrong:

**Render into a copy.** The render path mutates the project directory — scene
mtimes, the decisions log, `.an/render_work` — so rendering in place makes
the git sha in the ledger filename a lie about the tree that produced the row.

**Do not inherit a stale render.** `shutil.copytree` of a developer’s
checkout would carry `.an/render_work` and `output/` across, `frames/` is
never cleared, and ffmpeg’s image2 demuxer reads the contiguous
`frame_%06d.png` run from 0 — so a longer previous render is silently
appended to this one. Every encode-side metric pairs source frame *i* with
decoded frame *i*, so that appends garbage to one leg and shifts nothing on the
other. `artifacts/` is deliberately kept *except for one subdirectory*: it
holds the audio cache, whose warm/cold state is recorded rather than destroyed
— but `artifacts/shots` is `mall["shots"]`, the previous render’s per-shot
mp4s, and this module’s whole promise is that nothing of a previous render
crosses. It is gitignored, so it does not reproduce on a clean checkout: a
per-developer landmine, in the module whose docstring says the opposite.

### Functions

| [`capture_fixture`](#an.bench.capture.capture_fixture)(name, fixture, \*, repo_root)   | Render `fixture` in a throwaway copy and return its artifacts.             |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`cleanup`](#an.bench.capture.cleanup)(capture)                                | Remove a capture's throwaway tree.                                         |
| [`dirty_paths`](#an.bench.capture.dirty_paths)(repo_root)                          | `git status --porcelain` lines, so a capture can prove it touched nothing. |
| [`distinct_png_sizes`](#an.bench.capture.distinct_png_sizes)(frames_dir)                  | Every distinct `(width, height)` among a shot's frame PNGs, sorted.        |
| [`expected_frame_count`](#an.bench.capture.expected_frame_count)(duration, fps)             | The renderer's own frame-count expression, reused rather than restated.    |

### Classes

| [`SceneCapture`](#an.bench.capture.SceneCapture)(name, source, prepared, ...[, ...])   | One fixture's whole render.    |
|-----------------------------------------------------------------------------------------------------|--------------------------------|
| [`ShotCapture`](#an.bench.capture.ShotCapture)(shot_id, frames_dir, scene_json, ...)  | One rendered shot's artifacts. |

### Exceptions

| [`GitStatusUnavailable`](#an.bench.capture.GitStatusUnavailable)   | `git status` did not answer, so "the tree is clean" is not known.   |
|-------------------------------------------------------------------------|---------------------------------------------------------------------|

### *exception* an.bench.capture.GitStatusUnavailable

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

`git status` did not answer, so “the tree is clean” is not known.

Separated from an empty result on purpose. `git status` failing prints
nothing to stdout, so `check=False` turned every failure into “no dirty
paths” — indistinguishable from a clean tree, and *silently* so. Measured:
a concurrent `git` in a linked worktree of this repo takes `index.lock`,
`git status` exits nonzero with empty stdout, and
`test_a_capture_leaves_the_repository_untouched` fails with `[] != [...]`
— an assertion about the capture, pointing at nothing, in a run that has
been green fifty times. A check that could not run is not evidence that
nothing is wrong.

### *class* an.bench.capture.SceneCapture(name, source, prepared, project_dir, mp4, shots, resolution, fps, duration, n_declared_entity_refs, visual_kinds, asset_resolution, audio_cache, wall_seconds, determinism=<factory>, capture='', film=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One fixture’s whole render.

#### capture *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

How the frames left the browser (`"screenshot"` / `"canvas"`),
resolved the way the render resolves it. The decoded pixels are the same
either way, so no metric moves — but `wall_seconds` does, several-fold,
and a timing row is only readable beside the path that produced it
(an#192 flipped the default).

#### film *: [ShotCapture](#an.bench.capture.ShotCapture) | [None](https://docs.python.org/3/builtins/constants.html#None)*

An ASSEMBLED scene’s composed frames (transitions, a sound layer —
`an.assemble`), as one segment: what the delivered mp4 shows. `None`
for a scene that is the concatenation of its shots, which is every scene
before an#279’s core corpus. When set, every metric, the golden frames
and the frame count read IT — pairing the shots’ frames against a film
whose dissolves overlap them would measure the overlap, not the encoder.

#### *property* frame_segments *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[ShotCapture](#an.bench.capture.ShotCapture)]*

The frame sequence(s) the delivered mp4 shows, in order.

### *class* an.bench.capture.ShotCapture(shot_id, frames_dir, scene_json, runtime_dir, frame_count, duration=0.0, frame_sizes=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One rendered shot’s artifacts.

#### duration *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The shot’s declared duration, from the IR rather than from the staged
scene, so the expected frame count is derived from the same number the
renderer used.

#### frame_sizes *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)], ...]*

The distinct pixel sizes actually on disk, from each PNG’s IHDR. The
independent half of a pair whose other half — `SceneCapture.resolution`
— comes from the staged scene’s `meta` and never from a file. Empty
only when the shot wrote no frames.

### an.bench.capture.capture_fixture(name, fixture, , repo_root, keep_render=None)

Render `fixture` in a throwaway copy and return its artifacts.

The copy lives until the caller is done with it — the metrics read the
frames — so this is a context-free function that leaves the tree in place
and hands back the path. `captured()` is the scoped form.

* **Return type:**
  [`SceneCapture`](#an.bench.capture.SceneCapture)

### an.bench.capture.cleanup(capture)

Remove a capture’s throwaway tree.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.bench.capture.dirty_paths(repo_root)

`git status --porcelain` lines, so a capture can prove it touched nothing.

Raises [`GitStatusUnavailable`](#an.bench.capture.GitStatusUnavailable) when git does not answer, rather than
reporting a clean tree it never observed.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.bench.capture.distinct_png_sizes(frames_dir)

Every distinct `(width, height)` among a shot’s frame PNGs, sorted.

Read from each file’s IHDR — 24 bytes per frame — so reading all of them
costs nothing and catches what sampling one would miss: a sequence whose
size changes partway through, which is what a half-applied supersample
produces.

**Recorded here, enforced elsewhere.** Rendering a fixture at a size the
scene does not declare is a legitimate thing to do —
`misc/bench/wave3_ab.py` patches `runtime.js` to `resolution: k,
autoDensity: false` and drives [`capture_fixture()`](#an.bench.capture.capture_fixture) directly to measure
the supersample — so this module reports what it saw and
[`an.bench.run`](an.bench.run.md#module-an.bench.run) is where the *bench’s* invariant is asserted.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)], [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.bench.capture.expected_frame_count(duration, fps)

The renderer’s own frame-count expression, reused rather than restated.

`max(1, int(round(duration * fps)))` — and Python 3’s `round` is
banker’s rounding, so `math.ceil` or `int(x + 0.5)` silently disagrees
on every half-frame duration.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> expected_frame_count(2.5, 24)
60
>>> expected_frame_count(0.0, 24)
1
```
