"""The ``Engine`` protocol: a seekable thing that turns a time, or a state, into a frame.

The second of the three renderer tiers (ADR 0001 decision 12; core study §2.7):

1. ``Renderer`` (``an.adapters._base``) -- shot in, media file out. Every back-end
   is reachable through it; Manim lives there, whole-shot.
2. **``Engine``** (this module) -- ``previz``'s meaning of the word: something
   that can show the scene at any instant and hand over the pixels. The core
   turns any engine into a ``Renderer`` with :func:`an.engines.frame_stage_renderer`,
   which owns the clock, the capture loop, supersampling, the shutter and the
   sinks, so an engine implements none of them.
3. ``LiveEngine`` -- apply, settle, capture in real time (``walkthru``'s recorder).
   **Declared, not built.**

**Capabilities are read from which members exist, never from a flag**
(``previz``'s rule, ADR 0002 applied to engines), so a flag can never disagree
with the code. :func:`describe` is the one place that reads them.

An ``Engine`` is a stateless factory, safe to share across the threads of a
parallel render. :meth:`Engine.open` loads one shot and yields a **session**:
the loaded, seekable view, whose members say what it can do.

=====================  =====================================================  ==============
session member         unlocks                                                  feature
=====================  =====================================================  ==============
``frame(t)``           TIME-DRIVEN: the engine evaluates the compiled           drive ``time``
                       channels itself (``runtime.js``) and draws ``t``
``state(t)``           read-back of the state a time-driven engine evaluated;   ``readback``
                       what conformance against the kernel's golden vectors
                       (``an/data/timing/timing_vectors.json``) is tested on
``timeline`` +         STATE-DRIVEN: the core evaluates ``at(t)``               drive ``state``
``render(state)``      (:func:`an.timing.timeline.evaluate_timeline`, in the
                       session's ``space`` when it has one) and the engine
                       draws the state it is handed (``previz``, ``burns``)
``frames(requests)``   several instants per round trip, in order                 ``batch``
``render_states(       a STATE-driven session's batch: several evaluated states  ``batch``
states)``              per round trip (an#286); the core evaluates them
``resolve(samples,     the engine's own normalisation of its raw frames (e.g.    ``resolve``
...)``                 refusing a non-opaque RGBA canvas); without it, the
                       core's resolve, which passes a lone frame through
                       untouched at supersample 1
``bounds(t)``          node rectangles, for the layout verifier                  ``bounds``
``project(point, t)``  screen position of a world point, for anchored overlays   ``project``
``frame_with_alpha(t)``  a frame with a transparent background                   ``alpha``
``provenance()``       the engine's own facts for the shot's provenance          ``provenance``
=====================  =====================================================  ==============

And on the ``Engine`` itself: ``check(ctx)`` validates the engine's own knobs
before anything launches (a typo must fail in microseconds, not after a browser
started).

>>> class _Still:
...     def frame(self, t): return b"png"
...     def state(self, t): return {}
>>> describe(_Still())
EngineProfile(tier='seekable', drive='time', features=frozenset({'readback'}))
>>> class _Crop:
...     timeline = None
...     def render(self, state): return b"png"
>>> describe(_Crop()).drive
'state'
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - types only
    from an.adapters._base import RenderContext
    from an.ir.schema import Shot

__all__ = [
    "DRIVE_STATE",
    "DRIVE_TIME",
    "Engine",
    "EngineProfile",
    "FEATURE_MEMBERS",
    "FrameJob",
    "FrameRequest",
    "LiveEngine",
    "StateDriven",
    "TIER_LIVE",
    "TIER_SEEKABLE",
    "TimeDriven",
    "UnseekableEngineError",
    "describe",
    "drive_mode",
    "require_seekable",
    "requests_as_dicts",
]

#: Drive modes (core study §2.7): who evaluates the timeline.
DRIVE_TIME: str = "time"
DRIVE_STATE: str = "state"

#: Tiers an engine can be on (the ``Renderer`` tier is not an engine).
TIER_SEEKABLE: str = "seekable"
TIER_LIVE: str = "live"

#: Optional session member -> the feature it unlocks. The SSOT :func:`describe`
#: reads; a new feature is a new row, never a flag on an engine.
FEATURE_MEMBERS: dict[str, str] = {
    "state": "readback",
    "frames": "batch",
    # A state-driven session's batch (an#286): the states of a round trip at once.
    "render_states": "batch",
    "resolve": "resolve",
    "bounds": "bounds",
    "project": "project",
    "frame_with_alpha": "alpha",
    "provenance": "provenance",
}


class UnseekableEngineError(TypeError):
    """A session that the frame stage cannot drive; the message says what to add."""


@dataclass(frozen=True, slots=True)
class FrameRequest:
    """One output frame's instants, in the order they must be captured.

    One instant unless a frame clock opened the shutter
    (``RenderContext.frame_samples``).
    """

    frame: int
    times: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class FrameJob:
    """What the frame stage asks of an engine for one shot.

    Built by the core, before :meth:`Engine.open`: every knob here is already
    validated, so an engine never re-derives the frame count or the factor.
    """

    shot: "Shot"
    ctx: "RenderContext"
    #: The shot's own scratch directory (``<work_dir>/shot_<id>``). The engine
    #: may stage files in it (the stage engine's runtime copy); the core owns
    #: ``frames/`` and the delivered mp4 inside it.
    workspace: Path
    frames_dir: Path
    total_frames: int
    #: The validated supersample factor: the engine draws at ``k`` times the
    #: declared size, and the core resolves back to it.
    supersample: int
    #: Per frame, the instants to capture and average, or ``None`` for one
    #: instant at ``i / fps``.
    frame_samples: tuple[tuple[float, ...], ...] | None = None

    @property
    def size(self) -> tuple[int, int]:
        """The DECLARED (width, height): what every resolved frame must be."""
        return (int(self.ctx.resolution[0]), int(self.ctx.resolution[1]))

    def requests(self) -> tuple[FrameRequest, ...]:
        """Every frame's request, frame ``i`` at ``i / fps`` unless a clock says otherwise.

        >>> from types import SimpleNamespace
        >>> job = FrameJob(None, SimpleNamespace(fps=4, resolution=(2, 2)), Path("."),
        ...                Path("."), total_frames=3, supersample=1)
        >>> [r.times for r in job.requests()]
        [(0.0,), (0.25,), (0.5,)]
        """
        if self.frame_samples is None:
            fps = float(self.ctx.fps)
            return tuple(FrameRequest(i, (i / fps,)) for i in range(self.total_frames))
        return tuple(
            FrameRequest(i, tuple(times)) for i, times in enumerate(self.frame_samples)
        )


@runtime_checkable
class Engine(Protocol):
    """A stateless factory of loaded, seekable sessions -- one per shot render."""

    #: The engine's name (``"stage"``); also how provenance names it.
    name: str

    def open(self, job: FrameJob) -> AbstractContextManager[Any]:
        """Load ``job.shot`` and yield a session (see the module table)."""


@runtime_checkable
class TimeDriven(Protocol):
    """A session that evaluates the compiled channels itself."""

    def frame(self, t: float) -> bytes:
        """The scene at ``t`` as PNG bytes (``supersample`` times the declared size)."""

    def state(self, t: float) -> Mapping[Any, Any]:
        """The state the engine evaluated at ``t``: a sparse pose, absent = at rest."""


@runtime_checkable
class StateDriven(Protocol):
    """A session the core hands states to."""

    #: The ``an.timing`` ``Timeline`` the core evaluates.
    timeline: Any

    def render(self, state: Mapping[Any, Any]) -> bytes:
        """PNG bytes of ``state`` (``supersample`` times the declared size)."""


@runtime_checkable
class LiveEngine(Protocol):
    """The live tier: apply, settle, capture in real time. **Declared, not built.**

    Its recorder resamples to a constant rate (``walkthru``'s worked example);
    ``frame_stage_renderer`` does not drive it, and never falls back to it.
    """

    def apply(self, state: Mapping[Any, Any]) -> None: ...

    def settle(self) -> None: ...

    def capture(self) -> bytes: ...


@dataclass(frozen=True, slots=True)
class EngineProfile:
    """What a session can do, read off its members."""

    tier: str | None
    drive: str | None
    features: frozenset[str]


def _has(obj: Any, member: str) -> bool:
    return getattr(obj, member, None) is not None


def drive_mode(session: Any) -> str | None:
    """``"time"``, ``"state"``, or ``None`` for a session the frame stage cannot drive.

    A session with both ``frame`` and ``render`` is time-driven: it evaluates
    its own document, and the core does not second-guess it.
    """
    if callable(getattr(session, "frame", None)):
        return DRIVE_TIME
    # `timeline` is a data member: its presence is the declaration (a session
    # class may leave it unset until `open` fills it).
    if callable(getattr(session, "render", None)) and hasattr(session, "timeline"):
        return DRIVE_STATE
    return None


def describe(session: Any) -> EngineProfile:
    """The tier, drive mode and features a session (or a session class) offers."""
    drive = drive_mode(session)
    if drive is not None:
        tier = TIER_SEEKABLE
    elif all(
        callable(getattr(session, m, None)) for m in ("apply", "settle", "capture")
    ):
        tier = TIER_LIVE
    else:
        tier = None
    features = frozenset(
        feature for member, feature in FEATURE_MEMBERS.items() if _has(session, member)
    )
    return EngineProfile(tier=tier, drive=drive, features=features)


def require_seekable(session: Any) -> str:
    """The session's drive mode, or a refusal that says what to add.

    >>> require_seekable(object())
    Traceback (most recent call last):
      ...
    an.engines.protocol.UnseekableEngineError: this engine session cannot be captured: it has no frame(t) (time-driven), and no render(state) with a timeline (state-driven). Add frame(t) and state(t) if the engine evaluates the timeline itself, or timeline and render(state) if the core should evaluate it.
    """
    drive = drive_mode(session)
    if drive is not None:
        return drive
    live = describe(session).tier == TIER_LIVE
    raise UnseekableEngineError(
        "this engine session cannot be captured: it has no frame(t) "
        "(time-driven), and no render(state) with a timeline (state-driven). "
        + (
            "It is a live engine (apply/settle/capture), and the live tier is "
            "declared, not built: the frame stage never falls back to real-time "
            "capture. "
            if live
            else ""
        )
        + "Add frame(t) and state(t) if the engine evaluates the timeline "
        "itself, or timeline and render(state) if the core should evaluate it."
    )


def requests_as_dicts(requests: Sequence[FrameRequest]) -> list[dict[str, Any]]:
    """Requests as plain dicts, the shape a page or a subprocess takes."""
    return [{"frame": r.frame, "times": list(r.times)} for r in requests]
