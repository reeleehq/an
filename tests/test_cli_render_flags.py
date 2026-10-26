"""`an render` reaches the leaf renderer with every flag it advertises.

The CLI calls `an.orchestrate.render_project`, a wrapper that once
re-declared the leaf's parameters and silently fell behind them: from the day
`--supersample` landed, `an render <dir>` raised ``TypeError`` for everyone,
while the CLI test stubbed the wrapper and stayed green (an#98 review). This
test stubs the LEAF, so the wrapper is exercised for real.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_every_cli_render_flag_reaches_the_leaf_renderer(monkeypatch):
    from an import orchestrate, tools

    seen = {}

    def leaf(project_dir, **kw):
        seen.update(kw)
        return Path("out.mp4")

    monkeypatch.setattr(orchestrate, "_render_project", leaf)
    out = tools.render("proj", tts="mac_say", lipsync="rhubarb", parallel="auto", strict_assets=True, supersample=2, pix_fmt="yuv444p", step_hz=12.0, language="fr", capture="canvas")
    assert out.startswith("rendered:")
    # The shot cache (an#242): the CLI hands the leaf its own engine, so it can
    # report which shots were rendered and which reused.
    from an.build import ShotCache

    assert isinstance(seen.pop("incremental"), ShotCache)
    assert seen == {
        # None: the leaf names the output after the scene file (an#539).
        "output_name": None, "scene_file": "scene.md", "tts": "mac_say", "lipsync": "rhubarb", "parallel": "auto",
        "strict_assets": True, "supersample": 2, "pix_fmt": "yuv444p", "step_hz": 12.0, "language": "fr",
        "capture": "canvas", "force_render": False,
        # The CLI prints the render's findings grouped, after it (an#254).
        "echo_warnings": False,
    }
    seen.clear()
    tools.render("proj", force_render=True, no_cache=True)
    assert seen["force_render"] is True and seen["incremental"] is False
    # And the leaf actually accepts every one of them.
    import inspect

    from an.render import render_project

    params = inspect.signature(render_project).parameters
    assert set(seen) <= set(params), sorted(set(seen) - set(params))


def test_a_scene_flag_reaches_the_leaf_which_names_the_output(monkeypatch):
    """an#539: `--scene scene.studio.md` selects the scene file; the output name
    is left to the leaf (one place decides it), unless the user gave one."""
    from an import orchestrate, tools

    seen = {}
    monkeypatch.setattr(
        orchestrate, "_render_project", lambda d, **kw: seen.update(kw) or Path("out.mp4")
    )
    tools.render("proj", scene="scene.studio.md")
    assert (seen["scene_file"], seen["output_name"]) == ("scene.studio.md", None)
    tools.render("proj", scene="scene.studio.md", output_name="final")
    assert seen["output_name"] == "final"


def _two_scene_project(tmp_path):
    from an import init

    root = init(tmp_path / "demo")
    (root / "scene.studio.md").write_text(
        "# Studio\n\n```yaml meta\ntitle: Studio\nduration: 1\nfps: 12\n```\n",
        encoding="utf-8",
    )
    return root


def test_render_project_names_the_output_after_the_scene_file(monkeypatch, tmp_path):
    """`render_project`'s own `output_name=None` default: `main` for scene.md,
    the stem for another scene; another scene may never take `main`."""
    from an import render as render_mod
    from an.ir.sync import SceneFileError

    root = _two_scene_project(tmp_path)
    seen = []
    monkeypatch.setattr(
        render_mod, "render", lambda project, **kw: seen.append(kw["output_name"])
    )
    render_mod.render_project(root)
    render_mod.render_project(root, scene_file="scene.studio.md")
    render_mod.render_project(root, scene_file="scene.studio.md", output_name="final")
    assert seen == ["main", "scene.studio", "final"]
    with pytest.raises(SceneFileError, match="--output-name"):
        render_mod.render_project(root, scene_file="scene.studio.md", output_name="main")
    (root / "main.md").write_text((root / "scene.studio.md").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(SceneFileError, match="rename the file"):
        render_mod.render_project(root, scene_file="main.md")
    assert seen == ["main", "scene.studio", "final"]  # refused before any render


def test_a_bad_scene_flag_is_a_one_line_refusal_on_the_cli(tmp_path):
    """`an sync <dir> --scene typo.md` used to print "no changes" and exit 0."""
    from typer.testing import CliRunner

    from an.__main__ import build_app

    root = _two_scene_project(tmp_path)
    for command in ("sync", "render"):
        result = CliRunner().invoke(build_app(), [command, str(root), "--scene", "typo.md"])
        assert result.exit_code == 1, result.output
        assert "no scene file 'typo.md'" in result.output
        assert "Traceback" not in result.output
