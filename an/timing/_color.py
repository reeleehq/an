"""Colour parsing, formatting and mixing for the ``color`` field kind.

Accepted values: ``#rgb``, ``#rgba``, ``#rrggbb``, ``#rrggbbaa``, or a list
``[r, g, b]`` / ``[r, g, b, a]`` of sRGB-encoded channels in ``0..1``. OKLab is
Björn Ottosson's (2020); CSS Color 4 makes it the default interpolation space and
interpolates with premultiplied alpha, which ``mix_oklab`` follows. The
coefficients and the formatting rule are the timing contract's (the same numbers
the TypeScript kernel uses), so a colour mixes to the same bytes in both.

>>> parse_color("#f00")
(1.0, 0.0, 0.0, 1.0)
>>> format_color((1.0, 0.5, 0.0, 1.0), "#000000")
'#ff8000'
>>> format_color((1.0, 0.5, 0.0, 0.5), [0, 0, 0])
[1.0, 0.5, 0.0, 0.5]
"""

from __future__ import annotations

import math
import re
from typing import Any

Rgba = tuple[float, float, float, float]

_HEX = re.compile(r"^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$", re.IGNORECASE)
BYTE = 255
SRGB_KNEE = 0.04045
LINEAR_KNEE = 0.0031308
SRGB_SLOPE = 12.92
SRGB_GAMMA = 2.4
SRGB_OFFSET = 0.055


def _cbrt(x: float) -> float:
    """``math.cbrt`` (3.11+), with the same sign rule on older Pythons."""
    cbrt = getattr(math, "cbrt", None)
    if cbrt is not None:
        return cbrt(x)
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


def color_problem(value: Any) -> str | None:
    """Why ``value`` is not a colour, or ``None`` when it is one."""
    if isinstance(value, str):
        if _HEX.match(value):
            return None
        return f'"{value}" is not a hex colour (#rgb, #rgba, #rrggbb or #rrggbbaa)'
    if isinstance(value, (list, tuple)):
        if len(value) not in (3, 4):
            return f"a colour array has 3 or 4 channels, got {len(value)}"
        ok = all(
            isinstance(c, (int, float))
            and not isinstance(c, bool)
            and math.isfinite(c)
            and 0 <= c <= 1
            for c in value
        )
        return (
            None
            if ok
            else f"colour array channels are numbers in 0..1, got {list(value)}"
        )
    return f"expected a hex string or an [r, g, b, a?] array, got {value!r}"


def parse_color(value: Any) -> Rgba:
    """``value`` as sRGB-encoded ``(r, g, b, a)`` in ``0..1``."""
    problem = color_problem(value)
    if problem:
        raise ValueError(problem)
    if isinstance(value, (list, tuple)):
        r, g, b, *rest = (float(c) for c in value)
        return (r, g, b, rest[0] if rest else 1.0)
    digits = value[1:]
    if len(digits) <= 4:
        digits = "".join(c + c for c in digits)

    def byte(i: int) -> float:
        return int(digits[2 * i : 2 * i + 2], 16) / BYTE

    return (byte(0), byte(1), byte(2), byte(3) if len(digits) == 8 else 1.0)


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _js_round(x: float) -> int:
    """JavaScript's ``Math.round`` (half rounds UP), not Python's banker's round."""
    return math.floor(x + 0.5)


def format_color(rgba: Rgba, like: Any) -> Any:
    """``rgba`` written in the form of ``like``: hex (bytes, alpha digits only when
    alpha < 1) or a list (three channels only when ``like`` has three and alpha is 1)."""
    c = tuple(_clamp01(x) for x in rgba)
    if isinstance(like, (list, tuple)):
        return [c[0], c[1], c[2]] if len(like) == 3 and c[3] == 1 else list(c)

    def hex2(x: float) -> str:
        return format(_js_round(x * BYTE), "02x")

    return "#" + hex2(c[0]) + hex2(c[1]) + hex2(c[2]) + (hex2(c[3]) if c[3] < 1 else "")


def _to_linear(c: float) -> float:
    if c <= SRGB_KNEE:
        return c / SRGB_SLOPE
    return ((c + SRGB_OFFSET) / (1 + SRGB_OFFSET)) ** SRGB_GAMMA


def _from_linear(c: float) -> float:
    if c <= LINEAR_KNEE:
        return SRGB_SLOPE * c
    return (1 + SRGB_OFFSET) * math.copysign(
        abs(c) ** (1 / SRGB_GAMMA), c
    ) - SRGB_OFFSET


def srgb_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    lr, lg, lb = _to_linear(r), _to_linear(g), _to_linear(b)
    l_ = _cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb)
    m_ = _cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb)
    s_ = _cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb)
    return (
        0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_,
    )


def oklab_to_srgb(L: float, a: float, b: float) -> tuple[float, float, float]:
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
    return (
        _from_linear(4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_),
        _from_linear(-1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_),
        _from_linear(-0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_),
    )


def mix_oklab(src: Rgba, dst: Rgba, u: float) -> Rgba:
    """Mix two colours at ``u`` in OKLab with premultiplied alpha, clamped to sRGB."""
    la = tuple(x * src[3] for x in srgb_to_oklab(*src[:3]))
    lb = tuple(x * dst[3] for x in srgb_to_oklab(*dst[:3]))
    alpha = src[3] + (dst[3] - src[3]) * u
    if alpha <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    lab = tuple((x + (y - x) * u) / alpha for x, y in zip(la, lb))
    r, g, b = oklab_to_srgb(*lab)
    return (_clamp01(r), _clamp01(g), _clamp01(b), _clamp01(alpha))


def mix_srgb(src: Rgba, dst: Rgba, u: float) -> Rgba:
    """Mix two colours at ``u`` componentwise on the sRGB-ENCODED channels and
    straight alpha (what Manim does, and what `an`'s three tint scalars do)."""
    return tuple(_clamp01(x + (y - x) * u) for x, y in zip(src, dst))  # type: ignore[return-value]
