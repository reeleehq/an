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

### Functions

| [`evaluate_timeline`](#an.adapters.cutout.timeline.evaluate_timeline)(timeline, t)                  | Evaluate `timeline` at time `t`, merging poses across tracks/clips.       |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`screen_position`](#an.adapters.cutout.timeline.screen_position)(scene, path, \*[, pose, point]) | Where `point` in `path`'s local space lands on the canvas.                |
| [`timeline_from_scene`](#an.adapters.cutout.timeline.timeline_from_scene)(scene)                      | The compiled scene's `timeline`/`animations` as this module's `Timeline`. |
| [`transform_of`](#an.adapters.cutout.timeline.transform_of)(node[, pose])                      | A node's transform, with `pose` overriding what the document declares.    |

### Classes

| [`PlacedClip`](#an.adapters.cutout.timeline.PlacedClip)(clip[, start_time, duration, ...])   | A clip placed at an absolute time on a track.                           |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`Timeline`](#an.adapters.cutout.timeline.Timeline)(duration[, tracks])                    | A duration + ordered list of tracks.                                    |
| [`Track`](#an.adapters.cutout.timeline.Track)([target_root, clips])                     | A sequence of placed clips that share a common purpose / target prefix. |
| [`Transform2D`](#an.adapters.cutout.timeline.Transform2D)([x, y, rotation, scale_x, ...])     | One node's local transform, in the runtime's own vocabulary.            |

### *class* an.adapters.cutout.timeline.PlacedClip(clip, start_time=0.0, duration=None, speed=1.0, blend_in=0.0, blend_out=0.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A clip placed at an absolute time on a track.

#### *property* effective_duration *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Duration this clip occupies on the timeline (after speed scaling).

### *class* an.adapters.cutout.timeline.Timeline(duration, tracks=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A duration + ordered list of tracks. The canonical playback structure.

### *class* an.adapters.cutout.timeline.Track(target_root='', clips=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A sequence of placed clips that share a common purpose / target prefix.

`target_root` is informational metadata for downstream tools (the JS
runtime can use it to scope rendering); evaluation does not filter by it.

### *class* an.adapters.cutout.timeline.Transform2D(x=0.0, y=0.0, rotation=0.0, scale_x=1.0, scale_y=1.0, pivot_x=0.0, pivot_y=0.0)

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

The inverse of [`apply()`](#an.adapters.cutout.timeline.Transform2D.apply) — a parent-space point, in local space.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> t = Transform2D(x=10.0, pivot_x=3.0, scale_x=2.0, rotation=0.4)
>>> round(t.unapply(t.apply((7.0, -2.0)))[0], 9)
7.0
```

### an.adapters.cutout.timeline.evaluate_timeline(timeline, t)

Evaluate `timeline` at time `t`, merging poses across tracks/clips.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.adapters.cutout.timeline.screen_position(scene, path, , pose=None, point=(0.0, 0.0))

Where `point` in `path`’s local space lands on the canvas.

The composition the runtime performs, walked from the node up to `root`
and then offset by the canvas centre — which is where `runtime.js` places
the root container.

`pose` is keyed by the FULL path (`"street/hills"`), matching what
`evaluate_timeline` returns, and each node reads only its own entry.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

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
