"""The canvas capture path: frames read from the page, not photographed off the screen.

The screenshot capture (`render._capture_frames`, ``capture="screenshot"``, the
default until an#192) asks Playwright for an ELEMENT screenshot of ``#stage`` on
every frame. That is a page
capture clipped to the element, taken from the compositor, and it is the largest
single cost in the frame path — ~100 ms/frame at 1080p that is neither the GPU
readback nor the PNG encode (`an-dev-render-pipeline` §8). This path instead
asks the runtime for the canvas's own pixels (``window.anCaptureFrames`` in
``runtime.js``: seek, ``app.view.toDataURL('image/png')``), in batches, and does
the rest here.

**It is a different route to the same pixels, and the whole contract is that
nothing downstream can tell.** The frames it writes are RGB PNGs of the declared
size whose DECODED arrays equal the screenshot path's, so ffmpeg receives the
same frames, the golden gate the same arrays, and the bench the same sizes. The
file bytes differ (a different PNG encoder), which is why the equivalence gate is
on decoded pixels — the same criterion the golden corpus already uses.

The classic traps, and where each one is closed:

- **Row order.** ``gl.readPixels`` returns rows bottom-up. ``toDataURL`` returns
  the image top-down, and this path uses ``toDataURL`` — so there is no flip,
  and adding one is the mutation the equivalence test must catch.
- **Premultiplied alpha.** Not live today: the runtime leaves PixiJS's
  ``backgroundAlpha`` at 1, so the WebGL context is created without alpha and
  every pixel measured came back at 255. It becomes live the day a scene gets a
  translucent background — then the premultiplied drawing buffer, the
  un-premultiplied PNG and the screenshot's composite over the page's white all
  disagree. So a frame with any pixel below full alpha is REFUSED
  (:func:`opaque_rgb`) rather than guessed at: compositing it here would be a
  second implementation of the browser's blend, equal to it only by luck.
- **Why not ``renderer.extract``.** It re-renders the stage into a render
  texture, which is not multisampled — a different picture from the one the
  ``antialias: true`` backbuffer holds.
- **Why not raw ``readPixels`` bytes.** Measured at 1920x1080 on an M1 Max:
  moving 8 MB of RGBA per frame across the DevTools protocol costs 830-950
  ms/frame (in-page base64 through ``btoa`` or ``FileReader``), and Playwright's
  own typed-array serialisation 5.9 s/frame — against ~46 ms/frame for the PNG
  data URL, which is ~45 KB. The PNG *is* the transfer encoding.

Supersampling and the frame clock go through the same arithmetic as the
screenshot path — :func:`an.adapters.cutout.supersample.block_mean_resolve` then
:func:`an.adapters.cutout.shutter.temporal_mean` — so a supersampled or blurred
canvas frame is the screenshot path's frame, not a lookalike.

Nothing in this module touches a browser: it is the pure half, testable offline.
The loop that drives the page (batching, ordering, back-pressure) is
``render._capture_frames_canvas``.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Sequence
from typing import Any

from an.media.supersample import NO_SUPERSAMPLE, block_mean_resolve

__all__ = [
    "CanvasCaptureError",
    "DATA_URL_PREFIX",
    "canvas_frame_png",
    "decode_data_url",
    "opaque_rgb",
]

#: What ``HTMLCanvasElement.toDataURL('image/png')`` returns. Anything else —
#: ``"data:,"`` for a zero-size canvas, or a JPEG a browser fell back to — is
#: refused rather than decoded as whatever it happens to be.
DATA_URL_PREFIX: str = "data:image/png;base64,"

#: zlib level for the frames this path writes. The file bytes are not the
#: contract (the decoded pixels are), so this trades disk for time only.
#: Measured at 1920x1080 on one frame of `single_character`: level 1 40.8 ms and
#: 63 KB, level 6 48.2 ms and 10 KB. 6 — Pillow's default, and what the
#: supersample resolve already writes — keeps a long shot's frames directory the
#: size the screenshot path leaves; the encode runs on a worker pool, off the
#: page's critical path, so the difference is mostly hidden.
DEFAULT_PNG_COMPRESS_LEVEL: int = 6


class CanvasCaptureError(ValueError):
    """A captured frame that cannot be turned into the screenshot path's frame."""


