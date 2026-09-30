# an.characters.validate

Whether an art package is one the compiler can actually render.

The artist-facing contract, checked offline. Wave 4 (#78) exists because the
previous check had no teeth in two separate ways:

- **It checked file existence only.** A part that was present but drew nothing
  passed, and then rendered invisibly — the one failure mode with no diagnostic
  anywhere in the pipeline (`misc/docs/wave4_research.md` §4).
- **It returned a bespoke report type**, so the orchestrator’s typed-error
  routing did not apply to any character problem. Findings here are
  [`an.verify._base.Finding`](an.verify.md#an.verify.Finding), the same type every verifier emits, with
  > `ir_path` pointing at the file or slot that needs the fix.

Everything here is offline and free: no render, no browser, no network. That is
the point — an illustrator should be able to run it before delivering, and a
contract they cannot check themselves is a contract that gets them paid for work
that cannot land.

### Module Attributes

| [`PROHIBITED_ELEMENTS`](#an.characters.validate.PROHIBITED_ELEMENTS)       | Elements an art package may not contain.                                                                                                |
|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| [`PART_SUFFIXES`](#an.characters.validate.PART_SUFFIXES)             | SVG, or raster with the suffixes `an.raster` reads (an#211).                                                                            |
| [`DRAWABLE_ELEMENTS`](#an.characters.validate.DRAWABLE_ELEMENTS)         | Elements that put ink on the canvas.                                                                                                    |
| [`BLOCKING`](#an.characters.validate.BLOCKING)                  | Severity for a problem that stops the part rendering correctly.                                                                         |
| [`ADVISORY`](#an.characters.validate.ADVISORY)                  | Severity for a problem worth fixing that still renders.                                                                                 |
| [`DECLARED_ASPECT_TOLERANCE`](#an.characters.validate.DECLARED_ASPECT_TOLERANCE) | How far a declared box's aspect may differ from its art's before the containment is worth saying (a rounding of a pixel or two is not). |

### Functions

| [`format_report`](#an.characters.validate.format_report)(report, \*, name)          | A short human-readable rendering, for the CLI.                          |
|-------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`render_contract`](#an.characters.validate.render_contract)()                        | The artist-facing spec, generated from the schema and the checks above. |
| [`validate_character`](#an.characters.validate.validate_character)(char_dir, \*[, name]) | Check an art package against the contract, offline.                     |

### an.characters.validate.ADVISORY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'warning'*

Severity for a problem worth fixing that still renders.

### an.characters.validate.BLOCKING *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'error'*

Severity for a problem that stops the part rendering correctly.

### an.characters.validate.DECLARED_ASPECT_TOLERANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.01*

How far a declared box’s aspect may differ from its art’s before the
containment is worth saying (a rounding of a pixel or two is not).

### an.characters.validate.DRAWABLE_ELEMENTS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'circle', 'ellipse', 'line', 'path', 'polygon', 'polyline', 'rect', 'text', 'use'})*

Elements that put ink on the canvas. A part containing none of these is
blank, whatever else it contains.

### an.characters.validate.PART_SUFFIXES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('.svg', '.png', '.jpg', '.jpeg', '.webp')*

SVG, or raster with the
suffixes `an.raster` reads (an#211). Order is the lookup order for a
required part, so an SVG wins when both exist.

* **Type:**
  The part file formats an art package may ship

### an.characters.validate.PROHIBITED_ELEMENTS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'foreignObject': 'embeds non-SVG content that most rasterisers drop', 'image': 'raster embed; ship the raster as its own part instead (parts/<name>.png, with alpha — an#211)', 'script': 'executable content; a part is a drawing, not a program'}*

Elements an art package may not contain.

Not a security perimeter — the renderer loads these files into a headless
browser we control — but a portability one: each of these makes a part render
differently, or not at all, depending on the rasteriser, and a part that
depends on script execution is not a drawing.

### an.characters.validate.format_report(report, , name)

A short human-readable rendering, for the CLI.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.validate.render_contract()

The artist-facing spec, generated from the schema and the checks above.

Every line here is read out of a live object: the required parts and mouth
shapes from [`an.characters.schema`](an.characters.schema.md#module-an.characters.schema), the slot and attachment layout from
a freshly-built descriptor, the prohibitions from
[`PROHIBITED_ELEMENTS`](#an.characters.validate.PROHIBITED_ELEMENTS), and the drawable set from
[`DRAWABLE_ELEMENTS`](#an.characters.validate.DRAWABLE_ELEMENTS). Nothing is retyped, so the document and the
validator cannot disagree.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.validate.validate_character(char_dir, , name=None)

Check an art package against the contract, offline.

Reports a [`Finding`](an.verify.md#an.verify.Finding) per problem: a missing or
unparseable descriptor, absent required parts or mouth shapes, a part that
draws nothing, a prohibited construct, a letterboxed part, a joint name
colliding with a part id, and an unpopulated `AssetSource`.

* **Return type:**
  [`VerificationReport`](an.verify.md#an.verify.VerificationReport)

```pycon
>>> import tempfile, pathlib
>>> with tempfile.TemporaryDirectory() as d:
...     report = validate_character(d, name="nobody")
>>> report.passed
False
>>> any("character.json" in f.description for f in report.findings)
True
```
