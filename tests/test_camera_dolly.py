"""A dolly (an#478): the camera travels into a scene of planes, so each grows by its depth.

Asserted on the compiled channels through the runtime's executable spec
(`evaluate_timeline` + `screen_position`), no browser: a plane of parallax
factor ``f`` shows a local point ``u`` at ``g(f)·(u − f·cam)`` from the
centre, ``g(f) = 1 / (1 − f·dolly)`` (a pinhole camera).
"""

from __future__ import annotations

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.ir.camera import DOLLY_IN, DOLLY_OUT, dolly_growth
from an.ir.schema import AssetRef, Camera, CameraKey, Meta, SceneIR, Shot
from an.ir.validate import validate_semantic

FPS, W, H = 12, 640, 360
DEPTHS = {"far": 0.25, "near": 2.0}
OFFSET = 40.0  # each plane's rest offset on x


def _mall(tmp_path, depths=DEPTHS):
    from an.environments import EnvironmentDescriptor, Plane, PlaneArt
    from an.stores import build_project_mall

    mall = build_project_mall(tmp_path, ensure=True)
    mall["environments"]["depths"] = EnvironmentDescriptor(
        name="depths",
        planes=[
            Plane(
                name=n,
                art=PlaneArt(kind="fill", color="#336699"),
                depth=d,
                size=(40.0, 40.0),
                offset=(OFFSET, 0.0),
            )
            for n, d in depths.items()
        ],
    ).model_dump(mode="json")
    return mall


def _shot(camera: Camera, duration: float = 2.0) -> Shot:
    return Shot(
        id="d",
        renderer="cutout",
        duration=duration,
        camera=camera,
        entities=[
            AssetRef(
                kind="environment", id="depths", store="environments", ref="depths"
            )
        ],
    )


def _compile(tmp_path, camera, **kw):
    return compile_shot(
        _shot(camera), mall=_mall(tmp_path, **kw), fps=FPS, width=W, height=H,
        strict_assets=True,
    )  # fmt: skip


def _on_screen(doc, plane, t, u=0.0):
    """Where plane-local point ``(u, 0)`` lands, from the canvas centre."""
    from an.stage.timeline import (
        evaluate_timeline,
        screen_position,
        timeline_from_scene,
    )

    pose = evaluate_timeline(timeline_from_scene(doc), t)
    x, y = screen_position(doc, f"depths/{plane}", pose=pose, point=(u, 0.0))
    return x - W / 2, y - H / 2


def test_a_dolly_grows_each_plane_by_its_depth(tmp_path):
    """The acceptance: the near plane grows more than the far one, by the
    pinhole model's ratio, at every frame drawn; the dolly is eased."""
    doc = _compile(tmp_path, Camera(move="dolly_in"))
    for k in range(2 * FPS + 1):
        t = k / FPS
        sizes = {}
        for plane, f in DEPTHS.items():
            (x0, _), (x1, _) = (_on_screen(doc, plane, t, u) for u in (-OFFSET, 0.0))
            sizes[plane] = (x1 - x0) / OFFSET
            assert x1 == pytest.approx(sizes[plane] * OFFSET)  # grows about the centre
        if k == 2 * FPS:
            for plane, f in DEPTHS.items():
                assert sizes[plane] == pytest.approx(dolly_growth(f, DOLLY_IN))
    assert sizes["near"] / sizes["far"] == pytest.approx(
        (1 - DEPTHS["far"] * DOLLY_IN) / (1 - DEPTHS["near"] * DOLLY_IN)
    )
    assert sizes["near"] > dolly_growth(1.0, DOLLY_IN) > sizes["far"] > 1.0


def test_a_dolly_during_a_pan_keeps_the_pinhole_projection(tmp_path):
    """Pan and dolly in one key list: a plane point ``u`` lands at
    ``g(f)·(u − f·cam)``, the root zoomed by the character plane's growth."""
    cam = Camera(keys=[CameraKey(at=0.0), CameraKey(at=2.0, x=100.0, dolly=0.2)])
    doc = _compile(tmp_path, cam)
    for t in (0.0, 1.0, 2.0):
        x_cam, dolly = 100.0 * t / 2.0, 0.2 * t / 2.0  # linear keys
        for plane, f in DEPTHS.items():
            for u in (0.0, OFFSET):
                x, _ = _on_screen(doc, plane, t, u - OFFSET)
                assert x == pytest.approx(dolly_growth(f, dolly) * (u - f * x_cam))


def test_dolly_out_shrinks_the_near_plane_most(tmp_path):
    doc = _compile(tmp_path, Camera(move="dolly_out"))
    (x0, _), (x1, _) = (_on_screen(doc, "near", 2.0, u) for u in (-OFFSET, 0.0))
    size = (x1 - x0) / OFFSET
    assert size == pytest.approx(dolly_growth(2.0, DOLLY_OUT)) and size < 0.8


def test_a_camera_without_a_dolly_emits_no_plane_scale(tmp_path):
    """No dolly, no scale and no per-frame keys: a pan compiles to the
    translation-only parallax it always did."""
    doc = _compile(tmp_path, Camera(move="pan_left"))
    props = {
        ch.property
        for aid, a in doc.animations.items()
        if aid.startswith("__parallax__")
        for ch in a.channels
    }
    assert props == {"x"}
    pivot = [
        ch
        for aid, a in doc.animations.items()
        if aid.startswith("__camera__")
        for ch in a.channels
    ]
    assert [len(ch.keyframes) for ch in pivot] == [2]


def test_a_dolly_past_a_foreground_plane_is_refused(tmp_path):
    """A plane at depth 6 is a sixth of the way to the character plane; a
    dolly of 0.2 goes through it."""
    with pytest.raises(CutoutCompileError, match="past plane 'close'"):
        _compile(tmp_path, Camera(move="dolly_in"), depths={"close": 6.0})
    mall = _mall(tmp_path / "v", depths={"close": 6.0})
    report = validate_semantic(
        SceneIR(meta=Meta(), timeline=[_shot(Camera(move="dolly_in"))]),
        available_environments=mall["environments"],
    )
    assert any(
        f.severity == "error" and "past plane 'close'" in f.description
        for f in report.findings
    )


def test_a_dolly_key_round_trips_and_no_dolly_writes_nothing():
    from an.ir.sync import ir_to_markdown, markdown_to_ir

    assert "dolly" not in CameraKey(at=1.0, x=3.0).model_dump()
    shot = _shot(Camera(keys=[CameraKey(at=0.0), CameraKey(at=2.0, dolly=0.2)]))
    back = markdown_to_ir(
        ir_to_markdown(SceneIR(meta=Meta(title="X", duration=2.0), timeline=[shot]))
    )
    assert [k.dolly for k in back.timeline[0].camera.keys] == [0.0, 0.2]
    with pytest.raises(ValueError):
        CameraKey(dolly=1.0)  # the camera on the character plane


def test_the_dolly_moves_need_an_engine_that_lowers_depth():
    from an.semantic import lookup

    assert [str(r) for r in lookup("camera_move", "dolly_in").requires] == [
        "space.multiplane"
    ]
    assert [str(r) for r in lookup("camera_move", "push_in").requires] == [
        "space.framing2d"
    ]
