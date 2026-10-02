# an.audio.providers

Provider factory: name → concrete TTS/LipSync provider instance.

Used by the CLI and orchestrator to map `--tts elevenlabs` (and similar)
strings into instantiated providers without callers having to import the
specific classes.

```pycon
>>> from an.audio.providers import make_tts, make_lipsync
>>> make_tts("offline").name
'offline'
>>> make_lipsync("none").name
'none'
```

### Module Attributes

| [`DEFAULT_LANGUAGE`](#an.audio.providers.DEFAULT_LANGUAGE)   | The language a provider aligns for when the caller says nothing.     |
|---------------------------------------------------------------------|----------------------------------------------------------------------|
| [`LIPSYNC_FACTORIES`](#an.audio.providers.LIPSYNC_FACTORIES)  | The lip-sync providers the core itself offers.                       |
| [`DFLT_LIPSYNC`](#an.audio.providers.DFLT_LIPSYNC)       | The provider `default_lipsync()` prefers when a genre registered it. |

### Functions

| [`known_lipsync_names`](#an.audio.providers.known_lipsync_names)()              | Return the registered LipSync provider names.                                 |
|-------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`known_tts_names`](#an.audio.providers.known_tts_names)()                  | Return the registered TTS provider names.                                     |
| [`lipsync_factories`](#an.audio.providers.lipsync_factories)()                | Every lip-sync factory by name: the core's, then the loaded genres' services. |
| [`make_lipsync`](#an.audio.providers.make_lipsync)(name, \*[, language]) | Instantiate a LipSync provider by name.                                       |
| [`make_tts`](#an.audio.providers.make_tts)(name)                     | Instantiate a TTS provider by name.                                           |

### an.audio.providers.DEFAULT_LANGUAGE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'en'*

The language a provider aligns for when the caller says nothing. Only
Rhubarb reads it today (its recognizer follows the language, an#96).

### an.audio.providers.DFLT_LIPSYNC *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'offline'*

The provider `default_lipsync()` prefers when a genre registered it.

### an.audio.providers.LIPSYNC_FACTORIES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[[...], [LipSyncProvider](an.audio.lipsync.md#an.audio.lipsync.LipSyncProvider)]]* *= {'none': <function <lambda>>}*

The lip-sync providers the core itself offers. A genre adds its own through
the `lipsync.<name>` service (`cutan`: `offline`, `rhubarb`,
`whisper`); see [`lipsync_factories()`](#an.audio.providers.lipsync_factories).

### an.audio.providers.known_lipsync_names()

Return the registered LipSync provider names.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.audio.providers.known_tts_names()

Return the registered TTS provider names.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.audio.providers.lipsync_factories()

Every lip-sync factory by name: the core’s, then the loaded genres’ services.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`LipSyncProvider`](an.audio.lipsync.md#an.audio.lipsync.LipSyncProvider)]]

### an.audio.providers.make_lipsync(name, , language='en')

Instantiate a LipSync provider by name.

`language` (BCP-47) reaches providers that select behaviour by language —
Rhubarb’s recognizer today; a future aligner’s weight allowlist.

The default name (`"offline"`) resolves to [`NullLipSync`](an.audio.lipsync.md#an.audio.lipsync.NullLipSync)
when no loaded genre provides it, so voicing a line needs no genre; any other
name that nothing provides is an error that says how to get it.

* **Return type:**
  [`LipSyncProvider`](an.audio.lipsync.md#an.audio.lipsync.LipSyncProvider)

```pycon
>>> make_lipsync("offline").name in {"offline", "none"}
True
```

### an.audio.providers.make_tts(name)

Instantiate a TTS provider by name.

Raises `ValueError` for unknown names with a list of known options.

* **Return type:**
  [`TTSProvider`](an.audio.tts.md#an.audio.tts.TTSProvider)
