"""The canvas capture path's offline half: arithmetic, ordering, back-pressure.

No browser and no ffmpeg — a fake page stands in for Chromium and answers
``anCaptureFrames`` with synthetic PNG data URLs. What needs a real browser (the
decoded-pixel equivalence with the screenshot path over the golden corpus) is in
``tests/test_canvas_capture_equivalence.py``.
"""

from __future__ import annotations

import base64
import io
import threading
import time

import numpy as np
import pytest

from an.adapters.cutout import canvas_capture, render
from an.adapters.cutout.canvas_capture import (
    DATA_URL_PREFIX,
    CanvasCaptureError,
    canvas_frame_png,
)
from an.adapters.cutout.shutter import mean_png_bytes

WIDTH, HEIGHT = 8, 6


def _png(arr) -> bytes:
    # Pillow is imported where it is used, never at module scope: collection
    # must not depend on the environment (`tests/test_browser_gate.py`).
    from PIL import Image

    out = io.BytesIO()
    Image.fromarray(arr).save(out, format="PNG")
    return out.getvalue()


def _decoded(data: bytes):
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        return im.mode, np.asarray(im).copy()


def _frame_rgba(value: int, *, factor: int = 1):
    """An opaque RGBA canvas frame whose pixels encode ``value``, top row marked.

    The first row is different from the rest, so a vertical flip is visible,
    and every frame differs from every other, so a reordering is visible.
    """
    rng = np.random.default_rng(value)
    arr = rng.integers(0, 256, (HEIGHT * factor, WIDTH * factor, 4), dtype=np.uint8)
    arr[..., 3] = 255
    arr[0, :, 0] = value % 256
    return arr


def _data_url(arr) -> str:
    return DATA_URL_PREFIX + base64.b64encode(_png(arr)).decode("ascii")


# --------------------------------------------------------------- arithmetic


#: Chromium's `toDataURL` returned RGBA on every frame measured; RGB is accepted
#: too, and every pixel test runs over both so neither branch is untested.
CANVAS_MODES = ("RGBA", "RGB")


def _canvas_png(arr, mode: str) -> bytes:
    return _png(arr if mode == "RGBA" else np.ascontiguousarray(arr[..., :3]))


@pytest.mark.parametrize("mode", CANVAS_MODES)
@pytest.mark.parametrize("factor", [1, 2, 3])
@pytest.mark.parametrize("n_samples", [1, 3])
def test_a_canvas_frame_decodes_to_the_screenshot_paths_frame(factor, n_samples, mode):
    """Same pixels in, same decoded frame out — the whole contract, offline.

    The screenshot path gets RGB PNGs from Chromium and runs
    `shutter.mean_png_bytes` (spatial block mean, then temporal mean). The
    canvas path gets RGBA PNGs of the SAME pixels and runs `canvas_frame_png`.
    Their decoded outputs must be identical arrays in the identical mode, at
    every supersample factor and sample count the frame clock can ask for —
    including the rounding ties both resolves spell out.
    """
    rgba = [_frame_rgba(10 * factor + s, factor=factor) for s in range(n_samples)]
    screenshot = mean_png_bytes([_png(a[..., :3]) for a in rgba], factor=factor)
    canvas = canvas_frame_png(
        [_canvas_png(a, mode) for a in rgba], frame=0, factor=factor, size=(WIDTH, HEIGHT)
    )
    s_mode, s_arr = _decoded(screenshot)
    c_mode, c_arr = _decoded(canvas)
    assert (c_mode, c_arr.shape) == (s_mode, s_arr.shape) == ("RGB", (HEIGHT, WIDTH, 3))
    assert np.array_equal(c_arr, s_arr)


@pytest.mark.parametrize("mode", CANVAS_MODES)
def test_rows_are_kept_top_down(mode):
    """`toDataURL` is not `readPixels`: the PNG is already top-down, so the
    first row of the canvas image is the first row written. A flip here is the
    classic readback bug, and it is invisible in a frame-size check."""
    arr = _frame_rgba(200)
    _, out = _decoded(canvas_frame_png([_canvas_png(arr, mode)], frame=0))
    assert np.array_equal(out, arr[..., :3])
    assert not np.array_equal(out, arr[::-1, :, :3])


