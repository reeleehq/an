"""The library's verbs: ``publish``, ``find``, ``vocabulary``, ``show``, ``promote``, ``retire``.

Plain functions over :class:`~an.library.federation.Library` objects (pillar 8:
the functions are the API; the ``an library …`` CLI and, later, MCP are thin
projections of them). Writes take the one owning library; reads take a library
or a search path (:func:`~an.library.federation.search_path`). Check-out lives
in :mod:`an.library.checkout`.

The documents they write (ADR 0005 decision 4, design §4):

- a **record** per asset — identity and curation, mutable: ``id``, ``kind``,
  ``title``, ``family``, ``head``, ``status`` (``retired`` hides it from
  ``find``: :func:`retire`), its append-only ``status_history``, ``facets``
  (``style``, ``origin``), ``tags``;
- a **label** per relabel of a version's unchanged content (an#307) —
  append-only, keyed by the hash of what it says: the source, who and why,
  and the rights it gave the version; a version's rights read its labels;
- a **version** per publish — immutable: the descriptor ``doc`` verbatim, its
  ``files`` as ``dol.content.ContentRef`` s, the asset-level ``source``,
  ``derived_from``, the derived ``affordances`` with the ``analysers`` that made
  them, the rolled-up ``rights``, the ``art`` facet, and ``manifest_sha256`` —
  the **version identity**: the hash of ``doc``, the files' hashes, ``source``
  and ``derived_from``. It is not a content key (lineage changes it, and a
  checked-out copy can be edited after it is pinned); nothing should cache on it
  as one. Publishing what the head already is makes no new version.

**Rights are recomputed, not trusted.** The stored ``rights`` block is a cache of
:func:`effective_rights`, which rolls up — most restrictive wins — the asset-level
source, the descriptor's own source, every part's, and recursively every version
the asset derives from. ``promote`` and ``find(rights=…)`` recompute it.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import posixpath
import re
import unicodedata
import warnings

from an.genres import service
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

from dol.content import ContentRef, content_hash

from an.ir.assets import PRIVATE_STUDY, PUBLIC_DOMAIN, AssetSource, license_class
from an.credits import (
    factory_recorded,
    is_factory_stamp,
    is_clutter,
    is_generated_source,
    nobody_labelled,
    referenced_paths,
    same_source,
)
from an.ir.migrate import (
    DocumentKind,
    migrate,
    omit_unset,
    register_kind,
    register_migration,
)
from an.library.affordances import (
    CAPABILITIES,
    KEY_SEP,
    KEYS_PARAM,
    analyse,
    capability_of,
    current_affordances,
    missing,
    remedy_for,
)
from an.library.floor import (
    BlobFloor,
    library_origin,
    machine_libraries,
    record_statement,
    register_library,
    remember,
)
from an.library.federation import (
    AssetNotFoundError,
    Libraries,
    Library,
    as_libraries,
    is_federated,
    open_library,
    resolve,
    versions_of,
)
from an.library.ids import (
    AssetIdError,
    LibraryRef,
    asset_kind,
    check_asset_id,
    parse_ref,
    version_label,
    version_number,
)
from an.library.kinds import ASSET_KINDS, UnknownKindError, asset_kind_info
from an.library.registry import RegistryError, generated_by
from an.library.rights import (
    ASSET_SOURCE_LABEL,
    LICENSE_CLASS_ORDER,
    COMMERCIAL_CLASSES,
    PUBLISHABLE_CLASSES,
    Rights,
    RightsRefusal,
    descriptor_source,
    roll_up,
    sources_in,
)
from an.library.root import CORE_PACKAGE
from an.library.stores import (
    LABEL_KEY_SEP,
    VersionExistsError,
    canonical_json,
    label_key,
    version_key,
)

__all__ = [
    "CheckoutError",
    "FindResult",
    "Hit",
    "IndexEntry",
    "IntegrityError",
    "LIBRARY_ERRORS",
    "LibraryError",
    "LibraryIndexWarning",
    "PlaceholderRigWarning",
    "PublishResult",
    "effective_rights",
    "find",
    "promote",
    "publish",
    "publish_dir",
    "reindex",
    "retire",
    "scan_index",
    "set_status",
    "show",
    "unknown_advice",
    "version_labels",
    "version_sources",
    "vocabulary",
]

#: Schema version of the record and version documents (each its own document kind).
LIBRARY_SCHEMA_VERSION: str = "0.1.0"
RECORD_KIND: DocumentKind = register_kind(
    DocumentKind(
        name="LibraryRecord",
        version_field="schema_version",
        current_version=LIBRARY_SCHEMA_VERSION,
    )
)
VERSION_KIND: DocumentKind = register_kind(
    DocumentKind(
        name="LibraryVersion",
        version_field="schema_version",
        current_version="0.2.0",
    )
)


@register_migration(VERSION_KIND.name, LIBRARY_SCHEMA_VERSION, "0.2.0")
def _version_0_1_to_0_2(doc: dict[str, Any]) -> dict[str, Any]:
    """0.2.0 adds the optional ``file_sources`` (an#345): nothing to rewrite.

    A version is WRITTEN at 0.2.0 only when it carries ``file_sources``, so an
    older reader (which knows no path from 0.2.0) refuses it rather than
    reading its per-file statements as the asset-level label alone.
    """
    return {**doc, "schema_version": "0.2.0"}


LABEL_KIND: DocumentKind = register_kind(
    DocumentKind(
        name="LibraryLabel",
        version_field="schema_version",
        current_version=LIBRARY_SCHEMA_VERSION,
    )
)
#: Curation status vocabulary (design §5); a status is curation, so it lives on the record.
#: ``retired``: a dead id (an#307) — hidden from ``find``, never deleted.
STATUSES: tuple[str, ...] = ("draft", "approved", "deprecated", "retired")
DFLT_STATUS: str = "draft"
#: Statuses ``find`` and ``vocabulary`` leave out unless asked for by name:
#: their versions stay readable (projects pin them), they are just not offered.
HIDDEN_STATUSES: frozenset[str] = frozenset({"retired"})
#: The record field logging every status change: ``[{status, by, reason, at}]``,
#: appended to, never rewritten.
STATUS_HISTORY_FIELD: str = "status_history"
#: The ``rights=`` filter values besides a licence class.
RIGHTS_ANY: str = "any"
RIGHTS_PUBLISHABLE: str = "publishable"
#: ``find(rights=…)``: what a COMMERCIAL video may use (an#373: not ``noncommercial``).
RIGHTS_COMMERCIAL: str = "commercial"
#: File extensions by art type, for the derived ``art`` facet.
VECTOR_EXTS: frozenset[str] = frozenset({".svg"})
RASTER_EXTS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
#: The descriptor ``metadata`` key a check-out records its origin under.
ORIGIN_KEY: str = "library_origin"
#: Set in the origin block when check-out had to create ``metadata`` to hold it,
#: so a re-publish removes it again and the content reads back unchanged.
METADATA_ADDED_FLAG: str = "metadata_added"
#: The origin-block entry holding the asset-level source check-out wrote into a
#: descriptor that had none, so a re-publish removes exactly that again.
SOURCE_ADDED_KEY: str = "source_added"
#: The version field recording an explicit relicence: ``{"by": who, "reason": why}``.
#: The only way a version's rights can be LESS restrictive than what it inherits.
RELICENSE_FIELD: str = "relicense"
#: The version field naming the head this version follows (``<lib>:<id>@vNNN``):
#: a new version inherits the old one's rights, so it cannot relabel them.
PREVIOUS_FIELD: str = "previous"
#: The version field listing the files a CARRIED asset-level source does not
#: speak for: changed or added since the version the source was declared on
#: (S1 of review-259). Each is ``unknown`` — on this version and, through
#: ``previous``, on every later one — until a publish labels it: an explicit
#: ``source=`` with a recorded ``relabel`` (:data:`RELABEL_FIELD`), or a relicence.
UNLABELLED_FIELD: str = "unlabelled"
#: The version field recording an explicit LABEL of bytes nobody labelled:
#: ``{"by": who, "reason": why}``, beside an explicit ``source`` (an#263). It
#: answers the GAPS of the asset's own version chain — a file an earlier version
#: recorded as ``unlabelled``, a file no person's source spoke for (a
#: placeholder of the credits walk: :func:`an.credits.nobody_labelled`), an
#: earlier version that recorded no source at all, another asset's SILENCE
#: about a file the chain once held and the labelling version no longer holds
#: (an#307) — with that source. It is a first statement, not a relaxation: it
#: answers nothing anyone stated (a private or any other licence, a per-part
#: source, a version it derives from, another asset's statement about bytes
#: the labelling version holds). Also the field of a label recorded on an
#: existing version (:func:`version_labels`).
RELABEL_FIELD: str = "relabel"
#: The version field pinning its lineage: ``{parent_ref: manifest_sha256}`` for
#: ``previous`` and every ``derived_from`` parent, as resolved at publish
#: (review-269 B1). A walk reads a parent only if it is still THAT version;
#: references alone are re-resolved by name, and a same-named library's other
#: ``x@v001`` would stand in for it.
LINEAGE_FIELD: str = "lineage"
#: The version field holding per-file statements (an#345): ``{path: source}``,
#: each source pinned to the digest of the file it was given for. Any file of
#: the version can carry one, attachment or not. A version carrying the field
#: (and every version whose lineage does) is stated under the never-relax rule
#: (:class:`_PerFileRule`): a per-file statement can only ever be stricter than
#: what the bytes already carry, unless a recorded relicence names those bytes.
FILE_SOURCES_FIELD: str = "file_sources"
#: How a per-file statement is labelled among a version's contributors (and in
#: a check-out's origin block, where no descriptor label can shadow it).
FILE_SOURCE_PREFIX: str = "file:"
#: The relicence entry listing the digests a relicence speaks for, recorded on
#: a version carrying ``file_sources``: a per-file statement stricter than the
#: relicence is not covered, and keeps binding.
RELICENSE_COVERS: str = "covers"
#: The version-document schema a version carrying ``file_sources`` is written
#: at, so an older ``an`` refuses to read it instead of reading it looser.
PER_FILE_SCHEMA_VERSION: str = "0.2.0"
#: How many labels a publish tries when another publisher takes the one it chose.
MAX_PUBLISH_ATTEMPTS: int = 8
#: How many close capability names a typo's error suggests.
CLOSE_MATCHES: int = 3


class LibraryError(Exception):
    """A library operation refused, with a sentence saying why and what to do."""


class CheckoutError(LibraryError):
    """A version cannot be materialised into this project as asked."""


class IntegrityError(LibraryError):
    """Stored bytes, paths or a stored manifest do not match what was recorded."""


class PlaceholderRigWarning(UserWarning):
    """A character published with no rig: the compiler would draw only its placeholder."""


class LibraryIndexWarning(UserWarning):
    """A record or version could not be read; the index skipped it."""


class RightsConflictWarning(UserWarning):
    """A statement about some bytes is freer than one that already binds them (an#357).

    Inform, don't block: the freer statement is kept, the stricter one binds,
    and the conflict is recorded beside the statement. A publish refuses one
    only under ``strict_assets``; a relicence resolves it deliberately.
    """


@dataclass(frozen=True)
class RightsConflict:
    """A statement a version makes about a file, freer than what binds those bytes (an#357).

    ``claimed`` is the version's own statement (a per-part ``source``, a
    per-file ``file_sources`` entry, or a relicence that does not cover these
    bytes); ``binding`` is the stricter statement that wins: the same bytes at
    another path, the other statement of this version, or what its lineage
    said. Both are kept; the effective label is ``binding_class``.

    >>> c = RightsConflict("parts/a.png", "ab" * 32, "free", "parts/a.png itemised as cc0-1.0",
    ...                    "private", "cutan:prop.a@v001: the asset's own label")
    >>> print(c)
    parts/a.png: parts/a.png itemised as cc0-1.0 (free) is freer than cutan:prop.a@v001: the asset's own label (private); private binds
    """

    path: str
    digest: str
    claimed_class: str
    claimed: str
    binding_class: str
    binding: str

    def __str__(self) -> str:
        return (
            f"{self.path}: {self.claimed} ({self.claimed_class}) is freer than "
            f"{self.binding} ({self.binding_class}); {self.binding_class} binds"
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "sha256": self.digest,
            "claimed_class": self.claimed_class,
            "claimed": self.claimed,
            "binding_class": self.binding_class,
            "binding": self.binding,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RightsConflict":
        return cls(
            str(raw.get("path", "?")),
            str(raw.get("sha256", "")),
            str(raw.get("claimed_class", "unknown")),
            str(raw.get("claimed", "?")),
            str(raw.get("binding_class", "unknown")),
            str(raw.get("binding", "?")),
        )


#: The key a floor statement, a check-out's origin block and a credits record
#: hold rights conflicts under (an#357). Persisted: do not rename.
CONFLICTS_KEY: str = "conflicts"


#: Every error a library verb raises for a caller's mistake (not a bug): the CLI
#: prints these as a sentence and exits non-zero.
LIBRARY_ERRORS: tuple[type[BaseException], ...] = (
    LibraryError,
    AssetIdError,
    AssetNotFoundError,
    VersionExistsError,
    RightsRefusal,
    UnknownKindError,
    RegistryError,
)

#: ``publish(expect_head=…)`` default: no expectation about the head.
_ANY_HEAD: Any = object()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_list(value: str | Iterable[str] | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value] if value else None
    out = [v for v in value if v]
    return out or None


def _doc_dict(doc: Any) -> dict[str, Any]:
    """A descriptor as a plain JSON document.

    A model is dumped with only the fields its author set (plus its identity
    fields), so a later additive field with a default does not turn an
    unchanged asset into a "changed" version.
    """
    if hasattr(doc, "model_dump_json"):
        return omit_unset(doc, json.loads(doc.model_dump_json()))
    if not isinstance(doc, Mapping):
        raise TypeError(
            f"a descriptor must be a mapping or a pydantic model, got {type(doc).__name__}"
        )
    return json.loads(json.dumps(doc))


def _source_dict(
    source: AssetSource | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if source is None:
        return None
    model = (
        source
        if isinstance(source, AssetSource)
        else AssetSource.model_validate(dict(source))
    )
    return json.loads(model.model_dump_json(exclude_defaults=True))


def _source_model(raw: Mapping[str, Any] | None) -> AssetSource | None:
    return AssetSource.model_validate(dict(raw)) if raw else None


#: Names Windows refuses as a file (any extension), compared case-insensitively.
_WINDOWS_RESERVED: frozenset[str] = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def check_relpath(path: str) -> str:
    """``path`` if it is a clean relative POSIX path inside an asset, else ``LibraryError``.

    Clean means: no ``..``, ``.`` or empty segment, no leading ``/``, no
    backslash, no drive, no control character (NUL included), and no segment
    Windows cannot hold (a reserved name such as ``con``, or a trailing dot or
    space). Check-out runs the same test on paths read back from a library,
    which may not be one this machine wrote.

    >>> check_relpath("parts/head.svg")
    'parts/head.svg'
    >>> check_relpath("parts/../../escape")  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    LibraryError: ...
    """
    parts = path.split("/") if isinstance(path, str) and path else [""]
    if (
        "\\" in path
        or ":" in path
        or path.startswith("/")
        or any(ord(c) < 32 or c == "\x7f" for c in path)
        or any(
            p in ("", ".", "..")
            or p.endswith((".", " "))
            or p.split(".", 1)[0].lower() in _WINDOWS_RESERVED
            for p in parts
        )
    ):
        raise LibraryError(
            f"file path {path!r} must be a clean relative path (no '..', '.', "
            "'\\', drive, leading '/', control character, reserved name, or "
            "trailing dot/space) that stays inside the asset"
        )
    return path


def _path_key(path: str) -> str:
    """How a case- and normalisation-insensitive filesystem (APFS, NTFS) names ``path``."""
    return unicodedata.normalize("NFC", path).casefold()


def check_path_set(paths: Iterable[str]) -> None:
    """Refuse a set of file paths that cannot all exist as distinct files on every disk.

    Two paths that differ only by case or Unicode normalisation (``A.svg`` /
    ``a.svg``, NFC / NFD ``é``) are one file on macOS and Windows, so one would
    silently overwrite the other; a path that is also a folder of another
    (``parts`` and ``parts/x``) cannot be written at all.

    >>> check_path_set(["parts/a.svg", "parts/b.svg"])
    >>> check_path_set(["parts/A.svg", "parts/a.svg"])  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    LibraryError: ...
    """
    seen: dict[str, str] = {}
    folders: dict[str, str] = {}
    for path in sorted(paths):
        key = _path_key(path)
        if key in seen:
            raise LibraryError(
                f"file paths {seen[key]!r} and {path!r} name the same file on a "
                "case- or normalisation-insensitive disk (macOS, Windows); rename one"
            )
        seen[key] = path
        parts = key.split("/")
        for n in range(1, len(parts)):
            folders.setdefault("/".join(parts[:n]), path)
    for key, path in seen.items():
        if key in folders:
            raise LibraryError(
                f"{path!r} is a file, but {folders[key]!r} needs it to be a folder"
            )


def _art_facet(paths: Iterable[str]) -> str:
    exts = {posixpath.splitext(p)[1].lower() for p in paths}
    vector, raster = bool(exts & VECTOR_EXTS), bool(exts & RASTER_EXTS)
    if vector and raster:
        return "mixed"
    return "vector" if vector else "raster" if raster else "none"


def _manifest(
    doc: Any,
    file_hashes: Mapping[str, str],
    source: Any,
    derived_from: Iterable[str],
    *,
    previous: str | None = None,
    relicense: Mapping[str, Any] | None = None,
    relabel: Mapping[str, Any] | None = None,
    unlabelled: Iterable[str] = (),
    lineage: Mapping[str, str] | None = None,
    file_sources: Mapping[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "doc": doc,
        "files": dict(file_hashes),
        "source": source,
        "derived_from": sorted(derived_from),
    }
    if previous:
        payload[PREVIOUS_FIELD] = previous
    if relicense:
        payload[RELICENSE_FIELD] = dict(relicense)
    if relabel:
        payload[RELABEL_FIELD] = dict(relabel)
    if lineage:
        payload[LINEAGE_FIELD] = dict(lineage)
    if unlabelled:
        payload[UNLABELLED_FIELD] = sorted(unlabelled)
    if file_sources is not None:
        # Present (even empty) on every version of a chain that ever carried
        # per-file statements: absent leaves every older manifest unchanged.
        payload[FILE_SOURCES_FIELD] = dict(file_sources)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _file_hashes(files: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    return {path: ContentRef.from_json(ref).item_id for path, ref in files.items()}


def version_manifest(version: Mapping[str, Any]) -> str:
    """Recompute a stored version's ``manifest_sha256`` from what it holds."""
    return _manifest(
        version.get("doc"),
        _file_hashes(version.get("files") or {}),
        version.get("source"),
        version.get("derived_from") or [],
        previous=version.get(PREVIOUS_FIELD),
        relicense=version.get(RELICENSE_FIELD),
        relabel=version.get(RELABEL_FIELD),
        unlabelled=version.get(UNLABELLED_FIELD) or (),
        lineage=version.get(LINEAGE_FIELD),
        file_sources=version.get(FILE_SOURCES_FIELD),
    )


def pop_origin(doc: dict[str, Any]) -> Mapping[str, Any] | None:
    """Remove what a check-out added to ``doc`` (in place), returning its origin block.

    The block is the project's note of where the copy came from, not content:
    left in, an unedited check-out would publish as a "changed" version. Also
    removed: the ``metadata`` dict check-out created to hold it, and the
    asset-level source it wrote into a descriptor that had none — each only if
    still exactly what check-out wrote.
    """
    meta = doc.get("metadata")
    if not isinstance(meta, dict) or ORIGIN_KEY not in meta:
        return None
    origin = meta.pop(ORIGIN_KEY)
    if isinstance(origin, Mapping):
        if origin.get(METADATA_ADDED_FLAG) and not meta:
            del doc["metadata"]
        added = origin.get(SOURCE_ADDED_KEY)
        if isinstance(added, Mapping) and same_source(
            doc.get("source"), added.get("source")
        ):
            if added.get("had_key"):
                doc["source"] = added.get("previous")
            else:
                del doc["source"]
    return origin


def _read_record(library: Library, asset_id: str) -> dict[str, Any]:
    return migrate(dict(library.records[asset_id]), kind=RECORD_KIND.name)


def read_version(library: Library, asset_id: str, label: str) -> dict[str, Any]:
    """One stored version, migrated to the current version-document schema."""
    return migrate(
        dict(library.versions[version_key(asset_id, label)]), kind=VERSION_KIND.name
    )


# --------------------------------------------------------------------------- per-file


def _glob_regex(glob: str, *, near: bool = False) -> re.Pattern[str]:
    """The regex a ``--license-part`` glob matches stored paths with.

    ``*`` and ``?`` stay inside one path segment, a whole ``**`` segment
    matches any number of segments (none included), everything else is
    literal and case-exact. ``near``: the looser pattern a NEAR miss matches —
    any case, any extension in place of the glob's own, ``_``/``-``/space
    interchangeable or absent in the file name, and extra folders above it.
    """
    segments = unicodedata.normalize("NFC", glob).split("/")
    out: list[str] = []
    for n, seg in enumerate(segments):
        last = n == len(segments) - 1
        if seg == "**":
            out.append("(?:[^/]+/)*" if not last else "(?:[^/]+(?:/[^/]+)*)?")
            continue
        stem, dot, ext = seg.rpartition(".")
        # An extension swap only where the stem names something (``head_*``):
        # a bare ``*.png`` means "every PNG", and its other files are no miss.
        swap = (
            near and last and dot and set(stem) - set("*?") and not set(ext) & set("*?")
        )
        body = stem if swap else seg
        loose = near and last
        piece = "".join(
            "[^/]*"
            if c == "*"
            else "[^/]"
            if c == "?"
            else r"[_\- ]?"
            if loose and c in "_- "
            else re.escape(c)
            for c in body
        )
        if loose:
            out.append("(?:[^/]+/)*")
        out.append(piece + (r"\.[^/.]+" if swap else "") + ("" if last else "/"))
    return re.compile("".join(out), re.IGNORECASE if near else 0)


def match_license_parts(
    parts: Mapping[str, Any], paths: Iterable[str]
) -> dict[str, tuple[str, Any]]:
    """``{path: (glob, source)}``: which stored path each ``--license-part`` glob labels.

    Matched against the paths the version stores (after clutter is skipped),
    NFC on both sides. Refused, with a sentence: a glob matching nothing; a
    path two globs give different sources; and a NEAR miss — a path no glob
    matches that one would match ignoring case, extension, the ``_``/``-``/space
    separators or extra folders
    (``parts/Head_3.PNG``, ``parts/head_3.jpg`` beside ``parts/head_*.png``),
    since a miss falls to the looser asset-level label.

    >>> match_license_parts({"parts/head_*.png": "private"},
    ...                     ["parts/head_1.png", "parts/body.svg"])
    {'parts/head_1.png': ('parts/head_*.png', 'private')}
    >>> sorted(match_license_parts({"**/*.png": "x"}, ["a.png", "parts/sub/b.png"]))
    ['a.png', 'parts/sub/b.png']
    >>> match_license_parts({"parts/head_*.png": "p"},
    ...     ["parts/head_1.png", "parts/head_2.jpg"])  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    LibraryError: ...
    """
    stored = {unicodedata.normalize("NFC", p): p for p in paths}
    found: dict[str, tuple[str, Any]] = {}
    for glob, source in parts.items():
        if not glob:
            raise LibraryError("a --license-part needs a glob before its '='")
        pattern = _glob_regex(glob)
        hits = [p for nfc, p in stored.items() if pattern.fullmatch(nfc)]
        if not hits:
            raise LibraryError(
                f"--license-part {glob!r} matches no file of the asset (globs are "
                "case-exact, '*' stays inside one folder and '**' crosses folders)"
            )
        for path in hits:
            held = found.get(path)
            if held is not None and held[1] != source:
                raise LibraryError(
                    f"{path!r} is matched by --license-part {held[0]!r} and {glob!r} "
                    "with different sources; make the globs disjoint"
                )
            found[path] = (glob, source)
    for glob in parts:
        near = _glob_regex(glob, near=True)
        missed = sorted(
            p for nfc, p in stored.items() if p not in found and near.fullmatch(nfc)
        )
        if missed:
            raise LibraryError(
                f"--license-part {glob!r} nearly matches {missed} (another case, "
                "extension, separator or folder), which would fall to the "
                "asset-level label: name them with their own --license-part, or "
                "widen the glob"
            )
    return found


def _file_entry(
    version: Mapping[str, Any], path: str, digest: str
) -> AssetSource | None:
    """The per-file statement ``version`` makes about exactly these bytes at ``path``.

    An entry pinned to other bytes (the file changed since) speaks for nothing.
    """
    raw = (version.get(FILE_SOURCES_FIELD) or {}).get(path)
    if not isinstance(raw, Mapping):
        return None
    try:
        source = AssetSource.model_validate(dict(raw))
    except ValueError:
        return None
    return source if _digest_of(source) == digest else None


def _file_contributions(
    version: Mapping[str, Any], prefix: str = ""
) -> list[tuple[str, AssetSource]]:
    """The per-file statements a version makes about the bytes it holds, as contributors."""
    out: list[tuple[str, AssetSource]] = []
    for path, raw in sorted((version.get("files") or {}).items()):
        entry = _file_entry(version, path, ContentRef.from_json(raw).item_id)
        if entry is not None:
            out.append((f"{prefix}{FILE_SOURCE_PREFIX}{path}", entry))
    return out


def _part_contributions(
    version: Mapping[str, Any], prefix: str = ""
) -> list[tuple[str, AssetSource]]:
    """The per-part sources pinned to the bytes a version holds, as contributors (an#357)."""
    out: list[tuple[str, AssetSource]] = []
    for path, raw in sorted((version.get("files") or {}).items()):
        part = itemising_source(version, path, ContentRef.from_json(raw).item_id)
        if part is not None:
            out.append((f"{prefix}{path}", part))
    return out


# --------------------------------------------------------------------------- rights


def _relicense_note(relicense: Mapping[str, Any]) -> str:
    return f"relicensed by {relicense.get('by')}: {relicense.get('reason')}"


def _relabel_note(relabel: Mapping[str, Any]) -> str:
    return f"labelled by {relabel.get('by')}: {relabel.get('reason')}"


#: How to label bytes nobody labelled, named wherever such a gap is reported.
LABEL_HINT: str = (
    "a publish with --license/--provider and --relabel-by/--relabel-reason labels it"
)


def _digest_of(source: AssetSource) -> str | None:
    sha = (source.sha256 or "").strip().lower()
    return sha.removeprefix("sha256:") or None


def itemising_source(
    version: Mapping[str, Any], path: str, digest: str
) -> AssetSource | None:
    """The per-part source a version gives exactly these bytes at ``path``, if any.

    It itemises only if it pins the same digest: a per-part source left on a
    file whose bytes have since changed (a factory stamp on a re-carved part)
    describes other bytes and speaks for nothing. A factory stamp itemises only
    if the factory's own record confirms it drew those bytes
    (:func:`an.credits.factory_recorded`): a stamp in a descriptor, typed or
    written by the public stamping functions, proves nothing (review-288 B1). The descriptor's ``source_svg``
    is itemised by a generator's descriptor-level stamp pinning its digest.
    """
    doc = version.get("doc") or {}
    own = doc.get("source")
    if path == doc.get("source_svg") and is_generated_source(own):
        # The generator's descriptor-level stamp pins the drawing the parts were
        # cut from — the same rule `an credits` applies (S2 of review-259).
        try:
            claim = AssetSource.model_validate(dict(own))
        except ValueError:
            claim = None
        if (
            claim is not None
            and _digest_of(claim) == digest
            and (
                not is_factory_stamp(own)
                or factory_recorded(digest, descriptor=doc, path=path)
            )
        ):
            return claim
    for skin in (doc.get("skins") or {}).values():
        if not isinstance(skin, Mapping):
            continue
        for attachments in (skin.get("slots") or {}).values():
            if not isinstance(attachments, Mapping):
                continue
            for att in attachments.values():
                if not isinstance(att, Mapping) or att.get("path") != path:
                    continue
                raw = att.get("source")
                if not isinstance(raw, Mapping):
                    continue
                try:
                    source = AssetSource.model_validate(dict(raw))
                except ValueError:
                    continue
                if _digest_of(source) == digest:
                    if is_factory_stamp(raw) and not factory_recorded(
                        digest, descriptor=doc, path=path
                    ):
                        # A factory stamp the factory's record does not
                        # confirm labels nothing (review-288 B1).
                        continue
                    return source
    return None


def factory_drew(version: Mapping[str, Any], path: str, digest: str) -> bool:
    """Whether ``version`` holds at ``path`` bytes the character factory provably drew.

    Both must hold: the version itemises the file with the factory's own stamp
    pinned to these bytes (:func:`itemising_source`; per part, or the
    descriptor's stamp for its ``source_svg``), AND this machine's record of
    generated bytes says the factory drew them
    (:func:`an.library.registry.generated_by`) — a record only the factory's
    stamping code writes. A stamp typed into a descriptor, or carried onto
    other bytes, fails the second test.

    What it buys (an#269): another asset's ``unknown`` statement about the same
    bytes — the silence of an asset published before stamps existed — does
    not bind them. It relaxes nothing anyone stated: a ``private`` or
    ``attribution`` statement still binds.
    """
    from an.credits import is_factory_stamp

    stamp = itemising_source(version, path, digest)
    if stamp is None or not is_factory_stamp(stamp.model_dump(mode="json")):
        return False
    return factory_recorded(digest, descriptor=version.get("doc"), path=path)


#: ``version_sources(floor=…)`` default: read the floor from every library on the machine.
_MACHINE: Any = object()


class _Answer(NamedTuple):
    """A recorded label answering the gaps of a version chain (an#263, an#307)."""

    note: str  # "labelled by <who>: <why>"
    source: AssetSource | None  # the source it labels them with
    held: frozenset[str]  # the digests the labelling version holds


#: What answers an ``unknown`` contributor, as :class:`Contributor` records it.
REMEDY_RELABEL: str = "relabel"
#: ``parent:<ref>`` — a gap of a version this one derives from.
REMEDY_PARENT: str = "parent:"
#: ``other:<ref>`` — another asset's silence about bytes this version holds.
REMEDY_OTHER: str = "other:"


class Contributor(str):
    """A contributor's label in :func:`version_sources`, knowing what would answer it.

    A plain ``str`` everywhere a label is read (reasons, credits); ``remedy``
    (one of the ``REMEDY_*`` forms, or empty) is what :func:`unknown_advice`
    turns into the sentence a refusal prints — so the advice names what works
    for THIS gap, not a relabel that cannot answer it (an#307).

    >>> c = Contributor("asset: no source", REMEDY_RELABEL)
    >>> (c, c.remedy, c.upper())
    ('asset: no source', 'relabel', 'ASSET: NO SOURCE')
    """

    remedy: str

    def __new__(cls, text: str, remedy: str = "") -> "Contributor":
        obj = super().__new__(cls, text)
        obj.remedy = remedy
        return obj


def version_labels(
    library: Library | None, version: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """The labels recorded on a stored version since it was published, oldest first.

    A relabel of a version's UNCHANGED content is recorded on that version, in
    the library's append-only ``labels`` store, instead of minting a new
    version (an#307). A label counts only for the very version it was made on:
    its ``manifest`` must be this version's (a same-named library's other
    ``x@v001`` never inherits it). An unreadable label is skipped with a
    :class:`LibraryIndexWarning`; skipping one can only leave the version
    stricter.
    """
    if library is None:
        return []
    asset, label, manifest = (
        version.get("asset"),
        version.get("version"),
        version.get("manifest_sha256"),
    )
    if not (asset and label and manifest):
        return []
    try:
        prefix = version_key(asset, label) + LABEL_KEY_SEP
    except AssetIdError:
        return []
    store = library.labels
    out: list[dict[str, Any]] = []
    for key in list(store):
        if not str(key).startswith(prefix):
            continue
        try:
            doc = migrate(dict(store[key]), kind=LABEL_KIND.name)
            relabel = doc.get(RELABEL_FIELD) or {}
            _source_model(doc.get("source"))
        except Exception as e:  # noqa: BLE001 — reported, and skipping is stricter
            warnings.warn(
                f"{library.name}:{key} could not be read ({type(e).__name__}: {e}); "
                "that label is not counted",
                LibraryIndexWarning,
                stacklevel=2,
            )
            continue
        if str(key).rpartition(LABEL_KEY_SEP)[2] != _label_id(doc):
            warnings.warn(
                f"{library.name}:{key} does not say what its id was made from (it "
                "was edited); that label is not counted",
                LibraryIndexWarning,
                stacklevel=2,
            )
            continue
        if (
            doc.get("manifest") == manifest
            and doc.get("source")
            and relabel.get("by")
            and relabel.get("reason")
        ):
            out.append({**doc, "_key": str(key)})
    return sorted(out, key=lambda d: (str(d.get("labelled") or ""), d["_key"]))


#: The fields of a label its id is the hash of: what it says, and the version it says it of.
_LABEL_ID_FIELDS: tuple[str, ...] = ("manifest", "source", RELABEL_FIELD, "rights")
#: Hex digits of that hash in the label's key.
_LABEL_ID_LEN: int = 16


def _label_id(label: Mapping[str, Any]) -> str:
    """The id of a label: the hash of what it says (an edited label no longer matches it)."""
    said = {f: label.get(f) for f in _LABEL_ID_FIELDS}
    return hashlib.sha256(canonical_json(said).encode("utf-8")).hexdigest()[
        :_LABEL_ID_LEN
    ]


def labelled_view(
    version: Mapping[str, Any], labels: Iterable[Mapping[str, Any]]
) -> Mapping[str, Any]:
    """``version`` as its latest label presents it: what a check-out writes, what a publish carries.

    The latest label's source and relabel replace the version's own, and the
    gaps the version recorded (``unlabelled``) are answered — exactly the
    version a relabel publish of the unchanged content would have minted.
    Rights are never read from it: :func:`version_sources` reads the version
    and its labels.
    """
    labels = list(labels)
    if not labels:
        return version
    latest = labels[-1]
    view = {
        **version,
        "source": latest.get("source"),
        RELABEL_FIELD: latest.get(RELABEL_FIELD),
    }
    view.pop(UNLABELLED_FIELD, None)
    return view


def stored_rights(library: Library | None, version: Mapping[str, Any]) -> Rights:
    """The rights cached for a version: its latest label's, else the version's own.

    A cache, never the answer: every reader takes the stricter of it and the
    recomputed :func:`effective_rights`.
    """
    labels = version_labels(library, version)
    block = (labels[-1].get("rights") if labels else None) or version.get("rights")
    return Rights.from_dict(block or {})


def _stricter_statement(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Whether statement ``a`` is more restrictive than ``b``."""
    order = LICENSE_CLASS_ORDER.index
    return order(a.get("class", "unknown")) < order(b.get("class", "unknown"))


def _resolve_lineage(
    libraries: Libraries, ref: str, pin: str | None
) -> tuple[Library, LibraryRef, Mapping[str, Any]]:
    """``(holder, pinned_ref, version)`` for a lineage reference.

    With ``pin`` (the manifest the child recorded for this parent at publish,
    :data:`LINEAGE_FIELD`), only that very version answers — in whichever
    library on the path holds it. A same-named library's other ``x@v001`` is
    another version, so it raises :class:`AssetNotFoundError` instead of being
    read in its place (review-269 B1).
    """
    if not pin:
        return resolve(libraries, ref)
    wanted = parse_ref(ref)
    for library in as_libraries(libraries):
        if wanted.namespace and library.name != wanted.namespace:
            continue
        if wanted.version is None or wanted.asset_id not in library.records:
            continue
        key = version_key(wanted.asset_id, wanted.version)
        if key not in library.versions:
            continue
        version = library.versions[key]
        if version.get("manifest_sha256") == pin:
            return (
                library,
                LibraryRef(wanted.asset_id, wanted.version, library.name),
                version,
            )
    raise AssetNotFoundError(
        f"{ref} as pinned (manifest {pin[:12]}…) is in no library on the path"
    )


def version_sources(
    libraries: Libraries,
    version: Mapping[str, Any],
    *,
    floor: BlobFloor | None = _MACHINE,
    owner: Library | None = None,
    per_file: bool = True,
) -> list[tuple[str, AssetSource | None]]:
    """Every labelled source a version's rights depend on — its own, its lineage, its bytes.

    - its own (:func:`an.library.rights.sources_in`: asset-level, descriptor, parts);
    - the version it follows (``previous``) and each ``derived_from`` version,
      recursively, labelled ``<ref> > <label>``. A version records the
      manifest of each parent it resolved at publish (:data:`LINEAGE_FIELD`);
      a parent that no longer resolves to that manifest is "not on the search
      path", and the rights the child recorded stand in for it;
    - the **floor** of every file of every version walked: what any library on
      this machine says about the same bytes (:mod:`an.library.floor`),
      labelled ``<path>: same bytes as <asset>@<version>``. A blob is as
      restricted as the strictest statement made about it anywhere.

    One exception to reading the floor, so a ``relabel`` can answer an earlier
    version's gap: the ``unknown`` statements of a version this walk read in
    full AND could verify (each lineage link resolved to its pinned manifest,
    or a ``previous`` link inside the same library root) are not read twice. A
    ``private`` or ``attribution`` statement is always read, and so is anything
    said by a version the walk could not verify (review-269 B1).

    floor: a :class:`~an.library.floor.BlobFloor` to read (default: every
        library on the machine); ``None`` leaves the floor out — what the
        version itself says (its "asset label"), which is what the floor stores
    owner: the library holding ``version`` (default: unknown — its own
        statements are then read from the floor too, which repeats a reason and
        relaxes nothing)
    per_file: count each walked version's per-file statements
        (:data:`FILE_SOURCES_FIELD`, labelled ``file:<path>``; an#345) — they
        count toward a version's rights, never toward the label that speaks
        for the files nothing itemises (``False``: :func:`_own_label_class`)

    A version carrying an explicit ``relicense`` (who, why) contributes its
    asset-level source alone: that recorded statement replaces everything it
    would otherwise inherit, and is the only way to relax rights. A version
    carrying a ``relabel`` (who, why, beside an explicit source) answers the
    GAPS of its own ``previous`` chain with that source — a file recorded
    ``unlabelled``, a version that recorded no source at all — and nothing else
    (:data:`RELABEL_FIELD`). A parent no library on the path holds falls back to
    the rights recorded at publish, or ``unknown`` — never silence.
    """
    if floor is _MACHINE:
        floor = BlobFloor(libraries)
    out: list[tuple[str, AssetSource | None]] = []
    seen: set[str] = set()
    trusted: set[tuple[str, str]] = set()  # (library origin, manifest)
    # (prefix, version walked, the labels answering its chain — nearest first)
    visits: list[tuple[str, Mapping[str, Any], tuple[_Answer, ...]]] = []

    def walk(
        version: Mapping[str, Any],
        holder: Library | None,
        prefix: str,
        answers: tuple[_Answer, ...],
        *,
        via: str | None = None,
        raw: bool = False,
    ) -> bool:
        """Add one version's contributions and its lineage's; return whether it is verified.

        answers: the recorded labels of this chain made after this version,
            nearest first: the nearest answers its gaps; any whose labelling
            version no longer holds a file answers another asset's silence
            about it (an#307)
        via: the ``derived_from`` parent this branch of the walk entered by
            (``None`` on the version's own chain), for the remedy a gap names
        raw: the version as published, without the labels recorded on it since
        """
        if not raw:
            labels = version_labels(holder, version)
            if labels:
                # Each label is a statement made about this very version after
                # it was published (an#307): what a relabel publish of its
                # unchanged content would have said as a new version — its
                # source contributes, and the earliest label answers the gaps
                # of this version and its own chain.
                kind = ASSET_KINDS.get(version.get("doc_kind") or "")
                hashes = _file_hashes(version.get("files") or {})
                for label in labels:
                    out.extend(
                        (f"{prefix}{name}", src)
                        for name, src in sources_in(
                            version.get("doc") or {},
                            store=kind.credits_store if kind else None,
                            source=_source_model(label.get("source")),
                            files=hashes,
                        )
                    )
                first = labels[0]
                answer = _Answer(
                    _relabel_note(first[RELABEL_FIELD]),
                    _source_model(first.get("source")),
                    frozenset(hashes.values()),
                )
                return walk(
                    version, holder, prefix, (answer, *answers), via=via, raw=True
                )
        relicense = version.get(RELICENSE_FIELD)
        if not relicense:  # a relicence replaces everything, its bytes' floor included
            visits.append((prefix, version, answers))
        if relicense:
            out.append(
                (
                    f"{prefix}asset ({_relicense_note(relicense)})",
                    _source_model(version.get("source")),
                )
            )
            # A relicence never covers a per-file statement it did not name:
            # one stricter than it keeps binding (an#345) — nor a per-part
            # source pinned to the version's own bytes (an#357, probe T5).
            if per_file:
                out.extend(_file_contributions(version, prefix))
                out.extend(_part_contributions(version, prefix))
            return _verify(version, holder, True)

        def gap(
            label: str, why: str = "", *, placeholder: AssetSource | None = None
        ) -> tuple[str, AssetSource | None]:
            # Nobody ever said anything here: answered by a later version's
            # explicit, recorded label of this chain, else unknown.
            if not answers:
                if via is not None:
                    hint = f"label {via} first"
                    remedy = f"{REMEDY_PARENT}{via}"
                else:
                    hint, remedy = LABEL_HINT, REMEDY_RELABEL
                text = f"{label} ({why}: {hint})" if why else label
                return (Contributor(text, remedy), placeholder)
            return (f"{label} ({answers[0].note})", answers[0].source)

        kind = ASSET_KINDS.get(version.get("doc_kind") or "")
        out.extend(
            gap(f"{prefix}{label}")
            if src is None and label == ASSET_SOURCE_LABEL
            # A file no person's source speaks for (an#307): a gap too.
            else gap(f"{prefix}{label}", placeholder=src)
            if nobody_labelled(src)
            else (f"{prefix}{label}", src)
            for label, src in sources_in(
                version.get("doc") or {},
                store=kind.credits_store if kind else None,
                source=_source_model(version.get("source")),
                files=_file_hashes(version.get("files") or {}),
            )
        )
        if per_file:
            out.extend(_file_contributions(version, prefix))
        out.extend(
            gap(
                f"{prefix}{path}",
                "changed since the carried source was declared; not labelled",
            )
            for path in version.get(UNLABELLED_FIELD) or []
        )
        relabel = version.get(RELABEL_FIELD)
        own_answer = (
            _Answer(
                _relabel_note(relabel),
                _source_model(version.get("source")),
                frozenset(_file_hashes(version.get("files") or {}).values()),
            )
            if relabel and version.get("source")
            else None
        )
        pins = version.get(LINEAGE_FIELD) or {}
        chain = (own_answer, *answers) if own_answer else answers
        lineage = [
            (ref, f"previous version {ref}", chain, True)
            for ref in [version.get(PREVIOUS_FIELD)]
            if ref
        ] + [(ref, ref, (), False) for ref in version.get("derived_from") or []]
        links_ok = True
        for parent, label, answer, is_previous in lineage:
            pin = pins.get(parent)
            try:
                parent_holder, pinned, parent_version = _resolve_lineage(
                    libraries, parent, pin
                )
            except (AssetNotFoundError, AssetIdError):
                # Not on this search path (or not the version pinned): fall
                # back to the rights this version recorded when it was
                # published (which did resolve the parent).
                links_ok = False
                recorded = version.get("rights")
                out.append(
                    (
                        f"{prefix}{label} (not on the search path; as recorded)",
                        _recorded_source(Rights.from_dict(recorded), parent)
                        if recorded
                        else None,
                    )
                )
                continue
            # A link is verified by its pin, or — a `previous` link, which never
            # leaves its asset — by resolving inside the child's own library.
            link_ok = bool(pin) or (
                is_previous
                and holder is not None
                and library_origin(parent_holder) == library_origin(holder)
            )
            if str(pinned) in seen:
                links_ok = links_ok and link_ok
                continue
            seen.add(str(pinned))
            parent_ok = walk(
                parent_version,
                parent_holder,
                f"{prefix}{label} > ",
                answer,
                via=via if is_previous else str(pinned),
            )
            links_ok = links_ok and link_ok and parent_ok
        return _verify(version, holder, links_ok)

    def _verify(version: Mapping[str, Any], holder: Library | None, ok: bool) -> bool:
        if ok and holder is not None and version.get("manifest_sha256"):
            trusted.add((library_origin(holder), version["manifest_sha256"]))
        return ok

    root_ok = walk(version, owner, "", ())
    if floor is None:
        return out
    out.extend(_rule_contributions(libraries, version, owner, roll_up(out)))
    # The root's own statements, when its walk is verified, are this walk.
    own = (
        {(library_origin(owner), version["manifest_sha256"])}
        if root_ok and owner is not None and version.get("manifest_sha256")
        else set()
    )
    for prefix, walked, answers in visits:
        for path, raw in sorted((walked.get("files") or {}).items()):
            digest = ContentRef.from_json(raw).item_id
            bound: dict[str, dict[str, Any]] = {}
            answered: dict[str, dict[str, Any]] = {}
            # A later label of this chain made by a version that no longer
            # holds these bytes (an#307).
            answer = next((a for a in answers if digest not in a.held), None)
            for origin, key, statement in floor.each(digest):
                cls = statement.get("class", "unknown")
                made_by = (origin, statement.get("manifest"))
                if cls == "free" or made_by in own:
                    continue
                if cls == "unknown" and made_by in trusted:
                    # A verified version this walk read in full: its silence
                    # is already here, and may be a gap a later label answers.
                    # (Its `private` or `attribution` is always read.)
                    continue
                if cls == "unknown" and answer is not None:
                    # Another asset's SILENCE about bytes an earlier version
                    # of this chain held, and the version whose label answers
                    # this chain's gaps no longer holds (an#307): binding the
                    # chain to it would make two assets that once shared an
                    # unlabelled file block each other's labels forever. The
                    # label says nothing about those bytes — they stay
                    # `unknown` wherever they are held — and `private` or
                    # `attribution` statements are never answered.
                    answered[key] = statement
                    continue
                held = bound.get(key)
                if held is None or _stricter_statement(statement, held):
                    bound[key] = statement
            # Another asset's silence (`unknown`) about bytes the factory
            # provably drew is no statement against them (an#269).
            if any(st.get("class") == "unknown" for st in bound.values()) and (
                factory_drew(walked, path, digest)
            ):
                bound = {
                    k: st for k, st in bound.items() if st.get("class") != "unknown"
                }
            for asset_key, statement in sorted(bound.items()):
                ref = f"{asset_key}@{statement.get('version')}"
                label = (
                    f"{prefix}{path}: same bytes as {ref} ({statement.get('label')})"
                )
                out.append(
                    (
                        Contributor(label, f"{REMEDY_OTHER}{ref}")
                        if statement.get("class", "unknown") == "unknown"
                        else label,
                        _recorded_source(
                            Rights(statement.get("class", "unknown"), []), ref
                        ),
                    )
                )
            for asset_key, statement in sorted(answered.items()):
                if asset_key in bound:
                    continue
                ref = f"{asset_key}@{statement.get('version')}"
                out.append(
                    (
                        f"{prefix}{path}: same bytes as {ref}, unlabelled there "
                        f"(not held since; {answer.note})",
                        answer.source,
                    )
                )
    return out


def _rule_contributions(
    libraries: Libraries,
    version: Mapping[str, Any],
    owner: Library | None,
    walked: Rights,
) -> list[tuple[str, AssetSource]]:
    """What :class:`_PerFileRule` states about ``version``'s own blobs, where stricter than ``walked``.

    The rights walk stops at a relicence; the rule does not, for bytes the
    relicence did not cover (an#345 R1/R2). Without this a version's rights
    could read freer than what the floor states about its own bytes (an#357:
    a per-file label behind a relicence that never named it). Only a version
    the rule can state stricter than its own label is read: one carrying a
    per-part or per-file statement, a relicence, or per-file statements in
    its lineage.
    """
    order = LICENSE_CLASS_ORDER.index
    rule = _PerFileRule(libraries)
    hashes = _file_hashes(version.get("files") or {})
    if version.get(RELICENSE_FIELD) or rule.applies(version, owner):
        digests = set(hashes.values())
    else:
        digests = {
            d for p, d in hashes.items() if any(rule._claims(version, p, d))
        }
    out: list[tuple[str, AssetSource]] = []
    for digest in sorted(digests):
        cls, why = rule.statement(version, owner, digest)
        if order(cls) < order(walked.license_class):
            path = next(p for p, d in sorted(hashes.items()) if d == digest)
            out.append((f"{path}: {why}", _recorded_source(Rights(cls, []), why)))
    return out


def _own_label_class(
    libraries: Libraries, version: Mapping[str, Any], *, owner: Library | None = None
) -> str:
    """The class of what a version says about every file it does not itemise
    (with the labels recorded on it since, when ``owner`` holds it).

    Per-file statements (an#345) are left out at every depth of the walk: a
    file another file's label names is no reason to restate THIS file.
    """
    return roll_up(
        version_sources(libraries, version, floor=None, owner=owner, per_file=False)
    ).license_class


#: A statement as the never-relax rule weighs it: ``(class, why)``.
_Said = tuple[str, str]


def _strictest(*said: _Said | None) -> _Said:
    """The most restrictive of several ``(class, why)``; on a tie, the first."""
    order = LICENSE_CLASS_ORDER.index
    present = [s for s in said if s is not None]
    return min(present, key=lambda s: order(s[0])) if present else ("free", "")


def _source_class(source: AssetSource | None) -> str:
    return license_class(source) if source is not None else "unknown"


def _relicence_covers(version: Mapping[str, Any], digest: str) -> bool:
    """Whether ``version``'s relicence speaks for ``digest``: all its bytes,
    or only those its ``covers`` lists (a version under the per-file rule)."""
    relicense = version.get(RELICENSE_FIELD)
    if not relicense:
        return False
    covers = relicense.get(RELICENSE_COVERS)
    return covers is None or digest in covers


class _PerFileRule:
    """What a version says about each of its blobs under the never-relax rule (an#345, an#357).

    For each file the class stated is the STRICTEST of:

    - its per-file statement and its per-part source, whichever it has (neither
      wins by position), else the version's label computed without any
      per-file statement (:func:`_own_label_class`);
    - what the version says about the same bytes at its other paths;
    - what every version of its lineage — ``previous`` back to the first,
      and each ``derived_from`` parent — says about these bytes: the
      statement of the nearest one holding them, or, for bytes it does not
      hold, its own label (bytes new to a private chain stay private).

    A relicensed version states its relicence for the bytes it covers
    (:data:`RELICENSE_COVERS`) and its per-file or per-part statement for any
    stricter. A per-part source carrying the character factory's own stamp,
    which the factory's record confirms it drew (:func:`factory_drew`), speaks
    for those bytes alone (an#281: mouths redrawn under a private body).

    Every version is stated this way since an#357, a per-part source included:
    a version without one, and without per-file statements in its lineage, is
    stated exactly as before. A statement the version makes that is freer than
    what binds is kept and recorded as a :class:`RightsConflict`
    (:meth:`conflicts`), never discarded and never refused here.
    Memoised: build one per operation.
    """

    def __init__(self, readers: Libraries) -> None:
        self.readers = readers
        self._memo: dict[tuple[Any, ...], Any] = {}

    def _cached(self, key: tuple[Any, ...], compute: Callable[[], Any]) -> Any:
        if key not in self._memo:
            self._memo[key] = compute()
        return self._memo[key]

    @staticmethod
    def _vid(version: Mapping[str, Any], holder: Library | None) -> tuple[Any, ...]:
        # The manifest does not name the asset: two assets' identical versions
        # share one, and must not share what is said about them.
        return (
            library_origin(holder) if holder is not None else None,
            version.get("asset"),
            version.get("version"),
            version.get("manifest_sha256") or id(version),
        )

    def parents(
        self, version: Mapping[str, Any], holder: Library | None
    ) -> list[tuple[str, Mapping[str, Any] | None, Library | None]]:
        """``(ref, parent, holder)`` per lineage link; ``parent`` None if it no longer resolves."""

        def compute() -> list[tuple[str, Mapping[str, Any] | None, Library | None]]:
            pins = version.get(LINEAGE_FIELD) or {}
            refs = [version.get(PREVIOUS_FIELD), *(version.get("derived_from") or [])]
            out: list[tuple[str, Mapping[str, Any] | None, Library | None]] = []
            for ref in (r for r in refs if r):
                try:
                    at, pinned, parent = _resolve_lineage(
                        self.readers, ref, pins.get(ref)
                    )
                    parent = migrate(dict(parent), kind=VERSION_KIND.name)
                except Exception:  # noqa: BLE001 — unresolvable or unreadable: as recorded
                    out.append((ref, None, None))
                    continue
                out.append((str(pinned), parent, at))
            return out

        return self._cached(("parents", *self._vid(version, holder)), compute)

    def applies(self, version: Mapping[str, Any], holder: Library | None) -> bool:
        """Whether ``version`` or any version of its lineage carries ``file_sources``."""
        return self._cached(
            ("applies", *self._vid(version, holder)),
            lambda: (
                FILE_SOURCES_FIELD in version
                or any(
                    parent is not None and self.applies(parent, at)
                    for _, parent, at in self.parents(version, holder)
                )
            ),
        )

    def per_file_lineage(
        self, version: Mapping[str, Any], holder: Library | None, digest: str
    ) -> _Said | None:
        """The strictest PER-FILE statement any version of ``version``'s lineage made about ``digest``.

        What a relicence must name to relax (R1/R2 of the an#345 review): a
        walk stops at a relicence that covered the digest, which relaxed it.
        """

        def compute() -> _Said | None:
            said: list[_Said] = []
            for ref, parent, at in self.parents(version, holder):
                if parent is None:
                    continue
                for path, d in _file_hashes(parent.get("files") or {}).items():
                    entry = _file_entry(parent, path, d) if d == digest else None
                    if entry is not None:
                        said.append(
                            (
                                _source_class(entry),
                                f"{ref}: {path} itemised per file as {entry.license}",
                            )
                        )
                if not _relicence_covers(parent, digest):
                    deeper = self.per_file_lineage(parent, at, digest)
                    if deeper is not None:
                        said.append(deeper)
            return _strictest(*said) if said else None

        return self._cached(("per_file", *self._vid(version, holder), digest), compute)

    def own_label(self, version: Mapping[str, Any], holder: Library | None) -> str:
        return self._cached(
            ("own", *self._vid(version, holder)),
            lambda: _own_label_class(self.readers, version, owner=holder),
        )

    def lineage(
        self, version: Mapping[str, Any], holder: Library | None, digest: str
    ) -> _Said | None:
        """The strictest thing the lineage of ``version`` says about ``digest`` (None: no lineage)."""
        if _relicence_covers(version, digest):
            return None  # a relicence replaces what it inherits, for what it names

        def compute() -> _Said | None:
            said: list[_Said] = []
            for ref, parent, at in self.parents(version, holder):
                if parent is None:
                    recorded = Rights.from_dict(version.get("rights") or {})
                    said.append(
                        (
                            recorded.license_class,
                            f"{ref} (not on the search path; as recorded)",
                        )
                    )
                    continue
                cls, why = self.said(parent, at, digest)
                said.append((cls, f"{ref}: {why}"))
            return _strictest(*said) if said else None

        return self._cached(("lineage", *self._vid(version, holder), digest), compute)

    def said(
        self, version: Mapping[str, Any], holder: Library | None, digest: str
    ) -> _Said:
        """What ``version`` says about ``digest``, held or not, with its own lineage's statement."""

        def compute() -> _Said:
            if digest in _file_hashes(version.get("files") or {}).values():
                own = self.statement(version, holder, digest)
            else:
                own = (self.own_label(version, holder), "its own label")
            return _strictest(own, self.lineage(version, holder, digest))

        return self._cached(("said", *self._vid(version, holder), digest), compute)

    def statement(
        self, version: Mapping[str, Any], holder: Library | None, digest: str
    ) -> _Said:
        """What ``version`` says about the bytes ``digest`` it holds: strictest over its paths."""

        def compute() -> _Said:
            paths = [
                p
                for p, d in sorted(_file_hashes(version.get("files") or {}).items())
                if d == digest
            ]
            # One statement per digest, the strictest over its paths: never the
            # last path's (L1-4 of the an#345 review; an#357 for per-part sources).
            return _strictest(
                *(self._at_path(version, holder, p, digest) for p in paths)
            )

        return self._cached(("statement", *self._vid(version, holder), digest), compute)

    def _claims(
        self, version: Mapping[str, Any], path: str, digest: str
    ) -> tuple[_Said | None, _Said | None]:
        """``(per-file, per-part)``: what ``version`` itself says about the bytes at ``path``."""
        entry = _file_entry(version, path, digest)
        mine = (
            (_source_class(entry), f"{path} itemised per file as {entry.license}")
            if entry is not None
            else None
        )
        part = itemising_source(version, path, digest)
        part_said = (
            (license_class(part), f"{path} itemised as {part.license or 'no licence'}")
            if part is not None
            else None
        )
        return mine, part_said

    def _relicence(self, version: Mapping[str, Any]) -> _Said:
        source = _source_model(version.get("source"))
        return (
            _source_class(source) if source is not None else "unknown",
            _relicense_note(version[RELICENSE_FIELD]),
        )

    def _at_path(
        self, version: Mapping[str, Any], holder: Library | None, path: str, digest: str
    ) -> _Said:
        mine, part_said = self._claims(version, path, digest)
        if version.get(RELICENSE_FIELD):
            rel = self._relicence(version)
            if _relicence_covers(version, digest):
                # A relicence speaks for what it covers; a stricter statement
                # this version makes about the file still binds (probe T5).
                return _strictest(mine, part_said, rel)
            # A relicence speaks only for the bytes it names: these keep what
            # their lineage said about them.
            return _strictest(
                mine or rel, part_said, self.lineage(version, holder, digest)
            )
        if mine is None and part_said is None:
            own = (self.own_label(version, holder), "the asset's own label")
            if not self.applies(version, holder):
                return own  # the own label already rolls up the lineage
            return _strictest(own, self.lineage(version, holder, digest))
        claims = _strictest(mine, part_said)
        if mine is None and factory_drew(version, path, digest):
            # The factory's own drawing, confirmed by its record: its stamp
            # speaks for these bytes, whatever body they were drawn for (an#281).
            return claims
        # An itemised statement never relaxes what binds these bytes (an#357).
        return _strictest(claims, self.lineage(version, holder, digest))

    def conflicts(
        self, version: Mapping[str, Any], holder: Library | None
    ) -> list[RightsConflict]:
        """Every statement ``version`` makes about a file that is freer than what binds it (an#357).

        A claim is the file's per-file statement, its per-part source, or a
        relicence that does not cover these bytes although no stricter
        statement of this version names them. Each is compared with the
        version's statement about the digest (:meth:`statement`: the
        strictest over its paths and its lineage).
        """

        def compute() -> list[RightsConflict]:
            order = LICENSE_CLASS_ORDER.index
            out: list[RightsConflict] = []
            for path, digest in sorted(_file_hashes(version.get("files") or {}).items()):
                mine, part_said = self._claims(version, path, digest)
                claims = [mine, part_said]
                if (
                    version.get(RELICENSE_FIELD)
                    and not _relicence_covers(version, digest)
                    and mine is None
                ):
                    claims.append(self._relicence(version))
                claims = list(dict.fromkeys(c for c in claims if c is not None))
                if not claims:
                    continue  # nothing claimed about this file: nothing to conflict
                binding = self.statement(version, holder, digest)
                for claim in claims:
                    if order(claim[0]) > order(binding[0]):
                        out.append(
                            RightsConflict(path, digest, *claim, *binding)
                        )
            return out

        return self._cached(("conflicts", *self._vid(version, holder)), compute)


def _version_statements(
    library: Library,
    readers: Libraries,
    version: Mapping[str, Any],
    *,
    rule: _PerFileRule | None = None,
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """``(digest, asset_key, statement)`` for each blob of ``version``, one per digest.

    Every version is stated by :class:`_PerFileRule` (an#357): a per-part or
    per-file statement never relaxes what binds its bytes, and the same bytes
    at two paths take the stricter. A statement freer than what binds is
    kept as a :class:`RightsConflict` under :data:`CONFLICTS_KEY` (only when
    there is one, so a statement without a conflict is stored as before).
    The version's own label is computed at most once (an#249 R4-N3).
    """
    asset_key = f"{library.name}:{version['asset']}"
    rule = rule if rule is not None else _PerFileRule(readers)
    conflicts: dict[str, list[dict[str, str]]] = {}
    for conflict in rule.conflicts(version, library):
        conflicts.setdefault(conflict.digest, []).append(conflict.to_dict())
    digests = dict.fromkeys(
        ContentRef.from_json(raw).item_id
        for _, raw in sorted((version.get("files") or {}).items())
    )
    for digest in digests:
        cls, why = rule.statement(version, library, digest)
        statement = {
            "version": version.get("version"),
            "number": version_number(version["version"]),
            "class": cls,
            "label": why,
            "manifest": version.get("manifest_sha256"),
        }
        if digest in conflicts:
            statement[CONFLICTS_KEY] = conflicts[digest]
        yield (digest, asset_key, statement)


def _index_version(
    library: Library, readers: Libraries, version: Mapping[str, Any]
) -> None:
    """Record what ``version`` says about each of its blobs: in ``library``'s floor
    index, and in the machine's memory (which outlives the library's root)."""
    said = list(_version_statements(library, readers, version))
    remember(library, said)
    for digest, asset_key, statement in said:
        record_statement(library.blob_rights, digest, asset_key, statement)


def _reindex_readers(library: Library, search: Libraries | None) -> list[Library]:
    # The search path first, then every other library on the machine: a
    # lineage link pinned to its parent's manifest resolves wherever the parent
    # lives, so what a version states does not depend on whether the caller
    # passed the parent's library (an#361). An unpinned link resolves by name,
    # and the search path is read first.
    return machine_libraries(
        [
            library,
            *(
                lib
                for lib in (as_libraries(search) if search else [])
                if lib.name != library.name
            ),
        ]
    )


def _fresh_index(
    library: Library, readers: Libraries
) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str, dict[str, Any]]]]:
    """``(index, statements)``: the floor index ``library``'s versions state now, written nowhere."""
    fresh: dict[str, dict[str, Any]] = {}
    said_all: list[tuple[str, str, dict[str, Any]]] = []
    rule = _PerFileRule(readers)  # one memo for the whole library (review N3)
    for key in sorted(
        library.versions,
        key=lambda k: (k.split("@")[0], version_number(k.split("@")[1])),
    ):
        try:
            version = migrate(dict(library.versions[key]), kind=VERSION_KIND.name)
        except Exception:  # noqa: BLE001 — reported by scan_index; nothing to index
            continue
        said = list(_version_statements(library, readers, version, rule=rule))
        said_all += said
        for digest, asset_key, statement in said:
            record_statement(fresh, digest, asset_key, statement)
    return fresh, said_all


def reindex(library: Library, *, search: Libraries | None = None) -> int:
    """Rebuild ``library``'s floor index from its versions. Returns the number of blobs indexed.

    Lineage resolves through ``search`` and then every library on this machine
    (:func:`an.library.floor.machine_libraries`), so a promoted copy's parent
    in a genre's library is read without being named (an#361).

    The index is derived data: rebuilding it is always safe, and the way to
    repair a library whose index was lost or written by an older ``an``. It also
    (re-)registers the library's root in the machine registry
    (:mod:`an.library.registry`), so a library made at a custom root before the
    registry existed becomes visible to every other library's rights floor.
    :func:`reindex_changes` says first what a rebuild would change.

    The new index is computed in full first, then written over the old one
    entry by entry, and only then are stale entries removed: a crash midway
    leaves old and new statements side by side, never an empty floor (an#249
    R4-N4).
    """
    register_library(library)
    fresh, said = _fresh_index(library, _reindex_readers(library, search))
    remember(library, said)
    store = library.blob_rights
    for digest, entries in fresh.items():
        store[digest] = entries
    for digest in [d for d in store if d not in fresh]:
        del store[digest]
    return len(fresh)


@dataclass(frozen=True)
class LabelChange:
    """What a :func:`reindex` would change in what one asset states about one blob."""

    asset: str  # "<library>:<asset_id>"
    paths: tuple[str, ...]  # where the asset's stating version holds the blob
    digest: str
    before: str  # the class the index holds now ("" when it holds none)
    after: str  # the class a rebuild states ("" when it states none)
    label: str  # why, as the rebuild states it
    conflicts: int = 0  # rights conflicts the rebuilt statement records

    def __str__(self) -> str:
        where = ", ".join(self.paths) or self.digest[:12]
        note = f"; {self.conflicts} rights conflict(s)" if self.conflicts else ""
        return (
            f"{self.asset} {where}: {self.before or '-'} -> {self.after or '-'} "
            f"({self.label}{note})"
        )


def reindex_changes(
    library: Library, *, search: Libraries | None = None
) -> list[LabelChange]:
    """A dry run of :func:`reindex`: every statement whose class would change, and nothing written.

    Neither the library, the machine registry nor its memory of statements is
    touched. A statement that changes only its wording (its ``label``) or
    gains a recorded conflict without changing class is not listed as a
    change unless it gains a conflict.

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> _ = publish(lib, "prop.lamp", {"name": "lamp"}, {"a.svg": b"<svg/>"},
    ...             source={"provider": "me", "license": "cc0-1.0"})
    >>> reindex_changes(lib)
    []
    """
    fresh, _ = _fresh_index(library, _reindex_readers(library, search))
    store = library.blob_rights
    out: list[LabelChange] = []
    for digest in sorted(set(fresh) | set(store)):
        new = fresh.get(digest) or {}
        old = (store[digest] if digest in store else None) or {}
        for asset_key in sorted(set(new) | set(old)):
            after, before = new.get(asset_key) or {}, old.get(asset_key) or {}
            gained = len(after.get(CONFLICTS_KEY) or []) > len(
                before.get(CONFLICTS_KEY) or []
            )
            if after.get("class") == before.get("class") and not gained:
                continue
            stating = after or before
            out.append(
                LabelChange(
                    asset_key,
                    _paths_of(library, asset_key, stating.get("version"), digest),
                    digest,
                    before.get("class", ""),
                    after.get("class", ""),
                    after.get("label") or before.get("label") or "",
                    len(after.get(CONFLICTS_KEY) or []),
                )
            )
    return out


def _paths_of(
    library: Library, asset_key: str, version: str | None, digest: str
) -> tuple[str, ...]:
    """The paths at which ``asset_key@version`` holds ``digest`` (none if unreadable)."""
    asset_id = asset_key.split(":", 1)[-1]
    key = version_key(asset_id, version) if version else None
    try:
        held = library.versions[key] if key and key in library.versions else {}
    except Exception:  # noqa: BLE001 — a damaged version names no path
        return ()
    return tuple(
        p for p, d in sorted(_file_hashes(held.get("files") or {}).items()) if d == digest
    )


#: The licence code standing in for each class when only a recorded class is known.
_CLASS_LICENSE: dict[str, str | None] = {
    "private": PRIVATE_STUDY,
    "noncommercial": "cc-by-nc",
    "attribution": "cc-by",
    "free": PUBLIC_DOMAIN,
    "unknown": None,
}


def _recorded_source(rights: Rights, ref: str) -> AssetSource:
    """A stand-in source carrying a recorded licence class (for a parent not on the path)."""
    return AssetSource(
        provider="library",
        id=ref,
        license=_CLASS_LICENSE.get(rights.license_class),
        extra={"recorded_rights": rights.to_dict()},
    )


def effective_rights(
    libraries: Libraries,
    version: Mapping[str, Any],
    *,
    floor: BlobFloor | None = _MACHINE,
    owner: Library | None = None,
) -> Rights:
    """The rights of a version, recomputed from its sources, its lineage and its bytes.

    owner: the library holding ``version`` (see :func:`version_sources`)

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> _ = publish(lib, "prop.vase", {"name": "vase"},
    ...             source={"provider": "film", "license": "all-rights-reserved"})
    >>> effective_rights(lib, read_version(lib, "prop.vase", "v001"), owner=lib).license_class
    'private'
    """
    rights = roll_up(version_sources(libraries, version, floor=floor, owner=owner))
    relicense = version.get(RELICENSE_FIELD)
    if relicense:
        return Rights(
            rights.license_class, [*rights.reasons, _relicense_note(relicense)]
        )
    notes = [
        _relabel_note(relabel)
        for relabel in [
            version.get(RELABEL_FIELD),
            *(label.get(RELABEL_FIELD) for label in version_labels(owner, version)),
        ]
        if relabel
    ]
    if notes:
        return Rights(rights.license_class, [*rights.reasons, *notes])
    return rights


def _stricter(a: Rights, b: Rights) -> Rights:
    """The more restrictive of two rights; on a tie, ``b`` (the recomputed one)."""
    order = LICENSE_CLASS_ORDER.index
    return a if order(a.license_class) < order(b.license_class) else b


def _label_version(
    library: Library,
    readers: Libraries,
    version: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None,
    relabel: Mapping[str, Any],
    floor: BlobFloor,
    note: str | None = None,
) -> bool:
    """Record a relabel of ``version``'s unchanged content on it; return whether one was written.

    The label holds the source, who and why, and the rights it gives the
    version — computed as the version a relabel publish would have minted
    (``previous`` the version, that source and relabel) would have them. Its
    key is a hash of all three, so repeating the same relabel with the same
    outcome writes nothing, and repeating it after another asset was labelled
    records the new outcome beside the old (append-only). The version's floor
    statements are then rebuilt, so what it says about its bytes reflects it.
    """
    ref = str(LibraryRef(version["asset"], version["version"], library.name))
    as_new = {
        "doc_kind": version.get("doc_kind"),
        "doc": version.get("doc"),
        "files": version.get("files") or {},
        "source": source,
        "derived_from": [],
        PREVIOUS_FIELD: ref,
        LINEAGE_FIELD: {ref: version["manifest_sha256"]},
        RELABEL_FIELD: dict(relabel),
    }
    rights = effective_rights(readers, as_new, floor=floor, owner=library)
    said = {
        "manifest": version["manifest_sha256"],
        "source": source,
        RELABEL_FIELD: dict(relabel),
        "rights": rights.to_dict(),
    }
    if (
        version.get(RELABEL_FIELD) == dict(relabel)
        and version.get("source") == source
        and stored_rights(library, version).to_dict() == said["rights"]
    ):
        return False  # the version itself already says exactly this
    key = label_key(version["asset"], version["version"], _label_id(said))
    if key in library.labels:
        return False
    try:
        library.labels[key] = {
            "kind": LABEL_KIND.name,
            "schema_version": LIBRARY_SCHEMA_VERSION,
            "asset": version["asset"],
            "version": version["version"],
            **said,
            "labelled": _now_precise(),
            "note": note,
        }
    except VersionExistsError:
        return False  # another publisher recorded the same label meanwhile
    _index_version(library, readers, version)
    return True


def _now_precise() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def unknown_advice(
    libraries: Libraries,
    version: Mapping[str, Any],
    *,
    owner: Library | None = None,
    floor: BlobFloor | None = _MACHINE,
) -> list[str]:
    """What would answer each ``unknown`` contributor of a version — one sentence per kind.

    The advice a refusal prints, so it names what works for THESE gaps
    (an#307): a gap of the asset's own chain takes a relabel; a gap of a
    version it derives from is labelled there; another asset's silence about
    bytes this version still holds is answered by labelling THAT asset (a
    relabel here cannot speak for another asset), or by dropping the file; and
    anything stated (a licence nobody recognises, an unverified stamp, a
    parent not on the path) relaxes only by a relicence.

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> r = publish(lib, "prop.vase", {"name": "vase"})
    >>> r.rights.license_class, "--relabel-by" in r.advice[0]
    ('unknown', True)
    """
    relabel, parents, others, stated = False, [], [], False
    for label, src in version_sources(libraries, version, floor=floor, owner=owner):
        if src is not None and license_class(src) != "unknown":
            continue
        remedy = getattr(label, "remedy", "")
        if remedy == REMEDY_RELABEL:
            relabel = True
        elif remedy.startswith(REMEDY_PARENT):
            parents.append(remedy[len(REMEDY_PARENT) :])
        elif remedy.startswith(REMEDY_OTHER):
            others.append(remedy[len(REMEDY_OTHER) :])
        else:
            stated = True
    out: list[str] = []
    if relabel:
        out.append(
            "To label what this asset's own versions never labelled, publish it "
            "again with --license … --provider … --relabel-by <who> "
            "--relabel-reason <why> (unchanged content makes no new version: the "
            "label is recorded on this one)."
        )
    for parent in dict.fromkeys(parents):
        out.append(
            f"It derives from {parent}, which nobody labelled: relabel {parent} "
            "itself, then publish this again."
        )
    if others:
        names = ", ".join(dict.fromkeys(others))
        out.append(
            f"Files it holds are held unlabelled by {names} too, and a relabel "
            "here cannot speak for another asset's files: relabel that asset, "
            "then repeat this relabel — or drop those files from this asset and "
            "publish it with the relabel (a file it no longer holds binds it no "
            "more)."
        )
    if stated:
        out.append(
            "The rest is a recorded statement (a licence nobody recognises, a "
            "stamp that pins other bytes, a parent not on the search path): fix "
            "the source it names, or relax it explicitly with --license … "
            "--provider … --relicense-by <who> --relicense-reason <why>."
        )
    return out


# --------------------------------------------------------------------------- publish


@dataclass(frozen=True)
class PublishResult:
    """What a publish did: the version it names, and whether it made one."""

    ref: LibraryRef
    manifest_sha256: str
    created: bool
    rights: Rights
    affordances: dict[str, dict[str, Any]]
    #: For an ``unknown`` result: what would answer each kind of gap, one
    #: sentence each (:func:`unknown_advice`).
    advice: tuple[str, ...] = ()
    #: The rights conflicts the version records (an#357): statements freer
    #: than what binds their bytes, kept beside the stricter one that binds.
    conflicts: tuple[RightsConflict, ...] = ()

    def __str__(self) -> str:
        what = "published" if self.created else "unchanged (the head already is this)"
        out = f"{what}: {self.ref} [{self.rights.license_class}] manifest {self.manifest_sha256[:12]}"
        if self.conflicts:
            out += f"\n{len(self.conflicts)} rights conflict(s), the stricter binds:"
            out += "".join(f"\n  {c}" for c in self.conflicts)
        return out


def _same_content(
    head: Mapping[str, Any],
    pending: Mapping[str, Any],
    hashes: Mapping[str, str],
    *,
    head_ref: str,
) -> bool:
    """Whether a publish holds exactly the head's content: descriptor, file
    bytes and ``derived_from`` — or exactly ``[head]``: a check-out of the
    head, published back unedited, derives from the head, and its content is
    the head's."""
    if head.get("doc") != pending["doc"] or _file_hashes(
        head.get("files") or {}
    ) != dict(hashes):
        return False
    parents = sorted(pending["derived_from"])
    return parents in (sorted(head.get("derived_from") or []), [head_ref])


def _same_as_head(
    head: Mapping[str, Any],
    pending: Mapping[str, Any],
    hashes: Mapping[str, str],
    *,
    head_ref: str,
) -> bool:
    """Whether a publish would repeat the head: the same content and statements.

    The same content (:func:`_same_content`), asset-level source, relicence,
    unlabelled files and per-file statements (adding a per-file label to
    unchanged content is a new statement, so a new version). A relabel the publish does not repeat is no difference:
    it was a statement about earlier gaps, which the head already makes.
    ``head`` is the head as its labels present it (:func:`labelled_view`).
    """
    return (
        _same_content(head, pending, hashes, head_ref=head_ref)
        and head.get("source") == pending["source"]
        and (head.get(RELICENSE_FIELD) or None)
        == (pending.get(RELICENSE_FIELD) or None)
        and (
            not pending.get(RELABEL_FIELD)
            or (head.get(RELABEL_FIELD) or None) == pending.get(RELABEL_FIELD)
        )
        and sorted(head.get(UNLABELLED_FIELD) or [])
        == sorted(pending.get(UNLABELLED_FIELD) or [])
        and head.get(FILE_SOURCES_FIELD) == pending.get(FILE_SOURCES_FIELD)
    )


def _apply_curation(
    record: dict[str, Any],
    *,
    title: str | None,
    family: str | None,
    style: str | Iterable[str] | None,
    origin: str | None,
    status: str | None,
    tags: str | Iterable[str] | None,
    replace_curation: bool,
) -> None:
    if title is not None:
        record["title"] = title
    if family is not None:
        record["family"] = family
    if status is not None:
        if record.get("status") != status:
            record.setdefault(STATUS_HISTORY_FIELD, []).append(
                {
                    "status": status,
                    "by": None,
                    "reason": "set by a publish",
                    "at": _now(),
                }
            )
        record["status"] = status
    if origin is not None:
        record["facets"]["origin"] = origin
    for name, values in (("style", style), ("tags", tags)):
        new = _as_list(values)
        if new is None and not (replace_curation and values is not None):
            continue
        bucket = record["facets"]["style"] if name == "style" else record["tags"]
        if replace_curation:
            bucket.clear()
        bucket.extend(v for v in (new or []) if v not in bucket)


def _given_file_sources(
    license_parts: Mapping[str, Any] | None,
    file_sources: Mapping[str, Any] | None,
    hashes: Mapping[str, str],
    *,
    source_doc: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """``{path: source}`` a publish states per file, each pinned to its file's digest.

    Refuses: ``license_parts`` with no asset-level source (the label every
    other file takes would be undefined), a path the asset does not store, and
    a source pinning other bytes. The same bytes given two classes are a
    rights conflict, not an error (an#357).
    """
    given: dict[str, Any] = {}
    if license_parts:
        if source_doc is None:
            raise LibraryError(
                "--license-part labels named files; the asset-level label every "
                "other file takes must be given too (--license and --provider)"
            )
        given.update(
            {
                path: src
                for path, (_, src) in match_license_parts(license_parts, hashes).items()
            }
        )
    for path, src in (file_sources or {}).items():
        if path not in hashes:
            raise LibraryError(
                f"file_sources names {path!r}, which the asset does not store"
            )
        given[path] = src
    out: dict[str, dict[str, Any]] = {}
    for path, src in sorted(given.items()):
        pinned = _source_dict(src) or {}
        digest = hashes[path]
        said = (pinned.get("sha256") or "").strip().lower().removeprefix("sha256:")
        if said and said != digest:
            raise LibraryError(
                f"the per-file source for {path!r} pins other bytes ({said[:12]}…) "
                f"than the file holds ({digest[:12]}…)"
            )
        out[path] = {**pinned, "sha256": digest}
    # The same bytes given two classes are not refused (an#357): the rule
    # states the stricter for both, and publish records the freer as a conflict.
    return out


def _carried_file_sources(
    head: Mapping[str, Any] | None,
    given: Mapping[str, dict[str, Any]],
    hashes: Mapping[str, str],
) -> tuple[dict[str, dict[str, Any]] | None, list[str]]:
    """``(file_sources, dropped)`` of a new version: the given ones over the head's carried ones.

    A head's statement is carried for its file while the bytes are unchanged
    (the carried-source rule); a file changed since is ``dropped`` — recorded
    ``unlabelled`` — and never re-pinned to its new bytes by path. ``None``:
    neither the head nor this publish states anything per file.
    """
    held = (head or {}).get(FILE_SOURCES_FIELD)
    if held is None and not given:
        return None, []
    out: dict[str, dict[str, Any]] = {}
    dropped: list[str] = []
    for path, raw in (held or {}).items():
        if path in given or path not in hashes or not isinstance(raw, Mapping):
            continue
        source = _source_model(raw)
        if source is not None and _digest_of(source) == hashes[path]:
            out[path] = dict(raw)
        else:
            dropped.append(path)
    out.update(given)
    return dict(sorted(out.items())), dropped


def _covered(
    readers: Libraries,
    pending: Mapping[str, Any],
    relicense: Mapping[str, Any],
    source_doc: Mapping[str, Any] | None,
    entries: Mapping[str, Mapping[str, Any]],
    hashes: Mapping[str, str],
) -> dict[str, Any]:
    """``relicense`` with the digests it covers: all but those a STRICTER per-file statement names.

    A relicence relaxes what it names. Bytes an earlier version of the lineage
    labelled stricter PER FILE, which this publish does not label per file
    itself, are not covered (review R1/R2 of an#345: a head moved to another
    path, or re-added later, is not freed by a relicence that never named it):
    they keep binding, and the relicence's claim about them is a rights
    conflict (an#357), never refused here.
    """
    order = LICENSE_CLASS_ORDER.index
    rel = _source_class(_source_model(source_doc))
    stricter = {
        hashes[path]
        for path, src in entries.items()
        if order(_source_class(_source_model(src))) < order(rel)
    }
    named = {hashes[path] for path in entries}
    rule = _PerFileRule(readers)
    for digest in sorted(set(hashes.values()) - named):
        prior = rule.per_file_lineage(pending, None, digest)
        if prior is not None and order(prior[0]) < order(rel):
            stricter.add(digest)
    return {
        **relicense,
        RELICENSE_COVERS: sorted(set(hashes.values()) - stricter),
    }


def _publish_conflicts(
    readers: Libraries, pending: Mapping[str, Any], *, strict: bool
) -> tuple[RightsConflict, ...]:
    """The rights conflicts a publish would record (an#357): warned, or refused under ``strict``.

    Inform, don't block: the freer statement is kept in the version, the
    stricter binds, and the conflict is stated beside it in the floor and
    wherever the asset is shown. ``strict`` (``--strict-assets``) refuses
    instead, before anything is written.
    """
    conflicts = tuple(_PerFileRule(readers).conflicts(pending, None))
    if not conflicts:
        return ()
    listed = "; ".join(map(str, conflicts))
    if strict:
        raise RightsRefusal(
            f"{len(conflicts)} rights conflict(s), refused under --strict-assets: "
            f"{listed}. Without it the stricter statement binds and the conflict "
            "is recorded; to relax deliberately, record a relicence "
            "(--relicense-by <who> --relicense-reason <why>, naming per-file "
            "parts that stay stricter with --license-part)"
        )
    warnings.warn(
        f"{len(conflicts)} rights conflict(s), recorded (the stricter statement "
        f"binds; a relicence resolves one deliberately): {listed}",
        RightsConflictWarning,
        stacklevel=3,
    )
    return conflicts


def publish(
    library: Library,
    asset_id: str,
    doc: Any,
    files: Mapping[str, bytes] | None = None,
    *,
    source: AssetSource | Mapping[str, Any] | None = None,
    relicense: Mapping[str, str] | None = None,
    relabel: Mapping[str, str] | None = None,
    derived_from: Iterable[str] = (),
    title: str | None = None,
    family: str | None = None,
    style: str | Iterable[str] | None = None,
    origin: str | None = None,
    status: str | None = None,
    tags: str | Iterable[str] | None = None,
    replace_curation: bool = False,
    note: str | None = None,
    expect_head: str | None = _ANY_HEAD,
    search: Libraries | None = None,
    carry_source: bool = True,
    license_parts: Mapping[str, AssetSource | Mapping[str, Any]] | None = None,
    file_sources: Mapping[str, AssetSource | Mapping[str, Any]] | None = None,
    strict_assets: bool = False,
) -> PublishResult:
    """Publish ``doc`` and its ``files`` as the next version of ``asset_id`` in ``library``.

    library: the owning library (writes never go to a search path)
    asset_id: ``<kind>.<slug>``; the kind must be registered
    doc: the descriptor — the existing document ``an`` already versions
        (``CharacterDescriptor``, …), as a model or its JSON dict, stored verbatim
    files: the asset's files, by the relative paths the descriptor uses
        (``parts/head.svg``) — stored once each in the content-addressed blobs
    source: provenance declared for the asset as a whole. It contributes BESIDE
        the descriptor's own ``source`` (the most restrictive wins), never
        instead of it. With no ``source``, and a descriptor declaring nothing
        or exactly what the head's declared, the source of the previous version
        carries forward (``carry_source``) — for the bytes it was declared on
        only: a file changed or added since is recorded as ``unlabelled`` on the
        version and is ``unknown``. Later versions inherit that gap through
        ``previous`` even when they pass ``source=``; ``relabel`` (or a
        relicence) answers it. With no source at all the version is ``unknown``
        — recorded and visible, not refused
    relicense: ``{"by": who, "reason": why}`` — the ONLY way to relax rights.
        Rights attach to the bytes and the lineage: a new version inherits the
        version it follows (``previous``), every version it derives from, and
        every version holding the same file bytes, and may only be more
        restrictive than they are — a cc0 in the descriptor or in ``source=``
        never relabels private art. A relicence makes ``source`` (required) the
        whole statement, records who and why on the version (and in its
        manifest and reasons), and covers these bytes for later versions
    relabel: ``{"by": who, "reason": why}`` beside an explicit ``source=``
        (required) — a first statement about bytes NOBODY labelled (an#263):
        the gaps of this asset's own version chain (files an earlier version
        recorded ``unlabelled``, files no person's source spoke for, an earlier
        version with no source at all) are answered with ``source``, and so is
        another asset's silence about a file the chain held once and this
        version no longer holds (an#307). It relaxes no statement anyone made:
        a private (or any) licence, a per-part source, a version this one
        derives from, and every other asset's statement about bytes this
        version holds still bind. On content that changed, recorded on the new
        version, in its manifest and in its reasons; on UNCHANGED content,
        recorded on the head in the append-only ``labels`` store
        (:func:`version_labels`) and no version is minted (an#307)
    derived_from: library references this version derives from (an earlier version,
        the original of a recolour); each must resolve, and its rights are inherited.
        A descriptor checked out of a library derives from its origin by default
    title, family, style, origin, status, tags: curation, stored on the record;
        given again with unchanged content they update the record and make no
        version. ``style`` and ``tags`` add to what is there, or replace it with
        ``replace_curation=True``
    note: what changed, stored on the version
    expect_head: guard against publishing into an asset you did not mean:
        ``None`` — the id must be new; ``"vNNN"`` — the head must be that version
    search: further libraries where ``derived_from`` references resolve (the
        owning library is always searched first)
    license_parts: ``{glob: source}`` — a per-file statement for every stored
        path a glob matches (:func:`match_license_parts`: ``*`` stays in one
        folder, ``**`` crosses folders, case-exact; a glob matching nothing,
        two globs disagreeing on a path, or a near miss refuse), each pinned
        to the file's digest (an#345). Needs an asset-level ``source`` (given
        or carried): the files no glob names are stated with the version's
        label computed WITHOUT these statements. A per-file statement never
        relaxes what the bytes already carry — the per-part source of the same
        file, the same bytes at another path, and every earlier statement of
        this asset's chain or of a version it derives from about them: a
        looser one is kept and recorded as a rights conflict, the stricter
        binding (an#357), unless ``relicense`` records who and why (the
        relicence then lists the digests it covers, and a per-file statement
        stricter than it keeps binding). At a later publish a statement is
        carried for its file while the bytes are unchanged; a file changed
        since is recorded ``unlabelled``
    file_sources: ``{path: source}`` — the same, by exact stored path (what a
        stored version holds; :func:`promote` passes it)
    strict_assets: refuse a publish that would record a rights conflict
        (:class:`RightsConflict`: a per-part or per-file statement freer than
        what binds its bytes) instead of recording it with a
        :class:`RightsConflictWarning` (an#357: inform, don't block, by default)

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> doc = {"name": "lamp", "source": {"provider": "me", "license": "cc0-1.0"}}
    >>> r = publish(lib, "prop.lamp", doc, {"parts/lamp.svg": b"<svg/>"}, style="reiniger")
    >>> str(r.ref), r.created, r.rights.license_class
    ('an:prop.lamp@v001', True, 'free')
    >>> publish(lib, "prop.lamp", doc, {"parts/lamp.svg": b"<svg/>"}).created
    False
    """
    check_asset_id(asset_id)
    kind = asset_kind_info(asset_kind(asset_id))
    if status is not None and status not in STATUSES:
        raise LibraryError(f"status {status!r} is not one of {list(STATUSES)}")
    if relicense is not None:
        relicense = {
            k: str(v).strip()
            for k, v in dict(relicense).items()
            if k != RELICENSE_COVERS  # recomputed for this version below
        }
        if not relicense.get("by") or not relicense.get("reason"):
            raise LibraryError(
                "a relicence records who and why: relicense={'by': …, 'reason': …} "
                "(--relicense-by, --relicense-reason)"
            )
        if source is None:
            raise LibraryError(
                "a relicence needs the source= it relicenses the asset under "
                "(--license and --provider)"
            )
    if relabel is not None:
        relabel = {k: str(v).strip() for k, v in dict(relabel).items()}
        if not relabel.get("by") or not relabel.get("reason"):
            raise LibraryError(
                "a label of unlabelled bytes records who and why: relabel={'by': …, "
                "'reason': …} (--relabel-by, --relabel-reason)"
            )
        if source is None:
            raise LibraryError(
                "a relabel needs the source= it labels the bytes with "
                "(--license and --provider)"
            )
        if relicense is not None:
            raise LibraryError(
                "relabel and relicense are exclusive: a relicence already replaces "
                "every statement the version inherits"
            )
    doc = _doc_dict(doc)
    origin_block = pop_origin(doc)
    derived = list(derived_from)
    if (
        not derived
        and isinstance(origin_block, Mapping)
        and origin_block.get("library")
    ):
        derived = [origin_block["library"]]
    readers = [library] + [
        lib
        for lib in (as_libraries(search) if search is not None else [])
        if lib.name != library.name
    ]
    pinned_parents: list[str] = []
    lineage: dict[str, str] = {}
    for parent in derived:
        try:
            _, pinned, parent_version = resolve(readers, parent)
        except (AssetNotFoundError, AssetIdError) as e:
            raise LibraryError(
                f"derived_from {parent!r} does not resolve: {e}. "
                "Pass search=… (CLI: --extra) with the library it is in."
            ) from e
        pinned_parents.append(str(pinned))
        lineage[str(pinned)] = parent_version["manifest_sha256"]

    existing = _read_record(library, asset_id) if asset_id in library.records else None
    if (existing or {}).get("status") in HIDDEN_STATUSES and status is None:
        raise LibraryError(
            f"{library.name}:{asset_id} is {existing['status']}: pick another id, or "
            "revive it by publishing with status=… (--status draft)"
        )
    head = (existing or {}).get("head")
    if expect_head is not _ANY_HEAD and head != expect_head:
        raise LibraryError(
            f"{library.name}:{asset_id} "
            + (f"already exists (head {head})" if head else "does not exist yet")
            + f", but this publish expected {'a new asset' if expect_head is None else expect_head}. "
            "Pick another id (a different asset sharing an id would be merged into it), "
            "or pass the head you mean to follow (expect_head=…, --expect-head)."
        )
    head_version = read_version(library, asset_id, head) if head else None
    # The head as the labels recorded on it since present it (an#307): a
    # relabel of unchanged content is recorded there, not as a new version.
    head_view = (
        labelled_view(head_version, version_labels(library, head_version))
        if head_version is not None
        else None
    )

    check_path_set(files or {})
    # Before anything is written: a library the machine registry does not know
    # is invisible to every other library's rights floor (an#249).
    register_library(library)
    blobs = library.blobs
    file_refs: dict[str, dict[str, Any]] = {}
    for path, data in sorted((files or {}).items()):
        rel = check_relpath(path)
        file_refs[rel] = blobs.add(bytes(data), name=rel).to_json()

    source_doc = _source_dict(source)
    if (
        source_doc is None
        and carry_source
        and head_view is not None
        and descriptor_source(doc, store=kind.credits_store)
        == descriptor_source(head_view.get("doc") or {}, store=kind.credits_store)
    ):
        # A source declared on an earlier publish carries forward — but only
        # where the descriptor says nothing new itself (nothing, or exactly
        # what the head's said, such as the factory's own stamp): a descriptor
        # that now declares another source is never masked by it.
        source_doc = head_view.get("source")
    hashes = _file_hashes(file_refs)
    parts_given = _given_file_sources(
        license_parts, file_sources, hashes, source_doc=source_doc
    )
    unlabelled: list[str] = []
    if source_doc is not None and source is None and head_view is not None:
        # The carried source was a statement about the bytes it was declared
        # on. A file changed or added since is bytes nobody has labelled: it
        # stays `unknown` (in the floor, in the rights, in the credits of a
        # check-out) until a publish passes `source=` again — unless the
        # descriptor itself labels those very bytes, a per-part source pinned
        # to their digest (the factory re-stamping the mouths it redrew:
        # an#281), which then speaks for them as it would on any publish.
        before = _file_hashes(head_view.get("files") or {})
        still = set(head_view.get(UNLABELLED_FIELD) or [])
        unlabelled = sorted(
            path
            for path, digest in hashes.items()
            if (before.get(path) != digest or path in still)
            and itemising_source({"doc": doc}, path, digest) is None
            and path not in parts_given
        )
    pending: dict[str, Any] = {
        "doc_kind": kind.name,
        "doc": doc,
        "source": source_doc,
        "derived_from": pinned_parents,
        "files": file_refs,
    }
    if head:
        pending[PREVIOUS_FIELD] = str(LibraryRef(asset_id, head, library.name))
        lineage[pending[PREVIOUS_FIELD]] = head_version["manifest_sha256"]
    if lineage:
        pending[LINEAGE_FIELD] = dict(sorted(lineage.items()))
    if relicense:
        pending[RELICENSE_FIELD] = relicense
    if relabel:
        pending[RELABEL_FIELD] = relabel
    entries, dropped = _carried_file_sources(head_view, parts_given, hashes)
    if entries is None and _PerFileRule(readers).applies(pending, None):
        # Under the rule through its lineage: recorded, so the version is
        # written at the schema an older reader refuses (review S1).
        entries = {}
    unlabelled = sorted({*unlabelled, *dropped})
    if unlabelled:
        pending[UNLABELLED_FIELD] = unlabelled
    if entries is not None:
        pending[FILE_SOURCES_FIELD] = entries
        if relicense:
            relicense = pending[RELICENSE_FIELD] = _covered(
                readers, pending, relicense, source_doc, entries, hashes
            )
    conflicts = _publish_conflicts(readers, pending, strict=strict_assets)
    floor = BlobFloor(readers)
    rights = effective_rights(readers, pending, floor=floor, owner=library)
    manifest = _manifest(
        doc,
        hashes,
        source_doc,
        pinned_parents,
        previous=pending.get(PREVIOUS_FIELD),
        relicense=relicense,
        relabel=relabel,
        unlabelled=unlabelled,
        lineage=pending.get(LINEAGE_FIELD),
        file_sources=pending.get(FILE_SOURCES_FIELD),
    )
    _load_genres()  # the analysers are the genres' (P7): never an empty facet by accident
    affordances, analysers = analyse(kind.name, doc, file_refs)
    publish_warning = service("library.publish_warning")
    message = publish_warning(kind.name, doc) if publish_warning is not None else None
    if message:
        warnings.warn(f"{asset_id} {message}", PlaceholderRigWarning, stacklevel=2)

    created = True
    label = head
    head_ref = str(LibraryRef(asset_id, head, library.name)) if head else ""
    if (
        relabel
        and head_version is not None
        and _same_content(head_version, pending, hashes, head_ref=head_ref)
        and pending.get(FILE_SOURCES_FIELD) != head_view.get(FILE_SOURCES_FIELD)
    ):
        raise LibraryError(
            "per-file labels on unchanged content are a new statement, not a "
            "relabel of a gap: publish them without --relabel-by/--relabel-reason "
            "(that records a new version), then relabel if a gap remains"
        )
    if (
        relabel
        and head_version is not None
        and _same_content(head_version, pending, hashes, head_ref=head_ref)
    ):
        # Relabelling unchanged content records the label on the head, in
        # the append-only labels store, and mints no version (an#307).
        created = False
        manifest = head_version["manifest_sha256"]
        _label_version(
            library,
            readers,
            head_version,
            source=source_doc,
            relabel=relabel,
            floor=floor,
            note=note,
        )
        rights = effective_rights(
            readers, head_version, floor=BlobFloor(readers), owner=library
        )
    elif head_view is not None and _same_as_head(
        head_view, pending, hashes, head_ref=head_ref
    ):
        created = False
        manifest = head_version["manifest_sha256"]
        rights = effective_rights(readers, head_version, floor=floor, owner=library)
    else:
        label = _write_version(
            library,
            asset_id,
            {
                "kind": VERSION_KIND.name,
                "schema_version": PER_FILE_SCHEMA_VERSION
                if FILE_SOURCES_FIELD in pending
                else LIBRARY_SCHEMA_VERSION,
                "asset": asset_id,
                **pending,
                "files": file_refs,
                "affordances": affordances,
                "analysers": analysers,
                "rights": rights.to_dict(),
                "art": _art_facet(file_refs),
                "manifest_sha256": manifest,
                "published": _now(),
                "note": note,
            },
        )
        _index_version(library, readers, read_version(library, asset_id, label))
    _save_record(
        library,
        asset_id,
        kind.name,
        label,
        dict(
            title=title,
            family=family,
            style=style,
            origin=origin,
            status=status,
            tags=tags,
            replace_curation=replace_curation,
        ),
    )
    return PublishResult(
        LibraryRef(asset_id, label, library.name),
        manifest,
        created,
        rights,
        affordances,
        advice=(
            tuple(
                unknown_advice(
                    readers,
                    read_version(library, asset_id, label),
                    owner=library,
                )
            )
            if rights.license_class == "unknown"
            else ()
        ),
        conflicts=conflicts,
    )


def _head_number(record: Mapping[str, Any] | None) -> int:
    head = (record or {}).get("head")
    return version_number(head) if head else 0


def _save_record(
    library: Library,
    asset_id: str,
    kind: str,
    label: str,
    curation: Mapping[str, Any],
) -> None:
    """Write the record with ``head`` never moving backwards, even under racing publishers.

    The record is re-read immediately before each write and ``head`` set to the
    newer of what is stored and ``label``; after writing, it is read back, and a
    concurrent writer that put an older head over ours is corrected.
    """
    for _ in range(MAX_PUBLISH_ATTEMPTS):
        current = (
            _read_record(library, asset_id) if asset_id in library.records else None
        )
        record = current or {
            "schema_version": LIBRARY_SCHEMA_VERSION,
            "id": asset_id,
            "kind": kind,
            "title": None,
            "family": None,
            "status": DFLT_STATUS,
            "facets": {"style": [], "origin": None},
            "tags": [],
            "created": _now(),
        }
        if version_number(label) > _head_number(current):
            record["head"] = label
        _apply_curation(record, **curation)
        record["updated"] = _now()
        library.records[asset_id] = record
        if _head_number(_read_record(library, asset_id)) >= version_number(label):
            return
    raise LibraryError(
        f"{library.name}:{asset_id}: could not record head {label} against concurrent "
        "publishers — retry"
    )


def set_status(
    library: Library,
    asset_id: str,
    status: str,
    *,
    by: str,
    reason: str,
) -> dict[str, Any]:
    """Set an asset's curation status, recording who and why; return the record.

    The record's ``status_history`` is appended to, never rewritten, and no
    version is touched: a project pinned to one keeps reading it.

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> _ = publish(lib, "prop.lamp", {"name": "lamp"})
    >>> set_status(lib, "prop.lamp", "approved", by="me", reason="looks right")["status"]
    'approved'
    """
    check_asset_id(asset_id)
    if status not in STATUSES:
        raise LibraryError(f"status {status!r} is not one of {list(STATUSES)}")
    by, reason = str(by or "").strip(), str(reason or "").strip()
    if not by or not reason:
        raise LibraryError(
            "a status change records who and why: by=…, reason=… (--by, --reason)"
        )
    if asset_id not in library.records:
        raise AssetNotFoundError(f"{library.name}:{asset_id} is not in the library")
    record = _read_record(library, asset_id)
    record.setdefault(STATUS_HISTORY_FIELD, []).append(
        {"status": status, "by": by, "reason": reason, "at": _now()}
    )
    record["status"] = status
    record["updated"] = _now()
    library.records[asset_id] = record
    return record


def retire(library: Library, asset_id: str, *, by: str, reason: str) -> dict[str, Any]:
    """Retire an asset id: recorded, hidden from ``find`` by default, never deleted.

    Its versions stay readable — a project pinned to one still checks it out
    and validates — and its rights statements still bind the floor (retiring
    is curation, not a relabel). ``find(status="retired")`` lists it; a publish
    into it is refused unless it passes ``status=`` to revive it.

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> _ = publish(lib, "prop.dead", {"name": "dead"})
    >>> _ = retire(lib, "prop.dead", by="me", reason="superseded")
    >>> len(find(lib)), [h.asset_id for h in find(lib, status="retired")]
    (0, ['prop.dead'])
    """
    return set_status(library, asset_id, "retired", by=by, reason=reason)


def _write_version(library: Library, asset_id: str, version: dict[str, Any]) -> str:
    """Write ``version`` under the next free label; another publisher's label is skipped.

    The versions store's create is exclusive on the folder backend, so two
    publishers racing for ``v002`` cannot both get it: the loser retries on the
    next label instead of being told a version it does not hold.
    """
    for _ in range(MAX_PUBLISH_ATTEMPTS):
        labels = versions_of(library, asset_id)
        label = version_label(version_number(labels[-1]) + 1 if labels else 1)
        try:
            library.versions[version_key(asset_id, label)] = {
                **version,
                "version": label,
            }
        except VersionExistsError:
            continue
        return label
    raise LibraryError(
        f"could not claim a version label for {asset_id} after {MAX_PUBLISH_ATTEMPTS} "
        "attempts; another process keeps publishing it — retry"
    )


def _read_folder(
    folder: Path, *, skip: str | None, named: frozenset[str] = frozenset()
) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        if not path.is_file() or rel == skip or is_clutter(rel, named):
            continue
        out[rel] = path.read_bytes()
    return out


def publish_dir(
    library: Library, folder: str | os.PathLike, asset_id: str, **kwargs: Any
) -> PublishResult:
    """Publish an asset folder as it sits in a project store (``assets/characters/alice/``).

    The descriptor is the kind's descriptor file (``character.json``); every other
    file under the folder is published as one of the asset's files, so a
    check-out reproduces the folder — except operating-system clutter
    (``.DS_Store``, hidden files, ``Thumbs.db``: :func:`an.stores._common.is_os_junk`)
    that the descriptor does not name — a part it names is published whatever
    its file is called (review-288 S2). Keyword arguments go to :func:`publish`.
    """
    folder = Path(folder)
    kind = asset_kind_info(asset_kind(check_asset_id(asset_id)))
    if kind.descriptor is None:
        raise LibraryError(
            f"a {kind.name} is one JSON document, not a folder; call publish() with the document"
        )
    descriptor = folder / kind.descriptor
    if not descriptor.is_file():
        raise LibraryError(
            f"{folder} has no {kind.descriptor}; is it a {kind.name} folder?"
        )
    doc = json.loads(descriptor.read_text(encoding="utf-8"))
    return publish(
        library,
        asset_id,
        doc,
        _read_folder(folder, skip=kind.descriptor, named=referenced_paths(doc)),
        **kwargs,
    )


# --------------------------------------------------------------------------- find


@dataclass(frozen=True)
class IndexEntry:
    """One asset's head version, as the index sees it."""

    library: str
    asset_id: str
    version: str
    kind: str
    record: Mapping[str, Any]
    rights: Rights
    affordances: Mapping[str, Mapping[str, Any]]
    art: str
    document: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def facet_values(self) -> dict[str, set[str]]:
        """Every facet's values for this entry (the AND/OR matcher's input)."""
        facets = self.record.get("facets") or {}
        return {
            "kind": {self.kind},
            "style": set(facets.get("style") or ()),
            "family": {self.record["family"]} if self.record.get("family") else set(),
            "origin": {facets["origin"]} if facets.get("origin") else set(),
            "status": {self.record.get("status") or DFLT_STATUS},
            "tags": set(self.record.get("tags") or ()),
            "license_class": {self.rights.license_class},
            "art": {self.art},
        }

    def affordance_terms(self) -> set[str]:
        """Every query term this entry satisfies: ``cap`` and each ``cap:key``."""
        out: set[str] = set()
        for cap, params in self.affordances.items():
            out.add(cap)
            out.update(f"{cap}{KEY_SEP}{k}" for k in (params or {}).get(KEYS_PARAM, ()))
        return out


#: The index seam: ``Library -> entries``. v1 scans the JSON; SQLite FTS or an
#: embedding index replaces it without changing ``find`` (design §6).
Index = Callable[[Library], Iterable[IndexEntry]]


def scan_index(library: Library) -> Iterator[IndexEntry]:
    """Every asset's head version in ``library``, read from the stores.

    Affordances snapshotted by an older analyser are recomputed, not trusted. A
    record or version that cannot be read (a damaged file) is skipped with a
    :class:`LibraryIndexWarning` naming it, so one bad entry never blinds every
    search.
    """
    _load_genres()
    for asset_id in library.records:
        try:
            record = _read_record(library, asset_id)
            head = record.get("head")
            if not head:
                continue
            version = read_version(library, asset_id, head)
        except Exception as e:  # noqa: BLE001 — reported, never silent
            warnings.warn(
                f"{library.name}:{asset_id} could not be read ({type(e).__name__}: {e}); "
                "it is missing from this search",
                LibraryIndexWarning,
                stacklevel=2,
            )
            continue
        kind = record.get("kind") or asset_kind(asset_id)
        affordances = current_affordances(
            kind,
            version.get("doc") or {},
            version.get("files") or {},
            stored=version.get("affordances"),
            stored_analysers=version.get("analysers"),
        )
        yield IndexEntry(
            library.name,
            asset_id,
            head,
            kind,
            record,
            stored_rights(library, version),
            affordances,
            version.get("art") or _art_facet(version.get("files") or {}),
            version,
        )


@dataclass(frozen=True)
class Hit:
    """One asset that answers a query — or nearly does (``missing`` non-empty)."""

    library: str
    asset_id: str
    version: str
    score: float
    title: str | None = None
    license_class: str = "unknown"
    missing: list[str] = field(default_factory=list)
    remedies: dict[str, str] = field(default_factory=dict)
    federated: bool = False

    @property
    def ref(self) -> str:
        """The reference to pin: namespaced when the search spanned several libraries."""
        return str(
            LibraryRef(
                self.asset_id, self.version, self.library if self.federated else None
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """A JSON-ready view (CLI ``--json``, MCP)."""
        return {
            "ref": self.ref,
            "library": self.library,
            "asset_id": self.asset_id,
            "version": self.version,
            "score": self.score,
            "title": self.title,
            "license_class": self.license_class,
            "missing": list(self.missing),
            "remedies": dict(self.remedies),
        }


@dataclass(frozen=True)
class FindResult:
    """Hits, near misses (with ``near=True``), and per-facet value counts over the hits."""

    hits: list[Hit]
    near: list[Hit]
    counts: dict[str, dict[str, int]]

    def __iter__(self) -> Iterator[Hit]:
        return iter(self.hits)

    def __len__(self) -> int:
        return len(self.hits)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-ready view."""
        return {
            "hits": [h.to_dict() for h in self.hits],
            "near": [h.to_dict() for h in self.near],
            "counts": self.counts,
        }


def _rights_filter(rights: str | Iterable[str] | None) -> set[str] | None:
    values = _as_list(rights)
    if values is None or values == [RIGHTS_ANY]:
        return None
    out: set[str] = set()
    for v in values:
        if v == RIGHTS_PUBLISHABLE:
            out |= set(PUBLISHABLE_CLASSES)
        elif v == RIGHTS_COMMERCIAL:
            out |= set(COMMERCIAL_CLASSES)
        elif v in LICENSE_CLASS_ORDER:
            out.add(v)
        else:
            raise LibraryError(
                f"rights={v!r} is not {RIGHTS_ANY!r}, {RIGHTS_PUBLISHABLE!r}, "
                f"{RIGHTS_COMMERCIAL!r} or a "
                f"licence class {list(LICENSE_CLASS_ORDER)}"
            )
    return out


def _load_genres() -> None:
    """Register the installed genres, whose analysers and capabilities the library reads.

    Explicit discovery (ADR 0001 decision 3) at the library's entry points, as
    ``an.load(project)`` and the CLI do: the character analyser is the cut-out
    genre's (P7), so a library used from a plain script must load it, or every
    facet would come back empty. Idempotent and cheap after the first call.
    """
    from an.genres import load
    from an.stage.props import register_prop_analyser  # the stage's rig kind (an#340)

    load()
    register_prop_analyser()


def _check_capability_terms(terms: Iterable[str]) -> None:
    """Refuse a capability name nobody registered: a typo must not read as "no asset"."""
    if terms:
        _load_genres()
    for term in terms:
        name, _ = capability_of(term)
        if name not in CAPABILITIES:
            close = difflib.get_close_matches(name, CAPABILITIES, n=CLOSE_MATCHES)
            raise LibraryError(
                f"{name!r} is not a registered capability"
                + (f"; did you mean {', '.join(close)}?" if close else "")
                + f" Known: {sorted(CAPABILITIES)} (see vocabulary())."
            )


def _counts(entries: Iterable[IndexEntry]) -> dict[str, dict[str, int]]:
    counters: dict[str, Counter] = {}
    for entry in entries:
        for facet, values in entry.facet_values().items():
            counters.setdefault(facet, Counter()).update(values)
        counters.setdefault("affords", Counter()).update(entry.affordance_terms())
    return {facet: dict(sorted(c.items())) for facet, c in sorted(counters.items())}


#: How a style mismatch is named among a near miss's ``missing`` terms.
STYLE_GAP_PREFIX: str = "style:"


def _recolourable(entry: IndexEntry) -> bool:
    """Whether a scene's StylePack can recolour this asset: a character whose
    descriptor tags its colours by role (every ``an character new --offline``
    character). Hand-drawn art keeps its colours, so no style reaches it."""
    doc = (entry.document or {}).get("doc") or {}
    return entry.kind == "character" and bool(doc.get("colour_roles"))


def _restyle_remedy(wanted: Iterable[str], has: Iterable[str]) -> str:
    want = " or ".join(wanted)
    now = ", ".join(sorted(has)) or "no style"
    return (
        f"no command restyles a published asset (it is curated as {now}). Its "
        f"colours are role-tagged, so the {want} style's StylePack recolours it at "
        "render: save the pack and set `style_pack:` in the scene's meta (the "
        "an-style skill, step 3). That changes colours only, never the build, "
        f"head or shapes; if {want} needs another build, make a character for it "
        "(`an character new <name> --offline --build …`) and publish it with "
        f"--style {want} in the same --family"
    )


def find(
    libraries: Libraries,
    *,
    kind: str | Iterable[str] | None = None,
    style: str | Iterable[str] | None = None,
    affords: str | Iterable[str] | None = None,
    rights: str | Iterable[str] | None = RIGHTS_ANY,
    family: str | Iterable[str] | None = None,
    origin: str | Iterable[str] | None = None,
    status: str | Iterable[str] | None = None,
    tags: str | Iterable[str] | None = None,
    art: str | Iterable[str] | None = None,
    near: bool = False,
    index: Index = scan_index,
) -> FindResult:
    """Assets matching every facet given (AND across facets, OR within one facet's values).

    affords: capabilities the asset must ALL have — ``limbs.legs``, or
        ``swap.view:side`` for a capability with a given key. Each capability is
        its own boolean facet, so a list of them is AND, as across facets. An
        unregistered name raises, naming the close ones
    rights: ``any`` (default — study renders are legitimate), ``publishable``
        (``free`` + ``attribution`` + ``noncommercial``), ``commercial``
        (``free`` + ``attribution``: what a commercial video may use, an#373),
        or licence classes. Rights are recomputed
        from each version's sources and lineage, not read from its cache
    status: curation statuses; an asset whose status is hidden
        (:data:`HIDDEN_STATUSES`: ``retired``) is offered only when its status
        is asked for by name
    near: also return assets that pass every other facet but miss some
        capabilities, or are curated for another style than asked, each with
        what is missing and the remedy that would add it (a style mismatch is
        listed as ``style:<wanted>``, remedied by restyling: an#271)
    index: the index to read (default: a scan of the stores)

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> _ = publish(lib, "prop.lamp", {"name": "lamp"}, style=["reiniger", "gilliam"])
    >>> [h.ref for h in find(lib, kind="prop", style="gilliam")]
    ['prop.lamp@v001']
    >>> len(find(lib, kind="prop", rights="publishable"))  # no source: unknown
    0
    """
    asked = {
        "kind": _as_list(kind),
        "style": _as_list(style),
        "family": _as_list(family),
        "origin": _as_list(origin),
        "status": _as_list(status),
        "tags": _as_list(tags),
        "art": _as_list(art),
    }
    license_classes = _rights_filter(rights)
    wanted = _as_list(affords) or []
    _check_capability_terms(wanted)
    libs = as_libraries(libraries)
    federated = is_federated(libs)
    hits: list[tuple[int, Hit]] = []
    near_hits: list[tuple[int, Hit]] = []
    matched: list[IndexEntry] = []
    floor = BlobFloor(libs)
    hidden = HIDDEN_STATUSES - set(asked["status"] or ())
    for order, library, entry in _rated_entries(libs, index, floor):
        values = entry.facet_values()
        if values["status"] & hidden:
            continue
        failed = {
            f
            for f, want in asked.items()
            if want is not None and not (values[f] & set(want))
        }
        # Only the style differs: with near=True, a restyle away (an#271) —
        # offered only where a style pack reaches the art (an#307).
        restyle = near and failed == {"style"} and _recolourable(entry)
        if failed and not restyle:
            continue
        if license_classes is not None and not (
            values["license_class"] & license_classes
        ):
            continue
        gaps = missing(entry.affordances, wanted)
        remedies = {g: remedy_for(g) for g in gaps}
        if restyle:
            term = STYLE_GAP_PREFIX + "|".join(asked["style"] or [])
            gaps = [term, *gaps]
            remedies[term] = _restyle_remedy(asked["style"] or [], values["style"])
        if gaps and not near:
            continue
        asks = len(wanted) + (1 if asked["style"] else 0)
        score = (asks - len(gaps)) / asks if asks else 1.0
        hit = Hit(
            entry.library,
            entry.asset_id,
            entry.version,
            score,
            title=entry.record.get("title"),
            license_class=entry.rights.license_class,
            missing=gaps,
            remedies=remedies,
            federated=federated,
        )
        if gaps:
            near_hits.append((order, hit))
        else:
            hits.append((order, hit))
            matched.append(entry)

    def ordered(items: list[tuple[int, Hit]]) -> list[Hit]:
        return [
            h
            for _, h in sorted(
                items, key=lambda oh: (-oh[1].score, oh[0], oh[1].asset_id)
            )
        ]

    return FindResult(ordered(hits), ordered(near_hits), _counts(matched))


def _rated_entries(
    libs: list[Library], index: Index, floor: BlobFloor
) -> Iterator[tuple[int, Library, IndexEntry]]:
    """``(order, library, entry)`` for every indexed asset, its rights recomputed.

    The one place ``find`` and ``vocabulary`` read rights from, so the two
    never disagree (an#307): the stricter of the cached rights and the ones
    recomputed from the version's sources, lineage and bytes — the bytes'
    floor moves when another asset is published, the cache does not.
    """
    for order, library in enumerate(libs):
        readers = [library, *(lib for lib in libs if lib is not library)]
        for entry in index(library):
            if entry.document:
                recomputed = effective_rights(
                    readers, entry.document, floor=floor, owner=library
                )
                entry = replace(entry, rights=_stricter(entry.rights, recomputed))
            yield order, library, entry


def vocabulary(libraries: Libraries, *, index: Index = scan_index) -> dict[str, Any]:
    """Every facet with its values and counts, and the registered capabilities.

    What an agent reads to turn words into a typed query (spectrum (b)): "a
    Reiniger character who can walk in profile" → ``style=reiniger``,
    ``affords=["limbs.legs", "swap.view:side"]``. The counts are over what
    ``find`` offers by default — the same recomputed rights, and no asset of a
    hidden status (``retired``), whose numbers are under ``hidden``.

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> v = vocabulary(lib)
    >>> sorted(v)
    ['capabilities', 'facets', 'hidden', 'kinds', 'rights', 'statuses']
    >>> isinstance(v["capabilities"], (dict, list, tuple))
    True
    """
    libs = as_libraries(libraries)
    entries: list[IndexEntry] = []
    hidden: Counter = Counter()
    for _, _, entry in _rated_entries(libs, index, BlobFloor(libs)):
        status = entry.record.get("status") or DFLT_STATUS
        if status in HIDDEN_STATUSES:
            hidden[status] += 1
        else:
            entries.append(entry)
    counts = _counts(entries)
    caps_count = counts.get("affords", {})
    return {
        "facets": counts,
        "capabilities": {
            name: {
                "description": cap.description,
                "remedy": cap.remedy,
                "count": caps_count.get(name, 0),
            }
            for name, cap in sorted(CAPABILITIES.items())
            if cap.subject
            == "asset"  # an asset's facets; engine/env are not searchable
        },
        "kinds": sorted(ASSET_KINDS),
        "statuses": list(STATUSES),
        "hidden": dict(sorted(hidden.items())),
        "rights": [RIGHTS_ANY, RIGHTS_PUBLISHABLE, *LICENSE_CLASS_ORDER],
    }


def show(libraries: Libraries, ref: str | LibraryRef) -> dict[str, Any]:
    """The record, the resolved version, its recomputed rights and the list of versions.

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> _ = publish(lib, "prop.lamp", {"name": "lamp"}, title="A lamp")
    >>> s = show(lib, "prop.lamp")
    >>> s["ref"], s["record"]["title"], s["versions"]
    ('an:prop.lamp@v001', 'A lamp', ['v001'])
    """
    library, pinned, _ = resolve(libraries, ref)
    version = read_version(library, pinned.asset_id, pinned.version)
    stored = stored_rights(library, version)
    return {
        "ref": str(pinned),
        "library": library.name,
        "record": _read_record(library, pinned.asset_id),
        "version": version,
        "rights": _stricter(
            stored, effective_rights(libraries, version, owner=library)
        ).to_dict(),
        # Statements freer than what binds their bytes, kept beside it (an#357).
        CONFLICTS_KEY: [c.to_dict() for c in version_conflicts(libraries, version, owner=library)],
        "versions": versions_of(library, pinned.asset_id),
    }


def version_conflicts(
    libraries: Libraries, version: Mapping[str, Any], *, owner: Library | None = None
) -> list[RightsConflict]:
    """The rights conflicts ``version`` records (an#357): each statement it makes
    about a file that is freer than what binds those bytes.

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> private = {"provider": "a-film", "license": "all-rights-reserved-private-study"}
    >>> _ = publish(lib, "prop.lamp", {"name": "lamp"}, {"a.png": b"carved"}, source=private)
    >>> import warnings
    >>> with warnings.catch_warnings():
    ...     warnings.simplefilter("ignore")
    ...     r = publish(lib, "prop.lamp", {"name": "lamp"}, {"a.png": b"carved"},
    ...                 license_parts={"a.png": {"provider": "me", "license": "cc0-1.0"}})
    >>> [(c.path, c.claimed_class, c.binding_class)
    ...  for c in version_conflicts(lib, read_version(lib, "prop.lamp", "v002"), owner=lib)]
    [('a.png', 'free', 'private')]
    """
    return _PerFileRule(libraries).conflicts(version, owner)


# --------------------------------------------------------------------------- verified reads


def verified_files(library: Library, version: Mapping[str, Any]) -> dict[str, bytes]:
    """The version's files from the blobs — every path, byte and the manifest checked.

    A library on the search path may not be one this machine wrote (a team
    share, a seed library), so nothing it stores is trusted: a path that is not
    clean and relative, a missing blob, bytes that do not hash to their key, or
    a manifest that does not match the version's content raise
    :class:`IntegrityError`.
    """
    files = version.get("files") or {}
    out: dict[str, bytes] = {}
    try:
        check_path_set(files)
    except LibraryError as e:
        raise IntegrityError(
            f"{version.get('asset')}@{version.get('version')} stores colliding file paths: {e}"
        ) from None
    for path, raw in files.items():
        try:
            check_relpath(path)
        except LibraryError as e:
            raise IntegrityError(
                f"{version.get('asset')}@{version.get('version')} stores an unsafe file path: {e}"
            ) from None
        ref = ContentRef.from_json(raw)
        try:
            data = library.blobs[ref.item_id]
        except KeyError:
            raise IntegrityError(
                f"{version.get('asset')}@{version.get('version')}: the blob of {path} "
                f"({ref.item_id[:12]}…) is missing from the {library.name!r} library"
            ) from None
        if content_hash(data) != ref.item_id:
            raise IntegrityError(
                f"blob for {path} does not hash to {ref.item_id}; the library is damaged"
            )
        out[path] = data
    if version_manifest(version) != version.get("manifest_sha256"):
        raise IntegrityError(
            f"{version.get('asset')}@{version.get('version')}: manifest does not match its content"
        )
    return out


# --------------------------------------------------------------------------- promote


def _derives_from_asset(target: Library, asset_id: str, source: LibraryRef) -> bool:
    for label in versions_of(target, asset_id):
        for parent in read_version(target, asset_id, label).get("derived_from") or []:
            ref = parse_ref(parent)
            if ref.asset_id == source.asset_id and ref.namespace == source.namespace:
                return True
    return False


def promote(
    libraries: Libraries,
    ref: str | LibraryRef,
    *,
    to: Library | None = None,
    as_id: str | None = None,
    allow_restricted: bool = False,
) -> PublishResult:
    """Copy one version into another library — by default the core ``an`` library.

    An asset made in a genre's library and reused across genres is promoted to the
    core (plan §1 decision 7). The copy is a new version in the target, derived
    from the source version, with the record's curation carried over.

    - A ``private`` or ``unknown`` version is refused unless
      ``allow_restricted=True``: private-study material never leaves its library
      by default (ADR 0005 decision 10). The rights checked are recomputed from
      the version's sources and lineage, and the stricter of those and the
      stored ones wins.
    - If the target already has an asset with this id that does not derive from
      the one promoted (another character that happens to share the id), it is
      refused: promoting would make it a new version of an unrelated asset.
      ``as_id`` promotes under another id.
    """
    library, pinned, version = resolve(libraries, ref)
    target = to if to is not None else open_library(CORE_PACKAGE)
    if target.name == library.name:
        raise LibraryError(f"{pinned} is already in the {target.name!r} library")
    readers = [library, *(lib for lib in as_libraries(libraries) if lib is not library)]
    stored = stored_rights(library, version)
    rights = _stricter(stored, effective_rights(readers, version, owner=library))
    if not rights.publishable and not allow_restricted:
        raise RightsRefusal(
            f"{pinned} is {rights.license_class} ({'; '.join(rights.reasons) or 'no reasons recorded'}); "
            "it is not copied out of its library without allow_restricted=True "
            "(--allow-restricted)"
        )
    target_id = check_asset_id(as_id) if as_id else pinned.asset_id
    if asset_kind(target_id) != pinned.kind:
        raise LibraryError(f"as_id {target_id!r} must keep the kind {pinned.kind!r}")
    if target_id in target.records and not _derives_from_asset(
        target, target_id, pinned
    ):
        raise LibraryError(
            f"the {target.name!r} library already has {target_id}, and it is not a copy of "
            f"{library.name}:{pinned.asset_id}; promote under another id (as_id=…, --as-id)"
        )
    record = _read_record(library, pinned.asset_id)
    facets = record.get("facets") or {}
    # The source as the version's labels present it: what a relabel version
    # would have carried (an#307).
    labelled = labelled_view(version, version_labels(library, version))
    return publish(
        target,
        target_id,
        version["doc"],
        verified_files(library, version),
        source=labelled.get("source"),
        relicense=version.get(RELICENSE_FIELD),
        # No relabel: it was a statement about the SOURCE asset's chain, which
        # the copy inherits through derived_from; it says nothing about the
        # target's own earlier versions.
        derived_from=[str(pinned)],
        title=record.get("title"),
        family=record.get("family"),
        style=facets.get("style"),
        origin=facets.get("origin"),
        status=record.get("status"),
        tags=record.get("tags"),
        note=f"promoted from {pinned}",
        search=readers,
        carry_source=False,
        # The per-file statements travel with the bytes they were made about
        # (an#345): left behind, the copy would state its private parts free.
        file_sources=version.get(FILE_SOURCES_FIELD),
    )
