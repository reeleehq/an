# an.audio.voice_listing

The voices a TTS provider offers, as rows a host can show and filter (an#712).

A host that lets a user cast a voice (reelee’s character voices) needs the same
few facts from every provider: an id, a name, a language, a gender, an accent,
a description, a sample to hear, and whether the voice is one of the provider’s
stock voices that nobody designed (`is_stock`) or one an account designed,
cloned, recorded or added from a shared voice library. Those facts are fields of
[`VoiceMeta`](an.audio.tts.html.md#an.audio.tts.VoiceMeta), which each provider fills in its own
`list_voices`; a row is its flat view, [`as_row()`](an.audio.tts.html.md#an.audio.tts.VoiceMeta.as_row)
([`VoiceRow`](#an.audio.voice_listing.VoiceRow)). So a host filters on a field rather than on a provider’s
category string, and a new provider adds itself by filling `VoiceMeta`.

Two listings, two shapes: [`list_voices()`](#an.audio.voice_listing.list_voices) (`an.audio.list_voices`) returns
rows, for a host; [`browse_voices()`](#an.audio.voice_listing.browse_voices) and a provider’s own `list_voices`
return [`VoiceMeta`](an.audio.tts.html.md#an.audio.tts.VoiceMeta).

```pycon
>>> rows = list_voices("offline")
>>> [(r["voice_id"], r["provider"], r["is_stock"]) for r in rows]
[('default', 'offline', True)]
```

### Functions

| [`browse_voices`](#an.audio.voice_listing.browse_voices)([provider, search, api_key, make])   | The voices `provider` exposes, optionally filtered by `search`.                                                                                |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| [`list_voices`](#an.audio.voice_listing.list_voices)(provider, \*[, api_key, search, make]) | The voices `provider` offers, as rows (an#712): [`browse_voices()`](#an.audio.voice_listing.browse_voices) through `VoiceMeta.as_row()`. |

### Classes

| [`VoiceRow`](#an.audio.voice_listing.VoiceRow)   | The keys of `VoiceMeta.as_row()`, typed for hosts (a plain `dict` at runtime); a test pins them to the dataclass.   |
|-------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|

### *class* an.audio.voice_listing.VoiceRow

Bases: [`TypedDict`](https://docs.python.org/3/library/typing.html#typing.TypedDict)

The keys of `VoiceMeta.as_row()`, typed for hosts (a plain `dict`
at runtime); a test pins them to the dataclass.

### an.audio.voice_listing.browse_voices(provider='elevenlabs', \*, search=None, api_key=None, make=<function make_tts>)

The voices `provider` exposes, optionally filtered by `search`.

A provider whose `list_voices` takes `search` (ElevenLabs) filters on
its server; for the others the filter is a case-insensitive substring over
the id, name, accent, description and labels.

`make` is the provider seam: `make(name)`, or `make(name,
api_key=api_key)` only when a key was given (so a `make` that takes no
key serves every keyless call); default [`an.audio.providers.make_tts()`](an.audio.providers.html.md#an.audio.providers.make_tts).
`api_key=None` means the provider’s own default (ElevenLabs: the
environment’s key); an empty key is refused (`ValueError`) rather than
read as “none”.

```pycon
>>> class Fake:
...     name = "fake"
...     def list_voices(self):
...         return [VoiceMeta("v1", "Ada", "fake"),
...                 VoiceMeta("v2", "Bob", "fake", description="adenoidal")]
>>> [v.name for v in browse_voices("fake", search="ad", make=lambda _: Fake())]
['Ada', 'Bob']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`VoiceMeta`](an.audio.tts.html.md#an.audio.tts.VoiceMeta)]

### an.audio.voice_listing.list_voices(provider, \*, api_key=None, search=None, make=<function make_tts>)

The voices `provider` offers, as rows (an#712): [`browse_voices()`](#an.audio.voice_listing.browse_voices)
through `VoiceMeta.as_row()`.

`api_key` is a host’s own key for a provider that takes one
([`an.audio.providers.listable_providers()`](an.audio.providers.html.md#an.audio.providers.listable_providers)); `None` means the
environment’s key, and `""` is refused (`ValueError`), so a host that
forwards a guest’s absent key never lists the server’s own account. A
provider that cannot be asked at all (its `check_available()` fails: no
key anywhere) raises its own typed error (ElevenLabs:
[`ElevenLabsUnavailableError`](an.audio.elevenlabs_tts.html.md#an.audio.elevenlabs_tts.ElevenLabsUnavailableError)) rather than
answering `[]`, so an empty listing means “no voices”. `search` and
`make` are as in [`browse_voices()`](#an.audio.voice_listing.browse_voices). An unknown provider is a
`ValueError` naming the known ones.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`VoiceRow`](#an.audio.voice_listing.VoiceRow)]
