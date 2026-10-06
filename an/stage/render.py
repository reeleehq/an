"""The 2D stage engine (``runtime.js`` in headless Chromium), and the cut-out renderer built on it.

Since an#247 this module is an ENGINE, not a whole renderer: the frame stage is
the core's (:func:`an.engines.frame_stage_renderer` -- clock, capture loop,
supersample and shutter resolves, MP4 sink, provenance), and this module only
does what is specific to the stage:

1. :class:`StageEngine` compiles the shot to a ``CutoutSceneJSON``
   (``compile_shot``), stages a copy of the JS runtime plus the shot's textures
   in ``<work_dir>/shot_<id>/runtime/``, serves it over loopback HTTP (PixiJS
   cannot fetch ``file://`` in headless Chromium), launches Chromium with the
   pinned rasteriser flags, injects the supersample factor, loads the scene with
   a deadline, and judges the determinism probe.
2. It yields a session the core drives: :class:`_CanvasStageSession` (the
   default, ``capture="canvas"``: batches of in-page canvas reads,
   ``window.anCaptureFrames``) or :class:`_ScreenshotStageSession`
   (``capture="screenshot"``: an element screenshot per instant). Both are
   batched (``frames(requests)``), so a runtime throw is located by frame.
3. :class:`CutoutRenderer` is ``frame_stage_renderer(StageEngine())`` under the
   persisted renderer name ``cutout``, raising ``CutoutRenderError``.

The engine-independent halves moved to the core in an#247 and are still
reachable here by their old names: the mux, the pixel format and the x264 argv
(:mod:`an.media.mp4`), the frame naming (:mod:`an.media.frames`), the resolves
(:mod:`an.media.supersample`, :mod:`an.media.shutter`) and the capture tunables
(:mod:`an.engines.capture`). Those old names are LIVE aliases
(:mod:`an._shims`): rebinding ``DETERMINISTIC_X264_ARGS`` or ``DEFAULT_PIX_FMT``
here rebinds the global the core reads, so the bench's levers keep reaching the
encode. The module itself moved here from ``an/adapters/cutout/render.py`` in
an#247; that path is a live alias of this one (:func:`an._shims.alias_module`).

Failures are reported with concrete remediation: missing ffmpeg, missing
Chromium, runtime load timeout, etc. Subprocess errors are wrapped at the
facade boundary.

>>> CutoutRenderer().name, CutoutRenderer().supported_renderers
('cutout', ('cutout', 'stage'))
"""

from __future__ import annotations

import http.server
import json
import shutil
import socketserver
import threading
import warnings
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from an.adapters._base import RenderContext
from an.stage.canvas_capture import (
    CanvasCaptureError,
    canvas_frame_png,
    decode_data_url,
)
from an.stage.compile import compile_shot
from an.stage.runtime_files import runtime_dir
from an.stage.serialize import to_dict
from an.stage.text_layout import INLINE_SRC_PREFIX
from an.determinism import capture_violations, determinism_enforced
from an.engines import capture as _capture
from an.engines.capture import FrameStageError
from an.engines.frame_stage import FrameStageRenderer
from an.engines.protocol import Engine, FrameJob, FrameRequest, requests_as_dicts
from an.ir.schema import Shot, resolve_step_hz
from an.media import mp4 as _mp4
from an.media.supersample import NO_SUPERSAMPLE
from an.stage import STAGE_RENDERER_NAMES
from an.stage.raster import strip_version

#: The engine's name: what it is, independent of the renderer names it is
#: registered under (``cutout``, a persisted identifier, and ``stage``).
STAGE_ENGINE_NAME: str = "stage"


# Tunables — exposed as module constants per the no-magic-numbers rule.
DEFAULT_RUNTIME_LOAD_TIMEOUT_MS: int = 15_000

#: Deadline for `anLoadScene`, which awaits `PIXI.Assets.load` for every declared
#: texture. **A bound is required, not merely nice**: a degenerate part SVG —
#: `<svg/>`, malformed XML, a zero-dimension root — makes `Assets.load` never
#: settle, so without this the render hangs indefinitely with no error and no
#: output (an#79). `page.evaluate` is not subject to Playwright's default
#: timeout, so the deadline is imposed inside the page instead.
#:
#: The value is a policy choice, not a measurement: it needs to sit far above a
#: legitimate cold load of a few dozen small SVGs and far below "a human gave
#: up". Raise it for a genuinely heavy art package rather than removing it.
DEFAULT_ASSET_LOAD_TIMEOUT_MS: int = 60_000

#: Chromium launch flags that pin the rasteriser (an#31, research §2).
#:
#: **Unconditional, deliberately** — not gated behind an env var. A render whose
#: rasteriser depends on ``AN_DETERMINISTIC`` is non-reproducible *by default*,
#: which is the property this work exists to remove; and the flags are a
#: measured no-op on today's output (0 differing pixels over both fixtures,
#: verified on this repo at the commit that introduced them), so there is no
#: baseline to protect by making them opt-in.
#:
#: Unpinned, the same code renders differently in ways nobody would attribute
#: correctly: GPU vs software rasterisation is a 1.9% / max-57 pixel difference,
#: and a headed browser (reachable by a one-word local edit) differs by 1.91%.
#: A band that wide hides any real regression.
#:
#: Two flags are deliberately NOT here. ``--use-angle=swiftshader`` — including
#: Chromium's own documented ``--use-gl=angle --use-angle=swiftshader`` form —
#: moves 1.55% of pixels by up to 58/255, so it would re-baseline the corpus for
#: nothing. ``--disable-frame-rate-limit`` measured 1.05x on this WebGL runtime
#: (the widely-cited 2.3x is a canvas-2D artefact). ``--deterministic-mode`` is a
#: verified no-op here, because the runtime uses ``autoStart:false`` plus an
#: explicit ``app.render()``.
#:
#: Record the argv **verbatim** in any provenance row: all four rasteriser
#: configurations report the byte-identical ``UNMASKED_RENDERER_WEBGL`` string,
#: so the renderer string cannot witness this choice.
DETERMINISTIC_CHROMIUM_ARGS: tuple[str, ...] = (
    "--no-sandbox",  # was already passed; also a Playwright default
    "--disable-gpu",  # pins SOFTWARE rasterisation
    "--enable-unsafe-swiftshader",  # Chrome 137 removed the automatic fallback
    "--force-color-profile=srgb",  # pins the screenshot path's colour management
)

