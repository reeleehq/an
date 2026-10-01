# an.impacts.truth

Ground truth: what was intended, what was executed, and what each frame shows.

Every position here comes from one of two sources, and they are checked against
each other at every instant the renderer captures:

- **the compiled document**, evaluated by `an.stage.timeline` — the
  executable spec of the JS runtime (parity-tested under node) — and projected
  to canvas pixels by `screen_position`. The per-frame keypoints come from
  here, at exactly the instants the renderer captured;
- **the analytic stroke** ([`an.impacts.stroke.Stroke`](an.impacts.stroke.html.md#an.impacts.stroke.Stroke)), mapped through
  the object’s affine channels. The dense trajectory comes from here, because
  it is exact at any instant and cheap.

A frame with an open shutter is the AVERAGE of its sample instants, so what it
shows is the average of the keypoint’s positions over them — not the position
at mid-exposure. The two differ most exactly where estimators are scored: a
surface contact is a V in position, and its average sits above contact (by
~6 px at 30 fps and a 180-degree shutter). So each frame records both, and the
observation stream carries the average.

[`ground_truth()`](#an.impacts.truth.ground_truth) refuses ([`TruthMismatch`](#an.impacts.truth.TruthMismatch)) if the two sources
disagree at any sample instant, or if the compiled document does not put the
object at contact at every executed impact; `write_impact_clip` additionally
refuses if the document the renderer staged is not the one the truth was read
from. A sidecar that could silently drift from its video would be worse than
none.

\*\*The `truth.json` schema\*\* (`schema: "an.impacts/truth"`, version
[`TRUTH_SCHEMA_VERSION`](#an.impacts.truth.TRUTH_SCHEMA_VERSION); every time is scene seconds, every position canvas
pixels with the origin at the top-left and `y` down; objects are a LIST so a
clip with two can be described without changing any reader):

- `generator` — `{package, version, module}`.
- `spec` — the [`an.impacts.clip.ImpactClipSpec`](an.impacts.clip.html.md#an.impacts.clip.ImpactClipSpec), verbatim;
  `ImpactClipSpec.from_dict(truth["spec"])` regenerates the clip (byte for
  byte under the same `an` version).
- `clock` — the resolved [`an.frame_clock.FrameClock`](an.frame_clock.html.md#an.frame_clock.FrameClock).
- `tempo` — `{points: [[beat, bpm], ...]}`, piecewise-linear in beats.
- `clip` — `{duration, fps, width, height, frame_count, rendered, files}`.
- `objects` — one entry per striking object: `{name, keypoints: [names],
  impact_keypoint, params, surface_xy (top-centre of the surface, or null),
  stroke: {kind, segments: [{t0, t1, h0, h1, easing}], channels: [{target,
  property, contact_value, stroke_extent}]}}`. `h` is exact and
  continuous; each channel’s value is `contact_value - stroke_extent * h`.
- `events` — one per impact:
  - `object` (a name from `objects`), `index`, `beat`, `amplitude`;
  - `t_grid` — INTENDED time (the tempo grid);
  - `t_impact` — EXECUTED time, continuous; `offset = t_impact - t_grid`;
  - `kind` — `surface` (contact; velocity reverses at `t_impact`) or
    `air` (turning point; velocity is zero at `t_impact`);
  - `t_peak_speed` (`= t_impact` for surface, `t_impact - brake` for
    air), `peak_speed` (stroke heights/s), `peak_speed_px` (the impact
    keypoint’s px/s), `fall`, `brake` (seconds);
  - `impact_xy` — the impact keypoint at `t_impact`;
  - `frames` — what the frames show: `before` (last frame whose exposure
    closed at or before the impact), `after` (first to open at or after it),
    `during` (the frame whose exposure contains it, else `null`),
    `nearest` (+ `nearest_error`, by exposure midpoint), and `lowest` —
    the frame a naive “lowest point” detector picks, by the stroke height the
    frame SHOWS (averaged over its samples) — with `lowest_h`,
    `lowest_t_reported` and `lowest_error` (its reported time minus
    `t_impact`: the frame-snapped baseline’s error).
- `frames` — one per video frame: `index`, `t_nominal` (`index / fps`,
  what the mp4 says), `t_open`, `t_close`, `t_mid`, `samples` (the
  instants rendered and averaged), `t_reported` (what `keypoints.ndjson`
  carries as `t`), `keypoints` (`{object: {name: [x, y]}}`, averaged
  over the samples — what the frame shows) and `keypoints_mid` (at
  `t_mid`; equal to `keypoints` when the shutter is instantaneous).

`keypoints.ndjson` is one line per frame,
`{"tick", "t", "value": {"width", "height", "keypoints": [{"object", "name",
"x", "y"}]}}` — observations only (the frame’s `keypoints`, at its reported
time). `trajectory.csv` is `t, h, <object>.<kp>_x, <object>.<kp>_y, ...` at
`spec.trajectory_hz`.

### Module Attributes

| [`TRUTH_SCHEMA_VERSION`](#an.impacts.truth.TRUTH_SCHEMA_VERSION)   | Bumped on any change a reader must know about; additive fields bump MINOR.   |
|-------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`KEYPOINT_TOLERANCE_PX`](#an.impacts.truth.KEYPOINT_TOLERANCE_PX)  | The analytic and compiled keypoints must agree to this many pixels.          |

### Functions

| [`ground_truth`](#an.impacts.truth.ground_truth)(\*, scene, obj, stroke, events, ...)   | The truth document for one clip (see the module docstring for its schema).   |
|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`keypoint_lines`](#an.impacts.truth.keypoint_lines)(truth, \*[, digits])                 | One observation per frame, in thoremin's recorder shape.                     |
| [`trajectory_rows`](#an.impacts.truth.trajectory_rows)(\*, scene, obj, stroke, hz[, ...])  | The dense continuous trajectory: a header row, then one row per `1/hz` s.    |

### Exceptions

| [`TruthMismatch`](#an.impacts.truth.TruthMismatch)   | The ground truth and the thing it describes disagree.   |
|------------------------------------------------------------------|---------------------------------------------------------|

### an.impacts.truth.KEYPOINT_TOLERANCE_PX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1e-06*

The analytic and compiled keypoints must agree to this many pixels. Both are
double-precision evaluations of the same easing, so any real disagreement is
orders of magnitude larger.

### an.impacts.truth.TRUTH_SCHEMA_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '1.0.0'*

Bumped on any change a reader must know about; additive fields bump MINOR.

### *exception* an.impacts.truth.TruthMismatch

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The ground truth and the thing it describes disagree.

### an.impacts.truth.ground_truth(, scene, obj, stroke, events, frames, header)

The truth document for one clip (see the module docstring for its schema).

`header` is merged in first (spec, clock, tempo, clip, generator); this
function owns `objects`, `events` and `frames`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.impacts.truth.keypoint_lines(truth, , digits=4)

One observation per frame, in thoremin’s recorder shape.

`{"tick", "t", "value": {"width", "height", "keypoints": [{"object",
"name", "x", "y"}]}}` — `t` is the frame’s REPORTED timestamp and the
points are what the frame shows; nothing else from the truth leaks in.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.impacts.truth.trajectory_rows(, scene, obj, stroke, hz, digits=6)

The dense continuous trajectory: a header row, then one row per `1/hz` s.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]
