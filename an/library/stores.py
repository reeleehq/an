"""The library mall: ``records``, ``versions`` and ``blobs``, each an injected ``MutableMapping``.

ADR 0005 decision 11 and design §10. Three entities, three stores:

==========  ==============================  ==========================================
store       key                             on disk (default backend)
==========  ==============================  ==========================================
records     ``<asset_id>``                  ``library/records/<asset_id>.json``
versions    ``<asset_id>@<vNNN>``           ``library/versions/<asset_id>/<vNNN>.json``
blobs       ``<sha256>``                    ``library/blobs/<aa>/<sha256>``
==========  ==============================  ==========================================

- **``dol`` stores**, unlike the project mall's hand-written folder classes: a
  byte store (:class:`LocalFiles`) seen through :func:`dol.wrap_kvs` with a JSON
  codec and a key transform. Each store is replaced by injection
  (``build_library_mall(blobs=my_s3_store)``), and business logic sees only the
  mapping interface — the move to S3 is an injection, not a rewrite.
  :class:`LocalFiles` rather than ``dol.Files`` because the library needs three
  things ``dol.Files`` does not give: writes that cannot tear (temp file +
  ``os.replace``), an exclusive create for write-once versions, and containment
  (``dol.Files`` writes a ``../x`` key outside its root).
- **``versions`` is write-once** (:class:`WriteOnce`): a version is immutable, so
  overwriting or deleting one raises :class:`VersionExistsError` — projects pin
  versions, and a pin that could change under them is no pin. On the folder
  backend the create is exclusive, so racing publishers cannot both win.
- **``blobs`` is content-addressed and undeletable** (:class:`ImmutableBlobs`,
  a ``dol.content.ContentAddressedStore``): every file of every version once,
  keyed by its SHA-256; a key can never point at changed bytes, and a blob a
  version pins cannot be deleted from under it.
- **Keys are validated twice** before they become paths: by the id grammars
  (:mod:`an.library.ids`), and by :class:`LocalFiles`' containment check.
- **Nothing is created until the first write.**

>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     lib = build_library_mall(d)
...     sorted(lib)
['blob_rights', 'blobs', 'records', 'versions']
>>> mem = build_library_mall(records={}, versions={}, blobs={})  # all in memory
>>> ref = mem["blobs"].add(b"<svg/>")
>>> mem["blobs"][ref.item_id]
b'<svg/>'
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

from dol import filt_iter, wrap_kvs
from dol.content import ContentAddressedStore

from an.library.ids import AssetIdError, check_asset_id, check_version_label
from an.library.root import CORE_PACKAGE, LIBRARY_DIRNAME, library_root

__all__ = [
    "LIBRARY_STORES",
    "ImmutableBlobs",
    "LocalFiles",
    "VersionExistsError",
    "WriteOnce",
    "build_library_mall",
    "canonical_json",
    "version_key",
    "split_version_key",
]

#: The three stores every library mall holds.
LIBRARY_STORES: tuple[str, ...] = ("records", "versions", "blobs")
#: Derived stores beside them: rebuildable from the versions (``reindex``).
#: ``blob_rights``: ``sha256 -> {asset: statement}``, the strictest thing each
#: asset says about those bytes (:mod:`an.library.floor`).
DERIVED_STORES: tuple[str, ...] = ("blob_rights",)
#: The separator between an asset id and its version label in a ``versions`` key.
VERSION_KEY_SEP: str = "@"
#: Extension of the JSON documents on disk.
JSON_EXT: str = ".json"
#: Leading hex digits of a blob's hash used as its fan-out folder (``blobs/<aa>/``),
#: so no single folder holds every file of a large library.
BLOB_FANOUT: int = 2
#: Indentation of the JSON written to disk — readable diffs, stable bytes.
JSON_INDENT: int = 2

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class VersionExistsError(KeyError):
    """A write-once key was written twice, or deleted. Versions are immutable."""

    def __str__(self) -> str:  # KeyError's repr-quoting hides the sentence
        return str(self.args[0]) if self.args else "version exists"


def canonical_json(obj: Any, *, indent: int | None = None) -> str:
    """JSON with sorted keys and no locale or platform dependence.

    With ``indent=None`` it is the compact form hashed for a manifest; with an
    indent it is the on-disk form (same content, readable).

    >>> canonical_json({"b": 1, "a": [1, 2]})
    '{"a":[1,2],"b":1}'
    """
    if indent is None:
        return json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    return json.dumps(obj, sort_keys=True, indent=indent, ensure_ascii=False)


def _json_bytes(obj: Any) -> bytes:
    return (canonical_json(obj, indent=JSON_INDENT) + "\n").encode("utf-8")


def _json_obj(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"))


def version_key(asset_id: str, version: str) -> str:
    """The ``versions`` key of one version.

    >>> version_key("character.alice", "v002")
    'character.alice@v002'
    """
    return f"{check_asset_id(asset_id)}{VERSION_KEY_SEP}{check_version_label(version)}"


def split_version_key(key: str) -> tuple[str, str]:
    """``(asset_id, version)`` of a ``versions`` key, validated.

    >>> split_version_key("character.alice@v002")
    ('character.alice', 'v002')
    """
    asset_id, sep, version = str(key).rpartition(VERSION_KEY_SEP)
    if not sep:
        raise AssetIdError(f"versions key {key!r} is not '<asset_id>@<vNNN>'")
    return check_asset_id(asset_id), check_version_label(version)


def _check_sha(key: str) -> str:
    if not isinstance(key, str) or not _SHA256_RE.match(key):
        raise KeyError(f"blob key {key!r} is not a lowercase hex SHA-256 digest")
    return key


class WriteOnce(MutableMapping):
    """A mapping whose keys, once written, can be neither overwritten nor deleted.

    Wraps any injected ``MutableMapping``. Rewriting a key with the *same* value
    is refused too: immutability is about the key, and a silent no-op would hide
    a caller that believes it is replacing something.

    **Atomicity.** When the wrapped store offers ``create_only(key, value)`` — an
    exclusive create that raises :class:`VersionExistsError` if the key exists —
    every write goes through it, so two publishers racing for one key cannot both
    win. The default folder backend has one (a hard link of a fully written temp
    file); an S3 backend would map it to a conditional put (``If-None-Match: *``).
    A store without it gets a check-then-set, which is correct for one writer.

    >>> versions = WriteOnce({})
    >>> versions["character.a@v001"] = {"x": 1}
    >>> versions["character.a@v001"] = {"x": 2}  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    VersionExistsError: ...
    """

    def __init__(self, store: MutableMapping) -> None:
        self.store = store

    def __getitem__(self, key: str) -> Any:
        return self.store[key]

    def __setitem__(self, key: str, value: Any) -> None:
        create_only = getattr(self.store, "create_only", None)
        if create_only is not None:
            create_only(key, value)
            return
        if key in self.store:
            raise VersionExistsError(
                f"{key!r} is already published; versions are immutable — "
                "publish a new version instead"
            )
        self.store[key] = value

    def __delitem__(self, key: str) -> None:
        raise VersionExistsError(
            f"refusing to delete {key!r}: versions are immutable, and projects pin them"
        )

    def __iter__(self) -> Iterator[str]:
        return iter(self.store)

    def __len__(self) -> int:
        return len(self.store)

    def __contains__(self, key: object) -> bool:
        return key in self.store

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.store!r})"


class ImmutableBlobs(ContentAddressedStore):
    """The content-addressed blob store, with deletion refused.

    Versions are write-once and pin their files by hash, so deleting a blob
    would leave a published version pointing at nothing. Reclaiming unreferenced
    blobs is a maintenance job (a garbage collector that counts references), not
    a mapping operation.

    >>> blobs = ImmutableBlobs({})
    >>> ref = blobs.add(b"x")
    >>> del blobs[ref.item_id]  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    VersionExistsError: ...
    """

    def __delitem__(self, k: str) -> None:
        raise VersionExistsError(
            f"refusing to delete blob {k!r}: published versions pin their files by hash"
        )


#: Prefix of the temporary files a write goes through (never listed as keys).
TMP_PREFIX: str = ".tmp-"


class LocalFiles(MutableMapping):
    """``relative/posix/path -> bytes`` under one folder, with atomic, contained writes.

    The default backend of every library store:

    - **contained**: a key that would resolve outside the folder (``..``, an
      absolute path, a drive) raises ``KeyError`` and never touches the disk;
    - **atomic**: a write goes to a temp file in the target folder and is moved
      into place with ``os.replace``, so a crash never leaves a torn document;
    - **create-only** (:meth:`create_only`): a hard link of the fully written temp
      file, which fails if the target exists — the primitive :class:`WriteOnce`
      uses so two publishers cannot both create one version;
    - **lazy**: nothing is created until the first write, so opening (or
      mistyping) a library never creates folders.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     f = LocalFiles(d + "/lib")
    ...     f["a/b.json"] = b"{}"
    ...     sorted(f), f["a/b.json"]
    (['a/b.json'], b'{}')
    """

    def __init__(self, root: str | os.PathLike) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or not key or "\\" in key or ":" in key:
            raise KeyError(f"invalid file key {key!r}")
        parts = key.split("/")
        if any(p in ("", ".", "..") or p.startswith(TMP_PREFIX) for p in parts):
            raise KeyError(f"file key {key!r} does not stay inside its store")
        return self.root.joinpath(*parts)

    def __getitem__(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            raise KeyError(key) from None

    def _temp(self, path: Path, data: bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=TMP_PREFIX, dir=path.parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        return Path(tmp)

    def __setitem__(self, key: str, data: bytes) -> None:
        path = self._path(key)
        os.replace(self._temp(path, bytes(data)), path)

    def create_only(self, key: str, data: bytes) -> None:
        """Write ``key`` only if it does not exist — atomically, in one step."""
        path = self._path(key)
        exists = VersionExistsError(
            f"{key!r} already exists; versions are immutable — publish a new version"
        )
        tmp = self._temp(path, bytes(data))
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise exists from None
        except OSError:
            # No hard links here (exFAT, some SMB mounts): an exclusive open is
            # still a create-only, at the cost of a reader seeing a file being
            # filled; the temp copy is written first so that window is short.
            try:
                with open(path, "xb") as fh:
                    fh.write(tmp.read_bytes())
            except FileExistsError:
                raise exists from None
        finally:
            tmp.unlink(missing_ok=True)

    def __delitem__(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            raise KeyError(key) from None

    def __contains__(self, key: object) -> bool:
        try:
            return self._path(key).is_file()  # type: ignore[arg-type]
        except KeyError:
            return False

    def __iter__(self) -> Iterator[str]:
        if not self.root.is_dir():
            return
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root).as_posix()
            if path.is_file() and not any(
                p.startswith(TMP_PREFIX) for p in rel.split("/")
            ):
                yield rel

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self.root)!r})"


def _codec_store(
    files: LocalFiles, *, depth: int, id_of_key, key_of_id, json_values: bool
) -> MutableMapping:
    """``files`` seen through ``dol``: a key transform, a filter on depth, a codec."""
    codec = (
        {"data_of_obj": _json_bytes, "obj_of_data": _json_obj} if json_values else {}
    )
    store = wrap_kvs(
        filt_iter(files, filt=lambda p: p.count("/") == depth),
        id_of_key=id_of_key,
        key_of_id=key_of_id,
        **codec,
    )
    return store


def _records_store(folder: Path) -> MutableMapping:
    return _codec_store(
        LocalFiles(folder),
        depth=0,
        id_of_key=lambda asset_id: check_asset_id(asset_id) + JSON_EXT,
        key_of_id=lambda path: path[: -len(JSON_EXT)],
        json_values=True,
    )


def _versions_store(folder: Path) -> MutableMapping:
    def id_of_key(key: str) -> str:
        asset_id, version = split_version_key(key)
        return f"{asset_id}/{version}{JSON_EXT}"

    def key_of_id(path: str) -> str:
        asset_id, _, file = path.partition("/")
        return f"{asset_id}{VERSION_KEY_SEP}{file[: -len(JSON_EXT)]}"

    files = LocalFiles(folder)
    store = _codec_store(
        files, depth=1, id_of_key=id_of_key, key_of_id=key_of_id, json_values=True
    )

    # The exclusive create, exposed through the codec so WriteOnce can use it.
    def create_only(key: str, value: Any) -> None:
        try:
            files.create_only(id_of_key(key), _json_bytes(value))
        except VersionExistsError:
            raise VersionExistsError(
                f"{key!r} is already published; versions are immutable — "
                "publish a new version instead"
            ) from None

    store.create_only = create_only
    return WriteOnce(store)


def _blobs_backend(folder: Path) -> MutableMapping:
    def id_of_key(sha: str) -> str:
        sha = _check_sha(sha)
        return f"{sha[:BLOB_FANOUT]}/{sha}"

    return _codec_store(
        LocalFiles(folder),
        depth=1,
        id_of_key=id_of_key,
        key_of_id=lambda path: path.rpartition("/")[2],
        json_values=False,
    )


def _blob_rights_store(folder: Path) -> MutableMapping:
    def id_of_key(sha: str) -> str:
        sha = _check_sha(sha)
        return f"{sha[:BLOB_FANOUT]}/{sha}{JSON_EXT}"

    return _codec_store(
        LocalFiles(folder),
        depth=1,
        id_of_key=id_of_key,
        key_of_id=lambda path: path.rpartition("/")[2][: -len(JSON_EXT)],
        json_values=True,
    )


def build_library_mall(
    root: str | os.PathLike | None = None,
    *,
    package: str = CORE_PACKAGE,
    **overrides: MutableMapping,
) -> dict[str, MutableMapping]:
    """The library mall of ``package``: ``records``, ``versions`` (write-once), ``blobs`` (CAS).

    root: the package's data root (default: resolved by
        :func:`an.library.root.library_root` — ``root`` → ``<PKG>_HOME`` → the
        platform data folder); the stores live under ``<root>/library/``
    package: whose library this is (``an``, or a genre such as ``cutan``)
    overrides: a store per name to inject instead of the folder default — a
        ``dict`` for tests, an S3 or database mapping later. An injected
        ``versions`` is still made write-once and an injected ``blobs`` still
        content-addressed and undeletable, so injection cannot drop an invariant.

    Nothing is created until the first write: opening a library (or mistyping
    one on a search path) leaves the disk as it was.
    """
    unknown = set(overrides) - set(LIBRARY_STORES) - set(DERIVED_STORES)
    if unknown:
        raise TypeError(
            f"unknown library store(s) {sorted(unknown)}; a library mall holds "
            f"{list(LIBRARY_STORES + DERIVED_STORES)}"
        )
    base: Path | None = None
    in_memory = set(LIBRARY_STORES) <= set(overrides)
    if not in_memory:
        base = library_root(root, package=package) / LIBRARY_DIRNAME

    def _get(name: str, factory) -> MutableMapping:
        return overrides[name] if name in overrides else factory(base / name)

    records = _get("records", _records_store)
    versions = _get("versions", _versions_store)
    if not isinstance(versions, WriteOnce):
        versions = WriteOnce(versions)
    blobs = _get("blobs", _blobs_backend)
    if not isinstance(blobs, ImmutableBlobs):
        blobs = ImmutableBlobs(blobs)
    # A mall whose primary stores are all injected keeps its derived index in
    # memory too, rather than reaching for a folder nobody asked for.
    blob_rights = overrides.get("blob_rights")
    if blob_rights is None:
        blob_rights = {} if in_memory else _blob_rights_store(base / "blob_rights")
    return {
        "records": records,
        "versions": versions,
        "blobs": blobs,
        "blob_rights": blob_rights,
    }
