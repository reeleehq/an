# an.audio.voice_design

Design a project’s voices from their written notes, then let the writer choose.

A voice document (`assets/voices/<ref>.json`) may carry the voice in words:
`notes` (age, accent, pitch, pace, attitude) and, optionally,
`sample_text` (what the samples say). Voice design turns those words into
candidate voices the writer can LISTEN to, and the writer’s choice becomes the
document’s `voice_id`. That is how a regional accent gets cast by the one
person who can hear it (a local ear for a local accent), with nobody else
picking from a stock library.

Two steps, both plain functions over injected stores:

- [`design_voice_options()`](#an.audio.voice_design.design_voice_options): per voice, ask a *designer* for previews of its
  notes speaking its sample text, store each preview’s audio in `samples` and
  return the options manifest (`{ref: {"notes", "sample_text", "design_model",
  "options": [{"option": "A", "generated_voice_id", "voice_id", "sample",
  "duration_s"}]}}`). With `persist=True` (the default) every preview is saved
  as a durable provider voice at once, because a provider’s previews expire; with
  `persist=False` only the chosen one is, later (fewer voices in the account,
  but a choice must come before the previews expire).
- [`choose_voice_option()`](#an.audio.voice_design.choose_voice_option): the `voice_id` of the chosen option (saving it
  as a voice first when it was not persisted).

**A choice is recorded, and a render needs one** (an#486). A voice written in
words (`notes`) is cast by the writer, nobody else: `an voices choose`
writes `chosen_by` and `chosen_at` beside the `voice_id`
([`record_choice()`](#an.audio.voice_design.record_choice)), and a voice document that has `notes` but no
recorded choice is a render finding, refused under `--strict-assets` before
anything is synthesized ([`voice_casting_problem()`](#an.audio.voice_design.voice_casting_problem)). A timing draft may
speak a stand-in voice only with an explicit `provisional` (`true`, or a
string saying why), which every render report lists.

The project-level forms, [`design_project_voices()`](#an.audio.voice_design.design_project_voices) and
[`choose_project_voice()`](#an.audio.voice_design.choose_project_voice), keep the manifest in
`artifacts/voice_options/<ref>.json`, the samples in
`artifacts/voice_samples/<ref>_<option>.mp3`, and write the chosen `voice_id`
(and `provider`) into the voice document. `an voices design` and `an voices
choose` are their CLI.

The designer is a seam (`designer=`): by default
[`ElevenLabsVoiceDesigner`](#an.audio.voice_design.ElevenLabsVoiceDesigner) (ElevenLabs Voice Design through the
`elevenlabs` SDK an’s ElevenLabs TTS already uses; key in `ELEVEN_API_KEY`).
voxy’s `ElevenLabsSpeechModel` is a drop-in (`designer=voxy.get_speech_model("elevenlabs")`),
not the default because voxy brings torch. Anything with these two methods works:

```default
design_voice_previews(description, *, text, model_id) -> [preview]   # preview.generated_voice_id, .audio, .duration_s
design_voice(description, *, preview, name) -> profile                # profile.segment is the voice id
```

Designing is billed by the provider; nothing here is called by a render.

```pycon
>>> class Fake:
...     def design_voice_previews(self, description, *, text=None, model_id=None):
...         from types import SimpleNamespace as N
...         return [N(generated_voice_id=f"g{i}", audio=b"ID3", duration_s=1.0) for i in range(2)]
...     def design_voice(self, description, *, preview, name):
...         from types import SimpleNamespace as N
...         return N(segment="v-" + getattr(preview, "generated_voice_id", preview))
>>> samples = {}
>>> notes = "A man in his fifties from rural Yorkshire, warm and unhurried."
>>> manifest = design_voice_options({"jerry": {"notes": notes}}, samples=samples, designer=Fake())
>>> [(o["option"], o["voice_id"], o["sample"]) for o in manifest["jerry"]["options"]]
[('A', 'v-g0', 'jerry_A'), ('B', 'v-g1', 'jerry_B')]
>>> sorted(samples)
['jerry_A', 'jerry_B']
>>> choose_voice_option(manifest["jerry"], "B", designer=Fake())
'v-g1'
```

### Functions

| [`cast_project_voice`](#an.audio.voice_design.cast_project_voice)(project_dir, ref[, ...])        | Record a voice picked by hand (from `an voices list`, or the document's own `voice_id`) as the writer's choice for `ref`: `voice_id` (default: the one the document already names), `chosen_by`, `chosen_at`; no options manifest needed and nothing billed.                                                                                                                        |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`choose_project_voice`](#an.audio.voice_design.choose_project_voice)(project_dir, ref, option, \*) | Write the chosen option's `voice_id` into `assets/voices/<ref>.json`, with who chose it (`by`, default the login name) and when (`at`, default now; [`record_choice()`](#an.audio.voice_design.record_choice)); return the document.                                                                                                                                         |
| [`choose_voice_option`](#an.audio.voice_design.choose_voice_option)(entry, option, \*[, ref, ...]) | The provider `voice_id` of `option` in one voice's manifest `entry`.                                                                                                                                                                                                                                                                                                                |
| [`default_chooser`](#an.audio.voice_design.default_chooser)()                                  | Who a choice is recorded as when nobody is named: the login name.                                                                                                                                                                                                                                                                                                                   |
| [`default_designer`](#an.audio.voice_design.default_designer)(\*[, api_key])                    | The designer used when none is given: [`ElevenLabsVoiceDesigner`](#an.audio.voice_design.ElevenLabsVoiceDesigner).                                                                                                                                                                                                                                                                     |
| [`design_project_voices`](#an.audio.voice_design.design_project_voices)(project_dir[, refs, ...])    | Design options for the project's voices; write manifests and samples; return the manifest.                                                                                                                                                                                                                                                                                          |
| [`design_voice_options`](#an.audio.voice_design.design_voice_options)(voices, \*, samples[, ...])   | Design options for each voice with notes; return the options manifest.                                                                                                                                                                                                                                                                                                              |
| [`designable_voices`](#an.audio.voice_design.designable_voices)(voices[, refs])                  | The voice documents (of `refs`, else all) that carry `notes`.                                                                                                                                                                                                                                                                                                                       |
| [`provisional_reason`](#an.audio.voice_design.provisional_reason)(doc)                            | Why `doc` speaks a voice nobody chose (its `provisional`, as text), or `None` when it is not provisional.                                                                                                                                                                                                                                                                           |
| [`record_choice`](#an.audio.voice_design.record_choice)(doc, voice_id, \*[, by, at, ...])    | The voice document with `voice_id` chosen by `by` at `at` (default: now, UTC): `chosen_by` and `chosen_at` beside the `voice_id`, the `provider` set when given (`None`, the default, keeps the document's: a designed option passes `DESIGN_PROVIDER`; a hand-picked voice of another provider passes nothing), and `provisional` dropped, since a choice is what it stood in for. |
| [`sample_text_from_lines`](#an.audio.voice_design.sample_text_from_lines)(lines, \*[, limit])         | A sample text from a voice's own dialogue lines, or `None` when they are too short for a provider preview (then the provider writes one).                                                                                                                                                                                                                                           |
| [`sample_text_of`](#an.audio.voice_design.sample_text_of)(doc[, fallback])                    | The document's `sample_text` (clipped), else `fallback`.                                                                                                                                                                                                                                                                                                                            |
| [`voice_casting`](#an.audio.voice_design.voice_casting)(voice_refs, voices)                  | `(uncast, provisional)`: one message per distinct voice of `voice_refs` (the voices a scene's lines speak with) that a render must not speak as it stands, and one per voice it speaks provisionally.                                                                                                                                                                               |
| [`voice_casting_problem`](#an.audio.voice_design.voice_casting_problem)(doc)                         | Why a render must not speak `doc` as it stands, or `None`.                                                                                                                                                                                                                                                                                                                          |

### Classes

| [`ElevenLabsVoiceDesigner`](#an.audio.voice_design.ElevenLabsVoiceDesigner)(\*[, api_key, ...])   | ElevenLabs Voice Design through the `elevenlabs` SDK (what an's ElevenLabs TTS already uses): the default designer, with voxy's two-method shape.   |
|------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|

### Exceptions

| [`VoiceDesignError`](#an.audio.voice_design.VoiceDesignError)   | A voice that cannot be designed or chosen (no notes, an unknown option, ...).   |
|---------------------------------------------------------------------|---------------------------------------------------------------------------------|

### *class* an.audio.voice_design.ElevenLabsVoiceDesigner(, api_key=None, client_factory=None, timeout_s=120)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

ElevenLabs Voice Design through the `elevenlabs` SDK (what an’s ElevenLabs
TTS already uses): the default designer, with voxy’s two-method shape.

api_key: defaults to `ELEVEN_API_KEY` / `ELEVENLABS_API_KEY`
client_factory: `api_key -> client`; tests inject a fake so nothing is billed

#### delete_voice(voice_id)

Remove a saved voice from the account (a choice the writer replaced).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### design_voice(description, , preview, name)

Save `preview` (or its `generated_voice_id`) as an account voice; `.segment` is its id.

#### design_voice_previews(description, , text=None, model_id='eleven_ttv_v3')

Previews (`generated_voice_id`, `audio` mp3 bytes, `duration_s`) of `description`.

### *exception* an.audio.voice_design.VoiceDesignError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A voice that cannot be designed or chosen (no notes, an unknown option, …).

### an.audio.voice_design.cast_project_voice(project_dir, ref, voice_id=None, , by=None, at=None, provider=None)

Record a voice picked by hand (from `an voices list`, or the document’s
own `voice_id`) as the writer’s choice for `ref`: `voice_id` (default:
the one the document already names), `chosen_by`, `chosen_at`; no
options manifest needed and nothing billed. `provider` sets the
document’s when given. Returns the document.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.audio.voice_design.choose_project_voice(project_dir, ref, option, , designer=None, by=None, at=None)

Write the chosen option’s `voice_id` into `assets/voices/<ref>.json`,
with who chose it (`by`, default the login name) and when (`at`, default
now; [`record_choice()`](#an.audio.voice_design.record_choice)); return the document.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.audio.voice_design.choose_voice_option(entry, option, , ref='', designer=None)

The provider `voice_id` of `option` in one voice’s manifest `entry`.

An option that was not persisted is saved as a voice now (its preview must
not have expired).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.voice_design.default_chooser()

Who a choice is recorded as when nobody is named: the login name.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.voice_design.default_designer(, api_key=None)

The designer used when none is given: [`ElevenLabsVoiceDesigner`](#an.audio.voice_design.ElevenLabsVoiceDesigner).

* **Return type:**
  [`ElevenLabsVoiceDesigner`](#an.audio.voice_design.ElevenLabsVoiceDesigner)

### an.audio.voice_design.design_project_voices(project_dir, refs=None, , designer=None, model_id='eleven_ttv_v3', persist=True, name_prefix=None)

Design options for the project’s voices; write manifests and samples; return the manifest.

A voice document without `sample_text` speaks its own lines from the scene.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### an.audio.voice_design.design_voice_options(voices, , samples, refs=None, designer=None, model_id='eleven_ttv_v3', persist=True, name_prefix='an', lines_of=None)

Design options for each voice with notes; return the options manifest.

voices: `{ref: voice document}` (a project’s `voices` store)
samples: where each option’s audio goes, keyed `<ref>_<option>` (mp3 bytes)
refs: the voices to design (default: every one with `notes`)
designer: a two-method designer (default: [`default_designer()`](#an.audio.voice_design.default_designer))
model_id: the provider’s voice-design model
persist: save every option as a durable voice now (else only the chosen one, later)
name_prefix: prefix of the saved voices’ names in the provider account
lines_of: `ref -> that voice's dialogue lines`, for a sample text when the

> document has none (else the provider writes one)
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### an.audio.voice_design.designable_voices(voices, refs=None)

The voice documents (of `refs`, else all) that carry `notes`.

Raise [`VoiceDesignError`](#an.audio.voice_design.VoiceDesignError) for a named ref that is missing or has no
usable notes; skip the unnamed ones silently.

```pycon
>>> designable_voices({"a": {"notes": "x" * 30}, "b": {}})
{'a': {'notes': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'}}
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)]

### an.audio.voice_design.provisional_reason(doc)

Why `doc` speaks a voice nobody chose (its `provisional`, as text), or
`None` when it is not provisional.

```pycon
>>> provisional_reason({"provisional": "timing draft"}), provisional_reason({"provisional": True})
('timing draft', 'provisional')
>>> provisional_reason({"provisional": False}) is None, provisional_reason({}) is None
(True, True)
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.voice_design.record_choice(doc, voice_id, , by=None, at=None, provider=None)

The voice document with `voice_id` chosen by `by` at `at` (default:
now, UTC): `chosen_by` and `chosen_at` beside the `voice_id`, the
`provider` set when given (`None`, the default, keeps the document’s:
a designed option passes `DESIGN_PROVIDER`; a hand-picked voice of
another provider passes nothing), and `provisional` dropped, since a
choice is what it stood in for. `by` defaults to the login name, which
says nothing about the writer: a connector or an agent choosing on a
writer’s behalf passes the writer’s name.

```pycon
>>> doc = record_choice({"notes": "a warm voice", "provisional": True}, "v1",
...                     by="noel", at="2026-10-20T22:00:00+00:00", provider="elevenlabs")
>>> doc == {"notes": "a warm voice", "provider": "elevenlabs", "voice_id": "v1",
...         "chosen_by": "noel", "chosen_at": "2026-10-20T22:00:00+00:00"}
True
>>> record_choice({"provider": "mac_say"}, "Junior", by="noel", at="t")["provider"]
'mac_say'
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.audio.voice_design.sample_text_from_lines(lines, , limit=1000)

A sample text from a voice’s own dialogue lines, or `None` when they are
too short for a provider preview (then the provider writes one).

```pycon
>>> sample_text_from_lines(["Hi."]) is None
True
>>> len(sample_text_from_lines(["That's a big mountain over there, I'd say."] * 5)) >= 100
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.voice_design.sample_text_of(doc, fallback=None)

The document’s `sample_text` (clipped), else `fallback`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.voice_design.voice_casting(voice_refs, voices)

`(uncast, provisional)`: one message per distinct voice of `voice_refs`
(the voices a scene’s lines speak with) that a render must not speak as it
stands, and one per voice it speaks provisionally. Each message starts
with `voice '<ref>'` and the uncast ones name the fix.

```pycon
>>> voices = {"j": {"notes": "n", "voice_id": "v"}, "p": {"notes": "n", "voice_id": "v",
...           "provisional": "round-2 timing draft"}, "k": {"voice_id": "x"}}
>>> uncast, provisional = voice_casting(["j", "p", "k", "j", "ghost"], voices)
>>> print(uncast[0])
voice 'j' has a voice_id nobody is recorded as choosing (no chosen_by). Cast it: `an voices design` (options from its notes) then `an voices choose <option> --by <writer>` (the pick, recorded as chosen_by), or `an voices cast <voice_id> --by <writer>` for a voice picked by hand (`an voices list`); a timing draft may set `provisional: true` on the voice document instead.
>>> provisional
["voice 'p' is provisional (round-2 timing draft): choose a voice before the cut"]
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.audio.voice_design.voice_casting_problem(doc)

Why a render must not speak `doc` as it stands, or `None`.

A voice written in words (`notes`) is cast only once a choice is recorded
(`chosen_by` beside the `voice_id`), or it is marked `provisional`. A
document without `notes` names its voice by hand and is not judged here.

```pycon
>>> voice_casting_problem({"voice_id": "v1"}) is None
True
>>> print(voice_casting_problem({"notes": "a warm voice"}))
is written in words but no voice is chosen for it: nothing to speak with
>>> print(voice_casting_problem({"notes": "a warm voice", "voice_id": "v1"}))
has a voice_id nobody is recorded as choosing (no chosen_by)
>>> voice_casting_problem({"notes": "n", "voice_id": "v1", "chosen_by": "noel"}) is None
True
>>> voice_casting_problem({"notes": "n", "voice_id": "v1", "provisional": "draft"}) is None
True
>>> voice_casting_problem({"notes": "n", "provisional": True}) is None  # provisional WHAT?
False
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
