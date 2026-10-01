"""Field kinds: the declared interpolator of each animatable property.

**The declared kind picks the interpolator; a runtime value never does.** A field
kind is what lets a number be an angle (shortest arc), a log-space zoom, or a
colour mixed in OKLab — none of which a value's type can say. Kinds are declared
per property by a *property space* (:mod:`an.timing.spaces`); a property no space
declares is :class:`DiscreteKind`.

Seven kinds are seeded, each parametrised (the TypeScript kernel's seven):

====================  =========================================================
``number(space)``     ``linear``: ``a + (b - a) * u``; ``log``: ``a * (b / a) ** u``
``angle(unit, wrap)`` shortest arc (``wrap``) or the raw numbers; ``deg``/``rad``
``vector``            componentwise lerp of equal-length number lists
``quaternion``        slerp of unit ``[x, y, z, w]`` after a sign fix
``color(space)``      ``oklab`` (premultiplied alpha) or ``srgb`` (componentwise)
``orbit(unit)``       azimuth on the shortest arc, elevation clamped, distance in
                      log, target componentwise, other members discrete
``discrete(switch_at)`` holds ``a``, shows ``b`` from ``a.time + switch_at * span``
====================  =========================================================

**Discrete is defined on TIME, never on a ratio or an eased value** (an#86). A
segment from key ``a`` to key ``b`` shows ``b`` iff ``t >= a.time + switch_at *
(b.time - a.time)``, and ``switch_at == 1`` is evaluated as ``t >= b.time`` with
no arithmetic at all: ``(t - a.time) / span`` can round up to 1.0 while
``t < b.time``, and an overshooting easing would flip an eased comparison twice.

Genres add kinds with :func:`register_kind` (a Manim genre's ``points``, say)
without editing this module.

>>> NumberKind().interpolate(0.0, 10.0, 0.25, Segment(0.25, 0.0, 1.0))
2.5
>>> NumberKind(space="log").interpolate(1.0, 4.0, 0.5, Segment(0.5, 0.0, 1.0))
2.0
>>> AngleKind().interpolate(350, 10, 0.5, Segment(0.5, 0.0, 1.0))  # not re-normalised
360.0
>>> b = 9.767899248713501
>>> DiscreteKind(switch_at=1).interpolate("A", "B", 1.0, Segment(math.nextafter(b, 0), 0.15, b))
'A'
>>> kind_from_spec({"kind": "number", "space": "log"})
NumberKind(space='log')
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any, Callable, ClassVar, Mapping

from an.timing._color import (
    color_problem,
    format_color,
    mix_oklab,
    mix_srgb,
    parse_color,
)

#: Where an undeclared discrete value switches, in normalised segment time.
DEFAULT_SWITCH_AT: float = 0.5
DEG_TURN: float = 360.0
RAD_TURN: float = 2 * math.pi
ANGLE_UNITS: tuple[str, ...] = ("deg", "rad")
NUMBER_SPACES: tuple[str, ...] = ("linear", "log")
COLOR_SPACES: tuple[str, ...] = ("oklab", "srgb")
QUATERNION_LENGTH: int = 4
#: How far a quaternion's norm may be from 1 and still count as unit length.
QUATERNION_UNIT_TOLERANCE: float = 1e-3
#: Above this |dot|, slerp falls back to normalised lerp (the arc is too short).
SLERP_LINEAR_THRESHOLD: float = 0.9995
ORBIT_KEYS: tuple[str, ...] = ("azimuth", "elevation", "distance")
ORBIT_MEMBERS: tuple[str, ...] = (*ORBIT_KEYS, "target")


class FieldKindError(ValueError):
    """A kind spec is malformed, or names no registered kind."""


@dataclass(frozen=True, slots=True)
class Segment:
    """Where an evaluation sits: time ``t`` inside the segment ``[start, end)``."""

    t: float
    start: float
    end: float

    def switched(self, switch_at: float) -> bool:
        """Whether a discrete value has switched to the segment's second key.

        >>> Segment(0.5, 0.0, 1.0).switched(0.5), Segment(0.49, 0.0, 1.0).switched(0.5)
        (True, False)
        >>> Segment(0.9999999999, 0.0, 1.0).switched(1.0)  # only at b.time itself
        False
        """
        if switch_at >= 1:
            return self.t >= self.end  # an#86: a comparison, no arithmetic
        return self.t > self.start and self.t >= self.start + switch_at * (
            self.end - self.start
        )


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def shortest_delta(a: float, b: float, period: float = DEG_TURN) -> float:
    """The signed shortest turn from ``a`` to ``b``, in ``[-period/2, period/2]``.

    An exact half turn goes in the direction of ``b - a``, so a return trip
    retraces its path (0 -> 180 -> 0 goes there and back, not round).

    >>> shortest_delta(350, 10), shortest_delta(10, 350), shortest_delta(0, 180)
    (20.0, -20.0, 180.0)
    """
    half = period / 2
    d = (((b - a + half) % period) + period) % period - half
    return half if d == -half and b > a else d


@dataclass(frozen=True)
class FieldKind:
    """Base of every field kind: a frozen, hashable, JSON-describable interpolator.

    Subclasses set ``name`` and implement :meth:`interpolate`; the dataclass
    fields are the kind's parameters, and :meth:`to_spec` writes them as the
    contract does (``{"kind": name, **non-default params}``).
    """

    name: ClassVar[str] = ""
    #: True when the value (or part of it) switches on TIME rather than moving.
    switches: ClassVar[bool] = False

    def interpolate(self, a: Any, b: Any, u: float, seg: Segment) -> Any:
        """The value between keys ``a`` and ``b`` at eased progress ``u``."""
        raise FieldKindError(f"{type(self).__name__} does not implement interpolate")

    def check(self, value: Any) -> str | None:
        """Why ``value`` is not valid for this kind, or ``None``."""
        return None

    def to_spec(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.name}
        for f in fields(self):
            value = getattr(self, f.name)
            if value != f.default:
                out[f.name] = value
        return out


@dataclass(frozen=True)
class NumberKind(FieldKind):
    """A continuous scalar. ``space="log"`` interpolates the logarithm (zoom, scale).

    Linear interpolation is ``a + (b - a) * u`` with no special case at the ends,
    which is the stage runtime's arithmetic: a declared ``number`` channel is
    bit-identical to what ``runtime.js`` draws.
    """

    name: ClassVar[str] = "number"
    space: str = "linear"

    def __post_init__(self) -> None:
        if self.space not in NUMBER_SPACES:
            raise FieldKindError(
                f"number space must be one of {NUMBER_SPACES}, got {self.space!r}"
            )

    def interpolate(self, a: Any, b: Any, u: float, seg: Segment) -> Any:
        if self.space == "log":
            return a * (b / a) ** u
        return a + (b - a) * u

    def check(self, value: Any) -> str | None:
        if not _is_number(value):
            return f"expected a finite number, got {value!r}"
        if self.space == "log" and value <= 0:
            return f"a log-space number must be positive, got {value}"
        return None


@dataclass(frozen=True)
class AngleKind(FieldKind):
    """An angle: the shortest arc when ``wrap``, else the raw numbers. Interpolated
    angles are not re-normalised (350 -> 10 passes through 360)."""

    name: ClassVar[str] = "angle"
    unit: str = "deg"
    wrap: bool = True

    def __post_init__(self) -> None:
        if self.unit not in ANGLE_UNITS:
            raise FieldKindError(
                f"angle unit must be one of {ANGLE_UNITS}, got {self.unit!r}"
            )

    @property
    def period(self) -> float:
        return RAD_TURN if self.unit == "rad" else DEG_TURN

    def interpolate(self, a: Any, b: Any, u: float, seg: Segment) -> Any:
        if u == 0:
            return a
        if u == 1:
            return b
        delta = shortest_delta(a, b, self.period) if self.wrap else b - a
        return a + delta * u

    def check(self, value: Any) -> str | None:
        return (
            None
            if _is_number(value)
            else f"expected an angle (finite number), got {value!r}"
        )


def _number_list(value: Any, what: str, length: int | None = None) -> str | None:
    if not isinstance(value, (list, tuple)) or not all(_is_number(v) for v in value):
        return f"{what} must be an array of finite numbers, got {value!r}"
    if length is not None and len(value) != length:
        return f"{what} must have {length} numbers, got {len(value)}"
    return None


def _vector_lerp(a: Any, b: Any, u: float) -> list[float]:
    if len(a) != len(b):
        raise FieldKindError(
            f"cannot interpolate vectors of lengths {len(a)} and {len(b)}"
        )
    return [_lerp(x, y, u) for x, y in zip(a, b)]


@dataclass(frozen=True)
class VectorKind(FieldKind):
    """A fixed-length list of numbers, interpolated componentwise."""

    name: ClassVar[str] = "vector"

    def interpolate(self, a: Any, b: Any, u: float, seg: Segment) -> Any:
        if u == 0:
            return a
        if u == 1:
            return b
        return _vector_lerp(a, b, u)

    def check(self, value: Any) -> str | None:
        return _number_list(value, "a vector")


def _normalize(q: list[float]) -> list[float]:
    n = math.hypot(*q)
    if n == 0:
        raise FieldKindError("a quaternion cannot be zero")
    return [c / n for c in q]


def slerp(a: Any, b: Any, u: float) -> list[float]:
    """Spherical interpolation of unit quaternions ``[x, y, z, w]``, the short way."""
    p = _normalize(list(a))
    q = _normalize(list(b))
    dot = sum(x * y for x, y in zip(p, q))
    if dot < 0:
        q = [-c for c in q]
        dot = -dot
    if dot > SLERP_LINEAR_THRESHOLD:
        return _normalize([_lerp(x, y, u) for x, y in zip(p, q)])
    theta = math.acos(min(1.0, dot))
    sin = math.sin(theta)
    wa = math.sin((1 - u) * theta) / sin
    wb = math.sin(u * theta) / sin
    return [wa * x + wb * y for x, y in zip(p, q)]


@dataclass(frozen=True)
class QuaternionKind(FieldKind):
    """A unit quaternion ``[x, y, z, w]``, interpolated by slerp after a sign fix."""

    name: ClassVar[str] = "quaternion"

    def interpolate(self, a: Any, b: Any, u: float, seg: Segment) -> Any:
        if u == 0:
            return a
        if u == 1:
            return b
        return slerp(a, b, u)

    def check(self, value: Any) -> str | None:
        problem = _number_list(value, "a quaternion [x, y, z, w]", QUATERNION_LENGTH)
        if problem:
            return problem
        norm = math.hypot(*value)
        if norm == 0:
            return "a quaternion cannot be all zeros"
        if abs(norm - 1) > QUATERNION_UNIT_TOLERANCE:
            return f"a quaternion must be unit length (got norm {norm}); normalize it first"
        return None


@dataclass(frozen=True)
class ColorKind(FieldKind):
    """A colour (hex or ``[r, g, b, a?]`` in 0..1), written back in the form of
    the start value. ``oklab`` mixes perceptually with premultiplied alpha;
    ``srgb`` lerps the encoded channels (Manim's and the stage tint's rule)."""

    name: ClassVar[str] = "color"
    space: str = "oklab"

    def __post_init__(self) -> None:
        if self.space not in COLOR_SPACES:
            raise FieldKindError(
                f"color space must be one of {COLOR_SPACES}, got {self.space!r}"
            )

    def interpolate(self, a: Any, b: Any, u: float, seg: Segment) -> Any:
        if u == 0:
            return a
        if u == 1:
            return b
        mix = mix_oklab if self.space == "oklab" else mix_srgb
        return format_color(mix(parse_color(a), parse_color(b), u), a)

    def check(self, value: Any) -> str | None:
        return color_problem(value)


@dataclass(frozen=True)
class OrbitKind(FieldKind):
    """A camera orbiting a target: ``{azimuth, elevation, distance, target?}``.

    Azimuth takes the shortest arc, elevation is lerped and clamped to the poles,
    distance is lerped in log, target componentwise. Any other member is discrete
    and switches at :data:`DEFAULT_SWITCH_AT` (on time). One value: a dotted
    address never reaches inside it.
    """

    name: ClassVar[str] = "orbit"
    switches: ClassVar[bool] = True
    unit: str = "deg"

    def __post_init__(self) -> None:
        if self.unit not in ANGLE_UNITS:
            raise FieldKindError(
                f"orbit unit must be one of {ANGLE_UNITS}, got {self.unit!r}"
            )

    @property
    def period(self) -> float:
        return RAD_TURN if self.unit == "rad" else DEG_TURN

    def interpolate(self, a: Any, b: Any, u: float, seg: Segment) -> Any:
        switched = seg.switched(DEFAULT_SWITCH_AT)
        keys = list(dict.fromkeys([*a, *b]))
        if u in (0, 1):
            end = a if u == 0 else b
            return {
                k: end.get(k)
                if k in ORBIT_MEMBERS
                else (b.get(k) if switched else a.get(k))
                for k in keys
            }
        pole = self.period / 4
        out: dict[str, Any] = {}
        for k in keys:
            p, q = a.get(k), b.get(k)
            if k == "azimuth":
                out[k] = p + shortest_delta(p, q, self.period) * u
            elif k == "elevation":
                out[k] = min(pole, max(-pole, _lerp(p, q, u)))
            elif k == "distance":
                out[k] = p * (q / p) ** u
            elif k == "target" and isinstance(p, list) and isinstance(q, list):
                out[k] = _vector_lerp(p, q, u)
            else:
                out[k] = q if switched else p
        return out

    def check(self, value: Any) -> str | None:
        if not isinstance(value, Mapping):
            return f"an orbit is an object {{azimuth, elevation, distance, target?}}, got {value!r}"
        missing = [k for k in ORBIT_KEYS if not _is_number(value.get(k))]
        if missing:
            return f"an orbit needs finite numbers for {', '.join(missing)}"
        if value["distance"] <= 0:
            return f"orbit distance must be positive, got {value['distance']}"
        pole = self.period / 4
        if abs(value["elevation"]) > pole:
            return f"orbit elevation must lie within ±{pole}, got {value['elevation']}"
        if "target" in value:
            return _number_list(value["target"], "orbit target")
        return None


@dataclass(frozen=True)
class DiscreteKind(FieldKind):
    """Holds ``a`` and switches to ``b`` on TIME (see the module docstring).

    ``switch_at`` lies in ``(0, 1]``. The default, 0.5, is the switch point of an
    undeclared property; a replacement drawing (a swap set) declares 1, so it
    never appears before its own key.
    """

    name: ClassVar[str] = "discrete"
    switches: ClassVar[bool] = True
    switch_at: float = DEFAULT_SWITCH_AT

    def __post_init__(self) -> None:
        if isinstance(self.switch_at, bool) or not (0 < self.switch_at <= 1):
            raise FieldKindError(
                f"discrete switch_at must lie in (0, 1], got {self.switch_at!r}"
            )

    def interpolate(self, a: Any, b: Any, u: float, seg: Segment) -> Any:
        return b if seg.switched(self.switch_at) else a


# -----------------------------------------------------------------------------
# The registry
# -----------------------------------------------------------------------------

#: A kind's factory: its parameters as keyword arguments -> an instance.
KindFactory = Callable[..., FieldKind]

_REGISTRY: dict[str, KindFactory] = {}
_OWNERS: dict[str, str | None] = {}
#: Who registered the seeded kinds (only these reach the contract files).
CORE_OWNER: str = "an"


def register_kind(
    name: str,
    factory: KindFactory,
    *,
    replace: bool = False,
    owner: str | None = None,
) -> KindFactory:
    """Register a field kind under ``name`` (how a genre adds one).

    ``owner`` names who registered it; only :data:`CORE_OWNER`'s kinds reach
    `an`'s contract files.

    >>> sorted(kind_names())[:3]
    ['angle', 'color', 'discrete']
    """
    if not replace and name in _REGISTRY:
        raise FieldKindError(f"field kind {name!r} is already registered")
    _REGISTRY[name] = factory
    _OWNERS[name] = owner
    return factory


def kind_names(*, owner: str | None = None) -> tuple[str, ...]:
    """The registered kind names in registration order; only ``owner``'s when given."""
    return tuple(k for k in _REGISTRY if owner is None or _OWNERS[k] == owner)


