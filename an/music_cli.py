"""``an music …``: acquire a licensed music library from the shell (an#470).

A thin projection of :mod:`foley.sources.music_library` through an's bridge,
:mod:`an.music_library`, wired into the CLI by :data:`an.tools._dispatch_namespaces`.
"""

from __future__ import annotations

from an.music_library import DFLT_PAUSE_S

__all__ = ["add_library"]

#: What ``add_library`` writes beside the files.
TRACKS_TABLE: str = "tracks.csv"
ATTRIBUTION_FILE: str = "ATTRIBUTION.md"


def add_library(
    library: str,
    titles_from: str = "",
    out: str = "",
    pause: float = DFLT_PAUSE_S,
) -> str:
    """Download a library's tracks, verified, with a tracks table and the attribution blocks.

    Writes the files, `tracks.csv` (one row per title: status, file, duration,
    sha256, licence, the URL the bytes came from and the library's page, the
    attribution, and any metadata the titles file gives) and `ATTRIBUTION.md`
    (the blocks to paste under a video) into OUT. A rerun keeps the files the
    previous `tracks.csv` recorded, digest checked, and exits 1 when a title
    could not be fetched, or its licence does not allow the use (the table
    still lists it, with why). A paid library (artlist,
    epidemic_sound) downloads nothing: its rows are a wishlist.

    library: a registered library (incompetech, artlist, epidemic_sound)
    titles_from: a JSON list of titles, a JSON object {title: {metadata}}, or a text file (a video description) whose credits name LIBRARY
    out: the folder the files, tracks.csv and ATTRIBUTION.md go in
    pause: seconds before a second request to the same host
    """
    from collections import Counter
    from pathlib import Path

    from an.cli_status import failed
    from an.music_library import (
        FAILED,
        MUSIC_LIBRARIES,
        REFUSED,
        MusicLibraryError,
        acquire,
        attribution_text,
        files_store,
        kept_sources,
        titles_by_library,
        titles_from_json,
        tracks_table,
    )

    if not titles_from or not out:
        raise SystemExit("an music add-library: --titles-from and --out are required")
    if library not in MUSIC_LIBRARIES:
        raise SystemExit(
            f"an music add-library: no library {library!r}; "
            f"registered: {sorted(MUSIC_LIBRARIES)}"
        )
    source = Path(titles_from)
    text = source.read_text(encoding="utf-8")
    try:
        titles = (
            titles_from_json(text)
            if source.suffix.lower() == ".json"
            else titles_by_library(text).get(library, [])
        )
        if not titles:
            raise MusicLibraryError(f"no {library} titles in {titles_from}")
        store = files_store(out)
        previous = store.get(TRACKS_TABLE, b"").decode("utf-8")
        rows = acquire(
            library, titles, out=store, pause=pause, kept=kept_sources(previous)
        )
    except MusicLibraryError as e:
        raise SystemExit(f"an music add-library: {e}") from e
    store[TRACKS_TABLE] = tracks_table(rows).encode("utf-8")
    store[ATTRIBUTION_FILE] = attribution_text(rows).encode("utf-8")
    counts = Counter(r.status for r in rows)
    reasons = [f"  {r.title}: {r.error}" for r in rows if r.error]
    report = "\n".join(
        [
            f"{library}: "
            + ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
            + f" -> {Path(out) / TRACKS_TABLE}",
            *reasons,
        ]
    )
    return failed(report) if counts[FAILED] or counts[REFUSED] else report


_dispatch_funcs = [add_library]
