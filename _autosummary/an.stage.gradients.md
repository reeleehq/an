# an.stage.gradients

Gradient fills on the stage: a [`Gradient`](an.paint.md#an.paint.Gradient) drawn as an inline SVG texture.

The stage draws a gradient the way it already draws a glow (an#163): as ordinary
document content – a `data:` SVG texture under a content-addressed alias,
on an `svg_sprite` visual – not as a runtime feature. So `runtime.js` does
not change, staging skips the inline source, and the bytes of the texture are a
pure function of the gradient and its box.

Two boxes matter:

- the **box** the sprite covers (a plane’s declared `size`, or the fill span
  that covers the canvas at any camera position), and
- the **frame** the gradient is laid out over (the declared `size`, or the
  canvas): a gradient without a declared size is shaped by what the camera
  shows, and beyond the frame its end colours hold (SVG’s `spreadMethod`
  `pad`, CSS’s behaviour), so a pan never runs off the edge of the paint.

The SVG is rasterised at most [`GRADIENT_RASTER_MAX`](#an.stage.gradients.GRADIENT_RASTER_MAX) pixels on its longer
side and stretched to the box – a smooth ramp loses nothing to that, and a
4000-pixel backdrop does not cost a 64 MB texture.

```pycon
>>> from an.paint import Gradient
>>> svg = gradient_svg(Gradient(stops=["#000", "#fff"]), box=(100.0, 50.0), frame=(100.0, 50.0))
>>> svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"')
True
>>> 'x1="50" y1="0" x2="50" y2="50"' in svg  # CSS's default: top to bottom
True
```

### Module Attributes

| [`GRADIENT_RASTER_MAX`](#an.stage.gradients.GRADIENT_RASTER_MAX)   | The longest side, in texture pixels, a gradient is rasterised at.   |
|------------------------------------------------------------------------|---------------------------------------------------------------------|

### Functions

| [`gradient_svg`](#an.stage.gradients.gradient_svg)(gradient, \*, box, frame[, ...])   | The SVG that paints `gradient` over `box`, laid out on the centred `frame`.   |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`gradient_src`](#an.stage.gradients.gradient_src)(svg)                               | `svg` as the inline (`data:`) texture source the runtime loads.               |
| [`gradient_alias`](#an.stage.gradients.gradient_alias)(prefix, src)                     | A content-addressed texture alias: the same gradient, the same alias.         |

### an.stage.gradients.GRADIENT_RASTER_MAX *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1024*

The longest side, in texture pixels, a gradient is rasterised at.

### an.stage.gradients.gradient_alias(prefix, src)

A content-addressed texture alias: the same gradient, the same alias.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> gradient_alias("glass.sky", "data:x") == gradient_alias("glass.sky", "data:x")
True
```

### an.stage.gradients.gradient_src(svg)

`svg` as the inline (`data:`) texture source the runtime loads.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.stage.gradients.gradient_svg(gradient, , box, frame, raster_max=1024)

The SVG that paints `gradient` over `box`, laid out on the centred `frame`.

Coordinates are scene pixels (the `viewBox`); `width`/`height` are the
raster size, at most `raster_max` on the longer side.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> from an.paint import Gradient
>>> svg = gradient_svg(Gradient(type="radial", stops=["#fff", "#000"]),
...                    box=(4000.0, 4000.0), frame=(1920.0, 1080.0))
>>> 'width="1024" height="1024"' in svg
True
>>> 'gradientTransform="translate(2000 2000) scale(960 540)"' in svg
True
```
