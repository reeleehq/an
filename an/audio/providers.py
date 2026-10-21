"""Provider factory: name → concrete TTS/LipSync provider instance.

Used by the CLI and orchestrator to map ``--tts elevenlabs`` (and similar)
strings into instantiated providers without callers having to import the
specific classes.

>>> from an.audio.providers import make_tts, make_lipsync
>>> make_tts("offline").name
'offline'
>>> make_lipsync("none").name
'none'
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, Callable

from an.audio.elevenlabs_tts import ElevenLabsTTS
from an.audio.lipsync import LipSyncProvider, NullLipSync
from an.audio.mac_say_tts import MacSayTTS
from an.audio.offline_tts import OfflineTTS
from an.audio.recorded import RecordedTTS, RECORDINGS_STORE
from an.audio.tts import TTSProvider


def _recorded_factory(*, mall: Mapping[str, Any] | None = None) -> RecordedTTS:
    """The ``recorded`` provider over the project's recordings store (an#490)."""
    store = mall.get(RECORDINGS_STORE) if mall is not None else None
    return RecordedTTS(recordings=store)


#: A factory takes no arguments, or ``mall=`` when the provider reads a project
#: store (``recorded``): :func:`make_tts` passes it only to those that accept it.
TTS_FACTORIES: dict[str, Callable[..., TTSProvider]] = {
    "offline": lambda: OfflineTTS(),
    "elevenlabs": lambda: ElevenLabsTTS(),
    "mac_say": lambda: MacSayTTS(),
    "recorded": _recorded_factory,
}

#: The language a provider aligns for when the caller says nothing. Only
#: Rhubarb reads it today (its recognizer follows the language, an#96).
DEFAULT_LANGUAGE: str = "en"

#: The lip-sync providers the core itself offers. A genre adds its own through
#: the ``lipsync.<name>`` service (``cutan``: ``offline``, ``rhubarb``,
#: ``whisper``); see :func:`lipsync_factories`.
LIPSYNC_FACTORIES: dict[str, Callable[..., LipSyncProvider]] = {
    "none": lambda **_: NullLipSync(),
}

#: The provider :func:`default_lipsync` prefers when a genre registered it.
DFLT_LIPSYNC: str = "offline"


def lipsync_factories() -> dict[str, Callable[..., LipSyncProvider]]:
    """Every lip-sync factory by name: the core's, then the loaded genres' services."""
    from an.genres import services

    return {**services("lipsync."), **LIPSYNC_FACTORIES}


def _accepts(factory: Callable[..., Any], keyword: str) -> bool:
    try:
        params = inspect.signature(factory).parameters
    except (TypeError, ValueError):  # a builtin, a C callable: assume not
        return False
    return keyword in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


def make_tts(name: str, *, mall: Mapping[str, Any] | None = None) -> TTSProvider:
    """Instantiate a TTS provider by name.

    ``mall`` (the project mall) reaches the factories that take it — the
    ``recorded`` provider reads the project's ``recordings`` store; the others
    are built as before. Raises ``ValueError`` for unknown names with a list of
    known options.

    >>> make_tts("recorded").name
    'recorded'
    """
    try:
        factory = TTS_FACTORIES[name]
    except KeyError:
        raise ValueError(
            f"unknown TTS provider {name!r}; known: {sorted(TTS_FACTORIES)}"
        ) from None
    if mall is not None and _accepts(factory, "mall"):
        return factory(mall=mall)
    return factory()


def make_lipsync(name: str, *, language: str = DEFAULT_LANGUAGE) -> LipSyncProvider:
    """Instantiate a LipSync provider by name.

    ``language`` (BCP-47) reaches providers that select behaviour by language —
    Rhubarb's recognizer today; a future aligner's weight allowlist.

    The default name (``"offline"``) resolves to :class:`~an.audio.lipsync.NullLipSync`
    when no loaded genre provides it, so voicing a line needs no genre; any other
    name that nothing provides is an error that says how to get it.

    >>> make_lipsync("offline").name in {"offline", "none"}
    True
    """
    factories = lipsync_factories()
    if name == DFLT_LIPSYNC and name not in factories:
        # The default name, with no genre that draws mouths loaded: a line is still
        # voiced, and gets no viseme track (the out-of-the-box path must not need a genre).
        return NullLipSync()
    try:
        factory = factories[name]
    except KeyError:
        hint = (
            ' The cut-out genre provides "offline", "rhubarb" and "whisper": '
            'pip install "an[cutout]" and load genres (an.genres.load()).'
            if name in {"offline", "rhubarb", "whisper"}
            else ""
        )
        raise ValueError(
            f"unknown LipSync provider {name!r}; known: {sorted(factories)}.{hint}"
        ) from None
    return factory(language=language)


def known_tts_names() -> list[str]:
    """Return the registered TTS provider names."""
    return sorted(TTS_FACTORIES)


def known_lipsync_names() -> list[str]:
    """Return the registered LipSync provider names."""
    return sorted(lipsync_factories())
