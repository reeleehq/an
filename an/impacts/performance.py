"""The performance: a tempo grid, and when each impact was intended and executed.

Three times are kept apart on purpose, because scoring a sub-frame estimator is
meaningless if they blur together:

- ``t_grid`` — the INTENDED time: where the beat grid (a :class:`TempoMap`) put
  the event. What a quantiser would snap to.
- ``t_impact`` — the EXECUTED time, in continuous seconds: the grid time plus a
  humanisation offset. This is when the object actually hits (or, in the air,
  turns); the motion is built so it happens at exactly this float, never on a
  frame.
- what the frames show — not here at all; that is :mod:`an.impacts.truth`,
  after a :class:`an.frame_clock.FrameClock` has sampled the motion.

>>> events = perform(120, beats=4)
>>> [e.t_grid for e in events]
[0.5, 1.0, 1.5, 2.0]
>>> all(e.t_impact == e.t_grid for e in events)   # no humanisation by default
True

A tempo change is a :class:`TempoMap` with more than one point — here an
accelerando from 60 to 120 BPM over four beats, so the gaps shrink:

>>> ts = [e.t_grid for e in perform([(0, 60), (4, 120)], beats=5, lead_in=0.0)]
>>> [round(b - a, 3) for a, b in zip(ts, ts[1:])]
[0.893, 0.729, 0.617, 0.534]
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Union

__all__ = [
    "DEFAULT_LEAD_IN",
    "MAX_OFFSET_FRACTION",
    "Humanizer",
    "ImpactEvent",
    "PerformanceError",
    "TempoMap",
    "TempoSpec",
    "gaussian_humanizer",
    "perform",
    "tempo_map",
]

#: Seconds before the first grid beat. Long enough for the first stroke's
#: preparation and for any humanisation to pull the first impact early.
DEFAULT_LEAD_IN: float = 0.5

#: A humanisation offset is clamped to this fraction of the gap to each
#: neighbouring grid event, so executed impacts can never swap order or
#: collide — whatever the jitter's standard deviation.
MAX_OFFSET_FRACTION: float = 0.4

TempoSpec = Union[float, Sequence[Sequence[float]], "TempoMap"]

#: ``(grid_times, rng) -> offsets``, in seconds, one per grid time. The seam for
#: timing models richer than :func:`gaussian_humanizer` (a learned groove, a
#: drummer's measured microtiming).
Humanizer = Callable[[Sequence[float], object], Sequence[float]]


class PerformanceError(ValueError):
    """A performance description that cannot be played."""


@dataclass(frozen=True, slots=True)
class TempoMap:
    """Tempo as a function of beat: piecewise-linear BPM between ``(beat, bpm)`` points.

    Constant before the first point and after the last. Linear in BEATS, not in
    seconds, which is how a score writes an accelerando ("speed up over these
    four bars"); the time of a beat is the exact integral of ``60 / bpm``.

    >>> TempoMap(((0, 120),)).time_of(3)
    1.5
    >>> m = TempoMap(((0, 60), (4, 120)))
    >>> round(m.time_of(4), 6)   # 4 * 60/(120-60) * ln(120/60)
    2.772589
    >>> m.bpm_at(2), m.bpm_at(10)
    (90.0, 120.0)
    """

    points: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if not self.points:
            raise PerformanceError("a tempo map needs at least one (beat, bpm) point")
        beats = [b for b, _ in self.points]
        if any(b2 <= b1 for b1, b2 in zip(beats, beats[1:])):
            raise PerformanceError(f"tempo points must have increasing beats: {beats}")
        if any(not (math.isfinite(bpm) and bpm > 0) for _, bpm in self.points):
            raise PerformanceError(f"every bpm must be positive: {self.points}")

    def bpm_at(self, beat: float) -> float:
        pts = self.points
        if beat <= pts[0][0]:
            return float(pts[0][1])
        for (b0, v0), (b1, v1) in zip(pts, pts[1:]):
            if beat <= b1:
                return v0 + (v1 - v0) * (beat - b0) / (b1 - b0)
        return float(pts[-1][1])

    def time_of(self, beat: float) -> float:
        """Seconds from beat 0 to ``beat`` (``beat >= 0``)."""
        if beat < 0:
            raise PerformanceError(f"beat must be >= 0; got {beat}")
        knots = sorted({0.0, float(beat), *(b for b, _ in self.points if 0 < b < beat)})
        return sum(self._segment_time(a, b) for a, b in zip(knots, knots[1:]))

    def _segment_time(self, a: float, b: float) -> float:
        # Within [a, b] the bpm is linear (knots include every tempo point).
        va, vb = self.bpm_at(a), self.bpm_at(b)
        if math.isclose(va, vb, rel_tol=0, abs_tol=1e-12):
            return 60.0 * (b - a) / va
        slope = (vb - va) / (b - a)
        return 60.0 / slope * math.log(vb / va)

    def to_dict(self) -> dict:
        return {"points": [list(p) for p in self.points]}


def tempo_map(tempo: TempoSpec) -> TempoMap:
    """Coerce a bpm, a ``[(beat, bpm), ...]`` list, or a :class:`TempoMap`.

    >>> tempo_map(90).points
    ((0.0, 90.0),)
    >>> tempo_map([(0, 90), (16, 120)]).points
    ((0.0, 90.0), (16.0, 120.0))
    """
    if isinstance(tempo, TempoMap):
        return tempo
    if isinstance(tempo, (int, float)):
        return TempoMap(((0.0, float(tempo)),))
    return TempoMap(tuple((float(b), float(v)) for b, v in tempo))


def gaussian_humanizer(
    sd: float = 0.0, *, rho: float = 0.0, bias: float = 0.0
) -> Humanizer:
    """Offsets from an AR(1) Gaussian process: ``o[k] = bias + rho*(o[k-1]-bias) + e``.

    ``sd`` is the STATIONARY standard deviation of the offsets (seconds) — the
    innovation is scaled by ``sqrt(1 - rho**2)`` so changing ``rho`` changes how
    the timing wanders, not how far. ``rho = 0`` is independent jitter;
    ``rho`` near 1 is a player who drifts ahead or behind for several beats.
    ``bias`` is a constant lead (negative) or lag (positive).

    >>> import numpy as np
    >>> h = gaussian_humanizer(0.01, rho=0.5)
    >>> offs = h([0.0] * 20000, np.random.default_rng(0))
    >>> round(float(np.std(offs)), 3)
    0.01
    >>> gaussian_humanizer()([0.0, 1.0], None)
    [0.0, 0.0]
    """
    if sd < 0 or not -1.0 < rho < 1.0:
        raise PerformanceError(f"need sd >= 0 and -1 < rho < 1; got sd={sd}, rho={rho}")

    def humanize(grid: Sequence[float], rng: object) -> list[float]:
        if sd == 0.0:
            return [bias] * len(grid)
        innovation = sd * math.sqrt(1.0 - rho * rho)
        out, prev = [], rng.normal(0.0, sd)  # stationary start
        for _ in grid:
            out.append(bias + prev)
            prev = rho * prev + rng.normal(0.0, innovation)
        return out

    return humanize


@dataclass(frozen=True, slots=True)
class ImpactEvent:
    """One impact: where the grid put it and when it was executed."""

    index: int
    beat: float
    t_grid: float
    t_impact: float
    amplitude: float

    @property
    def offset(self) -> float:
        """``t_impact - t_grid``: the humanisation actually applied (post-clamp)."""
        return self.t_impact - self.t_grid

    def to_dict(self) -> dict:
        return {**asdict(self), "offset": self.offset}


def perform(
    tempo: TempoSpec = 100.0,
    *,
    beats: int = 16,
    subdivision: int = 1,
    pattern: Sequence[float] = (1.0,),
    lead_in: float = DEFAULT_LEAD_IN,
    humanizer: Humanizer | None = None,
    seed: int = 0,
) -> tuple[ImpactEvent, ...]:
    """The impacts of ``beats`` beats of ``pattern``, on ``tempo``'s grid.

    ``subdivision`` grid steps per beat; ``pattern`` is cycled over the steps,
    one value per step: ``0`` is a rest, anything in ``(0, 1]`` is a hit of that
    relative stroke height (an accent is a bigger stroke). ``lead_in`` shifts
    beat 0 to that many seconds into the clip. ``humanizer`` turns grid times
    into offsets (default: none); each offset is then clamped to
    :data:`MAX_OFFSET_FRACTION` of the gap to either neighbour, and the clamped
    value is what the event records — the ground truth is what was executed.

    >>> [e.beat for e in perform(120, beats=2, subdivision=2, pattern=(1, 0))]
    [0.0, 1.0]
    >>> [e.amplitude for e in perform(120, beats=1, subdivision=4, pattern=(1, .5))]
    [1.0, 0.5, 1.0, 0.5]
    """
    import numpy as np

    if beats < 1 or subdivision < 1:
        raise PerformanceError(f"need beats >= 1, subdivision >= 1; got {beats}, {subdivision}")
    if not pattern or any(not 0.0 <= float(a) <= 1.0 for a in pattern):
        raise PerformanceError(f"pattern values must lie in [0, 1]; got {list(pattern)}")
    if not any(pattern):
        raise PerformanceError("pattern has no hits (all zeros)")
    if lead_in < 0:
        raise PerformanceError(f"lead_in must be >= 0; got {lead_in}")
    tmap = tempo_map(tempo)
    steps = beats * subdivision
    grid = []
    for step in range(steps):
        amplitude = float(pattern[step % len(pattern)])
        if amplitude > 0:
            beat = step / subdivision
            grid.append((beat, lead_in + tmap.time_of(beat), amplitude))
    times = [t for _, t, _ in grid]
    rng = np.random.default_rng(seed)
    offsets = list((humanizer or gaussian_humanizer())(times, rng))
    if len(offsets) != len(times):
        raise PerformanceError(
            f"humanizer returned {len(offsets)} offsets for {len(times)} events"
        )
    events = []
    for k, ((beat, t, amplitude), offset) in enumerate(zip(grid, offsets)):
        gaps = [t - times[k - 1]] if k else [t]  # never before the clip starts
        if k + 1 < len(times):
            gaps.append(times[k + 1] - t)
        cap = MAX_OFFSET_FRACTION * min(gaps)
        clamped = min(max(float(offset), -cap), cap)
        events.append(ImpactEvent(k, beat, t, t + clamped, amplitude))
    return tuple(events)
