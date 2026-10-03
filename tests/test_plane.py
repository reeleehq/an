"""Planes tilted away from the camera, and the crawl (an#314).

A node any channel targets with a plane property (``rotation_x``,
``perspective``, ``plane_fade_start``, ``plane_fade_end``) is drawn by
`runtime.js` on a projected plane, its pivot sliding the content along it. The
Python side has three duties, pinned here without a browser: the properties
are part of the one transform vocabulary (validator, compiler, the timing
kernel's space), their rest values agree with the runtime's, and
`an.stage.timeline.Transform2D` projects exactly as the runtime draws. The
browser test renders a tilted square and finds its corners where the Python
projection puts them.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from an.base import PLANE_PROPERTIES, PLANE_REST_VALUES, TRANSFORM_PROPERTIES
from an.ir.schema import AssetRef, Shot, StagePlacement
from an.motion import as_leaves, crawl
from an.stage.compile import compile_shot
from an.stage.timeline import Transform2D, screen_position

W, H = 640, 360
RUNTIME = Path(__file__).resolve().parents[1] / "an" / "stage" / "runtime" / "runtime.js"

_SIDE = 200.0
_SQUARE = {
    "kind": "PathDescriptor",
    "name": "square",
    "points": [(-_SIDE / 2, -_SIDE / 2), (_SIDE / 2, -_SIDE / 2), (_SIDE / 2, _SIDE / 2),
               (-_SIDE / 2, _SIDE / 2), (-_SIDE / 2, -_SIDE / 2)],
    "color": "#ff0000",
    "width": 6.0,
    "cap": "square",
    "join": "miter",
}


def _square_shot(*, tilt: float, y: float = 60.0, pivot_y: float = 0.0) -> tuple[Shot, dict]:
    from an.ir.compose import set_

    shot = Shot(
        id="s",
        renderer="cutout",
        duration=0.5,
        entities=[AssetRef(kind="prop", id="sq", store="props", ref="square",
                           stage=StagePlacement(at=(0.0, y)))],
        actions=[set_("sq", "rotation_x", tilt), set_("sq", "pivot_y", pivot_y)],
    )
    return shot, {"props": {"square": dict(_SQUARE)}}


# -----------------------------------------------------------------------------
# One vocabulary
# -----------------------------------------------------------------------------


def test_the_plane_properties_are_transform_properties_with_units_and_rests():
    from an.stage.compile import _PROPERTY_REST_VALUES
    from an.timing.spaces import STAGE_NODE_UNITS

    assert PLANE_PROPERTIES <= TRANSFORM_PROPERTIES
    assert PLANE_PROPERTIES <= set(STAGE_NODE_UNITS)
    assert {p: _PROPERTY_REST_VALUES[p] for p in PLANE_PROPERTIES} == PLANE_REST_VALUES


def test_the_runtime_rests_the_plane_properties_where_python_does():
    """`runtime.js`'s ``PLANE_PROPERTIES`` table is the runtime's copy of
    :data:`an.base.PLANE_REST_VALUES`: a drift would make a node's rest differ
    between the Python evaluator and the picture."""
    src = RUNTIME.read_text(encoding="utf-8")
    body = re.search(r"const PLANE_PROPERTIES = \{(.*?)\};", src, re.S).group(1)
    js = {k: float(v) for k, v in re.findall(r"(\w+):\s*([-\d.]+)", body)}
    assert js == PLANE_REST_VALUES


def test_a_document_without_a_plane_property_never_mentions_one():
    shot, mall = _square_shot(tilt=0.0)
    flat = shot.model_copy(update={"actions": []})
    doc = compile_shot(flat, mall, width=W, height=H)
    text = doc.model_dump_json()
    assert not any(p in text for p in PLANE_PROPERTIES)


def test_a_plane_property_compiles_to_an_ordinary_channel():
    shot, mall = _square_shot(tilt=0.9)
    doc = compile_shot(shot, mall, width=W, height=H)
    channels = [
        (ch.target, ch.property)
        for anim in doc.animations.values()
        for ch in anim.channels
    ]
    assert ("sq", "rotation_x") in channels


# -----------------------------------------------------------------------------
# The projection: the Python twin of runtime.js "Planes"
# -----------------------------------------------------------------------------


def test_the_hinge_row_is_unmoved_and_rows_above_it_recede():
    t = Transform2D(rotation_x=math.radians(60), eye_distance=1000.0)
    assert t.project((50.0, 0.0)) == (50.0, 0.0)
    near, far = t.project((50.0, -100.0)), t.project((50.0, -400.0))
    # Farther up the plane is narrower, and closer to the horizon at f·cot θ.
    assert far[0] < near[0] < 50.0
    horizon = -1000.0 / math.tan(math.radians(60))
    assert horizon < far[1] < near[1] < 0.0


def test_an_untilted_node_is_the_affine_transform_it_was():
    t = Transform2D(x=10.0, pivot_y=5.0, scale_x=2.0, eye_distance=1000.0)
    assert t.apply((3.0, 4.0)) == Transform2D(x=10.0, pivot_y=5.0, scale_x=2.0).apply((3.0, 4.0))


def test_the_pivot_slides_content_along_the_plane():
    """On a tilted node the pivot is the point of the plane on the hinge: a
    larger ``pivot_y`` moves a content point UP the plane (smaller, higher)."""
    base = dict(rotation_x=1.0, eye_distance=800.0)
    a = Transform2D(**base).apply((100.0, 0.0))
    b = Transform2D(**base, pivot_y=200.0).apply((100.0, 0.0))
    assert b[1] < a[1] and abs(b[0]) < abs(a[0])


def test_screen_position_reads_the_perspective_in_frame_heights():
    shot, mall = _square_shot(tilt=0.9)
    doc = compile_shot(shot, mall, width=W, height=H)
    corner = (-_SIDE / 2, -_SIDE / 2)
    near = screen_position(doc, "sq", pose={("sq", "rotation_x"): 0.9,
                                            ("sq", "perspective"): 1.0}, point=corner)
    far = screen_position(doc, "sq", pose={("sq", "rotation_x"): 0.9,
                                           ("sq", "perspective"): 3.0}, point=corner)
    flat = screen_position(doc, "sq", point=corner)
    # A more distant eye flattens the perspective toward the orthographic tilt.
    assert flat[0] < far[0] < near[0]


# -----------------------------------------------------------------------------
# The crawl preset
# -----------------------------------------------------------------------------


def test_the_crawl_is_one_pivot_tween_and_its_plane_sets():
    from an.ir.compose import flatten
    from an.ir.schema import SetAction, TweenAction

    leaves = flatten(crawl("crawl", distance=1200, duration=12, start=-400, y=300))
    tweens = [f for f in leaves if isinstance(f.action, TweenAction)]
    assert [(f.action.property, f.action.from_value, f.action.to_value) for f in tweens] == [
        ("pivot_y", -400.0, 800.0)
    ]
    sets = {f.action.property for f in leaves if isinstance(f.action, SetAction) and f.start == 0}
    assert sets == {"rotation_x", "perspective", "plane_fade_start", "plane_fade_end", "y"}


def test_the_crawl_refuses_a_fade_that_ends_before_it_starts():
    with pytest.raises(ValueError, match="fade"):
        crawl("crawl", fade=(900.0, 300.0))


@pytest.mark.genre("cutout_animation")
def test_the_crawl_plays_by_name_from_scene_md():
    """``{kind: play, animation: crawl}``: playing a preset by name is the
    cut-out genre's action (an#225); without it, author the leaves."""
    from cutan.characters.registration import PlayAction

    shot = Shot(
        id="s",
        renderer="cutout",
        duration=4.0,
        entities=[AssetRef(kind="prop", id="sq", store="props", ref="square")],
        actions=[PlayAction(target="sq", animation="crawl",
                            args={"distance": 300, "duration": 4.0, "fade": None})],
    )
    doc = compile_shot(shot, {"props": {"square": dict(_SQUARE)}}, width=W, height=H)
    props = {ch.property for anim in doc.animations.values() for ch in anim.channels}
    assert {"rotation_x", "perspective", "pivot_y"} <= props


