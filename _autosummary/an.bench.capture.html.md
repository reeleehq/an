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

### Module Attributes

| [`IGNORED_ON_COPY`](#an.bench.capture.IGNORED_ON_COPY)          | they are the previous render's output, and one of them silently extends this one's frame sequence.   |
|---------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| [`IGNORED_RELPATHS_ON_COPY`](#an.bench.capture.IGNORED_RELPATHS_ON_COPY) | Excluded by their path **relative to the project root**, POSIX-spelled.                              |
| [`RENDER_WORK_RELPATH`](#an.bench.capture.RENDER_WORK_RELPATH)      | Where the renderer leaves its per-shot working tree inside the project.                              |
| [`FRAME_PNG_GLOB`](#an.bench.capture.FRAME_PNG_GLOB)           | How a shot's frames are named on disk.                                                               |

### Functions

| [`capture_fixture`](#an.bench.capture.capture_fixture)(name, fixture, \*, repo_root)   | Render `fixture` in a throwaway copy and return its artifacts.             |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`cleanup`](#an.bench.capture.cleanup)(capture)                                | Remove a capture's throwaway tree.                                         |
| [`dirty_paths`](#an.bench.capture.dirty_paths)(repo_root)                          | `git status --porcelain` lines, so a capture can prove it touched nothing. |
| [`distinct_png_sizes`](#an.bench.capture.distinct_png_sizes)(frames_dir)                  | Every distinct `(width, height)` among a shot's frame PNGs, sorted.        |
| [`expected_frame_count`](#an.bench.capture.expected_frame_count)(duration, fps)             | The renderer's own frame-count expression, reused rather than restated.    |
| [`stage_copy`](#an.bench.capture.stage_copy)(fixture_dir, base)                   | Copy a fixture into `base`, leaving the previous render behind.            |

### Classes

| [`SceneCapture`](#an.bench.capture.SceneCapture)(name, source, prepared, ...[, ...])   | One fixture's whole render.    |
|-----------------------------------------------------------------------------------------------------|--------------------------------|
| [`ShotCapture`](#an.bench.capture.ShotCapture)(shot_id, frames_dir, scene_json, ...)  | One rendered shot's artifacts. |

### Exceptions

| [`CaptureError`](#an.bench.capture.CaptureError)         | A capture could not produce something the metrics need.           |
|-----------------------------------------------------------------------|-------------------------------------------------------------------|
| [`GitStatusUnavailable`](#an.bench.capture.GitStatusUnavailable) | `git status` did not answer, so "the tree is clean" is not known. |

### *exception* an.bench.capture.CaptureError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A capture could not produce something the metrics need.

### an.bench.capture.FRAME_PNG_GLOB *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'frame_\*.png'*

How a shot’s frames are named on disk. One constant rather than the literal
repeated at each glob site.

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

### an.bench.capture.IGNORED_ON_COPY *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('.an', 'output', '.anima')*

they are the previous render’s
output, and one of them silently extends this one’s frame sequence.
Matched on the **basename**, at any depth — that is exactly what
`shutil.ignore_patterns` does, and it is why `artifacts/shots` cannot be
spelled here. See [`IGNORED_RELPATHS_ON_COPY`](#an.bench.capture.IGNORED_RELPATHS_ON_COPY).

* **Type:**
  Copied for the render, but never these

### an.bench.capture.IGNORED_RELPATHS_ON_COPY *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('artifacts/shots',)*

Excluded by their path **relative to the project root**, POSIX-spelled.
`mall["shots"]` is `<project>/artifacts/shots`, and `artifacts/`
itself is kept on purpose — it holds the audio cache, whose warm/cold state
this module records rather than destroys.

Neither spelling belongs in [`IGNORED_ON_COPY`](#an.bench.capture.IGNORED_ON_COPY), and \*\*both fail
silently\*\*. `shutil.ignore_patterns` returns a closure handed the NAMES
inside one directory, which it `fnmatch.filter``s — so ``"artifacts/shots"`
can never match anything (no name contains a separator) and a bare
`"shots"` would delete every directory of that name **anywhere** in the
tree, a character rig’s included.

### an.bench.capture.RENDER_WORK_RELPATH *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '.an/render_work'*

Where the renderer leaves its per-shot working tree inside the project.

### *class* an.bench.capture.SceneCapture(name, source, prepared, project_dir, mp4, shots, resolution, fps, duration, n_declared_entity_refs, visual_kinds, asset_resolution, audio_cache, wall_seconds, determinism=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One fixture’s whole render.

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
[`an.bench.run`](an.bench.run.html.md#module-an.bench.run) is where the *bench’s* invariant is asserted.

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

### an.bench.capture.stage_copy(fixture_dir, base)

Copy a fixture into `base`, leaving the previous render behind.

Split out of [`capture_fixture()`](#an.bench.capture.capture_fixture) so the exclusion is testable without
rendering anything — which matters, because the failure it prevents is
silent. `frames/` is never cleared and ffmpeg’s image2 demuxer reads the
contiguous `frame_%06d.png` run from 0, so a longer previous render is
appended to this one’s source leg and to nothing else.

Two kinds of exclusion, because one kind cannot say both things:
[`IGNORED_ON_COPY`](#an.bench.capture.IGNORED_ON_COPY) by basename at any depth, and
[`IGNORED_RELPATHS_ON_COPY`](#an.bench.capture.IGNORED_RELPATHS_ON_COPY) by path from the project root — which is
the only way to drop `artifacts/shots` while keeping `artifacts/audio`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
