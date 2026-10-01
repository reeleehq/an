# an.impacts.clip

One impact clip, end to end: spec -> scene -> ground truth -> (video) -> files.

[`ImpactClipSpec`](#an.impacts.clip.ImpactClipSpec) is the whole description of a clip as flat, JSON-able
data — it is written verbatim into the sidecar, so any clip can be regenerated
from its own `truth.json`. [`plan_impact_clip()`](#an.impacts.clip.plan_impact_clip) turns it into the scene an
animation would have (props + tweens, a normal `an` Shot) without touching
disk; [`write_impact_clip()`](#an.impacts.clip.write_impact_clip) compiles it, extracts the ground truth, renders
the video (optional — the truth and keypoints need no browser), and writes:

```pycon
>>> plan = plan_impact_clip(ImpactClipSpec(beats=4, tempo=120))
>>> [e.t_grid for e in plan.events]                        # intended
[0.5, 1.0, 1.5, 2.0]
>>> [round(e.t_impact - e.t_grid, 3) for e in plan.events]  # executed: humanised
[0.003, 0.013, -0.005, 0.006]
>>> len(plan.frames)
75
```

### Module Attributes

| [`DEFAULT_TAIL`](#an.impacts.clip.DEFAULT_TAIL)          | Seconds after the last grid beat before the clip ends.           |
|------------------------------------------------------------------------|------------------------------------------------------------------|
| [`DEFAULT_JITTER_SD`](#an.impacts.clip.DEFAULT_JITTER_SD)     | Default humanisation (seconds, standard deviation).              |
| [`DEFAULT_TRAJECTORY_HZ`](#an.impacts.clip.DEFAULT_TRAJECTORY_HZ) | Samples per second of the dense trajectory in `trajectory.csv`.  |
| [`BENCHMARK_SPEC`](#an.impacts.clip.BENCHMARK_SPEC)        | an accelerando with accents and human, slightly drifting timing. |

### Functions

| [`impact_set_specs`](#an.impacts.clip.impact_set_specs)(\*[, base, objects, kinds, ...])   | The cartesian product of the given axes over `base`.                                                                          |
|------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| [`plan_impact_clip`](#an.impacts.clip.plan_impact_clip)(spec)                              | Resolve `spec` into events, a stroke, frames and a Scene IR.                                                                  |
| [`write_impact_clip`](#an.impacts.clip.write_impact_clip)(spec, out_dir, \*[, ...])         | Write one clip into `out_dir / (clip_dir or spec.clip_id)`; return that dir.                                                  |
| [`write_impact_set`](#an.impacts.clip.write_impact_set)(out_dir[, specs, render, ...])     | Write every clip in `specs` (default: [`impact_set_specs()`](#an.impacts.clip.impact_set_specs)) plus `index.json`. |

### Classes

| [`ImpactClipSpec`](#an.impacts.clip.ImpactClipSpec)([object, kind, tempo, beats, ...])   | Everything that determines a clip.                                       |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`ImpactPlan`](#an.impacts.clip.ImpactPlan)(spec, events, obj, stroke, ...)          | A clip before it touches disk: events, motion, camera, and the Scene IR. |

### Exceptions

| [`ImpactSpecError`](#an.impacts.clip.ImpactSpecError)   | A clip spec that cannot describe a clip.   |
|--------------------------------------------------------------------|--------------------------------------------|

### an.impacts.clip.BENCHMARK_SPEC *= ImpactClipSpec(object='stick', kind='surface', tempo=((0.0, 96.0), (24.0, 132.0)), beats=24, subdivision=1, pattern=(1.0, 0.6, 0.8, 0.6), lead_in=0.5, tail=0.5, jitter_sd=0.012, jitter_rho=0.3, jitter_bias=0.0, rise=0.18, fall=0.18, brake=0.03, show_surface=None, fps=30.0, exposure=0.0, exposure_samples=None, timestamp_jitter_sd=0.0, timestamp_noise_sd=0.0, phase=0.0, timestamps='nominal', width=640, height=360, trajectory_hz=1000.0, seed=0)*

an accelerando with accents and
human, slightly drifting timing. What [`impact_set_specs()`](#an.impacts.clip.impact_set_specs) varies the
camera and the object over.

* **Type:**
  A harder default for scoring estimators

### an.impacts.clip.DEFAULT_JITTER_SD *: float* *= 0.008*

Default humanisation (seconds, standard deviation). See `ImpactClipSpec`.

### an.impacts.clip.DEFAULT_TAIL *: float* *= 0.5*

Seconds after the last grid beat before the clip ends.

### an.impacts.clip.DEFAULT_TRAJECTORY_HZ *: float* *= 1000.0*

Samples per second of the dense trajectory in `trajectory.csv`.

### *class* an.impacts.clip.ImpactClipSpec(object='stick', kind='surface', tempo=100.0, beats=16, subdivision=1, pattern=(1.0,), lead_in=0.5, tail=0.5, jitter_sd=0.008, jitter_rho=0.0, jitter_bias=0.0, rise=0.18, fall=0.18, brake=0.03, show_surface=None, fps=30.0, exposure=0.0, exposure_samples=None, timestamp_jitter_sd=0.0, timestamp_noise_sd=0.0, phase=0.0, timestamps='nominal', width=640, height=360, trajectory_hz=1000.0, seed=0)

Bases: `object`

Everything that determines a clip. Defaults: a stick hitting a table at 100 BPM.

Performance: `tempo` (a bpm, or `[(beat, bpm), ...]` for a tempo
change), `beats`, `subdivision`, `pattern` (per-step stroke heights,
`0` = rest), `lead_in`, `tail`, and the humanisation `jitter_sd` /
`jitter_rho` / `jitter_bias` (seconds; see
[`an.impacts.performance.gaussian_humanizer()`](an.impacts.performance.html.md#an.impacts.performance.gaussian_humanizer)). Humanised by default
(`jitter_sd` = [`DEFAULT_JITTER_SD`](#an.impacts.clip.DEFAULT_JITTER_SD)): on a perfect grid every impact
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

#### *property* clip_id *: str*

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
  [`ImpactClipSpec`](#an.impacts.clip.ImpactClipSpec)

### *class* an.impacts.clip.ImpactPlan(spec, events, obj, stroke, frames, scene)

Bases: `object`

A clip before it touches disk: events, motion, camera, and the Scene IR.

### *exception* an.impacts.clip.ImpactSpecError

Bases: `ValueError`

A clip spec that cannot describe a clip.

### an.impacts.clip.impact_set_specs(, base=ImpactClipSpec(object='stick', kind='surface', tempo=((0.0, 96.0), (24.0, 132.0)), beats=24, subdivision=1, pattern=(1.0, 0.6, 0.8, 0.6), lead_in=0.5, tail=0.5, jitter_sd=0.012, jitter_rho=0.3, jitter_bias=0.0, rise=0.18, fall=0.18, brake=0.03, show_surface=None, fps=30.0, exposure=0.0, exposure_samples=None, timestamp_jitter_sd=0.0, timestamp_noise_sd=0.0, phase=0.0, timestamps='nominal', width=640, height=360, trajectory_hz=1000.0, seed=0), objects=('stick', 'ball'), kinds=('surface', 'air'), fps=(24, 30, 60), exposures=(0.0, 0.5), timestamp_jitter_sds=(0.0,), seeds=(0,))

The cartesian product of the given axes over `base`.

* **Return type:**
  `list`[[`ImpactClipSpec`](#an.impacts.clip.ImpactClipSpec)]

```pycon
>>> len(impact_set_specs())
24
>>> {s.seed for s in impact_set_specs(seeds=(0, 1), fps=(30,))}
{0, 1}
```

### an.impacts.clip.plan_impact_clip(spec)

Resolve `spec` into events, a stroke, frames and a Scene IR. No I/O.

* **Return type:**
  [`ImpactPlan`](#an.impacts.clip.ImpactPlan)

### an.impacts.clip.write_impact_clip(spec, out_dir, , render=True, clip_dir=None)

Write one clip into `out_dir / (clip_dir or spec.clip_id)`; return that dir.

With `render=False` everything but `clip.mp4` is written, and no
browser is needed: the keypoints and the truth come from the compiled
document, not from the pixels.

* **Return type:**
  `Path`

### an.impacts.clip.write_impact_set(out_dir, specs=None, , render=True, progress=None)

Write every clip in `specs` (default: [`impact_set_specs()`](#an.impacts.clip.impact_set_specs)) plus `index.json`.

`progress`, if given, is called with `(i, n, clip_dir)` after each clip.

* **Return type:**
  `Path`
