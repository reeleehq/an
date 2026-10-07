# an.orchestrate

Orchestrator: validate → audio → render → verify.

Phase 5 ships `orchestrate(project_dir, ...)` — the high-level flow that
ties together validation, audio synthesis, rendering, and verification.
The full iterative edit loop (free-text “make Maya’s laugh longer” →
re-render only the affected shot) lives in the `an` skill, which calls
into these primitives.

```pycon
>>> from an.orchestrate import OrchestratorReport
>>> r = OrchestratorReport()
>>> r.success
True
```

### Functions

| [`iterate`](#an.orchestrate.iterate)(project_dir, instruction, \*\*kwargs)    | Apply a free-text edit instruction.                                                                                                                                                                                     |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`orchestrate`](#an.orchestrate.orchestrate)(project_dir, \*[, output_name, ...]) | Run the full pipeline.                                                                                                                                                                                                  |
| [`render_project`](#an.orchestrate.render_project)(project_dir, \*\*kwargs)          | Render the project's scene to a single mp4 under `output/` — the orchestrator's name for [`an.render.render_project()`](an.render.md#an.render.render_project), every keyword forwarded. |
| [`validate_project`](#an.orchestrate.validate_project)(project_dir, \*[, fps, ...])    | Schema + semantic validation of the scene at `project_dir`.                                                                                                                                                             |

### Classes

| [`OrchestratorReport`](#an.orchestrate.OrchestratorReport)([success, output_path, ...])   | Outcome of an end-to-end orchestrated run.   |
|----------------------------------------------------------------------------------------------------|----------------------------------------------|

### *class* an.orchestrate.OrchestratorReport(success=True, output_path=None, validation=None, verifications=<factory>, error=None, root=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Outcome of an end-to-end orchestrated run.

#### merge_verification(vr)

Add `vr` — less any finding this report already holds: the render
report repeats what the pre-render validation found (a synthesized
line still past its shot), and one finding is reported once (an#309).
The SAME finding: severity, path, location and description (its paths
made portable) — so a render that escalates a warning to an error, or
locates it elsewhere, is reported. `vr`’s verdict is kept.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### root *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [None](https://docs.python.org/3/builtins/constants.html#None)*

descriptions are compared with their
paths made portable (the render report stores them so; an#309).

* **Type:**
  The project root, when known

### an.orchestrate.iterate(project_dir, instruction, \*\*kwargs)

Apply a free-text edit instruction. Returns an IterateResult.

Thin re-export for consistency with the rest of the orchestrator surface;
the real implementation lives in `an.iterate`.

### an.orchestrate.orchestrate(project_dir, , output_name='main', verifiers=None, skip_render=False, tts=None, lipsync='offline', parallel=None, language='en')

Run the full pipeline. Returns a structured outcome.

Phases:

> 1. Validate (schema + semantic). Hard fail if the schema is broken.
> 2. Pre-render verifiers (any that accept `render=None`).
> 3. Render (audio is auto-run inside `render` when needed).
> 4. Post-render verifiers.

`verifiers` defaults to `[LayoutLintVerifier(), MediaQualityVerifier()]`
— the second one is why `an.verify.media.ssim`’s threshold is load-bearing
and must not be retuned casually. Pass an empty list
to skip verification, or include `HumanInTheLoopVerifier()` to prompt.
`skip_render=True` runs validation + lint only.

`tts` and `lipsync` accept either a provider name string or a
provider instance — useful for callers (e.g. `muvid`) that want
to inject a `an.audio.WordTimingsLipSync` driven by their
own alignment store, instead of letting `an` re-transcribe. `tts`
defaults to each voice’s own provider (an#305), as `an render` does.

* **Return type:**
  [`OrchestratorReport`](#an.orchestrate.OrchestratorReport)

### an.orchestrate.render_project(project_dir, \*\*kwargs)

Render the project’s scene to a single mp4 under `output/` — the
orchestrator’s name for [`an.render.render_project()`](an.render.md#an.render.render_project), every keyword
forwarded.

It used to re-declare the leaf’s parameters, and the two drifted: the CLI
(`an render`) passed `supersample`, `pix_fmt`, `step_hz` and `language`
here from the day each flag landed, and this wrapper refused all four with
a `TypeError` — invisible because the CLI test stubbed THIS function
rather than the leaf (an#98 review). A pass-through cannot drift.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.orchestrate.validate_project(project_dir, , fps=None, strict_assets=False)

Schema + semantic validation of the scene at `project_dir`.

A `scene.md` that does not PARSE — a dialogue line in no accepted shape
(an#96), a malformed YAML block — is a Finding, not a traceback: `an
validate` exists to print findings, and it used to be the one tool that
stack-dumped on the error it should report.

`fps` is the frame rate the render will use when it is not the scene’s
(`an render --fps`): the checks that depend on it (`step_hz`, a line
heard during a dissolve) use it, as the render will (an#435).

What loading the scene WARNED about (a retired camera field dropped on
read, a migration’s notice) is a warning finding too (an#454): a Python
warning is invisible to an agent reading `an validate`’s findings.

`strict_assets` (an#456) judges the scene as `an render
--strict-assets` will: each stage shot is compiled the way the render
compiles it, refusing stand-ins, and what it refuses is an error on that
shot; the library pins are checked strictly too.

* **Return type:**
  [`ValidationReport`](an.ir.validate.md#an.ir.validate.ValidationReport)
