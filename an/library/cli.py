"""``an library …`` — the asset library from the shell, over the same functions as Python.

Wired into the top-level dispatcher as the ``library`` namespace
(``an.tools._dispatch_namespaces``), programmatically, per pillar 8: these are
plain functions taking strings and booleans and returning the text to print;
the business logic is :mod:`an.library.api`.

Lists are comma-separated (``--style reiniger,gilliam``). Every command reads
the library of ``--package`` (default ``an``) at ``--root`` (default: the
package's data folder, or ``<PKG>_HOME``); the read commands search that
library, then the core ``an`` library, then ``--extra`` ones — and the library
a namespaced reference names (``cutan:character.alice@v002`` reads ``cutan``
with no ``--package``; an#251). A refusal (an unknown asset, a private asset
leaving its library, …) prints one sentence and exits non-zero.

Subcommands: ``publish``, ``kit``, ``find``, ``vocabulary``, ``show``,
``checkout`` (which checks out a whole kit when the reference is one),
``promote``, ``retire``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from functools import wraps
from pathlib import Path
from typing import Any

from an.library.api import (
    LIBRARY_ERRORS,
    find as _find,
    promote as _promote,
    publish_dir as _publish_dir,
    set_status as _set_status,
    show as _show,
    vocabulary as _vocabulary,
)
from an.library.checkout import checkout as _checkout
from an.library.kinds import KIT_KIND
from an.library.kits import checkout_kit as _checkout_kit
from an.library.kits import publish_kit as _publish_kit
from an.library.federation import Library, open_library, search_path
from an.library.ids import parse_ref
from an.genres import entity_kind
from an.ir.assets import AssetSource, license_class
from an.library.root import CORE_PACKAGE
from an.library.stores import version_key

__all__ = [
    "checkout",
    "find",
    "kit",
    "promote",
    "publish",
    "retire",
    "show",
    "vocabulary",
]


def _split(text: str) -> list[str] | None:
    items = [t.strip() for t in (text or "").split(",") if t.strip()]
    return items or None


def _source_from_flags(
    *, license: str, provider: str, author: str, url: str
) -> AssetSource | None:
    """An :class:`AssetSource` from the CLI's flags, or ``None`` when none was given."""
    if not (license or provider or author or url):
        return None
    if not provider:
        raise SystemExit(
            "an library publish: --provider is required when declaring a source"
        )
    return AssetSource(
        provider=provider,
        license=license or None,
        author=author or None,
        url=url or None,
    )


#: The ``key=value`` fields a ``--license-part`` may give after its licence.
_PART_FIELDS: frozenset[str] = frozenset({"provider", "author", "url", "id"})


def _license_parts(
    values: Iterable[str] | None, asset: AssetSource | None
) -> dict[str, AssetSource] | None:
    """``{glob: source}`` from repeated ``--license-part 'GLOB=LICENCE[,provider=…,author=…,url=…]'``.

    The glob is everything before the first ``=`` (match a path holding ``=``
    with ``?``). A part whose class differs from the asset's, or that owes
    attribution, names its own ``provider=`` (L1-12 of the an#345 review: the
    credit must go to the right party); otherwise it takes ``--provider``.

    >>> asset = AssetSource(provider="me", license="cc0-1.0")
    >>> p = _license_parts(["parts/*.png=cc0-1.0"], asset)
    >>> p["parts/*.png"].provider, p["parts/*.png"].license
    ('me', 'cc0-1.0')
    """
    out: dict[str, AssetSource] = {}
    for value in values or []:
        glob, eq, rest = value.partition("=")
        licence, *fields = [t.strip() for t in rest.split(",")]
        if not (eq and glob.strip() and licence):
            raise SystemExit(
                f"an library publish: --license-part {value!r} must read "
                "'GLOB=LICENCE[,provider=…,author=…,url=…]'"
            )
        extra: dict[str, str] = {}
        for item in fields:
            key, _, val = item.partition("=")
            if key not in _PART_FIELDS or not val:
                raise SystemExit(
                    f"an library publish: --license-part field {item!r} is not one "
                    f"of {sorted(_PART_FIELDS)} as key=value"
                )
            extra[key] = val
        if "provider" not in extra:
            cls = license_class(AssetSource(provider="-", license=licence))
            if (
                asset is None
                or cls in ("attribution", "noncommercial")
                or cls != license_class(asset)
            ):
                raise SystemExit(
                    f"an library publish: --license-part {value!r} needs its own "
                    "provider=… (a part whose licence class differs from the "
                    "asset's, or that owes attribution, is credited to its own party)"
                )
            extra["provider"] = asset.provider
        out[glob.strip()] = AssetSource(license=licence, **extra)
    return out or None


