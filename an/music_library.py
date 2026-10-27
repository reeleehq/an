"""Acquire a licensed music library, with provenance (an#470).

A production that scores itself from free libraries wrote the same script each
time: turn the titles a channel credits into download URLs, fetch them politely,
check each file is audio, record where it came from and under which licence,
and collect the attribution lines the licence asks for. :func:`acquire` is that
script, and ``an music add-library`` its command:

    an music add-library incompetech --titles-from usage.json --out audio/macleod

- **A library is data** (:class:`MusicLibrary`): who made it, its licence, the
  attribution it asks for, the names a video credits it by, and the rule from
  a title to the file's URL. The registry (:data:`MUSIC_LIBRARIES`,
  :func:`register_music_library`) holds ``incompetech`` (Kevin MacLeod, CC BY
  4.0) and two paid libraries, ``artlist`` and ``epidemic_sound``, which never
  download: their titles become wishlist rows to license by hand. A library
  whose licence this package has not checked is registered by the caller, who
  vouches for it.
- **Every step is a seam** (keyword arguments with working defaults):
  ``fetch`` (``url -> bytes``, :func:`polite_fetch`), ``mirrors`` (where else
  a URL's bytes may be: :func:`direct`, then :func:`wayback`, the Internet
  Archive's raw copy, the only route to a site that refuses scripts),
  ``verify`` (``bytes -> seconds``, :func:`ffprobe_verify`), ``sleep`` (the
  pause before a second request to the same host) and ``out`` (any
  ``{file name: bytes}`` store; a folder by default).
- **A row is an** :class:`an.ir.assets.AssetSource`, the provenance a sound in
  the project's store carries: ``url`` is where the bytes came from (the
  mirror that served them), ``source_page_url`` the library's own address.
  A title that fails is a ``failed`` row with its reasons; the batch goes on. A
  file whose digest a previous run recorded (``kept``) is not fetched again,
  so a rerun resumes.

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
import http.client
import io
import json
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import urllib.request
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from an.ir.assets import AssetSource

__all__ = [
    "MUSIC_LIBRARIES",
    "AcquiredTrack",
    "MusicLibrary",
    "MusicLibraryError",
    "MusicToolMissing",
    "acquire",
    "attribution_text",
    "direct",
    "ffprobe_verify",
    "files_store",
    "kept_digests",
    "polite_fetch",
    "register_music_library",
    "safe_file_name",
    "titles_by_library",
    "titles_from_json",
    "tracks_table",
    "wayback",
]

#: Seconds between two requests to one host: a library is someone's website.
DFLT_PAUSE_S: float = 2.0
#: How a download introduces itself.
USER_AGENT: str = "an-music-library (+https://github.com/reeleehq/an)"
#: Seconds a download may take before it counts as failed.
DFLT_TIMEOUT_S: float = 60.0
#: The largest file a download keeps: a music track is a few MB; a body past
#: this is not one.
DFLT_MAX_BYTES: int = 64 * 1024 * 1024
#: The Internet Archive's raw-file form of a URL (``id_``: the bytes as
#: archived, not the archive's page around them; ``2``: the latest capture).
WAYBACK_RAW: str = "https://web.archive.org/web/2id_/{url}"
#: The extension a track is saved with when its library names no other.
DFLT_SUFFIX: str = ".mp3"
#: The row statuses.
ACQUIRED, KEPT, FAILED, WISHLIST = "acquired", "kept", "failed", "wishlist"
#: The tracks table's columns, in order (a row's other extras, a catalogue's
#: ``feel`` or ``genre``, follow in name order).
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
    "source_page_url",
    "mirror",
    "attribution",
    "credited_by",
    "error",
)
#: The columns a titles file's metadata fills (the rest the library states).
METADATA_COLUMNS: tuple[str, ...] = ("credited_by",)
#: What a fetch, a verification or a store write may raise for ONE title (an
#: HTTP or URL error is an ``OSError``; a :class:`MusicLibraryError` a
#: ``ValueError``); anything else is a bug and stops the batch.
_TITLE_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ValueError,
    KeyError,
    http.client.HTTPException,
)


class MusicLibraryError(ValueError):
    """A library, a title or a file that cannot be used, and why."""


class MusicToolMissing(RuntimeError):
    """A tool every title needs is missing: the batch stops before it starts."""


def safe_file_name(title: str, *, suffix: str = DFLT_SUFFIX) -> str:
    """``title`` as a file name: NFC, path separators as ``-``, no leading dot.

    >>> safe_file_name("AC/DC"), safe_file_name("../../escape")
    ('AC-DC.mp3', '-..-escape.mp3')
    """
    name = unicodedata.normalize("NFC", title).replace("/", "-").replace("\\", "-")
    name = name.strip().lstrip(". ")
    if not name:
        raise MusicLibraryError(f"title {title!r} gives no file name")
    return name + suffix


@dataclass(frozen=True)
class MusicLibrary:
    """One library: who made it, under which licence, and where a title's file is.

    ``license`` is ``None`` for a PAID library (its titles become wishlist rows,
    never downloads); ``track_url`` is then unused. ``attribution`` is a
    template over ``{title}``, ``{author}`` and ``{license_url}``. ``aliases``
    are the names a video description credits it by (``From Epidemic Sound:``,
    ``Kevin MacLeod (incompetech.com)``); ``file_name`` the name a title is
    saved under.
    """

    name: str
    author: str
    license: str | None
    track_url: Callable[[str], str] | None = None
    license_url: str | None = None
    attribution: str = '"{title}" {author}'
    author_url: str | None = None
    aliases: tuple[str, ...] = ()
    file_name: Callable[[str], str] = safe_file_name

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


def polite_fetch(
    url: str, *, timeout: float = DFLT_TIMEOUT_S, max_bytes: int = DFLT_MAX_BYTES
) -> bytes:
    """``url``'s bytes, asked for with a named user agent. An HTTP error raises;
    so does a text page (an error page served with 200) and a body over
    ``max_bytes``, before it is read."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        kind = (response.headers.get("Content-Type") or "").split(";")[0].strip()
        if kind.startswith("text/"):
            raise MusicLibraryError(f"{url} is a {kind} page, not audio")
        size = int(response.headers.get("Content-Length") or 0)
        if size > max_bytes:
            raise MusicLibraryError(f"{url} is {size} bytes, over {max_bytes}")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise MusicLibraryError(f"{url} is over {max_bytes} bytes")
    return data


