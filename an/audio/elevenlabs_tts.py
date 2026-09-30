"""ElevenLabsTTS — real speech via the ElevenLabs API. Requires ELEVEN_API_KEY.

Lazily imports the elevenlabs SDK so the rest of `an` works without it.
If you want real speech, ``pip install elevenlabs`` and set
``ELEVEN_API_KEY`` (or ``ELEVENLABS_API_KEY``) in your environment.

**Expressive voices (an#209).** A voice document in the ``voices`` store may
declare, beside ``voice_id``, the ``model_id`` it speaks with, its
``voice_settings`` and a sampling ``seed``; a dialogue line's ``[emotion]`` and
``{direction}`` reach a model that takes inline audio tags (``eleven_v3``,
``eleven_v4`` and their variants) as ``[excited] Hi!``.
:meth:`ElevenLabsTTS.synthesis_options` turns those into the keyword arguments
:meth:`ElevenLabsTTS.synthesize` takes — the audio pipeline keys its cache on
exactly that dict, and a voice declaring none of them yields ``{}``, so no
existing cache key moves.

>>> tts = ElevenLabsTTS(api_key="unused")
>>> tts.synthesis_options({})
{}
>>> tts.synthesis_options({"model_id": "eleven_v3"}, emotion="happy", direction=["sighs"])
{'model_id': 'eleven_v3', 'audio_tags': ['happy', 'sighs']}
>>> tts.synthesis_options({"voice_settings": {"stability": 0.3, "speed": 1.1}})
{'voice_settings': {'speed': 1.1, 'stability': 0.3}}
>>> tagged_text("Hi!", ["excited"])
'[excited] Hi!'
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Iterable

from an.audio.tts import AudioClip, VoiceMeta


_DEFAULT_MODEL_ID: str = "eleven_turbo_v2_5"
_DEFAULT_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs's "Rachel"
_DEFAULT_OUTPUT_FORMAT: str = "mp3_44100_128"

#: Model ids that read inline audio tags (``[excited]``, ``[sighs]``). Matched
#: as prefixes, so ``eleven_v3_conversational`` and ``eleven_v4_turbo`` count.
#: Every other model would speak the brackets, so it never receives a tag.
AUDIO_TAG_MODEL_PREFIXES: tuple[str, ...] = ("eleven_v3", "eleven_v4")

#: The ``voice_settings`` keys the API takes, with the range each accepts
#: (``None`` = a boolean). ``speed`` is the API's documented 0.7–1.2.
VOICE_SETTINGS_RANGES: dict[str, tuple[float, float] | None] = {
    "stability": (0.0, 1.0),
    "similarity_boost": (0.0, 1.0),
    "style": (0.0, 1.0),
    "use_speaker_boost": None,
    "speed": (0.7, 1.2),
}

#: Emotions that are the absence of one: never sent as an audio tag.
_UNTAGGED_EMOTIONS: frozenset[str] = frozenset({"neutral"})


class ElevenLabsVoiceError(ValueError):
    """A voice document declares ElevenLabs settings that are malformed."""


def takes_audio_tags(
    model_id: str, *, prefixes: Sequence[str] = AUDIO_TAG_MODEL_PREFIXES
) -> bool:
    """Whether ``model_id`` reads inline audio tags.

    >>> takes_audio_tags("eleven_v3"), takes_audio_tags("eleven_turbo_v2_5")
    (True, False)
    """
    return any(str(model_id).startswith(p) for p in prefixes)


def normalize_voice_settings(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """The canonical ``voice_settings`` dict — only what was declared, key-sorted.

    Omit-when-unset: ``None`` and ``{}`` give ``{}``. Unknown keys and values out
    of range raise, so a typo cannot silently fall back to the account default.

    >>> normalize_voice_settings({"style": 1, "stability": 0.25})
    {'stability': 0.25, 'style': 1.0}
    >>> normalize_voice_settings({"stabilty": 0.5})
    Traceback (most recent call last):
        ...
    an.audio.elevenlabs_tts.ElevenLabsVoiceError: unknown voice_settings key(s) ['stabilty']; known: ['similarity_boost', 'speed', 'stability', 'style', 'use_speaker_boost']
    """
    if not raw:
        return {}
    if not isinstance(raw, Mapping):
        raise ElevenLabsVoiceError(
            f"voice_settings must be a mapping, got {type(raw).__name__}"
        )
    unknown = sorted(set(raw) - set(VOICE_SETTINGS_RANGES))
    if unknown:
        raise ElevenLabsVoiceError(
            f"unknown voice_settings key(s) {unknown}; "
            f"known: {sorted(VOICE_SETTINGS_RANGES)}"
        )
    out: dict[str, Any] = {}
    for key in sorted(raw):
        value, bounds = raw[key], VOICE_SETTINGS_RANGES[key]
        if value is None:
            continue
        if bounds is None:
            if not isinstance(value, bool):
                raise ElevenLabsVoiceError(f"{key} must be true or false, got {value!r}")
            out[key] = value
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ElevenLabsVoiceError(f"{key} must be a number, got {value!r}")
        lo, hi = bounds
        if not lo <= float(value) <= hi:
            raise ElevenLabsVoiceError(f"{key}={value} is outside [{lo}, {hi}]")
        out[key] = float(value)
    return out


def tagged_text(text: str, tags: Sequence[str] | None) -> str:
    """``text`` with each tag prefixed as ``[tag]`` — what an audio-tag model reads."""
    if not tags:
        return text
    return " ".join(f"[{t}]" for t in tags) + " " + text


class ElevenLabsTTS:
    """ElevenLabs-backed TTSProvider. Constructor takes an optional api_key
    (falls back to ``ELEVEN_API_KEY`` / ``ELEVENLABS_API_KEY``).

    Implements the ``TTSProvider`` protocol, plus the optional
    ``synthesis_options`` hook the audio pipeline reads (an#209).
    """

    name: str = "elevenlabs"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str = _DEFAULT_MODEL_ID,
        output_format: str = _DEFAULT_OUTPUT_FORMAT,
        audio_tag_model_prefixes: Sequence[str] = AUDIO_TAG_MODEL_PREFIXES,
        client_factory: Any = None,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("ELEVEN_API_KEY")
            or os.environ.get("ELEVENLABS_API_KEY")
        )
        self.model_id = model_id
        self.output_format = output_format
        self.audio_tag_model_prefixes = tuple(audio_tag_model_prefixes)
        #: ``api_key -> client``; tests inject a fake so nothing reaches the API.
        self.client_factory = client_factory

    def _client(self):
        if not self.api_key:
            raise RuntimeError(
                "ElevenLabsTTS requires an API key. Set ELEVEN_API_KEY in your "
                "environment or pass api_key= to the constructor."
            )
        if self.client_factory is not None:
            return self.client_factory(self.api_key)
        try:
            from elevenlabs.client import ElevenLabs  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "elevenlabs package not installed. Install with: pip install elevenlabs"
            ) from e
        return ElevenLabs(api_key=self.api_key)

    def synthesis_options(
        self,
        voice: Mapping[str, Any],
        *,
        emotion: str | None = None,
        direction: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """The ``synthesize`` keyword arguments a voice document and a line imply.

        Only what is declared appears (``{}`` for a plain voice), so the audio
        cache key — which includes this dict when it is non-empty — is unchanged
        for every voice that declares nothing new. ``audio_tags`` are the line's
        ``[emotion]`` (unless ``neutral``) then its ``direction`` cues, and only
        on a model that reads tags; elsewhere a direction is dropped with a
        warning and the emotion stays a face-only cue, as before.
        """
        opts: dict[str, Any] = {}
        model = voice.get("model_id")
        if model is not None:
            if not isinstance(model, str) or not model:
                raise ElevenLabsVoiceError(f"model_id must be a string, got {model!r}")
            opts["model_id"] = model
        settings = normalize_voice_settings(voice.get("voice_settings"))
        if settings:
            opts["voice_settings"] = settings
        seed = voice.get("seed")
        if seed is not None:
            if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
                raise ElevenLabsVoiceError(
                    f"seed must be a non-negative integer, got {seed!r}"
                )
            opts["seed"] = seed
        emotion = (emotion or "").strip()
        tags = ([emotion] if emotion and emotion.lower() not in _UNTAGGED_EMOTIONS else [])
        tags += [c for c in direction or [] if c not in tags]
        effective_model = opts.get("model_id", self.model_id)
        if tags and takes_audio_tags(effective_model, prefixes=self.audio_tag_model_prefixes):
            opts["audio_tags"] = tags
        elif direction:
            warnings.warn(
                f"direction {list(direction)} is dropped: model {effective_model!r} "
                "does not read audio tags (declare model_id: eleven_v3 on the voice)",
                stacklevel=2,
            )
        return opts

    def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        *,
        model_id: str | None = None,
        voice_settings: Mapping[str, Any] | None = None,
        seed: int | None = None,
        audio_tags: Sequence[str] | None = None,
        **kw,
    ) -> AudioClip:
        """Speak ``text``. The clip's ``transcript`` is ``text`` WITHOUT the tags,
        so alignment and captions never read a cue."""
        client = self._client()
        # ElevenLabs has no voice named "default"; if the caller passes the
        # canonical "default" sentinel (or None), use this provider's pinned
        # default voice instead.
        effective_voice = (
            voice_id if voice_id and voice_id != "default" else _DEFAULT_VOICE_ID
        )
        request: dict[str, Any] = dict(
            voice_id=effective_voice,
            text=tagged_text(text, audio_tags),
            model_id=model_id or self.model_id,
            output_format=self.output_format,
        )
        if voice_settings:
            request["voice_settings"] = _sdk_voice_settings(voice_settings)
        if seed is not None:
            request["seed"] = seed
        audio_bytes = b"".join(client.text_to_speech.convert(**request))

        out_path = kw.get("path")
        if out_path is not None:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(audio_bytes)

        return AudioClip(
            path=out_path,
            bytes_=audio_bytes,
            duration=_clip_duration(audio_bytes, self.output_format),
            sample_rate=44100,
            channels=1,
            voice_id=effective_voice,
            transcript=text,
        )

    def list_voices(self, *, search: str | None = None) -> Iterable[VoiceMeta]:
        """The account's voices (its own plus the ones it saved), newest API.

        ``search`` filters by name, description and labels on the server. An
        absent key or SDK yields ``[]``; a key that is present and a call that
        fails RAISES — an empty listing must mean "no voices", not "it broke".
        """
        try:
            client = self._client()
        except RuntimeError:
            return []
        out: list[VoiceMeta] = []
        if not hasattr(client.voices, "search"):  # SDK < 2: one unfiltered page
            pages = iter([client.voices.get_all()])
        else:
            pages = _search_pages(client, search)
        for page in pages:
            for v in page.voices:
                labels = dict(getattr(v, "labels", None) or {})
                out.append(
                    VoiceMeta(
                        voice_id=getattr(v, "voice_id", ""),
                        name=getattr(v, "name", ""),
                        provider=self.name,
                        language=labels.get("language", "en"),
                        gender=labels.get("gender"),
                        extra={
                            "category": getattr(v, "category", None),
                            "description": getattr(v, "description", None),
                            "labels": labels,
                        },
                    )
                )
        return out


def _search_pages(client, search: str | None, *, page_size: int = 100):
    """``voices.search`` pages until the server says there are no more (or
    repeats a token, which would otherwise loop forever)."""
    token, seen = None, set()
    while True:
        page = client.voices.search(
            search=search or None, page_size=page_size, next_page_token=token
        )
        yield page
        token = getattr(page, "next_page_token", None)
        if not getattr(page, "has_more", False) or not token or token in seen:
            return
        seen.add(token)


def _sdk_voice_settings(settings: Mapping[str, Any]):
    """The SDK's ``VoiceSettings`` for ``settings`` (a plain dict without the SDK)."""
    try:
        from elevenlabs import VoiceSettings  # type: ignore
    except ImportError:
        return dict(settings)
    return VoiceSettings(**settings)


def _clip_duration(audio_bytes: bytes, output_format: str) -> float:
    """Seconds of ``audio_bytes``: ffprobe's reading — the one the pipeline's
    cached path uses, so a fresh and a cached line time identically — else the
    bitrate estimate (``mp3_44100_128`` is 128 kbit/s = 16 000 bytes/s)."""
    if not audio_bytes:
        return 0.0
    from an.audio.pipeline import _ffprobe_duration

    measured = _ffprobe_duration(audio_bytes)
    if measured > 0:
        return measured
    kbps = next(
        (int(p) for p in output_format.split("_")[2:3] if p.isdigit()), 128
    )
    return len(audio_bytes) / (kbps * 1000 / 8)
