# an.world_cli

`an world …`: the scene’s world from the shell (ADR 0009).

Thin projections of [`an.stage.world`](an.stage.world.html.md#module-an.stage.world), wired into the CLI by
`an.tools._dispatch_namespaces`.

### Functions

| [`from_shot`](#an.world_cli.from_shot)(project_dir, shot[, focal, depth, ...])   | Give a scene placed by hand a world: invert a master shot's placements through a pinhole camera and write the `world` and the shot's viewpoint into the scene.   |
|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`show`](#an.world_cli.show)(project_dir[, shot, json, frames, scene])      | Print every framed shot as the compiler sees it: each entity's placement derived from the scene's world, and what the world added, replaced or could not place.  |

### an.world_cli.from_shot(project_dir, shot, focal=0.0, depth=0.0, dry_run=False, scene='scene.md')

Give a scene placed by hand a world: invert a master shot’s placements through a pinhole camera and write the `world` and the shot’s viewpoint into the scene.

Every entity the shot places by hand (`stage.at`) becomes a world member at
one depth, its screen position and scale inverted (x = sx·Z/f, height =
scale·native·Z/f), so the world lowers back to the placements the shot
already has; its environments become members as they are. The shot keeps
its `stage` lines (they agree with the world) and names the new viewpoint,
called after it.
The other shots then take viewpoints by hand. The scene file is updated
through the store: the prose around its blocks is kept.

project_dir: the an project
shot: the master shot’s id
focal: the lens in pixels (default: the default field of view at the scene’s width)
depth: the depth every member stands at, in world units (default: where the tallest is 1.7 tall, so units read as metres)
dry_run: print what would be written, and write nothing
scene: the scene file to read, inside the project (default scene.md)

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.world_cli.show(project_dir, shot='', json=False, frames=False, scene='scene.md')

Print every framed shot as the compiler sees it: each entity’s placement derived from the scene’s world, and what the world added, replaced or could not place.

The derived placements are never written to the project; this is how you
read them. A shot without a viewpoint is not listed: it is placed by hand,
as it always was.

project_dir: the an project
shot: one shot id (default: every framed shot)
json: print the report as JSON instead of text
frames: print instead the scene’s frames of reference, one line per frame per framed shot: its pose in the world as the shot opens and as it closes
scene: the scene file to read, inside the project (default scene.md; for example scene.studio.md)

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
