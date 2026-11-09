"""The frame clock: WHEN each output frame samples scene time.

A render has always sampled frame ``i`` at exactly ``i / fps`` — one instant,
on a perfect grid. A real camera does neither: its shutter stays open for part
of the frame period (so a moving object smears), and its capture instants
wander around the nominal grid (so the timestamp a frame carries is not quite
when it was taken). Anything that wants to *measure* motion from video — the
sub-frame impact estimators :mod:`cutan.impacts` exists to score — needs both, and
needs to know exactly what was done.

:class:`FrameClock` is that model as data. :meth:`FrameClock.frames` returns one
:class:`CapturedFrame` per output frame, carrying the exposure interval and the
instants integrated over it; :meth:`FrameClock.sample_times` is the projection
the renderer consumes through ``RenderContext.frame_samples``. One object feeds
both the render and the ground truth, so the two cannot disagree about when a
frame was taken.

It also owns the GRIDS a shot is laid onto, the pure rules every layer shares
(the IR's camera, the stage's compiler and solve): :func:`frame_times` (every
frame, the end included), :func:`step_times` (a stepped shot's pose grid,
an#89), :func:`grid_times` (one or the other, the solve's grid) and
:func:`camera_grid` (an#626), the instants a camera the runtime cannot
evaluate itself — a follow, a dolly — is keyed at so that every instant the
render samples, a shutter's sub-frame ones included, lands on an exact key.

The default clock is the old behaviour exactly — no exposure, no jitter, one
sample at ``i / fps``:

>>> FrameClock(fps=4).sample_times(1.0)
((0.0,), (0.25,), (0.5,), (0.75,))

A 180-degree shutter (``exposure=0.5``) integrates the first half of each frame
period, sampled at the midpoints of ``samples`` equal sub-intervals:

>>> FrameClock(fps=4, exposure=0.5, samples=2).sample_times(0.5)
((0.03125, 0.09375), (0.28125, 0.34375))
>>> f = FrameClock(fps=4, exposure=0.5, samples=2).frames(0.5)[1]
>>> (f.t_nominal, f.t_open, f.t_close, f.t_mid)
(0.25, 0.25, 0.375, 0.3125)

Capture jitter moves each frame's exposure as a unit, never out of order:

>>> clock = FrameClock(fps=30, jitter_sd=0.004, seed=7)
>>> opens = [f.t_open for f in clock.frames(2.0)]
>>> all(b > a for a, b in zip(opens, opens[1:]))
True
>>> clock.frames(2.0) == clock.frames(2.0)  # seeded: the same clock twice
True
"""

from __future__ import annotations

import bisect
import math
from dataclasses import asdict, dataclass
from typing import Literal, Sequence

__all__ = [
    "DEFAULT_EXPOSURE_SAMPLES",
    "MAX_JITTER_FRACTION",
    "MAX_REPORT_NOISE_FRACTION",
    "SAMPLE_MERGE_EPS",
    "STEP_GRID_EPS",
    "CameraGrid",
    "CapturedFrame",
    "FrameClock",
    "FrameClockError",
    "camera_grid",
    "frame_count",
    "frame_times",
    "grid_times",
    "step_times",
]

#: Sub-samples integrated per frame when the shutter is open and the caller did
#: not say how many. Eight midpoint samples put the smear of an object crossing
#: 100 px in one exposure at steps of ~12 px — continuous to a tracker, cheap to
#: render (each sample is one screenshot).
DEFAULT_EXPOSURE_SAMPLES: int = 8

#: A frame's capture offset is clamped to this fraction of the slack between
#: one exposure closing and the next opening, on each side. Below one half, so
#: two neighbouring frames can each move toward the other by the full clamp and
#: still not overlap: the clock never reorders frames, whatever ``jitter_sd`` is.
MAX_JITTER_FRACTION: float = 0.49

#: Report noise is clamped to this fraction of the frame period, each side, so
#: two neighbouring reported timestamps can never cross on a regular grid.
MAX_REPORT_NOISE_FRACTION: float = 0.24

#: A step instant this close to the end of a span is not a step of it
#: (``0.25 s × 12 Hz`` is 3 steps, not 4, whatever the float product rounds to).
STEP_GRID_EPS: float = 1e-9

