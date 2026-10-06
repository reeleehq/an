"""Kits: a curated, versioned set of library assets that a project checks out in one call.

A production in a named style needs a *set* of assets — the style's StylePack and
voice documents, a date-card environment, recurring props, the base cast — not
one. A **kit** is the library's answer: an asset of kind ``kit`` whose document
lists the members, each pinned to a concrete version, so a kit version always
means the same set of bytes. :func:`publish_kit` makes one; :func:`checkout_kit`
checks every member out through the ordinary :func:`~an.library.checkout.checkout`
(its pin in ``assets.lock.json``, its rights, its credits) and records the kit
beside them (``ProjectLock.kits``, :mod:`an.stores.library_lock`).

The document (kind ``Kit``, versioned like every document kind):

.. code-block:: json

    {"kind": "Kit", "schema_version": "0.1.0", "name": "reiniger-base",
     "members": [{"ref": "style.reiniger@v003", "key": null},
                 {"ref": "cutan:character.alice@v002", "key": "alice"}],
     "note": "what a Reiniger-style short starts from"}

Three rules, each the point rather than a detail:

- **Members are pinned.** ``latest`` and unversioned references are resolved when
  the kit is published, so re-checking out an old kit version never drifts. A
  member reference with no ``<library>:`` prefix resolves in the kit's own
  library first, then along the search path.
- **Kits do not nest** (v1). A member of kind ``kit`` is refused, at publish and
  at check-out: a nested set would make the lockfile's record of a kit's members
  a tree, and no one has asked for one.
- **Rights stay per member.** The kit's own document is its author's, so its
  rights come from the ``source=`` the publisher gives, like any document; the
  members' rights are NOT rolled into the kit's record, because each member
  carries its own at check-out (and ``an credits`` reads them there).

A check-out resolves and checks every member before it writes any: a missing
member, a nested kit, a corrupt blob or a project entry that is a fork refuses
the whole kit and leaves the project as it was.

>>> doc = Kit(name="base", members=[KitMember(ref="style.reiniger@v001")])
>>> [m.ref for m in doc.members], doc.schema_version
(['style.reiniger@v001'], '0.1.0')
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from an.ir.migrate import DocumentKind, migrate, register_kind
from an.library.api import CheckoutError, LibraryError, PublishResult, _now, publish
from an.library.checkout import CheckoutResult, _project_lock, check_checkout, checkout
from an.library.federation import (
    AssetNotFoundError,
    Libraries,
    Library,
    as_libraries,
    open_library,
    resolve,
)
from an.library.ids import AssetIdError, LibraryRef, asset_kind, parse_ref
from an.library.kinds import KIT_KIND, asset_kind_info
from an.library.lock import lock_key

__all__ = [
    "KIT_SCHEMA_VERSION",
    "Kit",
    "KitMember",
    "checkout_kit",
    "publish_kit",
]

#: Schema version of the kit document (its own document kind).
KIT_SCHEMA_VERSION: str = "0.1.0"
KIT_DOCUMENT_KIND: DocumentKind = register_kind(
    DocumentKind(
        name="Kit",
        version_field="schema_version",
        current_version=KIT_SCHEMA_VERSION,
    )
)


class KitMember(BaseModel):
    """One member of a kit: a pinned reference and the project key it lands under.

    ``key=None`` takes the check-out's default (the asset id's slug).
    """

    model_config = ConfigDict(extra="allow")

    ref: str
    key: str | None = None

    @field_validator("ref")
    @classmethod
    def _pinned(cls, ref: str) -> str:
        parse_ref(ref, require_pin=True)
        return ref


class Kit(BaseModel):
    """The kit document: a name, its pinned members, and a note saying what it is for."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["Kit"] = "Kit"
    schema_version: str = KIT_SCHEMA_VERSION
    name: str
    members: list[KitMember]
    note: str | None = None


def _slug(asset_id: str) -> str:
    return asset_id.split(".", 1)[1]


def _own_first(own: Library, libraries: Libraries) -> list[Library]:
    return [own, *(lib for lib in as_libraries(libraries) if lib is not own)]


def _slot(pinned: LibraryRef, key: str | None) -> tuple[str, str]:
    """The ``(store, key)`` a member lands in."""
    return asset_kind_info(pinned.kind).store or "", key or _slug(pinned.asset_id)


