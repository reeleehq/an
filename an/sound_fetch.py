"""Add a sound from a URL, with its provenance and the cut taken (an#318).

A production that sources its music or an effect from the web used to write
the same script each time: download, cut with ffmpeg, type an ``AssetSource``
by hand, :func:`an.sounds.add_sound`. :func:`add_sound_from_url` is that script:

- the download is a seam, ``fetcher=``: any ``(url) -> Fetched`` (the bytes in
  any container ffmpeg reads, and what the source says about itself). The
  default, :func:`yb_fetcher`, uses `yb <https://github.com/thorwhalen/yb>`_
  when it is installed (``pip install yb`` with its ``yt-dlp`` extra); it is
  never a dependency of ``an``. Another ingest (braidio's) plugs in here;
- the cut (``start``, ``duration``, ``fade_out``) is made by ffmpeg into a
  16-bit WAV, and recorded with the source, so ``an credits`` says which part
  of which page it is ("0:07.9–0:08.8 of <url>");
- the licence is the caller's statement, never guessed: required, and
  ``"unknown"`` says so explicitly (the sound is then UNVERIFIED) -- unless the
  source states its own rights (:attr:`Fetched.source`). A sound from a foley
  library does (an#729): :func:`foley_fetcher` reads ``foley:<sound_id>`` through
  ``foley.export_sound``, whose rights become the sound's
  :class:`~an.ir.assets.AssetSource` (:func:`foley_asset_source`, with foley's
  whole provenance as ``foley_provenance``), so the licence may be omitted, and
  a caller's licence that disagrees is refused. A fetcher says which refs it
  states rights for (:func:`fetcher_states_rights`), so a licence missing for
  any other is refused before anything is downloaded. The default fetcher
  (:func:`default_fetcher`) sends a ``foley:`` ref to foley and anything else to
  ``yb``, so ``an sounds add <project> door foley:fsd-222`` works.

>>> fetched = Fetched(audio=b"...", url="https://example.org/a", id="a", author="Ann")
>>> fetched.provider
'web'
"""

from __future__ import annotations

import enum
import functools
import hashlib
import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from an.ir.assets import AssetSource, normalise_license
from an.sounds import SoundAsset, SoundError, add_sound, wav_duration

__all__ = [
    "UNSTATED",
    "Fetched",
    "Fetcher",
    "Unstated",
    "add_sound_from_url",
    "ai_label",
    "cut_to_wav",
    "default_fetcher",
    "fetcher_states_rights",
    "file_digest_fields",
    "foley_asset_source",
    "foley_fetcher",
    "notice_label",
    "yb_fetcher",
]

#: The source field (an ``AssetSource`` extra) recording which part of the
#: fetched media the sound is: ``{"start": s, "end": s, "fade_out": s}``.
CUT_FIELD: str = "cut"
#: The source field holding the fetched media's own title.
TITLE_FIELD: str = "title"
#: The sample rate a fetched sound is stored at.
FETCH_SAMPLE_RATE: int = 44100
#: The source field keeping the digest of the media a sound was cut from: a
#: source's own ``sha256`` names those bytes, and a stored sound is the cut WAV,
#: whose digest is the :class:`~an.sounds.SoundAsset`'s (an#623, an#729).
FILE_SHA256_FIELD: str = "file_sha256"
#: The ref of a sound in a foley library: ``foley:<sound_id>`` (an#729).
FOLEY_SCHEME: str = "foley:"
#: The source field keeping foley's whole export provenance (JSON-safe): the
#: licence flags, a required notice, the terms' notes, excluded territories,
#: the archived bytes' digest, an AI clip's Art. 50 checklist, ...
FOLEY_PROVENANCE_FIELD: str = "foley_provenance"
#: The provenance key of an AI-generated sound's disclosure: foley's EU AI Act
#: Art. 50 checklist (``pending``, ``publish_ready``, ``obligations``) with the
#: generation block (``provenance.generator_model``, ...).
AI_DISCLOSURE_KEY: str = "ai_disclosure"
#: The provenance key of a notice the licence requires shown verbatim.
NOTICE_KEY: str = "notice_text_required"


