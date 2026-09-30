# an.verify

Verification protocol — same interface for human, lint, vision-LM, MoVer.

`StyleLintVerifier` is imported on first use, not here: `an.verify.style` is
also a script (`python -m an.verify.style`), and a package that imports the
module it is about to run as `__main__` makes `runpy` warn that it is
already in `sys.modules`.

### Classes

| [`Verifier`](#an.verify.Verifier)(\*args, \*\*kwargs)                    | Pluggable verifier.                            |
|--------------------------------------------------------------------------------------------------|------------------------------------------------|
| [`Finding`](#an.verify.Finding)(severity, ir_path, description[, ...])  | A single verification issue.                   |
| [`VerificationReport`](#an.verify.VerificationReport)([passed, findings])          | Result of running one or more verifiers.       |
| [`LayoutLintVerifier`](#an.verify.LayoutLintVerifier)()                            | Cheap IR-only verifier.                        |
| [`HumanInTheLoopVerifier`](#an.verify.HumanInTheLoopVerifier)(\*[, prompt])            | Open the mp4, prompt the user to approve.      |
| [`MediaQualityVerifier`](#an.verify.MediaQualityVerifier)(\*[, max_db_floor, ...])   | Post-render quality checks.                    |
| [`VisionLMVerifier`](#an.verify.VisionLMVerifier)(\*[, model, frame_count, ...]) | Claude vision Verifier (skip-if-missing-deps). |
| `StyleLintVerifier`(spec_or_targets, \*[, ...])                                                  | Compare a render to a style spec's `targets`.  |

### *class* an.verify.Finding(severity, ir_path, description, suggested_fix=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single verification issue.

`ir_path` lets the orchestrator route the fix to the correct layer of
the IR — e.g. `"timeline/0/dialogue/1"`.

### *class* an.verify.HumanInTheLoopVerifier(, prompt='Approve render? [y/N/r=reject]: ')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Open the mp4, prompt the user to approve. Implements `Verifier`.

### *class* an.verify.LayoutLintVerifier

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Cheap IR-only verifier. Implements `Verifier`.

### *class* an.verify.MediaQualityVerifier(, max_db_floor=-75.0, dialogue_silence_ratio=0.7, frozen_ssim_threshold=0.999, frame_sample_fps=4.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Post-render quality checks. Implements `Verifier`.

### *class* an.verify.VerificationReport(passed=True, findings=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of running one or more verifiers.

### *class* an.verify.Verifier(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Pluggable verifier. Same interface for human, lint, vision-LM, MoVer.

#### verify(ir, render)

Verify a scene + (optional) render result. `render` may be None
for pre-render lint passes.

* **Return type:**
  [`VerificationReport`](#an.verify.VerificationReport)

### *class* an.verify.VisionLMVerifier(, model='claude-haiku-4-5-20251001', frame_count=4, max_tokens=800, api_key=None, judge=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Claude vision Verifier (skip-if-missing-deps).

#### judge

Injected, per “no globals, no service locators” — and because
injection is what makes record-vs-replay drift impossible: the
recorded and replayed paths are the same call through the same
object, differing only in what the store returns.

### Modules

| [`human`](an.verify.human.md#module-an.verify.human)                 | HumanInTheLoopVerifier — opens the rendered mp4 and asks for approval.                               |
|-----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| [`layout`](an.verify.layout.md#module-an.verify.layout)               | LayoutLintVerifier — cheap pre-render checks on the IR.                                              |
| [`media`](an.verify.media.md#module-an.verify.media)                 | Media verification helpers — audio + frame quality checks for rendered mp4s.                         |
| [`media_quality`](an.verify.media_quality.md#module-an.verify.media_quality) | MediaQualityVerifier — post-render quality checks on the actual mp4.                                 |
| [`style`](an.verify.style.md#module-an.verify.style)                 | Style lint: measure a render's cadence, cut rate and palette, and compare them to a style's targets. |
| [`vision`](an.verify.vision.md#module-an.verify.vision)               | VisionLMVerifier — Claude vision looks at sampled frames and reports issues.                         |
