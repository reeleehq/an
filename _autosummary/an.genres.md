# an.genres

Genres: what a kind of animation adds to the core, declared as one object.

ADR 0001 decisions 2-4 and the core study §2.15. A **genre** (cut-out
animation, data visualisation, mathematical explainers, …) extends the core by
*registration*, never by editing a core `if kind == …` chain. It is one plain,
declarative [`Genre`](#an.genres.Genre) object — the shape `shaping` uses (“a new genre is
one file”) — listing what it registers:

- **action kinds** ([`ActionKind`](#an.genres.ActionKind)): a model, how it occupies time, how
  `scene.md` spells it;
- **entity kinds** ([`EntityKind`](#an.genres.EntityKind)), each naming the property space its
  nodes live in, plus any new **property spaces** and **field kinds** for the
  timing kernel ([`an.timing`](an.timing.md#module-an.timing));
- **semantic checks** ([`SemanticCheck`](#an.genres.SemanticCheck)) that `an validate` runs;
- **md sugar** ([`DialogueSugar`](#an.genres.DialogueSugar)) on `scene.md` dialogue lines.

Because the object is plain data, a genre is \*\*inspectable before it is
loaded\*\*: [`available()`](#an.genres.available) reads every installed genre’s declaration without
registering anything, which is how an unregistered kind’s error can name the
package that provides it.

**Discovery is explicit, never at import time** (decision 3). Importing `an`
registers no genre. [`load()`](#an.genres.load) reads the `an.genres` entry point group and
registers each genre it finds; `an.load(project)`, the `an` CLI and (later)
the MCP entry call it, and anyone can. A package declares its genre as:

```default
[project.entry-points."an.genres"]
cutout_animation = "an.genres.cutout:CUTOUT"
```

[`register_genre()`](#an.genres.register_genre) installs a genre object directly (a test, a notebook, a
genre defined in the same process).

```pycon
>>> from an.genres import Genre, register_genre, installed, without_genres
>>> with without_genres():
...     installed()
()
>>> demo = Genre("demo_genre", title="Demo")
>>> with without_genres():
...     _ = register_genre(demo)
...     installed()
('demo_genre',)
```

### Module Attributes

| [`ENTRY_POINT_GROUP`](#an.genres.ENTRY_POINT_GROUP)      | The entry-point group a genre package declares its [`Genre`](#an.genres.Genre) under.   |
|-------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------|
| [`IN_DISTRIBUTION_GENRES`](#an.genres.IN_DISTRIBUTION_GENRES) | Genres the `an` distribution itself ships, as entry-point values.                                                  |

### Functions

| [`action_kind`](#an.genres.action_kind)(name)                                | The registered kind called `name`, or `None`.                                                                                                                                                                           |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`action_kind_names`](#an.genres.action_kind_names)(\*[, owner])                   | Registered action-kind names in registration order; `owner`'s only when given.                                                                                                                                          |
| [`available`](#an.genres.available)(\*[, entry_points, builtin])           | Every discoverable genre's declaration, by name — read, never registered.                                                                                                                                               |
| `entity_kind`(name)                                                                               |                                                                                                                                                                                                                         |
| `entity_kind_names`(\*[, owner])                                                                  |                                                                                                                                                                                                                         |
| [`entity_space_resolver`](#an.genres.entity_space_resolver)(entities, \*[, default])   | `target -> PropertySpace`: the space its ENTITY's kind declares.                                                                                                                                                        |
| [`discovered_entry_points`](#an.genres.discovered_entry_points)(\*[, entry_points, ...]) | The in-distribution genres (`builtin`) merged with `entry_points` (default: the installed ones), de-duplicated by name — the in-distribution declaration first, so a stale or missing installed entry cannot shadow it. |
| [`genre_entry_points`](#an.genres.genre_entry_points)(\*[, group])                  | The installed `an.genres` entry points (nothing is imported).                                                                                                                                                           |
| [`genres_declaring`](#an.genres.genres_declaring)(test)                           | The installed genres (loaded or not) whose declaration passes `test`.                                                                                                                                                   |
| [`installed`](#an.genres.installed)()                                      | The names of the genres registered in this process, in registration order.                                                                                                                                              |
| [`genre_library`](#an.genres.genre_library)(name, \*[, default])               | The package whose data root holds genre `name`'s library and projects.                                                                                                                                                  |
| `installed_genre`(name)                                                                           |                                                                                                                                                                                                                         |
| [`load`](#an.genres.load)(\*[, entry_points, builtin])                | Register every discoverable genre.                                                                                                                                                                                      |
| [`providers_of`](#an.genres.providers_of)(kind, \*[, registry])               | The installed genres (loaded or not) that declare `kind` in `registry` (a key of [`Genre.provides()`](#an.genres.Genre.provides)).                                                                    |
| [`register_genre`](#an.genres.register_genre)(genre, \*[, replace])             | Register everything `genre` declares, owned by `genre.name`.                                                                                                                                                            |
| [`without_genres`](#an.genres.without_genres)()                                 | Run a block with no genre registered (the core alone), then restore.                                                                                                                                                    |

### Classes

| [`ActionKind`](#an.genres.ActionKind)(name, model[, duration, flatten, ...])   | One kind of action: its model, how it occupies time, how `scene.md` spells it.   |
|------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`DialogueSugar`](#an.genres.DialogueSugar)(name, opener, field, parse, format)   | `scene.md` sugar on a dialogue line: one bracket pair, one `Dialogue` field.     |
| [`EntityKind`](#an.genres.EntityKind)(name[, space, store, description])       | One kind of entity (`AssetRef.kind`): what its nodes' properties are.            |
| [`Genre`](#an.genres.Genre)(name[, title, description, package, ...])     | A genre: one plain, declarative object listing what it registers.                |
| [`SemanticCheck`](#an.genres.SemanticCheck)(name, run[, stage, order, ...])       | One semantic-validation check: `run(ctx)` adds findings to `ctx.report`.         |

### Exceptions

| [`GenreError`](#an.genres.GenreError)                                   | A genre declaration is malformed, or its entry point does not resolve.   |
|-----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`RegistryError`](#an.genres.RegistryError)                                | A registration is malformed or collides with one already made.           |
| [`UnregisteredKindError`](#an.genres.UnregisteredKindError)(what, name, \*[, ...]) | A document names a kind no loaded genre registered.                      |

### *class* an.genres.ActionKind(name, model, duration=None, flatten=None, children=None, read_md=None, write_md=None, md_start=True, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One kind of action: its model, how it occupies time, how `scene.md` spells it.

- `model` validates a document’s action of this kind. A genre’s model
  subclasses [`an.ir.schema.ExtensionAction`](an.ir.schema.md#an.ir.schema.ExtensionAction); the core’s are the
  static members of the schema’s union.
- `duration` is a LEAF’s natural length; a leaf flattens to one
  `FlatAction` on `[t, t + duration]` and advances a `sequence` by it.
- `flatten` replaces that default for kinds that place themselves
  differently (`set` does not advance the cursor) or that hold children
  (`sequence`): `flatten(action, t, ctx) -> new cursor`, where `ctx`
  is [`an.ir.compose.FlattenContext`](an.ir.compose.md#an.ir.compose.FlattenContext).
- `children` lists a composite’s child actions, so generic walkers
  (validation) reach every leaf without knowing the kind.
- `read_md` / `write_md` are the `scene.md` `yaml actions` hooks:
  `read_md(item, index=i) -> action` (`start:` already removed when
  `md_start`) and `write_md(action) -> dict` (without `start`).
  A kind with no `read_md` has no `scene.md` form.

#### md_start *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Does `start:` in `scene.md` wrap this kind in `sequence(delay(start), …)`?

### *class* an.genres.DialogueSugar(name, opener, field, parse, format, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`scene.md` sugar on a dialogue line: one bracket pair, one `Dialogue` field.

`parse(content) -> value` turns what is between the brackets into the
field’s value (raise `ValueError(why)` to refuse it); `format(line) ->
str | None` is the inverse (the content, without brackets, or `None` when
the line carries none). The cut-out genre’s `[emotion]` is one.

### an.genres.ENTRY_POINT_GROUP *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an.genres'*

The entry-point group a genre package declares its [`Genre`](#an.genres.Genre) under.

### *class* an.genres.EntityKind(name, space=None, store=None, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One kind of entity (`AssetRef.kind`): what its nodes’ properties are.

`space` names the registered [`an.timing.spaces.PropertySpace`](an.timing.spaces.md#an.timing.spaces.PropertySpace) its
nodes’ properties live in (`None`: the entity has no animatable nodes, as
a voice); `store` is the project-mall store its `ref` keys into.

### *class* an.genres.Genre(name, title='', description='', package='', library='', action_kinds=(), entity_kinds=(), spaces=(), field_kinds=(), checks=(), dialogue_sugar=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A genre: one plain, declarative object listing what it registers.

`name` is the genre’s persisted slug (`cutout_animation`); it is also
the owner of every entry it registers. `package` names the distribution
that ships it, for error messages. Every collection defaults to empty, so a
later phase adds a field (compile passes, vocabulary, capabilities) without
touching any genre that does not use it.

`spaces` are [`an.timing.spaces.PropertySpace`](an.timing.spaces.md#an.timing.spaces.PropertySpace) objects and
`field_kinds` are `(name, factory)` pairs for
[`an.timing.kinds.register_kind()`](an.timing.kinds.md#an.timing.kinds.register_kind).

`library` names the package whose data root holds the genre’s asset
library and its projects (`~/.local/share/<library>`, ADR 0005, plan §1
decision 7); empty means the core’s (`an`). It is not `package`: the
distribution that ships a genre and the root its data lives under can
differ (the cut-out genre ships inside `an` today, while its library is
already `cutan`’s). The core never names a genre’s library itself —
a project made in a genre asks the genre ([`genre_library()`](#an.genres.genre_library)).

#### provides()

What this genre registers, by registry, as names — without registering it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]]

```pycon
>>> Genre("g", action_kinds=()).provides()["action kinds"]
()
```

### *exception* an.genres.GenreError

Bases: [`RegistryError`](an.genres.registry.md#an.genres.registry.RegistryError)

A genre declaration is malformed, or its entry point does not resolve.

### an.genres.IN_DISTRIBUTION_GENRES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)], ...]* *= (('cutout_animation', 'an.genres.cutout:CUTOUT'),)*

Genres the `an` distribution itself ships, as entry-point values. They are
found by [`load()`](#an.genres.load) WITHOUT relying on installed metadata: an editable
install made before the `an.genres` group existed never refreshes its
`dist-info`, and a missing entry point must never silently drop a genre
that ships in the same distribution as the core (review-244 S1). Still
explicit discovery (only [`load()`](#an.genres.load) reads it, never an import). External
genres (`cutan` after P8) come through the entry point alone; when the
cut-out genre moves there, its line here goes.

### *exception* an.genres.RegistryError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A registration is malformed or collides with one already made.

### *class* an.genres.SemanticCheck(name, run, stage='shot', order=0.0, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One semantic-validation check: `run(ctx)` adds findings to `ctx.report`.

`ctx` is [`an.ir.validate.ValidationContext`](an.ir.validate.md#an.ir.validate.ValidationContext); a `shot` check is
called once per shot with `ctx.shot` set. Within a stage, checks run by
`order` (then registration order), so a genre’s check lands exactly where
it belongs in the report.

### *exception* an.genres.UnregisteredKindError(what, name, , known=(), providers=(), where='')

Bases: [`RegistryError`](an.genres.registry.md#an.genres.registry.RegistryError)

A document names a kind no loaded genre registered.

The message names the installed genres that *could* provide it (read from
their declarations, which are inspectable without loading them), so the fix
is one line: `an.genres.load()`, or installing the package named.

### an.genres.action_kind(name)

The registered kind called `name`, or `None`.

* **Return type:**
  [`ActionKind`](an.genres.registry.md#an.genres.registry.ActionKind) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.genres.action_kind_names(, owner=None)

Registered action-kind names in registration order; `owner`’s only when given.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.available(, entry_points=None, builtin=True)

Every discoverable genre’s declaration, by name — read, never registered.

The in-distribution genres plus the entry points ([`discovered_entry_points()`](#an.genres.discovered_entry_points)).
A genre whose entry point does not import is left out (its error is what
[`load()`](#an.genres.load) raises).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Genre`](#an.genres.Genre)]

### an.genres.discovered_entry_points(, entry_points=None, builtin=True)

The in-distribution genres (`builtin`) merged with `entry_points`
(default: the installed ones), de-duplicated by name — the in-distribution
declaration first, so a stale or missing installed entry cannot shadow it.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`EntryPoint`](https://docs.python.org/3/library/importlib.metadata.html#importlib.metadata.EntryPoint), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> [ep.name for ep in discovered_entry_points(entry_points=())]
['cutout_animation']
```

### an.genres.entity_space_resolver(entities, , default=None)

`target -> PropertySpace`: the space its ENTITY’s kind declares.

The ONE policy for “what are this target’s properties” (review-244 S7):
`an validate`’s generic target check and the compiler’s keyframe check
both use it. A target’s entity is its first path segment; a target with no
entity (the stage camera’s `root`), or an entity whose kind is
unregistered or declares no space, gets `default` — the timing default
[`an.timing.spaces.DFLT_TIMELINE_SPACE`](an.timing.spaces.md#an.timing.spaces.DFLT_TIMELINE_SPACE) when `None`.

(The default EVALUATOR still uses that one space for every target: a
compiled stage document does not carry its entities’ kinds, so a
per-entity evaluation default arrives with the `Engine` seam, P3.)

```pycon
>>> from an.ir.schema import AssetRef
>>> space_of = entity_space_resolver([AssetRef(kind="prop", id="lamp", store="props", ref="l")])
>>> space_of("lamp/shade").name, space_of("root").name
('stage.node', 'stage.node')
```

### an.genres.genre_entry_points(, group='an.genres')

The installed `an.genres` entry points (nothing is imported).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`EntryPoint`](https://docs.python.org/3/library/importlib.metadata.html#importlib.metadata.EntryPoint), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.genre_library(name, , default='an')

The package whose data root holds genre `name`’s library and projects.

`default` (the core package) for no genre, an unknown one, or a genre
that declares none. Reads the genres installed in this process (call
[`load()`](#an.genres.load) first, as every entry point does).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> genre_library(None)
'an'
```

### an.genres.genres_declaring(test)

The installed genres (loaded or not) whose declaration passes `test`.

Each is named as `genre (package)`. Reading declarations imports the
genre modules but registers nothing.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.installed()

The names of the genres registered in this process, in registration order.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.load(, entry_points=None, builtin=True)

Register every discoverable genre. Idempotent.

Discoverable: the genres the `an` distribution ships
([`IN_DISTRIBUTION_GENRES`](#an.genres.IN_DISTRIBUTION_GENRES), unless `builtin=False`) and the
`an.genres` entry points (`entry_points` replaces the installed ones —
tests, a host that curates). Returns the names of the genres registered
after the call. Never called at import time: the CLI, `an.load(project)`
and the MCP entry call it, so a document naming a genre’s kind validates to
that kind’s model.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.providers_of(kind, , registry='action kinds')

The installed genres (loaded or not) that declare `kind` in `registry`
(a key of [`Genre.provides()`](#an.genres.Genre.provides)). Used by the unregistered-kind errors.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.register_genre(genre, , replace=False)

Register everything `genre` declares, owned by `genre.name`.

Idempotent for the same object: registering a genre that is already
installed is a no-op, so [`load()`](#an.genres.load) can be called from every entry point.
A different object under an installed name raises unless `replace`.
All or nothing: a registration that fails part-way leaves no trace.

* **Return type:**
  [`Genre`](#an.genres.Genre)

### an.genres.without_genres()

Run a block with no genre registered (the core alone), then restore.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`None`](https://docs.python.org/3/builtins/constants.html#None)]

```pycon
>>> with without_genres():
...     action_kind("play") is None
True
```

### Modules

| [`cutout`](an.genres.cutout.md#module-an.genres.cutout)     | The cut-out animation genre, declared as one object (still inside `an`).           |
|-------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`registry`](an.genres.registry.md#module-an.genres.registry) | The core's open registries: action kinds, entity kinds, semantic checks, md sugar. |