class Unstated(enum.Enum):
    """The type of :data:`UNSTATED`, ``license=`` left out."""

    UNSTATED = "unstated"


#: ``license=`` left out: the caller states no licence, which only a source that
#: states its own rights (:attr:`Fetched.source`) may do.
UNSTATED = Unstated.UNSTATED


@dataclass(frozen=True)
class Fetched:
    """What a fetcher returns: the media's bytes, and what its page says about it.

    When ``source`` is set it is the sound's whole provenance (the rights the
    source states), and ``id``, ``title``, ``author`` and ``provider`` are not
    read; otherwise they are, with the caller's licence.
    """

    audio: bytes
    url: str
    id: str | None = None
    title: str | None = None
    author: str | None = None
    #: Where it came from, as an ``AssetSource.provider`` (``youtube``, …).
    provider: str = "web"
    #: The rights the source itself states (a foley library's export), or
    #: ``None``: then the licence is the caller's statement.
    source: AssetSource | None = None


#: ``(url) -> Fetched``: how :func:`add_sound_from_url` gets the media. A
#: fetcher whose source states its own rights for some refs says which with a
#: ``states_rights(url) -> bool`` attribute (:func:`fetcher_states_rights`).
Fetcher = Callable[[str], Fetched]


def fetcher_states_rights(fetcher: Fetcher, url: str) -> bool:
    """Whether ``fetcher`` declares that its source states the rights of ``url``.

    Read from its ``states_rights(url)`` attribute (a ``functools.partial`` of a
    fetcher keeps the declaration); a fetcher without one states none.

    >>> fetcher_states_rights(default_fetcher, "foley:fsd-222")
    True
    >>> fetcher_states_rights(default_fetcher, "https://youtu.be/x"), fetcher_states_rights(print, "x")
    (False, False)
    """
    while isinstance(fetcher, functools.partial):
        if hasattr(fetcher, "states_rights"):
            break
        fetcher = fetcher.func
    declared = getattr(fetcher, "states_rights", None)
    return bool(declared(url)) if callable(declared) else False


def file_digest_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """``fields`` with ``sha256`` (the fetched or library file's) moved to
    :data:`FILE_SHA256_FIELD`: a stored sound is the cut WAV, whose digest is the
    :class:`~an.sounds.SoundAsset`'s (an#623, an#729).

    >>> file_digest_fields({"provider": "p", "sha256": "ab"})
    {'provider': 'p', 'file_sha256': 'ab'}
    """
    out = dict(fields)
    if "sha256" in out:
        out[FILE_SHA256_FIELD] = out.pop("sha256")
    return out


def _provider_of(url: str) -> str:
    """``youtube`` for a YouTube page, else the host name (``web`` without one).

    >>> _provider_of("https://youtu.be/x"), _provider_of("https://www.youtube.com/watch?v=x")
    ('youtube', 'youtube')
    >>> _provider_of("https://archive.org/details/x")
    'archive.org'
    """
    host = (urlparse(url).hostname or "").removeprefix("www.").removeprefix("m.")
    if host in ("youtu.be", "youtube.com", "music.youtube.com"):
        return "youtube"
    return host or "web"


def yb_fetcher(url: str) -> Fetched:
    """Fetch the audio of ``url`` with ``yb`` (any site its ``yt-dlp`` reads)."""
    try:
        from yb import download_youtube_audio
    except ImportError as e:
        raise SoundError(
            "fetching a sound from a URL uses `yb` by default, which is not "
            "installed: pip install yb yt-dlp (or pass fetcher=… with your own)"
        ) from e
    with tempfile.TemporaryDirectory(prefix="an-fetch-") as tmp:
        result = download_youtube_audio(url, download_dir=tmp)
        audio = Path(result.path).read_bytes()
    info = result.info or {}
    page = info.get("webpage_url") or info.get("original_url") or url
    return Fetched(
        audio=audio,
        url=page,
        id=info.get("id"),
        title=info.get("title"),
        author=info.get("channel") or info.get("uploader"),
        provider=_provider_of(page),
    )


