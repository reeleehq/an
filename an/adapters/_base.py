"""Renderer protocol, render context, render result, and the renderer registry.

Every backend implements ``Renderer`` and registers itself by name. The
orchestrator (or `RenderRouter` in non-agent contexts) picks a renderer per
shot by inspecting ``shot.renderer`` and asking each registered renderer's
``can_render``.

>>> from an.adapters import Renderer
>>> hasattr(Renderer, '__call__') or True  # Protocol attribute access works
True
"""

from __future__ import annotations

import threading
import warnings
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Protocol, runtime_checkable

from an.base import DEFAULT_FPS, DEFAULT_RESOLUTION, DEFAULT_SUPERSAMPLE
from an.ir.schema import Shot


if TYPE_CHECKING:  # pragma: no cover - types only
    from an.styles import StylePack


@dataclass(slots=True)
class RenderContext:
    """Everything a renderer needs that isn't on the Shot itself.

    ``mall`` carries the project's stores so the renderer can resolve assets
    by reference. ``work_dir`` is a scratch space; the renderer must clean up
    after itself or treat it as ephemeral.
    """

    mall: Mapping[str, MutableMapping]
    work_dir: Path
    #: Frames per second of the delivered video. May be non-integer — a
    #: camera's 29.97 — and the capture loop and the mux honour it exactly. The
    #: COMPILER aligns its frame-sampled curves (gaze saccades, co-articulation,
    #: descriptor plays, face curves) to the nearest integer grid instead,
    #: because the compiled document's ``meta.fps`` is an integer; tweens and
    #: every other keyframe are exact at any rate.
    fps: int | float = DEFAULT_FPS
    resolution: tuple[int, int] = DEFAULT_RESOLUTION
    #: Refuse to draw a stand-in for a declared asset that the stores do not
    #: supply. Off by default so an asset-less project still renders; on for
    #: anything that measures pixels, where a stand-in is a different picture
    #: that looks like a successful render (an#33).
    strict_assets: bool = False
    #: Render at this many times the declared resolution and resolve back with
    #: an exact block mean. **1 means off, and off is free** — Chromium's own
    #: PNG bytes reach disk untouched.
    #:
    #: A `RenderContext` field, and that placement is load-bearing rather than
    #: convenient. Simulated against a real committed ledger row: as a
    #: `render_kwargs` entry it becomes a `COMMON_ENV_PATHS` key and **all 96
    #: metrics are refused**; as a field on the compiled scene document it moves
    #: `scene_contract_sha256` and **every scene becomes incomparable**; here,
    #: only `runtime_sha256` moves, which is deliberately not a comparability
    #: key — so 30 render-side entries still compare. It needs no
    #: `SCHEMA_VERSION` migration, and it MUST reach per-shot provenance, because
    #: a row that does not record it cannot be read back later.
    supersample: int = DEFAULT_SUPERSAMPLE
    #: The delivered encode's pixel format, or ``None`` for the module default.
    #: **The one first-order quality lever in the encoder**: 4:2:0 -> 4:4:4 cuts
    #: the edge-band error 11.35 -> 3.79, where mathematically lossless 4:2:0
    #: only reaches 10.15. Losslessness buys 8%; dropping chroma subsampling
    #: buys 66%.
    #:
    #: ``None`` rather than the literal, so the bench's `pix_fmt` lever — which
    #: rebinds the module default — still reaches an unset render. The default
    #: stays 4:2:0 for a PRODUCT reason and not an encoder one: High 4:4:4
    #: Predictive is refused by many hardware decoders, browsers and platforms.
    pix_fmt: str | None = None
    #: Scene-level stepped-timing policy for authored tweens (an#89); a shot's
    #: own ``step_hz`` overrides it. ``None`` = smooth. Reaches the compiled
    #: document's ``meta.step_hz`` (only when set) and per-shot provenance.
    #:
    #: The one deliberate exception to the rule two fields up ("a field on the
    #: compiled scene document moves `scene_contract_sha256`"): unlike
    #: `supersample`, this knob CHANGES the compiled document — the resampled
    #: keyframes are the contract — so the hash moves whenever it is set no
    #: matter where the knob lives, and a document that carries its own timing
    #: policy is the honest one. Omit-when-unset keeps the unset case free.
    step_hz: float | None = None

    #: The `StylePack` this render is drawn under, already resolved from the
    #: scene's `meta.style_pack` (an#112). Resolved ONCE per render rather than
    #: per shot: a pack is art direction for a project, and a scene whose shots
    #: disagreed about it would be two scenes.
    style_pack: "StylePack | None" = None
    #: The scene's ``meta.default_easing`` (an#166): the curve of every
    #: authored tween that names none. ``None`` = the built-in
    #: ``"ease_in_out"``, and a compiled document byte-identical to before the
    #: field existed; set, it changes keyframes, so the contract hash moves
    #: with it — as it should.
    default_easing: Any = None
    #: Per output frame, the scene instants to render and average into it —
    #: ``None`` is one instant at ``i / fps``, the path every render took before
    #: this field existed, byte for byte. Several instants per frame are an open
    #: shutter (motion blur); instants off the ``i / fps`` grid are capture
    #: jitter. Built by :class:`an.frame_clock.FrameClock`, which is also what
    #: the impact harness writes into its ground truth, so the render and the
    #: record of when each frame was taken come from one object.
    #:
    #: A `RenderContext` field for `supersample`'s reason: it changes how frames
    #: are CAPTURED, not what the scene is, so it must not move the compiled
    #: document. Its length must equal the render's frame count.
    frame_samples: tuple[tuple[float, ...], ...] | None = None
    #: How frames leave the browser: ``"screenshot"`` (a Playwright element
    #: screenshot per instant) or ``"canvas"`` (the runtime reads its own canvas
    #: in-page, in batches). ``None`` is the renderer's module default, read at
    #: call time — ``"canvas"`` since an#192, after the equivalence gate held on
    #: the whole corpus on both lanes. The two paths write frames whose DECODED
    #: pixels are equal, so this is a throughput knob and never a picture knob;
    #: a `RenderContext` field for `supersample`'s reason, and recorded in
    #: per-shot provenance.
    capture: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RenderResult:
    """Outcome of a single shot render."""

    mp4_path: Path
    duration: float  # actual rendered duration in seconds
    frame_manifest: list[Path] = field(default_factory=list)
    log: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Renderer(Protocol):
    """Backend renderer interface.

    Implementations should be cheap to construct and stateless across renders;
    state belongs in the ``RenderContext`` or the project mall.
    """

    name: str
    #: The `Shot.renderer` values this backend claims. It is the ONE place
    #: an adapter names them: `can_render` derives from it rather than
    #: comparing to its own literal, so an adapter cannot advertise one
    #: renderer and accept another. an#106 renamed this from
    #: `supported_styles`; the rename is a break for an out-of-tree adapter
    #: because `Renderer` is `@runtime_checkable` and 3.12 checks data
    #: members, so `isinstance(old_adapter, Renderer)` is now False.
    supported_renderers: tuple[str, ...]

    def can_render(self, shot: Shot) -> bool:
        """Return True if this renderer can render ``shot``."""

    def render(self, shot: Shot, ctx: RenderContext) -> RenderResult:
        """Render a single shot to mp4. Idempotent given identical inputs."""