def _ffprobe() -> str:
    exe = shutil.which("ffprobe")
    if exe is None:
        raise MusicToolMissing(
            "verifying a track needs ffprobe (it comes with ffmpeg: "
            "https://ffmpeg.org/download.html)"
        )
    return exe


def ffprobe_verify(data: bytes) -> float:
    """The duration of the audio ``data``, in seconds; :class:`MusicLibraryError`
    when it is empty, has no audio stream, or no duration (an error page saved
    as ``.mp3`` is all three). Probed from a temporary file: from a pipe,
    ffprobe reports no duration."""
    exe = _ffprobe()
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
        """The row as the tracks table writes it (a list joined by ``; ``, a
        mapping as JSON)."""
        src = self.source.model_dump(exclude_none=True, exclude={"provider", "id"})
        out = {
            "title": self.title,
            "library": self.library,
            "status": self.status,
            "file": self.file,
            "duration_s": None
            if self.duration_s is None
            else round(self.duration_s, 3),
            "error": self.error,
            **{k: v for k, v in src.items() if v != {}},
        }
        return {k: _cell(v) for k, v in out.items()}


def _cell(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return "; ".join(map(str, value))
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True)
    return value


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
    kept: Mapping[str, str] | None = None,
) -> list[AcquiredTrack]:
    """Download ``titles`` of ``library`` into ``out``, verified, one row each.

    ``titles`` is a list, or ``{title: metadata}`` whose metadata (``credited_by``:
    the videos that credit it; a catalogue's ``feel``, ``genre``, ...) is kept
    on the row. Each title is fetched from each of ``mirrors`` in turn until one
    gives bytes ``verify`` accepts; ``pause`` seconds pass before a second
    request to the same host. ``kept`` is ``{file name: sha256}`` a previous run
    recorded (:func:`kept_digests`): a file in ``out`` with that digest is kept,
    any other is fetched again. A paid library downloads nothing and returns
    wishlist rows.
    """
    lib = _library(library)
    meta = _titles_meta(titles, lib)
    store = files_store(out)
    kept = dict(kept or {})
    if verify is ffprobe_verify and not lib.paid:
        _ffprobe()  # stop before the first download, not after it
    names = {} if lib.paid else _file_names(lib, meta)
    hosts: set[str] = set()

    def wait(url: str) -> None:
        host = urlparse(url).netloc
        if host in hosts:
            sleep(pause)
        hosts.add(host)

    rows: list[AcquiredTrack] = []
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
        page, name = lib.track_url(title), names[title]
        source = source.model_copy(update={"source_page_url": page})
        try:
            if name in kept and name in store:
                data = store[name]
                if hashlib.sha256(data).hexdigest() == kept[name]:
                    rows.append(
                        _row(lib, title, KEPT, source, name, data, verify(data))
                    )
                    continue
            data, duration, url, mirror = _fetch_verified(
                page, mirrors=mirrors, fetch=fetch, verify=verify, wait=wait
            )
            store[name] = data
        except _TITLE_ERRORS as e:
            rows.append(AcquiredTrack(title, lib.name, FAILED, source, error=str(e)))
            continue
        source = source.model_copy(update={"url": url, "mirror": mirror})
        rows.append(_row(lib, title, ACQUIRED, source, name, data, duration))
    return rows


