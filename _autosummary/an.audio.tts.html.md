# an.audio.tts

TTS provider protocol + supporting dataclasses.

### Classes

| [`AudioClip`](#an.audio.tts.AudioClip)([path, bytes_, duration, ...])   | A rendered audio clip, on disk or in memory.       |
|---------------------------------------------------------------------------------------------|----------------------------------------------------|
| [`TTSProvider`](#an.audio.tts.TTSProvider)(\*args, \*\*kwargs)            | Text-to-speech provider.                           |
| [`VoiceMeta`](#an.audio.tts.VoiceMeta)(voice_id, name, provider[, ...]) | Metadata for a TTS voice as exposed by a provider. |

### *class* an.audio.tts.AudioClip(path=None, bytes_=None, duration=0.0, sample_rate=44100, channels=1, voice_id=None, transcript=None, words=None, phones=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A rendered audio clip, on disk or in memory.

#### phones *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The clip’s phone timings, `(phone, start_s, end_s)` from the clip’s
start, when an aligner gave them (a TextGrid’s `phones` tier on a
recorded take, an#491); `None` otherwise. A lip-sync provider that
maps phones to mouth shapes can use them instead of spreading letters.

#### words *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The clip’s word timings — `(word, start_s, end_s)` from the clip’s
start — when the provider knows them (a recorded take imported with a
timed transcript: [`an.audio.recorded`](an.audio.recorded.html.md#module-an.audio.recorded)); `None` otherwise. A
lip-sync provider that aligns from words prefers these to its own
transcription, and the audio pipeline stamps them on the line.

### *class* an.audio.tts.TTSProvider(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Text-to-speech provider.

#### list_voices()

Return all voices the provider exposes.

* **Return type:**
  [`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[[`VoiceMeta`](#an.audio.tts.VoiceMeta)]

#### synthesize(text, voice_id, \*\*kw)

Render `text` in `voice_id`’s voice. Returns an AudioClip.

* **Return type:**
  [`AudioClip`](#an.audio.tts.AudioClip)

### *class* an.audio.tts.VoiceMeta(voice_id, name, provider, language='en', gender=None, extra=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Metadata for a TTS voice as exposed by a provider.