@dataclass(slots=True)
class DurationMeasurement:
    """How long a clock-owning renderer's shot runs, as MEASURED (derived data).

    ``duration`` is the content's own length in seconds. ``findings`` are
    :class:`~an.verify.Finding` s about the shot whose ``ir_path`` is RELATIVE to
    the shot (``"options/source"``) — the core prefixes ``timeline/<i>/``.
    ``key`` is the content key the measurement is stored under.
    """

    duration: float
    findings: list[Any] = field(default_factory=list)
    key: str | None = None


@runtime_checkable
class ClockOwningRenderer(Renderer, Protocol):
    """A whole-shot renderer that decides how long its shot runs (core study §4.2).

    Manim is one: only the scene file's own ``play`` and ``wait`` calls fix its
    length, so ``shot.duration`` cannot be authored. The capability is the
    MEMBER — ``engine.measure_duration`` is derived from it, never declared
    (ADR 0002). The measurement is DERIVED data: it is kept in a derived store
    keyed by the shot's content, never written into the author's documents, and
    the core applies it in memory (:func:`an.measurements.settle_durations`)
    before laying out the film — so the layout is a pure function of the IR and
    the measurements. ``an sync --accept-measured`` takes it into the scene on
    request.
    """

    def measure_duration(
        self,
        shot: Shot,
        ctx: RenderContext,
        *,
        render: bool = True,
        force: bool = False,
    ) -> DurationMeasurement | None:
        """The shot's measured length. With ``render=False``, only a stored
        measurement (``None`` when there is none yet); with ``force=True``,
        measured afresh even when one is stored."""


# -----------------------------------------------------------------------------
# Registry
# -----------------------------------------------------------------------------


#: The entry-point group a package declares a renderer module under, e.g.
#: ``[project.entry-points."an.renderers"] burns = "burns.an_engine"``. The
#: module registers its renderer(s) when imported (``register_renderer``).
RENDERER_ENTRY_POINT_GROUP: str = "an.renderers"


