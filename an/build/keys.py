"""Cache keys for build stages: canonical digests, the project fallback, keyers.

ADR 0004 decision 2: *every key covers everything that changes the output*, and
``shot.id`` is never one of them (pillar 11). A shot key is composed from NAMED
parts, each a sha256 hex digest, so a re-render can say which input moved:

========== ===================================================================
part       what it covers
========== ===================================================================
renderer   the backend's name (two renderers never share an entry)
impl       :data:`SHOT_KEY_IMPL_VERSION`, the salt bumped when the key's own
           composition, or a renderer's unrecorded behaviour, changes
project    every asset in the project (ADR 0004 decision 3's fallback, until
           reads are recorded): :func:`project_assets_digest`
environment the machine's render environment, from the renderer's registered
           probe — separate, so a machine change invalidates renders without
           pretending the content changed
(keyer)    whatever the renderer's registered :data:`ShotKeyer` returns — for
           the cut-out renderer: the compiled document, its textures' bytes,
           the easing versions it names, the audio it muxes, the runtime and
           every render knob (`an.adapters.cutout.cache_key`)
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
#: composition of a key changes, or when a renderer changes its output in a way
#: none of the key's parts records (a capture-path rewrite that moves pixels
#: under an unchanged runtime and unchanged argv). Bumping it orphans every
#: entry; nothing is deleted (decision 6).
SHOT_KEY_IMPL_VERSION: int = 1

#: The mall stores that make up "every asset in the project" for decision 3's
#: fallback: the art the compiler reads (characters, environments, props,
#: styles) and the two the audio path reads (voices, sounds). The scene
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
    """The hex sha256 of a file's bytes, memoised on (path, mtime, size).

    ADR 0004 allows a stat-keyed memo *of a digest*, never as the key itself:
    this is :func:`an.raster.content_digest`, the memo the compiler already
    keys raster textures with, so a file is read once per process per edit.
    """
    from an.raster import content_digest

    return content_digest(path)


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


def project_assets_digest(
    mall: Mapping[str, Any], *, stores: Iterable[str] = PROJECT_ASSET_STORES
) -> str:
    """One digest over every asset store of the project (ADR 0004 decision 3).

    The first slice's dependency edge for every shot: safe — no asset can change
    without every shot's key moving — at the price of the per-character saving,
    which read recording buys back. A store the mall does not have is recorded
    as absent rather than skipped, so adding one later moves the digest.

    >>> a = project_assets_digest({"characters": {"c": {"v": 1}}}, stores=["characters"])
    >>> b = project_assets_digest({"characters": {"c": {"v": 2}}}, stores=["characters"])
    >>> a == b
    False
    """
    return canonical_digest(
        {
            name: (store_digest(mall[name]) if mall.get(name) is not None else ABSENT)
            for name in stores
        }
    )


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


@dataclass(frozen=True)
class _KeyerEntry:
    keyer: ShotKeyer
    environment: EnvironmentProbe | None


_KEYERS: dict[str, _KeyerEntry] = {}


def register_shot_keyer(
    renderer_name: str,
    keyer: ShotKeyer,
    *,
    environment: EnvironmentProbe | None = None,
) -> None:
    """Declare how shots of ``renderer_name`` are keyed, and how its machine is probed.

    The registration seam for every backend (cut-out here; Manim's opaque
    shots, keyed on source hash + Manim version + quality, are the next). A
    later registration for the same name replaces the earlier one.
    """
    _KEYERS[renderer_name] = _KeyerEntry(keyer=keyer, environment=environment)


def shot_keyer_for(renderer_name: str) -> _KeyerEntry | None:
    """The registered keyer of ``renderer_name``, or ``None`` (never cached)."""
    return _KEYERS.get(renderer_name)


def registered_shot_keyers() -> tuple[str, ...]:
    """The renderer names that have a keyer.

    >>> import an.adapters  # registers the built-in renderers and their keyers
    >>> "cutout" in registered_shot_keyers()
    True
    """
    return tuple(_KEYERS)
