# an.adapters.cutout.path

Stroked-path geometry — the executable spec of `runtime.js::pathGeometry`.

The runtime draws a path (an#160) from three things this module defines:

- **arc length** — cumulative straight-segment lengths over the polyline;
- **trim** — the visible span `[min(ts, te), max(ts, te)]`, clamped to
  `[0, 1]`, as fractions of that length;
- **the arrowhead** — a triangle whose tip is the trimmed end, oriented along
  the direction of the segment the tip lies on (the *incoming* segment when
  the tip sits exactly on a vertex).

`tests/test_path.py` lifts the real `runtime.js` functions, runs them under
node on a shared battery, and compares — behaviourally, like the channel
evaluator’s parity test. Both sides use the **same operation order** and no
trigonometry (a direction is a unit vector, never an angle), and every
operation is IEEE `+ - * / sqrt`, which both languages round exactly — so
the parity is exact, not within a tolerance.

Cubic Béziers never reach the runtime: [`flatten_curve()`](#an.adapters.cutout.path.flatten_curve) turns them into a
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

| [`HEAD_STROKE_INSET`](#an.adapters.cutout.path.HEAD_STROKE_INSET)   | Where the stroke stops under an arrowhead, as a fraction of the head's length back from the tip.   |
|----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|

### Functions

| [`flatten_curve`](#an.adapters.cutout.path.flatten_curve)(points, \*[, curve, samples])     | The polyline the runtime draws for `points`.                                                             |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| [`cumulative_lengths`](#an.adapters.cutout.path.cumulative_lengths)(points)                      | Arc length at each vertex.                                                                               |
| [`point_at`](#an.adapters.cutout.path.point_at)(points, cum, s)                        | The point at arc length `s`.                                                                             |
| [`trim_polyline`](#an.adapters.cutout.path.trim_polyline)(points, cum, a, b)                | The sub-polyline between arc lengths `a < b`: the two cut points and every vertex strictly between them. |
| [`path_geometry`](#an.adapters.cutout.path.path_geometry)(points, trim_start, trim_end, \*) | What the runtime draws: `{"stroke": [points], "head": [3 points] | None}`.                               |

### an.adapters.cutout.path.HEAD_STROKE_INSET *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

Where the stroke stops under an arrowhead, as a fraction of the head’s
length back from the tip. Half-way keeps a butt or round cap inside the
head for the default proportions, so the stroke never pokes past the tip.

### an.adapters.cutout.path.cumulative_lengths(points)

Arc length at each vertex. Mirror of `runtime.js::pathLengths`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> cumulative_lengths([(0, 0), (3, 4), (3, 10)])
[0.0, 5.0, 11.0]
```

### an.adapters.cutout.path.flatten_curve(points, , curve='polyline', samples=24)

The polyline the runtime draws for `points`.

`curve="cubic"` reads `points` as chained cubic Béziers
(`p0 c1 c2 p1 c1 c2 p2 ...`) and samples each uniformly in its parameter
at `samples` steps; shared endpoints appear once.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

```pycon
>>> flatten_curve([(0, 0), (10, 0)])
[(0.0, 0.0), (10.0, 0.0)]
>>> pts = flatten_curve([(0, 0), (0, 10), (10, 10), (10, 0)], curve="cubic", samples=2)
>>> pts
[(0.0, 0.0), (5.0, 7.5), (10.0, 0.0)]
```

### an.adapters.cutout.path.path_geometry(points, trim_start, trim_end, , head_length=0.0, head_width=0.0)

What the runtime draws: `{"stroke": [points], "head": [3 points] | None}`.

`head_length > 0` turns the arrowhead on. While the visible length is
shorter than the head, the head is scaled by `visible / head_length` so
a draw-on grows it in rather than popping a full-size triangle at frame
one. The stroke stops [`HEAD_STROKE_INSET`](#an.adapters.cutout.path.HEAD_STROKE_INSET) of the head’s length back
from the tip, inside the head. Mirror of `runtime.js::pathGeometry`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

```pycon
>>> path_geometry([(0.0, 0.0), (10.0, 0.0)], 0.3, 0.3)
{'stroke': [], 'head': None}
```

### an.adapters.cutout.path.point_at(points, cum, s)

The point at arc length `s`. Mirror of `runtime.js::pathPointAt`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.adapters.cutout.path.trim_polyline(points, cum, a, b)

The sub-polyline between arc lengths `a < b`: the two cut points and
every vertex strictly between them. Mirror of `runtime.js::pathTrim`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]
