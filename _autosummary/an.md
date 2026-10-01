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
| [`stagger`](#an.stagger)(lag, \*actions)                          | Start each action `lag` seconds after the previous one STARTS.              |
| [`delay`](#an.delay)(duration)                                  | An empty span that consumes time.                                           |
| [`loop`](#an.loop)(action, count)                              | Repeat `action` `count` times.                                              |
| [`flatten`](#an.flatten)(action, \*[, start, play_extent])        | Walk a composition tree, emitting leaf actions with absolute times.         |
| [`validate_schema`](#an.validate_schema)(doc)                             | Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema. |
| [`validate_semantic`](#an.validate_semantic)(scene, \*[, ...])              | Cross-field semantic checks.                                                |
| [`markdown_to_ir`](#an.markdown_to_ir)(md_text)                          | Parse the structured Markdown form of a scene into a SceneIR.               |
| [`ir_to_markdown`](#an.ir_to_markdown)(scene)                            | Render a SceneIR back into the structured Markdown form.                    |
| [`init`](#an.init)(project_dir, \*[, name, force])             | Create a fresh an project at `project_dir`.                                 |
| [`load`](#an.load)(project_dir, \*[, check_kinds])             | Load an existing project.                                                   |
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

#### kind *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

it selected nothing (the compiler
skipped it, nothing read the styles store) and the name belonged to the
renderer selector. Art direction arrives as a StylePack (#112).

A `str` in the schema, not a `Literal` (ADR 0001 decision 2): the
values are the REGISTERED entity kinds ([`an.genres`](an.genres.md#module-an.genres)) — the core’s
`environment`, `prop` and `voice`, a genre’s `character` — and
`an validate` checks it against that registry, naming the genre that
provides an unregistered one.

* **Type:**
  `"style"` was retired in an#106

#### library *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The asset-library version this entry was checked out from (ADR 0005
decision 8): `"[<library>:]<asset_id>@<version>"`, e.g.
`"cutan:character.alice-reiniger@v003"` (grammar:
[`an.library.ids.parse_ref()`](an.library.ids.md#an.library.ids.parse_ref), a pinned version required: `vNNN` or
`sha256:<prefix>`, never `latest`). `None` — the
default, and every document written before the library existed — means
the asset is the project’s own. Today the strategy is check-out, so
`ref` still names the project-store key the compiler reads and this
field is the pin beside it; live reference resolves it instead, later.

Additive and omit-when-unset, like `stage`: an unset `library`
leaves no trace in a dump, so no stored scene changes and no schema
version moves.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### stage *: [StagePlacement](an.ir.schema.md#an.ir.schema.StagePlacement) | [None](https://docs.python.org/3/builtins/constants.html#None)*

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

#### keys *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[CameraKey](an.ir.schema.md#an.ir.schema.CameraKey)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

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

`start` and `duration` are None until the audio pipeline runs (TTS
gives us a real duration); the pipeline stamps them then, deriving
`start` from the author’s `pause` / `at` ([`planned_start()`](#an.Dialogue.planned_start)).

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

#### word_timings *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[WordTimingIR](an.ir.schema.md#an.ir.schema.WordTimingIR)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

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

#### captions *: [Captions](an.ir.schema.md#an.ir.schema.Captions) | [None](https://docs.python.org/3/builtins/constants.html#None)*

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

#### default_renderer *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

a registered renderer’s name.

* **Type:**
  Like [`Shot.renderer`](#an.Shot.renderer)

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### sounds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SoundCue](an.ir.schema.md#an.ir.schema.SoundCue)]*

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

#### renderer *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Which RENDERER draws this shot — not art direction. The field was
called `style` until an#106, colliding with the styles store (which
holds art direction) and with `AssetRef(kind="style")`; one word for two
meanings is how a scene came to declare a “style” that selected a
renderer while the thing that actually styles it went unread.
A `str` in the schema (ADR 0001 decision 2): any name a renderer
registered (`an.adapters.register_renderer`), checked by `an
validate`. `cutout` stays the persisted default (decision 9).

#### sounds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SoundCue](an.ir.schema.md#an.ir.schema.SoundCue)]*

Sound cues in SHOT-local time (`SoundCue`).

#### step_hz *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per-shot override of [`Meta.step_hz`](#an.Meta.step_hz) (`None` = inherit).

#### transition *: [Transition](an.ir.schema.md#an.ir.schema.Transition) | [None](https://docs.python.org/3/builtins/constants.html#None)*

How this shot is entered (`Transition`); `None` is a hard cut.

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
  [`DelayAction`](an.ir.schema.md#an.ir.schema.DelayAction)

### an.flatten(action, , start=0.0, play_extent=None)

Walk a composition tree, emitting leaf actions with absolute times.

A `play` without `duration` advances a `sequence` by `play_extent`
(default `default_play_extent()`): its natural length, or zero for a
looping animation, which runs to the shot end.

Delays are absorbed into the timeline (they don’t appear in the output).
Loops are unrolled by simple repetition — appropriate at v0.1; the cutout
runtime can re-roll for efficiency later.

Every node is dispatched through its registered kind
([`ActionKind`](an.genres.md#an.genres.ActionKind)), so a genre’s kind flattens without an
edit here; a node whose kind nobody registered raises, naming the genre
that provides it, and an `ExtensionAction` read before its genre
loaded is validated by the registered model on the way through.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`FlatAction`](an.ir.compose.md#an.ir.compose.FlatAction)]

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

### an.load(project_dir, , check_kinds=True)

Load an existing project. Reconciles scene.md / ir/scene.json first.

Registers the installed genres first ([`an.genres.load()`](an.genres.md#an.genres.load), ADR 0001
decision 3: discovery is explicit, and loading a project is one of the
places it happens), so the scene’s genre kinds — the cut-out genre’s
`play`, `expression` and `character` — read as their own models.

Then refuses a scene that names an action kind, entity kind or renderer
nothing registered ([`an.ir.validate.require_registered_kinds()`](an.ir.validate.md#an.ir.validate.require_registered_kinds)): the
schema holds those as `str` (ADR 0001 decision 2), so without this a
typo’d `kind: enviroment` would load and render silently without its
backdrop. `check_kinds=False` is for `an validate`, which reports them
as findings instead.

* **Return type:**
  [`Project`](an.project.md#an.project.Project)

### an.loop(action, count)

Repeat `action` `count` times.

* **Return type:**
  [`LoopAction`](an.ir.schema.md#an.ir.schema.LoopAction)

### an.markdown_to_ir(md_text)

Parse the structured Markdown form of a scene into a SceneIR.

* **Return type:**
  [`SceneIR`](an.ir.schema.md#an.ir.schema.SceneIR)

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
  [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction)

### an.play(target, animation, , duration=None, speed=1.0, loop=None, args=None)

Play a named animation of the target entity’s descriptor (an#7).

`duration=None` fills the animation’s natural length — or the shot’s
remainder for a looping one. In a `sequence` a play with no `duration`
occupies its **natural** length (a motion preset’s own length divided by
`speed`; a non-looping descriptor animation’s likewise), so the sibling
after it starts when it ends; a looping one runs to the shot end and
occupies **zero**:

* **Return type:**
  [`PlayAction`](an.ir.schema.md#an.ir.schema.PlayAction)

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
[`an.motion.PRESETS`](an.motion.md#an.motion.PRESETS), with `args` as its parameters (an#166):

```pycon
>>> play("charlie", "hop", args={"height": 30}).args
{'height': 30}
```

### an.save(project)

Persist a Project’s current scene back to disk (md + json).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.sequence(\*actions)

Run children one after the other. Total duration = sum of child durations.

* **Return type:**
  [`SequenceAction`](an.ir.schema.md#an.ir.schema.SequenceAction)

### an.set_(target, property, value, , at=0.0)

Discrete property set at time `at` (relative to its enclosing scope).

* **Return type:**
  [`SetAction`](an.ir.schema.md#an.ir.schema.SetAction)

### an.stagger(lag, \*actions)

Start each action `lag` seconds after the previous one STARTS.

The **stagger** (Manim’s `LaggedStart`, `previz`’s compose, a crowd
entering one by one): the children run in parallel, the `i`-th delayed
by `i * lag`. It is authoring sugar, not a new kind — it builds the
`parallel` of `sequence(delay(i * lag), action)` it means, so the
scene document, `scene.md` and every renderer see only core kinds.
Total duration: the latest child’s end. `scene.md` holds it verbatim (a
`kind: parallel` entry), so it round-trips. (`an.text.reveal_units` —
`an.text.stagger` before an#241 — is the text-block preset: a LIST of
per-unit actions with holds, not a combinator.)

* **Return type:**
  [`ParallelAction`](an.ir.schema.md#an.ir.schema.ParallelAction)

```pycon
>>> flat = flatten(stagger(0.25, tween("a", "x", to=1.0, duration=1.0),
...                              tween("b", "x", to=1.0, duration=1.0),
...                              tween("c", "x", to=1.0, duration=1.0)))
>>> [(f.action.target, f.start, f.end) for f in flat]
[('a', 0.0, 1.0), ('b', 0.25, 1.25), ('c', 0.5, 1.5)]
>>> duration_of(stagger(0.5, delay(1.0), delay(1.0)))
1.5
>>> stagger(0.1).children
[]
>>> stagger(-1.0, delay(1.0))
Traceback (most recent call last):
...
ValueError: stagger lag must be >= 0, got -1.0
```

### an.tween(target, property, to, duration, , from_=None, easing=INHERIT)

Animate a property from `from_` (or its current value) to `to`.

`easing` left out inherits the scene’s `meta.default_easing` (else
`"ease_in_out"`); naming one — `"ease_in_out"` included — pins it.

* **Return type:**
  [`TweenAction`](an.ir.schema.md#an.ir.schema.TweenAction)

```pycon
>>> "easing" in tween("a", "x", to=1.0, duration=1.0).model_fields_set
False
>>> tween("a", "x", to=1.0, duration=1.0, easing="linear").easing
'linear'
```

### an.validate_schema(doc)

Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema.

* **Return type:**
  [`ValidationReport`](an.ir.validate.md#an.ir.validate.ValidationReport)

```pycon
>>> validate_schema({"meta": {"title": "x"}, "timeline": []}).passed
True
>>> r = validate_schema({"meta": {"title": "x"}, "timeline": [{"id": "s", "duration": "not-a-number"}]})
>>> r.passed
False
```

### an.validate_semantic(scene, , available_voices=None, available_characters=None, available_props=None, available_environments=None, available_sounds=None, available_library_lock=None)

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

`available_library_lock` is the project’s asset-library lockfile
(`mall["library_lock"]`): with it, every scene `library:` pin is checked
against the lockfile (`warning` on disagreement) and every pinned
check-out against its library version (`info` when it has been edited).

The checks are a REGISTRY ([`an.genres.registry.register_check()`](an.genres.registry.md#an.genres.registry.register_check)):
the core’s own register below, a genre’s when it is loaded (the cut-out
genre’s `play`, `expression`, turn and view checks), and they run in
stages — `scene`, then `shot` once per shot, then `finish` — each by
its `order`. An action or entity kind no loaded genre registered is one
error naming the genre that provides it; checks that would trip over it
skip that shot rather than crash.

* **Return type:**
  [`ValidationReport`](an.ir.validate.md#an.ir.validate.ValidationReport)

### Modules

| [`adapters`](an.adapters.md#module-an.adapters)         | Renderer adapters — facades over backends (cutout, Manim, Remotion, whiteboard).                   |
|--------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| [`assemble`](an.assemble.md#module-an.assemble)         | Film assembly: rendered shots → one film, with transitions and a sound layer.                      |
| [`audio`](an.audio.md#module-an.audio)               | Audio pipeline — TTS and lip-sync providers + orchestration.                                       |
| [`base`](an.base.md#module-an.base)                 | Core types, constants, and re-exports for an.                                                      |
| [`bench`](an.bench.md#module-an.bench)               | `an bench` — render a fixed corpus, compute a metrics panel, write one ledger row.                 |
| [`build`](an.build.md#module-an.build)               | Incremental re-processing: content-addressed build stages (ADR 0004).                              |
| [`capabilities`](an.capabilities.md#module-an.capabilities) | Capabilities: what an asset, an engine or the environment affords, and the one matcher.            |
| [`captions`](an.captions.md#module-an.captions)         | Captions from the word timings the audio pipeline already computes (an#175).                       |
| [`characters`](an.characters.md#module-an.characters)     | Character art system: Spine-shaped descriptor + SVG sidecars.                                      |
| [`conftest`](an.conftest.md#module-an.conftest)         | Collection rules for the package's own doctests.                                                   |
| [`credits`](an.credits.md#module-an.credits)           | What a rendered video owes, and to whom.                                                           |
| [`data`](an.data.md#module-an.data)                 | Bundled non-Python resources (cutout JS runtime, etc.).                                            |
| [`determinism`](an.determinism.md#module-an.determinism)   | The determinism perimeter: what must stay true for a render to be reproducible.                    |
| [`engines`](an.engines.md#module-an.engines)           | Engines: seekable things the core drives frame by frame, and the renderer that drives them.        |
| [`environments`](an.environments.md#module-an.environments) | Environments: a stage made of planes, at declared depths.                                          |
| [`expression`](an.expression.md#module-an.expression)     | Facial expression for the cutout face (an#98, epic #9 Wave 6).                                     |
| [`frame_clock`](an.frame_clock.md#module-an.frame_clock)   | The frame clock: WHEN each output frame samples scene time.                                        |
| [`genres`](an.genres.md#module-an.genres)             | Genres: what a kind of animation adds to the core, declared as one object.                         |
| [`impacts`](an.impacts.md#module-an.impacts)           | Synthetic impact clips with exact ground truth, for scoring sub-frame timing.                      |
| [`ir`](an.ir.md#module-an.ir)                     | Scene IR — the single source of truth for a scene.                                                 |
| [`iterate`](an.iterate.md#module-an.iterate)           | Iterative edit loop — free-text instruction → IR patch via Claude → re-render.                     |
| [`library`](an.library.md#module-an.library)           | The asset library: reusable assets that outlive their videos (ADR 0005).                           |
| [`live_api`](an.live_api.md#module-an.live_api)         | The one switch that says "yes, this run may spend money".                                          |
| [`mcp`](an.mcp.md#module-an.mcp)                   | The `an` MCP server: a curated, generated surface over the vocabulary and the capability registry. |
| [`measurements`](an.measurements.md#module-an.measurements) | Measured durations: shots whose renderer, not their author, decides their length.                  |
| [`media`](an.media.md#module-an.media)               | Frames to deliverables, engine-independent: the frame stage's resolves and the sinks.              |
| [`motion`](an.motion.md#module-an.motion)             | Motion presets: a named vocabulary of cut-out moves, as authoring macros.                          |
| [`orchestrate`](an.orchestrate.md#module-an.orchestrate)   | Orchestrator: validate → audio → render → verify.                                                  |
| [`paths`](an.paths.md#module-an.paths)               | Stroked paths: routes, invasion arrows, borders, timelines, connectors.                            |
| [`preview`](an.preview.md#module-an.preview)           | Live preview server: render a project's current scene in a browser, reloading on edit.             |
| [`project`](an.project.md#module-an.project)           | Project init/load/save — the on-disk anatomy of an an project.                                     |
| [`props`](an.props.md#module-an.props)               | Props: a rig whose art is not a person.                                                            |
| [`raster`](an.raster.md#module-an.raster)             | Raster art: what a PNG, JPEG or WebP is, read from its header (an#211).                            |
| [`render`](an.render.md#module-an.render)             | Project-level rendering: per-shot mp4 → final composited mp4 via ffmpeg concat.                    |
| [`semantic`](an.semantic.md#module-an.semantic)         | The semantic layer: one versioned vocabulary registry, methods, aspects and the matcher.           |
| [`sounds`](an.sounds.md#module-an.sounds)             | Sound assets: what the sound layer plays, where it came from, and a synthesizer.                   |
| [`stores`](an.stores.md#module-an.stores)             | Project mall: a dict of dol-backed `MutableMapping` stores.                                        |
| [`styles`](an.styles.md#module-an.styles)             | StylePack: art direction as a document, and the first reader the styles store has had.             |
| [`text`](an.text.md#module-an.text)                 | Words on screen: title cards, labels, and text you can animate word by word.                       |
| [`timing`](an.timing.md#module-an.timing)             | The timing kernel: what is on screen at time `t`, as a pure function.                              |
| [`tools`](an.tools.md#module-an.tools)               | User-facing utility functions, plus the SSOT list for CLI dispatch.                                |
| [`util`](an.util.md#module-an.util)                 | Internal helpers: file I/O, hashing, time arithmetic, light path utilities.                        |
| [`verify`](an.verify.md#module-an.verify)             | Verification protocol — same interface for human, lint, vision-LM, MoVer.                          |
