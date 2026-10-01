# an.timing.kinds

Field kinds: the declared interpolator of each animatable property.

**The declared kind picks the interpolator; a runtime value never does.** A field
kind is what lets a number be an angle (shortest arc), a log-space zoom, or a
colour mixed in OKLab — none of which a value’s type can say. Kinds are declared
per property by a *property space* ([`an.timing.spaces`](an.timing.spaces.md#module-an.timing.spaces)); a property no space
declares is [`DiscreteKind`](#an.timing.kinds.DiscreteKind).

Seven kinds are seeded, each parametrised (the TypeScript kernel’s seven):

**Discrete is defined on TIME, never on a ratio or an eased value** (an#86). A
segment from key `a` to key `b` shows `b` iff `t >= a.time + switch_at *
(b.time - a.time)`, and `switch_at == 1` is evaluated as `t >= b.time` with
no arithmetic at all: `(t - a.time) / span` can round up to 1.0 while
`t < b.time`, and an overshooting easing would flip an eased comparison twice.

Genres add kinds with [`register_kind()`](#an.timing.kinds.register_kind) (a Manim genre’s `points`, say)
without editing this module.

```pycon
>>> NumberKind().interpolate(0.0, 10.0, 0.25, Segment(0.25, 0.0, 1.0))
2.5
>>> NumberKind(space="log").interpolate(1.0, 4.0, 0.5, Segment(0.5, 0.0, 1.0))
2.0
>>> AngleKind().interpolate(350, 10, 0.5, Segment(0.5, 0.0, 1.0))  # not re-normalised
360.0
>>> b = 9.767899248713501
>>> DiscreteKind(switch_at=1).interpolate("A", "B", 1.0, Segment(math.nextafter(b, 0), 0.15, b))
'A'
>>> kind_from_spec({"kind": "number", "space": "log"})
NumberKind(space='log')
```

### Module Attributes

| [`DEFAULT_SWITCH_AT`](#an.timing.kinds.DEFAULT_SWITCH_AT)         | Where an undeclared discrete value switches, in normalised segment time.                                          |
|----------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| [`QUATERNION_UNIT_TOLERANCE`](#an.timing.kinds.QUATERNION_UNIT_TOLERANCE) | How far a quaternion's norm may be from 1 and still count as unit length.                                         |
| [`SLERP_LINEAR_THRESHOLD`](#an.timing.kinds.SLERP_LINEAR_THRESHOLD)    | Above this <br/><br/>```<br/>|dot|<br/>```<br/><br/>, slerp falls back to normalised lerp (the arc is too short). |
| [`KindFactory`](#an.timing.kinds.KindFactory)               | its parameters as keyword arguments -> an instance.                                                               |
| [`CORE_OWNER`](#an.timing.kinds.CORE_OWNER)                | Who registered the seeded kinds (only these reach the contract files).                                            |

### Functions

| [`kind_from_spec`](#an.timing.kinds.kind_from_spec)(spec)                               | A kind instance from its contract spec (`{"kind": name, **params}`), a bare kind name, or an instance (returned as is).   |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| [`kind_names`](#an.timing.kinds.kind_names)(\*[, owner])                            | The registered kind names in registration order; only `owner`'s when given.                                               |
| [`register_kind`](#an.timing.kinds.register_kind)(name, factory, \*[, replace, owner]) | Register a field kind under `name` (how a genre adds one).                                                                |
| [`shortest_delta`](#an.timing.kinds.shortest_delta)(a, b[, period])                     | The signed shortest turn from `a` to `b`, in `[-period/2, period/2]`.                                                     |
| [`slerp`](#an.timing.kinds.slerp)(a, b, u)                                     | Spherical interpolation of unit quaternions `[x, y, z, w]`, the short way.                                                |

### Classes

| [`AngleKind`](#an.timing.kinds.AngleKind)([unit, wrap])   | An angle: the shortest arc when `wrap`, else the raw numbers.                           |
|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`ColorKind`](#an.timing.kinds.ColorKind)([space])        | A colour (hex or `[r, g, b, a?]` in 0..1), written back in the form of the start value. |
| [`DiscreteKind`](#an.timing.kinds.DiscreteKind)([switch_at]) | Holds `a` and switches to `b` on TIME (see the module docstring).                       |
| [`FieldKind`](#an.timing.kinds.FieldKind)()               | Base of every field kind: a frozen, hashable, JSON-describable interpolator.            |
| [`NumberKind`](#an.timing.kinds.NumberKind)([space])       | A continuous scalar.                                                                    |
| [`OrbitKind`](#an.timing.kinds.OrbitKind)([unit])         | A camera orbiting a target: `{azimuth, elevation, distance, target?}`.                  |
| [`QuaternionKind`](#an.timing.kinds.QuaternionKind)()          | A unit quaternion `[x, y, z, w]`, interpolated by slerp after a sign fix.               |
| [`Segment`](#an.timing.kinds.Segment)(t, start, end)    | Where an evaluation sits: time `t` inside the segment `[start, end)`.                   |
| [`VectorKind`](#an.timing.kinds.VectorKind)()              | A fixed-length list of numbers, interpolated componentwise.                             |

### Exceptions

| [`FieldKindError`](#an.timing.kinds.FieldKindError)   | A kind spec is malformed, or names no registered kind.   |
|-------------------------------------------------------------------|----------------------------------------------------------|

### *class* an.timing.kinds.AngleKind(unit='deg', wrap=True)

Bases: [`FieldKind`](#an.timing.kinds.FieldKind)

An angle: the shortest arc when `wrap`, else the raw numbers. Interpolated
angles are not re-normalised (350 -> 10 passes through 360).

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.timing.kinds.CORE_OWNER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an'*

Who registered the seeded kinds (only these reach the contract files).

### *class* an.timing.kinds.ColorKind(space='oklab')

Bases: [`FieldKind`](#an.timing.kinds.FieldKind)

A colour (hex or `[r, g, b, a?]` in 0..1), written back in the form of
the start value. `oklab` mixes perceptually with premultiplied alpha;
`srgb` lerps the encoded channels (Manim’s and the stage tint’s rule).

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.timing.kinds.DEFAULT_SWITCH_AT *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

Where an undeclared discrete value switches, in normalised segment time.

### *class* an.timing.kinds.DiscreteKind(switch_at=0.5)

Bases: [`FieldKind`](#an.timing.kinds.FieldKind)

Holds `a` and switches to `b` on TIME (see the module docstring).

`switch_at` lies in `(0, 1]`. The default, 0.5, is the switch point of an
undeclared property; a replacement drawing (a swap set) declares 1, so it
never appears before its own key.

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### switches *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[[bool](https://docs.python.org/3/builtins/functions.html#bool)]* *= True*

True when the value (or part of it) switches on TIME rather than moving.

### *class* an.timing.kinds.FieldKind

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Base of every field kind: a frozen, hashable, JSON-describable interpolator.

Subclasses set `name` and implement [`interpolate()`](#an.timing.kinds.FieldKind.interpolate); the dataclass
fields are the kind’s parameters, and `to_spec()` writes them as the
contract does (`{"kind": name, **non-default params}`).

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### switches *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[[bool](https://docs.python.org/3/builtins/functions.html#bool)]* *= False*

True when the value (or part of it) switches on TIME rather than moving.

### *exception* an.timing.kinds.FieldKindError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A kind spec is malformed, or names no registered kind.

### an.timing.kinds.KindFactory

its parameters as keyword arguments -> an instance.

* **Type:**
  A kind’s factory

alias of `Callable`[[…], [`FieldKind`](#an.timing.kinds.FieldKind)]

### *class* an.timing.kinds.NumberKind(space='linear')

Bases: [`FieldKind`](#an.timing.kinds.FieldKind)

A continuous scalar. `space="log"` interpolates the logarithm (zoom, scale).

Linear interpolation is `a + (b - a) * u` with no special case at the ends,
which is the stage runtime’s arithmetic: a declared `number` channel is
bit-identical to what `runtime.js` draws.

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### *class* an.timing.kinds.OrbitKind(unit='deg')

Bases: [`FieldKind`](#an.timing.kinds.FieldKind)

A camera orbiting a target: `{azimuth, elevation, distance, target?}`.

Azimuth takes the shortest arc, elevation is lerped and clamped to the poles,
distance is lerped in log, target componentwise. Any other member is discrete
and switches at [`DEFAULT_SWITCH_AT`](#an.timing.kinds.DEFAULT_SWITCH_AT) (on time). One value: a dotted
address never reaches inside it.

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### switches *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[[bool](https://docs.python.org/3/builtins/functions.html#bool)]* *= True*

True when the value (or part of it) switches on TIME rather than moving.

### an.timing.kinds.QUATERNION_UNIT_TOLERANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.001*

How far a quaternion’s norm may be from 1 and still count as unit length.

### *class* an.timing.kinds.QuaternionKind

Bases: [`FieldKind`](#an.timing.kinds.FieldKind)

A unit quaternion `[x, y, z, w]`, interpolated by slerp after a sign fix.

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.timing.kinds.SLERP_LINEAR_THRESHOLD *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.9995*

Above this 

```
|dot|
```

, slerp falls back to normalised lerp (the arc is too short).

### *class* an.timing.kinds.Segment(t, start, end)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Where an evaluation sits: time `t` inside the segment `[start, end)`.

#### switched(switch_at)

Whether a discrete value has switched to the segment’s second key.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> Segment(0.5, 0.0, 1.0).switched(0.5), Segment(0.49, 0.0, 1.0).switched(0.5)
(True, False)
>>> Segment(0.9999999999, 0.0, 1.0).switched(1.0)  # only at b.time itself
False
```

### *class* an.timing.kinds.VectorKind

Bases: [`FieldKind`](#an.timing.kinds.FieldKind)

A fixed-length list of numbers, interpolated componentwise.

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.timing.kinds.kind_from_spec(spec)

A kind instance from its contract spec (`{"kind": name, **params}`),
a bare kind name, or an instance (returned as is).

* **Return type:**
  [`FieldKind`](#an.timing.kinds.FieldKind)

```pycon
>>> kind_from_spec("discrete")
DiscreteKind(switch_at=0.5)
>>> kind_from_spec({"kind": "points"})
Traceback (most recent call last):
 ...
an.timing.kinds.FieldKindError: unknown field kind 'points'; known: ['number', 'angle', 'vector', 'quaternion', 'color', 'orbit', 'discrete']
```

### an.timing.kinds.kind_names(, owner=None)

The registered kind names in registration order; only `owner`’s when given.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.timing.kinds.register_kind(name, factory, , replace=False, owner=None)

Register a field kind under `name` (how a genre adds one).

`owner` names who registered it; only [`CORE_OWNER`](#an.timing.kinds.CORE_OWNER)’s kinds reach
`an`’s contract files.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`FieldKind`](#an.timing.kinds.FieldKind)]

```pycon
>>> sorted(kind_names())[:3]
['angle', 'color', 'discrete']
```

### an.timing.kinds.shortest_delta(a, b, period=360.0)

The signed shortest turn from `a` to `b`, in `[-period/2, period/2]`.

An exact half turn goes in the direction of `b - a`, so a return trip
retraces its path (0 -> 180 -> 0 goes there and back, not round).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> shortest_delta(350, 10), shortest_delta(10, 350), shortest_delta(0, 180)
(20.0, -20.0, 180.0)
```

### an.timing.kinds.slerp(a, b, u)

Spherical interpolation of unit quaternions `[x, y, z, w]`, the short way.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]
