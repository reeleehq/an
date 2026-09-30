"""Raster art: what a PNG, JPEG or WebP is, read from its header (an#211).

Every piece of art the cutout renderer drew was SVG, and the size probe said
so: `an.characters.svg_utils.raster_size` parses its input as XML, so a PNG
plate died in the compiler with ``ParseError: not well-formed (invalid token):
line 1, column 0`` — the error a user sees for "I gave it a picture". Art carved
out of footage, a scanned drawing, a photographed paper cut-out: those are
raster, and tracing them to SVG throws away the shading that made them worth
carving.

PixiJS loads PNG, JPEG and WebP natively (its ``loadTextures`` parser, chosen by
the file's extension), so the renderer needed nothing new. What the COMPILER
needed was three answers it previously got only from an SVG:

- **how big is it** — :func:`image_size`, read from the header (no decode, no
  dependency: the four formats state their pixel size in the first few dozen
  bytes, and a header parse is the same cost as the SVG probe it sits beside);
- **what size does this art draw at, whatever it is** — :func:`art_size`, the
  one probe the compiler, the fidelity check and `an validate` call;
- **what exactly is it** — :func:`content_digest`, because a raster texture is
  addressed by its bytes: a re-carved part is a different texture (the runtime's
  loader ignores a re-added alias on hot reload, an#155) and a different
  compiled contract, so the contract hash covers the pixels it will draw.

**Why a raster part is never recoloured.** A StylePack recolours SVG art by
rewriting the literal colours its descriptor tags (`colour_roles`). A raster
has no literals — its colours are pixels, and inferring a role from a pixel is
exactly what caused an#99's wrong-tone lid — so it renders as drawn, and the
compiler says so once.

>>> is_raster("parts/head.png"), is_raster("parts/head.svg")
(True, False)
"""

from __future__ import annotations

import hashlib
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "RASTER_SUFFIXES",
    "RasterFormatError",
    "art_size",
    "content_digest",
    "has_alpha",
    "image_size",
    "is_raster",
]

#: The raster formats a plate or a part may be, by file suffix. PixiJS 7's
#: ``loadTextures`` picks its parser by extension and accepts exactly these
#: (plus AVIF, left out because Chromium's AVIF decode is the one of the four
#: whose output is not specified bit-exactly and the render is a contract).
RASTER_SUFFIXES: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")

#: How many hex digits of the content digest go into a texture alias — the
#: length the recoloured-texture aliases already use (an#112).
DIGEST_HEX_CHARS: int = 12

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
#: PNG colour types that carry an alpha channel (grey+alpha, RGBA).
_PNG_ALPHA_COLOUR_TYPES: frozenset[int] = frozenset({4, 6})
#: JPEG start-of-frame markers — every SOFn except DHT (C4), JPG (C8), DAC (CC).
_JPEG_SOF_MARKERS: frozenset[int] = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)
#: A header needs at most this many bytes, except a JPEG, whose SOF marker can
#: sit behind EXIF/ICC segments; those are walked marker by marker.
_HEADER_BYTES: int = 64


class RasterFormatError(ValueError):
    """A file named as raster art whose header this module cannot read.

    A `ValueError`, so the compiler's size probe treats it exactly like a
    malformed SVG: the art is declared (and fails loudly at load) rather than
    silently dropped.
    """


def is_raster(src: str | Path) -> bool:
    """Whether ``src`` names raster art, by its suffix (case-insensitive).

    >>> is_raster("plates/Street.JPG")
    True
    >>> is_raster("data:image/svg+xml;base64,AAAA")
    False
    """
    return str(src).lower().endswith(RASTER_SUFFIXES)


