"""Film assembly: rendered shots → one film, with transitions and a sound layer.

Every shot renders in isolation (`an.render`); this module decides how the
shots meet and what is heard over them. It runs only when a scene asks for it
— a non-``cut`` :class:`~an.ir.schema.Transition` or any
:class:`~an.ir.schema.SoundCue` — so a scene with neither takes the old
``_ffmpeg_concat`` path, byte for byte (:func:`needs_assembly`).

**Where each part happens, and why there.**

- *Picture*: transitions are composed in the FRAME STAGE, on the per-shot PNGs,
  in exact integer arithmetic, and encoded by the same
  ``an.media.mp4.mux_frames`` every shot uses. Composing in ffmpeg (``xfade``)
  would decode already-encoded shots and re-encode them — a second generation
  of x264 loss on every frame of the film, not just the transition — and would
  retire the render pipeline's "ffmpeg never touches a frame" clause.
- *The picture is a stream-copy concat of SEGMENTS* (an#260), each encoded
  once from PNGs: a shot no transition touches is its own mp4's video stream,
  copied; a shot a transition touches contributes the encoded span between its
  windows (its *body*) plus the PNGs inside them; each run of composed frames
  is encoded on its own. So a reused shot needs its mp4 (and, at a transition,
  its body and window PNGs, a few dozen frames) — never every frame it has
  (:func:`shot_windows`, :class:`ShotParts`). The film's frame ``i`` is at
  ``i / fps`` and decodes to exactly what its segment decodes to (measured,
  an#260; :data:`MIN_SEGMENT_FRAMES` is why no segment is shorter than three).
- *Sound*: the film's audio is rebuilt from SOURCES — every dialogue line's
  cached WAV and every cue's asset, placed in film time — in one ffmpeg mix,
  then muxed onto the picture with ``-c:v copy``. Mixing onto the shots'
  already-encoded AAC would be a second audio generation for the dialogue.

**The timeline is frame-exact.** Shot ``i`` occupies ``frame_count(duration,
fps)`` frames (the renderer's own rule) starting at film frame
:attr:`FilmTimeline.starts` ``[i]``; audio is placed at ``start / fps`` plus
its shot-local time, so a line stays on the frames it was lip-synced to
whatever the transitions do.

>>> from an.ir.schema import Shot, Transition
>>> tl = film_timeline(
...     [Shot(id="a", duration=2.0),
...      Shot(id="b", duration=2.0, transition=Transition(kind="dissolve", duration=0.5))],
...     fps=10,
... )
>>> tl.starts, tl.total_frames   # b starts 5 frames early: the film is 0.5 s shorter
((0, 15), 35)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from an.base import (
    FILM_AUDIO_BITRATE,
    FILM_AUDIO_CHANNELS,
    FILM_AUDIO_SAMPLE_RATE,
    MP4_FASTSTART_ARGS,
)
from an.frame_clock import frame_count
from an.ir.schema import SceneIR, Shot, SoundCue

__all__ = [
    "MIN_SEGMENT_FRAMES",
    "AssemblyError",
    "FilmTimeline",
    "Segment",
    "ShotParts",
    "ShotWindow",
    "assemble_film",
    "duck_gain",
    "film_duration",
    "film_timeline",
    "needs_assembly",
    "picture_segments",
    "shot_parts",
    "shot_windows",
    "transition_problems",
    "write_film_frames",
]


#: The ducking gain is re-evaluated every this many samples (10 ms at
#: 44.1 kHz): fine enough that a 80 ms attack is a ramp, not a step.
DUCK_FRAME_SAMPLES: int = 441

#: Dialogue spans per ducking expression. ffmpeg 9.0.1 refuses one nested
#: expression at about 95 spans (a sum of terms fails at 100 too); well under.
DUCK_SPANS_PER_EXPRESSION: int = 40

#: The fewest frames a segment of a MULTI-segment picture may have. Measured on
#: ffmpeg 9.0.1 / libx264 with the pinned argv (an#260): a stream of three or
#: more frames carries a two-frame B-pyramid decode delay (its first DTS is two
#: frames before its first PTS) whatever its content, and a stream of one or
#: two frames carries none. The concat demuxer offsets every file alike, so a
#: delay-free segment between two delayed ones leaves the DTS going backwards;
#: the muxer patches that with one-tick packets, and a constant-rate decode of
#: the film then shows a frame twice. :func:`shot_windows` widens every short
#: run instead, so each segment of a multi-segment picture has the delay.
MIN_SEGMENT_FRAMES: int = 3


class AssemblyError(RuntimeError):
    """The shots cannot be assembled as the scene asks. Carries the fix."""


# -----------------------------------------------------------------------------
# The timeline — pure, and the one statement of where every shot lands.
# -----------------------------------------------------------------------------


def _transition_frame_count(shot: Shot, fps: float) -> int:
    """Frames ``shot``'s incoming transition spans; 0 for a cut, or for one so
    short it rounds to nothing — which IS a cut, and must cost like one."""
    t = shot.transition
    if t is None or t.kind == "cut":
        return 0
    return int(round(t.duration * fps))


def needs_assembly(scene: SceneIR, *, fps: float | None = None) -> bool:
    """True when the scene asks for anything beyond hard cuts and shot audio.

    Decided on FRAMES at the render's rate (``fps``, default the scene's): a
    transition that rounds to zero frames asks for nothing, and must not cost a
    scene its byte-identical concat.

    >>> from an.ir.schema import Meta, SceneIR, Shot, Transition
    >>> needs_assembly(SceneIR(timeline=[Shot(id="a"), Shot(id="b")]))
    False
    >>> needs_assembly(SceneIR(timeline=[
    ...     Shot(id="a"), Shot(id="b", transition=Transition(kind="fade", duration=0.0))]))
    False
    """
    if scene.meta.sounds or any(shot.sounds for shot in scene.timeline):
        return True
    rate = fps if fps is not None else scene.meta.fps
    return any(_transition_frame_count(shot, rate) for shot in scene.timeline)


def film_duration(scene: SceneIR, *, fps: float | None = None) -> float:
    """Seconds the delivered film runs: the shots' durations, minus each
    dissolve's overlap. Exactly ``sum(durations)`` for a scene without one, so
    every existing document's arithmetic is unchanged.

    >>> from an.ir.schema import SceneIR, Shot, Transition
    >>> film_duration(SceneIR(timeline=[Shot(id="a", duration=2.0),
    ...     Shot(id="b", duration=2.0, transition=Transition(kind="dissolve", duration=0.5))]))
    3.5
    """
    rate = fps if fps is not None else scene.meta.fps
    total = sum(s.duration for s in scene.timeline)
    for shot in scene.timeline[1:]:
        if shot.transition is not None and shot.transition.kind == "dissolve":
            total -= _transition_frame_count(shot, rate) / rate
    return total


@dataclass(frozen=True)
class FilmTimeline:
    """Where each shot's frames land in the film, and what blends them.

    ``dissolve_in[i]`` — frames shot ``i`` overlaps the previous shot by.
    ``fade_in[i]`` — frames at shot ``i``'s head that fade up from a colour.
    ``fade_out[i]`` — frames at shot ``i``'s tail that fade to a colour (the
    NEXT shot's fade colour).
    """

    fps: float
    frames: tuple[int, ...]
    starts: tuple[int, ...]
    dissolve_in: tuple[int, ...]
    fade_in: tuple[int, ...]
    fade_out: tuple[int, ...]
    fade_in_color: tuple[str | None, ...]
    fade_out_color: tuple[str | None, ...]
    total_frames: int

    @property
    def duration(self) -> float:
        return self.total_frames / self.fps

    def start_seconds(self, i: int) -> float:
        """Film time of shot ``i``'s first frame."""
        return self.starts[i] / self.fps

    def end_seconds(self, i: int) -> float:
        """Film time just after shot ``i``'s last frame."""
        return (self.starts[i] + self.frames[i]) / self.fps

    @property
    def has_transitions(self) -> bool:
        return any(self.dissolve_in) or any(self.fade_in) or any(self.fade_out)


