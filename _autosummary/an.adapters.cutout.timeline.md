# an.adapters.cutout.timeline

Moved to [`an.stage.timeline`](an.stage.timeline.md#module-an.stage.timeline) (an#247); this path is a LIVE alias of it.

The compiled document’s evaluation entry point and its screen space are the
stage’s (ADR 0001 decision 5). Every name of the new module is reachable here,
and rebinding one here rebinds it there (`an._shims.alias_module()`).
