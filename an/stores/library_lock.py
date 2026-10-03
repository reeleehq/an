"""The project lockfile: which library version each checked-out asset came from.

``assets.lock.json`` at the project root (design §7.2), one entry per checked-out
asset, keyed ``<store>/<key>`` (``characters/alice``) — the address the scene's
``AssetRef`` already uses:

.. code-block:: json

    {"schema_version": "0.1.0",
     "assets": {"characters/alice": {"library": "cutan:character.alice-reiniger@v002",
                                     "manifest_sha256": "…", "checked_out": "…"}}}

**The lockfile is the single source of truth for a pin** (an#240). It is written
by the check-out that put the files there, beside the manifest it verified, so
it says what the project actually holds. A scene's ``AssetRef.library`` is the
declared intent, an optional restatement of it for the reader; a later
"reference" resolution resolves through the lockfile entry ``<store>/<ref>``
too, and treats ``library:`` as the intent it must match — never as a second
pin. ``an validate`` (and ``an render``, fatally under ``--strict-assets``)
reports every scene ``library:`` that disagrees with the lockfile, or names an
entry the lockfile does not pin (:func:`an.library.checkout.check_pins`). The
lockfile records no library root: it is committed, and a path would leak.

The pin records **provenance**: where each checked-out copy came from, so a
project can be rebuilt from the library. It is not a content key — the copy in
the project can be edited after it is pinned; :func:`an.library.checkout.verify_checkout`
says whether it still is its version (``an validate`` reports the drift as
``info``: an edited check-out is a fork, not a mistake), and only then may
anything treat the pin as standing for the content.

A **kit** check-out (:func:`an.library.kits.checkout_kit`) pins each member the
way any check-out does, and additionally records the kit in a top-level
``"kits"`` section, keyed by the kit's asset id::

    {"kits": {"kit.reiniger-base": {"library": "cutan:kit.reiniger-base@v002",
                                    "manifest_sha256": "…", "checked_out": "…",
                                    "members": ["styles/reiniger", "voices/narrator"]}}}

``members`` are lockfile keys of ``assets``. The section sits OUTSIDE ``assets``
on purpose: everything that walks the pins (``verify_checkout``, ``an validate``,
``check_pins``) iterates the mapping, which is ``assets`` only, so a kit entry
cannot be mistaken for an asset or collide with a ``<store>/<key>`` key. It is
additive (an older ``an`` reads the file and ignores the section, though its
next write drops it) and read through
:attr:`ProjectLock.kits`.

The lockfile is a ``MutableMapping`` like every other store (pillar 7),
registered in the project mall as ``mall["library_lock"]``
(:func:`an.stores.build_project_mall`); :func:`an.library.checkout.checkout`
writes through the mall's store unless one is injected (``lock=``). It lives
here, with the other project stores, so building a project mall never imports
the asset library; :mod:`an.library.lock` re-exports it.

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
#: The lockfile's section of per-asset pins, and of the kits checked out.
ASSETS_SECTION: str = "assets"
KITS_SECTION: str = "kits"
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


class _LockSection(MutableMapping):
    """One top-level section of the lockfile (``kits``), as a mapping over the file."""

    def __init__(self, lock: "ProjectLock", name: str) -> None:
        self._lock, self._name = lock, name

    def __getitem__(self, key: str) -> dict[str, Any]:
        return self._lock._read_section(self._name)[key]

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        section = self._lock._read_section(self._name)
        section[key] = value
        self._lock._write_section(self._name, section)

    def __delitem__(self, key: str) -> None:
        section = self._lock._read_section(self._name)
        del section[key]
        self._lock._write_section(self._name, section)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._lock._read_section(self._name)))

    def __len__(self) -> int:
        return len(self._lock._read_section(self._name))


class ProjectLock(MutableMapping):
    """``<store>/<key> -> pin`` over a project's ``assets.lock.json``.

    Every write rewrites the whole (small) file, sorted, so the lockfile diffs
    cleanly under version control. The mapping is the ``assets`` section;
    :attr:`kits` is the ``kits`` section, and a write to either keeps the other.
    """

    def __init__(self, project_dir: str | os.PathLike) -> None:
        self.path = Path(project_dir) / LOCKFILE_NAME

    @property
    def kits(self) -> MutableMapping[str, dict[str, Any]]:
        """``kit asset id -> record`` of the kits checked out into the project."""
        return _LockSection(self, KITS_SECTION)

    def _read_doc(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        doc.setdefault("kind", LOCKFILE_KIND.name)
        return dict(migrate(doc, kind=LOCKFILE_KIND.name))

    def _write_doc(self, sections: dict[str, dict[str, Any]]) -> None:
        doc = {
            "kind": LOCKFILE_KIND.name,
            "schema_version": LOCKFILE_SCHEMA_VERSION,
            **{name: body for name, body in sections.items() if body},
            # `assets` is always written, as it always was.
            "assets": sections.get("assets") or {},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _read_section(self, name: str) -> dict[str, Any]:
        return dict(self._read_doc().get(name) or {})

    def _write_section(self, name: str, body: dict[str, Any]) -> None:
        doc = self._read_doc()
        sections = {n: dict(doc.get(n) or {}) for n in (ASSETS_SECTION, KITS_SECTION)}
        sections[name] = body
        self._write_doc(sections)

    def _read(self) -> dict[str, Any]:
        return self._read_section(ASSETS_SECTION)

    def _write(self, assets: dict[str, Any]) -> None:
        self._write_section(ASSETS_SECTION, assets)

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
