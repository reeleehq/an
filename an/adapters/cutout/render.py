"""Headless cutout rendering: Playwright drives the JS runtime, ffmpeg muxes.

The flow per shot:

1. Compile the shot to a `CutoutSceneJSON` via `compile_shot`.
2. Stage a copy of the JS runtime in a per-shot work directory and write the
   JSON beside it.
3. Launch headless Chromium via Playwright; load `index.html`; inject the
   scene via ``window.anLoadScene``.
4. For each frame ``f`` in ``[0, total_frames)``: seek ``f/fps`` and capture the
   canvas to a PNG — by default (``capture="canvas"``, since an#192) reading its
   own pixels in-page, in batches (`an.adapters.cutout.canvas_capture`); with
   ``capture="screenshot"``, ``window.anSetTime`` plus a Playwright element
   screenshot per instant.
5. Mux the PNG sequence to mp4 with ffmpeg.

Failures are reported with concrete remediation: missing ffmpeg, missing
Chromium, runtime load timeout, etc. Subprocess errors are wrapped at the
facade boundary.
"""

from __future__ import annotations

import http.server
import json
import shutil
import socketserver
import subprocess
import threading
import warnings
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from an.adapters._base import RenderContext, RenderResult
from an.adapters.cutout.supersample import (
    NO_SUPERSAMPLE,
    check_factor,
    resolve_png_bytes,
)
from an.base import BT709_SCALE_FILTER, MP4_FASTSTART_ARGS
from an.determinism import capture_violations, determinism_enforced
from an.adapters.cutout.canvas_capture import (
    CanvasCaptureError,
    canvas_frame_png,
    decode_data_url,
)
from an.adapters.cutout.compile import compile_shot
from an.adapters.cutout.shutter import check_frame_samples, mean_png_bytes
from an.adapters.cutout.runtime_files import runtime_dir
from an.adapters.cutout.serialize import to_dict
from an.adapters.cutout.text import INLINE_SRC_PREFIX
from an.ir.schema import Shot, resolve_step_hz


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
DEFAULT_FRAME_PNG_PATTERN: str = "frame_%06d.png"

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

#: x264 encode knobs pinned so the delivered mp4 is a function of the frames
#: rather than of the machine (an#34, research §2).
#:
#: `-threads 1` — `-threads 1/4/11` all give bit-identical decoded pixels, so
#: this looks unnecessary on a laptop. It is not: `auto` raises
#: `lookahead_threads` above 1 at roughly `-threads >= 12`, and a forced
#: `lookahead-threads=4` changes 86.2% of the bytes (max delta 80). A big CI
#: runner crosses that line and a 4-core dev box never will, which is precisely
#: how an unpinned thread count ships without anyone seeing it.
#:
#: `-crf 23 -preset medium` — both are libx264's compiled-in defaults today, so
#: passing them changes nothing now and pins us against a build whose defaults
#: differ. Worth pinning because preset swings distinct colour counts **2.3x,
#: non-monotonically** (ultrafast 3141, veryfast 7296, medium 6064, slower 5393)
#: against a crf18->23 signal of 1.35x — an unpinned preset dominates the very
#: signal a quality ledger tries to measure.
#:
#: BT.709 is the one knob here that CHANGES today's output, and it changes more
#: than the research predicted — measured, not assumed (an#34):
#:
#: - `-colorspace bt709` does not merely *tag* the file. It sets the matrix of
#:   the auto-inserted RGB->YUV conversion, so the **encoded luma and chroma
#:   planes themselves change**. Confirmed by construction: forcing
#:   `scale=out_color_matrix=bt601` reproduces the untagged output's decoded
#:   stream byte-for-byte, i.e. `an` has been converting with BT.601 all along.
#:   **On ffmpeg 8/9. It is false on ffmpeg 6.1** — where the same flags reach
#:   only the VUI and the planes stay BT.601 (an#148, measured; see
#:   `an.base.BT709_SCALE_FILTER` for the numbers). That is why the mux now
#:   states the conversion explicitly with `-vf` instead of inferring it from
#:   these flags, which stay for the tag they land.
#: - `-color_range tv` is a **no-op today** (limited range is already the
#:   default for yuv420p here). Pinned anyway, so a build that defaults
#:   differently cannot change the output silently.
#: - The ffmpeg-level `-color_primaries` / `-color_trc` flags **do not reach the
#:   bitstream**: with them alone, ffprobe reports `color_space=bt709` and
#:   `color_primaries=unknown`, `color_transfer=unknown`. `-x264-params` is what
#:   lands all three in the VUI, and it leaves the decoded stream identical. A
#:   half-tagged file is worse than an untagged one — the player stops guessing
#:   the matrix but still guesses the primaries.
#:
#: Why bother: untagged, the *player* picks its matrix by a height heuristic
#: (BT.601 below ~576 lines). Every shipped `an` example is 320x240 to 640x360,
#: so encode and playback agree by luck; at 1080p the same code would encode
#: with BT.601 and be displayed as BT.709, a silent, resolution-dependent colour
#: error. Pinning both sides to BT.709 makes them agree at every resolution.
#: This is a **one-time deliberate re-baseline** of every mp4 — cheap now,
#: because no ledger exists yet to invalidate.
#: The delivered encode's pixel format, and **the one first-order quality lever
#: in this file**. Measured on 30 real 1080p `an` frames, edge-band mean error:
#: current flags 11.35, crf18 4:2:0 11.05, crf18 `-tune animation` 10.96,
#: mathematically lossless 4:2:0 **10.15** — and crf18 **4:4:4 3.79**.
#: Losslessness buys 8%; dropping chroma subsampling buys **66%**. Wave 2's own
#: conclusion: "bitrate is second-order, pixel format is first-order".
#:
#: **The default stays 4:2:0 because that is a PRODUCT constraint, not an
#: encoder-tuning one.** High 4:4:4 Predictive is refused by many hardware
#: decoders, browsers and platforms, so flipping it would hand a design partner
#: a file they cannot play. 4:4:4 is reachable per render
#: (`an render --pix-fmt yuv444p`), which is the right shape for a knob whose
#: right answer depends on where the file is going.
#:
#: Read as a MODULE GLOBAL at call time, deliberately: that is what lets the
#: bench's lever rebind it from outside, exactly as `high_crf` rebinds
#: `DETERMINISTIC_X264_ARGS`. Hoisting either into a default argument binds it
#: at `def` time and disarms the lever silently.
DEFAULT_PIX_FMT: str = "yuv420p"

