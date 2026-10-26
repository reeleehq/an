# an.world_cli

`an world …`: the scene’s world from the shell (ADR 0009).

Thin projections of [`an.stage.world`](an.stage.world.html.md#module-an.stage.world), wired into the CLI by
`an.tools._dispatch_namespaces`.

### Functions

| [`show`](#an.world_cli.show)(project_dir[, shot, json, frames, scene])   | Print every framed shot as the compiler sees it: each entity's placement derived from the scene's world, and what the world added, replaced or could not place.   |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|

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
