# an.ir.world_from_shot

World members from a shot placed by hand (an#514): the projection inverted.

A scene placed by hand (every production written before ADR 0009) adopts a
`world` without being re-authored: each placed entity of a *master* shot is
stood at one depth `Z` in front of a camera at the origin looking down
`+z`, with its screen position and scale inverted through the pinhole
([`an.ir.world`](an.ir.world.html.md#module-an.ir.world)):

> x = sx · Z / f        y = sy · Z / f        height = scale · native · Z / f

so the world lowers back to exactly the placements the shot already has, and
the master’s own `stage` lines agree with it (the `viewpoint` check says
nothing). `Z` defaults to the depth at which the tallest placed entity is
[`DFLT_SUBJECT_HEIGHT`](#an.ir.world_from_shot.DFLT_SUBJECT_HEIGHT) tall. Every member stands at that one depth: what
is nearer or farther is the author’s to say, by moving a member along its
line of sight (`at` and `height` scaled together keep it where the master
shows it). The camera itself, the lens and the scene file are the stage’s
([`an.stage.world.seed_world()`](an.stage.world.html.md#an.stage.world.seed_world)).

```pycon
>>> from an.ir.schema import AssetRef, Shot, StagePlacement
>>> shot = Shot(id="master", duration=1.0, entities=[
...     AssetRef(kind="prop", id="lamp", store="props", ref="lamp",
...              stage=StagePlacement(at=(100.0, 50.0), scale=0.5))])
>>> seeded = seed_members(shot, extents={"lamp": (-10.0, -200.0, 10.0, 0.0)}, focal=500.0)
>>> m = seeded.members[0]
>>> m.at, m.height, seeded.depth
((1.7, 0.85, 8.5), 1.7, 8.5)
```

### Module Attributes

| [`DFLT_SUBJECT_HEIGHT`](#an.ir.world_from_shot.DFLT_SUBJECT_HEIGHT)   | How tall the tallest placed entity is in the seeded world, by default: a person, in metres (the world's units are metres: `DFLT_WORLD_GRAVITY`).   |
|------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`seed_members`](#an.ir.world_from_shot.seed_members)(shot, \*, extents, focal[, ...])   | The world members `shot`'s hand placements are a view of, from a camera at the origin with focal length `focal` (pixels): every entity with a `stage.at` becomes a member at `depth` (default: where the tallest is [`DFLT_SUBJECT_HEIGHT`](#an.ir.world_from_shot.DFLT_SUBJECT_HEIGHT) tall), every environment a member as it is.   |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### Classes

| [`SeededMembers`](#an.ir.world_from_shot.SeededMembers)(members, depth[, skipped])   | What [`seed_members()`](#an.ir.world_from_shot.seed_members) derived: the members (environments first, as listed), the depth the placed ones stand at, and the drawn entities it left out (`{id: why}`), which stay listed in the shot and placed by hand.   |
|---------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### an.ir.world_from_shot.DFLT_SUBJECT_HEIGHT *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1.7*

How tall the tallest placed entity is in the seeded world, by default:
a person, in metres (the world’s units are metres: `DFLT_WORLD_GRAVITY`).

### *class* an.ir.world_from_shot.SeededMembers(members, depth, skipped=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What [`seed_members()`](#an.ir.world_from_shot.seed_members) derived: the members (environments first, as
listed), the depth the placed ones stand at, and the drawn entities it left
out (`{id: why}`), which stay listed in the shot and placed by hand.

### an.ir.world_from_shot.seed_members(shot, , extents, focal, depth=None, drawn=None)

The world members `shot`’s hand placements are a view of, from a
camera at the origin with focal length `focal` (pixels): every entity
with a `stage.at` becomes a member at `depth` (default: where the
tallest is [`DFLT_SUBJECT_HEIGHT`](#an.ir.world_from_shot.DFLT_SUBJECT_HEIGHT) tall), every environment a member
as it is. `extents` is each entity’s native box (`None`: unmeasured);
`drawn` the ids of the entities the stage draws (default: every one
`extents` names), the others (a voice) being no member of a picture.

Raises `ValueError` when nothing is placed by hand, for a non-positive
`depth` or `focal`, and for a drawn entity left out (no `stage.at`,
or unmeasured) that is listed before a member: a framed shot draws its
members first, so it would move on top of them.

* **Return type:**
  [`SeededMembers`](#an.ir.world_from_shot.SeededMembers)