#: How frames leave the browser. ``"canvas"`` (the default since an#192): the
#: runtime's ``anCaptureFrames`` reads the canvas in-page and hands back PNG data
#: URLs in batches (`an.stage.canvas_capture`), which writes frames
#: whose DECODED pixels equal the screenshot path's — ~7.8x faster in the frame
#: stage on the golden corpus, ~2.3x at 1080p. ``"screenshot"``: a Playwright
#: element screenshot of ``#stage`` per instant, the path every render took
#: before; still available (``an render --capture screenshot``).
#:
#: Flipped only after the equivalence gate (`tests/test_canvas_capture_equivalence.py`)
#: held on the whole golden corpus on a developer machine AND the labelled Linux
#: rendering lane (an#189, re-run on an#192): a faster path that moved a pixel
#: would silently invalidate every baseline recorded before it. Read as a MODULE
#: GLOBAL at call time, for `DEFAULT_PIX_FMT`'s reason — a default argument
#: would bind it at def time.
DEFAULT_CAPTURE: str = "canvas"

#: The capture paths `_check_capture` accepts. Not an open string: a typo must
#: fail before a browser launches, not minutes into a render.
SUPPORTED_CAPTURES: tuple[str, ...] = ("screenshot", "canvas")

#: The page-side capture call; see ``anCaptureFrames`` in ``runtime.js``.
_CAPTURE_FRAMES_JS: str = "(requests) => window.anCaptureFrames(requests)"

#: Races `anLoadScene` against an in-page deadline. `page.evaluate` awaits a
#: returned promise with no timeout of its own, so the bound has to live here.
#: The rejection message is matched by :func:`_evaluate` to name the cause.
_LOAD_SCENE_JS: str = """
async (args) => {
    let timer = null;
    const deadline = new Promise((_, reject) => {
        timer = setTimeout(
            () => reject(new Error(%(marker)r)), args.timeoutMs
        );
    });
    try {
        await Promise.race([window.anLoadScene(args.scene), deadline]);
    } finally {
        if (timer !== null) { clearTimeout(timer); }
    }
}
"""

#: Sentinel the in-page deadline rejects with, so the Python side can tell a
#: timeout apart from a load failure and say something different about each.
ASSET_LOAD_TIMEOUT_MARKER: str = "an:asset-load-timeout"

_LOAD_SCENE_JS = _LOAD_SCENE_JS % {"marker": ASSET_LOAD_TIMEOUT_MARKER}


def _evaluate(
    page: Any, expression: str, *args: Any, doing: str, hint: str = ""
) -> Any:
    """`page.evaluate`, with failures wrapped as :class:`CutoutRenderError`.

    A JS failure escapes Playwright as a raw ``playwright._impl._errors.Error``
    carrying a minified stack trace and nothing about what the renderer was
    doing. That violates the repo's typed-error convention and, in practice,
    surfaces the most likely art failure in the product as
    ``TypeError: Cannot read properties of undefined (reading 'x')`` (an#79).

    ``doing`` names the step. The JS message is carried through verbatim
    because it is the informative part; this only adds the context it lacks.
    """
    try:
        return page.evaluate(expression, *args)
    except Exception as e:  # noqa: BLE001 — re-raised as a typed error below
        detail = f"{type(e).__name__}: {e}"
        if ASSET_LOAD_TIMEOUT_MARKER in str(e):
            raise CutoutRenderError(
                f"timed out after {DEFAULT_ASSET_LOAD_TIMEOUT_MS} ms while {doing}. "
                "PIXI.Assets.load never settled — an empty, malformed or "
                "zero-dimension part SVG does this. Raise "
                "DEFAULT_ASSET_LOAD_TIMEOUT_MS only if the art is genuinely "
                f"this heavy.\n{detail}"
            ) from e
        message = f"failed while {doing}:\n{detail}"
        if hint:
            message = f"{message}\n\n{hint}"
        raise CutoutRenderError(message) from e


class CutoutRenderError(RuntimeError):
    """Raised when a cutout render fails. Carries actionable detail."""


def _check_pix_fmt(pix_fmt: str | None) -> str:
    """:func:`an.media.mp4.check_pix_fmt`, refusing as a ``CutoutRenderError``.

    The validation itself (and the module global it falls back to, the seam the
    bench pulls) lives in :mod:`an.media.mp4`; this name is the stage's door to
    it, which callers that expect the renderer's own error type use. **Not the
    renderer's path**: the frame stage calls ``an.media.mp4.check_pix_fmt``, so
    rebinding this name changes no render (rebind ``DEFAULT_PIX_FMT`` instead).

    >>> _check_pix_fmt(None)
    'yuv420p'
    """
    try:
        return _mp4.check_pix_fmt(pix_fmt)
    except _mp4.MediaError as e:
        raise CutoutRenderError(str(e)) from e


