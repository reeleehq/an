# an.semantic

The semantic layer: one versioned vocabulary registry, methods, aspects and the matcher.

ADR 0003 (the structured ↔ semantic spectrum) and ADR 0002 (capability-based
applicability). Defined once, in the core, for every genre (design principle 3):

- **the vocabulary** — every name a document may spell, as an [`Entry`](#an.semantic.Entry)
  (id, version, kind, title, description, params as JSON Schema with
  defaults, examples, requires, accepted levels, expand): action and entity
  kinds, easings, camera moves and IR fields from the core
  ([`an.semantic.seeds`](an.semantic.seeds.md#module-an.semantic.seeds)); motion and expression presets, methods and
  aspects from the genres ([`an.genres.Genre`](an.genres.md#an.genres.Genre)’s `vocabulary` and
  `aspects`);
- **methods and aspects** — a [`Method`](#an.semantic.Method) is an entry of kind `method`
  realising an [`Aspect`](#an.semantic.Aspect), whose default chain ends in a method that
  requires nothing or in the recorded `NOOP`;
- **the queries** — [`applicable()`](#an.semantic.applicable), [`why_not()`](#an.semantic.why_not) and [`resolve()`](#an.semantic.resolve)
  (with a [`Policy`](#an.semantic.Policy)), all calls to the one matcher
  [`an.capabilities.missing()`](an.capabilities.md#an.capabilities.missing);
- **the generated surfaces** — the `an iterate` prompt
  ([`an.semantic.prompt`](an.semantic.prompt.md#module-an.semantic.prompt)), the skill’s vocabulary section
  ([`an.semantic.docs`](an.semantic.docs.md#module-an.semantic.docs)), the MCP surface ([`an.mcp`](an.mcp.md#module-an.mcp)), and the shot’s
  vocabulary digest for the compile key ([`an.semantic.digest`](an.semantic.digest.md#module-an.semantic.digest)).

Nothing here imports `an.ir` at module level, and nothing below the IR ever
calls an LLM.

```pycon
>>> from an.semantic import entry, vocabulary
>>> entry("action.tween").kind
'action'
>>> any(e["id"] == "easing.ease_in_out" for e in vocabulary())
True
```

### Functions

| [`applicable`](#an.semantic.applicable)(aspect_name, subjects)                | The methods of `aspect_name` that apply to `subjects`, the default chain's order first.                                    |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| [`aspect`](#an.semantic.aspect)(name)                                     | The registered aspect `name`; [`UnknownEntryError`](#an.semantic.UnknownEntryError) otherwise.                |
| `aspect_names`(\*[, owner])                                                                       |                                                                                                                            |
| `aspects`()                                                                                       |                                                                                                                            |
| [`check_registry`](#an.semantic.check_registry)(\*[, owner, capabilities])        | The problems with the registered aspects and methods (empty: sound).                                                       |
| [`entries`](#an.semantic.entries)(\*[, kind, owner])                       | Every entry (registered and viewed), filtered by `kind`/`owner`, in a stable order.                                        |
| [`entry`](#an.semantic.entry)(entry_id)                                  | The entry with this id; [`UnknownEntryError`](#an.semantic.UnknownEntryError) naming the known ids otherwise. |
| [`lookup`](#an.semantic.lookup)(kind, name, \*[, aspect])                 | The entry of `kind` a document spells `name` (for methods, within `aspect`).                                               |
| [`methods_of`](#an.semantic.methods_of)(aspect_name)                          | Every registered method of an aspect: its chain first, in order, then the rest.                                            |
| `owner_of`(entry_id)                                                                              |                                                                                                                            |
| [`register_aspect`](#an.semantic.register_aspect)(a, \*[, owner, replace])         | Register an aspect and its default chain.                                                                                  |
| [`register_entry`](#an.semantic.register_entry)(e, \*[, owner, replace])          | Register a vocabulary entry under `owner`: ONE entry per id, and per spelling.                                             |
| [`resolve`](#an.semantic.resolve)(aspect_name, subjects[, requested, ...]) | Choose the method that realises `aspect_name` on `subjects`.                                                               |
| [`vocabulary`](#an.semantic.vocabulary)(\*[, kind, owner])                    | Every entry as data (what the MCP surface returns), filtered by `kind`/`owner`.                                            |
| [`why_not`](#an.semantic.why_not)(method, subjects)                        | What `method` is missing on `subjects`, each with its remedy (empty: it applies).                                          |

### Classes

| [`Aspect`](#an.semantic.Aspect)(name, chain[, applies_to, ...])          | Something every asset of a kind gets (locomotion, speech, blink, …).                                                     |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| [`Choice`](#an.semantic.Choice)(method[, args, version])                 | One method choice in a policy or a request: `previz`'s `FormulaCall` plus a pin.                                         |
| [`Entry`](#an.semantic.Entry)(id, kind[, version, name, title, ...])    | One vocabulary entry: a named, versioned, described, parametrised recipe.                                                |
| [`Method`](#an.semantic.Method)(id[, kind, version, name, title, ...])   | A way of realising an aspect (ADR 0002): an entry of kind `method`.                                                      |
| [`Missing`](#an.semantic.Missing)(term, remedy)                           | One unmet requirement term and what would meet it.                                                                       |
| [`Policy`](#an.semantic.Policy)([order])                                 | Per-aspect method orders set by a style (study_the_masters §4).                                                          |
| [`Resolution`](#an.semantic.Resolution)(aspect, method[, args, source, ...]) | What [`resolve()`](#an.semantic.resolve) chose: the method, its args, where the choice came from. |

### Exceptions

| [`UnknownEntryError`](#an.semantic.UnknownEntryError)   | A name or id is not in the vocabulary; the message lists what is.                    |
|----------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`VocabularyError`](#an.semantic.VocabularyError)     | A vocabulary entry, aspect or policy is malformed or collides with a registered one. |

### *class* an.semantic.Aspect(name, chain, applies_to=frozenset({}), description='', declared_by='', records_fallback=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Something every asset of a kind gets (locomotion, speech, blink, …).

`chain` is the default order of method ids, first applicable wins; its
last link requires nothing, or is `NOOP`. `applies_to` is the
entity kinds it makes sense for (empty: all); for any other kind the
aspect resolves to the recorded no-op.

#### declared_by *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

The asset-document field an asset declares its request in (a
character’s `gait`, `speech`): a declared method choice, reported as
such by `describe_asset` and honoured by the compiler.

#### records_fallback *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

Record falling down the chain even when nothing was requested (reason
`missing`, so `--strict-assets` sees it). For an aspect whose
fallback is a behaviour the asset never had before — speech’s pulse on a
baked face — rather than today’s long-standing default (a legless walk).

### *class* an.semantic.Choice(method, args=<factory>, version=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One method choice in a policy or a request: `previz`’s `FormulaCall` plus a pin.

```pycon
>>> Choice.of({"method": "speech.mouth_flap", "args": {"shapes": 3}}).args
{'shapes': 3}
>>> Choice.of("loco.rock").method
'loco.rock'
```

### *class* an.semantic.Entry(id, kind, version='1', name='', title='', description='', usage='', params=<factory>, examples=(), requires=(), levels=frozenset({'a', 'b-name'}), aspects=(), expand=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One vocabulary entry: a named, versioned, described, parametrised recipe.

- `id` is the persisted identifier (dotted: `motion.walk`,
  `loco.legged_cycle`); `name` is how a document spells it (`walk`;
  defaults to `id`), looked up per `kind`.
- `version` changes whenever the meaning changes for the same params; the
  versions of the entries a shot uses fold into its compile key.
- `params` is a JSON Schema object; `properties.*.default` are the
  defaults (`{}` when the entry takes none).
- `aspects` names the aspects that using this entry resolves (a `walk`
  resolves `locomotion`), so the digest of a shot can include the methods
  it may resolve to.
- `usage` is the longer note the generated surfaces print under the
  one-sentence `description` (how a document spells it, what bites).

#### defaults()

The params’ defaults (`properties.*.default`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

#### *classmethod* from_json(data, , expand=None)

An entry from its JSON form (what [`to_json()`](#an.semantic.Entry.to_json) writes, or another
package exports — previz’s formulas): the explicit loader, a `method`
kind giving a [`Method`](#an.semantic.Method).

* **Return type:**
  [`Entry`](#an.semantic.Entry)

```pycon
>>> e = Entry("camera.demo", "camera_move", name="demo", description="d")
>>> Entry.from_json(e.to_json()) == e
True
```

#### *property* term *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

How a document spells this entry.

#### to_json()

The entry as data (no `expand`): what the MCP surface and the docs list.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *class* an.semantic.Method(id, kind='method', version='1', name='', title='', description='', usage='', params=<factory>, examples=(), requires=(), levels=frozenset({'a', 'b-name'}), aspects=(), expand=None, aspect='', remedies=<factory>)

Bases: [`Entry`](#an.semantic.Entry)

A way of realising an aspect (ADR 0002): an entry of kind `method`.

`remedies` overrides a capability’s own remedy per requirement term (a
method can say “split the legs into two slots with hip pivots” where the
capability only says “add legs”).

```pycon
>>> m = Method("loco.rock", aspect="locomotion", name="rock")
>>> m.kind, m.aspect, m.requirement_free
('method', 'locomotion', True)
```

#### *property* requirement_free *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether the method applies to anything (a legal last link of a chain).

#### to_json()

The entry as data (no `expand`): what the MCP surface and the docs list.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *class* an.semantic.Missing(term, remedy)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One unmet requirement term and what would meet it.

### *class* an.semantic.Policy(order=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Per-aspect method orders set by a style (study_the_masters §4).

The parsed form of a style document’s `policy:` block; precedence when
resolving is the author’s request, then the shot, then the style, then the
aspect’s chain ([`layered()`](#an.semantic.Policy.layered)).

```pycon
>>> p = Policy.of({"locomotion": ["loco.bob", {"method": "loco.glide", "args": {"bob": 0}}]})
>>> [c.method for c in p.choices("locomotion")], p.choices("speech")
(['loco.bob', 'loco.glide'], ())
```

#### *static* layered(\*policies)

Policies in precedence order (shot before style): the first that names an aspect wins it.

* **Return type:**
  [`Policy`](#an.semantic.Policy)

### *class* an.semantic.Resolution(aspect, method, args=<factory>, source='chain', substitution=None, considered=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What [`resolve()`](#an.semantic.resolve) chose: the method, its args, where the choice came from.

`source` is `request`, `policy`, `chain` or `noop`;
`substitution` is the record when the choice departs from what was asked
(`None` when it did not); `considered` is the trail of methods tried
before it, each with what it was missing.

### *exception* an.semantic.UnknownEntryError

Bases: [`VocabularyError`](#an.semantic.VocabularyError), [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

A name or id is not in the vocabulary; the message lists what is.

### *exception* an.semantic.VocabularyError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A vocabulary entry, aspect or policy is malformed or collides with a registered one.

### an.semantic.applicable(aspect_name, subjects)

The methods of `aspect_name` that apply to `subjects`, the default chain’s order first.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Method`](#an.semantic.Method), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.semantic.aspect(name)

The registered aspect `name`; [`UnknownEntryError`](#an.semantic.UnknownEntryError) otherwise.

* **Return type:**
  [`Aspect`](#an.semantic.Aspect)

### an.semantic.check_registry(, owner=None, capabilities=True)

The problems with the registered aspects and methods (empty: sound).

ADR 0002 decision 5 as a check: every aspect’s chain names methods of that
aspect, and its last link requires nothing or is the recorded `NOOP`;
one spelling is one entry; and (`capabilities`) every requirement names a
registered capability. `owner` limits it to one genre’s aspects and
entries. [`an.genres.register_genre()`](an.genres.md#an.genres.register_genre) runs the chain checks per genre;
[`an.genres.load()`](an.genres.md#an.genres.load) runs the capability check once every genre is in, so
a genre needing another’s capability does not depend on load order.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.semantic.entries(, kind=None, owner=None)

Every entry (registered and viewed), filtered by `kind`/`owner`, in a stable order.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Entry`](#an.semantic.Entry), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.semantic.entry(entry_id)

The entry with this id; [`UnknownEntryError`](#an.semantic.UnknownEntryError) naming the known ids otherwise.

* **Return type:**
  [`Entry`](#an.semantic.Entry)

### an.semantic.lookup(kind, name, , aspect=None)

The entry of `kind` a document spells `name` (for methods, within `aspect`).

* **Return type:**
  [`Entry`](#an.semantic.Entry) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.semantic.methods_of(aspect_name)

Every registered method of an aspect: its chain first, in order, then the rest.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Method`](#an.semantic.Method), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.semantic.register_aspect(a, , owner='an', replace=False)

Register an aspect and its default chain. Checked as a whole by
[`an.semantic.check_registry()`](#an.semantic.check_registry) (a chain may name methods registered
after it, within the same genre).

* **Return type:**
  [`Aspect`](#an.semantic.Aspect)

### an.semantic.register_entry(e, , owner='an', replace=False)

Register a vocabulary entry under `owner`: ONE entry per id, and per spelling.

A name means one thing everywhere (`push_in` is one entry, an#257): a
second entry under a taken id — registered or provided by a view — or under
a taken `(kind, name)` (within an aspect, for methods) raises, unless
`replace=True` is passed explicitly, and then the replacement is recorded
(`replacements()`). Re-registering the same entry is a no-op.

* **Return type:**
  [`Entry`](#an.semantic.Entry)

```pycon
>>> from an.semantic.entries import Entry
>>> register_entry(Entry("demo.push_in", "camera_move", name="push_in"), owner="demo")
Traceback (most recent call last):
...
an.semantic.entries.VocabularyError: camera_move 'push_in' is already defined by 'camera.push_in' (owner 'an'); ...
```

### an.semantic.resolve(aspect_name, subjects, requested=None, , policy=None, entity='', entity_kind=None)

Choose the method that realises `aspect_name` on `subjects`.

`requested` is the author’s explicit choice (a method id, its spelling
in the aspect — `"hem"` for locomotion —, or `{method, args, version}`);
`policy` the layered shot/style policy; `entity_kind` the asset’s kind,
checked against the aspect’s `applies_to`. Never raises for a method that
does not apply: it falls back and records why.

* **Return type:**
  [`Resolution`](an.semantic.matcher.md#an.semantic.matcher.Resolution)

### an.semantic.vocabulary(, kind=None, owner=None)

Every entry as data (what the MCP surface returns), filtered by `kind`/`owner`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.semantic.why_not(method, subjects)

What `method` is missing on `subjects`, each with its remedy (empty: it applies).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Missing`](an.semantic.matcher.md#an.semantic.matcher.Missing), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### Modules

| [`describe`](an.semantic.describe.md#module-an.semantic.describe)   | Describe an asset: what it affords, and per aspect what applies and what is missing.        |
|-----------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`digest`](an.semantic.digest.md#module-an.semantic.digest)       | Which vocabulary entries a shot names, at which versions: the shot's vocabulary digest.     |
| [`docs`](an.semantic.docs.md#module-an.semantic.docs)           | The vocabulary section of the downstream `an` skill, generated from the registry.           |
| [`matcher`](an.semantic.matcher.md#module-an.semantic.matcher)     | The three queries and the policy (ADR 0002 decision 4): `applicable`, `why_not`, `resolve`. |
| [`prompt`](an.semantic.prompt.md#module-an.semantic.prompt)       | The `an iterate` system prompt, generated from the vocabulary registry.                     |
| [`registry`](an.semantic.registry.md#module-an.semantic.registry)   | The one vocabulary registry (ADR 0003 decision 6): entries and aspects, by owner.           |
| [`seeds`](an.semantic.seeds.md#module-an.semantic.seeds)         | The core's vocabulary: views over the kind and easing registries, camera moves, IR fields.  |
| [`views`](an.semantic.views.md#module-an.semantic.views)         | View spaces: what a camera move moves through, defined once for every engine (an#257).      |
