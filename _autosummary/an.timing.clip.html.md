# an.timing.clip

Clip: a named bundle of channels with a duration and loop mode.

A clip is what you’d call an “animation” in Spine / Rive terminology — a
reusable unit (e.g. `"walk_cycle"`, `"wave"`). Evaluating a clip at time
`t` produces a `Pose` by evaluating each of its channels at `t`.

Loop modes:

- `LoopMode.ONCE` — past `duration`, the last frame holds.
- `LoopMode.LOOP` — `t` wraps modulo `duration`.
- `LoopMode.PING_PONG` — `t` ping-pongs over `[0, duration]`.

```pycon
>>> from an.timing.channel import Channel, Keyframe
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> clip = Clip("walk", duration=1.0, channels=[ch], loop_mode=LoopMode.LOOP)
>>> evaluate(clip, 0.5)[("a", "x")]
5.0
>>> evaluate(clip, 1.25)[("a", "x")]  # loop wraps
2.5
```

### Module Attributes

| [`Pose`](#an.timing.clip.Pose)                              | Mapping of (target_path, property_name) -> value — the universal output of animation evaluation.                          |
|------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| [`KindOf`](#an.timing.clip.KindOf)                            | the declared kind of each channel.                                                                                        |
| [`wrap_time`](#an.timing.clip.wrap_time)(t, duration, loop_mode) | The public name of the loop rule (the contract's; `_wrap_time` is kept for the callers and tests that already import it). |

### Functions

| [`evaluate`](#an.timing.clip.evaluate)(clip, t, \*[, kind_of])   | Evaluate `clip` at time `t`, returning a `Pose`.                                                                          |
|-------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| [`merge_poses`](#an.timing.clip.merge_poses)(\*poses)               | Merge multiple poses with **override semantics** (later wins per key).                                                    |
| [`wrap_time`](#an.timing.clip.wrap_time)(t, duration, loop_mode)  | The public name of the loop rule (the contract's; `_wrap_time` is kept for the callers and tests that already import it). |

### Classes

| [`Clip`](#an.timing.clip.Clip)(name, duration[, channels, loop_mode])   | Named animation: a duration + a bundle of channels.   |
|------------------------------------------------------------------------------------------------|-------------------------------------------------------|
| [`LoopMode`](#an.timing.clip.LoopMode)(\*values)                            | How a clip behaves past its natural duration.         |

### *class* an.timing.clip.Clip(name, duration, channels=<factory>, loop_mode=LoopMode.ONCE)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Named animation: a duration + a bundle of channels.

### an.timing.clip.KindOf

the declared kind of each channel.

* **Type:**
  `(target, property) -> FieldKind`

alias of `Callable`[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)]

### *class* an.timing.clip.LoopMode(\*values)

Bases: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Enum`](https://docs.python.org/3/library/enum.html#enum.Enum)

How a clip behaves past its natural duration.

### an.timing.clip.Pose

Mapping of (target_path, property_name) -> value — the universal output of
animation evaluation. Application happens in `runtime.js` (`applyPose`);
the Python side only ever *produces* poses (an#86 deleted the Python
applier, which structurally could not apply swap or alpha values).

alias of [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.timing.clip.evaluate(clip, t, , kind_of=None)

Evaluate `clip` at time `t`, returning a `Pose`.

`kind_of` declares each channel’s field kind; `None` interpolates by
value type, as `runtime.js` does (see [`an.timing.channel`](an.timing.channel.html.md#module-an.timing.channel)).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.timing.clip.merge_poses(\*poses)

Merge multiple poses with **override semantics** (later wins per key).

Used by the timeline to combine concurrent clips on the same target.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> merge_poses({("a", "x"): 1.0}, {("a", "x"): 2.0, ("a", "y"): 3.0})
{('a', 'x'): 2.0, ('a', 'y'): 3.0}
```

### an.timing.clip.wrap_time(t, duration, loop_mode)

The public name of the loop rule (the contract’s; `_wrap_time` is kept for
the callers and tests that already import it).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)
