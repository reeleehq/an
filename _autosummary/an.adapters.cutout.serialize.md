# an.adapters.cutout.serialize

JSON contract between the Python compiler and the (future) JS runtime.

These Pydantic models describe **exactly** the JSON shape the PixiJS runtime
consumes — nothing more. `compile_shot` produces these objects; the runtime
reads them. The schema is deliberately separate from the cutout-internal
Python evaluation types (`clip.Clip`, `channel.Channel`) so the Python side
can evolve internally without breaking the runtime contract.

This file used to carry a sketched Spine-flavoured swap vocabulary
(`SkinJSON`, `RigJSON`, `CutoutSceneJSON.rigs`, `SlotJSON`/
`NodeJSON.slots`, `current_attachment`) that nothing populated and nothing
read — deleted in an#86 so the *real* swap mechanism (`VisualJSON`’s
per-node asset maps driven by step channels) is the only one the contract
describes. A few declared-but-unwired scalars remain (`PlacedClipJSON.blend_in`
/ `blend_out` — recorded, never applied; `VisualJSON.texture_id`): the same
debt class at smaller scale, kept only because they are field-shaped
placeholders rather than a parallel *vocabulary* for a capability that shipped
elsewhere. Do not add more; a new field needs its producer and its consumer in
the same change.

```pycon
>>> j = CutoutSceneJSON(
...     meta={"fps": 30, "width": 1920, "height": 1080, "duration": 5.0},
...     scene=NodeJSON(name="root"),
...     animations={},
...     timeline=TimelineJSON(duration=5.0, tracks=[]),
...     assets=AssetsJSON(textures={}, audio={}),
... )
>>> from_dict(to_dict(j)) == j
True
```

### Functions

