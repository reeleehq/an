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

An ASSEMBLED film (transitions, a sound layer) is a stream-copy concat of
segments (`an.assemble`, an#260): a shot no transition touches needs only its
mp4, and a shot one touches also needs its *parts* — its body, encoded once,
and the PNGs inside its transition window — a second entry,
``<key>.parts.<code>.h<head>.t<tail>``, of a few MB. So such a film reuses its
shots by default. (The older whole-frames entry, ``<key>.frames``, is read only
by a caller that asks for it with ``needs_frames=True``; the render loop no
longer does.)

Each cached render also records a *root* (``root.<digest>``): which entries a
render of output ``<name>`` under one set of render knobs on one machine used.
Roots are what `an.build.gc` keeps alive, beside what the current scene reaches.

**Invalidation is by digest, never by deletion** (decision 6): a changed input
is a different key, and the old entry simply stops being asked for. The
pre-cache ``artifacts/shots/<shot.id>.mp4`` archive is not read. Collecting
unreachable entries is a separate, explicit command: ``an cache gc``
(:mod:`an.build.gc`).

>>> from an.build.shot_cache import BuildReport, ShotOutcome
>>> r = BuildReport([ShotOutcome("a", "cutout", "reused", key="k" * 64),
...                  ShotOutcome("b", "cutout", "rendered", key="j" * 64, reason="new or changed")])
>>> r.summary()
'2 shot(s): 1 rendered (b), 1 reused (a); not reused: new or changed (b)'
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
    bytes_digest,
    canonical_digest,
    compose_shot_key,
    SHOT_KEY_IMPL_VERSION,
    every_asset_digest,
    project_dependencies,
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

#: The catalog id infix of a shot's PARTS entry (an#260): what an assembled
#: film takes from a shot its transitions touch — its body, encoded once, and
#: the PNGs inside its window. See :func:`parts_entry_id`.
PARTS_INFIX: str = ".parts."

#: The catalog id prefix of a ROOT: what one render used (see :meth:`ShotCache.record_root`).
ROOT_PREFIX: str = "root."

#: Why a shot was not reused, as the render summary says it.
MISS: str = "new or changed"
PARTS_NOT_CACHED: str = "parts at a transition not cached yet"
FRAMES_NOT_CACHED: str = (
    "frames not cached: film has transitions/sound; pass --cache-frames"
)

#: Bytes per read when a blob is streamed into the store.
STREAM_CHUNK_BYTES: int = 1 << 20

#: Who `ShotArtifact.provenance` attributes the render to (W3C PROV
#: ``wasAttributedTo``; lacing's ``processor:<name>`` convention).
PROVENANCE_AGENT: str = "processor:an"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

ShotStatus = Literal["rendered", "reused", "uncached"]


def human_bytes(n: int) -> str:
    """``n`` bytes for a person: 1024-based, one decimal.

    >>> human_bytes(0), human_bytes(1536), human_bytes(5 * 1024**3)
    ('0 B', '1.5 KB', '5.0 GB')
    """
    size, units = float(n), ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"


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
        role: Literal["mp4", "frames", "parts", "root"] = "mp4"
        shot_id: str = Field("", description="The author's id. Informational: never a key.")
        renderer: str = ""
        inputs: dict[str, str] = Field(default_factory=dict)
        #: ``{"store/key": digest}``: the asset entries the shot read (an#316),
        #: the ``assets`` part spelled out, so a re-render can name the asset
        #: that moved. Empty for a shot keyed on the whole project.
        reads: dict[str, str] = Field(default_factory=dict)
        #: The key composition it was written under (`SHOT_KEY_IMPL_VERSION`);
        #: 0 for an entry older than the field.
        key_version: int = 0
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
    #: The shot cache's size after the render, when the engine measured it.
    store_bytes: int | None = None
    store_entries: int | None = None

    @property
    def rendered(self) -> list[str]:
        return [o.shot_id for o in self.outcomes if o.status != "reused"]

    @property
    def reused(self) -> list[str]:
        return [o.shot_id for o in self.outcomes if o.status == "reused"]

    def summary(self) -> str:
        """One line: what was rendered, what reused, and WHY each rendered shot
        was not reused — a cache that silently re-renders everything reads as
        a broken cache (an#243 review, R2-1).

        >>> BuildReport([ShotOutcome("a", "cutout", "uncached", reason=FRAMES_NOT_CACHED)]).summary()
        '1 shot(s): 1 rendered (a), 0 reused (-); not reused: frames not cached: film has transitions/sound; pass --cache-frames (a)'
        """
        n = len(self.outcomes)
        ren, reu = self.rendered, self.reused
        line = (
            f"{n} shot(s): {len(ren)} rendered ({', '.join(ren) or '-'}), "
            f"{len(reu)} reused ({', '.join(reu) or '-'})"
        )
        why: dict[str, list[str]] = {}
        for o in self.outcomes:
            if o.status != "reused":
                why.setdefault(o.reason or "not cacheable", []).append(o.shot_id)
        if why:
            line += "; not reused: " + "; ".join(
                f"{reason} ({', '.join(ids)})" for reason, ids in why.items()
            )
        return line

    def store_line(self) -> str:
        """How big the shot cache is after the render, or ``""`` if unmeasured.

        >>> BuildReport(store_bytes=3 * 1024**2, store_entries=4).store_line()
        '3.0 MB in 4 entries'
        """
        if self.store_bytes is None:
            return ""
        return f"{human_bytes(self.store_bytes)} in {self.store_entries} entries"

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
    #: The asset entries the shot read, digested (``{"store/key": digest}``).
    reads: dict[str, str] = field(default_factory=dict)
    cached: "RenderResult | None" = None
    reason: str = ""
    key_s: float | None = None
    compile_s: float | None = None
    cached_render_s: float | None = None
    needs_frames: bool = False
    #: What an assembled film needs from this shot (`an.assemble.ShotWindow`);
    #: ``None`` for a film that is a plain concat of shot mp4s.
    window: Any = None
    #: The catalog id of this shot's parts entry, when its window is not whole.
    parts_id: str | None = None
    #: The reused parts (`an.assemble.ShotParts`), materialised for this plan.
    parts: Any = None


def machine_id() -> str:
    """A short digest naming this machine (its host name and hardware
    address), so each machine's renders of a synced project keep a root of
    their own. A digest, never the names themselves.

    >>> len(machine_id())
    16
    """
    import platform
    import uuid

    return canonical_digest(["an.machine", platform.node(), uuid.getnode()])[:16]


def project_id(project_root: Path | str | None) -> str:
    """A short digest naming a project by its resolved directory, so two
    projects sharing one cache store keep a root each (``""`` for none).

    >>> project_id(None)
    ''
    >>> len(project_id("."))
    16
    """
    if project_root is None:
        return ""
    return canonical_digest(["an.project", str(Path(project_root).resolve())])[:16]


def parts_entry_id(key: str, window: Any) -> str:
    """The catalog id of the parts entry of shot ``key`` for ``window``.

    The id names the window (the same shot cut for another neighbour is a
    different entry) and the digest of the code that cuts and encodes the parts
    (:func:`parts_code_digest`): a parts entry is produced by `an.assemble`, not
    by the renderer, so the renderer's own ``code`` key part does not cover it.

    >>> from an.assemble import ShotWindow
    >>> parts_entry_id("k" * 64, ShotWindow(frames=30, head=0, tail=4)).endswith(".h0.t4")
    True
    """
    return (
        f"{key}{PARTS_INFIX}{parts_code_digest()[:16]}.h{window.head}.t{window.tail}"
    )


_PARTS_CODE: list[str] = []

#: The modules whose source decides a parts entry's bytes: the cut and the
#: composition (`an.assemble`), the encoder and its pinned argv (`an.media.mp4`),
#: and the frame naming (`an.media.frames`).
PARTS_CODE_MODULES: tuple[str, ...] = ("an.assemble", "an.media.mp4", "an.media.frames")


def parts_code_digest() -> str:
    """sha256 over the source bytes of :data:`PARTS_CODE_MODULES`, once per process."""
    if not _PARTS_CODE:
        import importlib
        import inspect

        from an.build.keys import file_digest

        _PARTS_CODE.append(
            canonical_digest(
                [
                    file_digest(inspect.getsourcefile(importlib.import_module(m)))
                    for m in PARTS_CODE_MODULES
                ]
            )
        )
    return _PARTS_CODE[0]


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

    Two hooks are OPTIONAL (the render loop calls them when an engine has
    them): ``record_parts(plan, parts)`` once per rendered shot whose film
    window is not whole (an#260), and ``record_root(output_name, profile=...,
    output=...)`` once the film is delivered (what the garbage collector keeps).
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
        window: Any = None,
        force: bool = False,
    ) -> ShotPlan: ...

    def record(self, plan: ShotPlan, result: "RenderResult", *, render_s: float) -> None: ...

    def finish(self) -> BuildReport: ...