def _transition_frames(shots: Sequence[Shot], fps: float):
    """Per shot: (frames, dissolve_in, fade_in, fade_out, in_colour, out_colour)."""
    n = len(shots)
    frames = [frame_count(s.duration, fps) for s in shots]
    dissolve_in, fade_in, fade_out = [0] * n, [0] * n, [0] * n
    in_color: list[str | None] = [None] * n
    out_color: list[str | None] = [None] * n
    for i, shot in enumerate(shots):
        t = shot.transition
        k = _transition_frame_count(shot, fps)
        if not k:
            continue
        if t.kind == "dissolve":
            dissolve_in[i] = k
        elif i == 0:  # a fade on the first shot is a fade up from the colour
            fade_in[i], in_color[i] = k, t.color
        else:  # half out of the previous shot, half into this one
            fade_out[i - 1], out_color[i - 1] = k // 2, t.color
            fade_in[i], in_color[i] = k - k // 2, t.color
    return frames, dissolve_in, fade_in, fade_out, in_color, out_color


def transition_problems(shots: Sequence[Shot], fps: float) -> list[tuple[int, str]]:
    """Every reason these shots' transitions cannot be assembled, as
    ``(shot index, message)``. The ONE list `an validate` reports and
    :func:`film_timeline` raises on, so the two cannot disagree.

    >>> from an.ir.schema import Shot, Transition
    >>> transition_problems([Shot(id="a", transition=Transition(kind="dissolve"))], fps=30)
    [(0, "shot 'a' is the first shot, so a dissolve has nothing to dissolve from; use a fade (from a colour) or a cut")]
    """
    frames, dissolve_in, fade_in, fade_out, _, _ = _transition_frames(shots, fps)
    problems: list[tuple[int, str]] = []
    for i, shot in enumerate(shots):
        if i == 0 and dissolve_in[0]:
            problems.append(
                (
                    0,
                    f"shot {shot.id!r} is the first shot, so a dissolve has nothing "
                    "to dissolve from; use a fade (from a colour) or a cut",
                )
            )
        # The head of shot i is used by its own incoming transition; the tail by
        # the NEXT shot's. A frame may belong to only one of them — a frame in
        # two blends at once has no single rule, so it is refused, not guessed.
        head = dissolve_in[i] + fade_in[i]
        tail = fade_out[i] + (dissolve_in[i + 1] if i + 1 < len(shots) else 0)
        if head + tail > frames[i]:
            problems.append(
                (
                    i,
                    f"shot {shot.id!r} is {frames[i]} frames long but its transitions "
                    f"need {head} at its head and {tail} at its tail; shorten a "
                    "transition or lengthen the shot",
                )
            )
    return problems


