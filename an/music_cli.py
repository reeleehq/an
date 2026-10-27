"""``an music …``: acquire a licensed music library from the shell (an#470).

A thin projection of :mod:`an.music_library`, wired into the CLI by
:data:`an.tools._dispatch_namespaces`.
"""

from __future__ import annotations

__all__ = ["add_library"]

#: What ``add_library`` writes beside the files.
TRACKS_TABLE: str = "tracks.csv"
ATTRIBUTION_FILE: str = "ATTRIBUTION.md"


def add_library(
    library: str,
    titles_from: str,
    out: str,
    pause: float = 2.0,
) -> str:
    """Download a library's tracks, verified, with a tracks table and the attribution blocks.

    Writes the files, `tracks.csv` (one row per title: status, file, duration,
    sha256, licence, source URL, attribution, and any metadata the titles file
    gives) and `ATTRIBUTION.md` (the blocks to paste under a video) into OUT. A
    rerun keeps what is already there and verified. A paid library (artlist,
    epidemic_sound) downloads nothing: its rows are a wishlist.

    library: a registered library (incompetech, artlist, epidemic_sound)
    titles_from: a JSON list of titles, a JSON object {title: {metadata}}, or a text file (a video description) whose credit block for LIBRARY lists them
    out: the folder the files, tracks.csv and ATTRIBUTION.md go in
    pause: seconds between two downloads
    """
    import json
    from collections import Counter
    from pathlib import Path

    from an.music_library import (
        acquire,
        attribution_text,
        files_store,
        titles_by_library,
        tracks_table,
    )

    source = Path(titles_from)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        titles = json.loads(text)
    else:
        titles = titles_by_library(text).get(library, [])
    if not titles:
        raise SystemExit(f"an music add-library: no {library} titles in {titles_from}")
    store = files_store(out)
    rows = acquire(library, titles, out=store, pause=pause)
    store[TRACKS_TABLE] = tracks_table(rows).encode("utf-8")
    store[ATTRIBUTION_FILE] = attribution_text(rows).encode("utf-8")
    counts = Counter(r.status for r in rows)
    failed = [f"  {r.title}: {r.error}" for r in rows if r.error]
    return "\n".join(
        [
            f"{library}: "
            + ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
            + f" -> {Path(out) / TRACKS_TABLE}",
            *failed,
        ]
    )


_dispatch_funcs = [add_library]
