# an.audio.effects

Voice effects: a deterministic transform applied to a synthesized line (an#163).

A voice document in the `voices` store may declare `effects`. The one effect
that exists is `pitch_semitones` — South Park raises its voices to sound like
fourth graders, and a raised voice is a property of the *character*, not of the
TTS provider, so it lives beside the voice the line already resolves through
rather than in the IR.

```pycon
>>> normalize_effects({"pitch_semitones": 4})
{'pitch_semitones': 4.0}
>>> normalize_effects({"pitch_semitones": 0}) == normalize_effects(None) == {}
True
>>> round(_pitch_filter(12), 3)
0.5
>>> normalize_effects({"reverb": 1})
Traceback (most recent call last):
    ...
an.audio.effects.VoiceEffectError: unknown voice effect(s) ['reverb']; known: ['pitch_semitones']
```

Design, in the order the pipeline uses it:

- **The transform runs after synthesis and before alignment.** Lip-sync reads the
  audio the viewer hears. The chain keeps the duration (see below), so word
  timings computed on raw and on shifted audio agree to a frame, but the shifted
  bytes are what is aligned regardless.
- **The cache keys on the effect.** `effects_key` is empty for no effect, and
  `an.audio.pipeline` adds it to the audio key only when it is non-empty, so a
  project that declares none keeps every key it ever had.
- **Stock ffmpeg only.** The chain is `aresample → asetrate → aresample →
  atempo`: the sample rate is relabelled by the pitch ratio (pitch and speed both
  move) and `atempo` removes the speed change. `rubberband` is a better
  shifter but is a build option, and its output would differ between machines —
  which a content-hash cache cannot tolerate. The output is bit-exact WAV (no
  encoder tag, no metadata), so two runs produce identical bytes.

### Module Attributes

| [`PITCH_SEMITONES_LIMIT`](#an.audio.effects.PITCH_SEMITONES_LIMIT)   | Effects a voice document may declare, with the range each accepts.     |
|--------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`EFFECT_SAMPLE_RATE`](#an.audio.effects.EFFECT_SAMPLE_RATE)      | The sample rate the chain runs at (and the shifted WAV is written at). |

### Functions

| [`apply_voice_effects`](#an.audio.effects.apply_voice_effects)(audio, effects)   | `audio` (any container ffmpeg sniffs) with `effects` applied, as WAV bytes.   |
|----------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`filter_chain`](#an.audio.effects.filter_chain)(effects)                 | The ffmpeg `-af` chain for normalised `effects` (`""` for none).              |
| [`normalize_effects`](#an.audio.effects.normalize_effects)(raw)                | The canonical effects dict for a voice's `effects` value.                     |
| [`voice_effects`](#an.audio.effects.voice_effects)(mall, voice_id)         | The normalised effects declared by `mall["voices"][voice_id]`, or `{}`.       |

### Exceptions

| [`VoiceEffectError`](#an.audio.effects.VoiceEffectError)   | A voice declares an effect that is unknown, malformed or out of range.   |
|---------------------------------------------------------------------|--------------------------------------------------------------------------|

### an.audio.effects.EFFECT_SAMPLE_RATE *= 44100*

The sample rate the chain runs at (and the shifted WAV is written at).

### an.audio.effects.PITCH_SEMITONES_LIMIT *= 12.0*

Effects a voice document may declare, with the range each accepts.

### *exception* an.audio.effects.VoiceEffectError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A voice declares an effect that is unknown, malformed or out of range.

### an.audio.effects.apply_voice_effects(audio, effects)

`audio` (any container ffmpeg sniffs) with `effects` applied, as WAV bytes.

Returns the input unchanged for no effects. Raises `VoiceEffectError` when
ffmpeg is missing or fails — never returns unshifted audio for a voice that
asked for a shift.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

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