def decode_data_url(url: Any, *, frame: int) -> bytes:
    """A ``toDataURL('image/png')`` result -> the PNG's bytes, or refuse.

    >>> decode_data_url(DATA_URL_PREFIX + "iVBORw==", frame=0)[:4]
    b'\\x89PNG'
    >>> decode_data_url("data:,", frame=3)
    Traceback (most recent call last):
      ...
    an.stage.canvas_capture.CanvasCaptureError: frame 3: the canvas returned 'data:,' rather than a PNG data URL — a zero-size canvas does this
    """
    if not isinstance(url, str) or not url.startswith(DATA_URL_PREFIX):
        shown = url[:40] if isinstance(url, str) else type(url).__name__
        raise CanvasCaptureError(
            f"frame {frame}: the canvas returned {shown!r} rather than a PNG "
            "data URL — a zero-size canvas does this"
        )
    return base64.b64decode(url[len(DATA_URL_PREFIX) :], validate=True)


def opaque_rgb(png: bytes, *, frame: int) -> Any:
    """Decode a canvas PNG to an RGB ``PIL.Image``, refusing any transparency.

    The screenshot path composites the canvas over the page (white, since
    ``omit_background=False``); where every pixel has alpha 255 that composite
    is the identity, and the premultiplied drawing buffer and the
    un-premultiplied PNG agree. Anywhere else the two paths would differ, so the
    frame is refused with a count rather than blended here.

    Pillow end to end, deliberately: the alpha check is ``getextrema`` and the
    drop is ``convert("RGB")``, both in C. Slicing ``[..., :3]`` out of a numpy
    view and copying it contiguous measured ~5x slower at 1080p, on a path whose
    whole point is time.

    >>> import numpy as np
    >>> from PIL import Image
    >>> def png(a):
    ...     out = io.BytesIO(); Image.fromarray(a).save(out, format="PNG")
    ...     return out.getvalue()
    >>> rgba = np.zeros((2, 3, 4), np.uint8); rgba[..., 3] = 255; rgba[0, 0, 0] = 7
    >>> np.asarray(opaque_rgb(png(rgba), frame=0))[0, 0].tolist()
    [7, 0, 0]
    >>> rgba[1, 2, 3] = 128
    >>> opaque_rgb(png(rgba), frame=5)
    Traceback (most recent call last):
      ...
    an.stage.canvas_capture.CanvasCaptureError: frame 5: 1 of 6 canvas pixels are not opaque (min alpha 128); the screenshot path would composite them over the page's white and this path will not guess at that blend
    """
    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        image.load()
        mode = image.mode
        if mode not in ("RGBA", "RGB"):
            raise CanvasCaptureError(
                f"frame {frame}: the canvas PNG is mode {mode!r}; only RGBA and "
                "RGB are decoded, because any other mode is a conversion this "
                "path would be inventing"
            )
        # Chromium's `toDataURL` returned RGBA on every frame measured (alpha
        # all 255); RGB is accepted too, and both leave through the ONE
        # conversion below, so a flip or a conversion bug cannot hide in a
        # branch the tests do not reach.
        alpha = image.getchannel("A") if mode == "RGBA" else None
        low = alpha.getextrema()[0] if alpha is not None else 255
        if low != 255:
            import numpy as np

            values = np.asarray(alpha)
            raise CanvasCaptureError(
                f"frame {frame}: {int((values != 255).sum())} of {values.size} "
                f"canvas pixels are not opaque (min alpha {low}); the screenshot "
                "path would composite them over the page's white and this path "
                "will not guess at that blend"
            )
        # Rows as the PNG stores them: top-down. `toDataURL` is not
        # `readPixels`, so there is nothing to flip — see the module docstring.
        rgb = image.convert("RGB")
    # Pixels only: an iCCP / gAMA chunk from the canvas PNG must not ride
    # into the frame file, where the screenshot path's frames carry none.
    rgb.info.clear()
    return rgb


