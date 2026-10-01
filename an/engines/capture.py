"""The capture loop: drive a session through every frame, resolve, write -- for ANY engine.

Moved out of the stage renderer (``an/adapters/cutout/render.py``'s
``_capture_frames`` and ``_capture_frames_canvas``, an#247) and generalised over
the session members of :mod:`an.engines.protocol`. The algorithms are the ones
the stage shipped, unchanged, because the decoded frames are the contract (the
golden corpus and the canvas equivalence gate compare them):

- **Sequential** (a session without ``frames``): per frame, ``frame(t)`` for each
  instant; a frame of ONE instant at supersample 1 with no ``resolve`` member is
  written as the engine's own bytes -- nothing decoded, so **off is free** --
  and anything else goes through the resolve.
- **Batched** (a session with ``frames(requests)``): the requests go out in frame
  order, samples in the order given, at most ``batch`` frames and
  ``batch_pixels`` captured pixels per round trip (a frame whose instants alone
  exceed it is split over round trips and resolved once); the resolve runs on a
  small thread pool while the engine draws the next batch, with BACK-PRESSURE --
  at most ``max_inflight`` frames (and twice the pixel budget) wait on the pool,
  after which the loop blocks on the oldest before asking for more.

**The resolve runs here, in the frame stage, before a file is written**:
supersampling (:mod:`an.media.supersample`, an exact block mean) and the open
shutter (:mod:`an.media.shutter`, an exact temporal mean). Nothing downstream
reads a resolution off a file or averages anything; an ffmpeg ``-vf scale`` is
refused for the reasons in ``an-dev-render-pipeline`` §2. A session's own
``resolve`` member replaces the default resolve (the stage's canvas session
refuses non-opaque pixels there); the default is
:func:`an.media.shutter.mean_png_bytes`.

Two corruptions are silent unless refused, so both are refused: a dropped or
reordered frame (every file is named by its frame number, and every frame
``0..N-1`` must exist on disk before the loop returns), and unbounded buffering
(the bounds above).

**The bench's ``supersample`` lever rebinds** :func:`capture_frames` **on this
module** to force the product's own factor, so :mod:`an.engines.frame_stage`
calls it as a module attribute, at call time.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from an.engines.protocol import FrameRequest
from an.media.frames import frame_path, missing_frames
from an.media.shutter import mean_png_bytes
from an.media.supersample import NO_SUPERSAMPLE

__all__ = [
    "DEFAULT_BATCH",
    "DEFAULT_BATCH_PIXELS",
    "DEFAULT_ENCODE_WORKERS",
    "DEFAULT_MAX_INFLIGHT",
    "FrameStageError",
    "capture_frames",
    "default_resolve",
]

#: Frames per round trip of a batched session. Measured on the stage at
#: 1920x1080 on an M1 Max: 67 ms/frame one frame per call, 46 at four, 46 at
#: eight -- the round trip is ~20 ms of fixed cost, amortised by the batch.
DEFAULT_BATCH: int = 8

#: Threads resolving and encoding frames while the engine draws the next batch.
#: The stage's decode/encode is ~60 ms/frame of Pillow at 1080p, the same order
#: as the page's own work, so it must overlap it. Two, not `cpu_count()`: a
#: parallel render already runs one engine per shot.
DEFAULT_ENCODE_WORKERS: int = 2

#: The same two bounds in CAPTURED PIXELS (backbuffer pixels: a supersample
#: counts k² times, an open shutter once per instant): at most this many per
#: round trip, twice this many waiting on the pool. A frame COUNT bounds nothing
#: when a frame is a k-times, many-sample, incompressible canvas (an#192 review:
#: one reply overflowed the driver's string limit and the render hung).
DEFAULT_BATCH_PIXELS: int = 2 * 1920 * 1080

#: BACK-PRESSURE: frames handed to the pool and not yet written.
DEFAULT_MAX_INFLIGHT: int = 2 * DEFAULT_BATCH

Resolve = Callable[..., bytes]


class FrameStageError(RuntimeError):
    """The frame stage could not produce a frame directory it can vouch for.

    A renderer built by ``frame_stage_renderer(..., error=...)`` re-raises it as
    its own typed error at its boundary.
    """


def default_resolve(
    samples: Sequence[bytes], *, frame: int, factor: int, size: tuple[int, int] | None
) -> bytes:
    """The core's resolve: spatially by ``factor``, then the instants in time.

    One sample at factor 1 is returned as is -- the engine's own bytes.
    """
    return mean_png_bytes(samples, factor=factor)


def capture_frames(
    session: Any,
    requests: Sequence[FrameRequest],
    frames_dir: Path,
    *,
    factor: int = NO_SUPERSAMPLE,
    size: tuple[int, int] | None = None,
    batch: int | None = None,
    workers: int | None = None,
    max_inflight: int | None = None,
    batch_pixels: int | None = None,
) -> None:
    """Write one PNG per request into ``frames_dir``, resolved to the declared size.

    ``session`` is time-driven (``frame(t)``), optionally batched
    (``frames(requests)``), optionally with its own ``resolve``. A state-driven
    session is adapted by the frame stage before it reaches here. ``size``, when
    known, sets the pixel budget and is passed to the resolve. ``None`` for any
    tunable reads the module default at call time.
    """
    resolve: Resolve = getattr(session, "resolve", None) or default_resolve
    if callable(getattr(session, "frames", None)):
        _capture_batched(
            session,
            requests,
            frames_dir,
            resolve,
            factor=factor,
            size=size,
            batch=batch or DEFAULT_BATCH,
            workers=workers or DEFAULT_ENCODE_WORKERS,
            max_inflight=max(1, max_inflight or DEFAULT_MAX_INFLIGHT),
            budget=batch_pixels or DEFAULT_BATCH_PIXELS,
        )
    else:
        _capture_sequential(session, requests, frames_dir, resolve, factor=factor, size=size)
    if frames_dir is not None:
        missing = missing_frames(frames_dir, len(requests))
        if missing:
            raise FrameStageError(
                f"frame capture finished with frames {missing[:5]} missing from "
                f"{frames_dir} ({len(requests) - len(missing)} of {len(requests)} "
                "written); a dropped frame is silent corruption, so this refuses "
                "rather than muxing it"
            )


def _capture_sequential(
    session: Any,
    requests: Sequence[FrameRequest],
    frames_dir: Path,
    resolve: Resolve,
    *,
    factor: int,
    size: tuple[int, int] | None,
) -> None:
    free = resolve is default_resolve and factor == NO_SUPERSAMPLE
    for req in requests:
        out = frame_path(frames_dir, req.frame)
        if free and len(req.times) == 1:
            # The engine's own bytes reach disk: nothing decoded, nothing re-encoded.
            out.write_bytes(session.frame(req.times[0]))
            continue
        samples = [session.frame(t) for t in req.times]
        out.write_bytes(resolve(samples, frame=req.frame, factor=factor, size=size))


def _capture_batched(
    session: Any,
    requests: Sequence[FrameRequest],
    frames_dir: Path,
    resolve: Resolve,
    *,
    factor: int,
    size: tuple[int, int] | None,
    batch: int,
    workers: int,
    max_inflight: int,
    budget: int,
) -> None:
    # Backbuffer pixels per captured instant; 0 (unknown) disables the pixel
    # bounds and leaves the frame counts in charge.
    per_instant = size[0] * size[1] * factor * factor if size else 0

    def _encode(i: int, pngs: list[bytes]) -> int:
        frame_path(frames_dir, i).write_bytes(
            resolve(pngs, frame=i, factor=factor, size=size)
        )
        return i

    def _round_trips() -> Iterator[list[tuple[FrameRequest, bool]]]:
        """Requests grouped into round trips, each ``(request, frame_done)``.
        A frame's instants are split only when they alone exceed the budget,
        so the parts of one frame never share a round trip."""
        per_part = max(1, budget // per_instant) if per_instant else None
        trip: list[tuple[FrameRequest, bool]] = []
        trip_pixels = 0
        for req in requests:
            times = req.times
            step = per_part or len(times)
            for j in range(0, len(times), step):
                part = tuple(times[j : j + step])
                pixels = len(part) * per_instant
                if trip and (
                    len(trip) >= batch
                    or (per_instant and trip_pixels + pixels > budget)
                ):
                    yield trip
                    trip, trip_pixels = [], 0
                trip.append((FrameRequest(req.frame, part), j + step >= len(times)))
                trip_pixels += pixels
        if trip:
            yield trip

    written: list[int] = []
    inflight: deque = deque()  # (future, pixels)
    inflight_pixels = 0
    pending: list[bytes] = []  # the samples of a frame split across round trips
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="an-frames") as pool:
        try:
            for trip in _round_trips():
                asked = [req for req, _ in trip]
                reply = list(session.frames(asked))
                if len(reply) != len(asked):
                    raise FrameStageError(
                        f"the engine returned {len(reply)} frame(s) for a request "
                        f"of {len(asked)}; a dropped frame is silent corruption"
                    )
                for req, pngs, (_, done) in zip(asked, reply, trip):
                    if len(pngs) != len(req.times):
                        raise FrameStageError(
                            f"frame {req.frame}: the engine returned {len(pngs)} "
                            f"sample(s) for {len(req.times)} instant(s)"
                        )
                    pending.extend(pngs)
                    if not done:
                        continue
                    pixels = len(pending) * per_instant
                    while inflight and (
                        len(inflight) >= max_inflight
                        or (per_instant and inflight_pixels + pixels > 2 * budget)
                    ):
                        fut, done_pixels = inflight.popleft()
                        written.append(fut.result())
                        inflight_pixels -= done_pixels
                    inflight.append((pool.submit(_encode, req.frame, pending), pixels))
                    inflight_pixels += pixels
                    pending = []
            while inflight:
                written.append(inflight.popleft()[0].result())
        finally:
            # A failure anywhere must not leave encodes running against a
            # frames directory the caller is about to treat as finished.
            for fut, _ in inflight:
                fut.cancel()
    expected = [r.frame for r in requests]
    if written != expected:
        raise FrameStageError(
            f"frame capture wrote frames {written[:5]}... for a request of "
            f"{expected[:5]}...; a dropped or reordered frame is silent corruption"
        )
