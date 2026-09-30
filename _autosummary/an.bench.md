# an.bench

`an bench` — render a fixed corpus, compute a metrics panel, write one ledger row.

The instrument Wave 2 exists to build. Its job is not to say whether the
animation is good; it is to make a \*\*deliberate degradation move a number in a
direction declared in advance\*\*, so that a future regression is caught by
something other than someone noticing.

Three things about the panel that are easy to assume wrongly:

- **It is not the epic’s metric list.** All twelve originally-proposed metrics
  were refuted; every one here is a corrected form. `mean adjacent-frame
  SSIM` in particular is *out* — it moves the wrong way (0.958 at crf18 ->
  0.977 at crf51, because a crushed video is smoother), so shipping it would
  put a number in the ledger that rewards the degradation the gate exists to
  catch.
- \*\*Render-side and encode-side metrics are blind to each other’s mutations by
  construction\*\*, and are labelled so nothing mixes them. Render-side rows
  compare across any machine; encode-side rows are machine-scoped.
- **The vision judge is deliberately not here.** Not because its input is
  nondeterministic — over frozen frames it is perfectly reproducible — but
  because a cassetted judge is a *constant*, invariant to the code under test,
  so it can never move under a deliberate degradation.

Entry points: [`an.bench.run.run_bench()`](an.bench.run.md#an.bench.run.run_bench), and `an bench` on the CLI.

### Functions

| [`bless_scene`](#an.bench.bless_scene)(capture, \*, times, ...[, ...])       | Write one scene's golden frames and its bless record.                         |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`compare_scene`](#an.bench.compare_scene)(capture, \*, times, chromium_build) | Compare today's render against the committed goldens for one scene.           |
| [`decode_png`](#an.bench.decode_png)(data)                                  | Decode an 8-bit truecolour PNG to `(H, W, C)` uint8, `C` in `{3, 4}`.         |
| [`encode_png`](#an.bench.encode_png)(rgb, \*[, level])                      | Encode `(H, W, 3)` uint8 as an 8-bit truecolour PNG, every row filter 0.      |
| [`frame_key`](#an.bench.frame_key)(index)                                  | The filename stem for a frame, zero-padded so a directory listing sorts.      |
| [`pixels_sha256`](#an.bench.pixels_sha256)(rgb)                                | `sha256` over the decoded pixels — **shape and dtype included**.              |
| [`png_dimensions`](#an.bench.png_dimensions)(data)                              | `(width, height)` from a PNG's IHDR, without decoding a single pixel.         |
| [`read_png`](#an.bench.read_png)(path)                                    | `(H, W, 3)` uint8 for a PNG on disk, alpha dropped only if opaque.            |
| [`read_png_dimensions`](#an.bench.read_png_dimensions)(path)                         | `(width, height)` for a PNG on disk, reading only its header.                 |
| [`write_png`](#an.bench.write_png)(path, rgb, \*[, level])                 | Write `rgb` as a filter-0 PNG and **verify the round trip** before returning. |
| [`build_ledger`](#an.bench.build_ledger)(\*, provenance, scenes)              | The whole row.                                                                |
| [`build_scene_block`](#an.bench.build_scene_block)(\*, provenance, metrics, ...)   | Assemble one scene's three blocks, refusing anything unreadable.              |
| [`witnesses`](#an.bench.witnesses)(ledger_scene, mutation)                 | Which metrics would count for `mutation`, grouped by family.                  |
| [`run_bench`](#an.bench.run_bench)(\*[, scenes, out, keep_render, ...])    | Render the corpus, compute the panel, and (by default) write the row.         |
| [`format_panel`](#an.bench.format_panel)(ledger)                              | A human-readable digest of a row — the thing `an bench` prints.               |

### Classes

| [`MetricSpec`](#an.bench.MetricSpec)(key, family, unit, optimum, ...)     | One row of the panel.                                                      |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`Prediction`](#an.bench.Prediction)(expect[, counts, gate, reason, ...]) | What one metric is expected to do under one mutation, declared in advance. |
| [`Value`](#an.bench.Value)(value[, state, gate, detail, extra])      | One measured (or deliberately absent) number.                              |

### Exceptions

| [`GoldenError`](#an.bench.GoldenError)       | A bless was refused, or a committed golden is unusable.             |
|--------------------------------------------------------------------|---------------------------------------------------------------------|
| [`PngFormatError`](#an.bench.PngFormatError)    | A PNG this module deliberately does not decode, or a malformed one. |
| [`RegistryError`](#an.bench.RegistryError)     | A metric declaration violates one of the table's invariants.        |
| [`LedgerSchemaError`](#an.bench.LedgerSchemaError) | A ledger row violates an invariant that would make it misreadable.  |
| [`BenchError`](#an.bench.BenchError)        | The bench could not produce a row it would be honest to file.       |

### *exception* an.bench.BenchError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The bench could not produce a row it would be honest to file.

### *exception* an.bench.GoldenError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A bless was refused, or a committed golden is unusable.

### *exception* an.bench.LedgerSchemaError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A ledger row violates an invariant that would make it misreadable.

### *class* an.bench.MetricSpec(key, family, unit, optimum, predictions, sentence, role=None, reference='none', provisional=False, unreviewed=False, tripwire=False, requires='', notes=<factory>, sweep=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One row of the panel.

#### requires *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

What a scene must HAVE for this row to exist at all, or `""` when the
row applies to every scene (an#111).

The render-side panel rule is “nothing may be null on a real capture,
because a null render-side row is a blind panel”. That rule assumes
every metric could have been measured. `stage_min_plane_ratio_gap`
could not: a displacement ratio needs two planes moving at different
depths, and `single_character` has no planes at all — so its null is
structural, not a gap in the instrument.

Declared rather than hardcoded in the test, so the panel rule keeps
naming its own exceptions instead of a test file carrying a list the
registry does not know about.

#### sweep *: [Sweep](an.bench.registry.md#an.bench.registry.Sweep) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Set only on a hard-threshold counter (an#140); see `Sweep`.

### *exception* an.bench.PngFormatError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A PNG this module deliberately does not decode, or a malformed one.

Typed and specific on purpose: the alternative to refusing is returning a
plausible array, and a golden gate that compares a plausible array is worse
than one that does not run.

### *class* an.bench.Prediction(expect, counts=False, gate=None, reason='', reference=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one metric is expected to do under one mutation, declared in advance.

`expect=None` means **gated**: the number is uninterpretable rather than
good or bad, and `gate` says why. It is not “no change”.

### *exception* an.bench.RegistryError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A metric declaration violates one of the table’s invariants.

### *class* an.bench.Value(value, state='measured', gate=None, detail='', extra=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One measured (or deliberately absent) number.

### an.bench.bless_scene(capture, , times, chromium_build, reason, git, scene_contract_sha256, golden_note='', root=None)

Write one scene’s golden frames and its bless record. Refuses, loudly.

Every refusal here is a case where writing the file would produce a gate
that cannot fail:

- **no reason** — a re-bless with no recorded reason is the same failure as
  a silently widened threshold, which is the named failure mode this whole
  wave exists to prevent;
- **fewer than two frames** — one frame cannot notice a scene that renders
  its first instant correctly and then stops;
- **a pixel-identical pair** — measured on `promote_demo`: frame 0 and the
  `duration/2` frame differ by exactly zero pixels, so the obvious choice
  blesses one picture twice and the second golden tests nothing;
- **an unknown Chromium build** — the path keys on it, so without it the
  frames would be written under a name no future run could look up.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.build_ledger(, provenance, scenes)

The whole row.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.build_scene_block(, provenance, metrics, tripwires)

Assemble one scene’s three blocks, refusing anything unreadable.

Completeness is enforced in both directions. A metric the registry declares
but the row omits is a silently narrower panel; a metric the row carries
but the registry does not declare has no family, no side and no predicted
direction, so nothing downstream can count it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.compare_scene(capture, , times, chromium_build, root=None)

Compare today’s render against the committed goldens for one scene.

Returns a dict with `state` in `{"measured", "gated", "unavailable"}`,
the reduced numbers the ledger carries, and a per-frame record for
provenance. The reduction is **worst frame wins**: `identical` is the
conjunction and `min_ssim_win8` is the minimum, because a maximum or a
mean lets one clean frame hide a broken one, and this metric’s own name is
“the worst small window”.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.decode_png(data)

Decode an 8-bit truecolour PNG to `(H, W, C)` uint8, `C` in `{3, 4}`.

Refuses — rather than approximates — 16-bit, palette, greyscale and
interlaced images, naming what it found.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

```pycon
>>> import numpy as np
>>> a = np.array([[[1, 2, 3], [4, 5, 6]]], np.uint8)
>>> np.array_equal(decode_png(encode_png(a)), a)
True
```

### an.bench.encode_png(rgb, , level=9)

Encode `(H, W, 3)` uint8 as an 8-bit truecolour PNG, every row filter 0.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

```pycon
>>> import numpy as np
>>> data = encode_png(np.zeros((2, 3, 3), np.uint8))
>>> data[:8] == PNG_SIGNATURE
True
>>> decode_png(data).shape
(2, 3, 3)
```

### an.bench.format_panel(ledger)

A human-readable digest of a row — the thing `an bench` prints.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.bench.frame_key(index)

The filename stem for a frame, zero-padded so a directory listing sorts.

Keyed on the frame **index**, not the pinned time: the index is what names
the picture. A change to `fps` moves the index, which changes the path,
which makes the golden absent and therefore *gated* — loud, and pointing at
the right cause.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> frame_key(7)
'f0007'
```

### an.bench.pixels_sha256(rgb)

`sha256` over the decoded pixels — **shape and dtype included**.

Never over file bytes, for the reason in the module docstring. And never
over the raw buffer alone either: `tobytes()` carries no shape, so a
320x240 frame and a 240x320 one holding the same bytes hash identically,
and issue #38’s literal “the criterion is `sha256(decoded RGB array)`”
would report PASS on a transposed frame. Both orientations are live in this
corpus. [`an.bench.metrics.golden_comparison()`](an.bench.metrics.md#an.bench.metrics.golden_comparison) catches it separately via
its `shape_mismatch` branch; this makes the digest agree with the gate
rather than quietly disagreeing with it.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> import numpy as np
>>> a = np.arange(24, dtype=np.uint8)
>>> pixels_sha256(a.reshape(2, 4, 3)) == pixels_sha256(a.reshape(4, 2, 3))
False
```

### an.bench.png_dimensions(data)

`(width, height)` from a PNG’s IHDR, without decoding a single pixel.

Width first, matching the PNG header itself — and deliberately the opposite
order from [`read_png()`](#an.bench.read_png), which returns `(H, W, C)` like every other
array here. Getting it backwards produces a square-looking check that
passes on square frames only, so the order is asserted in the tests.

Cheap on purpose. The bench reads this for **every** frame on disk rather
than sampling one, because the failure it exists to catch — a render whose
frame size changed partway through — is exactly the one sampling misses.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]

```pycon
>>> import numpy as np
>>> png_dimensions(encode_png(np.zeros((240, 320, 3), np.uint8)))
(320, 240)
```

### an.bench.read_png(path)

`(H, W, 3)` uint8 for a PNG on disk, alpha dropped only if opaque.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.bench.read_png_dimensions(path)

`(width, height)` for a PNG on disk, reading only its header.

A 1080p frame is megabytes and its declared size is in the first 24 of
them. Reading only those is what makes checking every frame of every shot
free rather than a second full decode of the corpus.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]

### an.bench.run_bench(, scenes=None, out=None, keep_render=None, write=True, bless='', golden_root=None, lossless_scratch_root=None)

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

### an.bench.witnesses(ledger_scene, mutation)

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

### an.bench.write_png(path, rgb, , level=9)

Write `rgb` as a filter-0 PNG and **verify the round trip** before returning.

The verification is not defensive noise: it is the only thing standing
between a bug in this module’s own encoder and a committed golden that
silently disagrees with the frame it was blessed from. Research §3 asks for
exactly this — “assert the round trip at bless time against the in-memory
screenshot pixels, so a bug in `an`’s own encoder cannot hide”.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### Modules

| [`capture`](an.bench.capture.md#module-an.bench.capture)         | Render one corpus fixture into a throwaway copy, and hand back its artifacts.                 |
|------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| [`compare`](an.bench.compare.md#module-an.bench.compare)         | `an bench --compare`: read two ledger rows, and **refuse when they are not comparable**.      |
| [`contract`](an.bench.contract.md#module-an.bench.contract)       | `scene_contract_sha256`: the fact that decides whether two rows are comparable.               |
| [`corpus`](an.bench.corpus.md#module-an.bench.corpus)           | The bench corpus: which projects are measured, and what each must actually render.            |
| [`environment`](an.bench.environment.md#module-an.bench.environment) | The environment tuple — the fields that decide whether two rows may be compared.              |
| [`golden`](an.bench.golden.md#module-an.bench.golden)           | The golden gate: committed frames, compared on **decoded pixels**.                            |
| [`imageio`](an.bench.imageio.md#module-an.bench.imageio)         | The pinned ffmpeg decodes, and the lossless leg every encode-side metric is measured against. |
| [`ledger`](an.bench.ledger.md#module-an.bench.ledger)           | The ledger: three blocks that must never be mixed, and the guards that keep them apart.       |
| [`masks`](an.bench.masks.md#module-an.bench.masks)             | Every mask the panel is computed over, and the recorded operator for each.                    |
| [`metrics`](an.bench.metrics.md#module-an.bench.metrics)         | The metric panel: pure numpy, no I/O, no subprocess.                                          |
| [`mutants`](an.bench.mutants.md#module-an.bench.mutants)         | The guard mutants: "I mutation-tested it" as a runnable artifact, not a claim.                |
| [`mutations`](an.bench.mutations.md#module-an.bench.mutations)     | The levers: deliberate, declared changes through seams the shipped code already has.          |
| [`palette`](an.bench.palette.md#module-an.bench.palette)         | Derive the set of colours a compiled shot declared — never hand-pin it.                       |
| [`paths`](an.bench.paths.md#module-an.bench.paths)             | Where the bench reads its corpus from and writes its ledger to.                               |
| [`png`](an.bench.png.md#module-an.bench.png)                 | A filter-0 PNG writer and a full-filter reader — numpy and stdlib only.                       |
| [`registry`](an.bench.registry.md#module-an.bench.registry)       | The metric declaration table — what each number is, and which way it should move.             |
| [`run`](an.bench.run.md#module-an.bench.run)                 | `run_bench`: render the corpus, compute the panel, write one ledger row.                      |
| [`stage`](an.bench.stage.md#module-an.bench.stage)             | Measuring a pan: does the stage move as planes, or as one rigid image?                        |
