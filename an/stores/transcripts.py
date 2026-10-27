"""Transcripts as linked artifacts in the project store (an#493).

A transcript an earlier step produced (a speech-to-text pass, a script
export, a hand-timed SRT) is kept in the mall's ``transcripts`` store, a
``lacing.ArtifactStore`` (``catalog/<key>.json`` + ``blobs/<sha256>``, the
layout of the shot cache), so a later step can name it instead of a file:
``an voices import <dir> takes/ --transcript artifact:transcripts/<key>``
(:func:`an.audio.recorded.import_recordings`), and the take's provenance
points at the artifact it was cut by. The transcript's format rides in the
record's ``mime`` (:data:`FORMAT_MIME`).

>>> store = in_memory_transcripts_store()
>>> art = record_transcript(store, "take1", "1\\n00:00:00,000 --> 00:00:01,000\\nHello.\\n")
>>> art.mime, art.kind
('application/x-subrip', 'text')
>>> linked = linked_transcript("artifact:transcripts/take1", {"transcripts": store})
>>> linked.fmt, linked.ref, linked.text.splitlines()[2]
('srt', 'transcripts/take1', 'Hello.')
"""

from __future__ import annotations

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
#: ``artifact:<store>/<key>`` (the store defaults to :data:`TRANSCRIPTS_STORE`).
ARTIFACT_REF_PREFIX: str = "artifact:"
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


class TranscriptLinkError(ValueError):
    """A transcript artifact that cannot be found or read."""


@dataclass(frozen=True)
class LinkedTranscript:
    """A transcript read out of the store: its text, its format, and the
    reference that names it (``<store>/<key>``), for provenance."""

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
    text: str,
    *,
    fmt: str | None = None,
    generated_by: str = DFLT_GENERATED_BY,
    attributed_to: str = DFLT_ATTRIBUTED_TO,
    derived_from: Iterable[str] = (),
) -> Any:
    """Keep ``text`` (a transcript, its format detected unless ``fmt`` says)
    in ``store`` under ``key``; return its ``lacing.Artifact``. ``generated_by``
    and ``attributed_to`` are its provenance (``processor:<name>``, who ran
    it), ``derived_from`` the sha256 of what it was made from (a recording)."""
    from lacing import Artifact, Provenance, RationalTime

    from an.audio.transcripts import FORMATS, detect_format

    fmt = (fmt or detect_format(text)).lower()
    if fmt not in FORMAT_MIME:
        raise TranscriptLinkError(
            f"transcript format {fmt!r} is not one of {sorted(FORMAT_MIME)} ({FORMATS})"
        )
    data = text.encode("utf-8")
    artifact = Artifact(
        asset_id=store.put_blob(data),
        kind="json" if fmt == "json" else "text",
        mime=FORMAT_MIME[fmt],
        bytes_size=len(data),
        provenance=Provenance(
            was_generated_by=generated_by,
            was_attributed_to=attributed_to,
            was_derived_from=sorted(set(derived_from)),
            generated_at_time=RationalTime.now(),
        ),
    )
    store[key] = artifact
    return artifact


def is_artifact_ref(item: Any) -> bool:
    """Whether ``item`` names a transcript artifact: an ``artifact:`` reference
    or a ``lacing.Artifact``.

    >>> is_artifact_ref("artifact:transcripts/t"), is_artifact_ref("take.srt")
    (True, False)
    """
    if isinstance(item, str):
        return item.startswith(ARTIFACT_REF_PREFIX)
    return _is_artifact(item)


def linked_transcript(
    item: Any, mall: Mapping[str, Any], *, store: str = TRANSCRIPTS_STORE
) -> LinkedTranscript:
    """The transcript ``item`` names: ``artifact:<store>/<key>`` (``<key>``
    alone is in ``store``), or a ``lacing.Artifact`` (its blob, in ``store``),
    read through ``mall``. Raises :class:`TranscriptLinkError` for a store
    the mall has not, a key or blob it does not hold, or a record whose
    ``mime`` is not a transcript format."""
    if _is_artifact(item):
        artifact, ref = item, f"{store}/{item.asset_id}"
    else:
        name = str(item)[len(ARTIFACT_REF_PREFIX) :]
        store, _, key = name.rpartition("/") if "/" in name else (store, "", name)
        ref = f"{store}/{key}"
    if store not in mall:
        raise TranscriptLinkError(
            f"{item!r}: the project has no {store!r} store (its stores: {sorted(mall)})"
        )
    if not _is_artifact(item):
        try:
            artifact = mall[store][key]
        except KeyError:
            raise TranscriptLinkError(
                f"{item!r}: no transcript {key!r} in the {store!r} store"
            ) from None
    fmt = next((f for f, m in FORMAT_MIME.items() if m == artifact.mime), None)
    if fmt is None:
        raise TranscriptLinkError(
            f"{ref}: its media type {artifact.mime!r} is not a transcript's "
            f"({sorted(FORMAT_MIME.values())})"
        )
    data = mall[store].get_blob(artifact.asset_id)
    if data is None:
        raise TranscriptLinkError(f"{ref}: its content {artifact.asset_id} is missing")
    return LinkedTranscript(data.decode("utf-8-sig"), fmt, ref)


def _is_artifact(item: Any) -> bool:
    try:
        from lacing import Artifact
    except ImportError:  # pragma: no cover — lacing is a dependency
        return False
    return isinstance(item, Artifact)
