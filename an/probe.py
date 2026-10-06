"""``an probe``: a shot's frame at chosen instants, through the very path ``render`` draws it (an#347).

Looking at one moment of a shot used to mean a whole render, or a throwaway
script that staged the scene its own way and drew something else. A probe
prepares the shot exactly as :func:`an.render.render` does (``_prepare_shots``:
settled length, burned captions, the style pack, the resolved knobs), then asks
the shot's own renderer for the frames showing at the instants given:

- a frame-stage renderer (the stage engine, the cut-out renderer) opens the
  session ``render`` opens and captures through
  :func:`an.engines.capture.capture_frames` — supersample, frame clock and
  canvas readback included — only the frames asked for
  (:meth:`an.engines.frame_stage.FrameStageRenderer.probe_frames`);
- a renderer that owns its clock (Manim) serves the frames from the picture a
  render stored, or refuses with the remedy;
- any other renderer refuses: it has no ``probe_frames``.

Speech plays as the last render (or synthesis) stamped it: a probe never
synthesises a line. Nothing is cached, written to the shot cache or archived.

**Rights.** A frame showing material that is not publishable (``an credits``
for the shot says private or unknown) is refused at a path inside a git work
tree that does not ignore it; the default folder, ``artifacts/probes/``, is
ignored by ``an init`` and added to an older project's ``.gitignore``.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path

from an.project import PROBES_GITIGNORE, Project, keep_out_of_git, load

__all__ = ["ProbeError", "frame", "frames", "probe"]

#: Where a probe writes by default, inside the project (gitignored by ``an init``).
PROBE_DIR: str = "artifacts/probes"
#: The side of each cell when several instants are tiled into one grid.
PROBE_GRID_CELL: int = 480
#: The scratch folder a probe stages in, inside the project's ``.an``; removed after.
PROBE_WORK_DIR: str = "probe_work"


class ProbeError(RuntimeError):
    """A probe cannot draw what was asked: the message says why and what to do."""


def _project(project: Project | str | os.PathLike) -> Project:
    return project if isinstance(project, Project) else load(project)


def frames(
    project: Project | str | os.PathLike,
    shot: str,
    times: Sequence[float],
    *,
    supersample: int = 1,
) -> list[bytes]:
    """PNG bytes of shot ``shot``'s film frame at each of ``times`` (seconds into the shot).

    project: a loaded :class:`~an.project.Project` or its folder
    supersample: as ``an render --supersample`` (the frame is the film's only
        if it matches the render's)
    """
    from an.render import _prepare_shots

    project = _project(project)
    times = [float(t) for t in times]
    if not times:
        raise ProbeError("a probe needs at least one instant (--at <seconds>)")
    work = project.root / ".an" / PROBE_WORK_DIR / uuid.uuid4().hex[:12]
    work.mkdir(parents=True, exist_ok=True)
    try:
        prep = _prepare_shots(
            project,
            work,
            fps=None,
            resolution=None,
            strict_assets=False,
            supersample=supersample,
            pix_fmt=None,
            capture=None,
            step_hz=None,
            measure=False,  # a probe never runs a renderer to measure a shot
        )
        found = [(s, r, c) for s, r, c in prep.shot_renderers if s.id == shot]
        if not found:
            ids = [s.id for s, _, _ in prep.shot_renderers]
            raise ProbeError(f"the scene has no shot {shot!r}; its shots: {ids}")
        the_shot, renderer, ctx = found[0]
        late = [t for t in times if t < 0 or t > the_shot.duration]
        if late:
            raise ProbeError(
                f"shot {shot!r} runs {the_shot.duration:g} s; {late} is outside it"
            )
        probe_frames = getattr(renderer, "probe_frames", None)
        if probe_frames is None:
            raise ProbeError(
                f"the {getattr(renderer, 'name', type(renderer).__name__)!r} "
                f"renderer that draws shot {shot!r} cannot draw a single frame "
                "(it has no probe_frames); render the project instead"
            )
        return list(probe_frames(the_shot, ctx, times))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def frame(
    project: Project | str | os.PathLike, shot: str, t: float, **kwargs
) -> bytes:
    """PNG bytes of shot ``shot``'s film frame at ``t`` seconds (see :func:`frames`)."""
    return frames(project, shot, [t], **kwargs)[0]


def _shot_publishable(project: Project, shot: str) -> tuple[bool, list[str]]:
    """Whether everything shot ``shot`` draws or plays may ship, and what may not."""
    from an.credits import credits_for_scene

    scene = project.scene
    only = scene.model_copy(update={"timeline": [s for s in scene.timeline if s.id == shot]})
    report = credits_for_scene(project.mall, only)
    held = [
        f"{e.asset} ({e.license_class})"
        for e in report.entries
        if e.license_class in ("private", "unknown")
    ]
    return report.publishable, held


def probe(
    project_dir: str | os.PathLike,
    shot: str,
    at: Sequence[float],
    *,
    out: str | os.PathLike | None = None,
    columns: int | None = None,
    supersample: int = 1,
    allow_private_here: bool = False,
) -> Path:
    """Write shot ``shot``'s frames at ``at`` to one PNG (a grid for several instants).

    out: the PNG to write (default ``<project>/artifacts/probes/<shot>@<t>.png``)
    columns: cells per row of a grid (default: a square grid)
    allow_private_here: write not-publishable frames inside a git work tree
        that does not ignore the path
    """
    from an.library.root import check_private_output
    from an.media.grid import tile

    project = _project(project_dir)
    times = [float(t) for t in at]
    target = (
        Path(out)
        if out
        else project.root
        / PROBE_DIR
        / f"{shot}@{'+'.join(f'{t:g}' for t in times) or 'none'}.png"
    )
    if not out:
        keep_out_of_git(project.root, PROBES_GITIGNORE)
    publishable, held = _shot_publishable(project, shot)
    check_private_output(
        target,
        publishable=publishable,
        what=f"a probe of shot {shot!r} ({', '.join(held)})",
        allow=allow_private_here,
    )
    pngs = frames(project, shot, times, supersample=supersample)
    data = (
        pngs[0]
        if len(pngs) == 1
        else tile(
            pngs,
            cell=PROBE_GRID_CELL,
            columns=columns,
            labels=[f"{shot} @ {t:g} s" for t in times],
        )
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target
