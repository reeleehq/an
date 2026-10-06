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
  ``"unknown"`` says so explicitly (the sound is then UNVERIFIED).

>>> fetched = Fetched(audio=b"...", url="https://example.org/a", id="a", author="Ann")
>>> fetched.provider
'web'
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from an.ir.assets import AssetSource
from an.sounds import SoundAsset, SoundError, add_sound, wav_duration

__all__ = ["Fetched", "Fetcher", "add_sound_from_url", "cut_to_wav", "yb_fetcher"]

#: The source field (an ``AssetSource`` extra) recording which part of the
#: fetched media the sound is: ``{"start": s, "end": s, "fade_out": s}``.
CUT_FIELD: str = "cut"
#: The source field holding the fetched media's own title.
TITLE_FIELD: str = "title"
#: The sample rate a fetched sound is stored at.
FETCH_SAMPLE_RATE: int = 44100


@dataclass(frozen=True)
class Fetched:
    """What a fetcher returns: the media's bytes, and what its page says about it."""

    audio: bytes
    url: str
    id: str | None = None
    title: str | None = None
    author: str | None = None
    #: Where it came from, as an ``AssetSource.provider`` (``youtube``, …).
    provider: str = "web"


#: ``(url) -> Fetched``: how :func:`add_sound_from_url` gets the media.
Fetcher = Callable[[str], Fetched]


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
    for name, value in (("start", start), ("duration", duration), ("fade_out", fade_out)):
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


def add_sound_from_url(
    store: MutableMapping,
    key: str,
    url: str,
    *,
    license: str | None,
    fetcher: Fetcher | None = None,
    start: float | None = None,
    duration: float | None = None,
    fade_out: float | None = None,
    provider: str | None = None,
    author: str | None = None,
    description: str = "",
) -> SoundAsset:
    """Fetch ``url``, cut it, and put it in the sounds ``store`` under ``key`` with its provenance.

    license: the licence code the caller vouches for — required, never
        guessed; ``"unknown"`` (or ``None``) records that nobody has said
    fetcher: ``(url) -> Fetched`` (default :func:`yb_fetcher`)
    start, duration, fade_out: the cut, in seconds of the fetched media
    provider, author: override what the fetcher reported
    """
    fetched = (fetcher or yb_fetcher)(url)
    wav = cut_to_wav(fetched.audio, start=start, duration=duration, fade_out=fade_out)
    begin = float(start or 0.0)
    cut = {"start": round(begin, 3), "end": round(begin + wav_duration(wav), 3)}
    if fade_out:
        cut["fade_out"] = float(fade_out)
    code = None if license in (None, "", "unknown") else license
    source = AssetSource(
        provider=provider or fetched.provider,
        id=fetched.id,
        url=fetched.url,
        author=author or fetched.author,
        license=code,
        **{CUT_FIELD: cut, **({TITLE_FIELD: fetched.title} if fetched.title else {})},
    )
    return add_sound(store, key, wav, source=source, description=description)


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

    where = source.url or source.id or source.provider
    return f"{clock(cut['start'])}–{clock(cut['end'])} of {where}"
