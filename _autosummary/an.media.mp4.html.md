# an.media.mp4

The MP4 sink: PNG frames -> the delivered H.264 mp4, with the pinned argv.

Every flag here has a measured reason, recorded beside it; the
`an-dev-render-pipeline` skill (section 3) is the table of them. The argv is
pinned EXACTLY (`tests/test_encode_pins.py` compares it for equality, not as a
subset), because `DETERMINISTIC_X264_ARGS` is a comparability key of every
encode-side metric in the bench’s ledger.

Engine-independent: it reads a frame directory ([`an.media.frames`](an.media.frames.html.md#module-an.media.frames)) and
knows nothing about what drew the frames. Moved from
`an/adapters/cutout/render.py` (an#247), whose old names (`_ffmpeg_mux`,
`_check_pix_fmt`, `DEFAULT_PIX_FMT`, …) are LIVE aliases of these: reading
one reads here, and rebinding one – the bench’s `high_crf` lever, a test’s
`patch_subprocess_run` – rebinds here (`an._shims`).

**Two seams are module globals read at CALL time, deliberately**:
`DETERMINISTIC_X264_ARGS` (the `high_crf` lever rebinds it) and
`DEFAULT_PIX_FMT`. Hoisting either into a default argument binds it at
`def` time and disarms the lever silently.

```pycon
>>> check_pix_fmt(None), check_pix_fmt("yuv444p")
('yuv420p', 'yuv444p')
```

### Module Attributes

| [`AUDIO_SAMPLE_RATE`](#an.media.mp4.AUDIO_SAMPLE_RATE)       | The sample rate of every shot's audio stream, silent base included.                                                                           |
|--------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| [`DEFAULT_PIX_FMT`](#an.media.mp4.DEFAULT_PIX_FMT)         | The delivered encode's pixel format, and \*\*the one first-order quality lever in this file\*\*.                                              |
| [`SUPPORTED_PIX_FMTS`](#an.media.mp4.SUPPORTED_PIX_FMTS)      | a typo would reach ffmpeg as an obscure failure minutes into a render, and a format outside this set has not been measured against the panel. |
| [`DETERMINISTIC_X264_ARGS`](#an.media.mp4.DETERMINISTIC_X264_ARGS) | x264 encode knobs pinned so the delivered mp4 is a function of the frames rather than of the machine (an#34, research §2).                    |

### Functions

| [`add_audio`](#an.media.mp4.add_audio)(video_path, audio_inputs, ...)       | Mux a silence base + `audio_inputs` (path, delay_s) onto `video_path`.       |
|-------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`check_pix_fmt`](#an.media.mp4.check_pix_fmt)(pix_fmt)                         | Resolve and validate the pixel format, or refuse with the whole list.        |
| [`ensure_ffmpeg`](#an.media.mp4.ensure_ffmpeg)()                                | Refuse before anything launches when ffmpeg is not on `PATH`.                |
| [`mux_frames`](#an.media.mp4.mux_frames)(frames_dir, fps, output_mp4[, ...]) | Mux a PNG sequence to H.264 mp4.                                             |
| [`mux_shot`](#an.media.mp4.mux_shot)(frames_dir, shot, ctx, work_dir, ...) | Frames → the delivered per-shot mp4: a silent mux, then the audio mux.       |
| [`stage_audio_inputs`](#an.media.mp4.stage_audio_inputs)(shot, ctx, work_dir)        | Write the shot's per-dialogue audio bytes to disk and return (path, delay)s. |

### Exceptions

| [`MediaError`](#an.media.mp4.MediaError)   | A sink could not write what it was asked to.   |
|---------------------------------------------------------------|------------------------------------------------|

### an.media.mp4.AUDIO_SAMPLE_RATE *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 44100*

The sample rate of every shot’s audio stream, silent base included. One
rate for the whole film, so the concat never resamples.

### an.media.mp4.DEFAULT_PIX_FMT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'yuv420p'*

The delivered encode’s pixel format, and \*\*the one first-order quality lever
in this file\*\*. Measured on 30 real 1080p `an` frames, edge-band mean error:
current flags 11.35, crf18 4:2:0 11.05, crf18 `-tune animation` 10.96,
mathematically lossless 4:2:0 **10.15** — and crf18 **4:4:4 3.79**.
Losslessness buys 8%; dropping chroma subsampling buys **66%**. Wave 2’s own
conclusion: “bitrate is second-order, pixel format is first-order”.

\*\*The default stays 4:2:0 because that is a PRODUCT constraint, not an
encoder-tuning one.\*\* High 4:4:4 Predictive is refused by many hardware
decoders, browsers and platforms, so flipping it would hand a design partner
a file they cannot play. 4:4:4 is reachable per render
(`an render --pix-fmt yuv444p`), which is the right shape for a knob whose
right answer depends on where the file is going.

Read as a MODULE GLOBAL at call time, deliberately: that is what lets the
bench’s lever rebind it from outside, exactly as `high_crf` rebinds
`DETERMINISTIC_X264_ARGS`. Hoisting either into a default argument binds it
at `def` time and disarms the lever silently.

### an.media.mp4.DETERMINISTIC_X264_ARGS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('-threads', '1', '-crf', '23', '-preset', 'medium', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv', '-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709')*

x264 encode knobs pinned so the delivered mp4 is a function of the frames
rather than of the machine (an#34, research §2).

`-threads 1` — `-threads 1/4/11` all give bit-identical decoded pixels, so
this looks unnecessary on a laptop. It is not: `auto` raises
`lookahead_threads` above 1 at roughly `-threads >= 12`, and a forced
`lookahead-threads=4` changes 86.2% of the bytes (max delta 80). A big CI
runner crosses that line and a 4-core dev box never will, which is precisely
how an unpinned thread count ships without anyone seeing it.

`-crf 23 -preset medium` — both are libx264’s compiled-in defaults today, so
passing them changes nothing now and pins us against a build whose defaults
differ. Worth pinning because preset swings distinct colour counts \*\*2.3x,
non-monotonically\*\* (ultrafast 3141, veryfast 7296, medium 6064, slower 5393)
against a crf18->23 signal of 1.35x — an unpinned preset dominates the very
signal a quality ledger tries to measure.

BT.709 is the one knob here that CHANGES today’s output, and it changes more
than the research predicted — measured, not assumed (an#34):

- `-colorspace bt709` does not merely *tag* the file. It sets the matrix of
  the auto-inserted RGB->YUV conversion, so the \*\*encoded luma and chroma
  planes themselves change\*\*. Confirmed by construction: forcing
  `scale=out_color_matrix=bt601` reproduces the untagged output’s decoded
  stream byte-for-byte, i.e. `an` has been converting with BT.601 all along.
  **On ffmpeg 8/9. It is false on ffmpeg 6.1** — where the same flags reach
  only the VUI and the planes stay BT.601 (an#148, measured; see
  `an.base.BT709_SCALE_FILTER` for the numbers). That is why the mux now
  states the conversion explicitly with `-vf` instead of inferring it from
  these flags, which stay for the tag they land.
- `-color_range tv` is a **no-op today** (limited range is already the
  default for yuv420p here). Pinned anyway, so a build that defaults
  differently cannot change the output silently.
- The ffmpeg-level `-color_primaries` / `-color_trc` flags \*\*do not reach the
  bitstream\*\*: with them alone, ffprobe reports `color_space=bt709` and
  `color_primaries=unknown`, `color_transfer=unknown`. `-x264-params` is what
  lands all three in the VUI, and it leaves the decoded stream identical. A
  half-tagged file is worse than an untagged one — the player stops guessing
  the matrix but still guesses the primaries.

Why bother: untagged, the *player* picks its matrix by a height heuristic
(BT.601 below ~576 lines). Every shipped `an` example is 320x240 to 640x360,
so encode and playback agree by luck; at 1080p the same code would encode
with BT.601 and be displayed as BT.709, a silent, resolution-dependent colour
error. Pinning both sides to BT.709 makes them agree at every resolution.
This is a **one-time deliberate re-baseline** of every mp4 — cheap now,
because no ledger exists yet to invalidate.

### *exception* an.media.mp4.MediaError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A sink could not write what it was asked to. Carries actionable detail.

A renderer re-raises it as its own typed error at its boundary
(`frame_stage_renderer(..., error=...)`), so a cut-out render still fails
with `CutoutRenderError`.

### an.media.mp4.SUPPORTED_PIX_FMTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('yuv420p', 'yuv444p')*

a typo would reach ffmpeg
as an obscure failure minutes into a render, and a format outside this set
has not been measured against the panel.

* **Type:**
  The formats the knob accepts. Not an open string

### an.media.mp4.add_audio(video_path, audio_inputs, output_path, duration_s)

Mux a silence base + `audio_inputs` (path, delay_s) onto `video_path`.

Always emits an audio stream. `anullsrc` provides the silent base track
of length `duration_s` so concat across shots is safe; dialogue lines
are overlaid via `adelay` + `amix`. `duration_s` must be the
picture’s length (frames / fps): the concat advances each shot by its
container length, which is the longer of the two streams (an#195).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.media.mp4.check_pix_fmt(pix_fmt)

Resolve and validate the pixel format, or refuse with the whole list.

`None` resolves to [`DEFAULT_PIX_FMT`](#an.media.mp4.DEFAULT_PIX_FMT) **at call time**, which is what
lets the bench’s lever rebind the module global and reach this render.

Refuses an unknown format rather than passing it to ffmpeg: a typo would
otherwise surface minutes into a render as an obscure encoder error, and on
the second shot of a parallel render it would surface from a thread. A
format outside the list has also never been measured against the panel.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.media.mp4.ensure_ffmpeg()

Refuse before anything launches when ffmpeg is not on `PATH`.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.media.mp4.mux_frames(frames_dir, fps, output_mp4, pix_fmt=None)

Mux a PNG sequence to H.264 mp4.

`pix_fmt=None` means “whatever the module default is **right now**”, which
is what keeps the bench’s `pix_fmt` lever able to reach this call by
rebinding [`DEFAULT_PIX_FMT`](#an.media.mp4.DEFAULT_PIX_FMT). A caller that passes one wins; the bench
never passes one, so the lever reaches the encode AND the recorded
environment, and the two cannot disagree.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.media.mp4.mux_shot(frames_dir, shot, ctx, work_dir, output_mp4, , n_frames, pix_fmt=None)

Frames → the delivered per-shot mp4: a silent mux, then the audio mux.
Returns how many dialogue audio tracks were laid under the picture.

Every shot mp4 carries an AAC stream (silent if no dialogue) so the final
ffmpeg concat across heterogeneous shots works without surprises. The audio
is cut to the PICTURE’s length, `n_frames / fps`, not `shot.duration`:
a duration that is not a whole number of frames (2.6 s at 24 fps is 62.4)
gets `round(d * fps)` frames, and an audio track padded to `d` made the
shot’s container longer than its picture — the concat then advanced by the
container and left sub-frame holes in the film’s video timestamps, which
ffprobe reads as `r_frame_rate=120/1` (an#195).

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.media.mp4.stage_audio_inputs(shot, ctx, work_dir)

Write the shot’s per-dialogue audio bytes to disk and return (path, delay)s.

Looks up each `dialogue.audio_ref` in `mall["audio"]`. Lines without
an audio_ref or duration are skipped silently. Returns `[]` when no
audio is available, so the caller can use a video-only path.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]
