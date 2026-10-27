"""Transcripts as linked artifacts in the project store (an#493).

A transcript an earlier step produced (a speech-to-text pass, a script
export, a hand-timed SRT) is kept in the mall's ``transcripts`` store, a
``lacing.ArtifactStore`` (``catalog/<key>.json`` + ``blobs/<sha256>``, the
layout of the shot cache), so a later step can name it instead of a file:
``an voices import <dir> takes/ --transcript artifact:transcripts/<key>``
(:func:`an.audio.recorded.import_recordings`), and the take's provenance
points at the artifact it was cut by, content included
(``transcripts/<key>@<sha256>``: a key re-recorded later names other bytes).
The transcript's format rides in the record's ``mime`` (:data:`FORMAT_MIME`).
A transcript is a document the takes are cut BY, before any take exists and
often covering several, so it is its own store rather than a sidecar of a
recording.

A reference is ``artifact:[<store>/]<key>[@<sha256>]``, the store
:data:`TRANSCRIPTS_STORE` when it names none: ``lacing.ArtifactRef`` parses and
formats it and ``lacing.resolve_in_mall`` reads what it names (an#670), so the
spelling is lacing's, shared with reelee; this module only turns their
refusals into the :class:`TranscriptLinkError` that says which part is missing.

>>> store = in_memory_transcripts_store()
>>> art = record_transcript(store, "take1", "1\\n00:00:00,000 --> 00:00:01,000\\nHello.\\n")
>>> art.mime, art.kind
('application/x-subrip', 'text')
>>> linked = linked_transcript("artifact:transcripts/take1", {"transcripts": store})
>>> linked.fmt, linked.ref == f"transcripts/take1@{art.asset_id}", linked.text.splitlines()[2]
('srt', True, 'Hello.')
"""

from __future__ import annotations

import re

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "FORMAT_MIME",
    "LinkedTranscript",
    "TRANSCRIPTS_STORE",
    "TranscriptCatalogUnreadable",
    "TranscriptLinkError",
    "in_memory_transcripts_store",
    "is_artifact_ref",
    "linked_transcript",
    "orphan_transcript_blobs",
    "pin_of",
    "record_transcript",
    "transcripts_store",
]

#: The mall key of the transcripts store.
TRANSCRIPTS_STORE: str = "transcripts"
#: The media type each transcript format is recorded under (and read back from).
FORMAT_MIME: dict[str, str] = {
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
    "textgrid": "text/x-praat-textgrid",
    "json": "application/json",
    "plain": "text/plain",
}
#: Who a record says made it, when the caller does not (lacing's convention).
DFLT_GENERATED_BY: str = "processor:an.stores.transcripts"
DFLT_ATTRIBUTED_TO: str = "an"
_BOM: str = "﻿"


class TranscriptLinkError(ValueError):
    """A transcript artifact that cannot be found or read."""


@dataclass(frozen=True)
class LinkedTranscript:
    """A transcript read out of the store: its text, its format, and the
    reference that names it with its content (``<store>/<key>@<sha256>``)."""

    text: str
    fmt: str
    ref: str


def transcripts_store(root: str | Path) -> Any:
    """A filesystem transcripts store under ``root`` (lacing's layout)."""
    from lacing import ArtifactStore

    return ArtifactStore.from_directory(root)


def in_memory_transcripts_store() -> Any:
    """A transcripts store held in dicts: for tests, and a mall with no disk."""
    from lacing import ArtifactStore

    return ArtifactStore.in_memory()


def record_transcript(
    store: Any,
    key: str,
    text: str | Path,
    *,
    fmt: str | None = None,
    generated_by: str = DFLT_GENERATED_BY,
    attributed_to: str = DFLT_ATTRIBUTED_TO,
    derived_from: Iterable[str] = (),
) -> Any:
    """Keep ``text`` (a transcript, or a ``Path`` to one; its format detected,
    a file's suffix first, unless ``fmt`` says) in ``store`` under ``key``;
    return its ``lacing.Artifact``. ``generated_by`` and ``attributed_to`` are
    its provenance (``processor:<name>``, who ran it), ``derived_from`` the
    sha256 of what it was made from (a recording)."""
    from lacing import Artifact

    from an.audio.transcripts import detect_format

    suffix = ""
    if isinstance(text, Path):
        suffix, text = text.suffix, text.read_text(encoding="utf-8-sig")
    text = text.removeprefix(_BOM)
    _check_key(key)
    fmt = (fmt or detect_format(text, suffix=suffix)).lower()
    if fmt not in FORMAT_MIME:
        raise TranscriptLinkError(
            f"transcript format {fmt!r} is not one of {sorted(FORMAT_MIME)}"
        )
    data = text.encode("utf-8")
    artifact = Artifact.from_bytes(
        data,
        kind="json" if fmt == "json" else "text",
        mime=FORMAT_MIME[fmt],
        was_generated_by=generated_by,
        was_attributed_to=attributed_to,
        was_derived_from=tuple(sorted(set(derived_from))),
    )
    store.save(key, artifact, data=data)
    return artifact


