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
  `"unknown"` says so explicitly (the sound is then UNVERIFIED).

```pycon
>>> fetched = Fetched(audio=b"...", url="https://example.org/a", id="a", author="Ann")
>>> fetched.provider
'web'
```

### Module Attributes

| [`Fetcher`](#an.sound_fetch.Fetcher)   | how [`add_sound_from_url()`](#an.sound_fetch.add_sound_from_url) gets the media.   |
|------------------------------------------------------------|---------------------------------------------------------------------------------------------|

### Functions

| [`add_sound_from_url`](#an.sound_fetch.add_sound_from_url)(store, key, url, \*, license)   | Fetch `url`, cut it, and put it in the sounds `store` under `key` with its provenance.   |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| [`cut_to_wav`](#an.sound_fetch.cut_to_wav)(audio, \*[, start, duration, fade_out]) | `audio` (any container ffmpeg reads) cut to `[start, start + duration]`, as 16-bit WAV.  |
| [`yb_fetcher`](#an.sound_fetch.yb_fetcher)(url)                                    | Fetch the audio of `url` with `yb` (any site its `yt-dlp` reads).                        |

### Classes

| [`Fetched`](#an.sound_fetch.Fetched)(audio, url[, id, title, author, ...])   | What a fetcher returns: the media's bytes, and what its page says about it.   |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|

### *class* an.sound_fetch.Fetched(audio, url, id=None, title=None, author=None, provider='web')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a fetcher returns: the media’s bytes, and what its page says about it.

#### provider *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'web'*

Where it came from, as an `AssetSource.provider` (`youtube`, …).

### an.sound_fetch.Fetcher

how [`add_sound_from_url()`](#an.sound_fetch.add_sound_from_url) gets the media.

* **Type:**
  `(url) -> Fetched`

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Fetched`](#an.sound_fetch.Fetched)]

### an.sound_fetch.add_sound_from_url(store, key, url, , license, fetcher=None, start=None, duration=None, fade_out=None, provider=None, author=None, description='')

Fetch `url`, cut it, and put it in the sounds `store` under `key` with its provenance.

* **Return type:**
  [`SoundAsset`](an.sounds.html.md#an.sounds.SoundAsset)

license: the licence code the caller vouches for — required, never
: guessed; `"unknown"` (or `None`) records that nobody has said

fetcher: `(url) -> Fetched` (default [`yb_fetcher()`](#an.sound_fetch.yb_fetcher))
start, duration, fade_out: the cut, in seconds of the fetched media
provider, author: override what the fetcher reported

### an.sound_fetch.cut_to_wav(audio, , start=None, duration=None, fade_out=None)

`audio` (any container ffmpeg reads) cut to `[start, start + duration]`, as 16-bit WAV.

`fade_out`: seconds of linear fade at the end of the cut.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.sound_fetch.yb_fetcher(url)

Fetch the audio of `url` with `yb` (any site its `yt-dlp` reads).

* **Return type:**
  [`Fetched`](#an.sound_fetch.Fetched)
