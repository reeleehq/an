"""Check-out: materialise a library version into a project, carrying its rights with it.

The v1 resolution strategy (ADR 0005 decision 8). The descriptor and its files
land in the project's existing store layout (``assets/characters/<key>/``), so the
compiler, validator and renderer read the project as they always have. Three
things travel with the copy, because the project is where ``an credits`` and the
render-time private-study warning look:

- ``metadata.library_origin``: the pinned reference, the version's manifest,
  its recomputed ``rights``, and every source those rights depend on that the
  descriptor itself does not hold (the asset-level source, the sources of every
  version it derives from). ``an credits`` reads them
  (``an.credits._library_origin_credits``). For a version with an asset-level
  source it also records ``checked_out``: the descriptor's source as the
  check-out left it and the files' digests, so in the copy that label speaks
  only for the bytes it was declared on — a file edited or added since is
  UNVERIFIED in ``an credits``, as it is ``unknown`` when the copy is published
  back (an#264);
- the asset-level source, written into a descriptor that declares none (or
  only a generator's own source that owes nothing — the character factory's
  stamp, a free DiceBear style — which it then stands in for: an#281);
- the pin in ``assets.lock.json`` — the project mall's ``library_lock`` store,
  the single source of truth for which version a project holds (an#240).

One asymmetry, deliberate: a RELICENSED version's copy still carries the
descriptor's and the parts' own sources, so ``an credits`` in the project can
be stricter than the library — never looser.

The pin records provenance. It is not a cache key: a checked-out copy can be
edited after it is pinned. :func:`verify_checkout` says whether each pinned copy
is still byte-for-byte its version.
"""

from __future__ import annotations

import copy
import os
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dol.content import ContentRef, content_hash

from an.library.api import (
    METADATA_ADDED_FLAG,
    ORIGIN_KEY,
    SOURCE_ADDED_KEY,
    CheckoutError,
    IntegrityError,
    _stricter,
    labelled_view,
    pop_origin,
    stored_rights,
    verified_files,
    version_labels,
    version_sources,
)
from an.library.federation import (
    Libraries,
    Library,
    as_libraries,
    open_library,
    resolve,
)
from an.library.ids import SHA256_PREFIX, AssetIdError, LibraryRef, parse_ref
from an.library.kinds import KIT_KIND, asset_kind_info
from an.library.lock import ProjectLock, lock_key
from an.library.rights import (
    ASSET_SOURCE_LABEL,
    Rights,
    descriptor_source,
    roll_up,
    sources_in,
)
from an.credits import (
    CHECKED_OUT_KEY,
    checked_out_seal,
    gives_way_to_a_label,
    is_clutter,
    referenced_paths,
)
from an.library.root import LibraryLocationWarning, git_worktree_of

__all__ = [
    "CheckoutResult",
    "LibraryPinError",
    "LibraryPinWarning",
    "check_pins_before_render",
    "check_checkout",
    "check_pins",
    "checkout",
    "drift_findings",
    "pinned_libraries",
    "verify_checkout",
]

#: Kinds whose descriptor has a ``metadata`` dict to carry the origin block.
METADATA_KINDS: frozenset[str] = frozenset(
    {"character", "prop", "environment", "sound"}
)
#: A project-store key: one folder name.
_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class CheckoutResult:
    """Where a checked-out version landed in the project, and its pin."""

    ref: LibraryRef
    store: str
    key: str
    manifest_sha256: str
    files: int
    changed: bool
    rights: Rights

    def asset_ref(self, entity_id: str | None = None) -> Any:
        """An :class:`~an.ir.schema.AssetRef` casting this asset, pinned by ``library``."""
        from an.ir.schema import AssetRef

        return AssetRef(
            kind=self.ref.kind,
            id=entity_id or self.key,
            store=self.store,
            ref=self.key,
            library=str(self.ref),
        )

    def __str__(self) -> str:
        what = "checked out" if self.changed else "already checked out"
        return (
            f"{what}: {self.ref} -> {self.store}/{self.key} "
            f"({self.files} files) [{self.rights.license_class}]"
        )


