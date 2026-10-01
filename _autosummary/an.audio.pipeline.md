# an.audio.pipeline

Audio pipeline orchestration: dialogue → audio → visemes → IR mutation.

Phase 3 wires the pieces together. `produce_audio_for_scene` walks every
`Dialogue` in the scene, synthesizes its audio + viseme track via the
configured providers, persists artifacts to `mall["audio"]` /
`mall["visemes"]`, and stamps the resulting `VisemeTrack` and timing
back onto the `Dialogue` line so renderers can find it.

Defaults are the offline providers (silent WAV + deterministic visemes), so
the entire pipeline runs without API keys or external binaries.

```pycon
>>> from an.audio.pipeline import default_tts, default_lipsync
>>> default_tts().name
'offline'
>>> default_lipsync().name
'offline'
```

### Module Attributes

| [`TakeScorerFactory`](#an.audio.pipeline.TakeScorerFactory)           | `(TakesSpec) -> TakeScorer` — the seam that turns a takes spec into its scorer.                             |
|------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| [`OVERRUN_TOLERANCE_S`](#an.audio.pipeline.OVERRUN_TOLERANCE_S)         | a frame at 60 fps (the same as `an validate`'s).                                                            |
| [`REROLL_ONLY_HINT`](#an.audio.pipeline.REROLL_ONLY_HINT)            | only a new roll (new keys) replaces it.                                                                     |
| [`LEGACY_DURATION_TOLERANCE_S`](#an.audio.pipeline.LEGACY_DURATION_TOLERANCE_S) | How far a legacy sidecar's duration may sit from its audio's and still be the same take: a frame at 60 fps. |

### Functions

| [`audio_key`](#an.audio.pipeline.audio_key)(text, voice_id, tts_name[, ...])        | Content key of a line's audio: text, voice, provider, and — only when the voice declares them — its effects, the provider voice it names (an#194), the provider's synthesis options (model, settings, seed, audio tags — an#209).   |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`default_lipsync`](#an.audio.pipeline.default_lipsync)()                                 | The default lip-sync provider: `OfflineLipSync`.                                                                                                                                                                                    |
| [`default_tts`](#an.audio.pipeline.default_tts)()                                     | The default TTS provider: `OfflineTTS`.                                                                                                                                                                                             |
| [`dialogue_overruns`](#an.audio.pipeline.dialogue_overruns)(scene, \*[, tolerance_s, mall]) | One message per synthesized line that ends past its shot's end.                                                                                                                                                                     |
| [`produce_audio_for_dialogue`](#an.audio.pipeline.produce_audio_for_dialogue)(dialogue[, mall, ...]) | Synthesize audio + visemes for one dialogue line.                                                                                                                                                                                   |
| [`produce_audio_for_scene`](#an.audio.pipeline.produce_audio_for_scene)(scene[, mall, tts, ...])  | Walk every dialogue line, synthesize, and stamp viseme tracks back.                                                                                                                                                                 |
| [`retake_lines`](#an.audio.pipeline.retake_lines)(scene, mall, match, \*, tts[, ...])  | Mark the recorded takes of the lines whose text contains `match` to be chosen again on the next render; one message per matching line.                                                                                              |
| [`retime_dialogue`](#an.audio.pipeline.retime_dialogue)(scene, \*[, timed_shots_only])    | Stamp every synthesized line's `start` from its `pause` / `at`.                                                                                                                                                                     |
| [`stamp_from_stores`](#an.audio.pipeline.stamp_from_stores)(scene, mall, \*, tts, lipsync)  | Stamp `scene`'s dialogue exactly as [`produce_audio_for_scene()`](#an.audio.pipeline.produce_audio_for_scene) would with these providers — from the content-keyed `audio` and `visemes` stores only.                               |
| [`synthesis_options`](#an.audio.pipeline.synthesis_options)(tts, line, mall, voice_id)      | The provider-specific `synthesize` kwargs for `line` in `voice_id`.                                                                                                                                                                 |
| [`takes_cost_message`](#an.audio.pipeline.takes_cost_message)(lines, tts, audio_store)       | What synthesizing `lines` will bill, when any of them takes best-of-N; else `""`.                                                                                                                                                   |
| [`viseme_key`](#an.audio.pipeline.viseme_key)(audio_key_, lipsync_name, transcript)  | Content key of a line's viseme track (a function of the audio HEARD).                                                                                                                                                               |

### Exceptions

| [`AudioNotCachedError`](#an.audio.pipeline.AudioNotCachedError)    | A line's audio (or its visemes) is not in the content-keyed stores, so stamping it would need a synthesis this caller does not allow.   |
|-------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| [`AudioPipelineError`](#an.audio.pipeline.AudioPipelineError)     | The scene declares audio the pipeline cannot produce.                                                                                   |
| [`DialogueOverrunWarning`](#an.audio.pipeline.DialogueOverrunWarning) | A synthesized line runs past its shot's end, so its tail is cut.                                                                        |
| [`TakeDigestWarning`](#an.audio.pipeline.TakeDigestWarning)      | The audio restored for a line's recorded take is not the audio the record names.                                                        |

### *exception* an.audio.pipeline.AudioNotCachedError

Bases: [`AudioPipelineError`](#an.audio.pipeline.AudioPipelineError)

A line’s audio (or its visemes) is not in the content-keyed stores, so
stamping it would need a synthesis this caller does not allow.

### *exception* an.audio.pipeline.AudioPipelineError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The scene declares audio the pipeline cannot produce. Carries detail.

### *exception* an.audio.pipeline.DialogueOverrunWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A synthesized line runs past its shot’s end, so its tail is cut.

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

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`TakesSpec`](an.audio.takes.md#an.audio.takes.TakesSpec)], [`TakeScorer`](an.audio.takes.md#an.audio.takes.TakeScorer)]

### an.audio.pipeline.audio_key(text, voice_id, tts_name, effects=None, , provider_voice=None, options=None, takes=None, take=None, roll=None)

Content key of a line’s audio: text, voice, provider, and — only when the
voice declares them — its effects, the provider voice it names (an#194),
the provider’s synthesis options (model, settings, seed, audio tags —
an#209). With none of them, the payload is exactly the pre-effects one, so
every key a project already has is unchanged. `take` (1, 2, … — never 0)
and `roll` (1, 2, … after `an voices reroll`) key one candidate take of
a best-of-N line; take 0 of roll 0 is the single-take request and keeps its
key. `takes` ([`an.audio.takes.takes_choice_part()`](an.audio.takes.md#an.audio.takes.takes_choice_part)) keys the CHOICE
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

The default lip-sync provider: `OfflineLipSync`.

* **Return type:**
  [`LipSyncProvider`](an.audio.lipsync.md#an.audio.lipsync.LipSyncProvider)

### an.audio.pipeline.default_tts()

The default TTS provider: `OfflineTTS`.

* **Return type:**
  [`TTSProvider`](an.audio.tts.md#an.audio.tts.TTSProvider)

### an.audio.pipeline.dialogue_overruns(scene, , tolerance_s=0.016666666666666666, mall=None)

One message per synthesized line that ends past its shot’s end.

`an validate` warns before synthesis from an estimate; this is the exact
check AFTER it — a voice’s `tempo` (or a real voice’s own pace, or the
silence it pads a line with) can make a line longer than estimated, and the
render cuts the shot’s audio at the shot’s end, so the tail would otherwise
be lost silently. It is `an validate`’s own check
([`an.ir.validate.shot_dialogue_overruns()`](an.ir.validate.md#an.ir.validate.shot_dialogue_overruns)), over the synthesized lines;
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

`voice_id` (default: the line’s `voice_ref`, else `"default"`) is the
`voices`-store key; [`produce_audio_for_scene()`](#an.audio.pipeline.produce_audio_for_scene) passes the one
[`an.audio.voices.line_voice_id()`](an.audio.voices.md#an.audio.voices.line_voice_id) resolves, so a character’s bound
voice reaches here (an#194). The provider is handed the voice document’s
own voice id when it names one.

What the provider’s optional `synthesis_options` hook derives from the
voice document and the line (ElevenLabs: `model_id`, `voice_settings`,
`seed`, and the `[emotion]`/`direction` audio tags — an#209) is passed
to `synthesize` and keyed; the text handed to alignment is always the
bare `dialogue.text`, never the tagged one.

`takes` (default: what the voice declares for this line — see
[`an.audio.takes`](an.audio.takes.md#module-an.audio.takes); `None` forces one take) synthesizes several takes,
scores each with `take_scorer(spec)` on the audio the viewer hears, keeps
the best and records the choice in `mall["takes"]`. A recorded choice is
restored from the record and never re-rolled; a recorded take whose audio is
gone raises [`TakeLostError`](an.audio.takes.md#an.audio.takes.TakeLostError) before any request.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`AudioClip`](an.audio.tts.md#an.audio.tts.AudioClip), [`VisemeTrack`](an.audio.lipsync.md#an.audio.lipsync.VisemeTrack)]

### an.audio.pipeline.produce_audio_for_scene(scene, mall=None, \*, tts=None, lipsync=None, take_scorer=<function make_take_scorer>, announce=<function \_announce_to_stderr>, overruns=True)

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

* **Return type:**
  [`SceneIR`](an.ir.schema.md#an.ir.schema.SceneIR)

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
  [`SceneIR`](an.ir.schema.md#an.ir.schema.SceneIR)

```pycon
>>> from an.ir.schema import Dialogue, SceneIR, Shot
>>> shot = Shot(id="s", dialogue=[
...     Dialogue(speaker="a", text="hi", start=0.0, duration=0.5, audio_ref="k1"),
...     Dialogue(speaker="b", text="bye", start=0.5, duration=0.4, audio_ref="k2",
...              pause=1.5)])
>>> [d.start for d in retime_dialogue(SceneIR(timeline=[shot])).timeline[0].dialogue]
[0.0, 2.0]
```

### an.audio.pipeline.stamp_from_stores(scene, mall, , tts, lipsync)

Stamp `scene`’s dialogue exactly as [`produce_audio_for_scene()`](#an.audio.pipeline.produce_audio_for_scene)
would with these providers — from the content-keyed `audio` and
`visemes` stores only. Synthesises, aligns and writes nothing; a line the
stores cannot answer raises [`AudioNotCachedError`](#an.audio.pipeline.AudioNotCachedError).

What a reader of the render’s cache keys needs (an#274): a `scene.md`
edit drops every stamp on re-sync, and the next render re-stamps the same
audio from the stores, so the keys a render WILL use are these, not the
unstamped IR’s. Mutates `scene` in place and returns it.

* **Return type:**
  [`SceneIR`](an.ir.schema.md#an.ir.schema.SceneIR)

### an.audio.pipeline.synthesis_options(tts, line, mall, voice_id)

The provider-specific `synthesize` kwargs for `line` in `voice_id`.

`{}` for a provider without a `synthesis_options` hook (offline,
mac_say) and for a voice written for another provider — which is what
keeps their cache keys where they were.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.audio.pipeline.takes_cost_message(lines, tts, audio_store)

What synthesizing `lines` will bill, when any of them takes best-of-N; else `""`.

Counts only the requests not already in `audio_store` (a cached take is
free; a recorded take is restored, never billed), and the provider’s billed
characters per request (its `billed_characters(text, **options)` hook —
ElevenLabs counts the audio tags too). A provider without the hook bills no
characters, and the message says so.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.pipeline.viseme_key(audio_key_, lipsync_name, transcript)

Content key of a line’s viseme track (a function of the audio HEARD).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
