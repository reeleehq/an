"""``frame_stage_renderer(engine)``: any seekable engine becomes a ``Renderer``.

The core owns everything around the engine, once, for every engine:

1. the knobs, validated before anything launches -- ffmpeg present, the
   supersample factor (:func:`an.media.supersample.check_factor`), the pixel
   format (:func:`an.media.mp4.check_pix_fmt`), the engine's own knobs
   (``Engine.check``), and the frame clock (:func:`an.media.shutter.check_frame_samples`);
2. the clock: ``frame_count = max(1, round(duration * fps))``, frame ``i`` at
   ``i / fps`` unless ``RenderContext.frame_samples`` (built by
   :class:`an.frame_clock.FrameClock`) says otherwise;
3. the shot's workspace -- ``<work_dir>/shot_<id>/`` with a cleared ``frames/``;
4. the capture loop (:mod:`an.engines.capture`): supersampling and the shutter
   resolved in the frame stage;
5. the sink: the frames muxed to the shot mp4 with the pinned argv, the shot's
   dialogue laid under it (:func:`an.media.mp4.mux_shot`);
6. provenance: the core's facts plus the session's own (``provenance()``).

The engine only loads the shot and draws instants (:mod:`an.engines.protocol`).
A STATE-driven session is adapted here: the core evaluates its ``timeline`` with
:func:`an.timing.timeline.evaluate_timeline` (in the session's ``space`` when it
has one) and hands each state to ``render``.

Errors the core raises (:class:`~an.engines.capture.FrameStageError`,
:class:`~an.media.mp4.MediaError`, :class:`~an.engines.protocol.UnseekableEngineError`)
are re-raised as the renderer's own ``error`` type at its boundary, message
intact, so a cut-out render still fails with ``CutoutRenderError``.

>>> from contextlib import contextmanager
>>> class Card:
...     name = "card"
...     @contextmanager
...     def open(self, job):
...         yield self
...     def frame(self, t): return b""
...     def state(self, t): return {}
>>> r = frame_stage_renderer(Card(), renderers=("card", "title"))
>>> r.name, r.supported_renderers
('card', ('card', 'title'))
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from an.engines import capture as _capture
from an.engines.capture import FrameStageError
from an.engines.protocol import (
    DRIVE_STATE,
    Engine,
    FrameJob,
    FrameRequest,
    UnseekableEngineError,
    require_seekable,
)
from an.frame_clock import frame_count
from an.media.frames import frame_path
from an.media import mp4 as _mp4
from an.media.shutter import check_frame_samples
from an.media.supersample import check_factor

if TYPE_CHECKING:  # pragma: no cover - types only
    from an.adapters._base import RenderContext, RenderResult
    from an.ir.schema import Shot

__all__ = [
    "FrameStageRenderer",
    "SHOT_WORKSPACE_PATTERN",
    "StateDrivenAdapter",
    "frame_stage_renderer",
    "require_engine",
    "shot_workspace",
]

#: A shot's scratch directory under ``RenderContext.work_dir``. Kept from the
#: stage renderer it came from, so the paths a render leaves behind (and that
#: the bench and film assembly read) do not move.
SHOT_WORKSPACE_PATTERN: str = "shot_{shot_id}"
#: Inside the workspace: the frame directory and the per-shot mp4's name.
FRAMES_DIRNAME: str = "frames"

#: The provenance keys the CORE records about what it did. A session's
#: ``provenance()`` may add facts but never restate these: an engine claiming
#: another argv, pixel format or frame count than the frame stage used would
#: make the record lie about the file (the bench and the shot cache read them).
CORE_PROVENANCE_KEYS: frozenset[str] = frozenset(
    {
        "shot_id",
        "fps",
        "resolution",
        "supersample",
        "pix_fmt",
        "frame_count",
        "audio_tracks",
        "x264_args",
        "engine",
        "frame_samples",
    }
)

#: The errors the core raises about the RENDER, re-raised as the renderer's own
#: type. A bad knob (`SupersampleError`, `ShutterError`, both `ValueError`s) is
#: not a render failure and keeps its own type, as it always has.
CORE_ERRORS: tuple[type[BaseException], ...] = (
    FrameStageError,
    _mp4.MediaError,
    UnseekableEngineError,
)


def shot_workspace(work_dir: Path, shot_id: str) -> Path:
    """``<work_dir>/shot_<id>``: the one per-shot scratch directory."""
    return Path(work_dir) / SHOT_WORKSPACE_PATTERN.format(shot_id=shot_id)


def _fresh_frames_dir(workspace: Path) -> Path:
    """``<workspace>/frames``, emptied. Cleared, not reused: work dirs persist,
    and frames left by a longer earlier render of this shot would otherwise sit
    past this one's last frame -- in ``frame_manifest`` and in the mux's input."""
    frames = workspace / FRAMES_DIRNAME
    workspace.mkdir(parents=True, exist_ok=True)
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True, exist_ok=True)
    return frames


@dataclass
class StateDrivenAdapter:
    """A state-driven session seen as a time-driven one: the core evaluates ``at(t)``.

    ``frame(t)`` is ``render(evaluate_timeline(timeline, t, space=space))`` and
    ``state(t)`` is the evaluated state, so the capture loop and the conformance
    tests treat both drive modes alike. The session's other members (``resolve``,
    ``provenance``, ...) are reached through attribute access.
    """

    session: Any

    def state(self, t: float) -> Mapping[Any, Any]:
        from an.timing.timeline import evaluate_timeline

        return evaluate_timeline(
            self.session.timeline, t, space=getattr(self.session, "space", None)
        )

    def frame(self, t: float) -> bytes:
        return self.session.render(self.state(t))

    def __getattr__(self, name: str) -> Any:
        # Only for members the adapter does not define; `frames` (batching) is
        # not forwarded, because a state-driven batch would bypass `state`.
        if name == "frames":
            raise AttributeError(name)
        return getattr(self.session, name)


#: Slack when snapping an instant to the frame showing then: ``1.5`` s at 30 fps
#: is frame 45 even when ``1.5 * 30`` lands a hair under.
_FRAME_EPS: float = 1e-9


def film_frame(t: float, fps: float, total_frames: int) -> int:
    """The index of the film frame showing at ``t`` seconds into a shot.

    >>> film_frame(1.5, 30, 90), film_frame(0.0, 30, 90), film_frame(99, 30, 90)
    (45, 0, 89)
    """
    import math

    return min(
        max(total_frames - 1, 0), max(0, math.floor(t * float(fps) + _FRAME_EPS))
    )


@dataclass
class FrameStageRenderer:
    """A ``Renderer`` that drives an :class:`~an.engines.protocol.Engine` frame by frame.

    Build it with :func:`frame_stage_renderer`. Stateless across renders, so one
    instance serves every shot of a parallel render: each ``render`` opens its
    own session.
    """

    engine: Engine
    name: str = ""
    #: The ``Shot.renderer`` values this renderer claims (the ONE place it names them).
    supported_renderers: tuple[str, ...] = ()
    #: The exception type raised at the boundary for every core error.
    error: type[Exception] = FrameStageError
    #: Capture-loop tunables passed through to :func:`an.engines.capture.capture_frames`
    #: (``batch``, ``workers``, ``max_inflight``, ``batch_pixels``); unset = its defaults.
    capture_options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.engine.name
        if not self.supported_renderers:
            self.supported_renderers = (self.name,)

    def can_render(self, shot: "Shot") -> bool:
        return shot.renderer in self.supported_renderers

    def render(self, shot: "Shot", ctx: "RenderContext") -> "RenderResult":
        """Render ``shot`` to mp4 through the engine; see the module docstring."""
        try:
            return self._render(shot, ctx)
        except CORE_ERRORS as e:
            if isinstance(e, self.error):
                raise
            raise self.error(str(e)) from e

    def probe_frames(
        self, shot: "Shot", ctx: "RenderContext", times: "list[float]"
    ) -> list[bytes]:
        """The film's frames of ``shot`` showing at each of ``times`` (seconds), as PNG bytes.

        ``an probe`` (an#347): the session :meth:`render` opens (the same
        engine, state-driven adapter, supersample and frame clock) and the
        same :func:`~an.engines.capture.capture_frames`, asked only for the
        frames needed — so a probe frame IS the film's frame, without the
        rest of the shot or the mux. Each instant is snapped to the frame
        showing then (``floor(t * fps)``, clamped to the shot).
        """
        try:
            return self._probe(shot, ctx, list(times))
        except CORE_ERRORS as e:
            if isinstance(e, self.error):
                raise
            raise self.error(str(e)) from e

    def _probe(
        self, shot: "Shot", ctx: "RenderContext", times: list[float]
    ) -> list[bytes]:
        supersample = check_factor(ctx.supersample)
        check = getattr(self.engine, "check", None)
        if check is not None:
            check(ctx)
        total_frames = frame_count(shot.duration, ctx.fps)
        frame_samples = check_frame_samples(
            ctx.frame_samples, total_frames=total_frames, duration=shot.duration
        )
        workspace = shot_workspace(ctx.work_dir, shot.id)
        frames_dir = _fresh_frames_dir(workspace)
        job = FrameJob(
            shot=shot,
            ctx=ctx,
            workspace=workspace,
            frames_dir=frames_dir,
            total_frames=total_frames,
            supersample=supersample,
            frame_samples=frame_samples,
        )
        every = job.requests()
        film = [film_frame(t, ctx.fps, total_frames) for t in times]
        # Numbered 0..n-1: the capture loop checks for exactly that many files.
        requests = [FrameRequest(n, every[i].times) for n, i in enumerate(film)]
        with self.engine.open(job) as session:
            if require_seekable(session) == DRIVE_STATE:
                session = StateDrivenAdapter(session)
            _capture.capture_frames(
                session,
                requests,
                frames_dir,
                factor=supersample,
                size=job.size,
                **self.capture_options,
            )
        return [frame_path(frames_dir, n).read_bytes() for n in range(len(requests))]

    def _render(self, shot: "Shot", ctx: "RenderContext") -> "RenderResult":
        from an.adapters._base import RenderResult

        # Validated before anything launches: an engine load is seconds to
        # minutes, and these are microseconds.
        _mp4.ensure_ffmpeg()
        supersample = check_factor(ctx.supersample)
        pix_fmt = _mp4.check_pix_fmt(ctx.pix_fmt)
        check = getattr(self.engine, "check", None)
        if check is not None:
            check(ctx)
        total_frames = frame_count(shot.duration, ctx.fps)
        frame_samples = check_frame_samples(
            ctx.frame_samples, total_frames=total_frames, duration=shot.duration
        )

        workspace = shot_workspace(ctx.work_dir, shot.id)
        frames_dir = _fresh_frames_dir(workspace)
        job = FrameJob(
            shot=shot,
            ctx=ctx,
            workspace=workspace,
            frames_dir=frames_dir,
            total_frames=total_frames,
            supersample=supersample,
            frame_samples=frame_samples,
        )
        with self.engine.open(job) as session:
            if require_seekable(session) == DRIVE_STATE:
                session = StateDrivenAdapter(session)
            # A module attribute, read at call time: the bench's supersample
            # lever rebinds it (an.bench.mutations).
            _capture.capture_frames(
                session,
                job.requests(),
                frames_dir,
                factor=supersample,
                size=job.size,
                **self.capture_options,
            )
            session_provenance = dict(
                session.provenance()
                if callable(getattr(session, "provenance", None))
                else {}
            )
        clash = sorted(CORE_PROVENANCE_KEYS & set(session_provenance))
        if clash:
            raise FrameStageError(
                f"engine {self.engine.name!r} reports provenance keys the frame "
                f"stage owns: {clash}. Those record what the CORE did (argv, "
                "pixel format, frame count, ...); an engine adds its own facts "
                "under other names."
            )

        output_mp4 = workspace / f"{shot.id}.mp4"
        n_audio_tracks = _mp4.mux_shot(
            frames_dir,
            shot,
            ctx,
            workspace,
            output_mp4,
            n_frames=total_frames,
            pix_fmt=pix_fmt,
        )
        provenance: dict[str, Any] = {
            "shot_id": shot.id,
            "fps": ctx.fps,
            "resolution": ctx.resolution,
            # The DECLARED size, unchanged by supersampling: the frames on disk
            # are always this, because the resolve runs in the frame stage.
            "supersample": supersample,
            "pix_fmt": pix_fmt,
            "frame_count": total_frames,
            "audio_tracks": n_audio_tracks,
            # Read at call time: the `high_crf` lever rebinds it.
            "x264_args": list(_mp4.DETERMINISTIC_X264_ARGS),
            **session_provenance,
            "engine": self.engine.name,
            # Present only when a frame clock was supplied, so an ordinary
            # render's provenance is unchanged. The instants verbatim: a
            # blurred or jittered frame is only interpretable beside them.
            **(
                {"frame_samples": [list(f) for f in frame_samples]}
                if frame_samples is not None
                else {}
            ),
        }
        return RenderResult(
            mp4_path=output_mp4,
            duration=shot.duration,
            frame_manifest=sorted(frames_dir.glob("*.png")),
            log="",
            provenance=provenance,
        )


def frame_stage_renderer(
    engine: Engine,
    *,
    name: str | None = None,
    renderers: tuple[str, ...] | None = None,
    error: type[Exception] = FrameStageError,
    capture_options: Mapping[str, Any] | None = None,
) -> FrameStageRenderer:
    """Turn ``engine`` into a ``Renderer``: the core's clock, capture loop, resolves and sinks.

    ``name`` defaults to the engine's; ``renderers`` -- the ``Shot.renderer``
    values claimed -- default to ``(name,)``. ``error`` is the typed exception
    the renderer raises at its boundary for every core error.
    """
    require_engine(engine)
    return FrameStageRenderer(
        engine,
        name=name or engine.name,
        supported_renderers=tuple(renderers or ()),
        error=error,
        capture_options=dict(capture_options or {}),
    )


def require_engine(engine: Any) -> None:
    """Refuse an object that is not an engine, saying what is missing.

    >>> require_engine(object())
    Traceback (most recent call last):
      ...
    TypeError: an Engine needs `name` and `open(job)`; object lacks: name, open
    """
    missing = [m for m in ("name", "open") if not hasattr(engine, m)]
    if missing:
        raise TypeError(
            "an Engine needs `name` and `open(job)`; "
            f"{type(engine).__name__} lacks: {', '.join(missing)}"
        )
