# an.stage.timeline

Stage timeline helpers: the compiled scene as a `Timeline`, and screen space.

The evaluation itself — tracks of placed clips, write groups, the pure pose —
moved to [`an.timing.timeline`](an.timing.timeline.md#module-an.timing.timeline) (the timing kernel). This module re-exports
it so every existing caller keeps its import path, and keeps what is the STAGE’s
own: reading a compiled `CutoutSceneJSON` ([`timeline_from_scene()`](#an.stage.timeline.timeline_from_scene)) and
composing node transforms into canvas positions ([`screen_position()`](#an.stage.timeline.screen_position)).

```pycon
>>> from an.timing.channel import Channel, Keyframe
>>> from an.adapters.cutout.clip import Clip
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> clip = Clip("walk", duration=1.0, channels=[ch])
>>> tl = Timeline(duration=2.0, tracks=[Track("a", clips=[PlacedClip(clip, start_time=0.5)])])
>>> evaluate_timeline(tl, 1.0)[("a", "x")]
5.0
```

### Functions

| [`merge_poses`](#an.stage.timeline.merge_poses)(\*poses)                            | Merge multiple poses with **override semantics** (later wins per key).                                                    |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| [`write_group`](#an.stage.timeline.write_group)(prop)                               | What `prop` writes on a STAGE node (the `stage.node` space's groups).                                                     |
| [`evaluate_timeline`](#an.stage.timeline.evaluate_timeline)(timeline, t, \*[, space])     | Evaluate `timeline` at time `t`, merging poses across tracks/clips.                                                       |
| [`clip_from_json`](#an.stage.timeline.clip_from_json)(anim, \*[, name])                | One compiled animation (`compiled.schema.json`'s `animation`) as a [`Clip`](#an.stage.timeline.Clip). |
| [`timeline_from_scene`](#an.stage.timeline.timeline_from_scene)(scene)                      | The compiled scene's `timeline`/`animations` as an evaluable `Timeline`.                                                  |
| [`transform_of`](#an.stage.timeline.transform_of)(node[, pose])                      | A node's transform, with `pose` overriding what the document declares.                                                    |
| [`screen_position`](#an.stage.timeline.screen_position)(scene, path, \*[, pose, point]) | Where `point` in `path`'s local space lands on the canvas.                                                                |

### Classes

| [`Channel`](#an.stage.timeline.Channel)(target, property[, keyframes])        | Sorted keyframes for one property of one target.                        |
|------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`Keyframe`](#an.stage.timeline.Keyframe)(time, value[, easing])               | One keyframe: time, value, optional per-segment easing.                 |
| [`Clip`](#an.stage.timeline.Clip)(name, duration[, channels, loop_mode])   | Named animation: a duration + a bundle of channels.                     |
| [`LoopMode`](#an.stage.timeline.LoopMode)(\*values)                            | How a clip behaves past its natural duration.                           |
| [`PlacedClip`](#an.stage.timeline.PlacedClip)(clip[, start_time, duration, ...]) | A clip placed at an absolute time on a track.                           |
| [`Track`](#an.stage.timeline.Track)([target_root, clips])                   | A sequence of placed clips that share a common purpose / target prefix. |
| [`Timeline`](#an.stage.timeline.Timeline)(duration[, tracks, space])           | A duration + ordered list of tracks.                                    |
| [`Transform2D`](#an.stage.timeline.Transform2D)([x, y, rotation, scale_x, ...])   | One node's local transform, in the runtime's own vocabulary.            |

### *class* an.stage.timeline.Channel(target, property, keyframes=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Sorted keyframes for one property of one target.

Construction validates that `keyframes` is non-empty and sorted.

### *class* an.stage.timeline.Clip(name, duration, channels=<factory>, loop_mode=LoopMode.ONCE)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Named animation: a duration + a bundle of channels.

### *class* an.stage.timeline.Keyframe(time, value, easing=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One keyframe: time, value, optional per-segment easing.

The easing on a keyframe describes the curve **leaving** that keyframe
toward the next one. The last keyframe’s easing is therefore unused.

### *class* an.stage.timeline.LoopMode(\*values)

Bases: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Enum`](https://docs.python.org/3/library/enum.html#enum.Enum)

How a clip behaves past its natural duration.

### *class* an.stage.timeline.PlacedClip(clip, start_time=0.0, duration=None, speed=1.0, blend_in=0.0, blend_out=0.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A clip placed at an absolute time on a track.

#### *property* effective_duration *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Duration this clip occupies on the timeline (after speed scaling).

### *class* an.stage.timeline.Timeline(duration, tracks=<factory>, space=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A duration + ordered list of tracks. The canonical playback structure.

`space` is the property space the timeline’s DOCUMENT declares for its
targets (an#245): one space, a registered name, or a `target -> space`
resolver. It is what [`evaluate_timeline()`](#an.stage.timeline.evaluate_timeline) uses when the caller passes
none, so every caller of the default evaluates a target in the space its
entity’s kind declares. `None` (every document that declares nothing) is
the kernel default, [`an.timing.spaces.DFLT_TIMELINE_SPACE`](an.timing.spaces.md#an.timing.spaces.DFLT_TIMELINE_SPACE).

### *class* an.stage.timeline.Track(target_root='', clips=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A sequence of placed clips that share a common purpose / target prefix.

`target_root` is informational metadata for downstream tools (the JS
runtime can use it to scope rendering); evaluation does not filter by it.

### *class* an.stage.timeline.Transform2D(x=0.0, y=0.0, rotation=0.0, scale_x=1.0, scale_y=1.0, pivot_x=0.0, pivot_y=0.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One node’s local transform, in the runtime’s own vocabulary.

Field names and defaults mirror `applyTransform` in `runtime.js` exactly —
`x`, `y`, `rotation`, `scale_x`, `scale_y`, `pivot_x`, `pivot_y` — because
the point of this class is to agree with the vendored engine rather than to
re-derive it. `skew` is deliberately absent: PixiJS composes skew into the
same matrix, but no emitter in this package produces a skew channel, and a
field nothing writes is a claim this compositor cannot honour.

#### apply(point)

This node’s local point, in its PARENT’s coordinates.

`world = position + M·(local − pivot)` — the composition PixiJS
performs, and the reason `root.pivot` is a 2D camera: moving the pivot
moves everything the node contains, in the opposite direction.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> Transform2D(x=10.0).apply((0.0, 0.0))
(10.0, 0.0)
>>> Transform2D(pivot_x=25.0).apply((0.0, 0.0))
(-25.0, 0.0)
>>> Transform2D(scale_x=2.0).apply((5.0, 0.0))
(10.0, 0.0)
```

#### unapply(point)

The inverse of [`apply()`](#an.stage.timeline.Transform2D.apply) — a parent-space point, in local space.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> t = Transform2D(x=10.0, pivot_x=3.0, scale_x=2.0, rotation=0.4)
>>> round(t.unapply(t.apply((7.0, -2.0)))[0], 9)
7.0
```

### an.stage.timeline.clip_from_json(anim, , name=None)

One compiled animation (`compiled.schema.json`’s `animation`) as a [`Clip`](#an.stage.timeline.Clip).

Accepts the JSON mapping or any object with the same attributes (the stage’s
`AnimationClipJSON`). Two fields are carried rather than defaulted, and
both have cost a bug: `loop_mode` (without it every loop evaluated as
`once` — an#7) and a list-valued `easing`, which is a cubic-bezier
control quadruple and must stay a tuple for `Keyframe`. The stage compiler
reads a from-less tween’s start through this too (an#212), so it evaluates
exactly what the runtime will.

* **Return type:**
  [`Clip`](an.timing.clip.md#an.timing.clip.Clip)

### an.stage.timeline.evaluate_timeline(timeline, t, , space=None)

Evaluate `timeline` at time `t`, merging poses across tracks/clips.

The result is a PURE function of `t` (an#185): what a node shows at `t`
never depends on which instants were evaluated before it. Per
`(target, property)`:

- **Active** — some clip writing it is playing at `t` (inclusive end:
  a clip at `[s, e]` is active at `t == e` too, so the final frame of
  “play this from 0 to 1 s” is visible at 1.0). Later wins: track order,
  then clip order within a track. Written at `t`.
- **Held** — no clip writing it is playing, but one has ended: the value
  the clip reached AT ITS END holds. The latest end wins; a tie goes to
  the later clip, the same “later wins” as above. Written at that end.
- **At rest** — nothing writing it has started yet. The key is ABSENT from
  the pose, and its value is the node’s own (the entity’s rest state;
  `runtime.js` restores what it built).

Keys that write the same thing on one node (a write group: the swap sets of
one visual, `rotation`/`rotation_rad`) keep only the most recently
WRITTEN — an ended `viseme@happy` span does not outlive the `viseme`
track that took the mouth back.

`space` says what each property is ([`an.timing.spaces`](an.timing.spaces.md#module-an.timing.spaces)): one space, a
registered space’s name, or a `target -> space` resolver. Its field kinds
interpolate and its write groups resolve. `None` is the default space,
[`an.timing.spaces.DFLT_TIMELINE_SPACE`](an.timing.spaces.md#an.timing.spaces.DFLT_TIMELINE_SPACE) (the stage node’s declared
kinds, by name at call time). `space=VALUE_TYPED` is the rule
`runtime.js` implements — interpolation by value type, the `stage.node`
write groups — which gives the same pose on every timeline the compiler
emits (it refuses a value that fails its field kind).

Forward-order rendering used to show the value at the clip’s last SAMPLED
frame instead (the runtime kept whatever it last applied). The two agree
whenever a clip ends on the frame grid — true of every golden-corpus clip
— and differ when it ends between frames: a 0.37 s tween to 10 at 24 fps
used to stop at 9.80 and now lands on 10, as authored. That landing is
deliberate (it is the bug the motion presets’ settling `set` patched one
preset at a time), and it is what makes the pose independent of the grid.
Also deliberate: a clip shorter than a frame that no frame lands in now
leaves its end value, and a held descendant tint stays on top of an
ancestor’s later tint (the more specific target wins, as it always did
while both played).

`runtime.js::evaluateTimeline` is a port of this function and
`tests/test_pure_pose.py` holds the two to it.

```pycon
>>> from an.timing.channel import Channel, Keyframe
>>> from an.timing.clip import Clip
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> tl = Timeline(2.0, [Track("a", [PlacedClip(Clip("m", 1.0, [ch]), 0.5)])])
>>> evaluate_timeline(tl, 0.0)  # not started: at rest, so absent
{}
>>> evaluate_timeline(tl, 1.0)[("a", "x")]  # active
5.0
>>> evaluate_timeline(tl, 1.75)[("a", "x")]  # ended: its end value holds
10.0
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.stage.timeline.merge_poses(\*poses)

Merge multiple poses with **override semantics** (later wins per key).

Used by the timeline to combine concurrent clips on the same target.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> merge_poses({("a", "x"): 1.0}, {("a", "x"): 2.0, ("a", "y"): 3.0})
{('a', 'x'): 2.0, ('a', 'y'): 3.0}
```

### an.stage.timeline.screen_position(scene, path, , pose=None, point=(0.0, 0.0))

Where `point` in `path`’s local space lands on the canvas.

The composition the runtime performs, walked from the node up to `root`
and then offset by the canvas centre — which is where `runtime.js` places
the root container.

`pose` is keyed by the FULL path (`"street/hills"`), matching what
`evaluate_timeline` returns, and each node reads only its own entry.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> from an.stage.serialize import CutoutSceneJSON, NodeJSON, TimelineJSON, TransformJSON
>>> scene = CutoutSceneJSON(
...     scene=NodeJSON(name="root", children=[
...         NodeJSON(name="hill", transform=TransformJSON(x=40.0))]),
...     timeline=TimelineJSON(duration=1.0),
... )
>>> scene.meta.width, scene.meta.height = 320, 240
>>> screen_position(scene, "hill")
(200.0, 120.0)
```

…and moving the camera’s pivot moves it the other way, which is the whole
reason `root.pivot` is the camera:

```pycon
>>> screen_position(scene, "hill", pose={("root", "pivot_x"): 25.0})
(175.0, 120.0)
```

### an.stage.timeline.timeline_from_scene(scene)

The compiled scene’s `timeline`/`animations` as an evaluable `Timeline`.

`compile_shot` produces a serialisable document (`an.stage.serialize`)
for the JS runtime; this rebuilds the *evaluable* form, so a caller can ask
what a compiled scene’s pose is at time `t` without a browser. It is the
Python side of the parity contract: `evaluate_timeline` over this object is
the executable spec `runtime.js` is tested against. The reading itself is the
kernel’s ([`an.timing.timeline.timeline_from_compiled()`](an.timing.timeline.md#an.timing.timeline.timeline_from_compiled)), which carries
`loop_mode` and keeps a list-valued `easing` a tuple.

* **Return type:**
  [`Timeline`](an.timing.timeline.md#an.timing.timeline.Timeline)

```pycon
>>> from an.stage.compile import compile_shot
>>> from an.ir.compose import tween
>>> from an.ir.schema import Shot
>>> shot = Shot(id="s1", renderer="cutout", duration=2.0,
...             actions=[tween("root", "x", 10.0, 1.0, from_=0.0)])
>>> scene = compile_shot(shot, mall=None, fps=24)
>>> evaluate_timeline(timeline_from_scene(scene), 0.5)[("root", "x")]
5.0
```

### an.stage.timeline.transform_of(node, pose=None)

A node’s transform, with `pose` overriding what the document declares.

The runtime applies a pose value by assigning the property on the display
object, so a channel REPLACES the declared value rather than adding to it —
which is why the parallax compensation carries the plane’s own offset in
every keyframe instead of an offset from it.

* **Return type:**
  [`Transform2D`](#an.stage.timeline.Transform2D)

### an.stage.timeline.write_group(prop)

What `prop` writes on a STAGE node (the `stage.node` space’s groups).

Two keys in one group set the same thing, so only the more recently written
can be showing: every swap set on a node swaps the one visual it carries
(`viseme` and `viseme@happy` both set the mouth’s texture, an#88), and
`rotation_rad` is `rotation`. Every other runtime property
(`an.base.TRANSFORM_PROPERTIES`, the runtime’s own switch) writes only
itself.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> write_group("x"), write_group("rotation_rad"), write_group("viseme@happy")
('x', 'rotation', '<swap>')
```
