"""Style lint: measure a render's cadence, cut rate and palette, and compare them to a style's targets.

"Make it in the style of X" is only checkable if X is a set of numbers. The
cut-out styles research (``misc/docs/cutout_styles_research.md``) measured six
styles with one fixed set of statistics; this module is that measurement,
ported, so an agent can render, measure the same statistics on its own output,
and adjust. The style specs that carry the ``targets`` live with the downstream
skill (``.claude/skills/an-style/styles/*.yaml``).

**The estimators are the research's estimators, on purpose.** Every threshold
below is the one the six styles were measured with, including the ones that are
crude (a noise floor at the 10th percentile of frame differences, a cut as a
colour-histogram jump). A better estimator would measure a different quantity
from the one the targets were calibrated on, and a render would then pass or
miss for a reason nobody measured. Change an estimator only together with
re-measuring the targets.

What is measured (see :data:`METRICS` for the vocabulary a spec's ``targets``
may use):

- **Holds and cadence.** A frame "changes" when its mean absolute grey
  difference from the previous frame exceeds ``max(0.25, 2.5 × p10)``, where
  p10 is the clip's own 10th-percentile difference (compression noise, capped
  at 1.0 — see :data:`NOISE_FLOOR_CAP`). From
  that: the share of frames identical to the previous one, pose changes per
  second, and the histogram of gaps between successive changes (one frame = on
  ones, two = on twos, three or more = threes and holds, gaps above 12 frames
  ignored as holds rather than cadence).
- **Cuts and shot length.** For an ``an`` render the cuts are KNOWN — every shot
  boundary in the IR is a hard cut, because shots are concatenated — so the
  verifier takes them from the IR. Without an IR (any mp4), a cut is a frame
  whose 8×8×8 colour-histogram L1 distance exceeds 0.6 and whose mean
  difference exceeds 8; dissolves and morphs are missed, so on such footage the
  count is a floor.
- **Palette.** Mean HSV saturation, the share of dark pixels (every channel
  below 60, an outline proxy), and the coverage of the 16 most common colours
  after 4-bit quantisation (flatness), all on every 15th frame.

Not ported, deliberately: the research also measured global camera motion
(``cv2.phaseCorrelate``) and a k-means palette. Both need OpenCV or
scikit-learn, and this module adds no dependency — numpy and the ffmpeg binary
are already what ``an.verify.media`` uses.

A pure function over frames — :func:`measure_style` — is the core, so it is
testable without ffmpeg:

>>> import numpy as np
>>> still = np.zeros((4, 8, 8, 3), np.uint8)
>>> frames = np.concatenate([still, still + 200, still + 200, still])  # 16 frames, changes at 4 and 12
>>> m = measure_style(frames, fps=4.0, shot_durations=[4.0])
>>> m.identical_frame_share, m.pose_changes_per_s
(0.867, 0.5)

A target is a ``[low, high]`` range; a miss is a warning naming the knob that
moves it:

>>> findings = check_targets(m, {"identical_frame_share": [0.2, 0.5]})
>>> findings[0].severity, findings[0].ir_path
('warning', '<style>/identical_frame_share')
>>> check_targets(m, {"identical_frame_share": [0.5, 0.9]})
[]

A target nothing measures is refused, not ignored — a spec that silently checks
less than it says is worse than one that fails to load:

>>> check_targets(m, {"camera_shake": [0, 1]})
Traceback (most recent call last):
...
ValueError: unknown style target 'camera_shake'; measurable targets are [...]
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from an.adapters._base import RenderResult
from an.ir.schema import SceneIR
from an.verify._base import Finding, VerificationReport
from an.verify.vision import FAILURE_SEVERITY

__all__ = [
    "METRICS",
    "StyleMetrics",
    "StyleLintResult",
    "StyleLintVerifier",
    "measure_style",
    "measure_video",
    "check_targets",
    "load_style_spec",
    "style_lint",
]

# -----------------------------------------------------------------------------
# The research's estimator constants — change them only with the targets
# -----------------------------------------------------------------------------

#: Decode size. The targets were measured at 320×180; the mean-difference
#: thresholds below are in grey levels at this scale.
DECODE_WIDTH: int = 320
DECODE_HEIGHT: int = 180
#: A step is a change above ``max(MIN_CHANGE_THRESHOLD, NOISE_FLOOR_MULTIPLIER × pN)``
#: where pN is the ``NOISE_FLOOR_PERCENTILE``-th percentile of the clip's steps.
MIN_CHANGE_THRESHOLD: float = 0.25
NOISE_FLOOR_PERCENTILE: float = 10.0
NOISE_FLOOR_MULTIPLIER: float = 2.5
#: The ONE departure from the research's estimator: the noise floor is capped.
#: The floor is meant to be compression noise, but when fewer than 10% of a
#: clip's steps are holds the percentile lands on real motion — a clip changing
#: by the same amount every frame would measure as 100% identical. In all six
#: study clips the uncapped floor was at most 0.16 grey levels, so this cap
#: moves none of the measured targets.
NOISE_FLOOR_CAP: float = 1.0
#: Pixel cut detector (used only when no shot list is given).
CUT_HISTOGRAM_L1: float = 0.6
CUT_MEAN_DIFF: float = 8.0
CUT_DEDUPE_FRAMES: int = 5
HISTOGRAM_BITS_DROPPED: int = 5  # 8 bins per channel over 0..255
#: Gaps between changes longer than this are holds, not cadence.
MAX_CADENCE_INTERVAL: int = 12
#: Palette statistics use every Nth frame.
PALETTE_FRAME_STRIDE: int = 15
DARK_PIXEL_MAX: int = 60
FLAT_COLOUR_BITS_DROPPED: int = 4
FLAT_TOP_COLOURS: int = 16
#: Below this clip length, one cut moves ``cuts_per_min`` by ``60 / duration``;
#: the verifier says so when a shot target is checked on a shorter clip.
SHORT_CLIP_S: float = 30.0

#: The target vocabulary: every key a spec's ``targets`` may use, and what it is.
METRICS: dict[str, str] = {
    "identical_frame_share": "share of frames identical to the previous one (holds)",
    "pose_changes_per_s": "changed frames per second",
    "one_frame_interval_share": "share of change gaps of one frame (on ones)",
    "two_frame_interval_share": "share of change gaps of two frames (on twos)",
    "three_plus_interval_share": "share of change gaps of three to twelve frames",
    "max_hold_frames": "longest run of identical frames",
    "cuts_per_min": "hard cuts per minute",
    "mean_shot_s": "mean shot length in seconds",
    "mean_saturation": "mean HSV saturation, 0..1",
    "dark_pixel_share": "share of pixels with every channel below 60",
    "top16_colour_coverage": "coverage of the 16 commonest 4-bit colours (flatness)",
}

#: What to change when a metric is out of range, as ``(too_low, too_high)``.
#: Every knob named here is a shipped one.
_FIXES: dict[str, tuple[str, str]] = {
    "identical_frame_share": (
        "hold more: set `step_hz` (fps/2 = on twos, fps/3 = on threes), "
        "shorten tweens and leave gaps between them",
        "move more: drop `step_hz`, add idle `play`s or longer overlapping tweens",
    ),
    "pose_changes_per_s": (
        "add motion: more or longer tweens, or a higher `step_hz`",
        "hold more: a lower `step_hz`, fewer simultaneous tweens",
    ),
    "one_frame_interval_share": (
        "run moves on ones: `step_hz: null` and short tweens between holds",
        "step the tweens: set `step_hz` to fps/2 or fps/3",
    ),
    "two_frame_interval_share": (
        "set `step_hz` to fps/2 (on twos)",
        "drop `step_hz` or set it to fps/3",
    ),
    "three_plus_interval_share": (
        "set `step_hz` to fps/3 or lower",
        "raise `step_hz` or drop it",
    ),
    "max_hold_frames": (
        "leave a longer still stretch between actions",
        "fill the long hold: a blink, an idle `play`, or cut sooner",
    ),
    "cuts_per_min": (
        "split long shots into more, shorter ones",
        "merge shots or lengthen them",
    ),
    "mean_shot_s": (
        "lengthen shots or merge them",
        "split long shots",
    ),
    "mean_saturation": (
        "more saturated StylePack roles and art colours",
        "desaturate StylePack roles and art colours",
    ),
    "dark_pixel_share": (
        "darker backdrop (StylePack `sky`/`ground`, plane fills) or outlines",
        "lighter backdrop and fills",
    ),
    "top16_colour_coverage": (
        "fewer, flatter colours: flat fills, no gradients",
        "more colour variety or textured art",
    ),
}


# -----------------------------------------------------------------------------
# Measurement (pure)
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StyleMetrics:
    """The statistics :data:`METRICS` names, measured on one clip."""

    fps: float
    frames: int
    duration_s: float
    identical_frame_share: float
    pose_changes_per_s: float
    one_frame_interval_share: float
    two_frame_interval_share: float
    three_plus_interval_share: float
    max_hold_frames: int
    cuts: int
    cuts_per_min: float
    mean_shot_s: float
    mean_saturation: float
    dark_pixel_share: float
    top16_colour_coverage: float
    #: Where the cuts came from: ``"shots"`` (a shot list, exact) or ``"pixels"``.
    cut_source: str
    change_threshold: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cut_frames_from_shots(shot_durations: Sequence[float], fps: float, n: int):
    """Frame indices where a new shot starts (excluding 0 and the end)."""
    bounds = np.round(np.cumsum(shot_durations)[:-1] * fps).astype(int)
    return sorted({int(b) for b in bounds if 0 < b < n})


def _cut_frames_from_pixels(frames: np.ndarray, step_diff: np.ndarray) -> list[int]:
    q = (frames >> HISTOGRAM_BITS_DROPPED).astype(np.int32)
    bins = 256 >> HISTOGRAM_BITS_DROPPED
    key = (q[..., 0] * bins + q[..., 1]) * bins + q[..., 2]
    per_frame = key.reshape(len(frames), -1)
    hists = np.stack([np.bincount(k, minlength=bins**3) / k.size for k in per_frame])
    hist_l1 = np.abs(hists[1:] - hists[:-1]).sum(axis=1)
    cuts: list[int] = []
    for i in np.flatnonzero((hist_l1 > CUT_HISTOGRAM_L1) & (step_diff > CUT_MEAN_DIFF)):
        if not cuts or (i + 1) - cuts[-1] > CUT_DEDUPE_FRAMES:
            cuts.append(int(i + 1))
    return cuts


def _palette_stats(frames: np.ndarray) -> tuple[float, float, float]:
    px = frames[::PALETTE_FRAME_STRIDE].reshape(-1, 3)
    hi = px.max(axis=1).astype(np.float64)
    lo = px.min(axis=1).astype(np.float64)
    sat = np.where(hi > 0, (hi - lo) / np.where(hi > 0, hi, 1), 0.0)
    dark = float((hi < DARK_PIXEL_MAX).mean())
    q = (px >> FLAT_COLOUR_BITS_DROPPED).astype(np.int32)
    bins = 256 >> FLAT_COLOUR_BITS_DROPPED
    counts = np.bincount((q[:, 0] * bins + q[:, 1]) * bins + q[:, 2])
    top = np.sort(counts)[::-1][:FLAT_TOP_COLOURS].sum() / counts.sum()
    return float(sat.mean()), dark, float(top)


def measure_style(
    frames: np.ndarray,
    *,
    fps: float,
    shot_durations: Sequence[float] | None = None,
) -> StyleMetrics:
    """Measure the :data:`METRICS` on ``frames``, an ``(n, h, w, 3)`` uint8 RGB array.

    ``shot_durations`` (seconds, in order) gives the cuts exactly; without it the
    pixel cut detector is used. Ratios are rounded to three decimals.

    >>> import numpy as np
    >>> f = np.zeros((6, 4, 4, 3), np.uint8)
    >>> f[1::2] = 255                       # a change on every frame
    >>> m = measure_style(f, fps=6.0, shot_durations=[1.0])
    >>> m.identical_frame_share, m.one_frame_interval_share, m.cuts
    (0.0, 1.0, 0)
    """
    frames = np.asarray(frames)
    if frames.ndim != 4 or frames.shape[-1] != 3 or frames.dtype != np.uint8:
        raise ValueError(
            f"expected an (n, h, w, 3) uint8 array; got {frames.shape} {frames.dtype}"
        )
    n = len(frames)
    if n < 2:
        raise ValueError(f"need at least two frames to measure a style; got {n}")
    if fps <= 0:
        raise ValueError(f"fps must be positive; got {fps}")

    grey = frames.astype(np.float32).mean(axis=3)
    step_diff = np.abs(grey[1:] - grey[:-1]).mean(axis=(1, 2))
    noise_floor = min(
        NOISE_FLOOR_CAP, float(np.percentile(step_diff, NOISE_FLOOR_PERCENTILE))
    )
    threshold = max(MIN_CHANGE_THRESHOLD, NOISE_FLOOR_MULTIPLIER * noise_floor)
    changed = step_diff > threshold

    if shot_durations:
        cuts = _cut_frames_from_shots(shot_durations, fps, n)
        cut_source = "shots"
    else:
        cuts = _cut_frames_from_pixels(frames, step_diff)
        cut_source = "pixels"
    duration = n / fps
    bounds = [0, *cuts, n]
    shots = [(b - a) / fps for a, b in zip(bounds[:-1], bounds[1:])]

    # Cadence ignores the step INTO a cut: that is an edit, not a pose change.
    cut_steps = {c - 1 for c in cuts}
    idx = [i for i in np.flatnonzero(changed) if i not in cut_steps]
    gaps = np.diff(idx)
    gaps = gaps[gaps <= MAX_CADENCE_INTERVAL]
    total = max(len(gaps), 1)

    runs, run = [], 1
    for c in changed:
        if c:
            runs.append(run)
            run = 1
        else:
            run += 1
    runs.append(run)

    sat, dark, top16 = _palette_stats(frames)
    r3 = lambda x: round(float(x), 3)  # noqa: E731
    return StyleMetrics(
        fps=r3(fps),
        frames=n,
        duration_s=r3(duration),
        identical_frame_share=r3(1 - changed.sum() / (n - 1)),
        pose_changes_per_s=r3(changed.sum() / duration),
        one_frame_interval_share=r3((gaps == 1).sum() / total),
        two_frame_interval_share=r3((gaps == 2).sum() / total),
        three_plus_interval_share=r3((gaps >= 3).sum() / total),
        max_hold_frames=int(max(runs)),
        cuts=len(cuts),
        cuts_per_min=r3(len(cuts) / duration * 60),
        mean_shot_s=r3(np.mean(shots)),
        mean_saturation=r3(sat),
        dark_pixel_share=r3(dark),
        top16_colour_coverage=r3(top16),
        cut_source=cut_source,
        change_threshold=r3(threshold),
    )


def _validate_targets(targets: Mapping[str, Sequence[float]]) -> None:
    """Raise ``ValueError`` for an unknown target or a malformed range."""
    for name, rng in targets.items():
        if name not in METRICS:
            raise ValueError(
                f"unknown style target {name!r}; measurable targets are "
                f"{sorted(METRICS)}"
            )
        if (
            isinstance(rng, (str, bytes))
            or not isinstance(rng, Sequence)
            or len(rng) != 2
            or not all(isinstance(v, (int, float)) for v in rng)
            or rng[0] > rng[1]
        ):
            raise ValueError(
                f"style target {name!r} must be a [low, high] range; got {rng!r}"
            )


def check_targets(
    metrics: StyleMetrics,
    targets: Mapping[str, Sequence[float]],
    *,
    miss_severity: str = "warning",
) -> list[Finding]:
    """One :class:`Finding` per target the metrics miss; ``[]`` when all hit.

    Raises ``ValueError`` for a target :data:`METRICS` does not name, or a range
    that is not ``[low, high]`` with ``low <= high``.
    """
    _validate_targets(targets)
    findings = []
    for name, rng in targets.items():
        lo, hi = rng
        value = getattr(metrics, name)
        if lo <= value <= hi:
            continue
        low = value < lo
        findings.append(
            Finding(
                severity=miss_severity,
                ir_path=f"<style>/{name}",
                description=(
                    f"{name} = {value} is {'below' if low else 'above'} the "
                    f"style's range [{lo}, {hi}] ({METRICS[name]})"
                ),
                suggested_fix=_FIXES[name][0 if low else 1],
            )
        )
    return findings


# -----------------------------------------------------------------------------
# I/O: decode, spec loading
# -----------------------------------------------------------------------------


class StyleLintError(RuntimeError):
    """The video could not be decoded or probed for style measurement."""


def _run(cmd: list[str]) -> bytes:
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError as e:
        raise StyleLintError(
            f"{cmd[0]} is not on PATH; style lint needs ffmpeg/ffprobe "
            "(e.g. `brew install ffmpeg` / `apt-get install ffmpeg`)"
        ) from e
    if proc.returncode != 0:
        raise StyleLintError(
            f"{cmd[0]} failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()[:400]}"
        )
    return proc.stdout


def _probe_fps(mp4: Path) -> float:
    out = (
        _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate",
                "-of",
                "csv=p=0",
                str(mp4),
            ]
        )
        .decode("utf-8")
        .strip()
    )
    num, _, den = out.partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError) as e:
        raise StyleLintError(f"could not read a frame rate from {out!r}") from e


def _decode_frames(mp4: Path, *, width: int, height: int) -> np.ndarray:
    raw = _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(mp4),
            "-map",
            "0:v:0",
            "-fps_mode",
            "passthrough",
            "-vf",
            f"scale={width}:{height}",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    size = width * height * 3
    n = len(raw) // size
    return np.frombuffer(raw[: n * size], np.uint8).reshape(n, height, width, 3)


def measure_video(
    mp4: str | Path,
    *,
    shot_durations: Sequence[float] | None = None,
    width: int = DECODE_WIDTH,
    height: int = DECODE_HEIGHT,
) -> StyleMetrics:
    """Decode ``mp4`` at the research's scale and :func:`measure_style` it."""
    mp4 = Path(mp4)
    if not mp4.exists():
        raise StyleLintError(f"no such video: {mp4}")
    return measure_style(
        _decode_frames(mp4, width=width, height=height),
        fps=_probe_fps(mp4),
        shot_durations=shot_durations,
    )


