# an.stage.compile

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
>>> from an.stage.compile import compile_shot
>>> shot = Shot(id="s1", renderer="cutout", duration=2.0)
>>> j = compile_shot(shot, mall={"characters": {}})
>>> j.timeline.duration
2.0
```

### Module Attributes

| [`RUNTIME_APPLIED_PROPERTIES`](#an.stage.compile.RUNTIME_APPLIED_PROPERTIES)   | Every property name the JS runtime's `applyProperty` STATIC switch implements — exactly the numeric transform vocabulary (the rest-value SSOT above).                                                                     |
|-------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_TARGET_SUGGESTIONS`](#an.stage.compile.DFLT_TARGET_SUGGESTIONS)      | How many "did you mean" paths an unknown-target message offers.                                                                                                                                                           |
| [`CAMERA_NODE`](#an.stage.compile.CAMERA_NODE)                  | indexed by the runtime, absent from the tree.                                                                                                                                                                             |
| [`STAGE_COMPILE_PASSES`](#an.stage.compile.STAGE_COMPILE_PASSES)         | The STAGE's own compile passes, in order.                                                                                                                                                                                 |
| [`RUNTIME_FIELD_KINDS`](#an.stage.compile.RUNTIME_FIELD_KINDS)          | The field kinds `runtime.js` implements (its `FIELD_KINDS` table; a test pins the two).                                                                                                                                   |
| [`STAGE_SCENE_BUILDERS`](#an.stage.compile.STAGE_SCENE_BUILDERS)         | phase 0 the backdrop, phase 1 the cast.                                                                                                                                                                                   |
| [`ENVIRONMENT_ART_PREFIX`](#an.stage.compile.ENVIRONMENT_ART_PREFIX)       | The `assets.textures` `src` prefix an environment plate is addressed under.                                                                                                                                               |
| [`PLANE_FILL_SPAN`](#an.stage.compile.PLANE_FILL_SPAN)              | A `fill` plane with no declared size covers the canvas at any camera scale — defined beside the schema (`an.stage.environments.PLANE_FILL_SPAN`) so the IR layer's framing check reads the same number, re-exported here. |
| [`FOREGROUND_SUFFIX`](#an.stage.compile.FOREGROUND_SUFFIX)            | Suffix for the container holding an environment's FOREGROUND planes.                                                                                                                                                      |
| [`STAGE_NODE_SPACE`](#an.stage.compile.STAGE_NODE_SPACE)             | The property space every compiled node lives in ([`an.timing.spaces`](an.timing.spaces.html.md#module-an.timing.spaces)).                                                                              |
| [`PLANE_EDGE_ON_MARGIN`](#an.stage.compile.PLANE_EDGE_ON_MARGIN)         | at ±π/2 the runtime draws nothing, and a value past it is almost always DEGREES typed where radians were meant (an#314 review).                                                                                           |

### Functions

| [`camera_keys`](#an.stage.compile.camera_keys)(shot, \*, width, height)             | [`an.ir.camera.camera_keys()`](an.ir.camera.html.md#an.ir.camera.camera_keys), with its refusal typed for this adapter.                                                           |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`compile_passes_for_stage`](#an.stage.compile.compile_passes_for_stage)()                       | The stage's passes and every registered one, in run order (stable by name).                                                                                                                              |
| [`compile_shot`](#an.stage.compile.compile_shot)(shot[, mall, fps, width, ...])      | Compile a single cutout-style `Shot` to its JS-runtime JSON form.                                                                                                                                        |
| [`entity_spaces_of`](#an.stage.compile.entity_spaces_of)(shot)                           | `{entity id: space}` for each entity whose kind declares a space other than the kernel default -- what the compiled document records so the default evaluator agrees with validate and compile (an#245). |
| [`foreground_node_name`](#an.stage.compile.foreground_node_name)(entity_id)                  | The node name an environment's foreground planes live under.                                                                                                                                             |
| [`node_path_suggestions`](#an.stage.compile.node_path_suggestions)(target, paths, \*[, n])    | The built node paths a mistyped `target` most plausibly meant.                                                                                                                                           |
| [`note_raster_rig`](#an.stage.compile.note_raster_rig)(entity, desc_data, pack, raster) | Record a rig with raster parts that a colour-setting pack is applied to.                                                                                                                                 |
| [`parse_tint`](#an.stage.compile.parse_tint)(value, \*, where)                     | A `#rrggbb` string to three multipliers in 0..1.                                                                                                                                                         |
| [`plane_parents`](#an.stage.compile.plane_parents)(env, entity_id)                    | `{plane name: the node path its channels must target}`.                                                                                                                                                  |
| [`scene_builders`](#an.stage.compile.scene_builders)()                                 | `{entity kind: builder}`: the stage's, and every registered one.                                                                                                                                         |
| [`space_definitions`](#an.stage.compile.space_definitions)(entity_spaces)                 | `{space name: definition}` for every space `entity_spaces` names -- what the compiled document embeds as `meta.spaces` so `runtime.js` evaluates each declared entity in its space (an#287).             |
| [`stage_replacements`](#an.stage.compile.stage_replacements)()                             | `{stage pass or builder: the genre replacing it}` -- recorded in the compiled document's `meta.extensions` when non-empty.                                                                               |
| [`step_times`](#an.stage.compile.step_times)(start, duration, step_hz)             | Clip-local times at which a stepped tween updates its pose (an#89).                                                                                                                                      |
| [`style_pack_for`](#an.stage.compile.style_pack_for)(scene_meta, styles_store)         | The `StylePack` a scene declares, or `None` (an#112).                                                                                                                                                    |
| [`unknown_target_message`](#an.stage.compile.unknown_target_message)(target, paths)            | One sentence saying `target` is not a built node, with suggestions.                                                                                                                                      |

### Classes

| [`ActionLowering`](#an.stage.compile.ActionLowering)(\*args, \*\*kwargs)           | How a genre's action kind becomes clips in the stage compiler (an#225).   |
|-----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`CompileState`](#an.stage.compile.CompileState)(shot, mall, fps, width, height) | What the stage compiler's passes read and write, for one shot (an#247).   |
| [`SceneBuild`](#an.stage.compile.SceneBuild)(shot, mall, textures, ...[, ...]) | The scene being built, as an entity builder sees it (an#247).             |

### Exceptions

| [`CompilePassCollision`](#an.stage.compile.CompilePassCollision)   | A genre registered a pass (or a builder) the stage already has, without `replace=True`.   |
|-------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| [`CutoutCompileError`](#an.stage.compile.CutoutCompileError)     | A shot cannot be compiled to a cutout scene.                                              |
| [`CutoutCompileWarning`](#an.stage.compile.CutoutCompileWarning)   | A shot compiles, but something in it will not reach the screen.                           |

### *class* an.stage.compile.ActionLowering(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

How a genre’s action kind becomes clips in the stage compiler (an#225).

Registered as [`an.genres.ActionKind.lowering`](an.genres.html.md#an.genres.ActionKind.lowering). The stage knows no
kind by name beyond its own (`tween`, `set`); a genre’s kind supplies:

- `extent_resolver(vocab)`: `action -> seconds` for a leaf that names no
  duration (or `None`);
- `expand(flat_list, *, vocab, fps, step_hz, default_easing, resolutions)`:
  the flat list with this kind’s leaves replaced by what they stand for;
- `view_of(entity_swaps, vocab, *, duration)`: `flat -> view name | None`
  (or `None`), for kinds whose clips depend on the view in force;
- `clip(action, *, anim_id, vocab, fps, view)`: the animation clip of one
  leaf that survived `expand`.

### an.stage.compile.CAMERA_NODE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'root'*

indexed by the runtime, absent from the tree.

* **Type:**
  The runtime’s camera node

### *exception* an.stage.compile.CompilePassCollision

Bases: [`CutoutCompileError`](#an.stage.compile.CutoutCompileError)

A genre registered a pass (or a builder) the stage already has, without `replace=True`.

### *class* an.stage.compile.CompileState(shot, mall, fps, width, height, strict_assets=False, step_hz=None, default_easing=None, style_pack=None, expression_provider=None, textures=<factory>, resolutions=<factory>, overlay_children=<factory>, fonts=<factory>, scene_root=None, vocab=None, animations=<factory>, tracks=<factory>, entity_swaps=<factory>, extra_actions=<factory>, no_lip_sync=frozenset({}), poses=None, view_spans=None, blink_phases=<factory>, gaze_seeds=<factory>, products=<factory>, meta_extensions=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What the stage compiler’s passes read and write, for one shot (an#247).

The stage’s own passes ([`STAGE_COMPILE_PASSES`](#an.stage.compile.STAGE_COMPILE_PASSES)) and every pass a genre
registers for the `"stage"` compiler ([`an.genres.CompilePass`](an.genres.html.md#an.genres.CompilePass)) run
over one of these, in order; `_assemble_document()` turns it into the
wire document. The fields are the locals `compile_shot` used to thread by
hand, unchanged, so the document is byte-identical.

#### extra_actions *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)*

Actions a pass contributes beside the authored ones, compiled with them
by the `actions` pass (the cut-out `speech` pass’s pulses, an#248).

#### no_lip_sync *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= frozenset({})*

Cut-out passes’ products, read by later passes (an empty default is what
a shot with no character produces anyway).

#### products *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]*

what a genre’s pass produces for a later
pass (`products`, by key), and what it adds to the document’s meta
(`meta_extensions` -> `meta.extensions`, omitted when empty). A new
genre needs no new field here.

* **Type:**
  The generic slots (an#247)

### *exception* an.stage.compile.CutoutCompileError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A shot cannot be compiled to a cutout scene. Carries actionable detail.

A `ValueError` rather than a `RuntimeError` — unlike the rest of this
package’s error tree — because every one of these is “this value is not in
the known set”, which is the existing idiom for argument-level rejection.
The render-time errors stay `RuntimeError`: they are failures of the
machinery, not of the input.

### *exception* an.stage.compile.CutoutCompileWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A shot compiles, but something in it will not reach the screen.

The line between this and [`CutoutCompileError`](#an.stage.compile.CutoutCompileError) is whether the author
could plausibly have meant it. An unknown `camera.move` is always a
mistake, so it raises. A speaker with no mouth is usually an off-screen
narrator and occasionally a typo — refusing it would break the documented
idiom, and passing in silence is what this whole change is against.

### an.stage.compile.DFLT_TARGET_SUGGESTIONS *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 3*

How many “did you mean” paths an unknown-target message offers.

### an.stage.compile.ENVIRONMENT_ART_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'environments/'*

The `assets.textures` `src` prefix an environment plate is addressed under.

### an.stage.compile.FOREGROUND_SUFFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '_\_front'*

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

### an.stage.compile.PLANE_EDGE_ON_MARGIN *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.001*

at
±π/2 the runtime draws nothing, and a value past it is almost always
DEGREES typed where radians were meant (an#314 review).

* **Type:**
  How close to edge-on a plane may be authored (radians short of ±π/2)

### an.stage.compile.PLANE_FILL_SPAN *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 4000.0*

A `fill` plane with no declared size covers the canvas at any camera scale
— defined beside the schema (`an.stage.environments.PLANE_FILL_SPAN`) so the IR
layer’s framing check reads the same number, re-exported here.

### an.stage.compile.RUNTIME_APPLIED_PROPERTIES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'alpha', 'dash_offset', 'perspective', 'pivot_x', 'pivot_y', 'plane_fade_end', 'plane_fade_start', 'rotation', 'rotation_rad', 'rotation_x', 'scale_x', 'scale_y', 'skew_x', 'skew_y', 'tint_b', 'tint_g', 'tint_r', 'trim_end', 'trim_start', 'x', 'y'})*

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

### an.stage.compile.RUNTIME_FIELD_KINDS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'angle', 'color', 'discrete', 'number', 'orbit', 'quaternion', 'vector'})*

The field kinds `runtime.js` implements (its `FIELD_KINDS` table; a test
pins the two). A declared space using any other kind cannot be drawn by the
stage, so the compiler refuses it instead of the browser failing mid-render.

### an.stage.compile.STAGE_COMPILE_PASSES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[CompilePass](an.genres.registry.html.md#an.genres.registry.CompilePass), ...]* *= (CompilePass(name='scene', run=<function \_scene_pass>, order=100, compiler='stage', builds=None, description='the scene tree, overlay, grain, vocabulary', replace=False), CompilePass(name='actions', run=<function \_actions_pass>, order=200, compiler='stage', builds=None, description='authored actions -> clips', replace=False), CompilePass(name='camera', run=<function \_camera_pass>, order=600, compiler='stage', builds=None, description='the camera onto the scene root', replace=False), CompilePass(name='parallax', run=<function \_parallax_pass>, order=700, compiler='stage', builds=None, description="planes' parallax", replace=False), CompilePass(name='checks', run=<function \_checks_pass>, order=900, compiler='stage', builds=None, description='targets, easings, stand-ins', replace=False))*

The STAGE’s own compile passes, in order. A genre adds passes between them by
registering [`an.genres.CompilePass`](an.genres.html.md#an.genres.CompilePass) objects for the `"stage"`
compiler; the in-repo cut-out genre registers `swap_pose` (300),
`view_spans` (310), `visemes` (400) and `face` (500), and the `rig`
entity builder (`an.genres.cutout.CUTOUT_COMPILE_PASSES`). Held HERE, not in the genre tables, so
no `without_genres()` can take the stage’s own passes away.

### an.stage.compile.STAGE_NODE_SPACE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'stage.node'*

The property space every compiled node lives in ([`an.timing.spaces`](an.timing.spaces.html.md#module-an.timing.spaces)).

### an.stage.compile.STAGE_SCENE_BUILDERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [CompilePass](an.genres.registry.html.md#an.genres.registry.CompilePass)]* *= {'environment': CompilePass(name='environment', run=<function \_build_environment_entity>, order=0, compiler='stage', builds='environment', description="an environment's planes (the backdrop)", replace=False), 'prop': CompilePass(name='prop', run=<function \_build_prop_entity>, order=1, compiler='stage', builds='prop', description='a prop, a stroked path or a text block', replace=False)}*

phase 0 the backdrop, phase 1 the cast.

* **Type:**
  The stage’s own entity builders

### *class* an.stage.compile.SceneBuild(shot, mall, textures, resolutions, style_pack, overlay, fonts, width, height, children=<factory>, in_front=<factory>, reached=<factory>, skipped=<factory>, raster=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The scene being built, as an entity builder sees it (an#247).

A builder ([`an.genres.CompilePass`](an.genres.html.md#an.genres.CompilePass) with `builds` set) appends its
entity’s subtree to `children` (or `overlay`, or `in_front`) and
records its textures and resolutions here, exactly as the scene pass did
by hand.

### an.stage.compile.camera_keys(shot, , width, height)

[`an.ir.camera.camera_keys()`](an.ir.camera.html.md#an.ir.camera.camera_keys), with its refusal typed for this adapter.

The resolver itself lives in the IR layer so `an.ir.validate` can call the
SAME function — one table, not two reconciled by a test. This wrapper only
re-raises `CameraError` as a `CutoutCompileError`, which is the compiler’s
own boundary contract: every failure out of `compile_shot` is one type.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`CameraKey`](an.ir.schema.html.md#an.ir.schema.CameraKey)]

### an.stage.compile.compile_passes_for_stage()

The stage’s passes and every registered one, in run order (stable by name).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`CompilePass`](an.genres.registry.html.md#an.genres.registry.CompilePass), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.stage.compile.compile_shot(shot, mall=None, , fps=30, width=1920, height=1080, background='#ffffff', strict_assets=False, step_hz=None, expression_provider=None, style_pack=None, default_easing=None)

Compile a single cutout-style `Shot` to its JS-runtime JSON form.

`default_easing` (an#166) is the scene’s `meta.default_easing`: the
curve of every authored tween that names none (tween > this > the built-in
`"ease_in_out"`, [`resolved_easing()`](an.ir.schema.html.md#an.ir.schema.TweenAction.resolved_easing)).
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
unknown environment ref — from a warning into a [`CutoutCompileError`](#an.stage.compile.CutoutCompileError).
Off by default so an asset-less project still renders; on for anything that
measures pixels, where a stand-in is a wrong answer wearing a right one’s
clothes (an#33).

* **Return type:**
  [`CutoutSceneJSON`](an.stage.serialize.html.md#an.stage.serialize.CutoutSceneJSON)

### an.stage.compile.entity_spaces_of(shot)

`{entity id: space}` for each entity whose kind declares a space other
than the kernel default – what the compiled document records so the
default evaluator agrees with validate and compile (an#245).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from an.ir.schema import AssetRef, Shot
>>> entity_spaces_of(Shot(id="s", entities=[AssetRef(kind="prop", id="p", store="props", ref="p")]))
{}
```

### an.stage.compile.foreground_node_name(entity_id)

The node name an environment’s foreground planes live under.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> foreground_node_name("street")
'street__front'
```

### an.stage.compile.node_path_suggestions(target, paths, , n=3)

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

### an.stage.compile.note_raster_rig(entity, desc_data, pack, raster)

Record a rig with raster parts that a colour-setting pack is applied to.

Public (an#338) because a genre that builds a rig calls it before
[`an.stage.rig.build_rig_subtree()`](an.stage.rig.html.md#an.stage.rig.build_rig_subtree), as the prop builder does.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.stage.compile.parse_tint(value, , where)

A `#rrggbb` string to three multipliers in 0..1.

Per-channel in **sRGB** — on the 8-bit values as written — not linear-light.
`tint` is a multiply the GPU applies in the space the author read the hex
out of, and a fade between two hex values that did not pass through the
values between them would surprise whoever wrote them (an#62).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.stage.compile.plane_parents(env, entity_id)

`{plane name: the node path its channels must target}`.

One rule, computed the same way by the builder and by the parallax pass —
the alternative is two places deciding which container a plane ended up in,
which is the class of drift this wave keeps closing.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> from an.stage.environments import EnvironmentDescriptor, Plane
>>> env = EnvironmentDescriptor(name="e", planes=[Plane(name="a"), Plane(name="b")],
...                             characters_after="a")
>>> plane_parents(env, "street")
{'a': 'street', 'b': 'street__front'}
```

### an.stage.compile.scene_builders()

`{entity kind: builder}`: the stage’s, and every registered one.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`CompilePass`](an.genres.registry.html.md#an.genres.registry.CompilePass)]

### an.stage.compile.space_definitions(entity_spaces)

`{space name: definition}` for every space `entity_spaces` names –
what the compiled document embeds as `meta.spaces` so `runtime.js`
evaluates each declared entity in its space (an#287).

The definition is `to_json()` without
its prose (a reworded description must not move a contract hash; a
space’s `version` does). A space using a field kind the runtime does not
implement is refused here ([`CutoutCompileError`](#an.stage.compile.CutoutCompileError)).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

```pycon
>>> space_definitions({})
{}
>>> space_definitions({"cam": "stage.camera"})["stage.camera"]["fields"][0]
{'pattern': 'x', 'spec': {'kind': 'number'}, 'unit': 'px'}
```

### an.stage.compile.stage_replacements()

`{stage pass or builder: the genre replacing it}` – recorded in the
compiled document’s `meta.extensions` when non-empty.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.stage.compile.step_times(start, duration, step_hz)

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

### an.stage.compile.style_pack_for(scene_meta, styles_store)

The `StylePack` a scene declares, or `None` (an#112).

`None` for every document written before an#112 and for every scene that
declares no pack — which is what makes this feature byte-identity-free: the
no-pack path is a lookup with a default, not a rewrite.

A declared pack that is missing, or is not a `StylePack`, RAISES. An art
direction the author asked for and did not get is a different picture that
renders happily, which is the an#33 failure this package refuses everywhere
else.

* **Return type:**
  [`StylePack`](an.styles.html.md#an.styles.StylePack) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.stage.compile.unknown_target_message(target, paths)

One sentence saying `target` is not a built node, with suggestions.

Shared by the compiler (which raises it) and `an validate` (which
reports it), so the two say the same thing about the same path.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> print(unknown_target_message("ned/mouth", ["ned", "ned/head", "ned/head/mouth"]))
'ned/mouth' is not a node of the built scene; did you mean 'ned/head/mouth'? (nodes of 'ned': ['ned', 'ned/head', 'ned/head/mouth'])
```