def _fetch_verified(
    url: str,
    *,
    mirrors: Sequence[Callable[[str], str]],
    fetch: Callable[[str], bytes],
    verify: Callable[[bytes], float],
    wait: Callable[[str], None],
) -> tuple[bytes, float, str, str]:
    """``(bytes, seconds, the URL that served them, its mirror's name)`` from
    the first of ``mirrors`` whose bytes ``verify`` accepts; every mirror's
    reason in one :class:`MusicLibraryError` when none does."""
    reasons = []
    for mirror in mirrors:
        where = mirror(url)
        wait(where)
        try:
            data = fetch(where)
            return data, verify(data), where, mirror.__name__
        except _TITLE_ERRORS as e:
            reasons.append(f"{mirror.__name__}: {e}")
    raise MusicLibraryError("; ".join(reasons))


def _titles_meta(titles: Any, lib: MusicLibrary) -> dict[str, dict[str, Any]]:
    """``titles`` as ``{title: metadata}``, refused when it is neither a list of
    titles nor such a mapping, or when metadata would restate the library."""
    if isinstance(titles, (str, bytes)):
        raise MusicLibraryError("titles is one string; pass a list of titles")
    if isinstance(titles, Mapping):
        meta = {}
        for title, m in titles.items():
            if not isinstance(m, Mapping):
                raise MusicLibraryError(
                    f"{title!r}: metadata must be an object ({{'feel': ...}}), got {m!r}"
                )
            meta[title] = dict(m)
    else:
        meta = {t: {} for t in titles}
    reserved = (set(AssetSource.model_fields) | set(TRACK_COLUMNS)) - set(
        METADATA_COLUMNS
    )
    for title, extra in meta.items():
        if not isinstance(title, str) or not title.strip():
            raise MusicLibraryError(
                f"a title must be a non-empty string, got {title!r}"
            )
        clash = sorted(set(extra) & reserved)
        if clash:
            raise MusicLibraryError(
                f"{title!r}: its metadata sets {clash}, which the library or the "
                f"table states ({lib.name}); drop them from the titles file"
            )
    return meta


def _file_names(lib: MusicLibrary, meta: Mapping[str, Any]) -> dict[str, str]:
    """``{title: file name}``, refused when two titles share a file (as a
    case-insensitive disk sees it)."""
    names = {title: lib.file_name(title) for title in meta}
    seen: dict[str, str] = {}
    for title, name in names.items():
        key = unicodedata.normalize("NFC", name).casefold()
        if key in seen:
            raise MusicLibraryError(
                f"titles {seen[key]!r} and {title!r} would both be saved as {name!r}"
            )
        seen[key] = title
    return names


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
    duration: float,
) -> AcquiredTrack:
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


def kept_digests(table: str) -> dict[str, str]:
    """``{file: sha256}`` of the acquired or kept rows of a tracks table
    (:func:`tracks_table`'s text): what a rerun may keep."""
    return {
        r["file"]: r["sha256"]
        for r in csv.DictReader(io.StringIO(table))
        if r.get("status") in (ACQUIRED, KEPT) and r.get("file") and r.get("sha256")
    }


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


