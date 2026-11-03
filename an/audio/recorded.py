"""Recorded voices: a performer's takes as the voice of a character (an#490).

A production that records its actors has the voices already; nothing should be
synthesized, billed, or approximated. This module makes a recording a
first-class input, through the seams the audio pipeline already has:

- **The take is a voice.** :class:`RecordedTTS` is a :class:`~an.audio.tts.TTSProvider`
  named ``recorded`` whose "synthesis" is a lookup in the project's
  ``recordings`` store (:class:`~an.stores.recordings.RecordingsStore`). A voice
  document that declares ``provider: recorded`` is spoken by it (an#305), so
  takes, effects, leveling, captions, the shot cache and ``an render`` work
  unchanged, and nothing is billed: the provider declares ``billed = False``
  and ``repeatable = True``. Its ``synthesis_options`` hook keys each line by
  the digest of the take it has for it, so a re-recorded line is a new audio
  key, never a stale cache hit.
- **The words travel with the clip.** A take imported with a timed transcript
  (or transcribed) knows its word timings; they are stored with it, handed to
  the pipeline on :attr:`~an.audio.tts.AudioClip.words`, and a lip-sync
  provider that aligns from words (``cutan``'s) uses them instead of its own
  transcription — the mouth follows the performance.
- **Import** (:func:`import_recordings`, ``an voices import``): one or more
  audio files — a whole take with several lines, or one file per line — with an
  optional transcript (SRT, WebVTT, TextGrid, word JSON or plain text:
  :mod:`an.audio.transcripts`). Each line of the recording is cut out, matched
  to the scene's dialogue by its words (a line the scene does not have yet is
  added to the shot you name), and stored with its provenance: who recorded it,
  under which licence or permission, from which file and span. The speaker's
  character is bound to the recorded voice; the gap heard between two lines
  becomes the next line's ``pause``, so the shot's timing follows the recording.

Seams, each one keyword argument of :func:`import_recordings`:

- ``transcribe``: a callable ``path -> segments`` for a take that comes with no
  timed transcript; the default is scribed's facade (``pip install
  "an[recorded]"``, then a backend of your choice — words and, where the
  backend has it, speakers). Not needed for one file per line or a timed
  transcript: those paths run with no model at all.
- ``denoise``: off; a strategy name runs the matching ffmpeg filter
  (:data:`DENOISE_FILTERS`) before anything else; ``voxy.refprep.condition`` is
  the fuller conditioning when you want more.
- Speaker attribution: ``speaker`` (one performer), ``speakers`` (a label →
  character map, for a diarizer's or a transcript's labels and file stems), the
  transcript's own ``speaker:`` prefixes, the file's stem, or the scene line
  the words match.

>>> from an.audio.tts import AudioClip
>>> tts = RecordedTTS()
>>> tts.name, tts.billed, tts.repeatable
('recorded', False, True)
>>> normalize_key_text("Hello, there!") == normalize_key_text("hello there")
True
"""

from __future__ import annotations

import datetime as _dt
import difflib
import hashlib
import json
import io
import re
import shutil
import subprocess
import tempfile
import warnings
import wave
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, NamedTuple, Protocol, runtime_checkable

from an.audio.transcripts import (
    ARPABET,
    IPA,
    TranscriptSegment,
    WordTiming,
    align_words,
    cut_spans,
    from_transcript_object,
    normalize_text,
    parse_transcript,
    parse_transcript_text,
    rebase_words,
    segment_lines,
    tokens_of,
)
from an.audio.tts import AudioClip, VoiceMeta
from an.stores.transcripts import (
    LinkedTranscript,
    TranscriptLinkError,
    is_artifact_ref,
    linked_transcript,
)
from an.ir.assets import AssetSource
from an.ir.sync import DEFAULT_SCENE_FILE

__all__ = [
    "PROVIDER_NAME",
    "RECORDINGS_STORE",
    "RECORDING_OPTION",
    "RECORD_VERSION",
    "RECORDED_VOICE_SUFFIX",
    "DENOISE_FILTERS",
    "DFLT_DENOISE",
    "DFLT_MATCH_THRESHOLD",
    "RecordedVoicesError",
    "RecordedVoicesWarning",
    "RecordingMissingError",
    "TranscriberUnavailableError",
    "RecordedTTS",
    "ImportedTake",
    "ImportReport",
    "import_recordings",
    "add_recording",
    "find_recording",
    "recording_by_digest",
    "read_recording",
    "recording_key",
    "normalize_key_text",
    "audio_paths",
    "scribed_transcriber",
    "load_wav",
    "cut_wav",
    "wav_seconds",
]

#: The TTS provider's name: what a voice document's ``provider`` says.
PROVIDER_NAME: str = "recorded"
#: The mall store the takes live in (``assets/recordings/<key>/``).
RECORDINGS_STORE: str = "recordings"
#: The ``synthesize`` keyword (and audio-key option) naming the take by digest.
RECORDING_OPTION: str = "recording"
#: The audio-key option of a take with phones: a digest of its words and
#: phones, so new timings on the same audio re-sync (an#491).
TIMINGS_OPTION: str = "timings"
#: The shape of a record in the store; raised when a field changes meaning.
RECORD_VERSION: int = 1
#: The voice document a speaker's takes are bound to, when ``voice`` names none.
RECORDED_VOICE_SUFFIX: str = "_recorded"
#: How alike (``difflib`` ratio over normalized words) a take's words and a
#: scene line must be for the take to be that line's.
DFLT_MATCH_THRESHOLD: float = 0.75
#: ``denoise`` strategies → the ffmpeg filter that runs (voxy.refprep's table).
DENOISE_FILTERS: dict[str, str] = {"afftdn": "afftdn", "anlmdn": "anlmdn"}
#: The strategy a bare request for denoising means.
DFLT_DENOISE: str = "afftdn"
#: What a take DECODED by ffmpeg (a non-WAV file, or any file when denoising)
#: is resampled to, mono 16-bit: the film mix's rate. A 16-bit PCM WAV is kept
#: as it is, whatever its rate and channels.
IMPORT_SAMPLE_RATE: int = 44100
#: Files :func:`audio_paths` takes from a directory.
AUDIO_SUFFIXES: frozenset[str] = frozenset(
    {
        ".wav",
        ".mp3",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".opus",
        ".aif",
        ".aiff",
        ".mp4",
        ".mov",
        ".webm",
        ".mkv",
    }
)
#: Transcript files :func:`import_recordings` pairs with a take by stem.
TRANSCRIPT_SUFFIXES: tuple[str, ...] = (".srt", ".vtt", ".json", ".textgrid", ".txt")
#: The ``AssetSource.provider`` of a take: a person, not a service.
SOURCE_PROVIDER: str = "recording"
#: The remedy named by every "no recording" error.
IMPORT_HINT: str = (
    "import one with `an voices import <project> <audio> --speaker <character> "
    "--license <code> [--transcript <file>]`, or give the line another voice"
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SLUG_LEN: int = 32
_STEM_SPLIT_RE = re.compile(r"[-_. ]")


class RecordedVoicesError(RuntimeError):
    """An import, or a lookup of a take, that cannot proceed; the message says what to do."""


class RecordedVoicesWarning(UserWarning):
    """An import that went ahead in a weaker form than asked; the message says
    what was lost and what to do (an#716)."""


class RecordingMissingError(RecordedVoicesError):
    """A line spoken by a recorded voice has no take in the store."""


class TranscriberUnavailableError(RecordedVoicesError):
    """A take needs transcribing and no transcriber can run here."""


class AlignmentError(RecordedVoicesError):
    """A forced aligner ran and could not align a take with its text (an#637)."""


# --- the store's front door -----------------------------------------------------


def normalize_key_text(text: str) -> str:
    """The form a line's text is matched by: :func:`~an.audio.transcripts.normalize_text`."""
    return normalize_text(text)


def recording_key(speaker: str, text: str, sha256: str) -> str:
    """A readable, unique store key: ``<speaker>--<words>--<digest prefix>``.

    >>> recording_key("carl", "Hello, there!", "1a2b3c4d5e6f")
    'carl--hello-there--1a2b3c4d'
    """
    slug = (
        _SLUG_RE.sub("-", text.casefold()).strip("-")[:_SLUG_LEN].rstrip("-") or "line"
    )
    who = _SLUG_RE.sub("-", speaker.casefold()).strip("-") or "speaker"
    return f"{who}--{slug}--{sha256[:8]}"


def find_recording(
    store: Mapping | None, voice: str, text: str
) -> tuple[str, dict] | None:
    """The newest take of ``text`` for ``voice`` in ``store``, as ``(key, record)``; ``None`` if none.

    Texts are compared normalized (case and punctuation aside), so a comma
    added in ``scene.md`` does not orphan the take.
    """
    if store is None:
        return None
    wanted = normalize_key_text(text)
    best: tuple[str, str, dict] | None = None
    for key in store:
        record = store[key]
        if not isinstance(record, Mapping) or record.get("voice") != voice:
            continue
        if normalize_key_text(str(record.get("text", ""))) != wanted:
            continue
        stamp = str(record.get("imported_at") or "")
        if best is None or stamp > best[0]:
            best = (stamp, key, dict(record))
    return (best[1], best[2]) if best else None


def recording_by_digest(
    store: Mapping | None, sha256: str, *, text: str | None = None
) -> tuple[str, dict] | None:
    """The take whose audio has ``sha256``, as ``(key, record)``; ``None`` if none.

    The same bytes may be stored under two records (a take re-imported with its
    text corrected): ``text`` picks the record whose text it is, so the line
    gets its own words.
    """
    if store is None:
        return None
    found: list[tuple[str, dict]] = []
    for key in store:
        record = store[key]
        if isinstance(record, Mapping) and record.get("sha256") == sha256:
            found.append((key, dict(record)))
    if not found:
        return None
    if text is not None:
        wanted = normalize_key_text(text)
        for key, record in found:
            if normalize_key_text(str(record.get("text", ""))) == wanted:
                return key, record
    return found[0]


def read_recording(store: Mapping, key: str) -> tuple[dict, bytes]:
    """``(record, wav_bytes)`` for ``key``, the bytes checked against the record's digest.

    The licence is attached to the digest: different bytes under the key are a
    take nobody vouched for, and are refused.
    """
    try:
        record = dict(store[key])
    except KeyError:
        raise RecordingMissingError(
            f"no recording {key!r} in the store; {IMPORT_HINT}"
        ) from None
    audio = store.read_audio(key)
    digest = hashlib.sha256(audio).hexdigest()
    if record.get("sha256") and record["sha256"] != digest:
        raise RecordedVoicesError(
            f"recording {key!r}: its audio's digest ({digest[:12]}…) is not the one its "
            f"record vouches for ({str(record['sha256'])[:12]}…); re-import it"
        )
    return record, audio


def add_recording(
    store: MutableMapping,
    *,
    voice: str,
    speaker: str,
    text: str,
    audio: bytes,
    source: AssetSource | Mapping[str, Any],
    words: Iterable[WordTiming] | None = None,
    imported_at: str | None = None,
    phones: Iterable[WordTiming] | None = None,
    phone_alphabet: str | None = None,
) -> tuple[str, dict]:
    """Put a take (WAV ``audio`` of ``speaker`` saying ``text``, spoken for
    ``voice``) in ``store`` with its provenance; ``(key, record)``.

    ``source`` is required: a recording with no recorded origin is exactly the
    asset ``an credits`` cannot vouch for.
    """
    from an.sounds import wav_info, well_formed_wav

    source = AssetSource.model_validate(source)
    audio = well_formed_wav(audio)
    sample_rate, channels, frames = wav_info(audio)
    if not frames:
        raise RecordedVoicesError(f"the take of {text!r} holds no audio (0 frames)")
    digest = hashlib.sha256(audio).hexdigest()
    key = recording_key(speaker, text, digest)
    record = {
        "record_version": RECORD_VERSION,
        "voice": voice,
        "speaker": speaker,
        "text": text,
        "duration": frames / sample_rate,
        "sample_rate": sample_rate,
        "channels": channels,
        "sha256": digest,
        "words": _timings(words),
        **({"phones": _timings(phones)} if phones else {}),  # an#491
        # the alphabet the phones are in, when the aligner said (an#637)
        **({"phone_alphabet": phone_alphabet} if phones and phone_alphabet else {}),
        "source": source.model_dump(exclude_none=True),
        "imported_at": imported_at
        or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="microseconds"),
    }
    store[key] = record
    store.write_audio(key, audio)
    return key, record


