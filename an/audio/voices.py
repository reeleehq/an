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
handed that, and otherwise the store key itself. Nothing declared anywhere
resolves every line to ``"default"`` handed to the provider as ``"default"`` —
exactly what the pipeline did before this module, so no cache key moves.

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
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The voice a line gets when neither it nor its speaker names one.
DEFAULT_VOICE: str = "default"
#: The key, in a voice document, naming the TTS provider's own voice.
PROVIDER_VOICE_KEY: str = "voice_id"
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


def provider_voice(mall: Mapping | None, voice_id: str) -> str | None:
    """The provider voice ``mall["voices"][voice_id]`` names, or ``None``.

    ``None`` means "hand the provider ``voice_id`` itself" — a voice that is not
    in the store, a document without ``voice_id``, or one whose ``voice_id`` is
    its own key (which changes nothing, so it must not move a cache key).
    """
    voices = mall.get("voices") if mall is not None else None
    if voices is None or voice_id not in voices:
        return None
    doc = voices[voice_id]
    named = doc.get(PROVIDER_VOICE_KEY) if isinstance(doc, Mapping) else None
    if not isinstance(named, str) or not named or named == voice_id:
        return None
    return named