def _entry_dir(store: Any, key: str) -> Path | None:
    meta = getattr(store, "META_NAME", None)
    if not hasattr(store, "sidecar_path") or meta is None:
        return None
    return Path(store.sidecar_path(key, meta)).parent


def drift(store: Any, key: str, version: Mapping[str, Any]) -> list[str]:
    """How the project's ``store[key]`` differs from ``version`` — empty when it is that version.

    The descriptor is compared with the check-out's additions removed; every
    file is compared by hash, and files the version does not have count too —
    except operating-system clutter (``.DS_Store``…), which publish skips too.
    """
    if key not in store:
        return ["missing from the project"]
    out: list[str] = []
    doc = copy.deepcopy(dict(store[key]))
    pop_origin(doc)
    if doc != version.get("doc"):
        out.append("descriptor edited")
    entry = _entry_dir(store, key)
    files = version.get("files") or {}
    if entry is None:
        return out + (["files expected, but the store keeps none"] if files else [])
    meta = getattr(store, "META_NAME", "")
    named = referenced_paths(doc) | referenced_paths(version.get("doc") or {})
    on_disk = {
        rel
        for p in entry.rglob("*")
        if p.is_file()
        and (rel := p.relative_to(entry).as_posix()) != meta
        and not is_clutter(rel, named)
    }
    for path, raw in sorted(files.items()):
        target = entry.joinpath(*path.split("/"))
        if path not in on_disk:
            out.append(f"{path} missing")
        elif content_hash(target.read_bytes()) != ContentRef.from_json(raw).item_id:
            out.append(f"{path} edited")
    out += [f"{path} added" for path in sorted(on_disk - set(files))]
    return out


def _origin_block(
    pinned: LibraryRef,
    version: Mapping[str, Any],
    contributors: list[tuple[str, Any]],
    rights: Rights,
    visible: set[str],
) -> dict[str, Any]:
    return {
        "library": str(pinned),
        "manifest_sha256": version["manifest_sha256"],
        "rights": rights.to_dict(),
        "sources": [
            {
                "label": label,
                "source": source.model_dump(mode="json", exclude_defaults=True)
                if source is not None
                else None,
            }
            for label, source in contributors
            if label not in visible
        ],
    }


