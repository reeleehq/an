"""The project lockfile, as the asset library sees it (re-exported from :mod:`an.stores.library_lock`).

The lockfile is a project store — ``mall["library_lock"]``, registered by
:func:`an.stores.build_project_mall` (an#240) — so its class lives with the other
project stores and building a project never imports the library. This module
keeps the import path the library and its callers already use.

>>> LOCKFILE_NAME, lock_key("characters", "alice")
('assets.lock.json', 'characters/alice')
"""

from an.stores.library_lock import (
    LOCKFILE_KIND,
    LOCKFILE_NAME,
    LOCKFILE_SCHEMA_VERSION,
    ProjectLock,
    lock_key,
)

__all__ = ["LOCKFILE_NAME", "LOCKFILE_SCHEMA_VERSION", "ProjectLock", "lock_key"]
