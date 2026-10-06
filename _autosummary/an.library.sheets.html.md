# an.library.sheets

`an library sheet`: a contact sheet of library versions, one specimen frame each (an#347).

For each reference the version is checked out into a temporary project and
its kind is asked for a specimen — a short shot showing the entity on its own
([`an.genres.EntityKind.specimen`](an.genres.html.md#an.genres.EntityKind.specimen); the core gives props, text blocks and
environments one, a genre its own kinds) — whose first frame is drawn by
[`an.probe.frame()`](an.probe.html.md#an.probe.frame), the path `render` draws with. A kind without a
specimen (a voice, a style, a sound, a kind whose genre gives none) shows a
labelled placeholder. `parts=True` tiles the version’s art files instead.

Every cell is captioned with its reference and licence class, the stricter of
the version’s stored and recomputed rights. A sheet showing anything not
publishable (private or unknown) is refused at a path inside a git work tree
that does not ignore it (`an.library.root.check_private_output()`).

### Module Attributes

| [`DFLT_SHEET`](#an.library.sheets.DFLT_SHEET)   | Where a sheet is written by default (relative to the current folder).   |
|---------------------------------------------------------------|-------------------------------------------------------------------------|

### Functions

| [`sheet`](#an.library.sheets.sheet)(refs, \*[, libraries, package, out, ...])   | Write a contact sheet of `refs` (`[<library>:]<id>[@<version>]`) to one PNG.   |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|

### an.library.sheets.DFLT_SHEET *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'artifacts/probes/sheet.png'*

Where a sheet is written by default (relative to the current folder).

### an.library.sheets.sheet(refs, , libraries=None, package=None, out=None, cell=256, columns=None, parts=False, allow_private_here=False)

Write a contact sheet of `refs` (`[<library>:]<id>[@<version>]`) to one PNG.

libraries: where the references resolve (default: `package`’s search path)
out: the PNG (default [`DFLT_SHEET`](#an.library.sheets.DFLT_SHEET))
parts: tile each version’s art files instead of one specimen frame
allow_private_here: write a not-publishable sheet inside a git work tree

> that does not ignore the path
* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
