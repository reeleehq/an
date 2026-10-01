# an.impacts.performance

The performance: a tempo grid, and when each impact was intended and executed.

Three times are kept apart on purpose, because scoring a sub-frame estimator is
meaningless if they blur together:

- `t_grid` — the INTENDED time: where the beat grid (a [`TempoMap`](#an.impacts.performance.TempoMap)) put
  the event. What a quantiser would snap to.
- `t_impact` — the EXECUTED time, in continuous seconds: the grid time plus a
  humanisation offset. This is when the object actually hits (or, in the air,
  turns); the motion is built so it happens at exactly this float, never on a
  frame.
- what the frames show — not here at all; that is [`an.impacts.truth`](an.impacts.truth.md#module-an.impacts.truth),
  after a [`an.frame_clock.FrameClock`](an.frame_clock.md#an.frame_clock.FrameClock) has sampled the motion.

```pycon
>>> events = perform(120, beats=4)
>>> [e.t_grid for e in events]
[0.5, 1.0, 1.5, 2.0]
>>> all(e.t_impact == e.t_grid for e in events)   # no humanisation by default
True
```

A tempo change is a [`TempoMap`](#an.impacts.performance.TempoMap) with more than one point — here an
accelerando from 60 to 120 BPM over four beats, so the gaps shrink:

```pycon
>>> ts = [e.t_grid for e in perform([(0, 60), (4, 120)], beats=5, lead_in=0.0)]
>>> [round(b - a, 3) for a, b in zip(ts, ts[1:])]
[0.893, 0.729, 0.617, 0.534]
```

### Module Attributes

| [`DEFAULT_LEAD_IN`](#an.impacts.performance.DEFAULT_LEAD_IN)     | Seconds before the first grid beat.                                                                                                                                                           |
|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`MAX_OFFSET_FRACTION`](#an.impacts.performance.MAX_OFFSET_FRACTION) | A humanisation offset is clamped to this fraction of the gap to each neighbouring grid event, so executed impacts can never swap order or collide — whatever the jitter's standard deviation. |
| [`Humanizer`](#an.impacts.performance.Humanizer)           | `(grid_times, rng) -> offsets`, in seconds, one per grid time.                                                                                                                                |

### Functions

| [`gaussian_humanizer`](#an.impacts.performance.gaussian_humanizer)([sd, rho, bias])       | Offsets from an AR(1) Gaussian process: `o[k] = bias + rho*(o[k-1]-bias) + e`.                             |
|--------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| [`perform`](#an.impacts.performance.perform)([tempo, beats, subdivision, ...]) | The impacts of `beats` beats of `pattern`, on `tempo`'s grid.                                              |
| [`tempo_map`](#an.impacts.performance.tempo_map)(tempo)                          | Coerce a bpm, a `[(beat, bpm), ...]` list, or a [`TempoMap`](#an.impacts.performance.TempoMap). |

### Classes

| [`ImpactEvent`](#an.impacts.performance.ImpactEvent)(index, beat, t_grid, t_impact, ...)   | One impact: where the grid put it and when it was executed.                     |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`TempoMap`](#an.impacts.performance.TempoMap)(points)                                  | Tempo as a function of beat: piecewise-linear BPM between `(beat, bpm)` points. |

### Exceptions

| [`PerformanceError`](#an.impacts.performance.PerformanceError)   | A performance description that cannot be played.   |
|---------------------------------------------------------------------|----------------------------------------------------|

### an.impacts.performance.DEFAULT_LEAD_IN *: float* *= 0.5*

Seconds before the first grid beat. Long enough for the first stroke’s
preparation and for any humanisation to pull the first impact early.

### an.impacts.performance.Humanizer

`(grid_times, rng) -> offsets`, in seconds, one per grid time. The seam for
timing models richer than [`gaussian_humanizer()`](#an.impacts.performance.gaussian_humanizer) (a learned groove, a
drummer’s measured microtiming).

alias of `Callable`[[`Sequence`[`float`], `object`], `Sequence`[`float`]]

### *class* an.impacts.performance.ImpactEvent(index, beat, t_grid, t_impact, amplitude)

Bases: `object`

One impact: where the grid put it and when it was executed.

#### *property* offset *: float*

the humanisation actually applied (post-clamp).

* **Type:**
  `t_impact - t_grid`

### an.impacts.performance.MAX_OFFSET_FRACTION *: float* *= 0.4*

A humanisation offset is clamped to this fraction of the gap to each
neighbouring grid event, so executed impacts can never swap order or
collide — whatever the jitter’s standard deviation.

### *exception* an.impacts.performance.PerformanceError

Bases: `ValueError`

A performance description that cannot be played.

### *class* an.impacts.performance.TempoMap(points)

Bases: `object`

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
  `float`

### an.impacts.performance.gaussian_humanizer(sd=0.0, , rho=0.0, bias=0.0)

Offsets from an AR(1) Gaussian process: `o[k] = bias + rho*(o[k-1]-bias) + e`.

`sd` is the STATIONARY standard deviation of the offsets (seconds) — the
innovation is scaled by `sqrt(1 - rho**2)` so changing `rho` changes how
the timing wanders, not how far. `rho = 0` is independent jitter;
`rho` near 1 is a player who drifts ahead or behind for several beats.
`bias` is a constant lead (negative) or lag (positive).

* **Return type:**
  `Callable`[[`Sequence`[`float`], `object`], `Sequence`[`float`]]

```pycon
>>> import numpy as np
>>> h = gaussian_humanizer(0.01, rho=0.5)
>>> offs = h([0.0] * 20000, np.random.default_rng(0))
>>> round(float(np.std(offs)), 3)
0.01
>>> gaussian_humanizer()([0.0, 1.0], None)
[0.0, 0.0]
```

### an.impacts.performance.perform(tempo=100.0, , beats=16, subdivision=1, pattern=(1.0,), lead_in=0.5, humanizer=None, seed=0)

The impacts of `beats` beats of `pattern`, on `tempo`’s grid.

`subdivision` grid steps per beat; `pattern` is cycled over the steps,
one value per step: `0` is a rest, anything in `(0, 1]` is a hit of that
relative stroke height (an accent is a bigger stroke). `lead_in` shifts
beat 0 to that many seconds into the clip. `humanizer` turns grid times
into offsets (default: none); each offset is then clamped to
[`MAX_OFFSET_FRACTION`](#an.impacts.performance.MAX_OFFSET_FRACTION) of the gap to either neighbour, and the clamped
value is what the event records — the ground truth is what was executed.

* **Return type:**
  `tuple`[[`ImpactEvent`](#an.impacts.performance.ImpactEvent), `...`]

```pycon
>>> [e.beat for e in perform(120, beats=2, subdivision=2, pattern=(1, 0))]
[0.0, 1.0]
>>> [e.amplitude for e in perform(120, beats=1, subdivision=4, pattern=(1, .5))]
[1.0, 0.5, 1.0, 0.5]
```

### an.impacts.performance.tempo_map(tempo)

Coerce a bpm, a `[(beat, bpm), ...]` list, or a [`TempoMap`](#an.impacts.performance.TempoMap).

* **Return type:**
  [`TempoMap`](#an.impacts.performance.TempoMap)

```pycon
>>> tempo_map(90).points
((0.0, 90.0),)
>>> tempo_map([(0, 90), (16, 120)]).points
((0.0, 90.0), (16.0, 120.0))
```
