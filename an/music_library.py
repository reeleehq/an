"""Acquire a licensed music library, with provenance (an#470).

A production that scores itself from free libraries wrote the same script each
time: turn the titles a channel credits into download URLs, fetch them politely,
check each file is audio, record where it came from and under which licence,
and collect the attribution lines the licence asks for. :func:`acquire` is that
script, and ``an music add-library`` its command:

    an music add-library incompetech --titles-from usage.json --out audio/macleod

- **A library is data** (:class:`MusicLibrary`): who made it, its licence, the
  attribution it asks for, and the rule from a title to the file's URL. The
  registry (:data:`MUSIC_LIBRARIES`, :func:`register_music_library`) holds
  ``incompetech`` (Kevin MacLeod, CC BY 4.0) and two paid libraries, ``artlist``
  and ``epidemic_sound``, which never download: their titles become wishlist
  rows to license by hand. A library whose licence this package has not
  checked is registered by the caller, who vouches for it.
- **Every step is a seam** (keyword arguments with working defaults):
  ``fetch`` (``url -> bytes``, :func:`polite_fetch`), ``mirrors`` (where else
  a URL's bytes may be: :func:`direct`, then :func:`wayback`, the Internet
  Archive's raw copy, the only route to a site that refuses scripts),
  ``verify`` (``path -> seconds``, :func:`ffprobe_verify`) and ``sleep``
  (the pause between downloads).
- **A row is an** :class:`an.ir.assets.AssetSource`: the same provenance a
  sound in the project's store carries, so ``an credits`` reads it the same
  way, with the title, file, duration and digest beside it. A title that fails
  is a ``failed`` row with its reason; the batch goes on. A file already in
  ``out`` that verifies is kept, not fetched again, so a rerun resumes.

>>> lib = MUSIC_LIBRARIES["incompetech"]
>>> lib.track_url("Sneaky Snitch")
'https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Snitch.mp3'
>>> print(lib.attribution_for("Sneaky Snitch"))
"Sneaky Snitch" Kevin MacLeod (incompetech.com)
Licensed under Creative Commons: By Attribution 4.0 License
http://creativecommons.org/licenses/by/4.0/
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from an.ir.assets import AssetSource

__all__ = [
    "MUSIC_LIBRARIES",
    "AcquiredTrack",
    "MusicLibrary",
    "MusicLibraryError",
    "acquire",
    "attribution_text",
    "direct",
    "ffprobe_verify",
    "polite_fetch",
    "register_music_library",
    "files_store",
    "titles_by_library",
    "tracks_table",
    "wayback",
]

#: Seconds between two downloads from one library: a library is someone's
#: website, not a CDN.
DFLT_PAUSE_S: float = 2.0
#: How a download introduces itself.
USER_AGENT: str = "an-music-library (+https://github.com/reeleehq/an)"
#: Seconds a download may take before it counts as failed.
DFLT_TIMEOUT_S: float = 60.0
#: The Internet Archive's raw-file form of a URL (``id_``: the bytes as
#: archived, not the archive's page around them; ``2``: the latest capture).
WAYBACK_RAW: str = "https://web.archive.org/web/2id_/{url}"
#: The row statuses.
ACQUIRED, KEPT, FAILED, WISHLIST = "acquired", "kept", "failed", "wishlist"
#: The tracks table's columns, in order (a row's ``AssetSource`` extras beyond
#: them, a catalogue's ``feel`` or ``genre``, follow in name order).
TRACK_COLUMNS: tuple[str, ...] = (
    "title",
    "library",
    "status",
    "file",
    "duration_s",
    "sha256",
    "license",
    "license_url",
    "author",
    "url",
    "attribution",
    "credited_by",
    "error",
)


class MusicLibraryError(ValueError):
    """A library that is not registered, or a file that is not usable audio."""


@dataclass(frozen=True)
class MusicLibrary:
    """One library: who made it, under which licence, and where a title's file is.

    ``license`` is ``None`` for a PAID library (its titles become wishlist rows,
    never downloads); ``track_url`` is then unused. ``attribution`` is a
    template over ``{title}``, ``{author}`` and ``{license_url}``. ``aliases``
    are the names a video description credits it by (``From Epidemic Sound:``).
    """

    name: str
    author: str
    license: str | None
    track_url: Callable[[str], str] | None = None
    license_url: str | None = None
    attribution: str = '"{title}" {author}'
    author_url: str | None = None
    aliases: tuple[str, ...] = ()
    #: The file name a title is saved under in ``out``.
    file_name: Callable[[str], str] = field(default=lambda title: f"{title}.mp3")

    @property
    def paid(self) -> bool:
        return self.license is None

    def attribution_for(self, title: str) -> str:
        return self.attribution.format(
            title=title, author=self.author, license_url=self.license_url or ""
        )


#: The registered libraries, by name.
MUSIC_LIBRARIES: dict[str, MusicLibrary] = {}


def register_music_library(library: MusicLibrary, *, replace: bool = False) -> None:
    """Add ``library`` to :data:`MUSIC_LIBRARIES` (``replace`` to redefine one)."""
    if library.name in MUSIC_LIBRARIES and not replace:
        raise MusicLibraryError(
            f"music library {library.name!r} is already registered; pass replace=True"
        )
    if not library.paid and library.track_url is None:
        raise MusicLibraryError(
            f"music library {library.name!r} is free but has no track_url rule"
        )
    MUSIC_LIBRARIES[library.name] = library


def _incompetech_url(title: str) -> str:
    """Kevin MacLeod's rule: the MP3 is the title, quoted, under one folder."""
    return "https://incompetech.com/music/royalty-free/mp3-royaltyfree/" + quote(
        f"{title}.mp3"
    )


