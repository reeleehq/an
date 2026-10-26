"""Project init / load / save smoke tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from an import init, load, save
from an.ir.schema import Meta, SceneIR, Shot
from an.ir.sync import SceneFileError, resolve_scene_file


def test_init_creates_full_layout():
    with tempfile.TemporaryDirectory() as d:
        root = init(Path(d) / "demo")
        for sub in (
            "scene.md",
            "ir/scene.json",
            "an.toml",
            "assets/characters",
            "assets/props",
            "assets/environments",
            "assets/voices",
            "assets/styles",
            "assets/sounds",
            "artifacts/audio",
            "artifacts/visemes",
            "artifacts/shots",
            "artifacts/previews",
            "output",
            ".an",
            ".an/memory.md",
        ):
            assert (root / sub).exists(), f"missing {sub}"


def test_init_idempotent_when_empty():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "demo"
        init(root)
        # Replacing scene.md with empty content should let init succeed again.
        (root / "scene.md").write_text("", encoding="utf-8")
        init(root)  # no error


def test_init_refuses_to_clobber():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "demo"
        init(root)
        # scene.md now has content; init without force should refuse.
        with pytest.raises(FileExistsError):
            init(root)


def test_init_force_overwrites():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "demo"
        init(root, name="orig")
        init(root, name="new", force=True)
        assert "new" in (root / "an.toml").read_text(encoding="utf-8")


def test_load_returns_project_with_mall_and_scene():
    with tempfile.TemporaryDirectory() as d:
        root = init(Path(d) / "demo")
        proj = load(root)
        assert proj.root == root
        assert "scenes" in proj.mall
        assert proj.scene.kind == "SceneIR"


def test_save_persists_scene_changes():
    with tempfile.TemporaryDirectory() as d:
        root = init(Path(d) / "demo")
        proj = load(root)
        proj.scene = SceneIR(
            meta=Meta(title="changed", duration=2.0),
            timeline=[Shot(id="s1", duration=2.0)],
        )
        save(proj)
        proj2 = load(root)
        assert proj2.scene.meta.title == "changed"


def test_a_project_keeps_several_scenes_side_by_side(tmp_path):
    """an#539: `scene_file` picks a scene.<name>.md and its ir/scene.<name>.json;
    the default scene is untouched, and writes through the mall go to the pair."""
    from an.orchestrate import validate_project

    root = init(tmp_path / "demo")
    studio = "# Studio\n\n```yaml meta\ntitle: Studio\nduration: 3\nfps: 24\n```\n\n## Shot s1 (cutout)\n\n```yaml shot\nduration: 3\n```\n"
    (root / "scene.studio.md").write_text(studio, encoding="utf-8")

    project = load(root, scene_file="scene.studio.md")
    assert [s.id for s in project.scene.timeline] == ["s1"]
    assert (root / "ir" / "scene.studio.json").exists()
    assert load(root).scene.timeline == []  # the default scene is another document

    project.scene.timeline[0].duration = 4.0
    save(project)
    assert "duration: 4" in (root / "scene.studio.md").read_text(encoding="utf-8")
    assert "duration: 4" not in (root / "scene.md").read_text(encoding="utf-8")

    assert validate_project(root, scene_file="scene.studio.md").passed
    for bad in ("nope.md", "sub/scene.md", "scene.txt"):
        report = validate_project(root, scene_file=bad)
        assert not report.passed and bad in report.findings[0].ir_path
    with pytest.raises(SceneFileError, match="no scene file"):
        load(root, scene_file="nope.md")


def test_a_scene_file_is_resolved_the_way_it_was_typed(tmp_path, monkeypatch):
    """an#539 review: a path into the project is accepted however it is spelled
    (relative to the shell, absolute, with `..`); `Scene.md` is refused (did you mean scene.md)
    scene on a case-insensitive disk; a backslash, a sub-folder and a stem of
    `main` (the default scene's output) are refused."""
    root = init(tmp_path / "demo")
    (root / "scene.x.md").write_text("# X\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    spellings = (
        "scene.x.md",
        "demo/scene.x.md",
        str(root / "scene.x.md"),
        str(root / ".." / "demo" / "scene.x.md"),
    )
    for spelled in spellings:
        sf = resolve_scene_file(root, spelled)
        assert (sf.name, sf.json_path.name, sf.output_name) == (
            "scene.x.md", "scene.x.json", "scene.x"
        ), spelled
    monkeypatch.chdir(root)
    assert resolve_scene_file(".", "./scene.x.md").name == "scene.x.md"

    with pytest.raises(SceneFileError, match="did you mean scene.md"):
        resolve_scene_file(root, "Scene.md")
    with pytest.raises(SceneFileError, match="file stem"):
        resolve_scene_file(root, "scene.x.md", must_exist=False).output_for("sub/x")
    for bad in ("sub\\scene.x.md", "sub/scene.x.md", "scene.txt", ".hidden.md"):
        with pytest.raises(SceneFileError, match="directly inside"):
            resolve_scene_file(root, bad, must_exist=False)
    with pytest.raises(SceneFileError, match="rename the file"):
        resolve_scene_file(root, "main.md", must_exist=False)
    with pytest.raises(SceneFileError, match="no scene file"):
        resolve_scene_file(root, "scene.y.md")
    # The default scene missing is not an error: a new project has none yet.
    (root / "scene.md").unlink()
    assert resolve_scene_file(root).md_path == root / "scene.md"


def test_sync_refuses_a_scene_file_that_is_not_there(tmp_path):
    """`an sync <dir> --scene typo.md` used to report "no changes"."""
    from an import tools
    from an.ir.sync import sync

    root = init(tmp_path / "demo")
    with pytest.raises(SceneFileError, match="no scene file 'typo.md'"):
        sync(root, "typo.md")
    with pytest.raises(SceneFileError, match="no scene file 'typo.md'"):
        tools.sync(str(root), scene="typo.md")
    assert not (root / "ir" / "typo.json").exists()
