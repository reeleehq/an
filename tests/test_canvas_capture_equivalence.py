"""The canvas capture path's equivalence gate: same decoded frames, or no flip.

`capture="canvas"` is a faster route to the frames `capture="screenshot"`
writes, and the whole case for it is that nothing downstream can tell. So this
renders each golden-corpus scene both ways and demands, for EVERY frame of every
shot, the same decoded array in the same mode — and the same delivered mp4,
byte for byte, which follows when the frames do because the encode is pinned.
File bytes are not compared: the two paths use different PNG encoders, and
decoded pixels are the criterion the golden corpus itself uses.

It is the gate epic #9's throughput track names. It held on the whole corpus
on a developer machine AND on the labelled Linux rendering lane (an#189), and
the default flipped to ``"canvas"`` on that evidence (an#192) — so a red here
now means the DEFAULT path moved a pixel.

Slow on purpose — every corpus scene twice — so it lives apart from the
offline tests in ``tests/test_canvas_capture.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from an.bench.corpus import BENCH_RENDER_KWARGS, DFLT_FIXTURES

pytestmark = [pytest.mark.browser, pytest.mark.ffmpeg]

REPO_ROOT = Path(__file__).resolve().parents[1]


def _decoded_frames(project_dir: Path, shot_ids) -> list[tuple[str, str, str, tuple, str]]:
    """``(shot, file, mode, shape, sha256-of-decoded-array)`` per frame, in
    TIMELINE order (never directory order — see `iter_shot_dirs`)."""
    import numpy as np
    from PIL import Image

    from an.bench.corpus import iter_shot_dirs

    out = []
    work = project_dir / ".an" / "render_work"
    for shot_id, shot_dir in iter_shot_dirs(work, order=list(shot_ids)):
        for png in sorted((shot_dir / "frames").glob("*.png")):
            with Image.open(png) as im:
                arr = np.asarray(im)
                out.append(
                    (
                        shot_id,
                        png.name,
                        im.mode,
                        arr.shape,
                        hashlib.sha256(arr.tobytes()).hexdigest(),
                    )
                )
    return out


def _render_fixture(name: str, capture: str, base: Path):
    from an.bench.capture import stage_copy
    from an.project import load
    from an.render import render

    fixture = DFLT_FIXTURES[name]
    copy = stage_copy(REPO_ROOT / fixture.path, base / capture)
    if fixture.prepare is not None:
        fixture.prepare(copy)
    project = load(copy)
    mp4 = Path(render(project, **BENCH_RENDER_KWARGS, capture=capture))
    frames = _decoded_frames(copy, [s.id for s in project.scene.timeline])
    return frames, hashlib.sha256(mp4.read_bytes()).hexdigest()


def _mismatches(a, b) -> list[str]:
    if [f[:2] for f in a] != [f[:2] for f in b]:
        return [f"different frame sets: {len(a)} vs {len(b)} frames"]
    return [f"{x[0]}/{x[1]}" for x, y in zip(a, b) if x != y]


@pytest.mark.parametrize("name", sorted(DFLT_FIXTURES))
def test_canvas_capture_is_decoded_pixel_identical_on_the_golden_corpus(name, tmp_path):
    screenshot, screenshot_mp4 = _render_fixture(name, "screenshot", tmp_path)
    canvas, canvas_mp4 = _render_fixture(name, "canvas", tmp_path)
    assert screenshot, f"{name} rendered no frames"
    bad = _mismatches(screenshot, canvas)
    assert not bad, (
        f"{name}: {len(bad)} of {len(screenshot)} frames differ between the "
        f"screenshot and canvas capture paths, e.g. {bad[:5]}"
    )
    assert canvas_mp4 == screenshot_mp4, (
        f"{name}: identical decoded frames but a different delivered mp4 — the "
        "mux is not seeing what the frames directory holds"
    )


def test_the_gate_catches_flipped_rows(tmp_path, monkeypatch):
    """MUTATION: the canvas image flipped top-to-bottom — the `readPixels`
    bottom-up trap. Every frame has the declared size, so no shape check can see
    it; the gate above must. Rendered on a scene with nothing symmetric about
    its horizontal axis."""
    from PIL import Image

    from an.adapters.cutout import canvas_capture

    real = canvas_capture.opaque_rgb

    def flipped(png, *, frame):
        return real(png, frame=frame).transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    screenshot, _ = _render_fixture("path_draw", "screenshot", tmp_path)
    monkeypatch.setattr(canvas_capture, "opaque_rgb", flipped)
    canvas, _ = _render_fixture("path_draw", "canvas", tmp_path)
    assert len(_mismatches(screenshot, canvas)) == len(screenshot), (
        "a vertically flipped capture must differ on every frame"
    )


# ---------------------------------------- a long shot in a parallel pool

LONG_SHOT_SECONDS = 4.0
LONG_SHOT_FPS = 24
LONG_SHOT_COUNT = 3


def _long_project(root: Path):
    """Three 4 s shots of a character crossing the frame: every frame differs
    from its neighbours, so a dropped, duplicated or reordered frame cannot
    hide behind an identical one."""
    from an import init
    from an.ir.compose import tween
    from an.ir.schema import AssetRef, Meta, Resolution, SceneIR, Shot
    from an.project import load

    init(root)
    project = load(root)
    shots = [
        Shot(
            id=f"shot{i}",
            renderer="cutout",
            duration=LONG_SHOT_SECONDS,
            entities=[
                AssetRef(kind="character", id="charlie", store="characters", ref="charlie-v1")
            ],
            actions=[
                tween(
                    "charlie",
                    "x",
                    from_=-100.0 + 10 * i,
                    to=100.0 - 10 * i,
                    duration=LONG_SHOT_SECONDS,
                    easing="linear",
                )
            ],
        )
        for i in range(LONG_SHOT_COUNT)
    ]
    project.scene = SceneIR(
        meta=Meta(
            title="long",
            duration=LONG_SHOT_SECONDS * LONG_SHOT_COUNT,
            fps=LONG_SHOT_FPS,
            resolution=Resolution(width=320, height=240),
        ),
        timeline=shots,
    )
    project.mall["scenes"]["main"] = project.scene
    return [s.id for s in shots]


@pytest.mark.genre("cutout_animation")
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_a_long_render_in_a_parallel_pool_keeps_every_frame_in_order(tmp_path):
    """Back-pressure and ordering under the conditions the prototype numbers
    were NOT measured in: a long shot, a live local server, and one Chromium
    per shot in a parallel pool. The frames must be the screenshot path's,
    frame for frame, in order."""
    from an.render import render_project

    results = {}
    for capture in ("screenshot", "canvas"):
        root = tmp_path / capture
        ids = _long_project(root)
        # Cold: an equivalence measurement must render, and it reads the
        # shots' frames from `.an/render_work/shot_<id>/` (an#242).
        mp4 = render_project(
            root, parallel=LONG_SHOT_COUNT, capture=capture, incremental=False
        )
        results[capture] = (
            _decoded_frames(root, ids),
            hashlib.sha256(Path(mp4).read_bytes()).hexdigest(),
        )
    (a, a_mp4), (b, b_mp4) = results["screenshot"], results["canvas"]
    expected = LONG_SHOT_COUNT * int(round(LONG_SHOT_SECONDS * LONG_SHOT_FPS))
    assert len(a) == len(b) == expected
    per_shot = {}
    for shot, _, _, _, digest in b:
        per_shot.setdefault(shot, []).append(digest)
    for shot, digests in per_shot.items():
        assert all(x != y for x, y in zip(digests, digests[1:])), (
            f"{shot}: two consecutive frames are identical, so this scene cannot "
            "witness a reordering — fix the fixture, not the assertion"
        )
    assert not _mismatches(a, b)
    assert a_mp4 == b_mp4


@pytest.mark.genre("cutout_animation")
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_supersample_and_an_open_shutter_go_through_the_canvas_path_identically(tmp_path):
    """The two frame-stage resolves — the k x k block mean and the frame
    clock's temporal mean — must run on canvas frames exactly as on
    screenshots, and provenance must say which path ran."""
    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer
    from an.project import load

    fps, duration = 12, 1.0
    total = int(round(fps * duration))
    samples = tuple(
        tuple(min(duration, i / fps + d) for d in (0.0, 0.02, 0.04)) for i in range(total)
    )
    frames = {}
    for capture in ("screenshot", "canvas"):
        root = tmp_path / capture
        (shot_id,) = _long_project(root)[:1]
        project = load(root)
        shot = project.scene.timeline[0].model_copy(update={"duration": duration})
        ctx = RenderContext(
            mall=project.mall,
            work_dir=root / ".an" / "render_work",
            fps=fps,
            resolution=(160, 120),
            supersample=2,
            frame_samples=samples,
            capture=capture,
        )
        result = CutoutRenderer().render(shot, ctx)
        assert result.provenance["capture"] == capture
        frames[capture] = _decoded_frames(root, [shot_id])
    assert len(frames["canvas"]) == total
    assert {f[3] for f in frames["canvas"]} == {(120, 160, 3)}
    assert not _mismatches(frames["screenshot"], frames["canvas"])
