"""TTS provider protocol + supporting dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol, runtime_checkable


@dataclass(slots=True)
class VoiceMeta:
    """Metadata for a TTS voice as exposed by a provider.

    ``extra`` is the provider's own detail. Keys hosts read (a contract):
    ElevenLabs's ``category``, ``description``, ``labels`` and ``preview_url``
    (a sample to hear before casting, an#666; ``None`` when it has none).

    ``is_library`` is the provider's own answer to "nobody designed this": a
    voice of the provider's shared library (ElevenLabs' premade voices, a
    system voice), not one an account designed, cloned or recorded (an#712);
    ``None`` when the provider does not say.
    """

    voice_id: str
    name: str
    provider: str
    language: str = "en"
    gender: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    is_library: bool | None = None


@dataclass(slots=True)
class AudioClip:
    """A rendered audio clip, on disk or in memory."""

    path: Path | None = None
    bytes_: bytes | None = None
    duration: float = 0.0
    sample_rate: int = 44100
    channels: int = 1
    voice_id: str | None = None
    transcript: str | None = None
    #: The clip's word timings — ``(word, start_s, end_s)`` from the clip's
    #: start — when the provider knows them (a recorded take imported with a
    #: timed transcript: :mod:`an.audio.recorded`); ``None`` otherwise. A
    #: lip-sync provider that aligns from words prefers these to its own
    #: transcription, and the audio pipeline stamps them on the line.
    words: list[tuple[str, float, float]] | None = None
    #: The clip's phone timings, ``(phone, start_s, end_s)`` from the clip's
    #: start, when an aligner gave them (a TextGrid's ``phones`` tier on a
    #: recorded take, an#491); ``None`` otherwise. A lip-sync provider that
    #: maps phones to mouth shapes can use them instead of spreading letters.
    phones: list[tuple[str, float, float]] | None = None


@runtime_checkable
class TTSProvider(Protocol):
    """Text-to-speech provider."""

    name: str

    def synthesize(self, text: str, voice_id: str, **kw: Any) -> AudioClip:
        """Render ``text`` in ``voice_id``'s voice. Returns an AudioClip."""

    def list_voices(self) -> Iterable[VoiceMeta]:
        """Return all voices the provider exposes."""
