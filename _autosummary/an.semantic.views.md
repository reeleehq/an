# an.semantic.views

View spaces: what a camera move moves through, defined once for every engine (an#257).

A camera move (`push_in`, `pan_left`, an orbit) is not a crop, a zoom or a
parameter tween: it is a **path through a view space**, which each engine
lowers its own way —

- a **crop engine** (`burns`, a still or a video) moves a rectangle over
  fixed pixels, so pushing in loses resolution;
- a **render engine** (the stage engine of `an`/`cutan`, vector art)
  re-renders the scene into the rectangle, so pushing in loses nothing;
- a **parameter engine** (`previz`) moves a vector of view parameters — an
  orbit camera in 3D, a chart’s axis domain.

So the vocabulary defines each move once, over an abstract space, and an engine
affords the space it can lower (`space.framing2d` is an engine capability,
[`an.capabilities.subjects`](an.capabilities.subjects.md#module-an.capabilities.subjects)). The core declares two spaces; a genre or a
package declares more (an n-dimensional one) with [`view_space()`](#an.semantic.views.view_space), and
registers moves over them into the same `camera_move` table — so `push_in`
means one thing everywhere, and `burns`’ moves and `previz`’s camera
formulas join it instead of redefining it.

```pycon
>>> FRAMING_2D.entry.id, FRAMING_2D.capability.name, FRAMING_2D.entry.params["properties"]["zoom"]["scale"]
('view.framing2d', 'space.framing2d', 'log')
```

### Module Attributes

| [`FRAMING_2D`](#an.semantic.views.FRAMING_2D)   | where the frame is, how close, how rolled.                 |
|---------------------------------------------------------------|------------------------------------------------------------|
| [`ORBIT_3D`](#an.semantic.views.ORBIT_3D)     | a camera on a sphere around a target (previz's turntable). |

### Functions

| [`view_space`](#an.semantic.views.view_space)(name, fields, \*, description[, ...])   | Declare a view space: an entry `view.<name>` and an engine capability `space.<name>`.   |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|

### Classes

| [`ViewField`](#an.semantic.views.ViewField)(name, unit[, scale, rest, description])   | One axis of a view space: its name, unit, how it interpolates, its rest value.     |
|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`ViewSpace`](#an.semantic.views.ViewSpace)(entry, capability)                        | A declared view space: its vocabulary entry and the engine capability to lower it. |

### an.semantic.views.FRAMING_2D *: [ViewSpace](#an.semantic.views.ViewSpace)* *= ViewSpace(entry=Entry(id='view.framing2d', kind='view_space', version='1', name='framing2d', title='', description='a 2D framing of a flat picture: position, zoom (log), roll (angle)', usage='axes: x (frame widths, linear), y (frame heights, linear), zoom (ratio, log), rotation (rad, angle)', params={'type': 'object', 'properties': {'x': {'type': 'number', 'unit': 'frame widths', 'scale': 'linear', 'default': 0.0, 'description': '+x moves the view right'}, 'y': {'type': 'number', 'unit': 'frame heights', 'scale': 'linear', 'default': 0.0, 'description': '+y moves the view down'}, 'zoom': {'type': 'number', 'unit': 'ratio', 'scale': 'log', 'default': 1.0, 'description': 'on-screen magnification; > 1 is closer'}, 'rotation': {'type': 'number', 'unit': 'rad', 'scale': 'angle', 'default': 0.0, 'description': "the view's roll"}}}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), capability=Capability(name='space.framing2d', description='the engine lowers moves through the framing2d view space: a 2D framing of a flat picture: position, zoom (log), roll (angle)', remedy='render with an engine that lowers the framing2d view space', subject='engine', command=None, version='1'))*

where the frame is, how close, how rolled. Every
engine that shows a flat picture lowers it — by cropping pixels (burns) or by
re-rendering into the frame (the stage engine).

* **Type:**
  The 2D framing space

### an.semantic.views.ORBIT_3D *: [ViewSpace](#an.semantic.views.ViewSpace)* *= ViewSpace(entry=Entry(id='view.orbit3d', kind='view_space', version='1', name='orbit3d', title='', description='an orbit camera around a 3D target: azimuth and elevation (angles), distance (log)', usage='axes: azimuth (rad, angle), elevation (rad, angle), distance (scene units, log), target_x (scene units, linear), target_y (scene units, linear), target_z (scene units, linear)', params={'type': 'object', 'properties': {'azimuth': {'type': 'number', 'unit': 'rad', 'scale': 'angle', 'default': 0.0, 'description': 'around the target'}, 'elevation': {'type': 'number', 'unit': 'rad', 'scale': 'angle', 'default': 0.0, 'description': "above the target's horizon"}, 'distance': {'type': 'number', 'unit': 'scene units', 'scale': 'log', 'default': 1.0, 'description': 'from the target'}, 'target_x': {'type': 'number', 'unit': 'scene units', 'scale': 'linear', 'default': 0.0}, 'target_y': {'type': 'number', 'unit': 'scene units', 'scale': 'linear', 'default': 0.0}, 'target_z': {'type': 'number', 'unit': 'scene units', 'scale': 'linear', 'default': 0.0}}}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), capability=Capability(name='space.orbit3d', description='the engine lowers moves through the orbit3d view space: an orbit camera around a 3D target: azimuth and elevation (angles), distance (log)', remedy='render with an engine that lowers the orbit3d view space', subject='engine', command=None, version='1'))*

a camera on a sphere around a target (previz’s turntable).

* **Type:**
  The 3D orbit space

### *class* an.semantic.views.ViewField(name, unit, scale='linear', rest=0.0, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One axis of a view space: its name, unit, how it interpolates, its rest value.

### *class* an.semantic.views.ViewSpace(entry, capability)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A declared view space: its vocabulary entry and the engine capability to lower it.

### an.semantic.views.view_space(name, fields, , description, version='1')

Declare a view space: an entry `view.<name>` and an engine capability `space.<name>`.

Register both through a [`an.genres.Genre`](an.genres.md#an.genres.Genre) (`vocabulary` and
`capabilities`) or, for the core’s, directly.

* **Return type:**
  [`ViewSpace`](#an.semantic.views.ViewSpace)
