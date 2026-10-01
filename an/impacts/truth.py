"""Ground truth: what was intended, what was executed, and what each frame shows.

Every position here comes from one of two sources, and they are checked against
each other at every instant the renderer captures:

- **the compiled document**, evaluated by `an.stage.timeline` — the
  executable spec of the JS runtime (parity-tested under node) — and projected
  to canvas pixels by `screen_position`. The per-frame keypoints come from
  here, at exactly the instants the renderer captured;
- **the analytic stroke** (:class:`an.impacts.stroke.Stroke`), mapped through
  the object's affine channels. The dense trajectory comes from here, because
  it is exact at any instant and cheap.

A frame with an open shutter is the AVERAGE of its sample instants, so what it
shows is the average of the keypoint's positions over them — not the position
at mid-exposure. The two differ most exactly where estimators are scored: a
surface contact is a V in position, and its average sits above contact (by
~6 px at 30 fps and a 180-degree shutter). So each frame records both, and the
observation stream carries the average.

:func:`ground_truth` refuses (:class:`TruthMismatch`) if the two sources
disagree at any sample instant, or if the compiled document does not put the
object at contact at every executed impact; `write_impact_clip` additionally
refuses if the document the renderer staged is not the one the truth was read
from. A sidecar that could silently drift from its video would be worse than
none.

**The ``truth.json`` schema** (``schema: "an.impacts/truth"``, version
:data:`TRUTH_SCHEMA_VERSION`; every time is scene seconds, every position canvas
pixels with the origin at the top-left and ``y`` down; objects are a LIST so a
clip with two can be described without changing any reader):

- ``generator`` — ``{package, version, module}``.
- ``spec`` — the :class:`an.impacts.clip.ImpactClipSpec`, verbatim;
  ``ImpactClipSpec.from_dict(truth["spec"])`` regenerates the clip (byte for
  byte under the same `an` version).
- ``clock`` — the resolved :class:`an.frame_clock.FrameClock`.
- ``tempo`` — ``{points: [[beat, bpm], ...]}``, piecewise-linear in beats.
- ``clip`` — ``{duration, fps, width, height, frame_count, rendered, files}``.
- ``objects`` — one entry per striking object: ``{name, keypoints: [names],
  impact_keypoint, params, surface_xy (top-centre of the surface, or null),
  stroke: {kind, segments: [{t0, t1, h0, h1, easing}], channels: [{target,
  property, contact_value, stroke_extent}]}}``. ``h`` is exact and
  continuous; each channel's value is ``contact_value - stroke_extent * h``.
- ``events`` — one per impact:

  - ``object`` (a name from ``objects``), ``index``, ``beat``, ``amplitude``;
  - ``t_grid`` — INTENDED time (the tempo grid);
  - ``t_impact`` — EXECUTED time, continuous; ``offset = t_impact - t_grid``;
  - ``kind`` — ``surface`` (contact; velocity reverses at ``t_impact``) or
    ``air`` (turning point; velocity is zero at ``t_impact``);
  - ``t_peak_speed`` (``= t_impact`` for surface, ``t_impact - brake`` for
    air), ``peak_speed`` (stroke heights/s), ``peak_speed_px`` (the impact
    keypoint's px/s), ``fall``, ``brake`` (seconds);
  - ``impact_xy`` — the impact keypoint at ``t_impact``;
  - ``frames`` — what the frames show: ``before`` (last frame whose exposure
    closed at or before the impact), ``after`` (first to open at or after it),
    ``during`` (the frame whose exposure contains it, else ``null``),
    ``nearest`` (+ ``nearest_error``, by exposure midpoint), and ``lowest`` —
    the frame a naive "lowest point" detector picks, by the stroke height the
    frame SHOWS (averaged over its samples) — with ``lowest_h``,
    ``lowest_t_reported`` and ``lowest_error`` (its reported time minus
    ``t_impact``: the frame-snapped baseline's error).

- ``frames`` — one per video frame: ``index``, ``t_nominal`` (``index / fps``,
  what the mp4 says), ``t_open``, ``t_close``, ``t_mid``, ``samples`` (the
  instants rendered and averaged), ``t_reported`` (what ``keypoints.ndjson``
  carries as ``t``), ``keypoints`` (``{object: {name: [x, y]}}``, averaged
  over the samples — what the frame shows) and ``keypoints_mid`` (at
  ``t_mid``; equal to ``keypoints`` when the shutter is instantaneous).

``keypoints.ndjson`` is one line per frame,
``{"tick", "t", "value": {"width", "height", "keypoints": [{"object", "name",
"x", "y"}]}}`` — observations only (the frame's ``keypoints``, at its reported
time). ``trajectory.csv`` is ``t, h, <object>.<kp>_x, <object>.<kp>_y, ...`` at
``spec.trajectory_hz``.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from an.stage.serialize import CutoutSceneJSON
from an.stage.timeline import (
    evaluate_timeline,
    screen_position,
    timeline_from_scene,
)
from an.frame_clock import CapturedFrame
from an.impacts.objects import ImpactObject
from an.impacts.performance import ImpactEvent
from an.impacts.stroke import Stroke

__all__ = [
    "KEYPOINT_TOLERANCE_PX",
    "TRUTH_SCHEMA",
    "TRUTH_SCHEMA_VERSION",
    "TruthMismatch",
    "ground_truth",
    "keypoint_lines",
    "trajectory_rows",
]

TRUTH_SCHEMA: str = "an.impacts/truth"
#: Bumped on any change a reader must know about; additive fields bump MINOR.
TRUTH_SCHEMA_VERSION: str = "1.0.0"

#: The analytic and compiled keypoints must agree to this many pixels. Both are
#: double-precision evaluations of the same easing, so any real disagreement is
#: orders of magnitude larger.
KEYPOINT_TOLERANCE_PX: float = 1e-6

#: The compiled property must equal the contact value at each impact to this.
_CONTACT_TOLERANCE: float = 1e-9

#: Finite-difference step for the impact keypoint's peak speed (seconds).
_SPEED_DT: float = 1e-5

Points = dict[str, tuple[float, float]]


class TruthMismatch(RuntimeError):
    """The ground truth and the thing it describes disagree."""


@dataclass
class _Projector:
    """Keypoint pixels at a time, from the compiled doc or from the stroke."""

    scene: CutoutSceneJSON
    obj: ImpactObject
    stroke: Stroke
    timeline: Any = field(init=False)

    def __post_init__(self) -> None:
        self.timeline = timeline_from_scene(self.scene)

    def compiled(self, t: float) -> Points:
        return self._project(evaluate_timeline(self.timeline, t))

    def analytic(self, t: float) -> Points:
        return self._project(self.obj.pose(self.stroke.h(t)))

    def checked(self, t: float, *, frame: int) -> Points:
        """The compiled positions at ``t``, refused if the stroke disagrees."""
        compiled, analytic = self.compiled(t), self.analytic(t)
        for name, (x, y) in compiled.items():
            ax, ay = analytic[name]
            if max(abs(x - ax), abs(y - ay)) > KEYPOINT_TOLERANCE_PX:
                raise TruthMismatch(
                    f"frame {frame}, sample t={t!r}, keypoint {name!r}: compiled "
                    f"{(x, y)} vs analytic {(ax, ay)}"
                )
        return compiled

    def _project(self, pose) -> Points:
        return {
            name: screen_position(
                self.scene, self.obj.keypoint_node(name), pose=pose, point=local
            )
            for name, local in self.obj.keypoints.items()
        }


def _mean(points: Sequence[Points]) -> Points:
    n = float(len(points))
    return {
        name: (sum(p[name][0] for p in points) / n, sum(p[name][1] for p in points) / n)
        for name in points[0]
    }


def _check_contacts(projector: _Projector, events: Sequence[ImpactEvent]) -> None:
    for e in events:
        pose = evaluate_timeline(projector.timeline, e.t_impact)
        for c in projector.obj.channels:
            got = pose.get((c.target, c.property))
            if got is None or abs(got - c.contact_value) > _CONTACT_TOLERANCE:
                raise TruthMismatch(
                    f"impact {e.index} at t={e.t_impact!r}: the compiled document "
                    f"has {c.target}:{c.property}={got!r}, not the contact value "
                    f"{c.contact_value!r}"
                )


def _shown_h(frame: CapturedFrame, stroke: Stroke) -> float:
    """The stroke height a frame SHOWS: its samples' average."""
    return sum(stroke.h(t) for t in frame.samples) / len(frame.samples)


