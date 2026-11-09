# an.audio.phones

Phones to mouth shapes: an aligner’s phone timings as a Rhubarb viseme track (an#727).

The phone counterpart of [`an.audio.lipsync.word_timings_to_visemes()`](an.audio.lipsync.html.md#an.audio.lipsync.word_timings_to_visemes), in the
core beside it: the Rhubarb convention is the core’s, so a lip-sync provider of
any genre maps phones the same way (moved from `cutan.audio.phones`).

A recorded take imported with a forced aligner’s output carries its phones,
`AudioClip.phones`: `(phone, start_s, end_s)` from the clip’s start (an#491),
in ARPAbet (MFA’s English models: `HH`, `AH0`) or IPA (`mfa:ipa`: `h`,
`ə`). The take’s record states which (`AudioClip.phone_alphabet`, an#721) and
that wins; a clip without it has the alphabet decided once per clip from its
labels ([`phone_alphabet()`](#an.audio.phones.phone_alphabet)).

[`phones_track()`](#an.audio.phones.phones_track) is what a lip-sync provider calls: the clip’s track from its
phones, or `None` to align some other way. A word the aligner could not
phonetise (MFA writes `spn` under a name it does not know, and `an` drops it)
has no phones under it; it is spoken by its letters spread over its own span,
as in the word-timing rule (`an.audio.lipsync.word_timings_to_visemes`),
though its rests land at the phone rule’s times (when the last sound ends).

```pycon
>>> [(v.time, v.code) for v in phones_to_visemes(
...     [("HH", 0.1, 0.2), ("AH0", 0.2, 0.3), ("L", 0.3, 0.4), ("OW1", 0.4, 0.6)],
...     total_duration=1.0,
... )]
[(0.0, 'X'), (0.1, 'C'), (0.3, 'H'), (0.4, 'F'), (0.6, 'X'), (1.0, 'X')]
```

### Module Attributes

| [`PhoneToViseme`](#an.audio.phones.PhoneToViseme)     | a Rhubarb shape, or `None` when unknown (`alphabet` is the clip's, [`phone_alphabet()`](#an.audio.phones.phone_alphabet)).                                     |
|--------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`ARPABET_TO_VISEME`](#an.audio.phones.ARPABET_TO_VISEME) | ARPAbet (stress digits removed) to a Rhubarb shape.                                                                                                                        |
| [`IPA_TO_VISEME`](#an.audio.phones.IPA_TO_VISEME)     | IPA (diacritics, length and stress marks removed) to a Rhubarb shape.                                                                                                      |
| [`NO_INTENSITY`](#an.audio.phones.NO_INTENSITY)      | How strongly a phone's shape holds against its neighbours (`Viseme.intensity`), keyed by the phone's base (ARPAbet upper case, IPA as written); a phone not listed is 1.0. |
| [`TAKES_NEXT_SHAPE`](#an.audio.phones.TAKES_NEXT_SHAPE)  | `HH` is a breath before the vowel (Rhubarb draws it so), not a mouth shape of its own.                                                                                     |

### Functions

| [`clip_timings`](#an.audio.phones.clip_timings)(audio, field)                      | `audio`'s `words` or `phones` as a list of `(label, start_s, end_s)`; `None` when it has none (or its `an` predates the field).                                                                                                                          |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`phone_alphabet`](#an.audio.phones.phone_alphabet)(phones)                          | `"arpabet"` when every phone is ARPAbet as aligners write it (ASCII, one case throughout, each in `an`'s `ARPABET_PHONES` once its stress digit is dropped), else `"ipa"`.                                                                               |
| [`phone_viseme`](#an.audio.phones.phone_viseme)(phone, \*[, alphabet])             | The Rhubarb shape of one phone in `alphabet`; `REST_VISEME` for a silence; `None` for a phone the table does not know.                                                                                                                                   |
| [`phones_to_visemes`](#an.audio.phones.phones_to_visemes)(phones, \*, total_duration)   | A viseme track from phone timings: each phone's shape at its start (in the clip's [`phone_alphabet()`](#an.audio.phones.phone_alphabet)), the mouth closed at a silence, at a pause longer than `min_gap_for_rest` and after the last sound. |
| [`phones_track`](#an.audio.phones.phones_track)(audio, \*[, phone_to_viseme, ...]) | The mouth track of a clip whose phones are timed (`AudioClip.phones`, a take timed by a forced aligner, an#491), carrying the clip's words too; `None` when it has no phones, or one `phone_to_viseme` does not know.                                    |

### an.audio.phones.ARPABET_TO_VISEME *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'AA': 'D', 'AE': 'C', 'AH': 'C', 'AO': 'E', 'AW': 'D', 'AY': 'D', 'B': 'A', 'CH': 'B', 'D': 'B', 'DH': 'B', 'EH': 'C', 'ER': 'E', 'EY': 'C', 'F': 'G', 'G': 'B', 'HH': 'C', 'IH': 'B', 'IY': 'B', 'JH': 'B', 'K': 'B', 'L': 'H', 'M': 'A', 'N': 'B', 'NG': 'B', 'OW': 'F', 'OY': 'E', 'P': 'A', 'R': 'B', 'S': 'B', 'SH': 'B', 'T': 'B', 'TH': 'B', 'UH': 'F', 'UW': 'F', 'V': 'G', 'W': 'F', 'Y': 'B', 'Z': 'B', 'ZH': 'B'}*

ARPAbet (stress digits removed) to a Rhubarb shape.

### an.audio.phones.IPA_TO_VISEME *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'a': 'D', 'b': 'A', 'c': 'B', 'd': 'B', 'e': 'C', 'f': 'G', 'g': 'B', 'h': 'C', 'i': 'B', 'j': 'B', 'k': 'B', 'l': 'H', 'm': 'A', 'n': 'B', 'o': 'F', 'p': 'A', 'r': 'B', 's': 'B', 't': 'B', 'u': 'F', 'v': 'G', 'w': 'F', 'y': 'F', 'z': 'B', 'æ': 'C', 'ç': 'B', 'ð': 'B', 'ŋ': 'B', 'ɐ': 'C', 'ɑ': 'D', 'ɒ': 'D', 'ɔ': 'E', 'ə': 'C', 'əw': 'F', 'əʊ': 'F', 'ɚ': 'E', 'ɛ': 'C', 'ɜ': 'E', 'ɝ': 'E', 'ɟ': 'B', 'ɡ': 'B', 'ɪ': 'B', 'ɫ': 'H', 'ɱ': 'G', 'ɲ': 'B', 'ɹ': 'B', 'ɾ': 'B', 'ʃ': 'B', 'ʉ': 'F', 'ʊ': 'F', 'ʌ': 'C', 'ʎ': 'H', 'ʒ': 'B', 'ʔ': 'B', 'θ': 'B'}*

IPA (diacritics, length and stress marks removed) to a Rhubarb shape. A
phone not in it is read by its first symbol (`aj` as `a`, `tʃ` as `t`).

### an.audio.phones.NO_INTENSITY *: [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [float](https://docs.python.org/3/builtins/functions.html#float)]* *= {}*

How strongly a phone’s shape holds against its neighbours (`Viseme.intensity`),
keyed by the phone’s base (ARPAbet upper case, IPA as written); a phone not
listed is 1.0. Which phones weigh less is a genre’s art direction (cutan’s
tongue-only consonants, cutan#157), passed as `intensity_of`.
The default: every cue at full intensity.

### an.audio.phones.PhoneToViseme

a Rhubarb shape, or `None` when
unknown (`alphabet` is the clip’s, [`phone_alphabet()`](#an.audio.phones.phone_alphabet)). Silences never
reach it: they are the rest shape.

* **Type:**
  `phone_to_viseme(phone, *, alphabet)`

alias of `Callable`[[…], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### an.audio.phones.TAKES_NEXT_SHAPE *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'HH', 'h', 'ɦ'})*

`HH` is a breath
before the vowel (Rhubarb draws it so), not a mouth shape of its own.

* **Type:**
  The phones that take the shape of the phone after them

### an.audio.phones.clip_timings(audio, field)

`audio`’s `words` or `phones` as a list of `(label, start_s, end_s)`;
`None` when it has none (or its `an` predates the field).

```pycon
>>> clip_timings(AudioClip(duration=1.0, phones=[("M", 0, 0.1)]), "phones")
[('M', 0.0, 0.1)]
>>> clip_timings(AudioClip(duration=1.0), "phones") is None
True
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]]

### an.audio.phones.phone_alphabet(phones)

`"arpabet"` when every phone is ARPAbet as aligners write it (ASCII, one
case throughout, each in `an`’s `ARPABET_PHONES` once its stress digit is
dropped), else `"ipa"`. Decided per clip: a SAMPA `V` (the vowel of
*love*) beside a lowercase `l` is not ARPAbet `V`. The rule is `an`’s
([`phone_alphabet_of()`](an.audio.transcripts.html.md#an.audio.transcripts.phone_alphabet_of)), which says `None` where
it cannot tell; this lip-sync reads that as IPA.

```pycon
>>> phone_alphabet(["HH", "AH0", "L"]), phone_alphabet(["hh", "ah0"])
('arpabet', 'arpabet')
>>> phone_alphabet(["l", "V", "v"]), phone_alphabet(["h", "ə", "l"])
('ipa', 'ipa')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.audio.phones.phone_viseme(phone, , alphabet='arpabet')

The Rhubarb shape of one phone in `alphabet`; `REST_VISEME` for a
silence; `None` for a phone the table does not know.

```pycon
>>> phone_viseme("AA1"), phone_viseme("M"), phone_viseme("sil"), phone_viseme("Q9")
('D', 'A', 'X', None)
>>> [phone_viseme(p, alphabet="ipa") for p in ("tʃ", "iː", "əw", "ʘ")]
['B', 'B', 'F', None]
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.audio.phones.phones_to_visemes(phones, \*, total_duration, words=(), phone_to_viseme=<function phone_viseme>, char_to_viseme=None, rest_viseme='X', min_gap_for_rest=0.2, alphabet=None, intensity_of={}, takes_next_shape=frozenset({'HH', 'h', 'ɦ'}))

A viseme track from phone timings: each phone’s shape at its start (in the
clip’s [`phone_alphabet()`](#an.audio.phones.phone_alphabet)), the mouth closed at a silence, at a pause
longer than `min_gap_for_rest` and after the last sound. A word of `words`
with no phone under it is spoken by its letters (`char_to_viseme`).

`alphabet` is the take’s recorded one (`AudioClip.phone_alphabet`); with
none, the clip’s labels decide ([`phone_alphabet()`](#an.audio.phones.phone_alphabet)).

`intensity_of` maps a phone (its base: stress and modifiers dropped) to the
`Viseme.intensity` of its cue, so a genre’s co-articulation can let a
vowel’s `B` beat a tongue-only consonant’s (cutan#157). A phone of
`takes_next_shape` (`HH`) shows the shape of the next spoken phone, kept
as its own only at the end.

`None` when a phone is one `phone_to_viseme` does not know: a phone set
this table was not written for is better spread by its words than guessed.

```pycon
>>> phones_to_visemes([("ʘ", 0.0, 0.1)], total_duration=1.0) is None
True
>>> [(v.time, v.code) for v in phones_to_visemes(
...     [("M", 0.0, 0.1), ("AA1", 0.1, 0.3), ("P", 0.6, 0.7)], total_duration=0.7)]
[(0.0, 'X'), (0.0, 'A'), (0.1, 'D'), (0.3, 'X'), (0.6, 'A'), (0.7, 'X')]
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Viseme`](an.audio.lipsync.html.md#an.audio.lipsync.Viseme)]]

### an.audio.phones.phones_track(audio, \*, phone_to_viseme=<function phone_viseme>, char_to_viseme=None, rest_viseme='X', convention='rhubarb', intensity_of={})

The mouth track of a clip whose phones are timed (`AudioClip.phones`, a
take timed by a forced aligner, an#491), carrying the clip’s words too;
`None` when it has no phones, or one `phone_to_viseme` does not know.

```pycon
>>> clip = AudioClip(duration=0.5, phones=[("M", 0.1, 0.2)], words=[("m", 0.1, 0.2)])
>>> track = phones_track(clip)
>>> [v.code for v in track.visemes], track.words
(['X', 'A', 'X', 'X'], [('m', 0.1, 0.2)])
>>> phones_track(AudioClip(duration=0.5)) is None
True
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`VisemeTrack`](an.audio.lipsync.html.md#an.audio.lipsync.VisemeTrack)]
