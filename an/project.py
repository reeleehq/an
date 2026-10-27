"""Project init/load/save — the on-disk anatomy of an an project.

Layout (from spec §11):

    my-scene/
    ├── an.toml
    ├── scene.md
    ├── ir/scene.json
    ├── assets/{characters,props,environments,voices,styles,sounds}/
    ├── artifacts/{audio,visemes,shots,previews}/
    ├── output/
    └── .an/{decisions.jsonl,verifier_runs/,memory.md}
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from an.base import DEFAULT_FPS, DEFAULT_RESOLUTION
from an.ir.schema import Meta, Resolution, SceneIR
from an.ir.sync import (
    DEFAULT_SCENE_FILE,
    SceneFile,
    ir_to_markdown,
    read_scene,
    resolve_scene_file,
    sync as sync_files,
)
from an.stores import build_project_mall
from an.util import _read_text, _write_json, _write_text


#: Seeded by :func:`init` and read by nothing — ``load`` never opens it, and
#: there is no ``tomllib`` anywhere in the package (see
#: ``tests/test_bench_corpus.py::test_no_corpus_fixture_ships_an_an_toml``). It
#: is documentation of the project layout that happens to be valid TOML.
#:
#: The providers therefore have to match the DEFAULTS, not an aspiration. They
#: used to say ``tts = "elevenlabs"``: inert today, but the only place in the
#: repo stating a paid provider as a project default, in the file a user opens
#: to learn what the defaults are. The day somebody wires config reading — the
#: natural next step for a file that exists and is documented — every project
#: ever created by ``an init`` would begin defaulting to a billed provider,
#: entirely outside :mod:`an.live_api`, which only the example consults. an#63
#: is about exactly that shape, so the template says what `render` does.
_ANIMA_TOML_TEMPLATE = """# an project config
[project]
name = "{name}"
default_renderer = "cutout"

[render]
fps = {fps}
resolution = [{width}, {height}]

# Nothing reads this section yet; it mirrors the defaults `an render` uses.
# A paid provider belongs here only behind an explicit opt-in — see an.live_api.
[providers]
# "voice": each voice document's own `provider` speaks its lines; a voice that
# names none is spoken by the offline (silent) provider.
tts = "voice"
lipsync = "offline"
"""


@dataclass(slots=True)
class Project:
    """A loaded an project: directory + mall + current scene."""

    root: Path
    mall: Mapping[str, MutableMapping]
    scene: SceneIR


def _age_the_seed(*paths: Path) -> None:
    """Date the seed files back past `sync`'s mtime tolerance.

    `sync` treats two files less than ``SYNC_MTIME_TOLERANCE_S`` apart as the
    same age and rewrites neither. A ``scene.md`` written right after ``an
    init`` — by a script, or an agent — was therefore ignored: the empty seed
    ``scene.json`` stayed the scene, and ``an validate`` reported "no shots"
    for a file full of them. A seed holds nothing worth preferring over any
    edit, so it is made old enough that the first edit always wins.
    """
    import os
    import time

    from an.ir.sync import SYNC_MTIME_TOLERANCE_S

    then = time.time() - 4 * SYNC_MTIME_TOLERANCE_S
    for p in paths:
        os.utime(p, (then, then))


#: A render report records what a render on THIS machine found — warnings,
#: exception text — so it is per-machine output, not project source (an#254).
RENDER_REPORTS_GITIGNORE: tuple[str, ...] = ("artifacts/render_reports/",)
#: Probe frames and contact sheets (``an probe``, ``an library sheet``,
#: an#347): looks at work in progress, which may show private-study material.
PROBES_GITIGNORE: tuple[str, ...] = ("artifacts/probes/",)
#: The file locks an options manifest's writers take (``<ref>.json.lock``,
#: an#587): empty, per machine, never project source.
LOCKS_GITIGNORE: tuple[str, ...] = ("artifacts/voice_options/*.lock",)
#: What a project's ``.gitignore`` keeps out of version control (``an init``
#: adds each line a ``.gitignore`` lacks, never removing one).
PROJECT_GITIGNORE: tuple[str, ...] = (
    RENDER_REPORTS_GITIGNORE + PROBES_GITIGNORE + LOCKS_GITIGNORE
)


def _ensure_gitignored(pdir: Path, lines: tuple[str, ...]) -> None:
    """Append to ``pdir/.gitignore`` each of ``lines`` it does not already hold,
    in the file's own line endings (a CRLF file stays CRLF)."""
    path = pdir / ".gitignore"
    data = path.read_bytes() if path.exists() else b""
    text = data.decode("utf-8")
    present = {line.strip() for line in text.splitlines()}
    missing = [line for line in lines if line not in present]
    if not missing:
        return
    eol = "\r\n" if "\r\n" in text else "\n"
    if text and not text.endswith(("\n", "\r")):
        text += eol
    path.write_bytes(
        (text + "".join(f"{line}{eol}" for line in missing)).encode("utf-8")
    )


def keep_out_of_git(pdir: Path, lines: tuple[str, ...]) -> None:
    """Add ``lines`` to an OLDER project's ``.gitignore`` (an ``an init`` from
    before they existed left them out) — conservatively: never a line whose
    folder the file already says anything about (a project may have chosen to
    commit its reports, ``!artifacts/render_reports/``), never through a
    symlink (a shared ignore file), and never creating a ``.gitignore`` in a
    project that is not in a git work tree."""
    path = pdir / ".gitignore"
    if path.is_symlink():
        return
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = tuple(
            line for line in lines if line.rstrip("/").rsplit("/", 1)[-1] not in text
        )
    elif not any((d / ".git").exists() for d in (pdir, *pdir.parents)):
        return
    if lines:
        _ensure_gitignored(pdir, lines)


