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

| [`lower_world`](#an.ir.lower_world)(scene, \*, extents[, ...])             | The scene with every framed shot's placements derived from the world.                                                                                                                              |
|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`set_`](#an.ir.set_)(target, property, value, \*[, at])            | Discrete property set at time `at` (relative to its enclosing scope).                                                                                                                              |
| [`tween`](#an.ir.tween)(target, property, to, duration, \*[, ...])   | Animate a property from `from_` (or its current value) to `to`.                                                                                                                                    |
| [`sequence`](#an.ir.sequence)(\*actions)                                | Run children one after the other.                                                                                                                                                                  |
| [`parallel`](#an.ir.parallel)(\*actions)                                | Run all children at once.                                                                                                                                                                          |
| [`stagger`](#an.ir.stagger)(lag, \*actions)                            | Start each action `lag` seconds after the previous one STARTS.                                                                                                                                     |
| [`crowd`](#an.ir.crowd)(id, \*, ref, count[, kind, store, ...])      | `count` entities of one asset (`kind`/`store`/`ref`) placed in `area`.                                                                                                                             |
| [`fan_out`](#an.ir.fan_out)(action, members, \*[, crowd_id])           | A copy of `action` per member, its targets moved from the crowd to the member.                                                                                                                     |
| [`delay`](#an.ir.delay)(duration)                                    | An empty span that consumes time.                                                                                                                                                                  |
| [`loop`](#an.ir.loop)(action, count)                                | Repeat `action` `count` times.                                                                                                                                                                     |
| [`flatten`](#an.ir.flatten)(action, \*[, start, play_extent])          | Walk a composition tree, emitting leaf actions with absolute times.                                                                                                                                |
| [`validate_schema`](#an.ir.validate_schema)(doc)                               | Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema.                                                                                                                        |
| [`validate_semantic`](#an.ir.validate_semantic)(scene, \*[, ...])                | Cross-field semantic checks.                                                                                                                                                                       |
| [`migrate`](#an.ir.migrate)(doc[, target_version, kind])               | Migrate a document to `target_version` (default: its kind's current).                                                                                                                              |
| [`register_migration`](#an.ir.register_migration)(kind, from_version, ...)        | Decorator: register a migration for one kind in `MIGRATIONS`.                                                                                                                                      |
| [`register_kind`](#an.ir.register_kind)(kind)                                | Register a document kind.                                                                                                                                                                          |
| [`kind_of`](#an.ir.kind_of)(doc, \*[, kind])                           | Resolve a document's kind, by explicit name or from its `kind` tag.                                                                                                                                |
| [`markdown_to_ir`](#an.ir.markdown_to_ir)(md_text)                            | Parse the structured Markdown form of a scene into a SceneIR.                                                                                                                                      |
| [`ir_to_markdown`](#an.ir.ir_to_markdown)(scene)                              | Render a SceneIR back into the structured Markdown form.                                                                                                                                           |
| [`sync`](#an.ir.sync)(project_dir[, scene_file])                    | Reconcile a scene's markdown and JSON inside a project directory (`scene.md` and `ir/scene.json`, or the pair of the `scene_file` named; a named scene that is not there raises `SceneFileError`). |
| [`pin`](#an.ir.pin)(point, to, \*[, duration])                     | `point` held at `to`.                                                                                                                                                                              |
| [`pull`](#an.ir.pull)(point, to, \*[, over, give])                  | `point` drawn toward `to` (a point, a body point, or a path).                                                                                                                                      |
| [`join`](#an.ir.join)(joint, \*[, at])                              | Rejoin the joint named `joint` at `at`.                                                                                                                                                            |
| [`unjoin`](#an.ir.unjoin)(joint, \*[, at])                            | Let go of the joint named `joint` at `at`.                                                                                                                                                         |
| [`grasp`](#an.ir.grasp)(by, item, \*[, reach, retract, lean, align]) | `by` takes `item`.                                                                                                                                                                                 |
| [`reframe`](#an.ir.reframe)(target, \*, to[, at, keep, snap, ...])     | `target` changes to frame `to` at `at` seconds into the action.                                                                                                                                    |
| [`place`](#an.ir.place)(item, onto, \*[, by, rotation, reach, ...])  | The hand holding `item` puts it `onto` a target.                                                                                                                                                   |
| [`release`](#an.ir.release)(item, \*[, at, onto, arc, rotation])       | Let `item` go at `at` (a drop, or a toss `onto: ground@x`).                                                                                                                                        |
| [`handover`](#an.ir.handover)(item, to, \*[, by, meet, reach, ...])     | Give `item` to `to`.                                                                                                                                                                               |
| [`swap`](#an.ir.swap)(holder, \*, take, give, by[, lag, ...])       | `by` takes `take` from `holder`; `give` goes there in its place.                                                                                                                                   |

### Classes

| [`SceneIR`](#an.ir.SceneIR)(\*[, version, compatible_version, ...])   | Top-level Scene IR document.                                                                                                       |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| [`Meta`](#an.ir.Meta)(\*[, title, author, duration, fps, ...])     | Scene metadata.                                                                                                                    |
| [`AssetRef`](#an.ir.AssetRef)(\*, kind, id, store, ref[, ...])         | Reference to an entry in a project store.                                                                                          |
| [`Shot`](#an.ir.Shot)(\*, id[, renderer, duration, camera, ...])   | A single rendered unit.                                                                                                            |
| [`Dialogue`](#an.ir.Dialogue)(\*, speaker, text[, voice_ref, ...])     | One line of spoken dialogue.                                                                                                       |
| [`Camera`](#an.ir.Camera)(\*[, shake, follow, move, keys])           | Camera state for a shot: a named move, or explicit keys.                                                                           |
| [`Resolution`](#an.ir.Resolution)(\*[, width, height])                   | Pixel dimensions of the rendered output.                                                                                           |
| [`World`](#an.ir.World)(\*[, members, viewpoints, travel, frames])  | A scene's world: members at positions, the named viewpoints that are its coverage, and its travel (ADR 0009).                      |
| [`WorldMember`](#an.ir.WorldMember)(\*, kind, id, store, ref[, ...])      | An entity of the scene's world: the same reference a shot's entity carries, at a world position with a size (ADR 0009 decision 1). |
| [`Attachment`](#an.ir.Attachment)(\*, to[, at, scale])                   | A member that goes where another member goes (ADR 0009 decision 1).                                                                |
| [`Viewpoint`](#an.ir.Viewpoint)(\*[, at, look, look_at, vanish, ...])   | A pinhole camera onto the world, or a composition that resolves to one (ADR 0009 decision 2).                                      |
| [`Frame`](#an.ir.Frame)(\*[, parent, at, look, coupling, ...])      | A frame of reference: a pose (position and orientation) over film time, relative to its `parent` (ADR 0009 amendment, an#501).     |
| [`FrameMoving`](#an.ir.FrameMoving)(\*[, direction])                      | A frame translating at a constant velocity: sugar for a frame whose `at` grows by `direction × speed` per second of FILM time.     |
| [`Travel`](#an.ir.Travel)(\*[, direction, speed, near, far, ...])    | The viewpoints moving through the world in film time (ADR 0009 decision 4).                                                        |
| [`Stream`](#an.ir.Stream)(\*, id, ref[, kind, store, height, ...])   | A row of one prop along a travel's direction (ADR 0009 decision 4).                                                                |
| [`FlatAction`](#an.ir.FlatAction)(start, end, action)                    | A leaf action with its absolute start and end times.                                                                               |
| [`ValidationReport`](#an.ir.ValidationReport)([passed, findings])              | Result of running one or more validators.                                                                                          |
| [`ValidationFinding`](#an.ir.ValidationFinding)(severity, ir_path, description) | A single validation issue with a path into the IR.                                                                                 |
| [`DocumentKind`](#an.ir.DocumentKind)(name, version_field, ...)            | A schema-versioned document kind.                                                                                                  |

### *class* an.ir.AssetRef(\*, kind, id, store, ref, overrides=None, stage=None, library=None, joints=<factory>, \*\*extra_data)

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

#### joints *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[JointSpec](an.ir.schema.html.md#an.ir.schema.JointSpec)]*

its parts’
limits, its strings, its pins to other entities; `a` is relative to
the entity. Omitted when empty, so no stored scene changes.

* **Type:**
  Joints this entity declares (`JointSpec`, ADR 0008)

#### kind *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

it selected nothing (the compiler
skipped it, nothing read the styles store) and the name belonged to the
renderer selector. Art direction arrives as a StylePack (#112).

A `str` in the schema, not a `Literal` (ADR 0001 decision 2): the
values are the REGISTERED entity kinds ([`an.genres`](an.genres.html.md#module-an.genres)) — the core’s
`environment`, `prop` and `voice`, a genre’s `character` — and
`an validate` checks it against that registry, naming the genre that
provides an unregistered one.

* **Type:**
  `"style"` was retired in an#106

#### library *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The asset-library version this entry was checked out from (ADR 0005
decision 8): `"[<library>:]<asset_id>@<version>"`, e.g.
`"cutan:character.alice-reiniger@v003"` (grammar:
[`an.library.ids.parse_ref()`](an.library.ids.html.md#an.library.ids.parse_ref), a pinned version required: `vNNN` or
`sha256:<prefix>`, never `latest`). `None` — the
default, and every document written before the library existed — means
the asset is the project’s own. Today the strategy is check-out, so
`ref` still names the project-store key the compiler reads and this
field is the pin beside it; live reference resolves it instead, later.

Additive and omit-when-unset, like `stage`: an unset `library`
leaves no trace in a dump, so no stored scene changes and no schema
version moves.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### stage *: [StagePlacement](an.ir.schema.html.md#an.ir.schema.StagePlacement) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where on the stage this entity stands. `None` — the default and what
every existing document has — means “wherever the layout puts it”,
which for characters is the evenly-spaced row the compiler computes.

**Additive by construction, and hash-free by construction**: the
contract hashes the COMPILED document, and an `AssetRef` never reaches
it. So this field can grow without retiring a single ledger row.

### *class* an.ir.Attachment(, to, at=None, scale=1.0, \*\*extra_data)

Bases: `_IRModel`

A member that goes where another member goes (ADR 0009 decision 1).

```pycon
>>> Attachment(to="paul", at=(8.0, 70.0), scale=0.9).to
'paul'
```

`at` is the offset in the HOST’s native units (its art’s pixels at
`stage.scale` 1) and `scale` the size relative to the host, so the
pair is derived from the host’s placement in every framing. Without
`at` the member is added whenever the host is, with no placement of
its own: another pass places it (the cut-out genre’s body attachments,
from the host’s bones).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.Camera(, shake=None, follow=None, move=None, keys=None, \*\*extra_data)

Bases: `_CameraShakes`

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

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### move *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

A named preset — sugar for `keys`. The cutout renderer’s vocabulary is
`an.stage.compile.CAMERA_MOVES`; validate and the compiler are
pinned to the same table by test, because a move that validates and then
raises is the failure `_check_renderable` exists to prevent.

### *class* an.ir.Dialogue(, speaker, text, voice_ref=None, start=None, duration=None, emotion=None, emotion_intensity=None, viseme_track=None, word_timings=None, audio_ref=None, viseme_ref=None, leveled=None, spoken=None, pause=None, at=None, direction=None, \*\*extra_data)

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

#### emotion_intensity *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

`maya [angry 0.4]: …`
in `scene.md`, a typed parameter on the (b-name) emotion. `None` is
full strength, and is omitted from JSON.

* **Type:**
  How strongly `emotion` shows, 0..1 (an#253)

#### leveled *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict) | [None](https://docs.python.org/3/builtins/constants.html#None)*

<the synthesized
line’s audio_ref>, “gain_db”: <its voice’s gain>}\`\` when `audio_ref`
is the leveled audio. `None` — unleveled — is omitted from JSON.

* **Type:**
  Stamped by voice leveling (an#315)
* **Type:**
  ```
  ``
  ```

  {“source”

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### pause *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Seconds of silence before this line, after the previous line’s speech
ends (the shot start, for the first line) — `(pause 1.5)` in `scene.md`.

#### planned_start(cursor)

Where this line starts, given the previous line ends at `cursor`.

The one rule the audio pipeline stamps into `start` and `an validate`
lays lines out by: `at` if set, else `cursor + pause`. A `start`
on a line never synthesized (no `audio_ref`) was authored — the
spelling of `at` before an#187 — and counts as one; a synthesized
line’s `start` is the pipeline’s own stamp, re-derived here.

```pycon
>>> Dialogue(speaker="a", text="bye", pause=1.5).planned_start(0.8)
2.3
>>> Dialogue(speaker="a", text="bye", at=4.0).planned_start(0.8)
4.0
>>> Dialogue(speaker="a", text="bye").planned_start(0.8)
0.8
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

#### spoken *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

seconds from the line’s start to the end of its
AUDIBLE speech — its take’s own trailing silence left out — stamped
with `duration` from the line’s audio. The next line’s `pause` counts
from here (a line with no pause still follows the whole take).
`None` (silent audio, a line its voice’s `trim_silence` already cut to
the tail the author keeps, a line stamped before an#397) counts from the
end of `duration`, as before. Never written to JSON: it is read off
the line’s stored audio on every pass (the audio pipeline, and a render
that skips synthesis), so `scene.json` and its fixtures do not change.

* **Type:**
  DERIVED (an#397)

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

### *class* an.ir.Frame(\*, parent='world', at=(0.0, 0.0, 0.0), look=(0.0, 0.0, 0.0), coupling='rigid', moving=None, sway=None, sockets=<factory>, \*\*extra_data)

Bases: `_IRModel`

A frame of reference: a pose (position and orientation) over film time,
relative to its `parent` (ADR 0009 amendment, an#501).

```pycon
>>> Frame(moving=FrameMoving(speed=20.0)).parent
'world'
>>> Frame(parent="vehicle", coupling="far").coupling
'far'
```

`at` and `look` (`[yaw, pitch, roll]`, as a viewpoint’s) are the pose
in the parent’s units at film time 0; `moving` adds a constant velocity;
a `set`/`tween` of `<frame>:at_x|at_y|at_z|yaw|pitch|roll` in a shot
replaces the channel for that shot. `coupling: far` follows the parent’s
rotation and none of its translation: the frame of what is at infinity (a
sky, a range of mountains).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### sockets *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]]*

where a
member that `reframe``s into it with ``snap: <name>` lands (a hand’s
palm, a shelf’s slot).

* **Type:**
  Named points of this frame, `{name: point}` in its units

#### sway *: [FrameSway](an.ir.schema.html.md#an.ir.schema.FrameSway) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Lean of the members riding in it when it accelerates (off when unset).

### *class* an.ir.FrameMoving(, direction=(0.0, 0.0, 1.0), speed, \*\*extra_data)

Bases: `_IRModel`

A frame translating at a constant velocity: sugar for a frame whose
`at` grows by `direction × speed` per second of FILM time.

```pycon
>>> FrameMoving(direction=(0.0, 0.0, 1.0), speed=20.0).speed
20.0
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.Meta(\*, title='', author='', duration=0.0, fps=30, resolution=<factory>, default_renderer='cutout', notes='', step_hz=None, style_pack=None, default_easing=None, sounds=<factory>, captions=None, closing_transition=None, voice_loudness=None, \*\*extra_data)

Bases: `_IRModel`

Scene metadata.

#### captions *: [Captions](an.ir.schema.html.md#an.ir.schema.Captions) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Captions from the dialogue’s word timings (`Captions`, an#175);
`None` — the default — is none, omitted from JSON like `style_pack`.

#### closing_transition *: [Transition](an.ir.schema.html.md#an.ir.schema.Transition) | [None](https://docs.python.org/3/builtins/constants.html#None)*

a `fade` to its `color` over its
`duration`, on the last shot’s last frames (the film’s length is
unchanged, and its final frame is the colour; the sound fades with it).
`None` (or a `cut`) ends on the last frame as drawn. A dissolve has
nothing to dissolve into, so it is refused.

* **Type:**
  How the film ENDS (an#389)

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
  Like [`Shot.renderer`](#an.ir.Shot.renderer)

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

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

#### voice_loudness *: [VoiceLoudness](an.ir.schema.html.md#an.ir.schema.VoiceLoudness) | [None](https://docs.python.org/3/builtins/constants.html#None)*

One loudness for every voice (`VoiceLoudness`, an#315); `None`
— the default — levels nothing, and is omitted from JSON.

### *class* an.ir.Resolution(, width=1920, height=1080, \*\*extra_data)

Bases: `_IRModel`

Pixel dimensions of the rendered output.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.SceneIR(\*, version='0.3.0', compatible_version='0.3.0', kind='SceneIR', meta=<factory>, assets=<factory>, timeline=<factory>, world=None, \*\*extra_data)

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

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### world *: [World](an.ir.schema.html.md#an.ir.schema.World) | [None](https://docs.python.org/3/builtins/constants.html#None)*

its members at world positions, its
named viewpoints and its travel. `None` — the default, and every
document written before it existed — is no world at all: every shot is
placed by hand. Omitted from JSON when unset (the `stage` rule), so no
stored scene and no schema version moves.

* **Type:**
  The scene’s **world** (ADR 0009)

### *class* an.ir.Shot(\*, id, renderer='cutout', duration=5.0, camera=None, entities=<factory>, actions=<factory>, dialogue=<factory>, narration=<factory>, options=<factory>, step_hz=None, transition=None, sounds=<factory>, policy=None, viewpoint=None, welds=<factory>, joints=<factory>, solve=None, \*\*extra_data)

Bases: `_IRModel`

A single rendered unit. A scene is a sequence of shots.

A shot’s `renderer` selects the backend that draws it. Every renderer must accept the
same Shot fields; renderer-specific options go under `options`.

#### joints *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[JointSpec](an.ir.schema.html.md#an.ir.schema.JointSpec)]*

Joints between this shot’s bodies (`JointSpec`, ADR 0008); the
`solve` compile pass keeps them at every frame. Omitted when empty.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### policy *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

per aspect, the methods it prefers in
order, over the style pack’s (`StylePack.policy`) and under an author’s
request — `{"locomotion": ["loco.glide"]}`. `None`: the style’s.

* **Type:**
  This shot’s **policy** (an#348)

#### renderer *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Which RENDERER draws this shot — not art direction. The field was
called `style` until an#106, colliding with the styles store (which
holds art direction) and with `AssetRef(kind="style")`; one word for two
meanings is how a scene came to declare a “style” that selected a
renderer while the thing that actually styles it went unread.
A `str` in the schema (ADR 0001 decision 2): any name a renderer
registered (`an.adapters.register_renderer`), checked by `an
validate`. `cutout` stays the persisted default (decision 9).

#### solve *: [SolveSettings](an.ir.schema.html.md#an.ir.schema.SolveSettings) | [None](https://docs.python.org/3/builtins/constants.html#None)*

mode, gravity and
damping over the style pack’s. `None` (omitted): the defaults.

* **Type:**
  How this shot is solved (`SolveSettings`)

#### sounds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SoundCue](an.ir.schema.html.md#an.ir.schema.SoundCue)]*

Sound cues in SHOT-local time (`SoundCue`).

#### step_hz *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per-shot override of [`Meta.step_hz`](#an.ir.Meta.step_hz) (`None` = inherit).

#### transition *: [Transition](an.ir.schema.html.md#an.ir.schema.Transition) | [None](https://docs.python.org/3/builtins/constants.html#None)*

How this shot is entered (`Transition`); `None` is a hard cut.

#### viewpoint *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [Viewpoint](an.ir.schema.html.md#an.ir.schema.Viewpoint) | [None](https://docs.python.org/3/builtins/constants.html#None)*

the name
of one of `world.viewpoints` or an inline [`Viewpoint`](#an.ir.Viewpoint). `None`
(the default, and every document written before the world existed)
means the shot is placed by hand, as it always was. Omitted from JSON
when unset, like `policy`.

* **Type:**
  This shot’s **viewpoint** onto the scene’s world (ADR 0009)

#### welds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[Weld](an.ir.schema.html.md#an.ir.schema.Weld)]*

Items held by something for a span (`Weld`); omitted when empty.

### *class* an.ir.Stream(, id, ref, kind='prop', store='props', height=None, width=None, units_per_px=None, every, lane=0.0, y=0.0, after=None, seed=0, frame=None, \*\*extra_data)

Bases: `_IRModel`

A row of one prop along a travel’s direction (ADR 0009 decision 4).

```pycon
>>> Stream(id="tree", ref="olive_tree", height=4.0, every=(1.0, 3.0), lane=(-3.0, -2.0)).id
'tree'
```

Instances `<id>_<k>` stand `every` world units apart along the
direction (a range is seeded-uniform), `lane` to the right of it
(negative: left), at height `y`; sized like a member. They are
positioned in the world once, so every shot sees the same instances in
the same places at the same film time.

#### frame *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

the world.

* **Type:**
  The frame the row stands in (document key `in`); unset

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.Travel(\*, direction=(0.0, 0.0, 1.0), speed=None, near=0.5, far=60.0, tolerance_px=1.0, max_actions=20000, streams=<factory>, plates=<factory>, \*\*extra_data)

Bases: `_IRModel`

The viewpoints moving through the world in film time (ADR 0009 decision 4).

```pycon
>>> t = Travel(speed=20.0, streams=[Stream(id="pole", ref="pole", height=6.0, every=12.0, lane=2.0)])
>>> t.direction, t.speed
((0.0, 0.0, 1.0), 20.0)
```

The vehicle the members and viewpoints ride moves at `speed` world units
per second of FILM time along `direction`; `streams` stream past
between `near` and `far`. `plates` declares every plane a framed
shot’s environment holds as `far` (at infinity; its parallax factor
must be 0) or `vehicle` (rigid with the camera): `{"far":
["set/rear_view"], "vehicle": ["set/cabin"]}`. A plane in neither is a
validate warning, because a plate with near objects baked in stands
still while the streams move.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.ValidationFinding(severity, ir_path, description, location=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single validation issue with a path into the IR.

#### location *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

`"<file>:<line>"` when the thing to fix is an opaque source a shot runs
(a Manim scene file, an#279) rather than the IR; `None` otherwise.

### *class* an.ir.ValidationReport(passed=True, findings=list())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of running one or more validators.

`passed` is True iff there are no error-severity findings.

### *class* an.ir.Viewpoint(\*, at=None, look=(0.0, 0.0, 0.0), look_at=None, vanish=None, fov=None, focal=None, subject=None, size=None, distance=None, subject_at=(0.0, 0.0), hide=<factory>, frame=None, \*\*extra_data)

Bases: `_IRModel`

A pinhole camera onto the world, or a composition that resolves to one
(ADR 0009 decision 2).

```pycon
>>> Viewpoint(at=(0.0, 0.0, 0.0), vanish=(0.0, -262.0)).vanish
(0.0, -262.0)
>>> Viewpoint(subject="paul", size="close_up", subject_at=(190.0, 0.0)).size
'close_up'
```

A camera: `at` (world), its look as `look: [yaw, pitch, roll]` in
degrees (yaw turns right, pitch looks down, roll turns the picture clockwise), or
`look_at` (a world point), or `vanish` (where the `+z` direction
lands on screen, in pixels from the frame centre: the road’s vanishing
point), and `fov` (horizontal, degrees) or `focal` (pixels).

A composition: `subject` (a member, or a list), `size` (a `SHOT_SIZES`
name) or `distance` (world units), and `subject_at` (where the
subject’s band lands on screen, pixels; the centre by default). The
camera is computed on the look direction so the band fills the frame as
the size says. `hide` names members this shot leaves out.

#### frame *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The frame this camera is mounted in (document key `in`); its `at` and
`look` are in that frame’s units. Unset: the world’s default frame.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.World(\*, members=<factory>, viewpoints=<factory>, travel=None, frames=<factory>, \*\*extra_data)

Bases: `_IRModel`

A scene’s world: members at positions, the named viewpoints that are
its coverage, and its travel (ADR 0009).

```pycon
>>> world = World(members=[
...     WorldMember(kind="character", id="jerry", store="characters", ref="jerry", at=(-0.45, 0.65, 1.6), height=1.75),
...     WorldMember(kind="prop", id="wheel", store="props", ref="wheel", attached=Attachment(to="jerry")),
... ], viewpoints={"two_shot": Viewpoint(at=(0.0, 0.0, 0.0))})
>>> [m.id for m in world.members], sorted(world.viewpoints)
(['jerry', 'wheel'], ['two_shot'])
```

#### all_frames()

The declared frames plus the one a `travel` with a `speed` is
sugar for (`vehicle`, moving along the travel’s direction).

```pycon
>>> World(travel=Travel(speed=4.0)).all_frames()["vehicle"].moving.speed
4.0
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Frame`](an.ir.schema.html.md#an.ir.schema.Frame)]

#### default_frame()

The frame a member or viewpoint is in when it names none: the
travel’s `vehicle` (members ride it) when there is one, else the world.

```pycon
>>> World().default_frame(), World(travel=Travel(speed=1.0)).default_frame()
('world', 'vehicle')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### frames *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Frame](an.ir.schema.html.md#an.ir.schema.Frame)]*

The frames of reference, `{name: Frame}`; `world` is the implicit
root and a travel with a `speed` adds `vehicle`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.WorldMember(\*, kind, id, store, ref, overrides=None, stage=None, library=None, joints=<factory>, at=None, height=None, width=None, units_per_px=None, attached=None, after=None, frame=None, planes=None, depths=None, \*\*extra_data)

Bases: [`AssetRef`](an.ir.schema.html.md#an.ir.schema.AssetRef)

An entity of the scene’s world: the same reference a shot’s entity
carries, at a world position with a size (ADR 0009 decision 1).

```pycon
>>> m = WorldMember(kind="character", id="paul", store="characters", ref="paul",
...                 at=(0.45, 0.65, 1.6), height=1.75)
>>> m.at, m.height
((0.45, 0.65, 1.6), 1.75)
```

`at` is where the entity’s placement point stands (a character’s feet,
a prop’s origin) in world units; exactly one of `height`/`width` (its
size in world units) or `units_per_px` (world units per native pixel, for art
whose extent cannot be measured) sizes it. A member is `attached` to
another instead of positioned, or it is an environment (present in every
framed shot, placed by nothing: plates are per shot). `after` is the
draw anchor a shot’s `stage.after` would be. A member never carries
`stage`: the viewpoint places it.

#### depths *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

An environment’s planes at a depth, `{plane name: z}` in world units
from the camera along its look direction (an#503): the parallax factor of
a plane is DERIVED from it, `z_ref / z` with `z_ref` the depth of the
viewpoint’s subject (else of what the shot shows: the character plane), so
a plane declares where it is and not how fast it scrolls. A plane
with a depth must keep the descriptor’s own `depth` (1.0) and
`parallax` unset: two spellings of one fact are refused. What is at
infinity is a plane in a `far` frame, not a depth.

#### frame *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The frame of reference this member is in (document key `in`); unset
means the world’s default frame ([`World.default_frame()`](#an.ir.World.default_frame)). An
environment’s `frame` is the default of its planes; `planes` names
the exceptions, `{plane name: frame}` (one environment can hold a
cabin plate and a sky plate).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.crowd(id, , ref, count, kind='prop', store=None, layout='grid', area=(-480.0, -60.0, 480.0, 240.0), scale=1.0, scale_jitter=0.0, jitter=0.0, seed=0)

`count` entities of one asset (`kind`/`store`/`ref`) placed in `area`.

id: the crowd’s name; member `k` is `<id>_<k>` (`member_id()`)
ref: the asset every member draws
count: how many (at least 1)
kind: the entity kind (`prop`, or a genre’s, such as `character`)
store: the store the asset lives in (default: the kind’s registered store)
layout: `grid` (rows filled from the back), `row` or `scatter`
area: `(x0, y0, x1, y1)` in scene pixels about the stage centre; a

> member’s stage point stands inside it

scale: every member’s stage scale
scale_jitter: each member’s scale varies by up to this fraction (`0.1`: ±10%)
jitter: each grid or row member moves by up to this fraction of its cell
seed: the scatter and the jitters are drawn from it

```pycon
>>> [m.stage.at for m in crowd("line", ref="dot", count=3, layout="row", area=(0, 0, 300, 100))]
[(50.0, 50.0), (150.0, 50.0), (250.0, 50.0)]
>>> crowd("x", ref="dot", count=0)
Traceback (most recent call last):
...
ValueError: a crowd needs at least one member; got count=0
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`AssetRef`](an.ir.schema.html.md#an.ir.schema.AssetRef)]

### an.ir.delay(duration)

An empty span that consumes time. Useful inside `sequence`.

* **Return type:**
  [`DelayAction`](an.ir.schema.html.md#an.ir.schema.DelayAction)

### an.ir.fan_out(action, members, , crowd_id=None)

A copy of `action` per member, its targets moved from the crowd to the member.

action: any action, leaf or composite; every target naming the crowd
: (`army`, or a node of it, `army/arm_l`) is rewritten

members: the crowd’s members (`AssetRef` s or ids), in order
crowd_id: the crowd’s name (default: read off the first member’s id,

> `army_0` -> `army`)

Pair it with [`an.ir.compose.stagger()`](an.ir.compose.html.md#an.ir.compose.stagger) for a ripple through the ranks,
or [`parallel()`](an.ir.compose.html.md#an.ir.compose.parallel) for the crowd moving as one.

```pycon
>>> from an.ir.compose import tween
>>> [a.target for a in fan_out(tween("army/arm_l", "rotation", to=1.0, duration=0.5), ["army_0", "army_1"])]
['army_0/arm_l', 'army_1/arm_l']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.ir.flatten(action, , start=0.0, play_extent=None)

Walk a composition tree, emitting leaf actions with absolute times.

A `play` without `duration` advances a `sequence` by `play_extent`
(default `default_play_extent()`): its natural length, or zero for a
looping animation, which runs to the shot end.

Delays are absorbed into the timeline (they don’t appear in the output).
Loops are unrolled by simple repetition — appropriate at v0.1; the cutout
runtime can re-roll for efficiency later.

Every node is dispatched through its registered kind
([`ActionKind`](an.genres.html.md#an.genres.ActionKind)), so a genre’s kind flattens without an
edit here; a node whose kind nobody registered raises, naming the genre
that provides it, and an `ExtensionAction` read before its genre
loaded is validated by the registered model on the way through.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`FlatAction`](an.ir.compose.html.md#an.ir.compose.FlatAction)]

### an.ir.grasp(by, item, , reach=0.4, retract=0.35, lean=60.0, align=True)

`by` takes `item`.

```pycon
>>> grasp("stu@hand_r", "musket@grip").item
'musket@grip'
```

* **Return type:**
  [`GraspAction`](an.ir.holds.html.md#an.ir.holds.GraspAction)

### an.ir.handover(item, to, , by=None, meet=1.0, reach=0.4, retract=0.35, lean=60.0, align=True)

Give `item` to `to`.

```pycon
>>> handover("cup", "jo@hand_l", meet=0.5).meet
0.5
```

* **Return type:**
  [`HandoverAction`](an.ir.holds.html.md#an.ir.holds.HandoverAction)

### an.ir.ir_to_markdown(scene)

Render a SceneIR back into the structured Markdown form.

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

This writes the WHOLE document in the writer’s own formatting, and keeps no
prose but `meta.notes`. Updating an existing `scene.md` goes through
`merge_markdown()`, which keeps the author’s text wherever the content
did not change.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.ir.join(joint, , at=0.0)

Rejoin the joint named `joint` at `at`.

```pycon
>>> join("grip", at=2.0).at
2.0
```

* **Return type:**
  [`JoinAction`](an.ir.joints.html.md#an.ir.joints.JoinAction)

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

### an.ir.lower_world(scene, , extents, film_starts=None, fps=None, extent_problems=None, plane_geometry=None)

The scene with every framed shot’s placements derived from the world.

A shot without a viewpoint is returned as it is. For a framed shot: its
listed entities keep their order of appearance among themselves but are
drawn in depth order (far first) with the members the frame shows and the
shot did not list; environments come first; listed entities that are not
members go on top. A listed member’s hand `stage.at` wins (a note says
when it disagrees with the world; its `scale` is the world’s unless set);
one without is filled in. A member the viewpoint hides is left out unless
the shot lists it: the listing wins, and a note says so. Under a travel,
the streams’ slot entities are added with their motion; a scene already
lowered gains nothing from a second pass.

`extents` is what the stage measured ([`an.stage.world.member_extents()`](an.stage.world.html.md#an.stage.world.member_extents)),
`extent_problems` why some could not be; `film_starts` is where each
shot starts in the film, so stream phase is continuous across cuts (the
shot sum by default); `plane_geometry` is `{environment member id: {plane:
(offset, box)}}`, each plane’s origin on screen (`Plane.offset`) and its
drawn box around it (`None`: unknown), read by the stage
(`an.stage.world.plane_geometry()`): where a plane at a world depth is
anchored and when it is on screen (an#503; the origin and no box for one
it does not name).

Raises `WorldError` for a viewpoint the world cannot resolve.

```pycon
>>> lower_world(SceneIR(), extents={}).scene.timeline
[]
```

* **Return type:**
  [`Lowered`](an.ir.world.html.md#an.ir.world.Lowered)

### an.ir.markdown_to_ir(md_text)

Parse the structured Markdown form of a scene into a SceneIR.

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

* **Return type:**
  [`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR)

### an.ir.migrate(doc, target_version=None, , kind=None)

Migrate a document to `target_version` (default: its kind’s current).

Walks the migration registry one step at a time, considering only the
migrations registered for this document’s kind. Raises `ValueError` if no
path exists between the source and target versions.

```pycon
>>> from an.base import SCHEMA_VERSION
>>> migrate({"version": SCHEMA_VERSION, "kind": "SceneIR"})["version"] == SCHEMA_VERSION
True
>>> migrate({"version": "0.1.0", "kind": "SceneIR"})["version"] == SCHEMA_VERSION
True
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.ir.parallel(\*actions)

Run all children at once. Total duration = max of child durations.

* **Return type:**
  [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction)

### an.ir.pin(point, to, , duration=None)

`point` held at `to`. `to` is `body[@point]` or `(x, y)`.

```pycon
>>> pin("cup", (10.0, -40.0)).to
(10.0, -40.0)
```

* **Return type:**
  [`PinAction`](an.ir.joints.html.md#an.ir.joints.PinAction)

### an.ir.place(item, onto, , by=None, rotation=None, reach=0.4, retract=0.35, lean=60.0)

The hand holding `item` puts it `onto` a target.

```pycon
>>> place("book", "ground@-860").onto
'ground@-860'
```

* **Return type:**
  [`PlaceAction`](an.ir.holds.html.md#an.ir.holds.PlaceAction)

### an.ir.pull(point, to, , over=None, give=0.0)

`point` drawn toward `to` (a point, a body point, or a path).

```pycon
>>> pull("kite", "world@0,-300", over=1.0).give == DFLT_PULL_GIVE
True
```

* **Return type:**
  [`PullAction`](an.ir.joints.html.md#an.ir.joints.PullAction)

### an.ir.reframe(target, , to, at=0.0, keep='world', snap=None, inherit=None, motion=None, velocity=(0.0, 0.0, 0.0), gravity=9.81)

`target` changes to frame `to` at `at` seconds into the action.

```pycon
>>> reframe("cup", to="hand", snap="palm").snap
'palm'
```

* **Return type:**
  `ReframeAction`

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

```pycon
>>> @register_migration("Widget", "1.0", "2.0")
... def _bump(doc):
...     doc["widget_version"] = "2.0"
...     return doc
>>> ("Widget", "1.0", "2.0") in MIGRATIONS
True
```

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]], [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]]

### an.ir.release(item, , at=0.0, onto=None, arc=40.0, rotation=None)

Let `item` go at `at` (a drop, or a toss `onto: ground@x`).

```pycon
>>> release("musket", onto="ground@-620", arc=60).arc
60.0
```

* **Return type:**
  [`ReleaseAction`](an.ir.holds.html.md#an.ir.holds.ReleaseAction)

### an.ir.sequence(\*actions)

Run children one after the other. Total duration = sum of child durations.

* **Return type:**
  [`SequenceAction`](an.ir.schema.html.md#an.ir.schema.SequenceAction)

### an.ir.set_(target, property, value, , at=0.0)

Discrete property set at time `at` (relative to its enclosing scope).

* **Return type:**
  [`SetAction`](an.ir.schema.html.md#an.ir.schema.SetAction)

### an.ir.stagger(lag, \*actions)

Start each action `lag` seconds after the previous one STARTS.

The **stagger** (Manim’s `LaggedStart`, `previz`’s compose, a crowd
entering one by one): the children run in parallel, the `i`-th delayed
by `i * lag`. It is authoring sugar, not a new kind — it builds the
`parallel` of `sequence(delay(i * lag), action)` it means, so the
scene document, `scene.md` and every renderer see only core kinds.
Total duration: the latest child’s end. `scene.md` holds it verbatim (a
`kind: parallel` entry), so it round-trips. (`an.stage.text.reveal_units` —
`an.stage.text.stagger` before an#241 — is the text-block preset: a LIST of
per-unit actions with holds, not a combinator.)

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

* **Return type:**
  [`ParallelAction`](an.ir.schema.html.md#an.ir.schema.ParallelAction)

### an.ir.swap(holder, , take, give, by, lag=0.25, rotation=None, reach=0.4, retract=0.35, lean=60.0, align=True)

`by` takes `take` from `holder`; `give` goes there in its place.

```pycon
>>> swap("nap/hand", take="musket", give="sword", by="stu@hand_r").give
'sword'
```

* **Return type:**
  [`SwapAction`](an.ir.holds.html.md#an.ir.holds.SwapAction)

### an.ir.sync(project_dir, scene_file='scene.md')

Reconcile a scene’s markdown and JSON inside a project directory
(`scene.md` and `ir/scene.json`, or the pair of the `scene_file` named;
a named scene that is not there raises `SceneFileError`).

Strategy in v0.1: Markdown is the human SSOT; if both exist, the JSON is
regenerated from the Markdown unless mtimes show JSON is newer (which the
user is told never to do — but we warn instead of silently overwriting).

* **Return type:**
  `SyncResult`

### an.ir.tween(target, property, to, duration, , from_=None, easing=INHERIT)

Animate a property from `from_` (or its current value) to `to`.

`easing` left out inherits the scene’s `meta.default_easing` (else
`"ease_in_out"`); naming one — `"ease_in_out"` included — pins it.

```pycon
>>> "easing" in tween("a", "x", to=1.0, duration=1.0).model_fields_set
False
>>> tween("a", "x", to=1.0, duration=1.0, easing="linear").easing
'linear'
```

* **Return type:**
  [`TweenAction`](an.ir.schema.html.md#an.ir.schema.TweenAction)

### an.ir.unjoin(joint, , at=0.0)

Let go of the joint named `joint` at `at`.

```pycon
>>> unjoin("grip").joint
'grip'
```

* **Return type:**
  [`UnjoinAction`](an.ir.joints.html.md#an.ir.joints.UnjoinAction)

### an.ir.validate_schema(doc)

Validate that `doc` (dict, JSON string, or SceneIR) conforms to the schema.

```pycon
>>> validate_schema({"meta": {"title": "x"}, "timeline": []}).passed
True
>>> r = validate_schema({"meta": {"title": "x"}, "timeline": [{"id": "s", "duration": "not-a-number"}]})
>>> r.passed
False
```

* **Return type:**
  [`ValidationReport`](an.ir.validate.html.md#an.ir.validate.ValidationReport)

### an.ir.validate_semantic(scene, , available_voices=None, available_characters=None, available_props=None, available_environments=None, available_sounds=None, available_library_lock=None, available_styles=None, available_recordings=None, only=None, fps=None)

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
does after synthesis, `post_synthesis_findings()`), plus the ones in
`ALWAYS_RUN_CHECKS`, which report on whichever checks ran; `fps` is the one
the film is assembled at when it is not the scene’s (`an render --fps`),
which decides how long a dissolve’s overlap is.

* **Return type:**
  [`ValidationReport`](an.ir.validate.html.md#an.ir.validate.ValidationReport)

### Modules

| [`assets`](an.ir.assets.html.md#module-an.ir.assets)     | Where a third-party asset came from, and what its licence obliges.                         |
|---------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| [`camera`](an.ir.camera.html.md#module-an.ir.camera)     | Camera semantics: the named moves, and the one resolver that expands them.                 |
| [`compose`](an.ir.compose.html.md#module-an.ir.compose)   | Composition combinators for authoring action trees, plus a flattener.                      |
| [`frames`](an.ir.frames.html.md#module-an.ir.frames)     | Frames of reference: a tree of named poses over film time (ADR 0009 amendment, an#501).    |
| [`holds`](an.ir.holds.html.md#module-an.ir.holds)       | Holding things: `grasp`, `place`, `release`, `handover` and `swap` (an#502, catalogue A4). |
| [`joints`](an.ir.joints.html.md#module-an.ir.joints)     | The constraint layer's verbs: `pin`, `pull`, `join` and `unjoin` (ADR 0008, an#512).       |
| [`schema`](an.ir.schema.html.md#module-an.ir.schema)     | Pydantic v2 models for the Scene IR.                                                       |
| [`validate`](an.ir.validate.html.md#module-an.ir.validate) | Schema and semantic validation for SceneIR documents.                                      |
| [`world`](an.ir.world.html.md#module-an.ir.world)       | One world, many shots: the scene world's geometry and its lowering (ADR 0009).             |
