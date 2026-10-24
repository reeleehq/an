# an.kinematics

A deterministic 2D constraint solver: bodies joined at points, driven at a
few of them, settled by gravity (an#499, ADR 0008).

Four nouns and one verb. A [`Body`](#an.kinematics.Body) is a rigid rectangle posed by
`(x, y, rotation, scale)`; a [`Point`](#an.kinematics.Point) on it is a fraction of its
extent. A joint relates two bodies (or a body and `WORLD`):
[`Pin`](#an.kinematics.Pin), [`Hinge`](#an.kinematics.Hinge) (a pin with an angle range), [`Weld`](#an.kinematics.Weld),
[`Distance`](#an.kinematics.Distance) (`equal` a rod, `at_most` a string, `at_least` a
spacer), [`Slide`](#an.kinematics.Slide) (a groove) and [`Contact`](#an.kinematics.Contact) (one-sided: a foot on
the ground, a lamp on a table). A driver is a target on a body’s channels (a
nail: met exactly where the joints allow), a [`Force`](#an.kinematics.Force) (a push, or a
soft pull toward a point), or gravity. [`solve()`](#an.kinematics.solve) does one frame,
[`solve_frames()`](#an.kinematics.solve_frames) a run of them with the caller’s targets and
joined/unjoined joints per frame, and both return a typed result that names
what could not be held instead of raising.

```pycon
>>> torso = Body("torso", width=40.0, height=80.0)
>>> upper = Body("upper", x=20.0, y=-30.0, width=50.0, height=10.0, origin=(0.0, 0.5))
>>> fore = Body("fore", x=70.0, y=-30.0, width=40.0, height=8.0, origin=(0.0, 0.5))
>>> handle = Body("handle", x=80.0, y=10.0, width=4.0, height=4.0, fixed=True)
>>> arm = [Pin(Point("upper", 0.0, 0.5), Point("torso", 1.0, 0.125)),
...        Hinge(Point("fore", 0.0, 0.5), Point("upper", 1.0, 0.5), limits=(-2.6, 0.0)),
...        Pin(Point("fore", 1.0, 0.5), Point("handle", 0.5, 0.5))]
>>> solve([torso, upper, fore, handle], arm, targets={"torso": {"x": 0.0, "y": 0.0}}).ok
True
```

Nothing here imports the scene IR or the stage, and nothing names an
animation: bodies are numbers, joints are rows (`# extraction candidate`:
this becomes its own package when a second consumer exists). The compile
pass that reads joints from a scene is P2 (an#512).

**The method, and why** (measured in
`misc/docs/research/puppeteering_2026-10.md` §4, which compared analytic
two-bone, CCD, FABRIK, PBD and XPBD on the same tasks, and re-measured on
this module by `misc/docs/research/puppeteering_2026-10/measure_kinematics.py`,
results in `kinematics_measurements.json` beside it; CPython 3.12, x86-64,
one core). Extended position-based dynamics on 2D rigid bodies (XPBD,
Macklin et al. 2016; rigid bodies and joints, Müller et al. 2020):
Gauss–Seidel over the joints in a fixed order, each a projection with the
generalized inverse mass `1/m + (r × n)² / I` about the body’s centre (or
about its pose point while that is held), hinge limits as angular
projections, a fixed count of substeps and iterations. It is the one family
of the five that does chains, strings, rods, contacts, gravity and
unjoining in one loop, and its compliance is a stiffness that does not
depend on the iteration count. Its weakness, slow propagation down long
chains, is covered for the common case by the analytic two-link solve used
as the initial guess for every chain between two held ends (an arm with a
hand is a two-link chain whose second link is the forearm and the hand held
at their current angles), which also makes the elbow’s bend side an explicit
choice (the side its range allows, else the side it already has).

- **Convergence per iteration** (the arm above, pose mode, worst residual):
  from the closed-form start, 2e-14 px after one pass; from a cold start,
  5.8 / 3.3 / 0.80 / 0.10 / 0.0014 px after 1 / 2 / 4 / 8 / 16 passes, 5e-14
  after 64. A frame that leaves a joint failing is retried with four times
  the passes, so the default eight reach the sixteen-pass figure when needed.
- **Singularities**: a target at exactly full reach (a straight arm) is met
  with zero residual and a straight elbow; 1 px or 5 px beyond reach the
  grip alone is refused (`dropped`, its gap in `unsatisfied`), the
  shoulder and elbow hold exactly, and the arm points straight at the
  target; a target on the shoulder itself (inside the nearest reach, where
  the direction is undefined) is refused the same way, the arm left where
  it was rather than guessed. (The torso is nailed in rotation here; free
  to turn, it turns toward the target first.) A chain between two rigidly
  held ends whose ends are outside its reach is refused before any pass.
- **A straight chain pushed along its length** (a rope bridge of 3 to 20
  planks pinned at 0.8 of its length, laid straight): no correction has a
  sideways part, so nothing moves; the retry’s start, nudged by 1e-3 rad,
  buckles it, and every joint holds (tests).
- **Stability at frame-exact steps** (a 12-link chain dropped horizontal, 10 s
  at 24 fps, under gravity): at 4 substeps (the default) no frame fails a
  joint and the tip hangs within 0.03° of vertical; at 1 or 2 substeps the
  whip under-converges (worst 3.2 / 0.9 px with the retry, 17 / 3.4 px
  without), reported per frame and never given up (a tree cannot conflict).
  Nothing diverges at any setting.
- **Compliance**: a soft rod (`compliance=1e-4`) under a 100-unit weight
  stretches 11.85 units after one second at 1, 2, 8 and 32 iterations alike,
  to the digit; it settles to the static 9.8.
- **Cost per frame**, dynamic, defaults: 14 ms for five ten-part
  marionettes (50 bodies, 65 joints, 25 strings), no frame failing; 0.9 ms for
  the two-link reach in pose mode. A 50-link rope or chain costs 34-48 ms (the
  retry runs on its failing frames) and under-converges on 40-47 of 48 frames
  (Gauss–Seidel’s n² propagation): reported, never cut. Long ropes want more
  substeps, or the FABRIK seam the research names.
- **Determinism**: Python floats and [`math`](https://docs.python.org/3/library/math.html#module-math) inside the loop, numpy at the
  boundary; bitwise-equal poses across runs and across processes on one
  platform (`tests/test_kinematics.py`). Not across platforms: a dynamic
  run amplifies a last-ulp libm difference (1e-13 on one frame’s input is
  0.014 units 96 frames later), so a cache key is built on the inputs
  ([`inputs_digest()`](#an.kinematics.inputs_digest), with `SOLVER_VERSION`), never the output.

Not in this version: friction (a contact is frictionless: a lamp on a table
sliding sideways stays where it is until the edge passes), blending a snap
(a rejoined joint closes its gap in one frame, reported in
`FramesResult.snaps`), and the stochastic driver `seed` is reserved
for.

### Functions

| [`mass`](#an.kinematics.mass)(body)                                        | The body's mass: density × scaled area; `inf` for a fixed body.                                                                                                                                                     |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`inertia`](#an.kinematics.inertia)(body)                                     | Rotational inertia about the body's pose point (parallel-axis from the extent's centre); `inf` for a fixed body.                                                                                                    |
| [`point_world`](#an.kinematics.point_world)(body, point)                          | The point's position in the body's frame of reference (the world, for a body posed in it); a `WORLD` point is returned as is.                                                                                       |
| [`reach`](#an.kinematics.reach)(l1, l2)                                     | The `(nearest, farthest)` distance from the root a two-link chain of lengths `l1` and `l2` can put its tip.                                                                                                         |
| [`two_bone`](#an.kinematics.two_bone)(root, target, lengths, \*[, bend])       | Absolute angles `(theta1, theta2)` of two links of `lengths` `(l1, l2)` hinged at `root` so that the tip meets `target`; `None` when the target is out of [`reach()`](#an.kinematics.reach). |
| [`solve`](#an.kinematics.solve)(bodies, joints, \*[, targets, forces, ...]) | One frame: the poses of all `bodies` that satisfy the joined `joints` with the `targets` held, forces and `gravity` acting.                                                                                         |
| [`solve_frames`](#an.kinematics.solve_frames)(bodies, joints, \*, frames, dt)      | `frames` solves in a row, each starting from the last: the caller's time dimension.                                                                                                                                 |
| [`resolve_rests`](#an.kinematics.resolve_rests)(bodies, joints)                     | `joints` with every `rest=None` hinge and weld given the relative angle the bodies have now, so a run of frames measures its limits from one pose rather than from each frame's.                                    |
| [`quantize`](#an.kinematics.quantize)(poses, \*[, position_quantum, ...])      | `poses` (any shape whose last axis is `POSE_CHANNELS`) rounded to the quanta a document stores: positions and scale to `position_quantum`, rotation to `angle_quantum`.                                             |
| [`digest`](#an.kinematics.digest)(poses, \*\*quanta)                         | A hex digest of the quantized poses' bytes, with the solver version: for comparing solved poses on one platform (a golden test).                                                                                    |
| [`inputs_digest`](#an.kinematics.inputs_digest)(bodies, joints, \*[, targets, ...]) | A hex digest of everything a solve reads, with `SOLVER_VERSION`: the cache key for a solve (or a run of them: pass the per-frame targets as a list, and `frames`, `dt` and the rest as `options`).                  |

### Classes

| [`Body`](#an.kinematics.Body)(name[, x, y, rotation, scale, width, ...])   | A rigid rectangle posed in one frame.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Point`](#an.kinematics.Point)(body, u, v)                                 | A point on a body, as a fraction of the body's extent.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| [`Pin`](#an.kinematics.Pin)(a, b[, compliance, joined])                   | Two points coincide; free rotation about them.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| [`Hinge`](#an.kinematics.Hinge)(a, b[, limits, rest, compliance, joined])   | A pin with a range for the angle of `b`'s body relative to `a`'s.                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| [`Weld`](#an.kinematics.Weld)(a, b[, rest, compliance, joined])            | A pin plus a fixed relative angle (`rest`, or the starting one).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| [`Distance`](#an.kinematics.Distance)(a, b, length[, mode, compliance, ...])   | The two points keep `length` apart: exactly, at most, or at least.                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| [`Slide`](#an.kinematics.Slide)(point, start, end[, compliance, joined])    | `point` stays on the segment `start`–`end` (both on one other body, or the world), within its ends.                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| [`Contact`](#an.kinematics.Contact)(point, start, end[, compliance, joined])  | `point` stays on the free side of the segment `start`–`end`, or on it; nothing holds it there (it may lift off), and nothing holds it beyond the segment's ends (it may fall off an edge).                                                                                                                                                                                                                                                                                                                                                      |
| [`Force`](#an.kinematics.Force)(point[, vector, toward, strength])          | A driver that is not a target: a constant `vector` (force per unit mass, applied at `point`, so an off-centre push also turns the body), or a pull of `point` `toward` a position with `strength` (a compliant zero-length rope: `compliance = 1 / strength`), or both.                                                                                                                                                                                                                                                                         |
| [`SolveResult`](#an.kinematics.SolveResult)(bodies, poses, residuals, ...[, ...]) | What one frame's solve found.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| [`FramesResult`](#an.kinematics.FramesResult)(bodies, poses, unsatisfied, ...)     | A run of frames: `poses` is `(frames, bodies, 4)`; `unsatisfied` and `limit_violations` are per frame; `snaps` lists every joint that is enforced again after a frame it was not (the caller rejoined it, or a conflict had dropped it) as `(frame, joint index, distance)`, the gap it closes in one frame (the caller decides whether to blend or to refuse it; in dynamic mode a large gap yanks the bodies it joins); `final` is the last frame's bodies, ready to continue the run; `dropped` the joints each frame gave up in a conflict. |

### Exceptions

| [`KinematicsError`](#an.kinematics.KinematicsError)   | A solve that cannot be set up: an unknown body, gravity without time, a joint on the world alone, a body with no extent.   |
|--------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|

### *class* an.kinematics.Body(name, x=0.0, y=0.0, rotation=0.0, scale=1.0, width=1.0, height=1.0, origin=(0.5, 0.5), fixed=False, density=1.0, vx=0.0, vy=0.0, omega=0.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A rigid rectangle posed in one frame.

`fixed` bodies have infinite mass: joints move everything else around
them. `vx`, `vy` (the velocity of the extent’s centre) and `omega`
are what a dynamic solve carries from one frame to the next (zero at
rest). `density` sets the mass per unit area, spread evenly over the
extent, so a limb whose pose point is at its end still swings about it.

```pycon
>>> b = Body("box", width=4.0, height=2.0)
>>> round(mass(b), 3), round(inertia(b), 3)
(8.0, 13.333)
```

#### posed(, x=None, y=None, rotation=None, vx=None, vy=None, omega=None)

This body with the given pose channels (and velocities) replaced.

```pycon
>>> Body("b").posed(x=3.0).x
3.0
```

* **Return type:**
  [`Body`](an.kinematics.bodies.html.md#an.kinematics.bodies.Body)

### *class* an.kinematics.Contact(point, start, end, compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`point` stays on the free side of the segment `start`–`end`, or
on it; nothing holds it there (it may lift off), and nothing holds it
beyond the segment’s ends (it may fall off an edge).

```pycon
>>> Contact(Point("lamp", 0.5, 1.0), Point("table", 0.0, 0.0), Point("table", 1.0, 0.0)).joined
True
```

### *class* an.kinematics.Distance(a, b, length, mode='equal', compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The two points keep `length` apart: exactly, at most, or at least.

```pycon
>>> Distance(Point("hand", 0.5, 0.5), Point("world", 0.0, -200.0), length=150.0, mode="at_most").mode
'at_most'
```

### *class* an.kinematics.Force(point, vector=None, toward=None, strength=1.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A driver that is not a target: a constant `vector` (force per unit
mass, applied at `point`, so an off-centre push also turns the body), or
a pull of `point` `toward` a position with `strength` (a compliant
zero-length rope: `compliance = 1 / strength`), or both.

```pycon
>>> Force(Point("kite", 0.5, 0.0), vector=(30.0, 0.0)).toward is None
True
```

### *class* an.kinematics.FramesResult(bodies, poses, unsatisfied, limit_violations, snaps, final=(), dropped=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A run of frames: `poses` is `(frames, bodies, 4)`; `unsatisfied`
and `limit_violations` are per frame; `snaps` lists every joint that
is enforced again after a frame it was not (the caller rejoined it, or a
conflict had dropped it) as `(frame, joint index, distance)`, the gap
it closes in one frame (the caller decides whether to blend or to refuse
it; in dynamic mode a large gap yanks the bodies it joins); `final` is the last frame’s bodies, ready to continue the
run; `dropped` the joints each frame gave up in a conflict.

### *class* an.kinematics.Hinge(a, b, limits=None, rest=None, compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A pin with a range for the angle of `b`’s body relative to `a`’s.

`limits` is `(lo, hi)` in radians about `rest`, within
`[-pi, pi]`; `rest` is the relative angle (`b.rotation -
a.rotation`) the range is measured from, taken from the bodies’ poses at
the start of the solve when `None`. With no `limits` it is a pin.

```pycon
>>> Hinge(Point("fore", 0.0, 0.5), Point("upper", 1.0, 0.5), limits=(-2.6, 0.0)).limits
(-2.6, 0.0)
```

### *exception* an.kinematics.KinematicsError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A solve that cannot be set up: an unknown body, gravity without time,
a joint on the world alone, a body with no extent.

### *class* an.kinematics.Pin(a, b, compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Two points coincide; free rotation about them.

```pycon
>>> Pin(Point("arm", 0.0, 0.5), Point("torso", 1.0, 0.2)).joined
True
```

### *class* an.kinematics.Point(body, u, v)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A point on a body, as a fraction of the body’s extent.

On `WORLD` the fraction is an absolute position instead.

```pycon
>>> Point("hand", 0.5, 1.0).body
'hand'
```

### *class* an.kinematics.Slide(point, start, end, compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`point` stays on the segment `start`–`end` (both on one other
body, or the world), within its ends.

```pycon
>>> Slide(Point("bead", 0.5, 0.5), Point("world", 0.0, 0.0), Point("world", 100.0, 0.0)).joined
True
```

### *class* an.kinematics.SolveResult(bodies, poses, residuals, unsatisfied, limit_violations, dropped=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one frame’s solve found.

`bodies` are the input bodies with their poses and velocities updated,
ready to be the next frame’s input; `poses` is the same as an array,
one row per body in input order, columns `POSE_CHANNELS`.
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

### *class* an.kinematics.Weld(a, b, rest=None, compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A pin plus a fixed relative angle (`rest`, or the starting one).

```pycon
>>> Weld(Point("hat", 0.5, 1.0), Point("head", 0.5, 0.0)).rest is None
True
```

### an.kinematics.digest(poses, \*\*quanta)

A hex digest of the quantized poses’ bytes, with the solver version:
for comparing solved poses on one platform (a golden test). A cache key
is built on the inputs instead ([`inputs_digest()`](#an.kinematics.inputs_digest)).

```pycon
>>> digest(np.zeros((2, 4))) == digest(np.zeros((2, 4)) + 1e-9)
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.kinematics.inertia(body)

Rotational inertia about the body’s pose point (parallel-axis from the
extent’s centre); `inf` for a fixed body.

```pycon
>>> round(inertia(Body("b", width=4.0, height=2.0, origin=(0.0, 0.5))), 3)
45.333
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.kinematics.inputs_digest(bodies, joints, , targets=None, forces=(), gravity=None, \*\*options)

A hex digest of everything a solve reads, with `SOLVER_VERSION`:
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

### an.kinematics.mass(body)

The body’s mass: density × scaled area; `inf` for a fixed body.

```pycon
>>> mass(Body("b", width=3.0, height=2.0, scale=2.0))
24.0
>>> mass(Body("b", fixed=True))
inf
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.kinematics.point_world(body, point)

The point’s position in the body’s frame of reference (the world, for
a body posed in it); a `WORLD` point is returned as is.

```pycon
>>> b = Body("b", x=1.0, y=1.0, rotation=math.pi / 2, width=2.0, height=2.0)
>>> tuple(round(c, 9) for c in point_world(b, Point("b", 1.0, 0.5)))
(1.0, 2.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.kinematics.quantize(poses, , position_quantum=1e-06, angle_quantum=1e-07)

`poses` (any shape whose last axis is `POSE_CHANNELS`) rounded
to the quanta a document stores: positions and scale to
`position_quantum`, rotation to `angle_quantum`.

```pycon
>>> q = quantize(np.array([[1.00000049, 2.0, 0.123456789, 1.0]]))
>>> float(q[0, 0]), bool(abs(q[0, 2] - 0.1234568) < 1e-15)
(1.0, True)
```

* **Return type:**
  `ndarray`

### an.kinematics.reach(l1, l2)

The `(nearest, farthest)` distance from the root a two-link chain of
lengths `l1` and `l2` can put its tip.

```pycon
>>> reach(3.0, 4.0)
(1.0, 7.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.kinematics.resolve_rests(bodies, joints)

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

### an.kinematics.solve(bodies, joints, , targets=None, forces=(), gravity=None, dt=None, iterations=8, substeps=4, damping=0.02, tolerance=0.25, angle_tolerance=0.001, seed_chains=True, retry=4, drop_conflicts=True, seed=0)

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
the `iterations` (1: never); `drop_conflicts`
then gives up the joints in conflict, last declared first (module
docstring); `False` keeps them all and reports what fails. `seed` is reserved for stochastic drivers and does nothing in this
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
  [`SolveResult`](an.kinematics.solver.html.md#an.kinematics.solver.SolveResult)

### an.kinematics.solve_frames(bodies, joints, , frames, dt, targets_at=None, joints_at=None, forces=(), gravity=None, \*\*options)

`frames` solves in a row, each starting from the last: the caller’s
time dimension. `targets_at(k)` (or `targets_at[k]`) gives frame
`k`’s targets; `joints_at(k)` its joints (the same list with
`joined` flags flipped is how a joint is unjoined and rejoined). Hinge
and weld rests are fixed from the starting poses. `options` go to
[`solve()`](#an.kinematics.solve).

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
  [`FramesResult`](an.kinematics.solver.html.md#an.kinematics.solver.FramesResult)

### an.kinematics.two_bone(root, target, lengths, , bend=1)

Absolute angles `(theta1, theta2)` of two links of `lengths`
`(l1, l2)` hinged at `root` so that the tip meets `target`; `None`
when the target is out of [`reach()`](#an.kinematics.reach).

`bend` is `+1` for a middle joint that deviates counter-clockwise from
the root-to-target line (which, on a y-down screen, reads as clockwise),
`-1` for the other side. Each side is a different pose of the same chain;
which one is right is the author’s (or a hinge range’s) choice.

```pycon
>>> t1, t2 = two_bone((0.0, 0.0), (1.0, 1.0), (1.0, 1.0), bend=1)
>>> round(math.degrees(t1)), round(math.degrees(t2))
(90, 0)
>>> t1, t2 = two_bone((0.0, 0.0), (1.0, 1.0), (1.0, 1.0), bend=-1)
>>> round(math.degrees(t1)), round(math.degrees(t2))
(0, 90)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### Modules

| [`bodies`](an.kinematics.bodies.html.md#module-an.kinematics.bodies)   | Bodies and the points on them: the things a joint joins and a driver moves.   |
|---------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`chains`](an.kinematics.chains.html.md#module-an.kinematics.chains)   | Closed-form pieces for chains: the two-link reach and its reachable range.    |
| [`joints`](an.kinematics.joints.html.md#module-an.kinematics.joints)   | Joints: declared relations between two bodies, or a body and the world.       |
| [`solver`](an.kinematics.solver.html.md#module-an.kinematics.solver)   | The solve: bodies joined at points, driven at a few, settled by gravity.      |
