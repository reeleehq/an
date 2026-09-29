# an.base

Core types, constants, and re-exports for an.

This module is the *type vocabulary* shared across the package: schema versions,
default render parameters, easing presets, type aliases for paths and time. Heavy
data classes (the Pydantic IR models, the Renderer/Verifier protocols) live in
their own subpackages and are re-exported from `an` itself.

Keep this module small and dependency-light. Everything here should import in a
fraction of a second so the CLI is snappy.

### Module Attributes

| [`SCHEMA_VERSION`](#an.base.SCHEMA_VERSION)                     | Current Scene IR schema version.                                                                                                                                                                                                            |
|-------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`COMPATIBLE_VERSION`](#an.base.COMPATIBLE_VERSION)                 | Minimum Scene IR version this code can still read without migration.                                                                                                                                                                        |
| [`DEFAULT_SUPERSAMPLE`](#an.base.DEFAULT_SUPERSAMPLE)                | Render at this many times the declared resolution, then resolve back with an exact block mean.                                                                                                                                              |
| [`MP4_FASTSTART_ARGS`](#an.base.MP4_FASTSTART_ARGS)                 | Put the mp4's `moov` atom in front of `mdat`, so a player can start before the file has finished downloading.                                                                                                                               |
| [`BT709_SCALE_FILTER`](#an.base.BT709_SCALE_FILTER)                 | The RGB->YUV conversion `an` performs, stated EXPLICITLY rather than left to the encoder flags to imply.                                                                                                                                    |
| [`EASING_PRESETS`](#an.base.EASING_PRESETS)                     | Named easing presets.                                                                                                                                                                                                                       |
| [`COLOUR_PROPERTY`](#an.base.COLOUR_PROPERTY)                    | The property names the cutout runtime animates NUMERICALLY.                                                                                                                                                                                 |
| [`TRIM_PROPERTIES`](#an.base.TRIM_PROPERTIES)                    | The two path-only properties inside `TRANSFORM_PROPERTIES` (an#160).                                                                                                                                                                        |
| [`SWAP_SET_NAME_FORBIDDEN_SUBSTRINGS`](#an.base.SWAP_SET_NAME_FORBIDDEN_SUBSTRINGS) | `/` would read as a path segment and `::` is the runtime's pose-key separator.                                                                                                                                                              |
| [`AUTHORABLE_PROPERTIES`](#an.base.AUTHORABLE_PROPERTIES)              | a compiled transform channel, or the authored colour spelling the compiler expands.                                                                                                                                                         |
| [`PathStr`](#an.base.PathStr)                            | Slash-delimited node path, e.g. `"charlie/head/mouth"`.                                                                                                                                                                                     |
| [`Seconds`](#an.base.Seconds)                            | Time in seconds.                                                                                                                                                                                                                            |
| [`EasingSpec`](#an.base.EasingSpec)                         | Either an easing preset name or a 4-tuple cubic-Bézier control [cx1,cy1,cx2,cy2].                                                                                                                                                           |
| [`RendererName`](#an.base.RendererName)                       | Which renderer draws a shot.                                                                                                                                                                                                                |
| [`SUPPORTED_RENDERERS`](#an.base.SUPPORTED_RENDERERS)                | The same vocabulary as [`RendererName`](#an.base.RendererName), as a runtime tuple — DERIVED from it, because a hand-typed second copy is a second SSOT that drifts on the day a renderer is added and nothing fails. |

### Functions

| [`swap_set_name_problem`](#an.base.swap_set_name_problem)(name)   | Why `name` cannot be a swap-set name, or `None` if it can.   |
|--------------------------------------------------------------------------------|--------------------------------------------------------------|

### an.base.AUTHORABLE_PROPERTIES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'alpha', 'pivot_x', 'pivot_y', 'rotation', 'rotation_rad', 'scale_x', 'scale_y', 'skew_x', 'skew_y', 'tint', 'tint_b', 'tint_g', 'tint_r', 'trim_end', 'trim_start', 'x', 'y'})*

a compiled transform channel, or the authored
colour spelling the compiler expands. Validate checks against this, and the
compiler’s rest table against `TRANSFORM_PROPERTIES` — the difference between
the two sets is exactly `tint`, and a test pins that rather than trusting it.

* **Type:**
  What a set/tween may name

### an.base.BT709_SCALE_FILTER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'scale=out_range=tv:out_color_matrix=bt709'*

The RGB->YUV conversion `an` performs, stated EXPLICITLY rather than left to
the encoder flags to imply.

an#34 pinned `-colorspace bt709` and measured that it does not merely *tag*
the file: it sets the matrix of the auto-inserted conversion, so the encoded
planes themselves change. That measurement was made on ffmpeg 8/9 and \*\*is
not a universal ffmpeg fact\*\* (an#148). Measured on the product’s own
`_ffmpeg_mux` with flat known-colour frames, decoded as raw `yuv420p` (planes
verbatim, no conversion on read), against the analytic limited-range values:

build | pure red decodes to Y | BT.601 says | BT.709 says |
<br/>

```
|---|
```

—

```
|---|
```

—|
| ffmpeg 9.0.1 | 63 | 81.5 | 62.6 |
| ffmpeg 6.1.6 | 81 | 81.5 | 62.6 |

Over five colours and all three planes, the worst disagreement is 0.44 from
BT.709 and 28.45 from BT.601 on ffmpeg 9 – and 0.48 from BT.601 against
27.63 from BT.709 on ffmpeg 6.1.6, which is the CI runner’s apt build. Both
files are *tagged* `color_space=bt709 color_primaries=bt709
color_transfer=bt709 color_range=tv`. So on 6.1 an#34’s re-baseline was
metadata only: `an` shipped BT.601 planes wearing a BT.709 label, and a
conforming player undoes a conversion that was never applied.

This filter removes the build-dependence by naming the conversion instead of
inferring it. It is BYTE-IDENTICAL to today’s output on ffmpeg 9.0.1
(measured: same mp4 sha256 on real corpus frames), so it re-baselines nothing
where the flags already worked, and it moves ffmpeg 6.1.6’s output onto the
same conversion (its residual against an analytic BT.709 reference drops from
luma mean 0.788 to 0.205 – ffmpeg 9’s own number to three decimals).

\*\*The committed ledger rows were captured on ffmpeg 8.1, which is not on this
machine, so the byte-identity above was not re-measured there.\*\* That those
rows are equally unaffected rests on an#34’s own measurement — that on 8.x
`-colorspace bt709` already set the auto-inserted conversion, so this filter
names what that build was doing anyway. It is a sound inference from a
recorded measurement, not a second observation; treat it as such if an 8.x
build ever contradicts a row.

Here, and not beside one of the ffmpeg calls, for the same reason
`MP4_FASTSTART_ARGS` is: **three commands must agree on it**, and they are in
two packages. The delivered mux (`_ffmpeg_mux`), the bench’s lossless
reference leg and the bench’s PNG decode leg all perform this conversion, and
the lossless leg’s entire contract is “these ARE the planes libx264
received”. Pin one and not the others and every encode-side metric silently
measures a colour-space disagreement instead of encoder damage – the failure
`an/bench/imageio.py`’s module docstring records CI catching once already.

### an.base.COLOUR_PROPERTY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'tint'*

The property names the cutout runtime animates NUMERICALLY. Any other
property on a set/tween names a swap SET declared by the target entity’s
descriptor (an#87). This is the SSOT the three consumers share so the IR
validator, the character validator and the compiler cannot drift: the
compiler derives its rest-value table from `TransformJSON` and a test
asserts that derivation equals this set. Lives here because `an.base` is
the one module all three layers may import.
The colour multiply as an AUTHOR spells it. Not in
`TRANSFORM_PROPERTIES` because nothing downstream of the compiler ever
sees it — `_expand_tint_actions` rewrites each leaf into the three numeric
components before the swap-set dispatch, which would otherwise read it as an
asset-set name (an#62).

### an.base.COMPATIBLE_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '0.3.0'*

Minimum Scene IR version this code can still read without migration.

### an.base.DEFAULT_SUPERSAMPLE *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

Render at this many times the declared resolution, then resolve back with an
exact block mean. **1 is off, and off is free**: the un-supersampled path
keeps Chromium’s own PNG bytes and pays nothing.

Here rather than in `an.adapters.cutout.supersample`, where the rest of the
mechanism lives, because `an/adapters/_base.py` needs it for
`RenderContext`’s default and importing the cutout package from there is a
real cycle (`_base` -> `cutout` -> `render` -> `_base`), not a hypothetical
one. `an/base.py` imports nothing from `an`.

The default stays 1 deliberately. Supersampling ships OPT-IN with its A/B
committed (an#58, discussion #52), per the standing rule that a default
chosen by taste ships opt-in and the flip is its own one-line change.

### an.base.EASING_PRESETS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('linear', 'ease', 'ease_in', 'ease_out', 'ease_in_out', 'step')*

Named easing presets. Renderers should accept these and the cubic-Bézier
4-tuple form `[cx1, cy1, cx2, cy2]`. Names follow the GSAP / CSS convention.

### an.base.EasingSpec *: [TypeAlias](https://docs.python.org/3/library/typing.html#typing.TypeAlias)* *= str | tuple[float, float, float, float] | list[float]*

Either an easing preset name or a 4-tuple cubic-Bézier control [cx1,cy1,cx2,cy2].

### an.base.MP4_FASTSTART_ARGS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('-movflags', '+faststart')*

Put the mp4’s `moov` atom in front of `mdat`, so a player can start before
the file has finished downloading.

Here, and not beside one of the ffmpeg calls, because \*\*three separate
commands build the one file a user receives\*\* – the frame mux
(`_ffmpeg_mux`), the audio mux (`_ffmpeg_add_audio`) and the concat
(`_ffmpeg_concat`) – and each of the last two re-lays the container with
`-c copy`, which writes `moov` LAST. The flag was on the first of those
alone, which reads as done and delivers nothing: it applied only to
`silent.mp4`, a per-shot intermediate that is never handed to anyone.
Measured on a local example render (these mp4s are gitignored build
products; `git ls-files` tracks exactly one, and it is moov-last too):
`.an/render_work/shot_s1/silent.mp4` is `ftyp moov free mdat`, while the
per-shot mp4, `artifacts/shots/*.mp4` and `output/main.mp4` are all
`ftyp free mdat moov`. Single-shot and multi-shot alike; an#57’s
“single-shot ones keep it” is wrong, because the `shutil.copy` branch
copies a file that already lost it.

Deliberately NOT part of `DETERMINISTIC_X264_ARGS`. That tuple is an
`ENCODE_ENV_PATHS` comparability key (an/bench/compare.py:98), and this flag
moves no number the panel reads: with `-c copy` it is a container rewrite,
not a re-encode. Verified on ffmpeg 8.1 – elementary-stream sha256
identical, video/audio packet totals identical, file size identical,
decoded YUV sha256 identical, wall time unchanged.

### an.base.PathStr

Slash-delimited node path, e.g. `"charlie/head/mouth"`.

The example matters: an unknown target now RAISES rather than being skipped,
and the long-standing `"charlie/torso/left_arm"` illustration names a node
no rig actually builds — the cutout rigs are flat, so arms are siblings of
the torso, not children of it.

### an.base.RendererName

Which renderer draws a shot. The orchestrator uses this to pick an adapter.

alias of [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[‘cutout’, ‘manim’, ‘motion_graphics’, ‘whiteboard’]

### an.base.SCHEMA_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '0.3.0'*

Current Scene IR schema version. Bump on additive changes; on breaking
changes, also bump COMPATIBLE_VERSION and add a migration in `ir.migrate`.
0.2.0 renamed `Shot.style` -> `Shot.renderer` and `Meta.default_style` ->
`Meta.default_renderer`, and retired `AssetRef(kind="style")` (an#106).
0.3.0 removed `Camera.position` / `.target` / `.focal_length`, which
described a 3D camera this package never had, and gave `Camera` a `keys`
list so it can translate (an#109).

### an.base.SUPPORTED_RENDERERS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('cutout', 'manim', 'motion_graphics', 'whiteboard')*

The same vocabulary as [`RendererName`](#an.base.RendererName), as a runtime tuple — DERIVED
from it, because a hand-typed second copy is a second SSOT that drifts on
the day a renderer is added and nothing fails.

### an.base.SWAP_SET_NAME_FORBIDDEN_SUBSTRINGS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('/', '::')*

`/` would read
as a path segment and `::` is the runtime’s pose-key separator.

* **Type:**
  Characters within which a swap-set name is not addressable

### an.base.Seconds

Time in seconds. Floats at the IR boundary; rational time is used internally
only inside the audio pipeline where drift matters.

### an.base.TRIM_PROPERTIES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'trim_end', 'trim_start'})*

The two path-only properties inside `TRANSFORM_PROPERTIES` (an#160).

### an.base.swap_set_name_problem(name)

Why `name` cannot be a swap-set name, or `None` if it can.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> swap_set_name_problem("hands") is None
True
>>> swap_set_name_problem("alpha")
"'alpha' is a transform property; the runtime's static switch would shadow the set"
>>> swap_set_name_problem("a::b")
"'a::b' contains '::', which is reserved"
```