def film_timeline(shots: Sequence[Shot], *, fps: float) -> FilmTimeline:
    """Lay ``shots`` end to end, overlapping each dissolve. Raises
    :class:`AssemblyError` on any :func:`transition_problems`."""
    problems = transition_problems(shots, fps)
    if problems:
        raise AssemblyError("; ".join(msg for _, msg in problems))
    frames, dissolve_in, fade_in, fade_out, in_color, out_color = _transition_frames(
        shots, fps
    )
    starts: list[int] = []
    cursor = 0
    for i, n in enumerate(frames):
        cursor -= dissolve_in[i]
        starts.append(cursor)
        cursor += n
    return FilmTimeline(
        fps=fps,
        frames=tuple(frames),
        starts=tuple(starts),
        dissolve_in=tuple(dissolve_in),
        fade_in=tuple(fade_in),
        fade_out=tuple(fade_out),
        fade_in_color=tuple(in_color),
        fade_out_color=tuple(out_color),
        total_frames=cursor,
    )


# -----------------------------------------------------------------------------
# Picture: the frame-stage composer.
# -----------------------------------------------------------------------------


def _hex_rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def blend(a: Any, b: Any, num: int, den: int) -> Any:
    """``a`` moved ``num/den`` of the way to ``b``, per channel, exactly.

    Integer arithmetic rounded half-to-even — the rule the supersample and
    shutter resolves spell out — so a transition frame is a pure function of
    its two inputs on every machine.

    >>> import numpy as np
    >>> a, b = np.zeros((1, 1, 3), np.uint8), np.full((1, 1, 3), 255, np.uint8)
    >>> blend(a, b, 1, 2)[0, 0].tolist()   # 127.5 -> 128 (even)
    [128, 128, 128]
    >>> blend(a, b, 0, 3) is a, blend(a, b, 3, 3) is b
    (True, True)
    """
    import numpy as np

    if num == 0:
        return a
    if num == den:
        return b
    total = a.astype(np.uint32) * (den - num) + b.astype(np.uint32) * num
    quotient, remainder = np.divmod(total, den)
    twice = 2 * remainder
    tie_to_even = (twice == den) & (quotient % 2 == 1)
    return (quotient + ((twice > den) | tie_to_even)).astype(np.uint8)


def _frame_sources(timeline: FilmTimeline) -> list[list[tuple[int, int]]]:
    """Per film frame, the ``(shot, local frame)`` pairs that make it."""
    sources: list[list[tuple[int, int]]] = [[] for _ in range(timeline.total_frames)]
    for i, (start, n) in enumerate(zip(timeline.starts, timeline.frames)):
        for j in range(n):
            sources[start + j].append((i, j))
    return sources


def _colour_weight(
    timeline: FilmTimeline, i: int, j: int
) -> tuple[int, int, str | None]:
    """``(num, den, colour)``: how far frame ``j`` of shot ``i`` is faded.

    Head frames go ``m/m, (m-1)/m, … 1/m`` of colour — the first frame of a
    faded-in shot IS the colour, so a fade through black reaches black on
    exactly one frame. Tail frames go ``1/(h+1) … h/(h+1)`` and never reach it.
    """
    m = timeline.fade_in[i]
    if j < m:
        return m - j, m, timeline.fade_in_color[i]
    h = timeline.fade_out[i]
    tail = j - (timeline.frames[i] - h)
    if h and tail >= 0:
        return tail + 1, h + 1, timeline.fade_out_color[i]
    return 0, 1, None


@dataclass(frozen=True)
class ShotWindow:
    """Which of one shot's ``frames`` its film needs as PNGs: the first
    ``head`` and the last ``tail``.

    Between them is the shot's *body*, which the film takes as one encoded
    span. A shot with an empty window (:attr:`whole`) is taken as its own
    mp4's video stream, so it needs no frame at all.

    >>> w = ShotWindow(frames=10, head=0, tail=4)
    >>> w.whole, w.body, w.png_indices
    (False, (0, 6), (6, 7, 8, 9))
    """

    frames: int
    head: int = 0
    tail: int = 0

    @property
    def whole(self) -> bool:
        return not (self.head or self.tail)

    @property
    def body(self) -> tuple[int, int]:
        """``(first, stop)``: the shot-local frames taken as one encoded span."""
        return self.head, self.frames - self.tail

    @property
    def png_indices(self) -> tuple[int, ...]:
        """The shot-local frames the film needs as PNGs."""
        return tuple(range(self.head)) + tuple(
            range(self.frames - self.tail, self.frames)
        )


@dataclass(frozen=True)
class Segment:
    """One independently encoded run of the film's picture, film frames
    ``[start, stop)``: a whole shot's own stream (``"shot"``), a shot's
    encoded body (``"body"``), or a run of PNGs composed here (``"frames"``)."""

    kind: Literal["shot", "body", "frames"]
    shot: int | None
    start: int
    stop: int

    def __len__(self) -> int:
        return self.stop - self.start


def picture_segments(
    timeline: FilmTimeline, windows: Sequence[ShotWindow]
) -> list[Segment]:
    """The film's picture as segments, in film order.

    A film frame is part of a shot's body when exactly one shot shows it and
    that frame is outside the shot's window; every other frame (a blend, a
    fade, or a frame a window was widened over) is composed from PNGs.

    >>> from an.ir.schema import Shot, Transition
    >>> tl = film_timeline([Shot(id="a", duration=1.0), Shot(id="b", duration=1.0,
    ...     transition=Transition(kind="dissolve", duration=0.4))], fps=10)
    >>> [(s.kind, s.shot, s.start, s.stop) for s in picture_segments(tl, shot_windows(tl))]
    [('body', 0, 0, 6), ('frames', None, 6, 10), ('body', 1, 10, 16)]
    """
    segments: list[Segment] = []
    for f, sources in enumerate(_frame_sources(timeline)):
        kind, shot = "frames", None
        if len(sources) == 1:
            i, j = sources[0]
            first, stop = windows[i].body
            if first <= j < stop:
                kind, shot = ("shot" if windows[i].whole else "body"), i
        last = segments[-1] if segments else None
        if last is not None and (last.kind, last.shot) == (kind, shot):
            segments[-1] = Segment(kind, shot, last.start, f + 1)
        else:
            segments.append(Segment(kind, shot, f, f + 1))
    return segments


