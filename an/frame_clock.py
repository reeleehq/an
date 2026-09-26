"""The frame clock: WHEN each output frame samples scene time.

A render has always sampled frame ``i`` at exactly ``i / fps`` — one instant,
on a perfect grid. A real camera does neither: its shutter stays open for part
of the frame period (so a moving object smears), and its capture instants
wander around the nominal grid (so the timestamp a frame carries is not quite
when it was taken). Anything that wants to *measure* motion from video — the
sub-frame impact estimators :mod:`an.impacts` exists to score — needs both, and
needs to know exactly what was done.

:class:`FrameClock` is that model as data. :meth:`FrameClock.frames` returns one
:class:`CapturedFrame` per output frame, carrying the exposure interval and the
instants integrated over it; :meth:`FrameClock.sample_times` is the projection
the renderer consumes through ``RenderContext.frame_samples``. One object feeds
both the render and the ground truth, so the two cannot disagree about when a
frame was taken.

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

import math
from dataclasses import asdict, dataclass
from typing import Literal

__all__ = [
    "DEFAULT_EXPOSURE_SAMPLES",
    "MAX_JITTER_FRACTION",
    "MAX_REPORT_NOISE_FRACTION",
    "CapturedFrame",
    "FrameClock",
    "FrameClockError",
    "frame_count",
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

Timestamps = Literal["nominal", "actual"]


class FrameClockError(ValueError):
    """A frame clock that cannot describe a camera."""


def frame_count(duration: float, fps: float) -> int:
    """Frames in a render of ``duration`` seconds — the renderer's own rule.

    >>> frame_count(2.0, 30), frame_count(0.01, 30)
    (60, 1)
    """
    return max(1, int(round(duration * fps)))


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
                raise FrameClockError(f"{name} must be a finite number >= 0; got {value!r}")
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
        return [float(v) for v in np.clip(rng.normal(0.0, self.jitter_sd, n), -cap, cap)]

    def _report_noise(self, n: int) -> list[float]:
        if self.report_noise_sd == 0.0:
            return [0.0] * n
        import numpy as np

        rng = np.random.default_rng([self.seed, 1])
        cap = MAX_REPORT_NOISE_FRACTION / self.fps
        return [float(v) for v in np.clip(rng.normal(0.0, self.report_noise_sd, n), -cap, cap)]