def _refusing(func: Callable[..., str]) -> Callable[..., str]:
    """Turn a library refusal into one printed sentence and a non-zero exit.

    ``SystemExit`` with a message prints it to stderr and exits 1; the CLI
    wrapper deliberately lets ``SystemExit`` through. Anything that is not a
    refusal keeps its traceback, because that is a bug.
    """

    @wraps(func)
    def run(*args: Any, **kwargs: Any) -> str:
        try:
            return func(*args, **kwargs)
        except LIBRARY_ERRORS as e:
            raise SystemExit(f"an library {func.__name__}: {e}") from e

    return run


def _namespaces(refs: Iterable[str]) -> list[str]:
    """The libraries named by namespaced references (``cutan:character.x`` -> ``cutan``)."""
    out: list[str] = []
    for ref in refs:
        namespace = parse_ref(ref).namespace
        if namespace and namespace not in out:
            out.append(namespace)
    return out


def _libraries(
    package: str, root: str, extra: str, *, refs: Iterable[str] = ()
) -> list[Library]:
    """``package``'s search path, plus ``--extra`` and every library a reference names.

    With no ``package``, the library a namespaced reference names is the one
    read first — and the one ``--root`` locates (``cutan:character.x --root
    study`` opens ``cutan`` at ``study``, never ``an``); ``--root`` with
    references into several libraries needs ``--package`` to say which.
    """
    if not package:
        named = _namespaces(refs)
        if root and len(named) > 1:
            raise SystemExit(
                f"an library: --root is ambiguous for references into {named}; "
                "say which library it locates with --package"
            )
        package = named[0] if named else CORE_PACKAGE
    roots = {package: root} if root else {}
    names = _split(extra) or []
    names += [n for n in _namespaces(refs) if n not in names]
    return search_path(package, extra=names, roots=roots)


def _link_command(project: Path, folder: Path, ref: Any) -> str:
    """The check-out that links ``folder`` to the version just published from it (an#346).

    It names the folder's key when the folder is unpinned or pinned to this
    same asset id, and ``--upgrade`` when pinned to an earlier version of it; a
    folder pinned to ANOTHER asset is never offered (L2-6).
    """
    from an.library.lock import lock_key
    from an.stores.library_lock import ProjectLock

    base = f"an library checkout {project} {ref}"
    folder = folder.expanduser().absolute()
    try:
        pin = ProjectLock(project).get(lock_key(folder.parent.name, folder.name))
        held = parse_ref(pin["library"]) if pin else None
    except Exception:  # noqa: BLE001 — an unreadable lockfile or pin: the plain command
        return base
    if held is None:
        return f"{base} --key {folder.name}"
    if held.asset_id != ref.asset_id:
        return base
    upgrade = " --upgrade" if held.version != ref.version else ""
    return f"{base} --key {folder.name}{upgrade}"


def _project_of(folder: str) -> Path | None:
    """The project an asset folder sits in (``<project>/assets/<store>/<key>``), if any."""
    here = Path(folder).expanduser().absolute()
    project = here.parent.parent.parent
    if here.parent.parent.name == "assets" and (project / "scene.md").is_file():
        return project
    return None