def shot_windows(
    timeline: FilmTimeline, *, min_segment_frames: int = MIN_SEGMENT_FRAMES
) -> tuple[ShotWindow, ...]:
    """Each shot's :class:`ShotWindow`: the frames its transitions touch,
    widened until every segment of the picture has ``min_segment_frames``.

    A pure function of the timeline, so the render loop, the shot cache and
    the garbage collector all agree on what a shot's film needs from it. A
    picture of one segment has no minimum (there is nothing to concatenate).

    >>> from an.ir.schema import Shot, Transition
    >>> d = Transition(kind="dissolve", duration=0.1)   # one frame at 10 fps
    >>> tl = film_timeline([Shot(id="a", duration=1.0), Shot(id="b", duration=1.0,
    ...     transition=d)], fps=10)
    >>> [(w.head, w.tail) for w in shot_windows(tl)]   # the 1-frame run, widened to 3
    [(0, 1), (3, 0)]
    """
    k = len(timeline.frames)
    head = [timeline.dissolve_in[i] + timeline.fade_in[i] for i in range(k)]
    tail = [
        timeline.fade_out[i] + (timeline.dissolve_in[i + 1] if i + 1 < k else 0)
        for i in range(k)
    ]

    def windows() -> tuple[ShotWindow, ...]:
        return tuple(ShotWindow(timeline.frames[i], head[i], tail[i]) for i in range(k))

    # Each pass turns at least one more frame into a PNG, so this ends; at
    # worst every frame is one, which is a picture of one segment.
    while True:
        current = windows()
        segments = picture_segments(timeline, current)
        if len(segments) <= 1:
            return current
        short = [(n, s) for n, s in enumerate(segments) if len(s) < min_segment_frames]
        if not short:
            return current
        n, seg = short[0]
        if seg.kind != "frames":
            # A body (or a whole shot) too short to stand alone: all PNGs.
            head[seg.shot] = timeline.frames[seg.shot] - tail[seg.shot]
            continue
        need = min_segment_frames - len(seg)
        neighbours = [
            (s, side)
            for s, side in (
                (segments[n + 1] if n + 1 < len(segments) else None, "head"),
                (segments[n - 1] if n else None, "tail"),
            )
            if s is not None
        ]
        # Widen into an already-split shot before splitting a whole one.
        for s, side in sorted(neighbours, key=lambda p: p[0].kind == "shot"):
            take = min(need, len(s))
            if side == "head":
                head[s.shot] += take
            else:
                tail[s.shot] += take
            need -= take
            if not need:
                break


@dataclass(frozen=True)
class ShotParts:
    """What a film takes from a shot its transitions touch: the PNGs inside
    its :class:`ShotWindow` (``frames``: shot-local index -> path) and its
    body, encoded once (``body``; ``None`` when the window covers the shot)."""

    window: ShotWindow
    frames: Mapping[int, Path]
    body: Path | None = None


def _link(src: Path, dst: Path) -> None:
    """``dst`` with ``src``'s bytes: a hard link where the filesystem allows."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def _fresh_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def shot_parts(
    frames: Sequence[Path],
    window: ShotWindow,
    *,
    fps: float,
    work_dir: Path,
    pix_fmt: str | None = None,
) -> ShotParts:
    """A rendered shot's :class:`ShotParts` for ``window``, from its frames.

    The body is encoded by ``an.media.mp4.mux_frames`` — the shot mux's own
    encoder and argv — from the body's PNGs, renumbered from zero in
    ``work_dir``. The window's PNGs are referenced where they are.
    """
    from an.media.frames import DEFAULT_FRAME_PNG_PATTERN
    from an.media.mp4 import mux_frames

    frames = sorted(Path(p) for p in frames)
    if len(frames) < window.frames:
        raise AssemblyError(
            f"a shot rendered {len(frames)} frames but the timeline needs "
            f"{window.frames}; a transition needs the frames at its window, so "
            "this renderer cannot take part in one"
        )
    first, stop = window.body
    body = None
    if stop > first:
        src = _fresh_dir(Path(work_dir) / "body_frames")
        for n, path in enumerate(frames[first:stop]):
            _link(path, src / (DEFAULT_FRAME_PNG_PATTERN % n))
        body = Path(work_dir) / "body.mp4"
        mux_frames(src, fps, body, pix_fmt)
    return ShotParts(
        window=window,
        frames={j: frames[j] for j in window.png_indices},
        body=body,
    )


def _compose_frame(
    timeline: FilmTimeline,
    sources: Sequence[tuple[int, int]],
    frame_of: Any,
    out: Path,
) -> None:
    """Write one film frame from its ``(shot, local frame)`` ``sources``;
    ``frame_of(i, j)`` is that frame's PNG. A frame nothing blends or fades is
    COPIED — its bytes are the renderer's own; only blended frames are decoded."""
    import numpy as np
    from PIL import Image

    def load(path: Path) -> Any:
        with Image.open(path) as image:
            return np.asarray(image)

    if len(sources) == 1:
        i, j = sources[0]
        num, den, colour = _colour_weight(timeline, i, j)
        if not num:
            shutil.copyfile(frame_of(i, j), out)
            return
        arr = load(frame_of(i, j))
        fill = np.empty_like(arr)
        fill[..., :3] = _hex_rgb(colour)
        if arr.shape[-1] == 4:
            fill[..., 3] = arr[..., 3]
        Image.fromarray(blend(arr, fill, num, den)).save(out, format="PNG")
        return
    # A dissolve: the previous shot's tail under this shot's head.
    (ia, ja), (ib, jb) = sorted(sources)
    k = timeline.dissolve_in[ib]
    a, b = load(frame_of(ia, ja)), load(frame_of(ib, jb))
    if a.shape != b.shape:
        # Meet in the previous shot's mode, so the film's frames do not
        # change pixel format mid-sequence.
        mode = "RGBA" if a.shape[-1] == 4 else "RGB"
        b = np.asarray(Image.fromarray(b).convert(mode))
    Image.fromarray(blend(a, b, jb + 1, k + 1)).save(out, format="PNG")


