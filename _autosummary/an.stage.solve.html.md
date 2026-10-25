# an.stage.solve

The `solve` compile pass: joints kept at every frame (ADR 0008 decision 6, an#512).

After every pass that moves a body (the actions, a genre’s poses and faces;
order 525, between `face` at 500 and `camera_follow` at 550), the
document so far is evaluated at every frame of the shot’s grid, the joints a
scene declares are solved under the authored motion by [`an.kinematics`](an.kinematics.html.md#module-an.kinematics),
and one key per frame is emitted for every channel the solve moved. A scene
that declares no joint and no verb compiles byte for byte as before: the pass
returns before it reads anything.

**Bodies** are read from the built tree and the rigs ([`an.stage.rig.rig_structure()`](an.stage.rig.html.md#an.stage.rig.rig_structure)):
every part of an entity a declaration names is a body posed in stage space
(the root’s own coordinates: scene px from the stage centre), with the extent
of its drawing; its bones’ joints are hinges; a bone with no part is a named
point (`paul/fore_r@hand_r`). A node that is not a body (a face part) is a
point on the body it rides.

**Drivers.** What the author wrote is met exactly where the joints allow:

- a rig’s ROOT parts (a torso, a prop’s body: nothing hangs them from a
  parent) stay where they are staged and animated, unless the entity says
  `overrides: {free: true}` (or names the parts: `free: [torso]`), or a
  `pin`/`pull` moves them (a pinned cup goes to the hand);
- a part hung from a parent (an arm) is free, except in the channels authored
  on it; in `nesting: bones` an authored rotation is its joint held at that
  angle (a weld), since the angle is relative to a parent that may itself move;
- `overrides: {fixed: true}` holds every part of an entity where the author put it.

**What it emits.** One clip per entity, `__solve__<entity>`, placed last in
that entity’s track (later wins, so a solved channel replaces an authored one
on the same span: that is what a join means), with one quantised key per
frame on `x`, `y` and `rotation` of a part whose parent is not a body
(a root, a part of a flat rig) and `rotation` alone of a part nested in a
chain (its position follows from its parent’s). A channel the solve never
moves from what the document already shows is not emitted. Under `step_hz`
the solve runs on the shot’s step grid and the keys are stepped (its own
emission site, as the camera’s). `meta.extensions.solve` records the mode,
the solver version and effort, a digest of the solve’s inputs, the joints in
solver order, and what could not be held (the joints given up, the rejoins
that snapped, the authored spans the solve overrode): what `an validate`’s
joint checks read ([`an.verify.joints`](an.verify.joints.html.md#module-an.verify.joints)).

```pycon
>>> from an.ir.schema import Shot
>>> declarations(Shot(id="s"), {}).empty
True
```

### Module Attributes

| [`SOLVE_ORDER`](#an.stage.solve.SOLVE_ORDER)       | after `face` (500), before `camera_follow` (550).                        |
|--------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`SOLVE_CLIP_PREFIX`](#an.stage.solve.SOLVE_CLIP_PREFIX) | The name of the clip of each entity's solved channels (`__solve__paul`). |
| [`SOLVE_EXTENSION`](#an.stage.solve.SOLVE_EXTENSION)   | The `meta.extensions` key of the solve's report.                         |

### Functions

| [`declarations`](#an.stage.solve.declarations)(shot, mall, \*[, verbs, play_extent])   | The joints `shot` declares (its entities' descriptors', its entities', its own, in that order) and its verbs, flattened to shot time.                                                |
|-------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`build_puppet`](#an.stage.solve.build_puppet)(doc, shot, mall, decl, \*[, vocab])     | The bodies and joints of `shot` as built in `doc`; raises [`UnknownBodyError`](#an.stage.solve.UnknownBodyError) naming every reference it cannot resolve.                |
| [`solve_pass`](#an.stage.solve.solve_pass)(state)                                    | The `solve` compile pass (order [`SOLVE_ORDER`](#an.stage.solve.SOLVE_ORDER)).                                                                                       |
| [`joint_residuals`](#an.stage.solve.joint_residuals)(doc, shot, mall, \*[, times])        | How far each joined joint of `shot` is from holding in `doc`, at every frame: `(puppet, times, gaps[k][j], range_excess[k][j])` (px; and radians past a hinge's range, 0 inside it). |
| [`shot_declares_solve`](#an.stage.solve.shot_declares_solve)(shot[, mall])                    | Whether `shot` declares anything the solve acts on (the pass's gate).                                                                                                                |
| [`solve_knobs`](#an.stage.solve.solve_knobs)(shot)                                    | The solve's render knobs for the shot-cache key: the solver's version, the shot's mode and effort as declared, and a digest of its declarations.                                     |

### Classes

| [`Declarations`](#an.stage.solve.Declarations)([joints, verbs, problems, holds])   | Every joint and verb a shot declares, in solver order (structure first), and what it holds ([`an.stage.hold.HoldDeclarations`](an.stage.hold.html.md#an.stage.hold.HoldDeclarations)).   |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Puppet`](#an.stage.solve.Puppet)(bodies, rows, held, events, rest[, ...])  | A shot's bodies (structure first) and joints, ready to solve.                                                                                                                                                  |

### Exceptions

| [`UnknownBodyError`](#an.stage.solve.UnknownBodyError)(message, problems)   | A declaration names a body, a point or a joint the shot does not have.   |
|----------------------------------------------------------------------------------------|--------------------------------------------------------------------------|

### *class* an.stage.solve.Declarations(joints=list(), verbs=list(), problems=list(), holds=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Every joint and verb a shot declares, in solver order (structure first),
and what it holds ([`an.stage.hold.HoldDeclarations`](an.stage.hold.html.md#an.stage.hold.HoldDeclarations)).

#### holds *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= None*

The hold verbs and `held_by` overrides ([`an.stage.hold`](an.stage.hold.html.md#module-an.stage.hold)), or `None`.

#### problems *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

`(where, message)` for a declaration that does not read (a descriptor’s).

### *class* an.stage.solve.Puppet(bodies, rows, held, events, rest, located=dict(), nodes=dict(), lean=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A shot’s bodies (structure first) and joints, ready to solve.

#### lean *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)]]*

Per-frame rotation targets the hold layer gives bodies (a lean, and what
rides on it): `body -> [rotation or None, per frame]`.

#### located *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)], [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

`(ref, side) -> Located`.

* **Type:**
  The holder points the hold verbs name

#### nodes *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

The built tree’s nodes by path.

### an.stage.solve.SOLVE_CLIP_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '_\_solve_\_'*

The name of the clip of each entity’s solved channels (`__solve__paul`).

### an.stage.solve.SOLVE_EXTENSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'solve'*

The `meta.extensions` key of the solve’s report.

### an.stage.solve.SOLVE_ORDER *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 525*

after `face` (500), before `camera_follow` (550).

* **Type:**
  Where the pass runs

### *exception* an.stage.solve.UnknownBodyError(message, problems)

Bases: [`CutoutCompileError`](an.stage.compile.html.md#an.stage.compile.CutoutCompileError)

A declaration names a body, a point or a joint the shot does not have.

`problems` lists each one as `(where, message)`, `where` relative to
the shot (`joints/0`, `actions/2`): what `an validate`’s
`unknown_body` check reports.

### an.stage.solve.build_puppet(doc, shot, mall, decl, , vocab=None)

The bodies and joints of `shot` as built in `doc`; raises
[`UnknownBodyError`](#an.stage.solve.UnknownBodyError) naming every reference it cannot resolve.

* **Return type:**
  [`Puppet`](#an.stage.solve.Puppet)

### an.stage.solve.declarations(shot, mall, , verbs=True, play_extent=None)

The joints `shot` declares (its entities’ descriptors’, its entities’,
its own, in that order) and its verbs, flattened to shot time.

* **Return type:**
  [`Declarations`](#an.stage.solve.Declarations)

### an.stage.solve.joint_residuals(doc, shot, mall, , times=None)

How far each joined joint of `shot` is from holding in `doc`, at
every frame: `(puppet, times, gaps[k][j], range_excess[k][j])` (px; and
radians past a hinge’s range, 0 inside it). An unjoined joint reads 0.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Puppet`](#an.stage.solve.Puppet), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]]]

### an.stage.solve.shot_declares_solve(shot, mall=None)

Whether `shot` declares anything the solve acts on (the pass’s gate).

```pycon
>>> shot_declares_solve(Shot(id="s"))
False
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.stage.solve.solve_knobs(shot)

The solve’s render knobs for the shot-cache key: the solver’s version, the
shot’s mode and effort as declared, and a digest of its declarations.

```pycon
>>> sorted(solve_knobs(Shot(id="s")))
['declared', 'hold_version', 'iterations', 'mode', 'solver_version', 'substeps']
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.stage.solve.solve_pass(state)

The `solve` compile pass (order [`SOLVE_ORDER`](#an.stage.solve.SOLVE_ORDER)). A no-op for a shot
that declares no joint and no verb.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