def _frame_evidence(
    event: ImpactEvent,
    frames: Sequence[CapturedFrame],
    stroke: Stroke,
    window: tuple[float, float],
) -> dict[str, Any]:
    """Which frames bracket, contain and best approximate one impact."""
    T = event.t_impact
    closes = [f.t_close for f in frames]
    opens = [f.t_open for f in frames]
    before = bisect.bisect_right(closes, T) - 1
    after = bisect.bisect_left(opens, T)
    during = next((f.index for f in frames if f.t_open < T < f.t_close), None)
    nearest = min(frames, key=lambda f: abs(f.t_mid - T))
    in_window = [f for f in frames if window[0] <= f.t_mid <= window[1]] or [nearest]
    lowest = min(in_window, key=lambda f: (_shown_h(f, stroke), abs(f.t_mid - T)))
    return {
        "before": before if before >= 0 else None,
        "after": after if after < len(frames) else None,
        "during": during,
        "nearest": nearest.index,
        "nearest_error": nearest.t_mid - T,
        "lowest": lowest.index,
        "lowest_h": _shown_h(lowest, stroke),
        "lowest_t_reported": lowest.t_reported,
        "lowest_error": lowest.t_reported - T,
    }


def _xy(points: Points) -> dict[str, list[float]]:
    return {name: [x, y] for name, (x, y) in points.items()}