def _timings(timings: Iterable[WordTiming] | None) -> list | None:
    """Timings as a record stores them: ``[[label, start, end], ...]``."""
    return [[t[0], float(t[1]), float(t[2])] for t in timings] if timings else None


def _read_timings(stored: Any) -> list[WordTiming] | None:
    """A record's ``[[label, start, end], ...]`` back as tuples (``None`` when absent)."""
    return [(str(t[0]), float(t[1]), float(t[2])) for t in stored] if stored else None


# --- the provider --------------------------------------------------------------


class RecordedTTS:
    """The ``recorded`` TTS provider: a line's audio is the take imported for it.

    Built by :func:`an.audio.providers.make_tts` with the project mall, so it
    reads ``mall["recordings"]``; the pipeline hands it each line's text and
    voice through :meth:`synthesis_options` (which keys the line by its take's
    digest) and :meth:`synthesize`. A line with no take raises
    :class:`RecordingMissingError` before anything else is touched — a recorded
    voice never falls back to a synthesized one.

    >>> RecordedTTS().check_available()
    Traceback (most recent call last):
        ...
    an.audio.recorded.RecordedVoicesError: the recorded provider has no recordings store ...
    """

    name: str = PROVIDER_NAME
    #: The same request gives the same bytes, and nothing is billed (an#311).
    repeatable: bool = True
    billed: bool = False
    silent: bool = False

    def __init__(self, *, recordings: Mapping | None = None) -> None:
        self.recordings = recordings
        self._digests: dict[str, str] | None = None

    # -- TTSProvider -------------------------------------------------------------

    def check_available(self) -> None:
        if self.recordings is None:
            raise RecordedVoicesError(
                "the recorded provider has no recordings store (it is built from a "
                "project: `make_tts('recorded', mall=mall)`, which the render does)"
            )

    def list_voices(self) -> list[VoiceMeta]:
        """One entry per voice that has takes in the store."""
        if self.recordings is None:
            return []
        seen: dict[str, int] = {}
        for key in self.recordings:
            record = self.recordings[key]
            if isinstance(record, Mapping) and record.get("voice"):
                seen[str(record["voice"])] = seen.get(str(record["voice"]), 0) + 1
        return [
            VoiceMeta(
                voice_id=v,
                name=v,
                provider=self.name,
                extra={"takes": n},
                is_stock=False,  # a performer's own takes (an#712)
            )
            for v, n in sorted(seen.items())
        ]

    def synthesis_options(
        self,
        voice_doc: Mapping[str, Any],
        *,
        emotion: str | None = None,
        direction: Sequence[str] | None = None,
        text: str | None = None,
        voice_id: str | None = None,
    ) -> dict[str, Any]:
        """``{"recording": <digest>}`` of the take this line has — the audio key
        follows the take, so a re-recorded line is new audio. A take with
        phones adds ``{"timings": <digest>}`` of its words and phones (an#491):
        the same audio imported again with new timings is new audio to the
        caches, so the lip-sync sees them. (Only then: a take without phones
        keys as before.)

        A line with no take is refused HERE, when the pipeline resolves every
        line's request before the first synthesis: nothing of the scene is
        produced for a recorded voice that is missing a take. Without a line
        (``an validate`` asks about the voice alone) there is nothing to refuse.
        """
        if self.recordings is None or text is None or voice_id is None:
            return {}
        found = find_recording(self.recordings, voice_id, text)
        if found is None:
            raise RecordingMissingError(
                f"voice {voice_id!r} is recorded, but there is no take of {text!r}; {IMPORT_HINT}"
            )
        record = found[1]
        options = {RECORDING_OPTION: record["sha256"]}
        if record.get("phones"):
            options[TIMINGS_OPTION] = hashlib.sha256(
                json.dumps([record.get("words"), record["phones"]]).encode()
            ).hexdigest()
        return options

    def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        *,
        recording: str | None = None,
        **kw: Any,
    ) -> AudioClip:
        """The take of ``text`` in ``voice_id`` (by ``recording`` digest when given), with its words."""
        self.check_available()
        found = (
            recording_by_digest(self.recordings, recording, text=text)
            if recording
            else find_recording(self.recordings, voice_id, text)
        )
        if found is None:
            raise RecordingMissingError(
                f"voice {voice_id!r} is recorded, but there is no take of {text!r}"
                + (f" (digest {recording[:12]}…)" if recording else "")
                + f"; {IMPORT_HINT}"
            )
        key, _ = found
        record, audio = read_recording(self.recordings, key)
        return AudioClip(
            bytes_=audio,
            duration=float(record["duration"]),
            sample_rate=int(record.get("sample_rate") or IMPORT_SAMPLE_RATE),
            channels=int(record.get("channels") or 1),
            voice_id=voice_id,
            transcript=text,
            words=_read_timings(record.get("words")),
            phones=_read_timings(record.get("phones")),
        )

    # -- the pipeline's read-back hook ------------------------------------------

    def words_for_clip(self, clip: AudioClip) -> list[WordTiming] | None:
        """The stored words of the take whose bytes ``clip`` carries, or ``None``."""
        record = self._record_for_clip(clip)
        return _read_timings(record.get("words")) if record else None

    def phones_for_clip(self, clip: AudioClip) -> list[WordTiming] | None:
        """The stored phones of the take whose bytes ``clip`` carries, or ``None`` (an#491)."""
        record = self._record_for_clip(clip)
        return _read_timings(record.get("phones")) if record else None

    def _record_for_clip(self, clip: AudioClip) -> Mapping[str, Any] | None:
        """The record of the take whose bytes ``clip`` carries, or ``None``."""
        if self.recordings is None or clip.bytes_ is None:
            return None
        digest = hashlib.sha256(clip.bytes_).hexdigest()
        key = self._index().get(digest)
        if key is None:
            self._digests = None  # a take imported since: look again, once
            key = self._index().get(digest)
        return self.recordings[key] if key is not None else None

    def _index(self) -> dict[str, str]:
        if self._digests is None:
            self._digests = {}
            for key in self.recordings or ():
                record = self.recordings[key]
                if isinstance(record, Mapping) and record.get("sha256"):
                    self._digests[str(record["sha256"])] = key
        return self._digests


# --- audio files ------------------------------------------------------------------


