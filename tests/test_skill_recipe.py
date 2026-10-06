"""The `an` skill's recipe and minimal scene, run as written.

An end-user agent (the e2e style test) could not start a project from the
skill alone: no complete `scene.md`, no way to create a text, path, plane or
sound document, and the only full example lived in a repo-only demo builder.
The skill now carries both, marked ``<!-- skill-test: recipe -->`` (a Python
block) and ``<!-- skill-test: scene -->`` (a ``scene.md``). This runs the recipe
in a fresh directory, writes the scene straight after ``init`` — which is also
the regression test for the seed winning over an immediate edit — validates it,
and compiles every shot with ``strict_assets`` (no browser needed).
"""

from __future__ import annotations

import pytest

import re
import warnings
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "an" / "SKILL.md"


def _skill_text() -> str:
    """The skill's index and every reference file it links (progressive disclosure)."""
    parts = [SKILL, *sorted((SKILL.parent / "references").glob("*.md"))]
    return "\n".join(p.read_text(encoding="utf-8") for p in parts)


def _block(marker: str, fence: str) -> str:
    text = _skill_text()
    m = re.search(
        rf"<!-- skill-test: {marker} -->\n({re.escape(fence)}\w*)\n(.*?)\n{re.escape(fence)}\n",
        text,
        re.DOTALL,
    )
    assert m, f"the an skill has no `<!-- skill-test: {marker} -->` {fence} block"
    return m.group(2)


@pytest.mark.genre("cutout_animation")
def test_the_recipe_and_the_minimal_scene_validate_and_compile(tmp_path, monkeypatch):
    from an.adapters.cutout.compile import compile_shot, style_pack_for
    from an.ir.schema import resolve_step_hz
    from an.orchestrate import validate_project
    from an.project import load

    monkeypatch.chdir(tmp_path)
    exec(compile(_block("recipe", "```"), "an-skill-recipe", "exec"), {})
    root = tmp_path / "my_film"
    (root / "scene.md").write_text(_block("scene", "````"), encoding="utf-8")

    report = validate_project(root)
    assert report.passed, report.findings
    assert not report.findings, [f"{f.severity} {f.ir_path}: {f.description}" for f in report.findings]

    project = load(root)
    scene = project.scene
    assert [s.id for s in scene.timeline] == ["card", "map", "talk"]
    pack = style_pack_for(scene.meta, project.mall["styles"])
    for shot in scene.timeline:
        with warnings.catch_warnings():
            # The pack cannot recolour SVG characters and says so; expected.
            warnings.simplefilter("ignore")
            compile_shot(
                shot,
                mall=project.mall,
                fps=scene.meta.fps,
                width=scene.meta.resolution.width,
                height=scene.meta.resolution.height,
                strict_assets=True,
                step_hz=resolve_step_hz(shot, scene.meta.step_hz),
                style_pack=pack,
                default_easing=scene.meta.default_easing,
            )


def test_a_scene_written_right_after_init_is_the_scene(tmp_path):
    """`init` wrote `scene.md` and `ir/scene.json` in the same instant; a
    `scene.md` written within `sync`'s 0.5 s tolerance was ignored, and the
    empty seed JSON stayed the scene ("no shots")."""
    from an.project import init, load

    root = init(tmp_path / "p")
    (root / "scene.md").write_text(
        "# t\n\n```yaml meta\ntitle: t\n```\n\n## Shot s1 (cutout)\n\n"
        "```yaml shot\nduration: 1.0\n```\n",
        encoding="utf-8",
    )
    assert [s.id for s in load(root).scene.timeline] == ["s1"]
