"""Rights on every version: the most restrictive licence class wins (ADR 0005 decision 10, design §9).

The library adds no licence vocabulary. A version's rights are rolled up from
``an``'s existing model (an#211): :class:`~an.ir.assets.AssetSource` records and
:func:`~an.ir.assets.license_class`'s four classes. The roll-up reads them from

- the source declared for the asset as a whole at publish, AND the descriptor's
  own ``source`` — both, never one instead of the other (an asset with neither
  is ``unknown``: recorded and visible, never rejected);
- every part and plane that declares its own ``source`` — gathered by
  :func:`an.credits.collect_credits`, the same walk ``an credits`` runs, so the
  library and the credits report can never disagree about what an asset holds;
- every version it derives from (``derived_from``) and the version it follows
  (``previous``), recursively, by the same rules: a derivative inherits the
  obligations of its sources, and a new version cannot relabel the old one;
- the source any other version records for the same file bytes (by blob
  digest): a file's own recorded provenance travels with its bytes, so carved
  parts published again under a new id keep their obligations
  (:func:`an.library.api.version_sources` walks all of it).

A version may only ever be MORE restrictive than what it inherits. Relaxing
takes an explicit, recorded relicence — who and why — on the version. Where
nobody ever said anything (a file an earlier version recorded ``unlabelled``,
a version with no source), an explicit source with a recorded ``relabel`` —
who and why — is the first statement (an#263); it relaxes nothing anyone said.

Order, most restrictive first: ``private`` > ``unknown`` > ``attribution`` >
``free``. ``private`` and ``unknown`` are not publishable.

>>> from an.ir.assets import AssetSource
>>> r = roll_up([("asset", AssetSource(provider="p", license="cc0-1.0")),
...              ("parts/head.png", AssetSource(provider="film", license="all-rights-reserved"))])
>>> (r.license_class, r.publishable)
('private', False)
>>> r.reasons
['parts/head.png: all-rights-reserved (private)']
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from an.ir.assets import AssetSource, LicenseClass, license_class

__all__ = [
    "LICENSE_CLASS_ORDER",
    "PUBLISHABLE_CLASSES",
    "Rights",
    "RightsRefusal",
    "most_restrictive",
    "descriptor_source",
    "roll_up",
    "sources_in",
]

#: Licence classes, most restrictive first. The roll-up keeps the first that occurs.
LICENSE_CLASS_ORDER: tuple[LicenseClass, ...] = (
    "private",
    "unknown",
    "attribution",
    "free",
)
#: The classes a video may ship with (``attribution`` with its credit displayed).
PUBLISHABLE_CLASSES: frozenset[str] = frozenset({"free", "attribution"})
#: The label of a source declared for the asset as a whole (at publish), in reasons.
ASSET_SOURCE_LABEL: str = "asset"
#: The label of the source the descriptor itself declares, in reasons.
DESCRIPTOR_SOURCE_LABEL: str = "descriptor"


class RightsRefusal(PermissionError):
    """A private or unknown version would leave the user's library without an override."""


