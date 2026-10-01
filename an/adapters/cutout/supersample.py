"""Moved to :mod:`an.media.supersample` (an#247); this path re-exports it.

The spatial resolve is engine-independent, so it lives in the core's media
package. Every name below is the same object as in its new home.
"""

from an.media.supersample import (  # noqa: F401
    NO_SUPERSAMPLE,
    SupersampleError,
    block_mean_resolve,
    check_factor,
    resolve_png_bytes,
)

__all__ = [
    "NO_SUPERSAMPLE",
    "SupersampleError",
    "block_mean_resolve",
    "check_factor",
    "resolve_png_bytes",
]
