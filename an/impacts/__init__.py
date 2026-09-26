"""Synthetic impact clips with exact ground truth, for scoring sub-frame timing.

Structured animations of simple objects — a stick or a ball — striking a
surface, or striking "the air" (a stroke that reverses with no contact), on a
known tempo grid. Each clip ships a sidecar that keeps three times apart:

- the **intended** grid time of every event (``t_grid``),
- the **executed** impact time in continuous seconds (``t_impact`` — the grid
  plus controllable humanisation, never snapped to a frame),
- and **what the frames show**: every frame's exposure interval and sample
  instants (:class:`an.frame_clock.FrameClock`: frame rate, shutter, capture
  jitter), the 2D keypoints at each frame, and which frames bracket each impact.

The clips are ordinary `an` scenes — props moved by tweens — rendered by the
cutout backend, and the ground truth is read back from the same compiled
document the renderer draws.

Quick start::

    from an.impacts import ImpactClipSpec, write_impact_clip, write_impact_set

    write_impact_clip(ImpactClipSpec(kind="air", fps=30, exposure=0.5,
                                     jitter_sd=0.01), "~/clips")
    write_impact_set("~/clips/set")      # 24 clips: objects x kinds x fps x shutter

Or from the shell: ``an impacts clip OUT_DIR`` / ``an impacts clip-set OUT_DIR``.

>>> plan = plan_impact_clip(ImpactClipSpec(kind="air", beats=2, tempo=60))
>>> [(e.t_grid, e.t_impact) for e in plan.events]
[(0.5, 0.5), (1.5, 1.5)]
"""

from an.frame_clock import CapturedFrame, FrameClock
from an.impacts.clip import (
    BENCHMARK_SPEC,
    CLIP_FILES,
    ImpactClipSpec,
    ImpactPlan,
    impact_set_specs,
    plan_impact_clip,
    write_impact_clip,
    write_impact_set,
)
from an.impacts.objects import IMPACT_OBJECTS, ImpactObject, ball, impact_object, stick
from an.impacts.performance import (
    ImpactEvent,
    TempoMap,
    gaussian_humanizer,
    perform,
    tempo_map,
)
from an.impacts.stroke import IMPACT_KINDS, Stroke, StrokeSegment, build_stroke
from an.impacts.truth import TRUTH_SCHEMA, TRUTH_SCHEMA_VERSION, TruthMismatch

__all__ = [
    "BENCHMARK_SPEC",
    "CLIP_FILES",
    "CapturedFrame",
    "FrameClock",
    "IMPACT_KINDS",
    "IMPACT_OBJECTS",
    "ImpactClipSpec",
    "ImpactEvent",
    "ImpactObject",
    "ImpactPlan",
    "Stroke",
    "StrokeSegment",
    "TRUTH_SCHEMA",
    "TRUTH_SCHEMA_VERSION",
    "TempoMap",
    "TruthMismatch",
    "ball",
    "build_stroke",
    "gaussian_humanizer",
    "impact_object",
    "impact_set_specs",
    "perform",
    "plan_impact_clip",
    "stick",
    "tempo_map",
    "write_impact_clip",
    "write_impact_set",
]
