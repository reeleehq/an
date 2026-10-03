"""Cache keys for build stages: canonical digests, the project fallback, keyers.

ADR 0004 decision 2: *every key covers everything that changes the output*, and
``shot.id`` is never one of them (pillar 11). A shot key is composed from NAMED
parts, each a sha256 hex digest, so a re-render can say which input moved:

========== ===================================================================
part       what it covers
========== ===================================================================
renderer   the backend's registered identity: its class and its keyer, by
           qualified name (two implementations never share an entry)
impl       :data:`SHOT_KEY_IMPL_VERSION`, the salt bumped when the key's own
           composition changes
assets     the asset entries the shot's compile READ (ADR 0004 decision 3,
           an#316): :func:`an.build.reads.read_digests`, for a renderer
           whose keyer is registered with ``records_reads=True`` — and for
           any other, every asset in the project, the first slice's
           fallback (an opaque Manim source opens files by path, an#291):
           :func:`every_asset_digest`
project    what EVERY shot depends on, project-wide: by default the
           project-root files (the library lockfile),
           :func:`project_dependencies`
environment the machine's render environment, from the renderer's registered
           probe — separate, so a machine change invalidates renders without
           pretending the content changed
(keyer)    whatever the renderer's registered :data:`ShotKeyer` returns — for
           the cut-out renderer: the compiled document, its textures' bytes,
           the easing versions it names, the audio it muxes, the runtime,
           the render path's Python source and every render knob
           (`an.stage.cache_key`)
========== ===================================================================

The core names no renderer: a backend joins by :func:`register_shot_keyer`. A
renderer with no keyer is never cached, which is the safe default — an opaque
shot is re-rendered, never reused on a guess.

>>> canonical_digest({"b": 1, "a": [1, 2]}) == canonical_digest({"a": [1, 2], "b": 1})
True
>>> len(compose_shot_key({"renderer": canonical_digest("cutout")}))
64
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The key's own version — the ``impl_version`` salt of `nw.Transform` and of
#: `burns.RESOLVER_IMPL_VERSION` ("a lock, not a receipt"). Bump it when the
#: COMPOSITION of a key changes (a part added, renamed or re-spelled). It is
#: NOT how a renderer's code changes reach the key — a hand-bumped constant is
#: one someone forgets — that is each keyer's ``code`` part, a digest of the
#: render path's source. Bumping it orphans every entry; nothing is deleted
#: (decision 6).
SHOT_KEY_IMPL_VERSION: int = 2  # 2: `assets` (recorded reads) beside `project` (an#316)

#: The mall's ASSET stores: the art the compiler reads (characters,
#: environments, props, styles) and the two the audio path reads (voices,
#: sounds). What a recording view records (:mod:`an.build.reads`), and what
#: "every asset in the project" means for decision 3's fallback. The scene
#: document is deliberately NOT here — each shot's own slice reaches its key
#: through its compiled document, which is what lets an edit to one shot
#: re-render only that shot.
PROJECT_ASSET_STORES: tuple[str, ...] = (
    "characters",
    "environments",
    "props",
    "styles",
    "voices",
    "sounds",
)

#: Files at the project ROOT that every shot depends on, whether or not a mall
#: store exposes them. ``assets.lock.json`` is the asset library's lockfile of
#: pinned library versions (ADR 0005, P5): a re-pin changes what is checked out,
#: so it must move every key — and it must do so before (and independently of)
#: its registration in the mall (an#240). Read by path, through
#: :func:`project_root_files_digest`; an absent file is recorded as absent.
PROJECT_ROOT_FILES: tuple[str, ...] = ("assets.lock.json",)

#: File names under an asset root that are never assets: an OS's folder
#: metadata must not re-render a film.
IGNORED_ASSET_NAME_PREFIXES: tuple[str, ...] = (".",)

#: A part's value when the thing it digests is absent: a missing texture, an
#: audio ref the store does not hold. Still deterministic, and different from
#: any present value, so a part that later appears re-renders.
ABSENT: str = "absent"


def _jsonable(obj: Any) -> Any:
    """``json.dumps``' ``default``: paths, tuples-in-sets, models, the rest by repr."""
    if isinstance(obj, Path):
        return obj.as_posix()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=repr)
    if isinstance(obj, bytes):
        return {"sha256": bytes_digest(obj)}
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    return repr(obj)


