"""The stroke: impact events -> one continuous height curve ``h(t)``.

``h`` is the object's height above its impact position, in units of a full
stroke: ``0`` is contact (or, in the air, the turning point) and ``1`` a full
preparation. Every object in :mod:`an.impacts.objects` maps ``h`` AFFINELY onto
one animated property (a stick's rotation, a ball's ``y``), which is what makes
the curve below exactly the curve the renderer draws: an eased tween of the
property IS the same easing of ``h``.

The curve is a chain of :class:`StrokeSegment`\\ s built only from the
quadratic easings the cutout runtime already has, and each is chosen for its
physics:

- **surface** — the object falls with ``ease_in`` (constant acceleration, like
  gravity) and reaches ``h = 0`` at full speed, then leaves with ``ease_out``: a
  velocity reversal AT the impact. Contact is visible in position (the object
  stops at the surface) and as a kink in velocity.
- **air** — no surface. The fall is ``ease_in`` and then a short ``ease_out``
  **brake** of ``brake`` seconds that brings the object to rest at ``h = 0``;
  it then leaves with ``ease_in_out``. The executed "impact" is that turning
  point — the moment the stroke's lowest point is reached — and the peak speed
  comes ``brake`` seconds BEFORE it. The brake's distance is chosen so velocity
  is continuous into it (``d = apex * brake / fall``), so the only
  discontinuity is in acceleration — a muscle stopping a limb, not a collision.

In both kinds the speed at the peak is ``2 * apex / fall``.

>>> from an.impacts.performance import perform
>>> events = perform(120, beats=3)
>>> s = build_stroke(events, kind="surface", duration=2.0)
>>> [s.h(e.t_impact) for e in events]
[0.0, 0.0, 0.0]
>>> round(s.h(0.0), 6), round(s.h(0.75), 6)   # at rest, then the apex between hits
(1.0, 1.0)
>>> a = build_stroke(events, kind="air", duration=2.0)
>>> [round(a.velocity(e.t_impact), 9) for e in events]   # the air stroke TURNS
[0.0, 0.0, 0.0]
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Literal

from an.adapters.cutout.easing import apply_easing
from an.impacts.performance import ImpactEvent

__all__ = [
    "DEFAULT_BRAKE",
    "DEFAULT_FALL",
    "DEFAULT_RISE",
    "IMPACT_KINDS",
    "ImpactKind",
    "Stroke",
    "StrokeError",
    "StrokeKinematics",
    "StrokeSegment",
    "build_stroke",
]

ImpactKind = Literal["surface", "air"]
IMPACT_KINDS: tuple[str, ...] = ("surface", "air")

#: Longest rise after an impact, and longest fall into one (seconds). A slower
#: tempo holds at the apex between them instead of floating: a drummer's stroke
#: takes about as long at 60 BPM as at 120, it is the wait that changes.
DEFAULT_RISE: float = 0.18
DEFAULT_FALL: float = 0.18

#: The air stroke's braking time before its turning point (seconds).
DEFAULT_BRAKE: float = 0.03

#: Derivatives of the quadratic presets, in ``u`` — the stroke uses only these.
_EASING_SLOPES = {
    "linear": lambda u: 1.0,
    "ease_in": lambda u: 2.0 * u,
    "ease_out": lambda u: 2.0 * (1.0 - u),
    "ease_in_out": lambda u: 4.0 * u if u < 0.5 else 4.0 * (1.0 - u),
}


class StrokeError(ValueError):
    """A stroke that cannot be built from these events."""


@dataclass(frozen=True, slots=True)
class StrokeSegment:
    """``h`` goes from ``h0`` to ``h1`` over ``[t0, t1]`` under ``easing``."""

    t0: float
    t1: float
    h0: float
    h1: float
    easing: str

    def h(self, t: float) -> float:
        u = (t - self.t0) / (self.t1 - self.t0)
        return self.h0 + (self.h1 - self.h0) * apply_easing(self.easing, u)

    def velocity(self, t: float) -> float:
        u = (t - self.t0) / (self.t1 - self.t0)
        slope = _EASING_SLOPES[self.easing](min(max(u, 0.0), 1.0))
        return (self.h1 - self.h0) * slope / (self.t1 - self.t0)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StrokeKinematics:
    """How the object moved into one impact.

    ``t_peak_speed`` equals ``t_impact`` for a surface impact and precedes it by
    ``brake`` for an air impact; ``peak_speed`` is in stroke heights per second
    (multiply by the object's stroke extent for pixels or radians).
    """

    index: int
    kind: str
    t_impact: float
    t_peak_speed: float
    peak_speed: float
    apex: float
    fall: float
    brake: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stroke:
    """The whole curve, plus the kinematics of every impact on it."""

    kind: str
    duration: float
    segments: tuple[StrokeSegment, ...]
    kinematics: tuple[StrokeKinematics, ...]

    def _segment_at(self, t: float) -> StrokeSegment:
        starts = [s.t0 for s in self.segments]
        i = max(0, bisect.bisect_right(starts, t) - 1)
        return self.segments[i]

    def h(self, t: float) -> float:
        """Stroke height at scene time ``t`` (clamped to the clip)."""
        t = min(max(t, 0.0), self.duration)
        return self._segment_at(t).h(t)

    def velocity(self, t: float) -> float:
        """``dh/dt`` at ``t``; at a segment boundary, the LATER segment's value."""
        t = min(max(t, 0.0), self.duration)
        return self._segment_at(t).velocity(t)


def build_stroke(
    events: Sequence[ImpactEvent],
    *,
    kind: ImpactKind = "surface",
    duration: float,
    rise: float = DEFAULT_RISE,
    fall: float = DEFAULT_FALL,
    brake: float = DEFAULT_BRAKE,
    rest_height: float = 1.0,
) -> Stroke:
    """Chain rise / hold / fall segments through every executed impact.

    The object starts and ends at ``rest_height``; before impact ``k`` it is
    raised to ``events[k].amplitude`` (a bigger preparation, a harder hit).
    Segments tile ``[0, duration]`` exactly, and every impact is a segment
    boundary at precisely ``t_impact``.
    """
    if kind not in IMPACT_KINDS:
        raise StrokeError(f"kind must be one of {IMPACT_KINDS}; got {kind!r}")
    if not events:
        raise StrokeError("a stroke needs at least one impact")
    if min(rise, fall) <= 0 or brake <= 0:
        raise StrokeError(f"rise, fall and brake must be > 0; got {rise}, {fall}, {brake}")
    times = [e.t_impact for e in events]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise StrokeError("impact times must strictly increase")
    if times[0] <= 0 or times[-1] >= duration:
        raise StrokeError(
            f"impacts must lie strictly inside the clip (0, {duration}); "
            f"first={times[0]}, last={times[-1]}"
        )

    segments: list[StrokeSegment] = []
    kinematics: list[StrokeKinematics] = []

    def add(t0: float, t1: float, h0: float, h1: float, easing: str) -> None:
        if t1 > t0:
            segments.append(StrokeSegment(t0, t1, h0, h1, easing))

    def fall_into(event: ImpactEvent, *, from_t: float, apex: float) -> None:
        T = event.t_impact
        D = min(fall, T - from_t)
        add(from_t, T - D, apex, apex, "linear")  # hold at the apex
        if kind == "surface":
            add(T - D, T, apex, 0.0, "ease_in")
            b, t_peak = 0.0, T
        else:
            b = min(brake, D / 2.0)
            d = apex * b / D
            add(T - D, T - b, apex, d, "ease_in")
            add(T - b, T, d, 0.0, "ease_out")
            t_peak = T - b
        kinematics.append(
            StrokeKinematics(event.index, kind, T, t_peak, 2.0 * apex / D, apex, D, b)
        )

    def rise_from(t: float, *, longest: float, to: float) -> float:
        top = t + min(rise, longest)
        add(t, top, 0.0, to, "ease_out" if kind == "surface" else "ease_in_out")
        return top

    fall_into(events[0], from_t=0.0, apex=events[0].amplitude)
    # The clip opens at rest height; ease to the first apex during the hold.
    if rest_height != events[0].amplitude and segments[0].easing == "linear":
        first = segments[0]
        segments[0] = StrokeSegment(first.t0, first.t1, rest_height, first.h1, "ease_in_out")
    for k, event in enumerate(events):
        if k + 1 < len(events):
            nxt = events[k + 1]
            half = (nxt.t_impact - event.t_impact) / 2.0
            top = rise_from(event.t_impact, longest=half, to=nxt.amplitude)
            fall_into(nxt, from_t=top, apex=nxt.amplitude)
        else:
            top = rise_from(event.t_impact, longest=duration - event.t_impact, to=rest_height)
            add(top, duration, rest_height, rest_height, "linear")
    _check_tiling(segments, duration)
    return Stroke(kind, duration, tuple(segments), tuple(kinematics))


def _check_tiling(segments: Sequence[StrokeSegment], duration: float) -> None:
    """The segments must cover ``[0, duration]`` with no gap and no overlap."""
    if segments[0].t0 != 0.0 or abs(segments[-1].t1 - duration) > 1e-9:
        raise StrokeError(
            f"stroke covers [{segments[0].t0}, {segments[-1].t1}], not [0, {duration}]"
        )
    for a, b in zip(segments, segments[1:]):
        if a.t1 != b.t0 or abs(a.h1 - b.h0) > 1e-12:
            raise StrokeError(f"stroke is discontinuous between {a} and {b}")
