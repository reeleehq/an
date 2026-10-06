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
:class:`an.stage.props.PropDescriptor` and a scene names it with an ordinary
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

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from an.ir.assets import AssetSource
from an.ir.migrate import DocumentKind, migrate, omit_unset, register_kind

__all__ = [
    "PATH_SCHEMA_VERSION",
    "PATH_DOCUMENT_KIND",
    "PathDescriptor",
    "resolve_path",
    "drawn_polyline",
    "draw_on_through",
    "DFLT_STROKE_COLOUR",
    "MIN_DASH_PERIOD",
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

#: The stroke colour when the document names none. A `StylePack`'s `stroke`
#: role replaces it (an#161) — but only this default: a document that sets
#: `color` itself is art, not a default, and a pack does not rewrite art (the
#: same line `an.styles` draws for SVG). A per-entity `stroke` override in the
#: pack wins over both.
DFLT_STROKE_COLOUR: str = "#c0392b"

#: The shortest dash period (dash + gap), scene pixels. Bounds the number of
#: dashes a path can ask the runtime to redraw every frame: a path a few
#: thousand pixels long is a few thousand dashes at most.
MIN_DASH_PERIOD: float = 1.0

#: Default stroke width, scene pixels.
DFLT_STROKE_WIDTH: float = 8.0

#: Arrowhead length and width as multiples of the stroke width, when the
#: document does not give them in pixels.
DFLT_HEAD_LENGTH_FACTOR: float = 3.5
DFLT_HEAD_WIDTH_FACTOR: float = 3.0

#: The wobble's wavelength as a multiple of the stroke width, when the
#: document does not give it in pixels: a few stroke-widths of travel per
#: swing reads as a steady hand, not a shaky one.
DFLT_WOBBLE_WAVELENGTH_FACTOR: float = 10.0

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
    #: How a cubic's samples are spaced (an#161): ``"parameter"`` (uniform in
    #: the curve's parameter, the default) or ``"arclength"`` (evenly along it).
    sampling: Literal["parameter", "arclength"] = "parameter"
    #: ``#rrggbb``.
    color: str = DFLT_STROKE_COLOUR
    #: Stroke width, scene px. ``0`` = no stroke, only for a ``fill``ed shape
    #: (a region without a border).
    width: float = Field(default=DFLT_STROKE_WIDTH, ge=0, allow_inf_nan=False)
    #: A variable width (an#161): ``[[t, factor], ...]`` along the WHOLE path's
    #: arc length (``t`` from 0 to 1, increasing; ``factor`` times ``width``,
    #: linear between stops), so ``[[0, 1], [1, 0]]`` tapers to a point and a
    #: trim never makes the width crawl. The stroke becomes a filled shape:
    #: butt ends, mitred corners (no ``cap``/``join``).
    width_profile: list[tuple[float, float]] | None = None
    cap: Literal["round", "butt", "square"] = "round"
    join: Literal["round", "miter", "bevel"] = "round"
    #: The visible span before anything animates it, as fractions of arc
    #: length. ``trim_end=0`` starts a draw-on hidden, and a trim tween
    #: with no ``from_value`` starts from these values (not the global rest).
    trim_start: float = Field(default=0.0, ge=0.0, le=1.0)
    trim_end: float = Field(default=1.0, ge=0.0, le=1.0)
    #: A dash pattern, scene pixels: ``dash`` on, ``gap`` off, repeating along
    #: the path from ITS start — anchored to the path, not to the trimmed span,
    #: so a draw-on reveals dashes in place instead of making them crawl.
    #: ``gap`` defaults to ``dash``. ``None`` = a solid stroke.
    dash: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    gap: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    #: Shifts the pattern along the path (positive = forward). An ordinary
    #: numeric node property like ``trim_end``, so ``tween route dash_offset``
    #: is the "marching ants" route; only a dashed path has one.
    dash_offset: float = Field(default=0.0, allow_inf_nan=False)
    arrowhead: bool = False
    #: An arrowhead at the START too, pointing back along the path (an#161):
    #: with ``arrowhead``, a double-headed arrow. Same size as the end's.
    tail_arrowhead: bool = False
    #: Scene pixels; ``None`` = a multiple of ``width``.
    head_length: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    head_width: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    #: A closed shape (an#161): the path returns to its first point (a straight
    #: closing leg is added when the last point is elsewhere) and the stroke
    #: joins there instead of ending in two caps. Trim still runs from the
    #: first point round to it again.
    closed: bool = False
    #: The region a closed path encloses, ``#rrggbb``; ``None`` = unfilled.
    #: Drawn under the stroke and NOT trimmed: a draw-on draws the border and
    #: the fill is there throughout. To fade a region in separately, make it
    #: its own entity (``width: 0``, filled) and tween that node's ``alpha``.
    fill: str | None = None
    #: The fill's opacity, ``0..1``.
    fill_alpha: float = Field(default=1.0, ge=0.0, le=1.0)
    #: A hand-drawn wobble (an#161): the stroke wanders up to this many scene
    #: px either side of its line, by seeded smooth noise applied at compile
    #: (:mod:`an.stage.path_wobble`), its ends left where they are. ``0`` = a
    #: ruled line.
    wobble: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    #: The wobble's wavelength, scene px; ``None`` = a multiple of ``width``.
    wobble_wavelength: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    #: Another wobble of the same path: the noise is seeded by the entity's id
    #: and this number.
    wobble_seed: int = 0
    source: AssetSource | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def _dump_what_was_authored(self, handler):
        """Dump only the fields the author set (plus ``kind``/``schema_version``),
        so ``model_validate_json(d.model_dump_json())`` always round-trips — the
        set-but-inert checks read ``model_fields_set``, and a full dump would
        mark every default as set (:func:`an.ir.migrate.omit_unset`)."""
        return omit_unset(self, handler(self))

    @field_validator("points")
    @classmethod
    def _finite_points(cls, points):
        for x, y in points:
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f"path points must be finite; got {(x, y)!r}")
        return points

    @field_validator("fill")
    @classmethod
    def _hex_fill(cls, fill):
        if fill is not None and not _HEX_COLOUR.fullmatch(fill):
            raise ValueError(f"`fill` takes a #rrggbb string; got {fill!r}")
        return fill

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

    @model_validator(mode="after")
    def _nothing_set_is_ignored(self) -> "PathDescriptor":
        """Refuse a field that would silently do nothing — the reason this
        model is ``extra="forbid"`` applies to set-but-inert fields too.

        A field written out AT its default (``gap: null``, ``dash_offset: 0``)
        asks for nothing, so it is not refused: a document dumped by another
        tool, or by this model before it learned to omit unset fields, loads.
        """
        fields = type(self).model_fields
        given = {
            name
            for name in self.model_fields_set
            if getattr(self, name) != fields[name].default
        }
        if not (self.arrowhead or self.tail_arrowhead) and given & {
            "head_length",
            "head_width",
        }:
            raise ValueError(
                "head_length/head_width are set but arrowhead is false (and so is "
                "tail_arrowhead), so they would draw nothing; set one or drop them"
            )
        if self.dash is None and given & {"gap", "dash_offset"}:
            raise ValueError(
                "gap/dash_offset are set but `dash` is not, so the stroke is "
                "solid and they would draw nothing; set `dash` or drop them"
            )
        if self.dash is not None and self.dash + self.gap_px < MIN_DASH_PERIOD:
            raise ValueError(
                f"dash + gap = {self.dash + self.gap_px} scene px is below "
                f"{MIN_DASH_PERIOD}: that is thousands of dashes redrawn every "
                "frame and finer than a pixel"
            )
        if self.curve == "polyline" and given & {"samples_per_segment", "sampling"}:
            raise ValueError(
                "samples_per_segment (and sampling) only applies to curve='cubic'; "
                "a polyline is drawn through its points as given"
            )
        if self.fill is not None and not self.closed:
            raise ValueError(
                "`fill` is set on an open path; a fill needs a region: set "
                "`closed: true`"
            )
        if self.fill is None and given & {"fill_alpha"}:
            raise ValueError(
                "fill_alpha is set but `fill` is not, so it would draw nothing; "
                "set `fill` or drop it"
            )
        if self.fill is not None and len(set(self.points)) < 3:
            raise ValueError(
                "a filled shape needs at least three distinct points; fewer "
                "enclose no area"
            )
        if not self.width:
            if self.fill is None:
                raise ValueError(
                    "`width` is 0 and there is no `fill`, so the path would draw "
                    "nothing; give it a width or a fill"
                )
            inert = sorted(
                given & {"dash", "gap", "dash_offset", "cap", "join", "color", "trim_start", "trim_end", "width_profile"}
            ) + [n for n in ("arrowhead", "tail_arrowhead") if getattr(self, n)]
            if inert:
                raise ValueError(
                    f"{inert} draw on the stroke, and `width` is 0 (a fill with "
                    "no border); give it a width or drop them"
                )
        if self.width_profile is not None:
            _check_width_profile(self.width_profile)
            if given & {"cap", "join"}:
                raise ValueError(
                    "cap/join are set but the stroke has a `width_profile`, which "
                    "draws it as a filled shape (butt ends, mitred corners); drop them"
                )
        if not self.wobble and given & {"wobble_wavelength", "wobble_seed"}:
            raise ValueError(
                "wobble_wavelength/wobble_seed are set but `wobble` is 0, so the "
                "line is ruled and they would draw nothing; set `wobble` or drop them"
            )
        if self.wobble:
            from an.stage.path_wobble import MAX_WOBBLE_POINTS, wobble_point_count

            # The control polygon is at least as long as the curve it draws.
            reach = sum(
                math.dist(a, b) for a, b in zip(self.points, self.points[1:])
            )
            if wobble_point_count(reach, self.wobble_wavelength_px) > MAX_WOBBLE_POINTS:
                raise ValueError(
                    f"a wobble of wavelength {self.wobble_wavelength_px:g} px along "
                    f"a path up to {reach:.0f} px long is more than "
                    f"{MAX_WOBBLE_POINTS} points redrawn every frame: lengthen "
                    "`wobble_wavelength`"
                )
        if all(p == self.points[0] for p in self.points):
            raise ValueError(
                "every point of the path is the same point, so it has zero "
                "length and would draw nothing"
            )
        return self

    @property
    def gap_px(self) -> float:
        """The gap of the dash pattern, scene pixels (``dash`` when unset)."""
        if self.gap is not None:
            return float(self.gap)
        return float(self.dash) if self.dash is not None else 0.0

    @property
    def wobble_wavelength_px(self) -> float:
        """The wobble's wavelength in scene pixels."""
        if self.wobble_wavelength is not None:
            return float(self.wobble_wavelength)
        return DFLT_WOBBLE_WAVELENGTH_FACTOR * self.width

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


