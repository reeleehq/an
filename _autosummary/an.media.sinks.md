# an.media.sinks

Frame sinks: a frame directory in, one deliverable out – one sink per format.

A sink reads the frame directory the frame stage writes ([`an.media.frames`](an.media.frames.md#module-an.media.frames):
one PNG per output frame, at the declared size) and writes one deliverable. It
knows nothing about what drew the frames, so a stage render, a Manim shot’s
frames or a `burns` crop sequence go through the same three:

| name   | what it writes                                                                                             | knobs            |
|--------|------------------------------------------------------------------------------------------------------------|------------------|
| `mp4`  | H.264, the pinned argv ([`an.media.mp4`](an.media.mp4.md#module-an.media.mp4)) | `pix_fmt`        |
| `gif`  | the one palette recipe ([`an.media.gif`](an.media.gif.md#module-an.media.gif)) | `crop`, `fps`, … |
| `png`  | the frames themselves, copied to a directory                                                               | –                |

New formats register by name ([`register_sink()`](#an.media.sinks.register_sink)) – a WebM sink, say –
without editing this module. Browser-side sinks (WebCodecs) belong to the
TypeScript side (`previz`) and are not duplicated here (core study §2.8).

```pycon
>>> sorted(sink_names())
['gif', 'mp4', 'png']
>>> get_sink("gif", crop="10:10:0:0").crop
'10:10:0:0'
```

### Functions

| [`get_sink`](#an.media.sinks.get_sink)(name, \*\*knobs)                   | A sink by name, built with `knobs`; the error lists what exists.   |
|----------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| [`register_sink`](#an.media.sinks.register_sink)(name, factory, \*[, replace]) | Register a sink factory under `name`; refuse a silent replacement. |
| [`sink_names`](#an.media.sinks.sink_names)()                                | The registered sink names.                                         |

### Classes

| [`FrameSink`](#an.media.sinks.FrameSink)(\*args, \*\*kwargs)                 | Writes a frame directory as one deliverable.                                                                                                         |
|------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`GifSink`](#an.media.sinks.GifSink)([crop, fps, width, max_colours, ...]) | The demo gallery's palette recipe.                                                                                                                   |
| [`Mp4Sink`](#an.media.sinks.Mp4Sink)([pix_fmt, name, suffix])              | The silent picture mux (the shot's audio is laid by [`an.media.mp4.mux_shot()`](an.media.mp4.md#an.media.mp4.mux_shot)). |
| [`PngSequenceSink`](#an.media.sinks.PngSequenceSink)([name, suffix])               | The frames themselves, renumbered from 0 into `output` (a directory).                                                                                |

### *class* an.media.sinks.FrameSink(\*args, \*\*kwargs)

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

### *class* an.media.sinks.GifSink(crop='', fps=12, width=480, max_colours=128, name='gif', suffix='.gif')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The demo gallery’s palette recipe.

### *class* an.media.sinks.Mp4Sink(pix_fmt=None, name='mp4', suffix='.mp4')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The silent picture mux (the shot’s audio is laid by [`an.media.mp4.mux_shot()`](an.media.mp4.md#an.media.mp4.mux_shot)).

`pix_fmt=None` is the module default AT CALL TIME, the seam the bench pulls.

### *class* an.media.sinks.PngSequenceSink(name='png', suffix='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The frames themselves, renumbered from 0 into `output` (a directory).

```pycon
>>> import tempfile
>>> src, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "seq"
>>> _ = frame_path(src, 0).write_bytes(b"png")
>>> sorted(p.name for p in PngSequenceSink().write(src, out, fps=24).iterdir())
['frame_000000.png']
```

### an.media.sinks.get_sink(name, \*\*knobs)

A sink by name, built with `knobs`; the error lists what exists.

* **Return type:**
  [`FrameSink`](#an.media.sinks.FrameSink)

### an.media.sinks.register_sink(name, factory, , replace=False)

Register a sink factory under `name`; refuse a silent replacement.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.media.sinks.sink_names()

The registered sink names.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
