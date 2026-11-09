# an.stage.hold

The hold layer: what carries each item, frame by frame, and the hands that move it (an#502, catalogue A4).

The verbs are [`an.ir.holds`](an.ir.holds.html.md#module-an.ir.holds) (`grasp`, `place`, `release`,
`handover`, `swap`). This module runs them inside the `solve` compile
pass ([`an.stage.solve`](an.stage.solve.html.md#module-an.stage.solve)), because a hold needs the SOLVED hand at every
frame: the hand is a body of the shot’s puppet, the item is not.

**The model.** Every item is, at each instant, in exactly one \*holder’s
frame\*: a body’s point (a hand, a figurine’s socket), the ground, a point of
the stage, or none (in flight). A change of holder is a reframe that keeps the
item’s world pose at that instant (`keep: world`, an#502): the item’s local
transform in the new holder’s frame is computed so the picture is continuous,
so there is never a slide or a jump. What makes the change look *handled* is
that the hand first goes where the item is:

- **Reach and retract.** A gesture drives its hand’s point (an end effector:
  `stu@hand_r`, `stu/arm_r`) along a minimum-jerk path from where the shot
  would have it to the goal (the item’s grip; for a `place`, the point that
  puts the item’s contact point on its target), and back, as a `pull` row of
  the solver whose goal moves frame by frame. The arm follows by the solver’s
  joints. The item changes holder at the frame the hand arrives.
- **Lean.** When the goal is out of the arm’s reach, the body the arm hangs
  from (the chain’s root: a torso, a crane’s base) turns about its own pivot
  by the least angle that brings the goal in reach (closed form, the two-link
  triangle), up to `lean` degrees, rising with the reach and falling with
  the retract, and every part riding on it turns with it (the head, the other
  arm). A reach that still cannot arrive is reported (`unreachable_hold`,
  with how far it stays short and which way to move the carrier).
- **Carry.** A held item’s world transform is its holder’s times a fixed local
  transform, so it turns, mirrors and squashes with the hand (a character
  turning round carries the musket round with it).
- **Place.** Over a `place`’s reach the item keeps its point in the hand and
  turns from how it is carried to how it will rest (a wrist), so it arrives
  aligned with a socket’s frame or lying on the ground at its rest angle, its
  lowest INK point at floor height (the texture’s alpha, not its box, so a
  carved part with a transparent margin does not float).
- **Release.** A parabola under gravity (the shot’s or the style pack’s, else
  [`DFLT_FALL_GRAVITY`](#an.stage.hold.DFLT_FALL_GRAVITY)) from the velocity the hand gave it, turning to its
  > rest angle on the way down, landing on the ground exactly; `onto:
  > ground@x` solves the throw that lands there on an arc `arc` px high.

**Draw order.** While a body holds an item, the item is PAINTED just after
its holder’s part (an#537): a `paint_after` channel on the item’s entity node
([`an.base.PAINT_AFTER_PROPERTY`](an.base.html.md#an.base.PAINT_AFTER_PROPERTY)) names that part from the frame the hold
changes, and `""` (its staged place, `stage.after` included) once nothing
holds it. The item keeps its own node, so its transform is untouched; the
runtime paints it from right after the part (`runtime.js`, `makeHeldPaints`).
A musket in a hand draws over the arm that carries it and under whatever the
holder draws over that arm; put in a figurine’s hand, it draws with the
figurine, not over the one who put it there.

**Two passes.** The goals and the leans are planned from a solve without the
gestures (the shot as authored), the shot is solved with them, and the plan is
made again from that solve (an item carried after a grasp hangs where the
grasp really put it) before the final solve. [`HOLD_PLAN_PASSES`](#an.stage.hold.HOLD_PLAN_PASSES) says how
many times.

The item’s channels (`x`, `y`, `rotation`, `scale_x`, `scale_y` of its
entity node) are emitted with the puppet’s in the entity’s `__solve__` clip;
`meta.extensions.solve.holds` records each gesture (its contact instant,
where the hand arrived, how far it stayed short, its lean) and each item’s
holders, what `an validate`’s hold checks read ([`an.verify.holds`](an.verify.holds.html.md#module-an.verify.holds)).

```pycon
>>> from an.ir.schema import Shot
>>> declares_holds(Shot(id="s"))
False
```

### Module Attributes

| [`HOLD_VERSION`](#an.stage.hold.HOLD_VERSION)       | bump it when the same declarations can compile to other keys.                                                                                   |
|---------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| [`HOLDS_REPORT`](#an.stage.hold.HOLDS_REPORT)       | The key of the hold report inside `meta.extensions.solve`.                                                                                      |
| [`ON_OVERRIDE`](#an.stage.hold.ON_OVERRIDE)        | what holds an item when the shot opens (`ground`, a body's point, `world@x,y`).                                                                 |
| [`AIM_OVERRIDE`](#an.stage.hold.AIM_OVERRIDE)       | the stage angle it is held at, as a place's `rotation` (a shot that opens on a musket already aimed at someone, continuing the shot before it). |
| [`GRASP_TOLERANCE_PX`](#an.stage.hold.GRASP_TOLERANCE_PX) | A reach that ends farther than this from its goal did not arrive (scene px).                                                                    |
| [`DFLT_FALL_GRAVITY`](#an.stage.hold.DFLT_FALL_GRAVITY)  | Gravity for a released item when neither the shot nor the style pack says (scene px / s², down the screen).                                     |
| [`HOLD_PLAN_PASSES`](#an.stage.hold.HOLD_PLAN_PASSES)   | How many times the gestures are planned (each from the solve the previous plan made).                                                           |

### Functions

| [`declares_holds`](#an.stage.hold.declares_holds)(shot)                       | Whether `shot` has a hold verb or an item `held_by` something.                                                                                                                                                                                                                                   |
|---------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`hold_declarations`](#an.stage.hold.hold_declarations)(shot, \*[, play_extent]) | The hold verbs of `shot` flattened to shot time, its `held_by` overrides, the holder points they name and who moves a hand.                                                                                                                                                                      |
| [`solve_holds`](#an.stage.hold.solve_holds)(state, doc, puppet, decl, ...) | Plan and solve a shot's holds: the final run, the items' channels `{(path, prop): (values, as the document shows them)}`, the keys of each held item's `paint_after` channel ([`paint_hosts()`](#an.stage.hold.paint_hosts)), and the report.                                   |
| [`ink_box`](#an.stage.hold.ink_box)(doc, node, mall)                   | The box round a node's ink ([`ink_points()`](#an.stage.hold.ink_points)), in its own frame.                                                                                                                                                                                    |
| [`ink_points`](#an.stage.hold.ink_points)(doc, node, mall)                | A node's drawn ink as points in its own frame: the corners of the box its art is fitted into, or, for a raster the store can read, the convex hull of its painted pixels inside that box (so the lowest point of a part turned any way is the lowest painted pixel, not a corner of its margin). |
| [`paint_hosts`](#an.stage.hold.paint_hosts)(holders, times, \*[, lead])    | The keys of an item's `paint_after` channel (an#537) from its holders `[(frame, holder)]` in the order they changed: the part it paints just after (`""`: its staged place, when no body holds it), at each change; at one frame the last change stands.                                         |

### Classes

| [`HoldVerb`](#an.stage.hold.HoldVerb)(action, start, end, where)           | A flattened hold verb (a `swap` is its `grasp` and its `place`).             |
|------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`HoldDeclarations`](#an.stage.hold.HoldDeclarations)([verbs, initial, aims, ...]) | The hold verbs of a shot and its `held_by` overrides, read without geometry. |

### Exceptions

| [`HoldError`](#an.stage.hold.HoldError)(message, problems)   | The holds of a shot do not make sense (a hand puts down what it does not hold, a socket gets a second item, one hand does two things at once).   |
|---------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|

### an.stage.hold.AIM_OVERRIDE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'held_rotation'*

the stage angle it
is held at, as a place’s `rotation` (a shot that opens on a musket already
aimed at someone, continuing the shot before it).

* **Type:**
  The override that aims an item a socket holds from the start

### an.stage.hold.DFLT_FALL_GRAVITY *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 980.0*

Gravity for a released item when neither the shot nor the style pack says
(scene px / s², down the screen).

### an.stage.hold.GRASP_TOLERANCE_PX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

A reach that ends farther than this from its goal did not arrive (scene px).

### an.stage.hold.HOLDS_REPORT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'holds'*

The key of the hold report inside `meta.extensions.solve`.

### an.stage.hold.HOLD_PLAN_PASSES *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

How many times the gestures are planned (each from the solve the previous
plan made).

### an.stage.hold.HOLD_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '2'*

bump it
when the same declarations can compile to other keys.

* **Type:**
  The hold layer’s version, in the shot-cache key (`solve_knobs`)

### *class* an.stage.hold.HoldDeclarations(verbs=list(), initial=dict(), aims=dict(), refs=list(), items=dict(), movers=set())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The hold verbs of a shot and its `held_by` overrides, read without geometry.

`refs` are the holder points to resolve as `(ref, where, side)` (side
`hand`: a moving point, `socket`: one that holds still); `items` the
entities held (`id -> where first named`); `movers` the entities that
move a hand (they are solved; a holder that never moves is held fixed).

#### aims *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

`id -> (stage angle, where)`

* **Type:**
  `held_rotation` overrides

### *exception* an.stage.hold.HoldError(message, problems)

Bases: [`CutoutCompileError`](an.stage.compile.html.md#an.stage.compile.CutoutCompileError)

The holds of a shot do not make sense (a hand puts down what it does not
hold, a socket gets a second item, one hand does two things at once).

`problems` lists each one as `(where, message)`, `where` relative to
the shot: what `an validate`’s `hold_conflict` check reports.

### *class* an.stage.hold.HoldVerb(action, start, end, where)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A flattened hold verb (a `swap` is its `grasp` and its `place`).

### an.stage.hold.ON_OVERRIDE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'held_by'*

what holds an item when the shot opens
(`ground`, a body’s point, `world@x,y`).

* **Type:**
  `AssetRef.overrides` key

### an.stage.hold.declares_holds(shot)

Whether `shot` has a hold verb or an item `held_by` something.

```pycon
>>> from an.ir.schema import Shot
>>> cup = {"kind": "prop", "id": "cup", "store": "props", "ref": "cup", "overrides": {"held_by": "ground"}}
>>> declares_holds(Shot(id="s", entities=[cup]))
True
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.stage.hold.hold_declarations(shot, , play_extent=None)

The hold verbs of `shot` flattened to shot time, its `held_by` overrides,
the holder points they name and who moves a hand.

* **Return type:**
  [`HoldDeclarations`](#an.stage.hold.HoldDeclarations)

### an.stage.hold.ink_box(doc, node, mall)

The box round a node’s ink ([`ink_points()`](#an.stage.hold.ink_points)), in its own frame.

```pycon
>>> from an.stage.serialize import NodeJSON, VisualJSON
>>> ink_box(None, NodeJSON(name="n", visual=VisualJSON(width=10, height=20)), None)
(-5.0, -10.0, 10.0, 20.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.stage.hold.ink_points(doc, node, mall)

A node’s drawn ink as points in its own frame: the corners of the box
its art is fitted into, or, for a raster the store can read, the convex
hull of its painted pixels inside that box (so the lowest point of a part
turned any way is the lowest painted pixel, not a corner of its margin).

```pycon
>>> from an.stage.serialize import NodeJSON, VisualJSON
>>> ink_points(None, NodeJSON(name="n", visual=VisualJSON(width=10, height=20)), None)
[(-5.0, -10.0), (5.0, -10.0), (-5.0, 10.0), (5.0, 10.0)]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.stage.hold.paint_hosts(holders, times, , lead=1e-06)

The keys of an item’s `paint_after` channel (an#537) from its holders
`[(frame, holder)]` in the order they changed: the part it paints just
after (`""`: its staged place, when no body holds it), at each change; at
one frame the last change stands. A change key leads its frame by `lead`
seconds, so the frame sees it however its time was rounded (the property is
`discrete(switch_at=1)`: it switches at its own key; a space that
declares it otherwise must keep that). `[]` when no body ever holds it:
nothing to emit, and the shot compiles as before.

```pycon
>>> hand = Holder("body", ref="fig/arm_r", body="fig/arm_r", local=(0.0, 0.0))
>>> times = [0.0, 0.5, 1.0, 1.5, 2.0]
>>> paint_hosts([(0, Holder("ground")), (2, hand), (4, None)], times, lead=0.25)
[(0.0, ''), (0.75, 'fig/arm_r'), (1.75, '')]
>>> paint_hosts([(0, Holder("ground"))], times)
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.stage.hold.solve_holds(state, doc, puppet, decl, settings, times)

Plan and solve a shot’s holds: the final run, the items’ channels
`{(path, prop): (values, as the document shows them)}`, the keys of each
held item’s `paint_after` channel ([`paint_hosts()`](#an.stage.hold.paint_hosts)), and the report.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[`Run`, [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]
