# an.kinematics.joints

Joints: declared relations between two bodies, or a body and the world.

Every joint names its points as [`Point`](an.kinematics.bodies.html.md#an.kinematics.bodies.Point)s and
carries `joined` (the caller’s time dimension: an unjoined joint is kept in
the list, so its index is stable, and simply not enforced) and `compliance`
(0 is rigid; a positive value is a softness in units of distance per unit of
force, which XPBD keeps independent of the iteration count).

- [`Pin`](#an.kinematics.joints.Pin): two points coincide; the bodies turn freely about them.
- [`Hinge`](#an.kinematics.joints.Hinge): a pin plus a range for the relative angle, about the
  relative angle the bodies have on the solve’s input (or the first frame
  of a run), or an explicit `rest`.
- [`Weld`](#an.kinematics.joints.Weld): a pin plus a fixed relative angle.
- [`Distance`](#an.kinematics.joints.Distance): the two points keep a length: `equal` (a rod),
  `at_most` (a rope or string: slack is free), `at_least` (a spacer).
- [`Slide`](#an.kinematics.joints.Slide): a point stays on a segment of another body (a groove).
- [`Contact`](#an.kinematics.joints.Contact): a point stays on the free side of a segment, or on it
  (a foot on the ground, a lamp on a table); one-sided, and only over the
  segment’s own extent, so a body slides off an edge.

A segment’s free side: with the segment running from `start` to `end`,
the free side is the one a y-down screen shows ABOVE a left-to-right
segment (normal `(ty, -tx)`).

```pycon
>>> Distance(Point("a", 0.5, 0.5), Point("b", 0.5, 0.5), length=10.0).mode
'equal'
```

### Module Attributes

| [`DistanceMode`](#an.kinematics.joints.DistanceMode)   | The ways a [`Distance`](#an.kinematics.joints.Distance) joint may hold its length.   |
|-----------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| [`Joint`](#an.kinematics.joints.Joint)          | Every joint kind, in the order the module documents them.                                         |

### Classes

| [`Contact`](#an.kinematics.joints.Contact)(point, start, end[, compliance, joined])   | `point` stays on the free side of the segment `start`–`end`, or on it; nothing holds it there (it may lift off), and nothing holds it beyond the segment's ends (it may fall off an edge).                                                                              |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Distance`](#an.kinematics.joints.Distance)(a, b, length[, mode, compliance, ...])    | The two points keep `length` apart: exactly, at most, or at least.                                                                                                                                                                                                      |
| [`Force`](#an.kinematics.joints.Force)(point[, vector, toward, strength])           | A driver that is not a target: a constant `vector` (force per unit mass, applied at `point`, so an off-centre push also turns the body), or a pull of `point` `toward` a position with `strength` (a compliant zero-length rope: `compliance = 1 / strength`), or both. |
| [`Hinge`](#an.kinematics.joints.Hinge)(a, b[, limits, rest, compliance, joined])    | A pin with a range for the angle of `b`'s body relative to `a`'s.                                                                                                                                                                                                       |
| [`Pin`](#an.kinematics.joints.Pin)(a, b[, compliance, joined])                    | Two points coincide; free rotation about them.                                                                                                                                                                                                                          |
| [`Slide`](#an.kinematics.joints.Slide)(point, start, end[, compliance, joined])     | `point` stays on the segment `start`–`end` (both on one other body, or the world), within its ends.                                                                                                                                                                     |
| [`Weld`](#an.kinematics.joints.Weld)(a, b[, rest, compliance, joined])             | A pin plus a fixed relative angle (`rest`, or the starting one).                                                                                                                                                                                                        |

### *class* an.kinematics.joints.Contact(point, start, end, compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`point` stays on the free side of the segment `start`–`end`, or
on it; nothing holds it there (it may lift off), and nothing holds it
beyond the segment’s ends (it may fall off an edge).

```pycon
>>> Contact(Point("lamp", 0.5, 1.0), Point("table", 0.0, 0.0), Point("table", 1.0, 0.0)).joined
True
```

### *class* an.kinematics.joints.Distance(a, b, length, mode='equal', compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The two points keep `length` apart: exactly, at most, or at least.

```pycon
>>> Distance(Point("hand", 0.5, 0.5), Point("world", 0.0, -200.0), length=150.0, mode="at_most").mode
'at_most'
```

### an.kinematics.joints.DistanceMode

The ways a [`Distance`](#an.kinematics.joints.Distance) joint may hold its length.

alias of [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[‘equal’, ‘at_most’, ‘at_least’]

### *class* an.kinematics.joints.Force(point, vector=None, toward=None, strength=1.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A driver that is not a target: a constant `vector` (force per unit
mass, applied at `point`, so an off-centre push also turns the body), or
a pull of `point` `toward` a position with `strength` (a compliant
zero-length rope: `compliance = 1 / strength`), or both.

```pycon
>>> Force(Point("kite", 0.5, 0.0), vector=(30.0, 0.0)).toward is None
True
```

### *class* an.kinematics.joints.Hinge(a, b, limits=None, rest=None, compliance=0.0, joined=True)

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

### an.kinematics.joints.Joint *= an.kinematics.joints.Pin | an.kinematics.joints.Hinge | an.kinematics.joints.Weld | an.kinematics.joints.Distance | an.kinematics.joints.Slide | an.kinematics.joints.Contact*

Every joint kind, in the order the module documents them.

### *class* an.kinematics.joints.Pin(a, b, compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Two points coincide; free rotation about them.

```pycon
>>> Pin(Point("arm", 0.0, 0.5), Point("torso", 1.0, 0.2)).joined
True
```

### *class* an.kinematics.joints.Slide(point, start, end, compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`point` stays on the segment `start`–`end` (both on one other
body, or the world), within its ends.

```pycon
>>> Slide(Point("bead", 0.5, 0.5), Point("world", 0.0, 0.0), Point("world", 100.0, 0.0)).joined
True
```

### *class* an.kinematics.joints.Weld(a, b, rest=None, compliance=0.0, joined=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A pin plus a fixed relative angle (`rest`, or the starting one).

```pycon
>>> Weld(Point("hat", 0.5, 1.0), Point("head", 0.5, 0.0)).rest is None
True
```
