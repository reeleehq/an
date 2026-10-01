"""Incremental re-processing: content-addressed build stages (ADR 0004).

A draft must stay adjustable without re-processing everything: an edit
re-renders only what depends on it. The first slice is the **shot cache** —
`an render` skips any shot whose key (everything its render reads, digested;
never ``shot.id``) already has an entry, and reuses that entry's mp4.

- :mod:`an.build.keys` — canonical digests, the project-wide fallback
  dependency, and the registry through which a renderer says what its shot
  render reads (:func:`register_shot_keyer`).
- :mod:`an.build.shot_cache` — the ``incremental=`` seam
  (:class:`IncrementalEngine`), its built-in engine :class:`ShotCache`, and
  the entries, shaped as ``lacing`` artifacts in a ``lacing.ArtifactStore``.

The core names no renderer; the cut-out keyer lives with the cut-out backend
(`an.adapters.cutout.cache_key`) and registers on its import.

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
    "SHOT_CACHE_STORE",
    "SHOT_KEY_IMPL_VERSION",
    "BuildReport",
    "IncrementalEngine",
    "ShotCache",
    "ShotCacheWarning",
    "ShotKeyInputs",
    "ShotOutcome",
    "ShotPlan",
    "canonical_digest",
    "compose_shot_key",
    "default_environment_digest",
    "in_memory_shot_cache_store",
    "project_assets_digest",
    "register_shot_keyer",
    "registered_shot_keyers",
    "resolve_incremental",
    "shot_artifact_type",
    "shot_cache_store",
    "shot_keyer_for",
]
