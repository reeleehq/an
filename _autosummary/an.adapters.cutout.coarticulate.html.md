# an.adapters.cutout.coarticulate

Co-articulation for a swap mouth: the passes between a provider’s raw viseme
track and the compiler’s channel emission (an#97, epic #9 Wave 6).

A lip-sync provider hands the compiler a list of `(time, code)` cues — one
mouth shape per phoneme or per character, at whatever density it produced.
Shown as-is, that track *flickers*: consonant clusters swap the mouth faster
than a frame or two can show, tongue-only shapes swap the lips for one frame, and
every shape lands exactly on its sound instead of a beat ahead of it. These
passes turn the raw track into what an animator would key, in this order:

1. **Symbolic** — [`merge_duplicates()`](#an.adapters.cutout.coarticulate.merge_duplicates) drops a cue whose shape is already
   showing; [`suppress_weak()`](#an.adapters.cutout.coarticulate.suppress_weak) drops a low-dominance cue that would show for
   less than one frame (JALI, Edwards et al. 2016 §4.2: “Tongue-only visemes
   (l n t d g k N) have no influence on the lips” — for a swap mouth, “take the
   neighbour’s shape” is “do not swap”).
2. **Anticipation** — [`lead()`](#an.adapters.cutout.coarticulate.lead) moves every cue earlier by a fixed lead
   (JALI: “speech onset begins 120 ms before the apex”; the animator’s “two
   frames ahead”; Rhubarb’s own `maxExtensionDuration` of 60 ms), clamped
   at 0.
   2b. **Close after speech** — [`close_after_speech()`](#an.adapters.cutout.coarticulate.close_after_speech) puts the mouth at rest
   where the last WORD ends, when the line knows its words (an#213). A
   provider that aligns from words keyed a rest between words but, until
   an#213, not after the last one, so the last shape held through the
   trailing silence of the clip; cached tracks keep that defect, so the
   compiler closes the mouth rather than asking for a re-alignment. After
   the lead (on the led times, so a word shorter than the lead still opens
   the mouth before it closes) and before the decay (which gives the last
   shape its time).
3. **Decay** — [`decay()`](#an.adapters.cutout.coarticulate.decay) gives a shape its time to close: a rest cue that
   arrives sooner than `decay_s` after the shape before it is pushed out to
   `decay_s` (JALI: “another 120 ms to decay to zero”), never past the next
   speaking cue.
4. **Minimum hold** — [`condense()`](#an.adapters.cutout.coarticulate.condense), LAST. It **holds and votes**; it never
   drops a cue unvoted (a carried loser can lose its next window too and never
   show — outvoted twice, not skipped). Windows of at least `min_hold_s` open at each cue that clears the
   previous window; within a window the shape with the largest
   `span × dominance` (Rhubarb’s “select shape with highest total duration
   within the candidate range”, weighted by Cohen–Massaro’s per-segment
   dominance) shows, **placed at the window start**. The old compiler loop

   ```
   ``
   ```

   continue\`\`d past every cue inside the window, so a consonant cluster
   collapsed to whichever shape arrived first — the defect epic #9 names.

Order matters: (1) before (4) so a one-frame /t/ never wins a window; (2) and
(3) before (4) so the hold is measured on shifted times. Every pass is a pure
function over `list[Cue]`, runs in the **compiler** (never in the audio
pipeline, so a knob change is a recompile and never a paid re-alignment), and
none of these constants may ever enter a cache key.

Dominance: the ORDER of [`DOMINANCE`](#an.adapters.cutout.coarticulate.DOMINANCE) is sourced — A (bilabial closure;
JALI rule 1 “must close the lips”) > F, G (lip-heavy) > E, D > C > X > B, H
(tongue) — and its values are art direction. A provider that knows the
character behind a cue may scale it through `Cue.intensity` (Rhubarb’s `B`
codes both “most consonants” and the vowel EE, so the letter alone cannot say).

### Module Attributes

| [`DOMINANCE`](#an.adapters.cutout.coarticulate.DOMINANCE)          | Per-shape dominance for Rhubarb's letters.                                                                 |
|---------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| [`DEFAULT_DOMINANCE`](#an.adapters.cutout.coarticulate.DEFAULT_DOMINANCE)  | A shape not in the table (another convention's code) is neither strong nor weak.                           |
| [`WEAK_BELOW`](#an.adapters.cutout.coarticulate.WEAK_BELOW)         | Below this dominance a cue is "weak" for [`suppress_weak()`](#an.adapters.cutout.coarticulate.suppress_weak). |
| [`DEFAULT_LEAD_S`](#an.adapters.cutout.coarticulate.DEFAULT_LEAD_S)     | Anticipation lead — two frames at 24 fps (art direction; JALI's 120 ms is the ceiling).                    |
| [`DEFAULT_DECAY_S`](#an.adapters.cutout.coarticulate.DEFAULT_DECAY_S)    | Time a shape is given to close before rest (JALI's "120 ms to decay").                                     |
| [`DEFAULT_MIN_HOLD_S`](#an.adapters.cutout.coarticulate.DEFAULT_MIN_HOLD_S) | The minimum hold, unchanged from the pre-an#97 compiler until measured.                                    |

### Functions

| [`close_after_speech`](#an.adapters.cutout.coarticulate.close_after_speech)(keys, \*, speech_end[, rest])   | Rest once speech is over: at `speech_end`, or just after the last shape when a shape is keyed at or after it — never before a shape.                                                                                    |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`coarticulate`](#an.adapters.cutout.coarticulate.coarticulate)(keys, \*, fps[, end, ...])            | All the passes, in the order the module docstring gives.                                                                                                                                                                |
| [`condense`](#an.adapters.cutout.coarticulate.condense)(keys, \*, min_hold_s[, end])              | Enforce a minimum hold by voting, never by dropping.                                                                                                                                                                    |
| [`decay`](#an.adapters.cutout.coarticulate.decay)(keys, \*, decay_s[, rest, end])              | Give a shape `decay_s` to close: a rest arriving sooner than that after the shape before it is pushed out to `decay_s`, never past the next cue and never past `end` (a rest pushed to `end` is where the line closes). |
| [`lead`](#an.adapters.cutout.coarticulate.lead)(keys, \*, lead_s)                             | Anticipation: every cue moves `lead_s` earlier, clamped at 0.                                                                                                                                                           |
| [`merge_duplicates`](#an.adapters.cutout.coarticulate.merge_duplicates)(keys)                             | Drop a cue whose shape is the one already showing.                                                                                                                                                                      |
| [`suppress_weak`](#an.adapters.cutout.coarticulate.suppress_weak)(keys, \*, max_weak_s[, end])         | Drop a weak (low-dominance) cue that would show for less than `max_weak_s`.                                                                                                                                             |

### Classes

| [`Cue`](#an.adapters.cutout.coarticulate.Cue)(time, code[, intensity])   | One mouth-shape cue: when it starts, which shape, how loudly it wants the lips.   |
|---------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|

### *class* an.adapters.cutout.coarticulate.Cue(time, code, intensity=1.0)

Bases: `object`

One mouth-shape cue: when it starts, which shape, how loudly it wants the lips.

### an.adapters.cutout.coarticulate.DEFAULT_DECAY_S *: float* *= 0.12*

Time a shape is given to close before rest (JALI’s “120 ms to decay”).

### an.adapters.cutout.coarticulate.DEFAULT_DOMINANCE *: float* *= 0.5*

A shape not in the table (another convention’s code) is neither strong nor weak.

### an.adapters.cutout.coarticulate.DEFAULT_LEAD_S *: float* *= 0.08333333333333333*

Anticipation lead — two frames at 24 fps (art direction; JALI’s 120 ms is the ceiling).

### an.adapters.cutout.coarticulate.DEFAULT_MIN_HOLD_S *: float* *= 0.14*

The minimum hold, unchanged from the pre-an#97 compiler until measured.

### an.adapters.cutout.coarticulate.DOMINANCE *: dict[str, float]* *= {'A': 1.0, 'B': 0.3, 'C': 0.6, 'D': 0.8, 'E': 0.8, 'F': 0.9, 'G': 0.9, 'H': 0.3, 'X': 0.5}*

Per-shape dominance for Rhubarb’s letters. Order sourced, values ours.

### an.adapters.cutout.coarticulate.WEAK_BELOW *: float* *= 0.5*

Below this dominance a cue is “weak” for [`suppress_weak()`](#an.adapters.cutout.coarticulate.suppress_weak).

### an.adapters.cutout.coarticulate.close_after_speech(keys, , speech_end, rest='X')

Rest once speech is over: at `speech_end`, or just after the last
shape when a shape is keyed at or after it — never before a shape.

`speech_end` is where the line’s last word ends (`None`: the line does
not know its words, and nothing changes). A provider spreads a very short
word’s shapes over a minimum span, so a shape can start after its word’s
end; the rest then follows that shape, and [`decay()`](#an.adapters.cutout.coarticulate.decay) pushes it out to
`decay_s` after it (an#213 review). Nothing is inserted when the mouth
is already at rest there. `rest` is the TRACK’s rest code (a track keyed
in another convention closes with its own).

The evidence, “Bye.” timed 0.0–0.5 s in a 1.84 s clip:

* **Return type:**
  `list`[[`Cue`](#an.adapters.cutout.coarticulate.Cue)]

```pycon
>>> raw = [(0, "X"), (0, "A"), (0.167, "B"), (0.333, "C"), (1.838, "X")]
>>> [(c.time, c.code) for c in close_after_speech(raw, speech_end=0.5)]
[(0.0, 'X'), (0.0, 'A'), (0.167, 'B'), (0.333, 'C'), (0.5, 'X'), (1.838, 'X')]
>>> close_after_speech(raw, speech_end=None) == _cues(raw)
True
```

A 25 ms last word whose second shape starts after it ends:

```pycon
>>> [(c.time, c.code) for c in close_after_speech(
...     [(0, "X"), (1.0, "E"), (1.025, "B"), (2.0, "X")], speech_end=1.02)][-3:]
[(1.025, 'B'), (1.025000001, 'X'), (2.0, 'X')]
```

### an.adapters.cutout.coarticulate.coarticulate(keys, , fps, end=None, min_hold_s=0.14, lead_s=0.08333333333333333, decay_s=0.12, rest='X', speech_end=None)

All the passes, in the order the module docstring gives.

`speech_end` (where the last word ends, when the line knows its words)
closes the mouth there instead of at `end` (an#213):

* **Return type:**
  `list`[[`Cue`](#an.adapters.cutout.coarticulate.Cue)]

```pycon
>>> bye = [(0, "X"), (0, "A"), (0.167, "B"), (0.333, "C"), (1.838, "X")]
>>> [(round(c.time, 3), c.code) for c in coarticulate(bye, fps=24, end=1.838)][-2:]
[(0.28, 'C'), (1.755, 'X')]
>>> [(round(c.time, 3), c.code) for c in coarticulate(bye, fps=24, end=1.838, speech_end=0.5)][-2:]
[(0.28, 'C'), (0.5, 'X')]
```

(The shapes lead by two frames; the closing rest is placed after the lead,
at the word’s end, and the decay keeps it at least `decay_s` after the
last shape.)

```pycon
>>> raw = [(0.0, "X"), (0.30, "B"), (0.34, "A"), (0.38, "D"), (0.80, "X")]
>>> [(round(c.time, 3), c.code) for c in coarticulate(raw, fps=24, end=1.0)]
[(0.0, 'X'), (0.257, 'D'), (0.717, 'X')]
```

A track that ends on `rest` still does after the passes, at `end` when
the decay left no room before it (the compiler appends its own terminal
rest at the line’s end regardless — this is for every other caller):

```pycon
>>> [(round(c.time, 3), c.code) for c in coarticulate([(0, "X"), (0.3, "D"), (0.69, "C"), (0.71, "X")], fps=24, end=0.71)]
[(0.0, 'X'), (0.217, 'D'), (0.607, 'C'), (0.71, 'X')]
```

The knobs are validated up front — a negative lead or a zero hold is a
typo, not a style:

```pycon
>>> coarticulate(raw, fps=24, end=1.0, min_hold_s=0)
Traceback (most recent call last):
...
ValueError: min_hold_s must be > 0, got 0
```

### an.adapters.cutout.coarticulate.condense(keys, , min_hold_s, end=None)

Enforce a minimum hold by voting, never by dropping.

Windows of `min_hold_s` open at each cue that clears the previous window.
Every cue inside a window — the opener included — votes with the length of
its raw span **that falls inside the window** times its dominance
(Rhubarb’s “select shape with highest total duration within the candidate
range”, weighted); the winner shows for the window, placed at the window
start. A member whose span runs past the window’s end and did not win is
not lost: it opens the next window at the window’s end, delayed — that is
the hold doing its job. Ties go to the later arrival.

The defect the epic names, verbatim semantics of the old compiler loop —
‘A’ (the closure) and ‘D’ (the open vowel) are gone and a 40 ms ‘B’ holds
for 500 ms:

* **Return type:**
  `list`[[`Cue`](#an.adapters.cutout.coarticulate.Cue)]

```pycon
>>> raw = [(0.0, "X"), (0.30, "B"), (0.34, "A"), (0.38, "D"), (0.80, "X")]
>>> old = []
>>> for t, v in raw:
...     if old and (t - old[-1][0]) < 0.14:
...         continue
...     old.append((t, v))
>>> old
[(0.0, 'X'), (0.3, 'B'), (0.8, 'X')]
```

The vote in the window at 0.30: B (0.04 × 0.3) and A (0.04 × 1.0) lose to
D (0.06 in-window × 0.8), which shows at the window’s start:

```pycon
>>> [(c.time, c.code) for c in condense(raw, min_hold_s=0.14)]
[(0.0, 'X'), (0.3, 'D'), (0.8, 'X')]
```

A cue exactly at the window edge opens the next window, untouched — also
at the third edge, where `0.28 + 0.14` is a hair over `0.42` in binary:

```pycon
>>> [(c.time, c.code) for c in condense([(0.0, "X"), (0.14, "C"), (0.28, "D"), (0.42, "A")], min_hold_s=0.14)]
[(0.0, 'X'), (0.14, 'C'), (0.28, 'D'), (0.42, 'A')]
```

Without `end` the last cue shows forever, so it always survives (it opens
its own window when it loses one):

```pycon
>>> [(c.time, c.code) for c in condense([(0.0, "X"), (0.1, "A")], min_hold_s=0.14)]
[(0.0, 'X'), (0.14, 'A')]
```

Windows chain, so nothing is lost: the opening rest keeps its window
(0.10 of rest beats a 20 ms closure and 20 ms of F); F, running past the
window, opens the next one at 0.14 and wins it over the 40 ms of C inside
it; C in turn opens the window at 0.28:

```pycon
>>> [(c.time, c.code) for c in condense([(0.0, "X"), (0.10, "A"), (0.12, "F"), (0.20, "C"), (0.9, "X")], min_hold_s=0.14)]
[(0.0, 'X'), (0.14, 'F'), (0.28, 'C'), (0.9, 'X')]
```

A winner equal to the shape already showing is merged:

```pycon
>>> [(c.time, c.code) for c in condense([(0.0, "X"), (0.05, "B"), (0.10, "X")], min_hold_s=0.14)]
[(0.0, 'X')]
```

### an.adapters.cutout.coarticulate.decay(keys, , decay_s, rest='X', end=None)

Give a shape `decay_s` to close: a rest arriving sooner than that after
the shape before it is pushed out to `decay_s`, never past the next cue
and never past `end` (a rest pushed to `end` is where the line closes).

* **Return type:**
  `list`[[`Cue`](#an.adapters.cutout.coarticulate.Cue)]

```pycon
>>> [(round(c.time, 3), c.code) for c in decay([(0.0, "X"), (0.2, "D"), (0.25, "X"), (0.6, "B")], decay_s=0.12)]
[(0.0, 'X'), (0.2, 'D'), (0.32, 'X'), (0.6, 'B')]
>>> [(round(c.time, 3), c.code) for c in decay([(0.0, "X"), (0.2, "D"), (0.25, "X"), (0.30, "B")], decay_s=0.12)]
[(0.0, 'X'), (0.2, 'D'), (0.3, 'B')]
```

### an.adapters.cutout.coarticulate.lead(keys, , lead_s)

Anticipation: every cue moves `lead_s` earlier, clamped at 0.

Cues that collide at 0 collapse to the last one — the shape that is still
the state once the collision is over. An opening burst shorter than the
lead (`[(0, X), (0.02, A), (0.05, D), (0.07, X)]`) therefore never opens
the mouth; the hold would have refused a 70 ms word anyway, and the old
condenser did.

* **Return type:**
  `list`[[`Cue`](#an.adapters.cutout.coarticulate.Cue)]

```pycon
>>> [(round(c.time, 3), c.code) for c in lead([(0.0, "X"), (0.05, "D"), (0.5, "B")], lead_s=0.08)]
[(0.0, 'D'), (0.42, 'B')]
```

### an.adapters.cutout.coarticulate.merge_duplicates(keys)

Drop a cue whose shape is the one already showing.

* **Return type:**
  `list`[[`Cue`](#an.adapters.cutout.coarticulate.Cue)]

```pycon
>>> [(c.time, c.code) for c in merge_duplicates([(0, "X"), (0.1, "B"), (0.2, "B"), (0.3, "C")])]
[(0.0, 'X'), (0.1, 'B'), (0.3, 'C')]
```

### an.adapters.cutout.coarticulate.suppress_weak(keys, , max_weak_s, end=None)

Drop a weak (low-dominance) cue that would show for less than `max_weak_s`.

* **Return type:**
  `list`[[`Cue`](#an.adapters.cutout.coarticulate.Cue)]

```pycon
>>> raw = [(0.0, "X"), (0.20, "D"), (0.40, "B"), (0.43, "D"), (0.80, "X")]
>>> [(c.time, c.code) for c in suppress_weak(raw, max_weak_s=0.04)]
[(0.0, 'X'), (0.2, 'D'), (0.8, 'X')]
```

A weak cue that lasts is kept — this is not the minimum-hold pass:

```pycon
>>> [(c.time, c.code) for c in suppress_weak([(0.0, "X"), (0.2, "B"), (0.5, "D")], max_weak_s=0.04)]
[(0.0, 'X'), (0.2, 'B'), (0.5, 'D')]
```
