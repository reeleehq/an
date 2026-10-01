# an.library.affordances

Affordances: what an asset can do, derived from its descriptor and the art present.

This is the seed of ADR 0002’s `affordances(asset) → set[Capability]`, built
so its registry (P7) adopts it rather than writing a second derivation:

- an **analyser** is registered per asset kind ([`register_analyser()`](#an.library.affordances.register_analyser)) with a
  version. It reads the descriptor document and the art present — a mapping of
  each file’s relative path to its `ContentRef` (so a later analyser can read
  bytes through the blob store; today’s tests membership only) —
  never a hand-typed list beside them (ADR 0002 decision 2) — and returns
  `{capability: params}`. A capability that is absent is not afforded;
- a **capability** is a dotted, registered name ([`register_capability()`](#an.library.affordances.register_capability))
  with a description and a **remedy** (what would add it, and the command when
  one exists), because `find(…, near=True)` must say how to close a near miss;
- **params** are the capability’s parameters. The one convention every query
  relies on: `keys` lists the discrete values it affords, so `swap.view:side`
  asks for `swap.view` with `side` among its keys. `overrides` lists the
  declared descriptor fields (`rest_view`, …) the
  derivation used instead of deriving — ADR 0002’s “the derivation reports which
  overrides it used”.

The library snapshots an analyser’s output on each version with the analyser’s
version (`analysers: {kind: version}`); a reader whose analyser is newer
recomputes rather than trusting the snapshot ([`current_affordances()`](#an.library.affordances.current_affordances)).

Capability names are persisted identifiers: once a version stores one, it is
renamed only through this registry, never in place.

```pycon
>>> afford = {"swap.view": {"keys": ["front", "side"]}, "limbs.legs": {}}
>>> matches(afford, "swap.view:side"), matches(afford, "swap.view:back"), matches(afford, "limbs.legs")
(True, False, True)
```

### Module Attributes

| [`KEY_SEP`](#an.library.affordances.KEY_SEP)      | Separates a capability from one of its keys in a query (`swap.view:side`).   |
|---------------------------------------------------------------|------------------------------------------------------------------------------|
| [`CAPABILITIES`](#an.library.affordances.CAPABILITIES) | Registered capabilities, by name.                                            |
| [`ANALYSERS`](#an.library.affordances.ANALYSERS)    | Registered analysers, by asset kind.                                         |

### Functions

| [`analyse`](#an.library.affordances.analyse)(kind, doc, art)                            | `(affordances, analysers)` of one asset: its capabilities and the analyser versions used.   |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`capability_of`](#an.library.affordances.capability_of)(query)                               | `(capability, key)` of a query term.                                                        |
| [`current_affordances`](#an.library.affordances.current_affordances)(kind, doc, art, \*, ...)       | The stored snapshot when its analyser version is current, else a fresh derivation.          |
| [`matches`](#an.library.affordances.matches)(affordances, query)                        | Whether `affordances` satisfy one query term (`cap` or `cap:key`).                          |
| [`missing`](#an.library.affordances.missing)(affordances, queries)                      | The query terms `affordances` do not satisfy, in the order asked.                           |
| [`register_analyser`](#an.library.affordances.register_analyser)(kind, \*, version)               | Decorator: register `derive` as the analyser of `kind` at `version`.                        |
| [`register_capability`](#an.library.affordances.register_capability)(name, \*, description, remedy) | Register (or re-register) a capability.                                                     |
| [`remedy_for`](#an.library.affordances.remedy_for)(query)                                  | What would add the capability a query term asks for.                                        |

### Classes

| [`Analyser`](#an.library.affordances.Analyser)(kind, version, derive)       | The derivation of one asset kind's affordances, versioned.      |
|----------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| [`Capability`](#an.library.affordances.Capability)(name, description, remedy) | A registered capability name, what it means, and how to add it. |

### an.library.affordances.ANALYSERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Analyser](#an.library.affordances.Analyser)]* *= {'character': Analyser(kind='character', version='0.1.0', derive=<function character_affordances>)}*

Registered analysers, by asset kind.

### *class* an.library.affordances.Analyser(kind, version, derive)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The derivation of one asset kind’s affordances, versioned.

### an.library.affordances.CAPABILITIES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Capability](#an.library.affordances.Capability)]* *= {'face.mouth': Capability(name='face.mouth', description='an overlay mouth with a viseme chart that lip-sync drives (keys: the chart)', remedy="give the character an overlay mouth: a \`mouth\` slot with the viseme set's drawings (\`an character mouths <dir>\` writes the default nine) and face_overlay: true — a face baked into the head art cannot lip-sync"), 'limbs.arms': Capability(name='limbs.arms', description='a pair of arm slots with art that a walk swings and gestures move', remedy='add two arm slots named arm_l/arm_r (or left_arm/right_arm) with their art, pivoted at the shoulder (an-art-package skill)'), 'limbs.legs': Capability(name='limbs.legs', description='a pair of leg slots with art that a legged walk swings', remedy='add two leg slots named leg_l/leg_r (or left_leg/right_leg) with their art, pivoted at the hip; \`an character new\` builds them (an-art-package skill)'), 'swap.view': Capability(name='swap.view', description='the turnaround views the character can show (keys); swappable=true when a \`view\` swap set lets it turn', remedy='add turnaround art and list it in the \`view\` swap set: \`an character add-views <dir>\` for an offline character, else draw the views')}*

Registered capabilities, by name. Genre packages add theirs on import.

### *class* an.library.affordances.Capability(name, description, remedy)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A registered capability name, what it means, and how to add it.

### an.library.affordances.KEY_SEP *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ':'*

Separates a capability from one of its keys in a query (`swap.view:side`).

### an.library.affordances.analyse(kind, doc, art)

`(affordances, analysers)` of one asset: its capabilities and the analyser versions used.

A kind with no registered analyser affords nothing *derived* and records no
analyser — an honest empty answer, not a guess.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.library.affordances.capability_of(query)

`(capability, key)` of a query term.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

```pycon
>>> capability_of("swap.view:side"), capability_of("limbs.legs")
(('swap.view', 'side'), ('limbs.legs', None))
```

### an.library.affordances.current_affordances(kind, doc, art, , stored, stored_analysers)

The stored snapshot when its analyser version is current, else a fresh derivation.

Affordances are derived data, so recomputing them is always safe; trusting a
snapshot made by an older analyser is what would make a facet lie.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.library.affordances.matches(affordances, query)

Whether `affordances` satisfy one query term (`cap` or `cap:key`).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.library.affordances.missing(affordances, queries)

The query terms `affordances` do not satisfy, in the order asked.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.library.affordances.register_analyser(kind, , version)

Decorator: register `derive` as the analyser of `kind` at `version`.

Bump `version` whenever the derivation’s output can change for the same
input: versions published under the old one are then recomputed on read.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)], [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]]], [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)], [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]]]

### an.library.affordances.register_capability(name, , description, remedy)

Register (or re-register) a capability. Returns it.

* **Return type:**
  [`Capability`](#an.library.affordances.Capability)

### an.library.affordances.remedy_for(query)

What would add the capability a query term asks for.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> remedy_for("no.such.capability")
'no registered capability no.such.capability; see vocabulary() for the known names'
```