def checkout(
    libraries: Libraries,
    project_dir: str | os.PathLike,
    ref: str | LibraryRef,
    *,
    key: str | None = None,
    mall: Mapping[str, Any] | None = None,
    lock: Any | None = None,
    overwrite: bool = False,
) -> CheckoutResult:
    """Materialise a library version into a project, carry its rights, pin it.

    project_dir: the project to check out into
    ref: ``[<library>:]<asset_id>[@<version>]``; ``latest`` (or no version) is
        resolved now and pinned
    key: the key in the project store (default: the asset id's slug)
    mall: the project mall (default: ``build_project_mall(project_dir)``)
    lock: the lockfile mapping (default: the mall's ``library_lock`` store,
        ``<project_dir>/assets.lock.json``)
    overwrite: replace an existing entry that is not exactly this version — a
        local fork (any edited file or descriptor) or another asset; without it
        that is refused

    An entry that already IS this version byte for byte — the folder a
    ``publish`` just sent to the library, still unedited — is recognised and
    linked (origin block, carried source, pin) without ``overwrite``: publishing
    a project's asset and checking it back out is the natural first round trip.

    Every stored path, blob and the manifest are verified before anything is
    written, and every file is written inside the entry's folder or not at all.
    Editing the checked-out copy forks it; ``publish`` of the edited folder
    sends it back as a new version derived from this one.
    """
    from an.stores import build_project_mall

    if key is not None and not _KEY_RE.fullmatch(key):
        raise CheckoutError(
            f"key {key!r} must be one folder name (letters, digits, '.', '_', '-')"
        )
    library, pinned, version = resolve(libraries, ref)
    kind = asset_kind_info(pinned.kind)
    if kind.name == KIT_KIND:
        raise CheckoutError(
            f"{pinned} is a kit: a set of assets, not an asset with files of its own. "
            "Check it out with checkout_kit() (an library checkout does, for a kit)"
        )
    if kind.store is None:
        raise CheckoutError(
            f"a {kind.name} has no project store to check out into (yet)"
        )
    files = verified_files(library, version)
    readers = [library, *(lib for lib in as_libraries(libraries) if lib is not library)]
    contributors = version_sources(readers, version, owner=library)
    rights = _stricter(stored_rights(library, version), roll_up(contributors))
    # What the copy carries is the version as its labels present it (an#307):
    # the source a relabel of its unchanged content recorded on it.
    labelled = labelled_view(version, version_labels(library, version))
    manifest = version["manifest_sha256"]
    mall = mall if mall is not None else build_project_mall(project_dir, ensure=True)
    store = mall[kind.store]
    lock = _project_lock(lock, mall, project_dir)
    key = (
        key
        or _unedited_copy(store, lock, kind.store, pinned, version)
        or (pinned.asset_id.split(".", 1)[1])
    )
    entry_key = lock_key(kind.store, key)
    if key in store:
        existing = store[key]
        origin = (
            (existing.get("metadata") or {}) if isinstance(existing, Mapping) else {}
        ).get(ORIGIN_KEY) or {}
        same_version = origin.get("library") == str(pinned) or (
            lock.get(entry_key, {}) if entry_key in lock else {}
        ).get("library") == str(pinned)
        differences = drift(store, key, version)
        # A copy checked out by an older `an` lacks the record of which bytes
        # its carried label speaks for (an#264): an unedited one is re-linked.
        # Only a kind whose descriptor carries the origin block can be outdated:
        # a style or a voice never records one, and is never re-linked for it.
        outdated = (
            kind.name in METADATA_KINDS
            and bool(labelled.get("source"))
            and CHECKED_OUT_KEY not in origin
        )
        if same_version and not differences and not overwrite and not outdated:
            if entry_key not in lock:
                lock[entry_key] = _pin(pinned, manifest)
            return CheckoutResult(
                pinned, kind.store, key, manifest, len(files), False, rights
            )
        # The entry is byte-for-byte this version but was never linked to it: the
        # folder a publish just sent to the library. Linking it rewrites the same
        # bytes, so it needs no overwrite.
        linking = not differences and (not same_version or outdated)
        if not overwrite and not linking:
            raise CheckoutError(
                _fork_refusal(kind.store, key, pinned, same_version, differences)
            )
        del store[key]
    if files and not hasattr(store, "sidecar_path"):
        raise CheckoutError(
            f"the project's {kind.store!r} store keeps no files beside its documents, "
            f"so the {len(files)} files of {pinned} have nowhere to go"
        )
    if rights.license_class == "private":
        repo = git_worktree_of(project_dir)
        if repo is not None:
            warnings.warn(
                f"checking private-study material ({pinned}) out into {project_dir}, "
                f"inside the git work tree {repo}: never commit it",
                LibraryLocationWarning,
                stacklevel=2,
            )
    if files:
        entry = Path(store.sidecar_path(key, "_")).parent.resolve()
        targets = {}
        for path in files:
            target = Path(store.sidecar_path(key, path))
            if not target.resolve().is_relative_to(entry):
                raise IntegrityError(
                    f"{pinned}: file {path!r} would land outside {entry}"
                )
            targets[path] = target
        for path, data in sorted(files.items()):
            targets[path].parent.mkdir(parents=True, exist_ok=True)
            targets[path].write_bytes(data)
    doc = copy.deepcopy(version["doc"])
    if kind.name in METADATA_KINDS and isinstance(doc, dict):
        added = None
        if labelled.get("source") and (
            descriptor_source(doc, store=kind.credits_store) is None
            or gives_way_to_a_label(doc.get("source"))
        ):
            # The asset-level source speaks for every file nothing itemises; the
            # generator's descriptor source speaks only for the bytes its part
            # stamps pin, so it gives way (and comes back on a re-publish).
            added = {
                "source": copy.deepcopy(labelled["source"]),
                "had_key": "source" in doc,
                "previous": doc.get("source"),
            }
            doc["source"] = copy.deepcopy(labelled["source"])
        # What the project's own credits walk will see in the written descriptor;
        # every other contributor is recorded in the origin block.
        visible = {
            label
            for label, _ in sources_in(
                doc,
                store=kind.credits_store,
                files={
                    path: ContentRef.from_json(raw).item_id
                    for path, raw in (version.get("files") or {}).items()
                },
            )
            if label != ASSET_SOURCE_LABEL
        }
        if added is not None:
            visible.add(ASSET_SOURCE_LABEL)
        origin = _origin_block(pinned, version, contributors, rights, visible)
        if added is not None:
            origin[SOURCE_ADDED_KEY] = added
        if labelled.get("source"):
            # The version's asset-level label was declared on these bytes, and
            # a publish of the copy carries it for them only: `an credits` in
            # the project reads it the same way (an#264).
            digests = {
                path: ContentRef.from_json(raw).item_id
                for path, raw in sorted((version.get("files") or {}).items())
            }
            origin[CHECKED_OUT_KEY] = {
                "source": copy.deepcopy(doc.get("source")),
                "files": digests,
                "seal": checked_out_seal(doc.get("source"), digests),
            }
        if not isinstance(doc.get("metadata"), dict):
            doc["metadata"] = {}
            origin[METADATA_ADDED_FLAG] = True
        doc["metadata"][ORIGIN_KEY] = origin
    store[key] = doc
    lock[entry_key] = _pin(pinned, manifest)
    return CheckoutResult(pinned, kind.store, key, manifest, len(files), True, rights)


