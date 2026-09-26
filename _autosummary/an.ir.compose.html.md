# an.ir.compose

Composition combinators for authoring action trees, plus a flattener.

The composition tree is the *authoring* form. The flat list of 

```
`
```

FlatAction\`s
with absolute start times is the *canonical* form that gets verified, cached,
and rendered. Both forms round-trip through the schema; the flat form is
what tooling reasons about.

```pycon
>>> from an.ir.compose import sequence, parallel, tween, delay, flatten
>>> action = sequence(
...     tween("charlie/torso", "rotation", to=10.0, duration=1.0),
...     delay(0.5),
...     tween("charlie/torso", "rotation", to=0.0, duration=1.0),
... )
>>> flat = flatten(action)
>>> [round(f.start, 3) for f in flat]
[0.0, 1.5]
>>> [round(f.end, 3) for f in flat]
[1.0, 2.5]
>>> action2 = parallel(
...     tween("a", "x", to=1.0, duration=2.0),
...     tween("b", "y", to=1.0, duration=3.0),
... )
>>> flat2 = flatten(action2)
>>> [(round(f.start, 2), round(f.end, 2)) for f in flat2]
[(0.0, 2.0), (0.0, 3.0)]
```

### Functions

| [`delay`](#an.ir.compose.delay)(duration)                                  | An empty span that consumes time.                                     |
|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`duration_of`](#an.ir.compose.duration_of)(action)                              | Compute the total duration of an action tree without evaluating it.   |
| [`expression`](#an.ir.compose.expression)(target[, preset, axes, ...])          | Hold a facial expression on an entity (an#98).                        |
| [`flatten`](#an.ir.compose.flatten)(action, \*[, start])                     | Walk a composition tree, emitting leaf actions with absolute times.   |
| [`loop`](#an.ir.compose.loop)(action, count)                              | Repeat `action` `count` times.                                        |
| [`parallel`](#an.ir.compose.parallel)(\*actions)                              | Run all children at once.                                             |
| [`play`](#an.ir.compose.play)(target, animation, \*[, duration, ...])     | Play a named animation of the target entity's descriptor (an#7).      |
| [`sequence`](#an.ir.compose.sequence)(\*actions)                              | Run children one after the other.                                     |
| [`set_`](#an.ir.compose.set_)(target, property, value, \*[, at])          | Discrete property set at time `at` (relative to its enclosing scope). |
| [`tween`](#an.ir.compose.tween)(target, property, to, duration, \*[, ...]) | Animate a property from `from_` (or its current value) to `to`.       |

### Classes

| [`FlatAction`](#an.ir.compose.FlatAction)(start, end, action)   | A leaf action with its absolute start and end times.   |
|-----------------------------------------------------------------------------------|--------------------------------------------------------|

### *class* an.ir.compose.FlatAction(start, end, action)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A leaf action with its absolute start and end times.

The flat-form list is the canonical representation passed to renderers
and verifiers. Composition nodes (sequence/parallel/delay/loop) do not
appear in the flat form — they’re collapsed into time offsets.

### an.ir.compose.delay(duration)

An empty span that consumes time. Useful inside `sequence`.

* **Return type:**
  [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction)

### an.ir.compose.duration_of(action)

Compute the total duration of an action tree without evaluating it.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> duration_of(tween("a", "x", to=1.0, duration=2.0))
2.0
>>> duration_of(sequence(delay(0.5), tween("a", "x", to=1.0, duration=1.5)))
2.0
>>> duration_of(parallel(delay(0.5), delay(2.5)))
2.5
>>> duration_of(loop(delay(0.25), 4))
1.0
>>> duration_of(set_("a", "x", 1.0))
0.0
```

### an.ir.compose.expression(target, preset=None, , axes=None, intensity=1.0, duration=None, blend=0.15)

Hold a facial expression on an entity (an#98).

`duration=None` runs to the shot end and counts as **zero** in a
`sequence`, like `play`:

* **Return type:**
  [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction)

```pycon
>>> [f.start for f in flatten(sequence(expression("a", "happy"), delay(1.0), expression("a", "sad")))]
[0.0, 1.0]
>>> flatten(expression("a", "angry", duration=2.0))[0].end
2.0
```

### an.ir.compose.flatten(action, , start=0.0)

Walk a composition tree, emitting leaf actions with absolute times.

Delays are absorbed into the timeline (they don’t appear in the output).
Loops are unrolled by simple repetition — appropriate at v0.1; the cutout
runtime can re-roll for efficiency later.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`FlatAction`](#an.ir.compose.FlatAction)]

### an.ir.compose.loop(action, count)

Repeat `action` `count` times.

* **Return type:**
  [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)

### an.ir.compose.parallel(\*actions)

Run all children at once. Total duration = max of child durations.

* **Return type:**
  [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction)

### an.ir.compose.play(target, animation, , duration=None, speed=1.0, loop=None)

Play a named animation of the target entity’s descriptor (an#7).

`duration=None` fills the animation’s natural length — or the shot’s
remainder for a looping one — but counts as **zero** in a `sequence`,
so a sibling placed after it starts at the same instant:

* **Return type:**
  [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction)

```pycon
>>> [f.start for f in flatten(sequence(play("a", "idle_breath"), delay(1.0), play("a", "blink")))]
[0.0, 1.0]
>>> [f.start for f in flatten(sequence(play("a", "idle_breath", duration=2.0), play("a", "blink")))]
[0.0, 2.0]
```

### an.ir.compose.sequence(\*actions)

Run children one after the other. Total duration = sum of child durations.

* **Return type:**
  [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction)

### an.ir.compose.set_(target, property, value, , at=0.0)

Discrete property set at time `at` (relative to its enclosing scope).

* **Return type:**
  [`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction)

### an.ir.compose.tween(target, property, to, duration, , from_=None, easing='ease_in_out')

Animate a property from `from_` (or its current value) to `to`.

* **Return type:**
  [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction)