def ground_truth(
    *,
    scene: CutoutSceneJSON,
    obj: ImpactObject,
    stroke: Stroke,
    events: Sequence[ImpactEvent],
    frames: Sequence[CapturedFrame],
    header: dict[str, Any],
) -> dict[str, Any]:
    """The truth document for one clip (see the module docstring for its schema).

    ``header`` is merged in first (spec, clock, tempo, clip, generator); this
    function owns ``objects``, ``events`` and ``frames``.
    """
    projector = _Projector(scene, obj, stroke)
    _check_contacts(projector, events)

    frame_docs = []
    for f in frames:
        shown = _mean([projector.checked(t, frame=f.index) for t in f.samples])
        mid = shown if len(f.samples) == 1 else projector.compiled(f.t_mid)
        frame_docs.append(
            {
                **f.to_dict(),
                "keypoints": {obj.name: _xy(shown)},
                "keypoints_mid": {obj.name: _xy(mid)},
            }
        )

    times = [e.t_impact for e in events]
    bounds = [0.0, *((a + b) / 2.0 for a, b in zip(times, times[1:])), stroke.duration]
    kin = {k.index: k for k in stroke.kinematics}
    event_docs = []
    for k, e in enumerate(events):
        kk = kin[e.index]
        tp = kk.t_peak_speed
        p0 = projector.analytic(tp - _SPEED_DT)[obj.impact_keypoint]
        p1 = projector.analytic(tp)[obj.impact_keypoint]
        speed_px = ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5 / _SPEED_DT
        event_docs.append(
            {
                "object": obj.name,
                **e.to_dict(),
                "kind": stroke.kind,
                "t_peak_speed": tp,
                "peak_speed": kk.peak_speed,
                "peak_speed_px": speed_px,
                "fall": kk.fall,
                "brake": kk.brake,
                "impact_xy": list(projector.analytic(e.t_impact)[obj.impact_keypoint]),
                "frames": _frame_evidence(
                    e, frames, stroke, (bounds[k], bounds[k + 1])
                ),
            }
        )

    surface_xy = None
    if obj.surface_at is not None:
        surface_xy = [
            obj.surface_at[0] + scene.meta.width / 2.0,
            obj.surface_at[1] + scene.meta.height / 2.0,
        ]
    return {
        "schema": TRUTH_SCHEMA,
        "schema_version": TRUTH_SCHEMA_VERSION,
        **header,
        "objects": [
            {
                "name": obj.name,
                "keypoints": list(obj.keypoints),
                "impact_keypoint": obj.impact_keypoint,
                "params": dict(obj.params),
                "surface_xy": surface_xy,
                "stroke": {
                    "kind": stroke.kind,
                    "segments": [s.to_dict() for s in stroke.segments],
                    "channels": [c.to_dict() for c in obj.channels],
                },
            }
        ],
        "events": event_docs,
        "frames": frame_docs,
    }


def keypoint_lines(
    truth: dict[str, Any], *, digits: int = 4
) -> Iterator[dict[str, Any]]:
    """One observation per frame, in thoremin's recorder shape.

    ``{"tick", "t", "value": {"width", "height", "keypoints": [{"object",
    "name", "x", "y"}]}}`` — ``t`` is the frame's REPORTED timestamp and the
    points are what the frame shows; nothing else from the truth leaks in.
    """
    width, height = truth["clip"]["width"], truth["clip"]["height"]
    for f in truth["frames"]:
        yield {
            "tick": f["index"],
            "t": round(f["t_reported"], 9),
            "value": {
                "width": width,
                "height": height,
                "keypoints": [
                    {
                        "object": o,
                        "name": n,
                        "x": round(x, digits),
                        "y": round(y, digits),
                    }
                    for o, points in f["keypoints"].items()
                    for n, (x, y) in points.items()
                ],
            },
        }


def trajectory_rows(
    *,
    scene: CutoutSceneJSON,
    obj: ImpactObject,
    stroke: Stroke,
    hz: float,
    digits: int = 6,
) -> Iterator[list[Any]]:
    """The dense continuous trajectory: a header row, then one row per ``1/hz`` s."""
    projector = _Projector(scene, obj, stroke)
    names = list(obj.keypoints)
    yield [
        "t",
        "h",
        *(f"{obj.name}.{n}_{axis}" for n in names for axis in ("x", "y")),
    ]
    # `+ 1e-9`: `int(2.3 * 1000)` is 2299, which would drop the last sample.
    n = int(stroke.duration * hz + 1e-9)
    for i in range(n + 1):
        t = min(i / hz, stroke.duration)
        points = projector.analytic(t)
        yield [
            round(t, 9),
            round(stroke.h(t), digits),
            *(round(v, digits) for name in names for v in points[name]),
        ]
