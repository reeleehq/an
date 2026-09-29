"""Stroked paths: routes, invasion arrows, borders, timelines, connectors.

One drawable covers the whole map-and-infographic motif family (epic #9,
Wave 9; an#160): a stroke along a polyline or a chain of cubic Béziers, with an
animatable **trim** — the visible span, as fractions of arc length — and an
optional **arrowhead** that rides the moving tip, oriented along the path.

>>> arrow = PathDescriptor(
...     name="route",
...     points=[(-300.0, 0.0), (0.0, 0.0), (0.0, 200.0)],
...     arrowhead=True,
... )
>>> arrow.kind, arrow.curve, arrow.trim_end
('PathDescriptor', 'polyline', 1.0)
>>> arrow.head_length_px, arrow.head_width_px  # defaults scale with the stroke
(28.0, 24.0)

**Where it lives, and why there.** A path is a prop — a drawable that is not a
person — so its document sits in the ``props`` store beside
:class:`an.props.PropDescriptor` and a scene names it with an ordinary
``AssetRef(kind="prop", ...)``. The compiler dispatches on the document's
``kind``. That keeps the scene IR unchanged (no field, no migration) and gives
a path stage placement (``at``, ``scale``) and entity ordering for free.

Geometry is often per-shot (the same arrow style, a different route), so an
entity's ``overrides`` are merged over the stored document and the result is
validated **strictly** — :func:`resolve_path` is the one place that happens,
and both the compiler and ``an validate`` call it, so their verdicts agree.

**Trim is an ordinary property.** ``trim_start`` / ``trim_end`` are numeric
node properties in :data:`an.base.TRANSFORM_PROPERTIES`, animated by ordinary
``set``/``tween`` actions and flattened to the canonical timeline like
``alpha``: ``tween route trim_end 0 -> 1`` is a draw-on. The fields below are
only the values the path shows before anything animates it.

Why a separate document rather than a ``PropDescriptor`` field: a
``PropDescriptor`` is a *rig* (bones, slots, skins, swap sets) whose art is
SVG; a path has none of those, and its colour is decided by the compiler
(which is what will let a :class:`an.styles.StylePack` reach it), not by art.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from an.ir.assets import AssetSource
from an.ir.migrate import DocumentKind, migrate, register_kind

__all__ = [
    "PATH_SCHEMA_VERSION",
    "PATH_DOCUMENT_KIND",
    "PathDescriptor",
    "resolve_path",
    "DFLT_STROKE_COLOUR",
]

PATH_SCHEMA_VERSION = "0.1.0"

#: Its own versioned document kind, registered from the module that owns the
#: schema — the rule `PropDescriptor` and `CharacterDescriptor` follow.
PATH_DOCUMENT_KIND: DocumentKind = register_kind(
    DocumentKind(
        name="PathDescriptor",
        version_field="schema_version",
        current_version=PATH_SCHEMA_VERSION,
    )
)

#: The stroke colour when the document names none.
#:
#: Not yet a `StylePack` role: `an.styles.REACHABLE_ROLES` is a closed set, and
#: every role in it is asserted to reach a compiled document from one fixed
#: scene (`tests/test_styles.py`). A `stroke` role is a small follow-up, not a
#: field that silently does nothing today.
DFLT_STROKE_COLOUR: str = "#c0392b"

#: Default stroke width, scene pixels.
DFLT_STROKE_WIDTH: float = 8.0

#: Arrowhead length and width as multiples of the stroke width, when the
#: document does not give them in pixels.
DFLT_HEAD_LENGTH_FACTOR: float = 3.5
DFLT_HEAD_WIDTH_FACTOR: float = 3.0

#: Straight segments each cubic Bézier is flattened into, uniformly in its
#: parameter. The wire carries only the flattened polyline, so this is the one
#: knob between a curve and what the runtime draws.
DFLT_SAMPLES_PER_CUBIC: int = 24

_HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")

class PathDescriptor(BaseModel):
    """The on-disk path schema, saved as a prop's ``prop.json``.

    ``extra="forbid"``, unlike the store documents around it: a path is a
    precise drawing instruction, and a misspelt ``trim_ends`` that silently
    did nothing is the defect class this package refuses (the `Plane`
    precedent, an#110).

    ``curve="cubic"`` reads ``points`` as chained cubic Béziers,
    ``p0 c1 c2 p1 c1 c2 p2 ...`` — ``3n + 1`` points, the SVG ``C`` command
    chained:

    >>> PathDescriptor(name="s", curve="cubic", points=[(0, 0), (1, 1), (2, 1), (3, 0)]).curve
    'cubic'
    >>> PathDescriptor(name="s", curve="cubic", points=[(0, 0), (1, 1), (3, 0)])
    Traceback (most recent call last):
    ...
    pydantic_core._pydantic_core.ValidationError: 1 validation error for PathDescriptor
      Value error, a cubic path takes 3n + 1 points (p0, then c1 c2 p per segment); got 3 [type=value_error, input_value=..., input_type=dict]
    ...
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["PathDescriptor"] = "PathDescriptor"
    schema_version: str = PATH_SCHEMA_VERSION
    name: str
    #: Scene pixels, relative to the node's origin (``AssetRef.stage.at``).
    points: list[tuple[float, float]] = Field(min_length=2)
    curve: Literal["polyline", "cubic"] = "polyline"
    samples_per_segment: int = Field(default=DFLT_SAMPLES_PER_CUBIC, ge=1, le=512)
    #: ``#rrggbb``.
    color: str = DFLT_STROKE_COLOUR
    width: float = Field(default=DFLT_STROKE_WIDTH, gt=0, allow_inf_nan=False)
    cap: Literal["round", "butt", "square"] = "round"
    join: Literal["round", "miter", "bevel"] = "round"
    #: The visible span before anything animates it, as fractions of arc
    #: length. ``trim_end=0`` starts a draw-on hidden.
    trim_start: float = Field(default=0.0, ge=0.0, le=1.0)
    trim_end: float = Field(default=1.0, ge=0.0, le=1.0)
    arrowhead: bool = False
    #: Scene pixels; ``None`` = a multiple of ``width``.
    head_length: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    head_width: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    source: AssetSource | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("points")
    @classmethod
    def _finite_points(cls, points):
        for x, y in points:
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f"path points must be finite; got {(x, y)!r}")
        return points

    @field_validator("color")
    @classmethod
    def _hex(cls, color):
        if not _HEX_COLOUR.fullmatch(color):
            raise ValueError(f"`color` takes a #rrggbb string; got {color!r}")
        return color

    @model_validator(mode="after")
    def _cubic_arity(self) -> "PathDescriptor":
        if self.curve == "cubic" and (len(self.points) - 1) % 3:
            raise ValueError(
                "a cubic path takes 3n + 1 points (p0, then c1 c2 p per "
                f"segment); got {len(self.points)}"
            )
        return self

    @property
    def head_length_px(self) -> float:
        """The arrowhead's length in scene pixels."""
        if self.head_length is not None:
            return float(self.head_length)
        return DFLT_HEAD_LENGTH_FACTOR * self.width

    @property
    def head_width_px(self) -> float:
        """The arrowhead's base width in scene pixels."""
        if self.head_width is not None:
            return float(self.head_width)
        return DFLT_HEAD_WIDTH_FACTOR * self.width


def resolve_path(
    document: Mapping[str, Any], overrides: Mapping[str, Any] | None = None
) -> PathDescriptor:
    """The path an entity draws: its stored document with ``overrides`` on top.

    Validated strictly after the merge, so an override key the schema does not
    know raises instead of vanishing (an environment override silently drops
    unknown keys; a path's does not).

    >>> doc = {"kind": "PathDescriptor", "name": "a", "points": [[0, 0], [10, 0]]}
    >>> resolve_path(doc, {"points": [[0, 0], [0, 50]]}).points
    [(0.0, 0.0), (0.0, 50.0)]
    >>> resolve_path(doc, {"colour": "#000000"})
    Traceback (most recent call last):
    ...
    pydantic_core._pydantic_core.ValidationError: 1 validation error for PathDescriptor
    colour
      Extra inputs are not permitted [type=extra_forbidden, input_value='#000000', input_type=str]
    ...
    """
    stored = migrate(dict(document), kind=PATH_DOCUMENT_KIND.name)
    merged = {**stored, **dict(overrides or {})}
    return PathDescriptor.model_validate(merged)
