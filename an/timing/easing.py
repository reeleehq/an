"""The easing registry: every named timing curve, each with the solver that computes it.

An **easing** (CSS: *timing function*; Manim: *rate function*) maps a segment's
normalised time ``u`` in ``[0, 1]`` to its progress. One registry holds every
curve a timeline may name, and each entry carries its own **solver**, because two
solvers of "the same" curve do not agree to the contract tolerance (core study
§2.3): `an`'s cubic Bézier runs 8 Newton steps and stops, the CSS one runs Newton
and then bisects.

Four vocabularies live here, and none is silently aliased to another:

- **legacy** — `an`'s own names, with the polynomial curves `an` has always drawn
  (``ease``, ``ease_in``, ``ease_out``, ``ease_in_out``, ``step``). ``ease`` and
  ``ease_in_out`` are the quadratic ease-in-out, **not** CSS ``ease``; the CSS
  ``ease`` curve is spelled ``cubic-bezier(0.25, 0.1, 0.25, 1)``.
- **css** — CSS Easing Level 1/2 hyphenated names with the exact CSS curves
  (``ease-in``, ``ease-out``, ``ease-in-out``, ``step-start``, ``step-end``),
  plus the parametrised ``cubic-bezier(x1, y1, x2, y2)`` and
  ``steps(n[, position])``.
- **manim** — Manim Community Edition's rate functions under their own names
  (``smooth``, ``there_and_back``, ``rush_into``, ...), so a curve means the same
  thing whether the stage engine or Manim draws it.
- **common** — ``linear``, which every vocabulary agrees on.

A bare 4-sequence ``[cx1, cy1, cx2, cy2]`` (what `an` scenes have always written)
is a cubic Bézier solved by the **legacy** solver, so no existing scene moves.

>>> apply_easing("linear", 0.5)
0.5
>>> apply_easing("ease_in_out", 0.25)  # an's quadratic, not CSS
0.125
>>> round(apply_easing("ease-in-out", 0.25), 6)  # the CSS curve
0.129162
>>> round(apply_easing("cubic-bezier(0.42, 0, 0.58, 1)", 0.25), 6)
0.129162
>>> apply_easing("steps(4)", 0.3)
0.25
>>> round(apply_easing("smooth", 0.25), 6)  # Manim's default rate function
0.070104
>>> round(apply_easing([0.42, 0.0, 0.58, 1.0], 0.25), 6)  # legacy solver
0.129162
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, Collection, Mapping, Sequence

from an.base import EasingSpec

#: A curve: normalised time ``u`` -> progress.
Curve = Callable[[float], float]

#: Families an entry can belong to (see the module docstring).
EASING_FAMILIES: tuple[str, ...] = ("common", "legacy", "css", "manim")

#: The solvers, by name. An entry names the one that computes it, so a curve's
#: numbers are reproducible in another language from its entry alone.
SOLVERS: dict[str, str] = {
    "closed-form": "evaluated directly from its formula",
    "an-bezier-newton-8": (
        "an's cubic Bézier: x(s) = t solved by exactly 8 Newton steps from s = t, "
        "each clamped to [0, 1], stopping only on a derivative below 1e-12; no "
        "bisection. Bit-identical to runtime.js cubicBezier"
    ),
    "css-bezier-newton-bisection": (
        "the CSS cubic Bézier: up to 8 Newton steps from s = t (stop when "
        "|x(s) - t| < 1e-12, give up on a slope below 1e-6), then up to 60 "
        "bisection steps on [0, 1] to the same 1e-12"
    ),
    "css-steps": "the CSS Easing Level 1 step algorithm",
}


@dataclass(frozen=True)
class EasingEntry:
    """One named easing: its curve, where it comes from, and how it is solved.

    ``version`` follows ADR 0003: an entry whose meaning changes gets a new
    version, so a shot that names it re-renders visibly instead of silently.
    """

    name: str
    curve: Curve = field(compare=False, repr=False)
    family: str
    solver: str
    description: str
    version: int = 1
    params: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if self.family not in EASING_FAMILIES:
            raise ValueError(
                f"easing {self.name!r}: family {self.family!r} is not one of "
                f"{EASING_FAMILIES}"
            )
        if self.solver not in SOLVERS:
            raise ValueError(
                f"easing {self.name!r}: solver {self.solver!r} is not one of "
                f"{sorted(SOLVERS)}"
            )

    def to_json(self) -> dict[str, Any]:
        """The entry as the contract file lists it (without samples)."""
        out: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "solver": self.solver,
            "description": self.description,
        }
        if self.params:
            out["params"] = dict(self.params)
        return out


class UnknownEasingError(ValueError):
    """An easing spec names no registered curve and parses as no parametrised one."""


# -----------------------------------------------------------------------------
# Legacy curves (an's own). DO NOT change their arithmetic: runtime.js mirrors
# them bit for bit, and every pixel golden was drawn through them.
# -----------------------------------------------------------------------------


def _linear(t: float) -> float:
    return t


def _ease_in(t: float) -> float:
    return t * t


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2


def _ease_in_out(t: float) -> float:
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - 2.0 * (1.0 - t) ** 2


def _ease(t: float) -> float:
    """an's ``ease``: the quadratic ease-in-out (NOT CSS ``ease``)."""
    return _ease_in_out(t)


