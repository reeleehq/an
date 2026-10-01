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

| [`RIG_STORES`](#an.ir.validate.RIG_STORES)                   | Entity kind → (the mall store holding its rig, the descriptor `kind` tag that store's documents carry).   |
|-------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| [`RETIRED_KEYS`](#an.ir.validate.RETIRED_KEYS)                 | Keys an#106 retired, and what to write instead.                                                           |
| [`RETIRED_CAMERA_KEYS`](#an.ir.validate.RETIRED_CAMERA_KEYS)          | an#109's removed camera fields.                                                                           |
| [`DIALOGUE_OVERRUN_TOLERANCE_S`](#an.ir.validate.DIALOGUE_OVERRUN_TOLERANCE_S) | a frame at 60 fps.                                                                                        |

### Functions

| [`check_character_refs`](#an.ir.validate.check_character_refs)(ctx)                    | The cut-out genre's missing-character warning.                                                                                                                                                                |
|-----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`check_expression_actions`](#an.ir.validate.check_expression_actions)(ctx)                | The cut-out genre's `expression` / `[emotion]` check.                                                                                                                                                         |
| [`check_hidden_mouth_while_speaking`](#an.ir.validate.check_hidden_mouth_while_speaking)(ctx)       | The cut-out genre's mouth-hidden-by-a-view warning.                                                                                                                                                           |
| [`check_play_actions`](#an.ir.validate.check_play_actions)(ctx)                      | The cut-out genre's `play` check (`_check_play_actions()`).                                                                                                                                                   |
| [`check_turns`](#an.ir.validate.check_turns)(ctx)                             | The cut-out genre's contradicted-turn warning (`_check_turns()`).                                                                                                                                             |
| [`check_view_continuity`](#an.ir.validate.check_view_continuity)(ctx)                   | The cut-out genre's view-across-a-cut warning (`_check_view_continuity()`).                                                                                                                                   |
| [`registered_kind_problems`](#an.ir.validate.registered_kind_problems)(scene)              | The findings of the three registry checks alone — every action kind, entity kind and renderer the scene names must be registered — without the rest of `validate_semantic` (no stores, no rig builds; cheap). |
| [`require_registered_kinds`](#an.ir.validate.require_registered_kinds)(scene, \*[, where]) | `scene`, or [`UnregisteredInSceneError`](#an.ir.validate.UnregisteredInSceneError) naming every action kind, entity kind and renderer it uses that is not registered.                                      |
| [`validate_schema`](#an.ir.validate.validate_schema)(doc)                         | Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema.                                                                                                                                   |
| [`validate_semantic`](#an.ir.validate.validate_semantic)(scene, \*[, ...])          | Cross-field semantic checks.                                                                                                                                                                                  |

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

### an.ir.validate.RIG_STORES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]* *= {'character': ('characters', 'CharacterDescriptor'), 'prop': ('props', 'PropDescriptor')}*

Entity kind → (the mall store holding its rig, the descriptor `kind` tag
that store’s documents carry). `environment` and `voice` are absent because
neither has a rig to declare asset sets on.

### *exception* an.ir.validate.UnregisteredInSceneError(findings, , where='')

Bases: [`UnregisteredKindError`](an.genres.registry.html.md#an.genres.registry.UnregisteredKindError)

A scene names kinds or renderers nothing registered: refused at load.

Raised by [`require_registered_kinds()`](#an.ir.validate.require_registered_kinds) — what `an.load(project)`
(and so `an render`) runs, so a typo’d `kind:` or `renderer:` can no
longer render silently wrong now that the schema holds them as `str`
(review-244 S2). `findings` keeps each one with its IR path.

### *class* an.ir.validate.ValidationContext(scene, report, stores, voices=None, characters=None, sounds=None, shot=None, index=None, memo=<factory>)

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

#### *property* path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The IR path of the current shot (`timeline/<index>`).

### *class* an.ir.validate.ValidationFinding(severity, ir_path, description)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single validation issue with a path into the IR.

### *class* an.ir.validate.ValidationReport(passed=True, findings=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of running one or more validators.

`passed` is True iff there are no error-severity findings.

### an.ir.validate.check_character_refs(ctx)

The cut-out genre’s missing-character warning. A WARNING: the compiler
falls back to the built-in placeholder rig and the scene still renders.
Deliberately not escalated — an asset-less project rendering placeholders
is a supported way to work.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.ir.validate.check_expression_actions(ctx)

The cut-out genre’s `expression` / `[emotion]` check.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.ir.validate.check_hidden_mouth_while_speaking(ctx)

The cut-out genre’s mouth-hidden-by-a-view warning.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.ir.validate.check_play_actions(ctx)

The cut-out genre’s `play` check (`_check_play_actions()`).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.ir.validate.check_turns(ctx)

The cut-out genre’s contradicted-turn warning (`_check_turns()`).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.ir.validate.check_view_continuity(ctx)

The cut-out genre’s view-across-a-cut warning (`_check_view_continuity()`).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

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

### an.ir.validate.validate_semantic(scene, , available_voices=None, available_characters=None, available_props=None, available_environments=None, available_sounds=None)

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

The checks are a REGISTRY ([`an.genres.registry.register_check()`](an.genres.registry.html.md#an.genres.registry.register_check)):
the core’s own register below, a genre’s when it is loaded (the cut-out
genre’s `play`, `expression`, turn and view checks), and they run in
stages — `scene`, then `shot` once per shot, then `finish` — each by
its `order`. An action or entity kind no loaded genre registered is one
error naming the genre that provides it; checks that would trip over it
skip that shot rather than crash.

* **Return type:**
  [`ValidationReport`](#an.ir.validate.ValidationReport)
