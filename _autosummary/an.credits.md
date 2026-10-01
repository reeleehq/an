# an.credits

What a rendered video owes, and to whom.

`an` composes work it did not create into a video its user ships. Recording where
that work came from (`an.ir.assets.AssetSource`) is half the job; the other half
is being able to *produce* the credits, because \*\*a licence recorded and never
displayed is not compliance\*\* — it is a note to oneself.

So this module walks a project’s reachable assets and answers three questions a
user actually has:

- what third-party work is in this video?
- may I ship it at all? (an#211 — material that is all rights reserved, used
  for private study only, is recognised and said LOUDLY: the report opens with
  it, and a render that uses it ends with a warning that it is not
  publishable);
- what must I display, verbatim, to ship it?
- is anything in here unverified?

The last is the one that matters most and is easiest to lose. An asset with no
licence is reported as **UNKNOWN**, never as “nothing owed”: those are different
answers, and collapsing them is exactly how an obligation goes missing.

Public domain (`pd`, `public-domain`, `cc-pdm-1.0`, `cc0-*`) is recognised as
nothing owed, and an environment’s planes may each carry their own `source`,
so a composite stage — a carved plate plus a CC0 prop — credits both. A
character’s (or prop’s) attachments may too (an#220): a figure composed from
parts carved out of several clips credits each clip, part by part.

### Functions

| [`is_factory_stamp`](#an.credits.is_factory_stamp)(raw)                       | Whether a source is the character factory's own stamp (an#236, an#251).              |
|----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`is_generated_source`](#an.credits.is_generated_source)(raw)                    | Whether a descriptor's source was written by a generator rather than a person.       |
| [`collect_credits`](#an.credits.collect_credits)(mall, \*[, only])           | Walk a project mall and gather every recorded `AssetSource`.                         |
| [`credits_for_project`](#an.credits.credits_for_project)(project_dir)            | Credits for the project at `project_dir`.                                            |
| [`credits_for_scene`](#an.credits.credits_for_scene)(mall, scene)              | Credits for exactly the assets `scene` draws or plays (an#211).                      |
| [`speech_credits`](#an.credits.speech_credits)(mall, scene)                 | One entry per voice whose lines a render synthesized with a named provider (an#271). |
| [`warn_if_private_study`](#an.credits.warn_if_private_study)(report, \*[, output]) | Warn, loudly, when `report` holds private-study material.                            |

### Classes

| [`CreditsReport`](#an.credits.CreditsReport)([entries])   | Everything a project owes, split by whether we actually know.   |
|-----------------------------------------------------------------------------|-----------------------------------------------------------------|

### Exceptions

| [`PrivateStudyWarning`](#an.credits.PrivateStudyWarning)   | A render used material that is all rights reserved, private study only.   |
|------------------------------------------------------------------------|---------------------------------------------------------------------------|

### *class* an.credits.CreditsReport(entries=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Everything a project owes, split by whether we actually know.

#### format()

Human-readable, and honest about what it does not know.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### *property* owed *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[CreditEntry]*

Entries that definitely require an attribution.

#### *property* private *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[CreditEntry]*

all rights reserved, private
study only (an#211). A video containing any of them is not shippable,
whatever else it credits.

* **Type:**
  Entries that may NOT be published

#### *property* publishable *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

`False` when any entry is private-study material.

#### *property* unverified *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[CreditEntry]*

Entries whose licence we could not classify.

Deliberately its own list rather than folded into [`owed`](#an.credits.CreditsReport.owed). Folding
them in cries wolf; folding them into “nothing owed” hides a real
obligation. Neither is honest, so they are counted separately — the same
reason `priv`’s upkeep keeps `unavailable` apart from `findings`.

### *exception* an.credits.PrivateStudyWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A render used material that is all rights reserved, private study only.

Raised as a warning at the END of a render (an#211), so the last thing the
author reads about the mp4 is that it must not be published.

### an.credits.collect_credits(mall, , only=None)

Walk a project mall and gather every recorded `AssetSource`.

`only` restricts the walk to those `store/key` names (what a render
used, [`credits_for_scene()`](#an.credits.credits_for_scene)) — nothing else is read.

Four stores carry provenance: characters, **props** (an#108),
**environments** (an#110) and **sounds**. Each was added by the PR that gave that store
real art, which is the rule rather than a coincidence — a walk that skips a
store holding third-party plates does not return less information, it
returns an affirmative false statement to exactly the people who need the
opposite. **Sounds** joined with the sound layer (an#163) — a sound is
third-party work more often than any other asset. Styles will join when a
StylePack has art (#112).

Legacy reconstruction runs on characters only: it recovers a DiceBear
record from `metadata.dicebear_*`, which no other store has ever written.

* **Return type:**
  [`CreditsReport`](#an.credits.CreditsReport)

### an.credits.credits_for_project(project_dir)

Credits for the project at `project_dir`.

* **Return type:**
  [`CreditsReport`](#an.credits.CreditsReport)

### an.credits.credits_for_scene(mall, scene)

Credits for exactly the assets `scene` draws or plays (an#211).

[`collect_credits()`](#an.credits.collect_credits) walks the whole project; a render owes only what it
used, and a private-study plate sitting unused in the store must not make
an unrelated render “not publishable”. Kept: every entry under a
`store/ref` some shot’s entity names, and every sound a cue names.

* **Return type:**
  [`CreditsReport`](#an.credits.CreditsReport)

### an.credits.is_factory_stamp(raw)

Whether a source is the character factory’s own stamp (an#236, an#251).

The factory stamps every part it draws `cc0` with the part’s digest, and
the descriptor with its `source_svg`’s, so the asset library can tell its
shared parts from carved ones. It is `an`’s own work, not third-party: a
credits report lists what is OWED, and listing fifty generated parts per
character would bury the one carved head.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.credits.is_generated_source(raw)

Whether a descriptor’s source was written by a generator rather than a person.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> is_generated_source({"provider": "dicebear", "license": "cc0-1.0"})
True
>>> is_generated_source({"provider": "a-film", "license": "all-rights-reserved"})
False
```

### an.credits.speech_credits(mall, scene)

One entry per voice whose lines a render synthesized with a named provider (an#271).

Read from what the audio pipeline already keeps — no record of its own:
the scene’s lines that carry an `audio_ref` (stamped when synthesized),
each line’s voice as the pipeline resolves it
([`an.audio.voices.line_voice_id()`](an.audio.voices.md#an.audio.voices.line_voice_id)), and that voice’s document in
`mall["voices"]` (its `provider`, `voice_id` and `model_id`). A
voice document may declare its own `source` (the provider’s terms, the
licence the user holds); otherwise the speech is listed UNVERIFIED — the
provider’s terms decide what is owed, and nobody recorded them. A voice
whose document names no provider (the offline default) is not listed:
which provider spoke it is not recorded anywhere.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[`CreditEntry`]

```pycon
>>> from types import SimpleNamespace as NS
>>> line = NS(voice_ref="bob", speaker="bob", audio_ref="k1")
>>> scene = NS(timeline=[NS(dialogue=[line], entities=[])])
>>> mall = {"voices": {"bob": {"provider": "elevenlabs", "voice_id": "TX3",
...                            "model_id": "eleven_v3"}}}
>>> [(e.asset, e.license_class, e.source.extra["model"]) for e in speech_credits(mall, scene)]
[('speech/bob', 'unknown', 'eleven_v3')]
```

### an.credits.warn_if_private_study(report, , output=None)

Warn, loudly, when `report` holds private-study material.

Returns whether it warned. Called at the end of a render, so the warning is
the last word about the file; `output` names it.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
