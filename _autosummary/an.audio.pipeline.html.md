# an.audio.pipeline

Audio pipeline orchestration: dialogue → audio → visemes → IR mutation.

Phase 3 wires the pieces together. `produce_audio_for_scene` walks every
`Dialogue` in the scene, synthesizes its audio + viseme track via the
configured providers, persists artifacts to `mall["audio"]` /
`mall["visemes"]`, and stamps the resulting `VisemeTrack` and timing
back onto the `Dialogue` line so renderers can find it.

**Who speaks a line** (an#305): with no `tts` given, each line’s voice
document decides — its `provider` ([`an.audio.voices.declared_provider()`](an.audio.voices.html.md#an.audio.voices.declared_provider))
— and a voice that names none is spoken by the offline provider (silent WAV;
lip-sync defaults to deterministic offline visemes), so a project that declares
no provider runs without API keys or external binaries, exactly as before. A
`tts` given is an override for every line; a line spoken by another provider
than its voice declares is a [`VoiceStandInWarning`](#an.audio.pipeline.VoiceStandInWarning) (an error under
`strict`). See [`tts_chooser()`](#an.audio.pipeline.tts_chooser).

```pycon
>>> from an.audio.pipeline import default_tts, default_lipsync
>>> default_tts().name
'offline'
```

### Module Attributes

| [`VOICE_TTS`](#an.audio.pipeline.VOICE_TTS)                   | The `tts` that means "each line's voice document names its provider" — the default of a render (an#305).    |
|------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| [`DEFAULT_TTS_NAME`](#an.audio.pipeline.DEFAULT_TTS_NAME)            | Who speaks a line whose voice declares no provider, when no `tts` overrides it.                             |
| [`TakeScorerFactory`](#an.audio.pipeline.TakeScorerFactory)           | `(TakesSpec) -> TakeScorer` — the seam that turns a takes spec into its scorer.                             |
| [`OVERRUN_TOLERANCE_S`](#an.audio.pipeline.OVERRUN_TOLERANCE_S)         | a frame at 60 fps (the same as `an validate`'s).                                                            |
| [`AUDIO_OUTPUT_STORES`](#an.audio.pipeline.AUDIO_OUTPUT_STORES)         | The stores the audio pipeline writes what it makes to.                                                      |
| [`REROLL_ONLY_HINT`](#an.audio.pipeline.REROLL_ONLY_HINT)            | only a new roll (new keys) replaces it.                                                                     |
| [`LEGACY_DURATION_TOLERANCE_S`](#an.audio.pipeline.LEGACY_DURATION_TOLERANCE_S) | How far a legacy sidecar's duration may sit from its audio's and still be the same take: a frame at 60 fps. |

### Functions

| [`audio_key`](#an.audio.pipeline.audio_key)(text, voice_id, tts_name[, ...])        | Content key of a line's audio: text, voice, provider, and — only when the voice declares them — its effects, the provider voice it names (an#194), the provider's synthesis options (model, settings, seed, audio tags — an#209).                                                      |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`default_lipsync`](#an.audio.pipeline.default_lipsync)()                                 | The default lip-sync provider: the loaded genre's `offline` one (the deterministic char-to-viseme provider of `cutan`), else [`NullLipSync`](an.audio.lipsync.html.md#an.audio.lipsync.NullLipSync).                                                                |
| [`default_tts`](#an.audio.pipeline.default_tts)()                                     | The default TTS provider: `OfflineTTS`.                                                                                                                                                                                                                                                |
| [`dialogue_overruns`](#an.audio.pipeline.dialogue_overruns)(scene, \*[, tolerance_s, mall]) | One message per synthesized line that ends past its shot's end.                                                                                                                                                                                                                        |
| [`free_and_repeatable`](#an.audio.pipeline.free_and_repeatable)(provider)                     | Whether `provider` may be run where nothing may be spent or written (an#311): it DECLARES `repeatable = True` (the same request gives the same bytes: `offline`, `mac_say`) and `billed = False` — stated, never inferred from a missing method — and has no `billed_characters` hook. |
| [`in_memory_audio_mall`](#an.audio.pipeline.in_memory_audio_mall)(mall)                        | `mall` with its audio and visemes stores behind [`InMemoryOverlay`](#an.audio.pipeline.InMemoryOverlay) s — hand it to [`stamp_from_stores()`](#an.audio.pipeline.stamp_from_stores) (`free_in_memory=True`) and then to whatever keys the stamped scene (an#311).     |
| [`is_voice_tts`](#an.audio.pipeline.is_voice_tts)(tts)                                 | Whether `tts` means "each voice's own provider": `None`, `""` or [`VOICE_TTS`](#an.audio.pipeline.VOICE_TTS).                                                                                                                                                           |
| [`produce_audio_for_dialogue`](#an.audio.pipeline.produce_audio_for_dialogue)(dialogue[, mall, ...]) | Synthesize audio + visemes for one dialogue line.                                                                                                                                                                                                                                      |
| [`produce_audio_for_scene`](#an.audio.pipeline.produce_audio_for_scene)(scene[, mall, tts, ...])  | Walk every dialogue line, synthesize, and stamp viseme tracks back.                                                                                                                                                                                                                    |
| [`retake_lines`](#an.audio.pipeline.retake_lines)(scene, mall, match, \*, tts[, ...])  | Mark the recorded takes of the lines whose text contains `match` to be chosen again on the next render; one message per matching line.                                                                                                                                                 |
| [`retime_dialogue`](#an.audio.pipeline.retime_dialogue)(scene, \*[, timed_shots_only])    | Stamp every synthesized line's `start` from its `pause` / `at`.                                                                                                                                                                                                                        |
| [`stamp_from_stores`](#an.audio.pipeline.stamp_from_stores)(scene, mall, \*[, tts, ...])    | Stamp `scene`'s dialogue exactly as [`produce_audio_for_scene()`](#an.audio.pipeline.produce_audio_for_scene) would with these providers — `tts` as it takes it: `None` for each voice's own (an#305) — from the content-keyed `audio` and `visemes` stores only.                     |
| [`synthesis_options`](#an.audio.pipeline.synthesis_options)(tts, line, mall, voice_id)      | The provider-specific `synthesize` kwargs for `line` in `voice_id`.                                                                                                                                                                                                                    |
| [`takes_cost_message`](#an.audio.pipeline.takes_cost_message)(lines, tts, audio_store)       | What synthesizing `lines` with `tts` will bill, when any of them takes best-of-N or `tts` bills per character (an#305: a voice that names a paid provider is spoken by it with no flag, so its cost is said first); else `""`.                                                         |
| [`tts_chooser`](#an.audio.pipeline.tts_chooser)(tts, mall, \*[, make])                | `voice_id -> provider`: who speaks a line in that voice (an#305).                                                                                                                                                                                                                      |
| [`viseme_key`](#an.audio.pipeline.viseme_key)(audio_key_, lipsync_name, transcript)  | Content key of a line's viseme track (a function of the audio HEARD).                                                                                                                                                                                                                  |
| [`voice_stand_ins`](#an.audio.pipeline.voice_stand_ins)(lines, mall, \*, overridden)      | One message per voice whose lines are spoken by another provider than its document declares; `lines` is `(voice_id, provider)` per line, and `overridden` says whether a `tts` was given for every line.                                                                               |

### Classes

| [`InMemoryOverlay`](#an.audio.pipeline.InMemoryOverlay)(store)   | A store view that reads through and keeps every write IN MEMORY: what a reader of a render's cache keys stamps free audio into (an#311), so the keys it computes next see that audio while the store itself is untouched.   |
|---------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### Exceptions

| [`AudioNotCachedError`](#an.audio.pipeline.AudioNotCachedError)    | A line's audio (or its visemes) is not in the content-keyed stores, so stamping it would need a synthesis this caller does not allow.           |
|-------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| [`AudioPipelineError`](#an.audio.pipeline.AudioPipelineError)     | The scene declares audio the pipeline cannot produce.                                                                                           |
| [`DialogueOverrunWarning`](#an.audio.pipeline.DialogueOverrunWarning) | A synthesized line runs past its shot's end, so its tail is cut.                                                                                |
| [`TakeDigestWarning`](#an.audio.pipeline.TakeDigestWarning)      | The audio restored for a line's recorded take is not the audio the record names.                                                                |
| [`VoiceStandInError`](#an.audio.pipeline.VoiceStandInError)      | Under `strict`: a line would be spoken by another provider than its voice declares.                                                             |
| [`VoiceStandInWarning`](#an.audio.pipeline.VoiceStandInWarning)    | A line is spoken by another provider than its voice document declares — an override for every line, or a provider `an` has no TTS for (an#305). |

### an.audio.pipeline.AUDIO_OUTPUT_STORES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('audio', 'visemes')*

The stores the audio pipeline writes what it makes to.

### *exception* an.audio.pipeline.AudioNotCachedError

Bases: [`AudioPipelineError`](#an.audio.pipeline.AudioPipelineError)

A line’s audio (or its visemes) is not in the content-keyed stores, so
stamping it would need a synthesis this caller does not allow.

### *exception* an.audio.pipeline.AudioPipelineError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The scene declares audio the pipeline cannot produce. Carries detail.

### an.audio.pipeline.DEFAULT_TTS_NAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'offline'*

Who speaks a line whose voice declares no provider, when no `tts` overrides it.

### *exception* an.audio.pipeline.DialogueOverrunWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A synthesized line runs past its shot’s end, so its tail is cut.

### *class* an.audio.pipeline.InMemoryOverlay(store)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

A store view that reads through and keeps every write IN MEMORY: what a
reader of a render’s cache keys stamps free audio into (an#311), so the
keys it computes next see that audio while the store itself is untouched.
Deleting is refused.

### an.audio.pipeline.LEGACY_DURATION_TOLERANCE_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.016666666666666666*

How far a legacy sidecar’s duration may sit from its audio’s and still be
the same take: a frame at 60 fps.

### an.audio.pipeline.OVERRUN_TOLERANCE_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.016666666666666666*

a frame at 60 fps
(the same as `an validate`’s).

* **Type:**
  Slack before a line counts as running past its shot

### an.audio.pipeline.REROLL_ONLY_HINT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'Re-roll it with \`an voices reroll <project> <words of the line>\` (new takes under new keys, billed; the render prints the cost first)'*

only a new roll (new keys) replaces it.

* **Type:**
  The remedy when a recorded take is gone

### *exception* an.audio.pipeline.TakeDigestWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

The audio restored for a line’s recorded take is not the audio the record names.

### an.audio.pipeline.TakeScorerFactory

`(TakesSpec) -> TakeScorer` — the seam that turns a takes spec into its scorer.

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`TakesSpec`](an.audio.takes.html.md#an.audio.takes.TakesSpec)], [`TakeScorer`](an.audio.takes.html.md#an.audio.takes.TakeScorer)]

### an.audio.pipeline.VOICE_TTS *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'voice'*

The `tts` that means “each line’s voice document names its provider” — the
default of a render (an#305). `None` and `""` mean the same.

### *exception* an.audio.pipeline.VoiceStandInError

Bases: [`AudioPipelineError`](#an.audio.pipeline.AudioPipelineError)

Under `strict`: a line would be spoken by another provider than its
voice declares. Raised before any request.

### *exception* an.audio.pipeline.VoiceStandInWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A line is spoken by another provider than its voice document declares —
an override for every line, or a provider `an` has no TTS for (an#305).

### an.audio.pipeline.audio_key(text, voice_id, tts_name, effects=None, , provider_voice=None, options=None, takes=None, take=None, roll=None)

Content key of a line’s audio: text, voice, provider, and — only when the
voice declares them — its effects, the provider voice it names (an#194),
the provider’s synthesis options (model, settings, seed, audio tags —
an#209). With none of them, the payload is exactly the pre-effects one, so
every key a project already has is unchanged. `take` (1, 2, … — never 0)
and `roll` (1, 2, … after `an voices reroll`) key one candidate take of
a best-of-N line; take 0 of roll 0 is the single-take request and keeps its
key. `takes` ([`an.audio.takes.takes_choice_part()`](an.audio.takes.html.md#an.audio.takes.takes_choice_part)) keys the CHOICE
among a line’s takes — the record in `mall["takes"]`, not an audio blob.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> audio_key("hi", "default", "offline") == audio_key(
...     "hi", "default", "offline", {}, provider_voice=None, options={},
...     takes=None, take=0, roll=0)
True
```

### an.audio.pipeline.default_lipsync()

The default lip-sync provider: the loaded genre’s `offline` one (the
deterministic char-to-viseme provider of `cutan`), else
[`NullLipSync`](an.audio.lipsync.html.md#an.audio.lipsync.NullLipSync).

* **Return type:**
  [`LipSyncProvider`](an.audio.lipsync.html.md#an.audio.lipsync.LipSyncProvider)

```pycon
>>> default_lipsync().name in {"offline", "none"}
True
```

### an.audio.pipeline.default_tts()

The default TTS provider: `OfflineTTS`.

* **Return type:**
  [`TTSProvider`](an.audio.tts.html.md#an.audio.tts.TTSProvider)

### an.audio.pipeline.dialogue_overruns(scene, , tolerance_s=0.016666666666666666, mall=None)

One message per synthesized line that ends past its shot’s end.

`an validate` warns before synthesis from an estimate; this is the exact
check AFTER it — a voice’s `tempo` (or a real voice’s own pace, or the
silence it pads a line with) can make a line longer than estimated, and the
render cuts the shot’s audio at the shot’s end, so the tail would otherwise
be lost silently. It is `an validate`’s own check
([`an.ir.validate.shot_dialogue_overruns()`](an.ir.validate.html.md#an.ir.validate.shot_dialogue_overruns)), over the synthesized lines;
`mall` lets its fix name the voice’s `trim_silence`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from an.ir.schema import Dialogue, SceneIR, Shot
>>> shot = Shot(id="s", duration=1.0, dialogue=[
...     Dialogue(speaker="a", text="hi", start=0.2, duration=1.3, audio_ref="k")])
>>> dialogue_overruns(SceneIR(timeline=[shot]))[0][:46]
"shot 's': line 0 (a) ends at 1.30s as synthesi"
```

### an.audio.pipeline.free_and_repeatable(provider)

Whether `provider` may be run where nothing may be spent or written
(an#311): it DECLARES `repeatable = True` (the same request gives the
same bytes: `offline`, `mac_say`) and `billed = False` — stated, never
inferred from a missing method — and has no `billed_characters` hook.
Re-running it reproduces exactly what a render stored; anything else would
give new bytes, so new keys, or cost money.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> from an.audio.offline_tts import OfflineTTS
>>> free_and_repeatable(OfflineTTS()), free_and_repeatable(object())
(True, False)
```

### an.audio.pipeline.in_memory_audio_mall(mall)

`mall` with its audio and visemes stores behind [`InMemoryOverlay`](#an.audio.pipeline.InMemoryOverlay)
s — hand it to [`stamp_from_stores()`](#an.audio.pipeline.stamp_from_stores) (`free_in_memory=True`) and then
to whatever keys the stamped scene (an#311).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.audio.pipeline.is_voice_tts(tts)

Whether `tts` means “each voice’s own provider”: `None`, `""` or
[`VOICE_TTS`](#an.audio.pipeline.VOICE_TTS).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> [is_voice_tts(t) for t in (None, "", "voice", " Voice ", "offline")]
[True, True, True, True, False]
```

### an.audio.pipeline.produce_audio_for_dialogue(dialogue, mall=None, \*, tts=None, lipsync=None, effects=None, voice_id=None, takes=<object object>, take_scorer=<function make_take_scorer>)

Synthesize audio + visemes for one dialogue line.

Side effects: when `mall` is provided, persists the WAV to
`mall["audio"]` keyed by the content-hash of the dialogue, and persists
the viseme JSON to `mall["visemes"]` similarly. Cache-friendly: a
second call with identical inputs returns the cached versions.

`effects` (default: what the line’s voice declares in `mall["voices"]`)
is applied to the synthesized audio BEFORE alignment, so the visemes are
computed on the audio the viewer hears. The raw synthesis stays cached under
its own key, so changing an effect never re-pays the TTS.

`tts` (default: the provider the voice document declares, else offline —
[`tts_chooser()`](#an.audio.pipeline.tts_chooser)) is an override when given.

`voice_id` (default: the line’s `voice_ref`, else `"default"`) is the
`voices`-store key; [`produce_audio_for_scene()`](#an.audio.pipeline.produce_audio_for_scene) passes the one
[`an.audio.voices.line_voice_id()`](an.audio.voices.html.md#an.audio.voices.line_voice_id) resolves, so a character’s bound
voice reaches here (an#194). The provider is handed the voice document’s
own voice id when it names one.

What the provider’s optional `synthesis_options` hook derives from the
voice document and the line (ElevenLabs: `model_id`, `voice_settings`,
`seed`, and the `[emotion]`/`direction` audio tags — an#209) is passed
to `synthesize` and keyed; the text handed to alignment is always the
bare `dialogue.text`, never the tagged one.

`takes` (default: what the voice declares for this line — see
[`an.audio.takes`](an.audio.takes.html.md#module-an.audio.takes); `None` forces one take) synthesizes several takes,
scores each with `take_scorer(spec)` on the audio the viewer hears, keeps
the best and records the choice in `mall["takes"]`. A recorded choice is
restored from the record and never re-rolled; a recorded take whose audio is
gone raises [`TakeLostError`](an.audio.takes.html.md#an.audio.takes.TakeLostError) before any request.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`AudioClip`](an.audio.tts.html.md#an.audio.tts.AudioClip), [`VisemeTrack`](an.audio.lipsync.html.md#an.audio.lipsync.VisemeTrack)]

### an.audio.pipeline.produce_audio_for_scene(scene, mall=None, \*, tts=None, lipsync=None, take_scorer=<function make_take_scorer>, announce=<function \_announce_to_stderr>, overruns=True, strict=False, tts_factory=None)

Walk every dialogue line, synthesize, and stamp viseme tracks back.

Mutates the `scene` in place AND returns it (for chaining).
Stamps `Dialogue.duration`, `Dialogue.viseme_track`, and
`Dialogue.audio_ref` (mall[“audio”] key) so the renderer can find the
audio later. Lines with an existing viseme_track AND audio_ref are not
re-synthesized (idempotent).

`Dialogue.start` is DERIVED on every pass, synthesized or not, by
`Dialogue.planned_start()`: the line’s `at` if set, else the previous
line’s end plus its `pause` (an#187). So editing a pause re-times the
shot without touching the audio, and every consumer of `start` — the
mux, the visemes, captions, ducking — follows. A `start` on a line that
was never synthesized is an authored start from before `at` existed,
and is kept as the line’s `at`.

Every line’s request is resolved BEFORE anything is synthesized, so a
malformed voice (an effect, a `takes`), a corrupt takes record or a
recorded take whose audio is gone fails before a credit is spent; and
`announce` (default: a line on stderr; `None` for silence) is told, before the first request, what best-of-N takes will bill (requests
and the provider’s characters) and which recorded takes were chosen by an
older scorer version than the current one (they are kept). After synthesis,
a line that ends past its shot’s end ([`dialogue_overruns()`](#an.audio.pipeline.dialogue_overruns)) is
announced too — or, with `announce=None`, a `DialogueOverrunWarning` —
unless `overruns=False`: `an render` passes that, because it reports
every post-synthesis finding together in its summary (an#254).

**Who speaks each line** (an#305, [`tts_chooser()`](#an.audio.pipeline.tts_chooser)): with `tts` not
given (`None`, `""` or [`VOICE_TTS`](#an.audio.pipeline.VOICE_TTS)), the line’s voice document’s
`provider`, built by `tts_factory` (default
[`an.audio.providers.make_tts()`](an.audio.providers.html.md#an.audio.providers.make_tts)), else offline; a `tts` given speaks
every line. A line spoken by another provider than its voice declares is a
[`VoiceStandInWarning`](#an.audio.pipeline.VoiceStandInWarning) — the silent offline voice says so — and,
with `strict`, a [`VoiceStandInError`](#an.audio.pipeline.VoiceStandInError) before any request. A provider
with requests to send is asked `check_available()` first (ElevenLabs: is
there a key?), and what a provider that bills per character will bill is
announced before the first request — whatever chose the provider; a cached
line is never billed and never counted.

* **Return type:**
  [`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR)

### an.audio.pipeline.retake_lines(scene, mall, match, \*, tts, rescore=False, take_scorer=<function make_take_scorer>)

Mark the recorded takes of the lines whose text contains `match` to be
chosen again on the next render; one message per matching line.

`rescore=True` re-chooses among the takes already synthesized (with the
current scorer; nothing billed while they are cached); otherwise a new roll
of takes is synthesized (billed — the render prints the cost first). Either
way the replaced choice is kept in the record’s `history`, and the new
take has its own key, so its visemes and word timings are aligned afresh.
This is the only way a recorded take is replaced (ADR 0003).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.audio.pipeline.retime_dialogue(scene, , timed_shots_only=False)

Stamp every synthesized line’s `start` from its `pause` / `at`.

Pure — synthesizes nothing, reads no store — and idempotent. The audio
pipeline ends with it, and every path that skips the pipeline (`render`
with `auto_audio=False`, `an preview`) runs it too, so a pause edited
after synthesis is never played at the stale stamp (an#187). A shot is
re-timed up to its first line with no `duration` (never synthesized:
nothing after it has a known start). Mutates in place and returns
`scene`.

`timed_shots_only=True` — what the paths that skip synthesis pass —
leaves a shot whose lines carry no `pause`/`at` exactly as stamped:
a hand-built scene may stamp `start` itself (a test, a fixture), and
without the pipeline there is no authority to say that stamp is stale.

* **Return type:**
  [`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR)

```pycon
>>> from an.ir.schema import Dialogue, SceneIR, Shot
>>> shot = Shot(id="s", dialogue=[
...     Dialogue(speaker="a", text="hi", start=0.0, duration=0.5, audio_ref="k1"),
...     Dialogue(speaker="b", text="bye", start=0.5, duration=0.4, audio_ref="k2",
...              pause=1.5)])
>>> [d.start for d in retime_dialogue(SceneIR(timeline=[shot])).timeline[0].dialogue]
[0.0, 2.0]
```

### an.audio.pipeline.stamp_from_stores(scene, mall, , tts=None, lipsync, tts_factory=None, free_in_memory=False)

Stamp `scene`’s dialogue exactly as [`produce_audio_for_scene()`](#an.audio.pipeline.produce_audio_for_scene)
would with these providers — `tts` as it takes it: `None` for each
voice’s own (an#305) — from the content-keyed `audio` and `visemes`
stores only. Synthesises, aligns, writes and announces nothing; a line the
stores cannot answer raises [`AudioNotCachedError`](#an.audio.pipeline.AudioNotCachedError).

`free_in_memory` (an#311): a line the stores cannot answer whose
provider is free and repeatable ([`free_and_repeatable()`](#an.audio.pipeline.free_and_repeatable): offline
speech) is synthesised and aligned for real — it reproduces the bytes a
render stored — into the mall’s [`InMemoryOverlay`](#an.audio.pipeline.InMemoryOverlay) s, which
[`in_memory_audio_mall()`](#an.audio.pipeline.in_memory_audio_mall) puts in front of the audio and visemes stores
(required: nothing is ever written to a store). Billed or non-repeatable
providers still raise. Still nothing is announced.

What a reader of the render’s cache keys needs (an#274): a `scene.md`
edit drops every stamp on re-sync, and the next render re-stamps the same
audio from the stores, so the keys a render WILL use are these, not the
unstamped IR’s. Mutates `scene` in place and returns it.

* **Return type:**
  [`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR)

### an.audio.pipeline.synthesis_options(tts, line, mall, voice_id)

The provider-specific `synthesize` kwargs for `line` in `voice_id`.

`{}` for a provider without a `synthesis_options` hook (offline,
mac_say) and for a voice written for another provider — which is what
keeps their cache keys where they were.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.audio.pipeline.takes_cost_message(lines, tts, audio_store)

What synthesizing `lines` with `tts` will bill, when any of them takes
best-of-N or `tts` bills per character (an#305: a voice that names a paid
provider is spoken by it with no flag, so its cost is said first); else `""`.

Counts only the requests not already in `audio_store` (a cached take is
free; a recorded take is restored, never billed), and the provider’s billed
characters per request (its `billed_characters(text, **options)` hook —
ElevenLabs counts the audio tags too). A provider without the hook bills no
characters, and the message says so.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.pipeline.tts_chooser(tts, mall, , make=None)

`voice_id -> provider`: who speaks a line in that voice (an#305).

A `tts` given (a provider, or a name `make` builds) speaks every line —
an override. Otherwise (`None`, `""`, [`VOICE_TTS`](#an.audio.pipeline.VOICE_TTS)) the voice
document’s `provider` decides, and a voice that declares none — or one
`make` has no provider for ([`voice_stand_ins()`](#an.audio.pipeline.voice_stand_ins) reports it) — is
spoken by [`DEFAULT_TTS_NAME`](#an.audio.pipeline.DEFAULT_TTS_NAME). One instance per provider name.
`make` defaults to [`an.audio.providers.make_tts()`](an.audio.providers.html.md#an.audio.providers.make_tts).

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`TTSProvider`](an.audio.tts.html.md#an.audio.tts.TTSProvider)]

```pycon
>>> mall = {"voices": {"bob": {"provider": "mac_say"}, "ann": {}}}
>>> choose = tts_chooser(None, mall)
>>> choose("bob").name, choose("ann").name, choose("nobody").name
('mac_say', 'offline', 'offline')
>>> tts_chooser("offline", mall)("bob").name
'offline'
```

### an.audio.pipeline.viseme_key(audio_key_, lipsync_name, transcript)

Content key of a line’s viseme track (a function of the audio HEARD).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.pipeline.voice_stand_ins(lines, mall, , overridden)

One message per voice whose lines are spoken by another provider than its
document declares; `lines` is `(voice_id, provider)` per line, and
`overridden` says whether a `tts` was given for every line.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from an.audio.offline_tts import OfflineTTS
>>> mall = {"voices": {"bob": {"provider": "elevenlabs"}}}
>>> print(voice_stand_ins([("bob", OfflineTTS())] * 2, mall, overridden=True)[0])
voice 'bob' declares provider 'elevenlabs', but its 2 line(s) are spoken by 'offline' — SILENT audio — because `tts` overrides every voice. Drop `--tts` to let each voice speak with its own provider.
>>> voice_stand_ins([("bob", OfflineTTS())], {}, overridden=True)
[]
```
