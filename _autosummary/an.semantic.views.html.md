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
[`an.capabilities.subjects`](an.capabilities.subjects.html.md#module-an.capabilities.subjects)). The core declares two spaces; a genre or a
package declares more (an n-dimensional one) with [`view_space()`](#an.semantic.views.view_space), and
registers moves over them into the same `camera_move` table — so `push_in`
means one thing everywhere, and `burns`’ moves and `previz`’s camera
formulas join it instead of redefining it.

```pycon
>>> FRAMING_2D.entry.id, FRAMING_2D.capability.name, FRAMING_2D.entry.params["properties"]["zoom"]["scale"]
('view.framing2d', 'space.framing2d', 'log')
```

### Module Attributes

| [`MULTIPLANE`](#an.semantic.views.MULTIPLANE)   | the 2D framing plus how far the camera has travelled into a scene of planes at depths, so each plane grows by its own depth.                                                                                 |
|---------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`ORBIT_3D`](#an.semantic.views.ORBIT_3D)     | a camera on a sphere around a target (previz's turntable), one `orbit` value, version 2 (version 1 split it into radian scalars and a flattened target, which matched neither the kernel's kind nor previz). |

### Functions

| [`view_space`](#an.semantic.views.view_space)(name, fields, \*, description[, ...])   | Declare a view space: an entry `view.<name>` and an engine capability `space.<name>`.   |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|

### Classes

| [`ViewField`](#an.semantic.views.ViewField)(name, unit[, scale, rest, ...])   | One axis of a view space: its name, unit, how it interpolates, its rest value.     |
|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`ViewSpace`](#an.semantic.views.ViewSpace)(entry, capability[, fields])      | A declared view space: its vocabulary entry and the engine capability to lower it. |

### an.semantic.views.MULTIPLANE *: [ViewSpace](#an.semantic.views.ViewSpace)* *= ViewSpace(entry=Entry(id='view.multiplane', kind='view_space', version='1', name='multiplane', title='', description='a 2D framing that also travels in depth through planes (a dolly)', usage='axes: x (frame widths, linear), y (frame heights, linear), zoom (ratio, log), rotation (rad, angle), dolly (character-plane distance, linear)', params={'type': 'object', 'properties': {'x': {'type': 'number', 'unit': 'frame widths', 'scale': 'linear', 'default': 0.0, 'description': '+x moves the view right'}, 'y': {'type': 'number', 'unit': 'frame heights', 'scale': 'linear', 'default': 0.0, 'description': '+y moves the view down'}, 'zoom': {'type': 'number', 'unit': 'ratio', 'scale': 'log', 'default': 1.0, 'description': 'on-screen magnification; > 1 is closer'}, 'rotation': {'type': 'number', 'unit': 'rad', 'scale': 'angle', 'default': 0.0, 'description': "the view's roll"}, 'dolly': {'type': 'number', 'unit': 'character-plane distance', 'scale': 'linear', 'default': 0.0, 'description': 'travel toward the scene; 0.2 is a fifth of the way to the character plane'}}}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), capability=Capability(name='space.multiplane', description='the engine lowers moves through the multiplane view space: a 2D framing that also travels in depth through planes (a dolly)', remedy='render with an engine that lowers the multiplane view space', subject='engine', command=None, version='1'), fields=(ViewField(name='x', unit='frame widths', scale='linear', rest=0.0, description='+x moves the view right', kind=None), ViewField(name='y', unit='frame heights', scale='linear', rest=0.0, description='+y moves the view down', kind=None), ViewField(name='zoom', unit='ratio', scale='log', rest=1.0, description='on-screen magnification; > 1 is closer', kind=None), ViewField(name='rotation', unit='rad', scale='angle', rest=0.0, description="the view's roll", kind=None), ViewField(name='dolly', unit='character-plane distance', scale='linear', rest=0.0, description='travel toward the scene; 0.2 is a fifth of the way to the character plane', kind=None)))*

the 2D framing plus how far the camera has
travelled into a scene of planes at depths, so each plane grows by its own
depth. A crop engine cannot lower it (its pixels have no depth); the stage
engine does, from its planes’ parallax factors.

* **Type:**
  The multiplane space (an#478)

### an.semantic.views.ORBIT_3D *: [ViewSpace](#an.semantic.views.ViewSpace)* *= ViewSpace(entry=Entry(id='view.orbit3d', kind='view_space', version='2', name='orbit3d', title='', description='an orbit camera around a 3D target: azimuth and elevation (angles), distance (log)', usage='axes: orbit (deg, orbit)', params={'type': 'object', 'properties': {'orbit': {'type': 'object', 'properties': {'azimuth': {'type': 'number', 'unit': 'deg', 'description': 'around the target (shortest arc)'}, 'elevation': {'type': 'number', 'unit': 'deg', 'minimum': -90.0, 'maximum': 90.0, 'description': "above the target's horizon, within the poles"}, 'distance': {'type': 'number', 'exclusiveMinimum': 0, 'unit': 'scene units', 'description': 'from the target (interpolated in log)'}, 'target': {'type': 'array', 'items': {'type': 'number'}, 'unit': 'scene units', 'description': 'what the camera looks at'}}, 'required': ['azimuth', 'elevation', 'distance'], 'kind': {'kind': 'orbit'}, 'unit': 'deg', 'default': {'azimuth': 0.0, 'elevation': 0.0, 'distance': 1.0, 'target': [0.0, 0.0, 0.0]}, 'description': 'a camera on a sphere around its target: {azimuth, elevation, distance, target?}'}}}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), capability=Capability(name='space.orbit3d', description='the engine lowers moves through the orbit3d view space: an orbit camera around a 3D target: azimuth and elevation (angles), distance (log)', remedy='render with an engine that lowers the orbit3d view space', subject='engine', command=None, version='1'), fields=(ViewField(name='orbit', unit='deg', scale='linear', rest={'azimuth': 0.0, 'elevation': 0.0, 'distance': 1.0, 'target': [0.0, 0.0, 0.0]}, description='a camera on a sphere around its target: {azimuth, elevation, distance, target?}', kind=OrbitKind(unit='deg')),))*

a camera on a sphere around a target (previz’s turntable),
one `orbit` value, version 2 (version 1 split it into radian scalars and a
flattened target, which matched neither the kernel’s kind nor previz).

* **Type:**
  The 3D orbit space

### *class* an.semantic.views.ViewField(name, unit, scale='linear', rest=0.0, description='', kind=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One axis of a view space: its name, unit, how it interpolates, its rest value.

A scalar axis says how it interpolates with `scale`; an axis whose value
is not one number (an orbit, a colour, a vector) carries its field
`kind` ([`an.timing.kinds`](an.timing.kinds.html.md#module-an.timing.kinds)) instead, built from the property
declaration it shares with an engine’s property space
([`from_decl()`](#an.semantic.views.ViewField.from_decl)), so the two are one thing (an#788).

#### decl()

This axis as a property declaration ([`an.timing.spaces.FieldDecl`](an.timing.spaces.html.md#an.timing.spaces.FieldDecl)).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### *property* field_kind *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)*

its own, else the one its
`scale` names (`linear` and `log` numbers, a shortest-arc angle).

```pycon
>>> ViewField("zoom", "ratio", "log").field_kind
NumberKind(space='log')
>>> ViewField("roll", "rad", "angle").field_kind
AngleKind(unit='rad', wrap=True)
```

* **Type:**
  The field kind that interpolates this axis

#### *classmethod* from_decl(decl, , rest)

The view field a property declaration ([`an.timing.spaces.FieldDecl`](an.timing.spaces.html.md#an.timing.spaces.FieldDecl))
makes: its name, kind, unit and description, at `rest`.

* **Return type:**
  [`ViewField`](#an.semantic.views.ViewField)

### *class* an.semantic.views.ViewSpace(entry, capability, fields=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A declared view space: its vocabulary entry and the engine capability to lower it.

#### property_space()

The space as an engine’s property space ([`an.timing.spaces.PropertySpace`](an.timing.spaces.html.md#an.timing.spaces.PropertySpace),
`view.<name>`): each axis’s declaration, the one an engine whose state
this view space moves registers (an#788).

```pycon
>>> [(d.pattern, d.kind.to_spec()) for d in ORBIT_3D.property_space().fields]
[('orbit', {'kind': 'orbit'})]
```

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.semantic.views.view_space(name, fields, , description, version='1')

Declare a view space: an entry `view.<name>` and an engine capability `space.<name>`.

Register both through a [`an.genres.Genre`](an.genres.html.md#an.genres.Genre) (`vocabulary` and
`capabilities`) or, for the core’s, directly.

* **Return type:**
  [`ViewSpace`](#an.semantic.views.ViewSpace)
