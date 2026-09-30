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
from dataclasses import asdict, dataclass, field
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
    "measure_shots",
    "measure_video",
    "film_shots",
    "project_of_render",
    "ShotMetrics",
    "SHOT_METRICS",
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

#: The fixes for a style whose spec SETS ``step_hz`` (its ``live.meta``): the
#: knob is the style's, so no fix may drop it or move it. ``{step_hz}`` is the
#: spec's value. Only the metrics whose generic fix touches ``step_hz`` differ.
_FIXES_STEPPED: dict[str, tuple[str, str]] = {
    "identical_frame_share": (
        "hold more: check `step_hz: {step_hz}` is set as the style says, then "
        "shorter tweens with real holds between them and fewer simultaneous moves",
        "move more while characters talk: gesture beats of 0.2-0.3 s on arms and "
        "head, closer framing (`stage.scale`), fewer dead holds; keep `step_hz` "
        "at the style's {step_hz}",
    ),
    "pose_changes_per_s": (
        "add motion: more gesture beats and closer framing; keep `step_hz` at "
        "the style's {step_hz}",
        "hold more: fewer simultaneous tweens and longer holds between beats; "
        "keep `step_hz` at the style's {step_hz}",
    ),
    "one_frame_interval_share": (
        "only unstepped motion changes on ones here (the camera, blinks, mouth "
        "swaps, `play` clips); a camera move or more talking raises it, and "
        "`step_hz` stays at the style's {step_hz}",
        "check `step_hz: {step_hz}` is set as the style says, and move bodies with "
        "tweens (which it steps) rather than `play` clips or the camera",
    ),
    "two_frame_interval_share": (
        "check `step_hz: {step_hz}` is set as the style says, and move bodies with "
        "tweens (which it steps) rather than `play` clips or the camera",
        "more holds between moves, so fewer changes land two frames apart; keep "
        "`step_hz` at the style's {step_hz}",
    ),
    "three_plus_interval_share": (
        "leave real holds (a few frames) between moves; keep `step_hz` at the "
        "style's {step_hz}",
        "fewer, shorter holds between moves; keep `step_hz` at the style's {step_hz}",
    ),
}

#: The fixes for a style whose spec leaves ``step_hz`` UNSET: it runs on ones,
#: so no fix may tell the author to step it.
_FIXES_UNSTEPPED: dict[str, tuple[str, str]] = {
    "identical_frame_share": (
        "hold more: shorter bursts (tweens in the style's range) with real holds "
        "between them; leave `step_hz` unset, as the style says",
        "move more: more or longer tweens, gesture bursts while characters talk, "
        "closer framing; check `step_hz` is unset, as the style says",
    ),
    "pose_changes_per_s": (
        "add motion: more or longer tweens, gesture bursts, closer framing",
        "hold more: fewer simultaneous tweens, longer holds between bursts",
    ),
    "one_frame_interval_share": (
        "check `step_hz` is unset, as the style says; then short tweens between "
        "holds, so each burst changes every frame",
        "more holds between bursts, so some changes land further apart",
    ),
    "two_frame_interval_share": (
        "this style runs on ones, so two-frame gaps come only from very short "
        "holds; accept the miss rather than stepping the tweens",
        "check `step_hz` is unset, as the style says",
    ),
    "three_plus_interval_share": (
        "leave longer holds between bursts; `step_hz` stays unset",
        "fewer, shorter holds between bursts; `step_hz` stays unset",
    ),
}


def _fix_for(name: str, low: bool, live: Mapping[str, Any] | None) -> str:
    """The fix to suggest for a miss on ``name``, respecting the style's own
    ``live`` settings: a spec that sets ``step_hz`` never hears "drop it", and
    one that leaves it unset never hears "set it". With no ``live`` section (a
    bare targets mapping) the generic fix is all there is."""
    table, fmt = _FIXES, {}
    if live is not None:
        step_hz = (live.get("meta") or {}).get("step_hz")
        if step_hz is not None:
            table, fmt = _FIXES_STEPPED, {"step_hz": step_hz}
        else:
            table = _FIXES_UNSTEPPED
    fix = table.get(name, _FIXES[name])[0 if low else 1]
    return fix.format(**fmt) if fmt else fix


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


def _r3(x: float) -> float:
    return round(float(x), 3)


