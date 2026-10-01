# an.audio.cli

`an voices ...` — browse a TTS provider’s voices from the shell (an#209).

Thin string-typed wrappers dispatched by typer the way `an character ...` is;
the business logic is [`browse_voices()`](#an.audio.cli.browse_voices), a plain function over the
provider factories.

> an voices list –provider elevenlabs
> an voices list –provider elevenlabs –search british
> an voices list –provider mac_say
> an voices rescore <project> “He did not ask”    # re-choose a line’s take from its cached takes
> an voices reroll <project> “He did not ask”     # synthesize new takes for it (billed)

The `voice_id` column is what a `voices`-store document’s `voice_id` takes.
`rescore` and `reroll` are the only ways a recorded best-of-N take is
replaced ([`an.audio.pipeline.retake_lines()`](an.audio.pipeline.html.md#an.audio.pipeline.retake_lines)); the next `an render` does
the choosing, and prints what it will bill first.

### Functions

| [`browse_voices`](#an.audio.cli.browse_voices)([provider, search, make])         | The voices `provider` exposes, optionally filtered by `search`.         |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`format_voices`](#an.audio.cli.format_voices)(voices)                           | One line per voice: `voice_id  name  (labels)`.                         |
| [`retake`](#an.audio.cli.retake)(project, line, \*[, rescore, tts, make]) | Release the recorded takes of the lines of `project` containing `line`. |

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

### an.audio.cli.retake(project, line, \*, rescore=False, tts='elevenlabs', make=<function make_tts>)

Release the recorded takes of the lines of `project` containing `line`.

The plain-function core of `an voices rescore` / `an voices reroll`: see
[`an.audio.pipeline.retake_lines()`](an.audio.pipeline.html.md#an.audio.pipeline.retake_lines). `tts` must be the provider the
line is rendered with (its takes are keyed by it).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
