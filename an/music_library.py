"""Acquire a licensed music library, with provenance: an's bridge to foley (an#470, an#656).

The library itself lives in foley (:mod:`foley.sources.music_library`): the
registry (``incompetech``, and the paid ``artlist`` and ``epidemic_sound``,
whose titles become wishlist rows), the direct and Wayback mirrors, the polite
fetch with ``429`` / ``Retry-After`` resilience, the audio probe, the licence
gate, the tracks table and the credit parser. ``an music add-library``
(:mod:`an.music_cli`) is its command:

    an music add-library incompetech --titles-from usage.json --out audio/macleod

What stays here is what is an's:

- :func:`asset_source`, the bridge: one foley row (an
  :class:`~foley.sources.music_library.AcquiredTrack`, or its ``.row()`` read
  back from a tracks table) as an :class:`an.ir.assets.AssetSource`, the
  provenance a sound in the project's store carries. foley's licence ids become
  an's codes (:func:`license_code`: ``CC-BY-4.0`` is ``cc-by-4.0``; foley's
  ``unknown``, a paid library's, is ``None``, which an reads as UNKNOWN); the
  library's own address is ``source_page_url``; ``rights_verified``, the mirror
  and a titles file's metadata ride as extras.
- :func:`acquire`, foley's with an's ``pause`` knob (seconds before a second
  request to one host), which becomes foley's per-host ``rate``.

The rest of foley's surface the command and its tests use (:data:`MUSIC_LIBRARIES`,
:func:`tracks_table`, :func:`attribution_text`, :func:`titles_by_library`, ...) is
re-exported by name, and loaded on first use: ``import an`` never imports foley.

>>> license_code("CC-BY-4.0"), license_code("unknown")
('cc-by-4.0', None)
>>> src = asset_source({"title": "Sneaky Snitch", "library": "incompetech",
...                     "status": "acquired", "license": "CC-BY-4.0",
...                     "source_page_url": "https://incompetech.com/x.mp3",
...                     "rights_verified": True, "mirror": "wayback"})
>>> src.provider, src.id, src.license, src.source_page_url
('incompetech', 'Sneaky Snitch', 'cc-by-4.0', 'https://incompetech.com/x.mp3')
>>> src.model_extra
{'rights_verified': True, 'mirror': 'wayback'}
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from an.ir.assets import AssetSource

if TYPE_CHECKING:  # foley loads on first use, never with `import an`
    from foley.sources.music_library import AcquiredTrack

__all__ = [
    "ACQUIRED",
    "DFLT_PAUSE_S",
    "FAILED",
    "FOLEY_LICENSE_CODES",
    "KEPT",
    "MUSIC_LIBRARIES",
    "REFUSED",
    "WISHLIST",
    "AcquiredTrack",
    "MusicLibrary",
    "MusicLibraryError",
    "MusicToolMissing",
    "acquire",
    "asset_source",
    "attribution_text",
    "files_store",
    "kept_digests",
    "kept_sources",
    "license_code",
    "probe_verify",
    "register_music_library",
    "titles_by_library",
    "titles_from_json",
    "tracks_table",
    "wayback",
]

#: Where the music library lives.
FOLEY_MODULE: str = "foley.sources.music_library"
#: foley's names an re-exports, loaded from :data:`FOLEY_MODULE` on first use.
FOLEY_NAMES: frozenset[str] = frozenset(
    {
        "ACQUIRED",
        "FAILED",
        "KEPT",
        "MUSIC_LIBRARIES",
        "REFUSED",
        "WISHLIST",
        "AcquiredTrack",
        "MusicLibrary",
        "MusicLibraryError",
        "MusicToolMissing",
        "attribution_text",
        "files_store",
        "kept_digests",
        "kept_sources",
        "probe_verify",
        "register_music_library",
        "titles_by_library",
        "titles_from_json",
        "tracks_table",
        "wayback",
    }
)
#: Seconds before a second request to one host (foley's default pace: a library
#: is someone's website).
DFLT_PAUSE_S: float = 2.0
SECONDS_PER_MINUTE: float = 60.0
#: foley licence ids whose an code is not the id in lowercase: ``unknown`` (a paid
#: library claims no rights) is ``None``, an's UNKNOWN.
FOLEY_LICENSE_CODES: Mapping[str, str | None] = {"unknown": None}
#: The row columns that describe the acquisition, not the asset: they stay in the
#: tracks table. ``title`` and ``library`` become ``id`` and ``provider``.
ROW_ONLY: frozenset[str] = frozenset({"status", "file", "duration_s", "error"})
#: The licence flags a row carries: a tracks table read back from CSV gives them as
#: ``"True"`` / ``"False"``, which :func:`asset_source` makes booleans again.
FLAG_COLUMNS: frozenset[str] = frozenset({"rights_verified", "commercial_ok"})
#: How a CSV cell spells a flag.
CSV_BOOLEANS: Mapping[str, bool] = {"True": True, "False": False}
#: Row columns an :class:`AssetSource` field of the same name takes as is.
SAME_NAME: tuple[str, ...] = (
    "url",
    "license_url",
    "author",
    "source_page_url",
    "attribution",
    "sha256",
)


def __getattr__(name: str) -> Any:
    """foley's re-exported names (:data:`FOLEY_NAMES`), imported on first use."""
    if name in FOLEY_NAMES:
        return getattr(importlib.import_module(FOLEY_MODULE), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | FOLEY_NAMES)


