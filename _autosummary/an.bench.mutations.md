# an.bench.mutations

The levers: deliberate, declared changes through seams the shipped code already has.

This is the other half of the instrument. `an bench` records numbers; these
change the pipeline on purpose so a test can check the numbers move the way the
registry declared **in advance**. A metric that never moves under any lever is
decoration, and the only way to know which is which is to pull one.

**Two of the three are degradations and the third is an improvement**, and that
asymmetry is the point rather than an untidiness. `high_crf` and
`disabled_aa` make the picture worse; `supersample` makes it better. A panel
that has only ever been shown things getting worse cannot tell an improvement
from a regression — run as a plain commit-to-commit diff, a k=2 supersample
reports **2 false regressions** (`off_palette_pixel_fraction` rises as blends
multiply, `min_ssim_win8_vs_golden` falls away from the golden) and \*\*7
unearned improvements\*\* (every family C/D/E/G metric whose mask derives from the
source frames: gates live inside `Prediction`, which exists only per declared
mutation, so with `mutation=None` no gate is consulted and a softer source
shrinks each mask to its easiest members). Declared as a lever, none of that
happens. So what a lever has to be is **declared in advance**, not bad — and the
word “degradations” in the old first line was quietly making the stronger, false
claim (an#56).

**Two of the three levers have no production knob, and that is deliberate.**
The third, `supersample`, has had one since an#58 (`an render --supersample
N`) and the lever now FORCES the product’s own parameter rather than carrying
a second copy of the resolve — a lever that reproduces the code it examines is
examining itself. The inverse also exists: `step_hz` (an#89) is a product
knob with **no lever**, on measurement — a per-frame instrument cannot judge a
temporal choice (the `an-dev-bench` skill’s table has the numbers). Each lever
reaches an existing seam from the outside:

- `high_crf` rebinds `an.adapters.cutout.render.DETERMINISTIC_X264_ARGS`.
  `_ffmpeg_mux` reads that name as a module global at call time, so the
  rebinding reaches the delivered encode. It does **not** reach
  `an.bench.imageio.lossless_encode_command`, which bound the tuple at import
  — and that is exactly right: the lossless reference must stay lossless, or
  every encode-side metric would be measured against a moving target and the
  lever would produce beautiful numbers about nothing.
- `disabled_aa` copies the staged runtime, flips PixiJS’s `antialias` in the
  copy, and rebinds `an.adapters.cutout.render.runtime_dir`. The shipped
  `runtime.js` is never written to.
- `supersample` reaches the SAME runtime seam — `resolution: k,
  autoDensity: false` in the Pixi application options — and then a second one
  it cannot do without: it rebinds
  `an.adapters.cutout.render._capture_frames` so the k-times PNGs are
  block-mean-resolved back to the declared size **in the frame stage**, before
  ffmpeg or the metrics or the golden gate read them. That is not tidiness. A
  lever must measure what the product will produce, and everything downstream
  reads the declared resolution off the STAGED SCENE, never off the files.

A knob in the product is a cost each of the other two levers avoids: it has to
be documented, defended, and kept from being switched on by accident — which is
why supersampling is opt-in and off is free.

**Each lever verifies that it applied.** A lever that silently failed to take
produces a run in which nothing moved — which reads exactly like an instrument
that cannot see it, and sends the reader to fix the wrong thing. So
`verify_applied` is part of the declaration rather than a courtesy, and the
two levers verify it in different places for a structural reason: the encode
argv is recorded in the ledger row, and the runtime is not (the runtime is the
code under test, not a comparability key — see
`an.bench.registry.MUTATION_TOUCHES`).

### Module Attributes

| [`HIGH_CRF`](#an.bench.mutations.HIGH_CRF)       | measured on the CRF ladder, 40 gives C x8.4, D x8.0 and F -42% on `single_character` — large, unambiguous, and still a rate a human might plausibly ship.                                                                         |
|-----------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`AA_ON`](#an.bench.mutations.AA_ON)          | The exact text the AA lever flips, and where.                                                                                                                                                                                     |
| [`SUPERSAMPLE_K`](#an.bench.mutations.SUPERSAMPLE_K)  | The supersample lever's factor, read at call time so a test can move it.                                                                                                                                                          |
| [`APP_OPEN`](#an.bench.mutations.APP_OPEN)       | The exact text the supersample lever anchors to, and what it inserts.                                                                                                                                                             |
| [`STAGING_IGNORE`](#an.bench.mutations.STAGING_IGNORE) | Excluded from the staged copy so the staged tree is a pure function of the shipped source and the patch — which is what lets `_verify_supersample` RECOMPUTE the digest it expects instead of settling for "not the shipped one". |
| [`LEVERS`](#an.bench.mutations.LEVERS)         | The levers, keyed by the mutation name the registry declares.                                                                                                                                                                     |

### Functions

| [`mutated_row`](#an.bench.mutations.mutated_row)(name, \*\*run_kwargs)   | Render the corpus with one lever pulled, and prove the lever took.   |
|--------------------------------------------------------------------------------------|----------------------------------------------------------------------|

### Classes

| [`Lever`](#an.bench.mutations.Lever)(name, side, what, why, apply[, verify_row])   | One deliberate, declared change to the pipeline, with the evidence that it took.   |
|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|

### Exceptions

| [`MutationError`](#an.bench.mutations.MutationError)   | A lever could not be applied, or applied and left no trace.   |
|------------------------------------------------------------------|---------------------------------------------------------------|

### an.bench.mutations.AA_ON *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'antialias: true'*

The exact text the AA lever flips, and where. Pinned as a literal so a
rename in `runtime.js` fails here — loudly, at the lever — rather than
producing a “mutation” that changes nothing.

### an.bench.mutations.APP_OPEN *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'const resolution = Math.max(1, (NS.anSupersample | 0) || 1);'*

The exact text the supersample lever anchors to, and what it inserts. Pinned
for the same reason `AA_ON` is: a reformat of the Pixi options object must
fail here rather than produce a “mutation” that renders at 1x and then reads
as an instrument that cannot see a supersample. `app = new PIXI.Application({`
and NOT `new PIXI.Application(`: the shorter form occurs twice in
`runtime.js` — the second is inside a comment — and a two-hit anchor would
patch prose.

**\`autoDensity: false\` is load-bearing and is the whole plumbing finding.**
With it `true`, Pixi sets the canvas CSS size to the LOGICAL size and
Chromium composites the k-times backbuffer down before the screenshot — a
blind browser downscale with no filter choice and no record of having
happened, i.e. the `device_scale_factor` failure wearing the name that most
suggests it is the right one. Measured on `aa_probe`, declared 320x240:
neither key -> 320x240 PNGs; `resolution: 2, autoDensity: false` -> 640x480;
`resolution: 2, autoDensity: true` -> 320x240. Neither key is in the shipped
options today, so the engine default `RESOLUTION: 1` applies silently and
both have to be introduced.
Since an#58 the product owns `resolution` / `autoDensity: false` and reads
the factor from an injected global, so the lever \*\*overrides the line that
reads it\*\* rather than writing a second copy of the product’s Pixi options.
A lever that reproduces the code it is examining is examining itself.

Injecting the global does NOT work and the reason is worth keeping: the
product sets `window.anSupersample` from `ctx.supersample` immediately before
`anLoadScene`, so it would overwrite whatever the lever put there. Caught by
an#54’s shape guard — 160x120 frames against a 320x240 declaration — which is
what that guard is for.

### an.bench.mutations.HIGH_CRF *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '40'*

measured on the CRF
ladder, 40 gives C x8.4, D x8.0 and F -42% on `single_character` — large,
unambiguous, and still a rate a human might plausibly ship. 51 is
pathological, and a lever nobody would ever pull by accident is a weaker
proxy for the regressions this instrument exists to catch.

* **Type:**
  The CRF the encoder lever raises to. 40 rather than 51

### an.bench.mutations.LEVERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Lever](#an.bench.mutations.Lever)]* *= {'disabled_aa': Lever(name='disabled_aa', side='render', what='build the PixiJS application with multisampling off', why='moves the render-side families and fires the golden tripwire. Its effect is scene-dependent by measurement, not by accident: MSAA applies to WebGL geometry, so an SVG sprite is nearly blind to it (96 differing pixels of 12.4M) and axis-aligned \`drawRect\` edges are bit-identical with it on or off. \`aa_probe\` exists so the corpus contains edges this lever can actually change.', apply=<function \_disabled_aa>, verify_row=<function \_verify_disabled_aa>), 'high_crf': Lever(name='high_crf', side='encode', what='raise the delivered encode from the pinned CRF to 40', why='moves only post-encode metrics. The golden corpus is upstream of the encoder, so family B cannot see this by construction — which is the reason two disjoint levers are mandatory.', apply=<function \_high_crf>, verify_row=<function \_verify_high_crf>), 'supersample': Lever(name='supersample', side='render', what='build the PixiJS application at resolution 2 with \`autoDensity: false\`, and resolve the frames back to the declared size with an exact 2x2 block mean before anything reads them', why="the instrument's exam against a change somebody WANTS to ship (an#56). Run instead as a plain commit-to-commit diff, \`_verdict_by_optimum\` reports it as 2 false regressions and 7 unearned improvements, plus 7 unscored \`changed\`s including the metric the wave's done-when names — a table that looks like evidence and is not. Its effect is scene-dependent BY MEASUREMENT and in the exact inverse of \`disabled_aa\`: +2.6% to +8.0% edge width on the five procedural scenes and -34.8% on \`promote_demo\`. The two render levers therefore reach complementary scenes, which strengthens the harness rather than diluting it.", apply=<function \_supersample>, verify_row=<function \_verify_supersample>)}*

The levers, keyed by the mutation name the registry declares. At least one
per SIDE is mandatory and the two sides are **disjoint on purpose**: an
encoder lever cannot touch a golden-frame metric, because the corpus sits
UPSTREAM of the encoder. So requiring three families from a CRF change alone
would fail for a reason that has nothing to do with the instrument being
blind — and that failure would be misdiagnosed as the harness being wrong.

The two RENDER levers are not redundant: measured, they reach complementary
scenes. `disabled_aa` is nearly blind to the descriptor path (96 differing
pixels of 12.4M on `promote_demo`, because MSAA applies to WebGL geometry and
an SVG sprite is a pre-rasterised texture); `supersample` hits that same
scene hardest of all six (-34.8% edge width, because the sprite rasterises AT
2x rather than being stretched up from a 1x texture).

### *class* an.bench.mutations.Lever(name, side, what, why, apply, verify_row=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One deliberate, declared change to the pipeline, with the evidence that it took.

#### verify_row *: [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[[[dict](https://docs.python.org/3/builtins/stdtypes.html#dict)], [None](https://docs.python.org/3/builtins/constants.html#None)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Given the ledger row the mutated run produced, raise unless the lever’s
fingerprint is in it. `None` when the row cannot carry one — see the
module docstring.

### *exception* an.bench.mutations.MutationError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A lever could not be applied, or applied and left no trace.

### an.bench.mutations.STAGING_IGNORE *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('_\_pycache_\_',)*

Excluded from the staged copy so the staged tree is a pure function of the
shipped source and the patch — which is what lets `_verify_supersample`
RECOMPUTE the digest it expects instead of settling for “not the shipped
one”. `runtime_sha256()` walks whatever `render.runtime_dir()` returns, so
with this excluded on the staging side and on the recompute side, the two
hash byte-identical file sets.

### an.bench.mutations.SUPERSAMPLE_K *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

The supersample lever’s factor, read at call time so a test can move it. 2
rather than 3, deliberately and with the residual on the record: research §3
renders each corpus scene at rising k and lets `edge_transition_width`
converge, and k=3 reaches that ceiling on every scene that has one while k=2
falls 43% short on `saturated_outline` and 33% short on `graded_field`
(0.09-0.17 px). It is 2 because \*\*the lever must be the change the product
will ship\*\* — an#58 ships k=2 — and a lever measuring a factor nobody will
run is a beautiful number about nothing. Cost, read off 1080p because the
corpus cannot inform it: 0.126 s/f at k=1, 0.319 at k=2 (2.54x), 0.640 at k=3.

### an.bench.mutations.mutated_row(name, \*\*run_kwargs)

Render the corpus with one lever pulled, and prove the lever took.

Deliberately returns a row rather than a comparison: what to do with it is
[`an.bench.compare`](an.bench.compare.md#module-an.bench.compare)’s job, and keeping the two apart is what lets the
criterion be evaluated against a row written months ago.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
