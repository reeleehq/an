# an.stage.counters

A counter, lowered at compile: a number that reads as text (an#342, T2 of an#331).

A counter block is a text block whose document declares `counter: {format,
start}` ([`an.stage.text.Counter`](an.stage.text.html.md#an.stage.text.Counter)). In the IR its number is an ordinary
channel, authored as `tween <id> value a→b` and `set <id> value v`; what the
renderer sees is a replacement set (an#341): one `block_0` drawing per string
the frames show, swapped by `set text <key>`. The number never reaches the
runtime, which has no `value` case.

The lowering is the stage’s `counters` compile pass. It runs after every pass
that can contribute a `value` action (a genre pass adds them to
`state.extra_actions` before the `actions` pass) and before the `actions`
pass, whose swap check reads the vocabulary; `tests/test_text_counter.py`
pins that order against the registry. For each counter block it:

1. compiles the block’s `value` leaves as one numeric channel with the
   compiler’s own clip builder (`an.stage.compile._compile_actions()`), so
   easings, `step_hz`, the set-hold rule and a from-less tween’s start are
   exactly those of every other channel;
2. samples that channel on the frame grid `i / fps` (a `step_hz` shot’s
   channel is already stepped, so its grid is honoured by construction);
3. formats each sample ([`an.formats`](an.formats.html.md#module-an.formats)), typesets every distinct string once
   and rebuilds the block as a `texts` set whose rest is the first frame’s
   string;
4. replaces each `value` leaf by a `delay` of the same length (so no
   sequence around it moves) and adds a `set <id>/block_0 text <key>` half a
   frame before the first frame showing each new string (the captions’ rule,
   so no float disagreement about `i / fps` moves a boundary a frame).

A counter with no `start` shows its first action’s value until then; a
from-less tween with neither a `start` nor an earlier `value` action, and a
counter with neither a `start` nor any `value` action, are compile errors
naming both. A shot with no counter block is untouched.

### Module Attributes

| [`VALUE_PROPERTY`](#an.stage.counters.VALUE_PROPERTY)     | The block-scoped property a counter's number is authored on.   |
|---------------------------------------------------------------------|----------------------------------------------------------------|
| [`COUNTER_KEY_PREFIX`](#an.stage.counters.COUNTER_KEY_PREFIX) | What every generated key of a counter's set starts with.       |

### Functions

| [`lower_counters`](#an.stage.counters.lower_counters)(state)             | The `counters` pass (see the module docstring).                                                                                    |
|------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| [`counter_blocks`](#an.stage.counters.counter_blocks)(shot, props_store) | `{entity id: block}` for every text block of `shot` that declares a counter (an unresolvable document is the builder's to report). |

### an.stage.counters.COUNTER_KEY_PREFIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'v_'*

What every generated key of a counter’s set starts with.

### an.stage.counters.VALUE_PROPERTY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'value'*

The block-scoped property a counter’s number is authored on. NOT a global
authorable property (an#342): a genre’s own `value` is untouched.

### an.stage.counters.counter_blocks(shot, props_store)

`{entity id: block}` for every text block of `shot` that declares a
counter (an unresolvable document is the builder’s to report).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), `_CounterBlock`]

### an.stage.counters.lower_counters(state)

The `counters` pass (see the module docstring). A no-op for a shot
with no counter block, which is every shot written before an#342.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