def test_the_crawl_round_trips_through_scene_md_as_leaves():
    from an.ir.sync import ir_to_markdown, markdown_to_ir
    from an.ir.schema import Meta, SceneIR

    shot, _ = _square_shot(tilt=0.0)
    shot = shot.model_copy(update={"actions": as_leaves(crawl("sq", duration=2.0))})
    scene = SceneIR(meta=Meta(title="t", duration=2.0), timeline=[shot])
    again = markdown_to_ir(ir_to_markdown(scene))
    assert [a.model_dump() for a in again.timeline[0].actions] == [
        a.model_dump() for a in shot.actions
    ]


# -----------------------------------------------------------------------------
# Pixels
# -----------------------------------------------------------------------------


def _red_rows(png) -> dict[int, tuple[int, int]]:
    """``{row: (min x, max x)}`` of the red stroke's pixels."""
    from PIL import Image

    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()
    rows: dict[int, tuple[int, int]] = {}
    for y in range(h):
        xs = [x for x in range(w) if px[x, y][0] > 160 and px[x, y][1] < 90 and px[x, y][2] < 90]
        if xs:
            rows[y] = (min(xs), max(xs))
    assert rows, f"no red pixels in {png}"
    return rows


@pytest.mark.browser
@pytest.mark.ffmpeg
@pytest.mark.parametrize("pivot_y", [0.0, 60.0])
def test_in_pixels_a_tilted_square_lands_where_the_projection_says(tmp_path, pivot_y):
    """A 200 px square, tilted 55°, drawn where `Transform2D` projects its
    corners (within the stroke's half-width plus antialiasing), and a
    trapezoid: its far edge narrower than its near one. With a pivot, the
    same square slides up the plane."""
    from an.adapters._base import RenderContext
    from an.stage.render import CutoutRenderer

    tilt = math.radians(55)
    shot, mall = _square_shot(tilt=tilt, pivot_y=pivot_y)
    result = CutoutRenderer().render(
        shot, RenderContext(mall=mall, work_dir=tmp_path, fps=4, resolution=(W, H))
    )
    rows = _red_rows(result.frame_manifest[-1])
    top, bottom = min(rows), max(rows)
    top_w = rows[top][1] - rows[top][0]
    bottom_w = rows[bottom][1] - rows[bottom][0]
    assert top_w < bottom_w * 0.85, (top_w, bottom_w)

    doc = compile_shot(shot, mall, width=W, height=H)
    pose = {("sq", "rotation_x"): tilt, ("sq", "pivot_y"): pivot_y}
    half = _SIDE / 2
    (tlx, tly), (brx, bry) = (
        screen_position(doc, "sq", pose=pose, point=p) for p in ((-half, -half), (half, half))
    )
    tol = 6
    assert abs(top - tly) <= tol and abs(bottom - bry) <= tol, (top, bottom, tly, bry)
    assert abs(rows[top][0] - tlx) <= tol and abs(rows[bottom][1] - brx) <= tol


