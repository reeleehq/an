# an.frame_clock

The frame clock: WHEN each output frame samples scene time.

A render has always sampled frame `i` at exactly `i / fps` — one instant,
on a perfect grid. A real camera does neither: its shutter stays open for part
of the frame period (so a moving object smears), and its capture instants
wander around the nominal grid (so the timestamp a frame carries is not quite
when it was taken). Anything that wants to *measure* motion from video — the
sub-frame impact estimators [`an.impacts`](an.impacts.md#module-an.impacts) exists to score — needs both, and
needs to know exactly what was done.

[`FrameClock`](#an.frame_clock.FrameClock) is that model as data. [`FrameClock.frames()`](#an.frame_clock.FrameClock.frames) returns one
[`CapturedFrame`](#an.frame_clock.CapturedFrame) per output frame, carrying the exposure interval and the
instants integrated over it; [`FrameClock.sample_times()`](#an.frame_clock.FrameClock.sample_times) is the projection
the renderer consumes through `RenderContext.frame_samples`. One object feeds
both the render and the ground truth, so the two cannot disagree about when a
frame was taken.

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

### Functions

| [`frame_count`](#an.frame_clock.frame_count)(duration, fps)   | Frames in a render of `duration` seconds — the renderer's own rule.   |
|-------------------------------------------------------------------------------|-----------------------------------------------------------------------|

### Classes

| [`CapturedFrame`](#an.frame_clock.CapturedFrame)(index, t_nominal, t_open, ...)   | One output frame: when its exposure opened and closed, and what it saw.   |
|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`FrameClock`](#an.frame_clock.FrameClock)([fps, exposure, samples, ...])      | A camera's timing, as data.                                               |

### Exceptions

| [`FrameClockError`](#an.frame_clock.FrameClockError)   | A frame clock that cannot describe a camera.   |
|--------------------------------------------------------------------|------------------------------------------------|

### *class* an.frame_clock.CapturedFrame(index, t_nominal, t_open, t_close, samples, t_reported)

Bases: `object`

One output frame: when its exposure opened and closed, and what it saw.

`t_nominal` is `index / fps` — what a constant-rate container (an mp4)
says the frame’s time is. `samples` are the instants actually rendered
and averaged into it; `t_mid` is the middle of the exposure, the single
best instant to attribute a blurred frame to. `t_reported` is the
timestamp a capture pipeline hands downstream: nominal or actual, per the
clock’s `timestamps` setting.

### an.frame_clock.DEFAULT_EXPOSURE_SAMPLES *: int* *= 8*

Sub-samples integrated per frame when the shutter is open and the caller did
not say how many. Eight midpoint samples put the smear of an object crossing
100 px in one exposure at steps of ~12 px — continuous to a tracker, cheap to
render (each sample is one screenshot).

### *class* an.frame_clock.FrameClock(fps=30.0, exposure=0.0, samples=None, jitter_sd=0.0, phase=0.0, timestamps='nominal', report_noise_sd=0.0, seed=0)

Bases: `object`

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
  `tuple`[[`CapturedFrame`](#an.frame_clock.CapturedFrame), `...`]

#### *property* max_jitter *: float*

The clamp on a frame’s capture offset, in seconds.

```pycon
>>> round(FrameClock(fps=10, exposure=0.5).max_jitter, 9)
0.0245
```

#### sample_times(duration)

Per frame, the scene instants to render and average — the render seam.

* **Return type:**
  `tuple`[`tuple`[`float`, `...`], `...`]

#### *property* samples_per_frame *: int*

1 for an instantaneous shutter.

```pycon
>>> FrameClock().samples_per_frame, FrameClock(exposure=0.5).samples_per_frame
(1, 8)
```

* **Type:**
  The resolved sample count

### *exception* an.frame_clock.FrameClockError

Bases: `ValueError`

A frame clock that cannot describe a camera.

### an.frame_clock.MAX_JITTER_FRACTION *: float* *= 0.49*

A frame’s capture offset is clamped to this fraction of the slack between
one exposure closing and the next opening, on each side. Below one half, so
two neighbouring frames can each move toward the other by the full clamp and
still not overlap: the clock never reorders frames, whatever `jitter_sd` is.

### an.frame_clock.MAX_REPORT_NOISE_FRACTION *: float* *= 0.24*

Report noise is clamped to this fraction of the frame period, each side, so
two neighbouring reported timestamps can never cross on a regular grid.

### an.frame_clock.frame_count(duration, fps)

Frames in a render of `duration` seconds — the renderer’s own rule.

* **Return type:**
  `int`

```pycon
>>> frame_count(2.0, 30), frame_count(0.01, 30)
(60, 1)
```
