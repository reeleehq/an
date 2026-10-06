"""``step_hz`` is validated against the frame rate the RENDER uses (an#435).

A scene at 24 fps with ``step_hz: 15`` validated clean, then a render at 12
fps (``render_project(fps=12)``) refused at compile: "step_hz must satisfy
0 < step_hz <= fps (12)". Validate now checks against the render's fps when it
is told it (``validate_semantic(fps=)``, ``validate_project(fps=)``,
``an validate --fps``), and says which fps it used.
"""

from __future__ import annotations

from an.ir.schema import Meta, SceneIR, Shot
from an.ir.validate import validate_semantic


def _scene(*, meta_hz=None, shot_hz=None) -> SceneIR:
    return SceneIR(
        meta=Meta(fps=24, step_hz=meta_hz),
        timeline=[Shot(id="s1", renderer="cutout", duration=1.0, step_hz=shot_hz)],
    )


def _step_errors(report):
    return [f for f in report.findings if f.ir_path.endswith("step_hz") and f.severity == "error"]


def test_step_hz_is_checked_against_the_renders_fps_when_given():
    scene = _scene(meta_hz=15)
    assert not _step_errors(validate_semantic(scene))  # 15 <= 24
    (err,) = _step_errors(validate_semantic(scene, fps=12))
    assert err.ir_path == "meta/step_hz"
    assert "12" in err.description and "the render's fps" in err.description


def test_a_shots_step_hz_too():
    scene = _scene(shot_hz=20)
    assert not _step_errors(validate_semantic(scene))
    (err,) = _step_errors(validate_semantic(scene, fps=12))
    assert err.ir_path.endswith("/step_hz") and err.ir_path != "meta/step_hz"


def test_without_a_render_fps_the_message_names_meta_fps():
    (err,) = _step_errors(validate_semantic(_scene(meta_hz=30)))
    assert "meta.fps" in err.description and "24" in err.description


def test_an_validate_takes_fps(tmp_path):
    from an.project import init
    from an.tools import validate

    project = init(tmp_path / "p")
    md = project / "scene.md"
    text = md.read_text(encoding="utf-8")
    assert "fps: 30" in text
    md.write_text(text.replace("fps: 30", "fps: 30\nstep_hz: 15"), encoding="utf-8")
    assert "step_hz" not in validate(str(project))
    out = validate(str(project), fps=12)
    assert "meta/step_hz" in out and "the render's fps" in out