def audio_paths(audio: str | Path | Sequence[str | Path]) -> list[Path]:
    """The audio files ``audio`` names: a file, a directory (its audio files,
    sorted), a glob, a comma-separated list, or a sequence of those.

    >>> audio_paths([])
    []
    """
    if isinstance(audio, (str, Path)):
        literal = Path(str(audio)).expanduser()
        items: list[str | Path] = (
            [part.strip() for part in str(audio).split(",") if part.strip()]
            if isinstance(audio, str) and "," in audio and not literal.exists()
            else [audio]
        )
    else:
        items = list(audio)
    out: list[Path] = []
    for item in items:
        p = Path(item).expanduser()
        if p.is_dir():
            out += sorted(
                c
                for c in p.iterdir()
                if c.is_file() and c.suffix.lower() in AUDIO_SUFFIXES
            )
        elif p.is_file():
            out.append(p)
        elif any(ch in str(p) for ch in "*?["):
            out += sorted(c for c in p.parent.glob(p.name) if c.is_file())
        else:
            raise RecordedVoicesError(f"no such audio file or directory: {p}")
    return out


def wav_seconds(wav: bytes) -> float:
    """The length of a PCM WAV, seconds."""
    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.getnframes() / w.getframerate()


def cut_wav(wav: bytes, start: float, end: float) -> bytes:
    """The frames of ``wav`` between ``start`` and ``end`` seconds, as a WAV of the same format.

    >>> import struct
    >>> buf = io.BytesIO()
    >>> with wave.open(buf, "wb") as w:
    ...     w.setnchannels(1); w.setsampwidth(2); w.setframerate(100)
    ...     w.writeframes(struct.pack("<100h", *range(100)))
    >>> round(wav_seconds(cut_wav(buf.getvalue(), 0.25, 0.5)), 2)
    0.25
    """
    with wave.open(io.BytesIO(wav), "rb") as w:
        rate, channels, width, frames = (
            w.getframerate(),
            w.getnchannels(),
            w.getsampwidth(),
            w.getnframes(),
        )
        a = max(0, min(frames, int(round(start * rate))))
        b = max(a, min(frames, int(round(end * rate))))
        w.setpos(a)
        data = w.readframes(b - a)
    out = io.BytesIO()
    with wave.open(out, "wb") as o:
        o.setnchannels(channels)
        o.setsampwidth(width)
        o.setframerate(rate)
        o.writeframes(data)
    return out.getvalue()


def _is_pcm16_wav(data: bytes) -> bool:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            return w.getsampwidth() == 2 and w.getnframes() > 0
    except (wave.Error, EOFError):
        return False


def load_wav(path: Path, *, denoise: str | None = None) -> bytes:
    """``path`` as 16-bit PCM WAV bytes: a PCM WAV is taken as it is; anything
    else (MP3, M4A, a video's audio) is decoded with ffmpeg to mono at
    :data:`IMPORT_SAMPLE_RATE`; ``denoise`` (a key of :data:`DENOISE_FILTERS`)
    runs that filter first, which also goes through ffmpeg.
    """
    if denoise is not None and denoise not in DENOISE_FILTERS:
        raise RecordedVoicesError(
            f"unknown denoise strategy {denoise!r}; known: {sorted(DENOISE_FILTERS)}"
        )
    data = Path(path).read_bytes()
    if denoise is None and _is_pcm16_wav(data):
        return data
    if shutil.which("ffmpeg") is None:
        raise RecordedVoicesError(
            f"decoding {Path(path).name}"
            + (" with denoising" if denoise else "")
            + " needs the ffmpeg binary on PATH (macOS: `brew install ffmpeg`; "
            "Debian/Ubuntu: `apt install ffmpeg`), or give a 16-bit PCM WAV"
        )
    filters = [DENOISE_FILTERS[denoise]] if denoise else []
    filters.append(f"aresample={IMPORT_SAMPLE_RATE}")
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "take.wav"
        argv = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(path), "-vn", "-af", ",".join(filters), "-ac", "1",
            "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact",
            "-c:a", "pcm_s16le", str(out_path),
        ]  # fmt: skip
        proc = subprocess.run(argv, capture_output=True, check=False)
        if proc.returncode != 0 or not out_path.exists():
            raise RecordedVoicesError(
                f"ffmpeg could not decode {Path(path).name}: {proc.stderr.decode(errors='replace').strip()}"
            )
        return out_path.read_bytes()


# --- transcribing -------------------------------------------------------------------

#: ``path -> segments``: what the ``transcribe`` seam takes.
Transcriber = Callable[[Path], Sequence[TranscriptSegment]]


class Aligner(Protocol):
    """What the ``align`` seam takes (an#637): a forced aligner, which times a
    KNOWN ``text`` against the audio at ``path`` (a WAV) and gives each
    segment's words and phones, as a TextGrid with a ``phones`` tier would.
    ``phone_alphabet`` (``"arpabet"``, ``"ipa"``, ``None`` unknown) is stored
    beside the phones on the take's record."""

    @property
    def phone_alphabet(self) -> str | None: ...

    def __call__(self, path: Path, text: str) -> Sequence[TranscriptSegment]: ...


@runtime_checkable
class LineAligner(Protocol):
    """An :class:`Aligner` that can also align each of several ROUGHLY timed
    lines within its own interval (an#716): what a long take of many lines
    needs, since a forced aligner is built for short utterances. ``lines``
    are timed (``start``/``end``, seconds in the take at ``path``)."""

    def align_lines(
        self, path: Path, lines: Sequence[TranscriptSegment]
    ) -> Sequence[TranscriptSegment]: ...


#: Silence kept on each side of a roughly timed line when a line aligner aligns
#: it within its own interval (an#716): a transcriber's word edges are rough,
#: and a line cut short would lose its first or last phone.
DFLT_ALIGN_LINE_PAD_S: float = 0.25
#: The least share of a plain transcript's words the transcriber must hear
#: (:attr:`~an.audio.transcripts.AlignedWords.coverage`) for its rough line
#: times to be trusted (an#716): below it the times are guesses, and the lines
#: are aligned as one utterance instead.
DFLT_ROUGH_MIN_COVERAGE: float = 0.5
#: The shortest a roughly timed line may be, seconds (an#716): a line the
#: transcriber did not hear is squeezed between its neighbours, and an
#: interval that narrow holds no line to align.
DFLT_ROUGH_MIN_LINE_S: float = 0.1
#: The Montreal Forced Aligner's English models (an#637): one pronouncing
#: dictionary and acoustic model per phone alphabet, both named the same.
MFA_MODELS: Mapping[str, str] = {ARPABET: "english_us_arpa", IPA: "english_mfa"}
DFLT_MFA_ALPHABET: str = ARPABET
#: MFA 3's alignment subcommand (4.0 renames it ``align_legacy``): a keyword
#: of :func:`mfa_aligner`, so a newer MFA is a keyword away.
DFLT_MFA_COMMAND: str = "align"
#: The file stem the take and its text get in MFA's one-file corpus.
MFA_TAKE_STEM: str = "take"
#: How MFA is installed, and its models fetched: said when it is not found.
MFA_INSTALL_HINT: str = (
    "install the Montreal Forced Aligner (`conda install -c conda-forge "
    "montreal-forced-aligner`, https://montreal-forced-aligner.readthedocs.io) and "
    "its English model (`mfa model download acoustic {model}` and `mfa model "
    "download dictionary {model}`), or give a TextGrid with a phones tier"
)


@dataclass(frozen=True)
class MfaAligner:
    """An :class:`Aligner` that runs the Montreal Forced Aligner as a tool
    (an#637): the take (a WAV) and its text as a one-file corpus in a folder of
    its own name (MFA names its working directory after the corpus folder, so
    two imports never share one), ``mfa align`` with the English model of
    ``alphabet`` (:data:`MFA_MODELS`), and the TextGrid it writes read back
    (:func:`an.audio.transcripts.parse_textgrid`), words and phones. It runs
    where the recordings are (the user's machine): nothing is downloaded here.
    ``run`` is the subprocess seam (``subprocess.run``'s signature).

    >>> MfaAligner(alphabet="ipa").phone_alphabet
    'ipa'
    """

    alphabet: str = DFLT_MFA_ALPHABET
    executable: str = "mfa"
    command: str = DFLT_MFA_COMMAND
    run: Callable[..., Any] | None = None

    def __post_init__(self) -> None:
        if self.alphabet not in MFA_MODELS:
            raise RecordedVoicesError(
                f"no MFA model for the phone alphabet {self.alphabet!r}; "
                f"known: {sorted(MFA_MODELS)}"
            )

    @property
    def phone_alphabet(self) -> str:
        return self.alphabet

    def __call__(self, path: Path, text: str) -> list[TranscriptSegment]:
        """``text`` aligned as one utterance over the whole take (a ``.lab``)."""
        return self._align(path, f"{MFA_TAKE_STEM}.lab", text)

    def align_lines(
        self, path: Path, lines: Sequence[TranscriptSegment]
    ) -> list[TranscriptSegment]:
        """Each of the roughly timed ``lines`` aligned within its own interval
        (an#716): MFA is given a TextGrid with one interval per line instead
        of a ``.lab``, so a long take of many lines aligns as many short
        utterances, which is what MFA is built for. The intervals are clamped
        to the file's length (the take's length as cut may round past it)."""
        from an.audio.transcripts import textgrid_text

        xmax = wav_seconds(Path(path).read_bytes())
        intervals = [
            (max(0.0, seg.start), min(xmax, seg.end), seg.text) for seg in lines
        ]
        grid = textgrid_text({MFA_TAKE_STEM: intervals}, xmax=xmax)
        return self._align(path, f"{MFA_TAKE_STEM}.TextGrid", grid)

    def _align(self, path: Path, transcript: str, text: str) -> list[TranscriptSegment]:
        """Run MFA on the take and its ``transcript`` file (named so MFA reads
        it: ``.lab`` or ``.TextGrid``, holding ``text``) as a one-file corpus,
        and read back the TextGrid it writes."""
        import shutil
        import subprocess
        import tempfile

        from an.audio.transcripts import parse_textgrid

        model = MFA_MODELS[self.alphabet]
        if self.run is None and shutil.which(self.executable) is None:
            raise TranscriberUnavailableError(
                f"aligning {Path(path).name} needs `{self.executable}` on PATH: "
                + MFA_INSTALL_HINT.format(model=model)
            )
        with tempfile.TemporaryDirectory(prefix="an-mfa-") as tmp:
            corpus = Path(tmp) / Path(tmp).name  # unique: MFA's workspace name
            out = Path(tmp) / "aligned"
            corpus.mkdir()
            shutil.copyfile(path, corpus / f"{MFA_TAKE_STEM}.wav")
            (corpus / transcript).write_text(text, encoding="utf-8")
            argv = [self.executable, self.command, str(corpus), model, model,
                    str(out), "--clean", "--single_speaker"]  # fmt: skip
            proc = (self.run or subprocess.run)(argv, capture_output=True, check=False)
            grid = out / f"{MFA_TAKE_STEM}.TextGrid"
            if getattr(proc, "returncode", 1) != 0 or not grid.exists():
                said = b"".join(
                    x if isinstance(x, bytes) else str(x).encode()
                    for x in (
                        getattr(proc, "stdout", b""),
                        getattr(proc, "stderr", b""),
                    )
                    if x
                ).decode(errors="replace")
                raise AlignmentError(
                    f"`{self.executable} {self.command}` could not align "
                    f"{Path(path).name} with its transcript: "
                    f"{said.strip()[-400:] or 'no TextGrid written'}. Check the "
                    "transcript is what is said; a long take aligns better cut "
                    "into one file per line"
                )
            return parse_textgrid(grid.read_text(encoding="utf-8"))


