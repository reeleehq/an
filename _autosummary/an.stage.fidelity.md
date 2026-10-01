# an.stage.fidelity

How faithfully a compiled scene reproduces the art it was built from.

Wave 4’s instrument (#9, `misc/docs/wave4_research.md` §2). One number per
sprite: the **aspect distortion**, the factor by which the compiler’s box
disagrees with the art’s own raster about shape.

## Why this and not a rendered bounding box

The obvious instrument — render a frame, find the part’s ink, measure its
extents — does not work. Measured on the repo’s own art, the same `arm_l`
render is 2, 4, 6 or 8 px wide depending only on the anti-aliasing threshold
chosen, so any tolerance asserted against it is really an assertion about a
threshold. The scale ratio below is exact, threshold-free, needs no browser and
no render at all, and reads straight off the two numbers that actually decide
the shape.

## What it measures

`makeSvgSprite` sets `sprite.width` and `sprite.height` independently
(`runtime.js:164-165`); PixiJS turns each into an independent axis scale.
So the sprite’s two scale factors are

> sx = box_width  / raster_width
> sy = box_height / raster_height

and the art keeps its shape exactly when `sx == sy`.
[`PartFidelity.aspect_distortion`](#an.stage.fidelity.PartFidelity.aspect_distortion) is `max(sx, sy) / min(sx, sy)` — 1.0
when the art is respected, and the factor by which it is squashed otherwise.

\*\*The invariant this exists to enforce: aspect ratio is intrinsic to the art,
and the compiler may never override it.\*\* A part is placed and uniformly
scaled, never stretched to fit a box.

### Module Attributes

| [`DFLT_ASPECT_TOLERANCE`](#an.stage.fidelity.DFLT_ASPECT_TOLERANCE)   | Ratios within this of 1.0 count as uniform.                                 |
|--------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`SPRITE_KIND`](#an.stage.fidelity.SPRITE_KIND)             | The visual kind whose art comes from a file and can therefore be distorted. |
| [`CONTAIN_FIT`](#an.stage.fidelity.CONTAIN_FIT)             | Fit policies, mirroring `VisualJSON.fit`.                                   |

### Functions

| [`aspect_findings`](#an.stage.fidelity.aspect_findings)(scene, \*, asset_root[, ...])     | Report each non-uniformly scaled sprite as a typed `Finding`.          |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`part_fidelity`](#an.stage.fidelity.part_fidelity)(scene, \*, asset_root[, tolerance]) | Measure every `svg_sprite` in a compiled scene against its source art. |

### Classes

| [`PartFidelity`](#an.stage.fidelity.PartFidelity)(node_path, asset_id, src, box, ...)   | One sprite's box, its art's raster, and the disagreement between them.   |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|

### an.stage.fidelity.CONTAIN_FIT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'contain'*

Fit policies, mirroring `VisualJSON.fit`.

### an.stage.fidelity.DFLT_ASPECT_TOLERANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1.000001*

Ratios within this of 1.0 count as uniform. Guards float noise only — it is
not a tolerance for “close enough”, which is why it is this tight.

### *class* an.stage.fidelity.PartFidelity(node_path, asset_id, src, box, raster, fit='stretch')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One sprite’s box, its art’s raster, and the disagreement between them.

#### *property* aspect_distortion *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The factor by which the art is actually reshaped on screen.

**The fit policy is what decides this, not the box.** Under
`contain` the runtime scales both axes by one factor, so the art
keeps its shape whatever the box says and this is 1.0. Under
`stretch` the box wins on both axes and the disagreement is the
distortion.

#### *property* box_aspect_disagreement *: [float](https://docs.python.org/3/builtins/functions.html#float)*

How far the box’s shape is from the art’s. 1.0 when they agree.

Pure geometry, independent of the fit policy. Under `contain` this is
*slack* — the art still keeps its shape and the box is simply roomier on
one axis — so it is a weaker signal than [`aspect_distortion`](#an.stage.fidelity.PartFidelity.aspect_distortion), but
it is what tells you the compiler is sizing from the art rather than
from a constant.

### an.stage.fidelity.SPRITE_KIND *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'svg_sprite'*

The visual kind whose art comes from a file and can therefore be distorted.

### an.stage.fidelity.aspect_findings(scene, , asset_root, severity='error', tolerance=1.000001)

Report each non-uniformly scaled sprite as a typed `Finding`.

Uses the existing finding type so the orchestrator’s error routing applies,
and sets `ir_path` to the scene-graph node path so a fix is routed to the
part that needs it.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Finding`](an.verify.md#an.verify.Finding)]

### an.stage.fidelity.part_fidelity(scene, , asset_root, tolerance=1.000001)

Measure every `svg_sprite` in a compiled scene against its source art.

`asset_root` is the directory a texture’s `src` is relative to — the
staged runtime directory, or the mall’s characters-store root with the
`characters/` prefix retained.

Sprites whose art cannot be read are skipped rather than guessed at; a
missing part is #76’s problem, not this function’s.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`PartFidelity`](#an.stage.fidelity.PartFidelity)]
