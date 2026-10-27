# an.audio.transcripts

Transcripts as INPUT: SRT, WebVTT, Praat TextGrid, word-timed JSON and plain
text read into timed segments, and a known text matched to a transcriber’s words.

Every package in the fleet writes subtitles ([`an.captions`](an.captions.html.md#module-an.captions), `mixing.srt`,
scribed’s `Transcript.srt`); this module is the reading direction, for a
performer’s recording that arrives with its words already written down. Three
shapes come in:

- **timed segments** — SRT, WebVTT, a word-timed JSON, a TextGrid: each line
  of dialogue has a start and an end in the recording, so the take can be cut
  at them with no model at all;
- **plain text** — the lines, one per line, optionally `speaker: text` (the
  `scene.md` grammar). No times: either each line is its own audio file, or
  a transcriber’s timed words are matched to the text ([`align_words()`](#an.audio.transcripts.align_words));
- **a transcriber’s result** — any object shaped like scribed’s `Transcript`
  (segments with `text`/`start`/`end`/`speaker`/`words`), read by
  [`from_transcript_object()`](#an.audio.transcripts.from_transcript_object).

All times are seconds from the start of the recording they describe.

```pycon
>>> segs = parse_transcript("1\n00:00:01,000 --> 00:00:02,500\ncarl: Hello there.\n\n"
...                         "2\n00:00:03,000 --> 00:00:03,800\nned: Hi.\n")
>>> [(s.speaker, s.text, s.start, s.end) for s in segs]
[('carl', 'Hello there.', 1.0, 2.5), ('ned', 'Hi.', 3.0, 3.8)]
>>> aligned = align_words(["Hello", "there,", "friend"],
...                       [("hello", 0.5, 0.9), ("there", 0.9, 1.2), ("fred", 1.3, 1.6)])
>>> aligned.words
[('Hello', 0.5, 0.9), ('there,', 0.9, 1.2), ('friend', 1.3, 1.6)]
>>> aligned.matched, aligned.total
(2, 3)
```

### Module Attributes

| [`FORMATS`](#an.audio.transcripts.FORMATS)   | The transcript formats read here, in detection order.   |
|------------------------------------------------------------|---------------------------------------------------------|

### Functions

| [`detect_format`](#an.audio.transcripts.detect_format)(text, \*[, suffix])           | Which of [`FORMATS`](#an.audio.transcripts.FORMATS) `text` is, by its file suffix first, then its content.                                                                                                                                                                                                       |
|----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`parse_transcript`](#an.audio.transcripts.parse_transcript)(source, \*[, fmt])         | Read `source` — a path to a transcript file, or the transcript text itself — into segments.                                                                                                                                                                                                                                    |
| [`parse_transcript_text`](#an.audio.transcripts.parse_transcript_text)(text, \*[, fmt])      | The transcript `text` (never a path: what a store hands back, an#493) into segments; `fmt` (one of [`FORMATS`](#an.audio.transcripts.FORMATS)) overrides detection.                                                                                                                                              |
| [`parse_srt`](#an.audio.transcripts.parse_srt)(text)                             | SubRip cues → timed segments; a `speaker:` prefix names the speaker.                                                                                                                                                                                                                                                           |
| [`parse_vtt`](#an.audio.transcripts.parse_vtt)(text)                             | WebVTT cues → timed segments; `<v Name>` or a `speaker:` prefix names the speaker.                                                                                                                                                                                                                                             |
| [`parse_plain`](#an.audio.transcripts.parse_plain)(text)                           | One non-empty line per segment, untimed; `speaker: text` names the speaker.                                                                                                                                                                                                                                                    |
| [`parse_json`](#an.audio.transcripts.parse_json)(obj)                             | A word-timed JSON → segments.                                                                                                                                                                                                                                                                                                  |
| [`parse_textgrid`](#an.audio.transcripts.parse_textgrid)(text)                        | A Praat TextGrid (long or short form, as a forced aligner writes it) → segments.                                                                                                                                                                                                                                               |
| [`from_transcript_object`](#an.audio.transcripts.from_transcript_object)(obj)                 | A transcriber's result — scribed's `Transcript` or anything shaped like it (iterable segments with `text`, `start`, `end`, `speaker` and `words` having `text`/`start`/`end`) — as segments.                                                                                                                                   |
| [`parse_timestamp`](#an.audio.transcripts.parse_timestamp)(value)                      | `HH:MM:SS,mmm` / `MM:SS.mmm` / plain seconds → seconds.                                                                                                                                                                                                                                                                        |
| [`normalize_tokens`](#an.audio.transcripts.normalize_tokens)(text)                      | The words of `text` for matching: case-folded, punctuation dropped, an apostrophe inside a word kept.                                                                                                                                                                                                                          |
| [`normalize_text`](#an.audio.transcripts.normalize_text)(text)                        | [`normalize_tokens()`](#an.audio.transcripts.normalize_tokens) joined by single spaces (what two lines are compared by).                                                                                                                                                                                                  |
| [`align_words`](#an.audio.transcripts.align_words)(reference, timed, \*[, bounds]) | Time the `reference` words (the text the performer was meant to say) by a transcriber's `timed` words of the same audio.                                                                                                                                                                                                       |
| [`segment_lines`](#an.audio.transcripts.segment_lines)(lines, timed, \*[, bounds])   | Time untimed `lines` (a plain transcript) by a transcriber's `timed` words of the whole recording: the lines' words are aligned as one text ([`align_words()`](#an.audio.transcripts.align_words)) and handed back per line, each line spanning its first word's start to its last word's end, with its own `words`. |
| [`cut_spans`](#an.audio.transcripts.cut_spans)(segments, \*, total[, pad_s])     | Where to cut the recording for each timed segment: its span widened by `pad_s` on each side, never past the midpoint to its neighbour or the recording's ends (`total` seconds).                                                                                                                                               |
| [`rebase_words`](#an.audio.transcripts.rebase_words)(words, start)                  | `words` re-timed from `start` (a cut's start): the clip-relative words a line keeps.                                                                                                                                                                                                                                           |

### Classes

| [`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)(text[, start, end, ...])   | One spoken line of a transcript: its text, and when and who, if known.                                                                                                                     |
|-----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`AlignedWords`](#an.audio.transcripts.AlignedWords)(words, matched, total)          | [`align_words()`](#an.audio.transcripts.align_words)'s result: the reference words timed, and how many of them a transcribed word actually anchored (the rest are interpolated). |

### *class* an.audio.transcripts.AlignedWords(words, matched, total)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

[`align_words()`](#an.audio.transcripts.align_words)’s result: the reference words timed, and how many
of them a transcribed word actually anchored (the rest are interpolated).

#### *property* coverage *: [float](https://docs.python.org/3/builtins/functions.html#float)*

The share of reference words anchored by a transcribed word, 0..1.

### an.audio.transcripts.FORMATS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('vtt', 'textgrid', 'json', 'srt', 'plain')*

The transcript formats read here, in detection order.

### *class* an.audio.transcripts.TranscriptSegment(text, start=None, end=None, speaker=None, words=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One spoken line of a transcript: its text, and when and who, if known.

`start`/`end` are seconds from the recording’s start, `None` for an
untimed (plain) transcript; `words` are the segment’s own word timings
when the format carries them (word JSON, TextGrid), else `None`.

#### *property* timed *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether both `start` and `end` are known.

### an.audio.transcripts.align_words(reference, timed, , bounds=None)

Time the `reference` words (the text the performer was meant to say) by a
transcriber’s `timed` words of the same audio.

Reference words that a transcribed word matches (same normalized form, in
sequence — [`difflib.SequenceMatcher`](https://docs.python.org/3/library/difflib.html#difflib.SequenceMatcher)) take that word’s times. A run
the transcriber heard differently (`friend` heard as `fred`) is spread
over the misheard words’ span; a run it did not hear at all is spread over
the gap to the next anchor, in proportion to word length — so a misheard or
dropped word still gets a plausible slot. `bounds` (`(start, end)` of
the audio) time the ends when no anchor does; without it the first and last
transcribed words do. Words come back in reference order with
non-decreasing starts.

```pycon
>>> align_words(["I", "did", "NOT", "ask"], [("i", 0.0, 0.1), ("did", 0.1, 0.3), ("ask", 0.6, 0.9)]).words
[('I', 0.0, 0.1), ('did', 0.1, 0.3), ('NOT', 0.3, 0.6), ('ask', 0.6, 0.9)]
```

* **Return type:**
  [`AlignedWords`](#an.audio.transcripts.AlignedWords)

### an.audio.transcripts.cut_spans(segments, , total, pad_s=0.05)

Where to cut the recording for each timed segment: its span widened by
`pad_s` on each side, never past the midpoint to its neighbour or the
recording’s ends (`total` seconds).

```pycon
>>> segs = [TranscriptSegment("a", 1.0, 2.0), TranscriptSegment("b", 2.04, 3.0)]
>>> cut_spans(segs, total=3.02)
[(0.95, 2.02), (2.02, 3.02)]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.audio.transcripts.detect_format(text, , suffix='')

Which of [`FORMATS`](#an.audio.transcripts.FORMATS) `text` is, by its file suffix first, then its content.

```pycon
>>> detect_format("WEBVTT\n\n00:01.000 --> 00:02.000\nhi")
'vtt'
>>> detect_format("1\n00:00:01,000 --> 00:00:02,000\nhi"), detect_format("hi there")
('srt', 'plain')
>>> detect_format('{"segments": []}'), detect_format("", suffix=".TextGrid")
('json', 'textgrid')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.transcripts.from_transcript_object(obj)

A transcriber’s result — scribed’s `Transcript` or anything shaped like
it (iterable segments with `text`, `start`, `end`, `speaker` and
`words` having `text`/`start`/`end`) — as segments.

```pycon
>>> from types import SimpleNamespace as NS
>>> t = [NS(text="Hi there", start=0.2, end=0.9, speaker="A",
...         words=[NS(text="Hi", start=0.2, end=0.4), NS(text="there", start=0.5, end=0.9)])]
>>> from_transcript_object(t)[0].words
(('Hi', 0.2, 0.4), ('there', 0.5, 0.9))
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)]

### an.audio.transcripts.normalize_text(text)

[`normalize_tokens()`](#an.audio.transcripts.normalize_tokens) joined by single spaces (what two lines are compared by).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.transcripts.normalize_tokens(text)

The words of `text` for matching: case-folded, punctuation dropped,
an apostrophe inside a word kept.

```pycon
>>> normalize_tokens("Hello, there — it's ME!")
['hello', 'there', "it's", 'me']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.audio.transcripts.parse_json(obj)

A word-timed JSON → segments. Accepted: `{"segments": [...]}` or a list
of segments, each `{"text", "start", "end", "speaker", "words": [{"text"|"word",
"start", "end"}, ...]}` (`start_ms`/`end_ms` are read too, and a word may
be a `[text, start, end]` list); or a bare list of words, read as one segment.

```pycon
>>> segs = parse_json({"segments": [{"speaker": "carl", "words": [
...     {"word": "Hello", "start": 0.5, "end": 0.9}, ["there", 0.9, 1.2]]}]})
>>> segs[0].text, segs[0].start, segs[0].end, segs[0].words
('Hello there', 0.5, 1.2, (('Hello', 0.5, 0.9), ('there', 0.9, 1.2)))
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)]

### an.audio.transcripts.parse_plain(text)

One non-empty line per segment, untimed; `speaker: text` names the speaker.

```pycon
>>> [s.speaker for s in parse_plain("carl: Hi.\n\nJust a line.\n")]
['carl', None]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)]

### an.audio.transcripts.parse_srt(text)

SubRip cues → timed segments; a `speaker:` prefix names the speaker.

```pycon
>>> parse_srt("1\n00:00:00,500 --> 00:00:01,000\nHi\nthere\n")
[TranscriptSegment(text='Hi there', start=0.5, end=1.0, speaker=None, words=None)]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)]

### an.audio.transcripts.parse_textgrid(text)

A Praat TextGrid (long or short form, as a forced aligner writes it) → segments.

The words come from a tier named `words` (else the first interval tier);
a tier named `utterances`/`lines`/`sentences` gives one segment per
non-empty interval, with the words inside it; without one, the whole grid
is one segment.

```pycon
>>> tg = ('File type = "ooTextFile"\nObject class = "TextGrid"\nxmin = 0\nxmax = 2\n'
...       'tiers? <exists>\nsize = 1\nitem []:\n    item [1]:\n        class = "IntervalTier"\n'
...       '        name = "words"\n        xmin = 0\n        xmax = 2\n        intervals: size = 3\n'
...       '        intervals [1]:\n            xmin = 0\n            xmax = 0.5\n            text = ""\n'
...       '        intervals [2]:\n            xmin = 0.5\n            xmax = 0.9\n            text = "hello"\n'
...       '        intervals [3]:\n            xmin = 0.9\n            xmax = 1.3\n            text = "there"\n')
>>> parse_textgrid(tg)
[TranscriptSegment(text='hello there', start=0.5, end=1.3, speaker=None, words=(('hello', 0.5, 0.9), ('there', 0.9, 1.3)))]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)]

### an.audio.transcripts.parse_timestamp(value)

`HH:MM:SS,mmm` / `MM:SS.mmm` / plain seconds → seconds.

```pycon
>>> parse_timestamp("00:01:02,500"), parse_timestamp("01:02.5"), parse_timestamp("7.25")
(62.5, 62.5, 7.25)
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.audio.transcripts.parse_transcript(source, , fmt=None)

Read `source` — a path to a transcript file, or the transcript text
itself — into segments. `fmt` (one of [`FORMATS`](#an.audio.transcripts.FORMATS)) overrides detection.

```pycon
>>> parse_transcript("carl: Hello.\nned: Hi.")[1]
TranscriptSegment(text='Hi.', start=None, end=None, speaker='ned', words=None)
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)]

### an.audio.transcripts.parse_transcript_text(text, , fmt=None)

The transcript `text` (never a path: what a store hands back, an#493)
into segments; `fmt` (one of [`FORMATS`](#an.audio.transcripts.FORMATS)) overrides detection.

```pycon
>>> parse_transcript_text("note", fmt="plain")[0].text
'note'
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)]

### an.audio.transcripts.parse_vtt(text)

WebVTT cues → timed segments; `<v Name>` or a `speaker:` prefix names the speaker.

```pycon
>>> parse_vtt("WEBVTT\n\n00:01.000 --> 00:02.000\n<v Carl>Hello</v>\n")
[TranscriptSegment(text='Hello', start=1.0, end=2.0, speaker='Carl', words=None)]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)]

### an.audio.transcripts.rebase_words(words, start)

`words` re-timed from `start` (a cut’s start): the clip-relative words a line keeps.

```pycon
>>> rebase_words([("hi", 1.0, 1.4)], 0.95)
(('hi', 0.05, 0.45),)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.transcripts.segment_lines(lines, timed, , bounds=None)

Time untimed `lines` (a plain transcript) by a transcriber’s `timed`
words of the whole recording: the lines’ words are aligned as one text
([`align_words()`](#an.audio.transcripts.align_words)) and handed back per line, each line spanning its
first word’s start to its last word’s end, with its own `words`.

```pycon
>>> lines = parse_plain("carl: Hello there.\nned: Hi.")
>>> timed = [("hello", 0.5, 0.9), ("there", 0.9, 1.3), ("hi", 2.0, 2.3)]
>>> [(s.speaker, s.start, s.end, len(s.words)) for s in segment_lines(lines, timed)]
[('carl', 0.5, 1.3, 2), ('ned', 2.0, 2.3, 1)]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`TranscriptSegment`](#an.audio.transcripts.TranscriptSegment)]
