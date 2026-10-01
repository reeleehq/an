"""``an.media`` (an#247): the sinks, the one GIF recipe, and the old paths that must stay LIVE.

The move out of ``an/adapters/cutout/`` is only safe if every seam the bench and
the tests reach from outside still reaches the code that now reads it. A plain
re-export copies a binding, so rebinding the old name would change nothing the
product reads -- silently. These tests pull each seam at its OLD path and look
for the effect at the NEW one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import an.media.mp4 as mp4
from an.media import GifSink, Mp4Sink, PngSequenceSink, get_sink, register_sink, sink_names
from an.media.frames import DEFAULT_FRAME_PNG_PATTERN, frame_path
from an.media.gif import gif_filter


# ------------------------------------------------------------------ the sinks


def test_one_sink_per_format_and_new_ones_register_by_name():
    assert {"mp4", "gif", "png"} <= set(sink_names())
    assert isinstance(get_sink("mp4", pix_fmt="yuv444p"), Mp4Sink)
    with pytest.raises(KeyError, match="registered:"):
        get_sink("webm")

    class WebmSink:
        name, suffix = "webm", ".webm"

        def write(self, frames_dir, output, *, fps):
            return output

    register_sink("webm", WebmSink)
    try:
        assert get_sink("webm").suffix == ".webm"
        with pytest.raises(ValueError, match="already registered"):
            register_sink("webm", lambda: None)
    finally:
        from an.media import sinks

        sinks._SINKS.pop("webm")


def test_the_gif_recipe_is_the_demo_gallerys_byte_for_byte():
    """The one copy: what `misc/demos/build_demos.py` shipped before an#247."""
    assert gif_filter() == (
        "fps=12,scale=480:-1:flags=neighbor,split[a][b];"
        "[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=none"
    )
    assert gif_filter(crop="100:80:10:0").startswith("crop=100:80:10:0,fps=12,")
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_demos_gif_check", Path(__file__).resolve().parents[1] / "misc/demos/build_demos.py"
    )
    source = Path(spec.origin).read_text(encoding="utf-8")
    assert "palettegen" not in source, "the recipe has one home, an.media.gif"


def test_the_png_sequence_sink_renumbers_from_zero(tmp_path):
    src = tmp_path / "frames"
    src.mkdir()
    for i in (3, 4):
        frame_path(src, i).write_bytes(f"f{i}".encode())
    out = PngSequenceSink().write(src, tmp_path / "seq", fps=24)
    assert [p.read_bytes() for p in sorted(out.iterdir())] == [b"f3", b"f4"]
    assert sorted(p.name for p in out.iterdir()) == [
        DEFAULT_FRAME_PNG_PATTERN % 0,
        DEFAULT_FRAME_PNG_PATTERN % 1,
    ]


@pytest.mark.ffmpeg
def test_the_gif_sink_writes_a_gif_from_a_frame_directory(tmp_path):
    from PIL import Image

    frames = tmp_path / "frames"
    frames.mkdir()
    for i in range(4):
        Image.fromarray(np.full((24, 32, 3), 40 * i, np.uint8)).save(frame_path(frames, i))
    gif = GifSink(width=32).write(frames, tmp_path / "out.gif", fps=24)
    assert gif.read_bytes()[:6] in (b"GIF87a", b"GIF89a")


# ------------------------------------------------ the old paths are LIVE aliases


def test_rebinding_the_pixel_format_at_the_old_path_reaches_the_encode(monkeypatch):
    """The `pix_fmt` seam: the mux resolves `None` from `an.media.mp4`'s global."""
    from an.adapters.cutout import render

    monkeypatch.setattr(render, "DEFAULT_PIX_FMT", "yuv444p")
    assert mp4.DEFAULT_PIX_FMT == "yuv444p"
    assert mp4.check_pix_fmt(None) == "yuv444p"


def test_the_high_crf_lever_still_reaches_the_argv_the_frame_stage_records():
    """`high_crf` rebinds `render.DETERMINISTIC_X264_ARGS`; the core reads mp4's."""
    from an.adapters.cutout import render
    from an.bench.mutations import HIGH_CRF, LEVERS

    shipped = mp4.DETERMINISTIC_X264_ARGS
    with LEVERS["high_crf"].apply():
        argv = list(mp4.DETERMINISTIC_X264_ARGS)
        assert argv[argv.index("-crf") + 1] == HIGH_CRF
        assert render.DETERMINISTIC_X264_ARGS == mp4.DETERMINISTIC_X264_ARGS
    assert mp4.DETERMINISTIC_X264_ARGS == shipped


def test_the_old_names_are_the_new_objects():
    from an.adapters.cutout import render, shutter, supersample
    from an.media import shutter as new_shutter
    from an.media import supersample as new_supersample

    assert render._ffmpeg_mux is mp4.mux_frames
    assert render._ffmpeg_add_audio is mp4.add_audio
    assert render._mux_shot is mp4.mux_shot
    assert render._stage_audio_inputs is mp4.stage_audio_inputs
    assert render.subprocess is mp4.subprocess, "patch_subprocess_run(render) must reach the mux"
    assert render.DEFAULT_FRAME_PNG_PATTERN == DEFAULT_FRAME_PNG_PATTERN
    assert supersample.block_mean_resolve is new_supersample.block_mean_resolve
    assert shutter.mean_png_bytes is new_shutter.mean_png_bytes


def test_a_stub_of_the_ffmpeg_check_at_the_old_path_reaches_the_frame_stage(monkeypatch):
    """`tests/_render_seam.py` stubs `render._ensure_ffmpeg_available` so a seam
    guard runs in the default lane, where there is no ffmpeg. The frame stage
    calls `an.media.mp4.ensure_ffmpeg`; the stub must be what it calls."""
    from an.adapters.cutout import render

    sentinel = lambda: None  # noqa: E731
    monkeypatch.setattr(render, "_ensure_ffmpeg_available", sentinel)
    assert mp4.ensure_ffmpeg is sentinel


def test_a_fractional_rate_reaches_the_mux_unrounded(tmp_path, monkeypatch):
    """23.976 fps must be muxed at 23.976, not 23 or 24: the picture would
    drift against the audio by a frame every 40 s."""
    from tests._fake_subprocess import patch_subprocess_run, touch_output

    seen = []

    class _Result:
        returncode, stderr = 0, ""

    def fake_run(cmd, *a, **kw):
        seen.append(list(cmd))
        touch_output(cmd[-1], root=tmp_path, argv=list(cmd))
        return _Result()

    patch_subprocess_run(monkeypatch, mp4, fake_run)
    mp4.mux_frames(tmp_path, 23.976, tmp_path / "out.mp4")
    argv = seen[0]
    assert argv[argv.index("-framerate") + 1] == "23.976"