def keep_reports_out_of_git(pdir: Path) -> None:
    """Add :data:`RENDER_REPORTS_GITIGNORE` to an older project's ``.gitignore``
    the first time a render writes a report (an#309), by :func:`keep_out_of_git`'s rules."""
    keep_out_of_git(pdir, RENDER_REPORTS_GITIGNORE)


def init(
    project_dir: str | Path, *, name: str | None = None, force: bool = False
) -> Path:
    """Create a fresh an project at ``project_dir``.

    Idempotent unless the directory already contains a non-empty ``scene.md``;
    pass ``force=True`` to overwrite. Returns the absolute project root. The
    project's ``.gitignore`` gains :data:`PROJECT_GITIGNORE` (lines it lacks).
    """
    pdir = Path(project_dir).expanduser().resolve()
    proj_name = name or pdir.name
    # The default scene's pair, as every command resolves it (an#554).
    seed = resolve_scene_file(pdir, must_exist=False)

    if seed.md_path.exists() and not force:
        if seed.md_path.stat().st_size > 0:
            raise FileExistsError(
                f"{seed.md_path} already exists with content; pass force=True to overwrite"
            )

    pdir.mkdir(parents=True, exist_ok=True)

    # Build the mall to materialize the directory tree.
    build_project_mall(pdir, ensure=True)

    # Seed scene.md with an empty SceneIR-equivalent.
    seed_scene = SceneIR(
        meta=Meta(
            title=proj_name,
            fps=DEFAULT_FPS,
            resolution=Resolution(
                width=DEFAULT_RESOLUTION[0], height=DEFAULT_RESOLUTION[1]
            ),
        )
    )
    _write_text(seed.md_path, ir_to_markdown(seed_scene))
    _write_json(seed.json_path, json.loads(seed_scene.model_dump_json()))
    _age_the_seed(seed.md_path, seed.json_path)

    # Seed an.toml.
    toml_path = pdir / "an.toml"
    if not toml_path.exists() or force:
        toml_path.write_text(
            _ANIMA_TOML_TEMPLATE.format(
                name=proj_name,
                fps=DEFAULT_FPS,
                width=DEFAULT_RESOLUTION[0],
                height=DEFAULT_RESOLUTION[1],
            ),
            encoding="utf-8",
        )

    _ensure_gitignored(pdir, PROJECT_GITIGNORE)

    # Touch the agent-memory file so it's discoverable.
    memory_path = pdir / ".an" / "memory.md"
    if not memory_path.exists():
        memory_path.write_text(
            f"# Agent memory for {proj_name}\n\n"
            "Append running notes here across sessions.\n",
            encoding="utf-8",
        )

    return pdir


def load(
    project_dir: str | Path,
    *,
    check_kinds: bool = True,
    scene_file: str | Path | SceneFile = DEFAULT_SCENE_FILE,
    sync: bool = True,
) -> Project:
    """Load an existing project. Reconciles scene.md / ir/scene.json first
    (unless ``sync=False``).

    ``sync=False`` is the read-only load (an#573): the scene is read past a
    stale pair with :func:`an.ir.sync.read_scene` and nothing is written to the
    scene files; ``project.mall["scenes"]`` is then a read-only view of that
    scene. For commands that only look (``an cache info``, ``an cache gc``, ``credits``,
    ``world show``). ``an validate`` keeps syncing: it reports the sync's own
    warnings (a tie that disagrees) as findings, which this path does not emit.

    ``scene_file`` names another scene of the project (``scene.studio.md``, its
    JSON twin ``ir/scene.studio.json``, an#539; resolved by
    :func:`an.ir.sync.resolve_scene_file`, so a bad or missing one raises
    :class:`~an.ir.sync.SceneFileError`); the assets are the project's.

    Registers the installed genres first (:func:`an.genres.load`, ADR 0001
    decision 3: discovery is explicit, and loading a project is one of the
    places it happens), so the scene's genre kinds — the cut-out genre's
    ``play``, ``expression`` and ``character`` — read as their own models.

    Then refuses a scene that names an action kind, entity kind or renderer
    nothing registered (:func:`an.ir.validate.require_registered_kinds`): the
    schema holds those as ``str`` (ADR 0001 decision 2), so without this a
    typo'd ``kind: enviroment`` would load and render silently without its
    backdrop. ``check_kinds=False`` is for ``an validate``, which reports them
    as findings instead.
    """
    from an.genres import load as load_genres

    load_genres()
    pdir = Path(project_dir).expanduser().resolve()
    if not pdir.exists():
        raise FileNotFoundError(f"no such project directory: {pdir}")

    # Sync md ↔ json so the loaded scene reflects the latest Markdown.
    scene_file = resolve_scene_file(pdir, scene_file)
    if sync:
        sync_files(pdir, scene_file)
        mall = build_project_mall(pdir, ensure=True, scene_file=scene_file)
        scene = mall["scenes"]["main"]
    else:
        scene = read_scene(pdir, scene_file)
        mall = build_project_mall(
            pdir, scene_file=scene_file, scenes=MappingProxyType({"main": scene})
        )
    if check_kinds:
        from an.ir.validate import require_registered_kinds

        require_registered_kinds(scene, where=str(pdir))
    return Project(root=pdir, mall=mall, scene=scene)


def save(project: Project) -> None:
    """Persist a Project's current scene back to disk (md + json)."""
    project.mall["scenes"]["main"] = project.scene
