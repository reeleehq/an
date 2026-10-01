# an.adapters.cutout.clip

Clips, loop modes and poses — moved to [`an.timing.clip`](an.timing.clip.md#module-an.timing.clip) (the timing kernel).

This path keeps working for every existing caller; new code imports from
`an.timing`.

```pycon
>>> from an.adapters.cutout.channel import Channel, Keyframe
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> clip = Clip("walk", duration=1.0, channels=[ch], loop_mode=LoopMode.LOOP)
>>> evaluate(clip, 1.25)[("a", "x")]  # loop wraps
2.5
```

### Functions

| [`evaluate`](#an.adapters.cutout.clip.evaluate)(clip, t, \*[, kind_of])   | Evaluate `clip` at time `t`, returning a `Pose`.                       |
|-------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`merge_poses`](#an.adapters.cutout.clip.merge_poses)(\*poses)               | Merge multiple poses with **override semantics** (later wins per key). |

### Classes

| [`Clip`](#an.adapters.cutout.clip.Clip)(name, duration[, channels, loop_mode])   | Named animation: a duration + a bundle of channels.   |
|------------------------------------------------------------------------------------------------|-------------------------------------------------------|
| [`LoopMode`](#an.adapters.cutout.clip.LoopMode)(\*values)                            | How a clip behaves past its natural duration.         |

### *class* an.adapters.cutout.clip.Clip(name, duration, channels=<factory>, loop_mode=LoopMode.ONCE)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Named animation: a duration + a bundle of channels.

### *class* an.adapters.cutout.clip.LoopMode(\*values)

Bases: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Enum`](https://docs.python.org/3/library/enum.html#enum.Enum)

How a clip behaves past its natural duration.

### an.adapters.cutout.clip.evaluate(clip, t, , kind_of=None)

Evaluate `clip` at time `t`, returning a `Pose`.

`kind_of` declares each channel’s field kind; `None` interpolates by
value type, as `runtime.js` does (see [`an.timing.channel`](an.timing.channel.md#module-an.timing.channel)).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.adapters.cutout.clip.merge_poses(\*poses)

Merge multiple poses with **override semantics** (later wins per key).

Used by the timeline to combine concurrent clips on the same target.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> merge_poses({("a", "x"): 1.0}, {("a", "x"): 2.0, ("a", "y"): 3.0})
{('a', 'x'): 2.0, ('a', 'y'): 3.0}
```