def foley_asset_source(
    rights: Mapping[str, Any], provenance: Mapping[str, Any], *, url: str | None = None
) -> AssetSource:
    """foley's ``(rights, provenance)`` (``foley.export_sound``) as an :class:`AssetSource`.

    ``rights`` is keyed by the source's own field names (foley pins them to
    ``lacing.Rights``, an's ``AssetSource``); its ``title`` rides as an extra.
    ``sha256`` is the exported bytes' digest, and the whole ``provenance``
    (JSON-safe) rides as :data:`FOLEY_PROVENANCE_FIELD`. ``url`` is where the
    bytes came from (``foley:<sound_id>``).

    >>> src = foley_asset_source(
    ...     {"provider": "fsd50k", "id": "222", "title": "Door creak", "license": "cc-by-4.0",
    ...      "attribution": "Door creak by amy", "author": None},
    ...     {"sha256": "ab", "archived_sha256": "cd", "ai_disclosure": None}, url="foley:fsd-222")
    >>> src.provider, src.license, src.url, src.author, src.sha256
    ('fsd50k', 'cc-by-4.0', 'foley:fsd-222', None, 'ab')
    >>> src.model_extra["title"], src.model_extra["foley_provenance"]["archived_sha256"]
    ('Door creak', 'cd')
    """
    fields = {
        **rights,
        "url": url,
        "sha256": provenance.get("sha256"),
        FOLEY_PROVENANCE_FIELD: json.loads(json.dumps(dict(provenance), default=str)),
    }
    return AssetSource(**{k: v for k, v in fields.items() if v is not None})


def _is_foley_ref(url: str) -> bool:
    """Whether ``url`` is a ``foley:<sound_id>`` ref (foley states its rights)."""
    return url.startswith(FOLEY_SCHEME)


def _foley_id(ref: str) -> str:
    """The sound id of a ``foley:<sound_id>`` ref.

    >>> _foley_id("foley:fsd-222")
    'fsd-222'
    """
    sound_id = ref[len(FOLEY_SCHEME) :].strip() if ref.startswith(FOLEY_SCHEME) else ""
    if not sound_id:
        raise SoundError(
            f"{ref!r} is not a foley ref: write {FOLEY_SCHEME}<sound_id> "
            "(the id of a sound in the foley library)"
        )
    return sound_id


def foley_fetcher(ref: str, *, export: Callable[[str], tuple] | None = None) -> Fetched:
    """Fetch ``foley:<sound_id>`` from a foley library, with the rights foley records.

    export: ``(sound_id) -> (bytes, rights, provenance)``, default
        ``foley.export_sound`` (its default library; bind another with
        ``functools.partial(foley.export_sound, library=...)``). foley is
        imported on first use: ``import an`` never imports it.

    The bytes are checked against the digest foley's provenance names, and the
    rights become :attr:`Fetched.source` (:func:`foley_asset_source`), the
    sound's only rights. It states rights for every ``foley:`` ref
    (``foley_fetcher.states_rights``).

    Raises:
        SoundError: For a ref that is not ``foley:<sound_id>``, foley not
            installed, a sound foley does not hold or will not export (its
            terms forbid keeping the bytes: a Freesound API pull is stored by
            reference; its bytes changed since ingest; a failed re-encode),
            naming the ref and foley's reason, or bytes that do not match the
            digest foley names.
    """
    sound_id = _foley_id(ref)
    if export is None:
        try:
            from foley import export_sound as export
        except ImportError as e:
            raise SoundError(
                "fetching a foley: sound needs foley: pip install foley "
                "(or pass export=... / fetcher=... with your own)"
            ) from e
    try:
        audio, rights, provenance = export(sound_id)
    except Exception as e:  # noqa: BLE001 — a refusal (ValueError), a missing sound, a failed encode
        raise SoundError(
            f"foley will not export {sound_id!r} ({ref}): {type(e).__name__}: {e}"
        ) from e
    if hashlib.sha256(audio).hexdigest() != provenance.get("sha256"):
        raise SoundError(
            f"foley's export of {sound_id!r} does not match the sha256 its "
            "provenance names; nothing was stored"
        )
    source = foley_asset_source(rights, provenance, url=ref)
    return Fetched(audio=audio, url=ref, source=source)


