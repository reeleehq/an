"""Audio pipeline — TTS and lip-sync providers + orchestration.

Phase 3 ships:

- Protocols: ``TTSProvider``, ``LipSyncProvider`` (Phase 1).
- Default offline provider: ``OfflineTTS`` (silent WAV). The lip-sync providers
  (``OfflineLipSync`` deterministic char-to-viseme, ``RhubarbLipSync``,
  ``WhisperLipSync``) moved to ``cutan`` with the cut-out genre (an#225); the old
  names still resolve from here, with a warning.
- Real providers: ``ElevenLabsTTS`` (needs ``ELEVEN_API_KEY``).
- Orchestration: ``produce_audio_for_dialogue`` /
  ``produce_audio_for_scene`` walk a SceneIR, synthesize, persist to mall,
  stamp viseme tracks back onto the IR.

The defaults are intentionally offline so the entire `an` pipeline works
without external services.
"""

from an.audio.tts import TTSProvider, AudioClip, VoiceMeta
from an.audio.lipsync import (
    LipSyncProvider,
    Viseme,
    VisemeTrack,
    WordTiming,
    WordTimingProvider,
    NullLipSync,
    word_timings_to_visemes,
)
from an.audio.offline_tts import OfflineTTS
from an.audio.elevenlabs_tts import ElevenLabsTTS
from an.audio.mac_say_tts import MacSayTTS
from an.audio.pipeline import (
    default_tts,
    default_lipsync,
    produce_audio_for_dialogue,
    produce_audio_for_scene,
)
from an.audio.providers import (
    make_tts,
    make_lipsync,
    known_tts_names,
    known_lipsync_names,
)

__all__ = [
    "TTSProvider",
    "AudioClip",
    "VoiceMeta",
    "LipSyncProvider",
    "Viseme",
    "VisemeTrack",
    "WordTiming",
    "WordTimingProvider",
    "NullLipSync",
    "word_timings_to_visemes",
    "OfflineTTS",
    "ElevenLabsTTS",
    "MacSayTTS",
    "default_tts",
    "default_lipsync",
    "produce_audio_for_dialogue",
    "produce_audio_for_scene",
    "make_tts",
    "make_lipsync",
    "known_tts_names",
    "known_lipsync_names",
]

from an._shims import moved_names as _moved_names  # noqa: E402

__getattr__ = _moved_names(
    __name__,
    {
        "OfflineLipSync": "cutan.audio.offline_lipsync:OfflineLipSync",
        "RhubarbLipSync": "cutan.audio.rhubarb_lipsync:RhubarbLipSync",
        "WhisperLipSync": "cutan.audio.whisper_lipsync:WhisperLipSync",
        "StaticWordTimings": "cutan.audio.injectable_lipsync:StaticWordTimings",
        "WordTimingsLipSync": "cutan.audio.injectable_lipsync:WordTimingsLipSync",
    },
)
