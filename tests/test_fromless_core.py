"""A from-less tween starts from the built value with NO genre registered (an#365).

The rule (an#212) is the core's: a tween with no ``from`` continues from what its
node shows at its start, the built pose (a ``stage`` placement, a laid-out
``x``) overridden by the sets and tweens before it. It used to run only inside
the cut-out genre's lowering, so a core-only compile snapped to the property's
identity at the tween's first frame. Now the stage's actions pass applies it,
and the document is the same with or without the genre.
"""

from __future__ import annotations

import warnings

from an.adapters.cutout.compile import compile_shot
from an.adapters.cutout.serialize import to_dict
from an.genres import without_genres
from an.ir.compose import sequence, delay, tween
from an.ir.schema import AssetRef, SetAction, Shot, StagePlacement

W, H = 320, 240

_TEXT = {"kind": "TextDescriptor", "name": "t", "text": "hi", "unit": "line"}


def _shot(actions) -> Shot:
    return Shot(
        id="s",
        renderer="stage",
        duration=2.0,
        entities=[
            AssetRef(
                kind="prop",
                id="label",
                store="props",
                ref="t",
                stage=StagePlacement(at=(100.0, -20.0), scale=1.5),
            )
        ],
        actions=list(actions),
    )


def _first_keys(doc) -> dict[tuple[str, str], float]:
    """``{(target, property): first keyframe value}`` of every authored channel."""
    out = {}
    for anim in to_dict(doc)["animations"].values():
        for ch in anim["channels"]:
            out.setdefault((ch["target"], ch["property"]), ch["keyframes"][0]["value"])
    return out


def _compile(shot, *, genre: bool):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if genre:
            return compile_shot(shot, {"props": {"t": _TEXT}}, width=W, height=H)
        with without_genres():
            return compile_shot(shot, {"props": {"t": _TEXT}}, width=W, height=H)


def test_a_from_less_tween_starts_from_the_built_value_with_no_genre():
    shot = _shot([tween("label", "x", 200.0, 1.0), tween("label", "scale_x", 3.0, 1.0)])
    keys = _first_keys(_compile(shot, genre=False))
    assert keys[("label", "x")] == 100.0, "the stage placement, not 0"
    assert keys[("label", "scale_x")] == 1.5


def test_it_continues_from_the_set_or_tween_before_it():
    shot = _shot(
        [
            SetAction(target="label", property="y", value=40.0, at=0.0),
            sequence(delay(0.5), tween("label", "y", 80.0, 0.5)),
            sequence(delay(1.0), tween("label", "y", 0.0, 0.5)),
        ]
    )
    doc = _compile(shot, genre=False)
    firsts = sorted(
        (anim_id, ch["keyframes"][0]["value"])
        for anim_id, anim in to_dict(doc)["animations"].items()
        for ch in anim["channels"]
        if ch["property"] == "y" and len(ch["keyframes"]) > 1 and ch["keyframes"][0]["easing"] != "step"
    )
    assert [v for _, v in firsts] == [40.0, 80.0], firsts


def test_the_document_is_the_same_with_and_without_the_genre():
    shot = _shot(
        [
            tween("label", "x", 200.0, 1.0),
            sequence(delay(1.0), tween("label", "rotation", 0.5, 0.5)),
            SetAction(target="label", property="alpha", value=0.5, at=0.2),
            sequence(delay(0.4), tween("label", "alpha", 1.0, 0.3)),
        ]
    )
    assert to_dict(_compile(shot, genre=False)) == to_dict(_compile(shot, genre=True))
