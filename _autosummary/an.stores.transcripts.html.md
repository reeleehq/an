# an.stores.transcripts

Transcripts as linked artifacts in the project store (an#493).

A transcript an earlier step produced (a speech-to-text pass, a script
export, a hand-timed SRT) is kept in the mall’s `transcripts` store, a
`lacing.ArtifactStore` (`catalog/<key>.json` + `blobs/<sha256>`, the
layout of the shot cache), so a later step can name it instead of a file:
`an voices import <dir> takes/ --transcript artifact:transcripts/<key>`
([`an.audio.recorded.import_recordings()`](an.audio.recorded.html.md#an.audio.recorded.import_recordings)), and the take’s provenance
points at the artifact it was cut by, content included
(`transcripts/<key>@<sha256>`: a key re-recorded later names other bytes).
The transcript’s format rides in the record’s `mime` ([`FORMAT_MIME`](#an.stores.transcripts.FORMAT_MIME)).
A transcript is a document the takes are cut BY, before any take exists and
often covering several, so it is its own store rather than a sidecar of a
recording.

```pycon
>>> store = in_memory_transcripts_store()
>>> art = record_transcript(store, "take1", "1\n00:00:00,000 --> 00:00:01,000\nHello.\n")
>>> art.mime, art.kind
('application/x-subrip', 'text')
>>> linked = linked_transcript("artifact:transcripts/take1", {"transcripts": store})
>>> linked.fmt, linked.ref == f"transcripts/take1@{art.asset_id}", linked.text.splitlines()[2]
('srt', True, 'Hello.')
```

### Module Attributes

| [`TRANSCRIPTS_STORE`](#an.stores.transcripts.TRANSCRIPTS_STORE)   | The mall key of the transcripts store.                                                                                                                                                                                                                     |
|----------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`ARTIFACT_REF_PREFIX`](#an.stores.transcripts.ARTIFACT_REF_PREFIX) | How a transcript artifact is named where a path is expected: `artifact:<store>/<key>`, or `artifact:<key>` in [`TRANSCRIPTS_STORE`](#an.stores.transcripts.TRANSCRIPTS_STORE) (reelee's `artifact:<id>` spelling, with the store an#493 adds in front). |
| [`FORMAT_MIME`](#an.stores.transcripts.FORMAT_MIME)         | The media type each transcript format is recorded under (and read back from).                                                                                                                                                                              |

### Functions

| [`in_memory_transcripts_store`](#an.stores.transcripts.in_memory_transcripts_store)()                   | A transcripts store held in dicts: for tests, and a mall with no disk.                                                                                                                                                                                                                                                                                       |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`is_artifact_ref`](#an.stores.transcripts.is_artifact_ref)(item)                           | Whether `item` names a transcript artifact: an `artifact:` reference or a `lacing.Artifact`.                                                                                                                                                                                                                                                                 |
| [`linked_transcript`](#an.stores.transcripts.linked_transcript)(item, mall, \*[, store_name]) | The transcript `item` names: `artifact:[<store>/]<key>[@<sha256>]` ([`parse_artifact_ref()`](#an.stores.transcripts.parse_artifact_ref)), or a `lacing.Artifact` (filed in `store_name`), read through `mall`.                                                                                                                                             |
| [`orphan_transcript_blobs`](#an.stores.transcripts.orphan_transcript_blobs)(store, \*[, named])     | The transcript contents of `store` that no catalog record and nothing in `named` (the pins a take's provenance records, an#607) names: what re-recording a key left behind.                                                                                                                                                                                  |
| [`parse_artifact_ref`](#an.stores.transcripts.parse_artifact_ref)(ref, mall, \*[, store_name]) | `(store, key, pin)` of `artifact:[<store>/]<key>[@<sha256>]` (an#607): the first segment names a store of `mall` when it is one that holds the key (else the whole name is a key of `store_name`, so a transcript keyed `takes/a` is found though the mall has a `takes` store); `pin` is the content a recorded reference names, `None` when it names none. |
| [`pin_of`](#an.stores.transcripts.pin_of)(reference)                               | The content digest a recorded reference pins (`<store>/<key>@<sha256>`).                                                                                                                                                                                                                                                                                     |
| [`record_transcript`](#an.stores.transcripts.record_transcript)(store, key, text, \*[, ...])  | Keep `text` (a transcript, or a `Path` to one; its format detected, a file's suffix first, unless `fmt` says) in `store` under `key`; return its `lacing.Artifact`.                                                                                                                                                                                          |
| [`transcripts_store`](#an.stores.transcripts.transcripts_store)(root)                         | A filesystem transcripts store under `root` (lacing's layout).                                                                                                                                                                                                                                                                                               |

### Classes

| [`LinkedTranscript`](#an.stores.transcripts.LinkedTranscript)(text, fmt, ref)   | A transcript read out of the store: its text, its format, and the reference that names it with its content (`<store>/<key>@<sha256>`).   |
|-------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|

### Exceptions

| [`TranscriptCatalogUnreadable`](#an.stores.transcripts.TranscriptCatalogUnreadable)   | A transcripts catalog record cannot be read: what it names is unknown, so nothing can be said to be named by nothing (an#607).   |
|--------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| [`TranscriptLinkError`](#an.stores.transcripts.TranscriptLinkError)           | A transcript artifact that cannot be found or read.                                                                              |

### an.stores.transcripts.ARTIFACT_REF_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'artifact:'*

How a transcript artifact is named where a path is expected:
`artifact:<store>/<key>`, or `artifact:<key>` in [`TRANSCRIPTS_STORE`](#an.stores.transcripts.TRANSCRIPTS_STORE)
(reelee’s `artifact:<id>` spelling, with the store an#493 adds in front).

### an.stores.transcripts.FORMAT_MIME *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'json': 'application/json', 'plain': 'text/plain', 'srt': 'application/x-subrip', 'textgrid': 'text/x-praat-textgrid', 'vtt': 'text/vtt'}*

The media type each transcript format is recorded under (and read back from).

### *class* an.stores.transcripts.LinkedTranscript(text, fmt, ref)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A transcript read out of the store: its text, its format, and the
reference that names it with its content (`<store>/<key>@<sha256>`).

### an.stores.transcripts.TRANSCRIPTS_STORE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'transcripts'*

The mall key of the transcripts store.

### *exception* an.stores.transcripts.TranscriptCatalogUnreadable

Bases: [`TranscriptLinkError`](#an.stores.transcripts.TranscriptLinkError)

A transcripts catalog record cannot be read: what it names is unknown,
so nothing can be said to be named by nothing (an#607).

### *exception* an.stores.transcripts.TranscriptLinkError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A transcript artifact that cannot be found or read.

### an.stores.transcripts.in_memory_transcripts_store()

A transcripts store held in dicts: for tests, and a mall with no disk.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.stores.transcripts.is_artifact_ref(item)

Whether `item` names a transcript artifact: an `artifact:` reference
or a `lacing.Artifact`.

```pycon
>>> is_artifact_ref("artifact:transcripts/t"), is_artifact_ref("take.srt")
(True, False)
>>> is_artifact_ref("artifact: Hello there.")   # a plain transcript's speaker
False
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.stores.transcripts.linked_transcript(item, mall, , store_name='transcripts')

The transcript `item` names: `artifact:[<store>/]<key>[@<sha256>]`
([`parse_artifact_ref()`](#an.stores.transcripts.parse_artifact_ref)), or a `lacing.Artifact` (filed in
`store_name`), read through `mall`. A pinned reference (what a take’s
provenance records) reads exactly those bytes, even after the key was
recorded again. Raises [`TranscriptLinkError`](#an.stores.transcripts.TranscriptLinkError) for a store the mall
has not, one that is not an artifact store, a key or content it does not
hold, or a record whose `mime` is not a transcript format.

* **Return type:**
  [`LinkedTranscript`](#an.stores.transcripts.LinkedTranscript)

### an.stores.transcripts.orphan_transcript_blobs(store, , named=())

The transcript contents of `store` that no catalog record and nothing
in `named` (the pins a take’s provenance records, an#607) names: what
re-recording a key left behind. Raises [`TranscriptCatalogUnreadable`](#an.stores.transcripts.TranscriptCatalogUnreadable)
when a record cannot be read, since its blob might be the one it names.

```pycon
>>> store = in_memory_transcripts_store()
>>> first = record_transcript(store, "k", "carl: Hello.")
>>> _ = record_transcript(store, "k", "carl: Hello there.")
>>> orphan_transcript_blobs(store) == [first.asset_id]
True
>>> orphan_transcript_blobs(store, named=[first.asset_id])
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.stores.transcripts.parse_artifact_ref(ref, mall, , store_name='transcripts')

`(store, key, pin)` of `artifact:[<store>/]<key>[@<sha256>]` (an#607):
the first segment names a store of `mall` when it is one that holds the
key (else the whole name is a key of `store_name`, so a transcript keyed
`takes/a` is found though the mall has a `takes` store); `pin` is the
content a recorded reference names, `None` when it names none.

```pycon
>>> mall = {"transcripts": {"takes/a": 1}, "takes": {}}
>>> parse_artifact_ref("artifact:takes/a", mall)
('transcripts', 'takes/a', None)
>>> parse_artifact_ref("artifact:transcripts/k@" + "0" * 64, mall)[1:]
('k', '0000000000000000000000000000000000000000000000000000000000000000')
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### an.stores.transcripts.pin_of(reference)

The content digest a recorded reference pins (`<store>/<key>@<sha256>`).

```pycon
>>> pin_of("transcripts/k@" + "a" * 64) == "a" * 64, pin_of("transcripts/k")
(True, None)
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.stores.transcripts.record_transcript(store, key, text, , fmt=None, generated_by='processor:an.stores.transcripts', attributed_to='an', derived_from=())

Keep `text` (a transcript, or a `Path` to one; its format detected,
a file’s suffix first, unless `fmt` says) in `store` under `key`;
return its `lacing.Artifact`. `generated_by` and `attributed_to` are
its provenance (`processor:<name>`, who ran it), `derived_from` the
sha256 of what it was made from (a recording).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.stores.transcripts.transcripts_store(root)

A filesystem transcripts store under `root` (lacing’s layout).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)
