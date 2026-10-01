# an.audio.providers

Provider factory: name → concrete TTS/LipSync provider instance.

Used by the CLI and orchestrator to map `--tts elevenlabs` (and similar)
strings into instantiated providers without callers having to import the
specific classes.

```pycon
>>> from an.audio.providers import make_tts, make_lipsync
>>> make_tts("offline").name
'offline'
>>> make_lipsync("offline").name
'offline'
```

### Module Attributes

| [`DEFAULT_LANGUAGE`](#an.audio.providers.DEFAULT_LANGUAGE)   | The language a provider aligns for when the caller says nothing.   |
|---------------------------------------------------------------------|--------------------------------------------------------------------|

### Functions

| [`known_lipsync_names`](#an.audio.providers.known_lipsync_names)()              | Return the registered LipSync provider names.   |
|-------------------------------------------------------------------------------------|-------------------------------------------------|
| [`known_tts_names`](#an.audio.providers.known_tts_names)()                  | Return the registered TTS provider names.       |
| [`make_lipsync`](#an.audio.providers.make_lipsync)(name, \*[, language]) | Instantiate a LipSync provider by name.         |
| [`make_tts`](#an.audio.providers.make_tts)(name)                     | Instantiate a TTS provider by name.             |

### an.audio.providers.DEFAULT_LANGUAGE *: str* *= 'en'*

The language a provider aligns for when the caller says nothing. Only
Rhubarb reads it today (its recognizer follows the language, an#96).

### an.audio.providers.known_lipsync_names()

Return the registered LipSync provider names.

* **Return type:**
  `list`[`str`]

### an.audio.providers.known_tts_names()

Return the registered TTS provider names.

* **Return type:**
  `list`[`str`]

### an.audio.providers.make_lipsync(name, , language='en')

Instantiate a LipSync provider by name.

`language` (BCP-47) reaches providers that select behaviour by language —
Rhubarb’s recognizer today; a future aligner’s weight allowlist.

* **Return type:**
  [`LipSyncProvider`](an.audio.lipsync.md#an.audio.lipsync.LipSyncProvider)

### an.audio.providers.make_tts(name)

Instantiate a TTS provider by name.

Raises `ValueError` for unknown names with a list of known options.

* **Return type:**
  [`TTSProvider`](an.audio.tts.md#an.audio.tts.TTSProvider)
