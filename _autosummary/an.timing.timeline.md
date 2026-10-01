# an.timing.timeline

Timeline: tracks of placed clips with absolute times — the compiled evaluation form.

A `Timeline` is a flat description of *what plays when*: tracks of
[`PlacedClip`](#an.timing.timeline.PlacedClip), each a [`Clip`](an.timing.clip.md#an.timing.clip.Clip) at an absolute start,
with a duration override, a speed and recorded blend ramps. It is the level the
stage runtime evaluates (`runtime.js::evaluateTimeline` is a port of
[`evaluate_timeline()`](#an.timing.timeline.evaluate_timeline)) and the level the contract’s golden vectors exercise
(`compiled.schema.json`). Authoring composition trees (`an.ir.compose`) are
flattened into it by a compiler.

`blend_in` and `blend_out` ramps are recorded but **not applied** to pose
values: the timeline produces the raw pose.

```pycon
>>> from an.timing.channel import Channel, Keyframe
>>> from an.timing.clip import Clip
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> clip = Clip("walk", duration=1.0, channels=[ch])
>>> tl = Timeline(duration=2.0, tracks=[Track("a", clips=[PlacedClip(clip, start_time=0.5)])])
>>> evaluate_timeline(tl, 1.0)[("a", "x")]
5.0
```

### Functions

| [`write_group`](#an.timing.timeline.write_group)(prop)                           | What `prop` writes on a STAGE node (the `stage.node` space's groups).       |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`evaluate_timeline`](#an.timing.timeline.evaluate_timeline)(timeline, t, \*[, space]) | Evaluate `timeline` at time `t`, merging poses across tracks/clips.         |
| [`clip_from_json`](#an.timing.timeline.clip_from_json)(anim, \*[, name])            | One compiled animation (`compiled.schema.json`'s `animation`) as a `Clip`.  |
| [`timeline_from_compiled`](#an.timing.timeline.timeline_from_compiled)(doc)                 | The compiled document's `timeline`/`animations` as an evaluable `Timeline`. |

### Classes

| [`PlacedClip`](#an.timing.timeline.PlacedClip)(clip[, start_time, duration, ...])   | A clip placed at an absolute time on a track.                           |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`Track`](#an.timing.timeline.Track)([target_root, clips])                     | A sequence of placed clips that share a common purpose / target prefix. |
| [`Timeline`](#an.timing.timeline.Timeline)(duration[, tracks])                    | A duration + ordered list of tracks.                                    |

### *class* an.timing.timeline.PlacedClip(clip, start_time=0.0, duration=None, speed=1.0, blend_in=0.0, blend_out=0.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A clip placed at an absolute time on a track.

#### *property* effective_duration *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Duration this clip occupies on the timeline (after speed scaling).

### *class* an.timing.timeline.Timeline(duration, tracks=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A duration + ordered list of tracks. The canonical playback structure.

### *class* an.timing.timeline.Track(target_root='', clips=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A sequence of placed clips that share a common purpose / target prefix.

`target_root` is informational metadata for downstream tools (the JS
runtime can use it to scope rendering); evaluation does not filter by it.

### an.timing.timeline.clip_from_json(anim, , name=None)

One compiled animation (`compiled.schema.json`’s `animation`) as a `Clip`.

Accepts the JSON mapping or any object with the same attributes (the stage’s
`AnimationClipJSON`). Two fields are carried rather than defaulted, and
both have cost a bug: `loop_mode` (without it every loop evaluated as
`once` — an#7) and a list-valued `easing`, which is a cubic-bezier
control quadruple and must stay a tuple for `Keyframe`. The stage compiler
reads a from-less tween’s start through this too (an#212), so it evaluates
exactly what the runtime will.

* **Return type:**
  [`Clip`](an.timing.clip.md#an.timing.clip.Clip)

### an.timing.timeline.evaluate_timeline(timeline, t, , space=None)

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
interpolate and its write groups resolve. `None` is the stage runtime’s
rule, which `runtime.js` implements: interpolation by value type, the
`stage.node` write groups.

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

### an.timing.timeline.timeline_from_compiled(doc)

The compiled document’s `timeline`/`animations` as an evaluable `Timeline`.

`doc` is the JSON mapping of `compiled.schema.json` or any object with
the same attributes (the stage’s `CutoutSceneJSON`). This is the Python
side of the parity contract: `evaluate_timeline` over what it returns is
the executable spec `runtime.js` is tested against.

`target_root` and the blend ramps are carried although nothing reads them
yet: a reader that quietly drops a field it was handed is a lossy “rebuilds
the evaluable form”.

* **Return type:**
  [`Timeline`](#an.timing.timeline.Timeline)

```pycon
>>> doc = {"timeline": {"duration": 1.0, "tracks": [{"clips": [
...     {"animation_id": "m", "start_time": 0.0}]}]},
...     "animations": {"m": {"duration": 1.0, "channels": [{"target": "a",
...     "property": "x", "keyframes": [{"time": 0.0, "value": 0.0},
...     {"time": 1.0, "value": 4.0}]}]}}}
>>> evaluate_timeline(timeline_from_compiled(doc), 0.25)
{('a', 'x'): 1.0}
```

### an.timing.timeline.write_group(prop)

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
