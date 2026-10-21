# an.stores.recordings

Recordings store — one directory per recorded take: `recording.json` beside `audio.wav`.

A recording is a performer’s take of one dialogue line, imported from an audio
file (`an voices import`, [`an.audio.recorded`](an.audio.recorded.html.md#module-an.audio.recorded)). Like a sound, it is bytes
that end up in a film a user ships, so its record carries provenance and rights
(`source`, an [`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource): who recorded it, under which
licence or permission, from which file and span) and the digest of the bytes the
licence is attached to; `an credits` walks this store like the others. The
record also says which voice and line the take belongs to and, when they are
known, the words it contains and when ([`an.audio.recorded.RECORD_VERSION`](an.audio.recorded.html.md#an.audio.recorded.RECORD_VERSION)
names the shape).

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     store = RecordingsStore(d)
...     store['carl--hello--1a2b3c4d'] = {'voice': 'carl_recorded', 'text': 'Hello.'}
...     store.write_audio('carl--hello--1a2b3c4d', b'RIFF....')
...     store['carl--hello--1a2b3c4d']['text'], store.read_audio('carl--hello--1a2b3c4d')
('Hello.', b'RIFF....')
```

### Classes

| [`RecordingsStore`](#an.stores.recordings.RecordingsStore)(root_dir)   | Per-take directory store: `<key>/recording.json` + `<key>/audio.wav`.   |
|------------------------------------------------------------------------------|-------------------------------------------------------------------------|

### *class* an.stores.recordings.RecordingsStore(root_dir)

Bases: `AudioSidecarStore`

Per-take directory store: `<key>/recording.json` + `<key>/audio.wav`.

#### ENTRY_NOUN *= 'recording'*

What an entry is called in error messages.
