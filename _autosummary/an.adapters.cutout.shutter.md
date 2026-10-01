# an.adapters.cutout.shutter

Moved to [`an.media.shutter`](an.media.shutter.md#module-an.media.shutter) (an#247); this path is a LIVE alias of it.

The resolve is engine-independent, so it lives in the core’s media package.
Every name of the new module is reachable here, and rebinding one here rebinds
it there (`an._shims.alias_module()`).
