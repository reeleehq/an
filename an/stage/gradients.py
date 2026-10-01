"""Gradient fills on the stage: a :class:`~an.paint.Gradient` drawn as an inline SVG texture.

The stage draws a gradient the way it already draws a glow (an#163): as ordinary
document content -- a ``data:`` SVG texture under a content-addressed alias,
on an ``svg_sprite`` visual -- not as a runtime feature. So ``runtime.js`` does
not change, staging skips the inline source, and the bytes of the texture are a
pure function of the gradient and its box.

Two boxes matter:

- the **box** the sprite covers (a plane's declared ``size``, or the fill span
  that covers the canvas at any camera position), and
- the **frame** the gradient is laid out over (the declared ``size``, or the
  canvas): a gradient without a declared size is shaped by what the camera
  shows, and beyond the frame its end colours hold (SVG's ``spreadMethod``
  ``pad``, CSS's behaviour), so a pan never runs off the edge of the paint.

The SVG is rasterised at most :data:`GRADIENT_RASTER_MAX` pixels on its longer
side and stretched to the box -- a smooth ramp loses nothing to that, and a
4000-pixel backdrop does not cost a 64 MB texture.

>>> from an.paint import Gradient
>>> svg = gradient_svg(Gradient(stops=["#000", "#fff"]), box=(100.0, 50.0), frame=(100.0, 50.0))
>>> svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"')
True
>>> 'x1="50" y1="0" x2="50" y2="50"' in svg  # CSS's default: top to bottom
True
"""

from __future__ import annotations

import base64
import hashlib
import math

from an.paint import Gradient, rgba_of

__all__ = ["GRADIENT_RASTER_MAX", "gradient_svg", "gradient_src", "gradient_alias"]

#: The longest side, in texture pixels, a gradient is rasterised at.
GRADIENT_RASTER_MAX: int = 1024
#: Decimals written into the SVG (coordinates are scene pixels).
SVG_DECIMALS: int = 4
#: Hex digits of the content digest in a gradient texture's alias.
ALIAS_DIGEST_LEN: int = 12


def _fmt(x: float) -> str:
    text = f"{x:.{SVG_DECIMALS}f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _hex6(rgba: tuple[float, float, float, float]) -> str:
    return "#" + "".join(f"{math.floor(c * 255 + 0.5):02x}" for c in rgba[:3])


def _stops(gradient: Gradient) -> str:
    out = []
    for stop in gradient.stops:
        rgba = rgba_of(stop.color)
        opacity = "" if rgba[3] >= 1 else f' stop-opacity="{_fmt(rgba[3])}"'
        out.append(
            f'<stop offset="{_fmt(stop.offset)}" stop-color="{_hex6(rgba)}"{opacity}/>'
        )
    return "".join(out)


def gradient_svg(
    gradient: Gradient,
    *,
    box: tuple[float, float],
    frame: tuple[float, float],
    raster_max: int = GRADIENT_RASTER_MAX,
) -> str:
    """The SVG that paints ``gradient`` over ``box``, laid out on the centred ``frame``.

    Coordinates are scene pixels (the ``viewBox``); ``width``/``height`` are the
    raster size, at most ``raster_max`` on the longer side.

    >>> from an.paint import Gradient
    >>> svg = gradient_svg(Gradient(type="radial", stops=["#fff", "#000"]),
    ...                    box=(4000.0, 4000.0), frame=(1920.0, 1080.0))
    >>> 'width="1024" height="1024"' in svg
    True
    >>> 'gradientTransform="translate(2000 2000) scale(960 540)"' in svg
    True
    """
    bw, bh = box
    fw, fh = frame
    k = min(1.0, raster_max / max(bw, bh))
    width, height = max(1, math.ceil(bw * k)), max(1, math.ceil(bh * k))
    cx, cy = bw / 2, bh / 2
    if gradient.type == "linear":
        theta = math.radians(gradient.angle)
        dx, dy = math.sin(theta), -math.cos(theta)
        half = (abs(fw * dx) + abs(fh * dy)) / 2
        paint = (
            '<linearGradient id="g" gradientUnits="userSpaceOnUse" '
            f'x1="{_fmt(cx - dx * half)}" y1="{_fmt(cy - dy * half)}" '
            f'x2="{_fmt(cx + dx * half)}" y2="{_fmt(cy + dy * half)}">'
            f"{_stops(gradient)}</linearGradient>"
        )
    else:
        gx = (bw - fw) / 2 + gradient.center[0] * fw
        gy = (bh - fh) / 2 + gradient.center[1] * fh
        paint = (
            '<radialGradient id="g" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="1" '
            f'gradientTransform="translate({_fmt(gx)} {_fmt(gy)}) '
            f'scale({_fmt(gradient.radius * fw)} {_fmt(gradient.radius * fh)})">'
            f"{_stops(gradient)}</radialGradient>"
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {_fmt(bw)} {_fmt(bh)}" preserveAspectRatio="none">'
        f'<defs>{paint}</defs><rect width="{_fmt(bw)}" height="{_fmt(bh)}" '
        'fill="url(#g)"/></svg>'
    )


def gradient_src(svg: str) -> str:
    """``svg`` as the inline (``data:``) texture source the runtime loads."""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode(
        "ascii"
    )


def gradient_alias(prefix: str, src: str) -> str:
    """A content-addressed texture alias: the same gradient, the same alias.

    >>> gradient_alias("glass.sky", "data:x") == gradient_alias("glass.sky", "data:x")
    True
    """
    digest = hashlib.sha256(src.encode("ascii")).hexdigest()[:ALIAS_DIGEST_LEN]
    return f"{prefix}.{digest}"
