"""Frame sinks: a frame directory in, one deliverable out -- one sink per format.

A sink reads the frame directory the frame stage writes (:mod:`an.media.frames`:
one PNG per output frame, at the declared size) and writes one deliverable. It
knows nothing about what drew the frames, so a stage render, a Manim shot's
frames or a ``burns`` crop sequence go through the same three:

========  ===================================================  =====================
name      what it writes                                       knobs
========  ===================================================  =====================
``mp4``   H.264, the pinned argv (:mod:`an.media.mp4`)         ``pix_fmt``
``gif``   the one palette recipe (:mod:`an.media.gif`)         ``crop``, ``fps``, ...
``png``   the frames themselves, copied to a directory         --
========  ===================================================  =====================

New formats register by name (:func:`register_sink`) -- a WebM sink, say --
without editing this module. Browser-side sinks (WebCodecs) belong to the
TypeScript side (``previz``) and are not duplicated here (core study §2.8).

>>> sorted(sink_names())
['gif', 'mp4', 'png']
>>> get_sink("gif", crop="10:10:0:0").crop
'10:10:0:0'
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from an.media import gif as _gif
from an.media import mp4 as _mp4
from an.media.frames import DEFAULT_FRAME_PNG_PATTERN, frame_path

__all__ = [
    "FrameSink",
    "GifSink",
    "Mp4Sink",
    "PngSequenceSink",
    "get_sink",
    "register_sink",
    "sink_names",
]


@runtime_checkable
class FrameSink(Protocol):
    """Writes a frame directory as one deliverable."""

    #: The registry name, and the format's usual name.
    name: str
    #: The deliverable's suffix (``".mp4"``), or ``""`` for a directory.
    suffix: str

    def write(self, frames_dir: Path, output: Path, *, fps: float) -> Path:
        """Write ``frames_dir`` (rendered at ``fps``) to ``output``; return it."""


@dataclass(frozen=True, slots=True)
class Mp4Sink:
    """The silent picture mux (the shot's audio is laid by :func:`an.media.mp4.mux_shot`).

    ``pix_fmt=None`` is the module default AT CALL TIME, the seam the bench pulls.
    """

    pix_fmt: str | None = None
    name: str = "mp4"
    suffix: str = ".mp4"

    def write(self, frames_dir: Path, output: Path, *, fps: float) -> Path:
        _mp4.mux_frames(Path(frames_dir), fps, Path(output), self.pix_fmt)
        return Path(output)


@dataclass(frozen=True, slots=True)
class GifSink:
    """The demo gallery's palette recipe."""

    crop: str = ""
    fps: int = _gif.GIF_FPS
    width: int = _gif.GIF_WIDTH
    max_colours: int = _gif.GIF_MAX_COLOURS
    name: str = "gif"
    suffix: str = ".gif"

    def write(self, frames_dir: Path, output: Path, *, fps: float) -> Path:
        return _gif.to_gif(
            Path(frames_dir),
            Path(output),
            crop=self.crop,
            source_fps=fps,
            fps=self.fps,
            width=self.width,
            max_colours=self.max_colours,
        )


@dataclass(frozen=True, slots=True)
class PngSequenceSink:
    """The frames themselves, renumbered from 0 into ``output`` (a directory).

    >>> import tempfile
    >>> src, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "seq"
    >>> _ = frame_path(src, 0).write_bytes(b"png")
    >>> sorted(p.name for p in PngSequenceSink().write(src, out, fps=24).iterdir())
    ['frame_000000.png']
    """

    name: str = "png"
    suffix: str = ""

    def write(self, frames_dir: Path, output: Path, *, fps: float) -> Path:
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        frames = sorted(Path(frames_dir).glob("*.png"))
        for i, src in enumerate(frames):
            shutil.copyfile(src, output / (DEFAULT_FRAME_PNG_PATTERN % i))
        return output


#: name -> factory taking the sink's knobs as keyword arguments.
_SINKS: dict[str, Callable[..., FrameSink]] = {
    "mp4": Mp4Sink,
    "gif": GifSink,
    "png": PngSequenceSink,
}


def register_sink(name: str, factory: Callable[..., FrameSink], *, replace: bool = False) -> None:
    """Register a sink factory under ``name``; refuse a silent replacement."""
    if name in _SINKS and not replace and _SINKS[name] is not factory:
        raise ValueError(
            f"a sink named {name!r} is already registered ({_SINKS[name]!r}); "
            "pass replace=True to replace it on purpose"
        )
    _SINKS[name] = factory


def get_sink(name: str, **knobs) -> FrameSink:
    """A sink by name, built with ``knobs``; the error lists what exists."""
    try:
        factory = _SINKS[name]
    except KeyError:
        raise KeyError(
            f"no frame sink named {name!r}; registered: {sorted(_SINKS)}"
        ) from None
    return factory(**knobs)


def sink_names() -> list[str]:
    """The registered sink names."""
    return list(_SINKS)
