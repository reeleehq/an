"""Where a third-party asset came from, and what its licence obliges.

`an` composes work it did not create — avatar art from a generator, stock images,
fonts, commissioned SVG — into a video its user ships. A licence defect is the
only failure in this package that reaches *backwards* through completed work: a
video shipped with an unattributed CC BY asset cannot be un-shipped, whereas
every rendering bug can be fixed forward.

Until now there was nowhere to record any of it. The character descriptor's
`metadata` dict carried a comment saying it *could* hold a licence; nothing ever
put one there.

## Why the field names look borrowed

They are. The rights fields are spelled exactly as `illustration.ImageResult`
spells them — `license`, `license_url`, `attribution`, `source_page_url`,
`author`, `author_url`, `cacheable`, `provider`, `id`, `url` — because
`illustration` is the federation's image-retrieval package and its results are
the most likely thing to become an `AssetSource`. Identical names mean the
adapter is a dict copy rather than a rename table, and a rename table is where a
field quietly stops being carried.

`tests/` pins this literally. That is the precedent `artful` already set for
shared vocabulary across packages that must not depend on each other.

Two fields are `an`'s own, because `ImageResult` has no equivalent:

- `sha256` — the digest of the bytes as they entered the project. A licence
  attached to a URL is a licence attached to whatever that URL serves *today*;
  attached to a digest, it stays attached to the thing that was actually used.
- `cost_usd` — what acquiring it cost, if anything. **`None` means unknown, never
  free.** That is the federation's rule for costs and it matters here for the
  same reason it matters in a plan: a `0.0` that means "we did not check" reads
  as "this was free" to every consumer downstream.

## The long-term home

This is a local definition of something three packages need — `illustration`
retrieves third-party images, `an` composes them, `reelee` ships the result — and
that is the signature of a missing federation primitive rather than three missing
local fields. It is proposed upstream as `lacing.Artifact.rights` (lacing#34).
`Artifact` is frozen and holds real deployed data, so that change needs a
registered migration and a coordinated release; until it lands, this mirror is
what keeps `an` from shipping unattributed work in the meantime.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AssetSource",
    "ATTRIBUTION_REQUIRING_LICENSES",
    "NONCOMMERCIAL_LICENSES",
    "NONCOMMERCIAL_RESTRICTION",
    "LicenseClass",
    "PRIVATE_STUDY",
    "PUBLIC_DOMAIN",
    "PROVIDER_TERMS",
    "PROVIDER_TERMS_RESTRICTIONS",
    "provider_terms_restriction",
    "license_class",
    "license_restriction",
    "normalise_license",
    "requires_attribution",
]

#: The recognised code for material its owner has not licensed at all — frames
#: or art carved out of a film, a show, a book — that a user may study
#: privately but must not publish (an#211). Any code that normalises to one
#: starting with ``all-rights-reserved`` or ``private-study`` is this class,
#: so ``"All rights reserved - private study only"`` is recognised too.
PRIVATE_STUDY: str = "all-rights-reserved-private-study"

#: The recognised code for the public domain — no rights to clear, nothing
#: owed (an#211). ``pd``, ``pd-us``, ``pdm-1.0``, ``public-domain``,
#: ``cc-pdm-1.0`` and ``cc0-*`` are all this class.
PUBLIC_DOMAIN: str = "public-domain"

#: What a licence means for shipping the video it ends up in.
#:
#: - ``attribution`` — shippable, with a credit that MUST be displayed;
#: - ``free`` — shippable, nothing owed (public domain, CC0, MIT-shaped);
#: - ``noncommercial`` — shippable in a personal or private video, with its
#:   credit displayed, but NOT for commercial use (a monetised, sponsored or
#:   client video): CC BY-NC and its variants, the ElevenLabs free plan (an#373);
#: - ``private`` — NOT shippable: all rights reserved, private study only;
#: - ``unknown`` — not classified, which is not the same as free.
LicenseClass = Literal["attribution", "free", "noncommercial", "private", "unknown"]

#: Licences of what a provider SYNTHESIZES for you, under the provider's own
#: terms (an#307): the ``source.license`` a voice document declares for the
#: speech that provider made, by provider. A code counts only on a source
#: whose ``provider`` is that provider — another provider's terms say nothing
#: about it — and is matched as whole leading words (``elevenlabs-paid-plan``,
#: ``elevenlabs-paid-plan-creator``). Which one applies is the user's account,
#: which ``an`` cannot see: declaring it is the user's statement.
#:
#: - ElevenLabs: on a paid plan the output may be used commercially with no
#:   credit (``free``). On the free plan it must credit ElevenLabs AND is for
#:   non-commercial use only: ``noncommercial`` (an#373, the maintainer's
#:   decision of 2026-10-09: one class for it and CC BY-NC), with its
#:   restriction named (:data:`PROVIDER_TERMS_RESTRICTIONS`) wherever it is
#:   listed. Check the current terms before shipping.
#: - Stability AI (Stable Audio Open and the other community models): under the
#:   Stability AI Community License (read 2026-10-06 at
#:   stability.ai/community-license-agreement, last updated 2024-07-05) "You
#:   own any outputs generated from the Models", no notice is owed for outputs,
#:   and the licence terminates once the user (with affiliates) makes more than
#:   USD 1,000,000 in annual revenue; outputs must follow Stability's acceptable
#:   use policy. So ``free``, with that cap named wherever it is listed (an#332).
_STABILITY_TERMS: dict[str, LicenseClass] = {"stability-community": "free"}
PROVIDER_TERMS: dict[str, dict[str, LicenseClass]] = {
    "elevenlabs": {
        "elevenlabs-paid-plan": "free",
        "elevenlabs-free-plan": "noncommercial",
    },
    # The names a Stable Audio output's source is recorded under.
    "stability": _STABILITY_TERMS,
    "stability-ai": _STABILITY_TERMS,
    "stable-audio": _STABILITY_TERMS,
}
#: What a provider-terms code restricts beyond its class, by code: the words a
#: credits report prints beside it.
PROVIDER_TERMS_RESTRICTIONS: dict[str, str] = {
    "elevenlabs-free-plan": "ElevenLabs free plan: non-commercial use only, and "
    "the video must credit ElevenLabs (elevenlabs.io)",
    "stability-community": "Stability AI Community License: the licence ends once "
    "you (with affiliates) make over USD 1,000,000 a year (then an Enterprise "
    "licence is needed), and use must follow Stability's acceptable use policy",
}


def provider_terms_restriction(source: AssetSource) -> str | None:
    """The restriction a provider-terms licence carries beyond its class, if any.

    >>> provider_terms_restriction(AssetSource(provider="elevenlabs", license="elevenlabs-free-plan"))[:21]
    'ElevenLabs free plan:'
    >>> provider_terms_restriction(AssetSource(provider="openai", license="elevenlabs-free-plan")) is None
    True
    """
    code = normalise_license(source.license or "")
    terms = PROVIDER_TERMS.get((source.provider or "").strip().lower(), {})
    for term in terms:
        if (code == term or code.startswith(term + "-")) and (
            term in PROVIDER_TERMS_RESTRICTIONS
        ):
            return PROVIDER_TERMS_RESTRICTIONS[term]
    return None


#: Normalised phrases that mean "all rights reserved" ANYWHERE in the code —
#: "(c) Studio. All rights reserved" is the usual way it is written.
_PRIVATE_PHRASES: tuple[str, ...] = ("all-rights-reserved", "private-study")
#: …and whole normalised codes that mean it.
_PRIVATE_EXACT: frozenset[str] = frozenset({"arr"})

#: Normalised codes that mean "no rights to clear", matched as whole leading
#: WORDS (``code == w`` or ``code.startswith(w + "-")``), never as bare string
#: prefixes — ``mitigated`` is not MIT.
_FREE_WORDS: tuple[str, ...] = (
    "cc0",
    "pd",
    "pdm",
    "publicdomain",
    "public-domain",
    "cc-pdm",
    "mit",
    "apache",
    "bsd",
)

#: Licence codes that oblige the *user of the output* to credit someone.
#:
#: Matched case-insensitively against the licence code. Deliberately a small,
#: explicit set rather than a pattern: "does this oblige me" is a question with
#: a legal answer, and a regex that guesses is worse than a list that admits what
#: it does not know. An unrecognised licence is reported as UNKNOWN, which is
#: not the same as "no obligation".
ATTRIBUTION_REQUIRING_LICENSES: frozenset[str] = frozenset(
    {
        "cc-by-4.0",
        "cc-by",
        "by",
        "cc-by-sa-4.0",
        "cc-by-sa",
        "by-sa",
        "cc-by-nd",
    }
)
#: Licence codes for NON-COMMERCIAL use only, each owing a credit too (an#373):
#: Creative Commons' NC family. Matched like :data:`ATTRIBUTION_REQUIRING_LICENSES`
#: (a trailing version counts as its family: ``cc-by-nc-sa-4.0``).
NONCOMMERCIAL_LICENSES: frozenset[str] = frozenset(
    {
        "cc-by-nc",
        "by-nc",
        "cc-by-nc-sa",
        "by-nc-sa",
        "cc-by-nc-nd",
        "by-nc-nd",
    }
)
#: What a ``noncommercial`` licence restricts, printed wherever one is listed
#: (a provider's own terms say it in their own words instead).
NONCOMMERCIAL_RESTRICTION: str = (
    "non-commercial use only (no monetised, sponsored or client video); credit owed"
)
#: A licence version at the end of a code (``cc-by-nc-4.0``, ``cc-by-3.0``): a
#: code is attribution-requiring when the code without it is listed (an#332).
_LICENSE_VERSION_RE = re.compile(r"-\d+(?:\.\d+)*$")


class AssetSource(BaseModel):
    """Provenance and rights for one third-party asset.

    >>> s = AssetSource(provider="dicebear", id="lorelei/amy", license="cc0-1.0")
    >>> requires_attribution(s)
    False
    >>> s = AssetSource(provider="dicebear", id="adventurer/amy", license="cc-by-4.0")
    >>> requires_attribution(s)
    True
    """

    model_config = ConfigDict(extra="allow")

    # --- identity. Names match illustration.ImageResult exactly.
    provider: str = Field(description="Where it came from, e.g. 'dicebear'.")
    id: str | None = Field(default=None, description="Provider-native identifier.")
    url: str | None = Field(default=None, description="Where it was fetched from.")

    # --- rights. Names match illustration.ImageResult exactly.
    license: str | None = Field(
        default=None,
        description="Licence code, e.g. 'cc0-1.0'. None means UNKNOWN, not unencumbered.",
    )
    license_url: str | None = None
    attribution: str | None = Field(
        default=None, description="Ready-to-render attribution sentence."
    )
    source_page_url: str | None = None
    author: str | None = None
    author_url: str | None = None
    #: Whether the terms let the bytes be KEPT (stored, cached): ``False`` —
    #: they do not (the Freesound API keeps every sound by reference), and no
    #: store takes them; ``None`` — not recorded, which is not a yes (an#332,
    #: as ``lacing.Rights``); ``True`` — they do.
    cacheable: bool | None = None

    # --- an's own.
    sha256: str | None = Field(
        default=None,
        description="Digest of the bytes as they entered the project.",
    )
    cost_usd: float | None = Field(
        default=None,
        description="Acquisition cost. None means UNKNOWN — never free.",
    )
    extra: dict[str, Any] = Field(default_factory=dict)


def normalise_license(code: str) -> str:
    """A licence code folded to lowercase words joined by ``-``.

    Free text is what people actually write in a licence field, so the
    classifier reads through punctuation and spacing:

    >>> normalise_license("All rights reserved - private study only; never publish")
    'all-rights-reserved-private-study-only-never-publish'
    >>> normalise_license(" CC-BY-4.0 ")
    'cc-by-4-0'
    """
    return "-".join(re.findall(r"[a-z0-9]+", code.lower()))


def license_class(source: AssetSource) -> LicenseClass:
    """What this asset's licence means for shipping the video (an#211).

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

    A provider's terms count for what that provider made (:data:`PROVIDER_TERMS`):

    >>> license_class(AssetSource(provider="elevenlabs", license="elevenlabs-paid-plan"))
    'free'
    >>> license_class(AssetSource(provider="openai", license="elevenlabs-paid-plan"))
    'unknown'
    """
    if not source.license:
        return "unknown"
    raw = source.license.strip().lower()
    if (
        raw in NONCOMMERCIAL_LICENSES
        or _LICENSE_VERSION_RE.sub("", raw) in NONCOMMERCIAL_LICENSES
    ):
        return "noncommercial"
    if (
        raw in ATTRIBUTION_REQUIRING_LICENSES
        or _LICENSE_VERSION_RE.sub("", raw) in ATTRIBUTION_REQUIRING_LICENSES
    ):
        return "attribution"
    code = normalise_license(raw)
    if code in _PRIVATE_EXACT or any(p in code for p in _PRIVATE_PHRASES):
        return "private"
    terms = PROVIDER_TERMS.get((source.provider or "").strip().lower(), {})
    for term, cls in terms.items():
        if code == term or code.startswith(term + "-"):
            return cls
    if any(code == w or code.startswith(w + "-") for w in _FREE_WORDS):
        return "free"
    return "unknown"


def requires_attribution(source: AssetSource) -> bool | None:
    """Whether shipping this asset obliges the user to credit someone.

    Returns ``None`` for an unrecognised or absent licence: "we do not know" is a
    distinct answer from "no", and collapsing them is how an obligation gets
    silently dropped. Private-study material (all rights reserved) also answers
    ``None`` here — the question is not whom to credit but that it may not ship
    at all; :func:`license_class` says so (``"private"``).
    """
    return {"attribution": True, "noncommercial": True, "free": False}.get(
        license_class(source)
    )


def license_restriction(source: AssetSource) -> str | None:
    """What a licence restricts beyond its class's credit, for a report line (an#373).

    >>> license_restriction(AssetSource(provider="freesound", license="cc-by-nc-4.0"))[:24]
    'non-commercial use only '
    >>> license_restriction(AssetSource(provider="p", license="cc-by-4.0")) is None
    True
    """
    terms = provider_terms_restriction(source)
    if terms is not None:
        return terms
    return NONCOMMERCIAL_RESTRICTION if license_class(source) == "noncommercial" else None
