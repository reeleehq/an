# an.adapters.cutout.compile

Compile a top-level `Shot` (renderer=”cutout”) into a `CutoutSceneJSON`.

This is the bridge between the renderer-agnostic `an.ir` types and the
cutout-specific JSON contract that the JS runtime will consume in Phase 2B.

Strategy:

1. **Resolve entities** from the project mall: each `AssetRef` in
   `shot.entities` becomes a sub-tree of the cutout scene (a character with
   placeholder rect parts when the character store has no sidecar art yet).
2. **Flatten authoring actions** via `an.ir.compose.flatten` — every
   `tween`/`set`/`play`/composition produces leaf 

   ```
   `
   ```

   FlatAction\`s with
   absolute times.
3. **Compile each FlatAction to PlacedClipJSON entries** on the appropriate
   track. Tween → a 2-keyframe AnimationClipJSON + a PlacedClipJSON (or, under
   `step_hz`, a grid of step-eased keyframes — an#89). Set →
   a step channel that HOLDS until the next action on the same
   target/property. Play → a per-instance clip (`__play__{n}`) resolved
   from the target’s descriptor animation (an#7).

The compiler is deterministic and side-effect-free (it doesn’t write to the
mall). It reads only.

```pycon
>>> from an.ir.schema import Meta, SceneIR, Shot
>>> from an.adapters.cutout.compile import compile_shot
>>> shot = Shot(id="s1", renderer="cutout", duration=2.0)
>>> j = compile_shot(shot, mall={"characters": {}})
>>> j.timeline.duration
2.0
```

### Module Attributes

| [`DFLT_LEG_COLOUR`](#an.adapters.cutout.compile.DFLT_LEG_COLOUR)            | The procedural rig's leg colour — a literal the palette table never carried, which is why it is a named constant rather than two copies of a string.                                                                                                                                                         |
|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_PUPIL_COLOUR`](#an.adapters.cutout.compile.DFLT_PUPIL_COLOUR)          | The procedural rig's pupil colour.                                                                                                                                                                                                                                                                           |
| [`COARTICULATION_ENABLED`](#an.adapters.cutout.compile.COARTICULATION_ENABLED)     | Co-articulation on/off (an#97).                                                                                                                                                                                                                                                                              |
| [`PROCEDURAL_MOUTH_KEYS`](#an.adapters.cutout.compile.PROCEDURAL_MOUTH_KEYS)      | The procedural (drawn) mouth's swap vocabulary, DECLARED as data on its visual exactly as the runtime declares it (`g._anDrawSets = {viseme: ...}`) and as an SVG mouth carries its projection.                                                                                                              |
| [`EYE_NODE_NAMES`](#an.adapters.cutout.compile.EYE_NODE_NAMES)             | the default rig's eye slots ARE its node names, on both the procedural and the descriptor path.                                                                                                                                                                                                              |
| [`PUPIL_NODE_NAMES`](#an.adapters.cutout.compile.PUPIL_NODE_NAMES)           | The pupil nodes of the gaze stack (an#99); a rig without them takes gaze as a no-op.                                                                                                                                                                                                                         |
| [`GAZE_ELLIPSE_MARGIN`](#an.adapters.cutout.compile.GAZE_ELLIPSE_MARGIN)        | The summed gaze (x, y), in axis units, is clamped to a circle of this radius — the declared travel maps the unit circle onto the sclera's inner ellipse, and 0.95 keeps the whole pupil disc inside it at every angle (measured on the synthesized eye: 1.0 pokes out by 2% of the ellipse at the diagonal). |
| [`RUNTIME_APPLIED_PROPERTIES`](#an.adapters.cutout.compile.RUNTIME_APPLIED_PROPERTIES) | Every property name the JS runtime's `applyProperty` STATIC switch implements — exactly the numeric transform vocabulary (the rest-value SSOT above).                                                                                                                                                        |
| [`DFLT_TARGET_SUGGESTIONS`](#an.adapters.cutout.compile.DFLT_TARGET_SUGGESTIONS)    | How many "did you mean" paths an unknown-target message offers.                                                                                                                                                                                                                                              |
| [`CAMERA_NODE`](#an.adapters.cutout.compile.CAMERA_NODE)                | indexed by the runtime, absent from the tree.                                                                                                                                                                                                                                                                |
| [`ENVIRONMENT_ART_PREFIX`](#an.adapters.cutout.compile.ENVIRONMENT_ART_PREFIX)     | The `assets.textures` `src` prefix an environment plate is addressed under.                                                                                                                                                                                                                                  |
| [`PLANE_FILL_SPAN`](#an.adapters.cutout.compile.PLANE_FILL_SPAN)            | A `fill` plane with no declared size covers the canvas at any camera scale.                                                                                                                                                                                                                                  |
| [`FOREGROUND_SUFFIX`](#an.adapters.cutout.compile.FOREGROUND_SUFFIX)          | Suffix for the container holding an environment's FOREGROUND planes.                                                                                                                                                                                                                                         |
| [`SCENE_PX_PER_VIEW_BOX`](#an.adapters.cutout.compile.SCENE_PX_PER_VIEW_BOX)      | Scene-graph pixels spanned by a descriptor's full `view_box` height.                                                                                                                                                                                                                                         |
| [`CONTAIN_FIT`](#an.adapters.cutout.compile.CONTAIN_FIT)                | The fit policy every compiled sprite carries.                                                                                                                                                                                                                                                                |
| [`CHARACTER_ART_PREFIX`](#an.adapters.cutout.compile.CHARACTER_ART_PREFIX)       | The `assets.textures` `src` prefix a rig's art is addressed under, which is also the mall store that resolves it (`render.ASSET_SRC_PREFIX_TO_STORE`).                                                                                                                                                       |
| [`PROP_ART_PREFIX`](#an.adapters.cutout.compile.PROP_ART_PREFIX)            | The same, for props.                                                                                                                                                                                                                                                                                         |

### Functions

| [`blink_phase`](#an.adapters.cutout.compile.blink_phase)(entity_id)                        | The entity's blink phase in [0, 1): the runtime's rule, ported exactly.                                                                        |
|------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| [`camera_keys`](#an.adapters.cutout.compile.camera_keys)(shot, \*, width, height)          | [`an.ir.camera.camera_keys()`](an.ir.camera.md#an.ir.camera.camera_keys), with its refusal typed for this adapter. |
| [`compile_shot`](#an.adapters.cutout.compile.compile_shot)(shot[, mall, fps, width, ...])   | Compile a single cutout-style `Shot` to its JS-runtime JSON form.                                                                              |
| [`foreground_node_name`](#an.adapters.cutout.compile.foreground_node_name)(entity_id)               | The node name an environment's foreground planes live under.                                                                                   |
| [`node_path_suggestions`](#an.adapters.cutout.compile.node_path_suggestions)(target, paths, \*[, n]) | The built node paths a mistyped `target` most plausibly meant.                                                                                 |
| [`parse_tint`](#an.adapters.cutout.compile.parse_tint)(value, \*, where)                  | A `#rrggbb` string to three multipliers in 0..1.                                                                                               |
| [`plane_parents`](#an.adapters.cutout.compile.plane_parents)(env, entity_id)                 | `{plane name: the node path its channels must target}`.                                                                                        |
| [`step_times`](#an.adapters.cutout.compile.step_times)(start, duration, step_hz)          | Clip-local times at which a stepped tween updates its pose (an#89).                                                                            |
| [`style_pack_for`](#an.adapters.cutout.compile.style_pack_for)(scene_meta, styles_store)      | The `StylePack` a scene declares, or `None` (an#112).                                                                                          |
| [`unknown_target_message`](#an.adapters.cutout.compile.unknown_target_message)(target, paths)         | One sentence saying `target` is not a built node, with suggestions.                                                                            |

### Exceptions

| [`CutoutCompileError`](#an.adapters.cutout.compile.CutoutCompileError)   | A shot cannot be compiled to a cutout scene.                    |
|-----------------------------------------------------------------------|-----------------------------------------------------------------|
| [`CutoutCompileWarning`](#an.adapters.cutout.compile.CutoutCompileWarning) | A shot compiles, but something in it will not reach the screen. |

### an.adapters.cutout.compile.CAMERA_NODE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'root'*

indexed by the runtime, absent from the tree.

* **Type:**
  The runtime’s camera node

### an.adapters.cutout.compile.CHARACTER_ART_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'characters/'*

The `assets.textures` `src` prefix a rig’s art is addressed under, which is
also the mall store that resolves it (`render.ASSET_SRC_PREFIX_TO_STORE`).
A parameter rather than a literal because the rig builder is the same code
for a character and for a prop, and the store is the ONLY thing that differs
about where their art lives. Two hardcoded copies of `"characters/"` — the
`src` builder and the probe’s own — reached three call sites, and that is
what made “a prop is a rig too” read as a rewrite instead of an argument
(an#108).

### an.adapters.cutout.compile.COARTICULATION_ENABLED *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Co-articulation on/off (an#97). ON is the product; OFF reproduces the
pre-#97 mouth CHOICE — the raw provider track thinned by the old drop-not-hold
condenser — over the new frame-ceiled clip window (so not byte-for-byte the
old emission: OFF still closes the mouth after a line) and exists so the `lipsync-coarticulation` demo and a test can
render the two side by side. Not a RenderContext knob: nobody should ship
the old behaviour, and a module flag rebound for one render is the shape
the bench’s levers already use.

### an.adapters.cutout.compile.CONTAIN_FIT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'contain'*

The fit policy every compiled sprite carries. Named rather than inlined so
the one place that decides “the art keeps its shape” is greppable.

### *exception* an.adapters.cutout.compile.CutoutCompileError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A shot cannot be compiled to a cutout scene. Carries actionable detail.

A `ValueError` rather than a `RuntimeError` — unlike the rest of this
package’s error tree — because every one of these is “this value is not in
the known set”, which is the existing idiom for argument-level rejection.
The render-time errors stay `RuntimeError`: they are failures of the
machinery, not of the input.

### *exception* an.adapters.cutout.compile.CutoutCompileWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A shot compiles, but something in it will not reach the screen.

The line between this and [`CutoutCompileError`](#an.adapters.cutout.compile.CutoutCompileError) is whether the author
could plausibly have meant it. An unknown `camera.move` is always a
mistake, so it raises. A speaker with no mouth is usually an off-screen
narrator and occasionally a typo — refusing it would break the documented
idiom, and passing in silence is what this whole change is against.

### an.adapters.cutout.compile.DFLT_LEG_COLOUR *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '#2c3e50'*

The procedural rig’s leg colour — a literal the palette table never
carried, which is why it is a named constant rather than two copies of a
string. A `StylePack`’s `leg` role replaces it.

### an.adapters.cutout.compile.DFLT_PUPIL_COLOUR *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '#1a1a1a'*

The procedural rig’s pupil colour. `makeEye` reads it from the document —
the eye WHITE beside it is a literal and cannot be reached, which is the
split `REACHABLE_ROLES` / `UNREACHABLE_ROLES` records.

### an.adapters.cutout.compile.DFLT_TARGET_SUGGESTIONS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 3*

How many “did you mean” paths an unknown-target message offers.

### an.adapters.cutout.compile.ENVIRONMENT_ART_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'environments/'*

The `assets.textures` `src` prefix an environment plate is addressed under.

### an.adapters.cutout.compile.EYE_NODE_NAMES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'left_eye', 'right_eye'})*

the default rig’s eye slots ARE its node
names, on both the procedural and the descriptor path.

* **Type:**
  The nodes that blink, by name

### an.adapters.cutout.compile.FOREGROUND_SUFFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '_\_front'*

Suffix for the container holding an environment’s FOREGROUND planes.

The split has to produce two sibling containers, and before an#110’s review
both were named `entity.id`. The runtime’s `nodeIndex` is a flat
`path -> container` dict, so the second silently overwrote the first — an
authored `set street:x` then moved the foreground half and left the
background where it was, with no warning from either side: the compiler’s
collision check compares `(entity/plane, prop)` and never sees `(entity, x)`,
and the runtime’s unknown-target throw does not fire because the name IS
known, just bound to the wrong one of two. The determinism report’s
`node_count` under-counted by one per split environment too.

### an.adapters.cutout.compile.GAZE_ELLIPSE_MARGIN *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.95*

The summed gaze (x, y), in axis units, is clamped to a circle of this radius
— the declared travel maps the unit circle onto the sclera’s inner ellipse,
and 0.95 keeps the whole pupil disc inside it at every angle (measured on
the synthesized eye: 1.0 pokes out by 2% of the ellipse at the diagonal).

### an.adapters.cutout.compile.PLANE_FILL_SPAN *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 4000.0*

A `fill` plane with no declared size covers the canvas at any camera scale.
The same 4000 the preset backdrop uses, and for the same reason — the runtime
centres `root` and applies camera scale, so a huge rect always covers.

### an.adapters.cutout.compile.PROCEDURAL_MOUTH_KEYS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D', 'E': 'E', 'F': 'F', 'G': 'G', 'H': 'H', 'X': 'X'}*

The procedural (drawn) mouth’s swap vocabulary, DECLARED as data on its
visual exactly as the runtime declares it (`g._anDrawSets = {viseme: ...}`)
and as an SVG mouth carries its projection. A drawn mouth has no textures,
so each key maps to itself — the code the runtime’s shape table draws. The
compiler never branches on the set’s NAME: the drawn mouth is just a node
whose visual carries a `viseme` set (an#87).

### an.adapters.cutout.compile.PROP_ART_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'props/'*

The same, for props. Both are keys of `render.ASSET_SRC_PREFIX_TO_STORE`,
which is what decides where the staging step copies the art from.

### an.adapters.cutout.compile.PUPIL_NODE_NAMES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'left_pupil', 'right_pupil'})*

The pupil nodes of the gaze stack (an#99); a rig without them takes gaze as a no-op.

### an.adapters.cutout.compile.RUNTIME_APPLIED_PROPERTIES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'alpha', 'dash_offset', 'pivot_x', 'pivot_y', 'rotation', 'rotation_rad', 'scale_x', 'scale_y', 'skew_x', 'skew_y', 'tint_b', 'tint_g', 'tint_r', 'trim_end', 'trim_start', 'x', 'y'})*

Every property name the JS runtime’s `applyProperty` STATIC switch
implements — exactly the numeric transform vocabulary (the rest-value SSOT
above). This is the Python side of the two-evaluator drift gate:
`tests/test_loud_discards.py` extracts the runtime’s actual switch cases
and asserts exact equality with this set, in both directions. It replaced
`pose.py`’s allow-list when the Python applier was deleted (an#86).
Any OTHER property is a swap-set name, applied dynamically through the
node’s `asset_sets` projection (an#87) — `viseme` left the static
switch when that landed, which is precisely what makes it a conventional
set name rather than control flow.

### an.adapters.cutout.compile.SCENE_PX_PER_VIEW_BOX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 345.0*

Scene-graph pixels spanned by a descriptor’s full `view_box` height.

The single number that maps descriptor space to scene space. One uniform
factor `k = SCENE_PX_PER_VIEW_BOX / view_box_height` scales bone positions
and part extents alike — uniform by construction, so the compiler cannot
violate the invariant that aspect ratio is intrinsic to the art (an#74).

345 is a calibration, not a preference. It is what reproduces the framing the
seven deleted `_SVG_*_SIZE` constants hand-tuned: at k = 345/1024 = 0.3369,
`saturated-rig`’s own art gives torso 107.8x129.4 against the old 110x130,
legs 37.7x118.6 against 38x120. The constants were an approximation of
exactly this product, which is the evidence that the rig should have been
driving it all along.

### an.adapters.cutout.compile.blink_phase(entity_id)

The entity’s blink phase in [0, 1): the runtime’s rule, ported exactly.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> blink_phase("charlie")
0.762
```

### an.adapters.cutout.compile.camera_keys(shot, , width, height)

[`an.ir.camera.camera_keys()`](an.ir.camera.md#an.ir.camera.camera_keys), with its refusal typed for this adapter.

The resolver itself lives in the IR layer so `an.ir.validate` can call the
SAME function — one table, not two reconciled by a test. This wrapper only
re-raises `CameraError` as a `CutoutCompileError`, which is the compiler’s
own boundary contract: every failure out of `compile_shot` is one type.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`CameraKey`](an.ir.schema.md#an.ir.schema.CameraKey)]

### an.adapters.cutout.compile.compile_shot(shot, mall=None, , fps=30, width=1920, height=1080, background='#ffffff', strict_assets=False, step_hz=None, expression_provider=None, style_pack=None, default_easing=None)

Compile a single cutout-style `Shot` to its JS-runtime JSON form.

`default_easing` (an#166) is the scene’s `meta.default_easing`: the
curve of every authored tween that names none (tween > this > the built-in
`"ease_in_out"`, [`resolved_easing()`](an.ir.schema.md#an.ir.schema.TweenAction.resolved_easing)).
`None` leaves the document byte-identical to before the knob existed.

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
unknown environment ref — from a warning into a [`CutoutCompileError`](#an.adapters.cutout.compile.CutoutCompileError).
Off by default so an asset-less project still renders; on for anything that
measures pixels, where a stand-in is a wrong answer wearing a right one’s
clothes (an#33).

* **Return type:**
  [`CutoutSceneJSON`](an.adapters.cutout.serialize.md#an.adapters.cutout.serialize.CutoutSceneJSON)

### an.adapters.cutout.compile.foreground_node_name(entity_id)

The node name an environment’s foreground planes live under.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> foreground_node_name("street")
'street__front'
```

### an.adapters.cutout.compile.node_path_suggestions(target, paths, , n=3)

The built node paths a mistyped `target` most plausibly meant.

The paths of the SAME entity that end in the same part name — the usual
mistake is a missing level (`ned/left_brow` for `ned/head/left_brow`)
— or, when there are none, the closest spellings.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> built = ["ned", "ned/head", "ned/head/left_brow", "ned/head/mouth", "ned/arm_l"]
>>> node_path_suggestions("ned/left_brow", built)
['ned/head/left_brow']
>>> node_path_suggestions("ned/arm_x", built)
['ned/arm_l']
>>> node_path_suggestions("zzz", built)
[]
```

### an.adapters.cutout.compile.parse_tint(value, , where)

A `#rrggbb` string to three multipliers in 0..1.

Per-channel in **sRGB** — on the 8-bit values as written — not linear-light.
`tint` is a multiply the GPU applies in the space the author read the hex
out of, and a fade between two hex values that did not pass through the
values between them would surprise whoever wrote them (an#62).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.adapters.cutout.compile.plane_parents(env, entity_id)

`{plane name: the node path its channels must target}`.

One rule, computed the same way by the builder and by the parallax pass —
the alternative is two places deciding which container a plane ended up in,
which is the class of drift this wave keeps closing.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from an.environments import EnvironmentDescriptor, Plane
>>> env = EnvironmentDescriptor(name="e", planes=[Plane(name="a"), Plane(name="b")],
...                             characters_after="a")
>>> plane_parents(env, "street")
{'a': 'street', 'b': 'street__front'}
```

### an.adapters.cutout.compile.step_times(start, duration, step_hz)

Clip-local times at which a stepped tween updates its pose (an#89).

The grid is SHOT-wide — multiples of `1/step_hz` on the shot’s clock,
shared by every tween in the shot — not the tween’s own: “on twos” means
every character changes pose on the same frames, so a tween starting at
0.033 s updates at the next grid point, not 0.033 s later. (Shots compile
independently, so the grid restarts at each cut.) Local 0 (the tween’s
start) and `duration` (where the end value lands) are always present, so
a tween shorter than one step is a single step to its end value.

`step_hz` must be positive: with a non-positive rate the walk below never
reaches `duration` — an infinite loop, not an error — so it is refused.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> step_times(0.0, 0.3, 10)
[0.0, 0.1, 0.2, 0.3]
>>> [round(t, 3) for t in step_times(0.05, 0.3, 10)]
[0.0, 0.05, 0.15, 0.25, 0.3]
>>> step_times(0.0, 0.02, 10)
[0.0, 0.02]
```

### an.adapters.cutout.compile.style_pack_for(scene_meta, styles_store)

The `StylePack` a scene declares, or `None` (an#112).

`None` for every document written before an#112 and for every scene that
declares no pack — which is what makes this feature byte-identity-free: the
no-pack path is a lookup with a default, not a rewrite.

A declared pack that is missing, or is not a `StylePack`, RAISES. An art
direction the author asked for and did not get is a different picture that
renders happily, which is the an#33 failure this package refuses everywhere
else.

* **Return type:**
  [`StylePack`](an.styles.md#an.styles.StylePack) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.adapters.cutout.compile.unknown_target_message(target, paths)

One sentence saying `target` is not a built node, with suggestions.

Shared by the compiler (which raises it) and `an validate` (which
reports it), so the two say the same thing about the same path.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> print(unknown_target_message("ned/mouth", ["ned", "ned/head", "ned/head/mouth"]))
'ned/mouth' is not a node of the built scene; did you mean 'ned/head/mouth'? (nodes of 'ned': ['ned', 'ned/head', 'ned/head/mouth'])
```
