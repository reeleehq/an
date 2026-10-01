# an.bench.golden

The golden gate: committed frames, compared on **decoded pixels**.

Family B of the panel. Everything else in [`an.bench`](an.bench.html.md#module-an.bench) measures a property
of one render; this compares today’s render against a picture a human looked at
and blessed, so it is the only part that can catch a change nobody predicted.

Four decisions here that are easy to get wrong in a way that still looks like
it works:

\*\*The criterion is `sha256` of the decoded RGB array, never the file bytes.\*\*
Chromium 1187 -> 1223 changed 144 of 144 PNG files and **zero** pixels. A
file-byte gate goes red on the first Playwright bump for a reason that has
nothing to do with animation quality — and, worse, trains people to re-bless
without looking.

**The path keys on the Chromium build ALONE** — no platform, no arch. Measured
across arm64 macOS, x86-64 Linux and arm64 Linux, across two different
SwiftShader JIT backends: zero differing pixels *and* zero differing PNG bytes.
Carrying the platform would force one committed copy per platform for no
information. What the convention keeps is its real benefit: a Playwright bump
becomes a **new path requiring a deliberate re-bless**, not a red test with no
explanation.

**Three different absences get three different gates.** “This scene declares no
golden frames”, “goldens exist but not for this Chromium build” and “the
Chromium build could not be determined at all” are three different facts, and a
reader who cannot tell them apart cannot act on any of them. The last one
matters most: [`an.bench.environment.probe_browser()`](an.bench.environment.html.md#an.bench.environment.probe_browser) never raises, it
returns `{"error": ...}` — so without a distinct gate an un-probeable browser
reads exactly like a scene nobody has blessed yet.

**A comparison against a golden written in the same run is a tautology**, so a
`--bless` run records family B as gated rather than as a pass. The row would
otherwise carry a perfect score that no code could ever have failed.

### Module Attributes

| [`BLESS_MANIFEST_TEMPLATE`](#an.bench.golden.BLESS_MANIFEST_TEMPLATE)   | Per-scene, per-build bless record, committed beside the frames.                         |
|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`REQUIRED_GOLDEN_FRAMES`](#an.bench.golden.REQUIRED_GOLDEN_FRAMES)    | How many golden frames a scene must declare.                                            |
| [`GATE_UNDECLARED`](#an.bench.golden.GATE_UNDECLARED)           | Gate names.                                                                             |
| [`RETIRED_GATES`](#an.bench.golden.RETIRED_GATES)             | Gate names that appear in rows written BEFORE this module existed, and what they meant. |

### Functions

| [`bless_scene`](#an.bench.golden.bless_scene)(capture, \*, times, ...[, ...])       | Write one scene's golden frames and its bless record.                         |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`chromium_build_of`](#an.bench.golden.chromium_build_of)(environment)                    | The Chromium build from an environment record, or `None` if unknown.          |
| [`compare_scene`](#an.bench.golden.compare_scene)(capture, \*, times, chromium_build) | Compare today's render against the committed goldens for one scene.           |
| [`frame_index_for`](#an.bench.golden.frame_index_for)(time, \*, fps, n_frames)          | The frame a pinned time names, snapped to the nearest one.                    |
| [`frame_key`](#an.bench.golden.frame_key)(index)                                  | The filename stem for a frame, zero-padded so a directory listing sorts.      |
| [`frame_png_path`](#an.bench.golden.frame_png_path)(capture, ref)                      | Where the renderer left the PNG for one resolved frame.                       |
| [`iter_committed`](#an.bench.golden.iter_committed)(scene, chromium_build, \*[, root]) | Every committed golden PNG for one scene and build, in sorted order.          |
| [`load_manifest`](#an.bench.golden.load_manifest)(scene, chromium_build, \*[, root])  | The committed bless record, or `None` when this scene has never been blessed. |
| [`manifest_path`](#an.bench.golden.manifest_path)(scene, chromium_build, \*[, root])  | Where one scene's bless record for one Chromium build lives.                  |
| [`pixels_sha256`](#an.bench.golden.pixels_sha256)(rgb)                                | `sha256` over the decoded pixels — **shape and dtype included**.              |
| [`resolve_frames`](#an.bench.golden.resolve_frames)(capture, times)                    | Map each pinned time onto `(global index, shot, index within that shot)`.     |

### Classes

| [`FrameRef`](#an.bench.golden.FrameRef)(key, time, index, shot_id, local_index)   | One pinned golden frame, resolved against the render that just happened.   |
|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|

### Exceptions

| [`GoldenError`](#an.bench.golden.GoldenError)   | A bless was refused, or a committed golden is unusable.   |
|----------------------------------------------------------------|-----------------------------------------------------------|

### an.bench.golden.BLESS_MANIFEST_TEMPLATE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'bless-chromium{chromium_build}.json'*

Per-scene, per-build bless record, committed beside the frames. Per build
rather than per scene: a Playwright bump adds a new set of frames under new
names, and the old set stays valid for anyone still on the old build.

### *class* an.bench.golden.FrameRef(key, time, index, shot_id, local_index)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One pinned golden frame, resolved against the render that just happened.

#### local_index *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Index WITHIN that shot’s frame directory.

### an.bench.golden.GATE_UNDECLARED *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'golden_frames_undeclared'*

Gate names. Literals rather than an enum because they are written into the
ledger and read back by `an bench --compare` from rows written by older
registries, so their spelling is a wire format.

### *exception* an.bench.golden.GoldenError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A bless was refused, or a committed golden is unusable.

### an.bench.golden.REQUIRED_GOLDEN_FRAMES *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 2*

How many golden frames a scene must declare. Two, because one frame tests a
single instant and cannot notice a scene that renders its first frame
correctly and then stops.

### an.bench.golden.RETIRED_GATES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'golden_absent': 'golden_absent_for_chromium_build'}*

Gate names that appear in rows written BEFORE this module existed, and what
they meant. `an bench --compare` (an#40) reads old rows as fact, so the one
place a reader has to look is here rather than in a commit message. The
an#36 row carried a single `golden_absent` for both family-B keys, at a time
when the corpus had no goldens for ANY build — which is this module’s
`GATE_ABSENT`, not its `GATE_UNDECLARED` (the fixtures did declare no times,
but the gate was not distinguishing the two).

### an.bench.golden.bless_scene(capture, , times, chromium_build, reason, git, scene_contract_sha256, golden_note='', root=None)

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

### an.bench.golden.chromium_build_of(environment)

The Chromium build from an environment record, or `None` if unknown.

`probe_browser` never raises — it reports an `error` key — so “we could
not ask the browser” arrives here as a missing field rather than as an
exception, and must not be confused with “nobody has blessed this scene”.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.bench.golden.compare_scene(capture, , times, chromium_build, root=None)

Compare today’s render against the committed goldens for one scene.

Returns a dict with `state` in `{"measured", "gated", "unavailable"}`,
the reduced numbers the ledger carries, and a per-frame record for
provenance. The reduction is **worst frame wins**: `identical` is the
conjunction and `min_ssim_win8` is the minimum, because a maximum or a
mean lets one clean frame hide a broken one, and this metric’s own name is
“the worst small window”.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.golden.frame_index_for(time, , fps, n_frames)

The frame a pinned time names, snapped to the nearest one.

`int(time * fps)` is the trap: `0.25 * 24` is `5.999999999999999` in
binary floating point, so the obvious spelling silently picks frame 5.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> frame_index_for(0.25, fps=24, n_frames=12)
6
>>> frame_index_for(0.0, fps=24, n_frames=12)
0
```

### an.bench.golden.frame_key(index)

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

### an.bench.golden.frame_png_path(capture, ref)

Where the renderer left the PNG for one resolved frame.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.bench.golden.iter_committed(scene, chromium_build, , root=None)

Every committed golden PNG for one scene and build, in sorted order.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### an.bench.golden.load_manifest(scene, chromium_build, , root=None)

The committed bless record, or `None` when this scene has never been blessed.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.bench.golden.manifest_path(scene, chromium_build, , root=None)

Where one scene’s bless record for one Chromium build lives.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.bench.golden.pixels_sha256(rgb)

`sha256` over the decoded pixels — **shape and dtype included**.

Never over file bytes, for the reason in the module docstring. And never
over the raw buffer alone either: `tobytes()` carries no shape, so a
320x240 frame and a 240x320 one holding the same bytes hash identically,
and issue #38’s literal “the criterion is `sha256(decoded RGB array)`”
would report PASS on a transposed frame. Both orientations are live in this
corpus. [`an.bench.metrics.golden_comparison()`](an.bench.metrics.html.md#an.bench.metrics.golden_comparison) catches it separately via
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

### an.bench.golden.resolve_frames(capture, times)

Map each pinned time onto `(global index, shot, index within that shot)`.

Indices run over the scene’s **concatenated** timeline — what the delivered
mp4 shows — so a pinned time can land in the second shot, which is exactly
what `multi_shot`’s second golden does.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`FrameRef`](#an.bench.golden.FrameRef)]
