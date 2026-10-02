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

### Module Attributes

| [`INHERIT`](#an.ir.compose.INHERIT)    | `tween(..., easing=INHERIT)` — the default — leaves the easing UNSET, so the scene's `meta.default_easing` applies, else `"ease_in_out"` (an#166).   |
|-------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`PlayExtent`](#an.ir.compose.PlayExtent) | `PlayAction -> seconds` a play WITHOUT an explicit `duration` occupies in a `sequence`.                                                              |

### Functions

| [`delay`](#an.ir.compose.delay)(duration)                                  | An empty span that consumes time.                                                                                              |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| [`duration_of`](#an.ir.compose.duration_of)(action, \*[, play_extent])           | Compute the total duration of an action tree without evaluating it.                                                            |
| [`flatten`](#an.ir.compose.flatten)(action, \*[, start, play_extent])        | Walk a composition tree, emitting leaf actions with absolute times.                                                            |
| [`iter_actions`](#an.ir.compose.iter_actions)(action)                             | `action` and every action under it, depth first (composites through their kind's `children` hook).                             |
| [`kind_of`](#an.ir.compose.kind_of)(action)                                  | The registered [`ActionKind`](an.genres.md#an.genres.ActionKind) that governs `action`.         |
| [`loop`](#an.ir.compose.loop)(action, count)                              | Repeat `action` `count` times.                                                                                                 |
| [`parallel`](#an.ir.compose.parallel)(\*actions)                              | Run all children at once.                                                                                                      |
| [`resolve_action`](#an.ir.compose.resolve_action)(action)                           | `action` as its registered model (an `ExtensionAction` left open by a document read before its genre loaded is validated now). |
| [`sequence`](#an.ir.compose.sequence)(\*actions)                              | Run children one after the other.                                                                                              |
| [`set_`](#an.ir.compose.set_)(target, property, value, \*[, at])          | Discrete property set at time `at` (relative to its enclosing scope).                                                          |
| [`stagger`](#an.ir.compose.stagger)(lag, \*actions)                          | Start each action `lag` seconds after the previous one STARTS.                                                                 |
| [`tween`](#an.ir.compose.tween)(target, property, to, duration, \*[, ...]) | Animate a property from `from_` (or its current value) to `to`.                                                                |

### Classes

| [`FlatAction`](#an.ir.compose.FlatAction)(start, end, action)   | A leaf action with its absolute start and end times.                    |
|-----------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`FlattenContext`](#an.ir.compose.FlattenContext)(out[, extent])    | What a kind's `flatten` hook gets: where to put leaves, how to recurse. |

### *class* an.ir.compose.FlatAction(start, end, action)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A leaf action with its absolute start and end times.

The flat-form list is the canonical representation passed to renderers
and verifiers. Composition nodes (sequence/parallel/delay/loop) do not
appear in the flat form — they’re collapsed into time offsets.

### *class* an.ir.compose.FlattenContext(out, extent=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a kind’s `flatten` hook gets: where to put leaves, how to recurse.

`extent` is the caller’s extent resolver ([`PlayExtent`](#an.ir.compose.PlayExtent)), passed on
to every leaf’s `duration` hook.

#### flatten(action, t)

Flatten `action` starting at `t`; return the new cursor.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.ir.compose.INHERIT *= INHERIT*

`tween(..., easing=INHERIT)` — the default — leaves the easing UNSET, so
the scene’s `meta.default_easing` applies, else `"ease_in_out"` (an#166).
A sentinel rather than `None` because `None` already means linear.

### an.ir.compose.PlayExtent

`PlayAction -> seconds` a play WITHOUT an explicit `duration` occupies in
a `sequence`. The default is `default_play_extent()`; the compiler and
`an validate` pass one bound to the entity’s descriptor. Generically, it is
the caller’s **extent resolver**: it is handed to every leaf kind’s
`duration` hook ([`an.genres.ActionKind`](an.genres.md#an.genres.ActionKind)), and the kinds that have an
open-ended length (the cut-out genre’s `play`) consult it.

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.ir.compose.delay(duration)

An empty span that consumes time. Useful inside `sequence`.

* **Return type:**
  [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction)

### an.ir.compose.duration_of(action, , play_extent=None)

Compute the total duration of an action tree without evaluating it.

`play_extent` resolves a duration-less `play` (see [`PlayExtent`](#an.ir.compose.PlayExtent)).

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

### an.ir.compose.flatten(action, , start=0.0, play_extent=None)

Walk a composition tree, emitting leaf actions with absolute times.

A `play` without `duration` advances a `sequence` by `play_extent`
(default `default_play_extent()`): its natural length, or zero for a
looping animation, which runs to the shot end.

Delays are absorbed into the timeline (they don’t appear in the output).
Loops are unrolled by simple repetition — appropriate at v0.1; the cutout
runtime can re-roll for efficiency later.

Every node is dispatched through its registered kind
([`ActionKind`](an.genres.md#an.genres.ActionKind)), so a genre’s kind flattens without an
edit here; a node whose kind nobody registered raises, naming the genre
that provides it, and an `ExtensionAction` read before its genre
loaded is validated by the registered model on the way through.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`FlatAction`](#an.ir.compose.FlatAction)]

### an.ir.compose.iter_actions(action)

`action` and every action under it, depth first (composites through
their kind’s `children` hook). Unregistered kinds are yielded, not raised:
a validator walks with this to REPORT them.

```pycon
>>> [a.kind for a in iter_actions(sequence(delay(1.0), loop(delay(0.5), 2)))]
['sequence', 'delay', 'loop', 'delay']
```

### an.ir.compose.kind_of(action)

The registered [`ActionKind`](an.genres.md#an.genres.ActionKind) that governs `action`.

Raises [`UnregisteredKindError`](an.genres.md#an.genres.UnregisteredKindError), naming the genre that
provides it, for a kind nobody registered.

* **Return type:**
  [`ActionKind`](an.genres.registry.md#an.genres.registry.ActionKind)

```pycon
>>> kind_of(delay(1.0)).name
'delay'
```

### an.ir.compose.loop(action, count)

Repeat `action` `count` times.

* **Return type:**
  [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction)

### an.ir.compose.parallel(\*actions)

Run all children at once. Total duration = max of child durations.

* **Return type:**
  [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction)

### an.ir.compose.resolve_action(action)

`action` as its registered model (an `ExtensionAction` left open
by a document read before its genre loaded is validated now).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> resolve_action(delay(0.5)).duration
0.5
```

### an.ir.compose.sequence(\*actions)

Run children one after the other. Total duration = sum of child durations.

* **Return type:**
  [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction)

### an.ir.compose.set_(target, property, value, , at=0.0)

Discrete property set at time `at` (relative to its enclosing scope).

* **Return type:**
  [`SetAction`](an.ir.schema.md#an.ir.schema.SetAction)

### an.ir.compose.stagger(lag, \*actions)

Start each action `lag` seconds after the previous one STARTS.

The **stagger** (Manim’s `LaggedStart`, `previz`’s compose, a crowd
entering one by one): the children run in parallel, the `i`-th delayed
by `i * lag`. It is authoring sugar, not a new kind — it builds the
`parallel` of `sequence(delay(i * lag), action)` it means, so the
scene document, `scene.md` and every renderer see only core kinds.
Total duration: the latest child’s end. `scene.md` holds it verbatim (a
`kind: parallel` entry), so it round-trips. (`an.stage.text.reveal_units` —
`an.stage.text.stagger` before an#241 — is the text-block preset: a LIST of
per-unit actions with holds, not a combinator.)

* **Return type:**
  [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction)

```pycon
>>> flat = flatten(stagger(0.25, tween("a", "x", to=1.0, duration=1.0),
...                              tween("b", "x", to=1.0, duration=1.0),
...                              tween("c", "x", to=1.0, duration=1.0)))
>>> [(f.action.target, f.start, f.end) for f in flat]
[('a', 0.0, 1.0), ('b', 0.25, 1.25), ('c', 0.5, 1.5)]
>>> duration_of(stagger(0.5, delay(1.0), delay(1.0)))
1.5
>>> stagger(0.1).children
[]
>>> stagger(-1.0, delay(1.0))
Traceback (most recent call last):
...
ValueError: stagger lag must be >= 0, got -1.0
```

### an.ir.compose.tween(target, property, to, duration, , from_=None, easing=INHERIT)

Animate a property from `from_` (or its current value) to `to`.

`easing` left out inherits the scene’s `meta.default_easing` (else
`"ease_in_out"`); naming one — `"ease_in_out"` included — pins it.

* **Return type:**
  [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction)

```pycon
>>> "easing" in tween("a", "x", to=1.0, duration=1.0).model_fields_set
False
>>> tween("a", "x", to=1.0, duration=1.0, easing="linear").easing
'linear'
```
