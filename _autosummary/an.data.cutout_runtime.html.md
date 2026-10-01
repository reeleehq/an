# an.data.cutout_runtime

Moved to [`an.stage.runtime`](an.stage.runtime.html.md#module-an.stage.runtime) (an#247); this path is a LIVE alias of it.

The 2D stage runtime is the first engine, outside the core’s import firewall
(ADR 0001 decisions 5 and 14). Every name of the new module is reachable here,
and rebinding one here (a bench lever, `monkeypatch`) rebinds it there, where
the code runs (`an._shims.alias_module()`).
