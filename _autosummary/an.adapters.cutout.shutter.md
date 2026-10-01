# an.adapters.cutout.shutter

Moved to [`an.media.shutter`](an.media.shutter.md#module-an.media.shutter) (an#247); this path re-exports it.

The temporal resolve is engine-independent, so it lives in the core’s media
package. Every name below is the same object as in its new home.

### Functions

| [`check_frame_samples`](#an.adapters.cutout.shutter.check_frame_samples)(frame_samples, \*, ...)   | Validate `frame_samples` against the render it is for; normalise to tuples.   |
|------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`mean_png_bytes`](#an.adapters.cutout.shutter.mean_png_bytes)(shots, \*, factor)             | Spatially resolve each screenshot by `factor`, then average them in time.     |
| [`temporal_mean`](#an.adapters.cutout.shutter.temporal_mean)(frames)                         | `k` equal-shape uint8 frames -> their exact per-pixel mean, uint8.            |

### Exceptions

| [`ShutterError`](#an.adapters.cutout.shutter.ShutterError)   | Frame samples a render cannot honour.   |
|-----------------------------------------------------------------|-----------------------------------------|

### *exception* an.adapters.cutout.shutter.ShutterError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

Frame samples a render cannot honour.

### an.adapters.cutout.shutter.check_frame_samples(frame_samples, , total_frames, duration)

Validate `frame_samples` against the render it is for; normalise to tuples.

Checked before a browser launches, for `check_factor`’s reason: the render
costs minutes and this costs microseconds.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)], [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> check_frame_samples(None, total_frames=3, duration=0.1) is None
True
>>> check_frame_samples([[0.0], [0.5, 0.6]], total_frames=2, duration=1.0)
((0.0,), (0.5, 0.6))
>>> check_frame_samples([[0.0]], total_frames=2, duration=1.0)
Traceback (most recent call last):
  ...
an.media.shutter.ShutterError: frame_samples has 1 frame(s) but this render has 2; a frame clock must describe every frame, and only those
```

### an.adapters.cutout.shutter.mean_png_bytes(shots, , factor)

Spatially resolve each screenshot by `factor`, then average them in time.

One screenshot takes exactly the spatial path — the same bytes a render
without a shutter writes.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.adapters.cutout.shutter.temporal_mean(frames)

`k` equal-shape uint8 frames -> their exact per-pixel mean, uint8.

Rounded half-to-even, the rule `block_mean_resolve` spells out, so the
temporal and spatial resolves agree about every tie. The mean is of the
ENCODED (sRGB) values, as the spatial resolve’s is — not of linear light, so
a smear’s profile is not exactly a physical sensor’s. The centroid of what
is drawn is still the average of the sampled positions, which is the
property the impact ground truth relies on.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> a, b = np.full((1, 2, 3), 1, np.uint8), np.full((1, 2, 3), 2, np.uint8)
>>> temporal_mean([a, b])[0, 0].tolist()   # 1.5 -> 2 (even)
[2, 2, 2]
>>> temporal_mean([a, a + 2])[0, 0].tolist()   # 2.0 exactly
[2, 2, 2]
>>> temporal_mean([a]) is a
True
```
