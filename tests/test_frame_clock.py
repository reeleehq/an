"""The frame clock and the render seam it feeds (``RenderContext.frame_samples``).

The default lane covers the clock, the temporal mean's rounding, validation,
and the capture loop's single-sample path through a fake page — which is the
path every existing render takes, so "off is free" is asserted without a
browser. The averaging path needs Pillow and is covered by the browser-marked
render test in `tests/test_impacts.py`.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from an.adapters._base import RenderContext
from an.adapters.cutout.render import DEFAULT_FRAME_PNG_PATTERN, _capture_frames
from an.adapters.cutout.shutter import (
    ShutterError,
    check_frame_samples,
    temporal_mean,
)
from an.frame_clock import FrameClock, FrameClockError, frame_count


# --- the clock ----------------------------------------------------------------


def test_the_default_clock_is_the_old_grid_exactly():
    for fps, duration in [(24, 1.0), (30, 2.5), (60, 0.5), (29.97, 3.0)]:
        got = FrameClock(fps=fps).sample_times(duration)
        n = max(1, int(round(duration * fps)))
        assert got == tuple((i / fps,) for i in range(n)), fps


def test_frame_count_is_the_renderers_rule():
    """The clock and `CutoutRenderer.render` must agree on the frame count, or
    `check_frame_samples` refuses the render."""
    for d, fps in [(2.8, 30), (1.0 / 3, 24), (0.001, 60), (13.37, 29.97)]:
        assert frame_count(d, fps) == max(1, int(round(d * fps)))
        assert len(FrameClock(fps=fps).frames(d)) == frame_count(d, fps)


def test_an_open_shutter_integrates_midpoints_of_the_exposure():
    clock = FrameClock(fps=10, exposure=0.5, samples=4)
    f = clock.frames(1.0)[3]
    assert (f.t_open, f.t_close) == pytest.approx((0.3, 0.35))
    assert f.samples == pytest.approx((0.30625, 0.31875, 0.33125, 0.34375))
    assert f.t_mid == pytest.approx(sum(f.samples) / 4)


def test_jitter_is_clamped_so_frames_never_overlap_or_reorder():
    clock = FrameClock(fps=30, exposure=0.5, jitter_sd=1.0, seed=3)  # absurd sd
    frames = clock.frames(5.0)
    for a, b in zip(frames, frames[1:]):
        assert a.t_close <= b.t_open
    offsets = [f.t_open - f.t_nominal for f in frames[1:-1]]
    assert max(abs(o) for o in offsets) <= clock.max_jitter + 1e-12
    assert any(abs(o) > 0 for o in offsets)


def test_jitter_is_seeded_and_timestamps_report_what_was_asked():
    a = FrameClock(fps=30, jitter_sd=0.003, seed=1)
    assert a.frames(1.0) == FrameClock(fps=30, jitter_sd=0.003, seed=1).frames(1.0)
    assert a.frames(1.0) != FrameClock(fps=30, jitter_sd=0.003, seed=2).frames(1.0)
    assert all(f.t_reported == f.t_nominal for f in a.frames(1.0))
    actual = FrameClock(fps=30, jitter_sd=0.003, seed=1, timestamps="actual")
    assert all(f.t_reported == f.t_open for f in actual.frames(1.0))


def test_every_instant_is_inside_the_timeline():
    frames = FrameClock(fps=30, exposure=1.0, phase=0.02, samples=3).frames(1.0)
    assert all(0.0 <= t <= 1.0 for f in frames for t in f.samples)
    assert check_frame_samples(
        [f.samples for f in frames], total_frames=len(frames), duration=1.0
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fps": 0},
        {"fps": math.inf},
        {"exposure": 1.5},
        {"samples": 0},
        {"samples": 4},  # an instantaneous shutter has one instant
        {"jitter_sd": -1},
        {"timestamps": "wallclock"},
    ],
)
def test_an_impossible_camera_is_refused(kwargs):
    with pytest.raises(FrameClockError):
        FrameClock(**kwargs)


# --- the temporal mean --------------------------------------------------------


def test_the_temporal_mean_rounds_half_to_even_exactly():
    rng = np.random.default_rng(0)
    for k in (2, 3, 4, 8):
        frames = [rng.integers(0, 256, (7, 5, 3), dtype=np.uint8) for _ in range(k)]
        exact = np.stack(frames).astype(np.float64).mean(axis=0)
        assert (temporal_mean(frames) == np.rint(exact).astype(np.uint8)).all(), k


def test_frame_samples_are_validated_before_a_render():
    with pytest.raises(ShutterError, match="has 2"):
        check_frame_samples([[0.0], [0.1], [0.2]], total_frames=2, duration=1.0)
    with pytest.raises(ShutterError, match="outside"):
        check_frame_samples([[0.0], [1.5]], total_frames=2, duration=1.0)
    with pytest.raises(ShutterError, match="no sample"):
        check_frame_samples([[0.0], []], total_frames=2, duration=1.0)


def test_render_context_defaults_to_no_frame_samples():
    ctx = RenderContext(mall={}, work_dir=None)  # type: ignore[arg-type]
    assert ctx.frame_samples is None


# --- the capture loop's seam, with a fake page ---------------------------------


class _FakeCanvas:
    def __init__(self, log):
        self.log = log

    def screenshot(self, path=None, omit_background=False):
        self.log.append(("shot", path))
        return b""


class _FakePage:
    def __init__(self):
        self.log = []

    def evaluate(self, js, t):
        assert js == "(t) => window.anSetTime(t)"
        self.log.append(("t", t))

    def locator(self, selector):
        assert selector == "#stage"
        return _FakeCanvas(self.log)


def test_no_frame_samples_is_the_old_capture_call_for_call(tmp_path):
    page = _FakePage()
    _capture_frames(page, 3, 30, tmp_path)
    assert page.log == [
        ("t", 0.0),
        ("shot", str(tmp_path / (DEFAULT_FRAME_PNG_PATTERN % 0))),
        ("t", 1 / 30),
        ("shot", str(tmp_path / (DEFAULT_FRAME_PNG_PATTERN % 1))),
        ("t", 2 / 30),
        ("shot", str(tmp_path / (DEFAULT_FRAME_PNG_PATTERN % 2))),
    ]


def test_single_instant_frame_samples_capture_exactly_those_instants(tmp_path):
    page = _FakePage()
    _capture_frames(page, 2, 30, tmp_path, frame_samples=((0.01,), (0.05,)))
    assert [e for e in page.log if e[0] == "t"] == [("t", 0.01), ("t", 0.05)]
    assert [e[1] for e in page.log if e[0] == "shot"] == [
        str(tmp_path / (DEFAULT_FRAME_PNG_PATTERN % 0)),
        str(tmp_path / (DEFAULT_FRAME_PNG_PATTERN % 1)),
    ]
