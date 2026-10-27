# an.ir.world

One world, many shots: the scene world’s geometry and its lowering (ADR 0009).

A scene may declare a **world** (`SceneIR.world`): members at world positions
with a size, named viewpoints, and a travel. A shot with a **viewpoint** is a
pinhole camera onto that world; this module turns the two into what the stage
already understands — a `stage` placement per entity, and plain `set`/`tween`
actions for the streams of a travelling view — so the compiler, the shot cache
and the renderers see nothing new. A shot without a viewpoint is untouched,
and a hand `stage.at` always wins.

The projection, with the stage’s axes extended by depth (`x` right, `y` DOWN,
`z` away from the viewer): a point `p` seen from a camera at `c` with basis
`(forward, right, down)` and focal length `f` (pixels) lands at

> depth = (p − c) · forward
> sx    = f · ((p − c) · right) / depth
> sy    = f · ((p − c) · down)  / depth

and an entity of world size `S` whose art is `n` pixels tall at `stage.scale`
1 is drawn at `stage.scale = (S / n) · f / depth`. That is the multiplane
camera: near things are large and rush past, far things are small and barely
move, and a close-up is the same world seen from nearer.

```pycon
>>> from an.ir.schema import World, WorldMember, Viewpoint
>>> world = World(members=[
...     WorldMember(kind="prop", id="near", store="props", ref="p", at=(1.0, 0.0, 2.0), height=1.0),
...     WorldMember(kind="prop", id="far", store="props", ref="p", at=(1.0, 0.0, 20.0), height=1.0),
... ])
>>> box = (-10.0, -20.0, 10.0, 0.0)             # 20 px tall art, feet at the origin
>>> eye = resolve_viewpoint(world, Viewpoint(at=(0.0, 0.0, 0.0), focal=1000.0),
...                         extents={"near": box, "far": box}, width=1280, height=720)
>>> placed = member_placements(world, eye, extents={"near": box, "far": box}, width=1280, height=720)
>>> placed["near"].at, round(placed["near"].scale, 2)
((500.0, 0.0), 25.0)
>>> placed["far"].at, round(placed["far"].scale, 2)
((50.0, 0.0), 2.5)
```

### Module Attributes