def default_fetcher(url: str) -> Fetched:
    """The default ``fetcher=``: :func:`foley_fetcher` for a ``foley:`` ref, else :func:`yb_fetcher`."""
    fetch = foley_fetcher if _is_foley_ref(url) else yb_fetcher
    return fetch(url)


foley_fetcher.states_rights = _is_foley_ref
default_fetcher.states_rights = _is_foley_ref


def cut_to_wav(
    audio: bytes,
    *,
    start: float | None = None,
    duration: float | None = None,
    fade_out: float | None = None,
) -> bytes:
    """``audio`` (any container ffmpeg reads) cut to ``[start, start + duration]``, as 16-bit WAV.

    ``fade_out``: seconds of linear fade at the end of the cut.
    """
    if shutil.which("ffmpeg") is None:
        raise SoundError(
            "cutting a fetched sound needs the ffmpeg binary on PATH "
            "(macOS: `brew install ffmpeg`; Debian/Ubuntu: `apt install ffmpeg`)"
        )
    for name, value in (
        ("start", start),
        ("duration", duration),
        ("fade_out", fade_out),
    ):
        if value is not None and value < 0:
            raise SoundError(f"{name} must not be negative, got {value}")
    with tempfile.TemporaryDirectory(prefix="an-cut-") as tmp:
        out = Path(tmp) / "cut.wav"
        argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-i", "pipe:0"]  # fmt: skip
        if start:
            argv += ["-ss", f"{start:.6f}"]
        if duration is not None:
            argv += ["-t", f"{duration:.6f}"]
        argv += ["-vn", "-ar", str(FETCH_SAMPLE_RATE), "-map_metadata", "-1",
                 "-c:a", "pcm_s16le", str(out)]  # fmt: skip
        proc = subprocess.run(argv, input=audio, capture_output=True, check=False)
        if proc.returncode != 0 or not out.exists():
            raise SoundError(
                f"ffmpeg could not cut the fetched audio: "
                f"{proc.stderr.decode(errors='replace').strip()[-400:]}"
            )
        wav = out.read_bytes()
    return _fade_out(wav, fade_out) if fade_out else wav


def _fade_out(wav: bytes, seconds: float) -> bytes:
    """``wav`` (16-bit PCM) with its last ``seconds`` faded linearly to silence."""
    import io
    import wave

    import numpy as np

    with wave.open(io.BytesIO(wav), "rb") as w:
        params = w.getparams()
        samples = np.frombuffer(w.readframes(w.getnframes()), "<i2").copy()
    channels = params.nchannels
    frames = samples.reshape(-1, channels)
    n = min(len(frames), round(seconds * params.framerate))
    if n:
        ramp = np.linspace(1.0, 0.0, n, endpoint=False)[:, None]
        frames[-n:] = np.round(frames[-n:] * ramp).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(frames.astype("<i2").tobytes())
    return out.getvalue()


