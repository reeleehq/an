# an.characters.svg_utils

SVG manipulation: namespace-aware DOM helpers using stdlib `xml.etree`.

Pure stdlib so the package stays dependency-light. Operations supported:

- [`promote_inkscape_labels_to_ids()`](#an.characters.svg_utils.promote_inkscape_labels_to_ids) — copy `inkscape:label` to `id`
  on each group, since Inkscape doesn’t auto-promote labels (a 2008-vintage
  bug; see research §1.2).
- [`normalize_svg()`](#an.characters.svg_utils.normalize_svg) — promote labels, ensure a viewBox is set, return
  the parsed `ElementTree`.
- [`extract_pivots()`](#an.characters.svg_utils.extract_pivots) — read the `<g id="skeleton">` group of named
  `<circle>` elements and return `{name: (cx, cy)}`.
- [`extract_part()`](#an.characters.svg_utils.extract_part) — emit a standalone SVG containing only the named
  group. By default it writes a viewBox **cropped** to the part’s own bbox
  while copying the parent’s `width`/`height`, which letterboxes the part
  under `preserveAspectRatio="xMidYMid meet"` (see #75). The crop rect’s
  parent-space origin survives as the viewBox’s first two numbers.
- [`write_svg()`](#an.characters.svg_utils.write_svg) — pretty-print an `ElementTree` (or `Element`) to
  disk with the SVG namespace set as the default.

```pycon
>>> raw = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
...   <g id="skeleton"><circle id="neck" cx="50" cy="40" r="2"/></g>
...   <g id="illustration"><g id="head"><circle cx="50" cy="40" r="20"/></g></g>
... </svg>'''
>>> import io
>>> tree = normalize_svg(io.StringIO(raw))
>>> extract_pivots(tree)
{'neck': (50.0, 40.0)}
>>> part = extract_part(tree, 'head')
>>> b'<g id="head"' in write_svg(part)
True
```

### Functions

| [`extract_part`](#an.characters.svg_utils.extract_part)(source, part_id, \*[, ...])      | Emit a standalone SVG tree containing only the group with the given id.   |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`extract_pivots`](#an.characters.svg_utils.extract_pivots)(source, \*[, skeleton_id])     | Return `{name: (cx, cy)}` for every named `<circle>` under skeleton.      |
| [`normalize_svg`](#an.characters.svg_utils.normalize_svg)(source, \*[, fallback_viewbox]) | Promote Inkscape labels to ids and ensure a viewBox is set.               |
| [`promote_inkscape_labels_to_ids`](#an.characters.svg_utils.promote_inkscape_labels_to_ids)(tree)          | Copy `inkscape:label` to `id` on each group missing an id.                |
| [`raster_size`](#an.characters.svg_utils.raster_size)(source)                           | Return the `(width, height)` an SVG declares for its own raster.          |
| [`write_svg`](#an.characters.svg_utils.write_svg)(tree_or_element[, path])            | Serialize an `ElementTree` or `Element` to bytes (and optionally disk).   |

### an.characters.svg_utils.extract_part(source, part_id, , crop_viewbox=True, padding=8.0)

Emit a standalone SVG tree containing only the group with the given id.

Any top-level `<defs>` from the source is copied so the part can
resolve gradient / pattern / filter references like
`fill="url(#some_gradient)"`. The matched group is appended unchanged.

When `crop_viewbox` is True (the default), the new SVG’s viewBox is
cropped to the bounding box of the part’s primitive content (rect /
circle / ellipse / path) plus `padding` units on each side. This
keeps a part’s texture proportional to its content instead of to the whole
character canvas. Falls back to the source viewBox when no bbox can be
derived.

The emitted `width`/`height` always match the emitted viewBox, so the
part rasterises at its own extent and is never letterboxed inside a canvas
it does not fill. The crop rect’s \*\*parent-space origin survives as the
viewBox’s first two numbers\*\*, so where the part sat relative to its
siblings is not lost and needs no separate record.

If no match is found, raises [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError).

* **Return type:**
  [`ElementTree`](https://docs.python.org/3/library/xml.etree.elementtree.html#xml.etree.ElementTree.ElementTree)

### an.characters.svg_utils.extract_pivots(source, , skeleton_id='skeleton')

Return `{name: (cx, cy)}` for every named `<circle>` under skeleton.

Pivots use the Pose Animator convention: a `<g id="skeleton">` group
sibling of the illustration, containing one `<circle>` per named joint.
The circle’s `cx`/`cy` is the pivot in the same coordinate system as
the art (the SVG’s viewBox).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.characters.svg_utils.normalize_svg(source, , fallback_viewbox='0 0 1024 1024')

Promote Inkscape labels to ids and ensure a viewBox is set.

Returns the parsed `ElementTree`. Idempotent: running it twice is a
no-op on the second pass.

* **Return type:**
  [`ElementTree`](https://docs.python.org/3/library/xml.etree.elementtree.html#xml.etree.ElementTree.ElementTree)

### an.characters.svg_utils.promote_inkscape_labels_to_ids(tree)

Copy `inkscape:label` to `id` on each group missing an id.

Returns the number of groups updated.

Inkscape stores the user-visible name in the `inkscape:label` attribute
and does NOT promote it to `id` on save. This is a long-standing UX
issue (Inkscape bug #243383); the workaround is to promote at parse time.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.characters.svg_utils.raster_size(source)

Return the `(width, height)` an SVG declares for its own raster.

This is the size the browser rasterises the file at, which is what a
`Sprite` then scales — **not** the extent of the drawn art. The two differ
whenever [`extract_part()`](#an.characters.svg_utils.extract_part) has cropped the viewBox while copying the
parent’s dimensions, which is the defect behind #75.

Falls back to the viewBox extent when no `width`/`height` is declared,
matching the browser.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> raster_size('<svg xmlns="http://www.w3.org/2000/svg" '
...             'viewBox="0 0 10 20" width="100" height="100"/>')
(100.0, 100.0)
>>> raster_size('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 20"/>')
(10.0, 20.0)
```

### an.characters.svg_utils.write_svg(tree_or_element, path=None)

Serialize an `ElementTree` or `Element` to bytes (and optionally disk).

Always emits `<?xml version="1.0" encoding="UTF-8"?>` and the SVG
namespace as the default, so the output is a valid standalone SVG.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)
