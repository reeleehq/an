"""Numbers as text: a declared subset of d3-format, for counters (an#342).

A counter text block (:class:`an.stage.text.TextDescriptor` ``counter``) shows a
number that moves; what it draws is a string, and this module is the one
statement of how the number becomes the string. The format is a **declared
mini-language, not Python's** ``str.format`` (which allows attribute access,
states no rounding and is not reproducible in a browser): one d3-format
specifier in braces, with optional literal text around it.

>>> format_number(7, "Day {d}")
'Day 7'
>>> format_number(1234567, "{,d}")
'1,234,567'
>>> format_number(21.456, "{.1f} °C")
'21.5 °C'
>>> format_number(0.256, "{.0%}")
'26%'
>>> format_number(1500, "{.2s}")
'1.5k'

The subset, and what each specifier means (d3-format's meaning, so a JavaScript
consumer can reproduce it with ``d3.format``):

========= =============================================================
``d``     an integer
``,d``    an integer with ``,`` between thousands
``.Nf``   fixed point, ``N`` decimals
``.N%``   times 100, fixed point, ``N`` decimals, then ``%``
``s``     ``N`` significant digits (``.Ns``; default 6) with an SI prefix
          (``k``, ``M``, ``G``, …, ``m``; ``µ`` and smaller are refused at
          typesetting by a face that lacks the glyph)
========= =============================================================

**Rounding is to nearest, ties to even, on the float's exact value** (Python's
own correctly rounded formatting): ``2.5`` → ``2`` and ``3.5`` → ``4`` under
``d``; ``0.125`` → ``0.12`` under ``.2f``. d3 rounds ties away from zero, so a
JavaScript reproduction must round half to even to agree on exact ties (the
frame grid rarely lands on one). Two further departures from d3's defaults,
both stated: the minus sign is ``-`` (U+002D), because the embedded face has no
U+2212, and a value that rounds to zero never carries a sign (``-0.4`` → ``0``),
which is d3's own rule.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

__all__ = [
    "CounterFormatError",
    "NumberFormat",
    "parse_format",
    "format_number",
    "DFLT_SI_PRECISION",
]

#: ``s`` with no precision: d3's default of 6 significant digits.
DFLT_SI_PRECISION: int = 6

#: SI prefixes by power of 1000, d3's table (``µ`` is U+00B5, as d3 writes it).
_SI_PREFIXES: tuple[str, ...] = (
    "y", "z", "a", "f", "p", "n", "µ", "m", "", "k", "M", "G", "T", "P", "E", "Z", "Y",
)  # fmt: skip
_SI_ZERO_INDEX: int = 8

_SPEC = re.compile(r"(?P<comma>,)?(?:\.(?P<precision>\d+))?(?P<type>[dfs%])")


class CounterFormatError(ValueError):
    """A counter ``format`` outside the declared subset."""


@dataclass(frozen=True)
class NumberFormat:
    """A parsed format: literal ``prefix``, the specifier, literal ``suffix``."""

    prefix: str
    type: str
    precision: int | None
    comma: bool
    suffix: str

    def __call__(self, value: float) -> str:
        return self.prefix + _format_spec(self, float(value)) + self.suffix


def parse_format(fmt: str) -> NumberFormat:
    """Parse ``fmt``: literal text around exactly one ``{specifier}``.

    >>> parse_format("Day {d}").prefix
    'Day '
    >>> parse_format("{.3d}")
    Traceback (most recent call last):
    ...
    an.formats.CounterFormatError: counter format '{.3d}': `d` takes no precision (it is an integer); the subset is d, ,d, .Nf, .N%, s, .Ns
    """
    subset = "the subset is d, ,d, .Nf, .N%, s, .Ns"
    if fmt.count("{") != 1 or fmt.count("}") != 1 or fmt.index("{") > fmt.index("}"):
        raise CounterFormatError(
            f"counter format {fmt!r} must hold exactly one {{specifier}} with "
            f"optional literal text around it (e.g. 'Day {{d}}'); {subset}"
        )
    prefix, _, rest = fmt.partition("{")
    spec, _, suffix = rest.partition("}")
    m = _SPEC.fullmatch(spec)
    if m is None:
        raise CounterFormatError(f"counter format {fmt!r}: {spec!r} is not in it; {subset}")
    kind, comma = m["type"], m["comma"] is not None
    precision = int(m["precision"]) if m["precision"] is not None else None
    if kind == "d" and precision is not None:
        raise CounterFormatError(
            f"counter format {fmt!r}: `d` takes no precision (it is an integer); {subset}"
        )
    if kind in ("f", "%") and precision is None:
        raise CounterFormatError(
            f"counter format {fmt!r}: `{kind}` needs a precision (`.N{kind}`); {subset}"
        )
    if comma and kind != "d":
        raise CounterFormatError(
            f"counter format {fmt!r}: `,` groups an integer (`,d`) only; {subset}"
        )
    if kind == "s" and precision == 0:
        raise CounterFormatError(
            f"counter format {fmt!r}: `s` needs at least one significant digit"
        )
    return NumberFormat(prefix, kind, precision, comma, suffix)


def format_number(value: float, fmt: str | NumberFormat) -> str:
    """``value`` drawn as ``fmt`` says (see the module docstring).

    >>> [format_number(v, "{d}") for v in (2.5, 3.5, -0.4, 29.5)]
    ['2', '4', '0', '30']
    >>> format_number(-1234.5, "{,d}")
    '-1,234'
    """
    if not math.isfinite(value):
        raise CounterFormatError(f"a counter cannot show {value!r}")
    parsed = parse_format(fmt) if isinstance(fmt, str) else fmt
    return parsed(value)


def _unsigned(text: str) -> str:
    """Drop the sign of a string that shows zero (d3's rule)."""
    if text.startswith("-") and not any(c in "123456789" for c in text):
        return text[1:]
    return text


def _format_spec(spec: NumberFormat, value: float) -> str:
    if spec.type == "d":
        return _unsigned(f"{round(value):,d}" if spec.comma else f"{round(value):d}")
    if spec.type == "f":
        return _unsigned(f"{value:.{spec.precision}f}")
    if spec.type == "%":
        return _unsigned(f"{value * 100:.{spec.precision}f}") + "%"
    return _si(value, spec.precision or DFLT_SI_PRECISION)


def _si(value: float, precision: int) -> str:
    """d3's ``s``: ``precision`` significant digits, the decimal point placed by
    an SI prefix (a power of 1000 clamped to yocto..yotta)."""
    if value == 0:
        return "0" if precision == 1 else "0." + "0" * (precision - 1)
    # The digits, rounded half-even on the exact value, and the exponent
    # AFTER rounding (9.995 at 3 digits is 1.00e+01).
    mantissa, _, exp_text = f"{abs(value):.{precision - 1}e}".partition("e")
    digits, exponent = mantissa.replace(".", ""), int(exp_text)
    k = max(-_SI_ZERO_INDEX, min(_SI_ZERO_INDEX, math.floor(exponent / 3)))
    i = exponent - 3 * k + 1  # digits before the decimal point
    n = len(digits)
    if i >= n:
        body = digits + "0" * (i - n)
    elif i > 0:
        body = digits[:i] + "." + digits[i:]
    else:
        body = "0." + "0" * (-i) + digits
    sign = "-" if value < 0 else ""
    return _unsigned(sign + body) + _SI_PREFIXES[_SI_ZERO_INDEX + k]