def canonical_json(obj: Any) -> str:
    """``obj`` as sorted, whitespace-free JSON — the one spelling every digest hashes.

    >>> canonical_json({"b": (1, 2), "a": None})
    '{"a":null,"b":[1,2]}'
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), default=_jsonable, allow_nan=False
    )


def bytes_digest(data: bytes) -> str:
    """The hex sha256 of ``data``.

    >>> bytes_digest(b"")[:8]
    'e3b0c442'
    """
    return hashlib.sha256(data).hexdigest()


def canonical_digest(obj: Any) -> str:
    """The hex sha256 of :func:`canonical_json` of ``obj``."""
    return bytes_digest(canonical_json(obj).encode("utf-8"))


def file_digest(path: str | Path) -> str:
    """The hex sha256 of a file's bytes, read NOW.

    Deliberately unmemoised. A (path, mtime, size) memo — `an.stage.raster`'s, which
    is fine for a texture alias inside one compile — let a same-size edit whose
    mtime was restored (``cp -p``, ``rsync -t``, ``tar x``, a sync client) be
    served stale from cache in a long-running process (an#243 review, S2). A
    cache KEY is only as good as its weakest input, so every byte is read on
    every render; on the golden corpus the whole project digest is under 10 ms.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def compose_shot_key(parts: Mapping[str, str]) -> str:
    """The shot key: one digest over the named parts and the key's own version.

    The parts are a MAPPING so the record can keep them by name, and a
    re-render can be explained ("``textures`` moved") rather than merely
    observed.
    """
    return canonical_digest({"impl": SHOT_KEY_IMPL_VERSION, "parts": dict(parts)})


# -----------------------------------------------------------------------------
# Decision 3's fallback: every shot depends on every asset in its project
# -----------------------------------------------------------------------------


def _iter_asset_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part.startswith(IGNORED_ASSET_NAME_PREFIXES) for part in rel.parts):
            continue
        if path.is_file():
            yield path


def store_digest(store: Any) -> str:
    """A digest of one store's whole content.

    A filesystem store (one exposing ``_root``) is digested from its FILES,
    sidecars included — a character's ``meta.json`` is not its art; the SVG
    parts beside it are. That reads behind the mapping, which is ADR 0004's gap
    3 ("art bypasses the mall"), and it is exactly why this is the fallback:
    once art is read through the stores (the asset library, ADR 0005), a
    read-recording view replaces it with the keys a shot actually read. Any
    other mapping is digested from its items.

    >>> store_digest({"a": {"x": 1}}) == store_digest({"a": {"x": 1}})
    True
    >>> store_digest({"a": {"x": 1}}) == store_digest({"a": {"x": 2}})
    False
    """
    root = getattr(store, "_root", None)
    if root is not None and Path(root).is_dir():
        root = Path(root)
        return canonical_digest(
            [
                [p.relative_to(root).as_posix(), file_digest(p)]
                for p in _iter_asset_files(root)
            ]
        )
    items = []
    for key in sorted(store, key=str):
        try:
            value = store[key]
        except Exception as e:  # noqa: BLE001 — an unreadable entry is a fact, not a crash
            value = {"unreadable": f"{type(e).__name__}: {e}"}
        items.append([str(key), canonical_digest(value)])
    return canonical_digest(items)


def project_root_files_digest(
    project_root: str | Path, *, files: Iterable[str] = PROJECT_ROOT_FILES
) -> dict[str, str]:
    """``{name: sha256 or ABSENT}`` for the project-root files every shot depends on.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     project_root_files_digest(d, files=["assets.lock.json"])
    {'assets.lock.json': 'absent'}
    """
    root = Path(project_root)
    return {
        name: (file_digest(root / name) if (root / name).is_file() else ABSENT)
        for name in files
    }


def project_assets_digest(
    mall: Mapping[str, Any],
    *,
    stores: Iterable[str] = PROJECT_ASSET_STORES,
    project_root: str | Path | None = None,
    root_files: Iterable[str] = PROJECT_ROOT_FILES,
) -> str:
    """One digest over every asset store of the project (ADR 0004 decision 3).

    The first slice's dependency edge for every shot: safe — no asset can change
    without every shot's key moving — at the price of the per-character saving,
    which read recording buys back. A store the mall does not have is recorded
    as absent rather than skipped, so adding one later moves the digest.

    With ``project_root``, the files in ``root_files`` (the library lockfile)
    are hashed by PATH as well — so a re-pin moves every key whether or not
    the mall has a store for the file yet.

    >>> a = project_assets_digest({"characters": {"c": {"v": 1}}}, stores=["characters"])
    >>> b = project_assets_digest({"characters": {"c": {"v": 2}}}, stores=["characters"])
    >>> a == b
    False
    """
    digest: dict[str, Any] = {
        name: (store_digest(mall[name]) if mall.get(name) is not None else ABSENT)
        for name in stores
    }
    if project_root is not None:
        digest["root_files"] = project_root_files_digest(project_root, files=root_files)
    return canonical_digest(digest)


