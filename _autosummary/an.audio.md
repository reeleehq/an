# an.audio

Audio pipeline — TTS and lip-sync providers + orchestration.

Phase 3 ships:

- Protocols: `TTSProvider`, `LipSyncProvider` (Phase 1).
- Default offline providers: `OfflineTTS` (silent WAV), `OfflineLipSync`
  (deterministic char-to-viseme).
- Real providers: `ElevenLabsTTS` (needs `ELEVEN_API_KEY`),
  `RhubarbLipSync` (needs `rhubarb` binary).
- Orchestration: `produce_audio_for_dialogue` /
  `produce_audio_for_scene` walk a SceneIR, synthesize, persist to mall,
  stamp viseme tracks back onto the IR.

The defaults are intentionally offline so the entire `an` pipeline works
without external services.

### Functions

| [`word_timings_to_visemes`](#an.audio.word_timings_to_visemes)(words, \*, ...[, ...])    | Distribute viseme keyframes across word boundaries.                 |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`default_tts`](#an.audio.default_tts)()                                     | The default TTS provider: `OfflineTTS`.                             |
| [`default_lipsync`](#an.audio.default_lipsync)()                                 | The default lip-sync provider: `OfflineLipSync`.                    |
| [`produce_audio_for_dialogue`](#an.audio.produce_audio_for_dialogue)(dialogue[, mall, ...]) | Synthesize audio + visemes for one dialogue line.                   |
| [`produce_audio_for_scene`](#an.audio.produce_audio_for_scene)(scene[, mall, tts, ...])  | Walk every dialogue line, synthesize, and stamp viseme tracks back. |
| [`make_tts`](#an.audio.make_tts)(name)                                    | Instantiate a TTS provider by name.                                 |
| [`make_lipsync`](#an.audio.make_lipsync)(name, \*[, language])                | Instantiate a LipSync provider by name.                             |
| [`known_tts_names`](#an.audio.known_tts_names)()                                 | Return the registered TTS provider names.                           |
| [`known_lipsync_names`](#an.audio.known_lipsync_names)()                             | Return the registered LipSync provider names.                       |

### Classes

| [`TTSProvider`](#an.audio.TTSProvider)(\*args, \*\*kwargs)                   | Text-to-speech provider.                                                                                                                          |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| [`AudioClip`](#an.audio.AudioClip)([path, bytes_, duration, ...])          | A rendered audio clip, on disk or in memory.                                                                                                      |
| [`VoiceMeta`](#an.audio.VoiceMeta)(voice_id, name, provider[, ...])        | Metadata for a TTS voice as exposed by a provider.                                                                                                |
| [`LipSyncProvider`](#an.audio.LipSyncProvider)(\*args, \*\*kwargs)               | Audio + transcript → aligned viseme track.                                                                                                        |
| [`Viseme`](#an.audio.Viseme)(time, code[, intensity])                   | A single mouth-shape keyframe.                                                                                                                    |
| [`VisemeTrack`](#an.audio.VisemeTrack)([visemes, convention, duration, ...]) | Aligned viseme sequence produced by a LipSyncProvider.                                                                                            |
| [`WordTimingProvider`](#an.audio.WordTimingProvider)(\*args, \*\*kwargs)            | Audio → `[(word, start_s, end_s), ...]`.                                                                                                          |
| [`OfflineTTS`](#an.audio.OfflineTTS)(\*[, sample_rate, channels, ...])      | Default TTS provider: silent WAV of length proportional to text.                                                                                  |
| [`OfflineLipSync`](#an.audio.OfflineLipSync)(\*[, char_to_viseme])              | Default lip-sync provider: deterministic char-to-viseme mapping.                                                                                  |
| [`ElevenLabsTTS`](#an.audio.ElevenLabsTTS)(\*[, api_key, model_id, ...])       | ElevenLabs-backed TTSProvider.                                                                                                                    |
| [`MacSayTTS`](#an.audio.MacSayTTS)(\*[, default_voice_id, ...])            | macOS `say`-backed TTSProvider.                                                                                                                   |
| [`RhubarbLipSync`](#an.audio.RhubarbLipSync)(\*[, binary_path, language, ...])  | Wrap the rhubarb CLI.                                                                                                                             |
| [`WhisperLipSync`](#an.audio.WhisperLipSync)(\*[, model_size, device, ...])     | faster-whisper word timestamps → visemes.                                                                                                         |
| [`StaticWordTimings`](#an.audio.StaticWordTimings)(words, \*[, label])             | A [`WordTimingProvider`](#an.audio.WordTimingProvider) over a fixed list of timings.                                               |
| [`WordTimingsLipSync`](#an.audio.WordTimingsLipSync)(provider, \*[, ...])           | [`LipSyncProvider`](#an.audio.LipSyncProvider) driven by a [`WordTimingProvider`](#an.audio.WordTimingProvider). |

### *class* an.audio.AudioClip(path=None, bytes_=None, duration=0.0, sample_rate=44100, channels=1, voice_id=None, transcript=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A rendered audio clip, on disk or in memory.

### *class* an.audio.ElevenLabsTTS(, api_key=None, model_id='eleven_turbo_v2_5', output_format='mp3_44100_128')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

ElevenLabs-backed TTSProvider. Constructor takes an optional api_key
(falls back to `ELEVEN_API_KEY` / `ELEVENLABS_API_KEY`).

Implements the `TTSProvider` protocol.

### *class* an.audio.LipSyncProvider(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Audio + transcript → aligned viseme track.

A provider that fills `VisemeTrack.words` also declares
`emits_word_timings = True` (a plain class attribute, absent means
False). The audio pipeline reads it to decide whether a line whose
`word_timings` are missing needs re-alignment — without the flag, a
provider that cannot supply words would re-align every line forever.

#### align(audio, transcript)

Produce a viseme track for `audio` given its `transcript`.

* **Return type:**
  [`VisemeTrack`](an.audio.lipsync.md#an.audio.lipsync.VisemeTrack)

### *class* an.audio.MacSayTTS(, default_voice_id='Samantha', sample_rate=22050, rate_wpm=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

macOS `say`-backed TTSProvider.

Implements the `TTSProvider` protocol. Audible, deterministic, and
fully offline — uses Apple’s voice synthesis bundled with the OS.

### *class* an.audio.OfflineLipSync(, char_to_viseme=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Default lip-sync provider: deterministic char-to-viseme mapping.

Implements the `LipSyncProvider` protocol.

### *class* an.audio.OfflineTTS(, sample_rate=22050, channels=1, seconds_per_char=0.06)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Default TTS provider: silent WAV of length proportional to text.

Implements the `TTSProvider` protocol.

### *class* an.audio.RhubarbLipSync(, binary_path=None, language='en', recognizer=None, timeout_s=60.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Wrap the rhubarb CLI. Implements the `LipSyncProvider` protocol.

```pycon
>>> RhubarbLipSync(binary_path="/bin/rhubarb").recognizer
'pocketSphinx'
>>> RhubarbLipSync(binary_path="/bin/rhubarb", language="de").recognizer
'phonetic'
>>> RhubarbLipSync(binary_path="/bin/rhubarb", language="de").name
'rhubarb:phonetic'
```

#### *property* uses_dialog_file *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether the chosen recognizer reads a transcript at all.

### *class* an.audio.StaticWordTimings(words, , label='static')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A [`WordTimingProvider`](#an.audio.WordTimingProvider) over a fixed list of timings.

### *class* an.audio.TTSProvider(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Text-to-speech provider.

#### list_voices()

Return all voices the provider exposes.

* **Return type:**
  [`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[[`VoiceMeta`](an.audio.tts.md#an.audio.tts.VoiceMeta)]

#### synthesize(text, voice_id, \*\*kw)

Render `text` in `voice_id`’s voice. Returns an AudioClip.

* **Return type:**
  [`AudioClip`](an.audio.tts.md#an.audio.tts.AudioClip)

### *class* an.audio.Viseme(time, code, intensity=1.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single mouth-shape keyframe.

### *class* an.audio.VisemeTrack(visemes=<factory>, convention='rhubarb', duration=0.0, words=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Aligned viseme sequence produced by a LipSyncProvider.

`words` carries the word timings the provider aligned from, when it had
any (whisper, [`WordTimingsLipSync`](an.audio.injectable_lipsync.md#an.audio.injectable_lipsync.WordTimingsLipSync));
`None` for providers that never see words (offline, Rhubarb — whose JSON
is mouth cues only). Retained since an#96 rather than discarded after the
viseme conversion: captions (Wave 8) and any consumer that wants to know
*which word* a mouth shape belongs to read them from the IR.

### *class* an.audio.VoiceMeta(voice_id, name, provider, language='en', gender=None, extra=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Metadata for a TTS voice as exposed by a provider.

### *class* an.audio.WhisperLipSync(, model_size='tiny', device='cpu', compute_type='int8', char_to_viseme=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

faster-whisper word timestamps → visemes.

Implements the `LipSyncProvider` protocol. The model is lazy-loaded on
the first call (subsequent calls in the same process reuse the instance
via the class-level `_model` cache).

#### emits_word_timings *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Whisper aligns from words, so the track carries them (an#96).

### *class* an.audio.WordTimingProvider(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Audio → `[(word, start_s, end_s), ...]`.

Implementations may run a transcriber (Whisper / Scribe) or look up
pre-computed timings (`muvid`’s lacing store). Returned tuples are
expected to be in ascending start-time order; gaps between words are
fine and represent silence the lipsync provider should rest through.

#### words_for(audio, , transcript='')

Return the word timings for `audio`.

* **Return type:**
  [`Sequence`](https://docs.python.org/3/library/typing.html#typing.Sequence)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### *class* an.audio.WordTimingsLipSync(provider, , char_to_viseme=None, convention='rhubarb', rest_viseme='X', min_gap_for_rest=0.2)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

[`LipSyncProvider`](#an.audio.LipSyncProvider) driven by a [`WordTimingProvider`](#an.audio.WordTimingProvider).

Skips transcription entirely. Use this when the caller already has
authoritative word timings (e.g. from a separate lyric-alignment
pipeline).

* **Parameters:**
  * **provider** ([`WordTimingProvider`](an.audio.lipsync.md#an.audio.lipsync.WordTimingProvider)) – any [`WordTimingProvider`](#an.audio.WordTimingProvider).
  * **char_to_viseme** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – optional override of the character→viseme code
    mapping; defaults to the one shared with
    [`OfflineLipSync`](#an.audio.OfflineLipSync) / [`WhisperLipSync`](#an.audio.WhisperLipSync).
  * **convention** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – declared viseme convention string for the produced
    track. Defaults to `"rhubarb"` for compatibility with the
    existing cutout adapter.
  * **rest_viseme** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – code emitted in silent gaps. Defaults to
    `_REST_VISEME`.
  * **min_gap_for_rest** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – minimum inter-word silence (seconds) before
    we insert a rest keyframe. Defaults to `0.20`.

#### emits_word_timings *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Built from words, so the track carries them (an#96).

### an.audio.default_lipsync()

The default lip-sync provider: `OfflineLipSync`.

* **Return type:**
  [`LipSyncProvider`](an.audio.lipsync.md#an.audio.lipsync.LipSyncProvider)

### an.audio.default_tts()

The default TTS provider: `OfflineTTS`.

* **Return type:**
  [`TTSProvider`](an.audio.tts.md#an.audio.tts.TTSProvider)

### an.audio.known_lipsync_names()

Return the registered LipSync provider names.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.audio.known_tts_names()

Return the registered TTS provider names.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.audio.make_lipsync(name, , language='en')

Instantiate a LipSync provider by name.

`language` (BCP-47) reaches providers that select behaviour by language —
Rhubarb’s recognizer today; a future aligner’s weight allowlist.

* **Return type:**
  [`LipSyncProvider`](an.audio.lipsync.md#an.audio.lipsync.LipSyncProvider)

### an.audio.make_tts(name)

Instantiate a TTS provider by name.

Raises `ValueError` for unknown names with a list of known options.

* **Return type:**
  [`TTSProvider`](an.audio.tts.md#an.audio.tts.TTSProvider)

### an.audio.produce_audio_for_dialogue(dialogue, mall=None, , tts=None, lipsync=None, effects=None)

Synthesize audio + visemes for one dialogue line.

Side effects: when `mall` is provided, persists the WAV to
`mall["audio"]` keyed by the content-hash of the dialogue, and persists
the viseme JSON to `mall["visemes"]` similarly. Cache-friendly: a
second call with identical inputs returns the cached versions.

`effects` (default: what the line’s voice declares in `mall["voices"]`)
is applied to the synthesized audio BEFORE alignment, so the visemes are
computed on the audio the viewer hears. The raw synthesis stays cached under
its own key, so changing an effect never re-pays the TTS.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`AudioClip`](an.audio.tts.md#an.audio.tts.AudioClip), [`VisemeTrack`](an.audio.lipsync.md#an.audio.lipsync.VisemeTrack)]

### an.audio.produce_audio_for_scene(scene, mall=None, , tts=None, lipsync=None)

Walk every dialogue line, synthesize, and stamp viseme tracks back.

Mutates the `scene` in place AND returns it (for chaining).
Stamps `Dialogue.duration`, `Dialogue.start` (if unset),
`Dialogue.viseme_track`, and `Dialogue.audio_ref` (mall[“audio”] key)
so the renderer can find the audio later. Lines with an existing
viseme_track AND audio_ref are skipped (idempotent).

* **Return type:**
  [`SceneIR`](an.ir.schema.md#an.ir.schema.SceneIR)

### an.audio.word_timings_to_visemes(words, , total_duration, char_to_viseme, rest_viseme='X', min_gap_for_rest=0.2)

Distribute viseme keyframes across word boundaries.

Used by [`WhisperLipSync`](#an.audio.WhisperLipSync) and [`WordTimingsLipSync`](#an.audio.WordTimingsLipSync). The
algorithm: per word, walk its characters in order, look up each
character’s viseme code, dedupe consecutive identical codes, and
space the resulting keyframes evenly across the word’s
`[start, end]` interval. In gaps wider than `min_gap_for_rest`
insert a single rest keyframe just after the previous word ended.

Times are clamped to `[0, total_duration]` since some
transcribers occasionally round the last word’s end past the
audio’s actual length.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Viseme`](an.audio.lipsync.md#an.audio.lipsync.Viseme)]

### Modules

| [`effects`](an.audio.effects.md#module-an.audio.effects)                       | Voice effects: a deterministic transform applied to a synthesized line (an#163).   |
|--------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`elevenlabs_tts`](an.audio.elevenlabs_tts.md#module-an.audio.elevenlabs_tts)         | ElevenLabsTTS — real speech via the ElevenLabs API.                                |
| [`injectable_lipsync`](an.audio.injectable_lipsync.md#module-an.audio.injectable_lipsync) | Lip-sync provider that consumes pre-computed word timings.                         |
| [`lipsync`](an.audio.lipsync.md#module-an.audio.lipsync)                       | Lip-sync provider protocol + viseme dataclasses.                                   |
| [`mac_say_tts`](an.audio.mac_say_tts.md#module-an.audio.mac_say_tts)               | MacSayTTS — audible offline speech via macOS's built-in `say` command.             |
| [`offline_lipsync`](an.audio.offline_lipsync.md#module-an.audio.offline_lipsync)       | OfflineLipSync — deterministic transcript → viseme track.                          |
| [`offline_tts`](an.audio.offline_tts.md#module-an.audio.offline_tts)               | OfflineTTS — produces silent audio of plausible duration.                          |
| [`pipeline`](an.audio.pipeline.md#module-an.audio.pipeline)                     | Audio pipeline orchestration: dialogue → audio → visemes → IR mutation.            |
| [`providers`](an.audio.providers.md#module-an.audio.providers)                   | Provider factory: name → concrete TTS/LipSync provider instance.                   |
| [`rhubarb_lipsync`](an.audio.rhubarb_lipsync.md#module-an.audio.rhubarb_lipsync)       | RhubarbLipSync — calls the rhubarb-lip-sync binary for phoneme-aligned visemes.    |
| [`tts`](an.audio.tts.md#module-an.audio.tts)                               | TTS provider protocol + supporting dataclasses.                                    |
| [`whisper_lipsync`](an.audio.whisper_lipsync.md#module-an.audio.whisper_lipsync)       | WhisperLipSync — faster-whisper word timestamps → viseme keyframes.                |
