# an.ir.assets

Where a third-party asset came from, and what its licence obliges.

`an` composes work it did not create — avatar art from a generator, stock images,
fonts, commissioned SVG — into a video its user ships. A licence defect is the
only failure in this package that reaches *backwards* through completed work: a
video shipped with an unattributed CC BY asset cannot be un-shipped, whereas
every rendering bug can be fixed forward.

Until now there was nowhere to record any of it. The character descriptor’s
`metadata` dict carried a comment saying it *could* hold a licence; nothing ever
put one there.

### Why the field names look borrowed

They are. The rights fields are spelled exactly as `illustration.ImageResult`
spells them — `license`, `license_url`, `attribution`, `source_page_url`,
`author`, `author_url`, `cacheable`, `provider`, `id`, `url` — because
`illustration` is the federation’s image-retrieval package and its results are
the most likely thing to become an `AssetSource`. Identical names mean the
adapter is a dict copy rather than a rename table, and a rename table is where a
field quietly stops being carried.

`tests/` pins this literally. That is the precedent `artful` already set for
shared vocabulary across packages that must not depend on each other.

Two fields are `an`’s own, because `ImageResult` has no equivalent:

- `sha256` — the digest of the bytes as they entered the project. A licence
  attached to a URL is a licence attached to whatever that URL serves *today*;
  attached to a digest, it stays attached to the thing that was actually used.
- `cost_usd` — what acquiring it cost, if anything. **\`None\` means unknown, never
  free.** That is the federation’s rule for costs and it matters here for the
  same reason it matters in a plan: a `0.0` that means “we did not check” reads
  as “this was free” to every consumer downstream.

### The long-term home

This is a local definition of something three packages need — `illustration`
retrieves third-party images, `an` composes them, `reelee` ships the result — and
that is the signature of a missing federation primitive rather than three missing
local fields. It is proposed upstream as `lacing.Artifact.rights` (lacing#34).
`Artifact` is frozen and holds real deployed data, so that change needs a
registered migration and a coordinated release; until it lands, this mirror is
what keeps `an` from shipping unattributed work in the meantime.

### Module Attributes

| [`PRIVATE_STUDY`](#an.ir.assets.PRIVATE_STUDY)                  | The recognised code for material its owner has not licensed at all — frames or art carved out of a film, a show, a book — that a user may study privately but must not publish (an#211).   |
|---------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`PUBLIC_DOMAIN`](#an.ir.assets.PUBLIC_DOMAIN)                  | The recognised code for the public domain — no rights to clear, nothing owed (an#211).                                                                                                     |
| [`LicenseClass`](#an.ir.assets.LicenseClass)                   | What a licence means for shipping the video it ends up in.                                                                                                                                 |
| [`PROVIDER_TERMS_RESTRICTIONS`](#an.ir.assets.PROVIDER_TERMS_RESTRICTIONS)    | the words a credits report prints beside it.                                                                                                                                               |
| [`ATTRIBUTION_REQUIRING_LICENSES`](#an.ir.assets.ATTRIBUTION_REQUIRING_LICENSES) | Licence codes that oblige the *user of the output* to credit someone.                                                                                                                      |
| [`NONCOMMERCIAL_LICENSES`](#an.ir.assets.NONCOMMERCIAL_LICENSES)         | Licence codes for NON-COMMERCIAL use only, each owing a credit too (an#373): Creative Commons' NC family.                                                                                  |
| [`NONCOMMERCIAL_RESTRICTION`](#an.ir.assets.NONCOMMERCIAL_RESTRICTION)      | What a `noncommercial` licence restricts, printed wherever one is listed (a provider's own terms say it in their own words instead).                                                       |

### Functions

| [`provider_terms_restriction`](#an.ir.assets.provider_terms_restriction)(source)   | The restriction a provider-terms licence carries beyond its class, if any.      |
|---------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`license_class`](#an.ir.assets.license_class)(source)                | What this asset's licence means for shipping the video (an#211).                |
| [`license_restriction`](#an.ir.assets.license_restriction)(source)          | What a licence restricts beyond its class's credit, for a report line (an#373). |
| [`normalise_license`](#an.ir.assets.normalise_license)(code)              | A licence code folded to lowercase words joined by `-`.                         |
| [`requires_attribution`](#an.ir.assets.requires_attribution)(source)         | Whether shipping this asset obliges the user to credit someone.                 |

### Classes

| [`AssetSource`](#an.ir.assets.AssetSource)(\*\*data)   | Provenance and rights for one third-party asset.   |
|--------------------------------------------------------------------------|----------------------------------------------------|

### an.ir.assets.ATTRIBUTION_REQUIRING_LICENSES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'by', 'by-sa', 'cc-by', 'cc-by-4.0', 'cc-by-nd', 'cc-by-sa', 'cc-by-sa-4.0'})*

Licence codes that oblige the *user of the output* to credit someone.

Matched case-insensitively against the licence code. Deliberately a small,
explicit set rather than a pattern: “does this oblige me” is a question with
a legal answer, and a regex that guesses is worse than a list that admits what
it does not know. An unrecognised licence is reported as UNKNOWN, which is
not the same as “no obligation”.

### *class* an.ir.assets.AssetSource(\*\*data)

Bases: `BaseModel`

Provenance and rights for one third-party asset.

```pycon
>>> s = AssetSource(provider="dicebear", id="lorelei/amy", license="cc0-1.0")
>>> requires_attribution(s)
False
>>> s = AssetSource(provider="dicebear", id="adventurer/amy", license="cc-by-4.0")
>>> requires_attribution(s)
True
```

#### cacheable *: [bool](https://docs.python.org/3/builtins/functions.html#bool) | [None](https://docs.python.org/3/builtins/constants.html#None)*

`False` —
they do not (the Freesound API keeps every sound by reference), and no
store takes them; `None` — not recorded, which is not a yes (an#332,
as `lacing.Rights`); `True` — they do.

* **Type:**
  Whether the terms let the bytes be KEPT (stored, cached)

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.assets.LicenseClass

What a licence means for shipping the video it ends up in.

- `attribution` — shippable, with a credit that MUST be displayed;
- `free` — shippable, nothing owed (public domain, CC0, MIT-shaped);
- `noncommercial` — shippable in a personal or private video, with its
  credit displayed, but NOT for commercial use (a monetised, sponsored or
  client video): CC BY-NC and its variants, the ElevenLabs free plan (an#373);
- `private` — NOT shippable: all rights reserved, private study only;
- `unknown` — not classified, which is not the same as free.

alias of [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[‘attribution’, ‘free’, ‘noncommercial’, ‘private’, ‘unknown’]

### an.ir.assets.NONCOMMERCIAL_LICENSES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'by-nc', 'by-nc-nd', 'by-nc-sa', 'cc-by-nc', 'cc-by-nc-nd', 'cc-by-nc-sa'})*

Licence codes for NON-COMMERCIAL use only, each owing a credit too (an#373):
Creative Commons’ NC family. Matched like [`ATTRIBUTION_REQUIRING_LICENSES`](#an.ir.assets.ATTRIBUTION_REQUIRING_LICENSES)
(a trailing version counts as its family: `cc-by-nc-sa-4.0`).

### an.ir.assets.NONCOMMERCIAL_RESTRICTION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'non-commercial use only (no monetised, sponsored or client video); credit owed'*

What a `noncommercial` licence restricts, printed wherever one is listed
(a provider’s own terms say it in their own words instead).

### an.ir.assets.PRIVATE_STUDY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'all-rights-reserved-private-study'*

The recognised code for material its owner has not licensed at all — frames
or art carved out of a film, a show, a book — that a user may study
privately but must not publish (an#211). Any code that normalises to one
starting with `all-rights-reserved` or `private-study` is this class,
so `"All rights reserved - private study only"` is recognised too.

### an.ir.assets.PROVIDER_TERMS_RESTRICTIONS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'elevenlabs-free-plan': 'ElevenLabs free plan: non-commercial use only, and the video must credit ElevenLabs (elevenlabs.io)', 'stability-community': "Stability AI Community License: the licence ends once you (with affiliates) make over USD 1,000,000 a year (then an Enterprise licence is needed), and use must follow Stability's acceptable use policy"}*

the words a
credits report prints beside it.

* **Type:**
  What a provider-terms code restricts beyond its class, by code

### an.ir.assets.PUBLIC_DOMAIN *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'public-domain'*

The recognised code for the public domain — no rights to clear, nothing
owed (an#211). `pd`, `pd-us`, `pdm-1.0`, `public-domain`,
`cc-pdm-1.0` and `cc0-*` are all this class.

### an.ir.assets.license_class(source)

What this asset’s licence means for shipping the video (an#211).

* **Return type:**
  [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'attribution'`, `'free'`, `'noncommercial'`, `'private'`, `'unknown'`]

