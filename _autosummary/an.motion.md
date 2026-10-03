# an.motion

Motion presets: a named vocabulary of moves, as authoring macros.

`pop_in`, `hop`, `shake`, `slide_in`, `slide_out`,
`squash_stretch` and `crawl` each EXPAND to ordinary `tween` (and
`set`) actions on transform properties, composed with
[`sequence()`](an.ir.compose.md#an.ir.compose.sequence) and [`parallel()`](an.ir.compose.md#an.ir.compose.parallel). Called from
Python, nothing downstream learns a preset exists: the flat timeline, `an
validate`, the verifiers and the renderer see the same tweens an author could
have written by hand. No runtime change, and no compiled document that does not
use a preset moves by a byte.

These are the core’s presets: each moves the node it is given (an entity
container, a text block, a plane) and needs no rig. The moves that name a
rig’s parts or swap its views — `nod`, `point`, `turn`, `walk`,
`waddle`, `speech_pulse` — are the cut-out genre’s, in `cutan.motion`
(an#322); their old names here are live aliases while anything still imports
them. This module also holds what every preset is built from: the rest pose
([`rest_pose()`](#an.motion.rest_pose), [`stage_poses()`](#an.motion.stage_poses)), the landing `set`, and
[`as_leaves()`](#an.motion.as_leaves).

```pycon
>>> from an.ir.compose import flatten, sequence
>>> leaves = _tweens(sequence(pop_in("charlie"), hop("charlie"), shake("charlie")))
>>> [(f.action.target, f.action.property) for f in leaves][:3]
[('charlie', 'scale_x'), ('charlie', 'scale_y'), ('charlie', 'y')]
>>> round(leaves[-1].end, 3)
1.35
```

**Targets.** A preset targets the node it is given — usually the entity
container (`"charlie"`), the node a descriptor’s `bone:root` track animates
too. A target the built scene does not carry makes the render raise (the
runtime refuses an unknown node, naming the known ones); [`rest_pose()`](#an.motion.rest_pose)
raises for it up front, before any browser starts.

**Landing.** Every preset ends each property it moves with a `set` at the
value it ends on, so the move lands exactly whatever the frame rate or
`step_hz` (a tween ending between two frames otherwise leaves the property
where the last sampled frame had it). The `set` holds until the next tween
on that property.

**Rest.** A tween’s value is ABSOLUTE, and every preset writes its `from`
explicitly so presets chain without a jump. Each preset therefore needs the
target node’s rest value for the properties it moves; `rest=None` means the
identity pose (`x = y = rotation = 0`, `scale = 1`), which is right for
every rotation, and for `y`/`scale` of any entity without a `stage`
placement — but an entity’s `x` is laid out across the shot (`-110` and
`110` for two characters), so a move on `x` (`shake`, `slide_in`,
`slide_out`) in a shot with more than one character
wants `rest=rest_pose(shot, "charlie")`, which reads the value off the
compiler’s own scene builder rather than restating its layout.

**scene.md: play a preset by name** (an#166; `play` is the cut-out genre’s
action kind, and `cutan.motion.PRESETS` lists these presets with its own). `{kind: play, target:
charlie, animation: hop, args: {height: 30}, start: 1.0}` expands to exactly
this module’s tweens at compile, with `rest` the pose the node HAS at the
play’s start — the built scene’s (stage placement, layout) overridden by the
sets and tweens before it (an#212) — so no `rest=`, and a preset after a move
starts where the move left it (an entrance in [`HOME_PRESETS`](#an.motion.HOME_PRESETS) lands on the
built pose instead); `args` are the preset’s keyword arguments. A character
descriptor animation of the same name WINS; `an validate` and the compiler
decide both through `cutan.characters.play.play_problems()`. `duration`
stretches the move and `speed` divides it; `loop` is refused. In a
`sequence` a `play` without a `duration` occupies the preset’s own
length divided by `speed`, so two in a row run one after the other.
[`as_leaves()`](#an.motion.as_leaves) remains for a preset composed in Python and written into
`scene.md` as plain, hand-editable tweens (a composition tree round-trips
too since an#241, but verbatim, as its JSON form).

### Module Attributes

| [`OVERSHOOT`](#an.motion.OVERSHOOT)       | A cubic-Bézier that overshoots its target by about 10% and settles back (CSS "easeOutBack").                                                                                                                                                                                                    |
|------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`PRESETS`](#an.motion.PRESETS)         | the moves that need no rig.                                                                                                                                                                                                                                                                     |
| [`PRESET_VERSIONS`](#an.motion.PRESET_VERSIONS) | bump a preset's version in the SAME change that makes it expand differently for the same args, so every shot that plays it re-renders visibly instead of silently ([`an.semantic`](an.semantic.md#module-an.semantic) folds it into the shot's vocabulary digest). |
| [`HOME_PRESETS`](#an.motion.HOME_PRESETS)    | Presets whose `rest` is the node's HOME — where an entrance LANDS — rather than where the node is when the move starts.                                                                                                                                                                         |

### Functions

| [`as_leaves`](#an.motion.as_leaves)(action, \*[, start])                   | `action` as top-level leaves that `scene.md` can round-trip.                                                                                                                                                                                                                         |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`crawl`](#an.motion.crawl)(target, \*[, distance, duration, ...])     | An opening crawl: lay `target` on a plane tilted away, and slide it up and away.                                                                                                                                                                                                     |
| [`hop`](#an.motion.hop)(target, \*[, height, duration, rest])        | Jump up by `height` scene pixels and land back where it started.                                                                                                                                                                                                                     |
| [`pop_in`](#an.motion.pop_in)(target, \*[, duration, easing, rest])     | Grow from nothing to full size, overshooting and settling (an entrance).                                                                                                                                                                                                             |
| [`rest_pose`](#an.motion.rest_pose)(shot, target, \*[, mall])              | The rest values of `target`'s node as the compiler builds `shot`.                                                                                                                                                                                                                    |
| [`shake`](#an.motion.shake)(target, \*[, amplitude, duration, ...])    | Tremble side to side `cycles` times and come back to rest (on `x`).                                                                                                                                                                                                                  |
| [`stage_poses`](#an.motion.stage_poses)(shot, \*[, mall, width, height])     | `{node path: rest pose}` for every node the compiler builds for `shot`'s stage — what [`rest_pose()`](#an.motion.rest_pose) reads one entry of, and what `an validate` checks a preset `play`'s node and every `set`/`tween` target against (an#166, an#193). |
| [`slide_in`](#an.motion.slide_in)(target, \*[, from_side, distance, ...]) | Whip in from `distance` pixels off to one side, overshoot, and settle.                                                                                                                                                                                                               |
| [`slide_out`](#an.motion.slide_out)(target, \*[, to_side, distance, ...])  | Exit `distance` pixels off to one side, accelerating (an exit).                                                                                                                                                                                                                      |
| [`squash_stretch`](#an.motion.squash_stretch)(target, \*[, amount, ...])        | Squash (wide and short), stretch (narrow and tall), then settle.                                                                                                                                                                                                                     |

### an.motion.HOME_PRESETS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'pop_in', 'slide_in'})*

Presets whose `rest` is the node’s HOME — where an entrance LANDS — rather
than where the node is when the move starts. Played by name these read the
BUILT pose (`slide_out` then `slide_in` comes back home; `pop_in` after a
`set` of the scales to 0 grows to full size); every other preset moves
relative to where the node IS at its start (an#212).

### an.motion.OVERSHOOT *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= (0.34, 1.56, 0.64, 1.0)*

A cubic-Bézier that overshoots its target by about 10% and settles back
(CSS “easeOutBack”). The compiler and both evaluators take any 4-point
Bézier on a numeric channel, and nothing clamps `y` to `[0, 1]`.

### an.motion.PRESETS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[...], [Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[SetAction](an.ir.schema.md#an.ir.schema.SetAction), Tag(tag=[set](https://docs.python.org/3/builtins/stdtypes.html#set))] | [Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[TweenAction](an.ir.schema.md#an.ir.schema.TweenAction), Tag(tag=tween)] | [Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[SequenceAction](an.ir.schema.md#an.ir.schema.SequenceAction), Tag(tag=sequence)] | [Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[ParallelAction](an.ir.schema.md#an.ir.schema.ParallelAction), Tag(tag=parallel)] | [Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[DelayAction](an.ir.schema.md#an.ir.schema.DelayAction), Tag(tag=delay)] | [Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[LoopAction](an.ir.schema.md#an.ir.schema.LoopAction), Tag(tag=loop)] | [Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[ExtensionAction](an.ir.schema.md#an.ir.schema.ExtensionAction), SerializeAsAny(), Tag(tag=extension)], Discriminator(discriminator=\_action_tag, custom_error_type=[None](https://docs.python.org/3/builtins/constants.html#None), custom_error_message=[None](https://docs.python.org/3/builtins/constants.html#None), custom_error_context=[None](https://docs.python.org/3/builtins/constants.html#None))]]]* *= {'crawl': <function crawl>, 'hop': <function hop>, 'pop_in': <function pop_in>, 'shake': <function shake>, 'slide_in': <function slide_in>, 'slide_out': <function slide_out>, 'squash_stretch': <function squash_stretch>}*

the moves that need no rig. A genre’s presets
(the cut-out ones: `cutan.motion.PRESETS`, an#322) are listed beside these
by the genre, which owns the `play` that names them.

* **Type:**
  The core’s presets by name

### an.motion.PRESET_VERSIONS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'crawl': '1', 'hop': '1', 'pop_in': '1', 'shake': '1', 'slide_in': '1', 'slide_out': '1', 'squash_stretch': '1'}*

bump a preset’s
version in the SAME change that makes it expand differently for the same
args, so every shot that plays it re-renders visibly instead of silently
([`an.semantic`](an.semantic.md#module-an.semantic) folds it into the shot’s vocabulary digest). Versioning
starts here (an#248).

* **Type:**
  Each preset’s vocabulary version (ADR 0003 decision 2)

### an.motion.as_leaves(action, , start=0.0)

`action` as top-level leaves that `scene.md` can round-trip.

The markdown writer spells a leaf and the `sequence(delay(start), leaf)`
wrapper the parser produces for a `start:` key in their short form, and
writes any other composition tree verbatim (its JSON form, an#241). This
flattens a preset (or any tree) into the short form, with the same
absolute times, which is what a person editing `scene.md` wants.

A `set` keeps its absolute time in `at` instead of a wrapper.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[`Union`[[`SetAction`](an.ir.schema.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction), [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction), [`ExtensionAction`](an.ir.schema.md#an.ir.schema.ExtensionAction)]]

```pycon
>>> leaves = as_leaves(hop("charlie"), start=1.0)
>>> [type(a).__name__ for a in leaves]
['SequenceAction', 'SequenceAction', 'SetAction']
>>> [round(f.start, 3) for a in leaves for f in flatten(a)]  # each from 0
[1.0, 1.25, 1.5]
```

### an.motion.crawl(target, , distance=2400.0, duration=30.0, start=None, tilt=0.96, perspective=1.0, fade=(700.0, 1500.0), y=None, easing='linear', rest=None)

An opening crawl: lay `target` on a plane tilted away, and slide it up and away.

Sets the plane (`rotation_x` = `tilt`, `perspective`, the far
`fade`, and the hinge’s `y` when given) at the start, then ONE tween:
`pivot_y` from `start` (default: where the pivot rests) to `start +
distance`. On a tilted node the pivot is the point of the plane on the
hinge (an#314), so the content travels `distance` scene px along the
plane; the slowing and shrinking as it recedes are the projection’s, not
the tween’s. A block centred on its origin starts with its middle on the
hinge: a negative `start` (half the block’s height and more) has it
enter from below. `fade=None` draws the plane to the horizon.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction), [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction), [`ExtensionAction`](an.ir.schema.md#an.ir.schema.ExtensionAction)]

```pycon
>>> leaves = flatten(crawl("crawl", distance=1000, duration=20, start=-300, fade=None))
>>> sorted((f.action.property, getattr(f.action, "value", None)) for f in leaves
...        if isinstance(f.action, SetAction) and f.start == 0)
[('perspective', 1.0), ('rotation_x', 0.96)]
>>> [(f.action.from_value, f.action.to_value, f.end) for f in _tweens(crawl("crawl",
...     distance=1000, duration=20, start=-300))]
[(-300.0, 700.0, 20.0)]
```

### an.motion.hop(target, , height=40.0, duration=0.5, rest=None)

Jump up by `height` scene pixels and land back where it started.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction), [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction), [`ExtensionAction`](an.ir.schema.md#an.ir.schema.ExtensionAction)]

```pycon
>>> [(f.action.from_value, f.action.to_value) for f in _tweens(hop("charlie", height=30))]
[(0.0, -30.0), (-30.0, 0.0)]
```

### an.motion.pop_in(target, , duration=0.45, easing=(0.34, 1.56, 0.64, 1.0), rest=None)

Grow from nothing to full size, overshooting and settling (an entrance).

Scales the target from 0 to its rest scale. Before the preset starts the
target shows at its rest pose: to keep it hidden until it pops, start the
preset at the target’s first frame (or hold `scale_x`/`scale_y` at 0
with a `set` before it).

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction), [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction), [`ExtensionAction`](an.ir.schema.md#an.ir.schema.ExtensionAction)]

```pycon
>>> [(f.action.property, f.action.from_value, f.action.to_value)
...  for f in _tweens(pop_in("charlie"))]
[('scale_x', 0.0, 1.0), ('scale_y', 0.0, 1.0)]
```

### an.motion.rest_pose(shot, target, , mall=None)

The rest values of `target`’s node as the compiler builds `shot`.

Compiles the shot’s STAGE — its entities, without actions, dialogue or
camera — through the cutout compiler’s own scene builder, so the layout
(`-110`/`110` for two characters), a `stage` placement and a stage
scale are read, never restated. Pass the same `mall` you render with:
a descriptor rig is built from its character store.

(These examples build character entities, the cut-out genre’s; they are not run here.)

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> from an.ir.schema import AssetRef
>>> two = Shot(id="s", entities=[
...     AssetRef(kind="character", id=n, store="characters", ref=n) for n in ("a", "b")])
>>> rest_pose(two, "a")["x"], rest_pose(two, "b")["x"]
(-110.0, 110.0)
>>> rest_pose(two, "a/head")["y"]
-55.0
```

### an.motion.shake(target, , amplitude=8.0, duration=0.4, cycles=3, rest=None)

Tremble side to side `cycles` times and come back to rest (on `x`).

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction), [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction), [`ExtensionAction`](an.ir.schema.md#an.ir.schema.ExtensionAction)]

```pycon
>>> [f.action.to_value for f in _tweens(shake("charlie", amplitude=5, cycles=2))]
[5.0, -5.0, 5.0, -5.0, 0.0]
>>> [f.action.to_value for f in _tweens(shake("charlie", cycles=1, rest={"x": -110}))]
[-102.0, -118.0, -110.0]
```

### an.motion.slide_in(target, , from_side='left', distance=600.0, duration=0.35, easing=(0.34, 1.56, 0.64, 1.0), rest=None)

Whip in from `distance` pixels off to one side, overshoot, and settle.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction), [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction), [`ExtensionAction`](an.ir.schema.md#an.ir.schema.ExtensionAction)]

```pycon
>>> [(f.action.from_value, f.action.to_value) for f in _tweens(slide_in("charlie", distance=400))]
[(-400.0, 0.0)]
```

### an.motion.slide_out(target, , to_side='right', distance=600.0, duration=0.35, easing='ease_in', rest=None)

Exit `distance` pixels off to one side, accelerating (an exit).

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction), [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction), [`ExtensionAction`](an.ir.schema.md#an.ir.schema.ExtensionAction)]

```pycon
>>> [(f.action.from_value, f.action.to_value) for f in _tweens(slide_out("charlie", to_side="left"))]
[(0.0, -600.0)]
```

### an.motion.squash_stretch(target, , amount=0.2, duration=0.36, rest=None)

Squash (wide and short), stretch (narrow and tall), then settle.

Scales about the target’s own origin (for the procedural rig, the torso’s
centre). Volume is roughly kept: one axis grows by what the other loses.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction), [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction), [`ExtensionAction`](an.ir.schema.md#an.ir.schema.ExtensionAction)]

```pycon
>>> [[round(f.action.to_value, 2) for f in _tweens(squash_stretch("c"))
...   if f.action.property == p] for p in ("scale_x", "scale_y")]
[[1.2, 0.9, 1.0], [0.8, 1.1, 1.0]]
```

### an.motion.stage_poses(shot, , mall=None, width=None, height=None)

`{node path: rest pose}` for every node the compiler builds for
`shot`’s stage — what [`rest_pose()`](#an.motion.rest_pose) reads one entry of, and what
`an validate` checks a preset `play`’s node and every `set`/`tween`
target against (an#166, an#193). `width`/`height` (default: the
compiler’s) matter to text, whose line breaks depend on the frame.

(These examples build character entities, the cut-out genre’s; they are not run here.)

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

```pycon
>>> from an.ir.schema import AssetRef
>>> one = Shot(id="s", entities=[AssetRef(kind="character", id="c", store="characters", ref="c")])
>>> poses = stage_poses(one)
>>> "c/right_arm" in poses, poses["c/head"]["y"]
(True, -55.0)
```
