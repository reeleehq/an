"""Place an entity among the planes: ``StagePlacement.after`` (an#344, D1 of an#331).

``stage.after`` names the anchor an entity is drawn right after: an environment
plane (``"set/sky"``) or another placed entity. Checked:

- the document: omit-when-unset, so every stored scene is unchanged;
- the order: bands of planes in containers (``<env>``, ``<env>__band_<k>`` with
  ``scope=<env>``, so every plane stays ``<env>/<plane>``), followers in entity
  order, a follower's own followers right after it;
- the depth: an entity after a compensated plane rides a wrapper
  (``<env>__after_<k>``, ``scope=""``, its paths unchanged) carrying that plane's
  compensation under its own, asserted-new clip id: on screen it moves with
  the plane, not with the camera;
- the refusals, at compile and at validate: no such anchor, itself, a cycle, an
  overlay text block, ``__`` in an entity id, a path indexed twice.
"""

from __future__ import annotations

import warnings

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.adapters.cutout.serialize import to_dict
from an.adapters.cutout.timeline import evaluate_timeline, screen_position, timeline_from_scene
from an.ir.compose import tween
from an.ir.schema import (
    AssetRef,
    Camera,
    CameraKey,
    Meta,
    Resolution,
    SceneIR,
    Shot,
    StagePlacement,
)
from an.ir.validate import validate_semantic
from an.stage import tree

W, H = 320, 240


def _plane(name, color, *, size=None, depth=1.0, offset=(0.0, 0.0)):
    out = {"name": name, "art": {"kind": "fill", "color": color}, "depth": depth, "offset": list(offset)}
    if size is not None:
        out["size"] = list(size)
    return out


def _mall(**props):
    env = {
        "kind": "EnvironmentDescriptor",
        "name": "w",
        "planes": [
            _plane("sky", "#102040", depth=0.25),
            _plane("wall", "#806040", size=(100, 240)),
            _plane("sill", "#604020", size=(320, 40), offset=(0, 100)),
        ],
    }
    text = {"kind": "TextDescriptor", "name": "t", "text": "O", "unit": "line"}
    return {"environments": {"w": env}, "props": {k: {**text, **v} for k, v in props.items()}}


def _prop(eid, after=None, *, at=None):
    stage = StagePlacement(after=after, at=at) if (after or at) else None
    return AssetRef(kind="prop", id=eid, store="props", ref=eid, stage=stage)


def _shot(*entities, actions=(), pan=0.0) -> Shot:
    camera = (
        Camera(keys=[CameraKey(at=0.0, x=0.0), CameraKey(at=1.0, x=pan)]) if pan else None
    )
    return Shot(
        id="s",
        renderer="stage",
        duration=1.0,
        camera=camera,
        entities=[AssetRef(kind="environment", id="set", store="environments", ref="w"), *entities],
        actions=list(actions),
    )


def _compile(shot, mall):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(shot, mall, width=W, height=H)


def _top(doc) -> list[tuple[str, str | None, list[str]]]:
    return [
        (c["name"], c.get("scope"), [x["name"] for x in c["children"]])
        for c in to_dict(doc)["scene"]["children"]
    ]


def _errors(shot, mall) -> list[str]:
    scene = SceneIR(meta=Meta(duration=1.0, resolution=Resolution(width=W, height=H)), timeline=[shot])
    report = validate_semantic(
        scene, available_environments=mall["environments"], available_props=mall["props"]
    )
    return [f.description for f in report.findings if f.severity == "error"]


# --- the document -----------------------------------------------------------------


def test_after_is_omitted_when_unset():
    assert "after" not in StagePlacement(at=(1.0, 2.0)).model_dump()
    assert StagePlacement(after="set/sky").model_dump()["after"] == "set/sky"


def test_no_after_is_today_s_tree_and_after_none_changes_nothing():
    mall = _mall(a={})
    plain = to_dict(_compile(_shot(_prop("a")), mall))
    assert plain == to_dict(_compile(_shot(_prop("a", at=None)), mall))
    assert [c["name"] for c in plain["scene"]["children"]] == ["set", "a"]


# --- the order ----------------------------------------------------------------------


def test_an_entity_after_a_plane_is_drawn_between_the_planes():
    doc = _compile(_shot(_prop("disc", "set/sky")), _mall(disc={}))
    assert _top(doc) == [
        ("set", None, ["sky"]),
        ("set__after_0", "", ["disc"]),
        ("set__band_1", "set", ["wall", "sill"]),
    ]
    # Every plane keeps its one address; the entity keeps its own.
    assert {"set/sky", "set/wall", "set/sill", "disc", "disc/line_0"} <= tree.paths(doc.scene)


