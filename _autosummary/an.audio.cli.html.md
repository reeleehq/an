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
> an voices design <project>                      # design options from each voice’s notes (billed)
> an voices choose <project> jerry_voice B –by noel   # the writer’s pick becomes the voice_id (recorded)
> an voices cast <project> paul_voice <voice_id> –by noel   # a voice picked by hand, recorded the same way
> an voices import <project> takes/ –transcript takes/ –license cc-by-4.0 –recorded-by “J. Doe”

> > # a performer’s recording becomes the voice (an#490)

The `voice_id` column is what a `voices`-store document’s `voice_id` takes.
`rescore` and `reroll` are the only ways a recorded best-of-N take is
replaced ([`an.audio.pipeline.retake_lines()`](an.audio.pipeline.html.md#an.audio.pipeline.retake_lines)); the next `an render` does
the choosing, and prints what it will bill first.

### Functions

| [`browse_voices`](#an.audio.cli.browse_voices)([provider, search, make])         | The voices `provider` exposes, optionally filtered by `search`.                                                                                                                                                                                     |
|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`format_voices`](#an.audio.cli.format_voices)(voices)                           | One line per voice: `voice_id  name  (labels)`.                                                                                                                                                                                                     |
| [`retake`](#an.audio.cli.retake)(project, line, \*[, rescore, tts, make]) | Release the recorded takes of the lines of `project` containing `line`.                                                                                                                                                                             |
| [`import_recorded`](#an.audio.cli.import_recorded)(project, audio[, ...])          | Import a performer's recording as the voice of its lines: each line is cut out, matched to the scene's dialogue (or added to --shot), stored with its provenance, and the speaker's character speaks with it — nothing synthesized, nothing billed. |

### an.audio.cli.browse_voices(provider='elevenlabs', \*, search=None, make=<function make_tts>)

The voices `provider` exposes, optionally filtered by `search`.

A provider whose `list_voices` takes `search` (ElevenLabs) filters on
its server; for the others the filter is a case-insensitive substring over
the name, id and labels.

```pycon
>>> from an.audio.tts import VoiceMeta
>>> class Fake:
...     name = "fake"
...     def list_voices(self):
...         return [VoiceMeta("v1", "Ada", "fake"), VoiceMeta("v2", "Bob", "fake")]
>>> [v.name for v in browse_voices("fake", search="ad", make=lambda _: Fake())]
['Ada']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`VoiceMeta`](an.audio.tts.html.md#an.audio.tts.VoiceMeta)]

### an.audio.cli.format_voices(voices)

One line per voice: `voice_id  name  (labels)`.

```pycon
>>> from an.audio.tts import VoiceMeta
>>> print(format_voices([VoiceMeta("abc", "Ada", "x", extra={"labels": {"accent": "british"}})]))
abc  Ada  (accent=british)
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.cli.import_recorded(project, audio, transcript='', speaker='', speakers='', shot='', voice='', denoise=False, license='', recorded_by='', transcriber='', diarize=False)

Import a performer’s recording as the voice of its lines: each line is cut out,
matched to the scene’s dialogue (or added to –shot), stored with its provenance,
and the speaker’s character speaks with it — nothing synthesized, nothing billed.

project: the project directory
audio: the take(s): a file, a directory, a glob, or comma-separated files (one take with several lines, or one file per line)
transcript: SRT / WebVTT / TextGrid / word JSON (timed: no transcribing) or plain `speaker: text` lines; a directory pairs by stem
speaker: the one character every take belongs to
speakers: label=character pairs for a transcript’s or diarizer’s labels and file stems, e.g. spk_0=carl,spk_1=ned
shot: the shot new lines go into (takes matching no scene line)
voice: the recorded voice document to bind (default <speaker>_recorded)
denoise: clean each file first (ffmpeg afftdn)
license: REQUIRED — the licence or permission code you vouch for (cc0-1.0, cc-by-4.0, all-rights-reserved, unknown)
recorded_by: who recorded the take (the performer), for the credits
transcriber: the scribed backend when a take must be transcribed (default: scribed’s default)
diarize: ask the transcriber for speaker labels (map them with –speakers)

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.cli.retake(project, line, \*, rescore=False, tts='elevenlabs', make=<function make_tts>)

Release the recorded takes of the lines of `project` containing `line`.

The plain-function core of `an voices rescore` / `an voices reroll`: see
[`an.audio.pipeline.retake_lines()`](an.audio.pipeline.html.md#an.audio.pipeline.retake_lines). `tts` must be the provider the
line is rendered with (its takes are keyed by it).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