def write_film_frames(
    timeline: FilmTimeline,
    frame_of: Any,
    out_dir: Path,
    *,
    pattern: str | None = None,
) -> list[Path]:
    """Every frame of the film as a PNG, in ``out_dir`` — what the delivered
    picture shows, frame for frame, BEFORE it is encoded.

    The film itself is a concat of segments (an#260) and never holds this
    sequence on disk; a measurement that needs the composed picture — the
    bench's reference for an assembled scene (an#279) — builds it here, with
    the same per-frame composition (:func:`_compose_frame`) the segments use.
    ``frame_of(i, j)`` is the PNG of frame ``j`` of shot ``i``.
    """
    from an.media.frames import DEFAULT_FRAME_PNG_PATTERN

    pattern = pattern or DEFAULT_FRAME_PNG_PATTERN
    out_dir = _fresh_dir(Path(out_dir))
    written = []
    for index, sources in enumerate(_frame_sources(timeline)):
        path = out_dir / (pattern % index)
        _compose_frame(timeline, sources, frame_of, path)
        written.append(path)
    return written


def _video_only(mp4: Path, out: Path) -> None:
    """``mp4``'s video stream, stream-copied into a file of its own: the shot
    mux lays audio under the picture with ``-c:v copy``, so these are the bits
    ``mux_frames`` wrote, and a file with no audio has its picture's length."""
    _run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-map", "0:v",
         "-c", "copy", *MP4_FASTSTART_ARGS, str(out)],
        doing=f"taking the video stream of {Path(mp4).name}",
    )  # fmt: skip


def _concat_video(
    inputs: Sequence[Path], durations: Sequence[float], out: Path
) -> None:
    """Stream-copy concat of video-only segments: no frame is re-encoded.

    Each segment's ``duration`` is STATED (its frames / fps), not read from its
    container: the mov muxer writes the edit list in the movie timescale
    (1000), and truncates it when the last packet in decode order is the
    P-frame at the highest PTS (x264 on moving content). The concat demuxer
    advances by that duration, so at 24 or 30 fps every later frame landed up
    to 1 ms early per join, cumulatively, and the film's average rate stopped
    being ``fps/1`` (an#280 review, F1; measured).
    """
    listing = out.with_suffix(".concat.txt")
    lines = []
    for p, d in zip(inputs, durations):
        quoted = str(Path(p).resolve()).replace("'", "'\\''")
        lines.append(f"file '{quoted}'\nduration {d:.9f}\n")
    listing.write_text("".join(lines), encoding="utf-8")
    _run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", *MP4_FASTSTART_ARGS, str(out)],
        doing="concatenating the film's picture",
    )  # fmt: skip


#: The stream properties every segment of one picture must share, or the
#: stream-copy concat yields a film that plays wrong with no error.
SEGMENT_STREAM_FIELDS: tuple[str, ...] = (
    "codec_name",
    "profile",
    "width",
    "height",
    "pix_fmt",
    "r_frame_rate",
)


#: Relative difference under which a segment's frame rate is the film's.
RATE_TOLERANCE: float = 1e-4


def _probe_stream(mp4: Path) -> dict[str, Any]:
    """The first video stream's :data:`SEGMENT_STREAM_FIELDS` and frame count."""
    import json

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=" + ",".join((*SEGMENT_STREAM_FIELDS, "nb_frames")),
             "-of", "json", str(mp4)],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
    except OSError as e:
        raise AssemblyError(f"ffprobe failed to launch: {e}") from e
    streams = json.loads(result.stdout or "{}").get("streams") or []
    if result.returncode != 0 or not streams:
        raise AssemblyError(f"{Path(mp4).name} has no video stream ffprobe can read")
    return streams[0]