@_refusing
def publish(
    folder: str,
    asset_id: str,
    package: str = CORE_PACKAGE,
    root: str = "",
    title: str = "",
    family: str = "",
    style: str = "",
    origin: str = "",
    status: str = "",
    tags: str = "",
    note: str = "",
    derived_from: str = "",
    license: str = "",
    provider: str = "",
    author: str = "",
    source_url: str = "",
    relicense_by: str = "",
    relicense_reason: str = "",
    relabel_by: str = "",
    relabel_reason: str = "",
    expect_head: str = "",
    replace_curation: bool = False,
    extra: str = "",
    license_part: list[str] | None = None,
) -> str:
    """Publish an asset folder as the next version of ``asset_id``.

    folder: the asset folder as it sits in a project (e.g. assets/characters/alice)
    asset_id: <kind>.<slug>, e.g. character.alice-reiniger
    package: whose library to publish into (an, or a genre such as cutan)
    root: that library's root (default: the package's data folder)
    title: a human title for the record
    family: the identity shared across styles and variants (e.g. alice)
    style: styles the asset suits, comma-separated
    origin: drawn, procedural, dicebear, carved, traced, stock, commissioned, generated
    status: draft, approved, deprecated or retired (publishing into a retired id needs it, to revive it)
    tags: free tags, comma-separated
    note: what changed in this version
    derived_from: library references this derives from, comma-separated
    license: licence code of the asset as a whole (counted BESIDE the descriptor's own source and everything it inherits; the strictest wins)
    provider: where it came from (required with --license)
    author: who made it
    source_url: where it was fetched from
    relicense_by: who relicenses the asset (with --relicense-reason and --license): the only way to relax inherited rights
    relicense_reason: why — recorded on the version and shown in its rights
    relabel_by: who labels bytes nobody labelled (with --relabel-reason and --license): answers the asset's earlier unlabelled files and sourceless versions, never a stricter statement nor another asset's files; on unchanged content it is recorded on the head, no new version
    relabel_reason: why — recorded (on the version, or on the head it labels) and shown in its rights
    expect_head: refuse unless the asset's head is this version, or 'new' for an id that must not exist yet
    replace_curation: --style/--tags replace the record's lists instead of adding to them
    extra: further libraries where --derived-from resolves, by package name, comma-separated
    license_part: GLOB=LICENCE[,provider=…,author=…,url=…], repeatable — a licence for the files the glob names ('*' stays in one folder, '**' crosses folders, case-exact); every other file takes the version's label without them. Never looser than what the bytes already carry, unless relicensed
    """
    lib = open_library(package, root or None)
    asset_source = _source_from_flags(
        license=license, provider=provider, author=author, url=source_url
    )
    others = _libraries(package, root, extra, refs=_split(derived_from) or ())[1:]
    result = _publish_dir(
        lib,
        folder,
        asset_id,
        source=asset_source,
        license_parts=_license_parts(license_part, asset_source),
        derived_from=_split(derived_from) or (),
        title=title or None,
        family=family or None,
        style=_split(style),
        origin=origin or None,
        status=status or None,
        tags=_split(tags),
        note=note or None,
        relicense=(
            {"by": relicense_by, "reason": relicense_reason}
            if relicense_by or relicense_reason
            else None
        ),
        relabel=(
            {"by": relabel_by, "reason": relabel_reason}
            if relabel_by or relabel_reason
            else None
        ),
        replace_curation=replace_curation,
        search=others or None,
        **(
            {"expect_head": None if expect_head == "new" else expect_head}
            if expect_head
            else {}
        ),
    )
    lines = [str(result)]
    if result.rights.license_class == "unknown":
        lines.append(
            f"unknown (never publishable): {'; '.join(result.rights.reasons)}."
        )
        lines += list(result.advice)
    project = _project_of(folder)
    if project is not None:
        lines.append(
            "to link the project's copy to it (pin it in assets.lock.json): "
            + _link_command(project, Path(folder), result.ref)
        )
    return "\n".join(lines)


