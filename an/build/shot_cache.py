"""The content-keyed shot cache: ADR 0004's first slice, behind the ``incremental=`` seam.

``render_project`` asks an *incremental engine*, per shot, for a plan: the
shot's key, and — when an entry with that key exists — the rendered shot to
reuse. It renders only the misses, and hands each fresh render back to be
recorded. The engine is a seam (``incremental=`` on `an.render.render`), and
:class:`ShotCache` is its built-in default; an `nw`-backed engine is the
planned alternative (ADR 0004 decision 5).

**Data model: `lacing`'s** (decision 4). An entry is a :class:`ShotArtifact` —
a ``lacing.Artifact`` (``asset_id`` = sha256 of the mp4, W3C-PROV provenance
whose ``was_derived_from`` lists the key's input digests) plus the named parts
of its key and the timings that produced it. Entries live in a
``lacing.ArtifactStore``: a catalog (``key -> record``) and a content-addressed
blob store, both injected ``dol`` mappings. In a project the store is
``mall["shot_cache"]`` (``artifacts/shot_cache/{catalog,blobs}/``).

**Invalidation is by digest, never by deletion** (decision 6): a changed input
is a different key, and the old entry simply stops being asked for. The
pre-cache ``artifacts/shots/<shot.id>.mp4`` archive is not read. Collecting
unreachable blobs is a separate, explicit command (not in this slice).

>>> from an.build.shot_cache import BuildReport, ShotOutcome
>>> r = BuildReport([ShotOutcome("a", "cutout", "reused", key="k" * 64),
...                  ShotOutcome("b", "cutout", "rendered", key="j" * 64)])
>>> r.summary()
'2 shot(s): 1 rendered (b), 1 reused (a)'
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
import warnings
import zipfile
from collections.abc import Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from an.build.keys import (
    ShotKeyInputs,
    canonical_digest,
    compose_shot_key,
    project_assets_digest,
    shot_keyer_for,
)

if TYPE_CHECKING:  # pragma: no cover - types only
    from an.adapters._base import RenderContext, RenderResult

logger = logging.getLogger("an.build")

#: The mall key of the shot cache.
SHOT_CACHE_STORE: str = "shot_cache"

#: The catalog id suffix of a shot's FRAMES entry (the PNG sequence, zipped),
#: recorded only for a film that is assembled from frames (transitions, a
#: sound layer — `an.assemble`), which cannot be built from an mp4.
FRAMES_SUFFIX: str = ".frames"

#: Bytes per read when a blob is streamed into the store.
STREAM_CHUNK_BYTES: int = 1 << 20

#: Who `ShotArtifact.provenance` attributes the render to (W3C PROV
#: ``wasAttributedTo``; lacing's ``processor:<name>`` convention).
PROVENANCE_AGENT: str = "processor:an"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

ShotStatus = Literal["rendered", "reused", "uncached"]


# -----------------------------------------------------------------------------
# The record
# -----------------------------------------------------------------------------


def _artifact_base():
    from lacing import Artifact

    return Artifact


def _make_record_type():
    from pydantic import Field

    Artifact = _artifact_base()

    class ShotArtifact(Artifact):
        """A cached shot render: a ``lacing.Artifact`` plus the key it answers.

        ``inputs`` are the key's named parts (each a sha256 hex digest), so a
        record says WHAT it was rendered from, not merely that it was. Unknown
        fields are ignored on read, so a newer writer's record stays readable.
        """

        model_config = {"frozen": True, "extra": "ignore"}

        shot_key: str = Field(..., description="The key this entry answers.")
        role: Literal["mp4", "frames"] = "mp4"
        shot_id: str = Field("", description="The author's id. Informational: never a key.")
        renderer: str = ""
        inputs: dict[str, str] = Field(default_factory=dict)
        timings: dict[str, float] = Field(default_factory=dict)
        render_provenance: dict[str, Any] = Field(default_factory=dict)

    return ShotArtifact


_RECORD_TYPE = None


def shot_artifact_type():
    """The record type (`lacing.Artifact` subclass), built on first use."""
    global _RECORD_TYPE
    if _RECORD_TYPE is None:
        _RECORD_TYPE = _make_record_type()
    return _RECORD_TYPE


def shot_cache_store(root: str | Path) -> Any:
    """A filesystem shot cache under ``root``: ``catalog/`` + ``blobs/`` (lacing's layout)."""
    from lacing import ArtifactStore

    return ArtifactStore.from_directory(root, record_type=shot_artifact_type())


def in_memory_shot_cache_store() -> Any:
    """A shot cache held in dicts — for tests, and for a mall with no disk."""
    from lacing import ArtifactStore

    return ArtifactStore.in_memory()


# -----------------------------------------------------------------------------
# What the engine reports
# -----------------------------------------------------------------------------


@dataclass
class ShotOutcome:
    """What happened to one shot in one render, with its wall times (seconds).

    ``key_s`` is the whole key computation, of which ``compile_s`` is the
    compile; ``render_s`` is this render's wall time (``None`` when reused) and
    ``cached_render_s`` the wall time of the render being reused.
    """

    shot_id: str
    renderer: str
    status: ShotStatus
    key: str | None = None
    reason: str = ""
    key_s: float | None = None
    compile_s: float | None = None
    render_s: float | None = None
    cached_render_s: float | None = None


@dataclass
class BuildReport:
    """Every shot's outcome, in timeline order."""

    outcomes: list[ShotOutcome] = field(default_factory=list)

    @property
    def rendered(self) -> list[str]:
        return [o.shot_id for o in self.outcomes if o.status != "reused"]

    @property
    def reused(self) -> list[str]:
        return [o.shot_id for o in self.outcomes if o.status == "reused"]

    def summary(self) -> str:
        n = len(self.outcomes)
        ren, reu = self.rendered, self.reused
        return (
            f"{n} shot(s): {len(ren)} rendered ({', '.join(ren) or '-'}), "
            f"{len(reu)} reused ({', '.join(reu) or '-'})"
        )

    def timing_table(self) -> str:
        """A Markdown table of the per-shot wall times."""

        def s(x: float | None) -> str:
            return "" if x is None else f"{x:.3f}"

        rows = [
            "| shot | status | compile s | key s | render s | cached render s |",
            "|---|---|---|---|---|---|",
        ]
        for o in self.outcomes:
            rows.append(
                f"| {o.shot_id} | {o.status} | {s(o.compile_s)} | {s(o.key_s)} "
                f"| {s(o.render_s)} | {s(o.cached_render_s)} |"
            )
        return "\n".join(rows)


@dataclass
class ShotPlan:
    """The engine's answer for one shot: its key, and what to reuse if anything."""

    shot_id: str
    renderer: str
    key: str | None
    inputs: dict[str, str] = field(default_factory=dict)
    cached: "RenderResult | None" = None
    reason: str = ""
    key_s: float | None = None
    compile_s: float | None = None
    cached_render_s: float | None = None
    needs_frames: bool = False


# -----------------------------------------------------------------------------
# The seam
# -----------------------------------------------------------------------------


@runtime_checkable
class IncrementalEngine(Protocol):
    """The ``incremental=`` seam of `an.render.render` (ADR 0004 decision 5).

    ``begin`` once per render with the project mall (and its root, for the
    root files every shot depends on); ``plan`` once per shot,
    BEFORE any shot renders (in the calling thread); ``record`` once per shot
    that was rendered (possibly from a worker thread); ``finish`` returns the
    report.
    """

    def begin(
        self, mall: Mapping[str, Any], *, project_root: Path | None = None
    ) -> None: ...

    def plan(
        self,
        shot: Any,
        renderer: Any,
        ctx: "RenderContext",
        *,
        needs_frames: bool = False,
        force: bool = False,
    ) -> ShotPlan: ...

    def record(self, plan: ShotPlan, result: "RenderResult", *, render_s: float) -> None: ...

    def finish(self) -> BuildReport: ...


_ENVIRONMENTS: dict[str, str] = {}


def default_environment_digest(renderer_name: str) -> str:
    """The digest of ``renderer_name``'s registered environment probe, once per process.

    Once, because the cut-out probe launches a browser (~1 s); a machine does
    not change under a running process. A renderer with no probe has the
    empty environment.
    """
    if renderer_name not in _ENVIRONMENTS:
        entry = shot_keyer_for(renderer_name)
        record = entry.environment() if entry and entry.environment else {}
        _ENVIRONMENTS[renderer_name] = canonical_digest(record)
    return _ENVIRONMENTS[renderer_name]


class ShotCache:
    """The built-in engine: look a shot's key up in an ArtifactStore; record misses.

    ``store`` is the injected ``lacing.ArtifactStore``; ``None`` means the
    mall's ``shot_cache`` (resolved in :meth:`begin`), and a mall without one
    renders every shot. ``environment(renderer_name) -> digest`` is the
    environment seam — injectable so a test (or a remote-render backend) can
    state its machine rather than probe this one. ``project_digest`` is
    decision 3's fallback dependency; pass ``False`` to key a shot on what its
    compiled document and textures name alone (what read recording will make
    the default).

    After a render, :attr:`report` holds what happened to each shot.
    """

    def __init__(
        self,
        store: Any = None,
        *,
        environment: Any = default_environment_digest,
        project_digest: bool = True,
    ) -> None:
        self.store = store
        self.environment = environment
        self.project_digest = project_digest
        self.report = BuildReport()
        self._store = store
        self._project: str | None = None
        self._outcomes: dict[int, ShotOutcome] = {}
        self._order: list[int] = []

    # -- the protocol ------------------------------------------------------

    def begin(
        self, mall: Mapping[str, Any], *, project_root: Path | None = None
    ) -> None:
        self._store = self.store if self.store is not None else mall.get(SHOT_CACHE_STORE)
        self._project = (
            project_assets_digest(mall, project_root=project_root)
            if self.project_digest
            else None
        )
        self._outcomes = {}
        self._order = []
        self.report = BuildReport()

    def plan(
        self,
        shot: Any,
        renderer: Any,
        ctx: "RenderContext",
        *,
        needs_frames: bool = False,
        force: bool = False,
    ) -> ShotPlan:
        name = getattr(renderer, "name", "") or ""
        entry = shot_keyer_for(name)
        if entry is None or self._store is None:
            reason = (
                f"no shot keyer registered for renderer {name!r}"
                if entry is None
                else "no shot cache store in the mall"
            )
            plan = ShotPlan(shot.id, name, key=None, reason=reason)
            self._note(plan, "uncached")
            return plan

        t0 = time.perf_counter()
        inputs: ShotKeyInputs = entry.keyer(shot, ctx)
        parts = {"renderer": canonical_digest(name), **inputs.parts}
        parts["environment"] = self.environment(name)
        if self._project is not None:
            parts["project"] = self._project
        key = compose_shot_key(parts)
        key_s = time.perf_counter() - t0

        plan = ShotPlan(
            shot.id,
            name,
            key=key,
            inputs=parts,
            key_s=key_s,
            compile_s=inputs.compile_s,
            needs_frames=needs_frames,
        )
        # The report lists shots in timeline order, not in the order a thread
        # pool finishes them.
        self._order.append(id(plan))
        if force:
            plan.reason = "forced"
            return plan
        cached, why = self._lookup(plan, ctx)
        if cached is None:
            plan.reason = why
            return plan
        plan.cached = cached
        # The compile's warnings, replayed: this shot will not compile again,
        # and a stand-in (an#33) must stay audible on a reused shot.
        for w in inputs.details.get("warnings", ()):
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
        self._note(plan, "reused")
        return plan

    def record(self, plan: ShotPlan, result: "RenderResult", *, render_s: float) -> None:
        if plan.key is None or self._store is None:
            self._note(plan, "uncached", render_s=render_s)
            return
        timings = {"render_s": render_s}
        if plan.compile_s is not None:
            timings["compile_s"] = plan.compile_s
        if plan.key_s is not None:
            timings["key_s"] = plan.key_s
        try:
            self._save(plan, result, timings)
        except Exception as e:  # noqa: BLE001 — a failed cache write never fails a render
            warnings.warn(
                f"shot {plan.shot_id!r} rendered, but its cache entry could not be "
                f"written ({type(e).__name__}: {e}); the next render renders it again",
                ShotCacheWarning,
                stacklevel=2,
            )
        self._note(plan, "rendered", render_s=render_s)

    def finish(self) -> BuildReport:
        self.report = BuildReport(
            [self._outcomes[i] for i in self._order if i in self._outcomes]
        )
        return self.report

    # -- internals ---------------------------------------------------------

    def _note(self, plan: ShotPlan, status: ShotStatus, *, render_s: float | None = None) -> None:
        i = id(plan)
        if i not in self._order:
            self._order.append(i)
        outcome = ShotOutcome(
            shot_id=plan.shot_id,
            renderer=plan.renderer,
            status=status,
            key=plan.key,
            reason=plan.reason,
            key_s=plan.key_s,
            compile_s=plan.compile_s,
            render_s=render_s,
            cached_render_s=plan.cached_render_s,
        )
        self._outcomes[i] = outcome
        logger.info(
            "shot %s: %s%s (key %s, compile %s s, render %s s)",
            plan.shot_id,
            status,
            f" [{plan.reason}]" if plan.reason else "",
            (plan.key or "-")[:12],
            "-" if plan.compile_s is None else f"{plan.compile_s:.3f}",
            "-" if render_s is None else f"{render_s:.3f}",
        )

    def _lookup(self, plan: ShotPlan, ctx: "RenderContext") -> tuple[Any, str]:
        store = self._store
        try:
            record = store.get(plan.key)
        except Exception as e:  # noqa: BLE001 — an unreadable entry is a miss, said
            return None, f"unreadable entry ({type(e).__name__})"
        if record is None:
            return None, "miss"
        if not store.has_blob(record.asset_id):
            return None, "entry without its mp4 blob"
        frames_dir = None
        if plan.needs_frames:
            frames_rec = store.get(plan.key + FRAMES_SUFFIX)
            if frames_rec is None or not store.has_blob(frames_rec.asset_id):
                return None, "frames needed for assembly, not cached"
        from an.adapters._base import RenderResult

        out_dir = Path(ctx.work_dir) / "shot_cache" / plan.key[:16]
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
        mp4 = out_dir / f"{plan.shot_id}.mp4"
        mp4.write_bytes(store.get_blob(record.asset_id))
        manifest: list[Path] = []
        if plan.needs_frames:
            frames_dir = out_dir / "frames"
            frames_dir.mkdir()
            with tempfile.TemporaryFile() as tmp:
                tmp.write(store.get_blob(frames_rec.asset_id))
                tmp.seek(0)
                with zipfile.ZipFile(tmp) as zf:
                    zf.extractall(frames_dir)
            manifest = sorted(frames_dir.glob("*.png"))
        plan.cached_render_s = record.timings.get("render_s")
        provenance = dict(record.render_provenance)
        provenance["shot_cache"] = {"status": "reused", "key": plan.key}
        return (
            RenderResult(
                mp4_path=mp4,
                duration=record.duration_s if record.duration_s is not None else 0.0,
                frame_manifest=manifest,
                provenance=provenance,
            ),
            "",
        )

    def _save(self, plan: ShotPlan, result: "RenderResult", timings: dict[str, float]) -> None:
        from lacing import Provenance, RationalTime

        store = self._store
        record_type = shot_artifact_type()
        derived = sorted({d for d in plan.inputs.values() if _HEX64.match(d)})

        def provenance() -> Any:
            return Provenance(
                was_generated_by=f"processor:an.render/{plan.renderer}",
                was_attributed_to=PROVENANCE_AGENT,
                was_derived_from=derived,
                generated_at_time=RationalTime.now(),
                activity="derive",
            )

        common = dict(
            shot_key=plan.key,
            shot_id=plan.shot_id,
            renderer=plan.renderer,
            inputs=dict(plan.inputs),
            timings=timings,
        )
        # Frames first, the mp4 record last: the mp4 record is what a lookup
        # asks for, so it must never point at an entry whose parts are missing.
        if plan.needs_frames and result.frame_manifest:
            fd, name = tempfile.mkstemp(suffix=".zip")
            os.close(fd)
            zpath = Path(name)
            try:
                with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_STORED) as zf:
                    for p in result.frame_manifest:
                        zf.write(p, arcname=Path(p).name)
                asset_id = store.put_blob_stream(_chunks(zpath))
                store[plan.key + FRAMES_SUFFIX] = record_type(
                    asset_id=asset_id,
                    kind="binary",
                    mime="application/zip",
                    bytes_size=zpath.stat().st_size,
                    duration_s=float(result.duration),
                    provenance=provenance(),
                    role="frames",
                    **common,
                )
            finally:
                zpath.unlink(missing_ok=True)
        mp4 = Path(result.mp4_path)
        asset_id = store.put_blob_stream(_chunks(mp4))
        store[plan.key] = record_type(
            asset_id=asset_id,
            kind="video",
            mime="video/mp4",
            bytes_size=mp4.stat().st_size,
            duration_s=float(result.duration),
            provenance=provenance(),
            render_provenance=_jsonable_dict(result.provenance),
            **common,
        )


