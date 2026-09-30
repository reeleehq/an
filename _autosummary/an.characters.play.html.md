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
[`expand_preset_play()`](#an.characters.play.expand_preset_play) builds them at the moved node’s REST pose, which
the caller reads off the built scene, so an author never passes `rest`.

```pycon
>>> play_problems(desc, "walk")
["no animation 'walk': the descriptor declares ['blink', 'idle_breath'] and no
  motion preset has that name (presets: ['hop', 'nod', 'point', 'pop_in',
  'shake', 'slide_in', 'slide_out', 'squash_stretch', 'turn', 'waddle'])"]
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

### Functions

| [`active_skin`](#an.characters.play.active_skin)(desc)                               | The skin the rig draws: `default`, else the first declared, else empty.                                                                                                                                                                                                                         |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`art_exists_for`](#an.characters.play.art_exists_for)(characters_store, ref)           | `rel_path -> is the art on disk`, for a character in a filesystem store; `None` when the store has no root to look under (a dict, a fake) — a store that can answer nothing must assume presence, not absence, exactly as the rig builder's part probe does.                                    |
| [`drawn_attachment`](#an.characters.play.drawn_attachment)(desc, skin, slot)              | The `(name, attachment)` a slot draws by default, or `None`.                                                                                                                                                                                                                                    |
| [`expand_preset_play`](#an.characters.play.expand_preset_play)(action, \*, start, rest_of)  | A preset `play` as the flat tweens and settling `set``s it stands for, at absolute times from ``start` (an#166).                                                                                                                                                                                |
| [`play_problems`](#an.characters.play.play_problems)(desc, animation, \*[, ...])       | Every reason `play(<entity>, animation, ...)` cannot resolve — empty when it can.                                                                                                                                                                                                               |
| [`play_source`](#an.characters.play.play_source)(desc, animation)                    | Which library a `play` of `animation` resolves in — [`DESCRIPTOR_SOURCE`](#an.characters.play.DESCRIPTOR_SOURCE) when `desc` declares it (the descriptor WINS a name a preset also has), else [`PRESET_SOURCE`](#an.characters.play.PRESET_SOURCE) when a motion preset has it. |
| [`preset_moved_node`](#an.characters.play.preset_moved_node)(action_target, animation)     | The ONE node path a preset play moves — `<target>/head` for a `nod`, the target itself for the rest.                                                                                                                                                                                            |
| [`preset_play_span`](#an.characters.play.preset_play_span)(action)                        | How long a preset `play` runs, in seconds: its `duration` when set, else the preset's natural length divided by `speed`.                                                                                                                                                                        |
| [`preset_problems`](#an.characters.play.preset_problems)(animation, \*[, args, ...])     | Why a `play` of the motion preset `animation` cannot expand.                                                                                                                                                                                                                                    |
| [`primary_slot_per_bone`](#an.characters.play.primary_slot_per_bone)(desc)                     | `{bone name: the slot that IS that bone}`, when one exists.                                                                                                                                                                                                                                     |
| [`resolve_play`](#an.characters.play.resolve_play)(desc, animation, \*[, art_exists]) | Resolve `animation` of `desc` into renderer-ready tracks, or raise [`PlayResolutionError`](#an.characters.play.PlayResolutionError) listing every problem found.                                                                                                                            |
| [`sampled_deviations`](#an.characters.play.sampled_deviations)(track, duration, fps)        | `(time, deviation)` pairs for a sine bone track at the frame rate — [`an.characters.idle.evaluate_track()`](an.characters.idle.html.md#an.characters.idle.evaluate_track)'s formula, sampled, so the descriptor's own evaluator stays the one definition of a sine track.      |
| [`sine_sample_times`](#an.characters.play.sine_sample_times)(duration, fps)                | Frame-rate sample times for a sine track, ALWAYS ending at `duration`.                                                                                                                                                                                                                          |
| [`slot_node_path`](#an.characters.play.slot_node_path)(desc, slot_name)                 | The node path of a slot RELATIVE to its entity (`head/left_eye`, `torso`) — the rig builder's nesting rule, stated once.                                                                                                                                                                        |
| [`slot_parent`](#an.characters.play.slot_parent)(desc, slot)                         | The slot `slot` nests under, or `None` when it is a direct child.                                                                                                                                                                                                                               |
| [`suppressed_slots`](#an.characters.play.suppressed_slots)(desc)                          | Slots the rig builder never builds: with the face baked into the head art (`face_overlay=false`), every slot nested under the HEAD BONE's primary slot — keyed on the bone, not on a slot named "head".                                                                                         |

### Classes

| [`BoneTrack`](#an.characters.play.BoneTrack)(track, slot, property, unit, ...)   | A resolved `bone:<name>.<prop>` track.                              |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`ResolvedPlay`](#an.characters.play.ResolvedPlay)(animation, tracks)               |                                                                     |
| [`SlotTrack`](#an.characters.play.SlotTrack)(track, slot, set_name, frames)      | A resolved `slot:<name>.attachment` track: one set, frames as KEYS. |

### Exceptions

| [`PlayResolutionError`](#an.characters.play.PlayResolutionError)(animation, problems)   | A `play` that cannot resolve; `problems` lists every reason found.   |
|---------------------------------------------------------------------------------------------|----------------------------------------------------------------------|

### an.characters.play.BONE_TRACK_PROPERTIES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float)]]* *= {'rotation_deg': ('rotation', 0.017453292519943295), 'scale_x': ('scale_x', 1.0), 'scale_y': ('scale_y', 1.0), 'x': ('x', 1.0), 'y': ('y', 1.0)}*

Descriptor bone-track properties → `(runtime property, unit factor)`.
The descriptor speaks degrees for rotation; the runtime is radians.

### *class* an.characters.play.BoneTrack(track, slot, property, unit, rig_scaled)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A resolved `bone:<name>.<prop>` track.

`slot` is the primary slot whose node carries the bone, or `None` for
the entity container (`bone:root`). `property` is the RUNTIME name;
values are `rest + deviation * unit` (times the rig’s pixel factor when
`rig_scaled`).

### an.characters.play.DESCRIPTOR_SOURCE *= 'descriptor'*

the entity descriptor’s own `animations`…

* **Type:**
  Where a `play` resolves

### an.characters.play.HEAD_BONE *= 'head'*

The bone whose primary slot’s nested slots are the FACE — what
`face_overlay=false` suppresses.

### an.characters.play.PRESET_SOURCE *= 'preset'*

…or, for a name it does not declare, [`an.motion.PRESETS`](an.motion.html.md#an.motion.PRESETS) (an#166).

### *exception* an.characters.play.PlayResolutionError(animation, problems)

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A `play` that cannot resolve; `problems` lists every reason found.

### an.characters.play.RESERVED_PRESET_ARGS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'rest', 'target'})*

the target is
the play’s own, and the rest pose is read off the built scene.

* **Type:**
  Preset parameters an author may NOT pass through `args`

### an.characters.play.RIG_SCALED_PROPERTIES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'x', 'y'})*

Bone-track properties whose values are view-box LENGTHS, so a renderer
scales them by the rig’s view-box → scene-pixel factor. Scales and angles
are dimensionless.

### an.characters.play.ROOT_BONE *= 'root'*

a track on it animates the entity’s
container node rather than any slot.

* **Type:**
  The bone that stands for the whole rig

### *class* an.characters.play.ResolvedPlay(animation, tracks)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

### *class* an.characters.play.SlotTrack(track, slot, set_name, frames)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A resolved `slot:<name>.attachment` track: one set, frames as KEYS.

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
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`bool`](https://docs.python.org/3/builtins/functions.html#bool)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.characters.play.drawn_attachment(desc, skin, slot)

The `(name, attachment)` a slot draws by default, or `None`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Attachment`](an.characters.schema.html.md#an.characters.schema.Attachment)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.characters.play.expand_preset_play(action, , start, rest_of)

A preset `play` as the flat tweens and settling `set``s it stands
for, at absolute times from ``start` (an#166).

`rest_of(node_path)` returns that node’s built rest pose (`x`, `y`,
`rotation`, `scale_x`, `scale_y`, `alpha`), or `None` when the
built scene carries no such node — then this raises naming it, which is
what the runtime would otherwise do mid-render. `duration` stretches the
move to that length; `speed` divides it. Assumes
[`preset_problems()`](#an.characters.play.preset_problems) came back empty.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

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

### an.characters.play.play_problems(desc, animation, , art_exists=None, args=None, duration=None, speed=1.0, loop=None)

Every reason `play(<entity>, animation, ...)` cannot resolve — empty
when it can. THE verdict `an validate` reports and the compiler raises
on, for both sources (an#7, an#166).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

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
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.play.preset_moved_node(action_target, animation, args=None)

The ONE node path a preset play moves — `<target>/head` for a `nod`,
the target itself for the rest. Read off the expansion rather than
restated per preset, so a preset added later needs no entry here.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> preset_moved_node("charlie", "nod"), preset_moved_node("charlie", "hop")
('charlie/head', 'charlie')
```

### an.characters.play.preset_play_span(action)

How long a preset `play` runs, in seconds: its `duration` when set,
else the preset’s natural length divided by `speed`. What a
`sequence` advances by is `play_extent()`, which is this for a preset
source.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

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
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.characters.play.primary_slot_per_bone(desc)

`{bone name: the slot that IS that bone}`, when one exists.

Used for node nesting, which is deliberately **not** the bone hierarchy.
The rigs here are flat by design — arms are siblings of the torso, not
children (CLAUDE.md pillar 4) — so bone parentage decides *position* only.
A slot nests under the primary slot of its bone when it is not that slot
itself, which is what puts eyes and mouth under `head` and leaves every
limb a direct child of the entity.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

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

### an.characters.play.sampled_deviations(track, duration, fps)

`(time, deviation)` pairs for a sine bone track at the frame rate —
[`an.characters.idle.evaluate_track()`](an.characters.idle.html.md#an.characters.idle.evaluate_track)’s formula, sampled, so the
descriptor’s own evaluator stays the one definition of a sine track.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.characters.play.sine_sample_times(duration, fps)

Frame-rate sample times for a sine track, ALWAYS ending at `duration`.

`ceil` rather than `round`: with `round`, a 0.18 s track at 24 fps
got samples up to 0.1667 s and then held that value to the clip end, so
the cycle-closing sample (equal to the first) was never emitted and the
clip wrapped with a jump (an#7 review).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

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
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> slot_node_path(CharacterDescriptor(name="m"), "left_eye")
'head/left_eye'
>>> slot_node_path(CharacterDescriptor(name="m"), "torso")
'torso'
```

### an.characters.play.slot_parent(desc, slot)

The slot `slot` nests under, or `None` when it is a direct child.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.characters.play.suppressed_slots(desc)

Slots the rig builder never builds: with the face baked into the head
art (`face_overlay=false`), every slot nested under the HEAD BONE’s
primary slot — keyed on the bone, not on a slot named “head”.

* **Return type:**
  [`frozenset`](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> sorted(suppressed_slots(CharacterDescriptor(name="m", face_overlay=False)))
['left_brow', 'left_eye', 'mouth', 'right_brow', 'right_eye']
>>> suppressed_slots(CharacterDescriptor(name="m"))
frozenset()
```