def _check_capture(capture: str | None) -> str:
    """Resolve and validate the capture path; ``None`` is the module default
    **at call time**, which keeps :data:`DEFAULT_CAPTURE` flippable from outside.

    >>> _check_capture(None), _check_capture("screenshot")
    ('canvas', 'screenshot')
    """
    resolved = capture or DEFAULT_CAPTURE
    if resolved not in SUPPORTED_CAPTURES:
        raise CutoutRenderError(
            f"capture={resolved!r} is not one of {SUPPORTED_CAPTURES}. "
            "'canvas' is the default and reads the canvas in-page; 'screenshot' "
            "takes a Playwright element screenshot per instant. Both write frames "
            "with the same decoded pixels."
        )
    return resolved


@dataclass(slots=True)
class _RenderJob:
    """Per-shot scratch area + the scene that's about to render."""

    work_dir: Path
    runtime_dir: Path
    json_path: Path
    frames_dir: Path
    output_mp4: Path


def effective_step_hz(shot: Shot, ctx: RenderContext) -> float | None:
    """The stepped-timing policy a shot renders under (an#89): the shot's own
    ``step_hz`` when it declares one, else the scene's (``ctx.step_hz``), else
    ``None`` — smooth. The compiler stamps whatever this returns.

    >>> from pathlib import Path
    >>> ctx = RenderContext(mall={}, work_dir=Path("."), step_hz=15.0)
    >>> effective_step_hz(Shot(id="s"), ctx)
    15.0
    >>> effective_step_hz(Shot(id="s", step_hz=10.0), ctx)
    10.0
    >>> effective_step_hz(Shot(id="s"), RenderContext(mall={}, work_dir=Path("."))) is None
    True
    """
    return resolve_step_hz(shot, ctx.step_hz)


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