| [`Box`](#an.ir.world.Box)                         | `(x0, y0, x1, y1)` in its art's pixels at `stage.scale` 1, relative to its placement point (a character's feet).                                                                                         |
|------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Extents`](#an.ir.world.Extents)                     | `{member or stream id: Box | None}`, measured by the stage ([`an.stage.world.member_extents()`](an.stage.world.html.md#an.stage.world.member_extents)); the IR layer only reads it. |
| [`HAND_PLACEMENT_TOLERANCE_PX`](#an.ir.world.HAND_PLACEMENT_TOLERANCE_PX) | A hand `stage.at` this far from the world's placement is "the same" (the cut-continuity tolerance, an#394); farther is a lint warning.                                                                   |
| [`PERSPECTIVE_TOLERANCE`](#an.ir.world.PERSPECTIVE_TOLERANCE)       | A hand placement whose scale differs from the ground plane's by more than this fraction is out of perspective (catalogue A6).                                                                            |

### Functions

| [`fit_channel`](#an.ir.world.fit_channel)(g, a, b, \*, tolerance, min_step)      | One channel's motion `g` on `[a, b]` as tweens: `[(t0, t1, v0, v1, easing)]`, each a cubic-Bézier easing whose end slopes match `g`'s (a Hermite fit: control points `(1/3, d0/3, 2/3, 1 − d1/3)`), split in two wherever the fit strays more than `tolerance` from `g` — dense where the motion bends (a stream instance near the camera), one segment where it is straight.   |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`focal_length`](#an.ir.world.focal_length)(viewpoint, \*, width)                 | The lens in pixels: `focal` as given, else from `fov` (horizontal, degrees; `DFLT_FOV_DEG` when unset) and the frame width.                                                                                                                                                                                                                                                     |
| [`ground_scale`](#an.ir.world.ground_scale)(projection, at, \*, floor_y, unit)    | The `stage.scale` of a member standing on the horizontal plane `y = floor_y` whose feet are drawn at screen `at` (px from the frame centre), or `None` at or above the horizon or when the plane is not below the eye.                                                                                                                                                          |
| [`frame_poses`](#an.ir.world.frame_poses)(scene, \*[, film_starts])              | Per framed shot, where each frame stands in the world as the shot opens and as it closes (after the shot's own `<frame>:at_*` actions): what `an world show --frames` prints.                                                                                                                                                                                                   |
| [`has_world`](#an.ir.world.has_world)(scene)                                   | Whether lowering would change anything: a world, or a shot with a viewpoint.                                                                                                                                                                                                                                                                                                    |
| [`lower_world`](#an.ir.world.lower_world)(scene, \*, extents[, ...])             | The scene with every framed shot's placements derived from the world.                                                                                                                                                                                                                                                                                                           |
| [`member_of`](#an.ir.world.member_of)(entity, \*\*placement)                   | The world member a shot entity becomes (the inverse of `entity_of()`): its fields as they are, its `stage` dropped (a member is placed by each shot's viewpoint) and its `after` kept, with `placement` (`at`, `height`, ...) where the world stands it.                                                                                                                        |
| [`member_placements`](#an.ir.world.member_placements)(world, projection, \*, ...)      | Every member's placement under `projection`: `{id: Placed}`.                                                                                                                                                                                                                                                                                                                    |
| [`pose_look`](#an.ir.world.pose_look)(pose)                                    | The `(yaw, pitch)` in degrees a pose faces.                                                                                                                                                                                                                                                                                                                                     |
| [`resolve_viewpoint`](#an.ir.world.resolve_viewpoint)(world, viewpoint, \*, ...)       | The camera a viewpoint is, as a [`Projection`](#an.ir.world.Projection), in its own frame's units.                                                                                                                                                                                                                                                          |
| [`stream_instances`](#an.ir.world.stream_instances)(stream, travel, \*, s_min, s_max) | The instances of `stream` whose position along the travel lies in `[s_min, s_max]`: `[(k, world position)]`, `k` the instance index.                                                                                                                                                                                                                                            |
| [`stream_slots`](#an.ir.world.stream_slots)(stream, travel)                       | How many entities a stream needs by its depth range: one per instance that can be between `near` and `far` at once, plus one.                                                                                                                                                                                                                                                   |
| [`viewpoint_of`](#an.ir.world.viewpoint_of)(world, viewpoint)                     | The shot's viewpoint as a model: a name is looked up in the world.                                                                                                                                                                                                                                                                                                              |

### Classes

| [`Lowered`](#an.ir.world.Lowered)(scene[, notes, origins, carried])        | The scene as the compiler will see it, the notes to report, and for each framed shot where its lowered entities came from (`origins`: per lowered entity index, the author's entity index, or `None` for one the world added), so a finding on a lowered shot can name the author's line.   |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Placed`](#an.ir.world.Placed)(id, at, scale, depth, box, in_frame, via) | Where one member lands in a framed shot.                                                                                                                                                                                                                                                    |
| [`Projection`](#an.ir.world.Projection)(at, forward, right, down, focal)      | A resolved viewpoint: where the camera is, which way it looks, its lens.                                                                                                                                                                                                                    |
| [`WorldNote`](#an.ir.world.WorldNote)(shot, index, severity, kind, ...)      | One thing the lowering did or could not do for one shot, for `an validate` (its severity) and `an world show`.                                                                                                                                                                              |

### Exceptions

| [`WorldError`](#an.ir.world.WorldError)   | A world or viewpoint that cannot be resolved (an unknown member, a subject whose extent is unknown, a viewpoint name the world does not have, a travel past its budget).   |
|---------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### an.ir.world.Box

`(x0, y0, x1, y1)` in its art’s pixels at
`stage.scale` 1, relative to its placement point (a character’s feet).
`None` means it could not be measured (nothing drawn, or a compile that
failed: the lowering’s note says which).

* **Type:**
  A member’s native extent

alias of [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.ir.world.Extents

`{member or stream id: Box | None}`, measured by the stage
([`an.stage.world.member_extents()`](an.stage.world.html.md#an.stage.world.member_extents)); the IR layer only reads it.

alias of [`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), `Box | None`]

### an.ir.world.HAND_PLACEMENT_TOLERANCE_PX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 2.0*

A hand `stage.at` this far from the world’s placement is “the same”
(the cut-continuity tolerance, an#394); farther is a lint warning.

### *class* an.ir.world.Lowered(scene, notes=list(), origins=dict(), carried=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The scene as the compiler will see it, the notes to report, and for
each framed shot where its lowered entities came from (`origins`: per
lowered entity index, the author’s entity index, or `None` for one the
world added), so a finding on a lowered shot can name the author’s line.

#### carried *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)]*

Per continued shot (an#542), how many actions its `continue:` put
before the author’s, so a finding’s `actions/<k>` can name the
author’s line.

### an.ir.world.PERSPECTIVE_TOLERANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.15*

A hand placement whose scale differs from the ground plane’s by more than
this fraction is out of perspective (catalogue A6).

### *class* an.ir.world.Placed(id, at, scale, depth, box, in_frame, via, note='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Where one member lands in a framed shot.

#### at *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Screen pixels from the frame centre; `None` when another pass places
it (attached without an offset) or it cannot be placed (see `note`).

#### box *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Its screen box, when its extent is known.

#### note *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

Why it is not placed by the world, when it is not.

#### via *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`world` (projected), `attached` (from the host’s placement),
`host` (goes with the host, placed by nothing here), `environment`.

### *class* an.ir.world.Projection(at, forward, right, down, focal)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A resolved viewpoint: where the camera is, which way it looks, its lens.

```pycon
>>> eye = Projection(at=(0.0, 0.0, 0.0), forward=(0.0, 0.0, 1.0), right=(1.0, 0.0, 0.0), down=(0.0, 1.0, 0.0), focal=1000.0)
>>> eye.project((2.0, -1.0, 10.0))
(200.0, -100.0, 10.0)
>>> eye.project((0.0, 0.0, -1.0)) is None
True
>>> rolled = Projection((0.0, 0.0, 0.0), *_basis(0.0, 0.0, 90.0), focal=100.0)
>>> [round(v, 6) + 0.0 for v in rolled.project((1.0, 0.0, 10.0))]   # a point on the right: now at the bottom
[0.0, 10.0, 10.0]
```

#### moved(by)

The same camera translated by `by` (the vehicle moved).

* **Return type:**
  [`Projection`](#an.ir.world.Projection)

#### project(p)

`(sx, sy, depth)`: screen pixels from the frame centre, and the
depth; `None` for a point at or behind the camera.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### transformed(pose)

The same camera carried by a frame whose pose is `pose`: this
projection is in the frame’s units, the result is in its parent’s
(the world’s, for a frame’s world pose).

```pycon
>>> eye = Projection((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 100.0)
>>> eye.transformed(Pose(at=(0.0, 0.0, 4.0))).at
(0.0, 0.0, 4.0)
>>> eye.transformed(Pose()) is eye
True
```

* **Return type:**
  [`Projection`](#an.ir.world.Projection)

#### view(p)

`p` in camera coordinates: `(right, down, depth)`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### *exception* an.ir.world.WorldError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A world or viewpoint that cannot be resolved (an unknown member, a
subject whose extent is unknown, a viewpoint name the world does not
have, a travel past its budget). The IR layer raises it; `an validate`
reports it as an error and the lowering is then skipped for that scene.

### *class* an.ir.world.WorldNote(shot, index, severity, kind, entity, message)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One thing the lowering did or could not do for one shot, for
`an validate` (its severity) and `an world show`.

#### *property* description *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The note as a finding says it (validate and the render alike).

#### *property* ir_path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

the shot’s entities.

* **Type:**
  Where a finding on it points

### an.ir.world.fit_channel(g, a, b, , tolerance, min_step)

One channel’s motion `g` on `[a, b]` as tweens: `[(t0, t1, v0, v1,
easing)]`, each a cubic-Bézier easing whose end slopes match `g`’s (a
Hermite fit: control points `(1/3, d0/3, 2/3, 1 − d1/3)`), split in two
wherever the fit strays more than `tolerance` from `g` — dense where
the motion bends (a stream instance near the camera), one segment where
it is straight. A segment is never shorter than `min_step`.

```pycon
>>> segs = fit_channel(lambda t: 100.0 / (10.0 - t), 0.0, 9.0, tolerance=1.0, min_step=0.05)
>>> segs[0][:2], segs[-1][1], round(segs[-1][3], 1)
((0.0, 4.5), 9.0, 100.0)
>>> len(segs) < 8
True
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.ir.world.focal_length(viewpoint, , width)

The lens in pixels: `focal` as given, else from `fov` (horizontal,
degrees; `DFLT_FOV_DEG` when unset) and the frame width. A wider frame at
the same field of view is a longer focal, so a world framed once frames the
same at any resolution.

```pycon
>>> round(focal_length(Viewpoint(fov=90.0), width=1280))
640
>>> focal_length(Viewpoint(focal=500.0), width=1280)
500.0
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.ir.world.frame_poses(scene, , film_starts=None)

Per framed shot, where each frame stands in the world as the shot opens
and as it closes (after the shot’s own `<frame>:at_*` actions): what
`an world show --frames` prints.

```pycon
>>> from an.ir.schema import Frame, FrameMoving, Viewpoint, World
>>> scene = SceneIR(world=World(frames={"car": Frame(moving=FrameMoving(speed=10.0))},
...                             viewpoints={"v": Viewpoint(at=(0.0, 0.0, 0.0), frame="car")}),
...                 timeline=[Shot(id="s", duration=2.0, viewpoint="v")])
>>> row = frame_poses(scene)[0]
>>> row["viewpoint_frame"], row["frames"][0]["name"], row["frames"][0]["end"]["at"]
('car', 'car', (0.0, 0.0, 20.0))
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.ir.world.ground_scale(projection, at, , floor_y, unit)

The `stage.scale` of a member standing on the horizontal plane `y = floor_y` whose feet are drawn at screen `at` (px from the frame centre), or `None` at or above the horizon or when the plane is not below the eye.

The single-view relation (catalogue A6): the ray through the pixel meets the
floor at depth `t * f`, and a member of `unit` world units per native
pixel is drawn at `unit * f / depth` = `unit * ray_y / (floor_y - eye_y)`,
so scale grows with the pixel’s distance below the horizon.

```pycon
>>> eye = Projection((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 1000.0)
>>> round(ground_scale(eye, (0.0, 100.0), floor_y=1.0, unit=0.01), 3)    # feet 100 px below the horizon
1.0
>>> round(ground_scale(eye, (0.0, 200.0), floor_y=1.0, unit=0.01), 3)    # nearer: twice the size
2.0
>>> ground_scale(eye, (0.0, -50.0), floor_y=1.0, unit=0.01) is None      # above the horizon
True
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.ir.world.has_world(scene)

Whether lowering would change anything: a world, or a shot with a viewpoint.

```pycon
>>> has_world(SceneIR())
False
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.ir.world.lower_world(scene, , extents, film_starts=None, fps=None, extent_problems=None, plane_geometry=None)

The scene with every framed shot’s placements derived from the world.

A shot without a viewpoint is returned as it is. For a framed shot: its
listed entities keep their order of appearance among themselves but are
drawn in depth order (far first) with the members the frame shows and the
shot did not list; environments come first; listed entities that are not
members go on top. A listed member’s hand `stage.at` wins (a note says
when it disagrees with the world; its `scale` is the world’s unless set);
one without is filled in. A member the viewpoint hides is left out unless
the shot lists it: the listing wins, and a note says so. Under a travel,
the streams’ slot entities are added with their motion; a scene already
lowered gains nothing from a second pass.

`extents` is what the stage measured ([`an.stage.world.member_extents()`](an.stage.world.html.md#an.stage.world.member_extents)),
`extent_problems` why some could not be; `film_starts` is where each
shot starts in the film, so stream phase is continuous across cuts (the
shot sum by default); `plane_geometry` is `{environment member id: {plane:
(offset, box)}}`, each plane’s origin on screen (`Plane.offset`) and its
drawn box around it (`None`: unknown), read by the stage
(`an.stage.world.plane_geometry()`): where a plane at a world depth is
anchored and when it is on screen (an#503; the origin and no box for one
it does not name).

Raises [`WorldError`](#an.ir.world.WorldError) for a viewpoint the world cannot resolve.

```pycon
>>> lower_world(SceneIR(), extents={}).scene.timeline
[]
```

* **Return type:**
  [`Lowered`](#an.ir.world.Lowered)

### an.ir.world.member_of(entity, \*\*placement)

The world member a shot entity becomes (the inverse of
`entity_of()`): its fields as they are, its `stage` dropped (a
member is placed by each shot’s viewpoint) and its `after` kept, with
`placement` (`at`, `height`, …) where the world stands it. Its
`joints` stay with the shot: they tie it to other entities of THAT shot,
and `entity_of()` gives a member none.

```pycon
>>> e = AssetRef(kind="prop", id="lamp", store="props", ref="lamp",
...              stage=StagePlacement(at=(1.0, 2.0), after="set/sky"))
>>> m = member_of(e, at=(0.0, 0.0, 5.0), height=1.0)
>>> m.at, m.after, m.stage
((0.0, 0.0, 5.0), 'set/sky', None)
```

* **Return type:**
  [`WorldMember`](an.ir.schema.html.md#an.ir.schema.WorldMember)

### an.ir.world.member_placements(world, projection, , extents, width, height, hide=(), hand=None, extent_problems=None, member_at=None, fixed=None)

Every member’s placement under `projection`: `{id: Placed}`.

Positioned members are projected; attached ones follow their host (an
offset in the host’s native units, times the host’s scale); an
environment is present with no placement. A member behind the camera
is placed nowhere and is not in frame. `hand` is `{id: (at, scale)}`
for members a shot placed by hand, positioned or attached: that placement
stands in for the derived one (its depth stays the world’s), so what is
attached to it follows the hand, as the compiler’s own passes do.
`extent_problems` says why an extent could not be measured, for the note.
`member_at` overrides a member’s `at` with where it stands in the
viewpoint’s frame (a member in another frame, or moved by an action);
`fixed` is a placement some other pass already settled (a member in
motion), which attached members then follow.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Placed`](#an.ir.world.Placed)]

### an.ir.world.pose_look(pose)

The `(yaw, pitch)` in degrees a pose faces.

```pycon
>>> pose_look(Pose())
(0.0, 0.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.ir.world.resolve_viewpoint(world, viewpoint, , extents, width, height, member_at=None)

The camera a viewpoint is, as a [`Projection`](#an.ir.world.Projection), in its own frame’s
units. `member_at` overrides a subject’s `at` with where it stands in
the VIEWPOINT’s frame (a subject in another frame, at the shot’s start).

A viewpoint with `at` is that camera. One with a `subject` is computed:
on the look direction, at the distance that fills `fill` of the frame
with the subject’s band (`SHOT_SIZES`), shifted so the band’s centre lands
at `subject_at`. With several subjects the band is their union, aimed at
their mean depth, and the distance is what the NEAREST subject needs from
its own depth, so every subject fits the frame’s height and width.

```pycon
>>> from an.ir.schema import World, WorldMember
>>> world = World(members=[WorldMember(kind="prop", id="p", store="props", ref="p", at=(3.0, 0.0, 10.0), height=2.0)])
>>> eye = resolve_viewpoint(world, Viewpoint(subject="p", size="full", focal=900.0),
...                         extents={"p": (-10.0, -40.0, 10.0, 0.0)}, width=1600, height=900)
>>> [round(v, 3) for v in eye.at]           # 2 units tall fills 0.9 × 900 px: 2.222 away, centred on the box
[3.0, -1.0, 7.778]
```

* **Return type:**
  [`Projection`](#an.ir.world.Projection)

### an.ir.world.stream_instances(stream, travel, , s_min, s_max)

The instances of `stream` whose position along the travel lies in
`[s_min, s_max]`: `[(k, world position)]`, `k` the instance index.

Instance `k` stands at `k × mean spacing` plus a seeded jitter that
keeps consecutive spacings inside the stream’s range, `lane` to the right
of the direction of travel, at height `y`.

```pycon
>>> from an.ir.schema import Stream, Travel
>>> t = Travel(speed=10.0)
>>> s = Stream(id="pole", ref="pole", height=6.0, every=12.0, lane=2.0)
>>> stream_instances(s, t, s_min=0.0, s_max=30.0)
[(0, (2.0, 0.0, 0.0)), (1, (2.0, 0.0, 12.0)), (2, (2.0, 0.0, 24.0))]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]]

### an.ir.world.stream_slots(stream, travel)

How many entities a stream needs by its depth range: one per instance
that can be between `near` and `far` at once, plus one. Instance `k`
is drawn by slot `k mod slots`, so an entity is reused for the next
instance once this one has passed the camera. A shot takes the larger of
this and what its viewpoint shows (`_span_slots()`, an#516), so the
count, and the slot an instance takes, can differ between two shots;
nothing relies on it, since each shot compiles alone.

```pycon
>>> stream_slots(Stream(id="pole", ref="pole", height=6.0, every=12.0), Travel(speed=10.0, near=0.5, far=60.0))
6
```

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.ir.world.viewpoint_of(world, viewpoint)

The shot’s viewpoint as a model: a name is looked up in the world.

```pycon
>>> viewpoint_of(World(viewpoints={"a": Viewpoint(focal=1.0)}), "a").focal
1.0
>>> viewpoint_of(None, "a")
Traceback (most recent call last):
...
an.ir.world.WorldError: shot names viewpoint 'a' but the scene has no `world`
```

* **Return type:**
  [`Viewpoint`](an.ir.schema.html.md#an.ir.schema.Viewpoint) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