#: The name the seam's MFA aligner was first given (an#637).
mfa_aligner = MfaAligner

#: The aligners ``an voices import --aligner NAME[:ALPHABET]`` builds.
ALIGNERS: Mapping[str, Callable[..., Aligner]] = {"mfa": MfaAligner}


def aligner_named(spec: str) -> Aligner:
    """The aligner ``spec`` names: ``NAME`` or ``NAME:ALPHABET`` (``mfa:ipa``).

    >>> aligner_named("mfa:ipa").phone_alphabet
    'ipa'
    """
    name, _, alphabet = spec.partition(":")
    if name not in ALIGNERS:
        raise RecordedVoicesError(
            f"no aligner {name!r}; known: {sorted(ALIGNERS)} "
            f"(with an alphabet: {', '.join(f'{name}:{a}' for a in MFA_MODELS)})"
        )
    return ALIGNERS[name](**({"alphabet": alphabet} if alphabet else {}))


def scribed_transcriber(
    backend: str | None = None, *, diarize: bool = False
) -> Transcriber:
    """The default transcriber: scribed's facade with word timestamps (and
    speaker labels when ``diarize`` and the backend has them). The import is
    lazy: a take with a timed transcript never needs it.
    """

    def transcribe(path: Path) -> list[TranscriptSegment]:
        try:
            import scribed
        except ImportError as e:
            raise TranscriberUnavailableError(
                f"{Path(path).name} needs transcribing (no timed transcript was given), "
                'and scribed is not installed: `pip install "an[recorded]"` and a backend '
                '(`pip install "scribed[faster-whisper]"` for a local one, or an API key for '
                "elevenlabs / openai), or give --transcript"
            ) from e
        options: dict[str, Any] = {"word_timestamps": True}
        options["backend"] = backend or _default_local_backend(scribed)
        if diarize:
            options["diarize"] = True
        try:
            result = scribed.transcribe(str(path), **options)
        except Exception as e:  # noqa: BLE001 — the backend's own error, with the way out
            raise TranscriberUnavailableError(
                f"transcribing {Path(path).name} with scribed"
                + (f" ({backend})" if backend else "")
                + f" failed: {e}. Pick a backend with --transcriber (scribed.doctor() lists "
                "what runs here), or give --transcript"
            ) from e
        return from_transcript_object(result)

    return transcribe


def _default_local_backend(scribed_module: Any) -> str:
    """The first usable LOCAL scribed backend. A remote one uploads the
    performer's audio to a service and may bill, so it is never chosen
    silently: name it with ``transcriber`` (``--transcriber elevenlabs``)."""
    try:
        available = [str(b) for b in scribed_module.available_backends()]
        local = {str(getattr(b, "id", b)) for b in scribed_module.find(is_local=True)}
    except Exception as e:  # noqa: BLE001 — scribed's own error, with the way out
        raise TranscriberUnavailableError(
            f"scribed could not list its backends: {e}; name one with --transcriber"
        ) from e
    for name in available:
        if name in local:
            return name
    remote = ", ".join(n for n in available if n not in local)
    raise TranscriberUnavailableError(
        "no local transcriber is installed"
        + (
            f" (installed: {remote} — remote services that upload the audio and may bill)"
            if remote
            else ""
        )
        + ': install one (`pip install "scribed[faster-whisper]"`), name a remote one '
        "explicitly with --transcriber, or give --transcript"
    )


# --- the import -----------------------------------------------------------------


@dataclass
class ImportedTake:
    """One take the import stored, and where it went."""

    key: str
    speaker: str
    voice: str
    text: str
    duration: float
    source_file: str
    span: tuple[float, float]
    words: int
    #: ``"<shot id>/<line index>"`` of the scene line it is the audio of.
    line: str
    #: ``True`` when the line was ADDED to the scene by this import.
    added: bool = False
    #: The ``pause`` written on the line from the recording, if any.
    pause: float | None = None


@dataclass
class ImportReport:
    """What :func:`import_recordings` did; ``str()`` is the CLI's output."""

    takes: list[ImportedTake] = field(default_factory=list)
    voices: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = []
        for t in self.takes:
            words = f", {t.words} words" if t.words else ""
            pause = f", pause {t.pause:g}s" if t.pause is not None else ""
            what = "added" if t.added else "bound"
            lines.append(
                f"{t.line} {what}: {t.speaker}: {t.text!r} ← {t.source_file} "
                f"[{t.span[0]:.2f}–{t.span[1]:.2f}] ({t.duration:.2f} s{words}{pause}) → recordings/{t.key}"
            )
        lines += self.voices
        lines += [f"warning: {w}" for w in self.warnings]
        return "\n".join(lines) if lines else "nothing imported"


@dataclass
class _Take:
    """A cut of one recording, before it is bound to a line."""

    path: Path
    segment: TranscriptSegment
    span: tuple[float, float]
    wav: bytes
    words: tuple[WordTiming, ...] | None
    speaker: str | None
    transcript_kind: str
    #: the take's phone timings, clip-relative, when the transcript had them (an#491)
    phones: tuple[WordTiming, ...] | None = None
    #: the alphabet those phones are in, when the aligner said (an#637)
    phone_alphabet: str | None = None
    #: silence heard between the previous take of the same file and this one
    gap_before: float | None = None
    #: the linked transcript artifact it was cut by (``<store>/<key>``, an#493)
    transcript_ref: str | None = None
    line: Any = None
    where: str = ""
    added: bool = False
    pause: float | None = None


def _parse_speakers(speakers: str | Mapping[str, str] | None) -> dict[str, str]:
    """``"spk_0=carl,spk_1=ned"`` (or a mapping) → ``{label: character}``, labels case-folded."""
    if not speakers:
        return {}
    if isinstance(speakers, Mapping):
        pairs = speakers.items()
    else:
        pairs = []
        for part in str(speakers).split(","):
            if not part.strip():
                continue
            if "=" not in part:
                raise RecordedVoicesError(
                    f"--speakers takes label=character pairs, got {part.strip()!r}"
                )
            label, who = part.split("=", 1)
            pairs.append((label, who))
    return {str(k).strip().casefold(): str(v).strip() for k, v in pairs}


def _scene_speakers(scene: Any) -> dict[str, str]:
    """``{casefolded name: name}`` of every speaker and character entity in the scene."""
    names: dict[str, str] = {}
    for shot in scene.timeline:
        for entity in shot.entities:
            if getattr(entity, "kind", None) == "character":
                names.setdefault(entity.id.casefold(), entity.id)
        for line in shot.dialogue:
            names.setdefault(line.speaker.casefold(), line.speaker)
    return names


class _Given(NamedTuple):
    """The transcript given for one take: its segments, its kind (``'srt'``,
    ``'text'``, ...) and the artifact it was read from (``<store>/<key>``,
    an#493), if it was."""

    segments: list[TranscriptSegment]
    kind: str
    ref: str | None = None


def _linked(transcript: Any, mall: Mapping[str, Any]) -> Any:
    """``transcript`` with every artifact it names (``artifact:<store>/<key>``,
    or a ``lacing.Artifact``; an#493) read out of ``mall`` into a
    :class:`~an.stores.transcripts.LinkedTranscript`; anything else as given."""

    def one(item: Any) -> Any:
        if not is_artifact_ref(item):
            return item
        try:
            return linked_transcript(item, mall)
        except TranscriptLinkError as e:
            raise RecordedVoicesError(str(e)) from None

    if isinstance(transcript, str) and "," in transcript:
        parts = [part.strip() for part in transcript.split(",") if part.strip()]
        if any(is_artifact_ref(part) for part in parts):
            # the CLI's spelling of one transcript per take, an artifact or a
            # file each: `--transcript artifact:transcripts/a,b.srt`
            return [one(part) for part in parts]
    if (
        transcript is None
        or isinstance(transcript, (str, Path, LinkedTranscript))
        or is_artifact_ref(transcript)
    ):
        return one(transcript)
    return [one(item) for item in transcript]


