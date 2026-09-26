"""Ground truth: what was intended, what was executed, and what each frame shows.

Every position here comes from one of two sources, and they are checked against
each other on every clip:

- **the compiled document**, evaluated by `an.adapters.cutout.timeline` — the
  executable spec of the JS runtime (parity-tested under node) — and projected
  to canvas pixels by `screen_position`. The per-frame keypoints come from
  here, at exactly the instants the renderer captured, so they describe the
  pixels in the video rather than an intention about them;
- **the analytic stroke** (:class:`an.impacts.stroke.Stroke`), mapped through
  the object's affine map. The dense trajectory comes from here, because it is
  exact at any instant and cheap.

:func:`ground_truth` refuses (``TruthMismatch``) if the two disagree anywhere a
frame was taken, or if the compiled document does not put the object at
contact at every executed impact time. A sidecar that could silently drift from
its video would be worse than none.

**The ``truth.json`` schema** (``schema: "an.impacts/truth"``, version
:data:`TRUTH_SCHEMA_VERSION`; every time is scene seconds, every position canvas
pixels with the origin at the top-left and ``y`` down):

- ``generator`` — ``{package, version, module}``.
- ``spec`` — the :class:`an.impacts.clip.ImpactClipSpec`, verbatim;
  ``ImpactClipSpec.from_dict(truth["spec"])`` regenerates the clip byte for byte.
- ``clock`` — the resolved :class:`an.frame_clock.FrameClock`.
- ``tempo`` — ``{points: [[beat, bpm], ...]}``, piecewise-linear in beats.
- ``clip`` — ``{duration, fps, width, height, frame_count, rendered, files}``.
- ``object`` — ``{name, keypoints: [names], impact_keypoint, params}``.
- ``stroke`` — ``{kind, target, property, contact_value, stroke_extent,
  segments: [{t0, t1, h0, h1, easing}]}``: the exact continuous motion. The
  animated property is ``contact_value - stroke_extent * h``.
- ``events`` — one per impact:

  - ``index``, ``beat``, ``amplitude`` (stroke height of the preparation);
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
    the frame a naive "lowest point" detector picks — with ``lowest_h``,
    ``lowest_t_reported`` and ``lowest_error`` (its reported time minus
    ``t_impact``: the frame-snapped baseline's error).

- ``frames`` — one per video frame: ``index``, ``t_nominal`` (``index / fps``,
  what the mp4 says), ``t_open``, ``t_close``, ``t_mid``, ``samples`` (the
  instants rendered and averaged) and ``t_reported`` (what
  ``keypoints.ndjson`` carries as ``t``).

``keypoints.ndjson`` is one line per frame,
``{"tick", "t", "value": {"width", "height", "keypoints": [{"name", "x", "y"}]}}``
— observations only, at each frame's ``t_mid``. ``trajectory.csv`` is
``t, h, <kp>_x, <kp>_y, ...`` at ``spec.trajectory_hz``.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from an.adapters.cutout.serialize import CutoutSceneJSON
from an.adapters.cutout.timeline import (
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


class TruthMismatch(RuntimeError):
    """The compiled document and the analytic stroke disagree."""


@dataclass
class _Projector:
    """Keypoint pixels at a time, from the compiled doc or from the stroke."""

    scene: CutoutSceneJSON
    obj: ImpactObject
    stroke: Stroke
    timeline: Any = field(init=False)

    def __post_init__(self) -> None:
        self.timeline = timeline_from_scene(self.scene)

    def compiled(self, t: float) -> dict[str, tuple[float, float]]:
        return self._project(evaluate_timeline(self.timeline, t))

    def analytic(self, t: float) -> dict[str, tuple[float, float]]:
        value = self.obj.value(self.stroke.h(t))
        return self._project({(self.obj.name, self.obj.property): value})

    def _project(self, pose) -> dict[str, tuple[float, float]]:
        return {
            name: screen_position(self.scene, self.obj.name, pose=pose, point=local)
            for name, local in self.obj.keypoints.items()
        }


def _check_contacts(projector: _Projector, events: Sequence[ImpactEvent]) -> None:
    key = (projector.obj.name, projector.obj.property)
    for e in events:
        got = evaluate_timeline(projector.timeline, e.t_impact).get(key)
        if got is None or abs(got - projector.obj.contact_value) > _CONTACT_TOLERANCE:
            raise TruthMismatch(
                f"impact {e.index} at t={e.t_impact!r}: the compiled document has "
                f"{key[1]}={got!r}, not the contact value {projector.obj.contact_value!r}"
            )


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
    lowest = min(in_window, key=lambda f: (stroke.h(f.t_mid), abs(f.t_mid - T)))
    return {
        "before": before if before >= 0 else None,
        "after": after if after < len(frames) else None,
        "during": during,
        "nearest": nearest.index,
        "nearest_error": nearest.t_mid - T,
        "lowest": lowest.index,
        "lowest_h": stroke.h(lowest.t_mid),
        "lowest_t_reported": lowest.t_reported,
        "lowest_error": lowest.t_reported - T,
    }


def ground_truth(
    *,
    scene: CutoutSceneJSON,
    obj: ImpactObject,
    stroke: Stroke,
    events: Sequence[ImpactEvent],
    frames: Sequence[CapturedFrame],
    header: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, tuple[float, float]]]]:
    """``(truth document, per-frame keypoints)`` for one clip.

    ``header`` is merged in first (spec, clip, generator); this function owns
    ``events``, ``frames``, ``object`` and ``stroke``.
    """
    projector = _Projector(scene, obj, stroke)
    _check_contacts(projector, events)

    per_frame: list[dict[str, tuple[float, float]]] = []
    for f in frames:
        compiled, analytic = projector.compiled(f.t_mid), projector.analytic(f.t_mid)
        for name, (x, y) in compiled.items():
            ax, ay = analytic[name]
            if max(abs(x - ax), abs(y - ay)) > KEYPOINT_TOLERANCE_PX:
                raise TruthMismatch(
                    f"frame {f.index} (t_mid={f.t_mid!r}), keypoint {name!r}: "
                    f"compiled {(x, y)} vs analytic {(ax, ay)}"
                )
        per_frame.append(compiled)

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
                **e.to_dict(),
                "kind": stroke.kind,
                "t_peak_speed": tp,
                "peak_speed": kk.peak_speed,
                "peak_speed_px": speed_px,
                "fall": kk.fall,
                "brake": kk.brake,
                "impact_xy": list(projector.analytic(e.t_impact)[obj.impact_keypoint]),
                "frames": _frame_evidence(e, frames, stroke, (bounds[k], bounds[k + 1])),
            }
        )

    doc = {
        "schema": TRUTH_SCHEMA,
        "schema_version": TRUTH_SCHEMA_VERSION,
        **header,
        "object": {
            "name": obj.name,
            "keypoints": list(obj.keypoints),
            "impact_keypoint": obj.impact_keypoint,
            "params": dict(obj.params),
        },
        "stroke": {
            "kind": stroke.kind,
            "target": obj.name,
            "property": obj.property,
            "contact_value": obj.contact_value,
            "stroke_extent": obj.stroke_extent,
            "segments": [s.to_dict() for s in stroke.segments],
        },
        "events": event_docs,
        "frames": [f.to_dict() for f in frames],
    }
    return doc, per_frame


def keypoint_lines(
    frames: Sequence[CapturedFrame],
    per_frame: Sequence[dict[str, tuple[float, float]]],
    *,
    width: int,
    height: int,
    digits: int = 4,
) -> Iterator[dict[str, Any]]:
    """One observation per frame, in thoremin's recorder shape.

    ``{"tick", "t", "value": {"width", "height", "keypoints": [{"name","x","y"}]}}``
    — ``t`` is the frame's REPORTED timestamp, and nothing else from the ground
    truth leaks into the observation stream.
    """
    for f, points in zip(frames, per_frame):
        yield {
            "tick": f.index,
            "t": round(f.t_reported, 9),
            "value": {
                "width": width,
                "height": height,
                "keypoints": [
                    {"name": n, "x": round(x, digits), "y": round(y, digits)}
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
    yield ["t", "h", *(f"{n}_{axis}" for n in names for axis in ("x", "y"))]
    n = int(stroke.duration * hz)
    for i in range(n + 1):
        t = min(i / hz, stroke.duration)
        points = projector.analytic(t)
        yield [
            round(t, 9),
            round(stroke.h(t), digits),
            *(round(v, digits) for name in names for v in points[name]),
        ]