#: Two camera key instants closer than this (s) are one key: a shutter sample
#: that IS a frame up to float noise adds no key beside it (two keys a
#: femtosecond apart would only divide by that femtosecond).
SAMPLE_MERGE_EPS: float = 1e-9

Timestamps = Literal["nominal", "actual"]
CameraEasing = Literal["linear", "step"]


class FrameClockError(ValueError):
    """A frame clock that cannot describe a camera."""


def frame_count(duration: float, fps: float) -> int:
    """Frames in a render of ``duration`` seconds — the renderer's own rule.

    >>> frame_count(2.0, 30), frame_count(0.01, 30)
    (60, 1)
    """
    return max(1, int(round(duration * fps)))


def frame_times(duration: float, *, fps: float) -> list[float]:
    """The time of every frame a ``duration`` render draws, the end included
    (``k / fps``, the renderer's own expression, capped at ``duration``).

    THE frame grid rule (an#626). ``an.ir.camera.frame_times`` is this very
    function re-exported, and ``an.stage.solve.frame_times`` a thin wrapper
    over :func:`grid_times`; neither restates it.

    >>> frame_times(0.5, fps=4)
    [0.0, 0.25, 0.5]
    """
    return [min(duration, n / fps) for n in range(frame_count(duration, fps) + 1)]


def step_times(start: float, duration: float, step_hz: float) -> list[float]:
    """Clip-local times at which a stepped tween updates its pose (an#89).

    The grid is SHOT-wide — multiples of ``1/step_hz`` on the shot's clock,
    shared by every tween in the shot — not the tween's own: "on twos" means
    every character changes pose on the same frames, so a tween starting at
    0.033 s updates at the next grid point, not 0.033 s later. (Shots compile
    independently, so the grid restarts at each cut.) Local 0 (the tween's
    start) and ``duration`` (where the end value lands) are always present, so
    a tween shorter than one step is a single step to its end value.

    ``step_hz`` must be positive: with a non-positive rate the walk below never
    reaches ``duration`` — an infinite loop, not an error — so it is refused.

    >>> step_times(0.0, 0.3, 10)
    [0.0, 0.1, 0.2, 0.3]
    >>> [round(t, 3) for t in step_times(0.05, 0.3, 10)]
    [0.0, 0.05, 0.15, 0.25, 0.3]
    >>> step_times(0.0, 0.02, 10)
    [0.0, 0.02]
    """
    if not step_hz > 0:
        raise ValueError(f"step_hz must be positive; got {step_hz!r}")
    eps = STEP_GRID_EPS
    j = math.ceil(start * step_hz - eps)
    times = [0.0]
    while True:
        t = j / step_hz - start
        if t >= duration - eps:
            break
        if t > eps:
            times.append(t)
        j += 1
    times.append(float(duration))
    return times


def grid_times(
    duration: float, *, fps: float, step_hz: float | None = None
) -> list[float]:
    """A shot's own grid: every frame (:func:`frame_times`), or its step grid
    (:func:`step_times`) under ``step_hz``. What the solve runs at.

    >>> grid_times(0.1, fps=20)
    [0.0, 0.05, 0.1]
    >>> grid_times(0.25, fps=20, step_hz=10)
    [0.0, 0.1, 0.2, 0.25]
    """
    if step_hz:
        return step_times(0.0, duration, step_hz)
    return frame_times(duration, fps=fps)


@dataclass(frozen=True, slots=True)
class CameraGrid:
    """Where a camera the runtime cannot evaluate itself is keyed (an#626).

    ``times``: the key instants, sorted. ``easing``: the keys' easing —
    ``"linear"`` on ones, ``"step"`` on a stepped shot (the camera holds
    between keys as a stepped tween holds between poses). ``base``: the
    grid the camera is COMPUTED on — every frame, and every step instant on a
    stepped shot — before the render's sample instants are added (a follow's
    lag runs over it); ``times`` is a superset of it.
    """

    times: tuple[float, ...]
    base: tuple[float, ...]
    easing: CameraEasing

    @property
    def stepped(self) -> bool:
        return self.easing == "step"