def _parse_transcript_file(
    item: str | Path | LinkedTranscript,
) -> list[TranscriptSegment]:
    """:func:`parse_transcript`, with a refusal that names the file instead of a traceback."""
    if isinstance(item, LinkedTranscript):
        try:
            return parse_transcript_text(item.text, fmt=item.fmt)
        except ValueError as e:
            raise RecordedVoicesError(f"{item.ref}: {e}") from e
    try:
        return parse_transcript(item)
    except (ValueError, OSError) as e:
        p = Path(str(item)) if len(str(item)) < 4096 else None
        name = p.name if p is not None and p.is_file() else "the transcript text"
        raise RecordedVoicesError(f"{name}: {e}") from e


def _transcripts_for(
    paths: Sequence[Path],
    transcript: str
    | Path
    | LinkedTranscript
    | Sequence[str | Path | LinkedTranscript]
    | None,
) -> dict[Path, _Given]:
    """``{audio path: given}`` from what ``transcript`` names: nothing;
    a directory (paired by stem, every take must pair); one file, text or
    linked artifact per audio file (same count); one for one take; or one
    plain transcript whose lines are the takes."""
    if transcript is None or transcript == "":
        return {}
    items: list[str | Path | LinkedTranscript]
    if isinstance(transcript, LinkedTranscript):
        items = [transcript]
    elif isinstance(transcript, (str, Path)):
        p = Path(transcript) if len(str(transcript)) < 4096 else None
        if p is not None and p.is_dir():
            out = {}
            for audio in paths:
                match = next(
                    (
                        c
                        for c in sorted(p.iterdir())
                        if c.stem == audio.stem
                        and c.suffix.lower() in TRANSCRIPT_SUFFIXES
                    ),
                    None,
                )
                if match is not None:
                    out[audio] = _Given(
                        _parse_transcript_file(match),
                        match.suffix.lstrip(".").lower(),
                    )
            unpaired = [a.name for a in paths if a not in out]
            if unpaired:
                raise RecordedVoicesError(
                    f"no transcript in {p.name}/ pairs by stem with {', '.join(unpaired)} "
                    f"(looked for {', '.join(TRANSCRIPT_SUFFIXES)}); name the file(s) with "
                    "the take's stem, give --transcript <file>, or leave --transcript out to transcribe"
                )
            return out
        literal_files = (
            isinstance(transcript, str)
            and "," in transcript
            and all(
                Path(x.strip()).is_file() for x in transcript.split(",") if x.strip()
            )
        )
        items = (
            [part.strip() for part in str(transcript).split(",") if part.strip()]
            if literal_files
            else [transcript]
        )
    else:
        items = list(transcript)

    def kind_of(item: str | Path | LinkedTranscript) -> str:
        if isinstance(item, LinkedTranscript):  # a plain one reads as plain text does
            return "text" if item.fmt == "plain" else item.fmt
        p = Path(item) if len(str(item)) < 4096 else None
        if p is not None and p.is_file():
            return p.suffix.lstrip(".").lower() or "text"
        return "text"

    def ref_of(item: Any) -> str | None:
        return item.ref if isinstance(item, LinkedTranscript) else None

    if len(items) == len(paths):
        return {
            audio: _Given(_parse_transcript_file(item), kind_of(item), ref_of(item))
            for audio, item in zip(paths, items)
        }
    if len(items) != 1:
        raise RecordedVoicesError(
            f"{len(items)} transcript(s) for {len(paths)} audio file(s): give one per file "
            "(a directory pairs them by stem), or one transcript for one take"
        )
    segments = _parse_transcript_file(items[0])
    kind, ref = kind_of(items[0]), ref_of(items[0])
    if len(paths) == 1:
        return {paths[0]: _Given(segments, kind, ref)}
    if all(not s.timed for s in segments) and len(segments) == len(paths):
        return {audio: _Given([seg], kind, ref) for audio, seg in zip(paths, segments)}
    raise RecordedVoicesError(
        f"one transcript ({len(segments)} line(s)) for {len(paths)} audio files: a plain "
        "transcript with one line per file pairs them in order; a timed transcript goes "
        "with ONE take (or one transcript per file, paired by stem from a directory)"
    )


def _timed_segments(
    path: Path,
    total: float,
    given: _Given | None,
    *,
    transcribe: Transcriber | None,
    make_transcriber: Callable[[], Transcriber],
    align: Aligner | None = None,
    wav: bytes | None = None,
    rough_timing: bool = True,
) -> tuple[list[TranscriptSegment], str]:
    """The lines of the take at ``path``, each with its span in the file, and
    how the words were obtained: the transcript's kind (``'srt'``, ``'txt'``,
    ...), ``'asr'``, ``'<kind>+asr'`` for a plain transcript timed by the
    transcriber, ``'file'`` for one line, or ``'<kind>+align'`` for a plain
    transcript timed by the forced aligner, words and phones (an#637; ``wav``
    is the take as decoded, which the aligner is given; ``rough_timing``: the
    transcriber times its lines roughly first, :func:`_aligned_lines`). An
    aligner with no plain transcript is refused: it has no text to align."""
    lines = [s for s in given[0] if s.text] if given is not None else []
    if align is not None and (given is None or (lines and all(s.timed for s in lines))):
        raise RecordedVoicesError(
            f"{path.name}: an aligner times a PLAIN transcript (`speaker: text` "
            "lines), and this take has "
            + ("none" if given is None else "a timed one, whose times are kept")
            + "; give its plain transcript with --transcript, or drop --aligner"
        )
    if given is None:
        segments = list((transcribe or make_transcriber())(path))
        timed = sorted(
            (s for s in segments if s.timed and s.text), key=lambda s: (s.start, s.end)
        )
        if not timed:
            raise RecordedVoicesError(
                f"the transcriber found no speech with timings in {path.name}"
            )
        return timed, "asr"
    segments, kind, _ref = given
    segments = [s for s in segments if s.text]
    if not segments:
        raise RecordedVoicesError(f"the transcript for {path.name} has no lines")
    if all(s.timed for s in segments):
        inside = sorted(
            (s for s in segments if s.start < total + 1e-6),
            key=lambda s: (s.start, s.end),
        )
        if len(inside) < len(segments):
            raise RecordedVoicesError(
                f"{len(segments) - len(inside)} line(s) of the transcript for {path.name} "
                f"start after the audio ends ({total:.2f} s)"
            )
        return inside, kind
    if any(s.timed for s in segments):
        raise RecordedVoicesError(
            f"the transcript for {path.name} times some lines and not others; time all or none"
        )
    if align is not None:

        def rough() -> list[WordTiming]:
            """The transcriber's words: rough line times for a long take (an#716)."""
            heard = (transcribe or make_transcriber())(path)
            return [w for s in heard for w in (s.words or ())]

        return (
            _aligned_lines(
                path, segments, total=total, align=align, wav=wav,
                rough=rough if rough_timing else None,
            ),
            f"{kind}+align",
        )  # fmt: skip
    if len(segments) == 1:
        seg = segments[0]
        return [
            TranscriptSegment(
                text=seg.text,
                start=0.0,
                end=total,
                speaker=seg.speaker,
                words=seg.words,
            )
        ], "file"
    heard = list((transcribe or make_transcriber())(path))
    words = [w for s in heard for w in (s.words or ())]
    if not words:
        raise RecordedVoicesError(
            f"the transcriber returned no word timings for {path.name}; the plain transcript "
            "cannot be timed by it — pick a backend with word timestamps, or give an SRT/VTT"
        )
    return segment_lines(segments, words, bounds=(0.0, total)), f"{kind}+asr"


