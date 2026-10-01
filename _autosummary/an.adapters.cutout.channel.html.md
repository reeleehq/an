# an.adapters.cutout.channel

Channel: keyframes for a single (target, property) pair, evaluated at time t.

A channel holds a sorted list of `Keyframe`s. ``evaluate(channel, t)`` does a
binary search to find the surrounding keyframes, applies the easing for that
segment, and lerps between the two values.

\*\*This module is the executable spec of `runtime.js`’s `evaluateChannel``**
— the browser implementation must stay behaviourally identical, and
``tests/test_cutout_channel_parity.py` runs the real extracted JS against this
one to pin it (the same harness pattern that pins `wrapTime`).

Two value classes, two rules:

- **Numeric** (`int`/`float`, excluding `bool`): true interpolation
  through the segment’s easing.
- **Everything else** (strings — viseme codes, swap keys): the value holds
  `a` for exactly `[a.time, b.time)` and switches at `b.time`.
  **Easing does not apply** — the snap compares `t` against `b.time`
  directly, never an eased or derived parameter, because each indirection was
  measured wrong: an overshooting cubic-bezier easing crosses 1.0 mid-segment
  (showing the *second* key early, or flapping A→B→A within one segment), and
  even the raw `(t - a.time) / span` can round up to 1.0 while
  `t < b.time`. The time comparison has no intermediate arithmetic, so step
  semantics is a theorem here, not a convention. The easing is still
  *validated* (an unknown spec raises) so a typo’d easing name stays loud on
  every channel.

`bool` keyframe values are refused upstream by the compiler
(`compile.py::_check_keyframe_value`): Python’s `isinstance(True, int)`
would lerp what JS’s `typeof` snaps.

```pycon
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> evaluate(ch, 0.5)
5.0
>>> evaluate(ch, -1.0)  # before first → clamps to first value
0.0
>>> evaluate(ch, 99.0)  # after last → clamps to last value
10.0
>>> sw = Channel("a", "hands", [Keyframe(0.0, "fist"), Keyframe(1.0, "open")])
>>> evaluate(sw, 0.999)  # holds the first key for the whole segment
'fist'
>>> evaluate(sw, 1.0)  # switches exactly at the keyframe
'open'
```

### Functions

| [`evaluate`](#an.adapters.cutout.channel.evaluate)(channel, t)   | Evaluate `channel` at time `t`.   |
|-------------------------------------------------------------------------|-----------------------------------|

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

### an.adapters.cutout.channel.evaluate(channel, t)

Evaluate `channel` at time `t`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)
