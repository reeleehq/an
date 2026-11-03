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

| [`TTS_FACTORIES`](#an.audio.providers.TTS_FACTORIES)     | A factory takes no arguments, or `mall=` when the provider reads a project store (`recorded`), or `api_key=` when a host may hand it its own key (`elevenlabs`): [`make_tts()`](#an.audio.providers.make_tts) passes each only to those that accept it, and [`listable_providers()`](#an.audio.providers.listable_providers) reads the latter, so a provider registered here with `api_key=` is listable by hosts with nothing else to change.   |
|--------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DEFAULT_LANGUAGE`](#an.audio.providers.DEFAULT_LANGUAGE)  | The language a provider aligns for when the caller says nothing.                                                                                                                                                                                                                                                                                                                                                                                                     |
| [`LIPSYNC_FACTORIES`](#an.audio.providers.LIPSYNC_FACTORIES) | The lip-sync providers the core itself offers.                                                                                                                                                                                                                                                                                                                                                                                                                       |
| [`DFLT_LIPSYNC`](#an.audio.providers.DFLT_LIPSYNC)      | The provider `default_lipsync()` prefers when a genre registered it.                                                                                                                                                                                                                                                                                                                                                                                                 |

### Functions

| [`known_lipsync_names`](#an.audio.providers.known_lipsync_names)()               | Return the registered LipSync provider names.                                                                  |
|--------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| [`known_tts_names`](#an.audio.providers.known_tts_names)()                   | Return the registered TTS provider names.                                                                      |
| [`lipsync_factories`](#an.audio.providers.lipsync_factories)()                 | Every lip-sync factory by name: the core's, then the loaded genres' services.                                  |
| [`listable_providers`](#an.audio.providers.listable_providers)(\*[, factories]) | The TTS providers a host may list voices from with its own key: those whose factory takes `api_key=` (an#712). |
| [`make_lipsync`](#an.audio.providers.make_lipsync)(name, \*[, language])  | Instantiate a LipSync provider by name.                                                                        |
| [`make_tts`](#an.audio.providers.make_tts)(name, \*[, mall, api_key]) | Instantiate a TTS provider by name.                                                                            |

### an.audio.providers.DEFAULT_LANGUAGE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'en'*

The language a provider aligns for when the caller says nothing. Only
Rhubarb reads it today (its recognizer follows the language, an#96).

### an.audio.providers.DFLT_LIPSYNC *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'offline'*

The provider `default_lipsync()` prefers when a genre registered it.

### an.audio.providers.LIPSYNC_FACTORIES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[..., [LipSyncProvider](an.audio.lipsync.html.md#an.audio.lipsync.LipSyncProvider)]]* *= {'none': <function <lambda>>}*

The lip-sync providers the core itself offers. A genre adds its own through
the `lipsync.<name>` service (`cutan`: `offline`, `rhubarb`,
`whisper`); see [`lipsync_factories()`](#an.audio.providers.lipsync_factories).

### an.audio.providers.TTS_FACTORIES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[..., [TTSProvider](an.audio.tts.html.md#an.audio.tts.TTSProvider)]]* *= {'elevenlabs': <function <lambda>>, 'mac_say': <function <lambda>>, 'offline': <function <lambda>>, 'recorded': <function \_recorded_factory>}*

A factory takes no arguments, or `mall=` when the provider reads a project
store (`recorded`), or `api_key=` when a host may hand it its own key
(`elevenlabs`): [`make_tts()`](#an.audio.providers.make_tts) passes each only to those that accept it,
and [`listable_providers()`](#an.audio.providers.listable_providers) reads the latter, so a provider registered
here with `api_key=` is listable by hosts with nothing else to change.

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
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`LipSyncProvider`](an.audio.lipsync.html.md#an.audio.lipsync.LipSyncProvider)]]

### an.audio.providers.listable_providers(\*, factories={'elevenlabs': <function <lambda>>, 'mac_say': <function <lambda>>, 'offline': <function <lambda>>, 'recorded': <function \_recorded_factory>})

The TTS providers a host may list voices from with its own key: those
whose factory takes `api_key=` (an#712). Hand one, with the key, to
[`an.audio.list_voices()`](an.audio.html.md#an.audio.list_voices).

```pycon
>>> listable_providers()
['elevenlabs']
>>> listable_providers(factories={"a": lambda *, api_key=None: None, "b": lambda: None})
['a']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.audio.providers.make_lipsync(name, , language='en')

Instantiate a LipSync provider by name.

`language` (BCP-47) reaches providers that select behaviour by language —
Rhubarb’s recognizer today; a future aligner’s weight allowlist.

The default name (`"offline"`) resolves to [`NullLipSync`](an.audio.lipsync.html.md#an.audio.lipsync.NullLipSync)
when no loaded genre provides it, so voicing a line needs no genre; any other
name that nothing provides is an error that says how to get it.

```pycon
>>> make_lipsync("offline").name in {"offline", "none"}
True
```

* **Return type:**
  [`LipSyncProvider`](an.audio.lipsync.html.md#an.audio.lipsync.LipSyncProvider)

### an.audio.providers.make_tts(name, , mall=None, api_key=None)

Instantiate a TTS provider by name.

`mall` (the project mall) reaches the factories that take it — the
`recorded` provider reads the project’s `recordings` store; `api_key`
(a host’s own key) reaches those that take one (ElevenLabs, an#712); the
others are built as before. Raises `ValueError` for unknown names with a
list of known options.

```pycon
>>> make_tts("recorded").name
'recorded'
```

* **Return type:**
  [`TTSProvider`](an.audio.tts.html.md#an.audio.tts.TTSProvider)
