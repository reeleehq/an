# an.audio.effects

Voice effects: a deterministic transform applied to a synthesized line (an#163).

A voice document in the `voices` store may declare `effects`. Three exist:

- `pitch_semitones` (an#163) — South Park raises its voices to sound like
  fourth graders; duration-preserving.
- `tempo` (an#265) — a pitch-preserving speed ratio (`1.1` is 10% faster).
  `eleven_v3` ignores `voice_settings.speed` and no audio tag moves its rate,
  so a narrator that must run at 5.8 syllables/s, or an expressive voice that
  must be slowed to a serene pace, is re-timed here. Unlike the pitch effect it
  CHANGES the line’s duration.
- `trim_silence` (an#254) — cut the silence before the first word and after
  the last, keeping a little of each (`true`, or `{threshold_db, keep_lead_s,
  keep_tail_s}`). A real voice pads a line: `eleven_v3` returned 1.6 s for
  “Hi!” — 0.4 s of breath before the word and 0.65 s of room tone after it — so
  the line started late and the next one ran past its shot. It CHANGES the
  line’s duration too, and it is OPT-IN: a voice that values its breaths (a
  style that keeps a performance’s natural artifacts) declares nothing, or a
  lower threshold, and keeps them.

A raised voice or a fast narrator is a property of the *character*, not of the
TTS provider, so it lives beside the voice the line already resolves through
rather than in the IR.

```pycon
>>> normalize_effects({"pitch_semitones": 4})
{'pitch_semitones': 4.0, 'chain_version': 2}
>>> normalize_effects({"pitch_semitones": 0}) == normalize_effects({"tempo": 1}) == normalize_effects(None) == {}
True
>>> normalize_effects({"tempo": 1.1, "pitch_semitones": -2})
{'pitch_semitones': -2.0, 'tempo': 1.1, 'chain_version': 2}
>>> round(_pitch_filter(12), 3)
0.5
>>> filter_chain({"tempo": 1.25})
'aresample=44100,apad=pad_dur=0.25,atempo=1.250000000'
>>> normalize_effects({"trim_silence": True})["trim_silence"]
{'keep_lead_s': 0.1, 'keep_tail_s': 0.2, 'threshold_db': -20.0, 'version': 1}
>>> normalize_effects({"trim_silence": False}) == {}
True
>>> normalize_effects({"reverb": 1})
Traceback (most recent call last):
    ...
an.audio.effects.VoiceEffectError: unknown voice effect(s) ['reverb']; known: ['pitch_semitones', 'tempo', 'trim_silence']
```

Design, in the order the pipeline uses it:

- **The transform runs after synthesis and before alignment.** Lip-sync reads the
  audio the viewer hears. The pitch chain keeps the duration, so word timings
  computed on raw and on shifted audio agree to a frame; a `tempo` does not,
  which is why the shifted bytes are what is aligned, the line’s `duration` is
  read from them, and the viseme key derives from the effect-keyed audio key —
  visemes, word timings and captions all follow the audio the viewer hears.
- **The cache keys on the effect.** `effects_key` is empty for no effect, and
  `an.audio.pipeline` adds it to the audio key only when it is non-empty, so a
  project that declares none keeps every key it ever had.
- **Stock ffmpeg only.** The chain is `aresample → asetrate → aresample →
  atempo`: the sample rate is relabelled by the pitch ratio (pitch and speed both
  move) and `atempo` removes the speed change; a `tempo` multiplies into that
  same `atempo` factor (`aresample → atempo` alone when there is no pitch).
  A factor outside `atempo`’s clean `[0.5, 2]` is split into stages, each
  inside it; the pitch-only chain is one stage, character for character what it
  was before `tempo` existed. `rubberband` is a better
  shifter but is a build option, and its output would differ between machines —
  which a content-hash cache cannot tolerate. The output is bit-exact WAV (no
  encoder tag, no metadata), so two runs produce identical bytes.
- **The trim runs last, in Python**, on the WAV the chain wrote (or on the
  synthesized audio, decoded by ffmpeg only when it is not 16-bit PCM WAV —
  ElevenLabs sends MP3): the level of each [`TRIM_WINDOW_S`](#an.audio.effects.TRIM_WINDOW_S) window is
  compared with the line’s loudest, so a quiet voice and a loud one are cut
  alike, and the kept padding is in the seconds the viewer hears. Its
  parameters, resolved (defaults included) with [`TRIM_VERSION`](#an.audio.effects.TRIM_VERSION), are what
  the key holds, so a changed default re-trims instead of replaying. What it
  cut is RECORDED in the WAV it writes — a standard `LIST`/`INFO` comment
  after the samples, which every reader skips — and [`trim_record()`](#an.audio.effects.trim_record) reads
  it back: the record travels with the bytes it describes and is collected
  with them. A line with nothing above the threshold (the offline voice’s
  silence) is left whole.

### Module Attributes

| [`PITCH_SEMITONES_LIMIT`](#an.audio.effects.PITCH_SEMITONES_LIMIT)   | Effects a voice document may declare, with the range each accepts.                                                                                                                                                                                        |
|--------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`TEMPO_LIMITS`](#an.audio.effects.TEMPO_LIMITS)            | half to double speed.                                                                                                                                                                                                                                     |
| [`ATEMPO_STAGE_LIMITS`](#an.audio.effects.ATEMPO_STAGE_LIMITS)     | One `atempo` stage's clean range; a factor beyond it is chained in stages.                                                                                                                                                                                |
| [`EFFECT_SAMPLE_RATE`](#an.audio.effects.EFFECT_SAMPLE_RATE)      | The sample rate the chain runs at (and the shifted WAV is written at).                                                                                                                                                                                    |
| [`TRIM_SILENCE`](#an.audio.effects.TRIM_SILENCE)            | The effect that cuts a line's leading and trailing silence (an#254).                                                                                                                                                                                      |
| [`DFLT_TRIM_THRESHOLD_DB`](#an.audio.effects.DFLT_TRIM_THRESHOLD_DB)  | `trim_silence`'s defaults.                                                                                                                                                                                                                                |
| [`DFLT_TRIM_KEEP_LEAD_S`](#an.audio.effects.DFLT_TRIM_KEEP_LEAD_S)   | more than the lip-sync anticipation lead (2/24 s), so the mouth can open before the sound.                                                                                                                                                                |
| [`DFLT_TRIM_KEEP_TAIL_S`](#an.audio.effects.DFLT_TRIM_KEEP_TAIL_S)   | a word's release and decay.                                                                                                                                                                                                                               |
| [`TRIM_THRESHOLD_LIMITS`](#an.audio.effects.TRIM_THRESHOLD_LIMITS)   | `threshold_db` bounds (relative to the line's loudest window).                                                                                                                                                                                            |
| [`TRIM_KEEP_LIMITS`](#an.audio.effects.TRIM_KEEP_LIMITS)        | `keep_lead_s` / `keep_tail_s` bounds, seconds.                                                                                                                                                                                                            |
| [`TRIM_WINDOW_S`](#an.audio.effects.TRIM_WINDOW_S)           | a change to it (or to anything else that moves a trimmed line's bytes) is a [`TRIM_VERSION`](#an.audio.effects.TRIM_VERSION) bump — a test pins the trim's output to the version (an#309).                                                   |
| [`TRIM_VERSION`](#an.audio.effects.TRIM_VERSION)            | Bumped whenever a trimmed line's bytes would change (algorithm, window, record tag, rounding); part of every trimmed line's key.                                                                                                                          |
| [`CHAIN_VERSION`](#an.audio.effects.CHAIN_VERSION)           | The version of the ffmpeg chain every effected line passes (pitch, tempo, and the decode of a non-WAV line before its trim): its filters, rate ([`EFFECT_SAMPLE_RATE`](#an.audio.effects.EFFECT_SAMPLE_RATE)), `atempo` stages and flags (an#309). |
| [`TEMPO_PAD_S`](#an.audio.effects.TEMPO_PAD_S)             | Seconds of silence appended before the `atempo` stages, so their window never eats the line's tail (it dropped 20-40 ms of every short padded clip, an#350); the output is then cut to the exact length the tempo gives.                                  |
| [`TRIM_RECORD_TAG`](#an.audio.effects.TRIM_RECORD_TAG)         | The prefix of the `LIST`/`INFO` comment a trimmed WAV carries.                                                                                                                                                                                            |

### Functions

| [`apply_voice_effects`](#an.audio.effects.apply_voice_effects)(audio, effects)             | `audio` (any container ffmpeg sniffs) with `effects` applied, as WAV bytes.                                                                                            |
|--------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`atempo_stages`](#an.audio.effects.atempo_stages)(factor, \*[, limits])             | `factor` as a product of `atempo` stages, each inside `limits`.                                                                                                        |
| [`decode_chain`](#an.audio.effects.decode_chain)()                                  | The chain that decodes a non-WAV line (MP3, from ElevenLabs) before its trim (part of [`CHAIN_VERSION`](#an.audio.effects.CHAIN_VERSION)).                 |
| [`ffmpeg_argv`](#an.audio.effects.ffmpeg_argv)(chain, out_path, \*[, source_path]) | The argv that runs `chain` over audio on stdin into a bit-exact 16-bit PCM WAV at `out_path` (part of [`CHAIN_VERSION`](#an.audio.effects.CHAIN_VERSION)). |
| [`filter_chain`](#an.audio.effects.filter_chain)(effects)                           | The ffmpeg `-af` chain for normalised `effects` (`""` for none).                                                                                                       |
| [`normalize_effects`](#an.audio.effects.normalize_effects)(raw)                          | The canonical effects dict for a voice's `effects` value.                                                                                                              |
| [`speech_end`](#an.audio.effects.speech_end)(audio, \*[, threshold_db, window_s]) | Seconds into `audio` at which its audible speech ends (an#397); `None` when silent or unreadable.                                                                      |
| [`trim_record`](#an.audio.effects.trim_record)(wav)                                | What `trim_silence` cut from `wav` (`lead_s`, `tail_s`, `source_s`), read from the comment it wrote; `None` for audio it did not write.                                |
| [`trim_silence`](#an.audio.effects.trim_silence)(wav, \*[, threshold_db, ...])      | `wav` (16-bit PCM) cut to its speech, plus `keep_lead_s` before it and `keep_tail_s` after it, and the cut recorded in the WAV it returns.                             |
| [`voice_effects`](#an.audio.effects.voice_effects)(mall, voice_id)                   | The normalised effects declared by `mall["voices"][voice_id]`, or `{}`.                                                                                                |

### Classes

| [`SilenceTrim`](#an.audio.effects.SilenceTrim)(audio, lead_s, tail_s, source_s)   | What [`trim_silence()`](#an.audio.effects.trim_silence) produced: the trimmed WAV, and what it cut.   |
|-------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------|

### Exceptions

| [`VoiceEffectError`](#an.audio.effects.VoiceEffectError)   | A voice declares an effect that is unknown, malformed or out of range.   |
|---------------------------------------------------------------------|--------------------------------------------------------------------------|

### an.audio.effects.ATEMPO_STAGE_LIMITS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= (0.5, 2.0)*

One `atempo` stage’s clean range; a factor beyond it is chained in stages.

### an.audio.effects.CHAIN_VERSION *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

The version of the ffmpeg chain every effected line passes (pitch, tempo,
and the decode of a non-WAV line before its trim): its filters, rate
([`EFFECT_SAMPLE_RATE`](#an.audio.effects.EFFECT_SAMPLE_RATE)), `atempo` stages and flags (an#309). Keyed
only once it is not the first, so introducing it moved no key; bump it with
any change to [`filter_chain()`](#an.audio.effects.filter_chain), [`ffmpeg_argv()`](#an.audio.effects.ffmpeg_argv) or their constants
— a test pins them to the version. Moving the key re-processes each line
from its raw take, which is cached: nothing is billed.

2 (an#350): silence padded before the `atempo` stages and the output cut
to exactly `input / tempo` — `atempo` dropped the last 20-40 ms.

### an.audio.effects.DFLT_TRIM_KEEP_LEAD_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.1*

more than the lip-sync
anticipation lead (2/24 s), so the mouth can open before the sound.

* **Type:**
  Kept before the first window above the threshold

### an.audio.effects.DFLT_TRIM_KEEP_TAIL_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.2*

a word’s release and decay.

* **Type:**
  Kept after the last window above it

### an.audio.effects.DFLT_TRIM_THRESHOLD_DB *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= -20.0*

`trim_silence`’s defaults. A window is “speech” when its RMS level is within
`threshold_db` of the line’s loudest window. Measured on two eleven_v3 lines
(an#254): the breath before “Hi!” peaks 25 dB under the word and its room
tone 35-40 dB under, while each word’s own edges stay within 20 dB — so -20
cuts the breath and the tail and keeps the word. Lower it (-45) to keep breaths.

### an.audio.effects.EFFECT_SAMPLE_RATE *= 44100*

The sample rate the chain runs at (and the shifted WAV is written at).

### an.audio.effects.PITCH_SEMITONES_LIMIT *= 12.0*

Effects a voice document may declare, with the range each accepts.

### *class* an.audio.effects.SilenceTrim(audio, lead_s, tail_s, source_s)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What [`trim_silence()`](#an.audio.effects.trim_silence) produced: the trimmed WAV, and what it cut.

#### lead_s *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Seconds cut before the kept audio, and after it.

#### record()

The record the trimmed WAV carries ([`trim_record()`](#an.audio.effects.trim_record)).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

#### source_s *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The length of the audio before the trim, seconds.

### an.audio.effects.TEMPO_LIMITS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= (0.5, 2.0)*

half to double speed. Outside it speech stops being speech.

* **Type:**
  `tempo` bounds

### an.audio.effects.TEMPO_PAD_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.25*

Seconds of silence appended before the `atempo` stages, so their window
never eats the line’s tail (it dropped 20-40 ms of every short padded clip,
an#350); the output is then cut to the exact length the tempo gives.
Enough for the slowest stage of [`TEMPO_LIMITS`](#an.audio.effects.TEMPO_LIMITS) at every pitch.

### an.audio.effects.TRIM_KEEP_LIMITS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= (0.0, 2.0)*

`keep_lead_s` / `keep_tail_s` bounds, seconds.

### an.audio.effects.TRIM_RECORD_TAG *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an:trim_silence '*

The prefix of the `LIST`/`INFO` comment a trimmed WAV carries.

### an.audio.effects.TRIM_SILENCE *= 'trim_silence'*

The effect that cuts a line’s leading and trailing silence (an#254).

### an.audio.effects.TRIM_THRESHOLD_LIMITS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= (-80.0, -3.0)*

`threshold_db` bounds (relative to the line’s loudest window).

### an.audio.effects.TRIM_VERSION *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

Bumped whenever a trimmed line’s bytes would change (algorithm, window,
record tag, rounding); part of every trimmed line’s key.

### an.audio.effects.TRIM_WINDOW_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.02*

a change to it (or
to anything else that moves a trimmed line’s bytes) is a [`TRIM_VERSION`](#an.audio.effects.TRIM_VERSION)
bump — a test pins the trim’s output to the version (an#309).

* **Type:**
  The level-measuring window, seconds. Not keyed itself

### *exception* an.audio.effects.VoiceEffectError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A voice declares an effect that is unknown, malformed or out of range.

### an.audio.effects.apply_voice_effects(audio, effects)

`audio` (any container ffmpeg sniffs) with `effects` applied, as WAV bytes.

Returns the input unchanged for no effects. Raises `VoiceEffectError` when
ffmpeg is missing or fails — never returns unprocessed audio for a voice that
asked for an effect. `trim_silence` alone on a 16-bit PCM WAV needs no
ffmpeg ([`trim_silence()`](#an.audio.effects.trim_silence)).

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.audio.effects.atempo_stages(factor, , limits=(0.5, 2.0))

`factor` as a product of `atempo` stages, each inside `limits`.

One stage when `factor` already fits (the pitch-only chain, always).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> atempo_stages(1.5)
[1.5]
>>> atempo_stages(3.0)
[2.0, 1.5]
>>> atempo_stages(0.3)
[0.5, 0.6]
```

### an.audio.effects.decode_chain()

The chain that decodes a non-WAV line (MP3, from ElevenLabs) before its
trim (part of [`CHAIN_VERSION`](#an.audio.effects.CHAIN_VERSION)).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.effects.ffmpeg_argv(chain, out_path, , source_path=None)

The argv that runs `chain` over audio on stdin into a bit-exact 16-bit
PCM WAV at `out_path` (part of [`CHAIN_VERSION`](#an.audio.effects.CHAIN_VERSION)).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

source_path: also write the input, decoded ([`decode_chain()`](#an.audio.effects.decode_chain)) and
: untouched, there — in the same run, so its length is known whatever
  container came in (an#350: a tempo chain’s output is cut to it)

```pycon
>>> ffmpeg_argv("aresample=44100", "o.wav")[-3:]
['-c:a', 'pcm_s16le', 'o.wav']
>>> ffmpeg_argv("atempo=2", "o.wav", source_path="s.wav")[-1]
's.wav'
```

### an.audio.effects.filter_chain(effects)

The ffmpeg `-af` chain for normalised `effects` (`""` for none).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.effects.normalize_effects(raw)

The canonical effects dict for a voice’s `effects` value.

Omit-when-unset: `None`, `{}` and a zero-valued effect all normalise to
`{}`, which the pipeline treats as “no effect” (and keys nothing on).
Unknown keys raise — an effect that silently does nothing is worse than none.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.audio.effects.speech_end(audio, , threshold_db=-20.0, window_s=0.02)

Seconds into `audio` at which its audible speech ends (an#397); `None` when silent or unreadable.

The end of the last `window_s` window whose RMS level is within
`threshold_db` of the loudest window’s — [`trim_silence()`](#an.audio.effects.trim_silence)’s rule, so
a take’s own trailing silence (a provider pads ~0.3 s) is not counted. A
16-bit PCM WAV is read directly; any other container is decoded with ffmpeg
when it is installed.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> import array, io, wave
>>> rate = 8000
>>> samples = array.array("h", [9000, -9000] * (rate // 4) + [0] * rate)  # 0.5 s, then 1 s silent
>>> buf = io.BytesIO()
>>> with wave.open(buf, "wb") as w:
...     w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(samples.tobytes())
>>> round(speech_end(buf.getvalue()), 2)
0.5
```

### an.audio.effects.trim_record(wav)

What `trim_silence` cut from `wav` (`lead_s`, `tail_s`, `source_s`),
read from the comment it wrote; `None` for audio it did not write.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.effects.trim_silence(wav, , threshold_db=-20.0, keep_lead_s=0.1, keep_tail_s=0.2, window_s=0.02)

`wav` (16-bit PCM) cut to its speech, plus `keep_lead_s` before it and
`keep_tail_s` after it, and the cut recorded in the WAV it returns.

Speech is every `window_s` window whose RMS level is within
`threshold_db` of the loudest window’s; only the edges move, never a pause
between words. A clip with no sound at all is returned whole (with the
record of a zero cut), and a pad is never longer than the silence it keeps.

* **Return type:**
  [`SilenceTrim`](#an.audio.effects.SilenceTrim)

```pycon
>>> import array, io, math, wave
>>> rate = 8000
>>> tone = [int(9000 * math.sin(i / 3)) for i in range(rate // 2)]
>>> samples = array.array("h", [0] * rate + tone + [0] * rate)   # 1 s, 0.5 s, 1 s
>>> buf = io.BytesIO()
>>> with wave.open(buf, "wb") as w:
...     w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
...     w.writeframes(samples.tobytes())
>>> cut = trim_silence(buf.getvalue(), keep_lead_s=0.1, keep_tail_s=0.2)
>>> round(cut.lead_s, 2), round(cut.tail_s, 2), round(cut.source_s, 2)
(0.9, 0.8, 2.5)
>>> trim_record(cut.audio) == cut.record()
True
>>> with wave.open(io.BytesIO(cut.audio)) as w:
...     round(w.getnframes() / w.getframerate(), 2)
0.8
```

### an.audio.effects.voice_effects(mall, voice_id)

The normalised effects declared by `mall["voices"][voice_id]`, or `{}`.

A voice that is not in the store (the offline default, a raw provider voice
id) has no effects; so does a store that does not exist.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