def cut_record(
    wav: bytes, *, start: float | None = None, fade_out: float | None = None
) -> dict[str, float]:
    """The ``cut`` a source records for ``wav``, cut from ``start`` (seconds of
    the media) with ``fade_out``: what ``an credits`` shows as "0:07.9–0:08.8".
    Shared by every path that stores a cut (a URL, an acquired track, an#623)."""
    begin = float(start or 0.0)
    cut = {"start": round(begin, 3), "end": round(begin + wav_duration(wav), 3)}
    if fade_out:
        cut["fade_out"] = float(fade_out)
    return cut


def _license_code(license: str | None) -> str | None:
    """The code a caller's licence records: ``None`` (UNKNOWN) for ``unknown`` or nothing."""
    return None if license in (None, "", "unknown") else license


def _stated_fields(
    stated: AssetSource,
    *,
    license: str | None | Unstated,
    provider: str | None,
    author: str | None,
) -> dict[str, Any]:
    """The fields of a source that states its own rights, checked against the caller's.

    The source's rights are complete: a licence the caller gives must name the
    same code (case and punctuation aside), and no provider or author may be
    set over them (an AI clip has no author to add).
    """
    fields = stated.model_dump(exclude_none=True)
    if license is not UNSTATED and _same_code(_license_code(license), stated.license):
        license = UNSTATED
    given = {} if license is UNSTATED else {"license": _license_code(license)}
    given |= {k: v for k, v in (("provider", provider), ("author", author)) if v}
    for name, value in given.items():
        raise SoundError(
            f"the source states its own rights ({name}={fields.get(name)!r}), and "
            f"the caller says {name}={value!r}: they are not overridden; leave "
            f"{name} out, or use another copy of the sound"
        )
    return file_digest_fields(fields)


def _same_code(a: str | None, b: str | None) -> bool:
    """Whether two licence codes are the same code, case and punctuation aside.

    >>> _same_code("CC-BY-4.0", "cc-by-4.0"), _same_code(None, "cc0-1.0")
    (True, False)
    """
    return normalise_license(a or "") == normalise_license(b or "")


def _refuse_unstated(url: str) -> None:
    raise SoundError(
        f"{url!r}: the licence is required, since this source states none "
        "(license=..., --license on the command line: the code you vouch for; "
        "'unknown' records that nobody has said, and the sound is UNVERIFIED)"
    )


def add_sound_from_url(
    store: MutableMapping,
    key: str,
    url: str,
    *,
    license: str | None | Unstated = UNSTATED,
    fetcher: Fetcher | None = None,
    start: float | None = None,
    duration: float | None = None,
    fade_out: float | None = None,
    provider: str | None = None,
    author: str | None = None,
    description: str = "",
) -> SoundAsset:
    """Fetch ``url``, cut it, and put it in the sounds ``store`` under ``key`` with its provenance.

    license: the licence code the caller vouches for, never guessed;
        ``"unknown"`` (or ``None``) records that nobody has said. Required
        unless the source states its own rights (:attr:`Fetched.source`, a
        ``foley:`` sound), which are then recorded; a licence given with them
        must agree
    fetcher: ``(url) -> Fetched`` (default :func:`default_fetcher`: a
        ``foley:<sound_id>`` ref from foley, anything else with ``yb``)
    start, duration, fade_out: the cut, in seconds of the fetched media
    provider, author: override what the fetcher reported (never on a source
        that states its rights)

    No cut is recorded when the whole media is kept (no ``start``,
    ``duration`` or ``fade_out``).

    Raises:
        SoundError: For no licence for a ref the fetcher states no rights for
            (before anything is fetched: :func:`fetcher_states_rights`), or from
            a source that turned out to state none; a caller's licence that
            contradicts the source's, or a provider or author set over it; and
            whatever the fetch, the cut or the store refuse.
    """
    fetcher = fetcher or default_fetcher
    if license is UNSTATED and not fetcher_states_rights(fetcher, url):
        _refuse_unstated(url)
    fetched = fetcher(url)
    if fetched.source is None and license is UNSTATED:
        _refuse_unstated(url)
    wav = cut_to_wav(fetched.audio, start=start, duration=duration, fade_out=fade_out)
    if fetched.source is not None:
        fields = _stated_fields(
            fetched.source, license=license, provider=provider, author=author
        )
    else:
        fields = {
            "provider": provider or fetched.provider,
            "id": fetched.id,
            "author": author or fetched.author,
            "license": _license_code(license),
            **({TITLE_FIELD: fetched.title} if fetched.title else {}),
        }
    fields.setdefault("url", fetched.url)
    if any(v is not None for v in (start, duration, fade_out)):
        fields[CUT_FIELD] = cut_record(wav, start=start, fade_out=fade_out)
    return add_sound(
        store, key, wav, source=AssetSource(**fields), description=description
    )


