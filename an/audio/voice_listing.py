"""The voices a TTS provider offers, as rows a host can show and filter (an#712).

A host that lets a user cast a voice (reelee's character voices) needs the same
few facts from every provider: an id, a name, a language, a gender, an accent,
a description, a sample to hear, and whether the voice is one of the provider's
stock voices that nobody designed (``is_stock``) or one an account designed,
cloned, recorded or added from a shared voice library. Those facts are fields of
:class:`~an.audio.tts.VoiceMeta`, which each provider fills in its own
``list_voices``; a row is its flat view, :meth:`~an.audio.tts.VoiceMeta.as_row`
(:data:`VoiceRow`). So a host filters on a field rather than on a provider's
category string, and a new provider adds itself by filling ``VoiceMeta``.

Two listings, two shapes: :func:`list_voices` (``an.audio.list_voices``) returns
rows, for a host; :func:`browse_voices` and a provider's own ``list_voices``
return :class:`~an.audio.tts.VoiceMeta`.

>>> rows = list_voices("offline")
>>> [(r["voice_id"], r["provider"], r["is_stock"]) for r in rows]
[('default', 'offline', True)]
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TypedDict

from an.audio.providers import make_tts
from an.audio.tts import TTSProvider, VoiceMeta

__all__ = ["VoiceRow", "browse_voices", "list_voices"]

#: The provider ``an voices list`` browses when none is named.
DEFAULT_BROWSE_PROVIDER = "elevenlabs"


#: One voice as a host lists it: :meth:`VoiceMeta.as_row`, every
#: :class:`~an.audio.tts.VoiceMeta` field but ``extra``, plus the provider's own
#: ``category`` word (kept for display; filter on ``is_stock``).
class VoiceRow(TypedDict):
    """The keys of :meth:`VoiceMeta.as_row`, typed for hosts (a plain ``dict``
    at runtime); a test pins them to the dataclass."""

    voice_id: str
    name: str
    provider: str
    language: str | None
    gender: str | None
    is_stock: bool | None
    accent: str | None
    description: str | None
    preview_url: str | None
    category: str | None


def browse_voices(
    provider: str = DEFAULT_BROWSE_PROVIDER,
    *,
    search: str | None = None,
    api_key: str | None = None,
    make: Callable[..., TTSProvider] = make_tts,
) -> list[VoiceMeta]:
    """The voices ``provider`` exposes, optionally filtered by ``search``.

    A provider whose ``list_voices`` takes ``search`` (ElevenLabs) filters on
    its server; for the others the filter is a case-insensitive substring over
    the id, name, accent, description and labels.

    ``make`` is the provider seam: ``make(name)``, or ``make(name,
    api_key=api_key)`` only when a key was given (so a ``make`` that takes no
    key serves every keyless call); default :func:`an.audio.providers.make_tts`.
    ``api_key=None`` means the provider's own default (ElevenLabs: the
    environment's key); an empty key is refused (``ValueError``) rather than
    read as "none".

    >>> class Fake:
    ...     name = "fake"
    ...     def list_voices(self):
    ...         return [VoiceMeta("v1", "Ada", "fake"),
    ...                 VoiceMeta("v2", "Bob", "fake", description="adenoidal")]
    >>> [v.name for v in browse_voices("fake", search="ad", make=lambda _: Fake())]
    ['Ada', 'Bob']
    """
    return _search(_build(provider, api_key=api_key, make=make), search)


def list_voices(
    provider: str,
    *,
    api_key: str | None = None,
    search: str | None = None,
    make: Callable[..., TTSProvider] = make_tts,
) -> list[VoiceRow]:
    """The voices ``provider`` offers, as rows (an#712): :func:`browse_voices`
    through :meth:`VoiceMeta.as_row`.

    ``api_key`` is a host's own key for a provider that takes one
    (:func:`an.audio.providers.listable_providers`); ``None`` means the
    environment's key, and ``""`` is refused (``ValueError``), so a host that
    forwards a guest's absent key never lists the server's own account. A
    provider that cannot be asked at all (its ``check_available()`` fails: no
    key anywhere) raises its own typed error (ElevenLabs:
    :class:`~an.audio.elevenlabs_tts.ElevenLabsUnavailableError`) rather than
    answering ``[]``, so an empty listing means "no voices". ``search`` and
    ``make`` are as in :func:`browse_voices`. An unknown provider is a
    ``ValueError`` naming the known ones.
    """
    tts = _build(provider, api_key=api_key, make=make)
    check = getattr(tts, "check_available", None)
    if check is not None:
        check()
    return [m.as_row() for m in _search(tts, search)]


def _build(
    provider: str, *, api_key: str | None, make: Callable[..., TTSProvider]
) -> TTSProvider:
    """``provider`` from ``make``, handed ``api_key`` only when one was given."""
    if api_key is None:
        return make(provider)
    if not api_key.strip():
        raise ValueError(
            f"an empty api_key for {provider!r} is refused: pass the key, or "
            "api_key=None to use the environment's"
        )
    return make(provider, api_key=api_key)


def _search(tts: TTSProvider, search: str | None) -> list[VoiceMeta]:
    """``tts``'s voices matching ``search``: on its server when its
    ``list_voices`` takes ``search``, else locally (:func:`_haystack`)."""
    if "search" in inspect.signature(tts.list_voices).parameters:
        return list(tts.list_voices(search=search))  # type: ignore[call-arg]
    voices = list(tts.list_voices())
    if search:
        needle = search.lower()
        voices = [v for v in voices if needle in _haystack(v)]
    return voices


def _haystack(v: VoiceMeta) -> str:
    labels = (v.extra or {}).get("labels") or {}
    words = [v.voice_id, v.name, v.accent, v.description, *labels.values()]
    return " ".join(str(w) for w in words if w).lower()
