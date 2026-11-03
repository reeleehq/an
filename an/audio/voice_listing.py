"""The voices a TTS provider offers, as rows a host can show and filter (an#712).

A host that lets a user cast a voice (reelee's character voices) needs the same
few facts from every provider: an id, a name, a language, a gender, an accent,
a description, a sample to hear, and whether the voice is one of the provider's
own library voices that nobody designed (``is_library``) or one an account
designed, cloned or recorded. Those facts are the provider's; this module turns
each provider's :class:`~an.audio.tts.VoiceMeta` into one flat
:class:`VoiceRow`, so a host filters on a field rather than on a provider's
category string, and a new provider adds itself by filling ``VoiceMeta``
(``is_library`` included) in its own ``list_voices``.

>>> rows = list_voices("offline")
>>> [(r.voice_id, r.provider, r.is_library) for r in rows]
[('default', 'offline', True)]
>>> sorted(rows[0].as_dict())[:4]
['accent', 'category', 'description', 'gender']
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from an.audio.tts import TTSProvider, VoiceMeta

__all__ = ["VoiceRow", "browse_voices", "list_voices", "voice_row"]

#: The provider ``an voices list`` browses when none is named.
DEFAULT_BROWSE_PROVIDER = "elevenlabs"


@dataclass(frozen=True)
class VoiceRow:
    """One voice as a host lists it. ``category`` is the provider's own word
    for it (ElevenLabs': ``premade``, ``cloned``, ``generated``…), kept for
    display; filter on ``is_library`` (``None``: the provider does not say)."""

    voice_id: str
    name: str
    provider: str
    language: str | None = None
    gender: str | None = None
    accent: str | None = None
    description: str | None = None
    preview_url: str | None = None
    category: str | None = None
    is_library: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        """The row as plain JSON-ready data."""
        return asdict(self)


def voice_row(meta: VoiceMeta) -> VoiceRow:
    """``meta`` as a :class:`VoiceRow`: its own fields, and the keys hosts
    read from its ``extra`` (``labels.accent``, ``description``,
    ``preview_url``, ``category``).

    >>> voice_row(VoiceMeta("v1", "Rachel", "elevenlabs", gender="female",
    ...     extra={"labels": {"accent": "american"}, "category": "premade"},
    ...     is_library=True)).accent
    'american'
    """
    extra = dict(meta.extra or {})
    labels = dict(extra.get("labels") or {})
    return VoiceRow(
        voice_id=meta.voice_id,
        name=meta.name,
        provider=meta.provider,
        language=meta.language,
        gender=meta.gender,
        accent=labels.get("accent"),
        description=extra.get("description"),
        preview_url=extra.get("preview_url"),
        category=extra.get("category"),
        is_library=meta.is_library,
    )


def browse_voices(
    provider: str = DEFAULT_BROWSE_PROVIDER,
    *,
    search: str | None = None,
    make: Callable[[str], TTSProvider] | None = None,
) -> list[VoiceMeta]:
    """The voices ``provider`` exposes, optionally filtered by ``search``.

    A provider whose ``list_voices`` takes ``search`` (ElevenLabs) filters on
    its server; for the others the filter is a case-insensitive substring over
    the name, id and labels.

    >>> from an.audio.tts import VoiceMeta
    >>> class Fake:
    ...     name = "fake"
    ...     def list_voices(self):
    ...         return [VoiceMeta("v1", "Ada", "fake"), VoiceMeta("v2", "Bob", "fake")]
    >>> [v.name for v in browse_voices("fake", search="ad", make=lambda _: Fake())]
    ['Ada']
    """
    if make is None:
        from an.audio.providers import make_tts as make
    tts = make(provider)
    if "search" in inspect.signature(tts.list_voices).parameters:
        return list(tts.list_voices(search=search))  # type: ignore[call-arg]
    voices = list(tts.list_voices())
    if search:
        needle = search.lower()
        voices = [v for v in voices if needle in _haystack(v)]
    return voices


def _haystack(v: VoiceMeta) -> str:
    labels = (v.extra or {}).get("labels") or {}
    return " ".join([v.voice_id, v.name, *map(str, labels.values())]).lower()


def list_voices(
    provider: str,
    *,
    api_key: str | None = None,
    search: str | None = None,
    make: Callable[..., TTSProvider] | None = None,
) -> list[VoiceRow]:
    """The voices ``provider`` offers, as rows (an#712): :func:`browse_voices`
    (``search`` on the provider's side when it can, else over name, id and
    labels) through :func:`voice_row`. ``api_key`` is a host's own key for a
    provider that takes one (else the environment's); ``make`` is the
    provider seam, ``make(name, api_key=...)`` (default
    :func:`an.audio.providers.make_tts`). An unknown provider is a
    ``ValueError`` naming the known ones.
    """
    if make is None:
        from an.audio.providers import make_tts as make

    def build(name: str) -> TTSProvider:
        return make(name, api_key=api_key)

    return [voice_row(m) for m in browse_voices(provider, search=search, make=build)]