| [`from_dict`](#an.adapters.cutout.serialize.from_dict)(d)   | Rebuild a scene from a plain-dict representation.              |
|-----------------------------------------------------------------|----------------------------------------------------------------|
| [`to_dict`](#an.adapters.cutout.serialize.to_dict)(scene) | Dump a scene to a plain-dict representation (no None pruning). |

### Classes

| [`AnimationClipJSON`](#an.adapters.cutout.serialize.AnimationClipJSON)(\*\*data)   | A named, reusable animation clip.                                          |
|--------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`AssetJSON`](#an.adapters.cutout.serialize.AssetJSON)(\*\*data)           | A single asset (texture / audio file).                                     |
| [`AssetResolutionJSON`](#an.adapters.cutout.serialize.AssetResolutionJSON)(\*\*data) | How one scene entity's store reference actually resolved at compile time.  |
| [`AssetsJSON`](#an.adapters.cutout.serialize.AssetsJSON)(\*\*data)          | Map of asset id → AssetJSON, split by kind.                                |
| [`ChannelJSON`](#an.adapters.cutout.serialize.ChannelJSON)(\*\*data)         | One animated property of one target.                                       |
| [`CutoutSceneJSON`](#an.adapters.cutout.serialize.CutoutSceneJSON)(\*\*data)     | Top-level cutout scene JSON — the JS runtime's input contract.             |
| [`CutoutSceneMetaJSON`](#an.adapters.cutout.serialize.CutoutSceneMetaJSON)(\*\*data) | Per-shot metadata.                                                         |
| [`KeyframeJSON`](#an.adapters.cutout.serialize.KeyframeJSON)(\*\*data)        | Single keyframe in an animation channel.                                   |
| [`NodeJSON`](#an.adapters.cutout.serialize.NodeJSON)(\*\*data)            | One node in the scene tree.                                                |
| [`PathJSON`](#an.adapters.cutout.serialize.PathJSON)(\*\*data)            | A stroked path's drawing instruction (an#160), carried on a `path` visual. |
| [`PlacedClipJSON`](#an.adapters.cutout.serialize.PlacedClipJSON)(\*\*data)      | An animation placed on a track at a specific time.                         |
| [`TimelineJSON`](#an.adapters.cutout.serialize.TimelineJSON)(\*\*data)        | Top-level timeline: total duration + tracks.                               |
| [`TrackJSON`](#an.adapters.cutout.serialize.TrackJSON)(\*\*data)           | A sequence of placed clips with optional target-prefix metadata.           |
| [`TransformJSON`](#an.adapters.cutout.serialize.TransformJSON)(\*\*data)       | Local transform of a scene-graph node (authoring form).                    |
| [`VisualJSON`](#an.adapters.cutout.serialize.VisualJSON)(\*\*data)          | Drawable content attached to a node.                                       |

### *class* an.adapters.cutout.serialize.AnimationClipJSON(\*\*data)

Bases: `_JSONModel`

A named, reusable animation clip.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.AssetJSON(\*\*data)

Bases: `_JSONModel`

A single asset (texture / audio file).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.AssetResolutionJSON(\*\*data)

Bases: `_JSONModel`

How one scene entity’s store reference actually resolved at compile time.

The IR declares every drawable entity as `store` + `ref`. What the
compiler *builds* from that pair is not recoverable from the scene tree
afterwards: a character whose descriptor is missing and a character that
never had one produce byte-identical procedural rigs. That ambiguity is
an#33 — three CI runners once agreed perfectly about a picture that was not
the picture, and the agreement read as a clean positive result.

So the compiler records what it did, per entity, in the artifact the
browser actually loads. `fallback` is the load-bearing bit: True means
the declared ref supplied nothing and a stand-in was drawn in its place.

```pycon
>>> AssetResolutionJSON(
...     id="maya", kind="character", store="characters", ref="maya-v1",
...     resolved="descriptor", fallback=False,
... ).fallback
False
```

#### detail *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

One human sentence saying why, when `fallback` is True.

#### fallback *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

True when the declared ref supplied nothing and a stand-in was drawn.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### resolved *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

“descriptor” | “parts” | “placeholder”.
Environments: “store” | “preset” | “default”.

* **Type:**
  What was built. Characters

### *class* an.adapters.cutout.serialize.AssetsJSON(\*\*data)

Bases: `_JSONModel`

Map of asset id → AssetJSON, split by kind.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.ChannelJSON(\*\*data)

Bases: `_JSONModel`

One animated property of one target.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.CutoutSceneJSON(\*\*data)

Bases: `_JSONModel`

Top-level cutout scene JSON — the JS runtime’s input contract.

Versioned so the runtime can refuse incompatible inputs.

#### asset_resolution *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[AssetResolutionJSON](#an.adapters.cutout.serialize.AssetResolutionJSON)]*

One entry per drawable entity, in scene order — see
[`AssetResolutionJSON`](#an.adapters.cutout.serialize.AssetResolutionJSON). Inert to the runtime; read by the bench
harness and the golden-corpus bless to assert WHICH render path ran.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### overlay *: [NodeJSON](#an.adapters.cutout.serialize.NodeJSON) | [None](https://docs.python.org/3/builtins/constants.html#None)*

a second top-level container the
runtime centres on the canvas and never indexes, so no channel — the
camera’s `root.pivot`/`root.scale` included — can reach it. Its
children are indexed by their own paths exactly like `scene`’s, so an
overlay title’s words tween like anything else. `None` when the shot
has no overlay, and then omitted from the serialized document.

* **Type:**
  The camera-immune layer (an#155)

### *class* an.adapters.cutout.serialize.CutoutSceneMetaJSON(\*\*data)

Bases: `_JSONModel`

Per-shot metadata.

#### blink_phases *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float)]*

Per-entity blink phase in [0, 1), a pure function of the entity NAME
(an#88). Stamped by the compiler — which now emits blinks as channels —
and inert to the runtime. It is recorded because renaming a corpus
character silently re-phases every blink and moves every pixel metric;
a stamped phase turns that into a visible diff instead of an
unexplained metric shift. (The runtime’s determinism probe used to
carry this; the fact moved with the mechanism.)

#### fonts *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

entity id ->
`"<family> <style> [(embedded)] sha256:<digest>"` — identity by the
font’s BYTES, since a family name is not one. Provenance, inert to the
runtime (the glyphs are already SVG). **Serialized only when non-empty.**

* **Type:**
  Per text block, the face that set it (an#155)

#### gaze_seeds *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [int](https://docs.python.org/3/builtins/functions.html#int)]*

Per-entity saccade seed (an#99), a pure function of the entity NAME
like `blink_phases`; stamped for the rigs that have pupils and
**serialized only when non-empty** — a pre-Wave-6 rig has no pupils and
its compiled document, the bench’s scene contract, must not move.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### step_hz *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The stepped-timing policy the shot’s tweens were compiled under
(an#89); `None` = smooth. **Serialized only when set**: the compiled
document is the bench’s scene contract (`scene_contract_sha256`), so a
`null` here would move every committed row’s hash for a knob nobody
turned. Inert to the runtime; read by the ledger.

#### style_pack *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The name of the `StylePack` this scene was compiled under, or `None`.
Recorded so a rendered document says which art direction produced it —
the pack’s COLOURS are already resolved into the nodes, so this is
provenance rather than an instruction. Omitted from the serialized
document when unset (see the wrap serializer below).

### *class* an.adapters.cutout.serialize.KeyframeJSON(\*\*data)

Bases: `_JSONModel`

Single keyframe in an animation channel.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.NodeJSON(\*\*data)

Bases: `_JSONModel`

One node in the scene tree.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.PathJSON(\*\*data)

Bases: `_JSONModel`

A stroked path’s drawing instruction (an#160), carried on a `path` visual.

`points` is always a POLYLINE — the compiler flattens cubic Béziers
(`an.adapters.cutout.path.flatten_curve`), so the runtime knows one geometry.
`trim_start` / `trim_end` are the values shown before any channel
touches the node; channels on those two properties move them.
`head_length == 0` means no arrowhead. What the runtime draws from this
is specified by `an.adapters.cutout.path.path_geometry`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.PlacedClipJSON(\*\*data)

Bases: `_JSONModel`

An animation placed on a track at a specific time.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.TimelineJSON(\*\*data)

Bases: `_JSONModel`

Top-level timeline: total duration + tracks.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.TrackJSON(\*\*data)

Bases: `_JSONModel`

A sequence of placed clips with optional target-prefix metadata.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.TransformJSON(\*\*data)

Bases: `_JSONModel`

Local transform of a scene-graph node (authoring form).

`alpha` is not geometry, but it lives here for the same reason the rest
does: this is the per-node property bag the runtime applies, and it is
animatable through the same channel machinery.

It is set on the node’s *container*, so it **cascades** — fading a character
fades every part of it. Note that this is per-part compositing, not a
flattened group fade: where two parts of the same character overlap, the
seam is visible mid-fade. That is the standard behaviour of a 2D scene graph
and the right default; a true group fade needs the subtree rendered to a
texture first, which costs a render pass per node per frame.

\*\*This class’s field defaults are the single source of truth for a
property’s rest value\*\* — see `compile.py`’s `_PROPERTY_REST_VALUES`,
which is derived from them rather than restated.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.serialize.VisualJSON(\*\*data)

Bases: `_JSONModel`

Drawable content attached to a node.

`kind="svg_sprite"` is the Phase 11b path: the runtime instantiates a
`PIXI.Sprite` from a pre-loaded SVG texture identified by `asset_id`.

`asset_sets` carries this node’s swap vocabulary —
`{set_name: {KEY: asset_id}}`, the compiler’s per-slot **projection** of
the descriptor’s `asset_sets` onto the slot this visual draws (an#87).
A channel whose property names one of these sets swaps the sprite’s
texture by key; `viseme` is just the conventional set name lip-sync
uses. Same field name as `CharacterDescriptor.asset_sets` on purpose:
one vocabulary, two layers (descriptor = declared, wire = resolved to
texture aliases). Replaces the mouth-only `viseme_assets`.

`width`/`height` are the box the art is fitted **into**, not the size it
is forced to. Under `fit="contain"` the art keeps its own aspect ratio and
may leave slack on one axis; that slack is the correct rendering, not a bug.

#### fit *: [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)['stretch', 'contain']*

How the art is fitted to `width`/`height`.

`"contain"` scales uniformly so the art keeps the shape it was drawn
with — the invariant of an#74. `"stretch"` sizes each axis
independently, which is what every sprite did before that issue and what
distorted `arm_l` by 3.929x on the repo’s own art.

Additive with a `"stretch"` default so no stored scene changes meaning;
the compiler emits `"contain"` for every sprite it builds.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### path *: [PathJSON](#an.adapters.cutout.serialize.PathJSON) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The stroke for `kind="path"` (an#160); `None` on every other visual.

### an.adapters.cutout.serialize.from_dict(d)

Rebuild a scene from a plain-dict representation.

* **Return type:**
  [`CutoutSceneJSON`](#an.adapters.cutout.serialize.CutoutSceneJSON)

### an.adapters.cutout.serialize.to_dict(scene)

Dump a scene to a plain-dict representation (no None pruning).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
