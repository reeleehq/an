"""The asset library: reusable assets that outlive their videos (ADR 0005).

A **library** holds characters, props, environments, sounds, styles, voices and
motion clips across videos and styles; a **project** is one video that checks
assets out of it. Each package has its own library root (``an`` →
``~/.local/share/an``, a genre such as ``cutan`` → ``~/.local/share/cutan``),
read together as an ordered search path.

The example publishes a character, which is the cut-out genre's asset (``pip install
"an[cutout]"``), so it is not run where that package is absent:

>>> import tempfile
>>> from cutan.characters.schema import CharacterDescriptor  # doctest: +SKIP
>>> with tempfile.TemporaryDirectory() as d:  # doctest: +SKIP
...     lib = open_library("an", root=d)
...     doc = CharacterDescriptor(name="blob")
...     r = publish(lib, "character.blob", doc, style="reiniger")
...     [h.ref for h in find(lib, kind="character", affords="swap.view:front")]
['character.blob@v001']

What lives where:

- :mod:`an.library.root` — the root of each package's data (vendored XDG logic);
- :mod:`an.library.ids` — asset ids, version labels, library references;
- :mod:`an.library.stores` — the mall: ``records``, write-once ``versions``,
  content-addressed ``blobs``, append-only ``labels``, all injected
  ``MutableMapping`` s;
- :mod:`an.library.federation` — :class:`Library` and the search path;
- :mod:`an.library.affordances` — capabilities and per-kind analysers (the seed
  of ADR 0002's registry); :mod:`an.library.character` — the character analyser;
- :mod:`an.library.rights` — the most-restrictive roll-up over ``AssetSource``;
  :mod:`an.library.floor` — the strictest statement any library on the machine
  makes about a blob; :mod:`an.library.registry` — the machine's registry of
  library roots the floor reads, independent of the environment;
- :mod:`an.library.api` — ``publish``, ``find``, ``vocabulary``, ``show``,
  ``promote``; :mod:`an.library.checkout` — ``checkout``, ``verify_checkout``,
  ``check_pins``, ``drift_findings`` (both run by ``an validate``);
  :mod:`an.library.lock` — the project lockfile (a project store,
  ``mall["library_lock"]``);
- :mod:`an.library.cli` — ``an library …``, a projection of the same functions.
"""

from an.library.affordances import (
    CAPABILITIES,
    Capability,
    analyse,
    register_analyser,
    register_capability,
)
from an.library.api import (
    LIBRARY_ERRORS,
    CheckoutError,
    FindResult,
    Hit,
    IntegrityError,
    LibraryError,
    PublishResult,
    effective_rights,
    find,
    promote,
    publish,
    publish_dir,
    reindex,
    retire,
    scan_index,
    set_status,
    show,
    version_labels,
    vocabulary,
)
from an.library.checkout import (
    CheckoutResult,
    check_pins,
    checkout,
    drift_findings,
    verify_checkout,
)
from an.library.federation import (
    AssetNotFoundError,
    Library,
    open_library,
    resolve,
    search_path,
)
from an.library.ids import AssetIdError, LibraryRef, parse_ref
from an.library.kinds import register_asset_kind
from an.library.lock import ProjectLock
from an.library.registry import RegistryError, register_root, registered_roots
from an.library.rights import Rights, RightsRefusal, roll_up
from an.library.root import library_root, project_dir, projects_root
from an.library.stores import VersionExistsError, build_library_mall

__all__ = [
    "AssetIdError",
    "AssetNotFoundError",
    "CAPABILITIES",
    "Capability",
    "CheckoutError",
    "CheckoutResult",
    "FindResult",
    "Hit",
    "IntegrityError",
    "LIBRARY_ERRORS",
    "Library",
    "LibraryError",
    "LibraryRef",
    "ProjectLock",
    "PublishResult",
    "RegistryError",
    "Rights",
    "RightsRefusal",
    "VersionExistsError",
    "analyse",
    "build_library_mall",
    "check_pins",
    "checkout",
    "drift_findings",
    "effective_rights",
    "find",
    "library_root",
    "open_library",
    "parse_ref",
    "project_dir",
    "projects_root",
    "promote",
    "publish",
    "publish_dir",
    "reindex",
    "retire",
    "register_analyser",
    "register_asset_kind",
    "register_capability",
    "register_root",
    "registered_roots",
    "resolve",
    "roll_up",
    "scan_index",
    "search_path",
    "set_status",
    "show",
    "verify_checkout",
    "version_labels",
    "vocabulary",
]
