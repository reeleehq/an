# an.motion

Motion presets: a named vocabulary of cut-out moves, as authoring macros.

`pop_in`, `hop`, `shake`, `nod`, `point`, `slide_in`, `slide_out`,
`squash_stretch`, `waddle`, `turn` and `walk` each EXPAND to ordinary `tween`
actions on transform properties (`turn` adds one swap `set`), composed with [`sequence()`](an.ir.compose.html.md#an.ir.compose.sequence) and
[`parallel()`](an.ir.compose.html.md#an.ir.compose.parallel). Called from Python, nothing downstream
learns a preset exists: the flat timeline, `an validate`, the verifiers and
the renderer see the same tweens an author could have written by hand. Played
by NAME from `scene.md` (an#166, below), the compiler expands the `play`
into those same tweens before anything else looks; `PlayAction.args` is the
one IR field that added. No runtime change either way, and no compiled
document that does not use a preset moves by a byte.

```pycon
>>> from an.ir.compose import flatten, sequence
>>> leaves = _tweens(sequence(pop_in("charlie"), hop("charlie"), nod("charlie")))
>>> [(f.action.target, f.action.property) for f in leaves][:3]
[('charlie', 'scale_x'), ('charlie', 'scale_y'), ('charlie', 'y')]
>>> round(leaves[-1].end, 3)
1.45
```

**Targets.** Whole-body moves target the entity container (`"charlie"`) —
the node a descriptor’s `bone:root` track animates too. Part moves name the
part: `nod` rotates `<entity>/head` (the head is a direct child of the
entity on both the procedural and the descriptor rig), and `point` takes
the ARM node itself, because the two rigs name it differently — the
procedural rig’s `right_arm` stands on the viewer’s right, a descriptor
rig’s `arm_r` on the viewer’s left. The rigs are flat (arms are siblings of
the torso), and a target the built scene does not carry makes the render
raise (the runtime refuses an unknown node, naming the known ones);
[`rest_pose()`](#an.motion.rest_pose) raises for it up front, before any browser starts.

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
`slide_out`, `waddle(travel=...)`) in a shot with more than one character
wants `rest=rest_pose(shot, "charlie")`, which reads the value off the
compiler’s own scene builder rather than restating its layout.

**scene.md: play a preset by name** (an#166). `{kind: play, target:
charlie, animation: hop, args: {height: 30}, start: 1.0}` expands to exactly
this module’s tweens at compile, with `rest` the pose the node HAS at the
play’s start — the built scene’s (stage placement, layout) overridden by the
sets and tweens before it (an#212) — so no `rest=`, and a preset after a move
starts where the move left it (an entrance in [`HOME_PRESETS`](#an.motion.HOME_PRESETS) lands on the
built pose instead); `args` are the preset’s keyword arguments. A character
descriptor animation of the same name WINS; `an validate` and the compiler
decide both through [`an.characters.play.play_problems()`](an.characters.play.html.md#an.characters.play.play_problems). `duration`
stretches the move and `speed` divides it; `loop` is refused. In a
`sequence` a `play` without a `duration` occupies the preset’s own
length divided by `speed`, so two in a row run one after the other.
[`as_leaves()`](#an.motion.as_leaves) remains for a preset composed in Python and written into
`scene.md` as plain tweens (a composition tree does not round-trip).

### Module Attributes

| [`OVERSHOOT`](#an.motion.OVERSHOOT)     | A cubic-Bézier that overshoots its target by about 10% and settles back (CSS "easeOutBack").                                                                                                                     |
|----------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`IDENTITY_POSE`](#an.motion.IDENTITY_POSE) | `x = y = rotation = 0`, `scale_x = scale_y = alpha = 1`.                                                                                                                                                         |
| [`PRESETS`](#an.motion.PRESETS)       | Every preset by name — the one list the skill, the demo and the `play` fallback ([`an.characters.play.play_source()`](an.characters.play.html.md#an.characters.play.play_source), an#166) read. |
| [`HOME_PRESETS`](#an.motion.HOME_PRESETS)  | Presets whose `rest` is the node's HOME — where an entrance LANDS — rather than where the node is when the move starts.                                                                                          |

### Functions

| [`face_toward`](#an.motion.face_toward)(shot, who, other, \*[, view, ...])     | [`turn()`](#an.motion.turn) `who` to `view`, facing `other` — the direction read off the stage, so a profile looks at the other character wherever the layout put them.                                                                                  |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`as_leaves`](#an.motion.as_leaves)(action, \*[, start])                     | `action` as top-level leaves that `scene.md` can round-trip.                                                                                                                                                                                                                         |
| [`hop`](#an.motion.hop)(target, \*[, height, duration, rest])          | Jump up by `height` scene pixels and land back where it started.                                                                                                                                                                                                                     |
| [`nod`](#an.motion.nod)(target, \*[, part, angle, duration, ...])      | Dip the head `count` times (a rotation of `<target>/<part>`).                                                                                                                                                                                                                        |
| [`point`](#an.motion.point)(target, \*[, angle, raise_duration, ...])    | Swing an arm out to point, hold it, and lower it again.                                                                                                                                                                                                                              |
| [`pop_in`](#an.motion.pop_in)(target, \*[, duration, easing, rest])       | Grow from nothing to full size, overshooting and settling (an entrance).                                                                                                                                                                                                             |
| [`rest_pose`](#an.motion.rest_pose)(shot, target, \*[, mall])                | The rest values of `target`'s node as the compiler builds `shot`.                                                                                                                                                                                                                    |
| [`shake`](#an.motion.shake)(target, \*[, amplitude, duration, ...])      | Tremble side to side `cycles` times and come back to rest (on `x`).                                                                                                                                                                                                                  |
| [`stage_poses`](#an.motion.stage_poses)(shot, \*[, mall, width, height])       | `{node path: rest pose}` for every node the compiler builds for `shot`'s stage — what [`rest_pose()`](#an.motion.rest_pose) reads one entry of, and what `an validate` checks a preset `play`'s node and every `set`/`tween` target against (an#166, an#193). |
| [`slide_in`](#an.motion.slide_in)(target, \*[, from_side, distance, ...])   | Whip in from `distance` pixels off to one side, overshoot, and settle.                                                                                                                                                                                                               |
| [`slide_out`](#an.motion.slide_out)(target, \*[, to_side, distance, ...])    | Exit `distance` pixels off to one side, accelerating (an exit).                                                                                                                                                                                                                      |
| [`squash_stretch`](#an.motion.squash_stretch)(target, \*[, amount, ...])          | Squash (wide and short), stretch (narrow and tall), then settle.                                                                                                                                                                                                                     |
| [`turn`](#an.motion.turn)(target, \*[, to, direction, ...])             | Turn a character to the view `to` — the classic cut-out turn (an#197).                                                                                                                                                                                                               |
| [`waddle`](#an.motion.waddle)(target, \*[, steps, step_duration, ...])    | A walk cycle for a rig with no legs to animate: rock and bob per step.                                                                                                                                                                                                               |
| [`walk`](#an.motion.walk)(target, \*[, to_x, distance, direction, ...]) | Walk: the body travels on `x` and bobs once per step while the legs alternate and the arms swing against them (an#214).                                                                                                                                                              |

### an.motion.HOME_PRESETS *: frozenset[str]* *= frozenset({'pop_in', 'slide_in'})*

Presets whose `rest` is the node’s HOME — where an entrance LANDS — rather
than where the node is when the move starts. Played by name these read the
BUILT pose (`slide_out` then `slide_in` comes back home; `pop_in` after a
`set` of the scales to 0 grows to full size); every other preset moves
relative to where the node IS at its start (an#212).

### an.motion.IDENTITY_POSE *: dict[str, float]* *= {'alpha': 1.0, 'rotation': 0.0, 'scale_x': 1.0, 'scale_y': 1.0, 'x': 0.0, 'y': 0.0}*

`x = y = rotation = 0`, `scale_x = scale_y = alpha = 1`.

### an.motion.OVERSHOOT *: tuple[float, float, float, float]* *= (0.34, 1.56, 0.64, 1.0)*

A cubic-Bézier that overshoots its target by about 10% and settles back
(CSS “easeOutBack”). The compiler and both evaluators take any 4-point
Bézier on a numeric channel, and nothing clamps `y` to `[0, 1]`.

### an.motion.PRESETS *: dict[str, Callable[[...], Annotated[[SetAction](an.ir.schema.html.md#an.ir.schema.SetAction) | [TweenAction](an.ir.schema.html.md#an.ir.schema.TweenAction) | [PlayAction](an.ir.schema.html.md#an.ir.schema.PlayAction) | [ExpressionAction](an.ir.schema.html.md#an.ir.schema.ExpressionAction) | [SequenceAction](an.ir.schema.html.md#an.ir.schema.SequenceAction) | [ParallelAction](an.ir.schema.html.md#an.ir.schema.ParallelAction) | [DelayAction](an.ir.schema.html.md#an.ir.schema.DelayAction) | [LoopAction](an.ir.schema.html.md#an.ir.schema.LoopAction), FieldInfo(annotation=NoneType, required=True, discriminator='kind')]]]* *= {'hop': <function hop>, 'nod': <function nod>, 'point': <function point>, 'pop_in': <function pop_in>, 'shake': <function shake>, 'slide_in': <function slide_in>, 'slide_out': <function slide_out>, 'squash_stretch': <function squash_stretch>, 'turn': <function turn>, 'waddle': <function waddle>, 'walk': <function walk>}*

Every preset by name — the one list the skill, the demo and the `play`
fallback ([`an.characters.play.play_source()`](an.characters.play.html.md#an.characters.play.play_source), an#166) read.

### an.motion.as_leaves(action, , start=0.0)

`action` as top-level leaves that `scene.md` can round-trip.

The markdown writer keeps a leaf and the `sequence(delay(start), leaf)`
wrapper the parser produces for a `start:` key, and drops composition
trees from `scene.md`. This flattens a preset (or any tree) into exactly
those, with the same absolute times.

A `set` keeps its absolute time in `at` instead of a wrapper.

* **Return type:**
  `list`[`Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]]

```pycon
>>> leaves = as_leaves(hop("charlie"), start=1.0)
>>> [type(a).__name__ for a in leaves]
['SequenceAction', 'SequenceAction', 'SetAction']
>>> [round(f.start, 3) for a in leaves for f in flatten(a)]  # each from 0
[1.0, 1.25, 1.5]
```

### an.motion.face_toward(shot, who, other, , view='side', from_direction=None, duration=0.3, mall=None)

[`turn()`](#an.motion.turn) `who` to `view`, facing `other` — the direction read
off the stage, so a profile looks at the other character wherever the
layout put them.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> from an.ir.schema import AssetRef
>>> two = Shot(id="s", entities=[
...     AssetRef(kind="character", id=n, store="characters", ref=n) for n in ("a", "b")])
>>> [f.action.to_value for f in _tweens(face_toward(two, "b", "a"))]
[0.0, -1.0]
```

### an.motion.hop(target, , height=40.0, duration=0.5, rest=None)

Jump up by `height` scene pixels and land back where it started.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> [(f.action.from_value, f.action.to_value) for f in _tweens(hop("charlie", height=30))]
[(0.0, -30.0), (-30.0, 0.0)]
```

### an.motion.nod(target, , part='head', angle=0.18, duration=0.5, count=2, rest=None)

Dip the head `count` times (a rotation of `<target>/<part>`).

In a front-facing 2D cut-out a nod reads as a small head rotation about
its pivot; `rest` is the HEAD’s rest, not the entity’s.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> [(f.action.target, round(f.action.to_value, 2)) for f in _tweens(nod("charlie", count=1))]
[('charlie/head', 0.18), ('charlie/head', 0.0)]
```

### an.motion.point(target, , angle=-1.3, raise_duration=0.25, hold=0.6, easing=(0.34, 1.56, 0.64, 1.0), rest=None)

Swing an arm out to point, hold it, and lower it again.

`target` is the ARM node — `"charlie/right_arm"` on the procedural
rig, `"maya/arm_r"` on a descriptor rig (and there, since that arm hangs
on the viewer’s left, pass a positive `angle` to point outward).

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> [(f.start, f.action.to_value) for f in _tweens(point("charlie/right_arm", hold=0.5))]
[(0.0, -1.3), (0.75, 0.0)]
```

### an.motion.pop_in(target, , duration=0.45, easing=(0.34, 1.56, 0.64, 1.0), rest=None)

Grow from nothing to full size, overshooting and settling (an entrance).

Scales the target from 0 to its rest scale. Before the preset starts the
target shows at its rest pose: to keep it hidden until it pops, start the
preset at the target’s first frame (or hold `scale_x`/`scale_y` at 0
with a `set` before it).

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

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

* **Return type:**
  `dict`[`str`, `float`]

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
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> [f.action.to_value for f in _tweens(shake("charlie", amplitude=5, cycles=2))]
[5.0, -5.0, 5.0, -5.0, 0.0]
>>> [f.action.to_value for f in _tweens(shake("charlie", cycles=1, rest={"x": -110}))]
[-102.0, -118.0, -110.0]
```

### an.motion.slide_in(target, , from_side='left', distance=600.0, duration=0.35, easing=(0.34, 1.56, 0.64, 1.0), rest=None)

Whip in from `distance` pixels off to one side, overshoot, and settle.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> [(f.action.from_value, f.action.to_value) for f in _tweens(slide_in("charlie", distance=400))]
[(-400.0, 0.0)]
```

### an.motion.slide_out(target, , to_side='right', distance=600.0, duration=0.35, easing='ease_in', rest=None)

Exit `distance` pixels off to one side, accelerating (an exit).

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> [(f.action.from_value, f.action.to_value) for f in _tweens(slide_out("charlie", to_side="left"))]
[(0.0, -600.0)]
```

### an.motion.squash_stretch(target, , amount=0.2, duration=0.36, rest=None)

Squash (wide and short), stretch (narrow and tall), then settle.

Scales about the target’s own origin (for the procedural rig, the torso’s
centre). Volume is roughly kept: one axis grows by what the other loses.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

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

* **Return type:**
  `dict`[`str`, `dict`[`str`, `float`]]

```pycon
>>> from an.ir.schema import AssetRef
>>> one = Shot(id="s", entities=[AssetRef(kind="character", id="c", store="characters", ref="c")])
>>> poses = stage_poses(one)
>>> "c/right_arm" in poses, poses["c/head"]["y"]
(True, -55.0)
```

### an.motion.turn(target, , to='back', direction='right', from_direction=None, duration=0.3, view_set='view', rest=None)

Turn a character to the view `to` — the classic cut-out turn (an#197).

`scale_x` squashes to 0 (the character edge-on), the view swaps at that
midpoint, and `scale_x` opens again to the rest scale — mirrored when
`direction="left"`: a `side` view is drawn facing the viewer’s right,
so `direction` is which way the character FACES after the turn.
`from_direction` is which way it faced before — by default the sign of
the rest `scale_x` (a character staged mirrored faces left). Called from
Python the preset cannot see an EARLIER turn, so turning back from a
left-facing profile is `turn(to="front", from_direction="left")`; PLAYED
by name (`{kind: play, animation: turn}`) the compiler fills it in from
the timeline before it ([`an.characters.play.resolve_turns()`](an.characters.play.html.md#an.characters.play.resolve_turns), an#203).

`to` is a key of the character’s `view` set — `front`, `back`,
`side` or `three_quarter` on a factory character
(`an character new --offline`); the swap is a `set` on the ENTITY,
which the compiler fans out to the head and torso and which poses the face
(the back hides it, the profile keeps one eye). `rest` is the entity’s:
its `scale_x` magnitude is where the turn opens to.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> def lands(a):  # a tween's end value, a set's value
...     return a.to_value if a.kind == "tween" else a.value
>>> [(round(f.start, 2), f.action.property, lands(f.action))
...  for f in flatten(turn("ned", to="side", direction="left"))]
[(0.0, 'scale_x', 0.0), (0.15, 'view', 'side'), (0.15, 'scale_x', -1.0), (0.3, 'scale_x', -1.0)]
```

### an.motion.waddle(target, , steps=4, step_duration=0.3, angle=0.1, lift=6.0, travel=0.0, rest=None)

A walk cycle for a rig with no legs to animate: rock and bob per step.

Each step rocks the body to alternate sides by `angle` and bobs it up by
`lift`; `angle=0` is a plain bob. `travel` (scene px, signed)
carries the body sideways over the whole walk — the one `x` move here,
so it is the one that needs `rest` in a multi-character shot.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> w = _tweens(waddle("charlie", steps=2, travel=100))
>>> sorted({f.action.property for f in w})
['rotation', 'x', 'y']
>>> max(f.end for f in w)
0.6
```

### an.motion.walk(target, , to_x=None, distance=None, direction=None, steps=None, step_s=0.4, step_length=80.0, stride=0.35, lift=10.0, bob=6.0, arm_swing=0.3, rock=0.06, hem_tilt=0.24, view=None, gait=None, legs=None, arms=None, parts=None, rest=None)

Walk: the body travels on `x` and bobs once per step while the legs
alternate and the arms swing against them (an#214).

**Where to.** `to_x` (absolute scene x) or `distance` (signed px; with
`direction` `"left"`/`"right"` its sign is the direction’s), or
neither to walk on the spot. The walk starts where the entity IS —
played by name, `rest` is its pose at the play’s start (an#212), so
`set x -800` then `walk to_x: -100` walks in from off-screen.

**How many steps.** `steps`, else `|distance| / step_length`, else
`DFLT_WALK_STEPS` — never counted from the start position, so the
walk’s length (`steps × step_s`) is known before it is placed and a
`sequence` waits for exactly that long.

**Legs, by view.** In a view in `WALK_SWING_VIEWS` (`side`,
`three_quarter`) each leg swings `stride` radians either side of its
rest about the hip, the two in opposition; in any other view (`front`,
`back`, or none) the stepping leg rises `lift` px and sets down again,
the two alternating. Played by name, `view` is the one in force on the
timeline at the play’s start (the view the last `turn` or `set` left);
pass it to override. `legs`/`arms` name the two limb nodes; by
default the first pair in `WALK_LEG_NAMES` / `WALK_ARM_NAMES`
that the rig builds (`parts`: the entity’s built parts with their pose
at the start, filled in by the compiler). Played by name with no view on
the timeline, the view is the descriptor’s `rest_view` (an#220) — a
character carved in profile swings its legs with nothing passed.

**Gait** (`gait`, one of [`an.characters.schema.GAITS`](an.characters.schema.html.md#an.characters.schema.GAITS), an#220).
`legs` is the above. `hem` is a robe whose leg slots are the two
halves of its hem: facing the camera the halves TILT in turn by
`hem_tilt` radians about the hip while the body sways by `rock` and
bobs (in a profile they swing like legs). `rock` moves no leg: the body
rocks and bobs (a blob, a sack). Unset: the descriptor’s `gait` when
played by name, else `legs` when the rig builds a leg pair and `rock`
when it does not. Limbs land on
their rest with a `WALK_LANDING_S` constant tween, not a settling
`set`: a `set`’s hold would outrank the view’s pose channel and keep a
profile’s splay after a later turn to the front.

The walk does not turn the character: in a side view, face the way it
walks first (`turn`, `direction`) — the classic walk-off is `turn`
then `walk`.

* **Return type:**
  `Union`[[`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction), [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction), [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction), [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction), [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction), [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction), [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)]

```pycon
>>> w = walk("bob", distance=160, steps=2, step_s=0.5)
>>> sorted({(f.action.target, f.action.property) for f in _tweens(w)})
[('bob', 'x'), ('bob', 'y'), ('bob/arm_l', 'rotation'), ('bob/arm_r', 'rotation'), ('bob/leg_l', 'y'), ('bob/leg_r', 'y')]
>>> max(f.end for f in flatten(w)), [f.action.to_value for f in _tweens(w) if f.action.property == "x"]
(1.0, [160.0])
>>> sorted({f.action.property for f in _tweens(walk("bob", distance=80, view="side"))
...         if f.action.target == "bob/leg_l"})
['rotation']
>>> sorted({f.action.target for f in _tweens(walk("blob", steps=2, legs=(), arms=()))})
['blob']
>>> sorted({(f.action.target, f.action.property) for f in _tweens(walk("al", steps=2, gait="hem"))
...         if f.action.target in ("al", "al/leg_l")})
[('al', 'rotation'), ('al', 'y'), ('al/leg_l', 'rotation')]
```
