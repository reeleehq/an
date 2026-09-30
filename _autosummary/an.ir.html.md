# an.ir

Scene IR — the single source of truth for a scene.

Three layers, per the architectural spec:

- **Narrative** (`scene.md`) — human Markdown with structured fenced blocks.
- **Scene Graph** (`ir/scene.json`) — Pydantic-validated JSON. The SSOT.
- **Render Code** — generated per-backend, disposable.

This subpackage owns layer 2 (the Pydantic schema), the Markdown↔JSON sync that
keeps layer 1 and layer 2 in lock-step, the validators (schema + semantic),
the version migration registry, and the composition combinators that flatten
authoring-time DSL to canonical-form actions.

### Functions

| [`set_`](#an.ir.set_)(target, property, value, \*[, at])          | Discrete property set at time `at` (relative to its enclosing scope).       |
|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`tween`](#an.ir.tween)(target, property, to, duration, \*[, ...]) | Animate a property from `from_` (or its current value) to `to`.             |
| [`play`](#an.ir.play)(target, animation, \*[, duration, ...])     | Play a named animation of the target entity's descriptor (an#7).            |
| [`expression`](#an.ir.expression)(target[, preset, axes, ...])          | Hold a facial expression on an entity (an#98).                              |
| [`sequence`](#an.ir.sequence)(\*actions)                              | Run children one after the other.                                           |
| [`parallel`](#an.ir.parallel)(\*actions)                              | Run all children at once.                                                   |
| [`delay`](#an.ir.delay)(duration)                                  | An empty span that consumes time.                                           |
| [`loop`](#an.ir.loop)(action, count)                              | Repeat `action` `count` times.                                              |
| [`flatten`](#an.ir.flatten)(action, \*[, start, play_extent])        | Walk a composition tree, emitting leaf actions with absolute times.         |
| [`validate_schema`](#an.ir.validate_schema)(doc)                             | Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema. |
| [`validate_semantic`](#an.ir.validate_semantic)(scene, \*[, ...])              | Cross-field semantic checks.                                                |
| [`migrate`](#an.ir.migrate)(doc[, target_version, kind])             | Migrate a document to `target_version` (default: its kind's current).       |
| [`register_migration`](#an.ir.register_migration)(kind, from_version, ...)      | Decorator: register a migration for one kind in `MIGRATIONS`.               |
| [`register_kind`](#an.ir.register_kind)(kind)                              | Register a document kind.                                                   |
| [`kind_of`](#an.ir.kind_of)(doc, \*[, kind])                         | Resolve a document's kind, by explicit name or from its `kind` tag.         |
| [`markdown_to_ir`](#an.ir.markdown_to_ir)(md_text)                          | Parse the structured Markdown form of a scene into a SceneIR.               |
| [`ir_to_markdown`](#an.ir.ir_to_markdown)(scene)                            | Render a SceneIR back into the structured Markdown form.                    |
| [`sync`](#an.ir.sync)(project_dir)                                | Reconcile `scene.md` and `ir/scene.json` inside a project directory.        |

### Classes

| [`SceneIR`](#an.ir.SceneIR)(\*\*data)                                 | Top-level Scene IR document.                             |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------|
| [`Meta`](#an.ir.Meta)(\*\*data)                                    | Scene metadata.                                          |
| [`AssetRef`](#an.ir.AssetRef)(\*\*data)                                | Reference to an entry in a project store.                |
| [`Shot`](#an.ir.Shot)(\*\*data)                                    | A single rendered unit.                                  |
| [`Dialogue`](#an.ir.Dialogue)(\*\*data)                                | One line of spoken dialogue.                             |
| [`Camera`](#an.ir.Camera)(\*\*data)                                  | Camera state for a shot: a named move, or explicit keys. |
| [`Resolution`](#an.ir.Resolution)(\*\*data)                              | Pixel dimensions of the rendered output.                 |
| [`FlatAction`](#an.ir.FlatAction)(start, end, action)                    | A leaf action with its absolute start and end times.     |
| [`ValidationReport`](#an.ir.ValidationReport)([passed, findings])              | Result of running one or more validators.                |
| [`ValidationFinding`](#an.ir.ValidationFinding)(severity, ir_path, description) | A single validation issue with a path into the IR.       |
| [`DocumentKind`](#an.ir.DocumentKind)(name, version_field, ...)            | A schema-versioned document kind.                        |

### *class* an.ir.AssetRef(\*\*data)

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

### *class* an.ir.Camera(\*\*data)

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

### *class* an.ir.Dialogue(\*\*data)

Bases: `_IRModel`

One line of spoken dialogue.

`start` and `duration` are None until the audio pipeline runs (TTS
gives us a real duration); the pipeline stamps them then, deriving
`start` from the author’s `pause` / `at` ([`planned_start()`](#an.ir.Dialogue.planned_start)).

#### at *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where this line starts, in SHOT seconds, whatever came before it —
`(at 3.0)` in `scene.md`. `start` is what the audio pipeline
DERIVES from `at`/`pause` on every pass; these two are what the
author wrote (an#187).

#### direction *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

How the line is DELIVERED — cues such as `["excited"]` or
`["sighs", "annoyed"]`, `{excited}` in `scene.md` (an#209). A TTS
model that takes inline audio tags (ElevenLabs v3/v4) receives them as
`[excited] Hi!`; others ignore them. Never part of `text`, so
captions and lip-sync alignment never see a cue.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### pause *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Seconds of silence before this line, after the previous line ends (the
shot start, for the first line) — `(pause 1.5)` in `scene.md`.

#### planned_start(cursor)

Where this line starts, given the previous line ends at `cursor`.

The one rule the audio pipeline stamps into `start` and `an validate`
lays lines out by: `at` if set, else `cursor + pause`. A `start`
on a line never synthesized (no `audio_ref`) was authored — the
spelling of `at` before an#187 — and counts as one; a synthesized
line’s `start` is the pipeline’s own stamp, re-derived here.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> Dialogue(speaker="a", text="bye", pause=1.5).planned_start(0.8)
2.3
>>> Dialogue(speaker="a", text="bye", at=4.0).planned_start(0.8)
4.0
>>> Dialogue(speaker="a", text="bye").planned_start(0.8)
0.8
```

#### word_timings *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[WordTimingIR](an.ir.schema.html.md#an.ir.schema.WordTimingIR)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The provider’s word timings, line-relative; `None` when the provider
has none (offline, Rhubarb) or the line was stamped before an#96.

### *class* an.ir.DocumentKind(name, version_field, current_version)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A schema-versioned document kind.

`version_field` differs between kinds (`version` for the scene IR,
`schema_version` for the character descriptor), which is exactly why a
migrator cannot simply reach for `doc["version"]`.

#### version_of(doc)

The document’s declared version, defaulting to this build’s.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### *class* an.ir.FlatAction(start, end, action)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A leaf action with its absolute start and end times.

The flat-form list is the canonical representation passed to renderers
and verifiers. Composition nodes (sequence/parallel/delay/loop) do not
appear in the flat form — they’re collapsed into time offsets.

### *class* an.ir.Meta(\*\*data)

Bases: `_IRModel`

Scene metadata.

#### captions *: [Captions](an.ir.schema.html.md#an.ir.schema.Captions) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Captions from the dialogue’s word timings (`Captions`, an#175);
`None` — the default — is none, omitted from JSON like `style_pack`.

#### default_easing *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)] | [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The easing every authored `tween` that names none is drawn with
(an#166) — `"linear"` for a snappy South Park cadence, an overshooting
cubic-Bezier for a bouncy one. Precedence is \*\*tween > this > the
built-in `"ease_in_out"``** (:meth:`TweenAction.resolved_easing`).
``None` — the default and what every existing document has — changes
nothing, and is omitted from JSON like `style_pack`, so no committed
scene and no compiled document moves. It reaches authored tweens ONLY:
a motion preset writes its own easings, the camera’s named moves supply
theirs, and blinks, `play` clips and swap channels have none to
inherit. There is no per-shot override yet — style is a scene’s.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### sounds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SoundCue](an.ir.schema.html.md#an.ir.schema.SoundCue)]*

Sound cues in FILM time — a music bed, an ambience under every shot
(`SoundCue`). Empty, the default, is no sound layer at all.

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
leg and pupil colours, the environment presets’ sky and ground — and SVG
art whose descriptor tags its colours by role (`colour_roles`, written by
`an character new`). Untagged art is never inferred (inferring a role
from a pixel is what produced an#99’s wrong-tone lid); a rig a pack
cannot reach is WARNED about by name at compile.

### *class* an.ir.Resolution(\*\*data)

Bases: `_IRModel`

Pixel dimensions of the rendered output.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.SceneIR(\*\*data)

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

### *class* an.ir.Shot(\*\*data)

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

#### sounds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SoundCue](an.ir.schema.html.md#an.ir.schema.SoundCue)]*

Sound cues in SHOT-local time (`SoundCue`).

#### step_hz *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per-shot override of [`Meta.step_hz`](#an.ir.Meta.step_hz) (`None` = inherit).

#### transition *: [Transition](an.ir.schema.html.md#an.ir.schema.Transition) | [None](https://docs.python.org/3/builtins/constants.html#None)*

How this shot is entered (`Transition`); `None` is a hard cut.

### *class* an.ir.ValidationFinding(severity, ir_path, description)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single validation issue with a path into the IR.

### *class* an.ir.ValidationReport(passed=True, findings=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of running one or more validators.

`passed` is True iff there are no error-severity findings.

### an.ir.delay(duration)

An empty span that consumes time. Useful inside `sequence`.

* **Return type:**
  [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction)

### an.ir.expression(target, preset=None, , axes=None, intensity=1.0, duration=None, blend=0.15)

Hold a facial expression on an entity (an#98).

`duration=None` runs to the shot end and counts as **zero** in a
`sequence`, as a looping `play` does:

* **Return type:**
  [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction)

```pycon
>>> [f.start for f in flatten(sequence(expression("a", "happy"), delay(1.0), expression("a", "sad")))]
[0.0, 1.0]
>>> flatten(expression("a", "angry", duration=2.0))[0].end
2.0
```

### an.ir.flatten(action, , start=0.0, play_extent=None)

Walk a composition tree, emitting leaf actions with absolute times.

A `play` without `duration` advances a `sequence` by `play_extent`
(default `default_play_extent()`): its natural length, or zero for a
looping animation, which runs to the shot end.

Delays are absorbed into the timeline (they don’t appear in the output).
Loops are unrolled by simple repetition — appropriate at v0.1; the cutout
runtime can re-roll for efficiency later.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`FlatAction`](an.ir.compose.html.md#an.ir.compose.FlatAction)]

### an.ir.ir_to_markdown(scene)

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

### an.ir.kind_of(doc, , kind=None)

Resolve a document’s kind, by explicit name or from its `kind` tag.

Raises `ValueError` for an unregistered kind rather than guessing — a
document whose kind nobody declared has no known version field, so any
answer would be a fabrication.

* **Return type:**
  [`DocumentKind`](#an.ir.DocumentKind)

### an.ir.loop(action, count)

Repeat `action` `count` times.

* **Return type:**
  [`LoopAction`](an.ir.schema.html.md#an.ir.schema.LoopAction)

### an.ir.markdown_to_ir(md_text)

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

### an.ir.migrate(doc, target_version=None, , kind=None)

Migrate a document to `target_version` (default: its kind’s current).

Walks the migration registry one step at a time, considering only the
migrations registered for this document’s kind. Raises `ValueError` if no
path exists between the source and target versions.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> from an.base import SCHEMA_VERSION
>>> migrate({"version": SCHEMA_VERSION, "kind": "SceneIR"})["version"] == SCHEMA_VERSION
True
>>> migrate({"version": "0.1.0", "kind": "SceneIR"})["version"] == SCHEMA_VERSION
True
```

### an.ir.parallel(\*actions)

Run all children at once. Total duration = max of child durations.

* **Return type:**
  [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction)

### an.ir.play(target, animation, , duration=None, speed=1.0, loop=None, args=None)

Play a named animation of the target entity’s descriptor (an#7).

`duration=None` fills the animation’s natural length — or the shot’s
remainder for a looping one. In a `sequence` a play with no `duration`
occupies its **natural** length (a motion preset’s own length divided by
`speed`; a non-looping descriptor animation’s likewise), so the sibling
after it starts when it ends; a looping one runs to the shot end and
occupies **zero**:

* **Return type:**
  [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction)

```pycon
>>> [f.start for f in flatten(sequence(play("a", "idle_breath"), delay(1.0), play("a", "blink")))]
[0.0, 1.0]
>>> [f.start for f in flatten(sequence(play("a", "idle_breath", duration=2.0), play("a", "blink")))]
[0.0, 2.0]
>>> [f.start for f in flatten(sequence(play("a", "hop"), play("a", "nod")))]
[0.0, 0.5]
>>> [f.start for f in flatten(sequence(play("a", "hop", speed=2.0), play("a", "nod")))]
[0.0, 0.25]
```

(Bare `flatten` knows only the presets, by name; `an validate` and the
compiler pass the entity’s descriptor too — `an.characters.play.play_extent()`
— so a descriptor animation that shares a preset’s name is measured as the
descriptor’s.)

A name the descriptor does not declare falls back to a motion preset of
[`an.motion.PRESETS`](an.motion.html.md#an.motion.PRESETS), with `args` as its parameters (an#166):

```pycon
>>> play("charlie", "hop", args={"height": 30}).args
{'height': 30}
```

### an.ir.register_kind(kind)

Register a document kind. Returns it, so callers can bind the result.

* **Return type:**
  [`DocumentKind`](#an.ir.DocumentKind)

### an.ir.register_migration(kind, from_version, to_version)

Decorator: register a migration for one kind in `MIGRATIONS`.

Registered against the throwaway `Widget` kind from the module docstring,
deliberately: this registry is process-wide, so a doctest that registered a
step for a REAL kind would leave a second path through the ladder for every
test that ran afterwards — which is exactly what happened once, and it
presented as one unrelated test failing only in a full run (an#106).

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]], [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]]

```pycon
>>> @register_migration("Widget", "1.0", "2.0")
... def _bump(doc):
...     doc["widget_version"] = "2.0"
...     return doc
>>> ("Widget", "1.0", "2.0") in MIGRATIONS
True
```

### an.ir.sequence(\*actions)

Run children one after the other. Total duration = sum of child durations.

* **Return type:**
  [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction)

### an.ir.set_(target, property, value, , at=0.0)

Discrete property set at time `at` (relative to its enclosing scope).

* **Return type:**
  [`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction)

### an.ir.sync(project_dir)

Reconcile `scene.md` and `ir/scene.json` inside a project directory.

Strategy in v0.1: Markdown is the human SSOT; if both exist, the JSON is
regenerated from the Markdown unless mtimes show JSON is newer (which the
user is told never to do — but we warn instead of silently overwriting).

* **Return type:**
  `SyncResult`

### an.ir.tween(target, property, to, duration, , from_=None, easing=INHERIT)

Animate a property from `from_` (or its current value) to `to`.

`easing` left out inherits the scene’s `meta.default_easing` (else
`"ease_in_out"`); naming one — `"ease_in_out"` included — pins it.

* **Return type:**
  [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction)

```pycon
>>> "easing" in tween("a", "x", to=1.0, duration=1.0).model_fields_set
False
>>> tween("a", "x", to=1.0, duration=1.0, easing="linear").easing
'linear'
```

### an.ir.validate_schema(doc)

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

### an.ir.validate_semantic(scene, , available_voices=None, available_characters=None, available_props=None, available_environments=None, available_sounds=None)

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

| [`assets`](an.ir.assets.html.md#module-an.ir.assets)     | Where a third-party asset came from, and what its licence obliges.         |
|---------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`camera`](an.ir.camera.html.md#module-an.ir.camera)     | Camera semantics: the named moves, and the one resolver that expands them. |
| [`compose`](an.ir.compose.html.md#module-an.ir.compose)   | Composition combinators for authoring action trees, plus a flattener.      |
| [`schema`](an.ir.schema.html.md#module-an.ir.schema)     | Pydantic v2 models for the Scene IR.                                       |
| [`validate`](an.ir.validate.html.md#module-an.ir.validate) | Schema and semantic validation for SceneIR documents.                      |