def image_size(source: Any) -> tuple[float, float]:
    """``(width, height)`` in pixels of a PNG, JPEG or WebP, from its header.

    ``source`` is a path or the file's bytes.

    >>> import struct, zlib
    >>> ihdr = struct.pack(">IIBBBBB", 3, 2, 8, 6, 0, 0, 0)
    >>> png = (b"\\x89PNG\\r\\n\\x1a\\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
    ...        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)))
    >>> image_size(png)
    (3.0, 2.0)
    """
    data = _read(source)
    if data.startswith(_PNG_SIGNATURE):
        return _png_size(data)
    if data[:2] == b"\xff\xd8":
        return _jpeg_size(source if not isinstance(source, bytes) else data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp_size(data)
    raise RasterFormatError(
        f"{_label(source)} is not a PNG, JPEG or WebP (header "
        f"{data[:12]!r}); raster art must be one of {list(RASTER_SUFFIXES)}"
    )


def has_alpha(source: Any) -> bool | None:
    """Whether the image can be transparent anywhere; ``None`` if unknown.

    A PNG says so in its header (colour type 4 or 6) or with a ``tRNS`` chunk;
    a JPEG never can; a WebP says so in its ``VP8X`` flags or by being lossless
    with an alpha bit. A cut-out part without alpha is a rectangle — the whole
    canvas draws, background and all — which is what `an character validate`
    uses this for.
    """
    data = _read(source)
    if data.startswith(_PNG_SIGNATURE):
        if data[25] in _PNG_ALPHA_COLOUR_TYPES:
            return True
        return b"tRNS" in _png_chunk_types(source)
    if data[:2] == b"\xff\xd8":
        return False
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            return bool(data[20] & 0x10)
        if chunk == b"VP8L":
            bits = struct.unpack("<I", data[21:25])[0]
            return bool((bits >> 28) & 1)
        return False
    return None


def art_size(source: str | Path) -> tuple[float, float]:
    """The size a piece of art rasterises at, whatever format it is.

    SVG: its declared ``width``/``height`` (else its viewBox), as the browser
    does — :func:`an.characters.svg_utils.raster_size`. Raster: its pixel size.
    The ONE probe the compiler, the fidelity check and `an validate` share, so
    none of them can size a PNG as if it were XML again.
    """
    if is_raster(source):
        return image_size(source)
    from an.characters.svg_utils import raster_size

    return raster_size(source)


def content_digest(path: str | Path) -> str:
    """The hex sha256 of a file's bytes, cached by (path, mtime, size).

    Cached because a rig registers every attachment of every slot and a scene
    compiles each shot separately; keyed on the stat so an edited file is
    re-read, which is what makes the digest safe to put in a texture alias.
    """
    p = Path(path)
    st = p.stat()
    return _digest(str(p.resolve()), st.st_mtime_ns, st.st_size)


def short_digest(path: str | Path) -> str:
    """:func:`content_digest`, cut to the length a texture alias carries."""
    return content_digest(path)[:DIGEST_HEX_CHARS]


@lru_cache(maxsize=1024)
def _digest(resolved: str, mtime_ns: int, size: int) -> str:  # noqa: ARG001 — cache key
    return hashlib.sha256(Path(resolved).read_bytes()).hexdigest()


# --- header parsers ----------------------------------------------------------


def _read(source: Any, n: int = _HEADER_BYTES) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source[:n]) if n else bytes(source)
    with open(source, "rb") as f:
        return f.read(n) if n else f.read()


def _label(source: Any) -> str:
    return "the given bytes" if isinstance(source, (bytes, bytearray)) else str(source)


def _png_size(data: bytes) -> tuple[float, float]:
    if data[12:16] != b"IHDR" or len(data) < 24:
        raise RasterFormatError("PNG whose first chunk is not IHDR")
    w, h = struct.unpack(">II", data[16:24])
    if not (w and h):
        raise RasterFormatError(f"PNG with a zero dimension ({w}x{h})")
    return (float(w), float(h))


def _png_chunk_types(source: Any) -> set[bytes]:
    """Chunk types before the image data — where ``tRNS`` must sit."""
    data = _read(source, 0)
    out: set[bytes] = set()
    i = len(_PNG_SIGNATURE)
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i : i + 4])[0]
        kind = data[i + 4 : i + 8]
        if kind == b"IDAT":
            break
        out.add(kind)
        i += 12 + length
    return out


def _jpeg_size(source: Any) -> tuple[float, float]:
    """Walk the marker segments to the first SOFn (EXIF/ICC may precede it)."""
    data = _read(source, 0)
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise RasterFormatError(f"malformed JPEG marker at byte {i}")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        if marker in _JPEG_SOF_MARKERS:
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            if not (w and h):
                raise RasterFormatError(f"JPEG with a zero dimension ({w}x{h})")
            return (float(w), float(h))
        i += 2 + length
    raise RasterFormatError("JPEG with no start-of-frame marker")


def _webp_size(data: bytes) -> tuple[float, float]:
    chunk = data[12:16]
    if chunk == b"VP8X":
        w = 1 + int.from_bytes(data[24:27], "little")
        h = 1 + int.from_bytes(data[27:30], "little")
    elif chunk == b"VP8L":
        bits = struct.unpack("<I", data[21:25])[0]
        w = 1 + (bits & 0x3FFF)
        h = 1 + ((bits >> 14) & 0x3FFF)
    elif chunk == b"VP8 ":
        w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
    else:
        raise RasterFormatError(f"WebP with an unknown first chunk {chunk!r}")
    return (float(w), float(h))
