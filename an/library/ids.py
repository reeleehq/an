"""Asset ids, version labels and library references — the library's persisted names.

Three grammars, each a persisted identifier (ADR 0005 decisions 3 and 4, plan §1
decision 7), so each is checked here once and never re-parsed by hand elsewhere:

- an **asset id** is ``<kind>.<slug>`` — flat, readable, filename-safe
  (``character.alice-reiniger``). The kind prefix keeps two kinds from colliding
  on one slug and makes ``find(kind=…)`` cheap;
- a **version label** is ``v001``, ``v002``, … — the studio convention, for
  people. The version's ``manifest_sha256`` is its identity for machines;
- a **library reference** is ``[<namespace>:]<asset_id>[@<version>]``, where
  ``<version>`` is a label, ``latest`` (floating; resolved once at check-out and
  pinned) or ``sha256:<prefix>`` (exact content). The namespace names the library
  an id resolves in when several are federated (``cutan:character.alice@v003``).

Because these strings become file names (``records/<asset_id>.json``,
``versions/<asset_id>/<vNNN>.json``), the grammars are also the path-traversal
guard: nothing that parses here can contain ``/``, ``..`` or a drive letter.

>>> ref = parse_ref("cutan:character.alice-reiniger@v003")
>>> (ref.namespace, ref.asset_id, ref.version, ref.kind)
('cutan', 'character.alice-reiniger', 'v003', 'character')
>>> str(ref)
'cutan:character.alice-reiniger@v003'
>>> version_label(12)
'v012'
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "AssetIdError",
    "LATEST",
    "LibraryRef",
    "SHA256_PREFIX",
    "asset_kind",
    "check_asset_id",
    "check_namespace",
    "check_version_label",
    "parse_ref",
    "version_label",
    "version_number",
]

#: The floating version: the record's head, resolved once and then pinned.
LATEST: str = "latest"
#: The prefix of a content-addressed version selector (``sha256:<hex prefix>``).
SHA256_PREFIX: str = "sha256:"
#: Fewest hex digits a ``sha256:`` selector may give: short enough to type,
#: long enough that a collision inside one library is not a practical worry.
MIN_SHA_PREFIX: int = 6
#: Zero-padding of a version label's number (``v001``): ordered as strings up to
#: ``v999``, and still parseable past it.
VERSION_DIGITS: int = 3

_KIND = r"[a-z][a-z0-9_]*"
_SLUG = r"[a-z0-9]+(?:[-_][a-z0-9]+)*"
_ASSET_ID = rf"{_KIND}\.{_SLUG}"
_NAMESPACE = r"[a-z][a-z0-9_]*"
_VERSION = rf"v\d{{{VERSION_DIGITS},}}"
_SELECTOR = rf"{_VERSION}|{LATEST}|{SHA256_PREFIX}[0-9a-f]{{{MIN_SHA_PREFIX},64}}"

_ASSET_ID_RE = re.compile(rf"^{_ASSET_ID}$")
_NAMESPACE_RE = re.compile(rf"^{_NAMESPACE}$")
_VERSION_RE = re.compile(rf"^{_VERSION}$")
_REF_RE = re.compile(
    rf"^(?:(?P<namespace>{_NAMESPACE}):)?(?P<asset_id>{_ASSET_ID})"
    rf"(?:@(?P<version>{_SELECTOR}))?$"
)


class AssetIdError(ValueError):
    """An asset id, version label or library reference that does not parse."""


def check_asset_id(asset_id: str) -> str:
    """Return ``asset_id`` if it is ``<kind>.<slug>``, else raise :class:`AssetIdError`.

    >>> check_asset_id("prop.teacup-victorian")
    'prop.teacup-victorian'
    >>> check_asset_id("Alice")  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    AssetIdError: ...
    """
    if not isinstance(asset_id, str) or not _ASSET_ID_RE.fullmatch(asset_id):
        raise AssetIdError(
            f"asset id {asset_id!r} is not '<kind>.<slug>' (lowercase letters, "
            "digits, '-' or '_' in the slug), e.g. 'character.alice-reiniger'"
        )
    return asset_id


def check_namespace(name: str) -> str:
    """Return ``name`` if it can name a library (a package name), else raise."""
    if not isinstance(name, str) or not _NAMESPACE_RE.fullmatch(name):
        raise AssetIdError(
            f"library name {name!r} must be a lowercase package-style name, e.g. 'cutan'"
        )
    return name


def check_version_label(label: str) -> str:
    """Return ``label`` if it is ``vNNN``, else raise :class:`AssetIdError`."""
    if not isinstance(label, str) or not _VERSION_RE.fullmatch(label):
        raise AssetIdError(f"version label {label!r} is not 'v' + digits, e.g. 'v001'")
    return label


def asset_kind(asset_id: str) -> str:
    """The kind an asset id declares by its prefix.

    >>> asset_kind("environment.palace-hall")
    'environment'
    """
    return check_asset_id(asset_id).split(".", 1)[0]


def version_label(number: int) -> str:
    """The label of the ``number``-th version (1-based).

    >>> version_label(1), version_label(1000)
    ('v001', 'v1000')
    """
    if number < 1:
        raise AssetIdError(f"version numbers start at 1, got {number}")
    return f"v{number:0{VERSION_DIGITS}d}"


def version_number(label: str) -> int:
    """The number of a version label.

    >>> version_number("v012")
    12
    """
    return int(check_version_label(label)[1:])


@dataclass(frozen=True)
class LibraryRef:
    """A parsed ``[<namespace>:]<asset_id>[@<version>]``.

    ``version`` is ``None`` when the reference gave none (read as ``latest`` by
    readers; refused where a pin is required, e.g. ``AssetRef.library``).
    """

    asset_id: str
    version: str | None = None
    namespace: str | None = None

    @property
    def kind(self) -> str:
        """The asset kind, from the id's prefix."""
        return asset_kind(self.asset_id)

    @property
    def is_pinned(self) -> bool:
        """Whether this names one immutable version (a label or a content hash)."""
        return self.version is not None and self.version != LATEST

    def with_version(self, version: str | None) -> "LibraryRef":
        """The same asset, another version."""
        return LibraryRef(self.asset_id, version, self.namespace)

    def with_namespace(self, namespace: str | None) -> "LibraryRef":
        """The same asset and version, qualified by another library name."""
        return LibraryRef(self.asset_id, self.version, namespace)

    def __str__(self) -> str:
        ns = f"{self.namespace}:" if self.namespace else ""
        ver = f"@{self.version}" if self.version else ""
        return f"{ns}{self.asset_id}{ver}"


