# an.project

Project init/load/save — the on-disk anatomy of an an project.

Layout (from spec §11):

> my-scene/
> ├── an.toml
> ├── scene.md
> ├── ir/scene.json
> ├── assets/{characters,props,environments,voices,styles,sounds}/
> ├── artifacts/{audio,visemes,shots,previews}/
> ├── output/
> └── .an/{decisions.jsonl,verifier_runs/,memory.md}

### Module Attributes

| [`PROJECT_GITIGNORE`](#an.project.PROJECT_GITIGNORE)   | What a project's `.gitignore` keeps out of version control (`an init` adds each line a `.gitignore` lacks, never removing one).   |
|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`init`](#an.project.init)(project_dir, \*[, name, force])   | Create a fresh an project at `project_dir`.                 |
|-----------------------------------------------------------------------------------------|-------------------------------------------------------------|
| [`load`](#an.project.load)(project_dir, \*[, check_kinds])   | Load an existing project.                                   |
| [`save`](#an.project.save)(project)                          | Persist a Project's current scene back to disk (md + json). |

### Classes

| [`Project`](#an.project.Project)(root, mall, scene)   | A loaded an project: directory + mall + current scene.   |
|-------------------------------------------------------------------------------|----------------------------------------------------------|

### an.project.PROJECT_GITIGNORE *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('artifacts/render_reports/',)*

What a project’s `.gitignore` keeps out of version control (`an init`
adds each line a `.gitignore` lacks, never removing one). A render report
records what a render on THIS machine found — warnings, exception text — so it
is per-machine output, not project source (an#254).

### *class* an.project.Project(root, mall, scene)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A loaded an project: directory + mall + current scene.

### an.project.init(project_dir, , name=None, force=False)

Create a fresh an project at `project_dir`.

Idempotent unless the directory already contains a non-empty `scene.md`;
pass `force=True` to overwrite. Returns the absolute project root. The
project’s `.gitignore` gains [`PROJECT_GITIGNORE`](#an.project.PROJECT_GITIGNORE) (lines it lacks).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.project.load(project_dir, , check_kinds=True)

Load an existing project. Reconciles scene.md / ir/scene.json first.

Registers the installed genres first ([`an.genres.load()`](an.genres.html.md#an.genres.load), ADR 0001
decision 3: discovery is explicit, and loading a project is one of the
places it happens), so the scene’s genre kinds — the cut-out genre’s
`play`, `expression` and `character` — read as their own models.

Then refuses a scene that names an action kind, entity kind or renderer
nothing registered ([`an.ir.validate.require_registered_kinds()`](an.ir.validate.html.md#an.ir.validate.require_registered_kinds)): the
schema holds those as `str` (ADR 0001 decision 2), so without this a
typo’d `kind: enviroment` would load and render silently without its
backdrop. `check_kinds=False` is for `an validate`, which reports them
as findings instead.

* **Return type:**
  [`Project`](#an.project.Project)

### an.project.save(project)

Persist a Project’s current scene back to disk (md + json).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
