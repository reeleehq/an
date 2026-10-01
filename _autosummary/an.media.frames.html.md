# an.media.frames

The frame directory every engine writes and every sink reads.

One PNG per output frame, named by [`DEFAULT_FRAME_PNG_PATTERN`](#an.media.frames.DEFAULT_FRAME_PNG_PATTERN), at the
DECLARED size: the frame stage (`an.engines.capture`) resolves supersampling
and the open shutter before a file is written, so nothing downstream ever reads
a resolution off a file or averages anything. The bench, the golden gate, film
assembly and every sink rely on exactly that.

Moved from `an/adapters/cutout/render.py` (an#247); the old name still reads
from here.

```pycon
>>> from pathlib import Path
>>> frame_path(Path("frames"), 7).name
'frame_000007.png'
```

### Module Attributes

| [`DEFAULT_FRAME_PNG_PATTERN`](#an.media.frames.DEFAULT_FRAME_PNG_PATTERN)   | The printf pattern of a frame file.   |
|------------------------------------------------------------------------------|---------------------------------------|

### Functions

| [`frame_path`](#an.media.frames.frame_path)(frames_dir, index)            | Where frame `index` lives in `frames_dir`.                          |
|-------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`missing_frames`](#an.media.frames.missing_frames)(frames_dir, total_frames) | The frame indices in `[0, total_frames)` that have no file on disk. |

### an.media.frames.DEFAULT_FRAME_PNG_PATTERN *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'frame_%06d.png'*

The printf pattern of a frame file. ffmpeg reads the same pattern, so a
rename here is a rename of every mux’s input argument too.

### an.media.frames.frame_path(frames_dir, index)

Where frame `index` lives in `frames_dir`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.media.frames.missing_frames(frames_dir, total_frames)

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
