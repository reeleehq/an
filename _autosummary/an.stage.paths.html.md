# an.stage.paths

Stroked paths: routes, invasion arrows, borders, timelines, connectors.

One drawable covers the whole map-and-infographic motif family (epic #9,
Wave 9; an#160): a stroke along a polyline or a chain of cubic Béziers, with an
animatable **trim** — the visible span, as fractions of arc length — and an
optional **arrowhead** that rides the moving tip, oriented along the path.

```pycon
>>> arrow = PathDescriptor(
...     name="route",
...     points=[(-300.0, 0.0), (0.0, 0.0), (0.0, 200.0)],
...     arrowhead=True,
... )
>>> arrow.kind, arrow.curve, arrow.trim_end
('PathDescriptor', 'polyline', 1.0)
>>> arrow.head_length_px, arrow.head_width_px  # defaults scale with the stroke
(28.0, 24.0)
```

**Where it lives, and why there.** A path is a prop — a drawable that is not a
person — so its document sits in the `props` store beside
[`an.stage.props.PropDescriptor`](an.stage.props.html.md#an.stage.props.PropDescriptor) and a scene names it with an ordinary
`AssetRef(kind="prop", ...)`. The compiler dispatches on the document’s
`kind`. That keeps the scene IR unchanged (no field, no migration) and gives
a path stage placement (`at`, `scale`) and entity ordering for free.

Geometry is often per-shot (the same arrow style, a different route), so an
entity’s `overrides` are merged over the stored document and the result is
validated **strictly** — [`resolve_path()`](#an.stage.paths.resolve_path) is the one place that happens,
and both the compiler and `an validate` call it, so their verdicts agree.

**Trim is an ordinary property.** `trim_start` / `trim_end` are numeric
node properties in `an.base.TRANSFORM_PROPERTIES`, animated by ordinary
`set`/`tween` actions and flattened to the canonical timeline like
`alpha`: `tween route trim_end 0 -> 1` is a draw-on. The fields below are
only the values the path shows before anything animates it.

Why a separate document rather than a `PropDescriptor` field: a
`PropDescriptor` is a *rig* (bones, slots, skins, swap sets) whose art is
SVG; a path has none of those, and its colour is decided by the compiler
(which is what will let a [`an.styles.StylePack`](an.styles.html.md#an.styles.StylePack) reach it), not by art.

### Module Attributes

| [`PATH_DOCUMENT_KIND`](#an.stage.paths.PATH_DOCUMENT_KIND)   | Its own versioned document kind, registered from the module that owns the schema — the rule `PropDescriptor` and `CharacterDescriptor` follow.   |
|-----------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_STROKE_COLOUR`](#an.stage.paths.DFLT_STROKE_COLOUR)   | The stroke colour when the document names none.                                                                                                  |
| [`MIN_DASH_PERIOD`](#an.stage.paths.MIN_DASH_PERIOD)      | The shortest dash period (dash + gap), scene pixels.                                                                                             |

### Functions

| [`resolve_path`](#an.stage.paths.resolve_path)(document[, overrides])            | The path an entity draws: its stored document with `overrides` on top.                                                                                                                                                                                                                                                                                     |
|-------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`drawn_polyline`](#an.stage.paths.drawn_polyline)(desc, entity_id)                | The polyline the compiler puts on the wire for entity `entity_id` drawing `desc` — flattened, closed, wobbled (the wobble is seeded by the entity) — and the index in it of each AUTHORED on-path point: every point of a polyline, `p0 p1 p2 ...` of a cubic chain (not its controls), and the closing return to the first point when `closed` added one. |
| [`draw_on_through`](#an.stage.paths.draw_on_through)(entity_id, path, arrivals, \*) | A draw-on whose tip reaches each authored point at its own time (an#161).                                                                                                                                                                                                                                                                                  |

### Classes

| [`PathDescriptor`](#an.stage.paths.PathDescriptor)(\*\*data)   | The on-disk path schema, saved as a prop's `prop.json`.   |
|-----------------------------------------------------------------------------|-----------------------------------------------------------|

### an.stage.paths.DFLT_STROKE_COLOUR *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '#c0392b'*

The stroke colour when the document names none. A `StylePack`’s `stroke`
role replaces it (an#161) — but only this default: a document that sets
`color` itself is art, not a default, and a pack does not rewrite art (the
same line `an.styles` draws for SVG). A per-entity `stroke` override in the
pack wins over both.

### an.stage.paths.MIN_DASH_PERIOD *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1.0*

The shortest dash period (dash + gap), scene pixels. Bounds the number of
dashes a path can ask the runtime to redraw every frame: a path a few
thousand pixels long is a few thousand dashes at most.

### an.stage.paths.PATH_DOCUMENT_KIND *: [DocumentKind](an.ir.html.md#an.ir.DocumentKind)* *= DocumentKind(name='PathDescriptor', version_field='schema_version', current_version='0.1.0')*

Its own versioned document kind, registered from the module that owns the
schema — the rule `PropDescriptor` and `CharacterDescriptor` follow.

### *class* an.stage.paths.PathDescriptor(\*\*data)

Bases: `BaseModel`

The on-disk path schema, saved as a prop’s `prop.json`.

`extra="forbid"`, unlike the store documents around it: a path is a
precise drawing instruction, and a misspelt `trim_ends` that silently
did nothing is the defect class this package refuses (the `Plane`
precedent, an#110).

`curve="cubic"` reads `points` as chained cubic Béziers,
`p0 c1 c2 p1 c1 c2 p2 ...` — `3n + 1` points, the SVG `C` command
chained:

```pycon
>>> PathDescriptor(name="s", curve="cubic", points=[(0, 0), (1, 1), (2, 1), (3, 0)]).curve
'cubic'
>>> PathDescriptor(name="s", curve="cubic", points=[(0, 0), (1, 1), (3, 0)])
Traceback (most recent call last):
...
pydantic_core._pydantic_core.ValidationError: 1 validation error for PathDescriptor
  Value error, a cubic path takes 3n + 1 points (p0, then c1 c2 p per segment); got 3 [type=value_error, input_value=..., input_type=dict]
...
```

#### closed *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

the path returns to its first point (a straight
closing leg is added when the last point is elsewhere) and the stroke
joins there instead of ending in two caps. Trim still runs from the
first point round to it again.

* **Type:**
  A closed shape (an#161)

#### color *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`#rrggbb`.

#### dash *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

`dash` on, `gap` off, repeating along
the path from ITS start — anchored to the path, not to the trimmed span,
so a draw-on reveals dashes in place instead of making them crawl.
`gap` defaults to `dash`. `None` = a solid stroke.

* **Type:**
  A dash pattern, scene pixels

#### dash_offset *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Shifts the pattern along the path (positive = forward). An ordinary
numeric node property like `trim_end`, so `tween route dash_offset`
is the “marching ants” route; only a dashed path has one.

#### fill *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The region a closed path encloses, `#rrggbb`; `None` = unfilled.
Drawn under the stroke and NOT trimmed: a draw-on draws the border and
the fill is there throughout. To fade a region in separately, make it
its own entity (`width: 0`, filled) and tween that node’s `alpha`.

#### fill_alpha *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The fill’s opacity, `0..1`.

#### *property* gap_px *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The gap of the dash pattern, scene pixels (`dash` when unset).

#### head_length *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Scene pixels; `None` = a multiple of `width`.

#### *property* head_length_px *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The arrowhead’s length in scene pixels.

#### *property* head_width_px *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The arrowhead’s base width in scene pixels.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### points *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]]*

Scene pixels, relative to the node’s origin (`AssetRef.stage.at`).

#### sampling *: [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)['parameter', 'arclength']*

`"parameter"` (uniform in
the curve’s parameter, the default) or `"arclength"` (evenly along it).

* **Type:**
  How a cubic’s samples are spaced (an#161)

#### tail_arrowhead *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

An arrowhead at the START too, pointing back along the path (an#161):
with `arrowhead`, a double-headed arrow. Same size as the end’s.

#### trim_start *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The visible span before anything animates it, as fractions of arc
length. `trim_end=0` starts a draw-on hidden, and a trim tween
with no `from_value` starts from these values (not the global rest).

#### width *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Stroke width, scene px. `0` = no stroke, only for a 

```
``
```

fill\`\`ed shape
(a region without a border).

#### width_profile *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]] | [None](https://docs.python.org/3/builtins/constants.html#None)*

`[[t, factor], ...]` along the WHOLE path’s
arc length (`t` from 0 to 1, increasing; `factor` times `width`,
linear between stops), so `[[0, 1], [1, 0]]` tapers to a point and a
trim never makes the width crawl. The stroke becomes a filled shape:
butt ends, mitred corners (no `cap`/`join`).

* **Type:**
  A variable width (an#161)

#### wobble *: [float](https://docs.python.org/3/builtins/functions.html#float)*

the stroke wanders up to this many scene
px either side of its line, by seeded smooth noise applied at compile
([`an.stage.path_wobble`](an.stage.path_wobble.html.md#module-an.stage.path_wobble)), its ends left where they are. `0` = a
ruled line.

* **Type:**
  A hand-drawn wobble (an#161)

#### wobble_seed *: [int](https://docs.python.org/3/builtins/functions.html#int)*

the noise is seeded by the entity’s id
and this number.

* **Type:**
  Another wobble of the same path

#### wobble_wavelength *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The wobble’s wavelength, scene px; `None` = a multiple of `width`.

#### *property* wobble_wavelength_px *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The wobble’s wavelength in scene pixels.

### an.stage.paths.draw_on_through(entity_id, path, arrivals, , start=0.0, easing='ease_in_out')

A draw-on whose tip reaches each authored point at its own time (an#161).

`arrivals[k]` is when the tip reaches authored point `k + 1` (the tip
is at point 0, hidden, at `start`): a route that reaches each city on a
beat, or slows into the last turn. One `tween` of `trim_end` per leg,
from the arc fraction of one point to the next on the polyline the
compiler draws ([`drawn_polyline()`](#an.stage.paths.drawn_polyline), wobble included, so the tip is ON
the point), each eased by `easing`, preceded by a `set` of
`trim_end` to 0 at 0. `arrivals` are absolute shot times, increasing.

Returns a list of top-level actions for `shot.actions.extend(...)`, as
[`an.stage.text.reveal_units()`](an.stage.text.html.md#an.stage.text.reveal_units) does.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

```pycon
>>> acts = draw_on_through("r", {"kind": "PathDescriptor", "name": "r",
...     "points": [[0, 0], [30, 0], [30, 10]]}, [1.0, 3.0])
>>> [(a.kind, getattr(a, "to_value", getattr(a, "value", None))) for a in acts]
[('set', 0.0), ('tween', 0.75), ('sequence', None)]
```

### an.stage.paths.drawn_polyline(desc, entity_id)

The polyline the compiler puts on the wire for entity `entity_id`
drawing `desc` — flattened, closed, wobbled (the wobble is seeded by
the entity) — and the index in it of each AUTHORED on-path point: every
point of a polyline, `p0 p1 p2 ...` of a cubic chain (not its controls),
and the closing return to the first point when `closed` added one.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]]

```pycon
>>> pts, anchors = drawn_polyline(PathDescriptor(name="r", points=[(0, 0), (10, 0), (10, 10)], closed=True), "r")
>>> pts[anchors[-1]], anchors
((0.0, 0.0), [0, 1, 2, 3])
```

### an.stage.paths.resolve_path(document, overrides=None)

The path an entity draws: its stored document with `overrides` on top.

Validated strictly after the merge, so an override key the schema does not
know raises instead of vanishing (an environment override silently drops
unknown keys; a path’s does not).

* **Return type:**
  [`PathDescriptor`](#an.stage.paths.PathDescriptor)

```pycon
>>> doc = {"kind": "PathDescriptor", "name": "a", "points": [[0, 0], [10, 0]]}
>>> resolve_path(doc, {"points": [[0, 0], [0, 50]]}).points
[(0.0, 0.0), (0.0, 50.0)]
>>> try:
...     resolve_path(doc, {"colour": "#000000"})
... except ValueError as e:
...     print(str(e).split("Value error, ")[1].split(". The fields")[0])
unknown PathDescriptor field(s): 'colour' (did you mean 'color', 'curve', 'source'?)
```