```pycon
>>> license_class(AssetSource(provider="p", license="pd"))
'free'
>>> license_class(AssetSource(provider="p", license="all-rights-reserved"))
'private'
>>> license_class(AssetSource(provider="p", license="cc-by-4.0"))
'attribution'
>>> license_class(AssetSource(provider="freesound", license="cc-by-nc-4.0"))
'noncommercial'
>>> license_class(AssetSource(provider="p", license="bespoke"))
'unknown'
```

A provider’s terms count for what that provider made (`PROVIDER_TERMS`):

```pycon
>>> license_class(AssetSource(provider="elevenlabs", license="elevenlabs-paid-plan"))
'free'
>>> license_class(AssetSource(provider="openai", license="elevenlabs-paid-plan"))
'unknown'
```

### an.ir.assets.license_restriction(source)

What a licence restricts beyond its class’s credit, for a report line (an#373).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> license_restriction(AssetSource(provider="freesound", license="cc-by-nc-4.0"))[:24]
'non-commercial use only '
>>> license_restriction(AssetSource(provider="p", license="cc-by-4.0")) is None
True
```

### an.ir.assets.normalise_license(code)

A licence code folded to lowercase words joined by `-`.

Free text is what people actually write in a licence field, so the
classifier reads through punctuation and spacing:

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> normalise_license("All rights reserved - private study only; never publish")
'all-rights-reserved-private-study-only-never-publish'
>>> normalise_license(" CC-BY-4.0 ")
'cc-by-4-0'
```

### an.ir.assets.provider_terms_restriction(source)

The restriction a provider-terms licence carries beyond its class, if any.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> provider_terms_restriction(AssetSource(provider="elevenlabs", license="elevenlabs-free-plan"))[:21]
'ElevenLabs free plan:'
>>> provider_terms_restriction(AssetSource(provider="openai", license="elevenlabs-free-plan")) is None
True
```

### an.ir.assets.requires_attribution(source)

Whether shipping this asset obliges the user to credit someone.

Returns `None` for an unrecognised or absent licence: “we do not know” is a
distinct answer from “no”, and collapsing them is how an obligation gets
silently dropped. Private-study material (all rights reserved) also answers
`None` here — the question is not whom to credit but that it may not ship
at all; [`license_class()`](#an.ir.assets.license_class) says so (`"private"`).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
