# an.paths

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
[`an.props.PropDescriptor`](an.props.html.md#an.props.PropDescriptor) and a scene names it with an ordinary
`AssetRef(kind="prop", ...)`. The compiler dispatches on the document’s
`kind`. That keeps the scene IR unchanged (no field, no migration) and gives
a path stage placement (`at`, `scale`) and entity ordering for free.

Geometry is often per-shot (the same arrow style, a different route), so an
entity’s `overrides` are merged over the stored document and the result is
validated **strictly** — [`resolve_path()`](#an.paths.resolve_path) is the one place that happens,
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

| [`PATH_DOCUMENT_KIND`](#an.paths.PATH_DOCUMENT_KIND)   | Its own versioned document kind, registered from the module that owns the schema — the rule `PropDescriptor` and `CharacterDescriptor` follow.   |
|-----------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_STROKE_COLOUR`](#an.paths.DFLT_STROKE_COLOUR)   | The stroke colour when the document names none.                                                                                                  |
| [`MIN_DASH_PERIOD`](#an.paths.MIN_DASH_PERIOD)      | The shortest dash period (dash + gap), scene pixels.                                                                                             |

### Functions

| [`resolve_path`](#an.paths.resolve_path)(document[, overrides])   | The path an entity draws: its stored document with `overrides` on top.   |
|----------------------------------------------------------------------------------------|--------------------------------------------------------------------------|

### Classes

| [`PathDescriptor`](#an.paths.PathDescriptor)(\*\*data)   | The on-disk path schema, saved as a prop's `prop.json`.   |
|-----------------------------------------------------------------------------|-----------------------------------------------------------|

### an.paths.DFLT_STROKE_COLOUR *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '#c0392b'*

The stroke colour when the document names none. A `StylePack`’s `stroke`
role replaces it (an#161) — but only this default: a document that sets
`color` itself is art, not a default, and a pack does not rewrite art (the
same line `an.styles` draws for SVG). A per-entity `stroke` override in the
pack wins over both.

### an.paths.MIN_DASH_PERIOD *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1.0*

The shortest dash period (dash + gap), scene pixels. Bounds the number of
dashes a path can ask the runtime to redraw every frame: a path a few
thousand pixels long is a few thousand dashes at most.

### an.paths.PATH_DOCUMENT_KIND *: [DocumentKind](an.ir.html.md#an.ir.DocumentKind)* *= DocumentKind(name='PathDescriptor', version_field='schema_version', current_version='0.1.0')*

Its own versioned document kind, registered from the module that owns the
schema — the rule `PropDescriptor` and `CharacterDescriptor` follow.

### *class* an.paths.PathDescriptor(\*\*data)

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

#### trim_start *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The visible span before anything animates it, as fractions of arc
length. `trim_end=0` starts a draw-on hidden, and a trim tween
with no `from_value` starts from these values (not the global rest).

### an.paths.resolve_path(document, overrides=None)

The path an entity draws: its stored document with `overrides` on top.

Validated strictly after the merge, so an override key the schema does not
know raises instead of vanishing (an environment override silently drops
unknown keys; a path’s does not).

* **Return type:**
  [`PathDescriptor`](#an.paths.PathDescriptor)

```pycon
>>> doc = {"kind": "PathDescriptor", "name": "a", "points": [[0, 0], [10, 0]]}
>>> resolve_path(doc, {"points": [[0, 0], [0, 50]]}).points
[(0.0, 0.0), (0.0, 50.0)]
>>> resolve_path(doc, {"colour": "#000000"})
Traceback (most recent call last):
...
pydantic_core._pydantic_core.ValidationError: 1 validation error for PathDescriptor
colour
  Extra inputs are not permitted [type=extra_forbidden, input_value='#000000', input_type=str]
...
```
