# an.ir.validate

Schema and semantic validation for SceneIR documents.

Two layers, called separately so callers can pick how strict to be:

- `validate_schema` — Pydantic validation only. Wrong types, missing required
  fields, malformed JSON.
- `validate_semantic` — cross-field checks. Unknown asset references,
  zero-duration shots, voice refs missing from a voices store.

Layout-overlap checks (boxes off-screen, text behind sprites) live in
`an.verify.layout`, not here, because they need a render context.

### Module Attributes

| [`RETIRED_KEYS`](#an.ir.validate.RETIRED_KEYS)                 | Keys an#106 retired, and what to write instead.                                                                                                                                                                                                                                                                                                              |
|-------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`RETIRED_CAMERA_KEYS`](#an.ir.validate.RETIRED_CAMERA_KEYS)          | an#109's removed camera fields.                                                                                                                                                                                                                                                                                                                              |
| [`DIALOGUE_OVERRUN_TOLERANCE_S`](#an.ir.validate.DIALOGUE_OVERRUN_TOLERANCE_S) | a frame at 60 fps.                                                                                                                                                                                                                                                                                                                                           |
| [`POST_SYNTHESIS_CHECKS`](#an.ir.validate.POST_SYNTHESIS_CHECKS)        | The registered checks whose answer depends on what synthesis produced — a line's real length, hence where it starts and ends — and that `an render` therefore runs again AFTER the audio pipeline, on the timing it will mux ([`post_synthesis_findings()`](#an.ir.validate.post_synthesis_findings) runs exactly these, by name, through the registry). |

### Functions

| [`post_synthesis_findings`](#an.ir.validate.post_synthesis_findings)(scene, \*[, fps, checks])   | `(check, finding)` for each finding the synthesized timing gives.                                                                                                                                             |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`registered_kind_problems`](#an.ir.validate.registered_kind_problems)(scene)                     | The findings of the three registry checks alone — every action kind, entity kind and renderer the scene names must be registered — without the rest of `validate_semantic` (no stores, no rig builds; cheap). |
| [`require_registered_kinds`](#an.ir.validate.require_registered_kinds)(scene, \*[, where])        | `scene`, or [`UnregisteredInSceneError`](#an.ir.validate.UnregisteredInSceneError) naming every action kind, entity kind and renderer it uses that is not registered.                                      |
| [`rig_stores`](#an.ir.validate.rig_stores)()                                        | `{entity kind: (mall store, descriptor kind)}` for every kind that has a rig.                                                                                                                                 |
| [`shot_dialogue_overruns`](#an.ir.validate.shot_dialogue_overruns)(shot, \*[, ...])             | `(k, message)` for each line of `shot` that ends past the shot's end.                                                                                                                                         |
| [`validate_schema`](#an.ir.validate.validate_schema)(doc)                                | Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema.                                                                                                                                   |
| [`validate_semantic`](#an.ir.validate.validate_semantic)(scene, \*[, ...])                 | Cross-field semantic checks.                                                                                                                                                                                  |

### Classes

| [`ValidationContext`](#an.ir.validate.ValidationContext)(scene, report, stores[, ...])   | What a registered semantic check ([`an.genres.SemanticCheck`](an.genres.html.md#an.genres.SemanticCheck)) reads.   |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| [`ValidationFinding`](#an.ir.validate.ValidationFinding)(severity, ir_path, description) | A single validation issue with a path into the IR.                                                                                           |
| [`ValidationReport`](#an.ir.validate.ValidationReport)([passed, findings])              | Result of running one or more validators.                                                                                                    |

### Exceptions

| [`UnregisteredInSceneError`](#an.ir.validate.UnregisteredInSceneError)(findings, \*[, where])   | A scene names kinds or renderers nothing registered: refused at load.   |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|

### an.ir.validate.DIALOGUE_OVERRUN_TOLERANCE_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.016666666666666666*

a frame at 60 fps.

* **Type:**
  Slack before a line counts as running past its shot

### an.ir.validate.POST_SYNTHESIS_CHECKS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('dialogue_fits', 'dialogue_in_dissolve', 'cutout.hidden_mouth_while_speaking')*

The registered checks whose answer depends on what synthesis produced — a
line’s real length, hence where it starts and ends — and that `an render`
therefore runs again AFTER the audio pipeline, on the timing it will mux
([`post_synthesis_findings()`](#an.ir.validate.post_synthesis_findings) runs exactly these, by name, through the
registry). A check added later that reads `Dialogue.duration` or `start`
belongs here; `tests/test_render_findings.py` lists the ones that do.

### an.ir.validate.RETIRED_CAMERA_KEYS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'focal_length', 'position', 'target'})*

an#109’s removed camera fields. A WARNING, not an error, and the difference
is the harm: a surviving `style` silently picks the wrong RENDERER, while
these three selected nothing — they described a 3D camera this package never
had. What is left is dead weight in a file, so it is worth saying and not
worth failing over.

Reported at all because the migration cannot reach them: a document already
at the current version is never migrated again, so a camera block that came
through a sync between the version bump and this check keeps them forever as
`extra="allow"` extras, and nothing else looks.

### an.ir.validate.RETIRED_KEYS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]* *= {'meta': {'default_style': 'default_renderer'}, 'shot': {'style': 'renderer'}}*

Keys an#106 retired, and what to write instead. `SceneIR`’s models are
`extra="allow"` (deliberately — forward compatibility), so a document that
still carries one of these validates cleanly and renders with the DEFAULT
renderer. The migration rewrites stored 0.1.x documents, but nothing rewrites
a document that is already 0.2.0: an agent patch, a hand edit, or a caller
passing `style=` to `Shot(...)` all produce a permanently dead key that no
later migration will touch. So it is caught here, at ERROR, by name.

### *exception* an.ir.validate.UnregisteredInSceneError(findings, , where='')

Bases: [`UnregisteredKindError`](an.genres.registry.html.md#an.genres.registry.UnregisteredKindError)

A scene names kinds or renderers nothing registered: refused at load.

Raised by [`require_registered_kinds()`](#an.ir.validate.require_registered_kinds) — what `an.load(project)`
(and so `an render`) runs, so a typo’d `kind:` or `renderer:` can no
longer render silently wrong now that the schema holds them as `str`
(review-244 S2). `findings` keeps each one with its IR path.

### *class* an.ir.validate.ValidationContext(scene, report, stores, voices=None, characters=None, sounds=None, library_lock=None, shot=None, index=None, memo=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a registered semantic check ([`an.genres.SemanticCheck`](an.genres.html.md#an.genres.SemanticCheck)) reads.

`stores` holds only the stores actually supplied, keyed by MALL name (an
absent one means its checks did not RUN — never that what it holds is
missing). `shot` and `index` are set while the `shot` stage runs.
`memo` is shared by every check of one `validate_semantic` call, so
two checks that need the same derived fact compute it once
([`cached()`](#an.ir.validate.ValidationContext.cached)).

#### cached(key, compute)

`compute()`, once per `key` per validation.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### library_lock *: [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)] | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The project’s asset-library lockfile (`mall["library_lock"]`, an#240);
`None` means the pin checks did not run.

#### *property* path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The IR path of the current shot (`timeline/<index>`).

### *class* an.ir.validate.ValidationFinding(severity, ir_path, description, location=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single validation issue with a path into the IR.

#### location *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

`"<file>:<line>"` when the thing to fix is an opaque source a shot runs
(a Manim scene file, an#279) rather than the IR; `None` otherwise.

### *class* an.ir.validate.ValidationReport(passed=True, findings=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of running one or more validators.

`passed` is True iff there are no error-severity findings.

### an.ir.validate.post_synthesis_findings(scene, , fps=None, checks=('dialogue_fits', 'dialogue_in_dissolve', 'cutout.hidden_mouth_while_speaking'), \*\*stores)

`(check, finding)` for each finding the synthesized timing gives.

The SAME registered checks `an validate` runs, selected by name
([`POST_SYNTHESIS_CHECKS`](#an.ir.validate.POST_SYNTHESIS_CHECKS)): dialogue past its shot’s end, a speaker
overlapping themself, a line heard during a dissolve, a line spoken while
the speaker’s view hides its mouth. `an render` calls this once the audio
pipeline has stamped every line’s real `duration`, so what `an validate`
could only estimate is reported exactly, at the moment it becomes known
(an#254). `fps` is the render’s (it decides the dissolve overlaps);
default the scene’s. `stores` are [`validate_semantic()`](#an.ir.validate.validate_semantic)’s
`available_*` keywords. A check no loaded genre registered is skipped.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`ValidationFinding`](#an.ir.validate.ValidationFinding)]]

### an.ir.validate.registered_kind_problems(scene)

The findings of the three registry checks alone — every action kind,
entity kind and renderer the scene names must be registered — without the
rest of `validate_semantic` (no stores, no rig builds; cheap).

* **Return type:**
  [`ValidationReport`](#an.ir.validate.ValidationReport)

### an.ir.validate.require_registered_kinds(scene, , where='')

`scene`, or [`UnregisteredInSceneError`](#an.ir.validate.UnregisteredInSceneError) naming every action
kind, entity kind and renderer it uses that is not registered.

* **Return type:**
  [`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR)

### an.ir.validate.rig_stores()

`{entity kind: (mall store, descriptor kind)}` for every kind that has a rig.

The core’s own (`prop`) plus the kinds genres register with a
`descriptor_kind` (the cut-out genre’s `character`): derived from the
registry, not a table the core edits (an#246).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> rig_stores()["prop"]
('props', 'PropDescriptor')
```

### an.ir.validate.shot_dialogue_overruns(shot, , effects_of=None, synthesized_only=False, tolerance_s=0.016666666666666666)

`(k, message)` for each line of `shot` that ends past the shot’s end.

The ONE overrun check: `an validate` runs it, the audio pipeline runs it
after synthesis ([`an.audio.pipeline.dialogue_overruns()`](an.audio.pipeline.html.md#an.audio.pipeline.dialogue_overruns)), and `an
render` reports it from the rendered timing ([`post_synthesis_findings()`](#an.ir.validate.post_synthesis_findings)).

The audio is cut at the shot end (each shot’s mix is trimmed to its
duration), and the lines play back to back, so a shot shortened below its
dialogue loses the tail of it — silently, until now (an e2e run shrank an
8.2 s shot holding 7.1 s of speech to 3.0 s and `an validate` said nothing).

What is known depends on when this runs. After the audio pipeline, a line
carries its real `duration` and the check is exact. Before it, the
duration is the offline voice’s estimate
([`an.audio.offline_tts.estimate_speech_duration()`](an.audio.offline_tts.html.md#an.audio.offline_tts.estimate_speech_duration) over the voice’s
`tempo` — exactly what an offline render will give, and an
under-estimate for a real voice). Either
way the lines are laid out by the pipeline’s own rule,
[`an.ir.schema.Dialogue.planned_start()`](an.ir.schema.html.md#an.ir.schema.Dialogue.planned_start) — back to back from the shot
start, shifted by each line’s `pause` or pinned by its `at` (an#187) —
so a pause edited after synthesis is judged where it will play, not where
the stale stamp says. `effects_of` (

```
``
```

line -> \`\` its voice’s normalised
effects) supplies the tempo, and — for a synthesized line whose voice does
not trim — the fix of trimming the silence a real voice pads a line with.

```pycon
>>> from an.ir.schema import Dialogue, Shot
>>> shot = Shot(id="s", duration=1.0, dialogue=[
...     Dialogue(speaker="a", text="hi", start=0.2, duration=1.3, audio_ref="k")])
>>> [(k, m[:44]) for k, m in shot_dialogue_overruns(shot)]
[(0, 'line 0 (a) ends at 1.30s as synthesized, pas')]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.ir.validate.validate_schema(doc)

Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema.

* **Return type:**
  [`ValidationReport`](#an.ir.validate.ValidationReport)

```pycon
>>> validate_schema({"meta": {"title": "x"}, "timeline": []}).passed
True
>>> r = validate_schema({"meta": {"title": "x"}, "timeline": [{"id": "s", "duration": "not-a-number"}]})
>>> r.passed
False
```

### an.ir.validate.validate_semantic(scene, , available_voices=None, available_characters=None, available_props=None, available_environments=None, available_sounds=None, available_library_lock=None, available_styles=None, only=None, fps=None)

Cross-field semantic checks. Pass live stores in for cross-store checks.

Both `available_voices` and `available_characters` accept any mapping;
`available_props` is the same thing for `kind="prop"` entities (an#108),
and `available_environments` lets the flat-pan warning read a stage’s
planes (an#111) —
without it a prop’s swaps are reported as having no descriptor, which is
validate refusing what compile accepts.
Voices are consulted via `__contains__` only; characters additionally
via `__getitem__` (the swap-reference and `play` checks read descriptor
dicts, an#87 / an#7). Pass `None` to skip those checks — and know that
skipping them is what it sounds like: a `play` or a swap the compiler
will refuse passes silently without the store (the CLI, `an validate`,
always passes it).

`available_styles` is the project’s `styles` store: a check reads the
StylePack the scene names (`meta.style_pack`) from `ctx.stores["styles"]`
(a style’s `policy`, an#348).

`available_library_lock` is the project’s asset-library lockfile
(`mall["library_lock"]`): with it, every scene `library:` pin is checked
against the lockfile (`warning` on disagreement) and every pinned
check-out against its library version (`info` when it has been edited).

The checks are a REGISTRY ([`an.genres.registry.register_check()`](an.genres.registry.html.md#an.genres.registry.register_check)):
the core’s own register below, a genre’s when it is loaded (the cut-out
genre’s `play`, `expression`, turn and view checks), and they run in
stages — `scene`, then `shot` once per shot, then `finish` — each by
its `order`. An action or entity kind no loaded genre registered is one
error naming the genre that provides it; checks that would trip over it
skip that shot rather than crash.

`only` runs just the registered checks of those names (what `an render`
does after synthesis, [`post_synthesis_findings()`](#an.ir.validate.post_synthesis_findings)); `fps` is the one
the film is assembled at when it is not the scene’s (`an render --fps`),
which decides how long a dissolve’s overlap is.

* **Return type:**
  [`ValidationReport`](#an.ir.validate.ValidationReport)
