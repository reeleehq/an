# an.audio.injectable_lipsync

Lip-sync provider that consumes pre-computed word timings.

Useful when an upstream system already has authoritative word-level
timings and would otherwise force `an` to re-transcribe the same
audio. The canonical case is `muvid`, where the lyric → audio
alignment store (`lacing`) is the SSOT and re-running
`WhisperLipSync` on the audio produces a redundant (and possibly
divergent) word-timestamp set.

Two pieces:

- [`StaticWordTimings`](#an.audio.injectable_lipsync.StaticWordTimings) — a `WordTimingProvider` over a
  fixed list of `(word, start, end)` tuples.
- [`WordTimingsLipSync`](#an.audio.injectable_lipsync.WordTimingsLipSync) — a `LipSyncProvider` that reads
  from any `WordTimingProvider` and runs the same
  word→viseme conversion as `WhisperLipSync` (via
  `word_timings_to_visemes()`), so output is shape-compatible with
  > the rest of the cutout pipeline.

Drop-in usage:

```default
from an.audio.injectable_lipsync import (
    StaticWordTimings, WordTimingsLipSync,
)

timings = [("hello", 0.5, 1.0), ("world", 1.2, 1.8)]
lipsync = WordTimingsLipSync(StaticWordTimings(timings))
track = lipsync.align(audio_clip, "hello world")
```

### Classes

| [`StaticWordTimings`](#an.audio.injectable_lipsync.StaticWordTimings)(words, \*[, label])   | A `WordTimingProvider` over a fixed list of timings.   |
|------------------------------------------------------------------------------------------|--------------------------------------------------------|
| [`WordTimingsLipSync`](#an.audio.injectable_lipsync.WordTimingsLipSync)(provider, \*[, ...]) | `LipSyncProvider` driven by a `WordTimingProvider`.    |

### *class* an.audio.injectable_lipsync.StaticWordTimings(words, , label='static')

Bases: `object`

A `WordTimingProvider` over a fixed list of timings.

### *class* an.audio.injectable_lipsync.WordTimingsLipSync(provider, , char_to_viseme=None, convention='rhubarb', rest_viseme='X', min_gap_for_rest=0.2)

Bases: `object`

`LipSyncProvider` driven by a `WordTimingProvider`.

Skips transcription entirely. Use this when the caller already has
authoritative word timings (e.g. from a separate lyric-alignment
pipeline).

* **Parameters:**
  * **provider** ([`WordTimingProvider`](an.audio.lipsync.md#an.audio.lipsync.WordTimingProvider)) – any `WordTimingProvider`.
  * **char_to_viseme** (`dict`[`str`, `str`] | `None`) – optional override of the character→viseme code
    mapping; defaults to the one shared with
    `OfflineLipSync` / `WhisperLipSync`.
  * **convention** (`str`) – declared viseme convention string for the produced
    track. Defaults to `"rhubarb"` for compatibility with the
    existing cutout adapter.
  * **rest_viseme** (`str`) – code emitted in silent gaps. Defaults to
    `_REST_VISEME`.
  * **min_gap_for_rest** (`float`) – minimum inter-word silence (seconds) before
    we insert a rest keyframe. Defaults to `0.20`.

#### emits_word_timings *: bool* *= True*

Built from words, so the track carries them (an#96).
