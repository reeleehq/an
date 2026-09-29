# an.adapters.cutout

Cutout-style 2D animation backend.

The render path is `compile.py` → `serialize.py` → `render.py` →
`runtime.js` (the browser evaluates and applies every frame). The Python
evaluation chain (`easing`/`channel`/`clip`/`timeline`) is kept as the
executable spec of the runtime’s semantics, pinned by node-backed parity tests;
application lives in `runtime.js` alone (an#86).

```pycon
>>> from an.adapters.cutout import CutoutRenderer, compile_shot
>>> CutoutRenderer().name
'cutout'
```

### Functions

| [`compile_shot`](#an.adapters.cutout.compile_shot)(shot[, mall, fps, width, ...])   | Compile a single cutout-style `Shot` to its JS-runtime JSON form.   |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|

### Classes

| [`CutoutRenderer`](#an.adapters.cutout.CutoutRenderer)()              | Headless cutout renderer: Playwright + ffmpeg.                            |
|--------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`CutoutSceneJSON`](#an.adapters.cutout.CutoutSceneJSON)(\*\*data)     | Top-level cutout scene JSON — the JS runtime's input contract.            |
| [`NodeJSON`](#an.adapters.cutout.NodeJSON)(\*\*data)            | One node in the scene tree.                                               |
| [`VisualJSON`](#an.adapters.cutout.VisualJSON)(\*\*data)          | Drawable content attached to a node.                                      |
| [`AnimationClipJSON`](#an.adapters.cutout.AnimationClipJSON)(\*\*data)   | A named, reusable animation clip.                                         |
| [`ChannelJSON`](#an.adapters.cutout.ChannelJSON)(\*\*data)         | One animated property of one target.                                      |
| [`KeyframeJSON`](#an.adapters.cutout.KeyframeJSON)(\*\*data)        | Single keyframe in an animation channel.                                  |
| [`TimelineJSON`](#an.adapters.cutout.TimelineJSON)(\*\*data)        | Top-level timeline: total duration + tracks.                              |
| [`TrackJSON`](#an.adapters.cutout.TrackJSON)(\*\*data)           | A sequence of placed clips with optional target-prefix metadata.          |
| [`PlacedClipJSON`](#an.adapters.cutout.PlacedClipJSON)(\*\*data)      | An animation placed on a track at a specific time.                        |
| [`AssetsJSON`](#an.adapters.cutout.AssetsJSON)(\*\*data)          | Map of asset id → AssetJSON, split by kind.                               |
| [`AssetJSON`](#an.adapters.cutout.AssetJSON)(\*\*data)           | A single asset (texture / audio file).                                    |
| [`AssetResolutionJSON`](#an.adapters.cutout.AssetResolutionJSON)(\*\*data) | How one scene entity's store reference actually resolved at compile time. |

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

### *class* an.adapters.cutout.CutoutRenderer

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Headless cutout renderer: Playwright + ffmpeg.

```pycon
>>> r = CutoutRenderer()
>>> r.name
'cutout'
>>> r.supported_renderers
('cutout',)
```

#### render(shot, ctx)

Render `shot` to mp4 using `ctx` for paths + parameters.

* **Return type:**
  [`RenderResult`](an.adapters.html.md#an.adapters.RenderResult)

### *class* an.adapters.cutout.CutoutSceneJSON(\*\*data)

Bases: `_JSONModel`

Top-level cutout scene JSON — the JS runtime’s input contract.

Versioned so the runtime can refuse incompatible inputs.

#### asset_resolution *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[AssetResolutionJSON](an.adapters.cutout.serialize.html.md#an.adapters.cutout.serialize.AssetResolutionJSON)]*

One entry per drawable entity, in scene order — see
[`AssetResolutionJSON`](#an.adapters.cutout.AssetResolutionJSON). Inert to the runtime; read by the bench
harness and the golden-corpus bless to assert WHICH render path ran.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

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

#### path *: [PathJSON](an.adapters.cutout.serialize.html.md#an.adapters.cutout.serialize.PathJSON) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The stroke for `kind="path"` (an#160); `None` on every other visual.

### an.adapters.cutout.compile_shot(shot, mall=None, , fps=30, width=1920, height=1080, background='#ffffff', strict_assets=False, step_hz=None, expression_provider=None, style_pack=None)

Compile a single cutout-style `Shot` to its JS-runtime JSON form.

`expression_provider` (an#98) is the seam that turns authored
`expression` leaves and dialogue `[emotion]` sugar into per-axis
curves for the face solver; `None` is `DefaultExpressionProvider`.

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
  [`CutoutSceneJSON`](an.adapters.cutout.serialize.html.md#an.adapters.cutout.serialize.CutoutSceneJSON)

### Modules

| [`channel`](an.adapters.cutout.channel.html.md#module-an.adapters.cutout.channel)             | Channel: keyframes for a single (target, property) pair, evaluated at time t.                                                                   |
|--------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| [`clip`](an.adapters.cutout.clip.html.md#module-an.adapters.cutout.clip)                   | Clip: a named bundle of channels with a duration and loop mode.                                                                                 |
| [`coarticulate`](an.adapters.cutout.coarticulate.html.md#module-an.adapters.cutout.coarticulate)   | Co-articulation for a swap mouth: the passes between a provider's raw viseme track and the compiler's channel emission (an#97, epic #9 Wave 6). |
| [`compile`](an.adapters.cutout.compile.html.md#module-an.adapters.cutout.compile)             | Compile a top-level `Shot` (renderer="cutout") into a `CutoutSceneJSON`.                                                                        |
| [`easing`](an.adapters.cutout.easing.html.md#module-an.adapters.cutout.easing)               | Easing functions for keyframe interpolation.                                                                                                    |
| [`fidelity`](an.adapters.cutout.fidelity.html.md#module-an.adapters.cutout.fidelity)           | How faithfully a compiled scene reproduces the art it was built from.                                                                           |
| [`gaze`](an.adapters.cutout.gaze.html.md#module-an.adapters.cutout.gaze)                   | Ambient saccades for a cutout rig's pupils: a seeded generator (an#99, epic #9 Wave 6).                                                         |
| [`path`](an.adapters.cutout.path.html.md#module-an.adapters.cutout.path)                   | Stroked-path geometry — the executable spec of `runtime.js::pathGeometry`.                                                                      |
| [`render`](an.adapters.cutout.render.html.md#module-an.adapters.cutout.render)               | Headless cutout rendering: Playwright drives the JS runtime, ffmpeg muxes.                                                                      |
| [`runtime_files`](an.adapters.cutout.runtime_files.html.md#module-an.adapters.cutout.runtime_files) | Locate the bundled cutout JS runtime files.                                                                                                     |
| [`serialize`](an.adapters.cutout.serialize.html.md#module-an.adapters.cutout.serialize)         | JSON contract between the Python compiler and the (future) JS runtime.                                                                          |
| [`shutter`](an.adapters.cutout.shutter.html.md#module-an.adapters.cutout.shutter)             | The temporal half of the frame stage: average several instants into one frame.                                                                  |
| [`supersample`](an.adapters.cutout.supersample.html.md#module-an.adapters.cutout.supersample)     | Render bigger, then resolve back exactly — the supersample knob's two halves.                                                                   |
| [`timeline`](an.adapters.cutout.timeline.html.md#module-an.adapters.cutout.timeline)           | Timeline: tracks of placed clips with absolute times and blend ramps.                                                                           |