def load_style_spec(spec: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """A style spec as a dict: a mapping is passed through, a path is read as YAML."""
    if isinstance(spec, Mapping):
        return dict(spec)
    import yaml

    data = yaml.safe_load(Path(spec).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"style spec {spec} is not a mapping")
    return data


def _targets_of(spec_or_targets: str | Path | Mapping[str, Any]) -> tuple[str, dict]:
    """``(style name, targets)`` from a spec (path or mapping) or a bare targets mapping."""
    spec = load_style_spec(spec_or_targets)
    if "targets" in spec:
        return str(spec.get("style", "")), dict(spec["targets"] or {})
    return "", spec


# -----------------------------------------------------------------------------
# The lint, and the Verifier
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class StyleLintResult:
    """What one lint run measured, and what it found."""

    metrics: StyleMetrics | None
    report: VerificationReport


def style_lint(
    mp4: str | Path,
    spec_or_targets: str | Path | Mapping[str, Any],
    *,
    shot_durations: Sequence[float] | None = None,
    miss_severity: str = "warning",
) -> StyleLintResult:
    """Measure ``mp4`` and compare it to a style spec's ``targets``.

    A decode or probe failure is reported at
    :data:`an.verify.vision.FAILURE_SEVERITY`, never as ``info`` — a lint that
    could not run must not read as a clean one. A malformed spec raises: that is
    the caller's error, not the video's.
    """
    style, targets = _targets_of(spec_or_targets)
    # Validate the spec before touching the video, so a bad spec fails loudly.
    _validate_targets(targets)

    report = VerificationReport()
    label = f"style {style!r}" if style else "style targets"
    try:
        metrics = measure_video(mp4, shot_durations=shot_durations)
    except (StyleLintError, ValueError) as e:
        report.add(
            FAILURE_SEVERITY,
            "<style>",
            f"style lint could not measure {mp4}: {e}",
            suggested_fix="check the render produced a readable mp4 and ffmpeg is installed",
        )
        return StyleLintResult(None, report)

    measured = ", ".join(f"{k}={getattr(metrics, k)}" for k in METRICS)
    report.add(
        "info",
        "<style>",
        f"measured against {label} ({metrics.duration_s} s, cuts from "
        f"{metrics.cut_source}): {measured}",
    )
    shot_targets = {"cuts_per_min", "mean_shot_s"} & set(targets)
    if shot_targets and metrics.duration_s < SHORT_CLIP_S:
        report.add(
            "info",
            "<style>/cuts_per_min",
            f"the clip is {metrics.duration_s} s long, so one cut moves "
            f"cuts_per_min by {60 / metrics.duration_s:.1f}; "
            f"{sorted(shot_targets)} are coarse on a clip this short",
        )
    for f in check_targets(metrics, targets, miss_severity=miss_severity):
        report.add(f.severity, f.ir_path, f.description, f.suggested_fix)
    return StyleLintResult(metrics, report)


class StyleLintVerifier:
    """Compare a render to a style spec's ``targets``. Implements ``Verifier``.

    Shot boundaries come from the IR (every shot boundary is a hard cut in an
    ``an`` render), so ``cuts_per_min`` and ``mean_shot_s`` are exact rather
    than detected. Pre-render (``render is None``) it reports ``info`` and
    passes: it has nothing to measure yet.
    """

    name: str = "style_lint"

    def __init__(
        self,
        spec_or_targets: str | Path | Mapping[str, Any],
        *,
        miss_severity: str = "warning",
    ) -> None:
        self.style, self.targets = _targets_of(spec_or_targets)
        self.miss_severity = miss_severity
        # Refuse a bad spec at construction, not at the end of a render.
        _validate_targets(self.targets)

    def verify(self, ir: SceneIR, render: RenderResult | None) -> VerificationReport:
        if render is None:
            report = VerificationReport()
            report.add("info", "<style>", "no render result; skipping style lint")
            return report
        shots = [float(s.duration) for s in ir.timeline] if ir.timeline else None
        return style_lint(
            render.mp4_path,
            {"style": self.style, "targets": self.targets},
            shot_durations=shots,
            miss_severity=self.miss_severity,
        ).report


def _main(argv: Sequence[str]) -> int:
    """``python -m an.verify.style VIDEO SPEC.yaml`` — print metrics and findings as JSON.

    Exit status 0 when every target hits, 1 on a miss, 2 when it could not measure.
    """
    if len(argv) != 2:
        print("usage: python -m an.verify.style VIDEO SPEC.yaml", file=sys.stderr)
        return 2
    result = style_lint(argv[0], argv[1])
    print(
        json.dumps(
            {
                "metrics": result.metrics.as_dict() if result.metrics else None,
                "findings": [asdict(f) for f in result.report.findings],
            },
            indent=2,
        )
    )
    if result.metrics is None:
        return 2
    return 0 if all(f.severity == "info" for f in result.report.findings) else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
