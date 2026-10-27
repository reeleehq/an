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
    "TranscriptCatalogUnreadable",
    "TranscriptLinkError",
    "in_memory_transcripts_store",
    "is_artifact_ref",
    "linked_transcript",
    "orphan_transcript_blobs",
    "parse_artifact_ref",
    "pin_of",
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
#: A recorded reference's content pin: ``<key>@<sha256>``.
_PINNED = re.compile(r"(?P<key>.+)@(?P<pin>[0-9a-f]{64})")
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
    if _PINNED.fullmatch(key):
        raise TranscriptLinkError(
            f"transcript key {key!r} ends in `@<sha256>`, which a reference reads as "
            "a content pin: choose another key"
        )
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


def parse_artifact_ref(
    ref: str, mall: Mapping[str, Any], *, store_name: str = TRANSCRIPTS_STORE
) -> tuple[str, str, str | None]:
    """``(store, key, pin)`` of ``artifact:[<store>/]<key>[@<sha256>]`` (an#607):
    the first segment names a store of ``mall`` when it is one that holds the
    key (else the whole name is a key of ``store_name``, so a transcript keyed
    ``takes/a`` is found though the mall has a ``takes`` store); ``pin`` is the
    content a recorded reference names, ``None`` when it names none.

    >>> mall = {"transcripts": {"takes/a": 1}, "takes": {}}
    >>> parse_artifact_ref("artifact:takes/a", mall)
    ('transcripts', 'takes/a', None)
    >>> parse_artifact_ref("artifact:transcripts/k@" + "0" * 64, mall)[1:]
    ('k', '0000000000000000000000000000000000000000000000000000000000000000')
    """
    name = ref.strip()[len(ARTIFACT_REF_PREFIX) :]
    pinned = _PINNED.fullmatch(name)
    pin = None
    if pinned:
        name, pin = pinned["key"], pinned["pin"]
    head, sep, rest = name.partition("/")
    if (
        sep
        and head in mall
        and (_has(mall[head], rest) or not _has(mall.get(store_name) or {}, name))
    ):
        return head, rest, pin
    return store_name, name, pin


def linked_transcript(
    item: Any, mall: Mapping[str, Any], *, store_name: str = TRANSCRIPTS_STORE
) -> LinkedTranscript:
    """The transcript ``item`` names: ``artifact:[<store>/]<key>[@<sha256>]``
    (:func:`parse_artifact_ref`), or a ``lacing.Artifact`` (filed in
    ``store_name``), read through ``mall``. A pinned reference (what a take's
    provenance records) reads exactly those bytes, even after the key was
    recorded again. Raises :class:`TranscriptLinkError` for a store the mall
    has not, one that is not an artifact store, a key or content it does not
    hold, or a record whose ``mime`` is not a transcript format."""
    pin = None
    if _is_artifact(item):
        artifact, name = item, store_name
    else:
        name, key, pin = parse_artifact_ref(str(item), mall, store_name=store_name)
    if name not in mall:
        raise TranscriptLinkError(
            f"{item!r}: the project has no {name!r} store (its stores: {sorted(mall)})"
        )
    store = mall[name]
    if pin is not None:  # the bytes it pinned, whatever the key names now
        return _pinned(store, f"{name}/{key}@{pin}", pin)
    if _is_artifact(item):
        key = next((k for k in store if _holds(store, k, item.asset_id)), None)
        if key is None:
            raise TranscriptLinkError(
                f"no record in the {name!r} store holds transcript {item.asset_id}"
            )
    else:
        artifact = _record(store, key, item=item, name=name)
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


def _record(store: Any, key: str, *, item: Any, name: str) -> Any:
    """The artifact record at ``key``, or a :class:`TranscriptLinkError` naming why not."""
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
    return artifact


def _pinned(store: Any, ref: str, pin: str) -> LinkedTranscript:
    """The transcript ``pin`` names: its bytes, read even when its key now names
    other content or is gone; its format from a record that still holds those
    bytes, else read from them (a plain transcript that looks like another
    format is then read as that one)."""
    from an.audio.transcripts import detect_format

    data = store.get_blob(pin)
    if data is None:
        raise TranscriptLinkError(
            f"{ref}: the content pinned is no longer kept (`an cache gc` collects "
            "what nothing names)"
        )
    text = data.decode("utf-8-sig")
    mime = next(
        (store[k].mime for k in list(store) if _holds(store, k, pin)),
        None,
    )
    fmt = next((f for f, m in FORMAT_MIME.items() if m == mime), None)
    return LinkedTranscript(text, fmt or detect_format(text), ref)


def _has(store: Any, key: str) -> bool:
    try:
        return key in store
    except Exception:  # noqa: BLE001 — a store that cannot say does not hold it
        return False


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


def pin_of(reference: str) -> str | None:
    """The content digest a recorded reference pins (``<store>/<key>@<sha256>``).

    >>> pin_of("transcripts/k@" + "a" * 64) == "a" * 64, pin_of("transcripts/k")
    (True, None)
    """
    pinned = _PINNED.fullmatch(str(reference or ""))
    return pinned["pin"] if pinned else None


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
