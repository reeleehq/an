"""Moved to :mod:`an.media.shutter` (an#247); this path is a LIVE alias of it.

The resolve is engine-independent, so it lives in the core's media package.
Every name of the new module is reachable here, and rebinding one here rebinds
it there (:func:`an._shims.alias_module`).
"""

from an._shims import alias_module

alias_module(__name__, "an.media.shutter")
