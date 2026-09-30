# an.sounds

Sound assets: what the sound layer plays, where it came from, and a synthesizer.

A [`an.ir.schema.SoundCue`](an.ir.schema.html.md#an.ir.schema.SoundCue) names a key in the project’s `sounds` store;
this module is the typed front door to that store. Every sound carries an
[`AssetSource`](an.ir.assets.html.md#an.ir.assets.AssetSource) — provenance and licence — and the sha256 of
the bytes that licence is attached to, because a sound is third-party work far
more often than a character is, and \*\*a licence recorded and never displayed is
not compliance\*\*: `an credits` walks this store like the others.

```pycon
>>> import tempfile
>>> from an.stores.sounds import SoundsStore
>>> with tempfile.TemporaryDirectory() as d:
...     store = SoundsStore(d)
...     asset = add_sound(store, "beep", synth_tone(440.0, 0.25), source=SYNTH_SOURCE)
...     asset.duration, get_sound(store, "beep")[1][:4]
(0.25, b'RIFF')
```

**The film mix is mono at 44.1 kHz** (the per-shot audio’s format), so a
stereo asset is mixed down. **v1 stores WAV (PCM) only.** The mix needs each asset’s exact length to place
a fade-out, and a WAV header states it without decoding anything; convert other
formats with ffmpeg before adding them.

The synthesizers ([`synth_tone()`](#an.sounds.synth_tone), [`synth_hit()`](#an.sounds.synth_hit), [`synth_bed()`](#an.sounds.synth_bed)) are
what the demo and the tests use instead of shipping any third-party audio: pure
numpy, seeded, so the same call writes the same bytes.

### Module Attributes

| [`SYNTH_SOURCE`](#an.sounds.SYNTH_SOURCE)   | The provenance of everything [`synth_tone()`](#an.sounds.synth_tone) / [`synth_hit()`](#an.sounds.synth_hit) / [`synth_bed()`](#an.sounds.synth_bed) produce: generated on the user's machine by `an` from numbers, so no third party's work is in it.   |
|-----------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`add_sound`](#an.sounds.add_sound)(store, key, audio, \*, source[, ...])    | Put `audio` (WAV bytes) in `store` under `key`, with its provenance.     |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`get_sound`](#an.sounds.get_sound)(store, key)                              | `(asset, wav_bytes)` for `key`, the bytes checked against the digest.    |
| [`synth_bed`](#an.sounds.synth_bed)(duration, \*[, chord, pulse_hz, ...])    | A music bed: a sustained chord with a gentle pulse, loopable end to end. |
| [`synth_hit`](#an.sounds.synth_hit)([duration, seed, thump_hz, decay, ...])  | A percussive hit: a seeded noise burst over a low thump, decaying fast.  |
| [`synth_tone`](#an.sounds.synth_tone)(freq, duration, \*[, sample_rate, ...]) | A sine at `freq` Hz, with short linear ramps so it does not click.       |
| [`wav_info`](#an.sounds.wav_info)(data)                                     | `(sample_rate, channels, frames)` from a WAV's header.                   |

### Classes

| [`SoundAsset`](#an.sounds.SoundAsset)(\*\*data)   | The `sound.json` of one entry in the `sounds` store.   |
|-------------------------------------------------------------------------|--------------------------------------------------------|

### Exceptions

| [`SoundError`](#an.sounds.SoundError)   | A sound the store cannot hold, or holds wrongly.   |
|---------------------------------------------------------------|----------------------------------------------------|

### an.sounds.SYNTH_SOURCE *= AssetSource(provider='an.sounds', id='procedural-synthesis', url=None, license='cc0-1.0', license_url=None, attribution=None, source_page_url=None, author='an (procedural synthesis, generated locally)', author_url=None, cacheable=True, sha256=None, cost_usd=None, extra={})*

The provenance of everything [`synth_tone()`](#an.sounds.synth_tone) / [`synth_hit()`](#an.sounds.synth_hit) /
[`synth_bed()`](#an.sounds.synth_bed) produce: generated on the user’s machine by `an` from
numbers, so no third party’s work is in it.

### *class* an.sounds.SoundAsset(\*\*data)

Bases: `BaseModel`

The `sound.json` of one entry in the `sounds` store.

#### duration *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Seconds, from the WAV header.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### sha256 *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Digest of `audio.wav` as it entered the project; checked on every read.

### *exception* an.sounds.SoundError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A sound the store cannot hold, or holds wrongly.

### an.sounds.add_sound(store, key, audio, , source, description='')

Put `audio` (WAV bytes) in `store` under `key`, with its provenance.

`source` is required: a sound with no recorded origin is exactly the
asset `an credits` cannot vouch for. Its `license` may be `None` —
that is recorded as UNKNOWN and reported as unverified, never as free.

* **Return type:**
  [`SoundAsset`](#an.sounds.SoundAsset)

### an.sounds.get_sound(store, key)

`(asset, wav_bytes)` for `key`, the bytes checked against the digest.

A mismatch raises: the licence is attached to the digest, so different
bytes under the same key are an asset nobody recorded.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`SoundAsset`](#an.sounds.SoundAsset), [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]

### an.sounds.synth_bed(duration, , chord=(220.0, 277.18, 329.63), pulse_hz=2.0, sample_rate=44100, amplitude=0.3)

A music bed: a sustained chord with a gentle pulse, loopable end to end.

The pulse is a whole number of cycles over `duration` when
`duration * pulse_hz` is whole, so a looped bed does not bump at the seam.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

```pycon
>>> len(synth_bed(1.0)) > 44 and synth_bed(1.0) == synth_bed(1.0)
True
```

### an.sounds.synth_hit(duration=0.35, , seed=0, thump_hz=90.0, decay=0.06, sample_rate=44100, amplitude=0.6)

A percussive hit: a seeded noise burst over a low thump, decaying fast.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

```pycon
>>> synth_hit(seed=1) == synth_hit(seed=1), synth_hit(seed=1) == synth_hit(seed=2)
(True, False)
```

### an.sounds.synth_tone(freq, duration, , sample_rate=44100, amplitude=0.3, attack=0.005, release=0.02)

A sine at `freq` Hz, with short linear ramps so it does not click.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

```pycon
>>> synth_tone(440.0, 0.1) == synth_tone(440.0, 0.1)
True
```

### an.sounds.wav_info(data)

`(sample_rate, channels, frames)` from a WAV’s header.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]

```pycon
>>> wav_info(synth_tone(440.0, 0.5, sample_rate=8000))
(8000, 1, 4000)
```
