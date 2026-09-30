"""Film assembly: rendered shots → one film, with transitions and a sound layer.

Every shot renders in isolation (`an.render`); this module decides how the
shots meet and what is heard over them. It runs only when a scene asks for it
— a non-``cut`` :class:`~an.ir.schema.Transition` or any
:class:`~an.ir.schema.SoundCue` — so a scene with neither takes the old
``_ffmpeg_concat`` path, byte for byte (:func:`needs_assembly`).

**Where each part happens, and why there.**

- *Picture*: transitions are composed in the FRAME STAGE, on the per-shot PNGs,
  in exact integer arithmetic, and the film is muxed ONCE by the same
  ``_ffmpeg_mux`` every shot uses. Composing in ffmpeg (``xfade``) would decode
  already-encoded shots and re-encode them — a second generation of x264 loss
  on every frame of the film, not just the transition — and would retire the
  render pipeline's "ffmpeg never touches a frame" clause. A frame no
  transition touches is copied byte for byte: Chromium's own PNG.
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

import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from an.base import (
    FILM_AUDIO_BITRATE,
    FILM_AUDIO_CHANNELS,
    FILM_AUDIO_SAMPLE_RATE,
    MP4_FASTSTART_ARGS,
)
from an.frame_clock import frame_count
from an.ir.schema import SceneIR, Shot, SoundCue

__all__ = [
    "AssemblyError",
    "FilmTimeline",
    "assemble_film",
    "duck_gain",
    "film_duration",
    "film_timeline",
    "needs_assembly",
    "transition_problems",
]


#: The ducking gain is re-evaluated every this many samples (10 ms at
#: 44.1 kHz): fine enough that a 80 ms attack is a ramp, not a step.
DUCK_FRAME_SAMPLES: int = 441

#: Dialogue spans per ducking expression. ffmpeg 9.0.1 refuses one nested
#: expression at about 95 spans (a sum of terms fails at 100 too); well under.
DUCK_SPANS_PER_EXPRESSION: int = 40


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


def _colour_weight(timeline: FilmTimeline, i: int, j: int) -> tuple[int, int, str | None]:
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


def compose_frames(
    timeline: FilmTimeline,
    shot_frames: Sequence[Sequence[Path]],
    out_dir: Path,
    *,
    pattern: str,
) -> list[Path]:
    """Write the film's frames to ``out_dir`` as ``pattern % index``.

    ``shot_frames[i]`` are shot ``i``'s PNGs in order (at least
    ``timeline.frames[i]`` of them). A frame no transition touches is COPIED —
    its bytes are the renderer's own; only blended frames are decoded.
    """
    import numpy as np
    from PIL import Image

    for i, paths in enumerate(shot_frames):
        if len(paths) < timeline.frames[i]:
            raise AssemblyError(
                f"shot {i} rendered {len(paths)} frames but the timeline needs "
                f"{timeline.frames[i]}; a transition needs every shot's frames, "
                "so this renderer cannot take part in one"
            )
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.png"):
        stale.unlink()

    def load(path: Path) -> Any:
        with Image.open(path) as image:
            return np.asarray(image)

    def faded(i: int, j: int, arr: Any | None) -> Any | None:
        num, den, colour = _colour_weight(timeline, i, j)
        if not num:
            return arr
        if arr is None:
            arr = load(shot_frames[i][j])
        fill = np.empty_like(arr)
        fill[..., :3] = _hex_rgb(colour)
        if arr.shape[-1] == 4:
            fill[..., 3] = arr[..., 3]
        return blend(arr, fill, num, den)

    written: list[Path] = []
    for f, sources in enumerate(_frame_sources(timeline)):
        out = out_dir / (pattern % f)
        if len(sources) == 1:
            i, j = sources[0]
            arr = faded(i, j, None)
            if arr is None:
                shutil.copyfile(shot_frames[i][j], out)
            else:
                Image.fromarray(arr).save(out, format="PNG")
        else:  # a dissolve: the previous shot's tail under this shot's head
            (ia, ja), (ib, jb) = sorted(sources)
            k = timeline.dissolve_in[ib]
            a, b = load(shot_frames[ia][ja]), load(shot_frames[ib][jb])
            if a.shape != b.shape:
                # Meet in the previous shot's mode, so the film's frames do not
                # change pixel format mid-sequence.
                mode = "RGBA" if a.shape[-1] == 4 else "RGB"
                b = np.asarray(Image.fromarray(b).convert(mode))
            Image.fromarray(blend(a, b, jb + 1, k + 1)).save(out, format="PNG")
        written.append(out)
    return written


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
    from an.sounds import get_sound

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
            staged[key] = (path, asset.duration)
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
    spans: Sequence[tuple[float, float]], *, duck_db: float, attack: float, release: float
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
) -> Path:
    """Assemble rendered shots into ``output``: the picture from the shots'
    frames (transitions composed in), muxed once, then the mix.

    ``shot_results`` are the renderers' `RenderResult`s, in timeline order;
    each must carry its frames (``frame_manifest``), so a renderer that only
    produces an mp4 cannot take part in an assembled film.
    """
    timeline = film_timeline(scene.timeline, fps=fps)
    work = Path(work_dir) / "film"
    work.mkdir(parents=True, exist_ok=True)
    picture = work / "picture.mp4"
    # ALWAYS from frames, even with no transition: the concat of shot mp4s
    # starts its picture after the AAC priming delay (23 ms) and advances by
    # each shot's CONTAINER length, not its frame count, so a mix placed on the
    # frame grid would lead the picture by 23 ms and drift at every shot whose
    # duration is not a whole number of frames (both measured, an#163 review).
    # One mux of the frame sequence puts frame i at exactly i / fps.
    from an.adapters.cutout.render import DEFAULT_FRAME_PNG_PATTERN, _ffmpeg_mux

    frames = compose_frames(
        timeline,
        [sorted(r.frame_manifest) for r in shot_results],
        work / "frames",
        pattern=DEFAULT_FRAME_PNG_PATTERN,
    )
    if len(frames) != timeline.total_frames:  # pragma: no cover — invariant
        raise AssemblyError("composed frame count disagrees with the timeline")
    _ffmpeg_mux(work / "frames", fps, picture, pix_fmt)
    plan = mix_plan(scene, timeline, mall, work / "audio")
    _run(mix_command(plan, picture, output), doing="mixing the film's sound")
    return output

