# an.audio.loudness

Voice loudness: one integrated loudness for every voice of a film (an#315).

TTS providers deliver voices at very different levels — measured on a four-voice
ElevenLabs episode: -16.4, -35.5, -28.4 and -23.4 LUFS, a 19 dB spread that left
one character barely audible. `meta.voice_loudness` ([`VoiceLoudness`](an.ir.schema.html.md#an.ir.schema.VoiceLoudness))
asks for one level for all of them:

- each voice’s integrated loudness (EBU R128 / ITU-R BS.1770, measured by
  ffmpeg’s `ebur128` over ALL of that voice’s lines in the film, back to
  back: a 0.6 s line has a single 400 ms gating block, and a voice’s own
  dynamics between lines — a whisper, a shout — are kept);
- ONE gain per voice, `target - measured` plus the voice document’s
  `loudness_offset_db`, rounded to [`GAIN_STEP_DB`](#an.audio.loudness.GAIN_STEP_DB), then a lookahead
  peak limiter at `peak_db` ([`limit_peaks()`](#an.audio.loudness.limit_peaks): a sample never passes the
  ceiling, and the gain eases into and out of a peak rather than clipping);
- the result is DERIVED audio, content-keyed in the `audio` store by
  (the line’s audio, the gain, the ceiling, [`LEVEL_VERSION`](#an.audio.loudness.LEVEL_VERSION)) — never a
  re-synthesis, never billed — and the line is stamped with it, so the
  per-shot mux, the film mix and every cache key follow it. The gain changes
  no timing: lip-sync, word timings and durations are the source line’s.

A voice whose lines are silence (the offline provider) is left as it is. A
voice whose lines are all short is measured looped ([`MIN_MEASURE_S`](#an.audio.loudness.MIN_MEASURE_S)).
The gain is capped at [`MAX_GAIN_DB`](#an.audio.loudness.MAX_GAIN_DB), and a voice that ends more than
[`MISS_WARNING_DB`](#an.audio.loudness.MISS_WARNING_DB) from its target (capped, or held down by its peaks) is
warned about. `peak_db` is a SAMPLE-peak ceiling: an AAC encode can still
overshoot it between samples by a fraction of a dB, so keep a margin.

The gain and the source are stamped on each line (`Dialogue.leveled`): a
render whose voice is unchanged reuses them without decoding or measuring
anything, and a re-measure that moves the gain by less than a step keeps the
previous gain (hysteresis), so one new line rarely re-renders a voice’s other
shots.
Without a target, [`loudness_report()`](#an.audio.loudness.loudness_report) measures the voices and
[`voice_loudness_spread()`](#an.audio.loudness.voice_loudness_spread) says when they differ by more than
[`SPREAD_WARNING_DB`](#an.audio.loudness.SPREAD_WARNING_DB) — the render warns, naming each voice’s level.

The measuring and the limiter are the fleet’s shared loudness component,
`mixing.loudness` (an#563; `mixing` is a core dependency since an#611):
`mixing.loudness.level_group()` measures a voice’s lines back to back (looped
to [`MIN_MEASURE_S`](#an.audio.loudness.MIN_MEASURE_S), channels kept when they agree) and caps the gain, with
ffmpeg’s `ebur128` injected as its meter ([`METER`](#an.audio.loudness.METER)) so `an` takes no
scipy; `mixing.loudness.limit_peaks()` is the limiter, moved there unchanged
(so [`LEVEL_VERSION`](#an.audio.loudness.LEVEL_VERSION) did not move, and a test pins the leveled bytes).
What stays here is `an`’s own: the voices, the offsets, the hysteresis, the
makeup pass and the content keys. A `mixing` too old to have
`mixing.loudness` raises [`VoiceLoudnessError`](#an.audio.loudness.VoiceLoudnessError) telling the user to
upgrade it ([`an.audio.shared_mixing.mixing_too_old()`](an.audio.shared_mixing.html.md#an.audio.shared_mixing.mixing_too_old), an#621).

### Module Attributes

| [`LEVEL_VERSION`](#an.audio.loudness.LEVEL_VERSION)     | Bumped whenever a leveled line's bytes would change for the same inputs (the limiter, its window, the encoding); part of every leveled line's key.                                                                                  |
|--------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`GAIN_STEP_DB`](#an.audio.loudness.GAIN_STEP_DB)      | A voice's gain is rounded to this, so a new line that moves its voice's loudness by less than half of it re-renders nothing else (half a dB is below what a listener hears between two lines; the measurement itself is to 0.1 LU). |
| [`SILENCE_LUFS`](#an.audio.loudness.SILENCE_LUFS)      | never leveled.                                                                                                                                                                                                                      |
| [`SPREAD_WARNING_DB`](#an.audio.loudness.SPREAD_WARNING_DB) | Voices further apart than this, with no target set, are warned about.                                                                                                                                                               |
| [`LIMITER_WINDOW_S`](#an.audio.loudness.LIMITER_WINDOW_S)  | the gain eases into a peak and back out over this much on each side, so nothing below ~20 Hz is modulated within a cycle (a 5 ms release distorted anything under 100 Hz, an#315 review).                                           |
| [`MAX_GAIN_DB`](#an.audio.loudness.MAX_GAIN_DB)       | The largest gain leveling gives a voice; beyond it the voice is mostly noise (room tone measured at -62 LUFS asked for +46 dB).                                                                                                     |
| [`OFFSET_LIMITS_DB`](#an.audio.loudness.OFFSET_LIMITS_DB)  | `loudness_offset_db` bounds on a voice document.                                                                                                                                                                                    |
| [`MIN_MEASURE_S`](#an.audio.loudness.MIN_MEASURE_S)     | EBU R128 gates in 400 ms blocks, and a voice of only short lines would read as silence.                                                                                                                                             |
| [`MISS_WARNING_DB`](#an.audio.loudness.MISS_WARNING_DB)   | A leveled voice that ends further than this from its target (the limiter held its peaks, or the gain was capped) is warned about.                                                                                                   |
| [`METER`](#an.audio.loudness.METER)             | The loudness meter injected into `mixing.loudness` (one of its `METERS`): ffmpeg's `ebur128`, so `an` needs no scipy for its numpy meter.                                                                                           |

### Functions

| [`group_loudness`](#an.audio.loudness.group_loudness)(pcms)                        | The integrated loudness of a voice's lines, measured back to back.                                                                                                                                                                                                                                                          |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`integrated_loudness`](#an.audio.loudness.integrated_loudness)(pcm)                    | EBU R128 integrated loudness (LUFS) of `pcm`, by [`METER`](#an.audio.loudness.METER) through `mixing.loudness.integrated_lufs()` (`-inf` for silence).                                                                                                                                                   |
| [`level_voices`](#an.audio.loudness.level_voices)(scene, mall, spec)             | Level every voice of `scene` to `spec` ([`VoiceLoudness`](an.ir.schema.html.md#an.ir.schema.VoiceLoudness)): each line is stamped with its leveled audio (made once per source bytes, gain and ceiling, in the `audio` store) and `Dialogue.leveled`.                                                |
| [`leveled_audio`](#an.audio.loudness.leveled_audio)(audio, \*, gain_db, peak_db)  | `audio` at `gain_db`, its peaks held at `peak_db` dBFS, as a 16-bit PCM WAV of exactly the length of the decoded source (an MP3 source is stored decoded, as the mux would decode it).                                                                                                                                      |
| [`leveled_key`](#an.audio.loudness.leveled_key)(source, \*, gain_db, peak_db)   | The content key of a leveled line: the sha256 of its source audio's BYTES (not the request that made them: a take re-synthesised under the same request is other audio, an#315 review), the gain, the ceiling, the rate a non-WAV source is decoded at, and [`LEVEL_VERSION`](#an.audio.loudness.LEVEL_VERSION). |
| [`limit_peaks`](#an.audio.loudness.limit_peaks)(samples, \*, ceiling[, window]) | `samples` with no sample above `ceiling` (absolute, full scale 1.0): `mixing.loudness.limit_peaks()` (sample peak), the lookahead limiter that moved there unchanged from here (an#563).                                                                                                                                    |
| [`loudness_report`](#an.audio.loudness.loudness_report)(scene, mall)                | Every voice's integrated loudness over its lines, as heard now (a leveled line's leveled audio).                                                                                                                                                                                                                            |
| [`voice_loudness_spread`](#an.audio.loudness.voice_loudness_spread)(levels)               | What to say when the audible voices differ by more than [`SPREAD_WARNING_DB`](#an.audio.loudness.SPREAD_WARNING_DB); `None` otherwise.                                                                                                                                                                               |
| [`voiced_lines`](#an.audio.loudness.voiced_lines)(scene, mall)                   | `{voice id: [line, ...]}` for every line with audio in the store.                                                                                                                                                                                                                                                           |
| [`voiced_sources`](#an.audio.loudness.voiced_sources)(scene, mall)                 | [`voiced_lines()`](#an.audio.loudness.voiced_lines), by each line's SOURCE audio (a leveled line's own).                                                                                                                                                                                                        |

### Classes

| [`VoiceLevel`](#an.audio.loudness.VoiceLevel)(voice, lufs[, gain_db, lines])   | One voice's measured loudness, and the gain leveling gives it.   |
|----------------------------------------------------------------------------------------------|------------------------------------------------------------------|

### Exceptions

| [`VoiceLoudnessError`](#an.audio.loudness.VoiceLoudnessError)   | The voices cannot be measured or leveled (no ffmpeg, an unreadable line).                                             |
|-----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| [`VoiceLoudnessWarning`](#an.audio.loudness.VoiceLoudnessWarning) | The film's voices differ in loudness by more than [`SPREAD_WARNING_DB`](#an.audio.loudness.SPREAD_WARNING_DB). |

### an.audio.loudness.GAIN_STEP_DB *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

A voice’s gain is rounded to this, so a new line that moves its voice’s
loudness by less than half of it re-renders nothing else (half a dB is
below what a listener hears between two lines; the measurement itself is
to 0.1 LU).

### an.audio.loudness.LEVEL_VERSION *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

Bumped whenever a leveled line’s bytes would change for the same inputs
(the limiter, its window, the encoding); part of every leveled line’s key.
A test pins the leveled output to it.

### an.audio.loudness.LIMITER_WINDOW_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.05*

the gain eases into a peak
and back out over this much on each side, so nothing below ~20 Hz is
modulated within a cycle (a 5 ms release distorted anything under 100 Hz,
an#315 review).

* **Type:**
  The limiter’s lookahead and release, seconds

### an.audio.loudness.MAX_GAIN_DB *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 24.0*

The largest gain leveling gives a voice; beyond it the voice is mostly
noise (room tone measured at -62 LUFS asked for +46 dB). Capped, and warned.

### an.audio.loudness.METER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'ffmpeg_ebur128'*

The loudness meter injected into `mixing.loudness` (one of its
`METERS`): ffmpeg’s `ebur128`, so `an` needs no scipy for its numpy meter.

### an.audio.loudness.MIN_MEASURE_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1.0*

EBU R128 gates
in 400 ms blocks, and a voice of only short lines would read as silence.

* **Type:**
  A voice shorter than this is measured looped to this length

### an.audio.loudness.MISS_WARNING_DB *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1.0*

A leveled voice that ends further than this from its target (the limiter
held its peaks, or the gain was capped) is warned about.

### an.audio.loudness.OFFSET_LIMITS_DB *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= (-12.0, 12.0)*

`loudness_offset_db` bounds on a voice document.

### an.audio.loudness.SILENCE_LUFS *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= -70.0*

never leveled.

* **Type:**
  Below this a voice is silence (BS.1770’s absolute gate)

### an.audio.loudness.SPREAD_WARNING_DB *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 6.0*

Voices further apart than this, with no target set, are warned about.

### *class* an.audio.loudness.VoiceLevel(voice, lufs, gain_db=0.0, lines=0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One voice’s measured loudness, and the gain leveling gives it.

### *exception* an.audio.loudness.VoiceLoudnessError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The voices cannot be measured or leveled (no ffmpeg, an unreadable line).

### *exception* an.audio.loudness.VoiceLoudnessWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

The film’s voices differ in loudness by more than [`SPREAD_WARNING_DB`](#an.audio.loudness.SPREAD_WARNING_DB).

### an.audio.loudness.group_loudness(pcms)

The integrated loudness of a voice’s lines, measured back to back.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.audio.loudness.integrated_loudness(pcm)

EBU R128 integrated loudness (LUFS) of `pcm`, by [`METER`](#an.audio.loudness.METER) through
`mixing.loudness.integrated_lufs()` (`-inf` for silence).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.audio.loudness.level_voices(scene, mall, spec)

Level every voice of `scene` to `spec` ([`VoiceLoudness`](an.ir.schema.html.md#an.ir.schema.VoiceLoudness)):
each line is stamped with its leveled audio (made once per source bytes,
gain and ceiling, in the `audio` store) and `Dialogue.leveled`.
Returns each voice’s level; warns ([`VoiceLoudnessWarning`](#an.audio.loudness.VoiceLoudnessWarning)) about a
voice it had to cap or could not bring within [`MISS_WARNING_DB`](#an.audio.loudness.MISS_WARNING_DB).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`VoiceLevel`](#an.audio.loudness.VoiceLevel)]

### an.audio.loudness.leveled_audio(audio, , gain_db, peak_db)

`audio` at `gain_db`, its peaks held at `peak_db` dBFS, as a 16-bit
PCM WAV of exactly the length of the decoded source (an MP3 source is
stored decoded, as the mux would decode it).

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.audio.loudness.leveled_key(source, , gain_db, peak_db)

The content key of a leveled line: the sha256 of its source audio’s
BYTES (not the request that made them: a take re-synthesised under the
same request is other audio, an#315 review), the gain, the ceiling, the
rate a non-WAV source is decoded at, and [`LEVEL_VERSION`](#an.audio.loudness.LEVEL_VERSION).

```pycon
>>> leveled_key(b"a", gain_db=1.0, peak_db=-1.5) != leveled_key(b"a", gain_db=1.1, peak_db=-1.5)
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.loudness.limit_peaks(samples, , ceiling, window=1)

`samples` with no sample above `ceiling` (absolute, full scale 1.0):
`mixing.loudness.limit_peaks()` (sample peak), the lookahead limiter
that moved there unchanged from here (an#563).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.audio.loudness.loudness_report(scene, mall)

Every voice’s integrated loudness over its lines, as heard now (a
leveled line’s leveled audio).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`VoiceLevel`](#an.audio.loudness.VoiceLevel)]

### an.audio.loudness.voice_loudness_spread(levels)

What to say when the audible voices differ by more than
[`SPREAD_WARNING_DB`](#an.audio.loudness.SPREAD_WARNING_DB); `None` otherwise.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.loudness.voiced_lines(scene, mall)

`{voice id: [line, ...]}` for every line with audio in the store.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.audio.loudness.voiced_sources(scene, mall)

[`voiced_lines()`](#an.audio.loudness.voiced_lines), by each line’s SOURCE audio (a leveled line’s own).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]
