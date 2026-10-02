"""Which voice speaks a dialogue line: the character → voice binding (an#194).

A line resolves its voice — a key of the project's ``voices`` store — in this
order, first hit wins:

1. the line's own ``voice_ref`` (set from Python or ``ir/scene.json``);
2. the speaking character's ``voice_ref``: the shot entity whose ``id`` is the
   line's ``speaker``, read from its descriptor in the ``characters`` store with
   the entity's ``overrides`` merged over it (so ``overrides: {voice_ref: x}``
   on the entity re-voices it for one shot);
3. :data:`DEFAULT_VOICE`.

A voice document may name the TTS provider's own voice with ``voice_id`` (a
``say -v`` name for ``mac_say``, a voice id for ElevenLabs); the provider is
handed that, and otherwise the store key itself. A document that declares
``provider`` scopes its provider-specific keys (``voice_id``, and the
``model_id`` / ``voice_settings`` / ``seed`` ElevenLabs reads — an#209) to that
provider: rendered with another one, the line is handed ``"default"``, so an
ElevenLabs-voiced project previews with ``mac_say`` or ``offline`` instead of
failing on a foreign voice id. Nothing declared anywhere
resolves every line to ``"default"`` handed to the provider as ``"default"`` —
exactly what the pipeline did before this module, so no cache key moves.

The document's ``provider`` also DECIDES who speaks the line when the render
names no provider (an#305): :func:`declared_provider` reads it, and
:func:`an.audio.pipeline.tts_chooser` turns it into the provider — so a voice
written for ElevenLabs is spoken by ElevenLabs by a plain ``an render``, and
``--tts`` is an override for every line.

>>> from an.ir.schema import AssetRef, Dialogue, Shot
>>> shot = Shot(id="s", entities=[
...     AssetRef(kind="character", id="carl", store="characters", ref="carl"),
...     AssetRef(kind="character", id="ned", store="characters", ref="ned",
...              overrides={"voice_ref": "ned_sad"})])
>>> mall = {"characters": {"carl": {"voice_ref": "carl_kid"}, "ned": {"voice_ref": "ned_kid"}},
...         "voices": {"carl_kid": {"voice_id": "Junior"}}}
>>> [line_voice_id(Dialogue(speaker=s, text="hi"), shot, mall) for s in ("carl", "ned", "narrator")]
['carl_kid', 'ned_sad', 'default']
>>> line_voice_id(Dialogue(speaker="carl", text="hi", voice_ref="own"), shot, mall)
'own'
>>> provider_voice(mall, "carl_kid"), provider_voice(mall, "default")
('Junior', None)
>>> mall["voices"]["bob"] = {"provider": "elevenlabs", "voice_id": "abc123"}
>>> provider_voice(mall, "bob", tts_name="elevenlabs"), provider_voice(mall, "bob", tts_name="mac_say")
('abc123', 'default')
>>> declared_provider(mall, "bob"), declared_provider(mall, "carl_kid")
('elevenlabs', None)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The voice a line gets when neither it nor its speaker names one.
DEFAULT_VOICE: str = "default"
#: The key, in a voice document, naming the TTS provider's own voice.
PROVIDER_VOICE_KEY: str = "voice_id"
#: The key, in a voice document, naming the TTS provider it is written for.
PROVIDER_KEY: str = "provider"
#: The key, in a character descriptor (or an entity's ``overrides``), naming
#: the character's voice in the ``voices`` store.
CHARACTER_VOICE_KEY: str = "voice_ref"


def speaker_voice_ref(speaker: str, shot: Any, mall: Mapping | None) -> str | None:
    """The voice the speaking character is bound to in ``shot``, or ``None``.

    ``None`` when no character entity of the shot has the speaker's id (an
    off-screen narrator), or when neither its descriptor nor its ``overrides``
    name a voice. A store that is absent, or that does not hold the ref, still
    lets the entity's ``overrides`` speak.
    """
    entity = next(
        (
            e
            for e in getattr(shot, "entities", ())
            if e.kind == "character" and e.id == speaker
        ),
        None,
    )
    if entity is None:
        return None
    doc: Mapping = {}
    store = mall.get("characters") if mall is not None else None
    if store is not None:
        try:
            found = store[entity.ref] if entity.ref in store else None
        except (KeyError, TypeError):
            found = None
        if isinstance(found, Mapping):
            doc = found
    merged = {**doc, **(entity.overrides or {})}
    ref = merged.get(CHARACTER_VOICE_KEY)
    return ref if isinstance(ref, str) and ref else None


def line_voice_id(
    line: Any, shot: Any, mall: Mapping | None, *, default: str = DEFAULT_VOICE
) -> str:
    """The ``voices``-store key ``line`` is spoken with (see the module doc)."""
    return line.voice_ref or speaker_voice_ref(line.speaker, shot, mall) or default


def voice_document(mall: Mapping | None, voice_id: str) -> Mapping:
    """``mall["voices"][voice_id]`` when it is a mapping, else ``{}``."""
    voices = mall.get("voices") if mall is not None else None
    if voices is None or voice_id not in voices:
        return {}
    doc = voices[voice_id]
    return doc if isinstance(doc, Mapping) else {}


def declared_provider(mall: Mapping | None, voice_id: str) -> str | None:
    """The TTS provider ``mall["voices"][voice_id]`` is written for, lower-cased,
    or ``None`` when the voice declares none (or has no document).

    >>> declared_provider({"voices": {"v": {"provider": " ElevenLabs "}}}, "v")
    'elevenlabs'
    >>> declared_provider({"voices": {"v": {"provider": ""}}}, "v") is None
    True
    """
    declared = voice_document(mall, voice_id).get(PROVIDER_KEY)
    if not isinstance(declared, str) or not declared.strip():
        return None
    return declared.strip().lower()


def voice_applies(doc: Mapping, tts_name: str | None) -> bool:
    """Whether ``doc``'s provider-specific keys apply under the TTS ``tts_name``.

    True when the document names no ``provider``, or names this one (case
    ignored), or when the caller does not say which provider is speaking.

    >>> voice_applies({}, "offline"), voice_applies({"provider": "ElevenLabs"}, "elevenlabs")
    (True, True)
    >>> voice_applies({"provider": "elevenlabs"}, "offline")
    False
    """
    declared = doc.get(PROVIDER_KEY)
    if not declared or tts_name is None:
        return True
    return str(declared).strip().lower() == str(tts_name).strip().lower()


def provider_voice(
    mall: Mapping | None, voice_id: str, *, tts_name: str | None = None
) -> str | None:
    """The provider voice ``mall["voices"][voice_id]`` names, or ``None``.

    ``None`` means "hand the provider ``voice_id`` itself" — a voice that is not
    in the store, a document without ``voice_id``, or one whose ``voice_id`` is
    its own key (which changes nothing, so it must not move a cache key).
    Given ``tts_name``, a document written for ANOTHER provider gives
    :data:`DEFAULT_VOICE` — never a foreign voice id (an#209).
    """
    doc = voice_document(mall, voice_id)
    if not doc:
        return None
    named = doc.get(PROVIDER_VOICE_KEY)
    if not isinstance(named, str) or not named or named == voice_id:
        return None
    if not voice_applies(doc, tts_name):
        return DEFAULT_VOICE
    return named