def _aligned_lines(
    path: Path,
    lines: Sequence[TranscriptSegment],
    *,
    total: float,
    align: Aligner,
    wav: bytes | None,
    rough: Callable[[], Sequence[WordTiming]] | None = None,
    line_pad_s: float = DFLT_ALIGN_LINE_PAD_S,
    min_coverage: float = DFLT_ROUGH_MIN_COVERAGE,
    min_line_s: float = DFLT_ROUGH_MIN_LINE_S,
) -> list[TranscriptSegment]:
    """A plain transcript's ``lines`` timed by a forced aligner (an#637): its
    words time the lines as a transcriber's would (:func:`segment_lines`), and
    each line keeps the phones that fall in its span. One line spans the file.
    The aligner is given ``wav`` (the take as decoded, denoised included: the
    samples that are cut) as a WAV file, any format the import read.

    Several lines and an aligner that can align lines (:class:`LineAligner`,
    MFA): the lines are first timed roughly by ``rough`` (the transcriber's
    words, :func:`_rough_line_intervals`), and each is aligned within its own
    interval, ``line_pad_s`` wider on each side (an#716), since a forced aligner
    is built for short utterances; each aligned word and phone belongs to the
    line whose interval it falls in. Without ``rough`` (``rough_timing=False``),
    the whole text is aligned as one utterance, as before an#716; so it is, with
    a :class:`RecordedVoicesWarning`, when no transcriber can run or its words
    do not fit the lines (``min_coverage``, ``min_line_s``). A line the aligner
    placed no word in keeps its rough times, without phones, and is warned of."""
    import tempfile

    intervals = (
        _rough_intervals_or_none(
            path, lines, rough, total=total, pad_s=line_pad_s,
            min_coverage=min_coverage, min_line_s=min_line_s,
        )
        if len(lines) > 1 and rough is not None and isinstance(align, LineAligner)
        else None
    )  # fmt: skip

    def aligned_from(file: Path) -> list[TranscriptSegment]:
        if intervals is not None:
            return list(align.align_lines(file, intervals))
        return list(align(file, " ".join(line.text for line in lines)))

    if wav is None:
        aligned = aligned_from(path)
    else:
        with tempfile.TemporaryDirectory(prefix="an-align-") as tmp:
            decoded = Path(tmp) / f"{path.stem}.wav"
            decoded.write_bytes(wav)
            aligned = aligned_from(decoded)
    words = [w for s in aligned for w in (s.words or ())]
    phones = [p for s in aligned for p in (s.phones or ())]
    if not words:
        raise RecordedVoicesError(
            f"the aligner returned no word timings for {path.name}; check the transcript "
            "is what is said, or give a TextGrid"
        )
    # The aligner's declared alphabet, else what its output showed (an#721).
    alphabet = getattr(align, "phone_alphabet", None) or next(
        (s.phone_alphabet for s in aligned if s.phone_alphabet), None
    )
    if intervals is not None:
        return _lines_by_interval(
            intervals, words, phones, alphabet=alphabet, name=path.name
        )
    timed = (
        [
            TranscriptSegment(
                text=lines[0].text,
                start=0.0,
                end=total,
                speaker=lines[0].speaker,
                words=tuple(words),
            )
        ]  # fmt: skip
        if len(lines) == 1
        else segment_lines(lines, words, bounds=(0.0, total))
    )
    eps = 1e-6

    def with_phones(seg: TranscriptSegment) -> TranscriptSegment:
        inside = tuple(
            p for p in phones if seg.start - eps <= p[1] and p[2] <= seg.end + eps
        )
        return replace(
            seg, phones=inside or None, phone_alphabet=alphabet if inside else None
        )

    return [with_phones(seg) for seg in timed]


class _RoughTimingUnfit(ValueError):
    """The transcriber's words cannot time the lines, roughly (an#716); the message says why."""


def _rough_intervals_or_none(
    path: Path,
    lines: Sequence[TranscriptSegment],
    rough: Callable[[], Sequence[WordTiming]],
    **fit: Any,
) -> list[TranscriptSegment] | None:
    """:func:`_rough_line_intervals` of ``rough()``'s words, or ``None`` with a
    :class:`RecordedVoicesWarning` naming what went wrong (no transcriber, or
    words that do not fit), so the lines are aligned as one utterance."""
    try:
        return _rough_line_intervals(lines, rough(), **fit)
    except (TranscriberUnavailableError, _RoughTimingUnfit) as e:
        warnings.warn(
            f"{path.name}: its {len(lines)} lines could not be timed roughly ({e}), "
            "so the forced aligner aligns them as one utterance, which drifts on a "
            "long take; give a transcriber (--transcriber), or cut the take into "
            "one file per line",
            RecordedVoicesWarning,
            stacklevel=2,
        )
        return None


def _rough_line_intervals(
    lines: Sequence[TranscriptSegment],
    words: Sequence[WordTiming],
    *,
    total: float,
    pad_s: float,
    min_coverage: float = DFLT_ROUGH_MIN_COVERAGE,
    min_line_s: float = DFLT_ROUGH_MIN_LINE_S,
) -> list[TranscriptSegment]:
    """``lines`` timed roughly by a transcriber's ``words``
    (:func:`~an.audio.transcripts.align_words`), each widened by ``pad_s`` as a
    cut is (:func:`~an.audio.transcripts.cut_spans`: never past the midpoint to
    its neighbour, nor out of ``0..total``): the intervals a line aligner aligns
    each line within (an#716). Each keeps its rough ``words``. Raises
    :class:`_RoughTimingUnfit` when the words cannot be trusted to place every
    line: fewer than ``min_coverage`` of the lines' words heard, a line with
    no words, or a line whose PADDED interval is shorter than ``min_line_s``,
    which is what a line the transcriber did not hear between two it did
    becomes (a heard one-word line keeps its pad, so it passes).

    >>> lines = parse_transcript_text("carl: Hello there.\\nned: Hi.", fmt="plain")
    >>> words = [("hello", 0.5, 0.9), ("there", 0.9, 1.3), ("hi", 2.0, 2.3)]
    >>> [(s.text, s.start, s.end) for s in _rough_line_intervals(lines, words, total=3.0, pad_s=0.25)]
    [('Hello there.', 0.25, 1.55), ('Hi.', 1.75, 2.55)]
    """
    per_line = [tokens_of(line.text) for line in lines]
    heard = align_words(
        [t for toks in per_line for t in toks], words, bounds=(0.0, total)
    )
    if heard.coverage < min_coverage:
        raise _RoughTimingUnfit(
            f"the transcriber heard {heard.matched} of the transcript's "
            f"{heard.total} words, under {min_coverage:.0%}"
        )
    timed, cursor = [], 0
    for line, toks in zip(lines, per_line):
        said = tuple(heard.words[cursor : cursor + len(toks)])
        cursor += len(toks)
        if not said:
            raise _RoughTimingUnfit(f"the line {line.text!r} has no words")
        timed.append(replace(line, start=said[0][1], end=said[-1][2], words=said))
    spans = cut_spans(timed, total=total, pad_s=pad_s)
    # Judged padded: a heard one-word line ("No.", 0.08 s) keeps its pad either
    # side; an unheard one squeezed between two heard lines has next to none.
    for seg, (a, b) in zip(timed, spans):
        if b - a < min_line_s:
            raise _RoughTimingUnfit(
                f"the line {seg.text!r} was not heard (its interval is under {min_line_s:g} s)"
            )
    return [replace(seg, start=a, end=b) for seg, (a, b) in zip(timed, spans)]


def _lines_by_interval(
    intervals: Sequence[TranscriptSegment],
    words: Sequence[WordTiming],
    phones: Sequence[WordTiming],
    *,
    alphabet: str | None,
    name: str,
) -> list[TranscriptSegment]:
    """Each line of ``intervals`` (disjoint, in order, as
    :func:`_rough_line_intervals` gives them) timed by the aligned ``words``
    and ``phones`` whose midpoint falls in its interval (an#716). A line given
    no word keeps its rough words and times, without phones, with a
    :class:`RecordedVoicesWarning` (``name`` is the take's)."""
    starts = [seg.start for seg in intervals]

    def by_line(timings: Sequence[WordTiming]) -> list[list[WordTiming]]:
        out: list[list[WordTiming]] = [[] for _ in intervals]
        for t in timings:
            i = bisect_right(starts, (t[1] + t[2]) / 2) - 1
            if i >= 0 and (t[1] + t[2]) / 2 <= intervals[i].end:
                out[i].append(t)
        return out

    def timed(seg: TranscriptSegment, said: list, sounds: list) -> TranscriptSegment:
        if said:
            return replace(
                seg, start=said[0][1], end=said[-1][2], words=tuple(said),
                phones=tuple(sounds) or None,
                phone_alphabet=alphabet if sounds else None,
            )  # fmt: skip
        warnings.warn(
            f"{name}: the aligner placed no word of the line {seg.text!r} in "
            f"{seg.start:.2f}–{seg.end:.2f} s; it keeps the transcriber's rough "
            "times and has no phones. Check it is what is said",
            RecordedVoicesWarning,
            stacklevel=2,
        )
        rough = seg.words or ()
        return replace(
            seg,
            start=rough[0][1] if rough else seg.start,
            end=rough[-1][2] if rough else seg.end,
            phones=None,
            phone_alphabet=None,
        )

    return [
        timed(seg, said, sounds)
        for seg, said, sounds in zip(intervals, by_line(words), by_line(phones))
    ]


def _speaker_of(
    take: _Take,
    *,
    speaker: str | None,
    speakers: Mapping[str, str],
    known: Mapping[str, str],
) -> str | None:
    """Who speaks ``take``: the one performer given, a mapped or known transcript
    label, a mapped or known file stem; ``None`` leaves it to the line it matches."""
    if speaker:
        return speaker
    label = (take.segment.speaker or "").strip()
    if label:
        if label.casefold() in speakers:
            return speakers[label.casefold()]
        if label.casefold() in known:
            return known[label.casefold()]
    stem = take.path.stem
    for candidate in (stem, _STEM_SPLIT_RE.split(stem, 1)[0]):
        if candidate.casefold() in speakers:
            return speakers[candidate.casefold()]
        if candidate.casefold() in known:
            return known[candidate.casefold()]
    return None


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(
        None, normalize_text(a), normalize_text(b), autojunk=False
    ).ratio()


