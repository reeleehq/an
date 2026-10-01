"""Frames to deliverables, engine-independent: the frame stage's resolves and the sinks.

Core (ADR 0001 decisions 8(a) and 12; core study §2.8 and §5). Nothing here
knows what drew a frame: the stage engine, a Manim shot or a ``burns`` crop all
hand over PNGs, and everything below is the same for each.

- :mod:`an.media.frames` -- the frame directory's naming (``frame_%06d.png``).
- :mod:`an.media.supersample` -- the SPATIAL resolve: an exact ``k x k`` block mean.
- :mod:`an.media.shutter` -- the TEMPORAL resolve: a frame's sample instants averaged.
- :mod:`an.media.mp4` -- the MP4 sink with the pinned argv, plus the shot's audio mux.
- :mod:`an.media.gif` -- the GIF sink's one palette recipe.
- :mod:`an.media.sinks` -- the ``FrameSink`` protocol and the name-keyed sink registry.

Moved out of ``an/adapters/cutout/`` and ``misc/demos/build_demos.py`` in an#247;
the old paths re-export (and the module globals the bench rebinds stay LIVE at
the old paths, see :mod:`an._shims`). Film assembly (``an.assemble``) consumes
these sinks' output and stays where it is.

>>> from an.media import get_sink
>>> get_sink("mp4").suffix
'.mp4'
"""

from an.media.frames import DEFAULT_FRAME_PNG_PATTERN, frame_path, missing_frames
from an.media.mp4 import MediaError
from an.media.sinks import (
    FrameSink,
    GifSink,
    Mp4Sink,
    PngSequenceSink,
    get_sink,
    register_sink,
    sink_names,
)
from an.media.supersample import NO_SUPERSAMPLE, block_mean_resolve, check_factor
from an.media.shutter import check_frame_samples, mean_png_bytes, temporal_mean

__all__ = [
    "DEFAULT_FRAME_PNG_PATTERN",
    "FrameSink",
    "GifSink",
    "MediaError",
    "Mp4Sink",
    "NO_SUPERSAMPLE",
    "PngSequenceSink",
    "block_mean_resolve",
    "check_factor",
    "check_frame_samples",
    "frame_path",
    "get_sink",
    "mean_png_bytes",
    "missing_frames",
    "register_sink",
    "sink_names",
    "temporal_mean",
]
