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
import io
import re
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from an.audio.transcripts import (
    TranscriptSegment,
    WordTiming,
    cut_spans,
    from_transcript_object,
    normalize_text,
    parse_transcript,
    rebase_words,
    segment_lines,
)
from an.audio.tts import AudioClip, VoiceMeta
from an.ir.assets import AssetSource

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
#: What a decoded take is resampled to (the film mix's rate), mono 16-bit.
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


class RecordingMissingError(RecordedVoicesError):
    """A line spoken by a recorded voice has no take in the store."""


class TranscriberUnavailableError(RecordedVoicesError):
    """A take needs transcribing and no transcriber can run here."""


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


def recording_by_digest(store: Mapping | None, sha256: str) -> tuple[str, dict] | None:
    """The take whose audio has ``sha256``, as ``(key, record)``; ``None`` if none."""
    if store is None:
        return None
    for key in store:
        record = store[key]
        if isinstance(record, Mapping) and record.get("sha256") == sha256:
            return key, dict(record)
    return None


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
        "words": [[w[0], float(w[1]), float(w[2])] for w in words] if words else None,
        "source": source.model_dump(exclude_none=True),
        "imported_at": imported_at
        or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="microseconds"),
    }
    store[key] = record
    store.write_audio(key, audio)
    return key, record


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
            VoiceMeta(voice_id=v, name=v, provider=self.name, extra={"takes": n})
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
        follows the take, so a re-recorded line is new audio.

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
        return {RECORDING_OPTION: found[1]["sha256"]}

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
            recording_by_digest(self.recordings, recording)
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
        words = record.get("words") or None
        return AudioClip(
            bytes_=audio,
            duration=float(record["duration"]),
            sample_rate=int(record.get("sample_rate") or IMPORT_SAMPLE_RATE),
            channels=int(record.get("channels") or 1),
            voice_id=voice_id,
            transcript=text,
            words=(
                [(str(w[0]), float(w[1]), float(w[2])) for w in words]
                if words
                else None
            ),
        )

    # -- the pipeline's read-back hook ------------------------------------------

    def words_for_clip(self, clip: AudioClip) -> list[WordTiming] | None:
        """The stored words of the take whose bytes ``clip`` carries, or ``None``."""
        if self.recordings is None or clip.bytes_ is None:
            return None
        digest = hashlib.sha256(clip.bytes_).hexdigest()
        key = self._index().get(digest)
        if key is None:
            self._digests = None  # a take imported since: look again, once
            key = self._index().get(digest)
        if key is None:
            return None
        words = self.recordings[key].get("words")
        return [(str(w[0]), float(w[1]), float(w[2])) for w in words] if words else None

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
        items: list[str | Path] = (
            [part.strip() for part in str(audio).split(",") if part.strip()]
            if isinstance(audio, str) and "," in audio
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
        if backend:
            options["backend"] = backend
        if diarize:
            options["diarize"] = True
        try:
            result = scribed.transcribe(str(path), **options)
        except (
            Exception
        ) as e:  # noqa: BLE001 — the backend's own error, with the way out
            raise TranscriberUnavailableError(
                f"transcribing {Path(path).name} with scribed"
                + (f" ({backend})" if backend else "")
                + f" failed: {e}. Pick a backend with --transcriber (scribed.doctor() lists "
                "what runs here), or give --transcript"
            ) from e
        return from_transcript_object(result)

    return transcribe


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
    #: silence heard between the previous take of the same file and this one
    gap_before: float | None = None
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


def _transcripts_for(
    paths: Sequence[Path], transcript: str | Path | Sequence[str | Path] | None
) -> dict[Path, tuple[list[TranscriptSegment], str]]:
    """``{audio path: (segments, kind)}`` from what ``transcript`` names: nothing;
    a directory (paired by stem); one file or text per audio file (same count);
    one file for one take; or one plain transcript whose lines are the takes."""
    if transcript is None or transcript == "":
        return {}
    items: list[str | Path]
    if isinstance(transcript, (str, Path)):
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
                    out[audio] = (
                        parse_transcript(match),
                        match.suffix.lstrip(".").lower(),
                    )
            return out
        items = (
            [part.strip() for part in str(transcript).split(",") if part.strip()]
            if isinstance(transcript, str)
            and "," in transcript
            and all(
                Path(x.strip()).is_file() for x in transcript.split(",") if x.strip()
            )
            else [transcript]
        )
    else:
        items = list(transcript)

    def kind_of(item: str | Path) -> str:
        p = Path(item) if len(str(item)) < 4096 else None
        return (
            p.suffix.lstrip(".").lower() or "text"
            if p is not None and p.is_file()
            else "text"
        )

    if len(items) == len(paths):
        return {
            audio: (parse_transcript(item), kind_of(item))
            for audio, item in zip(paths, items)
        }
    if len(items) != 1:
        raise RecordedVoicesError(
            f"{len(items)} transcript(s) for {len(paths)} audio file(s): give one per file "
            "(a directory pairs them by stem), or one transcript for one take"
        )
    segments = parse_transcript(items[0])
    kind = kind_of(items[0])
    if len(paths) == 1:
        return {paths[0]: (segments, kind)}
    if all(not s.timed for s in segments) and len(segments) == len(paths):
        return {audio: ([seg], kind) for audio, seg in zip(paths, segments)}
    raise RecordedVoicesError(
        f"one transcript ({len(segments)} line(s)) for {len(paths)} audio files: a plain "
        "transcript with one line per file pairs them in order; a timed transcript goes "
        "with ONE take (or one transcript per file, paired by stem from a directory)"
    )


def _timed_segments(
    path: Path,
    total: float,
    given: tuple[list[TranscriptSegment], str] | None,
    *,
    transcribe: Transcriber | None,
    make_transcriber: Callable[[], Transcriber],
) -> tuple[list[TranscriptSegment], str]:
    """The lines of the take at ``path``, each with its span in the file, and
    how the words were obtained (``'srt'``, ``'asr'``, ``'plain+asr'``, ``'file'``)."""
    if given is None:
        segments = list((transcribe or make_transcriber())(path))
        timed = [s for s in segments if s.timed and s.text]
        if not timed:
            raise RecordedVoicesError(
                f"the transcriber found no speech with timings in {path.name}"
            )
        return timed, "asr"
    segments, kind = given
    segments = [s for s in segments if s.text]
    if not segments:
        raise RecordedVoicesError(f"the transcript for {path.name} has no lines")
    if all(s.timed for s in segments):
        inside = [s for s in segments if s.start < total + 1e-6]
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
    the best ratio at or above ``threshold``; its speaker when the take had none."""
    used: set[tuple[str, int]] = set()
    for take in takes:
        best: tuple[float, Any, int, Any] | None = None
        for shot in scene.timeline:
            for idx, line in enumerate(shot.dialogue):
                if (shot.id, idx) in used:
                    continue
                if take.speaker and line.speaker.casefold() != take.speaker.casefold():
                    continue
                score = _ratio(take.segment.text, line.text)
                if score >= threshold and (best is None or score > best[0]):
                    best = (score, shot, idx, line)
        if best is None:
            continue
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
    refs = sorted(
        {
            e.ref
            for shot in scene.timeline
            for e in shot.entities
            if getattr(e, "kind", None) == "character"
            and e.id.casefold() == speaker.casefold()
        }
    )
    characters = mall.get("characters")
    bound = []
    for ref in refs:
        if characters is None or ref not in characters:
            continue
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
        report.voices.append(
            f"voices/{key} ({'created' if created else 'kept'}, provider recorded) is set on "
            f"{len(lines)} line(s) of {speaker!r}, who is no character entity of any shot: a "
            "per-line voice_ref lives in ir/scene.json only, so an edit of scene.md drops it; "
            "add the character to its shots to bind the voice by descriptor"
        )
    else:
        report.voices.append(
            f"voices/{key} ({'created' if created else 'kept'}) already voices {', '.join(refs)}"
        )
    return key


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
    match_threshold: float = DFLT_MATCH_THRESHOLD,
    write: bool = True,
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
    ``write=False`` runs everything but writes nothing (a dry run).
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
    proj = load(project)
    scene, mall = proj.scene, proj.mall
    if RECORDINGS_STORE not in mall:
        raise RecordedVoicesError("this project's mall has no recordings store")
    given = _transcripts_for(paths, transcript)
    speaker_map = _parse_speakers(speakers)
    known = _scene_speakers(scene)
    make_transcriber = lambda: scribed_transcriber(
        transcriber, diarize=diarize
    )  # noqa: E731

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
        )
        spans = cut_spans(segments, total=total)
        previous_end: float | None = None
        for segment, (a, b) in zip(segments, spans):
            take = _Take(
                path=path,
                segment=segment,
                span=(a, b),
                wav=cut_wav(wav, a, b) if (a, b) != (0.0, total) else wav,
                words=rebase_words(segment.words, a),
                speaker=None,
                transcript_kind=kind,
                gap_before=(
                    (segment.start - previous_end) if previous_end is not None else None
                ),
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
    voice_of: dict[str, str] = {}
    recorded_ids: set[int] = set()
    for spk in sorted({t.speaker for t in takes}, key=str.casefold):
        lines = [t.line for t in takes if t.speaker == spk]
        voice_of[spk] = (
            _voice_for(
                mall,
                scene,
                spk,
                voice=voice,
                recorded_by=recorded_by,
                lines=lines,
                report=report,
            )
            if write
            else (voice or f"{spk}{RECORDED_VOICE_SUFFIX}")
        )
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
