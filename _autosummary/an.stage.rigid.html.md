# an.stage.rigid

Rigid falls in the stage plane: a let-go item’s flight, landing, tip and bounce; a body toppling about a contact.

Two motions, both of a rigid drawing under gravity (stage px, `y` down, an
angle turning `+x` toward `+y`, clockwise on screen), shared by the hold
layer’s `release` ([`an.stage.hold`](an.stage.hold.html.md#module-an.stage.hold)) and the `topple` pass
([`an.stage.topple`](an.stage.topple.html.md#module-an.stage.topple)):

- **A drop** ([`drop_track()`](#an.stage.rigid.drop_track)): the item’s centre flies a parabola from
  where it was let go, spinning at a CONSTANT rate (a body in the air has no
  torque on it), until its lowest point touches the floor slightly short of
  its rest angle; it then **tips** about that point onto its resting side
  (rotation about a fixed contact under gravity, the impact’s angular momentum
  carried over), **bounces** a little (`bounce`, a coefficient of
  restitution) and comes to rest. A flat landing bounces straight up instead.
  Nothing eases into its rest pose: the old release’s smooth-step rotation was
  what made a dropped musket read as floating.
- **A pivot fall** ([`pivot_fall()`](#an.stage.rigid.pivot_fall)): a body turning about a fixed contact
  point under gravity from an angular velocity, until a `stop` function of
  its turn says it hit something (the floor, another body, a target).

Pure functions over points; no stage types. The item is a cloud of points
(its ink) about its centre of mass, at a reference pose; a pose is
`(cx, cy, turn)` with `turn` the rotation from that reference.

```pycon
>>> rod = [(-50.0, 0.0), (50.0, 0.0)]
>>> round(inertia(rod), 1)    # a uniform rod of length 100: L**2 / 12
833.3
```

### Module Attributes

| [`DFLT_BOUNCE`](#an.stage.rigid.DFLT_BOUNCE)   | the share of its speed it keeps when it bounces (a clatter, not a rubber ball).   |
|----------------------------------------------------------------|-----------------------------------------------------------------------------------|

### Functions

| [`stable_angles`](#an.stage.rigid.stable_angles)(points)                         | The angles a rigid drawing can lie at on a floor: each side of its ink's convex hull turned to be the bottom, where its centre (the origin of `points`) stands over that side with at least `LIE_MIN` to tip before it falls off.                                                                    |
|------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`drop_track`](#an.stage.rigid.drop_track)(points, \*\*kw)                    | The motion of a rigid item let go (`_drop_once()` has the parameters); a toss `toss_x` is aimed so that the item comes to REST, after the tip onto its side, centred on that `x`.                                                                                                                    |
| [`inertia`](#an.stage.rigid.inertia)(points)                               | Moment of inertia per unit mass about the centre (px²), from ink points on the drawing's outline: a third of their mean squared distance (a uniform rod's `L²/12`, a square's `a²/6`).                                                                                                               |
| [`pivot_fall`](#an.stage.rigid.pivot_fall)(centre, pivot, \*, gravity[, ...]) | A body whose centre is at `centre` turning about `pivot` under `gravity` (px/s², down), from angular velocity `omega` (rad/s, clockwise positive), until `stop(turn)` changes sign from positive (the gap to whatever it hits; the crossing is found to a fraction of a step) or `cap` seconds pass. |

### Classes

| [`DropTrack`](#an.stage.rigid.DropTrack)(touch, rest, bounces, angle, ...)   | A let-go item's motion from the instant it is let go (`t = 0`): `pose()` gives `(cx, cy, angle, scale_x, scale_y)` at any `t`.                                                                                 |
|------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`PivotFall`](#an.stage.rigid.PivotFall)(pivot, centre0, times, turns, ...)  | A body turning about a fixed `pivot`: `turn(t)` and `centre(t)` for `t` from 0 to `duration`; `omega_end` is its angular velocity when it stopped, `stopped` whether `stop` said so (else the cap or the end). |

### an.stage.rigid.DFLT_BOUNCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.15*

the share of its
speed it keeps when it bounces (a clatter, not a rubber ball).

* **Type:**
  Coefficient of restitution of a let-go item on the floor

### *class* an.stage.rigid.DropTrack(touch, rest, bounces, angle, floor, \_phases, \_scale)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A let-go item’s motion from the instant it is let go (`t = 0`):
[`pose()`](#an.stage.rigid.DropTrack.pose) gives `(cx, cy, angle, scale_x, scale_y)` at any `t`.

`touch` is when it first touches the floor, `rest` when it stops
moving, `bounces` when each bounce lands (all seconds from the let-go);
`floor` the line it comes to rest on.

#### angle *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The angle it comes to rest at.

#### floor *: [float](https://docs.python.org/3/builtins/functions.html#float)*

`ground`, or the line its lowest point was
already on (below `ground`) when it was let go touching the floor.

* **Type:**
  The floor line it lies on

#### pose(t)

`(cx, cy, angle, scale_x, scale_y)` `t` s after the let-go.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### *class* an.stage.rigid.PivotFall(pivot, centre0, times, turns, duration, omega_end, stopped)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A body turning about a fixed `pivot`: `turn(t)` and `centre(t)`
for `t` from 0 to `duration`; `omega_end` is its angular velocity when
it stopped, `stopped` whether `stop` said so (else the cap or the end).

#### centre(t)

Where the centre is `t` s into the fall.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

#### turn(t)

The turn `t` s into the fall (linear between steps).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.stage.rigid.drop_track(points, \*\*kw)

The motion of a rigid item let go (`_drop_once()` has the
parameters); a toss `toss_x` is aimed so that the item comes to REST,
after the tip onto its side, centred on that `x`.

```pycon
>>> rod = [(-50.0, 0.0), (50.0, 0.0), (-50.0, 4.0), (50.0, 4.0)]
>>> tr = drop_track(rod, centre=(0.0, 0.0), velocity=(0.0, 0.0), angle=0.6,
...                 rest_angle=0.0, ground=200.0, gravity=980.0, toss_x=120.0, arc=30.0)
>>> round(tr.pose(tr.rest)[0], 3)
120.0
```

* **Return type:**
  [`DropTrack`](#an.stage.rigid.DropTrack)

### an.stage.rigid.inertia(points)

Moment of inertia per unit mass about the centre (px²), from ink points
on the drawing’s outline: a third of their mean squared distance (a uniform
rod’s `L²/12`, a square’s `a²/6`).

```pycon
>>> round(inertia([(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]), 3)  # a 2x2 square
0.667
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.stage.rigid.pivot_fall(centre, pivot, , gravity, omega=0.0, inertia_cm=1.0, stop=None, cap=4.0)

A body whose centre is at `centre` turning about `pivot` under
`gravity` (px/s², down), from angular velocity `omega` (rad/s,
clockwise positive), until `stop(turn)` changes sign from positive (the
gap to whatever it hits; the crossing is found to a fraction of a step) or
`cap` seconds pass.

The equation is the rigid pendulum’s, inverted: `I_p θ'' = g r_x` with
`r` from the pivot to the centre and `I_p = I_cm + |r|²`.

```pycon
>>> f = pivot_fall((0.0, -100.0), (0.0, 0.0), gravity=980.0, omega=0.5,
...                inertia_cm=833.3, stop=lambda a: math.pi / 2 - a)
>>> f.stopped, round(f.turn(f.duration), 3), 0.8 < f.duration < 1.2
(True, 1.571, True)
```

* **Return type:**
  [`PivotFall`](#an.stage.rigid.PivotFall)

### an.stage.rigid.stable_angles(points)

The angles a rigid drawing can lie at on a floor: each side of its ink’s
convex hull turned to be the bottom, where its centre (the origin of
`points`) stands over that side with at least `LIE_MIN` to tip
before it falls off. Radians in `(-pi, pi]`.

```pycon
>>> sorted(round(a, 3) for a in stable_angles([(-50.0, -2.0), (50.0, -2.0), (50.0, 2.0), (-50.0, 2.0)]))
[0.0, 3.142]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]
