# an.adapters.cutout.channel

Channel evaluation — moved to [`an.timing.channel`](an.timing.channel.html.md#module-an.timing.channel) (the timing kernel).

This path keeps working for every existing caller; new code imports from
`an.timing`. \*\*This module’s names are the executable spec of
`runtime.js`’s `evaluateChannel``** (with the default ``kind=None`: by value
type), pinned by `tests/test_cutout_channel_parity.py`.

```pycon
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> evaluate(ch, 0.5)
5.0
```

### Functions

| [`evaluate`](#an.adapters.cutout.channel.evaluate)(channel, t, \*[, kind])   | Evaluate `channel` at time `t` (see the module docstring for `kind`).   |
|-------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`check_channel`](#an.adapters.cutout.channel.check_channel)(channel, kind)       | Why `channel`'s keyframe values do not fit `kind` (empty if they do).   |

### Classes

| [`Channel`](#an.adapters.cutout.channel.Channel)(target, property[, keyframes])   | Sorted keyframes for one property of one target.        |
|-------------------------------------------------------------------------------------------|---------------------------------------------------------|
| [`Keyframe`](#an.adapters.cutout.channel.Keyframe)(time, value[, easing])          | One keyframe: time, value, optional per-segment easing. |

### *class* an.adapters.cutout.channel.Channel(target, property, keyframes=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Sorted keyframes for one property of one target.

Construction validates that `keyframes` is non-empty and sorted.

### *class* an.adapters.cutout.channel.Keyframe(time, value, easing=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One keyframe: time, value, optional per-segment easing.

The easing on a keyframe describes the curve **leaving** that keyframe
toward the next one. The last keyframe’s easing is therefore unused.

### an.adapters.cutout.channel.check_channel(channel, kind)

Why `channel`’s keyframe values do not fit `kind` (empty if they do).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.adapters.cutout.channel.evaluate(channel, t, , kind=None)

Evaluate `channel` at time `t` (see the module docstring for `kind`).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)
