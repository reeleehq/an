# an.adapters

Renderer adapters — facades over backends (the stage, Manim, Remotion, whiteboard).

The Renderer Protocol and registry live in `_base`. The core’s own optional
backends are imported here so they self-register on package import. The stage
(`an.stage`, the cut-out renderer) sits behind the import firewall, so it is
named by MODULE and imported the first time the registry is asked anything
(an#247). Backends with missing
system deps still register but their `render()` raises a clear error;
`can_render(shot)` continues to work for routing decisions.

### Functions

| [`register_renderer`](#an.adapters.register_renderer)(renderer)          | Register a renderer in the default registry.                               |
|---------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`get_renderer`](#an.adapters.get_renderer)(name)                   | Look up a renderer by name in the default registry.                        |
| [`list_renderers`](#an.adapters.list_renderers)()                     | Names of all renderers registered in the default registry.                 |
| [`register_lazy_renderer`](#an.adapters.register_lazy_renderer)(name, module) | Name the module whose import registers renderer `name` (default registry). |

### Classes

| [`Renderer`](#an.adapters.Renderer)(\*args, \*\*kwargs)                       | Backend renderer interface.                                                  |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`RendererRegistry`](#an.adapters.RendererRegistry)(\*[, entry_point_group])          | Name-keyed registry of renderers.                                            |
| [`RenderContext`](#an.adapters.RenderContext)(mall, work_dir[, fps, ...])          | Everything a renderer needs that isn't on the Shot itself.                   |
| [`RenderResult`](#an.adapters.RenderResult)(mp4_path, duration[, ...])            | Outcome of a single shot render.                                             |
| [`ManimRenderer`](#an.adapters.ManimRenderer)(\*[, render_check, source_resolver]) | Manim Community Edition, through `manimkit`: an opaque-source shot renderer. |
| [`RemotionRenderer`](#an.adapters.RemotionRenderer)()                                 | Remotion-based renderer (skeleton).                                          |
| [`WhiteboardRenderer`](#an.adapters.WhiteboardRenderer)()                               | Whiteboard-style renderer (stub).                                            |

### *class* an.adapters.ManimRenderer(, render_check=None, source_resolver=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Manim Community Edition, through `manimkit`: an opaque-source shot renderer.

Implements [`Renderer`](#an.adapters.Renderer) and
`ClockOwningRenderer`. Seams: `render_check`
(default `manimkit.render_check()`, imported on first use) and
`source_resolver` (default: the project’s `sources` store,
`store_source_resolver()`). The shot cache keys a shot through the
REGISTERED instance’s resolver; a subclass registers its own keyer
(`register_shot_keyer(name, manim_shot_inputs, renderer_type=Sub)`).

#### measure_duration(shot, ctx, , render=True, force=False)

Manim’s length of this shot’s scene, from the `measurements` store,
or rendered now (and stored) when there is none — or when `force`.

* **Return type:**
  `DurationMeasurement` | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### probe_frames(shot, ctx, times)

The film’s frames of `shot` at each of `times`, from its STORED picture (an#347).

Manim owns its clock and renders a whole scene at once, so `an
probe` never runs it: the picture a render stored is conformed
exactly as [`render()`](#an.adapters.ManimRenderer.render) conforms it, and the frames showing at
`times` are read out. With no stored picture it refuses, naming the
render that stores one.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]

#### render(shot, ctx)

Render `shot` for exactly `shot.duration` (`an.render` settles it
to the measured length, or longer to hold for its narration).

* **Return type:**
  [`RenderResult`](#an.adapters.RenderResult)

#### stored_reads(key, ctx)

The read trace stored with picture `key` (`None`: none stored,
or not recorded). Reads stores only; never renders.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *class* an.adapters.RemotionRenderer

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Remotion-based renderer (skeleton).

### *class* an.adapters.RenderContext(mall, work_dir, fps=30, resolution=(1920, 1080), strict_assets=False, supersample=1, pix_fmt=None, step_hz=None, style_pack=None, default_easing=None, frame_samples=None, capture=None, extra=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Everything a renderer needs that isn’t on the Shot itself.

`mall` carries the project’s stores so the renderer can resolve assets
by reference. `work_dir` is a scratch space; the renderer must clean up
after itself or treat it as ephemeral.

#### capture *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

`"screenshot"` (a Playwright element
screenshot per instant) or `"canvas"` (the runtime reads its own canvas
in-page, in batches). `None` is the renderer’s module default, read at
call time — `"canvas"` since an#192, after the equivalence gate held on
the whole corpus on both lanes. The two paths write frames whose DECODED
pixels are equal, so this is a throughput knob and never a picture knob;
a `RenderContext` field for `supersample`’s reason, and recorded in
per-shot provenance.

* **Type:**
  How frames leave the browser

#### default_easing *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)*

the curve of every
authored tween that names none. `None` = the built-in
`"ease_in_out"`, and a compiled document byte-identical to before the
field existed; set, it changes keyframes, so the contract hash moves
with it — as it should.

* **Type:**
  The scene’s `meta.default_easing` (an#166)

#### fps *: [int](https://docs.python.org/3/builtins/functions.html#int) | [float](https://docs.python.org/3/builtins/functions.html#float)*

Frames per second of the delivered video. May be non-integer — a
camera’s 29.97 — and the capture loop and the mux honour it exactly. The
COMPILER aligns its frame-sampled curves (gaze saccades, co-articulation,
descriptor plays, face curves) to the nearest integer grid instead,
because the compiled document’s `meta.fps` is an integer; tweens and
every other keyframe are exact at any rate.

#### frame_samples *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), ...], ...] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per output frame, the scene instants to render and average into it —
`None` is one instant at `i / fps`, the path every render took before
this field existed, byte for byte. Several instants per frame are an open
shutter (motion blur); instants off the `i / fps` grid are capture
jitter. Built by [`an.frame_clock.FrameClock`](an.frame_clock.html.md#an.frame_clock.FrameClock), which is also what
the impact harness writes into its ground truth, so the render and the
record of when each frame was taken come from one object.

A `RenderContext` field for `supersample`’s reason: it changes how frames
are CAPTURED, not what the scene is, so it must not move the compiled
document. Its length must equal the render’s frame count.

#### pix_fmt *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The delivered encode’s pixel format, or `None` for the module default.
**The one first-order quality lever in the encoder**: 4:2:0 -> 4:4:4 cuts
the edge-band error 11.35 -> 3.79, where mathematically lossless 4:2:0
only reaches 10.15. Losslessness buys 8%; dropping chroma subsampling
buys 66%.

`None` rather than the literal, so the bench’s `pix_fmt` lever — which
rebinds the module default — still reaches an unset render. The default
stays 4:2:0 for a PRODUCT reason and not an encoder one: High 4:4:4
Predictive is refused by many hardware decoders, browsers and platforms.

#### step_hz *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Scene-level stepped-timing policy for authored tweens (an#89); a shot’s
own `step_hz` overrides it. `None` = smooth. Reaches the compiled
document’s `meta.step_hz` (only when set) and per-shot provenance.

The one deliberate exception to the rule two fields up (“a field on the
compiled scene document moves `scene_contract_sha256`”): unlike
`supersample`, this knob CHANGES the compiled document — the resampled
keyframes are the contract — so the hash moves whenever it is set no
matter where the knob lives, and a document that carries its own timing
policy is the honest one. Omit-when-unset keeps the unset case free.

#### strict_assets *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Refuse to draw a stand-in for a declared asset that the stores do not
supply. Off by default so an asset-less project still renders; on for
anything that measures pixels, where a stand-in is a different picture
that looks like a successful render (an#33).

#### style_pack *: [StylePack](an.styles.html.md#an.styles.StylePack) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The `StylePack` this render is drawn under, already resolved from the
scene’s `meta.style_pack` (an#112). Resolved ONCE per render rather than
per shot: a pack is art direction for a project, and a scene whose shots
disagreed about it would be two scenes.

#### supersample *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Render at this many times the declared resolution and resolve back with
an exact block mean. **1 means off, and off is free** — Chromium’s own
PNG bytes reach disk untouched.

A `RenderContext` field, and that placement is load-bearing rather than
convenient. Simulated against a real committed ledger row: as a
`render_kwargs` entry it becomes a `COMMON_ENV_PATHS` key and \*\*all 96
metrics are refused\*\*; as a field on the compiled scene document it moves
`scene_contract_sha256` and **every scene becomes incomparable**; here,
only `runtime_sha256` moves, which is deliberately not a comparability
key — so 30 render-side entries still compare. It needs no
`SCHEMA_VERSION` migration, and it MUST reach per-shot provenance, because
a row that does not record it cannot be read back later.

### *class* an.adapters.RenderResult(mp4_path, duration, frame_manifest=<factory>, log='', provenance=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Outcome of a single shot render.

### *class* an.adapters.Renderer(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Backend renderer interface.

Implementations should be cheap to construct and stateless across renders;
state belongs in the `RenderContext` or the project mall.

#### can_render(shot)

Return True if this renderer can render `shot`.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### render(shot, ctx)

Render a single shot to mp4. Idempotent given identical inputs.

* **Return type:**
  [`RenderResult`](#an.adapters.RenderResult)

#### supported_renderers *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

The `Shot.renderer` values this backend claims. It is the ONE place
an adapter names them: `can_render` derives from it rather than
comparing to its own literal, so an adapter cannot advertise one
renderer and accept another. an#106 renamed this from
`supported_styles`; the rename is a break for an out-of-tree adapter
because `Renderer` is `@runtime_checkable` and 3.12 checks data
members, so `isinstance(old_adapter, Renderer)` is now False.

### *class* an.adapters.RendererRegistry(, entry_point_group=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Name-keyed registry of renderers.

A module-level instance is exposed via `register_renderer` /
`get_renderer` / `list_renderers`; callers needing isolation (tests,
multi-tenant servers) can construct their own.

**Backends outside the core register LAZILY** (an#247): a renderer that
lives behind the import firewall – the stage, a genre’s, a third-party
engine – is named here by the MODULE that registers it
([`register_lazy()`](#an.adapters.RendererRegistry.register_lazy), or the `an.renderers` entry point group), and
that module is imported the first time the registry is asked anything. So
importing the core loads no backend, and every lookup still finds it.

#### find_for(shot)

Return the first registered renderer that `can_render(shot)`.

`None` when none can; a `RendererLoadError` when none can AND
a backend failed to import, since that backend may have been the one.

* **Return type:**
  [`Renderer`](#an.adapters.Renderer) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### get(name)

The renderer registered as `name`, else the one that claims it
(`get("stage")` is the stage renderer, registered as `cutout`).

* **Return type:**
  [`Renderer`](#an.adapters.Renderer)

#### register_lazy(name, module)

Declare that importing `module` registers the renderer `name`.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *class* an.adapters.WhiteboardRenderer

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Whiteboard-style renderer (stub).

### an.adapters.get_renderer(name)

Look up a renderer by name in the default registry.

* **Return type:**
  [`Renderer`](#an.adapters.Renderer)

### an.adapters.list_renderers()

Names of all renderers registered in the default registry.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.adapters.register_lazy_renderer(name, module)

Name the module whose import registers renderer `name` (default registry).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.adapters.register_renderer(renderer)

Register a renderer in the default registry.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### Modules

| [`cutout`](an.adapters.cutout.html.md#module-an.adapters.cutout)                     | The cut-out backend's old package: the stage moved to [`an.stage`](an.stage.html.md#module-an.stage) (an#247).   |
|-------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| [`manim_adapter`](an.adapters.manim_adapter.html.md#module-an.adapters.manim_adapter)       | ManimRenderer — a whole-shot renderer for opaque Manim scene files (an#279).                                                                |
| [`remotion_adapter`](an.adapters.remotion_adapter.html.md#module-an.adapters.remotion_adapter) | RemotionRenderer — invoke `npx remotion render` against a generated TSX project.                                                            |
| [`whiteboard`](an.adapters.whiteboard.html.md#module-an.adapters.whiteboard)             | WhiteboardRenderer — stub for hand-drawn / chalkboard-style animation.                                                                      |
