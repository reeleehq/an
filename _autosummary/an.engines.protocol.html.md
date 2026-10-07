# an.engines.protocol

The `Engine` protocol: a seekable thing that turns a time, or a state, into a frame.

The second of the three renderer tiers (ADR 0001 decision 12; core study §2.7):

1. `Renderer` (`an.adapters._base`) – shot in, media file out. Every back-end
   is reachable through it; Manim lives there, whole-shot.
2. **\`\`Engine\`\`** (this module) – `previz`’s meaning of the word: something
   that can show the scene at any instant and hand over the pixels. The core
   turns any engine into a `Renderer` with [`an.engines.frame_stage_renderer()`](an.engines.html.md#an.engines.frame_stage_renderer),
   which owns the clock, the capture loop, supersampling, the shutter and the
   sinks, so an engine implements none of them.
3. `LiveEngine` – apply, settle, capture in real time (`walkthru`’s recorder).
   **Declared, not built.**

**Capabilities are read from which members exist, never from a flag**
(`previz`’s rule, ADR 0002 applied to engines), so a flag can never disagree
with the code. [`describe()`](#an.engines.protocol.describe) is the one place that reads them.

An `Engine` is a stateless factory, safe to share across the threads of a
parallel render. [`Engine.open()`](#an.engines.protocol.Engine.open) loads one shot and yields a **session**:
the loaded, seekable view, whose members say what it can do.

And on the `Engine` itself: `check(ctx)` validates the engine’s own knobs
before anything launches (a typo must fail in microseconds, not after a browser
started).

```pycon
>>> class _Still:
...     def frame(self, t): return b"png"
...     def state(self, t): return {}
>>> describe(_Still())
EngineProfile(tier='seekable', drive='time', features=frozenset({'readback'}))
>>> class _Crop:
...     timeline = None
...     def render(self, state): return b"png"
>>> describe(_Crop()).drive
'state'
```

### Module Attributes

| [`DRIVE_TIME`](#an.engines.protocol.DRIVE_TIME)      | who evaluates the timeline.                                       |
|------------------------------------------------------------------|-------------------------------------------------------------------|
| [`TIER_SEEKABLE`](#an.engines.protocol.TIER_SEEKABLE)   | Tiers an engine can be on (the `Renderer` tier is not an engine). |
| [`FEATURE_MEMBERS`](#an.engines.protocol.FEATURE_MEMBERS) | Optional session member -> the feature it unlocks.                |

### Functions

| [`describe`](#an.engines.protocol.describe)(session)           | The tier, drive mode and features a session (or a session class) offers.   |
|------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`drive_mode`](#an.engines.protocol.drive_mode)(session)         | `"time"`, `"state"`, or `None` for a session the frame stage cannot drive. |
| [`require_seekable`](#an.engines.protocol.require_seekable)(session)   | The session's drive mode, or a refusal that says what to add.              |
| [`requests_as_dicts`](#an.engines.protocol.requests_as_dicts)(requests) | Requests as plain dicts, the shape a page or a subprocess takes.           |

### Classes

| [`Engine`](#an.engines.protocol.Engine)(\*args, \*\*kwargs)                      | A stateless factory of loaded, seekable sessions -- one per shot render.   |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`EngineProfile`](#an.engines.protocol.EngineProfile)(tier, drive, features)            | What a session can do, read off its members.                               |
| [`FrameJob`](#an.engines.protocol.FrameJob)(shot, ctx, workspace, frames_dir, ...) | What the frame stage asks of an engine for one shot.                       |
| [`FrameRequest`](#an.engines.protocol.FrameRequest)(frame, times)                      | One output frame's instants, in the order they must be captured.           |
| [`LiveEngine`](#an.engines.protocol.LiveEngine)(\*args, \*\*kwargs)                  | The live tier: apply, settle, capture in real time.                        |
| [`StateDriven`](#an.engines.protocol.StateDriven)(\*args, \*\*kwargs)                 | A session the core hands states to.                                        |
| [`TimeDriven`](#an.engines.protocol.TimeDriven)(\*args, \*\*kwargs)                  | A session that evaluates the compiled channels itself.                     |

### Exceptions

| [`UnseekableEngineError`](#an.engines.protocol.UnseekableEngineError)   | A session that the frame stage cannot drive; the message says what to add.   |
|--------------------------------------------------------------------------|------------------------------------------------------------------------------|

### an.engines.protocol.DRIVE_TIME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'time'*

who evaluates the timeline.

* **Type:**
  Drive modes (core study §2.7)

### *class* an.engines.protocol.Engine(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

A stateless factory of loaded, seekable sessions – one per shot render.

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The engine’s name (`"stage"`); also how provenance names it.

#### open(job)

Load `job.shot` and yield a session (see the module table).

* **Return type:**
  [`AbstractContextManager`](https://docs.python.org/3/library/contextlib.html#contextlib.AbstractContextManager)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *class* an.engines.protocol.EngineProfile(tier, drive, features)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a session can do, read off its members.

### an.engines.protocol.FEATURE_MEMBERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'bounds': 'bounds', 'frame_with_alpha': 'alpha', 'frames': 'batch', 'project': 'project', 'provenance': 'provenance', 'render_states': 'batch', 'resolve': 'resolve', 'state': 'readback'}*

Optional session member -> the feature it unlocks. The SSOT [`describe()`](#an.engines.protocol.describe)
reads; a new feature is a new row, never a flag on an engine.

### *class* an.engines.protocol.FrameJob(shot, ctx, workspace, frames_dir, total_frames, supersample, frame_samples=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What the frame stage asks of an engine for one shot.

Built by the core, before [`Engine.open()`](#an.engines.protocol.Engine.open): every knob here is already
validated, so an engine never re-derives the frame count or the factor.

#### frame_samples *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), ...], ...] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per frame, the instants to capture and average, or `None` for one
instant at `i / fps`.

#### requests()

Every frame’s request, frame `i` at `i / fps` unless a clock says otherwise.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`FrameRequest`](#an.engines.protocol.FrameRequest), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> from types import SimpleNamespace
>>> job = FrameJob(None, SimpleNamespace(fps=4, resolution=(2, 2)), Path("."),
...                Path("."), total_frames=3, supersample=1)
>>> [r.times for r in job.requests()]
[(0.0,), (0.25,), (0.5,)]
```

