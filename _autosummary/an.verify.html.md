# an.verify

Verification protocol — same interface for human, lint, vision-LM, MoVer.

Every public name here is imported on first use (PEP 562), not when the package
is: [`an.verify.constraints`](an.verify.constraints.html.md#module-an.verify.constraints), the constraint lints `an validate` runs
(an#497), is imported by `an.ir` on every `import an`, and the media verifier
behind this package pulls in numpy, which the validate path has no use for.
The cut-out style lint is `cutan.verify.style` (an#225).

### Classes

| [`Verifier`](#an.verify.Verifier)(\*args, \*\*kwargs)                    | Pluggable verifier.                            |
|--------------------------------------------------------------------------------------------------|------------------------------------------------|
| [`Finding`](#an.verify.Finding)(severity, ir_path, description[, ...])  | A single verification issue.                   |
| [`VerificationReport`](#an.verify.VerificationReport)([passed, findings])          | Result of running one or more verifiers.       |
| [`LayoutLintVerifier`](#an.verify.LayoutLintVerifier)()                            | Cheap IR-only verifier.                        |
| [`HumanInTheLoopVerifier`](#an.verify.HumanInTheLoopVerifier)(\*[, prompt])            | Open the mp4, prompt the user to approve.      |
| [`MediaQualityVerifier`](#an.verify.MediaQualityVerifier)(\*[, max_db_floor, ...])   | Post-render quality checks.                    |
| [`VisionLMVerifier`](#an.verify.VisionLMVerifier)(\*[, model, frame_count, ...]) | Claude vision Verifier (skip-if-missing-deps). |

### *class* an.verify.Finding(severity, ir_path, description, suggested_fix=None, location=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single verification issue.

`ir_path` lets the orchestrator route the fix to the correct layer of
the IR — e.g. `"timeline/0/dialogue/1"`. `location` is set when the
thing to fix is not IR at all but an OPAQUE SOURCE the shot runs — a Manim
scene file — as `"<file>:<line>"` (core study §2.10): the fix then goes
to that line, and `ir_path` still names the shot that runs it.

```pycon
>>> Finding("warning", "timeline/0/options/source", "text cut off",
...         location="assets/sources/chart.py:14").location
'assets/sources/chart.py:14'
```

### *class* an.verify.HumanInTheLoopVerifier(, prompt='Approve render? [y/N/r=reject]: ')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Open the mp4, prompt the user to approve. Implements `Verifier`.

### *class* an.verify.LayoutLintVerifier

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Cheap IR-only verifier. Implements `Verifier`.

### *class* an.verify.MediaQualityVerifier(, max_db_floor=-75.0, dialogue_silence_ratio=0.7, frozen_ssim_threshold=0.999, frame_sample_fps=4.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Post-render quality checks. Implements `Verifier`.

### *class* an.verify.VerificationReport(passed=True, findings=list())

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

| [`constraints`](an.verify.constraints.html.md#module-an.verify.constraints)     | Constraints: declarative statements a lint checks and a solver may enforce (an#497).         |
|-----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| [`holds`](an.verify.holds.html.md#module-an.verify.holds)                 | The hold checks: what `an validate` says about a shot's holds (an#502, catalogue A1 and A4). |
| [`human`](an.verify.human.html.md#module-an.verify.human)                 | HumanInTheLoopVerifier — opens the rendered mp4 and asks for approval.                       |
| [`joints`](an.verify.joints.html.md#module-an.verify.joints)               | The joint checks: what `an validate` says about a shot's joints (ADR 0008, an#512).          |
| [`layout`](an.verify.layout.html.md#module-an.verify.layout)               | LayoutLintVerifier — cheap pre-render checks on the IR.                                      |
| [`media`](an.verify.media.html.md#module-an.verify.media)                 | Media verification helpers — audio + frame quality checks for rendered mp4s.                 |
| [`media_quality`](an.verify.media_quality.html.md#module-an.verify.media_quality) | MediaQualityVerifier — post-render quality checks on the actual mp4.                         |
| [`prosody`](an.verify.prosody.html.md#module-an.verify.prosody)             | Prosody measurement: how a recorded voice delivers its words, as numbers a target can check. |
| [`vision`](an.verify.vision.html.md#module-an.verify.vision)               | VisionLMVerifier — Claude vision looks at sampled frames and reports issues.                 |
