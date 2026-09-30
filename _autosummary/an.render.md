# an.render

Project-level rendering: per-shot mp4 → final composited mp4 via ffmpeg concat.

The orchestrator picks a renderer per shot from the registry (matched on
`shot.renderer`) and renders each shot in isolation, then concatenates the
per-shot outputs into one final mp4 written to `project.mall["output"]`.

Phase 2D ships the cutout path; later phases register Manim / Remotion / etc.
adapters and the same flow handles them.

### Functions

| [`render`](#an.render.render)(project, \*[, output_name, fps, ...])   | Lower-level: render a loaded `Project` to mp4.                         |
|-------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`render_project`](#an.render.render_project)(project_dir, \*[, ...])         | Render every shot in `project_dir`'s scene and concatenate to one mp4. |

### Exceptions

| [`RenderError`](#an.render.RenderError)   | Raised on render-pipeline failures with actionable detail.   |
|----------------------------------------------------------------|--------------------------------------------------------------|

### *exception* an.render.RenderError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised on render-pipeline failures with actionable detail.

### an.render.render(project, , output_name='main', fps=None, resolution=None, auto_audio=True, tts='offline', lipsync='offline', parallel=None, strict_assets=False, supersample=1, pix_fmt=None, capture=None, step_hz=None, language='en')

Lower-level: render a loaded `Project` to mp4.

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

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.render.render_project(project_dir, , output_name='main', fps=None, resolution=None, tts='offline', lipsync='offline', parallel=None, strict_assets=False, supersample=1, pix_fmt=None, capture=None, step_hz=None, language='en')

Render every shot in `project_dir`’s scene and concatenate to one mp4.

`tts` and `lipsync` may be provider name strings (`"offline"`,
`"elevenlabs"`, `"rhubarb"`) or provider instances. Defaults are
offline so no API keys are required. Switching providers triggers a
re-synthesis on dialogue lines whose stamped audio_ref / viseme_ref
no longer match the current configuration.

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

`capture` picks how frames leave the browser: `"screenshot"` (the
default, via `None`) or `"canvas"` — an in-page read of the canvas,
batched, writing frames whose decoded pixels equal the screenshot path’s
and measured ~7.8x faster in the frame stage on the golden corpus, ~2.3x at 1080p (see
`an.adapters.cutout.canvas_capture`). Opt-in until the equivalence gate has
held on both rendering lanes.

`step_hz` overrides the scene’s `meta.step_hz` for this render (a shot’s
own `step_hz` still wins): authored tweens are resampled onto a pose grid
of that many updates per second — 15 at 30 fps is “on twos”. `None` uses
the scene’s declaration, which is itself `None` (smooth) by default.

`language` (BCP-47) reaches lip-sync providers that select behaviour by
it when `lipsync` is a provider *name* — Rhubarb’s recognizer (an#96). A
provider *instance* carries its own.

Returns the absolute path of the final output file (under `output/`).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
