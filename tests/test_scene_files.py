"""Several scene files in one project, project-wide (an#554, follow-up of an#539).

`--scene <file>` reaches every command that reads a scene; two scenes that
share shot ids never write the same probe, preview or render work file; no
scene takes another's output name; `an cache gc` keeps what EVERY scene of the
project reaches.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from an import init, load
from an.ir.schema import Meta, Resolution, SceneIR, Shot
from an.ir.sync import (
    SceneFileError,
    project_scene_files,
    resolve_scene_file,
)
from an.stores import build_project_mall
from tests.test_shot_cache import fake_render  # noqa: F401 — the fixture, by name

_STUDIO = "# Studio\n\n```yaml meta\ntitle: Studio\nduration: 1\nfps: 12\n```\n\n## Shot s1 (cutout)\n\n```yaml shot\nduration: 1\n```\n"


def _two_scene_project(tmp_path) -> Path:
    root = init(tmp_path / "demo")
    (root / "scene.studio.md").write_text(_STUDIO, encoding="utf-8")
    return root


def _put_scene(root: Path, scene_file: str, scene: SceneIR) -> None:
    build_project_mall(root, ensure=True, scene_file=scene_file)["scenes"]["main"] = (
        scene
    )


# -----------------------------------------------------------------------------
# The resolver
# -----------------------------------------------------------------------------


def test_no_scene_takes_another_scenes_output_name(tmp_path):
    """`--scene scene.a.md --output-name scene.b` overwrote scene.b.md's film."""
    root = _two_scene_project(tmp_path)
    (root / "scene.b.md").write_text(_STUDIO, encoding="utf-8")
    studio = resolve_scene_file(root, "scene.studio.md")
    default = resolve_scene_file(root)
    for sf, taken in (
        (studio, "scene.b"),
        (studio, "SCENE.B"),
        (default, "scene.studio"),
    ):
        with pytest.raises(SceneFileError, match="other scene file"):
            sf.output_for(taken)
    # Its own stem, and a name no scene owns, are fine.
    assert studio.output_for("scene.studio") == "scene.studio"
    assert studio.output_for("final") == "final"
    assert default.output_for("main") == "main"


def test_the_render_leaf_refuses_another_scenes_output_before_any_work(
    monkeypatch, tmp_path
):
    from an import render as render_mod

    root = _two_scene_project(tmp_path)
    seen = []
    monkeypatch.setattr(render_mod, "render", lambda project, **kw: seen.append(kw))
    with pytest.raises(SceneFileError, match="scene.studio.md"):
        render_mod.render_project(root, output_name="scene.studio")
    assert seen == []


def test_a_resolved_scene_file_is_kept_not_resolved_again(tmp_path):
    root = _two_scene_project(tmp_path)
    sf = resolve_scene_file(root, "scene.studio.md")
    assert resolve_scene_file(root, sf) is sf
    assert resolve_scene_file(str(root) + "/.", sf) is sf  # however the dir is spelled
    (root / "scene.studio.md").unlink()
    with pytest.raises(SceneFileError, match="no scene file"):
        resolve_scene_file(root, sf)


def test_the_scenes_of_a_project_are_the_md_files_with_a_json_twin(tmp_path):
    root = _two_scene_project(tmp_path)
    (root / "README.md").write_text("# notes\n", encoding="utf-8")
    assert [sf.name for sf in project_scene_files(root)] == ["scene.md"]
    load(root, scene_file="scene.studio.md")  # writes ir/scene.studio.json
    assert [sf.name for sf in project_scene_files(root)] == [
        "scene.md",
        "scene.studio.md",
    ]


def test_init_seeds_the_resolvers_default_pair(tmp_path):
    root = init(tmp_path / "p")
    sf = resolve_scene_file(root)
    assert sf.md_path.exists() and sf.json_path.exists()


# -----------------------------------------------------------------------------
# Per-scene files
# -----------------------------------------------------------------------------


def _same_shot_in_two_scenes(tmp_path) -> Path:
    root = init(tmp_path / "p")
    for name, title in (("scene.md", "a"), ("scene.studio.md", "b")):
        _put_scene(
            root,
            name,
            SceneIR(
                meta=Meta(
                    title=title,
                    duration=1.0,
                    resolution=Resolution(width=320, height=240),
                ),
                timeline=[Shot(id="only", renderer="cutout", duration=1.0)],
            ),
        )
    return root


def test_probes_of_two_scenes_sharing_a_shot_id_do_not_overwrite(monkeypatch, tmp_path):
    import an.probe as probe_mod

    root = _same_shot_in_two_scenes(tmp_path)
    monkeypatch.setattr(
        probe_mod,
        "frames",
        lambda project, shot, times, **kw: [project.scene.meta.title.encode()],
    )
    monkeypatch.setattr(
        probe_mod, "_shot_publishable", lambda project, shot: (True, [])
    )
    a = probe_mod.probe(root, "only", [0.5])
    b = probe_mod.probe(root, "only", [0.5], scene_file="scene.studio.md")
    assert a == root / "artifacts" / "probes" / "only@0.5.png"  # unchanged
    assert (
        b == root / "artifacts" / "probes" / "scenes" / "scene.studio" / "only@0.5.png"
    )
    assert (a.read_bytes(), b.read_bytes()) == (b"a", b"b")