# -----------------------------------------------------------------------------
# Loud, not blank (an#314 review)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prop, value, match",
    [("rotation_x", 60.0, "RADIANS"), ("rotation_x", -math.pi / 2, "edge-on"),
     ("perspective", 0.0, "positive"), ("perspective", -1.0, "positive")],
)
def test_a_plane_value_that_would_draw_nothing_is_refused(prop, value, match):
    from an.ir.compose import set_
    from an.stage.compile import CutoutCompileError

    shot, mall = _square_shot(tilt=0.5)
    shot = shot.model_copy(update={"actions": [*shot.actions, set_("sq", prop, value)]})
    with pytest.raises(CutoutCompileError, match=match):
        compile_shot(shot, mall, width=W, height=H)


def test_a_blend_on_a_tilted_node_is_warned_about():
    from an.stage.compile import CutoutCompileWarning
    from an.styles import StylePack

    shot, mall = _square_shot(tilt=0.5)
    pack = StylePack.model_validate({"name": "p", "surface": {"glow": {"color": "#ffffff"}}})
    with pytest.warns(CutoutCompileWarning, match="blend mode"):
        compile_shot(shot, mall, width=W, height=H, style_pack=pack)


def test_the_projection_has_no_position_for_a_point_it_does_not_draw():
    t = Transform2D(rotation_x=1.0, eye_distance=500.0)
    with pytest.raises(ValueError, match="not drawn"):
        t.project((100.0, 700.0))
    with pytest.raises(ValueError, match="not drawn"):
        Transform2D(rotation_x=1.0, eye_distance=0.0).project((0.0, 0.0))
