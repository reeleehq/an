# an.adapters.cutout.canvas_capture

The canvas capture path: frames read from the page, not photographed off the screen.

The screenshot capture (`render._capture_frames`, `capture="screenshot"`, the
default until an#192) asks Playwright for an ELEMENT screenshot of `#stage` on
every frame. That is a page
capture clipped to the element, taken from the compositor, and it is the largest
single cost in the frame path — ~100 ms/frame at 1080p that is neither the GPU
readback nor the PNG encode (`an-dev-render-pipeline` §8). This path instead
asks the runtime for the canvas’s own pixels (`window.anCaptureFrames` in
`runtime.js`: seek, `app.view.toDataURL('image/png')`), in batches, and does
the rest here.

\*\*It is a different route to the same pixels, and the whole contract is that
nothing downstream can tell.\*\* The frames it writes are RGB PNGs of the declared
size whose DECODED arrays equal the screenshot path’s, so ffmpeg receives the
same frames, the golden gate the same arrays, and the bench the same sizes. The
file bytes differ (a different PNG encoder), which is why the equivalence gate is
on decoded pixels — the same criterion the golden corpus already uses.

The classic traps, and where each one is closed:

- **Row order.** `gl.readPixels` returns rows bottom-up. `toDataURL` returns
  the image top-down, and this path uses `toDataURL` — so there is no flip,
  and adding one is the mutation the equivalence test must catch.
- **Premultiplied alpha.** Not live today: the runtime leaves PixiJS’s
  `backgroundAlpha` at 1, so the WebGL context is created without alpha and
  every pixel measured came back at 255. It becomes live the day a scene gets a
  translucent background — then the premultiplied drawing buffer, the
  un-premultiplied PNG and the screenshot’s composite over the page’s white all
  disagree. So a frame with any pixel below full alpha is REFUSED
  ([`opaque_rgb()`](#an.adapters.cutout.canvas_capture.opaque_rgb)) rather than guessed at: compositing it here would be a
  second implementation of the browser’s blend, equal to it only by luck.
- \*\*Why not `renderer.extract`.\*\* It re-renders the stage into a render
  texture, which is not multisampled — a different picture from the one the
  `antialias: true` backbuffer holds.
- \*\*Why not raw `readPixels` bytes.\*\* Measured at 1920x1080 on an M1 Max:
  moving 8 MB of RGBA per frame across the DevTools protocol costs 830-950
  ms/frame (in-page base64 through `btoa` or `FileReader`), and Playwright’s
  own typed-array serialisation 5.9 s/frame — against ~46 ms/frame for the PNG
  data URL, which is ~45 KB. The PNG *is* the transfer encoding.

Supersampling and the frame clock go through the same arithmetic as the
screenshot path — [`an.adapters.cutout.supersample.block_mean_resolve()`](an.adapters.cutout.supersample.html.md#an.adapters.cutout.supersample.block_mean_resolve) then
[`an.adapters.cutout.shutter.temporal_mean()`](an.adapters.cutout.shutter.html.md#an.adapters.cutout.shutter.temporal_mean) — so a supersampled or blurred
canvas frame is the screenshot path’s frame, not a lookalike.

Nothing in this module touches a browser: it is the pure half, testable offline.
The loop that drives the page (batching, ordering, back-pressure) is
`render._capture_frames_canvas`.

### Module Attributes

| [`DATA_URL_PREFIX`](#an.adapters.cutout.canvas_capture.DATA_URL_PREFIX)   | What `HTMLCanvasElement.toDataURL('image/png')` returns.   |
|--------------------------------------------------------------------|------------------------------------------------------------|

### Functions

| [`canvas_frame_png`](#an.adapters.cutout.canvas_capture.canvas_frame_png)(samples, \*, frame[, ...])   | One output frame's canvas PNGs -> the RGB PNG the screenshot path writes.   |
|------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`decode_data_url`](#an.adapters.cutout.canvas_capture.decode_data_url)(url, \*, frame)               | A `toDataURL('image/png')` result -> the PNG's bytes, or refuse.            |
| [`opaque_rgb`](#an.adapters.cutout.canvas_capture.opaque_rgb)(png, \*, frame)                    | Decode a canvas PNG to an RGB `PIL.Image`, refusing any transparency.       |

### Exceptions

| [`CanvasCaptureError`](#an.adapters.cutout.canvas_capture.CanvasCaptureError)   | A captured frame that cannot be turned into the screenshot path's frame.   |
|-----------------------------------------------------------------------|----------------------------------------------------------------------------|

### *exception* an.adapters.cutout.canvas_capture.CanvasCaptureError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A captured frame that cannot be turned into the screenshot path’s frame.

### an.adapters.cutout.canvas_capture.DATA_URL_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'data:image/png;base64,'*

What `HTMLCanvasElement.toDataURL('image/png')` returns. Anything else —
`"data:,"` for a zero-size canvas, or a JPEG a browser fell back to — is
refused rather than decoded as whatever it happens to be.

### an.adapters.cutout.canvas_capture.canvas_frame_png(samples, , frame, factor=1, size=None, compress_level=None)

One output frame’s canvas PNGs -> the RGB PNG the screenshot path writes.

`samples` are the frame’s instants in capture order (one unless a frame
clock opened the shutter). Each is decoded and refused unless opaque,
resolved by `factor` with the product’s block mean, and the results
averaged with the product’s temporal mean — the arithmetic the screenshot
path runs, so the two agree about every tie. `size` (width, height), when
given, is the DECLARED size the resolved frame must have: a canvas that is
not `factor` times it is refused here, not muxed. `compress_level=None`
reads `DEFAULT_PNG_COMPRESS_LEVEL` at call time.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

```pycon
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
an.adapters.cutout.canvas_capture.CanvasCaptureError: frame 9: resolved to 6x4, declared 3x2 (supersample 1)
```

### an.adapters.cutout.canvas_capture.decode_data_url(url, , frame)

A `toDataURL('image/png')` result -> the PNG’s bytes, or refuse.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

```pycon
>>> decode_data_url(DATA_URL_PREFIX + "iVBORw==", frame=0)[:4]
b'\x89PNG'
>>> decode_data_url("data:,", frame=3)
Traceback (most recent call last):
  ...
an.adapters.cutout.canvas_capture.CanvasCaptureError: frame 3: the canvas returned 'data:,' rather than a PNG data URL — a zero-size canvas does this
```

### an.adapters.cutout.canvas_capture.opaque_rgb(png, , frame)

Decode a canvas PNG to an RGB `PIL.Image`, refusing any transparency.

The screenshot path composites the canvas over the page (white, since
`omit_background=False`); where every pixel has alpha 255 that composite
is the identity, and the premultiplied drawing buffer and the
un-premultiplied PNG agree. Anywhere else the two paths would differ, so the
frame is refused with a count rather than blended here.

Pillow end to end, deliberately: the alpha check is `getextrema` and the
drop is `convert("RGB")`, both in C. Slicing `[..., :3]` out of a numpy
view and copying it contiguous measured ~5x slower at 1080p, on a path whose
whole point is time.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
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
an.adapters.cutout.canvas_capture.CanvasCaptureError: frame 5: 1 of 6 canvas pixels are not opaque (min alpha 128); the screenshot path would composite them over the page's white and this path will not guess at that blend
```
