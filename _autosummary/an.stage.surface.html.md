# an.stage.surface

Surface treatments, compiled (an#163 gap 5): outline, paper-gap shadow, glow, grain.

Every treatment here is a COMPILE-TIME expansion into ordinary document
content. None is a runtime filter, and none draws anything random at render
time. `runtime.js` keeps its rule against per-frame randomness, and its
determinism probe still sees zero filters.

- **Outline and paper-gap shadow**: [`UnderlayJSON`](an.stage.serialize.html.md#an.stage.serialize.UnderlayJSON)
  entries on a part’s visual. The runtime draws each one as a copy of the
  part’s own visual, BEHIND it, in the part’s own container. So the copy takes
  every transform the part takes (tweens, `play`, the camera, a stage scale)
  and needs no channel of its own. A swap on the part (a viseme, a blink)
  re-textures its copies in the same call.
- **Glow**: one extra child node, first in the entity so it draws behind every
  part. It is a radial-gradient SVG sprite, drawn with the engine’s native
  `add` blend.
- **Grain**: one seeded noise tile, made here as a palette PNG and tiled on the
  camera-immune overlay under any text, drawn with the native `multiply`
  blend. The PNG bytes are fully determined by the seed. The deflate stream is
  written as STORED blocks by hand, because a compressor’s output is not
  stable across zlib builds (zlib-ng differs), and the texture is part of the
  scene contract.

A scene whose pack sets none of these compiles byte-identically to before.
Nothing here runs without a treatment, and the new wire fields are omitted
when unset.

### Module Attributes

| [`UNDERLAY_KINDS`](#an.stage.surface.UNDERLAY_KINDS)   | The visual kinds a copy can be drawn for.                                                                                                                                                                            |
|-------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`GLOW_NODE`](#an.stage.surface.GLOW_NODE)        | The glow's node name inside its entity, and the grain's on the overlay.                                                                                                                                              |
| [`GRAIN_LEVELS`](#an.stage.surface.GRAIN_LEVELS)     | Grey levels in the grain tile. 16 = a 4-bit palette PNG (half the bytes of an 8-bit one), and finer steps than 8-bit output could show at the small <br/><br/>```<br/>`<br/>```<br/><br/>amount\`s grain is used at. |

### Functions

| [`ring_offsets`](#an.stage.surface.ring_offsets)(radius)                               | The outline ring's copy offsets at `radius` pixels.                                                                    |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| [`apply_surface`](#an.stage.surface.apply_surface)(node, surface, \*, textures)         | Expand `surface` into `node` (an entity's subtree), in place.                                                          |
| [`drawn_box`](#an.stage.surface.drawn_box)(node)                                    | `(x0, y0, x1, y1)` of what `node`'s parts draw, in its own frame.                                                      |
| [`glow_svg`](#an.stage.surface.glow_svg)(width, height, \*, color, intensity, ...) | The glow's texture: an elliptical radial gradient filling its box.                                                     |
| [`grain_indices`](#an.stage.surface.grain_indices)(seed, tile)                          | `tile × tile` grey-level indices in `[0, GRAIN_LEVELS)`, row-major.                                                    |
| [`grain_greys`](#an.stage.surface.grain_greys)(amount)                                | The palette: level `n` multiplies the frame by `grey/255`, from white (level 0) down to `1 − amount` (the last level). |
| [`grain_png`](#an.stage.surface.grain_png)(\*, seed, amount, tile)                  | The grain tile as a 4-bit palette PNG: opaque and lossless.                                                            |
| [`grain_node`](#an.stage.surface.grain_node)(grain, \*, width, height, textures)     | The grain layer: one tile texture, tiled over the frame in frame pixels.                                               |
| [`faded_treated_targets`](#an.stage.surface.faded_treated_targets)(scene, animations)           | The `alpha` channel targets that FADE a part carrying underlays.                                                       |

### an.stage.surface.GLOW_NODE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '_glow'*

The glow’s node name inside its entity, and the grain’s on the overlay.
Leading underscore: no rig slot or entity id is spelled like this, and a
collision with an overlay entity still raises in `compile_shot`.

### an.stage.surface.GRAIN_LEVELS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 16*

Grey levels in the grain tile. 16 = a 4-bit palette PNG (half the bytes
of an 8-bit one), and finer steps than 8-bit output could show at the small

```
`
```

amount\`s grain is used at.

### an.stage.surface.UNDERLAY_KINDS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'ellipse', 'rect', 'svg_sprite'})*

The visual kinds a copy can be drawn for. `runtime.js` refuses any other.
An eye already draws its own rim, a procedural mouth is a redraw function,
and a path is already a line.

### an.stage.surface.apply_surface(node, surface, , textures)

Expand `surface` into `node` (an entity’s subtree), in place.

Returns what it could not do, for the compiler to warn with (a glow on an
entity that draws nothing). A no-op for `None`, which is every entity of
a scene whose pack sets no treatment. The outline and the shadow go on each part: the entity’s
direct children, and deeper parts too when the treatment is `nested`.
The glow is added after the parts are walked, so it never gets an outline
of its own.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from an.styles import SurfaceTreatment
>>> part = NodeJSON(name="torso", visual=VisualJSON(kind="rect", width=40, height=60))
>>> ent = NodeJSON(name="bob", children=[part])
>>> apply_surface(ent, SurfaceTreatment(outline={"width": 2}, shadow={}), textures={})
[]
>>> [(u.grow, u.offsets) for u in part.visual.underlays]
[(2.0, [(4.0, 4.0)]), (2.0, [(0.0, 0.0)])]
```

### an.stage.surface.drawn_box(node)

`(x0, y0, x1, y1)` of what `node`’s parts draw, in its own frame.

The entity’s own visual and every descendant’s: rest translations and each
visual’s box and anchor. Rest rotations and
scales are not applied: the compiled rigs have none below the entity
root. That is an assumption about the rigs this compiler builds, not
about arbitrary documents.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> head = NodeJSON(name="h", transform=TransformJSON(y=-50),
...                 visual=VisualJSON(kind="ellipse", width=40, height=40))
>>> drawn_box(NodeJSON(name="e", children=[head]))
(-20.0, -70.0, 20.0, -30.0)
```

### an.stage.surface.faded_treated_targets(scene, animations)

The `alpha` channel targets that FADE a part carrying underlays.

A treated part’s copies are drawn separately, so a fade shows them
through the part instead of the background (see `an.styles.Outline`).
A hide or a show is not a fade (`_fades()`), and an alpha on the glow
node only fades the glow, which is fine.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.stage.surface.glow_svg(width, height, , color, intensity, core)

The glow’s texture: an elliptical radial gradient filling its box.

It holds `intensity` out to `core` (a fraction of the radius) and
fades to nothing at the edge.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> glow_svg(10, 10, color="#ffffff", intensity=0.5, core=0.4)[:52]
'<svg xmlns="http://www.w3.org/2000/svg" width="10" h'
```

### an.stage.surface.grain_greys(amount)

The palette: level `n` multiplies the frame by `grey/255`, from
white (level 0) down to `1 − amount` (the last level).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]

```pycon
>>> grain_greys(0.06)[:3], grain_greys(0.06)[-1]
([255, 254, 253], 240)
```

### an.stage.surface.grain_indices(seed, tile)

`tile × tile` grey-level indices in `[0, GRAIN_LEVELS)`, row-major.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]

```pycon
>>> grain_indices(0, 4)
[14, 6, 0, 15, 1, 5, 2, 12, 3, 15, 6, 12, 8, 8, 11, 8]
>>> grain_indices(0, 4) == grain_indices(0, 4) != grain_indices(1, 4)
True
```

### an.stage.surface.grain_node(grain, , width, height, textures)

The grain layer: one tile texture, tiled over the frame in frame pixels.

It goes on the OVERLAY, which is centred on the canvas and cannot be
reached by the camera. Each tile sits at an integer frame position at
scale 1, so at `supersample` 1 a texel is exactly one pixel. Tiling is
done with nodes rather than a `TilingSprite`, which the runtime does not
wire (an#110’s rule: wire it fully or not at all).

* **Return type:**
  [`NodeJSON`](an.stage.serialize.html.md#an.stage.serialize.NodeJSON)

### an.stage.surface.grain_png(, seed, amount, tile)

The grain tile as a 4-bit palette PNG: opaque and lossless.

It is opaque on purpose. With no alpha channel there is no premultiply
step on load that could differ between engines.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.stage.surface.ring_offsets(radius)

The outline ring’s copy offsets at `radius` pixels.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

```pycon
>>> ring_offsets(2.0)[:3]
[(2.0, 0.0), (1.414214, 1.414214), (0.0, 2.0)]
>>> len(ring_offsets(3.0)) == OUTLINE_RING
True
```