@_refusing
def kit(
    package: str,
    asset_id: str,
    refs: str,
    key_for: str = "",
    name: str = "",
    note: str = "",
    title: str = "",
    family: str = "",
    style: str = "",
    status: str = "",
    tags: str = "",
    license: str = "",
    provider: str = "",
    author: str = "",
    source_url: str = "",
    root: str = "",
    extra: str = "",
) -> str:
    """Publish a kit: a pinned set of assets a project checks out in one call.

    package: whose library to publish the kit into (an, or a genre such as cutan)
    asset_id: kit.<slug>, e.g. kit.reiniger-base
    refs: the members, comma-separated [<library>:]<asset_id>[@<version>] (latest is pinned now)
    key_for: the project key of a member, as ref=key pairs, comma-separated (default: the asset's slug)
    name: the kit's name in its document (default: the asset id's slug)
    note: what the kit is for
    title: a human title for the record
    family: the identity shared across styles and variants
    style: styles the kit suits, comma-separated
    status: draft, approved, deprecated or retired
    tags: free tags, comma-separated
    license: licence code of the kit document itself (the members keep their own rights)
    provider: where the kit document came from (required with --license)
    author: who made it
    source_url: where it was fetched from
    root: that library's root (default: the package's data folder)
    extra: further libraries where the members resolve, by package name, comma-separated
    """
    members = _split(refs) or []
    keys = dict(pair.split("=", 1) for pair in _split(key_for) or [] if "=" in pair)
    strays = [r for r in keys if r not in members]
    if strays or len(keys) != len(_split(key_for) or []):
        raise SystemExit(
            f"an library kit: --key-for takes ref=key pairs naming members; "
            f"got {key_for!r} for members {members}"
        )
    lib = open_library(package, root or None)
    others = _libraries(package, root, extra, refs=members)[1:]
    result = _publish_kit(
        lib,
        asset_id,
        [(ref, keys.get(ref)) for ref in members],
        search=others or None,
        name=name or None,
        note=note or None,
        source=_source_from_flags(
            license=license, provider=provider, author=author, url=source_url
        ),
        title=title or None,
        family=family or None,
        style=_split(style),
        status=status or None,
        tags=_split(tags),
    )
    lines = [str(result)]
    pinned = lib.versions[version_key(asset_id, result.ref.version)]["doc"]["members"]
    lines += [f"  {m['ref']}" + (f" as {m['key']}" if m["key"] else "") for m in pinned]
    if result.rights.license_class == "unknown":
        lines.append(
            f"unknown (never publishable): {'; '.join(result.rights.reasons)}."
        )
        lines += list(result.advice)
    return "\n".join(lines)


@_refusing
def find(
    kind: str = "",
    style: str = "",
    affords: str = "",
    rights: str = "any",
    family: str = "",
    origin: str = "",
    status: str = "",
    tags: str = "",
    near: bool = False,
    package: str = CORE_PACKAGE,
    root: str = "",
    extra: str = "",
    json_out: bool = False,
) -> str:
    """Find assets: AND across facets, OR within one facet's comma-separated values.

    kind: character, prop, environment, ...
    style: styles, comma-separated (any of them)
    affords: capabilities the asset must ALL have, e.g. limbs.legs,swap.view:side
    rights: any, publishable, commercial (publishable in a commercial video: not non-commercial), or licence classes (free, attribution, noncommercial, private, unknown)
    family: families, comma-separated
    origin: origins, comma-separated
    status: draft, approved, deprecated, retired (a retired asset is listed only when asked for)
    tags: tags, comma-separated (any of them)
    near: also list assets that only miss capabilities, with the remedy for each
    package: the library to search first (then the core an library)
    root: that library's root
    extra: further libraries to search, by package name, comma-separated
    json_out: print JSON instead of a table
    """
    result = _find(
        _libraries(package, root, extra),
        kind=_split(kind),
        style=_split(style),
        affords=_split(affords),
        rights=_split(rights) or "any",
        family=_split(family),
        origin=_split(origin),
        status=_split(status),
        tags=_split(tags),
        near=near,
    )
    if json_out:
        return json.dumps(result.to_dict(), indent=2, sort_keys=True)
    lines = [f"{len(result.hits)} match(es)"]
    lines += [
        f"  {h.ref}  [{h.license_class}]  {h.title or ''}".rstrip() for h in result.hits
    ]
    if near:
        lines.append(f"{len(result.near)} near miss(es)")
        for h in result.near:
            lines.append(f"  {h.ref}  missing: {', '.join(h.missing)}")
            lines += [f"      {cap}: {remedy}" for cap, remedy in h.remedies.items()]
    return "\n".join(lines)


@_refusing
def vocabulary(package: str = CORE_PACKAGE, root: str = "", extra: str = "") -> str:
    """Every facet value with its count, and every capability with its remedy (JSON).

    package: the library to read first (then the core an library)
    root: that library's root
    extra: further libraries, by package name, comma-separated
    """
    return json.dumps(
        _vocabulary(_libraries(package, root, extra)), indent=2, sort_keys=True
    )


def _file_count(record: dict, version: dict) -> str:
    """The files a check-out writes, as a reader counts them on disk (an#271):
    the descriptor file too, which a version holds as its ``doc``.

    >>> _file_count({"kind": "environment"}, {"files": {"plates/a.svg": {}, "plates/b.svg": {}}})
    '3 (meta.json + 2)'
    """
    from an.library.kinds import asset_kind_info

    n = len(version.get("files") or {})
    try:
        descriptor = asset_kind_info(record.get("kind") or "").descriptor
    except Exception:  # noqa: BLE001 — an unknown kind: count the files alone
        descriptor = None
    return f"{n + 1} ({descriptor} + {n})" if descriptor else str(n)


