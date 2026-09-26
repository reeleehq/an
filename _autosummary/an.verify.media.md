# an.verify.media

Media verification helpers — audio + frame quality checks for rendered mp4s.

Phase 8 Tier 2. These complement the existing IR-only `LayoutLintVerifier`
by inspecting actual mp4 output: silence detection (catches cutoff dialogue),
audio level (catches missing audio), and per-frame perceptual diff via SSIM
(catches “all frames are identical” or “scene drifted between frames”).

Designed to depend only on `ffmpeg` / `ffprobe` and `numpy` (Pillow when
loading frames). No scikit-image, no opencv.

### Functions

| [`audio_volume`](#an.verify.media.audio_volume)(media_path)                        | Return dict with mean_db and max_db of the media's audio stream.               |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`detect_silence`](#an.verify.media.detect_silence)(media_path, \*[, noise_db, ...]) | Return `SilenceSpan``s in the audio of ``media_path` via ffmpeg.               |
| [`extract_frames`](#an.verify.media.extract_frames)(media_path, out_dir, \*[, ...])  | Extract frames from `media_path` at `fps` to `out_dir`.                        |
| [`ssim`](#an.verify.media.ssim)(a, b)                                      | A global-moment structural-similarity score between two single-channel images. |
| [`ssim_image_files`](#an.verify.media.ssim_image_files)(path_a, path_b)                | SSIM between two image files (any format Pillow can read).                     |
| [`transcribe`](#an.verify.media.transcribe)(media_path, \*[, model_size])        | Return the transcribed speech in `media_path`.                                 |

### Classes

| [`SilenceSpan`](#an.verify.media.SilenceSpan)(start, end)   | A contiguous run of near-silence inside an audio stream.   |
|----------------------------------------------------------------------------|------------------------------------------------------------|

### *class* an.verify.media.SilenceSpan(start, end)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A contiguous run of near-silence inside an audio stream.

### an.verify.media.audio_volume(media_path)

Return dict with mean_db and max_db of the media’s audio stream.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.verify.media.detect_silence(media_path, , noise_db=-30.0, min_duration_s=0.3)

Return `SilenceSpan``s in the audio of ``media_path` via ffmpeg.

Wraps `ffmpeg -af silencedetect=...` and parses the stderr “silence_start”
/ “silence_end” lines. Useful for catching dialogue that got cut off
(silence at the start/end of a shot when speech was expected).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`SilenceSpan`](#an.verify.media.SilenceSpan)]

### an.verify.media.extract_frames(media_path, out_dir, , fps=4.0, pattern='frame_%04d.png')

Extract frames from `media_path` at `fps` to `out_dir`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### an.verify.media.ssim(a, b)

A global-moment structural-similarity score between two single-channel images.

**Not Wang et al.’s SSIM**, despite what this docstring said for a long
time: that estimator is computed over sliding local windows, and this one
uses one global mean, variance and covariance per image. The formula is the
same; the reduction is not, and the difference is the whole behaviour.
Global moments are blind to a small local change — a total eye-blink scores
0.9989 here — because the flat fill that is most of a cutout frame drags
the mean to 1.0.

That blindness is *fine for what this function is used for*: catching a
frozen render, where every pixel is identical or none is. It is not fine as
a quality metric, which is why [`an.bench.metrics.ssim_map()`](an.bench.metrics.md#an.bench.metrics.ssim_map) exists
beside it rather than replacing it — `MediaQualityVerifier`’s frozen-render
threshold was tuned against this reduction, and that verifier is in the
default orchestrate chain.

Inputs are float arrays in [0, 1]. Returns a float in roughly `[-1, 1]`;
1 means identical.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> import numpy as np
>>> x = np.zeros((8, 8), dtype=np.float32)
>>> ssim(x, x)
1.0
```

### an.verify.media.ssim_image_files(path_a, path_b)

SSIM between two image files (any format Pillow can read).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.verify.media.transcribe(media_path, , model_size='tiny')

Return the transcribed speech in `media_path`.

Lazily imports faster-whisper. Raises `RuntimeError` with a clear
message when the package isn’t installed.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
