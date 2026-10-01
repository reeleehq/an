# an.audio.offline_tts

OfflineTTS — produces silent audio of plausible duration. No network, no keys.

This is the **default** TTS provider for `an`. It’s honest about being silent
(it doesn’t pretend to speak), but it produces a real WAV file with the right
duration so the rest of the pipeline (lip-sync, rendering, mp4 muxing) runs
end-to-end without any API setup.

Use `ElevenLabsTTS` for real speech once you’ve set `ELEVEN_API_KEY`.

```pycon
>>> tts = OfflineTTS()
>>> clip = tts.synthesize("Hello, world!", voice_id="default")
>>> clip.duration > 0.0
True
>>> clip.transcript
'Hello, world!'
```

### Functions

| [`estimate_speech_duration`](#an.audio.offline_tts.estimate_speech_duration)(text, \*[, ...])   | Seconds the offline voice takes to say `text` — a leading pad plus a per-character rate over the non-space characters, clamped.   |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|

### Classes

| [`OfflineTTS`](#an.audio.offline_tts.OfflineTTS)(\*[, sample_rate, channels, ...])   | Default TTS provider: silent WAV of length proportional to text.   |
|-------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|

### *class* an.audio.offline_tts.OfflineTTS(, sample_rate=22050, channels=1, seconds_per_char=0.06)

Bases: `object`

Default TTS provider: silent WAV of length proportional to text.

Implements the `TTSProvider` protocol.

### an.audio.offline_tts.estimate_speech_duration(text, , seconds_per_char=0.06)

Seconds the offline voice takes to say `text` — a leading pad plus a
per-character rate over the non-space characters, clamped.

It is exactly what an offline render gives a line, so `an validate` uses
it to warn about a shot too short for its dialogue BEFORE anything is
synthesized. A real voice is usually a little slower, so for one this is an
under-estimate: a line it says overruns will overrun.

* **Return type:**
  `float`

```pycon
>>> round(estimate_speech_duration("It only takes exact change."), 3)
1.43
```
