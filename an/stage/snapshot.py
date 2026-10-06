"""Rasterise art files to PNG in the browser the stage already uses (an#347).

``an library sheet --parts`` tiles an asset's part files; most cut-out parts
are SVG, which nothing in the core can decode. Chromium draws them exactly as
the stage will. Raster parts (PNG, JPEG, WebP, GIF) are drawn the same way, so
one path serves every format the stage loads.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence

__all__ = ["rasterise"]

#: The MIME type each art extension is served as.
_MIME: dict[str, str] = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def drawable(path: str) -> bool:
    """Whether :func:`rasterise` can draw a file of this name.

    >>> drawable("parts/head.svg"), drawable("parts/notes.txt")
    (True, False)
    """
    return any(path.lower().endswith(ext) for ext in _MIME)


def rasterise(files: Sequence[tuple[str, bytes]], *, size: int) -> list[bytes]:
    """PNG bytes of each ``(path, data)`` art file, fitted into a ``size`` square, transparent behind.

    Raises :class:`ImportError` with the install hint when the stage extra is absent.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover — depends on the extra
        raise ImportError(
            "drawing part files needs the stage extra: pip install 'an[stage]' "
            "&& playwright install chromium"
        ) from e
    out: list[bytes] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": size, "height": size})
            for path, data in files:
                ext = "." + path.rsplit(".", 1)[-1].lower()
                src = f"data:{_MIME[ext]};base64,{base64.b64encode(data).decode()}"
                page.set_content(
                    '<html><body style="margin:0;background:transparent">'
                    f'<img src="{src}" style="width:{size}px;height:{size}px;'
                    'object-fit:contain;display:block"></body></html>'
                )
                page.wait_for_function(
                    "() => [...document.images].every(i => i.complete)"
                )
                out.append(page.screenshot(omit_background=True))
        finally:
            browser.close()
    return out
