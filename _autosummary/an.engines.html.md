# an.engines

Engines: seekable things the core drives frame by frame, and the renderer that drives them.

Core (ADR 0001 decision 12; core study §2.7). No engine is core: the core holds
the PROTOCOL and the frame stage, and an engine – the 2D stage runtime, a
`previz` view behind a page, a `burns` crop over a still – lives in its own
package and registers the renderer [`frame_stage_renderer()`](#an.engines.frame_stage_renderer) builds from it.

- [`an.engines.protocol`](an.engines.protocol.html.md#module-an.engines.protocol) – `Engine` (a factory that opens a session per
  shot), the time-driven and state-driven session protocols, the declared live
  tier, and [`describe()`](#an.engines.describe), which reads a session’s tier, drive mode and
  features off the members it implements (never off a flag).
- [`an.engines.capture`](an.engines.capture.html.md#module-an.engines.capture) – the capture loop, sequential or batched, with the
  frame stage’s resolves (supersample, shutter).
- [`an.engines.frame_stage`](an.engines.frame_stage.html.md#module-an.engines.frame_stage) – [`frame_stage_renderer()`](#an.engines.frame_stage_renderer): an engine in, a
  `Renderer` out, using the core’s frame clock, capture loop, resolves and MP4
  sink ([`an.media`](an.media.html.md#module-an.media)).

```pycon
>>> from contextlib import contextmanager
>>> class Blank:
...     name = "blank"
...     @contextmanager
...     def open(self, job):
...         yield self
...     def frame(self, t): return b""
...     def state(self, t): return {}
>>> describe(Blank()).drive, frame_stage_renderer(Blank()).name
('time', 'blank')
```

### Functions

| [`capture_frames`](#an.engines.capture_frames)(session, requests, frames_dir, \*)   | Write one PNG per request into `frames_dir`, resolved to the declared size.          |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`describe`](#an.engines.describe)(session)                                   | The tier, drive mode and features a session (or a session class) offers.             |
| [`drive_mode`](#an.engines.drive_mode)(session)                                 | `"time"`, `"state"`, or `None` for a session the frame stage cannot drive.           |
| [`frame_stage_renderer`](#an.engines.frame_stage_renderer)(engine, \*[, name, ...])       | Turn `engine` into a `Renderer`: the core's clock, capture loop, resolves and sinks. |
| [`require_engine`](#an.engines.require_engine)(engine)                              | Refuse an object that is not an engine, saying what is missing.                      |
| [`require_seekable`](#an.engines.require_seekable)(session)                           | The session's drive mode, or a refusal that says what to add.                        |
| [`requests_as_dicts`](#an.engines.requests_as_dicts)(requests)                         | Requests as plain dicts, the shape a page or a subprocess takes.                     |
| [`shot_workspace`](#an.engines.shot_workspace)(work_dir, shot_id)                   | `<work_dir>/shot_<id>`: the one per-shot scratch directory.                          |

### Classes

| [`Engine`](#an.engines.Engine)(\*args, \*\*kwargs)                      | A stateless factory of loaded, seekable sessions -- one per shot render.                                                       |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| [`EngineProfile`](#an.engines.EngineProfile)(tier, drive, features)            | What a session can do, read off its members.                                                                                   |
| [`FrameJob`](#an.engines.FrameJob)(shot, ctx, workspace, frames_dir, ...) | What the frame stage asks of an engine for one shot.                                                                           |
| [`FrameRequest`](#an.engines.FrameRequest)(frame, times)                      | One output frame's instants, in the order they must be captured.                                                               |
| [`FrameStageRenderer`](#an.engines.FrameStageRenderer)(engine[, name, ...])         | A `Renderer` that drives an [`Engine`](an.engines.protocol.html.md#an.engines.protocol.Engine) frame by frame. |
| [`LiveEngine`](#an.engines.LiveEngine)(\*args, \*\*kwargs)                  | The live tier: apply, settle, capture in real time.                                                                            |
| [`StateDriven`](#an.engines.StateDriven)(\*args, \*\*kwargs)                 | A session the core hands states to.                                                                                            |
| [`StateDrivenAdapter`](#an.engines.StateDrivenAdapter)(session)                     | A state-driven session seen as a time-driven one: the core evaluates `at(t)`.                                                  |
| [`TimeDriven`](#an.engines.TimeDriven)(\*args, \*\*kwargs)                  | A session that evaluates the compiled channels itself.                                                                         |

### Exceptions

| [`FrameStageError`](#an.engines.FrameStageError)       | The frame stage could not produce a frame directory it can vouch for.      |
|------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`UnseekableEngineError`](#an.engines.UnseekableEngineError) | A session that the frame stage cannot drive; the message says what to add. |

### *class* an.engines.Engine(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

A stateless factory of loaded, seekable sessions – one per shot render.

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The engine’s name (`"stage"`); also how provenance names it.

#### open(job)

Load `job.shot` and yield a session (see the module table).

* **Return type:**
  [`AbstractContextManager`](https://docs.python.org/3/library/contextlib.html#contextlib.AbstractContextManager)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *class* an.engines.EngineProfile(tier, drive, features)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a session can do, read off its members.

### *class* an.engines.FrameJob(shot, ctx, workspace, frames_dir, total_frames, supersample, frame_samples=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What the frame stage asks of an engine for one shot.

Built by the core, before [`Engine.open()`](#an.engines.Engine.open): every knob here is already
validated, so an engine never re-derives the frame count or the factor.

#### frame_samples *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), ...], ...] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per frame, the instants to capture and average, or `None` for one
instant at `i / fps`.

#### requests()

Every frame’s request, frame `i` at `i / fps` unless a clock says otherwise.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`FrameRequest`](an.engines.protocol.html.md#an.engines.protocol.FrameRequest), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

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
  The DECLARED ([*width*](an.characters.html.md#an.characters.Attachment.width), height)

#### supersample *: [int](https://docs.python.org/3/builtins/functions.html#int)*

the engine draws at `k` times the
declared size, and the core resolves back to it.

* **Type:**
  The validated supersample factor

#### workspace *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

The shot’s own scratch directory (`<work_dir>/shot_<id>`). The engine
may stage files in it (the stage engine’s runtime copy); the core owns
`frames/` and the delivered mp4 inside it.

### *class* an.engines.FrameRequest(frame, times)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One output frame’s instants, in the order they must be captured.

One instant unless a frame clock opened the shutter
(`RenderContext.frame_samples`).

### *exception* an.engines.FrameStageError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The frame stage could not produce a frame directory it can vouch for.

A renderer built by `frame_stage_renderer(..., error=...)` re-raises it as
its own typed error at its boundary.

### *class* an.engines.FrameStageRenderer(engine, name='', supported_renderers=(), error=<class 'an.engines.capture.FrameStageError'>, capture_options=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A `Renderer` that drives an [`Engine`](an.engines.protocol.html.md#an.engines.protocol.Engine) frame by frame.

Build it with [`frame_stage_renderer()`](#an.engines.frame_stage_renderer). Stateless across renders, so one
instance serves every shot of a parallel render: each `render` opens its
own session.

#### capture_options *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

Capture-loop tunables passed through to [`an.engines.capture.capture_frames()`](an.engines.capture.html.md#an.engines.capture.capture_frames)
(`batch`, `workers`, `max_inflight`, `batch_pixels`); unset = its defaults.

#### error

alias of [`FrameStageError`](an.engines.capture.html.md#an.engines.capture.FrameStageError)

#### render(shot, ctx)

Render `shot` to mp4 through the engine; see the module docstring.

* **Return type:**
  [`RenderResult`](an.adapters.html.md#an.adapters.RenderResult)

#### supported_renderers *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

The `Shot.renderer` values this renderer claims (the ONE place it names them).

### *class* an.engines.LiveEngine(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

The live tier: apply, settle, capture in real time. **Declared, not built.**

Its recorder resamples to a constant rate (`walkthru`’s worked example);
`frame_stage_renderer` does not drive it, and never falls back to it.

### *class* an.engines.StateDriven(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

A session the core hands states to.

#### render(state)

PNG bytes of `state` (`supersample` times the declared size).

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

#### timeline *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)*

The `an.timing` `Timeline` the core evaluates.

### *class* an.engines.StateDrivenAdapter(session)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A state-driven session seen as a time-driven one: the core evaluates `at(t)`.

`frame(t)` is `render(evaluate_timeline(timeline, t, space=space))` and
`state(t)` is the evaluated state, so the capture loop and the conformance
tests treat both drive modes alike. The session’s other members (`resolve`,
`provenance`, …) are reached through attribute access.

### *class* an.engines.TimeDriven(\*args, \*\*kwargs)

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

### *exception* an.engines.UnseekableEngineError

Bases: [`TypeError`](https://docs.python.org/3/builtins/exceptions.html#TypeError)

A session that the frame stage cannot drive; the message says what to add.

### an.engines.capture_frames(session, requests, frames_dir, , factor=1, size=None, batch=None, workers=None, max_inflight=None, batch_pixels=None)

Write one PNG per request into `frames_dir`, resolved to the declared size.

`session` is time-driven (`frame(t)`), optionally batched
(`frames(requests)`), optionally with its own `resolve`. A state-driven
session is adapted by the frame stage before it reaches here. `size`, when
known, sets the pixel budget and is passed to the resolve. `None` for any
tunable reads the module default at call time.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.engines.describe(session)

The tier, drive mode and features a session (or a session class) offers.

* **Return type:**
  [`EngineProfile`](an.engines.protocol.html.md#an.engines.protocol.EngineProfile)

### an.engines.drive_mode(session)

`"time"`, `"state"`, or `None` for a session the frame stage cannot drive.

A session with both `frame` and `render` is time-driven: it evaluates
its own document, and the core does not second-guess it.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.engines.frame_stage_renderer(engine, \*, name=None, renderers=None, error=<class 'an.engines.capture.FrameStageError'>, capture_options=None)

Turn `engine` into a `Renderer`: the core’s clock, capture loop, resolves and sinks.

`name` defaults to the engine’s; `renderers` – the `Shot.renderer`
values claimed – default to `(name,)`. `error` is the typed exception
the renderer raises at its boundary for every core error.

* **Return type:**
  [`FrameStageRenderer`](an.engines.frame_stage.html.md#an.engines.frame_stage.FrameStageRenderer)

### an.engines.requests_as_dicts(requests)

Requests as plain dicts, the shape a page or a subprocess takes.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.engines.require_engine(engine)

Refuse an object that is not an engine, saying what is missing.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> require_engine(object())
Traceback (most recent call last):
  ...
TypeError: an Engine needs `name` and `open(job)`; object lacks: name, open
```

### an.engines.require_seekable(session)

The session’s drive mode, or a refusal that says what to add.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> require_seekable(object())
Traceback (most recent call last):
  ...
an.engines.protocol.UnseekableEngineError: this engine session cannot be captured: it has no frame(t) (time-driven), and no render(state) with a timeline (state-driven). Add frame(t) and state(t) if the engine evaluates the timeline itself, or timeline and render(state) if the core should evaluate it.
```

### an.engines.shot_workspace(work_dir, shot_id)

`<work_dir>/shot_<id>`: the one per-shot scratch directory.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### Modules

| [`capture`](an.engines.capture.html.md#module-an.engines.capture)         | The capture loop: drive a session through every frame, resolve, write -- for ANY engine.   |
|--------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| [`frame_stage`](an.engines.frame_stage.html.md#module-an.engines.frame_stage) | `frame_stage_renderer(engine)`: any seekable engine becomes a `Renderer`.                  |
| [`protocol`](an.engines.protocol.html.md#module-an.engines.protocol)       | The `Engine` protocol: a seekable thing that turns a time, or a state, into a frame.       |