#: The formats the knob accepts. Not an open string: a typo would reach ffmpeg
#: as an obscure failure minutes into a render, and a format outside this set
#: has not been measured against the panel.
SUPPORTED_PIX_FMTS: tuple[str, ...] = ("yuv420p", "yuv444p")

#: How frames leave the browser. ``"canvas"`` (the default since an#192): the
#: runtime's ``anCaptureFrames`` reads the canvas in-page and hands back PNG data
#: URLs in batches (`an.adapters.cutout.canvas_capture`), which writes frames
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

#: Frames per ``anCaptureFrames`` round trip. Measured at 1920x1080 on an M1
#: Max, `single_character`: 67 ms/frame one frame per call, 46 at four, 46 at
#: eight — the round trip is ~20 ms of fixed cost, amortised by the batch. It is
#: also the memory the page holds before Python takes it: eight data URLs of a
#: 1080p frame are well under a megabyte of text, and at a supersampled 4K
#: backbuffer a few megabytes each.
DEFAULT_CANVAS_BATCH: int = 8

#: Threads decoding, resolving and re-encoding canvas frames while the page
#: renders the next batch. The decode/encode is ~60 ms/frame of Pillow and zlib
#: at 1080p — the same order as the page's own work — so it must overlap it or
#: it eats the win. Two, not `cpu_count()`: `an render --parallel` already runs
#: one Chromium per shot, and each of them is another source of CPU pressure.
DEFAULT_CANVAS_ENCODE_WORKERS: int = 2

#: The same two bounds in CAPTURED PIXELS (backbuffer pixels, so a supersample
#: counts k² times and an open shutter once per instant): at most this many per
#: ``anCaptureFrames`` round trip, and twice this many waiting on the encode
#: pool. Two 1080p instants: small scenes still batch by the frame count
#: above, and at 1080p the batch size stopped mattering for a flat scene
#: (96 frames: 4.7 s at 2, 4 or 8 per round trip) while it decides everything
#: for an incompressible one (a grain pack, 48 frames: 11.0 s / 0.38 GB at 2
#: against 17.8 s / 2.1 GB at 8; the screenshot path 17.8 s / 0.16 GB). Needed
#: because a count alone does not bound the bytes: the review of an#192
#: measured grain at supersample 2 with an 8-sample shutter overflowing the
#: driver's string limit in ONE reply (the render hung in ``browser.close()``),
#: and ~16 GB of Python memory at supersample 3. A frame whose instants alone
#: exceed it is captured over several round trips.
DEFAULT_CANVAS_BATCH_PIXELS: int = 2 * 1920 * 1080

