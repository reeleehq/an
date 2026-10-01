# an.audio.lipsync

Lip-sync provider protocol + viseme dataclasses.

Viseme conventions are renderer-agnostic in the IR; concrete providers in
later phases (Rhubarb, Azure, MFA) emit their own letter/number encodings,
which the cutout adapter then maps to mouth-slot attachments.

Two protocols live here:

- [`LipSyncProvider`](#an.audio.lipsync.LipSyncProvider) — the head-to-toe pipeline (“audio + transcript
  → visemes”). Owns its own transcription if it needs one. Most cutout
  callers go through this.
- [`WordTimingProvider`](#an.audio.lipsync.WordTimingProvider) — the narrower “audio → word timings”
  contract. Lets external callers (e.g. `muvid`, with its own lyric
  alignment store) skip a redundant transcription pass and feed timings
  directly into `WordTimingsLipSync`.

### Module Attributes

| [`WordTiming`](#an.audio.lipsync.WordTiming)   | One word's slice in time.   |
|---------------------------------------------------------------|-----------------------------|

### Functions

| [`word_timings_to_visemes`](#an.audio.lipsync.word_timings_to_visemes)(words, \*, ...[, ...])   | Distribute viseme keyframes across word boundaries.   |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------|

### Classes

| [`LipSyncProvider`](#an.audio.lipsync.LipSyncProvider)(\*args, \*\*kwargs)               | Audio + transcript → aligned viseme track.             |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------|
| [`Viseme`](#an.audio.lipsync.Viseme)(time, code[, intensity])                   | A single mouth-shape keyframe.                         |
| [`VisemeTrack`](#an.audio.lipsync.VisemeTrack)([visemes, convention, duration, ...]) | Aligned viseme sequence produced by a LipSyncProvider. |
| [`WordTimingProvider`](#an.audio.lipsync.WordTimingProvider)(\*args, \*\*kwargs)            | Audio → `[(word, start_s, end_s), ...]`.               |

### *class* an.audio.lipsync.LipSyncProvider(\*args, \*\*kwargs)

Bases: `Protocol`

Audio + transcript → aligned viseme track.

A provider that fills `VisemeTrack.words` also declares
`emits_word_timings = True` (a plain class attribute, absent means
False). The audio pipeline reads it to decide whether a line whose
`word_timings` are missing needs re-alignment — without the flag, a
provider that cannot supply words would re-align every line forever.

#### align(audio, transcript)

Produce a viseme track for `audio` given its `transcript`.

* **Return type:**
  [`VisemeTrack`](#an.audio.lipsync.VisemeTrack)

### *class* an.audio.lipsync.Viseme(time, code, intensity=1.0)

Bases: `object`

A single mouth-shape keyframe.

### *class* an.audio.lipsync.VisemeTrack(visemes=<factory>, convention='rhubarb', duration=0.0, words=None)

Bases: `object`

Aligned viseme sequence produced by a LipSyncProvider.

`words` carries the word timings the provider aligned from, when it had
any (whisper, [`WordTimingsLipSync`](an.audio.injectable_lipsync.md#an.audio.injectable_lipsync.WordTimingsLipSync));
`None` for providers that never see words (offline, Rhubarb — whose JSON
is mouth cues only). Retained since an#96 rather than discarded after the
viseme conversion: captions (Wave 8) and any consumer that wants to know
*which word* a mouth shape belongs to read them from the IR.

### an.audio.lipsync.WordTiming

One word’s slice in time. Tuple form keeps providers cheap.

alias of `tuple`[`str`, `float`, `float`]

### *class* an.audio.lipsync.WordTimingProvider(\*args, \*\*kwargs)

Bases: `Protocol`

Audio → `[(word, start_s, end_s), ...]`.

Implementations may run a transcriber (Whisper / Scribe) or look up
pre-computed timings (`muvid`’s lacing store). Returned tuples are
expected to be in ascending start-time order; gaps between words are
fine and represent silence the lipsync provider should rest through.

#### words_for(audio, , transcript='')

Return the word timings for `audio`.

* **Return type:**
  `Sequence`[`tuple`[`str`, `float`, `float`]]

### an.audio.lipsync.word_timings_to_visemes(words, , total_duration, char_to_viseme, rest_viseme='X', min_gap_for_rest=0.2)

Distribute viseme keyframes across word boundaries.

Used by `WhisperLipSync` and `WordTimingsLipSync`. The
algorithm: per word, walk its characters in order, look up each
character’s viseme code, dedupe consecutive identical codes, and
space the resulting keyframes evenly across the word’s
`[start, end]` interval. In gaps wider than `min_gap_for_rest` —
between two words, or after the last one before `total_duration` —
insert a single rest keyframe just after the previous word ended.

Times are clamped to `[0, total_duration]` since some
transcribers occasionally round the last word’s end past the
audio’s actual length.

* **Return type:**
  `list`[[`Viseme`](#an.audio.lipsync.Viseme)]
