"""The GIF sink: ONE palette recipe, for flat 2D art.

The recipe the demo gallery has shipped since it existed, moved here from
``misc/demos/build_demos.py`` (an#247) so there is one copy of it: the clip's
own palette (``palettegen``), applied with **no dithering**, at a reduced rate
and width, with nearest-neighbour scaling. The same lessons were learned three
times across the fleet (``walkthru``'s palette graph, ``previz``'s ``gifenc``
sink); this is ``an``'s copy, and the only one in this repository.

- ``dither=none`` -- dithering a flat fill invents texture that is not in the
  render.
- a limited palette -- these frames genuinely hold few colours.
- 12 fps rather than the render's 24 -- a GIF stores whole frames, so halving
  the rate halves the file; nothing in a short clip at gallery size moves fast
  enough for the drop to read. Keep the mp4 beside it for the full rate.

>>> gif_filter()
'fps=12,scale=480:-1:flags=neighbor,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=none'
>>> gif_filter(crop="200:200:0:0").startswith('crop=200:200:0:0,fps=12')
True
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from an.media.frames import DEFAULT_FRAME_PNG_PATTERN

__all__ = [
    "GIF_FPS",
    "GIF_MAX_COLOURS",
    "GIF_WIDTH",
    "gif_filter",
    "to_gif",
]

#: Output rate. See the module docstring for why it is half the render's.
GIF_FPS: int = 12
#: Output width in pixels; the height follows the aspect ratio.
GIF_WIDTH: int = 480
#: Palette size. Flat art holds few colours; more buys nothing visible.
GIF_MAX_COLOURS: int = 128


def gif_filter(
    *,
    crop: str = "",
    fps: int = GIF_FPS,
    width: int = GIF_WIDTH,
    max_colours: int = GIF_MAX_COLOURS,
) -> str:
    """The ffmpeg filter graph of the recipe. ``crop`` is an ffmpeg ``crop`` expression."""
    crop_clause = f"crop={crop}," if crop else ""
    return (
        f"{crop_clause}fps={fps},scale={width}:-1:flags=neighbor"
        f",split[a][b];"
        f"[a]palettegen=max_colors={max_colours}[p];[b][p]paletteuse=dither=none"
    )


def to_gif(
    source: Path,
    gif: Path,
    *,
    crop: str = "",
    source_fps: float | None = None,
    fps: int = GIF_FPS,
    width: int = GIF_WIDTH,
    max_colours: int = GIF_MAX_COLOURS,
) -> Path:
    """``source`` -> GIF with a palette generated from the clip's own colours.

    ``source`` is a video file (an mp4 the renderer delivered) or a frame
    DIRECTORY (:mod:`an.media.frames`), in which case ``source_fps`` -- the
    rate the frames were rendered at -- is required.
    """
    source, gif = Path(source), Path(gif)
    if source.is_dir():
        if source_fps is None:
            raise ValueError(
                "a frame directory has no rate of its own; pass source_fps= "
                "(the rate the frames were rendered at)"
            )
        inputs = ["-framerate", str(source_fps), "-i", str(source / DEFAULT_FRAME_PNG_PATTERN)]
    else:
        inputs = ["-i", str(source)]
    vf = gif_filter(crop=crop, fps=fps, width=width, max_colours=max_colours)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *inputs, "-vf", vf, str(gif)],
        check=True,
    )
    return gif
