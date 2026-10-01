"""Asset kinds: the ``kind`` facet's vocabulary, and where each kind lives in a project.

An asset id's prefix is its kind (``character.alice``). A kind says two things the
library needs for check-out and for publishing from a folder: which project
store holds it (``characters``) and what its descriptor file is called inside a
folder (``character.json``). Kinds with no project store yet (``motion``,
``reference``, ``plane``) can be published and found, not checked out.

Genre packages register their kinds on import (ADR 0005 decision 12); the
built-ins below are the kinds ``an``'s project mall already stores, plus the ones
the design names.

>>> asset_kind_info("character").store
'characters'
>>> asset_kind_info("motion").store is None
True
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ASSET_KINDS",
    "AssetKind",
    "UnknownKindError",
    "asset_kind_info",
    "register_asset_kind",
]


class UnknownKindError(ValueError):
    """An asset id whose kind prefix nobody registered."""


@dataclass(frozen=True)
class AssetKind:
    """One asset kind: its project store and its descriptor file name in a folder.

    ``descriptor`` is ``None`` for kinds whose project store keeps one JSON
    document per key with no folder (voices, styles): such an asset has no files.
    """

    name: str
    store: str | None
    descriptor: str | None
    #: The ``an credits`` store name its sources are read under (rights roll-up);
    #: ``None`` reads the top-level ``source`` only.
    credits_store: str | None = None


#: Registered asset kinds, by name.
ASSET_KINDS: dict[str, AssetKind] = {}


def register_asset_kind(
    name: str,
    *,
    store: str | None = None,
    descriptor: str | None = None,
    credits_store: str | None = None,
) -> AssetKind:
    """Register (or re-register) an asset kind. Returns it."""
    kind = AssetKind(name, store, descriptor, credits_store)
    ASSET_KINDS[name] = kind
    return kind


def asset_kind_info(name: str) -> AssetKind:
    """The registered kind ``name``, or :class:`UnknownKindError` naming the known ones."""
    try:
        return ASSET_KINDS[name]
    except KeyError:
        raise UnknownKindError(
            f"asset kind {name!r} is not registered; known: {sorted(ASSET_KINDS)}. "
            "A genre package registers its kinds with register_asset_kind()."
        ) from None


register_asset_kind(
    "character",
    store="characters",
    descriptor="character.json",
    credits_store="characters",
)
register_asset_kind(
    "prop", store="props", descriptor="prop.json", credits_store="props"
)
register_asset_kind(
    "environment",
    store="environments",
    descriptor="meta.json",
    credits_store="environments",
)
register_asset_kind(
    "sound", store="sounds", descriptor="sound.json", credits_store="sounds"
)
register_asset_kind("style", store="styles")
register_asset_kind("voice", store="voices")
register_asset_kind("plane")
register_asset_kind("motion")
register_asset_kind("reference")
