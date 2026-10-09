# an.stage.environments

Environments: a stage made of planes, at declared depths.

An environment was three scalars — `sky_color`, `ground_color`, `ground_y` —
merged through an **intersection filter** that silently dropped everything
else. The test pinning that warning used `parallax_layers: 3` as its example,
which says what the shape was for.

An `EnvironmentDescriptor` declares `planes`, and \*\*list order is draw
order\*\*. There is deliberately no `z` integer: the runtime sets no `zIndex`, so
a `z` field would be a second source of truth it could not honour, and two
orderings that can disagree is how the intersecting override got here in the
first place.

**\`depth\` is the parallax factor**, in Godot’s `Parallax2D.scroll_scale`
coordinates — a ratio, not a distance:

| `depth`     | meaning                                                                                                                                       |
|-------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `0.0`       | infinitely far: does not PAN — pinned against a camera<br/>translation. It still scales and rotates with the camera; see<br/>the limit below. |
| `0 < d < 1` | background — Godot’s own sanity range is 0.1 sky → 0.7 forest                                                                                 |
| `1.0`       | the character plane; **emits nothing**, which is today’s<br/>behaviour for everything and why this is byte-identity-free                      |
| `> 1.0`     | foreground: nearer than the characters, moving faster                                                                                         |

**\`depth\` governs translation only, and that is a stated limit rather than an
oversight.** The compensation is on `x`/`y`; `root.scale` and `root.rotation`
multiply the whole composed expression, so no per-plane factor can cancel
them. Measured: a `depth = 0` plane under `push_in` grows 1.0 → 1.25× and
drifts, exactly like the character plane.

Depth-aware zoom is the **dolly**, and the design of record defers it with its
reason: a true dolly grows the foreground ×1.40 while the moon grows ×1.02,
where today’s `push_in` grows both ×1.25 — precisely the uniform zoom the 1937
multiplane camera was built to replace. Until `dolly_in` exists, pair a
`depth = 0` plate with a pan, not a zoom.

Sign trap, pinned here because every surveyed tool disagrees: \*\*larger depth =
nearer = faster.\*\* Unity’s z-derived factor uses the INVERSE convention
(`f_unity ≡ 1 − f_godot`), so a Unity tutorial read while writing this code
will produce a stage that parallaxes backwards.

`characters_after` is how a plane gets IN FRONT of the characters — Rive’s
relative-ordering shape. `None` reproduces the old two-loop behaviour exactly
(every plane behind every character) and dissolves the tie between two planes
that share a depth.

### Module Attributes

| [`PLANE_FILL_SPAN`](#an.stage.environments.PLANE_FILL_SPAN)           | A `fill` plane with no declared size covers the canvas at any camera scale.                                                                                                                           |
|----------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Rect`](#an.stage.environments.Rect)                      | `(left, top, right, bottom)` in scene pixels, `y` down (the stage's axes).                                                                                                                            |
| [`ENVIRONMENT_DOCUMENT_KIND`](#an.stage.environments.ENVIRONMENT_DOCUMENT_KIND) | Its own versioned document, registered from the module that owns the schema — the rule `CharacterDescriptor` and `PropDescriptor` both follow, and the reason the registry is keyed per KIND (an#77). |

### Functions

| [`frame_rect`](#an.stage.environments.frame_rect)(\*, x, y, zoom, rotation, width, ...)   | The scene region a camera pose shows: centred on the camera, the canvas divided by the zoom, grown to the axis-aligned box of a rolled frame — CONSERVATIVE under roll (the box contains corners the rotated frame does not show, so a plate that covers a rolled view can still be flagged).   |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`plane_rect`](#an.stage.environments.plane_rect)(plane, art_size, \*[, camera])          | Where `plane` is drawn, in scene pixels, with the camera at `camera`.                                                                                                                                                                                                                           |
| [`uncovered_part`](#an.stage.environments.uncovered_part)(view, covers)                       | The bounding box of the part of `view` no rect in `covers` covers.                                                                                                                                                                                                                              |

### Classes

| [`EnvironmentDescriptor`](#an.stage.environments.EnvironmentDescriptor)(\*\*data)   | A stage made of planes.               |
|------------------------------------------------------------------------------------|---------------------------------------|
| [`Plane`](#an.stage.environments.Plane)(\*\*data)                   | One layer of the stage, at one depth. |
| [`PlaneArt`](#an.stage.environments.PlaneArt)(\*\*data)                | What a plane is made of.              |

### an.stage.environments.ENVIRONMENT_DOCUMENT_KIND *: [DocumentKind](an.ir.html.md#an.ir.DocumentKind)* *= DocumentKind(name='EnvironmentDescriptor', version_field='schema_version', current_version='0.1.0')*

Its own versioned document, registered from the module that owns the schema
— the rule `CharacterDescriptor` and `PropDescriptor` both follow, and the
reason the registry is keyed per KIND (an#77).

**No migration ladder, deliberately.** The obvious one — “today’s free-form
`meta.json` entries become plane-less descriptors” — would migrate nothing,
because a free-form entry ALREADY validates as an `EnvironmentDescriptor`
with no planes: `extra="allow"` carries `description`/`tags`/the colour
scalars through untouched, and every field this model adds has a default.
There is no shape change to make.

It was written and then removed in review (an#110): `_environment_descriptor`
gates on the `kind` tag before migrating, so only a document already written
in the post-an#110 shape could ever have reached it — a registered migration
that runs on nothing, which is the decoration `CLAUDE.md`’s “never register
a migration without a read path that runs it” rule exists to prevent. The
KIND stays registered: it declares where the version field lives, which is
what a future real migration will need.

### *class* an.stage.environments.EnvironmentDescriptor(\*\*data)

Bases: `_EnvModel`

A stage made of planes. Saved as `meta.json` in the environments store.

```pycon
>>> env = EnvironmentDescriptor(name="forest", planes=[
...     Plane(name="sky", depth=0.1),
...     Plane(name="trees", depth=0.6),
...     Plane(name="grass", depth=1.4),
... ], characters_after="trees")
>>> [p.name for p in env.planes]
['sky', 'trees', 'grass']
>>> env.characters_after
'trees'
```

List order is draw order, and `characters_after` names the plane the
characters stand in front of — so `grass` above is a FOREGROUND plane,
drawn over them. `None` puts every plane behind every character, which is
what the two-loop builder did before an#110 and is why an environment that
declares no planes compiles byte-identically.

#### anchors *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]]*

Named stage marks — a horizon is one of them. A dedicated `horizon`
field would be two fields for one fact, which is how the intersecting
override arrived.

#### characters_after *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The plane the characters are drawn in FRONT of. `None` = all planes
behind all characters.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### planes *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[Plane](#an.stage.environments.Plane)]*

the runtime sets no
`zIndex`, so a second ordering would be one it could not honour.

* **Type:**
  **LIST ORDER IS DRAW ORDER.** There is no `z` field

#### source *: [AssetSource](an.ir.assets.html.md#an.ir.assets.AssetSource) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where this art came from and what its licence obliges. Not decoration:
`an credits` walked ONLY `mall["characters"]`, so the PR that gives
environments art is the PR that closes that hole — otherwise
`an credits` becomes an affirmative false statement about plates.

### an.stage.environments.PLANE_FILL_SPAN *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 4000.0*

A `fill` plane with no declared size covers the canvas at any camera scale.
The same 4000 the preset backdrop uses, and for the same reason — the runtime
centres `root` and applies camera scale, so a huge rect always covers. Lives
here (the schema) so the IR layer’s framing check and the compiler read one
number; `an.stage.compile` re-exports it.

### *class* an.stage.environments.Plane(\*\*data)

Bases: `BaseModel`

One layer of the stage, at one depth.

```pycon
>>> Plane(name="sky", art=PlaneArt(color="#cfe9ff"), depth=0.1).depth
0.1
>>> Plane(name="sky", parallax=(0.2, 0.0)).parallax
(0.2, 0.0)
```

**\`extra=”forbid”\`, unlike the document that holds it.** An
`EnvironmentDescriptor` is `extra="allow"` because the environments store
is a free-form `meta.json` whose natural shape includes `name`,
`description` and `tags` — refusing those would hard-fail ordinary data. A
plane is not free-form: it is a precise instruction to draw something, and
a misspelled key there is the exact failure an#110 exists to remove. The
old override path *silently dropped* every key it did not know, and the
test pinning that warning used `parallax_layers: 3` as its example.

#### anchor *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]*

The art’s anchor within its own box, in 0..1 per axis.

#### depth *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The parallax factor — a RATIO, in Godot’s `Parallax2D.scroll_scale`
coordinates. `1.0` is the character plane and emits nothing. See this
module’s docstring for the table and for the Unity sign trap.

#### factors()

The per-axis parallax factors this plane actually moves by.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> Plane(name="p", depth=0.4).factors()
(0.4, 0.4)
>>> Plane(name="p", depth=0.4, parallax=(0.2, 0.0)).factors()
(0.2, 0.0)
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Becomes the scene node’s name, under the environment entity’s id.

#### offset *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]*

Where the plane sits, in scene pixels from the stage centre.

#### parallax *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per-axis override of `depth`, for a plane that scrolls horizontally but
not vertically. `None` means `(depth, depth)`.

#### size *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

`None` = the art’s own extent. A `fill` with no size covers the canvas.
The box the art is fitted into, in scene pixels. **A declared size wins**
(an#211); `None` = the art’s own extent — an SVG’s `width`/`height`, a
raster’s pixel size. A `fill` with no size covers the canvas.

#### source *: [AssetSource](an.ir.assets.html.md#an.ir.assets.AssetSource) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where THIS plane’s art came from, when it is not the environment’s —
a composite stage of a carved plate and a CC0 prop credits both
(an#211). `None` = the environment’s `source` covers it. Omitted from
the stored document when unset.

### *class* an.stage.environments.PlaneArt(\*\*data)

Bases: `BaseModel`

What a plane is made of.

```pycon
>>> PlaneArt(kind="fill", color="#cfe9ff").color
'#cfe9ff'
>>> PlaneArt(kind="image", src="plates/forest.svg").src
'plates/forest.svg'
>>> PlaneArt(kind="image", src="plates/street.png").src
'plates/street.png'
```

An `image` is SVG or raster — PNG, JPEG or WebP (an#211): the compiler
sizes it from its header and PixiJS loads it natively.

A `gradient` (an#275) is a linear or radial blend of colour stops
([`an.paint.Gradient`](an.paint.html.md#an.paint.Gradient), CSS’s vocabulary), compiled into an inline SVG
texture ([`an.stage.gradients`](an.stage.gradients.html.md#module-an.stage.gradients)) – a backlit-glass plate or a sky
without hand-drawing one:

```pycon
>>> PlaneArt(kind="gradient", gradient={"type": "radial",
...          "stops": ["#fff3d0", "#3a2a18"]}).gradient.type
'radial'
```

A `role` names the plane’s paint for a StylePack: under a pack whose
`gradients` sets that role, the plane is drawn with the pack’s gradient (a
`fill` plane included); with no pack, or a pack that does not set it, the
plane draws exactly as authored.

```pycon
>>> PlaneArt(kind="fill", color="#202830", role="glass").role
'glass'
```

`generated` art is still not a kind: it needs a generator, and this
package’s standing rule is that schema without a consumer is worse than an
absent field — the `repeat`/`TilingSprite` decision in an#110 is the same
call made the same way.

#### color *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

a CSS colour.

* **Type:**
  `fill` only

#### gradient *: [Gradient](an.paint.html.md#an.paint.Gradient) | [None](https://docs.python.org/3/builtins/constants.html#None)*

the gradient (an#275). Omitted from the stored document
when unset.

* **Type:**
  `gradient` only

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### role *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

the gradient role a StylePack may set for this
plane (an#275). Omitted from the stored document when unset.

* **Type:**
  `fill` or `gradient`

#### src *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

a path under the environment’s own folder in the store,
exactly as a character attachment’s `path` is — `.svg`, `.png`,
`.jpg`/`.jpeg` or `.webp`.

* **Type:**
  `image` only

### an.stage.environments.Rect

`(left, top, right, bottom)` in scene pixels, `y` down (the stage’s axes).

alias of [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.stage.environments.frame_rect(, x, y, zoom, rotation, width, height)

The scene region a camera pose shows: centred on the camera, the canvas
divided by the zoom, grown to the axis-aligned box of a rolled frame —
CONSERVATIVE under roll (the box contains corners the rotated frame does
not show, so a plate that covers a rolled view can still be flagged).

`root.pivot` is the camera and `root.scale` the zoom, composed about the
canvas centre, so a pose shows `camera ± canvas / (2 · zoom)`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> frame_rect(x=0, y=0, zoom=1.25, rotation=0, width=320, height=240)
(-128.0, -96.0, 128.0, 96.0)
```

### an.stage.environments.plane_rect(plane, art_size, , camera=(0.0, 0.0))

Where `plane` is drawn, in scene pixels, with the camera at `camera`.

The compiler’s own geometry, restated for a pre-flight: the box is the
declared `size` or the art’s extent (`art_size`), the art is fitted into
it by `fit`, placed by `anchor` at `offset`, and the plane’s parallax
compensation moves it by `(1 − f) · camera` per axis. `None` when the
extent cannot be known (an image whose art cannot be measured and whose
`fit` makes the drawn size depend on it) — an unknown, not a hole.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> plane_rect(Plane(name="p", art=PlaneArt(kind="image", src="a.png"),
...                  size=(100.0, 50.0), fit="stretch"), None)
(-50.0, -25.0, 50.0, 25.0)
>>> plane_rect(Plane(name="p", art=PlaneArt(kind="image", src="a.png"), depth=0.0),
...            (200.0, 100.0), camera=(40.0, 0.0))
(-60.0, -50.0, 140.0, 50.0)
```

### an.stage.environments.uncovered_part(view, covers)

The bounding box of the part of `view` no rect in `covers` covers.

`None` when the union covers the whole view. Exact for axis-aligned
rects: the view is cut into cells at every cover edge, and a cell is
covered or not as a whole.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> uncovered_part((0, 0, 10, 10), [(0, 0, 10, 8)])
(0, 8, 10, 10)
>>> uncovered_part((0, 0, 10, 10), [(0, 0, 6, 10), (5, 0, 10, 10)]) is None
True
```