def parse_ref(
    text: str, *, require_version: bool = False, require_pin: bool = False
) -> LibraryRef:
    """Parse a library reference.

    ``require_version=True`` refuses a reference with no ``@<version>``;
    ``require_pin=True`` also refuses ``@latest`` — the grammar of
    ``AssetRef.library``, where a floating reference would make a render depend
    on whatever the library's head is that day.

    >>> parse_ref("character.alice")
    LibraryRef(asset_id='character.alice', version=None, namespace=None)
    >>> parse_ref("character.alice@sha256:0a1b2c3d").version
    'sha256:0a1b2c3d'
    >>> parse_ref("character.alice", require_version=True)  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    AssetIdError: ...
    """
    m = _REF_RE.fullmatch(text) if isinstance(text, str) else None
    if m is None:
        raise AssetIdError(
            f"library reference {text!r} is not '[<library>:]<kind>.<slug>[@<version>]' "
            f"where <version> is vNNN, {LATEST!r} or '{SHA256_PREFIX}<hex prefix>'"
        )
    ref = LibraryRef(m["asset_id"], m["version"], m["namespace"])
    if require_pin and ref.version == LATEST:
        raise AssetIdError(
            f"library reference {text!r} floats ('@{LATEST}'); a scene pins one "
            "version — check the asset out, which resolves latest and writes the pin"
        )
    if (require_version or require_pin) and ref.version is None:
        raise AssetIdError(
            f"library reference {text!r} names no version; write "
            f"'{ref.asset_id}@v001' (or '@{LATEST}' while authoring, which "
            "check-out resolves and pins)"
        )
    return ref
