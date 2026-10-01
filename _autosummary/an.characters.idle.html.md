# an.characters.idle

Idle animation factories: breath, blink, weight-shift.

Defaults are taken from production references (see research §6.3):

- 15 breaths/min ⇒ 4-second period.
- ±2 px torso vertical travel at a 1024-px-tall canonical character height.
- ±0.5° head rotation, phase-offset by 0.25 cycles from the chest.
- Blink closure ≈ 0.13 s; spontaneous blink gap 3-8 s (sampled per scene).

The functions return [`an.characters.IdleAnimation`](an.characters.html.md#an.characters.IdleAnimation) instances ready
to drop into `CharacterDescriptor.animations`.

**Nothing here renders on its own.** Descriptor `animations` are seeded
by `model_post_init` and reach the screen ONLY through an authored `play`
action (an#7: `play("maya", "idle_breath")` renders exactly what
[`breath_animation()`](#an.characters.idle.breath_animation) returns — resolved by [`an.characters.play`](an.characters.play.html.md#module-an.characters.play)),
never automatically. The blink you see without one is compiled by
`an.stage.compile._add_face_clips` (an#88, via `_blink_placements`) from a fixed
entity-name-phase schedule (period 4.0 s). `random_blink_schedule` has no
caller — it is the seeded alternative the compiled blink could adopt.

One documented number is not what a `play` shows: the “4-second period”
above is `DEFAULT_BREATH_PERIOD_S`, but the seeded `idle_breath` also
carries the 6 s weight shift, and [`evaluate_track()`](#an.characters.idle.evaluate_track) divides by the
ANIMATION’s duration — `max(4, 6)` — so every sine track in it runs a 6 s
cycle. A per-track period is the fix; until then, `include_weight_shift=False`
gives the 4 s breath the numbers describe.

```pycon
>>> a = breath_animation()
>>> a.name
'idle_breath'
>>> [t.target for t in a.tracks][:2]
['bone:torso.y', 'bone:head.rotation_deg']
>>> b = blink_animation()
>>> b.duration
0.18
```

### Functions

| [`blink_animation`](#an.characters.idle.blink_animation)(\*[, closure_s, duration_s, ...])   | Step-animation that snaps both eye slots closed → open.             |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`breath_animation`](#an.characters.idle.breath_animation)(\*[, period_s, ...])               | Sine-wave breath on torso Y + head rotation; optional weight shift. |
| [`evaluate_track`](#an.characters.idle.evaluate_track)(track, t, duration)                  | Evaluate a single animation track at time `t`.                      |
| [`random_blink_schedule`](#an.characters.idle.random_blink_schedule)(duration_s, \*[, ...])        | Return a sorted list of blink start times across `duration_s`.      |

### an.characters.idle.blink_animation(, closure_s=0.13, duration_s=0.18, eye_l_slot='left_eye', eye_r_slot='right_eye', open_attachment_l='open', closed_attachment_l='closed', open_attachment_r='open', closed_attachment_r='closed', name='blink')

Step-animation that snaps both eye slots closed → open.

The closure is centred: open → closed at `(duration - closure) / 2` →
open again `closure` later. With the defaults (0.13s closure in an
0.18s envelope) that is closed at 0.025s, open at 0.155s. (An earlier
docstring claimed 0.05/0.13 — numbers from an older closure value; and
the slot/attachment defaults were the stale pre-0.2.0 spellings
`eye_l`/`eye_l_open`, unnoticed for as long as nothing consumed
`descriptor.animations` — both fixed in an#87.)

* **Return type:**
  [`IdleAnimation`](an.characters.schema.html.md#an.characters.schema.IdleAnimation)

### an.characters.idle.breath_animation(, period_s=4.0, amplitude_px=2.0, head_tilt_deg=0.5, include_weight_shift=True, weight_shift_amplitude_px=1.5, weight_shift_period_s=6.0, name='idle_breath')

Sine-wave breath on torso Y + head rotation; optional weight shift.

The head tilt is phase-offset by 0.25 cycles to follow the chest with a
natural lag. The optional weight shift is on a slower 6-second period to
avoid a metronomic feel when both run at the same time.

The animation’s `duration` is the LCM-ish combined period: the longest
sub-track period, so the overall loop closes cleanly.

* **Return type:**
  [`IdleAnimation`](an.characters.schema.html.md#an.characters.schema.IdleAnimation)

### an.characters.idle.evaluate_track(track, t, duration)

Evaluate a single animation track at time `t`.

For sine: `amplitude * sin(2π * (t/duration + phase))`.
For step: returns the value of the latest frame whose time ≤ `t`.
For linear: linear interpolation between bracketing frames.

* **Return type:**
  [`object`](https://docs.python.org/3/builtins/functions.html#object)

```pycon
>>> tr = AnimationTrack(target='bone:torso.y', type='sine', amplitude=2.0)
>>> round(evaluate_track(tr, 0.0, 4.0), 6)
0.0
>>> round(evaluate_track(tr, 1.0, 4.0), 6)
2.0
```

### an.characters.idle.random_blink_schedule(duration_s, , min_gap_s=3.0, max_gap_s=8.0, seed=None)

Return a sorted list of blink start times across `duration_s`.

A seeded schedule with uniform gaps in `[min_gap_s, max_gap_s]`. NOT
what the renderer uses today (see the module docstring); kept as the
candidate for descriptor-driven scheduling.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> times = random_blink_schedule(20.0, seed=0)
>>> all(0 <= t < 20 for t in times)
True
>>> times == sorted(times)
True
```
