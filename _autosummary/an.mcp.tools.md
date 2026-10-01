# an.mcp.tools

The curated MCP tools: plain functions over the vocabulary, the capability registry and a project.

ADR 0003 decision 6: the MCP surface is a curated list, not all of
`_dispatch_funcs`. Each tool here is an ordinary function with simple,
JSON-shaped arguments and results (so `py2mcp` can project it, and a test
can call it without any MCP stack):

- **queries** — [`vocabulary()`](#an.mcp.tools.vocabulary), [`vocabulary_entry()`](#an.mcp.tools.vocabulary_entry),
  [`scene_schema()`](#an.mcp.tools.scene_schema), [`validate_scene()`](#an.mcp.tools.validate_scene), [`describe_character()`](#an.mcp.tools.describe_character),
  [`applicable_methods()`](#an.mcp.tools.applicable_methods), [`why_not_method()`](#an.mcp.tools.why_not_method);
- **edits** — [`apply_patch()`](#an.mcp.tools.apply_patch), a typed JSON-pointer patch (the `an
  iterate` patch shape), validated before anything is written, `dry_run` by
  default;
- **long work as jobs** — [`start_render()`](#an.mcp.tools.start_render) returns a job id at once and
  [`job_status()`](#an.mcp.tools.job_status) polls it; nothing blocks a client for minutes. The bench
  > stays CLI-only.

Every tool loads the installed genres first (explicit discovery, ADR 0001
decision 3): their presets, methods and analysers are part of the answer.

```pycon
>>> any(e["id"] == "action.tween" for e in vocabulary(kind="action"))
True
```

### Module Attributes

| [`TOOLS`](#an.mcp.tools.TOOLS)   | The curated surface, in the order a client lists it.   |
|----------------------------------------------------------|--------------------------------------------------------|

### Functions

| [`applicable_methods`](#an.mcp.tools.applicable_methods)(aspect, project_dir, name)   | The methods of `aspect` (`locomotion`, `speech`, …) that apply to the character.                                                            |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| [`apply_patch`](#an.mcp.tools.apply_patch)(project_dir, patches[, dry_run])    | Apply typed JSON-pointer patches to the scene, validated before anything is written.                                                        |
| [`describe_character`](#an.mcp.tools.describe_character)(project_dir, name)           | What a character affords, and per aspect the default method, the applicable ones, and the missing capabilities (with remedies) of the rest. |
| [`job_status`](#an.mcp.tools.job_status)(job)                                 | A job's state: `running`, `done` (with its `result`) or `failed` (with its `error`).                                                        |
| [`scene_schema`](#an.mcp.tools.scene_schema)([document])                        | The JSON Schema of a document: `scene` (the scene IR) or `character` (a descriptor).                                                        |
| [`start_render`](#an.mcp.tools.start_render)(project_dir[, strict_assets, ...]) | Start rendering the project to an mp4; returns `{job}` at once — poll [`job_status()`](#an.mcp.tools.job_status).        |
| [`validate_scene`](#an.mcp.tools.validate_scene)(project_dir)                     | Validate the project's scene (schema and semantics): `{passed, findings}`.                                                                  |
| [`vocabulary`](#an.mcp.tools.vocabulary)([kind, owner])                       | Every registered vocabulary entry (presets, kinds, easings, camera moves, methods, IR fields).                                              |
| [`vocabulary_entry`](#an.mcp.tools.vocabulary_entry)(entry_id)                      | One vocabulary entry by id (`motion.walk`, `loco.legged_cycle`).                                                                            |
| [`why_not_method`](#an.mcp.tools.why_not_method)(method, project_dir, name)       | What the character lacks for `method` to apply, each with its remedy (empty: it applies).                                                   |

### an.mcp.tools.TOOLS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)* *= (<function vocabulary>, <function vocabulary_entry>, <function scene_schema>, <function validate_scene>, <function describe_character>, <function applicable_methods>, <function why_not_method>, <function apply_patch>, <function start_render>, <function job_status>)*

The curated surface, in the order a client lists it.

### an.mcp.tools.applicable_methods(aspect, project_dir, name)

The methods of `aspect` (`locomotion`, `speech`, …) that apply to the character.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.mcp.tools.apply_patch(project_dir, patches, dry_run=True)

Apply typed JSON-pointer patches to the scene, validated before anything is written.

`patches` are `{op: set|append|delete, path: "timeline/0/duration",
value: …}` (the `an iterate` patch shape). The patched scene is validated
(schema and semantics); with `dry_run=False` and a passing validation it
is saved through the scenes store (`scene.md` and `ir/scene.json` stay
in step) and the edit is recorded in the decisions log.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.mcp.tools.describe_character(project_dir, name)

What a character affords, and per aspect the default method, the applicable
ones, and the missing capabilities (with remedies) of the rest.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.mcp.tools.job_status(job)

A job’s state: `running`, `done` (with its `result`) or `failed` (with its `error`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.mcp.tools.scene_schema(document='scene')

The JSON Schema of a document: `scene` (the scene IR) or `character` (a descriptor).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.mcp.tools.start_render(project_dir, strict_assets=False, output_name='main')

Start rendering the project to an mp4; returns `{job}` at once — poll [`job_status()`](#an.mcp.tools.job_status).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.mcp.tools.validate_scene(project_dir)

Validate the project’s scene (schema and semantics): `{passed, findings}`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.mcp.tools.vocabulary(kind='', owner='')

Every registered vocabulary entry (presets, kinds, easings, camera moves, methods, IR fields).

Each entry: id, kind, name (how a document spells it), version, title,
description, accepted spectrum levels, params (JSON Schema with defaults),
examples, requires. `kind` filters (`motion_preset`, `method`, …),
`owner` filters by who registered it (`an`, a genre).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.mcp.tools.vocabulary_entry(entry_id)

One vocabulary entry by id (`motion.walk`, `loco.legged_cycle`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.mcp.tools.why_not_method(method, project_dir, name)

What the character lacks for `method` to apply, each with its remedy (empty: it applies).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]
