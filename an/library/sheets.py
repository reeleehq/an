"""``an library sheet``: a contact sheet of library versions, one specimen frame each (an#347).

For each reference the version is checked out into a temporary project and
its kind is asked for a specimen — a short shot showing the entity on its own
(:attr:`an.genres.EntityKind.specimen`; the core gives props, text blocks and
environments one, a genre its own kinds) — whose first frame is drawn by
:func:`an.probe.frame`, the path ``render`` draws with. A kind without a
specimen (a voice, a style, a sound, a kind whose genre gives none) shows a
labelled placeholder. ``parts=True`` tiles the version's art files instead.

Every cell is captioned with its reference and licence class, the stricter of
the version's stored and recomputed rights. A sheet showing anything not
publishable (private or unknown) is refused at a path inside a git work tree
that does not ignore it (:func:`an.library.root.check_private_output`).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

__all__ = ["DFLT_SHEET", "sheet"]

#: Where a sheet is written by default (relative to the current folder).
DFLT_SHEET: str = "artifacts/probes/sheet.png"
#: The grey of a cell with nothing to draw.
PLACEHOLDER_GREY: int = 200


def _placeholder(cell: int) -> bytes:
    # Imported here: `an.library` imports this module, and stays as light as it was.
    import numpy as np

    from an.bench.png import encode_png

    return encode_png(np.full((cell, cell, 3), PLACEHOLDER_GREY, np.uint8))


def _rights(library, version) -> str:
    from an.library.api import _stricter, effective_rights, stored_rights

    return _stricter(
        stored_rights(library, version),
        effective_rights([library], version, owner=library),
    ).license_class


#: The smallest canvas a specimen is drawn on (it is trimmed to what it shows).
SPECIMEN_CANVAS: int = 768
#: How many times its largest ``view_box`` side a specimen's canvas spans: the
#: entity is drawn at the centre, and may extend from its origin either way.
SPECIMEN_REACH: float = 2.2


def _canvas(version) -> int:
    box = (version.get("doc") or {}).get("view_box") or ()
    sides = [abs(float(v)) for v in list(box)[2:4]]
    return max(SPECIMEN_CANVAS, round(SPECIMEN_REACH * max(sides, default=0)))


def _specimen_frame(libraries, ref: str, kind, *, canvas: int) -> bytes:
    """The first frame of ``kind``'s specimen of ``ref``, drawn in a temporary project
    on a ``canvas`` square and trimmed to what it shows."""
    from an.ir.schema import Meta, Resolution, SceneIR
    from an.library.checkout import checkout
    from an.media.grid import trim
    from an.probe import frame
    from an.project import init, load

    folder = Path(tempfile.mkdtemp(prefix="an-sheet-"))
    try:
        project = init(folder / "p")
        result = checkout(libraries, project, ref)
        shot = kind.specimen(result.asset_ref())
        loaded = load(project)
        loaded.mall["scenes"]["main"] = SceneIR(
            meta=Meta(
                resolution=Resolution(width=canvas, height=canvas),
                default_renderer=shot.renderer,
            ),
            timeline=[shot],
        )
        return trim(frame(project, shot.id, 0.0))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def sheet(
    refs: Iterable[str],
    *,
    libraries=None,
    package: str | None = None,
    out: str | os.PathLike | None = None,
    cell: int = 256,
    columns: int | None = None,
    parts: bool = False,
    allow_private_here: bool = False,
) -> Path:
    """Write a contact sheet of ``refs`` (``[<library>:]<id>[@<version>]``) to one PNG.

    libraries: where the references resolve (default: ``package``'s search path)
    out: the PNG (default :data:`DFLT_SHEET`)
    parts: tile each version's art files instead of one specimen frame
    allow_private_here: write a not-publishable sheet inside a git work tree
        that does not ignore the path
    """
    from an.genres import entity_kind
    from an.library.federation import resolve, search_path
    from an.library.ids import parse_ref
    from an.library.root import CORE_PACKAGE, check_private_output
    from an.media.grid import tile

    refs = list(refs)
    if not refs:
        raise ValueError("a sheet needs at least one reference")
    if libraries is None:
        names = [n for n in (parse_ref(r).namespace for r in refs) if n]
        libraries = search_path(
            package or (names[0] if names else CORE_PACKAGE),
            extra=[n for n in dict.fromkeys(names)],
        )
    target = Path(out) if out else Path(DFLT_SHEET)
    images: list[bytes] = []
    labels: list[str] = []
    classes: list[str] = []
    for ref in refs:
        library, pinned, version = resolve(libraries, ref)
        cls = _rights(library, version)
        if parts:
            from an.library.api import verified_files
            from an.stage.snapshot import drawable, rasterise

            files = sorted(verified_files(library, version).items())
            art = [(p, d) for p, d in files if drawable(p)]
            images += rasterise(art, size=cell) if art else []
            labels += [f"{pinned} {p} [{cls}]" for p, _ in art]
            classes += [cls] * len(art)
            continue
        kind = entity_kind(pinned.kind)
        if kind is None or getattr(kind, "specimen", None) is None:
            images.append(_placeholder(cell))
            labels.append(f"{pinned} [{cls}] (no specimen for a {pinned.kind})")
        else:
            images.append(
                _specimen_frame(libraries, str(pinned), kind, canvas=_canvas(version))
            )
            labels.append(f"{pinned} [{cls}]")
        classes.append(cls)
    if not images:
        raise ValueError(f"nothing to draw: {refs} hold no art files")
    held = sorted({c for c in classes if c in ("private", "unknown")})
    check_private_output(
        target,
        publishable=not held,
        what=f"a sheet of {len(refs)} reference(s) ({', '.join(held)})",
        allow=allow_private_here,
    )
    data = tile(images, cell=cell, columns=columns, labels=labels)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target