def _check_segments(
    segments: Sequence[Segment], paths: Sequence[Path], timeline: FilmTimeline
) -> None:
    """Refuse a picture whose segments a stream copy cannot join: a shot's own
    stream (a renderer that writes only an mp4 — Manim's 480p15, say) must
    match the others and hold exactly the frames the timeline gives it.

    Before an#260 such a film was refused for having no frames; a stream copy
    would otherwise deliver it at the wrong size, rate and length, silently
    (an#280 review, F2).
    """
    from fractions import Fraction

    reference: dict[str, Any] | None = None
    for seg, path in zip(segments, paths):
        info = _probe_stream(path)
        rate = float(Fraction(info.get("r_frame_rate") or "0/1"))
        # 29.97 may read back as 30000/1001: equal to well under a frame per hour.
        if abs(rate - float(timeline.fps)) > RATE_TOLERANCE * float(timeline.fps):
            raise AssemblyError(
                f"{_segment_name(seg)} plays at {info.get('r_frame_rate')} fps but "
                f"the film is {timeline.fps} fps; a stream cannot be re-timed by a copy"
            )
        if seg.kind == "shot" and int(info.get("nb_frames") or -1) != len(seg):
            raise AssemblyError(
                f"{_segment_name(seg)} holds {info.get('nb_frames')} frames but the "
                f"timeline gives it {len(seg)}"
            )
        fields = {k: info.get(k) for k in SEGMENT_STREAM_FIELDS}
        if reference is None:
            reference = fields
        elif fields != reference:
            diff = {
                k: (reference[k], fields[k])
                for k in fields
                if fields[k] != reference[k]
            }
            raise AssemblyError(
                f"{_segment_name(seg)} cannot be joined to the rest of the film: "
                f"its stream differs in {diff}. A shot whose renderer writes only "
                "an mp4 can take part in an assembled film only when its stream is "
                "encoded like every other shot's (same size, pixel format, profile "
                "and rate)"
            )


def _segment_name(seg: Segment) -> str:
    if seg.kind == "frames":
        return f"film frames {seg.start}-{seg.stop - 1}"
    return f"shot {seg.shot}"


def _assemble_picture(
    timeline: FilmTimeline,
    windows: Sequence[ShotWindow],
    mp4s: Sequence[Path],
    parts: Sequence[ShotParts | None],
    work: Path,
    *,
    fps: float,
    pix_fmt: str | None,
) -> Path:
    """Encode or copy each :func:`picture_segments` segment, then concat."""
    from an.media.frames import DEFAULT_FRAME_PNG_PATTERN
    from an.media.mp4 import mux_frames

    pattern = DEFAULT_FRAME_PNG_PATTERN
    sources = _frame_sources(timeline)
    composed = _fresh_dir(work / "frames")  # by FILM frame index
    seg_dir = _fresh_dir(work / "segments")

    def frame_of(i: int, j: int) -> Path:
        return parts[i].frames[j]

    paths: list[Path] = []
    segments = picture_segments(timeline, windows)
    for n, seg in enumerate(segments):
        out = seg_dir / f"{n:03d}.mp4"
        if seg.kind == "shot":
            _video_only(Path(mp4s[seg.shot]), out)
        elif seg.kind == "body":
            out = parts[seg.shot].body
        else:
            run = _fresh_dir(seg_dir / f"{n:03d}_frames")
            for f in range(seg.start, seg.stop):
                film_png = composed / (pattern % f)
                _compose_frame(timeline, sources[f], frame_of, film_png)
                _link(film_png, run / (pattern % (f - seg.start)))
            mux_frames(run, fps, out, pix_fmt)
        paths.append(Path(out))
    _check_segments(segments, paths, timeline)
    picture = work / "picture.mp4"
    if len(paths) == 1:
        shutil.copyfile(paths[0], picture)
    else:
        _concat_video(paths, [len(seg) / fps for seg in segments], picture)
    return picture


# -----------------------------------------------------------------------------
# Sound: the film mix, rebuilt from sources.
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    """One audio source in film time.

    ``gain_db`` / fades / ``duck`` apply to cues only; a dialogue line is placed
    as recorded. ``play`` is how long it sounds (``None``: its own length).
    """

    path: Path
    at: float
    play: float | None = None
    loop: bool = False
    gain_db: float = 0.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    duck: tuple[float, float, float] | None = None  # (duck_db, attack, release)


@dataclass
class MixPlan:
    """Everything the film mix places, plus the dialogue it ducks under."""

    duration: float
    placements: list[Placement] = field(default_factory=list)
    dialogue_spans: list[tuple[float, float]] = field(default_factory=list)


def _cue_placement(
    cue: SoundCue, *, at: float, container_end: float, path: Path, asset_duration: float
) -> Placement:
    if cue.duration is not None:
        # A cue that does not loop cannot sound longer than its asset: its
        # fade-out must land on audio that exists.
        play = cue.duration if cue.loop else min(cue.duration, asset_duration)
    elif cue.loop:
        play = max(0.0, container_end - at)
    else:
        play = asset_duration
    return Placement(
        path=path,
        at=at,
        play=play,
        loop=cue.loop,
        gain_db=cue.gain_db,
        fade_in=cue.fade_in,
        fade_out=cue.fade_out,
        duck=(
            (cue.duck_db, cue.duck_attack, cue.duck_release)
            if cue.duck_db is not None
            else None
        ),
    )


