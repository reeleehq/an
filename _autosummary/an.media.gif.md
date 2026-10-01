# an.media.gif

The GIF sink: ONE palette recipe, for flat 2D art.

The recipe the demo gallery has shipped since it existed, moved here from
`misc/demos/build_demos.py` (an#247) so there is one copy of it: the clip’s
own palette (`palettegen`), applied with **no dithering**, at a reduced rate
and width, with nearest-neighbour scaling. The same lessons were learned three
times across the fleet (`walkthru`’s palette graph, `previz`’s `gifenc`
sink); this is `an`’s copy, and the only one in this repository.

- `dither=none` – dithering a flat fill invents texture that is not in the
  render.
- a limited palette – these frames genuinely hold few colours.
- 12 fps rather than the render’s 24 – a GIF stores whole frames, so halving
  the rate halves the file; nothing in a short clip at gallery size moves fast
  enough for the drop to read. Keep the mp4 beside it for the full rate.

```pycon
>>> gif_filter()
'fps=12,scale=480:-1:flags=neighbor,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=none'
>>> gif_filter(crop="200:200:0:0").startswith('crop=200:200:0:0,fps=12')
True
```

### Module Attributes

| [`GIF_FPS`](#an.media.gif.GIF_FPS)         | Output rate.                                                 |
|------------------------------------------------------------------|--------------------------------------------------------------|
| [`GIF_WIDTH`](#an.media.gif.GIF_WIDTH)       | Output width in pixels; the height follows the aspect ratio. |
| [`GIF_MAX_COLOURS`](#an.media.gif.GIF_MAX_COLOURS) | Palette size.                                                |

### Functions

| [`gif_filter`](#an.media.gif.gif_filter)(\*[, crop, fps, width, max_colours])   | The ffmpeg filter graph of the recipe.                                |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`to_gif`](#an.media.gif.to_gif)(source, gif, \*[, crop, source_fps, ...])  | `source` -> GIF with a palette generated from the clip's own colours. |

### an.media.gif.GIF_FPS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 12*

Output rate. See the module docstring for why it is half the render’s.

### an.media.gif.GIF_MAX_COLOURS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 128*

Palette size. Flat art holds few colours; more buys nothing visible.

### an.media.gif.GIF_WIDTH *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 480*

Output width in pixels; the height follows the aspect ratio.

### an.media.gif.gif_filter(, crop='', fps=12, width=480, max_colours=128)

The ffmpeg filter graph of the recipe. `crop` is an ffmpeg `crop` expression.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.media.gif.to_gif(source, gif, , crop='', source_fps=None, fps=12, width=480, max_colours=128)

`source` -> GIF with a palette generated from the clip’s own colours.

`source` is a video file (an mp4 the renderer delivered) or a frame
DIRECTORY ([`an.media.frames`](an.media.frames.md#module-an.media.frames)), in which case `source_fps` – the
rate the frames were rendered at – is required.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
