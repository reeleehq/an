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
  timing kernel ([`an.timing`](an.timing.html.md#module-an.timing));
- **semantic checks** ([`SemanticCheck`](#an.genres.SemanticCheck)) that `an validate` runs;
- **md sugar** ([`DialogueSugar`](#an.genres.DialogueSugar)) on `scene.md` dialogue lines;
- **capabilities** and **analysers** ([`an.capabilities`](an.capabilities.html.md#module-an.capabilities), ADR 0002): the
  capability names its methods require and the derivation of what its assets
  afford;
- **vocabulary** entries — presets, methods, IR-field notes — and **aspects**
  with their default chains ([`an.semantic`](an.semantic.html.md#module-an.semantic), ADR 0003).

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
cutout_animation = "cutan.genre:CUTOUT"
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
| [`API_LEVEL`](#an.genres.API_LEVEL)              | every hook, registry field and moved path a genre package may rely on.                                             |
| [`IN_DISTRIBUTION_GENRES`](#an.genres.IN_DISTRIBUTION_GENRES) | Genres the `an` distribution itself ships, as entry-point values.                                                  |

### Functions

| [`require_api_level`](#an.genres.require_api_level)(level, \*, package)            | Refuse, with an upgrade hint, when this `an` is older than `package` needs.                                                                                                                                            |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`hook_modules`](#an.genres.hook_modules)(\*[, exclude_owner])                | The modules whose code the genres' registered hooks run, sorted and unique.                                                                                                                                            |
| [`register_service`](#an.genres.register_service)(name, target, \*[, owner, ...]) | Register a named service a genre offers the core (an#225).                                                                                                                                                             |
| [`require_service`](#an.genres.require_service)(name, \*[, what, extra])         | The registered service `name`; a typed error naming the install when absent.                                                                                                                                           |
| [`service`](#an.genres.service)(name[, default])                         | The registered service `name`, resolved, or `default` when none is.                                                                                                                                                    |
| [`services`](#an.genres.services)(prefix)                                 | `{name without the prefix: resolved service}` for every service under `prefix`.                                                                                                                                        |
| [`action_kind`](#an.genres.action_kind)(name)                                | The registered kind called `name`, or `None`.                                                                                                                                                                          |
| [`action_kind_names`](#an.genres.action_kind_names)(\*[, owner])                   | Registered action-kind names in registration order; `owner`'s only when given.                                                                                                                                         |
| [`available`](#an.genres.available)(\*[, entry_points, builtin])           | Every discoverable genre's declaration, by name — read, never registered.                                                                                                                                              |
| `entity_kind`(name)                                                                               |                                                                                                                                                                                                                        |
| `entity_kind_names`(\*[, owner])                                                                  |                                                                                                                                                                                                                        |
| [`entity_space_resolver`](#an.genres.entity_space_resolver)(entities, \*[, default])   | `target -> PropertySpace`: the space its ENTITY's kind declares.                                                                                                                                                       |
| [`discovered_entry_points`](#an.genres.discovered_entry_points)(\*[, entry_points, ...]) | The in-distribution genres (`builtin`; none since the cut-out genre moved to `cutan`, an#225) merged with `entry_points` (default: the installed ones), de-duplicated by name — the in-distribution declaration first. |
| [`genre_entry_points`](#an.genres.genre_entry_points)(\*[, group])                  | The installed `an.genres` entry points (nothing is imported).                                                                                                                                                          |
| [`genres_declaring`](#an.genres.genres_declaring)(test)                           | The installed genres (loaded or not) whose declaration passes `test`.                                                                                                                                                  |
| [`installed`](#an.genres.installed)()                                      | The names of the genres registered in this process, in registration order.                                                                                                                                             |
| [`genre_library`](#an.genres.genre_library)(name, \*[, default])               | The package whose data root holds genre `name`'s library and projects.                                                                                                                                                 |
| `installed_genre`(name)                                                                           |                                                                                                                                                                                                                        |
| [`load`](#an.genres.load)(\*[, entry_points, builtin])                | Register every discoverable genre.                                                                                                                                                                                     |
| [`providers_of`](#an.genres.providers_of)(kind, \*[, registry])               | The installed genres (loaded or not) that declare `kind` in `registry` (a key of [`Genre.provides()`](#an.genres.Genre.provides)).                                                                   |
| [`register_genre`](#an.genres.register_genre)(genre, \*[, replace, ...])        | Register everything `genre` declares, owned by `genre.name`.                                                                                                                                                           |
| [`without_genres`](#an.genres.without_genres)()                                 | Run a block with no genre registered (the core alone), then restore.                                                                                                                                                   |

### Classes

| [`ActionKind`](#an.genres.ActionKind)(name, model[, duration, flatten, ...])   | One kind of action: its model, how it occupies time, how `scene.md` spells it.                                                                                                                                                                               |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`CompilePass`](#an.genres.CompilePass)(name, run[, order, compiler, ...])      | One step a genre adds to an engine's COMPILER (shot -> compiled document).                                                                                                                                                                                   |
| [`RuntimeScript`](#an.genres.RuntimeScript)(name, source[, engine, ...])          | JavaScript a genre adds to an engine's RUNTIME (an#247; ADR 0001 decision 4, second batch): for the stage, code that registers visual kinds with `window.anRegisterVisual(kind, make)` -- how the cut-out mouth and eye leave `runtime.js` for `cutan` (P8). |
| [`SwapDeclaration`](#an.genres.SwapDeclaration)(sets[, descriptor, ...])            | What one entity's descriptor declares for the stage compiler's swap vocabulary.                                                                                                                                                                              |
| [`DialogueSugar`](#an.genres.DialogueSugar)(name, opener, field, parse, format)   | `scene.md` sugar on a dialogue line: one bracket pair, one `Dialogue` field.                                                                                                                                                                                 |
| [`EntityKind`](#an.genres.EntityKind)(name[, space, store, ...])               | One kind of entity (`AssetRef.kind`): what its nodes' properties are.                                                                                                                                                                                        |
| [`Genre`](#an.genres.Genre)(name[, title, description, package, ...])     | A genre: one plain, declarative object listing what it registers.                                                                                                                                                                                            |
| [`SemanticCheck`](#an.genres.SemanticCheck)(name, run[, stage, order, ...])       | One semantic-validation check: `run(ctx)` adds findings to `ctx.report`.                                                                                                                                                                                     |

### Exceptions

| [`GenreAPILevelError`](#an.genres.GenreAPILevelError)                           | A genre package needs a newer `an` than the one installed.             |
|-----------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`ServiceMissingError`](#an.genres.ServiceMissingError)                          | The core asked a genre for a service nobody registered.                |
| [`GenreError`](#an.genres.GenreError)                                   | A genre declaration is malformed, or its entry point does not resolve. |
| [`RegistryError`](#an.genres.RegistryError)                                | A registration is malformed or collides with one already made.         |
| [`UnregisteredKindError`](#an.genres.UnregisteredKindError)(what, name, \*[, ...]) | A document names a kind no loaded genre registered.                    |

### an.genres.API_LEVEL *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

every hook, registry
field and moved path a genre package may rely on. Bumped by each change a
genre needs (the P8 seam PRs and each move to `cutan`, an#225), never
decremented. A genre states the lowest level it needs with
[`require_api_level()`](#an.genres.require_api_level), which is how “the genre declares the lowest `an`
it supports” (ADR 0001 decision 8) is said without a version pin: `an`’s
version is assigned by CI at merge, so no PR can name the release it ships in.

A genre package must also run against an `an` older than this constant:
it reads `getattr(an.genres, "API_LEVEL", 0)` before calling
[`require_api_level()`](#an.genres.require_api_level), and raises its own typed error when it is missing.

Levels (one line each; `tests/test_genre_gate.py` holds the list complete):

1 = moved-module shims (`an._shims.moved_to_package`) and this check (an#296, P8 B0a).
2 = the cut-out genre’s move (an#225): `Genre.services`, `ActionKind.lowering`,

> `EntityKind.swap_declaration`, `an.stage.rig`.
* **Type:**
  The level of the genre-facing API this `an` provides

### *class* an.genres.ActionKind(name, model, duration=None, flatten=None, children=None, read_md=None, write_md=None, md_start=True, description='', version='1', lowering=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One kind of action: its model, how it occupies time, how `scene.md` spells it.

- `model` validates a document’s action of this kind. A genre’s model
  subclasses [`an.ir.schema.ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction); the core’s are the
  static members of the schema’s union.
- `duration` is a LEAF’s natural length; a leaf flattens to one
  `FlatAction` on `[t, t + duration]` and advances a `sequence` by it.
- `flatten` replaces that default for kinds that place themselves
  differently (`set` does not advance the cursor) or that hold children
  (`sequence`): `flatten(action, t, ctx) -> new cursor`, where `ctx`
  is [`an.ir.compose.FlattenContext`](an.ir.compose.html.md#an.ir.compose.FlattenContext).
- `children` lists a composite’s child actions, so generic walkers
  (validation) reach every leaf without knowing the kind.
- `read_md` / `write_md` are the `scene.md` `yaml actions` hooks:
  `read_md(item, index=i) -> action` (`start:` already removed when
  `md_start`) and `write_md(action) -> dict` (without `start`).
  A kind with no `read_md` has no `scene.md` form.

#### lowering *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= None*

How the STAGE compiler turns an action of this kind into clips, for a kind
that is not a plain tween or set (the cut-out `play`): an object with
`extent_resolver(vocab)`, `expand(flat_list, *, vocab, fps, step_hz,
default_easing, resolutions)`, `view_of(entity_swaps, vocab, *, duration)`
and `clip(action, *, anim_id, vocab, fps, view)` – see
[`an.stage.compile.ActionLowering`](an.stage.compile.html.md#an.stage.compile.ActionLowering). `None`: the compiler has
nothing kind-specific to do. (an#225: this is how the compiler stops
naming `play`.)

#### md_start *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Does `start:` in `scene.md` wrap this kind in `sequence(delay(start), …)`?

#### version *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '1'*

bump when what an action of
this kind compiles to changes for the same fields, so the shots that use
it re-render visibly ([`an.semantic`](an.semantic.html.md#module-an.semantic) folds it into the shot digest).

* **Type:**
  The kind’s vocabulary version (ADR 0003)

### *class* an.genres.CompilePass(name, run, order=0.0, compiler='stage', builds=None, description='', replace=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One step a genre adds to an engine’s COMPILER (shot -> compiled document).

A compiler (`compiler`: today `"stage"`, [`an.stage.compile`](an.stage.compile.html.md#module-an.stage.compile)) runs
its own passes plus every registered one, in `order`. A pass with
`builds` set is an ENTITY BUILDER instead: the compiler’s scene pass calls
it for each entity of that kind (the cut-out genre’s `rig` builds a
`character`); builders with a lower `order` build all their entities
first (the stage’s backdrop before the cast), equal orders in entity order.

`run` is the callable, or `"module:function"`, resolved on first use –
so a genre is inspectable ([`an.genres.available()`](#an.genres.available)) without importing
the engine its passes target. What `run` receives is the compiler’s
business (the stage hands a pass its `CompileState`, a builder the entity
and the scene being built); the core never calls it.

#### replace *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

Explicitly take the place of the ENGINE’s own pass of this name (or its
builder for `builds`). Without it a name or kind the engine already
has is refused when the compiler runs; with it the replacement is
recorded in the compiled document (review of an#270, S3).

#### resolve()

The callable `run` names.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> CompilePass("p", "math:sqrt").resolve()(4.0)
2.0
```

### *class* an.genres.DialogueSugar(name, opener, field, parse, format, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`scene.md` sugar on a dialogue line: one bracket pair, one `Dialogue` field.

`parse(content) -> value` turns what is between the brackets into the
field’s value (raise `ValueError(why)` to refuse it); `format(line) ->
str | None` is the inverse (the content, without brackets, or `None` when
the line carries none). The cut-out genre’s `[emotion]` is one.

### an.genres.ENTRY_POINT_GROUP *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an.genres'*

The entry-point group a genre package declares its [`Genre`](#an.genres.Genre) under.

### *class* an.genres.EntityKind(name, space=None, store=None, description='', version='1', swap_declaration=None, descriptor_kind=None, placeholder_on_missing=False, swap_checks=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One kind of entity (`AssetRef.kind`): what its nodes’ properties are.

`space` names the registered [`an.timing.spaces.PropertySpace`](an.timing.spaces.html.md#an.timing.spaces.PropertySpace) its
nodes’ properties live in (`None`: the entity has no animatable nodes, as
a voice); `store` is the project-mall store its `ref` keys into.

#### descriptor_kind *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The `kind` tag of the descriptor document `store` holds for this kind
(`"CharacterDescriptor"`): what makes the validator treat the entity as a
rig whose declared asset sets it can check (an#246).

#### placeholder_on_missing *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

A missing `ref` is NOT an error because the compiler draws a placeholder
instead; the genre reports it with its own (warning) check.

#### swap_checks *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= None*

an object with
`missing_set_hint(prop) -> str` (appended to “names no declared asset
set”) and `whole_entity(action, desc, prop, keys, entity_id, *, where,
report, art_exists) -> bool` (judge a swap on the entity ITSELF; `True`
when handled). `None`: the generic per-node rule only.

* **Type:**
  Extra swap-reference checks for this kind

#### swap_declaration *: [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[Any](https://docs.python.org/3/library/typing.html#typing.Any), [Any](https://docs.python.org/3/library/typing.html#typing.Any)], [SwapDeclaration](an.genres.registry.html.md#an.genres.registry.SwapDeclaration) | [None](https://docs.python.org/3/builtins/constants.html#None)] | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

what the entity’s descriptor
declares for the stage compiler’s swap vocabulary (an#87). `None`: the
kind declares nothing (its built nodes’ sets ARE its declaration).

* **Type:**
  `(entity, mall) -> SwapDeclaration | None`

#### version *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '1'*

The kind’s vocabulary version (ADR 0003), as [`ActionKind.version`](#an.genres.ActionKind.version).

### *class* an.genres.Genre(name, title='', description='', package='', library='', action_kinds=(), entity_kinds=(), spaces=(), field_kinds=(), checks=(), dialogue_sugar=(), capabilities=(), analysers=(), vocabulary=(), aspects=(), compile_passes=(), runtime_scripts=(), services=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A genre: one plain, declarative object listing what it registers.

`name` is the genre’s persisted slug (`cutout_animation`); it is also
the owner of every entry it registers. `package` names the distribution
that ships it, for error messages. Every collection defaults to empty, so a
later phase adds a field (compile passes, vocabulary, capabilities) without
touching any genre that does not use it.

`spaces` are [`an.timing.spaces.PropertySpace`](an.timing.spaces.html.md#an.timing.spaces.PropertySpace) objects and
`field_kinds` are `(name, factory)` pairs for
[`an.timing.kinds.register_kind()`](an.timing.kinds.html.md#an.timing.kinds.register_kind). `capabilities` are
[`an.capabilities.Capability`](an.capabilities.html.md#an.capabilities.Capability) objects, `analysers`
[`an.capabilities.Analyser`](an.capabilities.html.md#an.capabilities.Analyser) objects, `vocabulary`
[`an.semantic.Entry`](an.semantic.html.md#an.semantic.Entry) objects (methods included) and `aspects`
[`an.semantic.Aspect`](an.semantic.html.md#an.semantic.Aspect) objects; registering the genre checks the whole
([`an.semantic.check_registry()`](an.semantic.html.md#an.semantic.check_registry)): every aspect’s chain ends in a method
that requires nothing, and every requirement names a registered capability.

`library` names the package whose data root holds the genre’s asset
library and its projects (`~/.local/share/<library>`, ADR 0005, plan §1
decision 7); empty means the core’s (`an`). It is not `package`: the
distribution that ships a genre and the root its data lives under can
differ (the cut-out genre ships inside `an` today, while its library is
already `cutan`’s). The core never names a genre’s library itself —
a project made in a genre asks the genre ([`genre_library()`](#an.genres.genre_library)).

#### compile_passes *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[CompilePass](an.genres.registry.html.md#an.genres.registry.CompilePass), ...]* *= ()*

Steps the genre adds to an engine’s compiler, and builders for its
entity kinds ([`CompilePass`](#an.genres.CompilePass); an#247).

#### provides()

What this genre registers, by registry, as names — without registering it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]]

```pycon
>>> Genre("g", action_kinds=()).provides()["action kinds"]
()
```

#### runtime_scripts *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[RuntimeScript](an.genres.registry.html.md#an.genres.registry.RuntimeScript), ...]* *= ()*

its visual kinds
([`RuntimeScript`](#an.genres.RuntimeScript); an#247).

* **Type:**
  Code the genre adds to an engine’s runtime

#### services *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [object](https://docs.python.org/3/builtins/functions.html#object)]*

`{name: object or "module:attr"}` the genre offers the core by name
([`register_service()`](#an.genres.register_service); an#225): the CLI namespaces it adds
(`cli.<namespace>`), its lip-sync providers (`lipsync.<name>`), and the
other places the core asks “is there a genre that does this?”.

### *exception* an.genres.GenreAPILevelError

Bases: [`GenreError`](#an.genres.GenreError), [`ImportError`](https://docs.python.org/3/builtins/exceptions.html#ImportError)

A genre package needs a newer `an` than the one installed.

### *exception* an.genres.GenreError

Bases: [`RegistryError`](an.genres.registry.html.md#an.genres.registry.RegistryError)

A genre declaration is malformed, or its entry point does not resolve.

### an.genres.IN_DISTRIBUTION_GENRES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)], ...]* *= ()*

Genres the `an` distribution itself ships, as entry-point values. They are
found by [`load()`](#an.genres.load) WITHOUT relying on installed metadata: an editable
install made before the `an.genres` group existed never refreshes its
`dist-info`, and a missing entry point must never silently drop a genre
that ships in the same distribution as the core (review-244 S1). Still
explicit discovery (only [`load()`](#an.genres.load) reads it, never an import). Every genre is
external now: the cut-out genre moved to `cutan` (an#225) and comes through
the `an.genres` entry point alone.

### *exception* an.genres.RegistryError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A registration is malformed or collides with one already made.

### *class* an.genres.RuntimeScript(name, source, engine='stage', description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

JavaScript a genre adds to an engine’s RUNTIME (an#247; ADR 0001 decision 4,
second batch): for the stage, code that registers visual kinds with
`window.anRegisterVisual(kind, make)` – how the cut-out mouth and eye
leave `runtime.js` for `cutan` (P8).

`source` is `"package:relative/path.js"`, read with
[`importlib.resources`](https://docs.python.org/3/library/importlib.resources.html#module-importlib.resources) when the engine stages its runtime, so it ships
in the genre’s wheel. The staged code is part of the shot cache’s key.

#### code()

The script’s code (UTF-8).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> RuntimeScript("x", "an.stage.runtime:extensions.js").code().startswith("//")
True
```

### *class* an.genres.SemanticCheck(name, run, stage='shot', order=0.0, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One semantic-validation check: `run(ctx)` adds findings to `ctx.report`.

`ctx` is [`an.ir.validate.ValidationContext`](an.ir.validate.html.md#an.ir.validate.ValidationContext); a `shot` check is
called once per shot with `ctx.shot` set. Within a stage, checks run by
`order` (then registration order), so a genre’s check lands exactly where
it belongs in the report.

### *exception* an.genres.ServiceMissingError

Bases: [`RegistryError`](an.genres.registry.html.md#an.genres.registry.RegistryError), [`ImportError`](https://docs.python.org/3/builtins/exceptions.html#ImportError)

The core asked a genre for a service nobody registered.

### *class* an.genres.SwapDeclaration(sets, descriptor=None, art_exists=None, scale=1.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one entity’s descriptor declares for the stage compiler’s swap vocabulary.

`sets` is `{set name: {KEY: attachment name}}` as declared;
`descriptor` is the (migrated) document the declaration came from, kept
for the kind’s own lowering; `art_exists` answers `rel_path -> art on
disk` (`None` when the store cannot say); `scale` is the factor from the
entity’s view box to scene pixels.

### *exception* an.genres.UnregisteredKindError(what, name, , known=(), providers=(), where='')

Bases: [`RegistryError`](an.genres.registry.html.md#an.genres.registry.RegistryError)

A document names a kind no loaded genre registered.

The message names the installed genres that *could* provide it (read from
their declarations, which are inspectable without loading them), so the fix
is one line: `an.genres.load()`, or installing the package named.

### an.genres.action_kind(name)

The registered kind called `name`, or `None`.

* **Return type:**
  [`ActionKind`](an.genres.registry.html.md#an.genres.registry.ActionKind) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

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

The in-distribution genres (`builtin`; none since the cut-out genre moved to
`cutan`, an#225) merged with `entry_points` (default: the installed ones),
de-duplicated by name — the in-distribution declaration first.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`EntryPoint`](https://docs.python.org/3/library/importlib.metadata.html#importlib.metadata.EntryPoint), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> [ep.name for ep in discovered_entry_points(entry_points=())]
[]
```

### an.genres.entity_space_resolver(entities, , default=None)

`target -> PropertySpace`: the space its ENTITY’s kind declares.

The ONE policy for “what are this target’s properties” (review-244 S7):
`an validate`’s generic target check and the compiler’s keyframe check
both use it. A target’s entity is its first path segment; a target with no
entity (the stage camera’s `root`), or an entity whose kind is
unregistered or declares no space, gets `default` — the timing default
[`an.timing.spaces.DFLT_TIMELINE_SPACE`](an.timing.spaces.html.md#an.timing.spaces.DFLT_TIMELINE_SPACE) when `None`.

The default EVALUATOR agrees since an#245: the stage’s compiled document
records each entity whose kind declares another space
(`meta.entity_spaces`), and `timeline_from_compiled` resolves by it.

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

### an.genres.hook_modules(, exclude_owner='an')

The modules whose code the genres’ registered hooks run, sorted and unique.

Compile passes, lowerings, entity hooks, checks, services and runtime scripts
of every owner but `exclude_owner` (the core’s own are walked from the
renderer already). The shot cache’s code key starts its walk here for the
packages outside `an`, so a change to a genre’s code changes the key
(an#294): the genre is reached by REGISTRATION, not by an import from `an`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> isinstance(hook_modules(), tuple)
True
```

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

### an.genres.register_genre(genre, , replace=False, check_capabilities=True)

Register everything `genre` declares, owned by `genre.name`.

Idempotent for the same object: registering a genre that is already
installed is a no-op, so [`load()`](#an.genres.load) can be called from every entry point.
A different object under an installed name raises unless `replace`.
All or nothing: a registration that fails part-way leaves no trace.
`check_capabilities=False` defers the “every requirement names a
registered capability” check to the caller ([`load()`](#an.genres.load) runs it once all
genres are in, so a genre extending another loads in any order).

* **Return type:**
  [`Genre`](#an.genres.Genre)

### an.genres.register_service(name, target, , owner='an', replace=False)

Register a named service a genre offers the core (an#225).

The seam for the places where the core needs a genre’s code only when that
genre is installed: a CLI namespace (`cli.character`), a provider factory
(`lipsync.offline`), a licence lookup. `target` is the object itself or
`"module:attr"` (imported on first use, so declaring a service imports no
engine). The names a genre may use are the core’s contract, listed with
their callers in `misc/docs/architecture_as_built.md`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.genres.require_api_level(level, , package)

Refuse, with an upgrade hint, when this `an` is older than `package` needs.

A genre package calls it at import (`require_api_level(3, package="cutan")`).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> require_api_level(1, package="demo")
>>> try:
...     require_api_level(API_LEVEL + 1, package="demo")
... except GenreAPILevelError as e:
...     print(str(e).startswith(f"demo needs an.genres API level {API_LEVEL + 1}"))
True
```

### an.genres.require_service(name, , what='', extra='cutout')

The registered service `name`; a typed error naming the install when absent.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.genres.service(name, default=None)

The registered service `name`, resolved, or `default` when none is.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> service("no.such.service") is None
True
```

### an.genres.services(prefix)

`{name without the prefix: resolved service}` for every service under `prefix`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> services("no.such.")
{}
```

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

| [`registry`](an.genres.registry.html.md#module-an.genres.registry)   | The core's open registries: action kinds, entity kinds, semantic checks, md sugar, compile passes.   |
|---------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
