# an.bench.palette

Derive the set of colours a compiled shot declared — never hand-pin it.

`off_palette_pixel_fraction`’s whole meaning is “not one of the colours the
compiler declared for this shot”. A hand-tuned palette constant would make it a
per-scene magic number, which is exactly what killed its predecessor
(`blend_pixel_fraction`: a 12-flat-fill, anti-aliasing-free frame read 2.46%
at `K=10`, i.e. 4.8x the entire claimed signal).

So the palette is read out of the artifacts the browser actually loaded — the
staged `scene.json` and the staged SVG files beside it — never from a
re-compile. A re-compile can differ from what ran: a missing character
descriptor makes the compiler fall back to the procedural rig, and before
an#33 it did so without a word.

**Three things this module must get right, each a silent failure otherwise:**

1. `parse_color` is a **verbatim mirror of the runtime’s rule**
   (`hex.padEnd(6,'0').slice(0,6)`), not a CSS parser. A CSS-correct 3-digit
   expander maps `"#222"` to `0x222222`; the runtime paints `0x222000`.
2. Some colours are **runtime constants, never present in the JSON** — the eye
   whites, the four mouth colours. A JSON-only sweep under-collects them and
   the metric reads high with no error anywhere.
3. Some `visual.color` values are **inert**: `drawMouthShape` never reads
   its node’s colour, and every `svg_sprite` carries the `#888888` schema
   default. Collecting those over-collects.

Both directions are recorded in `palette_sources` so a reviewer can see which
half moved when the number does.

### Module Attributes

| [`RUNTIME_DEFAULT_COLOUR`](#an.bench.palette.RUNTIME_DEFAULT_COLOUR)    | The runtime's fallback when a `visual.color` is absent or not a string.      |
|----------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`RUNTIME_EYE_COLOURS`](#an.bench.palette.RUNTIME_EYE_COLOURS)       | the sclera fill and the 0.6-alpha outline.                                   |
| [`RUNTIME_MOUTH_COLOURS`](#an.bench.palette.RUNTIME_MOUTH_COLOURS)     | lip, fill, teeth, tongue.                                                    |
| [`RUNTIME_EYE_PUPIL_DEFAULT`](#an.bench.palette.RUNTIME_EYE_PUPIL_DEFAULT) | The runtime's fallback pupil colour when a `visual.color` is absent.         |
| [`COLOURED_KINDS`](#an.bench.palette.COLOURED_KINDS)            | `visual.kind` values whose `visual.color` the runtime actually paints.       |
| [`INERT_COLOUR_KINDS`](#an.bench.palette.INERT_COLOUR_KINDS)        | `visual.kind` values whose `visual.color` is inert.                          |
| [`RUNTIME_JS_RELPATH`](#an.bench.palette.RUNTIME_JS_RELPATH)        | Where the runtime's own hard-coded colours live, for the source cross-check. |

### Functions

| [`palette_for_scene`](#an.bench.palette.palette_for_scene)(scene_json, \*, runtime_dir)   | The declared palette of one staged shot.                                        |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`parse_color`](#an.bench.palette.parse_color)(value)                               | The runtime's own colour rule, mirrored exactly.                                |
| [`runtime_literal_colours`](#an.bench.palette.runtime_literal_colours)(runtime_js)              | Every 6-digit hex literal the runtime source paints.                            |
| [`svg_colours`](#an.bench.palette.svg_colours)(svg_path)                            | Every colour literal an SVG paints, plus the tokens that could not be resolved. |

### an.bench.palette.COLOURED_KINDS *: frozenset[str]* *= frozenset({'ellipse', 'path', 'rect'})*

`visual.kind` values whose `visual.color` the runtime actually paints.
A stroked path (an#160) paints `path.color` — the compiler stamps the same
value onto `visual.color` (asserted by `tests/test_styles.py`), so one read
covers the stroke and the arrowhead, which is filled in that colour.

### an.bench.palette.INERT_COLOUR_KINDS *: frozenset[str]* *= frozenset({'mouth', 'sprite', 'svg_sprite'})*

`visual.kind` values whose `visual.color` is inert.

### an.bench.palette.RUNTIME_DEFAULT_COLOUR *: int* *= 8947848*

The runtime’s fallback when a `visual.color` is absent or not a string.

### an.bench.palette.RUNTIME_EYE_COLOURS *: tuple[int, ...]* *= (16777215, 2236962)*

the sclera fill and the
0.6-alpha outline. The outline’s alpha means it paints BLENDS, so it is a
lower bound on that node’s contribution — the safe direction.

* **Type:**
  Painted by `makeEye` regardless of `visual.color`

### an.bench.palette.RUNTIME_EYE_PUPIL_DEFAULT *: str* *= '#1a1a1a'*

The runtime’s fallback pupil colour when a `visual.color` is absent.

### an.bench.palette.RUNTIME_JS_RELPATH *: str* *= 'an/data/cutout_runtime/runtime.js'*

Where the runtime’s own hard-coded colours live, for the source cross-check.

### an.bench.palette.RUNTIME_MOUTH_COLOURS *: tuple[int, ...]* *= (7023403, 2756624, 16448250, 11552840)*

lip, fill, teeth, tongue. The mouth node’s own
`visual.color` is never read.

* **Type:**
  Painted by `drawMouthShape`

### an.bench.palette.palette_for_scene(scene_json, , runtime_dir)

The declared palette of one staged shot.

`scene_json` is the **staged** compiled scene (what the browser loaded);
`runtime_dir` is the directory it was served from, which is where its
SVGs were staged.

Returns a dict carrying the palette itself plus enough provenance to
explain a move: which half of the derivation each colour came from, whether
the palette is a superset of what was painted, and every token that could
not be resolved.

* **Return type:**
  `dict`

### an.bench.palette.parse_color(value)

The runtime’s own colour rule, mirrored exactly.

`runtime.js`:

```default
function parseColor(s) {
    if (typeof s !== 'string') return 0x888888;
    const hex = s.startsWith('#') ? s.slice(1) : s;
    return parseInt(hex.padEnd(6, '0').slice(0, 6), 16);
}
```

Note what that is **not**: a 3-digit CSS shorthand expander. `"#222"`
pads to `"222000"`, so the runtime paints `0x222000` and so must this.

* **Return type:**
  `int`

```pycon
>>> hex(parse_color("#222"))
'0x222000'
>>> hex(parse_color("#ffffffaa"))
'0xffffff'
>>> hex(parse_color(None))
'0x888888'
```

### an.bench.palette.runtime_literal_colours(runtime_js)

Every 6-digit hex literal the runtime source paints.

Used to cross-check [`RUNTIME_EYE_COLOURS`](#an.bench.palette.RUNTIME_EYE_COLOURS) and
[`RUNTIME_MOUTH_COLOURS`](#an.bench.palette.RUNTIME_MOUTH_COLOURS) against the file that actually paints them,
so adding a fifth mouth colour reddens a test instead of silently inflating
`off_palette_pixel_fraction`.

* **Return type:**
  `set`[`int`]

### an.bench.palette.svg_colours(svg_path)

Every colour literal an SVG paints, plus the tokens that could not be resolved.

Parsed as XML rather than scraped with a regex, so `style="fill:#abc"`
and a `display:none` subtree are both handled — the first is a spelling a
regex over `fill="…"` misses entirely, and the second contributes colours
to a palette that never reach a pixel.

An unresolvable token (a named colour, a `url(#gradient)` reference) is
**returned rather than guessed**: guessing puts a wrong colour in the
palette, and the metric then reads low with no error anywhere.

* **Return type:**
  `tuple`[`set`[`int`], `set`[`str`]]
