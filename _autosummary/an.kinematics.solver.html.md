# an.kinematics.solver

The solve: bodies joined at points, driven at a few, settled by gravity.

One frame at a time ([`solve()`](#an.kinematics.solver.solve)), or a run of frames with the caller’s
targets and joined/unjoined joints per frame ([`solve_frames()`](#an.kinematics.solver.solve_frames)). The
method and the measurements behind it are in the package docstring
([`an.kinematics`](an.kinematics.html.md#module-an.kinematics)); in one line: extended position-based dynamics on 2D
rigid bodies [Müller et al. 2020], Gauss–Seidel over the joints, a fixed
number of substeps and iterations, hinge limits as angular projections, the
two-link closed form as the initial guess.

**Two modes.** With `dt=None` (`pose`) the bodies are projected onto the
joints from where they stand, with no inertia and no gravity: the answer is
a function of the targets alone (plus the starting poses, which choose
between symmetric solutions). With a `dt` (`dynamic`) the bodies carry
velocity from frame to frame, gravity and forces act, a target is reached
over the frame’s substeps (the driven body moves, it does not teleport), and
the result depends on every frame before: baked from the first frame at a
fixed substep, it is still a pure function of the inputs.

**Conflicts.** When the joints cannot all hold (a grip beyond the arm’s
reach, an elbow asked past its range), Gauss–Seidel would spread the error
over every joint in the loop and tear the arm off its shoulder. The rows are
projected last-declared first, so the first-declared joint is the last
correction of every pass. A frame that leaves a rigid joint failing is
solved again with [`DFLT_CONFLICT_RETRY`](#an.kinematics.solver.DFLT_CONFLICT_RETRY) times the iterations from a
start nudged by [`DFLT_NUDGE`](#an.kinematics.solver.DFLT_NUDGE) (a straight chain pushed along its length
has no sideways correction to buckle with otherwise). If that at least
halves the failure ([`DFLT_CONFLICT_PROGRESS`](#an.kinematics.solver.DFLT_CONFLICT_PROGRESS)) it was slow convergence:
the retry is repeated with `retry` times the passes while each round still
cuts what is left by more than [`DFLT_STALL_PROGRESS`](#an.kinematics.solver.DFLT_STALL_PROGRESS), up to
[`DFLT_CONVERGE_CAP`](#an.kinematics.solver.DFLT_CONVERGE_CAP) times `iterations` (an#568). A round that stalls
is a conflict after all (a grip inside the arm’s length but past its elbow’s
range converges at first, then sits a pixel short), and what is left after the
cap is only reported. If not, it is a conflict, settled per
LOOP: the joints that share a cycle through the held bodies with a failing
one are tried last-declared first, and the first whose loss lets every
other joint hold is given up for the frame (a joint on no cycle, such as
any joint of a rope hung from one hook, is never a candidate: a tree can
always be satisfied). The joints given up are in
`SolveResult.dropped`, and their gaps in `unsatisfied`. So declare
the structure (the skeleton) before what it reaches for (a grip): an
unreachable grip is refused, and the arm reaches toward it from its
shoulder.

**Determinism.** Fixed order, fixed counts, no randomness, Python floats and
[`math`](https://docs.python.org/3/library/math.html#module-math) only inside the loop (Gauss–Seidel is sequential, and scalar
numpy is both slower and free to take a different SIMD path per CPU), numpy
only at the boundary: on one platform the same inputs give the same bytes,
run after run and process after process. Across platforms they need not: a
libm may differ in the last ulp, and a dynamic run amplifies that (measured:
1e-13 on one frame’s input is 0.014 units 96 frames later). So a cache key
built on a solve is built on its INPUTS ([`inputs_digest()`](#an.kinematics.solver.inputs_digest), which holds
[`SOLVER_VERSION`](#an.kinematics.solver.SOLVER_VERSION)), never on its output; [`quantize()`](#an.kinematics.solver.quantize) and
[`digest()`](#an.kinematics.solver.digest) are for storing and comparing poses on one platform.

```pycon
>>> arm = Body("arm", x=0.0, y=0.0, width=60.0, height=8.0, origin=(0.0, 0.5))
>>> r = solve([arm], [Pin(Point("arm", 0.0, 0.5), Point(WORLD, 0.0, 0.0))],
...           targets={"arm": {"rotation": 0.5}})
>>> round(r.pose("arm").rotation, 3), r.unsatisfied
(0.5, ())
```

### Module Attributes

| [`DFLT_ITERATIONS`](#an.kinematics.solver.DFLT_ITERATIONS)        | Gauss–Seidel passes over the joints per substep (dynamic) or per solve (pose).                                                                                                                              |
|-------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_SUBSTEPS`](#an.kinematics.solver.DFLT_SUBSTEPS)          | "smaller time steps are more effective than more iterations" (Catto 2024), and four keeps a 24 fps frame under a quarter of its period of free fall at 980 px/s².                                           |
| [`DFLT_DAMPING`](#an.kinematics.solver.DFLT_DAMPING)           | the one style knob a puppet has for how long it swings.                                                                                                                                                     |
| [`DFLT_TOLERANCE`](#an.kinematics.solver.DFLT_TOLERANCE)         | A joined joint whose points are further apart than this after the solve is reported as unsatisfied (scene units; a quarter pixel is below what a render shows).                                             |
| [`DFLT_ANGLE_TOLERANCE`](#an.kinematics.solver.DFLT_ANGLE_TOLERANCE)   | A hinge or weld whose angle is outside its range by more than this is reported (radians; 1e-3 rad is 0.06 degrees).                                                                                         |
| [`DFLT_CONFLICT_RETRY`](#an.kinematics.solver.DFLT_CONFLICT_RETRY)    | A solve that leaves a joint failing is run again with this many times the iterations before anything is given up: what more passes fix was slow convergence (a hard swing), what they do not is a conflict. |
| [`DFLT_CONFLICT_PROGRESS`](#an.kinematics.solver.DFLT_CONFLICT_PROGRESS) | A failing joint is in conflict when the retry left more than this fraction of its failure (residual over tolerance, or range broken over angle tolerance): a conflict is what more passes do not fix.       |
| [`DFLT_MAX_DROP_TRIALS`](#an.kinematics.solver.DFLT_MAX_DROP_TRIALS)   | The most trial solves [`solve()`](#an.kinematics.solver.solve) spends looking for the joint to give up in a conflict (each is a full solve of the frame).                                   |
| [`DFLT_NUDGE`](#an.kinematics.solver.DFLT_NUDGE)             | Radians each free body is turned by on a retry, alternating in sign (see `_nudge`): far below what a frame shows, enough to buckle a straight chain pushed along its length.                                |
| [`DFLT_POSITION_QUANTUM`](#an.kinematics.solver.DFLT_POSITION_QUANTUM)  | finer than any render shows.                                                                                                                                                                                |
| [`DFLT_SEGMENT_MARGIN`](#an.kinematics.solver.DFLT_SEGMENT_MARGIN)    | A contact or slide looks this far past a segment's ends (scene units) before letting the point go: a foot half a unit past the edge still stands.                                                           |
| [`SOLVER_VERSION`](#an.kinematics.solver.SOLVER_VERSION)         | Bumped whenever the solve can give a different answer for the same inputs (a changed projection, order, or default): part of every cache key built on this module.                                          |
| [`DFLT_CONVERGE_CAP`](#an.kinematics.solver.DFLT_CONVERGE_CAP)      | The most passes a frame whose first retry made progress is given, as a multiple of `iterations`: its retry is repeated with `retry` times the passes while each round still makes progress (an#568).        |
| [`DFLT_STALL_PROGRESS`](#an.kinematics.solver.DFLT_STALL_PROGRESS)    | A later round STALLS when what is left is more than this fraction of the round before (it cut less than 10%): a conflict, given up.                                                                         |
| [`POSE_CHANNELS`](#an.kinematics.solver.POSE_CHANNELS)          | The pose channels, in the order `SolveResult.poses` holds them.                                                                                                                                             |
| [`Targets`](#an.kinematics.solver.Targets)                | `{body name: {channel: value}}`; a channel given is held at its value for the frame (a nail), the others move.                                                                                              |

### Functions

| [`digest`](#an.kinematics.solver.digest)(poses, \*\*quanta)                         | A hex digest of the quantized poses' bytes, with the solver version: for comparing solved poses on one platform (a golden test).                                                                                                                  |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`inputs_digest`](#an.kinematics.solver.inputs_digest)(bodies, joints, \*[, targets, ...]) | A hex digest of everything a solve reads, with [`SOLVER_VERSION`](#an.kinematics.solver.SOLVER_VERSION): the cache key for a solve (or a run of them: pass the per-frame targets as a list, and `frames`, `dt` and the rest as `options`). |
| [`quantize`](#an.kinematics.solver.quantize)(poses, \*[, position_quantum, ...])      | `poses` (any shape whose last axis is [`POSE_CHANNELS`](#an.kinematics.solver.POSE_CHANNELS)) rounded to the quanta a document stores: positions and scale to `position_quantum`, rotation to `angle_quantum`.                            |
| [`resolve_rests`](#an.kinematics.solver.resolve_rests)(bodies, joints)                     | `joints` with every `rest=None` hinge and weld given the relative angle the bodies have now, so a run of frames measures its limits from one pose rather than from each frame's.                                                                  |
| [`solve`](#an.kinematics.solver.solve)(bodies, joints, \*[, targets, forces, ...]) | One frame: the poses of all `bodies` that satisfy the joined `joints` with the `targets` held, forces and `gravity` acting.                                                                                                                       |
| [`solve_frames`](#an.kinematics.solver.solve_frames)(bodies, joints, \*, frames, dt)      | `frames` solves in a row, each starting from the last: the caller's time dimension.                                                                                                                                                               |

### Classes

| [`FramesResult`](#an.kinematics.solver.FramesResult)(bodies, poses, unsatisfied, ...)     | A run of frames: `poses` is `(frames, bodies, 4)`; `unsatisfied` and `limit_violations` are per frame; `snaps` lists every joint that is enforced again after a frame it was not (the caller rejoined it, or a conflict had dropped it) as `(frame, joint index, distance)`, the gap it closes in one frame (the caller decides whether to blend or to refuse it; in dynamic mode a large gap yanks the bodies it joins); `final` is the last frame's bodies, ready to continue the run; `dropped` the joints each frame gave up in a conflict.   |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`SolveResult`](#an.kinematics.solver.SolveResult)(bodies, poses, residuals, ...[, ...]) | What one frame's solve found.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |

### Exceptions

| [`KinematicsError`](#an.kinematics.solver.KinematicsError)   | A solve that cannot be set up: an unknown body, gravity without time, a joint on the world alone, a body with no extent.   |
|--------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|

### an.kinematics.solver.DFLT_ANGLE_TOLERANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.001*

A hinge or weld whose angle is outside its range by more than this is
reported (radians; 1e-3 rad is 0.06 degrees).

### an.kinematics.solver.DFLT_CONFLICT_PROGRESS *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

A failing joint is in conflict when the retry left more than this fraction
of its failure (residual over tolerance, or range broken over angle
tolerance): a conflict is what more passes do not fix.

### an.kinematics.solver.DFLT_CONFLICT_RETRY *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 4*

A solve that leaves a joint failing is run again with this many times the
iterations before anything is given up: what more passes fix was slow
convergence (a hard swing), what they do not is a conflict.

### an.kinematics.solver.DFLT_CONVERGE_CAP *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 64*

The most passes a frame whose first retry made progress is given, as a
multiple of `iterations`: its retry is repeated with `retry` times the
passes while each round still makes progress (an#568). On 300 random
out-and-back reaches of a two-link arm in dynamic mode, 126 frames were left
up to 6 px apart at the single retry (most of them a grip past the elbow’s
range, a conflict that halved once and then stalled); none at a cap of 64.
A frame that converges at once pays nothing; a 50-link rope with its end out
of reach pays ~90 rather than ~40 ms a frame, with 7 rather than 22 frames
left failing.

### an.kinematics.solver.DFLT_DAMPING *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.02*

the one style knob
a puppet has for how long it swings. 0.02 reads as a wooden marionette.
It is per substep, so changing `substeps` changes the swing too (both
are in every cache key built on a solve).

* **Type:**
  Fraction of velocity lost per substep in dynamic mode

### an.kinematics.solver.DFLT_ITERATIONS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 8*

Gauss–Seidel passes over the joints per substep (dynamic) or per solve
(pose). Measured (package docstring): a two-link chain with a goal and a
hinge limit reaches its target to 1e-6 px within 6 passes from the
closed-form start.

### an.kinematics.solver.DFLT_MAX_DROP_TRIALS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 12*

The most trial solves [`solve()`](#an.kinematics.solver.solve) spends looking for the joint to give
up in a conflict (each is a full solve of the frame).

### an.kinematics.solver.DFLT_NUDGE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.001*

Radians each free body is turned by on a retry, alternating in sign (see
`_nudge`): far below what a frame shows, enough to buckle a straight
chain pushed along its length.

### an.kinematics.solver.DFLT_POSITION_QUANTUM *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1e-06*

finer than any
render shows.

* **Type:**
  Quanta a stored pose is rounded to by [`quantize()`](#an.kinematics.solver.quantize)

### an.kinematics.solver.DFLT_SEGMENT_MARGIN *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

A contact or slide looks this far past a segment’s ends (scene units)
before letting the point go: a foot half a unit past the edge still stands.

### an.kinematics.solver.DFLT_STALL_PROGRESS *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.9*

A later round STALLS when what is left is more than this fraction of the
round before (it cut less than 10%): a conflict, given up. Laxer than
[`DFLT_CONFLICT_PROGRESS`](#an.kinematics.solver.DFLT_CONFLICT_PROGRESS), which decides the first retry: requiring
every round to halve gave up a reachable grip that was still converging.

### an.kinematics.solver.DFLT_SUBSTEPS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 4*

“smaller time steps are more effective
than more iterations” (Catto 2024), and four keeps a 24 fps frame under a
quarter of its period of free fall at 980 px/s².

* **Type:**
  Substeps per frame in dynamic mode

### an.kinematics.solver.DFLT_TOLERANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.25*

A joined joint whose points are further apart than this after the solve is
reported as unsatisfied (scene units; a quarter pixel is below what a
render shows).

### *class* an.kinematics.solver.FramesResult(bodies, poses, unsatisfied, limit_violations, snaps, final=(), dropped=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A run of frames: `poses` is `(frames, bodies, 4)`; `unsatisfied`
and `limit_violations` are per frame; `snaps` lists every joint that
is enforced again after a frame it was not (the caller rejoined it, or a
conflict had dropped it) as `(frame, joint index, distance)`, the gap
it closes in one frame (the caller decides whether to blend or to refuse
it; in dynamic mode a large gap yanks the bodies it joins); `final` is the last frame’s bodies, ready to continue the
run; `dropped` the joints each frame gave up in a conflict.

### *exception* an.kinematics.solver.KinematicsError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A solve that cannot be set up: an unknown body, gravity without time,
a joint on the world alone, a body with no extent.

### an.kinematics.solver.POSE_CHANNELS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('x', 'y', 'rotation', 'scale')*

The pose channels, in the order `SolveResult.poses` holds them.

### an.kinematics.solver.SOLVER_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '2'*

Bumped whenever the solve can give a different answer for the same inputs
(a changed projection, order, or default): part of every cache key built
on this module.

### *class* an.kinematics.solver.SolveResult(bodies, poses, residuals, unsatisfied, limit_violations, dropped=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one frame’s solve found.

`bodies` are the input bodies with their poses and velocities updated,
ready to be the next frame’s input; `poses` is the same as an array,
one row per body in input order, columns [`POSE_CHANNELS`](#an.kinematics.solver.POSE_CHANNELS).
`residuals` has one entry per joint in input order: how far apart a
joined joint’s points still are (0 for an unjoined joint, or one that
holds; a compliant joint’s stretch); `unsatisfied` lists the rigid
joints’ `(joint index, residual)` pairs above tolerance, and
`limit_violations` the rigid hinges and welds outside their angle range
as `(joint index, radians)`. `dropped` lists the joints
given up in a conflict (module docstring), in the order they were.

#### *property* ok *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Every joined joint holds and every range is kept.

```pycon
>>> solve([Body("b")], []).ok
True
```

#### pose(name)

The body called `name` as solved.

```pycon
>>> b = Body("b", x=1.0)
>>> solve([b], []).pose("b").x
1.0
```

* **Return type:**
  [`Body`](an.kinematics.bodies.html.md#an.kinematics.bodies.Body)

### an.kinematics.solver.Targets

`{body name: {channel: value}}`; a channel given is held at its value
for the frame (a nail), the others move.

alias of [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.kinematics.solver.digest(poses, \*\*quanta)

A hex digest of the quantized poses’ bytes, with the solver version:
for comparing solved poses on one platform (a golden test). A cache key
is built on the inputs instead ([`inputs_digest()`](#an.kinematics.solver.inputs_digest)).

```pycon
>>> digest(np.zeros((2, 4))) == digest(np.zeros((2, 4)) + 1e-9)
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.kinematics.solver.inputs_digest(bodies, joints, , targets=None, forces=(), gravity=None, \*\*options)

A hex digest of everything a solve reads, with [`SOLVER_VERSION`](#an.kinematics.solver.SOLVER_VERSION):
the cache key for a solve (or a run of them: pass the per-frame targets
as a list, and `frames`, `dt` and the rest as `options`). Floats
are hashed exactly (`float.hex`); mappings by sorted key.

```pycon
>>> a = inputs_digest([Body("b", x=1.0)], [], dt=1 / 24)
>>> a == inputs_digest([Body("b", x=1.0)], [], dt=1 / 24), a == inputs_digest([Body("b", x=1.0 + 1e-15)], [], dt=1 / 24)
(True, False)
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.kinematics.solver.quantize(poses, , position_quantum=1e-06, angle_quantum=1e-07)

`poses` (any shape whose last axis is [`POSE_CHANNELS`](#an.kinematics.solver.POSE_CHANNELS)) rounded
to the quanta a document stores: positions and scale to
`position_quantum`, rotation to `angle_quantum`.

```pycon
>>> q = quantize(np.array([[1.00000049, 2.0, 0.123456789, 1.0]]))
>>> float(q[0, 0]), bool(abs(q[0, 2] - 0.1234568) < 1e-15)
(1.0, True)
```

* **Return type:**
  `ndarray`

### an.kinematics.solver.resolve_rests(bodies, joints)

`joints` with every `rest=None` hinge and weld given the relative
angle the bodies have now, so a run of frames measures its limits from
one pose rather than from each frame’s.

```pycon
>>> a = Body("a", rotation=0.1); b = Body("b", rotation=0.4)
>>> [round(j.rest, 3) for j in resolve_rests([a, b], [Hinge(Point("a", 0.5, 0.5), Point("b", 0.5, 0.5), limits=(-1.0, 1.0))])]
[0.3]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Pin`](an.kinematics.joints.html.md#an.kinematics.joints.Pin) | [`Hinge`](an.kinematics.joints.html.md#an.kinematics.joints.Hinge) | [`Weld`](an.kinematics.joints.html.md#an.kinematics.joints.Weld) | [`Distance`](an.kinematics.joints.html.md#an.kinematics.joints.Distance) | [`Slide`](an.kinematics.joints.html.md#an.kinematics.joints.Slide) | [`Contact`](an.kinematics.joints.html.md#an.kinematics.joints.Contact)]

### an.kinematics.solver.solve(bodies, joints, , targets=None, forces=(), gravity=None, dt=None, iterations=8, substeps=4, damping=0.02, tolerance=0.25, angle_tolerance=0.001, seed_chains=True, retry=4, drop_conflicts=True, seed=0, converge_cap=64)

One frame: the poses of all `bodies` that satisfy the joined
`joints` with the `targets` held, forces and `gravity` acting.

`dt=None` is pose mode: no inertia, no gravity, no pushes (a gravity or
a `Force.vector` is refused there: they need time; a `Force.toward`
pull works in both modes). With a `dt` the bodies step through
`substeps` of `dt / substeps`, carrying their velocities in and out,
and a target is reached over those substeps. `targets` hold channels
exactly (a body held in x and y is immovable to the joints for the frame,
one held in rotation unturnable); a target beyond a chain’s reach shows
up in `unsatisfied` rather than stretching anything. Hinge and weld
rests left `None` are the relative angles the bodies have on input.
A frame that leaves a joint failing is solved again with `retry` times
the `iterations` (1: never), again while each round still cuts what is
left, up to `converge_cap` times the `iterations`; `drop_conflicts`
then gives up the joints in conflict (a first retry that did not halve the
failure, or a later one that stalled), last declared first (module docstring);
`False` keeps them all and reports what fails. `seed` is reserved for stochastic drivers and does nothing in this
version: the solve has no randomness.

A shoulder driven to a point, an upper arm pinned to it, a forearm
hinged to that, the hand pinned to a handle (the two-link case): the hand
lands on the handle and the elbow bends the way its range allows.

```pycon
>>> torso = Body("torso", width=40.0, height=80.0)
>>> upper = Body("upper", x=20.0, y=-30.0, width=50.0, height=10.0, origin=(0.0, 0.5))
>>> fore = Body("fore", x=70.0, y=-30.0, width=40.0, height=8.0, origin=(0.0, 0.5))
>>> handle = Body("handle", x=80.0, y=10.0, width=4.0, height=4.0, fixed=True)
>>> joints = [Pin(Point("upper", 0.0, 0.5), Point("torso", 1.0, 0.125)),
...           Hinge(Point("fore", 0.0, 0.5), Point("upper", 1.0, 0.5), limits=(-2.6, 0.0)),
...           Pin(Point("fore", 1.0, 0.5), Point("handle", 0.5, 0.5))]
>>> r = solve([torso, upper, fore, handle], joints, targets={"torso": {"x": 0.0, "y": 0.0}})
>>> r.ok, tuple(round(v, 3) for v in r.residuals)
(True, (0.0, 0.0, 0.0))
```

Out of reach, the grip is reported, and the arm stays on its shoulder:

```pycon
>>> far = handle.posed(x=300.0)
>>> r = solve([torso, upper, fore, far], joints, targets={"torso": {"x": 0.0, "y": 0.0}})
>>> [j for j, _ in r.unsatisfied], r.dropped, [round(v, 6) for v in r.residuals[:2]]
([2], (2,), [0.0, 0.0])
```

* **Return type:**
  [`SolveResult`](#an.kinematics.solver.SolveResult)

### an.kinematics.solver.solve_frames(bodies, joints, , frames, dt, targets_at=None, joints_at=None, forces=(), gravity=None, \*\*options)

`frames` solves in a row, each starting from the last: the caller’s
time dimension. `targets_at(k)` (or `targets_at[k]`) gives frame
`k`’s targets; `joints_at(k)` its joints (the same list with
`joined` flags flipped is how a joint is unjoined and rejoined). Hinge
and weld rests are fixed from the starting poses. `options` go to
[`solve()`](#an.kinematics.solver.solve).

A part unjoined falls, and is caught where it is when rejoined:

```pycon
>>> peg = Body("peg", width=2.0, height=2.0, fixed=True)
>>> part = Body("part", y=10.0, width=4.0, height=20.0, origin=(0.5, 0.0))
>>> joined = [Pin(Point("part", 0.5, 0.0), Point("peg", 0.5, 0.5))]
>>> loose = [Pin(Point("part", 0.5, 0.0), Point("peg", 0.5, 0.5), joined=False)]
>>> r = solve_frames([peg, part], joined, frames=12, dt=1 / 24, gravity=(0.0, 980.0),
...                  joints_at=lambda k: loose if 2 <= k < 8 else joined)
>>> bool(r.poses[1, 1, 1] < r.poses[7, 1, 1]), r.snaps[0][:2], r.snaps[0][2] > 2.0
(True, (8, 0), True)
>>> r.unsatisfied[-1]
()
```

* **Return type:**
  [`FramesResult`](#an.kinematics.solver.FramesResult)
