# an.stage.topple

The `topple` compile pass: rigid bodies falling over, one knocking the next ([`an.ir.topple`](an.ir.html.md#an.ir.topple)).

Runs after the `solve` pass (order [`TOPPLE_ORDER`](#an.stage.topple.TOPPLE_ORDER)), on the document as
the solve and the hold layer left it, so a figurine falls with the sabre its
hand holds. For each `topple` action, in the order they start:

1. **The body** is the entity’s drawn ink at the instant it starts (every
   drawn node under it, plus every item a part of it holds then, per the hold
   report), as points on the stage. Its centre of mass is the centroid of
   their convex hull; its moment of inertia comes from the hull
   ([`an.stage.rigid.inertia()`](an.stage.rigid.html.md#an.stage.rigid.inertia)).
2. **The pivot** is its lowest point on the side it falls `toward`.
3. **The fall** is [`an.stage.rigid.pivot_fall()`](an.stage.rigid.html.md#an.stage.rigid.pivot_fall) from `push` (or, when
   `after` names the topple that knocks it, from that body’s speed where it
   first touches this one), until another point of it reaches the floor (then
   a small bounce, [`an.stage.rigid.DFLT_BOUNCE`](an.stage.rigid.html.md#an.stage.rigid.DFLT_BOUNCE)) or `point` reaches
   `until` (it stays there: nothing is cheated, so a target off the circle
   `point` sweeps is a [`ToppleError`](#an.stage.topple.ToppleError) saying how far to move the body).
4. **The keys**: every frame from its start, the body’s entity node and the
   items it holds are turned about the pivot by the fall’s angle, written as a
   `__topple__<entity>` clip after the solve’s (the last clip of a track
   wins its channels).

The report, `meta.extensions.topple`, lists each topple and its `events`
(`topple`, `hit`, `land`, `pin`, `bounce`, `rest`), which a sound
cue can be timed by (`at: {when: cam, event: land}`, [`an.sound_anchors`](an.sound_anchors.html.md#module-an.sound_anchors)).

### Module Attributes

| [`TOPPLE_ORDER`](#an.stage.topple.TOPPLE_ORDER)     | after `solve` (525), before the camera follows (550).               |
|-------------------------------------------------------------------|---------------------------------------------------------------------|
| [`TOPPLE_EXTENSION`](#an.stage.topple.TOPPLE_EXTENSION) | The key of the report in the compiled document's `meta.extensions`. |

### Functions

| [`topple_pass`](#an.stage.topple.topple_pass)(state)   | The `topple` compile pass (order [`TOPPLE_ORDER`](#an.stage.topple.TOPPLE_ORDER)); a no-op for a shot with no `topple`.   |
|-----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|

### Exceptions

| [`ToppleError`](#an.stage.topple.ToppleError)   | A topple that cannot happen as written: the message says why and what to change.   |
|----------------------------------------------------------------|------------------------------------------------------------------------------------|

### an.stage.topple.TOPPLE_EXTENSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'topple'*

The key of the report in the compiled document’s `meta.extensions`.

### an.stage.topple.TOPPLE_ORDER *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 535*

after `solve` (525), before the camera follows (550).

* **Type:**
  Where the pass runs

### *exception* an.stage.topple.ToppleError

Bases: [`CutoutCompileError`](an.stage.compile.html.md#an.stage.compile.CutoutCompileError)

A topple that cannot happen as written: the message says why and what to change.

### an.stage.topple.topple_pass(state)

The `topple` compile pass (order [`TOPPLE_ORDER`](#an.stage.topple.TOPPLE_ORDER)); a no-op for a shot with no `topple`.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
