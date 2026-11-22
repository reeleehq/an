# an.stage.mirror_states

Mirror states (an#819): the drawing art uses when it is drawn mirrored.

A carried item mirrors with its carrier (the hold layer composes the hand’s
transform, mirror included), which is right for the handle and wrong for
lettering: a “BEST DAD EVER!” mug carried by a character turned to face right
reads backwards. Art says which drawing to use when it is drawn mirrored, per
key of a swap set, in its store document’s `metadata`:

```default
metadata:
  mirror_states: {best_dad: best_dad_mirror}
  lettering: true
```

and the stage swaps to it wherever the drawing’s net x scale on the set is
negative (its own, every parent’s: held, placed, fallen, or mirrored by hand),
so lettering always reads. The `mirror_states` compile pass (after the solve
and the topple, before the camera) samples the compiled document on the
render’s grid ([`an.frame_clock.camera_grid()`](an.frame_clock.html.md#an.frame_clock.camera_grid)) and writes one stepped swap
channel per drawing that is ever mirrored with a mapped key; a shot where none
is leaves the document byte for byte as it was. The `lettering` check warns
about art declaring `lettering: true` drawn mirrored with a drawing that has
no mirror state.

A key maps to a key of the SAME swap set (its mirror drawing is one of the
set’s states). The mirror is read before the camera, as the `light` check
reads a shaded side.

```pycon
>>> mirror_states_of({"metadata": {"mirror_states": {"best_dad": "best_dad_mirror"}}})
{'best_dad': 'best_dad_mirror'}
>>> mirror_states_of({"metadata": {}}), mirror_states_of(None)
({}, {})
>>> is_mirrored((-1.0, 0.0, 0.0, 1.0, 0.0, 0.0)), is_mirrored((-1.0, 0.0, 0.0, -1.0, 0.0, 0.0))
(True, False)
```

### Module Attributes

| [`MIRROR_STATES_KEY`](#an.stage.mirror_states.MIRROR_STATES_KEY)   | The art-metadata key naming each swap-set key's mirror drawing.                                               |
|----------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| [`LETTERING_KEY`](#an.stage.mirror_states.LETTERING_KEY)       | The art-metadata key saying the art carries lettering (it must not read mirrored).                            |
| [`ART_METADATA_KEY`](#an.stage.mirror_states.ART_METADATA_KEY)    | Where the art's declarations live in its store document.                                                      |
| [`MIRROR_STATES_ORDER`](#an.stage.mirror_states.MIRROR_STATES_ORDER) | after `solve` (525) and `topple` (535), which mirror what they carry or tip, before the camera passes (550+). |
| [`MIRROR_TRACK`](#an.stage.mirror_states.MIRROR_TRACK)        | last at the time it runs, so its channel wins over the authored swaps it already accounts for.                |

### Functions

| [`applicable_pairs`](#an.stage.mirror_states.applicable_pairs)(states, keys)                     | The pairs of `states` one swap set can show: both the key and its mirror key are among the set's `keys` (a set projected onto a slot holds only the keys that slot's drawings resolve, so another slot may hold one and not the other).                                                                      |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`art_metadata`](#an.stage.mirror_states.art_metadata)(document)                             | The `metadata` of an art store document (`{}` when it has none).                                                                                                                                                                                                                                             |
| [`declares_lettering`](#an.stage.mirror_states.declares_lettering)(document)                       | Whether the art says it carries lettering (`metadata.lettering: true`).                                                                                                                                                                                                                                      |
| [`drawing_states`](#an.stage.mirror_states.drawing_states)(doc, entity_id, times, \*[, ...])   | Each drawing of `entity_id` in the compiled (or assembled) document `doc` at each of `times`: the swap set and key in force (the timeline's, else the drawing it is built with) and whether it is drawn mirrored on the set (before the camera).                                                             |
| [`is_mirrored`](#an.stage.mirror_states.is_mirrored)(matrix)                                | Whether an affine `(a, b, c, d, x, y)` flips handedness (its net x scale is negative, whatever the rotation): its determinant is negative.                                                                                                                                                                   |
| [`mirror_channel_targets`](#an.stage.mirror_states.mirror_channel_targets)(doc)                        | The `(node path, swap set)` pairs the `mirror_states` pass wrote a channel for in the compiled `doc`.                                                                                                                                                                                                        |
| [`mirror_channels`](#an.stage.mirror_states.mirror_channels)(doc, entity_id, states, times, \*) | `{(node path, swap set): [(t, key), ...]}`: for each drawing of `entity_id` that is ever mirrored showing a key with a mirror state its set can show ([`applicable_pairs()`](#an.stage.mirror_states.applicable_pairs)), its key at each change of `times`, the mirror key wherever it is drawn mirrored. |
| [`mirror_states_of`](#an.stage.mirror_states.mirror_states_of)(document)                         | `{key: its mirror key}` the art declares (`{}` for none); a declaration that is not a mapping of names to names raises.                                                                                                                                                                                      |
| [`mirror_states_pass`](#an.stage.mirror_states.mirror_states_pass)(state)                          | The `mirror_states` compile pass (order [`MIRROR_STATES_ORDER`](#an.stage.mirror_states.MIRROR_STATES_ORDER)): see the module docstring.                                                                                                                                                                     |

### Classes

| [`DrawingState`](#an.stage.mirror_states.DrawingState)(t, path, swap_set, key, mirrored)   | What one drawing of an entity shows at one instant.   |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------|

### Exceptions

| [`MirrorStatesError`](#an.stage.mirror_states.MirrorStatesError)   | Art declares `mirror_states` that do not read.                               |
|----------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`MirrorStatesWarning`](#an.stage.mirror_states.MirrorStatesWarning) | A drawing with a mirror state that the stage cannot swap (said, not raised). |

### an.stage.mirror_states.ART_METADATA_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'metadata'*

Where the art’s declarations live in its store document.

### *class* an.stage.mirror_states.DrawingState(t, path, swap_set, key, mirrored, ambiguous=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one drawing of an entity shows at one instant.

#### ambiguous *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

which one shows
is the runtime’s write-group call, so nothing is swapped on it.

* **Type:**
  More than one of its swap sets written at this instant

### an.stage.mirror_states.LETTERING_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'lettering'*

The art-metadata key saying the art carries lettering (it must not read mirrored).

### an.stage.mirror_states.MIRROR_STATES_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'mirror_states'*

The art-metadata key naming each swap-set key’s mirror drawing.

### an.stage.mirror_states.MIRROR_STATES_ORDER *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 540*

after `solve` (525) and `topple` (535), which
mirror what they carry or tip, before the camera passes (550+).

* **Type:**
  The compile pass’s order

### an.stage.mirror_states.MIRROR_TRACK *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '_\_mirror_\_'*

last at the time it runs, so
its channel wins over the authored swaps it already accounts for.

* **Type:**
  The track the pass’s channels are placed on

### *exception* an.stage.mirror_states.MirrorStatesError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

Art declares `mirror_states` that do not read.

### *exception* an.stage.mirror_states.MirrorStatesWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A drawing with a mirror state that the stage cannot swap (said, not raised).

### an.stage.mirror_states.applicable_pairs(states, keys)

The pairs of `states` one swap set can show: both the key and its mirror
key are among the set’s `keys` (a set projected onto a slot holds only the
keys that slot’s drawings resolve, so another slot may hold one and not the
other).

```pycon
>>> applicable_pairs({"plain": "flipped", "x": "y"}, {"plain", "flipped", "x"})
{'plain': 'flipped'}
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.stage.mirror_states.art_metadata(document)

The `metadata` of an art store document (`{}` when it has none).

* **Return type:**
  [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.stage.mirror_states.declares_lettering(document)

Whether the art says it carries lettering (`metadata.lettering: true`).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.stage.mirror_states.drawing_states(doc, entity_id, times, , swap_sets_only=True)

Each drawing of `entity_id` in the compiled (or assembled) document
`doc` at each of `times`: the swap set and key in force (the timeline’s,
else the drawing it is built with) and whether it is drawn mirrored on the
set (before the camera). `swap_sets_only=False` includes the drawings
with no swap set (their set and key are `None`).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`DrawingState`](#an.stage.mirror_states.DrawingState)]

### an.stage.mirror_states.is_mirrored(matrix)

Whether an affine `(a, b, c, d, x, y)` flips handedness (its net x scale
is negative, whatever the rotation): its determinant is negative.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.stage.mirror_states.mirror_channel_targets(doc)

The `(node path, swap set)` pairs the `mirror_states` pass wrote a
channel for in the compiled `doc`.

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.stage.mirror_states.mirror_channels(doc, entity_id, states, times, , shot_id='')

`{(node path, swap set): [(t, key), ...]}`: for each drawing of
`entity_id` that is ever mirrored showing a key with a mirror state its
set can show ([`applicable_pairs()`](#an.stage.mirror_states.applicable_pairs)), its key at each change of
`times`, the mirror key wherever it is drawn mirrored. Empty when nothing
needs to change. A mirror key no swap set of the entity holds raises: the
declaration names a drawing that does not exist.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]]

### an.stage.mirror_states.mirror_states_of(document)

`{key: its mirror key}` the art declares (`{}` for none); a
declaration that is not a mapping of names to names raises.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.stage.mirror_states.mirror_states_pass(state)

The `mirror_states` compile pass (order [`MIRROR_STATES_ORDER`](#an.stage.mirror_states.MIRROR_STATES_ORDER)):
see the module docstring. A no-op for a shot whose entities’ art declares
no mirror state.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
