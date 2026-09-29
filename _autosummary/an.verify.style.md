# an.verify.style

Style lint: measure a render’s cadence, cut rate and palette, and compare them to a style’s targets.

“Make it in the style of X” is only checkable if X is a set of numbers. The
cut-out styles research (`misc/docs/cutout_styles_research.md`) measured six
styles with one fixed set of statistics; this module is that measurement,
ported, so an agent can render, measure the same statistics on its own output,
and adjust. The style specs that carry the `targets` live with the downstream
skill (`.claude/skills/an-style/styles/*.yaml`).

**The estimators are the research’s estimators, on purpose.** Every threshold
below is the one the six styles were measured with, including the ones that are
crude (a noise floor at the 10th percentile of frame differences, a cut as a
colour-histogram jump). A better estimator would measure a different quantity
from the one the targets were calibrated on, and a render would then pass or
miss for a reason nobody measured. Change an estimator only together with
re-measuring the targets.

What is measured (see [`METRICS`](#an.verify.style.METRICS) for the vocabulary a spec’s `targets`
may use):

- **Holds and cadence.** A frame “changes” when its mean absolute grey
  difference from the previous frame exceeds `max(0.25, 2.5 × p10)`, where
  p10 is the clip’s own 10th-percentile difference (compression noise, capped
  at 1.0 — see `NOISE_FLOOR_CAP`). From
  that: the share of frames identical to the previous one, pose changes per
  second, and the histogram of gaps between successive changes (one frame = on
  ones, two = on twos, three or more = threes and holds, gaps above 12 frames
  ignored as holds rather than cadence).
- **Cuts and shot length.** For an `an` render the cuts are KNOWN — every shot
  boundary in the IR is a hard cut, because shots are concatenated — so the
  verifier takes them from the IR. Without an IR (any mp4), a cut is a frame
  whose 8×8×8 colour-histogram L1 distance exceeds 0.6 and whose mean
  difference exceeds 8; dissolves and morphs are missed, so on such footage the
  count is a floor.
- **Palette.** Mean HSV saturation, the share of dark pixels (every channel
  below 60, an outline proxy), and the coverage of the 16 most common colours
  after 4-bit quantisation (flatness), all on every 15th frame.

Not ported, deliberately: the research also measured global camera motion
(`cv2.phaseCorrelate`) and a k-means palette. Both need OpenCV or
scikit-learn, and this module adds no dependency — numpy and the ffmpeg binary
are already what `an.verify.media` uses.

A pure function over frames — [`measure_style()`](#an.verify.style.measure_style) — is the core, so it is
testable without ffmpeg:

```pycon
>>> import numpy as np
>>> still = np.zeros((4, 8, 8, 3), np.uint8)
>>> frames = np.concatenate([still, still + 200, still + 200, still])  # 16 frames, changes at 4 and 12
>>> m = measure_style(frames, fps=4.0, shot_durations=[4.0])
>>> m.identical_frame_share, m.pose_changes_per_s
(0.867, 0.5)
```

A target is a `[low, high]` range; a miss is a warning naming the knob that
moves it:

```pycon
>>> findings = check_targets(m, {"identical_frame_share": [0.2, 0.5]})
>>> findings[0].severity, findings[0].ir_path
('warning', '<style>/identical_frame_share')
>>> check_targets(m, {"identical_frame_share": [0.5, 0.9]})
[]
```

A target nothing measures is refused, not ignored — a spec that silently checks
less than it says is worse than one that fails to load:

```pycon
>>> check_targets(m, {"camera_shake": [0, 1]})
Traceback (most recent call last):
...
ValueError: unknown style target 'camera_shake'; measurable targets are [...]
```

### Module Attributes

| [`METRICS`](#an.verify.style.METRICS)   | every key a spec's `targets` may use, and what it is.   |
|------------------------------------------------------------|---------------------------------------------------------|

### Functions

| [`measure_style`](#an.verify.style.measure_style)(frames, \*, fps[, shot_durations])   | Measure the [`METRICS`](#an.verify.style.METRICS) on `frames`, an `(n, h, w, 3)` uint8 RGB array.   |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| [`measure_video`](#an.verify.style.measure_video)(mp4, \*[, shot_durations, ...])      | Decode `mp4` at the research's scale and [`measure_style()`](#an.verify.style.measure_style) it.          |
| [`check_targets`](#an.verify.style.check_targets)(metrics, targets, \*[, ...])         | One `Finding` per target the metrics miss; `[]` when all hit.                                                          |
| [`load_style_spec`](#an.verify.style.load_style_spec)(spec)                              | A style spec as a dict: a mapping is passed through, a path is read as YAML.                                           |
| [`style_lint`](#an.verify.style.style_lint)(mp4, spec_or_targets, \*[, ...])        | Measure `mp4` and compare it to a style spec's `targets`.                                                              |

### Classes

| [`StyleMetrics`](#an.verify.style.StyleMetrics)(fps, frames, duration_s, ...)    | The statistics [`METRICS`](#an.verify.style.METRICS) names, measured on one clip.   |
|------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| [`StyleLintResult`](#an.verify.style.StyleLintResult)(metrics, report)              | What one lint run measured, and what it found.                                                         |
| [`StyleLintVerifier`](#an.verify.style.StyleLintVerifier)(spec_or_targets, \*[, ...]) | Compare a render to a style spec's `targets`.                                                          |

### an.verify.style.METRICS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'cuts_per_min': 'hard cuts per minute', 'dark_pixel_share': 'share of pixels with every channel below 60', 'identical_frame_share': 'share of frames identical to the previous one (holds)', 'max_hold_frames': 'longest run of identical frames', 'mean_saturation': 'mean HSV saturation, 0..1', 'mean_shot_s': 'mean shot length in seconds', 'one_frame_interval_share': 'share of change gaps of one frame (on ones)', 'pose_changes_per_s': 'changed frames per second', 'three_plus_interval_share': 'share of change gaps of three to twelve frames', 'top16_colour_coverage': 'coverage of the 16 commonest 4-bit colours (flatness)', 'two_frame_interval_share': 'share of change gaps of two frames (on twos)'}*

every key a spec’s `targets` may use, and what it is.

* **Type:**
  The target vocabulary

### *class* an.verify.style.StyleLintResult(metrics, report)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one lint run measured, and what it found.

### *class* an.verify.style.StyleLintVerifier(spec_or_targets, , miss_severity='warning')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Compare a render to a style spec’s `targets`. Implements `Verifier`.

Shot boundaries come from the IR (every shot boundary is a hard cut in an
`an` render), so `cuts_per_min` and `mean_shot_s` are exact rather
than detected. Pre-render (`render is None`) it reports `info` and
passes: it has nothing to measure yet.

### *class* an.verify.style.StyleMetrics(fps, frames, duration_s, identical_frame_share, pose_changes_per_s, one_frame_interval_share, two_frame_interval_share, three_plus_interval_share, max_hold_frames, cuts, cuts_per_min, mean_shot_s, mean_saturation, dark_pixel_share, top16_colour_coverage, cut_source, change_threshold)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The statistics [`METRICS`](#an.verify.style.METRICS) names, measured on one clip.

#### cut_source *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`"shots"` (a shot list, exact) or `"pixels"`.

* **Type:**
  Where the cuts came from

### an.verify.style.check_targets(metrics, targets, , miss_severity='warning')

One `Finding` per target the metrics miss; `[]` when all hit.

Raises `ValueError` for a target [`METRICS`](#an.verify.style.METRICS) does not name, or a range
that is not `[low, high]` with `low <= high`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Finding`](an.verify.md#an.verify.Finding)]

### an.verify.style.load_style_spec(spec)

A style spec as a dict: a mapping is passed through, a path is read as YAML.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.verify.style.measure_style(frames, , fps, shot_durations=None)

Measure the [`METRICS`](#an.verify.style.METRICS) on `frames`, an `(n, h, w, 3)` uint8 RGB array.

`shot_durations` (seconds, in order) gives the cuts exactly; without it the
pixel cut detector is used. Ratios are rounded to three decimals.

* **Return type:**
  [`StyleMetrics`](#an.verify.style.StyleMetrics)

```pycon
>>> import numpy as np
>>> f = np.zeros((6, 4, 4, 3), np.uint8)
>>> f[1::2] = 255                       # a change on every frame
>>> m = measure_style(f, fps=6.0, shot_durations=[1.0])
>>> m.identical_frame_share, m.one_frame_interval_share, m.cuts
(0.0, 1.0, 0)
```

### an.verify.style.measure_video(mp4, , shot_durations=None, width=320, height=180)

Decode `mp4` at the research’s scale and [`measure_style()`](#an.verify.style.measure_style) it.

* **Return type:**
  [`StyleMetrics`](#an.verify.style.StyleMetrics)

### an.verify.style.style_lint(mp4, spec_or_targets, , shot_durations=None, miss_severity='warning')

Measure `mp4` and compare it to a style spec’s `targets`.

A decode or probe failure is reported at
[`an.verify.vision.FAILURE_SEVERITY`](an.verify.vision.md#an.verify.vision.FAILURE_SEVERITY), never as `info` — a lint that
could not run must not read as a clean one. A malformed spec raises: that is
the caller’s error, not the video’s.

* **Return type:**
  [`StyleLintResult`](#an.verify.style.StyleLintResult)