@_refusing
def show(
    ref: str,
    package: str = "",
    root: str = "",
    extra: str = "",
    json_out: bool = False,
) -> str:
    """Show one asset: its record, the resolved version, and its other versions.

    ref: [<library>:]<asset_id>[@<version>] (latest by default); a <library>: prefix reads that library
    package: the library to read first, then the core an library (default: the reference's <library>: prefix, else an)
    root: that library's root (with no --package, the root of the library the reference names)
    extra: further libraries, by package name, comma-separated
    json_out: print the full record and version as JSON
    """
    info = _show(_libraries(package, root, extra, refs=[ref]), ref)
    if json_out:
        return json.dumps(info, indent=2, sort_keys=True)
    record, version = info["record"], info["version"]
    facets = record.get("facets") or {}
    lines = [
        f"{info['ref']}  {record.get('title') or ''}".rstrip(),
        f"  versions: {', '.join(info['versions'])} (head {record.get('head')})",
        f"  family: {record.get('family')}  status: {record.get('status')}  "
        f"style: {', '.join(facets.get('style') or []) or '-'}  origin: {facets.get('origin')}",
        f"  tags: {', '.join(record.get('tags') or []) or '-'}",
        f"  rights: {info['rights']['license_class']}"
        + (
            f" ({'; '.join(info['rights']['reasons'])})"
            if info["rights"]["reasons"]
            else ""
        ),
        f"  files: {_file_count(record, version)}  art: {version.get('art')}  "
        f"manifest: {version['manifest_sha256'][:16]}",
        f"  derived_from: {', '.join(version.get('derived_from') or []) or '-'}",
        "  affords:",
    ]
    for cap, params in sorted((version.get("affordances") or {}).items()):
        keys = (params or {}).get("keys")
        lines.append(f"    {cap}" + (f": {', '.join(keys)}" if keys else ""))
    return "\n".join(lines)


@_refusing
def checkout(
    project_dir: str,
    ref: str,
    key: str = "",
    overwrite: bool = False,
    upgrade: bool = False,
    package: str = "",
    root: str = "",
    extra: str = "",
    only: str = "",
    skip: str = "",
) -> str:
    """Check a library version out into a project, and pin it in assets.lock.json.

    project_dir: the an project
    ref: [<library>:]<asset_id>[@<version>] (latest is resolved now and pinned); a <library>: prefix reads that library, no --package needed. A kit.<slug> reference checks out every member of the kit, each pinned, and records the kit in the lockfile
    key: the key in the project store (default: the asset's slug)
    overwrite: replace an existing entry that is not this version (an unedited folder you just published is recognised without it)
    upgrade: update in place the entry pinned to an earlier version of this asset, if unedited; the pin moves (then update the scene's library: line)
    package: the library to read first, then the core an library (default: the reference's <library>: prefix, else an)
    root: that library's root (with no --package, the root of the library the reference names)
    extra: further libraries, by package name, comma-separated
    only: for a kit, check out only these members (their keys or asset ids, comma-separated)
    skip: for a kit, leave these members out (their keys or asset ids, comma-separated)
    """
    libraries = _libraries(package, root, extra, refs=[ref])
    is_kit = parse_ref(ref).kind == KIT_KIND
    if (only or skip) and not is_kit:
        raise SystemExit(
            "an library checkout: --only and --skip select a kit's members; "
            f"{ref} is not a kit"
        )
    if is_kit:
        if key:
            raise SystemExit(
                "an library checkout: --key names one asset's key; a kit's members "
                "carry their own keys (set them with `an library kit --key-for`)"
            )
        results = _checkout_kit(
            libraries,
            project_dir,
            ref,
            overwrite=overwrite,
            upgrade=upgrade,
            only=_names(only) or None,
            skip=_names(skip),
        )
        lines = [f"kit {ref}: {len(results)} members", *map(str, results)]
        castable = [r for r in results if entity_kind(r.ref.kind) is not None]
        return "\n".join([*lines, *_entities_block(castable)])
    result = _checkout(
        libraries,
        project_dir,
        ref,
        key=key or None,
        overwrite=overwrite,
        upgrade=upgrade,
    )
    return "\n".join([str(result), *_entities_block([result])])


