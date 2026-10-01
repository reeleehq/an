# an.media

Frames to deliverables, engine-independent: the frame stage’s resolves and the sinks.

Core (ADR 0001 decisions 8(a) and 12; core study §2.8 and §5). Nothing here
knows what drew a frame: the stage engine, a Manim shot or a `burns` crop all
hand over PNGs, and everything below is the same for each.

- [`an.media.frames`](an.media.frames.html.md#module-an.media.frames) – the frame directory’s naming (`frame_%06d.png`).
- [`an.media.supersample`](an.media.supersample.html.md#module-an.media.supersample) – the SPATIAL resolve: an exact `k x k` block mean.
- [`an.media.shutter`](an.media.shutter.html.md#module-an.media.shutter) – the TEMPORAL resolve: a frame’s sample instants averaged.
- [`an.media.mp4`](an.media.mp4.html.md#module-an.media.mp4) – the MP4 sink with the pinned argv, plus the shot’s audio mux.
- [`an.media.gif`](an.media.gif.html.md#module-an.media.gif) – the GIF sink’s one palette recipe.
- [`an.media.sinks`](an.media.sinks.html.md#module-an.media.sinks) – the `FrameSink` protocol and the name-keyed sink registry.

Moved out of `an/adapters/cutout/` and `misc/demos/build_demos.py` in an#247;
the old paths re-export (and the module globals the bench rebinds stay LIVE at
the old paths, see `an._shims`). Film assembly (`an.assemble`) consumes
these sinks’ output and stays where it is.

```pycon
>>> from an.media import get_sink
>>> get_sink("mp4").suffix
'.mp4'
```

### Functions

| [`block_mean_resolve`](#an.media.block_mean_resolve)(frame, factor)           | `(H*k, W*k, C)` uint8 -> `(H, W, C)` uint8, by an exact `k x k` mean.       |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`check_factor`](#an.media.check_factor)(factor)                        | Validate a supersample factor, or refuse with the reason.                   |
| [`check_frame_samples`](#an.media.check_frame_samples)(frame_samples, \*, ...) | Validate `frame_samples` against the render it is for; normalise to tuples. |
| [`frame_path`](#an.media.frame_path)(frames_dir, index)               | Where frame `index` lives in `frames_dir`.                                  |
| [`get_sink`](#an.media.get_sink)(name, \*\*knobs)                   | A sink by name, built with `knobs`; the error lists what exists.            |
| [`mean_png_bytes`](#an.media.mean_png_bytes)(shots, \*, factor)           | Spatially resolve each screenshot by `factor`, then average them in time.   |
| [`missing_frames`](#an.media.missing_frames)(frames_dir, total_frames)    | The frame indices in `[0, total_frames)` that have no file on disk.         |
| [`register_sink`](#an.media.register_sink)(name, factory, \*[, replace]) | Register a sink factory under `name`; refuse a silent replacement.          |
| [`sink_names`](#an.media.sink_names)()                                | The registered sink names.                                                  |
| [`temporal_mean`](#an.media.temporal_mean)(frames)                       | `k` equal-shape uint8 frames -> their exact per-pixel mean, uint8.          |

### Classes

| [`FrameSink`](#an.media.FrameSink)(\*args, \*\*kwargs)                 | Writes a frame directory as one deliverable.                                                                                                         |
|------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`GifSink`](#an.media.GifSink)([crop, fps, width, max_colours, ...]) | The demo gallery's palette recipe.                                                                                                                   |
| [`Mp4Sink`](#an.media.Mp4Sink)([pix_fmt, name, suffix])              | The silent picture mux (the shot's audio is laid by [`an.media.mp4.mux_shot()`](an.media.mp4.html.md#an.media.mp4.mux_shot)). |
| [`PngSequenceSink`](#an.media.PngSequenceSink)([name, suffix])               | The frames themselves, renumbered from 0 into `output` (a directory).                                                                                |

### Exceptions

| [`MediaError`](#an.media.MediaError)   | A sink could not write what it was asked to.   |
|---------------------------------------------------------------|------------------------------------------------|

### *class* an.media.FrameSink(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Writes a frame directory as one deliverable.

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The registry name, and the format’s usual name.

#### suffix *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The deliverable’s suffix (`".mp4"`), or `""` for a directory.

#### write(frames_dir, output, , fps)

Write `frames_dir` (rendered at `fps`) to `output`; return it.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### *class* an.media.GifSink(crop='', fps=12, width=480, max_colours=128, name='gif', suffix='.gif')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The demo gallery’s palette recipe.

### *exception* an.media.MediaError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A sink could not write what it was asked to. Carries actionable detail.

A renderer re-raises it as its own typed error at its boundary
(`frame_stage_renderer(..., error=...)`), so a cut-out render still fails
with `CutoutRenderError`.

### *class* an.media.Mp4Sink(pix_fmt=None, name='mp4', suffix='.mp4')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The silent picture mux (the shot’s audio is laid by [`an.media.mp4.mux_shot()`](an.media.mp4.html.md#an.media.mp4.mux_shot)).

`pix_fmt=None` is the module default AT CALL TIME, the seam the bench pulls.

### *class* an.media.PngSequenceSink(name='png', suffix='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The frames themselves, renumbered from 0 into `output` (a directory).

```pycon
>>> import tempfile
>>> src, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "seq"
>>> _ = frame_path(src, 0).write_bytes(b"png")
>>> sorted(p.name for p in PngSequenceSink().write(src, out, fps=24).iterdir())
['frame_000000.png']
```

### an.media.block_mean_resolve(frame, factor)

`(H*k, W*k, C)` uint8 -> `(H, W, C)` uint8, by an exact `k x k` mean.

Two-step, summing rows and then columns in `uint16`, rather than the
obvious `reshape(...).astype(float64).mean(axis=(1, 3))`. The two agree
**bit for bit** — asserted exhaustively over every possible 2x2 block, and
on real frames — and the two-step form is 2.3x faster at 1080p (111.7 ms
against 262.0 ms), because the cost here is the strided reduce and the
64-bit temporary, not the arithmetic.

Rounding is spelled out rather than inherited: `np.rint` is banker’s
rounding, so a block averaging exactly `.5` goes to the EVEN neighbour.
Getting that wrong changes one code value on every half-block, which is
invisible in a picture and moves every golden.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> f = np.array([[0, 0, 1, 2], [0, 4, 1, 2]], np.uint8)[..., None].repeat(3, -1)
>>> block_mean_resolve(f, 2)[0, :, 0].tolist()
[1, 2]
>>> block_mean_resolve(f, 1) is f
True
```

### an.media.check_factor(factor)

Validate a supersample factor, or refuse with the reason.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> check_factor(1), check_factor(2)
(1, 2)
>>> check_factor(0)
Traceback (most recent call last):
  ...
an.media.supersample.SupersampleError: supersample must be >= 1, got 0
```

### an.media.check_frame_samples(frame_samples, , total_frames, duration)

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

### an.media.frame_path(frames_dir, index)

Where frame `index` lives in `frames_dir`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.media.get_sink(name, \*\*knobs)

A sink by name, built with `knobs`; the error lists what exists.

* **Return type:**
  [`FrameSink`](an.media.sinks.html.md#an.media.sinks.FrameSink)

### an.media.mean_png_bytes(shots, , factor)

Spatially resolve each screenshot by `factor`, then average them in time.

One screenshot takes exactly the spatial path — the same bytes a render
without a shutter writes.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.media.missing_frames(frames_dir, total_frames)

The frame indices in `[0, total_frames)` that have no file on disk.

Checked on DISK rather than on a capture loop’s bookkeeping, because the
mux reads the directory: the directory is what must hold every frame.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]

```pycon
>>> import tempfile
>>> d = Path(tempfile.mkdtemp())
>>> _ = frame_path(d, 0).write_bytes(b"")
>>> missing_frames(d, 3)
[1, 2]
```

### an.media.register_sink(name, factory, , replace=False)

Register a sink factory under `name`; refuse a silent replacement.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.media.sink_names()

The registered sink names.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.media.temporal_mean(frames)

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

### Modules

| [`frames`](an.media.frames.html.md#module-an.media.frames)           | The frame directory every engine writes and every sink reads.                  |
|------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`gif`](an.media.gif.html.md#module-an.media.gif)                 | The GIF sink: ONE palette recipe, for flat 2D art.                             |
| [`mp4`](an.media.mp4.html.md#module-an.media.mp4)                 | The MP4 sink: PNG frames -> the delivered H.264 mp4, with the pinned argv.     |
| [`shutter`](an.media.shutter.html.md#module-an.media.shutter)         | The temporal half of the frame stage: average several instants into one frame. |
| [`sinks`](an.media.sinks.html.md#module-an.media.sinks)             | Frame sinks: a frame directory in, one deliverable out -- one sink per format. |
| [`supersample`](an.media.supersample.html.md#module-an.media.supersample) | Render bigger, then resolve back exactly — the supersample knob's two halves.  |
