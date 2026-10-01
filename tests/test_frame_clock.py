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


def test_jitter_at_its_limit_never_overlaps_or_reorders_frames():
    base = FrameClock(fps=30, exposure=0.5)
    clock = FrameClock(fps=30, exposure=0.5, jitter_sd=base.max_jitter / 2, seed=3)
    frames = clock.frames(20.0)
    for a, b in zip(frames, frames[1:]):
        assert a.t_close <= b.t_open
    offsets = [f.t_open - f.t_nominal for f in frames[1:-1]]
    assert max(abs(o) for o in offsets) <= clock.max_jitter + 1e-12
    assert np.std(offsets) == pytest.approx(clock.jitter_sd, rel=0.15)


def test_a_jitter_the_clamp_would_shrink_is_refused_not_honoured_silently():
    with pytest.raises(FrameClockError, match="cannot be honoured"):
        FrameClock(fps=30, exposure=0.9, jitter_sd=0.004)
    with pytest.raises(FrameClockError, match="cannot be honoured"):
        FrameClock(fps=30, exposure=1.0, jitter_sd=1e-6)  # no room at all


def test_report_noise_moves_the_timestamp_and_nothing_else():
    clean = FrameClock(fps=30, seed=4).frames(2.0)
    noisy = FrameClock(fps=30, seed=4, report_noise_sd=0.003).frames(2.0)
    assert [f.samples for f in noisy] == [f.samples for f in clean]
    diffs = np.array([n.t_reported - c.t_reported for n, c in zip(noisy, clean)])
    assert diffs.std() == pytest.approx(0.003, rel=0.3) and (diffs != 0).all()


def test_phase_offsets_every_instant_by_a_sub_frame_amount():
    frames = FrameClock(fps=30, phase=0.01).frames(1.0)
    assert [f.t_open for f in frames[:-1]] == pytest.approx([i / 30 + 0.01 for i in range(29)])


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
        {"report_noise_sd": math.nan},
        {"phase": 1 / 30},  # a whole frame is a scene shift, not a camera phase
        {"phase": math.nan},
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
        # Since an#247 the core frame stage writes every frame file, so the
        # screenshot is taken to BYTES; `path` is logged to prove it stays None.
        self.log.append(("shot", path))
        return f"shot-{len(self.log)}".encode()


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
    """One seek and one capture per frame, in order -- and the screenshot's own
    bytes reach each frame file untouched (nothing decoded at supersample 1).

    Before an#247 the page wrote the file itself (`screenshot(path=...)`); the
    core frame stage now writes every engine's frames, so this pins the bytes
    rather than the keyword."""
    page = _FakePage()
    # The screenshot path by name: it is no longer the default (an#192).
    _capture_frames(page, 3, 30, tmp_path, capture="screenshot")
    assert page.log == [
        ("t", 0.0),
        ("shot", None),
        ("t", 1 / 30),
        ("shot", None),
        ("t", 2 / 30),
        ("shot", None),
    ]
    assert [
        (tmp_path / (DEFAULT_FRAME_PNG_PATTERN % i)).read_bytes() for i in range(3)
    ] == [b"shot-2", b"shot-4", b"shot-6"]


def test_single_instant_frame_samples_capture_exactly_those_instants(tmp_path):
    page = _FakePage()
    _capture_frames(
        page, 2, 30, tmp_path, frame_samples=((0.01,), (0.05,)), capture="screenshot"
    )
    assert [e for e in page.log if e[0] == "t"] == [("t", 0.01), ("t", 0.05)]
    assert [e[1] for e in page.log if e[0] == "shot"] == [None, None]
    assert sorted(p.name for p in tmp_path.glob("*.png")) == [
        DEFAULT_FRAME_PNG_PATTERN % 0,
        DEFAULT_FRAME_PNG_PATTERN % 1,
    ]
