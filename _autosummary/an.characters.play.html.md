# an.characters.play

Resolve a `play` against a character descriptor — the renderer-free half (an#7).

A [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction) names a descriptor animation. Its tracks
speak the DESCRIPTOR’s vocabulary — bones, slots, attachment names, view-box
units, degrees — while the renderer’s channels speak the SCENE’s: node paths,
swap-set keys, scene pixels, radians. This module does everything on the
descriptor side of that line and knows no renderer, so that `an validate`
and the cutout compiler share ONE verdict on whether a play can resolve. The
compiler used to decide alone, and validate passed plays that compile then
refused — four measured cases: an unknown bone property, a bone with no slot
of its own, a frame naming art that is not on disk, and a slot suppressed by
`face_overlay=false` (an#7 review).

Every rule mirrors a rig-builder fact, and the builder imports the shared
helpers rather than restating them, so the two cannot drift:

- A bone track animates the node of the bone’s **primary slot** — the slot
  named like the bone ([`primary_slot_per_bone()`](#an.characters.play.primary_slot_per_bone)); `bone:root.*`
  animates the entity container. A bone with no primary slot is a resolution
  error that *says so*: the old message (“no node of that name was built”)
  named the symptom and left the rule for the author to guess.
- A slot track resolves to exactly **one** swap set: the set whose keys name
  every frame’s attachment. Resolving frame-by-frame used to split a track
  across two channels; the runtime applies a pose’s properties in name order,
  so `blink` never closed once a second set that sorted before `eyelid`
  also named `open`. Two candidates is an error naming both.
- Art is consulted when the caller can consult it (`art_exists`): a frame
  whose attachment is declared but not on disk is reported as exactly that,
  not as “no set resolves it”.

```pycon
>>> from an.characters.schema import CharacterDescriptor
>>> desc = CharacterDescriptor(name="maya")
>>> resolved = resolve_play(desc, "blink")
>>> [(t.slot, t.set_name) for t in resolved.tracks]
[('left_eye', 'eyelid'), ('right_eye', 'eyelid')]
```

**Motion presets (an#166).** A name the descriptor does not declare — or any
name on an entity with no descriptor (a procedural rig, a prop) — falls back
to [`an.motion.PRESETS`](an.motion.html.md#an.motion.PRESETS). The DESCRIPTOR WINS a name both know: a rig that
ships its own `hop` means that one. [`play_source()`](#an.characters.play.play_source) makes that call and
[`play_problems()`](#an.characters.play.play_problems) gives the whole verdict, for `an validate` and the
compiler alike. A preset resolves to tweens, not a clip:
[`expand_preset_play()`](#an.characters.play.expand_preset_play) builds them at the moved node’s pose, which the
caller reads off the built scene and the timeline before the play (an#212),
so an author never passes `rest`.

```pycon
>>> play_problems(desc, "moonwalk")
["no animation 'moonwalk': the descriptor declares ['blink', 'idle_breath'] and no
  motion preset has that name (presets: ['hop', 'nod', 'point', 'pop_in',
  'shake', 'slide_in', 'slide_out', 'squash_stretch', 'turn', 'waddle', 'walk'])"]
>>> play_source(desc, "hop"), play_source(None, "hop"), play_source(desc, "blink")
('preset', 'preset', 'descriptor')
```

### Module Attributes

| [`BONE_TRACK_PROPERTIES`](#an.characters.play.BONE_TRACK_PROPERTIES)   | Descriptor bone-track properties → `(runtime property, unit factor)`.                                                               |
|--------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| [`RIG_SCALED_PROPERTIES`](#an.characters.play.RIG_SCALED_PROPERTIES)   | Bone-track properties whose values are view-box LENGTHS, so a renderer scales them by the rig's view-box → scene-pixel factor.      |
| [`ROOT_BONE`](#an.characters.play.ROOT_BONE)               | a track on it animates the entity's container node rather than any slot.                                                            |
| [`HEAD_BONE`](#an.characters.play.HEAD_BONE)               | The bone whose primary slot's nested slots are the FACE — what `face_overlay=false` suppresses.                                     |
| [`DESCRIPTOR_SOURCE`](#an.characters.play.DESCRIPTOR_SOURCE)       | the entity descriptor's own `animations`…                                                                                           |
| [`PRESET_SOURCE`](#an.characters.play.PRESET_SOURCE)           | …or, for a name it does not declare, [`an.motion.PRESETS`](an.motion.html.md#an.motion.PRESETS) (an#166). |
| [`RESERVED_PRESET_ARGS`](#an.characters.play.RESERVED_PRESET_ARGS)    | the target is the play's own, and the rest pose is read off the built scene.                                                        |
| [`TURN_PRESET`](#an.characters.play.TURN_PRESET)             | a turn opens from the side the character faces NOW, which only the timeline knows.                                                  |

### Functions

| [`active_skin`](#an.characters.play.active_skin)(desc)                                | The skin the rig draws: `default`, else the first declared, else empty.                                                                                                                                                                                                                                                                                                |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`art_exists_for`](#an.characters.play.art_exists_for)(characters_store, ref)            | `rel_path -> is the art on disk`, for a character in a filesystem store; `None` when the store has no root to look under (a dict, a fake) — a store that can answer nothing must assume presence, not absence, exactly as the rig builder's part probe does.                                                                                                           |
| [`drawn_attachment`](#an.characters.play.drawn_attachment)(desc, skin, slot)               | The `(name, attachment)` a slot draws by default, or `None`.                                                                                                                                                                                                                                                                                                           |
| [`expand_preset_play`](#an.characters.play.expand_preset_play)(action, \*, start, rest_of)   | A preset `play` as the flat tweens and settling `set``s it stands for, at absolute times from ``start` (an#166).                                                                                                                                                                                                                                                       |
| [`facing_at`](#an.characters.play.facing_at)(events, entity, t, \*[, view_set])     | What `entity` shows at time `t`: the latest `view_set` swap set on the entity and the sign of the latest `scale_x` it was given, at or before `t` (a tween counts from its END, when its value has landed; at one instant the one LATER in `events` wins — so pass them in authoring order, as [`resolve_turns()`](#an.characters.play.resolve_turns) does). |
| [`play_problems`](#an.characters.play.play_problems)(desc, animation, \*[, ...])        | Every reason `play(<entity>, animation, ...)` cannot resolve — empty when it can.                                                                                                                                                                                                                                                                                      |
| [`play_source`](#an.characters.play.play_source)(desc, animation)                     | Which library a `play` of `animation` resolves in — [`DESCRIPTOR_SOURCE`](#an.characters.play.DESCRIPTOR_SOURCE) when `desc` declares it (the descriptor WINS a name a preset also has), else [`PRESET_SOURCE`](#an.characters.play.PRESET_SOURCE) when a motion preset has it.                                                                        |
| [`preset_moved_node`](#an.characters.play.preset_moved_node)(action_target, animation)      | The ONE node path a preset play moves — `<target>/head` for a `nod`, the target itself for the rest.                                                                                                                                                                                                                                                                   |
| [`preset_moved_nodes`](#an.characters.play.preset_moved_nodes)(action_target, animation)     | Every node path a preset play moves.                                                                                                                                                                                                                                                                                                                                   |
| [`preset_takes`](#an.characters.play.preset_takes)(animation, name)                    | Whether the motion preset `animation` has the keyword `name`.                                                                                                                                                                                                                                                                                                          |
| [`preset_play_span`](#an.characters.play.preset_play_span)(action)                         | How long a preset `play` runs, in seconds: its `duration` when set, else the preset's natural length divided by `speed`.                                                                                                                                                                                                                                               |
| [`preset_problems`](#an.characters.play.preset_problems)(animation, \*[, args, ...])      | Why a `play` of the motion preset `animation` cannot expand.                                                                                                                                                                                                                                                                                                           |
| [`primary_slot_per_bone`](#an.characters.play.primary_slot_per_bone)(desc)                      | `{bone name: the slot that IS that bone}`, when one exists.                                                                                                                                                                                                                                                                                                            |
| [`resolve_play`](#an.characters.play.resolve_play)(desc, animation, \*[, art_exists])  | Resolve `animation` of `desc` into renderer-ready tracks, or raise [`PlayResolutionError`](#an.characters.play.PlayResolutionError) listing every problem found.                                                                                                                                                                                                   |
| [`resolve_turns`](#an.characters.play.resolve_turns)(flat_list, \*, descriptor_of, ...) | Fill in each turn's `from_direction` from the timeline before it (an#203): a `play` of `turn` on an entity that does not pass one opens from the side the latest earlier `scale_x` left the entity facing — so `side` (`direction: left`) then `back` is two plays, with no `from_direction` by hand.                                                                  |
| [`sampled_deviations`](#an.characters.play.sampled_deviations)(track, duration, fps)         | `(time, deviation)` pairs for a sine bone track at the frame rate — [`an.characters.idle.evaluate_track()`](an.characters.idle.html.md#an.characters.idle.evaluate_track)'s formula, sampled, so the descriptor's own evaluator stays the one definition of a sine track.                                                                             |
| [`sine_sample_times`](#an.characters.play.sine_sample_times)(duration, fps)                 | Frame-rate sample times for a sine track, ALWAYS ending at `duration`.                                                                                                                                                                                                                                                                                                 |
| [`slot_node_path`](#an.characters.play.slot_node_path)(desc, slot_name)                  | The node path of a slot RELATIVE to its entity (`head/left_eye`, `torso`) — the rig builder's nesting rule, stated once.                                                                                                                                                                                                                                               |
| [`slot_parent`](#an.characters.play.slot_parent)(desc, slot)                          | The slot `slot` nests under, or `None` when it is a direct child.                                                                                                                                                                                                                                                                                                      |
| [`suppressed_slots`](#an.characters.play.suppressed_slots)(desc)                           | Slots the rig builder never builds: with the face baked into the head art (`face_overlay=false`), every slot nested under the HEAD BONE's primary slot — keyed on the bone, not on a slot named "head".                                                                                                                                                                |

### Classes

| [`BoneTrack`](#an.characters.play.BoneTrack)(track, slot, property, unit, ...)   | A resolved `bone:<name>.<prop>` track.                                                                                                                                                                                                                                                                                             |
|------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Facing`](#an.characters.play.Facing)([view, direction])                     | What an entity shows at one instant, read off a flat timeline.                                                                                                                                                                                                                                                                     |
| [`ResolvedPlay`](#an.characters.play.ResolvedPlay)(animation, tracks)               |                                                                                                                                                                                                                                                                                                                                    |
| [`SlotTrack`](#an.characters.play.SlotTrack)(track, slot, set_name, frames)      | A resolved `slot:<name>.attachment` track: one set, frames as KEYS.                                                                                                                                                                                                                                                                |
| [`TurnInference`](#an.characters.play.TurnInference)(index, start, entity, before)   | One `play` of [`TURN_PRESET`](#an.characters.play.TURN_PRESET) and the state it starts from.                                                                                                                                                                                                                           |
| [`TurnResolution`](#an.characters.play.TurnResolution)(flats, turns, events)          | [`resolve_turns()`](#an.characters.play.resolve_turns)' result: `flats` is the input with each turn's inferred `from_direction` filled in; `turns` says what each turn started from; `events` is the timeline with every preset play expanded, which [`facing_at()`](#an.characters.play.facing_at) reads. |

### Exceptions

| [`PlayResolutionError`](#an.characters.play.PlayResolutionError)(animation, problems)   | A `play` that cannot resolve; `problems` lists every reason found.   |
|---------------------------------------------------------------------------------------------|----------------------------------------------------------------------|

### an.characters.play.BONE_TRACK_PROPERTIES *: dict[str, tuple[str, float]]* *= {'rotation_deg': ('rotation', 0.017453292519943295), 'scale_x': ('scale_x', 1.0), 'scale_y': ('scale_y', 1.0), 'x': ('x', 1.0), 'y': ('y', 1.0)}*

Descriptor bone-track properties → `(runtime property, unit factor)`.
The descriptor speaks degrees for rotation; the runtime is radians.

### *class* an.characters.play.BoneTrack(track, slot, property, unit, rig_scaled)

Bases: `object`

A resolved `bone:<name>.<prop>` track.

`slot` is the primary slot whose node carries the bone, or `None` for
the entity container (`bone:root`). `property` is the RUNTIME name;
values are `rest + deviation * unit` (times the rig’s pixel factor when
`rig_scaled`).

### an.characters.play.DESCRIPTOR_SOURCE *= 'descriptor'*

the entity descriptor’s own `animations`…

* **Type:**
  Where a `play` resolves

### *class* an.characters.play.Facing(view=None, direction=None)

Bases: `object`

What an entity shows at one instant, read off a flat timeline.

`view` is the key of its view set last set on the ENTITY (`None`: not
set in this shot, so the rig’s default — `front` on a factory
character); `direction` is `"right"`/`"left"` from the sign of the
last `scale_x` it was given (`None`: nothing set it, so its rest).

### an.characters.play.HEAD_BONE *= 'head'*

The bone whose primary slot’s nested slots are the FACE — what
`face_overlay=false` suppresses.

### an.characters.play.PRESET_SOURCE *= 'preset'*

…or, for a name it does not declare, [`an.motion.PRESETS`](an.motion.html.md#an.motion.PRESETS) (an#166).

### *exception* an.characters.play.PlayResolutionError(animation, problems)

Bases: `ValueError`

A `play` that cannot resolve; `problems` lists every reason found.

### an.characters.play.RESERVED_PRESET_ARGS *: frozenset[str]* *= frozenset({'parts', 'rest', 'target'})*

the target is
the play’s own, and the rest pose is read off the built scene.

* **Type:**
  Preset parameters an author may NOT pass through `args`

### an.characters.play.RIG_SCALED_PROPERTIES *: frozenset[str]* *= frozenset({'x', 'y'})*

Bone-track properties whose values are view-box LENGTHS, so a renderer
scales them by the rig’s view-box → scene-pixel factor. Scales and angles
are dimensionless.

### an.characters.play.ROOT_BONE *= 'root'*

a track on it animates the entity’s
container node rather than any slot.

* **Type:**
  The bone that stands for the whole rig

### *class* an.characters.play.ResolvedPlay(animation, tracks)

Bases: `object`

### *class* an.characters.play.SlotTrack(track, slot, set_name, frames)

Bases: `object`

A resolved `slot:<name>.attachment` track: one set, frames as KEYS.

### an.characters.play.TURN_PRESET *= 'turn'*

a
turn opens from the side the character faces NOW, which only the timeline
knows.

* **Type:**
  The preset whose START depends on what came before it on the timeline

### *class* an.characters.play.TurnInference(index, start, entity, before, declared=None)

Bases: `object`

One `play` of [`TURN_PRESET`](#an.characters.play.TURN_PRESET) and the state it starts from.

`index` is the play’s position in the flat list it was read from;
`declared` is the `from_direction` the author passed (`None`: left
to the timeline).

#### *property* contradicted *: bool*

The author’s `from_direction` disagrees with the timeline — the
turn would jump to the other side before it squashes.

### *class* an.characters.play.TurnResolution(flats, turns, events)

Bases: `object`

[`resolve_turns()`](#an.characters.play.resolve_turns)’ result: `flats` is the input with each turn’s
inferred `from_direction` filled in; `turns` says what each turn
started from; `events` is the timeline with every preset play expanded,
which [`facing_at()`](#an.characters.play.facing_at) reads.

### an.characters.play.active_skin(desc)

The skin the rig draws: `default`, else the first declared, else empty.

* **Return type:**
  [`Skin`](an.characters.schema.html.md#an.characters.schema.Skin)

### an.characters.play.art_exists_for(characters_store, ref)

`rel_path -> is the art on disk`, for a character in a filesystem
store; `None` when the store has no root to look under (a dict, a
fake) — a store that can answer nothing must assume presence, not absence,
exactly as the rig builder’s part probe does.

* **Return type:**
  `Callable`[[`str`], `bool`] | `None`

### an.characters.play.drawn_attachment(desc, skin, slot)

The `(name, attachment)` a slot draws by default, or `None`.

* **Return type:**
  `tuple`[`str`, [`Attachment`](an.characters.schema.html.md#an.characters.schema.Attachment)] | `None`

### an.characters.play.expand_preset_play(action, , start, rest_of, parts_of=None)

A preset `play` as the flat tweens and settling `set``s it stands
for, at absolute times from ``start` (an#166).

`rest_of(node_path)` returns the pose to build that node’s move from
(`x`, `y`, `rotation`, `scale_x`, `scale_y`, `alpha` — the
compiler passes the pose the node HAS at `start`, an#212), or `None` when the
built scene carries no such node — then this raises naming it, which is
what the runtime would otherwise do mid-render. `duration` stretches the
move to that length; `speed` divides it. Assumes
[`preset_problems()`](#an.characters.play.preset_problems) came back empty.

A preset that moves several nodes of the entity (it takes `parts`,
`PARTS_ARG` — `walk`) gets `parts_of(entity)`’s paths with their
`rest_of` poses, and every node its expansion moves is checked.

* **Return type:**
  `list`

```pycon
>>> from an.ir.schema import PlayAction
>>> flats = expand_preset_play(
...     PlayAction(target="a", animation="hop", args={"height": 10}),
...     start=1.0, rest_of=lambda p: {"y": 5.0})
>>> [(round(f.start, 3), type(f.action).__name__, f.action.property) for f in flats]
[(1.0, 'TweenAction', 'y'), (1.25, 'TweenAction', 'y'), (1.5, 'SetAction', 'y')]
>>> flats[0].action.to_value
-5.0
```

### an.characters.play.facing_at(events, entity, t, , view_set='view')

What `entity` shows at time `t`: the latest `view_set` swap set
on the entity and the sign of the latest `scale_x` it was given, at or
before `t` (a tween counts from its END, when its value has landed; at
one instant the one LATER in `events` wins — so pass them in authoring
order, as [`resolve_turns()`](#an.characters.play.resolve_turns) does).

* **Return type:**
  [`Facing`](#an.characters.play.Facing)

```pycon
>>> from an.ir.compose import flatten, sequence
>>> from an.motion import turn
>>> flats = flatten(sequence(turn("ned", to="side", direction="left")))
>>> facing_at(flats, "ned", 0.0), facing_at(flats, "ned", 1.0)
(Facing(view=None, direction=None), Facing(view='side', direction='left'))
```

### an.characters.play.play_problems(desc, animation, , art_exists=None, args=None, duration=None, speed=1.0, loop=None)

Every reason `play(<entity>, animation, ...)` cannot resolve — empty
when it can. THE verdict `an validate` reports and the compiler raises
on, for both sources (an#7, an#166).

* **Return type:**
  `list`[`str`]

```pycon
>>> play_problems(None, "hop", args={"heigth": 3})
["motion preset 'hop' has no parameter 'heigth' (it takes: [...])"]
>>> play_problems(None, "hop", loop=True)
["motion preset 'hop' is a one-shot: `loop: true` ...
```

### an.characters.play.play_source(desc, animation)

Which library a `play` of `animation` resolves in —
[`DESCRIPTOR_SOURCE`](#an.characters.play.DESCRIPTOR_SOURCE) when `desc` declares it (the descriptor WINS a
name a preset also has), else [`PRESET_SOURCE`](#an.characters.play.PRESET_SOURCE) when a motion preset
has it. `desc=None` is an entity with no descriptor: presets only.

Raises [`PlayResolutionError`](#an.characters.play.PlayResolutionError) naming BOTH vocabularies when neither
has the name.

* **Return type:**
  `str`

### an.characters.play.preset_moved_node(action_target, animation, args=None)

The ONE node path a preset play moves — `<target>/head` for a `nod`,
the target itself for the rest. Read off the expansion rather than
restated per preset, so a preset added later needs no entry here.

* **Return type:**
  `str`

```pycon
>>> preset_moved_node("charlie", "nod"), preset_moved_node("charlie", "hop")
('charlie/head', 'charlie')
```

### an.characters.play.preset_moved_nodes(action_target, animation, args=None, , parts=None)

Every node path a preset play moves. `parts` (the entity’s built part
paths, relative to it) is what a multi-node preset chooses its limbs from;
`None` lets it assume the rig contract’s names.

* **Return type:**
  `list`[`str`]

```pycon
>>> preset_moved_nodes("bob", "walk", {"distance": 80}, parts=["torso", "left_leg", "right_leg"])
['bob', 'bob/left_leg', 'bob/right_leg']
>>> preset_moved_nodes("charlie", "nod")
['charlie/head']
```

### an.characters.play.preset_play_span(action)

How long a preset `play` runs, in seconds: its `duration` when set,
else the preset’s natural length divided by `speed`. What a
`sequence` advances by is `play_extent()`, which is this for a preset
source.

* **Return type:**
  `float`

```pycon
>>> from an.ir.schema import PlayAction
>>> preset_play_span(PlayAction(target="a", animation="hop"))
0.5
>>> preset_play_span(PlayAction(target="a", animation="hop", speed=2.0))
0.25
```

### an.characters.play.preset_problems(animation, , args=None, duration=None, speed=1.0, loop=None)

Why a `play` of the motion preset `animation` cannot expand.

The parameters are checked by NAME against the preset’s signature, then by
building it (at the identity pose), so a value the preset itself refuses —
`cycles: 0`, a string height — is reported in the preset’s own words.

* **Return type:**
  `list`[`str`]

### an.characters.play.preset_takes(animation, name)

Whether the motion preset `animation` has the keyword `name`.

* **Return type:**
  `bool`

```pycon
>>> preset_takes("walk", "parts"), preset_takes("hop", "parts")
(True, False)
```

### an.characters.play.primary_slot_per_bone(desc)

`{bone name: the slot that IS that bone}`, when one exists.

Used for node nesting, which is deliberately **not** the bone hierarchy.
The rigs here are flat by design — arms are siblings of the torso, not
children (CLAUDE.md pillar 4) — so bone parentage decides *position* only.
A slot nests under the primary slot of its bone when it is not that slot
itself, which is what puts eyes and mouth under `head` and leaves every
limb a direct child of the entity.

* **Return type:**
  `dict`[`str`, `str`]

```pycon
>>> primary_slot_per_bone(CharacterDescriptor(name="m"))["head"]
'head'
```

### an.characters.play.resolve_play(desc, animation, , art_exists=None)

Resolve `animation` of `desc` into renderer-ready tracks, or raise
[`PlayResolutionError`](#an.characters.play.PlayResolutionError) listing every problem found.

`art_exists(rel_path)` answers whether a skin attachment’s art is on
disk; pass `None` when the caller cannot know, and every declared
attachment is assumed present (the rig builder’s own rule for a store
without a filesystem root).

* **Return type:**
  [`ResolvedPlay`](#an.characters.play.ResolvedPlay)

### an.characters.play.resolve_turns(flat_list, , descriptor_of, rest_of)

Fill in each turn’s `from_direction` from the timeline before it
(an#203): a `play` of `turn` on an entity that does not pass one
opens from the side the latest earlier `scale_x` left the entity facing
— so `side` (`direction: left`) then `back` is two plays, with no
`from_direction` by hand. Turns are resolved in time order, each seeing
the ones before it expanded. THE resolver the compiler expands with and
`an validate` checks with.

An explicit `from_direction` is kept — `turns` records it with the
inferred state so `an validate` can say when the two disagree. A play
that cannot resolve is left for [`play_problems()`](#an.characters.play.play_problems) to report.

* **Return type:**
  [`TurnResolution`](#an.characters.play.TurnResolution)

```pycon
>>> from an.ir.compose import flatten, sequence
>>> from an.ir.schema import PlayAction
>>> flats = flatten(sequence(
...     PlayAction(target="ned", animation="turn", args={"to": "side", "direction": "left"}),
...     PlayAction(target="ned", animation="turn", args={"to": "back"})))
>>> res = resolve_turns(flats, descriptor_of=lambda e: None,
...                     rest_of=lambda p: {"scale_x": 1.0})
>>> res.flats[1].action.args["from_direction"], res.turns[1].before
('left', Facing(view='side', direction='left'))
```

### an.characters.play.sampled_deviations(track, duration, fps)

`(time, deviation)` pairs for a sine bone track at the frame rate —
[`an.characters.idle.evaluate_track()`](an.characters.idle.html.md#an.characters.idle.evaluate_track)’s formula, sampled, so the
descriptor’s own evaluator stays the one definition of a sine track.

* **Return type:**
  `list`[`tuple`[`float`, `float`]]

### an.characters.play.sine_sample_times(duration, fps)

Frame-rate sample times for a sine track, ALWAYS ending at `duration`.

`ceil` rather than `round`: with `round`, a 0.18 s track at 24 fps
got samples up to 0.1667 s and then held that value to the clip end, so
the cycle-closing sample (equal to the first) was never emitted and the
clip wrapped with a jump (an#7 review).

* **Return type:**
  `list`[`float`]

```pycon
>>> sine_sample_times(0.19, 24)[-2:]
[0.16666666666666666, 0.19]
>>> len(sine_sample_times(6.0, 24))
145
```

### an.characters.play.slot_node_path(desc, slot_name)

The node path of a slot RELATIVE to its entity (`head/left_eye`,
`torso`) — the rig builder’s nesting rule, stated once.

* **Return type:**
  `str`

```pycon
>>> slot_node_path(CharacterDescriptor(name="m"), "left_eye")
'head/left_eye'
>>> slot_node_path(CharacterDescriptor(name="m"), "torso")
'torso'
```

### an.characters.play.slot_parent(desc, slot)

The slot `slot` nests under, or `None` when it is a direct child.

* **Return type:**
  `str` | `None`

### an.characters.play.suppressed_slots(desc)

Slots the rig builder never builds: with the face baked into the head
art (`face_overlay=false`), every slot nested under the HEAD BONE’s
primary slot — keyed on the bone, not on a slot named “head”.

* **Return type:**
  `frozenset`[`str`]

```pycon
>>> sorted(suppressed_slots(CharacterDescriptor(name="m", face_overlay=False)))
['left_brow', 'left_eye', 'mouth', 'right_brow', 'right_eye']
>>> suppressed_slots(CharacterDescriptor(name="m"))
frozenset()
```
