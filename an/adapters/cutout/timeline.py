"""Moved to :mod:`an.stage.timeline` (an#247); this path is a LIVE alias of it.

The compiled document's evaluation entry point and its screen space are the
stage's (ADR 0001 decision 5). Every name of the new module is reachable here,
and rebinding one here rebinds it there (:func:`an._shims.alias_module`).
"""

from an._shims import alias_module

alias_module(__name__, "an.stage.timeline")
