# an.adapters.remotion_adapter

RemotionRenderer — invoke `npx remotion render` against a generated TSX project.

Phase 6 skeleton. The full implementation needs a templated Remotion node
project (package.json + Composition.tsx + Root.tsx) and per-shot TSX
generation. For now the renderer raises a clear error when invoked,
documenting what’s needed.

### Classes

| [`RemotionRenderer`](#an.adapters.remotion_adapter.RemotionRenderer)()   | Remotion-based renderer (skeleton).   |
|-----------------------------------------------------------------------|---------------------------------------|

### Exceptions

| [`RemotionRenderError`](#an.adapters.remotion_adapter.RemotionRenderError)   | Raised when a Remotion render fails.   |
|------------------------------------------------------------------------|----------------------------------------|

### *exception* an.adapters.remotion_adapter.RemotionRenderError

Bases: `RuntimeError`

Raised when a Remotion render fails.

### *class* an.adapters.remotion_adapter.RemotionRenderer

Bases: `object`

Remotion-based renderer (skeleton).
