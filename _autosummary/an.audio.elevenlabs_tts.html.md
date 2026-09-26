# an.audio.elevenlabs_tts

ElevenLabsTTS — real speech via the ElevenLabs API. Requires ELEVEN_API_KEY.

Lazily imports the elevenlabs SDK so the rest of `an` works without it.
If you want real speech, `pip install elevenlabs` and set
`ELEVEN_API_KEY` (or `ELEVENLABS_API_KEY`) in your environment.

### Classes

| [`ElevenLabsTTS`](#an.audio.elevenlabs_tts.ElevenLabsTTS)(\*[, api_key, model_id, ...])   | ElevenLabs-backed TTSProvider.   |
|------------------------------------------------------------------------------------------------|----------------------------------|

### *class* an.audio.elevenlabs_tts.ElevenLabsTTS(, api_key=None, model_id='eleven_turbo_v2_5', output_format='mp3_44100_128')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

ElevenLabs-backed TTSProvider. Constructor takes an optional api_key
(falls back to `ELEVEN_API_KEY` / `ELEVENLABS_API_KEY`).

Implements the `TTSProvider` protocol.
