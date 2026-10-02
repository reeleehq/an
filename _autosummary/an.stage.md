# an.stage

The 2D stage: the default engine, shipped with `an` but outside the core (an#247).

ADR 0001 decisions 5, 9 and 14; core study §5. The stage is a keyframed 2D
scene-graph player – `runtime.js` (PixiJS) in headless Chromium, its JSON
wire contract, and what it draws for every genre: stroked paths, text, raster
and SVG art, planes with parallax, props, the camera, surface treatments. It is
ONE engine among several (Manim draws explainer shots, `previz` engines draw
view states), so the core never imports it: the renderer registry names it by
module and imports it on first use (`an.adapters.register_lazy_renderer`).
Its optional dependency (Playwright) is the `an[stage]` extra.

- [`an.stage.render`](an.stage.render.md#module-an.stage.render) – [`StageEngine`](an.stage.render.md#an.stage.render.StageEngine) and the
  renderer, which claims both `stage` and the persisted `cutout`;
- [`an.stage.compile`](an.stage.compile.md#module-an.stage.compile) – shot -> compiled document, as ordered compile
  passes (`an.stage.passes`); genres register theirs;
- [`an.stage.serialize`](an.stage.serialize.md#module-an.stage.serialize) – the wire contract (field names unchanged);
- [`an.stage.timeline`](an.stage.timeline.md#module-an.stage.timeline) – the compiled document’s evaluation and screen space;
- drawables: [`paths`](an.stage.paths.md#module-an.stage.paths), [`text`](an.stage.text.md#module-an.stage.text),
  [`raster`](an.stage.raster.md#module-an.stage.raster), [`environments`](an.stage.environments.md#module-an.stage.environments), [`props`](an.stage.props.md#module-an.stage.props);
  [`path_geometry`](an.stage.path_geometry.md#module-an.stage.path_geometry), [`text_layout`](an.stage.text_layout.md#module-an.stage.text_layout), [`surface`](an.stage.surface.md#module-an.stage.surface);
- [`an.stage.preview`](an.stage.preview.md#module-an.stage.preview) (live preview), [`an.stage.fidelity`](an.stage.fidelity.md#module-an.stage.fidelity),
  [`an.stage.canvas_capture`](an.stage.canvas_capture.md#module-an.stage.canvas_capture), [`an.stage.runtime_files`](an.stage.runtime_files.md#module-an.stage.runtime_files) and the bundled
  > runtime under `an/stage/runtime/`.

Every old path (`an.adapters.cutout.render`, `an.paths`, …) is a live alias.
This `__init__` imports nothing, so importing one stage module does not load
the others.

### Module Attributes

| [`STAGE_RENDERER_NAMES`](#an.stage.STAGE_RENDERER_NAMES)   | the persisted `cutout` and the engine's own `stage` (ADR 0001 decision 9).   |
|-------------------------------------------------------------------------|------------------------------------------------------------------------------|

### an.stage.STAGE_RENDERER_NAMES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('cutout', 'stage')*

the persisted `cutout` and
the engine’s own `stage` (ADR 0001 decision 9). The ONE copy.

* **Type:**
  The `Shot.renderer` values the stage draws

### Modules

| [`cache_key`](an.stage.cache_key.md#module-an.stage.cache_key)           | What a cut-out shot render reads: the keyer behind its shot-cache key (ADR 0004).                                                           |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| [`canvas_capture`](an.stage.canvas_capture.md#module-an.stage.canvas_capture) | The canvas capture path: frames read from the page, not photographed off the screen.                                                        |
| [`compile`](an.stage.compile.md#module-an.stage.compile)               | Compile a top-level `Shot` (renderer="cutout") into a `CutoutSceneJSON`.                                                                    |
| [`easing`](an.stage.easing.md#module-an.stage.easing)                 | The stage engine's easing vocabulary — a view of [`an.timing.easing`](an.timing.easing.md#module-an.timing.easing). |
| [`environments`](an.stage.environments.md#module-an.stage.environments)     | Environments: a stage made of planes, at declared depths.                                                                                   |
| [`fidelity`](an.stage.fidelity.md#module-an.stage.fidelity)             | How faithfully a compiled scene reproduces the art it was built from.                                                                       |
| [`gradients`](an.stage.gradients.md#module-an.stage.gradients)           | Gradient fills on the stage: a [`Gradient`](an.paint.md#an.paint.Gradient) drawn as an inline SVG texture.  |
| [`path_geometry`](an.stage.path_geometry.md#module-an.stage.path_geometry)   | Stroked-path geometry — the executable spec of `runtime.js::pathGeometry`.                                                                  |
| [`paths`](an.stage.paths.md#module-an.stage.paths)                   | Stroked paths: routes, invasion arrows, borders, timelines, connectors.                                                                     |
| [`preview`](an.stage.preview.md#module-an.stage.preview)               | Live preview server: render a project's current scene in a browser, reloading on edit.                                                      |
| [`props`](an.stage.props.md#module-an.stage.props)                   | Props: a rig whose art is not a person.                                                                                                     |
| [`raster`](an.stage.raster.md#module-an.stage.raster)                 | Raster art: what a PNG, JPEG or WebP is, read from its header (an#211).                                                                     |
| [`render`](an.stage.render.md#module-an.stage.render)                 | The 2D stage engine (`runtime.js` in headless Chromium), and the cut-out renderer built on it.                                              |
| [`rig`](an.stage.rig.md#module-an.stage.rig)                       | The rig model the stage draws: bones, slots, skins and attachments.                                                                         |
| [`runtime`](an.stage.runtime.md#module-an.stage.runtime)               | Cutout JS runtime — see README.md in this directory.                                                                                        |
| [`runtime_files`](an.stage.runtime_files.md#module-an.stage.runtime_files)   | Locate the bundled cutout JS runtime files.                                                                                                 |
| [`serialize`](an.stage.serialize.md#module-an.stage.serialize)           | JSON contract between the Python compiler and the (future) JS runtime.                                                                      |
| [`surface`](an.stage.surface.md#module-an.stage.surface)               | Surface treatments, compiled (an#163 gap 5): outline, paper-gap shadow, glow, grain.                                                        |
| [`text`](an.stage.text.md#module-an.stage.text)                     | Words on screen: title cards, labels, and text you can animate word by word.                                                                |
| [`text_layout`](an.stage.text_layout.md#module-an.stage.text_layout)       | A text block, compiled: one node per unit, each an SVG sprite (an#155).                                                                     |
| [`timeline`](an.stage.timeline.md#module-an.stage.timeline)             | Stage timeline helpers: the compiled scene as a `Timeline`, and screen space.                                                               |
