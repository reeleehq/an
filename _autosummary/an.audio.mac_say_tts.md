# an.audio.mac_say_tts

MacSayTTS — audible offline speech via macOS’s built-in `say` command.

Free, local, no API keys, no Python deps. macOS-only. The `say` binary
ships with every macOS install since at least 10.4. Voices are listed
by `say -v '?'` and can be passed as `voice_id`; common defaults:
`"Samantha"`, `"Daniel"`, `"Karen"`, `"Alex"`.

Output is 16-bit little-endian PCM WAV at 22050 Hz so the rest of the
audio pipeline (which prefers WAV) can read frames + duration directly.

```pycon
>>> tts = MacSayTTS()
>>> tts.name
'mac_say'
```

### Classes

| [`MacSayTTS`](#an.audio.mac_say_tts.MacSayTTS)(\*[, default_voice_id, ...])   | macOS `say`-backed TTSProvider.   |
|-------------------------------------------------------------------------------------------|-----------------------------------|

### Exceptions

| [`MacSayTTSError`](#an.audio.mac_say_tts.MacSayTTSError)   | Raised when the `say` subprocess fails.   |
|-------------------------------------------------------------------|-------------------------------------------|

### *class* an.audio.mac_say_tts.MacSayTTS(, default_voice_id='Samantha', sample_rate=22050, rate_wpm=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

macOS `say`-backed TTSProvider.

Implements the `TTSProvider` protocol. Audible, deterministic, and
fully offline — uses Apple’s voice synthesis bundled with the OS.

### *exception* an.audio.mac_say_tts.MacSayTTSError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when the `say` subprocess fails.
