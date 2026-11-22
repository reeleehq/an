# an.ir.dialogue

Where each dialogue line of a shot will play (an#767): the layout `an validate` and the genres’ checks share.

[`dialogue_layout()`](#an.ir.dialogue.dialogue_layout) is the audio pipeline’s own rule
([`an.ir.schema.Dialogue.planned_start()`](an.ir.schema.html.md#an.ir.schema.Dialogue.planned_start): a line’s `at`, else back to back
after the previous line plus its `pause`) over each line’s real duration when
it was synthesized, else the offline voice’s estimate. A check that judges a
line by when it plays (a speaker’s eyeline, a line run past its shot, two lines
in one mouth) reads it here, never the stamped `start`, which a pause edited
since the last synthesis has made stale.

```pycon
>>> from an.ir.schema import Dialogue, Shot
>>> shot = Shot(id="s", duration=9.0, dialogue=[
...     Dialogue(speaker="a", text="hi", duration=1.0),
...     Dialogue(speaker="b", text="bye", duration=0.5, pause=0.25),
... ])
>>> [(p.k, p.start, p.end, p.estimated) for p in dialogue_layout(shot)]
[(0, 0.0, 1.0, False), (1, 1.25, 1.75, False)]
```

### Functions

| [`dialogue_layout`](#an.ir.dialogue.dialogue_layout)(shot, \*[, tempo_of])   | A [`LinePlacement`](#an.ir.dialogue.LinePlacement) for each dialogue line of `shot`, in order.   |
|------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|

### Classes

| [`LinePlacement`](#an.ir.dialogue.LinePlacement)(k, line, start, end, estimated)   | One line of a shot and where it plays (shot-local seconds).   |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------|

### *class* an.ir.dialogue.LinePlacement(k, line, start, end, estimated)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

One line of a shot and where it plays (shot-local seconds).

A tuple, so `for k, line, start, end, estimated in dialogue_layout(shot)`
reads it as the private layout it replaces did.

#### end *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Alias for field number 3

#### estimated *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether `end` comes from the offline estimate (the line has no audio yet).

#### k *: [int](https://docs.python.org/3/builtins/functions.html#int)*

The line’s index in `shot.dialogue`.

#### line *: [Any](https://docs.python.org/3/library/typing.html#typing.Any)*

Alias for field number 1

#### start *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Alias for field number 2

### an.ir.dialogue.dialogue_layout(shot, , tempo_of=None)

A [`LinePlacement`](#an.ir.dialogue.LinePlacement) for each dialogue line of `shot`, in order.

A line synthesized plays for its `duration`; one not yet synthesized for
the offline voice’s estimate ([`an.audio.offline_tts.estimate_speech_duration()`](an.audio.offline_tts.html.md#an.audio.offline_tts.estimate_speech_duration))
divided by its voice’s `tempo`, `tempo_of(line)` (an#265: the effect
applies under every provider; default 1).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`LinePlacement`](#an.ir.dialogue.LinePlacement)]