def camera_grid(
    duration: float,
    *,
    fps: float,
    step_hz: float | None = None,
    frame_samples: Sequence[Sequence[float]] | None = None,
    sample_fps: float | None = None,
    merge_eps: float = SAMPLE_MERGE_EPS,
) -> CameraGrid:
    """The ONE sampler for a non-affine camera — a follow, a dolly, anything
    the runtime cannot evaluate from a few eased keys (an#626).

    On ones (``step_hz`` unset) the camera is keyed at every frame
    (:func:`frame_times`), linearly. On a stepped shot it is keyed at every
    frame AND every step instant (:func:`step_times`), step-eased: it holds
    between keys as the stepped poses hold, so a step is a cut, not a
    one-frame ramp. The step grid alone would not do: a tween's end lands off
    it, and the frames keep the camera exact where the target already moved.

    ``frame_samples`` (``RenderContext.frame_samples``, a
    :class:`FrameClock`'s :meth:`~FrameClock.sample_times`) adds every
    instant the render actually samples — a shutter's sub-frame ones, a
    jittered capture's — clipped to ``[0, duration]``, so each lands on an
    exact key instead of between two. An instant within ``merge_eps`` of a
    key already there is that key. ``None`` adds nothing: the keys are
    exactly the frame grid they always were. They must describe THIS shot:
    one entry per frame (:func:`frame_count`) at ``sample_fps``, the rate the
    render samples at (a camera's 29.97, where the compiled grid's ``fps`` is
    rounded to 30; ``fps`` when unset), or a :class:`FrameClockError`:
    another shot's samples would key the camera at the wrong instants.

    >>> camera_grid(0.5, fps=4)
    CameraGrid(times=(0.0, 0.25, 0.5), base=(0.0, 0.25, 0.5), easing='linear')
    >>> camera_grid(0.5, fps=4, frame_samples=((0.0,), (0.3, 0.6))).times
    (0.0, 0.25, 0.3, 0.5)
    >>> g = camera_grid(0.5, fps=4, step_hz=3)
    >>> [round(t, 3) for t in g.times], g.easing, g.base == g.times
    ([0.0, 0.25, 0.333, 0.5], 'step', True)
    >>> len(camera_grid(20.0, fps=30, frame_samples=[(k / 29.97,) for k in range(599)], sample_fps=29.97).times) > 600
    True
    >>> camera_grid(0.5, fps=4, frame_samples=((0.0,),))
    Traceback (most recent call last):
      ...
    an.frame_clock.FrameClockError: frame_samples describes 1 frame(s) but a 0.5 s shot at 4 fps has 2: they are another shot's samples.
    """
    base = frame_times(duration, fps=fps)
    if step_hz:
        _merge_into(base, step_times(0.0, duration, step_hz), eps=merge_eps)
    times = list(base)
    if frame_samples is not None:
        rate = sample_fps or fps
        frames = frame_count(duration, rate)
        if len(frame_samples) != frames:
            raise FrameClockError(
                f"frame_samples describes {len(frame_samples)} frame(s) but a "
                f"{duration:g} s shot at {rate:g} fps has {frames}: they are "
                "another shot's samples."
            )
        instants = [float(t) for frame in frame_samples for t in frame]
        bad = [t for t in instants if not math.isfinite(t)]
        if bad:
            raise FrameClockError(
                f"frame_samples holds non-finite instants {bad[:3]}: a render "
                "samples a scene at real times only."
            )
        _merge_into(
            times, [min(max(t, 0.0), duration) for t in instants], eps=merge_eps
        )
    return CameraGrid(
        times=tuple(times),
        base=tuple(base),
        easing="step" if step_hz else "linear",
    )


def _merge_into(times: list[float], extra: Sequence[float], *, eps: float) -> None:
    """Insert each of ``extra`` into the sorted ``times`` unless one is within
    ``eps`` of it already (the instants already there win)."""
    for t in sorted(set(extra)):
        i = bisect.bisect_left(times, t)
        near = (i > 0 and t - times[i - 1] <= eps) or (
            i < len(times) and times[i] - t <= eps
        )
        if not near:
            times.insert(i, t)


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """One output frame: when its exposure opened and closed, and what it saw.

    ``t_nominal`` is ``index / fps`` — what a constant-rate container (an mp4)
    says the frame's time is. ``samples`` are the instants actually rendered
    and averaged into it; ``t_mid`` is the middle of the exposure, the single
    best instant to attribute a blurred frame to. ``t_reported`` is the
    timestamp a capture pipeline hands downstream: nominal or actual, per the
    clock's ``timestamps`` setting.
    """

    index: int
    t_nominal: float
    t_open: float
    t_close: float
    samples: tuple[float, ...]
    t_reported: float

    @property
    def t_mid(self) -> float:
        return (self.t_open + self.t_close) / 2.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["samples"] = list(self.samples)
        d["t_mid"] = self.t_mid
        return d


