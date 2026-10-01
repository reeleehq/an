# an.adapters.cutout.timeline

Timeline: tracks of placed clips with absolute times and blend ramps.

A `Timeline` is a flat description of *what plays when*. It’s the canonical
form passed downstream to the JS runtime in Phase 2B. Authoring composition
trees from `an.ir.compose` (sequence/parallel/etc.) get *flattened into* a
Timeline by `compile_shot` (see `compile.py`).

Evaluation semantics in Phase 2A:

- For each track, identify all clips active at time `t`.
- Each active clip produces a `Pose`.
- Clips on **the same track** override each other in start-order (later wins).
- Clips on **different tracks** merge with later-track override semantics
  (track order in the list determines priority — last track wins on conflict).
- `blend_in` and `blend_out` ramps are recorded but **not yet applied** to
  pose values in 2A — the timeline produces the raw Pose and the renderer
  decides what to do with the ramps. Additive blending lands in 2B.

```pycon
>>> from an.adapters.cutout.channel import Channel, Keyframe
>>> from an.adapters.cutout.clip import Clip
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> clip = Clip("walk", duration=1.0, channels=[ch])
>>> tl = Timeline(duration=2.0, tracks=[Track("a", clips=[PlacedClip(clip, start_time=0.5)])])
>>> evaluate_timeline(tl, 1.0)[("a", "x")]
5.0
```

### Module Attributes

