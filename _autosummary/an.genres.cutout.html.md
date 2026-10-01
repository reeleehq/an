# an.genres.cutout

The cut-out animation genre, declared as one object (still inside `an`).

ADR 0001 §First slice: the cut-out genre’s IR extensions register through the
same door any genre uses — the `an.genres` entry point (`pyproject.toml`
declares `cutout_animation = "an.genres.cutout:CUTOUT"`) — instead of being
wired into the core. `CUTOUT` lists:

- **action kinds** `play` ([`an.characters.registration`](an.characters.registration.html.md#module-an.characters.registration)) and
  `expression` ([`an.expression.registration`](an.expression.registration.html.md#module-an.expression.registration));
- **entity kind** `character`, whose nodes are stage nodes (`stage.node`);
- the **\`\`[emotion]\`\`** dialogue sugar;
- its **semantic checks**: `play` and `expression` resolution, the turn
  checks (contradicted `from_direction`, a mouth hidden while speaking) and
  view continuity across a cut, placed in the report where they always were.

Its `name` is the persisted genre slug `cutout_animation`, the one
`an.genre` declares to `nw` (ADR 0001 decision 9: persisted
identifiers do not change). When the `cutan` package exists (P8), this object
moves there and registers through the same entry point from that distribution;
nothing in the core’s dispatch changes.

Importing this module registers nothing: [`an.genres.load()`](an.genres.html.md#an.genres.load) (or
[`an.genres.register_genre()`](an.genres.html.md#an.genres.register_genre)) does.

```pycon
>>> CUTOUT.provides()["action kinds"]
('play', 'expression')
```

### Module Attributes

| [`CUTOUT_GENRE_NAME`](#an.genres.cutout.CUTOUT_GENRE_NAME)   | The genre's persisted slug (also `an.genre.CUTOUT_ANIMATION_SLUG`).   |
|----------------------------------------------------------------------|-----------------------------------------------------------------------|

### an.genres.cutout.CUTOUT_GENRE_NAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'cutout_animation'*

The genre’s persisted slug (also `an.genre.CUTOUT_ANIMATION_SLUG`).