def _bind_to_lines(scene: Any, takes: list[_Take], *, threshold: float) -> None:
    """Give each take the scene line whose words it says (once per line), by
    the best ratio at or above ``threshold``; its speaker when the take had none.

    A take with no speaker that fits lines of two speakers equally well is
    refused: order in the file is no evidence of who spoke."""
    used: set[tuple[str, int]] = set()
    for take in takes:
        best: tuple[float, Any, int, Any] | None = None
        tied: set[str] = set()
        for shot in scene.timeline:
            for idx, line in enumerate(shot.dialogue):
                if (shot.id, idx) in used:
                    continue
                if take.speaker and line.speaker.casefold() != take.speaker.casefold():
                    continue
                score = _ratio(take.segment.text, line.text)
                if score < threshold:
                    continue
                if best is None or score > best[0] + 1e-9:
                    best = (score, shot, idx, line)
                    tied = {line.speaker}
                elif abs(score - best[0]) <= 1e-9:
                    tied.add(line.speaker)
        if best is None:
            continue
        if take.speaker is None and len(tied) > 1:
            raise RecordedVoicesError(
                f"the take {take.segment.text!r} ({take.path.name}) fits lines of "
                f"{sorted(tied)} equally well; say who speaks it: --speaker <character>, "
                "--speakers <label=character,...>, or `speaker:` prefixes in the transcript"
            )
        _, shot, idx, line = best
        used.add((shot.id, idx))
        take.line = line
        take.where = f"{shot.id}/{idx}"
        take.speaker = take.speaker or line.speaker


def _shot_for_new_lines(scene: Any, shot_id: str | None, unmatched: list[_Take]) -> Any:
    if shot_id:
        found = next((s for s in scene.timeline if s.id == shot_id), None)
        if found is None:
            raise RecordedVoicesError(
                f"no shot {shot_id!r} in the scene (shots: {[s.id for s in scene.timeline]})"
            )
        return found
    if not scene.timeline:
        raise RecordedVoicesError(
            "the scene has no shot to put the lines in; add one to scene.md first"
        )
    if not any(s.dialogue for s in scene.timeline):
        return scene.timeline[0]
    listing = "; ".join(
        f"{t.speaker or '?'}: {t.segment.text!r} ({t.path.name})" for t in unmatched
    )
    raise RecordedVoicesError(
        f"{len(unmatched)} take(s) match no line of the scene: {listing}. Add them as new "
        "lines with --shot <id>, or fix the transcript so the words match the scene's"
    )


def _add_new_lines(scene: Any, takes: list[_Take], *, shot_id: str | None) -> None:
    from an.ir.schema import Dialogue

    unmatched = [t for t in takes if t.line is None]
    if not unmatched:
        return
    nameless = [t for t in unmatched if not t.speaker]
    if nameless:
        listing = "; ".join(f"{t.segment.text!r} ({t.path.name})" for t in nameless)
        raise RecordedVoicesError(
            f"{len(nameless)} take(s) have no speaker and match no scene line: {listing}. "
            "Give --speaker <character>, --speakers <label=character,...>, or `speaker:` "
            "prefixes in the transcript"
        )
    shot = _shot_for_new_lines(scene, shot_id, unmatched)
    for take in unmatched:
        line = Dialogue(speaker=take.speaker, text=take.segment.text)
        shot.dialogue.append(line)
        take.line = line
        take.where = f"{shot.id}/{len(shot.dialogue) - 1}"
        take.added = True


def _write_pauses(scene: Any, takes: list[_Take]) -> None:
    """The silence heard between two consecutive takes of one file becomes the
    later line's ``pause``, when that line is right after the earlier one in its
    shot and its author wrote no timing — so the shot follows the recording."""
    where: dict[int, tuple[Any, int]] = {}
    for shot in scene.timeline:
        for idx, line in enumerate(shot.dialogue):
            where[id(line)] = (shot, idx)
    previous: _Take | None = None
    for take in takes:
        if (
            previous is not None
            and previous.path == take.path
            and take.gap_before is not None
        ):
            here, there = where.get(id(take.line)), where.get(id(previous.line))
            line = take.line
            if (
                here is not None
                and there is not None
                and here[0] is there[0]
                and here[1] == there[1] + 1
                and line.pause is None
                and line.at is None
            ):
                line.pause = round(max(0.0, take.gap_before), 3)
                take.pause = line.pause
        previous = take


def _voice_for(
    mall: Mapping[str, MutableMapping],
    scene: Any,
    speaker: str,
    *,
    voice: str | None,
    recorded_by: str | None,
    lines: list[Any],
    report: ImportReport,
) -> str:
    """The voice document ``speaker``'s takes belong to, created when missing and
    bound to the speaker's character (its descriptor's ``voice_ref``) — or, for a
    speaker with no character entity, to each imported line."""
    key = voice or f"{speaker}{RECORDED_VOICE_SUFFIX}"
    voices = mall["voices"]
    doc = dict(voices[key]) if key in voices else None
    if doc is not None and str(doc.get("provider", "")).strip().lower() not in (
        "",
        PROVIDER_NAME,
    ):
        raise RecordedVoicesError(
            f"voice {key!r} is written for provider {doc['provider']!r}; the takes of "
            f"{speaker!r} need a recorded voice: name another with --voice, or change that document"
        )
    created = doc is None
    doc = doc or {}
    doc["provider"] = PROVIDER_NAME
    doc.setdefault("speaker", speaker)
    if recorded_by:
        doc["recorded_by"] = recorded_by
    entity_refs = sorted(
        {
            e.ref
            for shot in scene.timeline
            for e in shot.entities
            if getattr(e, "kind", None) == "character"
            and e.id.casefold() == speaker.casefold()
        }
    )
    characters = mall.get("characters")
    # An entity whose descriptor is not in the store cannot carry the binding:
    # it is treated like no character at all (the line keeps it), and said.
    refs = [r for r in entity_refs if characters is not None and r in characters]
    undescribed = [r for r in entity_refs if r not in refs]
    bound = []
    for ref in refs:
        descriptor = dict(characters[ref])
        previous = descriptor.get("voice_ref")
        if previous == key:
            continue
        if previous:
            doc.setdefault("replaces", previous)
        descriptor["voice_ref"] = key
        characters[ref] = descriptor
        bound.append(ref)
    voices[key] = doc
    if bound:
        report.voices.append(
            f"voices/{key} ({'created' if created else 'kept'}, provider recorded) now voices "
            f"character(s) {', '.join(bound)}"
            + (
                f"; it replaces {doc['replaces']!r} — set voice_ref back to hear that voice"
                if doc.get("replaces")
                else ""
            )
        )
    elif not refs:
        for line in lines:
            line.voice_ref = key
        why = (
            f"whose character entity ({', '.join(undescribed)}) has no descriptor in the "
            "characters store"
            if undescribed
            else "who is no character entity of any shot"
        )
        report.voices.append(
            f"voices/{key} ({'created' if created else 'kept'}, provider recorded) is set on "
            f"{len(lines)} line(s) of {speaker!r}, {why}: the line's voice is "
            "written in scene.md as `(voice <key>)`, so it survives an edit; to bind "
            "it to the character instead, "
            + (
                "create the descriptor"
                if undescribed
                else "add the character to its shots"
            )
        )
    else:
        report.voices.append(
            f"voices/{key} ({'created' if created else 'kept'}) already voices {', '.join(refs)}"
        )
    return key


def _check_voice_document(
    mall: Mapping[str, MutableMapping], key: str, speaker: str
) -> None:
    """Refuse a voice document written for another provider (before any write)."""
    voices = mall["voices"]
    doc = voices[key] if key in voices else None
    if isinstance(doc, Mapping) and str(
        doc.get("provider", "")
    ).strip().lower() not in (
        "",
        PROVIDER_NAME,
    ):
        raise RecordedVoicesError(
            f"voice {key!r} is written for provider {doc['provider']!r}; the takes of "
            f"{speaker!r} need a recorded voice: name another with --voice, or change that document"
        )


def _warn_repeated_text(scene: Any, takes: list[_Take], report: ImportReport) -> None:
    """The pipeline keys a line's audio by voice and text: two lines of one
    speaker saying the same words play the same (newest) take. Say so."""
    seen: dict[tuple[str, str], int] = {}
    for take in takes:
        k = (take.speaker.casefold(), normalize_key_text(take.line.text))
        seen[k] = seen.get(k, 0) + 1
    repeated = {k for k, n in seen.items() if n > 1}
    speakers = {t.speaker.casefold() for t in takes}
    scene_counts: dict[tuple[str, str], int] = {}
    for shot in scene.timeline:
        for line in shot.dialogue:
            if line.speaker.casefold() in speakers:
                k = (line.speaker.casefold(), normalize_key_text(line.text))
                scene_counts[k] = scene_counts.get(k, 0) + 1
    repeated |= {k for k, n in scene_counts.items() if n > 1 and k in seen}
    for spk, text in sorted(repeated):
        report.warnings.append(
            f"{spk!r} says {text!r} more than once: a line's audio is keyed by its voice and "
            "text, so every such line plays the same (newest) take — the recording's other "
            "take of it is stored but not heard (reeleehq/an#492 is the way to tell them apart)"
        )


def _unrecorded_lines(
    scene: Any, mall: Mapping, speaker: str, voice: str, recorded: set[int]
) -> int:
    """How many other lines of ``speaker`` have no take, so will refuse to render."""
    store = mall.get(RECORDINGS_STORE)
    n = 0
    for shot in scene.timeline:
        for line in shot.dialogue:
            if line.speaker.casefold() != speaker.casefold() or id(line) in recorded:
                continue
            if find_recording(store, voice, line.text) is None:
                n += 1
    return n


