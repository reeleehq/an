# an.genres.registry

The core’s open registries: action kinds, entity kinds, semantic checks, md sugar, compile passes.

ADR 0001 decision 2 (“the IR is open at the type level; genres register, never
edit”) and decision 4 (the first batch of registries). Each registry is a plain
name-keyed table with an **owner** per entry, so the core can tell its own
entries from a genre’s (the timing contract does the same, review-237 S3), and a
test can take every genre out and put it back ([`snapshot()`](#an.genres.registry.snapshot) /
`restore()`).

This module imports nothing from `an.ir`: the schema consults it while it
validates (a document’s `kind: play` is looked up here), so it must sit below
the schema in the import graph. That is also why an entry holds its model class
and hooks as plain values: the registry never needs to know what they are.

```pycon
>>> isinstance(action_kind("tween"), ActionKind)  # core kinds register on import of the IR
True
>>> "play" in action_kind_names(owner=CORE_OWNER)  # a genre's kind is never the core's
False
```

### Module Attributes

| [`CORE_OWNER`](#an.genres.registry.CORE_OWNER)        | The owner of every entry the core registers itself.                |
|--------------------------------------------------------------------|--------------------------------------------------------------------|
| [`DurationHook`](#an.genres.registry.DurationHook)      | the natural length of a leaf.                                      |
| [`CheckStage`](#an.genres.registry.CheckStage)        | once before the shots, once per shot, once after them.             |
| [`DIALOGUE_BRACKETS`](#an.genres.registry.DIALOGUE_BRACKETS) | The bracket pairs a GENRE may claim on a `scene.md` dialogue line. |

### Functions

| [`action_kind`](#an.genres.registry.action_kind)(name)                                 | The registered kind called `name`, or `None`.                                     |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`action_kind_names`](#an.genres.registry.action_kind_names)(\*[, owner])                    | Registered action-kind names in registration order; `owner`'s only when given.    |
| `action_kind_owner`(name)                                                                          |                                                                                   |
| `check_names`(\*[, owner])                                                                         |                                                                                   |
| [`checks`](#an.genres.registry.checks)(stage)                                     | The registered checks of `stage`, in run order (`order`, then registration).      |
| `compile_pass_names`(\*[, owner])                                                                  |                                                                                   |
| [`compile_pass_owner`](#an.genres.registry.compile_pass_owner)(name)                          | Who registered the compile pass `name` (a genre's name), or `None`.               |
| [`compile_passes`](#an.genres.registry.compile_passes)(compiler)                          | The registered passes of `compiler` (builders excluded), in run order.            |
| [`dialogue_sugar`](#an.genres.registry.dialogue_sugar)(opener)                            | The sugar registered for the bracket `opener`, or `None`.                         |
| `dialogue_sugars`()                                                                                |                                                                                   |
| [`entity_builders`](#an.genres.registry.entity_builders)(compiler)                         | `{entity kind: builder}` registered for `compiler`.                               |
| `entity_kind`(name)                                                                                |                                                                                   |
| `entity_kind_names`(\*[, owner])                                                                   |                                                                                   |
| [`hook_modules`](#an.genres.registry.hook_modules)(\*[, exclude_owner])                 | The modules whose code the genres' registered hooks run, sorted and unique.       |
| [`owners`](#an.genres.registry.owners)()                                          | Every owner with at least one entry, the core first.                              |
| [`register_action_kind`](#an.genres.registry.register_action_kind)(kind, \*[, owner, replace])  | Register an action kind.                                                          |
| [`register_check`](#an.genres.registry.register_check)(check, \*[, owner, replace])       | Register a semantic-validation check (run by `an.ir.validate.validate_semantic`). |
| [`register_compile_pass`](#an.genres.registry.register_compile_pass)(compile_pass, \*[, ...])    | Register a compile pass (or an entity builder) under its name.                    |
| [`register_dialogue_sugar`](#an.genres.registry.register_dialogue_sugar)(sugar, \*[, owner, ...])  | Register `scene.md` dialogue sugar.                                               |
| [`register_entity_kind`](#an.genres.registry.register_entity_kind)(kind, \*[, owner, replace])  | Register an entity kind (a value `AssetRef.kind` may take).                       |
| [`register_runtime_script`](#an.genres.registry.register_runtime_script)(script, \*[, owner, ...]) | Register runtime code for an engine (a genre's visual kinds).                     |
| [`register_service`](#an.genres.registry.register_service)(name, target, \*[, owner, ...])  | Register a named service a genre offers the core (an#225).                        |
| [`require_service`](#an.genres.registry.require_service)(name, \*[, what, extra])          | The registered service `name`; a typed error naming the install when absent.      |
| `restore`(state)                                                                                   |                                                                                   |
| [`runtime_scripts`](#an.genres.registry.runtime_scripts)(engine)                           | The scripts registered for `engine`, by name (a stable order).                    |
| [`service`](#an.genres.registry.service)(name[, default])                          | The registered service `name`, resolved, or `default` when none is.               |
| [`services`](#an.genres.registry.services)(prefix)                                  | `{name without the prefix: resolved service}` for every service under `prefix`.   |
| [`snapshot`](#an.genres.registry.snapshot)()                                        | The state of every table, for `restore()`.                                        |
| [`unregister_owner`](#an.genres.registry.unregister_owner)(owner)                           | Remove every entry `owner` registered, from every table.                          |

### Classes

| [`ActionKind`](#an.genres.registry.ActionKind)(name, model[, duration, flatten, ...])   | One kind of action: its model, how it occupies time, how `scene.md` spells it.                                                                                                                                                                               |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`CompilePass`](#an.genres.registry.CompilePass)(name, run[, order, compiler, ...])      | One step a genre adds to an engine's COMPILER (shot -> compiled document).                                                                                                                                                                                   |
| [`DialogueSugar`](#an.genres.registry.DialogueSugar)(name, opener, field, parse, format)   | `scene.md` sugar on a dialogue line: one bracket pair, one `Dialogue` field (and, declared in `fields`, the parameters it may carry).                                                                                                                        |
| [`EntityKind`](#an.genres.registry.EntityKind)(name[, space, store, ...])               | One kind of entity (`AssetRef.kind`): what its nodes' properties are.                                                                                                                                                                                        |
| [`RuntimeScript`](#an.genres.registry.RuntimeScript)(name, source[, engine, ...])          | JavaScript a genre adds to an engine's RUNTIME (an#247; ADR 0001 decision 4, second batch): for the stage, code that registers visual kinds with `window.anRegisterVisual(kind, make)` -- how the cut-out mouth and eye leave `runtime.js` for `cutan` (P8). |
| [`SemanticCheck`](#an.genres.registry.SemanticCheck)(name, run[, stage, order, ...])       | One semantic-validation check: `run(ctx)` adds findings to `ctx.report`.                                                                                                                                                                                     |
| [`SwapDeclaration`](#an.genres.registry.SwapDeclaration)(sets[, descriptor, ...])            | What one entity's descriptor declares for the stage compiler's swap vocabulary.                                                                                                                                                                              |

### Exceptions

| [`RegistryError`](#an.genres.registry.RegistryError)                                | A registration is malformed or collides with one already made.   |
|-----------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| [`ServiceMissingError`](#an.genres.registry.ServiceMissingError)                          | The core asked a genre for a service nobody registered.          |
| [`UnregisteredKindError`](#an.genres.registry.UnregisteredKindError)(what, name, \*[, ...]) | A document names a kind no loaded genre registered.              |

### *class* an.genres.registry.ActionKind(name, model, duration=None, flatten=None, children=None, read_md=None, write_md=None, md_start=True, description='', version='1', lowering=None)

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

#### lowering *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= None*

How the STAGE compiler turns an action of this kind into clips, for a kind
that is not a plain tween or set (the cut-out `play`): an object with
`extent_resolver(vocab, *, products)`, `expand(flat_list, *, vocab, fps,
step_hz, default_easing, resolutions, products)`, `view_of(entity_swaps, vocab, *, duration)`
and `clip(action, *, anim_id, vocab, fps, view)` – see
[`an.stage.compile.ActionLowering`](an.stage.compile.md#an.stage.compile.ActionLowering). `None`: the compiler has
nothing kind-specific to do. (an#225: this is how the compiler stops
naming `play`.)

#### md_start *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Does `start:` in `scene.md` wrap this kind in `sequence(delay(start), …)`?

#### version *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '1'*

bump when what an action of
this kind compiles to changes for the same fields, so the shots that use
it re-render visibly ([`an.semantic`](an.semantic.md#module-an.semantic) folds it into the shot digest).

* **Type:**
  The kind’s vocabulary version (ADR 0003)

### an.genres.registry.CORE_OWNER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an'*

The owner of every entry the core registers itself. A genre registers under
its own name (`an.genres.Genre.name`).

### an.genres.registry.CheckStage

once before the shots, once per shot, once after them.

* **Type:**
  When a check runs

alias of [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[‘scene’, ‘shot’, ‘finish’]

### *class* an.genres.registry.CompilePass(name, run, order=0.0, compiler='stage', builds=None, description='', replace=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One step a genre adds to an engine’s COMPILER (shot -> compiled document).

A compiler (`compiler`: today `"stage"`, [`an.stage.compile`](an.stage.compile.md#module-an.stage.compile)) runs
its own passes plus every registered one, in `order`. A pass with
`builds` set is an ENTITY BUILDER instead: the compiler’s scene pass calls
it for each entity of that kind (the cut-out genre’s `rig` builds a
`character`); builders with a lower `order` build all their entities
first (the stage’s backdrop before the cast), equal orders in entity order.

`run` is the callable, or `"module:function"`, resolved on first use –
so a genre is inspectable ([`an.genres.available()`](an.genres.md#an.genres.available)) without importing
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

### an.genres.registry.DIALOGUE_BRACKETS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'[': ']'}*

The bracket pairs a GENRE may claim on a `scene.md` dialogue line. The
line grammar has three: `(…)` (timing) and `{…}` (delivery direction)
are the core’s own and never registered; `[…]` is the one left for sugar.

### *class* an.genres.registry.DialogueSugar(name, opener, field, parse, format, description='', fields=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`scene.md` sugar on a dialogue line: one bracket pair, one `Dialogue` field
(and, declared in `fields`, the parameters it may carry).

`parse(content) -> value` turns what is between the brackets into the
field’s value (raise `ValueError(why)` to refuse it); `format(line) ->
str | None` is the inverse (the content, without brackets, or `None` when
the line carries none). The cut-out genre’s `[emotion]` is one.

A sugar that also sets other `Dialogue` fields (`[angry 0.4]`: the
emotion and its `emotion_intensity`, an#253) names them in `fields`;
its `parse` then returns `{field name: value}` over `field` and any
of `fields`, and `format` writes them back.

#### values(content)

`{Dialogue field: value}` for the bracket `content` (`parse`,
checked against what the sugar declares).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.genres.registry.DurationHook

the natural length of a leaf. `extent` is
the caller’s per-call resolver for a leaf that has no explicit duration (the
compiler and `an validate` pass one bound to the entity’s descriptor), or
`None`.

* **Type:**
  `(action, extent) -> seconds`

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### *class* an.genres.registry.EntityKind(name, space=None, store=None, description='', version='1', swap_declaration=None, descriptor_kind=None, placeholder_on_missing=False, swap_checks=None, specimen=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One kind of entity (`AssetRef.kind`): what its nodes’ properties are.

`space` names the registered [`an.timing.spaces.PropertySpace`](an.timing.spaces.md#an.timing.spaces.PropertySpace) its
nodes’ properties live in (`None`: the entity has no animatable nodes, as
a voice); `store` is the project-mall store its `ref` keys into.

#### descriptor_kind *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The `kind` tag of the descriptor document `store` holds for this kind
(`"CharacterDescriptor"`): what makes the validator treat the entity as a
rig whose declared asset sets it can check (an#246).

#### placeholder_on_missing *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

A missing `ref` is NOT an error because the compiler draws a placeholder
instead; the genre reports it with its own (warning) check.

#### specimen *: [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[Any](https://docs.python.org/3/library/typing.html#typing.Any)], [Any](https://docs.python.org/3/library/typing.html#typing.Any)] | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

a short shot showing one entity of this kind
on its own, the one `ref` casts — what `an library sheet` draws for a
version of it (an#347). `None`: the sheet shows a labelled placeholder.

* **Type:**
  `(ref: AssetRef) -> Shot`

#### swap_checks *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)* *= None*

an object with
`missing_set_hint(prop) -> str` (appended to “names no declared asset
set”) and `whole_entity(action, desc, prop, keys, entity_id, *, where,
report, art_exists) -> bool` (judge a swap on the entity ITSELF; `True`
when handled). `None`: the generic per-node rule only.

* **Type:**
  Extra swap-reference checks for this kind

#### swap_declaration *: [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[Any](https://docs.python.org/3/library/typing.html#typing.Any), [Any](https://docs.python.org/3/library/typing.html#typing.Any)], [SwapDeclaration](#an.genres.registry.SwapDeclaration) | [None](https://docs.python.org/3/builtins/constants.html#None)] | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

what the entity’s descriptor
declares for the stage compiler’s swap vocabulary (an#87). `None`: the
kind declares nothing (its built nodes’ sets ARE its declaration).

* **Type:**
  `(entity, mall) -> SwapDeclaration | None`

#### version *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '1'*

The kind’s vocabulary version (ADR 0003), as [`ActionKind.version`](#an.genres.registry.ActionKind.version).

### *exception* an.genres.registry.RegistryError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A registration is malformed or collides with one already made.

### *class* an.genres.registry.RuntimeScript(name, source, engine='stage', description='')

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

### *class* an.genres.registry.SemanticCheck(name, run, stage='shot', order=0.0, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One semantic-validation check: `run(ctx)` adds findings to `ctx.report`.

`ctx` is [`an.ir.validate.ValidationContext`](an.ir.validate.md#an.ir.validate.ValidationContext); a `shot` check is
called once per shot with `ctx.shot` set. Within a stage, checks run by
`order` (then registration order), so a genre’s check lands exactly where
it belongs in the report.

### *exception* an.genres.registry.ServiceMissingError

Bases: [`RegistryError`](#an.genres.registry.RegistryError), [`ImportError`](https://docs.python.org/3/builtins/exceptions.html#ImportError)

The core asked a genre for a service nobody registered.

### *class* an.genres.registry.SwapDeclaration(sets, descriptor=None, art_exists=None, scale=1.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one entity’s descriptor declares for the stage compiler’s swap vocabulary.

`sets` is `{set name: {KEY: attachment name}}` as declared;
`descriptor` is the (migrated) document the declaration came from, kept
for the kind’s own lowering; `art_exists` answers `rel_path -> art on
disk` (`None` when the store cannot say); `scale` is the factor from the
entity’s view box to scene pixels.

### *exception* an.genres.registry.UnregisteredKindError(what, name, , known=(), providers=(), where='')

Bases: [`RegistryError`](#an.genres.registry.RegistryError)

A document names a kind no loaded genre registered.

The message names the installed genres that *could* provide it (read from
their declarations, which are inspectable without loading them), so the fix
is one line: `an.genres.load()`, or installing the package named.

### an.genres.registry.action_kind(name)

The registered kind called `name`, or `None`.

* **Return type:**
  [`ActionKind`](#an.genres.registry.ActionKind) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.genres.registry.action_kind_names(, owner=None)

Registered action-kind names in registration order; `owner`’s only when given.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.registry.checks(stage)

The registered checks of `stage`, in run order (`order`, then registration).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`SemanticCheck`](#an.genres.registry.SemanticCheck), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.registry.compile_pass_owner(name)

Who registered the compile pass `name` (a genre’s name), or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.genres.registry.compile_passes(compiler)

The registered passes of `compiler` (builders excluded), in run order.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`CompilePass`](#an.genres.registry.CompilePass), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.registry.dialogue_sugar(opener)

The sugar registered for the bracket `opener`, or `None`.

* **Return type:**
  [`DialogueSugar`](#an.genres.registry.DialogueSugar) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.genres.registry.entity_builders(compiler)

`{entity kind: builder}` registered for `compiler`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`CompilePass`](#an.genres.registry.CompilePass)]

### an.genres.registry.hook_modules(, exclude_owner='an')

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

### an.genres.registry.owners()

Every owner with at least one entry, the core first.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.registry.register_action_kind(kind, , owner='an', replace=False)

Register an action kind. Its model’s `kind` must default to its name.

* **Return type:**
  [`ActionKind`](#an.genres.registry.ActionKind)

```pycon
>>> from pydantic import BaseModel
>>> class Bad(BaseModel):
...     kind: str = "other"
>>> register_action_kind(ActionKind("wave", Bad), owner="demo")
Traceback (most recent call last):
...
an.genres.registry.RegistryError: action kind 'wave': ...
```

### an.genres.registry.register_check(check, , owner='an', replace=False)

Register a semantic-validation check (run by `an.ir.validate.validate_semantic`).

* **Return type:**
  [`SemanticCheck`](#an.genres.registry.SemanticCheck)

### an.genres.registry.register_compile_pass(compile_pass, , owner='an', replace=False)

Register a compile pass (or an entity builder) under its name.

* **Return type:**
  [`CompilePass`](#an.genres.registry.CompilePass)

### an.genres.registry.register_dialogue_sugar(sugar, , owner='an', replace=False)

Register `scene.md` dialogue sugar. One sugar per bracket pair.

* **Return type:**
  [`DialogueSugar`](#an.genres.registry.DialogueSugar)

### an.genres.registry.register_entity_kind(kind, , owner='an', replace=False)

Register an entity kind (a value `AssetRef.kind` may take).

* **Return type:**
  [`EntityKind`](#an.genres.registry.EntityKind)

### an.genres.registry.register_runtime_script(script, , owner='an', replace=False)

Register runtime code for an engine (a genre’s visual kinds).

* **Return type:**
  [`RuntimeScript`](#an.genres.registry.RuntimeScript)

### an.genres.registry.register_service(name, target, , owner='an', replace=False)

Register a named service a genre offers the core (an#225).

The seam for the places where the core needs a genre’s code only when that
genre is installed: a CLI namespace (`cli.character`), a provider factory
(`lipsync.offline`), a licence lookup. `target` is the object itself or
`"module:attr"` (imported on first use, so declaring a service imports no
engine). The names a genre may use are the core’s contract, listed with
their callers in `misc/docs/architecture_as_built.md`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.genres.registry.require_service(name, , what='', extra='cutout')

The registered service `name`; a typed error naming the install when absent.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.genres.registry.runtime_scripts(engine)

The scripts registered for `engine`, by name (a stable order).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`RuntimeScript`](#an.genres.registry.RuntimeScript), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.genres.registry.service(name, default=None)

The registered service `name`, resolved, or `default` when none is.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> service("no.such.service") is None
True
```

### an.genres.registry.services(prefix)

`{name without the prefix: resolved service}` for every service under `prefix`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> services("no.such.")
{}
```

### an.genres.registry.snapshot()

The state of every table, for `restore()`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)

### an.genres.registry.unregister_owner(owner)

Remove every entry `owner` registered, from every table.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
