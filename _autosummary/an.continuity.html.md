# an.continuity

Open a shot from another shot’s end state (an#542).

A scene that picks up where another left off (the third scene opens on the
last frame of the bedtime scene; back to the studio as the studio scene left
it) used to rebuild that opening by hand: one `set` at 0 per lamp veil,
pillow head, robe and aimed musket, each read by eye off the other scene’s
actions, and a wrong value was a pop at the cut that nothing checked. A shot
now says where it continues from:

```default
continue: studio                   # a shot of this scene
continue: scene.studio.md#studio   # a shot of a sibling scene file
```

and every entity it shares with that shot (by id) opens at that shot’s final
EVALUATED state: the entity’s transform, every channel of its nodes (rotation,
swap keys, alpha, tint), and what holds it (a hand: `held_by` and
`held_rotation`; the ground: `held_by: ground`). The shot’s own opening
`set` or `tween` of a channel wins over the carried one.

[`continue_shots()`](#an.continuity.continue_shots) resolves it before compile, as part of the scene the
compiler sees ([`an.stage.world.lower_scene()`](an.stage.world.html.md#an.stage.world.lower_scene)): the source shot is
compiled (itself lowered and continued first), evaluated at its end by the
runtime’s executable spec, and its state written into the continuing shot as
`set` actions at 0 and hold overrides. The source can be a later shot, or
another scene’s; a cycle is refused ([`ContinuityError`](#an.continuity.ContinuityError)).

```pycon
>>> parse_continue("scene.studio.md#studio"), parse_continue("studio")
(('scene.studio.md', 'studio'), (None, 'studio'))
```

### Functions

| [`continue_shots`](#an.continuity.continue_shots)(scene, mall, \*[, fps, ...])   | `scene` (already world-lowered) with every `continue:` resolved.                                                                                                                                                                    |
|------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`end_states`](#an.continuity.end_states)(doc, entity_ids, \*, at)           | `{entity id: EntityEnd}` of a compiled document evaluated at `at`: each entity's own transform (an alias such as `rotation_rad` folded into the property it writes), then every animated channel of its nodes, one per write group. |
| [`opened_channels`](#an.continuity.opened_channels)(shot, \*, fps)                | `(target, write group)` the shot itself gives a value in its first frame: a `set`, or a `tween` with a `from`.                                                                                                                      |
| [`parse_continue`](#an.continuity.parse_continue)(ref)                           | `(scene file or None, shot id)` of a `continue:` value.                                                                                                                                                                             |

### Classes

| [`EntityEnd`](#an.continuity.EntityEnd)([channels, holder])   | One entity as a shot ends: its channels `{(target, property): value}` and what holds it (the hold layer's last holder; `None` when no hold layer ran).   |
|----------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|

### Exceptions

| [`ContinuityError`](#an.continuity.ContinuityError)(message, \*[, shot])   | A `continue:` that cannot be resolved: an unknown shot or scene file, a cycle, or a source shot that does not compile.   |
|-----------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|

### *exception* an.continuity.ContinuityError(message, , shot=None)

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A `continue:` that cannot be resolved: an unknown shot or scene file,
a cycle, or a source shot that does not compile. `shot` is the shot
whose `continue:` it is: `an validate` reports it at that shot’s
`continue_from`; a render raises it.

### *class* an.continuity.EntityEnd(channels=dict(), holder=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One entity as a shot ends: its channels `{(target, property): value}`
and what holds it (the hold layer’s last holder; `None` when no hold
layer ran).

### an.continuity.continue_shots(scene, mall, , fps=None, project_dir=None, read_scene=None, lower_world=None, compile_shot=None)

`scene` (already world-lowered) with every `continue:` resolved.

`project_dir` is where a sibling scene file is read from (default: the
mall’s `scenes` store’s [`project_dir`](an.stores.scenes.html.md#an.stores.scenes.ScenesStore.project_dir)).
The seams: `read_scene` (`an.ir.sync.read_scene()`), `lower_world`
(`(scene, mall, *, fps) -> scene`, `an.stage.world.lower_scene_world()`)
and `compile_shot` ([`an.stage.compile.compile_shot()`](an.stage.compile.html.md#an.stage.compile.compile_shot)). Each source
is resolved once, and only the shots a continuation needs are: a sibling
file’s other shots are not compiled. A scene without `continue:` comes
back as it is.

* **Return type:**
  [`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR)

### an.continuity.end_states(doc, entity_ids, , at)

`{entity id: EntityEnd}` of a compiled document evaluated at `at`:
each entity’s own transform (an alias such as `rotation_rad` folded into
the property it writes), then every animated channel of its nodes, one
per write group.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`EntityEnd`](#an.continuity.EntityEnd)]

### an.continuity.opened_channels(shot, , fps)

`(target, write group)` the shot itself gives a value in its first
frame: a `set`, or a `tween` with a `from`. A tween from where the
entity is (no `from`) starts from the carried value, so it opens nothing.

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.continuity.parse_continue(ref)

`(scene file or None, shot id)` of a `continue:` value.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