def project_dependencies(
    mall: Mapping[str, Any], *, project_root: str | Path | None = None
) -> str:
    """What every shot depends on project-wide: the project-root files
    (:data:`PROJECT_ROOT_FILES`, the library lockfile), read by path. A re-pin
    changes what is checked out, so it moves every key, conservatively.

    >>> project_dependencies({}) == project_dependencies({"props": {"a": 1}})
    True
    """
    return canonical_digest(
        project_root_files_digest(project_root) if project_root is not None else ABSENT
    )


def every_asset_digest(
    mall: Mapping[str, Any], *, project_root: str | Path | None = None
) -> str:
    """Every asset in the project (decision 3's fallback), without the root
    files — those are :func:`project_dependencies`'. The ``assets`` part of a
    shot whose keyer cannot vouch for its reads.

    >>> every_asset_digest({"props": {"a": 1}}) != every_asset_digest({"props": {"a": 2}})
    True
    """
    return project_assets_digest(mall)


# -----------------------------------------------------------------------------
# Renderer keyers: how a backend says what its shot render reads
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ShotKeyInputs:
    """What a renderer's keyer returns for one shot.

    ``parts`` are named sha256 hex digests (the key's content half); the engine
    adds ``renderer``, ``project`` and ``environment``. ``compile_s`` is the
    wall time of the compile the keyer ran to get its digest, or ``None`` for a
    renderer that has no compile stage.
    """

    parts: Mapping[str, str]
    compile_s: float | None = None
    #: Diagnostics a keyer wants on the record beside the digests — never part
    #: of the key (the digests are).
    details: Mapping[str, Any] = field(default_factory=dict)


#: ``keyer(shot, ctx) -> ShotKeyInputs``. Raises what the render itself would
#: raise for the same inputs (a compile error, an invalid knob), so a bad shot
#: fails before any browser launches.
ShotKeyer = Callable[[Any, Any], ShotKeyInputs]

#: ``probe() -> Mapping``: the renderer's environment record. Called once per
#: process per renderer (see `ShotCache`), because a browser probe costs a
#: launch.
EnvironmentProbe = Callable[[], Mapping[str, Any]]


#: ``part(shot, ctx) -> str``: one more named digest for a renderer's key —
#: the additive seam for an input read OUTSIDE the compiled document (a genre's
#: side file, a vocabulary entry's version). See :func:`register_shot_key_part`.
ShotKeyPart = Callable[[Any, Any], str]


def callable_identity(obj: Any) -> str:
    """``module.qualname`` of a function or class (of an instance: of its type).

    >>> callable_identity(callable_identity)
    'an.build.keys.callable_identity'
    """
    target = obj if isinstance(obj, type) or callable(obj) and hasattr(obj, "__qualname__") else type(obj)
    return f"{getattr(target, '__module__', '?')}.{getattr(target, '__qualname__', repr(target))}"


@dataclass(frozen=True)
class _KeyerEntry:
    keyer: ShotKeyer
    environment: EnvironmentProbe | None
    #: The renderer CLASS this keyer describes. A renderer of any other class —
    #: a subclass that adds a watermark, a test double that borrowed the name —
    #: gets no keyer, and so is never cached: the keyer's claim "this is
    #: everything the render reads" is about one implementation (review S4).
    renderer_type: type | None = None
    parts: dict[str, ShotKeyPart] = field(default_factory=dict)
    #: The keyer's claim that everything its shot reads from the project's
    #: ASSET stores, it reads through ``ctx.mall`` — so the engine may hand it
    #: a recording view and key the shot on exactly those reads (an#316).
    #: ``False`` (an opaque source that opens files by path) keeps the
    #: whole-project dependency.
    records_reads: bool = False

    def identity(self) -> str:
        """What the ``renderer`` part digests: the class and the keyer, by name."""
        return canonical_json(
            {
                "renderer_type": callable_identity(self.renderer_type)
                if self.renderer_type is not None
                else None,
                "keyer": callable_identity(self.keyer),
                "parts": {k: callable_identity(v) for k, v in sorted(self.parts.items())},
            }
        )


_KEYERS: dict[str, _KeyerEntry] = {}


class ShotKeyerRegistrationError(ValueError):
    """A shot keyer or key part was registered twice, or collides with another."""


