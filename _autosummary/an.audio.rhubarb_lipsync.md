# an.audio.rhubarb_lipsync

RhubarbLipSync — calls the rhubarb-lip-sync binary for phoneme-aligned visemes.

Requires the `rhubarb` binary on PATH. macOS: `brew install rhubarb-lipsync`.
Linux/Windows: download from the project’s GitHub releases.

Falls back gracefully (raises a clear error) if the binary is missing — the
default `OfflineLipSync` keeps the pipeline functional in the meantime.

**The recognizer follows the language** (an#96, epic #9 defect 5a). Rhubarb has
two: `pocketSphinx` — its default, “use for English recordings”, the only one
that reads `--dialogFile` (it builds a dialog language model and mixes it 90/10
with the default) — and `phonetic`, “use for non-English recordings”, which
`UNUSED(dialog)``s the transcript at source. This module used to pass
``-r phonetic` **and** `--dialogFile` unconditionally: English speech from an
English transcript ran the language-independent recognizer and the transcript
it wrote to disk was never read. Now `recognizer=None` (the default) resolves
per `language` — `"en"` → `pocketSphinx` with the dialog file, anything
else → `phonetic` and **no transcript is written** (a file nothing reads is a
lie waiting for the next reader). An explicit `recognizer` still overrides.
`name` carries the recognizer so the viseme cache key changes with it and no
stale `phonetic` track replays.

### Module Attributes

| [`ENGLISH_LANGUAGES`](#an.audio.rhubarb_lipsync.ENGLISH_LANGUAGES)   | The languages `pocketSphinx` (CMU Sphinx US English acoustic model) covers.   |
|----------------------------------------------------------------------|-------------------------------------------------------------------------------|

### Functions

| [`recognizer_for`](#an.audio.rhubarb_lipsync.recognizer_for)(language)   | The Rhubarb recognizer for a BCP-47 language tag (primary subtag only).   |
|-----------------------------------------------------------------------------|---------------------------------------------------------------------------|

### Classes

| [`RhubarbLipSync`](#an.audio.rhubarb_lipsync.RhubarbLipSync)(\*[, binary_path, language, ...])   | Wrap the rhubarb CLI.   |
|-----------------------------------------------------------------------------------------------------|-------------------------|

### an.audio.rhubarb_lipsync.ENGLISH_LANGUAGES *: frozenset[str]* *= frozenset({'en'})*

The languages `pocketSphinx` (CMU Sphinx US English acoustic model) covers.

### *class* an.audio.rhubarb_lipsync.RhubarbLipSync(, binary_path=None, language='en', recognizer=None, timeout_s=60.0)

Bases: `object`

Wrap the rhubarb CLI. Implements the `LipSyncProvider` protocol.

```pycon
>>> RhubarbLipSync(binary_path="/bin/rhubarb").recognizer
'pocketSphinx'
>>> RhubarbLipSync(binary_path="/bin/rhubarb", language="de").recognizer
'phonetic'
>>> RhubarbLipSync(binary_path="/bin/rhubarb", language="de").name
'rhubarb:phonetic'
```

#### *property* uses_dialog_file *: bool*

Whether the chosen recognizer reads a transcript at all.

### an.audio.rhubarb_lipsync.recognizer_for(language)

The Rhubarb recognizer for a BCP-47 language tag (primary subtag only).

Accepts the POSIX locale spelling too (`en_US`); an empty tag is refused
rather than read as “non-English” (an#96 review).

* **Return type:**
  `str`

```pycon
>>> recognizer_for("en"), recognizer_for("en-GB"), recognizer_for("en_US"), recognizer_for("fr")
('pocketSphinx', 'pocketSphinx', 'pocketSphinx', 'phonetic')
```