def kind_from_spec(spec: Mapping[str, Any] | FieldKind | str) -> FieldKind:
    """A kind instance from its contract spec (``{"kind": name, **params}``),
    a bare kind name, or an instance (returned as is).

    >>> kind_from_spec("discrete")
    DiscreteKind(switch_at=0.5)
    >>> kind_from_spec({"kind": "points"})
    Traceback (most recent call last):
     ...
    an.timing.kinds.FieldKindError: unknown field kind 'points'; known: ['number', 'angle', 'vector', 'quaternion', 'color', 'orbit', 'discrete']
    """
    if isinstance(spec, FieldKind):
        return spec
    if isinstance(spec, str):
        spec = {"kind": spec}
    params = dict(spec)
    name = params.pop("kind", None)
    factory = _REGISTRY.get(name)  # type: ignore[arg-type]
    if factory is None:
        raise FieldKindError(f"unknown field kind {name!r}; known: {list(_REGISTRY)}")
    try:
        return factory(**params)
    except TypeError as e:
        raise FieldKindError(
            f"bad parameters for field kind {name!r}: {params} ({e})"
        ) from e


for _kind in (
    NumberKind,
    AngleKind,
    VectorKind,
    QuaternionKind,
    ColorKind,
    OrbitKind,
    DiscreteKind,
):
    register_kind(_kind.name, _kind, owner=CORE_OWNER)