_ENVIRONMENTS: dict[str, str] = {}


def default_environment_digest(renderer_name: str) -> str:
    """The digest of ``renderer_name``'s registered environment probe, once per process.

    Memoised per renderer NAME (each backend has its own machine: Chromium and
    ffmpeg for cut-out, a Manim install for Manim), and once per process,
    because the cut-out probe launches a browser and encodes a frame. So a
    long-lived host does not see a ``playwright install`` or a ``brew upgrade``
    made after its first render: restart it, or pass ``force_render``. A
    renderer with no probe has the empty environment.
    """
    if renderer_name not in _ENVIRONMENTS:
        entry = shot_keyer_for(renderer_name)
        record = entry.environment() if entry and entry.environment else {}
        _ENVIRONMENTS[renderer_name] = canonical_digest(record)
    return _ENVIRONMENTS[renderer_name]


#: ``strategy(mall, *, project_root) -> digest``: a project-wide digest — the
#: shape of both ``ShotCache(dependencies=...)`` (what EVERY shot depends on:
#: by default the library lockfile, :func:`~an.build.keys.project_dependencies`;
#: the ``project`` part) and ``ShotCache(fallback=...)`` (the ``assets`` of a
#: shot whose reads are not recorded: by default every asset,
#: :func:`~an.build.keys.every_asset_digest`).
Dependencies = Any


