# an.impacts.objects

The things that strike: a stick and a ball, as ordinary `an` props.

An [`ImpactObject`](#an.impacts.objects.ImpactObject) is data: the prop to draw, where it stands, the ONE
property the stroke animates and the affine map from stroke height `h` to
that property’s value, and the named keypoints a tracker would report. Being
affine is the whole contract — it is what lets [`an.impacts.stroke`](an.impacts.stroke.md#module-an.impacts.stroke) reason
in `h` while the renderer tweens the property, with no approximation between
them.

The objects are real props (an#108), stored in a real props store and drawn by
the real cutout rig builder, so the harness exercises the same path an
animation does. Their art is generated here as plain SVG, sized so the rig’s
view-box factor is exactly 1 (`view_box` height = the compiler’s
`SCENE_PX_PER_VIEW_BOX`): one SVG pixel is one scene pixel, and a keypoint’s
local coordinates are read straight off the drawing.

Coordinates are scene pixels relative to the canvas centre, `y` down — the
space `StagePlacement.at` and the camera use. Rotation is in radians,
clockwise-positive on screen, as PixiJS applies it.

```pycon
>>> s = stick()
>>> s.pose(0.0) == {("stick", "rotation"): 0.35}
True
>>> (ch,) = s.channels
>>> round(ch.value(1.0) - ch.value(0.0), 6) == -ch.stroke_extent
True
>>> list(ball().pose(1.0))
[('ball', 'y')]
```

### Module Attributes

| [`IMPACT_OBJECTS`](#an.impacts.objects.IMPACT_OBJECTS)   | Name -> factory.   |
|-------------------------------------------------------------------|--------------------|

### Functions

| [`ball`](#an.impacts.objects.ball)(\*[, radius, x, floor_y, drop, color, ...])   | A ball moving vertically onto a floor whose top is at `floor_y`.   |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| [`impact_object`](#an.impacts.objects.impact_object)(name, \*\*kwargs)                    | Build a registered object by name.                                 |
| [`stick`](#an.impacts.objects.stick)(\*[, length, thickness, pivot, ...])         | A drumstick rotating about `pivot` (its butt — the hand).          |

### Classes

| [`ImpactObject`](#an.impacts.objects.ImpactObject)(name, art, at, channels, ...[, ...])   | One striking object, its surface, and how the stroke moves it.        |
|------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`PropArt`](#an.impacts.objects.PropArt)(ref, descriptor, parts)                     | A prop's descriptor and its SVG parts — what goes into a props store. |
| [`StrokeChannel`](#an.impacts.objects.StrokeChannel)(target, property, ...)                | One animated property, AFFINE in stroke height `h`.                   |

### an.impacts.objects.IMPACT_OBJECTS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[...], [ImpactObject](#an.impacts.objects.ImpactObject)]]* *= {'ball': <function ball>, 'stick': <function stick>}*

Name -> factory. The registry the clip spec and the CLI resolve names through.

### *class* an.impacts.objects.ImpactObject(name, art, at, channels, keypoints, impact_keypoint, keypoint_nodes=<factory>, surface_art=None, surface_at=None, params=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One striking object, its surface, and how the stroke moves it.

`channels` are the properties the stroke drives — one for a stick or a
ball, two for a forearm-plus-stick limb (each affine in the SAME `h`, so
the motion stays exact). `keypoints` are local points by name; each lives
on the node `keypoint_nodes[name]` names, the entity itself by default.

#### impact_keypoint *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The keypoint that does the striking (a stick’s tip, a ball’s bottom).

#### keypoints *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]]*

Local points by name. What a tracker would report.

#### pose(h)

`{(node path, property): value}` at stroke height `h`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

#### surface_at *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where the surface’s top edge is centred, in scene coordinates.

### *class* an.impacts.objects.PropArt(ref, descriptor, parts)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A prop’s descriptor and its SVG parts — what goes into a props store.

### *class* an.impacts.objects.StrokeChannel(target, property, contact_value, stroke_extent)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One animated property, AFFINE in stroke height `h`.

`value(h) = contact_value - stroke_extent * h`: `h = 0` is contact and
`stroke_extent` is how far a full stroke moves the property away from it
(radians, or pixels). Affine is the whole contract — it is what makes an
eased tween of the property exactly the same easing of `h`.

### an.impacts.objects.ball(, radius=18.0, x=0.0, floor_y=90.0, drop=170.0, color='#111827', surface_color='#9ca3af', surface_size=(160.0, 24.0))

A ball moving vertically onto a floor whose top is at `floor_y`.

A full stroke lifts it `drop` pixels. Keypoints: `center` and
`bottom` (its contact point).

* **Return type:**
  [`ImpactObject`](#an.impacts.objects.ImpactObject)

### an.impacts.objects.impact_object(name, \*\*kwargs)

Build a registered object by name.

* **Return type:**
  [`ImpactObject`](#an.impacts.objects.ImpactObject)

```pycon
>>> impact_object("ball").name
'ball'
>>> impact_object("hammer")
Traceback (most recent call last):
  ...
KeyError: "no impact object 'hammer'; known: ['ball', 'stick']"
```

### an.impacts.objects.stick(, length=200.0, thickness=12.0, pivot=(-120.0, -30.0), contact_angle=0.35, swing=0.95, color='#111827', surface_color='#9ca3af', surface_size=(140.0, 24.0))

A drumstick rotating about `pivot` (its butt — the hand).

At contact it points `contact_angle` radians below horizontal; a full
stroke raises it by `swing` radians. Keypoints: `pivot` and `tip`
(the end of its axis). The surface’s top meets the lowest point of its
rounded end.

* **Return type:**
  [`ImpactObject`](#an.impacts.objects.ImpactObject)
