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

### Classes

| [`OfflineTTS`](#an.audio.offline_tts.OfflineTTS)(\*[, sample_rate, channels, ...])   | Default TTS provider: silent WAV of length proportional to text.   |
|-------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|

### *class* an.audio.offline_tts.OfflineTTS(, sample_rate=22050, channels=1, seconds_per_char=0.06)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Default TTS provider: silent WAV of length proportional to text.

Implements the `TTSProvider` protocol.
