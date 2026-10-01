# an.semantic.registry

The one vocabulary registry (ADR 0003 decision 6): entries and aspects, by owner.

Two kinds of source feed it:

- **registered entries** ([`register_entry()`](#an.semantic.registry.register_entry), [`register_aspect()`](#an.semantic.registry.register_aspect)):
  methods, motion and expression presets, camera moves, IR fields — each with
  an owner (the core, or a genre, through [`an.genres.Genre`](an.genres.md#an.genres.Genre)’s
  `vocabulary` and `aspects` fields, so a genre’s entries come out with it);
- **views** ([`register_view()`](#an.semantic.registry.register_view)): entries derived on every read from a
  registry that already exists — the action and entity kinds of
  [`an.genres.registry`](an.genres.registry.md#module-an.genres.registry), the easings of [`an.timing.easing`](an.timing.easing.md#module-an.timing.easing) — so a kind
  > or an easing is defined once, where it lives, and never copied here (design
  > principle 3).

Like [`an.genres.registry`](an.genres.registry.md#module-an.genres.registry) this module imports nothing from `an.ir`: a
view imports its source lazily, when it is read.

```pycon
>>> from an.semantic.entries import Entry
>>> e = register_entry(Entry("demo.wiggle", "motion_preset", name="wiggle"), owner="demo")
>>> lookup("motion_preset", "wiggle") is e, entry("demo.wiggle") is e
(True, True)
>>> drop_owner("demo"); lookup("motion_preset", "wiggle") is None
True
```

### Functions

| [`duplicates`](#an.semantic.registry.duplicates)()                             | Spellings defined twice (a view and a registered entry disagreeing on an id count once: the registered one shadows).       |
|-------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| [`aspect`](#an.semantic.registry.aspect)(name)                             | The registered aspect `name`; [`UnknownEntryError`](#an.semantic.registry.UnknownEntryError) otherwise.                |
| `aspect_names`(\*[, owner])                                                               |                                                                                                                            |
| `aspects`()                                                                               |                                                                                                                            |
| [`drop_owner`](#an.semantic.registry.drop_owner)(owner)                        | Remove every entry and aspect `owner` registered.                                                                          |
| [`entries`](#an.semantic.registry.entries)(\*[, kind, owner])               | Every entry (registered and viewed), filtered by `kind`/`owner`, in a stable order.                                        |
| [`entry`](#an.semantic.registry.entry)(entry_id)                          | The entry with this id; [`UnknownEntryError`](#an.semantic.registry.UnknownEntryError) naming the known ids otherwise. |
| [`lookup`](#an.semantic.registry.lookup)(kind, name, \*[, aspect])         | The entry of `kind` a document spells `name` (for methods, within `aspect`).                                               |
| [`methods_of`](#an.semantic.registry.methods_of)(aspect_name)                  | Every registered method of an aspect: its chain first, in order, then the rest.                                            |
| `owner_of`(entry_id)                                                                      |                                                                                                                            |
| [`register_aspect`](#an.semantic.registry.register_aspect)(a, \*[, owner, replace]) | Register an aspect and its default chain.                                                                                  |
| [`register_entry`](#an.semantic.registry.register_entry)(e, \*[, owner, replace])  | Register a vocabulary entry under `owner`: ONE entry per id, and per spelling.                                             |
| [`register_view`](#an.semantic.registry.register_view)(name, view)                | Register a read-time view (core only: the kinds and easing registries).                                                    |
| [`replacements`](#an.semantic.registry.replacements)()                           | Every deliberate replacement: `{id: (previous owner, new owner, previous version)}`.                                       |
| `restore`(state)                                                                          |                                                                                                                            |
| [`snapshot`](#an.semantic.registry.snapshot)()                               | The state of the registered tables (views are code, not state).                                                            |

### Exceptions

| [`UnknownEntryError`](#an.semantic.registry.UnknownEntryError)   | A name or id is not in the vocabulary; the message lists what is.   |
|----------------------------------------------------------------------|---------------------------------------------------------------------|

### *exception* an.semantic.registry.UnknownEntryError

Bases: [`VocabularyError`](an.semantic.md#an.semantic.VocabularyError), [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

A name or id is not in the vocabulary; the message lists what is.

### an.semantic.registry.aspect(name)

The registered aspect `name`; [`UnknownEntryError`](#an.semantic.registry.UnknownEntryError) otherwise.

* **Return type:**
  [`Aspect`](an.semantic.md#an.semantic.Aspect)

### an.semantic.registry.drop_owner(owner)

Remove every entry and aspect `owner` registered.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.semantic.registry.duplicates()

Spellings defined twice (a view and a registered entry disagreeing on an id
count once: the registered one shadows). Empty when one name is one thing.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.semantic.registry.entries(, kind=None, owner=None)

Every entry (registered and viewed), filtered by `kind`/`owner`, in a stable order.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Entry`](an.semantic.md#an.semantic.Entry), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.semantic.registry.entry(entry_id)

The entry with this id; [`UnknownEntryError`](#an.semantic.registry.UnknownEntryError) naming the known ids otherwise.

* **Return type:**
  [`Entry`](an.semantic.md#an.semantic.Entry)

### an.semantic.registry.lookup(kind, name, , aspect=None)

The entry of `kind` a document spells `name` (for methods, within `aspect`).

* **Return type:**
  [`Entry`](an.semantic.md#an.semantic.Entry) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.semantic.registry.methods_of(aspect_name)

Every registered method of an aspect: its chain first, in order, then the rest.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Method`](an.semantic.md#an.semantic.Method), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.semantic.registry.register_aspect(a, , owner='an', replace=False)

Register an aspect and its default chain. Checked as a whole by
[`an.semantic.check_registry()`](an.semantic.md#an.semantic.check_registry) (a chain may name methods registered
after it, within the same genre).

* **Return type:**
  [`Aspect`](an.semantic.md#an.semantic.Aspect)

### an.semantic.registry.register_entry(e, , owner='an', replace=False)

Register a vocabulary entry under `owner`: ONE entry per id, and per spelling.

A name means one thing everywhere (`push_in` is one entry, an#257): a
second entry under a taken id — registered or provided by a view — or under
a taken `(kind, name)` (within an aspect, for methods) raises, unless
`replace=True` is passed explicitly, and then the replacement is recorded
([`replacements()`](#an.semantic.registry.replacements)). Re-registering the same entry is a no-op.

* **Return type:**
  [`Entry`](an.semantic.md#an.semantic.Entry)

```pycon
>>> from an.semantic.entries import Entry
>>> register_entry(Entry("demo.push_in", "camera_move", name="push_in"), owner="demo")
Traceback (most recent call last):
...
an.semantic.entries.VocabularyError: camera_move 'push_in' is already defined by 'camera.push_in' (owner 'an'); ...
```

### an.semantic.registry.register_view(name, view)

Register a read-time view (core only: the kinds and easing registries).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.semantic.registry.replacements()

Every deliberate replacement: `{id: (previous owner, new owner, previous version)}`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.semantic.registry.snapshot()

The state of the registered tables (views are code, not state).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)
