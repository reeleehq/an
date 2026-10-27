# an.ir.frames

Frames of reference: a tree of named poses over film time (ADR 0009 amendment, an#501).

A **frame** is a rigid pose (a position and an orientation) as a function of
film time, relative to a parent frame; `world` is the root. Every element of
the scene’s world (a member, a viewpoint, a stream, a plane) is in exactly one
frame, with a local pose in that frame’s units. Its world pose is the
composition of the poses up the chain, and what a viewpoint sees is the
pinhole projection of world poses into the viewpoint’s own frame (the
projection itself is [`an.ir.world.Projection`](an.ir.world.html.md#an.ir.world.Projection)). The multiplane camera,
the moving panorama, the process shot and the camera rig are all the same
tree with a different shape: what stands still in one frame is scenery in
another, and the eye is attached to whichever frame the shot is in.

Orientation uses the viewpoint’s convention: `look: [yaw, pitch, roll]`
degrees, the frame’s local axes being `(right, down, forward)` — so a frame
with `look` zero is the world’s axes (`x` right, `y` DOWN, `z` away
from the viewer).

A **far** frame follows its parent’s rotation and none of its translation: what
is at infinity turns with the camera and never moves with it.

This module is pure geometry on tuples; it imports the schema’s `Frame`
and the easing function, nothing else. It is an extraction candidate: previz
(an#257) is the TypeScript twin of the same vocabulary.

```pycon
>>> from an.ir.schema import Frame, FrameMoving
>>> tree = FrameTree({
...     "car": Frame(moving=FrameMoving(speed=20.0)),
...     "seat": Frame(parent="car", at=(0.45, 0.65, 1.6)),
...     "horizon": Frame(parent="car", coupling="far"),
... })
>>> tree.world_pose("seat", 2.0).at          # 2 s on: the seat is 40 m down the road
(0.45, 0.65, 41.6)
>>> tree.world_pose("horizon", 2.0).at       # at infinity: never translates
(0.0, 0.0, 0.0)
```

### Module Attributes

| [`Axes`](#an.ir.frames.Axes)             | a frame's local axes in its parent's coordinates.                                                                                              |
|-------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| [`FRAME_PROPERTIES`](#an.ir.frames.FRAME_PROPERTIES) | The channels of a frame an ordinary `set`/`tween` may target (`<frame>:at_x`): its position in its parent's units, its orientation in degrees. |

### Functions

| [`lag_filter`](#an.ir.frames.lag_filter)(values, \*, lag, dt)   | `values` seen through a first-order filter of time constant `lag` (s), sampled every `dt`: it starts on the first value and closes `1 - exp(-dt/lag)` of the gap each step (Cinemachine's damping: the time it takes to catch up).   |
|------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`look_basis`](#an.ir.frames.look_basis)(yaw, pitch, roll)      | `(forward, right, down)` for a look of `yaw` (turn right), `pitch` (look down) and `roll` (the PICTURE turns clockwise: what was on the right moves to the bottom), in degrees.                                                      |

### Classes

| [`FrameTree`](#an.ir.frames.FrameTree)(frames, \*[, tracks])             | The frames of a scene and the world pose of anything in one of them.                                                                                                                                                                                |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Pose`](#an.ir.frames.Pose)([at, axes])                            | A rigid pose: where a frame's origin is (`at`) and how its axes lie (`axes`, `None` for the parent's), both in the parent's coordinates.                                                                                                            |
| [`Track`](#an.ir.frames.Track)(events)                               | The `set`/`tween` actions on one channel of a frame, as a function of shot time: it holds the base value until the first event, a set steps, a tween ramps from its `from_` (the value the channel has when it starts, if unset) and holds its end. |
| [`TrackEvent`](#an.ir.frames.TrackEvent)(start, end, to[, from_, easing]) | One `set` (`start == end`) or `tween` of a channel, in shot time.                                                                                                                                                                                   |

### Exceptions

| [`FrameError`](#an.ir.frames.FrameError)   | A frame tree that cannot be built or evaluated (an unknown frame).   |
|---------------------------------------------------------------|----------------------------------------------------------------------|

### an.ir.frames.Axes

a frame’s local axes in its parent’s coordinates.

* **Type:**
  `(right, down, forward)`

alias of [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.ir.frames.FRAME_PROPERTIES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('at_x', 'at_y', 'at_z', 'yaw', 'pitch', 'roll')*

The channels of a frame an ordinary `set`/`tween` may target
(`<frame>:at_x`): its position in its parent’s units, its orientation in
degrees.

### *exception* an.ir.frames.FrameError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A frame tree that cannot be built or evaluated (an unknown frame).

### *class* an.ir.frames.FrameTree(frames, , tracks=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The frames of a scene and the world pose of anything in one of them.

`tracks` are the shot’s `set`/`tween` actions on frame channels
(`{frame: {channel: Track}}`, shot time): a track REPLACES the channel’s
declared value for that shot, the way a pose value replaces a property.
`moving` adds `direction × speed × film time` to the position on top.
Poses are evaluated at a shot time `t` with `film_start` the shot’s
start in the film, so a moving frame keeps its phase across a cut.

```pycon
>>> from an.ir.schema import Frame, FrameMoving
>>> tree = FrameTree({"car": Frame(moving=FrameMoving(speed=10.0))})
>>> tree.world_pose("car", 1.0, film_start=4.0).at
(0.0, 0.0, 50.0)
>>> tree.relative_pose("world", "car", 1.0).at        # the world seen from the car: it comes at us
(0.0, 0.0, -10.0)
>>> FrameTree({"a": Frame(parent="b"), "b": Frame(parent="a")})
Traceback (most recent call last):
...
an.ir.frames.FrameError: frames form a cycle through 'a'
```

#### acceleration(name, t, , film_start=0.0, dt=0.01, within=None)

The world acceleration of `name`’s origin at shot time `t`
(second difference of step `dt`, units/s²): zero for a frame at rest
or at a constant speed.

`within=(lo, hi)` keeps the three samples inside that window (a
shot): near an end the stencil slides inward (a one-sided difference),
and a window narrower than `2·dt` shrinks the step to half of it, so
a motion that starts at the window’s edge is not read as an impulse.

```pycon
>>> from an.ir.schema import Frame, FrameMoving
>>> tree = FrameTree({"car": Frame(moving=FrameMoving(speed=20.0))})
>>> [round(v, 3) + 0.0 for v in tree.acceleration("car", 1.0)]
[0.0, 0.0, 0.0]
>>> track = Track([TrackEvent(0.0, 1.0, to=10.0, from_=0.0, easing="ease_out")])
>>> braking = FrameTree({"car": Frame()}, tracks={"car": {"at_z": track}})
>>> [round(v, 1) + 0.0 for v in braking.acceleration("car", 0.5)]   # 20 m/s to 0 in a second
[0.0, 0.0, -20.0]
>>> [round(v, 1) + 0.0 for v in braking.acceleration("car", 0.0, dt=0.04, within=(0.0, 1.0))]
[0.0, 0.0, -20.0]
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

#### chain(name)

The frames from `name` up to (not including) the world, root first.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### constant_motion(name)

`(unit direction, speed)` when `name` is a frame of the world
that does nothing but translate at a constant velocity from the origin
(a `vehicle`), else `None`: the case a straight travel’s streams are
solved for in closed form.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### is_static(name, to, duration, , film_start=0.0, samples=33)

Whether `name` stands still in `to` through a shot of `duration`
seconds: the same frame, two frames that move together, or two still
ones. Sampled (and at every action’s start and end), exactly equal
within `_SAME_POSE_EPS`.

```pycon
>>> from an.ir.schema import Frame, FrameMoving
>>> tree = FrameTree({"car": Frame(moving=FrameMoving(speed=5.0)), "seat": Frame(parent="car", at=(1.0, 0.0, 0.0))})
>>> tree.is_static("seat", "car", 2.0), tree.is_static("world", "car", 2.0)
(True, False)
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### is_still(name)

Whether `name` and every frame above it are fixed for any shot:
nothing moves them and no action animates them.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### local_pose(name, t, , film_start=0.0)

`name`’s pose in its parent’s units at shot time `t`.

* **Return type:**
  [`Pose`](#an.ir.frames.Pose)

#### relative_pose(name, to, t, , film_start=0.0)

`name`’s pose expressed in `to`’s coordinates: what takes a point
in `name` to the same point in `to`.

* **Return type:**
  [`Pose`](#an.ir.frames.Pose)

#### sway_frame(name)

The frame whose `sway` governs what is in `name`: the nearest one
up the chain that declares it, else `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### world_pose(name, t, , film_start=0.0)

`name`’s pose in the world at shot time `t`: the poses up the
chain composed; a `far` edge keeps its parent’s rotation and none of
its translation.

* **Return type:**
  [`Pose`](#an.ir.frames.Pose)

### *class* an.ir.frames.Pose(at=(0.0, 0.0, 0.0), axes=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A rigid pose: where a frame’s origin is (`at`) and how its axes lie
(`axes`, `None` for the parent’s), both in the parent’s coordinates.

```pycon
>>> Pose(at=(1.0, 0.0, 0.0)).apply((0.0, 0.0, 5.0))
(1.0, 0.0, 5.0)
>>> turned = Pose(axes=_axes(90.0, 0.0, 0.0))     # turned right by 90 degrees
>>> [round(v, 6) + 0.0 for v in turned.apply((0.0, 0.0, 1.0))]
[1.0, 0.0, 0.0]
>>> [round(v, 6) + 0.0 for v in turned.unapply(turned.apply((2.0, 3.0, 4.0)))]
[2.0, 3.0, 4.0]
```

#### apply(p)

A point in this frame’s units, in the parent’s.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

#### compose(child)

`self ∘ child`: the child’s pose seen from this pose’s parent.

```pycon
>>> Pose(at=(10.0, 0.0, 0.0)).compose(Pose(at=(1.0, 0.0, 0.0))).at
(11.0, 0.0, 0.0)
```

* **Return type:**
  [`Pose`](#an.ir.frames.Pose)

#### inverse()

The pose that undoes this one.

* **Return type:**
  [`Pose`](#an.ir.frames.Pose)

#### rotate(v)

A direction in this frame’s axes, in the parent’s.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

#### same_as(other)

Equal within `_SAME_POSE_EPS` (position and axes).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### unapply(p)

The inverse of [`apply()`](#an.ir.frames.Pose.apply).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### *class* an.ir.frames.Track(events)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The `set`/`tween` actions on one channel of a frame, as a function
of shot time: it holds the base value until the first event, a set steps,
a tween ramps from its `from_` (the value the channel has when it starts,
if unset) and holds its end.

```pycon
>>> track = Track([TrackEvent(1.0, 3.0, to=10.0, easing=None)])
>>> track.value(0.0, 4.0), track.value(2.0, 4.0), track.value(5.0, 4.0)
(4.0, 7.0, 10.0)
```

#### *property* breaks *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), ...]*

every event’s start and end.

* **Type:**
  Where the channel’s behaviour changes

### *class* an.ir.frames.TrackEvent(start, end, to, from_=None, easing=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One `set` (`start == end`) or `tween` of a channel, in shot time.

### an.ir.frames.lag_filter(values, , lag, dt)

`values` seen through a first-order filter of time constant `lag`
(s), sampled every `dt`: it starts on the first value and closes
`1 - exp(-dt/lag)` of the gap each step (Cinemachine’s damping: the time
it takes to catch up). `lag <= 0` returns them as they are.

```pycon
>>> out = lag_filter([0.0] + [100.0] * 30, lag=0.5, dt=0.1)
>>> round(out[5], 1)                  # 0.5 s after the step: 1 - 1/e of it
63.2
>>> lag_filter([0.0, 1.0], lag=0.5, dt=0.0)
Traceback (most recent call last):
  ...
ValueError: lag_filter: the sample step `dt` must be positive (got 0.0).
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.ir.frames.look_basis(yaw, pitch, roll)

`(forward, right, down)` for a look of `yaw` (turn right), `pitch`
(look down) and `roll` (the PICTURE turns clockwise: what was on the
right moves to the bottom), in degrees.

```pycon
>>> [tuple(round(v, 6) + 0.0 for v in axis) for axis in look_basis(0.0, 0.0, 0.0)]
[(0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
>>> [round(v, 6) + 0.0 for v in look_basis(90.0, 0.0, 0.0)[0]]
[1.0, 0.0, 0.0]
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]
