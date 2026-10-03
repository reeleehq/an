"""Incremental re-processing: content-addressed build stages (ADR 0004).

A draft must stay adjustable without re-processing everything: an edit
re-renders only what depends on it. The first slice is the **shot cache** —
`an render` skips any shot whose key (everything its render reads, digested;
never ``shot.id``) already has an entry, and reuses that entry's mp4.

- :mod:`an.build.keys` — canonical digests, the project-wide fallback
  dependency, and the registry through which a renderer says what its shot
  render reads (:func:`register_shot_keyer`).
- :mod:`an.build.reads` — what a shot read: the recording view of the mall a
  keyer compiles against, and the digests of the entries it saw (an#316).
- :mod:`an.build.shot_cache` — the ``incremental=`` seam
  (:class:`IncrementalEngine`), its built-in engine :class:`ShotCache`, and
  the entries, shaped as ``lacing`` artifacts in a ``lacing.ArtifactStore``.

- :mod:`an.build.gc` — garbage collection: what the current scene and the
  recorded renders reach, and deleting the rest (``an cache gc``,
  ``an cache info``; :mod:`an.build.cli`).

The core names no renderer; the cut-out keyer lives with the cut-out backend
(`an.stage.cache_key`) and registers on its import.

>>> from an.build import ShotCache, resolve_incremental
>>> isinstance(resolve_incremental(True), ShotCache)
True
"""

from an.build.keys import (
    PROJECT_ASSET_STORES,
    PROJECT_ROOT_FILES,
    SHOT_KEY_IMPL_VERSION,
    ShotKeyInputs,
    canonical_digest,
    compose_shot_key,
    project_assets_digest,
    register_shot_keyer,
    registered_shot_keyers,
    shot_keyer_for,
)
from an.build.gc import CacheGcError, cache_info, collect_garbage
from an.build.reads import RecordingMall, read_digests
from an.build.shot_cache import (
    SHOT_CACHE_STORE,
    BuildReport,
    IncrementalEngine,
    ShotCache,
    ShotCacheWarning,
    ShotOutcome,
    ShotPlan,
    default_environment_digest,
    in_memory_shot_cache_store,
    resolve_incremental,
    shot_artifact_type,
    shot_cache_store,
)

__all__ = [
    "PROJECT_ASSET_STORES",
    "PROJECT_ROOT_FILES",
    "RecordingMall",
    "SHOT_CACHE_STORE",
    "SHOT_KEY_IMPL_VERSION",
    "BuildReport",
    "CacheGcError",
    "IncrementalEngine",
    "ShotCache",
    "ShotCacheWarning",
    "ShotKeyInputs",
    "ShotOutcome",
    "ShotPlan",
    "cache_info",
    "canonical_digest",
    "collect_garbage",
    "compose_shot_key",
    "default_environment_digest",
    "in_memory_shot_cache_store",
    "project_assets_digest",
    "read_digests",
    "register_shot_keyer",
    "registered_shot_keyers",
    "resolve_incremental",
    "shot_artifact_type",
    "shot_cache_store",
    "shot_keyer_for",
]