def _check_width_profile(profile: list[tuple[float, float]]) -> None:
    """A profile the stroke can be drawn with: stops from ``t=0`` to ``t=1``,
    strictly increasing, finite non-negative factors, not all zero.

    >>> _check_width_profile([(0.0, 1.0), (0.5, 0.0)])
    Traceback (most recent call last):
    ...
    ValueError: a width_profile runs from t=0 to t=1; got stops at [0.0, 0.5]
    """
    ts = [t for t, _ in profile]
    if len(profile) < 2 or ts[0] != 0.0 or ts[-1] != 1.0:
        raise ValueError(f"a width_profile runs from t=0 to t=1; got stops at {ts}")
    if any(not b > a for a, b in zip(ts, ts[1:])):
        raise ValueError(f"a width_profile's stops must increase strictly; got {ts}")
    factors = [f for _, f in profile]
    if any(not (math.isfinite(f) and f >= 0) for f in factors) or not any(factors):
        raise ValueError(
            "a width_profile's factors are finite, non-negative and not all zero; "
            f"got {factors}"
        )


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


def drawn_polyline(
    desc: PathDescriptor, entity_id: str
) -> tuple[list[tuple[float, float]], list[int]]:
    """The polyline the compiler puts on the wire for entity ``entity_id``
    drawing ``desc`` — flattened, closed, wobbled (the wobble is seeded by
    the entity) — and the index in it of each AUTHORED on-path point: every
    point of a polyline, ``p0 p1 p2 ...`` of a cubic chain (not its controls),
    and the closing return to the first point when ``closed`` added one.

    >>> pts, anchors = drawn_polyline(PathDescriptor(name="r", points=[(0, 0), (10, 0), (10, 10)], closed=True), "r")
    >>> pts[anchors[-1]], anchors
    ((0.0, 0.0), [0, 1, 2, 3])
    """
    from an.stage.path_geometry import flatten_curve
    from an.stage.path_wobble import wobble_with_vertices

    points = flatten_curve(
        desc.points,
        curve=desc.curve,
        samples=desc.samples_per_segment,
        sampling=desc.sampling,
    )
    step = desc.samples_per_segment if desc.curve == "cubic" else 1
    anchors = list(range(0, len(points), step))
    if desc.closed and points[-1] != points[0]:
        points.append(points[0])
        anchors.append(len(points) - 1)
    if desc.wobble:
        points, landed = wobble_with_vertices(
            points,
            amplitude=desc.wobble,
            wavelength=desc.wobble_wavelength_px,
            seed=f"{entity_id}:{desc.wobble_seed}",
        )
        anchors = [landed[i] for i in anchors]
    return points, anchors


