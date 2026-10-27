# an.music_library

Acquire a licensed music library, with provenance: an’s bridge to foley (an#470, an#656).

The library itself lives in foley (`foley.sources.music_library`): the
registry (`incompetech`, and the paid `artlist` and `epidemic_sound`,
whose titles become wishlist rows), the direct and Wayback mirrors, the polite
fetch with `429` / `Retry-After` resilience, the audio probe, the licence
gate, the tracks table and the credit parser. `an music add-library`
([`an.music_cli`](an.music_cli.html.md#module-an.music_cli)) is its command:

> an music add-library incompetech –titles-from usage.json –out audio/macleod

What stays here is what is an’s:

- [`asset_source()`](#an.music_library.asset_source), the bridge: one foley row (an
  `AcquiredTrack`, or its `.row()` read
  > back from a tracks table) as an [`an.ir.assets.AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource), the
  > provenance a sound in the project’s store carries. foley’s licence ids become
  > an’s codes ([`license_code()`](#an.music_library.license_code): `CC-BY-4.0` is `cc-by-4.0`; foley’s
  > `unknown`, a paid library’s, is `None`, which an reads as UNKNOWN); the
  > library’s own address is `source_page_url`; `rights_verified`, the mirror
  > and a titles file’s metadata ride as extras.
- [`acquire()`](#an.music_library.acquire), foley’s with an’s `pause` knob (seconds before a second
  request to one host), which becomes foley’s per-host `rate`.

The rest of foley’s surface the command and its tests use (`MUSIC_LIBRARIES`,
[`tracks_table()`](#an.music_library.tracks_table), [`attribution_text()`](#an.music_library.attribution_text), [`titles_by_library()`](#an.music_library.titles_by_library), …) is
re-exported by name, and loaded on first use: `import an` never imports foley.

```pycon
>>> license_code("CC-BY-4.0"), license_code("unknown")
('cc-by-4.0', None)
>>> src = asset_source({"title": "Sneaky Snitch", "library": "incompetech",
...                     "status": "acquired", "license": "CC-BY-4.0",
...                     "source_page_url": "https://incompetech.com/x.mp3",
...                     "rights_verified": True, "mirror": "wayback"})
>>> src.provider, src.id, src.license, src.source_page_url
('incompetech', 'Sneaky Snitch', 'cc-by-4.0', 'https://incompetech.com/x.mp3')
>>> src.model_extra
{'rights_verified': True, 'mirror': 'wayback'}
```

### Module Attributes

| [`DFLT_PAUSE_S`](#an.music_library.DFLT_PAUSE_S)        | a library is someone's website).                                     |
|----------------------------------------------------------------------|----------------------------------------------------------------------|
| [`FOLEY_LICENSE_CODES`](#an.music_library.FOLEY_LICENSE_CODES) | `unknown` (a paid library claims no rights) is `None`, an's UNKNOWN. |

### Functions

| [`acquire`](#an.music_library.acquire)(library, titles, \*, out[, pause, config])   | foley's `acquire()`, paced by `pause`.                                                                                                                                                                                                                                            |
|-------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`asset_source`](#an.music_library.asset_source)(track, \*[, codes])                     | One foley row as an's [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource).                                                                                                                                                                      |
| [`attribution_text`](#an.music_library.attribution_text)(rows)                               | The attribution blocks to paste under a video, one per track that has one (acquired or kept), blank-line separated, each once.                                                                                                                                                    |
| [`files_store`](#an.music_library.files_store)(out)                                     | `out` as a `{file name: bytes}` store: a mapping is used as it is; a folder becomes foley's file store over it (`foley.stores.make_byte_store()`, which makes the folder on its first write).                                                                                     |
| [`kept_digests`](#an.music_library.kept_digests)(table)                                  | `{file: sha256}` of the acquired or kept rows of a tracks table: what a rerun may keep.                                                                                                                                                                                           |
| [`kept_sources`](#an.music_library.kept_sources)(table)                                  | `{file: {"sha256", "url", "mirror"}}` of the acquired or kept rows of a tracks table: [`kept_digests()`](#an.music_library.kept_digests) with where each file came from, so a kept row still says which URL and mirror served it (`acquire(kept=...)` takes either). |
| [`license_code`](#an.music_library.license_code)(license_id, \*[, codes])                | foley's licence id as an's code: `codes` first, else the id in lowercase.                                                                                                                                                                                                         |
| [`probe_verify`](#an.music_library.probe_verify)(data, \*[, probe, has_audio, suffix])   | The duration of the audio `data`, in seconds.                                                                                                                                                                                                                                     |
| [`register_music_library`](#an.music_library.register_music_library)(library, \*[, replace])       | Add `library` to `MUSIC_LIBRARIES` (`replace` to redefine one).                                                                                                                                                                                                                   |
| [`titles_by_library`](#an.music_library.titles_by_library)(description, \*[, libraries])      | The titles a video description credits, by library (default: the registered ones).                                                                                                                                                                                                |
| [`titles_from_json`](#an.music_library.titles_from_json)(text)                               | A titles file's JSON: a list of titles, or `{title: {metadata}}`.                                                                                                                                                                                                                 |
| [`tracks_table`](#an.music_library.tracks_table)(rows)                                   | The tracks table as CSV text: `TRACK_COLUMNS`, then any metadata the rows carry, in name order.                                                                                                                                                                                   |
| [`wayback`](#an.music_library.wayback)(url)                                         | The Internet Archive's raw copy of `url` (`WAYBACK_RAW`).                                                                                                                                                                                                                         |

### Classes

| [`AcquiredTrack`](#an.music_library.AcquiredTrack)(title, library, status, license)   | One row of the tracks table: a title, what became of it, and its provenance.   |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`MusicLibrary`](#an.music_library.MusicLibrary)(name, author[, license_url, ...])   | One library: who made it, under which licence, and where a title's file is.    |

### Exceptions

| [`MusicLibraryError`](#an.music_library.MusicLibraryError)   | A library, a title or a file that cannot be used, and why.             |
|----------------------------------------------------------------------|------------------------------------------------------------------------|
| [`MusicToolMissing`](#an.music_library.MusicToolMissing)    | A tool every title needs is missing: the batch stops before it starts. |

### *class* an.music_library.AcquiredTrack(title, library, status, license, file=None, sha256=None, duration_s=None, url=None, mirror=None, page_url=None, credited_by=(), metadata=dict(), error=None)

Bases: `SerializableMixin`

One row of the tracks table: a title, what became of it, and its provenance.

`url` is the URL that served the bytes (a mirror’s), `mirror` that mirror’s
name, `page_url` the library’s own address for the title; `credited_by` the
videos that credit it and `metadata` a titles file’s other fields (`feel`,
`genre`, …).

#### row()

The row as the tracks table writes it: flat and JSON-safe (a list joined
by 

```
``
```

; 

```
``
```

, a mapping as JSON).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.music_library.DFLT_PAUSE_S *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 2.0*

a library
is someone’s website).

* **Type:**
  Seconds before a second request to one host (foley’s default pace

### an.music_library.FOLEY_LICENSE_CODES *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)]* *= {'unknown': None}*

`unknown` (a paid
library claims no rights) is `None`, an’s UNKNOWN.

* **Type:**
  foley licence ids whose an code is not the id in lowercase

### *class* an.music_library.MusicLibrary(name, author, license_url=None, track_url=None, attribution='"{title}" {author}', author_url=None, aliases=(), file_name=<function safe_file_name>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One library: who made it, under which licence, and where a title’s file is.

`license_url` is the URL of its Creative Commons licence, read by
`license_id_from_cc_url()`; `None` makes the library
PAID (its titles become wishlist rows, never downloads; `track_url` is then
unused). `track_url` is the `title -> URL` rule (`title_url()` builds one
from a template). `attribution` is a template over `{title}`, `{author}`
and `{license_url}`. `aliases` are the names a video description credits it
by (`From Epidemic Sound:`, `Kevin MacLeod (incompetech.com)`);
`file_name` the name a title is saved under.

#### attribution_for(title)

The library’s attribution for `title`, from its template.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### file_name(, suffix='.mp3')

`title` as a file name: NFC, path separators as `-`, no leading dot.

```pycon
>>> safe_file_name("AC/DC"), safe_file_name("../../escape")
('AC-DC.mp3', '-..-escape.mp3')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### *property* license_id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The foley licence id its licence URL maps to (`'unknown'` when paid).

#### *property* paid *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether the library has no free licence (wishlist rows only).

#### *property* rights_verified *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether foley recognises the licence outright (never for a paid library).

### *exception* an.music_library.MusicLibraryError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A library, a title or a file that cannot be used, and why.

### *exception* an.music_library.MusicToolMissing

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A tool every title needs is missing: the batch stops before it starts.

### an.music_library.acquire(library, titles, , out, pause=2.0, config=None, \*\*kwargs)

foley’s `acquire()`, paced by `pause`.

`pause` is the seconds before a second request to one host (`0`: no
pause), foley’s `rate` unless `config` states its own. `config` and every
other keyword (`fetch`, `mirrors`, `verify`, `kept`, `intended_use`,
`clock`, `sleep`, …) go to foley as they are. Bridge the rows with
[`asset_source()`](#an.music_library.asset_source).

* **Raises:**
  [**MusicLibraryError**](#an.music_library.MusicLibraryError) – For a negative `pause`, and whatever foley’s
      `acquire` refuses.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`AcquiredTrack`](#an.music_library.AcquiredTrack)]

### an.music_library.asset_source(track, , codes={'unknown': None})

One foley row as an’s [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource).

`track` is a foley `AcquiredTrack` or its `.row()` (as a tracks table
reads back). `library` is the `provider`, `title` the `id`, the
licence id an’s code ([`license_code()`](#an.music_library.license_code)); `url` (the mirror that served
the bytes), `source_page_url` (the library’s own address), the licence URL,
author, attribution and `sha256` keep their names. The acquisition’s own
columns (`ROW_ONLY`) stay in the table; every other column
(`rights_verified`, `commercial_ok`, `mirror`, `credited_by`, a titles
file’s metadata) rides as an extra; a licence flag read back from CSV
(`FLAG_COLUMNS`) is a boolean again. Empty cells are dropped. A track also
gives its licence’s `creator_url` as `author_url` and whether its terms let
the bytes be kept as `cacheable`.

* **Return type:**
  [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource)

### an.music_library.attribution_text(rows)

The attribution blocks to paste under a video, one per track that has one
(acquired or kept), blank-line separated, each once.

Each block is `foley.provenance.credits.attribution_line()` of the row’s
licence: the library’s own wording, verbatim.

```pycon
>>> from foley.sources.music_library import MUSIC_LIBRARIES, track_license
>>> lic = track_license(MUSIC_LIBRARIES["incompetech"], "A")
>>> print(attribution_text([AcquiredTrack("A", "incompetech", ACQUIRED, lic)] * 2))
"A" Kevin MacLeod (incompetech.com)
Licensed under Creative Commons: By Attribution 4.0 License
http://creativecommons.org/licenses/by/4.0/
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.music_library.files_store(out)

`out` as a `{file name: bytes}` store: a mapping is used as it is; a folder
becomes foley’s file store over it (`foley.stores.make_byte_store()`, which
makes the folder on its first write).

* **Return type:**
  [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]

### an.music_library.kept_digests(table)

`{file: sha256}` of the acquired or kept rows of a tracks table: what a rerun
may keep. `table` is [`tracks_table()`](#an.music_library.tracks_table)’s CSV text, or the rows themselves
([`AcquiredTrack`](#an.music_library.AcquiredTrack) or their [`row()`](#an.music_library.AcquiredTrack.row) dicts, read back
from JSON).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.music_library.kept_sources(table)

`{file: {"sha256", "url", "mirror"}}` of the acquired or kept rows of a
tracks table: [`kept_digests()`](#an.music_library.kept_digests) with where each file came from, so a kept row
still says which URL and mirror served it (`acquire(kept=...)` takes either).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.music_library.license_code(license_id, , codes={'unknown': None})

foley’s licence id as an’s code: `codes` first, else the id in lowercase.

```pycon
>>> license_code("CC0-1.0"), license_code("unknown"), license_code(None)
('cc0-1.0', None, None)
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.music_library.probe_verify(data, , probe=None, has_audio=None, suffix='.mp3')

The duration of the audio `data`, in seconds.

The bytes are written to a temporary file named with `suffix` (from a pipe,
ffprobe reports no duration). `has_audio(path) -> True | False | None` must
say `True` (default `has_audio_stream()`; `None`,
“cannot tell”, is a refusal), then `probe(path) -> seconds | None` reads the
length (default `default_probe()`).

```pycon
>>> probe_verify(b"ID3...", probe=lambda path: 61.5, has_audio=lambda path: True)
61.5
>>> probe_verify(b"<html>403</html>", probe=lambda path: 3.0,
...              has_audio=lambda path: False)
Traceback (most recent call last):
...
foley.sources.music_library.libraries.MusicLibraryError: the file has no audio stream
>>> probe_verify(b"ID3...", probe=lambda path: None, has_audio=lambda path: True)
Traceback (most recent call last):
...
foley.sources.music_library.libraries.MusicLibraryError: the file has no readable duration (not audio)
```

* **Raises:**
  [**MusicLibraryError**](#an.music_library.MusicLibraryError) – When the file is empty, has no audio stream (or one
      cannot be confirmed), or has no readable duration.
* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.music_library.register_music_library(library, , replace=False)

Add `library` to `MUSIC_LIBRARIES` (`replace` to redefine one).

A free library is checked for one licence right only, keeping the files
(`cache_bytes_ok`); the uses a production makes of them are gated per title by
`acquire()` (`intended_use`).

* **Raises:**
  [**MusicLibraryError**](#an.music_library.MusicLibraryError) – If the name is taken (and not `replace`), or a free
      library has no `track_url` rule or a licence that does not allow
      keeping the files (a ShareAlike / NoDerivatives licence, refused on
      purpose; a licence URL foley cannot read; a licence whose flags say no).
* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.music_library.titles_by_library(description, , libraries=None)

The titles a video description credits, by library (default: the registered ones).

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

* **Raises:**
  [**MusicLibraryError**](#an.music_library.MusicLibraryError) – If `text` is not JSON, or not one of those two shapes.
* **Return type:**
  [`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]]

### an.music_library.tracks_table(rows)

The tracks table as CSV text: `TRACK_COLUMNS`, then any metadata the
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