def _step(t: float) -> float:
    return 0.0 if t < 1.0 else 1.0


#: Newton steps of the legacy Bézier solver, and its degenerate-slope guard.
LEGACY_BEZIER_NEWTON_STEPS: int = 8
LEGACY_BEZIER_MIN_SLOPE: float = 1e-12


def legacy_cubic_bezier(
    cx1: float, cy1: float, cx2: float, cy2: float, t: float
) -> float:
    """an's cubic-Bézier easing at ``t`` — the ``an-bezier-newton-8`` solver.

    The curve is defined by P0=(0,0), P1=(cx1,cy1), P2=(cx2,cy2), P3=(1,1).
    Given a desired x=t we solve for the matching curve parameter u, then
    return the y coordinate, by exactly 8 clamped Newton steps.

    Structurally IDENTICAL to runtime.js::cubicBezier on purpose: always 8
    iterations, break only on a degenerate derivative, clamp each step. This
    function is the spec of that port, and the two are compared bit-for-bit by
    the parity battery — an earlier version had an extra |u_new - u| < 1e-9
    early-convergence break the JS side lacked, which left the two a ULP apart;
    a numeric channel lerping large magnitudes amplifies a ULP of easing by
    (b - a) (found by the an#86 adversarial review; the loops now match).

    It does NOT agree with the CSS solver (:func:`css_cubic_bezier`) to 1e-9
    for every control point, which is why it stays a named legacy solver until
    the pixel goldens are re-blessed under the stricter one.

    >>> round(legacy_cubic_bezier(0.0, 0.0, 1.0, 1.0, 0.5), 6)  # linear
    0.5
    >>> legacy_cubic_bezier(0.42, 0.0, 0.58, 1.0, 0.0), legacy_cubic_bezier(0.42, 0.0, 0.58, 1.0, 1.0)
    (0.0, 1.0)
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0

    def bx(u: float) -> float:
        # x coordinate of the curve at parameter u (note P0.x=0, P3.x=1)
        return 3 * (1 - u) ** 2 * u * cx1 + 3 * (1 - u) * u * u * cx2 + u**3

    def dbx(u: float) -> float:
        return (
            3 * (1 - u) ** 2 * cx1
            - 6 * (1 - u) * u * cx1
            + 6 * (1 - u) * u * cx2
            - 3 * u * u * cx2
            + 3 * u * u
        )

    def by(u: float) -> float:
        return 3 * (1 - u) ** 2 * u * cy1 + 3 * (1 - u) * u * u * cy2 + u**3

    u = t
    for _ in range(LEGACY_BEZIER_NEWTON_STEPS):
        f = bx(u) - t
        fp = dbx(u)
        if abs(fp) < LEGACY_BEZIER_MIN_SLOPE:
            break
        u_new = u - f / fp
        # Clamp into the valid range so we don't escape during iteration.
        if u_new < 0.0:
            u_new = 0.0
        elif u_new > 1.0:
            u_new = 1.0
        u = u_new
    return by(u)


# -----------------------------------------------------------------------------
# CSS curves
# -----------------------------------------------------------------------------

#: The CSS named curves, as cubic-bezier control points (CSS Easing Level 1).
CSS_BEZIERS: dict[str, tuple[float, float, float, float]] = {
    "ease": (0.25, 0.1, 0.25, 1.0),
    "ease-in": (0.42, 0.0, 1.0, 1.0),
    "ease-out": (0.0, 0.0, 0.58, 1.0),
    "ease-in-out": (0.42, 0.0, 0.58, 1.0),
}

#: The CSS solver's constants (see ``SOLVERS["css-bezier-newton-bisection"]``).
CSS_NEWTON_STEPS: int = 8
CSS_EPSILON: float = 1e-12
CSS_BISECTION_STEPS: int = 60
CSS_MIN_SLOPE: float = 1e-6


def css_cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Curve:
    """The CSS ``cubic-bezier(x1, y1, x2, y2)`` curve, solved to well below 1e-9.

    ``x1`` and ``x2`` must lie in ``[0, 1]`` (so the curve is a function of
    time); ``y`` may overshoot.

    >>> css = css_cubic_bezier(0.42, 0.0, 0.58, 1.0)
    >>> css(0.0), css(1.0), round(css(0.5), 12)
    (0, 1, 0.5)
    >>> css_cubic_bezier(1.5, 0, 0, 1)
    Traceback (most recent call last):
     ...
    ValueError: cubic-bezier x values must lie in [0, 1], got x1=1.5, x2=0
    """
    values = (x1, y1, x2, y2)
    if not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        for v in values
    ):
        raise ValueError(f"cubic-bezier needs four finite numbers, got {values}")
    if not (0 <= x1 <= 1 and 0 <= x2 <= 1):
        raise ValueError(
            f"cubic-bezier x values must lie in [0, 1], got x1={x1}, x2={x2}"
        )
    # Polynomial coefficients of B(s) = 3(1-s)^2 s p1 + 3(1-s) s^2 p2 + s^3.
    cx = 3 * x1
    bx = 3 * (x2 - x1) - cx
    ax = 1 - cx - bx
    cy = 3 * y1
    by = 3 * (y2 - y1) - cy
    ay = 1 - cy - by

    def x_at(s: float) -> float:
        return ((ax * s + bx) * s + cx) * s

    def y_at(s: float) -> float:
        return ((ay * s + by) * s + cy) * s

    def dx_at(s: float) -> float:
        return (3 * ax * s + 2 * bx) * s + cx

    def solve(x: float) -> float:
        s = x
        for _ in range(CSS_NEWTON_STEPS):
            err = x_at(s) - x
            if abs(err) < CSS_EPSILON:
                return s
            slope = dx_at(s)
            if abs(slope) < CSS_MIN_SLOPE:
                break
            s -= err / slope
        lo, hi = 0.0, 1.0
        s = x
        for _ in range(CSS_BISECTION_STEPS):
            v = x_at(s)
            if abs(v - x) < CSS_EPSILON:
                return s
            if v < x:
                lo = s
            else:
                hi = s
            s = (lo + hi) / 2
        return s

    def curve(tau: float) -> float:
        if tau <= 0:
            return 0
        if tau >= 1:
            return 1
        return y_at(solve(tau))

    return curve


#: The positions ``steps()`` accepts; ``start``/``end`` are the CSS aliases of
#: ``jump-start``/``jump-end``.
STEP_POSITIONS: tuple[str, ...] = (
    "jump-start",
    "jump-end",
    "jump-none",
    "jump-both",
    "start",
    "end",
)
DFLT_STEP_POSITION: str = "jump-end"


def css_steps(n: int, position: str = DFLT_STEP_POSITION) -> Curve:
    """CSS ``steps(n, position)``, following the CSS Easing Level 1 algorithm.

    >>> f = css_steps(4)
    >>> [f(u) for u in (0.0, 0.24, 0.25, 0.99, 1.0)]
    [0.0, 0.0, 0.25, 0.75, 1.0]
    >>> css_steps(3, "jump-none")(0.5)
    0.5
    """
    if position not in STEP_POSITIONS:
        raise ValueError(
            f'steps(): unknown position "{position}". Known: {", ".join(STEP_POSITIONS)}'
        )
    pos = {"start": "jump-start", "end": "jump-end"}.get(position, position)
    minimum = 2 if pos == "jump-none" else 1
    if isinstance(n, bool) or not isinstance(n, int) or n < minimum:
        raise ValueError(
            f"steps() needs a whole number of steps (at least {minimum}), got {n}"
        )
    jumps = n + 1 if pos == "jump-both" else n - 1 if pos == "jump-none" else n

    def curve(tau: float) -> float:
        x = min(1.0, max(0.0, tau))
        step = math.floor(x * n)
        if pos in ("jump-start", "jump-both"):
            step += 1
        return min(step, jumps) / jumps

    return curve


# -----------------------------------------------------------------------------
# Manim rate functions (Manim Community Edition, manim/utils/rate_functions.py)
# -----------------------------------------------------------------------------

#: Manim's default sigmoid steepness for ``smooth`` and its relatives.
MANIM_INFLECTION: float = 10.0
MANIM_PAUSE_RATIO: float = 1.0 / 3
MANIM_PULL_FACTOR: float = -0.5
MANIM_WIGGLES: float = 2.0
MANIM_LINGER_END: float = 0.8
MANIM_HALF_LIFE: float = 0.1


def _unit_interval(f: Curve) -> Curve:
    """Manim's ``@unit_interval``: 0 before the segment, 1 after it."""

    def wrapped(t: float) -> float:
        if 0 <= t <= 1:
            return f(t)
        return 0 if t < 0 else 1

    return wrapped


