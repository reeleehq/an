# an.kinematics.bodies

Bodies and the points on them: the things a joint joins and a driver moves.

A [`Body`](#an.kinematics.bodies.Body) is a rigid rectangle of `width` by `height` (its *extent*)
posed in one frame by `(x, y, rotation, scale)`: the pose point is the
body’s `origin`, a fraction of the extent (`(0.5, 0.5)` is the centre,
`(0.5, 0.0)` the middle of the top edge: where a hanging part is hinged). A
[`Point`](#an.kinematics.bodies.Point) on a body is likewise a fraction `(u, v)` of the extent, so a
caller that knows its landmarks (a bone, a grip, a corner) resolves them to
fractions once and the solver never learns their names. The world is the body
named [`WORLD`](#an.kinematics.bodies.WORLD): a point on it is an absolute position.

Nothing here imports the scene IR or the stage: a body is four numbers and an
extent, which is what lets this package be described without naming an
animation (`# extraction candidate`: it becomes its own package when a
second consumer exists).

```pycon
>>> arm = Body("arm", x=10.0, y=20.0, width=60.0, height=10.0, origin=(0.0, 0.5))
>>> point_world(arm, Point("arm", 1.0, 0.5))   # the far end of an unrotated arm
(70.0, 20.0)
>>> point_world(arm, Point(WORLD, 3.0, 4.0))   # a world point is itself
(3.0, 4.0)
```

### Module Attributes

| [`WORLD`](#an.kinematics.bodies.WORLD)        | a [`Point`](#an.kinematics.bodies.Point) on it is an absolute position, and it has infinite mass (a joint to it is a joint to the ground).   |
|---------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_DENSITY`](#an.kinematics.bodies.DFLT_DENSITY) | mass = density × area.                                                                                                                                       |
| [`DFLT_ORIGIN`](#an.kinematics.bodies.DFLT_ORIGIN)  | the centre of its extent.                                                                                                                                    |

### Functions

| [`inertia`](#an.kinematics.bodies.inertia)(body)             | Rotational inertia about the body's pose point (parallel-axis from the extent's centre); `inf` for a fixed body.                                                             |
|----------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`local_offset`](#an.kinematics.bodies.local_offset)(body, point) | The point's offset from the body's pose point, in the body's own (unrotated) frame, scaled.                                                                                  |
| [`mass`](#an.kinematics.bodies.mass)(body)                | The body's mass: density × scaled area; `inf` for a fixed body.                                                                                                              |
| [`point_world`](#an.kinematics.bodies.point_world)(body, point)  | The point's position in the body's frame of reference (the world, for a body posed in it); a [`WORLD`](#an.kinematics.bodies.WORLD) point is returned as is. |

### Classes

| [`Body`](#an.kinematics.bodies.Body)(name[, x, y, rotation, scale, width, ...])   | A rigid rectangle posed in one frame.                  |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------|
| [`Point`](#an.kinematics.bodies.Point)(body, u, v)                                 | A point on a body, as a fraction of the body's extent. |

### *class* an.kinematics.bodies.Body(name, x=0.0, y=0.0, rotation=0.0, scale=1.0, width=1.0, height=1.0, origin=(0.5, 0.5), fixed=False, density=1.0, vx=0.0, vy=0.0, omega=0.0)

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
  [`Body`](#an.kinematics.bodies.Body)

### an.kinematics.bodies.DFLT_DENSITY *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1.0*

mass = density × area. Only the
RATIO of masses matters to a solve (a heavy prop drags a light arm), so one
unit per square unit of extent is the natural default.

* **Type:**
  Density of a body whose caller gave none

### an.kinematics.bodies.DFLT_ORIGIN *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= (0.5, 0.5)*

the centre of its extent.

* **Type:**
  Where a body’s pose point sits by default

### *class* an.kinematics.bodies.Point(body, u, v)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A point on a body, as a fraction of the body’s extent.

On [`WORLD`](#an.kinematics.bodies.WORLD) the fraction is an absolute position instead.

```pycon
>>> Point("hand", 0.5, 1.0).body
'hand'
```

### an.kinematics.bodies.WORLD *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'world'*

a [`Point`](#an.kinematics.bodies.Point) on it is an absolute position,
and it has infinite mass (a joint to it is a joint to the ground).

* **Type:**
  The name of the world body

### an.kinematics.bodies.inertia(body)

Rotational inertia about the body’s pose point (parallel-axis from the
extent’s centre); `inf` for a fixed body.

```pycon
>>> round(inertia(Body("b", width=4.0, height=2.0, origin=(0.0, 0.5))), 3)
45.333
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.kinematics.bodies.local_offset(body, point)

The point’s offset from the body’s pose point, in the body’s own
(unrotated) frame, scaled.

```pycon
>>> local_offset(Body("b", width=10.0, height=4.0), Point("b", 1.0, 0.0))
(5.0, -2.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.kinematics.bodies.mass(body)

The body’s mass: density × scaled area; `inf` for a fixed body.

```pycon
>>> mass(Body("b", width=3.0, height=2.0, scale=2.0))
24.0
>>> mass(Body("b", fixed=True))
inf
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.kinematics.bodies.point_world(body, point)

The point’s position in the body’s frame of reference (the world, for
a body posed in it); a [`WORLD`](#an.kinematics.bodies.WORLD) point is returned as is.

```pycon
>>> b = Body("b", x=1.0, y=1.0, rotation=math.pi / 2, width=2.0, height=2.0)
>>> tuple(round(c, 9) for c in point_world(b, Point("b", 1.0, 0.5)))
(1.0, 2.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]
