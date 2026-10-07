# an.audio.takes

Best-of-N takes: re-roll a line, score every take, keep the best, record the choice.

An expressive TTS model does not repeat itself: `eleven_v3` returned three
different files for three byte-identical requests (same text, voice, settings
and seed), and the spread between two takes of one line was larger than the
effect of any voice setting. So the way to land a delivery on its measured
targets is to synthesize a few takes and keep the one that measures closest.

A voice document opts in with `takes`:

```default
{"voice_id": "...", "model_id": "eleven_v3",
 "takes": {"n": 3,                                  # takes per line (1 = off)
           "targets": {"articulation_rate_sps": [5.2, 6.3], ...},
           "cues": {"deadpan": {"n": 4, "targets": {...}}}}}
```

- `n` — takes per line; `1` (the default) is today’s single take, byte for
  byte. A bare integer (`takes: 3`) is `{"n": 3}`.
- `targets` — `[low, high]` prosody targets ([`an.verify.prosody.METRICS`](an.verify.prosody.html.md#an.verify.prosody.METRICS))
  the default scorer measures each take against. A style’s targets are named by
  role in its spec; [`style_voice_role()`](#an.audio.takes.style_voice_role) resolves those names into values
  when the style is applied, so the voice document holds numbers, never names.
- `reference_hz` — the voice’s neutral median pitch, for a `register_st` target.
- `cues` — per-line opt-in: a line whose `{direction}` carries one of these
  cues uses that entry’s `n` / `targets` / `reference_hz` over the
  voice’s (the first matching cue, in the line’s order, wins). So a narrator
  can re-roll only its `{deadpan}` punchlines, scored as punchlines.
- `scorer` — the scorer’s name (default `prosody`); the scorer itself is a
  seam ([`TakeScorer`](#an.audio.takes.TakeScorer), the pipeline’s `take_scorer=`).

How the pipeline uses it ([`an.audio.pipeline`](an.audio.pipeline.html.md#module-an.audio.pipeline)):

1. **Every take has its own content key.** Take `0` of roll `0` is the
   request a single take makes, under the same key — turning takes on for a
   line already synthesized reuses that take and pays for `n - 1` more. Take
   `i` adds `take: i` (and a re-roll adds `roll: r`) to its key, and a
   provider may vary its request per take (ElevenLabs offsets a declared
   `seed` by `i`). The audio a line KEEPS is the chosen take’s own heard
   key (its effects applied), so a different take is a different
   `audio_ref`, and its visemes, word timings and captions follow it.
2. Each take is scored on the audio the viewer hears (the voice’s effects
   applied, so a `tempo` counts toward the rate); the lowest score wins, ties
   to the lower take index.
3. **The record is the resolution** (ADR 0003 decision 3). The choice is
   written to `mall["takes"]` under the line’s *choice key* — the line’s
   request, `n`, the scorer’s name and its configuration (its targets), but
   NOT its version — with the chosen take, the sha256 of what it sounds like,
   every take’s keys, digests and scores, and the scorer that chose. Every
   render reads it first:
   - the chosen take is restored from the record (its heard audio, else its
     raw audio with the effects re-applied) and never re-billed;
   - a hand edit of `chosen` wins: that take is restored, the record says
     `superseded_by: hand` and the decision is logged;
   - a chosen take whose audio is gone is a [`TakeLostError`](#an.audio.takes.TakeLostError) raised
     before any request — `an voices reroll` is the explicit way to re-roll;
   - a record made by an older scorer version is KEPT, and the render reports
     it — `an voices rescore` re-chooses explicitly, from the cached takes.

   Changing `n`, the targets, the scorer or the voice’s effects is a new
   choice key, chosen from the takes already cached where it can.

```pycon
>>> spec = takes_spec({"n": 3, "targets": {"f0_sd_st": [2, 4]}})
>>> spec.n, spec.scorer, dict(spec.targets)
(3, 'prosody', {'f0_sd_st': [2.0, 4.0]})
>>> takes_spec(None) is None and takes_spec(1) is None
True
>>> doc = {"n": 1, "cues": {"deadpan": {"n": 4, "targets": {"final_drop_st": [-3.6, -1.7]}}}}
>>> takes_spec(doc, direction=["deadpan"]).n, takes_spec(doc, direction=["excited"])
(4, None)
>>> takes_spec({"n": 3})
Traceback (most recent call last):
    ...
an.audio.takes.VoiceTakesError: takes: n=3 with the prosody scorer needs `targets` ([low, high] per metric) to choose by
>>> choose_take([TakeScore((0.5, 1.0)), TakeScore((0.0, 2.0)), TakeScore((0.0, 2.0))])
1
```

### Module Attributes

| [`TAKES_KEY`](#an.audio.takes.TAKES_KEY)              | The key, in a voice document, declaring best-of-N takes.                                                                                                                                                                           |
|-------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`TAKES_STORE`](#an.audio.takes.TAKES_STORE)            | The name of the store the choices are recorded in.                                                                                                                                                                                 |
| [`DEFAULT_SCORER`](#an.audio.takes.DEFAULT_SCORER)         | The scorer a `takes` declaration uses when it names none.                                                                                                                                                                          |
| [`MAX_TAKES`](#an.audio.takes.MAX_TAKES)              | each one is a billed request.                                                                                                                                                                                                      |
| [`TAKES_RECORD_VERSION`](#an.audio.takes.TAKES_RECORD_VERSION)   | The shape of a record in `mall["takes"]`; raised when a field changes meaning.                                                                                                                                                     |
| [`PROSODY_SCORER_VERSION`](#an.audio.takes.PROSODY_SCORER_VERSION) | The prosody scorer's own version (its distance and tie-break); the estimator's version ([`an.verify.prosody.ESTIMATOR_VERSION`](an.verify.prosody.html.md#an.verify.prosody.ESTIMATOR_VERSION)) is joined to it. |
| [`SCORING_SAMPLE_RATE`](#an.audio.takes.SCORING_SAMPLE_RATE)    | The sample rate takes are decoded at for scoring — the one the targets were measured at.                                                                                                                                           |
| [`REROLL_HINT`](#an.audio.takes.REROLL_HINT)            | What to run when a recorded take must be replaced (named in every error).                                                                                                                                                          |
| [`SCORERS`](#an.audio.takes.SCORERS)                | `TakesSpec -> TakeScorer`.                                                                                                                                                                                                         |

### Functions

| [`audio_digest`](#an.audio.takes.audio_digest)(audio)                               | The sha256 a takes record names a take's audio by.                                                                                                                                                                                |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`choose_take`](#an.audio.takes.choose_take)(scores)                               | The index of the best take: the lowest score, ties to the lower index.                                                                                                                                                            |
| [`decode_for_scoring`](#an.audio.takes.decode_for_scoring)(audio, \*[, sr])               | `audio` as mono float samples at `sr` Hz, decoded by ffmpeg — the decoder the targets were measured with, and the only one, so the same bytes score the same on every machine.                                                    |
| [`make_take_scorer`](#an.audio.takes.make_take_scorer)(spec)                            | The scorer `spec` names, from [`SCORERS`](#an.audio.takes.SCORERS) (the pipeline's default `take_scorer`).                                                                                                    |
| [`normalize_takes`](#an.audio.takes.normalize_takes)(raw)                              | The canonical `takes` declaration of a voice document (`{}` for none).                                                                                                                                                            |
| [`read_takes_record`](#an.audio.takes.read_takes_record)(store, key)                     | The takes record under `key` in `store` (`mall["takes"]`), or `None`.                                                                                                                                                             |
| [`require_ffmpeg`](#an.audio.takes.require_ffmpeg)()                                  | Raise [`VoiceTakesError`](#an.audio.takes.VoiceTakesError) with the install hint when ffmpeg is not on PATH.                                                                                                          |
| [`scorer_identity`](#an.audio.takes.scorer_identity)(scorer)                           | The scorer as a record names it: name, version and configuration.                                                                                                                                                                 |
| [`style_voice_role`](#an.audio.takes.style_voice_role)(spec, role)                      | The partial voice document a style casts `role` as, with target NAMES resolved.                                                                                                                                                   |
| [`takes_choice_part`](#an.audio.takes.takes_choice_part)(scorer, n)                      | What identifies a CHOICE among `n` takes: the scorer's name and its configuration, never its version — a new scorer version keeps the takes it chose, and says so ([`REROLL_HINT`](#an.audio.takes.REROLL_HINT)). |
| [`takes_spec`](#an.audio.takes.takes_spec)(raw, \*[, direction])                  | The takes a line with `direction` gets from a voice's `takes`, or `None` for one take.                                                                                                                                            |
| [`voice_takes`](#an.audio.takes.voice_takes)(mall, voice_id, \*[, direction, ...]) | The takes `mall["voices"][voice_id]` declares for a line with `direction`.                                                                                                                                                        |
| [`write_takes_record`](#an.audio.takes.write_takes_record)(store, key, record)            | Write `record` under `key` (stable, indented JSON); no store, no record.                                                                                                                                                          |

### Classes

| [`ProsodyTakeScorer`](#an.audio.takes.ProsodyTakeScorer)(targets, \*[, reference_hz, sr])   | Scores a take by how far its prosody sits from `[low, high]` targets.         |
|-------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`TakeScore`](#an.audio.takes.TakeScore)(value[, detail])                           | A take's score — compared as a tuple, lower is better — and what it measured. |
| [`TakeScorer`](#an.audio.takes.TakeScorer)(\*args, \*\*kwargs)                       | Scores one take of a line.                                                    |
| [`TakesSpec`](#an.audio.takes.TakesSpec)(n[, scorer, targets, reference_hz])        | The takes ONE line gets: how many, and what chooses between them.             |

### Exceptions

| [`TakeLostError`](#an.audio.takes.TakeLostError)    | A line's recorded take is gone from the audio store and cannot be restored.   |
|-------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`TakesRecordError`](#an.audio.takes.TakesRecordError) | A `mall["takes"]` record cannot be read as a takes record.                    |
| [`VoiceTakesError`](#an.audio.takes.VoiceTakesError)  | A voice's `takes` declaration is malformed, or cannot be scored.              |

### an.audio.takes.DEFAULT_SCORER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'prosody'*

The scorer a `takes` declaration uses when it names none.

### an.audio.takes.MAX_TAKES *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 10*

each one is a billed request.

* **Type:**
  More takes than this per line is refused

### an.audio.takes.PROSODY_SCORER_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '1'*

The prosody scorer’s own version (its distance and tie-break); the
estimator’s version ([`an.verify.prosody.ESTIMATOR_VERSION`](an.verify.prosody.html.md#an.verify.prosody.ESTIMATOR_VERSION)) is joined to it.

### *class* an.audio.takes.ProsodyTakeScorer(targets, , reference_hz=None, sr=16000)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Scores a take by how far its prosody sits from `[low, high]` targets.

The score is [`an.verify.prosody.target_distance()`](an.verify.prosody.html.md#an.verify.prosody.target_distance): the summed distance
outside the ranges, then the summed distance from their midpoints (the
tie-break between takes all on target), in units of each range’s width.

#### SCORE_MEANS *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= "score = [outside, off_centre], lower is better; the take with the smallest pair is kept. outside: for each target in scorer.config.targets, how far the measured value sits outside its [low, high] range, in widths of that range (0 inside; a value this take cannot measure, listed in \`unmeasured\`, counts 1). off_centre: each value's distance from its range's middle, in the same units (the tie-break). \`measured\` holds the values, \`misses\` the targets missed."*

What a take’s `score` pair means, written into each takes record (an#397).

#### check_available()

Raise before any request when this scorer could not score (no ffmpeg).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.takes.REROLL_HINT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 're-roll it explicitly with \`an voices reroll <project> <words of the line>\` (new takes, billed) or, while every take of its roll is still cached, re-choose among them with \`an voices rescore <project> <words of the line>\`'*

What to run when a recorded take must be replaced (named in every error).

### an.audio.takes.SCORERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[TakesSpec](#an.audio.takes.TakesSpec)], [TakeScorer](#an.audio.takes.TakeScorer)]]* *= {'prosody': <function <lambda>>}*

`TakesSpec -> TakeScorer`.

* **Type:**
  Scorer factories by name

### an.audio.takes.SCORING_SAMPLE_RATE *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 16000*

The sample rate takes are decoded at for scoring — the one the targets were measured at.

### an.audio.takes.TAKES_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'takes'*

The key, in a voice document, declaring best-of-N takes.

### an.audio.takes.TAKES_RECORD_VERSION *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

The shape of a record in `mall["takes"]`; raised when a field changes meaning.

### an.audio.takes.TAKES_STORE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'takes'*

The name of the store the choices are recorded in.

### *exception* an.audio.takes.TakeLostError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A line’s recorded take is gone from the audio store and cannot be restored.

Raised before any request: re-rolling an approved take is never implicit.

### *class* an.audio.takes.TakeScore(value, detail=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A take’s score — compared as a tuple, lower is better — and what it measured.

### *class* an.audio.takes.TakeScorer(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Scores one take of a line. Deterministic: the same bytes score the same.

`name`, `version` and `config` enter the line’s audio key, so a scorer
that would choose differently must differ in one of them.

#### score(audio, text)

Score `audio` (any container ffmpeg reads; WAV without it) speaking `text`.

* **Return type:**
  [`TakeScore`](#an.audio.takes.TakeScore)

### *exception* an.audio.takes.TakesRecordError

Bases: [`VoiceTakesError`](#an.audio.takes.VoiceTakesError)

A `mall["takes"]` record cannot be read as a takes record.

### *class* an.audio.takes.TakesSpec(n, scorer='prosody', targets=<factory>, reference_hz=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The takes ONE line gets: how many, and what chooses between them.

### *exception* an.audio.takes.VoiceTakesError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A voice’s `takes` declaration is malformed, or cannot be scored.

### an.audio.takes.audio_digest(audio)

The sha256 a takes record names a take’s audio by.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.takes.choose_take(scores)

The index of the best take: the lowest score, ties to the lower index.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.audio.takes.decode_for_scoring(audio, , sr=16000)

`audio` as mono float samples at `sr` Hz, decoded by ffmpeg — the decoder
the targets were measured with, and the only one, so the same bytes score the
same on every machine. Raises [`VoiceTakesError`](#an.audio.takes.VoiceTakesError) without ffmpeg.

### an.audio.takes.make_take_scorer(spec)

The scorer `spec` names, from [`SCORERS`](#an.audio.takes.SCORERS) (the pipeline’s default `take_scorer`).

* **Return type:**
  [`TakeScorer`](#an.audio.takes.TakeScorer)

### an.audio.takes.normalize_takes(raw)

The canonical `takes` declaration of a voice document (`{}` for none).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> normalize_takes(3)
{'n': 3}
>>> normalize_takes({"cues": {"deadpan": 4}})
{'cues': {'deadpan': {'n': 4}}}
```

### an.audio.takes.read_takes_record(store, key)

The takes record under `key` in `store` (`mall["takes"]`), or `None`.

Raises [`TakesRecordError`](#an.audio.takes.TakesRecordError) — naming the record and the remedy — for one
that is not JSON, not a mapping, or whose `chosen` names no take.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> read_takes_record({}, "k") is None
True
>>> read_takes_record({"k": b'{"chosen": 0, "takes": [{"take": 0}]}'}, "k")["chosen"]
0
>>> read_takes_record({"k": b"[1, 2]"}, "k")
Traceback (most recent call last):
    ...
an.audio.takes.TakesRecordError: the takes record 'k' is not a takes record (a JSON object with `chosen` and `takes`): ...
```

### an.audio.takes.require_ffmpeg()

Raise [`VoiceTakesError`](#an.audio.takes.VoiceTakesError) with the install hint when ffmpeg is not on PATH.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.takes.scorer_identity(scorer)

The scorer as a record names it: name, version and configuration.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.audio.takes.style_voice_role(spec, role)

The partial voice document a style casts `role` as, with target NAMES resolved.

A style spec (`cutan.style_spec(name)`) declares
`live.voice.roles.<role>` and may name a delivery’s targets by its key in
`prosody_targets` (`takes: {n: 3, targets: narrator}`). This returns a
copy whose `takes` (and each cue’s) hold the target VALUES, ready to merge
beside a `voice_id`: `{**style_voice_role(spec, "narrator"), "voice_id": ...}`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> spec = {"live": {"voice": {"roles": {"narrator": {"model_id": "eleven_v3",
...     "takes": {"n": 2, "targets": "narrator", "cues": {"deadpan": {"targets": "punchline"}}}}}}},
...     "prosody_targets": {"narrator": {"f0_sd_st": [3.9, 5.2]}, "punchline": {"f0_sd_st": [2.2, 3.4]}}}
>>> role = style_voice_role(spec, "narrator")
>>> role["takes"]["targets"], role["takes"]["cues"]["deadpan"]["targets"]
({'f0_sd_st': [3.9, 5.2]}, {'f0_sd_st': [2.2, 3.4]})
```

### an.audio.takes.takes_choice_part(scorer, n)

What identifies a CHOICE among `n` takes: the scorer’s name and its
configuration, never its version — a new scorer version keeps the takes it
chose, and says so ([`REROLL_HINT`](#an.audio.takes.REROLL_HINT)).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.audio.takes.takes_spec(raw, , direction=None)

The takes a line with `direction` gets from a voice’s `takes`, or `None` for one take.

Raises [`VoiceTakesError`](#an.audio.takes.VoiceTakesError) for a malformed declaration, and for more
than one take with nothing to choose by.

* **Return type:**
  [`TakesSpec`](#an.audio.takes.TakesSpec) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.takes.voice_takes(mall, voice_id, , direction=None, tts_name=None, repeatable=False)

The takes `mall["voices"][voice_id]` declares for a line with `direction`.

`None` (one take) for a voice not in the store, one declaring nothing, one
written for another provider than `tts_name`, and any voice spoken by a
`repeatable` provider (`offline`, `mac_say`: the same request gives the
same audio, so a second take is the first one again). A malformed
declaration raises [`VoiceTakesError`](#an.audio.takes.VoiceTakesError) in every case.

* **Return type:**
  [`TakesSpec`](#an.audio.takes.TakesSpec) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.takes.write_takes_record(store, key, record)

Write `record` under `key` (stable, indented JSON); no store, no record.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