def _zero(f: Curve) -> Curve:
    """Manim's ``@zero``: 0 outside the segment (curves that return to 0)."""

    def wrapped(t: float) -> float:
        return f(t) if 0 <= t <= 1 else 0

    return wrapped


def _sigmoid(x: float) -> float:
    return 1.0 / (1 + math.exp(-x))


def _smooth_raw(t: float, inflection: float = MANIM_INFLECTION) -> float:
    error = _sigmoid(-inflection / 2)
    return min(max((_sigmoid(inflection * (t - 0.5)) - error) / (1 - 2 * error), 0), 1)


_smooth = _unit_interval(_smooth_raw)


def _there_and_back_raw(t: float) -> float:
    new_t = 2 * t if t < 0.5 else 2 * (1 - t)
    return _smooth(new_t)


def _there_and_back_with_pause_raw(t: float) -> float:
    a = 2.0 / (1.0 - MANIM_PAUSE_RATIO)
    if t < 0.5 - MANIM_PAUSE_RATIO / 2:
        return _smooth(a * t)
    if t < 0.5 + MANIM_PAUSE_RATIO / 2:
        return 1
    return _smooth(a - a * t)


def _running_start_raw(t: float) -> float:
    p = MANIM_PULL_FACTOR
    mt = 1 - t
    return (
        15 * t**2 * mt**4 * p
        + 20 * t**3 * mt**3 * p
        + 15 * t**4 * mt**2
        + 6 * t**5 * mt
        + t**6
    )


