# an.bench.ledger

The ledger: three blocks that must never be mixed, and the guards that keep them apart.

`metrics` — numbers, each labelled **render-side** or **encode-side**. The
two families are blind to each other’s mutations by construction, and a
comparison that mixes them is comparing two different questions.

`tripwires` — change detectors. They fire on improvements and regressions
alike, so they count **zero** toward any criterion. A tripwire in the metrics
block is a boolean wearing a measurement’s clothes.

`provenance` — never gated, never counted. Everything needed to decide
whether two rows may be compared *at all*: the scene contract hash, the
resolved encode and decode commands, the mask parameters, the palette, and the
environment tuple split into a render side (**comparable on any machine** — the
pixels are ISA- and OS-invariant at a pinned Chromium build) and an encode side
(**machine-scoped** — a different x264 build moves the decoded stream by two
orders of magnitude, and a band wide enough to absorb that would swallow
`flat_field_deviation`’s entire crf18->23 signal).

Four value states, not two. `no change` and `null` are famously easy to
conflate, and conflating them lets any pre-encode statistic pad the witness
count for free:

### Module Attributes

| [`SCHEMA_VERSION`](#an.bench.ledger.SCHEMA_VERSION)     | Bumped when a reader could misinterpret an older row.   |
|---------------------------------------------------------------------|---------------------------------------------------------|
| [`INLINE_SPEC_FIELDS`](#an.bench.ledger.INLINE_SPEC_FIELDS) | Fields a per-scene row carries inline.                  |

### Functions

| [`build_ledger`](#an.bench.ledger.build_ledger)(\*, provenance, scenes)            | The whole row.                                                          |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`build_scene_block`](#an.bench.ledger.build_scene_block)(\*, provenance, metrics, ...) | Assemble one scene's three blocks, refusing anything unreadable.        |
| [`gated`](#an.bench.ledger.gated)(gate[, detail])                           | Shorthand: this number would be uninterpretable, and here is the gate.  |
| [`measured`](#an.bench.ledger.measured)(value, \*\*extra)                      | Shorthand: a real number.                                               |
| [`metric_declarations`](#an.bench.ledger.metric_declarations)()                           | The full declaration of every metric and tripwire, once per ledger row. |
| [`unavailable`](#an.bench.ledger.unavailable)(detail)                             | Shorthand: this check could not run, and here is why.                   |
| [`witnesses`](#an.bench.ledger.witnesses)(ledger_scene, mutation)               | Which metrics would count for `mutation`, grouped by family.            |
| [`write_ledger`](#an.bench.ledger.write_ledger)(ledger, path)                      | Write a row.                                                            |

### Classes

| [`Value`](#an.bench.ledger.Value)(value[, state, gate, detail, extra])   | One measured (or deliberately absent) number.   |
|-----------------------------------------------------------------------------------------------|-------------------------------------------------|

### Exceptions

| [`LedgerSchemaError`](#an.bench.ledger.LedgerSchemaError)   | A ledger row violates an invariant that would make it misreadable.   |
|----------------------------------------------------------------------|----------------------------------------------------------------------|

### an.bench.ledger.INLINE_SPEC_FIELDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('side', 'family', 'comparison_scope', 'reference', 'counts')*

Fields a per-scene row carries inline. Everything else about a metric — the
sentence, the notes, each prediction’s reason and reference — is identical
for every scene in a row and for every row, so it lives once in the
ledger-level `metric_declarations` block.

The split is not only size (it took a two-scene row from 54 KB to a third of
that, and an#38 quadruples the corpus). It is readability: a scene block you
can read is one where the numbers are not buried in the prose explaining
what the numbers are. What stays inline is exactly what
`an bench --compare` (an#40) keys on, so a comparison never has to consult
a second block to decide whether two rows may be compared at all.

### *exception* an.bench.ledger.LedgerSchemaError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A ledger row violates an invariant that would make it misreadable.

### an.bench.ledger.SCHEMA_VERSION *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

Bumped when a reader could misinterpret an older row. `an bench --compare`
(an#40) must refuse a version it does not understand rather than guess.

### *class* an.bench.ledger.Value(value, state='measured', gate=None, detail='', extra=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One measured (or deliberately absent) number.

### an.bench.ledger.build_ledger(, provenance, scenes)

The whole row.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.ledger.build_scene_block(, provenance, metrics, tripwires)

Assemble one scene’s three blocks, refusing anything unreadable.

Completeness is enforced in both directions. A metric the registry declares
but the row omits is a silently narrower panel; a metric the row carries
but the registry does not declare has no family, no side and no predicted
direction, so nothing downstream can count it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.ledger.gated(gate, detail='')

Shorthand: this number would be uninterpretable, and here is the gate.

* **Return type:**
  [`Value`](#an.bench.ledger.Value)

### an.bench.ledger.measured(value, \*\*extra)

Shorthand: a real number.

`nan` is refused rather than serialized: `json.dumps` emits the
non-standard literal `NaN`, which several strict readers reject, and a
metric whose mask was empty is an `unavailable`, not a number.

* **Return type:**
  [`Value`](#an.bench.ledger.Value)

### an.bench.ledger.metric_declarations()

The full declaration of every metric and tripwire, once per ledger row.

Carried IN the row rather than referenced, because `--compare` reads rows
written by older registries: a row from six months ago has to be
interpretable without checking out the commit that wrote it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.ledger.unavailable(detail)

Shorthand: this check could not run, and here is why.

* **Return type:**
  [`Value`](#an.bench.ledger.Value)

### an.bench.ledger.witnesses(ledger_scene, mutation)

Which metrics would count for `mutation`, grouped by family.

Reads the row rather than the registry, so an#41’s criterion is evaluated
against what was actually written down.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> witnesses({"metrics": {"m": {"family": "A",
...     "under_mutation": {"high_crf": {"counts": True}}}}}, "high_crf")
{'A': ['m']}
```

### an.bench.ledger.write_ledger(ledger, path)

Write a row. `sort_keys=True` so two rows diff line-for-line.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
