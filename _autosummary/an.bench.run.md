# an.bench.run

`run_bench`: render the corpus, compute the panel, write one ledger row.

\*\*Every encode-side metric is measured against a lossless (`-qp 0`) encode of
the same frames, not against a second conversion of the PNGs.\*\* That is a
correction, and CI is what made it: the PNG conversion agrees with the
encoder’s own exactly on ffmpeg 8.1 and disagrees by mean 0.63 / max 5 on the
Linux runner’s older build — 42% of `coded_luma_edge_error`’s whole crf23 value,
which would have been measured as encoder damage on that machine and as nothing
on this one. `-qp 0` is lossless, so its decoded luma **is** the plane libx264
received, on any build. Referencing to it removes the assumption rather than
widening it. See [`an.bench.imageio`](an.bench.imageio.md#module-an.bench.imageio).

The PNG conversion is still performed and its distance from the encoder’s input
is recorded as `png_to_encoder_input_luma` — that number is the build
dependence, and it belongs in provenance rather than inside a gate.

### Module Attributes

| [`GOLDEN_METRIC_KEY`](#an.bench.run.GOLDEN_METRIC_KEY)              | Family B's two rows, one in each block.                                                                                                                                                         |
|---------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`MIN_PINNED_FRAMES_FOR_PAIRWISE`](#an.bench.run.MIN_PINNED_FRAMES_FOR_PAIRWISE) | A pairwise minimum needs two frames; every fixture pins at least two, so on a real capture this row is always measured (the render-side panel may not be null — `tests/test_bench_capture.py`). |
| [`STAGE_METRIC_KEY`](#an.bench.run.STAGE_METRIC_KEY)               | The pan measurement (an#111).                                                                                                                                                                   |
| [`STAGE_MIN_RATIO_GAP`](#an.bench.run.STAGE_MIN_RATIO_GAP)            | The floor the tripwire fires below, set at HALF the first bless's measured minimum — the `expression_min_pairwise_changed_px` precedent followed literally.                                     |
| [`JUST_BLESSED_DETAIL`](#an.bench.run.JUST_BLESSED_DETAIL)            | Said when a run blessed the goldens it would otherwise have compared against.                                                                                                                   |

### Functions

| [`conversion_distance`](#an.bench.run.conversion_distance)(frames_dir, ...)              | How far this build's PNG->YUV conversion sits from the encoder's own.                                                                                                             |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`format_panel`](#an.bench.run.format_panel)(ledger)                              | A human-readable digest of a row — the thing `an bench` prints.                                                                                                                   |
| [`lossless_reference`](#an.bench.run.lossless_reference)(frames_dir, fps, out, \*, ...) | Encode the frames losslessly and return the decode — the encoder's input.                                                                                                         |
| [`naming_git_state`](#an.bench.run.naming_git_state)(git, \*, blessed, root)          | Which git state NAMES the row: the tree the run **left**, not the one it read.                                                                                                    |
| [`pinned_frames_min_pairwise_changed_px`](#an.bench.run.pinned_frames_min_pairwise_changed_px)(...)        | `expression_min_pairwise_changed_px` for one scene: decode the pinned frames from today's render and take the minimum over every pair of the count of pixels that differ (an#98). |
| [`run_bench`](#an.bench.run.run_bench)(\*[, scenes, out, keep_render, ...])    | Render the corpus, compute the panel, and (by default) write the row.                                                                                                             |
| [`shot_policy_provenance`](#an.bench.run.shot_policy_provenance)(shots)                     | The per-shot COMPILE POLICIES a scene rendered under, keyed by shot id.                                                                                                           |
| [`viseme_keyframes_per_second`](#an.bench.run.viseme_keyframes_per_second)(scene_json)           | Viseme keyframes per second of dialogue in a compiled shot, or `None` when nothing speaks (an#97).                                                                                |

### Exceptions

| [`BenchError`](#an.bench.run.BenchError)   | The bench could not produce a row it would be honest to file.   |
|---------------------------------------------------------------|-----------------------------------------------------------------|

### *exception* an.bench.run.BenchError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The bench could not produce a row it would be honest to file.

### an.bench.run.GOLDEN_METRIC_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'min_ssim_win8_vs_golden'*

Family B’s two rows, one in each block. Named here because the golden result
fills both from one comparison, and a reader has to be able to see that the
boolean and the number are the same evidence read two ways.

### an.bench.run.JUST_BLESSED_DETAIL *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'this run WROTE these goldens, so comparing against them is a tautology: the identity holds by construction and no code could have failed it. Run \`an bench\` again, without --bless, for a comparison that can fail.'*

Said when a run blessed the goldens it would otherwise have compared against.

### an.bench.run.MIN_PINNED_FRAMES_FOR_PAIRWISE *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

A pairwise minimum needs two frames; every fixture pins at least two, so on
a real capture this row is always measured (the render-side panel may not
be null — `tests/test_bench_capture.py`).

### an.bench.run.STAGE_METRIC_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'stage_min_plane_ratio_gap'*

The pan measurement (an#111). Metric and tripwire come from ONE measurement,
as the golden pair does: the boolean and the number must be the same evidence
read two ways, or a reader has to reconcile them.

### an.bench.run.STAGE_MIN_RATIO_GAP *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.1875*

The floor the tripwire fires below, set at HALF the first bless’s measured
minimum — the `expression_min_pairwise_changed_px` precedent followed
literally.

Measured on `stage_pan` at the first bless: **0.375**. Ratios are taken
against the largest mover, so depths 0.25 / 1.0 / 2.0 report as
0.125 / 0.5 / 1.0 and the closest pair is far/mid. (An earlier draft of this
comment said 0.75, which is the same measurement taken against the
`depth == 1` plane — a reference the pixel half cannot see, which is why
`_reference` is now always the largest mover.)

### an.bench.run.conversion_distance(frames_dir, lossless_mp4, , height, width, frames)

How far this build’s PNG->YUV conversion sits from the encoder’s own.

Recorded, never gated. It was a gate — a hard equality — and it failed on
the Linux runner while passing here, which is precisely the shape of a
machine-dependent fact masquerading as a universal one. Now the metrics no
longer depend on it, and the number is kept because it is the thing that
will explain a future cross-build surprise.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.run.format_panel(ledger)

A human-readable digest of a row — the thing `an bench` prints.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.bench.run.lossless_reference(frames_dir, fps, out, , delivered)

Encode the frames losslessly and return the decode — the encoder’s input.

Returned as a path rather than an array so the caller controls its
lifetime; every encode-side reference comes from here.

`delivered` is the delivered mp4 this leg is the reference FOR, and
passing it is what makes the leg’s pixel format match — \*\*probed off the
file rather than re-derived\*\* (an#72). Re-deriving is not enough: the
delivered encode resolves its format from `RenderContext.pix_fmt` *or*
from `render.DEFAULT_PIX_FMT`, so a leg that consults the global tracks
the bench’s lever and silently misses `an render --pix-fmt yuv444p`,
which sets the context instead. Only the file knows which seam won.

`delivered` is keyword-only and has **no default**, deliberately — the
same argument `imageio._reshape` makes for its own `frames`: a default here
would let a caller opt out of the match by omission, and the failure is
invisible (a 4:2:0 reference silently measuring a 4:4:4 delivery). Passing
`None` explicitly means “no delivered file to match” and falls back to the
module default; that is right for a caller building a reference for its own
sake and wrong for the bench, which always has the file in hand.

### an.bench.run.naming_git_state(git, , blessed, root)

Which git state NAMES the row: the tree the run **left**, not the one it read.

[`run_bench()`](#an.bench.run.run_bench) reads `git_state` once, *before* the corpus loop,
because that is the tree the pixels came from. A `--bless` run then WRITES
into that same tree inside the loop — the golden PNGs, and a bless record
whose `blessed_at` moves on every run — so by the time the row is named
the two are no longer one fact.

Named under the pre-bless state, a bless on a clean tree lands as
`<date>-<sha>.json`: a filename claiming a commit whose tree that very run
then modified, which is exactly what the `-dirty` suffix exists to prevent
([`an.bench.paths.ledger_path()`](an.bench.paths.md#an.bench.paths.ledger_path)). So the row records both — `git` is
what rendered, `git_after_bless` is what the run left behind — and the
*filename* follows the second. A non-bless run re-reads nothing.

Deliberately a plain function of `blessed` rather than an inline
conditional: it is the whole of the fix, and a guard for it must not have to
render the corpus to reach it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.run.pinned_frames_min_pairwise_changed_px(capture, times)

`expression_min_pairwise_changed_px` for one scene: decode the pinned
frames from today’s render and take the minimum over every pair of the
count of pixels that differ (an#98). On a two-frame scene that is the
pair’s own change; `unavailable`, never zero, only when a scene pins a
single frame, which the fixture rule forbids.

* **Return type:**
  [`Value`](an.bench.ledger.md#an.bench.ledger.Value)

### an.bench.run.run_bench(, scenes=None, out=None, keep_render=None, write=True, bless='', golden_root=None, lossless_scratch_root=None)

Render the corpus, compute the panel, and (by default) write the row.

`bless` is the **reason** a re-bless is being made, and passing it is what
turns the run into a bless. One argument rather than a `--bless` flag plus
a `--reason` string, so “blessed with no recorded reason” — the failure
this rule exists to prevent — is not expressible.

`lossless_scratch_root` is forwarded to `_lossless_scratch_dir()` for
every scene (an#143) — a caller may point it at a shared parent to prove
that two concurrent lossless-leg encodes still get distinct scratch
directories under it; production code has no reason to pass it.

`golden_root` redirects where goldens are read and written, and it exists
because without it a test of the bless path has no choice but to overwrite
the committed corpus. That is not hypothetical: the first version of an#38’s
bless test did exactly that, replacing a real bless record’s reason with the
test’s own.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.run.shot_policy_provenance(shots)

The per-shot COMPILE POLICIES a scene rendered under, keyed by shot id.

Additive scene-provenance facts read off each staged `scene_json`’s
`meta`; `shots` is any iterable of objects with `shot_id` and
`scene_json` (a [`ShotCapture`](an.bench.capture.md#an.bench.capture.ShotCapture), or a stand-in).

- `blink_phases` (an#88): the per-entity blink phase each shot was
  compiled with. A renamed corpus character re-phases every blink and
  moves every pixel metric; this makes that a visible diff in the row
  instead of an unexplained shift.
- `step_hz` (an#89): the stepped-timing policy each shot’s tweens were
  compiled under; `None` = smooth (the meta key is absent then, by the
  serializer). Stepping moves `scene_contract_sha256` by construction —
  the resampled keyframes ARE the contract — and this says the movement
  was a timing policy, not a mystery.

```pycon
>>> from types import SimpleNamespace as NS
>>> shot_policy_provenance([NS(shot_id="s1", scene_json={"meta": {"step_hz": 12.0, "blink_phases": {"a": 0.5}}}),
...                         NS(shot_id="s2", scene_json={"meta": {}})])
{'blink_phases': {'s1': {'a': 0.5}, 's2': {}}, 'step_hz': {'s1': 12.0, 's2': None}, 'viseme_keyframes_per_second': {'s1': None, 's2': None}}
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.bench.run.viseme_keyframes_per_second(scene_json)

Viseme keyframes per second of dialogue in a compiled shot, or `None`
when nothing speaks (an#97).

Counted over the `__viseme__` clips: keyframes minus one per channel
(the trailing rest is an invariant, not a decision — today’s emission has
one channel per clip), over the clips’ summed durations, which are the
frame-ceiled windows rather than the lines’ exact lengths (a small
downward bias, the same for every row). Keyframes, not distinct shapes — a repeated code (the carried
rest before the terminal one) counts. The co-articulation passes bring
this below the RAW provider track’s rate; against the old drop-not-hold
condenser it can rise, because that loop was cheaper only by dropping
shapes. Recorded as provenance rather than a panel metric because no lever
in the registry moves it.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> viseme_keyframes_per_second({"animations": {}})
>>> viseme_keyframes_per_second({"animations": {"__viseme__s_0_m": {"duration": 2.0,
...     "channels": [{"keyframes": [{"time": 0}, {"time": 0.5}, {"time": 1.0}, {"time": 2.0}]}]}}})
1.5
```
