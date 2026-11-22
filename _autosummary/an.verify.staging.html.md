# an.verify.staging

Staging checks: a figure faces the way it goes, and is painted in front of what stands behind it.

Two constraints on the one interface ([`an.verify.constraints.Constraint`](an.verify.constraints.html.md#an.verify.constraints.Constraint)),
over the compiled shot:

- `facing_travel` (warning): an entity whose art says which way it faces
  (`metadata.faces` in its store document, or the entity’s own
  `overrides.faces`) moves the other way: a character walking backwards
  because it was never turned (flip-to-turn) or was turned the wrong way.

How it reads a shot. The facing is where the art’s declared side points on the
set (its own and every parent’s mirror and rotation, before the camera, as the
`light` check reads a shaded side), at every frame. The travel is the
entity’s OWN move, its origin’s `x`/`y` in its parent’s frame carried onto
the set through that parent: a camera pan, a parallax wrapper or a vehicle the
entity rides is not the entity walking. A frame where the art is squashed (a
flip-to-turn passing through zero, its side probe under half its longest
length in the shot) faces nowhere and is not judged.

`faces` is `"left"` or `"right"` (the way the unmirrored art faces), or,
for art whose facing depends on what it shows, a map from a swap set to its
keys’ facings: `{"face": {"dozy": "left", "rage": "left"}, "view": {"side":
"right"}}`. A key the map does not list (a front face) faces nowhere and is
not judged, and so is a set the shot never sets (the compiled document has no
channel for a rig’s rest key). `overrides: {faces: false}` on the entity
turns the check off for it (a figure that backs away on purpose). The facing
is measured at the entity’s root: a part mirrored on its own is not followed.

- `depth_order` (warning, an#820): a solid that walks past a floor prop
  standing farther back than its feet, and is painted under it, reads as
  walking behind it. In a shot with a floor, the foot line is the depth cue:
  lower on the set is nearer the camera.

How it reads a shot. A **floor prop** is an item whose holder at that instant
(the hold layer’s report, `meta.extensions.solve.holds`) is the floor or a
place on the set: `ground`, `ground@x`, `world@x,y` (an item put down,
let fall, or staged with `overrides: {held_by: world@x,y}`), so a cup on a
table or a novel on a desk that nothing holds is not one; nor is one whose foot
rests on another solid’s top (`world@` on a counter top,
[`rests_on()`](#an.verify.staging.rests_on)). An item is held, and not judged, while its `paint_after`
channel names a body’s part (an#537). Floor props are chosen in ONE place,
[`held_on_floor()`](#an.verify.staging.held_on_floor), handed to [`depth_inversions()`](#an.verify.staging.depth_inversions) as `on_floor`. A
**walker** is any solid that is not an item of the hold layer (which carries
it, or lets it fall: a falling musket does not walk), such as a character or a
pushed crate, whose OWN travel on the set (as `facing_travel` reads it: its
origin’s steps through its parent, so a camera pan or a ride is not a walk;
across the set or up and down it) is at least `MIN_TRAVEL_SPEED_PX_S`;
once it is painted under a prop behind it, the stretch goes on while it stays
there, though it stops. The pairs are the `solidity` check’s: the same
boxes, read the same way, on the same samples
(`an.verify.constraints.SOLIDITY_SAMPLE_S`), covering more than
`an.verify.constraints.SOLIDITY_TOLERANCE` of the smaller, two members
the world paints by depth skipped. A `stage.after` does not excuse a pair
here: a misplaced one is how the mistake is made.

The prop stands farther back when its foot (its box’s bottom) is between the
walker’s middle and [`DEPTH_MARGIN_SHARE`](#an.verify.staging.DEPTH_MARGIN_SHARE) of the walker’s height above
the walker’s feet (its box’s bottom). Both are read on the canvas, which a
camera pan and zoom move and scale alike, and the margin is a share of the
walker’s height, so a wide and a close-up agree; a camera roll is not undone.
Equal foot lines (the margin) give no depth cue and are not judged: the
authoring answer there is to put the prop a little upstage. Limits: a pass
quicker than the sample step can fall between two samples, and a staged prop
nothing holds is not judged.

```pycon
>>> [c.name for c in STAGING_CONSTRAINTS]
['facing_travel', 'depth_order']
```

### Module Attributes

| [`FACES_KEY`](#an.verify.staging.FACES_KEY)           | Where art says which way it faces (in its store document's `metadata`, or the entity's own `overrides`).                                             |
|----------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DEPTH_MARGIN_SHARE`](#an.verify.staging.DEPTH_MARGIN_SHARE)  | How far above a walker's feet, as a share of its height, a floor prop's foot must stand to read as farther back: closer foot lines are no depth cue. |
| [`FLOOR_HOLDERS`](#an.verify.staging.FLOOR_HOLDERS)       | The holders (the hold report's text, before any `@`) that put an item on the floor or at a place of the set, not in a hand or on a body.             |
| [`STAGING_CONSTRAINTS`](#an.verify.staging.STAGING_CONSTRAINTS) | The staging checks, in the order they run.                                                                                                           |

### Functions

| [`declared_faces`](#an.verify.staging.declared_faces)(entity, stores)                     | `faces` from the entity's `overrides` (winning) or its art's `metadata`; `None` when neither says.                                                                                                                                                                                                                                                 |
|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`art_facing_at`](#an.verify.staging.art_facing_at)(faces, pose, entity_id)              | The way the unmirrored art of `entity_id` faces under `pose` (a normalised declaration): the declaration itself when it is a facing; else the facing of the first swap set it lists whose key in force (a channel of that set's name on the entity or a part of it) it lists; `None` for a key it does not list, or no channel.                    |
| [`backward_runs`](#an.verify.staging.backward_runs)(entity, times, xs, facings, \*)      | The stretches where an entity whose own travel has brought it to set x `xs[i]` at `times[i]`, facing `facings[i]` on the set (`None`: not judged), goes the other way.                                                                                                                                                                             |
| [`stands_behind`](#an.verify.staging.stands_behind)(walker_box, prop_box, \*[, ...])     | How many px the prop's foot stands above the walker's feet when it reads as farther back and the two overlap: its foot (`prop_box`'s bottom, boxes are `(x0, y0, x1, y1)`, y down) between the walker's middle and `margin_share` of the walker's height above its feet, and the boxes covering more than `tolerance` of the smaller; else `None`. |
| [`rests_on`](#an.verify.staging.rests_on)(prop_box, other_box)                      | Whether a prop's foot (the middle of its box's bottom) rests on another solid: it lies inside `other_box`, in its upper half (on its top, not at its foot in front of it).                                                                                                                                                                         |
| [`floor_holder_at`](#an.verify.staging.floor_holder_at)(timeline, t)                       | Whether the hold report's holder timeline of an item (`[[t, holder], ...]`) has it on the floor or at a place of the set at `t` ([`FLOOR_HOLDERS`](#an.verify.staging.FLOOR_HOLDERS)).                                                                                                                                                  |
| [`held_on_floor`](#an.verify.staging.held_on_floor)(holders)                             | `on_floor(entity_id, t)` for [`depth_inversions()`](#an.verify.staging.depth_inversions), from the hold report's `holders`: an item whose holder at `t` puts it on the floor or at a place of the set ([`floor_holder_at()`](#an.verify.staging.floor_holder_at)).                                                                |
| [`depth_inversions`](#an.verify.staging.depth_inversions)(doc, entities, on_floor, \*, ...) | Every walker among `entities` painted under a floor prop that stands behind it ([`stands_behind()`](#an.verify.staging.stands_behind)), one record per pair and stretch of sampled instants.                                                                                                                                            |

### Classes

| [`FacingRun`](#an.verify.staging.FacingRun)(entity, moves, start, end, distance)    | `entity` moved `moves` (`left`/`right`) while facing the other way from `start` to `end` (s), over `distance` px of the set.                                                                   |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DepthInversion`](#an.verify.staging.DepthInversion)(walker, prop, start, end, upstage) | `walker` was painted under `prop` from `start` to `end` (s, the sampled instants), though the prop's foot stood up to `upstage` px farther back (higher on the canvas) than the walker's feet. |

### an.verify.staging.DEPTH_MARGIN_SHARE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.05*

How far above a walker’s feet, as a share of its height, a floor prop’s foot
must stand to read as farther back: closer foot lines are no depth cue.

### *class* an.verify.staging.DepthInversion(walker, prop, start, end, upstage)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`walker` was painted under `prop` from `start` to `end` (s, the
sampled instants), though the prop’s foot stood up to `upstage` px
farther back (higher on the canvas) than the walker’s feet.

### an.verify.staging.FACES_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'faces'*

Where art says which way it faces (in its store document’s `metadata`, or
the entity’s own `overrides`).

### an.verify.staging.FLOOR_HOLDERS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'ground', 'world'})*

The holders (the hold report’s text, before any `@`) that put an item on
the floor or at a place of the set, not in a hand or on a body.

### *class* an.verify.staging.FacingRun(entity, moves, start, end, distance)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`entity` moved `moves` (`left`/`right`) while facing the other
way from `start` to `end` (s), over `distance` px of the set.

### an.verify.staging.STAGING_CONSTRAINTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Constraint](an.verify.constraints.html.md#an.verify.constraints.Constraint), ...]* *= (Constraint(name='facing_travel', check=<function check_facing_travel>, stage='shot', order=200.0, description='art that says which way it faces does not travel the other way (no walking backwards)', term=None), Constraint(name='depth_order', check=<function check_depth_order>, stage='shot', order=200.0, description='a walker is not painted under a floor prop that stands farther back (an#820)', term=None))*

The staging checks, in the order they run.

### an.verify.staging.art_facing_at(faces, pose, entity_id)

The way the unmirrored art of `entity_id` faces under `pose` (a
normalised declaration): the declaration itself when it is a facing; else
the facing of the first swap set it lists whose key in force (a channel of
that set’s name on the entity or a part of it) it lists; `None` for a key
it does not list, or no channel.

```pycon
>>> faces = {"face": {"dozy": "left"}}
>>> art_facing_at("right", {}, "stu")
'right'
>>> art_facing_at(faces, {("stu/torso/face", "face"): "dozy"}, "stu")
'left'
>>> art_facing_at(faces, {("stu/torso/face", "face"): "smile"}, "stu") is None
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.verify.staging.backward_runs(entity, times, xs, facings, , min_speed=20.0, min_duration=0.2, min_distance=30.0, max_gap=3)

The stretches where an entity whose own travel has brought it to set x
`xs[i]` at `times[i]`, facing `facings[i]` on the set (`None`: not
judged), goes the other way. An interval is judged by the facing at its
start, else at its end; up to `max_gap` unjudged intervals inside a
stretch keep it one stretch.

```pycon
>>> ts = [i / 10 for i in range(11)]
>>> xs = [100.0 * t for t in ts]
>>> backward_runs("stu", ts, xs, ["left"] * 11)
[FacingRun(entity='stu', moves='right', start=0.0, end=1.0, distance=100.0)]
>>> backward_runs("stu", ts, xs, ["right"] * 11)
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`FacingRun`](#an.verify.staging.FacingRun)]

### an.verify.staging.declared_faces(entity, stores)

`faces` from the entity’s `overrides` (winning) or its art’s
`metadata`; `None` when neither says. The one reader of the
declaration, for this check and for a genre that turns figures.

```pycon
>>> from types import SimpleNamespace as NS
>>> stu = NS(overrides=None, store="characters", ref="stu")
>>> declared_faces(stu, {"characters": {"stu": {"metadata": {"faces": "left"}}}})
'left'
>>> declared_faces(NS(overrides={"faces": False}, store="c", ref="s"), {}) is False
True
```

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.verify.staging.depth_inversions(doc, entities, on_floor, , duration, carried=frozenset({}), candidates=None, depth_sorted=frozenset({}), min_speed=20.0, margin_share=0.05, tolerance=0.25)

Every walker among `entities` painted under a floor prop that stands
behind it ([`stands_behind()`](#an.verify.staging.stands_behind)), one record per pair and stretch of
sampled instants. `on_floor(entity_id, t)` says which props are on the
floor at `t` ([`held_on_floor()`](#an.verify.staging.held_on_floor)), `candidates` the ids it can say
so of (default: every entity); `carried` the ids that never walk (the
hold layer’s items: carried, or falling). A prop resting on another solid
lower than it ([`rests_on()`](#an.verify.staging.rests_on): a counter top) is not on the floor. A
walker starts a stretch while it moves at least `min_speed`, and the
stretch goes on while it stays painted under the prop behind it, though it
stops there; a gap of more than one sample ends it.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`DepthInversion`](#an.verify.staging.DepthInversion)]

### an.verify.staging.floor_holder_at(timeline, t)

Whether the hold report’s holder timeline of an item (`[[t, holder],
...]`) has it on the floor or at a place of the set at `t`
([`FLOOR_HOLDERS`](#an.verify.staging.FLOOR_HOLDERS)).

```pycon
>>> tl = [[0.0, "world@-840,460"], [1.0, "stu/hand_r"], [3.0, "ground"]]
>>> [floor_holder_at(tl, t) for t in (0.5, 2.0, 3.5)]
[True, False, True]
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.verify.staging.held_on_floor(holders)

`on_floor(entity_id, t)` for [`depth_inversions()`](#an.verify.staging.depth_inversions), from the hold
report’s `holders`: an item whose holder at `t` puts it on the floor or
at a place of the set ([`floor_holder_at()`](#an.verify.staging.floor_holder_at)). The one place floor props
are chosen: a later reading (a staged prop nothing holds) extends this.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.verify.staging.rests_on(prop_box, other_box)

Whether a prop’s foot (the middle of its box’s bottom) rests on another
solid: it lies inside `other_box`, in its upper half (on its top, not at
its foot in front of it). A cup on a counter top, a book on a shelf: the
place it rests at is not the floor.

```pycon
>>> counter = (0, 100, 200, 200)
>>> rests_on((80, 70, 120, 102), counter)  # a cup standing on its top
True
>>> rests_on((80, 170, 120, 198), counter)  # a box at its foot, in front
False
>>> rests_on((300, 70, 340, 102), counter)  # beside it
False
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.verify.staging.stands_behind(walker_box, prop_box, , margin_share=0.05, tolerance=0.25)

How many px the prop’s foot stands above the walker’s feet when it reads
as farther back and the two overlap: its foot (`prop_box`’s bottom, boxes
are `(x0, y0, x1, y1)`, y down) between the walker’s middle and
`margin_share` of the walker’s height above its feet, and the boxes
covering more than `tolerance` of the smaller; else `None`.

```pycon
>>> stu = (0, 0, 40, 200)  # a 200 px walker, feet at y 200
>>> stands_behind(stu, (10, 160, 60, 180))  # a book whose foot is 20 px upstage
20
>>> stands_behind(stu, (10, 185, 60, 195)) is None  # 5 px: equal foot lines
True
>>> stands_behind(stu, (10, 40, 60, 90)) is None  # above his middle: not on his floor
True
>>> stands_behind(stu, (100, 160, 160, 180)) is None  # not where he is
True
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