def _fork_refusal(
    store_name: str,
    key: str,
    pinned: LibraryRef,
    same_version: bool,
    differences: list[str],
) -> str:
    """The refusal when a project entry is a fork (or another asset) and no overwrite was asked."""
    what = (
        f"a fork of it ({', '.join(differences)})"
        if same_version
        else f"a local fork or another asset ({', '.join(differences)})"
    )
    return (
        f"the project already has {store_name}/{key}, and it is not {pinned} "
        f"as published: it is {what}. Replace it with overwrite=True "
        "(--overwrite), or check out beside it with key=… (--key …)"
    )


def check_checkout(
    libraries: Libraries,
    ref: str | LibraryRef,
    *,
    key: str | None = None,
    mall: Mapping[str, Any],
    lock: Any,
    overwrite: bool = False,
) -> LibraryRef:
    """Raise :class:`CheckoutError` if :func:`checkout` of ``ref`` would refuse; write nothing.

    Resolves the version, verifies its stored files, and applies the refusals
    ``checkout`` makes about the project (a key that is not a folder name, a kind
    with no store, a store that keeps no files, an entry that is a fork) — so a
    caller about to check out several assets (a kit) learns of the one that will
    fail before the first is written. Returns the pinned reference.
    """
    if key is not None and not _KEY_RE.fullmatch(key):
        raise CheckoutError(
            f"key {key!r} must be one folder name (letters, digits, '.', '_', '-')"
        )
    library, pinned, version = resolve(libraries, ref)
    kind = asset_kind_info(pinned.kind)
    if kind.name == KIT_KIND or kind.store is None:
        raise CheckoutError(
            f"{pinned} is a {kind.name}: it has no project store to check out into"
        )
    files = verified_files(library, version)
    store = mall[kind.store]
    if files and not hasattr(store, "sidecar_path"):
        raise CheckoutError(
            f"the project's {kind.store!r} store keeps no files beside its documents, "
            f"so the {len(files)} files of {pinned} have nowhere to go"
        )
    key = (
        key
        or _unedited_copy(store, lock, kind.store, pinned, version)
        or pinned.asset_id.split(".", 1)[1]
    )
    if key in store and not overwrite:
        differences = drift(store, key, version)
        if differences:
            entry_key = lock_key(kind.store, key)
            origin = (
                (store[key].get("metadata") or {})
                if isinstance(store[key], Mapping)
                else {}
            ).get(ORIGIN_KEY) or {}
            same_version = origin.get("library") == str(pinned) or (
                lock.get(entry_key, {}) if entry_key in lock else {}
            ).get("library") == str(pinned)
            raise CheckoutError(
                _fork_refusal(kind.store, key, pinned, same_version, differences)
            )
    return pinned


