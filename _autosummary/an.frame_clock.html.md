# an.frame_clock

The frame clock: WHEN each output frame samples scene time.

A render has always sampled frame `i` at exactly `i / fps` — one instant,
on a perfect grid. A real camera does neither: its shutter stays open for part
of the frame period (so a moving object smears), and its capture instants
wander around the nominal grid (so the timestamp a frame carries is not quite
when it was taken). Anything that wants to *measure* motion from video — the
sub-frame impact estimators `cutan.impacts` exists to score — needs both, and
needs to know exactly what was done.

[`FrameClock`](#an.frame_clock.FrameClock) is that model as data. [`FrameClock.frames()`](#an.frame_clock.FrameClock.frames) returns one
[`CapturedFrame`](#an.frame_clock.CapturedFrame) per output frame, carrying the exposure interval and the
instants integrated over it; [`FrameClock.sample_times()`](#an.frame_clock.FrameClock.sample_times) is the projection
the renderer consumes through `RenderContext.frame_samples`. One object feeds
both the render and the ground truth, so the two cannot disagree about when a
frame was taken.

It also owns the GRIDS a shot is laid onto, the pure rules every layer shares
(the IR’s camera, the stage’s compiler and solve): [`frame_times()`](#an.frame_clock.frame_times) (every
frame, the end included), [`step_times()`](#an.frame_clock.step_times) (a stepped shot’s pose grid,
an#89), [`grid_times()`](#an.frame_clock.grid_times) (one or the other, the solve’s grid) and
[`camera_grid()`](#an.frame_clock.camera_grid) (an#626), the instants a camera the runtime cannot
evaluate itself — a follow, a dolly — is keyed at so that every instant the
render samples, a shutter’s sub-frame ones included, lands on an exact key.

The default clock is the old behaviour exactly — no exposure, no jitter, one
sample at `i / fps`:

```pycon
>>> FrameClock(fps=4).sample_times(1.0)
((0.0,), (0.25,), (0.5,), (0.75,))
```

A 180-degree shutter (`exposure=0.5`) integrates the first half of each frame
period, sampled at the midpoints of `samples` equal sub-intervals:

```pycon
>>> FrameClock(fps=4, exposure=0.5, samples=2).sample_times(0.5)
((0.03125, 0.09375), (0.28125, 0.34375))
>>> f = FrameClock(fps=4, exposure=0.5, samples=2).frames(0.5)[1]
>>> (f.t_nominal, f.t_open, f.t_close, f.t_mid)
(0.25, 0.25, 0.375, 0.3125)
```

Capture jitter moves each frame’s exposure as a unit, never out of order:

```pycon
>>> clock = FrameClock(fps=30, jitter_sd=0.004, seed=7)
>>> opens = [f.t_open for f in clock.frames(2.0)]
>>> all(b > a for a, b in zip(opens, opens[1:]))
True
>>> clock.frames(2.0) == clock.frames(2.0)  # seeded: the same clock twice
True
```

### Module Attributes

| [`DEFAULT_EXPOSURE_SAMPLES`](#an.frame_clock.DEFAULT_EXPOSURE_SAMPLES)   | Sub-samples integrated per frame when the shutter is open and the caller did not say how many.                                                      |
|-----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| [`MAX_JITTER_FRACTION`](#an.frame_clock.MAX_JITTER_FRACTION)        | A frame's capture offset is clamped to this fraction of the slack between one exposure closing and the next opening, on each side.                  |
| [`MAX_REPORT_NOISE_FRACTION`](#an.frame_clock.MAX_REPORT_NOISE_FRACTION)  | Report noise is clamped to this fraction of the frame period, each side, so two neighbouring reported timestamps can never cross on a regular grid. |
| [`STEP_GRID_EPS`](#an.frame_clock.STEP_GRID_EPS)              | A step instant this close to the end of a span is not a step of it (`0.25 s × 12 Hz` is 3 steps, not 4, whatever the float product rounds to).      |
| [`SAMPLE_MERGE_EPS`](#an.frame_clock.SAMPLE_MERGE_EPS)           | a shutter sample that IS a frame up to float noise adds no key beside it (two keys a femtosecond apart would only divide by that femtosecond).      |

### Functions

| [`camera_grid`](#an.frame_clock.camera_grid)(duration, \*, fps[, step_hz, ...])   | The ONE sampler for a non-affine camera — a follow, a dolly, anything the runtime cannot evaluate from a few eased keys (an#626).                                                                  |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`frame_count`](#an.frame_clock.frame_count)(duration, fps)                       | Frames in a render of `duration` seconds — the renderer's own rule.                                                                                                                                |
| [`frame_times`](#an.frame_clock.frame_times)(duration, \*, fps)                   | The time of every frame a `duration` render draws, the end included (`k / fps`, the renderer's own expression, capped at `duration`).                                                              |
| [`grid_times`](#an.frame_clock.grid_times)(duration, \*, fps[, step_hz])         | A shot's own grid: every frame ([`frame_times()`](#an.frame_clock.frame_times)), or its step grid ([`step_times()`](#an.frame_clock.step_times)) under `step_hz`. |
| [`step_times`](#an.frame_clock.step_times)(start, duration, step_hz)             | Clip-local times at which a stepped tween updates its pose (an#89).                                                                                                                                |

### Classes

| [`CameraGrid`](#an.frame_clock.CameraGrid)(times, base, easing)              | Where a camera the runtime cannot evaluate itself is keyed (an#626).    |
|-----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`CapturedFrame`](#an.frame_clock.CapturedFrame)(index, t_nominal, t_open, ...) | One output frame: when its exposure opened and closed, and what it saw. |
| [`FrameClock`](#an.frame_clock.FrameClock)([fps, exposure, samples, ...])    | A camera's timing, as data.                                             |

### Exceptions

| [`FrameClockError`](#an.frame_clock.FrameClockError)   | A frame clock that cannot describe a camera.   |
|--------------------------------------------------------------------|------------------------------------------------|

### *class* an.frame_clock.CameraGrid(times, base, easing)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Where a camera the runtime cannot evaluate itself is keyed (an#626).

`times`: the key instants, sorted. `easing`: the keys’ easing —
`"linear"` on ones, `"step"` on a stepped shot (the camera holds
between keys as a stepped tween holds between poses). `base`: the
grid the camera is COMPUTED on — every frame, and every step instant on a
stepped shot — before the render’s sample instants are added (a follow’s
lag runs over it); `times` is a superset of it.

### *class* an.frame_clock.CapturedFrame(index, t_nominal, t_open, t_close, samples, t_reported)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One output frame: when its exposure opened and closed, and what it saw.

`t_nominal` is `index / fps` — what a constant-rate container (an mp4)
says the frame’s time is. `samples` are the instants actually rendered
and averaged into it; `t_mid` is the middle of the exposure, the single
best instant to attribute a blurred frame to. `t_reported` is the
timestamp a capture pipeline hands downstream: nominal or actual, per the
clock’s `timestamps` setting.

### an.frame_clock.DEFAULT_EXPOSURE_SAMPLES *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 8*

Sub-samples integrated per frame when the shutter is open and the caller did
not say how many. Eight midpoint samples put the smear of an object crossing
100 px in one exposure at steps of ~12 px — continuous to a tracker, cheap to
render (each sample is one screenshot).

### *class* an.frame_clock.FrameClock(fps=30.0, exposure=0.0, samples=None, jitter_sd=0.0, phase=0.0, timestamps='nominal', report_noise_sd=0.0, seed=0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A camera’s timing, as data. Every field defaults to the ideal camera.

`fps`: nominal frame rate (need not be an integer: 29.97 is a camera).
`exposure`: fraction of the frame period the shutter is open, in
`[0, 1]`; 0 is an instantaneous sample, 0.5 a 180-degree shutter.
`samples`: instants integrated per open exposure (midpoint rule);
`None` means 1 when `exposure == 0` and
[`DEFAULT_EXPOSURE_SAMPLES`](#an.frame_clock.DEFAULT_EXPOSURE_SAMPLES) otherwise.
`jitter_sd`: standard deviation, in seconds, of each frame’s CAPTURE
offset from the nominal grid — the frame really is taken early or late.
Gaussian, clamped at [`max_jitter`](#an.frame_clock.FrameClock.max_jitter) so frames never overlap; a
`jitter_sd` above half that clamp is refused rather than silently
shrunk (at `exposure=1` there is no room for any).
`phase`: seconds added to every capture instant — the camera clock’s
sub-frame offset from scene time, in `(-1/fps, 1/fps)`.
`timestamps`: the base of `CapturedFrame.t_reported` —
`"nominal"` (`index / fps`, what a naive tick loop or an mp4 reports)
or `"actual"` (`t_open`, what a capture API with real timestamps
reports).
`report_noise_sd`: Gaussian noise, in seconds, added to the REPORTED
timestamp only — regular capture, noisy clock (a browser frame callback).
Clamped at [`MAX_REPORT_NOISE_FRACTION`](#an.frame_clock.MAX_REPORT_NOISE_FRACTION) of a frame period, with the
same refuse-rather-than-shrink rule as `jitter_sd`, and reported
timestamps must still increase: a real frame clock never runs backwards.
`seed`: the random streams (capture jitter and report noise are
independent draws from it).

Every instant is clipped into `[0, duration]`, because a render cannot
sample a scene outside its own timeline; the clipped values are what
[`frames()`](#an.frame_clock.FrameClock.frames) returns and what gets rendered.

#### frames(duration)

One [`CapturedFrame`](#an.frame_clock.CapturedFrame) per output frame of a `duration` render.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`CapturedFrame`](#an.frame_clock.CapturedFrame), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

#### *property* max_jitter *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The clamp on a frame’s capture offset, in seconds.

```pycon
>>> round(FrameClock(fps=10, exposure=0.5).max_jitter, 9)
0.0245
```

#### sample_times(duration)

Per frame, the scene instants to render and average — the render seam.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)], [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

#### *property* samples_per_frame *: [int](https://docs.python.org/3/builtins/functions.html#int)*

1 for an instantaneous shutter.

```pycon
>>> FrameClock().samples_per_frame, FrameClock(exposure=0.5).samples_per_frame
(1, 8)
```

* **Type:**
  The resolved sample count

### *exception* an.frame_clock.FrameClockError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A frame clock that cannot describe a camera.

### an.frame_clock.MAX_JITTER_FRACTION *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.49*

A frame’s capture offset is clamped to this fraction of the slack between
one exposure closing and the next opening, on each side. Below one half, so
two neighbouring frames can each move toward the other by the full clamp and
still not overlap: the clock never reorders frames, whatever `jitter_sd` is.

### an.frame_clock.MAX_REPORT_NOISE_FRACTION *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.24*

Report noise is clamped to this fraction of the frame period, each side, so
two neighbouring reported timestamps can never cross on a regular grid.

### an.frame_clock.SAMPLE_MERGE_EPS *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1e-09*

a shutter sample
that IS a frame up to float noise adds no key beside it (two keys a
femtosecond apart would only divide by that femtosecond).

* **Type:**
  Two camera key instants closer than this (s) are one key

### an.frame_clock.STEP_GRID_EPS *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1e-09*

A step instant this close to the end of a span is not a step of it
(`0.25 s × 12 Hz` is 3 steps, not 4, whatever the float product rounds to).

### an.frame_clock.camera_grid(duration, , fps, step_hz=None, frame_samples=None, sample_fps=None, merge_eps=1e-09)

The ONE sampler for a non-affine camera — a follow, a dolly, anything
the runtime cannot evaluate from a few eased keys (an#626).

On ones (`step_hz` unset) the camera is keyed at every frame
([`frame_times()`](#an.frame_clock.frame_times)), linearly. On a stepped shot it is keyed at every
frame AND every step instant ([`step_times()`](#an.frame_clock.step_times)), step-eased: it holds
between keys as the stepped poses hold, so a step is a cut, not a
one-frame ramp. The step grid alone would not do: a tween’s end lands off
it, and the frames keep the camera exact where the target already moved.

`frame_samples` (`RenderContext.frame_samples`, a
[`FrameClock`](#an.frame_clock.FrameClock)’s [`sample_times()`](#an.frame_clock.FrameClock.sample_times)) adds every
instant the render actually samples — a shutter’s sub-frame ones, a
jittered capture’s — clipped to `[0, duration]`, so each lands on an
exact key instead of between two. An instant within `merge_eps` of a
key already there is that key. `None` adds nothing: the keys are
exactly the frame grid they always were. They must describe THIS shot:
one entry per frame ([`frame_count()`](#an.frame_clock.frame_count)) at `sample_fps`, the rate the
render samples at (a camera’s 29.97, where the compiled grid’s `fps` is
rounded to 30; `fps` when unset), or a [`FrameClockError`](#an.frame_clock.FrameClockError):
another shot’s samples would key the camera at the wrong instants.

```pycon
>>> camera_grid(0.5, fps=4)
CameraGrid(times=(0.0, 0.25, 0.5), base=(0.0, 0.25, 0.5), easing='linear')
>>> camera_grid(0.5, fps=4, frame_samples=((0.0,), (0.3, 0.6))).times
(0.0, 0.25, 0.3, 0.5)
>>> g = camera_grid(0.5, fps=4, step_hz=3)
>>> [round(t, 3) for t in g.times], g.easing, g.base == g.times
([0.0, 0.25, 0.333, 0.5], 'step', True)
>>> len(camera_grid(20.0, fps=30, frame_samples=[(k / 29.97,) for k in range(599)], sample_fps=29.97).times) > 600
True
>>> camera_grid(0.5, fps=4, frame_samples=((0.0,),))
Traceback (most recent call last):
  ...
an.frame_clock.FrameClockError: frame_samples describes 1 frame(s) but a 0.5 s shot at 4 fps has 2: they are another shot's samples.
```

* **Return type:**
  [`CameraGrid`](#an.frame_clock.CameraGrid)

### an.frame_clock.frame_count(duration, fps)

Frames in a render of `duration` seconds — the renderer’s own rule.

```pycon
>>> frame_count(2.0, 30), frame_count(0.01, 30)
(60, 1)
```

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.frame_clock.frame_times(duration, , fps)

The time of every frame a `duration` render draws, the end included
(`k / fps`, the renderer’s own expression, capped at `duration`).

THE frame grid rule (an#626). `an.ir.camera.frame_times` is this very
function re-exported, and `an.stage.solve.frame_times` a thin wrapper
over [`grid_times()`](#an.frame_clock.grid_times); neither restates it.

```pycon
>>> frame_times(0.5, fps=4)
[0.0, 0.25, 0.5]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.frame_clock.grid_times(duration, , fps, step_hz=None)

A shot’s own grid: every frame ([`frame_times()`](#an.frame_clock.frame_times)), or its step grid
([`step_times()`](#an.frame_clock.step_times)) under `step_hz`. What the solve runs at.

```pycon
>>> grid_times(0.1, fps=20)
[0.0, 0.05, 0.1]
>>> grid_times(0.25, fps=20, step_hz=10)
[0.0, 0.1, 0.2, 0.25]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.frame_clock.step_times(start, duration, step_hz)

Clip-local times at which a stepped tween updates its pose (an#89).

The grid is SHOT-wide — multiples of `1/step_hz` on the shot’s clock,
shared by every tween in the shot — not the tween’s own: “on twos” means
every character changes pose on the same frames, so a tween starting at
0.033 s updates at the next grid point, not 0.033 s later. (Shots compile
independently, so the grid restarts at each cut.) Local 0 (the tween’s
start) and `duration` (where the end value lands) are always present, so
a tween shorter than one step is a single step to its end value.

`step_hz` must be positive: with a non-positive rate the walk below never
reaches `duration` — an infinite loop, not an error — so it is refused.

```pycon
>>> step_times(0.0, 0.3, 10)
[0.0, 0.1, 0.2, 0.3]
>>> [round(t, 3) for t in step_times(0.05, 0.3, 10)]
[0.0, 0.05, 0.15, 0.25, 0.3]
>>> step_times(0.0, 0.02, 10)
[0.0, 0.02]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]