def _refuse_slots(
    where: str, slots: list[tuple[str, str]], error: type[LibraryError]
) -> None:
    seen: set[tuple[str, str]] = set()
    for store, key in slots:
        if (store, key) in seen:
            raise error(
                f"{where}: two members land in {store}/{key}; give one of them "
                "another key"
            )
        seen.add((store, key))


def _refuse_member_kind(
    where: str, ref: str, pinned: LibraryRef, error: type[LibraryError]
) -> None:
    if pinned.kind == KIT_KIND:
        raise error(f"{where}: member {ref} is itself a kit; kits do not nest")
    if asset_kind_info(pinned.kind).store is None:
        raise error(
            f"{where}: member {ref} is a {pinned.kind}, which has no project "
            "store to check out into"
        )


def _as_member(item: Any) -> tuple[str, str | None]:
    """``(ref, key)`` from a reference, a ``(ref, key)`` pair, a mapping or a :class:`KitMember`."""
    if isinstance(item, (str, LibraryRef)):
        return str(item), None
    if isinstance(item, KitMember):
        return item.ref, item.key
    if isinstance(item, Mapping):
        return str(item["ref"]), item.get("key")
    ref, key = item
    return str(ref), key


def publish_kit(
    library: Library,
    asset_id: str,
    members: Iterable[Any],
    *,
    search: Libraries | None = None,
    name: str | None = None,
    note: str | None = None,
    **curation: Any,
) -> PublishResult:
    """Publish a kit — a pinned set of assets — as the next version of ``asset_id`` in ``library``.

    library: the owning library (writes never go to a search path)
    asset_id: ``kit.<slug>``
    members: each a library reference (``[<library>:]<asset_id>[@<version>]``), a
        ``(reference, key)`` pair, or a mapping ``{"ref": …, "key": …}``; ``key`` is
        the name the member takes in the project's store (default: the asset's slug)
    search: further libraries where member references resolve (the owning library
        is always searched first, as in :func:`~an.library.api.publish`)
    name: the kit's name in its document (default: the asset id's slug)
    note: what the kit is for, stored in the document and on the version
    curation: everything else :func:`~an.library.api.publish` takes — ``source=``
        (the kit document is its author's own authoring: its rights come from
        this, never from its members), ``title``, ``style``, ``tags``, …

    Every member must resolve; ``latest`` and unversioned references are pinned to
    the concrete version now, so the kit version is reproducible. A member that is
    itself a kit, one with no project store, or two members landing in one
    ``(store, key)`` are refused.

    >>> lib = open_library("an", records={}, versions={}, blobs={})
    >>> _ = publish(lib, "style.noir", {"name": "noir"}, source={"provider": "me", "license": "cc0-1.0"})
    >>> r = publish_kit(lib, "kit.noir-base", ["style.noir"], source={"provider": "me", "license": "cc0-1.0"})
    >>> lib.versions["kit.noir-base@v001"]["doc"]["members"]
    [{'ref': 'style.noir@v001', 'key': None}]
    """
    if asset_kind(asset_id) != KIT_KIND:
        raise AssetIdError(f"a kit's id is 'kit.<slug>', not {asset_id!r}")
    where = f"kit {asset_id}"
    readers = _own_first(library, search) if search is not None else [library]
    pinned_members: list[KitMember] = []
    slots: list[tuple[str, str]] = []
    for text, key in map(_as_member, members):
        ref = parse_ref(text)
        try:
            holder, pinned, _ = resolve(readers, ref)
        except AssetNotFoundError as e:
            raise LibraryError(f"{where}: member {text} cannot be found: {e}") from e
        _refuse_member_kind(where, text, pinned, LibraryError)
        # The author's own spelling survives where it is unambiguous: a member
        # that lives in the kit's own library, named without a prefix.
        qualified = ref.namespace is not None or holder is not library
        pinned_members.append(
            KitMember(
                ref=str(pinned if qualified else pinned.with_namespace(None)), key=key
            )
        )
        slots.append(_slot(pinned, key))
    if not pinned_members:
        raise LibraryError(f"{where}: a kit needs at least one member")
    _refuse_slots(where, slots, LibraryError)
    doc = Kit(name=name or _slug(asset_id), members=pinned_members, note=note)
    return publish(
        library,
        asset_id,
        doc.model_dump(mode="json"),
        search=search,
        note=note,
        **curation,
    )


