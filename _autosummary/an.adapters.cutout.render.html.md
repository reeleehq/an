# an.adapters.cutout.render

The 2D stage engine (`runtime.js` in headless Chromium), and the cut-out renderer built on it.

Since an#247 this module is an ENGINE, not a whole renderer: the frame stage is
the core’s ([`an.engines.frame_stage_renderer()`](an.engines.html.md#an.engines.frame_stage_renderer) – clock, capture loop,
supersample and shutter resolves, MP4 sink, provenance), and this module only
does what is specific to the stage:

1. [`StageEngine`](#an.adapters.cutout.render.StageEngine) compiles the shot to a `CutoutSceneJSON`
   (`compile_shot`), stages a copy of the JS runtime plus the shot’s textures
   in `<work_dir>/shot_<id>/runtime/`, serves it over loopback HTTP (PixiJS
   cannot fetch `file://` in headless Chromium), launches Chromium with the
   pinned rasteriser flags, injects the supersample factor, loads the scene with
   a deadline, and judges the determinism probe.
2. It yields a session the core drives: `_CanvasStageSession` (the
   default, `capture="canvas"`: batches of in-page canvas reads,
   `window.anCaptureFrames`) or `_ScreenshotStageSession`
   (`capture="screenshot"`: an element screenshot per instant). Both are
   batched (`frames(requests)`), so a runtime throw is located by frame.
3. [`CutoutRenderer`](#an.adapters.cutout.render.CutoutRenderer) is `frame_stage_renderer(StageEngine())` under the
   persisted renderer name `cutout`, raising `CutoutRenderError`.

The engine-independent halves moved to the core in an#247 and are still
reachable here by their old names: the mux, the pixel format and the x264 argv
([`an.media.mp4`](an.media.mp4.html.md#module-an.media.mp4)), the frame naming ([`an.media.frames`](an.media.frames.html.md#module-an.media.frames)), the resolves
([`an.media.supersample`](an.media.supersample.html.md#module-an.media.supersample), [`an.media.shutter`](an.media.shutter.html.md#module-an.media.shutter)) and the capture tunables
([`an.engines.capture`](an.engines.capture.html.md#module-an.engines.capture)). Those old names are LIVE aliases
(`an._shims`): rebinding `DETERMINISTIC_X264_ARGS` or `DEFAULT_PIX_FMT`
here rebinds the global the core reads, so the bench’s levers keep reaching the
encode. The whole module moves to `an.stage` in the next step of an#247.

Failures are reported with concrete remediation: missing ffmpeg, missing
Chromium, runtime load timeout, etc. Subprocess errors are wrapped at the
facade boundary.

```pycon
>>> CutoutRenderer().name, CutoutRenderer().supported_renderers
('cutout', ('cutout',))
```

### Module Attributes

| [`STAGE_ENGINE_NAME`](#an.adapters.cutout.render.STAGE_ENGINE_NAME)             | what it is, independent of the renderer names it is registered under (`cutout`, a persisted identifier, and `stage`).                                                                                                                                                                |
|--------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DEFAULT_ASSET_LOAD_TIMEOUT_MS`](#an.adapters.cutout.render.DEFAULT_ASSET_LOAD_TIMEOUT_MS) | Deadline for `anLoadScene`, which awaits `PIXI.Assets.load` for every declared texture.                                                                                                                                                                                              |
| [`DETERMINISTIC_CHROMIUM_ARGS`](#an.adapters.cutout.render.DETERMINISTIC_CHROMIUM_ARGS)   | Chromium launch flags that pin the rasteriser (an#31, research §2).                                                                                                                                                                                                                  |
| [`DEFAULT_CAPTURE`](#an.adapters.cutout.render.DEFAULT_CAPTURE)               | the runtime's `anCaptureFrames` reads the canvas in-page and hands back PNG data URLs in batches (`an.adapters.cutout.canvas_capture`), which writes frames whose DECODED pixels equal the screenshot path's — ~7.8x faster in the frame stage on the golden corpus, ~2.3x at 1080p. |
| [`SUPPORTED_CAPTURES`](#an.adapters.cutout.render.SUPPORTED_CAPTURES)            | a typo must fail before a browser launches, not minutes into a render.                                                                                                                                                                                                               |
| [`ASSET_LOAD_TIMEOUT_MARKER`](#an.adapters.cutout.render.ASSET_LOAD_TIMEOUT_MARKER)     | Sentinel the in-page deadline rejects with, so the Python side can tell a timeout apart from a load failure and say something different about each.                                                                                                                                  |
| [`ASSET_SRC_PREFIX_TO_STORE`](#an.adapters.cutout.render.ASSET_SRC_PREFIX_TO_STORE)     | Texture `src` prefix → the mall store that resolves the rest of the path.                                                                                                                                                                                                            |

### Functions

| [`effective_step_hz`](#an.adapters.cutout.render.effective_step_hz)(shot, ctx)   | The stepped-timing policy a shot renders under (an#89): the shot's own `step_hz` when it declares one, else the scene's (`ctx.step_hz`), else `None` — smooth.   |
|---------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### Classes

| [`CutoutRenderer`](#an.adapters.cutout.render.CutoutRenderer)([engine, name, ...])   | Headless cutout renderer: the stage engine through the core frame stage.                                       |
|----------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| [`StageEngine`](#an.adapters.cutout.render.StageEngine)([name])                   | The 2D stage runtime as an [`Engine`](an.engines.protocol.html.md#an.engines.protocol.Engine). |

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

### *class* an.adapters.cutout.render.CutoutRenderer(engine=<factory>, name='cutout', supported_renderers=('cutout', ), error=<class 'an.adapters.cutout.render.CutoutRenderError'>, capture_options=<factory>)

Bases: [`FrameStageRenderer`](an.engines.frame_stage.html.md#an.engines.frame_stage.FrameStageRenderer)

Headless cutout renderer: the stage engine through the core frame stage.

```pycon
>>> r = CutoutRenderer()
>>> r.name
'cutout'
>>> r.supported_renderers
('cutout',)
```

#### error

alias of [`CutoutRenderError`](#an.adapters.cutout.render.CutoutRenderError)

#### supported_renderers *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('cutout',)*

The `Shot.renderer` values this renderer claims (the ONE place it names them).

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

### an.adapters.cutout.render.STAGE_ENGINE_NAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'stage'*

what it is, independent of the renderer names it is
registered under (`cutout`, a persisted identifier, and `stage`).

* **Type:**
  The engine’s name

### an.adapters.cutout.render.SUPPORTED_CAPTURES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('screenshot', 'canvas')*

a typo must
fail before a browser launches, not minutes into a render.

* **Type:**
  The capture paths `_check_capture` accepts. Not an open string

### *class* an.adapters.cutout.render.StageEngine(name='stage')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The 2D stage runtime as an [`Engine`](an.engines.protocol.html.md#an.engines.protocol.Engine).

Stateless: every `open()` launches its own Chromium and HTTP server, so
one instance serves a parallel render.

#### check(ctx)

Refuse an unknown capture path before anything launches.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

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