def test_a_translucent_pixel_is_refused_not_blended():
    """Where alpha < 255 the premultiplied drawing buffer, the PNG and the
    screenshot's composite over the page's white all disagree. Refuse."""
    arr = _frame_rgba(1)
    arr[2, 3, 3] = 254
    with pytest.raises(CanvasCaptureError, match="1 of 48 canvas pixels are not opaque"):
        canvas_frame_png([_png(arr)], frame=4)


def test_a_frame_of_the_wrong_size_is_refused():
    arr = _frame_rgba(1, factor=2)
    with pytest.raises(CanvasCaptureError, match="resolved to 16x12, declared 8x6"):
        canvas_frame_png([_png(arr)], frame=0, factor=1, size=(WIDTH, HEIGHT))


def test_samples_of_different_sizes_are_refused():
    a, b = _frame_rgba(1), _frame_rgba(2, factor=2)
    with pytest.raises(CanvasCaptureError, match="resized mid-frame"):
        canvas_frame_png([_png(a), _png(b)], frame=0)


def test_a_non_png_data_url_is_refused():
    with pytest.raises(CanvasCaptureError, match="zero-size canvas"):
        canvas_capture.decode_data_url("data:,", frame=0)
    with pytest.raises(CanvasCaptureError):
        canvas_capture.decode_data_url("data:image/jpeg;base64,AAAA", frame=0)


def test_the_capture_knob_refuses_an_unknown_path_before_anything_launches():
    # an#192: the canvas path is the default; the screenshot path stays selectable.
    assert render._check_capture(None) == render.DEFAULT_CAPTURE == "canvas"
    assert render._check_capture("screenshot") == "screenshot"
    with pytest.raises(render.CutoutRenderError, match="not one of"):
        render._check_capture("webgl")


def test_the_default_is_read_at_call_time(monkeypatch):
    """So the default is a one-line change, and a lever can pull it."""
    monkeypatch.setattr(render, "DEFAULT_CAPTURE", "screenshot")
    assert render._check_capture(None) == "screenshot"


# ------------------------------------------------ ordering and back-pressure


class _FakePage:
    """Answers ``anCaptureFrames`` like the runtime does, recording each request.

    ``tamper`` rewrites a reply before it is returned — how the tests below
    simulate a page that drops, duplicates or reorders frames.
    """

    def __init__(self, *, frames_dir=None, tamper=None, factor=1):
        self.requests: list[list[dict]] = []
        self.seeks: list[float] = []
        self.written_at_call: list[int] = []
        self.frames_dir = frames_dir
        self.tamper = tamper
        self.factor = factor

    def evaluate(self, expression, arg=None):
        assert expression == render._CAPTURE_FRAMES_JS
        self.requests.append(arg)
        if self.frames_dir is not None:
            self.written_at_call.append(len(list(self.frames_dir.glob("*.png"))))
        frames = []
        for req in arg:
            pngs = []
            for t in req["times"]:
                self.seeks.append(t)
                pngs.append(_data_url(_frame_rgba(req["frame"], factor=self.factor)))
            frames.append(
                {"frame": req["frame"], "width": WIDTH, "height": HEIGHT, "pngs": pngs}
            )
        reply = {"frames": frames}
        return self.tamper(reply) if self.tamper else reply


def test_every_frame_is_written_to_its_own_file_in_order(tmp_path):
    total = 23  # not a multiple of the batch, so the last batch is short
    page = _FakePage()
    render._capture_frames_canvas(page, total, 24, tmp_path, batch=5, workers=3)
    written = sorted(tmp_path.glob("*.png"))
    assert [p.name for p in written] == [
        render.DEFAULT_FRAME_PNG_PATTERN % i for i in range(total)
    ]
    for i, path in enumerate(written):
        _, arr = _decoded(path.read_bytes())
        assert np.array_equal(arr, _frame_rgba(i)[..., :3]), f"frame {i} holds another frame"
    # Seeks go out in frame order, exactly the screenshot path's order.
    assert page.seeks == [i / 24.0 for i in range(total)]
    assert [len(r) for r in page.requests] == [5, 5, 5, 5, 3]


