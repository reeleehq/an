"""The project lockfile: which library version each checked-out asset came from.

``assets.lock.json`` at the project root (design §7.2), one entry per checked-out
asset, keyed ``<store>/<key>`` (``characters/alice``) — the address the scene's
``AssetRef`` already uses:

.. code-block:: json

    {"schema_version": "0.1.0",
     "assets": {"characters/alice": {"library": "cutan:character.alice-reiniger@v002",
                                     "manifest_sha256": "…", "checked_out": "…"}}}

The pin records **provenance**: where each checked-out copy came from, so a
project can be rebuilt from the library. It is not a content key — the copy in
the project can be edited after it is pinned; :func:`an.library.checkout.verify_checkout`
says whether it still is its version, and only then may anything (ADR 0004's
shot cache) treat the pin as standing for the content.

The lockfile is a ``MutableMapping`` like every other store (pillar 7);
:func:`an.library.checkout.checkout` takes one by injection (``lock=``) and
defaults to :class:`ProjectLock` over the project folder. Registering it in the
project mall (``mall["library_lock"]``) is an#240.

>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     lock = ProjectLock(d)
...     lock["characters/alice"] = {"library": "character.alice@v001"}
...     list(ProjectLock(d).items())
[('characters/alice', {'library': 'character.alice@v001'})]
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

from an.ir.migrate import DocumentKind, migrate, register_kind

__all__ = ["LOCKFILE_NAME", "LOCKFILE_SCHEMA_VERSION", "ProjectLock", "lock_key"]

#: The lockfile's name at the project root.
LOCKFILE_NAME: str = "assets.lock.json"
#: The lockfile document's schema version (its own document kind).
LOCKFILE_SCHEMA_VERSION: str = "0.1.0"
LOCKFILE_KIND: DocumentKind = register_kind(
    DocumentKind(
        name="AssetsLock",
        version_field="schema_version",
        current_version=LOCKFILE_SCHEMA_VERSION,
    )
)


def lock_key(store: str, key: str) -> str:
    """The lockfile key of one project store entry.

    >>> lock_key("characters", "alice")
    'characters/alice'
    """
    return f"{store}/{key}"


class ProjectLock(MutableMapping):
    """``<store>/<key> -> pin`` over a project's ``assets.lock.json``.

    Every write rewrites the whole (small) file, sorted, so the lockfile diffs
    cleanly under version control.
    """

    def __init__(self, project_dir: str | os.PathLike) -> None:
        self.path = Path(project_dir) / LOCKFILE_NAME

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        doc.setdefault("kind", LOCKFILE_KIND.name)
        return dict(migrate(doc, kind=LOCKFILE_KIND.name).get("assets") or {})

    def _write(self, assets: dict[str, Any]) -> None:
        doc = {
            "kind": LOCKFILE_KIND.name,
            "schema_version": LOCKFILE_SCHEMA_VERSION,
            "assets": assets,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def __getitem__(self, key: str) -> dict[str, Any]:
        return self._read()[key]

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        assets = self._read()
        assets[key] = value
        self._write(assets)

    def __delitem__(self, key: str) -> None:
        assets = self._read()
        del assets[key]
        self._write(assets)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._read()))

    def __len__(self) -> int:
        return len(self._read())

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self.path)!r})"