def _step_changes(frames: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """``(step_diff, changed, threshold)`` over the frame-to-frame steps: the
    mean absolute grey difference of each step, whether it counts as a change,
    and the clip's change threshold (see the module docstring)."""
    grey = frames.astype(np.float32).mean(axis=3)
    step_diff = np.abs(grey[1:] - grey[:-1]).mean(axis=(1, 2))
    noise_floor = min(
        NOISE_FLOOR_CAP, float(np.percentile(step_diff, NOISE_FLOOR_PERCENTILE))
    )
    threshold = max(MIN_CHANGE_THRESHOLD, NOISE_FLOOR_MULTIPLIER * noise_floor)
    return step_diff, step_diff > threshold, threshold


def _cadence(changed: np.ndarray, *, cut_steps: set[int], fps: float) -> dict:
    """The hold and cadence statistics of one run of steps (a clip or a shot).

    Cadence ignores the step INTO a cut: that is an edit, not a pose change.
    """
    n_steps = len(changed)
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
    duration = (n_steps + 1) / fps
    return dict(
        identical_frame_share=_r3(1 - changed.sum() / max(n_steps, 1)),
        pose_changes_per_s=_r3(changed.sum() / duration),
        one_frame_interval_share=_r3((gaps == 1).sum() / total),
        two_frame_interval_share=_r3((gaps == 2).sum() / total),
        three_plus_interval_share=_r3((gaps >= 3).sum() / total),
        max_hold_frames=int(max(runs)),
    )


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

    step_diff, changed, threshold = _step_changes(frames)

    if shot_durations:
        cuts = _cut_frames_from_shots(shot_durations, fps, n)
        cut_source = "shots"
    else:
        cuts = _cut_frames_from_pixels(frames, step_diff)
        cut_source = "pixels"
    duration = n / fps
    bounds = [0, *cuts, n]
    shots = [(b - a) / fps for a, b in zip(bounds[:-1], bounds[1:])]

    cadence = _cadence(changed, cut_steps={c - 1 for c in cuts}, fps=fps)
    sat, dark, top16 = _palette_stats(frames)
    r3 = _r3
    return StyleMetrics(
        fps=r3(fps),
        frames=n,
        duration_s=r3(duration),
        **cadence,
        cuts=len(cuts),
        cuts_per_min=r3(len(cuts) / duration * 60),
        mean_shot_s=r3(np.mean(shots)),
        mean_saturation=r3(sat),
        dark_pixel_share=r3(dark),
        top16_colour_coverage=r3(top16),
        cut_source=cut_source,
        change_threshold=r3(threshold),
    )


#: The per-shot statistics: the cadence ones, which a single static shot (a date
#: card, a held map) can swing for the whole clip.
SHOT_METRICS: tuple[str, ...] = (
    "identical_frame_share",
    "pose_changes_per_s",
    "one_frame_interval_share",
    "two_frame_interval_share",
    "three_plus_interval_share",
    "max_hold_frames",
)


@dataclass(frozen=True, slots=True)
class ShotMetrics:
    """The cadence of one shot, measured with the WHOLE clip's change
    threshold so a shot's numbers add up to the clip's."""

    shot: str
    start_s: float
    duration_s: float
    frames: int
    identical_frame_share: float
    pose_changes_per_s: float
    one_frame_interval_share: float
    two_frame_interval_share: float
    three_plus_interval_share: float
    max_hold_frames: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def measure_shots(
    frames: np.ndarray,
    *,
    fps: float,
    shot_durations: Sequence[float] | None = None,
    shot_ids: Sequence[str] | None = None,
) -> list[ShotMetrics]:
    """Per-shot cadence (:data:`SHOT_METRICS`) of ``frames``, one row per shot.

    The shots are ``shot_durations`` (seconds, in order) when given, else the
    pixel cut detector's. The step INTO each shot is the cut, not a pose
    change, so it belongs to no shot. A one-frame shot has no step of its own
    and measures as all-identical.

    >>> import numpy as np
    >>> still = np.zeros((4, 8, 8, 3), np.uint8)
    >>> moving = np.stack([still[0] + 10 * i for i in range(4)])
    >>> rows = measure_shots(np.concatenate([still, moving]), fps=4.0,
    ...                      shot_durations=[1.0, 1.0], shot_ids=["card", "map"])
    >>> [(r.shot, r.identical_frame_share) for r in rows]
    [('card', 1.0), ('map', 0.0)]
    """
    frames = np.asarray(frames)
    n = len(frames)
    _, changed, _ = _step_changes(frames)
    if shot_durations:
        cuts = _cut_frames_from_shots(shot_durations, fps, n)
    else:
        cuts = _cut_frames_from_pixels(frames, _step_changes(frames)[0])
    bounds = [0, *cuts, n]
    ids = list(shot_ids or [])
    rows = []
    for k, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
        steps = changed[a : max(a, b - 1)]
        rows.append(
            ShotMetrics(
                shot=ids[k] if k < len(ids) else f"shot{k + 1}",
                start_s=_r3(a / fps),
                duration_s=_r3((b - a) / fps),
                frames=b - a,
                **_cadence(steps, cut_steps=set(), fps=fps),
            )
        )
    return rows


def film_shots(scene: SceneIR) -> list[tuple[str, float]]:
    """``(shot id, seconds on screen)`` per shot of an ``an`` render, in order.

    What the lint needs to place the cuts exactly. It is the shot durations,
    except where a dissolve overlaps two shots: the film is that much shorter
    than their sum (:func:`an.assemble.film_timeline`), and each shot is
    counted from where its frames start in the film.

    >>> from an.ir.schema import Shot, Transition
    >>> film_shots(SceneIR(timeline=[
    ...     Shot(id="a", duration=2.0),
    ...     Shot(id="b", duration=2.0, transition=Transition(kind="dissolve", duration=0.5))]))
    [('a', 1.5), ('b', 2.0)]
    """
    from an.assemble import film_timeline

    shots = list(scene.timeline)
    if not shots:
        return []
    fps = float(scene.meta.fps)
    tl = film_timeline(shots, fps=fps)
    ends = [*tl.starts[1:], tl.total_frames]
    return [
        (shot.id, (end - start) / fps)
        for shot, start, end in zip(shots, tl.starts, ends)
    ]


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
    live: Mapping[str, Any] | None = None,
) -> list[Finding]:
    """One :class:`Finding` per target the metrics miss; ``[]`` when all hit.

    ``live`` is the style spec's ``live`` section. Given, each suggested fix
    respects it — a style that sets ``step_hz`` is never told to drop it, one
    that leaves it unset is never told to set it:

    >>> m = measure_style(np.zeros((8, 4, 4, 3), np.uint8), fps=8.0, shot_durations=[1.0])
    >>> (f,) = check_targets(m, {"identical_frame_share": [0.5, 0.7]},
    ...                      live={"meta": {"fps": 24, "step_hz": 12}})
    >>> "drop `step_hz`" in f.suggested_fix, "keep `step_hz` at the style's 12" in f.suggested_fix
    (False, True)

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
                suggested_fix=_fix_for(name, low, live),
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


def _spec_parts(
    spec_or_targets: str | Path | Mapping[str, Any],
) -> tuple[str, dict, dict | None]:
    """``(style name, targets, live)`` from a spec (path or mapping) or a bare
    targets mapping (whose ``live`` is ``None``: nothing to respect)."""
    spec = load_style_spec(spec_or_targets)
    if "targets" in spec:
        live = spec.get("live")
        return (
            str(spec.get("style", "")),
            dict(spec["targets"] or {}),
            dict(live) if isinstance(live, Mapping) else None,
        )
    return "", spec, None


def _targets_of(spec_or_targets: str | Path | Mapping[str, Any]) -> tuple[str, dict]:
    """``(style name, targets)`` from a spec (path or mapping) or a bare targets mapping."""
    style, targets, _ = _spec_parts(spec_or_targets)
    return style, targets


def _load_scene(project_or_scene: str | Path | SceneIR) -> SceneIR:
    """A scene from a project directory (its ``ir/scene.json``), a ``scene.json``
    file, or a `SceneIR` passed through."""
    if isinstance(project_or_scene, SceneIR):
        return project_or_scene
    from an.ir.sync import scene_from_json_doc

    path = Path(project_or_scene)
    if path.is_dir():
        path = path / PROJECT_SCENE_JSON
    if not path.is_file():
        raise StyleLintError(
            f"no scene at {path}: pass a project directory (with {PROJECT_SCENE_JSON}) "
            "or a scene.json"
        )
    return scene_from_json_doc(json.loads(path.read_text(encoding="utf-8")))


#: Where a project keeps its scene, relative to the project directory.
PROJECT_SCENE_JSON: str = "ir/scene.json"


def project_of_render(mp4: str | Path) -> Path | None:
    """The project directory an ``an`` render sits in — ``<project>/output/x.mp4``
    beside ``<project>/ir/scene.json`` — or ``None`` for any other video."""
    mp4 = Path(mp4)
    candidate = mp4.resolve().parent.parent
    if mp4.resolve().parent.name == "output" and (candidate / PROJECT_SCENE_JSON).is_file():
        return candidate
    return None


# -----------------------------------------------------------------------------
# The lint, and the Verifier
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class StyleLintResult:
    """What one lint run measured, and what it found.

    ``per_shot`` is the cadence of each shot (:class:`ShotMetrics`) — the
    breakdown that finds which shot is holding a whole clip's share up (a
    static date card is 90% identical frames on its own)."""

    metrics: StyleMetrics | None
    report: VerificationReport
    per_shot: list[ShotMetrics] = field(default_factory=list)


def style_lint(
    mp4: str | Path,
    spec_or_targets: str | Path | Mapping[str, Any],
    *,
    shot_durations: Sequence[float] | None = None,
    scene: str | Path | SceneIR | None = None,
    miss_severity: str = "warning",
) -> StyleLintResult:
    """Measure ``mp4`` and compare it to a style spec's ``targets``.

    The cuts are exact when the shots are known: pass ``scene`` (a project
    directory, a ``scene.json``, or a `SceneIR`; dissolve overlaps are
    accounted for) or ``shot_durations``. Without either, cuts are detected
    from pixels, which misses a cut between two shots on the same backdrop and
    every dissolve — the lint says so in its report.

    Suggested fixes respect the spec's ``live`` settings (:func:`check_targets`).

    A decode or probe failure is reported at
    :data:`an.verify.vision.FAILURE_SEVERITY`, never as ``info`` — a lint that
    could not run must not read as a clean one. A malformed spec raises: that is
    the caller's error, not the video's.
    """
    style, targets, live = _spec_parts(spec_or_targets)
    # Validate the spec before touching the video, so a bad spec fails loudly.
    _validate_targets(targets)

    shot_ids: list[str] | None = None
    if scene is not None and shot_durations is None:
        shots = film_shots(_load_scene(scene))
        shot_ids = [sid for sid, _ in shots]
        shot_durations = [d for _, d in shots]

    report = VerificationReport()
    label = f"style {style!r}" if style else "style targets"
    try:
        mp4 = Path(mp4)
        if not mp4.exists():
            raise StyleLintError(f"no such video: {mp4}")
        frames = _decode_frames(mp4, width=DECODE_WIDTH, height=DECODE_HEIGHT)
        fps = _probe_fps(mp4)
        metrics = measure_style(frames, fps=fps, shot_durations=shot_durations)
        per_shot = measure_shots(
            frames, fps=fps, shot_durations=shot_durations, shot_ids=shot_ids
        )
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
    if shot_targets and metrics.cut_source == "pixels":
        report.add(
            "info",
            "<style>/cuts_per_min",
            f"cuts were detected from pixels ({metrics.cuts} found), which misses "
            "a cut between two shots on the same backdrop and every dissolve, so "
            f"{sorted(shot_targets)} may be wrong; pass the project "
            "(`--project DIR`, or `scene=` in Python) for the authored shot list",
        )
    if shot_targets and metrics.duration_s < SHORT_CLIP_S:
        report.add(
            "info",
            "<style>/cuts_per_min",
            f"the clip is {metrics.duration_s} s long, so one cut moves "
            f"cuts_per_min by {60 / metrics.duration_s:.1f}; "
            f"{sorted(shot_targets)} are coarse on a clip this short",
        )
    for f in check_targets(metrics, targets, miss_severity=miss_severity, live=live):
        report.add(f.severity, f.ir_path, f.description, f.suggested_fix)
    return StyleLintResult(metrics, report, per_shot)


class StyleLintVerifier:
    """Compare a render to a style spec's ``targets``. Implements ``Verifier``.

    Shot boundaries come from the IR (every shot boundary is a cut in an ``an``
    render, and a dissolve's overlap is accounted for), so ``cuts_per_min`` and
    ``mean_shot_s`` are exact rather than detected. Pre-render
    (``render is None``) it reports ``info`` and passes: it has nothing to
    measure yet.
    """

    name: str = "style_lint"

    def __init__(
        self,
        spec_or_targets: str | Path | Mapping[str, Any],
        *,
        miss_severity: str = "warning",
    ) -> None:
        self.style, self.targets, self.live = _spec_parts(spec_or_targets)
        self.miss_severity = miss_severity
        # Refuse a bad spec at construction, not at the end of a render.
        _validate_targets(self.targets)

    def verify(self, ir: SceneIR, render: RenderResult | None) -> VerificationReport:
        if render is None:
            report = VerificationReport()
            report.add("info", "<style>", "no render result; skipping style lint")
            return report
        spec: dict[str, Any] = {"style": self.style, "targets": self.targets}
        if self.live is not None:
            spec["live"] = self.live
        return style_lint(
            render.mp4_path,
            spec,
            scene=ir if ir.timeline else None,
            miss_severity=self.miss_severity,
        ).report


def _format_text(result: StyleLintResult, targets: Mapping[str, Sequence[float]]) -> str:
    """The human-readable report: metrics beside targets, findings, per shot."""
    m = result.metrics
    out = []
    if m is not None:
        out.append(f"{m.duration_s} s at {m.fps} fps, {m.cuts} cut(s) from {m.cut_source}")
        out.append("")
        out.append(f"{'metric':28} {'value':>8}  target")
        for name in METRICS:
            rng = targets.get(name)
            value = getattr(m, name)
            mark = ""
            if rng is not None:
                mark = "  ok" if rng[0] <= value <= rng[1] else "  MISS"
            tgt = f"[{rng[0]}, {rng[1]}]" if rng is not None else ""
            out.append(f"{name:28} {value!s:>8}  {tgt}{mark}")
    if result.per_shot:
        out.append("")
        out.append("per shot:")
        cols = ("start_s", "duration_s", *SHOT_METRICS)
        short = {
            "identical_frame_share": "identical",
            "pose_changes_per_s": "changes/s",
            "one_frame_interval_share": "ones",
            "two_frame_interval_share": "twos",
            "three_plus_interval_share": "threes+",
            "max_hold_frames": "max_hold",
            "start_s": "start",
            "duration_s": "dur",
        }
        width = max(len(r.shot) for r in result.per_shot)
        out.append(f"{'shot':{width}} " + " ".join(f"{short[c]:>10}" for c in cols))
        for r in result.per_shot:
            out.append(
                f"{r.shot:{width}} " + " ".join(f"{getattr(r, c)!s:>10}" for c in cols)
            )
    notes = [f for f in result.report.findings if f.severity != "info" or f.ir_path != "<style>"]
    if notes:
        out.append("")
        for f in notes:
            line = f"{f.severity}: {f.description}"
            if f.suggested_fix:
                line += f"\n  fix: {f.suggested_fix}"
            out.append(line)
    return "\n".join(out)


def _main(argv: Sequence[str]) -> int:
    """``python -m an.verify.style VIDEO SPEC.yaml [--project DIR] [--json]``.

    Prints the metrics beside the targets, one line per finding with its fix,
    and the per-shot cadence. The shots come from ``--project`` (a project
    directory or a ``scene.json``); without it, a video at
    ``<project>/output/*.mp4`` finds its own project, and anything else falls
    back to detecting cuts from pixels — with a warning, because that misses
    cuts. Exit status 0 when every target hits, 1 on a miss, 2 when it could not
    measure.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m an.verify.style",
        description="Measure a render against a style spec's targets.",
    )
    parser.add_argument("video", help="the rendered mp4")
    parser.add_argument("spec", help="a style spec YAML (an-style skill: styles/<name>.yaml)")
    parser.add_argument(
        "--project",
        "--scene",
        dest="project",
        default=None,
        help="the project directory (or its ir/scene.json) the video was rendered "
        "from, for exact cuts; found automatically for <project>/output/*.mp4",
    )
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(list(argv))

    project = args.project or project_of_render(args.video)
    if project is None:
        print(
            "warning: no project given and none found beside the video, so cuts are "
            "detected from pixels (misses cuts between shots on one backdrop, and "
            "dissolves); pass --project DIR",
            file=sys.stderr,
        )
    elif args.project is None:
        print(f"using the shot list of {project}", file=sys.stderr)
    try:
        result = style_lint(args.video, args.spec, scene=project)
    except StyleLintError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {
                    "metrics": result.metrics.as_dict() if result.metrics else None,
                    "per_shot": [r.as_dict() for r in result.per_shot],
                    "findings": [asdict(f) for f in result.report.findings],
                },
                indent=2,
            )
        )
    else:
        print(_format_text(result, _targets_of(args.spec)[1]))
    if result.metrics is None:
        return 2
    return 0 if all(f.severity == "info" for f in result.report.findings) else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