def mix_plan(
    scene: SceneIR,
    timeline: FilmTimeline,
    mall: Mapping[str, Any],
    stage_dir: Path,
) -> MixPlan:
    """Stage every audio source of the film into ``stage_dir`` and place it."""
    from an.sounds import SoundError, get_sound, wav_duration

    stage_dir.mkdir(parents=True, exist_ok=True)
    plan = MixPlan(duration=timeline.duration)
    audio_store = mall.get("audio")
    for i, shot in enumerate(scene.timeline):
        offset = timeline.start_seconds(i)
        for k, line in enumerate(shot.dialogue):
            # The per-shot mux's rule: a line with no audio yet is skipped.
            if not line.audio_ref or line.start is None or audio_store is None:
                continue
            try:
                data = audio_store[line.audio_ref]
            except KeyError:
                continue
            # The extension is a hint ffmpeg's probe starts from: say what the
            # bytes are (a provider may cache mp3), as the per-shot mux does.
            ext = "mp3" if data[:3] == b"ID3" or data[:1] == b"\xff" else "wav"
            path = stage_dir / f"dialogue_{i}_{k}.{ext}"
            path.write_bytes(data)
            at = offset + float(line.start)
            plan.placements.append(Placement(path=path, at=at))
            if line.duration:
                plan.dialogue_spans.append((at, at + float(line.duration)))

    sounds = mall.get("sounds")
    staged: dict[str, tuple[Path, float]] = {}

    def stage(key: str) -> tuple[Path, float]:
        if key not in staged:
            if sounds is None:
                raise AssemblyError(
                    f"the scene plays sound {key!r} but the mall has no 'sounds' store"
                )
            asset, data = get_sound(sounds, key)
            path = stage_dir / f"sound_{len(staged)}.wav"
            path.write_bytes(data)
            # The audio's own length, not the record's: a store filled before
            # an#330 recorded a pipe-cut WAV's streaming header (~22369 s). A
            # file this cannot parse keeps its record (ffmpeg decodes it).
            try:
                length = wav_duration(data)
            except SoundError:
                length = asset.duration
            staged[key] = (path, length)
        return staged[key]

    def place(cue: SoundCue, *, at: float, container_end: float) -> None:
        path, length = stage(cue.sound)
        placement = _cue_placement(
            cue, at=at, container_end=container_end, path=path, asset_duration=length
        )
        # A cue that would sound for no time (a loop placed after its
        # container ends) contributes nothing; validate warns about it.
        if placement.play and at < plan.duration:
            plan.placements.append(placement)

    for cue in scene.meta.sounds:
        place(cue, at=cue.at, container_end=timeline.duration)
    for i, shot in enumerate(scene.timeline):
        for cue in shot.sounds:
            place(
                cue,
                at=timeline.start_seconds(i) + cue.at,
                container_end=timeline.end_seconds(i),
            )
    return plan


def merge_spans(
    spans: Sequence[tuple[float, float]], *, attack: float, release: float
) -> list[tuple[float, float]]:
    """Sorted spans, with any two whose ramps would meet joined into one — so a
    bed stays down between two close lines instead of pumping up for a breath.

    >>> merge_spans([(3.0, 4.0), (1.0, 2.0), (2.1, 2.5)], attack=0.1, release=0.1)
    [(1.0, 2.5), (3.0, 4.0)]
    """
    merged: list[tuple[float, float]] = []
    for s, e in sorted(spans):
        if merged and s - attack <= merged[-1][1] + release:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def duck_gain(
    t: float,
    spans: Sequence[tuple[float, float]],
    *,
    duck_db: float,
    attack: float,
    release: float,
) -> float:
    """The linear gain a ducked cue plays at, at film time ``t`` — the spec the
    ffmpeg expressions (:func:`_duck_expressions`) are written from.

    Full level away from dialogue; ``duck_db`` down while a line plays; a linear
    ramp over ``attack`` seconds BEFORE each line (so its first syllable is
    already clear) and ``release`` seconds after.

    >>> spans = [(1.0, 2.0)]
    >>> [round(duck_gain(t, spans, duck_db=-20, attack=0.5, release=0.5), 3)
    ...  for t in (0.0, 0.75, 1.5, 2.25, 3.0)]
    [1.0, 0.55, 0.1, 0.55, 1.0]
    """
    depth = 1.0 - 10 ** (duck_db / 20.0)
    weight = 0.0
    for s, e in merge_spans(spans, attack=attack, release=release):
        w = min((t - (s - attack)) / attack, ((e + release) - t) / release)
        weight = max(weight, min(1.0, max(0.0, w)))
    return 1.0 - depth * weight


def _duck_expressions(
    spans: Sequence[tuple[float, float]],
    *,
    duck_db: float,
    attack: float,
    release: float,
) -> list[str]:
    """:func:`duck_gain` as ffmpeg ``volume`` expressions in ``t``, one per
    chunk of at most :data:`DUCK_SPANS_PER_EXPRESSION` spans, to be CHAINED.

    Chaining is exact, not an approximation: after :func:`merge_spans` no two
    spans' ramps overlap, so at any instant at most one chunk's gain differs
    from 1 and the product of the chunks is the single-expression gain. One
    expression for a whole film is not an option — ffmpeg 9.0.1 refuses the
    nested form at about 95 spans (measured), a long film's dialogue count.
    """
    depth = 1.0 - 10 ** (duck_db / 20.0)
    terms = [
        f"clip(min((t-{s - attack:.6f})/{attack:.6f}\\,"
        f"({e + release:.6f}-t)/{release:.6f})\\,0\\,1)"
        for s, e in merge_spans(spans, attack=attack, release=release)
    ]
    expressions = []
    for i in range(0, len(terms), DUCK_SPANS_PER_EXPRESSION):
        chunk = terms[i : i + DUCK_SPANS_PER_EXPRESSION]
        weight = chunk[0]
        for term in chunk[1:]:
            weight = f"max({weight}\\,{term})"
        expressions.append(f"1-{depth:.6f}*{weight}")
    return expressions


