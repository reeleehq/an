# an.adapters.cutout

The cut-out backend’s old package: the stage moved to [`an.stage`](an.stage.md#module-an.stage) (an#247).

The render path is `an.stage.compile` -> `an.stage.serialize` ->
`an.stage.render` (the stage engine, driven by the core frame stage) ->
`runtime.js`. Every module that moved keeps a LIVE alias here
(`an.adapters.cutout.render` is `an.stage.render` for reading and for
rebinding, `an._shims.alias_module()`). `coarticulate` and `gaze` moved to `cutan` (an#225; live aliases with a
warning). What stays here is the
timing re-exports (`channel`, `clip`, `timeline`).

The names this package used to export are resolved LAZILY, on first access:
importing `an.adapters.cutout.coarticulate` from the stage’s compiler must not
load the stage back through this `__init__`.

```pycon
>>> from an.adapters.cutout import CutoutRenderer, compile_shot
>>> CutoutRenderer().name
'cutout'
```

### Functions

| [`compile_shot`](#an.adapters.cutout.compile_shot)(shot[, mall, fps, width, ...])   | Compile a single cutout-style `Shot` to its JS-runtime JSON form.   |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|

### Classes

| [`CutoutRenderer`](#an.adapters.cutout.CutoutRenderer)([engine, name, ...])   | The stage renderer: the stage engine through the core frame stage.        |
|----------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`CutoutSceneJSON`](#an.adapters.cutout.CutoutSceneJSON)(\*\*data)             | Top-level cutout scene JSON — the JS runtime's input contract.            |
| [`NodeJSON`](#an.adapters.cutout.NodeJSON)(\*\*data)                    | One node in the scene tree.                                               |
| [`VisualJSON`](#an.adapters.cutout.VisualJSON)(\*\*data)                  | Drawable content attached to a node.                                      |
| [`AnimationClipJSON`](#an.adapters.cutout.AnimationClipJSON)(\*\*data)           | A named, reusable animation clip.                                         |
| [`ChannelJSON`](#an.adapters.cutout.ChannelJSON)(\*\*data)                 | One animated property of one target.                                      |
| [`KeyframeJSON`](#an.adapters.cutout.KeyframeJSON)(\*\*data)                | Single keyframe in an animation channel.                                  |
| [`TimelineJSON`](#an.adapters.cutout.TimelineJSON)(\*\*data)                | Top-level timeline: total duration + tracks.                              |
| [`TrackJSON`](#an.adapters.cutout.TrackJSON)(\*\*data)                   | A sequence of placed clips with optional target-prefix metadata.          |
| [`PlacedClipJSON`](#an.adapters.cutout.PlacedClipJSON)(\*\*data)              | An animation placed on a track at a specific time.                        |
| [`AssetsJSON`](#an.adapters.cutout.AssetsJSON)(\*\*data)                  | Map of asset id → AssetJSON, split by kind.                               |
| [`AssetJSON`](#an.adapters.cutout.AssetJSON)(\*\*data)                   | A single asset (texture / audio file).                                    |
| [`AssetResolutionJSON`](#an.adapters.cutout.AssetResolutionJSON)(\*\*data)         | How one scene entity's store reference actually resolved at compile time. |

### Exceptions

| [`CutoutRenderError`](#an.adapters.cutout.CutoutRenderError)   | Raised when a cutout render fails.   |
|----------------------------------------------------------------------|--------------------------------------|

### *class* an.adapters.cutout.AnimationClipJSON(\*\*data)

Bases: `_JSONModel`

A named, reusable animation clip.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.AssetJSON(\*\*data)

Bases: `_JSONModel`

A single asset (texture / audio file).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.AssetResolutionJSON(\*\*data)

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

### *class* an.adapters.cutout.AssetsJSON(\*\*data)

Bases: `_JSONModel`

Map of asset id → AssetJSON, split by kind.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.ChannelJSON(\*\*data)

Bases: `_JSONModel`

One animated property of one target.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *exception* an.adapters.cutout.CutoutRenderError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when a cutout render fails. Carries actionable detail.

### *class* an.adapters.cutout.CutoutRenderer(engine=<factory>, name='cutout', supported_renderers=('cutout', 'stage'), error=<class 'an.stage.render.CutoutRenderError'>, capture_options=<factory>)

Bases: [`FrameStageRenderer`](an.engines.frame_stage.md#an.engines.frame_stage.FrameStageRenderer)

The stage renderer: the stage engine through the core frame stage.

It claims both renderer names (ADR 0001 decision 9): `stage`, the
engine’s own, and `cutout`, the persisted name every existing scene
carries. Its registry name stays `cutout` – persisted too (the shot
cache keys on it) – and `StageRenderer` is the same class.

```pycon
>>> r = CutoutRenderer()
>>> r.name
'cutout'
>>> r.supported_renderers
('cutout', 'stage')
```

#### error

alias of [`CutoutRenderError`](an.stage.render.md#an.stage.render.CutoutRenderError)

#### supported_renderers *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('cutout', 'stage')*

The `Shot.renderer` values this renderer claims (the ONE place it names them).

### *class* an.adapters.cutout.CutoutSceneJSON(\*\*data)

Bases: `_JSONModel`

Top-level cutout scene JSON — the JS runtime’s input contract.

Versioned so the runtime can refuse incompatible inputs.

#### asset_resolution *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[AssetResolutionJSON](an.stage.serialize.md#an.stage.serialize.AssetResolutionJSON)]*

One entry per drawable entity, in scene order — see
[`AssetResolutionJSON`](#an.adapters.cutout.AssetResolutionJSON). Inert to the runtime; read by the bench
harness and the golden-corpus bless to assert WHICH render path ran.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### overlay *: [NodeJSON](an.stage.serialize.md#an.stage.serialize.NodeJSON) | [None](https://docs.python.org/3/builtins/constants.html#None)*

a second top-level container the
runtime centres on the canvas and never indexes, so no channel — the
camera’s `root.pivot`/`root.scale` included — can reach it. Its
children are indexed by their own paths exactly like `scene`’s, so an
overlay title’s words tween like anything else. `None` when the shot
has no overlay, and then omitted from the serialized document.

* **Type:**
  The camera-immune layer (an#155)

### *class* an.adapters.cutout.KeyframeJSON(\*\*data)

Bases: `_JSONModel`

Single keyframe in an animation channel.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.NodeJSON(\*\*data)

Bases: `_JSONModel`

One node in the scene tree.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### scope *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

as the children of the
node named `scope` in the same parent (`""`: as the parent’s own
children). `None` = under this node’s own path, the rule before
an#343. An environment’s foreground container carries `scope=<env>`,
so every plane is `<env>/<plane>` wherever the environment is cut.
[`an.stage.tree`](an.stage.tree.md#module-an.stage.tree) is the Python statement of the rule.

* **Type:**
  Where this node’s CHILDREN are indexed (an#343)

### *class* an.adapters.cutout.PlacedClipJSON(\*\*data)

Bases: `_JSONModel`

An animation placed on a track at a specific time.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.TimelineJSON(\*\*data)

Bases: `_JSONModel`

Top-level timeline: total duration + tracks.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.TrackJSON(\*\*data)

Bases: `_JSONModel`

A sequence of placed clips with optional target-prefix metadata.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.adapters.cutout.VisualJSON(\*\*data)

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

#### asset_geometry *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float)]] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Per-texture geometry for a swap key drawn differently from the built
one (an#211): `{asset_id: {"width", "height", "anchor_x", "anchor_y",
"x", "y"}}` — the box the key is fitted into, its anchor, and its
offset from the node (scene pixels). A swap used to carry the texture
only, so every key drew in the DEFAULT attachment’s box: a closed mouth
on a thin canvas squashed every open mouth to a fraction of a pixel. Only
keys whose geometry differs are listed; `None` = every key shares it.

#### blend *: [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)['add', 'multiply'] | [None](https://docs.python.org/3/builtins/constants.html#None)*

`"add"` for a
glow, `"multiply"` for the paper grain. PixiJS 7 does both in the
blend equation — no filter, no render texture. `None` = normal.

* **Type:**
  The engine’s native blend mode for this visual (an#163)

#### fit *: [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)['stretch', 'contain']*

How the art is fitted to `width`/`height`.

`"contain"` scales uniformly so the art keeps the shape it was drawn
with — the invariant of an#74. `"stretch"` sizes each axis
independently, which is what every sprite did before that issue and what
distorted `arm_l` by 3.929x on the repo’s own art.

Additive with a `"stretch"` default so no stored scene changes meaning;
the compiler emits `"contain"` for every sprite it builds.

#### kind *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

One of `BUILTIN_VISUAL_KINDS`, or a kind a genre’s runtime script
registers (`window.anRegisterVisual`, an#247). A string on the wire, as
it always was; the open set is what lets `cutan` ship the mouth and eye.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### path *: [PathJSON](an.stage.serialize.md#an.stage.serialize.PathJSON) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The stroke for `kind="path"` (an#160); `None` on every other visual.

#### underlays *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[UnderlayJSON](an.stage.serialize.md#an.stage.serialize.UnderlayJSON)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Copies drawn behind this visual, back to front (an#163) — the outline
and the paper-gap shadow. Only `rect`, `ellipse` and `svg_sprite`
take them; the runtime refuses any other kind.

### an.adapters.cutout.compile_shot(shot, mall=None, , fps=30, width=1920, height=1080, background='#ffffff', strict_assets=False, step_hz=None, expression_provider=None, style_pack=None, default_easing=None)

Compile a single cutout-style `Shot` to its JS-runtime JSON form.

`default_easing` (an#166) is the scene’s `meta.default_easing`: the
curve of every authored tween that names none (tween > this > the built-in
`"ease_in_out"`, [`resolved_easing()`](an.ir.schema.md#an.ir.schema.TweenAction.resolved_easing)).
`None` leaves the document byte-identical to before the knob existed.

`expression_provider` (an#98) is the seam that turns authored
`expression` leaves and dialogue `[emotion]` sugar into per-axis
curves for the face solver; `None` is the genre’s default provider.

`step_hz` (an#89) resamples every authored **tween** onto a SHOT-wide
pose grid of that many updates per second (multiples of `1/step_hz` on
this shot’s clock, shared by every tween in the shot; the grid restarts at
a cut), each keyframe step-eased, so the character holds each pose for the
frames between grid points — “on twos” at half the frame rate, “on threes”
at a third. It is sample-and-hold of the eased curve at the grid instants,
not a retiming into holds and fast transitions. `None` (default) leaves
tweens smooth and the compiled document byte-identical to before the knob
existed; anything else must satisfy `0 < step_hz <= fps` — checked HERE
as well as by `an validate`, because a render never runs validate and a
non-positive rate used to spin `step_times` forever (an#89 review).
Exempt by construction, because they are separate
emission sites rather than string-sniffed: the camera (`_add_camera_clips`
— a stepped character under a translating camera slides in screen space,
which is why the practice keeps cameras on ones), compiled blinks, `play`
clips, and swap channels (already stepped by format). The value is
stamped into `meta.step_hz` — only when set — so a serialized scene
declares its timing policy without moving the contract hash of one that
has none.

`strict_assets` turns a stand-in asset — the placeholder rig drawn for a
character whose descriptor is missing, or the default backdrop drawn for an
unknown environment ref — from a warning into a `CutoutCompileError`.
Off by default so an asset-less project still renders; on for anything that
measures pixels, where a stand-in is a wrong answer wearing a right one’s
clothes (an#33).

* **Return type:**
  [`CutoutSceneJSON`](an.stage.serialize.md#an.stage.serialize.CutoutSceneJSON)

### Modules

| [`cache_key`](an.adapters.cutout.cache_key.md#module-an.adapters.cutout.cache_key)           | Moved to [`an.stage.cache_key`](an.stage.cache_key.md#module-an.stage.cache_key) (an#247); this path is a LIVE alias of it.           |
|----------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`canvas_capture`](an.adapters.cutout.canvas_capture.md#module-an.adapters.cutout.canvas_capture) | Moved to [`an.stage.canvas_capture`](an.stage.canvas_capture.md#module-an.stage.canvas_capture) (an#247); this path is a LIVE alias of it. |
| [`channel`](an.adapters.cutout.channel.md#module-an.adapters.cutout.channel)               | Channel evaluation — moved to [`an.timing.channel`](an.timing.channel.md#module-an.timing.channel) (the timing kernel).              |
| [`clip`](an.adapters.cutout.clip.md#module-an.adapters.cutout.clip)                     | Clips, loop modes and poses — moved to [`an.timing.clip`](an.timing.clip.md#module-an.timing.clip) (the timing kernel).           |
| [`compile`](an.adapters.cutout.compile.md#module-an.adapters.cutout.compile)               | Moved to [`an.stage.compile`](an.stage.compile.md#module-an.stage.compile) (an#247); this path is a LIVE alias of it.               |
| [`easing`](an.adapters.cutout.easing.md#module-an.adapters.cutout.easing)                 | Moved to [`an.stage.easing`](an.stage.easing.md#module-an.stage.easing) (an#247); this path is a LIVE alias of it.                 |
| [`fidelity`](an.adapters.cutout.fidelity.md#module-an.adapters.cutout.fidelity)             | Moved to [`an.stage.fidelity`](an.stage.fidelity.md#module-an.stage.fidelity) (an#247); this path is a LIVE alias of it.             |
| [`path`](an.adapters.cutout.path.md#module-an.adapters.cutout.path)                     | Moved to [`an.stage.path_geometry`](an.stage.path_geometry.md#module-an.stage.path_geometry) (an#247); this path is a LIVE alias of it.   |
| [`render`](an.adapters.cutout.render.md#module-an.adapters.cutout.render)                 | Moved to [`an.stage.render`](an.stage.render.md#module-an.stage.render) (an#247); this path is a LIVE alias of it.                 |
| [`runtime_files`](an.adapters.cutout.runtime_files.md#module-an.adapters.cutout.runtime_files)   | Moved to [`an.stage.runtime_files`](an.stage.runtime_files.md#module-an.stage.runtime_files) (an#247); this path is a LIVE alias of it.   |
| [`serialize`](an.adapters.cutout.serialize.md#module-an.adapters.cutout.serialize)           | Moved to [`an.stage.serialize`](an.stage.serialize.md#module-an.stage.serialize) (an#247); this path is a LIVE alias of it.           |
| [`shutter`](an.adapters.cutout.shutter.md#module-an.adapters.cutout.shutter)               | Moved to [`an.media.shutter`](an.media.shutter.md#module-an.media.shutter) (an#247); this path is a LIVE alias of it.               |
| [`supersample`](an.adapters.cutout.supersample.md#module-an.adapters.cutout.supersample)       | Moved to [`an.media.supersample`](an.media.supersample.md#module-an.media.supersample) (an#247); this path is a LIVE alias of it.       |
| [`surface`](an.adapters.cutout.surface.md#module-an.adapters.cutout.surface)               | Moved to [`an.stage.surface`](an.stage.surface.md#module-an.stage.surface) (an#247); this path is a LIVE alias of it.               |
| [`text`](an.adapters.cutout.text.md#module-an.adapters.cutout.text)                     | Moved to [`an.stage.text_layout`](an.stage.text_layout.md#module-an.stage.text_layout) (an#247); this path is a LIVE alias of it.       |
| [`timeline`](an.adapters.cutout.timeline.md#module-an.adapters.cutout.timeline)             | Moved to [`an.stage.timeline`](an.stage.timeline.md#module-an.stage.timeline) (an#247); this path is a LIVE alias of it.             |
