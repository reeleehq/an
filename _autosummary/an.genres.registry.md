# an.genres.registry

The core’s open registries: action kinds, entity kinds, semantic checks, md sugar.

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

| [`action_kind`](#an.genres.registry.action_kind)(name)                                | The registered kind called `name`, or `None`.                                     |
|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`action_kind_names`](#an.genres.registry.action_kind_names)(\*[, owner])                   | Registered action-kind names in registration order; `owner`'s only when given.    |
| `action_kind_owner`(name)                                                                         |                                                                                   |
| `check_names`(\*[, owner])                                                                        |                                                                                   |
| [`checks`](#an.genres.registry.checks)(stage)                                    | The registered checks of `stage`, in run order (`order`, then registration).      |
| [`dialogue_sugar`](#an.genres.registry.dialogue_sugar)(opener)                           | The sugar registered for the bracket `opener`, or `None`.                         |
| `dialogue_sugars`()                                                                               |                                                                                   |
| `entity_kind`(name)                                                                               |                                                                                   |
| `entity_kind_names`(\*[, owner])                                                                  |                                                                                   |
| [`owners`](#an.genres.registry.owners)()                                         | Every owner with at least one entry, the core first.                              |
| [`register_action_kind`](#an.genres.registry.register_action_kind)(kind, \*[, owner, replace]) | Register an action kind.                                                          |
| [`register_check`](#an.genres.registry.register_check)(check, \*[, owner, replace])      | Register a semantic-validation check (run by `an.ir.validate.validate_semantic`). |
| [`register_dialogue_sugar`](#an.genres.registry.register_dialogue_sugar)(sugar, \*[, owner, ...]) | Register `scene.md` dialogue sugar.                                               |
| [`register_entity_kind`](#an.genres.registry.register_entity_kind)(kind, \*[, owner, replace]) | Register an entity kind (a value `AssetRef.kind` may take).                       |
| `restore`(state)                                                                                  |                                                                                   |
| [`snapshot`](#an.genres.registry.snapshot)()                                       | The state of every table, for `restore()`.                                        |
| [`unregister_owner`](#an.genres.registry.unregister_owner)(owner)                          | Remove every entry `owner` registered, from every table.                          |

### Classes

| [`ActionKind`](#an.genres.registry.ActionKind)(name, model[, duration, flatten, ...])   | One kind of action: its model, how it occupies time, how `scene.md` spells it.   |
|------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`DialogueSugar`](#an.genres.registry.DialogueSugar)(name, opener, field, parse, format)   | `scene.md` sugar on a dialogue line: one bracket pair, one `Dialogue` field.     |
| [`EntityKind`](#an.genres.registry.EntityKind)(name[, space, store, description])       | One kind of entity (`AssetRef.kind`): what its nodes' properties are.            |
| [`SemanticCheck`](#an.genres.registry.SemanticCheck)(name, run[, stage, order, ...])       | One semantic-validation check: `run(ctx)` adds findings to `ctx.report`.         |

### Exceptions

| [`RegistryError`](#an.genres.registry.RegistryError)                                | A registration is malformed or collides with one already made.   |
|-----------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| [`UnregisteredKindError`](#an.genres.registry.UnregisteredKindError)(what, name, \*[, ...]) | A document names a kind no loaded genre registered.              |

### *class* an.genres.registry.ActionKind(name, model, duration=None, flatten=None, children=None, read_md=None, write_md=None, md_start=True, description='')

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

### an.genres.registry.CORE_OWNER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an'*

The owner of every entry the core registers itself. A genre registers under
its own name (`an.genres.Genre.name`).

### an.genres.registry.CheckStage

once before the shots, once per shot, once after them.

* **Type:**
  When a check runs

alias of [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[‘scene’, ‘shot’, ‘finish’]

### an.genres.registry.DIALOGUE_BRACKETS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'[': ']'}*

The bracket pairs a GENRE may claim on a `scene.md` dialogue line. The
line grammar has three: `(…)` (timing) and `{…}` (delivery direction)
are the core’s own and never registered; `[…]` is the one left for sugar.

### *class* an.genres.registry.DialogueSugar(name, opener, field, parse, format, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`scene.md` sugar on a dialogue line: one bracket pair, one `Dialogue` field.

`parse(content) -> value` turns what is between the brackets into the
field’s value (raise `ValueError(why)` to refuse it); `format(line) ->
str | None` is the inverse (the content, without brackets, or `None` when
the line carries none). The cut-out genre’s `[emotion]` is one.

### an.genres.registry.DurationHook

the natural length of a leaf. `extent` is
the caller’s per-call resolver for a leaf that has no explicit duration (the
compiler and `an validate` pass one bound to the entity’s descriptor), or
`None`.

* **Type:**
  `(action, extent) -> seconds`

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### *class* an.genres.registry.EntityKind(name, space=None, store=None, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One kind of entity (`AssetRef.kind`): what its nodes’ properties are.

`space` names the registered [`an.timing.spaces.PropertySpace`](an.timing.spaces.md#an.timing.spaces.PropertySpace) its
nodes’ properties live in (`None`: the entity has no animatable nodes, as
a voice); `store` is the project-mall store its `ref` keys into.

### *exception* an.genres.registry.RegistryError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A registration is malformed or collides with one already made.

### *class* an.genres.registry.SemanticCheck(name, run, stage='shot', order=0.0, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One semantic-validation check: `run(ctx)` adds findings to `ctx.report`.

`ctx` is [`an.ir.validate.ValidationContext`](an.ir.validate.md#an.ir.validate.ValidationContext); a `shot` check is
called once per shot with `ctx.shot` set. Within a stage, checks run by
`order` (then registration order), so a genre’s check lands exactly where
it belongs in the report.

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

### an.genres.registry.dialogue_sugar(opener)

The sugar registered for the bracket `opener`, or `None`.

* **Return type:**
  [`DialogueSugar`](#an.genres.registry.DialogueSugar) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

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

### an.genres.registry.register_dialogue_sugar(sugar, , owner='an', replace=False)

Register `scene.md` dialogue sugar. One sugar per bracket pair.

* **Return type:**
  [`DialogueSugar`](#an.genres.registry.DialogueSugar)

### an.genres.registry.register_entity_kind(kind, , owner='an', replace=False)

Register an entity kind (a value `AssetRef.kind` may take).

* **Return type:**
  [`EntityKind`](#an.genres.registry.EntityKind)

### an.genres.registry.snapshot()

The state of every table, for `restore()`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)

### an.genres.registry.unregister_owner(owner)

Remove every entry `owner` registered, from every table.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
