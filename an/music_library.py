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
  an's codes (:func:`license_code`, foley's own mapping,
  ``foley.licensing.consumer_license_code``: ``CC-BY-4.0`` is ``cc-by-4.0``;
  foley's ``unknown``, a paid library's, is ``None``, which an reads as UNKNOWN); the
  library's own address is ``source_page_url``; ``rights_verified``, the mirror
  and a titles file's metadata ride as extras.
- :func:`acquire`, foley's with an's ``pause`` knob (seconds before a second
  request to one host), which becomes foley's per-host ``rate``.
- :func:`add_track_to_sounds` (an#623): one acquired row's verified file, cut,
  into the project's sounds store with the row as its provenance, so a film
  uses the track without fetching it again (``an music use``).

The rest of foley's surface the command and its tests use (:data:`MUSIC_LIBRARIES`,
:func:`tracks_table`, :func:`attribution_text`, :func:`titles_by_library`, and the
tracks-table reader :func:`read_tracks_table` and :data:`LIST_SEPARATOR`, an#731) is re-exported by name, and loaded on first use:
``import an`` never imports foley.

>>> license_code("CC-BY-4.0"), license_code("unknown")
('cc-by-4.0', None)
>>> src = asset_source({"title": "Sneaky Snitch", "library": "incompetech",
...                     "status": "acquired", "license": "CC-BY-4.0",
...                     "source_page_url": "https://incompetech.com/x.mp3",
...                     "rights_verified": True, "mirror": "wayback"})
>>> src.provider, src.id, src.license, src.source_page_url
('incompetech', 'Sneaky Snitch', 'cc-by-4.0', 'https://incompetech.com/x.mp3')
>>> src.model_extra
{'rights_verified': True, 'commercial_ok': True, 'mirror': 'wayback'}
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from an.ir.assets import AssetSource
from an.sound_fetch import file_digest_fields

if TYPE_CHECKING:  # foley loads on first use, never with `import an`
    from foley.sources.music_library import AcquiredTrack

__all__ = [
    "ACQUIRED",
    "DFLT_PAUSE_S",
    "FAILED",
    "KEPT",
    "MUSIC_LIBRARIES",
    "REFUSED",
    "WISHLIST",
    "AcquiredTrack",
    "DroppedColumnsWarning",
    "LIST_SEPARATOR",
    "MusicLibrary",
    "MusicLibraryError",
    "MusicToolMissing",
    "acquire",
    "add_track_to_sounds",
    "asset_source",
    "attribution_text",
    "files_store",
    "kept_digests",
    "kept_sources",
    "license_code",
    "probe_verify",
    "read_tracks_table",
    "register_music_library",
    "titles_by_library",
    "titles_from_json",
    "track_row",
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
        "DroppedColumnsWarning",
        "LIST_SEPARATOR",
        "MusicLibrary",
        "MusicLibraryError",
        "MusicToolMissing",
        "attribution_text",
        "files_store",
        "kept_digests",
        "kept_sources",
        "probe_verify",
        "read_tracks_table",
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
#: The row columns that describe the acquisition, not the asset: they stay in the
#: tracks table. ``title`` and ``library`` become ``id`` and ``provider``.
ROW_ONLY: frozenset[str] = frozenset({"status", "file", "duration_s", "error"})
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


def license_code(license_id: str | None) -> str | None:
    """foley's licence id as an's code: foley's ``consumer_license_code``, the
    one mapping (an#729), imported on first use.

    >>> license_code("CC0-1.0"), license_code("unknown"), license_code(None)
    ('cc0-1.0', None, None)
    """
    from foley.licensing import consumer_license_code

    return consumer_license_code(license_id)


def asset_source(track: AcquiredTrack | Mapping[str, Any]) -> AssetSource:
    """One foley row as an's :class:`~an.ir.assets.AssetSource`.

    ``track`` is a foley ``AcquiredTrack`` or its ``.row()`` (as a tracks table
    reads back), which is rebuilt first (``AcquiredTrack.from_row``, an#731): its
    licence comes from the library's registry, and a licence cell that says
    otherwise is REFUSED, so an edited row cannot grant rights. ``library`` is the ``provider``, ``title`` the ``id``, the
    licence id an's code (:func:`license_code`); ``url`` (the mirror that served
    the bytes), ``source_page_url`` (the library's own address), the licence URL,
    author, attribution and ``sha256`` keep their names. The acquisition's own
    columns (:data:`ROW_ONLY`) stay in the table; every other column
    (``rights_verified``, ``commercial_ok``, ``mirror``, ``credited_by``, a titles
    file's metadata) rides as an extra; a column named like one of the
    source's own fields (``cost_usd``, ``cacheable``, ``id``, ...) is dropped,
    never trusted. Empty cells are dropped. The licence's ``creator_url`` is
    the ``author_url`` and whether its terms let
    the bytes be kept as ``cacheable``.
    """
    if isinstance(
        track, Mapping
    ):  # a row: rebuilt, so a forged licence cell is refused
        from foley.sources.music_library import AcquiredTrack

        track = AcquiredTrack.from_row(track)
    row = track.row()
    fields: dict[str, Any] = {
        "author_url": track.license.creator_url,
        "cacheable": track.license.cache_bytes_ok,
    }
    # A titles file's metadata rides as extras, never as one of the source's own
    # fields: a `cost_usd` or `cacheable` column must not claim rights (an#623).
    rest = {
        k: v
        for k, v in row.items()
        if k not in {"title", "library", "license", *SAME_NAME, *ROW_ONLY}
        and k not in AssetSource.model_fields
    }
    fields.update({k: row.get(k) for k in SAME_NAME}, **rest)
    return AssetSource(
        provider=row["library"],
        id=row["title"],
        license=license_code(row.get("license")),
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


def track_row(text: str, title: str) -> dict[str, str]:
    """``title``'s row in the tracks table ``text``.

    Raises:
        MusicLibraryError: When no row has that title, naming the ones there are.
    """
    from foley.sources.music_library import MusicLibraryError, read_tracks_table

    rows = read_tracks_table(text)
    row = next((r for r in rows if r.get("title") == title), None)
    if row is None:
        raise MusicLibraryError(
            f"no track {title!r} in the tracks table; it lists "
            f"{sorted(r.get('title', '') for r in rows)}"
        )
    return row


def add_track_to_sounds(
    store: Any,
    key: str,
    track: AcquiredTrack | Mapping[str, Any],
    files: Mapping[str, bytes],
    *,
    start: float | None = None,
    duration: float | None = None,
    fade_out: float | None = None,
    description: str = "",
) -> Any:
    """Put one acquired track in the sounds ``store`` under ``key`` (an#623).

    ``track`` is foley's ``AcquiredTrack``, or its tracks-table row (a
    ``tracks.csv`` line, :func:`track_row`: its licence is rebuilt from the
    library's registry, ``AcquiredTrack.from_row``), and ``files`` the library
    folder as ``{file name: bytes}`` (``files_store(out)``). The file it names
    is checked against its ``sha256``, cut with :func:`an.sound_fetch.cut_to_wav`
    (``start``, ``duration``, ``fade_out``, as ``an sounds add`` takes them) and
    stored with the track as its :class:`~an.ir.assets.AssetSource`
    (:func:`asset_source`) plus the cut, the file's digest as
    ``file_sha256``, so ``an credits`` lists the music with its licence. Nothing
    is fetched again: the site may be the one that refused scripts.

    Raises:
        MusicLibraryError: For a track that holds no file (not acquired or kept,
            or no ``file``/``sha256``), a file missing from ``files``, one whose
            bytes do not match the recorded digest, or an unknown library.
    """
    import hashlib

    from an.sound_fetch import CUT_FIELD, cut_record, cut_to_wav
    from an.sounds import add_sound
    from foley.sources.music_library import HELD, MusicLibraryError

    if isinstance(track, Mapping):  # its licence rebuilt from the registry (an#623)
        from foley.sources.music_library import AcquiredTrack

        track = AcquiredTrack.from_row(track)
    if track.status not in HELD or not track.file or not track.sha256:
        raise MusicLibraryError(
            f"track {track.title!r} holds no file (status {track.status!r}); "
            "only an acquired or kept row of the tracks table can be used"
        )
    if track.file not in files:
        raise MusicLibraryError(
            f"track {track.title!r}: its file {track.file!r} is not in the library "
            "folder; rerun `an music add-library` to fetch it again"
        )
    audio = bytes(files[track.file])
    if hashlib.sha256(audio).hexdigest() != track.sha256:
        raise MusicLibraryError(
            f"track {track.title!r}: {track.file!r} does not match the sha256 its "
            "row recorded (changed since it was acquired); rerun `an music add-library`"
        )
    wav = cut_to_wav(audio, start=start, duration=duration, fade_out=fade_out)
    fields = file_digest_fields(asset_source(track).model_dump(exclude_none=True))
    fields[CUT_FIELD] = cut_record(wav, start=start, fade_out=fade_out)
    return add_sound(
        store, key, wav, source=AssetSource(**fields), description=description
    )
