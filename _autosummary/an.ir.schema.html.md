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

| [`DFLT_EXPRESSION_BLEND_S`](#an.ir.schema.DFLT_EXPRESSION_BLEND_S)   | Default ramp in/out of an expression, seconds (0 = cut).                                                                                                                   |
|----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`CORE_ACTION_KINDS`](#an.ir.schema.CORE_ACTION_KINDS)         | The `kind` of every action the core defines (the static union members).                                                                                                    |
| [`EXTENSION_TAG`](#an.ir.schema.EXTENSION_TAG)             | The union tag of the open member.                                                                                                                                          |
| [`Action`](#an.ir.schema.Action)                    | the core kinds plus [`ExtensionAction`](#an.ir.schema.ExtensionAction) for any other `kind` (a registered genre kind validates to its own model through it). |
| [`DEFAULT_CAPTION_MAX_CHARS`](#an.ir.schema.DEFAULT_CAPTION_MAX_CHARS) | the broadcast convention (BBC / Netflix timed-text guidance: 42 characters, two lines).                                                                                    |
| [`DEFAULT_CAPTION_SIZE`](#an.ir.schema.DEFAULT_CAPTION_SIZE)      | Caption type size as a fraction of frame height — a little under the title default, as captions are read while something else is watched.                                  |
| [`STAGE_NODE_SPACE`](#an.ir.schema.STAGE_NODE_SPACE)          | The property space a 2D stage engine's node lives in ([`an.timing.spaces`](an.timing.spaces.html.md#module-an.timing.spaces)).                          |

### Functions

| [`resolve_step_hz`](#an.ir.schema.resolve_step_hz)(shot, scene_step_hz)        | The stepped-timing policy `shot` renders under: its own `step_hz` when it declares one, else the scene's, else `None` (smooth).   |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| [`unregistered_action_kind`](#an.ir.schema.unregistered_action_kind)(kind, \*[, where]) | The error for an action `kind` no loaded genre registered.                                                                        |

### Classes

| [`AssetRef`](#an.ir.schema.AssetRef)(\*\*data)         | Reference to an entry in a project store.                                                                                                                           |
|-----------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Camera`](#an.ir.schema.Camera)(\*\*data)           | Camera state for a shot: a named move, or explicit keys.                                                                                                            |
| [`CameraKey`](#an.ir.schema.CameraKey)(\*\*data)        | One camera pose at one time — the explicit door behind the named moves.                                                                                             |
| [`Captions`](#an.ir.schema.Captions)(\*\*data)         | Captions for the whole film, built from the dialogue's word timings.                                                                                                |
| [`DelayAction`](#an.ir.schema.DelayAction)(\*\*data)      | Composition: an empty span that consumes time.                                                                                                                      |
| [`Dialogue`](#an.ir.schema.Dialogue)(\*\*data)         | One line of spoken dialogue.                                                                                                                                        |
| [`ExpressionAction`](#an.ir.schema.ExpressionAction)(\*\*data) | Hold a facial expression on an entity (an#98, epic #9 Wave 6).                                                                                                      |
| [`ExtensionAction`](#an.ir.schema.ExtensionAction)(\*\*data)  | An action of a kind the core does not define: the IR's one open member.                                                                                             |
| [`LoopAction`](#an.ir.schema.LoopAction)(\*\*data)       | Composition: repeat `child` `count` times.                                                                                                                          |
| [`Meta`](#an.ir.schema.Meta)(\*\*data)             | Scene metadata.                                                                                                                                                     |
| [`Narration`](#an.ir.schema.Narration)(\*\*data)        | Off-screen narration.                                                                                                                                               |
| [`ParallelAction`](#an.ir.schema.ParallelAction)(\*\*data)   | Composition: run all children simultaneously starting at the same time.                                                                                             |
| [`PlayAction`](#an.ir.schema.PlayAction)(\*\*data)       | Play a named animation of the target entity's descriptor (an#7).                                                                                                    |
| [`Resolution`](#an.ir.schema.Resolution)(\*\*data)       | Pixel dimensions of the rendered output.                                                                                                                            |
| [`SceneIR`](#an.ir.schema.SceneIR)(\*\*data)          | Top-level Scene IR document.                                                                                                                                        |
| [`SequenceAction`](#an.ir.schema.SequenceAction)(\*\*data)   | Composition: run children one after the other.                                                                                                                      |
| [`SetAction`](#an.ir.schema.SetAction)(\*\*data)        | Set a property to a value at a specific time.                                                                                                                       |
| [`Shot`](#an.ir.schema.Shot)(\*\*data)             | A single rendered unit.                                                                                                                                             |
| [`SoundCue`](#an.ir.schema.SoundCue)(\*\*data)         | One sound placed on the timeline: an SFX hit, an ambience, a music bed.                                                                                             |
| [`StagePlacement`](#an.ir.schema.StagePlacement)(\*\*data)   | Where an entity stands on the stage, and how big it is.                                                                                                             |
| [`Transition`](#an.ir.schema.Transition)(\*\*data)       | How a shot is ENTERED — from the previous shot, or (for the first shot) from nothing.                                                                               |
| [`TweenAction`](#an.ir.schema.TweenAction)(\*\*data)      | Animate a property from a start value to an end value over a duration.                                                                                              |
| [`VisemeKeyframe`](#an.ir.schema.VisemeKeyframe)(\*\*data)   | A single mouth-shape keyframe in a viseme track.                                                                                                                    |
| [`VisemeTrack`](#an.ir.schema.VisemeTrack)(\*\*data)      | Aligned viseme track produced by the lip-sync stage.                                                                                                                |
| [`WordTimingIR`](#an.ir.schema.WordTimingIR)(\*\*data)     | One word of a line and when it was spoken, in seconds from the line's start (like [`VisemeKeyframe`](#an.ir.schema.VisemeKeyframe), never absolute). |

### an.ir.schema.Action

the core kinds plus [`ExtensionAction`](#an.ir.schema.ExtensionAction) for any other
`kind` (a registered genre kind validates to its own model through it).
`SerializeAsAny` makes a typed genre instance (a `PlayAction`) serialize
with its own fields rather than the open member’s.

* **Type:**
  Every action

alias of `Annotated`[`Annotated`[[`SetAction`](#an.ir.schema.SetAction), `Tag`(tag=set)] | `Annotated`[[`TweenAction`](#an.ir.schema.TweenAction), `Tag`(tag=tween)] | `Annotated`[[`SequenceAction`](#an.ir.schema.SequenceAction), `Tag`(tag=sequence)] | `Annotated`[[`ParallelAction`](#an.ir.schema.ParallelAction), `Tag`(tag=parallel)] | `Annotated`[[`DelayAction`](#an.ir.schema.DelayAction), `Tag`(tag=delay)] | `Annotated`[[`LoopAction`](#an.ir.schema.LoopAction), `Tag`(tag=loop)] | `Annotated`[[`ExtensionAction`](#an.ir.schema.ExtensionAction), `SerializeAsAny`(), `Tag`(tag=extension)], `Discriminator`(discriminator=`_action_tag`, custom_error_type=[`None`](https://docs.python.org/3/builtins/constants.html#None), custom_error_message=[`None`](https://docs.python.org/3/builtins/constants.html#None), custom_error_context=[`None`](https://docs.python.org/3/builtins/constants.html#None))]

### *class* an.ir.schema.AssetRef(\*\*data)

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

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### stage *: [StagePlacement](#an.ir.schema.StagePlacement) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Where on the stage this entity stands. `None` — the default and what
every existing document has — means “wherever the layout puts it”,
which for characters is the evenly-spaced row the compiler computes.

**Additive by construction, and hash-free by construction**: the
contract hashes the COMPILED document, and an `AssetRef` never reaches
it. So this field can grow without retiring a single ledger row.

### an.ir.schema.CORE_ACTION_KINDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('set', 'tween', 'sequence', 'parallel', 'delay', 'loop')*

The `kind` of every action the core defines (the static union members).

### *class* an.ir.schema.Camera(\*\*data)

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

#### keys *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[CameraKey](#an.ir.schema.CameraKey)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The explicit door. `None` = use `move`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### move *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

A named preset — sugar for `keys`. The cutout renderer’s vocabulary is
`an.adapters.cutout.compile.CAMERA_MOVES`; validate and the compiler are
pinned to the same table by test, because a move that validates and then
raises is the failure `_check_renderable` exists to prevent.

### *class* an.ir.schema.CameraKey(\*\*data)

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

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### rotation *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Camera roll, radians.

#### x *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Camera position in scene pixels. `+x` moves the camera right.

#### zoom *: [float](https://docs.python.org/3/builtins/functions.html#float)*

On-screen magnification. Must be > 0 — a zero or negative zoom is not a
camera, and the compiler would emit a degenerate root scale.

### *class* an.ir.schema.Captions(\*\*data)

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

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### strict *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

A line with no word timings is captioned with its words spread evenly
over its duration, with a warning; `strict` makes that an error.

### an.ir.schema.DEFAULT_CAPTION_MAX_CHARS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 42*

the broadcast
convention (BBC / Netflix timed-text guidance: 42 characters, two lines).

* **Type:**
  Characters per caption line and lines per caption page

### an.ir.schema.DEFAULT_CAPTION_SIZE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.05*

Caption type size as a fraction of frame height — a little under the title
default, as captions are read while something else is watched.

### an.ir.schema.DFLT_EXPRESSION_BLEND_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.15*

Default ramp in/out of an expression, seconds (0 = cut). The dialogue
`[emotion]` sugar uses its own in `an.expression.provider`.

### *class* an.ir.schema.DelayAction(\*\*data)

Bases: `_ActionBase`

Composition: an empty span that consumes time.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.Dialogue(\*\*data)

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

#### word_timings *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[WordTimingIR](#an.ir.schema.WordTimingIR)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

The provider’s word timings, line-relative; `None` when the provider
has none (offline, Rhubarb) or the line was stamped before an#96.

### an.ir.schema.EXTENSION_TAG *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'extension'*

The union tag of the open member.

### *class* an.ir.schema.ExpressionAction(\*\*data)

Bases: [`ExtensionAction`](#an.ir.schema.ExtensionAction)

Hold a facial expression on an entity (an#98, epic #9 Wave 6).

`preset` names one of `an.expression.presets.PRESETS`; `axes`
are per-axis overrides layered on it (axis units, see
[`an.expression.axes`](an.expression.axes.html.md#module-an.expression.axes)); `None` + no axes is a cheap “return to
rest”. `duration=None` runs to the shot end (the looping-play rule) and
is **zero-width in a sequence**, like a looping `play`. `blend` ramps the
intensity in and out; two overlapping expressions cross-fade because the
face solver sums offsets. The dialogue `speaker [emotion]: …` bracket is
sugar for one of these over the line, desugared in memory only.

A leaf action, flattened like `play`: the compiler resolves it in the
face solver (one channel per `(node, property)`), never per action.

The ramp is a min over the two ends, so a span shorter than `2·blend`
never reaches full intensity (a 0.2 s expression at the default 0.15 s
blend peaks at 0.67) and a `duration=0` expression shows only where a
frame lands on it with `blend=0` — cut the blend for a flash.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.ExtensionAction(\*\*data)

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

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### resolved(, strict=True)

This action as its registered model.

A typed instance is returned as is. A bare `ExtensionAction` is
validated by the model its kind registered — or, unregistered, raises
[`UnregisteredKindError`](an.genres.registry.html.md#an.genres.registry.UnregisteredKindError) (`strict`) or
comes back unchanged (`strict=False`).

* **Return type:**
  [`ExtensionAction`](#an.ir.schema.ExtensionAction)

### *class* an.ir.schema.LoopAction(\*\*data)

Bases: `_ActionBase`

Composition: repeat `child` `count` times.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.Meta(\*\*data)

Bases: `_IRModel`

Scene metadata.

#### captions *: [Captions](#an.ir.schema.Captions) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Captions from the dialogue’s word timings ([`Captions`](#an.ir.schema.Captions), an#175);
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
  Like [`Shot.renderer`](#an.ir.schema.Shot.renderer)

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

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

### *class* an.ir.schema.Narration(\*\*data)

Bases: `_IRModel`

Off-screen narration. Same shape as Dialogue minus the speaker pin.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.ParallelAction(\*\*data)

Bases: `_ActionBase`

Composition: run all children simultaneously starting at the same time.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.PlayAction(\*\*data)

Bases: [`ExtensionAction`](#an.ir.schema.ExtensionAction)

Play a named animation of the target entity’s descriptor (an#7).

`animation` names an entry of `CharacterDescriptor.animations` (the
seeded `idle_breath` and `blink`, or anything an author adds); the
compiler resolves its tracks into channels on the entity’s nodes. A name
the descriptor does NOT declare — or any name on an entity with no
descriptor (a procedural rig, a prop) — falls back to the motion presets
of [`an.motion.PRESETS`](an.motion.html.md#an.motion.PRESETS) (`hop`, `nod`, …), which expand to
ordinary tweens at the target’s built rest pose; a descriptor animation of
the same name wins (an#166). Both halves are decided by
[`an.characters.play.play_problems()`](an.characters.play.html.md#an.characters.play.play_problems), the one resolver `an validate`
and the compiler share. For a preset, `args` are its parameters,
`duration` stretches the whole move to that length, `speed` divides
it, and `loop: true` is refused (a preset is a one-shot).
`duration` widens/narrows the placement window; `None` means the
animation’s own duration — or, when the resolved `loop` is true, the
rest of the shot, because a loop bounded by its own natural duration
never loops. `loop` overrides the animation’s declared `loop`
(`None` = use the descriptor’s). Inside a `sequence` a play with
`duration=None` occupies its NATURAL length — a motion preset’s own
length, a non-looping descriptor animation’s `duration`, both over
`speed` — so the next sibling starts when it ends; a looping one runs to
the shot end and occupies ZERO (`an.characters.play.play_extent()`).

#### args *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Parameters of a MOTION PRESET (an#166) — `{"height": 30}` for a
`hop` — passed to its [`an.motion.PRESETS`](an.motion.html.md#an.motion.PRESETS) function as keyword
arguments. `None` (the default, omitted from JSON) means the preset’s
own defaults. A descriptor animation takes none, and one given to it is
refused; `rest` is never one — it is read off the built scene.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.Resolution(\*\*data)

Bases: `_IRModel`

Pixel dimensions of the rendered output.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.schema.STAGE_NODE_SPACE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'stage.node'*

The property space a 2D stage engine’s node lives in ([`an.timing.spaces`](an.timing.spaces.html.md#module-an.timing.spaces)).

### *class* an.ir.schema.SceneIR(\*\*data)

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

### *class* an.ir.schema.SequenceAction(\*\*data)

Bases: `_ActionBase`

Composition: run children one after the other.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.SetAction(\*\*data)

Bases: `_ActionBase`

Set a property to a value at a specific time. Discrete, no tween.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.Shot(\*\*data)

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

#### sounds *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SoundCue](#an.ir.schema.SoundCue)]*

Sound cues in SHOT-local time ([`SoundCue`](#an.ir.schema.SoundCue)).

#### step_hz *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per-shot override of [`Meta.step_hz`](#an.ir.schema.Meta.step_hz) (`None` = inherit).

#### transition *: [Transition](#an.ir.schema.Transition) | [None](https://docs.python.org/3/builtins/constants.html#None)*

How this shot is entered ([`Transition`](#an.ir.schema.Transition)); `None` is a hard cut.

### *class* an.ir.schema.SoundCue(\*\*data)

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

#### duck_db *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Attenuation, in dB, while any dialogue line plays; `None` never ducks.
A music bed usually wants `DEFAULT_DUCK_DB`; an SFX hit wants none.

#### duration *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

the asset’s own length, or — when
`loop` — to the end of its shot (shot cue) or of the film (meta cue).

* **Type:**
  How long it plays. `None`

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.StagePlacement(\*\*data)

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

#### at *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[float](https://docs.python.org/3/builtins/functions.html#float), FieldInfo(annotation=NoneType, required=True, metadata=[\_PydanticGeneralMetadata(allow_inf_nan=False)])], [Annotated](https://docs.python.org/3/library/typing.html#typing.Annotated)[[float](https://docs.python.org/3/builtins/functions.html#float), FieldInfo(annotation=NoneType, required=True, metadata=[\_PydanticGeneralMetadata(allow_inf_nan=False)])]] | [None](https://docs.python.org/3/builtins/constants.html#None)*

`(x, y)` in scene pixels from the stage centre. `None` = default layout.

`allow_inf_nan=False` on both fields, and it is not pedantry: pydantic
serializes `inf` and `nan` to JSON **null**, and re-validating that JSON
raises — so a scene file written with either is corrupt one way, and the
author finds out on the next load rather than at the edit that did it
(an#108 review, M-1). `gt=0` already refuses `scale=0` and `scale=-1`; it
does not refuse `inf`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### scale *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Uniform scale multiplier on the built rig. `1.0` = the rig’s own size.

### *class* an.ir.schema.Transition(\*\*data)

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

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.TweenAction(\*\*data)

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

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

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

### *class* an.ir.schema.VisemeKeyframe(\*\*data)

Bases: `_IRModel`

A single mouth-shape keyframe in a viseme track.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.VisemeTrack(\*\*data)

Bases: `_IRModel`

Aligned viseme track produced by the lip-sync stage. Optional in P1.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.schema.WordTimingIR(\*\*data)

Bases: `_IRModel`

One word of a line and when it was spoken, in seconds from the line’s
start (like [`VisemeKeyframe`](#an.ir.schema.VisemeKeyframe), never absolute). Stamped by the audio
pipeline from the provider’s word timings when it has them (an#96); JSON
only — `scene.md` never carries it, the way it never carries visemes.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.schema.resolve_step_hz(shot, scene_step_hz)

The stepped-timing policy `shot` renders under: its own `step_hz`
when it declares one, else the scene’s, else `None` (smooth). The ONE
statement of the shot-over-scene rule — the cutout renderer, the preview
and the project renderer all call it (an#89 review: three copies).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> resolve_step_hz(Shot(id="s", step_hz=10.0), 15.0)
10.0
>>> resolve_step_hz(Shot(id="s"), 15.0)
15.0
>>> resolve_step_hz(Shot(id="s"), None) is None
True
```

### an.ir.schema.unregistered_action_kind(kind, , where='')

The error for an action `kind` no loaded genre registered.

It names the installed genres whose declaration provides the kind, read
without loading them ([`an.genres.providers_of()`](an.genres.html.md#an.genres.providers_of)).

* **Return type:**
  [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)
