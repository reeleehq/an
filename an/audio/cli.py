"""``an voices ...`` — browse a TTS provider's voices from the shell (an#209).

Thin string-typed wrappers dispatched by typer the way ``an character ...`` is;
the business logic is :func:`browse_voices`, a plain function over the
provider factories.

    an voices list --provider elevenlabs
    an voices list --provider elevenlabs --search british
    an voices list --provider mac_say
    an voices rescore <project> "He did not ask"    # re-choose a line's take from its cached takes
    an voices reroll <project> "He did not ask"     # synthesize new takes for it (billed)

The ``voice_id`` column is what a ``voices``-store document's ``voice_id`` takes.
``rescore`` and ``reroll`` are the only ways a recorded best-of-N take is
replaced (:func:`an.audio.pipeline.retake_lines`); the next ``an render`` does
the choosing, and prints what it will bill first.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from typing import Any

from an.audio.providers import make_tts
from an.audio.tts import TTSProvider, VoiceMeta

__all__ = ["browse_voices", "format_voices", "retake"]

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


def retake(
    project: str,
    line: str,
    *,
    rescore: bool = False,
    tts: str = DEFAULT_BROWSE_PROVIDER,
    make: Callable[[str], TTSProvider] = make_tts,
) -> str:
    """Release the recorded takes of the lines of ``project`` containing ``line``.

    The plain-function core of ``an voices rescore`` / ``an voices reroll``: see
    :func:`an.audio.pipeline.retake_lines`. ``tts`` must be the provider the
    line is rendered with (its takes are keyed by it).
    """
    from an.audio.pipeline import retake_lines
    from an.project import load

    proj = load(project)
    messages = retake_lines(proj.scene, proj.mall, line, tts=make(tts), rescore=rescore)
    return "\n".join(messages)


def _rescore(project: str, line: str, tts: str = DEFAULT_BROWSE_PROVIDER) -> str:
    """Re-choose the take of each line containing LINE from its cached takes, with
    the current scorer, at the next render (nothing billed while the takes are cached).

    project: the project directory
    line: words of the dialogue line (case-insensitive substring)
    tts: the TTS provider the line is rendered with
    """
    return retake(project, line, rescore=True, tts=tts)


def _reroll(project: str, line: str, tts: str = DEFAULT_BROWSE_PROVIDER) -> str:
    """Synthesize new takes for each line containing LINE at the next render, and
    keep the best (billed: the render prints the cost before the first request).

    project: the project directory
    line: words of the dialogue line (case-insensitive substring)
    tts: the TTS provider the line is rendered with
    """
    return retake(project, line, rescore=False, tts=tts)


_rescore.__name__ = "rescore"  # `an voices rescore`
_reroll.__name__ = "reroll"  # `an voices reroll`

_dispatch_funcs: list[Callable[..., Any]] = [_list, _rescore, _reroll]