def titles_from_json(text: str) -> list[str] | dict[str, dict[str, Any]]:
    """A titles file's JSON: a list of titles, or ``{title: {metadata}}``.

    >>> titles_from_json('["A", "B"]'), titles_from_json('{"A": {"feel": "Bright"}}')
    (['A', 'B'], {'A': {'feel': 'Bright'}})
    """
    try:
        titles = json.loads(text)
    except json.JSONDecodeError as e:
        raise MusicLibraryError(f"the titles file is not JSON ({e})") from e
    shapes = 'a list of titles (["A", "B"]) or an object ({"A": {"feel": "Bright"}})'
    if isinstance(titles, list) and all(isinstance(t, str) for t in titles):
        return titles
    if isinstance(titles, dict) and all(isinstance(m, dict) for m in titles.values()):
        return titles
    raise MusicLibraryError(f"the titles file must hold {shapes}")


#: What a credit line may carry before its title: a timestamp (``0:00``,
#: ``(1:02:03) -``) and a label (``Song:``, ``Track -``).
_TIMESTAMP = re.compile(r"^\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s*[-–—|:]?\s*")
_LABEL = re.compile(r"^(?:song|track|title)\s*[:\-–—]\s*", re.IGNORECASE)
#: The attribution form, ``"Title" Author (site)``.
_QUOTED = re.compile(r'^["“](?P<title>[^"”]+)["”]\s*(?:by\s+|[-–—]\s*)?(?P<who>.*)$')
#: What may wrap a library's name in a header (``From Epidemic Sound:``,
#: ``Music by Kevin MacLeod (incompetech.com)``, ``Music: Artlist``).
_HEADER_PREFIX = re.compile(
    r"^(?:from|music\s+by|music\s+from|music)\b\s*[:\-–]?\s*", re.I
)
_PARENS = re.compile(r"\s*\([^)]*\)")
#: Lines in a credit block that are not titles: a link, the licence's words.
_NOISE = re.compile(r"https?://|^www\.|licen[cs]ed under|creative\s+commons", re.I)


def titles_by_library(description: str) -> dict[str, list[str]]:
    """The titles a video description credits, by registered library.

    A line naming a library (by name or alias, with ``From``/``Music by``/
    ``Music:`` and a parenthetical allowed around it) opens its block, and each
    following line is a title until a blank line; a timestamp, a
    ``Song:``/``Track:`` label, quotes and bullets are stripped, and links and
    licence lines skipped. The attribution form (``"Title" Kevin MacLeod
    (incompetech.com)``) credits its title wherever it stands.

    >>> text = '''Music:
    ... From Epidemic Sound:
    ... - 0:00 Night Owl
    ... - Song: "Morning Light"
    ... https://www.epidemicsound.com/
    ...
    ... "Sneaky Snitch" Kevin MacLeod (incompetech.com)
    ... Licensed under Creative Commons: By Attribution 4.0 License'''
    >>> titles_by_library(text)
    {'epidemic_sound': ['Night Owl', 'Morning Light'], 'incompetech': ['Sneaky Snitch']}
    """
    names = {
        alias.casefold(): lib.name
        for lib in MUSIC_LIBRARIES.values()
        for alias in (lib.name, *lib.aliases)
    }

    def library_named(text: str) -> str | None:
        bare = _PARENS.sub("", text).strip().rstrip(":").strip()
        bare = _HEADER_PREFIX.sub("", bare).strip().rstrip(":").strip()
        return names.get(bare.casefold())

    out: dict[str, list[str]] = {}

    def credit(library: str, title: str) -> None:
        titles = out.setdefault(library, [])
        if title and title not in titles:
            titles.append(title)

    current: str | None = None
    for line in description.splitlines():
        text = line.strip().lstrip("-•*·").strip()
        if not text:
            current = None
            continue
        if _NOISE.search(text):
            continue
        quoted = _QUOTED.match(text)
        if quoted and (library := library_named(quoted["who"])):
            credit(library, quoted["title"].strip())
            continue
        if library := library_named(text):
            current = library
            out.setdefault(current, [])
            continue
        if current is not None:
            title = _LABEL.sub("", _TIMESTAMP.sub("", text)).strip().strip('"“”')
            credit(current, title)
    return {k: v for k, v in out.items() if v}
