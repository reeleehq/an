"""The MP4 sink: PNG frames -> the delivered H.264 mp4, with the pinned argv.

Every flag here has a measured reason, recorded beside it; the
``an-dev-render-pipeline`` skill (section 3) is the table of them. The argv is
pinned EXACTLY (``tests/test_encode_pins.py`` compares it for equality, not as a
subset), because ``DETERMINISTIC_X264_ARGS`` is a comparability key of every
encode-side metric in the bench's ledger.

Engine-independent: it reads a frame directory (:mod:`an.media.frames`) and
knows nothing about what drew the frames. Moved from
``an/adapters/cutout/render.py`` (an#247), whose old names (``_ffmpeg_mux``,
``_check_pix_fmt``, ``DEFAULT_PIX_FMT``, ...) are LIVE aliases of these: reading
one reads here, and rebinding one -- the bench's ``high_crf`` lever, a test's
``patch_subprocess_run`` -- rebinds here (:mod:`an._shims`).

**Two seams are module globals read at CALL time, deliberately**:
``DETERMINISTIC_X264_ARGS`` (the ``high_crf`` lever rebinds it) and
``DEFAULT_PIX_FMT``. Hoisting either into a default argument binds it at
``def`` time and disarms the lever silently.

>>> check_pix_fmt(None), check_pix_fmt("yuv444p")
('yuv420p', 'yuv444p')
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from an.base import BT709_SCALE_FILTER, MP4_FASTSTART_ARGS
from an.media.frames import DEFAULT_FRAME_PNG_PATTERN

if TYPE_CHECKING:  # pragma: no cover - types only
    from an.adapters._base import RenderContext
    from an.ir.schema import Shot

__all__ = [
    "AUDIO_SAMPLE_RATE",
    "BT709_SCALE_FILTER",
    "DEFAULT_PIX_FMT",
    "DETERMINISTIC_X264_ARGS",
    "MP4_FASTSTART_ARGS",
    "MediaError",
    "SUPPORTED_PIX_FMTS",
    "add_audio",
    "check_pix_fmt",
    "ensure_ffmpeg",
    "mux_frames",
    "mux_shot",
    "stage_audio_inputs",
]


class MediaError(RuntimeError):
    """A sink could not write what it was asked to. Carries actionable detail.

    A renderer re-raises it as its own typed error at its boundary
    (``frame_stage_renderer(..., error=...)``), so a cut-out render still fails
    with ``CutoutRenderError``.
    """


#: The sample rate of every shot's audio stream, silent base included. One
#: rate for the whole film, so the concat never resamples.
AUDIO_SAMPLE_RATE: int = 44100

#: The delivered encode's pixel format, and **the one first-order quality lever
#: in this file**. Measured on 30 real 1080p `an` frames, edge-band mean error:
#: current flags 11.35, crf18 4:2:0 11.05, crf18 `-tune animation` 10.96,
#: mathematically lossless 4:2:0 **10.15** — and crf18 **4:4:4 3.79**.
#: Losslessness buys 8%; dropping chroma subsampling buys **66%**. Wave 2's own
#: conclusion: "bitrate is second-order, pixel format is first-order".
#:
#: **The default stays 4:2:0 because that is a PRODUCT constraint, not an
#: encoder-tuning one.** High 4:4:4 Predictive is refused by many hardware
#: decoders, browsers and platforms, so flipping it would hand a design partner
#: a file they cannot play. 4:4:4 is reachable per render
#: (`an render --pix-fmt yuv444p`), which is the right shape for a knob whose
#: right answer depends on where the file is going.
#:
#: Read as a MODULE GLOBAL at call time, deliberately: that is what lets the
#: bench's lever rebind it from outside, exactly as `high_crf` rebinds
#: `DETERMINISTIC_X264_ARGS`. Hoisting either into a default argument binds it
#: at `def` time and disarms the lever silently.
DEFAULT_PIX_FMT: str = "yuv420p"

#: The formats the knob accepts. Not an open string: a typo would reach ffmpeg
#: as an obscure failure minutes into a render, and a format outside this set
#: has not been measured against the panel.
SUPPORTED_PIX_FMTS: tuple[str, ...] = ("yuv420p", "yuv444p")

#: x264 encode knobs pinned so the delivered mp4 is a function of the frames
#: rather than of the machine (an#34, research §2).
#:
#: `-threads 1` — `-threads 1/4/11` all give bit-identical decoded pixels, so
#: this looks unnecessary on a laptop. It is not: `auto` raises
#: `lookahead_threads` above 1 at roughly `-threads >= 12`, and a forced
#: `lookahead-threads=4` changes 86.2% of the bytes (max delta 80). A big CI
#: runner crosses that line and a 4-core dev box never will, which is precisely
#: how an unpinned thread count ships without anyone seeing it.
#:
#: `-crf 23 -preset medium` — both are libx264's compiled-in defaults today, so
#: passing them changes nothing now and pins us against a build whose defaults
#: differ. Worth pinning because preset swings distinct colour counts **2.3x,
#: non-monotonically** (ultrafast 3141, veryfast 7296, medium 6064, slower 5393)
#: against a crf18->23 signal of 1.35x — an unpinned preset dominates the very
#: signal a quality ledger tries to measure.
#:
#: BT.709 is the one knob here that CHANGES today's output, and it changes more
#: than the research predicted — measured, not assumed (an#34):
#:
#: - `-colorspace bt709` does not merely *tag* the file. It sets the matrix of
#:   the auto-inserted RGB->YUV conversion, so the **encoded luma and chroma
#:   planes themselves change**. Confirmed by construction: forcing
#:   `scale=out_color_matrix=bt601` reproduces the untagged output's decoded
#:   stream byte-for-byte, i.e. `an` has been converting with BT.601 all along.
#:   **On ffmpeg 8/9. It is false on ffmpeg 6.1** — where the same flags reach
#:   only the VUI and the planes stay BT.601 (an#148, measured; see
#:   `an.base.BT709_SCALE_FILTER` for the numbers). That is why the mux now
#:   states the conversion explicitly with `-vf` instead of inferring it from
#:   these flags, which stay for the tag they land.
#: - `-color_range tv` is a **no-op today** (limited range is already the
#:   default for yuv420p here). Pinned anyway, so a build that defaults
#:   differently cannot change the output silently.
#: - The ffmpeg-level `-color_primaries` / `-color_trc` flags **do not reach the
#:   bitstream**: with them alone, ffprobe reports `color_space=bt709` and
#:   `color_primaries=unknown`, `color_transfer=unknown`. `-x264-params` is what
#:   lands all three in the VUI, and it leaves the decoded stream identical. A
#:   half-tagged file is worse than an untagged one — the player stops guessing
#:   the matrix but still guesses the primaries.
#:
#: Why bother: untagged, the *player* picks its matrix by a height heuristic
#: (BT.601 below ~576 lines). Every shipped `an` example is 320x240 to 640x360,
#: so encode and playback agree by luck; at 1080p the same code would encode
#: with BT.601 and be displayed as BT.709, a silent, resolution-dependent colour
#: error. Pinning both sides to BT.709 makes them agree at every resolution.
#: This is a **one-time deliberate re-baseline** of every mp4 — cheap now,
#: because no ledger exists yet to invalidate.
DETERMINISTIC_X264_ARGS: tuple[str, ...] = (
    "-threads",
    "1",
    "-crf",
    "23",
    "-preset",
    "medium",
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
    # The half that actually reaches the bitstream; see above.
    "-x264-params",
    "colorprim=bt709:transfer=bt709:colormatrix=bt709",
)


def check_pix_fmt(pix_fmt: str | None) -> str:
    """Resolve and validate the pixel format, or refuse with the whole list.

    ``None`` resolves to :data:`DEFAULT_PIX_FMT` **at call time**, which is what
    lets the bench's lever rebind the module global and reach this render.

    Refuses an unknown format rather than passing it to ffmpeg: a typo would
    otherwise surface minutes into a render as an obscure encoder error, and on
    the second shot of a parallel render it would surface from a thread. A
    format outside the list has also never been measured against the panel.
    """
    resolved = pix_fmt or DEFAULT_PIX_FMT
    if resolved not in SUPPORTED_PIX_FMTS:
        raise MediaError(
            f"pix_fmt={resolved!r} is not one of {SUPPORTED_PIX_FMTS}. 4:4:4 is "
            "opt-in and 4:2:0 is the default for a PRODUCT reason rather than "
            "an encoder one — High 4:4:4 Predictive is refused by many hardware "
            "decoders, browsers and platforms, so a 4:4:4 file is one some "
            "viewers cannot play."
        )
    return resolved


def ensure_ffmpeg() -> None:
    """Refuse before anything launches when ffmpeg is not on ``PATH``."""
    if shutil.which("ffmpeg") is None:
        raise MediaError(
            "ffmpeg not found on PATH. Install with: brew install ffmpeg "
            "(macOS) or apt install ffmpeg (Linux)."
        )


def mux_frames(
    frames_dir: Path, fps: int | float, output_mp4: Path, pix_fmt: str | None = None
) -> None:
    """Mux a PNG sequence to H.264 mp4.

    ``pix_fmt=None`` means "whatever the module default is **right now**", which
    is what keeps the bench's `pix_fmt` lever able to reach this call by
    rebinding :data:`DEFAULT_PIX_FMT`. A caller that passes one wins; the bench
    never passes one, so the lever reaches the encode AND the recorded
    environment, and the two cannot disagree.
    """
    # Resolved AND validated through the one function that does both, so a
    # direct call to the mux cannot slip an unmeasured format past the check
    # the frame stage performs — and so there is one place that turns
    # `None` into the module default, which is the seam the lever pulls.
    resolved = check_pix_fmt(pix_fmt)
    pattern = str(frames_dir / DEFAULT_FRAME_PNG_PATTERN)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-i",
        pattern,
        # The RGB->YUV conversion, NAMED rather than inferred from the colour
        # tags below — which reach it on ffmpeg 8/9 and do not on ffmpeg 6.1
        # (an#148). Byte-identical to the pre-an#148 output on a build where
        # they did reach it.
        "-vf",
        BT709_SCALE_FILTER,
        "-c:v",
        "libx264",
        "-pix_fmt",
        resolved,
        *DETERMINISTIC_X264_ARGS,
        # Kept, though this file is an intermediate `silent.mp4` that never
        # ships and whose container `add_audio` re-lays anyway. The
        # point of naming the constant is that the answer to "does an's mp4
        # have faststart" stops depending on which of the three commands you
        # happen to be reading.
        *MP4_FASTSTART_ARGS,
        str(output_mp4),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        raise MediaError(f"ffmpeg failed to launch: {e}") from e
    if result.returncode != 0 or not output_mp4.exists():
        raise MediaError(
            "ffmpeg mux failed (rc=%d):\n%s" % (result.returncode, result.stderr)
        )


def stage_audio_inputs(
    shot: Shot, ctx: RenderContext, work_dir: Path
) -> list[tuple[Path, float]]:
    """Write the shot's per-dialogue audio bytes to disk and return (path, delay)s.

    Looks up each ``dialogue.audio_ref`` in ``mall["audio"]``. Lines without
    an audio_ref or duration are skipped silently. Returns ``[]`` when no
    audio is available, so the caller can use a video-only path.
    """
    audio_store = ctx.mall.get("audio") if ctx.mall else None
    if not audio_store:
        return []
    out: list[tuple[Path, float]] = []
    for i, line in enumerate(shot.dialogue):
        if not line.audio_ref or line.start is None:
            continue
        try:
            audio_bytes = audio_store[line.audio_ref]
        except KeyError:
            continue
        # Sniff format: WAV starts with 'RIFF', mp3 with 'ID3' or 0xFFFB.
        if audio_bytes[:4] == b"RIFF":
            ext = "wav"
        elif audio_bytes[:3] == b"ID3" or audio_bytes[:1] == b"\xff":
            ext = "mp3"
        else:
            ext = "wav"
        path = work_dir / f"audio_{i}_{line.audio_ref[:8]}.{ext}"
        path.write_bytes(audio_bytes)
        out.append((path, float(line.start)))
    return out


def mux_shot(
    frames_dir: Path,
    shot: Shot,
    ctx: RenderContext,
    work_dir: Path,
    output_mp4: Path,
    *,
    n_frames: int,
    pix_fmt: str | None = None,
) -> int:
    """Frames → the delivered per-shot mp4: a silent mux, then the audio mux.
    Returns how many dialogue audio tracks were laid under the picture.

    Every shot mp4 carries an AAC stream (silent if no dialogue) so the final
    ffmpeg concat across heterogeneous shots works without surprises. The audio
    is cut to the PICTURE's length, ``n_frames / fps``, not ``shot.duration``:
    a duration that is not a whole number of frames (2.6 s at 24 fps is 62.4)
    gets ``round(d * fps)`` frames, and an audio track padded to ``d`` made the
    shot's container longer than its picture — the concat then advanced by the
    container and left sub-frame holes in the film's video timestamps, which
    ffprobe reads as ``r_frame_rate=120/1`` (an#195).
    """
    silent_mp4 = work_dir / "silent.mp4"
    mux_frames(frames_dir, ctx.fps, silent_mp4, pix_fmt)
    audio_inputs = stage_audio_inputs(shot, ctx, work_dir)
    add_audio(silent_mp4, audio_inputs, output_mp4, n_frames / ctx.fps)
    return len(audio_inputs)


def add_audio(
    video_path: Path,
    audio_inputs: list[tuple[Path, float]],
    output_path: Path,
    duration_s: float,
) -> None:
    """Mux a silence base + ``audio_inputs`` (path, delay_s) onto ``video_path``.

    Always emits an audio stream. ``anullsrc`` provides the silent base track
    of length ``duration_s`` so concat across shots is safe; dialogue lines
    are overlaid via ``adelay`` + ``amix``. ``duration_s`` must be the
    picture's length (frames / fps): the concat advances each shot by its
    container length, which is the longer of the two streams (an#195).
    """
    sr = AUDIO_SAMPLE_RATE
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        # Silent base (input #1)
        "-f",
        "lavfi",
        "-t",
        f"{duration_s:.6f}",
        "-i",
        f"anullsrc=channel_layout=mono:sample_rate={sr}",
    ]
    for audio_path, _delay in audio_inputs:
        cmd += ["-i", str(audio_path)]

    filter_parts: list[str] = []
    # Resample silence base to ensure consistent format with dialogue inputs.
    filter_parts.append(
        f"[1:a]aformat=sample_fmts=fltp:sample_rates={sr}:channel_layouts=mono[base]"
    )
    overlays: list[str] = []
    for i, (_path, delay_s) in enumerate(audio_inputs):
        delay_ms = max(0, int(round(delay_s * 1000)))
        # Index in command: 0=video, 1=anullsrc, 2..=user audio
        cmd_idx = i + 2
        label = f"a{i}"
        filter_parts.append(
            f"[{cmd_idx}:a]aformat=sample_fmts=fltp:sample_rates={sr}:channel_layouts=mono,"
            f"adelay={delay_ms}|{delay_ms}[{label}]"
        )
        overlays.append(f"[{label}]")

    # Mix [base] + all overlays (always at least 1 input for amix).
    inputs_count = 1 + len(overlays)
    mix_in = "[base]" + "".join(overlays)
    filter_parts.append(
        f"{mix_in}amix=inputs={inputs_count}:dropout_transition=0:normalize=0[aout]"
    )

    cmd += [
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        str(sr),
        "-ac",
        "1",
        "-t",
        f"{duration_s:.6f}",
        # THE DELIVERED per-shot mp4 is this one, not `mux_frames`'s. `-c:v
        # copy` re-lays the container and writes `moov` last, so without this
        # every shot mp4 `an` has ever produced is progressive-download
        # hostile -- including the bytes that go into `mall["shots"]` and,
        # via the single-shot `shutil.copy` branch, into `output/main.mp4`.
        *MP4_FASTSTART_ARGS,
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        raise MediaError(f"ffmpeg audio mux failed to launch: {e}") from e
    if result.returncode != 0 or not output_path.exists():
        raise MediaError(
            "ffmpeg audio mux failed (rc=%d):\n%s" % (result.returncode, result.stderr)
        )
