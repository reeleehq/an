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
- [`choose_in_entry()`](#an.audio.voice_design.choose_in_entry): the choice made in one manifest entry (that
  `voice_id`, the designed voice it replaces retired, who chose it and
  when), returning the voice document and the replaced voice: the step every
  chooser shares, the CLI’s [`choose_project_voice()`](#an.audio.voice_design.choose_project_voice) and a connector’s alike.

**Two more routes to a voice** (an#485). Design from notes can miss a
regional accent entirely (every design of “rural Limerick Irish” came out
English). So a voice document may also carry a `library` query (`{"accent":
"irish", "gender": "male", "age": "middle_aged"}`), or `an voices design
--library accent=irish,gender=male` gives one to every voice: the provider’s
shared voice library, human-tagged by region, is searched and its candidates
join the same manifest as `L1`, `L2`, … options ([`ElevenLabsVoiceLibrary`](#an.audio.voice_design.ElevenLabsVoiceLibrary)
behind the `library=` seam; a search and a preview cost nothing). And
`an voices audition` makes an **audition reel** per option: the character’s
own lines from the scene, spoken with the film’s TTS provider and model, the
line’s cues as audio tags, 0.6 s apart ([`audition_voice_options()`](#an.audio.voice_design.audition_voice_options), the
`tts=` seam), so the writer hears what the film will sound like, accent
drift of the render model included. The writer’s ear is the judge: an accent
classifier was measured and cannot screen TTS accents (an#485).

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

| [`announce_auditions`](#an.audio.voice_design.announce_auditions)(jobs, tts)                      | What making `jobs` will bill, in one sentence (`""` for none).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`audition_key`](#an.audio.voice_design.audition_key)(voice_id, lines, \*[, effects, ...])  | The content key of a reel: what it would sound like depends on exactly these, so a reel with this key is never made (billed) twice.                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| [`audition_project_voices`](#an.audio.voice_design.audition_project_voices)(project_dir[, refs, ...])  | An audition reel per option of each voice in `refs` (default: every voice with a manifest): the voice's own lines from the scene, spoken with the film's TTS provider (`tts`, default ElevenLabs — the provider the film renders with, so the reel sounds like the film), the voice document's model, settings and effects, to `artifacts/voice_auditions/<ref>_<option>.wav` (`.../scenes/<stem>/` for a scene other than `scene.md`, so two scenes' reels coexist, an#571); the manifest records each reel (`audition_path`, and per scene under `auditions`) as soon as it is made. |
| [`audition_voice_options`](#an.audio.voice_design.audition_voice_options)(entry, lines, \*, ...)      | An audition reel per option of one voice's manifest `entry`: every line of `lines` — `(text, synthesize options)` pairs, the options being what the film's pipeline would send (`model_id`, `voice_settings`, `audio_tags` from the line's cues) — spoken in that option's voice by `tts` (the film's provider), the voice's `effects` applied, `gap_s` apart, as one WAV in `reels` under `<ref>_<option>`.                                                                                                                                                                           |
| [`plan_auditions`](#an.audio.voice_design.plan_auditions)(entry, lines, \*[, ref, ...])       | The reels to make for one voice's manifest `entry`, every one checked BEFORE anything is billed: the named `options` exist (default: every option with a voice id) and are saved voices, there are `lines` to speak, and an option whose recorded reel was made under this very key is skipped unless `redo`.                                                                                                                                                                                                                                                                          |
| [`run_auditions`](#an.audio.voice_design.run_auditions)(jobs, \*, reels, tts[, gap_s, ...])  | Make every reel of `jobs` with `tts` (`synthesize(text, voice_id, \*\*options)` per line — billed), `gap_s` apart, into `reels` under the job's reel key, and record it on the job's option (`audition`, `audition_lines`, `audition_key`); `on_reel` is called after each reel is recorded, so a failure later loses nothing paid for.                                                                                                                                                                                                                                                |
| [`cast_project_voice`](#an.audio.voice_design.cast_project_voice)(project_dir, ref[, ...])        | Record a voice picked by hand (from `an voices list`, or the document's own `voice_id`) as the writer's choice for `ref`: `voice_id` (default: the one the document already names), `chosen_by`, `chosen_at`; no options manifest needed and nothing billed.                                                                                                                                                                                                                                                                                                                           |
| [`merge_redesign`](#an.audio.voice_design.merge_redesign)(previous, entry, \*[, in_use])      | `entry` (a voice's options, designed again) keeping what the previous design's entry recorded (an#604).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| [`choose_in_entry`](#an.audio.voice_design.choose_in_entry)(entry, option, \*[, by, ...])      | Make `option` the choice of one voice's options manifest `entry` (an#549): the one choose step an's `an voices choose` and a connector (reelee's production pack) share.                                                                                                                                                                                                                                                                                                                                                                                                               |
| [`choose_project_voice`](#an.audio.voice_design.choose_project_voice)(project_dir, ref, option, \*) | Write the chosen option's `voice_id` into `assets/voices/<ref>.json`, with who chose it (`by`, default the login name) and when (`at`, default now), and the choice into its options manifest ([`choose_in_entry()`](#an.audio.voice_design.choose_in_entry)); return the document.                                                                                                                                                                                                                                                                                               |
| [`choose_voice_option`](#an.audio.voice_design.choose_voice_option)(entry, option, \*[, ref, ...]) | The provider `voice_id` of `option` in one voice's manifest `entry`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| [`default_chooser`](#an.audio.voice_design.default_chooser)()                                  | Who a choice is recorded as when nobody is named: the login name.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| [`default_designer`](#an.audio.voice_design.default_designer)(\*[, api_key])                    | The designer used when none is given: [`ElevenLabsVoiceDesigner`](#an.audio.voice_design.ElevenLabsVoiceDesigner).                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| [`default_library`](#an.audio.voice_design.default_library)(\*[, api_key])                     | The library used when none is given: [`ElevenLabsVoiceLibrary`](#an.audio.voice_design.ElevenLabsVoiceLibrary).                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| [`design_project_voices`](#an.audio.voice_design.design_project_voices)(project_dir[, refs, ...])    | Design options for the project's voices (and search the library for the ones with a query); write manifests and samples; return the manifest.                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| [`design_voice_options`](#an.audio.voice_design.design_voice_options)(voices, \*, samples[, ...])   | Design options for each voice with notes, and search the library for each voice with a query; return the options manifest.                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| [`designable_voices`](#an.audio.voice_design.designable_voices)(voices[, refs])                  | The voice documents (of `refs`, else all) that carry `notes`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| [`library_query_of`](#an.audio.voice_design.library_query_of)(doc[, default])                   | The document's own `library` query, else `default`, else `None`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| [`library_voice_options`](#an.audio.voice_design.library_voice_options)(query, \*, samples, ref)     | The library candidates for `query` as manifest options `L<n>`, each with its preview in `samples` (`<ref>_L<n>`) when the library has one (`sample` is `None` otherwise), and the sharing account's id (`owner_id`) so the voice can be added to the account later.                                                                                                                                                                                                                                                                                                                    |
| [`parse_library_query`](#an.audio.voice_design.parse_library_query)(text)                          | A library query from its CLI spelling, `accent=irish,gender=male` (a mapping passes through; empty is `None`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| [`provisional_reason`](#an.audio.voice_design.provisional_reason)(doc)                            | Why `doc` speaks a voice nobody chose (its `provisional`, as text), or `None` when it is not provisional.                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| [`record_choice`](#an.audio.voice_design.record_choice)(doc, voice_id, \*[, by, at, ...])    | The voice document with `voice_id` chosen by `by` at `at` (default: now, UTC): `chosen_by` and `chosen_at` beside the `voice_id`, the `provider` set when given (`None`, the default, keeps the document's: a designed option passes `DESIGN_PROVIDER`; a hand-picked voice of another provider passes nothing), and `provisional` dropped, since a choice is what it stood in for.                                                                                                                                                                                                    |
| [`sample_text_from_lines`](#an.audio.voice_design.sample_text_from_lines)(lines, \*[, limit])         | A sample text from a voice's own dialogue lines, or `None` when they are too short for a provider preview (then the provider writes one).                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| [`sample_text_of`](#an.audio.voice_design.sample_text_of)(doc[, fallback])                    | The document's `sample_text` (clipped), else `fallback`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| [`voice_casting`](#an.audio.voice_design.voice_casting)(voice_refs, voices)                  | `(uncast, provisional)`: one message per distinct voice of `voice_refs` (the voices a scene's lines speak with) that a render must not speak as it stands, and one per voice it speaks provisionally.                                                                                                                                                                                                                                                                                                                                                                                  |
| [`voice_casting_problem`](#an.audio.voice_design.voice_casting_problem)(doc)                         | Why a render must not speak `doc` as it stands, or `None`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |

### Classes

| [`ElevenLabsVoiceDesigner`](#an.audio.voice_design.ElevenLabsVoiceDesigner)(\*[, api_key, ...])      | ElevenLabs Voice Design through the `elevenlabs` SDK (what an's ElevenLabs TTS already uses): the default designer, with voxy's two-method shape.                                                                                                                                                                               |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`ElevenLabsVoiceLibrary`](#an.audio.voice_design.ElevenLabsVoiceLibrary)(\*[, api_key, ...])       | ElevenLabs' shared voice library through the `elevenlabs` SDK (`voices.get_shared`): voices other accounts published, human-tagged by accent, age and gender, with a region often in the description ("Cork", "west of Ireland").                                                                                               |
| [`LibraryVoice`](#an.audio.voice_design.LibraryVoice)(voice_id[, name, description, ...]) | One candidate from a provider's shared voice library.                                                                                                                                                                                                                                                                           |
| [`AuditionJob`](#an.audio.voice_design.AuditionJob)(ref, option, lines, effects, key)    | One reel to make: an option of one voice, the lines it speaks, and the content key the reel is recorded under (so it is never made twice).                                                                                                                                                                                      |
| [`VoiceChoice`](#an.audio.voice_design.VoiceChoice)(document[, previous, retired])       | What [`choose_in_entry()`](#an.audio.voice_design.choose_in_entry) did: the voice document; `previous`, the voice the choice displaced (what a voice file written before still names; `None` when it displaced none); and `retired`, that voice when it went into the `retired` ledger (one the choose step itself saved). |

### Exceptions

| [`VoiceDesignError`](#an.audio.voice_design.VoiceDesignError)   | A voice that cannot be designed or chosen (no notes, an unknown option, ...).   |
|---------------------------------------------------------------------|---------------------------------------------------------------------------------|

### *class* an.audio.voice_design.AuditionJob(ref, option, lines, effects, key)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One reel to make: an option of one voice, the lines it speaks, and the
content key the reel is recorded under (so it is never made twice).

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

### *class* an.audio.voice_design.ElevenLabsVoiceLibrary(, api_key=None, client_factory=None, fetch=None, timeout_s=120)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

ElevenLabs’ shared voice library through the `elevenlabs` SDK
(`voices.get_shared`): voices other accounts published, human-tagged by
accent, age and gender, with a region often in the description (“Cork”,
“west of Ireland”). A search and a preview download cost no credit; speaking
a library voice at render time is billed like any other.

api_key: defaults to `ELEVEN_API_KEY` / `ELEVENLABS_API_KEY`
client_factory: `api_key -> client`; tests inject a fake so nothing is called
fetch: `url -> bytes` for a preview (default: a plain HTTP GET)

#### add(voice_id, owner_id, , name)

Add the shared voice to the account under `name`; returns its id.

A production spoke shared voices by their id directly; ElevenLabs also
documents adding one (`voices.share`) and a `voice_not_found` on a
library id means it needs this. Free; not called by anything else here.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### preview(voice)

The voice’s own preview clip (mp3 bytes), or `None` when it has none.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### search(, limit=8, \*\*filters)

The shared voices matching `filters` (`LIBRARY_FILTERS`), at most `limit`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`LibraryVoice`](#an.audio.voice_design.LibraryVoice)]

### *class* an.audio.voice_design.LibraryVoice(voice_id, name='', description='', accent=None, age=None, gender=None, language=None, preview_url=None, owner_id=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One candidate from a provider’s shared voice library.

#### owner_id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The account that shares it (ElevenLabs `public_owner_id`).

### *class* an.audio.voice_design.VoiceChoice(document, previous=None, retired=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What [`choose_in_entry()`](#an.audio.voice_design.choose_in_entry) did: the voice document; `previous`, the
voice the choice displaced (what a voice file written before still
names; `None` when it displaced none); and `retired`, that voice when
it went into the `retired` ledger (one the choose step itself saved).

### *exception* an.audio.voice_design.VoiceDesignError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A voice that cannot be designed or chosen (no notes, an unknown option, …).

### an.audio.voice_design.announce_auditions(jobs, tts)

What making `jobs` will bill, in one sentence (`""` for none).

```pycon
>>> class T:
...     name = "elevenlabs"
...     def billed_characters(self, text, **kw):
...         return len(text)
>>> jobs = [AuditionJob("j", {"option": "A", "voice_id": "v"}, [("Hi.", {}), ("Bye.", {})], {}, "k")]
>>> announce_auditions(jobs, T())
'audition: 1 reel(s) x 2 line(s) = 2 request(s) to elevenlabs, 7 characters'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.voice_design.audition_key(voice_id, lines, , effects=None, gap_s=0.6, tts_name='')

The content key of a reel: what it would sound like depends on exactly
these, so a reel with this key is never made (billed) twice.

```pycon
>>> k = audition_key("v", [("Hi.", {"model_id": "m"})], tts_name="elevenlabs")
>>> k == audition_key("v", [("Hi.", {"model_id": "m"})], tts_name="elevenlabs"), len(k) > 8
(True, True)
>>> k != audition_key("v", [("Hi!", {"model_id": "m"})], tts_name="elevenlabs")
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.voice_design.audition_project_voices(project_dir, refs=None, \*, options=None, tts=None, gap_s=0.6, announce=<object object>, redo=False, scene_file='scene.md')

An audition reel per option of each voice in `refs` (default: every
voice with a manifest): the voice’s own lines from the scene, spoken with
the film’s TTS provider (`tts`, default ElevenLabs — the provider the
film renders with, so the reel sounds like the film), the voice document’s
model, settings and effects, to `artifacts/voice_auditions/<ref>_<option>.wav`
(`.../scenes/<stem>/` for a scene other than `scene.md`, so two scenes’
reels coexist, an#571); the manifest records each reel (`audition_path`,
and per scene under `auditions`) as soon as it is made.
Every voice’s reels are planned and checked before the first request, the
whole bill is announced once, and a reel already on record under the same
content key is not made again (`redo` makes them all again). Returns
the manifests of `refs`. `scene_file` takes the lines from another
scene of the project (`scene.studio.md`, an#554).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### an.audio.voice_design.audition_voice_options(entry, lines, \*, reels, tts, ref='', options=None, effects=None, gap_s=0.6, announce=<object object>, redo=False)

An audition reel per option of one voice’s manifest `entry`: every line
of `lines` — `(text, synthesize options)` pairs, the options being what
the film’s pipeline would send (`model_id`, `voice_settings`,
`audio_tags` from the line’s cues) — spoken in that option’s voice by
`tts` (the film’s provider), the voice’s `effects` applied, `gap_s`
apart, as one WAV in `reels` under `<ref>_<option>`. Returns a copy of
the entry with each made reel recorded on its option; the input is not
changed. [`plan_auditions()`](#an.audio.voice_design.plan_auditions) checks everything before the first
request; a reel already on record under the same content key is not made
again unless `redo` (so a second call bills nothing).

```pycon
>>> from types import SimpleNamespace as N
>>> import math, struct
>>> def tone(n):
...     import io, wave
...     b = io.BytesIO(); w = wave.open(b, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
...     w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20))) for i in range(n))); w.close()
...     return b.getvalue()
>>> class FakeTTS:
...     name = "fake"
...     def synthesize(self, text, voice_id, **kw):
...         return N(bytes_=tone(4410), transcript=text)
>>> entry = {"options": [{"option": "A", "voice_id": "v1"}, {"option": "L1", "voice_id": "v2"}]}
>>> reels = {}
>>> out = audition_voice_options(entry, [("Hi.", {}), ("Bye.", {"audio_tags": ["sad"]})], reels=reels, tts=FakeTTS(), ref="j", announce=None)
>>> sorted(reels), [o["audition"] for o in out["options"]]
(['j_A', 'j_L1'], ['j_A', 'j_L1'])
>>> again = audition_voice_options(out, [("Hi.", {}), ("Bye.", {"audio_tags": ["sad"]})], reels=reels, tts=FakeTTS(), ref="j", announce=None)
>>> again == out  # on record under the same key: nothing made, nothing billed
True
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.audio.voice_design.cast_project_voice(project_dir, ref, voice_id=None, , by=None, at=None, provider=None)

Record a voice picked by hand (from `an voices list`, or the document’s
own `voice_id`) as the writer’s choice for `ref`: `voice_id` (default:
the one the document already names), `chosen_by`, `chosen_at`; no
options manifest needed and nothing billed. `provider` sets the
document’s when given. Returns the document.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.audio.voice_design.choose_in_entry(entry, option, , by=None, designer=None, ref='', at=None, doc=None, in_use=(), name_prefix=None)

Make `option` the choice of one voice’s options manifest `entry`
(an#549): the one choose step an’s `an voices choose` and a connector
(reelee’s production pack) share. Returns the voice document
([`record_choice()`](#an.audio.voice_design.record_choice) of `doc`, default an empty one: a caller that
keeps the voice file elsewhere merges these keys into it) and the voice
it replaced.

`entry` is updated in place: `chosen` records the option, its
`voice_id`, `chosen_by` and `chosen_at`. Choosing the option already
chosen reuses its voice (nothing is saved), and keeps its `chosen_at`
when the same chooser chooses it again and no `at` is given. Choosing
another one names its voice (saved as a provider voice when it was not,
[`choose_voice_option()`](#an.audio.voice_design.choose_voice_option), named under `name_prefix`, default the
entry’s, and marked `saved_by_choice` and `saved_under` that prefix on
its option) and retires the voice it replaces when a choice saved it: its
option no longer names it, and `entry["retired"]` records it
(`{voice_id, option, name_prefix}`, the prefix it was saved under, an#618),
never deleted here (a copy of the manifest, or a
voice file already written, may still name it: freeing the provider’s
slot is a separate, explicit act). A voice saved when the options were
designed (`persist=True`), a library voice and one cast by hand stay
named where they are; a choice carried over a re-design (`retire_on_replace`,
an#604) is retired when replaced. A voice in `in_use` (one another voice
document speaks) is never retired: pass the project’s other voices. `by`
defaults to the login name (see [`record_choice()`](#an.audio.voice_design.record_choice)). A host choosing for
a project of its own (a fork) passes its `name_prefix` rather than
re-stamping the entry’s, which names the voices the entry already saved.

```pycon
>>> from types import SimpleNamespace
>>> class Saver:   # a designer that saves a preview as voice "v<preview>"
...     def design_voice(self, notes, *, preview, name): return SimpleNamespace(voice_id="v" + preview)
>>> entry = {"notes": "n", "options": [{"option": "A", "generated_voice_id": "a"},
...                                    {"option": "B", "generated_voice_id": "b"}]}
>>> choose_in_entry(entry, "a", by="noel", at="t1", designer=Saver()).document["voice_id"]
'va'
>>> choice = choose_in_entry(entry, "B", by="noel", at="t2", designer=Saver())
>>> choice.previous, choice.retired, [o["voice_id"] for o in entry["options"]]
('va', 'va', [None, 'vb'])
>>> choose_in_entry(entry, "B", by="noel").document["chosen_at"]   # the same choice again
't2'
```

A voice keeps the prefix it was saved under when a fork chooses with its own:

```pycon
>>> src = {"notes": "n", "name_prefix": "src", "options": [
...     {"option": "A", "generated_voice_id": "a"}, {"option": "B", "generated_voice_id": "b"}]}
>>> _ = choose_in_entry(src, "A", by="noel", designer=Saver())
>>> choose_in_entry(src, "B", by="ann", designer=Saver(), name_prefix="fork").retired
'va'
>>> src["retired"], src["options"][1]["saved_under"], src["name_prefix"]
([{'voice_id': 'va', 'option': 'A', 'name_prefix': 'src'}], 'fork', 'src')
```

* **Return type:**
  [`VoiceChoice`](#an.audio.voice_design.VoiceChoice)

### an.audio.voice_design.choose_project_voice(project_dir, ref, option, , designer=None, by=None, at=None)

Write the chosen option’s `voice_id` into `assets/voices/<ref>.json`,
with who chose it (`by`, default the login name) and when (`at`, default
now), and the choice into its options manifest ([`choose_in_entry()`](#an.audio.voice_design.choose_in_entry));
return the document.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.audio.voice_design.choose_voice_option(entry, option, , ref='', designer=None, name_prefix=None)

The provider `voice_id` of `option` in one voice’s manifest `entry`.

An option that was not persisted is saved as a voice now (its preview must
not have expired), named under `name_prefix` (default: the entry’s).

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

### an.audio.voice_design.default_library(, api_key=None)

The library used when none is given: [`ElevenLabsVoiceLibrary`](#an.audio.voice_design.ElevenLabsVoiceLibrary).

* **Return type:**
  [`ElevenLabsVoiceLibrary`](#an.audio.voice_design.ElevenLabsVoiceLibrary)

### an.audio.voice_design.design_project_voices(project_dir, refs=None, , designer=None, model_id='eleven_ttv_v3', persist=True, name_prefix=None, library=None, library_query=None, library_limit=8, design=True, scene_file='scene.md')

Design options for the project’s voices (and search the library for the
ones with a query); write manifests and samples; return the manifest.

A voice document without `sample_text` speaks its own lines from the scene
(`scene_file`: another scene of the project, an#554).
`library_query` (`accent=irish,gender=male`) applies to every voice
without a `library` of its own; `design=False` searches the library only.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### an.audio.voice_design.design_voice_options(voices, , samples, refs=None, designer=None, model_id='eleven_ttv_v3', persist=True, name_prefix='an', lines_of=None, library=None, library_query=None, library_limit=8, design=True, previous=None, in_use=())

Design options for each voice with notes, and search the library for
each voice with a query; return the options manifest.

voices: `{ref: voice document}` (a project’s `voices` store)
samples: where each option’s audio goes, keyed `<ref>_<option>` (mp3 bytes)
refs: the voices to design (default: every one with `notes` or `library`)
designer: a two-method designer (default: [`default_designer()`](#an.audio.voice_design.default_designer))
model_id: the provider’s voice-design model
persist: save every option as a durable voice now (else only the chosen one, later)
name_prefix: prefix of the saved voices’ names in the provider account
lines_of: `ref -> that voice's dialogue lines`, for a sample text when the

> document has none (else the provider writes one)

library: the shared-library seam ([`default_library()`](#an.audio.voice_design.default_library) for the CLI),
: searched for every voice that has a `library` query of its own or
  gets `library_query`. **Opt-in**: with neither `library` nor
  `library_query` given, a document’s `library` key is left alone
  and nothing reaches the network — a caller that passed only a
  `designer` sees exactly what it saw before.

library_query: the query for voices without their own (`accent=irish,gender=male`)
library_limit: at most this many library candidates per voice
design: with `False`, no designed previews (library candidates only, nothing billed)
previous: `{ref: the entry its last design wrote}` (a damaged one as anything

> that is not a mapping): each designed again keeps its record
> ([`merge_redesign()`](#an.audio.voice_design.merge_redesign)), and a damaged one is refused BEFORE anything is
> billed or saved (an#604)

in_use: voice ids a voice document names, which a re-design never retires;
: a caller passing `previous` should pass them (the default, none, would
  ledger a voice another character speaks)

A voice with `notes` gets designed options `A`, `B`, …; a voice with
a query gets library options `L1`, `L2`, …; one with both gets both in
one manifest, so the writer compares them on the same page.

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

### an.audio.voice_design.library_query_of(doc, default=None)

The document’s own `library` query, else `default`, else `None`.

```pycon
>>> library_query_of({"library": {"accent": "irish"}}, {"accent": "scottish"})
{'accent': 'irish'}
>>> library_query_of({}, {"accent": "scottish"}), library_query_of({}) is None
({'accent': 'scottish'}, True)
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.voice_design.library_voice_options(query, , samples, ref, library=None, limit=8)

The library candidates for `query` as manifest options `L<n>`, each
with its preview in `samples` (`<ref>_L<n>`) when the library has one
(`sample` is `None` otherwise), and the sharing account’s id
(`owner_id`) so the voice can be added to the account later.

```pycon
>>> class Fake:
...     def search(self, *, limit, **f):
...         return [LibraryVoice("v1", "Dan", "Cork", accent="irish", preview_url="u", owner_id="o")]
...     def preview(self, v):
...         return b"ID3"
>>> samples = {}
>>> library_voice_options({"accent": "irish"}, samples=samples, ref="j", library=Fake())
[{'option': 'L1', 'kind': 'library', 'voice_id': 'v1', 'owner_id': 'o', 'name': 'Dan', 'about': 'Cork', 'accent': 'irish', 'age': None, 'gender': None, 'sample': 'j_L1', 'duration_s': None}]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### an.audio.voice_design.merge_redesign(previous, entry, , in_use=())

`entry` (a voice’s options, designed again) keeping what the previous
design’s entry recorded (an#604). Its `chosen` is kept (the voice the
voice document names, by whom and when), its `option` cleared, since
this design’s option of that label is another voice, and marked
`RETIRE_ON_REPLACE_KEY` when that voice was a designed one, so the
choice that replaces it retires it. Its `retired` ledger is kept and
joined by every voice the previous design saved that nothing names any
more: not this design, not `chosen`, not `in_use` (a voice document
names it), not a library option (another account’s). `entry` is
returned, updated.

```pycon
>>> old = {"name_prefix": "p", "options": [{"option": "A", "voice_id": "v1"},
...        {"option": "B", "voice_id": "v2"}, {"option": "L1", "kind": "library", "voice_id": "pub"}],
...        "chosen": {"option": "A", "voice_id": "v1", "chosen_by": "n", "chosen_at": "t"}}
>>> new = merge_redesign(old, {"options": [{"option": "A", "voice_id": "v9"}]})
>>> new["chosen"]["option"], new["chosen"][RETIRE_ON_REPLACE_KEY], new["retired"]
(None, True, [{'voice_id': 'v2', 'option': 'B', 'name_prefix': 'p'}])
```

* **Return type:**
  [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

### an.audio.voice_design.parse_library_query(text)

A library query from its CLI spelling, `accent=irish,gender=male`
(a mapping passes through; empty is `None`).

```pycon
>>> parse_library_query("accent=irish, gender=male")
{'accent': 'irish', 'gender': 'male'}
>>> parse_library_query("") is None, parse_library_query({"age": "young"})
(True, {'age': 'young'})
>>> parse_library_query("irish")
Traceback (most recent call last):
...
an.audio.voice_design.VoiceDesignError: library query 'irish': write it as key=value pairs (accent, gender, age, language, search)
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.voice_design.plan_auditions(entry, lines, , ref='', options=None, effects=None, gap_s=0.6, tts_name='', redo=False, recorded=None)

The reels to make for one voice’s manifest `entry`, every one checked
BEFORE anything is billed: the named `options` exist (default: every
option with a voice id) and are saved voices, there are `lines` to speak,
and an option whose recorded reel was made under this very key is skipped
unless `redo`. `recorded(option)` says which record to judge that by
(default: the option’s own fields; the project forms pass the scene’s own
record, an#571). Raises [`VoiceDesignError`](#an.audio.voice_design.VoiceDesignError) for any problem.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`AuditionJob`](#an.audio.voice_design.AuditionJob)]

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

### an.audio.voice_design.run_auditions(jobs, \*, reels, tts, gap_s=0.6, announce=<object object>, on_reel=None)

Make every reel of `jobs` with `tts` (`synthesize(text, voice_id,
\*\*options)` per line — billed), `gap_s` apart, into `reels` under the
job’s reel key, and record it on the job’s option (`audition`,
`audition_lines`, `audition_key`); `on_reel` is called after each
reel is recorded, so a failure later loses nothing paid for. `announce`
(default: a line on stderr; `None` for silence) is told the whole bill
first, and the provider is asked `check_available()` before the first
request.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

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
voice 'j' has a voice_id nobody is recorded as choosing (no chosen_by). Cast it: `an voices design` (options from its notes or a library query), `an voices audition` (the lines in each option's voice), then `an voices choose <option> --by <writer>` (the pick, recorded as chosen_by), or `an voices cast <voice_id> --by <writer>` for a voice picked by hand (`an voices list`); a timing draft may set `provisional: true` on the voice document instead.
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
