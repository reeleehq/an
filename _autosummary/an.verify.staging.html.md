# an.verify.staging

Staging checks: a figure faces the way it goes.

One constraint on the one interface ([`an.verify.constraints.Constraint`](an.verify.constraints.html.md#an.verify.constraints.Constraint)),
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

```pycon
>>> [c.name for c in STAGING_CONSTRAINTS]
['facing_travel']
```

### Module Attributes

| [`FACES_KEY`](#an.verify.staging.FACES_KEY)           | Where art says which way it faces (in its store document's `metadata`, or the entity's own `overrides`).   |
|----------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| [`STAGING_CONSTRAINTS`](#an.verify.staging.STAGING_CONSTRAINTS) | The staging checks, in the order they run.                                                                 |

### Functions

| [`declared_faces`](#an.verify.staging.declared_faces)(entity, stores)                | `faces` from the entity's `overrides` (winning) or its art's `metadata`; `None` when neither says.                                                                                                                                                                                                                              |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`art_facing_at`](#an.verify.staging.art_facing_at)(faces, pose, entity_id)         | The way the unmirrored art of `entity_id` faces under `pose` (a normalised declaration): the declaration itself when it is a facing; else the facing of the first swap set it lists whose key in force (a channel of that set's name on the entity or a part of it) it lists; `None` for a key it does not list, or no channel. |
| [`backward_runs`](#an.verify.staging.backward_runs)(entity, times, xs, facings, \*) | The stretches where an entity whose own travel has brought it to set x `xs[i]` at `times[i]`, facing `facings[i]` on the set (`None`: not judged), goes the other way.                                                                                                                                                          |

### Classes

| [`FacingRun`](#an.verify.staging.FacingRun)(entity, moves, start, end, distance)   | `entity` moved `moves` (`left`/`right`) while facing the other way from `start` to `end` (s), over `distance` px of the set.   |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|

### an.verify.staging.FACES_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'faces'*

Where art says which way it faces (in its store document’s `metadata`, or
the entity’s own `overrides`).

### *class* an.verify.staging.FacingRun(entity, moves, start, end, distance)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`entity` moved `moves` (`left`/`right`) while facing the other
way from `start` to `end` (s), over `distance` px of the set.

### an.verify.staging.STAGING_CONSTRAINTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Constraint](an.verify.constraints.html.md#an.verify.constraints.Constraint), ...]* *= (Constraint(name='facing_travel', check=<function check_facing_travel>, stage='shot', order=200.0, description='art that says which way it faces does not travel the other way (no walking backwards)', term=None),)*

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
