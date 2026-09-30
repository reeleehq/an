# an.audio.cli

`an voices ...` — browse a TTS provider’s voices from the shell (an#209).

Thin string-typed wrappers dispatched by typer the way `an character ...` is;
the business logic is [`browse_voices()`](#an.audio.cli.browse_voices), a plain function over the
provider factories.

> an voices list –provider elevenlabs
> an voices list –provider elevenlabs –search british
> an voices list –provider mac_say

The `voice_id` column is what a `voices`-store document’s `voice_id` takes.

### Functions

| [`browse_voices`](#an.audio.cli.browse_voices)([provider, search, make])   | The voices `provider` exposes, optionally filtered by `search`.   |
|--------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| [`format_voices`](#an.audio.cli.format_voices)(voices)                     | One line per voice: `voice_id  name  (labels)`.                   |

### an.audio.cli.browse_voices(provider='elevenlabs', \*, search=None, make=<function make_tts>)

The voices `provider` exposes, optionally filtered by `search`.

A provider whose `list_voices` takes `search` (ElevenLabs) filters on
its server; for the others the filter is a case-insensitive substring over
the name, id and labels.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`VoiceMeta`](an.audio.tts.html.md#an.audio.tts.VoiceMeta)]

```pycon
>>> from an.audio.tts import VoiceMeta
>>> class Fake:
...     name = "fake"
...     def list_voices(self):
...         return [VoiceMeta("v1", "Ada", "fake"), VoiceMeta("v2", "Bob", "fake")]
>>> [v.name for v in browse_voices("fake", search="ad", make=lambda _: Fake())]
['Ada']
```

### an.audio.cli.format_voices(voices)

One line per voice: `voice_id  name  (labels)`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> from an.audio.tts import VoiceMeta
>>> print(format_voices([VoiceMeta("abc", "Ada", "x", extra={"labels": {"accent": "british"}})]))
abc  Ada  (accent=british)
```
