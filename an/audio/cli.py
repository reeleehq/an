"""``an voices ...`` — browse a TTS provider's voices from the shell (an#209).

Thin string-typed wrappers dispatched by typer the way ``an character ...`` is;
the business logic is :func:`browse_voices`, a plain function over the
provider factories.

    an voices list --provider elevenlabs
    an voices list --provider elevenlabs --search british
    an voices list --provider mac_say

The ``voice_id`` column is what a ``voices``-store document's ``voice_id`` takes.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from typing import Any

from an.audio.providers import make_tts
from an.audio.tts import TTSProvider, VoiceMeta

__all__ = ["browse_voices", "format_voices"]

#: The provider ``an voices list`` browses when none is named.
DEFAULT_BROWSE_PROVIDER = "elevenlabs"


def browse_voices(
    provider: str = DEFAULT_BROWSE_PROVIDER,
    *,
    search: str | None = None,
    make: Callable[[str], TTSProvider] = make_tts,
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
    tts = make(provider)
    if "search" in inspect.signature(tts.list_voices).parameters:
        return list(tts.list_voices(search=search))  # type: ignore[call-arg]
    voices = list(tts.list_voices())
    if search:
        needle = search.lower()
        voices = [v for v in voices if needle in _haystack(v)]
    return voices


def format_voices(voices: Iterable[VoiceMeta]) -> str:
    """One line per voice: ``voice_id  name  (labels)``.

    >>> from an.audio.tts import VoiceMeta
    >>> print(format_voices([VoiceMeta("abc", "Ada", "x", extra={"labels": {"accent": "british"}})]))
    abc  Ada  (accent=british)
    """
    lines = []
    for v in voices:
        labels = (v.extra or {}).get("labels") or {}
        tail = ", ".join(f"{k}={val}" for k, val in sorted(labels.items()) if val)
        lines.append(f"{v.voice_id}  {v.name}" + (f"  ({tail})" if tail else ""))
    return "\n".join(lines)


def _haystack(v: VoiceMeta) -> str:
    labels = (v.extra or {}).get("labels") or {}
    return " ".join([v.voice_id, v.name, *map(str, labels.values())]).lower()


def _list(provider: str = DEFAULT_BROWSE_PROVIDER, search: str = "") -> str:
    """List a TTS provider's voices; the first column is the voice_id to put in
    a voices-store document.

    provider: TTS provider name — elevenlabs (needs ELEVEN_API_KEY), mac_say, offline
    search: filter by name, description or labels (e.g. british, deep, female)
    """
    voices = browse_voices(provider, search=search or None)
    if not voices:
        return f"no voices from {provider!r}" + (
            f" matching {search!r}" if search else " (is its API key set?)"
        )
    return format_voices(voices)


_list.__name__ = "list"  # the CLI verb: `an voices list`

_dispatch_funcs: list[Callable[..., Any]] = [_list]
