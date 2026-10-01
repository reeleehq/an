"""``an library …`` — the asset library from the shell, over the same functions as Python.

Wired into the top-level dispatcher as the ``library`` namespace
(``an.tools._dispatch_namespaces``), programmatically, per pillar 8: these are
plain functions taking strings and booleans and returning the text to print;
the business logic is :mod:`an.library.api`.

Lists are comma-separated (``--style reiniger,gilliam``). Every command reads
the library of ``--package`` (default ``an``) at ``--root`` (default: the
package's data folder, or ``<PKG>_HOME``); the read commands search that
library, then the core ``an`` library, then ``--extra`` ones. A refusal (an
unknown asset, a private asset leaving its library, …) prints one sentence and
exits non-zero.

Subcommands: ``publish``, ``find``, ``vocabulary``, ``show``, ``checkout``,
``promote``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from an.library.api import (
    LIBRARY_ERRORS,
    find as _find,
    promote as _promote,
    publish_dir as _publish_dir,
    show as _show,
    vocabulary as _vocabulary,
)
from an.library.checkout import checkout as _checkout
from an.library.federation import Library, open_library, search_path
from an.ir.assets import AssetSource
from an.library.root import CORE_PACKAGE

__all__ = ["checkout", "find", "promote", "publish", "show", "vocabulary"]


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


def _libraries(package: str, root: str, extra: str) -> list[Library]:
    roots = {package: root} if root else {}
    return search_path(package, extra=_split(extra) or (), roots=roots)


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
    expect_head: str = "",
    replace_curation: bool = False,
    extra: str = "",
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
    status: draft, approved or deprecated
    tags: free tags, comma-separated
    note: what changed in this version
    derived_from: library references this derives from, comma-separated
    license: licence code of the asset as a whole (counted BESIDE the descriptor's own source and everything it inherits; the strictest wins)
    provider: where it came from (required with --license)
    author: who made it
    source_url: where it was fetched from
    relicense_by: who relicenses the asset (with --relicense-reason and --license): the only way to relax inherited rights
    relicense_reason: why — recorded on the version and shown in its rights
    expect_head: refuse unless the asset's head is this version, or 'new' for an id that must not exist yet
    replace_curation: --style/--tags replace the record's lists instead of adding to them
    extra: further libraries where --derived-from resolves, by package name, comma-separated
    """
    lib = open_library(package, root or None)
    others = _libraries(package, root, extra)[1:]
    result = _publish_dir(
        lib,
        folder,
        asset_id,
        source=_source_from_flags(
            license=license, provider=provider, author=author, url=source_url
        ),
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
        replace_curation=replace_curation,
        search=others or None,
        **(
            {"expect_head": None if expect_head == "new" else expect_head}
            if expect_head
            else {}
        ),
    )
    return str(result)


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
    rights: any, publishable, or licence classes (free, attribution, private, unknown)
    family: families, comma-separated
    origin: origins, comma-separated
    status: draft, approved, deprecated
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


@_refusing
def show(
    ref: str,
    package: str = CORE_PACKAGE,
    root: str = "",
    extra: str = "",
    json_out: bool = False,
) -> str:
    """Show one asset: its record, the resolved version, and its other versions.

    ref: [<library>:]<asset_id>[@<version>] (latest by default)
    package: the library to read first (then the core an library)
    root: that library's root
    extra: further libraries, by package name, comma-separated
    json_out: print the full record and version as JSON
    """
    info = _show(_libraries(package, root, extra), ref)
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
        f"  files: {len(version.get('files') or {})}  art: {version.get('art')}  "
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
    package: str = CORE_PACKAGE,
    root: str = "",
    extra: str = "",
) -> str:
    """Check a library version out into a project, and pin it in assets.lock.json.

    project_dir: the an project
    ref: [<library>:]<asset_id>[@<version>] (latest is resolved now and pinned)
    key: the key in the project store (default: the asset's slug)
    overwrite: replace an existing entry that is not this version
    package: the library to read first (then the core an library)
    root: that library's root
    extra: further libraries, by package name, comma-separated
    """
    result = _checkout(
        _libraries(package, root, extra),
        project_dir,
        ref,
        key=key or None,
        overwrite=overwrite,
    )
    entity = result.asset_ref()
    return (
        f"{result}\n"
        f"cast it in scene.md under `yaml entities`:\n"
        f"  - {{id: {entity.id}, kind: {entity.kind}, store: {entity.store}, "
        f'ref: {entity.ref}, library: "{entity.library}"}}'
    )


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
    package: the library it is in (a genre's, e.g. cutan)
    root: that library's root
    core_root: the core an library's root (default: its data folder)
    as_id: promote under another id (when the core library has an unrelated asset with this one)
    allow_restricted: copy a private or unknown version anyway (it otherwise never leaves its library)
    """
    if not package or package == CORE_PACKAGE:
        raise SystemExit(
            "an library promote: --package names the genre library to promote from"
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


_dispatch_funcs = [publish, find, vocabulary, show, checkout, promote]