| [`SWAP_WRITE_GROUP`](#an.adapters.cutout.timeline.SWAP_WRITE_GROUP)   | two keys in one group set the same thing, so only the more recently written can be showing.   |
|---------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|

### Functions

| [`clip_from_json`](#an.adapters.cutout.timeline.clip_from_json)(anim, \*[, name])                | One compiled animation (`AnimationClipJSON`) as an evaluable `Clip`.                                    |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| [`evaluate_timeline`](#an.adapters.cutout.timeline.evaluate_timeline)(timeline, t)                  | Evaluate `timeline` at time `t`, merging poses across tracks/clips.                                     |
| [`screen_position`](#an.adapters.cutout.timeline.screen_position)(scene, path, \*[, pose, point]) | Where `point` in `path`'s local space lands on the canvas.                                              |
| [`timeline_from_scene`](#an.adapters.cutout.timeline.timeline_from_scene)(scene)                      | The compiled scene's `timeline`/`animations` as this module's `Timeline`.                               |
| [`transform_of`](#an.adapters.cutout.timeline.transform_of)(node[, pose])                      | A node's transform, with `pose` overriding what the document declares.                                  |
| [`write_group`](#an.adapters.cutout.timeline.write_group)(prop)                               | What `prop` writes on its node — see [`SWAP_WRITE_GROUP`](#an.adapters.cutout.timeline.SWAP_WRITE_GROUP). |

### Classes

| [`PlacedClip`](#an.adapters.cutout.timeline.PlacedClip)(clip[, start_time, duration, ...])   | A clip placed at an absolute time on a track.                           |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`Timeline`](#an.adapters.cutout.timeline.Timeline)(duration[, tracks])                    | A duration + ordered list of tracks.                                    |
| [`Track`](#an.adapters.cutout.timeline.Track)([target_root, clips])                     | A sequence of placed clips that share a common purpose / target prefix. |
| [`Transform2D`](#an.adapters.cutout.timeline.Transform2D)([x, y, rotation, scale_x, ...])     | One node's local transform, in the runtime's own vocabulary.            |

### *class* an.adapters.cutout.timeline.PlacedClip(clip, start_time=0.0, duration=None, speed=1.0, blend_in=0.0, blend_out=0.0)

Bases: `object`

A clip placed at an absolute time on a track.

#### *property* effective_duration *: float*

Duration this clip occupies on the timeline (after speed scaling).

### an.adapters.cutout.timeline.SWAP_WRITE_GROUP *: str* *= '<swap>'*

two keys in one group set the same
thing, so only the more recently written can be showing. Every swap set on a
node swaps the one visual it carries (`viseme` and `viseme@happy` both set
the mouth’s texture, an#88), and `rotation_rad` is `rotation`. Every other
runtime property (`an.base.TRANSFORM_PROPERTIES`, the runtime’s own
switch) writes only itself.

* **Type:**
  The group a property WRITES, on its node

### *class* an.adapters.cutout.timeline.Timeline(duration, tracks=<factory>)

Bases: `object`

A duration + ordered list of tracks. The canonical playback structure.

### *class* an.adapters.cutout.timeline.Track(target_root='', clips=<factory>)

Bases: `object`

A sequence of placed clips that share a common purpose / target prefix.

`target_root` is informational metadata for downstream tools (the JS
runtime can use it to scope rendering); evaluation does not filter by it.

### *class* an.adapters.cutout.timeline.Transform2D(x=0.0, y=0.0, rotation=0.0, scale_x=1.0, scale_y=1.0, pivot_x=0.0, pivot_y=0.0)

Bases: `object`

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
  `tuple`[`float`, `float`]

```pycon
>>> Transform2D(x=10.0).apply((0.0, 0.0))
(10.0, 0.0)
>>> Transform2D(pivot_x=25.0).apply((0.0, 0.0))
(-25.0, 0.0)
>>> Transform2D(scale_x=2.0).apply((5.0, 0.0))
(10.0, 0.0)
```

#### unapply(point)

The inverse of [`apply()`](#an.adapters.cutout.timeline.Transform2D.apply) — a parent-space point, in local space.

* **Return type:**
  `tuple`[`float`, `float`]

```pycon
>>> t = Transform2D(x=10.0, pivot_x=3.0, scale_x=2.0, rotation=0.4)
>>> round(t.unapply(t.apply((7.0, -2.0)))[0], 9)
7.0
```

### an.adapters.cutout.timeline.clip_from_json(anim, , name=None)

One compiled animation (`AnimationClipJSON`) as an evaluable `Clip`.

Two fields are carried rather than defaulted, and both have cost a bug:
`loop_mode` (without it every loop evaluated as `once` — an#7) and a
list-valued `easing`, which is a cubic-bezier control quadruple and must
stay a tuple for `Keyframe`. The compiler reads a from-less tween’s
start through this too (an#212), so it evaluates exactly what the
runtime will.

* **Return type:**
  [`Clip`](an.adapters.cutout.clip.md#an.adapters.cutout.clip.Clip)

### an.adapters.cutout.timeline.evaluate_timeline(timeline, t)

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
  the pose, and its value is the node’s own (`transform_of` reads it
  from the document; `runtime.js` restores what it built).

Keys that write the same thing on one node ([`write_group()`](#an.adapters.cutout.timeline.write_group): the swap
sets of one visual, `rotation`/`rotation_rad`) keep only the most
recently WRITTEN — an ended `viseme@happy` span does not outlive the
`viseme` track that took the mouth back.

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
>>> from an.adapters.cutout.channel import Channel, Keyframe
>>> from an.adapters.cutout.clip import Clip
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
  `dict`[`tuple`[`str`, `str`], `Any`]

### an.adapters.cutout.timeline.screen_position(scene, path, , pose=None, point=(0.0, 0.0))

Where `point` in `path`’s local space lands on the canvas.

The composition the runtime performs, walked from the node up to `root`
and then offset by the canvas centre — which is where `runtime.js` places
the root container.

`pose` is keyed by the FULL path (`"street/hills"`), matching what
`evaluate_timeline` returns, and each node reads only its own entry.

* **Return type:**
  `tuple`[`float`, `float`]

```pycon
>>> from an.adapters.cutout.serialize import CutoutSceneJSON, NodeJSON, TimelineJSON, TransformJSON
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

### an.adapters.cutout.timeline.timeline_from_scene(scene)

The compiled scene’s `timeline`/`animations` as this module’s `Timeline`.

`compile_shot` produces a serialisable document (`an.adapters.cutout.serialize`)
for the JS runtime; this rebuilds the *evaluable* form, so a caller can ask
what a compiled scene’s pose is at time `t` without a browser. It is the
Python side of the parity contract: `evaluate_timeline` over this object is
the executable spec `runtime.js` is tested against.

Two fields are carried rather than defaulted, and both have cost a bug:
`loop_mode` (without it every loop evaluated as `once` — an#7) and a
list-valued `easing`, which is a cubic-bezier control quadruple and must
stay a tuple for `Keyframe`.

* **Return type:**
  [`Timeline`](#an.adapters.cutout.timeline.Timeline)

```pycon
>>> from an.adapters.cutout.compile import compile_shot
>>> from an.ir.compose import tween
>>> from an.ir.schema import Shot
>>> shot = Shot(id="s1", renderer="cutout", duration=2.0,
...             actions=[tween("root", "x", 10.0, 1.0, from_=0.0)])
>>> scene = compile_shot(shot, mall=None, fps=24)
>>> evaluate_timeline(timeline_from_scene(scene), 0.5)[("root", "x")]
5.0
```

### an.adapters.cutout.timeline.transform_of(node, pose=None)

A node’s transform, with `pose` overriding what the document declares.

The runtime applies a pose value by assigning the property on the display
object, so a channel REPLACES the declared value rather than adding to it —
which is why the parallax compensation carries the plane’s own offset in
every keyframe instead of an offset from it.

* **Return type:**
  [`Transform2D`](#an.adapters.cutout.timeline.Transform2D)

### an.adapters.cutout.timeline.write_group(prop)

What `prop` writes on its node — see [`SWAP_WRITE_GROUP`](#an.adapters.cutout.timeline.SWAP_WRITE_GROUP).

* **Return type:**
  `str`

```pycon
>>> write_group("x"), write_group("rotation_rad"), write_group("viseme@happy")
('x', 'rotation', '<swap>')
```