def _foley_provenance(source: AssetSource) -> Mapping[str, Any]:
    """The foley provenance a source records (:data:`FOLEY_PROVENANCE_FIELD`), or ``{}``."""
    prov = (source.model_extra or {}).get(FOLEY_PROVENANCE_FIELD)
    return prov if isinstance(prov, Mapping) else {}


def ai_label(source: AssetSource) -> str | None:
    """What an AI-generated source's disclosure says, or ``None`` for any other.

    The model; whether the disclosure is a duty (a recognizable voice: "must be
    disclosed") or a recommendation; and, when foley's EU AI Act Art. 50
    checklist is not ``publish_ready``, the obligations still pending.

    >>> ai = {"is_ai_generated": True, "publish_ready": False,
    ...       "pending": ["machine_readable_mark", "provenance_manifest"],
    ...       "obligations": {"voice_disclosure": {"required": False}},
    ...       "provenance": {"generator_model": "stable-audio-open-1.0"}}
    >>> ai_label(AssetSource(provider="stability-ai", foley_provenance={"ai_disclosure": ai}))
    'AI-generated with stable-audio-open-1.0: disclosure recommended; not publish-ready, Art. 50 pending: machine_readable_mark, provenance_manifest'
    >>> ai_label(AssetSource(provider="fsd50k")) is None
    True
    """
    ai = _foley_provenance(source).get(AI_DISCLOSURE_KEY)
    if not isinstance(ai, Mapping) or not ai.get("is_ai_generated"):
        return None
    model = (ai.get("provenance") or {}).get("generator_model")
    voice = (ai.get("obligations") or {}).get("voice_disclosure") or {}
    duty = "must be disclosed" if voice.get("required") else "disclosure recommended"
    label = f"AI-generated{f' with {model}' if model else ''}: {duty}"
    if ai.get("publish_ready") is False:
        pending = ", ".join(ai.get("pending") or ()) or "see foley's checklist"
        label += f"; not publish-ready, Art. 50 pending: {pending}"
    return label


def notice_label(source: AssetSource) -> str | None:
    """The notice a source's licence requires shown verbatim, or ``None``.

    >>> notice_label(AssetSource(provider="p", foley_provenance={"notice_text_required": "(c) X"}))
    '(c) X'
    """
    notice = _foley_provenance(source).get(NOTICE_KEY)
    return notice.strip() if isinstance(notice, str) and notice.strip() else None


def cut_label(source: AssetSource) -> str | None:
    """``"0:07.9–0:08.8 of <url>"`` for a source with a recorded cut, else ``None``.

    >>> cut_label(AssetSource(provider="youtube", url="https://youtu.be/x",
    ...                       cut={"start": 7.9, "end": 8.75}))
    '0:07.9–0:08.8 of https://youtu.be/x'
    """
    cut = (source.model_extra or {}).get(CUT_FIELD)
    if not isinstance(cut, dict) or "start" not in cut or "end" not in cut:
        return None

    def clock(t: float) -> str:
        minutes, seconds = divmod(float(t), 60)
        return f"{int(minutes)}:{seconds:04.1f}"

    where = source.source_page_url or source.url or source.id or source.provider
    return f"{clock(cut['start'])}–{clock(cut['end'])} of {where}"