def _read_kit(pinned: LibraryRef, version: Mapping[str, Any]) -> Kit:
    try:
        return Kit.model_validate(
            migrate(dict(version["doc"]), kind=KIT_DOCUMENT_KIND.name)
        )
    except (ValidationError, ValueError, KeyError) as e:
        raise CheckoutError(f"{pinned} is not a readable kit document: {e}") from e


def checkout_kit(
    libraries: Libraries,
    project_dir: str | os.PathLike,
    ref: str | LibraryRef,
    *,
    overwrite: bool = False,
    upgrade: bool = False,
    mall: Mapping[str, Any] | None = None,
    lock: Any | None = None,
) -> list[CheckoutResult]:
    """Check every member of a kit out into a project, pin each, and record the kit.

    libraries: where the kit and its members resolve
    project_dir: the project to check out into
    ref: ``[<library>:]<kit asset id>[@<version>]``; ``latest`` is resolved now
    overwrite: replace project entries that are not exactly their member's version
    upgrade: update in place a member's entry pinned to an earlier version of
        that member, unedited since (:func:`~an.library.checkout.checkout`)
    mall: the project mall (default: ``build_project_mall(project_dir)``)
    lock: the lockfile (default: the mall's ``library_lock`` store); it needs a
        ``kits`` section, as :class:`~an.stores.library_lock.ProjectLock` has

    Returns one :class:`~an.library.checkout.CheckoutResult` per member, in the
    kit's order. Each member is checked out by :func:`~an.library.checkout.checkout`
    under its ``key`` and pinned in ``assets.lock.json`` as any check-out is; the
    kit itself is recorded under the lockfile's ``kits`` section (its pinned
    reference, manifest and the members' lockfile keys), so ``an library`` readers
    and a human can see which kit the project came from. Checking the same kit out
    again is idempotent.

    All members are resolved and checked before the first is written: a missing
    member, a member that is itself a kit, a corrupt stored file, or a project
    entry that is a fork (without ``overwrite``) raises :class:`CheckoutError`
    and the project is untouched.
    """
    from an.stores import build_project_mall

    libs = as_libraries(libraries)
    library, pinned, version = resolve(libs, ref)
    if pinned.kind != KIT_KIND:
        raise CheckoutError(
            f"{pinned} is a {pinned.kind}, not a kit; check it out with checkout()"
        )
    kit = _read_kit(pinned, version)
    mall = mall if mall is not None else build_project_mall(project_dir, ensure=True)
    lock = _project_lock(lock, mall, project_dir)
    kits = getattr(lock, "kits", None)
    if kits is None:
        raise CheckoutError(
            f"the lockfile {type(lock).__name__} has no `kits` section to record "
            f"{pinned} in; use the project's ProjectLock"
        )
    where = f"{pinned}"
    plan: list[tuple[LibraryRef, str | None]] = []
    for member in kit.members:
        try:
            _, member_pin, _ = resolve(_own_first(library, libs), member.ref)
        except AssetNotFoundError as e:
            raise CheckoutError(
                f"{where}: member {member.ref} cannot be found: {e}"
            ) from e
        _refuse_member_kind(where, member.ref, member_pin, CheckoutError)
        plan.append((member_pin, member.key))
    _refuse_slots(where, [_slot(p, k) for p, k in plan], CheckoutError)
    for member_pin, key in plan:
        check_checkout(
            libs,
            member_pin,
            key=key,
            mall=mall,
            lock=lock,
            overwrite=overwrite,
            upgrade=upgrade,
            for_kit=True,
        )
    results = [
        checkout(
            libs,
            project_dir,
            member_pin,
            key=key,
            mall=mall,
            lock=lock,
            overwrite=overwrite,
            upgrade=upgrade,
            for_kit=True,
        )
        for member_pin, key in plan
    ]
    record = {
        "library": str(pinned),
        "manifest_sha256": version["manifest_sha256"],
        "members": [lock_key(r.store, r.key) for r in results],
    }
    held = kits.get(pinned.asset_id) or {}
    if {k: held.get(k) for k in record} != record:
        kits[pinned.asset_id] = {**record, "checked_out": _now()}
    return results
