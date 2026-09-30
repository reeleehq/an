# an.adapters.cutout.render

Headless cutout rendering: Playwright drives the JS runtime, ffmpeg muxes.

The flow per shot:

1. Compile the shot to a `CutoutSceneJSON` via `compile_shot`.
2. Stage a copy of the JS runtime in a per-shot work directory and write the
   JSON beside it.
3. Launch headless Chromium via Playwright; load `index.html`; inject the
   scene via `window.anLoadScene`.
4. For each frame `f` in `[0, total_frames)`: seek `f/fps` and capture the
   canvas to a PNG — by default (`capture="canvas"`, since an#192) reading its
   own pixels in-page, in batches (`an.adapters.cutout.canvas_capture`); with
   `capture="screenshot"`, `window.anSetTime` plus a Playwright element
   screenshot per instant.
5. Mux the PNG sequence to mp4 with ffmpeg.

Failures are reported with concrete remediation: missing ffmpeg, missing
Chromium, runtime load timeout, etc. Subprocess errors are wrapped at the
facade boundary.

### Module Attributes

| [`DEFAULT_ASSET_LOAD_TIMEOUT_MS`](#an.adapters.cutout.render.DEFAULT_ASSET_LOAD_TIMEOUT_MS)   | Deadline for `anLoadScene`, which awaits `PIXI.Assets.load` for every declared texture.                                                                                                                                                                                              |
|----------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DETERMINISTIC_CHROMIUM_ARGS`](#an.adapters.cutout.render.DETERMINISTIC_CHROMIUM_ARGS)     | Chromium launch flags that pin the rasteriser (an#31, research §2).                                                                                                                                                                                                                  |
| [`DEFAULT_PIX_FMT`](#an.adapters.cutout.render.DEFAULT_PIX_FMT)                 | x264 encode knobs pinned so the delivered mp4 is a function of the frames rather than of the machine (an#34, research §2).                                                                                                                                                           |
| [`SUPPORTED_PIX_FMTS`](#an.adapters.cutout.render.SUPPORTED_PIX_FMTS)              | a typo would reach ffmpeg as an obscure failure minutes into a render, and a format outside this set has not been measured against the panel.                                                                                                                                        |
| [`DEFAULT_CAPTURE`](#an.adapters.cutout.render.DEFAULT_CAPTURE)                 | the runtime's `anCaptureFrames` reads the canvas in-page and hands back PNG data URLs in batches (`an.adapters.cutout.canvas_capture`), which writes frames whose DECODED pixels equal the screenshot path's — ~7.8x faster in the frame stage on the golden corpus, ~2.3x at 1080p. |
| [`SUPPORTED_CAPTURES`](#an.adapters.cutout.render.SUPPORTED_CAPTURES)              | a typo must fail before a browser launches, not minutes into a render.                                                                                                                                                                                                               |
| [`DEFAULT_CANVAS_BATCH`](#an.adapters.cutout.render.DEFAULT_CANVAS_BATCH)            | Frames per `anCaptureFrames` round trip.                                                                                                                                                                                                                                             |
| [`DEFAULT_CANVAS_ENCODE_WORKERS`](#an.adapters.cutout.render.DEFAULT_CANVAS_ENCODE_WORKERS)   | Threads decoding, resolving and re-encoding canvas frames while the page renders the next batch.                                                                                                                                                                                     |
| [`DEFAULT_CANVAS_BATCH_PIXELS`](#an.adapters.cutout.render.DEFAULT_CANVAS_BATCH_PIXELS)     | The same two bounds in CAPTURED PIXELS (backbuffer pixels, so a supersample counts k² times and an open shutter once per instant): at most this many per `anCaptureFrames` round trip, and twice this many waiting on the encode pool.                                               |
| [`DEFAULT_CANVAS_MAX_INFLIGHT`](#an.adapters.cutout.render.DEFAULT_CANVAS_MAX_INFLIGHT)     | frames handed to the encode pool and not yet written.                                                                                                                                                                                                                                |
| [`ASSET_LOAD_TIMEOUT_MARKER`](#an.adapters.cutout.render.ASSET_LOAD_TIMEOUT_MARKER)       | Sentinel the in-page deadline rejects with, so the Python side can tell a timeout apart from a load failure and say something different about each.                                                                                                                                  |
| [`ASSET_SRC_PREFIX_TO_STORE`](#an.adapters.cutout.render.ASSET_SRC_PREFIX_TO_STORE)       | Texture `src` prefix → the mall store that resolves the rest of the path.                                                                                                                                                                                                            |

### Functions

| [`effective_step_hz`](#an.adapters.cutout.render.effective_step_hz)(shot, ctx)   | The stepped-timing policy a shot renders under (an#89): the shot's own `step_hz` when it declares one, else the scene's (`ctx.step_hz`), else `None` — smooth.   |
|---------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### Classes

| [`CutoutRenderer`](#an.adapters.cutout.render.CutoutRenderer)()   | Headless cutout renderer: Playwright + ffmpeg.   |
|---------------------------------------------------------------------|--------------------------------------------------|

### Exceptions

| [`CutoutAssetWarning`](#an.adapters.cutout.render.CutoutAssetWarning)   | A declared texture could not be staged into the runtime directory.   |
|-----------------------------------------------------------------------|----------------------------------------------------------------------|
| [`CutoutRenderError`](#an.adapters.cutout.render.CutoutRenderError)    | Raised when a cutout render fails.                                   |

### an.adapters.cutout.render.ASSET_LOAD_TIMEOUT_MARKER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an:asset-load-timeout'*

Sentinel the in-page deadline rejects with, so the Python side can tell a
timeout apart from a load failure and say something different about each.

### an.adapters.cutout.render.ASSET_SRC_PREFIX_TO_STORE *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'characters/': 'characters', 'environments/': 'environments', 'props/': 'props', 'styles/': 'styles'}*

Texture `src` prefix → the mall store that resolves the rest of the path.

A `src` reads `<prefix>/<ref>/parts/head.svg` and resolves to
`mall[store]._root/<ref>/parts/head.svg`. Only `characters/` is emitted
by the compiler today; the others are here because environments, styles and
props all route through this same staging step as they land, and the
previous hardcoded `characters/` test silently dropped everything else.

The prefix IS the store name plus a slash for all four, which is not an
accident worth relying on: the map is the contract, and a fifth kind whose
store is named differently must still work.

### *exception* an.adapters.cutout.render.CutoutAssetWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A declared texture could not be staged into the runtime directory.

Deliberately a warning and not an error, for now: an art package that is
still being assembled is a real state, and refusing to render it would be
worse than rendering it incompletely. But it must be *audible* — the
consequence of an un-staged texture is worse than it looks and worse than
this docstring used to claim. Measured (`misc/docs/wave4_research.md` §4):
an *absent* part file crashes the render with an unwrapped minified-PixiJS
`TypeError`; a degenerate SVG hangs it indefinitely (#79); a geometry-less
part renders invisibly. `PIXI.Texture.WHITE` — the actual white rectangle —
is reached only by a zero-byte file, an empty `src`, or no `src` key.
Either way a silent skip surfaces to the user as “the animation is broken”
rather than as an error, which is what this warning exists to prevent.

### *exception* an.adapters.cutout.render.CutoutRenderError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when a cutout render fails. Carries actionable detail.

### *class* an.adapters.cutout.render.CutoutRenderer

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Headless cutout renderer: Playwright + ffmpeg.

```pycon
>>> r = CutoutRenderer()
>>> r.name
'cutout'
>>> r.supported_renderers
('cutout',)
```

#### render(shot, ctx)

Render `shot` to mp4 using `ctx` for paths + parameters.

* **Return type:**
  [`RenderResult`](an.adapters.html.md#an.adapters.RenderResult)

### an.adapters.cutout.render.DEFAULT_ASSET_LOAD_TIMEOUT_MS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 60000*

Deadline for `anLoadScene`, which awaits `PIXI.Assets.load` for every declared
texture. **A bound is required, not merely nice**: a degenerate part SVG —
`<svg/>`, malformed XML, a zero-dimension root — makes `Assets.load` never
settle, so without this the render hangs indefinitely with no error and no
output (an#79). `page.evaluate` is not subject to Playwright’s default
timeout, so the deadline is imposed inside the page instead.

The value is a policy choice, not a measurement: it needs to sit far above a
legitimate cold load of a few dozen small SVGs and far below “a human gave
up”. Raise it for a genuinely heavy art package rather than removing it.

### an.adapters.cutout.render.DEFAULT_CANVAS_BATCH *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 8*

Frames per `anCaptureFrames` round trip. Measured at 1920x1080 on an M1
Max, `single_character`: 67 ms/frame one frame per call, 46 at four, 46 at
eight — the round trip is ~20 ms of fixed cost, amortised by the batch. It is
also the memory the page holds before Python takes it: eight data URLs of a
1080p frame are well under a megabyte of text, and at a supersampled 4K
backbuffer a few megabytes each.

### an.adapters.cutout.render.DEFAULT_CANVAS_BATCH_PIXELS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 4147200*

The same two bounds in CAPTURED PIXELS (backbuffer pixels, so a supersample
counts k² times and an open shutter once per instant): at most this many per
`anCaptureFrames` round trip, and twice this many waiting on the encode
pool. Two 1080p instants: small scenes still batch by the frame count
above, and at 1080p the batch size stopped mattering for a flat scene
(96 frames: 4.7 s at 2, 4 or 8 per round trip) while it decides everything
for an incompressible one (a grain pack, 48 frames: 11.0 s / 0.38 GB at 2
against 17.8 s / 2.1 GB at 8; the screenshot path 17.8 s / 0.16 GB). Needed
because a count alone does not bound the bytes: the review of an#192
measured grain at supersample 2 with an 8-sample shutter overflowing the
driver’s string limit in ONE reply (the render hung in `browser.close()`),
and ~16 GB of Python memory at supersample 3. A frame whose instants alone
exceed it is captured over several round trips.

### an.adapters.cutout.render.DEFAULT_CANVAS_ENCODE_WORKERS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

Threads decoding, resolving and re-encoding canvas frames while the page
renders the next batch. The decode/encode is ~60 ms/frame of Pillow and zlib
at 1080p — the same order as the page’s own work — so it must overlap it or
it eats the win. Two, not `cpu_count()`: `an render --parallel` already runs
one Chromium per shot, and each of them is another source of CPU pressure.

### an.adapters.cutout.render.DEFAULT_CANVAS_MAX_INFLIGHT *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 16*

frames handed to the encode pool and not yet written. When
the pool falls behind, the capture loop blocks on the oldest one before it
asks the page for more, so memory is bounded by this many frames plus one
batch however long the shot is.

* **Type:**
  BACK-PRESSURE

### an.adapters.cutout.render.DEFAULT_CAPTURE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'canvas'*

the
runtime’s `anCaptureFrames` reads the canvas in-page and hands back PNG data
URLs in batches (`an.adapters.cutout.canvas_capture`), which writes frames
whose DECODED pixels equal the screenshot path’s — ~7.8x faster in the frame
stage on the golden corpus, ~2.3x at 1080p. `"screenshot"`: a Playwright
element screenshot of `#stage` per instant, the path every render took
before; still available (`an render --capture screenshot`).

Flipped only after the equivalence gate (`tests/test_canvas_capture_equivalence.py`)
held on the whole golden corpus on a developer machine AND the labelled Linux
rendering lane (an#189, re-run on an#192): a faster path that moved a pixel
would silently invalidate every baseline recorded before it. Read as a MODULE
GLOBAL at call time, for `DEFAULT_PIX_FMT`’s reason — a default argument
would bind it at def time.

* **Type:**
  How frames leave the browser. `"canvas"` (the default since an#192)

### an.adapters.cutout.render.DEFAULT_PIX_FMT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'yuv420p'*

x264 encode knobs pinned so the delivered mp4 is a function of the frames
rather than of the machine (an#34, research §2).

`-threads 1` — `-threads 1/4/11` all give bit-identical decoded pixels, so
this looks unnecessary on a laptop. It is not: `auto` raises
`lookahead_threads` above 1 at roughly `-threads >= 12`, and a forced
`lookahead-threads=4` changes 86.2% of the bytes (max delta 80). A big CI
runner crosses that line and a 4-core dev box never will, which is precisely
how an unpinned thread count ships without anyone seeing it.

`-crf 23 -preset medium` — both are libx264’s compiled-in defaults today, so
passing them changes nothing now and pins us against a build whose defaults
differ. Worth pinning because preset swings distinct colour counts \*\*2.3x,
non-monotonically\*\* (ultrafast 3141, veryfast 7296, medium 6064, slower 5393)
against a crf18->23 signal of 1.35x — an unpinned preset dominates the very
signal a quality ledger tries to measure.

BT.709 is the one knob here that CHANGES today’s output, and it changes more
than the research predicted — measured, not assumed (an#34):

- `-colorspace bt709` does not merely *tag* the file. It sets the matrix of
  the auto-inserted RGB->YUV conversion, so the \*\*encoded luma and chroma
  planes themselves change\*\*. Confirmed by construction: forcing
  `scale=out_color_matrix=bt601` reproduces the untagged output’s decoded
  stream byte-for-byte, i.e. `an` has been converting with BT.601 all along.
  **On ffmpeg 8/9. It is false on ffmpeg 6.1** — where the same flags reach
  only the VUI and the planes stay BT.601 (an#148, measured; see
  `an.base.BT709_SCALE_FILTER` for the numbers). That is why the mux now
  states the conversion explicitly with `-vf` instead of inferring it from
  these flags, which stay for the tag they land.
- `-color_range tv` is a **no-op today** (limited range is already the
  default for yuv420p here). Pinned anyway, so a build that defaults
  differently cannot change the output silently.
- The ffmpeg-level `-color_primaries` / `-color_trc` flags \*\*do not reach the
  bitstream\*\*: with them alone, ffprobe reports `color_space=bt709` and
  `color_primaries=unknown`, `color_transfer=unknown`. `-x264-params` is what
  lands all three in the VUI, and it leaves the decoded stream identical. A
  half-tagged file is worse than an untagged one — the player stops guessing
  the matrix but still guesses the primaries.

Why bother: untagged, the *player* picks its matrix by a height heuristic
(BT.601 below ~576 lines). Every shipped `an` example is 320x240 to 640x360,
so encode and playback agree by luck; at 1080p the same code would encode
with BT.601 and be displayed as BT.709, a silent, resolution-dependent colour
error. Pinning both sides to BT.709 makes them agree at every resolution.
This is a **one-time deliberate re-baseline** of every mp4 — cheap now,
because no ledger exists yet to invalidate.
The delivered encode’s pixel format, and \*\*the one first-order quality lever
in this file\*\*. Measured on 30 real 1080p `an` frames, edge-band mean error:
current flags 11.35, crf18 4:2:0 11.05, crf18 `-tune animation` 10.96,
mathematically lossless 4:2:0 **10.15** — and crf18 **4:4:4 3.79**.
Losslessness buys 8%; dropping chroma subsampling buys **66%**. Wave 2’s own
conclusion: “bitrate is second-order, pixel format is first-order”.

\*\*The default stays 4:2:0 because that is a PRODUCT constraint, not an
encoder-tuning one.\*\* High 4:4:4 Predictive is refused by many hardware
decoders, browsers and platforms, so flipping it would hand a design partner
a file they cannot play. 4:4:4 is reachable per render
(`an render --pix-fmt yuv444p`), which is the right shape for a knob whose
right answer depends on where the file is going.

Read as a MODULE GLOBAL at call time, deliberately: that is what lets the
bench’s lever rebind it from outside, exactly as `high_crf` rebinds
`DETERMINISTIC_X264_ARGS`. Hoisting either into a default argument binds it
at `def` time and disarms the lever silently.

### an.adapters.cutout.render.DETERMINISTIC_CHROMIUM_ARGS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('--no-sandbox', '--disable-gpu', '--enable-unsafe-swiftshader', '--force-color-profile=srgb')*

Chromium launch flags that pin the rasteriser (an#31, research §2).

**Unconditional, deliberately** — not gated behind an env var. A render whose
rasteriser depends on `AN_DETERMINISTIC` is non-reproducible *by default*,
which is the property this work exists to remove; and the flags are a
measured no-op on today’s output (0 differing pixels over both fixtures,
verified on this repo at the commit that introduced them), so there is no
baseline to protect by making them opt-in.

Unpinned, the same code renders differently in ways nobody would attribute
correctly: GPU vs software rasterisation is a 1.9% / max-57 pixel difference,
and a headed browser (reachable by a one-word local edit) differs by 1.91%.
A band that wide hides any real regression.

Two flags are deliberately NOT here. `--use-angle=swiftshader` — including
Chromium’s own documented `--use-gl=angle --use-angle=swiftshader` form —
moves 1.55% of pixels by up to 58/255, so it would re-baseline the corpus for
nothing. `--disable-frame-rate-limit` measured 1.05x on this WebGL runtime
(the widely-cited 2.3x is a canvas-2D artefact). `--deterministic-mode` is a
verified no-op here, because the runtime uses `autoStart:false` plus an
explicit `app.render()`.

Record the argv **verbatim** in any provenance row: all four rasteriser
configurations report the byte-identical `UNMASKED_RENDERER_WEBGL` string,
so the renderer string cannot witness this choice.

### an.adapters.cutout.render.SUPPORTED_CAPTURES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('screenshot', 'canvas')*

a typo must
fail before a browser launches, not minutes into a render.

* **Type:**
  The capture paths `_check_capture` accepts. Not an open string

### an.adapters.cutout.render.SUPPORTED_PIX_FMTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('yuv420p', 'yuv444p')*

a typo would reach ffmpeg
as an obscure failure minutes into a render, and a format outside this set
has not been measured against the panel.

* **Type:**
  The formats the knob accepts. Not an open string

### an.adapters.cutout.render.effective_step_hz(shot, ctx)

The stepped-timing policy a shot renders under (an#89): the shot’s own
`step_hz` when it declares one, else the scene’s (`ctx.step_hz`), else
`None` — smooth. The compiler stamps whatever this returns.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> from pathlib import Path
>>> ctx = RenderContext(mall={}, work_dir=Path("."), step_hz=15.0)
>>> effective_step_hz(Shot(id="s"), ctx)
15.0
>>> effective_step_hz(Shot(id="s", step_hz=10.0), ctx)
10.0
>>> effective_step_hz(Shot(id="s"), RenderContext(mall={}, work_dir=Path("."))) is None
True
```
