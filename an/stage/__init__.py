"""The 2D stage: the default engine, shipped with ``an`` but outside the core (an#247).

ADR 0001 decisions 5, 9 and 14; core study §5. The stage is a keyframed 2D
scene-graph player -- ``runtime.js`` (PixiJS) in headless Chromium, its JSON
wire contract, and what it draws for every genre: stroked paths, text, raster
and SVG art, planes with parallax, props, the camera, surface treatments. It is
ONE engine among several (Manim draws explainer shots, ``previz`` engines draw
view states), so the core never imports it: the renderer registry names it by
module and imports it on first use (``an.adapters.register_lazy_renderer``).
Its optional dependency (Playwright) is the ``an[stage]`` extra.

- :mod:`an.stage.render` -- :class:`~an.stage.render.StageEngine` and the
  renderer, which claims both ``stage`` and the persisted ``cutout``;
- :mod:`an.stage.compile` -- shot -> compiled document, as ordered compile
  passes (:mod:`an.stage.passes`); genres register theirs;
- :mod:`an.stage.serialize` -- the wire contract (field names unchanged);
- :mod:`an.stage.timeline` -- the compiled document's evaluation and screen space;
- drawables: :mod:`~an.stage.paths`, :mod:`~an.stage.text`,
  :mod:`~an.stage.raster`, :mod:`~an.stage.environments`, :mod:`~an.stage.props`;
  :mod:`~an.stage.path_geometry`, :mod:`~an.stage.text_layout`, :mod:`~an.stage.surface`;
- :mod:`an.stage.preview` (live preview), :mod:`an.stage.fidelity`,
  :mod:`an.stage.canvas_capture`, :mod:`an.stage.runtime_files` and the bundled
  runtime under ``an/stage/runtime/``.

Every old path (``an.adapters.cutout.render``, ``an.paths``, ...) is a live alias.
This ``__init__`` imports nothing, so importing one stage module does not load
the others.
"""

#: The ``Shot.renderer`` values the stage draws: the persisted ``cutout`` and
#: the engine's own ``stage`` (ADR 0001 decision 9). The ONE copy.
STAGE_RENDERER_NAMES: tuple[str, ...] = ("cutout", "stage")
