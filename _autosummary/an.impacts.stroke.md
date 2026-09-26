# an.impacts.stroke

The stroke: impact events -> one continuous height curve `h(t)`.

`h` is the object’s height above its impact position, in units of a full
stroke: `0` is contact (or, in the air, the turning point) and `1` a full
preparation. Every object in [`an.impacts.objects`](an.impacts.objects.md#module-an.impacts.objects) maps `h` AFFINELY onto
one animated property (a stick’s rotation, a ball’s `y`), which is what makes
the curve below exactly the curve the renderer draws: an eased tween of the
property IS the same easing of `h`.

The curve is a chain of [`StrokeSegment`](#an.impacts.stroke.StrokeSegment)s built only from the
quadratic easings the cutout runtime already has, and each is chosen for its
physics:

- **surface** — the object falls with `ease_in` (constant acceleration, like
  gravity) and reaches `h = 0` at full speed, then leaves with `ease_out`: a
  velocity reversal AT the impact. Contact is visible in position (the object
  stops at the surface) and as a kink in velocity.
- **air** — no surface. The fall is `ease_in` and then a short `ease_out`
  **brake** of `brake` seconds that brings the object to rest at `h = 0`;
  it then leaves with `ease_in_out`. The executed “impact” is that turning
  point — the moment the stroke’s lowest point is reached — and the peak speed
  comes `brake` seconds BEFORE it. The brake’s distance is chosen so velocity
  is continuous into it (`d = apex * brake / fall`), so the only
  discontinuity is in acceleration — a muscle stopping a limb, not a collision.

In both kinds the speed at the peak is `2 * apex / fall`.

```pycon
>>> from an.impacts.performance import perform
>>> events = perform(120, beats=3)
>>> s = build_stroke(events, kind="surface", duration=2.0)
>>> [s.h(e.t_impact) for e in events]
[0.0, 0.0, 0.0]
>>> round(s.h(0.0), 6), round(s.h(0.75), 6)   # at rest, then the apex between hits
(1.0, 1.0)
>>> a = build_stroke(events, kind="air", duration=2.0)
>>> [round(a.velocity(e.t_impact), 9) for e in events]   # the air stroke TURNS
[0.0, 0.0, 0.0]
```

### Module Attributes

| [`DEFAULT_RISE`](#an.impacts.stroke.DEFAULT_RISE)   | Longest rise after an impact, and longest fall into one (seconds).   |
|-----------------------------------------------------------------|----------------------------------------------------------------------|
| [`DEFAULT_BRAKE`](#an.impacts.stroke.DEFAULT_BRAKE)  | The air stroke's braking time before its turning point (seconds).    |

### Functions

| [`build_stroke`](#an.impacts.stroke.build_stroke)(events, \*[, kind, rise, fall, ...])   | Chain rise / hold / fall segments through every executed impact.   |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|

### Classes

| [`Stroke`](#an.impacts.stroke.Stroke)(kind, duration, segments, kinematics)   | The whole curve, plus the kinematics of every impact on it.   |
|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------|
| [`StrokeKinematics`](#an.impacts.stroke.StrokeKinematics)(index, kind, t_impact, ...)   | How the object moved into one impact.                         |
| [`StrokeSegment`](#an.impacts.stroke.StrokeSegment)(t0, t1, h0, h1, easing)          | `h` goes from `h0` to `h1` over `[t0, t1]` under `easing`.    |

### Exceptions

| [`StrokeError`](#an.impacts.stroke.StrokeError)   | A stroke that cannot be built from these events.   |
|----------------------------------------------------------------|----------------------------------------------------|

### an.impacts.stroke.DEFAULT_BRAKE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.03*

The air stroke’s braking time before its turning point (seconds).

### an.impacts.stroke.DEFAULT_RISE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.18*

Longest rise after an impact, and longest fall into one (seconds). A slower
tempo holds at the apex between them instead of floating: a drummer’s stroke
takes about as long at 60 BPM as at 120, it is the wait that changes.

### *class* an.impacts.stroke.Stroke(kind, duration, segments, kinematics)

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

### *exception* an.impacts.stroke.StrokeError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A stroke that cannot be built from these events.

### *class* an.impacts.stroke.StrokeKinematics(index, kind, t_impact, t_peak_speed, peak_speed, apex, fall, brake)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

How the object moved into one impact.

`t_peak_speed` equals `t_impact` for a surface impact and precedes it by
`brake` for an air impact; `peak_speed` is in stroke heights per second
(multiply by the object’s stroke extent for pixels or radians).

### *class* an.impacts.stroke.StrokeSegment(t0, t1, h0, h1, easing)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`h` goes from `h0` to `h1` over `[t0, t1]` under `easing`.

### an.impacts.stroke.build_stroke(events, , kind='surface', duration, rise=0.18, fall=0.18, brake=0.03, rest_height=1.0)

Chain rise / hold / fall segments through every executed impact.

The object starts and ends at `rest_height`; before impact `k` it is
raised to `events[k].amplitude` (a bigger preparation, a harder hit).
Segments tile `[0, duration]` exactly, and every impact is a segment
boundary at precisely `t_impact`.

* **Return type:**
  [`Stroke`](#an.impacts.stroke.Stroke)
