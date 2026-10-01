"""The frame directory every engine writes and every sink reads.

One PNG per output frame, named by :data:`DEFAULT_FRAME_PNG_PATTERN`, at the
DECLARED size: the frame stage (``an.engines.capture``) resolves supersampling
and the open shutter before a file is written, so nothing downstream ever reads
a resolution off a file or averages anything. The bench, the golden gate, film
assembly and every sink rely on exactly that.

Moved from ``an/adapters/cutout/render.py`` (an#247); the old name still reads
from here.

>>> from pathlib import Path
>>> frame_path(Path("frames"), 7).name
'frame_000007.png'
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "DEFAULT_FRAME_PNG_PATTERN",
    "frame_path",
    "missing_frames",
]

#: The printf pattern of a frame file. ffmpeg reads the same pattern, so a
#: rename here is a rename of every mux's input argument too.
DEFAULT_FRAME_PNG_PATTERN: str = "frame_%06d.png"


def frame_path(frames_dir: Path, index: int) -> Path:
    """Where frame ``index`` lives in ``frames_dir``."""
    return Path(frames_dir) / (DEFAULT_FRAME_PNG_PATTERN % index)


def missing_frames(frames_dir: Path, total_frames: int) -> list[int]:
    """The frame indices in ``[0, total_frames)`` that have no file on disk.

    Checked on DISK rather than on a capture loop's bookkeeping, because the
    mux reads the directory: the directory is what must hold every frame.

    >>> import tempfile
    >>> d = Path(tempfile.mkdtemp())
    >>> _ = frame_path(d, 0).write_bytes(b"")
    >>> missing_frames(d, 3)
    [1, 2]
    """
    return [i for i in range(total_frames) if not frame_path(frames_dir, i).is_file()]
