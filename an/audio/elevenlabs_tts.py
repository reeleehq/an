"""ElevenLabsTTS — real speech via the ElevenLabs API. Requires ELEVEN_API_KEY.

Lazily imports the elevenlabs SDK so the rest of `an` works without it.
If you want real speech, ``pip install elevenlabs`` and set
``ELEVEN_API_KEY`` (or ``ELEVENLABS_API_KEY``) in your environment.

**Expressive voices (an#209).** A voice document in the ``voices`` store may
declare, beside ``voice_id``, the ``model_id`` it speaks with, its
``voice_settings`` and a sampling ``seed``; a dialogue line's ``[emotion]`` and
``{direction}`` reach a model that takes inline audio tags (``eleven_v3``,
``eleven_v4`` and their variants) as ``[excited] Hi!``. Which models those are is
voxy's knowledge, not this module's (an#822): ``voxy.dialect_for("elevenlabs",
model_id)`` names each model's *dialect*, and a model outside the inline-tags one
still honours a line's pause cues (``{beat}``, ``{pause}``) as real silence,
rendered by ``voxy.direction.plan_directions``; its other cues are dropped with a
warning.
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
from typing import TYPE_CHECKING, Any, Callable, Iterable

from an.audio.tts import AudioClip, VoiceMeta

if TYPE_CHECKING:  # voxy is imported when a dialect is asked for, never by `import an`
    from voxy.direction import Dialect


_DEFAULT_MODEL_ID: str = "eleven_turbo_v2_5"
_DEFAULT_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs's "Rachel"
_DEFAULT_OUTPUT_FORMAT: str = "mp3_44100_128"
#: The category ElevenLabs gives its stock voices, the ones any account holds
#: and nobody designed: ``VoiceMeta.is_stock`` (an#712). A voice an account
#: added from ElevenLabs' shared Voice Library has another category, and is
#: not stock.
ELEVENLABS_STOCK_CATEGORY: str = "premade"

#: The name voxy's dialect registry knows this engine by (``voxy.dialect_for``).
#: Which ElevenLabs models read inline audio tags (``[excited]``, ``[sighs]``) is
#: voxy's table (``eleven_v3*``, ``eleven_v4*``), extended with
#: ``voxy.register_dialect``; there is no second copy here (an#822).
_VOXY_BACKEND: str = "elevenlabs"

#: The ``voice_settings`` keys the API takes, with the range each accepts
#: (``None`` = a boolean). ``speed`` is the API's documented 0.7–1.2.
VOICE_SETTINGS_RANGES: dict[str, tuple[float, float] | None] = {
    "stability": (0.0, 1.0),
    "similarity_boost": (0.0, 1.0),
    "style": (0.0, 1.0),
    "use_speaker_boost": None,
    "speed": (0.7, 1.2),
}

#: Seeds the API accepts are below this (an unsigned 32-bit integer).
_SEED_MODULUS: int = 2**32

#: Emotions that are the absence of one: never sent as an audio tag.
_UNTAGGED_EMOTIONS: frozenset[str] = frozenset({"neutral"})


class ElevenLabsVoiceError(ValueError):
    """A voice document declares ElevenLabs settings that are malformed."""


class ElevenLabsUnavailableError(RuntimeError):
    """A request cannot be sent: no API key is configured."""


def model_dialect(model_id: str | None, *, backend: str = _VOXY_BACKEND) -> "Dialect":
    """How ``backend``'s model ``model_id`` takes delivery direction: voxy's answer.

    >>> model_dialect("eleven_v3").name, model_dialect("eleven_turbo_v2_5").name
    ('inline-tags', 'plain')
    """
    from voxy.direction import dialect_for

    return dialect_for(backend, model_id)


def model_native_break_s(model_id: str | None) -> float:
    """The longest SSML ``<break>`` ElevenLabs model ``model_id`` renders itself, in
    seconds: voxy's table (0 for a model it does not list, and for v3/v4, which
    take no SSML).

    >>> model_native_break_s("eleven_turbo_v2_5"), model_native_break_s("eleven_v3")
    (3.0, 0.0)
    """
    from voxy.elevenlabs_model import ELEVENLABS_NATIVE_BREAK_S

    return ELEVENLABS_NATIVE_BREAK_S.get(model_id or "", 0.0)


def takes_audio_tags(model_id: str, *, backend: str = _VOXY_BACKEND) -> bool:
    """Whether ``model_id`` reads inline audio tags.

    >>> takes_audio_tags("eleven_v3"), takes_audio_tags("eleven_v4_turbo")
    (True, True)
    >>> takes_audio_tags("eleven_turbo_v2_5")
    False
    """
    return model_dialect(model_id, backend=backend).inline_tags


def _pause_s(cue: str) -> float:
    """Seconds of silence ``cue`` asks for in voxy's vocabulary (0: not a pause)."""
    from voxy.direction import direction

    d = direction(cue)
    return d.pause_s if d.kind == "pause" else 0.0


