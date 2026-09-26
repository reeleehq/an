# an.bench.compare

`an bench --compare`: read two ledger rows, and **refuse when they are not comparable**.

Refusing is the feature. Two rows measured on different scenes, at different
resolutions, or on different x264 builds are not “one better and one worse” —
every number in them is **uninterpretable** relative to the other, and a number
reported across incomparable rows is worse than no number at all.

Three things here that are easy to get wrong in a way that still produces a
plausible verdict:

**A single per-metric sign mis-reports one of the two mutations.** The sharpness
family moves in *opposite* directions for AA-off and high-CRF, so the direction
is read per metric *and per mutation*, from the `under_mutation` block the row
already carries. Where the optimum is interior (`edge_transition_width` — under
1 is a staircase, 3+ is soft) there is no “better” direction at all, and the
comparison says `changed`, never `regression`. Inventing a band there would
be the silently-widened threshold this whole wave exists to prevent.

**The two sides have opposite comparison rules, and both are measured.**
Render-side rows compare across any machine: zero differing pixels across arm64
macOS, x86-64 Linux and arm64 Linux, across two SwiftShader JIT backends — \*at a
pinned Chromium build\*, which is why the browser build is itself a render-side
comparability key. Encode-side rows are **machine-scoped**: same ISA and x264
build is byte-identical, a different ISA moves the decoded stream a little, and a
different x264 build moves it by two orders of magnitude. A band wide enough to
absorb that would swallow `flat_field_deviation`’s entire crf18->23 signal
(0.0003 -> 0.0005), so the answer is to refuse, not to widen.

**There is no tolerance, and none is needed.** Every comparison is exact.
Measured: two consecutive `an bench` runs on the same machine produce
**bit-identical** numbers for every metric on all six scenes, and identical
`source_pixels_sha256` — the render is pinned and the encode is pinned, so a
delta of exactly zero is the normal case and any nonzero delta is a real change.
An epsilon here would only hide small real movements.

A fourth, quieter one: **a metric’s own declaration is a comparability key**.
If `family` or `optimum` changed between the two rows, the metric means
something different in each and the comparison is refused for that metric alone
— which is why every row carries its full `metric_declarations` block rather
than referencing the registry that happened to be installed.

### Module Attributes

