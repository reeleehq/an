# an.engines.frame_stage

`frame_stage_renderer(engine)`: any seekable engine becomes a `Renderer`.

The core owns everything around the engine, once, for every engine:

1. the knobs, validated before anything launches – ffmpeg present, the
   supersample factor ([`an.media.supersample.check_factor()`](an.media.supersample.html.md#an.media.supersample.check_factor)), the pixel
   format ([`an.media.mp4.check_pix_fmt()`](an.media.mp4.html.md#an.media.mp4.check_pix_fmt)), the engine’s own knobs
   (`Engine.check`), and the frame clock ([`an.media.shutter.check_frame_samples()`](an.media.shutter.html.md#an.media.shutter.check_frame_samples));
2. the clock: `frame_count = max(1, round(duration * fps))`, frame `i` at
   `i / fps` unless `RenderContext.frame_samples` (built by
   [`an.frame_clock.FrameClock`](an.frame_clock.html.md#an.frame_clock.FrameClock)) says otherwise;
3. the shot’s workspace – `<work_dir>/shot_<id>/` with a cleared `frames/`;
4. the capture loop ([`an.engines.capture`](an.engines.capture.html.md#module-an.engines.capture)): supersampling and the shutter
   resolved in the frame stage;
5. the sink: the frames muxed to the shot mp4 with the pinned argv, the shot’s
   dialogue laid under it ([`an.media.mp4.mux_shot()`](an.media.mp4.html.md#an.media.mp4.mux_shot));
6. provenance: the core’s facts plus the session’s own (`provenance()`).

The engine only loads the shot and draws instants ([`an.engines.protocol`](an.engines.protocol.html.md#module-an.engines.protocol)).
A STATE-driven session is adapted here: the core evaluates its `timeline` with
[`an.timing.timeline.evaluate_timeline()`](an.timing.timeline.html.md#an.timing.timeline.evaluate_timeline) (in the session’s `space` when it
has one) and hands each state to `render`.

Errors the core raises ([`FrameStageError`](an.engines.capture.html.md#an.engines.capture.FrameStageError),
[`MediaError`](an.media.mp4.html.md#an.media.mp4.MediaError), [`UnseekableEngineError`](an.engines.protocol.html.md#an.engines.protocol.UnseekableEngineError))
are re-raised as the renderer’s own `error` type at its boundary, message
intact, so a cut-out render still fails with `CutoutRenderError`.

```pycon
>>> from contextlib import contextmanager
>>> class Card:
...     name = "card"
...     @contextmanager
...     def open(self, job):
...         yield self
...     def frame(self, t): return b""
...     def state(self, t): return {}
>>> r = frame_stage_renderer(Card(), renderers=("card", "title"))
>>> r.name, r.supported_renderers
('card', ('card', 'title'))
```

### Module Attributes

| [`SHOT_WORKSPACE_PATTERN`](#an.engines.frame_stage.SHOT_WORKSPACE_PATTERN)   | A shot's scratch directory under `RenderContext.work_dir`.   |
|---------------------------------------------------------------------------|--------------------------------------------------------------|

### Functions

| [`frame_stage_renderer`](#an.engines.frame_stage.frame_stage_renderer)(engine, \*[, name, ...])   | Turn `engine` into a `Renderer`: the core's clock, capture loop, resolves and sinks.   |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| [`require_engine`](#an.engines.frame_stage.require_engine)(engine)                          | Refuse an object that is not an engine, saying what is missing.                        |
| [`shot_workspace`](#an.engines.frame_stage.shot_workspace)(work_dir, shot_id)               | `<work_dir>/shot_<id>`: the one per-shot scratch directory.                            |

### Classes

| [`FrameStageRenderer`](#an.engines.frame_stage.FrameStageRenderer)(engine[, name, ...])   | A `Renderer` that drives an [`Engine`](an.engines.protocol.html.md#an.engines.protocol.Engine) frame by frame.   |
|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| [`StateDrivenAdapter`](#an.engines.frame_stage.StateDrivenAdapter)(session)               | A state-driven session seen as a time-driven one: the core evaluates `at(t)`.                                                    |

### *class* an.engines.frame_stage.FrameStageRenderer(engine, name='', supported_renderers=(), error=<class 'an.engines.capture.FrameStageError'>, capture_options=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A `Renderer` that drives an [`Engine`](an.engines.protocol.html.md#an.engines.protocol.Engine) frame by frame.

Build it with [`frame_stage_renderer()`](#an.engines.frame_stage.frame_stage_renderer). Stateless across renders, so one
instance serves every shot of a parallel render: each `render` opens its
own session.

#### capture_options *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

Capture-loop tunables passed through to [`an.engines.capture.capture_frames()`](an.engines.capture.html.md#an.engines.capture.capture_frames)
(`batch`, `workers`, `max_inflight`, `batch_pixels`); unset = its defaults.

#### error

The exception type raised at the boundary for every core error.

alias of [`FrameStageError`](an.engines.capture.html.md#an.engines.capture.FrameStageError)

#### probe_frames(shot, ctx, times)

The film’s frames of `shot` showing at each of `times` (seconds), as PNG bytes.

`an probe` (an#347): the session [`render()`](#an.engines.frame_stage.FrameStageRenderer.render) opens (the same
engine, state-driven adapter, supersample and frame clock) and the
same [`capture_frames()`](an.engines.capture.html.md#an.engines.capture.capture_frames), asked only for the
frames needed — so a probe frame IS the film’s frame, without the
rest of the shot or the mux. Each instant is snapped to the frame
showing then (`floor(t * fps)`, clamped to the shot).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]

#### render(shot, ctx)

Render `shot` to mp4 through the engine; see the module docstring.

* **Return type:**
  [`RenderResult`](an.adapters.html.md#an.adapters.RenderResult)

#### supported_renderers *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

The `Shot.renderer` values this renderer claims (the ONE place it names them).

### an.engines.frame_stage.SHOT_WORKSPACE_PATTERN *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'shot_{shot_id}'*

A shot’s scratch directory under `RenderContext.work_dir`. Kept from the
stage renderer it came from, so the paths a render leaves behind (and that
the bench and film assembly read) do not move.

### *class* an.engines.frame_stage.StateDrivenAdapter(session)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A state-driven session seen as a time-driven one: the core evaluates `at(t)`.

`frame(t)` is `render(evaluate_timeline(timeline, t, space=space))` and
`state(t)` is the evaluated state, so the capture loop and the conformance
tests treat both drive modes alike. The session’s other members
(`resolve`, `provenance`, …) are reached through attribute access.

**Batched** (an#286): `frames(requests)` evaluates every instant here and
hands the session the STATES, through its optional `render_states(states)`
(one round trip per batch, the member a JS-bridged view engine implements),
else `render` per state. A session’s own `frames` is never forwarded: it
would take times and bypass `state`.

**Adapted by drive mode** (an#286): `project(point, t)` and `bounds(t)`
reach the session as `project(point, state)` and `bounds(state)` (the
state-driven signature, previz’s `project(point, {state, ...})`), and
exist only when the session has them, so [`describe()`](an.engines.protocol.html.md#an.engines.protocol.describe)
still reads capabilities from real members.

#### frames(requests)

One list of frames per request, a frame per instant, in order.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]]

### an.engines.frame_stage.frame_stage_renderer(engine, \*, name=None, renderers=None, error=<class 'an.engines.capture.FrameStageError'>, capture_options=None)

Turn `engine` into a `Renderer`: the core’s clock, capture loop, resolves and sinks.

`name` defaults to the engine’s; `renderers` – the `Shot.renderer`
values claimed – default to `(name,)`. `error` is the typed exception
the renderer raises at its boundary for every core error.

* **Return type:**
  [`FrameStageRenderer`](#an.engines.frame_stage.FrameStageRenderer)

### an.engines.frame_stage.require_engine(engine)

Refuse an object that is not an engine, saying what is missing.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> require_engine(object())
Traceback (most recent call last):
  ...
TypeError: an Engine needs `name` and `open(job)`; object lacks: name, open
```

### an.engines.frame_stage.shot_workspace(work_dir, shot_id)

`<work_dir>/shot_<id>`: the one per-shot scratch directory.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