def _check_dialect(dialect: "Dialect", model_id: str | None) -> None:
    if not dialect.inline_tags and dialect.instruction_param:
        raise ElevenLabsVoiceError(
            f"model {model_id!r} is declared to take direction through "
            f"{dialect.instruction_param!r}, a parameter ElevenLabs does not have; "
            "declare it inline-tags or plain"
        )


def _directed_text(text: str, tags: Sequence[str] | None, dialect: "Dialect") -> str:
    """What is sent for ``text`` with ``tags`` to a model speaking ``dialect``.

    An inline-tags model reads the tags as written; any other gets the pause tags
    as SSML breaks before the words and the rest removed (``voxy.direction``).
    Only the cues are rendered: the words are sent exactly as written.

    >>> from voxy.direction import INLINE, PLAIN
    >>> _directed_text("Hi!", ["excited"], INLINE)
    '[excited] Hi!'
    >>> _directed_text("I said [sic] that.", ["beat"], PLAIN)
    '<break time="0.45s" /> I said [sic] that.'
    >>> _directed_text("Hi!", None, PLAIN)
    'Hi!'
    """
    if not tags:
        return text
    if dialect.inline_tags:
        return tagged_text(text, tags)
    from voxy.direction import PLAIN, plan_directions

    (cues,) = plan_directions(tagged_text("", tags).strip(), PLAIN)
    return f"{cues.text} {text}" if cues.text else text


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
                raise ElevenLabsVoiceError(
                    f"{key} must be true or false, got {value!r}"
                )
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
    #: Every request is charged (an#311: what may never run in memory).
    billed: bool = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str = _DEFAULT_MODEL_ID,
        output_format: str = _DEFAULT_OUTPUT_FORMAT,
        dialect: Callable[[str], "Dialect"] = model_dialect,
        native_break_s: Callable[[str], float] = model_native_break_s,
        client_factory: Any = None,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("ELEVEN_API_KEY")
            or os.environ.get("ELEVENLABS_API_KEY")
        )
        self.model_id = model_id
        self.output_format = output_format
        #: ``model_id -> Dialect``: how a model takes direction (voxy's registry).
        self.dialect = dialect
        #: ``model_id -> seconds``: the longest SSML break a model renders (voxy's table).
        self.native_break_s = native_break_s
        #: ``api_key -> client``; tests inject a fake so nothing reaches the API.
        self.client_factory = client_factory

    def check_available(self) -> None:
        """Raise :class:`ElevenLabsUnavailableError` when a request could not be
        sent (no API key) — what the audio pipeline asks before the first
        request of a render, so nothing is half-synthesized (an#305)."""
        if not self.api_key:
            raise ElevenLabsUnavailableError(
                "ElevenLabsTTS requires an API key. Set ELEVEN_API_KEY in your "
                "environment or pass api_key= to the constructor."
            )

    def _client(self):
        self.check_available()
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
        ``[emotion]`` (unless ``neutral``) then its ``direction`` cues, all of
        them on a model that reads tags. Elsewhere only the direction's pause
        cues are kept (sent as SSML breaks, when the model renders a break that
        long: voxy's table), any other direction cue is dropped with a warning,
        and the emotion stays a face-only cue, as before.
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
        tags = (
            [emotion] if emotion and emotion.lower() not in _UNTAGGED_EMOTIONS else []
        )
        tags += [c for c in direction or [] if c not in tags]
        effective_model = opts.get("model_id", self.model_id)
        dialect = self.dialect(effective_model)
        _check_dialect(dialect, effective_model)
        if tags and dialect.inline_tags:
            opts["audio_tags"] = tags
            return opts
        # a pause cue is kept as real silence when the model renders a break that long
        longest = self.native_break_s(effective_model)
        pauses, dropped, unbreakable = [], [], []
        for cue in direction or []:
            norm = cue.strip().lower()
            pause = _pause_s(norm)
            if not pause:
                dropped.append(cue)
            elif pause <= longest:
                pauses.append(norm)
            else:
                unbreakable.append(cue)
        if pauses:
            opts["audio_tags"] = pauses
        if dropped:
            warnings.warn(
                f"direction {dropped} is dropped: model {effective_model!r} "
                "does not read audio tags (declare model_id: eleven_v3 on the voice)",
                stacklevel=2,
            )
        if unbreakable:
            warnings.warn(
                f"pause {unbreakable} is dropped: model {effective_model!r} renders "
                f"no SSML break that long (its longest: {longest:g}s)",
                stacklevel=2,
            )
        return opts

    def take_options(self, options: Mapping[str, Any], take: int) -> dict[str, Any]:
        """The request for candidate ``take`` of a best-of-N line (:mod:`an.audio.takes`).

        A declared ``seed`` is offset by the take, so a model that does honour
        it (every model but ``eleven_v3``, measured) still returns different
        takes; without a seed the request is unchanged and the model's own
        sampling varies the take.

        >>> ElevenLabsTTS(api_key="unused").take_options({"seed": 11}, 2)
        {'seed': 13}
        """
        out = dict(options)
        if out.get("seed") is not None:
            out["seed"] = (int(out["seed"]) + int(take)) % _SEED_MODULUS
        return out

    def billed_characters(
        self,
        text: str,
        *,
        audio_tags: Sequence[str] | None = None,
        model_id: str | None = None,
        **_options: Any,
    ) -> int:
        """Characters one request bills: the text as sent, audio tags included.

        >>> tts = ElevenLabsTTS(api_key="unused")
        >>> tts.billed_characters("Hi!", audio_tags=["excited"], model_id="eleven_v3")
        13
        """
        return len(self._sent_text(text, audio_tags, model_id))

    def _sent_text(
        self, text: str, audio_tags: Sequence[str] | None, model_id: str | None
    ) -> str:
        model = model_id or self.model_id
        dialect = self.dialect(model)
        _check_dialect(dialect, model)
        return _directed_text(text, audio_tags, dialect)

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
            text=self._sent_text(text, audio_tags, model_id),
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
                category = getattr(v, "category", None)
                description = getattr(v, "description", None)
                # a sample to hear before casting the voice (an#666)
                preview_url = getattr(v, "preview_url", None)
                out.append(
                    VoiceMeta(
                        voice_id=getattr(v, "voice_id", ""),
                        name=getattr(v, "name", ""),
                        provider=self.name,
                        language=labels.get("language", "en"),
                        gender=labels.get("gender"),
                        is_stock=category == ELEVENLABS_STOCK_CATEGORY,
                        accent=labels.get("accent"),
                        description=description,
                        preview_url=preview_url,
                        extra={
                            "category": category,
                            "labels": labels,
                            # the fields again, for one cycle: hosts read
                            # extra["preview_url"] since an#666 (an#712)
                            "description": description,
                            "preview_url": preview_url,
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
    kbps = next((int(p) for p in output_format.split("_")[2:3] if p.isdigit()), 128)
    return len(audio_bytes) / (kbps * 1000 / 8)