def _double_smooth_raw(t: float) -> float:
    if t < 0.5:
        return 0.5 * _smooth(2 * t)
    return 0.5 * (1 + _smooth(2 * t - 1))


def _lingering_raw(t: float) -> float:
    # Manim's `squish_rate_func(identity, 0, 0.8)`: t / 0.8, held at 1 after.
    return 1.0 if t > MANIM_LINGER_END else t / MANIM_LINGER_END


_MANIM_CURVES: dict[str, tuple[Curve, str]] = {
    "smooth": (
        _smooth,
        "Manim's default rate function: a logistic sigmoid (steepness 10), "
        "rescaled to run from 0 to 1",
    ),
    "smoothstep": (
        _unit_interval(lambda t: 3 * t**2 - 2 * t**3),
        "the first-order smoothstep polynomial 3t^2 - 2t^3",
    ),
    "smootherstep": (
        _unit_interval(lambda t: 6 * t**5 - 15 * t**4 + 10 * t**3),
        "the second-order smoothstep polynomial 6t^5 - 15t^4 + 10t^3",
    ),
    "smoothererstep": (
        _unit_interval(lambda t: 35 * t**4 - 84 * t**5 + 70 * t**6 - 20 * t**7),
        "the third-order smoothstep polynomial",
    ),
    "rush_into": (
        _unit_interval(lambda t: 2 * _smooth(t / 2.0)),
        "the first half of smooth, stretched: slow start, full speed at the end",
    ),
    "rush_from": (
        _unit_interval(lambda t: 2 * _smooth(t / 2.0 + 0.5) - 1),
        "the second half of smooth, stretched: full speed at the start, slow end",
    ),
    "slow_into": (
        _unit_interval(lambda t: math.sqrt(1 - (1 - t) * (1 - t))),
        "a quarter circle: fast start, decelerating into the end",
    ),
    "double_smooth": (
        _unit_interval(_double_smooth_raw),
        "two smooth curves back to back, each covering half the distance",
    ),
    "there_and_back": (
        _zero(_there_and_back_raw),
        "goes to 1 at the middle and returns to 0 (the segment ends where it began)",
    ),
    "there_and_back_with_pause": (
        _zero(_there_and_back_with_pause_raw),
        "there and back, holding at 1 for the middle third",
    ),
    "running_start": (
        _unit_interval(_running_start_raw),
        "pulls back (to -0.5 control) before going forward: a degree-6 Bézier "
        "evaluated at t directly",
    ),
    "wiggle": (
        _zero(lambda t: _there_and_back_raw(t) * math.sin(MANIM_WIGGLES * math.pi * t)),
        "there_and_back times sin(2 pi t): a wiggle that ends where it began",
    ),
    "lingering": (
        _unit_interval(_lingering_raw),
        "linear to 1 over the first 80% of the segment, then holds",
    ),
    "exponential_decay": (
        _unit_interval(lambda t: 1 - math.exp(-t / MANIM_HALF_LIFE)),
        "1 - exp(-t / 0.1): reaches 1 - e^-10 at the end of the segment, not 1",
    ),
}


