# an.characters.registration

The character side of the cut-out genre, as declarations: `play` and `character`.

What the cut-out genre ([`an.genres.cutout`](an.genres.cutout.html.md#module-an.genres.cutout)) registers from here (ADR 0001
§First slice):

- the **\`\`play\`\` action kind** — [`an.ir.schema.PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction), how long a
  duration-less play occupies a `sequence` (its natural length, through the
  caller’s extent resolver), and its `scene.md` spelling;
- the **\`\`character\`\` entity kind** — a rigged character, whose nodes are
  nodes of the 2D stage engine (the `stage.node` property space).

Plain declarations: importing this module registers nothing.

```pycon
>>> PLAY.name, CHARACTER.space
('play', 'stage.node')
```

### Functions

| [`play_duration`](#an.characters.registration.play_duration)(action, extent)   | The span a `play` occupies: its `duration`, else its natural extent.    |
|----------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`read_play_md`](#an.characters.registration.read_play_md)(item, \*, index)   | `{kind: play, target, animation, [duration], [speed], [loop], [args]}`. |
| [`write_play_md`](#an.characters.registration.write_play_md)(leaf)             | The `scene.md` entry for `leaf` (`read_play_md`'s inverse).             |

### an.characters.registration.play_duration(action, extent)

The span a `play` occupies: its `duration`, else its natural extent.

`extent` is the caller’s resolver (the compiler and `an validate` pass
one bound to the entity’s descriptor); without one, a motion preset’s own
length ([`an.ir.compose.default_play_extent()`](an.ir.compose.html.md#an.ir.compose.default_play_extent)).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> play_duration(PlayAction(target="a", animation="hop", duration=2.0), None)
2.0
>>> play_duration(PlayAction(target="a", animation="hop"), None)
0.5
```

### an.characters.registration.read_play_md(item, , index)

`{kind: play, target, animation, [duration], [speed], [loop], [args]}`.

Resolved at compile against the target entity’s descriptor `animations`
(an#7), falling back to the motion presets of `an.motion.PRESETS` for a
name the descriptor does not declare, with `args` as the preset’s
parameters (an#166). `loop` omitted means the animation’s own. This
reader accepted the shape from the start, then #24 made it refuse (nothing
resolved a play) while the writer kept emitting it — three days of a
project’s own scene.md failing to parse.

* **Return type:**
  [`PlayAction`](an.ir.schema.html.md#an.ir.schema.PlayAction)

### an.characters.registration.write_play_md(leaf)

The `scene.md` entry for `leaf` (`read_play_md`’s inverse).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