def recorded_transcript_pins(recordings: Mapping) -> set[str]:
    """The transcript contents the takes in ``recordings`` were cut by: the pin
    of each one's ``source.extra.transcript_artifact`` (an#607). Raises
    ``ValueError`` when a record cannot be read (a collection then keeps
    everything: an unknown take might name any of them)."""
    from an.stores.transcripts import pin_of

    pins = set()
    for key in list(recordings):
        record = recordings[key]
        if not isinstance(record, Mapping):
            raise ValueError(f"recording {key!r} is not a record")
        source = record.get("source") or {}
        extra = source.get("extra") if isinstance(source, Mapping) else None
        if not isinstance(extra or {}, Mapping):
            raise ValueError(f"recording {key!r} has a malformed source")
        pin = pin_of((extra or {}).get("transcript_artifact"))
        if pin:
            pins.add(pin)
    return pins


def import_recordings(
    project: str | Path,
    audio: str | Path | Sequence[str | Path],
    *,
    transcript: str | Path | Sequence[str | Path] | None = None,
    speaker: str | None = None,
    speakers: str | Mapping[str, str] | None = None,
    shot: str | None = None,
    voice: str | None = None,
    denoise: str | None = None,
    license: str | None = None,
    recorded_by: str | None = None,
    transcribe: Transcriber | None = None,
    transcriber: str | None = None,
    diarize: bool = False,
    align: Aligner | None = None,
    rough_timing: bool = True,
    match_threshold: float = DFLT_MATCH_THRESHOLD,
    write: bool = True,
    scene_file: Any = DEFAULT_SCENE_FILE,
) -> ImportReport:
    """Import a performer's recording(s) as the voice of their lines (an#490).

    ``audio`` names the takes (a file, several, a directory, a glob): a whole
    take holding several lines, or one file per line. ``transcript`` is
    optional: SRT, WebVTT, TextGrid or word JSON time the lines so nothing is
    transcribed; a plain transcript (``speaker: text`` lines) pairs one line per
    file, or is timed against ``transcribe``'s words for a whole take; with no
    transcript at all the take is transcribed and its segments are the lines.

    Each line is cut out, matched to the scene's dialogue by its words
    (``match_threshold``), stored in ``mall["recordings"]`` with its provenance
    (``license`` is required: the code you vouch for; ``recorded_by`` names the
    performer), and the speaker's character is bound to a recorded voice
    document (``voice``, default ``<speaker>_recorded``). Takes matching no line
    are added to ``shot`` (or the first shot of a scene with no dialogue). The
    gap heard between two lines of one file becomes the later line's ``pause``.

    ``denoise`` (``"afftdn"`` / ``"anlmdn"``) cleans each file first, through
    ffmpeg. ``transcribe`` is the transcriber seam (``path -> segments``); its
    default is :func:`scribed_transcriber` with ``transcriber`` as the backend
    and ``diarize`` for speaker labels, built only when a take needs it.
    ``align`` is the forced-aligner seam (``(path, text) -> segments``, e.g.
    :func:`mfa_aligner`, an#637): with a plain transcript it times the lines
    instead of a transcriber, and gives their phones, as a TextGrid would.
    Several lines in one take are first timed roughly by the transcriber
    (``transcribe``, else ``transcriber``: a billed backend named there is
    billed for this pass too), and each is aligned within its own interval
    (an#716); ``rough_timing=False`` never transcribes and aligns the whole
    text as one utterance, which drifts on a long take. With no transcriber
    to run, the import falls back to that one utterance, with a
    :class:`RecordedVoicesWarning`.
    ``write=False`` runs everything but writes nothing (a dry run).
    ``scene_file`` imports into another scene of the project
    (``scene.studio.md``, an#554).
    """
    from an.project import load

    if not license:
        raise RecordedVoicesError(
            "a licence (or permission) code is required: the code you vouch for, e.g. "
            "`cc0-1.0`, `cc-by-4.0`, `all-rights-reserved`, or `unknown` to record that "
            "nobody has said (the take is then UNVERIFIED in `an credits`)"
        )
    paths = audio_paths(audio)
    if not paths:
        raise RecordedVoicesError(f"no audio files found in {audio!r}")
    proj = load(project, scene_file=scene_file)
    scene, mall = proj.scene, proj.mall
    if RECORDINGS_STORE not in mall:
        raise RecordedVoicesError("this project's mall has no recordings store")
    given = _transcripts_for(paths, _linked(transcript, mall))
    speaker_map = _parse_speakers(speakers)
    known = _scene_speakers(scene)
    make_transcriber = lambda: scribed_transcriber(transcriber, diarize=diarize)  # noqa: E731

    takes: list[_Take] = []
    for path in paths:
        wav = load_wav(path, denoise=denoise)
        total = wav_seconds(wav)
        segments, kind = _timed_segments(
            path,
            total,
            given.get(path),
            transcribe=transcribe,
            make_transcriber=make_transcriber,
            align=align,
            wav=wav,
            rough_timing=rough_timing,
        )
        spans = cut_spans(segments, total=total)
        previous_end: float | None = None
        for segment, (a, b) in zip(segments, spans):
            clip = cut_wav(wav, a, b) if (a, b) != (0.0, total) else wav
            if b - a <= 0 or wav_seconds(clip) <= 0:
                raise RecordedVoicesError(
                    f"{path.name}: the cue {segment.text!r} ({segment.start:.2f}–{segment.end:.2f} s) "
                    "leaves no audio to cut — its times overlap or nest with a neighbour's; "
                    "fix the transcript's times. Nothing was written."
                )
            take = _Take(
                path=path,
                segment=segment,
                span=(a, b),
                wav=clip,
                words=rebase_words(segment.words, a),
                phones=rebase_words(segment.phones, a),
                phone_alphabet=segment.phone_alphabet if segment.phones else None,
                speaker=None,
                transcript_kind=kind,
                transcript_ref=given[path].ref if path in given else None,
                # The silence HEARD: from the previous speech's end to this cut's
                # start (the cut keeps its pad, so the pause must not count it twice).
                gap_before=(a - previous_end) if previous_end is not None else None,
            )
            take.speaker = _speaker_of(
                take, speaker=speaker, speakers=speaker_map, known=known
            )
            takes.append(take)
            previous_end = segment.end

    _bind_to_lines(scene, takes, threshold=match_threshold)
    _add_new_lines(scene, takes, shot_id=shot)
    _write_pauses(scene, takes)

    report = ImportReport()
    if voice and len({t.speaker.casefold() for t in takes}) > 1:
        raise RecordedVoicesError(
            "--voice names one voice document, but the takes have several speakers: "
            f"{sorted({t.speaker for t in takes})}; import one speaker at a time with --voice"
        )
    store = mall[RECORDINGS_STORE]
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="microseconds")
    speakers_found = sorted({t.speaker for t in takes}, key=str.casefold)
    voice_of: dict[str, str] = {
        spk: voice or f"{spk}{RECORDED_VOICE_SUFFIX}" for spk in speakers_found
    }
    for spk, key in voice_of.items():
        _check_voice_document(mall, key, spk)  # refuse BEFORE anything is written
    _warn_repeated_text(scene, takes, report)
    recorded_ids: set[int] = set()
    for take in takes:
        source = AssetSource(
            provider=SOURCE_PROVIDER,
            id=take.path.name,
            license=license,
            author=recorded_by,
            attribution=(
                f"Voice of {take.speaker}: {recorded_by}" if recorded_by else None
            ),
            cacheable=True,
            sha256=hashlib.sha256(take.path.read_bytes()).hexdigest(),
            extra={
                "span": [take.span[0], take.span[1]],
                "denoise": denoise,
                "transcript": take.transcript_kind,
                "line": take.where,
                **(
                    {"transcript_artifact": take.transcript_ref}
                    if take.transcript_ref
                    else {}
                ),
            },
        )
        if write:
            key, record = add_recording(
                store,
                voice=voice_of[take.speaker],
                speaker=take.speaker,
                text=take.line.text,
                audio=take.wav,
                source=source,
                words=take.words,
                phones=take.phones,
                phone_alphabet=take.phone_alphabet,
                imported_at=stamp,
            )
            duration = float(record["duration"])
        else:
            key = recording_key(
                take.speaker, take.line.text, hashlib.sha256(take.wav).hexdigest()
            )
            duration = wav_seconds(take.wav)
        recorded_ids.add(id(take.line))
        report.takes.append(
            ImportedTake(
                key=key,
                speaker=take.speaker,
                voice=voice_of[take.speaker],
                text=take.line.text,
                duration=duration,
                source_file=take.path.name,
                span=take.span,
                words=len(take.words or ()),
                line=take.where,
                added=take.added,
                pause=take.pause,
            )
        )
    # The takes are in the store: now the voice documents and the bindings
    # (a failure above leaves the project exactly as it was).
    if write:
        for spk in speakers_found:
            lines = [t.line for t in takes if t.speaker == spk]
            _voice_for(
                mall,
                scene,
                spk,
                voice=voice,
                recorded_by=recorded_by,
                lines=lines,
                report=report,
            )
    for spk, key in voice_of.items():
        n = _unrecorded_lines(scene, mall, spk, key, recorded_ids) if write else 0
        if n:
            report.warnings.append(
                f"{n} other line(s) of {spk!r} have no take: a render refuses them until they "
                "are imported (or given another voice)"
            )
    for shot_ in scene.timeline:
        total = sum(
            t.duration + (t.pause or 0.0)
            for t in report.takes
            if t.line.startswith(f"{shot_.id}/")
        )
        if total > float(shot_.duration) + 1e-6:
            report.warnings.append(
                f"shot {shot_.id!r} lasts {float(shot_.duration):.2f} s but its recorded lines "
                f"take {total:.2f} s; lengthen it in scene.md (`an validate` reports the overrun)"
            )
    if write:
        mall["scenes"]["main"] = scene
    return report