def test_frame_samples_are_seeked_in_frame_then_sample_order(tmp_path):
    samples = ((0.0, 0.01), (0.04, 0.05), (0.08, 0.09))
    page = _FakePage()
    render._capture_frames_canvas(
        page, 3, 25, tmp_path, frame_samples=samples, batch=2
    )
    assert page.seeks == [t for frame in samples for t in frame]
    assert len(list(tmp_path.glob("*.png"))) == 3


def test_supersampled_frames_resolve_to_the_declared_size(tmp_path):
    page = _FakePage(factor=2)
    render._capture_frames_canvas(
        page, 3, 24, tmp_path, 2, resolution=(WIDTH, HEIGHT), batch=2
    )
    from PIL import Image

    for path in tmp_path.glob("*.png"):
        with Image.open(path) as im:
            assert im.size == (WIDTH, HEIGHT)


@pytest.mark.parametrize(
    "tamper, match",
    [
        (lambda r: {"frames": r["frames"][::-1]}, "reordered"),
        (lambda r: {"frames": r["frames"][:-1]}, "dropped"),
        (lambda r: {"frames": r["frames"] + r["frames"][-1:]}, "dropped or reordered"),
        (
            lambda r: {"frames": [dict(f, pngs=f["pngs"] * 2) for f in r["frames"]]},
            r"2 sample\(s\) for 1 instant",
        ),
        (lambda r: None, "is the staged runtime.js older"),
    ],
    ids=["reordered", "dropped", "duplicated", "extra-sample", "no-reply"],
)
def test_a_reply_that_is_not_exactly_the_request_writes_nothing(tmp_path, tamper, match):
    """A dropped or reordered frame is silent corruption: it muxes, it plays,
    and it is wrong. The echoed frame numbers make it a loud one — and the whole
    batch is refused before any of it is written."""
    page = _FakePage(tamper=tamper)
    with pytest.raises(render.CutoutRenderError, match=match):
        render._capture_frames_canvas(page, 4, 24, tmp_path, batch=4)
    assert list(tmp_path.glob("*.png")) == []


def test_a_runtime_failure_is_located_like_the_screenshot_paths():
    page = _FakePage(tamper=lambda r: {"error": "Error: unknown property 'wobble'", "frame": 7, "t": 0.2917})
    with pytest.raises(render.CutoutRenderError) as info:
        render._capture_frames_canvas(page, 8, 24, None, batch=8)
    assert str(info.value).startswith("frame 7 (t=0.2917s) could not be evaluated:")
    assert "unknown property 'wobble'" in str(info.value)


def test_back_pressure_bounds_the_frames_held_in_flight(tmp_path, monkeypatch):
    """When the encoders fall behind, the loop must stop asking the page for
    more. Measured from outside: at every round trip, the frames requested so
    far minus the frames already on disk is at most ``max_inflight`` + one batch.
    Without the bound, a fast page and a slow encoder buffer the whole shot.

    The bound is exact, not approximate: every frame the loop has popped from
    its in-flight queue is already on disk, so requested - written can never
    exceed ``max_inflight`` at the moment the page is asked for more."""
    real = canvas_capture.canvas_frame_png
    active = []
    peak = [0]
    lock = threading.Lock()

    def slow(*a, **kw):
        with lock:
            active.append(1)
            peak[0] = max(peak[0], len(active))
        time.sleep(0.01)
        try:
            return real(*a, **kw)
        finally:
            with lock:
                active.pop()

    monkeypatch.setattr(render, "canvas_frame_png", slow)
    page = _FakePage(frames_dir=tmp_path)
    batch, max_inflight, total, workers = 2, 3, 30, 2
    render._capture_frames_canvas(
        page, total, 24, tmp_path, batch=batch, workers=workers, max_inflight=max_inflight
    )
    requested = 0
    for req, written in zip(page.requests, page.written_at_call):
        assert requested - written <= max_inflight, (requested, written)
        requested += len(req)
    assert len(list(tmp_path.glob("*.png"))) == total
    assert 1 <= peak[0] <= workers, "the pool never runs more encodes than it has workers"