def canvas_frame_png(
    samples: Sequence[bytes],
    *,
    frame: int,
    factor: int = NO_SUPERSAMPLE,
    size: tuple[int, int] | None = None,
    compress_level: int | None = None,
) -> bytes:
    """One output frame's canvas PNGs -> the RGB PNG the screenshot path writes.

    ``samples`` are the frame's instants in capture order (one unless a frame
    clock opened the shutter). Each is decoded and refused unless opaque,
    resolved by ``factor`` with the product's block mean, and the results
    averaged with the product's temporal mean — the arithmetic the screenshot
    path runs, so the two agree about every tie. ``size`` (width, height), when
    given, is the DECLARED size the resolved frame must have: a canvas that is
    not ``factor`` times it is refused here, not muxed. ``compress_level=None``
    reads :data:`DEFAULT_PNG_COMPRESS_LEVEL` at call time.

    >>> import numpy as np
    >>> from PIL import Image
    >>> def png(a):
    ...     out = io.BytesIO(); Image.fromarray(a).save(out, format="PNG")
    ...     return out.getvalue()
    >>> big = np.full((4, 6, 4), 255, np.uint8); big[:2, :2, :3] = 0
    >>> out = canvas_frame_png([png(big)], frame=0, factor=2, size=(3, 2))
    >>> np.asarray(Image.open(io.BytesIO(out))).shape
    (2, 3, 3)
    >>> canvas_frame_png([png(big)], frame=9, factor=1, size=(3, 2))
    Traceback (most recent call last):
      ...
    an.stage.canvas_capture.CanvasCaptureError: frame 9: resolved to 6x4, declared 3x2 (supersample 1)
    """
    from PIL import Image

    from an.media.shutter import temporal_mean

    if not samples:
        raise CanvasCaptureError(f"frame {frame}: no samples were captured")
    if compress_level is None:
        compress_level = DEFAULT_PNG_COMPRESS_LEVEL
    if len(samples) == 1 and factor == NO_SUPERSAMPLE:
        # The common case never leaves Pillow: nothing to resolve or average.
        image = opaque_rgb(samples[0], frame=frame)
        _check_size(image.size, size, frame=frame, factor=factor)
        return _encode(image, compress_level)
    import numpy as np

    # Resolved as each sample is decoded, so at most ONE full-size (k-times)
    # canvas is alive at a time, as on the screenshot path. Decoding them all
    # first held samples x k² full frames per frame in flight (review of an#192:
    # 16 GB at supersample 3 with a grain pack).
    resolved = [
        block_mean_resolve(np.asarray(opaque_rgb(png, frame=frame)), factor)
        for png in samples
    ]
    shapes = {r.shape for r in resolved}
    if len(shapes) != 1:
        raise CanvasCaptureError(
            f"frame {frame}: its samples differ in size {sorted(shapes)} — the "
            "canvas was resized mid-frame"
        )
    height, width = resolved[0].shape[:2]
    _check_size((width, height), size, frame=frame, factor=factor)
    return _encode(Image.fromarray(temporal_mean(resolved)), compress_level)


def _check_size(
    got: tuple[int, int], size: tuple[int, int] | None, *, frame: int, factor: int
) -> None:
    if size is not None and tuple(got) != tuple(size):
        raise CanvasCaptureError(
            f"frame {frame}: resolved to {got[0]}x{got[1]}, declared "
            f"{size[0]}x{size[1]} (supersample {factor})"
        )


def _encode(image: Any, compress_level: int) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG", compress_level=compress_level)
    return out.getvalue()
