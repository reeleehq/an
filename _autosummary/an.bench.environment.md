# an.bench.environment

The environment tuple — the fields that decide whether two rows may be compared.

Split into two halves with **different comparison rules**, because the two
sides of the pipeline were measured and their answers are opposite:

**Render side — comparable on any machine.** Both render paths, four machines
(local arm64 macOS, `macos-latest`, `ubuntu-latest` x86-64,
`ubuntu-24.04-arm`), 132 frames each: zero differing pixels *and* zero
differing PNG bytes, across two different SwiftShader JIT backends. So the
render-side metrics need **no cross-machine band column**, and the golden
corpus can be a CI gate. Record the Chromium build and the \*\*launch argv
verbatim\*\* — all four rasteriser configurations report a byte-identical
`UNMASKED_RENDERER_WEBGL` string, so the renderer string is demonstrably
blind to the choice it was proposed to guard.

**Encode side — machine-scoped, not bandable.** Same ISA + same x264 build is
byte-identical; a different ISA moves the decoded stream a little (luma <=2.66%
of samples); a different x264 build moves it by two orders of magnitude (up to
99.2% of samples, mean 

```
|d|
```

 3.94, max 36). A band that wide would swallow
`flat_field_deviation`’s entire crf18->23 signal. So `--compare` (an#40)
must **refuse** rows whose `x264_sei` or `isa` differ, in the same way it
refuses rows with a different `scene_contract_sha256` — the number is
uninterpretable, not good or bad.

### Module Attributes

| [`RUNTIME_DIGEST_SUFFIXES`](#an.bench.environment.RUNTIME_DIGEST_SUFFIXES)   | `_stage_job`'s `shutil.copytree` is a bare copy that DOES deliver everything under the runtime dir into the staged tree, so "what gets staged" cannot be the reason to exclude anything — the real reason is "what the page loads": `index.html`/`preview.html` pull in `.js` (including `vendor/`), `.css` and `.json`, and nothing else under the tree is read by the browser (an#141).   |
|----------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`RUNTIME_IGNORED_SUFFIXES`](#an.bench.environment.RUNTIME_IGNORED_SUFFIXES)  | Suffixes under the runtime dir that are known to be non-runtime — excluded from the digest on purpose, not by omission.                                                                                                                                                                                                                                                                     |

### Functions

| [`environment_record`](#an.bench.environment.environment_record)(\*, pix_fmt[, x264_sei, ...])   | Everything about this machine that could plausibly move a number.            |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`ffmpeg_identity`](#an.bench.environment.ffmpeg_identity)()                                  | The ffmpeg build banner.                                                     |
| [`probe_browser`](#an.bench.environment.probe_browser)()                                    | Launch Chromium with the render path's own flags and read back its identity. |
| [`runtime_sha256`](#an.bench.environment.runtime_sha256)()                                   | A digest of the JS runtime the renderer will stage, files and names.         |
| `tool_version`(name)                                                                                |                                                                              |
| [`x264_sei`](#an.bench.environment.x264_sei)(mp4)                                      | The encoder build + thread count, read straight out of the file.             |

### an.bench.environment.RUNTIME_DIGEST_SUFFIXES *= ('.js', '.html', '.css', '.json')*

`_stage_job`’s
`shutil.copytree` is a bare copy that DOES deliver everything under the
runtime dir into the staged tree, so “what gets staged” cannot be the
reason to exclude anything — the real reason is “what the page loads”:
`index.html`/`preview.html` pull in `.js` (including `vendor/`), `.css` and
`.json`, and nothing else under the tree is read by the browser (an#141).
Package metadata (`__init__.py`), docs (`README.md`), vendor licence text
can change — a stray `.DS_Store` included — without the page the renderer
loads changing at all, and hashing them anyway made the digest answer “did
the runtime change” wrong.

* **Type:**
  Suffixes `runtime_sha256` hashes. Deliberately narrow

### an.bench.environment.RUNTIME_IGNORED_SUFFIXES *= ('', '.py', '.pyc', '.md', '.txt')*

Suffixes under the runtime dir that are known to be non-runtime — excluded
from the digest on purpose, not by omission. `""` covers extension-less
dotfiles (`.DS_Store`, the one this issue was filed over); `.pyc` covers a
stray `__pycache__/*.pyc` from `__init__.py` (the issue’s other named
example — reproducible on this very tree). `test_bench_environment.py`
fails on any suffix that lands in neither this set nor
`RUNTIME_DIGEST_SUFFIXES`, so a future runtime asset (an `.svg`, `.woff`,
`.wasm`, `.mjs`) cannot silently fall outside what the digest sees (an#141).

### an.bench.environment.environment_record(, pix_fmt, x264_sei=None, browser=None)

Everything about this machine that could plausibly move a number.

`browser` lets the caller supply an already-taken probe. The golden gate
needs the Chromium build *before* the run-level provenance is assembled —
the path keys on it — and probing twice would launch a second browser and
could, in principle, report a different build from the one that rendered.

`pix_fmt` is required and has no default, because it is a \*\*comparability
key\*\* and the caller is the only one who can measure it. It must be the
format the delivered files actually are — `imageio.delivered_pix_fmt` — and
not a re-derivation, for the reason an#72 records: the delivered encode
resolves its format from `RenderContext.pix_fmt` *or* the module global,
so reading either one is a second source of truth that can disagree with
the file, and this field is what `bench-compare` uses to decide whether two
encode-side rows may be compared at all.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.bench.environment.ffmpeg_identity()

The ffmpeg build banner. Informational — the `x264_sei` is the key.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.bench.environment.probe_browser()

Launch Chromium with the render path’s own flags and read back its identity.

Never raises: a probe that crashes must not cost a caller a completed
capture, and a recorded `error` is more honest than a missing field that
reads as “nothing to report”.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.bench.environment.runtime_sha256()

A digest of the JS runtime the renderer will stage, files and names.

Provenance, NOT a comparability key: the runtime is the code under test, and
two rows rendered by different runtimes are exactly what `an bench --compare`
exists to compare. What it buys is that a render-side mutation leaves a
fingerprint in the row — before this, the `disabled_aa` lever had no way to
prove it applied, and `assert not report["mutation_may_not_have_applied"]`
asserted nothing for it (an#41 review).

Only files whose suffix is in `RUNTIME_DIGEST_SUFFIXES` are hashed, so a
file that is not staged as a runtime asset — a stray `.DS_Store`, a
`__pycache__` entry, package metadata — cannot move the digest (an#141).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.bench.environment.x264_sei(mp4)

The encoder build + thread count, read straight out of the file.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