| [`SUPPORTED_SCHEMA_VERSIONS`](#an.bench.compare.SUPPORTED_SCHEMA_VERSIONS)   | Row schema versions this comparer understands.                                                                                                                             |
|------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`SCENE_KEYS`](#an.bench.compare.SCENE_KEYS)                  | Scene-provenance fields that must match for ANY metric to be comparable.                                                                                                   |
| [`MASK_PARAM_PATHS`](#an.bench.compare.MASK_PARAM_PATHS)            | Mask **parameters**, addressed by path into the scene's `masks` block.                                                                                                     |
| [`RENDER_ENV_PATHS`](#an.bench.compare.RENDER_ENV_PATHS)            | Row-provenance paths that must match for a **render-side** metric.                                                                                                         |
| [`ENCODE_ENV_PATHS`](#an.bench.compare.ENCODE_ENV_PATHS)            | Row-provenance paths that must match for an **encode-side** metric.                                                                                                        |
| [`COMMON_ENV_PATHS`](#an.bench.compare.COMMON_ENV_PATHS)            | Row-provenance paths that must match for **either** side.                                                                                                                  |
| [`DECLARATION_KEYS`](#an.bench.compare.DECLARATION_KEYS)            | Per-metric declaration fields that must agree, or the metric means something different in each row.                                                                        |
| [`REQUIRED_FAMILIES`](#an.bench.compare.REQUIRED_FAMILIES)           | How many distinct causal families must move as declared for a mutation to count as caught.                                                                                 |
| [`CROSS_CHECKED_FIELDS`](#an.bench.compare.CROSS_CHECKED_FIELDS)        | Every field a row stores TWICE — inline on the metric and in `metric_declarations` — except `under_mutation`, whose nested shape gets `_prediction_disagreements` instead. |
| [`SCORING_FIELDS`](#an.bench.compare.SCORING_FIELDS)              | The fields of a per-mutation prediction that the verdict actually reads.                                                                                                   |

### Functions

| [`compare`](#an.bench.compare.compare)(before, after, \*[, mutation])   | Compare two ledger rows.                                            |
|-------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`direction_of`](#an.bench.compare.direction_of)(before, after)              | `increase` / `decrease` / `no_change` — exactly, with no tolerance. |
| [`format_comparison`](#an.bench.compare.format_comparison)(report)                | The human-readable digest.                                          |
| [`latest_rows`](#an.bench.compare.latest_rows)(\*[, root, count])           |                                                                     |
| [`load_row`](#an.bench.compare.load_row)(path)                           | Read one ledger row from disk.                                      |

### Exceptions

| [`ComparisonError`](#an.bench.compare.ComparisonError)   | The comparer was handed something it cannot read at all.   |
|--------------------------------------------------------------------|------------------------------------------------------------|

### an.bench.compare.COMMON_ENV_PATHS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...], ...]* *= (('render_kwargs',),)*

Row-provenance paths that must match for **either** side.

### an.bench.compare.CROSS_CHECKED_FIELDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('family', 'side', 'comparison_scope', 'reference')*

Every field a row stores TWICE — inline on the metric and in
`metric_declarations` — except `under_mutation`, whose nested shape gets
`_prediction_disagreements` instead. Both copies are written from one
registry at one moment, so a disagreement means the row was edited, and
`compare` reads the INLINE one.

Three defects of this exact class were found in one review pass, each on a
field that had been left out: `family` (moved a witness between families and
took `criterion_met_on` from three scenes to five), `under_mutation` (flipped
`contrary` to `as_declared`), and `comparison_scope` (compared an encode-side
metric across a different ISA). The list is therefore checked for
COMPLETENESS by a test rather than maintained by hand — see
`tests/test_bench_compare.py::test_every_doubly_stored_field_is_cross_checked`.

### *exception* an.bench.compare.ComparisonError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

The comparer was handed something it cannot read at all.

### an.bench.compare.DECLARATION_KEYS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('family', 'side', 'optimum', 'unit')*

Per-metric declaration fields that must agree, or the metric means something
different in each row. `optimum` decides which way “better” points and
`family` decides what an#41’s criterion counts.

### an.bench.compare.ENCODE_ENV_PATHS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...], ...]* *= (('environment', 'encode_side', 'isa'), ('environment', 'encode_side', 'x264_sei'), ('environment', 'encode_side', 'x264_argv'), ('environment', 'encode_side', 'pix_fmt'), ('environment', 'encode_side', 'scale_filter'), ('encode_command_source',), ('decode_commands',))*

Row-provenance paths that must match for an **encode-side** metric.

### an.bench.compare.MASK_PARAM_PATHS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...], ...]* *= (('masks', 'edge', 'operator'), ('masks', 'edge', 'threshold'), ('masks', 'flat', 'operator'), ('masks', 'flat', 'dilate_k'), ('masks', 'held', 'operator'), ('masks', 'ring', 'operator'), ('masks', 'render_edge', 'operator'), ('masks', 'render_edge', 'threshold'))*

Mask **parameters**, addressed by path into the scene’s `masks` block. The
counts and fractions beside them are measurements and are excluded.

### an.bench.compare.RENDER_ENV_PATHS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...], ...]* *= (('environment', 'render_side', 'chromium_build'), ('environment', 'render_side', 'playwright'), ('environment', 'render_side', 'launch_argv'))*

Row-provenance paths that must match for a **render-side** metric.
The Chromium build is here and not merely informational: the cross-arch
verdict measured ISA- and OS-invariance *at a pinned build*, and an#38’s
golden path keys on the build for the same reason. One bump has been measured
to move zero pixels (1187 -> 1223), so this refusal is precautionary rather
than a known break — and a deliberate re-bless is the intended response.

### an.bench.compare.REQUIRED_FAMILIES *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 3*

How many distinct causal families must move as declared for a mutation to
count as caught. an#41’s criterion, restated from the research: “>=3 metrics
from >=3 distinct causal families, evaluated per mutation, with a per-metric
per-mutation sign declared in advance”.

### an.bench.compare.SCENE_KEYS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('scene_contract_sha256', 'resolution', 'fps', 'n_frames', 'shot_order', 'palette_hex', 'tolerances')*

Scene-provenance fields that must match for ANY metric to be comparable.
Deliberately not the whole provenance block: that also carries per-run
*measurements* (mask pixel counts, `wall_seconds`, the golden diagnostics),
which change exactly when the render changes — i.e. when the two rows are
most worth comparing.

### an.bench.compare.SCORING_FIELDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('expect', 'counts', 'gate', 'state')*

The fields of a per-mutation prediction that the verdict actually reads.
`reason` is prose and is deliberately NOT here — the declarations block
carries it and the inline block drops it, so requiring it would refuse every
real row.

### an.bench.compare.SUPPORTED_SCHEMA_VERSIONS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), ...]* *= (1,)*

Row schema versions this comparer understands. A row it cannot read is
refused rather than guessed at — the whole point of the version field.

### an.bench.compare.compare(before, after, , mutation=None)

Compare two ledger rows. Returns a report; raises only on an unreadable row.

`mutation` selects the question. With one, the report answers an#41’s:
did the declared witnesses move in the declared direction, and did at least
three distinct causal families do so. Without one, it answers “is the second
row worse”, which only the one-sided metrics can answer at all.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.compare.direction_of(before, after)

`increase` / `decrease` / `no_change` — exactly, with no tolerance.

Two consecutive runs on one machine are bit-identical, so zero is the normal
delta and any nonzero one is real. Booleans compare as booleans: a tripwire
that went `True -> False` has not “decreased”.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> direction_of(1.0, 1.0)
'no_change'
>>> direction_of(True, False)
'decrease'
```

### an.bench.compare.format_comparison(report)

The human-readable digest. Refusals first, because they are the verdict.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.bench.compare.latest_rows(, root=None, count=2)

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

The most recent committed ledger rows, newest last — \*\*by 

```
`
```

generated_at\`\*\*.

Not by filename. Filenames are `<date>-<sha7>[-dirty].json`, so a filename
sort orders same-day rows by *sha hex*. On a Wave 3 PR the re-baseline and
the after-run are plausibly the same day, and when the after-commit’s sha
sorts lower a bare `an bench-compare` silently swaps before and after and
reports every improvement as a regression.

A row whose `generated_at` cannot be read sorts **before** every dated
one, so it is dropped as soon as two dated rows exist: a corrupt or
pre-schema file must never become the `after` row a verdict is drawn from.
The filename stays the tiebreak, which is what keeps a directory whose rows
all lack the key ordered by date.

`-dirty` rows are excluded: a row measured against uncommitted edits
describes no commit, and comparing one is comparing against nothing
nameable. `an bench --out` still lets a caller point at one explicitly.

### an.bench.compare.load_row(path)

Read one ledger row from disk.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
