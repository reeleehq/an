# an.audio.recorded

Recorded voices: a performer’s takes as the voice of a character (an#490).

A production that records its actors has the voices already; nothing should be
synthesized, billed, or approximated. This module makes a recording a
first-class input, through the seams the audio pipeline already has:

- **The take is a voice.** [`RecordedTTS`](#an.audio.recorded.RecordedTTS) is a [`TTSProvider`](an.audio.tts.html.md#an.audio.tts.TTSProvider)
  named `recorded` whose “synthesis” is a lookup in the project’s
  `recordings` store ([`RecordingsStore`](an.stores.recordings.html.md#an.stores.recordings.RecordingsStore)). A voice
  document that declares `provider: recorded` is spoken by it (an#305), so
  takes, effects, leveling, captions, the shot cache and `an render` work
  unchanged, and nothing is billed: the provider declares `billed = False`
  and `repeatable = True`. Its `synthesis_options` hook keys each line by
  the digest of the take it has for it, so a re-recorded line is a new audio
  key, never a stale cache hit.
- **The words travel with the clip.** A take imported with a timed transcript
  (or transcribed) knows its word timings; they are stored with it, handed to
  the pipeline on [`words`](an.audio.tts.html.md#an.audio.tts.AudioClip.words), and a lip-sync
  provider that aligns from words (`cutan`’s) uses them instead of its own
  transcription — the mouth follows the performance.
- **Import** ([`import_recordings()`](#an.audio.recorded.import_recordings), `an voices import`): one or more
  audio files — a whole take with several lines, or one file per line — with an
  optional transcript (SRT, WebVTT, TextGrid, word JSON or plain text:
  [`an.audio.transcripts`](an.audio.transcripts.html.md#module-an.audio.transcripts)). Each line of the recording is cut out, matched
  > to the scene’s dialogue by its words (a line the scene does not have yet is
  > added to the shot you name), and stored with its provenance: who recorded it,
  > under which licence or permission, from which file and span. The speaker’s
  > character is bound to the recorded voice; the gap heard between two lines
  > becomes the next line’s `pause`, so the shot’s timing follows the recording.

Seams, each one keyword argument of [`import_recordings()`](#an.audio.recorded.import_recordings):

- `transcribe`: a callable `path -> segments` for a take that comes with no
  timed transcript; the default is scribed’s facade (`pip install
  "an[recorded]"`, then a backend of your choice — words and, where the
  backend has it, speakers). Not needed for one file per line or a timed
  transcript: those paths run with no model at all.
- `denoise`: off; a strategy name runs the matching ffmpeg filter
  ([`DENOISE_FILTERS`](#an.audio.recorded.DENOISE_FILTERS)) before anything else; `voxy.refprep.condition` is
  the fuller conditioning when you want more.
- Speaker attribution: `speaker` (one performer), `speakers` (a label →
  character map, for a diarizer’s or a transcript’s labels and file stems), the
  transcript’s own `speaker:` prefixes, the file’s stem, or the scene line
  the words match.

```pycon
>>> from an.audio.tts import AudioClip
>>> tts = RecordedTTS()
>>> tts.name, tts.billed, tts.repeatable
('recorded', False, True)
>>> normalize_key_text("Hello, there!") == normalize_key_text("hello there")
True
```

### Module Attributes

| [`PROVIDER_NAME`](#an.audio.recorded.PROVIDER_NAME)         | what a voice document's `provider` says.                                                                                  |
|------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| [`RECORDINGS_STORE`](#an.audio.recorded.RECORDINGS_STORE)      | The mall store the takes live in (`assets/recordings/<key>/`).                                                            |
| [`RECORDING_OPTION`](#an.audio.recorded.RECORDING_OPTION)      | The `synthesize` keyword (and audio-key option) naming the take by digest.                                                |
| [`RECORD_VERSION`](#an.audio.recorded.RECORD_VERSION)        | The shape of a record in the store; raised when a field changes meaning.                                                  |
| [`RECORDED_VOICE_SUFFIX`](#an.audio.recorded.RECORDED_VOICE_SUFFIX) | The voice document a speaker's takes are bound to, when `voice` names none.                                               |
| [`DFLT_MATCH_THRESHOLD`](#an.audio.recorded.DFLT_MATCH_THRESHOLD)  | How alike (`difflib` ratio over normalized words) a take's words and a scene line must be for the take to be that line's. |
| [`DENOISE_FILTERS`](#an.audio.recorded.DENOISE_FILTERS)       | `denoise` strategies → the ffmpeg filter that runs (voxy.refprep's table).                                                |
| [`DFLT_DENOISE`](#an.audio.recorded.DFLT_DENOISE)          | The strategy a bare request for denoising means.                                                                          |

### Functions

| [`import_recordings`](#an.audio.recorded.import_recordings)(project, audio, \*[, ...])   | Import a performer's recording(s) as the voice of their lines (an#490).                                                                                                                                                                                                                                      |
|-------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`add_recording`](#an.audio.recorded.add_recording)(store, \*, voice, speaker, ...)  | Put a take (WAV `audio` of `speaker` saying `text`, spoken for `voice`) in `store` with its provenance; `(key, record)`.                                                                                                                                                                                     |
| [`find_recording`](#an.audio.recorded.find_recording)(store, voice, text)             | The newest take of `text` for `voice` in `store`, as `(key, record)`; `None` if none.                                                                                                                                                                                                                        |
| [`recording_by_digest`](#an.audio.recorded.recording_by_digest)(store, sha256, \*[, text]) | The take whose audio has `sha256`, as `(key, record)`; `None` if none.                                                                                                                                                                                                                                       |
| [`read_recording`](#an.audio.recorded.read_recording)(store, key)                     | `(record, wav_bytes)` for `key`, the bytes checked against the record's digest.                                                                                                                                                                                                                              |
| [`recording_key`](#an.audio.recorded.recording_key)(speaker, text, sha256)           | A readable, unique store key: `<speaker>--<words>--<digest prefix>`.                                                                                                                                                                                                                                         |
| [`normalize_key_text`](#an.audio.recorded.normalize_key_text)(text)                       | The form a line's text is matched by: [`normalize_text()`](an.audio.transcripts.html.md#an.audio.transcripts.normalize_text).                                                                                                                                                                 |
| [`audio_paths`](#an.audio.recorded.audio_paths)(audio)                             | The audio files `audio` names: a file, a directory (its audio files, sorted), a glob, a comma-separated list, or a sequence of those.                                                                                                                                                                        |
| [`scribed_transcriber`](#an.audio.recorded.scribed_transcriber)([backend, diarize])        | The default transcriber: scribed's facade with word timestamps (and speaker labels when `diarize` and the backend has them).                                                                                                                                                                                 |
| [`load_wav`](#an.audio.recorded.load_wav)(path, \*[, denoise])                  | `path` as 16-bit PCM WAV bytes: a PCM WAV is taken as it is; anything else (MP3, M4A, a video's audio) is decoded with ffmpeg to mono at `IMPORT_SAMPLE_RATE`; `denoise` (a key of [`DENOISE_FILTERS`](#an.audio.recorded.DENOISE_FILTERS)) runs that filter first, which also goes through ffmpeg. |
| [`cut_wav`](#an.audio.recorded.cut_wav)(wav, start, end)                       | The frames of `wav` between `start` and `end` seconds, as a WAV of the same format.                                                                                                                                                                                                                          |
| [`wav_seconds`](#an.audio.recorded.wav_seconds)(wav)                               | The length of a PCM WAV, seconds.                                                                                                                                                                                                                                                                            |

### Classes

| [`RecordedTTS`](#an.audio.recorded.RecordedTTS)(\*[, recordings])                | The `recorded` TTS provider: a line's audio is the take imported for it.                                    |
|-----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| [`ImportedTake`](#an.audio.recorded.ImportedTake)(key, speaker, voice, text, ...) | One take the import stored, and where it went.                                                              |
| [`ImportReport`](#an.audio.recorded.ImportReport)([takes, voices, warnings])      | What [`import_recordings()`](#an.audio.recorded.import_recordings) did; `str()` is the CLI's output. |

### Exceptions

| [`RecordedVoicesError`](#an.audio.recorded.RecordedVoicesError)         | An import, or a lookup of a take, that cannot proceed; the message says what to do.   |
|------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [`RecordingMissingError`](#an.audio.recorded.RecordingMissingError)       | A line spoken by a recorded voice has no take in the store.                           |
| [`TranscriberUnavailableError`](#an.audio.recorded.TranscriberUnavailableError) | A take needs transcribing and no transcriber can run here.                            |

### an.audio.recorded.DENOISE_FILTERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'afftdn': 'afftdn', 'anlmdn': 'anlmdn'}*

`denoise` strategies → the ffmpeg filter that runs (voxy.refprep’s table).

### an.audio.recorded.DFLT_DENOISE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'afftdn'*

The strategy a bare request for denoising means.

### an.audio.recorded.DFLT_MATCH_THRESHOLD *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.75*

How alike (`difflib` ratio over normalized words) a take’s words and a
scene line must be for the take to be that line’s.

### *class* an.audio.recorded.ImportReport(takes=list(), voices=list(), warnings=list())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What [`import_recordings()`](#an.audio.recorded.import_recordings) did; `str()` is the CLI’s output.

### *class* an.audio.recorded.ImportedTake(key, speaker, voice, text, duration, source_file, span, words, line, added=False, pause=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One take the import stored, and where it went.

#### added *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

`True` when the line was ADDED to the scene by this import.

#### line *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`"<shot id>/<line index>"` of the scene line it is the audio of.

#### pause *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The `pause` written on the line from the recording, if any.

### an.audio.recorded.PROVIDER_NAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'recorded'*

what a voice document’s `provider` says.

* **Type:**
  The TTS provider’s name

### an.audio.recorded.RECORDED_VOICE_SUFFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '_recorded'*

The voice document a speaker’s takes are bound to, when `voice` names none.

### an.audio.recorded.RECORDINGS_STORE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'recordings'*

The mall store the takes live in (`assets/recordings/<key>/`).

### an.audio.recorded.RECORDING_OPTION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'recording'*

The `synthesize` keyword (and audio-key option) naming the take by digest.

### an.audio.recorded.RECORD_VERSION *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

The shape of a record in the store; raised when a field changes meaning.

### *class* an.audio.recorded.RecordedTTS(, recordings=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The `recorded` TTS provider: a line’s audio is the take imported for it.

Built by [`an.audio.providers.make_tts()`](an.audio.providers.html.md#an.audio.providers.make_tts) with the project mall, so it
reads `mall["recordings"]`; the pipeline hands it each line’s text and
voice through [`synthesis_options()`](#an.audio.recorded.RecordedTTS.synthesis_options) (which keys the line by its take’s
digest) and [`synthesize()`](#an.audio.recorded.RecordedTTS.synthesize). A line with no take raises
[`RecordingMissingError`](#an.audio.recorded.RecordingMissingError) before anything else is touched — a recorded
voice never falls back to a synthesized one.

```pycon
>>> RecordedTTS().check_available()
Traceback (most recent call last):
    ...
an.audio.recorded.RecordedVoicesError: the recorded provider has no recordings store ...
```

#### list_voices()

One entry per voice that has takes in the store.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`VoiceMeta`](an.audio.tts.html.md#an.audio.tts.VoiceMeta)]

#### repeatable *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

The same request gives the same bytes, and nothing is billed (an#311).

#### synthesis_options(voice_doc, , emotion=None, direction=None, text=None, voice_id=None)

`{"recording": <digest>}` of the take this line has — the audio key
follows the take, so a re-recorded line is new audio.

A line with no take is refused HERE, when the pipeline resolves every
line’s request before the first synthesis: nothing of the scene is
produced for a recorded voice that is missing a take. Without a line
(`an validate` asks about the voice alone) there is nothing to refuse.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

#### synthesize(text, voice_id='default', , recording=None, \*\*kw)

The take of `text` in `voice_id` (by `recording` digest when given), with its words.

* **Return type:**
  [`AudioClip`](an.audio.tts.html.md#an.audio.tts.AudioClip)

#### words_for_clip(clip)

The stored words of the take whose bytes `clip` carries, or `None`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *exception* an.audio.recorded.RecordedVoicesError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

An import, or a lookup of a take, that cannot proceed; the message says what to do.

### *exception* an.audio.recorded.RecordingMissingError

Bases: [`RecordedVoicesError`](#an.audio.recorded.RecordedVoicesError)

A line spoken by a recorded voice has no take in the store.

### *exception* an.audio.recorded.TranscriberUnavailableError

Bases: [`RecordedVoicesError`](#an.audio.recorded.RecordedVoicesError)

A take needs transcribing and no transcriber can run here.

### an.audio.recorded.add_recording(store, , voice, speaker, text, audio, source, words=None, imported_at=None)

Put a take (WAV `audio` of `speaker` saying `text`, spoken for
`voice`) in `store` with its provenance; `(key, record)`.

`source` is required: a recording with no recorded origin is exactly the
asset `an credits` cannot vouch for.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### an.audio.recorded.audio_paths(audio)

The audio files `audio` names: a file, a directory (its audio files,
sorted), a glob, a comma-separated list, or a sequence of those.

```pycon
>>> audio_paths([])
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### an.audio.recorded.cut_wav(wav, start, end)

The frames of `wav` between `start` and `end` seconds, as a WAV of the same format.

```pycon
>>> import struct
>>> buf = io.BytesIO()
>>> with wave.open(buf, "wb") as w:
...     w.setnchannels(1); w.setsampwidth(2); w.setframerate(100)
...     w.writeframes(struct.pack("<100h", *range(100)))
>>> round(wav_seconds(cut_wav(buf.getvalue(), 0.25, 0.5)), 2)
0.25
```

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.audio.recorded.find_recording(store, voice, text)

The newest take of `text` for `voice` in `store`, as `(key, record)`; `None` if none.

Texts are compared normalized (case and punctuation aside), so a comma
added in `scene.md` does not orphan the take.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.recorded.import_recordings(project, audio, , transcript=None, speaker=None, speakers=None, shot=None, voice=None, denoise=None, license=None, recorded_by=None, transcribe=None, transcriber=None, diarize=False, match_threshold=0.75, write=True)

Import a performer’s recording(s) as the voice of their lines (an#490).

`audio` names the takes (a file, several, a directory, a glob): a whole
take holding several lines, or one file per line. `transcript` is
optional: SRT, WebVTT, TextGrid or word JSON time the lines so nothing is
transcribed; a plain transcript (`speaker: text` lines) pairs one line per
file, or is timed against `transcribe`’s words for a whole take; with no
transcript at all the take is transcribed and its segments are the lines.

Each line is cut out, matched to the scene’s dialogue by its words
(`match_threshold`), stored in `mall["recordings"]` with its provenance
(`license` is required: the code you vouch for; `recorded_by` names the
performer), and the speaker’s character is bound to a recorded voice
document (`voice`, default `<speaker>_recorded`). Takes matching no line
are added to `shot` (or the first shot of a scene with no dialogue). The
gap heard between two lines of one file becomes the later line’s `pause`.

`denoise` (`"afftdn"` / `"anlmdn"`) cleans each file first, through
ffmpeg. `transcribe` is the transcriber seam (`path -> segments`); its
default is [`scribed_transcriber()`](#an.audio.recorded.scribed_transcriber) with `transcriber` as the backend
and `diarize` for speaker labels, built only when a take needs it.
`write=False` runs everything but writes nothing (a dry run).

* **Return type:**
  [`ImportReport`](#an.audio.recorded.ImportReport)

### an.audio.recorded.load_wav(path, , denoise=None)

`path` as 16-bit PCM WAV bytes: a PCM WAV is taken as it is; anything
else (MP3, M4A, a video’s audio) is decoded with ffmpeg to mono at
`IMPORT_SAMPLE_RATE`; `denoise` (a key of [`DENOISE_FILTERS`](#an.audio.recorded.DENOISE_FILTERS))
runs that filter first, which also goes through ffmpeg.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.audio.recorded.normalize_key_text(text)

The form a line’s text is matched by: [`normalize_text()`](an.audio.transcripts.html.md#an.audio.transcripts.normalize_text).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.recorded.read_recording(store, key)

`(record, wav_bytes)` for `key`, the bytes checked against the record’s digest.

The licence is attached to the digest: different bytes under the key are a
take nobody vouched for, and are refused.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]

### an.audio.recorded.recording_by_digest(store, sha256, , text=None)

The take whose audio has `sha256`, as `(key, record)`; `None` if none.

The same bytes may be stored under two records (a take re-imported with its
text corrected): `text` picks the record whose text it is, so the line
gets its own words.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.recorded.recording_key(speaker, text, sha256)

A readable, unique store key: `<speaker>--<words>--<digest prefix>`.

```pycon
>>> recording_key("carl", "Hello, there!", "1a2b3c4d5e6f")
'carl--hello-there--1a2b3c4d'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.recorded.scribed_transcriber(backend=None, , diarize=False)

The default transcriber: scribed’s facade with word timestamps (and
speaker labels when `diarize` and the backend has them). The import is
lazy: a take with a timed transcript never needs it.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)], [`Sequence`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)[[`TranscriptSegment`](an.audio.transcripts.html.md#an.audio.transcripts.TranscriptSegment)]]

### an.audio.recorded.wav_seconds(wav)

The length of a PCM WAV, seconds.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)