@dataclass(frozen=True, slots=True)
class FrameClock:
    """A camera's timing, as data. Every field defaults to the ideal camera.

    ``fps``: nominal frame rate (need not be an integer: 29.97 is a camera).
    ``exposure``: fraction of the frame period the shutter is open, in
    ``[0, 1]``; 0 is an instantaneous sample, 0.5 a 180-degree shutter.
    ``samples``: instants integrated per open exposure (midpoint rule);
    ``None`` means 1 when ``exposure == 0`` and
    :data:`DEFAULT_EXPOSURE_SAMPLES` otherwise.
    ``jitter_sd``: standard deviation, in seconds, of each frame's CAPTURE
    offset from the nominal grid — the frame really is taken early or late.
    Gaussian, clamped at :attr:`max_jitter` so frames never overlap; a
    ``jitter_sd`` above half that clamp is refused rather than silently
    shrunk (at ``exposure=1`` there is no room for any).
    ``phase``: seconds added to every capture instant — the camera clock's
    sub-frame offset from scene time, in ``(-1/fps, 1/fps)``.
    ``timestamps``: the base of :attr:`CapturedFrame.t_reported` —
    ``"nominal"`` (``index / fps``, what a naive tick loop or an mp4 reports)
    or ``"actual"`` (``t_open``, what a capture API with real timestamps
    reports).
    ``report_noise_sd``: Gaussian noise, in seconds, added to the REPORTED
    timestamp only — regular capture, noisy clock (a browser frame callback).
    Clamped at :data:`MAX_REPORT_NOISE_FRACTION` of a frame period, with the
    same refuse-rather-than-shrink rule as ``jitter_sd``, and reported
    timestamps must still increase: a real frame clock never runs backwards.
    ``seed``: the random streams (capture jitter and report noise are
    independent draws from it).

    Every instant is clipped into ``[0, duration]``, because a render cannot
    sample a scene outside its own timeline; the clipped values are what
    :meth:`frames` returns and what gets rendered.
    """

    fps: float = 30.0
    exposure: float = 0.0
    samples: int | None = None
    jitter_sd: float = 0.0
    phase: float = 0.0
    timestamps: Timestamps = "nominal"
    report_noise_sd: float = 0.0
    seed: int = 0

    def __post_init__(self) -> None:
        if not (math.isfinite(self.fps) and self.fps > 0):
            raise FrameClockError(f"fps must be a positive number; got {self.fps!r}")
        if not 0.0 <= self.exposure <= 1.0:
            raise FrameClockError(
                f"exposure is a fraction of the frame period, in [0, 1]; got "
                f"{self.exposure!r}. 0.5 is a 180-degree shutter."
            )
        if self.samples is not None and self.samples < 1:
            raise FrameClockError(f"samples must be >= 1; got {self.samples!r}")
        if self.exposure == 0.0 and (self.samples or 1) > 1:
            raise FrameClockError(
                f"samples={self.samples} with exposure=0: an instantaneous "
                "shutter has one instant to sample. Set an exposure, or drop "
                "samples."
            )
        for name in ("jitter_sd", "report_noise_sd"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0):
                raise FrameClockError(
                    f"{name} must be a finite number >= 0; got {value!r}"
                )
        if self.jitter_sd > self.max_jitter / 2.0:
            raise FrameClockError(
                f"jitter_sd={self.jitter_sd!r} s cannot be honoured: frames must "
                f"not overlap, which caps a capture offset at {self.max_jitter:.6g} s "
                f"here (fps={self.fps}, exposure={self.exposure}), and a standard "
                "deviation above half the cap would be silently shrunk by it. "
                "Lower jitter_sd or the exposure; for noisy TIMESTAMPS on regular "
                "capture, use report_noise_sd."
            )
        if self.report_noise_sd > MAX_REPORT_NOISE_FRACTION / (2.0 * self.fps):
            raise FrameClockError(
                f"report_noise_sd={self.report_noise_sd!r} s cannot be honoured: "
                f"reported timestamps must keep increasing, which caps the noise at "
                f"{MAX_REPORT_NOISE_FRACTION / self.fps:.6g} s at {self.fps} fps, and a "
                "standard deviation above half the cap would be silently shrunk by it."
            )
        if not (math.isfinite(self.phase) and abs(self.phase) < 1.0 / self.fps):
            raise FrameClockError(
                f"phase must be a sub-frame offset in (-1/fps, 1/fps) = "
                f"(-{1.0 / self.fps:.6g}, {1.0 / self.fps:.6g}); got {self.phase!r}. "
                "A larger shift is a shift of the scene, not of the camera."
            )
        if self.timestamps not in ("nominal", "actual"):
            raise FrameClockError(
                f"timestamps must be 'nominal' or 'actual'; got {self.timestamps!r}"
            )

    @property
    def samples_per_frame(self) -> int:
        """The resolved sample count: 1 for an instantaneous shutter.

        >>> FrameClock().samples_per_frame, FrameClock(exposure=0.5).samples_per_frame
        (1, 8)
        """
        if self.samples is not None:
            return self.samples
        return 1 if self.exposure == 0.0 else DEFAULT_EXPOSURE_SAMPLES

    @property
    def max_jitter(self) -> float:
        """The clamp on a frame's capture offset, in seconds.

        >>> round(FrameClock(fps=10, exposure=0.5).max_jitter, 9)
        0.0245
        """
        return MAX_JITTER_FRACTION * (1.0 - self.exposure) / self.fps

    def frames(self, duration: float) -> tuple[CapturedFrame, ...]:
        """One :class:`CapturedFrame` per output frame of a ``duration`` render."""
        n = frame_count(duration, self.fps)
        offsets, noise = self._offsets(n), self._report_noise(n)
        period = 1.0 / self.fps
        open_for = self.exposure * period
        k = self.samples_per_frame

        def clip(t: float) -> float:
            return min(max(t, 0.0), duration)

        out = []
        for i in range(n):
            # `i / fps`, not `i * period`: the renderer's own expression, so the
            # default clock samples bit-for-bit the instants a plain render does.
            t_nominal = i / self.fps
            t_open = t_nominal + self.phase + offsets[i]
            if open_for == 0.0:
                instants = (clip(t_open),)
            else:
                instants = tuple(
                    clip(t_open + (j + 0.5) / k * open_for) for j in range(k)
                )
            opened, closed = clip(t_open), clip(t_open + open_for)
            out.append(
                CapturedFrame(
                    index=i,
                    t_nominal=t_nominal,
                    t_open=opened,
                    t_close=closed,
                    samples=instants,
                    t_reported=(t_nominal if self.timestamps == "nominal" else opened)
                    + noise[i],
                )
            )
        reported = [f.t_reported for f in out]
        if any(b <= a for a, b in zip(reported, reported[1:])):
            # Reachable only with `timestamps="actual"`, capture jitter AND report
            # noise together: jittered capture can bring two frames within less
            # than the noise's reach of each other.
            raise FrameClockError(
                "reported timestamps would run backwards: with timestamps='actual', "
                "capture jitter and report noise combine past what a monotone clock "
                "allows. Lower jitter_sd or report_noise_sd."
            )
        return tuple(out)

    def sample_times(self, duration: float) -> tuple[tuple[float, ...], ...]:
        """Per frame, the scene instants to render and average — the render seam."""
        return tuple(f.samples for f in self.frames(duration))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["samples_per_frame"] = self.samples_per_frame
        d["max_jitter"] = self.max_jitter
        return d

    def _offsets(self, n: int) -> list[float]:
        if self.jitter_sd == 0.0:
            return [0.0] * n
        import numpy as np

        rng = np.random.default_rng([self.seed, 0])
        cap = self.max_jitter
        return [
            float(v) for v in np.clip(rng.normal(0.0, self.jitter_sd, n), -cap, cap)
        ]

    def _report_noise(self, n: int) -> list[float]:
        if self.report_noise_sd == 0.0:
            return [0.0] * n
        import numpy as np

        rng = np.random.default_rng([self.seed, 1])
        cap = MAX_REPORT_NOISE_FRACTION / self.fps
        return [
            float(v)
            for v in np.clip(rng.normal(0.0, self.report_noise_sd, n), -cap, cap)
        ]