def _names(csv: str) -> list[str]:
    """The comma-separated names in ``csv``, stripped (none for an empty string)."""
    return [n.strip() for n in csv.split(",") if n.strip()]


def _entities_block(results: list[Any]) -> list[str]:
    """The lines inviting the author to cast ``results`` under ``yaml entities`` (none for none)."""
    if not results:
        return []
    lines = ["cast it in scene.md under `yaml entities`:"]
    for result in results:
        entity = result.asset_ref()
        lines.append(
            f"  - {{id: {entity.id}, kind: {entity.kind}, store: {entity.store}, "
            f'ref: {entity.ref}, library: "{entity.library}"}}'
        )
    return lines


@_refusing
def promote(
    ref: str,
    package: str = "",
    root: str = "",
    core_root: str = "",
    as_id: str = "",
    allow_restricted: bool = False,
) -> str:
    """Copy a version into the core an library, so other genres can reuse it.

    ref: [<library>:]<asset_id>[@<version>]
    package: the library it is in (a genre's, e.g. cutan; default: the reference's <library>: prefix)
    root: that library's root
    core_root: the core an library's root (default: its data folder)
    as_id: promote under another id (when the core library has an unrelated asset with this one)
    allow_restricted: copy a private or unknown version anyway (it otherwise never leaves its library)
    """
    package = package or (_namespaces([ref]) or [""])[0]
    if not package or package == CORE_PACKAGE:
        raise SystemExit(
            "an library promote: --package (or a <library>: prefix on the reference) "
            "names the genre library to promote from"
        )
    source = open_library(package, root or None)
    target = open_library(CORE_PACKAGE, core_root or None)
    return str(
        _promote(
            [source],
            ref,
            to=target,
            as_id=as_id or None,
            allow_restricted=allow_restricted,
        )
    )


@_refusing
def retire(
    ref: str,
    by: str = "",
    reason: str = "",
    status: str = "retired",
    package: str = "",
    root: str = "",
) -> str:
    """Retire an asset id: hidden from find, never deleted; its versions stay readable.

    ref: [<library>:]<asset_id> — a <library>: prefix names the library (no --package needed)
    by: who retires it (recorded)
    reason: why (recorded)
    status: the status to set instead (draft, approved or deprecated revives or re-curates it)
    package: the library it is in (default: the reference's <library>: prefix, else an)
    root: that library's root
    """
    parsed = parse_ref(ref)
    package = package or parsed.namespace or CORE_PACKAGE
    library = open_library(package, root or None)
    record = _set_status(library, parsed.asset_id, status, by=by, reason=reason)
    hidden = (
        " (hidden from find; find --status retired lists it)"
        if status == "retired"
        else ""
    )
    return (
        f"{library.name}:{parsed.asset_id} is {record['status']}{hidden}; "
        f"its versions ({record.get('head') or 'none'} latest) stay readable"
    )


@_refusing
def sheet(
    refs: list[str],
    out: str = "",
    cell: int = 256,
    columns: int = 0,
    parts: bool = False,
    allow_private_here: bool = False,
    package: str = "",
    root: str = "",
    extra: str = "",
) -> str:
    """Draw a contact sheet: one specimen frame per library version, captioned with its licence class.

    refs: [<library>:]<asset_id>[@<version>] references
    out: the PNG to write (default: artifacts/probes/sheet.png under the current folder)
    cell: the side of each cell, in pixels
    columns: cells per row (default: a square grid)
    parts: tile each version's art files instead of one specimen frame
    allow_private_here: write a sheet showing private or unknown material where git would pick it up
    package: the library to read first (default: the first reference's <library>: prefix, else an)
    root: that library's root
    extra: further libraries, by package name, comma-separated
    """
    from an.library.sheets import sheet as _sheet

    path = _sheet(
        refs,
        libraries=_libraries(package, root, extra, refs=refs),
        out=out or None,
        cell=cell,
        columns=columns or None,
        parts=parts,
        allow_private_here=allow_private_here,
    )
    return f"sheet: {path}"


_dispatch_funcs = [
    publish,
    kit,
    find,
    vocabulary,
    show,
    checkout,
    promote,
    retire,
    sheet,
]
