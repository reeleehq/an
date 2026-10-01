# an.characters.silhouette

Silhouette rendering and comparison for the silhouette test.

The silhouette test (Disney/AnimSchool, see research §6.4) is a quick
read-test for character distinctiveness: fill the character with solid
black, and if you can still tell who’s who, the design is strong.

This module renders an SVG to a binary silhouette PNG (Playwright is the
underlying rasterizer — already a project dep) and computes an IoU score
between two silhouettes after centering and scaling them to a common
canvas. A score near 1.0 means the silhouettes are nearly identical
(BAD — the characters are indistinguishable). A score below ~0.5 is
typically the sweet spot for visually-distinct characters.

```pycon
>>> from an.characters import generate_default_mouths
>>> import tempfile, pathlib
>>> # Skip the doctest body — it requires Playwright with Chromium installed.
```

### Functions

| [`compare_silhouettes`](#an.characters.silhouette.compare_silhouettes)(a, b, \*[, size])             | Return IoU between two silhouette PNGs (0..1; lower = more distinct).   |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`render_silhouette`](#an.characters.silhouette.render_silhouette)(svg_source, out_png, \*[, ...]) | Render an SVG to a binary silhouette PNG (black on white).              |

### an.characters.silhouette.compare_silhouettes(a, b, , size=(256, 256))

Return IoU between two silhouette PNGs (0..1; lower = more distinct).

Both images are resized to `size`, converted to grayscale, thresholded
at the midpoint, and the intersection-over-union of the foreground (dark)
pixels is computed.

* **Return type:**
  `float`

```pycon
>>> # Two identical silhouettes → IoU = 1.0; two empty → 0.0 (no overlap).
>>> # Tested via test suite, not doctest, since it requires Playwright.
```

### an.characters.silhouette.render_silhouette(svg_source, out_png, , size=(256, 256), background='#ffffff')

Render an SVG to a binary silhouette PNG (black on white).

Uses Playwright/Chromium to rasterize, then PIL to threshold by alpha
or luminance. Returns the output path.

The output is RGB; the silhouette is filled with black (#000) and the
background with the given color.

* **Return type:**
  `Path`
