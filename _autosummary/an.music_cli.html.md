# an.music_cli

`an music …`: acquire a licensed music library from the shell (an#470).

A thin projection of `foley.sources.music_library` through an’s bridge,
[`an.music_library`](an.music_library.html.md#module-an.music_library), wired into the CLI by `an.tools._dispatch_namespaces`.

### Functions

| [`add_library`](#an.music_cli.add_library)(library[, titles_from, out, pause])   | Download a library's tracks, verified, with a tracks table and the attribution blocks.           |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| [`use`](#an.music_cli.use)(project_dir, key, out, title[, start, ...])   | Put an acquired track in the project's sounds store, from its file: nothing is downloaded again. |

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

### an.music_cli.use(project_dir, key, out, title, start=0.0, duration=0.0, fade_out=0.0, description='')

Put an acquired track in the project’s sounds store, from its file: nothing is downloaded again.

Reads OUT/tracks.csv (what `an music add-library` wrote), checks TITLE’s file
against its recorded sha256, cuts it with ffmpeg and stores it as WAV under
KEY, with its provenance (library, the licence the library’s registry gives,
attribution, the URL the bytes came from) and the cut, so `an credits` lists
the music.

project_dir: the an project
key: the sound’s key in the project’s sounds store (what a cue names)
out: the library folder `an music add-library --out` wrote
title: the track’s title, as its tracks.csv row names it
start: seconds into the track where the cut begins
duration: seconds kept (default: to the end)
fade_out: seconds of fade at the end of the cut
description: what the sound is, for the store

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
