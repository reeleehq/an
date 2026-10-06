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
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from an.adapters._base import RenderContext, RenderResult
from an.assemble import (
    ShotParts,
    assemble_film,
    film_timeline,
    needs_assembly,
    shot_parts,
    shot_windows,
)
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
    tts: str | object | None = None,
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
    echo_warnings: bool = True,
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
    ``"elevenlabs"``, ``"rhubarb"``) or provider instances. **``tts`` defaults
    to each voice's own provider** (an#305): a line whose voice document
    declares ``provider: elevenlabs`` is spoken by ElevenLabs — its cost
    announced before the first request, a cached line never billed — and a
    voice that declares none by the offline provider, so a project that
    declares no provider needs no API key and renders exactly as before. A
    ``tts`` given overrides every voice; a line spoken by another provider than
    its voice declares (``--tts offline`` for an ElevenLabs voice: silence) is a
    finding, and refused under ``strict_assets``. ``lipsync`` defaults to
    offline. Switching providers triggers a re-synthesis on dialogue lines whose
    stamped audio_ref / viseme_ref no longer match the current configuration.

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
    1080p (see `an.stage.canvas_capture`) — or ``"screenshot"``, a
    Playwright element screenshot per instant.

    ``step_hz`` overrides the scene's ``meta.step_hz`` for this render (a shot's
    own ``step_hz`` still wins): authored tweens are resampled onto a pose grid
    of that many updates per second — 15 at 30 fps is "on twos". ``None`` uses
    the scene's declaration, which is itself ``None`` (smooth) by default.

    ``language`` (BCP-47) reaches lip-sync providers that select behaviour by
    it when ``lipsync`` is a provider *name* — Rhubarb's recognizer (an#96). A
    provider *instance* carries its own.

    A scene whose ``library:`` pins disagree with the project's
    ``assets.lock.json`` renders with a ``LibraryPinWarning`` per pin, and is
    refused under ``strict_assets`` (:func:`an.library.checkout.check_pins_before_render`).

    **What the render learned is reported** (an#254): see :func:`render` — every
    finding is in ``render_reports/<output_name>.json``, read back as
    ``Finding`` s by :func:`render_findings`, and summarised by ``an render``.

    Returns the absolute path of the final output file (under ``output/``).
    """
    project: Project = load(project_dir)
    if any(e.library for shot in project.scene.timeline for e in shot.entities):
        # The asset library's pins (an#240): the scene's `library:` must say what
        # assets.lock.json says the project holds — a warning, fatal under
        # --strict-assets. Imported only for a scene that pins anything.
        from an.library.checkout import check_pins_before_render

        caught: list = []
        with _recording_warnings(caught):
            check_pins_before_render(
                project.scene, project.mall.get("library_lock"), strict=strict_assets
            )
        # The render's report holds them too (`_pin_findings`): `an render`
        # lists them in its summary instead of as they happen.
        _echo(caught, all_of_them=echo_warnings)
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
        echo_warnings=echo_warnings,
    )


def render(
    project: Project,
    *,
    output_name: str = "main",
    fps: int | None = None,
    resolution: tuple[int, int] | None = None,
    auto_audio: bool = True,
    tts: str | object | None = None,
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
    echo_warnings: bool = True,
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

    **What the render learns, it reports** (an#254). Render is when a line's
    real length becomes known, so after synthesis the checks ``an validate``
    could only estimate run again on the timing the film will mux — the SAME
    functions (:func:`an.ir.validate.post_synthesis_findings`): a line past its
    shot's end, a speaker overlapping themself, a line heard during a dissolve.
    With them go the clock-owning renderers' findings (an#279), the scene's
    library pins that disagree with ``assets.lock.json``, and every warning
    raised while the film was made — a stand-in or a recorded substitution, a
    take whose audio is not the one recorded, a caption without word timings —
    each addressed to its shot when its message names one. All of it is written
    to ``render_reports/<output_name>.json`` (``kind`` says which check),
    readable as ``Finding`` s with :func:`render_findings`;
    :func:`format_render_findings` is ``an render``'s grouped summary of it.
    The warnings are still warned, after the render (``echo_warnings=False``:
    only reported — what ``an render`` passes, since it prints the summary; a
    render that fails echoes them anyway). What ``strict_assets`` refuses is
    refused where it is found, before a frame is drawn; nothing here is fatal.
    """
    scene = project.scene
    if not scene.timeline:
        raise RenderError("scene has no shots to render")
    caught: list = []
    ok = False
    try:
        with _recording_warnings(caught):
            output_path, report_scene, findings, fps_used = _render_film(
                project,
                output_name=output_name,
                fps=fps,
                resolution=resolution,
                auto_audio=auto_audio,
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
            ok = True
    finally:
        _echo(caught, all_of_them=echo_warnings or not ok)
    findings = [*findings, *_warning_findings(caught, report_scene)]
    findings += _post_synthesis(project, report_scene, fps=fps_used)
    _write_render_report(project.mall, output_name, findings, root=project.root)
    # Last, so it is the last word about the file (an#211): a render that used
    # all-rights-reserved, private-study material must not read as shippable.
    import warnings

    from an.credits import CreditsWarning, credits_for_scene, warn_if_private_study

    try:
        report = credits_for_scene(project.mall, report_scene)
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


def _render_film(
    project: Project,
    *,
    output_name: str,
    fps,
    resolution,
    auto_audio: bool,
    tts,
    lipsync,
    parallel,
    strict_assets: bool,
    supersample: int,
    pix_fmt,
    capture,
    step_hz,
    language: str,
    incremental,
    force_render: bool,
):
    """:func:`render`'s work: ``(output_path, settled scene, findings, fps)``,
    the findings being the ones that arrive as ``Finding`` s (measurements and
    library pins) under their kinds."""
    scene = project.scene
    findings: list[tuple[str, object]] = _pin_findings(project)

    if auto_audio and _has_any_audio_content(scene):
        # Lazy import to keep render.py importable without audio extras.
        from an.audio.pipeline import produce_audio_for_scene
        from an.audio.providers import make_lipsync

        lipsync_provider = (
            make_lipsync(lipsync, language=language)
            if isinstance(lipsync, str)
            else lipsync
        )

        produce_audio_for_scene(
            scene,
            project.mall,
            # A name, an instance, or None: each voice's own provider (an#305).
            tts=tts,
            lipsync=lipsync_provider,
            # Reported with every other post-synthesis finding, below (an#254).
            overruns=False,
            # A voice spoken by another provider than it declares is a stand-in.
            strict=strict_assets,
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

    prep = _prepare_shots(
        project,
        work_dir,
        fps=fps,
        resolution=resolution,
        strict_assets=strict_assets,
        supersample=supersample,
        pix_fmt=pix_fmt,
        capture=capture,
        step_hz=step_hz,
        measure=True,
        force_measure=force_render or engine is None,
    )
    # The SETTLED scene from here on: a clock-owning renderer's measured shot
    # lengths (an#279) reach the timeline, captions, the mix and every key.
    scene, shot_findings = prep.scene, prep.findings
    effective_fps, shots, shot_renderers = prep.fps, prep.shots, prep.shot_renderers
    captions, pages, windows = prep.captions, prep.pages, prep.windows
    pool_size = _resolve_parallel(parallel, n_shots=len(shots))

    # The shot cache (ADR 0004): every key is computed HERE, in this thread and
    # before any browser launches — a key compiles its shot, so a shot that
    # cannot compile fails now, and only the misses reach the pool.
    plans: list[ShotPlan | None] = [None] * len(shot_renderers)
    if engine is not None:
        engine.begin(project.mall, project_root=project.root)
        # An assembled film needs each shot's mp4 and, where a transition
        # touches it, its window's parts (an#260) — never all of its frames.
        plans = [
            engine.plan(
                shot,
                renderer,
                shot_ctx,
                window=windows[i] if windows is not None else None,
                force=force_render,
            )
            for i, (shot, renderer, shot_ctx) in enumerate(shot_renderers)
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

    parts = None
    if windows is not None:
        parts = _film_parts(
            windows, shot_results, plans, engine, work_dir, fps=effective_fps,
            pix_fmt=pix_fmt,
        )  # fmt: skip

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
            parts=parts,
        )
    else:
        _ffmpeg_concat([r.mp4_path for r in shot_results], output_path)

    # Also write to the output store for parity with other artifacts.
    with open(output_path, "rb") as f:
        project.mall["output"][output_name] = f.read()

    _write_caption_sidecar(
        project.mall, output_name, scene, captions, pages, fps=effective_fps
    )
    record_root = getattr(engine, "record_root", None)
    if callable(record_root):
        # What this render used, for `an cache gc` (an#274): the knobs AS
        # PASSED, so a later collection recomputes the current scene's keys
        # under them (None stays "the scene's own").
        record_root(
            output_name,
            profile=dict(
                fps=fps, resolution=resolution, strict_assets=strict_assets,
                supersample=supersample, pix_fmt=pix_fmt, capture=capture,
                step_hz=step_hz, tts=_tts_name(tts),
                lipsync=_provider_name(lipsync), language=language,
            ),
            output=output_path,
        )  # fmt: skip
    if engine is not None:
        _finish_run(work_dir)
    findings += [("measurement", f) for f in shot_findings]
    return output_path, scene, findings, effective_fps


def _write_render_report(mall, output_name: str, findings, *, root=None) -> None:
    """``render_reports/<output_name>.json``: what this render found, for
    ``orchestrate``, MCP and ``an render``'s summary to read (an#279, an#254).
    ``findings`` are ``(kind, Finding)`` pairs; each record is the ``Finding``'s
    fields plus its ``kind``, every text field made portable
    (:func:`portable_text`: no machine's absolute paths in a file a project
    may share). Always written — an empty report replaces a stale one — when
    the mall has the store."""
    import json

    from an.measurements import findings_record

    store = mall.get("render_reports")
    if store is None:
        return
    if root is not None:  # a project from before an#254 gets the line too
        from an.project import keep_reports_out_of_git

        try:
            keep_reports_out_of_git(Path(root))
        except (OSError, UnicodeDecodeError):
            pass  # a read-only project still gets its report
    records = findings_record(findings, text=lambda v: portable_text(v, root=root))
    store[output_name] = json.dumps(
        {"findings": records}, indent=2, sort_keys=True
    ).encode("utf-8")


#: What a temp-folder path becomes in a portable text (:func:`portable_text`).
TMP_TOKEN: str = "<tmp>"

#: After a path prefix, what may NOT follow for it to be the whole of a path
#: component: another name character, or a dot that starts an extension. So
#: ``/u/me/p`` is not a prefix of ``/u/me/proj2`` or ``/u/me/p-old``, but a
#: sentence may end with ``/u/me/p.``
_COMPONENT_END = r"(?![\w\-]|\.\w)"
#: Before a path prefix: the start of the text or of a word, or a URL's
#: ``file://`` — never the middle of another path (``/mnt/data/p`` is not
#: ``/data/p``) or of a name.
_PATH_START = r"(?:^|(?<=[^\w.\-~/\\])|(?<=://))"
#: The temp folders every POSIX machine has, besides the one Python reports.
POSIX_TEMP_DIRS: tuple[str, ...] = ("/tmp", "/private/tmp", "/var/tmp")


def _spellings(path: str, *, resolve: bool) -> list[str]:
    """``path`` as text may name it: as given, resolved, and on macOS with and
    without ``/private`` (``/private/var`` is ``/var``)."""
    out = [path]
    if resolve:
        try:
            out.append(str(Path(path).resolve()))
        except OSError:
            pass
    out += [p[len("/private") :] for p in list(out) if p.startswith("/private/")]
    return [p.rstrip("/\\") for p in dict.fromkeys(out) if p.rstrip("/\\")]


def _prefix_pattern(prefix: str) -> str:
    """A regex for ``prefix`` that matches either separator where it has one
    (``C:\\Users\\me`` is also ``C:/Users/me``)."""
    return "".join("[/\\\\]" if c in "/\\" else re.escape(c) for c in prefix)


def portable_text(text: str, *, root=None, home=None, tmp=None) -> str:
    """``text`` with this machine's absolute paths taken out: a path under the
    project ``root`` becomes project-relative, the root itself ``.``, a temp
    folder ``<tmp>`` and the home directory ``~`` — so a render report (which a
    project may commit or share, and an agent may pass on) names no user, host
    folder or temp dir. Only WHOLE path components are replaced, at both ends
    (an#309): a sibling that shares a prefix (``/u/me/proj2`` beside
    ``/u/me/p``) or a path that merely ends like one (``/mnt/data/p`` against
    ``/data/p``) is left as it is. A Windows path matches with either
    separator and in any case.

    >>> portable_text("missing at /u/me/p/assets/a.png; see /u/me/x.log",
    ...               root="/u/me/p", home="/u/me", tmp="/t")
    'missing at assets/a.png; see ~/x.log'
    >>> portable_text("rendered in /u/me/p", root="/u/me/p", home="/u/me", tmp="/t")
    'rendered in .'
    >>> portable_text("/u/me/proj2/a.png, /u/me2/x, /t/f.png, /mnt/u/me/p/b",
    ...               root="/u/me/p", home="/u/me", tmp="/t")
    '~/proj2/a.png, /u/me2/x, <tmp>/f.png, /mnt/u/me/p/b'
    >>> portable_text("c:/users/me/p/a.png", root=r"C:\\Users\\me\\p", home=r"C:\\Users\\me", tmp="/t")
    'a.png'
    """
    import tempfile

    explicit = home is not None
    roots = _spellings(str(root), resolve=not explicit) if root is not None else []
    tmps = [
        p
        for t in (
            (tmp,) if tmp is not None else (tempfile.gettempdir(), *POSIX_TEMP_DIRS)
        )
        for p in _spellings(str(t), resolve=tmp is None)
    ]
    homes = _spellings(str(home) if explicit else str(Path.home()), resolve=False)

    def swap(text: str, prefixes: list[str], child: str, whole: str) -> str:
        for prefix in sorted(set(prefixes), key=len, reverse=True):
            if len(prefix) <= 1:
                continue  # never "/" itself
            flags = re.IGNORECASE if re.match(r"^[A-Za-z]:", prefix) else 0
            head = _PATH_START + _prefix_pattern(prefix)
            text = re.sub(head + r"[/\\]+", lambda _m: child, text, flags=flags)
            text = re.sub(head + _COMPONENT_END, lambda _m: whole, text, flags=flags)
        return text

    text = swap(text, roots, "", ".")  # a root may sit in the temp folder or home
    text = swap(text, tmps, TMP_TOKEN + "/", TMP_TOKEN)
    return swap(text, homes, "~/", "~")


#: How ``an render``'s summary heads each ``kind`` of finding, in this order; a
#: kind not listed (another warning category) is headed by its own name, after.
FINDING_GROUPS: dict[str, str] = {
    "VoiceStandInWarning": "voices spoken by another provider than they declare",
    "dialogue_fits": "dialogue that does not fit its shot",
    "dialogue_in_dissolve": "dialogue heard during a dissolve",
    "measurement": "shots whose renderer measured their length",
    "library_pins": "library pins that disagree with assets.lock.json",
    "CutoutCompileWarning": "stand-ins, substitutions and compile notes",
    "CutoutAssetWarning": "art that could not be staged",
    "TakeDigestWarning": "takes whose audio is not the recorded one",
    "CaptionTimingWarning": "captions without word timings",
    "ShotCacheWarning": "the shot cache",
}
#: At most this many findings of one kind are listed in the summary.
SUMMARY_MAX_PER_GROUP: int = 5


def render_findings(project, output_name: str = "main") -> list:
    """The ``Finding`` s the last render of ``output_name`` reported (an#254),
    from ``render_reports/<output_name>.json``; ``[]`` before any render.

    ``project`` is a project directory, a loaded ``Project`` or its mall.
    """
    from an.verify._base import Finding

    fields = ("severity", "ir_path", "description", "suggested_fix", "location")
    return [
        Finding(**{k: r.get(k) for k in fields})
        for r in _report_records(project, output_name)
    ]


def _report_records(project, output_name: str) -> list[dict]:
    import json
    from collections.abc import Mapping

    if isinstance(project, Project):
        mall = project.mall
    elif isinstance(project, Mapping):
        mall = project
    elif Path(project).is_dir():
        from an.stores import build_project_mall

        mall = build_project_mall(project)
    else:
        return []  # no project there: nothing rendered (and nothing created)
    store = mall.get("render_reports")
    if store is None or output_name not in store:
        return []
    return list(json.loads(store[output_name]).get("findings", []))


def format_render_findings(
    project, output_name: str = "main", *, max_per_group: int = SUMMARY_MAX_PER_GROUP
) -> list[str]:
    """``an render``'s summary of what the render found: one heading per kind
    (:data:`FINDING_GROUPS`) with its count, then each finding's IR path and
    message — the message carries its fix — at most ``max_per_group`` per kind.
    ``info`` findings are counted in the report, not listed. ``[]`` when the
    render found nothing to warn about.

    >>> recs = {"findings": [{"severity": "warning", "ir_path": "timeline/0/dialogue/1",
    ...     "description": "line 1 (bob) ends at 3.64s as synthesized, past the shot's "
    ...     "3.6s end. Lengthen the shot", "suggested_fix": None, "location": None,
    ...     "kind": "dialogue_fits"}]}
    >>> import json
    >>> print("\\n".join(format_render_findings(
    ...     {"render_reports": {"main": json.dumps(recs)}})))
    findings: 1 warning (all in artifacts/render_reports/main.json)
      dialogue that does not fit its shot (1):
        timeline/0/dialogue/1: line 1 (bob) ends at 3.64s as synthesized, past the shot's 3.6s end. Lengthen the shot
    """
    records = [
        r for r in _report_records(project, output_name) if r.get("severity") != "info"
    ]
    if not records:
        return []
    order = list(FINDING_GROUPS)
    kinds = sorted(
        {r.get("kind") or "" for r in records},
        key=lambda k: (order.index(k) if k in order else len(order), k),
    )
    errors = sum(r.get("severity") == "error" for r in records)
    warns = len(records) - errors
    counts = ", ".join(
        f"{n} {word}{'s' if n != 1 else ''}"
        for n, word in ((errors, "error"), (warns, "warning"))
        if n
    )
    lines = [f"findings: {counts} (all in artifacts/render_reports/{output_name}.json)"]
    for kind in kinds:
        group = [r for r in records if (r.get("kind") or "") == kind]
        lines.append(f"  {FINDING_GROUPS.get(kind, kind or 'other')} ({len(group)}):")
        for r in group[:max_per_group]:
            where = f" ({r['location']})" if r.get("location") else ""
            fix = f" Fix: {r['suggested_fix']}" if r.get("suggested_fix") else ""
            text = f"{r['description']}{fix}".replace("\n", "\n      ")
            lines.append(f"    {r['ir_path']}{where}: {text}")
        if len(group) > max_per_group:
            lines.append(f"    ... and {len(group) - max_per_group} more")
    return lines


def _pin_findings(project: Project) -> list[tuple[str, object]]:
    """The scene's ``library:`` pins that disagree with ``assets.lock.json`` —
    :func:`an.library.checkout.check_pins`, the function ``render_project``
    warns (and, strict, refuses) with — for the report."""
    lock = project.mall.get("library_lock")
    scene = project.scene
    if lock is None or not any(
        e.library for shot in scene.timeline for e in shot.entities
    ):
        return []
    from an.library.checkout import check_pins

    return [("library_pins", f) for f in check_pins(scene, {k: lock[k] for k in lock})]


def _post_synthesis(project: Project, scene, *, fps) -> list[tuple[str, object]]:
    """``an validate``'s post-synthesis checks on the timing just muxed
    (:func:`an.ir.validate.post_synthesis_findings`), as ``Finding`` s. A check
    that cannot run is a finding itself — never a failed render."""
    from an.ir.validate import post_synthesis_findings
    from an.verify._base import Finding

    try:
        mall = project.mall
        found = post_synthesis_findings(
            scene,
            fps=fps,
            available_voices=mall.get("voices"),
            available_characters=mall.get("characters"),
            available_props=mall.get("props"),
            available_environments=mall.get("environments"),
        )
    except Exception as e:  # noqa: BLE001 — the film is made; say what is unknown
        return [
            (
                "post_synthesis",
                Finding(
                    "warning",
                    "timeline",
                    f"the post-synthesis checks could not run ({type(e).__name__}: "
                    f"{e}); run `an validate` on this project",
                ),
            )
        ]
    return [
        (kind, Finding(f.severity, f.ir_path, f.description, location=f.location))
        for kind, f in found
    ]


@contextmanager
def _recording_warnings(into: list):
    """Record every warning raised inside (worker threads included: the warning
    machinery is process-wide) into ``into`` — kept even when the body raises.
    The filters in force are kept, so an ``error`` filter still raises where
    the warning is raised, and an ``ignore`` still ignores."""
    import warnings

    with warnings.catch_warnings(record=True) as log:
        try:
            yield
        finally:
            into.extend(log)


def _is_an_warning(w) -> bool:
    """Whether ``w`` is ``an``'s own — its category is defined in ``an``, or it
    was raised from ``an``'s code (another library's is only echoed)."""
    if (getattr(w.category, "__module__", "") or "").split(".")[0] == "an":
        return True
    try:
        return Path(w.filename).resolve().is_relative_to(_AN_ROOT)
    except (OSError, ValueError, TypeError):
        return False


_AN_ROOT: Path = Path(__file__).resolve().parent


def _already_findings(w) -> bool:
    """A warning that restates a finding the report holds as one already."""
    from an.measurements import ShotFindingWarning

    return issubclass(w.category, ShotFindingWarning) or (
        w.category.__name__ == "LibraryPinWarning"
    )


def _unique(caught: list) -> list:
    seen: set = set()
    out = []
    for w in caught:
        key = (w.category, str(w.message))
        if key not in seen:
            seen.add(key)
            out.append(w)
    return out


def _echo(caught: list, *, all_of_them: bool = True) -> None:
    """Warn again what was recorded, at its own file and line. ``all_of_them=False``
    echoes only what the report does not carry (another library's warning)."""
    import warnings

    for w in _unique(caught):
        if all_of_them or not _is_an_warning(w):
            warnings.warn_explicit(
                w.message, w.category, w.filename, w.lineno, source=w.source
            )


_SHOT_NAMED = re.compile(r"""\bshot ['"]([^'"]+)['"]""")


def _warning_findings(caught: list, scene) -> list[tuple[str, object]]:
    """``(kind, Finding)`` per distinct warning ``an`` raised while making the
    film, its kind the warning's category, addressed to the shot its message
    names (``shot 's2' …``), else to the timeline. The message's first
    paragraph is kept: the rest is the explanation ``an`` prints when warning."""
    from an.verify._base import Finding

    index = {}
    for i, shot in enumerate(getattr(scene, "timeline", None) or []):
        index.setdefault(shot.id, i)
    out = []
    for w in _unique(caught):
        if not _is_an_warning(w) or _already_findings(w):
            continue
        text = str(w.message).split("\n\n", 1)[0].strip()
        named = _SHOT_NAMED.search(text)
        path = (
            f"timeline/{index[named.group(1)]}"
            if named and named.group(1) in index
            else "timeline"
        )
        out.append((w.category.__name__, Finding("warning", path, text)))
    return out


def _style_pack(scene, project: Project):
    """The scene's `StylePack`, resolved by the stage (which owns what a pack
    draws); imported here, at call time, so the core never imports the stage."""
    if not getattr(scene.meta, "style_pack", None):
        return None
    from an.stage.compile import style_pack_for

    return style_pack_for(scene.meta, project.mall.get("styles") or {})


@dataclass
class _PreparedShots:
    """Everything the render loop knows before the first shot renders."""

    ctx: RenderContext
    fps: float
    shots: list
    shot_renderers: list
    captions: object
    pages: list
    windows: tuple | None
    scene: object = None
    findings: list = field(default_factory=list)


def _prepare_shots(
    project: Project,
    work_dir: Path,
    *,
    fps,
    resolution,
    strict_assets,
    supersample,
    pix_fmt,
    capture,
    step_hz,
    measure: bool = False,
    force_measure: bool = False,
) -> _PreparedShots:
    """The render context and each shot's renderer, as :func:`render` uses them.

    One function, so :func:`cache_entries` (what the garbage collector keeps)
    sees the shots exactly as a render would — settled shot lengths, burned
    captions, style pack, resolved knobs, film windows and all.

    A renderer that owns its clock (Manim) says how long its shots run
    (an#279): the measurement is applied to an in-memory COPY of the scene
    before anything reads ``shot.duration`` — the film timeline, captions, the
    sound layer, every cache key — and never written into the author's scene.
    ``measure=True`` (a render) measures what is not stored, ``force_measure``
    everything afresh; ``measure=False`` (the collector) reads stored
    measurements only, so a collection never runs a renderer.
    """
    scene = project.scene
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
        style_pack=_style_pack(scene, project),
        default_easing=scene.meta.default_easing,
    )

    from an.measurements import settle_durations, warn_findings

    scene, findings = settle_durations(
        scene, ctx, render=measure, force=force_measure, strict=strict_assets
    )
    if measure:
        warn_findings(findings)

    shots = list(scene.timeline)
    windows = None
    if needs_assembly(scene, fps=effective_fps):
        # Before any browser launches: a transition the shots are too short
        # for is microseconds to find and minutes of rendering to discover.
        # What the film needs from each shot (an#260) is known now too.
        windows = shot_windows(film_timeline(shots, fps=effective_fps))
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

    return _PreparedShots(
        ctx=ctx,
        fps=effective_fps,
        shots=shots,
        shot_renderers=shot_renderers,
        captions=captions,
        pages=pages,
        windows=windows,
        scene=scene,
        findings=findings,
    )


def _provider_name(provider) -> str | None:
    """A provider as a root records it: its factory name, or ``None`` for an
    instance (which a collector cannot rebuild; that render's root still
    protects what it used)."""
    return provider if isinstance(provider, str) else None


def _tts_name(tts) -> str | None:
    """The ``tts`` a root records: :func:`_provider_name`, and ``"voice"``
    (:data:`an.audio.pipeline.VOICE_TTS`) for each voice's own provider (an#305)."""
    from an.audio.pipeline import VOICE_TTS, is_voice_tts

    return VOICE_TTS if is_voice_tts(tts) else _provider_name(tts)


def _film_parts(windows, shot_results, plans, engine, work_dir, *, fps, pix_fmt):
    """Each shot's `ShotParts` for an assembled film: a reused shot's from the
    cache, a rendered shot's built from its frames once and recorded."""
    record_parts = getattr(engine, "record_parts", None)
    parts: list[ShotParts | None] = []
    for i, (window, result, plan) in enumerate(zip(windows, shot_results, plans)):
        if window.whole:
            parts.append(None)
        elif plan is not None and plan.parts is not None:
            parts.append(plan.parts)
        else:
            built = shot_parts(
                result.frame_manifest, window, fps=fps, pix_fmt=pix_fmt,
                work_dir=Path(work_dir) / "film" / "parts" / f"{i:03d}",
            )  # fmt: skip
            if callable(record_parts) and plan is not None:
                record_parts(plan, built)
            parts.append(built)
    return parts


def cache_reach(
    project: Project,
    engine: IncrementalEngine,
    *,
    fps: int | None = None,
    resolution: tuple[int, int] | None = None,
    strict_assets: bool = False,
    supersample: int = DEFAULT_SUPERSAMPLE,
    pix_fmt: str | None = None,
    capture: str | None = None,
    step_hz: float | None = None,
    tts: str | object | None = None,
    lipsync: str | object = "offline",
    language: str = "en",
) -> CacheReach:
    """What a render of ``project``'s CURRENT scene under these knobs would
    read — the shot-cache entry ids, and the record-store entries of the
    renderers' derived stores (a Manim shot's measurement record, which names
    its picture and contact sheet: :mod:`an.build.derived`, an#299) — computed
    by the render's own setup and the engine's own key code, rendering and
    synthesising nothing.

    What `an.build.gc` keeps (an#274). The dialogue is stamped the way the
    render's audio pipeline stamps it, from the content-keyed audio and viseme
    stores only (`an.audio.pipeline.stamp_from_stores`): a ``scene.md`` edit
    drops every stamp on re-sync, and the next render re-stamps the same audio
    from the stores, so those are the keys it will use. A line the stores
    cannot answer whose provider is free and repeatable (offline speech) is
    re-made IN MEMORY, writing nothing (an#311): a later render re-makes the
    same bytes. Any other (new text in a billed voice, a non-repeatable
    provider) raises `an.audio.pipeline.AudioNotCachedError`: its shot's next
    key is unknowable without a paid or random synthesis, and a collector must
    not guess.
    """
    from an.audio.pipeline import (
        InMemoryOverlay,
        in_memory_audio_mall,
        retime_dialogue,
        stamp_from_stores,
    )
    from an.build.derived import derived_stores_for

    scene = project.scene
    if _has_any_audio_content(scene):
        from dataclasses import replace

        from an.audio.providers import make_lipsync

        # Free, repeatable speech missing from the stores is re-made in memory
        # (an#311) and the keys below read it from there; no store is written.
        # A caller keying several knob sets passes one overlaid mall for all.
        if not isinstance(project.mall.get("audio"), InMemoryOverlay):
            project = replace(project, mall=in_memory_audio_mall(project.mall))
        stamp_from_stores(
            scene,
            project.mall,
            tts=tts,  # None: each voice's own provider, as the render (an#305)
            lipsync=(
                make_lipsync(lipsync, language=language)
                if isinstance(lipsync, str)
                else lipsync
            ),
            free_in_memory=True,
        )
    else:
        retime_dialogue(scene, timed_shots_only=True)
    prep = _prepare_shots(
        project,
        project.root / ".an" / "render_work",  # nothing is written
        fps=fps,
        resolution=resolution,
        strict_assets=strict_assets,
        supersample=supersample,
        pix_fmt=pix_fmt,
        capture=capture,
        step_hz=step_hz,
    )
    engine.begin(project.mall, project_root=project.root)
    reach = CacheReach()
    for i, (shot, renderer, shot_ctx) in enumerate(prep.shot_renderers):
        window = prep.windows[i] if prep.windows is not None else None
        reach.ids.extend(engine.entry_ids(shot, renderer, shot_ctx, window=window))
        spec = derived_stores_for(getattr(renderer, "name", "") or "")
        if spec is not None:
            reach.derived.setdefault(spec.record_store, set()).update(
                spec.entries(renderer, shot, shot_ctx)
            )
    return reach


@dataclass
class CacheReach:
    """:func:`cache_reach`'s answer: shot-cache ids, and derived-store entries
    by store name."""

    ids: list[str] = field(default_factory=list)
    derived: dict[str, set[str]] = field(default_factory=dict)


def cache_entries(project: Project, engine: IncrementalEngine, **knobs) -> list[str]:
    """The shot-cache entry ids of :func:`cache_reach` (what `an.build.gc`
    keeps of the shot cache, an#274)."""
    return cache_reach(project, engine, **knobs).ids


#: Where a run's process cannot be asked whether it lives (Windows), a run
#: unfinished after this long is taken for one that crashed: otherwise it would
#: shield every cache entry written since, from `an cache gc`, for ever.
UNKNOWN_LIVENESS_MAX_S: float = 24 * 3600.0


def live_runs(project_root: Path) -> list[tuple[Path, float]]:
    """Every cached render of this project still in progress, with the time it
    started (its live marker's mtime): what `an cache gc` must not race."""
    runs = Path(project_root) / ".an" / "render_work" / RENDER_RUNS_DIR
    out: list[tuple[Path, float]] = []
    for d in sorted(runs.iterdir()) if runs.is_dir() else ():
        marker = d / RUN_LIVE_MARKER
        if not (d.is_dir() and marker.exists()) or _run_finished(d):
            continue
        try:
            started = marker.stat().st_mtime
            pid = int(marker.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):  # finished and removed while we looked
            continue
        if _pid_alive(pid) is None and time.time() - started > UNKNOWN_LIVENESS_MAX_S:
            continue
        out.append((d, started))
    return out


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
    from an.stage import STAGE_RENDERER_NAMES  # the stage has the overlay layer

    if shot.renderer not in STAGE_RENDERER_NAMES:
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
