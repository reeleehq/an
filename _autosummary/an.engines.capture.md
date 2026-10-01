# an.engines.capture

The capture loop: drive a session through every frame, resolve, write – for ANY engine.

Moved out of the stage renderer (`an/adapters/cutout/render.py`’s
`_capture_frames` and `_capture_frames_canvas`, an#247) and generalised over
the session members of [`an.engines.protocol`](an.engines.protocol.md#module-an.engines.protocol). The algorithms are the ones
the stage shipped, unchanged, because the decoded frames are the contract (the
golden corpus and the canvas equivalence gate compare them):

- **Sequential** (a session without `frames`): per frame, `frame(t)` for each
  instant; a frame of ONE instant at supersample 1 with no `resolve` member is
  written as the engine’s own bytes – nothing decoded, so **off is free** –
  and anything else goes through the resolve.
- **Batched** (a session with `frames(requests)`): the requests go out in frame
  order, samples in the order given, at most `batch` frames and
  `batch_pixels` captured pixels per round trip (a frame whose instants alone
  exceed it is split over round trips and resolved once); the resolve runs on a
  small thread pool while the engine draws the next batch, with BACK-PRESSURE –
  at most `max_inflight` frames (and twice the pixel budget) wait on the pool,
  after which the loop blocks on the oldest before asking for more.

**The resolve runs here, in the frame stage, before a file is written**:
supersampling ([`an.media.supersample`](an.media.supersample.md#module-an.media.supersample), an exact block mean) and the open
shutter ([`an.media.shutter`](an.media.shutter.md#module-an.media.shutter), an exact temporal mean). Nothing downstream
reads a resolution off a file or averages anything; an ffmpeg `-vf scale` is
refused for the reasons in `an-dev-render-pipeline` §2. A session’s own
`resolve` member replaces the default resolve (the stage’s canvas session
refuses non-opaque pixels there); the default is
[`an.media.shutter.mean_png_bytes()`](an.media.shutter.md#an.media.shutter.mean_png_bytes).

Two corruptions are silent unless refused, so both are refused: a dropped or
reordered frame (every file is named by its frame number, and every frame
`0..N-1` must exist on disk before the loop returns), and unbounded buffering
(the bounds above).

\*\*The bench’s `supersample` lever rebinds\*\* [`capture_frames()`](#an.engines.capture.capture_frames) \*\*on this
module\*\* to force the product’s own factor, so [`an.engines.frame_stage`](an.engines.frame_stage.md#module-an.engines.frame_stage)
calls it as a module attribute, at call time.

### Module Attributes

| [`DEFAULT_BATCH`](#an.engines.capture.DEFAULT_BATCH)          | Frames per round trip of a batched session.                                                                                              |
|-------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| [`DEFAULT_ENCODE_WORKERS`](#an.engines.capture.DEFAULT_ENCODE_WORKERS) | Threads resolving and encoding frames while the engine draws the next batch.                                                             |
| [`DEFAULT_BATCH_PIXELS`](#an.engines.capture.DEFAULT_BATCH_PIXELS)   | a supersample counts k² times, an open shutter once per instant): at most this many per round trip, twice this many waiting on the pool. |
| [`DEFAULT_MAX_INFLIGHT`](#an.engines.capture.DEFAULT_MAX_INFLIGHT)   | frames handed to the pool and not yet written.                                                                                           |

### Functions

| [`capture_frames`](#an.engines.capture.capture_frames)(session, requests, frames_dir, \*)   | Write one PNG per request into `frames_dir`, resolved to the declared size.   |
|------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`default_resolve`](#an.engines.capture.default_resolve)(samples, \*, frame, factor, size)   | The core's resolve: spatially by `factor`, then the instants in time.         |

### Exceptions

| [`FrameStageError`](#an.engines.capture.FrameStageError)   | The frame stage could not produce a frame directory it can vouch for.   |
|--------------------------------------------------------------------|-------------------------------------------------------------------------|

### an.engines.capture.DEFAULT_BATCH *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 8*

Frames per round trip of a batched session. Measured on the stage at
1920x1080 on an M1 Max: 67 ms/frame one frame per call, 46 at four, 46 at
eight – the round trip is ~20 ms of fixed cost, amortised by the batch.

### an.engines.capture.DEFAULT_BATCH_PIXELS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 4147200*

a supersample
counts k² times, an open shutter once per instant): at most this many per
round trip, twice this many waiting on the pool. A frame COUNT bounds nothing
when a frame is a k-times, many-sample, incompressible canvas (an#192 review:
one reply overflowed the driver’s string limit and the render hung).

* **Type:**
  The same two bounds in CAPTURED PIXELS (backbuffer pixels

### an.engines.capture.DEFAULT_ENCODE_WORKERS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

Threads resolving and encoding frames while the engine draws the next batch.
The stage’s decode/encode is ~60 ms/frame of Pillow at 1080p, the same order
as the page’s own work, so it must overlap it. Two, not `cpu_count()`: a
parallel render already runs one engine per shot.

### an.engines.capture.DEFAULT_MAX_INFLIGHT *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 16*

frames handed to the pool and not yet written.

* **Type:**
  BACK-PRESSURE

### *exception* an.engines.capture.FrameStageError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The frame stage could not produce a frame directory it can vouch for.

A renderer built by `frame_stage_renderer(..., error=...)` re-raises it as
its own typed error at its boundary.

### an.engines.capture.capture_frames(session, requests, frames_dir, , factor=1, size=None, batch=None, workers=None, max_inflight=None, batch_pixels=None)

Write one PNG per request into `frames_dir`, resolved to the declared size.

`session` is time-driven (`frame(t)`), optionally batched
(`frames(requests)`), optionally with its own `resolve`. A state-driven
session is adapted by the frame stage before it reaches here. `size`, when
known, sets the pixel budget and is passed to the resolve. `None` for any
tunable reads the module default at call time.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.engines.capture.default_resolve(samples, , frame, factor, size)

The core’s resolve: spatially by `factor`, then the instants in time.

One sample at factor 1 is returned as is – the engine’s own bytes.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)
