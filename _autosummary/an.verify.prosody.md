# an.verify.prosody

Prosody measurement: how a recorded voice delivers its words, as numbers a target can check.

“Read it like a deadpan narrator” is only checkable if the delivery is a set of
numbers. This module measures one spoken clip — a synthesized dialogue line, a
narration take, a reference recording studied privately — and compares the
measurement to `[low, high]` targets, the way `an.verify.style` does for
a render’s cadence. It knows nothing about characters, faces or genres: any
narrated video (cut-out, data-viz, math-viz) has a voice to measure.

What is measured ([`METRICS`](#an.verify.prosody.METRICS) is the vocabulary a target may use):

- **Rate.** `articulation_rate_sps` — syllables per second of *speaking* time
  (pauses excluded), and `speech_rate_sps` — syllables per second of the whole
  clip from first to last sound. Syllables come from the `text` when given
  ([`count_syllables()`](#an.verify.prosody.count_syllables), an English vowel-group estimate); without a text both
  rates are `nan`.
- **Pauses.** A pause is a run of non-speech frames of at least
  `min_pause_s` between two stretches of speech (the clip’s own leading and
  trailing silence never count). `pause_share` is pause time over the clip’s
  span; `pauses_per_min`, `pause_median_s` and `pause_p90_s` describe the
  pauses themselves. A frame is speech when its level is within
  `speech_floor_db` of the clip’s 95th-percentile level.
- **Pitch.** A YIN fundamental-frequency track (de Cheveigné & Kawahara 2002)
  on speech frames. Movement is reported in \*\*semitones about the clip’s own
  median\*\*, so a target transfers between a low and a high voice:
  `f0_sd_st` (spread), `f0_range_st` (5th to 95th percentile), and
  `final_drop_st` — per phrase (speech between pauses of at least
  `phrase_pause_s`), the median pitch of the phrase’s last quarter minus the
  phrase’s median, then the median over phrases: negative is a falling ending
  (a flat, final statement), positive a rising one (a question, a setup that
  is not finished). `f0_median_hz` is reported for reference, and
  `register_st` — the clip’s median pitch in semitones above (or below) a
  `reference_hz` the caller passes, typically the same voice’s neutral
  median — measures a register jump (a character voice, an outburst); it is
  `nan` without a reference.
- **Loudness.** `loudness_range_db`: the 90th minus the 10th percentile of
  the speech frames’ level.
- **Emphasis.** `emphasis_per_s`: syllable-rate peaks of the level envelope
  that stand out — at least `emphasis_db` above the clip’s median speech level
  or `emphasis_st` above its median pitch — per second of speaking time.

**Lines, not performances.** Targets measured per sentence (a range of
per-sentence values) are compared with the median over a set of lines, each
measured alone ([`measure_lines()`](#an.verify.prosody.measure_lines), the CLI’s default for several files):
joining lines first spreads the pitch statistics by the register changes
between them.

These are estimators, crude on purpose: numpy only, no model, deterministic.
A target measured with them is only comparable to a clip measured with them,
so change an estimator only together with re-measuring the targets that use it.

The core is a pure function over samples, testable without ffmpeg:

```pycon
>>> import numpy as np
>>> sr = 16000
>>> t = np.arange(int(0.5 * sr)) / sr
>>> tone = 0.3 * np.sin(2 * np.pi * 150 * t)
>>> clip = np.concatenate([tone, np.zeros(int(0.4 * sr)), tone])
>>> m = measure_prosody(clip, sr, text="one two")
>>> round(m.f0_median_hz), m.pauses, round(m.pause_median_s, 2)
(150, 1, 0.4)
>>> m.syllables, round(m.articulation_rate_sps, 1)
(2, 2.0)
```

A target is a `[low, high]` range; a miss is a warning, and a target nothing
measures is refused:

```pycon
>>> check_prosody(m, {"pauses_per_min": [0, 200]})
[]
>>> check_prosody(m, {"pauses_per_min": [0, 10]})[0].ir_path
'<prosody>/pauses_per_min'
>>> check_prosody(m, {"swagger": [0, 1]})
Traceback (most recent call last):
...
an.verify.prosody.ProsodyTargetError: unknown prosody target 'swagger'; measurable targets are [...]
```

### Module Attributes

| [`ESTIMATOR_VERSION`](#an.verify.prosody.ESTIMATOR_VERSION)   | Raised whenever an estimator or one of its defaults below changes what a clip measures.   |
|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| [`METRICS`](#an.verify.prosody.METRICS)             | The measurable targets, and what each one is.                                             |

### Functions

| [`measure_prosody`](#an.verify.prosody.measure_prosody)(samples, sr, \*[, text, ...])   | Measure one clip's delivery (see the module docstring for each metric).                                                                                                                                       |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`measure_prosody_file`](#an.verify.prosody.measure_prosody_file)(paths, \*[, text, sr])     | Measure one audio file, or several joined by [`join_speech()`](#an.verify.prosody.join_speech) (one performance).                                                                                |
| [`measure_lines`](#an.verify.prosody.measure_lines)(paths, \*[, texts, sr])           | Measure each file on its own (with its own text) and return the [`median_stats()`](#an.verify.prosody.median_stats) — the comparison for targets measured per sentence.                           |
| [`median_stats`](#an.verify.prosody.median_stats)(stats)                             | The per-field median of several clips' stats (`nan` ignored); counts and durations are summed.                                                                                                                |
| [`pitch_track`](#an.verify.prosody.pitch_track)(samples, sr, \*[, fmin, fmax, ...]) | A YIN pitch track: Hz per hop, `nan` where no period is found.                                                                                                                                                |
| [`count_syllables`](#an.verify.prosody.count_syllables)(text)                           | An English syllable estimate: vowel groups per word, a silent final `e` dropped, at least one per word; a number counts one per digit.                                                                        |
| [`join_speech`](#an.verify.prosody.join_speech)(clips, sr, \*[, gap_s, ...])        | Clips with their leading and trailing silence trimmed, joined with `gap_s` of silence — so a set of lines measures as one performance without the authored gaps between lines counting as the voice's pauses. |
| [`decode_audio`](#an.verify.prosody.decode_audio)(path, \*[, sr, ffmpeg])            | Any audio file ffmpeg reads, as mono float32 samples at `sr` Hz.                                                                                                                                              |
| [`check_prosody`](#an.verify.prosody.check_prosody)(stats, targets, \*[, ...])        | One finding per target `stats` misses (an `info` for one it cannot measure).                                                                                                                                  |
| [`target_distance`](#an.verify.prosody.target_distance)(stats, targets, \*[, ...])      | How far `stats` sits from `targets`: `(outside, off_centre)`, lower is closer.                                                                                                                                |
| [`validate_targets`](#an.verify.prosody.validate_targets)(targets)                       | Raise [`ProsodyTargetError`](#an.verify.prosody.ProsodyTargetError) unless every target names a metric and is a `[low, high]` range.                                                                    |
| [`prosody_lint`](#an.verify.prosody.prosody_lint)(audio, targets, \*[, text, ...])   | Measure `audio` (a path, several paths, or stats already measured) and report each target it misses.                                                                                                          |

### Classes

| [`ProsodyStats`](#an.verify.prosody.ProsodyStats)(duration_s, span_s, speech_s, ...)   | One clip's delivery, in the units [`METRICS`](#an.verify.prosody.METRICS) describes.   |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|

### Exceptions

| [`ProsodyTargetError`](#an.verify.prosody.ProsodyTargetError)   | A prosody target names no metric, or is not a `[low, high]` range.   |
|-----------------------------------------------------------------------|----------------------------------------------------------------------|
| [`ProsodyDecodeError`](#an.verify.prosody.ProsodyDecodeError)   | An audio file could not be decoded (ffmpeg missing or failing).      |

### an.verify.prosody.ESTIMATOR_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '1'*

Raised whenever an estimator or one of its defaults below changes what a clip
measures. Anything that persists a choice made from these numbers (the best
take of a line, [`an.audio.takes`](an.audio.takes.md#module-an.audio.takes)) keys on it, so a changed estimator
re-chooses instead of trusting numbers it would no longer produce.

### an.verify.prosody.METRICS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'articulation_rate_sps': 'syllables per second of speaking time (needs the text)', 'emphasis_per_s': 'stand-out level peaks per second of speaking time', 'f0_median_hz': 'median pitch (voice-specific; for reference)', 'f0_range_st': 'pitch range, 5th to 95th percentile, semitones', 'f0_sd_st': 'pitch spread, semitones about the median', 'final_drop_st': 'median phrase ending relative to its phrase, semitones (negative falls)', 'loudness_range_db': 'speech level, 90th minus 10th percentile, dB', 'pause_median_s': 'median pause length', 'pause_p90_s': '90th-percentile pause length', 'pause_share': 'share of the span that is pauses', 'pauses_per_min': 'pauses per minute of span', 'register_st': 'median pitch relative to reference_hz, semitones (needs a reference)', 'speech_rate_sps': "syllables per second of the clip's span (needs the text)", 'voiced_share': 'share of speaking time with a pitch'}*

The measurable targets, and what each one is.

### *exception* an.verify.prosody.ProsodyDecodeError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

An audio file could not be decoded (ffmpeg missing or failing).

### *class* an.verify.prosody.ProsodyStats(duration_s, span_s, speech_s, syllables, pauses, articulation_rate_sps, speech_rate_sps, pause_share, pauses_per_min, pause_median_s, pause_p90_s, f0_median_hz, f0_sd_st, f0_range_st, final_drop_st, loudness_range_db, emphasis_per_s, voiced_share, register_st=nan)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One clip’s delivery, in the units [`METRICS`](#an.verify.prosody.METRICS) describes.

`nan` means “not measurable on this clip” (no text for a rate, no pause
for a pause length, no voiced phrase for a contour).

#### as_dict(, ndigits=3)

The stats as a plain dict, floats rounded (`nan` becomes `None`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *exception* an.verify.prosody.ProsodyTargetError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A prosody target names no metric, or is not a `[low, high]` range.

### an.verify.prosody.check_prosody(stats, targets, , miss_severity='warning', path_prefix='<prosody>')

One finding per target `stats` misses (an `info` for one it cannot measure).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Finding`](an.verify.md#an.verify.Finding)]

### an.verify.prosody.count_syllables(text)

An English syllable estimate: vowel groups per word, a silent final `e`
dropped, at least one per word; a number counts one per digit.

Bracketed audio tags (`[sighs]`) are not words and are skipped.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> count_syllables("He did not do the job.")
6
>>> count_syllables("[deadpan] Forty-seven criteria.")  # truly 8: an estimate
7
```

### an.verify.prosody.decode_audio(path, , sr=16000, ffmpeg='ffmpeg')

Any audio file ffmpeg reads, as mono float32 samples at `sr` Hz.

* **Return type:**
  `ndarray`

### an.verify.prosody.join_speech(clips, sr, , gap_s=0.0, speech_floor_db=30.0, hop_s=0.01, window_s=0.025)

Clips with their leading and trailing silence trimmed, joined with `gap_s`
of silence — so a set of lines measures as one performance without the
authored gaps between lines counting as the voice’s pauses.

* **Return type:**
  `ndarray`

```pycon
>>> sr = 1000
>>> c = np.concatenate([np.zeros(200), np.ones(300), np.zeros(200)])
>>> 0.6 <= len(join_speech([c, c], sr)) / sr < 0.7  # edges blur by one window
True
```

### an.verify.prosody.measure_lines(paths, , texts=None, sr=16000, \*\*knobs)

Measure each file on its own (with its own text) and return the
[`median_stats()`](#an.verify.prosody.median_stats) — the comparison for targets measured per sentence.

* **Return type:**
  [`ProsodyStats`](#an.verify.prosody.ProsodyStats)

### an.verify.prosody.measure_prosody(samples, sr, , text=None, hop_s=0.01, window_s=0.025, fmin=60.0, fmax=500.0, speech_floor_db=30.0, min_pause_s=0.12, phrase_pause_s=0.25, emphasis_db=6.0, emphasis_st=3.0, peak_gap_s=0.12, final_share=0.25, reference_hz=None)

Measure one clip’s delivery (see the module docstring for each metric).

`samples` is mono audio at `sr` Hz (any scale); `text` is what is said,
used only to count syllables for the two rates; `reference_hz` is the pitch
`register_st` is measured from.

* **Return type:**
  [`ProsodyStats`](#an.verify.prosody.ProsodyStats)

### an.verify.prosody.measure_prosody_file(paths, , text=None, sr=16000, \*\*knobs)

Measure one audio file, or several joined by [`join_speech()`](#an.verify.prosody.join_speech) (one
performance). `text` is the words of all of them together.

Joining moves the pitch statistics: each line has its own register, so a
joined set spreads wider than any of its lines. To compare lines with
per-sentence targets, use [`measure_lines()`](#an.verify.prosody.measure_lines).

* **Return type:**
  [`ProsodyStats`](#an.verify.prosody.ProsodyStats)

### an.verify.prosody.median_stats(stats)

The per-field median of several clips’ stats (`nan` ignored); counts
and durations are summed. How a set of lines is compared with targets
measured per sentence.

* **Return type:**
  [`ProsodyStats`](#an.verify.prosody.ProsodyStats)

```pycon
>>> a = ProsodyStats(1.0, 1.0, 1.0, 3, 0, *[1.0] * 13)
>>> b = ProsodyStats(2.0, 2.0, 2.0, 5, 1, *[3.0] * 13)
>>> m = median_stats([a, b])
>>> m.f0_sd_st, m.syllables, m.span_s
(2.0, 8, 3.0)
```

### an.verify.prosody.pitch_track(samples, sr, , fmin=60.0, fmax=500.0, hop_s=0.01, window_s=0.025, threshold=0.1, voicing_threshold=0.35, chunk=4096)

A YIN pitch track: Hz per hop, `nan` where no period is found.

* **Return type:**
  `ndarray`

```pycon
>>> sr = 16000
>>> t = np.arange(sr // 2) / sr
>>> f0 = pitch_track(np.sin(2 * np.pi * 220 * t), sr)
>>> round(float(np.nanmedian(f0)))
220
>>> bool(np.isnan(pitch_track(np.zeros(sr // 4), sr)).all())
True
```

### an.verify.prosody.prosody_lint(audio, targets, , text=None, miss_severity='warning')

Measure `audio` (a path, several paths, or stats already measured) and
report each target it misses. Passes unless `miss_severity` is `error`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`ProsodyStats`](#an.verify.prosody.ProsodyStats), [`VerificationReport`](an.verify.md#an.verify.VerificationReport)]

### an.verify.prosody.target_distance(stats, targets, , unmeasurable=1.0)

How far `stats` sits from `targets`: `(outside, off_centre)`, lower is closer.

`outside` sums, over the targets, the distance outside `[low, high]` in
units of the range’s width (0 for a value inside); a metric this clip cannot
measure counts `unmeasurable` widths, so a broken take never wins by
having no number. `off_centre` sums each value’s distance from its range’s
midpoint, in the same units — the tie-break between takes that are all on
target. A zero-width range counts as one unit wide.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> s = ProsodyStats(1.0, 1.0, 1.0, 3, 0, *[3.0] * 13)
>>> target_distance(s, {"f0_sd_st": [2, 4]})
(0.0, 0.0)
>>> target_distance(s, {"f0_sd_st": [4, 6], "f0_range_st": [1, 5]})
(0.5, 1.0)
```

### an.verify.prosody.validate_targets(targets)

Raise [`ProsodyTargetError`](#an.verify.prosody.ProsodyTargetError) unless every target names a metric and is a `[low, high]` range.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> validate_targets({"f0_sd_st": [2, 4]})
>>> validate_targets({"f0_sd_st": [4, 2]})
Traceback (most recent call last):
...
an.verify.prosody.ProsodyTargetError: prosody target 'f0_sd_st' must be [low, high], got [4, 2]
```