class ShotCache:
    """The built-in engine: look a shot's key up in an ArtifactStore; record misses.

    ``store`` is the injected ``lacing.ArtifactStore``; ``None`` means the
    mall's ``shot_cache`` (resolved in :meth:`begin`), and a mall without one
    renders every shot. ``environment(renderer_name) -> digest`` is the
    environment seam — injectable so a test (or a remote-render backend) can
    state its machine rather than probe this one. Three dependency seams (see
    :data:`Dependencies`):

    - ``record_reads`` (on by default) keys a shot whose keyer is registered
      with ``records_reads=True`` on the asset entries its compile read
      (:mod:`an.build.reads`, an#316: the ``assets`` part), so an edit to an
      asset re-renders only the shots that read it;
    - ``fallback`` is the ``assets`` part of every OTHER shot — a keyer that
      cannot vouch for its reads, or every shot under ``record_reads=False``:
      by default every asset in the project (decision 3's first slice);
    - ``dependencies`` is what EVERY shot depends on (the ``project`` part): by
      default the library lockfile. ``None`` drops it, and ``fallback=None``
      keys an unrecorded shot on its own parts alone — use either knowingly.

    An engine built with other seams writes keys `an cache gc` (which
    recomputes the current scene's keys with the defaults) does not reach:
    collect such a cache with the same engine.
    ``cache_frames`` also stores each shot's whole PNG sequence when a caller
    plans with ``needs_frames=True``. The render loop no longer does (an#260):
    an assembled film takes a shot's mp4 and, at a transition, its *parts*
    (``window=``), which are cached by default at a few MB. Kept for callers of
    the engine that need every frame; ``an cache gc`` collects old frames.

    After a render, :attr:`report` holds what happened to each shot.
    """

    def __init__(
        self,
        store: Any = None,
        *,
        environment: Any = default_environment_digest,
        dependencies: Dependencies = project_dependencies,
        fallback: Dependencies = every_asset_digest,
        record_reads: bool = True,
        cache_frames: bool = False,
    ) -> None:
        if cache_frames:
            warnings.warn(
                "ShotCache(cache_frames=True) / `an render --cache-frames` is "
                "deprecated: an assembled film no longer needs whole frames "
                "(an#260), so the render loop never stores them. It will be "
                "removed in the next release.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.store = store
        self.environment = environment
        self.dependencies = dependencies
        self.fallback = fallback
        self.record_reads = record_reads
        self.cache_frames = cache_frames
        self.report = BuildReport()
        self._store = store
        self._mall: Mapping[str, Any] = {}
        self._digests: dict[str, str | None] = {}
        self._previous: dict[tuple[str, str], Any] | None = None
        self._outcomes: dict[int, ShotOutcome] = {}
        self._order: list[int] = []
        self._environments: dict[str, str] = {}
        self._used: dict[int, list[str]] = {}
        self._project_root: Path | None = None

    # -- the protocol ------------------------------------------------------

    def begin(
        self, mall: Mapping[str, Any], *, project_root: Path | None = None
    ) -> None:
        self._store = self.store if self.store is not None else mall.get(SHOT_CACHE_STORE)
        self._mall = mall if mall is not None else {}
        self._project_root = project_root
        # Digested on first need: a film of recorded-read shots never hashes
        # the whole project.
        self._digests = {}
        self._previous = None
        self._outcomes = {}
        self._order = []
        self._environments = {}
        self._used = {}
        self.report = BuildReport()

    def plan(
        self,
        shot: Any,
        renderer: Any,
        ctx: "RenderContext",
        *,
        needs_frames: bool = False,
        window: Any = None,
        force: bool = False,
    ) -> ShotPlan:
        """``window`` is what an assembled film needs from this shot
        (`an.assemble.ShotWindow`; ``None`` for a plain concat): a shot whose
        window is not whole is reused only when its parts entry is there too."""
        name = getattr(renderer, "name", "") or ""
        if needs_frames and not self.cache_frames:
            plan = ShotPlan(shot.id, name, key=None, reason=FRAMES_NOT_CACHED)
            self._note(plan, "uncached")
            return plan
        keyed = self._key(shot, renderer, ctx)
        if isinstance(keyed, str):
            plan = ShotPlan(shot.id, name, key=None, reason=keyed)
            self._note(plan, "uncached")
            return plan
        key, parts, inputs, key_s, reads = keyed

        plan = ShotPlan(
            shot.id,
            name,
            key=key,
            inputs=parts,
            reads=reads,
            key_s=key_s,
            compile_s=inputs.compile_s,
            needs_frames=needs_frames,
            window=window,
            parts_id=(
                parts_entry_id(key, window)
                if window is not None and not window.whole
                else None
            ),
        )
        # The report lists shots in timeline order, not in the order a thread
        # pool finishes them; the index also names this plan's own
        # materialisation directory, so two shots with ONE key never share one.
        index = len(self._order)
        self._order.append(id(plan))
        self._used[id(plan)] = [key] + ([plan.parts_id] if plan.parts_id else [])
        if force:
            plan.reason = "forced"
            return plan
        cached, why = self._lookup(plan, ctx, index=index)
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

    def entry_ids(
        self, shot: Any, renderer: Any, ctx: "RenderContext", *, window: Any = None
    ) -> list[str]:
        """The catalog ids a :meth:`plan` of this shot would read — computed by
        the same code, looking nothing up and rendering nothing. What
        `an.build.gc` keeps for the current scene. Call :meth:`begin` first."""
        keyed = self._key(shot, renderer, ctx)
        if isinstance(keyed, str):
            return []
        key = keyed[0]
        if window is not None and not window.whole:
            return [key, parts_entry_id(key, window)]
        return [key]

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

    def record_parts(self, plan: ShotPlan, parts: Any) -> None:
        """Store a freshly rendered shot's `an.assemble.ShotParts` under
        ``plan.parts_id``: its body mp4 and its window's PNGs, one stored zip.
        A failed write never fails the render (the next render renders it)."""
        if plan.parts_id is None or self._store is None:
            return
        try:
            self._save_parts(plan, parts)
        except Exception as e:  # noqa: BLE001 — a failed cache write never fails a render
            warnings.warn(
                f"shot {plan.shot_id!r} rendered, but its parts entry could not be "
                f"written ({type(e).__name__}: {e}); the next render renders it again",
                ShotCacheWarning,
                stacklevel=2,
            )

    def record_root(
        self,
        output_name: str,
        *,
        profile: Mapping[str, Any],
        output: Path,
    ) -> str | None:
        """Record what this render used, as a ROOT for `an.build.gc`; return its id.

        A root is keyed by the project (:func:`project_id`), the output name,
        the render ``profile`` (the knobs as passed — ``None`` meaning "the
        scene's own") and this machine (:func:`machine_id`), so the next render
        of the same output with the same knobs on the same machine replaces it
        — a browser upgrade included — while a render on another machine of a
        synced project, or of another project sharing the store, keeps its own. Its record is a ``lacing.Artifact`` of the delivered film,
        derived from the shot keys. Also measures the store, for the summary.
        """
        if self._store is None:
            return None
        used = [i for p in self._order for i in self._used.get(p, ())]
        profile = _jsonable_dict(profile)
        project = project_id(self._project_root)
        root_id = ROOT_PREFIX + canonical_digest(
            [project, output_name, profile, machine_id()]
        )
        try:
            self._save_root(root_id, output_name, profile, Path(output), used, project)
        except Exception as e:  # noqa: BLE001 — never fail a delivered film
            warnings.warn(
                f"the film was rendered, but its cache root could not be written "
                f"({type(e).__name__}: {e}); `an cache gc` keeps only what the "
                "current scene reaches until the next render records one",
                ShotCacheWarning,
                stacklevel=2,
            )
            root_id = None
        try:
            self.report.store_bytes, self.report.store_entries = store_usage(self._store)
        except Exception:  # noqa: BLE001 — a size is informational
            pass
        return root_id

    # -- internals ---------------------------------------------------------

    def _key(self, shot: Any, renderer: Any, ctx: "RenderContext"):
        """``(key, parts, inputs, key_s)``, or the reason the shot has no key.

        The ONE computation of a shot's key: :meth:`plan` and :meth:`entry_ids`
        (so the garbage collector) both call it, so they cannot disagree.
        """
        name = getattr(renderer, "name", "") or ""
        entry = shot_keyer_for(renderer)
        if entry is None:
            return (
                f"no shot keyer registered for renderer {name!r}"
                if shot_keyer_for(name) is None
                else f"renderer {name!r} is a {type(renderer).__qualname__}, not the "
                "class its shot keyer describes"
            )
        if self._store is None:
            return "no shot cache store in the mall"
        t0 = time.perf_counter()
        recording = None
        if self.record_reads and entry.records_reads:
            from dataclasses import replace

            from an.build.reads import RecordingMall

            # The keyer compiles against a view that notes every asset entry
            # it reads: those reads are the shot's dependency edges (an#316).
            recording = RecordingMall(ctx.mall)
            ctx = replace(ctx, mall=recording)
        inputs: ShotKeyInputs = entry.keyer(shot, ctx)
        parts = {"renderer": canonical_digest([name, entry.identity()]), **inputs.parts}
        for part_name, part in entry.parts.items():
            if part_name in parts:
                raise ValueError(
                    f"key part {part_name!r} registered for {name!r} collides with "
                    "a part its keyer already returns"
                )
            parts[part_name] = part(shot, ctx)
        parts["environment"] = self._environment_of(name)
        reads: dict[str, str] = {}
        if recording is not None:
            from an.build.reads import read_digests

            reads = read_digests(recording._mall, recording.reads)
            parts["assets"] = canonical_digest(reads)
        else:
            fallback = self._project_digest("fallback")
            if fallback is not None:
                parts["assets"] = fallback
        project = self._project_digest("dependencies")
        if project is not None:
            parts["project"] = project
        return compose_shot_key(parts), parts, inputs, time.perf_counter() - t0, reads

    def _project_digest(self, seam: str) -> str | None:
        """A project-wide seam's digest (``dependencies`` or ``fallback``),
        computed once per render, on first need."""
        if seam not in self._digests:
            strategy = getattr(self, seam)
            self._digests[seam] = (
                strategy(self._mall, project_root=self._project_root)
                if strategy is not None
                else None
            )
        return self._digests[seam]

    def _explain_miss(self, plan: ShotPlan) -> str:
        """Why ``plan`` has no entry, read off the newest earlier entry of the
        same shot: which asset or which key part moved (an#316). The shot id
        is only a way to FIND that entry — never part of a key."""
        try:
            previous = self._previous_entries().get((plan.renderer, plan.shot_id))
        except Exception:  # noqa: BLE001 — an explanation never fails a render
            previous = None
        if previous is None:
            return MISS
        if getattr(previous, "key_version", 0) != SHOT_KEY_IMPL_VERSION:
            return KEY_FORMAT_CHANGED
        return explain_change(
            dict(previous.inputs), dict(getattr(previous, "reads", {}) or {}),
            plan.inputs, plan.reads,
        )  # fmt: skip

    def _previous_entries(self) -> dict[tuple[str, str], Any]:
        """``{(renderer, shot id): newest mp4 entry}``, read once per render,
        on the first miss (a scan of the catalog, never of the blobs)."""
        if self._previous is None:
            newest: dict[tuple[str, str], tuple[Any, Any]] = {}
            for key in list(self._store):
                # Only a shot's mp4 entry is named by its bare key: parts,
                # frames and roots are skipped unread (a cache holds many).
                if not _HEX64.match(str(key)):
                    continue
                try:
                    rec = self._store[key]
                except Exception:  # noqa: BLE001 — unreadable: not a candidate
                    continue
                if getattr(rec, "role", "mp4") != "mp4" or not rec.shot_id:
                    continue
                when = _generated_at(rec)
                slot = (rec.renderer, rec.shot_id)
                if slot not in newest or when > newest[slot][0]:
                    newest[slot] = (when, rec)
            self._previous = {slot: rec for slot, (_, rec) in newest.items()}
        return self._previous

    def _environment_of(self, name: str) -> str:
        digest = self.environment(name)
        self._environments[name] = digest
        return digest

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

    def _verified_blob(self, asset_id: str) -> bytes | None:
        """The blob's bytes, or ``None`` when absent or not what its id says.

        ``asset_id`` IS the sha256 of the bytes, so checking costs one hash —
        milliseconds against a render — and a damaged or substituted blob is a
        miss rather than a film (an#243 review, N1).
        """
        try:
            if not self._store.has_blob(asset_id):
                return None
            data = self._store.get_blob(asset_id)
        except (OSError, KeyError):  # collected between the two calls (an cache gc)
            return None
        if data is None or bytes_digest(data) != asset_id:
            return None
        return data

    def _lookup(
        self, plan: ShotPlan, ctx: "RenderContext", *, index: int
    ) -> tuple[Any, str]:
        store = self._store
        try:
            record = store.get(plan.key)
        except Exception as e:  # noqa: BLE001 — an unreadable entry is a miss, said
            return None, f"unreadable entry ({type(e).__name__})"
        if record is None:
            return None, self._explain_miss(plan)
        mp4_bytes = self._verified_blob(record.asset_id)
        if mp4_bytes is None:
            return None, "entry whose mp4 blob is missing or does not match its id"
        frames_bytes = None
        if plan.needs_frames:
            frames_rec = store.get(plan.key + FRAMES_SUFFIX)
            frames_bytes = (
                self._verified_blob(frames_rec.asset_id) if frames_rec is not None else None
            )
            if frames_bytes is None:
                return None, "frames needed for assembly, not cached"
        parts_bytes = None
        if plan.parts_id is not None:
            try:
                parts_rec = store.get(plan.parts_id)
            except Exception as e:  # noqa: BLE001 — unreadable is a miss, said
                return None, f"unreadable parts entry ({type(e).__name__})"
            parts_bytes = (
                self._verified_blob(parts_rec.asset_id) if parts_rec is not None else None
            )
            if parts_bytes is None:
                return None, PARTS_NOT_CACHED
        from an.adapters._base import RenderResult

        # One directory per PLAN (index + id), inside this render's own work
        # dir: two shots with one key, or two concurrent renders, never share
        # (and never delete) each other's files (an#243 review, B1).
        out_dir = Path(ctx.work_dir) / "shot_cache" / f"{index:03d}_{plan.shot_id}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
        mp4 = out_dir / f"{plan.shot_id}.mp4"
        mp4.write_bytes(mp4_bytes)
        manifest: list[Path] = []
        if frames_bytes is not None:
            frames_dir = out_dir / "frames"
            frames_dir.mkdir()
            with tempfile.TemporaryFile() as tmp:
                tmp.write(frames_bytes)
                tmp.seek(0)
                with zipfile.ZipFile(tmp) as zf:
                    zf.extractall(frames_dir)
            manifest = sorted(frames_dir.glob("*.png"))
        if parts_bytes is not None:
            plan.parts = _unpack_parts(parts_bytes, plan.window, out_dir / "parts")
            if plan.parts is None:
                return None, "parts entry that does not hold its window's frames"
        plan.cached_render_s = record.timings.get("render_s")
        provenance = dict(record.render_provenance)
        # The shot this result is FOR, not the one first rendered under the key
        # (a renamed or duplicated shot reuses another id's entry).
        provenance["shot_id"] = plan.shot_id
        provenance["shot_cache"] = {
            "status": "reused",
            "key": plan.key,
            "rendered_as": record.shot_id,
        }
        return (
            RenderResult(
                mp4_path=mp4,
                duration=record.duration_s if record.duration_s is not None else 0.0,
                frame_manifest=manifest,
                provenance=provenance,
            ),
            "",
        )

    def _provenance(self, generated_by: str, derived_from: Any) -> Any:
        from lacing import Provenance, RationalTime

        return Provenance(
            was_generated_by=generated_by,
            was_attributed_to=PROVENANCE_AGENT,
            was_derived_from=sorted({d for d in derived_from if _HEX64.match(d)}),
            generated_at_time=RationalTime.now(),
            activity="derive",
        )

    def _save_parts(self, plan: ShotPlan, parts: Any) -> None:
        store = self._store
        fd, name = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        zpath = Path(name)
        try:
            _pack_parts(parts, zpath)
            asset_id = store.put_blob_stream(_chunks(zpath))
            store[plan.parts_id] = shot_artifact_type()(
                asset_id=asset_id,
                kind="binary",
                mime="application/zip",
                bytes_size=zpath.stat().st_size,
                provenance=self._provenance(
                    "processor:an.assemble/shot_parts", [plan.key]
                ),
                role="parts",
                shot_key=plan.key,
                shot_id=plan.shot_id,
                renderer=plan.renderer,
                inputs={"shot": plan.key, "parts_code": parts_code_digest()},
                render_provenance={
                    "window": {
                        "frames": parts.window.frames,
                        "head": parts.window.head,
                        "tail": parts.window.tail,
                    }
                },
            )
        finally:
            zpath.unlink(missing_ok=True)

    def _save_root(
        self,
        root_id: str,
        output_name: str,
        profile: dict,
        output: Path,
        used: list[str],
        project: str,
    ) -> None:
        from an.build.keys import file_digest

        self._store[root_id] = shot_artifact_type()(
            asset_id=file_digest(output),
            kind="video",
            mime="video/mp4",
            bytes_size=output.stat().st_size,
            provenance=self._provenance("processor:an.render", used),
            role="root",
            shot_key=root_id,
            shot_id=output_name,
            inputs={"profile": canonical_digest(profile)},
            render_provenance={
                "output": output_name,
                "profile": profile,
                "environment": dict(sorted(self._environments.items())),
                "machine": machine_id(),
                "project": project,
                "entries": used,
            },
        )

    def _save(self, plan: ShotPlan, result: "RenderResult", timings: dict[str, float]) -> None:
        store = self._store
        record_type = shot_artifact_type()

        def provenance() -> Any:
            return self._provenance(
                f"processor:an.render/{plan.renderer}", plan.inputs.values()
            )

        common = dict(
            shot_key=plan.key,
            shot_id=plan.shot_id,
            renderer=plan.renderer,
            inputs=dict(plan.inputs),
            reads=dict(plan.reads),
            key_version=SHOT_KEY_IMPL_VERSION,
            timings=timings,
        )
        # Frames first, the mp4 record last: the mp4 record is what a lookup
        # asks for, so it must never point at an entry whose parts are missing.
        if plan.needs_frames and self.cache_frames and result.frame_manifest:
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


def _generated_at(record: Any) -> Any:
    """When ``record`` was generated, as an orderable fraction (0 when unknown)."""
    from fractions import Fraction

    t = getattr(getattr(record, "provenance", None), "generated_at_time", None)
    try:
        return t.to_fraction() if t is not None else Fraction(0)
    except Exception:  # noqa: BLE001 — an unreadable time sorts first
        return Fraction(0)


#: How the summary names a key part that moved (:func:`explain_change`).
PART_LABELS: dict[str, str] = {
    "compiled": "its document",
    "textures": "its art",
    "easings": "an easing version",
    "audio": "its dialogue audio",
    "runtime": "the JS runtime",
    "runtime_extensions": "a genre's runtime code",
    "code": "an's render code",
    "knobs": "render settings",
    "environment": "the render environment",
    "renderer": "the renderer",
    "fonts": "the system fonts",
    "vocabulary": "a vocabulary entry",
    "project": "the library lockfile",
}

#: Parts that move BECAUSE an asset the shot read moved: when an asset is
#: named, naming these too would only blur the cause.
FOLLOWS_ASSETS: frozenset[str] = frozenset(
    {"compiled", "textures", "fonts", "easings", "assets"}
)

#: The reason when the newest earlier entry of a shot was keyed by another
#: composition of the key (an `an` upgrade: `SHOT_KEY_IMPL_VERSION`, recorded
#: on the entry as ``key_version``).
KEY_FORMAT_CHANGED: str = "the shot key's format changed (an upgrade)"


def explain_change(
    before: Mapping[str, str],
    before_reads: Mapping[str, str],
    after: Mapping[str, str],
    after_reads: Mapping[str, str],
) -> str:
    """Why a shot keyed ``after`` is not the entry keyed ``before``, in words.

    The assets it read that moved come first, by name (``asset changed:
    props/logo``), then every other key part that moved, appeared or went, by
    :data:`PART_LABELS` (an optional part — ``fonts``, ``runtime_extensions`` —
    comes and goes with what the shot draws). The parts that follow from an
    asset (:data:`FOLLOWS_ASSETS`) are left out when one is named. Both keys
    are of one composition: a different ``key_version`` is
    :data:`KEY_FORMAT_CHANGED`, decided before this is called.

    >>> explain_change({"compiled": "a", "assets": "x"}, {"props/logo": "1"},
    ...                {"compiled": "b", "assets": "y"}, {"props/logo": "2"})
    'asset changed: props/logo'
    >>> explain_change({"knobs": "a", "compiled": "c"}, {}, {"knobs": "b", "compiled": "c"}, {})
    'render settings changed'
    >>> explain_change({"compiled": "a"}, {}, {"compiled": "a", "fonts": "f"}, {})
    'the system fonts changed'
    >>> explain_change({"assets": "a"}, {}, {"assets": "b"}, {})  # an unrecorded shot
    'a project asset changed'
    """
    names = list(dict.fromkeys([*after, *before]))
    moved = [name for name in names if before.get(name) != after.get(name)]
    assets = sorted(
        k for k in set(before_reads) | set(after_reads)
        if before_reads.get(k) != after_reads.get(k)
    )  # fmt: skip
    said: list[str] = []
    if assets:
        said.append("asset changed: " + ", ".join(assets))
    others = [
        name for name in moved if not (assets and name in FOLLOWS_ASSETS)
    ]
    labels = [
        PART_LABELS.get(name, name)
        if name != "assets"
        else "a project asset"  # a whole-project digest: nothing to name
        for name in others
    ]
    if labels:
        said.append(" and ".join(labels) + " changed")
    return " and ".join(said) or MISS


class ShotCacheWarning(UserWarning):
    """The shot cache could not do something it should have; the render still stands."""


#: Inside a parts zip: the body's member name, and the folder of window PNGs
#: (named by the shot-LOCAL frame index, `an.media.frames`' pattern).
PARTS_BODY_MEMBER: str = "body.mp4"
PARTS_FRAMES_DIR: str = "frames"


def _pack_parts(parts: Any, zpath: Path) -> None:
    from an.media.frames import DEFAULT_FRAME_PNG_PATTERN

    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_STORED) as zf:
        if parts.body is not None:
            zf.write(parts.body, arcname=PARTS_BODY_MEMBER)
        for j, path in sorted(parts.frames.items()):
            zf.write(path, arcname=f"{PARTS_FRAMES_DIR}/{DEFAULT_FRAME_PNG_PATTERN % j}")


