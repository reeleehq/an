"""Project-level rendering: per-shot mp4 → final composited mp4 via ffmpeg concat.

The orchestrator picks a renderer per shot from the registry (matched on
``shot.renderer``) and renders each shot in isolation, then concatenates the
per-shot outputs into one final mp4 written to ``project.mall["output"]``.

Phase 2D ships the cutout path; later phases register Manim / Remotion / etc.
adapters and the same flow handles them.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

from an.adapters._base import RenderContext, RenderResult
from an.assemble import assemble_film, film_timeline, needs_assembly
from an.adapters.cutout.compile import style_pack_for
from an.adapters._base import _DEFAULT_REGISTRY
from an.build.shot_cache import IncrementalEngine, ShotPlan, resolve_incremental
from an.base import (
    DEFAULT_FPS,
    DEFAULT_RESOLUTION,
    DEFAULT_SUPERSAMPLE,
    MP4_FASTSTART_ARGS,
)
from an.ir.schema import Shot
from an.project import Project, load


logger = logging.getLogger("an.build")

#: Under ``.an/render_work/``: one directory per CACHED render run.
RENDER_RUNS_DIR: str = "runs"

#: In a run directory: the pid of the process rendering it (written at start).
RUN_LIVE_MARKER: str = ".live"
#: In a run directory: written when the run delivered its film.
RUN_DONE_MARKER: str = ".done"


def _run_id() -> str:
    import secrets

    return f"{time.strftime('%Y%m%dT%H%M%S')}_{os.getpid()}_{secrets.token_hex(3)}"


def _start_run(work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / RUN_LIVE_MARKER).write_text(str(os.getpid()), encoding="utf-8")


def _pid_alive(pid: int) -> bool | None:
    """Whether ``pid`` runs; ``None`` where that cannot be asked safely (Windows)."""
    if os.name != "posix":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _run_finished(d: Path) -> bool:
    """A run is finished when it says so, or when the process that ran it is gone."""
    if (d / RUN_DONE_MARKER).exists():
        return True
    try:
        pid = int((d / RUN_LIVE_MARKER).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False  # no marker we can read: not ours to judge
    return pid != os.getpid() and _pid_alive(pid) is False


def _finish_run(work_dir: Path) -> None:
    """Mark this run done and remove every OTHER finished run — promptly, not
    after hours: each run holds a whole render's PNGs (an#243 review, R2-2).
    This run is kept, as the latest, for inspection; a run still in progress
    (its process alive, no done marker) is never touched."""
    (work_dir / RUN_DONE_MARKER).write_text("", encoding="utf-8")
    runs = work_dir.parent
    for d in runs.iterdir() if runs.is_dir() else ():
        if d == work_dir or not d.is_dir():
            continue
        if _run_finished(d):
            shutil.rmtree(d, ignore_errors=True)


# Default cap so a 20-shot scene doesn't try to spawn 20 Chromiums; the user
# can always pass a higher number explicitly.
DEFAULT_PARALLEL_CAP: int = 4


class RenderError(RuntimeError):
    """Raised on render-pipeline failures with actionable detail."""


def _scene_has_pending_dialogue(scene) -> bool:
    """Return True if any dialogue line lacks a viseme_track or timing."""
    for shot in scene.timeline:
        for line in shot.dialogue:
            if line.viseme_track is None or line.duration is None:
                return True
    return False


def _has_any_audio_content(scene) -> bool:
    """True if any shot carries something the audio pipeline should look at.

    Narration counts even though the pipeline cannot synthesise it yet, and that
    is the point: this predicate is the ONLY thing that decides whether
    ``produce_audio_for_scene`` is called at all, so gating it on dialogue alone
    made the narration guard unreachable for exactly the scenes it names — a
    narration-only project skipped the pipeline entirely and rendered a silent
    mp4 with no diagnostic anywhere.
    """
    return any(shot.dialogue or shot.narration for shot in scene.timeline)


def render_project(
    project_dir: str | Path,
    *,
    output_name: str = "main",
    fps: int | None = None,
    resolution: tuple[int, int] | None = None,
    tts: str | object = "offline",
    lipsync: str | object = "offline",
    parallel: int | str | None = None,
    strict_assets: bool = False,
    supersample: int = DEFAULT_SUPERSAMPLE,
    pix_fmt: str | None = None,
    capture: str | None = None,
    step_hz: float | None = None,
    language: str = "en",
    incremental: bool | IncrementalEngine = True,
    force_render: bool = False,
) -> Path:
    """Render every shot in ``project_dir``'s scene and concatenate to one mp4.

    **Incremental by default** (ADR 0004): a shot whose key — a digest of
    everything its render reads, never its id — already has an entry in the
    project's shot cache is not rendered again; its cached mp4 is reused. So
    editing one shot re-renders that shot, and an unchanged project re-renders
    nothing. ``force_render=True`` renders every shot anyway (and refreshes
    their entries); ``incremental=False`` neither reads nor writes the cache.
    Pass your own engine (e.g. ``ShotCache()``) to read what happened to each
    shot afterwards from its ``report`` — the same summary is logged on the
    ``an.build`` logger. See :func:`render`.

    ``tts`` and ``lipsync`` may be provider name strings (``"offline"``,
    ``"elevenlabs"``, ``"rhubarb"``) or provider instances. Defaults are
    offline so no API keys are required. Switching providers triggers a
    re-synthesis on dialogue lines whose stamped audio_ref / viseme_ref
    no longer match the current configuration.

    ``parallel`` controls per-shot concurrency:

    - ``None`` or ``1`` (default): render shots serially.
    - ``"auto"``: ``min(n_shots, cpu_count(), DEFAULT_PARALLEL_CAP)``.
    - integer ≥ 2: cap the thread pool at that size.

    Each shot's renderer runs in its own thread (the cutout backend
    spawns a Chromium + http.server per shot, so threads release the
    GIL during the slow parts).

    ``supersample`` renders at N times the declared resolution and resolves back
    with an exact block mean. **Opt-in, and 1 is free** — at 1 nothing is
    decoded and Chromium's own bytes reach disk. See :func:`render`.

    ``capture`` picks how frames leave the browser: ``"canvas"`` (the default,
    via ``None``, since an#192) — an in-page read of the canvas, batched,
    writing frames whose decoded pixels equal the screenshot path's and
    measured ~7.8x faster in the frame stage on the golden corpus, ~2.3x at
    1080p (see `an.adapters.cutout.canvas_capture`) — or ``"screenshot"``, a
    Playwright element screenshot per instant.

    ``step_hz`` overrides the scene's ``meta.step_hz`` for this render (a shot's
    own ``step_hz`` still wins): authored tweens are resampled onto a pose grid
    of that many updates per second — 15 at 30 fps is "on twos". ``None`` uses
    the scene's declaration, which is itself ``None`` (smooth) by default.

    ``language`` (BCP-47) reaches lip-sync providers that select behaviour by
    it when ``lipsync`` is a provider *name* — Rhubarb's recognizer (an#96). A
    provider *instance* carries its own.

    Returns the absolute path of the final output file (under ``output/``).
    """
    project: Project = load(project_dir)
    return render(
        project,
        output_name=output_name,
        fps=fps,
        resolution=resolution,
        tts=tts,
        lipsync=lipsync,
        parallel=parallel,
        strict_assets=strict_assets,
        supersample=supersample,
        pix_fmt=pix_fmt,
        capture=capture,
        step_hz=step_hz,
        language=language,
        incremental=incremental,
        force_render=force_render,
    )


def render(
    project: Project,
    *,
    output_name: str = "main",
    fps: int | None = None,
    resolution: tuple[int, int] | None = None,
    auto_audio: bool = True,
    tts: str | object = "offline",
    lipsync: str | object = "offline",
    parallel: int | str | None = None,
    strict_assets: bool = False,
    supersample: int = DEFAULT_SUPERSAMPLE,
    pix_fmt: str | None = None,
    capture: str | None = None,
    step_hz: float | None = None,
    language: str = "en",
    incremental: bool | IncrementalEngine = False,
    force_render: bool = False,
) -> Path:
    """Lower-level: render a loaded ``Project`` to mp4.

    ``incremental`` is the build-cache seam (ADR 0004 decision 5): ``True`` is
    the built-in :class:`~an.build.ShotCache` over ``mall["shot_cache"]``, an
    :class:`~an.build.IncrementalEngine` is used as given, and ``False`` — the
    default HERE, unlike :func:`render_project` — renders every shot cold, as
    this function always has. Cold is this layer's default because its other
    callers are measurements (the bench, the golden corpus, the demo builds),
    whose wall times and lever rebinds a reused shot would silently void.
    ``force_render=True`` with an engine renders every shot and re-records it.

    ``supersample`` renders at N times the declared resolution and resolves back
    with an exact N x N block mean, in the frame stage, before anything else
    reads the frames. **Opt-in, and 1 costs nothing**: at 1 Chromium writes
    straight to disk and no pixel is decoded.

    **Measured on the shipped path, not on the render alone** — the distinction
    matters, because the two differ by 1.6x. `single_character` forced to
    1920x1080, 60 frames, this machine:

    ========  =============  ==========
    factor    ms/frame       vs k=1
    ========  =============  ==========
    1         125.5          1.00x
    2         508.6          **4.05x**
    ========  =============  ==========

    `misc/docs/wave3_research.md` §3b reports 2.54x for k=2; that is the
    **render only**, measured with a patched runtime and no Python-side resolve,
    and quoting it here would understate what a caller pays by 1.6x. The
    difference is the decode + block mean + re-encode per frame.

    **What it buys, and where it does not.** Research §3a renders each corpus
    scene at rising k and lets `edge_transition_width` converge: k=2 travels 57%
    to 112% of the way to that ceiling, and k=3 reaches it on every scene that
    has one, at twice k=2's cost. `promote_demo` — the descriptor path — is the
    scene it helps most (-34.8% edge width, because the SVG sprite rasterises AT
    2x instead of being stretched up from a 1x texture). `aa_probe` has no
    ceiling at all: its diagonals land the block-mean grid differently at every
    k, so it oscillates +/-5-8% with no settling.

    **The corpus cannot inform the factor and must not be used to.** At 320x240
    the same ladder reads 1.0x / 1.08x, because fixed costs dominate.

    When ``auto_audio`` is True (the default) and any shot has dialogue,
    the audio pipeline is run first so visemes + audio are available to
    the renderer. Re-synthesis is triggered on provider changes (the
    pipeline's idempotency check compares against the current providers'
    expected content hashes).

    ``strict_assets=True`` refuses to draw a stand-in for a declared asset the
    stores do not supply — the placeholder rig for a missing character
    descriptor, the default backdrop for an unknown environment ref. Use it for
    anything that measures pixels: a stand-in renders happily and is a
    different picture (an#33).
    """
    scene = project.scene
    if not scene.timeline:
        raise RenderError("scene has no shots to render")

    if auto_audio and _has_any_audio_content(scene):
        # Lazy import to keep render.py importable without audio extras.
        from an.audio.pipeline import produce_audio_for_scene
        from an.audio.providers import make_lipsync, make_tts

        tts_provider = make_tts(tts) if isinstance(tts, str) else tts
        lipsync_provider = (
            make_lipsync(lipsync, language=language)
            if isinstance(lipsync, str)
            else lipsync
        )

        produce_audio_for_scene(
            scene,
            project.mall,
            tts=tts_provider,
            lipsync=lipsync_provider,
        )
        # Persist the now-stamped scene back to disk so subsequent loads see it.
        project.mall["scenes"]["main"] = scene
    else:
        # No synthesis, but a pause edited since the last one must still play
        # where it now says, not at the stale stamp (an#187). In memory only.
        from an.audio.pipeline import retime_dialogue

        retime_dialogue(scene, timed_shots_only=True)

    engine = resolve_incremental(incremental)
    work_dir = project.root / ".an" / "render_work"
    if engine is not None:
        # A cached render works in a directory of its OWN: two renders of one
        # project at once (a 4:4:4 master and a 4:2:0 delivery, a person and an
        # agent) would otherwise write the same `shot_<id>/<id>.mp4` and each
        # record whatever bytes were there under its own key — poisoning the
        # cache durably, where before it spoiled one run (an#243 review, S1).
        work_dir = work_dir / RENDER_RUNS_DIR / _run_id()
        _start_run(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    effective_fps = fps if fps is not None else scene.meta.fps or DEFAULT_FPS
    effective_res = (
        resolution
        if resolution is not None
        else (
            scene.meta.resolution.width or DEFAULT_RESOLUTION[0],
            scene.meta.resolution.height or DEFAULT_RESOLUTION[1],
        )
    )

    ctx = RenderContext(
        mall=project.mall,
        work_dir=work_dir,
        fps=effective_fps,
        resolution=effective_res,
        strict_assets=strict_assets,
        supersample=supersample,
        pix_fmt=pix_fmt,
        capture=capture,
        step_hz=step_hz if step_hz is not None else scene.meta.step_hz,
        # Resolved here, once, so a missing pack fails before the first browser
        # launch rather than per shot — and so every shot in a scene is drawn
        # under the same art direction by construction.
        style_pack=style_pack_for(scene.meta, project.mall.get("styles") or {}),
        default_easing=scene.meta.default_easing,
    )

    shots = list(scene.timeline)
    if needs_assembly(scene, fps=effective_fps):
        # Before any browser launches: a transition the shots are too short
        # for is microseconds to find and minutes of rendering to discover.
        film_timeline(shots, fps=effective_fps)
    pool_size = _resolve_parallel(parallel, n_shots=len(shots))

    # Captions (an#175): ONE page list, from which the burned-in picture and
    # the sidecar are both derived, so they cannot disagree. Built before any
    # browser launches, so a strict-captions refusal costs nothing.
    captions = scene.meta.captions
    pages = []
    if captions is not None:
        from an.captions import caption_pages

        pages = caption_pages(scene, fps=effective_fps, captions=captions)

    # Resolve renderers up front so a missing one fails fast (before we spawn
    # workers).
    shot_renderers = []
    for i, shot in enumerate(shots):
        r = _DEFAULT_REGISTRY.find_for(shot)
        if r is None:
            raise RenderError(
                f"no renderer registered for shot {shot.id!r} "
                f"(renderer={shot.renderer!r}); registered: "
                f"{list(_DEFAULT_REGISTRY.names())}"
            )
        shot_ctx = ctx
        if captions is not None and captions.burn:
            shot, shot_ctx = _burn_captions(
                shot, i, pages, captions, ctx, project, fps=effective_fps
            )
        shot_renderers.append((shot, r, shot_ctx))

    # The shot cache (ADR 0004): every key is computed HERE, in this thread and
    # before any browser launches — a key compiles its shot, so a shot that
    # cannot compile fails now, and only the misses reach the pool.
    plans: list[ShotPlan | None] = [None] * len(shot_renderers)
    if engine is not None:
        engine.begin(project.mall, project_root=project.root)
        needs_frames = needs_assembly(scene, fps=effective_fps)
        plans = [
            engine.plan(
                shot, renderer, shot_ctx, needs_frames=needs_frames, force=force_render
            )
            for shot, renderer, shot_ctx in shot_renderers
        ]

    shot_results: list[RenderResult | None] = [None] * len(shot_renderers)
    todo = []
    for i, ((shot, renderer, shot_ctx), plan) in enumerate(zip(shot_renderers, plans)):
        if plan is not None and plan.cached is not None:
            shot_results[i] = plan.cached
            _archive_shot(project, shot, plan.cached)
        else:
            todo.append((i, shot, renderer, shot_ctx, plan))

    if pool_size <= 1:
        for i, shot, renderer, shot_ctx, plan in todo:
            shot_results[i] = _render_one(
                shot, renderer, shot_ctx, project, engine=engine, plan=plan
            )
    else:
        with ThreadPoolExecutor(max_workers=pool_size) as ex:
            futures = {
                ex.submit(
                    _render_one,
                    shot,
                    renderer,
                    shot_ctx,
                    project,
                    engine=engine,
                    plan=plan,
                ): i
                for i, shot, renderer, shot_ctx, plan in todo
            }
            for fut in as_completed(futures):
                shot_results[futures[fut]] = fut.result()
    # Scene-timeline order is kept by index, for the concat.

    if engine is not None:
        report = engine.finish()
        logger.info("%s", report.summary())

    # Concatenate per-shot mp4s.
    output_path = (project.root / "output" / f"{output_name}.mp4").resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if needs_assembly(scene, fps=effective_fps):
        # Transitions and/or a sound layer: composed in the frame stage and
        # mixed from sources (`an.assemble`). A scene with neither never
        # reaches this branch, so its delivered file is the concat's, byte
        # for byte. Captions do not send a scene here (an#200): since each
        # shot's audio is cut to its picture (an#195), the concat puts frame
        # i at i/fps — the caption sidecar's grid — whether or not the shots
        # are whole frames long, offset only by the AAC priming every concat
        # carries.
        assemble_film(
            scene,
            shot_results,
            output_path,
            fps=effective_fps,
            mall=project.mall,
            work_dir=work_dir,
            pix_fmt=pix_fmt,
        )
    else:
        _ffmpeg_concat([r.mp4_path for r in shot_results], output_path)

    # Also write to the output store for parity with other artifacts.
    with open(output_path, "rb") as f:
        project.mall["output"][output_name] = f.read()

    _write_caption_sidecar(
        project.mall, output_name, scene, captions, pages, fps=effective_fps
    )
    if engine is not None:
        _finish_run(work_dir)
    # Last, so it is the last word about the file (an#211): a render that used
    # all-rights-reserved, private-study material must not read as shippable.
    import warnings

    from an.credits import CreditsWarning, credits_for_scene, warn_if_private_study

    try:
        report = credits_for_scene(project.mall, scene)
    except Exception as e:  # noqa: BLE001 — never fail a finished render
        warnings.warn(
            f"{output_path} was rendered, but its credits could not be checked "
            f"({type(e).__name__}: {e}); run `an credits` before sharing it.",
            CreditsWarning,
            stacklevel=2,
        )
    else:
        warn_if_private_study(report, output=output_path)
    return output_path


def _write_caption_sidecar(mall, output_name, scene, captions, pages, *, fps):
    """Write ``output/<name>.srt`` from ``pages`` — or REMOVE a stale one.

    A player loads a sidecar that sits beside the mp4 by name, so a file left
    from an earlier captioned render would be shown over a film it no longer
    describes; this render's answer replaces it either way.
    """
    import warnings

    from an.captions import CaptionWarning

    store = mall.get("captions")
    if store is None:
        return
    if captions is None:
        # Not ours to delete: the scene never asked for captions, so a file
        # there may be the author's own. Said, because a player will load it.
        if output_name in store:
            warnings.warn(
                f"a caption sidecar for {output_name!r} sits beside the mp4 but "
                "the scene has no `captions`; it was NOT written by this render",
                CaptionWarning,
                stacklevel=3,
            )
        return
    if not captions.sidecar or not pages:
        if captions.sidecar:
            warnings.warn(
                "captions are on but no line could be captioned; no sidecar written",
                CaptionWarning,
                stacklevel=3,
            )
        store.pop(output_name, None)
        return
    # Beside the mp4, under the same key (`output/main.srt`), in FILM time on
    # the timeline the picture was just laid out on.
    from an.captions import srt_for_scene

    srt = srt_for_scene(scene, fps=fps, pages=pages)
    store[output_name] = srt.encode("utf-8")


def _burn_captions(shot, index, pages, captions, ctx, project, *, fps):
    """``shot`` with its caption pages added, and the context to render it in."""
    import dataclasses
    import warnings

    from an.captions import CaptionWarning, captioned_shot

    if not any(p.shot == index for p in pages):
        return shot, ctx
    if shot.renderer != "cutout":
        warnings.warn(
            f"shot {shot.id!r} is drawn by the {shot.renderer!r} renderer, which "
            "has no overlay layer: its captions are in the sidecar only",
            CaptionWarning,
            stacklevel=3,
        )
        return shot, ctx
    shot, mall = captioned_shot(
        shot,
        pages,
        captions,
        fps=fps,
        mall=ctx.mall,
        shot_index=index,
        base_dir=project.root,
        resolution=tuple(ctx.resolution),
    )
    return shot, dataclasses.replace(ctx, mall=mall)


def _render_one(
    shot: Shot,
    renderer,
    ctx: RenderContext,
    project: Project,
    *,
    engine: IncrementalEngine | None = None,
    plan: ShotPlan | None = None,
) -> RenderResult:
    """Render one shot, record it with ``engine``, and archive its mp4.

    Each call is self-contained: the cutout renderer creates a per-shot
    work directory, its own Chromium instance, its own http server. This
    is what makes the call thread-safe.
    """
    t0 = time.perf_counter()
    result = renderer.render(shot, ctx)
    render_s = time.perf_counter() - t0
    if engine is not None and plan is not None:
        engine.record(plan, result, render_s=render_s)
    _archive_shot(project, shot, result)
    return result


def _archive_shot(project: Project, shot: Shot, result: RenderResult) -> None:
    """Write the shot's mp4 to ``mall["shots"][shot.id]`` — an ARCHIVE, not a cache.

    Keyed by the author's id, so it holds the latest render of each shot for a
    person to look at; nothing reads it back (pillar 11). The cache is
    ``mall["shot_cache"]``, keyed by content.
    """
    with open(result.mp4_path, "rb") as f:
        project.mall["shots"][shot.id] = f.read()


def _resolve_parallel(parallel: int | str | None, *, n_shots: int) -> int:
    """Resolve ``parallel`` to an integer worker count.

    >>> _resolve_parallel(None, n_shots=5)
    1
    >>> _resolve_parallel(1, n_shots=5)
    1
    >>> _resolve_parallel(3, n_shots=5)
    3
    >>> _resolve_parallel(8, n_shots=2)  # capped to n_shots
    2
    """
    if parallel is None or parallel == 1 or parallel == 0 or parallel == "":
        return 1
    if parallel == "auto":
        cap = DEFAULT_PARALLEL_CAP
        cpu = os.cpu_count() or 1
        return max(1, min(n_shots, cpu, cap))
    try:
        n = int(parallel)
    except (TypeError, ValueError):
        return 1
    return max(1, min(n, n_shots))


# -----------------------------------------------------------------------------
# ffmpeg concat
# -----------------------------------------------------------------------------


def _ffmpeg_concat(inputs: Iterable[Path], output: Path) -> None:
    """Concatenate mp4 files using ffmpeg's concat demuxer."""
    if shutil.which("ffmpeg") is None:
        raise RenderError(
            "ffmpeg not found on PATH. Install with: brew install ffmpeg "
            "(macOS) or apt install ffmpeg (Linux)."
        )
    inputs = list(inputs)
    if len(inputs) == 1:
        # Single shot: just copy. This branch can therefore fix nothing about
        # the container -- it is sound only because the per-shot mp4 is
        # already faststart (`_ffmpeg_add_audio`), which is why the flag has
        # to be on the shot mux and not only on the concat below. Five of the
        # six bench corpus scenes take this path (only `multi_shot` has two
        # shots), so a concat-only fix would leave the corpus untouched.
        shutil.copy(inputs[0], output)
        return

    # Build a concat list file: ffmpeg's concat demuxer wants a `file '<path>'\n` list.
    list_path = output.with_suffix(".concat.txt")
    list_path.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in inputs) + "\n",
        encoding="utf-8",
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        # an#57's open question, answered by experiment on ffmpeg 8.1
        # (Homebrew, macOS arm64): `-f concat -c copy -movflags +faststart`
        # is a REMUX, not a transcode. The concatenated elementary stream is
        # sha256-identical to the two inputs' streams appended
        # (a4be46f7...218e == cat a.h264 b.h264), the video packet total is
        # unchanged, the decoded YUV is sha256-identical, the file size is
        # unchanged (moov is the same 1062 bytes, it just moves), and the
        # wall time is the same 0.02 s. So it does not create the double
        # encode epic #9 wrongly describes.
        *MP4_FASTSTART_ARGS,
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output.exists():
        raise RenderError(
            f"ffmpeg concat failed (rc={result.returncode}):\n{result.stderr}"
        )
    list_path.unlink(missing_ok=True)