def test_previews_of_two_scenes_stage_apart(tmp_path):
    import json

    from an.stage.preview import _stage_preview

    root = _same_shot_in_two_scenes(tmp_path)
    a = _stage_preview(root)
    b = _stage_preview(root, scene_file="scene.studio.md")
    assert a.runtime_dir == root.resolve() / ".an" / "preview" / "runtime"  # unchanged
    assert b.runtime_dir == (
        root.resolve() / ".an" / "preview" / "scenes" / "scene.studio" / "runtime"
    )
    assert a.scene_json_path.exists() and b.scene_json_path.exists()
    json.loads(a.scene_json_path.read_text(encoding="utf-8"))  # not clobbered by b's


# -----------------------------------------------------------------------------
# --scene reaches every command that reads a scene
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["credits", "{root}"],
        ["iterate", "{root}", "shorter"],
        ["world", "show", "{root}"],
        ["voices", "rescore", "{root}", "hello"],
        ["voices", "reroll", "{root}", "hello"],
        ["voices", "design", "{root}", "--no-design"],
        ["voices", "audition", "{root}"],
        ["voices", "import", "{root}", "{wav}", "--license", "cc0-1.0"],
    ],
    ids=lambda argv: " ".join(a for a in argv if not a.startswith("{")),
)
def test_every_scene_reading_command_takes_scene(argv, tmp_path, monkeypatch):
    """A `--scene` that is not there is refused by the command's own load, as a
    line, not a traceback: the flag reached the leaf (an#554)."""
    from typer.testing import CliRunner

    from an.__main__ import build_app

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-used")  # iterate checks it first
    pytest.importorskip("anthropic") if argv[0] == "iterate" else None
    root = _two_scene_project(tmp_path)
    wav = tmp_path / "take.wav"
    wav.write_bytes(b"")
    args = [a.format(root=root, wav=wav) for a in argv] + ["--scene", "typo.md"]
    result = CliRunner().invoke(build_app(), args)
    assert result.exit_code == 1, result.output
    assert "no scene file 'typo.md'" in result.output, result.output
    assert "Traceback" not in result.output


def test_world_show_and_credits_read_the_scene_named(tmp_path):
    from an import tools
    from an.credits import credits_for_project
    from an.world_cli import show

    root = _two_scene_project(tmp_path)
    assert "no framed shot" in show(str(root), scene="scene.studio.md")
    assert credits_for_project(root, scene_file="scene.studio.md").entries == []
    assert isinstance(tools.credits(str(root), scene="scene.studio.md"), str)


def test_orchestrate_runs_on_the_scene_named(tmp_path):
    from an.orchestrate import orchestrate

    root = _two_scene_project(tmp_path)
    report = orchestrate(
        root, scene_file="scene.studio.md", skip_render=True, verifiers=[]
    )
    assert report.success is not False, report.error
    bad = orchestrate(
        root, scene_file="scene.studio.md", output_name="main", verifiers=[]
    )
    assert bad.success is False and "--output-name" in bad.error
    missing = orchestrate(root, scene_file="nope.md", verifiers=[])
    assert missing.success is False and "no scene file" in missing.error


# -----------------------------------------------------------------------------
# The shot cache is the project's
# -----------------------------------------------------------------------------


@pytest.mark.usefixtures("frozen_source_digests")
def test_gc_keeps_what_every_scene_of_the_project_reaches(tmp_path, fake_render):
    """`an cache gc --max-age` used to key only scene.md, so a collection
    dropped another scene's entries once its render's root aged out."""
    from an.build import ShotCache
    from an.build.gc import collect_garbage
    from tests.test_shot_cache import _env, _project, _render, _shot

    root = _project(tmp_path, _shot("a", 10.0))
    _put_scene(
        root,
        "scene.studio.md",
        SceneIR(
            meta=Meta(fps=12, resolution=Resolution(width=160, height=120)),
            timeline=[_shot("a", 77.0)],  # the same shot id, another picture
        ),
    )
    _render(root, fake_render)
    studio, rendered = _render(root, fake_render, scene_file="scene.studio.md")
    assert rendered == ["a"]

    report = collect_garbage(
        root, engine=ShotCache(environment=_env()), max_age=1.0, now=time.time() + 60.0
    )
    assert report.deleted == []
    _, rendered = _render(root, fake_render, scene_file="scene.studio.md")
    assert rendered == []  # nothing the studio scene reads was collected


def test_gc_refuses_when_another_scene_cannot_be_read(tmp_path):
    from an.build.gc import CacheGcError, other_scenes

    root = _two_scene_project(tmp_path)
    load(root, scene_file="scene.studio.md")
    md = root / "scene.studio.md"
    md.write_text(_STUDIO.replace("(cutout)", "(no_such_renderer)"), encoding="utf-8")
    later = time.time() + 10  # newer than its JSON twin by more than sync's tolerance
    os.utime(md, (later, later))
    with pytest.raises(CacheGcError, match="scene.studio.md"):
        other_scenes(root)
