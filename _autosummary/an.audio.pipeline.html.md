# an.audio.pipeline

Audio pipeline orchestration: dialogue → audio → visemes → IR mutation.

Phase 3 wires the pieces together. `produce_audio_for_scene` walks every
`Dialogue` in the scene, synthesizes its audio + viseme track via the
configured providers, persists artifacts to `mall["audio"]` /
`mall["visemes"]`, and stamps the resulting `VisemeTrack` and timing
back onto the `Dialogue` line so renderers can find it.

Defaults are the offline providers (silent WAV + deterministic visemes), so
the entire pipeline runs without API keys or external binaries.

```pycon
>>> from an.audio.pipeline import default_tts, default_lipsync
>>> default_tts().name
'offline'
>>> default_lipsync().name
'offline'
```

### Functions

| [`default_lipsync`](#an.audio.pipeline.default_lipsync)()                                 | The default lip-sync provider: `OfflineLipSync`.                    |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`default_tts`](#an.audio.pipeline.default_tts)()                                     | The default TTS provider: `OfflineTTS`.                             |
| [`produce_audio_for_dialogue`](#an.audio.pipeline.produce_audio_for_dialogue)(dialogue[, mall, ...]) | Synthesize audio + visemes for one dialogue line.                   |
| [`produce_audio_for_scene`](#an.audio.pipeline.produce_audio_for_scene)(scene[, mall, tts, ...])  | Walk every dialogue line, synthesize, and stamp viseme tracks back. |

### Exceptions

| [`AudioPipelineError`](#an.audio.pipeline.AudioPipelineError)   | The scene declares audio the pipeline cannot produce.   |
|-----------------------------------------------------------------------|---------------------------------------------------------|

### *exception* an.audio.pipeline.AudioPipelineError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The scene declares audio the pipeline cannot produce. Carries detail.

### an.audio.pipeline.default_lipsync()

The default lip-sync provider: `OfflineLipSync`.

* **Return type:**
  [`LipSyncProvider`](an.audio.lipsync.html.md#an.audio.lipsync.LipSyncProvider)

### an.audio.pipeline.default_tts()

The default TTS provider: `OfflineTTS`.

* **Return type:**
  [`TTSProvider`](an.audio.tts.html.md#an.audio.tts.TTSProvider)

### an.audio.pipeline.produce_audio_for_dialogue(dialogue, mall=None, , tts=None, lipsync=None)

Synthesize audio + visemes for one dialogue line.

Side effects: when `mall` is provided, persists the WAV to
`mall["audio"]` keyed by the content-hash of the dialogue, and persists
the viseme JSON to `mall["visemes"]` similarly. Cache-friendly: a
second call with identical inputs returns the cached versions.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`AudioClip`](an.audio.tts.html.md#an.audio.tts.AudioClip), [`VisemeTrack`](an.audio.lipsync.html.md#an.audio.lipsync.VisemeTrack)]

### an.audio.pipeline.produce_audio_for_scene(scene, mall=None, , tts=None, lipsync=None)

Walk every dialogue line, synthesize, and stamp viseme tracks back.

Mutates the `scene` in place AND returns it (for chaining).
Stamps `Dialogue.duration`, `Dialogue.start` (if unset),
`Dialogue.viseme_track`, and `Dialogue.audio_ref` (mall[“audio”] key)
so the renderer can find the audio later. Lines with an existing
viseme_track AND audio_ref are skipped (idempotent).

* **Return type:**
  [`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR)
