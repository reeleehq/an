# an.ir.schema

Pydantic v2 models for the Scene IR.

Design principles (locked in from the architectural plan):

- **Renderer-agnostic.** No cutout-specific or Manim-specific fields here. Backend
  adapters compile shots into their own internal formats. This module only knows
  what every shot has in common.
- **Versioned envelope.** Every IR document carries `version` and
  `compatible_version`. Migrations live in `an.ir.migrate`.
- **Forward-compatible reads.** Top-level model has `extra="allow"` so a future
  field doesn’t crash an older reader.
- \*\*Open `Action` union\*\* (ADR 0001 decision 2). The union holds the core
  kinds (`set`, `tween`, `sequence`, `parallel`, `delay`, `loop`)
  and ONE open member, [`ExtensionAction`](#an.ir.schema.ExtensionAction), which a callable
  discriminator selects for any other `kind`. A genre registers its kinds
  ([`an.genres`](an.genres.html.md#module-an.genres)); a document’s `kind: play` then validates to the
  registered model, and before registration it stays an `ExtensionAction`
  that round-trips untouched and that validate, flatten and the compiler
  refuse by name. The union is never rebuilt at registration.
- **Time in seconds (float).** Always.

Doctest:

```pycon
>>> from an.ir.schema import SceneIR, Meta, Shot
>>> scene = SceneIR(
...     meta=Meta(title="Park Bench", duration=45.0),
...     timeline=[Shot(id="s1", renderer="cutout", duration=45.0)],
... )
>>> from an.base import SCHEMA_VERSION
>>> scene.version == SCHEMA_VERSION
True
>>> scene.kind
'SceneIR'
>>> scene.timeline[0].renderer
'cutout'
```

### Module Attributes

| [`DFLT_SHAKE_DURATION`](#an.ir.schema.DFLT_SHAKE_DURATION)       | how long a jolt lasts, how far the frame jumps (a fraction of the frame HEIGHT, so it reads the same at any resolution: 0.015 is about 11 px at 720p), and how many times a second it jumps.                                                                              |
|----------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Point3`](#an.ir.schema.Point3)                    | the stage's axes extended with depth — `x` right, `y` DOWN, `z` away from the viewer.                                                                                                                                                                                     |
| [`DFLT_FOV_DEG`](#an.ir.schema.DFLT_FOV_DEG)              | The horizontal field of view a viewpoint has when it names neither `fov` nor `focal`: a normal lens, neither wide nor long.                                                                                                                                               |
| [`SHOT_SIZES`](#an.ir.schema.SHOT_SIZES)                | Shot sizes, by where the frame cuts the subject (the film convention, see ADR 0009): `name: (top, bottom, fill)`.                                                                                                                                                         |
| [`DFLT_TRAVEL_NEAR`](#an.ir.schema.DFLT_TRAVEL_NEAR)          | nearer than `near` an instance has passed the camera (and is hidden); beyond `far` it is effectively at infinity (the far plate's job, not a stream's).                                                                                                                   |
| [`DFLT_TRAVEL_TOLERANCE_PX`](#an.ir.schema.DFLT_TRAVEL_TOLERANCE_PX)  | How far a stream instance's screen position may stray from the fitted tweens between two of their keys, in pixels: the fitting's tolerance.                                                                                                                               |
| [`DFLT_TRAVEL_MAX_ACTIONS`](#an.ir.schema.DFLT_TRAVEL_MAX_ACTIONS)   | The most actions one shot's travel may lower to before the lowering refuses and names the knobs: a 10 s road with three streams is about four thousand; a minute of dense road markings would be fifty thousand, which is a document the runtime pays for on every frame. |
| [`WORLD_FRAME`](#an.ir.schema.WORLD_FRAME)               | the world itself.                                                                                                                                                                                                                                                         |
| [`VEHICLE_FRAME`](#an.ir.schema.VEHICLE_FRAME)             | The frame a `travel` with a `speed` is sugar for (viewpoints and members ride it by default; streams stay in the world).                                                                                                                                                  |
| [`FRAME_COUPLINGS`](#an.ir.schema.FRAME_COUPLINGS)           | `rigid` takes the parent's whole pose, `far` only its rotation (what is at infinity turns with the camera and never translates).                                                                                                                                          |
| [`FRAME_KEY`](#an.ir.schema.FRAME_KEY)                 | The key an element's frame is written under in a document (`frame` is the field; `in` is not a name Python lets a field have).                                                                                                                                            |
| [`JOINT_TYPES`](#an.ir.schema.JOINT_TYPES)               | The joint types a scene declares.                                                                                                                                                                                                                                         |
| [`SEGMENT_JOINT_TYPES`](#an.ir.schema.SEGMENT_JOINT_TYPES)       | The types that join a point to a segment (`b` is its start, `end` its end).                                                                                                                                                                                               |
| [`PART_JOINT_TYPES`](#an.ir.schema.PART_JOINT_TYPES)          | a rig part's own joint to its parent.                                                                                                                                                                                                                                     |
| [`DISTANCE_MODES`](#an.ir.schema.DISTANCE_MODES)            | How a distance holds its length; `string` and `rod` imply one.                                                                                                                                                                                                            |
| [`DFLT_GRAVITY`](#an.ir.schema.DFLT_GRAVITY)              | The pull of gravity a `down` with no number means, in scene px per second² (a 1080-px frame is about 1.1 m of a standing figure, so 980 is earth's g at roughly one pixel per millimetre: the conventional animation default).                                            |
| [`GRAVITY_DIRECTIONS`](#an.ir.schema.GRAVITY_DIRECTIONS)        | Where each named gravity direction pulls, on the stage's y-down axes.                                                                                                                                                                                                     |
| [`NO_GRAVITY`](#an.ir.schema.NO_GRAVITY)                | The spellings of no gravity.                                                                                                                                                                                                                                              |
| [`TRAVEL_PLATE_ROLES`](#an.ir.schema.TRAVEL_PLATE_ROLES)        | at infinity, or rigid with the vehicle the viewpoints are mounted on.                                                                                                                                                                                                     |
| [`DFLT_WORLD_GRAVITY`](#an.ir.schema.DFLT_WORLD_GRAVITY)        | Gravity, world units per second² along +y (down; the world's units are metres): Earth's.                                                                                                                                                                                  |
| [`DFLT_SWAY_LIMIT_DEG`](#an.ir.schema.DFLT_SWAY_LIMIT_DEG)       | The most a member of a swaying frame leans by default, degrees.                                                                                                                                                                                                           |
| [`CORE_ACTION_KINDS`](#an.ir.schema.CORE_ACTION_KINDS)         | The `kind` of every action the core defines (the static union members).                                                                                                                                                                                                   |
| [`EXTENSION_TAG`](#an.ir.schema.EXTENSION_TAG)             | The union tag of the open member.                                                                                                                                                                                                                                         |
| [`Action`](#an.ir.schema.Action)                    | the core kinds plus [`ExtensionAction`](#an.ir.schema.ExtensionAction) for any other `kind` (a registered genre kind validates to its own model through it).                                                                                                |
| [`DEFAULT_CAPTION_MAX_CHARS`](#an.ir.schema.DEFAULT_CAPTION_MAX_CHARS) | the broadcast convention (BBC / Netflix timed-text guidance: 42 characters, two lines).                                                                                                                                                                                   |
| [`DEFAULT_CAPTION_SIZE`](#an.ir.schema.DEFAULT_CAPTION_SIZE)      | Caption type size as a fraction of frame height — a little under the title default, as captions are read while something else is watched.                                                                                                                                 |
| [`STAGE_NODE_SPACE`](#an.ir.schema.STAGE_NODE_SPACE)          | The property space a 2D stage engine's node lives in ([`an.timing.spaces`](an.timing.spaces.html.md#module-an.timing.spaces)).                                                                                                                         |
| [`SPECIMEN_DURATION`](#an.ir.schema.SPECIMEN_DURATION)         | How long a specimen shot runs (`an library sheet` draws its first frame).                                                                                                                                                                                                 |
| [`SPECIMEN_SHOT_ID`](#an.ir.schema.SPECIMEN_SHOT_ID)          | The id of a specimen shot.                                                                                                                                                                                                                                                |

### Functions

| [`gravity_vector`](#an.ir.schema.gravity_vector)(spec)                        | The acceleration a gravity declaration means, or `None` for none.                                                               |
|----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| [`resolve_step_hz`](#an.ir.schema.resolve_step_hz)(shot, scene_step_hz)        | The stepped-timing policy `shot` renders under: its own `step_hz` when it declares one, else the scene's, else `None` (smooth). |
| [`stage_specimen`](#an.ir.schema.stage_specimen)(ref)                         | A short shot showing the one stage entity `ref` casts, on its own (an#347).                                                     |
| [`unregistered_action_kind`](#an.ir.schema.unregistered_action_kind)(kind, \*[, where]) | The error for an action `kind` no loaded genre registered.                                                                      |

### Classes

| [`AssetRef`](#an.ir.schema.AssetRef)(\*, kind, id, store, ref[, ...])          | Reference to an entry in a project store.                                                                                                                                                                                                                                                |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Attachment`](#an.ir.schema.Attachment)(\*, to[, at, scale])                    | A member that goes where another member goes (ADR 0009 decision 1).                                                                                                                                                                                                                      |
| [`Camera`](#an.ir.schema.Camera)(\*[, shake, follow, move, keys])            | Camera state for a shot: a named move, or explicit keys.                                                                                                                                                                                                                                 |
| [`CameraFollow`](#an.ir.schema.CameraFollow)(\*, target[, axes, lag])              | A camera that follows an entity (an#445): the frame keeps `target` where it stood at the shot's start.                                                                                                                                                                                   |
| [`CameraKey`](#an.ir.schema.CameraKey)(\*[, at, x, y, zoom, rotation, easing])  | One camera pose at one time — the explicit door behind the named moves.                                                                                                                                                                                                                  |
| [`CameraShake`](#an.ir.schema.CameraShake)(\*[, at, duration, amplitude, ...])    | A jolt of the frame inside a shot (an#429): seeded screen-space jitter.                                                                                                                                                                                                                  |
| [`Captions`](#an.ir.schema.Captions)(\*[, burn, sidecar, max_chars, ...])      | Captions for the whole film, built from the dialogue's word timings.                                                                                                                                                                                                                     |
| [`CueAnchor`](#an.ir.schema.CueAnchor)(\*, when, reaches[, offset, shot])       | A sound cue's time, taken from the picture (an#317): when a node reaches a frame row or column.                                                                                                                                                                                          |
| [`CueUntil`](#an.ir.schema.CueUntil)(\*, cue[, offset])                        | Where a sound cue ends: at another cue's start, plus `offset` (an#317).                                                                                                                                                                                                                  |
| [`DelayAction`](#an.ir.schema.DelayAction)(\*[, name, kind])                      | Composition: an empty span that consumes time.                                                                                                                                                                                                                                           |
| [`Dialogue`](#an.ir.schema.Dialogue)(\*, speaker, text[, voice_ref, ...])      | One line of spoken dialogue.                                                                                                                                                                                                                                                             |
| [`ExtensionAction`](#an.ir.schema.ExtensionAction)(\*[, name])                        | An action of a kind the core does not define: the IR's one open member.                                                                                                                                                                                                                  |
| [`Frame`](#an.ir.schema.Frame)(\*[, parent, at, look, coupling, ...])       | A frame of reference: a pose (position and orientation) over film time, relative to its `parent` (ADR 0009 amendment, an#501).                                                                                                                                                           |
| [`FrameMoving`](#an.ir.schema.FrameMoving)(\*[, direction])                       | A frame translating at a constant velocity: sugar for a frame whose `at` grows by `direction × speed` per second of FILM time.                                                                                                                                                           |
| [`FrameSway`](#an.ir.schema.FrameSway)(\*[, gain, settle, gravity, limit])      | Opt-in sway of an accelerating frame (an#504): what rides in it leans away from the acceleration by `gain × atan(a / gravity)` (the pseudo-force of a non-inertial frame; follow-through and drag, in animation terms), settling with the time constant `settle` seconds (`0`: at once). |
| [`JointSpec`](#an.ir.schema.JointSpec)(\*, type, a[, b, end, limits, ...])      | A declared relation between two bodies (ADR 0008 decision 3).                                                                                                                                                                                                                            |
| [`LoopAction`](#an.ir.schema.LoopAction)(\*[, name, kind, count])                | Composition: repeat `child` `count` times.                                                                                                                                                                                                                                               |
| [`Meta`](#an.ir.schema.Meta)(\*[, title, author, duration, fps, ...])      | Scene metadata.                                                                                                                                                                                                                                                                          |
| [`Narration`](#an.ir.schema.Narration)(\*, text[, voice_ref, start, ...])       | Off-screen narration.                                                                                                                                                                                                                                                                    |
| [`ParallelAction`](#an.ir.schema.ParallelAction)(\*[, name, kind, children])         | Composition: run all children simultaneously starting at the same time.                                                                                                                                                                                                                  |
| [`Resolution`](#an.ir.schema.Resolution)(\*[, width, height])                    | Pixel dimensions of the rendered output.                                                                                                                                                                                                                                                 |
| [`SceneIR`](#an.ir.schema.SceneIR)(\*[, version, compatible_version, ...])    | Top-level Scene IR document.                                                                                                                                                                                                                                                             |
| [`SequenceAction`](#an.ir.schema.SequenceAction)(\*[, name, kind, children])         | Composition: run children one after the other.                                                                                                                                                                                                                                           |
| [`SetAction`](#an.ir.schema.SetAction)(\*[, name, kind, at])                    | Set a property to a value at a specific time.                                                                                                                                                                                                                                            |
| [`Shot`](#an.ir.schema.Shot)(\*, id[, renderer, duration, camera, ...])    | A single rendered unit.                                                                                                                                                                                                                                                                  |
| [`SolveSettings`](#an.ir.schema.SolveSettings)(\*[, mode, gravity, damping, ...])   | How a shot's joints are solved: a per-shot override of the style pack's `gravity` and `damping`, and the solve's mode and effort (ADR 0008 decision 4).                                                                                                                                  |
| [`SoundCue`](#an.ir.schema.SoundCue)(\*, sound[, at, until, cause, ...])       | One sound placed on the timeline: an SFX hit, an ambience, a music bed.                                                                                                                                                                                                                  |
| [`StagePlacement`](#an.ir.schema.StagePlacement)(\*[, at, scale, after])             | Where an entity stands on the stage, and how big it is.                                                                                                                                                                                                                                  |
| [`Stream`](#an.ir.schema.Stream)(\*, id, ref[, kind, store, height, ...])    | A row of one prop along a travel's direction (ADR 0009 decision 4).                                                                                                                                                                                                                      |
| [`Transition`](#an.ir.schema.Transition)(\*[, kind, duration, color, ...])       | How a shot is ENTERED — from the previous shot, or (for the first shot) from nothing.                                                                                                                                                                                                    |
| [`Travel`](#an.ir.schema.Travel)(\*[, direction, speed, near, far, ...])     | The viewpoints moving through the world in film time (ADR 0009 decision 4).                                                                                                                                                                                                              |
| [`TweenAction`](#an.ir.schema.TweenAction)(\*[, name, kind, from_value, ...])     | Animate a property from a start value to an end value over a duration.                                                                                                                                                                                                                   |
| [`Viewpoint`](#an.ir.schema.Viewpoint)(\*[, at, look, look_at, vanish, ...])    | A pinhole camera onto the world, or a composition that resolves to one (ADR 0009 decision 2).                                                                                                                                                                                            |
| [`VisemeKeyframe`](#an.ir.schema.VisemeKeyframe)(\*, time, viseme, \*\*extra_data)   | A single mouth-shape keyframe in a viseme track.                                                                                                                                                                                                                                         |
| [`VisemeTrack`](#an.ir.schema.VisemeTrack)(\*[, fps_hint, keyframes])             | Aligned viseme track produced by the lip-sync stage.                                                                                                                                                                                                                                     |
| [`VoiceLoudness`](#an.ir.schema.VoiceLoudness)(\*[, target_lufs, peak_db])          | One loudness for every voice of the film (an#315).                                                                                                                                                                                                                                       |
| [`Weld`](#an.ir.schema.Weld)(\*, item, by[, start, until, offset])         | A held item: `item` stays at `offset` from `by` between `start` and `until` (catalogue A4).                                                                                                                                                                                              |
| [`WordTimingIR`](#an.ir.schema.WordTimingIR)(\*, text, start, end, \*\*extra_data) | One word of a line and when it was spoken, in seconds from the line's start (like [`VisemeKeyframe`](#an.ir.schema.VisemeKeyframe), never absolute).                                                                                                                      |
| [`World`](#an.ir.schema.World)(\*[, members, viewpoints, travel, frames])   | A scene's world: members at positions, the named viewpoints that are its coverage, and its travel (ADR 0009).                                                                                                                                                                            |
| [`WorldMember`](#an.ir.schema.WorldMember)(\*, kind, id, store, ref[, ...])       | An entity of the scene's world: the same reference a shot's entity carries, at a world position with a size (ADR 0009 decision 1).                                                                                                                                                       |

### an.ir.schema.Action

the core kinds plus [`ExtensionAction`](#an.ir.schema.ExtensionAction) for any other
`kind` (a registered genre kind validates to its own model through it).
`SerializeAsAny` makes a typed genre instance (a `PlayAction`) serialize
with its own fields rather than the open member’s.

* **Type:**
  Every action

alias of `Annotated`[`Annotated`[[`SetAction`](#an.ir.schema.SetAction), `Tag`(tag=set)] | `Annotated`[[`TweenAction`](#an.ir.schema.TweenAction), `Tag`(tag=tween)] | `Annotated`[[`SequenceAction`](#an.ir.schema.SequenceAction), `Tag`(tag=sequence)] | `Annotated`[[`ParallelAction`](#an.ir.schema.ParallelAction), `Tag`(tag=parallel)] | `Annotated`[[`DelayAction`](#an.ir.schema.DelayAction), `Tag`(tag=delay)] | `Annotated`[[`LoopAction`](#an.ir.schema.LoopAction), `Tag`(tag=loop)] | `Annotated`[[`ExtensionAction`](#an.ir.schema.ExtensionAction), `SerializeAsAny`(), `Tag`(tag=extension)], `Discriminator`(discriminator=`_action_tag`, custom_error_type=[`None`](https://docs.python.org/3/builtins/constants.html#None), custom_error_message=[`None`](https://docs.python.org/3/builtins/constants.html#None), custom_error_context=[`None`](https://docs.python.org/3/builtins/constants.html#None))]

### *class* an.ir.schema.AssetRef(\*, kind, id, store, ref, overrides=None, stage=None, library=None, joints=<factory>, \*\*extra_data)

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

#### joints *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[JointSpec](#an.ir.schema.JointSpec)]*

its parts’
limits, its strings, its pins to other entities; `a` is relative to
the entity. Omitted when empty, so no stored scene changes.

* **Type:**
  Joints this entity declares ([`JointSpec`](#an.ir.schema.JointSpec), ADR 0008)

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

#### stage *: [StagePlacement](#an.ir.schema.StagePlacement) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where on the stage this entity stands. `None` — the default and what
every existing document has — means “wherever the layout puts it”,
which for characters is the evenly-spaced row the compiler computes.

**Additive by construction, and hash-free by construction**: the
contract hashes the COMPILED document, and an `AssetRef` never reaches
it. So this field can grow without retiring a single ledger row.

### *class* an.ir.schema.Attachment(, to, at=None, scale=1.0, \*\*extra_data)

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

### an.ir.schema.CORE_ACTION_KINDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('set', 'tween', 'sequence', 'parallel', 'delay', 'loop')*

The `kind` of every action the core defines (the static union members).

### *class* an.ir.schema.Camera(, shake=None, follow=None, move=None, keys=None, \*\*extra_data)

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

#### keys *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[CameraKey](#an.ir.schema.CameraKey)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The explicit door. `None` = use `move`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### move *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

A named preset — sugar for `keys`. The cutout renderer’s vocabulary is
`an.stage.compile.CAMERA_MOVES`; validate and the compiler are
pinned to the same table by test, because a move that validates and then
raises is the failure `_check_renderable` exists to prevent.

### *class* an.ir.schema.CameraFollow(, target, axes='x', lag=0.0, \*\*extra_data)

Bases: `_IRModel`

A camera that follows an entity (an#445): the frame keeps `target`
where it stood at the shot’s start.

```pycon
>>> CameraFollow(target="bob").axes
'x'
```

`target` is an entity id or one of its nodes (`bob/head`); `axes` is
which way the camera tracks it (`x`: a side-scrolling walk, `xy`: both).
Resolved at compile time from the compiled motion (the target’s position at
every frame), so planes parallax with it like any camera move.

#### lag *: [float](https://docs.python.org/3/builtins/functions.html#float)*

it tracks the target through
a first-order filter, so after `lag` seconds of a step it has covered
63% of it (Cinemachine’s damping). `0`: the frame keeps the target put.

* **Type:**
  Time constant of the camera’s catch-up (s)

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.CameraKey(, at=0.0, x=0.0, y=0.0, zoom=1.0, rotation=0.0, easing=None, \*\*extra_data)

Bases: `_IRModel`

One camera pose at one time — the explicit door behind the named moves.

```pycon
>>> CameraKey(at=1.0, x=-160.0, zoom=1.25).x
-160.0
```

**Sign convention**, stated because every surveyed tool disagrees: `+x`
moves the CAMERA right, which moves the content left. `zoom` is on-screen
magnification, so `1.25` means “everything 25% bigger”, and it composes
through the pivot — a push-in during a pan zooms toward what the camera is
looking at rather than toward a fixed frame centre. `rotation` is camera
roll in radians.

`easing` defaults to **\`None\`, not \`”ease_in_out”\`**, and that is not a
style choice: today’s emitter puts `"ease_in_out"` on the first keyframe
and `null` on the terminal one, so a per-key default of `"ease_in_out"`
would put it on both and move every camera scene’s contract hash. The
named moves supply the easing they have always supplied.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### rotation *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Camera roll, radians.

#### x *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Camera position in scene pixels. `+x` moves the camera right.

#### zoom *: [float](https://docs.python.org/3/builtins/functions.html#float)*

On-screen magnification. Must be > 0 — a zero or negative zoom is not a
camera, and the compiler would emit a degenerate root scale.

### *class* an.ir.schema.CameraShake(, at=0.0, duration=0.4, amplitude=0.015, frequency=24.0, decay=True, seed=0, \*\*extra_data)

Bases: `_IRModel`

A jolt of the frame inside a shot (an#429): seeded screen-space jitter.

```pycon
>>> CameraShake(at=1.0).duration
0.4
```

Layered on whatever the camera does (a `move`, `keys`, or nothing): the
pan and zoom are the root’s pivot and scale, a shake is its screen
position, so the two add without either knowing the other. The jitter is
deterministic (`seed`) and, with `decay`, falls linearly to rest by
the end; the frame is exactly at rest before `at` and after it.

#### amplitude *: [float](https://docs.python.org/3/builtins/functions.html#float)*

How far the frame jumps at most, as a fraction of the frame height.

#### at *: [float](https://docs.python.org/3/builtins/functions.html#float)*

When the jolt starts, in shot seconds.

#### decay *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Fall linearly to rest over the duration (an impact); off, it holds its
amplitude to the end (a rumble).

#### duration *: [float](https://docs.python.org/3/builtins/functions.html#float)*

How long it lasts.

#### frequency *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Jumps per second.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### seed *: [int](https://docs.python.org/3/builtins/functions.html#int)*

the same seed draws the same jolt on every machine.

* **Type:**
  Which jitter

### *class* an.ir.schema.Captions(, burn=True, sidecar=True, max_chars=42, max_lines=2, size=0.05, color='#1a1a1a', highlight=None, anchor='bottom', font=None, strict=False, \*\*extra_data)

Bases: `_IRModel`

Captions for the whole film, built from the dialogue’s word timings.

Present = on; `meta.captions` unset (the default) is no captions and no
trace in any document. One cue list ([`an.captions.caption_pages()`](an.captions.html.md#an.captions.caption_pages))
feeds BOTH outputs, so the picture and the sidecar cannot disagree:

- `burn`: each page is drawn as an overlay text block (camera-immune,
  placed at `anchor` in the title-safe area), shown for exactly the
  frames the sidecar says;
- `sidecar`: a SubRip `.srt` written through the `captions` store,
  next to the delivered mp4, in FILM time (a dissolve shortens the film,
  and every later cue moves with it).

```pycon
>>> Captions().max_chars, Captions().anchor
(42, 'bottom')
>>> Captions(highlight="#ffcc00").highlight
'#ffcc00'
```

#### anchor *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

One of tituli’s nine title-safe anchors.

#### font *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

`None` = the embedded face; else an ABSOLUTE font file path, or one
relative to the project directory.

#### highlight *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

the word being spoken is drawn in this colour (karaoke);
`None` draws every word in `color`.

* **Type:**
  `#rrggbb`

#### max_chars *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Line breaks are made HERE, by character count, and written into both
the burned block and the sidecar — the same lines in both. 42 fits the
title-safe width of a 16:9 or 4:3 frame at the default size; a square
or portrait frame needs fewer (about 32 at 1:1) or a smaller `size` —
a line that does not fit is REFUSED before the render, never clipped.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### strict *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

A line with no word timings is captioned with its words spread evenly
over its duration, with a warning; `strict` makes that an error.

### *class* an.ir.schema.CueAnchor(, when, reaches, offset=0.0, shot=None, \*\*extra_data)

Bases: `_IRModel`

A sound cue’s time, taken from the picture (an#317): when a node reaches a frame row or column.

`when` is a node path in a stage shot (`crawl/line_7`: a text block’s
unit, a prop, a plane); `reaches` is `{"y": px}` or `{"x": px}` in
the frame’s pixels (0 at the top or left), crossed in either direction by
the node’s on-screen centre — the camera, parallax and a crawl’s tilt
included. Resolved when the film is laid out, never written back into the
scene: a layout change moves the sound with the picture. `offset` is
added after. `shot` names the shot to look in, for a cue in
`meta.sounds` (default: the first shot that has the node).

```pycon
>>> CueAnchor(when="crawl/line_7", reaches={"y": 840}).axis
('y', 840.0)
```

#### *property* axis *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float)]*

`(axis, pixels)`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.CueUntil(, cue, offset=0.0, \*\*extra_data)

Bases: `_IRModel`

Where a sound cue ends: at another cue’s start, plus `offset` (an#317).

`cue` is the `sound` key of a cue in the same list (the shot’s, or
`meta.sounds`); the first such cue is meant.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.schema.DEFAULT_CAPTION_MAX_CHARS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 42*

the broadcast
convention (BBC / Netflix timed-text guidance: 42 characters, two lines).

* **Type:**
  Characters per caption line and lines per caption page

### an.ir.schema.DEFAULT_CAPTION_SIZE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.05*

Caption type size as a fraction of frame height — a little under the title
default, as captions are read while something else is watched.

### an.ir.schema.DFLT_FOV_DEG *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 50.0*

The horizontal field of view a viewpoint has when it names neither `fov`
nor `focal`: a normal lens, neither wide nor long.

### an.ir.schema.DFLT_GRAVITY *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 980.0*

The pull of gravity a `down` with no number means, in scene px per second²
(a 1080-px frame is about 1.1 m of a standing figure, so 980 is earth’s g at
roughly one pixel per millimetre: the conventional animation default).

### an.ir.schema.DFLT_SHAKE_DURATION *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.4*

how long a jolt lasts, how far the frame
jumps (a fraction of the frame HEIGHT, so it reads the same at any
resolution: 0.015 is about 11 px at 720p), and how many times a second it
jumps. Art direction, chosen to read as an impact rather than a tremor.

* **Type:**
  A camera shake’s defaults (an#429)

### an.ir.schema.DFLT_SWAY_LIMIT_DEG *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 75.0*

The most a member of a swaying frame leans by default, degrees.

### an.ir.schema.DFLT_TRAVEL_MAX_ACTIONS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 20000*

The most actions one shot’s travel may lower to before the lowering
refuses and names the knobs: a 10 s road with three streams is about four
thousand; a minute of dense road markings would be fifty thousand, which
is a document the runtime pays for on every frame.

### an.ir.schema.DFLT_TRAVEL_NEAR *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

nearer than `near` an instance has
passed the camera (and is hidden); beyond `far` it is effectively at infinity
(the far plate’s job, not a stream’s).

* **Type:**
  A travel’s depth range, in world units

### an.ir.schema.DFLT_TRAVEL_TOLERANCE_PX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1.0*

How far a stream instance’s screen position may stray from the fitted
tweens between two of their keys, in pixels: the fitting’s tolerance.

### an.ir.schema.DFLT_WORLD_GRAVITY *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 9.81*

Gravity, world units per second² along +y (down; the world’s units are
metres): Earth’s. A `motion: ballistic` reframe falls with it
([`an.ir.reframe`](an.ir.html.md#an.ir.reframe), which re-exports it) and a `FrameSway` leans by it.

### an.ir.schema.DISTANCE_MODES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('equal', 'at_most', 'at_least')*

How a distance holds its length; `string` and `rod` imply one.

### *class* an.ir.schema.DelayAction(, name=None, kind='delay', duration, \*\*extra_data)

Bases: `_ActionBase`

Composition: an empty span that consumes time.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.Dialogue(, speaker, text, voice_ref=None, start=None, duration=None, emotion=None, emotion_intensity=None, viseme_track=None, word_timings=None, audio_ref=None, viseme_ref=None, leveled=None, spoken=None, pause=None, at=None, direction=None, \*\*extra_data)

Bases: `_IRModel`

One line of spoken dialogue.

`start` and `duration` are None until the audio pipeline runs (TTS
gives us a real duration); the pipeline stamps them then, deriving
`start` from the author’s `pause` / `at` ([`planned_start()`](#an.ir.schema.Dialogue.planned_start)).

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

#### word_timings *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[WordTimingIR](#an.ir.schema.WordTimingIR)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The provider’s word timings, line-relative; `None` when the provider
has none (offline, Rhubarb) or the line was stamped before an#96.

### an.ir.schema.EXTENSION_TAG *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'extension'*

The union tag of the open member.

### *class* an.ir.schema.ExtensionAction(, name=None, kind, \*\*extra_data)

Bases: `_ActionBase`

An action of a kind the core does not define: the IR’s one open member.

The schema’s `Action` union selects this for any `kind` other than the
core’s (ADR 0001 decision 2). When a genre has REGISTERED that kind
([`an.genres.registry.register_action_kind()`](an.genres.registry.html.md#an.genres.registry.register_action_kind)), validating a document
yields the registered model instead — a `PlayAction` for `kind: play` —
so code downstream sees typed actions. Before registration the action
stays an `ExtensionAction`: its fields are kept as extras and round-trip
byte for byte, and [`resolved()`](#an.ir.schema.ExtensionAction.resolved) (called by `flatten`, `an validate`
and the compiler) refuses it naming the genre that provides it.

Every genre’s action model subclasses this, which is what lets a typed
instance sit in the union and serialize with its own fields.

```pycon
>>> ExtensionAction(kind="wave", target="flag").model_dump()
{'name': None, 'kind': 'wave', 'target': 'flag'}
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### resolved(, strict=True)

This action as its registered model.

A typed instance is returned as is. A bare `ExtensionAction` is
validated by the model its kind registered — or, unregistered, raises
[`UnregisteredKindError`](an.genres.registry.html.md#an.genres.registry.UnregisteredKindError) (`strict`) or
comes back unchanged (`strict=False`).

* **Return type:**
  [`ExtensionAction`](#an.ir.schema.ExtensionAction)

### an.ir.schema.FRAME_COUPLINGS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('rigid', 'far')*

`rigid` takes the parent’s whole pose,
`far` only its rotation (what is at infinity turns with the camera and never
translates).

* **Type:**
  How a frame follows its parent

### an.ir.schema.FRAME_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'in'*

The key an element’s frame is written under in a document (`frame` is the
field; `in` is not a name Python lets a field have).

### *class* an.ir.schema.Frame(\*, parent='world', at=(0.0, 0.0, 0.0), look=(0.0, 0.0, 0.0), coupling='rigid', moving=None, sway=None, sockets=<factory>, \*\*extra_data)

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

#### sway *: [FrameSway](#an.ir.schema.FrameSway) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Lean of the members riding in it when it accelerates (off when unset).

### *class* an.ir.schema.FrameMoving(, direction=(0.0, 0.0, 1.0), speed, \*\*extra_data)

Bases: `_IRModel`

A frame translating at a constant velocity: sugar for a frame whose
`at` grows by `direction × speed` per second of FILM time.

```pycon
>>> FrameMoving(direction=(0.0, 0.0, 1.0), speed=20.0).speed
20.0
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.FrameSway(, gain=1.0, settle=0.0, gravity=9.81, limit=75.0, \*\*extra_data)

Bases: `_IRModel`

Opt-in sway of an accelerating frame (an#504): what rides in it leans
away from the acceleration by `gain × atan(a / gravity)` (the pseudo-force
of a non-inertial frame; follow-through and drag, in animation terms),
settling with the time constant `settle` seconds (`0`: at once).
Fields at their default are left out of a dump.

```pycon
>>> FrameSway().gain
1.0
>>> FrameSway().model_dump(), FrameSway(gain=0.5, settle=0.2).model_dump()
({}, {'gain': 0.5, 'settle': 0.2})
```

#### gravity *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Gravity in the frame’s units per second² (the world is in metres; a
frame drawn at another scale says its own): the lean is
`atan(a / gravity)`.

#### limit *: [float](https://docs.python.org/3/builtins/functions.html#float)*

a stop with no easing is an impulse,
and an impulse would flip it over for a frame.

* **Type:**
  The most a member leans, degrees

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.schema.GRAVITY_DIRECTIONS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]]* *= {'down': (0.0, 1.0), 'left': (-1.0, 0.0), 'right': (1.0, 0.0), 'up': (0.0, -1.0)}*

Where each named gravity direction pulls, on the stage’s y-down axes.

### an.ir.schema.JOINT_TYPES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('pin', 'hinge', 'weld', 'distance', 'string', 'rod', 'slide', 'contact')*

The joint types a scene declares. `string` (a distance held at most) and
`rod` (a distance held exactly) are the puppeteer’s names for a
`distance` with its `mode` set.

### *class* an.ir.schema.JointSpec(, type, a, b=None, end=None, limits=None, length=None, mode=None, give=0.0, name=None, \*\*extra_data)

Bases: `_IRModel`

A declared relation between two bodies (ADR 0008 decision 3).

```pycon
>>> JointSpec(type="hinge", a="lamp/upper", limits=(-40, 90)).id
'lamp/upper'
>>> JointSpec(type="pin", a="paul/fore_r@hand_r", b="wheel@grip", name="grip").id
'grip'
```

A **body** is a node path (`paul/fore_r`, or an entity id for an entity
with one root part), and a **point** on it follows `@`: a fraction of the
body’s extent (`@0.5,1`), or the name of a bone of its rig (`@hand_r`:
a bone with no slot is a landmark). With no `@` the point is the body’s
pivot for `a` and the centre of its extent for `b`. `world@x,y` is a
point of the stage, in scene px from its centre (`StagePlacement.at`’s
ruler).

- `pin`: the two points coincide; `hinge` adds an angle range
  (`limits`, degrees about the rest pose, `a`’s body relative to
  `b`’s); `weld` holds the rest angle too. A `hinge` or `weld` that
  names only `a` (a rig part) is that part’s own joint to its parent:
  its `limits` override the bone’s.
- `distance` keeps `length` (default: the distance at rest) per
  `mode`; `string` is a distance held at most, `rod` exactly.
- `slide` keeps `a` on the segment `b` to `end`; `contact` keeps
  it on the segment’s free side (above a left-to-right segment).

`give` is the joint’s softness (compliance, px per unit of pull; 0 is
rigid). `name` is what `join` and `unjoin` call it (default: `a`).
On an entity (`AssetRef.joints`) `a` is relative to the entity
(`fore_r@hand_r`, `@0.5,0`) and `b` is a path in the shot.

#### *property* distance_mode *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The mode of a distance-like joint (`equal` unless said or implied).

#### *property* id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

What `join` and `unjoin` call this joint.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.LoopAction(, name=None, kind='loop', child, count=1, \*\*extra_data)

Bases: `_ActionBase`

Composition: repeat `child` `count` times.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.Meta(\*, title='', author='', duration=0.0, fps=30, resolution=<factory>, default_renderer='cutout', notes='', step_hz=None, style_pack=None, default_easing=None, sounds=<factory>, captions=None, closing_transition=None, voice_loudness=None, \*\*extra_data)

Bases: `_IRModel`

Scene metadata.

#### captions *: [Captions](#an.ir.schema.Captions) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Captions from the dialogue’s word timings ([`Captions`](#an.ir.schema.Captions), an#175);
`None` — the default — is none, omitted from JSON like `style_pack`.

#### closing_transition *: [Transition](#an.ir.schema.Transition) | [None](https://docs.python.org/3/builtins/constants.html#None)*

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
  Like [`Shot.renderer`](#an.ir.schema.Shot.renderer)

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### sounds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SoundCue](#an.ir.schema.SoundCue)]*

Sound cues in FILM time — a music bed, an ambience under every shot
([`SoundCue`](#an.ir.schema.SoundCue)). Empty, the default, is no sound layer at all.

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

#### voice_loudness *: [VoiceLoudness](#an.ir.schema.VoiceLoudness) | [None](https://docs.python.org/3/builtins/constants.html#None)*

One loudness for every voice ([`VoiceLoudness`](#an.ir.schema.VoiceLoudness), an#315); `None`
— the default — levels nothing, and is omitted from JSON.

### an.ir.schema.NO_GRAVITY *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'none', 'off'})*

The spellings of no gravity.

### *class* an.ir.schema.Narration(, text, voice_ref=None, start=None, duration=None, viseme_track=None, word_timings=None, audio_ref=None, viseme_ref=None, \*\*extra_data)

Bases: `_IRModel`

Off-screen narration. Same shape as Dialogue minus the speaker pin.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.schema.PART_JOINT_TYPES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'hinge', 'weld'})*

a rig part’s own joint to its parent.

* **Type:**
  The types that may name only `a`

### *class* an.ir.schema.ParallelAction(\*, name=None, kind='parallel', children=<factory>, \*\*extra_data)

Bases: `_ActionBase`

Composition: run all children simultaneously starting at the same time.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.schema.Point3

the stage’s axes extended with depth — `x`
right, `y` DOWN, `z` away from the viewer. The unit is the author’s.

* **Type:**
  A world position `(x, y, z)`

alias of [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[`Annotated`[[`float`](https://docs.python.org/3/builtins/functions.html#float), FieldInfo(annotation=NoneType, required=True, metadata=[AllowInfNan(allow_inf_nan=False)])], `Annotated`[[`float`](https://docs.python.org/3/builtins/functions.html#float), FieldInfo(annotation=NoneType, required=True, metadata=[AllowInfNan(allow_inf_nan=False)])], `Annotated`[[`float`](https://docs.python.org/3/builtins/functions.html#float), FieldInfo(annotation=NoneType, required=True, metadata=[AllowInfNan(allow_inf_nan=False)])]]

### *class* an.ir.schema.Resolution(, width=1920, height=1080, \*\*extra_data)

Bases: `_IRModel`

Pixel dimensions of the rendered output.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.schema.SEGMENT_JOINT_TYPES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'contact', 'slide'})*

The types that join a point to a segment (`b` is its start, `end` its end).

### an.ir.schema.SHOT_SIZES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]]* *= {'close_up': (0.0, 0.35, 0.9), 'full': (0.0, 1.0, 0.9), 'medium': (0.0, 0.55, 0.9), 'wide': (0.0, 1.0, 0.5)}*

Shot sizes, by where the frame cuts the subject (the film convention, see
ADR 0009): `name: (top, bottom, fill)`. `top`/`bottom` are the band of
the subject’s box the frame shows, as fractions of its height from the top
(`0.35`: head and shoulders; `0.55`: the waist); `fill` is how much of
the frame’s height that band fills. A genre may later supply landmarks from
its rig (a seam, not built); until then these are human proportions.

### an.ir.schema.SPECIMEN_DURATION *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.5*

How long a specimen shot runs (`an library sheet` draws its first frame).

### an.ir.schema.SPECIMEN_SHOT_ID *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'specimen'*

The id of a specimen shot.

### an.ir.schema.STAGE_NODE_SPACE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'stage.node'*

The property space a 2D stage engine’s node lives in ([`an.timing.spaces`](an.timing.spaces.html.md#module-an.timing.spaces)).

### *class* an.ir.schema.SceneIR(\*, version='0.3.0', compatible_version='0.3.0', kind='SceneIR', meta=<factory>, assets=<factory>, timeline=<factory>, world=None, \*\*extra_data)

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

#### world *: [World](#an.ir.schema.World) | [None](https://docs.python.org/3/builtins/constants.html#None)*

its members at world positions, its
named viewpoints and its travel. `None` — the default, and every
document written before it existed — is no world at all: every shot is
placed by hand. Omitted from JSON when unset (the `stage` rule), so no
stored scene and no schema version moves.

* **Type:**
  The scene’s **world** (ADR 0009)

### *class* an.ir.schema.SequenceAction(\*, name=None, kind='sequence', children=<factory>, \*\*extra_data)

Bases: `_ActionBase`

Composition: run children one after the other.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.SetAction(, name=None, kind='set', target, property, value, at=0.0, \*\*extra_data)

Bases: `_ActionBase`

Set a property to a value at a specific time. Discrete, no tween.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.Shot(\*, id, renderer='cutout', duration=5.0, camera=None, entities=<factory>, actions=<factory>, dialogue=<factory>, narration=<factory>, options=<factory>, step_hz=None, transition=None, sounds=<factory>, policy=None, viewpoint=None, welds=<factory>, joints=<factory>, solve=None, \*\*extra_data)

Bases: `_IRModel`

A single rendered unit. A scene is a sequence of shots.

A shot’s `renderer` selects the backend that draws it. Every renderer must accept the
same Shot fields; renderer-specific options go under `options`.

#### joints *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[JointSpec](#an.ir.schema.JointSpec)]*

Joints between this shot’s bodies ([`JointSpec`](#an.ir.schema.JointSpec), ADR 0008); the
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

#### solve *: [SolveSettings](#an.ir.schema.SolveSettings) | [None](https://docs.python.org/3/builtins/constants.html#None)*

mode, gravity and
damping over the style pack’s. `None` (omitted): the defaults.

* **Type:**
  How this shot is solved ([`SolveSettings`](#an.ir.schema.SolveSettings))

#### sounds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SoundCue](#an.ir.schema.SoundCue)]*

Sound cues in SHOT-local time ([`SoundCue`](#an.ir.schema.SoundCue)).

#### step_hz *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per-shot override of [`Meta.step_hz`](#an.ir.schema.Meta.step_hz) (`None` = inherit).

#### transition *: [Transition](#an.ir.schema.Transition) | [None](https://docs.python.org/3/builtins/constants.html#None)*

How this shot is entered ([`Transition`](#an.ir.schema.Transition)); `None` is a hard cut.

#### viewpoint *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [Viewpoint](#an.ir.schema.Viewpoint) | [None](https://docs.python.org/3/builtins/constants.html#None)*

the name
of one of `world.viewpoints` or an inline [`Viewpoint`](#an.ir.schema.Viewpoint). `None`
(the default, and every document written before the world existed)
means the shot is placed by hand, as it always was. Omitted from JSON
when unset, like `policy`.

* **Type:**
  This shot’s **viewpoint** onto the scene’s world (ADR 0009)

#### welds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[Weld](#an.ir.schema.Weld)]*

Items held by something for a span ([`Weld`](#an.ir.schema.Weld)); omitted when empty.

### *class* an.ir.schema.SolveSettings(, mode=None, gravity=None, damping=None, iterations=None, substeps=None, ground=None, \*\*extra_data)

Bases: `_IRModel`

How a shot’s joints are solved: a per-shot override of the style pack’s
`gravity` and `damping`, and the solve’s mode and effort (ADR 0008
decision 4).

```pycon
>>> SolveSettings(gravity="down 500").gravity_vector()
(0.0, 500.0)
>>> SolveSettings(mode="pose").model_dump()
{'mode': 'pose'}
```

`mode` unset is `dynamic` when gravity or a string acts (follow-through,
baked from frame 0) and `pose` otherwise (projection to convergence from
the previous frame: dead still between keys). `gravity` unset is the
style pack’s; `"none"` switches the pack’s off for this shot.

`ground` is the floor line, a stage `y` (scene px from the stage
centre, down positive): where `place` puts an item `onto: ground`, a
`release` lands it, and an item `overrides: {held_by: ground}` rests
([`an.ir.holds`](an.ir.holds.html.md#module-an.ir.holds)). Unset, a hand puts things on the floor its body
stands on (the bottom of its rig’s root parts).

```pycon
>>> SolveSettings(ground=502).model_dump()
{'ground': 502.0}
```

#### gravity_vector()

This shot’s own gravity (`None` also when it says nothing).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.SoundCue(, sound, at=0.0, until=None, cause=None, duration=None, gain_db=0.0, loop=False, fade_in=0.0, fade_out=0.0, duck_db=None, duck_attack=0.08, duck_release=0.3, \*\*extra_data)

Bases: `_IRModel`

One sound placed on the timeline: an SFX hit, an ambience, a music bed.

`sound` is a key in the project’s `sounds` store (`an.sounds`), where
the bytes and their licence live — the IR never inlines audio.

`at` is seconds from the start of whatever holds the cue: a shot’s
`sounds` are SHOT-local (they move with the shot, across transitions
and re-orderings), `meta.sounds` are FILM time (a music bed under the
whole thing).

```pycon
>>> SoundCue(sound="hit", at=1.2).gain_db
0.0
>>> SoundCue(sound="bed", loop=True, duck_db=-12).duck_db
-12.0
```

#### at *: [Union](https://docs.python.org/3/library/typing.html#typing.Union)[[float](https://docs.python.org/3/builtins/functions.html#float), [CueAnchor](#an.ir.schema.CueAnchor)]*

Seconds, or a [`CueAnchor`](#an.ir.schema.CueAnchor) resolved from the picture when the film
is laid out (an#317).

#### cause *: [CueAnchor](#an.ir.schema.CueAnchor) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The visible event this sound is the sound OF, for a cue authored at a
time (`at` in seconds): the `causality` lint checks the sound does
not precede it and stays within the audio-visual window (catalogue B7).
A shot cue only; an anchored `at` already is its cause.

#### duck_db *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Attenuation, in dB, while any dialogue line plays; `None` never ducks.
A music bed usually wants `DEFAULT_DUCK_DB`; an SFX hit wants none.

#### duration *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

the asset’s own length, or — when
`loop` — to the end of its shot (shot cue) or of the film (meta cue).

* **Type:**
  How long it plays. `None`

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### until *: [CueUntil](#an.ir.schema.CueUntil) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Ends the cue at another cue’s start ([`CueUntil`](#an.ir.schema.CueUntil)), instead of a
fixed `duration`.

### *class* an.ir.schema.StagePlacement(, at=None, scale=1.0, after=None, \*\*extra_data)

Bases: `_IRModel`

Where an entity stands on the stage, and how big it is.

```pycon
>>> StagePlacement(at=(120.0, -40.0), scale=0.5).at
(120.0, -40.0)
>>> StagePlacement().at is None
True
```

`at` is in SCENE pixels relative to the stage centre — the same space the
compiler already places characters in — so an author reads it off the same
ruler as a camera pivot. `scale` multiplies the rig’s own uniform scale.

**\`after\` landed in an#344** (a studio set’s sky disc between a sky plane
and a holed wall plate): it names the anchor the entity is drawn right
after. `depth` is still not a field: an entity takes the depth of the plane
it is placed after. The paragraphs below are the record of why both were
deferred, kept because `depth`’s reason still holds.

\*\*Deliberately only two fields, and the reason has been re-stated because
the first one expired.\*\* #108 sketched `depth` and `after` as well, deferred
on the grounds that they belong to a stage vocabulary that had not arrived.
It arrived the same day: #109 landed the translating camera and #110 landed
plane environments, and nothing revisited this paragraph — a deferral citing
a *condition* outlives the condition silently, which is why the reason below
cites a state instead (an#126).

The current reason is simply that \*\*nothing reads them and nothing has asked
to.\*\* Shipping either now would put a knob in the schema that a scene can
set, that renders identically, and that says nothing — which is worse than
an absent one, and is the same defect `an.styles.UNREACHABLE_ROLES` refuses
by construction on the other side of the compiler.

What each would cost, so the next reader does not re-derive it:

- `depth` would place a prop on a parallax plane, which means parenting the
  prop into that plane’s subtree — and `_track_root_of` makes entity
  identity the first path segment, so every animation target on that prop
  changes shape.
- `after` would order a prop against planes, which is `characters_after`’s
  problem a second time; that one needed the environment and character
  builders interleaved before any ordering could be expressed at all.

Neither is hard. Both are unmotivated, and an unmotivated knob in a
versioned schema is a migration you owe later for a feature nobody used.

#### after *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

an environment
plane (`"set/skyline"`) or another placed entity (`"grid"`).
`None` = the default band, where the environment’s
`characters_after` cuts. A plane’s parallax carries an entity placed
after it; an entity placed after an entity rides the default depth.

* **Type:**
  What this entity is drawn immediately after (an#344)

#### at *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

`(x, y)` in scene pixels from the stage centre. `None` = default layout.

`allow_inf_nan=False` on both fields, and it is not pedantry: pydantic
serializes `inf` and `nan` to JSON **null**, and re-validating that JSON
raises — so a scene file written with either is corrupt one way, and the
author finds out on the next load rather than at the edit that did it
(an#108 review, M-1). `gt=0` already refuses `scale=0` and `scale=-1`; it
does not refuse `inf`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### scale *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Uniform scale multiplier on the built rig. `1.0` = the rig’s own size.

### *class* an.ir.schema.Stream(, id, ref, kind='prop', store='props', height=None, width=None, units_per_px=None, every, lane=0.0, y=0.0, after=None, seed=0, frame=None, \*\*extra_data)

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

### an.ir.schema.TRAVEL_PLATE_ROLES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('far', 'vehicle')*

at infinity, or rigid with
the vehicle the viewpoints are mounted on.

* **Type:**
  What a plane under a travel may be declared as

### *class* an.ir.schema.Transition(, kind='cut', duration=0.5, color='#000000', direction='left', time_jump=False, \*\*extra_data)

Bases: `_IRModel`

How a shot is ENTERED — from the previous shot, or (for the first shot)
from nothing.

```pycon
>>> Transition(kind="dissolve", duration=0.5).duration
0.5
>>> Transition(kind="fade").color
'#000000'
```

- `cut` — the default, and what a shot with no `transition` means.
- `fade` — through `color`: the previous shot’s last `duration / 2`
  fades to the colour and this shot’s first `duration / 2` fades up from
  it. On the FIRST shot the whole `duration` is a fade up from the
  colour. **Holds the film’s length**: nothing overlaps.
- `dissolve` — the previous shot’s last `duration` seconds and this
  shot’s first `duration` seconds are seen through each other. \*\*The
  film gets `duration` shorter\*\* than the sum of its shots: both shots
  play in full, overlapped (the editor’s convention — the overlapped
  seconds are each shot’s “handle”). Dialogue stays in sync with its own
  shot’s picture; audio from both shots is heard in the overlap. Not
  allowed on the first shot.
- `wipe` — overlaps like a dissolve, but a hard edge sweeps across the
  frame in `direction` (the way the edge travels: `left` brings this
  shot in from the right), this shot on the side it has passed (an#390).
  The edge stands where a dissolve’s mix would: `(j + 1) / (k + 1)` of
  the way across on overlap frame `j` of `k`. Not on the first shot.

#### direction *: [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)['left', 'right', 'up', 'down']*

A `wipe`’s direction; omitted from a dump for every other kind.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### time_jump *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

what is absent from the
shots before it is not missing, it left in the meantime. Omitted from a
dump unless set.

* **Type:**
  Time passes across this transition (catalogue C1)

### *class* an.ir.schema.Travel(\*, direction=(0.0, 0.0, 1.0), speed=None, near=0.5, far=60.0, tolerance_px=1.0, max_actions=20000, streams=<factory>, plates=<factory>, \*\*extra_data)

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

### *class* an.ir.schema.TweenAction(, name=None, kind='tween', target, property, to_value, from_value=None, duration=1.0, easing='ease_in_out', \*\*extra_data)

Bases: `_ActionBase`

Animate a property from a start value to an end value over a duration.

#### easing *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)] | [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

a
tween that does not name an easing takes the scene’s
[`Meta.default_easing`](#an.ir.schema.Meta.default_easing), and only when that is unset too the
built-in `"ease_in_out"` this default spells. “Unset” is
`"easing" not in model_fields_set` — the default stays the literal so
every reader of `.easing` still sees the curve a scene without a
default draws — and the serializer below omits an unset easing, so the
distinction survives `scene.json`. `None` is an explicit LINEAR
ramp (the evaluators’ reading of a null easing), not “unset”.

* **Type:**
  The curve. \*\*Unset is not the same as 

  ```
  ``
  ```

  ”ease_in_out”

  ```
  ``
  ```

  \*\* (an#166)

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### resolved_easing(default=None)

The easing this tween draws with under a scene default of
`default` — the ONE statement of the precedence \*\*tween > scene
(`Meta.default_easing`) > built-in 

```
``
```

”ease_in_out”

```
``
```

\*\* (an#166).

```pycon
>>> TweenAction(target="a", property="x", to_value=1).resolved_easing("linear")
'linear'
>>> TweenAction(target="a", property="x", to_value=1, easing="ease_in_out").resolved_easing("linear")
'ease_in_out'
>>> TweenAction(target="a", property="x", to_value=1).resolved_easing(None)
'ease_in_out'
```

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.ir.schema.VEHICLE_FRAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'vehicle'*

The frame a `travel` with a `speed` is sugar for (viewpoints and members
ride it by default; streams stay in the world).

### *class* an.ir.schema.Viewpoint(\*, at=None, look=(0.0, 0.0, 0.0), look_at=None, vanish=None, fov=None, focal=None, subject=None, size=None, distance=None, subject_at=(0.0, 0.0), hide=<factory>, frame=None, \*\*extra_data)

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

### *class* an.ir.schema.VisemeKeyframe(, time, viseme, \*\*extra_data)

Bases: `_IRModel`

A single mouth-shape keyframe in a viseme track.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.VisemeTrack(\*, fps_hint=None, keyframes=<factory>, \*\*extra_data)

Bases: `_IRModel`

Aligned viseme track produced by the lip-sync stage. Optional in P1.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.VoiceLoudness(, target_lufs=-16.0, peak_db=-1.5, \*\*extra_data)

Bases: `_IRModel`

One loudness for every voice of the film (an#315).

TTS voices arrive at very different levels (a 19 dB spread measured on one
episode). Set, the render levels each voice: its integrated loudness over
ALL its lines (EBU R128), one gain to `target_lufs` (plus the voice
document’s `loudness_offset_db`), peaks held at `peak_db` dBFS by a
lookahead limiter — derived audio, content-keyed, never re-synthesised
([`an.audio.loudness`](an.audio.loudness.html.md#module-an.audio.loudness)). Unset, the default, levels nothing.

```pycon
>>> VoiceLoudness().target_lufs, VoiceLoudness().peak_db
(-16.0, -1.5)
>>> VoiceLoudness.model_validate(-20).target_lufs  # a bare number is the target
-20.0
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### peak_db *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The highest a sample may reach after the gain, dBFS.

#### target_lufs *: [float](https://docs.python.org/3/builtins/functions.html#float)*

speech for the web;
-23: EBU R128 broadcast).

* **Type:**
  The level every voice is brought to, LUFS (-16

### an.ir.schema.WORLD_FRAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'world'*

the world itself. Always present, never declared.

* **Type:**
  The root of the frame tree

### *class* an.ir.schema.Weld(, item, by, start=0.0, until=None, offset=None, \*\*extra_data)

Bases: `_IRModel`

A held item: `item` stays at `offset` from `by` between `start` and
`until` (catalogue A4). Pick-up is `start`, release is `until`.

```pycon
>>> Weld(item="cup", by="paul/hand_r", start=1.0, until=3.0).by
'paul/hand_r'
```

`by` is a node path (an entity, or a bone of it) and `item` an entity id,
both in the shot. `offset` is where the item’s centre sits from the carrier’s
centre, in scene px; without it, the offset the two have at `start` is the
one that must hold. `until` `None` is the end of the shot. A declaration
only: a lint reads it, nothing is composed from it.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.WordTimingIR(, text, start, end, \*\*extra_data)

Bases: `_IRModel`

One word of a line and when it was spoken, in seconds from the line’s
start (like [`VisemeKeyframe`](#an.ir.schema.VisemeKeyframe), never absolute). Stamped by the audio
pipeline from the provider’s word timings when it has them (an#96); JSON
only — `scene.md` never carries it, the way it never carries visemes.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.World(\*, members=<factory>, viewpoints=<factory>, travel=None, frames=<factory>, \*\*extra_data)

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
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Frame`](#an.ir.schema.Frame)]

#### default_frame()

The frame a member or viewpoint is in when it names none: the
travel’s `vehicle` (members ride it) when there is one, else the world.

```pycon
>>> World().default_frame(), World(travel=Travel(speed=1.0)).default_frame()
('world', 'vehicle')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### frames *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Frame](#an.ir.schema.Frame)]*

The frames of reference, `{name: Frame}`; `world` is the implicit
root and a travel with a `speed` adds `vehicle`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.WorldMember(\*, kind, id, store, ref, overrides=None, stage=None, library=None, joints=<factory>, at=None, height=None, width=None, units_per_px=None, attached=None, after=None, frame=None, planes=None, \*\*extra_data)

Bases: [`AssetRef`](#an.ir.schema.AssetRef)

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

#### frame *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The frame of reference this member is in (document key `in`); unset
means the world’s default frame ([`World.default_frame()`](#an.ir.schema.World.default_frame)). An
environment’s `frame` is the default of its planes; `planes` names
the exceptions, `{plane name: frame}` (one environment can hold a
cabin plate and a sky plate).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.schema.gravity_vector(spec)

The acceleration a gravity declaration means, or `None` for none.

`spec` is how a style pack or a shot spells it: `"down 980"`, `"down"`
([`DFLT_GRAVITY`](#an.ir.schema.DFLT_GRAVITY)), `"none"`, a number (down at that strength), or a
mapping `{strength, direction}` (the shape the `gravity` lint reads).

```pycon
>>> gravity_vector("down 500"), gravity_vector("none"), gravity_vector(None)
((0.0, 500.0), None, None)
>>> gravity_vector({"direction": "left"})
(-980.0, 0.0)
>>> gravity_vector("sideways")
Traceback (most recent call last):
...
ValueError: gravity 'sideways': say a direction (down, up, left, right) and an optional strength in px/s², e.g. 'down 980', or 'none'
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.ir.schema.resolve_step_hz(shot, scene_step_hz)

The stepped-timing policy `shot` renders under: its own `step_hz`
when it declares one, else the scene’s, else `None` (smooth). The ONE
statement of the shot-over-scene rule — the cutout renderer, the preview
and the project renderer all call it (an#89 review: three copies).

```pycon
>>> resolve_step_hz(Shot(id="s", step_hz=10.0), 15.0)
10.0
>>> resolve_step_hz(Shot(id="s"), 15.0)
15.0
>>> resolve_step_hz(Shot(id="s"), None) is None
True
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.ir.schema.stage_specimen(ref)

A short shot showing the one stage entity `ref` casts, on its own (an#347).

```pycon
>>> stage_specimen(AssetRef(kind="prop", id="lamp", store="props", ref="lamp")).entities[0].id
'lamp'
```

* **Return type:**
  [`Shot`](#an.ir.schema.Shot)

### an.ir.schema.unregistered_action_kind(kind, , where='')

The error for an action `kind` no loaded genre registered.

It names the installed genres whose declaration provides the kind, read
without loading them ([`an.genres.providers_of()`](an.genres.html.md#an.genres.providers_of)).

* **Return type:**
  [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)
