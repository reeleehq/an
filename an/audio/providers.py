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

from typing import Callable

from an.audio.elevenlabs_tts import ElevenLabsTTS
from an.audio.lipsync import LipSyncProvider, NullLipSync
from an.audio.mac_say_tts import MacSayTTS
from an.audio.offline_tts import OfflineTTS
from an.audio.tts import TTSProvider


TTS_FACTORIES: dict[str, Callable[[], TTSProvider]] = {
    "offline": lambda: OfflineTTS(),
    "elevenlabs": lambda: ElevenLabsTTS(),
    "mac_say": lambda: MacSayTTS(),
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


def make_tts(name: str) -> TTSProvider:
    """Instantiate a TTS provider by name.

    Raises ``ValueError`` for unknown names with a list of known options.
    """
    try:
        return TTS_FACTORIES[name]()
    except KeyError:
        raise ValueError(
            f"unknown TTS provider {name!r}; known: {sorted(TTS_FACTORIES)}"
        ) from None


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
