# an.stage.path_geometry

Stroked-path geometry — the executable spec of `runtime.js::pathGeometry`.

The runtime draws a path (an#160) from three things this module defines:

- **arc length** — cumulative straight-segment lengths over the polyline;
- **trim** — the visible span `[min(ts, te), max(ts, te)]`, clamped to
  `[0, 1]`, as fractions of that length;
- **dashes** — an optional on/off pattern laid along the WHOLE path from arc
  length 0 (shifted by an offset) and only then clipped to the trimmed span, so
  a draw-on reveals dashes in place rather than making them crawl (an#161);
- **the arrowhead** — a triangle whose tip is the trimmed end, oriented along
  the direction of the segment the tip lies on (the *incoming* segment when
  the tip sits exactly on a vertex).

`tests/test_path.py` lifts the real `runtime.js` functions, runs them under
node on a shared battery, and compares — behaviourally, like the channel
evaluator’s parity test. Both sides use the **same operation order** and no
trigonometry (a direction is a unit vector, never an angle), and every
operation is IEEE `+ - * / sqrt`, which both languages round exactly — so
the parity is exact, not within a tolerance.

Cubic Béziers never reach the runtime: [`flatten_curve()`](#an.stage.path_geometry.flatten_curve) turns them into a
polyline at compile time, so the wire carries one geometry kind.

```pycon
>>> g = path_geometry([(0.0, 0.0), (100.0, 0.0)], 0.0, 0.5)
>>> g["stroke"]
[(0.0, 0.0), (50.0, 0.0)]
>>> g["head"] is None
True
>>> g = path_geometry([(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)], 0.0, 0.75,
...                   head_length=20.0, head_width=10.0)
>>> g["head"]  # tip at (100, 50), pointing DOWN (+y) along the second leg
[(100.0, 50.0), (95.0, 30.0), (105.0, 30.0)]
```

### Module Attributes

| [`HEAD_STROKE_INSET`](#an.stage.path_geometry.HEAD_STROKE_INSET)   | Where the stroke stops under an arrowhead, as a fraction of the head's length back from the tip.                                                                                                            |
|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`OUTLINE_MITER_LIMIT`](#an.stage.path_geometry.OUTLINE_MITER_LIMIT) | The longest a variable-width stroke's corner may reach, as a multiple of its half-width there (an#161): past it the miter is cut to this length, so a hairpin turn does not throw a spike across the frame. |

### Functions

| [`flatten_curve`](#an.stage.path_geometry.flatten_curve)(points, \*[, curve, samples, ...])   | The polyline the runtime draws for `points`.                                                                                        |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| [`cumulative_lengths`](#an.stage.path_geometry.cumulative_lengths)(points)                         | Arc length at each vertex.                                                                                                          |
| [`point_at`](#an.stage.path_geometry.point_at)(points, cum, s)                           | The point at arc length `s`.                                                                                                        |
| [`trim_polyline`](#an.stage.path_geometry.trim_polyline)(points, cum, a, b)                   | The sub-polyline between arc lengths `a < b`: the two cut points and every vertex strictly between them.                            |
| [`dash_spans`](#an.stage.path_geometry.dash_spans)(a, b, dash, gap, offset)                | The arc-length spans `[lo, hi]` inside `[a, b]` that a dash covers.                                                                 |
| [`path_geometry`](#an.stage.path_geometry.path_geometry)(points, trim_start, trim_end, \*)    | What the runtime draws: `{"stroke": [points], "head": [3 points] | None}`.                                                          |
| [`profile_width`](#an.stage.path_geometry.profile_width)(profile, width, u)                   | The stroke width at fraction `u` of the WHOLE path's length (an#161): `width` times the profile's factor, linear between its stops. |
| [`stroke_outline`](#an.stage.path_geometry.stroke_outline)(line, start, total, width, ...)     | The filled polygon of a variable-width stroke along `line` (an#161).                                                                |

### an.stage.path_geometry.HEAD_STROKE_INSET *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

Where the stroke stops under an arrowhead, as a fraction of the head’s
length back from the tip. Half-way keeps a butt or round cap inside the
head for the default proportions, so the stroke never pokes past the tip.

### an.stage.path_geometry.OUTLINE_MITER_LIMIT *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 4.0*

The longest a variable-width stroke’s corner may reach, as a multiple of
its half-width there (an#161): past it the miter is cut to this length, so
a hairpin turn does not throw a spike across the frame.

### an.stage.path_geometry.cumulative_lengths(points)

Arc length at each vertex. Mirror of `runtime.js::pathLengths`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> cumulative_lengths([(0, 0), (3, 4), (3, 10)])
[0.0, 5.0, 11.0]
```

### an.stage.path_geometry.dash_spans(a, b, dash, gap, offset)

The arc-length spans `[lo, hi]` inside `[a, b]` that a dash covers.

The pattern is anchored at arc length `0` — dash `k` covers
`[offset + k*period, offset + k*period + dash]` — and is clipped to the
window afterwards, so moving `a` or `b` never moves a dash. Only IEEE
`+ - * /` and `floor`, in the order `runtime.js::pathDashSpans` uses.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

```pycon
>>> dash_spans(0.0, 100.0, 10.0, 15.0, 0.0)
[(0.0, 10.0), (25.0, 35.0), (50.0, 60.0), (75.0, 85.0)]
>>> dash_spans(30.0, 60.0, 10.0, 15.0, 0.0)  # clipped, not re-anchored
[(30.0, 35.0), (50.0, 60.0)]
>>> dash_spans(0.0, 30.0, 10.0, 10.0, 5.0)  # offset slides the pattern forward
[(5.0, 15.0), (25.0, 30.0)]
```

### an.stage.path_geometry.flatten_curve(points, , curve='polyline', samples=24, sampling='parameter')

The polyline the runtime draws for `points`.

`curve="cubic"` reads `points` as chained cubic Béziers
(`p0 c1 c2 p1 c1 c2 p2 ...`) and samples each at `samples` steps;
shared endpoints appear once. `sampling="parameter"` (the default) steps
uniformly in each curve’s parameter, so points crowd where the curve is
slow; `"arclength"` (an#161) steps uniformly along its length, so the
points are evenly spaced (a smoother bend for the same count).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

```pycon
>>> flatten_curve([(0, 0), (10, 0)])
[(0.0, 0.0), (10.0, 0.0)]
>>> pts = flatten_curve([(0, 0), (0, 10), (10, 10), (10, 0)], curve="cubic", samples=2)
>>> pts
[(0.0, 0.0), (5.0, 7.5), (10.0, 0.0)]
```

### an.stage.path_geometry.path_geometry(points, trim_start, trim_end, , head_length=0.0, head_width=0.0, dash=0.0, gap=0.0, dash_offset=0.0, tail_head_length=0.0, tail_head_width=0.0, width=0.0, width_profile=None)

What the runtime draws: `{"stroke": [points], "head": [3 points] | None}`.

`tail_head_length > 0` adds a TAIL arrowhead at the trimmed start,
pointing back along the path (an#161: a double-headed arrow with both); it
is then under a `"tail"` key (absent otherwise), and the stroke starts
[`HEAD_STROKE_INSET`](#an.stage.path_geometry.HEAD_STROKE_INSET) of its length in from that tip. While the visible
length is shorter than the heads together, both are scaled by the same
factor, so a draw-on grows them in.

`dash > 0` makes the stroke a dash pattern: `stroke` is then `[]` and
a `"dashes"` key (absent otherwise) holds one polyline per visible dash.

`width_profile` (an#161) makes the stroke a variable-width SHAPE: an
`"outlines"` key (absent otherwise) holds one polygon per stroke or dash
([`stroke_outline()`](#an.stage.path_geometry.stroke_outline)), which the runtime fills instead of stroking.

`head_length > 0` turns the arrowhead on. While the visible length is
shorter than the head, the head is scaled by `visible / head_length` so
a draw-on grows it in rather than popping a full-size triangle at frame
one. The stroke stops [`HEAD_STROKE_INSET`](#an.stage.path_geometry.HEAD_STROKE_INSET) of the head’s length back
from the tip, inside the head. Mirror of `runtime.js::pathGeometry`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

```pycon
>>> path_geometry([(0.0, 0.0), (10.0, 0.0)], 0.3, 0.3)
{'stroke': [], 'head': None}
```

### an.stage.path_geometry.point_at(points, cum, s)

The point at arc length `s`. Mirror of `runtime.js::pathPointAt`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.stage.path_geometry.profile_width(profile, width, u)

The stroke width at fraction `u` of the WHOLE path’s length (an#161):
`width` times the profile’s factor, linear between its stops.
Mirror of `runtime.js::pathProfileWidth`.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> profile_width([(0.0, 1.0), (1.0, 0.0)], 8.0, 0.25)
6.0
```

### an.stage.path_geometry.stroke_outline(line, start, total, width, profile)

The filled polygon of a variable-width stroke along `line` (an#161).

`line` is a trimmed piece of the path beginning at arc length `start`
of a path `total` long, so a point’s width is read at its place on the
WHOLE path: trimming never makes the width crawl. Each vertex is offset
both ways along the bisector of its legs’ normals by half its width,
lengthened to keep the stroke’s width through the corner (capped at
[`OUTLINE_MITER_LIMIT`](#an.stage.path_geometry.OUTLINE_MITER_LIMIT)). Butt ends. Left side forward, then the
right side back. Mirror of `runtime.js::pathOutline`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

```pycon
>>> stroke_outline([(0.0, 0.0), (10.0, 0.0)], 0.0, 10.0, 4.0, [(0.0, 1.0), (1.0, 0.5)])
[(0.0, 2.0), (10.0, 1.0), (10.0, -1.0), (0.0, -2.0)]
```

### an.stage.path_geometry.trim_polyline(points, cum, a, b)

The sub-polyline between arc lengths `a < b`: the two cut points and
every vertex strictly between them. Mirror of `runtime.js::pathTrim`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]
