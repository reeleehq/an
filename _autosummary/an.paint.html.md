# an.paint

Paint: what fills a shape when one flat colour is not enough – a gradient.

A **gradient** blends colour **stops** (CSS’s *color stops*: a colour at an
offset from 0 to 1 along the gradient) either along a line (**linear**) or
outward from a centre (**radial**). The vocabulary is CSS’s
(`linear-gradient` / `radial-gradient`), so an author who knows one knows
the other:

- `angle` (linear) is the CSS gradient angle in degrees: `0` runs to the
  top, `90` to the right, `180` (the default) to the bottom. As in CSS the
  gradient line is as long as it must be for the box’s corners to sit on the
  first and last stop.
- `center` and `radius` (radial) are fractions of the box. In a box that is
  not square the gradient is an ellipse with the box’s proportions (CSS’s
  `ellipse`); `radius: 0.5` touches the sides of a centred box.
- Colours between stops are interpolated in sRGB, as CSS and SVG do by default;
  beyond the first and last stop the end colours hold.

Colours are hex strings (`#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`), the
representation the StylePack uses everywhere. Stops may be written as plain
colours, which are spread evenly:

```pycon
>>> g = Gradient(stops=["#101030", "#f0d090"])
>>> [(s.offset, s.color) for s in g.stops]
[(0.0, '#101030'), (1.0, '#f0d090')]
>>> Gradient(type="radial", stops=["#fff", "#0000"], radius=0.75).radius
0.75
```

A field that would do nothing is refused rather than ignored:

```pycon
>>> Gradient(type="radial", stops=["#fff", "#000"], angle=90)
Traceback (most recent call last):
...
pydantic_core._pydantic_core.ValidationError: ...
```

This is genre-neutral core vocabulary: a plane of the 2D stage draws one
([`an.stage.environments.PlaneArt`](an.stage.environments.html.md#an.stage.environments.PlaneArt)), and a StylePack names them as
**gradient roles** ([`an.styles.StylePack.gradients`](an.styles.html.md#an.styles.StylePack.gradients)).

### Module Attributes

| [`DFLT_GRADIENT_ANGLE`](#an.paint.DFLT_GRADIENT_ANGLE)   | top to bottom.   |
|------------------------------------------------------------------------|------------------|

### Functions

| [`rgba_of`](#an.paint.rgba_of)(color)   | A hex colour as `(r, g, b, a)` in `0..1`.   |
|-------------------------------------------------------------------|---------------------------------------------|

### Classes

| [`Gradient`](#an.paint.Gradient)(\*\*data)     | A linear or radial gradient between colour stops (see the module docstring).   |
|-------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`GradientStop`](#an.paint.GradientStop)(\*\*data) | A colour at an offset along the gradient (`0` start, `1` end).                 |

### an.paint.DFLT_GRADIENT_ANGLE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 180.0*

top to bottom.

* **Type:**
  CSS’s default gradient direction

### *class* an.paint.Gradient(\*\*data)

Bases: `BaseModel`

A linear or radial gradient between colour stops (see the module docstring).

#### angle *: [float](https://docs.python.org/3/builtins/functions.html#float)*

the CSS gradient angle, degrees (0 up, 90 right, 180 down).

* **Type:**
  Linear only

#### center *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]*

the centre, in fractions of the box.

* **Type:**
  Radial only

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### radius *: [float](https://docs.python.org/3/builtins/functions.html#float)*

the radius, in fractions of the box (an ellipse in a
non-square box).

* **Type:**
  Radial only

### *class* an.paint.GradientStop(\*\*data)

Bases: `BaseModel`

A colour at an offset along the gradient (`0` start, `1` end).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.paint.rgba_of(color)

A hex colour as `(r, g, b, a)` in `0..1`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> rgba_of("#ff000080")
(1.0, 0.0, 0.0, 0.5019607843137255)
```
