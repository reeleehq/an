# an.capabilities

Capabilities: what an asset, an engine or the environment affords, and the one matcher.

ADR 0002 (capability-based applicability, with a universal default) and the core
study §2.13 (three subjects). This is the LOWER layer of the pair: it knows
capabilities, analysers, requirements and substitution records, and nothing
about vocabulary entries, methods or aspects — [`an.semantic`](an.semantic.html.md#module-an.semantic) imports it,
never the reverse, and neither imports [`an.ir`](an.ir.html.md#module-an.ir) at module level.

- A **capability** is a named, possibly parametrised fact (`limbs.legs`,
  `face.mouth` with chart `rhubarb9`, `env.latex`). Names use one dotted
  grammar, are registered with a description and a **remedy** (what would add
  it, and the command where one exists), and are **persisted identifiers**: the
  asset library’s facets and the substitution records store them. A capability
  belongs to one **subject**: `asset`, `engine` or `environment`.
- An **analyser** derives a subject’s capabilities — a **profile**,
  `{capability: params}` — from what is there (a descriptor and its art, a
  renderer’s implemented members, the tools on `PATH`), never from a list
  typed beside it (ADR 0002 decision 2). It is versioned: a stored snapshot
  made by an older analyser is recomputed ([`current_affordances()`](#an.capabilities.current_affordances)).
  Declared facts used *instead of* deriving are listed under the
  `overrides` param, so the derivation reports which overrides it used.
- A **requirement** is a predicate over a profile, spelled as a string. The
  whole grammar (consult on P7, §3): `cap` (afforded), `cap:key` (`key`
  among the capability’s `keys`), `cap>=N` (its `count` param — else its
  number of `keys` — is at least `N`) and `a|b` (any of). No callables:
  a requirement must name its remedy, render into the generated docs and the
  MCP surface, and diff when a method’s version bumps.
- [`missing()`](#an.capabilities.missing) is THE matcher: the requirement terms a profile (or a
  [`Subjects`](#an.capabilities.Subjects) triple) does not meet, in the order asked. `why_not`,
  > `applicable` and `resolve` (in [`an.semantic`](an.semantic.html.md#module-an.semantic)) and the library’s
  > `find(…, near=True)` are all calls to it.
- A [`Substitution`](#an.capabilities.Substitution) records that a method other than the requested one
  was used (generalising the compiled document’s `asset_resolution`).
  `policy` choices are information; `missing` and `noop` are warnings
  that `--strict-assets` makes fatal ([`FATAL_REASONS`](#an.capabilities.FATAL_REASONS)).

```pycon
>>> profile = {"swap.view": {"keys": ["front", "side"]}, "limbs.legs": {}}
>>> matches(profile, "swap.view:side"), matches(profile, "swap.view:back"), matches(profile, "limbs.legs")
(True, False, True)
>>> missing(profile, ["limbs.legs", "face.mouth|face.jaw", "swap.view>=3"])
['face.mouth|face.jaw', 'swap.view>=3']
```

### Module Attributes

| [`SUBJECTS`](#an.capabilities.SUBJECTS)        | The three subjects a capability can belong to (core study §2.13).                    |
|------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`KEY_SEP`](#an.capabilities.KEY_SEP)         | Separates a capability from one of its keys in a term (`swap.view:side`).            |
| [`KEYS_PARAM`](#an.capabilities.KEYS_PARAM)      | The params entry listing the discrete values a capability affords.                   |
| [`OVERRIDES_PARAM`](#an.capabilities.OVERRIDES_PARAM) | The params entry listing the declared facts the derivation used instead of deriving. |
| [`Profile`](#an.capabilities.Profile)         | `{capability: params}` — what an analyser derives, and the matcher's only input.     |
| [`CAPABILITIES`](#an.capabilities.CAPABILITIES)    | Registered capabilities, by name.                                                    |
| [`ANALYSERS`](#an.capabilities.ANALYSERS)       | Registered analysers, by kind.                                                       |
| [`FATAL_REASONS`](#an.capabilities.FATAL_REASONS)   | The reasons `--strict-assets` makes fatal (a test pins this set).                    |

### Functions

| [`affordances`](#an.capabilities.affordances)(asset[, art, kind])                   | `affordances(asset)` (ADR 0002 decision 2): what `asset` affords, derived.                                                |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| [`analyse`](#an.capabilities.analyse)(kind, doc[, art])                         | `(profile, analysers)` of one subject: its capabilities and the analyser versions used.                                   |
| [`art_in_dir`](#an.capabilities.art_in_dir)(directory, \*[, exclude])              | The art an asset folder holds, as an analyser reads it: `{relative path: True}`.                                          |
| [`capability_names`](#an.capabilities.capability_names)(\*[, subject, owner])            | The registered capability names, sorted; filtered by `subject`/`owner`.                                                   |
| [`capability_of`](#an.capabilities.capability_of)(query)                              | `(capability, key)` of a query term (the library's `find` form).                                                          |
| [`current_affordances`](#an.capabilities.current_affordances)(kind, doc, art, \*, ...)      | The stored snapshot when its analyser version is current, else a fresh derivation.                                        |
| [`matches`](#an.capabilities.matches)(profile, term)                            | Whether `profile` (or the subject of `term` in a [`Subjects`](#an.capabilities.Subjects)) meets `term`. |
| [`missing`](#an.capabilities.missing)(profile, requires)                        | The requirement terms `profile` does not meet, spelled, in the order asked.                                               |
| [`parse_requirement`](#an.capabilities.parse_requirement)(spec)                           | A [`Requirement`](#an.capabilities.Requirement) from its spelling (`cap`, `cap:key`, `cap>=N`, `a|b`).     |
| [`register_analyser`](#an.capabilities.register_analyser)(kind, \*[, version, ...])       | Register an analyser.                                                                                                     |
| [`register_capability`](#an.capabilities.register_capability)(name, \*[, description, ...]) | Register a capability (or a [`Capability`](#an.capabilities.Capability)).                                 |
| [`remedy_for`](#an.capabilities.remedy_for)(term)                                  | What would add the capability a requirement term asks for.                                                                |
| [`subject_of`](#an.capabilities.subject_of)(term)                                  | The subject whose profile a requirement term is matched against.                                                          |

### Classes

| [`Analyser`](#an.capabilities.Analyser)(kind, version, derive[, subject, ...])   | The derivation of one kind's profile, versioned.                                   |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`Capability`](#an.capabilities.Capability)(name, description, remedy[, ...])      | A registered capability: its name, what it means, and how to add it.               |
| [`Requirement`](#an.capabilities.Requirement)([capability, key, at_least, any_of])  | One requirement term: a capability, optionally a key or a count, or a disjunction. |
| [`Subjects`](#an.capabilities.Subjects)([asset, engine, environment])            | The three profiles a requirement can be matched against.                           |
| [`Substitution`](#an.capabilities.Substitution)(aspect, entity, requested, ...)      | One recorded substitution: the method asked for, the one used, and why.            |

### Exceptions

| [`CapabilityError`](#an.capabilities.CapabilityError)   | A capability, analyser or requirement is malformed, or collides with one registered.   |
|--------------------------------------------------------------------|----------------------------------------------------------------------------------------|

### an.capabilities.ANALYSERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Analyser](#an.capabilities.Analyser)]* *= {'engine': Analyser(kind='engine', version='2', subject='engine', declares=()), 'environment': Analyser(kind='environment', version='2', subject='environment', declares=())}*

Registered analysers, by kind.

### *class* an.capabilities.Analyser(kind, version, derive, subject='asset', declares=(), overrides=None)

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

### an.capabilities.CAPABILITIES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Capability](#an.capabilities.Capability)]* *= {'engine.compile': Capability(name='engine.compile', description='the engine implements the optional \`compile\` member', remedy='use an engine that implements \`compile\`', subject='engine', command=None, version='1'), 'engine.measure_duration': Capability(name='engine.measure_duration', description='the engine implements the optional \`measure_duration\` member', remedy='use an engine that implements \`measure_duration\`', subject='engine', command=None, version='1'), 'engine.preview': Capability(name='engine.preview', description='the engine implements the optional \`preview\` member', remedy='use an engine that implements \`preview\`', subject='engine', command=None, version='1'), 'engine.render': Capability(name='engine.render', description='the engine renders shots (keys: the Shot.renderer values it claims)', remedy="register a renderer that claims the shot's \`renderer\` (an.adapters.register_renderer)", subject='engine', command=None, version='1'), 'engine.render_frames': Capability(name='engine.render_frames', description='the engine implements the optional \`render_frames\` member', remedy='use an engine that implements \`render_frames\`', subject='engine', command=None, version='1'), 'engine.seek': Capability(name='engine.seek', description='the engine implements the optional \`seek\` member', remedy='use an engine that implements \`seek\`', subject='engine', command=None, version='1'), 'env.browser': Capability(name='env.browser', description='Playwright with a Chromium build, which the stage engine renders in', remedy="pip install 'an[cutout]' && playwright install chromium", subject='environment', command=None, version='1'), 'env.ffmpeg': Capability(name='env.ffmpeg', description='\`ffmpeg\` is on PATH', remedy='install ffmpeg (\`brew install ffmpeg\` on macOS, \`apt install ffmpeg\` on Debian)', subject='environment', command=None, version='1'), 'env.key.anthropic': Capability(name='env.key.anthropic', description='the ANTHROPIC_API_KEY environment variable is set (its value is never read)', remedy='set ANTHROPIC_API_KEY (needed by \`an iterate\` and the vision verifier)', subject='environment', command=None, version='1'), 'env.key.elevenlabs': Capability(name='env.key.elevenlabs', description='the ELEVEN_API_KEY environment variable is set (its value is never read)', remedy='set ELEVEN_API_KEY (needed by the ElevenLabs voices)', subject='environment', command=None, version='1'), 'env.latex': Capability(name='env.latex', description='\`latex\` is on PATH', remedy='install a TeX distribution (MacTeX / TeX Live) so \`latex\` is on PATH', subject='environment', command=None, version='1'), 'env.manim': Capability(name='env.manim', description='the manim, manimkit Python package(s) are importable', remedy="pip install 'an[manim]' (Manim Community Edition and manimkit; on Linux first \`apt install libcairo2-dev libpango1.0-dev\`)", subject='environment', command=None, version='1'), 'env.node': Capability(name='env.node', description='\`node\` is on PATH', remedy='install Node.js (\`brew install node\`)', subject='environment', command=None, version='1'), 'env.rhubarb': Capability(name='env.rhubarb', description='\`rhubarb\` is on PATH', remedy='install Rhubarb Lip Sync (\`brew install rhubarb-lipsync\`)', subject='environment', command=None, version='1'), 'rig.hierarchy': Capability(name='rig.hierarchy', description="the rig nests its parts in chains (\`nesting: bones\`): keys = the chain roots, count = the deepest chain's length in parts", remedy="declare \`nesting: bones\` on the rig document and parent each part's bone to the bone it hangs from (an elbow's to the shoulder's)", subject='asset', command=None, version='1'), 'space.framing2d': Capability(name='space.framing2d', description='the engine lowers moves through the framing2d view space: a 2D framing of a flat picture: position, zoom (log), roll (angle)', remedy='render with an engine that lowers the framing2d view space', subject='engine', command=None, version='1'), 'space.orbit3d': Capability(name='space.orbit3d', description='the engine lowers moves through the orbit3d view space: an orbit camera around a 3D target: azimuth and elevation (angles), distance (log)', remedy='render with an engine that lowers the orbit3d view space', subject='engine', command=None, version='1')}*

Registered capabilities, by name.

### *class* an.capabilities.Capability(name, description, remedy, subject='asset', command=None, version='1')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A registered capability: its name, what it means, and how to add it.

`command` is the CLI that adds it, when one exists (`an character
add-views`); `version` bumps when the *meaning* of the name changes (a
persisted name is never redefined in place).

#### to_json()

The capability as the generated docs and the MCP surface list it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *exception* an.capabilities.CapabilityError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A capability, analyser or requirement is malformed, or collides with one registered.

### an.capabilities.FATAL_REASONS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'missing', 'noop'})*

The reasons `--strict-assets` makes fatal (a test pins this set).

### an.capabilities.KEYS_PARAM *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'keys'*

The params entry listing the discrete values a capability affords.

### an.capabilities.KEY_SEP *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ':'*

Separates a capability from one of its keys in a term (`swap.view:side`).

### an.capabilities.OVERRIDES_PARAM *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'overrides'*

The params entry listing the declared facts the derivation used instead of deriving.

### an.capabilities.Profile

`{capability: params}` — what an analyser derives, and the matcher’s only input.

alias of [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### *class* an.capabilities.Requirement(capability='', key=None, at_least=None, any_of=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One requirement term: a capability, optionally a key or a count, or a disjunction.

```pycon
>>> str(parse_requirement("swap.view:side")), str(parse_requirement("rig.slots>=2"))
('swap.view:side', 'rig.slots>=2')
>>> [str(r) for r in parse_requirement("face.eyes|face.brows").any_of]
['face.eyes', 'face.brows']
```

#### capabilities()

Every capability name this term mentions.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.capabilities.SUBJECTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('asset', 'engine', 'environment')*

The three subjects a capability can belong to (core study §2.13).

### *class* an.capabilities.Subjects(asset=<factory>, engine=<factory>, environment=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The three profiles a requirement can be matched against.

A bare profile passed where `Subjects` is expected is the asset’s.

```pycon
>>> Subjects.of({"limbs.legs": {}}).asset
{'limbs.legs': {}}
```

### *class* an.capabilities.Substitution(aspect, entity, requested, chosen, reason, requested_version=None, chosen_version='', missing=(), remedies=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One recorded substitution: the method asked for, the one used, and why.

It generalises the compiled document’s `asset_resolution` (ADR 0002
decision 6): a requested method replaced by a default is said out loud,
and fatal under `--strict-assets` unless it was a policy choice.

```pycon
>>> s = Substitution("locomotion", "bob", requested="loco.hem_sway", chosen="loco.rock",
...                  reason="missing", missing=("limbs.legs",))
>>> s.fatal, s.sentence()
(True, "bob: locomotion 'loco.hem_sway' does not apply (missing limbs.legs); used 'loco.rock'")
```

#### sentence()

One human sentence saying what happened.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.capabilities.affordances(asset, art=None, , kind='character')

`affordances(asset)` (ADR 0002 decision 2): what `asset` affords, derived.

`asset` is the document (a mapping, or a pydantic model, dumped to JSON
first); `art` the files present, `{relative path: ref}`. The kind’s
registered analyser decides; with none, nothing is afforded.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.capabilities.analyse(kind, doc, art=None)

`(profile, analysers)` of one subject: its capabilities and the analyser versions used.

A kind with no registered analyser affords nothing *derived* and records no
analyser — an honest empty answer, not a guess.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> analyse("no-such-kind", {})
({}, {})
```

### an.capabilities.art_in_dir(directory, , exclude=())

The art an asset folder holds, as an analyser reads it: `{relative path: True}`.

`exclude` drops the document files themselves (`character.json`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`bool`](https://docs.python.org/3/builtins/functions.html#bool)]

```pycon
>>> import tempfile, pathlib
>>> with tempfile.TemporaryDirectory() as d:
...     _ = (pathlib.Path(d) / "parts").mkdir(); _ = (pathlib.Path(d) / "parts" / "head.svg").write_text("<svg/>", encoding="utf-8")
...     sorted(art_in_dir(d))
['parts/head.svg']
```

### an.capabilities.capability_names(, subject=None, owner=None)

The registered capability names, sorted; filtered by `subject`/`owner`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.capabilities.capability_of(query)

`(capability, key)` of a query term (the library’s `find` form).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

```pycon
>>> capability_of("swap.view:side"), capability_of("limbs.legs")
(('swap.view', 'side'), ('limbs.legs', None))
```

### an.capabilities.current_affordances(kind, doc, art, , stored, stored_analysers)

The stored snapshot when its analyser version is current, else a fresh derivation.

Affordances are derived data, so recomputing them is always safe; trusting a
snapshot made by an older analyser is what would make a facet lie.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.capabilities.matches(profile, term)

Whether `profile` (or the subject of `term` in a [`Subjects`](#an.capabilities.Subjects)) meets `term`.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.capabilities.missing(profile, requires)

The requirement terms `profile` does not meet, spelled, in the order asked.

THE matcher (ADR 0002 decision 4): `why_not`, `applicable`,
`resolve` and the library’s `find(…, near=True)` all call it.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> missing({}, ["env.ffmpeg"]), missing(Subjects(environment={"env.ffmpeg": {}}), ["env.ffmpeg"])
(['env.ffmpeg'], [])
```

### an.capabilities.parse_requirement(spec)

A [`Requirement`](#an.capabilities.Requirement) from its spelling (`cap`, `cap:key`, `cap>=N`, `a|b`).

* **Return type:**
  [`Requirement`](#an.capabilities.Requirement)

```pycon
>>> parse_requirement("rig.slots>=2").at_least
2
>>> parse_requirement("limbs.legs(hips)")
Traceback (most recent call last):
...
an.capabilities.CapabilityError: requirement 'limbs.legs(hips)': ...
```

### an.capabilities.register_analyser(kind, , version='', subject='asset', owner='an')

Register an analyser. Two forms.

`register_analyser(Analyser(...), owner=...)` registers the object and
returns it (a genre’s `analysers` field goes this way). With a `kind`
string it is a decorator: `@register_analyser("character", version="0.1.0")`
registers the decorated derivation.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.capabilities.register_capability(name, , description='', remedy='', subject='asset', command=None, version='1', owner='an')

Register a capability (or a [`Capability`](#an.capabilities.Capability)). Returns it.

Re-registering the same definition is a no-op; a different definition
under a name another owner holds raises, because capability names are
persisted and two meanings for one name would make a stored facet lie.

* **Return type:**
  [`Capability`](#an.capabilities.Capability)

```pycon
>>> cap = register_capability("demo.thing", description="a thing", remedy="add one", owner="demo")
>>> CAPABILITIES["demo.thing"] is cap
True
>>> _ = drop_owner("demo")
```

### an.capabilities.remedy_for(term)

What would add the capability a requirement term asks for.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> remedy_for("no.such.capability")
'no registered capability no.such.capability; see vocabulary() for the known names'
```

### an.capabilities.subject_of(term)

The subject whose profile a requirement term is matched against.

An unregistered capability is matched against the asset (and reported
missing there): [`an.semantic.check_registry()`](an.semantic.html.md#an.semantic.check_registry) is what refuses it.

* **Return type:**
  str

```pycon
>>> subject_of("env.latex") == subject_of("limbs.legs")
False
```

### Modules

| [`subjects`](an.capabilities.subjects.html.md#module-an.capabilities.subjects)   | The core's two non-asset subjects: the engine (a renderer) and the environment.   |
|---------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