def test_followers_keep_entity_order_and_a_follower_s_follower_comes_right_after_it():
    shot = _shot(
        _prop("x", "set/wall"),
        _prop("z", "set/wall"),
        _prop("y", "x"),
        _prop("free"),
    )
    doc = _compile(shot, _mall(x={}, y={}, z={}, free={}))
    order = [name for name, _, _ in _top(doc)]
    # Depth-1.0 wall: no wrapper. x, then what is after x, then z.
    assert order == ["set", "x", "y", "z", "set__band_1", "free"], order


def test_after_an_entity_orders_without_any_plane():
    doc = _compile(_shot(_prop("grid"), _prop("mark", "grid"), _prop("label")), _mall(grid={}, mark={}, label={}))
    assert [n for n, _, _ in _top(doc)] == ["set", "grid", "mark", "label"]


# --- the depth ------------------------------------------------------------------------


def test_an_entity_after_a_far_plane_moves_with_it_not_with_the_camera():
    shot = _shot(_prop("disc", "set/sky"), pan=80.0)
    doc = _compile(shot, _mall(disc={}))
    tl = timeline_from_scene(doc)
    first, last = evaluate_timeline(tl, 0.0), evaluate_timeline(tl, 1.0)

    def dx(path):
        return screen_position(doc, path, pose=last)[0] - screen_position(doc, path, pose=first)[0]

    assert dx("set/sky") == pytest.approx(-20.0)  # depth 0.25 of an 80 px pan
    assert dx("disc") == pytest.approx(dx("set/sky"))
    assert dx("set/wall") == pytest.approx(-80.0)
    clips = [a for a in to_dict(doc)["animations"] if "set__after_0" in a]
    assert clips == ["__parallax__s_set__after_0_x"], clips


def test_a_locked_off_shot_emits_no_wrapper_clip():
    doc = _compile(_shot(_prop("disc", "set/sky")), _mall(disc={}))
    assert not [a for a in to_dict(doc)["animations"] if "__parallax__" in a]


def test_an_authored_channel_on_the_wrapper_is_refused():
    shot = _shot(_prop("disc", "set/sky"), actions=[tween("set__after_0", "x", 5.0, 1.0, from_=0.0)], pan=80.0)
    with pytest.raises(CutoutCompileError, match="set__after_0"):
        _compile(shot, _mall(disc={}))


def test_a_synthetic_clip_id_is_asserted_new():
    from an.stage.compile import _add_compensation_clip

    animations, tracks = {}, []
    keys = [CameraKey(at=0.0, x=0.0), CameraKey(at=1.0, x=10.0)]
    _add_compensation_clip("id", "a", "x", keys, [0.0, 1.0], 1.0, animations, tracks)
    with pytest.raises(CutoutCompileError, match="already taken"):
        _add_compensation_clip("id", "b", "x", keys, [0.0, 1.0], 1.0, animations, tracks)


# --- the refusals -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "entities, needle",
    [
        ([_prop("a", "set/moon")], "neither a plane"),
        ([_prop("a", "nobody")], "neither a plane"),
        ([_prop("a", "a")], "after itself"),
        ([_prop("a", "b"), _prop("b", "a")], "cycle"),
    ],
)
def test_an_anchor_the_shot_cannot_honour_is_refused_at_compile_and_validate(entities, needle):
    mall = _mall(a={}, b={})
    with pytest.raises(CutoutCompileError, match=needle):
        _compile(_shot(*entities), mall)
    assert any(needle in e for e in _errors(_shot(*entities), mall)), _errors(_shot(*entities), mall)


def test_an_overlay_text_block_refuses_after():
    mall = _mall(title={"layer": "overlay"})
    shot = _shot(_prop("title", "set/sky"))
    with pytest.raises(CutoutCompileError, match="overlay"):
        _compile(shot, mall)
    assert any("overlay text 'title'" in e for e in _errors(shot, mall))


def test_validate_reserves_double_underscore_in_entity_ids():
    mall = _mall(**{"set__band_1": {}})
    shot = _shot(_prop("set__band_1"), _prop("disc", "set/sky"))
    assert any("reserved for the stage" in e for e in _errors(shot, {**mall, "props": {**mall["props"], "disc": mall["props"]["set__band_1"]}}))


def test_a_path_indexed_twice_is_refused_at_compile():
    mall = _mall(**{"set__band_1": {}, "disc": {}})
    shot = _shot(_prop("disc", "set/sky"), _prop("set__band_1"))
    with pytest.raises(CutoutCompileError, match="twice"):
        _compile(shot, mall)
