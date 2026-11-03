# an.sound_fetch

Add a sound from a URL, with its provenance and the cut taken (an#318).

A production that sources its music or an effect from the web used to write
the same script each time: download, cut with ffmpeg, type an `AssetSource`
by hand, [`an.sounds.add_sound()`](an.sounds.html.md#an.sounds.add_sound). [`add_sound_from_url()`](#an.sound_fetch.add_sound_from_url) is that script:

- the download is a seam, `fetcher=`: any `(url) -> Fetched` (the bytes in
  any container ffmpeg reads, and what the source says about itself). The
  default, [`yb_fetcher()`](#an.sound_fetch.yb_fetcher), uses [yb](https://github.com/thorwhalen/yb)
  when it is installed (`pip install yb` with its `yt-dlp` extra); it is
  never a dependency of `an`. Another ingest (braidio’s) plugs in here;
- the cut (`start`, `duration`, `fade_out`) is made by ffmpeg into a
  16-bit WAV, and recorded with the source, so `an credits` says which part
  of which page it is (“0:07.9–0:08.8 of <url>”);
- the licence is the caller’s statement, never guessed: required, and
  `"unknown"` says so explicitly (the sound is then UNVERIFIED) – unless the
  source states its own rights ([`Fetched.source`](#an.sound_fetch.Fetched.source)). A sound from a foley
  library does (an#729): [`foley_fetcher()`](#an.sound_fetch.foley_fetcher) reads `foley:<sound_id>` through
  `foley.export_sound`, whose rights become the sound’s
  [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource) ([`foley_asset_source()`](#an.sound_fetch.foley_asset_source), with foley’s
  > whole provenance as `foley_provenance`), so the licence may be omitted, and
  > a caller’s licence that disagrees is refused. A fetcher says which refs it
  > states rights for ([`fetcher_states_rights()`](#an.sound_fetch.fetcher_states_rights)), so a licence missing for
  > any other is refused before anything is downloaded. The default fetcher
  > ([`default_fetcher()`](#an.sound_fetch.default_fetcher)) sends a `foley:` ref to foley and anything else to
  > `yb`, so `an sounds add <project> door foley:fsd-222` works.

```pycon
>>> fetched = Fetched(audio=b"...", url="https://example.org/a", id="a", author="Ann")
>>> fetched.provider
'web'
```

### Module Attributes

| [`UNSTATED`](#an.sound_fetch.UNSTATED)   | the caller states no licence, which only a source that states its own rights ([`Fetched.source`](#an.sound_fetch.Fetched.source)) may do.   |
|-------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Fetcher`](#an.sound_fetch.Fetcher)    | how [`add_sound_from_url()`](#an.sound_fetch.add_sound_from_url) gets the media.                                                                |

### Functions

| [`add_sound_from_url`](#an.sound_fetch.add_sound_from_url)(store, key, url, \*[, ...])     | Fetch `url`, cut it, and put it in the sounds `store` under `key` with its provenance.                                                                                                                                                       |
|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`ai_label`](#an.sound_fetch.ai_label)(source)                                   | What an AI-generated source's disclosure says, or `None` for any other.                                                                                                                                                                      |
| [`cut_to_wav`](#an.sound_fetch.cut_to_wav)(audio, \*[, start, duration, fade_out]) | `audio` (any container ffmpeg reads) cut to `[start, start + duration]`, as 16-bit WAV.                                                                                                                                                      |
| [`default_fetcher`](#an.sound_fetch.default_fetcher)(url)                               | The default `fetcher=`: [`foley_fetcher()`](#an.sound_fetch.foley_fetcher) for a `foley:` ref, else [`yb_fetcher()`](#an.sound_fetch.yb_fetcher).                                                             |
| [`fetcher_states_rights`](#an.sound_fetch.fetcher_states_rights)(fetcher, url)                | Whether `fetcher` declares that its source states the rights of `url`.                                                                                                                                                                       |
| [`file_digest_fields`](#an.sound_fetch.file_digest_fields)(fields)                         | `fields` with `sha256` (the fetched or library file's) moved to `FILE_SHA256_FIELD`: a stored sound is the cut WAV, whose digest is the [`SoundAsset`](an.sounds.html.md#an.sounds.SoundAsset)'s (an#623, an#729). |
| [`foley_asset_source`](#an.sound_fetch.foley_asset_source)(rights, provenance, \*[, url])  | foley's `(rights, provenance)` (`foley.export_sound`) as an `AssetSource`.                                                                                                                                                                   |
| [`foley_fetcher`](#an.sound_fetch.foley_fetcher)(ref, \*[, export])                   | Fetch `foley:<sound_id>` from a foley library, with the rights foley records.                                                                                                                                                                |
| [`notice_label`](#an.sound_fetch.notice_label)(source)                               | The notice a source's licence requires shown verbatim, or `None`.                                                                                                                                                                            |
| [`yb_fetcher`](#an.sound_fetch.yb_fetcher)(url)                                    | Fetch the audio of `url` with `yb` (any site its `yt-dlp` reads).                                                                                                                                                                            |

### Classes

| [`Fetched`](#an.sound_fetch.Fetched)(audio, url[, id, title, author, ...])   | What a fetcher returns: the media's bytes, and what its page says about it.                 |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`Unstated`](#an.sound_fetch.Unstated)(\*values)                              | The type of [`UNSTATED`](#an.sound_fetch.UNSTATED), `license=` left out. |

### *class* an.sound_fetch.Fetched(audio, url, id=None, title=None, author=None, provider='web', source=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a fetcher returns: the media’s bytes, and what its page says about it.

When `source` is set it is the sound’s whole provenance (the rights the
source states), and `id`, `title`, `author` and `provider` are not
read; otherwise they are, with the caller’s licence.

#### provider *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'web'*

Where it came from, as an `AssetSource.provider` (`youtube`, …).

#### source *: [AssetSource](an.ir.assets.html.md#an.ir.assets.AssetSource) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The rights the source itself states (a foley library’s export), or
`None`: then the licence is the caller’s statement.

### an.sound_fetch.Fetcher

how [`add_sound_from_url()`](#an.sound_fetch.add_sound_from_url) gets the media. A
fetcher whose source states its own rights for some refs says which with a
`states_rights(url) -> bool` attribute ([`fetcher_states_rights()`](#an.sound_fetch.fetcher_states_rights)).

* **Type:**
  `(url) -> Fetched`

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Fetched`](#an.sound_fetch.Fetched)]

### an.sound_fetch.UNSTATED *= Unstated.UNSTATED*

the caller states no licence, which only a source that
states its own rights ([`Fetched.source`](#an.sound_fetch.Fetched.source)) may do.

* **Type:**
  `license=` left out

### *class* an.sound_fetch.Unstated(\*values)

Bases: [`Enum`](https://docs.python.org/3/library/enum.html#enum.Enum)

The type of [`UNSTATED`](#an.sound_fetch.UNSTATED), `license=` left out.

### an.sound_fetch.add_sound_from_url(store, key, url, , license=Unstated.UNSTATED, fetcher=None, start=None, duration=None, fade_out=None, provider=None, author=None, description='')

Fetch `url`, cut it, and put it in the sounds `store` under `key` with its provenance.

license: the licence code the caller vouches for, never guessed;
: `"unknown"` (or `None`) records that nobody has said. Required
  unless the source states its own rights ([`Fetched.source`](#an.sound_fetch.Fetched.source), a
  `foley:` sound), which are then recorded; a licence given with them
  must agree

fetcher: `(url) -> Fetched` (default [`default_fetcher()`](#an.sound_fetch.default_fetcher): a
: `foley:<sound_id>` ref from foley, anything else with `yb`)

start, duration, fade_out: the cut, in seconds of the fetched media
provider, author: override what the fetcher reported (never on a source

> that states its rights)

No cut is recorded when the whole media is kept (no `start`,
`duration` or `fade_out`).

* **Raises:**
  [**SoundError**](an.sounds.html.md#an.sounds.SoundError) – For no licence for a ref the fetcher states no rights for
      (before anything is fetched: [`fetcher_states_rights()`](#an.sound_fetch.fetcher_states_rights)), or from
      a source that turned out to state none; a caller’s licence that
      contradicts the source’s, or a provider or author set over it; and
      whatever the fetch, the cut or the store refuse.
* **Return type:**
  [`SoundAsset`](an.sounds.html.md#an.sounds.SoundAsset)

### an.sound_fetch.ai_label(source)

What an AI-generated source’s disclosure says, or `None` for any other.

The model; whether the disclosure is a duty (a recognizable voice: “must be
disclosed”) or a recommendation; and, when foley’s EU AI Act Art. 50
checklist is not `publish_ready`, the obligations still pending.

```pycon
>>> ai = {"is_ai_generated": True, "publish_ready": False,
...       "pending": ["machine_readable_mark", "provenance_manifest"],
...       "obligations": {"voice_disclosure": {"required": False}},
...       "provenance": {"generator_model": "stable-audio-open-1.0"}}
>>> ai_label(AssetSource(provider="stability-ai", foley_provenance={"ai_disclosure": ai}))
'AI-generated with stable-audio-open-1.0: disclosure recommended; not publish-ready, Art. 50 pending: machine_readable_mark, provenance_manifest'
>>> ai_label(AssetSource(provider="fsd50k")) is None
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.sound_fetch.cut_to_wav(audio, , start=None, duration=None, fade_out=None)

`audio` (any container ffmpeg reads) cut to `[start, start + duration]`, as 16-bit WAV.

`fade_out`: seconds of linear fade at the end of the cut.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.sound_fetch.default_fetcher(url)

The default `fetcher=`: [`foley_fetcher()`](#an.sound_fetch.foley_fetcher) for a `foley:` ref, else [`yb_fetcher()`](#an.sound_fetch.yb_fetcher).

* **Return type:**
  [`Fetched`](#an.sound_fetch.Fetched)

### an.sound_fetch.fetcher_states_rights(fetcher, url)

Whether `fetcher` declares that its source states the rights of `url`.

Read from its `states_rights(url)` attribute (a `functools.partial` of a
fetcher keeps the declaration); a fetcher without one states none.

```pycon
>>> fetcher_states_rights(default_fetcher, "foley:fsd-222")
True
>>> fetcher_states_rights(default_fetcher, "https://youtu.be/x"), fetcher_states_rights(print, "x")
(False, False)
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.sound_fetch.file_digest_fields(fields)

`fields` with `sha256` (the fetched or library file’s) moved to
`FILE_SHA256_FIELD`: a stored sound is the cut WAV, whose digest is the
[`SoundAsset`](an.sounds.html.md#an.sounds.SoundAsset)’s (an#623, an#729).

```pycon
>>> file_digest_fields({"provider": "p", "sha256": "ab"})
{'provider': 'p', 'file_sha256': 'ab'}
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.sound_fetch.foley_asset_source(rights, provenance, , url=None)

foley’s `(rights, provenance)` (`foley.export_sound`) as an `AssetSource`.

`rights` is keyed by the source’s own field names (foley pins them to
`lacing.Rights`, an’s `AssetSource`); its `title` rides as an extra.
`sha256` is the exported bytes’ digest, and the whole `provenance`
(JSON-safe) rides as `FOLEY_PROVENANCE_FIELD`. `url` is where the
bytes came from (`foley:<sound_id>`).

```pycon
>>> src = foley_asset_source(
...     {"provider": "fsd50k", "id": "222", "title": "Door creak", "license": "cc-by-4.0",
...      "attribution": "Door creak by amy", "author": None},
...     {"sha256": "ab", "archived_sha256": "cd", "ai_disclosure": None}, url="foley:fsd-222")
>>> src.provider, src.license, src.url, src.author, src.sha256
('fsd50k', 'cc-by-4.0', 'foley:fsd-222', None, 'ab')
>>> src.model_extra["title"], src.model_extra["foley_provenance"]["archived_sha256"]
('Door creak', 'cd')
```

* **Return type:**
  [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource)

### an.sound_fetch.foley_fetcher(ref, , export=None)

Fetch `foley:<sound_id>` from a foley library, with the rights foley records.

export: `(sound_id) -> (bytes, rights, provenance)`, default
: `foley.export_sound` (its default library; bind another with
  `functools.partial(foley.export_sound, library=...)`). foley is
  imported on first use: `import an` never imports it.

The bytes are checked against the digest foley’s provenance names, and the
rights become [`Fetched.source`](#an.sound_fetch.Fetched.source) ([`foley_asset_source()`](#an.sound_fetch.foley_asset_source)), the
sound’s only rights. It states rights for every `foley:` ref
(`foley_fetcher.states_rights`).

* **Raises:**
  [**SoundError**](an.sounds.html.md#an.sounds.SoundError) – For a ref that is not `foley:<sound_id>`, foley not
      installed, a sound foley does not hold or will not export (its
      terms forbid keeping the bytes: a Freesound API pull is stored by
      reference; its bytes changed since ingest; a failed re-encode),
      naming the ref and foley’s reason, or bytes that do not match the
      digest foley names.
* **Return type:**
  [`Fetched`](#an.sound_fetch.Fetched)

### an.sound_fetch.notice_label(source)

The notice a source’s licence requires shown verbatim, or `None`.

```pycon
>>> notice_label(AssetSource(provider="p", foley_provenance={"notice_text_required": "(c) X"}))
'(c) X'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.sound_fetch.yb_fetcher(url)

Fetch the audio of `url` with `yb` (any site its `yt-dlp` reads).

* **Return type:**
  [`Fetched`](#an.sound_fetch.Fetched)