# -----------------------------------------------------------------------------
# The registry
# -----------------------------------------------------------------------------

_REGISTRY: dict[str, EasingEntry] = {}


def register_easing(entry: EasingEntry, *, replace: bool = False) -> EasingEntry:
    """Add ``entry`` to the registry (a genre's own curves register here).

    Re-registering a name is refused unless ``replace=True``: a name's meaning
    changing under a scene that uses it is exactly what entry versions exist to
    make visible, so it must be deliberate.
    """
    if not replace and entry.name in _REGISTRY:
        raise ValueError(f"easing {entry.name!r} is already registered")
    if _parse_call(entry.name) is not None:
        raise ValueError(
            f"easing {entry.name!r} would shadow a parametrised spec; pick a plain name"
        )
    _REGISTRY[entry.name] = entry
    _resolve_cached.cache_clear()
    return entry


def easing_entry(name: str) -> EasingEntry:
    """The registered entry called ``name``.

    >>> easing_entry("ease").family
    'legacy'
    """
    try:
        return _REGISTRY[name]
    except KeyError as e:
        raise UnknownEasingError(
            f"unknown easing preset {name!r}; known: {sorted(_REGISTRY)}"
        ) from e


def easing_entries() -> tuple[EasingEntry, ...]:
    """Every registered entry, in registration order."""
    return tuple(_REGISTRY.values())


def _seed() -> None:
    register_easing(
        EasingEntry(
            "linear",
            _linear,
            family="common",
            solver="closed-form",
            description="progress equals time; the same in CSS, Manim and an",
        )
    )
    legacy = {
        "ease": (
            _ease,
            "an's 'ease': the quadratic ease-in-out (0.125 at u=0.25). NOT "
            "CSS 'ease', which is cubic-bezier(0.25, 0.1, 0.25, 1)",
        ),
        "ease_in": (_ease_in, "quadratic ease-in: u^2"),
        "ease_out": (_ease_out, "quadratic ease-out: 1 - (1 - u)^2"),
        "ease_in_out": (
            _ease_in_out,
            "quadratic ease-in-out: 2u^2, then 1 - 2(1 - u)^2",
        ),
        "step": (
            _step,
            "0 until u reaches 1, then 1 (a hold that jumps at the next key)",
        ),
    }
    for name, (curve, description) in legacy.items():
        register_easing(
            EasingEntry(
                name,
                curve,
                family="legacy",
                solver="closed-form",
                description=description,
            )
        )
    for name, points in CSS_BEZIERS.items():
        if name == "ease":
            continue  # 'ease' is an's legacy curve; the CSS one is cubic-bezier(...)
        register_easing(
            EasingEntry(
                name,
                css_cubic_bezier(*points),
                family="css",
                solver="css-bezier-newton-bisection",
                description=f"CSS '{name}': cubic-bezier{points}",
                params={"control_points": list(points)},
            )
        )
    register_easing(
        EasingEntry(
            "step-start",
            css_steps(1, "jump-start"),
            family="css",
            solver="css-steps",
            description="CSS 'step-start': steps(1, jump-start)",
        )
    )
    register_easing(
        EasingEntry(
            "step-end",
            css_steps(1, "jump-end"),
            family="css",
            solver="css-steps",
            description="CSS 'step-end': steps(1, jump-end)",
        )
    )
    for name, (curve, description) in _MANIM_CURVES.items():
        register_easing(
            EasingEntry(
                name,
                curve,
                family="manim",
                solver="closed-form",
                description=f"Manim rate function '{name}': {description}",
            )
        )


# -----------------------------------------------------------------------------
# Parametrised specs and the dispatcher
# -----------------------------------------------------------------------------

_CALL = re.compile(r"^([a-z-]+)\((.*)\)$")


