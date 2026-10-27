# an.music_cli

`an music …`: acquire a licensed music library from the shell (an#470).

A thin projection of `foley.sources.music_library` through an’s bridge,
[`an.music_library`](an.music_library.html.md#module-an.music_library), wired into the CLI by `an.tools._dispatch_namespaces`.

### Functions

| [`add_library`](#an.music_cli.add_library)(library[, titles_from, out, pause])   | Download a library's tracks, verified, with a tracks table and the attribution blocks.   |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|

### an.music_cli.add_library(library, titles_from='', out='', pause=2.0)

Download a library’s tracks, verified, with a tracks table and the attribution blocks.

Writes the files, `tracks.csv` (one row per title: status, file, duration,
sha256, licence, the URL the bytes came from and the library’s page, the
attribution, and any metadata the titles file gives) and `ATTRIBUTION.md`
(the blocks to paste under a video) into OUT. A rerun keeps the files the
previous `tracks.csv` recorded, digest checked, and exits 1 when a title
could not be fetched, or its licence does not allow the use (the table
still lists it, with why). A paid library (artlist,
epidemic_sound) downloads nothing: its rows are a wishlist.

library: a registered library (incompetech, artlist, epidemic_sound)
titles_from: a JSON list of titles, a JSON object {title: {metadata}}, or a text file (a video description) whose credits name LIBRARY
out: the folder the files, tracks.csv and ATTRIBUTION.md go in
pause: seconds before a second request to the same host

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
