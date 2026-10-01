# an.adapters.manim_adapter

ManimRenderer — generate a minimal Manim scene + invoke `manim` as subprocess.

Phase 6 ships the wiring + a placeholder scene. Real shot-to-Manim translation
is a Phase 7+ effort: it needs careful mapping from anima’s renderer-agnostic
IR onto Manim’s mobject grammar (Text / VGroup / Animation / etc).

For now: every cutout-style shot rendered through this adapter produces a
minimal “title card” Manim scene of the right duration. Useful as a pipeline
sanity check; not a real animation.

### Classes

| [`ManimRenderer`](#an.adapters.manim_adapter.ManimRenderer)()   | Manim Community Edition renderer (skeleton).   |
|--------------------------------------------------------------------|------------------------------------------------|

### Exceptions

| [`ManimRenderError`](#an.adapters.manim_adapter.ManimRenderError)   | Raised when a Manim render fails.   |
|---------------------------------------------------------------------|-------------------------------------|

### *exception* an.adapters.manim_adapter.ManimRenderError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when a Manim render fails. Carries actionable detail.

### *class* an.adapters.manim_adapter.ManimRenderer

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Manim Community Edition renderer (skeleton).

Implements the `Renderer` Protocol. `can_render` is True for shots
whose `renderer` is `"manim"`.
