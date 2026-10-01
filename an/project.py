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
from typing import Mapping

from an.base import DEFAULT_FPS, DEFAULT_RESOLUTION
from an.ir.schema import Meta, Resolution, SceneIR
from an.ir.sync import ir_to_markdown, sync as sync_files
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
tts = "offline"
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


def init(
    project_dir: str | Path, *, name: str | None = None, force: bool = False
) -> Path:
    """Create a fresh an project at ``project_dir``.

    Idempotent unless the directory already contains a non-empty ``scene.md``;
    pass ``force=True`` to overwrite. Returns the absolute project root.
    """
    pdir = Path(project_dir).expanduser().resolve()
    proj_name = name or pdir.name

    if pdir.exists() and (pdir / "scene.md").exists() and not force:
        if (pdir / "scene.md").stat().st_size > 0:
            raise FileExistsError(
                f"{pdir / 'scene.md'} already exists with content; pass force=True to overwrite"
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
    _write_text(pdir / "scene.md", ir_to_markdown(seed_scene))
    _write_json(pdir / "ir" / "scene.json", json.loads(seed_scene.model_dump_json()))
    _age_the_seed(pdir / "scene.md", pdir / "ir" / "scene.json")

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

    # Touch the agent-memory file so it's discoverable.
    memory_path = pdir / ".an" / "memory.md"
    if not memory_path.exists():
        memory_path.write_text(
            f"# Agent memory for {proj_name}\n\n"
            "Append running notes here across sessions.\n",
            encoding="utf-8",
        )

    return pdir


def load(project_dir: str | Path, *, check_kinds: bool = True) -> Project:
    """Load an existing project. Reconciles scene.md / ir/scene.json first.

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
    sync_files(pdir)

    mall = build_project_mall(pdir, ensure=True)
    scene = mall["scenes"]["main"]
    if check_kinds:
        from an.ir.validate import require_registered_kinds

        require_registered_kinds(scene, where=str(pdir))
    return Project(root=pdir, mall=mall, scene=scene)


def save(project: Project) -> None:
    """Persist a Project's current scene back to disk (md + json)."""
    project.mall["scenes"]["main"] = project.scene