@dataclass(frozen=True)
class Rights:
    """The rolled-up rights of one version, as stored on it."""

    license_class: LicenseClass
    reasons: list[str] = field(default_factory=list)

    @property
    def publishable(self) -> bool:
        """Whether a video containing this asset may ship."""
        return self.license_class in PUBLISHABLE_CLASSES

    def to_dict(self) -> dict[str, Any]:
        """The ``rights`` block of a version document."""
        return {
            "license_class": self.license_class,
            "publishable": self.publishable,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Rights":
        """Read a version's ``rights`` block back."""
        return cls(d.get("license_class", "unknown"), list(d.get("reasons") or []))


def most_restrictive(classes: Iterable[str]) -> LicenseClass:
    """The most restrictive of ``classes``; ``free`` for none.

    >>> most_restrictive(["free", "attribution"]), most_restrictive([])
    ('attribution', 'free')
    """
    present = set(classes)
    return next((c for c in LICENSE_CLASS_ORDER if c in present), "free")


def _reason(label: str, source: AssetSource, cls: str) -> str:
    return f"{label}: {source.license or 'no licence recorded'} ({cls})"


def roll_up(
    sources: Iterable[tuple[str, AssetSource | None]],
    *,
    inherited: Iterable[tuple[str, Rights]] = (),
) -> Rights:
    """Roll labelled sources (and parents' rights) up to one :class:`Rights`.

    A ``None`` source is ``unknown``. The reasons name every contributor of the
    winning class, so a reader sees *why* a version is restricted.

    >>> roll_up([("asset", None)]).to_dict()
    {'license_class': 'unknown', 'publishable': False, 'reasons': ['asset: no source recorded (unknown)']}
    """
    contributions: list[tuple[str, str]] = []
    for label, source in sources:
        if source is None:
            contributions.append(("unknown", f"{label}: no source recorded (unknown)"))
        else:
            cls = license_class(source)
            contributions.append((cls, _reason(label, source, cls)))
    for label, rights in inherited:
        contributions.append(
            (
                rights.license_class,
                f"{label}: derived from a {rights.license_class} version",
            )
        )
    winner = most_restrictive(c for c, _ in contributions)
    reasons = [r for c, r in contributions if c == winner and winner != "free"]
    return Rights(winner, reasons)


def descriptor_source(
    doc: Mapping[str, Any], *, store: str | None
) -> AssetSource | None:
    """The source the descriptor itself declares (or ``an credits`` reconstructs), if any."""
    return dict(_descriptor_sources(doc, store=store)).get(DESCRIPTOR_SOURCE_LABEL)


class _OneEntry(dict):
    """A one-entry project store for the credits walk, knowing its files' digests."""

    def __init__(self, doc: Mapping[str, Any], files: Mapping[str, str] | None):
        super().__init__({"_": dict(doc)})
        self._files = files

    def file_digests(self, key: str) -> Mapping[str, str] | None:
        return self._files


def _descriptor_sources(
    doc: Mapping[str, Any],
    *,
    store: str | None,
    files: Mapping[str, str] | None = None,
    covering: AssetSource | None = None,
) -> list[tuple[str, AssetSource]]:
    """The descriptor's own source and each part's, as ``an credits`` reads them.

    files: ``{path: sha256}`` of the asset's files, so the factory's stamps are
        checked against the bytes they pin, exactly as in a project
    covering: the asset-level source declared at publish. A check-out writes it
        into a descriptor that declares none (nor any the credits walk
        reconstructs), so the parts are walked as they will read there — the
        library and the project's credits see the same document — but it is
        reported under its own label, never as the descriptor's.
    """
    from an.credits import collect_credits, gives_way_to_a_label

    key = "_"
    prefix = f"{store}/{key}"

    def walk(document: Mapping[str, Any]) -> list[Any]:
        if not store:
            return []
        return collect_credits({store: _OneEntry(document, files)}).entries

    entries = walk(doc)
    own = next((e.source for e in entries if e.asset == prefix), None)
    if own is None and isinstance(doc.get("source"), Mapping):
        own = AssetSource.model_validate(doc["source"])
    if covering is not None and (
        own is None or gives_way_to_a_label(doc.get("source"))
    ):
        # What the checked-out copy will hold (an.library.checkout): the
        # asset-level source written in as the descriptor's — in place of
        # nothing, or of a generator's own source that owes nothing (the
        # factory's stamp, a free DiceBear style: an#281), which speaks only for the bytes its part stamps
        # already pin — speaking for every part nothing itemises.
        walked = {
            **doc,
            "source": covering.model_dump(mode="json", exclude_defaults=True),
        }
        entries = walk(walked)
        own = None
    parts = [
        (e.asset[len(prefix) + 1 :], e.source) for e in entries if e.asset != prefix
    ]
    return ([(DESCRIPTOR_SOURCE_LABEL, own)] if own is not None else []) + parts


def sources_in(
    doc: Mapping[str, Any],
    *,
    store: str | None,
    source: AssetSource | None = None,
    files: Mapping[str, str] | None = None,
) -> list[tuple[str, AssetSource | None]]:
    """Every labelled source one version holds: the asset's, the descriptor's, each part's.

    store: the project store this kind of document lives in (``characters``,
        ``props``, ``environments``, ``sounds``) — its sources are read by
        ``an credits``' own walk; ``None`` reads the top-level ``source`` alone
    source: a source declared for the asset as a whole (at publish, or carried
        from an earlier version). It is a contributor BESIDE the descriptor's
        own source, never instead of it: the roll-up takes the most
        restrictive, so a declared ``cc0`` cannot mask a descriptor that says
        the art came from a film. The only way to relax a stricter source is
        an explicit, recorded relicence (:func:`an.library.api.publish`'s
        ``relicense``), which bypasses this function altogether
    files: ``{path: sha256}`` of the asset's files. With them, a factory stamp
        is checked against the bytes it pins (:func:`an.credits._part_credits`):
        a re-carved part under a stale stamp, or a file the factory's
        descriptor stamp does not pin, is ``unknown`` unless a source covers it

    With no source anywhere the asset contributes ``None``: ``unknown``.

    >>> private = {"provider": "film", "license": "all-rights-reserved"}
    >>> [label for label, _ in sources_in({"source": private}, store=None,
    ...                                   source=AssetSource(provider="me", license="cc0-1.0"))]
    ['asset', 'descriptor']
    """
    found = _descriptor_sources(doc, store=store, files=files, covering=source)
    own = dict(found).get(DESCRIPTOR_SOURCE_LABEL)
    parts = [(label, src) for label, src in found if label != DESCRIPTOR_SOURCE_LABEL]
    top: list[tuple[str, AssetSource | None]]
    if source is not None and own is not None:
        top = [(ASSET_SOURCE_LABEL, source), (DESCRIPTOR_SOURCE_LABEL, own)]
    elif source is not None:
        top = [(ASSET_SOURCE_LABEL, source)]
    elif own is not None:
        top = [(DESCRIPTOR_SOURCE_LABEL, own)]
    else:
        top = [(ASSET_SOURCE_LABEL, None)]
    return [*top, *parts]