@contextmanager
def _serve_dir(directory: Path) -> Iterator[str]:
    """Run a tiny HTTP server on a free port serving ``directory``.

    Yields the base URL (``http://127.0.0.1:<port>``). Tears the server
    down on context exit. Used by the cutout renderer so PIXI.Assets can
    fetch SVG textures (file:// URLs don't work in headless Chromium).
    """

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a: Any, **kw: Any) -> None:
            super().__init__(*a, directory=str(directory), **kw)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ARG002
            return  # silence access logs

    class _Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = _Server(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


#: The staged file genres' runtime scripts are written to (`index.html` loads
#: it after `runtime.js`).
EXTENSIONS_FILE: str = "extensions.js"


def runtime_extensions() -> str:
    """The registered genres' runtime code for the stage, as one file's text --
    ``""`` when none is registered (the shipped file stays as it is).

    Part of the shot cache's key when non-empty: it can change pixels.
    """
    from an.genres.registry import runtime_scripts

    parts = [
        f"// --- {script.name} ({script.source})\n{script.code()}\n"
        for script in runtime_scripts("stage")
    ]
    return "".join(parts)


def _copy_runtime(runtime_target: Path) -> Path:
    """A fresh copy of the runtime at ``runtime_target``, with the registered
    genres' runtime scripts written into its ``extensions.js`` (an#247).

    ``runtime_dir`` is read as a module global at call time: the bench's render
    levers rebind it.
    """
    runtime_target = Path(runtime_target)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    if runtime_target.exists():
        shutil.rmtree(runtime_target)
    shutil.copytree(runtime_dir(), runtime_target)
    extensions = runtime_extensions()
    if extensions:
        (runtime_target / EXTENSIONS_FILE).write_text(extensions, encoding="utf-8")
    return runtime_target


def _stage_runtime(
    workspace: Path,
    scene_json: Any,
    *,
    mall: Mapping[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Copy the runtime into ``<workspace>/runtime``, stage the textures, write the scene.

    Returns ``(runtime directory, scene.json path)``. ``runtime_dir`` is read as
    a module global at call time: the bench's render levers rebind it.
    """
    runtime_target = _copy_runtime(Path(workspace) / "runtime")

    # Phase 11b: stage SVG character textures into the runtime dir at the
    # paths declared in scene.assets.textures, so Pixi can load them by
    # relative URL from index.html.
    if mall is not None:
        _stage_scene_assets(scene_json, mall, runtime_target)

    json_path = runtime_target / "scene.json"
    json_path.write_text(
        json.dumps(to_dict(scene_json), sort_keys=True), encoding="utf-8"
    )
    return runtime_target, json_path


def _stage_job(
    work_dir: Path,
    shot_id: str,
    scene_json: Any,
    *,
    mall: Mapping[str, Any] | None = None,
) -> _RenderJob:
    """Lay out per-shot directories + copy the runtime files + SVG assets.

    The whole layout a stage render uses, for callers that drive a page
    themselves (``cutan``'s ``tests/test_pure_pose.py``); the renderer itself gets its
    workspace and frames directory from the core frame stage, so rebinding this
    name changes no render.
    """
    from an.engines.frame_stage import _fresh_frames_dir, shot_workspace

    base = shot_workspace(work_dir, shot_id)
    frames_dir = _fresh_frames_dir(base)
    runtime_target, json_path = _stage_runtime(base, scene_json, mall=mall)
    return _RenderJob(
        work_dir=base,
        runtime_dir=runtime_target,
        json_path=json_path,
        frames_dir=frames_dir,
        output_mp4=base / f"{shot_id}.mp4",
    )


class CutoutAssetWarning(UserWarning):
    """A declared texture could not be staged into the runtime directory.

    Deliberately a warning and not an error, for now: an art package that is
    still being assembled is a real state, and refusing to render it would be
    worse than rendering it incompletely. But it must be *audible* — the
    consequence of an un-staged texture is worse than it looks and worse than
    this docstring used to claim. Measured (``misc/docs/wave4_research.md`` §4):
    an *absent* part file crashes the render with an unwrapped minified-PixiJS
    ``TypeError``; a degenerate SVG hangs it indefinitely (#79); a geometry-less
    part renders invisibly. ``PIXI.Texture.WHITE`` — the actual white rectangle —
    is reached only by a zero-byte file, an empty ``src``, or no ``src`` key.
    Either way a silent skip surfaces to the user as "the animation is broken"
    rather than as an error, which is what this warning exists to prevent.
    """


#: Texture ``src`` prefix → the mall store that resolves the rest of the path.
#:
#: A ``src`` reads ``<prefix>/<ref>/parts/head.svg`` and resolves to
#: ``mall[store]._root/<ref>/parts/head.svg``. Only ``characters/`` is emitted
#: by the compiler today; the others are here because environments, styles and
#: props all route through this same staging step as they land, and the
#: previous hardcoded ``characters/`` test silently dropped everything else.
#:
#: The prefix IS the store name plus a slash for all four, which is not an
#: accident worth relying on: the map is the contract, and a fifth kind whose
#: store is named differently must still work.
ASSET_SRC_PREFIX_TO_STORE: dict[str, str] = {
    "characters/": "characters",
    "environments/": "environments",
    "props/": "props",
    "styles/": "styles",
}


def texture_source(src_rel: str, mall: Mapping[str, Any]) -> tuple[Path | None, str]:
    """Where a texture's bytes are read from: ``(path, "")``, or ``(None, why)``.

    The ONE resolution of a texture ``src`` to a file: staging copies from it
    (:func:`_stage_scene_assets`) and the shot cache digests it
    (`an.stage.cache_key.texture_digests`), so the bytes keyed are the bytes
    drawn — a change to where art is read from (the asset library's reference
    mode, ADR 0005) changes both or neither (an#316 review). ``why`` is one of
    ``"prefix"``, ``"store"`` (absent or in-memory) and ``"missing"``.
    """
    prefix = next((p for p in ASSET_SRC_PREFIX_TO_STORE if src_rel.startswith(p)), None)
    if prefix is None:
        return None, "prefix"
    store = mall.get(ASSET_SRC_PREFIX_TO_STORE[prefix])
    root = getattr(store, "_root", None) if store is not None else None
    if root is None:
        return None, "store"
    # A raster src carries its digest as a query (an#211); the file is the
    # path before it.
    source = Path(root) / strip_version(src_rel)[len(prefix) :]
    if not source.exists():
        return None, "missing"
    return source, ""


def _stage_scene_assets(
    scene_json: Any,
    mall: Mapping[str, Any],
    runtime_target: Path,
) -> None:
    """Copy every ``assets.textures`` entry from its mall store into the runtime dir.

    Each texture's ``src`` is resolved through
    :data:`ASSET_SRC_PREFIX_TO_STORE`. Anything that cannot be resolved — an
    unknown prefix, an absent store, an in-memory store, or a file that is not
    on disk — emits a :class:`CutoutAssetWarning` naming the alias, the declared
    ``src`` and where it was looked for, rather than being skipped in silence.
    """
    textures = getattr(scene_json.assets, "textures", {}) if scene_json.assets else {}
    for alias, asset in textures.items():
        src_rel = getattr(asset, "src", None) or (
            asset.get("src") if isinstance(asset, dict) else None
        )
        if not src_rel:
            warnings.warn(
                f"texture {alias!r} declares no src; nothing to stage. "
                "The runtime will draw a white rectangle in its place — this is one "
                "of the three inputs that genuinely reach PIXI.Texture.WHITE (the "
                "others are a zero-byte file and an empty src). An absent *file* "
                "does not: it crashes at load. See misc/docs/wave4_research.md #4.",
                CutoutAssetWarning,
                stacklevel=2,
            )
            continue

        if src_rel.startswith(INLINE_SRC_PREFIX):
            # The bytes are IN the document (a text unit's glyphs, an#155):
            # there is nothing to copy, and nothing is missing.
            continue

        source, why = texture_source(src_rel, mall)
        if why == "prefix":
            warnings.warn(
                f"texture {alias!r} has src {src_rel!r}, whose prefix is not one of "
                f"{sorted(ASSET_SRC_PREFIX_TO_STORE)}. It cannot be resolved to a "
                "store, so nothing is staged for it and the render will fail at "
                "load rather than draw a stand-in.",
                CutoutAssetWarning,
                stacklevel=2,
            )
            continue

        if why == "store":
            store_name = next(
                v for k, v in ASSET_SRC_PREFIX_TO_STORE.items() if src_rel.startswith(k)
            )
            # An in-memory store is legitimate (tests do it) and has nothing on
            # disk to copy — but a scene that *declared* the texture still will
            # not get it, so say so.
            warnings.warn(
                f"texture {alias!r} resolves to the {store_name!r} store, which has "
                "no filesystem root (absent or in-memory); it cannot be staged.",
                CutoutAssetWarning,
                stacklevel=2,
            )
            continue

        if why == "missing":
            prefix = next(k for k in ASSET_SRC_PREFIX_TO_STORE if src_rel.startswith(k))
            store = mall.get(ASSET_SRC_PREFIX_TO_STORE[prefix])
            looked = Path(store._root) / strip_version(src_rel)[len(prefix) :]
            warnings.warn(
                f"texture {alias!r} declared as {src_rel!r} was not found at "
                f"{looked}. Nothing is staged for it, so the render will fail at "
                f"load rather than draw a stand-in.",
                CutoutAssetWarning,
                stacklevel=2,
            )
            continue

        target = runtime_target / strip_version(src_rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _determinism_report(page: Any) -> dict[str, Any]:
    """Read the runtime's determinism probe, and refuse a breached perimeter.

    Enforcement is ON by default (`an.determinism`), so this raises rather than
    warning: a frame that is a function of wall time or of `Math.random()` is
    not a worse frame, it is a frame that cannot be compared to any other — and
    everything downstream of here, the golden corpus and the metrics ledger
    alike, is comparison.

    A runtime too old to carry the probe is reported as such, not defaulted to
    "fine": the absence of evidence is what this whole perimeter exists against.
    """
    try:
        report = page.evaluate("() => window.anDeterminismReport()")
    except Exception as e:  # noqa: BLE001 — reported with its cause, never swallowed
        report = {"error": f"{type(e).__name__}: {e}"}
    if not isinstance(report, dict):
        report = {"error": f"the probe returned {type(report).__name__}, not an object"}

    violations = capture_violations(report)
    report["violations"] = violations
    report["enforced"] = determinism_enforced()
    if violations and report["enforced"]:
        raise CutoutRenderError(
            "the render's determinism perimeter is breached, so these frames "
            "cannot be compared with any others:\n\n"
            + "\n\n".join(f"  - {v}" for v in violations)
        )
    return report


def _checked_capture_reply(
    reply: Any, requests: list[dict[str, Any]]
) -> Iterator[tuple[int, list[bytes]]]:
    """Validate one ``anCaptureFrames`` reply against its request; yield
    ``(frame, [png bytes, ...])`` in frame order, or raise.

    The whole reply is checked before the first frame is yielded, so a bad
    batch writes nothing.
    """
    if isinstance(reply, dict) and "error" in reply:
        frame, t = reply.get("frame"), reply.get("t")
        where = (
            f"frame {frame} (t={t:.4f}s)"
            if isinstance(t, (int, float))
            else f"frame {frame}"
        )
        raise CutoutRenderError(f"{where} could not be evaluated:\n{reply['error']}")
    frames = reply.get("frames") if isinstance(reply, dict) else None
    if not isinstance(frames, list):
        raise CutoutRenderError(
            f"anCaptureFrames returned {type(reply).__name__}, not {{frames: [...]}} "
            "— is the staged runtime.js older than this renderer?"
        )
    asked = [r["frame"] for r in requests]
    got = [f.get("frame") if isinstance(f, dict) else None for f in frames]
    if got != asked:
        raise CutoutRenderError(
            f"the page returned frames {got} for a request of {asked}; a "
            "dropped or reordered frame is silent corruption, so nothing from "
            "this batch is written"
        )
    decoded = []
    for req, entry in zip(requests, frames):
        urls = entry.get("pngs")
        if not isinstance(urls, list) or len(urls) != len(req["times"]):
            raise CutoutRenderError(
                f"frame {req['frame']}: the page returned "
                f"{len(urls) if isinstance(urls, list) else urls!r} sample(s) for "
                f"{len(req['times'])} instant(s)"
            )
        try:
            pngs = [decode_data_url(u, frame=req["frame"]) for u in urls]
        except CanvasCaptureError as e:
            raise CutoutRenderError(f"canvas capture: {e}") from e
        decoded.append((req["frame"], pngs))
    yield from decoded


def _set_time(page: Any, t: float, *, frame: int) -> None:
    """Move the runtime to scene time ``t``, raising a typed, located error."""
    try:
        page.evaluate("(t) => window.anSetTime(t)", t)
    except Exception as e:
        # The runtime now raises on an unknown animated property and on an
        # animation aimed at a node that does not exist. Those escape
        # `page.evaluate` as a raw `playwright._impl._errors.Error`, which
        # says nothing about which frame or which shot — and would trade one
        # silent discard for a violation of the typed-error convention. The
        # JS message is the informative part, so it is carried through
        # verbatim rather than summarised.
        # Deliberately does not assert WHAT failed: a bare `except
        # Exception` here also catches a Playwright timeout, a closed
        # target and a crashed browser, and labelling those "the JS runtime
        # failed" points the reader at the wrong place. The nested message
        # says which it was.
        raise CutoutRenderError(
            f"frame {frame} (t={t:.4f}s) could not be evaluated:\n"
            f"{type(e).__name__}: {e}"
        ) from e


# -----------------------------------------------------------------------------
# The stage engine and its two sessions
# -----------------------------------------------------------------------------


@dataclass
class _StageSession:
    """A loaded stage page; the core frame stage drives it (``an.engines.protocol``).

    Time-driven: ``runtime.js`` evaluates the compiled channels itself, so the
    core hands it times, never states. Batched: ``frames(requests)`` carries the
    frame numbers, so a runtime throw is located by frame and time.
    """

    page: Any
    #: The engine's facts for the shot's provenance (see :meth:`provenance`).
    facts: dict[str, Any] = field(default_factory=dict)

    def frame(self, t: float) -> bytes:
        """The scene at ``t``, one instant (an error names it as frame 0).

        Every session subclass defines ``frames(requests)``; the core prefers it.
        """
        return self.frames([FrameRequest(0, (float(t),))])[0][0]

    def provenance(self) -> dict[str, Any]:
        return dict(self.facts)

    def state(self, t: float) -> dict[tuple[str, str], Any]:
        """The pose ``runtime.js`` evaluates at ``t`` (absent = at rest), not applied.

        The time-driven read-back (core study §2.7): what the engine itself
        computed, which :mod:`an.engines.conformance` holds to the timing
        kernel's golden vectors.
        """
        return self.states([t])[0]

    def states(self, times: Sequence[float]) -> list[dict[tuple[str, str], Any]]:
        """:meth:`state` at several instants in one round trip."""
        reply = _evaluate(
            self.page,
            "(ts) => window.anStates(ts)",
            [float(t) for t in times],
            doing=f"reading back the evaluated state at {len(times)} instant(s)",
        )
        if not isinstance(reply, list) or len(reply) != len(times):
            raise CutoutRenderError(
                f"anStates returned {type(reply).__name__}, not one pose per "
                "instant -- is the staged runtime.js older than this engine?"
            )
        return [
            {tuple(key.split("::", 1)): value for key, value in pose.items()}
            for pose in reply
        ]


@dataclass
class _ScreenshotStageSession(_StageSession):
    """``capture="screenshot"``: ``anSetTime`` then a Playwright element screenshot, per instant.

    The screenshot is a page capture clipped to ``#stage`` (an#57), returned as
    Chromium's own PNG bytes. With no ``resolve`` member the core passes a lone
    frame at supersample 1 through untouched -- **off is free**.
    """

    def frames(self, requests: Sequence[FrameRequest]) -> list[list[bytes]]:
        out = []
        for req in requests:
            shots = []
            for t in req.times:
                _set_time(self.page, t, frame=req.frame)
                # Located AFTER the time is set: a runtime throw must surface as
                # the typed frame error, not as whatever the locator raises first.
                shots.append(
                    self.page.locator("#stage").screenshot(omit_background=False)
                )
            out.append(shots)
        return out


@dataclass
class _CanvasStageSession(_StageSession):
    """``capture="canvas"`` (the default since an#192): the page reads its own canvas.

    ``window.anCaptureFrames`` seeks each instant and returns
    ``app.view.toDataURL('image/png')``; the reply is checked against the
    request (:func:`_checked_capture_reply`) before anything is written, and
    :meth:`resolve` turns each frame's RGBA PNGs into the frame the screenshot
    path writes (:mod:`an.stage.canvas_capture`), refusing any
    non-opaque pixel rather than guessing at a blend.
    """

    def frames(self, requests: Sequence[FrameRequest]) -> list[list[bytes]]:
        asked = requests_as_dicts(requests)
        reply = _evaluate(
            self.page,
            _CAPTURE_FRAMES_JS,
            asked,
            doing=(
                f"capturing frames {asked[0]['frame']}-{asked[-1]['frame']} "
                "from the canvas"
            ),
        )
        return [pngs for _, pngs in _checked_capture_reply(reply, asked)]

    def resolve(
        self,
        samples: Sequence[bytes],
        *,
        frame: int,
        factor: int,
        size: tuple[int, int] | None,
    ) -> bytes:
        try:
            # A module global, read at call time (tests slow it down or break it).
            return canvas_frame_png(samples, frame=frame, factor=factor, size=size)
        except CanvasCaptureError as e:
            raise CutoutRenderError(f"canvas capture: {e}") from e


#: The page size :meth:`StageEngine.open_document` uses when none is given: the
#: read-back does not depend on it, and a small canvas loads fast.
CONFORMANCE_SIZE: tuple[int, int] = (64, 48)


def _session_for(capture: str | None) -> type[_StageSession]:
    """The session class a capture path names; ``None`` is the module default."""
    return (
        _CanvasStageSession
        if _check_capture(capture) == "canvas"
        else _ScreenshotStageSession
    )


@dataclass(frozen=True)
class StageEngine:
    """The 2D stage runtime as an :class:`~an.engines.protocol.Engine`.

    Stateless: every :meth:`open` launches its own Chromium and HTTP server, so
    one instance serves a parallel render.
    """

    name: str = STAGE_ENGINE_NAME

    def check(self, ctx: RenderContext) -> None:
        """Refuse an unknown capture path before anything launches."""
        _check_capture(ctx.capture)

    @contextmanager
    def open(self, job: FrameJob) -> Iterator[_StageSession]:
        shot, ctx = job.shot, job.ctx
        capture = _check_capture(ctx.capture)
        from playwright.sync_api import sync_playwright  # noqa: F401  (local: optional dep)

        step_hz = effective_step_hz(shot, ctx)
        scene_json = compile_shot(
            shot,
            mall=ctx.mall,
            # The document's frame grid is integral; capture and mux keep the
            # exact rate (see `RenderContext.fps`). Identity for an int rate.
            fps=int(round(ctx.fps)),
            width=ctx.resolution[0],
            height=ctx.resolution[1],
            strict_assets=ctx.strict_assets,
            step_hz=step_hz,
            style_pack=ctx.style_pack,
            default_easing=ctx.default_easing,
        )
        runtime_target, _ = _stage_runtime(job.workspace, scene_json, mall=ctx.mall)
        with _loaded_page(
            runtime_target,
            to_dict(scene_json),
            size=(ctx.resolution[0], ctx.resolution[1]),
            supersample=job.supersample,
            doing=f"loading the scene for shot {shot.id!r}",
        ) as page:
            # Probed on EVERY render, judged only when enforcement is on.
            # Collecting it unconditionally puts the filter inventory into
            # RenderResult.provenance (the blink phases moved to the compiled
            # scene's meta when blinks became channels, an#88).
            determinism = _determinism_report(page)
            yield _session_for(capture)(
                page,
                facts={
                    # How the frames left the browser. Recorded because the
                    # two paths must agree on decoded pixels but not on file
                    # bytes, so a frame-byte diff between two runs is only
                    # interpretable beside it.
                    "capture": capture,
                    # The launch argv verbatim: all four rasteriser
                    # configurations report a byte-identical WebGL renderer
                    # string, so the string cannot witness the choice.
                    "chromium_args": list(DETERMINISTIC_CHROMIUM_ARGS),
                    "determinism": determinism,
                    # Per-entity blink phase (a pure function of the entity
                    # NAME): stamped by the compiler since blinks became
                    # channels (an#88), carried so a renamed character is a
                    # visible provenance diff rather than an unexplained
                    # metric shift.
                    "blink_phases": dict(scene_json.meta.blink_phases),
                    # The stepped-timing policy the tweens were compiled
                    # under (an#89); None = smooth.
                    "step_hz": scene_json.meta.step_hz,
                },
            )

    @contextmanager
    def open_document(
        self,
        document: Mapping[str, Any],
        *,
        workspace: Path,
        size: tuple[int, int] = CONFORMANCE_SIZE,
        capture: str | None = None,
    ) -> Iterator[_StageSession]:
        """A session over an already COMPILED document (a mapping in the wire
        shape), with no shot and no stores: what the conformance check against
        the timing vectors loads (:mod:`an.engines.conformance`). A document
        that is only a timeline (``timeline`` + ``animations``) gets an empty
        scene, so its read-back is the evaluator's alone."""
        doc = {
            "version": "0.1.0",
            "meta": {"width": size[0], "height": size[1]},
            "scene": {"name": "root", "children": []},
            "assets": {"textures": {}},
            **dict(document),
        }
        runtime_target = _copy_runtime(Path(workspace) / "runtime")
        with _loaded_page(
            runtime_target,
            doc,
            size=size,
            supersample=NO_SUPERSAMPLE,
            doing="loading a document",
        ) as page:
            yield _session_for(capture)(page)


@contextmanager
def _loaded_page(
    runtime_target: Path,
    scene: Mapping[str, Any],
    *,
    size: tuple[int, int],
    supersample: int,
    doing: str,
) -> Iterator[Any]:
    """Serve ``runtime_target``, launch the pinned Chromium, load ``scene``; yield the page."""
    from playwright.sync_api import sync_playwright  # local: optional dep

    # Phase 11b: serve runtime via local HTTP because PIXI.Assets.fetch()
    # can't load file:// URLs in headless Chromium. Same effect as a
    # static deployment, isolated to this render.
    with _serve_dir(runtime_target) as base_url, sync_playwright() as p:
        # `headless=True` explicitly: the default is headless today, but
        # relying on it means a Playwright default change silently swaps the
        # binary — full Chromium renders on the real GPU and differs by 1.91%.
        browser = p.chromium.launch(
            args=list(DETERMINISTIC_CHROMIUM_ARGS), headless=True
        )
        try:
            page = browser.new_page(viewport={"width": size[0], "height": size[1]})
            page.goto(f"{base_url}/index.html")

            # Injected BEFORE `anLoadScene`, which is where the PixiJS
            # application is constructed and therefore the only moment the
            # factor can reach `resolution`. `add_init_script` would be the
            # other option and is wrong: the page is already loaded by the
            # time we get here.
            _evaluate(
                page,
                "(k) => { window.anSupersample = k; }",
                int(supersample),
                doing=f"injecting the supersample factor ({supersample})",
            )

            # Wait for runtime + PixiJS to load.
            page.wait_for_function(
                "() => window.anLoadScene && window.PIXI",
                timeout=DEFAULT_RUNTIME_LOAD_TIMEOUT_MS,
            )

            # anLoadScene is async (Phase 11b: it awaits Assets.load).
            # Playwright awaits returned Promises automatically — and would
            # await a promise that never settles forever, which is exactly
            # what a degenerate part SVG produces, so the deadline is raced
            # against it inside the page (an#79).
            _evaluate(
                page,
                _LOAD_SCENE_JS,
                {"scene": dict(scene), "timeoutMs": DEFAULT_ASSET_LOAD_TIMEOUT_MS},
                doing=doing,
                hint=(
                    "A part SVG that is empty, malformed or zero-dimension makes "
                    "PIXI.Assets.load never settle; one that is absent fails the "
                    "load outright. Check the textures this shot declares."
                ),
            )

            if not _evaluate(
                page,
                "() => window.anCanvasReady()",
                doing="checking the PixiJS app initialised",
            ):
                raise CutoutRenderError(
                    "JS runtime did not initialize PixiJS app after anLoadScene"
                )
            yield page
        finally:
            browser.close()


@dataclass
class CutoutRenderer(FrameStageRenderer):
    """The stage renderer: the stage engine through the core frame stage.

    It claims both renderer names (ADR 0001 decision 9): ``stage``, the
    engine's own, and ``cutout``, the persisted name every existing scene
    carries. Its registry name stays ``cutout`` -- persisted too (the shot
    cache keys on it) -- and :data:`StageRenderer` is the same class.

    >>> r = CutoutRenderer()
    >>> r.name
    'cutout'
    >>> r.supported_renderers
    ('cutout', 'stage')
    """

    engine: Engine = field(default_factory=StageEngine)
    name: str = "cutout"
    supported_renderers: tuple[str, ...] = STAGE_RENDERER_NAMES
    error: type[Exception] = CutoutRenderError


# -----------------------------------------------------------------------------
# Driving an already-loaded page through the core capture loop
# -----------------------------------------------------------------------------


def _requests_for(
    total_frames: int, fps: float, frame_samples: Sequence[Sequence[float]] | None
) -> list[FrameRequest]:
    return [
        FrameRequest(
            i,
            (i / float(fps),) if frame_samples is None else tuple(frame_samples[i]),
        )
        for i in range(total_frames)
    ]


def _drive(session: _StageSession, requests, frames_dir, **kwargs) -> None:
    try:
        _capture.capture_frames(session, requests, frames_dir, **kwargs)
    except FrameStageError as e:
        raise CutoutRenderError(str(e)) from e


def _capture_frames(
    page: Any,
    total_frames: int,
    fps: int | float,
    frames_dir: Path,
    supersample: int = NO_SUPERSAMPLE,
    *,
    frame_samples: tuple[tuple[float, ...], ...] | None = None,
    capture: str | None = None,
    resolution: tuple[int, int] | None = None,
) -> None:
    """Step a LOADED page through ``total_frames`` and write them to ``frames_dir``.

    **Not the renderer's path** (an#247): rebinding this name changes no render
    -- the renderer runs :func:`an.engines.capture.capture_frames` through its
    frame stage. The stage half of the old frame stage, kept for callers that
    drive a page themselves: it wraps ``page`` in the session ``capture`` names (the module
    default when ``None``) and runs the core capture loop
    (:func:`an.engines.capture.capture_frames`) over it. The renderer does not
    come through here; it goes through :class:`CutoutRenderer`'s frame stage.
    """
    _drive(
        _session_for(capture)(page),
        _requests_for(total_frames, fps, frame_samples),
        frames_dir,
        factor=supersample,
        size=resolution,
    )


def _capture_frames_canvas(
    page: Any,
    total_frames: int,
    fps: int | float,
    frames_dir: Path,
    supersample: int = NO_SUPERSAMPLE,
    *,
    frame_samples: tuple[tuple[float, ...], ...] | None = None,
    resolution: tuple[int, int] | None = None,
    batch: int | None = None,
    workers: int | None = None,
    max_inflight: int | None = None,
    batch_pixels: int | None = None,
) -> None:
    """The ``capture="canvas"`` path over a loaded page, with the loop's tunables exposed.

    **Not the renderer's path** (an#247): rebinding this name changes no render.

    See :class:`_CanvasStageSession` for the page half and
    :mod:`an.engines.capture` for the loop (batching, ordering, back-pressure,
    the pixel budget).
    """
    _drive(
        _CanvasStageSession(page),
        _requests_for(total_frames, fps, frame_samples),
        frames_dir,
        factor=supersample,
        size=resolution,
        batch=batch,
        workers=workers,
        max_inflight=max_inflight,
        batch_pixels=batch_pixels,
    )


# -----------------------------------------------------------------------------
# Old names of what moved to the core (an#247): LIVE aliases, see an._shims
# -----------------------------------------------------------------------------

from an._shims import forward_module_attributes  # noqa: E402

forward_module_attributes(
    __name__,
    "an.media.mp4",
    {
        "DEFAULT_PIX_FMT": "DEFAULT_PIX_FMT",
        "SUPPORTED_PIX_FMTS": "SUPPORTED_PIX_FMTS",
        "DETERMINISTIC_X264_ARGS": "DETERMINISTIC_X264_ARGS",
        "MP4_FASTSTART_ARGS": "MP4_FASTSTART_ARGS",
        "BT709_SCALE_FILTER": "BT709_SCALE_FILTER",
        # The mux's own `subprocess` name: `patch_subprocess_run(render_mod, ...)`
        # must keep reaching the command the mux runs.
        "subprocess": "subprocess",
        "_ensure_ffmpeg_available": "ensure_ffmpeg",
        "_ffmpeg_mux": "mux_frames",
        "_ffmpeg_add_audio": "add_audio",
        "_stage_audio_inputs": "stage_audio_inputs",
        "_mux_shot": "mux_shot",
    },
)
forward_module_attributes(__name__, "an.media.frames", ["DEFAULT_FRAME_PNG_PATTERN"])
forward_module_attributes(
    __name__,
    "an.engines.capture",
    {
        "DEFAULT_CANVAS_BATCH": "DEFAULT_BATCH",
        "DEFAULT_CANVAS_ENCODE_WORKERS": "DEFAULT_ENCODE_WORKERS",
        "DEFAULT_CANVAS_BATCH_PIXELS": "DEFAULT_BATCH_PIXELS",
        "DEFAULT_CANVAS_MAX_INFLIGHT": "DEFAULT_MAX_INFLIGHT",
    },
)


#: The renderer under the engine's own name (the class is one: see
#: :class:`CutoutRenderer`), and its error under the same.
StageRenderer = CutoutRenderer
StageRenderError = CutoutRenderError


# -----------------------------------------------------------------------------
# Registration, on import of this module -- which the renderer registry does
# lazily (`an.adapters.register_lazy_renderer`), so the core never imports it.
# -----------------------------------------------------------------------------

from an.adapters._base import register_renderer as _register_renderer  # noqa: E402

_register_renderer(CutoutRenderer())

# ...and how its shots are keyed in the shot cache (ADR 0004): beside the
# renderer, so the core `an.build` never names a backend.
from an.build.keys import register_shot_keyer as _register_shot_keyer  # noqa: E402
from an.stage.cache_key import cutout_environment, cutout_shot_inputs  # noqa: E402

_register_shot_keyer(
    "cutout",
    cutout_shot_inputs,
    environment=cutout_environment,
    renderer_type=CutoutRenderer,
    # Every asset a cut-out shot depends on is read through `ctx.mall` by its
    # compile, or staged by path and digested by the `textures` part: so the
    # shot is keyed on the entries it read, not the whole project (an#316).
    records_reads=True,
)

# The versions of the vocabulary entries a shot names (ADR 0003 decision 2,
# an#248): a preset whose meaning changes re-renders the shots that play it.
from an.semantic.digest import register_vocabulary_key_part as _register_vocabulary_part  # noqa: E402

_register_vocabulary_part("cutout")
