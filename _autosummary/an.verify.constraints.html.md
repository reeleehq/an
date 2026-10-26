# an.verify.constraints

Constraints: declarative statements a lint checks and a solver may enforce (an#497).

A constraint says something about the world the shots show that must stay true:
a node does not jump within a shot, two solids do not pass through each other, a
prop meets the body it is drawn on. It is declared once and has up to two faces
(the constraints catalogue, `misc/docs/constraints_catalogue.md`):

- a **check**: a lint, run by `an validate` through the semantic-check registry
  ([`an.genres.SemanticCheck`](an.genres.html.md#an.genres.SemanticCheck)). It reads a
  [`an.ir.validate.ValidationContext`](an.ir.validate.html.md#an.ir.validate.ValidationContext) and adds findings to `ctx.report`;
- a **term**, optional: the residual the kinematic layer’s solver drives to zero,
  for a constraint that is enforced as well as checked. `None` means lint-only,
  and that is the legitimate default rather than a stub: draw order is derived
  from depth and continuity comes from solving each frame from the previous one,
  so neither has a residual.

Every constraint ships as a lint before it is a term, and a term never replaces
the lint: what the solver produces is checked again by the same `check`.

The one example a genre or a later batch copies (P2’s `joint_violation`):

```pycon
>>> def joint_check(ctx):
...     "Every joint of ctx.shot holds at every sampled instant, else ctx.report.add(...)."
>>> def joint_term(state):
...     "The solver's residual for one joint: zero when its two bodies meet there."
...     return 0.0
>>> JOINT = Constraint("joint_violation", joint_check, term=joint_term,
...                    description="a joint's two bodies meet at the joint")
>>> check = JOINT.semantic_check()
>>> check.name, check.stage, check.order == DFLT_ORDER, JOINT.term is joint_term
('joint_violation', 'shot', True, True)
```

A genre registers it like any check (`Genre(checks=(JOINT.semantic_check(),))`);
the core’s own are [`CONSTRAINTS`](#an.verify.constraints.CONSTRAINTS), registered when this module is imported
(`an.ir` imports it, so `validate_semantic` always has them, the way the core’s
other checks are registered when `an.ir.validate` is).

The core’s constraints:

- `continuity` (an#508, catalogue B1): a node does not jump within a shot
  unless a `set` says so, and a value is not held for less than a frame.
  [`discontinuities()`](#an.verify.constraints.discontinuities) is the pure function under it.
- `solidity` (an#509, catalogue A2): two solids (characters and props) whose
  boxes overlap, with no `stage.after` between them, are drawn through each
  other. `solid_overlaps()` is the pure function under it.
- `draw_order` (an#510, catalogue A3): two entities painted one way in one
  shot and the other way in a later one, with no change of `stage.after`
  between them. `order_flips()` is the pure function under it. (The
  within-shot half, painted order against world depth, is not built.)
- `jump_cut` (catalogue C4, the 30-degree rule): two consecutive shots of one
  subject from nearly the same angle and size. `jump_cut_between()` is the
  pure function under it.
- `object_permanence` (catalogue C1): an entity shown, then absent for whole
  shots, then shown again with no `time_jump` between and no entrance; and one
  entity drawn twice in a shot. [`vanishings()`](#an.verify.constraints.vanishings) is the pure function under it.
- `held_item` (catalogue A4, the weld): an item declared held by a node
  (`Shot.welds`) stays at its offset from the carrier between pick-up and
  release. [`weld_drifts()`](#an.verify.constraints.weld_drifts) is the pure function under it.
- `rigidity` (catalogue A5): an entity that declares `overrides: {rigid: true}`
  keeps its aspect (`scale_x` against `scale_y`) through the shot; one that
  declares `overrides: {preserve_volume: true}` keeps `scale_x * scale_y`.
  [`shape_drifts()`](#an.verify.constraints.shape_drifts) is the pure function under it. Opt-in, since the
  > `squash_stretch` preset deforms on purpose.
- `motion_style` (catalogue B2, B5): the style pack’s `motion` targets,
  measured on the compiled shot: `smoothness` (the log dimensionless jerk of
  each move) and `anticipation` (a big move is preceded by a small counter-move).
  [`move_jerk()`](#an.verify.constraints.move_jerk) and [`unanticipated()`](#an.verify.constraints.unanticipated) are the pure functions under it.

  Silent when the pack declares no `motion`. Arcs and overlap are not built.
- `gravity` (catalogue B4): under a style pack that declares `gravity`, an
  entity declaring `overrides: {airborne: {from, until}}` follows a parabola
  (constant downward acceleration) and does not hover. [`airborne_faults()`](#an.verify.constraints.airborne_faults)
  is the pure function under it. Unsupported falls and hangs wait on supports
  (catalogue A1) and joints.
- `causality` (catalogue B7): a shot sound cue that names its visible `cause`
  (a [`CueAnchor`](an.ir.schema.html.md#an.ir.schema.CueAnchor)) is not ahead of it (error past
  `CAUSE_TOLERANCE`) and sits within the audio-visual sync window
  > (warning). [`av_offset_fault()`](#an.verify.constraints.av_offset_fault) is the pure function under it. Dialogue and
  > lip-sync consistency are not built.

### Module Attributes

| [`CONSTRAINTS`](#an.verify.constraints.CONSTRAINTS)   | The core's constraints, in the order their checks run within a stage.   |
|----------------------------------------------------------------|-------------------------------------------------------------------------|

### Functions

| [`av_offset_fault`](#an.verify.constraints.av_offset_fault)(sound_t, cause_t)                  | How a sound at `sound_t` sits against its visible cause at `cause_t` (seconds): `None` inside the window, else `"early"` (sound ahead, past the window), `"late"` (behind), or `"before_cause"` (ahead by more than `CAUSE_TOLERANCE`).                                          |
|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`airborne_faults`](#an.verify.constraints.airborne_faults)(ys, dt, \*[, strength])            | What is wrong with a flight sampled as `ys` (screen y, down is positive) every `dt` s: `hover` (level for more than `HOVER_FRAMES`), `straight` (no downward acceleration: not a throw), `not_parabolic` (the acceleration is not constant), `strength` (not the declared pull). |
| [`move_jerk`](#an.verify.constraints.move_jerk)(values, dt)                              | The log dimensionless jerk `ln(T^5 / A^2 * integral |jerk|^2 dt)` of a move sampled every `dt` s: lower is smoother.                                                                                                                                                             |
| [`unanticipated`](#an.verify.constraints.unanticipated)(moves, \*, min_move, frames, fps)    | The moves of at least `min_move` with no anticipation: a move of the same channel, the other way, at most half as far, lasting `frames` frames, that ends at the big move's start (to within a frame).                                                                           |
| [`shape_drifts`](#an.verify.constraints.shape_drifts)(entity, samples, \*, quantity[, ...]) | The first of `samples` `(t, scale_x, scale_y)` whose `quantity` has left its starting value by more than `tolerance` (a fraction), as one drift carrying the worst ratio seen from then on.                                                                                      |
| [`weld_drifts`](#an.verify.constraints.weld_drifts)(samples, \*[, index, offset, ...])     | The first instant of `samples` `(t, carrier centre, item centre)` at which the item is more than `tolerance` from its `offset` to the carrier (the first sample's offset when `offset` is `None`), as one drift: the worst distance seen from then on.                           |
| [`vanishings`](#an.verify.constraints.vanishings)(presence, time_jumps[, entrances])      | The entities that vanish and return with nothing to explain it.                                                                                                                                                                                                                  |
| [`compile_outcome`](#an.verify.constraints.compile_outcome)(ctx)                               | `ctx.shot` compiled as `an render` compiles it, once per validation: `(document, None)`, `(None, the compile error)`, or `(None, None)` for a shot the stage does not render.                                                                                                    |
| [`compiled_shot`](#an.verify.constraints.compiled_shot)(ctx)                                 | The document of [`compile_outcome()`](#an.verify.constraints.compile_outcome), `None` for a shot the stage does not render or that does not compile: the checks that own those problems report them, and a constraint says nothing about a shot it could not see.           |
| [`continuity_findings`](#an.verify.constraints.continuity_findings)(doc, \*, duration, fps[, ...]) | `[(severity, ir path, message)]` for a compiled shot's jumps and short holds.                                                                                                                                                                                                    |
| [`discontinuities`](#an.verify.constraints.discontinuities)(timeline, \*, rest, duration)      | Every instant in `(0, duration]` where a numeric value of `timeline` jumps: the pose read just before the instant and just after it differ beyond `CONTINUITY_TOLERANCE`.                                                                                                        |
| [`short_holds`](#an.verify.constraints.short_holds)(timeline, \*, fps)                     | Step-held values shown for less than a frame: two `set``s of one property closer than ``1/fps`, so the first may never land on a frame.                                                                                                                                          |

### Classes

| [`Constraint`](#an.verify.constraints.Constraint)(name, check[, stage, order, ...])     | One constraint: a declarative statement with a `check` and, optionally, a `term`.                           |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| [`Move`](#an.verify.constraints.Move)(key, start, end, delta)                     | One clip's change of one channel: from `start` to `end` s, by `delta`.                                      |
| [`ShapeDrift`](#an.verify.constraints.ShapeDrift)(entity, quantity, at, ratio)          | The `quantity` (`aspect` or `volume`) of `entity` is `ratio` times its start at `at` s.                     |
| [`WeldDrift`](#an.verify.constraints.WeldDrift)(index, at, distance)                   | The item of weld `index` is `distance` px from where it is held, at `at` s.                                 |
| [`Vanishing`](#an.verify.constraints.Vanishing)(entity, before, after)                 | `entity` is in shot `before` and again in shot `after` (timeline indices) but in none of the shots between. |
| [`Discontinuity`](#an.verify.constraints.Discontinuity)(target, property, at, before, ...) | A numeric channel of `target` that jumps at `at` (seconds into the shot).                                   |
| [`ShortHold`](#an.verify.constraints.ShortHold)(target, property, at, value, held_s)   | A step-held value of `target`'s `property` shown for less than a frame.                                     |

### an.verify.constraints.CONSTRAINTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Constraint](#an.verify.constraints.Constraint), ...]* *= (Constraint(name='continuity', check=<function check_continuity>, stage='shot', order=200.0, description='a node does not jump within a shot unless a set says so (an#508)', term=None), Constraint(name='solidity', check=<function check_solidity>, stage='shot', order=200.0, description='two solids are not drawn through each other unless one is placed after (an#509)', term=None), Constraint(name='draw_order', check=<function check_draw_order>, stage='finish', order=200.0, description='two entities are painted in the same order in every shot unless \`after\` changes (an#510)', term=None), Constraint(name='jump_cut', check=<function check_jump_cut>, stage='finish', order=200.0, description='consecutive shots of one subject differ by 30 degrees or a shot size', term=None), Constraint(name='object_permanence', check=<function check_object_permanence>, stage='finish', order=200.0, description='an entity does not vanish and return across shots, nor appear twice in one (catalogue C1)', term=None), Constraint(name='held_item', check=<function check_held_item>, stage='shot', order=200.0, description='an item declared held stays at its offset from its carrier between pick-up and release (catalogue A4)', term=None), Constraint(name='rigidity', check=<function check_rigidity>, stage='shot', order=200.0, description='an entity declared rigid keeps its proportions, one declared volume-preserving keeps its area (catalogue A5)', term=None), Constraint(name='motion_style', check=<function check_motion_style>, stage='shot', order=200.0, description='moves are as smooth, and big moves as anticipated, as the style pack declares (catalogue B2, B5)', term=None), Constraint(name='gravity', check=<function check_gravity>, stage='shot', order=200.0, description='an entity declared airborne follows a parabola and does not hover under a style that declares gravity (catalogue B4)', term=None), Constraint(name='causality', check=<function check_causality>, stage='shot', order=200.0, description='a sound cue that names its visible cause is not ahead of it, and is within the audio-visual sync window (catalogue B7)', term=None))*

The core’s constraints, in the order their checks run within a stage.

### *class* an.verify.constraints.Constraint(name, check, stage='shot', order=200.0, description='', term=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One constraint: a declarative statement with a `check` and, optionally, a `term`.

`check(ctx)` is SemanticCheck-shaped (it adds findings to `ctx.report`);
`stage`, `order` and `description` are the registry’s. `term` is the
solver residual hook the kinematic layer’s `solve` pass consumes: a callable
returning the residual(s), zero when the constraint holds, in the units of the
constrained quantity. `None` is lint-only.

```pycon
>>> c = Constraint("holds", lambda ctx: None, stage="finish", order=5.0)
>>> c.semantic_check().stage, c.term
('finish', None)
```

#### semantic_check()

The registry’s view of this constraint: its `check`, to register.

* **Return type:**
  [`SemanticCheck`](an.genres.registry.html.md#an.genres.registry.SemanticCheck)

### *class* an.verify.constraints.Discontinuity(target, property, at, before, after, cause, deliberate)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A numeric channel of `target` that jumps at `at` (seconds into the shot).

#### cause *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

an action begins there from a value the node is not at;
`end`: the action governing the value ends there and another one, running
underneath, takes over; `loop`: a looping clip restarts there.

* **Type:**
  `start`

#### deliberate *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

the author’s.

* **Type:**
  A `set` (a step-held value equal to what shows) explains it

### *class* an.verify.constraints.Move(key, start, end, delta)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One clip’s change of one channel: from `start` to `end` s, by `delta`.

### *class* an.verify.constraints.ShapeDrift(entity, quantity, at, ratio)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The `quantity` (`aspect` or `volume`) of `entity` is `ratio` times its start at `at` s.

### *class* an.verify.constraints.ShortHold(target, property, at, value, held_s)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A step-held value of `target`’s `property` shown for less than a frame.

### *class* an.verify.constraints.Vanishing(entity, before, after)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`entity` is in shot `before` and again in shot `after` (timeline
indices) but in none of the shots between.

### *class* an.verify.constraints.WeldDrift(index, at, distance)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The item of weld `index` is `distance` px from where it is held, at `at` s.

### an.verify.constraints.airborne_faults(ys, dt, , strength=None)

What is wrong with a flight sampled as `ys` (screen y, down is positive)
every `dt` s: `hover` (level for more than `HOVER_FRAMES`),
`straight` (no downward acceleration: not a throw), `not_parabolic`
(the acceleration is not constant), `strength` (not the declared pull).

```pycon
>>> g = 1200.0
>>> arc = [-300 * (i / 30) + 0.5 * g * (i / 30) ** 2 for i in range(20)]
>>> airborne_faults(arc, 1 / 30)
[]
>>> airborne_faults([i * 5.0 for i in range(20)], 1 / 30)
['straight']
>>> airborne_faults([40.0] * 20, 1 / 30)
['hover']
>>> airborne_faults(arc, 1 / 30, strength=300.0)
['strength']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.verify.constraints.av_offset_fault(sound_t, cause_t)

How a sound at `sound_t` sits against its visible cause at `cause_t` (seconds): `None` inside the window, else `"early"` (sound ahead, past the window), `"late"` (behind), or `"before_cause"` (ahead by more than `CAUSE_TOLERANCE`).

```pycon
>>> av_offset_fault(1.0, 1.02), av_offset_fault(1.1, 1.0)
(None, None)
>>> av_offset_fault(1.0, 1.1), av_offset_fault(1.2, 1.0)
('early', 'late')
>>> av_offset_fault(0.5, 1.0)
'before_cause'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.verify.constraints.compile_outcome(ctx)

`ctx.shot` compiled as `an render` compiles it, once per validation:
`(document, None)`, `(None, the compile error)`, or `(None, None)` for
a shot the stage does not render.

The stores validate was given stand in for the mall; the scene’s frame rate
(the render’s when `an validate --fps` says), resolution, step grid,
default easing and **style pack** are the ones the render uses, so what is
linted is the document that is drawn: the `solve` pass reads the pack’s
gravity and damping, and a document compiled without them is a different
solve (an#534). Every compile-based check reads this one document.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### an.verify.constraints.compiled_shot(ctx)

The document of [`compile_outcome()`](#an.verify.constraints.compile_outcome), `None` for a shot the stage
does not render or that does not compile: the checks that own those
problems report them, and a constraint says nothing about a shot it could
not see.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.verify.constraints.continuity_findings(doc, , duration, fps, path='')

`[(severity, ir path, message)]` for a compiled shot’s jumps and short holds.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.verify.constraints.discontinuities(timeline, , rest, duration)

Every instant in `(0, duration]` where a numeric value of `timeline`
jumps: the pose read just before the instant and just after it differ
beyond `CONTINUITY_TOLERANCE`. `rest` is each `(target, property)`’s
value while nothing writes it (the node’s own transform); a key absent from
both the pose and `rest` is not judged.

A tween with a `from` the node is not at jumps where it starts; two tweens
on one property jump where the later one starts and again where it ends and
the earlier one shows through; a loop whose last pose is not its first jumps
at each restart. A `set` is a jump the author wrote: it is reported with
`deliberate=True`, for the caller to leave alone.

```pycon
>>> from an.timing.channel import Channel, Keyframe
>>> from an.timing.clip import Clip
>>> from an.timing.timeline import PlacedClip, Timeline, Track
>>> rise = Clip("rise", 1.0, [Channel("a", "y", [Keyframe(0.0, 3.0, "linear"), Keyframe(1.0, 10.0)])])
>>> tl = Timeline(2.0, [Track("a", [PlacedClip(rise, start_time=0.5)])])
>>> (d,) = discontinuities(tl, rest={("a", "y"): 0.0}, duration=2.0)
>>> d.at, d.before, d.after, d.cause, d.deliberate
(0.5, 0.0, 3.0, 'start', False)
>>> hold = Clip("hold", 1.5, [Channel("a", "y", [Keyframe(0.0, 3.0, "step")])])
>>> tl = Timeline(2.0, [Track("a", [PlacedClip(hold, start_time=0.5), PlacedClip(rise, start_time=0.5)])])
>>> discontinuities(tl, rest={("a", "y"): 0.0}, duration=2.0)[0].deliberate
True
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Discontinuity`](#an.verify.constraints.Discontinuity)]

### an.verify.constraints.move_jerk(values, dt)

The log dimensionless jerk `ln(T^5 / A^2 * integral |jerk|^2 dt)` of a move
sampled every `dt` s: lower is smoother. A minimum-jerk move scores about `ln 720`
(6.6) whatever its size and duration; corners score far higher. `None` for a
move too short or too small to measure.

```pycon
>>> import math
>>> s = [10 * u**3 - 15 * u**4 + 6 * u**5 for u in (i / 60 for i in range(61))]
>>> 6.0 < move_jerk(s, 1 / 30) < 7.0
True
>>> linear = [i / 60 for i in range(61)]
>>> move_jerk(linear, 1 / 30) > 9
True
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.verify.constraints.shape_drifts(entity, samples, , quantity, tolerance=None)

The first of `samples` `(t, scale_x, scale_y)` whose `quantity` has left
its starting value by more than `tolerance` (a fraction), as one drift
carrying the worst ratio seen from then on.

```pycon
>>> squash = [(0.0, 1.0, 1.0), (0.5, 1.2, 0.8), (1.0, 1.0, 1.0)]
>>> shape_drifts("ball", squash, quantity="volume")
[]
>>> [round(d.ratio, 3) for d in shape_drifts("ball", squash, quantity="aspect")]
[1.5]
>>> shape_drifts("ball", [(0.0, 1.0, 1.0), (1.0, 1.5, 1.0)], quantity="volume")[0].ratio
1.5
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`ShapeDrift`](#an.verify.constraints.ShapeDrift)]

### an.verify.constraints.short_holds(timeline, , fps)

Step-held values shown for less than a frame: two `set``s of one property
closer than ``1/fps`, so the first may never land on a frame.

```pycon
>>> from an.timing.channel import Channel, Keyframe
>>> from an.timing.clip import Clip
>>> from an.timing.timeline import PlacedClip, Timeline, Track
>>> sets = Clip("sets", 1.0, [Channel("a", "x", [Keyframe(0.0, 5.0, "step"), Keyframe(0.01, 0.0, "step")])])
>>> tl = Timeline(2.0, [Track("a", [PlacedClip(sets, start_time=0.5)])])
>>> [(h.at, h.value, round(h.held_s, 3)) for h in short_holds(tl, fps=24)]
[(0.5, 5.0, 0.01)]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`ShortHold`](#an.verify.constraints.ShortHold)]

### an.verify.constraints.unanticipated(moves, , min_move, frames, fps)

The moves of at least `min_move` with no anticipation: a move of the same
channel, the other way, at most half as far, lasting `frames` frames, that
ends at the big move’s start (to within a frame).

```pycon
>>> big = Move(("a", "x"), 1.0, 2.0, 100.0)
>>> wind = Move(("a", "x"), 0.8, 1.0, -20.0)
>>> unanticipated([wind, big], min_move=50.0, frames=(3, 10), fps=24.0)
[]
>>> unanticipated([big], min_move=50.0, frames=(3, 10), fps=24.0) == [big]
True
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Move`](#an.verify.constraints.Move)]

### an.verify.constraints.vanishings(presence, time_jumps, entrances=None)

The entities that vanish and return with nothing to explain it.

`presence[i]` is the ids drawn in shot `i`; `time_jumps[i]` says the
transition into shot `i` passes time; `entrances[i]` is the ids shot `i`
opens by acting on. A return after absent shots is explained by a time jump
into any shot from the first absent one to the returning one, or by an entrance.

```pycon
>>> shots = [frozenset({"a"}), frozenset(), frozenset({"a"})]
>>> vanishings(shots, [False] * 3)
[Vanishing(entity='a', before=0, after=2)]
>>> vanishings(shots, [False, False, True])
[]
>>> vanishings(shots, [False] * 3, [frozenset(), frozenset(), frozenset({"a"})])
[]
>>> vanishings([frozenset({"a"}), frozenset({"a"})], [False] * 2)
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Vanishing`](#an.verify.constraints.Vanishing)]

### an.verify.constraints.weld_drifts(samples, , index=0, offset=None, tolerance=4.0)

The first instant of `samples` `(t, carrier centre, item centre)` at which
the item is more than `tolerance` from its `offset` to the carrier (the
first sample’s offset when `offset` is `None`), as one drift: the worst
distance seen from then on.

```pycon
>>> held = [(0.0, (0, 0), (10, 0)), (1.0, (50, 0), (60, 0))]
>>> weld_drifts(held)
[]
>>> weld_drifts([*held, (2.0, (90, 0), (60, 0))])
[WeldDrift(index=0, at=2.0, distance=40.0)]
>>> weld_drifts(held, offset=(0, 0))[0].distance
10.0
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`WeldDrift`](#an.verify.constraints.WeldDrift)]