def _unpack_parts(data: bytes, window: Any, out_dir: Path) -> Any:
    """The `an.assemble.ShotParts` a parts zip holds, or ``None`` when it does
    not hold exactly what ``window`` needs (a body iff the window leaves one,
    and a PNG for every window frame)."""
    from an.assemble import ShotParts
    from an.media.frames import DEFAULT_FRAME_PNG_PATTERN

    expected = {
        f"{PARTS_FRAMES_DIR}/{DEFAULT_FRAME_PNG_PATTERN % j}": j
        for j in window.png_indices
    }
    first, stop = window.body
    with tempfile.TemporaryFile() as tmp:
        tmp.write(data)
        tmp.seek(0)
        with zipfile.ZipFile(tmp) as zf:
            names = set(zf.namelist())
            wants_body = stop > first
            if names != set(expected) | ({PARTS_BODY_MEMBER} if wants_body else set()):
                return None
            out_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(out_dir)
    return ShotParts(
        window=window,
        frames={j: out_dir / name for name, j in expected.items()},
        body=(out_dir / PARTS_BODY_MEMBER) if wants_body else None,
    )


def store_usage(store: Any) -> tuple[int, int]:
    """``(bytes, entries)`` of a shot cache store: every blob byte on disk (or,
    off disk, every distinct blob its records name) and its catalog entries.

    On a filesystem store this is a directory listing, not a read of every
    record, so the render summary can afford it on every render.
    """
    rootdir = getattr(getattr(store, "blobs", None), "rootdir", None)
    if rootdir is not None:
        total = 0
        with os.scandir(rootdir) as it:
            for e in it:
                if e.is_file(follow_symlinks=False):
                    total += e.stat(follow_symlinks=False).st_size
        return total, len(store)
    sizes: dict[str, int] = {}
    n = 0
    for key in list(store):
        n += 1
        try:
            rec = store[key]
        except Exception:  # noqa: BLE001 — an unreadable record has no size we know
            continue
        if getattr(rec, "role", "") != "root" and store.has_blob(rec.asset_id):
            sizes[rec.asset_id] = rec.bytes_size or 0
    return sum(sizes.values()), n


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
    "PARTS_INFIX",
    "ROOT_PREFIX",
    "SHOT_CACHE_STORE",
    "BuildReport",
    "IncrementalEngine",
    "ShotCache",
    "ShotCacheWarning",
    "ShotOutcome",
    "ShotPlan",
    "default_environment_digest",
    "explain_change",
    "human_bytes",
    "in_memory_shot_cache_store",
    "machine_id",
    "project_id",
    "parts_entry_id",
    "resolve_incremental",
    "shot_artifact_type",
    "shot_cache_store",
    "store_usage",
]
