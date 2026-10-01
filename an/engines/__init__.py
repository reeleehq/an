"""Engines: seekable things the core drives frame by frame, and the renderer that drives them.

Core (ADR 0001 decision 12; core study §2.7). No engine is core: the core holds
the PROTOCOL and the frame stage, and an engine -- the 2D stage runtime, a
``previz`` view behind a page, a ``burns`` crop over a still -- lives in its own
package and registers the renderer :func:`frame_stage_renderer` builds from it.

- :mod:`an.engines.protocol` -- ``Engine`` (a factory that opens a session per
  shot), the time-driven and state-driven session protocols, the declared live
  tier, and :func:`describe`, which reads a session's tier, drive mode and
  features off the members it implements (never off a flag).
- :mod:`an.engines.capture` -- the capture loop, sequential or batched, with the
  frame stage's resolves (supersample, shutter).
- :mod:`an.engines.frame_stage` -- :func:`frame_stage_renderer`: an engine in, a
  ``Renderer`` out, using the core's frame clock, capture loop, resolves and MP4
  sink (:mod:`an.media`).

>>> from contextlib import contextmanager
>>> class Blank:
...     name = "blank"
...     @contextmanager
...     def open(self, job):
...         yield self
...     def frame(self, t): return b""
...     def state(self, t): return {}
>>> describe(Blank()).drive, frame_stage_renderer(Blank()).name
('time', 'blank')
"""

from an.engines.capture import FrameStageError, capture_frames
from an.engines.frame_stage import (
    FrameStageRenderer,
    StateDrivenAdapter,
    frame_stage_renderer,
    require_engine,
    shot_workspace,
)
from an.engines.protocol import (
    DRIVE_STATE,
    DRIVE_TIME,
    FEATURE_MEMBERS,
    TIER_LIVE,
    TIER_SEEKABLE,
    Engine,
    EngineProfile,
    FrameJob,
    FrameRequest,
    LiveEngine,
    StateDriven,
    TimeDriven,
    UnseekableEngineError,
    describe,
    drive_mode,
    require_seekable,
    requests_as_dicts,
)

__all__ = [
    "DRIVE_STATE",
    "DRIVE_TIME",
    "FEATURE_MEMBERS",
    "TIER_LIVE",
    "TIER_SEEKABLE",
    "Engine",
    "EngineProfile",
    "FrameJob",
    "FrameRequest",
    "FrameStageError",
    "FrameStageRenderer",
    "LiveEngine",
    "StateDriven",
    "StateDrivenAdapter",
    "TimeDriven",
    "UnseekableEngineError",
    "capture_frames",
    "describe",
    "drive_mode",
    "frame_stage_renderer",
    "require_engine",
    "require_seekable",
    "requests_as_dicts",
    "shot_workspace",
]
