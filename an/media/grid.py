"""Tile images into one contact sheet: :func:`tile` (an#347).

A small pure function over PNG bytes — decoded and encoded by
:mod:`an.bench.png` (numpy and the standard library), each image fitted into a
square cell without distortion, an optional caption under each. ``an probe``
tiles several instants of a shot with it and ``an library sheet`` one specimen
per asset.

Candidate fleet component: one production wrote three ad hoc copies of this
before it existed (design of an#331, §5.3).

>>> from an.bench.png import decode_png, encode_png
>>> import numpy as np
>>> red = encode_png(np.full((4, 8, 3), (255, 0, 0), np.uint8))
>>> sheet = decode_png(tile([red, red, red], cell=16, columns=2))
>>> sheet.shape
(44, 44, 3)
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from an.bench.png import decode_png, encode_png

__all__ = ["tile", "trim", "fit_caption"]

#: The side of a square cell, in pixels.
DFLT_CELL: int = 256
#: Pixels between cells and around the sheet.
DFLT_GAP: int = 4
#: The sheet's background (RGB).
DFLT_BACKGROUND: tuple[int, int, int] = (255, 255, 255)
#: The caption strip's height, as a fraction of the cell.
CAPTION_FRACTION: float = 0.12
#: The caption colour (RGB).
CAPTION_INK: tuple[int, int, int] = (20, 20, 20)
#: How far (0-255, any channel) a pixel may differ from the background and
#: still count as background, for :func:`trim`.
DFLT_TRIM_TOLERANCE: int = 8
#: The margin :func:`trim` keeps around what it finds, as a fraction of its size.
TRIM_MARGIN: float = 0.06


def _rgb(image: np.ndarray, background: tuple[int, int, int]) -> np.ndarray:
    """``image`` as opaque RGB, any alpha composited over ``background``."""
    if image.ndim == 2:
        image = np.stack([image] * 3, axis=-1)
    if image.shape[-1] == 4:
        alpha = image[..., 3:4].astype(np.float64) / 255.0
        back = np.array(background, np.float64)
        image = image[..., :3] * alpha + back * (1.0 - alpha)
    return np.asarray(np.round(image[..., :3]), np.uint8)


def _fit(image: np.ndarray, side: int) -> np.ndarray:
    """``image`` scaled (nearest sample) to fit a ``side`` square, aspect kept."""
    h, w = image.shape[:2]
    scale = side / max(h, w)
    nh, nw = max(1, round(h * scale)), max(1, round(w * scale))
    rows = np.minimum((np.arange(nh) + 0.5) * h / nh, h - 1).astype(int)
    cols = np.minimum((np.arange(nw) + 0.5) * w / nw, w - 1).astype(int)
    return image[rows][:, cols]


def fit_caption(text: str | tuple[str, str], room: float, measure) -> str:
    """The caption that fits ``room`` (in ``measure``'s units): a long one is
    shortened with ``…``; a ``(head, tail)`` pair keeps its tail whole and
    shortens only the head (an#460), unless not even the tail fits.

    >>> fit_caption(("cutan:prop.desk-oversimplified", " [free]"), 20, len)
    'cutan:prop.d… [free]'
    >>> fit_caption("cutan:prop.desk-oversimplified [free]", 20, len)
    'cutan:prop.desk-ove…'
    """
    head, tail = text if isinstance(text, tuple) else (text, "")
    if measure(head + tail) <= room:
        return head + tail
    if measure(tail) >= room:  # not even the tail fits: shorten the whole line
        head, tail = head + tail, ""
    budget = room - measure(tail)
    while head and measure(head) > budget:
        head = head[:-2] + "…" if len(head) > 2 else ""
    return head + tail


def _caption(
    text: str | tuple[str, str], width: int, height: int, background
) -> np.ndarray:
    """``text`` drawn into a ``width`` x ``height`` strip; blank if Pillow is absent.

    A ``(head, tail)`` pair keeps its tail whole and shortens only the head
    (an#460: a sheet's licence class must survive a long reference)."""
    strip = np.empty((height, width, 3), np.uint8)
    strip[:] = background
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:  # captions are a convenience: the cells still tell the story
        return strip
    img = Image.fromarray(strip)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=max(8, int(height * 0.7)))
    except TypeError:  # Pillow < 10.1 has one fixed size
        font = ImageFont.load_default()
    shown = fit_caption(text, width - 2, lambda t: draw.textlength(t, font=font))
    draw.text((1, 0), shown, fill=CAPTION_INK, font=font)
    return np.asarray(img)


def tile(
    images: Sequence[bytes],
    *,
    cell: int = DFLT_CELL,
    columns: int | None = None,
    labels: Sequence[str | tuple[str, str]] | None = None,
    gap: int = DFLT_GAP,
    background: tuple[int, int, int] = DFLT_BACKGROUND,
) -> bytes:
    """One PNG holding every image of ``images`` (PNG bytes), each in a ``cell`` square.

    columns: cells per row (default: the smallest square grid that holds them)
    labels: one caption per image, drawn under its cell; a ``(head, tail)``
        pair is shortened in its head only, so the tail always shows
    """
    if not images:
        raise ValueError("tile() needs at least one image")
    if labels is not None and len(labels) != len(images):
        raise ValueError(f"{len(labels)} labels for {len(images)} images")
    n = len(images)
    columns = columns or int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / columns))
    strip = round(cell * CAPTION_FRACTION) if labels else 0
    pitch_x, pitch_y = cell + gap, cell + strip + gap
    sheet = np.empty((gap + rows * pitch_y, gap + columns * pitch_x, 3), np.uint8)
    sheet[:] = background
    for i, data in enumerate(images):
        r, c = divmod(i, columns)
        x0, y0 = gap + c * pitch_x, gap + r * pitch_y
        fitted = _fit(_rgb(decode_png(data), background), cell)
        h, w = fitted.shape[:2]
        oy, ox = y0 + (cell - h) // 2, x0 + (cell - w) // 2
        sheet[oy : oy + h, ox : ox + w] = fitted
        if labels:
            sheet[y0 + cell : y0 + cell + strip, x0 : x0 + cell] = _caption(
                labels[i], cell, strip, background
            )
    return encode_png(sheet)


def trim(
    image: bytes,
    *,
    tolerance: int = DFLT_TRIM_TOLERANCE,
    margin: float = TRIM_MARGIN,
) -> bytes:
    """``image`` (PNG bytes) cropped to what differs from its corner colour, plus a margin.

    An image that is all background is returned unchanged.

    >>> import numpy as np
    >>> a = np.full((20, 20, 3), 255, np.uint8); a[5:9, 10:12] = 0
    >>> decode_png(trim(encode_png(a), margin=0)).shape
    (4, 2, 3)
    """
    pixels = decode_png(image)
    rgb = pixels[..., :3].astype(np.int16)
    corner = rgb[0, 0]
    mask = (np.abs(rgb - corner) > tolerance).any(axis=-1)
    if pixels.shape[-1] == 4:
        mask |= pixels[..., 3] != pixels[0, 0, 3]
    if not mask.any():
        return image
    rows, cols = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    pad = round(margin * max(rows[-1] - rows[0] + 1, cols[-1] - cols[0] + 1))
    top, bottom = max(rows[0] - pad, 0), min(rows[-1] + 1 + pad, mask.shape[0])
    left, right = max(cols[0] - pad, 0), min(cols[-1] + 1 + pad, mask.shape[1])
    return encode_png(_rgb(pixels[top:bottom, left:right], DFLT_BACKGROUND))