class ShotCacheWarning(UserWarning):
    """The shot cache could not do something it should have; the render still stands."""


def _chunks(path: Path) -> Iterator[bytes]:
    with open(path, "rb") as f:
        while chunk := f.read(STREAM_CHUNK_BYTES):
            yield chunk


def _jsonable_dict(d: Mapping[str, Any]) -> dict[str, Any]:
    import json

    from an.build.keys import canonical_json

    return json.loads(canonical_json(dict(d)))


def resolve_incremental(incremental: Any) -> IncrementalEngine | None:
    """``incremental=`` → an engine, or ``None`` for "render every shot cold".

    ``True`` is a fresh :class:`ShotCache` over the mall's store; ``False`` or
    ``None`` is off; anything else must be an :class:`IncrementalEngine`.

    >>> resolve_incremental(False) is None
    True
    >>> isinstance(resolve_incremental(True), ShotCache)
    True
    """
    if incremental is None or incremental is False:
        return None
    if incremental is True:
        return ShotCache()
    if isinstance(incremental, IncrementalEngine):
        return incremental
    raise TypeError(
        f"incremental must be a bool or an IncrementalEngine (begin/plan/record/"
        f"finish), got {type(incremental).__name__}"
    )


__all__ = [
    "SHOT_CACHE_STORE",
    "BuildReport",
    "IncrementalEngine",
    "ShotCache",
    "ShotCacheWarning",
    "ShotOutcome",
    "ShotPlan",
    "default_environment_digest",
    "in_memory_shot_cache_store",
    "resolve_incremental",
    "shot_artifact_type",
    "shot_cache_store",
]