def license_code(
    license_id: str | None,
    *,
    codes: Mapping[str, str | None] = FOLEY_LICENSE_CODES,
) -> str | None:
    """foley's licence id as an's code: ``codes`` first, else the id in lowercase.

    >>> license_code("CC0-1.0"), license_code("unknown"), license_code(None)
    ('cc0-1.0', None, None)
    """
    if not license_id:
        return None
    if license_id in codes:
        return codes[license_id]
    return license_id.lower()


def asset_source(
    track: AcquiredTrack | Mapping[str, Any],
    *,
    codes: Mapping[str, str | None] = FOLEY_LICENSE_CODES,
) -> AssetSource:
    """One foley row as an's :class:`~an.ir.assets.AssetSource`.

    ``track`` is a foley ``AcquiredTrack`` or its ``.row()`` (as a tracks table
    reads back). ``library`` is the ``provider``, ``title`` the ``id``, the
    licence id an's code (:func:`license_code`); ``url`` (the mirror that served
    the bytes), ``source_page_url`` (the library's own address), the licence URL,
    author, attribution and ``sha256`` keep their names. The acquisition's own
    columns (:data:`ROW_ONLY`) stay in the table; every other column
    (``rights_verified``, ``commercial_ok``, ``mirror``, ``credited_by``, a titles
    file's metadata) rides as an extra; a licence flag read back from CSV
    (:data:`FLAG_COLUMNS`) is a boolean again. Empty cells are dropped. A track also
    gives its licence's ``creator_url`` as ``author_url`` and whether its terms let
    the bytes be kept as ``cacheable``.
    """
    row = dict(track) if isinstance(track, Mapping) else track.row()
    for k in FLAG_COLUMNS & row.keys():
        row[k] = CSV_BOOLEANS.get(row[k], row[k])
    fields: dict[str, Any] = {}
    if not isinstance(track, Mapping):
        fields["author_url"] = track.license.creator_url
        fields["cacheable"] = track.license.cache_bytes_ok
    rest = {
        k: v
        for k, v in row.items()
        if k not in {"title", "library", "license", *SAME_NAME, *ROW_ONLY}
    }
    fields.update({k: row.get(k) for k in SAME_NAME}, **rest)
    return AssetSource(
        provider=row["library"],
        id=row["title"],
        license=license_code(row.get("license"), codes=codes),
        **{k: v for k, v in fields.items() if v is not None and v != ""},
    )


def acquire(
    library: Any,
    titles: Any,
    *,
    out: Any,
    pause: float = DFLT_PAUSE_S,
    config: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> list[AcquiredTrack]:
    """foley's :func:`~foley.sources.music_library.acquire`, paced by ``pause``.

    ``pause`` is the seconds before a second request to one host (``0``: no
    pause), foley's ``rate`` unless ``config`` states its own. ``config`` and every
    other keyword (``fetch``, ``mirrors``, ``verify``, ``kept``, ``intended_use``,
    ``clock``, ``sleep``, ...) go to foley as they are. Bridge the rows with
    :func:`asset_source`.

    Raises:
        MusicLibraryError: For a negative ``pause``, and whatever foley's
            ``acquire`` refuses.
    """
    from foley.sources.music_library import MusicLibraryError
    from foley.sources.music_library import acquire as foley_acquire

    if pause < 0:
        raise MusicLibraryError(f"pause is seconds, at least 0; got {pause}")
    config = dict(config or {})
    if "rate" not in config:
        config["rate"] = {"per_min": SECONDS_PER_MINUTE / pause} if pause else {}
    return foley_acquire(library, titles, out=out, config=config, **kwargs)
