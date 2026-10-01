# an.audio.effects

Voice effects: a deterministic transform applied to a synthesized line (an#163).

A voice document in the `voices` store may declare `effects`. Two exist:

- `pitch_semitones` (an#163) — South Park raises its voices to sound like
  fourth graders; duration-preserving.
- `tempo` (an#265) — a pitch-preserving speed ratio (`1.1` is 10% faster).
  `eleven_v3` ignores `voice_settings.speed` and no audio tag moves its rate,
  so a narrator that must run at 5.8 syllables/s, or an expressive voice that
  must be slowed to a serene pace, is re-timed here. Unlike the pitch effect it
  CHANGES the line’s duration.

A raised voice or a fast narrator is a property of the *character*, not of the
TTS provider, so it lives beside the voice the line already resolves through
rather than in the IR.

```pycon
>>> normalize_effects({"pitch_semitones": 4})
{'pitch_semitones': 4.0}
>>> normalize_effects({"pitch_semitones": 0}) == normalize_effects({"tempo": 1}) == normalize_effects(None) == {}
True
>>> normalize_effects({"tempo": 1.1, "pitch_semitones": -2})
{'pitch_semitones': -2.0, 'tempo': 1.1}
>>> round(_pitch_filter(12), 3)
0.5
>>> filter_chain({"tempo": 1.25})
'aresample=44100,atempo=1.250000000'
>>> normalize_effects({"reverb": 1})
Traceback (most recent call last):
    ...
an.audio.effects.VoiceEffectError: unknown voice effect(s) ['reverb']; known: ['pitch_semitones', 'tempo']
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

### Module Attributes

| [`PITCH_SEMITONES_LIMIT`](#an.audio.effects.PITCH_SEMITONES_LIMIT)   | Effects a voice document may declare, with the range each accepts.         |
|--------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`TEMPO_LIMITS`](#an.audio.effects.TEMPO_LIMITS)            | half to double speed.                                                      |
| [`ATEMPO_STAGE_LIMITS`](#an.audio.effects.ATEMPO_STAGE_LIMITS)     | One `atempo` stage's clean range; a factor beyond it is chained in stages. |
| [`EFFECT_SAMPLE_RATE`](#an.audio.effects.EFFECT_SAMPLE_RATE)      | The sample rate the chain runs at (and the shifted WAV is written at).     |

### Functions

| [`apply_voice_effects`](#an.audio.effects.apply_voice_effects)(audio, effects)   | `audio` (any container ffmpeg sniffs) with `effects` applied, as WAV bytes.   |
|----------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`atempo_stages`](#an.audio.effects.atempo_stages)(factor, \*[, limits])   | `factor` as a product of `atempo` stages, each inside `limits`.               |
| [`filter_chain`](#an.audio.effects.filter_chain)(effects)                 | The ffmpeg `-af` chain for normalised `effects` (`""` for none).              |
| [`normalize_effects`](#an.audio.effects.normalize_effects)(raw)                | The canonical effects dict for a voice's `effects` value.                     |
| [`voice_effects`](#an.audio.effects.voice_effects)(mall, voice_id)         | The normalised effects declared by `mall["voices"][voice_id]`, or `{}`.       |

### Exceptions

| [`VoiceEffectError`](#an.audio.effects.VoiceEffectError)   | A voice declares an effect that is unknown, malformed or out of range.   |
|---------------------------------------------------------------------|--------------------------------------------------------------------------|

### an.audio.effects.ATEMPO_STAGE_LIMITS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= (0.5, 2.0)*

One `atempo` stage’s clean range; a factor beyond it is chained in stages.

### an.audio.effects.EFFECT_SAMPLE_RATE *= 44100*

The sample rate the chain runs at (and the shifted WAV is written at).

### an.audio.effects.PITCH_SEMITONES_LIMIT *= 12.0*

Effects a voice document may declare, with the range each accepts.

### an.audio.effects.TEMPO_LIMITS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= (0.5, 2.0)*

half to double speed. Outside it speech stops being speech.

* **Type:**
  `tempo` bounds

### *exception* an.audio.effects.VoiceEffectError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A voice declares an effect that is unknown, malformed or out of range.

### an.audio.effects.apply_voice_effects(audio, effects)

`audio` (any container ffmpeg sniffs) with `effects` applied, as WAV bytes.

Returns the input unchanged for no effects. Raises `VoiceEffectError` when
ffmpeg is missing or fails — never returns unprocessed audio for a voice that
asked for an effect.

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
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.audio.effects.voice_effects(mall, voice_id)

The normalised effects declared by `mall["voices"][voice_id]`, or `{}`.

A voice that is not in the store (the offline default, a raw provider voice
id) has no effects; so does a store that does not exist.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]
