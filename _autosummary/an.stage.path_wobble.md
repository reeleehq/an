# an.stage.path_wobble

A hand-drawn wobble for stroked paths, applied at compile time (an#161).

A ruled line reads as a diagram; a line that wanders a little reads as drawn
by hand. The wobble displaces the FLATTENED polyline sideways (along its
normal) by a smooth seeded noise, before it reaches the wire, so the runtime
and its parity spec ([`an.stage.path_geometry`](an.stage.path_geometry.md#module-an.stage.path_geometry)) never learn about it:
trim, dashes and arrowheads work on the wobbly polyline exactly as on any
other.

- **Deterministic everywhere.** The noise is value noise over knots one
  wavelength apart, each knot’s value read from `sha256(seed:k)`, joined by
  a cubic smoothstep: only `+ - * /`, `floor` and `sqrt`, no
  trigonometry, so the compiled points are the same bytes on every machine.
- **Seeded by the entity** (`"<entity id>:<wobble_seed>"`), like a
  character’s blink phase: two arrows sharing one document wobble
  differently, and the same arrow wobbles the same way every render.
- **The ends stay put.** The amplitude ramps up over the first and down over
  the last wavelength, so a route still starts and ends where it was drawn
  to, and an arrowhead’s tip lands on its target.
- **Static.** One displacement per path. A *boil* (a wobble that changes on
  twos) is several displaced polylines on a step channel; not built.

```pycon
>>> pts = wobble_polyline([(0.0, 0.0), (200.0, 0.0)], amplitude=4.0, wavelength=50.0, seed="route:0")
>>> pts[0], pts[-1]  # the ends are where they were
((0.0, 0.0), (200.0, 0.0))
>>> 0.0 < max(abs(y) for _, y in pts) <= 4.0
True
>>> pts == wobble_polyline([(0.0, 0.0), (200.0, 0.0)], amplitude=4.0, wavelength=50.0, seed="route:0")
True
```

### Module Attributes

| [`WOBBLE_SAMPLES_PER_WAVELENGTH`](#an.stage.path_wobble.WOBBLE_SAMPLES_PER_WAVELENGTH)   | enough that the wobble reads as a curve, not a zig-zag, at any amplitude a stroke should take.   |
|----------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| [`MAX_WOBBLE_POINTS`](#an.stage.path_wobble.MAX_WOBBLE_POINTS)               | The most points a wobbled path may carry.                                                        |

### Functions

| [`wobble_polyline`](#an.stage.path_wobble.wobble_polyline)(points, \*, amplitude, ...)      | `points` resampled and wobbled; see [`wobble_with_vertices()`](#an.stage.path_wobble.wobble_with_vertices).                            |
|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| [`wobble_with_vertices`](#an.stage.path_wobble.wobble_with_vertices)(points, \*, amplitude, ...) | `points` resampled every `wavelength / 8` px and each sample moved up to `amplitude` px along the path's normal by seeded smooth noise. |
| [`wobble_point_count`](#an.stage.path_wobble.wobble_point_count)(length, wavelength)           | How many samples a wobble of `wavelength` puts along `length` px.                                                                       |

### an.stage.path_wobble.MAX_WOBBLE_POINTS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 20000*

The most points a wobbled path may carry. Every point is redrawn each
frame a trim or dash moves; past this the wavelength is too short for the
path’s length (a hair-fine wobble over a long route).

### an.stage.path_wobble.WOBBLE_SAMPLES_PER_WAVELENGTH *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 8*

enough that the wobble reads as a
curve, not a zig-zag, at any amplitude a stroke should take.

* **Type:**
  Samples per wavelength of the noise

### an.stage.path_wobble.wobble_point_count(length, wavelength)

How many samples a wobble of `wavelength` puts along `length` px.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.stage.path_wobble.wobble_polyline(points, , amplitude, wavelength, seed)

`points` resampled and wobbled; see [`wobble_with_vertices()`](#an.stage.path_wobble.wobble_with_vertices).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.stage.path_wobble.wobble_with_vertices(points, , amplitude, wavelength, seed)

`points` resampled every `wavelength / 8` px and each sample moved
up to `amplitude` px along the path’s normal by seeded smooth noise.

The original vertices are kept as samples (a corner stays a corner) and
move along the bisector of their two legs. Raises `ValueError` when the
result would carry more than [`MAX_WOBBLE_POINTS`](#an.stage.path_wobble.MAX_WOBBLE_POINTS) points.

Also returns, for each input point, its index in the output (where a
vertex landed), so a caller can find the authored points on the wobbled
line ([`an.stage.paths.drawn_polyline()`](an.stage.paths.md#an.stage.paths.drawn_polyline)).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]]
