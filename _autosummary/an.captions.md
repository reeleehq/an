# an.captions

Captions from the word timings the audio pipeline already computes (an#175).

Epic #9 Wave 8, second slice. The audio pipeline stamps each dialogue line
with the provider’s word timings (`Dialogue.word_timings`, line-relative,
an#96) for lip-sync; this module turns them into captions, opt-in through
`meta.captions` ([`Captions`](an.ir.schema.md#an.ir.schema.Captions)).

**One cue list, two outputs.** [`caption_pages()`](#an.captions.caption_pages) is the single statement
of what is captioned and on which frames. Both outputs are derived from it:

- the picture — [`captioned_shot()`](#an.captions.captioned_shot) adds each page as an OVERLAY text
  block ([`an.stage.text`](an.stage.text.md#module-an.stage.text); camera-immune, placed at a title-safe anchor) plus
  ordinary `set` actions that show it for exactly its frames, and
  optionally tint the word being spoken;
- the sidecar — [`caption_cues()`](#an.captions.caption_cues) places the same pages in FILM time and
  [`dump_srt()`](#an.captions.dump_srt) writes SubRip, stored through the `captions` store beside
  > the delivered mp4.

So the two cannot disagree: a page’s cue starts at the first frame that shows
it and ends at the first frame that does not. Times are frames, not seconds,
until the last step:

```pycon
>>> from an.ir.schema import Dialogue, SceneIR, Shot, WordTimingIR
>>> line = Dialogue(speaker="a", text="Hello there, friend.", start=0.5, duration=1.5,
...     word_timings=[WordTimingIR(text=w, start=s, end=s + 0.3)
...                   for w, s in (("Hello", 0.0), ("there,", 0.4), ("friend.", 0.8))])
>>> scene = SceneIR(timeline=[Shot(id="s", duration=3.0, dialogue=[line])])
>>> [(p.start, p.end, p.text) for p in caption_pages(scene, fps=10)]
[(5, 20, 'Hello there, friend.')]
```

**Film time follows the delivered timeline.** A cue’s time is its shot’s
first frame in the film ([`an.assemble.film_timeline()`](an.assemble.md#an.assemble.film_timeline) — the same
function the assembler lays the picture out with) plus its shot-local frame,
so a dissolve, which overlaps two shots and shortens the film, moves every
later cue earlier by exactly its overlap.

**Timing is materialised into ordinary actions**, the way [`an.stage.text.reveal_units()`](an.stage.text.md#an.stage.text.reveal_units)
works: nothing in the compiler or the runtime knows what a caption is. The
caption blocks are added to the shot at RENDER time, never written back to
the scene — the word timings are the audio pipeline’s output, and a caption
baked into `scene.json` would go stale the moment a line is re-voiced.

**When a line has no word timings** (the offline and Rhubarb providers keep
none), its words are spread evenly over the line’s duration and a
[`CaptionTimingWarning`](#an.captions.CaptionTimingWarning) says so; `Captions(strict=True)` raises
instead. A line the audio pipeline has not placed (no `start`) cannot be
captioned and is skipped the same loud way.

\*\*The SubRip cue type is a pinned mirror of `mixing.srt``**, not an import
(epic #9, Decision 2, departed from on measurement): ``mixing`’s package
facade is lazy, so importing `mixing.srt` is cheap — but INSTALLING
`mixing` pulls `moviepy`, `opencv-contrib-python`, `scipy` and
`imageio-ffmpeg`, whose wheel ships an ffmpeg binary built with
`--enable-gpl`. A hard dependency would put a GPL binary inside every
`pip install an`, past a licence perimeter that reads declared metadata
(BSD-2) and would never see it. [`Cue`](#an.captions.Cue), [`seconds_to_srt_time()`](#an.captions.seconds_to_srt_time) and
[`dump_srt()`](#an.captions.dump_srt) therefore mirror `mixing.srt` field for field and byte for
byte, and `tests/test_captions.py` pins both against `mixing` whenever it
is importable, and against a literal otherwise; thorwhalen/mixing#54 asks
for the light base install that would let this become an import. WebVTT is `lacing`’s (its
adapter owns the body schema), so it is not written here.

### Module Attributes

| [`CAPTION_ID_PREFIX`](#an.captions.CAPTION_ID_PREFIX)   | A caption page's entity id is this plus its index within the shot.                                                                           |
|----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| [`CAPTION_PROP_REF`](#an.captions.CAPTION_PROP_REF)    | The props-store key the caption blocks resolve against — a style-only `TextDescriptor` supplied at render time, never stored in the project. |

### Functions

| [`caption_cues`](#an.captions.caption_cues)(pages, timeline)                  | `pages` in FILM time on `timeline` (an [`an.assemble.FilmTimeline`](an.assemble.md#an.assemble.FilmTimeline)).   |
|-------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| [`caption_pages`](#an.captions.caption_pages)(scene, \*, fps[, captions])      | Every caption page of `scene`, shot by shot, in the order shown.                                                                              |
| [`captioned_shot`](#an.captions.captioned_shot)(shot, pages, captions, \*, ...) | `shot` with its caption pages burned in, and the mall to compile it with.                                                                     |
| [`dump_srt`](#an.captions.dump_srt)(cues)                                 | Serialize cues to SubRip text, renumbering from 1.                                                                                            |
| [`paginate`](#an.captions.paginate)(words, \*, max_chars, max_lines)      | Split `words` into pages of at most `max_lines` wrapped lines, a new page starting after each sentence end.                                   |
| [`seconds_to_srt_time`](#an.captions.seconds_to_srt_time)(seconds)                   | `HH:MM:SS,mmm`, milliseconds ROUNDED with carry; negatives clamp to 0.                                                                        |
| [`srt_for_scene`](#an.captions.srt_for_scene)(scene, \*, fps[, pages])         | The SubRip sidecar of `scene` rendered at `fps`.                                                                                              |
| [`wrap_words`](#an.captions.wrap_words)(words, max_chars)                   | Greedy line breaks at `max_chars` characters (spaces counted); a word longer than a line gets a line of its own and is never split.           |

### Classes

| [`CaptionPage`](#an.captions.CaptionPage)(shot, start, end, lines, word_frames)   | One caption as shown: which shot, which frames, which words.   |
|------------------------------------------------------------------------------------------------------|----------------------------------------------------------------|
| [`Cue`](#an.captions.Cue)(index, start, end, text)                        | One SubRip cue — `mixing.srt.Cue`'s fields, in its order.      |

### Exceptions

| [`CaptionError`](#an.captions.CaptionError)         | Captions cannot be built as asked.                              |
|-----------------------------------------------------------------------|-----------------------------------------------------------------|
| [`CaptionTimingWarning`](#an.captions.CaptionTimingWarning) | A line is captioned on estimated timing, or not at all.         |
| [`CaptionWarning`](#an.captions.CaptionWarning)       | Captions were built, but not everything was captioned as asked. |

### an.captions.CAPTION_ID_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'caption_'*

A caption page’s entity id is this plus its index within the shot.

### an.captions.CAPTION_PROP_REF *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an.captions'*

The props-store key the caption blocks resolve against — a style-only
`TextDescriptor` supplied at render time, never stored in the project.

### *exception* an.captions.CaptionError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

Captions cannot be built as asked. Carries the fix.

### *class* an.captions.CaptionPage(shot, start, end, lines, word_frames, speaker=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One caption as shown: which shot, which frames, which words.

`start`/`end` are SHOT-local frames — the first that shows the page and
the first that does not. `lines` are the words per line, broken by
[`wrap_words()`](#an.captions.wrap_words); `word_frames[j]` is the frame word `j` (in reading
order) starts being spoken, clamped into the page.

#### *property* text *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

words joined by spaces, lines by
newlines.

* **Type:**
  The page as both outputs write it

#### *property* words *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Every word of the page, in reading order.

### *exception* an.captions.CaptionTimingWarning

Bases: [`CaptionWarning`](#an.captions.CaptionWarning)

A line is captioned on estimated timing, or not at all.

### *exception* an.captions.CaptionWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

Captions were built, but not everything was captioned as asked.

### *class* an.captions.Cue(index, start, end, text)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One SubRip cue — `mixing.srt.Cue`’s fields, in its order.

```pycon
>>> Cue(index=1, start=0.5, end=2.0, text="Hi").duration
1.5
```

#### *property* duration *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Cue duration in seconds (never negative).

### an.captions.caption_cues(pages, timeline)

`pages` in FILM time on `timeline` (an [`an.assemble.FilmTimeline`](an.assemble.md#an.assemble.FilmTimeline)).

A cue starts on the film frame that first shows its page and ends on the
first that does not — the same frames the picture shows it on.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Cue`](#an.captions.Cue)]

### an.captions.caption_pages(scene, , fps, captions=None)

Every caption page of `scene`, shot by shot, in the order shown.

`captions` defaults to `scene.meta.captions` (and to the defaults when
that is unset). Dialogue and narration are both captioned (though the
audio pipeline does not voice narration yet, so a narration line has no
`start` in a rendered scene and is skipped with a warning). Within a
shot a page is cut off when the next one starts, so two pages are never
drawn over each other at one anchor; ACROSS a transition they can be — a
dissolve blends the tail of one shot, captions included, with the head of
the next, and a fade takes the burned caption through the colour with the
rest of the picture, while the sidecar’s cue is simply on.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`CaptionPage`](#an.captions.CaptionPage)]

### an.captions.captioned_shot(shot, pages, captions, , fps, mall, shot_index=None, base_dir=None, resolution=None)

`shot` with its caption pages burned in, and the mall to compile it with.

Each page becomes an overlay text block `caption_<k>` and the `set`
actions that show it for exactly its frames. With `shot_index`, only the
pages of that shot are used, so a caller can pass the scene’s whole list;
without it every page must belong to one shot. The returned mall is
`mall` with the caption style laid over its props store — nothing is
written to the project. `base_dir` resolves a relative caption `font`.

With `resolution`, every page is typeset now, so a caption the face
cannot draw (an em dash in the embedded face) raises a [`CaptionError`](#an.captions.CaptionError)
naming the shot and the words — before a browser launches, rather than
from inside a shot’s compile after others have rendered.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Shot`](an.ir.schema.md#an.ir.schema.Shot), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.captions.dump_srt(cues)

Serialize cues to SubRip text, renumbering from 1.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> print(dump_srt([Cue(7, 1.0, 2.5, "Hello\nthere")]))
1
00:00:01,000 --> 00:00:02,500
Hello
there
```

### an.captions.paginate(words, , max_chars, max_lines)

Split `words` into pages of at most `max_lines` wrapped lines, a new
page starting after each sentence end. Returns index ranges.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`range`](https://docs.python.org/3/builtins/stdtypes.html#range)]

```pycon
>>> paginate("One two. Three four five six".split(), max_chars=10, max_lines=1)
[range(0, 2), range(2, 4), range(4, 6)]
```

### an.captions.seconds_to_srt_time(seconds)

`HH:MM:SS,mmm`, milliseconds ROUNDED with carry; negatives clamp to 0.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> seconds_to_srt_time(2592.187), seconds_to_srt_time(-3)
('00:43:12,187', '00:00:00,000')
```

### an.captions.srt_for_scene(scene, , fps, pages=None)

The SubRip sidecar of `scene` rendered at `fps`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> from an.ir.schema import Dialogue, SceneIR, Shot, Transition, WordTimingIR
>>> def shot(sid, **kw):
...     line = Dialogue(speaker="a", text="Hi.", start=0.2, duration=0.5,
...                     word_timings=[WordTimingIR(text="Hi.", start=0.0, end=0.4)])
...     return Shot(id=sid, duration=2.0, dialogue=[line], **kw)
>>> scene = SceneIR(timeline=[shot("a"), shot("b", transition=Transition(kind="dissolve"))])
>>> print(srt_for_scene(scene, fps=10))   # b starts at 1.5 s: the dissolve's 0.5 s overlap
1
00:00:00,200 --> 00:00:00,700
Hi.

2
00:00:01,700 --> 00:00:02,200
Hi.
```

### an.captions.wrap_words(words, max_chars)

Greedy line breaks at `max_chars` characters (spaces counted); a word
longer than a line gets a line of its own and is never split.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> wrap_words("the quick brown fox jumps".split(), 10)
[['the', 'quick'], ['brown', 'fox'], ['jumps']]
```
