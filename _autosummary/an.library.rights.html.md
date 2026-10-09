# an.library.rights

Rights on every version: the most restrictive licence class wins (ADR 0005 decision 10, design §9).

The library adds no licence vocabulary. A version’s rights are rolled up from
`an`’s existing model (an#211): [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource) records and
[`license_class()`](an.ir.assets.html.md#an.ir.assets.license_class)’s four classes. The roll-up reads them from

- the source declared for the asset as a whole at publish, AND the descriptor’s
  own `source` — both, never one instead of the other (an asset with neither
  is `unknown`: recorded and visible, never rejected);
- every part and plane that declares its own `source` — gathered by
  [`an.credits.collect_credits()`](an.credits.html.md#an.credits.collect_credits), the same walk `an credits` runs, so the
  > library and the credits report can never disagree about what an asset holds;
- every version it derives from (`derived_from`) and the version it follows
  (`previous`), recursively, by the same rules: a derivative inherits the
  obligations of its sources, and a new version cannot relabel the old one;
- the source any other version records for the same file bytes (by blob
  digest): a file’s own recorded provenance travels with its bytes, so carved
  parts published again under a new id keep their obligations
  ([`an.library.api.version_sources()`](an.library.api.html.md#an.library.api.version_sources) walks all of it).

A version may only ever be MORE restrictive than what it inherits. Relaxing
takes an explicit, recorded relicence — who and why — on the version. Where
nobody ever said anything (a file an earlier version recorded `unlabelled`,
a version with no source), an explicit source with a recorded `relabel` —
who and why — is the first statement (an#263); it relaxes nothing anyone said.

Order, most restrictive first: `private` > `unknown` > `attribution` >
`free`. `private` and `unknown` are not publishable.

```pycon
>>> from an.ir.assets import AssetSource
>>> r = roll_up([("asset", AssetSource(provider="p", license="cc0-1.0")),
...              ("parts/head.png", AssetSource(provider="film", license="all-rights-reserved"))])
>>> (r.license_class, r.publishable)
('private', False)
>>> r.reasons
['parts/head.png: all-rights-reserved (private)']
```

### Module Attributes

| [`LICENSE_CLASS_ORDER`](#an.library.rights.LICENSE_CLASS_ORDER)   | Licence classes, most restrictive first.                                                                                                                                                                  |
|------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`PUBLISHABLE_CLASSES`](#an.library.rights.PUBLISHABLE_CLASSES)   | The classes a video may ship with (`attribution` and `noncommercial` with their credit displayed; `noncommercial` only in a video nobody earns from — an#373: flagged for commercial use, never blocked). |
| [`COMMERCIAL_CLASSES`](#an.library.rights.COMMERCIAL_CLASSES)    | The classes a COMMERCIAL video may ship with (monetised, sponsored, client work).                                                                                                                         |

### Functions

| [`most_restrictive`](#an.library.rights.most_restrictive)(classes)                   | The most restrictive of `classes`; `free` for none.                                                            |
|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| [`descriptor_source`](#an.library.rights.descriptor_source)(doc, \*, store)           | The source the descriptor itself declares (or `an credits` reconstructs), if any.                              |
| [`roll_up`](#an.library.rights.roll_up)(sources, \*[, inherited])           | Roll labelled sources (and parents' rights) up to one [`Rights`](#an.library.rights.Rights). |
| [`sources_in`](#an.library.rights.sources_in)(doc, \*, store[, source, files]) | Every labelled source one version holds: the asset's, the descriptor's, each part's.                           |

### Classes

| [`Rights`](#an.library.rights.Rights)(license_class[, reasons])   | The rolled-up rights of one version, as stored on it.   |
|-------------------------------------------------------------------------------------|---------------------------------------------------------|

### Exceptions

| [`RightsRefusal`](#an.library.rights.RightsRefusal)   | A private or unknown version would leave the user's library without an override.   |
|------------------------------------------------------------------|------------------------------------------------------------------------------------|

### an.library.rights.COMMERCIAL_CLASSES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'attribution', 'free'})*

The classes a COMMERCIAL video may ship with (monetised, sponsored, client work).

### an.library.rights.LICENSE_CLASS_ORDER *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Literal](https://docs.python.org/3/library/typing.html#typing.Literal)['attribution', 'free', 'noncommercial', 'private', 'unknown'], ...]* *= ('private', 'unknown', 'noncommercial', 'attribution', 'free')*

Licence classes, most restrictive first. The roll-up keeps the first that occurs.

### an.library.rights.PUBLISHABLE_CLASSES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'attribution', 'free', 'noncommercial'})*

The classes a video may ship with (`attribution` and `noncommercial`
with their credit displayed; `noncommercial` only in a video nobody earns
from — an#373: flagged for commercial use, never blocked).

### *class* an.library.rights.Rights(license_class, reasons=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The rolled-up rights of one version, as stored on it.

#### *property* commercial *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether a COMMERCIAL video containing this asset may ship (an#373).

#### *classmethod* from_dict(d)

Read a version’s `rights` block back.

* **Return type:**
  [`Rights`](#an.library.rights.Rights)

#### *property* publishable *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether a video containing this asset may ship (commercially or not).

#### to_dict()

The `rights` block of a version document.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *exception* an.library.rights.RightsRefusal

Bases: [`PermissionError`](https://docs.python.org/3/builtins/exceptions.html#PermissionError)

A private or unknown version would leave the user’s library without an override.

### an.library.rights.descriptor_source(doc, , store)

The source the descriptor itself declares (or `an credits` reconstructs), if any.

* **Return type:**
  [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.library.rights.most_restrictive(classes)

The most restrictive of `classes`; `free` for none.

* **Return type:**
  [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'attribution'`, `'free'`, `'noncommercial'`, `'private'`, `'unknown'`]

```pycon
>>> most_restrictive(["free", "attribution"]), most_restrictive([])
('attribution', 'free')
```

### an.library.rights.roll_up(sources, , inherited=())

Roll labelled sources (and parents’ rights) up to one [`Rights`](#an.library.rights.Rights).

A `None` source is `unknown`. The reasons name every contributor of the
winning class, so a reader sees *why* a version is restricted.

* **Return type:**
  [`Rights`](#an.library.rights.Rights)

```pycon
>>> roll_up([("asset", None)]).to_dict()
{'license_class': 'unknown', 'publishable': False, 'reasons': ['asset: no source recorded (unknown)']}
```

### an.library.rights.sources_in(doc, , store, source=None, files=None)

Every labelled source one version holds: the asset’s, the descriptor’s, each part’s.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]]

store: the project store this kind of document lives in (`characters`,
: `props`, `environments`, `sounds`) — its sources are read by
  `an credits`’ own walk; `None` reads the top-level `source` alone

source: a source declared for the asset as a whole (at publish, or carried
: from an earlier version). It is a contributor BESIDE the descriptor’s
  own source, never instead of it: the roll-up takes the most
  restrictive, so a declared `cc0` cannot mask a descriptor that says
  the art came from a film. The only way to relax a stricter source is
  an explicit, recorded relicence ([`an.library.api.publish()`](an.library.api.html.md#an.library.api.publish)’s
  `relicense`), which bypasses this function altogether

files: `{path: sha256}` of the asset’s files. With them, a factory stamp
: is checked against the bytes it pins (`an.credits._part_credits()`):
  a re-carved part under a stale stamp, or a file the factory’s
  descriptor stamp does not pin, is `unknown` unless a source covers it

With no source anywhere the asset contributes `None`: `unknown`.

```pycon
>>> private = {"provider": "film", "license": "all-rights-reserved"}
>>> [label for label, _ in sources_in({"source": private}, store=None,
...                                   source=AssetSource(provider="me", license="cc0-1.0"))]
['asset', 'descriptor']
```
