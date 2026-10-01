# an.iterate

Iterative edit loop — free-text instruction → IR patch via Claude → re-render.

Phase 10. The spec’s signature user story:

> > “I say ‘make Maya’s laugh longer and warmer.’ Claude Code edits the IR,
> > re-renders just the affected shot, and shows me the diff. I approve.”

This module turns a free-text instruction into a structured set of patches
on the SceneIR JSON tree, validates them, applies them, persists, and (optionally)
re-renders. The vision LM is Claude Opus 4.7 with adaptive thinking;
`messages.parse()` + a Pydantic schema guarantees the patches are valid
JSON of the expected shape.

Path syntax for patches: slash-delimited JSON-pointer-style. List indices
are integers. Examples:

> “meta/title”
> “timeline/0/duration”
> “timeline/1/dialogue/0/text”
> “timeline/1/dialogue/0/emotion”

Patch operations:

> {“op”: “set”, “path”: “…”, “value”: …}     # replace (or create) value
> {“op”: “append”, “path”: “…”, “value”: …}  # append to a list
> {“op”: “delete”, “path”: “…”}                # remove an entry

The orchestrator records each iteration in `mall["decisions"]` so the
agent can review what changed across runs.

### Functions

| [`iterate`](#an.iterate.iterate)(project_dir, instruction, \*[, ...])   | Apply a free-text instruction to the scene at `project_dir`.   |
|-------------------------------------------------------------------------------------------------|----------------------------------------------------------------|

### Classes

| [`IterateResponse`](#an.iterate.IterateResponse)(\*\*data)                       | Structured reply from Claude for a single iterate() call.   |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| [`IterateResult`](#an.iterate.IterateResult)([success, summary, patches, ...]) | Outcome of an iterate() call.                               |
| [`Patch`](#an.iterate.Patch)(\*\*data)                                 | A single mutation against the SceneIR JSON tree.            |

### Exceptions

| [`IterateError`](#an.iterate.IterateError)   | Raised when an iterate call cannot apply its proposed patches.   |
|-----------------------------------------------------------------|------------------------------------------------------------------|

### *exception* an.iterate.IterateError

Bases: `RuntimeError`

Raised when an iterate call cannot apply its proposed patches.

### *class* an.iterate.IterateResponse(\*\*data)

Bases: `BaseModel`

Structured reply from Claude for a single iterate() call.

#### model_config *: ClassVar[ConfigDict]* *= {}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.iterate.IterateResult(success=True, summary='', patches=<factory>, affected_shots=<factory>, new_scene=None, validation=None, error=None)

Bases: `object`

Outcome of an iterate() call.

### *class* an.iterate.Patch(\*\*data)

Bases: `BaseModel`

A single mutation against the SceneIR JSON tree.

#### model_config *: ClassVar[ConfigDict]* *= {}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.iterate.iterate(project_dir, instruction, , apply=True, model='claude-opus-4-7', max_tokens=4096)

Apply a free-text instruction to the scene at `project_dir`.

Steps:

> 1. Load the project.
> 2. Send the current scene + the instruction to Claude.
> 3. Parse the structured patch response.
> 4. Apply patches to a deep-copied IR; validate.
> 5. If valid and `apply=True`, persist to mall[“scenes”][“main”] and
>    append to mall[“decisions”].

The caller is responsible for re-rendering. `IterateResult.affected_shots`
enumerates which shots changed so the orchestrator can render only those.

* **Return type:**
  [`IterateResult`](#an.iterate.IterateResult)