#: BACK-PRESSURE: frames handed to the encode pool and not yet written. When
#: the pool falls behind, the capture loop blocks on the oldest one before it
#: asks the page for more, so memory is bounded by this many frames plus one
#: batch however long the shot is.
DEFAULT_CANVAS_MAX_INFLIGHT: int = 2 * DEFAULT_CANVAS_BATCH

#: The page-side capture call; see ``anCaptureFrames`` in ``runtime.js``.
_CAPTURE_FRAMES_JS: str = "(requests) => window.anCaptureFrames(requests)"

DETERMINISTIC_X264_ARGS: tuple[str, ...] = (
    "-threads",
    "1",
    "-crf",
    "23",
    "-preset",
    "medium",
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
    # The half that actually reaches the bitstream; see above.
    "-x264-params",
    "colorprim=bt709:transfer=bt709:colormatrix=bt709",
)


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
    """Resolve and validate the pixel format, or refuse with the whole list.

    ``None`` resolves to :data:`DEFAULT_PIX_FMT` **at call time**, which is what
    lets the bench's lever rebind the module global and reach this render.

    Refuses an unknown format rather than passing it to ffmpeg: a typo would
    otherwise surface minutes into a render as an obscure encoder error, and on
    the second shot of a parallel render it would surface from a thread. A
    format outside the list has also never been measured against the panel.
    """
    resolved = pix_fmt or DEFAULT_PIX_FMT
    if resolved not in SUPPORTED_PIX_FMTS:
        raise CutoutRenderError(
            f"pix_fmt={resolved!r} is not one of {SUPPORTED_PIX_FMTS}. 4:4:4 is "
            "opt-in and 4:2:0 is the default for a PRODUCT reason rather than "
            "an encoder one — High 4:4:4 Predictive is refused by many hardware "
            "decoders, browsers and platforms, so a 4:4:4 file is one some "
            "viewers cannot play."
        )
    return resolved


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


