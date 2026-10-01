"""The library's verbs: ``publish``, ``find``, ``vocabulary``, ``show``, ``promote``.

Plain functions over :class:`~an.library.federation.Library` objects (pillar 8:
the functions are the API; the ``an library …`` CLI and, later, MCP are thin
projections of them). Writes take the one owning library; reads take a library
or a search path (:func:`~an.library.federation.search_path`). Check-out lives
in :mod:`an.library.checkout`.

The documents they write (ADR 0005 decision 4, design §4):

- a **record** per asset — identity and curation, mutable: ``id``, ``kind``,
  ``title``, ``family``, ``head``, ``status``, ``facets`` (``style``, ``origin``),
  ``tags``;
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
import unicodedata
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dol.content import ContentRef, content_hash

from an.ir.assets import PRIVATE_STUDY, PUBLIC_DOMAIN, AssetSource, license_class
from an.credits import is_generated_source
from an.ir.migrate import DocumentKind, migrate, omit_unset, register_kind
from an.library import character as _character
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
    PUBLISHABLE_CLASSES,
    Rights,
    RightsRefusal,
    descriptor_source,
    roll_up,
    sources_in,
)
from an.library.root import CORE_PACKAGE
from an.library.stores import VersionExistsError, canonical_json, version_key
from an.stores._common import is_os_junk

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
    "scan_index",
    "show",
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
        current_version=LIBRARY_SCHEMA_VERSION,
    )
)
#: Curation status vocabulary (design §5); a status is curation, so it lives on the record.
STATUSES: tuple[str, ...] = ("draft", "approved", "deprecated")
DFLT_STATUS: str = "draft"
#: The ``rights=`` filter values besides a licence class.
RIGHTS_ANY: str = "any"
RIGHTS_PUBLISHABLE: str = "publishable"
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
#: recorded as ``unlabelled``, an earlier version that recorded no source at
#: all — with that source. It is a first statement, not a relaxation: it answers
#: nothing anyone stated (a private or any other licence, a per-part source, a
#: version it derives from, another asset's statement about the same bytes).
RELABEL_FIELD: str = "relabel"
#: The version field pinning its lineage: ``{parent_ref: manifest_sha256}`` for
#: ``previous`` and every ``derived_from`` parent, as resolved at publish
#: (review-269 B1). A walk reads a parent only if it is still THAT version;
#: references alone are re-resolved by name, and a same-named library's other
#: ``x@v001`` would stand in for it.
LINEAGE_FIELD: str = "lineage"
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
        if isinstance(added, Mapping) and doc.get("source") == added.get("source"):
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
    describes other bytes and speaks for nothing. The descriptor's ``source_svg``
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
        if claim is not None and _digest_of(claim) == digest:
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
    from an.characters.factory import FACTORY_PROVIDER

    return FACTORY_PROVIDER in generated_by(digest)


#: ``version_sources(floor=…)`` default: read the floor from every library on the machine.
_MACHINE: Any = object()


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
            return library, LibraryRef(wanted.asset_id, wanted.version, library.name), version
    raise AssetNotFoundError(
        f"{ref} as pinned (manifest {pin[:12]}…) is in no library on the path"
    )


def version_sources(
    libraries: Libraries,
    version: Mapping[str, Any],
    *,
    floor: BlobFloor | None = _MACHINE,
    owner: Library | None = None,
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
    visits: list[tuple[str, Mapping[str, Any]]] = []

    def walk(
        version: Mapping[str, Any],
        holder: Library | None,
        prefix: str,
        answer_from_later: tuple[str, AssetSource | None] | None,
    ) -> bool:
        """Add one version's contributions and its lineage's; return whether it is verified."""
        relicense = version.get(RELICENSE_FIELD)
        if not relicense:  # a relicence replaces everything, its bytes' floor included
            visits.append((prefix, version))
        if relicense:
            out.append(
                (
                    f"{prefix}asset ({_relicense_note(relicense)})",
                    _source_model(version.get("source")),
                )
            )
            return _verify(version, holder, True)

        def gap(label: str, unanswered: str) -> tuple[str, AssetSource | None]:
            # Nobody ever said anything here: answered by a later version's
            # explicit, recorded label of this chain, else unknown.
            if answer_from_later is None:
                return (f"{label}{unanswered}", None)
            note, answer = answer_from_later
            return (f"{label} ({note})", answer)

        kind = ASSET_KINDS.get(version.get("doc_kind") or "")
        out.extend(
            gap(f"{prefix}{label}", "")
            if src is None and label == ASSET_SOURCE_LABEL
            else (f"{prefix}{label}", src)
            for label, src in sources_in(
                version.get("doc") or {},
                store=kind.credits_store if kind else None,
                source=_source_model(version.get("source")),
                files=_file_hashes(version.get("files") or {}),
            )
        )
        out.extend(
            gap(
                f"{prefix}{path}",
                " (changed since the carried source was declared; not labelled: "
                f"{LABEL_HINT})",
            )
            for path in version.get(UNLABELLED_FIELD) or []
        )
        relabel = version.get(RELABEL_FIELD)
        own_answer = (
            (_relabel_note(relabel), _source_model(version.get("source")))
            if relabel and version.get("source")
            else None
        )
        pins = version.get(LINEAGE_FIELD) or {}
        lineage = [
            (ref, f"previous version {ref}", own_answer or answer_from_later, True)
            for ref in [version.get(PREVIOUS_FIELD)]
            if ref
        ] + [(ref, ref, None, False) for ref in version.get("derived_from") or []]
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
            parent_ok = walk(parent_version, parent_holder, f"{prefix}{label} > ", answer)
            links_ok = links_ok and link_ok and parent_ok
        return _verify(version, holder, links_ok)

    def _verify(version: Mapping[str, Any], holder: Library | None, ok: bool) -> bool:
        if ok and holder is not None and version.get("manifest_sha256"):
            trusted.add((library_origin(holder), version["manifest_sha256"]))
        return ok

    root_ok = walk(version, owner, "", None)
    if floor is None:
        return out
    # The root's own statements, when its walk is verified, are this walk.
    own = (
        {(library_origin(owner), version["manifest_sha256"])}
        if root_ok and owner is not None and version.get("manifest_sha256")
        else set()
    )
    for prefix, walked in visits:
        for path, raw in sorted((walked.get("files") or {}).items()):
            digest = ContentRef.from_json(raw).item_id
            bound: dict[str, dict[str, Any]] = {}
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
                held = bound.get(key)
                if held is None or _stricter_statement(statement, held):
                    bound[key] = statement
            # Another asset's silence (`unknown`) about bytes the factory
            # provably drew is no statement against them (an#269).
            if any(st.get("class") == "unknown" for st in bound.values()) and (
                factory_drew(walked, path, digest)
            ):
                bound = {k: st for k, st in bound.items() if st.get("class") != "unknown"}
            for asset_key, statement in sorted(bound.items()):
                ref = f"{asset_key}@{statement.get('version')}"
                out.append(
                    (
                        f"{prefix}{path}: same bytes as {ref} ({statement.get('label')})",
                        _recorded_source(
                            Rights(statement.get("class", "unknown"), []), ref
                        ),
                    )
                )
    return out


def blob_statement(
    libraries: Libraries,
    version: Mapping[str, Any],
    path: str,
    digest: str,
    *,
    own_label: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """What ``version`` says about the bytes ``digest`` it holds at ``path`` (for the floor).

    own_label: the class of the version's own label, computed once by the
        caller for all its files (it is the same for every file the version
        does not itemise); default: computed here
    """
    relicense = version.get(RELICENSE_FIELD)
    itemised = None if relicense else itemising_source(version, path, digest)
    if relicense:
        cls = license_class(
            _source_model(version.get("source")) or AssetSource(provider="unknown")
        )
        if version.get("source") is None:
            cls = "unknown"
        label = _relicense_note(relicense)
    elif itemised is not None:
        cls, label = (
            license_class(itemised),
            f"{path} itemised as {itemised.license or 'no licence'}",
        )
    else:
        cls = (
            own_label()
            if own_label is not None
            else _own_label_class(libraries, version)
        )
        label = "the asset's own label"
    return {
        "version": version.get("version"),
        "number": version_number(version["version"]) if version.get("version") else 0,
        "class": cls,
        "label": label,
        "manifest": version.get("manifest_sha256"),
    }


def _own_label_class(libraries: Libraries, version: Mapping[str, Any]) -> str:
    """The class of what a version says about every file it does not itemise."""
    return roll_up(version_sources(libraries, version, floor=None)).license_class


def _version_statements(
    library: Library, readers: Libraries, version: Mapping[str, Any]
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """``(digest, asset_key, statement)`` for each file of ``version``.

    The version's own label is computed at most once (an#249 R4-N3): it walks
    the version's lineage, and it is the same for every un-itemised file.
    """
    asset_key = f"{library.name}:{version['asset']}"
    memo: list[str] = []

    def own_label() -> str:
        if not memo:
            memo.append(_own_label_class(readers, version))
        return memo[0]

    for path, raw in sorted((version.get("files") or {}).items()):
        digest = ContentRef.from_json(raw).item_id
        yield (
            digest,
            asset_key,
            blob_statement(readers, version, path, digest, own_label=own_label),
        )


def _index_version(
    library: Library, readers: Libraries, version: Mapping[str, Any]
) -> None:
    """Record what ``version`` says about each of its blobs: in ``library``'s floor
    index, and in the machine's memory (which outlives the library's root)."""
    said = list(_version_statements(library, readers, version))
    remember(library, said)
    for digest, asset_key, statement in said:
        record_statement(library.blob_rights, digest, asset_key, statement)


def reindex(library: Library, *, search: Libraries | None = None) -> int:
    """Rebuild ``library``'s floor index from its versions. Returns the number of blobs indexed.

    The index is derived data: rebuilding it is always safe, and the way to
    repair a library whose index was lost or written by an older ``an``. It also
    (re-)registers the library's root in the machine registry
    (:mod:`an.library.registry`), so a library made at a custom root before the
    registry existed becomes visible to every other library's rights floor.

    The new index is computed in full first, then written over the old one
    entry by entry, and only then are stale entries removed: a crash midway
    leaves old and new statements side by side, never an empty floor (an#249
    R4-N4).
    """
    register_library(library)
    readers = [
        library,
        *(
            lib
            for lib in (as_libraries(search) if search else [])
            if lib.name != library.name
        ),
    ]
    fresh: dict[str, dict[str, Any]] = {}
    for key in sorted(
        library.versions,
        key=lambda k: (k.split("@")[0], version_number(k.split("@")[1])),
    ):
        try:
            version = migrate(dict(library.versions[key]), kind=VERSION_KIND.name)
        except Exception:  # noqa: BLE001 — reported by scan_index; nothing to index
            continue
        said = list(_version_statements(library, readers, version))
        remember(library, said)
        for digest, asset_key, statement in said:
            record_statement(fresh, digest, asset_key, statement)
    store = library.blob_rights
    for digest, entries in fresh.items():
        store[digest] = entries
    for digest in [d for d in store if d not in fresh]:
        del store[digest]
    return len(fresh)


#: The licence code standing in for each class when only a recorded class is known.
_CLASS_LICENSE: dict[str, str | None] = {
    "private": PRIVATE_STUDY,
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
    relabel = version.get(RELABEL_FIELD)
    if relabel:
        return Rights(rights.license_class, [*rights.reasons, _relabel_note(relabel)])
    return rights


def _stricter(a: Rights, b: Rights) -> Rights:
    """The more restrictive of two rights; on a tie, ``b`` (the recomputed one)."""
    order = LICENSE_CLASS_ORDER.index
    return a if order(a.license_class) < order(b.license_class) else b


# --------------------------------------------------------------------------- publish


@dataclass(frozen=True)
class PublishResult:
    """What a publish did: the version it names, and whether it made one."""

    ref: LibraryRef
    manifest_sha256: str
    created: bool
    rights: Rights
    affordances: dict[str, dict[str, Any]]

    def __str__(self) -> str:
        what = "published" if self.created else "unchanged (the head already is this)"
        return f"{what}: {self.ref} [{self.rights.license_class}] manifest {self.manifest_sha256[:12]}"


def _same_as_head(
    head: Mapping[str, Any],
    pending: Mapping[str, Any],
    hashes: Mapping[str, str],
    *,
    head_ref: str,
) -> bool:
    """Whether a publish would repeat the head: the same content and statements.

    Same descriptor, file bytes, asset-level source and relicence, and the same
    ``derived_from`` — or exactly ``[head]``: a check-out of the head, published
    back unedited, derives from the head, and its content is the head's.
    """
    if (
        head.get("doc") != pending["doc"]
        or _file_hashes(head.get("files") or {}) != dict(hashes)
        or head.get("source") != pending["source"]
        or (head.get(RELICENSE_FIELD) or None) != (pending.get(RELICENSE_FIELD) or None)
        or (head.get(RELABEL_FIELD) or None) != (pending.get(RELABEL_FIELD) or None)
        or sorted(head.get(UNLABELLED_FIELD) or [])
        != sorted(pending.get(UNLABELLED_FIELD) or [])
    ):
        return False
    parents = sorted(pending["derived_from"])
    return parents in (sorted(head.get("derived_from") or []), [head_ref])


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
        recorded ``unlabelled``, an earlier version with no source at all) are
        answered with ``source``. It relaxes no statement anyone made: a private
        (or any) licence, a per-part source, a version this one derives from,
        and every other asset's statement about the same bytes still bind.
        Recorded on the version, in its manifest and in its reasons
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
        relicense = {k: str(v).strip() for k, v in dict(relicense).items()}
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
        and head_version is not None
        and descriptor_source(doc, store=kind.credits_store)
        == descriptor_source(head_version.get("doc") or {}, store=kind.credits_store)
    ):
        # A source declared on an earlier publish carries forward — but only
        # where the descriptor says nothing new itself (nothing, or exactly
        # what the head's said, such as the factory's own stamp): a descriptor
        # that now declares another source is never masked by it.
        source_doc = head_version.get("source")
    hashes = _file_hashes(file_refs)
    unlabelled: list[str] = []
    if source_doc is not None and source is None and head_version is not None:
        # The carried source was a statement about the bytes it was declared
        # on. A file changed or added since is bytes nobody has labelled: it
        # stays `unknown` (in the floor, in the rights, in the credits of a
        # check-out) until a publish passes `source=` again.
        before = _file_hashes(head_version.get("files") or {})
        still = set(head_version.get(UNLABELLED_FIELD) or [])
        unlabelled = sorted(
            path
            for path, digest in hashes.items()
            if before.get(path) != digest or path in still
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
    if unlabelled:
        pending[UNLABELLED_FIELD] = unlabelled
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
    )
    _load_genres()  # the analysers are the genres' (P7): never an empty facet by accident
    affordances, analysers = analyse(kind.name, doc, file_refs)
    if kind.name == "character" and _character.renders_as_placeholder(doc):
        warnings.warn(
            f"{asset_id} is neither a CharacterDescriptor nor a rig with 'parts': the "
            "compiler would draw only its placeholder stand-in (fatal under "
            "--strict-assets), so it affords nothing but its rest view",
            PlaceholderRigWarning,
            stacklevel=2,
        )

    created = True
    label = head
    if head_version is not None and _same_as_head(
        head_version,
        pending,
        hashes,
        head_ref=str(LibraryRef(asset_id, head, library.name)),
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
                "schema_version": LIBRARY_SCHEMA_VERSION,
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


def _read_folder(folder: Path, *, skip: str | None) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        if not path.is_file() or rel == skip or is_os_junk(rel):
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
    (``.DS_Store``, hidden files, ``Thumbs.db``: :func:`an.stores._common.is_os_junk`). Keyword arguments go to :func:`publish`.
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
        library, asset_id, doc, _read_folder(folder, skip=kind.descriptor), **kwargs
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
            Rights.from_dict(version.get("rights") or {}),
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
        elif v in LICENSE_CLASS_ORDER:
            out.add(v)
        else:
            raise LibraryError(
                f"rights={v!r} is not {RIGHTS_ANY!r}, {RIGHTS_PUBLISHABLE!r} or a "
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

    load()


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
        (``free`` + ``attribution``), or licence classes. Rights are recomputed
        from each version's sources and lineage, not read from its cache
    near: also return assets that pass every other facet but miss some
        capabilities, each with what is missing and the remedy that would add it
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
    for order, library in enumerate(libs):
        readers = [library, *(lib for lib in libs if lib is not library)]
        for entry in index(library):
            if entry.document:
                recomputed = effective_rights(
                    readers, entry.document, floor=floor, owner=library
                )
                entry = replace(entry, rights=_stricter(entry.rights, recomputed))
            values = entry.facet_values()
            if any(
                want is not None and not (values[f] & set(want))
                for f, want in asked.items()
            ):
                continue
            if license_classes is not None and not (
                values["license_class"] & license_classes
            ):
                continue
            gaps = missing(entry.affordances, wanted)
            if gaps and not near:
                continue
            score = (len(wanted) - len(gaps)) / len(wanted) if wanted else 1.0
            hit = Hit(
                entry.library,
                entry.asset_id,
                entry.version,
                score,
                title=entry.record.get("title"),
                license_class=entry.rights.license_class,
                missing=gaps,
                remedies={g: remedy_for(g) for g in gaps},
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


def vocabulary(libraries: Libraries, *, index: Index = scan_index) -> dict[str, Any]:
    """Every facet with its values and counts, and the registered capabilities.

    What an agent reads to turn words into a typed query (spectrum (b)): "a
    Reiniger character who can walk in profile" → ``style=reiniger``,
    ``affords=["limbs.legs", "swap.view:side"]``.

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> v = vocabulary(lib)
    >>> sorted(v)
    ['capabilities', 'facets', 'kinds', 'rights', 'statuses']
    >>> "limbs.legs" in v["capabilities"]
    True
    """
    entries = [e for lib in as_libraries(libraries) for e in index(lib)]
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
    stored = Rights.from_dict(version.get("rights") or {})
    return {
        "ref": str(pinned),
        "library": library.name,
        "record": _read_record(library, pinned.asset_id),
        "version": version,
        "rights": _stricter(
            stored, effective_rights(libraries, version, owner=library)
        ).to_dict(),
        "versions": versions_of(library, pinned.asset_id),
    }


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
    stored = Rights.from_dict(version.get("rights") or {})
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
    return publish(
        target,
        target_id,
        version["doc"],
        verified_files(library, version),
        source=version.get("source"),
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
    )
