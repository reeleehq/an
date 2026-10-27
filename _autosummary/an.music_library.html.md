# an.music_library

Acquire a licensed music library, with provenance (an#470).

A production that scores itself from free libraries wrote the same script each
time: turn the titles a channel credits into download URLs, fetch them politely,
check each file is audio, record where it came from and under which licence,
and collect the attribution lines the licence asks for. [`acquire()`](#an.music_library.acquire) is that
script, and `an music add-library` its command:

> an music add-library incompetech –titles-from usage.json –out audio/macleod
- **A library is data** ([`MusicLibrary`](#an.music_library.MusicLibrary)): who made it, its licence, the
  attribution it asks for, the names a video credits it by, and the rule from
  a title to the file’s URL. The registry ([`MUSIC_LIBRARIES`](#an.music_library.MUSIC_LIBRARIES),
  [`register_music_library()`](#an.music_library.register_music_library)) holds `incompetech` (Kevin MacLeod, CC BY
  > 4.0) and two paid libraries, `artlist` and `epidemic_sound`, which never
  > download: their titles become wishlist rows to license by hand. A library
  > whose licence this package has not checked is registered by the caller, who
  > vouches for it.
- **Every step is a seam** (keyword arguments with working defaults):
  `fetch` (`url -> bytes`, [`polite_fetch()`](#an.music_library.polite_fetch)), `mirrors` (where else
  a URL’s bytes may be: [`direct()`](#an.music_library.direct), then [`wayback()`](#an.music_library.wayback), the Internet
  Archive’s raw copy, the only route to a site that refuses scripts),
  `verify` (`bytes -> seconds`, [`ffprobe_verify()`](#an.music_library.ffprobe_verify)), `sleep` (the
  pause before a second request to the same host) and `out` (any
  `{file name: bytes}` store; a folder by default).
- **A row is an** [`an.ir.assets.AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource), the provenance a sound in
  the project’s store carries: `url` is where the bytes came from (the
  mirror that served them), `source_page_url` the library’s own address.
  A title that fails is a `failed` row with its reasons; the batch goes on. A
  file whose digest a previous run recorded (`kept`) is not fetched again,
  so a rerun resumes.

```pycon
>>> lib = MUSIC_LIBRARIES["incompetech"]
>>> lib.track_url("Sneaky Snitch")
'https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Snitch.mp3'
>>> print(lib.attribution_for("Sneaky Snitch"))
"Sneaky Snitch" Kevin MacLeod (incompetech.com)
Licensed under Creative Commons: By Attribution 4.0 License
http://creativecommons.org/licenses/by/4.0/
```

### Module Attributes

| [`MUSIC_LIBRARIES`](#an.music_library.MUSIC_LIBRARIES)   | The registered libraries, by name.   |
|--------------------------------------------------------------------|--------------------------------------|

### Functions

| [`acquire`](#an.music_library.acquire)(library, titles, \*, out[, fetch, ...])   | Download `titles` of `library` into `out`, verified, one row each.                                                                                                                                                   |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`attribution_text`](#an.music_library.attribution_text)(rows)                            | The attribution blocks to paste under a video, one per track that has one (acquired or kept), blank-line separated, each once.                                                                                       |
| [`direct`](#an.music_library.direct)(url)                                       | The URL itself: the library's own server.                                                                                                                                                                            |
| [`ffprobe_verify`](#an.music_library.ffprobe_verify)(data)                              | The duration of the audio `data`, in seconds; [`MusicLibraryError`](#an.music_library.MusicLibraryError) when it is empty, has no audio stream, or no duration (an error page saved as `.mp3` is all three). |
| [`files_store`](#an.music_library.files_store)(out)                                  | `out` as a `{file name: bytes}` store: a folder (made if missing) becomes a `dol.Files` over it; a mapping is used as it is.                                                                                         |
| [`kept_digests`](#an.music_library.kept_digests)(table)                               | `{file: sha256}` of the acquired or kept rows of a tracks table ([`tracks_table()`](#an.music_library.tracks_table)'s text): what a rerun may keep.                                                     |
| [`polite_fetch`](#an.music_library.polite_fetch)(url, \*[, timeout, max_bytes])       | `url`'s bytes, asked for with a named user agent.                                                                                                                                                                    |
| [`register_music_library`](#an.music_library.register_music_library)(library, \*[, replace])    | Add `library` to [`MUSIC_LIBRARIES`](#an.music_library.MUSIC_LIBRARIES) (`replace` to redefine one).                                                                                                       |
| [`safe_file_name`](#an.music_library.safe_file_name)(title, \*[, suffix])               | `title` as a file name: NFC, path separators as `-`, no leading dot.                                                                                                                                                 |
| [`titles_by_library`](#an.music_library.titles_by_library)(description)                    | The titles a video description credits, by registered library.                                                                                                                                                       |
| [`titles_from_json`](#an.music_library.titles_from_json)(text)                            | A titles file's JSON: a list of titles, or `{title: {metadata}}`.                                                                                                                                                    |
| [`tracks_table`](#an.music_library.tracks_table)(rows)                                | The tracks table as CSV text: `TRACK_COLUMNS`, then any extra the rows carry, in name order.                                                                                                                         |
| [`wayback`](#an.music_library.wayback)(url)                                      | The Internet Archive's raw copy of `url` (`WAYBACK_RAW`).                                                                                                                                                            |

### Classes

| [`AcquiredTrack`](#an.music_library.AcquiredTrack)(title, library, status, source)   | One row of the tracks table: a title, what became of it, and its provenance.   |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`MusicLibrary`](#an.music_library.MusicLibrary)(name, author, license[, ...])      | One library: who made it, under which licence, and where a title's file is.    |

### Exceptions

| [`MusicLibraryError`](#an.music_library.MusicLibraryError)   | A library, a title or a file that cannot be used, and why.             |
|----------------------------------------------------------------------|------------------------------------------------------------------------|
| [`MusicToolMissing`](#an.music_library.MusicToolMissing)    | A tool every title needs is missing: the batch stops before it starts. |

### *class* an.music_library.AcquiredTrack(title, library, status, source, file=None, duration_s=None, error=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One row of the tracks table: a title, what became of it, and its provenance.

#### row()

The row as the tracks table writes it (a list joined by 

```
``
```

; 

```
``
```

, a
mapping as JSON).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.music_library.MUSIC_LIBRARIES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [MusicLibrary](#an.music_library.MusicLibrary)]* *= {'artlist': MusicLibrary(name='artlist', author='Artlist', license=None, track_url=None, license_url=None, attribution='"{title}" {author}', author_url=None, aliases=('Artlist',), file_name=<function safe_file_name>), 'epidemic_sound': MusicLibrary(name='epidemic_sound', author='Epidemic Sound', license=None, track_url=None, license_url=None, attribution='"{title}" {author}', author_url=None, aliases=('Epidemic Sound', 'Epidemic'), file_name=<function safe_file_name>), 'incompetech': MusicLibrary(name='incompetech', author='Kevin MacLeod', license='cc-by-4.0', track_url=<function \_incompetech_url>, license_url='http://creativecommons.org/licenses/by/4.0/', attribution='"{title}" {author} (incompetech.com)\\nLicensed under Creative Commons: By Attribution 4.0 License\\n{license_url}', author_url='https://incompetech.com', aliases=('Kevin MacLeod', 'incompetech', 'incompetech.com'), file_name=<function safe_file_name>)}*

The registered libraries, by name.

### *class* an.music_library.MusicLibrary(name, author, license, track_url=None, license_url=None, attribution='"{title}" {author}', author_url=None, aliases=(), file_name=<function safe_file_name>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One library: who made it, under which licence, and where a title’s file is.

`license` is `None` for a PAID library (its titles become wishlist rows,
never downloads); `track_url` is then unused. `attribution` is a
template over `{title}`, `{author}` and `{license_url}`. `aliases`
are the names a video description credits it by (`From Epidemic Sound:`,
`Kevin MacLeod (incompetech.com)`); `file_name` the name a title is
saved under.

#### file_name(, suffix='.mp3')

`title` as a file name: NFC, path separators as `-`, no leading dot.

```pycon
>>> safe_file_name("AC/DC"), safe_file_name("../../escape")
('AC-DC.mp3', '-..-escape.mp3')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### *exception* an.music_library.MusicLibraryError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A library, a title or a file that cannot be used, and why.

### *exception* an.music_library.MusicToolMissing

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A tool every title needs is missing: the batch stops before it starts.

### an.music_library.acquire(library, titles, \*, out, fetch=<function polite_fetch>, mirrors=(<function direct>, <function wayback>), verify=<function ffprobe_verify>, pause=2.0, sleep=<built-in function sleep>, kept=None)

Download `titles` of `library` into `out`, verified, one row each.

`titles` is a list, or `{title: metadata}` whose metadata (`credited_by`:
the videos that credit it; a catalogue’s `feel`, `genre`, …) is kept
on the row. Each title is fetched from each of `mirrors` in turn until one
gives bytes `verify` accepts; `pause` seconds pass before a second
request to the same host. `kept` is `{file name: sha256}` a previous run
recorded ([`kept_digests()`](#an.music_library.kept_digests)): a file in `out` with that digest is kept,
any other is fetched again. A paid library downloads nothing and returns
wishlist rows.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`AcquiredTrack`](#an.music_library.AcquiredTrack)]

### an.music_library.attribution_text(rows)

The attribution blocks to paste under a video, one per track that has
one (acquired or kept), blank-line separated, each once.

```pycon
>>> src = AssetSource(provider="x", attribution='"A" B')
>>> attribution_text([AcquiredTrack("A", "x", ACQUIRED, src)] * 2)
'"A" B\n'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.music_library.direct(url)

The URL itself: the library’s own server.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.music_library.ffprobe_verify(data)

The duration of the audio `data`, in seconds; [`MusicLibraryError`](#an.music_library.MusicLibraryError)
when it is empty, has no audio stream, or no duration (an error page saved
as `.mp3` is all three). Probed from a temporary file: from a pipe,
ffprobe reports no duration.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.music_library.files_store(out)

`out` as a `{file name: bytes}` store: a folder (made if missing)
becomes a `dol.Files` over it; a mapping is used as it is.

* **Return type:**
  [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]

### an.music_library.kept_digests(table)

`{file: sha256}` of the acquired or kept rows of a tracks table
([`tracks_table()`](#an.music_library.tracks_table)’s text): what a rerun may keep.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.music_library.polite_fetch(url, , timeout=60.0, max_bytes=67108864)

`url`’s bytes, asked for with a named user agent. An HTTP error raises;
so does a text page (an error page served with 200) and a body over
`max_bytes`, before it is read.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.music_library.register_music_library(library, , replace=False)

Add `library` to [`MUSIC_LIBRARIES`](#an.music_library.MUSIC_LIBRARIES) (`replace` to redefine one).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.music_library.safe_file_name(title, , suffix='.mp3')

`title` as a file name: NFC, path separators as `-`, no leading dot.

```pycon
>>> safe_file_name("AC/DC"), safe_file_name("../../escape")
('AC-DC.mp3', '-..-escape.mp3')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.music_library.titles_by_library(description)

The titles a video description credits, by registered library.

A line naming a library (by name or alias, with `From`/`Music by`/
`Music:` and a parenthetical allowed around it) opens its block, and each
following line is a title until a blank line; a timestamp, a
`Song:`/`Track:` label, quotes and bullets are stripped, and links and
licence lines skipped. The attribution form (`"Title" Kevin MacLeod
(incompetech.com)`) credits its title wherever it stands.

```pycon
>>> text = '''Music:
... From Epidemic Sound:
... - 0:00 Night Owl
... - Song: "Morning Light"
... https://www.epidemicsound.com/
...
... "Sneaky Snitch" Kevin MacLeod (incompetech.com)
... Licensed under Creative Commons: By Attribution 4.0 License'''
>>> titles_by_library(text)
{'epidemic_sound': ['Night Owl', 'Morning Light'], 'incompetech': ['Sneaky Snitch']}
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.music_library.titles_from_json(text)

A titles file’s JSON: a list of titles, or `{title: {metadata}}`.

```pycon
>>> titles_from_json('["A", "B"]'), titles_from_json('{"A": {"feel": "Bright"}}')
(['A', 'B'], {'A': {'feel': 'Bright'}})
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)] | [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.music_library.tracks_table(rows)

The tracks table as CSV text: `TRACK_COLUMNS`, then any extra the
rows carry, in name order.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.music_library.wayback(url)

The Internet Archive’s raw copy of `url` (`WAYBACK_RAW`).

```pycon
>>> wayback("https://example.org/a.mp3")
'https://web.archive.org/web/2id_/https://example.org/a.mp3'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
