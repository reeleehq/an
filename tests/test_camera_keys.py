"""The camera's key shape is enforced, and a dropped retired field is a finding (an#454)."""

from __future__ import annotations

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.ir.camera import CameraError
from an.ir.schema import Camera, Meta, SceneIR, Shot
from an.ir.validate import validate_semantic


def _shot(camera=None, *, duration=2.0) -> Shot:
    return Shot(id="s1", renderer="cutout", duration=duration, camera=camera)


def _validate(shot):
    return validate_semantic(SceneIR(meta=Meta(), timeline=[shot]))




@pytest.mark.parametrize("bad", [{"at": 0.0, "bogus": 1}, {"t": 0.0, "x": 0.0}, {"at": 0.0, "pan_x": 0.0}])
def test_an_unknown_camera_key_field_is_refused_at_compile_and_at_validate(bad):
    shot = _shot(Camera(keys=[bad, {"at": 2.0, "x": 10.0}]))
    report = _validate(shot)
    assert not report.passed
    assert any("which no camera reads" in f.description for f in report.findings)
    with pytest.raises((CameraError, CutoutCompileError), match="which no camera reads"):
        compile_shot(shot, fps=24, width=320, height=240)


def test_a_dropped_camera_target_is_a_finding_that_names_follow(tmp_path):
    from an.orchestrate import validate_project
    from an.project import init

    root = init(tmp_path / "p")
    (root / "scene.md").write_text(
        "# X\n\n```yaml meta\ntitle: X\nduration: 1\nfps: 24\ndefault_renderer: cutout\n```\n\n"
        "## Shot s1 (cutout)\n\n```yaml shot\nduration: 1\ncamera:\n  move: hold\n  target: presenter\n```\n",
        encoding="utf-8",
    )
    report = validate_project(root)
    said = [f.description for f in report.findings if f.severity == "warning" and "target" in f.description]
    assert said and "camera.follow" in said[0], [f.description for f in report.findings]
