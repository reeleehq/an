"""The temporal half of the frame stage: average several instants into one frame.

`supersample.py` resolves a frame SPATIALLY — k x k pixels into one. This module
resolves it TEMPORALLY — the screenshots taken at each of a frame's sample
instants (``RenderContext.frame_samples``, built by
:class:`an.frame_clock.FrameClock`) into the one frame a camera with an open
shutter would have recorded. Same place, same rules: the resolve runs in the
frame stage, so everything downstream still sees PNGs at the declared size, and
the rounding is spelled out rather than inherited.

**One sample is free.** A frame with a single instant keeps the bytes the
spatial path produces (Chromium's own, at ``supersample == 1``), so a render
without an open shutter is byte-identical to one from before this module.

Engine-independent, like the spatial half: moved from
``an/adapters/cutout/shutter.py`` (an#247), which re-exports it.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from typing import Any

from an.media.supersample import resolve_png_bytes

__all__ = [
    "ShutterError",
    "check_frame_samples",
    "mean_png_bytes",
    "temporal_mean",
]


class ShutterError(ValueError):
    """Frame samples a render cannot honour."""


def check_frame_samples(
    frame_samples: Sequence[Sequence[float]] | None,
    *,
    total_frames: int,
    duration: float,
) -> tuple[tuple[float, ...], ...] | None:
    """Validate ``frame_samples`` against the render it is for; normalise to tuples.

    Checked before a browser launches, for `check_factor`'s reason: the render
    costs minutes and this costs microseconds.

    >>> check_frame_samples(None, total_frames=3, duration=0.1) is None
    True
    >>> check_frame_samples([[0.0], [0.5, 0.6]], total_frames=2, duration=1.0)
    ((0.0,), (0.5, 0.6))
    >>> check_frame_samples([[0.0]], total_frames=2, duration=1.0)
    Traceback (most recent call last):
      ...
    an.media.shutter.ShutterError: frame_samples has 1 frame(s) but this render has 2; a frame clock must describe every frame, and only those
    """
    if frame_samples is None:
        return None
    normalised = tuple(tuple(float(t) for t in frame) for frame in frame_samples)
    if len(normalised) != total_frames:
        raise ShutterError(
            f"frame_samples has {len(normalised)} frame(s) but this render has "
            f"{total_frames}; a frame clock must describe every frame, and only those"
        )
    for i, frame in enumerate(normalised):
        if not frame:
            raise ShutterError(f"frame {i} has no sample instants")
        bad = [t for t in frame if not (math.isfinite(t) and 0.0 <= t <= duration)]
        if bad:
            raise ShutterError(
                f"frame {i} samples {bad} lie outside the shot's timeline "
                f"[0, {duration}]; the scene has no state there to capture"
            )
    return normalised


def temporal_mean(frames: Sequence[Any]) -> Any:
    """``k`` equal-shape uint8 frames -> their exact per-pixel mean, uint8.

    Rounded half-to-even, the rule `block_mean_resolve` spells out, so the
    temporal and spatial resolves agree about every tie. The mean is of the
    ENCODED (sRGB) values, as the spatial resolve's is — not of linear light, so
    a smear's profile is not exactly a physical sensor's. The centroid of what
    is drawn is still the average of the sampled positions, which is the
    property the impact ground truth relies on.

    >>> import numpy as np
    >>> a, b = np.full((1, 2, 3), 1, np.uint8), np.full((1, 2, 3), 2, np.uint8)
    >>> temporal_mean([a, b])[0, 0].tolist()   # 1.5 -> 2 (even)
    [2, 2, 2]
    >>> temporal_mean([a, a + 2])[0, 0].tolist()   # 2.0 exactly
    [2, 2, 2]
    >>> temporal_mean([a]) is a
    True
    """
    import numpy as np

    if len(frames) == 1:
        return frames[0]
    shapes = {f.shape for f in frames}
    if len(shapes) != 1:
        raise ShutterError(f"sample frames differ in shape: {sorted(shapes)}")
    count = len(frames)
    total = np.sum(np.stack(frames).astype(np.uint32), axis=0)
    quotient, remainder = np.divmod(total, count)
    twice = 2 * remainder
    tie_to_even = (twice == count) & (quotient % 2 == 1)
    return (quotient + ((twice > count) | tie_to_even)).astype(np.uint8)


def mean_png_bytes(shots: Sequence[bytes], *, factor: int) -> bytes:
    """Spatially resolve each screenshot by ``factor``, then average them in time.

    One screenshot takes exactly the spatial path — the same bytes a render
    without a shutter writes.
    """
    if len(shots) == 1:
        return resolve_png_bytes(shots[0], factor=factor)

    import numpy as np
    from PIL import Image

    frames = []
    for shot in shots:
        with Image.open(io.BytesIO(resolve_png_bytes(shot, factor=factor))) as image:
            frames.append(np.asarray(image.convert("RGB")))
    out = io.BytesIO()
    Image.fromarray(temporal_mean(frames)).save(out, format="PNG")
    return out.getvalue()