def is_artifact_ref(item: Any) -> bool:
    """Whether ``item`` names a transcript artifact: an ``artifact:`` reference
    (``lacing.ArtifactRef`` reads it) or a ``lacing.Artifact``.

    >>> is_artifact_ref("artifact:transcripts/t"), is_artifact_ref("take.srt")
    (True, False)
    >>> is_artifact_ref("artifact: Hello there.")   # a plain transcript's speaker
    False
    """
    if isinstance(item, str):
        from lacing.artifact_ref import is_artifact_ref as _is_ref

        return _is_ref(item)
    return _is_artifact(item)


def linked_transcript(
    item: Any, mall: Mapping[str, Any], *, store_name: str = TRANSCRIPTS_STORE
) -> LinkedTranscript:
    """The transcript ``item`` names: ``artifact:[<store>/]<key>[@<sha256>]``
    (``lacing.ArtifactRef``: the first segment names a store of ``mall`` that
    holds the rest, else the whole name is a key of ``store_name``), or a
    ``lacing.Artifact`` (filed in ``store_name``), read through ``mall``. A
    pinned reference (what a take's provenance records) reads exactly those
    bytes, even after the key was recorded again or removed. Raises
    :class:`TranscriptLinkError` for text that is not a reference, a store the
    mall has not, one that is not an artifact store, a key or content it does
    not hold, bytes that do not match their pin, or a record whose ``mime`` is
    not a transcript format.

    >>> mall = {"transcripts": in_memory_transcripts_store()}
    >>> linked_transcript("artifact:transcripts/nope", mall)
    Traceback (most recent call last):
    ...
    an.stores.transcripts.TranscriptLinkError: 'artifact:transcripts/nope': no transcript 'nope' in the 'transcripts' store
    """
    from lacing import ArtifactRef, resolve_in_mall

    if _is_artifact(item):
        # An artifact names its content, not a key: pinned under a key no record
        # need have, the store looks up the record that holds those bytes.
        ref = ArtifactRef(item.asset_id, store=store_name, pin=item.asset_id)
    else:
        try:
            ref = ArtifactRef.parse(str(item))
        except ValueError as e:
            raise TranscriptLinkError(f"{item!r}: {e}") from None
    ref = ref.locate(mall, default_store=store_name)
    name, key, pin = ref.store, ref.key, ref.pin
    unheld = f"no record in the {name!r} store holds transcript {pin}"
    try:
        found = resolve_in_mall(ref, mall, default_store=store_name)
    except KeyError:  # before LookupError: a missing key is one
        problem = unheld if _is_artifact(item) else _missing(item, mall[name], ref)
        raise TranscriptLinkError(problem) from None
    except LookupError:
        raise TranscriptLinkError(
            f"{item!r}: the project has no {name!r} store (its stores: {sorted(mall)})"
        ) from None
    except TypeError:  # a store with no `resolve`: not an artifact store
        raise TranscriptLinkError(
            f"{item!r}: the {name!r} store ({type(mall[name]).__name__}) keeps other "
            "things, not transcript artifacts"
        ) from None
    except ValueError as e:  # a damaged record (unpinned), or bytes off their pin
        problem = (
            f"the record {key!r} in the {name!r} store is damaged: {e}"
            if pin is None
            else f"the content in the {name!r} store does not match its pin"
        )
        raise TranscriptLinkError(f"{item!r}: {problem}") from None
    if _is_artifact(item) and found.key is None:
        raise TranscriptLinkError(unheld)
    if found.record is not None and not _is_artifact(found.record):
        raise TranscriptLinkError(
            f"{item!r}: the {name!r} store keeps {type(found.record).__name__}s, "
            "not transcript artifacts"
        )
    # A reference read back keeps its own key; one read now names what it found.
    named = key if pin is not None and not _is_artifact(item) else found.key
    try:
        reference = _recorded(ArtifactRef(named, store=name, pin=found.content_hash))
    except ValueError:  # a key an older an recorded, which lacing now refuses
        reference = f"{name}/{named}@{found.content_hash}"
    text = found.data.decode("utf-8-sig")
    mime = getattr(found.record, "mime", None)
    fmt = next((f for f, m in FORMAT_MIME.items() if m == mime), None)
    if fmt is None and (pin is None or _is_artifact(item)):
        raise TranscriptLinkError(
            f"{reference}: its media type {mime!r} is not a transcript's "
            f"({sorted(FORMAT_MIME.values())})"
        )
    if fmt is None:  # pinned bytes no record names any more: read from them
        from an.audio.transcripts import detect_format

        fmt = detect_format(text)
    return LinkedTranscript(text, fmt, reference)