register_music_library(
    MusicLibrary(
        name="incompetech",
        author="Kevin MacLeod",
        license="cc-by-4.0",
        license_url="http://creativecommons.org/licenses/by/4.0/",
        author_url="https://incompetech.com",
        track_url=_incompetech_url,
        # The wording incompetech asks for, verbatim.
        attribution=(
            '"{title}" {author} (incompetech.com)\n'
            "Licensed under Creative Commons: By Attribution 4.0 License\n"
            "{license_url}"
        ),
        aliases=("Kevin MacLeod", "incompetech", "incompetech.com"),
    )
)
register_music_library(
    MusicLibrary(name="artlist", author="Artlist", license=None, aliases=("Artlist",))
)
register_music_library(
    MusicLibrary(
        name="epidemic_sound",
        author="Epidemic Sound",
        license=None,
        aliases=("Epidemic Sound", "Epidemic"),
    )
)


def direct(url: str) -> str:
    """The URL itself: the library's own server."""
    return url


def wayback(url: str) -> str:
    """The Internet Archive's raw copy of ``url`` (:data:`WAYBACK_RAW`).

    >>> wayback("https://example.org/a.mp3")
    'https://web.archive.org/web/2id_/https://example.org/a.mp3'
    """
    return WAYBACK_RAW.format(url=url)


#: Where to look for a file, in order.
DFLT_MIRRORS: tuple[Callable[[str], str], ...] = (direct, wayback)


