"""Moved to :mod:`an.media.shutter` (an#247); this path re-exports it.

The temporal resolve is engine-independent, so it lives in the core's media
package. Every name below is the same object as in its new home.
"""

from an.media.shutter import (  # noqa: F401
    ShutterError,
    check_frame_samples,
    mean_png_bytes,
    temporal_mean,
)

__all__ = [
    "ShutterError",
    "check_frame_samples",
    "mean_png_bytes",
    "temporal_mean",
]