def _parse_numbers(args: str, spec: str) -> list[float]:
    out = []
    for raw in args.split(","):
        text = raw.strip()
        try:
            value = float(text)
        except ValueError:
            value = math.nan
        if not text or not math.isfinite(value):
            raise UnknownEasingError(f"easing {spec!r}: {text!r} is not a number")
        out.append(value)
    return out


def _parse_call(spec: str) -> Curve | None:
    """``cubic-bezier(...)`` / ``steps(...)`` as a curve; ``None`` if not a call."""
    match = _CALL.match(spec.strip())
    if match is None:
        return None
    name, args = match.groups()
    if name == "cubic-bezier":
        nums = _parse_numbers(args, spec)
        if len(nums) != 4:
            raise UnknownEasingError(
                f"easing {spec!r}: cubic-bezier takes 4 numbers, got {len(nums)}"
            )
        return css_cubic_bezier(*nums)
    if name == "steps":
        parts = [a.strip() for a in args.split(",")]
        if len(parts) > 2:
            raise UnknownEasingError(
                f"easing {spec!r}: steps takes at most 2 arguments"
            )
        try:
            count = int(parts[0])
        except ValueError as e:
            raise UnknownEasingError(
                f"easing {spec!r}: {parts[0]!r} is not a whole number"
            ) from e
        position = parts[1] if len(parts) == 2 else DFLT_STEP_POSITION
        return css_steps(count, position)
    raise UnknownEasingError(
        f"unknown easing function {name!r} in {spec!r}; known: cubic-bezier(), steps()"
    )


@lru_cache(maxsize=1024)
def _resolve_cached(spec: str) -> Curve:
    entry = _REGISTRY.get(spec)
    if entry is not None:
        return entry.curve
    parsed = _parse_call(spec)
    if parsed is None:
        hint = (
            f" (CSS spells it {spec.replace('_', '-')!r})"
            if "_" in spec and spec.replace("_", "-") in _REGISTRY
            else ""
        )
        raise UnknownEasingError(
            f"unknown easing preset {spec!r}{hint}; known: {sorted(_REGISTRY)}, "
            "cubic-bezier(x1, y1, x2, y2), steps(n[, position])"
        )
    return parsed


def resolve_easing(spec: EasingSpec | None) -> Curve:
    """The curve an easing spec names.

    - ``None`` -> linear;
    - a registered name, ``cubic-bezier(x1, y1, x2, y2)`` or ``steps(n[, position])``;
    - a 4-sequence ``[cx1, cy1, cx2, cy2]`` -> the legacy Bézier solver.

    Raises :class:`UnknownEasingError` (a ``ValueError``) for an unknown name or
    a malformed sequence, ``TypeError`` for any other type.
    """
    if spec is None:
        return _linear
    if isinstance(spec, str):
        return _resolve_cached(spec)
    if isinstance(spec, Sequence) and not isinstance(spec, (str, bytes)):
        if len(spec) != 4:
            raise UnknownEasingError(
                f"cubic-bezier easing requires exactly 4 control values, got {len(spec)}"
            )
        cx1, cy1, cx2, cy2 = (float(v) for v in spec)
        return lambda t: legacy_cubic_bezier(cx1, cy1, cx2, cy2, t)
    raise TypeError(f"unsupported easing spec type: {type(spec).__name__}")


def apply_easing(
    spec: EasingSpec | None,
    t: float,
    *,
    names: Collection[str] | None = None,
) -> float:
    """Apply an easing spec to a normalised parameter ``t`` in ``[0, 1]``.

    ``names`` restricts the string specs accepted to that collection — what an
    engine that implements only part of the registry passes (the stage runtime
    implements the legacy names; see ``an.adapters.cutout.easing``). Sequences
    always take the legacy Bézier solver.

    >>> apply_easing(None, 0.25)
    0.25
    >>> apply_easing("step", 0.99), apply_easing("step", 1.0)
    (0.0, 1.0)
    >>> apply_easing("smooth", 0.5, names={"linear"})
    Traceback (most recent call last):
     ...
    an.timing.easing.UnknownEasingError: unknown easing preset 'smooth'; known: ['linear']
    """
    if names is not None and isinstance(spec, str) and spec not in names:
        raise UnknownEasingError(
            f"unknown easing preset {spec!r}; known: {sorted(names)}"
        )
    if spec is None:
        return t
    if isinstance(spec, str):
        entry = _REGISTRY.get(spec)
        if entry is not None:  # the hot path: one dict lookup, as before the registry
            return entry.curve(t)
    return resolve_easing(spec)(t)


_seed()