def mix_command(plan: MixPlan, video: Path, output: Path) -> list[str]:
    """The ffmpeg argv that lays ``plan``'s audio under ``video``'s picture.

    Pure (no I/O), so its shape is testable without ffmpeg. The picture is
    ``-c:v copy``: the mix never touches a frame.
    """
    sr, channels = FILM_AUDIO_SAMPLE_RATE, FILM_AUDIO_CHANNELS
    layout = "mono" if channels == 1 else "stereo"
    fmt = f"aformat=sample_fmts=fltp:sample_rates={sr}:channel_layouts={layout}"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video),
        "-f", "lavfi", "-t", f"{plan.duration:.6f}",
        "-i", f"anullsrc=channel_layout={layout}:sample_rate={sr}",
    ]  # fmt: skip
    parts = [f"[1:a]{fmt}[base]"]
    labels = ["[base]"]
    for n, p in enumerate(plan.placements):
        if p.loop:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-i", str(p.path)]
        chain = [fmt]
        if p.play is not None:
            chain.append(f"atrim=end={p.play:.6f}")
        if p.fade_in:
            chain.append(f"afade=t=in:d={p.fade_in:.6f}")
        if p.fade_out and p.play is not None:
            start = max(0.0, p.play - p.fade_out)
            chain.append(f"afade=t=out:st={start:.6f}:d={p.fade_out:.6f}")
        if p.gain_db:
            chain.append(f"volume={p.gain_db:.6f}dB")
        delay = int(round(p.at * sr))
        if delay:
            chain.append(f"adelay={delay}S:all=1")
        if p.duck is not None and plan.dialogue_spans:
            duck_db, attack, release = p.duck
            # `eval=frame` holds the gain for a whole audio frame, and a WAV
            # demuxes in frames of thousands of samples: re-chunked first, so
            # the ramp is a staircase of DUCK_FRAME_SAMPLES-long steps.
            chain.append(f"asetnsamples=n={DUCK_FRAME_SAMPLES}:p=0")
            for expr in _duck_expressions(
                plan.dialogue_spans, duck_db=duck_db, attack=attack, release=release
            ):
                chain.append(f"volume=eval=frame:volume='{expr}'")
        label = f"[s{n}]"
        parts.append(f"[{n + 2}:a]{','.join(chain)}{label}")
        labels.append(label)
    parts.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:dropout_transition=0:normalize=0[aout]"
    )
    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", FILM_AUDIO_BITRATE,
        "-ar", str(sr), "-ac", str(channels),
        "-t", f"{plan.duration:.6f}",
        *MP4_FASTSTART_ARGS,
        str(output),
    ]  # fmt: skip
    return cmd


def _run(cmd: list[str], *, doing: str) -> None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        raise AssemblyError(f"ffmpeg failed to launch while {doing}: {e}") from e
    if result.returncode != 0:
        raise AssemblyError(
            f"ffmpeg failed while {doing} (rc={result.returncode}):\n{result.stderr}"
        )


# -----------------------------------------------------------------------------
# The facade.
# -----------------------------------------------------------------------------


def assemble_film(
    scene: SceneIR,
    shot_results: Sequence[Any],
    output: Path,
    *,
    fps: float,
    mall: Mapping[str, Any],
    work_dir: Path,
    pix_fmt: str | None = None,
    parts: Sequence[ShotParts | None] | None = None,
) -> Path:
    """Assemble rendered shots into ``output``: the picture as a concat of
    segments (transitions composed in), then the mix.

    ``shot_results`` are the renderers' `RenderResult`s, in timeline order. A
    shot no transition touches contributes its mp4 alone. A shot one touches
    needs its :class:`ShotParts` for its :func:`shot_windows` window: pass them
    in ``parts`` (a reused shot's come from the shot cache), or the shot's
    ``frame_manifest`` must hold its frames, from which they are built.

    **Why not one mux of every frame**, as before an#260: the picture depended
    on every frame of every shot, so a film with a dissolve or a music bed
    could reuse no shot without caching all of its PNGs — hundreds of MB per
    1080p shot. The segment concat puts frame ``i`` at ``i / fps`` exactly as
    the one mux did (measured, an#260), and each frame decodes to exactly what
    its own segment decodes to.
    """
    timeline = film_timeline(scene.timeline, fps=fps)
    windows = shot_windows(timeline)
    work = Path(work_dir) / "film"
    work.mkdir(parents=True, exist_ok=True)
    given = list(parts) if parts is not None else [None] * len(windows)
    if len(given) != len(windows) or len(shot_results) != len(windows):
        raise AssemblyError(
            f"{len(windows)} shots on the timeline, but {len(shot_results)} "
            f"rendered shots and {len(given)} parts were given"
        )
    built: list[ShotParts | None] = []
    for i, (window, result, have) in enumerate(zip(windows, shot_results, given)):
        manifest = list(getattr(result, "frame_manifest", None) or ())
        if manifest and len(manifest) < window.frames:
            raise AssemblyError(
                f"shot {i} rendered {len(manifest)} frames but the timeline "
                f"needs {window.frames}"
            )
        if window.whole:
            built.append(None)
        elif have is not None:
            if have.window != window:
                raise AssemblyError(
                    f"shot {i}'s parts are for {have.window}, but the film needs {window}"
                )
            built.append(have)
        elif manifest:
            built.append(
                shot_parts(
                    manifest, window, fps=fps, work_dir=work / "parts" / f"{i:03d}",
                    pix_fmt=pix_fmt,
                )
            )  # fmt: skip
        else:
            raise AssemblyError(
                f"shot {i} meets a transition, so the film needs its frames at "
                f"the transition, but its renderer produced no frames and no "
                "parts were given; a renderer that only writes an mp4 can take "
                "part in a film only where no transition touches it"
            )
    picture = _assemble_picture(
        timeline,
        windows,
        [Path(r.mp4_path) for r in shot_results],
        built,
        work,
        fps=fps,
        pix_fmt=pix_fmt,
    )
    plan = mix_plan(scene, timeline, mall, work / "audio")
    _run(mix_command(plan, picture, output), doing="mixing the film's sound")
    return output
