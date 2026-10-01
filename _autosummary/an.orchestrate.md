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
| [`validate_project`](#an.orchestrate.validate_project)(project_dir)                    | Schema + semantic validation of the scene at `project_dir`.                                                                                                                                                             |

### Classes

| [`OrchestratorReport`](#an.orchestrate.OrchestratorReport)([success, output_path, ...])   | Outcome of an end-to-end orchestrated run.   |
|----------------------------------------------------------------------------------------------------|----------------------------------------------|

### *class* an.orchestrate.OrchestratorReport(success=True, output_path=None, validation=None, verifications=<factory>, error=None)

Bases: `object`

Outcome of an end-to-end orchestrated run.

### an.orchestrate.iterate(project_dir, instruction, \*\*kwargs)

Apply a free-text edit instruction. Returns an IterateResult.

Thin re-export for consistency with the rest of the orchestrator surface;
the real implementation lives in `an.iterate`.

### an.orchestrate.orchestrate(project_dir, , output_name='main', verifiers=None, skip_render=False, tts='offline', lipsync='offline', parallel=None, language='en')

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
to inject a [`an.audio.WordTimingsLipSync`](an.audio.md#an.audio.WordTimingsLipSync) driven by their
own alignment store, instead of letting `an` re-transcribe.

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
  `Path`

### an.orchestrate.validate_project(project_dir)

Schema + semantic validation of the scene at `project_dir`.

A `scene.md` that does not PARSE — a dialogue line in no accepted shape
(an#96), a malformed YAML block — is a Finding, not a traceback: `an
validate` exists to print findings, and it used to be the one tool that
stack-dumped on the error it should report.

* **Return type:**
  [`ValidationReport`](an.ir.validate.md#an.ir.validate.ValidationReport)
