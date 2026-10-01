# an.timing

The timing kernel: what is on screen at time `t`, as a pure function.

The heart of the core (core study §3, layer K; ADR 0001 decisions 10-11). Every
genre that can answer “what is the value of this property at time t” does it the
same way: **addressed** properties ([`address`](an.timing.address.html.md#module-an.timing.address)), each of a
declared **field kind** ([`kinds`](an.timing.kinds.html.md#module-an.timing.kinds)) chosen by its entity kind’s
**property space** ([`spaces`](an.timing.spaces.html.md#module-an.timing.spaces)), keyed over time with **easing**
([`easing`](an.timing.easing.html.md#module-an.timing.easing)), flattened to absolute times
([`flat`](an.timing.flat.html.md#module-an.timing.flat)), compiled to tracks of placed clips of channels
([`channel`](an.timing.channel.html.md#module-an.timing.channel), [`clip`](an.timing.clip.html.md#module-an.timing.clip), [`timeline`](an.timing.timeline.html.md#module-an.timing.timeline))
and evaluated by `evaluate_timeline(timeline, t)` — sparse: a property nothing
has started writing is absent, and the entity’s rest state supplies it.

The kernel is a **cross-language contract** before it is code: five JSON files
in `an/data/timing/` generated from these registries ([`contract`](an.timing.contract.html.md#module-an.timing.contract)),
which a second implementation (TypeScript) asserts. `runtime.js` — the stage
engine’s evaluator — is a bit-exact port of this package’s value-typed rule, and
its parity tests hold it there.

The frame clock is `an`’s: frame `k` at `k / fps`, `frame_count = max(1,
round(duration * fps))` ([`an.frame_clock`](an.frame_clock.html.md#module-an.frame_clock)).

```pycon
>>> from an.timing import Channel, Keyframe, evaluate_channel, get_space
>>> ch = Channel("charlie", "x", [Keyframe(0.0, 0.0, "ease_in_out"), Keyframe(1.0, 10.0)])
>>> evaluate_channel(ch, 0.25, kind=get_space("stage.node").kind_of("x"))
1.25
```

### Functions

| [`format_address`](#an.timing.format_address)(target, prop)                       | The address string of a compiled `(target, property)` pair, unvalidated (the fast path for keying states; [`Address.of()`](#an.timing.Address.of) validates).   |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`parse_address`](#an.timing.parse_address)(text)                                | `text` as an [`Address`](#an.timing.Address); raises [`AddressError`](#an.timing.AddressError) naming the fault.                         |
| [`check_channel`](#an.timing.check_channel)(channel, kind)                       | Why `channel`'s keyframe values do not fit `kind` (empty if they do).                                                                                                                 |
| [`evaluate_channel`](#an.timing.evaluate_channel)(channel, t, \*[, kind])           | Evaluate `channel` at time `t` (see the module docstring for `kind`).                                                                                                                 |
| [`merge_poses`](#an.timing.merge_poses)(\*poses)                               | Merge multiple poses with **override semantics** (later wins per key).                                                                                                                |
| [`wrap_time`](#an.timing.wrap_time)(t, duration, loop_mode)                  | The public name of the loop rule (the contract's; `_wrap_time` is kept for the callers and tests that already import it).                                                             |
| [`evaluate_clip`](#an.timing.evaluate_clip)(clip, t, \*[, kind_of])              | Evaluate `clip` at time `t`, returning a `Pose`.                                                                                                                                      |
| [`apply_easing`](#an.timing.apply_easing)(spec, t, \*[, names])                 | Apply an easing spec to a normalised parameter `t` in `[0, 1]`.                                                                                                                       |
| [`easing_entries`](#an.timing.easing_entries)(\*[, owner])                        | Every registered entry in registration order; only `owner`'s when given.                                                                                                              |
| [`easing_entry`](#an.timing.easing_entry)(name)                                 | The registered entry called `name`.                                                                                                                                                   |
| [`register_easing`](#an.timing.register_easing)(entry, \*[, replace, owner])       | Add `entry` to the registry (a genre's own curves register here).                                                                                                                     |
| [`resolve_easing`](#an.timing.resolve_easing)(spec)                               | The curve an easing spec names.                                                                                                                                                       |
| [`kind_from_spec`](#an.timing.kind_from_spec)(spec)                               | A kind instance from its contract spec (`{"kind": name, **params}`), a bare kind name, or an instance (returned as is).                                                               |
| [`kind_names`](#an.timing.kind_names)(\*[, owner])                            | The registered kind names in registration order; only `owner`'s when given.                                                                                                           |
| [`register_kind`](#an.timing.register_kind)(name, factory, \*[, replace, owner]) | Register a field kind under `name` (how a genre adds one).                                                                                                                            |
| `get_space`(name)                                                                                   |                                                                                                                                                                                       |
| [`register_space`](#an.timing.register_space)(space, \*[, replace, owner])        | Register `space` under its name (how an entity kind declares its properties).                                                                                                         |
| [`space_from_json`](#an.timing.space_from_json)(doc)                               | A space from its JSON form (what `PropertySpace.to_json()` writes).                                                                                                                   |
| [`space_names`](#an.timing.space_names)(\*[, owner])                           | The registered space names in registration order; only `owner`'s when given.                                                                                                          |
| [`clip_from_json`](#an.timing.clip_from_json)(anim, \*[, name])                   | One compiled animation (`compiled.schema.json`'s `animation`) as a [`Clip`](#an.timing.Clip).                                                             |
| [`evaluate_timeline`](#an.timing.evaluate_timeline)(timeline, t, \*[, space])        | Evaluate `timeline` at time `t`, merging poses across tracks/clips.                                                                                                                   |
| [`timeline_from_compiled`](#an.timing.timeline_from_compiled)(doc)                        | The compiled document's `timeline`/`animations` as an evaluable `Timeline`.                                                                                                           |

### Classes

| [`Address`](#an.timing.Address)(entity[, nodes, field, qualifier])    | A parsed address.                                                                       |
|------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`Channel`](#an.timing.Channel)(target, property[, keyframes])        | Sorted keyframes for one property of one target.                                        |
| [`Keyframe`](#an.timing.Keyframe)(time, value[, easing])               | One keyframe: time, value, optional per-segment easing.                                 |
| [`Clip`](#an.timing.Clip)(name, duration[, channels, loop_mode])   | Named animation: a duration + a bundle of channels.                                     |
| [`LoopMode`](#an.timing.LoopMode)(\*values)                            | How a clip behaves past its natural duration.                                           |
| [`EasingEntry`](#an.timing.EasingEntry)(name, curve, family, solver, ...) | One named easing: its curve, where it comes from, and how it is solved.                 |
| [`AngleKind`](#an.timing.AngleKind)([unit, wrap])                       | An angle: the shortest arc when `wrap`, else the raw numbers.                           |
| [`ColorKind`](#an.timing.ColorKind)([space])                            | A colour (hex or `[r, g, b, a?]` in 0..1), written back in the form of the start value. |
| [`DiscreteKind`](#an.timing.DiscreteKind)([switch_at])                     | Holds `a` and switches to `b` on TIME (see the module docstring).                       |
| [`FieldKind`](#an.timing.FieldKind)()                                   | Base of every field kind: a frozen, hashable, JSON-describable interpolator.            |
| [`NumberKind`](#an.timing.NumberKind)([space])                           | A continuous scalar.                                                                    |
| [`OrbitKind`](#an.timing.OrbitKind)([unit])                             | A camera orbiting a target: `{azimuth, elevation, distance, target?}`.                  |
| [`QuaternionKind`](#an.timing.QuaternionKind)()                              | A unit quaternion `[x, y, z, w]`, interpolated by slerp after a sign fix.               |
| [`Segment`](#an.timing.Segment)(t, start, end)                        | Where an evaluation sits: time `t` inside the segment `[start, end)`.                   |
| [`VectorKind`](#an.timing.VectorKind)()                                  | A fixed-length list of numbers, interpolated componentwise.                             |
| [`FieldDecl`](#an.timing.FieldDecl)(pattern, kind[, unit, writes, ...]) | One declaration of a property space: pattern -> kind, write group, unit.                |
| [`PropertySpace`](#an.timing.PropertySpace)(name[, fields, version, ...])   | An entity kind's properties: declarations, matched exact-first then by glob.            |
| [`PlacedClip`](#an.timing.PlacedClip)(clip[, start_time, duration, ...]) | A clip placed at an absolute time on a track.                                           |
| [`Timeline`](#an.timing.Timeline)(duration[, tracks])                  | A duration + ordered list of tracks.                                                    |
| [`Track`](#an.timing.Track)([target_root, clips])                   | A sequence of placed clips that share a common purpose / target prefix.                 |

### Exceptions

| [`AddressError`](#an.timing.AddressError)       | A string is not an address under the grammar.                               |
|---------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`UnknownEasingError`](#an.timing.UnknownEasingError) | An easing spec names no registered curve and parses as no parametrised one. |
| [`FieldKindError`](#an.timing.FieldKindError)     | A kind spec is malformed, or names no registered kind.                      |
| [`SpaceError`](#an.timing.SpaceError)         | A property space is malformed, unknown, or already registered.              |

### *class* an.timing.Address(entity, nodes=(), field='', qualifier=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A parsed address. `str(address)` writes it back unchanged.

#### *property* field_path *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

The dotted field, split.

#### *classmethod* of(target, prop)

The address of a compiled `(target, property)` pair (validated).

* **Return type:**
  [`Address`](an.timing.address.html.md#an.timing.address.Address)

#### *property* property *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

the field and its qualifier.

* **Type:**
  The compiled form’s `property`

#### *property* target *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

the entity and its node path.

* **Type:**
  The compiled form’s `target`

### *exception* an.timing.AddressError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A string is not an address under the grammar.

### *class* an.timing.AngleKind(unit='deg', wrap=True)

Bases: [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)

An angle: the shortest arc when `wrap`, else the raw numbers. Interpolated
angles are not re-normalised (350 -> 10 passes through 360).

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### *class* an.timing.Channel(target, property, keyframes=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Sorted keyframes for one property of one target.

Construction validates that `keyframes` is non-empty and sorted.

### *class* an.timing.Clip(name, duration, channels=<factory>, loop_mode=LoopMode.ONCE)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Named animation: a duration + a bundle of channels.

### *class* an.timing.ColorKind(space='oklab')

Bases: [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)

A colour (hex or `[r, g, b, a?]` in 0..1), written back in the form of
the start value. `oklab` mixes perceptually with premultiplied alpha;
`srgb` lerps the encoded channels (Manim’s and the stage tint’s rule).

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### *class* an.timing.DiscreteKind(switch_at=0.5)

Bases: [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)

Holds `a` and switches to `b` on TIME (see the module docstring).

`switch_at` lies in `(0, 1]`. The default, 0.5, is the switch point of an
undeclared property; a replacement drawing (a swap set) declares 1, so it
never appears before its own key.

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### switches *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[[bool](https://docs.python.org/3/builtins/functions.html#bool)]* *= True*

True when the value (or part of it) switches on TIME rather than moving.

### *class* an.timing.EasingEntry(name, curve, family, solver, description, version=1, params=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One named easing: its curve, where it comes from, and how it is solved.

`version` follows ADR 0003: an entry whose meaning changes gets a new
version, so a shot that names it re-renders visibly instead of silently.

#### to_json()

The entry as the contract file lists it (without samples).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *class* an.timing.FieldDecl(pattern, kind, unit=None, writes=None, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One declaration of a property space: pattern -> kind, write group, unit.

#### writes *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The write group this property belongs to; `None` means itself.

### *class* an.timing.FieldKind

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Base of every field kind: a frozen, hashable, JSON-describable interpolator.

Subclasses set `name` and implement [`interpolate()`](#an.timing.FieldKind.interpolate); the dataclass
fields are the kind’s parameters, and `to_spec()` writes them as the
contract does (`{"kind": name, **non-default params}`).

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### switches *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[[bool](https://docs.python.org/3/builtins/functions.html#bool)]* *= False*

True when the value (or part of it) switches on TIME rather than moving.

### *exception* an.timing.FieldKindError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A kind spec is malformed, or names no registered kind.

### *class* an.timing.Keyframe(time, value, easing=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One keyframe: time, value, optional per-segment easing.

The easing on a keyframe describes the curve **leaving** that keyframe
toward the next one. The last keyframe’s easing is therefore unused.

### *class* an.timing.LoopMode(\*values)

Bases: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Enum`](https://docs.python.org/3/library/enum.html#enum.Enum)

How a clip behaves past its natural duration.

### *class* an.timing.NumberKind(space='linear')

Bases: [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)

A continuous scalar. `space="log"` interpolates the logarithm (zoom, scale).

Linear interpolation is `a + (b - a) * u` with no special case at the ends,
which is the stage runtime’s arithmetic: a declared `number` channel is
bit-identical to what `runtime.js` draws.

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### *class* an.timing.OrbitKind(unit='deg')

Bases: [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)

A camera orbiting a target: `{azimuth, elevation, distance, target?}`.

Azimuth takes the shortest arc, elevation is lerped and clamped to the poles,
distance is lerped in log, target componentwise. Any other member is discrete
and switches at `DEFAULT_SWITCH_AT` (on time). One value: a dotted
address never reaches inside it.

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

#### switches *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[[bool](https://docs.python.org/3/builtins/functions.html#bool)]* *= True*

True when the value (or part of it) switches on TIME rather than moving.

### *class* an.timing.PlacedClip(clip, start_time=0.0, duration=None, speed=1.0, blend_in=0.0, blend_out=0.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A clip placed at an absolute time on a track.

#### *property* effective_duration *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Duration this clip occupies on the timeline (after speed scaling).

### *class* an.timing.PropertySpace(name, fields=(), version=1, description='', undeclared=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An entity kind’s properties: declarations, matched exact-first then by glob.

#### declaration(prop)

The declaration governing `prop`, or `None`.

* **Return type:**
  [`FieldDecl`](an.timing.spaces.html.md#an.timing.spaces.FieldDecl) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### undeclared *: [FieldKind](an.timing.kinds.html.md#an.timing.kinds.FieldKind)*

The kind of a property no declaration matches.

### *class* an.timing.QuaternionKind

Bases: [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)

A unit quaternion `[x, y, z, w]`, interpolated by slerp after a sign fix.

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### *class* an.timing.Segment(t, start, end)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Where an evaluation sits: time `t` inside the segment `[start, end)`.

#### switched(switch_at)

Whether a discrete value has switched to the segment’s second key.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> Segment(0.5, 0.0, 1.0).switched(0.5), Segment(0.49, 0.0, 1.0).switched(0.5)
(True, False)
>>> Segment(0.9999999999, 0.0, 1.0).switched(1.0)  # only at b.time itself
False
```

### *exception* an.timing.SpaceError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A property space is malformed, unknown, or already registered.

### *class* an.timing.Timeline(duration, tracks=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A duration + ordered list of tracks. The canonical playback structure.

### *class* an.timing.Track(target_root='', clips=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A sequence of placed clips that share a common purpose / target prefix.

`target_root` is informational metadata for downstream tools (the JS
runtime can use it to scope rendering); evaluation does not filter by it.

### *exception* an.timing.UnknownEasingError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

An easing spec names no registered curve and parses as no parametrised one.

### *class* an.timing.VectorKind

Bases: [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)

A fixed-length list of numbers, interpolated componentwise.

#### check(value)

Why `value` is not valid for this kind, or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### interpolate(a, b, u, seg)

The value between keys `a` and `b` at eased progress `u`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.timing.apply_easing(spec, t, , names=None)

Apply an easing spec to a normalised parameter `t` in `[0, 1]`.

`names` restricts the string specs accepted to that collection — what an
engine that implements only part of the registry passes (the stage runtime
implements the legacy names; see `an.adapters.cutout.easing`). Sequences
always take the legacy Bézier solver.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> apply_easing(None, 0.25)
0.25
>>> apply_easing("step", 0.99), apply_easing("step", 1.0)
(0.0, 1.0)
>>> apply_easing("smooth", 0.5, names={"linear"})
Traceback (most recent call last):
 ...
an.timing.easing.UnknownEasingError: unknown easing preset 'smooth'; known: ['linear']
```

### an.timing.check_channel(channel, kind)

Why `channel`’s keyframe values do not fit `kind` (empty if they do).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.timing.clip_from_json(anim, , name=None)

One compiled animation (`compiled.schema.json`’s `animation`) as a [`Clip`](#an.timing.Clip).

Accepts the JSON mapping or any object with the same attributes (the stage’s
`AnimationClipJSON`). Two fields are carried rather than defaulted, and
both have cost a bug: `loop_mode` (without it every loop evaluated as
`once` — an#7) and a list-valued `easing`, which is a cubic-bezier
control quadruple and must stay a tuple for `Keyframe`. The stage compiler
reads a from-less tween’s start through this too (an#212), so it evaluates
exactly what the runtime will.

* **Return type:**
  [`Clip`](an.timing.clip.html.md#an.timing.clip.Clip)

### an.timing.easing_entries(, owner=None)

Every registered entry in registration order; only `owner`’s when given.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`EasingEntry`](an.timing.easing.html.md#an.timing.easing.EasingEntry), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.timing.easing_entry(name)

The registered entry called `name`.

* **Return type:**
  [`EasingEntry`](an.timing.easing.html.md#an.timing.easing.EasingEntry)

```pycon
>>> easing_entry("ease").family
'legacy'
```

### an.timing.evaluate_channel(channel, t, , kind=None)

Evaluate `channel` at time `t` (see the module docstring for `kind`).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.timing.evaluate_clip(clip, t, , kind_of=None)

Evaluate `clip` at time `t`, returning a `Pose`.

`kind_of` declares each channel’s field kind; `None` interpolates by
value type, as `runtime.js` does (see [`an.timing.channel`](an.timing.channel.html.md#module-an.timing.channel)).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.timing.evaluate_timeline(timeline, t, , space=None)

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

`space` says what each property is ([`an.timing.spaces`](an.timing.spaces.html.md#module-an.timing.spaces)): one space, a
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

### an.timing.format_address(target, prop)

The address string of a compiled `(target, property)` pair, unvalidated
(the fast path for keying states; [`Address.of()`](#an.timing.Address.of) validates).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.timing.kind_from_spec(spec)

A kind instance from its contract spec (`{"kind": name, **params}`),
a bare kind name, or an instance (returned as is).

* **Return type:**
  [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)

```pycon
>>> kind_from_spec("discrete")
DiscreteKind(switch_at=0.5)
>>> kind_from_spec({"kind": "points"})
Traceback (most recent call last):
 ...
an.timing.kinds.FieldKindError: unknown field kind 'points'; known: ['number', 'angle', 'vector', 'quaternion', 'color', 'orbit', 'discrete']
```

### an.timing.kind_names(, owner=None)

The registered kind names in registration order; only `owner`’s when given.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.timing.merge_poses(\*poses)

Merge multiple poses with **override semantics** (later wins per key).

Used by the timeline to combine concurrent clips on the same target.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> merge_poses({("a", "x"): 1.0}, {("a", "x"): 2.0, ("a", "y"): 3.0})
{('a', 'x'): 2.0, ('a', 'y'): 3.0}
```

### an.timing.parse_address(text)

`text` as an [`Address`](#an.timing.Address); raises [`AddressError`](#an.timing.AddressError) naming the fault.

* **Return type:**
  [`Address`](an.timing.address.html.md#an.timing.address.Address)

```pycon
>>> parse_address("charlie/left_arm:rotation").target
'charlie/left_arm'
>>> parse_address("a::b")
Traceback (most recent call last):
 ...
an.timing.address.AddressError: 'a::b': an address has exactly one ':', found 2
```

### an.timing.register_easing(entry, , replace=False, owner=None)

Add `entry` to the registry (a genre’s own curves register here).

Re-registering a name is refused unless `replace=True`, and a replacement
must carry a HIGHER version: a name’s meaning changing under a scene that
uses it is exactly what entry versions exist to make visible, so it must be
deliberate and visible. `owner` names who registered it (core entries:
`CORE_OWNER`); only core entries reach the contract files.

* **Return type:**
  [`EasingEntry`](an.timing.easing.html.md#an.timing.easing.EasingEntry)

### an.timing.register_kind(name, factory, , replace=False, owner=None)

Register a field kind under `name` (how a genre adds one).

`owner` names who registered it; only `CORE_OWNER`’s kinds reach
`an`’s contract files.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`FieldKind`](an.timing.kinds.html.md#an.timing.kinds.FieldKind)]

```pycon
>>> sorted(kind_names())[:3]
['angle', 'color', 'discrete']
```

### an.timing.register_space(space, , replace=False, owner=None)

Register `space` under its name (how an entity kind declares its properties).

`owner` names who registered it; only `CORE_OWNER`’s spaces reach
`an`’s contract files, so an installed genre never edits the core contract.

* **Return type:**
  [`PropertySpace`](an.timing.spaces.html.md#an.timing.spaces.PropertySpace)

### an.timing.resolve_easing(spec)

The curve an easing spec names.

- `None` -> linear;
- a registered name, `cubic-bezier(x1, y1, x2, y2)` or `steps(n[, position])`;
- a 4-sequence `[cx1, cy1, cx2, cy2]` -> the legacy Bézier solver.

Raises [`UnknownEasingError`](#an.timing.UnknownEasingError) (a `ValueError`) for an unknown name or
a malformed sequence, `TypeError` for any other type.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`float`](https://docs.python.org/3/builtins/functions.html#float)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.timing.space_from_json(doc)

A space from its JSON form (what `PropertySpace.to_json()` writes).

* **Return type:**
  [`PropertySpace`](an.timing.spaces.html.md#an.timing.spaces.PropertySpace)

### an.timing.space_names(, owner=None)

The registered space names in registration order; only `owner`’s when given.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.timing.timeline_from_compiled(doc)

The compiled document’s `timeline`/`animations` as an evaluable `Timeline`.

`doc` is the JSON mapping of `compiled.schema.json` or any object with
the same attributes (the stage’s `CutoutSceneJSON`). This is the Python
side of the parity contract: `evaluate_timeline` over what it returns is
the executable spec `runtime.js` is tested against.

`target_root` and the blend ramps are carried although nothing reads them
yet: a reader that quietly drops a field it was handed is a lossy “rebuilds
the evaluable form”.

* **Return type:**
  [`Timeline`](an.timing.timeline.html.md#an.timing.timeline.Timeline)

```pycon
>>> doc = {"timeline": {"duration": 1.0, "tracks": [{"clips": [
...     {"animation_id": "m", "start_time": 0.0}]}]},
...     "animations": {"m": {"duration": 1.0, "channels": [{"target": "a",
...     "property": "x", "keyframes": [{"time": 0.0, "value": 0.0},
...     {"time": 1.0, "value": 4.0}]}]}}}
>>> evaluate_timeline(timeline_from_compiled(doc), 0.25)
{('a', 'x'): 1.0}
```

### an.timing.wrap_time(t, duration, loop_mode)

Apply the loop mode to `t`, returning a time within `[0, duration]`.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### Modules

| [`address`](an.timing.address.html.md#module-an.timing.address)   | The address grammar: one way to name an animatable value, in every genre.                    |
|-------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| [`channel`](an.timing.channel.html.md#module-an.timing.channel)   | Channel: keyframes for a single (target, property) pair, evaluated at time t.                |
| [`clip`](an.timing.clip.html.md#module-an.timing.clip)         | Clip: a named bundle of channels with a duration and loop mode.                              |
| [`contract`](an.timing.contract.html.md#module-an.timing.contract) | The timing kernel's cross-language contract: five JSON files, generated from the registries. |
| [`easing`](an.timing.easing.html.md#module-an.timing.easing)     | The easing registry: every named timing curve, each with the solver that computes it.        |
| [`flat`](an.timing.flat.html.md#module-an.timing.flat)         | The authored flat timeline: `(start, end, address, change)` rows.                            |
| [`kinds`](an.timing.kinds.html.md#module-an.timing.kinds)       | Field kinds: the declared interpolator of each animatable property.                          |
| [`spaces`](an.timing.spaces.html.md#module-an.timing.spaces)     | Property spaces: what an entity kind's properties ARE, declared once.                        |
| [`timeline`](an.timing.timeline.html.md#module-an.timing.timeline) | Timeline: tracks of placed clips with absolute times — the compiled evaluation form.         |
