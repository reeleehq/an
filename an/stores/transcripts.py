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
    "ARTIFACT_REF_PREFIX",
    "FORMAT_MIME",
    "LinkedTranscript",
    "TRANSCRIPTS_STORE",
    "TranscriptLinkError",
    "in_memory_transcripts_store",
    "is_artifact_ref",
    "linked_transcript",
    "record_transcript",
    "transcripts_store",
]

#: The mall key of the transcripts store.
TRANSCRIPTS_STORE: str = "transcripts"
#: How a transcript artifact is named where a path is expected:
#: ``artifact:<store>/<key>``, or ``artifact:<key>`` in :data:`TRANSCRIPTS_STORE`
#: (reelee's ``artifact:<id>`` spelling, with the store an#493 adds in front).
ARTIFACT_REF_PREFIX: str = "artifact:"
#: A reference: the prefix and a name with no whitespace (so a plain
#: ``artifact: some words`` transcript line is not taken for one).
_REF = re.compile(re.escape(ARTIFACT_REF_PREFIX) + r"[^\s/][^\s]*")
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
    or a ``lacing.Artifact``.

    >>> is_artifact_ref("artifact:transcripts/t"), is_artifact_ref("take.srt")
    (True, False)
    >>> is_artifact_ref("artifact: Hello there.")   # a plain transcript's speaker
    False
    """
    if isinstance(item, str):
        return _REF.fullmatch(item.strip()) is not None
    return _is_artifact(item)


def linked_transcript(
    item: Any, mall: Mapping[str, Any], *, store_name: str = TRANSCRIPTS_STORE
) -> LinkedTranscript:
    """The transcript ``item`` names: ``artifact:<store>/<key>`` (``<key>``
    alone is in ``store_name``; a key may itself hold slashes), or a
    ``lacing.Artifact`` (filed in ``store_name``), read through ``mall``.
    Raises :class:`TranscriptLinkError` for a store the mall has not, one
    that is not an artifact store, a key or content it does not hold, or a
    record whose ``mime`` is not a transcript format."""
    if _is_artifact(item):
        artifact, name = item, store_name
    else:
        name = str(item).strip()[len(ARTIFACT_REF_PREFIX) :]
        head, sep, rest = name.partition("/")
        name, key = (head, rest) if sep and head in mall else (store_name, name)
    if name not in mall:
        raise TranscriptLinkError(
            f"{item!r}: the project has no {name!r} store (its stores: {sorted(mall)})"
        )
    store = mall[name]
    if _is_artifact(item):
        key = next((k for k in store if _holds(store, k, item.asset_id)), None)
        if key is None:
            raise TranscriptLinkError(
                f"no record in the {name!r} store holds transcript {item.asset_id}"
            )
    else:
        try:
            artifact = store[key]
        except KeyError:
            raise TranscriptLinkError(
                f"{item!r}: no transcript {key!r} in the {name!r} store"
            ) from None
        except ValueError as e:  # a record that does not validate (pydantic)
            raise TranscriptLinkError(
                f"{item!r}: the record {key!r} in the {name!r} store is damaged: {e}"
            ) from None
    if not _is_artifact(artifact):
        raise TranscriptLinkError(
            f"{item!r}: the {name!r} store keeps {type(artifact).__name__}s, not "
            "transcript artifacts"
        )
    ref = f"{name}/{key}@{artifact.asset_id}"
    fmt = next((f for f, m in FORMAT_MIME.items() if m == artifact.mime), None)
    if fmt is None:
        raise TranscriptLinkError(
            f"{ref}: its media type {artifact.mime!r} is not a transcript's "
            f"({sorted(FORMAT_MIME.values())})"
        )
    data = store.get_blob(artifact.asset_id)
    if data is None:
        raise TranscriptLinkError(f"{ref}: its content is missing")
    return LinkedTranscript(data.decode("utf-8-sig"), fmt, ref)


def _holds(store: Any, key: str, asset_id: str) -> bool:
    """Whether the record at ``key`` is the artifact ``asset_id`` (a damaged
    record is not: it does not stop the search)."""
    try:
        return getattr(store[key], "asset_id", None) == asset_id
    except (KeyError, ValueError):
        return False


def _is_artifact(item: Any) -> bool:
    from lacing import Artifact

    return isinstance(item, Artifact)