def _unedited_copy(
    store: Any,
    lock: Any,
    store_name: str,
    pinned: LibraryRef,
    version: Mapping[str, Any],
) -> str | None:
    """The key of a project entry that already IS ``version``, byte for byte, if any.

    The natural first round trip publishes a project's ``characters/alice``
    as ``character.alice-reiniger``; checking that back out must link the
    folder it came from, not copy it beside it under the asset's slug and leave
    the original unpinned (an#271). The asset's own slug is preferred when it
    holds the version; an entry already pinned to ANOTHER version is never
    taken over.
    """
    slug = pinned.asset_id.split(".", 1)[1]
    try:
        keys = sorted(store, key=lambda k: (k != slug, k))
    except Exception:  # noqa: BLE001 — a store that cannot be listed: the slug
        return None
    for candidate in keys:
        entry_key = lock_key(store_name, candidate)
        held = (lock[entry_key] or {}).get("library") if entry_key in lock else None
        if held not in (None, str(pinned)):
            continue
        try:
            if not drift(store, candidate, version):
                return candidate
        except Exception:  # noqa: BLE001 — an unreadable entry is not this version
            continue
    return None


def _project_lock(lock: Any, mall: Mapping[str, Any], project_dir: Any) -> Any:
    """The lockfile to use: the injected one, else the mall's, else the project's file."""
    if lock is not None:
        return lock
    registered = mall.get("library_lock") if isinstance(mall, Mapping) else None
    return registered if registered is not None else ProjectLock(project_dir)


def _pin(pinned: LibraryRef, manifest: str) -> dict[str, Any]:
    from an.library.api import _now

    return {
        "library": str(pinned),
        "asset": pinned.asset_id,
        "version": pinned.version,
        "manifest_sha256": manifest,
        "checked_out": _now(),
    }


def pinned_libraries(lock: Mapping[str, Any]) -> list[Library]:
    """The library each pin in ``lock`` names, opened at its default root, once each.

    What :func:`verify_checkout` reads when no search path is given: a pin is
    namespaced (``cutan:character.alice@v002``), so it says which library to
    open. A pin that cannot be parsed names no library and is skipped here
    (the verification reports it).
    """
    names: list[str] = []
    for entry_key in lock:
        try:
            namespace = parse_ref(lock[entry_key]["library"]).namespace
        except Exception:  # noqa: BLE001 — a malformed pin is reported by the caller
            continue
        if namespace and namespace not in names:
            names.append(namespace)
    return [open_library(name) for name in names]


class _Unverifiable(Exception):
    """The pinned version cannot be found where this machine looks for it."""


def _pinned_version(libraries: Libraries, pin: Mapping[str, Any]) -> Mapping[str, Any]:
    """The version a lockfile pin names — the SAME version, or :class:`_Unverifiable`.

    The lockfile records no root (it is committed; a path would leak), so a
    version found by name may be another library's asset under the same name
    (a study library at a custom root and the default ``cutan`` can both hold
    ``character.x@v001``). The pin's manifest settles it: a different manifest
    is a different asset, never an edit.
    """
    try:
        _, _, version = resolve(libraries, pin["library"])
    except Exception as e:  # noqa: BLE001 — every failure is "cannot verify"
        raise _Unverifiable(f"the pinned version is not found ({e})") from None
    expected = pin.get("manifest_sha256")
    if expected and version.get("manifest_sha256") != expected:
        raise _Unverifiable(
            "the library found under that name holds a different version (its "
            "manifest is not the pinned one): the pinned library is not where this "
            "machine looks (a custom root?)"
        )
    return version


