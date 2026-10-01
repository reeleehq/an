# an.impacts

Synthetic impact clips with exact ground truth, for scoring sub-frame timing.

Structured animations of simple objects — a stick or a ball — striking a
surface, or striking “the air” (a stroke that reverses with no contact), on a
known tempo grid. Each clip ships a sidecar that keeps three times apart:

- the **intended** grid time of every event (`t_grid`),
- the **executed** impact time in continuous seconds (`t_impact` — the grid
  plus controllable humanisation, never snapped to a frame),
- and **what the frames show**: every frame’s exposure interval and sample
  instants ([`an.frame_clock.FrameClock`](an.frame_clock.html.md#an.frame_clock.FrameClock): frame rate, shutter, capture
  jitter), the 2D keypoints at each frame, and which frames bracket each impact.

The clips are ordinary `an` scenes — props moved by tweens — rendered by the
cutout backend, and the ground truth is read back from the same compiled
document the renderer draws.

Quick start:

```default
from an.impacts import ImpactClipSpec, write_impact_clip, write_impact_set

write_impact_clip(ImpactClipSpec(kind="air", fps=30, exposure=0.5,
                                 jitter_sd=0.01), "~/clips")
write_impact_set("~/clips/set")      # 24 clips: objects x kinds x fps x shutter
```

Or from the shell: `an impacts clip OUT_DIR` / `an impacts clip-set OUT_DIR`.

```pycon
>>> plan = plan_impact_clip(ImpactClipSpec(kind="air", beats=2, tempo=60, jitter_sd=0))
>>> [(e.t_grid, e.t_impact) for e in plan.events]
[(0.5, 0.5), (1.5, 1.5)]
```

### Functions

| [`ball`](#an.impacts.ball)(\*[, radius, x, floor_y, drop, color, ...])   | A ball moving vertically onto a floor whose top is at `floor_y`.                                                              |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| [`build_stroke`](#an.impacts.build_stroke)(events, \*[, kind, rise, fall, ...])  | Chain rise / hold / fall segments through every executed impact.                                                              |
| [`gaussian_humanizer`](#an.impacts.gaussian_humanizer)([sd, rho, bias])                | Offsets from an AR(1) Gaussian process: `o[k] = bias + rho*(o[k-1]-bias) + e`.                                                |
| [`impact_object`](#an.impacts.impact_object)(name, \*\*kwargs)                    | Build a registered object by name.                                                                                            |
| [`impact_set_specs`](#an.impacts.impact_set_specs)(\*[, base, objects, kinds, ...])  | The cartesian product of the given axes over `base`.                                                                          |
| [`perform`](#an.impacts.perform)([tempo, beats, subdivision, ...])          | The impacts of `beats` beats of `pattern`, on `tempo`'s grid.                                                                 |
| [`plan_impact_clip`](#an.impacts.plan_impact_clip)(spec)                             | Resolve `spec` into events, a stroke, frames and a Scene IR.                                                                  |
| [`stick`](#an.impacts.stick)(\*[, length, thickness, pivot, ...])         | A drumstick rotating about `pivot` (its butt — the hand).                                                                     |
| [`tempo_map`](#an.impacts.tempo_map)(tempo)                                   | Coerce a bpm, a `[(beat, bpm), ...]` list, or a [`TempoMap`](#an.impacts.TempoMap).                    |
| [`write_impact_clip`](#an.impacts.write_impact_clip)(spec, out_dir, \*[, ...])        | Write one clip into `out_dir / (clip_dir or spec.clip_id)`; return that dir.                                                  |
| [`write_impact_set`](#an.impacts.write_impact_set)(out_dir[, specs, render, ...])    | Write every clip in `specs` (default: [`impact_set_specs()`](#an.impacts.impact_set_specs)) plus `index.json`. |

### Classes

| [`CapturedFrame`](#an.impacts.CapturedFrame)(index, t_nominal, t_open, ...)      | One output frame: when its exposure opened and closed, and what it saw.         |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`FrameClock`](#an.impacts.FrameClock)([fps, exposure, samples, ...])         | A camera's timing, as data.                                                     |
| [`ImpactClipSpec`](#an.impacts.ImpactClipSpec)([object, kind, tempo, beats, ...]) | Everything that determines a clip.                                              |
| [`ImpactEvent`](#an.impacts.ImpactEvent)(index, beat, t_grid, t_impact, ...)   | One impact: where the grid put it and when it was executed.                     |
| [`ImpactObject`](#an.impacts.ImpactObject)(name, art, at, channels, ...[, ...]) | One striking object, its surface, and how the stroke moves it.                  |
| [`ImpactPlan`](#an.impacts.ImpactPlan)(spec, events, obj, stroke, ...)        | A clip before it touches disk: events, motion, camera, and the Scene IR.        |
| [`Stroke`](#an.impacts.Stroke)(kind, duration, segments, kinematics)      | The whole curve, plus the kinematics of every impact on it.                     |
| [`StrokeSegment`](#an.impacts.StrokeSegment)(t0, t1, h0, h1, easing)             | `h` goes from `h0` to `h1` over `[t0, t1]` under `easing`.                      |
| [`TempoMap`](#an.impacts.TempoMap)(points)                                  | Tempo as a function of beat: piecewise-linear BPM between `(beat, bpm)` points. |

### Exceptions

| [`TruthMismatch`](#an.impacts.TruthMismatch)   | The ground truth and the thing it describes disagree.   |
|------------------------------------------------------------------|---------------------------------------------------------|

### *class* an.impacts.CapturedFrame(index, t_nominal, t_open, t_close, samples, t_reported)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One output frame: when its exposure opened and closed, and what it saw.

`t_nominal` is `index / fps` — what a constant-rate container (an mp4)
says the frame’s time is. `samples` are the instants actually rendered
and averaged into it; `t_mid` is the middle of the exposure, the single
best instant to attribute a blurred frame to. `t_reported` is the
timestamp a capture pipeline hands downstream: nominal or actual, per the
clock’s `timestamps` setting.

### *class* an.impacts.FrameClock(fps=30.0, exposure=0.0, samples=None, jitter_sd=0.0, phase=0.0, timestamps='nominal', report_noise_sd=0.0, seed=0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A camera’s timing, as data. Every field defaults to the ideal camera.

`fps`: nominal frame rate (need not be an integer: 29.97 is a camera).
`exposure`: fraction of the frame period the shutter is open, in
`[0, 1]`; 0 is an instantaneous sample, 0.5 a 180-degree shutter.
`samples`: instants integrated per open exposure (midpoint rule);
`None` means 1 when `exposure == 0` and
`DEFAULT_EXPOSURE_SAMPLES` otherwise.
`jitter_sd`: standard deviation, in seconds, of each frame’s CAPTURE
offset from the nominal grid — the frame really is taken early or late.
Gaussian, clamped at [`max_jitter`](#an.impacts.FrameClock.max_jitter) so frames never overlap; a
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
Clamped at `MAX_REPORT_NOISE_FRACTION` of a frame period, with the
same refuse-rather-than-shrink rule as `jitter_sd`, and reported
timestamps must still increase: a real frame clock never runs backwards.
`seed`: the random streams (capture jitter and report noise are
independent draws from it).

Every instant is clipped into `[0, duration]`, because a render cannot
sample a scene outside its own timeline; the clipped values are what
[`frames()`](#an.impacts.FrameClock.frames) returns and what gets rendered.

#### frames(duration)

One [`CapturedFrame`](#an.impacts.CapturedFrame) per output frame of a `duration` render.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`CapturedFrame`](an.frame_clock.html.md#an.frame_clock.CapturedFrame), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

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

### *class* an.impacts.ImpactClipSpec(object='stick', kind='surface', tempo=100.0, beats=16, subdivision=1, pattern=(1.0,), lead_in=0.5, tail=0.5, jitter_sd=0.008, jitter_rho=0.0, jitter_bias=0.0, rise=0.18, fall=0.18, brake=0.03, show_surface=None, fps=30.0, exposure=0.0, exposure_samples=None, timestamp_jitter_sd=0.0, timestamp_noise_sd=0.0, phase=0.0, timestamps='nominal', width=640, height=360, trajectory_hz=1000.0, seed=0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Everything that determines a clip. Defaults: a stick hitting a table at 100 BPM.

Performance: `tempo` (a bpm, or `[(beat, bpm), ...]` for a tempo
change), `beats`, `subdivision`, `pattern` (per-step stroke heights,
`0` = rest), `lead_in`, `tail`, and the humanisation `jitter_sd` /
`jitter_rho` / `jitter_bias` (seconds; see
[`an.impacts.performance.gaussian_humanizer()`](an.impacts.performance.html.md#an.impacts.performance.gaussian_humanizer)). Humanised by default
(`jitter_sd` = `DEFAULT_JITTER_SD`): on a perfect grid every impact
of a round tempo lands exactly on a frame at common rates, which is the one
case a sub-frame estimator cannot be scored on. Set it to 0 for a metronome.

Motion: `object` (`"stick"` or `"ball"`), `kind` (`"surface"` or
`"air"`), the stroke timings `rise` / `fall` / `brake`, and
`show_surface` (`None`: drawn for surface impacts only).

Camera ([`an.frame_clock.FrameClock`](an.frame_clock.html.md#an.frame_clock.FrameClock)): `fps`, `exposure`,
`exposure_samples`, `timestamp_jitter_sd` (when frames are really
taken), `timestamp_noise_sd` (noise on the reported timestamp only),
`phase`, `timestamps`.

`seed` drives two independent streams — the performance’s and the
camera’s — so clips that differ only in camera settings share the exact same
performance.

#### *property* clip_id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

A readable, deterministic directory name.

```pycon
>>> ImpactClipSpec().clip_id[:-8]
'stick-surface-30fps-e0-'
>>> ImpactClipSpec().clip_id == ImpactClipSpec().clip_id
True
```

#### *classmethod* from_dict(d)

The inverse of `to_dict()`. Refuses fields it does not know —
dropping one would regenerate a different clip under the same spec.

* **Return type:**
  [`ImpactClipSpec`](an.impacts.clip.html.md#an.impacts.clip.ImpactClipSpec)

### *class* an.impacts.ImpactEvent(index, beat, t_grid, t_impact, amplitude)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One impact: where the grid put it and when it was executed.

#### *property* offset *: [float](https://docs.python.org/3/builtins/functions.html#float)*

the humanisation actually applied (post-clamp).

* **Type:**
  `t_impact - t_grid`

### *class* an.impacts.ImpactObject(name, art, at, channels, keypoints, impact_keypoint, keypoint_nodes=<factory>, surface_art=None, surface_at=None, params=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One striking object, its surface, and how the stroke moves it.

`channels` are the properties the stroke drives — one for a stick or a
ball, two for a forearm-plus-stick limb (each affine in the SAME `h`, so
the motion stays exact). `keypoints` are local points by name; each lives
on the node `keypoint_nodes[name]` names, the entity itself by default.

#### impact_keypoint *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The keypoint that does the striking (a stick’s tip, a ball’s bottom).

#### keypoints *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]]*

Local points by name. What a tracker would report.

#### pose(h)

`{(node path, property): value}` at stroke height `h`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

#### surface_at *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where the surface’s top edge is centred, in scene coordinates.

### *class* an.impacts.ImpactPlan(spec, events, obj, stroke, frames, scene)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A clip before it touches disk: events, motion, camera, and the Scene IR.

### *class* an.impacts.Stroke(kind, duration, segments, kinematics)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The whole curve, plus the kinematics of every impact on it.

#### h(t)

Stroke height at scene time `t` (clamped to the clip).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

#### velocity(t)

`dh/dt` at `t`; at a segment boundary, the LATER segment’s value.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### *class* an.impacts.StrokeSegment(t0, t1, h0, h1, easing)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`h` goes from `h0` to `h1` over `[t0, t1]` under `easing`.

### *class* an.impacts.TempoMap(points)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Tempo as a function of beat: piecewise-linear BPM between `(beat, bpm)` points.

Constant before the first point and after the last. Linear in BEATS, not in
seconds, which is how a score writes an accelerando (“speed up over these
four bars”); the time of a beat is the exact integral of `60 / bpm`.

```pycon
>>> TempoMap(((0, 120),)).time_of(3)
1.5
>>> m = TempoMap(((0, 60), (4, 120)))
>>> round(m.time_of(4), 6)   # 4 * 60/(120-60) * ln(120/60)
2.772589
>>> m.bpm_at(2), m.bpm_at(10)
(90.0, 120.0)
```

#### time_of(beat)

Seconds from beat 0 to `beat` (`beat >= 0`).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### *exception* an.impacts.TruthMismatch

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The ground truth and the thing it describes disagree.

### an.impacts.ball(, radius=18.0, x=0.0, floor_y=90.0, drop=170.0, color='#111827', surface_color='#9ca3af', surface_size=(160.0, 24.0))

A ball moving vertically onto a floor whose top is at `floor_y`.

A full stroke lifts it `drop` pixels. Keypoints: `center` and
`bottom` (its contact point).

* **Return type:**
  [`ImpactObject`](an.impacts.objects.html.md#an.impacts.objects.ImpactObject)

### an.impacts.build_stroke(events, , kind='surface', duration, rise=0.18, fall=0.18, brake=0.03, rest_height=1.0)

Chain rise / hold / fall segments through every executed impact.

The object starts and ends at `rest_height`; before impact `k` it is
raised to `events[k].amplitude` (a bigger preparation, a harder hit).
Segments tile `[0, duration]` exactly, and every impact is a segment
boundary at precisely `t_impact`.

* **Return type:**
  [`Stroke`](an.impacts.stroke.html.md#an.impacts.stroke.Stroke)

### an.impacts.gaussian_humanizer(sd=0.0, , rho=0.0, bias=0.0)

Offsets from an AR(1) Gaussian process: `o[k] = bias + rho*(o[k-1]-bias) + e`.

`sd` is the STATIONARY standard deviation of the offsets (seconds) — the
innovation is scaled by `sqrt(1 - rho**2)` so changing `rho` changes how
the timing wanders, not how far. `rho = 0` is independent jitter;
`rho` near 1 is a player who drifts ahead or behind for several beats.
`bias` is a constant lead (negative) or lag (positive).

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Sequence`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)[[`float`](https://docs.python.org/3/builtins/functions.html#float)], [`object`](https://docs.python.org/3/builtins/functions.html#object)], [`Sequence`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]]

```pycon
>>> import numpy as np
>>> h = gaussian_humanizer(0.01, rho=0.5)
>>> offs = h([0.0] * 20000, np.random.default_rng(0))
>>> round(float(np.std(offs)), 3)
0.01
>>> gaussian_humanizer()([0.0, 1.0], None)
[0.0, 0.0]
```

### an.impacts.impact_object(name, \*\*kwargs)

Build a registered object by name.

* **Return type:**
  [`ImpactObject`](an.impacts.objects.html.md#an.impacts.objects.ImpactObject)

```pycon
>>> impact_object("ball").name
'ball'
>>> impact_object("hammer")
Traceback (most recent call last):
  ...
KeyError: "no impact object 'hammer'; known: ['ball', 'stick']"
```

### an.impacts.impact_set_specs(, base=ImpactClipSpec(object='stick', kind='surface', tempo=((0.0, 96.0), (24.0, 132.0)), beats=24, subdivision=1, pattern=(1.0, 0.6, 0.8, 0.6), lead_in=0.5, tail=0.5, jitter_sd=0.012, jitter_rho=0.3, jitter_bias=0.0, rise=0.18, fall=0.18, brake=0.03, show_surface=None, fps=30.0, exposure=0.0, exposure_samples=None, timestamp_jitter_sd=0.0, timestamp_noise_sd=0.0, phase=0.0, timestamps='nominal', width=640, height=360, trajectory_hz=1000.0, seed=0), objects=('stick', 'ball'), kinds=('surface', 'air'), fps=(24, 30, 60), exposures=(0.0, 0.5), timestamp_jitter_sds=(0.0,), seeds=(0,))

The cartesian product of the given axes over `base`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`ImpactClipSpec`](an.impacts.clip.html.md#an.impacts.clip.ImpactClipSpec)]

```pycon
>>> len(impact_set_specs())
24
>>> {s.seed for s in impact_set_specs(seeds=(0, 1), fps=(30,))}
{0, 1}
```

### an.impacts.perform(tempo=100.0, , beats=16, subdivision=1, pattern=(1.0,), lead_in=0.5, humanizer=None, seed=0)

The impacts of `beats` beats of `pattern`, on `tempo`’s grid.

`subdivision` grid steps per beat; `pattern` is cycled over the steps,
one value per step: `0` is a rest, anything in `(0, 1]` is a hit of that
relative stroke height (an accent is a bigger stroke). `lead_in` shifts
beat 0 to that many seconds into the clip. `humanizer` turns grid times
into offsets (default: none); each offset is then clamped to
`MAX_OFFSET_FRACTION` of the gap to either neighbour, and the clamped
value is what the event records — the ground truth is what was executed.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`ImpactEvent`](an.impacts.performance.html.md#an.impacts.performance.ImpactEvent), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> [e.beat for e in perform(120, beats=2, subdivision=2, pattern=(1, 0))]
[0.0, 1.0]
>>> [e.amplitude for e in perform(120, beats=1, subdivision=4, pattern=(1, .5))]
[1.0, 0.5, 1.0, 0.5]
```

### an.impacts.plan_impact_clip(spec)

Resolve `spec` into events, a stroke, frames and a Scene IR. No I/O.

* **Return type:**
  [`ImpactPlan`](an.impacts.clip.html.md#an.impacts.clip.ImpactPlan)

### an.impacts.stick(, length=200.0, thickness=12.0, pivot=(-120.0, -30.0), contact_angle=0.35, swing=0.95, color='#111827', surface_color='#9ca3af', surface_size=(140.0, 24.0))

A drumstick rotating about `pivot` (its butt — the hand).

At contact it points `contact_angle` radians below horizontal; a full
stroke raises it by `swing` radians. Keypoints: `pivot` and `tip`
(the end of its axis). The surface’s top meets the lowest point of its
rounded end.

* **Return type:**
  [`ImpactObject`](an.impacts.objects.html.md#an.impacts.objects.ImpactObject)

### an.impacts.tempo_map(tempo)

Coerce a bpm, a `[(beat, bpm), ...]` list, or a [`TempoMap`](#an.impacts.TempoMap).

* **Return type:**
  [`TempoMap`](an.impacts.performance.html.md#an.impacts.performance.TempoMap)

```pycon
>>> tempo_map(90).points
((0.0, 90.0),)
>>> tempo_map([(0, 90), (16, 120)]).points
((0.0, 90.0), (16.0, 120.0))
```

### an.impacts.write_impact_clip(spec, out_dir, , render=True, clip_dir=None)

Write one clip into `out_dir / (clip_dir or spec.clip_id)`; return that dir.

With `render=False` everything but `clip.mp4` is written, and no
browser is needed: the keypoints and the truth come from the compiled
document, not from the pixels.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.impacts.write_impact_set(out_dir, specs=None, , render=True, progress=None)

Write every clip in `specs` (default: [`impact_set_specs()`](#an.impacts.impact_set_specs)) plus `index.json`.

`progress`, if given, is called with `(i, n, clip_dir)` after each clip.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### Modules

| [`cli`](an.impacts.cli.html.md#module-an.impacts.cli)                 | `an impacts ...` — the impact harness from the shell.                           |
|--------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`clip`](an.impacts.clip.html.md#module-an.impacts.clip)               | One impact clip, end to end: spec -> scene -> ground truth -> (video) -> files. |
| [`objects`](an.impacts.objects.html.md#module-an.impacts.objects)         | The things that strike: a stick and a ball, as ordinary `an` props.             |
| [`performance`](an.impacts.performance.html.md#module-an.impacts.performance) | The performance: a tempo grid, and when each impact was intended and executed.  |
| [`stroke`](an.impacts.stroke.html.md#module-an.impacts.stroke)           | The stroke: impact events -> one continuous height curve `h(t)`.                |
| [`truth`](an.impacts.truth.html.md#module-an.impacts.truth)             | Ground truth: what was intended, what was executed, and what each frame shows.  |
