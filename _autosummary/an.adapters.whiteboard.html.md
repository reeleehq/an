# an.adapters.whiteboard

WhiteboardRenderer — stub for hand-drawn / chalkboard-style animation.

Phase 6 ships the registry entry only. The real implementation will likely
be a thin wrapper around the cutout backend with hand-drawn-styled assets
(rough strokes, paper texture), or a Manim subclass with a chalkboard theme.
A spike during v0.1 picks the direction.

### Classes

| [`WhiteboardRenderer`](#an.adapters.whiteboard.WhiteboardRenderer)()   | Whiteboard-style renderer (stub).   |
|-------------------------------------------------------------------------|-------------------------------------|

### Exceptions

| [`WhiteboardRenderError`](#an.adapters.whiteboard.WhiteboardRenderError)   | Raised by the whiteboard stub.   |
|--------------------------------------------------------------------------|----------------------------------|

### *exception* an.adapters.whiteboard.WhiteboardRenderError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised by the whiteboard stub.

### *class* an.adapters.whiteboard.WhiteboardRenderer

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Whiteboard-style renderer (stub).