#: The prefix :func:`verify_checkout` gives an entry it could not compare.
CANNOT_VERIFY: str = "cannot verify: "


def verify_checkout(
    libraries: Libraries | None,
    project_dir: str | os.PathLike | None,
    *,
    mall: Mapping[str, Any] | None = None,
    lock: Any | None = None,
) -> dict[str, list[str]]:
    """``{<store>/<key>: differences}`` for every pinned entry; empty lists are intact copies.

    libraries: where the pinned versions resolve (``None``: the library each
        pin names, at its default root — :func:`pinned_libraries`)

    What makes a pin usable as more than provenance: an entry with no
    differences is byte-for-byte the version its pin names. An entry whose
    pinned version cannot be found, or is found with another manifest (a
    same-named asset in another library), reads ``["cannot verify: …"]`` —
    never as an edit.
    """
    from an.stores import build_project_mall

    mall = mall if mall is not None else build_project_mall(project_dir)
    lock = _project_lock(lock, mall, project_dir)
    if libraries is None:
        libraries = pinned_libraries(lock)
    out: dict[str, list[str]] = {}
    for entry_key in lock:
        store_name, _, key = entry_key.partition("/")
        try:
            version = _pinned_version(libraries, lock[entry_key])
        except _Unverifiable as e:
            out[entry_key] = [f"{CANNOT_VERIFY}{e}"]
            continue
        if store_name not in mall:
            out[entry_key] = [f"{CANNOT_VERIFY}the project has no {store_name!r} store"]
            continue
        out[entry_key] = drift(mall[store_name], key, version)
    return out


def drift_findings(
    project_dir: str | os.PathLike | None = None,
    *,
    mall: Mapping[str, Any] | None = None,
    lock: Any | None = None,
    libraries: Libraries | None = None,
) -> list[Any]:
    """One ``info`` Finding per checked-out entry that is no longer — or cannot be shown to be — its pinned version.

    An edited check-out is a fork, not a mistake — hence ``info``: it says the
    pin now records where the copy CAME FROM, not what it IS, so nothing may
    treat the pin as standing for the content (an#240), and publishing the
    folder would make a new version. A pin this machine cannot check (its
    library is at a custom root, or elsewhere) is its own ``info``, with no
    advice to check anything out again — that could swap the asset for a
    same-named other one.

    project_dir: the project (not needed when both ``mall`` and ``lock`` are given)
    """
    from an.stores import build_project_mall
    from an.verify._base import Finding

    mall = mall if mall is not None else build_project_mall(project_dir)
    lock = _project_lock(lock, mall, project_dir)
    out: list[Finding] = []
    for entry_key, differences in sorted(
        verify_checkout(libraries, project_dir, mall=mall, lock=lock).items()
    ):
        if not differences:
            continue
        pinned = (lock[entry_key] or {}).get("library")
        where = f"assets.lock.json/{entry_key}"
        if differences[0].startswith(CANNOT_VERIFY):
            out.append(
                Finding(
                    "info",
                    where,
                    f"{entry_key} (pinned to {pinned}): "
                    f"{differences[0][len(CANNOT_VERIFY) :]}; whether the copy is "
                    "still that version was not checked",
                    "nothing to do if the library lives at a custom root; otherwise "
                    "make the library that holds the pinned version available",
                )
            )
            continue
        out.append(
            Finding(
                "info",
                where,
                f"{entry_key} is no longer the version it is pinned to "
                f"({pinned}): {'; '.join(differences)}",
                "publish the folder as a new version (an library publish), or check the "
                "pinned version out again with --overwrite to drop the edits",
            )
        )
    return out