def register_shot_keyer(
    renderer_name: str,
    keyer: ShotKeyer,
    *,
    environment: EnvironmentProbe | None = None,
    renderer_type: type | None = None,
    records_reads: bool = False,
    replace: bool = False,
) -> None:
    """Declare how shots of ``renderer_name`` are keyed, and how its machine is probed.

    The registration seam for every backend (cut-out here; Manim's opaque
    shots, keyed on source hash + Manim version + quality, are the next).
    ``renderer_type`` binds the keyer to one renderer class: a renderer whose
    type is not exactly it is never cached. ``records_reads=True`` claims
    that every asset the shot depends on is read through ``ctx.mall`` (or is
    already digested by one of the keyer's parts): the engine then keys the
    shot on the entries it read rather than on the whole project. A second registration for a name
    is refused unless ``replace=True`` — a silent replacement would drop the
    first keyer's parts from every key without anyone saying so.
    """
    old = _KEYERS.get(renderer_name)
    # Compared WITH the registered parts, which a re-registration keeps: a
    # keyer whose parts were added since (an#248's `vocabulary`) is still the
    # same keyer.
    new = _KeyerEntry(
        keyer=keyer,
        environment=environment,
        renderer_type=renderer_type,
        parts=dict(old.parts) if old is not None else {},
        records_reads=records_reads,
    )
    if old is not None and not replace and old.identity() == new.identity() and (
        callable_identity(old.environment) if old.environment else None
    ) == (callable_identity(environment) if environment else None):
        # The SAME keyer again — a module re-executed by `importlib.reload` or
        # IPython's autoreload. Take the new objects (a reloaded renderer class
        # is a new class), keep the registered parts (an#243 review, R2-4).
        replace = True
    if old is not None and not replace:
        raise ShotKeyerRegistrationError(
            f"a shot keyer for renderer {renderer_name!r} is already registered "
            f"({callable_identity(_KEYERS[renderer_name].keyer)}); pass replace=True "
            "to replace it, or add an input with register_shot_key_part"
        )
    old_parts = dict(_KEYERS[renderer_name].parts) if renderer_name in _KEYERS else {}
    _KEYERS[renderer_name] = _KeyerEntry(
        keyer=keyer,
        environment=environment,
        renderer_type=renderer_type,
        parts=old_parts,
        records_reads=records_reads,
    )


def register_shot_key_part(renderer_name: str, part_name: str, part: ShotKeyPart) -> None:
    """Add one named input to every key of ``renderer_name``'s shots — additively.

    For an input the render reads OUTSIDE its compiled document (whatever
    changes the document is already covered by the ``compiled`` part, with
    early cutoff for free): a genre package's side file, a vocabulary entry's
    version (P7). Refuses a duplicate ``part_name``; a name that collides with
    one of the keyer's own parts is refused when the key is computed.

    A renderer registered LAZILY (the stage, an#247) brings its keyer when the
    renderer registry first loads, so this loads it first -- a genre adding a
    key part at install (``cutan``, P8) needs no prior lookup.
    """
    if renderer_name not in _KEYERS:
        registered_shot_keyers()  # a lazily registered backend brings its keyer
    entry = _KEYERS.get(renderer_name)
    if entry is None:
        raise ShotKeyerRegistrationError(
            f"no shot keyer for renderer {renderer_name!r}; register one first "
            f"(registered: {sorted(_KEYERS)})"
        )
    if part_name in entry.parts:
        raise ShotKeyerRegistrationError(
            f"key part {part_name!r} is already registered for {renderer_name!r}"
        )
    entry.parts[part_name] = part


def shot_keyer_for(renderer: Any) -> _KeyerEntry | None:
    """The keyer that describes ``renderer`` (an instance, or a name), or ``None``.

    ``None`` means the shot is never cached: no keyer for the name, or a
    renderer whose class is not the one the keyer was registered for.
    """
    name = renderer if isinstance(renderer, str) else getattr(renderer, "name", "") or ""
    if name not in _KEYERS:
        registered_shot_keyers()  # a lazily registered backend brings its keyer
    entry = _KEYERS.get(name)
    if entry is None or isinstance(renderer, str):
        return entry
    if entry.renderer_type is not None and type(renderer) is not entry.renderer_type:
        return None
    return entry


def registered_shot_keyers() -> tuple[str, ...]:
    """The renderer names that have a keyer.

    A keyer registers beside its renderer, and a backend behind the import
    firewall registers when the renderer registry first loads it (an#247), so
    this loads the registry first.

    >>> "cutout" in registered_shot_keyers()
    True
    """
    from an.adapters import list_renderers

    list_renderers()
    return tuple(_KEYERS)
