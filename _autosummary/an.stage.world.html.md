# an.stage.world

The stage’s side of the scene world (ADR 0009): measuring a member’s
extent, and lowering a whole scene for the compiler.

The IR layer ([`an.ir.world`](an.ir.world.html.md#module-an.ir.world)) projects points and sizes; what it cannot
know is how big an entity’s art is. This module measures that the way the
runtime would draw it, without a browser: it compiles the entity’s specimen
shot alone and takes the union of its nodes’ boxes
([`an.stage.timeline.node_box()`](an.stage.timeline.html.md#an.stage.timeline.node_box), an#445), relative to the entity’s own
placement point. Any registered entity kind with a specimen is measured
the same way, so a genre’s rig and the core’s props get one rule.

[`lower_scene()`](#an.stage.world.lower_scene) is the one call the pipeline’s entry points make
(`an render`, `an preview`, `an probe`, `an validate`, the orchestrator):
extents, film starts, then [`an.ir.world.lower_world()`](an.ir.world.html.md#an.ir.world.lower_world).

### Functions

| [`lower_scene`](#an.stage.world.lower_scene)(scene, mall, \*[, fps, ...])           | `scene` as the compiler should see it: every framed shot's placements derived from the world ([`an.ir.world.lower_world()`](an.ir.world.html.md#an.ir.world.lower_world)), with the members' extents measured here and each shot's film start from the assembled timeline (so a travel's streams keep phase across cuts).                                           |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`seed_world`](#an.stage.world.seed_world)(scene, mall, shot_id, \*[, focal, ...]) | `scene` with a world derived from its hand-placed shot `shot_id` ([`an.ir.world_from_shot.seed_members()`](an.ir.world_from_shot.html.md#an.ir.world_from_shot.seed_members), an#514): the members, and one viewpoint named after the shot, a camera at the origin with `focal` (pixels; default: the default field of view, so the world frames the same at any resolution). |
| [`lowered_or_same`](#an.stage.world.lowered_or_same)(scene, mall, \*[, fps])            | The lowered scene, or `scene` itself when it has no world or its world cannot be lowered: for the walks that must see what a framed shot draws (credits, publishability) but are not where a world error is reported (validate is).                                                                                                                                                         |
| [`member_extents`](#an.stage.world.member_extents)(world, mall, \*, width, height)     | `{id: native box}` for every positioned or attached member and every stream of `world` (environments draw plates, not a box, and are left out).                                                                                                                                                                                                                                             |
| [`native_box`](#an.stage.world.native_box)(ref, mall, \*, width, height)           | The box `ref`'s art occupies at `stage.scale` 1, `(x0, y0, x1, y1)` in scene pixels relative to its placement point; `None` when it draws nothing that can be measured (an unknown ref drawn as a placeholder is still measured: that is what the shot would show).                                                                                                                         |
| [`world_report`](#an.stage.world.world_report)(lowered)                              | What `an world show` prints: per framed shot, its entities as the compiler sees them (id, kind, at, scale, after) and the lowering's notes.                                                                                                                                                                                                                                                 |

### an.stage.world.lower_scene(scene, mall, , fps=None, film_starts=None, project_dir=None, continues=True)

`scene` as the compiler should see it: every framed shot’s placements
derived from the world ([`an.ir.world.lower_world()`](an.ir.world.html.md#an.ir.world.lower_world)), with the
members’ extents measured here and each shot’s film start from the
assembled timeline (so a travel’s streams keep phase across cuts). A scene
without a world comes back as it is, at no cost. Then every shot’s
`continue:` is resolved ([`an.continuity.continue_shots()`](an.continuity.html.md#an.continuity.continue_shots), an#542):
a shot that continues another opens as that one ends (`project_dir`:
where a sibling scene file is read; default the mall’s; `continues`:
off for the world alone, as `an validate` reports the two apart).

Raises [`an.ir.world.WorldError`](an.ir.world.html.md#an.ir.world.WorldError) for a viewpoint that cannot be
resolved; `an validate` reports the same error instead of raising.

```pycon
>>> lower_scene(SceneIR(), {}).scene.timeline
[]
```

* **Return type:**
  [`Lowered`](an.ir.world.html.md#an.ir.world.Lowered)

### an.stage.world.lowered_or_same(scene, mall, , fps=None)

The lowered scene, or `scene` itself when it has no world or its
world cannot be lowered: for the walks that must see what a framed shot
draws (credits, publishability) but are not where a world error is
reported (validate is).

* **Return type:**
  [`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR)

### an.stage.world.member_extents(world, mall, , width, height, problems=None)

`{id: native box}` for every positioned or attached member and every
stream of `world` (environments draw plates, not a box, and are left
out). A member whose art cannot be measured maps to `None` — a missing
ref, an unregistered kind, a compile that refuses — and `problems` (an
out-parameter, like the compiler’s `textures`) records why, so the
lowering can say it instead of a traceback (ADR 0009: validate reports).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### an.stage.world.native_box(ref, mall, , width, height)

The box `ref`’s art occupies at `stage.scale` 1, `(x0, y0, x1, y1)`
in scene pixels relative to its placement point; `None` when it draws
nothing that can be measured (an unknown ref drawn as a placeholder is
still measured: that is what the shot would show).

```pycon
>>> from an.ir.schema import AssetRef
>>> native_box(AssetRef(kind="voice", id="v", store="voices", ref="v"), {}, width=320, height=240) is None
True
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.stage.world.seed_world(scene, mall, shot_id, , focal=None, depth=None)

`scene` with a world derived from its hand-placed shot `shot_id`
([`an.ir.world_from_shot.seed_members()`](an.ir.world_from_shot.html.md#an.ir.world_from_shot.seed_members), an#514): the members, and one
viewpoint named after the shot, a camera at the origin with `focal`
(pixels; default: the default field of view, so the world frames the same
at any resolution). The shot names that viewpoint and keeps its own
`stage` lines, which agree with the world. The art is measured here,
as the lowering measures it ([`native_box()`](#an.stage.world.native_box); a measurement that fails
leaves the entity out, said in `skipped`).

Raises `ValueError` for a scene that already has a world, an unknown
shot or one that already names a viewpoint, and what
[`seed_members()`](an.ir.world_from_shot.html.md#an.ir.world_from_shot.seed_members) refuses.

```pycon
>>> seed_world(SceneIR(), {}, "a")
Traceback (most recent call last):
...
ValueError: no shot 'a' in the scene (its shots: [])
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR), [`SeededMembers`](an.ir.world_from_shot.html.md#an.ir.world_from_shot.SeededMembers)]

### an.stage.world.world_report(lowered)

What `an world show` prints: per framed shot, its entities as the
compiler sees them (id, kind, at, scale, after) and the lowering’s notes.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]