def _same_pin(said: LibraryRef, pinned: LibraryRef, manifest: str) -> bool:
    if said.asset_id != pinned.asset_id or said.namespace not in (
        None,
        pinned.namespace,
    ):
        return False
    version = said.version or ""
    if version.startswith(SHA256_PREFIX):
        return manifest.startswith(version[len(SHA256_PREFIX) :])
    return version == pinned.version


def check_pins(scene: Any, lock: Mapping[str, Any]) -> list[Any]:
    """Findings where a scene's ``AssetRef.library`` and the project lockfile disagree.

    The lockfile is the source of truth (it is what the check-out wrote, beside
    the files); the scene's ``library:`` restates it. Two records of one pin can
    drift — a re-check-out updates the lockfile, not the scene — so ``an
    validate`` runs this on every project (an#240). Each disagreement, and each
    ``library:`` the lockfile does not pin, is a ``warning``.
    """
    from an.verify._base import Finding

    out: list[Finding] = []
    for i, shot in enumerate(getattr(scene, "timeline", None) or []):
        for j, entity in enumerate(shot.entities):
            if entity.library is None:
                continue
            where = f"timeline/{i}/entities/{j}/library"
            pin = (
                lock.get(lock_key(entity.store, entity.ref))
                if lock_key(entity.store, entity.ref) in lock
                else None
            )
            if pin is None:
                out.append(
                    Finding(
                        "warning",
                        where,
                        f"{entity.library} is not pinned in the lockfile for {entity.store}/{entity.ref}",
                        "check the asset out (an library checkout) or remove the library field",
                    )
                )
                continue
            try:
                said, pinned = parse_ref(entity.library), parse_ref(pin["library"])
            except (AssetIdError, KeyError, TypeError) as e:
                out.append(
                    Finding(
                        "warning",
                        where,
                        f"the lockfile's pin for {entity.store}/{entity.ref} cannot be read ({e})",
                        "check the asset out again (an library checkout --overwrite)",
                    )
                )
                continue
            same = _same_pin(said, pinned, pin.get("manifest_sha256") or "")
            if not same:
                out.append(
                    Finding(
                        "warning",
                        where,
                        f"the scene says {entity.library} but {entity.store}/{entity.ref} "
                        f"is checked out from {pin['library']}",
                        f'set library: "{pin["library"]}" or check out {entity.library}',
                    )
                )
    return out


class LibraryPinWarning(UserWarning):
    """A scene's ``library:`` pin disagrees with the project lockfile (an#240)."""


class LibraryPinError(CheckoutError):
    """Under ``strict_assets``, a render refuses a scene whose ``library:`` pins disagree with the lockfile."""


def check_pins_before_render(
    scene: Any, lock: Mapping[str, Any] | None, *, strict: bool = False
) -> list[Any]:
    """The pin check ``an render`` runs: warn per disagreement, or refuse under ``strict``.

    The same findings ``an validate`` reports (:func:`check_pins`), so the
    e2e's costly miss — a scene pinned to ``v001`` rendering ``v002``'s files
    in silence — cannot happen to someone who renders without validating
    first. ``strict`` is ``--strict-assets``: an asset that is not what the
    scene says it is, is as fatal as an asset that is missing.
    """
    if lock is None or not any(
        e.library
        for shot in getattr(scene, "timeline", None) or []
        for e in shot.entities
    ):
        return []
    findings = check_pins(scene, {k: lock[k] for k in lock})
    if findings and strict:
        raise LibraryPinError(
            "the scene's library pins disagree with assets.lock.json (strict_assets): "
            + "; ".join(f"{f.ir_path}: {f.description}" for f in findings)
            + ". Fix: "
            + "; ".join(f.suggested_fix or "" for f in findings)
        )
    for f in findings:
        warnings.warn(
            f"{f.ir_path}: {f.description}. Fix: {f.suggested_fix}",
            LibraryPinWarning,
            stacklevel=2,
        )
    return findings