class CutoutRenderer:
    """Headless cutout renderer: Playwright + ffmpeg.

    >>> r = CutoutRenderer()
    >>> r.name
    'cutout'
    >>> r.supported_renderers
    ('cutout',)
    """

    name: str = "cutout"
    supported_renderers: tuple[str, ...] = ("cutout",)

    def can_render(self, shot: Shot) -> bool:
        return shot.renderer in self.supported_renderers

    def render(self, shot: Shot, ctx: RenderContext) -> RenderResult:
        """Render ``shot`` to mp4 using ``ctx`` for paths + parameters."""
        _ensure_ffmpeg_available()
        # Validated before anything launches: a browser and a scene compile are
        # minutes, and `check_factor` is microseconds.
        supersample = check_factor(ctx.supersample)
        pix_fmt = _check_pix_fmt(ctx.pix_fmt)
        capture = _check_capture(ctx.capture)
        total_frames = max(1, int(round(shot.duration * ctx.fps)))
        frame_samples = check_frame_samples(
            ctx.frame_samples, total_frames=total_frames, duration=shot.duration
        )
        from playwright.sync_api import sync_playwright  # local: optional dep

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

        job = _stage_job(ctx.work_dir, shot.id, scene_json, mall=ctx.mall)

        # Drive Chromium → capture frames (canvas read or screenshot, `capture`).
        # Phase 11b: serve runtime via local HTTP because PIXI.Assets.fetch()
        # can't load file:// URLs in headless Chromium. Same effect as a
        # static deployment, isolated to this render.
        with _serve_dir(job.runtime_dir) as base_url, sync_playwright() as p:
            # `headless=True` explicitly: the default is headless today, but
            # relying on it means a Playwright default change silently swaps the
            # binary — full Chromium renders on the real GPU and differs by 1.91%.
            browser = p.chromium.launch(
                args=list(DETERMINISTIC_CHROMIUM_ARGS), headless=True
            )
            try:
                page = browser.new_page(
                    viewport={"width": ctx.resolution[0], "height": ctx.resolution[1]}
                )
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

                scene_dict = to_dict(scene_json)
                # anLoadScene is async (Phase 11b: it awaits Assets.load).
                # Playwright awaits returned Promises automatically — and would
                # await a promise that never settles forever, which is exactly
                # what a degenerate part SVG produces, so the deadline is raced
                # against it inside the page (an#79).
                _evaluate(
                    page,
                    _LOAD_SCENE_JS,
                    {"scene": scene_dict, "timeoutMs": DEFAULT_ASSET_LOAD_TIMEOUT_MS},
                    doing=f"loading the scene for shot {shot.id!r}",
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

                # Probed on EVERY render, judged only when enforcement is on.
                # Collecting it unconditionally puts the filter inventory into
                # RenderResult.provenance (the blink phases moved to the compiled
                # scene's meta when blinks became channels, an#88). (An earlier
                # version of this comment claimed the metrics ledger stamps
                # them; it does not — `SceneCapture.determinism` is declared
                # and never populated, and no ledger row carries a determinism
                # key. The provenance record on the render result is real.)
                determinism = _determinism_report(page)

                _capture_frames(
                    page,
                    total_frames,
                    ctx.fps,
                    job.frames_dir,
                    supersample,
                    frame_samples=frame_samples,
                    capture=capture,
                    resolution=tuple(ctx.resolution),
                )
            finally:
                browser.close()

        n_audio_tracks = _mux_shot(
            job.frames_dir,
            shot,
            ctx,
            job.work_dir,
            job.output_mp4,
            n_frames=total_frames,
            pix_fmt=pix_fmt,
        )

        return RenderResult(
            mp4_path=job.output_mp4,
            duration=shot.duration,
            frame_manifest=sorted(job.frames_dir.glob("*.png")),
            log="",
            provenance={
                "shot_id": shot.id,
                "fps": ctx.fps,
                "resolution": ctx.resolution,
                # The DECLARED size, unchanged by supersampling — the frames on
                # disk are always this, because the resolve runs in the frame
                # stage. `supersample` beside it is what says how they got there.
                "supersample": supersample,
                "pix_fmt": pix_fmt,
                # How the frames left the browser. Recorded because the two
                # paths must agree on decoded pixels but not on file bytes, so a
                # frame-byte diff between two runs is only interpretable beside it.
                "capture": capture,
                "frame_count": total_frames,
                "audio_tracks": n_audio_tracks,
                # The launch argv verbatim: all four rasteriser configurations
                # report a byte-identical WebGL renderer string, so the string
                # cannot witness the choice and the argv is the only guard.
                "chromium_args": list(DETERMINISTIC_CHROMIUM_ARGS),
                "x264_args": list(DETERMINISTIC_X264_ARGS),
                "determinism": determinism,
                # Per-entity blink phase (a pure function of the entity NAME):
                # stamped by the compiler since blinks became channels (an#88),
                # carried here so a renamed character is a visible provenance
                # diff rather than an unexplained metric shift.
                "blink_phases": dict(scene_json.meta.blink_phases),
                # The stepped-timing policy the tweens were compiled under
                # (an#89); None = smooth. Recorded so a stepped render is a
                # visible provenance fact, not a mystery in the motion.
                "step_hz": scene_json.meta.step_hz,
                # Present only when a frame clock was supplied, so an ordinary
                # render's provenance is unchanged. The instants verbatim: a
                # blurred or jittered frame is only interpretable beside them.
                **(
                    {"frame_samples": [list(f) for f in frame_samples]}
                    if frame_samples is not None
                    else {}
                ),
            },
        )


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


def _ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise CutoutRenderError(
            "ffmpeg not found on PATH. Install with: brew install ffmpeg "
            "(macOS) or apt install ffmpeg (Linux)."
        )


def _stage_job(
    work_dir: Path,
    shot_id: str,
    scene_json: Any,
    *,
    mall: Mapping[str, Any] | None = None,
) -> _RenderJob:
    """Lay out per-shot directories + copy the runtime files + SVG assets."""
    base = Path(work_dir) / f"shot_{shot_id}"
    runtime_target = base / "runtime"
    frames_dir = base / "frames"
    base.mkdir(parents=True, exist_ok=True)
    # Cleared, not reused: `.an/render_work` persists, and frames left by a
    # longer earlier render of this shot would otherwise sit past this one's
    # last frame — in `frame_manifest`, and in the pattern the mux reads.
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    if runtime_target.exists():
        shutil.rmtree(runtime_target)
    shutil.copytree(runtime_dir(), runtime_target)

    # Phase 11b: stage SVG character textures into the runtime dir at the
    # paths declared in scene.assets.textures, so Pixi can load them by
    # relative URL from index.html.
    if mall is not None:
        _stage_scene_assets(scene_json, mall, runtime_target)

    json_path = runtime_target / "scene.json"
    json_path.write_text(
        json.dumps(to_dict(scene_json), sort_keys=True), encoding="utf-8"
    )
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

        prefix = next(
            (p for p in ASSET_SRC_PREFIX_TO_STORE if src_rel.startswith(p)), None
        )
        if prefix is None:
            warnings.warn(
                f"texture {alias!r} has src {src_rel!r}, whose prefix is not one of "
                f"{sorted(ASSET_SRC_PREFIX_TO_STORE)}. It cannot be resolved to a "
                "store, so nothing is staged for it and the render will fail at "
                "load rather than draw a stand-in.",
                CutoutAssetWarning,
                stacklevel=2,
            )
            continue

        store_name = ASSET_SRC_PREFIX_TO_STORE[prefix]
        store = mall.get(store_name)
        root = getattr(store, "_root", None) if store is not None else None
        if root is None:
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

        source = Path(root) / src_rel[len(prefix) :]
        if not source.exists():
            warnings.warn(
                f"texture {alias!r} declared as {src_rel!r} was not found at "
                f"{source}. Nothing is staged for it, so the render will fail at "
                f"load rather than draw a stand-in.",
                CutoutAssetWarning,
                stacklevel=2,
            )
            continue

        target = runtime_target / src_rel
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


def _capture_frames(
    page: Any,
    total_frames: int,
    fps: int,
    frames_dir: Path,
    supersample: int = NO_SUPERSAMPLE,
    *,
    frame_samples: tuple[tuple[float, ...], ...] | None = None,
    capture: str | None = None,
    resolution: tuple[int, int] | None = None,
) -> None:
    """Step the JS runtime through ``total_frames`` and capture the canvas each time.

    ``capture`` picks how the pixels leave the browser (:data:`DEFAULT_CAPTURE`
    when ``None``): ``"screenshot"`` is the loop below, ``"canvas"`` is
    :func:`_capture_frames_canvas`. Both write the same decoded frames to the same
    files; the dispatch lives HERE, inside the one function the bench's
    supersample lever wraps, so the lever reaches either path. ``resolution``
    (the declared width, height) lets the canvas path refuse a frame of the wrong
    size before it is written; the screenshot path does not read it.

    **The resolve happens here, in the frame stage, and that is not a stylistic
    choice.** Nothing downstream reads a resolution off the files: the bench's
    `capture.resolution` comes from the staged scene's `meta`, `_ffmpeg_mux`
    trusts whatever the PNGs are, and the golden gate compares against a frame
    blessed at the declared size. k-times PNGs left on disk would mux a 640x480
    video against a 320x240 declaration and put every render-side measurement
    out of reach — loudly since an#54, silently before it.

    An ffmpeg-side `-vf scale` would be the other place to put it, and is
    refused: it moves `x264_argv`, which refuses every encode-side metric, and
    retires the cross-arch verdict's "ffmpeg never touches a frame" clause.

    At ``supersample == 1`` this is byte-for-byte the old path — Chromium writes
    straight to disk and nothing decodes anything. **Off is free.**

    ``frame_samples`` (see ``RenderContext.frame_samples``) names, per frame,
    the instants to capture and average — an open shutter, capture jitter, or
    both. ``None`` is one instant at ``i / fps``, and a frame with one instant
    takes the path above unchanged, so the knob is free when it is off too.
    """
    if _check_capture(capture) == "canvas":
        _capture_frames_canvas(
            page,
            total_frames,
            fps,
            frames_dir,
            supersample,
            frame_samples=frame_samples,
            resolution=resolution,
        )
        return
    for i in range(total_frames):
        instants = (i / float(fps),) if frame_samples is None else frame_samples[i]
        out_path = frames_dir / (DEFAULT_FRAME_PNG_PATTERN % i)
        if len(instants) == 1 and supersample == NO_SUPERSAMPLE:
            _set_time(page, instants[0], frame=i)
            # Screenshot only the canvas element (no surrounding chrome). Located
            # AFTER the time is set, as before this loop grew samples: a runtime
            # throw must surface as the typed frame error, not as whatever the
            # locator raises first.
            page.locator("#stage").screenshot(path=str(out_path), omit_background=False)
            continue
        shots = []
        for t in instants:
            _set_time(page, t, frame=i)
            shots.append(page.locator("#stage").screenshot(omit_background=False))
        out_path.write_bytes(mean_png_bytes(shots, factor=supersample))


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
    """The ``capture="canvas"`` frame stage: in-page reads, batched, ordered, bounded.

    Per round trip the page seeks up to ``batch`` frames' instants **in frame
    order, samples in the order given** — the order the screenshot path seeks
    them. Since an#185 the pose is a pure function of ``t``, so the order no
    longer decides the picture; it is kept because the page echoes frame numbers
    in it — and returns each frame's canvas as PNG data URLs. The decode,
    opacity check, supersample and temporal resolve, and RGB re-encode
    (:func:`~an.adapters.cutout.canvas_capture.canvas_frame_png`) run on a
    small thread pool while the page renders the next batch.

    Two corruptions are silent unless refused, so both are refused explicitly:

    - **A dropped or reordered frame.** The page echoes each frame number; the
      reply must be exactly the frames requested, in the order requested, each
      with one PNG per instant — otherwise this raises before anything is
      written from that batch. Every file is named by the frame number the page
      echoed and the loop's own index agreeing, never by arrival order from the
      pool; and before returning, every frame file ``0..total_frames-1`` must
      exist on disk (redundant with the above by construction — kept because
      the mux reads the directory, not this loop's bookkeeping).
    - **Unbounded buffering.** At most ``max_inflight`` frames sit in the pool
      unwritten; past that the loop blocks on the OLDEST before asking the page
      for more (back-pressure), so a long shot costs bounded memory.

    Both bounds are ALSO held in captured pixels when ``resolution`` is known
    (:data:`DEFAULT_CANVAS_BATCH_PIXELS`, ``batch_pixels``): a round trip
    carries at most that many backbuffer pixels, the pool at most twice that,
    and a frame whose instants alone exceed it is captured over several round
    trips and encoded once all of them are in. A frame count alone bounds
    nothing when a frame is a k-times, many-sample, incompressible canvas.

    ``None`` for ``batch`` / ``workers`` / ``max_inflight`` / ``batch_pixels``
    reads the module defaults at call time.
    """
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor

    batch = batch or DEFAULT_CANVAS_BATCH
    workers = workers or DEFAULT_CANVAS_ENCODE_WORKERS
    max_inflight = max(1, max_inflight or DEFAULT_CANVAS_MAX_INFLIGHT)
    budget = batch_pixels or DEFAULT_CANVAS_BATCH_PIXELS
    instants = [
        (i / float(fps),) if frame_samples is None else tuple(frame_samples[i])
        for i in range(total_frames)
    ]
    # Backbuffer pixels per captured instant; 0 (unknown) disables the pixel
    # bounds and leaves the frame counts in charge, as before.
    per_instant = (
        resolution[0] * resolution[1] * supersample * supersample if resolution else 0
    )

    def _encode(i: int, pngs: list[bytes]) -> int:
        out = frames_dir / (DEFAULT_FRAME_PNG_PATTERN % i)
        try:
            data = canvas_frame_png(pngs, frame=i, factor=supersample, size=resolution)
        except CanvasCaptureError as e:
            raise CutoutRenderError(f"canvas capture: {e}") from e
        out.write_bytes(data)
        return i

    def _round_trips() -> Iterator[list[tuple[dict[str, Any], bool]]]:
        """Requests grouped into round trips, each ``(request, frame_done)``.
        A frame's instants are split only when they alone exceed the budget,
        so the parts of one frame never share a round trip."""
        per_part = max(1, budget // per_instant) if per_instant else None
        trip: list[tuple[dict[str, Any], bool]] = []
        trip_pixels = 0
        for i, times in enumerate(instants):
            step = per_part or len(times)
            for j in range(0, len(times), step):
                part = list(times[j : j + step])
                pixels = len(part) * per_instant
                if trip and (
                    len(trip) >= batch
                    or (per_instant and trip_pixels + pixels > budget)
                ):
                    yield trip
                    trip, trip_pixels = [], 0
                trip.append(({"frame": i, "times": part}, j + step >= len(times)))
                trip_pixels += pixels
        if trip:
            yield trip

    written: list[int] = []
    inflight: deque = deque()  # (future, pixels)
    inflight_pixels = 0
    pending: list[bytes] = []  # the samples of a frame split across round trips
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="an-canvas"
    ) as pool:
        try:
            for trip in _round_trips():
                requests = [req for req, _ in trip]
                reply = _evaluate(
                    page,
                    _CAPTURE_FRAMES_JS,
                    requests,
                    doing=(
                        f"capturing frames {requests[0]['frame']}-"
                        f"{requests[-1]['frame']} from the canvas"
                    ),
                )
                checked = list(_checked_capture_reply(reply, requests))
                for (i, pngs), (_, done) in zip(checked, trip):
                    pending.extend(pngs)
                    if not done:
                        continue
                    pixels = len(pending) * per_instant
                    while inflight and (
                        len(inflight) >= max_inflight
                        or (per_instant and inflight_pixels + pixels > 2 * budget)
                    ):
                        fut, done_pixels = inflight.popleft()
                        written.append(fut.result())
                        inflight_pixels -= done_pixels
                    inflight.append((pool.submit(_encode, i, pending), pixels))
                    inflight_pixels += pixels
                    pending = []
            while inflight:
                written.append(inflight.popleft()[0].result())
        finally:
            # A failure anywhere must not leave encodes running against a
            # frames directory the caller is about to treat as finished.
            for fut, _ in inflight:
                fut.cancel()
    # Belt and braces, checked on DISK rather than on the bookkeeping above
    # (which is correct by construction): the mux reads the directory, so the
    # directory is what must hold every frame exactly once.
    missing = [
        i
        for i in range(total_frames)
        if not (frames_dir / (DEFAULT_FRAME_PNG_PATTERN % i)).is_file()
    ]
    if written != list(range(total_frames)) or missing:
        raise CutoutRenderError(
            f"canvas capture finished with frames {missing[:5]} missing from "
            f"{frames_dir} ({len(written)} of {total_frames} encoded); a dropped "
            "frame is silent corruption, so this refuses rather than muxing it"
        )


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


def _ffmpeg_mux(
    frames_dir: Path, fps: int, output_mp4: Path, pix_fmt: str | None = None
) -> None:
    """Mux a PNG sequence to H.264 mp4.

    ``pix_fmt=None`` means "whatever the module default is **right now**", which
    is what keeps the bench's `pix_fmt` lever able to reach this call by
    rebinding :data:`DEFAULT_PIX_FMT`. A caller that passes one wins; the bench
    never passes one, so the lever reaches the encode AND the recorded
    environment, and the two cannot disagree.
    """
    # Resolved AND validated through the one function that does both, so a
    # direct call to the mux cannot slip an unmeasured format past the check
    # `CutoutRenderer.render` performs — and so there is one place that turns
    # `None` into the module default, which is the seam the lever pulls.
    resolved = _check_pix_fmt(pix_fmt)
    pattern = str(frames_dir / DEFAULT_FRAME_PNG_PATTERN)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-i",
        pattern,
        # The RGB->YUV conversion, NAMED rather than inferred from the colour
        # tags below — which reach it on ffmpeg 8/9 and do not on ffmpeg 6.1
        # (an#148). Byte-identical to the pre-an#148 output on a build where
        # they did reach it.
        "-vf",
        BT709_SCALE_FILTER,
        "-c:v",
        "libx264",
        "-pix_fmt",
        resolved,
        *DETERMINISTIC_X264_ARGS,
        # Kept, though this file is an intermediate `silent.mp4` that never
        # ships and whose container `_ffmpeg_add_audio` re-lays anyway. The
        # point of naming the constant is that the answer to "does an's mp4
        # have faststart" stops depending on which of the three commands you
        # happen to be reading.
        *MP4_FASTSTART_ARGS,
        str(output_mp4),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        raise CutoutRenderError(f"ffmpeg failed to launch: {e}") from e
    if result.returncode != 0 or not output_mp4.exists():
        raise CutoutRenderError(
            "ffmpeg mux failed (rc=%d):\n%s" % (result.returncode, result.stderr)
        )


def _stage_audio_inputs(
    shot: Shot, ctx: RenderContext, work_dir: Path
) -> list[tuple[Path, float]]:
    """Write the shot's per-dialogue audio bytes to disk and return (path, delay)s.

    Looks up each ``dialogue.audio_ref`` in ``mall["audio"]``. Lines without
    an audio_ref or duration are skipped silently. Returns ``[]`` when no
    audio is available, so the caller can use a video-only path.
    """
    audio_store = ctx.mall.get("audio") if ctx.mall else None
    if not audio_store:
        return []
    out: list[tuple[Path, float]] = []
    for i, line in enumerate(shot.dialogue):
        if not line.audio_ref or line.start is None:
            continue
        try:
            audio_bytes = audio_store[line.audio_ref]
        except KeyError:
            continue
        # Sniff format: WAV starts with 'RIFF', mp3 with 'ID3' or 0xFFFB.
        if audio_bytes[:4] == b"RIFF":
            ext = "wav"
        elif audio_bytes[:3] == b"ID3" or audio_bytes[:1] == b"\xff":
            ext = "mp3"
        else:
            ext = "wav"
        path = work_dir / f"audio_{i}_{line.audio_ref[:8]}.{ext}"
        path.write_bytes(audio_bytes)
        out.append((path, float(line.start)))
    return out


def _mux_shot(
    frames_dir: Path,
    shot: Shot,
    ctx: RenderContext,
    work_dir: Path,
    output_mp4: Path,
    *,
    n_frames: int,
    pix_fmt: str | None = None,
) -> int:
    """Frames → the delivered per-shot mp4: a silent mux, then the audio mux.
    Returns how many dialogue audio tracks were laid under the picture.

    Every shot mp4 carries an AAC stream (silent if no dialogue) so the final
    ffmpeg concat across heterogeneous shots works without surprises. The audio
    is cut to the PICTURE's length, ``n_frames / fps``, not ``shot.duration``:
    a duration that is not a whole number of frames (2.6 s at 24 fps is 62.4)
    gets ``round(d * fps)`` frames, and an audio track padded to ``d`` made the
    shot's container longer than its picture — the concat then advanced by the
    container and left sub-frame holes in the film's video timestamps, which
    ffprobe reads as ``r_frame_rate=120/1`` (an#195).
    """
    silent_mp4 = work_dir / "silent.mp4"
    _ffmpeg_mux(frames_dir, ctx.fps, silent_mp4, pix_fmt)
    audio_inputs = _stage_audio_inputs(shot, ctx, work_dir)
    _ffmpeg_add_audio(silent_mp4, audio_inputs, output_mp4, n_frames / ctx.fps)
    return len(audio_inputs)


def _ffmpeg_add_audio(
    video_path: Path,
    audio_inputs: list[tuple[Path, float]],
    output_path: Path,
    duration_s: float,
) -> None:
    """Mux a silence base + ``audio_inputs`` (path, delay_s) onto ``video_path``.

    Always emits an audio stream. ``anullsrc`` provides the silent base track
    of length ``duration_s`` so concat across shots is safe; dialogue lines
    are overlaid via ``adelay`` + ``amix``. ``duration_s`` must be the
    picture's length (frames / fps): the concat advances each shot by its
    container length, which is the longer of the two streams (an#195).
    """
    sr = 44100
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        # Silent base (input #1)
        "-f",
        "lavfi",
        "-t",
        f"{duration_s:.6f}",
        "-i",
        f"anullsrc=channel_layout=mono:sample_rate={sr}",
    ]
    for audio_path, _delay in audio_inputs:
        cmd += ["-i", str(audio_path)]

    filter_parts: list[str] = []
    # Resample silence base to ensure consistent format with dialogue inputs.
    filter_parts.append(
        f"[1:a]aformat=sample_fmts=fltp:sample_rates={sr}:channel_layouts=mono[base]"
    )
    overlays: list[str] = []
    for i, (_path, delay_s) in enumerate(audio_inputs):
        delay_ms = max(0, int(round(delay_s * 1000)))
        # Index in command: 0=video, 1=anullsrc, 2..=user audio
        cmd_idx = i + 2
        label = f"a{i}"
        filter_parts.append(
            f"[{cmd_idx}:a]aformat=sample_fmts=fltp:sample_rates={sr}:channel_layouts=mono,"
            f"adelay={delay_ms}|{delay_ms}[{label}]"
        )
        overlays.append(f"[{label}]")

    # Mix [base] + all overlays (always at least 1 input for amix).
    inputs_count = 1 + len(overlays)
    mix_in = "[base]" + "".join(overlays)
    filter_parts.append(
        f"{mix_in}amix=inputs={inputs_count}:dropout_transition=0:normalize=0[aout]"
    )

    cmd += [
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        str(sr),
        "-ac",
        "1",
        "-t",
        f"{duration_s:.6f}",
        # THE DELIVERED per-shot mp4 is this one, not `_ffmpeg_mux`'s. `-c:v
        # copy` re-lays the container and writes `moov` last, so without this
        # every shot mp4 `an` has ever produced is progressive-download
        # hostile -- including the bytes that go into `mall["shots"]` and,
        # via the single-shot `shutil.copy` branch, into `output/main.mp4`.
        *MP4_FASTSTART_ARGS,
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        raise CutoutRenderError(f"ffmpeg audio mux failed to launch: {e}") from e
    if result.returncode != 0 or not output_path.exists():
        raise CutoutRenderError(
            "ffmpeg audio mux failed (rc=%d):\n%s" % (result.returncode, result.stderr)
        )
