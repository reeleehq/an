# an

an — AI-driven structured animation.

Public API surface (curated). See `an.ir` for the Scene IR, `an.adapters`
for renderer plumbing, `an.audio` for TTS/lip-sync protocols, `an.verify`
for verification, and `an.stores` for the project mall.

```pycon
>>> import an
>>> 'SceneIR' in an.__all__
True
```

### Functions

| [`set_`](#an.set_)(target, property, value, \*[, at])          | Discrete property set at time `at` (relative to its enclosing scope).       |
|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`tween`](#an.tween)(target, property, to, duration, \*[, ...]) | Animate a property from `from_` (or its current value) to `to`.             |
| [`play`](#an.play)(target, animation, \*[, duration, ...])     | Play a named animation of the target entity's descriptor (an#7).            |
| [`sequence`](#an.sequence)(\*actions)                              | Run children one after the other.                                           |
| [`parallel`](#an.parallel)(\*actions)                              | Run all children at once.                                                   |
| [`delay`](#an.delay)(duration)                                  | An empty span that consumes time.                                           |
| [`loop`](#an.loop)(action, count)                              | Repeat `action` `count` times.                                              |
| [`flatten`](#an.flatten)(action, \*[, start])                     | Walk a composition tree, emitting leaf actions with absolute times.         |
| [`validate_schema`](#an.validate_schema)(doc)                             | Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema. |
| [`validate_semantic`](#an.validate_semantic)(scene, \*[, ...])              | Cross-field semantic checks.                                                |
| [`markdown_to_ir`](#an.markdown_to_ir)(md_text)                          | Parse the structured Markdown form of a scene into a SceneIR.               |
| [`ir_to_markdown`](#an.ir_to_markdown)(scene)                            | Render a SceneIR back into the structured Markdown form.                    |
| [`init`](#an.init)(project_dir, \*[, name, force])             | Create a fresh an project at `project_dir`.                                 |
| [`load`](#an.load)(project_dir)                                | Load an existing project.                                                   |
| [`save`](#an.save)(project)                                    | Persist a Project's current scene back to disk (md + json).                 |
| [`build_project_mall`](#an.build_project_mall)(project_dir, \*[, ensure])    | Build the standard project mall over `project_dir`.                         |
| [`check_requirements`](#an.check_requirements)()                             | Return a per-tool status dict.                                              |

### Classes

| [`SceneIR`](#an.SceneIR)(\*\*data)              | Top-level Scene IR document.                             |
|---------------------------------------------------------------------------------|----------------------------------------------------------|
| [`Meta`](#an.Meta)(\*\*data)                 | Scene metadata.                                          |
| [`AssetRef`](#an.AssetRef)(\*\*data)             | Reference to an entry in a project store.                |
| [`Shot`](#an.Shot)(\*\*data)                 | A single rendered unit.                                  |
| [`Dialogue`](#an.Dialogue)(\*\*data)             | One line of spoken dialogue.                             |
| [`Camera`](#an.Camera)(\*\*data)               | Camera state for a shot: a named move, or explicit keys. |
| [`Resolution`](#an.Resolution)(\*\*data)           | Pixel dimensions of the rendered output.                 |
| [`FlatAction`](#an.FlatAction)(start, end, action) | A leaf action with its absolute start and end times.     |
| [`Project`](#an.Project)(root, mall, scene)     | A loaded an project: directory + mall + current scene.   |

### *class* an.AssetRef(\*\*data)

Bases: `_IRModel`

Reference to an entry in a project store.

The IR never inlines large assets. Instead it references them by store
name + key, so the same character/voice/environment is reusable across
scenes. `overrides` lets a single shot tweak presentation without
forking the asset.

```pycon
>>> AssetRef(kind="character", id="maya", store="characters", ref="maya-v1").id
'maya'
```

#### kind *: [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)['character', 'environment', 'voice', 'prop']*

it selected nothing (the compiler
skipped it, nothing read the styles store) and the name belonged to the
renderer selector. Art direction arrives as a StylePack (#112).

* **Type:**
  `"style"` was retired in an#106

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### stage *: [StagePlacement](an.ir.schema.html.md#an.ir.schema.StagePlacement) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where on the stage this entity stands. `None` — the default and what
every existing document has — means “wherever the layout puts it”,
which for characters is the evenly-spaced row the compiler computes.

**Additive by construction, and hash-free by construction**: the
contract hashes the COMPILED document, and an `AssetRef` never reaches
it. So this field can grow without retiring a single ledger row.

### *class* an.Camera(\*\*data)

Bases: `_IRModel`

Camera state for a shot: a named move, or explicit keys.

```pycon
>>> Camera(move="push_in").move
'push_in'
>>> Camera(keys=[CameraKey(at=0.0), CameraKey(at=2.0, x=-200.0)]).keys[1].x
-200.0
```

**One code path, two front doors** — the shape the dialogue `[emotion]`
sugar already uses. A named `move` desugars to a key list; `keys` is that
list written out. Setting both raises, because a scene that says two
things about the same camera has no reading that is not a guess.

`keys` defaults to `None`, not `[]`, and that too is load-bearing: the
markdown writer dumps the camera with `exclude_none=True`, which KEEPS
empty lists — an empty default would write `keys: []` into every camera
block it regenerates.

`position`, `target` and `focal_length` were removed in an#109. They were
written into every `scene.md` this package ever generated and read by
nothing; a registered migration drops them.

#### keys *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[CameraKey](an.ir.schema.html.md#an.ir.schema.CameraKey)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The explicit door. `None` = use `move`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### move *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

A named preset — sugar for `keys`. The cutout renderer’s vocabulary is
`an.adapters.cutout.compile.CAMERA_MOVES`; validate and the compiler are
pinned to the same table by test, because a move that validates and then
raises is the failure `_check_renderable` exists to prevent.

### *class* an.Dialogue(\*\*data)

Bases: `_IRModel`

One line of spoken dialogue.

`timing` is None until the audio pipeline runs (TTS gives us a real
duration); the orchestrator fills it in then.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### word_timings *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[WordTimingIR](an.ir.schema.html.md#an.ir.schema.WordTimingIR)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The provider’s word timings, line-relative; `None` when the provider
has none (offline, Rhubarb) or the line was stamped before an#96.

### *class* an.FlatAction(start, end, action)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A leaf action with its absolute start and end times.

The flat-form list is the canonical representation passed to renderers
and verifiers. Composition nodes (sequence/parallel/delay/loop) do not
appear in the flat form — they’re collapsed into time offsets.

### *class* an.Meta(\*\*data)

Bases: `_IRModel`

Scene metadata.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### step_hz *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Stepped timing for AUTHORED TWEENS, in pose updates per second; `None`
(the default) leaves every tween smooth. At 30 fps, `15` is “on twos”
and `10` “on threes” — the character-animation practice Spider-Verse
made famous (characters on twos, simulation on ones). The camera is
exempt by construction, as are swap channels (already stepped by
format), compiled blinks and `play` clips: only `tween` curves are
resampled — sample-and-hold of the eased curve on a SHOT-wide grid
(every tween in a shot shares it; it restarts at a cut), not a retiming
into holds and fast transitions. A tween’s own START and END are always
pose changes too, so a tween that begins or ends off-grid changes pose
on that frame as well as on the grid (a `set` at an off-grid `at`
likewise lands where it was authored). A shot’s own `step_hz`
overrides this. Must be positive (schema) and `<= fps` (validate +
compile), an#89.

#### style_pack *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The `StylePack` in the project’s `styles` store this scene is drawn
under, by key. `None` — the default and what every existing document
has — leaves every colour exactly where it is, which is why adding this
moved no corpus hash (an#112).

A pack changes what the COMPILER decides: the character palette, the
leg and pupil colours, the environment presets’ sky and ground. It does
NOT recolour SVG art — that would need role tagging the descriptor does
not have, and inferring a role from a pixel is what produced an#99’s
wrong-tone lid. A rig whose art a pack cannot reach is WARNED about by
name at compile.

### *class* an.Project(root, mall, scene)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A loaded an project: directory + mall + current scene.

### *class* an.Resolution(\*\*data)

Bases: `_IRModel`

Pixel dimensions of the rendered output.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.SceneIR(\*\*data)

Bases: `_IRModel`

Top-level Scene IR document. The SSOT.

A document is portable, diffable, and renderer-agnostic. Persisted as JSON
at `ir/scene.json` inside an an project.

```pycon
>>> from an.base import SCHEMA_VERSION
>>> doc = SceneIR(meta=Meta(title="Hello"))
>>> doc.version == SCHEMA_VERSION
True
>>> round_tripped = SceneIR.model_validate_json(doc.model_dump_json())
>>> round_tripped.meta.title
'Hello'
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.Shot(\*\*data)

Bases: `_IRModel`

A single rendered unit. A scene is a sequence of shots.

A shot’s `renderer` selects the backend that draws it. Every renderer must accept the
same Shot fields; renderer-specific options go under `options`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### renderer *: [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)['cutout', 'manim', 'motion_graphics', 'whiteboard']*

Which RENDERER draws this shot — not art direction. The field was
called `style` until an#106, colliding with the styles store (which
holds art direction) and with `AssetRef(kind="style")`; one word for two
meanings is how a scene came to declare a “style” that selected a
renderer while the thing that actually styles it went unread.

#### step_hz *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per-shot override of [`Meta.step_hz`](#an.Meta.step_hz) (`None` = inherit).

### an.build_project_mall(project_dir, , ensure=False, \*\*overrides)

Build the standard project mall over `project_dir`.

Pass `ensure=True` to create the per-store directories on disk if they
don’t exist. Pass keyword overrides to swap in alternate stores (e.g. an
in-memory `dict` for tests).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`MutableMapping`](https://docs.python.org/3/library/typing.html#typing.MutableMapping)]

### an.check_requirements()

Return a per-tool status dict.

The CLI subcommand `an check` pretty-prints this. Programmatic callers
can inspect the dict directly.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### an.delay(duration)

An empty span that consumes time. Useful inside `sequence`.

* **Return type:**
  [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction)

### an.flatten(action, , start=0.0)

Walk a composition tree, emitting leaf actions with absolute times.

Delays are absorbed into the timeline (they don’t appear in the output).
Loops are unrolled by simple repetition — appropriate at v0.1; the cutout
runtime can re-roll for efficiency later.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`FlatAction`](an.ir.compose.html.md#an.ir.compose.FlatAction)]

### an.init(project_dir, , name=None, force=False)

Create a fresh an project at `project_dir`.

Idempotent unless the directory already contains a non-empty `scene.md`;
pass `force=True` to overwrite. Returns the absolute project root.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.ir_to_markdown(scene)

Render a SceneIR back into the structured Markdown form.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> from an.ir.schema import SceneIR, Meta, Shot
>>> scene = SceneIR(meta=Meta(title="Demo", duration=5.0),
...                 timeline=[Shot(id="s1", renderer="cutout", duration=5.0)])
>>> md = ir_to_markdown(scene)
>>> "# Demo" in md
True
>>> "## Shot s1 (cutout)" in md
True
```

### an.load(project_dir)

Load an existing project. Reconciles scene.md / ir/scene.json first.

* **Return type:**
  [`Project`](an.project.html.md#an.project.Project)

### an.loop(action, count)

Repeat `action` `count` times.

* **Return type:**
  [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)

### an.markdown_to_ir(md_text)

Parse the structured Markdown form of a scene into a SceneIR.

* **Return type:**
  [`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR)

```pycon
>>> md = '''# Demo
...
... ```yaml meta
... title: Demo
... duration: 5
... ```
...
... ## Shot s1 (cutout)
...
... ```yaml shot
... duration: 5
... ```
...
... ```dialogue
... charlie: hi
... ```
... '''
>>> scene = markdown_to_ir(md)
>>> scene.meta.title
'Demo'
>>> scene.timeline[0].id
's1'
>>> scene.timeline[0].dialogue[0].text
'hi'
```

### an.parallel(\*actions)

Run all children at once. Total duration = max of child durations.

* **Return type:**
  [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction)

### an.play(target, animation, , duration=None, speed=1.0, loop=None)

Play a named animation of the target entity’s descriptor (an#7).

`duration=None` fills the animation’s natural length — or the shot’s
remainder for a looping one — but counts as **zero** in a `sequence`,
so a sibling placed after it starts at the same instant:

* **Return type:**
  [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction)

```pycon
>>> [f.start for f in flatten(sequence(play("a", "idle_breath"), delay(1.0), play("a", "blink")))]
[0.0, 1.0]
>>> [f.start for f in flatten(sequence(play("a", "idle_breath", duration=2.0), play("a", "blink")))]
[0.0, 2.0]
```

### an.save(project)

Persist a Project’s current scene back to disk (md + json).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.sequence(\*actions)

Run children one after the other. Total duration = sum of child durations.

* **Return type:**
  [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction)

### an.set_(target, property, value, , at=0.0)

Discrete property set at time `at` (relative to its enclosing scope).

* **Return type:**
  [`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction)

### an.tween(target, property, to, duration, , from_=None, easing='ease_in_out')

Animate a property from `from_` (or its current value) to `to`.

* **Return type:**
  [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction)

### an.validate_schema(doc)

Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema.

* **Return type:**
  [`ValidationReport`](an.ir.validate.html.md#an.ir.validate.ValidationReport)

```pycon
>>> validate_schema({"meta": {"title": "x"}, "timeline": []}).passed
True
>>> r = validate_schema({"meta": {"title": "x"}, "timeline": [{"id": "s", "duration": "not-a-number"}]})
>>> r.passed
False
```

### an.validate_semantic(scene, , available_voices=None, available_characters=None, available_props=None, available_environments=None)

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

* **Return type:**
  [`ValidationReport`](an.ir.validate.html.md#an.ir.validate.ValidationReport)

### Modules

| [`adapters`](an.adapters.html.md#module-an.adapters)         | Renderer adapters — facades over backends (cutout, Manim, Remotion, whiteboard).       |
|--------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| [`audio`](an.audio.html.md#module-an.audio)               | Audio pipeline — TTS and lip-sync providers + orchestration.                           |
| [`base`](an.base.html.md#module-an.base)                 | Core types, constants, and re-exports for an.                                          |
| [`bench`](an.bench.html.md#module-an.bench)               | `an bench` — render a fixed corpus, compute a metrics panel, write one ledger row.     |
| [`characters`](an.characters.html.md#module-an.characters)     | Character art system: Spine-shaped descriptor + SVG sidecars.                          |
| [`conftest`](an.conftest.html.md#module-an.conftest)         | Collection rules for the package's own doctests.                                       |
| [`credits`](an.credits.html.md#module-an.credits)           | What a rendered video owes, and to whom.                                               |
| [`data`](an.data.html.md#module-an.data)                 | Bundled non-Python resources (cutout JS runtime, etc.).                                |
| [`determinism`](an.determinism.html.md#module-an.determinism)   | The determinism perimeter: what must stay true for a render to be reproducible.        |
| [`environments`](an.environments.html.md#module-an.environments) | Environments: a stage made of planes, at declared depths.                              |
| [`expression`](an.expression.html.md#module-an.expression)     | Facial expression for the cutout face (an#98, epic #9 Wave 6).                         |
| [`frame_clock`](an.frame_clock.html.md#module-an.frame_clock)   | The frame clock: WHEN each output frame samples scene time.                            |
| [`impacts`](an.impacts.html.md#module-an.impacts)           | Synthetic impact clips with exact ground truth, for scoring sub-frame timing.          |
| [`ir`](an.ir.html.md#module-an.ir)                     | Scene IR — the single source of truth for a scene.                                     |
| [`iterate`](an.iterate.html.md#module-an.iterate)           | Iterative edit loop — free-text instruction → IR patch via Claude → re-render.         |
| [`live_api`](an.live_api.html.md#module-an.live_api)         | The one switch that says "yes, this run may spend money".                              |
| [`orchestrate`](an.orchestrate.html.md#module-an.orchestrate)   | Orchestrator: validate → audio → render → verify.                                      |
| [`paths`](an.paths.html.md#module-an.paths)               | Stroked paths: routes, invasion arrows, borders, timelines, connectors.                |
| [`preview`](an.preview.html.md#module-an.preview)           | Live preview server: render a project's current scene in a browser, reloading on edit. |
| [`project`](an.project.html.md#module-an.project)           | Project init/load/save — the on-disk anatomy of an an project.                         |
| [`props`](an.props.html.md#module-an.props)               | Props: a rig whose art is not a person.                                                |
| [`render`](an.render.html.md#module-an.render)             | Project-level rendering: per-shot mp4 → final composited mp4 via ffmpeg concat.        |
| [`stores`](an.stores.html.md#module-an.stores)             | Project mall: a dict of dol-backed `MutableMapping` stores.                            |
| [`styles`](an.styles.html.md#module-an.styles)             | StylePack: art direction as a document, and the first reader the styles store has had. |
| [`tools`](an.tools.html.md#module-an.tools)               | User-facing utility functions, plus the SSOT list for CLI dispatch.                    |
| [`util`](an.util.html.md#module-an.util)                 | Internal helpers: file I/O, hashing, time arithmetic, light path utilities.            |
| [`verify`](an.verify.html.md#module-an.verify)             | Verification protocol — same interface for human, lint, vision-LM, MoVer.              |