def test_an_encode_failure_surfaces_as_the_typed_error(tmp_path, monkeypatch):
    def broken(*a, frame, **kw):
        raise CanvasCaptureError(f"frame {frame}: synthetic")

    monkeypatch.setattr(render, "canvas_frame_png", broken)
    with pytest.raises(render.CutoutRenderError, match="canvas capture: frame 0: synthetic"):
        render._capture_frames_canvas(_FakePage(), 5, 24, tmp_path, batch=2)


def test_capture_frames_dispatches_on_the_knob(tmp_path):
    """The dispatch sits inside `_capture_frames`, the one function the bench's
    supersample lever wraps, so the lever reaches either path."""
    page = _FakePage()
    render._capture_frames(page, 3, 24, tmp_path, capture="canvas")
    assert len(page.requests) == 1
    assert len(list(tmp_path.glob("*.png"))) == 3


def test_the_runtime_exposes_the_capture_hook():
    """The Python half calls `window.anCaptureFrames`; the runtime must define
    it, read the view (not `renderer.extract`, a non-multisampled re-render),
    and echo the frame numbers the ordering check depends on."""
    from an.adapters.cutout.runtime_files import runtime_dir

    source = (runtime_dir() / "runtime.js").read_text(encoding="utf-8")
    assert "NS.anCaptureFrames = function (requests)" in source
    assert "view.toDataURL('image/png')" in source
    assert "frame: req.frame" in source
    assert "extract" not in source.split("NS.anCaptureFrames")[1].split("};")[0]


# ------------------------------------------- the byte bound (review of an#192)


def test_a_round_trip_carries_at_most_the_pixel_budget(tmp_path):
    """A frame count bounds nothing when a frame is a k-times, many-sample
    canvas: the review measured one reply overflowing the driver's string limit
    (the render then hung). Each round trip is held to ``batch_pixels``."""
    per_frame = WIDTH * HEIGHT
    page = _FakePage()
    render._capture_frames_canvas(
        page, 10, 24, tmp_path, resolution=(WIDTH, HEIGHT), batch=8,
        batch_pixels=3 * per_frame,
    )
    assert [len(r) for r in page.requests] == [3, 3, 3, 1]
    assert len(list(tmp_path.glob("*.png"))) == 10


def test_a_frame_bigger_than_the_budget_is_split_and_written_once(tmp_path):
    """Five instants at a two-instant budget: three round trips for the frame,
    one file, the same pixels as capturing it in one go."""
    samples = ((0.0, 0.01, 0.02, 0.03, 0.04), (0.05,))
    page = _FakePage()
    render._capture_frames_canvas(
        page, 2, 24, tmp_path, frame_samples=samples, resolution=(WIDTH, HEIGHT),
        batch_pixels=2 * WIDTH * HEIGHT,
    )
    assert [[len(q["times"]) for q in r] for r in page.requests] == [[2], [2], [1, 1]]
    assert page.seeks == [t for frame in samples for t in frame]
    whole = tmp_path / "whole"
    whole.mkdir()
    render._capture_frames_canvas(
        _FakePage(), 2, 24, whole, frame_samples=samples, resolution=(WIDTH, HEIGHT)
    )
    for i in range(2):
        name = render.DEFAULT_FRAME_PNG_PATTERN % i
        assert np.array_equal(
            _decoded((tmp_path / name).read_bytes())[1], _decoded((whole / name).read_bytes())[1]
        )
    assert sorted(p.name for p in tmp_path.glob("*.png")) == [
        render.DEFAULT_FRAME_PNG_PATTERN % i for i in range(2)
    ]
