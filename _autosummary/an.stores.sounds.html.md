# an.stores.sounds

Sounds store — one directory per sound: `sound.json` beside `audio.wav`.

A sound is an asset like a character or a prop: bytes that end up in a video a
user ships, so it carries its provenance and licence (`source`, an
`an.ir.assets.AssetSource`) and the digest of the bytes the licence is attached
to. The metadata is the mapping’s value; the audio is a sidecar read and written
through `SoundsStore.read_audio()` / `SoundsStore.write_audio()`, so no
caller builds a path by hand (pillar 7). `an.sounds` is the typed front door.

### Classes

| [`SoundsStore`](#an.stores.sounds.SoundsStore)(root_dir)   | Per-sound directory store.   |
|--------------------------------------------------------------------------|------------------------------|

### *class* an.stores.sounds.SoundsStore(root_dir)

Bases: `JsonSidecarStore`

Per-sound directory store.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     store = SoundsStore(d)
...     store['hit'] = {'description': 'a stick on a table'}
...     store.write_audio('hit', b'RIFF....')
...     store['hit']['description'], store.read_audio('hit')
('a stick on a table', b'RIFF....')
```

#### AUDIO_NAME *= 'audio.wav'*

`an.sounds` reads
its header for the duration a fade-out needs, deterministically.

* **Type:**
  The sidecar holding the audio bytes. WAV only in v1
