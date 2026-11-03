"""TTS provider protocol + supporting dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Iterable, Protocol, runtime_checkable


@dataclass(slots=True)
class VoiceMeta:
    """Metadata for a TTS voice as exposed by a provider.

    The fields are the provider-neutral facts a host shows and filters on
    (an#712): ``is_stock`` is the provider's own answer to "nobody designed
    this" — one of its stock voices (ElevenLabs' premade voices, a system
    voice) rather than one an account designed, cloned, recorded or added from
    a shared voice library; ``accent``, ``description`` and ``preview_url`` (a
    sample to hear before casting, an#666) are ``None`` where the provider has
    none, and ``is_stock`` is ``None`` where it does not say.

    ``extra`` is the provider's own detail, in its own words. Keys hosts read
    (a contract): ElevenLabs's ``category`` and ``labels``. Its
    ``description`` and ``preview_url`` keys repeat the fields for one more
    cycle (hosts read ``extra["preview_url"]`` since an#666): read the fields.

    :meth:`as_row` is the flat, JSON-ready view a host lists
    (:func:`an.audio.list_voices`).

    >>> VoiceMeta("v1", "Rachel", "elevenlabs", is_stock=True, accent="american",
    ...     extra={"category": "premade", "labels": {"age": "young"}}).as_row()
    ... # doctest: +NORMALIZE_WHITESPACE
    {'voice_id': 'v1', 'name': 'Rachel', 'provider': 'elevenlabs',
     'language': 'en', 'gender': None, 'is_stock': True, 'accent': 'american',
     'description': None, 'preview_url': None, 'category': 'premade'}
    """

    voice_id: str
    name: str
    provider: str
    language: str = "en"
    gender: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    is_stock: bool | None = None
    accent: str | None = None
    description: str | None = None
    preview_url: str | None = None

    def as_row(self) -> dict[str, Any]:
        """The voice as one flat, JSON-ready row: every field but ``extra``,
        plus the provider's own ``category`` word (kept for display; filter on
        ``is_stock``)."""
        row = {f.name: getattr(self, f.name) for f in fields(self) if f.name != "extra"}
        row["category"] = (self.extra or {}).get("category")
        return row


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