#### *property* size *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)]*

what every resolved frame must be.

* **Type:**
  The DECLARED ([*width*](an.stage.paths.html.md#an.stage.paths.PathDescriptor.width), height)

#### supersample *: [int](https://docs.python.org/3/builtins/functions.html#int)*

the engine draws at `k` times the
declared size, and the core resolves back to it.

* **Type:**
  The validated supersample factor

#### workspace *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

The shot’s own scratch directory (`<work_dir>/shot_<id>`). The engine
may stage files in it (the stage engine’s runtime copy); the core owns
`frames/` and the delivered mp4 inside it.

### *class* an.engines.protocol.FrameRequest(frame, times)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One output frame’s instants, in the order they must be captured.

One instant unless a frame clock opened the shutter
(`RenderContext.frame_samples`).

### *class* an.engines.protocol.LiveEngine(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

The live tier: apply, settle, capture in real time. **Declared, not built.**

Its recorder resamples to a constant rate (`walkthru`’s worked example);
`frame_stage_renderer` does not drive it, and never falls back to it.

### *class* an.engines.protocol.StateDriven(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

A session the core hands states to.

#### render(state)

PNG bytes of `state` (`supersample` times the declared size).

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

#### timeline *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)*

The `an.timing` `Timeline` the core evaluates.

### an.engines.protocol.TIER_SEEKABLE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'seekable'*

Tiers an engine can be on (the `Renderer` tier is not an engine).

### *class* an.engines.protocol.TimeDriven(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

A session that evaluates the compiled channels itself.

#### frame(t)

The scene at `t` as PNG bytes (`supersample` times the declared size).

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

#### state(t)

The state the engine evaluated at `t`: a sparse pose, absent = at rest.

* **Return type:**
  [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *exception* an.engines.protocol.UnseekableEngineError

Bases: [`TypeError`](https://docs.python.org/3/builtins/exceptions.html#TypeError)

A session that the frame stage cannot drive; the message says what to add.

### an.engines.protocol.describe(session)

The tier, drive mode and features a session (or a session class) offers.

* **Return type:**
  [`EngineProfile`](#an.engines.protocol.EngineProfile)

### an.engines.protocol.drive_mode(session)

`"time"`, `"state"`, or `None` for a session the frame stage cannot drive.

A session with both `frame` and `render` is time-driven: it evaluates
its own document, and the core does not second-guess it.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.engines.protocol.requests_as_dicts(requests)

Requests as plain dicts, the shape a page or a subprocess takes.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.engines.protocol.require_seekable(session)

The session’s drive mode, or a refusal that says what to add.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> require_seekable(object())
Traceback (most recent call last):
  ...
an.engines.protocol.UnseekableEngineError: this engine session cannot be captured: it has no frame(t) (time-driven), and no render(state) with a timeline (state-driven). Add frame(t) and state(t) if the engine evaluates the timeline itself, or timeline and render(state) if the core should evaluate it.
```
