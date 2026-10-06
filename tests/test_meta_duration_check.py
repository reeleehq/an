"""`an validate` says when meta.duration disagrees with the shots (an#396)."""

from __future__ import annotations

from an.ir.schema import Meta, SceneIR, Shot, Transition
from an.ir.validate import validate_semantic


def _scene(duration, *shots):
    return SceneIR(meta=Meta(duration=duration), timeline=list(shots))


def _said(scene) -> list[str]:
    return [f.description for f in validate_semantic(scene).findings if f.ir_path == "meta/duration"]


def test_a_meta_duration_the_shots_disagree_with_is_a_warning():
    (msg,) = _said(_scene(11.0, Shot(id="a", duration=4.5), Shot(id="b", duration=7.0)))
    assert "11 s" in msg and "11.5 s" in msg and "duration: 11.5" in msg


def test_agreeing_unset_and_dissolve_aware():
    assert _said(_scene(11.5, Shot(id="a", duration=4.5), Shot(id="b", duration=7.0))) == []
    assert _said(_scene(0.0, Shot(id="a", duration=4.5))) == []
    dissolved = Shot(id="b", duration=2.0, transition=Transition(kind="dissolve", duration=0.5))
    assert _said(_scene(3.5, Shot(id="a", duration=2.0), dissolved)) == []
