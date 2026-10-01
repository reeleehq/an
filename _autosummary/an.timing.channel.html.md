# an.timing.channel

Channel: keyframes for a single (target, property) pair, evaluated at time t.

A channel holds a sorted list of `Keyframe`s. ``evaluate(channel, t)`` does a
binary search to find the surrounding keyframes, applies the easing for that
segment, and interpolates between the two values. Keys are half-open: the
segment `[a.time, b.time)` belongs to `a`; before the first key the first
value holds, from the last key on the last value holds; a zero-span segment
(two keys at one time) resolves to the later key.

**Who picks the interpolator.** Two rules, one per caller:

- `kind=None` — **by value type**, the rule `runtime.js`’s
  `evaluateChannel` implements, and the default because this function is that
  port’s executable spec (`tests/test_cutout_channel_parity.py` runs the real
  extracted JS against it). Numbers (`int`/`float`, excluding `bool`)
  interpolate through the segment’s easing; everything else holds `a` for
  exactly `[a.time, b.time)` and switches at `b.time`. Being runtime.js’s
  rule, it accepts only runtime.js’s easings
  ([`VALUE_TYPED_EASINGS`](an.timing.easing.html.md#an.timing.easing.VALUE_TYPED_EASINGS)): a curve the stage cannot
  draw raises here, as it does in the browser, instead of yielding a pose.
- `kind=<FieldKind>` — **by declaration** ([`an.timing.kinds`](an.timing.kinds.html.md#module-an.timing.kinds)), the
  kernel contract’s rule: the declared kind interpolates, a discrete kind
  switches on time, and the first instant of a segment is the key it leaves.
  The stage’s declarations (`stage.node`) give the same values as the
  value-type rule on everything the stage compiler emits; a test holds that.

In both, the snap of a held value compares `t` against a TIME, never an eased
or derived parameter, because each indirection was measured wrong: an
overshooting cubic-bezier easing crosses 1.0 mid-segment (showing the *second*
key early, or flapping A→B→A within one segment), and even the raw
`(t - a.time) / span` can round up to 1.0 while `t < b.time`. And in both,
the easing is *validated* on every segment (an unknown spec raises) so a typo’d
easing name stays loud on a swap channel too.

`bool` keyframe values are refused upstream by the stage compiler: Python’s
`isinstance(True, int)` would lerp what JS’s `typeof` snaps.

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
>>> from an.timing.kinds import AngleKind
>>> spin = Channel("a", "yaw", [Keyframe(0.0, 350.0), Keyframe(1.0, 10.0)])
>>> evaluate(spin, 0.5), evaluate(spin, 0.5, kind=AngleKind())
(180.0, 360.0)
```

### Functions

| [`check_channel`](#an.timing.channel.check_channel)(channel, kind)     | Why `channel`'s keyframe values do not fit `kind` (empty if they do).   |
|-----------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`evaluate`](#an.timing.channel.evaluate)(channel, t, \*[, kind]) | Evaluate `channel` at time `t` (see the module docstring for `kind`).   |

### Classes

| [`Channel`](#an.timing.channel.Channel)(target, property[, keyframes])   | Sorted keyframes for one property of one target.        |
|-------------------------------------------------------------------------------------------|---------------------------------------------------------|
| [`Keyframe`](#an.timing.channel.Keyframe)(time, value[, easing])          | One keyframe: time, value, optional per-segment easing. |

### *class* an.timing.channel.Channel(target, property, keyframes=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Sorted keyframes for one property of one target.

Construction validates that `keyframes` is non-empty and sorted.

### *class* an.timing.channel.Keyframe(time, value, easing=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One keyframe: time, value, optional per-segment easing.

The easing on a keyframe describes the curve **leaving** that keyframe
toward the next one. The last keyframe’s easing is therefore unused.

### an.timing.channel.check_channel(channel, kind)

Why `channel`’s keyframe values do not fit `kind` (empty if they do).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.timing.channel.evaluate(channel, t, , kind=None)

Evaluate `channel` at time `t` (see the module docstring for `kind`).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)
