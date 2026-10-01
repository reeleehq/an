# an.audio.tts

TTS provider protocol + supporting dataclasses.

### Classes

| [`AudioClip`](#an.audio.tts.AudioClip)([path, bytes_, duration, ...])   | A rendered audio clip, on disk or in memory.       |
|---------------------------------------------------------------------------------------------|----------------------------------------------------|
| [`TTSProvider`](#an.audio.tts.TTSProvider)(\*args, \*\*kwargs)            | Text-to-speech provider.                           |
| [`VoiceMeta`](#an.audio.tts.VoiceMeta)(voice_id, name, provider[, ...]) | Metadata for a TTS voice as exposed by a provider. |

### *class* an.audio.tts.AudioClip(path=None, bytes_=None, duration=0.0, sample_rate=44100, channels=1, voice_id=None, transcript=None)

Bases: `object`

A rendered audio clip, on disk or in memory.

### *class* an.audio.tts.TTSProvider(\*args, \*\*kwargs)

Bases: `Protocol`

Text-to-speech provider.

#### list_voices()

Return all voices the provider exposes.

* **Return type:**
  `Iterable`[[`VoiceMeta`](#an.audio.tts.VoiceMeta)]

#### synthesize(text, voice_id, \*\*kw)

Render `text` in `voice_id`’s voice. Returns an AudioClip.

* **Return type:**
  [`AudioClip`](#an.audio.tts.AudioClip)

### *class* an.audio.tts.VoiceMeta(voice_id, name, provider, language='en', gender=None, extra=<factory>)

Bases: `object`

Metadata for a TTS voice as exposed by a provider.