def _missing(item: Any, store: Any, ref: Any) -> str:
    """Why ``store`` (the one ``ref`` is located in) gave nothing for ``item``:
    no such key, no bytes for its record, or no bytes for its pin."""
    if ref.pin is not None:
        return (
            f"{_recorded(ref)}: the content pinned is no longer kept (`an cache gc` "
            "collects what nothing names)"
        )
    if not _holds_key(store, ref.key):
        return f"{item!r}: no transcript {ref.key!r} in the {ref.store!r} store"
    return f"{_recorded(ref)}: its content is missing"


def _recorded(ref: Any) -> str:
    """``ref`` as a take's provenance records it: ``<store>/<key>@<sha256>``,
    without the ``artifact:`` prefix (:func:`pin_of` reads it back)."""
    from lacing import ARTIFACT_REF_PREFIX

    return ref.format().removeprefix(ARTIFACT_REF_PREFIX)


def _holds_key(store: Any, key: str) -> bool:
    try:
        return key in store
    except Exception:  # noqa: BLE001 — a store that cannot say does not hold it
        return False


def _check_key(key: str) -> None:
    """Refuse a key no reference could name (``lacing.ArtifactRef``'s rule: an
    empty key, one with whitespace or a leading ``/``, or one ending in
    ``@<sha256>``, which a reference reads as a content pin)."""
    from lacing import ArtifactRef

    try:
        ArtifactRef(key)
    except ValueError as e:
        raise TranscriptLinkError(f"{e}: choose another transcript key") from None


class TranscriptCatalogUnreadable(TranscriptLinkError):
    """A transcripts catalog record cannot be read: what it names is unknown,
    so nothing can be said to be named by nothing (an#607)."""


def orphan_transcript_blobs(store: Any, *, named: Iterable[str] = ()) -> list[str]:
    """The transcript contents of ``store`` that no catalog record and nothing
    in ``named`` (the pins a take's provenance records, an#607) names: what
    re-recording a key left behind. Raises :class:`TranscriptCatalogUnreadable`
    when a record cannot be read, since its blob might be the one it names.

    >>> store = in_memory_transcripts_store()
    >>> first = record_transcript(store, "k", "carl: Hello.")
    >>> _ = record_transcript(store, "k", "carl: Hello there.")
    >>> orphan_transcript_blobs(store) == [first.asset_id]
    True
    >>> orphan_transcript_blobs(store, named=[first.asset_id])
    []
    """
    kept = set(named)
    for key in list(store):
        try:
            kept.add(store[key].asset_id)
        except Exception as e:  # noqa: BLE001 — unknown is not "names nothing"
            raise TranscriptCatalogUnreadable(
                f"the transcripts record {key!r} cannot be read ({type(e).__name__}): "
                "no transcript content is collected until it is repaired or removed"
            ) from None
    return sorted(h for h in store.iter_blobs() if h not in kept)


#: A recorded reference as an wrote it before lacing read them
#: (``<store>/<key>@<sha256>``, any key): :func:`pin_of`'s fallback.
_LEGACY_PINNED = re.compile(r".+@([0-9a-fA-F]{64})")


def pin_of(reference: str) -> str | None:
    """The content digest a recorded reference pins (``<store>/<key>@<sha256>``,
    read by ``lacing.ArtifactRef`` with or without its ``artifact:`` prefix);
    ``None`` when it pins none or is not a reference.

    >>> pin_of("transcripts/k@" + "a" * 64) == "a" * 64, pin_of("transcripts/k")
    (True, None)
    >>> pin_of("transcripts/my take@" + "A" * 64) == "a" * 64  # an older an's key
    True
    """
    from lacing import ArtifactRef

    text = str(reference or "")
    try:
        return ArtifactRef.parse(text, require_prefix=False).pin
    except ValueError:
        # What an older an recorded under a key lacing now refuses (a space in
        # it): still a pin, or `an cache gc` would collect what it names.
        legacy = _LEGACY_PINNED.fullmatch(text)
        return legacy.group(1).lower() if legacy else None


def _is_artifact(item: Any) -> bool:
    from lacing import Artifact

    return isinstance(item, Artifact)
