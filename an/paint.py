"""Paint: what fills a shape when one flat colour is not enough -- a gradient.

A **gradient** blends colour **stops** (CSS's *color stops*: a colour at an
offset from 0 to 1 along the gradient) either along a line (**linear**) or
outward from a centre (**radial**). The vocabulary is CSS's
(``linear-gradient`` / ``radial-gradient``), so an author who knows one knows
the other:

- ``angle`` (linear) is the CSS gradient angle in degrees: ``0`` runs to the
  top, ``90`` to the right, ``180`` (the default) to the bottom. As in CSS the
  gradient line is as long as it must be for the box's corners to sit on the
  first and last stop.
- ``center`` and ``radius`` (radial) are fractions of the box. In a box that is
  not square the gradient is an ellipse with the box's proportions (CSS's
  ``ellipse``); ``radius: 0.5`` touches the sides of a centred box.
- Colours between stops are interpolated in sRGB, as CSS and SVG do by default;
  beyond the first and last stop the end colours hold.

Colours are hex strings (``#rgb``, ``#rgba``, ``#rrggbb``, ``#rrggbbaa``), the
representation the StylePack uses everywhere. Stops may be written as plain
colours, which are spread evenly:

>>> g = Gradient(stops=["#101030", "#f0d090"])
>>> [(s.offset, s.color) for s in g.stops]
[(0.0, '#101030'), (1.0, '#f0d090')]
>>> Gradient(type="radial", stops=["#fff", "#0000"], radius=0.75).radius
0.75

A field that would do nothing is refused rather than ignored:

>>> Gradient(type="radial", stops=["#fff", "#000"], angle=90)
Traceback (most recent call last):
...
pydantic_core._pydantic_core.ValidationError: ...

This is genre-neutral core vocabulary: a plane of the 2D stage draws one
(:class:`an.stage.environments.PlaneArt`), and a StylePack names them as
**gradient roles** (:attr:`an.styles.StylePack.gradients`).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from an.timing._color import parse_color

__all__ = ["DFLT_GRADIENT_ANGLE", "Gradient", "GradientStop", "rgba_of"]

#: CSS's default gradient direction: top to bottom.
DFLT_GRADIENT_ANGLE: float = 180.0
#: A radial gradient's default centre and radius, in fractions of its box.
DFLT_RADIAL_CENTER: tuple[float, float] = (0.5, 0.5)
DFLT_RADIAL_RADIUS: float = 0.5
#: A gradient needs at least this many stops (one stop is a flat fill).
MIN_STOPS: int = 2

_LINEAR_ONLY = ("angle",)
_RADIAL_ONLY = ("center", "radius")


def rgba_of(color: str) -> tuple[float, float, float, float]:
    """A hex colour as ``(r, g, b, a)`` in ``0..1``.

    >>> rgba_of("#ff000080")
    (1.0, 0.0, 0.0, 0.5019607843137255)
    """
    if not isinstance(color, str):
        raise ValueError(f"a gradient colour is a hex string, got {color!r}")
    return parse_color(color)


class GradientStop(BaseModel):
    """A colour at an offset along the gradient (``0`` start, ``1`` end)."""

    model_config = ConfigDict(extra="forbid")

    offset: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    color: str

    @field_validator("color")
    @classmethod
    def _hex(cls, value: str) -> str:
        rgba_of(value)
        return value


class Gradient(BaseModel):
    """A linear or radial gradient between colour stops (see the module docstring)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["linear", "radial"] = "linear"
    stops: list[GradientStop]
    #: Linear only: the CSS gradient angle, degrees (0 up, 90 right, 180 down).
    angle: float = Field(DFLT_GRADIENT_ANGLE, allow_inf_nan=False)
    #: Radial only: the centre, in fractions of the box.
    center: tuple[float, float] = DFLT_RADIAL_CENTER
    #: Radial only: the radius, in fractions of the box (an ellipse in a
    #: non-square box).
    radius: float = Field(DFLT_RADIAL_RADIUS, gt=0.0, allow_inf_nan=False)

    @field_validator("stops", mode="before")
    @classmethod
    def _spread_plain_colours(cls, value: Any) -> Any:
        """Plain colours become evenly spaced stops."""
        if not isinstance(value, list):
            return value
        if len(value) < MIN_STOPS:
            raise ValueError(
                f"a gradient needs at least {MIN_STOPS} stops, got {len(value)} "
                "(one colour is a flat fill: use `kind: fill`)"
            )
        last = len(value) - 1
        return [
            {"offset": i / last, "color": stop} if isinstance(stop, str) else stop
            for i, stop in enumerate(value)
        ]

    @model_serializer(mode="wrap")
    def _only_what_shapes_it(self, handler):
        """Dump the fields of this gradient's own type only, so a dump reads back
        (the other type's fields would be refused as doing nothing)."""
        data = handler(self)
        if isinstance(data, dict):
            for key in _RADIAL_ONLY if self.type == "linear" else _LINEAR_ONLY:
                data.pop(key, None)
        return data

    @model_validator(mode="after")
    def _coherent(self) -> "Gradient":
        offsets = [s.offset for s in self.stops]
        if offsets != sorted(offsets):
            raise ValueError(f"gradient stop offsets must not decrease, got {offsets}")
        unused = _RADIAL_ONLY if self.type == "linear" else _LINEAR_ONLY
        set_but_unused = sorted(set(unused) & self.model_fields_set)
        if set_but_unused:
            raise ValueError(
                f"{set_but_unused} do nothing on a {self.type} gradient "
                f"({'angle' if self.type == 'linear' else 'center and radius'} "
                "is what shapes it)"
            )
        return self