def polite_fetch(url: str, *, timeout: float = DFLT_TIMEOUT_S) -> bytes:
    """``url``'s bytes, asked for with a named user agent; an HTTP error raises."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def ffprobe_verify(data: bytes) -> float:
    """The duration of the audio ``data``, in seconds; :class:`MusicLibraryError`
    when it is empty, has no audio stream, or no duration (an error page saved
    as ``.mp3`` is all three). Probed from a temporary file: from a pipe,
    ffprobe reports no duration."""
    exe = shutil.which("ffprobe")
    if exe is None:
        raise MusicLibraryError(
            "verifying a track needs ffprobe (it comes with ffmpeg: "
            "https://ffmpeg.org/download.html)"
        )
    if not data:
        raise MusicLibraryError("the file is empty")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "track"
        path.write_bytes(data)
        probe = subprocess.run(
            [exe, "-v", "error", "-show_entries", "stream=codec_type:format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
    info = json.loads(probe.stdout or "{}")
    if not any(s.get("codec_type") == "audio" for s in info.get("streams", ())):
        raise MusicLibraryError("the file has no audio stream")
    duration = float(info.get("format", {}).get("duration") or 0.0)
    if duration <= 0:
        raise MusicLibraryError("the file has no duration")
    return duration


@dataclass(frozen=True)
class AcquiredTrack:
    """One row of the tracks table: a title, what became of it, and its provenance."""

    title: str
    library: str
    status: str
    source: AssetSource
    file: str | None = None
    duration_s: float | None = None
    error: str | None = None

    def row(self) -> dict[str, Any]:
        """The row as the tracks table writes it (lists joined by ``; ``)."""
        src = self.source.model_dump(exclude_none=True)
        out = {
            "title": self.title,
            "library": self.library,
            "status": self.status,
            "file": self.file,
            "duration_s": None
            if self.duration_s is None
            else round(self.duration_s, 3),
            "error": self.error,
            **src,
        }
        return {
            k: "; ".join(map(str, v)) if isinstance(v, (list, tuple)) else v
            for k, v in out.items()
            if k not in ("provider", "id")
        }


def acquire(
    library: str | MusicLibrary,
    titles: Iterable[str] | Mapping[str, Mapping[str, Any]],
    *,
    out: str | Path | MutableMapping[str, bytes],
    fetch: Callable[[str], bytes] = polite_fetch,
    mirrors: Sequence[Callable[[str], str]] = DFLT_MIRRORS,
    verify: Callable[[bytes], float] = ffprobe_verify,
    pause: float = DFLT_PAUSE_S,
    sleep: Callable[[float], None] = time.sleep,
) -> list[AcquiredTrack]:
    """Download ``titles`` of ``library`` into ``out``, verified, one row each.

    ``out`` is a folder, or any ``{file name: bytes}`` store (:func:`files_store`).

    ``titles`` is a list, or ``{title: metadata}`` whose metadata (``credited_by``:
    the videos that credit it; a catalogue's ``feel``, ``genre``, ...) is kept
    on the row. Each title is fetched from each of ``mirrors`` in turn until one
    gives bytes ``verify`` accepts; ``pause`` seconds pass between downloads.
    A paid library downloads nothing and returns wishlist rows.
    """
    lib = _library(library)
    meta = (
        {t: dict(m or {}) for t, m in titles.items()}
        if isinstance(titles, Mapping)
        else {t: {} for t in titles}
    )
    for title, extra in meta.items():
        clash = sorted(set(extra) & set(AssetSource.model_fields))
        if clash:
            raise MusicLibraryError(
                f"{title!r}: its metadata sets {clash}, which the library states "
                f"({lib.name}); drop them from the titles file"
            )
    store = files_store(out)
    rows: list[AcquiredTrack] = []
    fetched_before = False
    for title, extra in meta.items():
        source = AssetSource(
            provider=lib.name,
            id=title,
            license=lib.license,
            license_url=lib.license_url,
            author=lib.author,
            author_url=lib.author_url,
            attribution=None if lib.paid else lib.attribution_for(title),
            **extra,
        )
        if lib.paid:
            rows.append(AcquiredTrack(title, lib.name, WISHLIST, source))
            continue
        url = lib.track_url(title)
        name = lib.file_name(title)
        source = source.model_copy(update={"url": url, "source_page_url": url})
        if name in store:
            try:
                rows.append(_row(lib, title, KEPT, source, name, store[name], verify))
                continue
            except MusicLibraryError:
                pass  # a broken file from an earlier run: fetch it again
        errors = []
        for mirror in mirrors:
            if fetched_before:
                sleep(pause)
            fetched_before = True
            try:
                data = fetch(mirror(url))
                row = _row(lib, title, ACQUIRED, source, name, data, verify)
            except Exception as e:  # noqa: BLE001 — every failure is the row's reason
                errors.append(f"{mirror.__name__}: {e}")
                continue
            store[name] = data
            rows.append(row)
            break
        else:
            rows.append(
                AcquiredTrack(title, lib.name, FAILED, source, error="; ".join(errors))
            )
    return rows


def _library(library: str | MusicLibrary) -> MusicLibrary:
    if isinstance(library, MusicLibrary):
        return library
    if library not in MUSIC_LIBRARIES:
        raise MusicLibraryError(
            f"no music library {library!r}; registered: {sorted(MUSIC_LIBRARIES)} "
            "(register_music_library adds one, with the licence you vouch for)"
        )
    return MUSIC_LIBRARIES[library]


def files_store(
    out: str | Path | MutableMapping[str, bytes],
) -> MutableMapping[str, bytes]:
    """``out`` as a ``{file name: bytes}`` store: a folder (made if missing)
    becomes a ``dol.Files`` over it; a mapping is used as it is."""
    if isinstance(out, MutableMapping):
        return out
    from dol import Files

    Path(out).mkdir(parents=True, exist_ok=True)
    return Files(str(out))


def _row(
    lib: MusicLibrary,
    title: str,
    status: str,
    source: AssetSource,
    name: str,
    data: bytes,
    verify: Callable[[bytes], float],
) -> AcquiredTrack:
    """The row of a verified file (``verify`` raises for one that is not)."""
    duration = verify(data)
    return AcquiredTrack(
        title,
        lib.name,
        status,
        source.model_copy(update={"sha256": hashlib.sha256(data).hexdigest()}),
        file=name,
        duration_s=duration,
    )


def tracks_table(rows: Iterable[AcquiredTrack]) -> str:
    """The tracks table as CSV text: :data:`TRACK_COLUMNS`, then any extra the
    rows carry, in name order."""
    dicts = [r.row() for r in rows]
    extras = sorted({k for d in dicts for k in d} - set(TRACK_COLUMNS))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[*TRACK_COLUMNS, *extras])
    writer.writeheader()
    writer.writerows(dicts)
    return buffer.getvalue()


def attribution_text(rows: Iterable[AcquiredTrack]) -> str:
    """The attribution blocks to paste under a video, one per track that has
    one (acquired or kept), blank-line separated, each once.

    >>> src = AssetSource(provider="x", attribution='"A" B')
    >>> attribution_text([AcquiredTrack("A", "x", ACQUIRED, src)] * 2)
    '"A" B\\n'
    """
    blocks = dict.fromkeys(
        r.source.attribution
        for r in rows
        if r.status in (ACQUIRED, KEPT) and r.source.attribution
    )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def titles_by_library(description: str) -> dict[str, list[str]]:
    """The titles a video description credits, by registered library: a line
    naming a library (by name or alias, ``From Epidemic Sound:``) opens its
    block, and each following line (bullets stripped) is a title until a blank
    line.

    >>> text = '''Music:
    ... From Epidemic Sound:
    ... - Night Owl
    ... - Morning Light
    ...
    ... Kevin MacLeod:
    ... Sneaky Snitch'''
    >>> titles_by_library(text)
    {'epidemic_sound': ['Night Owl', 'Morning Light'], 'incompetech': ['Sneaky Snitch']}
    """
    names = {
        alias.casefold(): lib.name
        for lib in MUSIC_LIBRARIES.values()
        for alias in (lib.name, *lib.aliases)
    }
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in description.splitlines():
        text = line.strip().lstrip("-•*").strip()
        if not text:
            current = None
            continue
        header = text.rstrip(":").strip()
        if header.casefold().startswith("from "):
            header = header[5:].strip()
        if text.endswith(":") and header.casefold() in names:
            current = names[header.casefold()]
            out.setdefault(current, [])
        elif current is not None:
            out[current].append(text)
    return out