class RendererRegistry:
    """Name-keyed registry of renderers.

    A module-level instance is exposed via ``register_renderer`` /
    ``get_renderer`` / ``list_renderers``; callers needing isolation (tests,
    multi-tenant servers) can construct their own.

    **Backends outside the core register LAZILY** (an#247): a renderer that
    lives behind the import firewall -- the stage, a genre's, a third-party
    engine -- is named here by the MODULE that registers it
    (:meth:`register_lazy`, or the ``an.renderers`` entry point group), and
    that module is imported the first time the registry is asked anything. So
    importing the core loads no backend, and every lookup still finds it.
    """

    def __init__(self, *, entry_point_group: str | None = None) -> None:
        self._by_name: dict[str, Renderer] = {}
        self._lazy: dict[str, str] = {}
        self._entry_point_group = entry_point_group
        #: Set only once every lazy module has imported. A module that failed
        #: is retried by the next lookup -- never silently forgotten.
        self._loaded = False
        self._imported: set[str] = set()
        self._failures: dict[str, BaseException] = {}
        # Re-entrant: importing a backend registers it, and its registration
        # may itself look the registry up (its shot keyer does) on this thread.
        self._lock = threading.RLock()
        self._loading = False

    def register(self, renderer: Renderer) -> None:
        if not getattr(renderer, "name", None):
            raise ValueError("renderer must have a non-empty 'name' attribute")
        self._by_name[renderer.name] = renderer

    def register_lazy(self, name: str, module: str) -> None:
        """Declare that importing ``module`` registers the renderer ``name``."""
        with self._lock:
            self._lazy[name] = module
            self._loaded = False

    def _pending_modules(self) -> list[str]:
        modules = [m for n, m in self._lazy.items() if n not in self._by_name]
        if self._entry_point_group:
            from importlib.metadata import entry_points

            # A value's `:attr` is not used: importing the module registers.
            modules += [
                ep.value.partition(":")[0]
                for ep in entry_points(group=self._entry_point_group)
            ]
        return [m for m in dict.fromkeys(modules) if m not in self._imported]

    def _load(self) -> dict[str, BaseException]:
        """Import every lazily named backend once; return the ones that failed.

        Thread-safe: concurrent first lookups wait for the one import rather
        than seeing a half-filled registry (review of an#270, S1). A module
        that raises is reported to the lookup that could not be answered
        without it, and retried by the next lookup.
        """
        if self._loaded:
            return {}
        with self._lock:
            if self._loaded or self._loading:  # done, or this thread is mid-import
                return dict(self._failures)
            self._loading = True
            try:
                from importlib import import_module

                failures: dict[str, BaseException] = {}
                for module in self._pending_modules():
                    try:
                        import_module(module)
                    except Exception as e:  # noqa: BLE001 -- reported, never swallowed
                        failures[module] = e
                    else:
                        self._imported.add(module)
                self._failures = failures
                self._loaded = not failures
            finally:
                self._loading = False
            return dict(failures)

    def _claimer(self, name: str) -> Renderer | None:
        return next(
            (r for r in self._by_name.values() if name in getattr(r, "supported_renderers", ())),
            None,
        )

    def get(self, name: str) -> Renderer:
        """The renderer registered as ``name``, else the one that claims it
        (``get("stage")`` is the stage renderer, registered as ``cutout``)."""
        failures = self._load()
        if name in self._by_name:
            return self._by_name[name]
        claimer = self._claimer(name)
        if claimer is not None:
            return claimer
        if failures:
            raise RendererLoadError(failures, wanted=f"renderer {name!r}")
        raise KeyError(f"no renderer registered with name {name!r}")

    def find_for(self, shot: Shot) -> Renderer | None:
        """Return the first registered renderer that ``can_render(shot)``.

        ``None`` when none can; a :class:`RendererLoadError` when none can AND
        a backend failed to import, since that backend may have been the one.
        """
        failures = self._load()
        for r in self._by_name.values():
            if r.can_render(shot):
                return r
        if failures:
            raise RendererLoadError(failures, wanted=f"shot {shot.id!r} (renderer={shot.renderer!r})")
        return None

    def names(self) -> Iterable[str]:
        failures = self._load()
        if failures:
            warnings.warn(str(RendererLoadError(failures, wanted="the renderer list")), RendererLoadWarning, stacklevel=2)
        return list(self._by_name.keys())


class RendererLoadError(ImportError):
    """A lazily registered backend could not be imported (an#247).

    Names each module and its error; the lookup that raised it could not be
    answered without them. The next lookup tries them again.
    """

    def __init__(self, failures: Mapping[str, BaseException], *, wanted: str) -> None:
        self.failures = dict(failures)
        detail = "; ".join(f"{m}: {type(e).__name__}: {e}" for m, e in self.failures.items())
        super().__init__(
            f"no renderer for {wanted}, and these renderer backends failed to "
            f"import (each is retried on the next lookup): {detail}"
        )


class RendererLoadWarning(UserWarning):
    """Listing the renderers while a lazily registered backend fails to import."""


_DEFAULT_REGISTRY = RendererRegistry(entry_point_group=RENDERER_ENTRY_POINT_GROUP)


def register_renderer(renderer: Renderer) -> None:
    """Register a renderer in the default registry."""
    _DEFAULT_REGISTRY.register(renderer)


def register_lazy_renderer(name: str, module: str) -> None:
    """Name the module whose import registers renderer ``name`` (default registry)."""
    _DEFAULT_REGISTRY.register_lazy(name, module)


def get_renderer(name: str) -> Renderer:
    """Look up a renderer by name in the default registry."""
    return _DEFAULT_REGISTRY.get(name)


def list_renderers() -> list[str]:
    """Names of all renderers registered in the default registry."""
    return list(_DEFAULT_REGISTRY.names())
