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

| [`audio_key`](#an.audio.pipeline.audio_key)(text, voice_id, tts_name[, ...])        | Content key of a line's audio: text, voice, provider, and — only when the voice declares them — its effects and the provider voice it names (an#194).   |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`default_lipsync`](#an.audio.pipeline.default_lipsync)()                                 | The default lip-sync provider: `OfflineLipSync`.                                                                                                        |
| [`default_tts`](#an.audio.pipeline.default_tts)()                                     | The default TTS provider: `OfflineTTS`.                                                                                                                 |
| [`produce_audio_for_dialogue`](#an.audio.pipeline.produce_audio_for_dialogue)(dialogue[, mall, ...]) | Synthesize audio + visemes for one dialogue line.                                                                                                       |
| [`produce_audio_for_scene`](#an.audio.pipeline.produce_audio_for_scene)(scene[, mall, tts, ...])  | Walk every dialogue line, synthesize, and stamp viseme tracks back.                                                                                     |
| [`retime_dialogue`](#an.audio.pipeline.retime_dialogue)(scene, \*[, timed_shots_only])    | Stamp every synthesized line's `start` from its `pause` / `at`.                                                                                         |
| [`viseme_key`](#an.audio.pipeline.viseme_key)(audio_key_, lipsync_name, transcript)  | Content key of a line's viseme track (a function of the audio HEARD).                                                                                   |

### Exceptions

| [`AudioPipelineError`](#an.audio.pipeline.AudioPipelineError)   | The scene declares audio the pipeline cannot produce.   |
|-----------------------------------------------------------------------|---------------------------------------------------------|

### *exception* an.audio.pipeline.AudioPipelineError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The scene declares audio the pipeline cannot produce. Carries detail.

### an.audio.pipeline.audio_key(text, voice_id, tts_name, effects=None, , provider_voice=None)

Content key of a line’s audio: text, voice, provider, and — only when the
voice declares them — its effects and the provider voice it names (an#194).
With neither, the payload is exactly the pre-effects one, so every key a
project already has is unchanged.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.pipeline.default_lipsync()

The default lip-sync provider: `OfflineLipSync`.

* **Return type:**
  [`LipSyncProvider`](an.audio.lipsync.md#an.audio.lipsync.LipSyncProvider)

### an.audio.pipeline.default_tts()

The default TTS provider: `OfflineTTS`.

* **Return type:**
  [`TTSProvider`](an.audio.tts.md#an.audio.tts.TTSProvider)

### an.audio.pipeline.produce_audio_for_dialogue(dialogue, mall=None, , tts=None, lipsync=None, effects=None, voice_id=None)

Synthesize audio + visemes for one dialogue line.

Side effects: when `mall` is provided, persists the WAV to
`mall["audio"]` keyed by the content-hash of the dialogue, and persists
the viseme JSON to `mall["visemes"]` similarly. Cache-friendly: a
second call with identical inputs returns the cached versions.

`effects` (default: what the line’s voice declares in `mall["voices"]`)
is applied to the synthesized audio BEFORE alignment, so the visemes are
computed on the audio the viewer hears. The raw synthesis stays cached under
its own key, so changing an effect never re-pays the TTS.

`voice_id` (default: the line’s `voice_ref`, else `"default"`) is the
`voices`-store key; [`produce_audio_for_scene()`](#an.audio.pipeline.produce_audio_for_scene) passes the one
[`an.audio.voices.line_voice_id()`](an.audio.voices.md#an.audio.voices.line_voice_id) resolves, so a character’s bound
voice reaches here (an#194). The provider is handed the voice document’s
own `voice_id` when it names one.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`AudioClip`](an.audio.tts.md#an.audio.tts.AudioClip), [`VisemeTrack`](an.audio.lipsync.md#an.audio.lipsync.VisemeTrack)]

### an.audio.pipeline.produce_audio_for_scene(scene, mall=None, , tts=None, lipsync=None)

Walk every dialogue line, synthesize, and stamp viseme tracks back.

Mutates the `scene` in place AND returns it (for chaining).
Stamps `Dialogue.duration`, `Dialogue.viseme_track`, and
`Dialogue.audio_ref` (mall[“audio”] key) so the renderer can find the
audio later. Lines with an existing viseme_track AND audio_ref are not
re-synthesized (idempotent).

`Dialogue.start` is DERIVED on every pass, synthesized or not, by
`Dialogue.planned_start()`: the line’s `at` if set, else the previous
line’s end plus its `pause` (an#187). So editing a pause re-times the
shot without touching the audio, and every consumer of `start` — the
mux, the visemes, captions, ducking — follows. A `start` on a line that
was never synthesized is an authored start from before `at` existed,
and is kept as the line’s `at`.

* **Return type:**
  [`SceneIR`](an.ir.schema.md#an.ir.schema.SceneIR)

### an.audio.pipeline.retime_dialogue(scene, , timed_shots_only=False)

Stamp every synthesized line’s `start` from its `pause` / `at`.

Pure — synthesizes nothing, reads no store — and idempotent. The audio
pipeline ends with it, and every path that skips the pipeline (`render`
with `auto_audio=False`, `an preview`) runs it too, so a pause edited
after synthesis is never played at the stale stamp (an#187). A shot is
re-timed up to its first line with no `duration` (never synthesized:
nothing after it has a known start). Mutates in place and returns
`scene`.

`timed_shots_only=True` — what the paths that skip synthesis pass —
leaves a shot whose lines carry no `pause`/`at` exactly as stamped:
a hand-built scene may stamp `start` itself (a test, a fixture), and
without the pipeline there is no authority to say that stamp is stale.

* **Return type:**
  [`SceneIR`](an.ir.schema.md#an.ir.schema.SceneIR)

```pycon
>>> from an.ir.schema import Dialogue, SceneIR, Shot
>>> shot = Shot(id="s", dialogue=[
...     Dialogue(speaker="a", text="hi", start=0.0, duration=0.5, audio_ref="k1"),
...     Dialogue(speaker="b", text="bye", start=0.5, duration=0.4, audio_ref="k2",
...              pause=1.5)])
>>> [d.start for d in retime_dialogue(SceneIR(timeline=[shot])).timeline[0].dialogue]
[0.0, 2.0]
```

### an.audio.pipeline.viseme_key(audio_key_, lipsync_name, transcript)

Content key of a line’s viseme track (a function of the audio HEARD).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