def draw_on_through(
    entity_id: str,
    path: "PathDescriptor | Mapping[str, Any]",
    arrivals: "list[float]",
    *,
    start: float = 0.0,
    easing: Any = "ease_in_out",
) -> list:
    """A draw-on whose tip reaches each authored point at its own time (an#161).

    ``arrivals[k]`` is when the tip reaches authored point ``k + 1`` (the tip
    is at point 0, hidden, at ``start``): a route that reaches each city on a
    beat, or slows into the last turn. One ``tween`` of ``trim_end`` per leg,
    from the arc fraction of one point to the next on the polyline the
    compiler draws (:func:`drawn_polyline`, wobble included, so the tip is ON
    the point), each eased by ``easing``, preceded by a ``set`` of
    ``trim_end`` to 0 at 0. ``arrivals`` are absolute shot times, increasing.

    Returns a list of top-level actions for ``shot.actions.extend(...)``, as
    :func:`an.stage.text.reveal_units` does.

    >>> acts = draw_on_through("r", {"kind": "PathDescriptor", "name": "r",
    ...     "points": [[0, 0], [30, 0], [30, 10]]}, [1.0, 3.0])
    >>> [(a.kind, getattr(a, "to_value", getattr(a, "value", None))) for a in acts]
    [('set', 0.0), ('tween', 0.75), ('sequence', None)]
    """
    from an.ir import compose as c
    from an.stage.path_geometry import cumulative_lengths

    desc = path if isinstance(path, PathDescriptor) else resolve_path(path)
    points, anchors = drawn_polyline(desc, entity_id)
    if len(arrivals) != len(anchors) - 1:
        raise ValueError(
            f"the path has {len(anchors)} authored points, so it takes "
            f"{len(anchors) - 1} arrival times (one per point after the first); "
            f"got {len(arrivals)}"
        )
    times = [start, *arrivals]
    if any(not b > a for a, b in zip(times, times[1:])):
        raise ValueError(
            f"arrival times must increase from start={start}; got {list(arrivals)}"
        )
    cum = cumulative_lengths(points)
    fractions = [cum[i] / cum[-1] for i in anchors]
    out: list = [c.set_(entity_id, "trim_end", 0.0)]
    for k in range(1, len(times)):
        tween = c.tween(
            entity_id,
            "trim_end",
            to=fractions[k],
            from_=fractions[k - 1],
            duration=times[k] - times[k - 1],
            easing=easing,
        )
        out.append(c.sequence(c.delay(times[k - 1]), tween) if times[k - 1] else tween)
    return out
