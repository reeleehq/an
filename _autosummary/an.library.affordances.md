# an.library.affordances

Affordances for the library: the capability registry, re-exported from [`an.capabilities`](an.capabilities.md#module-an.capabilities).

P5 seeded ADR 0002’s `affordances(asset)` here; P7 moved the tables and the
matcher to the core registry, [`an.capabilities`](an.capabilities.md#module-an.capabilities), and this module now
re-exports the SAME objects (`ANALYSERS is an.capabilities.ANALYSERS`), so the
library’s facets and `find(…, near=True)` and the compiler’s method choice
are one derivation and one matcher, never two.

The character analyser is the cut-out genre’s: it registers through
`an.genres.cutout.CUTOUT` (its `capabilities` and `analysers`
fields) when the genres load, which the library’s entry points do
([`an.library.api.publish()`](an.library.api.md#an.library.api.publish), [`an.library.api.find()`](an.library.api.md#an.library.api.find)).

```pycon
>>> import an.capabilities
>>> ANALYSERS is an.capabilities.ANALYSERS and CAPABILITIES is an.capabilities.CAPABILITIES
True
>>> afford = {"swap.view": {"keys": ["front", "side"]}, "limbs.legs": {}}
>>> matches(afford, "swap.view:side"), matches(afford, "swap.view:back"), matches(afford, "limbs.legs")
(True, False, True)
```

### Functions

| [`analyse`](#an.library.affordances.analyse)(kind, doc[, art])                         | `(profile, analysers)` of one subject: its capabilities and the analyser versions used.   |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| [`capability_of`](#an.library.affordances.capability_of)(query)                              | `(capability, key)` of a query term (the library's `find` form).                          |
| [`current_affordances`](#an.library.affordances.current_affordances)(kind, doc, art, \*, ...)      | The stored snapshot when its analyser version is current, else a fresh derivation.        |
| [`matches`](#an.library.affordances.matches)(profile, term)                            | Whether `profile` (or the subject of `term` in a `Subjects`) meets `term`.                |
| [`missing`](#an.library.affordances.missing)(profile, requires)                        | The requirement terms `profile` does not meet, spelled, in the order asked.               |
| [`register_analyser`](#an.library.affordances.register_analyser)(kind, \*[, version, ...])       | Register an analyser.                                                                     |
| [`register_capability`](#an.library.affordances.register_capability)(name, \*[, description, ...]) | Register a capability (or a [`Capability`](#an.library.affordances.Capability)). |
| [`remedy_for`](#an.library.affordances.remedy_for)(term)                                  | What would add the capability a requirement term asks for.                                |

### Classes

| [`Analyser`](#an.library.affordances.Analyser)(kind, version, derive[, subject, ...])   | The derivation of one kind's profile, versioned.                     |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`Capability`](#an.library.affordances.Capability)(name, description, remedy[, ...])      | A registered capability: its name, what it means, and how to add it. |

### *class* an.library.affordances.Analyser(kind, version, derive, subject='asset', declares=(), overrides=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The derivation of one kind’s profile, versioned.

`kind` is an asset kind (`character`) or a subject that has one
analyser (`engine`, `environment`). Bump `version` whenever the
output can change for the same input: snapshots made under the old one are
then recomputed on read. The version is NOT a compile input (consult §5):
the derived profile is, so touching an analyser without changing its output
re-renders nothing.

#### declares *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

The document’s declared facts the derivation honours instead of deriving
(`rest_view`, `face_overlay`) or reads as a request (`gait`):
reported by `describe_asset` (ADR 0002 decision 2).

#### overrides *: [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[Any](https://docs.python.org/3/library/typing.html#typing.Any), [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]], [Iterable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]] | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

`(doc, art) -> declared field names` the derivation USED as overrides
that do not show on an afforded capability’s params: a declared fact
that REMOVES a capability (a character’s `occluded`, an#381). Those on
an afforded capability are already in its `overrides` param.
`None`: none beyond those. Reporting only: it changes no profile, so
adding it does not bump `version`.

### *class* an.library.affordances.Capability(name, description, remedy, subject='asset', command=None, version='1')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A registered capability: its name, what it means, and how to add it.

`command` is the CLI that adds it, when one exists (`an character
add-views`); `version` bumps when the *meaning* of the name changes (a
persisted name is never redefined in place).

#### to_json()

The capability as the generated docs and the MCP surface list it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.library.affordances.analyse(kind, doc, art=None)

`(profile, analysers)` of one subject: its capabilities and the analyser versions used.

A kind with no registered analyser affords nothing *derived* and records no
analyser — an honest empty answer, not a guess.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> analyse("no-such-kind", {})
({}, {})
```

### an.library.affordances.capability_of(query)

`(capability, key)` of a query term (the library’s `find` form).

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

### an.library.affordances.matches(profile, term)

Whether `profile` (or the subject of `term` in a `Subjects`) meets `term`.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.library.affordances.missing(profile, requires)

The requirement terms `profile` does not meet, spelled, in the order asked.

THE matcher (ADR 0002 decision 4): `why_not`, `applicable`,
`resolve` and the library’s `find(…, near=True)` all call it.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> missing({}, ["env.ffmpeg"]), missing(Subjects(environment={"env.ffmpeg": {}}), ["env.ffmpeg"])
(['env.ffmpeg'], [])
```

### an.library.affordances.register_analyser(kind, , version='', subject='asset', owner='an')

Register an analyser. Two forms.

`register_analyser(Analyser(...), owner=...)` registers the object and
returns it (a genre’s `analysers` field goes this way). With a `kind`
string it is a decorator: `@register_analyser("character", version="0.1.0")`
registers the decorated derivation.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.library.affordances.register_capability(name, , description='', remedy='', subject='asset', command=None, version='1', owner='an')

Register a capability (or a [`Capability`](#an.library.affordances.Capability)). Returns it.

Re-registering the same definition is a no-op; a different definition
under a name another owner holds raises, because capability names are
persisted and two meanings for one name would make a stored facet lie.

* **Return type:**
  [`Capability`](an.capabilities.md#an.capabilities.Capability)

```pycon
>>> cap = register_capability("demo.thing", description="a thing", remedy="add one", owner="demo")
>>> CAPABILITIES["demo.thing"] is cap
True
>>> _ = drop_owner("demo")
```

### an.library.affordances.remedy_for(term)

What would add the capability a requirement term asks for.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> remedy_for("no.such.capability")
'no registered capability no.such.capability; see vocabulary() for the known names'
```
